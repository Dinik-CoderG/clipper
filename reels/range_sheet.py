"""One contact sheet of several chosen ranges, for the by-eye violence/nudity check before cutting.

usage: range_sheet.py <campaign folder> <out.jpg> <window:start-end> [<window:start-end> ...] [--fps 1] [--width 128]
Each range becomes one labelled row (or more) of frames; rows are stacked into a single image.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

FONT = "C\\\\:/Windows/Fonts/arial.ttf"


def main():
    a = sys.argv[1:]
    if len(a) < 3:
        sys.exit(__doc__)
    camp, out = Path(a[0]), Path(a[1])
    fps = float(a[a.index("--fps") + 1]) if "--fps" in a else 1.0
    width = int(a[a.index("--width") + 1]) if "--width" in a else 128
    ranges = [x for x in a[2:] if ":" in x and not x.startswith("--")]
    tmp = Path(tempfile.mkdtemp())
    rows = []
    for i, r in enumerate(ranges):
        win, span = r.split(":")
        s, e = (float(v) for v in span.split("-"))
        n = max(1, int((e - s) * fps))
        cols = 16
        lines = (n + cols - 1) // cols
        p = tmp / f"r{i}.png"
        dt = (f"drawtext=fontfile={FONT}:text='{win} %{{eif\\:t+{s}\\:d}}':fontsize=13:fontcolor=yellow:box=1:"
              f"boxcolor=black@0.7:x=2:y=2")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(s), "-t", str(e - s), "-i",
                        str(camp / "source" / f"{win}.mp4"), "-vf",
                        f"fps={fps},scale={width}:-2,{dt},tile={cols}x{lines}", "-frames:v", "1", str(p)], check=True)
        rows.append(p)
    args = sum([["-i", str(p)] for p in rows], [])
    if len(rows) == 1:
        subprocess.run(["ffmpeg", "-v", "error", "-y", *args, str(out)], check=True)
    else:
        pads = "".join(f"[{i}]pad={16 * width}:ih[p{i}];" for i in range(len(rows)))
        subprocess.run(["ffmpeg", "-v", "error", "-y", *args, "-filter_complex",
                        pads + "".join(f"[p{i}]" for i in range(len(rows))) + f"vstack=inputs={len(rows)}",
                        str(out)], check=True)
    print(out)


if __name__ == "__main__":
    main()
