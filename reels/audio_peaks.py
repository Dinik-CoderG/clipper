r"""Rank a long stream's reaction moments from its audio alone (when there is no chat replay or heatmap).

usage: audio_peaks.py <audio file> <out moments.json> [--bin 10] [--gap 180] [--top 60]
Decodes the audio to 8 kHz mono, measures loudness (dB RMS) per 10 s, and scores each bin against the stream's own
rolling baseline (median of the surrounding 10 minutes): a streamer's big reactions (screaming, laughing, hype) stand
out from their normal talking level. Keeps the strongest bins, at most one per 3 minutes; window = 60 s before to 30 s
after the peak. Same output format as twitch_moments.py / chat_peaks.py (titles empty; read the transcript instead).
"""
import json
import math
import statistics as st
import subprocess
import sys
from pathlib import Path

import numpy as np

SR = 8000


def main():
    a = sys.argv[1:]
    if len(a) < 2:
        sys.exit(__doc__)
    src, out = Path(a[0]), Path(a[1])
    binw = float(a[a.index("--bin") + 1]) if "--bin" in a else 10.0
    gap = float(a[a.index("--gap") + 1]) if "--gap" in a else 180.0
    top = int(a[a.index("--top") + 1]) if "--top" in a else 60
    proc = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(src), "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"],
                            stdout=subprocess.PIPE)
    per = int(SR * binw)
    db = []
    while True:
        buf = proc.stdout.read(per * 2)
        if not buf:
            break
        x = np.frombuffer(buf, dtype=np.int16).astype(np.float32) / 32768.0
        # loudness of the loudest 2 s inside the bin, so a short scream is not averaged away
        k = SR * 2
        peaks = [float(np.sqrt(np.mean(x[i:i + k] ** 2))) for i in range(0, max(1, len(x) - k + 1), SR)] or [0.0]
        db.append(20 * math.log10(max(1e-5, max(peaks))))
    proc.wait()
    n = len(db)
    half = int(300 // binw)
    score = []
    for i in range(n):
        ref = db[max(0, i - half):i + half + 1]
        score.append(db[i] - st.median(ref))
    order = sorted(range(n), key=lambda i: -score[i])
    picked = []
    for i in order:
        if db[i] < -40:          # silence / muted parts
            continue
        if all(abs(i - j) * binw >= gap for j in picked):
            picked.append(i)
        if len(picked) >= top:
            break
    dur = n * binw
    moments = []
    for rank, i in enumerate(picked, 1):
        peak = i * binw + binw / 2
        moments.append({"rank": rank, "start": max(0, peak - 60), "end": min(dur, peak + 30), "peak": peak,
                        "views": int(score[i] * 100), "clips": 0, "titles": [f"+{score[i]:.1f} dB over baseline"],
                        "dropped": None})
    out.write_text(json.dumps({"vod_duration": dur, "moments": moments}, indent=1), encoding="utf-8")
    print(f"{dur / 3600:.1f} h of audio, {len(moments)} peaks")
    for m in moments[:30]:
        s = int(m["peak"])
        print(f"  #{m['rank']:>2} {s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}  {m['titles'][0]}")


if __name__ == "__main__":
    main()
