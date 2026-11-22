"""Zoomed, gridded tiles around estimated screen points so exact corner pixels can be read off.
usage: probe.py <photo.jpg> x,y [x,y ...]   (full-res coords; grid every 10 px, labels show tile origin)"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
FONT = "C\\:/Windows/Fonts/arialbd.ttf"
photo = HERE / sys.argv[1]
pts = [tuple(map(int, p.split(","))) for p in sys.argv[2:]]
tiles = []
for i, (x, y) in enumerate(pts):
    x0, y0 = x - 80, y - 80
    out = HERE / f"tile_{i}.png"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(photo), "-vf",
                    f"crop=160:160:{x0}:{y0},scale=480:480:flags=neighbor,drawgrid=w=30:h=30:t=1:c=yellow@0.7,"
                    f"drawbox=x=237:y=237:w=6:h=6:c=red:t=fill,"
                    f"drawtext=fontfile='{FONT}':text='{x0},{y0}':x=4:y=4:fontsize=22:fontcolor=white:box=1:boxcolor=black",
                    str(out)], check=True)
    tiles.append(out)
args = sum((["-i", str(t)] for t in tiles), [])
lay = "|".join(f"{(i % 4) * 480}_{(i // 4) * 480}" for i in range(len(tiles)))
subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args, "-filter_complex",
                f"xstack=inputs={len(tiles)}:layout={lay}:fill=black",
                str(HERE.parent / "debug" / f"probe_{photo.stem}.png")], check=True)
print("ok")
