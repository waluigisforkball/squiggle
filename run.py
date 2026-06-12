"""
Squiggle orchestrator (Path B — charts).

Flow:
  1. Score all completed games for the slate date.
  2. Select games: the most exciting one ALWAYS posts; others join if they
     clear the excitement floor (up to MAX_GAMES total).
  3. Render a stacked WP chart PNG for the selected games.
  4. Build the post text (matchup + final score + badge).
  5. Post to Bluesky with the chart attached. In DRY_RUN, save the PNG and
     print the text instead of posting.

Env flags:
  DRY_RUN=1   -> render chart + print text, do not post. Saves chart to
                 ./squiggle_chart.png (uploaded as a workflow artifact).
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

import score_games as sg
from format_post import build_post_text, MAX_GAMES
from chart import render_chart

CHART_PATH = "squiggle_chart.png"


def slate_date() -> str:
    et_now = datetime.now(timezone.utc) - timedelta(hours=5)
    return (et_now - timedelta(days=1)).strftime("%Y-%m-%d")


def select_games(scored: list) -> list:
    """Top game always; others must clear the floor. Cap at MAX_GAMES."""
    if not scored:
        return []
    picked = [scored[0]]  # most exciting always posts
    for s in scored[1:]:
        if len(picked) >= MAX_GAMES:
            break
        if sg.qualifies(s):
            picked.append(s)
    return picked


def to_chart_dict(s) -> dict:
    return {
        "away": s.away, "home": s.home,
        "away_abbr": s.away_abbr, "home_abbr": s.home_abbr,
        "badge": s.badge, "series": s.series, "innings": s.innings,
    }


def main() -> int:
    date = sys.argv[1] if len(sys.argv) > 1 else slate_date()
    print(f"[squiggle] scoring slate {date}")

    scored = sg.score_date(date)
    if not scored:
        print("[squiggle] no completed games found — nothing to post.")
        return 0

    games = select_games(scored)
    print(f"[squiggle] {len(scored)} scored; posting {len(games)} "
          f"(floor {sg.EXCITEMENT_FLOOR})")

    text = build_post_text(games)
    if not text:
        print("[squiggle] nothing to post.")
        return 0

    chart_dicts = [to_chart_dict(s) for s in games]
    render_chart(chart_dicts, CHART_PATH)
    print(f"[squiggle] chart rendered -> {CHART_PATH}")

    alt = "Win probability charts for " + ", ".join(
        f"{s.away} vs {s.home}" for s in games)

    if os.environ.get("DRY_RUN") == "1":
        print("[squiggle] DRY_RUN — would post:\n")
        print(text)
        print(f"\n[squiggle] chart saved to {CHART_PATH} (not posted)")
        return 0

    from post import post_with_image
    uri = post_with_image(text, CHART_PATH, alt=alt[:300])
    print(f"[squiggle] posted: {uri}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
