r"""Estimate lip-sync offset: how far the voice is ahead of / behind the streamer's mouth in a video.

usage: lipsync_check.py <video> [--cam x y w h] [--from s] [--to s]
       (cam = facecam box as fractions of the frame; default the whole frame)
Correlates movement in the lower half of the face box (the mouth area) with the speech loudness, frame by frame, at
delays of -1.5..+1.5 s. Prints the best delay: positive = the audio comes LATER than the mouth moves (sound lags);
negative = the sound is early. |delay| <= 0.08 s is in sync; > 0.15 s is visible to viewers.
"""
import subprocess
import sys

import numpy as np

FPS = 30


def motion(path, cam, t0, t1):
    x, y, w, h = cam
    crop = f"crop=iw*{w}:ih*{h / 2}:iw*{x}:ih*{y + h / 2}"       # lower half of the face box
    cmd = ["ffmpeg", "-v", "error", "-ss", str(t0), "-i", path, "-t", str(t1 - t0),
           "-vf", f"fps={FPS},{crop},scale=96:48,format=gray", "-f", "rawvideo", "-"]
    f = np.frombuffer(subprocess.run(cmd, capture_output=True, check=True).stdout, np.uint8)
    f = f.reshape(-1, 48, 96).astype(np.float32)
    return np.concatenate([[0], np.abs(np.diff(f, axis=0)).mean(axis=(1, 2))])


def loudness(path, t0, t1):
    cmd = ["ffmpeg", "-v", "error", "-ss", str(t0), "-i", path, "-t", str(t1 - t0), "-vn", "-ac", "1",
           "-ar", "16000", "-af", "highpass=f=200,lowpass=f=3500", "-f", "s16le", "-"]
    a = np.frombuffer(subprocess.run(cmd, capture_output=True, check=True).stdout, np.int16).astype(np.float32)
    per = 16000 // FPS
    a = a[: len(a) // per * per].reshape(-1, per)
    return np.sqrt((a ** 2).mean(1))


def norm(v):
    v = np.diff(v, prepend=v[0])                 # changes, not levels: mouth opening vs syllable onsets
    return (v - v.mean()) / (v.std() + 1e-6)


def check(path, cam=(0, 0, 1, 1), t0=0.0, t1=None):
    if t1 is None:
        t1 = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                   path], capture_output=True, text=True).stdout)
    m, a = norm(motion(path, cam, t0, t1)), norm(loudness(path, t0, t1))
    n = min(len(m), len(a))
    m, a = m[:n], a[:n]
    best = (0.0, -9.0)
    scores = {}
    for k in range(-45, 46):
        x, y = (m[: n - k], a[k:]) if k >= 0 else (m[-k:], a[: n + k])
        c = float(np.dot(x, y) / len(x))
        scores[k] = c
        if c > best[1]:
            best = (k / FPS, c)
    base = float(np.median(list(scores.values())))
    return best[0], best[1], best[1] - base


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    cam = tuple(float(v) for v in a[a.index("--cam") + 1:a.index("--cam") + 5]) if "--cam" in a else (0, 0, 1, 1)
    t0 = float(a[a.index("--from") + 1]) if "--from" in a else 0.0
    t1 = float(a[a.index("--to") + 1]) if "--to" in a else None
    d, c, lift = check(a[0], cam, t0, t1)
    verdict = "in sync" if abs(d) <= 0.08 else ("visible offset" if abs(d) > 0.15 else "borderline")
    print(f"audio {'lags' if d > 0 else 'leads'} by {abs(d):.2f} s · {verdict} (peak {c:.2f}, above median {lift:.2f})")
