# Clipper

Local tool for making paid short-form clips for Content Rewards campaigns (Instagram Reels, YouTube Shorts,
TikTok) and clips from long videos. See README.md (long-video engine, `server\`) and campaigns\README.md (campaign
engine, `reels\`). Python: `.venv\Scripts\python.exe -P` from the project folder.

## Commands and skills
- **find-campaigns** skill ("find campaigns for <channel>"): reads Content Rewards in Chrome, ranks the top 5 for
  that channel (`channels.json`, `reels\rank_campaigns.py`, `reels\campaign_status.py`; enrolled campaigns that ran out of
  clips count as options when they still have footage and budget), and after the user picks and says yes, joins it,
  downloads brief + footage, and continues into campaign-pack. Full pipeline: find-campaigns → campaign-pack →
  meta-schedule.
- **channel-review** skill ("review <channel>"): the learning loop. Pulls post results in Chrome, joins them with
  each clip's recipe (`reels\learn.py`) and writes `learn\<channel>\playbook.md`: do more, stop, test next. One
  playbook per channel; the other skills read it before every batch and tag clips so results can be traced.
- **campaign-pack** skill (`/campaign-pack`, or "make the pack for this brief"): brief PDF in `inbox\` → edited
  clips, covers, posting-plan PDF, phone reminders (`schedule.ics`), then (one yes) scheduling via meta-schedule.
- **meta-schedule** skill: schedules a plan's posts in Meta Business Suite (and YouTube Studio) through Claude in
  Chrome. Needs Claude Code started with `claude --chrome`; one explicit yes for the whole listed schedule.
- `/daily-clips`: the daily trending job (never post its output unless a campaign covers that source).
- **gamer-organic** skill (`/gamer-organic`): the user's own gameplay in `own\<game>\` → organic (non-ad) posts,
  mainly the POV NPC-reaction series, planned around the campaign posts.
- Voice for organic posts: one-time `setup_voice.ps1`, then `reels\voice.py enroll <recording>`; per clip
  `voice.py make` → `render.py` → `voice.py mix`. The voice sample lives in `likeness\` and never leaves this PC.

## Scripts (reels\)
analyze.py · subs.py · gore_check.py · find_moments.py (ranks moments: hook, retention, payoff, visible change, loop,
brightness, YouTube replay heatmap) · edit_viral.py (beats: cuts, zooms, word captions, end card; no whoosh; top quality, no size limit) ·
make_photo_frame.py (builds the desk frames in frames\ from the real desk photos) · speech_edit.py + speaker.py + transcribe.py (talking footage: word-timed captions, pause/um trimming,
full-screen framing on whoever is speaking, GPU transcription) · make_setup_frame.py (old
drawn frame, not used) · render.py (old TV-frame style) · make_covers.py · check_plan.py (rules check, writes schedule.csv/.ics) ·
voice.py (+ voice_worker.py in .venv-voice) · templates\plan_pdf_template.py

## Rules that always apply
- Clip quality comes first: never shrink, shorten or recompress a clip to fit an upload limit. Clips over 10 MB
  (Claude in Chrome's upload limit) are scheduled by the user by hand and listed in the summary.
- Never read or print `.env` (API keys).
- Footage only from the campaign's official folder. Never use other creators' videos in a campaign post.
- The brief beats every default: tags, disclosure position, hashtag count, music, length, banned words.
- Captions and hooks state only facts from the brief or the brand's official pages (`brief\facts.md`).
- Minimum payout is per clip: views needed per clip = min payout / rate × 1,000.
- Account safety: at most 3 posts a day per account, 120+ min apart; no bots, auto-posters that need a password,
  boosting, ads, Trial Reels, hidden likes, caption edits after posting, or deleting before the keep-live date.
- Instagram allows 5 hashtags per post. Reels over 3 minutes aren't recommended.
- No violent scenes or wording, whatever the brief allows: Reels with violence get restricted and get 0 views.
  Violent windows are dropped by find_moments.py by default; every clip is also checked by eye.
- The user's voice (cloned or recorded) goes on organic posts only, never campaign posts. Cloned-voice posts
  must carry the AI label on Instagram and YouTube. Never upload or share `likeness\`.
- No whoosh or other transition sound on cuts, in any clip, reel or short.
- Lip sync must be exact. YouTube windows are cut with `reels\hls_window.py` (fetch_windows.py does it), never
  yt-dlp `--download-sections`: with YouTube's separate video/audio streams that left the picture up to 6 s behind
  the voice. Check a doubtful window with `reels\av_offset.py` / `audio_offset.py`.
- Streamer clips (layout `stack`): facecam full-width on top, the WHOLE game frame below (never cropped), the
  streamer's own small facecam inside the game left as it is, not blurred: a blurred box looks broken.
- Every clip needs a real edit (beats every 1-2.5 s, hook in frame 1, captions); raw re-uploads and
  long static shots hurt the whole account's reach. Pick moments by looking at timestamped sheets, not scores alone.
- Don't post, schedule, submit or join anything without the user's yes for that action.
- Channels are listed in `channels.json` (start from `channels.example.json`); every campaign folder names its
  channel in `rules.json`. Never post a campaign on a channel outside its niche, and never schedule on another
  channel's account.

## Frames (channels with a desk `frame` in channels.json)
- The desk frame is for **gameplay, trailers and cinematics** only. Screen recordings and website/app/product
  promos render without it: set `"layout": "wide"` (or `"full"`) on each clip in `edit.json`.
- Every gameplay/trailer clip for a desk-frame channel, campaign and organic, plays on the desk frame with the OLED
  look: `frames\setup_main` (blue desk, the main frame) and `frames\setup_red` (red desk, a variant). `edit_viral.py`
  picks them from `channels.json` (`frame`, `frame_variants`): the variant lands on every 5th clip, never two in a
  row. Don't set a `frame` or a non-setup `layout` in `edit.json` unless the brief needs full-screen footage.
- OLED look: `"oled"` in edit.json, 0-1.5, default and approved value **1.0**. It also dims the room ~18% and adds a
  soft glow in the footage's colours on the wall and desk only; the black bezel and monitor body stay black (a lit
  band along the screen's edge looks fake). Keep the room's LED strip as it is in the photo.
- The rooms are real Unsplash photos (free licence), not the user's own room: never say "my setup" in captions.
  Don't redraw or regenerate them. To rebuild: `reels\make_photo_frame.py 8_blue_desk setup_main` and
  `reels\make_photo_frame.py 7_red_desk setup_red`. `make_setup_frame.py` would overwrite nothing (it writes
  `setup_drawn` by default).
- A channel with no `frame` in `channels.json` renders without one.
