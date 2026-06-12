"""
Format the daily shortlist into a single spoiler-free Bluesky post.

Spoiler safety is enforced two ways:
1. We only ever feed team names + badge into the copy (no scores, no winner).
2. A denylist lint runs on the FINAL string and aborts the post if anything
   result-revealing slips through.
"""

from __future__ import annotations

import re

MAX_GAMES = 3
INTRO = "Tonight's squiggliest ⚾️"
FOOTER = "Spoiler-free. Go watch before you scroll."

# Hard denylist — result-revealing language. Matched as whole words/phrases
# (word boundaries) so legitimate team names never trip it: "Twins" must not
# match "wins", "White Sox" must not match anything, etc.
DENY_TERMS = [
    "walk-off", "walkoff", "walk off",
    "comeback win", "win", "wins", "won", "beat", "defeat", "defeated",
    "final score", "clinch", "clinched", "sweep", "swept",
    "extra innings", "extras", "loses", "lost", "blowout",
]
# Compile each term with word boundaries. \b handles the Twins/wins problem:
# \bwins\b matches "team wins" but not the "wins" inside "Twins".
_DENY_PATTERNS = [re.compile(rf"\b{re.escape(t)}\b", re.IGNORECASE)
                  for t in DENY_TERMS]
# Any "digit-dash-digit" looks like a score; block it.
SCORE_PATTERN = re.compile(r"\b\d{1,2}\s*[-–]\s*\d{1,2}\b")


class SpoilerLeak(Exception):
    pass


def matchup_line(score) -> str:
    """Neutral matchup phrasing: 'Away vs Home  <badge>'. No '@', no result."""
    return f"{score.away} vs {score.home}  {score.badge}"


def build_post(scored: list) -> str | None:
    """
    Build the post string from qualifying, pre-ranked games.
    Returns None if there's nothing to post (caller stays silent).
    """
    qualifying = scored[:MAX_GAMES]
    if not qualifying:
        return None

    lines = [INTRO, ""]
    for i, s in enumerate(qualifying, 1):
        lines.append(f"{i}. {matchup_line(s)}")
    lines.append("")
    lines.append(FOOTER)
    text = "\n".join(lines)

    _lint_or_raise(text)
    return text


def _lint_or_raise(text: str) -> None:
    for pat in _DENY_PATTERNS:
        m = pat.search(text)
        if m:
            raise SpoilerLeak(f"Denylist term in post: {m.group(0)!r}")
    if SCORE_PATTERN.search(text):
        raise SpoilerLeak("Score-like pattern detected in post.")
