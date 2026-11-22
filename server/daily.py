"""Daily run: fetch the top trending US YouTube videos, cut the best clips across all of them, file them by date.

Usage:  python daily.py [--videos 20] [--clips 50] [--date YYYY-MM-DD] [--force]
Output: clips/<date>/NN_<slug>.mp4 (+ .jpg), manifest.csv, manifest.json, run.log
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import shutil
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

import pipeline as p

ROOT = Path(__file__).resolve().parent.parent
CLIPS = ROOT / "clips"
WORK = ROOT / "jobs" / "_daily"
PER_VIDEO_CAP = 5  # keep the day's 50 spread across videos instead of 10 from one


def load_env() -> None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


def trending_us(n: int) -> list[dict]:
    """Most popular videos in the US via the YouTube Data API (chart=mostPopular)."""
    key = os.environ.get("YOUTUBE_API_KEY")
    if not key:
        raise SystemExit("YOUTUBE_API_KEY is not set. Add it to .env in the project folder (see README).")
    videos, page = [], None
    while len(videos) < n * 2:  # over-fetch: some get filtered (too long, live, no speech)
        q = {"part": "snippet,contentDetails,statistics", "chart": "mostPopular", "regionCode": "US",
             "maxResults": 50, "key": key}
        if page:
            q["pageToken"] = page
        with urllib.request.urlopen("https://www.googleapis.com/youtube/v3/videos?" + urllib.parse.urlencode(q), timeout=30) as r:
            data = json.load(r)
        for it in data.get("items", []):
            dur = _iso_duration(it["contentDetails"].get("duration", ""))
            if not dur or dur > p.MAX_DURATION_S or dur < 90 or it["snippet"].get("liveBroadcastContent") != "none":
                continue
            videos.append({
                "id": it["id"], "url": f"https://www.youtube.com/watch?v={it['id']}",
                "title": it["snippet"]["title"], "channel": it["snippet"]["channelTitle"],
                "views": int(it.get("statistics", {}).get("viewCount", 0)), "duration": dur,
            })
        page = data.get("nextPageToken")
        if not page:
            break
    return videos


def _iso_duration(s: str) -> int:
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s)
    if not m:
        return 0
    d, h, mi, se = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + se


def slug(s: str, n: int = 40) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:n].strip("-") or "clip"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--videos", type=int, default=20)
    ap.add_argument("--clips", type=int, default=50)
    ap.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    ap.add_argument("--force", action="store_true", help="rerun even if today's folder is complete")
    args = ap.parse_args()

    load_env()
    out = CLIPS / args.date
    out.mkdir(parents=True, exist_ok=True)
    if (out / "manifest.json").exists() and not args.force:
        print(f"{out} already complete; use --force to redo")
        return 0
    lock = out / ".running"
    if lock.exists():
        print(f"another run is in progress ({lock}); delete it if that run crashed")
        return 1
    lock.write_text(str(os.getpid()))

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                        handlers=[logging.FileHandler(out / "run.log", encoding="utf-8"), logging.StreamHandler(sys.stdout)])
    log = logging.info
    last = {"msg": ""}

    def progress(stage: str, frac: float, msg: str) -> None:
        if stage != "download" and msg != last["msg"] and (frac in (0, 1) or stage == "moments"):
            log(f"  [{stage}] {msg}")
        last["msg"] = msg

    try:
        videos = trending_us(args.videos)
        log(f"Fetched {len(videos)} candidate trending videos (US)")
        candidates = []  # (moment, video, src, segments)
        used = 0
        for v in videos:
            if used >= args.videos:
                break
            vdir = WORK / v["id"]
            vdir.mkdir(parents=True, exist_ok=True)
            log(f"[{used + 1}/{args.videos}] {v['title']} — {v['channel']} ({v['duration'] // 60} min)")
            try:
                src, _ = p.download(v["url"], vdir, progress)
                segments, lang = p.transcribe(src, vdir, v["duration"], progress)
                moments = p.pick_moments(segments, v["duration"], PER_VIDEO_CAP, progress)
            except Exception as e:
                log(f"  skipped: {e}")
                shutil.rmtree(vdir, ignore_errors=True)
                continue
            used += 1
            v["language"] = lang
            candidates += [(m, v, src, segments) for m in moments]

        # best clips across all videos; every video gets its top clip first, then fill by score
        candidates.sort(key=lambda c: -c[0].score)
        chosen, seen = [], set()
        for c in candidates:
            if c[1]["id"] not in seen:
                chosen.append(c)
                seen.add(c[1]["id"])
        chosen = chosen[:args.clips]
        picked = {id(c) for c in chosen}
        chosen += [c for c in candidates if id(c) not in picked][: args.clips - len(chosen)]
        chosen.sort(key=lambda c: -c[0].score)
        log(f"Rendering {len(chosen)} clips from {len(seen)} videos")

        rows = []
        for rank, (m, v, src, segments) in enumerate(chosen, 1):
            try:
                info = p.render_clip(src, src.parent, rank, m, segments, True, {})
            except Exception as e:
                log(f"  clip {rank} failed: {e}")
                continue
            name = f"{rank:02d}_{slug(v['channel'], 20)}_{slug(m.title)}"
            shutil.move(src.parent / info["video"], out / f"{name}.mp4")
            shutil.move(src.parent / info["thumb"], out / f"{name}.jpg")
            rows.append({
                "rank": rank, "file": f"{name}.mp4", "score": m.score, "clip_title": m.title,
                "duration_s": info["duration"], "source_title": v["title"], "channel": v["channel"],
                "source_url": f"{v['url']}&t={int(m.start)}s", "start_s": m.start, "end_s": m.end,
                "views": v["views"], "transcript": info["transcript"], "uploaded": "",
            })
            log(f"  {rank:02d} [{m.score}] {m.title}")

        with open(out / "manifest.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["rank"])
            w.writeheader()
            w.writerows(rows)
        (out / "manifest.json").write_text(json.dumps({"date": args.date, "clips": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
        log(f"Done: {len(rows)} clips in {out}")
        return 0
    finally:
        shutil.rmtree(WORK, ignore_errors=True)
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
