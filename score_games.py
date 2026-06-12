"""
Squiggle — MLB excitement scorer.

Pulls completed games for a date, reads per-play win probability from the MLB
GUMBO live feed, and computes a Tango-style Excitement Index plus secondary
signals (lead changes, late-game tightness). No result-revealing data is ever
returned from this module — only team names, scores, and category badges.

PROBE NOTE: The exact JSON path to per-play win probability is the one thing
that must be verified against the live API on first run. Run:
    python score_games.py --probe <gamePk>
to dump the candidate field paths for a single game before trusting scores.
"""

from __future__ import annotations

import sys
import json
import urllib.request
from dataclasses import dataclass

SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={date}"
# Per-play win probability lives on its OWN endpoint, not the live/GUMBO feed.
# Each entry is a play carrying top-level homeTeamWinProbability (0-100).
WP_URL = "https://statsapi.mlb.com/api/v1/game/{game_pk}/winProbability"

# --- Tuning knobs ---------------------------------------------------------
# Excitement floor: a game must clear this Tango EI to qualify. Calibrate with
# calibrate.py against real slates before trusting. Placeholder until tuned.
# Excitement floor: tuned against the 2026-06-10 slate. At 3.3 only genuinely
# notable games clear (comebacks + late-tight swings); the 2.x "one mild swing"
# games and sub-2 duds are correctly excluded. Stricter = more trustworthy bot.
EXCITEMENT_FLOOR = 3.3
# A play counts as a lead change if home WP crosses the 50% line decisively.
LEAD_LINE = 0.50
# Deadband: WP must move past 50% by this margin to count as a real lead
# change. Stops coin-flip jitter near 50% from inflating the comeback signal.
LEAD_DEADBAND = 0.10  # i.e. must reach 0.40 / 0.60 to "commit" to a side
# A game earns 🔁 Comeback only with this many decisive lead changes. Set high
# so the badge stays special — reserved for true back-and-forth slugfests.
COMEBACK_MIN_LEAD_CHANGES = 4
# "Late" tightness window: innings 7+.
LATE_INNING = 7
# How close to 50% counts as a nailbiter in the late window.
TIGHT_BAND = 0.15


@dataclass
class GameScore:
    game_pk: int
    away: str
    home: str
    away_abbr: str
    home_abbr: str
    excitement: float
    lead_changes: int
    late_tight: bool
    badge: str           # emoji + label (for post text)
    series: list         # home win prob per play, 0..1 (for the chart)
    innings: list        # parallel inning number per play (for x-axis)
    away_score: int      # final score (for post text only, never the chart)
    home_score: int


def _get_json(url: str):
    """Fetch JSON. Returns parsed data, or None on HTTP/network error so a
    single missing game can't crash a whole slate."""
    req = urllib.request.Request(url, headers={"User-Agent": "squiggle-bot"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError,
            json.JSONDecodeError, TimeoutError) as e:
        print(f"[squiggle] fetch failed for {url}: {e}", file=sys.stderr)
        return None


def fetch_completed_games(date: str) -> list[dict]:
    """Return [{gamePk, away, home, away_abbr, home_abbr}] for Final games."""
    data = _get_json(SCHEDULE_URL.format(date=date))
    dates = data.get("dates", []) if data else []
    if not dates:
        return []
    out = []
    for g in dates[0].get("games", []):
        state = g.get("status", {}).get("abstractGameState", "")
        if state != "Final":
            continue
        away_t = g["teams"]["away"]["team"]
        home_t = g["teams"]["home"]["team"]
        out.append(
            {
                "gamePk": g["gamePk"],
                "away": away_t["name"],
                "home": home_t["name"],
                # abbreviation may not be on the schedule team stub; fall back
                # to a short slice of the name, corrected later if needed.
                "away_abbr": away_t.get("abbreviation")
                             or _abbr_fallback(away_t["name"]),
                "home_abbr": home_t.get("abbreviation")
                             or _abbr_fallback(home_t["name"]),
            }
        )
    return out


def _abbr_fallback(name: str) -> str:
    """Last-resort abbreviation if the API stub lacks one: initials of the
    final word(s). e.g. 'Red Sox' -> 'RS'. Real abbr comes from the API."""
    parts = name.split()
    return (parts[-1][:3]).upper() if parts else name[:3].upper()


def _extract_home_wp(play: dict):
    """
    Home-team win probability for a single play, from the confirmed top-level
    `homeTeamWinProbability` field (0-100 scale). Normalized to 0..1.
    Returns None if absent.
    """
    wp = play.get("homeTeamWinProbability")
    if isinstance(wp, (int, float)):
        return wp / 100.0
    return None


def fetch_wp_series(game_pk: int):
    """
    Return (series, innings, final_away, final_home):
      series  - home win prob per play, 0..1
      innings - parallel inning number per play
      final_*  - final score from the last play's result block
    On error returns ([], [], None, None).
    """
    plays = _get_json(WP_URL.format(game_pk=game_pk))
    if not isinstance(plays, list) or not plays:
        return [], [], None, None
    series, innings = [], []
    for p in plays:
        wp = _extract_home_wp(p)
        if wp is None:
            continue
        series.append(wp)
        innings.append(p.get("about", {}).get("inning", 0))
    # Final score: scan from the end for a play that carries both scores.
    final_away = final_home = None
    for p in reversed(plays):
        res = p.get("result", {})
        if "awayScore" in res and "homeScore" in res:
            final_away = res["awayScore"]
            final_home = res["homeScore"]
            break
    return series, innings, final_away, final_home


def excitement_index(series: list[float]) -> float:
    """Tango Excitement Index: sum of absolute win-probability changes."""
    return sum(abs(series[i] - series[i - 1]) for i in range(1, len(series)))


def count_lead_changes(series: list[float]) -> int:
    """
    Number of decisive lead changes. A "side" is only committed once WP moves
    past 50% by LEAD_DEADBAND (e.g. >=0.60 home, <=0.40 away). A lead change is
    counted when the committed side flips. Jitter inside the deadband around
    50% is ignored, so a tight nailbiter doesn't read as a comeback.
    """
    hi = LEAD_LINE + LEAD_DEADBAND
    lo = LEAD_LINE - LEAD_DEADBAND
    side = 0          # -1 = away committed, +1 = home committed, 0 = neither
    changes = 0
    for wp in series:
        if wp >= hi:
            new = 1
        elif wp <= lo:
            new = -1
        else:
            continue  # inside deadband, no commitment change
        if side != 0 and new != side:
            changes += 1
        side = new
    return changes


def late_tightness(series: list[float], innings: list | None = None) -> bool:
    """
    Was the game still within TIGHT_BAND of 50% in the late innings (7+)?
    Uses real inning data when provided; otherwise approximates "late" as the
    final third of plays.
    """
    if len(series) < 6:
        return False
    if innings and len(innings) == len(series):
        tail = [wp for wp, inn in zip(series, innings) if inn >= LATE_INNING]
        if not tail:
            tail = series[int(len(series) * 0.66):]
    else:
        tail = series[int(len(series) * 0.66):]
    return any(abs(wp - LEAD_LINE) <= TIGHT_BAND for wp in tail)


def categorize(ei: float, lead_changes: int, late_tight: bool) -> str:
    """
    Pick the badge from whichever dimension dominates.
    Priority: many decisive lead changes -> comeback (reserved for true
    back-and-forth games); sustained late tightness -> nailbiter; otherwise
    high total swing -> rollercoaster. The floor guarantees every badged game
    already has meaningful total swing, so rollercoaster is an honest default.
    """
    if lead_changes >= COMEBACK_MIN_LEAD_CHANGES:
        return "🔁 Comeback"
    if late_tight:
        return "😬 Nailbiter"
    return "🎢 Rollercoaster"


def score_game(game: dict) -> GameScore | None:
    series, innings, away_score, home_score = fetch_wp_series(game["gamePk"])
    if len(series) < 2:
        return None
    ei = excitement_index(series)
    lc = count_lead_changes(series)
    lt = late_tightness(series, innings)
    return GameScore(
        game_pk=game["gamePk"],
        away=game["away"],
        home=game["home"],
        away_abbr=game["away_abbr"],
        home_abbr=game["home_abbr"],
        excitement=round(ei, 3),
        lead_changes=lc,
        late_tight=lt,
        badge=categorize(ei, lc, lt),
        series=series,
        innings=innings,
        away_score=away_score if away_score is not None else 0,
        home_score=home_score if home_score is not None else 0,
    )


def qualifies(score: GameScore) -> bool:
    return score.excitement >= EXCITEMENT_FLOOR


def score_date(date: str) -> list[GameScore]:
    games = fetch_completed_games(date)
    scored = []
    for g in games:
        s = score_game(g)
        if s:
            scored.append(s)
    # Rank by EI, tie-break on lead changes for stability.
    scored.sort(key=lambda s: (s.excitement, s.lead_changes), reverse=True)
    return scored


def _probe(game_pk: int) -> None:
    """Dump candidate WP field locations for one game to verify the path."""
    plays = _get_json(WP_URL.format(game_pk=int(game_pk)))
    if not isinstance(plays, list):
        print("Unexpected response shape — not a list of plays.")
        return
    print(f"Total plays: {len(plays)}")
    if not plays:
        print("No plays found — check feed structure.")
        return
    sample = plays[len(plays) // 2]
    print("homeTeamWinProbability:", sample.get("homeTeamWinProbability"))
    wp = _extract_home_wp(sample)
    print("Extracted home WP (normalized 0..1):", wp)
    series, innings, fa, fh = fetch_wp_series(int(game_pk))
    print(f"Series length: {len(series)}  innings captured: {len(innings)}")
    print(f"Final score (away-home): {fa}-{fh}")
    if series:
        print(f"EI: {excitement_index(series):.3f}  "
              f"lead_changes: {count_lead_changes(series)}  "
              f"late_tight: {late_tightness(series, innings)}")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--probe":
        _probe(sys.argv[2])
    elif len(sys.argv) >= 2:
        for s in score_date(sys.argv[1]):
            print(f"{s.away} vs {s.home}  EI={s.excitement}  "
                  f"LC={s.lead_changes}  tight={s.late_tight}  {s.badge}")
    else:
        print("Usage: score_games.py <YYYY-MM-DD> | --probe <gamePk>")
