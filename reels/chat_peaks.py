r"""Rank a YouTube live stream's moments from its chat replay (yt-dlp --write-subs --sub-langs live_chat).

usage: chat_peaks.py <chat.live_chat.json | "chunk_*.jsonl.gz"> <duration s> <out moments.json> [--bin 10] [--gap 180]
(a quoted glob reads the {"t","m"} chunk files written by chat_replay.py --from/--to)
Counts chat messages per 10 s, divides by the stream's own rolling baseline (median of the surrounding 10 minutes),
and keeps the strongest bins, at most one per 3 minutes. Chat reacts after the moment, so the window kept is 60 s
before to 30 s after the peak; clips should start 10-20 s before it. Messages in a peak are scanned for words that
suggest violence or sexual content and those moments are marked dropped. Same output format as twitch_moments.py:
{"vod_duration", "moments": [{"rank", "start", "end", "peak", "views" (= peak score x100), "clips", "titles", "dropped"}]}
"""
import json
import re
import statistics as st
import sys
from collections import Counter
from pathlib import Path

BAD = re.compile(r"\brip\b|kill|shot|shoot|\bgun|dead|died|blood|murder|cops?\b|police|fight|punch|nude|naked|"
                 r"strip|boob|\bsex|goon|freaky", re.I)


def text_of(item):
    runs = item.get("message", {}).get("runs", [])
    return "".join(r.get("text", "") or r.get("emoji", {}).get("shortcuts", [""])[0] for r in runs)


def main():
    a = sys.argv[1:]
    if len(a) < 3:
        sys.exit(__doc__)
    src, dur, out = Path(a[0]), float(a[1]), Path(a[2])
    binw = float(a[a.index("--bin") + 1]) if "--bin" in a else 10.0
    gap = float(a[a.index("--gap") + 1]) if "--gap" in a else 180.0
    nb = int(dur // binw) + 1
    counts, msgs = [0] * nb, [[] for _ in range(nb)]
    for g in sorted(src.parent.glob(src.name)) if any(ch in src.name for ch in "*?") else []:   # chunk files
        import gzip
        with gzip.open(g, "rt", encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                t = float(d.get("t", -1))
                if 0 <= t <= dur:
                    i = int(t // binw)
                    counts[i] += 1
                    if len(msgs[i]) < 400:
                        msgs[i].append(d.get("m", ""))
    with (src.open(encoding="utf-8") if src.exists() else open(__file__, encoding="utf-8")) as f:
        for line in f if src.exists() else []:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            r = d.get("replayChatItemAction", {})
            t = float(r.get("videoOffsetTimeMsec", -1)) / 1000
            if t < 0 or t > dur:
                continue
            for act in r.get("actions", []):
                item = act.get("addChatItemAction", {}).get("item", {})
                m = item.get("liveChatTextMessageRenderer") or item.get("liveChatPaidMessageRenderer")
                if m:
                    i = int(t // binw)
                    counts[i] += 1
                    if len(msgs[i]) < 400:
                        msgs[i].append(text_of(m))
    half = int(300 // binw)
    score = []
    for i in range(nb):
        ref = counts[max(0, i - half):i + half + 1]
        base = max(3.0, st.median(ref))
        score.append(counts[i] / base)
    order = sorted(range(nb), key=lambda i: -score[i])
    picked = []
    for i in order:
        if counts[i] < 10:
            continue
        if all(abs(i - j) * binw >= gap for j in picked):
            picked.append(i)
        if len(picked) >= 60:
            break
    moments = []
    for rank, i in enumerate(picked, 1):
        peak = i * binw + binw / 2
        words = Counter(w.lower() for m in msgs[i] for w in re.findall(r"[\w']+|[^\w\s]", m) if len(w) > 1)
        top = [w for w, _ in words.most_common(8)]
        bad = [m for m in msgs[i] if BAD.search(m)]
        flag = len(bad) >= max(3, len(msgs[i]) * 0.08)
        moments.append({"rank": rank, "start": max(0, peak - 60), "end": min(dur, peak + 30), "peak": peak,
                        "views": int(score[i] * 100), "clips": counts[i], "titles": [" ".join(top)] + msgs[i][:4],
                        "dropped": f"chat suggests violence/sexual: {bad[0][:40]}" if flag else None})
    out.write_text(json.dumps({"vod_duration": dur, "moments": moments}, indent=1, ensure_ascii=False), encoding="utf-8")
    keep = [m for m in moments if not m["dropped"]]
    print(f"{sum(counts)} chat messages, {len(moments)} peaks, {len(keep)} kept")
    for m in keep[:25]:
        s = int(m["peak"])
        print(f"  #{m['rank']:>2} {s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}  x{m['views'] / 100:.1f}  "
              f"{m['clips']} msgs | {m['titles'][0][:60]}")


if __name__ == "__main__":
    main()
