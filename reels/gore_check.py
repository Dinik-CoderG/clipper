"""Flag seconds of a source video with visible blood (large patches of saturated red) so clips can avoid them.
Briefs often ban violent content; COD hit effects show up as red mist/splatter.

usage: gore_check.py <campaign> <source> [threshold=0.004]
prints flagged times (4 samples/sec) and writes analysis/<source>/gore.json"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))  # scripts here run with python -P
import campaign  # noqa: E402

ROOT, args = campaign.from_argv("gore_check.py <campaign> <source> [threshold]")
name = args[0]
thr = float(args[1]) if len(args) > 1 else 0.004
W, H, FPS = 320, 180, 4
proc = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(ROOT / "source" / f"{name}.mp4"),
                         "-vf", f"fps={FPS},scale={W}:{H}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                        stdout=subprocess.PIPE)
flags, i = [], 0
while True:
    buf = proc.stdout.read(W * H * 3)
    if len(buf) < W * H * 3:
        break
    a = np.frombuffer(buf, np.uint8).reshape(H, W, 3).astype(np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    blood = (r > 120) & (r - g > 80) & (r - b > 50)          # deep saturated red (not orange fire, not pink neon)
    frac = float(blood.mean())
    if frac > thr:
        flags.append([round(i / FPS, 2), round(frac, 4)])
    i += 1
out = ROOT / "analysis" / name / "gore.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(flags))
print(" ".join(f"{t}s({f:.3f})" for t, f in flags))
