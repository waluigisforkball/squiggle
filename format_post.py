"""
Format the daily shortlist into the Bluesky post text.

The chart image carries the visual badges and the win-probability story; the
text stays lean — a little voice up top, then clean game lines with the score
and a short plain-word tag. Minimal emoji.
"""

from __future__ import annotations
import random

MAX_GAMES = 4

# A bit of rotating voice so the daily post isn't robotic. Picked at random.
INTROS = [
    "Last night's most unwatchable-if-you-already-know-the-score games:",
    "Games that earned their squiggles last night:",
    "If you skipped these, the win-probability chart has notes:",
    "Last night in baseball, ranked by sheer cardiac activity:",
    "The squiggle does not lie. Last night's wildest:",
    "Box scores hide the chaos. These charts don't:",
]

# plain-word tag per badge (no emoji in text; chart shows the colored badge)
TEXT_TAG = {
    "🔁🎢 Comeback + Back-and-forth": "comeback AND a brawl",
    "🔁 Comeback": "back from the dead",
    "🎢 Back-and-forth": "traded haymakers",
}


def _tag(badge: str) -> str:
    return TEXT_TAG.get(badge, "")


def matchup_line(s) -> str:
    tag = _tag(s.badge)
    base = f"{s.away} {s.away_score}, {s.home} {s.home_score}"
    return f"{base} — {tag}" if tag else base


def build_post_text(scored: list) -> str | None:
    games = scored[:MAX_GAMES]
    if not games:
        return None
    lines = [random.choice(INTROS), ""]
    for s in games:
        lines.append(matchup_line(s))
    return "\n".join(lines)
