"""
Render win-probability charts for the day's most exciting games (v3).

Adds soul:
  - Gradient line: colored by interpolating the away color (bottom) and home
    color (top) by the line's height, so the squiggle literally takes on the
    favored team's color as it rises/falls.
  - Team logos on the left axis (fetched from MLB's static CDN), with a
    colored-abbreviation fallback if a logo can't be loaded.
  - Roomier title spacing so matchup names never clip.

Requires matplotlib (+ numpy, bundled with it). Logo fetch uses urllib and
fails gracefully — a chart always renders even with no network.
"""

from __future__ import annotations

import io
import urllib.request

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection
from matplotlib.offsetbox import OffsetImage, AnnotationBbox

# --- Brand tokens (light theme) ------------------------------------------
BG = "#faf8f3"          # warm off-white background
MID = "#d6d0c4"         # 50% baseline (muted warm gray)
TEXT = "#15120a"        # near-black text
SUBTLE = "#8a8270"      # axis labels / ticks
DEFAULT_LINE = "#1a6ef5"

LOGO_URL = "https://www.mlbstatic.com/team-logos/{team_id}.svg"
# SVG won't load directly into matplotlib without cairosvg; we use the PNG
# cap logo spot endpoint which returns raster. Falls back to abbreviation.
LOGO_PNG_URL = ("https://midfield.mlbstatic.com/v1/team/{team_id}/spots/72")

plt.rcParams.update({
    "figure.facecolor": BG, "axes.facecolor": BG, "savefig.facecolor": BG,
    "text.color": TEXT, "axes.edgecolor": MID,
    "xtick.color": SUBTLE, "ytick.color": SUBTLE, "axes.labelcolor": SUBTLE,
    "font.family": "DejaVu Sans",
})

BADGE_STYLE = {
    "🎢 Back-and-forth": ("BACK-AND-FORTH", "#1457c4"),
    "🔁 Comeback": ("COMEBACK", "#c47a00"),
    "🔁🎢 Comeback + Back-and-forth": ("COMEBACK + B&F", "#c41e5a"),
}


def _badge(badge: str):
    return BADGE_STYLE.get(badge, (badge.split(" ", 1)[-1].upper(), SUBTLE))


def _hex_to_rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _vivid(rgb):
    """
    Make team colors pop on the cream background: boost saturation and lift
    very dark colors toward their hue so deep navies/maroons read as color,
    not as black. Keeps already-bright colors mostly as-is.
    """
    import colorsys
    r, g, b = rgb
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    s = min(1.0, s * 1.35 + 0.05)          # punch up saturation
    if l < 0.35:                            # lift very dark colors
        l = 0.42
    elif l > 0.82:                          # darken near-white a touch
        l = 0.70
    return colorsys.hls_to_rgb(h, l, s)


def _gradient_segments(x, y, away_rgb, home_rgb):
    """Build a LineCollection whose color interpolates away->home by height."""
    pts = np.array([x, y]).T.reshape(-1, 1, 2)
    segs = np.concatenate([pts[:-1], pts[1:]], axis=1)
    away = np.array(away_rgb)
    home = np.array(home_rgb)
    # color each segment by its midpoint height (0=away color, 1=home color)
    mids = (y[:-1] + y[1:]) / 2
    colors = [tuple(away + (home - away) * t) for t in mids]
    return LineCollection(segs, colors=colors)


def _load_logo(team_id: int):
    """Fetch a team logo as an image array, or None on any failure."""
    if not team_id:
        return None
    try:
        req = urllib.request.Request(
            LOGO_PNG_URL.format(team_id=team_id),
            headers={"User-Agent": "squiggle-bot"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = r.read()
        return plt.imread(io.BytesIO(data), format="png")
    except Exception:
        return None


def _draw_one(ax, g, is_hero: bool) -> None:
    series = g["series"]
    innings = g["innings"]
    x = np.arange(len(series))
    y = np.array(series)

    ax.axhline(0.5, color=MID, lw=1.2, ls=(0, (1, 4)), zorder=1)

    # gradient squiggle — vivid team colors, thick line
    away_rgb = _vivid(_hex_to_rgb(g["away_color"]))
    home_rgb = _vivid(_hex_to_rgb(g["home_color"]))
    lc = _gradient_segments(x, y, away_rgb, home_rgb)
    lc.set_linewidth(5.0 if is_hero else 3.6)
    lc.set_capstyle("round")
    lc.set_joinstyle("round")
    lc.set_zorder(3)
    ax.add_collection(lc)
    ax.plot(x[-1], y[-1], "o", color=home_rgb if y[-1] >= 0.5 else away_rgb,
            ms=9 if is_hero else 6, zorder=4)

    ax.set_ylim(0, 1)
    ax.set_yticks([0, 0.5, 1])
    ax.set_yticklabels(["", "50%", ""], fontsize=8 if is_hero else 7)

    # logos (or colored-abbr fallback) at the away(bottom)/home(top) ends
    _place_marker(ax, g["away_id"], g["away_abbr"], g["away_color"], y=0.0)
    _place_marker(ax, g["home_id"], g["home_abbr"], g["home_color"], y=1.0)

    # inning x-axis
    tick_pos, tick_lab, last = [], [], None
    for i, inn in enumerate(innings):
        if inn != last:
            tick_pos.append(i); tick_lab.append(str(inn)); last = inn
    ax.set_xticks(tick_pos)
    ax.set_xticklabels(tick_lab, fontsize=7)
    ax.set_xlabel("inning", fontsize=8, labelpad=3)
    ax.set_xlim(0, len(series) - 1)

    matchup = f"{g['away']} vs {g['home']}"
    ax.set_title(matchup, fontsize=12 if is_hero else 10, color=TEXT,
                 pad=14, loc="left", fontweight="bold")
    label, color = _badge(g["badge"])
    ax.set_title(label, fontsize=9 if is_hero else 8, color=color,
                 pad=14, loc="right", fontweight="bold")

    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.tick_params(length=0)


def _place_marker(ax, team_id, abbr, color, y):
    """Logo at the axis end if available, else a colored abbreviation."""
    logo = _load_logo(team_id)
    if logo is not None:
        im = OffsetImage(logo, zoom=0.32)
        ab = AnnotationBbox(im, (0, y), xycoords=("axes fraction", "data"),
                            box_alignment=(1.1, 0.5), frameon=False,
                            annotation_clip=False)
        ax.add_artist(ab)
    else:
        va = "bottom" if y == 0.0 else "top"
        ax.text(-0.02, y, abbr, transform=ax.get_yaxis_transform(),
                ha="right", va=va, fontsize=8, color=color, fontweight="bold")


def render_chart(games: list[dict], out_path: str) -> str:
    n = len(games)
    if n == 0:
        raise ValueError("No games to chart.")
    heights = [1.8] + [1.0] * (n - 1) if n > 1 else [1.6]
    fig_h = 3.4 + 2.0 * (n - 1)
    fig = plt.figure(figsize=(8, fig_h), dpi=150)
    gs = fig.add_gridspec(n, 1, height_ratios=heights, hspace=0.7,
                          left=0.13, right=0.95, top=0.90, bottom=0.08)
    for i, g in enumerate(games):
        _draw_one(fig.add_subplot(gs[i]), g, is_hero=(i == 0))
    fig.text(0.95, 0.012, "@squigglebaseball", ha="right", va="bottom",
             fontsize=7, color=SUBTLE)
    fig.savefig(out_path, facecolor=BG)
    plt.close(fig)
    return out_path
