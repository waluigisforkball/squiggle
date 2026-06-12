# Squiggle 🎢

Headless Bluesky bot that posts one daily, **spoiler-free** shortlist of the
most exciting completed MLB games, ranked by win-probability swing (Tango
Excitement Index). Sister bot to [@cmon-blue.bsky.social].

## How it works
1. GitHub Action runs nightly (`6am ET`, covers West Coast finishes).
2. `run.py` pulls yesterday's completed games from the free MLB Stats API.
3. `score_games.py` reads per-play home win probability from the GUMBO feed and
   computes, per game:
   - **Excitement Index** — sum of |Δ win-probability| across all plays.
   - **Lead changes** — decisive crossings of 50% (deadband filters jitter).
   - **Late tightness** — stayed near 50% into the final third (~7th+).
4. Games clearing `EXCITEMENT_FLOOR` get a badge: 🎢 Rollercoaster / 🔁 Comeback
   / 😬 Nailbiter, and the top ~3 go into **one** ranked post.
5. Zero qualifiers → posts nothing. Silent on dead nights.

## Spoiler safety
The post only ever contains team names + badge — never scores, winners, or
result language. `format_post.py` runs a denylist + score-pattern lint on the
final string and **aborts the post** if anything leaks.

## Setup
1. Create a Bluesky **app password** (Settings → App Passwords).
2. Add repo secrets: `BSKY_HANDLE`, `BSKY_APP_PASSWORD`.
3. **Verify the WP field path on first run** (see below).
4. **Tune the floor** with `calibrate.py` before going live.

### Verify the win-probability path (do this first)
The one field that must be confirmed against the live API:
```
python score_games.py --probe <gamePk>
```
This dumps where home win probability lives on a sample play. If MLB nests it
differently than the candidates in `_extract_home_wp`, add the path there.

### Tune the floor
```
python calibrate.py 2024-10-30 2024-09-26 2024-07-04
```
Pick a few known dates (a blowout-heavy day + a classic). Set
`EXCITEMENT_FLOOR` between the blowout cluster and the rollercoasters.

### Dry run (no posting)
```
DRY_RUN=1 python run.py 2024-09-26
```

## Files
- `score_games.py` — fetch + scoring + categorization (+ `--probe`)
- `format_post.py` — spoiler-free copy + lint
- `post.py` — AT Protocol posting
- `run.py` — orchestrator (silent on dead nights)
- `calibrate.py` — floor tuning helper
- `.github/workflows/squiggle.yml` — nightly cron
