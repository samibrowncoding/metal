"""Deterministic fabricated market data.

Every number in this module is invented. Nothing here touches the network.

Determinism
-----------
All randomness comes from :func:`_rng`, which seeds ``random.Random`` from the
report date, a stream name and ``config.MOCK_SEED_SALT``. The same date always
produces the same report, and the streams are independent, so adding a section
never shifts the numbers in the sections beside it.

Plausibility
------------
Prices are drawn inside the anchors in ``config.PRICE_ANCHORS``. Everything
downstream is derived from those prices rather than fabricated separately, so
the report ties together: ETF flows are valued at the session close, risk
notionals divide by it, EFP quotes sit on top of it, and limit utilisation
falls out of the positions rather than being drawn independently.
"""

from __future__ import annotations

import calendar
import math
import zlib
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from random import Random

import config
from models import (
    CalendarEvent,
    ClientFlowsSection,
    ClientSegment,
    ClientSegmentFlow,
    ComexContractActivity,
    ComexStocks,
    ContractRollWindow,
    CotManagedMoney,
    DeskPosition,
    Direction,
    EfpLevel,
    EtfFundFlow,
    EtfMetalAggregate,
    EtfSection,
    EventCategory,
    EventImportance,
    LbmaVaultHolding,
    LeaseRate,
    LevelType,
    LimitUtilisation,
    LocoPremium,
    LookAheadSection,
    Metal,
    MetalClientFlow,
    MetalSnapshot,
    MetalTechnicals,
    OptionsGreeks,
    PhysicalSection,
    PnlAttribution,
    PositioningSection,
    PriceBar,
    ReportHeader,
    RiskSection,
    SgeActivity,
    TechnicalLevel,
    TechnicalsSection,
    TradeSide,
    TrendLabel,
)

# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------


def _rng(report_date: date, stream: str) -> Random:
    """Return a generator seeded from the report date and a stream name.

    ``zlib.crc32`` rather than ``hash`` because Python salts string hashes per
    process, which would break determinism across restarts.
    """
    day_key = report_date.year * 10_000 + report_date.month * 100 + report_date.day
    seed = (day_key * 1_000_003) ^ zlib.crc32(stream.encode("utf-8")) ^ config.MOCK_SEED_SALT
    return Random(seed)


# ---------------------------------------------------------------------------
# Calendar helpers
# ---------------------------------------------------------------------------


def _is_business_day(day: date) -> bool:
    """Weekday test only — market holidays are handled in the look-ahead."""
    return day.weekday() < 5


def _previous_business_day(day: date) -> date:
    cursor = day - timedelta(days=1)
    while not _is_business_day(cursor):
        cursor -= timedelta(days=1)
    return cursor


def _next_business_day(day: date) -> date:
    cursor = day + timedelta(days=1)
    while not _is_business_day(cursor):
        cursor += timedelta(days=1)
    return cursor


def _add_business_days(day: date, count: int) -> date:
    """Move ``count`` business days forward (or backward when negative)."""
    step = 1 if count >= 0 else -1
    cursor = day
    for _ in range(abs(count)):
        cursor = _next_business_day(cursor) if step > 0 else _previous_business_day(cursor)
    return cursor


def _business_days_ending(end: date, count: int) -> list[date]:
    """The ``count`` business days ending on (or just before) ``end``."""
    cursor = end if _is_business_day(end) else _previous_business_day(end)
    days = [cursor]
    while len(days) < count:
        cursor = _previous_business_day(cursor)
        days.append(cursor)
    return list(reversed(days))


def _last_business_day_of_month(year: int, month: int) -> date:
    last = date(year, month, calendar.monthrange(year, month)[1])
    return last if _is_business_day(last) else _previous_business_day(last)


def _month_end_before(day: date, months_back: int) -> date:
    """Month end ``months_back`` months before ``day``'s month.

    ``months_back=1`` is last month end; ``months_back=3`` is the month end
    three months back, which is roughly the LBMA vault publication lag.
    """
    year, month = day.year, day.month
    for _ in range(months_back):
        month -= 1
        if month == 0:
            month, year = 12, year - 1
    return date(year, month, calendar.monthrange(year, month)[1])


def _latest_cot_survey_date(report_date: date) -> date:
    """Most recent Tuesday whose Friday publication has already happened."""
    cursor = report_date
    while True:
        # Tuesday is weekday 1; the report publishes on the Friday three days later.
        if cursor.weekday() == 1 and cursor + timedelta(days=3) <= report_date:
            return cursor
        cursor -= timedelta(days=1)


_MONTH_CODE_TO_NUMBER = {code: n for n, code in enumerate(config.MONTH_CODE_NAMES, start=1)}


def _first_notice_day(year: int, month: int) -> date:
    """COMEX first notice day: last business day of the month before delivery."""
    prior_month, prior_year = (month - 1, year) if month > 1 else (12, year - 1)
    return _last_business_day_of_month(prior_year, prior_month)


def _last_trade_day(year: int, month: int) -> date:
    """Approximated as the third-to-last business day of the delivery month."""
    return _add_business_days(_last_business_day_of_month(year, month), -2)


@dataclass(frozen=True)
class _Contract:
    """One dated COMEX contract."""

    code: str
    delivery_year: int
    delivery_month: int
    first_notice_date: date
    last_trade_date: date


def _contract_ladder(metal_code: str, report_date: date) -> list[_Contract]:
    """Active contracts for a metal, in delivery order, still ahead of the date."""
    spec = config.COMEX_CONTRACTS[metal_code]
    ladder: list[_Contract] = []
    for year in (report_date.year, report_date.year + 1):
        for month_code in spec.active_months:
            month = _MONTH_CODE_TO_NUMBER[month_code]
            first_notice = _first_notice_day(year, month)
            if first_notice <= report_date:
                continue
            ladder.append(
                _Contract(
                    code=f"{spec.contract_code}{month_code}{year % 10}",
                    delivery_year=year,
                    delivery_month=month,
                    first_notice_date=first_notice,
                    last_trade_date=_last_trade_day(year, month),
                )
            )
    ladder.sort(key=lambda c: (c.delivery_year, c.delivery_month))
    return ladder


# ---------------------------------------------------------------------------
# Price path and derived statistics
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _MetalMarket:
    """Everything downstream sections need to stay consistent with the price."""

    metal: Metal
    anchor: config.PriceAnchor
    bars: list[PriceBar]
    closes: list[float]
    close: float
    prior_close: float
    change: float
    change_pct: float
    session_high: float
    session_low: float
    lbma_pm: float
    realised_vol_1m_pct: float
    implied_vol_1m_pct: float

    @property
    def decimals(self) -> int:
        return self.anchor.price_decimals


def _annualised_vol_pct(closes: list[float], window: int = 21) -> float:
    """Annualised realised volatility of the last ``window`` log returns."""
    sample = closes[-(window + 1) :]
    returns = [math.log(b / a) for a, b in zip(sample, sample[1:]) if a > 0]
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    return math.sqrt(variance) * math.sqrt(config.TRADING_DAYS_PER_YEAR) * 100.0


def _rsi_14(closes: list[float], period: int = 14) -> float:
    """Wilder's RSI over ``period`` sessions, 0-100."""
    deltas = [b - a for a, b in zip(closes, closes[1:])]
    if len(deltas) < period:
        return 50.0
    gains = [max(d, 0.0) for d in deltas]
    losses = [max(-d, 0.0) for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for gain, loss in zip(gains[period:], losses[period:]):
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _moving_average(closes: list[float], window: int) -> float:
    sample = closes[-window:]
    return sum(sample) / len(sample)


def _build_market(report_date: date, metal_code: str) -> _MetalMarket:
    """Fabricate one metal's session and the year of history behind it."""
    anchor = config.PRICE_ANCHORS[metal_code]
    rng = _rng(report_date, f"price:{metal_code}")
    sessions = config.PRICE_HISTORY_SESSIONS
    decimals = anchor.price_decimals

    daily_vol = anchor.daily_vol_pct / 100.0
    # Drift is expressed over the whole history (-15% to +25% across the year)
    # so the moving averages stay within sight of the current price.
    drift = rng.uniform(-0.15, 0.25) / sessions
    levels: list[float] = []
    level = 1.0
    for _ in range(sessions):
        level *= 1.0 + drift + rng.gauss(0.0, daily_vol)
        levels.append(level)

    # Rescale the walk so the final close lands inside the configured anchor.
    target_close = rng.uniform(anchor.low_usd_per_oz, anchor.high_usd_per_oz)
    scale = target_close / levels[-1]
    closes = [round(value * scale, decimals) for value in levels]

    session_dates = _business_days_ending(report_date, sessions)
    bars: list[PriceBar] = []
    previous_close = closes[0]
    for session_date, close in zip(session_dates, closes):
        open_price = round(previous_close * (1.0 + rng.gauss(0.0, daily_vol * 0.30)), decimals)
        high = round(
            max(open_price, close) * (1.0 + abs(rng.gauss(0.0, daily_vol * 0.45))), decimals
        )
        low = round(
            min(open_price, close) * (1.0 - abs(rng.gauss(0.0, daily_vol * 0.45))), decimals
        )
        bars.append(
            PriceBar(
                session_date=session_date,
                open_usd_per_oz=open_price,
                high_usd_per_oz=high,
                low_usd_per_oz=low,
                close_usd_per_oz=close,
            )
        )
        previous_close = close

    last_bar = bars[-1]
    close = closes[-1]
    prior_close = closes[-2]
    change = round(close - prior_close, decimals)
    change_pct = round((close / prior_close - 1.0) * 100.0, 2)

    # The auction prints inside the session range, close to the close.
    auction = close * (1.0 + rng.gauss(0.0, daily_vol * 0.25))
    auction = min(max(auction, last_bar.low_usd_per_oz), last_bar.high_usd_per_oz)

    realised = _annualised_vol_pct(closes)
    implied = max(5.0, anchor.implied_vol_1m_pct + rng.uniform(-2.0, 2.5))

    return _MetalMarket(
        metal=Metal(metal_code),
        anchor=anchor,
        bars=bars,
        closes=closes,
        close=close,
        prior_close=prior_close,
        change=change,
        change_pct=change_pct,
        session_high=last_bar.high_usd_per_oz,
        session_low=last_bar.low_usd_per_oz,
        lbma_pm=round(auction, decimals),
        realised_vol_1m_pct=round(realised, 1),
        implied_vol_1m_pct=round(implied, 1),
    )


# ---------------------------------------------------------------------------
# Fabricated free text
# ---------------------------------------------------------------------------

#: Candidate client axes per metal. Fabrication detail, not a market anchor,
#: so these live here rather than in config.py.
_AXIS_TEMPLATES: dict[str, tuple[str, ...]] = {
    "XAU": (
        "Central bank buying loco London on dips",
        "Asset manager switch out of ETF into allocated",
        "CTA short covering above the 50-day",
        "Producer forward selling into the PM auction",
        "Refiner offers around the fix",
        "Wholesale demand for kilobars into Asia",
        "Family office accumulation in the 3,300s",
    ),
    "XAG": (
        "Industrial hedging on the dip",
        "Solar fabricator forward buying",
        "Macro fund adding length via futures",
        "Refiner selling 1,000oz bars loco London",
        "Retail wholesale restocking after the run",
        "Spread trader selling gold/silver ratio",
    ),
    "XPT": (
        "Autocat fabricator forward cover",
        "South African producer hedging Q4 output",
        "Refiner lending metal into a tight lease market",
        "Asset manager building a long via ETF",
        "Jewellery demand from China at the lows",
    ),
    "XPD": (
        "Autocat substitution flow out of palladium",
        "Producer selling into strength",
        "Hedge fund covering shorts on supply headlines",
        "Industrial consumer buying the dip",
        "Refiner sponge offers loco Zurich",
    ),
}

#: Desk notes attached to high-importance calendar entries.
_EVENT_NOTES: tuple[str, ...] = (
    "Gold most exposed to a hot print.",
    "Watch the real yield reaction rather than the headline.",
    "Silver likely to amplify any gold move.",
    "Thin liquidity around the release; expect a wide range.",
    "PGMs largely insulated, but the ratio trade will move.",
)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


# ---------------------------------------------------------------------------
# The provider
# ---------------------------------------------------------------------------


class MockDataProvider:
    """Deterministic fabricated implementation of the ``DataProvider`` protocol.

    Instances cache the per-date market state so that the eight section calls
    that make up one report agree with each other and stay cheap to re-render.
    """

    def __init__(self) -> None:
        self._markets: dict[date, dict[str, _MetalMarket]] = {}

    # -- shared state ------------------------------------------------------

    def _market_state(self, report_date: date) -> dict[str, _MetalMarket]:
        if report_date not in self._markets:
            self._markets[report_date] = {
                metal_code: _build_market(report_date, metal_code)
                for metal_code in config.METALS
            }
        return self._markets[report_date]

    # -- section 0 ---------------------------------------------------------

    def get_header(self, report_date: date, author_name: str) -> ReportHeader:
        markets = self._market_state(report_date)
        generated_at = datetime.combine(
            report_date,
            time(hour=config.LONDON_CLOSE_HOUR, minute=config.LONDON_CLOSE_MINUTE),
            tzinfo=config.LONDON_TZ,
        )
        snapshot = [
            MetalSnapshot(
                metal=market.metal,
                close_usd_per_oz=market.close,
                prior_close_usd_per_oz=market.prior_close,
                change_usd_per_oz=market.change,
                change_pct=market.change_pct,
                session_high_usd_per_oz=market.session_high,
                session_low_usd_per_oz=market.session_low,
                lbma_pm_auction_usd_per_oz=market.lbma_pm,
                direction=Direction.from_change(market.change),
                price_decimals=market.decimals,
            )
            for market in markets.values()
        ]
        return ReportHeader(
            report_date=report_date,
            generated_at_london=generated_at,
            report_label=config.REPORT_LABEL,
            author_name=author_name,
            headline="",
            snapshot=snapshot,
        )

    # -- section 1 ---------------------------------------------------------

    def get_client_flows(self, report_date: date) -> ClientFlowsSection:
        markets = self._market_state(report_date)
        metals: list[MetalClientFlow] = []
        total_tickets = 0
        total_gross_usd = 0.0

        for metal_code, market in markets.items():
            rng = _rng(report_date, f"flows:{metal_code}")
            turnover_oz = config.DAILY_CLIENT_TURNOVER_OZ[metal_code] * rng.uniform(0.7, 1.4)
            ticket_size_oz = config.AVERAGE_TICKET_SIZE_OZ[metal_code]
            weights = config.CLIENT_SEGMENT_WEIGHTS[metal_code]

            # Clients lean with the move in the speculative segments and against
            # it in the hedging segments, so the flow story matches the price.
            lean = 0.30 if market.change_pct >= 0 else -0.30
            segment_bias = {
                "central_bank": 0.25,
                "producer_hedger": -1.10 * lean,
                "refiner": -0.80 * lean,
                "investment_asset_manager": 1.00 * lean,
                "industrial": -0.40 * lean,
                "hedge_fund_cta": 1.20 * lean,
                "retail_wholesale": 0.60 * lean,
            }

            rows: list[ClientSegmentFlow] = []
            gross_oz = 0.0
            for segment_code in config.CLIENT_SEGMENTS:
                weight = weights[segment_code]
                if weight <= 0.0:
                    continue  # segment does not trade this metal
                segment_gross_oz = turnover_oz * weight * rng.uniform(0.75, 1.25)
                net_ratio = _clamp(rng.gauss(segment_bias[segment_code], 0.35), -0.9, 0.9)
                net_oz = segment_gross_oz * net_ratio
                tickets = max(
                    1, round(segment_gross_oz / (ticket_size_oz * rng.uniform(0.7, 1.3)))
                )
                gross_oz += segment_gross_oz
                rows.append(
                    ClientSegmentFlow(
                        segment=ClientSegment(segment_code),
                        net_oz=round(net_oz, 1),
                        net_usd=round(net_oz * market.close, 2),
                        ticket_count=tickets,
                    )
                )

            net_oz = sum(row.net_oz for row in rows)
            tickets = sum(row.ticket_count for row in rows)
            axes = _rng(report_date, f"axes:{metal_code}").sample(
                _AXIS_TEMPLATES[metal_code], k=3
            )
            side = (
                TradeSide.BUY
                if net_oz > 0
                else TradeSide.SELL
                if net_oz < 0
                else TradeSide.FLAT
            )

            metals.append(
                MetalClientFlow(
                    metal=market.metal,
                    net_client_side=side,
                    net_client_oz=round(net_oz, 1),
                    net_client_usd=round(net_oz * market.close, 2),
                    gross_client_oz=round(gross_oz, 1),
                    segment_breakdown=rows,
                    top_axes=axes,
                    unallocated_balance_change_oz=round(rng.gauss(0.0, turnover_oz * 0.08), 1),
                    ticket_count=tickets,
                    average_ticket_size_oz=round(gross_oz / tickets, 1),
                    average_ticket_size_usd=round(gross_oz * market.close / tickets, 2),
                )
            )
            total_tickets += tickets
            total_gross_usd += gross_oz * market.close

        return ClientFlowsSection(
            metals=metals,
            total_ticket_count=total_tickets,
            total_gross_usd=round(total_gross_usd, 2),
        )

    # -- section 2 ---------------------------------------------------------

    def get_risk(self, report_date: date) -> RiskSection:
        markets = self._market_state(report_date)
        rng = _rng(report_date, "risk")
        low_usage, high_usage = config.POSITION_LIMIT_USAGE_RANGE

        # Notionals are drawn as a share of the delta limits so that limit
        # utilisation is a consequence of the book rather than a separate roll.
        pgm_usage = rng.uniform(low_usage, high_usage)
        pgm_split = rng.uniform(0.5, 0.72)
        notional_targets = {
            "XAU": config.RISK_LIMITS_USD["Gold delta notional"]
            * rng.uniform(low_usage, high_usage),
            "XAG": config.RISK_LIMITS_USD["Silver delta notional"]
            * rng.uniform(low_usage, high_usage),
            "XPT": config.RISK_LIMITS_USD["PGM delta notional"] * pgm_usage * pgm_split,
            "XPD": config.RISK_LIMITS_USD["PGM delta notional"] * pgm_usage * (1.0 - pgm_split),
        }
        vega_shares = {"XAU": 0.50, "XAG": 0.25, "XPT": 0.15, "XPD": 0.10}
        vega_limit = config.RISK_LIMITS_USD["Vega (per vol point)"]
        vega_usage = rng.uniform(low_usage, high_usage)

        positions: list[DeskPosition] = []
        greeks: list[OptionsGreeks] = []
        var_by_metal: list[float] = []

        for metal_code, market in markets.items():
            sign = 1.0 if rng.random() < 0.55 else -1.0
            usd_notional = notional_targets[metal_code] * sign
            delta_equivalent_oz = usd_notional / market.close
            options_delta_oz = delta_equivalent_oz * rng.uniform(-0.25, 0.25)
            position_oz = delta_equivalent_oz - options_delta_oz

            daily_vol = (market.implied_vol_1m_pct / 100.0) / math.sqrt(
                config.TRADING_DAYS_PER_YEAR
            )
            metal_var = abs(usd_notional) * daily_vol * config.VAR_Z_99
            var_by_metal.append(metal_var)

            positions.append(
                DeskPosition(
                    metal=market.metal,
                    position_oz=round(position_oz, 1),
                    delta_equivalent_oz=round(delta_equivalent_oz, 1),
                    usd_notional=round(usd_notional, 2),
                    var_1d_99_usd=round(metal_var, 2),
                )
            )

            vega = vega_limit * vega_shares[metal_code] * vega_usage * rng.choice((1.0, 1.0, -1.0))
            greeks.append(
                OptionsGreeks(
                    metal=market.metal,
                    delta_oz=round(options_delta_oz, 1),
                    gamma_oz_per_pct=round(
                        abs(delta_equivalent_oz) * rng.uniform(0.02, 0.08) * (1.0 if vega > 0 else -1.0),
                        1,
                    ),
                    vega_usd_per_vol_pt=round(vega, 2),
                    theta_usd_per_day=round(-vega * rng.uniform(0.02, 0.05), 2),
                )
            )

        # Diversified desk VaR: sum of squares plus correlated cross terms.
        cross = sum(
            2.0 * config.VAR_CROSS_METAL_CORRELATION * var_by_metal[i] * var_by_metal[j]
            for i in range(len(var_by_metal))
            for j in range(i + 1, len(var_by_metal))
        )
        desk_var = math.sqrt(sum(v * v for v in var_by_metal) + cross)

        spot = rng.gauss(0.0, 0.30 * desk_var)
        carry = rng.gauss(0.02 * desk_var, 0.05 * desk_var)
        volatility = rng.gauss(0.0, 0.15 * desk_var)
        client_flow = abs(rng.gauss(0.08 * desk_var, 0.04 * desk_var))
        other = rng.gauss(0.0, 0.03 * desk_var)
        daily_pnl = spot + carry + volatility + client_flow + other
        mtd_pnl = daily_pnl + rng.gauss(0.9 * desk_var, 3.5 * desk_var)
        ytd_pnl = mtd_pnl + rng.gauss(6.0 * desk_var, 9.0 * desk_var)

        notional_by_metal = {
            position.metal.value: abs(position.usd_notional) for position in positions
        }
        utilisation = {
            "Desk VaR (1d, 99%)": desk_var,
            "Gold delta notional": notional_by_metal["XAU"],
            "Silver delta notional": notional_by_metal["XAG"],
            "PGM delta notional": notional_by_metal["XPT"] + notional_by_metal["XPD"],
            "Vega (per vol point)": sum(abs(g.vega_usd_per_vol_pt) for g in greeks),
        }
        limits: list[LimitUtilisation] = []
        for limit_name, limit_usd in config.RISK_LIMITS_USD.items():
            used = utilisation[limit_name]
            pct = used / limit_usd * 100.0
            limits.append(
                LimitUtilisation(
                    limit_name=limit_name,
                    limit_usd=limit_usd,
                    utilisation_usd=round(used, 2),
                    utilisation_pct=round(pct, 1),
                    above_warning_threshold=pct >= config.LIMIT_WARNING_PCT,
                )
            )

        return RiskSection(
            positions=positions,
            daily_pnl_usd=round(daily_pnl, 2),
            mtd_pnl_usd=round(mtd_pnl, 2),
            ytd_pnl_usd=round(ytd_pnl, 2),
            pnl_attribution=PnlAttribution(
                spot_usd=round(spot, 2),
                carry_forward_usd=round(carry, 2),
                volatility_usd=round(volatility, 2),
                client_flow_usd=round(client_flow, 2),
                other_usd=round(other, 2),
                total_usd=round(daily_pnl, 2),
            ),
            desk_var_1d_99_usd=round(desk_var, 2),
            greeks=greeks,
            limits=limits,
            any_limit_flagged=any(limit.above_warning_threshold for limit in limits),
        )

    # -- section 3 ---------------------------------------------------------

    def _technical_levels(
        self, market: _MetalMarket, ma_50: float, ma_100: float, ma_200: float
    ) -> tuple[list[TechnicalLevel], list[TechnicalLevel]]:
        close = market.close
        decimals = market.decimals
        highs = [bar.high_usd_per_oz for bar in market.bars]
        lows = [bar.low_usd_per_oz for bar in market.bars]
        step = config.ROUND_LEVEL_STEP_USD_PER_OZ[market.metal.value]

        candidates: list[tuple[str, float]] = [
            ("20-session high", max(highs[-20:])),
            ("60-session high", max(highs[-60:])),
            ("52-week high", max(highs)),
            ("20-session low", min(lows[-20:])),
            ("60-session low", min(lows[-60:])),
            ("52-week low", min(lows)),
            ("50-day moving average", ma_50),
            ("100-day moving average", ma_100),
            ("200-day moving average", ma_200),
            ("round number", math.ceil(close / step) * step),
            ("round number", math.floor(close / step) * step),
        ]

        def build(above: bool) -> list[TechnicalLevel]:
            picked: list[TechnicalLevel] = []
            side = [
                (label, price)
                for label, price in candidates
                if (price > close * 1.0005 if above else price < close * 0.9995)
            ]
            side.sort(key=lambda item: abs(item[1] - close))
            for label, price in side:
                if any(abs(price - kept.price_usd_per_oz) <= close * 0.0025 for kept in picked):
                    continue  # same level under a different name
                picked.append(
                    TechnicalLevel(
                        level_type=LevelType.RESISTANCE if above else LevelType.SUPPORT,
                        price_usd_per_oz=round(price, decimals),
                        label=label,
                        distance_pct=round((price - close) / close * 100.0, 2),
                    )
                )
                if len(picked) == 3:
                    break
            return picked

        return build(above=False), build(above=True)

    def get_technicals(self, report_date: date) -> TechnicalsSection:
        markets = self._market_state(report_date)
        blocks: list[MetalTechnicals] = []

        for market in markets.values():
            ma_50 = _moving_average(market.closes, 50)
            ma_100 = _moving_average(market.closes, 100)
            ma_200 = _moving_average(market.closes, 200)
            supports, resistances = self._technical_levels(market, ma_50, ma_100, ma_200)

            if ma_50 > ma_200 and market.close > ma_50:
                trend = TrendLabel.UPTREND
            elif ma_50 < ma_200 and market.close < ma_50:
                trend = TrendLabel.DOWNTREND
            else:
                trend = TrendLabel.RANGE

            nearest = min(
                supports + resistances,
                key=lambda level: abs(level.distance_pct),
            )

            blocks.append(
                MetalTechnicals(
                    metal=market.metal,
                    close_usd_per_oz=market.close,
                    ma_50_usd_per_oz=round(ma_50, market.decimals),
                    ma_100_usd_per_oz=round(ma_100, market.decimals),
                    ma_200_usd_per_oz=round(ma_200, market.decimals),
                    rsi_14=round(_rsi_14(market.closes), 1),
                    support_levels=supports,
                    resistance_levels=resistances,
                    trend_label=trend,
                    nearest_level_type=nearest.level_type,
                    nearest_level_usd_per_oz=nearest.price_usd_per_oz,
                    distance_to_nearest_level_pct=round(abs(nearest.distance_pct), 2),
                    realised_vol_1m_pct=market.realised_vol_1m_pct,
                    implied_vol_1m_pct=market.implied_vol_1m_pct,
                    vol_spread_pct=round(
                        market.implied_vol_1m_pct - market.realised_vol_1m_pct, 1
                    ),
                    price_history=market.bars,
                )
            )

        return TechnicalsSection(
            metals=blocks,
            default_chart_metal=Metal.XAU,
            history_session_count=config.PRICE_HISTORY_SESSIONS,
        )

    # -- section 4 ---------------------------------------------------------

    def get_etf(self, report_date: date) -> EtfSection:
        markets = self._market_state(report_date)
        as_of = _previous_business_day(report_date)
        funds: list[EtfFundFlow] = []

        specs = [
            (spec.ticker, spec.name, spec.metal, spec.holdings_tonnes)
            for spec in config.ETF_FUNDS
        ] + [
            (
                config.ETF_OTHER_TICKER,
                f"{config.ETF_OTHER_NAME} — {Metal(metal_code).display_name}",
                metal_code,
                tonnes,
            )
            for metal_code, tonnes in config.ETF_OTHER_HOLDINGS_TONNES.items()
        ]

        for ticker, fund_name, metal_code, anchor_tonnes in specs:
            market = markets[metal_code]
            rng = _rng(report_date, f"etf:{ticker}:{metal_code}")
            holdings = anchor_tonnes * rng.uniform(0.96, 1.05)
            daily_change = holdings * rng.gauss(0.0, 0.0035)
            # Cumulative windows nest: each period contains the one before it.
            wtd = daily_change + holdings * rng.gauss(0.0, 0.006)
            mtd = wtd + holdings * rng.gauss(0.004, 0.018)
            ytd = mtd + holdings * rng.gauss(0.030, 0.100)
            oz_value = config.tonnes_to_oz(1.0) * market.close

            funds.append(
                EtfFundFlow(
                    ticker=ticker,
                    fund_name=fund_name,
                    metal=market.metal,
                    holdings_tonnes=round(holdings, 2),
                    daily_change_tonnes=round(daily_change, 2),
                    daily_change_usd=round(daily_change * oz_value, 2),
                    aum_usd=round(holdings * oz_value, 2),
                    wtd_flow_tonnes=round(wtd, 2),
                    mtd_flow_tonnes=round(mtd, 2),
                    ytd_flow_tonnes=round(ytd, 2),
                    ytd_flow_usd=round(ytd * oz_value, 2),
                )
            )

        aggregates: list[EtfMetalAggregate] = []
        for metal_code in config.METALS:
            rows = [fund for fund in funds if fund.metal.value == metal_code]
            aggregates.append(
                EtfMetalAggregate(
                    metal=Metal(metal_code),
                    holdings_tonnes=round(sum(r.holdings_tonnes for r in rows), 2),
                    daily_change_tonnes=round(sum(r.daily_change_tonnes for r in rows), 2),
                    daily_change_usd=round(sum(r.daily_change_usd for r in rows), 2),
                    wtd_flow_tonnes=round(sum(r.wtd_flow_tonnes for r in rows), 2),
                    mtd_flow_tonnes=round(sum(r.mtd_flow_tonnes for r in rows), 2),
                    ytd_flow_tonnes=round(sum(r.ytd_flow_tonnes for r in rows), 2),
                    aum_usd=round(sum(r.aum_usd for r in rows), 2),
                )
            )

        return EtfSection(
            as_of_date=as_of,
            reporting_lag_note=(
                "Issuer holdings are reported T+1: the figures below are effective "
                f"{as_of:%d %b %Y}, published on the morning of {report_date:%d %b %Y}."
            ),
            funds=funds,
            metal_aggregates=aggregates,
        )

    # -- section 5 ---------------------------------------------------------

    def get_positioning(self, report_date: date) -> PositioningSection:
        markets = self._market_state(report_date)
        cot_survey_date = _latest_cot_survey_date(report_date)
        contracts: list[ComexContractActivity] = []
        cot: list[CotManagedMoney] = []
        efp: list[EfpLevel] = []

        for metal_code, market in markets.items():
            spec = config.COMEX_CONTRACTS[metal_code]
            rng = _rng(report_date, f"oi:{metal_code}")
            ladder = _contract_ladder(metal_code, report_date)
            front, next_active = ladder[0], ladder[1]

            open_interest = int(spec.open_interest_lots * rng.uniform(0.90, 1.10))
            volume = int(spec.session_volume_lots * rng.uniform(0.60, 1.60))
            volume_20d = int(spec.session_volume_lots * rng.uniform(0.92, 1.08))

            contracts.append(
                ComexContractActivity(
                    contract_code=spec.contract_code,
                    metal=market.metal,
                    contract_size_oz=spec.contract_size_oz,
                    open_interest_lots=open_interest,
                    open_interest_change_lots=int(open_interest * rng.gauss(0.0, 0.012)),
                    session_volume_lots=volume,
                    volume_20d_average_lots=volume_20d,
                    volume_vs_20d_average_pct=round((volume / volume_20d - 1.0) * 100.0, 1),
                    front_month_code=front.code,
                    front_month_expiry_date=front.last_trade_date,
                    next_active_month_code=next_active.code,
                    next_active_expiry_date=next_active.last_trade_date,
                )
            )

            cot_rng = _rng(report_date, f"cot:{metal_code}")
            long_lots = int(open_interest * cot_rng.uniform(0.22, 0.34))
            short_lots = int(open_interest * cot_rng.uniform(0.08, 0.22))
            net_lots = long_lots - short_lots
            cot.append(
                CotManagedMoney(
                    metal=market.metal,
                    report_date=cot_survey_date,
                    published_date=cot_survey_date + timedelta(days=3),
                    managed_money_long_lots=long_lots,
                    managed_money_short_lots=short_lots,
                    managed_money_net_lots=net_lots,
                    net_change_wow_lots=int(open_interest * cot_rng.gauss(0.0, 0.02)),
                    net_oz=round(net_lots * spec.contract_size_oz, 1),
                )
            )

            efp_rng = _rng(report_date, f"efp:{metal_code}")
            base = spec.efp_usd_per_oz
            decimals = max(market.decimals, 2)
            range_low = round(base * 0.45, decimals)
            range_high = round(base * 1.85, decimals)
            # EFP normally sits inside its trailing range; occasionally it
            # dislocates far enough to raise the flag.
            if efp_rng.random() < 0.07:
                multiple = efp_rng.choice((efp_rng.uniform(1.90, 2.60), efp_rng.uniform(0.15, 0.42)))
            else:
                multiple = efp_rng.uniform(0.50, 1.78)
            level = round(base * multiple, decimals)
            efp.append(
                EfpLevel(
                    metal=market.metal,
                    efp_usd_per_oz=level,
                    recent_range_low_usd_per_oz=range_low,
                    recent_range_high_usd_per_oz=range_high,
                    outside_recent_range=level < range_low or level > range_high,
                )
            )

        return PositioningSection(
            contracts=contracts,
            cot=cot,
            cot_report_date=cot_survey_date,
            cot_lag_days=(report_date - cot_survey_date).days,
            efp=efp,
            any_efp_flagged=any(level.outside_recent_range for level in efp),
        )

    # -- section 6 ---------------------------------------------------------

    def get_physical(self, report_date: date) -> PhysicalSection:
        markets = self._market_state(report_date)
        comex: list[ComexStocks] = []
        vaults: list[LbmaVaultHolding] = []
        sge: list[SgeActivity] = []
        premiums: list[LocoPremium] = []
        lease_rates: list[LeaseRate] = []
        vault_month_end = _month_end_before(report_date, months_back=3)

        for metal_code, market in markets.items():
            rng = _rng(report_date, f"physical:{metal_code}")
            registered_anchor, eligible_anchor = config.COMEX_STOCK_ANCHORS_OZ[metal_code]
            registered = registered_anchor * rng.uniform(0.90, 1.10)
            eligible = eligible_anchor * rng.uniform(0.90, 1.10)
            registered_change = registered * rng.gauss(0.0, 0.006)
            eligible_change = eligible * rng.gauss(0.0, 0.004)
            comex.append(
                ComexStocks(
                    metal=market.metal,
                    registered_oz=round(registered, 0),
                    eligible_oz=round(eligible, 0),
                    total_oz=round(registered + eligible, 0),
                    registered_change_oz=round(registered_change, 0),
                    eligible_change_oz=round(eligible_change, 0),
                    total_change_oz=round(registered_change + eligible_change, 0),
                )
            )

            vault_holdings = config.LBMA_VAULT_ANCHOR_TONNES[metal_code] * rng.uniform(0.97, 1.03)
            month_change = vault_holdings * rng.gauss(0.0, 0.012)
            vaults.append(
                LbmaVaultHolding(
                    metal=market.metal,
                    holdings_tonnes=round(vault_holdings, 1),
                    month_change_tonnes=round(month_change, 1),
                    month_change_pct=round(
                        month_change / (vault_holdings - month_change) * 100.0, 2
                    ),
                    as_of_month_end=vault_month_end,
                )
            )

            if metal_code in config.SGE_WITHDRAWAL_ANCHOR_TONNES:
                premium = config.SGE_PREMIUM_ANCHOR_USD_PER_OZ[metal_code] * rng.uniform(-0.4, 2.0)
                sge.append(
                    SgeActivity(
                        metal=market.metal,
                        withdrawals_tonnes=round(
                            config.SGE_WITHDRAWAL_ANCHOR_TONNES[metal_code]
                            * rng.uniform(0.65, 1.45),
                            1,
                        ),
                        withdrawals_period_days=config.SGE_WITHDRAWAL_PERIOD_DAYS,
                        premium_usd_per_oz=round(premium, 2),
                        premium_pct=round(premium / market.close * 100.0, 2),
                    )
                )

            rate_1m, rate_3m = config.LEASE_RATE_ANCHORS_PCT[metal_code]
            lease_rates.append(
                LeaseRate(
                    metal=market.metal,
                    lease_rate_1m_pct=round(rate_1m * rng.uniform(0.6, 1.7), 2),
                    lease_rate_3m_pct=round(rate_3m * rng.uniform(0.7, 1.5), 2),
                )
            )

        for location in config.PREMIUM_LOCATIONS:
            for metal_code, market in markets.items():
                rng = _rng(report_date, f"premium:{location}:{metal_code}")
                anchor = config.LOCO_PREMIUM_ANCHORS_USD_PER_OZ[location][metal_code]
                premiums.append(
                    LocoPremium(
                        location=location,
                        metal=market.metal,
                        premium_usd_per_oz=round(anchor * rng.uniform(-0.3, 2.1), 2),
                    )
                )

        return PhysicalSection(
            comex_stocks=comex,
            lbma_vault_holdings=vaults,
            lbma_monthly_note=(
                "LBMA publishes London vault holdings monthly and in arrears; "
                f"the figures below are as at {vault_month_end:%d %b %Y}."
            ),
            sge=sge,
            loco_premiums=premiums,
            lease_rates=lease_rates,
        )

    # -- section 7 ---------------------------------------------------------

    def _calendar_events(
        self, report_date: date, day_range: list[date], count: int, offset: int
    ) -> list[CalendarEvent]:
        """Draw ``count`` distinct calendar entries across ``day_range``."""
        rng = _rng(report_date, f"calendar:{offset}")
        templates = list(config.CALENDAR_TEMPLATES)
        rng.shuffle(templates)
        pool = templates[offset:] + templates[:offset]

        events: list[CalendarEvent] = []
        central_bank_days: set[date] = set()
        for name, region, event_time, importance, consensus, previous in pool:
            if len(events) == count:
                break
            event_day = day_range[len(events) % len(day_range)]
            is_central_bank = name in config.CENTRAL_BANK_EVENT_NAMES
            if is_central_bank and event_day in central_bank_days:
                continue  # one policy event a day is plenty
            if is_central_bank:
                central_bank_days.add(event_day)
            note = (
                rng.choice(_EVENT_NOTES)
                if importance == EventImportance.HIGH.value and rng.random() < 0.7
                else None
            )
            events.append(
                CalendarEvent(
                    event_date=event_day,
                    event_time_london=event_time,
                    category=(
                        EventCategory.CENTRAL_BANK
                        if is_central_bank
                        else EventCategory.ECONOMIC_RELEASE
                    ),
                    region=region,
                    event_name=name,
                    consensus=consensus,
                    previous=previous,
                    importance=EventImportance(importance),
                    note=note,
                )
            )
        return events

    def get_look_ahead(self, report_date: date) -> LookAheadSection:
        next_session = _next_business_day(report_date)
        week_start = _add_business_days(next_session, 1)
        week_end = _add_business_days(next_session, 5)
        week_days = _business_days_ending(week_end, 5)
        rng = _rng(report_date, "lookahead")

        next_session_events = self._calendar_events(
            report_date, [next_session], rng.randint(2, 4), offset=0
        )
        next_week_events = self._calendar_events(
            report_date, week_days, rng.randint(5, 8), offset=6
        )

        # LBMA auctions run every session; list the next one for each auctioned metal.
        for metal_code in ("XAU", "XAG"):
            times = config.LBMA_AUCTION_TIMES_LONDON[metal_code]
            next_session_events.append(
                CalendarEvent(
                    event_date=next_session,
                    event_time_london=times[0],
                    category=EventCategory.LBMA_AUCTION,
                    region="UK",
                    event_name=(
                        f"LBMA {Metal(metal_code).display_name.lower()} auction "
                        f"({', '.join(times)} London)"
                    ),
                    consensus=None,
                    previous=None,
                    importance=EventImportance.LOW,
                    note=None,
                )
            )

        roll_windows: list[ContractRollWindow] = []
        for metal_code in config.METALS:
            front = _contract_ladder(metal_code, report_date)[0]
            roll_windows.append(
                ContractRollWindow(
                    metal=Metal(metal_code),
                    contract_code=front.code,
                    first_notice_date=front.first_notice_date,
                    last_trade_date=front.last_trade_date,
                    roll_window_start_date=_add_business_days(
                        front.first_notice_date, -config.ROLL_WINDOW_BUSINESS_DAYS
                    ),
                    roll_window_end_date=_add_business_days(front.first_notice_date, -1),
                )
            )

            # Surface notice days, expiries and roll starts that fall in the window.
            for event_date, category, label in (
                (front.first_notice_date, EventCategory.COMEX_FIRST_NOTICE, "first notice day"),
                (front.last_trade_date, EventCategory.CONTRACT_EXPIRY, "last trading day"),
                (
                    _add_business_days(
                        front.first_notice_date, -config.ROLL_WINDOW_BUSINESS_DAYS
                    ),
                    EventCategory.ROLL_WINDOW,
                    "roll window opens",
                ),
            ):
                event = CalendarEvent(
                    event_date=event_date,
                    event_time_london=None,
                    category=category,
                    region="US",
                    event_name=f"COMEX {front.code} {label}",
                    consensus=None,
                    previous=None,
                    importance=EventImportance.MEDIUM,
                    note=None,
                )
                if event_date == next_session:
                    next_session_events.append(event)
                elif week_start <= event_date <= week_end:
                    next_week_events.append(event)

        holidays: list[CalendarEvent] = []
        horizon = report_date + timedelta(days=config.HOLIDAY_LOOKAHEAD_DAYS)
        for month, day, region, name in config.MARKET_HOLIDAYS:
            for year in (report_date.year, report_date.year + 1):
                try:
                    holiday_date = date(year, month, day)
                except ValueError:  # 29 February in a non-leap year
                    continue
                if report_date < holiday_date <= horizon:
                    holidays.append(
                        CalendarEvent(
                            event_date=holiday_date,
                            event_time_london=None,
                            category=EventCategory.HOLIDAY,
                            region=region,
                            event_name=f"{name} — reduced liquidity",
                            consensus=None,
                            previous=None,
                            importance=EventImportance.MEDIUM,
                            note=None,
                        )
                    )

        def sort_key(event: CalendarEvent) -> tuple[date, str]:
            return (event.event_date, event.event_time_london or "00:00")

        return LookAheadSection(
            next_session_date=next_session,
            next_session_events=sorted(next_session_events, key=sort_key),
            next_week_start_date=week_start,
            next_week_end_date=week_end,
            next_week_events=sorted(next_week_events, key=sort_key),
            roll_windows=roll_windows,
            holidays=sorted(holidays, key=sort_key),
        )
