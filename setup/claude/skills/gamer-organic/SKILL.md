---
name: gamer-organic
description: Make the account's organic (non-ad) gaming posts from the user's own gameplay recordings - POV NPC-reaction reels and other gamer formats - with captions, a plan and reminders that fit around the campaign posts. Use when the user drops recordings in own\ or asks for organic / gamer posts.
---

# Gamer organic posts

Purpose: make the account look and grow like a **gamer's** account, not an ad feed. These posts earn nothing
directly; they bring followers, teach Instagram the gaming niche, and give the account original content next to
the campaign posts. Never put campaign footage, #Ad or brand tags in these posts, and never put organic tricks
(voice, mods) into campaign posts. Follow CLAUDE.md. Python: `.venv\Scripts\python.exe -P` from the project folder.

Output, in `campaigns\own_<game>_<date>\`: `clips\`, `covers\`, `plan\posts.json` (all `"organic": true`),
`own_<game>_<date>_Plan.pdf`, `schedule.ics` (reminder: pin the comment and reply; nothing to submit).

## The account persona
One gamer, one main game, one recurring series. Viewers follow because they expect the next episode.
- Keep the same series format, opening style and caption style across posts. Numbering is optional.
- Content that says "this is a person who plays": first-person POV, real reactions, the user's voice when used.

## The page style (modelled on a reference gaming page, checked 2026-11-15)
16.6K followers, 106 posts, 1-2 reels a day. Every reel is the same template: a static shot of a desk with a
monitor, blue LED backlight and a keyboard; the game plays on the monitor; one white hook line sits above the
monitor for the whole reel; a trending track is added on Instagram. Footage is cinematic trailers and cutscenes
of big games (Assassin's Creed, God of War, MW4, Watch Dogs). Results swing widely: 15.8M, 7.1M, 5M, 1.4M plays
on the hits, 5K-50K on most others, so volume and consistency matter more than any single reel.
We model the **template and hook style**, in our own words, never the creator's captions, name or photo.

- **Frame:** the channel's permanent desk frames, real photos: `frames\setup_main` (blue desk, main) and
  `frames\setup_red` (red desk, variant), built by `reels\make_photo_frame.py` (see CLAUDE.md → Frames). Every
  reel, organic and campaign, renders through `reels\edit_viral.py`, which picks them from `channels.json` by
  itself (red on every 5th clip, never two in a row) with the OLED look at the approved `oled` 1.0, so the page
  looks like one desk. Leave `frame`, `layout` and `oled` out of `edit.json`. Never a different room each post,
  and never redraw or regenerate the rooms. They are stock photos (Unsplash), not the user's room: don't claim
  in captions that it's the user's setup.
- **Hook line (on screen all reel, max 12 words, 1-2 emoji from 🥶 ☠️ 🔥 🤯):** patterns that work there:
  "N years later and nothing has topped this ___" · "I forgot for a second this is just a game" ·
  "POV: you picked ___" · "Smoothest ___ in ___ trailers" · "___ vs ___" · "Cinematic gaming at its peak" ·
  "This ___ felt more like a movie than a game". Must be true of the clip; no fake claims.
- **Caption:** the hook reworded in one line + up to 5 hashtags (game name, #gaming, platform).
- **Length:** 12-40 s. Cut to the strongest 2-4 shots of the scene and end on a cliffhanger so it loops.
- **Music:** don't bake commercial music into the file. Add a trending track from Instagram's own audio library
  when posting (in the Instagram app; Business Suite scheduling may not offer it, so note "add audio in app").
  On YouTube use the Shorts audio library the same way.

### 0. Setup-frame cinematic (the page's main organic format)
Footage: **official trailers and cinematics from the publisher's own channel only**, where
`own\game_policies.json` allows it, plus the user's own recordings. Never another creator's reel, edit or
gameplay capture: Instagram stops recommending accounts that repost others' content, and it risks a copyright
strike on the account that carries the paid campaigns. Non-violent scenes only (entrances, reveals, landscapes,
transitions, character looks); the reference's most violent hits are exactly what got this account restricted.
Download the official trailer with yt-dlp into `own\<game>\` only after telling the user the title, channel and
size and getting a yes.

## Formats (best first)

### 1. POV NPC interaction (the reference format)
Reference: a GTA 5 POV page (94 posts, 23.4K followers, checked 2026-11-10). Every post is the same
format: first-person view, an NPC walks up and looks straight into the camera, the player offers something
(a burger, a snowball…), the NPC reacts. Most posts get 40K-130K views; the best ("Will you eat a burger") got
3M views, 142K likes, 2,075 comments and 89.4K sends. Captions are one short line ("Want to eat a burger for
free", "Friendliest citizen in los santos"), audio is the game's own sound, no hashtags needed.
Why it works, in the platforms' own terms:
- **Hook in the first second** (Instagram says hook in 3 s): a face looking at you, close up, fills the frame.
- **Sends** (Instagram's top signal for non-followers): absurd, harmless choices people forward to friends.
- **Comments**: viewers explain or joke about the reaction; a choice question invites answers.
- **Rewatch**: short, one beat, the reaction lands at the end so people loop it.
- **Series**: 94 posts of one format = an account people follow.
Our version: **non-violent only**. Offer food, gifts, money, flowers, a high five, a dance; NPCs reacting with
surprise, joy, confusion, refusal. No punching, slapping, fire, weapons, police fights, ragdolls of hurt or dead
NPCs: two of the user's reels were restricted for violence, and the reference account's violent posts did worse
than its burger posts anyway.

### 2. Other gamer formats (when the game or footage suits)
Hidden details, "X vs Y" comparisons (graphics, old vs new), satisfying moments, funny physics without anyone
getting hurt, first reactions to a new official trailer (Nintendo only, see `own\game_policies.json`).

## Game and footage rules
- Footage: **only gameplay the user recorded**, in `own\<game>\`, or official trailers where the policy allows
  them. Never other creators' gameplay, never campaign footage, never leaks.
- Check the publisher in `own\game_policies.json` first. GTA 5 (Rockstar/Take-Two): its policy allows gameplay
  for non-commercial use and removes isolated cutscenes and spoilers. Organic posts aren't paid, but the same
  account earns from campaigns. Tell the user this once and let them decide; if they go ahead, record **story
  mode only**, no GTA Online, no cheat or mod menus in multiplayer, no story cutscenes. Many GTA accounts post this
  format, but takedowns are possible and a strike would hit the account that carries the campaign posts.
- Prefer non-violent games when picking a new one.

## Recording guide (give this to the user the first time)
- 1080p or higher, 60 fps, game audio only (no music). NVIDIA app: Alt+Z → Record; or OBS.
- First-person camera. Record long sessions (20-30 min); don't stop for each attempt, the tool finds the moments.
- One action per encounter: walk up, offer the item, let the NPC react fully, wait 2 s, move on.
- Mix places (beach, gym, street, shop) and NPC types; faces close to the camera.
- Drop the files in `own\<game>\`.

## Steps
0. **Playbook.** Read `learn\<channel>\playbook.md` (run the **channel-review** skill if it's missing with 5+
   posts, or older than 7 days). About 70% of the posts follow "Do more", about 30% are its planned tests; give
   every clip `"tags": {"format", "game", "footage", "test"}`.
1. **Folder.** `campaigns\own_<game>_<date>\` with `source\` (symlink or copy the new recordings) and
   `rules.json` = `{"name": "Own posts: <game>", "violence_banned": true, "caption_notice": "<from
   game_policies.json, or empty>"}`.
2. **Moments.** `reels\analyze.py <folder>` then `reels\find_moments.py <folder> --min 6 --max 15 --top 25
   --per-source 8` (violent windows are dropped by default).
3. **Pick by eye.** For each candidate, make a 1 fps sheet of the window
   (`ffmpeg -ss <start> -t <len> -i <src> -vf fps=1,scale=320:-1,tile=6x3 sheet.jpg`) and keep only clips where:
   a face is clear in the first second, the reaction is complete, and nothing from the violence list appears.
   Trim so it starts on the approach (no walking-around intro) and ends 0.5-1 s after the reaction. Pick 7-10.
4. **On the desk frame.** Every reel for a channel with a `frame` plays on the channel's desk frame (see "The page style").
   Write `edit.json` in the folder: one clip per pick, its beats from the recording (`src`, `start`, `end`),
   a short hook above the monitor, no `frame`/`layout` keys, then run `reels\edit_viral.py <folder>`. Set
   `focus` so the NPC's face sits in the middle of the screen, and use a gentle `zoom` push-in so the face fills
   the monitor. No captions burned in unless there's speech.
5. **Covers.** `edit_viral.py` writes one per clip; set `cover_at` in `edit.json` to the moment the reaction
   peaks.
6. **Voice (optional).** Only if the user wants it for this series: 1 short line in the user's voice per clip via
   `reels\voice.py` (see CLAUDE.md), and `"ai_voice": true` on cloned-voice posts so the AI label reminder fires.
   The reference format works without voice.
7. **Captions.** One line, max 8 words, written like a gamer talking: a choice question or a deadpan line
   ("Would you take the burger?", "He was NOT ready for this"). No clickbait or false claims. 0-3 hashtags
   (game name + #gaming). Add the policy's `caption_notice` if any. Pinned comment: a question that invites
   answers ("What should I give him next? 👇").
8. **Plan.** Write `plan\posts.json` with `"organic": true` on every post. One organic post a day, at a time
   the campaign plans don't use: read every active campaign's `plan\posts.json` for the same dates and keep the
   whole account at **3 posts a day or fewer, 120+ min apart**. Default organic slot 18:00 IST, then 16:00.
9. **Check.** `reels\check_plan.py <folder>`; fix all FAILs. Then confirm the combined day counts across all
   active plans yourself.
10. **Plan PDF.** Build `own_<game>_<date>_Plan.pdf` from `reels\templates\plan_pdf_template.py` like the campaign
    pack, with: the series idea, one card per post (time, clip, cover, caption, pinned comment), "How to schedule
    in Meta Business Suite", and "When the reminder fires: pin the comment, reply for an hour". Open the pages
    and check them.
11. **Tell the user** the folder, number of posts, the first time, and to import `schedule.ics`.

## Learning from results
The **channel-review** skill does this: it pulls each post's results, joins them with the clip's recipe and
updates `learn\<channel>\playbook.md`. Run it weekly and before each new batch.
