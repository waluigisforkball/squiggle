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
    excitement: float
    lead_changes: int
    late_tight: bool
    badge: str  # emoji + label


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
    """Return [{gamePk, away, home}] for games that are Final on `date`."""
    data = _get_json(SCHEDULE_URL.format(date=date))
    dates = data.get("dates", []) if data else []
    if not dates:
        return []
    out = []
    for g in dates[0].get("games", []):
        state = g.get("status", {}).get("abstractGameState", "")
        if state != "Final":
            continue
        out.append(
            {
                "gamePk": g["gamePk"],
                "away": g["teams"]["away"]["team"]["name"],
                "home": g["teams"]["home"]["team"]["name"],
            }
        )
    return out


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


def fetch_wp_series(game_pk: int) -> list[float]:
    """Ordered list of home-win-probability values (0..1), one per play."""
    plays = _get_json(WP_URL.format(game_pk=game_pk))
    if not isinstance(plays, list):
        return []
    series = []
    for p in plays:
        wp = _extract_home_wp(p)
        if wp is not None:
            series.append(wp)
    return series


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


def late_tightness(series: list[float], plays_meta: list[dict] | None = None) -> bool:
    """
    Approx: was the game still within TIGHT_BAND of 50% deep in the game?
    Without per-play inning data we approximate "late" as the final third of
    plays, which reliably maps to ~7th inning onward.
    """
    if len(series) < 6:
        return False
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
    series = fetch_wp_series(game["gamePk"])
    if len(series) < 2:
        return None
    ei = excitement_index(series)
    lc = count_lead_changes(series)
    lt = late_tightness(series)
    return GameScore(
        game_pk=game["gamePk"],
        away=game["away"],
        home=game["home"],
        excitement=round(ei, 3),
        lead_changes=lc,
        late_tight=lt,
        badge=categorize(ei, lc, lt),
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
    series = fetch_wp_series(int(game_pk))
    print(f"Series length: {len(series)}")
    if series:
        print(f"EI: {excitement_index(series):.3f}  "
              f"lead_changes: {count_lead_changes(series)}  "
              f"late_tight: {late_tightness(series)}")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--probe":
        _probe(sys.argv[2])
    elif len(sys.argv) >= 2:
        for s in score_date(sys.argv[1]):
            print(f"{s.away} vs {s.home}  EI={s.excitement}  "
                  f"LC={s.lead_changes}  tight={s.late_tight}  {s.badge}")
    else:
        print("Usage: score_games.py <YYYY-MM-DD> | --probe <gamePk>")
