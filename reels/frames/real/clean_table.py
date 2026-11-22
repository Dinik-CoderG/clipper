"""Remove the snacks from the neon-room table, keeping the Kirby lamp (with plate) and the mini arcade.

- shelf cubbies: hidden plush is filled from pixels of the same cubby only (Telea), so colours can't mix
- table surface: rebuilt from a smooth lighting model fitted to bare table pixels + the lamp's warm glow + grain
Writes neon_room_clean.jpg plus previews in ../debug.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).parent
SRC, OUT = HERE / "neon_room.jpg", HERE / "neon_room_clean.jpg"
ANALYSIS = HERE.parent / "debug"
ANALYSIS.mkdir(exist_ok=True)
# polygons were read off a 0.75x view of the table crop that starts at photo (860, 1700)
OX, OY, K = 860, 1700, 0.75


def P(*pts):
    return [(OX + x / K, OY + y / K) for x, y in pts]


REMOVE = [
    P((105, 210), (140, 188), (350, 160), (392, 172), (480, 245), (528, 288), (512, 312), (255, 352), (205, 378),
      (165, 342), (150, 252)),                                                    # chips bag
    P((262, 350), (490, 350), (490, 456), (262, 456)),                            # Kirby card
    P((680, 132), (760, 106), (1070, 120), (1125, 155), (1125, 205), (898, 208), (898, 306), (752, 306),
      (752, 215)),                                                                # marshmallow bag
    P((868, 196), (900, 172), (1195, 172), (1218, 210), (1210, 335), (1145, 408), (1062, 432), (975, 424),
      (912, 378), (876, 292)),                                                    # bowl
    P((870, 210), (1290, 210), (1290, 258), (870, 258)),                          # chopsticks
    P((488, 425), (1440, 425), (1440, 525), (488, 525)),                          # candy stick (runs past the crop)
]
CUBBIES = [P((100, 40), (340, 194)), P((346, 40), (676, 194)), P((682, 40), (1006, 194)), P((1012, 40), (1338, 194))]
LAMP_BOX = P((530, 140), (812, 385))
LAMP_CENTER = P((655, 330))[0]              # where the lamp meets its plate: centre of the glow on the table
ARCADE = P((0, 20), (100, 260))             # mini arcade on the left edge of the table
TABLE_Y = int(OY + 194 / K)                 # first row of plain table below the shelf unit


def removal_mask(shape) -> np.ndarray:
    m = Image.new("L", (shape[1], shape[0]), 0)
    d = ImageDraw.Draw(m)
    for poly in REMOVE:
        d.polygon(poly, fill=255)
    m = cv2.dilate(np.asarray(m), np.ones((13, 13), np.uint8)) > 0
    return m & ~lamp_keep(shape)


LAMP_BODY = ((1735, 2045), (152, 150))   # head+body ellipse (photo px, measured on a 1:1 crop)
LAMP_PLATE = ((1735, 2177), (202, 70))   # plate ellipse


def lamp_keep(shape) -> np.ndarray:
    """Kirby lamp + plate: the plate ellipse, plus lamp-coloured pixels (white/yellow/orange, never blue) inside the
    head/body ellipse, so the edge of the removed bag right next to the lamp still goes."""
    a = np.asarray(Image.open(SRC).convert("RGB")).astype(np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    lampish = ((b - r) < 25) & ((b - g) < 25) & ((r + g + b) > 360)   # white / yellow / orange, not the blue bag
    body = np.zeros(shape, np.uint8)
    (cx, cy), (ax, ay) = LAMP_BODY
    cv2.ellipse(body, (cx, cy), (ax, ay), 0, 0, 360, 1, -1)
    plate = np.zeros(shape, np.uint8)
    (cx, cy), (ax, ay) = LAMP_PLATE
    cv2.ellipse(plate, (cx, cy), (ax, ay), 0, 0, 360, 1, -1)
    k = ((body > 0) & lampish).astype(np.uint8)
    k = cv2.morphologyEx(k, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))   # eyes/mouth holes
    k = cv2.morphologyEx(k, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))      # stray specks
    return ((k > 0) | (plate > 0))


def fill_cubbies(img: np.ndarray, m: np.ndarray, keep: np.ndarray) -> np.ndarray:
    out = img.copy()
    for (x0, y0), (x1, y1) in CUBBIES:
        x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)
        sub_m = (m[y0:y1, x0:x1] * 255).astype(np.uint8)
        if not sub_m.any():
            continue
        sub = cv2.cvtColor(out[y0:y1, x0:x1], cv2.COLOR_RGB2BGR)
        # the lamp head pokes into the cubby: treat it as unknown too so its yellow can't leak into the plush
        lamp = cv2.dilate(keep[y0:y1, x0:x1].astype(np.uint8), np.ones((15, 15), np.uint8)) * 255
        f = cv2.inpaint(sub, np.maximum(sub_m, lamp), 15, cv2.INPAINT_TELEA)
        f = cv2.GaussianBlur(f, (0, 0), 3)                     # plush fabric is soft and out of focus
        f = cv2.cvtColor(f, cv2.COLOR_BGR2RGB)
        out[y0:y1, x0:x1] = np.where(sub_m[..., None] > 0, f, out[y0:y1, x0:x1])
    return out


def plate_shadow(shape) -> np.ndarray:
    shadow = np.zeros(shape, np.uint8)
    (px0, py0), (px1, py1) = P((498, 296), (808, 392))
    cv2.ellipse(shadow, (int((px0 + px1) / 2), int((py0 + py1) / 2)),
                (int((px1 - px0) / 2), int((py1 - py0) / 2)), 0, 0, 360, 1, -1)
    return shadow > 0


def rebuild_table(img: np.ndarray, m: np.ndarray, keep: np.ndarray, with_lamp: bool = True):
    h, w = m.shape
    f = img.astype(np.float32)
    yy, xx = np.mgrid[0:h, 0:w]
    region = yy >= TABLE_Y
    (ax0, ay0), (ax1, ay1) = ARCADE
    arcade = (xx >= ax0) & (xx < ax1) & (yy >= ay0) & (yy < ay1)
    near_lamp = cv2.dilate(keep.astype(np.uint8), np.ones((241, 241), np.uint8)) > 0
    near_obj = cv2.dilate(m.astype(np.uint8), np.ones((41, 41), np.uint8)) > 0
    bare = region & ~near_obj & ~near_lamp & ~arcade & (xx > 860) & (xx < 2700)

    cx, cy = LAMP_CENTER

    def basis(x, y):
        u, v = (x - 1780) / 900.0, (y - 2180) / 250.0
        return np.stack([np.ones_like(u), u, v, u * u, u * v, v * v], -1)

    ys, xs = np.nonzero(bare)
    pick = np.random.default_rng(1).choice(len(xs), min(80000, len(xs)), replace=False)
    ys, xs = ys[pick], xs[pick]
    coef = np.linalg.lstsq(basis(xs, ys), f[ys, xs], rcond=None)[0]

    # lamp glow: elliptical falloff around the lamp base; size and per-channel strength fitted on the real
    # table pixels around the plate (grid search over sizes, least squares for strength)
    ring = region & near_lamp & ~near_obj & ~(cv2.dilate(keep.astype(np.uint8), np.ones((15, 15), np.uint8)) > 0)
    ry, rx = np.nonzero(ring)
    resid = f[ry, rx] - basis(rx, ry) @ coef
    best = None
    for sx in (160, 220, 300, 400, 520):
        for sy in (60, 90, 130, 180):
            g = np.exp(-(((rx - cx) / sx) ** 2 + ((ry - cy) / sy) ** 2))[:, None]
            amp = np.clip((g * resid).sum(0) / (g * g).sum(), 0, None)
            err = float(((resid - g * amp) ** 2).sum())
            if best is None or err < best[0]:
                best = (err, sx, sy, amp)
    _, sx, sy, amp = best

    def glow(x, y):
        return np.exp(-(((x - cx) / sx) ** 2 + ((y - cy) / sy) ** 2))

    # the whole visible table is rebuilt, so real and synthetic table never meet; only the lamp (+ plate and its
    # shadow) and the arcade stay real. Without the lamp, its spot becomes table too and there is no glow.
    # arcade: keep its real pixels (bright screen / red body) plus a little table right under it, not its whole box
    a16 = img.astype(np.int16)
    arcade_px = arcade & ((a16[..., 0] - a16[..., 2] > 40) | (a16.sum(-1) > 600) | (a16.sum(-1) < 200))
    arcade_px = cv2.dilate(cv2.morphologyEx(arcade_px.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((21, 21), np.uint8)),
                           np.ones((9, 9), np.uint8)) > 0
    real = (keep | plate_shadow(keep.shape) | arcade_px) if with_lamp else arcade_px
    target = region & ~real & (xx > 840) & (xx < 2720)
    ty, tx = np.nonzero(target)
    model = basis(tx, ty) @ coef + (glow(tx, ty)[:, None] * amp if with_lamp else 0)
    # grain like the real table
    ref = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY).astype(np.float32)
    sigma = float((ref - cv2.GaussianBlur(ref, (0, 0), 2))[bare].std())
    noise = cv2.GaussianBlur(np.random.default_rng(7).normal(0, sigma * 1.5, (h, w)).astype(np.float32), (0, 0), 0.8)
    synth = f.copy()
    synth[ty, tx] = model + noise[ty, tx, None]
    soft = cv2.GaussianBlur(target.astype(np.float32), (0, 0), 3)[..., None]
    print("table model fitted on", len(xs), "px; glow", sx, sy, amp.round(1), "grain", round(sigma, 2))
    out = np.clip(f * (1 - soft) + synth * soft, 0, 255).astype(np.uint8)
    return out, {"sx": sx, "sy": sy, "amp": amp.tolist()}


def main() -> None:
    import json

    img = np.asarray(Image.open(SRC).convert("RGB"))
    keep = lamp_keep(img.shape[:2])
    m = removal_mask(img.shape[:2])
    shelf = m.copy()
    shelf[TABLE_Y:] = False
    out, glow = rebuild_table(fill_cubbies(img, shelf, keep), m, keep)
    Image.fromarray(out).save(OUT, quality=95)

    # lamp-free version (the lamp gets placed elsewhere by the frame builder) + the lamp as a sprite
    lamp = keep | plate_shadow(keep.shape)
    shelf2 = (m | cv2.dilate(lamp.astype(np.uint8), np.ones((15, 15), np.uint8)).astype(bool))
    shelf2[TABLE_Y:] = False
    nolamp, _ = rebuild_table(fill_cubbies(img, shelf2, np.zeros_like(keep)), m | lamp, keep, with_lamp=False)
    Image.fromarray(nolamp).save(HERE / "neon_room_nolamp.jpg", quality=95)
    ys, xs = np.nonzero(lamp)
    x0, y0, x1, y1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
    alpha = cv2.GaussianBlur(lamp.astype(np.float32), (0, 0), 1.5)[y0:y1, x0:x1]
    sprite = np.dstack([img[y0:y1, x0:x1], (alpha * 255).astype(np.uint8)])
    Image.fromarray(sprite, "RGBA").save(HERE / "lamp_sprite.png")
    cx, cy = LAMP_CENTER
    (HERE / "lamp.json").write_text(json.dumps({**glow, "anchor": [cx - x0, cy - y0], "size": [int(x1 - x0), int(y1 - y0)]}))
    crop = (860, 1700, 2660, 2400)
    Image.fromarray(out).crop(crop).resize((1350, 525)).save(ANALYSIS / "clean_preview.jpg")
    print("saved", OUT)


if __name__ == "__main__":
    main()
