"""Pydantic models for the end-of-day precious metals report.

**This module is the data contract.** The Streamlit app, the mock provider, the
email renderer and the exported JSON Schema all agree on these shapes, and the
Rust implementation is expected to mirror them field for field.

Conventions — applied without exception
---------------------------------------
* Field names are ``snake_case`` and carry their unit as a suffix:

  =====================  ==========================================
  suffix                 meaning
  =====================  ==========================================
  ``_oz``                troy ounces (1 oz = 31.1035 g)
  ``_tonnes``            metric tonnes (1 t = 32,150.7 oz)
  ``_usd``               United States dollars
  ``_usd_per_oz``        United States dollars per troy ounce
  ``_pct``               percent, expressed as ``12.5`` for 12.5%
  ``_bp``                basis points, expressed as ``25.0`` for 0.25%
  ``_lots``              exchange contracts (see ``contract_size_oz``)
  ``_count``             an integer tally
  ``_date`` / ``_at``    calendar date / instant
  =====================  ==========================================

* **Signed quantities.** Anything that can point two ways is signed, and the
  sign convention is stated in the field description. Desk positions are
  positive when long. Client flow is positive when the *client* buys (the desk
  sells). P&L is positive when the desk makes money. Inventory and holdings
  changes are positive when metal arrives.
* **No ambiguous floats.** Every float names its unit; percentages are never
  fractions; currency is never scaled ("in millions" does not appear).
* **Dates are London dates**, instants are timezone-aware London time.
* Enumerations are string enums so they deserialise as tagged strings rather
  than integers.
* ``extra="forbid"`` everywhere: an unexpected field is a contract breach and
  should fail loudly on both sides of the port.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class Metal(str, Enum):
    """Metals in scope, identified by their ISO 4217 commodity code."""

    XAU = "XAU"
    XAG = "XAG"
    XPT = "XPT"
    XPD = "XPD"

    @property
    def display_name(self) -> str:
        return {"XAU": "Gold", "XAG": "Silver", "XPT": "Platinum", "XPD": "Palladium"}[
            self.value
        ]


class Direction(str, Enum):
    """Direction of a change, for the coloured up/down indicator."""

    UP = "up"
    DOWN = "down"
    FLAT = "flat"

    @classmethod
    def from_change(cls, change: float, epsilon: float = 1e-9) -> "Direction":
        if change > epsilon:
            return cls.UP
        if change < -epsilon:
            return cls.DOWN
        return cls.FLAT


class TradeSide(str, Enum):
    """Side of a net flow, from the client's perspective."""

    BUY = "buy"
    SELL = "sell"
    FLAT = "flat"


class ClientSegment(str, Enum):
    """Client taxonomy used for the flow breakdown."""

    CENTRAL_BANK = "central_bank"
    PRODUCER_HEDGER = "producer_hedger"
    REFINER = "refiner"
    INVESTMENT_ASSET_MANAGER = "investment_asset_manager"
    INDUSTRIAL = "industrial"
    HEDGE_FUND_CTA = "hedge_fund_cta"
    RETAIL_WHOLESALE = "retail_wholesale"

    @property
    def display_name(self) -> str:
        return {
            "central_bank": "Central bank",
            "producer_hedger": "Producer / hedger",
            "refiner": "Refiner",
            "investment_asset_manager": "Investment / asset manager",
            "industrial": "Industrial",
            "hedge_fund_cta": "Hedge fund / CTA",
            "retail_wholesale": "Retail / wholesale",
        }[self.value]


class TrendLabel(str, Enum):
    """Analyst-facing trend classification from the technical screen."""

    UPTREND = "uptrend"
    RANGE = "range"
    DOWNTREND = "downtrend"


class LevelType(str, Enum):
    """Whether a technical level sits below (support) or above (resistance)."""

    SUPPORT = "support"
    RESISTANCE = "resistance"


class EventCategory(str, Enum):
    """Kind of calendar entry in the look-ahead section."""

    ECONOMIC_RELEASE = "economic_release"
    CENTRAL_BANK = "central_bank"
    COMEX_FIRST_NOTICE = "comex_first_notice"
    CONTRACT_EXPIRY = "contract_expiry"
    ROLL_WINDOW = "roll_window"
    LBMA_AUCTION = "lbma_auction"
    HOLIDAY = "holiday"


class EventImportance(str, Enum):
    """Desk's own ranking of how much an event is likely to matter."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SectionKey(str, Enum):
    """Stable keys for the commentary boxes and the email section order."""

    MARKET_OVERVIEW = "market_overview"
    CLIENT_FLOWS = "client_flows"
    RISK = "risk"
    TECHNICALS = "technicals"
    ETF_FLOWS = "etf_flows"
    POSITIONING = "positioning"
    PHYSICAL = "physical"
    LOOK_AHEAD = "look_ahead"


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class ReportModel(BaseModel):
    """Base class fixing serialisation behaviour for the whole contract."""

    model_config = ConfigDict(extra="forbid", use_enum_values=False)


# ---------------------------------------------------------------------------
# Section 0 — header and snapshot strip
# ---------------------------------------------------------------------------


class MetalSnapshot(ReportModel):
    """One metal's line in the header snapshot strip.

    Prices are spot loco London in USD per troy ounce unless stated otherwise.
    """

    metal: Metal
    close_usd_per_oz: float = Field(description="Spot close at the London close.")
    prior_close_usd_per_oz: float = Field(
        description="Previous session's spot close, the comparison basis."
    )
    change_usd_per_oz: float = Field(
        description="close_usd_per_oz minus prior_close_usd_per_oz; signed."
    )
    change_pct: float = Field(
        description="Session change in percent of prior close; signed, 1.25 = +1.25%."
    )
    session_high_usd_per_oz: float = Field(description="Highest spot print of the session.")
    session_low_usd_per_oz: float = Field(description="Lowest spot print of the session.")
    lbma_pm_auction_usd_per_oz: float = Field(
        description=(
            "LBMA PM auction price for the session. For silver, which has a "
            "single daily auction, the noon auction price is reported here."
        )
    )
    direction: Direction = Field(
        description="Sign of change_usd_per_oz, driving the coloured indicator."
    )
    price_decimals: int = Field(
        ge=0,
        le=4,
        description="Decimal places this instrument is quoted to, for display consistency.",
    )


class ReportHeader(ReportModel):
    """Report identity plus the snapshot strip that opens the email."""

    report_date: date = Field(description="London trading date the report covers.")
    generated_at_london: datetime = Field(
        description="Timezone-aware instant the report was generated, Europe/London."
    )
    report_label: str = Field(
        description='Fixed label, e.g. "EOD — London close", shown beside the date.'
    )
    author_name: str = Field(description="Analyst publishing the report; free text.")
    headline: str = Field(
        default="",
        description="One-line headline typed by the analyst; empty is omitted from the email.",
    )
    snapshot: list[MetalSnapshot] = Field(
        description="One entry per metal in scope, in report order."
    )


# ---------------------------------------------------------------------------
# Section 1 — client flows
# ---------------------------------------------------------------------------


class ClientSegmentFlow(ReportModel):
    """Net client flow for one metal within one client segment."""

    segment: ClientSegment
    net_oz: float = Field(
        description="Net troy ounces; positive when the segment bought (desk sold)."
    )
    net_usd: float = Field(
        description="Net USD notional of the same flow; sign matches net_oz."
    )
    ticket_count: int = Field(ge=0, description="Tickets booked for this segment.")


class MetalClientFlow(ReportModel):
    """Client activity in one metal across the session."""

    metal: Metal
    net_client_side: TradeSide = Field(
        description="Direction of the aggregate client flow: buy, sell or flat."
    )
    net_client_oz: float = Field(
        description="Net troy ounces; positive when clients bought on balance."
    )
    net_client_usd: float = Field(
        description="Net USD notional of client flow; sign matches net_client_oz."
    )
    gross_client_oz: float = Field(
        ge=0, description="Sum of absolute client volume in troy ounces (two-way turnover)."
    )
    segment_breakdown: list[ClientSegmentFlow] = Field(
        description="Net flow per client segment; sums to net_client_oz / net_client_usd."
    )
    top_axes: list[str] = Field(
        description="Up to three short free-text axes, most significant first.",
        max_length=3,
    )
    unallocated_balance_change_oz: float = Field(
        description=(
            "Change in client unallocated (loco London) account balances in troy "
            "ounces; positive when client metal holdings with the desk increased."
        )
    )
    ticket_count: int = Field(ge=0, description="Total tickets in this metal.")
    average_ticket_size_oz: float = Field(
        ge=0, description="Gross ounces divided by ticket_count."
    )
    average_ticket_size_usd: float = Field(
        ge=0, description="Gross USD notional divided by ticket_count."
    )


class ClientFlowsSection(ReportModel):
    """Section 1. Desk-facing client flow, net of internal transfers."""

    metals: list[MetalClientFlow]
    total_ticket_count: int = Field(ge=0, description="Tickets across all metals.")
    total_gross_usd: float = Field(
        ge=0, description="Gross USD notional traded with clients across all metals."
    )


# ---------------------------------------------------------------------------
# Section 2 — risk
# ---------------------------------------------------------------------------


class DeskPosition(ReportModel):
    """The desk's end-of-session position in one metal."""

    metal: Metal
    position_oz: float = Field(
        description="Outright position in troy ounces; positive long, negative short."
    )
    delta_equivalent_oz: float = Field(
        description=(
            "Position including options delta, in troy ounces; positive long. "
            "Differs from position_oz by the options book's delta."
        )
    )
    usd_notional: float = Field(
        description="Delta-equivalent notional in USD; sign matches delta_equivalent_oz."
    )
    var_1d_99_usd: float = Field(
        ge=0, description="Standalone 1-day 99% VaR for this metal, in USD (positive loss)."
    )


class PnlAttribution(ReportModel):
    """Daily P&L split by driver. Components sum to total_usd."""

    spot_usd: float = Field(description="P&L from outright spot exposure.")
    carry_forward_usd: float = Field(
        description="P&L from forwards, leases and financing (carry)."
    )
    volatility_usd: float = Field(description="P&L from the options book's vol exposure.")
    client_flow_usd: float = Field(description="P&L captured on client spread / franchise.")
    other_usd: float = Field(description="Residual: fees, funding adjustments, rounding.")
    total_usd: float = Field(description="Sum of the five components; the day's P&L.")


class OptionsGreeks(ReportModel):
    """Options book greeks for one metal, expressed per-metal not per-strike."""

    metal: Metal
    delta_oz: float = Field(
        description="Options delta in troy ounces; positive long."
    )
    gamma_oz_per_pct: float = Field(
        description="Change in delta (troy ounces) for a +1% move in spot."
    )
    vega_usd_per_vol_pt: float = Field(
        description="P&L in USD for a +1 volatility point move in implied vol."
    )
    theta_usd_per_day: float = Field(
        description="Expected P&L in USD from one calendar day of time decay; usually negative when long options."
    )


class LimitUtilisation(ReportModel):
    """Utilisation of one desk risk limit."""

    limit_name: str = Field(description="Limit as named in the desk mandate.")
    limit_usd: float = Field(gt=0, description="Approved limit in USD.")
    utilisation_usd: float = Field(
        ge=0, description="Current usage in USD (absolute exposure against the limit)."
    )
    utilisation_pct: float = Field(
        ge=0, description="utilisation_usd as a percent of limit_usd; 82.5 = 82.5%."
    )
    above_warning_threshold: bool = Field(
        description="True when utilisation_pct is at or above the configured warning level (80%)."
    )


class RiskSection(ReportModel):
    """Section 2. Position, P&L, VaR, greeks and limit usage."""

    positions: list[DeskPosition]
    daily_pnl_usd: float = Field(description="Session P&L across the desk; positive is profit.")
    mtd_pnl_usd: float = Field(description="Month-to-date P&L across the desk.")
    ytd_pnl_usd: float = Field(description="Year-to-date P&L across the desk.")
    pnl_attribution: PnlAttribution
    desk_var_1d_99_usd: float = Field(
        ge=0,
        description=(
            "Diversified desk-level 1-day 99% VaR in USD (positive loss). Lower "
            "than the sum of per-metal VaRs because of correlation benefit."
        ),
    )
    greeks: list[OptionsGreeks]
    limits: list[LimitUtilisation]
    any_limit_flagged: bool = Field(
        description="True when at least one limit is at or above the warning threshold."
    )


# ---------------------------------------------------------------------------
# Section 3 — technicals
# ---------------------------------------------------------------------------


class PriceBar(ReportModel):
    """One daily OHLC bar of spot history, USD per troy ounce."""

    session_date: date
    open_usd_per_oz: float
    high_usd_per_oz: float
    low_usd_per_oz: float
    close_usd_per_oz: float


class TechnicalLevel(ReportModel):
    """A single support or resistance level."""

    level_type: LevelType
    price_usd_per_oz: float
    label: str = Field(
        description='Short human label, e.g. "prior range low", "38.2% retracement".'
    )
    distance_pct: float = Field(
        description=(
            "Signed distance from the current close to this level, in percent of "
            "the close; positive when the level is above the market."
        )
    )


class MetalTechnicals(ReportModel):
    """Technical picture for one metal at the London close."""

    metal: Metal
    close_usd_per_oz: float = Field(description="Close the technicals are measured against.")
    ma_50_usd_per_oz: float = Field(description="50-session simple moving average of closes.")
    ma_100_usd_per_oz: float = Field(description="100-session simple moving average of closes.")
    ma_200_usd_per_oz: float = Field(description="200-session simple moving average of closes.")
    rsi_14: float = Field(ge=0, le=100, description="14-session Wilder RSI, 0-100.")
    support_levels: list[TechnicalLevel] = Field(
        description="Key supports, nearest to the market first."
    )
    resistance_levels: list[TechnicalLevel] = Field(
        description="Key resistances, nearest to the market first."
    )
    trend_label: TrendLabel
    nearest_level_type: LevelType = Field(
        description="Whether the nearest level of any kind is support or resistance."
    )
    nearest_level_usd_per_oz: float = Field(description="Price of that nearest level.")
    distance_to_nearest_level_pct: float = Field(
        description="Absolute distance from close to the nearest level, in percent."
    )
    realised_vol_1m_pct: float = Field(
        ge=0,
        description="Annualised realised volatility over the last 21 sessions, in percent.",
    )
    implied_vol_1m_pct: float = Field(
        ge=0, description="1-month at-the-money implied volatility, in percent."
    )
    vol_spread_pct: float = Field(
        description="implied_vol_1m_pct minus realised_vol_1m_pct, in volatility points."
    )
    price_history: list[PriceBar] = Field(
        description=(
            "Daily bars ending on the report date, oldest first. Long enough to "
            "draw the 200-day moving average."
        )
    )


class TechnicalsSection(ReportModel):
    """Section 3. One technical block per metal plus charting defaults.

    The app charts a single analyst-selected metal rather than four charts, so
    the section carries a default selection.
    """

    metals: list[MetalTechnicals]
    default_chart_metal: Metal = Field(
        description="Metal charted when the analyst has not chosen one."
    )
    history_session_count: int = Field(
        gt=0, description="Number of bars supplied per metal in price_history."
    )


# ---------------------------------------------------------------------------
# Section 4 — ETF holdings and flows
# ---------------------------------------------------------------------------


class EtfFundFlow(ReportModel):
    """Holdings and flows for one exchange traded product.

    In production these figures are **T+1**: issuers publish the prior day's
    holdings in the morning, so the line reported at today's London close is
    yesterday's bar. ``as_of_date`` on the section states the effective date.
    """

    ticker: str = Field(description='Listing ticker, or "OTHER" for the aggregate line.')
    fund_name: str
    metal: Metal
    holdings_tonnes: float = Field(ge=0, description="Total metal held, in metric tonnes.")
    daily_change_tonnes: float = Field(
        description="Change in holdings vs the prior report, in tonnes; positive is a creation."
    )
    daily_change_usd: float = Field(
        description="Daily change valued at the session close, in USD; sign matches tonnes."
    )
    aum_usd: float = Field(ge=0, description="Assets under management in USD.")
    wtd_flow_tonnes: float = Field(description="Week-to-date cumulative flow in tonnes; signed.")
    mtd_flow_tonnes: float = Field(description="Month-to-date cumulative flow in tonnes; signed.")
    ytd_flow_tonnes: float = Field(description="Year-to-date cumulative flow in tonnes; signed.")
    ytd_flow_usd: float = Field(
        description="Year-to-date cumulative flow valued in USD; signed."
    )


class EtfMetalAggregate(ReportModel):
    """All tracked funds in one metal, summed."""

    metal: Metal
    holdings_tonnes: float = Field(ge=0)
    daily_change_tonnes: float
    daily_change_usd: float
    wtd_flow_tonnes: float
    mtd_flow_tonnes: float
    ytd_flow_tonnes: float
    aum_usd: float = Field(ge=0)


class EtfSection(ReportModel):
    """Section 4. Physically backed ETF holdings and flows.

    Reported holdings lag the market by one business day (T+1) in reality; the
    prototype fabricates the T+1 figure and stamps ``as_of_date`` accordingly.
    """

    as_of_date: date = Field(
        description="Effective date of the holdings figures (report date minus one session)."
    )
    reporting_lag_note: str = Field(
        description="Human-readable note explaining the T+1 reporting lag."
    )
    funds: list[EtfFundFlow]
    metal_aggregates: list[EtfMetalAggregate]


# ---------------------------------------------------------------------------
# Section 5 — open interest and positioning
# ---------------------------------------------------------------------------


class ComexContractActivity(ReportModel):
    """Open interest and volume for one COMEX contract."""

    contract_code: str = Field(description='Exchange root, e.g. "GC", "SI", "PL", "PA".')
    metal: Metal
    contract_size_oz: float = Field(gt=0, description="Troy ounces per contract.")
    open_interest_lots: int = Field(ge=0, description="Total open interest in contracts.")
    open_interest_change_lots: int = Field(
        description="Day-on-day change in open interest, in contracts; signed."
    )
    session_volume_lots: int = Field(ge=0, description="Session volume in contracts.")
    volume_20d_average_lots: int = Field(
        ge=0, description="Trailing 20-session average volume in contracts."
    )
    volume_vs_20d_average_pct: float = Field(
        description="Session volume as a percent deviation from the 20-day average; signed."
    )
    front_month_code: str = Field(description='Front month, e.g. "GCZ6".')
    front_month_expiry_date: date
    next_active_month_code: str = Field(description="Next active delivery month code.")
    next_active_expiry_date: date


class CotManagedMoney(ReportModel):
    """Managed money positioning from the CFTC Commitments of Traders report.

    The COT lags: it is surveyed on a Tuesday and published the following
    Friday afternoon, so ``report_date`` is always earlier than the report date
    and must be shown to the reader.
    """

    metal: Metal
    report_date: date = Field(description="Tuesday the COT position was surveyed.")
    published_date: date = Field(description="Friday the report was released by the CFTC.")
    managed_money_long_lots: int = Field(ge=0)
    managed_money_short_lots: int = Field(ge=0)
    managed_money_net_lots: int = Field(
        description="Long minus short, in contracts; signed."
    )
    net_change_wow_lots: int = Field(
        description="Week-on-week change in the net position, in contracts; signed."
    )
    net_oz: float = Field(
        description="Net position converted to troy ounces using contract_size_oz."
    )


class EfpLevel(ReportModel):
    """Exchange for physical level for one metal, USD per troy ounce."""

    metal: Metal
    efp_usd_per_oz: float = Field(
        description="Front-month EFP: futures minus loco London spot; signed."
    )
    recent_range_low_usd_per_oz: float = Field(
        description="Low of the trailing 20-session EFP range."
    )
    recent_range_high_usd_per_oz: float = Field(
        description="High of the trailing 20-session EFP range."
    )
    outside_recent_range: bool = Field(
        description="True when efp_usd_per_oz sits outside the trailing range — a dislocation flag."
    )


class PositioningSection(ReportModel):
    """Section 5. Exchange open interest, COT positioning and EFP levels."""

    contracts: list[ComexContractActivity]
    cot: list[CotManagedMoney]
    cot_report_date: date = Field(
        description="Survey date shared by the COT lines, surfaced for the heading."
    )
    cot_lag_days: int = Field(
        ge=0, description="Calendar days between cot_report_date and the report date."
    )
    efp: list[EfpLevel]
    any_efp_flagged: bool = Field(
        description="True when at least one EFP is outside its recent range."
    )


# ---------------------------------------------------------------------------
# Section 6 — physical inventories
# ---------------------------------------------------------------------------


class ComexStocks(ReportModel):
    """COMEX depository stocks for one metal, in troy ounces."""

    metal: Metal
    registered_oz: float = Field(ge=0, description="Registered (deliverable) stocks.")
    eligible_oz: float = Field(ge=0, description="Eligible (warranted but not offered) stocks.")
    total_oz: float = Field(ge=0, description="registered_oz plus eligible_oz.")
    registered_change_oz: float = Field(
        description="Day-on-day change in registered stocks; positive is metal in."
    )
    eligible_change_oz: float = Field(
        description="Day-on-day change in eligible stocks; positive is metal in."
    )
    total_change_oz: float = Field(description="Day-on-day change in total stocks; signed.")


class LbmaVaultHolding(ReportModel):
    """LBMA London vaulted holdings for one metal.

    LBMA publishes vault holdings **monthly**, around the twentieth of the
    following month, so this is the most recent month-end rather than today.
    """

    metal: Metal
    holdings_tonnes: float = Field(ge=0, description="Vaulted metal in London, in tonnes.")
    month_change_tonnes: float = Field(
        description="Change vs the prior published month, in tonnes; signed."
    )
    month_change_pct: float = Field(description="The same change in percent; signed.")
    as_of_month_end: date = Field(description="Month-end the holdings refer to.")


class SgeActivity(ReportModel):
    """Shanghai Gold Exchange withdrawals and the Shanghai premium."""

    metal: Metal
    withdrawals_tonnes: float = Field(
        ge=0, description="Metal withdrawn from SGE vaults over the reporting week, in tonnes."
    )
    withdrawals_period_days: int = Field(
        gt=0, description="Length of the withdrawal reporting period, in days."
    )
    premium_usd_per_oz: float = Field(
        description=(
            "Shanghai price versus loco London in USD per troy ounce; positive is "
            "a premium, negative a discount."
        )
    )
    premium_pct: float = Field(description="The same premium as a percent of loco London; signed.")


class LocoPremium(ReportModel):
    """Physical premium in one location versus loco London."""

    location: str = Field(description='Trading centre, e.g. "Zurich", "Singapore".')
    metal: Metal
    premium_usd_per_oz: float = Field(
        description="Premium over loco London in USD per troy ounce; negative is a discount."
    )


class LeaseRate(ReportModel):
    """Metal lease rates for one metal, annualised percent."""

    metal: Metal
    lease_rate_1m_pct: float = Field(description="1-month lease rate, annualised percent.")
    lease_rate_3m_pct: float = Field(description="3-month lease rate, annualised percent.")


class PhysicalSection(ReportModel):
    """Section 6. Inventories, regional premiums and lease rates.

    Mixed frequencies: COMEX stocks are daily, SGE withdrawals weekly, LBMA
    vault holdings monthly. Each model states its own effective period.
    """

    comex_stocks: list[ComexStocks]
    lbma_vault_holdings: list[LbmaVaultHolding]
    lbma_monthly_note: str = Field(
        description="Human-readable note explaining the monthly LBMA publication lag."
    )
    sge: list[SgeActivity]
    loco_premiums: list[LocoPremium]
    lease_rates: list[LeaseRate]


# ---------------------------------------------------------------------------
# Section 7 — look ahead
# ---------------------------------------------------------------------------


class CalendarEvent(ReportModel):
    """One dated entry in the forward calendar."""

    event_date: date
    event_time_london: str | None = Field(
        default=None,
        description='Time of day in London as "HH:MM" (24h), or null for all-day entries.',
    )
    category: EventCategory
    region: str = Field(description='Market affected, e.g. "US", "UK", "Euro area", "China".')
    event_name: str
    consensus: str | None = Field(
        default=None,
        description="Consensus expectation as displayed text, including its unit; null if none.",
    )
    previous: str | None = Field(
        default=None, description="Prior reading as displayed text; null if none."
    )
    importance: EventImportance
    note: str | None = Field(
        default=None, description="Desk note, e.g. which metal is most exposed."
    )


class ContractRollWindow(ReportModel):
    """First notice, expiry and roll window for one COMEX contract."""

    metal: Metal
    contract_code: str = Field(description='Full contract code, e.g. "GCZ6".')
    first_notice_date: date = Field(description="COMEX first notice day for the delivery month.")
    last_trade_date: date = Field(description="Final trading day of the contract.")
    roll_window_start_date: date
    roll_window_end_date: date


class LookAheadSection(ReportModel):
    """Section 7. Next session and next week.

    ``next_session_events`` covers the following trading day only;
    ``next_week_events`` covers the balance of the forward week.
    """

    next_session_date: date
    next_session_events: list[CalendarEvent]
    next_week_start_date: date
    next_week_end_date: date
    next_week_events: list[CalendarEvent]
    roll_windows: list[ContractRollWindow]
    holidays: list[CalendarEvent] = Field(
        description="Holiday entries affecting London, New York or Shanghai liquidity."
    )


# ---------------------------------------------------------------------------
# Commentary
# ---------------------------------------------------------------------------


class Commentary(ReportModel):
    """Analyst free text, persisted per report date.

    Every field is optional and an empty string means "omit this block from the
    email" — the renderer never emits a heading with no body. Keys match
    ``SectionKey`` so the Rust side can hold this as a map if preferred.
    """

    report_date: date
    author_name: str = Field(default="", description="Analyst who wrote the commentary.")
    headline: str = Field(default="", description="One-line headline for the email subject area.")
    market_overview: str = Field(default="", description="Top-level paragraph.")
    client_flows: str = Field(default="")
    risk: str = Field(default="")
    technicals: str = Field(default="")
    etf_flows: str = Field(default="")
    positioning: str = Field(default="")
    physical: str = Field(default="")
    look_ahead: str = Field(default="", description='The "what we are watching" box.')
    saved_at_london: datetime | None = Field(
        default=None, description="When the draft was last saved; null if never saved."
    )

    def text_for(self, key: SectionKey) -> str:
        """Return the commentary body for a section key, stripped."""
        return (getattr(self, key.value, "") or "").strip()


# ---------------------------------------------------------------------------
# Whole report
# ---------------------------------------------------------------------------


class EodReport(ReportModel):
    """One day's complete report: all seven sections plus the header.

    This is the object handed to the email renderer and the shape serialised to
    ``schema/sample_payload.json``.
    """

    header: ReportHeader
    client_flows: ClientFlowsSection
    risk: RiskSection
    technicals: TechnicalsSection
    etf: EtfSection
    positioning: PositioningSection
    physical: PhysicalSection
    look_ahead: LookAheadSection


#: Every model exported to ``schema/`` by ``export_schema.py``, in report order.
CONTRACT_MODELS: tuple[type[ReportModel], ...] = (
    MetalSnapshot,
    ReportHeader,
    ClientSegmentFlow,
    MetalClientFlow,
    ClientFlowsSection,
    DeskPosition,
    PnlAttribution,
    OptionsGreeks,
    LimitUtilisation,
    RiskSection,
    PriceBar,
    TechnicalLevel,
    MetalTechnicals,
    TechnicalsSection,
    EtfFundFlow,
    EtfMetalAggregate,
    EtfSection,
    ComexContractActivity,
    CotManagedMoney,
    EfpLevel,
    PositioningSection,
    ComexStocks,
    LbmaVaultHolding,
    SgeActivity,
    LocoPremium,
    LeaseRate,
    PhysicalSection,
    CalendarEvent,
    ContractRollWindow,
    LookAheadSection,
    Commentary,
    EodReport,
)
