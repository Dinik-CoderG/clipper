r"""The learning loop: join each post's results with how the clip was made, and write the channel's playbook.

usage: learn.py add <channel> <pulled.json>     merge freshly pulled metrics into learn\<channel>\posts.json
       learn.py build <channel>                 write learn\<channel>\playbook.md and playbook.json

pulled.json (what Claude reads from Instagram Insights / YouTube Studio / Content Rewards), one row per post:
[{"platform": "instagram", "url": "https://www.instagram.com/reel/...", "posted_at": "2026-11-16 20:30",
  "caption": "first line...", "duration_s": 12.3,
  "views": 1840, "reach": 1500, "avg_watch_s": 6.1, "watch_pct": 49, "likes": 60, "comments": 4,
  "shares": 12, "saves": 3, "follows": 2, "skip_rate": null,          # YouTube: "swiped away" %
  "cr_views": 1800, "cr_status": "pending" | "paid" | "rejected" | null, "cr_earned": 0}]
Unknown = null. Rows are matched by url, so pulling again updates the numbers (keep the latest).

How a post is matched to its clip: campaigns\*\plan\posts.json of the same channel, by scheduled.json url if
present, else by date (+-1 day) and the start of the caption. The clip's edit.json entry gives the features:
length, beats, cuts per 10 s, layout, frame, hook pattern and length, labels, captions, plus any "tags" the
skills wrote on the clip (game, format, footage type, what was being tested).

The playbook never treats a handful of posts as proof: groups with fewer than 4 posts are listed as "too few
to tell", 4-7 as "early signal", 8+ as "solid".
"""
from __future__ import annotations

import json
import re
import statistics as st
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001
        return default


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", (s or "").lower())[:40].strip()


def hook_pattern(text: str) -> str:
    t = (text or "").lower().replace("*", "")
    if not t.strip():
        return "none"
    if t.startswith("pov"):
        return "pov"
    if re.search(r"\bvs\.?\b", t):
        return "x vs y"
    if re.search(r"\d+ (years?|hours?|days?) (later|ago|of)", t) or "years later" in t or "still" in t:
        return "years later / still"
    if "?" in t:
        return "question"
    if re.search(r"\b(forgot|can't believe|didn't expect|wait for it|watch till)\b", t):
        return "disbelief / wait for it"
    if re.search(r"\b(best|smoothest|most|peak|greatest|craziest)\b", t):
        return "superlative"
    if re.search(r"^(this|that|the|when|how)\b", t):
        return "statement"
    return "other"


def bucket_len(s):
    if s is None:
        return None
    return "under 10 s" if s < 10 else "10-15 s" if s < 15 else "15-25 s" if s < 25 else "25-40 s" if s < 40 else "40 s+"


def clip_features(channel: str) -> list[dict]:
    """Every planned post of this channel with the features of its clip."""
    out = []
    for folder in sorted((ROOT / "campaigns").iterdir()):
        if not folder.is_dir() or folder.name.startswith("_"):
            continue
        rules = load(folder / "rules.json", {})
        if rules.get("channel") not in (channel, None):
            continue
        edits = {c["id"]: c for c in load(folder / "edit.json", []) if isinstance(c, dict) and "id" in c}
        sched = {(r.get("id"), r.get("platform")): r for r in load(folder / "scheduled.json", [])}
        need = {}
        for p, v in (rules.get("platforms") or {}).items():
            if v and v.get("per_1k") and v.get("min_payout") is not None:
                need[p] = v["min_payout"] / v["per_1k"] * 1000
        for post in load(folder / "plan" / "posts.json", []):
            cid = Path(post.get("file", "")).stem
            e = edits.get(cid, {})
            beats = e.get("beats", [])
            length = sum((b["end"] - b["start"]) / max(0.5, min(2.0, b.get("speed", 1.0))) for b in beats) or None
            f = {"campaign": folder.name, "organic": bool(post.get("organic")) or folder.name.startswith("own_"),
                 "clip": cid, "date": post.get("date"), "time": post.get("time"), "caption": post.get("caption", ""),
                 "hook": e.get("hook") or post.get("hook", ""), "length_s": round(length, 1) if length else None,
                 "beats": len(beats) or None,
                 "cuts_per_10s": round((len(beats) - 1) / length * 10, 1) if length and beats else None,
                 "layout": e.get("layout"), "frame": e.get("frame"),
                 "labels": any(b.get("label") for b in beats), "captions": any(b.get("text") for b in beats),
                 "tags": e.get("tags") or post.get("tags") or {}, "views_to_get_paid": need,
                 "urls": {pl: (sched.get((post.get("id"), pl)) or {}).get("url") for pl in post.get("platforms", [])}}
            out.append(f)
    return out


def match(row: dict, feats: list[dict]):
    for f in feats:
        if row.get("url") and row["url"] in f["urls"].values():
            return f
    try:
        when = datetime.strptime(row["posted_at"][:10], "%Y-%m-%d")
    except Exception:  # noqa: BLE001
        return None
    cap = norm(row.get("caption", ""))
    for f in feats:
        try:
            d = datetime.strptime(f["date"], "%Y-%m-%d")
        except Exception:  # noqa: BLE001
            continue
        if abs(d - when) <= timedelta(days=1) and cap and (cap[:25] == norm(f["caption"])[:25]):
            return f
    return None


def cmd_add(channel: str, pulled: Path) -> None:
    store = ROOT / "learn" / channel / "posts.json"
    store.parent.mkdir(parents=True, exist_ok=True)
    rows = {r["url"]: r for r in load(store, []) if r.get("url")}
    new = 0
    for r in load(pulled, []):
        if not r.get("url"):
            continue
        new += r["url"] not in rows
        r["pulled_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        rows[r["url"]] = {**rows.get(r["url"], {}), **{k: v for k, v in r.items() if v is not None}}
    store.write_text(json.dumps(list(rows.values()), indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(rows)} posts stored for {channel} ({new} new)")


def med(xs):
    xs = [x for x in xs if x is not None]
    return st.median(xs) if xs else None


def cmd_build(channel: str) -> None:
    folder = ROOT / "learn" / channel
    rows = load(folder / "posts.json", [])
    if not rows:
        sys.exit(f"no metrics for {channel} yet: pull them first (channel-review skill)")
    feats = clip_features(channel)
    posts = []
    for r in rows:
        f = match(r, feats) or {}
        views = r.get("views")
        hook = f.get("hook") or (r.get("caption") or "").split("\n")[0]
        length = f.get("length_s") or r.get("duration_s")
        hour = None
        try:
            hour = int(r["posted_at"][11:13])
        except Exception:  # noqa: BLE001
            pass
        need = (f.get("views_to_get_paid") or {}).get(r.get("platform"))
        p = {"url": r.get("url"), "platform": r.get("platform"), "posted_at": r.get("posted_at"), "views": views,
             "watch_pct": r.get("watch_pct") or (round(100 * r["avg_watch_s"] / length, 1)
                                                 if r.get("avg_watch_s") and length else None),
             "shares_per_1k": round(1000 * r["shares"] / views, 1) if views and r.get("shares") is not None else None,
             "engagement_pct": round(100 * ((r.get("likes") or 0) + (r.get("comments") or 0)) / views, 2) if views else None,
             "follows": r.get("follows"), "paid_line": need,
             "reached_paid_line": (views >= need) if (views is not None and need) else None,
             "cr_status": r.get("cr_status"), "matched": bool(f), "hook": hook,
             "f": {"type": ("organic" if f.get("organic") else "campaign") if f else "unknown",
                   "campaign": f.get("campaign"), "hook pattern": hook_pattern(hook),
                   "hook words": None if not hook else ("up to 6" if len(hook.split()) <= 6 else "7-10" if len(hook.split()) <= 10 else "11+"),
                   "length": bucket_len(length),
                   "cuts": None if f.get("cuts_per_10s") is None else ("static (under 2 per 10 s)" if f["cuts_per_10s"] < 2 else "2-5 per 10 s" if f["cuts_per_10s"] < 5 else "5+ per 10 s"),
                   "layout": f.get("layout"), "frame": f.get("frame"),
                   "labels": f.get("labels") if f else None, "captions on screen": f.get("captions") if f else None,
                   "post hour (IST)": None if hour is None else f"{hour:02d}:00",
                   "platform": r.get("platform"), **{f"tag: {k}": v for k, v in (f.get("tags") or {}).items()}}}
        posts.append(p)

    base = {pl: med([p["views"] for p in posts if p["platform"] == pl]) for pl in {p["platform"] for p in posts}}
    for p in posts:
        b = base.get(p["platform"])
        p["x_usual"] = round(p["views"] / b, 2) if p["views"] is not None and b else None

    groups = {}
    for p in posts:
        for k, v in p["f"].items():
            if v is None:
                continue
            groups.setdefault((k, str(v)), []).append(p)
    table = []
    for (k, v), ps in groups.items():
        n = len(ps)
        table.append({"feature": k, "value": v, "n": n, "x_usual": med([p["x_usual"] for p in ps]),
                      "watch_pct": med([p["watch_pct"] for p in ps]), "shares_per_1k": med([p["shares_per_1k"] for p in ps]),
                      "confidence": "solid" if n >= 8 else "early signal" if n >= 4 else "too few to tell"})
    usable = [t for t in table if t["n"] >= 4 and t["x_usual"] is not None]
    keep = sorted([t for t in usable if t["x_usual"] >= 1.3], key=lambda t: -t["x_usual"])
    drop = sorted([t for t in usable if t["x_usual"] <= 0.6], key=lambda t: t["x_usual"])
    few = sorted([t for t in table if t["n"] < 4], key=lambda t: (t["feature"], t["value"]))
    top = sorted([p for p in posts if p["x_usual"] is not None], key=lambda p: -p["x_usual"])
    paid = [p for p in posts if p["reached_paid_line"] is not None]

    def fmt(x, suffix=""):
        return "-" if x is None else f"{x:g}{suffix}"

    L = [f"# Playbook: {channel}", "",
         f"Built {datetime.now():%Y-%m-%d %H:%M} from {len(posts)} posts ({sum(p['matched'] for p in posts)} matched to their "
         "clip recipe). x usual = views compared with this channel's median on that platform.", ""]
    if len(posts) < 10:
        L += [f"**Only {len(posts)} posts: treat everything below as hints, not rules.**", ""]
    L += ["## Where the channel stands",
          *[f"- {pl}: median {base[pl]:,.0f} views per post" for pl in base if base[pl] is not None],
          f"- median watched: {fmt(med([p['watch_pct'] for p in posts]), '%')} of the clip · "
          f"shares per 1,000 views: {fmt(med([p['shares_per_1k'] for p in posts]))} · "
          f"likes+comments: {fmt(med([p['engagement_pct'] for p in posts]), '%')}"]
    if paid:
        L.append(f"- campaign clips that reached their payout line: {sum(p['reached_paid_line'] for p in paid)} of {len(paid)}")
    L += ["", "## Do more of this (4+ posts, clearly above usual)"]
    L += [f"- **{t['feature']} = {t['value']}**: {t['x_usual']:g}x usual over {t['n']} posts ({t['confidence']}); "
          f"watched {fmt(t['watch_pct'], '%')}, shares/1K {fmt(t['shares_per_1k'])}" for t in keep] or ["- nothing proven yet"]
    L += ["", "## Stop or change (4+ posts, clearly below usual)"]
    L += [f"- **{t['feature']} = {t['value']}**: {t['x_usual']:g}x usual over {t['n']} posts ({t['confidence']})" for t in drop] or ["- nothing proven yet"]
    L += ["", "## Best posts and what they had"]
    for p in top[:5]:
        f = p["f"]
        L.append(f"- {p['x_usual']:g}x ({p['views']:,} views, watched {fmt(p['watch_pct'], '%')}, shares/1K {fmt(p['shares_per_1k'])}): "
                 f"\"{p['hook'][:70]}\" · {f.get('hook pattern')} · {f.get('length') or '?'} · {f.get('cuts') or '?'} · "
                 f"{f.get('post hour (IST)') or '?'} · {p['url']}")
    L += ["", "## Worst posts"]
    for p in top[-3:][::-1] if len(top) > 5 else []:
        f = p["f"]
        L.append(f"- {p['x_usual']:g}x ({p['views']:,} views): \"{p['hook'][:70]}\" · {f.get('hook pattern')} · "
                 f"{f.get('length') or '?'} · {f.get('cuts') or '?'}")
    L += ["", "## Not tested enough (fewer than 4 posts): candidates for the next tests"]
    L += [f"- {t['feature']} = {t['value']} ({t['n']} posts, {fmt(t['x_usual'])}x so far)" for t in few[:25]] or ["- none"]
    L += ["", "## How the skills must use this",
          "- About 70% of the next batch follows \"Do more\"; about 30% are tests that change ONE thing from a proven clip",
          "  (hook pattern, length, cut speed, post hour, frame variant). Write what each test changes in the clip's `tags`.",
          "- Never repeat anything under \"Stop or change\" without changing the thing that failed.",
          "- Watch time and shares outrank raw views when they disagree: Instagram and YouTube rank on them."]
    (folder / "playbook.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (folder / "playbook.json").write_text(json.dumps({"built": datetime.now().isoformat(timespec="minutes"),
                                                      "posts": posts, "groups": table, "keep": keep, "drop": drop},
                                                     indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print("\n".join(L))


def main() -> None:
    a = sys.argv[1:]
    if len(a) >= 3 and a[0] == "add":
        cmd_add(a[1], Path(a[2]))
    elif len(a) >= 2 and a[0] == "build":
        cmd_build(a[1])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
