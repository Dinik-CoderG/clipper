# Campaigns

One folder per clipping campaign. The tool lives in `reels\` and is never stored here.
When a campaign ends, its folder is deleted and a line is added to **Past campaigns** below.

## Start a new campaign
1. Copy `_template\` to a new folder, e.g. `campaigns\gta6_trailer_clips\`.
2. Put the brief PDF in `brief\` and the official footage in `source\` (`<name>.mp4`).
3. Run, from the project folder (Python: `.venv\Scripts\python.exe -P`):
   - `reels\analyze.py <campaign>`: transcripts + contact sheets into `analysis\`
   - `reels\subs.py <campaign> <source> <start> <end>`: read in-game subtitles for a time range
   - fill `clips.json` (moments, hooks, captions)
   - `reels\render.py <campaign> [clip_id ...]`: Reels into `clips\` (clips cycle through the frames in the
     campaign's `frames.json`; without that file, frames 1 and 2 alternate)
   - `reels\make_covers.py <campaign>`: covers into `covers\`
   - posting plan: copy `reels\templates\plan_pdf_template.py` to `<campaign>\plan\build_plan.py` and edit
4. When posting each clip, check it against the brief's rules (tags, disclosure, hashtags, music, length).

Rendering uses the NVIDIA GPU (`h264_nvenc`, via `reels\encode.py`) automatically. If the GPU encoder isn't
available or fails, it falls back to x264 on the CPU by itself. A 14 s reel takes about 70 s instead of 4 min.
Set `CLIPPER_ENCODER=cpu` to force the CPU.

## clips.json fields
| field | meaning |
|---|---|
| `id`, `source`, `start`, `end` | clip name, source file (no .mp4), seconds in the source |
| `hook` | on-wall text; `*word*` = yellow highlight, emoji allowed |
| `cues` | hand-typed captions `[start, end, speaker, text]` (source seconds) |
| `captions: "whisper"` | auto word-by-word captions from the transcript instead |
| `cover` | source second for the cover image (default: middle of the clip) |
| `frame` | force one frame for this clip (default: next one in the rotation) |

## Frames (`reels\frames\real_frame.py`)
| frame | look |
|---|---|
| `1_neon_tv` | neon living room, big TV, Kirby lamp on the table |
| `2_neon_coffee_table` | neon room, TV seen past a coffee table |
| `6_ultrawide_neon` | dark desk, curved 21:9 ultrawide on a blue-purple neon wall (gameplay cropped a little top/bottom) |
| `7_red_desk` | dark desk room with red light, RGB keyboard, monitor across the full width |
| `8_blue_desk` | dark desk, white-blue LED strip under a 16:9 monitor, keyboard and controller |

`frames.json` in a campaign folder = the rotation, e.g. `["1_neon_tv", "2_neon_coffee_table", "6_ultrawide_neon", "7_red_desk"]`
(the template has all four).

## Active campaigns
- **<slug>**: campaign name (agency), platform. Joined <date> with <channel id>. Rate per 1K, min and max payout.
  Every post: required tags, disclosure, links. Footage: where it came from. Clip count and post dates.

## Past campaigns
- **<campaign>** (agency). Ended <date>; data deleted. Learned: what worked and what didn't.
