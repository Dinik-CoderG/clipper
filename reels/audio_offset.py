r"""How far (seconds) a window's audio is shifted from the true audio of the stream.

usage: audio_offset.py <window.mp4> <full_audio> <window start s> [--max 8]
Cross-correlates the window's audio envelope with the full stream audio around <window start>. Positive result =
the window's audio is from `result` seconds LATER in the stream than it should be (it plays ahead of the picture
if the picture is right). 0 = in place.
"""
import subprocess
import sys

import numpy as np

SR = 1000   # envelope rate (1 ms)


def env(path, ss=None, t=None):
    cmd = ["ffmpeg", "-v", "error"]
    if ss is not None:
        cmd += ["-ss", str(ss)]
    cmd += ["-i", path]
    if t is not None:
        cmd += ["-t", str(t)]
    cmd += ["-vn", "-ac", "1", "-ar", "8000", "-f", "s16le", "-"]
    x = np.frombuffer(subprocess.run(cmd, capture_output=True, check=True).stdout, np.int16).astype(np.float32)
    x = np.abs(x)[: len(x) // 8 * 8].reshape(-1, 8).mean(1)      # 1 kHz envelope
    return (x - x.mean()) / (x.std() + 1e-6)


def offset(window, full, start, max_s=8.0):
    w = env(window, t=60)
    r = env(full, ss=max(0.0, start - max_s), t=60 + 2 * max_s)
    best = None
    for k in range(0, len(r) - len(w)):
        c = float(np.dot(r[k:k + len(w)], w)) / len(w)
        if best is None or c > best[1]:
            best = (k / SR - min(max_s, start), c)
    return best


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) < 3:
        sys.exit(__doc__)
    m = float(a[a.index("--max") + 1]) if "--max" in a else 8.0
    s, c = offset(a[0], a[1], float(a[2]), m)
    print(f"{s:+.2f} s (match {c:.2f})")
