r"""Old drawn "gaming setup" frame (not used: desk-frame channels use the real-photo frames from make_photo_frame.py): a
dark desk, a monitor with LED backlight, a soundbar and a keyboard, footage inside the monitor (layout "setup").

usage: make_setup_frame.py [name] [--accent #1E6BFF] [--seed 7]
Writes  frames\<name>.png   1080x1920 with a transparent hole where the screen is
        frames\<name>.json  {"screen": [x, y, w, h], "text_top": y, "accent": "#..."}
Default name: setup_drawn (the channel's real frames, setup_main / setup_red, come from make_photo_frame.py and must not
be overwritten). Other accents: --accent purple #8A3DFF, red #FF2D3D, teal #19D3C5.
This is a drawn frame, not a photo of a real room: don't describe it as your real setup in captions.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

W, H = 1080, 1920
ROOT = Path(__file__).resolve().parent.parent
SCREEN = (54, 654, 972, 547)          # x, y, w, h (16:9)


def hexcol(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def glow(cx, cy, rx, ry, color, strength):
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    d = ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2
    a = np.exp(-d * 1.6) * strength
    return a[..., None] * np.array(color, np.float32)[None, None, :]


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    name = args[0] if args else "setup_drawn"
    accent = hexcol(sys.argv[sys.argv.index("--accent") + 1]) if "--accent" in sys.argv else hexcol("#1E6BFF")
    seed = int(sys.argv[sys.argv.index("--seed") + 1]) if "--seed" in sys.argv else 7
    rng = np.random.default_rng(seed)
    sx, sy, sw, sh = SCREEN
    desk_y = 1352

    # wall: near-black with the LED backlight blooming behind and under the monitor
    img = np.zeros((H, W, 3), np.float32) + np.array([5, 7, 12], np.float32)
    img += glow(W / 2, sy + sh / 2, 760, 560, accent, 0.62)
    img += glow(W / 2, sy + sh + 60, 620, 190, accent, 0.55)
    img += glow(W / 2, sy - 40, 560, 150, accent, 0.30)
    # desk: darker surface with the light pooling on it
    desk = np.zeros((H, W, 3), np.float32) + np.array([7, 8, 11], np.float32)
    desk += glow(W / 2, desk_y + 30, 640, 230, accent, 0.42)
    yy = np.arange(H)[:, None, None]
    img = np.where(yy >= desk_y, desk, img)
    img[desk_y:desk_y + 3] += np.array(accent, np.float32) * 0.18          # desk edge catching light
    base = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(6))

    d = ImageDraw.Draw(base, "RGBA")
    # monitor stand + base
    d.polygon([(W / 2 - 46, sy + sh + 20), (W / 2 + 46, sy + sh + 20), (W / 2 + 70, 1302), (W / 2 - 70, 1302)],
              fill=(9, 10, 13, 255))
    d.rounded_rectangle([W / 2 - 215, 1296, W / 2 + 215, 1322], radius=13, fill=(11, 12, 16, 255))
    # soundbar
    d.rounded_rectangle([W / 2 - 300, 1318, W / 2 + 300, 1384], radius=30, fill=(13, 14, 18, 255),
                        outline=(30, 33, 42, 255), width=2)
    for x in range(int(W / 2 - 270), int(W / 2 + 270), 9):
        d.line([(x, 1334), (x, 1368)], fill=(22, 24, 31, 255), width=2)
    d.ellipse([W / 2 + 262, 1346, W / 2 + 270, 1354], fill=(*accent, 255))
    # monitor body (bezel) and screen hole
    d.rounded_rectangle([sx - 16, sy - 16, sx + sw + 16, sy + sh + 26], radius=18, fill=(8, 9, 12, 255),
                        outline=(26, 28, 36, 255), width=2)
    d.ellipse([W / 2 - 4, sy + sh + 9, W / 2 + 4, sy + sh + 17], fill=(*accent, 220))

    # keyboard: black case, grey keycaps, rows growing toward the camera, faint underglow
    kb = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    k = ImageDraw.Draw(kb)
    top, bottom, rows = 1470, 1716, 5
    k.polygon([(86, top - 16), (W - 86, top - 16), (W - 34, bottom + 20), (34, bottom + 20)], fill=(10, 11, 14, 255))
    y = float(top)
    for r in range(rows):
        t = r / (rows - 1)
        kh = 34 + 12 * t
        inset = 100 - 52 * t
        n = 15
        gap = 5 + 2 * t
        kw = (W - 2 * inset - gap * (n - 1)) / n
        x = inset
        for i in range(n):
            wide = kw
            if r == rows - 1 and i == 5:            # space bar
                wide = kw * 6 + gap * 5
            shade = int(52 + rng.integers(-6, 7) + 14 * t)
            k.rounded_rectangle([x, y, x + wide, y + kh], radius=6, fill=(shade, shade + 2, shade + 7, 255))
            k.line([(x + 4, y + 3), (x + wide - 4, y + 3)], fill=(shade + 26, shade + 28, shade + 34, 255), width=2)
            x += wide + gap
            if r == rows - 1 and i == 5:
                for _ in range(5):
                    pass
            if x > W - inset - kw * 0.5:
                break
        y += kh + gap + 2
    kb = kb.filter(ImageFilter.GaussianBlur(1.6))                 # slightly out of focus, like a phone shot
    under = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(under).polygon([(70, top - 26), (W - 70, top - 26), (W - 16, bottom + 34), (16, bottom + 34)],
                                  fill=(*accent, 70))
    base.paste(under.filter(ImageFilter.GaussianBlur(26)), (0, 0), under.filter(ImageFilter.GaussianBlur(26)))
    base.paste(kb, (0, 0), kb)

    arr = np.asarray(base).astype(np.float32)
    # vignette + grain so it reads as a camera shot, not a flat drawing
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    vig = 1 - 0.55 * np.clip((((x - W / 2) / (W * 0.75)) ** 2 + ((y - H * 0.52) / (H * 0.62)) ** 2), 0, 1)
    arr = arr * vig[..., None] + rng.normal(0, 2.2, (H, W, 1))
    out = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGBA")
    # transparent screen + soft light spilling from the screen edge onto the bezel
    alpha = Image.new("L", (W, H), 255)
    ImageDraw.Draw(alpha).rounded_rectangle([sx, sy, sx + sw, sy + sh], radius=6, fill=0)
    out.putalpha(alpha)
    (ROOT / "frames").mkdir(exist_ok=True)
    out.save(ROOT / "frames" / f"{name}.png")
    (ROOT / "frames" / f"{name}.json").write_text(json.dumps(
        {"screen": list(SCREEN), "text_top": 250, "accent": "#%02X%02X%02X" % accent}, indent=1), encoding="utf-8")
    print(f"wrote frames\\{name}.png  (screen {SCREEN})")


if __name__ == "__main__":
    main()
