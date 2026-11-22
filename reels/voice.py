r"""Add the user's voice to organic (non-campaign) clips: either a clone of their voice (Chatterbox) or their own
recordings. Never for campaign posts: most briefs ban AI voices, and check_plan.py fails any that try.

usage:
  voice.py enroll <recording>            save a voice sample (15-30 s of natural talking) as likeness\voice_ref.wav
  voice.py make <campaign> [clip_id ...] speak each clip's lines, add them as captions in clips.json
  (then render.py <campaign> as usual)
  voice.py mix <campaign> [clip_id ...]  mix the voice into the rendered clips, game audio ducked underneath

In clips.json, give a clip either
  "voice": [{"at": 0.3, "text": "Okay, this map is huge"}, ...]        cloned voice; "at" = second in the clip
or
  "voice_takes": [{"at": 0.3, "file": "takes/map.wav", "text": "Okay, this map is huge"}]  your own recording
                                                                          ("text" is what you said: the caption)
Optional per clip: "voice_style": {"exaggeration": 0.5, "cfg_weight": 0.5}  (higher exaggeration = more energy)

Posts using the cloned voice must carry the platforms' AI label (Instagram "AI info", YouTube "Altered or
synthetic content: Yes"); set "ai_voice": true on them in plan\posts.json and check_plan.py will remind you.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TOOL = Path(__file__).parent
CLIPPER = TOOL.parent
sys.path.insert(0, str(TOOL))  # scripts here run with python -P
import campaign  # noqa: E402

REF = CLIPPER / "likeness" / "voice_ref.wav"
VOICE_PY = Path(os.environ.get("CLIPPER_VOICE_PY", CLIPPER / ".venv-voice" / "Scripts" / "python.exe"))
WORDS_PER_CAPTION = 4


def ff(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def length(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def segments(clip: dict) -> list[tuple[float, float]]:
    return [tuple(s) for s in clip["segments"]] if clip.get("segments") else [(clip["start"], clip["end"])]


def clip_len(clip: dict) -> float:
    return sum(e - s for s, e in segments(clip))


def to_source(clip: dict, t: float) -> float:
    """Second in the finished clip -> second in the source (render.py cues use source time)."""
    off = 0.0
    for s, e in segments(clip):
        if t <= off + (e - s) + 1e-6:
            return s + (t - off)
        off += e - s
    s, e = segments(clip)[-1]
    return e


# ---------- enroll ----------

def enroll(recording: Path) -> None:
    if not recording.exists():
        sys.exit(f"not found: {recording}")
    REF.parent.mkdir(exist_ok=True)
    # mono 24 kHz, rumble cut, silences trimmed, loudness evened out
    ff("-i", str(recording), "-ac", "1", "-ar", "24000", "-af",
       "highpass=f=80,silenceremove=start_periods=1:start_threshold=-45dB:stop_periods=-1:stop_duration=0.6:"
       "stop_threshold=-45dB,loudnorm=I=-18:TP=-2", str(REF))
    d = length(REF)
    print(f"saved {REF} ({d:.1f} s of speech)")
    if d < 8:
        print("too short: record at least 15 s of natural talking for a good clone")
    elif d > 40:
        print("long sample: 15-30 s is enough; the clone only uses the first part")


# ---------- make ----------

def chunk_cues(clip: dict, at: float, dur: float, text: str) -> list[list]:
    """Split a spoken line into short captions spread over its duration, in render.py's cue format."""
    words = text.split()
    groups = [words[i:i + WORDS_PER_CAPTION] for i in range(0, len(words), WORDS_PER_CAPTION)] or [[]]
    cues, t = [], at
    for g in groups:
        d = dur * len(g) / max(len(words), 1)
        a_, b_ = round(to_source(clip, t), 3), round(to_source(clip, min(t + d, at + dur)), 3)
        if b_ > a_:   # a line running past the clip's end yields nothing past the end
            cues.append([a_, b_, "", " ".join(g)])
        t += d
    return cues


def make(root: Path, only: set[str]) -> None:
    path = root / "clips.json"
    clips = json.loads(path.read_text(encoding="utf-8-sig"))
    vdir = root / "voice"
    vdir.mkdir(exist_ok=True)
    todo = [c for c in clips if (c.get("voice") or c.get("voice_takes")) and (not only or c["id"] in only)]
    if not todo:
        sys.exit('no clips with "voice" or "voice_takes" in clips.json')

    # 1. cloned lines, all in one model load
    tts = [(c, i, ln) for c in todo for i, ln in enumerate(c.get("voice", []))]
    if tts:
        if not REF.exists():
            sys.exit("no voice sample yet: run  voice.py enroll <recording>")
        if not VOICE_PY.exists():
            sys.exit(f"voice environment missing ({VOICE_PY}): run setup_voice.ps1 first")
        groups: dict[tuple, list] = {}
        for c, i, ln in tts:
            st = c.get("voice_style", {})
            key = (st.get("exaggeration", 0.5), st.get("cfg_weight", 0.5))
            groups.setdefault(key, []).append({"text": ln["text"], "out": str(vdir / f"{c['id']}_{i:02d}.wav")})
        for (ex, cfg), lines in groups.items():
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
                json.dump({"ref": str(REF), "exaggeration": ex, "cfg_weight": cfg, "lines": lines}, f)
            print(f"speaking {len(lines)} line(s) in your cloned voice...", flush=True)
            subprocess.run([str(VOICE_PY), str(TOOL / "voice_worker.py"), f.name], check=True)
            os.unlink(f.name)

    # 2. one voice track per clip + captions
    problems = 0
    for c in todo:
        dur = clip_len(c)
        placed = []
        for i, ln in enumerate(c.get("voice", [])):
            placed.append((ln["at"], vdir / f"{c['id']}_{i:02d}.wav", ln["text"]))
        for i, tk in enumerate(c.get("voice_takes", [])):
            src = root / tk["file"]
            if not src.exists():
                print(f"{c['id']}: missing recording {src}")
                problems += 1
                continue
            dst = vdir / f"{c['id']}_take{i:02d}.wav"
            ff("-i", str(src), "-ac", "1", "-ar", "48000", "-af", "highpass=f=80,loudnorm=I=-16:TP=-1.5", str(dst))
            placed.append((tk["at"], dst, tk.get("text", "")))
        placed.sort()
        cues, prev_end = [], -1.0
        for at, wav, text in placed:
            d = length(wav)
            if at < prev_end:
                print(f"{c['id']}: line at {at:.1f}s starts before the previous one ends ({prev_end:.1f}s)")
                problems += 1
            if at + d > dur + 0.05:
                print(f"{c['id']}: line at {at:.1f}s runs {at + d - dur:.1f}s past the clip's end ({dur:.1f}s): "
                      "shorten it or lengthen the clip")
                problems += 1
            prev_end = at + d
            if text:
                cues += chunk_cues(c, at, d, text)
        # voice track: every line at its time, silence elsewhere, exactly the clip's length
        ins, filt = [], []
        for k, (at, wav, _) in enumerate(placed):
            ins += ["-i", str(wav)]
            ms = int(at * 1000)
            filt.append(f"[{k}:a]aresample=48000,adelay={ms}|{ms}[l{k}]")
        mixin = "".join(f"[l{k}]" for k in range(len(placed)))
        filt.append(f"{mixin}amix=inputs={len(placed)}:normalize=0,apad,atrim=0:{dur:.3f}[out]")
        ff(*ins, "-filter_complex", ";".join(filt), "-map", "[out]", "-ac", "1", "-ar", "48000",
           str(vdir / f"{c['id']}.wav"))
        if c.get("captions") == "whisper":
            print(f"{c['id']}: switched captions from the game's speech to your voice lines")
            c.pop("captions")
        c["cues"] = cues
        print(f"{c['id']}: voice track ready ({len(placed)} line(s), {len(cues)} caption(s))")

    shutil.copyfile(path, root / "clips.json.bak")
    path.write_text(json.dumps(clips, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nclips.json updated (previous version in clips.json.bak). Next: render.py {root.name}, then "
          f"voice.py mix {root.name}")
    if problems:
        print(f"{problems} timing problem(s) above: fix the lines and run make again before rendering")


# ---------- mix ----------

def mix(root: Path, only: set[str]) -> None:
    clips = json.loads((root / "clips.json").read_text(encoding="utf-8-sig"))
    done = 0
    for c in clips:
        if only and c["id"] not in only:
            continue
        track = root / "voice" / f"{c['id']}.wav"
        video = root / "clips" / f"{c['id']}.mp4"
        if not track.exists():
            continue
        if not video.exists():
            print(f"{c['id']}: not rendered yet (run render.py first)")
            continue
        marker = root / "clips" / f"{c['id']}.voiced"
        if marker.exists() and marker.read_text(encoding="utf-8").strip() == str(video.stat().st_mtime_ns):
            print(f"{c['id']}: already has the voice mixed in (re-render it to mix again)")
            continue
        tmp = video.with_suffix(".tmp.mp4")
        # the game audio dips whenever you speak, then comes back; voice kept clear and level
        fc = ("[1:a]aresample=48000,volume=1.6,asplit=2[v][key];"
              "[0:a]aresample=48000[g];"
              "[g][key]sidechaincompress=threshold=0.02:ratio=10:attack=15:release=350[duck];"
              "[duck][v]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a]")
        ff("-i", str(video), "-i", str(track), "-filter_complex", fc, "-map", "0:v", "-map", "[a]",
           "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", str(tmp))
        tmp.replace(video)
        marker.write_text(str(video.stat().st_mtime_ns), encoding="utf-8")
        print(f"{c['id']}: voice mixed into {video}")
        done += 1
    if not done:
        print("nothing mixed")


def main() -> None:
    if len(sys.argv) >= 3 and sys.argv[1] == "enroll":
        return enroll(Path(sys.argv[2]))
    if len(sys.argv) < 3 or sys.argv[1] not in ("make", "mix"):
        sys.exit(__doc__)
    cmd = sys.argv.pop(1)
    root, ids = campaign.from_argv(f"voice.py {cmd} <campaign> [clip_id ...]")
    (make if cmd == "make" else mix)(root, set(ids))


if __name__ == "__main__":
    main()
