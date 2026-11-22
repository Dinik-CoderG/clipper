"""Download only the chosen moment windows of a VOD (not the whole stream) into <campaign>\source\.

usage: fetch_windows.py <campaign folder> [--top 16] [--before 75] [--after 20] [--format 1080p60/best]
Reads <campaign>\plan\moments.json (twitch_moments.py) and the VOD url in rules.json; for the top N moments not
marked "dropped" it downloads [peak - before, peak + after] as source\m<rank>.mp4 (skips files already there).
YouTube VODs go through reels\hls_window.py (frame-accurate, picture and sound in step); Twitch (one muxed
stream) through yt-dlp's section download. Check any window with reels\av_offset.py / audio_offset.py.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))      # scripts here run with python -P


def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    camp = Path(a[0])
    top = int(a[a.index("--top") + 1]) if "--top" in a else 16
    before = float(a[a.index("--before") + 1]) if "--before" in a else 75
    after = float(a[a.index("--after") + 1]) if "--after" in a else 20
    fmt = a[a.index("--format") + 1] if "--format" in a else "1080p60/best[height<=1080]"
    rules = json.loads((camp / "rules.json").read_text(encoding="utf-8-sig"))
    data = json.loads((camp / "plan" / "moments.json").read_text(encoding="utf-8"))
    exe = shutil.which("yt-dlp") or str(Path(__file__).resolve().parents[1] / ".venv" / "Scripts" / "yt-dlp.exe")
    src = camp / "source"
    src.mkdir(exist_ok=True)
    picked = [m for m in data["moments"] if not m.get("dropped")][:top]
    todo = []
    for m in picked:
        out = src / f"m{m['rank']:02d}.mp4"
        if out.exists():
            continue
        s, e = max(0, m["peak"] - before), min(data["vod_duration"], m["peak"] + after)
        todo.append((round(s), round(e), out, m))
    youtube = "youtube.com" in rules["vod"] or "youtu.be" in rules["vod"]
    if youtube:
        # YouTube = separate video and audio streams: yt-dlp's section cut can leave the picture up to ~6 s behind
        # the sound (lip-sync drift). Cut from whole HLS segments instead, both streams on the playlist clock.
        from hls_window import cut
        for s, e, out, m in todo:
            print(f"#{m['rank']} {s}-{e}s  {m['titles'][0][:50]}", flush=True)
        if todo:
            cut(rules["vod"], fmt if "+" in fmt else "312+234/bv*[height<=1080][protocol*=m3u8]+234",
                [(s, e, str(out)) for s, e, out, _ in todo])
    for s, e, out, m in ([] if youtube else todo):
        print(f"#{m['rank']} {s}-{e}s  {m['titles'][0][:50]}", flush=True)
        subprocess.run([exe, "-q", "--no-warnings", "-f", fmt, "--download-sections", f"*{s}-{e}",
                        "-o", str(out), rules["vod"]], check=False)
    print("done", sum(1 for _ in src.glob("m*.mp4")), "windows in", src, flush=True)


if __name__ == "__main__":
    main()
