r"""How far (seconds) the picture of one video is shifted against another copy of the same footage.

usage: av_offset.py <reference.mp4> <other.mp4> [--max 6]
Both are decoded at 10 fps, 64x36 grey; the shift with the smallest mean frame difference wins.
Positive result = <other> shows a moment `result` seconds LATER than the reference at the same timestamp.
Used to prove a window's picture is out of step with its audio (compare it with a frame-accurate re-cut).
"""
import subprocess
import sys

import numpy as np

FPS, W, H = 10, 64, 36


def frames(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vf", f"fps={FPS},scale={W}:{H},format=gray",
                          "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, H, W).astype(np.float32)


def offset(ref, other, max_s=6.0):
    a, b = frames(ref), frames(other)
    best = None
    for k in range(-int(max_s * FPS), int(max_s * FPS) + 1):
        x, y = (a[:len(a) - k], b[k:]) if k >= 0 else (a[-k:], b[:len(b) + k])
        n = min(len(x), len(y))
        if n < FPS * 20:
            continue
        d = float(np.mean(np.abs(x[:n] - y[:n])))
        if best is None or d < best[1]:
            best = (k / FPS, d)
    return best


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) < 2:
        sys.exit(__doc__)
    m = float(a[a.index("--max") + 1]) if "--max" in a else 6.0
    s, d = offset(a[0], a[1], m)
    print(f"{s:+.1f} s (frame difference {d:.1f})")
