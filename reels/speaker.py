r"""Find who is talking in a shot and the best full-screen crop on them. Used by edit_viral.py layout "speaker".

speaker_crop(src, start, end, hint=None, lock=False) -> dict
    {"rect": [x, y, w, h] in source pixels, "aspect": "9:16" | "4:5", "face": [cx, cy] (0-1 inside the rect),
     "faces": n, "picked": "talking" | "hint" | "largest" | "none", "upscale": factor}

How it works, for multi-person frames (podcast grids, panels, stream layouts):
- samples the shot at 4 fps (one ffmpeg pass, small greyscale frames), finds faces in each sample;
- groups them into people by position; the talker is the one whose mouth area moves most (unless lock=True, or
  it's too close to call: then the person nearest `hint`, else the largest face);
- keeps the crop inside that person's own tile: never past the midpoint to the next face, and never into rows
  that don't change (a static lower-third bar or letterbox);
- with prev= (the last shot's result) it keeps that framing when the person isn't found again;
- returns the largest 9:16 window there, face at ~40% from the top. If that would need upscaling more than 1.7x
  (small tile, 1080p source), it returns a 4:5 window instead, which edit_viral places on a blurred background.
With no face found it returns a centred 9:16 crop around `hint` (or the frame centre).
CLI test:  speaker.py <video> <start> <end>
"""
from __future__ import annotations

import json
import subprocess
import sys

import numpy as np

DET_W = 960
FPS = 4
OUT_H = 1920
MAX_UPSCALE = 1.7
_cascade = None


def _probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True).stdout.strip()
    w, h = out.split(",")[:2]
    return int(w), int(h)


def _frames(path, start, end, w, h):
    n = max(2, min(40, int((end - start) * FPS)))
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{max(0.5, end - start):.3f}", "-i",
                          str(path), "-vf", f"fps={FPS},scale={w}:{h},format=gray", "-frames:v", str(n), "-f",
                          "rawvideo", "-"], capture_output=True).stdout
    k = len(raw) // (w * h)
    return np.frombuffer(raw[:k * w * h], np.uint8).reshape(k, h, w) if k else np.zeros((0, h, w), np.uint8)


def _faces(gray):
    global _cascade
    import cv2
    if _cascade is None:
        _cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    m = max(24, gray.shape[0] // 12)
    return [tuple(int(v) for v in f) for f in
            _cascade.detectMultiScale(cv2.equalizeHist(gray), 1.06, 4, minSize=(m, m))]


def speaker_crop(src, start, end, hint=None, lock=False, prev=None):
    sw, sh = _probe(src)
    dw = min(DET_W, sw) // 2 * 2
    dh = int(sh * dw / sw) // 2 * 2
    fr = _frames(src, start, end, dw, dh)
    people = []   # each: {"boxes": {frame_index: (x, y, w, h)}}
    for i, g in enumerate(fr):
        for (x, y, w, h) in _faces(g):
            cx = x + w / 2
            for p in people:
                px = np.median([b[0] + b[2] / 2 for b in p["boxes"].values()])
                if abs(px - cx) < 0.08 * dw and i not in p["boxes"]:
                    p["boxes"][i] = (x, y, w, h)
                    break
            else:
                people.append({"boxes": {i: (x, y, w, h)}})
    people = [p for p in people if len(p["boxes"]) >= max(2, 0.25 * len(fr))]
    for p in people:
        b = np.array(list(p["boxes"].values()), np.float32)
        p["x"], p["y"], p["w"], p["h"] = (float(v) for v in np.median(b, axis=0))
        p["cx"], p["cy"] = p["x"] + p["w"] / 2, p["y"] + p["h"] / 2
        # mouth movement: change between samples in the lower part of the face box, relative to the upper part
        # (so a nodding head or a moving camera doesn't count as talking)
        x0, x1 = int(p["x"] + 0.2 * p["w"]), int(p["x"] + 0.8 * p["w"])
        m0, m1 = int(p["y"] + 0.62 * p["h"]), int(min(dh, p["y"] + 1.0 * p["h"]))
        u0, u1 = int(p["y"] + 0.1 * p["h"]), int(p["y"] + 0.5 * p["h"])
        d = np.abs(np.diff(fr.astype(np.int16), axis=0))
        mouth = d[:, m0:m1, x0:x1].mean() if m1 > m0 and x1 > x0 else 0.0
        upper = d[:, u0:u1, x0:x1].mean() if u1 > u0 and x1 > x0 else 0.0
        p["talk"] = float(max(0.0, mouth - 0.6 * upper))
        p["mouth"] = float(mouth)
    hx, hy = (hint[0] * dw, hint[1] * dh) if hint else (dw / 2, dh * 0.4)
    picked = "none"
    who = None
    if people:
        nearest = min(people, key=lambda p: (p["cx"] - hx) ** 2 + (p["cy"] - hy) ** 2)
        ranked = sorted(people, key=lambda p: -p["talk"])
        if lock and hint:
            who, picked = nearest, "hint"
        elif len(ranked) == 1:
            who, picked = ranked[0], "talking" if ranked[0]["talk"] > 0 else "largest"
        elif ranked[0]["talk"] > 0.35 and ranked[0]["talk"] > 1.3 * ranked[1]["talk"]:
            who, picked = ranked[0], "talking"
        elif hint:
            who, picked = nearest, "hint"
        elif max(p["mouth"] for p in people) > 1.5 * sorted(p["mouth"] for p in people)[-2] + 0.3:
            who, picked = max(people, key=lambda p: p["mouth"]), "talking"   # whole head moving while talking
        else:
            who, picked = max(people, key=lambda p: p["w"] * p["h"]), "largest"

    # the person we were on isn't found in this shot (turned away, hand over face): keep the previous framing
    # rather than jumping to whoever else is on screen
    if prev and hint and (who is None or (picked == "hint" and
                                          ((who["cx"] - hx) ** 2 + (who["cy"] - hy) ** 2) ** 0.5 > 0.1 * dw)):
        kept = dict(prev)
        kept["picked"] = "kept"
        return kept

    # rows that never change at the top/bottom = bars and lower-thirds: keep the crop out of them
    yt, yb = 0, dh
    if len(fr) >= 3:
        rows = fr[:, :, ::4].astype(np.float32).std(axis=0).mean(axis=1)
        live = rows > max(1.2, 0.25 * np.median(rows))
        if who is not None:
            fy = int(who["cy"])
            a = fy
            while a > 0 and (live[a - 1] or live[max(0, a - 6):a].any()):
                a -= 1
            b = fy
            while b < dh - 1 and (live[b + 1] or live[b + 1:b + 7].any()):
                b += 1
            if b - a > 0.3 * dh:
                yt, yb = a, b + 1
    xl, xr = 0, dw
    if who is not None:
        for p in people:
            if p is who:
                continue
            mid = (p["cx"] + who["cx"]) / 2
            if p["cx"] < who["cx"]:
                xl = max(xl, mid)
            else:
                xr = min(xr, mid)
        fcx, fcy, fh = who["cx"], who["cy"], who["h"]
    else:
        fcx, fcy, fh = hx, hy, dh * 0.25

    def window(aspect):
        h = min(yb - yt, (xr - xl) / aspect)
        h = min(h, max(fh * 4.2, 0.55 * (yb - yt)))       # don't make the face tiny when the tile is huge
        w = h * aspect
        x = min(max(fcx - w / 2, xl), xr - w)
        y = min(max(fcy - 0.40 * h, yt), yb - h)
        return x, y, w, h

    aspect = "9:16"
    x, y, w, h = window(9 / 16)
    s = sh / dh
    up = OUT_H / max(1.0, h * s)
    if up > MAX_UPSCALE:
        aspect = "4:5"
        x, y, w, h = window(4 / 5)
        up = 1350 / max(1.0, h * s)
    rect = [int(x * s) // 2 * 2, int(y * s) // 2 * 2, int(w * s) // 2 * 2, int(h * s) // 2 * 2]
    rect[2] = min(rect[2], sw - rect[0]) // 2 * 2
    rect[3] = min(rect[3], sh - rect[1]) // 2 * 2
    return {"rect": rect, "aspect": aspect, "face": [round(float((fcx - x) / w), 3), round(float((fcy - y) / h), 3)],
            "faces": len(people), "picked": picked, "face_h": round(float(fh / max(1.0, h)), 3), "upscale": round(float(up), 2),
            "talk": [round(p["talk"], 2) for p in sorted(people, key=lambda p: p["cx"])]}


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    print(json.dumps(speaker_crop(sys.argv[1], float(sys.argv[2]), float(sys.argv[3])), indent=1))
