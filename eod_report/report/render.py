"""Turn the section models plus commentary into one self-contained HTML email.

The template is deliberately dumb: this module formats every number, decides
every colour and assembles a plain view model of tables, paragraphs and
images, then Jinja renders it. Nothing in ``template.html.j2`` knows what a
troy ounce is, which keeps the porting job on the Rust side a matter of
producing the same view model.

Email constraints honoured here and in the template:

* table-based layout, inline CSS only, no ``<style>`` block, no classes,
  no flexbox or grid, no JavaScript, no external assets;
* 800px maximum width, Arial/Helvetica stack, Outlook assumed as worst case;
* numbers right-aligned with thousands separators and per-instrument decimals;
* green and red only on directional numbers, never as decoration.

Charts are embedded as base64 PNGs when ``config.EMBED_CHARTS_IN_EMAIL`` is on
and kaleido can render them; otherwise the email simply carries the tables,
which hold the same data.
"""

from __future__ import annotations

import base64
from datetime import datetime
from typing import Any, Iterable

from jinja2 import Environment, FileSystemLoader, select_autoescape

import charts
import config
from formatting import (
    fmt_date,
    fmt_date_short,
    fmt_datetime_london,
    fmt_lots,
    fmt_number,
    fmt_oz,
    fmt_pct,
    fmt_price,
    fmt_time,
    fmt_tonnes,
    fmt_usd_compact,
)
from models import (
    Commentary,
    EodReport,
    Metal,
    SectionKey,
)

COLOURS = config.EMAIL_COLOURS

#: Section number, heading and commentary key, in email order.
EMAIL_SECTIONS: tuple[tuple[int, str, SectionKey], ...] = (
    (1, "Client flows", SectionKey.CLIENT_FLOWS),
    (2, "Risk", SectionKey.RISK),
    (3, "Technicals", SectionKey.TECHNICALS),
    (4, "ETF holdings and flows", SectionKey.ETF_FLOWS),
    (5, "Open interest and positioning", SectionKey.POSITIONING),
    (6, "Physical inventories", SectionKey.PHYSICAL),
    (7, "Look ahead", SectionKey.LOOK_AHEAD),
)


# ---------------------------------------------------------------------------
# View-model primitives
# ---------------------------------------------------------------------------


def _cell(
    text: str, align: str = "right", colour: str | None = None, bold: bool = False
) -> dict[str, Any]:
    """One table cell. ``colour`` is a hex string or None for body text."""
    return {"text": text, "align": align, "colour": colour, "bold": bold}


def _table(
    columns: Iterable[tuple[str, str]],
    rows: list[list[dict[str, Any]]],
    caption: str | None = None,
) -> dict[str, Any]:
    """A table block: ``columns`` are ``(label, align)`` pairs."""
    return {
        "kind": "table",
        "caption": caption,
        "columns": [{"label": label, "align": align} for label, align in columns],
        "rows": rows,
    }


def _notes(lines: list[str], caption: str | None = None) -> dict[str, Any]:
    """A short list of labelled lines, used for the client axes."""
    return {"kind": "notes", "caption": caption, "lines": lines}


def _image(alt: str, data_uri: str, width: int) -> dict[str, Any]:
    return {"kind": "image", "alt": alt, "src": data_uri, "width": width}


def _signed_colour(value: float) -> str | None:
    """Green up, red down, nothing at all when flat."""
    if value > 0:
        return COLOURS["up"]
    if value < 0:
        return COLOURS["down"]
    return None


def _signed(text: str, value: float, bold: bool = False) -> dict[str, Any]:
    """Right-aligned cell coloured by the sign actually printed.

    Reading the colour off the formatted text rather than the raw value keeps
    the two in step: a figure that rounds to zero prints unsigned and so shows
    no colour, instead of a red "0.00".
    """
    printed = next((char for char in text if char in "+-"), "")
    colour = COLOURS["up"] if printed == "+" else COLOURS["down"] if printed == "-" else None
    return _cell(text, align="right", colour=colour, bold=bold)


def _price_decimals(metal: Metal) -> int:
    return config.PRICE_ANCHORS[metal.value].price_decimals


def _paragraphs(text: str) -> list[str]:
    """Split commentary into paragraphs on blank lines.

    An empty box yields an empty list, and the template renders nothing at all
    for it — no heading, no spacing, no trace.
    """
    blocks = [block.strip() for block in (text or "").strip().split("\n\n")]
    return [" ".join(block.split()) for block in blocks if block.strip()]


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------


def _png_data_uri(figure, width: int, height: int) -> str | None:
    """Render a plotly figure to a base64 PNG, or None when it cannot.

    Kaleido needs a headless Chrome; plenty of desks will not have one. A
    failure here is not an error — the email degrades to its tables.
    """
    if not config.EMBED_CHARTS_IN_EMAIL:
        return None
    try:
        png = figure.to_image(format="png", width=width, height=height, scale=2)
    except Exception:  # noqa: BLE001 — any kaleido/Chrome failure degrades
        return None
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


# ---------------------------------------------------------------------------
# Section builders — one per report section
# ---------------------------------------------------------------------------


def _snapshot_rows(report: EodReport) -> list[list[dict[str, Any]]]:
    rows = []
    for snapshot in report.header.snapshot:
        decimals = snapshot.price_decimals
        mark = "▲" if snapshot.change_usd_per_oz > 0 else "▼" if snapshot.change_usd_per_oz < 0 else "■"
        rows.append(
            [
                _cell(snapshot.metal.display_name, align="left", bold=True),
                _cell(fmt_price(snapshot.close_usd_per_oz, decimals), bold=True),
                _signed(
                    f"{mark} {fmt_number(snapshot.change_usd_per_oz, decimals, signed=True)}",
                    snapshot.change_usd_per_oz,
                ),
                _signed(fmt_pct(snapshot.change_pct), snapshot.change_pct),
                _cell(
                    f"{fmt_price(snapshot.session_low_usd_per_oz, decimals)} – "
                    f"{fmt_price(snapshot.session_high_usd_per_oz, decimals)}"
                ),
                _cell(fmt_price(snapshot.lbma_pm_auction_usd_per_oz, decimals)),
            ]
        )
    return rows


def _client_flow_blocks(report: EodReport, theme: str) -> list[dict[str, Any]]:
    section = report.client_flows
    blocks: list[dict[str, Any]] = [
        _table(
            (
                ("Metal", "left"),
                ("Net (oz)", "right"),
                ("Net (USD)", "right"),
                ("Gross (oz)", "right"),
                ("Unallocated (oz)", "right"),
                ("Tickets", "right"),
                ("Avg ticket (USD)", "right"),
            ),
            [
                [
                    _cell(flow.metal.display_name, align="left"),
                    _signed(fmt_oz(flow.net_client_oz, signed=True), flow.net_client_oz),
                    _signed(
                        fmt_usd_compact(flow.net_client_usd, signed=True), flow.net_client_usd
                    ),
                    _cell(fmt_oz(flow.gross_client_oz)),
                    _signed(
                        fmt_oz(flow.unallocated_balance_change_oz, signed=True),
                        flow.unallocated_balance_change_oz,
                    ),
                    _cell(fmt_number(flow.ticket_count)),
                    _cell(fmt_usd_compact(flow.average_ticket_size_usd)),
                ]
                for flow in section.metals
            ],
            caption="Positive is a client buy — the desk was the seller.",
        )
    ]

    chart = _png_data_uri(charts.client_flow_figure(section, theme, height=340), 720, 340)
    if chart:
        blocks.append(_image("Net client flow by segment", chart, width=720))

    segment_rows: list[list[dict[str, Any]]] = []
    for segment_code in config.CLIENT_SEGMENTS:
        cells = [_cell(config.CLIENT_SEGMENT_NAMES[segment_code], align="left")]
        present = False
        for flow in section.metals:
            entry = next(
                (r for r in flow.segment_breakdown if r.segment.value == segment_code), None
            )
            if entry:
                present = True
                cells.append(_signed(fmt_usd_compact(entry.net_usd, signed=True), entry.net_usd))
            else:
                cells.append(_cell("—"))
        if present:
            segment_rows.append(cells)
    blocks.append(
        _table(
            [("Segment", "left")] + [(flow.metal.display_name, "right") for flow in section.metals],
            segment_rows,
            caption="Net client flow by segment, USD notional",
        )
    )
    blocks.append(
        _notes(
            [f"{flow.metal.display_name}: {' · '.join(flow.top_axes)}" for flow in section.metals],
            caption="Top axes",
        )
    )
    return blocks


def _risk_blocks(report: EodReport) -> list[dict[str, Any]]:
    section = report.risk
    attribution = section.pnl_attribution
    return [
        _table(
            (
                ("Daily P&L", "right"),
                ("MTD", "right"),
                ("YTD", "right"),
                ("Desk VaR (1d, 99%)", "right"),
            ),
            [
                [
                    _signed(
                        fmt_usd_compact(section.daily_pnl_usd, signed=True),
                        section.daily_pnl_usd,
                        bold=True,
                    ),
                    _signed(fmt_usd_compact(section.mtd_pnl_usd, signed=True), section.mtd_pnl_usd),
                    _signed(fmt_usd_compact(section.ytd_pnl_usd, signed=True), section.ytd_pnl_usd),
                    _cell(fmt_usd_compact(section.desk_var_1d_99_usd)),
                ]
            ],
        ),
        _table(
            (
                ("Metal", "left"),
                ("Position (oz)", "right"),
                ("Delta-equiv (oz)", "right"),
                ("Notional (USD)", "right"),
                ("VaR 1d 99%", "right"),
            ),
            [
                [
                    _cell(position.metal.display_name, align="left"),
                    _signed(fmt_oz(position.position_oz, signed=True), position.position_oz),
                    _signed(
                        fmt_oz(position.delta_equivalent_oz, signed=True),
                        position.delta_equivalent_oz,
                    ),
                    _signed(
                        fmt_usd_compact(position.usd_notional, signed=True), position.usd_notional
                    ),
                    _cell(fmt_usd_compact(position.var_1d_99_usd)),
                ]
                for position in section.positions
            ],
            caption="Position is positive when long.",
        ),
        _table(
            (("P&L attribution", "left"), ("USD", "right")),
            [
                [_cell(label, align="left"), _signed(fmt_usd_compact(value, signed=True), value)]
                for label, value in (
                    ("Spot", attribution.spot_usd),
                    ("Carry / forward", attribution.carry_forward_usd),
                    ("Volatility", attribution.volatility_usd),
                    ("Client flow", attribution.client_flow_usd),
                    ("Other", attribution.other_usd),
                    ("Total", attribution.total_usd),
                )
            ],
        ),
        _table(
            (
                ("Metal", "left"),
                ("Delta (oz)", "right"),
                ("Gamma (oz/1%)", "right"),
                ("Vega (USD/vol pt)", "right"),
                ("Theta (USD/day)", "right"),
            ),
            [
                [
                    _cell(greek.metal.display_name, align="left"),
                    _signed(fmt_oz(greek.delta_oz, signed=True), greek.delta_oz),
                    _signed(fmt_oz(greek.gamma_oz_per_pct, signed=True), greek.gamma_oz_per_pct),
                    _signed(
                        fmt_usd_compact(greek.vega_usd_per_vol_pt, signed=True),
                        greek.vega_usd_per_vol_pt,
                    ),
                    _signed(
                        fmt_usd_compact(greek.theta_usd_per_day, signed=True),
                        greek.theta_usd_per_day,
                    ),
                ]
                for greek in section.greeks
            ],
            caption="Options greeks",
        ),
        _table(
            (("Limit", "left"), ("Limit (USD)", "right"), ("Used", "right"), ("Utilisation", "right")),
            [
                [
                    _cell(limit.limit_name, align="left"),
                    _cell(fmt_usd_compact(limit.limit_usd)),
                    _cell(fmt_usd_compact(limit.utilisation_usd)),
                    _cell(
                        fmt_pct(limit.utilisation_pct, 1, signed=False)
                        + (" — above threshold" if limit.above_warning_threshold else ""),
                        colour=COLOURS["flag"] if limit.above_warning_threshold else None,
                        bold=limit.above_warning_threshold,
                    ),
                ]
                for limit in section.limits
            ],
            caption=f"Limit utilisation, flagged at {config.LIMIT_WARNING_PCT:.0f}% of limit",
        ),
    ]


def _technicals_blocks(
    report: EodReport, theme: str, chart_metal: Metal
) -> list[dict[str, Any]]:
    section = report.technicals
    blocks = [
        _table(
            (
                ("Metal", "left"),
                ("Close", "right"),
                ("50-day / 200-day MA", "right"),
                ("RSI(14)", "right"),
                ("Trend", "left"),
                ("Nearest level", "right"),
                ("Realised / implied 1m", "right"),
            ),
            [
                [
                    _cell(block.metal.display_name, align="left"),
                    _cell(fmt_price(block.close_usd_per_oz, _price_decimals(block.metal)), bold=True),
                    _cell(
                        f"{fmt_price(block.ma_50_usd_per_oz, _price_decimals(block.metal))} / "
                        f"{fmt_price(block.ma_200_usd_per_oz, _price_decimals(block.metal))}"
                    ),
                    _cell(fmt_number(block.rsi_14, 1)),
                    _cell(block.trend_label.value, align="left"),
                    _cell(
                        f"{block.nearest_level_type.value} "
                        f"{fmt_price(block.nearest_level_usd_per_oz, _price_decimals(block.metal))}"
                        f" ({fmt_pct(block.distance_to_nearest_level_pct, 2, signed=False)})"
                    ),
                    _cell(
                        f"{fmt_pct(block.realised_vol_1m_pct, 1, signed=False)} / "
                        f"{fmt_pct(block.implied_vol_1m_pct, 1, signed=False)}"
                    ),
                ]
                for block in section.metals
            ],
        )
    ]

    charted = next(
        (block for block in section.metals if block.metal == chart_metal), section.metals[0]
    )
    figure = charts.price_figure(charted, theme, sessions=120, height=380)
    chart = _png_data_uri(figure, 720, 380)
    if chart:
        blocks.append(
            _image(
                f"{charted.metal.display_name} — close, moving averages and levels",
                chart,
                width=720,
            )
        )
    blocks.append(
        _table(
            (("Level", "left"), ("Type", "left"), ("Price (USD/oz)", "right"), ("Distance", "right")),
            [
                [
                    _cell(level.label, align="left"),
                    _cell(level.level_type.value, align="left"),
                    _cell(fmt_price(level.price_usd_per_oz, _price_decimals(charted.metal))),
                    # Distance to a level is a gap, not a move: no direction colour.
                    _cell(fmt_pct(level.distance_pct)),
                ]
                for level in list(charted.support_levels) + list(charted.resistance_levels)
            ],
            caption=f"{charted.metal.display_name} levels",
        )
    )
    return blocks


def _etf_blocks(report: EodReport) -> list[dict[str, Any]]:
    section = report.etf
    return [
        _table(
            (
                ("Fund", "left"),
                ("Metal", "left"),
                ("Holdings (t)", "right"),
                ("Daily (t)", "right"),
                ("Daily (USD)", "right"),
                # Three windows in one column: the email has to stay narrow
                # enough to read on a phone.
                ("WTD / MTD / YTD (t)", "right"),
                ("AUM", "right"),
            ),
            [
                [
                    _cell(fund.ticker, align="left"),
                    _cell(fund.metal.display_name, align="left"),
                    _cell(fmt_tonnes(fund.holdings_tonnes, 1)),
                    _signed(
                        fmt_tonnes(fund.daily_change_tonnes, 2, signed=True),
                        fund.daily_change_tonnes,
                    ),
                    _signed(
                        fmt_usd_compact(fund.daily_change_usd, signed=True), fund.daily_change_usd
                    ),
                    _cell(
                        f"{fmt_tonnes(fund.wtd_flow_tonnes, 1, signed=True)} / "
                        f"{fmt_tonnes(fund.mtd_flow_tonnes, 1, signed=True)} / "
                        f"{fmt_tonnes(fund.ytd_flow_tonnes, 1, signed=True)}"
                    ),
                    _cell(fmt_usd_compact(fund.aum_usd)),
                ]
                for fund in section.funds
            ],
            caption=section.reporting_lag_note,
        ),
        _table(
            (
                ("Metal", "left"),
                ("Holdings (t)", "right"),
                ("Daily (t)", "right"),
                ("Daily (USD)", "right"),
                ("WTD (t)", "right"),
                ("MTD (t)", "right"),
                ("YTD (t)", "right"),
            ),
            [
                [
                    _cell(aggregate.metal.display_name, align="left"),
                    _cell(fmt_tonnes(aggregate.holdings_tonnes, 1)),
                    _signed(
                        fmt_tonnes(aggregate.daily_change_tonnes, 2, signed=True),
                        aggregate.daily_change_tonnes,
                    ),
                    _signed(
                        fmt_usd_compact(aggregate.daily_change_usd, signed=True),
                        aggregate.daily_change_usd,
                    ),
                    _signed(
                        fmt_tonnes(aggregate.wtd_flow_tonnes, 1, signed=True),
                        aggregate.wtd_flow_tonnes,
                    ),
                    _signed(
                        fmt_tonnes(aggregate.mtd_flow_tonnes, 1, signed=True),
                        aggregate.mtd_flow_tonnes,
                    ),
                    _signed(
                        fmt_tonnes(aggregate.ytd_flow_tonnes, 1, signed=True),
                        aggregate.ytd_flow_tonnes,
                    ),
                ]
                for aggregate in section.metal_aggregates
            ],
            caption="Aggregate by metal",
        ),
    ]


def _positioning_blocks(report: EodReport) -> list[dict[str, Any]]:
    section = report.positioning
    return [
        _table(
            (
                ("Contract", "left"),
                ("Open interest", "right"),
                ("OI change", "right"),
                ("Volume", "right"),
                ("vs 20-day", "right"),
                ("Front month", "left"),
                ("Next active", "left"),
            ),
            [
                [
                    _cell(f"{contract.contract_code} · {contract.metal.display_name}", align="left"),
                    _cell(fmt_lots(contract.open_interest_lots)),
                    _signed(
                        fmt_lots(contract.open_interest_change_lots, signed=True),
                        contract.open_interest_change_lots,
                    ),
                    _cell(fmt_lots(contract.session_volume_lots)),
                    _signed(
                        fmt_pct(contract.volume_vs_20d_average_pct, 1),
                        contract.volume_vs_20d_average_pct,
                    ),
                    _cell(
                        f"{contract.front_month_code} "
                        f"(exp {fmt_date_short(contract.front_month_expiry_date)})",
                        align="left",
                    ),
                    _cell(contract.next_active_month_code, align="left"),
                ]
                for contract in section.contracts
            ],
            caption="COMEX open interest and volume, in contracts",
        ),
        _table(
            (
                ("Metal", "left"),
                ("Long", "right"),
                ("Short", "right"),
                ("Net", "right"),
                ("Net w/w", "right"),
                ("Net (oz)", "right"),
            ),
            [
                [
                    _cell(row.metal.display_name, align="left"),
                    _cell(fmt_lots(row.managed_money_long_lots)),
                    _cell(fmt_lots(row.managed_money_short_lots)),
                    _signed(
                        fmt_lots(row.managed_money_net_lots, signed=True),
                        row.managed_money_net_lots,
                    ),
                    _signed(fmt_lots(row.net_change_wow_lots, signed=True), row.net_change_wow_lots),
                    _signed(fmt_oz(row.net_oz, signed=True), row.net_oz),
                ]
                for row in section.cot
            ],
            caption=(
                f"Managed money, CFTC Commitments of Traders surveyed "
                f"{fmt_date(section.cot_report_date)} — {section.cot_lag_days} days before this "
                "report, in contracts"
            ),
        ),
        _table(
            (
                ("Metal", "left"),
                ("EFP (USD/oz)", "right"),
                ("20-day range", "right"),
                ("Status", "right"),
            ),
            [
                [
                    _cell(level.metal.display_name, align="left"),
                    _cell(fmt_number(level.efp_usd_per_oz, 2)),
                    _cell(
                        f"{fmt_number(level.recent_range_low_usd_per_oz, 2)} – "
                        f"{fmt_number(level.recent_range_high_usd_per_oz, 2)}"
                    ),
                    _cell(
                        "outside range" if level.outside_recent_range else "in range",
                        colour=COLOURS["flag"] if level.outside_recent_range else None,
                        bold=level.outside_recent_range,
                    ),
                ]
                for level in section.efp
            ],
            caption="EFP — futures over loco London spot",
        ),
    ]


def _physical_blocks(report: EodReport) -> list[dict[str, Any]]:
    section = report.physical
    blocks = [
        _table(
            (
                ("Metal", "left"),
                ("Registered (oz)", "right"),
                ("Registered Δ", "right"),
                ("Eligible (oz)", "right"),
                ("Eligible Δ", "right"),
                ("Total Δ", "right"),
            ),
            [
                [
                    _cell(stock.metal.display_name, align="left"),
                    _cell(fmt_oz(stock.registered_oz)),
                    _signed(
                        fmt_oz(stock.registered_change_oz, signed=True), stock.registered_change_oz
                    ),
                    _cell(fmt_oz(stock.eligible_oz)),
                    _signed(fmt_oz(stock.eligible_change_oz, signed=True), stock.eligible_change_oz),
                    _signed(fmt_oz(stock.total_change_oz, signed=True), stock.total_change_oz),
                ]
                for stock in section.comex_stocks
            ],
            caption="COMEX depository stocks, troy ounces",
        ),
        _table(
            (("Metal", "left"), ("London vaulted (t)", "right"), ("Month Δ (t)", "right"), ("Month Δ", "right")),
            [
                [
                    _cell(vault.metal.display_name, align="left"),
                    _cell(fmt_tonnes(vault.holdings_tonnes, 1)),
                    _signed(
                        fmt_tonnes(vault.month_change_tonnes, 1, signed=True),
                        vault.month_change_tonnes,
                    ),
                    _signed(fmt_pct(vault.month_change_pct), vault.month_change_pct),
                ]
                for vault in section.lbma_vault_holdings
            ],
            caption=section.lbma_monthly_note,
        ),
        _table(
            (
                ("Metal", "left"),
                ("SGE withdrawals (t)", "right"),
                ("Shanghai premium", "right"),
                ("Lease 1m", "right"),
                ("Lease 3m", "right"),
            ),
            [
                [
                    _cell(rate.metal.display_name, align="left"),
                    _cell(
                        fmt_tonnes(sge.withdrawals_tonnes, 1)
                        + f" ({sge.withdrawals_period_days}d)"
                        if sge
                        else "—"
                    ),
                    _signed(
                        fmt_number(sge.premium_usd_per_oz, 2, signed=True), sge.premium_usd_per_oz
                    )
                    if sge
                    else _cell("—"),
                    _cell(fmt_pct(rate.lease_rate_1m_pct, 2, signed=False)),
                    _cell(fmt_pct(rate.lease_rate_3m_pct, 2, signed=False)),
                ]
                for rate, sge in (
                    (
                        rate,
                        next((s for s in section.sge if s.metal == rate.metal), None),
                    )
                    for rate in section.lease_rates
                )
            ],
            caption="Shanghai withdrawals and premium over loco London; lease rates annualised",
        ),
    ]

    premium_rows: list[list[dict[str, Any]]] = []
    for location in config.PREMIUM_LOCATIONS:
        cells = [_cell(location, align="left")]
        for metal_code in config.METALS:
            premium = next(
                (
                    p
                    for p in section.loco_premiums
                    if p.location == location and p.metal.value == metal_code
                ),
                None,
            )
            cells.append(
                _signed(fmt_number(premium.premium_usd_per_oz, 2, signed=True), premium.premium_usd_per_oz)
                if premium
                else _cell("—")
            )
        premium_rows.append(cells)
    blocks.append(
        _table(
            [("Location", "left")] + [(Metal(code).display_name, "right") for code in config.METALS],
            premium_rows,
            caption="Loco premiums over London, USD per troy ounce",
        )
    )
    return blocks


def _calendar_table(events, caption: str) -> dict[str, Any]:
    return _table(
        (
            ("Date", "left"),
            ("London", "left"),
            ("Region", "left"),
            ("Event", "left"),
            ("Consensus", "right"),
            ("Previous", "right"),
        ),
        [
            [
                _cell(fmt_date_short(event.event_date), align="left"),
                _cell(fmt_time(event.event_time_london), align="left"),
                _cell(event.region, align="left"),
                _cell(
                    event.event_name + (f" — {event.note}" if event.note else ""),
                    align="left",
                    bold=event.importance.value == "high",
                ),
                _cell(event.consensus or "—"),
                _cell(event.previous or "—"),
            ]
            for event in events
        ],
        caption=caption,
    )


def _look_ahead_blocks(report: EodReport) -> list[dict[str, Any]]:
    section = report.look_ahead
    blocks = [
        _calendar_table(
            section.next_session_events, f"Next session — {fmt_date(section.next_session_date)}"
        ),
        _calendar_table(
            section.next_week_events,
            f"Rest of the week — {fmt_date(section.next_week_start_date)} to "
            f"{fmt_date(section.next_week_end_date)}",
        ),
        _table(
            (
                ("Metal", "left"),
                ("Contract", "left"),
                ("First notice", "left"),
                ("Last trade", "left"),
                ("Roll window", "left"),
            ),
            [
                [
                    _cell(window.metal.display_name, align="left"),
                    _cell(window.contract_code, align="left"),
                    _cell(fmt_date_short(window.first_notice_date), align="left"),
                    _cell(fmt_date_short(window.last_trade_date), align="left"),
                    _cell(
                        f"{fmt_date_short(window.roll_window_start_date)} – "
                        f"{fmt_date_short(window.roll_window_end_date)}",
                        align="left",
                    ),
                ]
                for window in section.roll_windows
            ],
            caption="Front-month roll windows",
        ),
    ]
    if section.holidays:
        blocks.append(
            _table(
                (("Date", "left"), ("Market", "left"), ("Holiday", "left")),
                [
                    [
                        _cell(fmt_date_short(holiday.event_date), align="left"),
                        _cell(holiday.region, align="left"),
                        _cell(holiday.event_name, align="left"),
                    ]
                    for holiday in section.holidays
                ],
                caption="Holidays affecting liquidity",
            )
        )
    return blocks


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def build_view_model(
    report: EodReport,
    commentary: Commentary,
    chart_metal: Metal | None = None,
    theme: str = "light",
) -> dict[str, Any]:
    """Everything the template needs, already formatted."""
    metal = chart_metal or report.technicals.default_chart_metal
    section_blocks = {
        SectionKey.CLIENT_FLOWS: lambda: _client_flow_blocks(report, theme),
        SectionKey.RISK: lambda: _risk_blocks(report),
        SectionKey.TECHNICALS: lambda: _technicals_blocks(report, theme, metal),
        SectionKey.ETF_FLOWS: lambda: _etf_blocks(report),
        SectionKey.POSITIONING: lambda: _positioning_blocks(report),
        SectionKey.PHYSICAL: lambda: _physical_blocks(report),
        SectionKey.LOOK_AHEAD: lambda: _look_ahead_blocks(report),
    }

    author = commentary.author_name or report.header.author_name
    return {
        "colours": COLOURS,
        "font_stack": config.EMAIL_FONT_STACK,
        "max_width": config.EMAIL_MAX_WIDTH_PX,
        "subject": email_subject(report, commentary),
        "report_label": report.header.report_label,
        "report_date": fmt_date(report.header.report_date),
        "generated_at": fmt_datetime_london(report.header.generated_at_london),
        "author": author,
        "headline": commentary.headline.strip() or report.header.headline.strip(),
        "market_overview": _paragraphs(commentary.text_for(SectionKey.MARKET_OVERVIEW)),
        "snapshot": _table(
            (
                ("Metal", "left"),
                ("Close (USD/oz)", "right"),
                ("Change", "right"),
                ("%", "right"),
                ("Session range", "right"),
                ("LBMA PM", "right"),
            ),
            _snapshot_rows(report),
        ),
        "sections": [
            {
                "number": number,
                "title": title,
                "commentary": _paragraphs(commentary.text_for(key)),
                "blocks": section_blocks[key](),
            }
            for number, title, key in EMAIL_SECTIONS
        ],
        "footer": (
            "Prototype report built from fabricated market data — not for trading or "
            "distribution. Figures carry the reporting lags noted in each section: ETF "
            "holdings are T+1, CFTC positioning is a weekly survey, LBMA vault data is "
            "monthly."
        ),
    }


def email_subject(report: EodReport, commentary: Commentary) -> str:
    """Subject line: label, date, and the headline when the analyst wrote one."""
    stem = f"Precious metals EOD — {fmt_date(report.header.report_date)}"
    headline = commentary.headline.strip()
    return f"{stem} — {headline}" if headline else stem


def _environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(config.TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_report(
    report: EodReport,
    commentary: Commentary,
    chart_metal: Metal | None = None,
    theme: str = "light",
) -> str:
    """Render one day's report to a single self-contained HTML string."""
    view_model = build_view_model(report, commentary, chart_metal, theme)
    template = _environment().get_template(config.TEMPLATE_NAME)
    return template.render(**view_model)


def _demo() -> None:
    """Render today's fabricated report to stdout — a quick smoke test."""
    from data.provider import build_report, get_provider

    report_date = datetime.now(config.LONDON_TZ).date()
    report = build_report(get_provider(), report_date, "A. Analyst")
    print(render_report(report, Commentary(report_date=report_date)))


if __name__ == "__main__":
    _demo()
