"""Rank a Twitch VOD's best moments from the clips its viewers made (Twitch's chat replay API is closed).

usage: twitch_moments.py <channel> <vod id> <out.json> [--scan 300] [--range 7d]
Uses yt-dlp metadata only: the channel's most-viewed clips (creation time, length, views, title) and the VOD's start
time and length. A clip is made a few seconds after the moment it shows, so a clip created at T sits around
T - vod_start in the VOD; the window kept is 75 s before to 15 s after that. Clips within 3 minutes of each other
merge into one moment (score = summed clip views). Moments whose clip titles suggest violence are marked dropped.
Writes [{"rank", "start", "end", "peak", "views", "clips", "titles", "dropped"}] sorted best first (seconds).
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

VIOLENT = re.compile(r"kill|shoot|shot|\bgun|dead|\bdie[sd]?\b|death|blood|punch|fight|beat(s|ing)? up|stab|murder|"
                     r"\bcops?\b|police|wanted|chase|run(s)? over|ran over|pepper|spray|mace|\brob|heist|hostage|bomb|"
                     r"explo|\bfire\b|burn|knife|smack|slap|hit him|hit her|jump(ed)? him|brawl|massacre|rampage", re.I)
SEXUAL = re.compile(r"peg|freaky|nud(e|ity)|naked|steamy|goon|booty|strip ?club|predator|horny|\bsex|twerk|thirst|ayo+\b", re.I)


def ytdlp(*args):
    exe = shutil.which("yt-dlp") or str(Path(__file__).resolve().parents[1] / ".venv" / "Scripts" / "yt-dlp.exe")
    return subprocess.run([exe, *args], capture_output=True, text=True, encoding="utf-8").stdout


def main():
    a = sys.argv[1:]
    if len(a) < 3:
        sys.exit(__doc__)
    channel, vod, out = a[0], str(a[1]), Path(a[2])
    scan = int(a[a.index("--scan") + 1]) if "--scan" in a else 300
    rng = a[a.index("--range") + 1] if "--range" in a else "7d"
    v0, vdur = ytdlp("--skip-download", "--print", "%(timestamp)s\t%(duration)s",
                     f"https://www.twitch.tv/videos/{vod}").strip().splitlines()[-1].split("\t")
    v0, vdur = int(float(v0)), float(vdur)
    clips = []
    for line in ytdlp("--flat-playlist", "--playlist-end", str(scan), "--print",
                      "%(timestamp)s\t%(duration)s\t%(view_count)s\t%(title)s",
                      f"https://www.twitch.tv/{channel}/clips?filter=clips&range={rng}").splitlines():
        p = line.split("\t")
        if len(p) < 4 or p[0] in ("NA", ""):
            continue
        at = int(float(p[0])) - v0
        if 0 < at <= vdur + 60:
            clips.append({"at": at, "views": int(float(p[2])) if p[2] not in ("NA", "") else 0, "title": p[3]})
    clips.sort(key=lambda c: c["at"])
    groups = []
    for c in clips:
        if groups and c["at"] - groups[-1][-1]["at"] <= 180:
            groups[-1].append(c)
        else:
            groups.append([c])
    moments = []
    for g in groups:
        top = max(g, key=lambda c: c["views"])
        titles = [c["title"] for c in sorted(g, key=lambda c: -c["views"])][:5]
        bad = [t for t in titles if VIOLENT.search(t) or SEXUAL.search(t)]
        moments.append({"start": max(0, min(c["at"] for c in g) - 75), "end": min(vdur, max(c["at"] for c in g) + 15),
                        "peak": top["at"], "views": sum(c["views"] for c in g), "clips": len(g), "titles": titles,
                        "dropped": f"violent/sexual title: {bad[0]}" if bad else None})
    moments.sort(key=lambda m: -m["views"])
    for i, m in enumerate(moments, 1):
        m["rank"] = i
    out.write_text(json.dumps({"vod": vod, "vod_start": v0, "vod_duration": vdur, "moments": moments},
                              indent=1, ensure_ascii=False), encoding="utf-8")
    keep = [m for m in moments if not m["dropped"]]
    print(f"{channel}: {len(clips)} clips from VOD {vod} ({vdur / 3600:.1f} h), {len(moments)} moments, "
          f"{len(keep)} non-violent, {len(moments) - len(keep)} dropped (violent/sexual title)")
    for m in keep[:22]:
        s = int(m["start"])
        print(f"  #{m['rank']:>2} {s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d} +{int(m['end'] - m['start'])}s "
              f"{m['views']:>6} views {m['clips']:>2} clips | {m['titles'][0][:58]}")


if __name__ == "__main__":
    main()
