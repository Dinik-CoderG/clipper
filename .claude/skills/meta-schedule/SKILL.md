---
name: meta-schedule
description: Schedule a campaign's (or organic plan's) posts in Meta Business Suite (business.facebook.com) and optionally YouTube Studio through Claude in Chrome, from the campaign's schedule.csv, after one yes from the user for the whole list. Use when the user says "schedule it", "schedule <campaign> on Meta / Business Suite", or at the end of campaign-pack when they accept.
---

# Schedule posts with Claude in Chrome

Input: `campaigns\<slug>\schedule.csv` (written by `reels\check_plan.py`) plus the clips and covers it points to.
Output: the posts scheduled in Meta Business Suite (Instagram) and, if the user includes it, YouTube Studio, a log
in `campaigns\<slug>\scheduled.json`, and a screenshot of each scheduled post in `campaigns\<slug>\scheduled\`.

Follow CLAUDE.md. This skill puts posts on the user's public account, so the approval rule below is not optional.

## 0. Before anything
1. Chrome tools must be present (session started with `claude --chrome`, or `/chrome` → Enabled). If they aren't,
   tell the user to restart with `claude --chrome` and stop.
2. Re-run `reels\check_plan.py <slug>`. If anything FAILs, stop: fix the plan first.
3. Clips are rendered at top quality with no size limit. Claude in Chrome can only upload files of **10 MB or
   less**, so read `clips\sizes.json`: posts whose clip is `"upload": "claude"` you schedule; posts marked
   `"manual"` the user schedules by hand. **Never re-render, shorten or compress a clip to make it fit.**
4. Skip posts whose time is less than 20 minutes away or already past; tell the user which.
5. Read `scheduled.json` if it exists: posts already logged as scheduled are skipped (never schedule twice).

## 1. One yes for the whole list
Show the user one table: date, time (IST), platform, clip file, size, first line of the caption, cover, and who
schedules it (Claude, or "you: over 10 MB"). The yes covers only the rows marked Claude. Say plainly:
"I'll schedule these N posts on <account> in Meta Business Suite [and YouTube Studio]. Reply yes to schedule all
of them." Wait for an explicit yes in chat. That yes covers exactly the listed posts with exactly those files,
captions and times. Anything not in the table (another post, a changed caption, a boost, a different account)
needs a new yes. If the user changes something, update `posts.json`, re-run check_plan, and show the table again.

## 2. Instagram, one post at a time (Meta Business Suite)
Meta's screens change; follow the goals, not exact button names. Use a new tab.
1. Open `https://business.facebook.com/latest/content_calendar` (Planner). If a login, checkpoint or CAPTCHA page
   appears, stop and ask the user to handle it in that Chrome window, then continue.
2. Confirm the account picker shows the Instagram account of this plan's channel (`rules.json` → `channel` →
   `channels.json` → `instagram`). With several channels this matters most: never schedule on another channel's
   account. If the right account isn't selectable, stop and ask.
3. **Duplicate check:** look at the planned day in the Planner. If a post with the same time and caption start
   already exists, log it as already scheduled and skip it.
4. Create → **Reel**. Post to: **Instagram only** (untick Facebook unless the user asked for both).
5. Upload the clip with the file-upload tool, using the absolute path from `schedule.csv`
   (`<project folder>\campaigns\<slug>\clips\...`). Wait until the upload finishes.
6. Caption: type it exactly as in `schedule.csv`, line breaks included. Then read the field back and compare with
   the CSV; fix any difference (emoji or line breaks dropped) before going on.
7. Cover: if the composer has a cover / thumbnail option, upload the matching `covers\` file. If not, note
   "cover: set in app" for the user.
8. Leave music off. Don't turn on Trial reel, boosting, paid partnership changes, or any ad option. Keep
   "Share to Feed" on if offered.
9. Scheduling options → **Schedule** → set the date and time from the CSV. Check the time zone the composer shows;
   if it isn't India Standard Time, convert so the post goes out at the IST time in the plan and tell the user.
10. Take a screenshot of the filled composer, save it to `scheduled\<id>_instagram_before.png`, then click
    **Schedule** (the final button). Never click Publish now.
11. Confirm the post appears in the Planner at the right day and time; screenshot to `scheduled\<id>_instagram.png`.
12. Append to `scheduled.json`: `{"id", "platform": "instagram", "date", "time_ist", "file", "status": "scheduled",
    "checked_at"}`. Then the next post.

If anything unexpected appears (new terms, a policy warning, an "eligible to boost" pop-up, a music-rights notice,
an error after clicking Schedule), stop and tell the user what the page says. Never accept terms or change account
settings. If a Schedule click may have gone through but you aren't sure, check the Planner before trying again.

## 3. YouTube Shorts (only if the plan has YouTube rows and the user's yes included them)
1. `https://studio.youtube.com` → check the channel name → Create → Upload videos → the same clip.
2. Title = `yt_title`; description = caption; Show more → tick **Paid promotion** for campaign posts; audience:
   No, it's not made for kids; altered or synthetic content: Yes only when `ai_voice` is true.
3. Visibility → **Schedule** → date and time from the CSV (check the time zone shown).
4. Screenshot, click Schedule, confirm it's listed under Content as Scheduled, log it like Instagram.

## 4. Pace and account safety
- One post at a time, at human speed; never parallel tabs posting at once.
- At most the posts in the approved table; the plan already keeps the account at ≤3 posts a day, 120+ min apart.
- Meta's terms forbid automated *data collection* without permission; scheduling your own posts from your own
  signed-in browser is ordinary use of Business Suite, but it is still automation, so keep it to the approved
  list and stop at any warning.

## 5. Finish
Tell the user: how many posts are scheduled (and any skipped, with why), then a clear list **"For you to
schedule by hand"**: each manual post with its date and time, clip file and size, cover file, and the caption
ready to paste (also in the posting-plan PDF). Also say the first post time, that the phone
reminders in `schedule.ics` still apply (submit the link on Content Rewards when each goes live), and any cover
they must set in the app.
