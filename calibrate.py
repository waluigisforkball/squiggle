"""
Floor calibration helper. Run against a few known dates to see the EI
distribution, then set EXCITEMENT_FLOOR in score_games.py on real numbers.

Usage:
    python calibrate.py 2024-09-26 2024-10-30 2024-07-04
Prints every game's EI sorted, so you can eyeball where blowouts end and
rollercoasters begin.
"""

from __future__ import annotations

import sys
import score_games as sg


def main(dates: list[str]) -> None:
    rows = []
    for d in dates:
        for s in sg.score_date(d):
            rows.append((s.excitement, d, f"{s.away} vs {s.home}",
                         s.lead_changes, s.late_tight, s.badge))
    rows.sort(reverse=True)
    print(f"{'EI':>6}  {'date':<10}  matchup")
    print("-" * 60)
    for ei, d, m, lc, lt, badge in rows:
        print(f"{ei:6.2f}  {d:<10}  {m}  (LC={lc} tight={lt}) {badge}")
    if rows:
        eis = [r[0] for r in rows]
        print("-" * 60)
        print(f"min={min(eis):.2f}  max={max(eis):.2f}  "
              f"median={sorted(eis)[len(eis)//2]:.2f}  n={len(eis)}")
        print("Set EXCITEMENT_FLOOR between the blowout cluster and the "
              "rollercoasters.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: calibrate.py <date> [date ...]")
        raise SystemExit(1)
    main(sys.argv[1:])
