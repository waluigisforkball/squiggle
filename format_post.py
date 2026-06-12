"""
Format the daily shortlist into the Bluesky post text (Path B).

Now that Squiggle shows full WP charts, the post is no longer spoiler-free:
the text carries the matchup, badge, AND final score. The chart image carries
the win-probability story. No more spoiler lint.
"""

from __future__ import annotations

MAX_GAMES = 4          # top game + up to 3 more that clear the floor
INTRO = "Last night's squiggliest \u26be"
FOOTER = "Charts = win probability. \U0001F3A2 big swings \u00b7 \U0001F501 comeback from a deep hole"


def matchup_line(s) -> str:
    """One line per game: matchup, final score, badge."""
    return (f"{s.away} {s.away_score}, {s.home} {s.home_score}  {s.badge}")


def build_post_text(scored: list) -> str | None:
    """
    Build the post text from qualifying, pre-ranked games.
    Returns None if there's nothing to post.
    """
    games = scored[:MAX_GAMES]
    if not games:
        return None
    lines = [INTRO, ""]
    for i, s in enumerate(games, 1):
        lines.append(f"{i}. {matchup_line(s)}")
    lines.append("")
    lines.append(FOOTER)
    return "\n".join(lines)
