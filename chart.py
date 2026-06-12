"""
Render win-probability charts for the day's most exciting games.

Path B: full, readable WP charts (labeled axis, you can see who was favored).
Output is ONE PNG with the qualifying games stacked vertically — the top
(most exciting) game largest, others smaller below.

Clean minimal style: the squiggle line, a 50% midline, inning x-axis, a
home/away win-% y-axis, matchup + badge as the title. Sports-blue accent.

Requires matplotlib (headless 'Agg' backend — no display needed).
"""

from __future__ import annotations

import matplotlib
matplotlib.use("Agg")  # headless backend for GitHub Actions
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

# --- Brand tokens ---------------------------------------------------------
BG = "#15120a"          # dark header color
LINE = "#1a6ef5"        # sports-blue squiggle
MID = "#3a3528"         # 50% baseline (muted)
TEXT = "#f4f1e9"        # warm off-white
SUBTLE = "#8a8270"      # axis labels / ticks
FAVOR_HOME = "#1a6ef5"  # line color (single accent; we keep it one color)

plt.rcParams.update({
    "figure.facecolor": BG,
    "axes.facecolor": BG,
    "savefig.facecolor": BG,
    "text.color": TEXT,
    "axes.edgecolor": MID,
    "xtick.color": SUBTLE,
    "ytick.color": SUBTLE,
    "axes.labelcolor": SUBTLE,
    "font.family": "DejaVu Sans",
})

# matplotlib's font can't render emoji, so the chart uses a text label + color.
# (The emoji still appears in the Bluesky post text, which renders fine.)
BADGE_STYLE = {
    "🎢 Rollercoaster": ("ROLLERCOASTER", "#1a6ef5"),
    "🔁 Comeback":      ("COMEBACK", "#f5a31a"),
    "😬 Nailbiter":     ("NAILBITER", "#e0457b"),
}


def _badge_text_color(badge: str):
    return BADGE_STYLE.get(badge, (badge.split(" ", 1)[-1].upper(), SUBTLE))


def _draw_one(ax, game, is_hero: bool) -> None:
    """Draw a single game's WP chart onto a matplotlib axis."""
    series = game["series"]          # list of home win prob, 0..1
    innings = game["innings"]        # parallel list of inning numbers (ints)
    x = list(range(len(series)))

    # 50% midline
    ax.axhline(0.5, color=MID, lw=1.2, ls=(0, (1, 4)), zorder=1)

    # the squiggle
    lw = 3.2 if is_hero else 2.2
    ax.plot(x, series, color=LINE, lw=lw, solid_capstyle="round",
            solid_joinstyle="round", zorder=3)
    # endpoint dot
    ax.plot(x[-1], series[-1], "o", color=LINE,
            ms=7 if is_hero else 5, zorder=4)

    # y-axis: which team is favored at top (home) vs bottom (away)
    ax.set_ylim(0, 1)
    ax.set_yticks([0, 0.5, 1])
    ax.set_yticklabels([game['away_abbr'], "50%", game['home_abbr']],
                       fontsize=8 if is_hero else 7)

    # x-axis: inning ticks where the inning number changes
    tick_pos, tick_lab = [], []
    last = None
    for i, inn in enumerate(innings):
        if inn != last:
            tick_pos.append(i)
            tick_lab.append(str(inn))
            last = inn
    ax.set_xticks(tick_pos)
    ax.set_xticklabels(tick_lab, fontsize=7)
    ax.set_xlabel("inning", fontsize=8, labelpad=4)
    ax.set_xlim(0, len(series) - 1)

    # title: matchup (left) + styled badge text (its own color)
    matchup = f"{game['away']} vs {game['home']}"
    ax.set_title(matchup, fontsize=12 if is_hero else 10,
                 color=TEXT, pad=8, loc="left", fontweight="bold")
    label, color = _badge_text_color(game['badge'])
    ax.set_title(label, fontsize=9 if is_hero else 8,
                 color=color, pad=8, loc="right", fontweight="bold")

    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.tick_params(length=0)


def render_chart(games: list[dict], out_path: str) -> str:
    """
    games: ordered list (most exciting first), each a dict with:
        away, home, away_abbr, home_abbr, badge, series (0..1), innings (ints)
    Writes a stacked PNG to out_path. Returns out_path.
    """
    n = len(games)
    if n == 0:
        raise ValueError("No games to chart.")

    # Hero gets ~1.8x the height of the others.
    heights = [1.8] + [1.0] * (n - 1) if n > 1 else [1.6]
    fig_h = 2.4 * sum(heights) / (heights[0] if n == 1 else 1.0)
    fig_h = 3.2 + 2.0 * (n - 1)  # simple, readable scaling

    fig = plt.figure(figsize=(8, fig_h), dpi=150)
    gs = GridSpec(n, 1, height_ratios=heights, hspace=0.55,
                  left=0.16, right=0.96, top=0.93, bottom=0.08)

    for i, game in enumerate(games):
        ax = fig.add_subplot(gs[i])
        _draw_one(ax, game, is_hero=(i == 0))

    # footer wordmark
    fig.text(0.96, 0.015, "@squigglebaseball", ha="right", va="bottom",
             fontsize=7, color=SUBTLE)

    fig.savefig(out_path, facecolor=BG)
    plt.close(fig)
    return out_path
