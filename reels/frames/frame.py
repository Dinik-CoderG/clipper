"""Put gameplay on the TV of a gaming-room background (TV screen is chroma green in the room image).

prep:    frame.py prep <room.jpg>                 -> rooms/<name>.png (RGBA, screen cut out) + <name>.json (screen box)
still:   frame.py still <room> <video> <sec> <hook> <out.jpg>
video:   frame.py video <room> <video> <start> <end> <hook> <out.mp4>
Hook text uses "*word*" to highlight a word in yellow.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
import encode  # noqa: E402

ROOMS = HERE / "experimental" / "rooms"   # AI-generated rooms (not used; real_frame.py is the live frame)
W, H = 1080, 1920
FONT = "C:/Windows/Fonts/segoeuib.ttf"
EMOJI_FONT = "C:/Windows/Fonts/seguiemj.ttf"


def _fill(img: Image.Image, xy: tuple[int, int]) -> np.ndarray:
    a = np.asarray(img)
    probe = img.copy()
    ImageDraw.floodfill(probe, xy, (255, 0, 255), thresh=45)
    pm = np.asarray(probe)
    marker = (pm[..., 0] == 255) & (pm[..., 1] == 0) & (pm[..., 2] == 255)
    return marker & ~((a[..., 0] == 255) & (a[..., 1] == 0) & (a[..., 2] == 255))


def find_screen(img: Image.Image) -> np.ndarray:
    """Mask of the TV screen: the largest flat, saturated, rectangular region flood-filled from a grid of seeds
    (searched on a quarter-size copy, then filled once at full size). Works whatever colour the screen came out."""
    small = img.resize((img.width // 4, img.height // 4), Image.BILINEAR)
    a = np.asarray(small).astype(np.int16)
    best, best_area = None, 0
    for fy in np.arange(0.25, 0.70, 0.04):
        for fx in np.arange(0.30, 0.71, 0.05):
            x, y = int(fx * small.width), int(fy * small.height)
            px = a[y, x]
            if px.max() - px.min() < 80:  # screen colours are strongly saturated
                continue
            filled = _fill(small, (x, y))
            area = int(filled.sum())
            if area <= best_area:
                continue
            ys, xs = np.nonzero(filled)
            if area / ((xs.max() - xs.min() + 1) * (ys.max() - ys.min() + 1)) > 0.85:
                best, best_area = (x, y), area
    if best is None or best_area < 2500:
        raise SystemExit("no TV screen found")
    return _fill(img, (best[0] * 4 + 2, best[1] * 4 + 2))


TV_WIDTH = 0.88   # TV spans this share of the frame width (phone-sized gameplay)
TV_TOP = 0.34     # TV top edge sits here, leaving wall space above for the hook


NO_ZOOM = {"4_player_pov"}  # the hands holding the controller are the point of this room; keep the full view


def zoom_to_tv(src: Image.Image, name: str = "") -> Image.Image:
    """Crop the generated room around its TV so the TV fills TV_WIDTH of a 9:16 frame."""
    full = src.resize((W, H), Image.LANCZOS)
    if name in NO_ZOOM:
        return full
    ys, xs = np.nonzero(find_screen(full))
    tw, cx, top = xs.max() - xs.min() + 1, (xs.max() + xs.min()) / 2, ys.min()
    cw = min(tw / TV_WIDTH, W)
    ch = cw * H / W
    x0 = min(max(cx - cw / 2, 0), W - cw)
    y0 = min(max(top - TV_TOP * ch, 0), H - ch)
    k = src.width / W
    crop = src.crop((x0 * k, y0 * k, (x0 + cw) * k, (y0 + ch) * k)).resize((W, H), Image.LANCZOS)
    return crop.filter(ImageFilter.UnsharpMask(radius=2, percent=60, threshold=2))


def prep(room_jpg: Path) -> tuple[Path, dict]:
    img = zoom_to_tv(Image.open(room_jpg).convert("RGB"), room_jpg.stem)
    green = find_screen(img)
    ys, xs = np.nonzero(green)
    # screen box from robust percentiles so stray green pixels elsewhere don't stretch it
    # video box overshoots the detected screen by a few px so no screen-colour fringe survives at the bezel
    pad = 10
    x0, x1 = np.percentile(xs, [0.5, 99.5]).astype(int)
    y0, y1 = np.percentile(ys, [0.5, 99.5]).astype(int)
    box = {"x": int(x0) - pad, "y": int(y0) - pad, "w": int(x1 - x0 + 1) + 2 * pad, "h": int(y1 - y0 + 1) + 2 * pad}
    # cut-out: everything inside the box that is greenish becomes transparent; slightly grow + feather the hole
    hole = np.zeros((H, W), np.uint8)
    hole[green] = 255
    inside = np.zeros_like(hole)
    inside[box["y"]:box["y"] + box["h"], box["x"]:box["x"] + box["w"]] = 255
    hole = np.minimum(hole, inside)
    m = Image.fromarray(hole).filter(ImageFilter.MaxFilter(17)).filter(ImageFilter.GaussianBlur(1.5))
    alpha = Image.eval(m, lambda v: 255 - v)
    rgba = img.convert("RGBA")
    rgba.putalpha(alpha)
    out = ROOMS / f"{room_jpg.stem}.png"
    rgba.save(out)
    (ROOMS / f"{room_jpg.stem}.json").write_text(json.dumps(box))
    return out, box


def _is_emoji(ch: str) -> bool:
    cp = ord(ch)
    return cp >= 0x1F000 or 0x2600 <= cp <= 0x27BF or cp in (0x200D, 0xFE0F)


def _runs(word: str) -> list[tuple[str, bool]]:
    """Split a word into (text, is_emoji) runs so emoji are drawn with the colour emoji font."""
    runs: list[tuple[str, bool]] = []
    for ch in word:
        e = _is_emoji(ch)
        if runs and runs[-1][1] == e:
            runs[-1] = (runs[-1][0] + ch, e)
        else:
            runs.append((ch, e))
    return runs


def hook_png(text: str, box: dict, path: Path) -> None:
    """White bold hook centered in the wall space above the TV; *spans like this* are yellow; emoji in colour."""
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(canvas)
    size = 70
    font = ImageFont.truetype(FONT, size)
    efont = ImageFont.truetype(EMOJI_FONT, size)

    def width(word: str) -> float:
        return sum(d.textlength(t, font=efont if e else font) for t, e in _runs(word))

    # (word, highlighted) pairs; a highlight span may cover several words
    words: list[tuple[str, bool]] = []
    on = False
    for w in text.split():
        start, end = w.startswith("*"), "*" in w[1:]   # "*Season 1*:" ends a span before punctuation too
        on = on or start
        words.append((w.replace("*", ""), on))
        if end:
            on = False
    space = d.textlength(" ", font=font)
    lines: list[list[tuple[str, bool]]] = [[]]
    for w in words:  # greedy wrap to 940 px; an emoji never starts a line alone (it takes the last word with it)
        if lines[-1] and sum(width(x) + space for x, _ in lines[-1]) + width(w[0]) > 940:
            emoji_only = all(e for _, e in _runs(w[0]))
            carry = [lines[-1].pop()] if emoji_only and len(lines[-1]) > 1 else []
            lines.append(carry)
        lines[-1].append(w)
    if len(lines) == 2:  # balance two lines so a lone word ("here 🔥") never dangles on the second one
        def lw(ws):
            return sum(width(x) for x, _ in ws) + space * (len(ws) - 1)
        splits = [k for k in range(1, len(words))
                  if not all(e for _, e in _runs(words[k][0])) and max(lw(words[:k]), lw(words[k:])) <= 940]
        if splits:
            k = min(splits, key=lambda k: max(lw(words[:k]), lw(words[k:])))
            lines = [words[:k], words[k:]]
    lh = int(size * 1.3)
    top = max(60, box["y"] - 40 - lh * len(lines))
    for i, line in enumerate(lines):
        x = (W - (sum(width(w) for w, _ in line) + space * (len(line) - 1))) / 2
        y = top + i * lh
        for w, hl in line:
            for t, e in _runs(w):
                if e:
                    d.text((x, y + size * 0.08), t, font=efont, embedded_color=True)
                    x += d.textlength(t, font=efont)
                else:
                    d.text((x, y), t, font=font, fill=(255, 212, 0) if hl else (255, 255, 255),
                           stroke_width=4, stroke_fill=(0, 0, 0))
                    x += d.textlength(t, font=font)
            x += space
    canvas.save(path)


def compose(room: str, video: str, start: float, end: float | None, hook: str, out: Path) -> None:
    png = ROOMS / f"{room}.png"
    if not png.exists():
        prep(next(p for p in ROOMS.glob(f"{room}.*") if p.suffix in (".jpg", ".webp")))
    box = json.loads((ROOMS / f"{room}.json").read_text())
    with tempfile.TemporaryDirectory() as d:
        hp = Path(d) / "hook.png"
        hook_png(hook, box, hp)
        # gameplay scaled to cover the screen box, room on top (screen is transparent), then hook text;
        # a soft glow from the screen colours the room slightly for realism
        fc = (f"color=black:s={W}x{H}:r=30[base];"
              f"[0:v]scale={box['w']}:{box['h']}:force_original_aspect_ratio=increase,crop={box['w']}:{box['h']},setsar=1[tv];"
              f"[tv]split[tv1][tv2];[tv2]scale=270:480,boxblur=30:3,scale={W}:{H},eq=brightness=-0.35[glow];"
              f"[base][glow]overlay=0:0[b1];[b1][tv1]overlay={box['x']}:{box['y']}[b2];"
              f"[b2][1:v]overlay=0:0[b3];[b3][2:v]overlay=0:0,format=yuv420p[v]")
        common = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
        if end is None:  # still
            subprocess.run(common + ["-ss", str(start), "-i", video, "-i", str(png), "-i", str(hp), "-filter_complex", fc,
                                     "-map", "[v]", "-frames:v", "1", "-q:v", "2", str(out)], check=True)
        else:
            encode.run(lambda vcodec: common + ["-ss", str(start), "-to", str(end), "-i", video, "-loop", "1",
                                                "-i", str(png), "-loop", "1", "-i", str(hp),
                                                "-filter_complex", fc + ";[0:a]anull[a]", "-map", "[v]", "-map", "[a]",
                                                "-shortest", "-r", "30", *vcodec, "-c:a", "aac", "-b:a", "192k",
                                                "-movflags", "+faststart", str(out)],
                       x264=["-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p"], quality="final")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "prep":
        print(prep(Path(sys.argv[2])))
    elif cmd == "still":
        compose(sys.argv[2], sys.argv[3], float(sys.argv[4]), None, sys.argv[5], Path(sys.argv[6]))
    elif cmd == "video":
        compose(sys.argv[2], sys.argv[3], float(sys.argv[4]), float(sys.argv[5]), sys.argv[6], Path(sys.argv[7]))
