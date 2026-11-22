"""Download a stream's chat replay (Twitch VOD or YouTube live) as compact gzip JSON lines: {"t": seconds, "m": text}.

usage: chat_replay.py <vod url> <out.jsonl.gz> [--max-hours H] [--from S --to S]
Twitch VOD chat no longer works (Twitch closed the API); YouTube live chat replay does.
Then rank peaks with chat_peaks.py. Needs chat-downloader in .venv (pip install chat-downloader).
"""
import gzip
import json
import sys
import time

from chat_downloader import ChatDownloader


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    url, out = sys.argv[1], sys.argv[2]
    max_h = float(sys.argv[sys.argv.index("--max-hours") + 1]) if "--max-hours" in sys.argv else None
    kw = {"end_time": int(max_h * 3600)} if max_h else {}
    if "--from" in sys.argv:          # a chunk of a long stream, in seconds: --from 0 --to 10800
        kw["start_time"] = int(float(sys.argv[sys.argv.index("--from") + 1]))
    if "--to" in sys.argv:
        kw["end_time"] = int(float(sys.argv[sys.argv.index("--to") + 1]))
    n, t0 = 0, time.time()
    with gzip.open(out, "wt", encoding="utf-8") as f:
        for msg in ChatDownloader().get_chat(url, message_groups=["messages"], **kw):
            t = msg.get("time_in_seconds")
            if t is None:
                continue
            f.write(json.dumps({"t": round(float(t), 1), "m": (msg.get("message") or "")[:120]},
                               ensure_ascii=False) + "\n")
            n += 1
            if n % 200000 == 0:
                print(f"{n} messages, at {t / 3600:.1f} h, {time.time() - t0:.0f}s", flush=True)
    print(f"done: {n} messages -> {out} in {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
