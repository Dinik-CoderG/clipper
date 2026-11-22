---
description: Run the whole clipping pipeline for one channel - review results, find campaigns, make the pack, schedule
argument-hint: <channel> [organic]
---
Run the full pipeline for the channel: $ARGUMENTS
(If no channel is given and channels.json has more than one, ask which. "all" = one channel after another.)

Do these stages in order, without stopping between them except at the points marked ASK:

1. **channel-review** skill, only if `learn\<channel>\playbook.md` is missing (and the channel has 5+ posts) or
   older than 7 days. Otherwise just read the playbook.
2. **find-campaigns** skill: rank the top 5 for this channel, including enrolled campaigns that can take another
   batch.
   ASK: which campaign.
   ASK: one yes to join it and download its footage (skip for a campaign already joined with nothing new to
   download).
3. **campaign-pack** skill on that campaign: clips, covers, posting-plan PDF, schedule.ics.
4. If the arguments include "organic": **gamer-organic** skill for the same days, fitted around the campaign posts.
5. **meta-schedule** skill.
   ASK: one yes for the full list of posts before anything is scheduled.
6. Finish with a short summary: campaign, number of clips, first post time, what was scheduled, and what the user
   still does by hand (**schedule these clips yourself: every clip over 10 MB, listed with date, time, file and
   caption**; submit links from the phone when the reminders fire; add trending audio in the Instagram
   app on organic posts; any bio change the campaign requires).

All rules in CLAUDE.md apply. If a stage stops on a login page, a warning or an error, say which stage and what
the page says, and continue from that stage once the user has dealt with it.
