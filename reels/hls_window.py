r"""Cut windows out of a long HLS stream with picture and sound exactly in step (YouTube live VODs).

usage: hls_window.py <video page url> <format, e.g. 312+234> <start s> <end s> <out.mp4> [<start> <end> <out> ...]

Why: YouTube serves video and audio as two separate HLS streams. `yt-dlp --download-sections` cuts each with
ffmpeg's input seek, and on some windows the picture starts at the beginning of its segment (up to ~6 s early)
while being stamped as if it started at the cut, and the sound is cut exactly: the picture then runs behind the
voice by up to 6 s (lip-sync drift seen on 8 clips).
How: read both playlists, download the whole segments that cover [start-1, end+1] for each stream, and cut both
locally at (start - that stream's first-segment time from the playlist), frame-accurately (decode + re-encode the
picture near-losslessly on the GPU, sound re-encoded as 256k AAC). Picture and sound then come from the same
playlist clock. A single muxed stream (Twitch) doesn't have this problem and can use yt-dlp as before.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def ytdlp():
    return shutil.which("yt-dlp") or str(ROOT / ".venv" / "Scripts" / "yt-dlp.exe")


def formats(page, fmt):
    out = subprocess.run([ytdlp(), "--no-warnings", "-j", "-f", fmt, page], capture_output=True, text=True,
                         check=True).stdout
    j = json.loads(out)
    return j.get("requested_formats") or [j]


def fetch(url, headers, tries=4):
    for k in range(tries):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60).read()
        except Exception:  # noqa: BLE001
            if k == tries - 1:
                raise
    return b""


class Playlist:
    def __init__(self, fmt):
        self.headers = fmt.get("http_headers", {})
        self.url = fmt["url"]
        text = fetch(self.url, self.headers).decode("utf-8", "replace")
        self.init, self.segs, t, dur = None, [], 0.0, None
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("#EXT-X-MAP:"):
                uri = line.split("URI=", 1)[1].split(",")[0].strip('"')
                self.init = urllib.parse.urljoin(self.url, uri)
            elif line.startswith("#EXTINF:"):
                dur = float(line[8:].split(",")[0])
            elif line and not line.startswith("#") and dur is not None:
                self.segs.append((t, dur, urllib.parse.urljoin(self.url, line)))
                t += dur
                dur = None

    def grab(self, start, end, path):
        """Download the segments covering [start, end] into one file; returns the playlist time of its start."""
        picked = [s for s in self.segs if s[0] + s[1] > start and s[0] < end]
        if not picked:
            raise SystemExit(f"no segments for {start}-{end}s")
        with open(path, "wb") as f:
            if self.init:
                f.write(fetch(self.init, self.headers))
            for _, _, u in picked:
                f.write(fetch(u, self.headers))
        return picked[0][0]


def encoder():
    try:
        r = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=s=256x256:d=0.1", "-c:v",
                            "h264_nvenc", "-f", "null", "-"], capture_output=True, timeout=30)
        if r.returncode == 0:
            return ["-c:v", "h264_nvenc", "-preset", "p7", "-rc", "vbr", "-cq", "15", "-b:v", "0", "-profile:v",
                    "high"]
    except Exception:  # noqa: BLE001
        pass
    return ["-c:v", "libx264", "-preset", "slow", "-crf", "14"]


def cut(page, fmt, jobs):
    """jobs = [(start, end, out_path)]. Video and audio playlists are read once for all windows."""
    fs = formats(page, fmt)
    if len(fs) != 2:
        raise SystemExit("hls_window.py is for separate video + audio streams (format like 312+234)")
    vpl, apl = Playlist(fs[0]), Playlist(fs[1])
    enc = encoder()
    for start, end, out in jobs:
        with tempfile.TemporaryDirectory() as tmp:
            v, a = Path(tmp) / "v.mp4", Path(tmp) / "a.mp4"
            v0 = vpl.grab(start - 1, end + 1, v)
            a0 = apl.grab(start - 1, end + 1, a)
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{start - v0:.3f}", "-i", str(v),
                            "-ss", f"{start - a0:.3f}", "-i", str(a), "-t", f"{end - start:.3f}",
                            "-map", "0:v:0", "-map", "1:a:0", *enc, "-pix_fmt", "yuv420p",
                            "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", str(out)], check=True)
        print(f"  {Path(out).name}: {start:.0f}-{end:.0f}s cut from segments (video +{start - v0:.2f}s, "
              f"audio +{start - a0:.2f}s into their first segment)", flush=True)


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) < 5 or (len(a) - 2) % 3:
        sys.exit(__doc__)
    cut(a[0], a[1], [(float(a[i]), float(a[i + 1]), a[i + 2]) for i in range(2, len(a), 3)])
