"""Day-by-day posting-plan PDF (HTML printed to PDF with headless Edge).

TEMPLATE: copy this file to <campaign>/plan/build_plan.py, then replace the campaign-specific parts (POSTS, DAYS,
sound links, the warning box, rules checklist, accuracy notes, sources) with the new campaign's brief.
Covers are read from <campaign>/covers/. The example content below is from the finished MW4 campaign."""
from __future__ import annotations

import html
import subprocess
from pathlib import Path

HERE = Path(__file__).parent
OUT_HTML = HERE / "plan.html"
OUT_PDF = HERE.parent / "Posting_Plan.pdf"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

IG_SOUND = "https://www.instagram.com/reels/audio/<sound-id>"
TT_SOUND = "https://www.tiktok.com/music/<sound-id>"

ORIGINAL = "Original game audio only (dialogue is the hook)"
MUSIC = "Add C.R.E.A.M. (MW4 Remix) at {}% · game audio 100%"

POSTS = {
    "05": dict(file="05_ghost_and_gaz", title="Price vs Ghost AND Gaz", secs=32, audio=ORIGINAL,
               cover="Ghost's skull mask (~0:08) or Gaz at gunpoint (last 5s)",
               caption="Price vs Ghost AND Gaz in MW4 💔 Task Force 141 is completely broken. COD really did this @callofduty\n\nWhose side are you on? 👇 Send this to your duo",
               tags="#MW4 #CaptainPrice #TaskForce141"),
    "01": dict(file="01_refuse_the_order", title="Refuse the order", secs=37, audio=ORIGINAL,
               cover="The hanging-tree silhouette (last 5s)",
               caption="MW4 made me choose: hang him or refuse 😳 I refused… and this is what happened next. Can't believe that just happened @callofduty\n\nWould you have pulled the rope? 👇",
               tags="#MW4 #CallofDuty #ModernWarfare4"),
    "07": dict(file="07_makarov_alley_fight", title="Price vs Makarov (spoilers)", secs=28, audio=ORIGINAL,
               cover="Makarov's smirk close-up (~0:09)",
               caption="SPOILERS ⚠️ Price vs Makarov in MW4. \"You're gonna burn in hell.\" This one's been a long time coming. Can't believe that just happened @callofduty\n\nSend this to someone who hasn't finished the campaign 🤐",
               tags="#MW4 #CaptainPrice #Makarov"),
    "04": dict(file="04_rooftop_knife_fight", title="Price vs Ghost rooftop knife fight", secs=26, audio=MUSIC.format(20),
               cover="Ghost, knife raised against the sky (~0:13)",
               caption="Price vs Ghost. Glass rooftop. Knives. 🔪 MW4 went there. Can't believe that just happened @callofduty\n\nWho wins this one? 👇",
               tags="#MW4 #CaptainPrice #Ghost"),
    "02": dict(file="02_find_more_rope", title="\"We can find more rope\"", secs=36, audio=ORIGINAL,
               cover="Commander Ri Ju-Young close-up (~0:21)",
               caption="Commander Ri Ju-Young: \"If you are not with me, I'm sure we can find more rope.\" 🥶 And that last line… if you know, you know 👀 COD really did this @callofduty\n\nSend this to whoever's still playing the campaign",
               tags="#MW4 #CallofDuty #ModernWarfare4"),
    "06": dict(file="06_makarov_chase", title="Chasing Makarov across Manhattan", secs=31, audio=MUSIC.format(20),
               cover="Makarov on the billboard catwalk (~0:03)",
               caption="Chasing Makarov across Manhattan rooftops in a snowstorm 🏃‍♂️❄️ MW4's chase missions are unreal @callofduty\n\nSend this to the friend playing tonight 🎮",
               tags="#MW4 #Makarov #CallofDuty"),
    "03": dict(file="03_new_supreme_leader", title="The new Supreme Leader on TV", secs=16, audio=ORIGINAL,
               cover="The TV with the leader's face (~0:11)",
               caption="\"Who's that, a K-pop star?\" 💀 MW4 snack run turned into a North Korea briefing @callofduty\n\nTag the friend who'd say this 😂",
               tags="#MW4 #CallofDuty #ModernWarfare4"),
    "09": dict(file="09_nightclub_shootout", title="Nightclub shootout", secs=32, audio=MUSIC.format(25),
               cover="The pink cherry-blossom room (~0:04)",
               caption="This MW4 nightclub mission turns into a shootout through cherry blossom and forest rooms 🌸🌲 COD really did this @callofduty\n\nBest-looking COD level ever? 👇",
               tags="#MW4 #CallofDuty #ModernWarfare4"),
    "08": dict(file="08_paris_car_chase", title="Paris car chase", secs=21, audio=MUSIC.format(20),
               cover="The car flipping (~0:06)",
               caption="Hanging out the window in a Paris car chase 🚗💥 MW4 doesn't let up @callofduty\n\nDriver or gunner? 👇",
               tags="#MW4 #CallofDuty #ModernWarfare4"),
}

# (day, date, [(time IST, post id)], live-until date)
DAYS = [
    (1, "Thu 29 Oct 2026", [("8:30 PM", "05"), ("11:00 PM", "01")], "Sat 28 Nov"),
    (2, "Fri 30 Oct 2026", [("8:30 PM", "07"), ("11:00 PM", "04")], "Sun 29 Nov"),
    (3, "Sat 31 Oct 2026", [("8:30 PM", "02"), ("11:00 PM", "06")], "Mon 30 Nov"),
    (4, "Sun 1 Nov 2026", [("8:30 PM", "03"), ("11:00 PM", "09")], "Tue 1 Dec"),
    (5, "Mon 2 Nov 2026", [("8:30 PM", "08")], "Wed 2 Dec"),
]


def e(s: str) -> str:
    return html.escape(s).replace("\n", "<br>")


def add_time(t: str, minutes: int) -> str:
    hm, ap = t.split()
    h, m = map(int, hm.split(":"))
    h24 = (h % 12) + (12 if ap == "PM" else 0)
    tot = (h24 * 60 + m + minutes) % (24 * 60)
    h24, m = divmod(tot, 60)
    return f"{(h24 % 12) or 12}:{m:02d} {'PM' if h24 >= 12 else 'AM'}"


def post_card(pid: str, time: str) -> str:
    p = POSTS[pid]
    music = "C.R.E.A.M." in p["audio"]
    return f"""
    <div class="post">
      <img src="../covers/{p['file']}.jpg">
      <div class="pbody">
        <div class="ptitle"><span class="time">{time} IST</span> Clip {pid} · {e(p['title'])} <span class="muted">({p['secs']}s)</span></div>
        <div class="file">File: <b>clips/{p['file']}.mp4</b></div>
        <div class="kv"><b>Audio:</b> {e(p['audio'])}{' · <a href="' + IG_SOUND + '">IG sound link</a>' if music else ''}</div>
        <div class="kv"><b>Cover:</b> upload <b>covers/{p['file']}.jpg</b> (shown left) · TikTok frame: {e(p['cover'])}</div>
        <div class="label">Caption (copy exactly, keep the line breaks)</div>
        <div class="caption">{e(p['caption'])}<br><br>#Ad<br>{e(p['tags'])}</div>
      </div>
    </div>"""


def day_page(day: int, date: str, slots: list[tuple[str, str]], live_until: str) -> str:
    rows = [("7:30 PM", "Prep (15 min)", "Copy clips to your phone, re-read captions, check the campaign is still active.")]
    for t, pid in slots:
        rows.append((add_time(t, -15), f"Set up clip {pid}", "+ → Reel → pick the file; set audio, cover, caption (page 2). Don't publish yet."))
        rows.append((t, f"<b>POST clip {pid}</b>", "Publish, pin a comment with the question, then post the same to TikTok."))
        rows.append((f"{add_time(t, 5)} – {add_time(t, 65)}", "Golden hour", "Reply to every comment fast and ask a question back. Don't edit the caption."))
        rows.append((add_time(t, 70), "Submit links", "Submit both post links (IG + TikTok) in your campaign dashboard."))
    rows.append(("Next day 10:00 AM", "Check (10 min)", "Insights: views, watch time, shares, likes (need ≥ 2 likes per 1,000 views)."))
    trs = "".join(f"<tr><td class='t'>{t}</td><td class='w'>{w}</td><td>{d}</td></tr>" for t, w, d in rows)
    cards = "".join(post_card(pid, t) for t, pid in slots)
    return f"""
  <section class="page">
    <div class="dayhead"><div class="daynum">DAY {day}</div><div><div class="date">{date}</div>
      <div class="muted">Keep these post(s) live until at least <b>{live_until}</b> (30 days)</div></div></div>
    <table class="sched"><tr><th>Time (IST)</th><th>Task</th><th>What to do</th></tr>{trs}</table>
    {cards}
  </section>"""


def overview_rows() -> str:
    out = []
    for day, date, slots, live in DAYS:
        for t, pid in slots:
            p = POSTS[pid]
            aud = "Original" if "Original" in p["audio"] else "Original + C.R.E.A.M. " + p["audio"].split(" at ")[1].split("%")[0] + "%"
            out.append(f"<tr><td>Day {day}</td><td>{date[:-5]}</td><td>{t}</td><td><b>{pid}</b> {e(p['title'])}</td><td>{aud}</td><td>{live}</td></tr>")
    return "".join(out)


CSS = """
@page { size: A4; margin: 14mm 13mm; }
* { box-sizing: border-box; }
body { font-family: 'Segoe UI', 'Segoe UI Emoji', Arial, sans-serif; color: #1b1f24; font-size: 10.5pt; line-height: 1.45; margin: 0; }
h1 { font-size: 26pt; margin: 0; letter-spacing: -0.5px; }
h2 { font-size: 15pt; margin: 0 0 8px; padding-bottom: 4px; border-bottom: 2px solid #1b1f24; }
h3 { font-size: 11.5pt; margin: 14px 0 6px; }
a { color: #0a58ca; text-decoration: none; }
.page { page-break-after: always; }
.page:last-child { page-break-after: auto; }
.hero { background: #111418; color: #fff; padding: 22px 24px; border-radius: 10px; margin-bottom: 14px; }
.hero .sub { color: #aab3bd; margin-top: 6px; font-size: 11pt; }
.hero .tag { display: inline-block; background: #e8b931; color: #111; font-weight: 700; padding: 2px 8px; border-radius: 4px; font-size: 9pt; margin-bottom: 8px; }
.warn { border: 2px solid #d63b3b; background: #fff3f3; border-radius: 8px; padding: 10px 14px; margin: 10px 0; }
.warn b.h { color: #c62828; }
.note { background: #f3f6f9; border-left: 4px solid #0a58ca; padding: 8px 12px; border-radius: 4px; margin: 8px 0; }
table { width: 100%; border-collapse: collapse; margin: 6px 0 10px; font-size: 9.5pt; }
th { background: #111418; color: #fff; text-align: left; padding: 5px 7px; font-weight: 600; }
td { border-bottom: 1px solid #dde2e7; padding: 5px 7px; vertical-align: top; }
tr:nth-child(even) td { background: #fafbfc; }
ol.steps { padding-left: 0; list-style: none; counter-reset: s; margin: 6px 0; }
ol.steps > li { counter-increment: s; position: relative; padding: 4px 0 6px 34px; }
ol.steps > li::before { content: counter(s); position: absolute; left: 0; top: 3px; width: 24px; height: 24px; border-radius: 50%; background: #111418; color: #e8b931; font-weight: 700; text-align: center; line-height: 24px; font-size: 10pt; }
ul { margin: 4px 0; padding-left: 18px; }
.cols { display: flex; gap: 14px; }
.cols > div { flex: 1; }
.do { border-top: 4px solid #2e7d32; background: #f2f8f2; padding: 8px 12px; border-radius: 6px; }
.dont { border-top: 4px solid #c62828; background: #fdf2f2; padding: 8px 12px; border-radius: 6px; }
.dayhead { display: flex; align-items: center; gap: 14px; background: #111418; color: #fff; padding: 8px 16px; border-radius: 10px; margin-bottom: 6px; }
.dayhead .muted { color: #aab3bd; }
.daynum { background: #e8b931; color: #111; font-weight: 800; font-size: 16pt; padding: 4px 12px; border-radius: 6px; }
.date { font-size: 14pt; font-weight: 700; }
.sched { font-size: 9pt; margin: 4px 0 6px; }
.sched td, .sched th { padding: 3px 7px; }
.sched td.t { white-space: nowrap; font-weight: 600; width: 115px; }
.sched td.w { width: 105px; }
.post { display: flex; gap: 12px; border: 1px solid #dde2e7; border-radius: 10px; padding: 8px 10px; margin: 6px 0; page-break-inside: avoid; }
.post img { width: 100px; height: 178px; object-fit: cover; border-radius: 6px; flex: none; background: #000; }
.post .caption { font-size: 9.5pt; padding: 5px 8px; }
.pbody { flex: 1; }
.ptitle { font-weight: 700; font-size: 11.5pt; margin-bottom: 2px; }
.time { background: #e8b931; color: #111; padding: 1px 6px; border-radius: 4px; font-size: 9.5pt; margin-right: 4px; }
.muted { color: #6b7480; font-weight: 400; }
.file { font-size: 9pt; color: #6b7480; margin-bottom: 4px; }
.kv { font-size: 9.5pt; margin: 1px 0; }
.label { font-size: 8.5pt; text-transform: uppercase; letter-spacing: 0.5px; color: #6b7480; margin-top: 6px; }
.caption { background: #f6f7f9; border: 1px dashed #b8c0c8; border-radius: 6px; padding: 7px 9px; font-size: 10pt; margin-top: 3px; }
.src { font-size: 8.5pt; color: #4b5560; }
.src li { margin: 1px 0; word-break: break-all; }
"""


def build() -> str:
    days = "".join(day_page(*d) for d in DAYS)
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>MW4 Viral Plan</title><style>{CSS}</style></head><body>

<section class="page">
  <div class="hero"><div class="tag">CLIPPING CULTURE · MW4 CAMPAIGN MOMENTS</div>
    <h1>MW4 Reels: Viral Posting Plan</h1>
    <div class="sub">9 ready-made clips · 5-day posting timetable · step-by-step posting guide · rules checklist<br>Prepared Wed 28 Oct 2026 · all times are India Standard Time (IST)</div></div>

  <div class="warn"><b class="h">⚠️ Do this first: check the campaign is still paying.</b><br>
  On 28 Oct the Content Rewards page showed the campaign as <b>“Paused”</b> with <b>$39,516 of $40,000</b> spent ($484 left).
  Open your Clipping Culture / Content Rewards dashboard before Day 1. If it's closed, posts made after the budget runs out may not be paid.
  Payout listed: <b>Instagram $1.25 / 1K views</b>, <b>TikTok $1.75 / 1K views</b> (max $1,000 per clip). The brief allows “TikTok and/or Instagram”, so this plan posts every clip to one IG account <i>and</i> one TikTok account.</div>

  <h2>The plan at a glance</h2>
  <table><tr><th>Day</th><th>Date</th><th>Time</th><th>Clip</th><th>Audio</th><th>Keep live until</th></tr>{overview_rows()}</table>

  <h3>Why this order?</h3>
  <ul>
    <li><b>Character showdowns and moral choices first</b> (05, 01, 07, 04). Named characters (Price, Ghost, Gaz, Makarov) and spoiler moments are what's trending in the MW4 niche right now, and people search by character name.</li>
    <li><b>Two posts per day, 2.5 hours apart</b>, so each post gets its own first hour instead of competing with the other.</li>
    <li><b>8:30 PM – 12:30 AM IST</b> is when US and UK viewers are awake (10 AM – 2 PM US East, 3 – 7 PM UK). The brief wants a mostly Tier 1 audience.</li>
  </ul>
  <div class="note"><b>Where the files are:</b> clips in <b>C:\\Clipper\\mw4\\clips\\</b> (1080×1920, H.264, original game audio). Copy them to your phone with Google Drive, Quick Share or a USB cable.</div>
</section>

<section class="page">
  <h2>Before Day 1: one-time setup (Wed 28 Oct)</h2>
  <ol class="steps">
    <li><b>Check the dashboard.</b> Confirm the MW4 Campaign Moments campaign is active and that you've joined it.</li>
    <li><b>Switch Instagram to a Professional account</b> (Settings → Account type and tools → Creator). This gives you Insights for views, watch time and audience countries.</li>
    <li><b>Make the account public</b> and make sure <b>“Hide like and view counts” is OFF</b> (Settings → Likes and shares). Hidden likes mean automatic rejection.</li>
    <li><b>Check your audience.</b> Insights → Total followers → Top countries. The brief wants mostly Tier 1 (US, UK, CA, AU…); more than 30% Tier 3 may get removed.</li>
    <li><b>Set up TikTok</b> on one account only, also public. Don't post the same clip to several accounts (that counts as spam).</li>
    <li><b>Save the official sound</b> on both apps so it's quick to add later:<br>
      Instagram: <a href="{IG_SOUND}">{IG_SOUND}</a><br>
      TikTok: <a href="{TT_SOUND}">tiktok.com/music/CREAM-Call-of-Duty-Modern-Warfare-4-Remix</a><br>
      The track is <b>“C.R.E.A.M. (Modern Warfare 4 Remix)”</b> by Wu-Tang Clan with Lee Young-ji.</li>
    <li><b>Copy all 9 clips and all 9 cover images to your phone</b> (C:\\Clipper\\mw4\\clips\\ and C:\\Clipper\\mw4\\covers\\) into one album named “MW4”.</li>
    <li><b>Watch every clip once on the phone</b> with sound on. Check the text is readable and nothing looks off.</li>
  </ol>

  <h2 style="margin-top:14px">How to post a Reel: step by step</h2>
  <ol class="steps">
    <li>Open Instagram → tap <b>+</b> → <b>Reel</b> → pick the clip from the MW4 album → <b>Next</b>. Don't trim or add filters; the clip is already edited.</li>
    <li><b>Audio (music clips only: 04, 06, 08, 09):</b> tap the music icon → search “C.R.E.A.M. Modern Warfare 4” (or open the saved sound and tap “Use audio”) → pick the most energetic part → tap <b>Volume / Mix</b> → <b>original audio 100</b>, <b>music 15–25</b>. Play it back: the game audio must be clearly louder than the music.</li>
    <li><b>Dialogue clips (01, 02, 03, 05, 07):</b> add no music. The lines are the hook.</li>
    <li>Tap <b>Next</b> → <b>Edit cover</b> → <b>Add from camera roll</b> → pick that clip's cover image from the <b>covers</b> folder (same name as the clip) → check the <b>profile grid preview</b> shows the title fully → <b>Done</b>.</li>
    <li>Paste the <b>caption</b> exactly as printed, with <b>#Ad alone on its own line</b> as the first hashtag. The @callofduty tag must be in the caption.</li>
    <li>Check <b>Share to Feed is ON</b> (so it shows on your grid). Do <b>not</b> turn on “Trial” (Trial Reels are hidden from your profile).</li>
    <li>Optional: <b>Tag people → @callofduty</b> on the video too (the caption tag is the one that's required).</li>
    <li>Tap <b>Share</b>. Then immediately post a comment with the caption's question and <b>pin it</b>.</li>
    <li><b>TikTok:</b> + → Upload → same clip → (music clips: add the official sound, original volume high, added sound low) → paste the same caption → <b>Select cover</b>: pick the TikTok frame listed for that clip and add the same title text with the cover-text tool → Post.</li>
    <li>Copy both post links and <b>submit them in the campaign dashboard</b>.</li>
  </ol>
</section>

{days}

<section class="page">
  <h2>Days 6 – 30: keep it alive (Tue 3 Nov → Wed 2 Dec)</h2>
  <table>
    <tr><th>When</th><th>Task</th></tr>
    <tr><td><b>Every day, 10 min</b> (any time)</td><td>Reply to new comments on all posts (comments keep pushing a Reel to new viewers). Check no post was flagged or removed.</td></tr>
    <tr><td><b>Every 3 days</b></td><td>Insights check: which clip has the best <i>average watch time</i> and <i>shares</i>? Note the hook style that won (character vs character, moral choice, spoiler, funny).</td></tr>
    <tr><td><b>Days 6–10</b>, if the campaign is still active</td><td>Ask for or make <b>new clips in the style that won</b> (only from the official folder). Don't re-upload the same clip; the brief caps it at 5 posts per video and duplicates get suppressed.</td></tr>
    <tr><td><b>Weekly</b></td><td>Confirm likes are still visible, every post is public, and each post's engagement is at least <b>2 likes per 1,000 views (0.20%)</b>.</td></tr>
    <tr><td><b>Sat 28 Nov – Wed 2 Dec</b></td><td>The 30-day minimum ends for each day's posts (dates on each day page). <b>Leaving them up after that is safest</b>; never delete before the date.</td></tr>
  </table>

  <h2 style="margin-top:12px">Secrets to going viral (and why they work)</h2>
  <table>
    <tr><th style="width:150px">Signal Instagram ranks on</th><th>What this plan does about it</th></tr>
    <tr><td><b>First 1–3 seconds</b></td><td>The hook text is on screen from frame 1 and names the characters. Viewers decide in seconds whether to stay.</td></tr>
    <tr><td><b>Watch time and rewatches</b></td><td>Clips are 16–38s. Short clips get rewatched and rewatches count. Instagram only recommends Reels under about 3 minutes to non-followers.</td></tr>
    <tr><td><b>Sends (DM shares)</b></td><td>Reportedly the strongest reach signal. Every caption ends with a share or tag prompt (“Send this to your duo”, “Tag the friend who'd say this”).</td></tr>
    <tr><td><b>Comments</b></td><td>A genuine question in every caption, plus a pinned question. Reply to everyone in the first hour. <i>Never</i> rage bait or exaggerated hooks; the brief bans them.</td></tr>
    <tr><td><b>Search / keywords</b></td><td>The first caption line has MW4 + character names (Price, Ghost, Gaz, Makarov, Ri Ju-Young). Instagram search is keyword-based now.</td></tr>
    <tr><td><b>Hashtags</b></td><td>Instagram allows max 5. The brief allows #Ad + 3. Use specific tags (#CaptainPrice, #Makarov, #TaskForce141), never generic ones (#viral #fyp #gaming).</td></tr>
    <tr><td><b>Originality</b></td><td>Instagram suppresses reposts. The clips are re-framed, captioned and hooked, so they're original edits. Never upload raw footage.</td></tr>
    <tr><td><b>Audio page discovery</b></td><td>Using the official sound lists your Reel on that sound's page, a free extra feed. Keep it quiet so the game audio stays clearly audible (a brief rule).</td></tr>
  </table>
</section>

<section class="page">
  <h2>Campaign rules checklist (from the brief)</h2>
  <div class="cols">
    <div class="do"><b>✅ Every post MUST</b>
      <ul>
        <li>Use footage only from the official folder (all 9 clips do)</li>
        <li>Tag <b>@callofduty</b> in the caption</li>
        <li>Have <b>#Ad</b> (or #Sponsored / #Advertisement) <b>on its own line</b> as the first hashtag after the caption text</li>
        <li>Have at most 3 more hashtags, all related to the content</li>
        <li>Be at least 10 seconds long, in English and high quality</li>
        <li>Keep the original audio clearly audible</li>
        <li>Stay live for at least 30 days with likes visible</li>
        <li>Reach at least 0.20% engagement (2 likes per 1,000 views)</li>
        <li>Say only true things: no made-up facts, stats or dates</li>
      </ul></div>
    <div class="dont"><b>❌ NEVER</b>
      <ul>
        <li>Hide likes (automatic rejection)</li>
        <li>Delete or archive before 30 days</li>
        <li>Boost or run ads on a post (permanent ban)</li>
        <li>Post the same video on multiple accounts, or more than 5 times</li>
        <li>Count on stories (story views don't count)</li>
        <li>Add copyrighted music (the official sound is fine)</li>
        <li>Add AI voiceover or narration, or logos on screen</li>
        <li>Use rage bait, hate bait or exaggerated hooks</li>
        <li>Call a trailer “gameplay”, or post NSFW or real-world violence</li>
        <li>Copy other clippers' captions</li>
      </ul></div>
  </div>

  <h3>Why every claim in the hooks and captions is safe</h3>
  <ul>
    <li><b>Price vs Ghost / Gaz:</b> the source file is named “GhostFight_GhostAndGazAtEnd”, and Wikipedia's plot says Ghost and Gaz confront Price in the Mumbai ambush. GameSpot also mentions the “fractured” Task Force 141.</li>
    <li><b>Price vs Makarov / Manhattan:</b> the source file is “MakarovChaseAndFight”; Wikipedia says Price pursues Makarov across downtown Manhattan. The in-game subtitle names “Makarov”.</li>
    <li><b>Ri Ju-Young and the rope line:</b> both are word-for-word from the in-game subtitles. “If you know, you know” teases her later coup without stating it.</li>
    <li><b>The refusal (01):</b> the game shows a refuse/execute prompt, and the player character says “No. This is wrong.”</li>
    <li><b>Content warning:</b> the campaign page says “No explicit content”. Clips 01 and 02 are official footage but the heaviest. If either gets flagged, the other clips carry the plan.</li>
  </ul>

  <h3>Sources</h3>
  <ul class="src">
    <li>Campaign brief PDF: “Modern Warfare 4 – Campaign Moments Clipping” (Clipping Culture)</li>
    <li>Campaign page: https://contentrewards.com/c/campaigns/&lt;campaign-id&gt;</li>
    <li>Plot: https://en.wikipedia.org/wiki/Call_of_Duty:_Modern_Warfare_4</li>
    <li>Review: https://www.gamespot.com/reviews/call-of-duty-modern-warfare-4-campaign-review/</li>
    <li>Official sound: https://www.invenglobal.com/articles/27591/remix-of-iconic-track-cream-featured-in-modern-warfare-4-released-featuring-lee-young-ji</li>
    <li>Trends: https://www.tiktok.com/discover/Modern-warfare · https://www.tiktok.com/discover/hold-the-line-or-cross-the-line-mw4</li>
    <li>Algorithm signals: https://www.dataslayer.ai/blog/instagram-algorithm-2025-complete-guide-for-marketers · https://blog.hootsuite.com/instagram-algorithm/</li>
    <li>Hashtag cap: https://later.com/blog/instagram-hashtags/ · Keyword search: https://www.inro.social/blog/instagram-seo-guide-2026</li>
    <li>Posting times: https://postfa.st/blog/best-time-to-post-reels-on-instagram · https://www.lilachbullock.com/best-time-to-post-instagram-reels-maximum-reach/</li>
  </ul>
  <p class="muted" style="font-size:8.5pt">Algorithm and timing advice comes from third-party marketing research, not official Instagram documentation. Treat it as a starting point and adjust from your own Insights after the first few posts.</p>
</section>
</body></html>"""


def main() -> None:
    OUT_HTML.write_text(build(), encoding="utf-8")
    subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--allow-file-access-from-files",
                    f"--print-to-pdf={OUT_PDF}", OUT_HTML.resolve().as_uri()], check=True, timeout=120)
    print(OUT_PDF)


if __name__ == "__main__":
    main()
