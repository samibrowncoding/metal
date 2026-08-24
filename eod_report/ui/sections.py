"""One render function per report section.

Each function takes its own section model and draws the data only — commentary
boxes are placed beside these by ``app.py``, so an analyst reads the numbers and
writes about them without scrolling.

Tables are built from preformatted strings through :mod:`formatting`, so a
figure looks the same here as it does in the email.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

import charts
import config
from formatting import (
    fmt_date,
    fmt_date_short,
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
    ClientFlowsSection,
    EtfSection,
    LookAheadSection,
    Metal,
    PhysicalSection,
    PositioningSection,
    ReportHeader,
    RiskSection,
    TechnicalsSection,
)

_FLAG = "⚠"


def _table(rows: list[dict[str, str]], height: int | None = None) -> None:
    """Render a list of already-formatted rows as a borderless table."""
    st.dataframe(pd.DataFrame(rows), hide_index=True, height=height or "auto")


def _price_decimals(metal: Metal) -> int:
    return config.PRICE_ANCHORS[metal.value].price_decimals


# ---------------------------------------------------------------------------
# Section 0 — header snapshot
# ---------------------------------------------------------------------------


def render_snapshot(header: ReportHeader) -> None:
    """The strip of per-metal closes that opens the report."""
    columns = st.columns(len(header.snapshot))
    for column, snapshot in zip(columns, header.snapshot):
        decimals = snapshot.price_decimals
        with column:
            st.metric(
                label=f"{snapshot.metal.display_name} ({snapshot.metal.value})",
                value=fmt_price(snapshot.close_usd_per_oz, decimals),
                delta=(
                    f"{fmt_number(snapshot.change_usd_per_oz, decimals, signed=True)} "
                    f"({fmt_pct(snapshot.change_pct)})"
                ),
            )

    _table(
        [
            {
                "Metal": s.metal.display_name,
                "Close (USD/oz)": fmt_price(s.close_usd_per_oz, s.price_decimals),
                "Prior close": fmt_price(s.prior_close_usd_per_oz, s.price_decimals),
                "Change": fmt_price(s.change_usd_per_oz, s.price_decimals),
                "Change %": fmt_pct(s.change_pct),
                "Session high": fmt_price(s.session_high_usd_per_oz, s.price_decimals),
                "Session low": fmt_price(s.session_low_usd_per_oz, s.price_decimals),
                "LBMA PM auction": fmt_price(s.lbma_pm_auction_usd_per_oz, s.price_decimals),
            }
            for s in header.snapshot
        ]
    )


# ---------------------------------------------------------------------------
# Section 1 — client flows
# ---------------------------------------------------------------------------


def render_client_flows(section: ClientFlowsSection, theme: str = "light") -> None:
    st.caption(
        f"{fmt_number(section.total_ticket_count)} tickets · "
        f"{fmt_usd_compact(section.total_gross_usd)} gross traded with clients. "
        "Positive is a client buy (the desk sold)."
    )

    _table(
        [
            {
                "Metal": flow.metal.display_name,
                "Side": flow.net_client_side.value.upper(),
                "Net (oz)": fmt_oz(flow.net_client_oz, signed=True),
                "Net (USD)": fmt_usd_compact(flow.net_client_usd, signed=True),
                "Gross (oz)": fmt_oz(flow.gross_client_oz),
                "Unallocated Δ (oz)": fmt_oz(flow.unallocated_balance_change_oz, signed=True),
                "Tickets": fmt_number(flow.ticket_count),
                "Avg ticket (oz)": fmt_oz(flow.average_ticket_size_oz),
                "Avg ticket (USD)": fmt_usd_compact(flow.average_ticket_size_usd),
            }
            for flow in section.metals
        ]
    )

    st.plotly_chart(
        charts.client_flow_figure(section, theme),
        theme=None,
        key="client_flow_chart",
    )

    # The chart's own table view: identity never rests on colour alone.
    segment_rows: list[dict[str, str]] = []
    for segment_code in config.CLIENT_SEGMENTS:
        row: dict[str, str] = {"Segment": config.CLIENT_SEGMENT_NAMES[segment_code]}
        present = False
        for flow in section.metals:
            entry = next(
                (r for r in flow.segment_breakdown if r.segment.value == segment_code), None
            )
            row[flow.metal.display_name] = (
                fmt_usd_compact(entry.net_usd, signed=True) if entry else "—"
            )
            present = present or entry is not None
        if present:
            segment_rows.append(row)
    st.caption("Net client flow by segment, USD notional")
    _table(segment_rows)

    st.caption("Top axes")
    for flow in section.metals:
        axes = " · ".join(flow.top_axes)
        st.markdown(f"**{flow.metal.display_name}** — {axes}")


# ---------------------------------------------------------------------------
# Section 2 — risk
# ---------------------------------------------------------------------------


def render_risk(section: RiskSection) -> None:
    pnl_columns = st.columns(4)
    for column, (label, value) in zip(
        pnl_columns,
        (
            ("Daily P&L", section.daily_pnl_usd),
            ("MTD P&L", section.mtd_pnl_usd),
            ("YTD P&L", section.ytd_pnl_usd),
            ("Desk VaR (1d, 99%)", -section.desk_var_1d_99_usd),
        ),
    ):
        with column:
            st.metric(label, fmt_usd_compact(value, signed=label != "Desk VaR (1d, 99%)"))

    _table(
        [
            {
                "Metal": position.metal.display_name,
                "Position (oz)": fmt_oz(position.position_oz, signed=True),
                "Delta-equivalent (oz)": fmt_oz(position.delta_equivalent_oz, signed=True),
                "Notional (USD)": fmt_usd_compact(position.usd_notional, signed=True),
                "VaR 1d 99% (USD)": fmt_usd_compact(position.var_1d_99_usd),
            }
            for position in section.positions
        ]
    )

    left, right = st.columns(2)
    with left:
        st.caption("P&L attribution")
        attribution = section.pnl_attribution
        _table(
            [
                {"Driver": "Spot", "USD": fmt_usd_compact(attribution.spot_usd, signed=True)},
                {
                    "Driver": "Carry / forward",
                    "USD": fmt_usd_compact(attribution.carry_forward_usd, signed=True),
                },
                {
                    "Driver": "Volatility",
                    "USD": fmt_usd_compact(attribution.volatility_usd, signed=True),
                },
                {
                    "Driver": "Client flow",
                    "USD": fmt_usd_compact(attribution.client_flow_usd, signed=True),
                },
                {"Driver": "Other", "USD": fmt_usd_compact(attribution.other_usd, signed=True)},
                {"Driver": "Total", "USD": fmt_usd_compact(attribution.total_usd, signed=True)},
            ]
        )
    with right:
        st.caption("Options greeks")
        _table(
            [
                {
                    "Metal": greek.metal.display_name,
                    "Delta (oz)": fmt_oz(greek.delta_oz, signed=True),
                    "Gamma (oz per 1%)": fmt_oz(greek.gamma_oz_per_pct, signed=True),
                    "Vega (USD/vol pt)": fmt_usd_compact(greek.vega_usd_per_vol_pt, signed=True),
                    "Theta (USD/day)": fmt_usd_compact(greek.theta_usd_per_day, signed=True),
                }
                for greek in section.greeks
            ]
        )

    st.caption(f"Limit utilisation — flagged at {config.LIMIT_WARNING_PCT:.0f}% of limit")
    _table(
        [
            {
                "Limit": limit.limit_name,
                "Limit (USD)": fmt_usd_compact(limit.limit_usd),
                "Utilisation (USD)": fmt_usd_compact(limit.utilisation_usd),
                "Utilisation %": fmt_pct(limit.utilisation_pct, decimals=1, signed=False),
                "Status": f"{_FLAG} above threshold" if limit.above_warning_threshold else "OK",
            }
            for limit in section.limits
        ]
    )
    if section.any_limit_flagged:
        st.warning("At least one limit is at or above its warning threshold.", icon=_FLAG)


# ---------------------------------------------------------------------------
# Section 3 — technicals
# ---------------------------------------------------------------------------


def render_technicals(section: TechnicalsSection, theme: str = "light") -> None:
    _table(
        [
            {
                "Metal": block.metal.display_name,
                "Close": fmt_price(block.close_usd_per_oz, _price_decimals(block.metal)),
                "50-day MA": fmt_price(block.ma_50_usd_per_oz, _price_decimals(block.metal)),
                "100-day MA": fmt_price(block.ma_100_usd_per_oz, _price_decimals(block.metal)),
                "200-day MA": fmt_price(block.ma_200_usd_per_oz, _price_decimals(block.metal)),
                "RSI(14)": fmt_number(block.rsi_14, 1),
                "Trend": block.trend_label.value,
                "Nearest level": (
                    f"{block.nearest_level_type.value} "
                    f"{fmt_price(block.nearest_level_usd_per_oz, _price_decimals(block.metal))}"
                ),
                "Distance": fmt_pct(block.distance_to_nearest_level_pct, signed=False),
                "Realised vol 1m": fmt_pct(block.realised_vol_1m_pct, 1, signed=False),
                "Implied vol 1m": fmt_pct(block.implied_vol_1m_pct, 1, signed=False),
                "Implied − realised": fmt_pct(block.vol_spread_pct, 1),
            }
            for block in section.metals
        ]
    )

    picker, window = st.columns([3, 2])
    with picker:
        chart_metal = st.radio(
            "Chart",
            options=[block.metal for block in section.metals],
            format_func=lambda metal: metal.display_name,
            horizontal=True,
            key="chart_metal",
            index=[block.metal for block in section.metals].index(section.default_chart_metal),
        )
    with window:
        sessions = st.select_slider(
            "Sessions shown",
            options=[60, 120, section.history_session_count],
            value=120,
            key="chart_sessions",
        )

    block = next(item for item in section.metals if item.metal == chart_metal)
    st.plotly_chart(
        charts.price_figure(block, theme, sessions=sessions),
        theme=None,
        key="price_chart",
    )

    levels = list(block.support_levels) + list(block.resistance_levels)
    _table(
        [
            {
                "Level": level.label,
                "Type": level.level_type.value,
                "Price (USD/oz)": fmt_price(level.price_usd_per_oz, _price_decimals(block.metal)),
                "Distance": fmt_pct(level.distance_pct),
            }
            for level in levels
        ]
    )


# ---------------------------------------------------------------------------
# Section 4 — ETF holdings and flows
# ---------------------------------------------------------------------------


def render_etf(section: EtfSection) -> None:
    st.caption(section.reporting_lag_note)
    _table(
        [
            {
                "Fund": f"{fund.ticker} — {fund.fund_name}",
                "Metal": fund.metal.display_name,
                "Holdings (t)": fmt_tonnes(fund.holdings_tonnes, 1),
                "Daily Δ (t)": fmt_tonnes(fund.daily_change_tonnes, 2, signed=True),
                "Daily Δ (USD)": fmt_usd_compact(fund.daily_change_usd, signed=True),
                "AUM (USD)": fmt_usd_compact(fund.aum_usd),
                "WTD (t)": fmt_tonnes(fund.wtd_flow_tonnes, 1, signed=True),
                "MTD (t)": fmt_tonnes(fund.mtd_flow_tonnes, 1, signed=True),
                "YTD (t)": fmt_tonnes(fund.ytd_flow_tonnes, 1, signed=True),
                "YTD (USD)": fmt_usd_compact(fund.ytd_flow_usd, signed=True),
            }
            for fund in section.funds
        ]
    )

    st.caption("Aggregate by metal")
    _table(
        [
            {
                "Metal": aggregate.metal.display_name,
                "Holdings (t)": fmt_tonnes(aggregate.holdings_tonnes, 1),
                "Daily Δ (t)": fmt_tonnes(aggregate.daily_change_tonnes, 2, signed=True),
                "Daily Δ (USD)": fmt_usd_compact(aggregate.daily_change_usd, signed=True),
                "WTD (t)": fmt_tonnes(aggregate.wtd_flow_tonnes, 1, signed=True),
                "MTD (t)": fmt_tonnes(aggregate.mtd_flow_tonnes, 1, signed=True),
                "YTD (t)": fmt_tonnes(aggregate.ytd_flow_tonnes, 1, signed=True),
                "AUM (USD)": fmt_usd_compact(aggregate.aum_usd),
            }
            for aggregate in section.metal_aggregates
        ]
    )


# ---------------------------------------------------------------------------
# Section 5 — open interest and positioning
# ---------------------------------------------------------------------------


def render_positioning(section: PositioningSection) -> None:
    _table(
        [
            {
                "Contract": contract.contract_code,
                "Metal": contract.metal.display_name,
                "Open interest (lots)": fmt_lots(contract.open_interest_lots),
                "OI Δ (lots)": fmt_lots(contract.open_interest_change_lots, signed=True),
                "Volume (lots)": fmt_lots(contract.session_volume_lots),
                "20-day avg (lots)": fmt_lots(contract.volume_20d_average_lots),
                "vs 20-day": fmt_pct(contract.volume_vs_20d_average_pct, 1),
                "Front month": (
                    f"{contract.front_month_code} "
                    f"(exp {fmt_date_short(contract.front_month_expiry_date)})"
                ),
                "Next active": contract.next_active_month_code,
            }
            for contract in section.contracts
        ]
    )

    st.caption(
        f"Managed money — CFTC Commitments of Traders surveyed "
        f"{fmt_date(section.cot_report_date)}, {section.cot_lag_days} days before this report"
    )
    _table(
        [
            {
                "Metal": row.metal.display_name,
                "Long (lots)": fmt_lots(row.managed_money_long_lots),
                "Short (lots)": fmt_lots(row.managed_money_short_lots),
                "Net (lots)": fmt_lots(row.managed_money_net_lots, signed=True),
                "Net w/w (lots)": fmt_lots(row.net_change_wow_lots, signed=True),
                "Net (oz)": fmt_oz(row.net_oz, signed=True),
                "Published": fmt_date(row.published_date),
            }
            for row in section.cot
        ]
    )

    st.caption("EFP — futures over loco London spot")
    _table(
        [
            {
                "Metal": level.metal.display_name,
                "EFP (USD/oz)": fmt_number(level.efp_usd_per_oz, 2),
                "20-day range": (
                    f"{fmt_number(level.recent_range_low_usd_per_oz, 2)} – "
                    f"{fmt_number(level.recent_range_high_usd_per_oz, 2)}"
                ),
                "Status": (
                    f"{_FLAG} outside range" if level.outside_recent_range else "in range"
                ),
            }
            for level in section.efp
        ]
    )
    if section.any_efp_flagged:
        st.warning("EFP is outside its recent range in at least one metal.", icon=_FLAG)


# ---------------------------------------------------------------------------
# Section 6 — physical inventories
# ---------------------------------------------------------------------------


def render_physical(section: PhysicalSection) -> None:
    st.caption("COMEX depository stocks (troy ounces)")
    _table(
        [
            {
                "Metal": stock.metal.display_name,
                "Registered": fmt_oz(stock.registered_oz),
                "Registered Δ": fmt_oz(stock.registered_change_oz, signed=True),
                "Eligible": fmt_oz(stock.eligible_oz),
                "Eligible Δ": fmt_oz(stock.eligible_change_oz, signed=True),
                "Total": fmt_oz(stock.total_oz),
                "Total Δ": fmt_oz(stock.total_change_oz, signed=True),
            }
            for stock in section.comex_stocks
        ]
    )

    st.caption(section.lbma_monthly_note)
    _table(
        [
            {
                "Metal": vault.metal.display_name,
                "London vaulted (t)": fmt_tonnes(vault.holdings_tonnes, 1),
                "Month Δ (t)": fmt_tonnes(vault.month_change_tonnes, 1, signed=True),
                "Month Δ %": fmt_pct(vault.month_change_pct),
                "As at": fmt_date(vault.as_of_month_end),
            }
            for vault in section.lbma_vault_holdings
        ]
    )

    left, right = st.columns(2)
    with left:
        st.caption("Shanghai Gold Exchange")
        _table(
            [
                {
                    "Metal": row.metal.display_name,
                    f"Withdrawals ({row.withdrawals_period_days}d, t)": fmt_tonnes(
                        row.withdrawals_tonnes, 1
                    ),
                    "Premium (USD/oz)": fmt_number(row.premium_usd_per_oz, 2, signed=True),
                    "Premium %": fmt_pct(row.premium_pct),
                }
                for row in section.sge
            ]
        )
        st.caption("Lease rates (annualised)")
        _table(
            [
                {
                    "Metal": rate.metal.display_name,
                    "1-month": fmt_pct(rate.lease_rate_1m_pct, signed=False),
                    "3-month": fmt_pct(rate.lease_rate_3m_pct, signed=False),
                }
                for rate in section.lease_rates
            ]
        )
    with right:
        st.caption("Loco premiums over London (USD/oz)")
        rows: list[dict[str, str]] = []
        for location in config.PREMIUM_LOCATIONS:
            row: dict[str, str] = {"Location": location}
            for premium in section.loco_premiums:
                if premium.location == location:
                    row[premium.metal.display_name] = fmt_number(
                        premium.premium_usd_per_oz, 2, signed=True
                    )
            rows.append(row)
        _table(rows)


# ---------------------------------------------------------------------------
# Section 7 — look ahead
# ---------------------------------------------------------------------------


def _calendar_rows(events) -> list[dict[str, str]]:
    return [
        {
            "Date": fmt_date_short(event.event_date),
            "Time (London)": fmt_time(event.event_time_london),
            "Region": event.region,
            "Event": event.event_name,
            "Consensus": event.consensus or "—",
            "Previous": event.previous or "—",
            "Importance": event.importance.value,
            "Note": event.note or "",
        }
        for event in events
    ]


def render_look_ahead(section: LookAheadSection) -> None:
    st.caption(f"Next session — {fmt_date(section.next_session_date)}")
    _table(_calendar_rows(section.next_session_events))

    st.caption(
        f"Rest of the week — {fmt_date(section.next_week_start_date)} to "
        f"{fmt_date(section.next_week_end_date)}"
    )
    _table(_calendar_rows(section.next_week_events))

    left, right = st.columns(2)
    with left:
        st.caption("Front-month roll windows")
        _table(
            [
                {
                    "Metal": window.metal.display_name,
                    "Contract": window.contract_code,
                    "First notice": fmt_date_short(window.first_notice_date),
                    "Last trade": fmt_date_short(window.last_trade_date),
                    "Roll window": (
                        f"{fmt_date_short(window.roll_window_start_date)} – "
                        f"{fmt_date_short(window.roll_window_end_date)}"
                    ),
                }
                for window in section.roll_windows
            ]
        )
    with right:
        st.caption("Holidays affecting liquidity")
        if section.holidays:
            _table(
                [
                    {
                        "Date": fmt_date_short(holiday.event_date),
                        "Market": holiday.region,
                        "Holiday": holiday.event_name,
                    }
                    for holiday in section.holidays
                ]
            )
        else:
            st.caption("None within the look-ahead window.")
