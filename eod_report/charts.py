"""Plotly figures shared by the Streamlit app and the email renderer.

Two charts earn their place: the split of net client flow by segment, which is
hard to read as a column of numbers, and the price chart with its moving
averages and levels, which is the one picture an analyst actually reads.
Everything else in the report is a table and stays a table.

Both builders take a theme name (``"light"`` or ``"dark"``) and pull their
colours from ``config.CHART_COLOURS``. Segment hues are assigned in the fixed
order of ``config.CLIENT_SEGMENTS`` so a segment keeps its colour whatever
subset is on screen.
"""

from __future__ import annotations

import plotly.graph_objects as go

import config
from models import ClientFlowsSection, MetalTechnicals

#: Chart surfaces the palette was validated against.
SURFACES: dict[str, str] = {"light": "#fcfcfb", "dark": "#1a1a19"}

#: Web-safe stack, so a chart rendered to PNG matches the email's typeface.
FONT_FAMILY = "Arial, Helvetica, sans-serif"


def palette(theme: str) -> dict[str, str]:
    return config.CHART_COLOURS["dark" if theme == "dark" else "light"]


def segment_colour(theme: str, segment_code: str) -> str:
    """Fixed slot for a client segment — never cycled, never reordered."""
    slot = config.CLIENT_SEGMENTS.index(segment_code) + 1
    return palette(theme)[f"segment_{slot}"]


def _rolling_mean(values: list[float], window: int) -> list[float | None]:
    """Simple moving average, ``None`` until the window is full."""
    if len(values) < window:
        return [None] * len(values)
    series: list[float | None] = [None] * (window - 1)
    running = sum(values[:window])
    series.append(running / window)
    for index in range(window, len(values)):
        running += values[index] - values[index - window]
        series.append(running / window)
    return series


def _base_layout(theme: str, height: int) -> dict:
    colours = palette(theme)
    surface = SURFACES["dark" if theme == "dark" else "light"]
    return {
        "height": height,
        "margin": {"l": 8, "r": 8, "t": 36, "b": 8},
        "paper_bgcolor": surface,
        "plot_bgcolor": surface,
        "font": {"family": FONT_FAMILY, "size": 12, "color": colours["ink"]},
        "hoverlabel": {"font": {"family": FONT_FAMILY, "size": 12}},
        "legend": {
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "x": 0,
            "font": {"size": 11, "color": colours["muted"]},
        },
    }


def client_flow_figure(
    section: ClientFlowsSection, theme: str = "light", height: int = 380
) -> go.Figure:
    """Stacked bar of net client flow by segment, valued in USD millions.

    USD rather than ounces so the four metals share one axis: 12m ounces of
    silver and 60k ounces of palladium are not comparable, their notionals are.
    Positive is a client buy (the desk sold).
    """
    colours = palette(theme)
    metals = section.metals
    labels = [flow.metal.display_name for flow in metals]

    figure = go.Figure()
    for segment_code in config.CLIENT_SEGMENTS:
        values: list[float] = []
        present = False
        for flow in metals:
            row = next(
                (r for r in flow.segment_breakdown if r.segment.value == segment_code), None
            )
            values.append((row.net_usd / 1_000_000.0) if row else 0.0)
            present = present or row is not None
        if not present:
            continue  # segment trades none of these metals
        figure.add_bar(
            name=config.CLIENT_SEGMENT_NAMES[segment_code],
            x=labels,
            y=values,
            marker={
                "color": segment_colour(theme, segment_code),
                "line": {"color": SURFACES["dark" if theme == "dark" else "light"], "width": 2},
                "cornerradius": 4,
            },
            hovertemplate="%{fullData.name}<br>%{x}: %{y:+,.1f}m USD<extra></extra>",
        )

    figure.update_layout(
        **_base_layout(theme, height),
        barmode="relative",
        bargap=0.45,
        hovermode="closest",
    )
    figure.update_xaxes(
        showgrid=False,
        linecolor=colours["axis"],
        tickfont={"color": colours["ink"]},
    )
    figure.update_yaxes(
        title={"text": "Net client flow, USD m", "font": {"size": 11, "color": colours["muted"]}},
        gridcolor=colours["grid"],
        zerolinecolor=colours["axis"],
        zerolinewidth=1,
        tickformat=",.0f",
        tickfont={"color": colours["muted"]},
    )
    return figure


def price_figure(
    technicals: MetalTechnicals,
    theme: str = "light",
    sessions: int = 120,
    height: int = 430,
    title: str | None = None,
) -> go.Figure:
    """Close, three moving averages and the drawn support/resistance levels.

    Levels are dashed neutral lines with their own text labels rather than
    coloured by side, so the chart stays quiet and nothing is encoded in colour
    alone.
    """
    colours = palette(theme)
    bars = technicals.price_history[-sessions:]
    dates = [bar.session_date for bar in bars]
    closes = [bar.close_usd_per_oz for bar in bars]
    decimals = 2 if technicals.close_usd_per_oz < 100 else 0

    figure = go.Figure()
    figure.add_scatter(
        x=dates,
        y=closes,
        name="Close",
        mode="lines",
        line={"color": colours["price"], "width": 2},
        hovertemplate="%{x|%d %b %Y}<br>Close %{y:,." + str(decimals) + "f}<extra></extra>",
    )
    # The section carries each moving average's current value; the curve is
    # recomputed from the same history so the line is a line, not a level.
    full_closes = [bar.close_usd_per_oz for bar in technicals.price_history]
    for label, window, colour_key in (
        ("50-day MA", 50, "ma_50"),
        ("100-day MA", 100, "ma_100"),
        ("200-day MA", 200, "ma_200"),
    ):
        series = _rolling_mean(full_closes, window)[-sessions:]
        if all(value is None for value in series):
            continue  # not enough history to draw this average at all
        figure.add_scatter(
            x=dates,
            y=series,
            name=label,
            mode="lines",
            line={"color": colours[colour_key], "width": 2},
            connectgaps=False,
            hovertemplate=f"{label} %{{y:,.{decimals}f}}<extra></extra>",
        )

    # Levels are drawn as shapes with their labels parked in the right margin,
    # so a label never sits on top of the price line. Labels are nudged apart
    # when two levels sit close enough for their text to overlap.
    ordered_levels = sorted(
        list(technicals.support_levels) + list(technicals.resistance_levels),
        key=lambda item: item.price_usd_per_oz,
        reverse=True,
    )
    previous_price: float | None = None
    label_shift = 0
    for level in ordered_levels:
        if (
            previous_price is not None
            and (previous_price - level.price_usd_per_oz) / technicals.close_usd_per_oz < 0.012
        ):
            label_shift -= 13
        else:
            label_shift = 0
        previous_price = level.price_usd_per_oz
        figure.add_shape(
            type="line",
            xref="paper",
            x0=0,
            x1=1,
            yref="y",
            y0=level.price_usd_per_oz,
            y1=level.price_usd_per_oz,
            line={"color": colours["level"], "width": 1, "dash": "dot"},
            layer="below",
        )
        figure.add_annotation(
            xref="paper",
            x=1.01,
            xanchor="left",
            yref="y",
            y=level.price_usd_per_oz,
            yanchor="middle",
            yshift=label_shift,
            # Abbreviated for the margin; the table beside the chart spells it out.
            text=f"{level.label.replace('moving average', 'MA')} "
            f"{level.price_usd_per_oz:,.{decimals}f}",
            showarrow=False,
            align="left",
            font={"size": 10, "color": colours["muted"]},
        )

    layout = _base_layout(theme, height)
    layout["margin"]["r"] = 130  # room for the level labels
    if title:
        layout["title"] = {
            "text": title,
            "font": {"size": 14, "color": colours["ink"]},
            "x": 0,
            "xanchor": "left",
            "y": 0.97,
            "yanchor": "top",
        }
        layout["margin"]["t"] = 72
    figure.update_layout(**layout, hovermode="x unified")
    figure.update_xaxes(
        showgrid=False,
        linecolor=colours["axis"],
        tickfont={"color": colours["muted"]},
    )
    figure.update_yaxes(
        gridcolor=colours["grid"],
        tickformat=f",.{decimals}f",
        tickfont={"color": colours["muted"]},
        title={
            "text": "USD per troy ounce",
            "font": {"size": 11, "color": colours["muted"]},
        },
    )
    return figure
