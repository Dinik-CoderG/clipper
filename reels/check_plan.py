"""Check a campaign's posting plan against its rules, then export the schedule.

usage: check_plan.py <campaign> [--test-reminder]
  --test-reminder  write reminder_test.ics with one alert 10 min from now (check your phone alerts first)

Reads   <campaign>/rules.json   (the brief as data; see campaigns/_template/rules.json)
        <campaign>/plan/posts.json  (one entry per post; see campaigns/_template/plan/posts.json)
Prints  PASS / WARN / FAIL per post. Exit code 1 if anything FAILs.
Writes  <campaign>/schedule.csv  every post with time, files, caption, keep-live date (for Meta Business Suite /
                                 YouTube Studio, or for Claude to work through)
        <campaign>/schedule.ics  phone calendar reminders: post time, "submit link" 5 min later, keep-live end
Times in posts.json are India Standard Time.
"""
from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))  # scripts here run with python -P
import campaign  # noqa: E402

IST = timezone(timedelta(hours=5, minutes=30))
HASHTAG = re.compile(r"(?<!\w)#\w+")
IG_MAX_HASHTAGS = 5          # Instagram's limit since Dec 2025
IG_MAX_SECONDS = 180         # Instagram doesn't recommend Reels over 3 minutes
YT_TITLE_MAX = 100           # YouTube's hard limit; ~40 chars show in the Shorts feed
SAFE_POSTS_PER_DAY = 3       # per platform: steady, human-looking volume
SAFE_GAP_MIN = 120           # minutes between two posts on the same platform
VIOLENT_WORDS = ["kill", "kills", "killed", "killing", "murder", "dead", "death", "blood", "bloody", "shoot",
                 "shooting", "headshot", "execute", "execution", "massacre", "gore", "stab", "slaughter"]


def duration(path: Path) -> float | None:
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                              str(path)], capture_output=True, text=True, check=True).stdout
        return float(out.strip())
    except Exception:  # noqa: BLE001
        return None


def check_post(p: dict, rules: dict, root: Path) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    fail = lambda m: out.append(("FAIL", m))  # noqa: E731
    warn = lambda m: out.append(("WARN", m))  # noqa: E731

    clip = root / p["file"]
    if not clip.exists():
        fail(f"clip file missing: {p['file']}")
    else:
        d = duration(clip)
        lo, hi = rules.get("length", {}).get("min"), rules.get("length", {}).get("max")
        if d is None:
            warn("could not read clip length (ffprobe)")
        else:
            if d > IG_MAX_SECONDS:
                fail(f"clip is {d:.0f}s: over 3 minutes is not recommended on Instagram")
            if lo and d < lo:
                fail(f"clip is {d:.1f}s, brief minimum is {lo}s")
            if hi and d > hi:
                fail(f"clip is {d:.1f}s, brief maximum is {hi}s")
    if p.get("cover") and not (root / p["cover"]).exists():
        fail(f"cover missing: {p['cover']}")

    platforms = p.get("platforms", ["instagram"])
    cap = p.get("caption", "")
    text = "\n".join([cap, p.get("hook", ""), p.get("title", ""), p.get("yt_title", "")])
    tags = HASHTAG.findall(cap)
    plain = text
    for name in rules.get("allowed_names", []):   # official names from the brief, e.g. a map called "Kill Block"
        plain = re.sub(re.escape(name), " ", plain, flags=re.I)
    for word in VIOLENT_WORDS:
        if re.search(rf"\b{word}\b", plain, re.I):
            warn(f'violent wording "{word}": safer to rephrase (Instagram limits violent content)')

    voiced = (root / p["file"]).with_suffix(".voiced").exists()   # voice.py mix leaves this marker
    if p.get("organic"):
        if voiced and not p.get("ai_voice") and not p.get("own_recording"):
            fail('clip has a voice mixed in: set "ai_voice": true (cloned) or "own_recording": true (your recording)')
        if p.get("ai_voice"):
            warn("cloned voice: turn on the AI label when scheduling (Instagram: AI info / Add AI label; "
                 "YouTube: Altered or synthetic content = Yes)")
    elif voiced or p.get("ai_voice") or p.get("own_recording"):
        fail("campaign post with an added voice: voices are for organic posts only (and briefs ban AI voices)")

    if p.get("organic"):   # own content: no campaign rules, just platform limits and honesty about ads
        disc = [o.lower() for o in rules.get("disclosure", {}).get("options", [])]
        if any(t.lower() in disc for t in tags):
            fail("organic post carries an ad disclosure tag; only paid posts should")
        if len(tags) > IG_MAX_HASHTAGS:
            fail(f"{len(tags)} hashtags: Instagram allows 5")
        notice = rules.get("caption_notice", "")
        if notice and notice.lower() not in cap.lower():
            fail(f'publisher requires this notice in the caption: "{notice}"')
        if re.search(r"\bofficial\b", text, re.I):
            fail('"official" in an organic post implies the publisher made it')
        if "youtube" in platforms and not p.get("yt_title"):
            fail("YouTube post without yt_title")
        return out

    allowed = set(rules.get("platforms", {}))
    for pl in platforms:
        if allowed and pl not in allowed:
            fail(f"{pl} is not paid by this campaign (brief pays: {', '.join(sorted(allowed))})")
    for must in rules.get("must_include", []):
        if must.lower() not in cap.lower():
            fail(f"caption is missing {must}")
    for bad in rules.get("banned_words", []):
        if re.search(rf"\b{re.escape(bad)}\b", text, re.I):
            fail(f'banned word "{bad}" in caption/hook/title')

    disc = rules.get("disclosure", {})
    options = [o.lower() for o in disc.get("options", [])]
    if options:
        found = [t for t in tags if t.lower() in options]
        if not found:
            fail(f"no disclosure tag ({' / '.join(disc['options'])})")
        else:
            if disc.get("first_hashtag") and tags[0].lower() not in options:
                fail(f"disclosure must be the first hashtag (first is {tags[0]})")
            if disc.get("own_line"):
                line = next((ln for ln in cap.splitlines() if found[0] in ln), "")
                if line.strip() != found[0]:
                    fail(f"{found[0]} must be on its own line")
    extra = [t for t in tags if t.lower() not in options]
    if len(tags) > IG_MAX_HASHTAGS:
        fail(f"{len(tags)} hashtags: Instagram allows 5")
    if "max_extra_hashtags" in rules and len(extra) > rules["max_extra_hashtags"]:
        fail(f"{len(extra)} extra hashtags, brief allows {rules['max_extra_hashtags']}")

    if "youtube" in platforms:
        t = p.get("yt_title", "")
        if not t:
            fail("YouTube post without yt_title")
        elif len(t) > YT_TITLE_MAX:
            fail(f"yt_title is {len(t)} chars (YouTube max 100)")
        elif len(t) > 40:
            warn(f"yt_title is {len(t)} chars; about 40 show in the Shorts feed")
    if not p.get("pinned"):
        warn("no pinned comment")
    when = datetime.fromisoformat(f"{p['date']}T{p['time']}").replace(tzinfo=IST)
    if when < datetime.now(IST):
        warn(f"post time {p['date']} {p['time']} IST is in the past")
    return out


def account_checks(posts: list[dict], rules: dict) -> list[tuple[str, str]]:
    """Volume and repetition rules that protect the account as a whole."""
    out = []
    by_day, by_platform = defaultdict(list), defaultdict(list)
    for p in posts:
        when = datetime.fromisoformat(f"{p['date']}T{p['time']}")
        for pl in p.get("platforms", ["instagram"]):
            by_day[(pl, p["date"])].append(p["id"])
            by_platform[pl].append((when, p["id"]))
    for (pl, day), ids in sorted(by_day.items()):
        if len(ids) > SAFE_POSTS_PER_DAY:
            out.append(("WARN", f"{pl} {day}: {len(ids)} posts; keep it to {SAFE_POSTS_PER_DAY} or fewer a day"))
    for pl, rows in by_platform.items():
        rows.sort()
        for (a, ia), (b, ib) in zip(rows, rows[1:]):
            gap = (b - a).total_seconds() / 60
            if gap < SAFE_GAP_MIN:
                out.append(("WARN", f"{pl}: {ia} and {ib} are {gap:.0f} min apart; space posts {SAFE_GAP_MIN}+ min"))
    files = Counter((pl, p["file"]) for p in posts for pl in p.get("platforms", ["instagram"]))
    for (pl, f), n in files.items():
        cap = rules.get("max_reposts")
        if n > 1:
            out.append(("FAIL" if cap and n > cap else "WARN", f"{pl}: {f} is posted {n} times"))
    return out


def ics_time(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def ics_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def export(posts: list[dict], rules: dict, root: Path) -> None:
    keep = rules.get("keep_live_days", 30)
    rows, events = [], []
    for p in sorted(posts, key=lambda p: (p["date"], p["time"])):
        when = datetime.fromisoformat(f"{p['date']}T{p['time']}").replace(tzinfo=IST)
        until = (when + timedelta(days=keep)).date().isoformat()
        for pl in p.get("platforms", ["instagram"]):
            rows.append({"date": p["date"], "time_ist": p["time"], "platform": pl, "id": p["id"],
                         "type": "organic" if p.get("organic") else "campaign",
                         "clip": str(root / p["file"]), "cover": str(root / p["cover"]) if p.get("cover") else "",
                         "caption": p["caption"], "yt_title": p.get("yt_title", "") if pl == "youtube" else "",
                         "pinned_comment": p.get("pinned", ""), "keep_live_until": until})
        name = rules.get("name", root.name)
        uid = f"{root.name}-{p['id']}"
        where = ", ".join(p.get("platforms", ["instagram"]))
        submit_url = rules.get("url", "the Content Rewards dashboard")
        if p.get("organic"):
            label = ("\n3. Check the AI label is on (cloned voice). If it's missing, add it now." if p.get("ai_voice")
                     else "")
            body = (f"Your scheduled post {p['id']} ({p.get('title', '')}) is live on {where}. Not a campaign post: "
                    f"nothing to submit.\n\n1. PIN this comment: {p.get('pinned', '')}\n2. Reply to every comment for the "
                    f"next hour.{label}")
            events.append(("LIVE", uid + "-live", when + timedelta(minutes=2), 15, f"LIVE: {p['id']} · pin + reply", body))
            continue
        body = (f"Your scheduled post {p['id']} ({p.get('title', '')}) is live on {where}.\n\n"
                f"1. Open it and copy the link.\n2. SUBMIT the link now: {submit_url}\n"
                f"3. PIN this comment: {p.get('pinned', '')}\n4. Reply to every comment for the next hour.\n\n"
                "If it didn't go live, open Meta Business Suite > Planner and check for an error.")
        limit = rules.get("submit_within_min")      # some campaigns only accept links within N minutes of posting
        head = f"SUBMIT LINK: {p['id']} · {name}"
        if limit:
            by = (when + timedelta(minutes=limit)).strftime("%H:%M")
            head = f"SUBMIT BY {by}: {p['id']} · {name}"
            body = (f"DEADLINE: this campaign only accepts the link within {limit} minutes of posting "
                    f"(by {by} IST). After that the clip earns nothing.\n\n" + body)
            half = max(5, limit // 2)
            events.append(("LIVE", uid + "-last", when + timedelta(minutes=half), 10,
                           f"LAST CALL by {by}: submit {p['id']} · {name}",
                           f"Skip this if you already submitted. {limit - half} minutes left.\n\n" + body))
        events += [
            ("LIVE", uid + "-live", when + timedelta(minutes=2), 15, head, body),
            ("KEEP", uid + "-keep", when + timedelta(days=keep), 15,
             f"{p['id']}: 30-day minimum reached", "Safe to leave up. Never delete before this."),
        ]
    with open(root / "schedule.csv", "w", newline="", encoding="utf-8-sig") as f:   # -sig: opens cleanly in Excel
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["date"])
        w.writeheader()
        w.writerows(rows)
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Clipper//check_plan//EN", "CALSCALE:GREGORIAN"]
    stamp = ics_time(datetime.now(IST))
    for kind, uid, start, mins, summary, desc in events:
        lines += ["BEGIN:VEVENT", f"UID:{uid}@clipper", f"DTSTAMP:{stamp}", f"DTSTART:{ics_time(start)}",
                  f"DTEND:{ics_time(start + timedelta(minutes=mins))}", f"SUMMARY:{ics_escape(summary)}",
                  f"DESCRIPTION:{ics_escape(desc)}"]
        if kind != "KEEP":
            lines += ["BEGIN:VALARM", "ACTION:DISPLAY", "TRIGGER:PT0M",
                      f"DESCRIPTION:{ics_escape(summary)}", "END:VALARM"]
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    (root / "schedule.ics").write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")


def test_reminder(root: Path) -> None:
    """One reminder 10 minutes from now, to check the phone really alerts before trusting a whole schedule."""
    start = datetime.now(IST) + timedelta(minutes=10)
    stamp = ics_time(datetime.now(IST))
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Clipper//check_plan//EN", "BEGIN:VEVENT",
             f"UID:test-{stamp}@clipper", f"DTSTAMP:{stamp}", f"DTSTART:{ics_time(start)}",
             f"DTEND:{ics_time(start + timedelta(minutes=10))}", "SUMMARY:Clipper test reminder",
             "DESCRIPTION:If this alerted on your phone\\, the campaign reminders will too.",
             "BEGIN:VALARM", "ACTION:DISPLAY", "TRIGGER:PT0M", "DESCRIPTION:Clipper test reminder", "END:VALARM",
             "END:VEVENT", "END:VCALENDAR"]
    (root / "reminder_test.ics").write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
    print(f"Wrote {root / 'reminder_test.ics'}: an alert at {start:%H:%M} IST. Import it and wait for it.")


def main() -> int:
    root, rest = campaign.from_argv("check_plan.py <campaign> [--test-reminder]")
    if "--test-reminder" in rest:
        test_reminder(root)
        return 0
    rules_path, posts_path = root / "rules.json", root / "plan" / "posts.json"
    for p in (rules_path, posts_path):
        if not p.exists():
            sys.exit(f"missing {p}")
    rules = json.loads(rules_path.read_text(encoding="utf-8-sig"))
    posts = json.loads(posts_path.read_text(encoding="utf-8-sig"))
    fails = 0
    for p in posts:
        res = check_post(p, rules, root)
        bad = [r for r in res if r[0] == "FAIL"]
        fails += len(bad)
        print(f"{'FAIL' if bad else 'PASS'}  {p['id']}  {p['date']} {p['time']} IST")
        for level, msg in res:
            print(f"      {level}: {msg}")
    for level, msg in account_checks(posts, rules):
        fails += level == "FAIL"
        print(f"{level}  account: {msg}")
    if fails:
        print(f"\n{fails} problem(s): fix them before posting. Schedule not written.")
        return 1
    export(posts, rules, root)
    print(f"\nAll posts pass. Wrote {root / 'schedule.csv'} and {root / 'schedule.ics'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
