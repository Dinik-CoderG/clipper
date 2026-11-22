"""Find the moments in a campaign's footage most likely to hold viewers and get rewatched and shared.

usage: find_moments.py <campaign> [options]
  --sources a,b        only these source files (names without .mp4); default: all in source/
  --min 7 --max 15     clip length range in seconds (default 7-15)
  --top 15             how many moments to output (default 15)
  --per-source 3       max moments from one source file (default 3)
  --heatmap URL[@offset]  YouTube upload of the same footage: use its "Most replayed" data.
                       offset = seconds to add to the YouTube time to get the source time (default 0).
                       Only applies with --sources naming exactly one file, or when there is one source.
  --keep-violence      keep windows with blood-like red flashes (default: drop any window that contains a sudden
                       red flash, because Instagram doesn't recommend violent content to non-followers; steady red
                       scenery like lava or sunsets is not dropped. Every pick is still checked by eye)
  --claude             have Claude review the top candidates' frame strips (needs ANTHROPIC_API_KEY)

Writes into <campaign>/analysis/:
  moments.json         ranked moments with scores, reasons and flags
  moments.md           the same as a readable table
  moments/NN_*.jpg     4-frame strip per moment (start, +1s, middle, end) for a quick visual check
  clips_draft.json     the moments in clips.json format (hooks left for you to write); clips.json is never touched

What it scores, mapped to what the platforms say officially:
  Instagram (Mosseri, 2025): the top ranking signals are watch time, likes and sends; sends matter most for
    reaching non-followers. Instagram for Creators: hook viewers in the first 3 seconds; reuploads, unoriginal
    content, watermarks, blur/low quality, borders, text covering most of the screen, over 3 minutes and violent
    content are not recommended to non-followers.
  YouTube (Shorts product lead, 2023): "the audience is the algorithm"; views count only when people choose to
    watch; no ideal length, so tell a complete moment; viewed-vs-swiped-away shows whether the opening works.
  So: hook = intensity in the first 1.5 s (watch time / viewed-vs-swiped), retention = no dead stretches,
  payoff = a peak near the end (complete moment, worth sending), loop = last frame resembles the first (rewatch),
  change = the end looks different from the start (a visible before -> after), replay = YouTube "Most replayed"
  when available. Dark or low-contrast windows lose up to 60% of their score: what can't be seen on a phone gets
  swiped. Recommendation gates (violence, length, low resolution) are
  checks, not scores. These are proxies built from the footage, not predictions: real results decide.
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))  # scripts here run with python -P
import campaign  # noqa: E402

FPS = 4                 # analysis frames per second
SW, SH = 160, 90        # analysis frame size
AUDIO_SR = 8000
HOOK_S = 1.5            # the opening that decides swipe-or-watch
TAG_WORDS = {"wow", "satisfying", "chaotic", "insane", "reveal", "epic", "funny", "charming", "crazy", "boss", "fail"}
HOOK_WORDS = re.compile(
    r"\b(never|nobody|everyone|biggest|worst|best|insane|crazy|secret|wait|look|watch|what|how|why|no way|oh my|"
    r"finally|new|first|last|reveal|wow)\b", re.I)
WEIGHTS = {"hook": 0.27, "retention": 0.22, "payoff": 0.13, "change": 0.13, "loop": 0.05, "replay": 0.20}
DARK_LUMA = 60          # mean brightness (0-255) below this reads as a black screen on a phone
FLAT_CONTRAST = 28      # luma std below this = washed-out / foggy / empty picture


# ---------- feature extraction ----------

def probe(src: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height:format=duration", "-of", "json", str(src)],
                         capture_output=True, text=True, check=True).stdout
    j = json.loads(out)
    s = j["streams"][0]
    return {"w": int(s["width"]), "h": int(s["height"]), "duration": float(j["format"]["duration"])}


def video_features(src: Path) -> dict:
    """Per analysis frame: motion, scene-cut, blood-like red share, plus a colour histogram for loop matching."""
    proc = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(src),
                             "-vf", f"fps={FPS},scale={SW}:{SH}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                            stdout=subprocess.PIPE)
    size = SW * SH * 3
    motion, cut, red, hists, luma, contrast, sat = [], [], [], [], [], [], []
    prev_g, prev_h = None, None
    while True:
        buf = proc.stdout.read(size)
        if len(buf) < size:
            break
        a = np.frombuffer(buf, np.uint8).reshape(SH, SW, 3).astype(np.int32)  # int32: 255*587 overflows int16
        g = (a[..., 0] * 299 + a[..., 1] * 587 + a[..., 2] * 114) // 1000
        h = np.concatenate([np.histogram(a[..., c], bins=16, range=(0, 256))[0] for c in range(3)]).astype(np.float32)
        h /= h.sum() + 1e-9
        r, gr, b = a[..., 0], a[..., 1], a[..., 2]
        red.append(float(((r > 120) & (r > gr * 2) & (r > b * 2)).mean()))
        luma.append(float(g.mean()))
        contrast.append(float(g.std()))
        sat.append(float((a.max(axis=2) - a.min(axis=2)).mean()))
        if prev_g is None:
            motion.append(0.0)
            cut.append(0.0)
        else:
            motion.append(float(np.abs(g - prev_g).mean()))
            cut.append(float(0.5 * np.abs(h - prev_h).sum()))  # 0 = same picture, 1 = totally different
        prev_g, prev_h = g, h
        hists.append(h)
    proc.wait()
    return {"motion": np.array(motion), "cut": np.array(cut), "red": np.array(red), "hist": np.array(hists),
            "luma": np.array(luma), "contrast": np.array(contrast), "sat": np.array(sat)}


def audio_loudness(src: Path, n: int) -> np.ndarray:
    """RMS loudness (dB) per analysis frame; zeros if the file has no audio."""
    proc = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(src), "-vn", "-ac", "1",
                           "-ar", str(AUDIO_SR), "-f", "s16le", "-"], capture_output=True)
    x = np.frombuffer(proc.stdout, np.int16).astype(np.float32) / 32768.0
    hop = AUDIO_SR // FPS
    if len(x) < hop:
        return np.zeros(n)
    m = len(x) // hop
    rms = np.sqrt((x[: m * hop].reshape(m, hop) ** 2).mean(axis=1) + 1e-9)
    db = 20 * np.log10(rms)
    out = np.full(n, db.min() if len(db) else 0.0)
    out[: min(n, m)] = db[:n]
    return out


def rank01(x: np.ndarray) -> np.ndarray:
    """Percentile rank in 0..1, so every feature is on the same scale whatever the footage."""
    if len(x) == 0:
        return x
    order = x.argsort(kind="stable")
    r = np.empty(len(x))
    r[order] = np.arange(len(x))
    return r / max(len(x) - 1, 1)


def transcript_words(analysis: Path, name: str) -> list[tuple[float, float, str]]:
    p = analysis / name / "transcript.json"
    if not p.exists():
        return []
    rows = json.loads(p.read_text(encoding="utf-8"))
    return [(a, b, w) for r in rows for a, b, w in r.get("words", [])]


def replay_curve(spec: str, n: int, duration: float) -> np.ndarray | None:
    """YouTube 'Most replayed' values per analysis frame, via yt-dlp. None if unavailable."""
    url, _, off = spec.partition("@")
    offset = float(off or 0)
    try:
        import yt_dlp
        with yt_dlp.YoutubeDL({"quiet": True, "skip_download": True, "no_warnings": True}) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:  # noqa: BLE001
        print(f"   heatmap: could not read {url}: {e}")
        return None
    hm = info.get("heatmap") or []
    if not hm:
        print("   heatmap: YouTube shows no 'Most replayed' data for this video (too new or too few views)")
        return None
    curve = np.zeros(n)
    t = np.arange(n) / FPS
    for seg in hm:
        a, b = seg["start_time"] + offset, seg["end_time"] + offset
        curve[(t >= a) & (t < b)] = seg["value"]
    print(f"   heatmap: {len(hm)} segments loaded")
    return curve


# ---------- window scoring ----------

def score_source(name: str, src: Path, analysis: Path, args, heatmap_spec: str | None) -> tuple[list[dict], dict]:
    meta = probe(src)
    vf = video_features(src)
    n = len(vf["motion"])
    if n < args.min * FPS:
        return [], meta
    loud = audio_loudness(src, n)
    onset = np.maximum(np.diff(loud, prepend=loud[0]), 0)
    cutflag = vf["cut"] > 0.35
    # how much is happening on screen and in the sound at each moment
    intensity = (0.40 * rank01(vf["motion"]) + 0.25 * rank01(loud) + 0.15 * rank01(onset)
                 + 0.20 * rank01(np.convolve(vf["cut"], np.ones(FPS) / FPS, mode="same")))
    # blood shows up as a sudden red flash; lava, sunsets and red worlds stay on screen. So compare each frame
    # with the red level around it (+-3 s) and flag only jumps. Still checked by eye before anything is used.
    red = vf["red"]
    k = 3 * FPS
    base = np.array([np.median(red[max(0, i - k):i + k + 1]) for i in range(len(red))])
    violent = (red - base > 0.004) & (red - base < 0.30)
    replay = replay_curve(heatmap_spec, n, meta["duration"]) if heatmap_spec else None
    if replay is not None and replay.max() > 0:
        replay = replay / replay.max()
    words = transcript_words(analysis, name)
    tags = sorted(TAG_WORDS & set(re.split(r"[_\-\s.]+", name.lower())))
    dead_thr = np.percentile(intensity, 25)

    lengths = range(int(args.min), int(args.max) + 1)
    hook_n = int(HOOK_S * FPS)
    cands = []
    for s in range(0, n - int(args.min * FPS), FPS // 2):          # start every 0.5 s
        if violent[s:s + int(args.min * FPS)].any() and not args.keep_violence:
            continue
        hook = float(intensity[s:s + hook_n].mean() * 0.7 + intensity[s:s + 3 * FPS].mean() * 0.3)
        best = None
        for L in lengths:
            e = s + L * FPS
            if e > n:
                break
            win = intensity[s:e]
            blocks = win[: (len(win) // FPS) * FPS].reshape(-1, FPS).mean(axis=1)
            dead = float((blocks < dead_thr).mean())
            retention = float(win.mean() * (1 - dead))
            tail = win[int(len(win) * 0.6):]
            payoff = float(min(1.0, tail.max() / (win.mean() + 1e-6) * 0.5))
            h0, h1 = vf["hist"][s], vf["hist"][e - 1]
            loop = float(1 - 0.5 * np.abs(h0 - h1).sum())
            # visible transformation: the picture at the end differs from the start (before -> after = payoff)
            a0 = vf["hist"][s:s + FPS].mean(axis=0)
            a1 = vf["hist"][e - FPS:e].mean(axis=0)
            change = float(min(1.0, 0.5 * np.abs(a0 - a1).sum() * 1.6))
            parts = {"hook": hook, "retention": retention, "payoff": payoff, "change": change, "loop": loop}
            if replay is not None:
                parts["replay"] = float(replay[s:e].mean())
            w = {k: WEIGHTS[k] for k in parts}
            score = sum(parts[k] * w[k] for k in parts) / sum(w.values())
            score *= 1 + 0.03 * (args.max - L) / max(args.max - args.min, 1)   # slight edge to shorter clips
            # readable on a phone: dark or flat windows lose most of their score (people swipe what they can't see)
            lum, con = float(vf["luma"][s:e].mean()), float(vf["contrast"][s:e].mean())
            vis = min(1.0, lum / DARK_LUMA) * min(1.0, con / FLAT_CONTRAST)
            score *= 0.4 + 0.6 * vis
            parts["visibility"] = round(vis, 3)
            if violent[s:e].any() and not args.keep_violence:
                break
            if best is None or score > best["score"]:
                best = {"start": s / FPS, "end": e / FPS, "score": score, "parts": parts, "dead": dead,
                        "dark": lum < DARK_LUMA, "brightness": round(lum, 1), "colour": round(float(vf["sat"][s:e].mean()), 1),
                        "violent": bool(violent[s:e].any())}
        if not best:
            continue
        # snap the start onto a scene cut within 1 s, so the clip opens on a clean shot
        lo, hi = max(0, s - FPS), min(n, s + FPS)
        cuts_near = np.nonzero(cutflag[lo:hi])[0]
        if len(cuts_near):
            shift = (lo + cuts_near[np.argmin(np.abs(lo + cuts_near - s))] - s) / FPS
            best["start"] = round(max(0.0, best["start"] + shift), 2)
            best["end"] = round(best["end"] + shift, 2)
        spoken = " ".join(w for a, b, w in words if best["start"] <= a < best["start"] + 3)
        if spoken and HOOK_WORDS.search(spoken):
            best["score"] *= 1.05
            best["hook_line"] = spoken
        if tags:
            best["score"] *= 1.05
        best.update(source=name, tags=tags, peak=float((s + int(np.argmax(intensity[s:int(best['end'] * FPS)]))) / FPS))
        cands.append(best)
    return cands, meta


def pick(cands: list[dict], top: int, per_source: int) -> list[dict]:
    """Best first, no overlapping windows, at most per_source from one file."""
    chosen, count = [], {}
    for c in sorted(cands, key=lambda c: c["score"], reverse=True):
        if count.get(c["source"], 0) >= per_source:
            continue
        if any(o["source"] == c["source"] and min(o["end"], c["end"]) - max(o["start"], c["start"]) > 0
               for o in chosen):
            continue
        chosen.append(c)
        count[c["source"]] = count.get(c["source"], 0) + 1
        if len(chosen) >= top:
            break
    return chosen


def reasons(c: dict) -> list[str]:
    p, out = c["parts"], []
    if p["hook"] >= 0.65:
        out.append("strong opening (busy first 1.5 s)")
    elif p["hook"] < 0.45:
        out.append("weak opening: consider a hook text or a later start")
    if c["dead"] == 0:
        out.append("no dead stretch")
    elif c["dead"] > 0.25:
        out.append(f"{int(c['dead'] * 100)}% of seconds are quiet")
    if p["payoff"] >= 0.75:
        out.append("builds to a peak near the end")
    if p.get("change", 0) >= 0.6:
        out.append("big visible change from start to end (before/after payoff)")
    if c.get("dark"):
        out.append(f"DARK (brightness {c['brightness']}/255): hard to see on a phone, brighten or skip")
    elif p.get("visibility", 1) < 0.8:
        out.append("low contrast: looks flat on a phone")
    if p["loop"] >= 0.8:
        out.append("end looks like the start (loops well)")
    if p.get("replay", 0) >= 0.6:
        out.append("YouTube viewers replay this part")
    if c.get("hook_line"):
        out.append(f'opening line: "{c["hook_line"][:60]}"')
    if c["tags"]:
        out.append("brand tagged the file: " + ", ".join(c["tags"]))
    return out


# ---------- outputs ----------

def strip(src: Path, c: dict, dst: Path) -> None:
    times = [c["start"] + 0.1, c["start"] + 1.0, (c["start"] + c["end"]) / 2, c["end"] - 0.2]
    frames = []
    for t in times:
        raw = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", str(src),
                              "-frames:v", "1", "-vf", "scale=320:180", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True).stdout
        if len(raw) == 320 * 180 * 3:
            frames.append(np.frombuffer(raw, np.uint8).reshape(180, 320, 3))
    if not frames:
        return
    img = np.concatenate(frames, axis=1)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                    "-s", f"{img.shape[1]}x{img.shape[0]}", "-i", "-", "-frames:v", "1", str(dst)],
                   input=img.tobytes(), check=True)


CLAUDE_SCHEMA = {
    "type": "object",
    "properties": {"moments": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "rank": {"type": "integer"},
            "hook": {"type": "integer", "description": "0-10: would a stranger stop scrolling in the first second?"},
            "send": {"type": "integer", "description": "0-10: would someone send this to a friend?"},
            "payoff": {"type": "integer", "description": "0-10: does it land as a complete moment?"},
            "risk": {"type": "string", "description": "brief-rule or recommendation risk, or empty"},
            "hook_text": {"type": "string", "description": "on-screen hook, max 8 words, true to the clip"},
        },
        "required": ["rank", "hook", "send", "payoff", "risk", "hook_text"], "additionalProperties": False}}},
    "required": ["moments"], "additionalProperties": False,
}


def claude_review(root: Path, moments: list[dict], strips: Path) -> None:
    import os
    import anthropic
    rules = ""
    for p in [root / "rules.md", *sorted((root / "brief").glob("*.md"))]:
        if p.exists():
            rules += p.read_text(encoding="utf-8")[:6000] + "\n"
    content = [{"type": "text", "text": (
        "You review candidate moments for short vertical clips (Instagram Reels, YouTube Shorts) cut from a brand's "
        "campaign footage. Each image is 4 frames: start, +1 s, middle, end. Judge as the platforms rank: Instagram "
        "weights watch time, likes and sends (sends most for non-followers) and says to hook viewers in the first "
        "3 seconds; YouTube counts only intentional views and favours complete moments people choose to watch. "
        "Flag anything the campaign rules or recommendation guidelines would block (violence, misleading claims). "
        "Hook text must be true to what is shown, no rage bait, max 8 words.\n\n"
        f"Campaign rules:\n{rules or '(none saved)'}\n\nCandidates follow.")}]
    for i, m in enumerate(moments, 1):
        img = strips / f"{i:02d}_{m['source'][:40]}.jpg"
        if not img.exists():
            continue
        content.append({"type": "text", "text": f"rank {i}: {m['source']} {m['start']:.1f}-{m['end']:.1f}s, "
                                                 f"signals {json.dumps({k: round(v, 2) for k, v in m['parts'].items()})}"})
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                     "data": base64.b64encode(img.read_bytes()).decode()}})
    client = anthropic.Anthropic()
    with client.messages.stream(
        model=os.environ.get("CLIPPER_MODEL", "claude-opus-5-5"),
        max_tokens=8000,
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": CLAUDE_SCHEMA}},
        messages=[{"role": "user", "content": content}],
    ) as stream:
        resp = stream.get_final_message()
    if resp.stop_reason == "refusal":
        print("   Claude declined the review; keeping signal scores only")
        return
    text = next(b.text for b in resp.content if b.type == "text")
    for r in json.loads(text)["moments"]:
        if 1 <= r["rank"] <= len(moments):
            m = moments[r["rank"] - 1]
            m["claude"] = r
            m["score_signals"] = m["score"]
            m["score"] = 0.6 * m["score"] + 0.4 * (r["hook"] * 0.45 + r["send"] * 0.35 + r["payoff"] * 0.2) / 10
    moments.sort(key=lambda m: m["score"], reverse=True)


def main() -> None:
    root, rest = campaign.from_argv("find_moments.py <campaign> [options]")
    ap = argparse.ArgumentParser(prog="find_moments.py <campaign>")
    ap.add_argument("--sources", default="")
    ap.add_argument("--min", type=float, default=7)
    ap.add_argument("--max", type=float, default=15)
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--per-source", type=int, default=3)
    ap.add_argument("--heatmap", default="")
    ap.add_argument("--keep-violence", action="store_true")
    ap.add_argument("--claude", action="store_true")
    args = ap.parse_args(rest)
    if args.max > 180:
        sys.exit("--max over 180 s: Instagram does not recommend Reels over 3 minutes")

    src_dir, analysis = root / "source", root / "analysis"
    names = [s for s in args.sources.split(",") if s] or [p.stem for p in sorted(src_dir.glob("*.mp4"))]
    if not names:
        sys.exit(f"no .mp4 files in {src_dir}")
    if args.heatmap and len(names) != 1:
        sys.exit("--heatmap needs exactly one source (use --sources)")

    all_cands, metas = [], {}
    for name in names:
        print(f"== {name}", flush=True)
        cands, meta = score_source(name, src_dir / f"{name}.mp4", analysis, args, args.heatmap or None)
        metas[name] = meta
        all_cands += cands
        print(f"   {meta['duration']:.0f}s, {meta['w']}x{meta['h']}, {len(cands)} candidate windows", flush=True)

    moments = pick(all_cands, args.top, args.per_source)
    for m in moments:
        meta = metas[m["source"]]
        m["flags"] = []
        if min(meta["w"], meta["h"]) < 720:
            m["flags"].append(f"source is {meta['w']}x{meta['h']}: low resolution is not recommended")
        if m["violent"]:
            m["flags"].append("red flashes in the clip (blood, or just fire/lava/red objects): check against the brief")
        m["reasons"] = reasons(m)

    strips = analysis / "moments"
    strips.mkdir(parents=True, exist_ok=True)
    for old in strips.glob("*.jpg"):
        old.unlink()
    for i, m in enumerate(moments, 1):
        strip(src_dir / f"{m['source']}.mp4", m, strips / f"{i:02d}_{m['source'][:40]}.jpg")

    if args.claude:
        print("== Claude review", flush=True)
        claude_review(root, moments, strips)
        for old in strips.glob("*.jpg"):     # re-number strips after re-ranking
            old.unlink()
        for i, m in enumerate(moments, 1):
            strip(src_dir / f"{m['source']}.mp4", m, strips / f"{i:02d}_{m['source'][:40]}.jpg")

    for m in moments:
        m["score"] = round(m["score"], 3)
        m["parts"] = {k: round(v, 3) for k, v in m["parts"].items()}
    (analysis / "moments.json").write_text(json.dumps(moments, indent=1, ensure_ascii=False), encoding="utf-8")

    lines = ["| # | score | source | start-end | why | flags |", "|---|---|---|---|---|---|"]
    for i, m in enumerate(moments, 1):
        why = "; ".join(m["reasons"]) + (f"; Claude hook: {m['claude']['hook_text']}" if m.get("claude") else "")
        lines.append(f"| {i} | {m['score']:.2f} | {m['source']} | {m['start']:.1f}-{m['end']:.1f} | {why} | "
                     f"{'; '.join(m['flags'])} |")
    (analysis / "moments.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    draft = [{"id": f"{i:02d}_{re.sub(r'[^a-z0-9]+', '_', m['source'].lower())[:30].strip('_')}",
              "source": m["source"], "start": m["start"], "end": m["end"],
              "hook": m.get("claude", {}).get("hook_text") or "TODO write the hook",
              "cover": round(m["peak"], 2)} for i, m in enumerate(moments, 1)]
    no_transcript = set()
    for d in draft:   # word-by-word captions need analyze.py's transcript; render.py crashes without it
        if (analysis / d["source"] / "transcript.json").exists():
            d["captions"] = "whisper"
        else:
            no_transcript.add(d["source"])
    if no_transcript:
        print(f"note: no transcript for {len(no_transcript)} source(s), so their drafts have no captions. "
              "Run analyze.py first if they have speech.")
    (analysis / "clips_draft.json").write_text(json.dumps(draft, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n{len(moments)} moments -> {analysis / 'moments.md'}  (strips in {strips})")


if __name__ == "__main__":
    main()
