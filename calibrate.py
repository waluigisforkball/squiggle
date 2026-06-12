"""
Two-lens calibration helper. Run against real slates to see the distribution
of big-swing counts and comeback low-points, so you can tune COMEBACK_MAX_LOW
and BACK_FORTH_MIN_SWINGS in score_games.py on real numbers.

Usage:
    python calibrate.py 2026-06-10 2026-06-09 2026-06-08
"""

from __future__ import annotations

import sys
import score_games as sg


def main(dates: list[str]) -> None:
    rows = []
    for d in dates:
        for s in sg.score_date(d):
            rows.append((s.big_swings, s.winner_low, s.total_movement, d,
                         f"{s.away} vs {s.home}", s.is_comeback, s.is_back_forth))
    rows.sort(reverse=True)
    print(f"{'swings':>6} {'low':>6} {'move':>6}  date        matchup")
    print("-" * 72)
    for sw, low, mv, d, m, cb, bf in rows:
        tag = "+".join([t for t, on in (("CB", cb), ("BF", bf)) if on]) or "--"
        print(f"{sw:>6} {low:>6.3f} {mv:>6.2f}  {d:<10}  {m}  [{tag}]")
    if rows:
        cbs = sum(1 for r in rows if r[5])
        bfs = sum(1 for r in rows if r[6])
        print("-" * 72)
        print(f"{len(rows)} games | comebacks: {cbs} | back-and-forth: {bfs} "
              f"| thresholds: low<={sg.COMEBACK_MAX_LOW} swings>={sg.BACK_FORTH_MIN_SWINGS}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: calibrate.py <date> [date ...]")
        raise SystemExit(1)
    main(sys.argv[1:])
