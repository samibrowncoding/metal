"""Shared chart helpers and the house style used across every notebook.

One place for colours, fonts and axis conventions so the charts in this repository
look like they came from the same desk. Static matplotlib for anything that ends up
in the docs, plotly for anything worth hovering over or rotating.

House rules applied here: every chart gets axis labels with units, and every chart
gets a one-line caption saying what to look at.

Import and call :func:`use_house_style` once at the top of a notebook.
"""

from __future__ import annotations

from typing import Any

import matplotlib as mpl
import matplotlib.pyplot as plt

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------
# A small categorical set that stays distinguishable in greyscale and for the most
# common colour vision deficiencies. Blue reads as the primary series throughout,
# amber as the comparison, and red is reserved for things that are wrong - a
# negative forward variance, a failing parity check.

INK = "#1a1a1a"
MUTED = "#6b7280"
GRID = "#e5e7eb"

PRIMARY = "#2563eb"     # blue - the main series
SECONDARY = "#d97706"   # amber - the comparison series
TERTIARY = "#059669"    # green - a third series
QUATERNARY = "#7c3aed"  # violet - a fourth
ALERT = "#dc2626"       # red - reserved for problems, never decoration

SERIES = (PRIMARY, SECONDARY, TERTIARY, QUATERNARY, "#0891b2", "#be185d")

# Semantic aliases, so call sites say what they mean rather than what colour it is.
CALL_COLOUR = PRIMARY
PUT_COLOUR = SECONDARY
DENSITY_COLOUR = "#93c5fd"
PAYOFF_COLOUR = SECONDARY
STRIKE_COLOUR = MUTED


def use_house_style() -> None:
    """Apply the house matplotlib style. Call once per notebook.

    Sets fonts, the categorical colour cycle, a light horizontal-only grid, and
    figure sizing. Deliberately not a .mplstyle file - keeping it as code means the
    palette constants above are the single source of truth for both matplotlib and
    plotly.
    """
    mpl.rcParams.update(
        {
            "figure.figsize": (9.0, 5.0),
            "figure.dpi": 110,
            "savefig.dpi": 160,
            "savefig.bbox": "tight",
            "font.family": "sans-serif",
            "font.sans-serif": ["DejaVu Sans", "Helvetica", "Arial"],
            "font.size": 10.5,
            "axes.titlesize": 12,
            "axes.titleweight": "bold",
            "axes.titlelocation": "left",
            "axes.titlepad": 10,
            "axes.labelsize": 10.5,
            "axes.labelcolor": INK,
            "axes.edgecolor": GRID,
            "axes.linewidth": 1.0,
            "axes.prop_cycle": mpl.cycler(color=list(SERIES)),
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "axes.axisbelow": True,
            "grid.color": GRID,
            "grid.linewidth": 0.8,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "xtick.labelsize": 9.5,
            "ytick.labelsize": 9.5,
            "legend.frameon": False,
            "legend.fontsize": 9.5,
            "lines.linewidth": 2.0,
            "lines.solid_capstyle": "round",
            "text.color": INK,
        }
    )


def style_axis(
    ax: plt.Axes,
    title: str,
    xlabel: str,
    ylabel: str,
    caption: str | None = None,
) -> plt.Axes:
    """Apply titles, axis labels and an optional caption to an axis.

    Args:
        ax: The axis to style.
        title: Chart title.
        xlabel: X axis label. **Include the units** - "Spot (CCY2 per CCY1)", not
            "Spot".
        ylabel: Y axis label, with units.
        caption: One line saying what the reader should look at. Rendered in muted
            text below the axis. This is a house rule, not decoration: a chart
            without a caption makes the reader guess what it is for.

    Returns:
        The same axis, so calls can be chained.
    """
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    if caption:
        ax.annotate(
            caption,
            xy=(0, -0.16),
            xycoords="axes fraction",
            fontsize=9,
            color=MUTED,
            ha="left",
            va="top",
            wrap=True,
        )
    return ax


def mark_level(
    ax: plt.Axes,
    x: float,
    label: str,
    colour: str = STRIKE_COLOUR,
    linestyle: str = "--",
) -> None:
    """Draw a labelled vertical reference line - a strike, a forward, an event date.

    Args:
        ax: Axis to draw on.
        x: Position on the x axis.
        label: Short label, drawn at the top of the line.
        colour: Line colour. Defaults to the muted grey used for strikes.
        linestyle: Matplotlib linestyle. Defaults to dashed.
    """
    ax.axvline(x, color=colour, linestyle=linestyle, linewidth=1.2, zorder=1)
    ax.annotate(
        label,
        xy=(x, 1.0),
        xycoords=("data", "axes fraction"),
        xytext=(3, -10),
        textcoords="offset points",
        fontsize=9,
        color=colour,
        ha="left",
        va="top",
    )


def as_percent(ax: plt.Axes, axis: str = "y", decimals: int = 1) -> None:
    """Format an axis as percentages, for values held as decimals.

    Everything internal to this package keeps volatilities and deltas as decimals
    (0.085, not 8.5). This puts the percent sign back on at the point of display,
    which is the only place it belongs.

    Args:
        ax: The axis to format.
        axis: ``"x"`` or ``"y"``. Defaults to ``"y"``.
        decimals: Decimal places to show. Defaults to 1.
    """
    formatter = mpl.ticker.PercentFormatter(xmax=1.0, decimals=decimals)
    target = ax.yaxis if axis == "y" else ax.xaxis
    target.set_major_formatter(formatter)


# ---------------------------------------------------------------------------
# Plotly
# ---------------------------------------------------------------------------

PLOTLY_LAYOUT: dict[str, Any] = {
    "template": "plotly_white",
    "font": {"family": "DejaVu Sans, Helvetica, Arial", "size": 12, "color": INK},
    "title": {"x": 0.0, "xanchor": "left", "font": {"size": 15}},
    "colorway": list(SERIES),
    "margin": {"l": 70, "r": 30, "t": 60, "b": 60},
    "hovermode": "x unified",
    "xaxis": {"gridcolor": GRID, "zerolinecolor": GRID},
    "yaxis": {"gridcolor": GRID, "zerolinecolor": GRID},
}
"""Layout dict matching the matplotlib house style, for plotly figures.

Apply with ``fig.update_layout(**PLOTLY_LAYOUT)``.
"""


def style_plotly(fig, title: str, xlabel: str, ylabel: str, caption: str | None = None):
    """Apply the house style to a plotly figure.

    Args:
        fig: A ``plotly.graph_objects.Figure``.
        title: Chart title.
        xlabel: X axis label, with units.
        ylabel: Y axis label, with units.
        caption: One line saying what to look at, added below the chart.

    Returns:
        The same figure, so calls can be chained.
    """
    fig.update_layout(**PLOTLY_LAYOUT)
    fig.update_layout(
        title_text=title,
        xaxis_title=xlabel,
        yaxis_title=ylabel,
    )
    if caption:
        fig.add_annotation(
            text=caption,
            xref="paper",
            yref="paper",
            x=0,
            y=-0.18,
            showarrow=False,
            font={"size": 11, "color": MUTED},
            xanchor="left",
        )
        fig.update_layout(margin={"b": 90})
    return fig
