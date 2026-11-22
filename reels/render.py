"""Render 1080x1920 Instagram Reels from a campaign's clips.json: gameplay on the TV of a real gaming-room photo
(frames/real_frame.py), a hook on the wall above the TV and dialogue captions just below it.

usage: render.py <campaign> [clip_id ...]"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

TOOL = Path(__file__).parent
sys.path.insert(0, str(TOOL))            # scripts here run with python -P
sys.path.insert(0, str(TOOL / "frames"))
import campaign  # noqa: E402
import encode  # noqa: E402
import real_frame  # noqa: E402

ROOT, ONLY = campaign.from_argv("render.py <campaign> [clip_id ...]")
SRC = ROOT / "source"
ANALYSIS = ROOT / "analysis"
OUT = ROOT / "clips"

W, H = 1080, 1920
# clips alternate between these frames (a clip can set "frame"); a campaign's frames.json overrides the rotation
FRAMES = ["1_neon_tv", "2_neon_coffee_table"]
if (ROOT / "frames.json").exists():
    FRAMES = json.loads((ROOT / "frames.json").read_text(encoding="utf-8-sig"))
CENSOR = {"shit": "SH*T", "fuck": "F*CK", "damn": "DAMN"}


def ass_ts(t: float) -> str:
    t = max(t, 0)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("{", "(").replace("}", ")")


def segments(clip: dict) -> list[tuple[float, float]]:
    """Source ranges the clip is cut from: "segments": [[s, e], ...] or a single "start"/"end"."""
    return [tuple(s) for s in clip["segments"]] if clip.get("segments") else [(clip["start"], clip["end"])]


def to_out(clip: dict, t: float) -> float | None:
    """Source second -> second in the finished clip (None if that moment was cut out)."""
    off = 0.0
    for s, e in segments(clip):
        if s - 0.05 <= t <= e + 0.05:
            return off + min(max(t - s, 0), e - s)
        off += e - s
    return None


def duration(clip: dict) -> float:
    return sum(e - s for s, e in segments(clip))


def words_in(clip: dict) -> list[tuple[float, float, str]]:
    rows = json.loads((ANALYSIS / clip["source"] / "transcript.json").read_text(encoding="utf-8"))
    words: list[tuple[float, float, str]] = []
    for r in rows:
        for a, b, w in r["words"]:
            oa, ob = to_out(clip, a), to_out(clip, b)
            if oa is None or ob is None or ob < oa:
                continue
            if w.startswith("-") and words:  # Whisper splits "K-pop" into "K" + "-pop"
                pa, _, pw = words.pop()
                words.append((pa, ob, pw + w))
            else:
                words.append((oa, ob, w))
    return words


def write_ass(path: Path, clip: dict, caption_y: int) -> None:
    dur = duration(clip)
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 0", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Cap,Impact,76,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,1,0,1,6,2,8,60,60,"
        f"{caption_y},1",
        "Style: Line,Arial,52,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,5,2,8,70,70,"
        f"{caption_y},1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    # in-game subtitles transcribed by hand: [start, end, speaker, text] in source time
    for a, b, who, text in clip.get("cues", []):
        oa, ob = to_out(clip, a), to_out(clip, b)
        if oa is None or ob is None:
            continue
        speaker = f"{{\\c&H00D7FF&}}{esc(who.upper())}: {{\\c&HFFFFFF&}}" if who else ""
        lines.append(f"Dialogue: 0,{ass_ts(oa)},{ass_ts(ob)},Line,,0,0,0,,{speaker}{esc(text)}")
    if clip.get("captions") == "whisper":
        words = []
        for a, b, w in words_in(clip):
            bare = w.rstrip(".,!?")
            words.append((a, b, CENSOR.get(bare.lower(), bare) + w[len(bare):]))
        # chunks of up to 3 words that never cross a sentence end; the word being spoken is highlighted yellow
        chunks: list[list[tuple[float, float, str]]] = [[]]
        for w in words:
            if len(chunks[-1]) == 3:
                chunks.append([])
            chunks[-1].append(w)
            if w[2].endswith((".", "?", "!")):
                chunks.append([])
        chunks = [c for c in chunks if c]
        for ci, chunk in enumerate(chunks):
            nxt = chunks[ci + 1][0][0] if ci + 1 < len(chunks) else dur
            chunk_end = min(max(chunk[-1][1] + 0.25, chunk[-1][1]), nxt, dur)
            for wi, (a, b, _) in enumerate(chunk):
                b2 = chunk[wi + 1][0] if wi + 1 < len(chunk) else chunk_end
                parts = [("{\\c&H00FFFF&}" if j == wi else "") + esc(w.upper()) + ("{\\c&HFFFFFF&}" if j == wi else "")
                         for j, (_, _, w) in enumerate(chunk)]
                lines.append(f"Dialogue: 0,{ass_ts(a)},{ass_ts(b2)},Cap,,0,0,0,,{' '.join(parts)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def cut_source(clip: dict, dst: Path) -> None:
    """Cut the clip's segment(s) from the source into one 1080p30 file (tiny audio fades at each join).
    Decoding 4K once here keeps the room-frame render light on memory."""
    segs = segments(clip)
    src = str(SRC / f"{clip['source']}.mp4")
    ins, parts = [], []
    for i, (s, e) in enumerate(segs):
        ins += ["-ss", str(s), "-to", str(e), "-i", src]
        d = e - s
        parts.append(f"[{i}:v]scale=1920:1080:flags=lanczos,fps=30,setsar=1,setpts=PTS-STARTPTS[v{i}];"
                     f"[{i}:a]aresample=48000,asetpts=PTS-STARTPTS,afade=t=in:d=0.04,"
                     f"afade=t=out:st={max(d - 0.04, 0):.3f}:d=0.04[a{i}]")
    joined = "".join(f"[v{i}][a{i}]" for i in range(len(segs)))
    fc = ";".join(parts) + f";{joined}concat=n={len(segs)}:v=1:a=1[v][a]"
    encode.run(lambda vcodec: ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-threads", "2", *ins,
                               "-filter_complex", fc, "-map", "[v]", "-map", "[a]", *vcodec,
                               "-c:a", "aac", "-b:a", "256k", str(dst)],
               x264=["-c:v", "libx264", "-preset", "fast", "-crf", "12", "-threads", "2"], quality="intermediate")


def render(clip: dict, frame: str) -> Path:
    OUT.mkdir(exist_ok=True)
    out = OUT / f"{clip['id']}.mp4"
    ass = OUT / f"{clip['id']}.ass"
    cut = OUT / f"{clip['id']}.cut.mp4"
    box = real_frame.screen_box(frame)
    write_ass(ass, clip, box["y"] + box["h"] + 45)   # captions just below the TV
    cut_source(clip, cut)
    real_frame.compose(frame, str(cut), 0, duration(clip), clip["hook"], out, ass)
    cut.unlink(missing_ok=True)
    return out


def main() -> None:
    clips = json.loads((ROOT / "clips.json").read_text(encoding="utf-8-sig"))  # -sig: Windows editors add a BOM
    only = set(ONLY)
    for i, clip in enumerate(clips):
        if only and clip["id"] not in only:
            continue
        frame = clip.get("frame", FRAMES[i % len(FRAMES)])
        print("rendering", clip["id"], "on", frame, flush=True)
        print("  ->", render(clip, frame), flush=True)


if __name__ == "__main__":
    main()
