---
name: campaign-pack
description: Turn a Content Rewards campaign brief PDF into ready-to-post clips, covers, a posting-plan PDF, phone reminders to submit the links, and (after one yes) the posts scheduled in Meta Business Suite through Claude in Chrome. Use when the user drops a brief in inbox\ or says "make the pack / clips for this campaign".
---

# Campaign pack

Pipeline: **find-campaigns → campaign-pack → meta-schedule**. If the user gives no brief PDF and names no campaign
folder, start with the **find-campaigns** skill (top 5 for a channel, they pick, it joins and pulls the files),
then come back here. If `campaigns\<slug>\` already has the brief and footage (find-campaigns made it), skip the
parts of steps 1-2 that are done.

Input: a brief PDF (newest PDF in `inbox\` if none is named) and, if given, the campaign's Content
Rewards URL. Output, in `campaigns\<slug>\`:

```
clips\                      the Reels / Shorts, ready to upload
covers\                     one cover per clip, same file names
<slug>_Posting_Plan.pdf     what to schedule, when, captions, hashtags, audio, pinned comments, rules
schedule.ics                phone reminders: "SUBMIT LINK" the moment each post goes live, plus 30-day markers
schedule.csv                the same schedule as a table
```

At the end, offer to schedule the posts with the **meta-schedule** skill (Claude in Chrome, one yes for the whole
list). Without that yes, nothing is posted or scheduled. This skill never submits links or joins campaigns. Follow CLAUDE.md throughout. Python: `.venv\Scripts\python.exe -P`
from the project folder. Keep a task list.

## New batch for a campaign that already has a folder
When the campaign folder already has posted clips (find-campaigns says "continue", or the user asks for more
clips): keep `rules.json` and `brief\`, re-read the brief and campaign page for changes, then run steps 3-9 with:
- `reels\campaign_status.py` → `discover\status.json` lists `unused` footage files and `used_windows`. Build the new
  clips from unused files first; from used files only take **different scenes** (no overlap with a used window).
  Never re-render or re-post an earlier cut.
- Read our results for the earlier batch (find-campaigns `local` block, or ask). Keep what cleared the payout
  line; if nothing did, change the format, hook style or footage type instead of making more of the same, and
  say what you changed and why.
- New ids continue the series with a batch prefix (`b2_01_...`). **Append** to `edit.json` and `plan\posts.json`;
  don't remove earlier entries. Render only the new ids (`edit_viral.py <slug> b2_`).
- Respect the campaign's limits (`max_reposts`, submissions per account) across all batches.

## 0. What this channel has learned
Read `learn\<channel>\playbook.md`. If it's missing and the channel has 5+ posts, or it's older than 7 days,
run the **channel-review** skill first. Then build this batch from it: about 70% of the clips follow "Do more",
about 30% are the tests listed in the Editor's notes (one change each), and nothing under "Stop or change" is
repeated unchanged. Give every clip in `edit.json` `"tags": {"format", "game", "footage", "test"}`. With no
playbook (new channel), work from the brief, the niche outliers and the default rules.

## 1. Brief → rules
1. Read the whole brief; if it links a Google Doc, read that too (`/mobilebasic` URL = plain text).
2. Pick a short slug (e.g. `warzone_s1`). Copy `campaigns\_template\` to `campaigns\<slug>\`, move the PDF to `brief\`.
3. Write `rules.json` (fields as in `campaigns\_template\rules.json`) from the brief and the campaign page only.
   Add `"channel": "<id>"` (from `channels.json`; ask which channel if there is more than one). Unknown = null. If the brief or campaign page gives a deadline to submit the link after
   posting, set `"submit_within_min": <minutes>`: the reminders then say "SUBMIT BY hh:mm" with a last-call
   alert, and step 6 must use post times when the user can submit (ask them; never guess). `violence_banned` is **always true** for this account, whatever the brief says: two Reels were
   restricted for violence and got 0 views. Put official proper names that contain violent words (map, mode or
   product names) in `allowed_names`.
4. Write `brief\facts.md`: every fact captions may use (dates, names, features), each with its source.
5. Show the user a short rules card and any ambiguity as a question for the campaign team. Keep working meanwhile.

## 2. Footage
- Only from the folder the brief links. Public Google Drive: tell the user the file count and rough size, and on
  their yes use `gdown --folder <url> -O campaigns\<slug>\source` (pip install gdown into .venv if missing).
  MediaSilo, Dropbox or anything behind a sign-in: ask the user to download it into `source\` and wait.
- Non-mp4 → `ffmpeg -i in.mov -c copy out.mp4`.

## 3. What's working
If vidIQ tools are available: check credits, then at most 2 `vidiq_instagram_tiktok_outlier_search` calls for the
campaign topic (last 14 days, min 10K views). Otherwise web search the campaign hashtag. Write
`research\outliers.md`: winning formats, proof (views, × usual, link), and whether the allowed footage can do it.

## 4. Best moments, no violence
1. `reels\analyze.py <slug>`, then `reels\gore_check.py <slug> <source>` for each source.
2. `reels\find_moments.py <slug> --min 2 --max 6 --top 30 --per-source 4` for **shots** (beats), and with the
   default `--min 7 --max 15` for whole moments. It ranks hook, retention, payoff, visible change (before -> after)
   and loop, and down-ranks dark or flat windows (marked DARK). Add `--heatmap <url>` if the footage is on the
   brand's YouTube channel.
3. **Look at the footage yourself; the scores only shortlist.** For every source you may use, make a timestamped
   sheet and open it:
   `ffmpeg -i <src> -vf "fps=1,scale=240:-1,drawtext=text='%{pts\:flt}':fontsize=20:fontcolor=yellow:box=1:boxcolor=black,tile=8x6" -frames:v 1 sheet.jpg`
   (fps=2 for short files). With `-ss`, the printed times start at 0, so add the -ss value back.
   Pick shots where something **visibly happens** (a change, a reveal, a transformation, a face/creature reaction),
   readable on a phone (not dark, not tiny), and true to the brief's top formats. Prefer the moments the brief or
   the file names call out (wow, reveal, satisfying, matched good/evil pairs).
4. **Violence review, by eye**, on the same sheets: reject any shot with a weapon fired or aimed at a person,
   someone shot, hit, stabbed, strangled or hanged, bodies or blood, a person on fire, a fist fight, or an explosion
   hitting people. Allowed: maps, vehicles, landscapes, lava/red scenery, menus, logos, weapons on their own,
   explosions with no people. When in doubt, leave it out.

## 5. Edit (cuts, zooms, sound, captions) and covers
Clips are **edited**, not trimmed: `reels\edit_viral.py` (format in its docstring) builds each clip from `edit.json`.
1. Write `edit.json`, one entry per clip (6-10 clips). Each clip is a **story in beats**:
   - Beat 1 (0-2 s) is the strongest picture, with the hook on screen from frame 1 (max 8 words, `*one word*`
     highlighted, true to `brief\facts.md`, no violent wording).
   - A new beat every 1-2.5 s: hard cut, `zoom` punch-in or slow push on every beat, `flash` on the big cuts.
     No whoosh or transition sounds on cuts: the user doesn't want them on any clip (21 Nov 2026); `sfx` stays
     `"none"` unless the user asks for a sound.
   - Captions (`text`) say what's happening in 2-5 words per beat; labels for comparisons (GOOD / EVIL, DAY 1).
   - Build to the payoff and show it fully; the last beat holds the payoff under the end card (`cta`) with the
     brand's call to action. Total 7-20 s unless the brief says otherwise.
   - `layout`: `full` (9:16 crop, for POV, characters, close action; set `focus` on the subject) or `wide`
     (square on a blurred fill, for landscapes and comparisons). `bright` for dark shots.
   - `brand`: the product name the brief wants shown.
   - **No frame for screen recordings:** when the footage is a website, app or product screen recording (not
     gameplay, trailers or cinematics), set `"layout": "wide"` on every clip so it renders without the desk frame.
   - **Channel frame:** if the channel in `channels.json` has a `frame`, `edit_viral.py` puts every clip on it
     by itself: e.g. `"frame": "setup_main"` (blue desk), with `setup_red` (red desk) on every 5th clip, never two
     in a row, and the OLED look at the approved `oled` 1.0. So leave `frame`, `layout` and `oled` out of
     `edit.json`; set `"layout": "full"` only when the brief forbids frames or needs full-screen footage. The hook
     stays above the monitor for the whole clip. This keeps campaign and organic reels looking like one page.
     The rooms are stock photos, not the user's room: no "my setup" in captions. See CLAUDE.md → Frames.
2. `reels\edit_viral.py <slug>`. It writes `clips\<id>.mp4` (top quality, no size limit; `clips\sizes.json` records each clip's size and whether Claude can upload
   it or the user schedules it by hand because it's over 10 MB)
   and `covers\<id>.jpg` (a real frame with the hook; no AI thumbnails).
3. **Check every clip** with a 2 fps sheet of the rendered file
   (`ffmpeg -i clips\<id>.mp4 -vf "fps=2,scale=180:-1,tile=12x2" -frames:v 1 check.jpg`): each beat shows what its
   caption says, hook and captions readable and inside the safe zone, nothing from the violence list, no beat
   that's dark or empty. Fix `edit.json` and re-render until every clip passes. Check each cover too.

## 5b. Talking footage (podcasts, streams, shows, interviews)
When the footage is people talking, the clip is built from the **words**, not from visual moments:
1. `reels\transcribe.py <slug>` (GPU when it works; `--windows a-b,c-d` for only parts of a long episode). Read
   `analysis\<source>\transcript.txt` and, if the file has its own subtitles, check names against them.
2. Pick 6-10 ideas, each one complete thought that makes sense with no context: a strong claim, a story with an
   ending, a number, a disagreement, a question with its answer. The first sentence must hook on its own.
   15-40 s unless the brief says otherwise.
3. Write `plan\clips_spec.json` (format in `reels\speech_edit.py`): for each clip its `segments` as
   [near-seconds, "first words", "last words"], the hook, tags, plus `source`, `brand`, `cta` and `fixes` for
   Whisper mishearings of names.
4. `reels\speech_edit.py <slug> --show` writes `edit.json`. It cuts on word boundaries, trims pauses over 0.45 s
   and "um/uh", gives every beat its word times (captions light up exactly as each word is spoken) and sets
   `"layout": "speaker"`: the editor finds whoever is talking in each beat and fills the screen with them
   (`reels\speaker.py`), 9:16 when the source is sharp enough, otherwise 4:5 on a blur. Set `focus` (and `lock`)
   in the spec only if it keeps picking the wrong person.
5. Render with `reels\edit_viral.py` and check each clip at 2 fps as in step 5: the speaker is the one framed in
   every beat, the face is whole and not cut by a tile edge, captions match the speech, no cut lands mid-word.
   No sound effects or flashes on talking clips unless the brief's style is loud.

## 6. Plan
1. Write `plan\posts.json` (fields as in `campaigns\_template\plan\posts.json`):
   - Platforms: only those the campaign pays **and** the user posts to (Instagram; YouTube Shorts when paid).
   - Times: the channel's `post_times_ist` in `channels.json` (default 20:30, then 23:00 IST). At most 3 posts a day
     **per channel**, counting every other plan with the same `channel` in its `rules.json` and its organic posts, 120+ min apart. Best clips first; if there's a launch date, a countdown post the
     day before.
   - Caption: keyword-first fan line + a question or send/tag prompt, required tags, then disclosure and hashtags
     exactly as `rules.json` says. Own words; never copy other clippers. `yt_title` (4-6 words) for YouTube.
   - `pinned`, `audio` (from the music rule), `why` (outlier proof).
2. **Organic posts are not part of this skill** (the `gamer-organic` skill makes them). But read any active
   `campaigns\own_*\plan\posts.json` for the same dates, so the whole account stays at 3 posts a day or fewer,
   120+ min apart. Never add a voice, mods or organic footage to campaign clips.
3. `reels\check_plan.py <slug>`; fix every FAIL and clear violent-wording WARNs, re-run until it passes. It writes
   `schedule.csv` and `schedule.ics`.

## 7. Posting-plan PDF
Copy `reels\templates\plan_pdf_template.py` to `plan\build_plan.py`. Make it read POSTS and DAYS from
`posts.json` and the rules checklist from `rules.json`, set `OUT_PDF` to `<slug>_Posting_Plan.pdf` in the campaign
folder, and include:
- a warning box with the 3 rules most different from the last campaign, plus "No violent scenes or wording";
- the plan at a glance, what's going viral, and the viral add-ons;
- **"How to schedule in Meta Business Suite"** instead of phone posting steps: Meta Business Suite → Planner (or
  Create Reel) → upload the clip from `clips\` → paste the caption exactly → add the cover from `covers\` if the
  composer offers it (otherwise set it in the Instagram app after it goes live: Edit → Edit cover) → Schedule →
  date and time from the plan. No music, no Trial Reel, Share to Feed on. For YouTube: YouTube Studio → Upload →
  title = `yt_title`, description = caption → Visibility → Schedule;
- day pages: one card per post (time, file, cover, hook, audio, caption, pinned comment, why);
- "When the reminder fires": open the post, copy the link, submit it on Content Rewards, pin the comment, reply for
  an hour;
- the rules checklist and sources.
Run it and open the PDF pages to check them.

## 8. Schedule (optional, with the user's yes)
Ask: "Schedule these N posts in Meta Business Suite now (and YouTube Studio)?" If the user says yes, use the
**meta-schedule** skill (it shows the full list and needs one explicit yes for it). If not, they schedule by hand
from the posting-plan PDF.

## 9. Finish
Add the campaign to **Active campaigns** in `campaigns\README.md`. Then tell the user, in a few lines: the folder,
clip count, first post time, and how to get the reminders. The first time (or on a new phone), have them test with
`reels\check_plan.py <slug> --test-reminder`, which writes `reminder_test.ics` with one alert 10 minutes later.
- **iPhone:** AirDrop or email `schedule.ics` to the phone, open it, Add All. The alerts in the file are used.
- **Android / Google Calendar:** on a computer, calendar.google.com → Settings → Import → `schedule.ics`. Google may
  not keep the alerts stored in the file, so after importing open one reminder event and check it has a
  notification; if the test reminder didn't alert, use the fallback.
- **Fallback that doesn't depend on the calendar:** in the claude.ai Clips project, ask Claude to "set phone
  reminders for <slug>". It reads `schedule.csv` and creates one scheduled task per post that sends a push
  notification to the phone at the post time, with the link to submit and the comment to pin.
