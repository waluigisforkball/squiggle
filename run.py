"""
Squiggle orchestrator.

Flow:
  1. Determine the slate date (yesterday in ET, since the 6am ET run covers
     games that finished overnight including West Coast).
  2. Score all completed games.
  3. Keep those clearing the excitement floor.
  4. If >=1 qualifies: build one spoiler-free ranked post and send it.
     If 0 qualify: do nothing (silent on dead nights).

Env flags:
  DRY_RUN=1   -> print the post instead of sending (no Bluesky call)
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

import score_games as sg
from format_post import build_post, SpoilerLeak


def slate_date() -> str:
    """Yesterday's date in US Eastern. ET = UTC-5/-4; -5 is safe for a 6am
    run since the slate is fully final regardless of DST."""
    et_now = datetime.now(timezone.utc) - timedelta(hours=5)
    return (et_now - timedelta(days=1)).strftime("%Y-%m-%d")


def main() -> int:
    date = sys.argv[1] if len(sys.argv) > 1 else slate_date()
    print(f"[squiggle] scoring slate {date}")

    scored = sg.score_date(date)
    qualifying = [s for s in scored if sg.qualifies(s)]
    print(f"[squiggle] {len(scored)} scored, {len(qualifying)} clear floor "
          f"({sg.EXCITEMENT_FLOOR})")

    if not qualifying:
        print("[squiggle] nothing clears the floor — staying silent.")
        return 0

    try:
        text = build_post(qualifying)
    except SpoilerLeak as e:
        print(f"[squiggle] ABORT — spoiler lint failed: {e}", file=sys.stderr)
        return 1

    if text is None:
        print("[squiggle] nothing to post.")
        return 0

    if os.environ.get("DRY_RUN") == "1":
        print("[squiggle] DRY_RUN — would post:\n")
        print(text)
        return 0

    from post import post_to_bluesky
    uri = post_to_bluesky(text)
    print(f"[squiggle] posted: {uri}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
