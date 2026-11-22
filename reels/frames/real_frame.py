"""Gaming-room frames from real photos (Unsplash, free licence; source link per frame below): gameplay warped onto
the real (curved) screen. No blur anywhere: frames are plain crops of the photo, the real table extended, or (desk
frames) the photo fading into a dark room around a monitor that spans the phone's width.

build:    real_frame.py build <frame>                 -> real/assets/<frame>/{room.png, xmap.pgm, ymap.pgm, frame.json}
outline:  real_frame.py outline <frame>               -> frames/debug/outline_<frame>.jpg (screen fit check)
still:    real_frame.py still <frame> <video> <sec> <hook> <out.jpg>
video:    real_frame.py video <frame> <video> <start> <end> <hook> <out.mp4>
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))  # sibling module; scripts here run with python -P
sys.path.insert(0, str(HERE.parent))
import encode  # noqa: E402
from frame import hook_png  # noqa: E402

REAL = HERE / "real"
DEBUG = HERE / "debug"
W, H = 1080, 1920
SRC_W, SRC_H = 1920, 1080

# screen = 8 points on the photo: TL, TM, TR, RM, BR, BM, BL, LM (corners + middle of each bowed edge)
FRAMES = {
    # unsplash.com/photos/LKGNbWDyKuo, snacks removed and Kirby lamp moved by real/clean_table.py
    "1_neon_tv": dict(photo="neon_room_nolamp.jpg", crop_x=(874, 2650), extend_table=True,
                      screen=[(1040, 682), (1760, 721), (2489, 684), (2488, 1117), (2488, 1550), (1760, 1512),
                              (1035, 1545), (1037, 1113)]),
    # unsplash.com/photos/oLaBrUwQuD4
    "2_neon_coffee_table": dict(photo="room2.jpg", center_x=1560,
                                screen=[(956, 792), (1545, 806), (2158, 818), (2142, 1155), (2134, 1496),
                                        (1545, 1478), (966, 1554), (963, 1170)]),
    # desk frames (dark-room monitor look): span = monitor width share of the frame, top = monitor top as share of
    # the height, dim = room brightness; fit = keep the 16:9 aspect (crops top/bottom on a 21:9 ultrawide)
    # unsplash.com/photos/mHm1ASYNC0I: curved 21:9 ultrawide against a blue-purple neon wall
    "6_ultrawide_neon": dict(photo="desk_blue.jpg", span=0.94, top=0.36, dim=0.8, fit=True,
                             screen=[(709, 691), (1480, 712), (2259, 698), (2253, 1020), (2247, 1348), (1480, 1331),
                                     (711, 1343), (709, 1017)]),
    # unsplash.com/photos/fewhfXbCUzI: dark room with red light and an RGB keyboard
    "7_red_desk": dict(photo="desk_red.jpg", span=0.94, top=0.36, dim=1.25,
                       screen=[(1162, 780), (1702, 780), (2243, 780), (2243, 1104), (2243, 1428), (1696, 1428),
                               (1149, 1428), (1155, 1104)]),
    # unsplash.com/photos/zo3Nl28 (photo-1607896426171): dark desk, blue LED strip, posters on the wall
    "8_blue_desk": dict(photo="desk_blue2.jpg", span=0.94, top=0.36, dim=1.1,
                        screen=[(1054, 674), (1817, 674), (2581, 674), (2581, 1102), (2581, 1531), (1817, 1531),
                                (1054, 1531), (1054, 1102)]),
    # not in the render rotation (vertical monitor); kept for reference
    # unsplash.com/photos/7ayGrSgGkjk
    "4_desk_angle": dict(photo="../experimental/room4.jpg", center_x=1150, fit=True,
                         screen=[(640, 55), (1280, 290), (1906, 534), (1606, 1500), (1590, 2580), (1035, 2610),
                                 (484, 2700), (462, 1380)]),
    # unsplash.com/photos/2Zv8ZFk1GK8
    "5_desk_front": dict(photo="../experimental/room5.jpg", center_x=1180, fit=True,
                         screen=[(597, 470), (1200, 476), (1795, 490), (1717, 1500), (1767, 2510), (1200, 2505),
                                 (560, 2492), (637, 1500)]),
}
LAMP = REAL / "lamp_sprite.png"   # frame 1: the Kirby lamp, re-placed in the middle of the extended table
LAMP_SCALE = 1.15                 # a bit larger: it sits closer to the camera than its original spot
TABLE_TOP_Y = 1958                # frame 1: photo row where the table in front of the shelf begins


def _q(p0, p1, p2, t):
    """Quadratic curve through p0 (t=0), p1 (t=0.5), p2 (t=1)."""
    t = t[..., None]
    return np.asarray(p0) * (1 - t) * (1 - 2 * t) + np.asarray(p1) * 4 * t * (1 - t) + np.asarray(p2) * t * (2 * t - 1)


def coons(scr, u, v):
    tl, tm, tr, rm, br, bm, bl, lm = scr
    top, bot = _q(tl, tm, tr, u), _q(bl, bm, br, u)
    left, right = _q(tl, lm, bl, v), _q(tr, rm, br, v)
    uu, vv = u[..., None], v[..., None]
    corners = (1 - uu) * (1 - vv) * np.asarray(tl) + uu * (1 - vv) * np.asarray(tr) + (1 - uu) * vv * np.asarray(bl) \
        + uu * vv * np.asarray(br)
    return (1 - vv) * top + vv * bot + (1 - uu) * left + uu * right - corners


def geometry(cfg, photo: Image.Image):
    """Crop window on the photo -> (x0, y0, scale) so out = (photo - (x0, y0)) * scale."""
    if cfg.get("extend_table"):
        x0, x1 = cfg["crop_x"]
        return x0, 0, W / (x1 - x0)
    if cfg.get("span"):
        xs, ys = [p[0] for p in cfg["screen"]], [p[1] for p in cfg["screen"]]
        s = cfg["span"] * W / (max(xs) - min(xs))
        return (max(xs) + min(xs)) / 2 - W / 2 / s, min(ys) - cfg["top"] * H / s, s
    s = H / photo.height
    cw = W / s
    x0 = min(max(cfg["center_x"] - cw / 2, 0), photo.width - cw)
    return x0, 0, s


def desk_background(cfg, photo: Image.Image, x0, y0, s) -> Image.Image:
    """The photo placed around its monitor; wherever the photo ends inside the frame it fades into the dark room,
    and the room is dimmed toward the edges so the screen is the brightest thing (the dark-desk reel look)."""
    px0, py0 = max(x0, 0), max(y0, 0)
    px1, py1 = min(x0 + W / s, photo.width), min(y0 + H / s, photo.height)
    ox, oy = round((px0 - x0) * s), round((py0 - y0) * s)
    w, h = min(round((px1 - px0) * s), W - ox), min(round((py1 - py0) * s), H - oy)
    part = photo.crop((round(px0), round(py0), round(px1), round(py1))).resize((w, h), Image.LANCZOS)
    canvas = np.zeros((H, W, 3), np.float32)
    canvas[oy:oy + h, ox:ox + w] = np.asarray(part, np.float32)

    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)

    def ramp(dist):  # smoothstep from black at the photo's edge to full photo 260 px inside it
        t = np.clip(dist / 260.0, 0, 1)
        return t * t * (3 - 2 * t)

    a = np.ones((H, W), np.float32)
    if oy > 0:
        a *= ramp(yy - oy)
    if oy + h < H:
        a *= ramp(oy + h - yy)
    if ox > 0:
        a *= ramp(xx - ox)
    if ox + w < W:
        a *= ramp(ox + w - xx)
    ys = [p[1] for p in cfg["screen"]]
    cy = ((min(ys) + max(ys)) / 2 - y0) * s
    vignette = 1 - 0.55 * np.clip(((yy - cy) / (0.62 * H)) ** 2 + ((xx - W / 2) / (1.1 * W)) ** 2, 0, 1)
    canvas *= (a * vignette * cfg.get("dim", 1.0))[..., None]
    return Image.fromarray(np.clip(canvas, 0, 255).astype(np.uint8))


def background(cfg, photo: Image.Image, x0, y0, s) -> Image.Image:
    if cfg.get("span"):
        return desk_background(cfg, photo, x0, y0, s)
    ph = round(photo.height * s)
    sharp = photo.crop((round(x0), 0, round(x0 + W / s), photo.height)).resize((W, min(ph, H)), Image.LANCZOS)
    if not cfg.get("extend_table"):
        return sharp
    # below the photo the plain table simply continues: each column keeps the colour of the photo's last table
    # rows, getting a little darker toward the camera like a real phone shot, with the photo's grain
    canvas = np.zeros((H, W, 3), np.float32)
    canvas[:ph] = np.asarray(sharp).astype(np.float32)
    seam = 80                                                              # crossfade rows into the extension
    base = canvas[ph - seam - 40:ph - seam].mean(0)                       # (W, 3) table colour per column
    k = np.exp(-0.5 * (np.arange(-75, 76) / 25.0) ** 2)                   # smooth it sideways
    base = np.stack([np.convolve(np.pad(base[:, c], 75, mode="edge"), k / k.sum(), "valid") for c in range(3)], -1)
    t = np.linspace(0, 1, H - ph + seam)[:, None, None]
    ext = base[None] * (1 - 0.32 * t ** 1.3)
    gray = np.asarray(sharp.convert("L")).astype(np.float32)[ph - 200:ph]
    sigma = float((gray - np.asarray(Image.fromarray(gray.astype(np.uint8)).filter(ImageFilter.GaussianBlur(2)),
                                     np.float32)).std())
    ext += np.random.default_rng(3).normal(0, sigma, ext.shape[:2])[..., None]
    w_ext = np.clip(np.arange(H - ph + seam) / seam, 0, 1)[:, None, None]
    canvas[ph - seam:] = canvas[ph - seam:] * (1 - w_ext) + ext * w_ext

    # Kirby lamp in the middle of the extended table, with its warm glow on the table around the plate
    meta = json.loads((LAMP.with_name("lamp.json")).read_text())
    ls = s * LAMP_SCALE
    sprite = Image.open(LAMP)
    sprite = sprite.resize((round(sprite.width * ls), round(sprite.height * ls)), Image.LANCZOS)
    ax, ay = meta["anchor"][0] * ls, meta["anchor"][1] * ls
    left = round(W / 2 - ax)
    top = round((round(TABLE_TOP_Y * s) + H) / 2 - sprite.height / 2)
    gx, gy = left + ax, top + ay
    yy, xx = np.mgrid[0:H, 0:W]
    g = np.exp(-(((xx - gx) / (meta["sx"] * ls)) ** 2 + ((yy - gy) / (meta["sy"] * ls)) ** 2))
    canvas += g[..., None] * np.array(meta["amp"], np.float32) * 1.6
    room = Image.fromarray(np.clip(canvas, 0, 255).astype(np.uint8))
    room.paste(sprite, (left, top), sprite)
    return room


def hook_shade(room: Image.Image, tv_top: int) -> Image.Image:
    """Soft dark backing behind the hook (above the screen) so text stays readable over the neon."""
    shade = np.zeros((H, W), np.float32)
    lo = max(tv_top - 300, 0)
    shade[lo:max(tv_top - 140, lo)] = 0.55
    a = max(tv_top - 140, 0)
    shade[a:tv_top + 20] = np.linspace(0.55, 0, 160)[-(tv_top + 20 - a):, None]
    lo2 = max(lo - 260, 0)
    if lo > lo2:
        shade[lo2:lo] = (np.linspace(0, 1, 260) * 0.55)[-(lo - lo2):, None]
    return Image.fromarray((np.asarray(room).astype(np.float32) * (1 - shade[..., None])).astype(np.uint8))


def screen_maps(cfg, x0, y0, s):
    """Per output pixel: (u, v) on the screen, by densely sampling the Coons patch and splatting."""
    scr = [((x - x0) * s, (y - y0) * s) for x, y in cfg["screen"]]
    n = 1600
    pad = 0.006                                     # overshoot a few px so no photo screen content peeks out
    us, vs = np.meshgrid(np.linspace(-pad, 1 + pad, n), np.linspace(-pad, 1 + pad, n))
    p = coons(scr, us, vs)
    xi, yi = np.rint(p[..., 0]).astype(int), np.rint(p[..., 1]).astype(int)
    ok = (xi >= 0) & (xi < W) & (yi >= 0) & (yi < H)
    U = np.full((H, W), np.nan)
    V = np.full((H, W), np.nan)
    U[yi[ok], xi[ok]] = us[ok]
    V[yi[ok], xi[ok]] = vs[ok]
    inside = ~np.isnan(U)
    return np.nan_to_num(U), np.nan_to_num(V), inside   # u, v run slightly past 0..1 in the overshoot


def build(name: str) -> None:
    cfg = FRAMES[name]
    out = REAL / "assets" / name
    out.mkdir(parents=True, exist_ok=True)
    photo = Image.open(REAL / cfg["photo"]).convert("RGB")
    x0, y0, s = geometry(cfg, photo)
    room = background(cfg, photo, x0, y0, s)
    u, v, inside = screen_maps(cfg, x0, y0, s)
    # overshoot past the measured screen edge: edge pixels stretched (hidden by a thick bezel), or on thin-bezel
    # desk monitors a black rim, since stretched edge pixels would show there
    overshoot = (u < 0) | (u > 1) | (v < 0) | (v > 1)
    u, v = np.clip(u, 0, 1), np.clip(v, 0, 1)
    ys, xs = np.nonzero(inside)
    if ys.min() > 330:
        room = hook_shade(room, int(ys.min()))

    # gameplay placement inside the screen: stretched to fill a wide screen, or fitted (black bars) on a tall one
    sx, sy = u.copy(), v.copy()
    if cfg.get("fit"):
        sw, sh = xs.max() - xs.min(), ys.max() - ys.min()   # screen size in output px (approx.)
        frac = (sw * SRC_H / SRC_W) / sh                    # share of the screen height the 16:9 video covers
        sy = (v - (1 - frac) / 2) / frac
        inside_video = inside & (sy >= 0) & (sy <= 1)
    else:
        inside_video = inside
    if cfg.get("span"):
        inside_video = inside_video & ~overshoot
    xmap = np.where(inside_video, np.clip(sx * (SRC_W - 1), 0, SRC_W - 1), 65535).astype(">u2")
    ymap = np.where(inside_video, np.clip(sy * (SRC_H - 1), 0, SRC_H - 1), 65535).astype(">u2")
    for nm, arr in (("xmap", xmap), ("ymap", ymap)):
        with open(out / f"{nm}.pgm", "wb") as f:
            f.write(f"P5 {W} {H} 65535\n".encode())
            f.write(arr.tobytes())

    # room layer: screen cut out (soft 1px edge) with a faint glass sheen left on top of the gameplay
    hole = Image.fromarray((inside * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.8))
    inner = np.asarray(Image.fromarray((inside * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(7))) == 255
    sheen = np.clip(0.10 - 0.10 * v - 0.04 * u, 0, 0.10)       # brighter top-left, fades down/right
    a = 255 - np.asarray(hole).astype(np.float32)
    a = np.where(inner, sheen * 255, a)                          # sheen only well inside the bezel
    rgb = np.asarray(room).astype(np.float32)
    rgb = np.where(inner[..., None], 255.0, rgb)                 # sheen colour = white
    layer = Image.fromarray(rgb.astype(np.uint8)).convert("RGBA")
    layer.putalpha(Image.fromarray(a.astype(np.uint8)))
    layer.save(out / "room.png")

    box = {"x": int(xs.min()), "y": int(ys.min()), "w": int(xs.max() - xs.min() + 1), "h": int(ys.max() - ys.min() + 1)}
    (out / "frame.json").write_text(json.dumps(box))
    print("built", name, box)


def outline(name: str) -> None:
    """Draw the fitted screen outline (red) on the photo crop to check the measurements."""
    cfg = FRAMES[name]
    photo = Image.open(REAL / cfg["photo"]).convert("RGB")
    k = 1000 / photo.height
    img = photo.resize((round(photo.width * k), 1000))
    d = ImageDraw.Draw(img)
    t = np.linspace(0, 1, 60)
    for u, v in ((t, 0 * t), (t, 0 * t + 1), (0 * t, t), (0 * t + 1, t)):
        p = coons(cfg["screen"], u, v) * k
        d.line([tuple(q) for q in p], fill=(0, 255, 0), width=1)
    DEBUG.mkdir(exist_ok=True)
    img.save(DEBUG / f"outline_{name}.jpg")


def screen_box(name: str) -> dict:
    assets = REAL / "assets" / name
    if not (assets / "room.png").exists():
        build(name)
    return json.loads((assets / "frame.json").read_text())


def compose(name: str, video: str, start: float, end: float | None, hook: str, out: Path,
            ass: Path | None = None) -> None:
    """ass: optional subtitle file (dialogue captions) burned on top; ffmpeg runs in its folder."""
    assets = REAL / "assets" / name
    box = screen_box(name)
    with tempfile.TemporaryDirectory() as d:
        hp = Path(d) / "hook.png"
        hook_png(hook, box, hp)
        subs = f",ass={ass.name}" if ass else ""
        fc = (f"[0:v]scale={SRC_W}:{SRC_H}:flags=lanczos,setsar=1,format=yuv444p[g];"
              f"[1:v]format=gray16le[xm];[2:v]format=gray16le[ym];"
              f"[g][xm][ym]remap=fill=black,format=yuv420p[tv];"
              f"[tv][3:v]overlay=0:0[b1];[b1][4:v]overlay=0:0{subs},format=yuv420p[v]")
        stills = [str(assets / "xmap.pgm"), str(assets / "ymap.pgm"), str(assets / "room.png"), str(hp)]
        # low thread counts keep memory small (4K source decode + 1080p encode on a 6 GB machine)
        common = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-filter_threads", "2", "-threads", "2"]
        if end is None:
            ins = sum((["-i", p] for p in stills), [])
            subprocess.run(common + ["-ss", str(start), "-i", video, *ins, "-filter_complex", fc, "-map", "[v]",
                                     "-frames:v", "1", "-q:v", "2", str(out)], check=True, cwd=ass.parent if ass else None)
        else:
            looped = sum((["-loop", "1", "-i", p] for p in stills), [])
            encode.run(lambda vcodec: common + ["-ss", str(start), "-to", str(end), "-i", video, *looped,
                                                "-filter_complex", fc + ";[0:a]anull[a]", "-map", "[v]", "-map", "[a]",
                                                "-shortest", "-r", "30", *vcodec, "-c:a", "aac", "-b:a", "192k",
                                                "-ar", "48000", "-movflags", "+faststart", str(out)],
                       x264=["-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
                             "-threads", "3", "-x264-params", "rc-lookahead=20"],
                       quality="final", cwd=ass.parent if ass else None)


if __name__ == "__main__":
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == "build":
        build(args[0])
    elif cmd == "outline":
        outline(args[0])
    elif cmd == "still":
        compose(args[0], args[1], float(args[2]), None, args[3], Path(args[4]))
    elif cmd == "video":
        compose(args[0], args[1], float(args[2]), float(args[3]), args[4], Path(args[5]))
