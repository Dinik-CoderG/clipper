"""Transcribe each source video of a campaign and build timestamped contact sheets for picking moments.

usage: analyze.py <campaign> [source_name ...]"""
from __future__ import annotations

import json
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
from faster_whisper import WhisperModel

sys.path.insert(0, str(Path(__file__).parent))  # scripts here run with python -P
import campaign  # noqa: E402

ROOT, NAMES = campaign.from_argv("analyze.py <campaign> [source_name ...]")
SRC = ROOT / "source"
OUT = ROOT / "analysis"
FONT = "C\\:/Windows/Fonts/arialbd.ttf"


def ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def contact_sheets(src: Path, out_dir: Path) -> None:
    # one frame every 3s, 4x4 per sheet => 48s of footage per image
    vf = (
        "fps=1/3,scale=480:-1,"
        f"drawtext=fontfile='{FONT}':text='%{{pts\\:hms}}':x=8:y=8:fontsize=28:fontcolor=yellow:box=1:boxcolor=black@0.6,"
        "tile=4x4"
    )
    ffmpeg("-i", str(src), "-vf", vf, "-fps_mode", "vfr", str(out_dir / "sheet_%02d.jpg"))


def transcribe(model: WhisperModel, src: Path, out_dir: Path) -> None:
    wav = out_dir / "audio.wav"
    ffmpeg("-i", str(src), "-vn", "-ac", "1", "-ar", "16000", str(wav))
    with wave.open(str(wav), "rb") as f:
        audio = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    segs, _ = model.transcribe(audio, language="en", word_timestamps=True, vad_filter=True)
    rows = []
    for s in segs:
        rows.append({
            "start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip(),
            "words": [[round(w.start, 2), round(w.end, 2), w.word.strip()] for w in (s.words or []) if w.word.strip()],
        })
    (out_dir / "transcript.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(out_dir / "transcript.txt", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(f"[{r['start']:7.2f}-{r['end']:7.2f}] {r['text']}\n")
    wav.unlink(missing_ok=True)


def main() -> None:
    names = NAMES or [p.stem for p in sorted(SRC.glob("*.mp4"))]
    model = WhisperModel("small.en", device="cpu", compute_type="int8")
    for name in names:
        src = SRC / f"{name}.mp4"
        out_dir = OUT / name
        out_dir.mkdir(parents=True, exist_ok=True)
        print(f"== {name}", flush=True)
        contact_sheets(src, out_dir)
        transcribe(model, src, out_dir)
        print(f"   done -> {out_dir}", flush=True)


if __name__ == "__main__":
    main()
