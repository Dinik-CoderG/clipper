"""Clip pipeline: download -> transcribe -> pick best moments -> face-tracked vertical render with captions."""
from __future__ import annotations

import json
import math
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

MAX_DURATION_S = 3 * 60 * 60
OUT_W, OUT_H = 1080, 1920
MIN_CLIP_S, MAX_CLIP_S = 20.0, 60.0

Progress = Callable[[str, float, str], None]  # (stage, fraction 0..1, message)


@dataclass
class Word:
    start: float
    end: float
    text: str


@dataclass
class Segment:
    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)


@dataclass
class Moment:
    start: float
    end: float
    title: str
    score: int
    reason: str


# ---------------------------------------------------------------- download

def download(url: str, job_dir: Path, progress: Progress) -> tuple[Path, dict]:
    import yt_dlp

    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "noplaylist": True}) as ydl:
        info = ydl.extract_info(url, download=False)
    duration = info.get("duration") or 0
    if duration and duration > MAX_DURATION_S:
        raise ValueError(f"Video is {duration / 3600:.1f}h long; the limit is 3 hours.")
    if info.get("is_live"):
        raise ValueError("Live streams can't be clipped until they finish.")

    def hook(d):
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            frac = d.get("downloaded_bytes", 0) / total if total else 0
            progress("download", min(frac, 0.99), f"Pulling the video… {frac * 100:.0f}%")

    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        # prefer H.264: AV1/VP9 decode is several times slower on CPU and the GTX 16xx can't hardware-decode AV1
        "format": "bv*[height<=1080][vcodec^=avc1]+ba[ext=m4a]/bv*[height<=1080][ext=mp4]+ba[ext=m4a]"
                  "/bv*[height<=1080]+ba/b[height<=1080]/b",
        "merge_output_format": "mp4",
        "outtmpl": str(job_dir / "source.%(ext)s"),
        "progress_hooks": [hook],
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
    src = next(p for p in job_dir.glob("source.*") if p.suffix in (".mp4", ".mkv", ".webm"))
    meta = {
        "title": info.get("title") or "Untitled",
        "duration": duration,
        "uploader": info.get("uploader") or info.get("channel") or "",
        "thumbnail": info.get("thumbnail"),
    }
    progress("download", 1.0, "Video pulled")
    return src, meta


# ---------------------------------------------------------------- transcribe

_whisper = None
whisper_device = ""  # e.g. "cuda/float16" or "cpu/int8", for logs


def _add_cuda_dll_dirs() -> None:
    """Let Windows find cuBLAS/cuDNN from the nvidia-*-cu12 pip wheels (not on the DLL search path by default)."""
    if os.name != "nt":
        return
    import site

    for base in site.getsitepackages():
        for bin_dir in Path(base).glob("nvidia/*/bin"):
            os.add_dll_directory(str(bin_dir))
            os.environ["PATH"] = f"{bin_dir}{os.pathsep}{os.environ['PATH']}"


def _load_whisper():
    global _whisper, whisper_device
    if _whisper is None:
        from faster_whisper import WhisperModel

        import numpy as np

        size = os.environ.get("CLIPPER_WHISPER_MODEL", "base")
        if os.environ.get("CLIPPER_DEVICE", "auto") != "cpu":
            _add_cuda_dll_dirs()
            # some GTX 16xx cards misbehave in pure fp16, so fall back through cheaper CUDA modes
            for compute in ("float16", "int8_float16", "int8"):
                try:
                    model = WhisperModel(size, device="cuda", compute_type=compute)
                    # missing cuBLAS/cuDNN DLLs only fail at inference time, so warm up before trusting CUDA
                    list(model.transcribe(np.zeros(16000, dtype=np.float32))[0])
                    _whisper, whisper_device = model, f"cuda/{compute}"
                    break
                except Exception:
                    continue
        if _whisper is None:
            _whisper, whisper_device = WhisperModel(size, device="cpu", compute_type="int8"), "cpu/int8"
    return _whisper


def transcribe(src: Path, job_dir: Path, duration: float, progress: Progress) -> tuple[list[Segment], str]:
    wav = job_dir / "audio.wav"
    _ffmpeg(["-i", str(src), "-vn", "-ac", "1", "-ar", "16000", str(wav)])
    progress("transcribe", 0.02, "Listening to the whole video…")
    model = _load_whisper()
    # feed samples directly: faster-whisper's own PyAV decoder breaks on newer PyAV releases
    seg_iter, info = model.transcribe(_read_wav(wav), word_timestamps=True, vad_filter=True)
    segments: list[Segment] = []
    for s in seg_iter:
        words = [Word(w.start, w.end, w.word.strip()) for w in (s.words or []) if w.word.strip()]
        segments.append(Segment(s.start, s.end, s.text.strip(), words))
        if duration:
            progress("transcribe", min(s.end / duration, 0.99), f"Transcribing… {_ts(s.end)} / {_ts(duration)}")
    (job_dir / "transcript.json").write_text(
        json.dumps([{"start": s.start, "end": s.end, "text": s.text} for s in segments], ensure_ascii=False),
        encoding="utf-8",
    )
    wav.unlink(missing_ok=True)
    progress("transcribe", 1.0, f"Transcribed ({info.language}, {whisper_device})")
    return segments, info.language


def _read_wav(path: Path):
    import wave

    import numpy as np

    with wave.open(str(path), "rb") as f:
        pcm = f.readframes(f.getnframes())
    return np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0


# ---------------------------------------------------------------- pick moments

def pick_moments(segments: list[Segment], duration: float, max_clips: int, progress: Progress) -> list[Moment]:
    if not segments:
        raise ValueError("No speech found in this video, so there's nothing to clip.")
    progress("moments", 0.1, "Finding the hooks…")
    moments: list[Moment] = []
    if _has_claude_credentials():
        try:
            moments = _pick_with_claude(segments, max_clips)
        except Exception as e:  # fall back to the heuristic rather than failing the job
            progress("moments", 0.3, f"AI picker unavailable ({type(e).__name__}); using built-in scorer")
    if not moments:
        moments = _pick_heuristic(segments, max_clips)
    moments = [_snap(m, segments, duration) for m in moments]
    moments.sort(key=lambda m: -m.score)
    progress("moments", 1.0, f"Found {len(moments)} moments")
    return moments


def _has_claude_credentials() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


MOMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "clips": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "number"},
                    "end": {"type": "number"},
                    "title": {"type": "string"},
                    "score": {"type": "integer"},
                    "reason": {"type": "string"},
                },
                "required": ["start", "end", "title", "score", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["clips"],
    "additionalProperties": False,
}


def _pick_with_claude(segments: list[Segment], max_clips: int) -> list[Moment]:
    import anthropic

    lines = "\n".join(f"[{s.start:.1f}-{s.end:.1f}] {s.text}" for s in segments)
    prompt = (
        f"Below is a timestamped transcript of a long video. Pick up to {max_clips} self-contained moments "
        f"that would perform best as vertical short-form clips (TikTok, Reels, Shorts).\n\n"
        f"Each clip must be {MIN_CLIP_S:.0f}-{MAX_CLIP_S:.0f} seconds, start on a strong hook (a claim, question, "
        "surprise or story opening), make sense without the rest of the video, and end on a complete thought. "
        "Use the transcript timestamps for start/end. Clips must not overlap. Spread picks across the whole video, "
        "not just the intro. Give each a short punchy title (max 8 words) and a virality score from 0-100.\n\n"
        f"<transcript>\n{lines}\n</transcript>"
    )
    client = anthropic.Anthropic()
    with client.messages.stream(
        model=os.environ.get("CLIPPER_MODEL", "claude-opus-5-5"),
        max_tokens=16000,
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": MOMENT_SCHEMA}},
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        response = stream.get_final_message()
    if response.stop_reason == "refusal":
        return []
    text = next(b.text for b in response.content if b.type == "text")
    clips = json.loads(text)["clips"]
    return [Moment(float(c["start"]), float(c["end"]), c["title"], int(c["score"]), c["reason"]) for c in clips]


HOOK_WORDS = re.compile(
    r"\b(secret|never|always|nobody|everyone|biggest|worst|best|mistake|truth|actually|crazy|insane|"
    r"how to|why|what if|the reason|here's|imagine|story|million|thousand|money|realized|wrong|stop)\b",
    re.I,
)


def _pick_heuristic(segments: list[Segment], max_clips: int) -> list[Moment]:
    """Score windows that start on a segment boundary by speech density and hook signals."""
    candidates: list[Moment] = []
    for i, first in enumerate(segments):
        text, j = "", i
        while j < len(segments) and segments[j].end - first.start <= MAX_CLIP_S:
            text += " " + segments[j].text
            j += 1
        if j == i:
            continue
        end = segments[j - 1].end
        length = end - first.start
        if length < MIN_CLIP_S:
            continue
        words = len(text.split())
        density = words / length  # words per second; energetic speech ≈ 3+
        opener = first.text
        score = (
            min(density / 3.2, 1.0) * 45
            + min(len(HOOK_WORDS.findall(text)), 5) * 5
            + (12 if re.search(r"\?|!", opener) or HOOK_WORDS.search(opener) else 0)
            + (8 if re.search(r"\d", text) else 0)
            + (5 if opener[:1].isupper() else 0)
        )
        title = " ".join(opener.split()[:8]).rstrip(",.;:") or "Highlight"
        candidates.append(Moment(first.start, end, title, int(min(score, 99)), "Dense, hook-heavy stretch"))
    candidates.sort(key=lambda m: -m.score)
    chosen: list[Moment] = []
    for c in candidates:
        if all(c.end <= m.start or c.start >= m.end for m in chosen):
            chosen.append(c)
        if len(chosen) >= max_clips:
            break
    return chosen


def _snap(m: Moment, segments: list[Segment], duration: float) -> Moment:
    """Clamp to the video and nudge edges onto word boundaries so clips don't cut mid-word."""
    words = [w for s in segments for w in s.words]
    start, end = max(0.0, m.start), min(m.end, duration or m.end)
    if words:
        start = min((w.start for w in words if w.start >= start - 0.5), default=start)
        end = max((w.end for w in words if w.end <= end + 0.5), default=end)
    end = min(max(end, start + MIN_CLIP_S / 2), start + MAX_CLIP_S + 5)
    return Moment(round(start, 2), round(end + 0.25, 2), m.title, m.score, m.reason)


# ---------------------------------------------------------------- face tracking

def face_track(src: Path, start: float, end: float) -> tuple[list[tuple[float, float]], int, int]:
    """Return [(t_rel, x_center_px)] keyframes, plus source width/height."""
    import cv2
    import numpy as np

    w, h = _probe_size(src)
    det_w = min(960, w)  # wide stage shots have tiny faces; keep enough resolution to find them
    det_h = int(h * det_w / w) // 2 * 2
    scale = det_w / max(w, 1)
    # one sequential decode of just this window at 2 fps; per-sample seeking re-decodes from a keyframe every time
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-threads", "4", "-ss", f"{start:.2f}", "-i", str(src),
         "-t", f"{end - start:.2f}", "-an", "-vf", f"fps=2,scale={det_w}:{det_h},format=gray",
         "-f", "rawvideo", "-"],
        capture_output=True,
    )
    frame_bytes = det_w * det_h
    frames = np.frombuffer(proc.stdout, dtype=np.uint8)[: len(proc.stdout) // frame_bytes * frame_bytes]
    frames = frames.reshape(-1, det_h, det_w)
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    samples: list[tuple[float, float | None]] = []
    for i, frame in enumerate(frames):
        faces = cascade.detectMultiScale(cv2.equalizeHist(frame), 1.08, 5, minSize=(18, 18))
        if len(faces):
            x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])  # biggest face = speaker
            samples.append((i * 0.5, (x + fw / 2) / scale))
        else:
            samples.append((i * 0.5, None))

    # fill gaps with last seen face (or frame center), then smooth + dead-zone to avoid jitter
    xs, last = [], w / 2
    first_seen = next((x for _, x in samples if x is not None), w / 2)
    last = first_seen
    for ts, x in samples:
        last = x if x is not None else last
        xs.append((ts, last))
    smoothed = []
    for i, (ts, _) in enumerate(xs):
        window = [x for _, x in xs[max(0, i - 3): i + 4]]
        smoothed.append((ts, sorted(window)[len(window) // 2]))
    deadzone = w * 0.06
    keys: list[tuple[float, float]] = []
    for ts, x in smoothed:
        if not keys or abs(x - keys[-1][1]) > deadzone:
            keys.append((ts, x))
    return keys[:40] or [(0.0, w / 2)], w, h


def _crop_x_expr(keys: list[tuple[float, float]], src_w: int, crop_w: int) -> str:
    def clamp(x: float) -> float:
        return max(0.0, min(src_w - crop_w, x - crop_w / 2))

    if len(keys) == 1:
        return f"{clamp(keys[0][1]):.1f}"
    # piecewise linear pans of 0.6s toward each new keyframe position
    expr = f"{clamp(keys[-1][1]):.1f}"
    for (t0, x0), (t1, x1) in reversed(list(zip(keys, keys[1:]))):
        a, b = clamp(x0), clamp(x1)
        pan_start = max(t0, t1 - 0.6)
        expr = (
            f"if(lt(t,{pan_start:.2f}),{a:.1f},"
            f"if(lt(t,{t1:.2f}),{a:.1f}+({b - a:.1f})*(t-{pan_start:.2f})/{max(t1 - pan_start, 0.01):.2f},{expr}))"
        )
    return expr


# ---------------------------------------------------------------- captions

def write_ass(path: Path, segments: list[Segment], start: float, end: float, style: dict) -> None:
    words = [w for s in segments for w in s.words if w.end > start and w.start < end]
    font = style.get("font", "Montserrat Black")
    hi = _ass_color(style.get("highlight", "#FFE600"))
    base = _ass_color(style.get("color", "#FFFFFF"))
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {OUT_W}
PlayResY: {OUT_H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{font},92,{base},{base},&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,6,3,2,80,80,520,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    chunk = 3
    for i in range(0, len(words), chunk):
        group = words[i:i + chunk]
        for k, w in enumerate(group):
            t0 = max(w.start, start) - start
            t1 = (group[k + 1].start if k + 1 < len(group) else w.end) - start
            t1 = min(t1, end - start)
            if t1 <= t0:
                continue
            text = " ".join(
                (f"{{\\c{hi}}}{_ass_escape(g.text.upper())}{{\\c{base}}}" if j == k else _ass_escape(g.text.upper()))
                for j, g in enumerate(group)
            )
            lines.append(f"Dialogue: 0,{_ass_ts(t0)},{_ass_ts(t1)},Cap,,0,0,0,,{{\\fscx104\\fscy104}}{text}")
    path.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")


def _ass_color(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H00{b}{g}{r}".upper()


def _ass_escape(s: str) -> str:
    return s.replace("{", "(").replace("}", ")").replace("\\", "")


def _ass_ts(t: float) -> str:
    t = max(t, 0)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


# ---------------------------------------------------------------- render

def render_clip(src: Path, job_dir: Path, idx: int, m: Moment, segments: list[Segment], captions: bool, style: dict) -> dict:
    keys, src_w, src_h = face_track(src, m.start, m.end)
    crop_h = src_h - src_h % 2
    crop_w = min(src_w, int(crop_h * 9 / 16)) // 2 * 2
    x_expr = _crop_x_expr(keys, src_w, crop_w)
    name = f"clip_{idx:02d}"
    vf = f"crop={crop_w}:{crop_h}:'{x_expr}':0,scale={OUT_W}:{OUT_H}:flags=lanczos,setsar=1"
    if captions:
        write_ass(job_dir / f"{name}.ass", segments, m.start, m.end, style)
        vf += f",subtitles={name}.ass"  # relative path: ffmpeg runs with cwd=job_dir (avoids Windows drive-colon escaping)
    io_args = ["-threads", "4", "-ss", f"{m.start:.2f}", "-i", str(src.resolve()), "-t", f"{m.end - m.start:.2f}", "-vf", vf]
    tail = ["-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", f"{name}.mp4"]
    x264 = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]
    if _nvenc_ok():
        try:
            _ffmpeg([*io_args, "-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "21", "-b:v", "0", *tail], cwd=job_dir)
        except RuntimeError:
            _nvenc["ok"] = False  # e.g. encoder sessions busy; stay on x264 for the rest of this process
            _ffmpeg([*io_args, *x264, *tail], cwd=job_dir)
    else:
        _ffmpeg([*io_args, *x264, *tail], cwd=job_dir)
    _ffmpeg(["-ss", "1", "-i", f"{name}.mp4", "-frames:v", "1", "-vf", "scale=360:-2", f"{name}.jpg"], cwd=job_dir)
    transcript = " ".join(s.text for s in segments if s.end > m.start and s.start < m.end)
    return {
        "id": name,
        "title": m.title,
        "score": m.score,
        "reason": m.reason,
        "start": m.start,
        "end": m.end,
        "duration": round(m.end - m.start, 1),
        "transcript": transcript,
        "video": f"{name}.mp4",
        "thumb": f"{name}.jpg",
    }


_nvenc: dict[str, bool | None] = {"ok": None}


def _nvenc_ok() -> bool:
    """True when ffmpeg can encode H.264 on the NVIDIA GPU (checked once per process)."""
    if _nvenc["ok"] is None:
        if os.environ.get("CLIPPER_ENCODER", "auto") == "cpu":
            _nvenc["ok"] = False
        else:
            try:
                _ffmpeg(["-f", "lavfi", "-i", "color=black:s=256x256:d=0.2", "-c:v", "h264_nvenc", "-f", "null", "-"])
                _nvenc["ok"] = True
            except RuntimeError:
                _nvenc["ok"] = False
    return bool(_nvenc["ok"])


def _probe_size(src: Path) -> tuple[int, int]:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                          "-of", "csv=p=0", str(src)], capture_output=True, text=True)
    w, h = (int(v) for v in out.stdout.strip().split(",")[:2])
    return w, h


def _ffmpeg(args: list[str], cwd: Path | None = None) -> None:
    proc = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args],
                          cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr.strip()[-600:]}")


def _ts(t: float) -> str:
    t = int(t)
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60}:{t % 60:02d}"


# ---------------------------------------------------------------- orchestrate

def run_job(url: str, job_dir: Path, opts: dict, progress: Progress) -> dict:
    src, meta = download(url, job_dir, progress)
    if not meta["duration"]:
        meta["duration"] = _probe_duration(src)
    segments, lang = transcribe(src, job_dir, meta["duration"], progress)
    moments = pick_moments(segments, meta["duration"], int(opts.get("max_clips", 6)), progress)
    clips = []
    for i, m in enumerate(moments, 1):
        progress("render", (i - 1) / len(moments), f"Cutting clip {i} of {len(moments)}: {m.title}")
        clips.append(render_clip(src, job_dir, i, m, segments, opts.get("captions", True), opts.get("style", {})))
    progress("render", 1.0, "Clips ready")
    if not opts.get("keep_source"):
        src.unlink(missing_ok=True)
    return {"meta": {**meta, "language": lang}, "clips": clips}


def _probe_duration(src: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(src)],
                         capture_output=True, text=True)
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0
