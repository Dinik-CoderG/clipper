r"""Edit Reels/Shorts like a short-form editor: a sequence of short beats with hard cuts, zoom punch-ins, flash
cuts, word-by-word captions, a hook in the first frame and an end card.

usage: edit_viral.py <campaign> [clip ids]
Reads   <campaign>\edit.json      list of clips (format below); footage from <campaign>\source\
Writes  <campaign>\clips\<id>.mp4    1080x1920, 30 fps, top quality, no size limit
        <campaign>\clips\sizes.json  size of each clip and who uploads it: "claude" (10 MB or less) or "manual"
        <campaign>\covers\<id>.jpg   a frame from the clip itself with the hook on it (no AI thumbnails)

edit.json:
[{"id": "01_lake_drain",
  "hook": "The boss drained the *entire lake*",     # *word* = highlight colour; shown from frame 1
  "hook_until": 2.5,                                  # seconds (default: end of the first beat, max 3.5)
  "brand": "EXAMPLE GAME",                             # small pill at the top the whole time (optional)
  "logo": {"path": "brief/logo.png", "width": 300, "x": 740, "y": 240},  # a brief's required logo, whole clip
                                                      # (path relative to the campaign; x/y default top-right)
  "cta": ["Search *EXAMPLE GAME*", "on the *game store*"],   # end card over the last cta_secs (optional)
  "cta_secs": 2.0,
  "cam": [0.0, 0.32, 0.205, 0.21],                    # layout "stack": facecam rect (x, y, w, h, 0-1 of source)
  "hook_y": 625,                                      # hook position without a frame (default 310)
  "layout": "full",                                   # default for beats: full (9:16 crop) | wide (1:1 on blur)
                                                      # | stack (facecam on top, the whole game frame below,
                                                      #   its own small facecam kept, "blur_cam": true hides it; needs "cam"; hook on the seam)
                                                      # | setup (plays on the monitor of the channel's desk frame)
  "frame": "setup_main",                              # with layout setup: frames\<name>.png + .json
                                                      # (make_photo_frame.py); the hook then stays on screen all clip.
                                                      # Default: the channel's frame (channels.json "frame", with a
                                                      # "frame_variants" entry on every 5th clip), if it has one.
  "oled": 1.0,                                        # setup frames: OLED-monitor look, 0 (off) - 1.5 (default 1.0)
  "beats": [
     {"src": "example_source", "start": 5.0, "end": 7.4,
      "speed": 1.0,             # 0.5 = slow motion, 1.5 = faster (0.5-2.0)
      "zoom": [1.0, 1.15],      # zoom at start -> end of the beat (punch-in / slow push)
      "focus": [0.5, 0.5],      # where to centre the crop (0-1 of the frame width/height)
      "layout": "wide",         # override per beat
      "flash": true,            # white flash on the cut into this beat
      "sfx": "none",            # impact | riser | pop | none (default), on the cut into this beat. No whoosh:
                                # the user rejected it (21 Nov 2026); an old "whoosh" in edit.json plays nothing
      "label": "GOOD",          # big label for the whole beat (optional), "label_color": "#5AE6FF"
      "text": "the water just leaves",   # word-by-word caption over the beat (optional)
      "words": [[5.02, 5.30, "the"], [5.30, 5.71, "water"]]}   # speech: Whisper word times in SOURCE seconds; the
                                # caption then lights each word exactly when it is spoken (made by speech_edit.py)
  Layout "speaker" (talking footage: podcasts, streams, shows) finds whoever is talking in each beat and fills
  the screen with them (reels\speaker.py); "focus": [x, y] hints at a person, "speaker": "focus" locks to them.
  ]}]

Editing rules this follows (and why): something changes every 1-2.5 s (Instagram/YouTube both say viewers decide
in the first seconds and swipe dead air), the payoff is shown fast and fully, captions are big and short (most
watch muted), no transition sounds on cuts (the user rejected the whoosh), everything important sits inside the safe zone (top 220 px and bottom
~420 px are covered by the app UI), and the end card carries the brand's call to action.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1080, 1920, 30
CHROME_UPLOAD_BYTES = 10 * 1024 * 1024   # Claude in Chrome can't upload bigger files; never a quality limit
YELLOW, WHITE = (255, 214, 10), (255, 255, 255)
HERE = Path(__file__).resolve().parent
FONTS = ["C:/Windows/Fonts/ariblk.ttf", "C:/Windows/Fonts/impact.ttf", "C:/Windows/Fonts/arialbd.ttf",
         "/usr/share/fonts/opentype/inter/Inter-Black.otf",
         "/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
FONT = next((f for f in FONTS if os.path.exists(f)), None)
SFX = {  # made with ffmpeg's own generators, so there is no copyrighted audio in any clip; used only when a beat
    # asks for one. No "whoosh": the user doesn't want it on any clip (21 Nov 2026), so it was removed.
    "impact": "aevalsrc='0.9*sin(2*PI*(70-40*t)*t)*exp(-5*t)':d=0.8:s=44100",
    "riser": "anoisesrc=d=1.2:c=white:a=0.6,bandpass=f=2500:w=1800,afade=t=in:d=1.15:curve=exp,"
             "afade=t=out:st=1.15:d=0.05,volume=0.45",
    "pop": "aevalsrc='0.6*sin(2*PI*900*t)*exp(-30*t)':d=0.15:s=44100",
}


def font(size):
    return ImageFont.truetype(FONT, size) if FONT else ImageFont.load_default()


def hexcol(c, default):
    if not c:
        return default
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def run(cmd, quiet=True):
    r = subprocess.run([str(c) for c in cmd], capture_output=quiet, text=True)
    if r.returncode:
        sys.exit(f"ffmpeg failed: {' '.join(str(c) for c in cmd[:8])} ...\n{(r.stderr or '')[-1500:]}")
    return r


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height:format=duration", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True).stdout
    j = json.loads(out)
    return j["streams"][0]["width"], j["streams"][0]["height"], float(j["format"]["duration"])


def has_audio(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout
    return bool(out.strip())


_GPU = None


def gpu():
    """What the NVIDIA GPU can take over, tested once by really encoding a frame (ffmpeg lists NVENC even on PCs
    without a usable GPU). CLIPPER_ENCODER=x264 forces everything onto the CPU.
    Returns {"final": bool, "lossless": bool, "decode": bool}."""
    global _GPU
    if _GPU is None:
        _GPU = {"final": False, "lossless": False, "decode": False}
        if os.environ.get("CLIPPER_ENCODER", "").lower() != "x264":
            def ok(fmt, *enc):
                return subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"color=black:s=1080x1920:d=0.2",
                                       "-pix_fmt", fmt, *enc, "-f", "null", "-"], capture_output=True).returncode == 0
            _GPU["final"] = ok("yuv420p", "-c:v", "h264_nvenc", "-preset", "p7", "-tune", "hq", "-rc", "vbr", "-cq", "17")
            _GPU["lossless"] = _GPU["final"] and ok("yuv444p", "-c:v", "h264_nvenc", "-preset", "p4", "-tune", "lossless")
            _GPU["decode"] = _GPU["final"]
        print("video encode: " + ("NVIDIA GPU (NVENC)" if _GPU["final"] else "CPU (x264)"), flush=True)
    return _GPU


def try_run(cmd):
    return subprocess.run([str(c) for c in cmd], capture_output=True, text=True).returncode == 0


# ---------------------------------------------------------------- text overlays (transparent PNGs)

EMOJI_FONTS = ["C:/Windows/Fonts/seguiemj.ttf", "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"]
EMOJI_FONT = next((f for f in EMOJI_FONTS if os.path.exists(f)), None)


def is_emoji(ch):
    o = ord(ch)
    return o >= 0x1F000 or 0x2600 <= o <= 0x27BF or o in (0xFE0F, 0x200D) or 0x2B00 <= o <= 0x2BFF


def runs(txt):
    """Split into (text, is_emoji) runs so emoji can be drawn with the colour emoji font."""
    out = []
    for ch in txt:
        e = is_emoji(ch)
        if out and out[-1][1] == e:
            out[-1][0] += ch
        else:
            out.append([ch, e])
    return out


def text_w(draw, txt, f, size):
    return sum(len([c for c in t if ord(c) not in (0xFE0F, 0x200D)]) * size * 1.08 if e else draw.textlength(t, font=f)
               for t, e in runs(txt))


def draw_text(draw, x, y, txt, f, size, fill, stroke):
    for t, e in runs(txt):
        if not e:
            draw.text((x, y), t, font=f, fill=fill, stroke_width=stroke, stroke_fill=(0, 0, 0))
            x += draw.textlength(t, font=f)
            continue
        for ch in t:
            if ord(ch) in (0xFE0F, 0x200D):
                continue
            if EMOJI_FONT:
                native = 109 if "Noto" in EMOJI_FONT else size
                try:
                    ef = ImageFont.truetype(EMOJI_FONT, native)
                    g = Image.new("RGBA", (int(native * 1.4), int(native * 1.4)), (0, 0, 0, 0))
                    ImageDraw.Draw(g).text((0, 0), ch, font=ef, embedded_color=True)
                    box = g.getbbox()
                    if box:
                        g = g.crop(box)
                        g = g.resize((max(1, int(g.width * size / native)), max(1, int(g.height * size / native))))
                        draw._image.alpha_composite(g, (int(x), int(y + size * 0.12)))
                except Exception:  # noqa: BLE001
                    pass
            x += size * 1.08
    return x


def stack_geometry(sw, sh, cam):
    """Layout "stack": facecam panel on top (full width, or narrower when the cam box is tall) and the whole game
    frame (16:9 -> 1080x608) right under it, the pair centred in the area the app UI leaves free (y 200-1500)."""
    gh = 2 * round(W * sh / sw / 2)
    ar = (sw * cam[2]) / (sh * cam[3])                  # facecam aspect (w/h)
    th = 2 * round(min(1300 - gh, W / ar) / 2)
    cw = 2 * round(min(W, th * ar) / 2)
    top = 200 + max(0, (1300 - th - gh) // 2)
    return {"cam_w": cw, "cam_h": th, "game_h": gh, "top": top, "seam": top + th}


LIT_STAR = "\x00"    # a literal "*" inside a caption word; "*word*" itself means highlight


def rich(draw, y, text, size, base=WHITE, hi=YELLOW, stroke=8, max_w=W - 120):
    """Centred text, *word* highlighted, wrapped to max_w. Returns the y below it."""
    f = font(size)
    words, out, hi_on = [], [], False
    for i, chunk in enumerate(text.split("*")):
        for w in chunk.split():
            words.append((w.replace(LIT_STAR, "*"), i % 2 == 1))   # a masked swear's stars ("f**k") stay stars
    line, lines = [], []
    for w in words:
        trial = " ".join(x for x, _ in line + [w])
        if line and text_w(draw, trial, f, size) > max_w:
            lines.append(line)
            line = []
        line.append(w)
    if line:
        lines.append(line)
    for ln in lines:
        total = text_w(draw, " ".join(x for x, _ in ln), f, size)
        x = (W - total) / 2
        for j, (w, h) in enumerate(ln):
            txt = w + (" " if j < len(ln) - 1 else "")
            x = draw_text(draw, x, y, txt, f, size, hi if h else base, stroke)
        y += int(size * 1.15)
    return y


OFFS = {}            # overlay file -> (x, y) where it sits on the 1080x1920 canvas
CAP_BAND = (0, 1230, W, 1570)   # every caption card is cut to this same band (the caption track needs one size)


def overlay_png(path, fn, box=None):
    """Draw on a transparent canvas, then keep only the part that has something on it (or the fixed `box`). A full
    1080x1920 overlay per text card is what made renders eat memory and CPU: ffmpeg blends every pixel of every
    card on every frame."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    fn(ImageDraw.Draw(img), img)
    bb = box or img.getbbox() or (0, 0, 2, 2)
    bb = (bb[0] // 2 * 2, bb[1] // 2 * 2, min(W, (bb[2] + 1) // 2 * 2), min(H, (bb[3] + 1) // 2 * 2))
    img.crop(bb).save(path)
    OFFS[str(path)] = (bb[0], bb[1])


def hook_png(path, hook, brand, y=310, size=82):
    def draw(d, img):
        _pill(d, brand)
        if hook:
            rich(d, y, hook, size, stroke=max(4, size // 10))
    overlay_png(path, draw)


def _pill(d, brand):
    if brand:
        f = font(34)
        tw = d.textlength(brand, font=f)
        d.rounded_rectangle([(W - tw) / 2 - 22, 232, (W + tw) / 2 + 22, 286], radius=27, fill=(0, 0, 0, 150))
        d.text(((W - tw) / 2, 238), brand, font=f, fill=YELLOW)


def label_png(path, text, color):
    overlay_png(path, lambda d, img: rich(d, 1120, f"*{text}*", 120, hi=color, stroke=10))


def caption_pngs(tmp, key, text, dur):
    """Word-by-word: phrases of up to 3 words, the current word in yellow. Returns [(png, t0, t1)]."""
    words = text.replace("*", LIT_STAR).split()
    if not words:
        return []
    per = dur / len(words)
    out = []
    for i, w in enumerate(words):
        g0 = (i // 3) * 3
        phrase = words[g0:g0 + 3]
        marked = " ".join(f"*{x}*" if g0 + k == i else x for k, x in enumerate(phrase))
        p = tmp / f"cap_{key}_{i}.png"
        overlay_png(p, lambda d, img, m=marked: rich(d, 1290, m.upper(), 78, stroke=9), box=CAP_BAND)
        out.append((p, i * per, (i + 1) * per))
    return out


CAPTION_DROP = {"um", "uh", "umm", "uhh", "erm", "hmm"}


def timed_caption_pngs(tmp, key, words, start, speed, dur):
    """Captions timed to the speech. words = [[t0, t1, "word"], ...] in source seconds (Whisper word times). Phrases
    of up to 3 words that end at punctuation; each word lights up when it is spoken and stays lit until the next.
    Returns [(png, t0, t1)] in beat time."""
    toks = []
    for t0, t1, w in words:
        shown = w.strip().strip('"').replace("--", "").replace("*", LIT_STAR)
        bare = shown.lower().strip(".,?!;:")
        if not bare or bare in CAPTION_DROP:
            continue
        toks.append([max(0.0, (t0 - start) / speed), max(0.0, (t1 - start) / speed), shown])
    phrases, cur = [], []
    for t in toks:
        cur.append(t)
        if len(cur) == 3 or t[2][-1:] in ".?!,;:":
            phrases.append(cur)
            cur = []
    if cur:
        phrases.append(cur)
    flat = [(pi, wi) for pi, ph in enumerate(phrases) for wi in range(len(ph))]
    out = []
    for n, (pi, wi) in enumerate(flat):
        ph = phrases[pi]
        t0 = ph[wi][0] if n else max(0.0, ph[wi][0] - 0.08)
        if n + 1 < len(flat):
            nxt = phrases[flat[n + 1][0]][flat[n + 1][1]][0]
            t1 = nxt if flat[n + 1][0] == pi else min(nxt, ph[wi][1] + 0.35)   # a pause clears the screen
        else:
            t1 = min(dur, ph[wi][1] + 0.25)
        t0, t1 = min(t0, dur), min(t1, dur)
        if t1 - t0 < 0.02:
            continue
        clean = [x[2].rstrip(".,;:") for x in ph]
        marked = " ".join(f"*{x}*" if k == wi else x for k, x in enumerate(clean))
        p = tmp / f"cap_{key}_{n}.png"
        overlay_png(p, lambda d, img, m=marked: rich(d, 1290, m.upper(), 78, stroke=9), box=CAP_BAND)
        out.append((p, t0, t1))
    return out


def cta_png(path, lines, rect=None):
    def draw(d, img):
        if rect:   # setup frame: the end card sits on the monitor screen
            x, y0, w, h = rect
            img.alpha_composite(Image.new("RGBA", (w, h), (0, 0, 0, 215)), (x, y0))
            y = y0 + h // 2 - int(len(lines) * 62 * 1.15) // 2
            for ln in lines:
                y = rich(d, y, ln, 62, stroke=6, max_w=w - 60)
            return
        band = Image.new("RGBA", (W, 560), (0, 0, 0, 200))
        img.alpha_composite(band, (0, 680))
        y = 740
        for ln in lines:
            y = rich(d, y, ln, 80)
    overlay_png(path, draw)


# ---------------------------------------------------------------- beats

def sfx_file(tmp, name):
    p = tmp / f"sfx_{name}.wav"
    if not p.exists():
        run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", SFX[name], "-ac", "2", "-ar", "44100", p])
    return p


def oled_filters(k):
    """The OLED-monitor look for footage on a setup frame, strength k (0 = off, 1 = default, max 1.5): deeper blacks
    and more contrast, saturation +17% at 1.0, clearly brighter mid-tones, highlights rolled off instead of clipped
    (only pure white stays white), and a light, small-radius unsharp mask. Curves run at 16 bits to avoid banding."""
    k = max(0.0, min(1.5, float(k)))
    if not k:
        return ""
    # many points so the spline can't sag: (input, change at k=1): black floor a touch deeper, low-mids and
    # mids lifted, highlights rolled off toward the unchanged white point
    lift = [(0.02, -0.008), (0.06, 0.02), (0.1, 0.045), (0.15, 0.06), (0.3, 0.08), (0.5, 0.075), (0.75, 0.05),
            (0.9, 0.025)]
    curve = "0/0 " + " ".join(f"{x}/{x + k * d:.4f}" for x, d in lift) + " 1/1"
    return (f",eq=saturation={1 + 0.17 * k:.3f},format=gbrp16le,curves=master='{curve}',format=yuv444p,"
            f"unsharp=lx=5:ly=5:la={0.4 * k:.2f}:cx=5:cy=5:ca=0")


def frame_layers(tmp, frame_png, meta, k):
    """Room dimmed by 18% x oled (max 25%) so the screen is the brightest thing, and a grey mask (0 on the screen)
    saying how much screen light falls on the bezel and desk around it."""
    img = Image.open(frame_png).convert("RGBA")
    a = np.asarray(img).astype(np.float32)
    a[..., :3] *= 1 - min(0.25, 0.18 * k)
    room = tmp / "room.png"
    Image.fromarray(a.clip(0, 255).astype(np.uint8)).save(room)
    hole = ImageChops.invert(img.getchannel("A"))                     # 255 on the screen
    blur = lambda r: np.asarray(hole.filter(ImageFilter.GaussianBlur(r)), np.float32) / 255
    far = blur(110)
    desk = np.roll(blur(80), 150, axis=0)                              # light pooling on the desk below
    # light only shows on surfaces that reflect it: the matte black bezel and monitor body stay black (a lit
    # band hugging the screen edge is what makes a composite look fake)
    lum = np.asarray(img.convert("RGB"), np.float32) @ np.array([0.299, 0.587, 0.114], np.float32)
    albedo = np.clip((lum - 8) / 60, 0, 1)
    g = (0.7 * far + 0.45 * desk) * albedo * (1 - np.asarray(hole, np.float32) / 255)
    mask = tmp / "glow.png"
    Image.fromarray((np.clip(g * min(1.0, 0.6 * k), 0, 1) * 255).astype(np.uint8)).convert("RGB").save(mask)
    return room, mask


def render_beat(tmp, idx, beat, default_layout, srcdir):
    src = srcdir / f"{beat['src']}.mp4"
    if not src.exists():
        sys.exit(f"missing footage: {src}")
    sw, sh, _ = probe(src)
    speed = max(0.5, min(2.0, float(beat.get("speed", 1.0))))
    span = float(beat["end"]) - float(beat["start"])
    dur = span / speed
    n = max(1, round(dur * FPS))
    z0, z1 = beat.get("zoom", [1.0, 1.08])
    fx, fy = beat.get("focus", [0.5, 0.5])
    layout = beat.get("layout", default_layout)
    zoom = (f"zoompan=z='{z0}+({z1}-{z0})*on/{max(n - 1, 1)}':d=1:fps={FPS}:"
            f"x='max(0,min(iw-iw/zoom,iw*{fx}-iw/zoom/2))':y='max(0,min(ih-ih/zoom,ih*{fy}-ih/zoom/2))'")
    pre = f"setpts=(PTS-STARTPTS)/{speed},fps={FPS}"
    if layout == "setup":   # the footage plays on the monitor of the channel's setup frame (frames\<name>.png)
        bx, by, bw, bh = beat["_screen"]
        quad = beat.get("_quad")
        k = 2 if quad else 1            # a warped screen is rendered at 2x, warped, then scaled down
        tw, th = bw * k, bh * k
        ar = tw / th
        cw = min(sw, round(sh * ar))
        ch = min(sh, round(cw / ar))
        cx = max(0, min(sw - cw, round(sw * fx - cw / 2)))
        cy = max(0, min(sh - ch, round(sh * fy - ch / 2)))
        zt = f"max(1,{z0}+({z1}-{z0})*t/{max(dur, 0.01):.3f})"
        # one lanczos scale straight from the source pixels to the screen size, zoom included (no zoompan resample)
        vf = (f"[0:v]{pre},crop={cw}:{ch}:{cx}:{cy},"
              f"scale=w='2*trunc({tw}*{zt}/2+0.5)':h='2*trunc({th}*{zt}/2+0.5)':eval=frame:"
              f"flags=lanczos+accurate_rnd+full_chroma_int,crop={tw}:{th}:'(iw-{tw})*{fx}':'(ih-{th})*{fy}'")
        if quad:   # corners TL, TR, BR, BL in screen-box pixels; ffmpeg wants TL, TR, BL, BR
            pts = ":".join(f"{x * k:.1f}:{y * k:.1f}" for x, y in (quad[0], quad[1], quad[3], quad[2]))
            vf += f",perspective={pts}:sense=destination:interpolation=cubic,scale={bw}:{bh}:flags=lanczos"
        vf += oled_filters(beat.get("_oled", 0)) + f",setsar=1,pad={W}:{H}:{bx}:{by}:black[v]"
    elif layout == "speaker":   # talking footage: full-screen crop on whoever is speaking (reels\speaker.py)
        from speaker import speaker_crop
        hint = beat.get("focus") or beat.get("_hint")
        sc = speaker_crop(src, float(beat["start"]), float(beat["end"]), hint=hint,
                          lock=beat.get("speaker") == "focus", prev=beat.get("_prev"))
        if sc.get("face_h", 0) > 0.40:     # the face already fills the frame: a gentle push only, no punch-in
            z0, z1 = 1.0, 1.02
        rx, ry, rw, rh = sc["rect"]
        px, py = sc["face"]
        beat["_center"] = [(rx + px * rw) / sw, (ry + py * rh) / sh]
        beat["_speaker"] = sc
        zsp = (f"zoompan=z='{z0}+({z1}-{z0})*on/{max(n - 1, 1)}':d=1:fps={FPS}:"
               f"x='max(0,min(iw-iw/zoom,iw*{px}-iw/zoom/2))':y='max(0,min(ih-ih/zoom,ih*{py}-ih/zoom/2))'")
        if sc["aspect"] == "9:16":
            vf = (f"[0:v]{pre},crop={rw}:{rh}:{rx}:{ry},scale={W}:{H}:flags=lanczos+accurate_rnd,"
                  f"{zsp}:s={W}x{H},setsar=1[v]")
        else:   # small tile / 1080p source: a 4:5 picture on a blur of itself instead of a soft 9:16 upscale
            fh = 1350
            vf = (f"[0:v]{pre},crop={rw}:{rh}:{rx}:{ry},split[a][b];"
                  f"[a]scale=270:480,boxblur=14:2,eq=brightness=-0.22,scale={W}:{H},setsar=1[bg];"
                  f"[b]scale={W}:{fh}:flags=lanczos+accurate_rnd,{zsp}:s={W}x{fh},setsar=1[fg];"
                  f"[bg][fg]overlay=0:{(H - fh) // 2 - 45}[v]")
    elif layout == "stack":   # streamer clip: big facecam on top, the WHOLE game frame under it (never cropped)
        cx0, cy0, cw0, ch0 = beat["cam"]                       # facecam rect, 0-1 of the source frame
        camw, camh = round(sw * cw0), round(sh * ch0)
        camx, camy = round(sw * cx0), round(sh * cy0)
        g = stack_geometry(sw, sh, beat["cam"])
        cwd, th, gh, y0 = g["cam_w"], g["cam_h"], g["game_h"], g["top"]
        # punch-ins happen on the face, so the game frame is always shown whole (the user's call, 21 Nov 2026)
        zc = (f"zoompan=z='{z0}+({z1}-{z0})*on/{max(n - 1, 1)}':d=1:fps={FPS}:"
              f"x='max(0,min(iw-iw/zoom,iw*0.5-iw/zoom/2))':y='max(0,min(ih-ih/zoom,ih*0.45-ih/zoom/2))'")
        # the streamer's own small facecam inside the game frame stays visible (the user's call, 21 Nov 2026);
        # "blur_cam": true on the clip/beat blurs it out instead
        bx, by = max(0, round(W * cx0) - 8), max(0, round(gh * cy0) - 8)
        bw = 2 * (min(W - bx, round(W * cw0) + 16) // 2)
        bh2 = 2 * (min(gh - by, round(gh * ch0) + 16) // 2)
        vf = (f"[0:v]{pre},split=3[b][c][g];"
              f"[b]crop={round(sh * 9 / 16)}:{sh},scale=270:480,boxblur=14:2,eq=brightness=-0.28,"
              f"scale={W}:{H},setsar=1[bg];"
              f"[c]crop={camw}:{camh}:{camx}:{camy},scale={cwd}:{th}:flags=lanczos,{zc}:s={cwd}x{th},setsar=1[top];"
              f"[g]scale={W}:{gh}:flags=lanczos,setsar=1,split[g1][g2];"
              + (f"[g2]crop={bw}:{bh2}:{bx}:{by},boxblur=24:4[gb];[g1][gb]overlay={bx}:{by}[game];"
                 if beat.get("blur_cam") else "[g1]null[game];[g2]nullsink;") +
              f"[bg][top]overlay={(W - cwd) // 2}:{y0}[t1];[t1][game]overlay=0:{y0 + th}[v]")
    elif layout == "full":
        cw = min(sw, round(sh * 9 / 16))
        cx = max(0, min(sw - cw, round(sw * fx - cw / 2)))
        vf = f"[0:v]{pre},crop={cw}:{sh}:{cx}:0,scale={W}:{H}:flags=lanczos,{zoom}:s={W}x{H},setsar=1[v]"
    else:  # wide: square crop of the action over a blurred, darkened copy of the same shot
        side = min(sw, sh)
        cx = max(0, min(sw - side, round(sw * fx - side / 2)))
        vf = (f"[0:v]{pre},split[a][b];"
              f"[a]crop={round(sh * 9 / 16)}:{sh},scale=270:480,boxblur=12:2,eq=brightness=-0.18,"
              f"scale={W}:{H},setsar=1[bg];"
              f"[b]crop={side}:{side}:{cx}:0,scale={W}:{W}:flags=lanczos,{zoom}:s={W}x{W},setsar=1[fg];"
              f"[bg][fg]overlay=0:{(H - W) // 2 - 40}[v]")
    if beat.get("flash"):
        vf = vf[:-3] + ",fade=t=in:st=0:d=0.15:color=white[v]"
    if beat.get("bright"):
        b = float(beat["bright"])
        vf = vf[:-3] + f",eq=brightness={0.06 * b}:gamma={1 + 0.25 * b}:saturation=1.1[v]"
    out = tmp / f"beat_{idx:02d}.mp4"
    mute = ",volume=0" if beat.get("mute") else ""    # "mute": true = silent beat (e.g. a hold under the end card)
    audio = (["-map", "0:a", "-af", f"atempo={speed},afade=t=in:d=0.03,afade=t=out:st={max(0, dur - 0.05)}:d=0.05{mute}"]
             if has_audio(src) else ["-f", "lavfi", "-t", dur, "-i", "anullsrc=r=44100:cl=stereo", "-map", "1:a"])
    g = gpu()
    # lossless beat files: the only lossy encode is the final pass. On an NVIDIA GPU the lossless encode runs there.
    venc = (["-c:v", "h264_nvenc", "-preset", "p4", "-tune", "lossless", "-pix_fmt", "yuv444p"] if g["lossless"] else
            ["-c:v", "libx264", "-preset", "ultrafast", "-qp", "0", "-pix_fmt", "yuv444p", "-threads", "2"])

    def build(hw):
        cmd = ["ffmpeg", "-y", "-v", "error", "-filter_complex_threads", "2", "-threads", "2",
               *(["-hwaccel", "cuda"] if hw else []), "-ss", beat["start"], "-t", span, "-i", src]
        aud = list(audio)
        if not has_audio(src):
            cmd += aud[:6]
            aud = aud[6:]
        return cmd + ["-filter_complex", vf, "-map", "[v]", *aud, "-t", dur, *venc, "-c:a", "pcm_s16le",
                      "-ar", "44100", "-ac", "2", out]
    # the GPU also decodes the source (HEVC/H.264); if this file can't be decoded there, the CPU does it
    if not (g["decode"] and try_run(build(True))):
        run(build(False))
    return out, dur


def build_clip(root, clip, tmp):
    beats = clip["beats"]
    srcdir = root / "source"
    frame = None
    if clip.get("frame") or clip.get("layout") == "setup":
        name = clip.get("frame", "setup_main")
        fdir = HERE.parent / "frames"
        if not (fdir / f"{name}.png").exists():
            sys.exit(f"frame not found: {fdir / (name + '.png')} (run reels\\make_setup_frame.py)")
        frame = (fdir / f"{name}.png", json.loads((fdir / f"{name}.json").read_text(encoding="utf-8")))
        clip.setdefault("layout", "setup")
        oled = float(clip.get("oled", 1.0))
        for b in beats:
            b["_screen"], b["_quad"], b["_oled"] = frame[1]["screen"], frame[1].get("quad"), oled
    parts, t, starts = [], 0.0, []
    for b in beats:                              # layout "stack": the clip's facecam rect unless a beat sets its own
        if clip.get("cam") and "cam" not in b:
            b["cam"] = clip["cam"]
        if clip.get("blur_cam") and "blur_cam" not in b:
            b["blur_cam"] = clip["blur_cam"]
    for i, b in enumerate(beats):
        if i and "_center" in beats[i - 1]:      # stay on the same person when it's unclear who is talking
            b.setdefault("_hint", beats[i - 1]["_center"])
            b.setdefault("_prev", beats[i - 1].get("_speaker"))
        p, d = render_beat(tmp, i, b, clip.get("layout", "full"), srcdir)
        parts.append(p)
        starts.append(t)
        t += d
    total = t
    lst = tmp / "list.txt"
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    joined = tmp / "joined.mov"
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", joined])

    # overlays: [png, t0, t1]
    ovs, caps = [], []
    hu = clip.get("hook_until", "end" if frame else min(3.5, max(1.8, starts[1] if len(starts) > 1 else 2.5)))
    hook_until = total + 1 if hu == "end" else float(hu)
    if frame:   # reference style: two calm lines above the monitor, on screen for the whole clip
        hook_png(tmp / "hook.png", clip.get("hook", ""), clip.get("brand"),
                 y=int(clip.get("hook_y", frame[1].get("text_top", frame[1]["screen"][1] - 230))),
                 size=int(clip.get("hook_size", 58)))
    elif clip.get("layout") == "stack" and clip.get("cam"):   # hook on the seam between facecam and game
        sw0, sh0, _ = probe(srcdir / f"{beats[0]['src']}.mp4")
        seam = stack_geometry(sw0, sh0, clip["cam"])["seam"]
        hook_png(tmp / "hook.png", clip.get("hook", ""), clip.get("brand"), y=seam - 60)
    else:
        hook_png(tmp / "hook.png", clip.get("hook", ""), clip.get("brand"), y=int(clip.get("hook_y", 310)))
    ovs.append((tmp / "hook.png", 0.0, hook_until))
    cta_secs = float(clip.get("cta_secs", 2.0)) if clip.get("cta") else 0.0
    if clip.get("brand"):
        overlay_png(tmp / "brand.png", lambda d, img: _pill(d, clip["brand"]))
        ovs.append((tmp / "brand.png", hook_until, total))
    for i, b in enumerate(beats):
        b0, b1 = starts[i], starts[i] + (starts[i + 1] - starts[i] if i + 1 < len(starts) else total - starts[i])
        if b.get("label"):
            p = tmp / f"label_{i}.png"
            label_png(p, b["label"], hexcol(b.get("label_color"), YELLOW))
            ovs.append((p, b0, b1))
        if b.get("text") and not b.get("words"):
            end = min(b1, total - cta_secs) if cta_secs else b1
            for p, a, z in caption_pngs(tmp, i, b["text"], max(0.3, end - b0)):
                caps.append((p, b0 + a, b0 + z))
        if b.get("words") and not b.get("text_only"):
            end = min(b1, total - cta_secs) if cta_secs else b1
            sp = max(0.5, min(2.0, float(b.get("speed", 1.0))))
            for p, a, z in timed_caption_pngs(tmp, i, b["words"], float(b["start"]), sp, max(0.1, end - b0)):
                caps.append((p, b0 + a, b0 + z))
    # Speech clips have 60-120 caption cards. One looped input per card makes ffmpeg crawl, so many cards go in as
    # ONE track (concat demuxer, a transparent card in the gaps); a handful stay as separate overlays as before.
    cap_track = None
    if len(caps) >= 16:
        overlay_png(tmp / "blank.png", lambda d, img: None, box=CAP_BAND)
        lines, t = [], 0.0
        for p, a, z in caps:
            if a - t > 0.01:
                lines.append(f"file '{(tmp / 'blank.png').as_posix()}'\nduration {a - t:.3f}\n")
            lines.append(f"file '{p.as_posix()}'\nduration {z - max(a, t):.3f}\n")
            t = z
        lines.append(f"file '{(tmp / 'blank.png').as_posix()}'\nduration {max(0.1, total - t + 0.5):.3f}\n")
        lines.append(f"file '{(tmp / 'blank.png').as_posix()}'\n")
        cap_track = tmp / "caps.txt"
        cap_track.write_text("".join(lines), encoding="utf-8")
    else:
        ovs += caps
    if cta_secs:
        cta_png(tmp / "cta.png", clip["cta"], frame[1]["screen"] if frame else None)
        ovs.append((tmp / "cta.png", total - cta_secs, total + 1))
    if clip.get("logo"):   # a brief's required logo overlay, visible for the whole clip (e.g. a streamer's logo)
        lg = clip["logo"] if isinstance(clip["logo"], dict) else {"path": clip["logo"]}
        im = Image.open(root / lg["path"]).convert("RGBA")
        lw = int(lg.get("width", 300))
        im = im.resize((lw, max(2, round(im.height * lw / im.width))), Image.LANCZOS)
        lp = tmp / "logo.png"
        im.save(lp)
        OFFS[str(lp)] = (int(lg.get("x", W - lw - 40)), int(lg.get("y", 240)))
        ovs.append((lp, 0.0, total + 1))

    inputs = ["-i", joined]
    fc, last, first = "", "0:v", 1
    if frame:   # dimmed room on top of the screen, plus a glow in the footage's own colours on bezel and desk
        room, mask = frame_layers(tmp, frame[0], frame[1], oled)
        inputs += ["-loop", "1", "-t", f"{total:.3f}", "-i", room, "-loop", "1", "-t", f"{total:.3f}", "-i", mask]
        bx, by, bw, bh = frame[1]["screen"]
        fc = (f"[0:v]format=gbrp,split=2[sv][gs];"
              f"[gs]crop={bw}:{bh}:{bx}:{by},scale=8:4:flags=area,scale={W}:{H}:flags=bicubic,tmix=frames=4[gc];"
              f"[2:v]format=gbrp[gm];[gc][gm]blend=all_mode=multiply[gl];"
              f"[sv][1:v]overlay=0:0:format=gbrp[rm];[rm][gl]blend=all_mode=addition[base];")
        last, first = "base", 3
    for p, _, _ in ovs:
        inputs += ["-loop", "1", "-t", f"{total:.3f}", "-i", p]
    for k, (p, a, z) in enumerate(ovs):
        px, py = OFFS.get(str(p), (0, 0))
        fc += f"[{last}][{k + first}:v]overlay={px}:{py}:enable='between(t,{a:.3f},{z:.3f})'[o{k}];"
        last = f"o{k}"
    j = len(ovs) + first
    if cap_track:
        inputs += ["-f", "concat", "-safe", "0", "-i", cap_track]
        fc += f"[{j}:v]format=rgba[capv];[{last}][capv]overlay={CAP_BAND[0]}:{CAP_BAND[1]}:eof_action=pass[ocap];"
        last = "ocap"
        j += 1
    # sound effects on the cuts
    sfx_inputs, amix = [], ["[0:a]volume=0.9[ga]"]
    labels = ["[ga]"]
    for i, b in enumerate(beats):
        name = b.get("sfx", "none")
        if name in SFX:
            sfx_inputs += ["-i", sfx_file(tmp, name)]
            lead = 1.1 if name == "riser" else 0.0
            ms = max(0, int((starts[i] - lead) * 1000))
            amix.append(f"[{j}:a]adelay={ms}|{ms}[s{j}]")
            labels.append(f"[s{j}]")
            j += 1
    fc += ";".join(amix) + ";" + "".join(labels) + f"amix=inputs={len(labels)}:normalize=0:duration=first," \
          f"alimiter=limit=0.95,afade=t=out:st={total - 0.3:.3f}:d=0.3[a]"
    out = root / "clips" / f"{clip['id']}.mp4"
    # Quality first, no size limit: constant-quality x264 (visually lossless at this size). Instagram and YouTube
    # re-encode every upload, so the cleaner the file we give them, the cleaner the result.
    # few filter threads: every looped overlay holds full 1080x1920 frames per thread (6 GB machine)
    common = ["ffmpeg", "-y", "-v", "error", "-filter_complex_threads", "2", *inputs, *sfx_inputs,
              "-filter_complex", fc, "-map", f"[{last}]", "-map", "[a]", "-t", f"{total:.3f}", "-threads", "4"]
    tail = ["-pix_fmt", "yuv420p", "-r", FPS, "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", out]
    crf = int(clip.get("crf", 15))
    x264 = ["-c:v", "libx264", "-preset", "slow", "-crf", str(crf), "-maxrate", "40000k", "-bufsize", "80000k",
            "-profile:v", "high", "-x264-params", "aq-mode=3:rc-lookahead=20"]
    # NVENC needs a little more bitrate than x264 for the same picture, so it gets a matching quality target and a
    # higher ceiling: the file is bigger, the picture is not worse. There is no size limit.
    nvenc = ["-c:v", "h264_nvenc", "-preset", "p7", "-tune", "hq", "-rc", "vbr", "-cq", str(crf + 1), "-b:v", "0",
             "-maxrate", "50000k", "-bufsize", "100000k", "-profile:v", "high", "-spatial-aq", "1", "-temporal-aq", "1",
             "-rc-lookahead", "20"]
    if not (gpu()["final"] and try_run([*common, *nvenc, *tail])):
        run([*common, *x264, *tail])
    size = out.stat().st_size / 1024 / 1024
    cover_t = float(clip.get("cover_at", min(1.2, hook_until - 0.3, total / 2)))
    run(["ffmpeg", "-y", "-v", "error", "-ss", cover_t, "-i", out, "-frames:v", 1, "-q:v", 2,
         root / "covers" / f"{clip['id']}.jpg"])
    on = f" on {frame[0].stem} (oled {oled:g})" if frame else ""
    print(f"made {out.name}: {total:.1f}s, {len(beats)} beats, {size:.1f} MB{on}")
    by = "claude" if out.stat().st_size <= CHROME_UPLOAD_BYTES else "manual"
    if by == "manual":
        print("   over 10 MB: Claude in Chrome can't upload it, so this one is scheduled by hand (quality kept)")
    sizes = root / "clips" / "sizes.json"
    try:
        data = json.loads(sizes.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        data = {}
    data[clip["id"]] = {"mb": round(size, 1), "seconds": round(total, 1), "upload": by}
    sizes.write_text(json.dumps(data, indent=1), encoding="utf-8")


def assign_channel_frames(root, clips):
    """Clips that name no frame and no other layout get the channel's frame (rules.json "channel" -> channels.json
    "frame"); every 5th of them gets a "frame_variants" entry instead, so a variant never follows a variant.
    A channel without a "frame" renders as before (no frame)."""
    rules = root / "rules.json"
    if not rules.exists():
        return
    cid = json.loads(rules.read_text(encoding="utf-8-sig")).get("channel")
    chans = json.loads((HERE.parent / "channels.json").read_text(encoding="utf-8-sig"))
    ch = next((c for c in chans if c.get("id") == cid), None)
    if not ch or not ch.get("frame"):
        return
    variants = ch.get("frame_variants") or []
    since, prev_var, used = 0, False, 0
    for i, c in enumerate(clips):    # edit.json order, so later batches continue the same rhythm
        if not c.get("frame") and c.get("layout", "setup") == "setup":
            nxt = clips[i + 1].get("frame") if i + 1 < len(clips) else None
            if variants and since >= 4 and not prev_var and nxt not in variants:
                c["frame"] = variants[used % len(variants)]
                used += 1
            else:
                c["frame"] = ch["frame"]
        prev_var = c.get("frame") in variants        # frames set by hand count too
        since = 0 if prev_var else since + 1


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    sys.path.insert(0, str(HERE))
    root = Path(sys.argv[1])
    if not root.exists():
        root = HERE.parent / "campaigns" / sys.argv[1]
    clips = json.loads((root / "edit.json").read_text(encoding="utf-8-sig"))
    assign_channel_frames(root, clips)
    want = sys.argv[2:]
    (root / "clips").mkdir(exist_ok=True)
    (root / "covers").mkdir(exist_ok=True)
    for clip in clips:
        if want and not any(clip["id"].startswith(w) for w in want):
            continue
        with tempfile.TemporaryDirectory() as td:
            build_clip(root, clip, Path(td))


if __name__ == "__main__":
    main()
