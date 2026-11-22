---
description: Run or check the daily trending-clips job (clips/<date>/)
argument-hint: "[status | run | run --force | <YYYY-MM-DD>]"
---
The daily job lives in `server/daily.py`, is launched by `daily.ps1`, and is scheduled in Windows Task Scheduler as "Clipper Daily Clips" (08:00 IST). Output goes to `clips/<YYYY-MM-DD>/` with `manifest.csv` (one row per clip, with an empty `uploaded` column for the user to fill), `manifest.json` and `run.log`.

Request: $ARGUMENTS

- `status` or empty: report the scheduled task's last/next run (`Get-ScheduledTaskInfo -TaskName "Clipper Daily Clips"`), then summarize today's folder: clip count, top 5 clips by score, and any `skipped`/`failed` lines from `run.log`. If today's folder has a `.running` file, say it's still running and show the last 10 log lines.
- `run` (optionally `--force`): start it in the background with `powershell -File .\daily.ps1 <flags>` and tell the user how to follow `run.log`.
- a date: summarize that day's folder the same way.
