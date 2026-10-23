"""Shared matplotlib style for the report figures (static PNGs).

Colors follow a validated categorical palette, assigned in fixed order so a
series keeps its color across figures; text uses ink colors, never the
series color; grid and axes are recessive."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
SURFACE, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"


def figure(w=7.5, h=4.2):
    fig, ax = plt.subplots(figsize=(w, h), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(AXIS)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    return fig, ax


def title(ax, text, subtitle=None):
    ax.set_title(text, loc="left", color=INK, fontsize=12, pad=24 if subtitle else 10)
    if subtitle:      # fixed offset in points, so it never collides with the title
        ax.annotate(subtitle, xy=(0, 1), xycoords="axes fraction", xytext=(0, 7),
                    textcoords="offset points", color=INK2, fontsize=9, va="bottom")


def end_labels(ax, x, items, min_gap):
    """Direct labels at the right end of lines, nudged apart vertically.
    items: list of (y_value, text)."""
    placed = []
    for y, text in sorted(items):
        y_lab = max(y, placed[-1] + min_gap) if placed else y
        placed.append(y_lab)
        ax.text(x, y_lab, text, color=INK2, fontsize=8, va="center")


def save(fig, path):
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
