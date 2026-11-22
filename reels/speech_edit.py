r"""Build edit.json for TALKING footage (podcasts, streams, shows, interviews) from Whisper word timings.

usage: speech_edit.py <campaign> [--show] [--keep-pauses] [--keep-fillers] [--append]
Reads   <campaign>\plan\clips_spec.json   which sentences each clip uses (format below)
        <campaign>\analysis\<source>\transcript.json   [{"start","end","text","words":[[t0,t1,"word"],...]}]
Writes  <campaign>\edit.json   (for reels\edit_viral.py)

What it does that a plain trim doesn't:
- cuts each clip on word boundaries into ~2 s beats that alternate two framings (hides the jump cuts);
- **tightens the pace**: pauses longer than 0.45 s are cut down to a breath, and "um"/"uh" are cut out of the
  audio. "like," "you know," "I mean," used as fillers are removed from the captions only (cutting them from the
  audio sounds choppy). --keep-pauses / --keep-fillers turn these off;
- gives every beat its real word times, so captions light up exactly when each word is spoken;
- uses layout "speaker": the editor finds whoever is talking and fills the screen with them.

clips_spec.json:
{"source": "Episode-002",                 # file name in source\ without .mp4
 "brand": "EXAMPLE SHOW",                 # optional pill
 "cta": ["Full episode on *Example Show*"], "cta_secs": 2.0,
 "layout": "speaker",                     # default; "wide"/"full"/"setup" also work
 "focus": [0.83, 0.36], "lock": false,    # optional: where the main speaker sits; lock = never switch person
 "cam": [0, 0.33, 0.2, 0.2], "hook_y": 640, # layout "stack": facecam rect + hook position (also per clip)
 "logo": {"path": "brief/logo.png"},      # optional required logo (also per clip)
 # each clip may also set its own "source" (window file) when the clips come from different files
 "fixes": [["tech crunch", "TechCrunch "]],   # Whisper mishearings: same number of words each side
 "clips": [{"id": "01_why_raise_money", "hook": "Why are you *raising money?*", "tags": {...},
            "segments": [[2326, "I wanna hear", "scale much faster?"], ...]}]}   # near-seconds, first words, last words
(An older spec that is just the list of clips also works; the other settings then use their defaults.)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAUSE = 0.45            # a gap longer than this between two words is cut
KEEP_AFTER, KEEP_BEFORE = 0.12, 0.07     # what's left of a cut pause: a breath after and before
CUT_AUDIO = {"um", "uh", "umm", "uhh", "erm"}
CAPTION_ONLY = {"like,", "you know,", "i mean,", "right,", "so,"}   # only when written with the comma = filler use
ZOOMS = {"speaker": [[1.0, 1.03], [1.12, 1.15]], "wide": [[1.69, 1.71], [1.80, 1.83]], "full": [[1.0, 1.04], [1.12, 1.16]],
         "setup": [[1.0, 1.03], [1.1, 1.13]]}


def norm(w):
    return re.sub(r"[^a-z0-9$%']", "", w.lower())


SWEARS = re.compile(r"(?i)\b(fuck\w*|motherfuck\w*|shit\w*|bitch\w*|ass(hole)?|dick\w*|cock\w*|pussy|bastard|damn|goddamn"
                    r"|nigg\w*)\b")


def mask(text):
    """Star out swear words in on-screen captions (the audio is untouched): 'fucking' -> 'f*****g'."""
    return SWEARS.sub(lambda m: m.group(0)[0] + "*" * max(1, len(m.group(0)) - 2) + (m.group(0)[-1] if len(m.group(0)) > 2 else ""), text)


def load_words(root, source, fixes):
    segs = json.loads((root / "analysis" / source / "transcript.json").read_text(encoding="utf-8-sig"))
    words = [list(w) for seg in segs for w in seg.get("words", [])]
    if not words:
        sys.exit("transcript.json has no word timings: transcribe with word_timestamps=True")
    merged = []
    for w in words:                      # Whisper splits "co -founder", "100 %": glue them back
        if merged and (w[2].startswith("-") or w[2] == "%" or re.match(r"^,\d", w[2])):
            merged[-1][1] = w[1]
            merged[-1][2] += w[2]
        else:
            merged.append(w)
    for old, new in fixes:
        o, n = old.split(" "), new.split(" ")
        if len(o) != len(n):
            sys.exit(f"fix must keep the word count: {old!r} -> {new!r}")
        for i in range(len(merged) - len(o) + 1):
            if all(merged[i + k][2] == o[k] for k in range(len(o))):
                for k in range(len(o)):
                    merged[i + k][2] = n[k]
    return merged


def find(words, phrase, near, window=25.0):
    toks = [norm(t) for t in phrase.split()]
    best = None
    for i in range(len(words) - len(toks) + 1):
        if abs(words[i][0] - near) > window:
            continue
        if all(norm(words[i + k][2]) == toks[k] for k in range(len(toks))):
            if best is None or abs(words[i][0] - near) < abs(words[best][0] - near):
                best = i
    if best is None:
        sys.exit(f"phrase not found near {near}s: {phrase!r}")
    return best, best + len(toks) - 1


def beats_for(words, i0, i1, zi, source, zooms, keep_pauses, keep_fillers, base):
    """Words i0..i1 -> beats. A new beat starts every ~2 s at a word boundary, and at every cut (pause / um)."""
    idx = [i for i in range(i0, i1 + 1)
           if keep_fillers or norm(words[i][2]) not in CUT_AUDIO]          # dropped words leave a gap that gets cut
    groups, cur, cuts = [], [idx[0]], []                                    # cuts[k] = hard cut after group k
    for a, b in zip(idx, idx[1:]):
        gap = words[b][0] - words[a][1]
        dur = words[a][1] - words[cur[0]][0]
        punct = words[a][2][-1:] in tuple(".,?!;:")
        hard = (b != a + 1) or (not keep_pauses and gap > PAUSE)
        if hard or dur >= 2.6 or (dur >= 1.5 and (punct or gap > 0.25)):
            groups.append(cur)
            cuts.append(hard)
            cur = []
        cur.append(b)
    groups.append(cur)
    cuts.append(True)
    # no blink-length beats: merge a tiny group into its neighbour when there is no cut between them
    k = 0
    while k < len(groups) - 1:
        g = groups[k + 1]
        if not cuts[k] and words[g[-1]][1] - words[g[0]][0] < 0.7:
            groups[k] += groups.pop(k + 1)
            cuts[k] = cuts.pop(k + 1)
        else:
            k += 1
    beats, saved = [], 0.0
    for n, g in enumerate(groups):
        first, last = words[g[0]], words[g[-1]]
        prev_cut = n == 0 or cuts[n - 1]
        start = first[0] - (KEEP_BEFORE if prev_cut else 0.0)
        if n == 0:
            start = first[0] - 0.12
        if cuts[n]:
            end = last[1] + (0.18 if n == len(groups) - 1 else KEEP_AFTER)
            if n + 1 < len(groups):
                nxt = words[groups[n + 1][0]][0] - KEEP_BEFORE
                end = min(end, nxt)                       # never overlap the next beat
                saved += max(0.0, nxt - end)
        else:
            end = words[groups[n + 1][0]][0]
        shown = []
        for i in g:
            w = words[i][2]
            pair = (words[i - 1][2] + " " + w).lower() if i > g[0] else ""
            if not keep_fillers and (w.lower() in CAPTION_ONLY or pair in CAPTION_ONLY):
                if pair in CAPTION_ONLY and shown:
                    shown.pop()
                continue
            shown.append([round(words[i][0], 2), round(words[i][1], 2), w])
        beat = {"src": source, "start": round(max(0, start), 2), "end": round(end, 2),
                "zoom": zooms[(zi + n) % 2], "sfx": "none", "words": shown,
                "text": " ".join(w for _, _, w in shown)}
        beat.update(base)
        beats.append(beat)
    return beats, saved


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    root = Path(args[0])
    if not root.exists():
        root = HERE.parent / "campaigns" / args[0]
    spec = json.loads((root / "plan" / "clips_spec.json").read_text(encoding="utf-8-sig"))
    if isinstance(spec, list):
        spec = {"clips": spec}
    source = spec.get("source") or next((p.stem for p in sorted((root / "source").glob("*.mp4"))), None)
    if not source:
        sys.exit("no source video found")
    layout = spec.get("layout", "speaker")
    zooms = spec.get("zooms") or ZOOMS.get(layout, ZOOMS["speaker"])
    base = {}
    if spec.get("focus"):
        base["focus"] = spec["focus"]
        if spec.get("lock"):
            base["speaker"] = "focus"
    cta, cta_secs = spec.get("cta"), float(spec.get("cta_secs", 2.0))
    cache = {}
    keep_p, keep_f = "--keep-pauses" in sys.argv, "--keep-fillers" in sys.argv
    clips = []
    for c in spec["clips"]:
        source = c.get("source") or spec.get("source") or source      # a clip may name its own window
        if source not in cache:
            cache[source] = load_words(root, source, spec.get("fixes", []))
        words = cache[source]
        clayout = c.get("layout", layout)                      # a clip may override layout and focus
        czooms = spec.get("zooms") or ZOOMS.get(clayout, ZOOMS["speaker"])
        cbase = dict(base, **({"focus": c["focus"]} if c.get("focus") else {}))
        beats, zi, saved = [], 0, 0.0
        for near, first, last in c["segments"]:
            a, _ = find(words, first, near)
            _, b = find(words, last, words[a][0] + 12, window=60.0)
            if b < a:
                sys.exit(f"{c['id']}: end before start for {first!r}")
            seg, s = beats_for(words, a, b, zi, source, czooms, c.get("keep_pauses", keep_p), keep_f, cbase)
            beats += seg
            zi += len(seg)
            saved += s
        if c.get("mask_profanity", spec.get("mask_profanity")):
            for bt in beats:
                if bt.get("text"):
                    bt["text"] = mask(bt["text"])
                if bt.get("words"):
                    bt["words"] = [[a, z, mask(x)] for a, z, x in bt["words"]]
        clip = {"id": c["id"], "hook": c["hook"], "hook_until": c.get("hook_until", 3.2), "layout": clayout,
                "tags": c.get("tags", {}), "beats": beats}
        if spec.get("brand"):
            clip["brand"] = spec["brand"]
        for k in ("cam", "hook_y", "logo"):              # layout "stack" (streamer clips) and a brief's logo
            if c.get(k, spec.get(k)) is not None:
                clip[k] = c.get(k, spec.get(k))
        if cta:   # hold on the speaker under the end card, silent, no caption
            t0 = beats[-1]["end"]
            tail = {"src": source, "start": t0, "end": round(t0 + cta_secs, 2), "zoom": czooms[zi % 2], "sfx": "none",
                    "mute": True}
            tail.update(cbase)
            beats.append(tail)
            clip["cta"], clip["cta_secs"] = cta, cta_secs
        total = sum(b["end"] - b["start"] for b in beats)
        print(f"{c['id']}: {total:.1f}s, {len(beats)} beats, {saved:.1f}s of pauses and ums cut")
        if "--show" in sys.argv:
            for b in beats:
                print(f"   {b['start']:8.2f}-{b['end']:8.2f}  {b.get('text', '(end card)')}")
        clips.append(clip)
    out = root / "edit.json"
    if "--append" in sys.argv and out.exists():
        old = [c for c in json.loads(out.read_text(encoding="utf-8-sig")) if c["id"] not in {x["id"] for x in clips}]
        clips = old + clips
    out.write_text(json.dumps(clips, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
