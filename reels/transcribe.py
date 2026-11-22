r"""Word-level transcript for talking footage, on the NVIDIA GPU when it works (CPU otherwise).

usage: transcribe.py <campaign> [source] [--windows 185-262,325-392] [--model small.en] [--cpu]
Writes  <campaign>\analysis\<source>\transcript.json   [{"start","end","text","words":[[t0,t1,"word"],...]}]
        <campaign>\analysis\<source>\transcript.txt    one line per sentence with its times (read this to pick clips)
--windows transcribes only those parts (seconds) of a long episode: much faster when you already know roughly
where the good parts are (from the episode's own subtitles, chapters, or a quick first pass with --model tiny.en).
Whisper mishears names: check brand, product and people names against the brief before using them in captions,
and list corrections as "fixes" in plan\clips_spec.json.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


def _add_cuda_dll_dirs() -> None:
    """Let Windows find cuBLAS/cuDNN from the nvidia-*-cu12 pip wheels (not on the DLL search path by default)."""
    if os.name != "nt":
        return
    import site
    for base in site.getsitepackages():
        for bin_dir in Path(base).glob("nvidia/*/bin"):
            os.add_dll_directory(str(bin_dir))
            os.environ["PATH"] = f"{bin_dir}{os.pathsep}{os.environ['PATH']}"


def load_model(size: str, cpu: bool):
    from faster_whisper import WhisperModel
    if not cpu:
        _add_cuda_dll_dirs()
        for compute in ("float16", "int8_float16", "int8"):     # some GTX 16xx cards misbehave in pure fp16
            try:
                model = WhisperModel(size, device="cuda", compute_type=compute)
                list(model.transcribe(np.zeros(16000, dtype=np.float32))[0])   # missing DLLs only fail at inference
                return model, f"GPU (cuda/{compute})"
            except Exception:  # noqa: BLE001
                continue
    return WhisperModel(size, device="cpu", compute_type="int8"), "CPU (int8)"


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)

    def opt(name, default=None):
        return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default
    root = Path(args[0])
    if not root.exists():
        root = HERE.parent / "campaigns" / args[0]
    sources = [args[1]] if len(args) > 1 else [p.stem for p in sorted((root / "source").glob("*.mp4"))]
    model, where = load_model(opt("--model", "small.en"), "--cpu" in sys.argv)
    print(f"transcribing on the {where}", flush=True)
    for source in sources:
        out = root / "analysis" / source
        out.mkdir(parents=True, exist_ok=True)
        wav = out / "audio.wav"
        if not wav.exists():
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(root / "source" / f"{source}.mp4"), "-vn", "-ac", "1",
                            "-ar", "16000", str(wav)], check=True)
        with wave.open(str(wav), "rb") as f:
            sr = f.getframerate()
            audio = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
        total = len(audio) / sr
        wins = [(0.0, total)]
        if opt("--windows"):
            wins = [tuple(float(x) for x in w.split("-")) for w in opt("--windows").split(",")]
        rows = []
        for a, b in wins:
            segs, _ = model.transcribe(audio[int(a * sr):int(b * sr)], word_timestamps=True,
                                       vad_filter=len(wins) == 1)
            for s in segs:
                rows.append({"start": round(s.start + a, 2), "end": round(s.end + a, 2), "text": s.text.strip(),
                             "words": [[round(w.start + a, 2), round(w.end + a, 2), w.word.strip()]
                                       for w in (s.words or []) if w.word.strip()]})
                print(f"\r   {source}: {rows[-1]['end']:.0f}s / {total:.0f}s", end="", flush=True)
        print()
        (out / "transcript.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        with open(out / "transcript.txt", "w", encoding="utf-8") as f:
            for r in rows:
                f.write(f"[{r['start']:7.2f}-{r['end']:7.2f}] {r['text']}\n")
        print(f"   wrote {out / 'transcript.json'} ({len(rows)} sentences)")


if __name__ == "__main__":
    main()
