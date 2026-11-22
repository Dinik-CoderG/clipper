"""Reel covers in the room-frame look: the clip's frame + hook at its most dramatic source second.
Each clip in clips.json may set "cover": <source second>; otherwise the middle of the clip is used.

usage: make_covers.py <campaign>"""
import json
import sys
from pathlib import Path

TOOL = Path(__file__).parent
sys.path.insert(0, str(TOOL))            # scripts here run with python -P
sys.path.insert(0, str(TOOL / "frames"))
import campaign  # noqa: E402
import real_frame  # noqa: E402
from render import FRAMES  # noqa: E402  (same frame rotation as the clips)

ROOT, _ = campaign.from_argv("make_covers.py <campaign>")
clips = json.loads((ROOT / "clips.json").read_text(encoding="utf-8-sig"))  # -sig: Windows editors add a BOM
out = ROOT / "covers"
out.mkdir(exist_ok=True)
for i, c in enumerate(clips):
    frame = c.get("frame", FRAMES[i % len(FRAMES)])
    s0, e0 = c["segments"][0] if c.get("segments") else (c["start"], c["end"])
    second = c.get("cover", (s0 + e0) / 2)
    dst = out / f"{c['id']}.jpg"
    real_frame.compose(frame, str(ROOT / "source" / f"{c['source']}.mp4"), second, None, c["hook"], dst)
    print(dst)
