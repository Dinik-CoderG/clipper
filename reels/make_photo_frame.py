r"""Turn a real-photo desk frame (frames\real_frame.py, e.g. 8_blue_desk) into a frame for edit_viral.py's "setup"
layout. The room is the exact image the old render.py used (same crop, dim and fades); only the screen becomes a
fully transparent hole.

usage: make_photo_frame.py <real_frame name> <out name> [--room-cap N]    e.g.  8_blue_desk setup_main --room-cap 60
--room-cap N: softly compress the room's highlights (an LED strip, lit keys) toward luma N, keeping their colour and
leaving dark areas untouched, so the playing video stays the brightest thing in the picture.
Writes  frames\<out>.png   1080x1920, room opaque, screen fully transparent (anti-aliased edge)
        frames\<out>.json  {"screen": [x, y, w, h], "text_top": y, "quad": [[x, y] TL, TR, BR, BL], "source": ...}
"quad" is only written when the screen isn't an axis-aligned rectangle (a tilted or keystoned monitor); then
edit_viral.py warps the footage onto those corners.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "reels" / "frames"))
import real_frame  # noqa: E402

W, H = real_frame.W, real_frame.H
PAD = 0.006       # same overshoot real_frame used: the hole runs a few px into the bezel so no photo screen shows
SS = 4            # supersampling for an anti-aliased hole edge


def tame_highlights(room: Image.Image, cap: float) -> Image.Image:
    """Soft knee: luma below cap/2 is unchanged, brighter luma approaches cap (never reaches it); RGB scaled
    together so hues stay the same."""
    a = np.asarray(room).astype(np.float32)
    lum = a @ np.array([0.299, 0.587, 0.114], np.float32)
    knee = cap / 2
    over = np.maximum(lum - knee, 0)
    new = np.where(lum > knee, knee + over / (1 + over / (cap - knee)), lum)
    return Image.fromarray((a * (new / np.maximum(lum, 1))[..., None]).clip(0, 255).astype(np.uint8))


def main() -> None:
    args, cap = sys.argv[1:], 0.0
    if "--room-cap" in args:
        i = args.index("--room-cap")
        cap = float(args[i + 1])
        del args[i:i + 2]
    if len(args) != 2:
        sys.exit(__doc__)
    src, out = args
    cfg = real_frame.FRAMES[src]
    photo = Image.open(real_frame.REAL / cfg["photo"]).convert("RGB")
    x0, y0, s = real_frame.geometry(cfg, photo)
    room = real_frame.background(cfg, photo, x0, y0, s)
    _, _, inside = real_frame.screen_maps(cfg, x0, y0, s)
    ys, _ = np.nonzero(inside)
    if ys.min() > 330:                      # build() darkens the wall behind the hook the same way
        room = real_frame.hook_shade(room, int(ys.min()))
    if cap:
        room = tame_highlights(room, cap)

    tl, _, tr, _, br, _, bl, _ = [((x - x0) * s, (y - y0) * s) for x, y in cfg["screen"]]
    cx, cy = (tl[0] + tr[0] + br[0] + bl[0]) / 4, (tl[1] + tr[1] + br[1] + bl[1]) / 4
    quad = [(cx + (px - cx) * (1 + 2 * PAD), cy + (py - cy) * (1 + 2 * PAD)) for px, py in (tl, tr, br, bl)]

    big = Image.new("L", (W * SS, H * SS), 255)
    ImageDraw.Draw(big).polygon([(px * SS, py * SS) for px, py in quad], fill=0)
    alpha = big.resize((W, H), Image.LANCZOS)
    rgb = np.asarray(room).astype(np.float32) * (np.asarray(alpha, np.float32)[..., None] / 255)  # edge blends to black
    img = Image.fromarray(rgb.clip(0, 255).astype(np.uint8)).convert("RGBA")
    img.putalpha(alpha)

    qx, qy = [p[0] for p in quad], [p[1] for p in quad]
    bx, by = int(np.floor(min(qx))), int(np.floor(min(qy)))
    bw, bh = int(np.ceil(max(qx))) - bx, int(np.ceil(max(qy))) - by
    meta = {"screen": [bx, by, bw, bh], "text_top": by - 230,
            "source": f"reels\\frames\\real_frame.py {src} ({cfg['photo']})"}
    if cap:
        meta["room_cap"] = cap
    rect = abs(quad[0][0] - quad[3][0]) < 1.5 and abs(quad[1][0] - quad[2][0]) < 1.5 \
        and abs(quad[0][1] - quad[1][1]) < 1.5 and abs(quad[3][1] - quad[2][1]) < 1.5
    if not rect:
        meta["quad"] = [[round(px - bx, 1), round(py - by, 1)] for px, py in quad]   # relative to the screen box
    fdir = ROOT / "frames"
    img.save(fdir / f"{out}.png")
    (fdir / f"{out}.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print(f"wrote frames\\{out}.png  screen {meta['screen']}" + ("  quad " + str(meta["quad"]) if not rect else ""))


if __name__ == "__main__":
    main()
