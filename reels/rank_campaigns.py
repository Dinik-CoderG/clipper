r"""Rank Content Rewards campaigns for one channel: niche fit, views needed to get paid, budget left, competition.

usage: rank_campaigns.py <channel> [found.json] [--top 5]
Reads   channels.json                      the user's channels (niche, platforms, what to avoid)
        discover\<channel>\found.json      campaigns Claude read from contentrewards.com (format below)
Writes  discover\<channel>\ranked.json and ranked.md, and prints the table.

found.json: [{
  "name": "Example Game - Clipping", "url": "https://contentrewards.com/c/campaigns/...",
  "tags": ["gaming", "vr"],                 # niche words from the campaign page
  "platforms": {"instagram": {"per_1k": 1.75, "min_payout": 5, "max_payout": 200}, "youtube": {...}},
  "budget_total": 2000, "budget_left": 1272, "clippers": 21,
  "footage": "google drive" | "mediasilo" | "none" | null,
  "joined": false,
  "requires": {"dedicated_account": false, "tier1_pct": 40, "countries": ["US"], "min_followers": 0,
               "bio_change": false, "submit_within_min": 30, "notes": "..."},
  "category": "gaming",                     # gaming | streamer | music | app | gambling | adult | crypto | other
  "local": {"slug": "example_game", "sources": 90, "sources_unused": 81, "posts_past": 3, "posts_upcoming": 0,
            "our_avg_views": 140, "our_best_views": 400, "submissions_left": null}   # joined campaigns only:
}]                                          # from campaign_status.py + the campaign's submissions page
Unknown values = null. The score only orders campaigns; the user picks.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALWAYS_AVOID = {"gambling", "adult", "crypto"}


def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def score(c: dict, ch: dict) -> dict:
    out = {"name": c.get("name"), "url": c.get("url"), "joined": bool(c.get("joined")), "why": [], "blockers": [],
           "warnings": []}
    req = c.get("requires") or {}
    shared = [p for p in (c.get("platforms") or {}) if p in ch["platforms"]]
    if not shared:
        out["blockers"].append("pays none of this channel's platforms")
    skip = [s.lower() for s in ch.get("skip_campaigns", [])]
    if any(s in (c.get("name") or "").lower() for s in skip) or (c.get("local") or {}).get("status") == "dropped":
        out["blockers"].append("dropped by the user: never suggest")
    cat = (c.get("category") or "").lower()
    if cat in ALWAYS_AVOID | {a.lower() for a in ch.get("avoid", [])}:
        out["blockers"].append(f"category '{cat}' is on the avoid list")
    tags = {t.lower() for t in c.get("tags") or []} | ({cat} if cat else set())
    niche = {t.lower() for t in ch.get("niche", [])}
    overlap = tags & niche
    if req.get("dedicated_account") and not overlap:
        out["blockers"].append("needs an account dedicated to a different niche")
    elif req.get("dedicated_account"):
        out["warnings"].append("wants a dedicated account: check the brief's bio/profile rules")
    if req.get("min_followers") and ch.get("followers") is not None and ch["followers"] < req["min_followers"]:
        out["blockers"].append(f"needs {req['min_followers']} followers")
    if req.get("tier1_pct"):
        have = ch.get("tier1_pct")
        if have is None:
            out["warnings"].append(f"needs {req['tier1_pct']}% Tier-1 audience (this channel's share is unknown)")
        elif have < req["tier1_pct"]:
            out["blockers"].append(f"needs {req['tier1_pct']}% Tier-1 audience, channel has {have}%")
    if req.get("countries"):
        out["warnings"].append("pays by viewer country: " + ", ".join(req["countries"]))
    if req.get("submit_within_min"):
        out["warnings"].append(f"link must be submitted within {req['submit_within_min']} min of posting: post only "
                               "when you can submit (at the laptop, or from your phone)")
    if req.get("bio_change"):
        out["warnings"].append("requires a bio/profile change")
    left = c.get("budget_left")
    if left is not None and left < 100:
        out["blockers"].append(f"only ${left:.0f} budget left")

    # views needed for one clip to get paid, on the best shared platform
    need = None
    for p in shared:
        pl = c["platforms"][p] or {}
        if pl.get("per_1k") and pl.get("min_payout") is not None:
            v = pl["min_payout"] / pl["per_1k"] * 1000
            if need is None or v < need[0]:
                need = (v, p, pl)
    s_niche = clamp(len(overlap) / max(1, min(2, len(niche)))) if niche else 0.5
    if need:
        s_need = clamp(1 - (math.log10(max(need[0], 300)) - math.log10(1000)) / (math.log10(15000) - math.log10(1000)))
        out["views_to_get_paid"] = round(need[0])
        out["best_platform"] = need[1]
        out["rate_per_1k"] = need[2]["per_1k"]
        out["min_payout"] = need[2]["min_payout"]
        out["why"].append(f"{round(need[0]):,} views pays out on {need[1]} (${need[2]['per_1k']}/1K, min ${need[2]['min_payout']})")
    else:
        s_need = 0.3
        out["warnings"].append("rate or min payout not shown")
    clippers = c.get("clippers")
    if left is not None:
        per = left / max(1, clippers or 1)
        s_budget = clamp(0.6 * clamp(math.log10(max(left, 100)) - 2, 0, 2) / 2 + 0.4 * clamp(per / 50))
        out["budget_left"] = left
        out["why"].append(f"${left:,.0f} left" + (f", {clippers} clippers (${per:,.0f} each)" if clippers else ""))
    else:
        s_budget = 0.3
    s_comp = 0.5 if clippers is None else clamp(1 - math.log10(max(clippers, 1)) / 3)
    foot = (c.get("footage") or "").lower()
    s_foot = 1.0 if "drive" in foot else (0.6 if foot and foot != "none" else 0.2)
    if overlap:
        out["why"].append("niche match: " + ", ".join(sorted(overlap)))
    if "drive" in foot:
        out["why"].append("footage on Google Drive (auto-download)")
    elif foot and foot != "none":
        out["warnings"].append(f"footage on {foot}: you may need to download it yourself")
    out["score"] = round(100 * (0.35 * s_niche + 0.30 * s_need + 0.20 * s_budget + 0.08 * s_comp + 0.07 * s_foot), 1)
    # an enrolled campaign that ran out of clips is still an option: a second batch needs no joining or download
    loc = c.get("local")
    out["action"] = "joined, not started: download + first batch" if c.get("joined") else "new: join + download"
    if loc:
        out["action"] = "continue: make another batch" if not loc.get("posts_upcoming") else "already running"
        unused, total = loc.get("sources_unused"), loc.get("sources")
        if loc.get("submissions_left") == 0:
            out["blockers"].append("no submissions left in this campaign")
        if unused:
            out["why"].append(f"already joined, {unused} of {total} footage files unused: new batch with no setup")
            out["score"] = round(min(100, out["score"] + 6), 1)
        elif total:
            out["warnings"].append("all footage files already used: only different scenes from the same files are "
                                   "left (never re-post the same cut)")
            out["score"] = round(out["score"] - 8, 1)
        avg, best = loc.get("our_avg_views"), loc.get("our_best_views")
        if avg is not None and need:
            if avg >= need[0]:
                out["why"].append(f"our clips here average {avg:,} views: above the payout line")
                out["score"] = round(min(100, out["score"] + 8), 1)
            elif best is not None and best >= need[0]:
                out["why"].append(f"our best clip here ({best:,} views) cleared the payout line")
            else:
                out["warnings"].append(f"our clips here average {avg:,} views, payout needs {round(need[0]):,}: "
                                       "more of the same won't pay; change the format or skip")
                out["score"] = round(out["score"] - 10, 1)
        if loc.get("posts_upcoming"):
            out["warnings"].append(f"{loc['posts_upcoming']} posts still scheduled for it")
    if out["blockers"]:
        out["score"] = 0.0
    return out


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    top = int(sys.argv[sys.argv.index("--top") + 1]) if "--top" in sys.argv else 5
    channels = json.loads((ROOT / "channels.json").read_text(encoding="utf-8-sig"))
    ch = next((c for c in channels if c["id"] == args[0]), None)
    if not ch:
        sys.exit(f"no channel '{args[0]}' in channels.json (have: {', '.join(c['id'] for c in channels)})")
    folder = ROOT / "discover" / ch["id"]
    found = Path(args[1]) if len(args) > 1 else folder / "found.json"
    rows = [score(c, ch) for c in json.loads(found.read_text(encoding="utf-8-sig"))]
    ok = sorted([r for r in rows if not r["blockers"]], key=lambda r: r["score"], reverse=True)
    bad = [r for r in rows if r["blockers"]]
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "ranked.json").write_text(json.dumps({"top": ok[:top], "rest": ok[top:], "excluded": bad}, indent=2,
                                                   ensure_ascii=False), encoding="utf-8")
    lines = [f"# Top campaigns for {ch['id']} ({', '.join(ch.get('niche', []))})", "",
             "| # | score | campaign | what to do | views to get paid | budget left | why | watch out |", "|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(ok[:top], 1):
        need = format(r["views_to_get_paid"], ",") if "views_to_get_paid" in r else "?"
        left = "$" + format(r["budget_left"], ",.0f") if "budget_left" in r else "?"
        lines.append(f"| {i} | {r['score']} | {r['name']}{' (joined)' if r['joined'] else ''} | {r['action']} | {need} | {left} | "
                     f"{'; '.join(r['why'])} | {'; '.join(r['warnings']) or '-'} |")
    if bad:
        lines += ["", "Excluded:"] + [f"- {r['name']}: {'; '.join(r['blockers'])}" for r in bad]
    (folder / "ranked.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
