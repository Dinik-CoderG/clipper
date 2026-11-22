"""Dump the in-game subtitle strip (1 frame/sec) for a time range as tall timestamped images.
usage: subs.py <campaign> <source> <start> <end> [fps]"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))  # scripts here run with python -P
import campaign  # noqa: E402

FONT = "C\\:/Windows/Fonts/arialbd.ttf"

ROOT, args = campaign.from_argv("subs.py <campaign> <source> <start> <end> [fps]")
name, start, end = args[0], float(args[1]), float(args[2])
fps = args[3] if len(args) > 3 else "1"
out = ROOT / "analysis" / name / f"subs_{int(start)}_{int(end)}_%02d.jpg"
out.parent.mkdir(parents=True, exist_ok=True)
vf = (
    f"fps={fps},crop=1500:200:1170:1660,"
    f"drawtext=fontfile='{FONT}':text='%{{pts\\:hms\\:{start}}}':x=4:y=4:fontsize=34:fontcolor=yellow:box=1:boxcolor=black,"
    "tile=1x12"
)
subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(start), "-to", str(end),
                "-i", str(ROOT / "source" / f"{name}.mp4"), "-vf", vf, "-fps_mode", "vfr", "-q:v", "3", str(out)], check=True)
print("\n".join(str(p) for p in sorted(out.parent.glob(out.name.replace("%02d", "*")))))
