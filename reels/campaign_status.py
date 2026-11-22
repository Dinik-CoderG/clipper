r"""What's left in each campaign folder: clips made, posts planned/posted, footage not used yet.

usage: campaign_status.py [channel]
Prints a table and writes discover\status.json. Used by the find-campaigns skill to decide whether an enrolled
campaign that ran out of clips is worth a second batch (there is unused footage, and the campaign still has budget).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IST = timezone(timedelta(hours=5, minutes=30))


def load(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001
        return default


def status(folder: Path) -> dict:
    rules = load(folder / "rules.json", {})
    posts = load(folder / "plan" / "posts.json", [])
    now = datetime.now(IST)
    past = upcoming = 0
    for p in posts:
        try:
            when = datetime.strptime(f"{p['date']} {p['time']}", "%Y-%m-%d %H:%M").replace(tzinfo=IST)
        except Exception:  # noqa: BLE001
            continue
        if when <= now:
            past += 1
        else:
            upcoming += 1
    sources = sorted(p.stem for p in (folder / "source").glob("*.mp4")) if (folder / "source").exists() else []
    used: dict[str, list] = {}
    for clip in load(folder / "edit.json", []):
        for b in clip.get("beats", []):
            used.setdefault(b["src"], []).append([b["start"], b["end"]])
    for clip in load(folder / "clips.json", []) if isinstance(load(folder / "clips.json", []), list) else []:
        if isinstance(clip, dict) and clip.get("source"):
            used.setdefault(clip["source"], []).append([clip.get("start"), clip.get("end")])
    unused = [s for s in sources if s not in used]
    scheduled = {(r.get("id"), r.get("platform")) for r in load(folder / "scheduled.json", [])}
    return {"slug": folder.name, "name": rules.get("name", folder.name), "channel": rules.get("channel"),
            "status": rules.get("status", "active"),
            "url": rules.get("url"), "clips_made": len(list((folder / "clips").glob("*.mp4"))) if (folder / "clips").exists() else 0,
            "posts_planned": len(posts), "posts_past": past, "posts_upcoming": upcoming,
            "posts_scheduled_by_claude": len(scheduled), "max_reposts": rules.get("max_reposts"),
            "sources": len(sources), "sources_unused": len(unused), "unused": unused[:60], "used_windows": used,
            "out_of_clips": upcoming == 0 and len(posts) > 0 and rules.get("status") != "dropped"}


def main() -> None:
    channel = sys.argv[1] if len(sys.argv) > 1 else None
    rows = []
    for folder in sorted((ROOT / "campaigns").iterdir()):
        if not folder.is_dir() or folder.name.startswith(("_", "own_")):
            continue
        s = status(folder)
        if channel and s["channel"] not in (channel, None):
            continue
        rows.append(s)
    (ROOT / "discover").mkdir(exist_ok=True)
    (ROOT / "discover" / "status.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print("| campaign | channel | clips made | posts past / upcoming | footage files unused / total | out of clips |")
    print("|---|---|---|---|---|---|")
    for s in rows:
        print(f"| {s['slug']} | {s['channel'] or '?'} | {s['clips_made']} | {s['posts_past']} / {s['posts_upcoming']} | "
              f"{s['sources_unused']} / {s['sources']} | {'YES' if s['out_of_clips'] else 'no'} |")


if __name__ == "__main__":
    main()
