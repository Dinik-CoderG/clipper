r"""Timestamped 1-fps contact sheets of every source window in a campaign, two windows stacked per image, for picking
moments by eye (CLAUDE.md: look at the sheets, not scores alone).

usage: window_sheets.py <campaign folder> [--fps 1] [--width 150]
Writes <campaign>\analysis\sheets\<a>+<b>.jpg (12 frames per row, the window name and seconds on every frame).
"""
import subprocess
import sys
from pathlib import Path

FONT = "C\\\\:/Windows/Fonts/arial.ttf"


def sheet(src: Path, out: Path, fps: float, width: int):
    dt = (f"drawtext=fontfile={FONT}:text='{src.stem} %{{pts\\:flt}}':fontsize=14:fontcolor=yellow:box=1:"
          f"boxcolor=black@0.7:x=2:y=2")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vf",
                    f"fps={fps},scale={width}:-2,{dt},tile=12x9", "-frames:v", "1", str(out)], check=True)


def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    camp = Path(a[0])
    fps = float(a[a.index("--fps") + 1]) if "--fps" in a else 1.0
    width = int(a[a.index("--width") + 1]) if "--width" in a else 150
    out = camp / "analysis" / "sheets"
    out.mkdir(parents=True, exist_ok=True)
    srcs = sorted((camp / "source").glob("m*.mp4"))
    singles = []
    for s in srcs:
        p = out / f"_{s.stem}.jpg"
        if not p.exists():
            sheet(s, p, fps, width)
        singles.append(p)
    for i in range(0, len(singles), 2):
        pair = singles[i:i + 2]
        name = out / ("+".join(p.stem.lstrip("_") for p in pair) + ".jpg")
        if len(pair) == 1:
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(pair[0]), str(name)], check=True)
        else:
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(pair[0]), "-i", str(pair[1]), "-filter_complex",
                            "[0][1]scale2ref=iw:ih*0+ih[a][b];[a][b]vstack", str(name)], check=False)
            if not name.exists():
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(pair[0]), "-i", str(pair[1]),
                                "-filter_complex", "vstack", str(name)], check=True)
        print(name)


if __name__ == "__main__":
    main()
