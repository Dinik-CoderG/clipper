# Clipper

A working, local rebuild of [vugolaai.com/youtube-clip-maker](https://www.vugolaai.com/youtube-clip-maker).
Paste a YouTube, Twitch, or Kick link and get back vertical 1080×1920 clips with face tracking and word-by-word captions.

## Setup (new user)

Windows 10/11 is required: the scripts use PowerShell, Windows fonts (`C:\Windows\Fonts`) and Microsoft Edge to print
the posting-plan PDFs. An NVIDIA GPU is optional. Without one, transcription and encoding run on the CPU, which is slower.

1. **Python 3.13** (3.11 or newer works) from [python.org](https://www.python.org/downloads/windows/). Tick
   "Add python.exe to PATH" in the installer. Check it with `python --version`.
2. **ffmpeg** (it includes `ffprobe`): `winget install Gyan.FFmpeg`. Then open a new terminal and check it with
   `ffmpeg -version`.
3. **Python packages**: in the project folder, run:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```
   (`run.ps1` also does this the first time if `.venv` is missing.)
4. **API keys**: copy `.env.example` to `.env` and fill in what you use:
   - `ANTHROPIC_API_KEY`: optional. Claude picks the moments; without it a built-in scorer does.
   - `YOUTUBE_API_KEY`: needed only for the daily trending job. Get it free from the Google Cloud Console
     (YouTube Data API v3).

   `server\daily.py` reads `.env` by itself. For `run.ps1` and the `reels\` scripts, set the same variables in
   PowerShell first (`$env:ANTHROPIC_API_KEY = "..."`) or add them as Windows user environment variables.
   Never commit `.env`. It is already in `.gitignore`.
5. **Your channels**: copy `channels.example.json` to `channels.json`, then replace the example handles with your
   own accounts. Fill in `niche`, `platforms`, `avoid`, `post_times_ist` and `max_posts_per_day`. Keep
   `"frame": "setup_main"` for the desk-frame look, or remove `frame` / `frame_variants` to render without a frame.
   `channels.json` stays private (it is in `.gitignore`).
6. **Campaigns**: copy `campaigns\_template\` to `campaigns\<name>\` for each campaign. See `campaigns\README.md`.
7. **Claude Code (optional)**: open Claude Code in the project folder to use the skills in `.claude\` (find-campaigns,
   campaign-pack, channel-review, meta-schedule, gamer-organic). The ones that use a browser need Claude in Chrome
   (`claude --chrome`). `CLAUDE.md` holds the rules they follow. `setup\claude\` holds an older copy of the skills.
8. **Voice tools (optional)**: these need Python 3.11. Run `powershell -ExecutionPolicy Bypass -File setup_voice.ps1`.

Folders such as `inbox\`, `own\`, `learn\`, `discover\`, `jobs\` and `clips\` are created as you use the tool. They
are git-ignored because they hold your own footage and results.

## Run

```powershell
.\run.ps1
```

Then open http://127.0.0.1:8000/youtube-clip-maker. The `/twitch-clip-maker` and `/kick-clip-maker` routes serve the same page with that platform selected.

Requires Python 3.11+ and `ffmpeg`/`ffprobe` on PATH. `run.ps1` creates `.venv` and installs `requirements.txt` the first time it runs.

| Env var | Effect |
|---|---|
| `ANTHROPIC_API_KEY` | Claude (`claude-opus-5-5`) picks the moments from the transcript. Without a key, a built-in heuristic scorer picks them. |
| `CLIPPER_MODEL` | Overrides the Claude model. |
| `CLIPPER_WHISPER_MODEL` | Sets the faster-whisper size: `tiny`, `base` (default), `small`, `medium`, or `large-v3`. |

## Pipeline (`server/pipeline.py`)

1. **Download** with yt-dlp, up to 1080p. Videos longer than 3 hours are rejected, matching the original site.
2. **Transcribe** with faster-whisper, including word timestamps and language auto-detection. It runs on an NVIDIA GPU through the `nvidia-cublas-cu12` and `nvidia-cudnn-cu12` wheels, trying float16, then int8_float16, then int8. Without a usable GPU it falls back to CPU int8. Set `CLIPPER_DEVICE=cpu` to force the CPU. On a GTX 1650, `base` runs about 12× realtime on the GPU versus 3.5× on the CPU, and `small` runs about 5× on the GPU.
3. **Pick moments** that are 20–60 s long and don't overlap. Claude does this with structured JSON output when a key is set; otherwise the heuristic scorer does. Clip edges are snapped to word boundaries.
4. **Face-track**: one ffmpeg pass decodes only the clip's window at 2 fps and 960 px wide. OpenCV takes the largest face as the speaker. The track is median-smoothed with a dead-zone and becomes a panning `crop` expression.
5. **Render** to a 9:16 crop scaled to 1080×1920, with ASS captions burned in, three words at a time and the current word highlighted. Encoding uses the NVIDIA GPU (`h264_nvenc`) when available and otherwise `libx264`; set `CLIPPER_ENCODER=cpu` to force x264. Downloads prefer H.264 over AV1/VP9 because those decode several times slower. One 50 s clip takes about 25 s on a GTX 1650, down from about 6 min.

Jobs run one at a time in a background thread. Output goes to `jobs/<id>/`, which holds `clip_NN.mp4`, `clip_NN.jpg`, `transcript.json`, and `job.json`. Finished jobs reload when the server restarts.

## Daily trending clips (08:00 IST)

`server/daily.py` takes the top 20 videos from YouTube's US "most popular" chart. It drops live videos, anything under 90 s or over 3 h, and videos with no speech. It finds up to 5 moments per video, then renders the 50 best overall. Every video gets its single best clip first, and the remaining slots go to the highest scores.

```
clips/2026-10-29/
  01_mrbeast_i-survived-50-hours.mp4   (+ .jpg thumbnail)
  ...
  manifest.csv    rank, file, score, clip_title, source_title, channel, source_url (timestamped), transcript, uploaded
  manifest.json
  run.log
```

Setup:
1. Put a YouTube Data API v3 key in `.env` as `YOUTUBE_API_KEY=...`. The key is free from Google Cloud Console.
2. Run `powershell -ExecutionPolicy Bypass -File register-task.ps1` once. It registers the "Clipper Daily Clips" task, which starts late if the PC was off or asleep at 8:00.
3. Run it manually with `.\daily.ps1`. Add `--force` to redo today, `--clips 10 --videos 3` for a quick test, or `--date 2026-10-29` to name the folder.

From Claude Code in this folder, `/daily-clips status` or `/daily-clips run`.

## API

- `POST /api/jobs` with `{"url": "...", "max_clips": 6, "captions": true, "highlight": "#FFE600"}` returns `{"id": ...}`
- `GET /api/jobs/{id}` returns the status, stage, progress, and clips
- `GET /api/jobs` returns recent jobs
- `GET /media/{id}/clip_01.mp4[?download=true]`
- `GET /docs` shows the OpenAPI UI

## How it was reverse-engineered

The live page was loaded in headless Chrome over CDP and captured with REA (`capture_web_screenshot`) and a passive DOM/computed-style dump. That capture gave the copy, layout, and design tokens: `--vg-blue #1677f2`, `--vg-surface #f8f9fc`, Inter with Montserrat 900 for headings, and the cycling headline (clips → Reels → Shorts → TikToks). On the live site, "Get clips" only redirects to `/auth/sign-up` and the clipping happens server-side behind the paywall. This project implements that missing backend locally.

The brand name, logo, and sample videos are not copied. "Clipper", its mascot, and the CSS phone mockups are original placeholders.
