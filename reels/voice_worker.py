"""Speak lines in the user's cloned voice with Chatterbox. Runs inside .venv-voice (see setup_voice.ps1),
called by voice.py; not meant to be run by hand.

usage: voice_worker.py <job.json>
job.json: {"ref": "likeness/voice_ref.wav", "exaggeration": 0.5, "cfg_weight": 0.5,
           "lines": [{"text": "...", "out": "path.wav"}, ...]}
Chatterbox (MIT, Resemble AI) adds its inaudible PerTh watermark to everything it generates.
"""
import json
import sys

import torch
import torchaudio as ta
from chatterbox.tts import ChatterboxTTS


def main() -> None:
    job = json.load(open(sys.argv[1], encoding="utf-8"))
    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cpu":
        print("warning: no CUDA GPU visible to .venv-voice; this will be slow", flush=True)
    model = ChatterboxTTS.from_pretrained(device=device)
    for line in job["lines"]:
        wav = model.generate(line["text"], audio_prompt_path=job["ref"],
                             exaggeration=job.get("exaggeration", 0.5), cfg_weight=job.get("cfg_weight", 0.5))
        ta.save(line["out"], wav, model.sr)
        print("spoke", line["out"], flush=True)


if __name__ == "__main__":
    main()
