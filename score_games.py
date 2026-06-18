"""
Squiggle — MLB excitement scorer (v2: two-lens model).

Pulls completed games for a date, reads per-play win probability from the MLB
winProbability endpoint, and evaluates each game on TWO independent lenses:

  COMEBACK     — did the eventual winner sink to a deep low and climb back?
                 Measured by the winner's single lowest win-probability point.
  BACK_FORTH   — how many BIG (40%+) peak-to-trough momentum reversals?
                 Measured by counting significant swings; tiny fidget ignored.

A game can qualify on either lens, both, or neither. Each lens has its own
threshold, tunable below. Raw total-movement (the old Excitement Index) is
retained only as a tiebreaker/diagnostic, not as a qualifier.
"""

from __future__ import annotations

import sys
import json
import urllib.request
from dataclasses import dataclass

SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={date}"
WP_URL = "https://statsapi.mlb.com/api/v1/game/{game_pk}/winProbability"

# --- Tuning knobs (two-lens model) ---------------------------------------
# COMEBACK: the eventual winner must have fallen at or below this WP at some
# point. 0.15 = "deep hole" (winner was once <=15% to win).
COMEBACK_MAX_LOW = 0.15
# COMEBACK: the eventual winner must have fallen at or below this WP. 0.10 =
# only near-death escapes (winner was once <=10% to win). Tuned on real data.
COMEBACK_MAX_LOW = 0.10

# BACK-AND-FORTH: defined by the lead genuinely changing hands several times
# AND high total movement. The old single-swing magnitude counter proved too
# brittle on real MLB WP (which zigzags in steps, rarely one clean 45% move),
# so we use lead changes + total movement, which track the real games well.
LEAD_LINE = 0.50
LEAD_DEADBAND = 0.10               # must reach 0.40/0.60 to "commit" to a side
BACK_FORTH_MIN_LEAD_CHANGES = 3   # lead changes hands 3+ times
BACK_FORTH_MIN_MOVEMENT = 3.5     # and total |WP change| >= this
SWING_THRESHOLD = 0.40            # big-swing size; kept for diagnostics only

# --- Team abbreviations, IDs, and colors ----------------------------------
# Full name -> (abbreviation, MLB team id, primary hex, secondary hex).
# team id powers the logo URL; colors power the gradient line.
TEAM_INFO = {
    "Arizona Diamondbacks": ("AZ", 109, "#A71930", "#E3D4AD"),
    "Atlanta Braves": ("ATL", 144, "#CE1141", "#13274F"),
    "Baltimore Orioles": ("BAL", 110, "#DF4601", "#000000"),
    "Boston Red Sox": ("BOS", 111, "#BD3039", "#0C2340"),
    "Chicago Cubs": ("CHC", 112, "#0E3386", "#CC3433"),
    "Chicago White Sox": ("CWS", 145, "#27251F", "#C4CED4"),
    "Cincinnati Reds": ("CIN", 113, "#C6011F", "#000000"),
    "Cleveland Guardians": ("CLE", 114, "#00385D", "#E50022"),
    "Colorado Rockies": ("COL", 115, "#33006F", "#C4CED4"),
    "Detroit Tigers": ("DET", 116, "#0C2340", "#FA4616"),
    "Houston Astros": ("HOU", 117, "#002D62", "#EB6E1F"),
    "Kansas City Royals": ("KC", 118, "#004687", "#BD9B60"),
    "Los Angeles Angels": ("LAA", 108, "#003263", "#BA0021"),
    "Los Angeles Dodgers": ("LAD", 119, "#005A9C", "#EF3E42"),
    "Miami Marlins": ("MIA", 146, "#00A3E0", "#EF3340"),
    "Milwaukee Brewers": ("MIL", 158, "#12284B", "#FFC52F"),
    "Minnesota Twins": ("MIN", 142, "#002B5C", "#D31145"),
    "New York Mets": ("NYM", 121, "#002D72", "#FF5910"),
    "New York Yankees": ("NYY", 147, "#003087", "#E4002C"),
    "Athletics": ("ATH", 133, "#003831", "#EFB21E"),
    "Oakland Athletics": ("OAK", 133, "#003831", "#EFB21E"),
    "Philadelphia Phillies": ("PHI", 143, "#E81828", "#002D72"),
    "Pittsburgh Pirates": ("PIT", 134, "#27251F", "#FDB827"),
    "San Diego Padres": ("SD", 135, "#2F241D", "#FFC425"),
    "San Francisco Giants": ("SF", 137, "#FD5A1E", "#27251F"),
    "Seattle Mariners": ("SEA", 136, "#0C2C56", "#005C5C"),
    "St. Louis Cardinals": ("STL", 138, "#C41E3A", "#0C2340"),
    "Tampa Bay Rays": ("TB", 139, "#092C5C", "#8FBCE6"),
    "Texas Rangers": ("TEX", 140, "#003278", "#C0111F"),
    "Toronto Blue Jays": ("TOR", 141, "#134A8E", "#1D2D5C"),
    "Washington Nationals": ("WSH", 120, "#AB0003", "#14225A"),
}


def abbr(name: str) -> str:
    if name in TEAM_INFO:
        return TEAM_INFO[name][0]
    parts = name.split()
    return (parts[-1][:3]).upper() if parts else name[:3].upper()


def team_id(name: str) -> int | None:
    return TEAM_INFO[name][1] if name in TEAM_INFO else None


def team_color(name: str) -> str:
    return TEAM_INFO[name][2] if name in TEAM_INFO else "#1a6ef5"


def team_secondary(name: str) -> str:
    return TEAM_INFO[name][3] if name in TEAM_INFO else "#888888"


@dataclass
class GameScore:
    game_pk: int
    away: str
    home: str
    away_abbr: str
    home_abbr: str
    away_color: str
    home_color: str
    away_color2: str
    home_color2: str
    away_id: int
    home_id: int
    # metrics
    total_movement: float        # old EI, diagnostic/tiebreak only
    big_swings: int              # count of big reversals
    lead_changes: int            # decisive lead changes (50% crossings)
    winner_low: float            # eventual winner's lowest WP (0..1)
    is_comeback: bool
    is_back_forth: bool
    badge: str                   # emoji + label for post text
    # chart + post data
    series: list                 # home win prob per play, 0..1
    innings: list
    away_score: int
    home_score: int


def _get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "squiggle-bot"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError,
            json.JSONDecodeError, TimeoutError) as e:
        print(f"[squiggle] fetch failed for {url}: {e}", file=sys.stderr)
        return None


def fetch_completed_games(date: str) -> list[dict]:
    data = _get_json(SCHEDULE_URL.format(date=date))
    dates = data.get("dates", []) if data else []
    if not dates:
        return []
    out = []
    for g in dates[0].get("games", []):
        if g.get("status", {}).get("abstractGameState", "") != "Final":
            continue
        away_n = g["teams"]["away"]["team"]["name"]
        home_n = g["teams"]["home"]["team"]["name"]
        out.append({
            "gamePk": g["gamePk"],
            "away": away_n, "home": home_n,
            "away_abbr": abbr(away_n), "home_abbr": abbr(home_n),
        })
    return out


def _extract_home_wp(play: dict):
    wp = play.get("homeTeamWinProbability")
    if isinstance(wp, (int, float)):
        return wp / 100.0
    return None


def fetch_wp_series(game_pk: int):
    """Return (series, innings, final_away, final_home)."""
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
    final_away = final_home = None
    for p in reversed(plays):
        res = p.get("result", {})
        if "awayScore" in res and "homeScore" in res:
            final_away, final_home = res["awayScore"], res["homeScore"]
            break
    return series, innings, final_away, final_home


def total_movement(series: list[float]) -> float:
    """Old Excitement Index: sum of |delta WP|. Diagnostic / tiebreaker."""
    return sum(abs(series[i] - series[i - 1]) for i in range(1, len(series)))


def count_lead_changes(series: list[float]) -> int:
    """
    Decisive lead changes: how many times the favored side flips. A side is
    only 'committed' once WP passes 50% by LEAD_DEADBAND (>=0.60 home / <=0.40
    away), so wobble right at 50% is ignored. Counts flips between committed
    sides — the real 'who's winning changed hands' signal.
    """
    hi, lo = LEAD_LINE + LEAD_DEADBAND, LEAD_LINE - LEAD_DEADBAND
    side, changes = 0, 0
    for wp in series:
        new = 1 if wp >= hi else (-1 if wp <= lo else 0)
        if new == 0:
            continue
        if side != 0 and new != side:
            changes += 1
        side = new
    return changes


def count_big_swings(series: list[float], threshold: float = SWING_THRESHOLD) -> int:
    """
    Count significant peak-to-trough reversals of >= threshold WP.

    Track the running extreme in the current direction. When price reverses
    from that extreme by >= threshold, count one swing and pivot: the point we
    reversed to becomes the new extreme, and direction flips. Small fidget
    never reaches the threshold, so it's ignored.
    """
    if len(series) < 2:
        return 0
    swings = 0
    extreme = series[0]
    direction = 0  # 0 unknown, +1 rising, -1 falling
    for wp in series[1:]:
        if direction == 1:
            if wp > extreme:
                extreme = wp                      # extend the high
            elif extreme - wp >= threshold:
                swings += 1                       # fell far enough -> swing
                extreme = wp
                direction = -1
        elif direction == -1:
            if wp < extreme:
                extreme = wp                      # extend the low
            elif wp - extreme >= threshold:
                swings += 1                       # rose far enough -> swing
                extreme = wp
                direction = 1
        else:  # direction unknown — establish it on first real move
            if wp > extreme:
                direction = 1; extreme = wp
            elif wp < extreme:
                direction = -1; extreme = wp
    return swings


def winner_low_point(series: list[float], home_score: int, away_score: int) -> float:
    """
    The eventual winner's single lowest win-probability value (0..1).
    If home won, that's min(home WP); if away won, min(away WP) = min(1 - home).
    """
    if not series:
        return 0.5
    if home_score > away_score:            # home won
        return min(series)
    elif away_score > home_score:          # away won
        return min(1.0 - wp for wp in series)
    return 0.5                              # tie (shouldn't happen in MLB)


def categorize(is_comeback: bool, is_back_forth: bool) -> str:
    """Badge reflects which lens(es) the game earned."""
    if is_comeback and is_back_forth:
        return "🔁🎢 Comeback + Back-and-forth"
    if is_comeback:
        return "🔁 Comeback"
    if is_back_forth:
        return "🎢 Back-and-forth"
    return ""  # no badge — shouldn't be posted


def score_game(game: dict) -> GameScore | None:
    series, innings, a_score, h_score = fetch_wp_series(game["gamePk"])
    if len(series) < 2:
        return None
    a_score = a_score or 0
    h_score = h_score or 0
    tm = total_movement(series)
    swings = count_big_swings(series)
    leads = count_lead_changes(series)
    low = winner_low_point(series, h_score, a_score)
    is_cb = low <= COMEBACK_MAX_LOW
    # back-and-forth: lead changes hands enough AND lots of total movement
    is_bf = (leads >= BACK_FORTH_MIN_LEAD_CHANGES
             and tm >= BACK_FORTH_MIN_MOVEMENT)
    return GameScore(
        game_pk=game["gamePk"], away=game["away"], home=game["home"],
        away_abbr=game["away_abbr"], home_abbr=game["home_abbr"],
        away_color=team_color(game["away"]), home_color=team_color(game["home"]),
        away_color2=team_secondary(game["away"]),
        home_color2=team_secondary(game["home"]),
        away_id=team_id(game["away"]) or 0, home_id=team_id(game["home"]) or 0,
        total_movement=round(tm, 3), big_swings=swings, lead_changes=leads,
        winner_low=round(low, 3), is_comeback=is_cb, is_back_forth=is_bf,
        badge=categorize(is_cb, is_bf),
        series=series, innings=innings,
        away_score=a_score, home_score=h_score,
    )


def qualifies(s: GameScore) -> bool:
    return s.is_comeback or s.is_back_forth


def score_date(date: str) -> list[GameScore]:
    games = fetch_completed_games(date)
    scored = [s for g in games if (s := score_game(g))]
    # Rank by lead changes, then total movement, then comeback depth.
    scored.sort(key=lambda s: (s.lead_changes, s.total_movement,
                               1.0 - s.winner_low), reverse=True)
    return scored


def _probe(game_pk: int) -> None:
    plays = _get_json(WP_URL.format(game_pk=int(game_pk)))
    if not isinstance(plays, list):
        print("Unexpected response shape — not a list of plays.")
        return
    print(f"Total plays: {len(plays)}")
    if not plays:
        return
    series, innings, fa, fh = fetch_wp_series(int(game_pk))
    print(f"Series length: {len(series)}  final (away-home): {fa}-{fh}")
    if series:
        low = winner_low_point(series, fh or 0, fa or 0)
        leads = count_lead_changes(series)
        print(f"big_swings: {count_big_swings(series)}  lead_changes: {leads}  "
              f"winner_low: {low:.3f}  total_movement: {total_movement(series):.3f}")
        bf = (leads >= BACK_FORTH_MIN_LEAD_CHANGES
              and total_movement(series) >= BACK_FORTH_MIN_MOVEMENT)
        print(f"comeback: {low <= COMEBACK_MAX_LOW}  back_forth: {bf}")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--probe":
        _probe(sys.argv[2])
    elif len(sys.argv) >= 2:
        for s in score_date(sys.argv[1]):
            tag = []
            if s.is_comeback: tag.append("CB")
            if s.is_back_forth: tag.append("BF")
            mark = "+".join(tag) if tag else "--"
            print(f"{s.away} vs {s.home}  swings={s.big_swings} "
                  f"low={s.winner_low} move={s.total_movement}  [{mark}] {s.badge}")
    else:
        print("Usage: score_games.py <YYYY-MM-DD> | --probe <gamePk>")
