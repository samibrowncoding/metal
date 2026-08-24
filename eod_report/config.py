"""Static configuration for the EOD precious metals report prototype.

Everything that a desk would plausibly want to tune without touching logic lives
here: the mock/live switch, price anchors used to fabricate plausible markets,
unit conversion constants, contract specifications and presentation defaults.

Nothing in this module performs I/O or network access.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

# ---------------------------------------------------------------------------
# Wiring switches
# ---------------------------------------------------------------------------

#: When True the app builds its report from ``MockDataProvider``.
#: Flip to False to route every call through ``LiveDataProvider`` instead.
USE_MOCK: bool = True

#: Embed plotly charts into the email as base64 PNGs (requires ``kaleido``).
#: When kaleido is missing the renderer degrades to tables automatically, so
#: leaving this True on a machine without kaleido is safe.
EMBED_CHARTS_IN_EMAIL: bool = True

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PACKAGE_ROOT: Path = Path(__file__).resolve().parent
COMMENTARY_DIR: Path = PACKAGE_ROOT / "commentary"
SCHEMA_DIR: Path = PACKAGE_ROOT / "schema"
TEMPLATE_DIR: Path = PACKAGE_ROOT / "report"
TEMPLATE_NAME: str = "template.html.j2"

# ---------------------------------------------------------------------------
# Time
# ---------------------------------------------------------------------------

#: All timestamps in the report are London wall-clock time.
LONDON_TZ = ZoneInfo("Europe/London")
NEW_YORK_TZ = ZoneInfo("America/New_York")
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")

REPORT_LABEL: str = "EOD — London close"

#: Nominal London close used to stamp the report when the app is opened
#: at some other time of day (24h clock, London time).
LONDON_CLOSE_HOUR: int = 16
LONDON_CLOSE_MINUTE: int = 30

#: LBMA auction times, London time (24h clock). Used by the look-ahead section.
LBMA_AUCTION_TIMES_LONDON: dict[str, tuple[str, ...]] = {
    "XAU": ("10:30", "15:00"),
    "XAG": ("12:00",),
    "XPT": ("09:45", "14:00"),
    "XPD": ("09:45", "14:00"),
}

# ---------------------------------------------------------------------------
# Units — the single source of truth for conversions
# ---------------------------------------------------------------------------

#: Troy ounces in one metric tonne (1 t = 32,150.7 oz).
OZ_PER_TONNE: float = 32_150.7
#: Grams in one troy ounce.
GRAMS_PER_TROY_OZ: float = 31.1035
#: Metric tonnes in one troy ounce.
TONNES_PER_OZ: float = 1.0 / OZ_PER_TONNE


def oz_to_tonnes(ounces: float) -> float:
    """Convert troy ounces to metric tonnes."""
    return ounces / OZ_PER_TONNE


def tonnes_to_oz(tonnes: float) -> float:
    """Convert metric tonnes to troy ounces."""
    return tonnes * OZ_PER_TONNE


def oz_to_grams(ounces: float) -> float:
    """Convert troy ounces to grams."""
    return ounces * GRAMS_PER_TROY_OZ


# ---------------------------------------------------------------------------
# Metals in scope
# ---------------------------------------------------------------------------

#: Metal codes in report order. Mirrored by ``models.Metal``.
METALS: tuple[str, ...] = ("XAU", "XAG", "XPT", "XPD")

METAL_NAMES: dict[str, str] = {
    "XAU": "Gold",
    "XAG": "Silver",
    "XPT": "Platinum",
    "XPD": "Palladium",
}


@dataclass(frozen=True)
class PriceAnchor:
    """Plausible current-market anchor for one metal, in USD per troy ounce.

    ``low``/``high`` bound the fabricated close; ``daily_vol_pct`` drives the
    size of the fabricated session move; ``price_decimals`` fixes how the metal
    is printed everywhere (screen and email) so decimals stay consistent per
    instrument.
    """

    low_usd_per_oz: float
    high_usd_per_oz: float
    daily_vol_pct: float
    price_decimals: int
    #: Typical annualised 1-month implied vol, in percent.
    implied_vol_1m_pct: float


#: Anchors are deliberately configurable — the mock provider reads these rather
#: than hardcoding literals, so re-anchoring the whole app is a one-line edit.
PRICE_ANCHORS: dict[str, PriceAnchor] = {
    "XAU": PriceAnchor(3_300.0, 3_500.0, 0.85, 2, 15.5),
    "XAG": PriceAnchor(38.0, 42.0, 1.60, 3, 27.0),
    "XPT": PriceAnchor(1_200.0, 1_400.0, 1.40, 2, 22.0),
    "XPD": PriceAnchor(1_000.0, 1_200.0, 1.70, 2, 30.0),
}


@dataclass(frozen=True)
class ContractSpec:
    """COMEX futures contract specification for one metal."""

    contract_code: str
    contract_size_oz: float
    #: Delivery months quoted as single-letter codes, in calendar order.
    active_months: tuple[str, ...]
    #: Anchor for fabricated total open interest, in contracts.
    open_interest_lots: int
    #: Anchor for fabricated session volume, in contracts.
    session_volume_lots: int
    #: Anchor for the front-month EFP, in USD per troy ounce.
    efp_usd_per_oz: float


COMEX_CONTRACTS: dict[str, ContractSpec] = {
    "XAU": ContractSpec("GC", 100.0, ("G", "J", "M", "Q", "Z"), 485_000, 168_000, 4.20),
    "XAG": ContractSpec("SI", 5_000.0, ("H", "K", "N", "U", "Z"), 152_000, 62_000, 0.075),
    "XPT": ContractSpec("PL", 50.0, ("F", "J", "N", "V"), 74_000, 21_000, 6.50),
    "XPD": ContractSpec("PA", 100.0, ("H", "M", "U", "Z"), 24_500, 6_800, 5.00),
}

#: Business days before first notice day that the desk treats as the roll window.
ROLL_WINDOW_BUSINESS_DAYS: int = 6

MONTH_CODE_NAMES: dict[str, str] = {
    "F": "Jan",
    "G": "Feb",
    "H": "Mar",
    "J": "Apr",
    "K": "May",
    "M": "Jun",
    "N": "Jul",
    "Q": "Aug",
    "U": "Sep",
    "V": "Oct",
    "X": "Nov",
    "Z": "Dec",
}


@dataclass(frozen=True)
class EtfSpec:
    """A physically backed ETF tracked by the desk."""

    ticker: str
    name: str
    metal: str
    #: Anchor for fabricated holdings, in metric tonnes.
    holdings_tonnes: float


ETF_FUNDS: tuple[EtfSpec, ...] = (
    EtfSpec("GLD", "SPDR Gold Shares", "XAU", 955.0),
    EtfSpec("IAU", "iShares Gold Trust", "XAU", 460.0),
    EtfSpec("SLV", "iShares Silver Trust", "XAG", 14_800.0),
    EtfSpec("PPLT", "abrdn Physical Platinum Shares", "XPT", 27.5),
    EtfSpec("PALL", "abrdn Physical Palladium Shares", "XPD", 8.4),
)

#: Ticker used for the residual "everything else" line in the ETF table.
ETF_OTHER_TICKER: str = "OTHER"
ETF_OTHER_NAME: str = "Other / aggregate (all issuers)"

#: Residual non-tracked holdings per metal, in tonnes, used for the Other line.
ETF_OTHER_HOLDINGS_TONNES: dict[str, float] = {
    "XAU": 1_620.0,
    "XAG": 8_900.0,
    "XPT": 63.0,
    "XPD": 12.5,
}

# ---------------------------------------------------------------------------
# Desk shape — drives the scale of fabricated flows, positions and limits
# ---------------------------------------------------------------------------

#: Client segments in report order. Mirrored by ``models.ClientSegment``.
CLIENT_SEGMENTS: tuple[str, ...] = (
    "central_bank",
    "producer_hedger",
    "refiner",
    "investment_asset_manager",
    "industrial",
    "hedge_fund_cta",
    "retail_wholesale",
)

CLIENT_SEGMENT_NAMES: dict[str, str] = {
    "central_bank": "Central bank",
    "producer_hedger": "Producer / hedger",
    "refiner": "Refiner",
    "investment_asset_manager": "Investment / asset manager",
    "industrial": "Industrial",
    "hedge_fund_cta": "Hedge fund / CTA",
    "retail_wholesale": "Retail / wholesale",
}

#: Round-number price increments the desk watches as levels, USD per troy ounce.
ROUND_LEVEL_STEP_USD_PER_OZ: dict[str, float] = {
    "XAU": 50.0,
    "XAG": 1.0,
    "XPT": 25.0,
    "XPD": 25.0,
}

#: Typical client ticket size per metal, in troy ounces.
AVERAGE_TICKET_SIZE_OZ: dict[str, float] = {
    "XAU": 3_000.0,
    "XAG": 100_000.0,
    "XPT": 1_500.0,
    "XPD": 800.0,
}

#: Rough daily client turnover per metal in troy ounces, used to scale flows.
DAILY_CLIENT_TURNOVER_OZ: dict[str, float] = {
    "XAU": 420_000.0,
    "XAG": 12_500_000.0,
    "XPT": 130_000.0,
    "XPD": 55_000.0,
}

#: Share of each client segment in a metal's client turnover. Rows sum to 1.0.
CLIENT_SEGMENT_WEIGHTS: dict[str, dict[str, float]] = {
    "XAU": {
        "central_bank": 0.18,
        "producer_hedger": 0.06,
        "refiner": 0.08,
        "investment_asset_manager": 0.24,
        "industrial": 0.03,
        "hedge_fund_cta": 0.26,
        "retail_wholesale": 0.15,
    },
    "XAG": {
        "central_bank": 0.00,
        "producer_hedger": 0.10,
        "refiner": 0.12,
        "investment_asset_manager": 0.18,
        "industrial": 0.22,
        "hedge_fund_cta": 0.23,
        "retail_wholesale": 0.15,
    },
    "XPT": {
        "central_bank": 0.00,
        "producer_hedger": 0.22,
        "refiner": 0.14,
        "investment_asset_manager": 0.14,
        "industrial": 0.28,
        "hedge_fund_cta": 0.16,
        "retail_wholesale": 0.06,
    },
    "XPD": {
        "central_bank": 0.00,
        "producer_hedger": 0.20,
        "refiner": 0.16,
        "investment_asset_manager": 0.10,
        "industrial": 0.38,
        "hedge_fund_cta": 0.12,
        "retail_wholesale": 0.04,
    },
}

#: Desk risk limits in USD, keyed by limit name, used for utilisation lines.
RISK_LIMITS_USD: dict[str, float] = {
    "Desk VaR (1d, 99%)": 14_000_000.0,
    "Gold delta notional": 320_000_000.0,
    "Silver delta notional": 120_000_000.0,
    "PGM delta notional": 85_000_000.0,
    "Vega (per vol point)": 1_400_000.0,
}

#: Utilisation at or above this percentage raises a flag in the risk section.
LIMIT_WARNING_PCT: float = 80.0

#: Fraction of a delta limit the desk typically runs, used to scale positions
#: so that fabricated limit utilisation lands in a plausible band.
POSITION_LIMIT_USAGE_RANGE: tuple[float, float] = (0.30, 0.86)

#: Confidence multiple for a 99% one-tailed VaR, and sessions in a trading year.
VAR_Z_99: float = 2.326
TRADING_DAYS_PER_YEAR: int = 252

#: Average pairwise correlation assumed between metals when diversifying VaR.
VAR_CROSS_METAL_CORRELATION: float = 0.60

# ---------------------------------------------------------------------------
# Physical market venues
# ---------------------------------------------------------------------------

#: Loco premium locations quoted in USD per troy ounce vs loco London.
PREMIUM_LOCATIONS: tuple[str, ...] = ("Zurich", "Dubai", "Singapore", "Hong Kong")

#: Typical loco premium over London, USD per troy ounce, by location and metal.
LOCO_PREMIUM_ANCHORS_USD_PER_OZ: dict[str, dict[str, float]] = {
    "Zurich": {"XAU": 0.35, "XAG": 0.02, "XPT": 1.50, "XPD": 1.75},
    "Dubai": {"XAU": 1.10, "XAG": 0.06, "XPT": 2.25, "XPD": 2.50},
    "Singapore": {"XAU": 1.60, "XAG": 0.09, "XPT": 3.00, "XPD": 3.25},
    "Hong Kong": {"XAU": 2.10, "XAG": 0.11, "XPT": 4.00, "XPD": 4.50},
}

#: COMEX depository anchors in troy ounces: (registered, eligible).
COMEX_STOCK_ANCHORS_OZ: dict[str, tuple[float, float]] = {
    "XAU": (18_400_000.0, 17_100_000.0),
    "XAG": (168_000_000.0, 335_000_000.0),
    "XPT": (285_000.0, 640_000.0),
    "XPD": (58_000.0, 82_000.0),
}

#: LBMA London vaulted holdings anchors, in metric tonnes.
LBMA_VAULT_ANCHOR_TONNES: dict[str, float] = {
    "XAU": 8_850.0,
    "XAG": 24_600.0,
    "XPT": 195.0,
    "XPD": 38.0,
}

#: Shanghai Gold Exchange weekly withdrawal anchors, in metric tonnes.
SGE_WITHDRAWAL_ANCHOR_TONNES: dict[str, float] = {"XAU": 27.0, "XAG": 320.0}

#: Shanghai premium over loco London anchors, in USD per troy ounce.
SGE_PREMIUM_ANCHOR_USD_PER_OZ: dict[str, float] = {"XAU": 9.0, "XAG": 0.35}

#: SGE withdrawal reporting period, in days.
SGE_WITHDRAWAL_PERIOD_DAYS: int = 7

#: Lease rate anchors in annualised percent: (1-month, 3-month).
LEASE_RATE_ANCHORS_PCT: dict[str, tuple[float, float]] = {
    "XAU": (1.05, 1.35),
    "XAG": (1.90, 2.20),
    "XPT": (3.40, 3.10),
    "XPD": (4.60, 4.10),
}

# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

#: Mixed into the per-date seed so a whole run of mock data can be re-rolled
#: without changing the report date.
MOCK_SEED_SALT: int = 20_260_101

#: Sessions of fabricated price history handed to the technicals section.
#: Must exceed 200 so the 200-day moving average is genuinely computable.
PRICE_HISTORY_SESSIONS: int = 260

# ---------------------------------------------------------------------------
# Look-ahead calendar
# ---------------------------------------------------------------------------

#: Fabricated economic and central bank calendar entries the mock provider
#: draws from. Tuple layout:
#: (event_name, region, time_london_hh_mm, importance, consensus, previous)
CALENDAR_TEMPLATES: tuple[tuple[str, str, str, str, str | None, str | None], ...] = (
    ("US CPI (m/m)", "US", "13:30", "high", "+0.2%", "+0.3%"),
    ("US core PCE (m/m)", "US", "13:30", "high", "+0.2%", "+0.2%"),
    ("US non-farm payrolls", "US", "13:30", "high", "+145k", "+119k"),
    ("US initial jobless claims", "US", "13:30", "medium", "228k", "233k"),
    ("US retail sales (m/m)", "US", "13:30", "medium", "+0.3%", "+0.5%"),
    ("US PPI (m/m)", "US", "13:30", "medium", "+0.2%", "+0.1%"),
    ("ISM manufacturing PMI", "US", "15:00", "medium", "49.4", "48.9"),
    ("US 10y Treasury auction", "US", "18:00", "low", None, "4.21% stop"),
    ("Euro area flash CPI (y/y)", "Euro area", "10:00", "medium", "+2.1%", "+2.2%"),
    ("UK labour market report", "UK", "07:00", "medium", "4.4% u/e", "4.4% u/e"),
    ("China official manufacturing PMI", "China", "02:30", "medium", "49.8", "49.6"),
    ("China trade balance", "China", "04:00", "low", "$92.0bn", "$98.2bn"),
    ("India festival demand survey", "India", "11:00", "low", None, None),
    ("FOMC rate decision", "US", "19:00", "high", "no change", "no change"),
    ("FOMC minutes", "US", "19:00", "medium", None, None),
    ("Fed chair testimony", "US", "15:00", "medium", None, None),
    ("ECB rate decision", "Euro area", "13:15", "high", "no change", "no change"),
    ("Bank of England rate decision", "UK", "12:00", "high", "no change", "-25bp"),
    ("PBoC monthly LPR fixing", "China", "01:15", "low", "no change", "no change"),
)

#: Calendar entries treated as central bank rather than economic releases.
CENTRAL_BANK_EVENT_NAMES: frozenset[str] = frozenset(
    {
        "FOMC rate decision",
        "FOMC minutes",
        "Fed chair testimony",
        "ECB rate decision",
        "Bank of England rate decision",
        "PBoC monthly LPR fixing",
    }
)

#: Fabricated market holidays affecting London, New York or Shanghai liquidity.
#: Tuple layout: (month, day, region, holiday_name). Year-agnostic on purpose —
#: the prototype does not model the moveable feasts.
MARKET_HOLIDAYS: tuple[tuple[int, int, str, str], ...] = (
    (1, 1, "London / New York / Shanghai", "New Year's Day"),
    (1, 19, "New York", "Martin Luther King Jr. Day"),
    (2, 17, "Shanghai", "Lunar New Year (week-long closure begins)"),
    (5, 4, "London", "Early May bank holiday"),
    (5, 25, "London / New York", "Spring bank holiday / Memorial Day"),
    (7, 3, "New York", "Independence Day (observed)"),
    (8, 31, "London", "Summer bank holiday"),
    (9, 7, "New York", "Labor Day"),
    (10, 1, "Shanghai", "National Day (Golden Week begins)"),
    (11, 26, "New York", "Thanksgiving"),
    (12, 25, "London / New York", "Christmas Day"),
    (12, 26, "London", "Boxing Day"),
)

#: How far ahead the look-ahead section scans for holidays, in calendar days.
HOLIDAY_LOOKAHEAD_DAYS: int = 21

# ---------------------------------------------------------------------------
# Presentation
# ---------------------------------------------------------------------------

#: Soft word-count guide shown under each commentary box.
COMMENTARY_WORD_TARGET: tuple[int, int] = (40, 80)

COMMENTARY_PLACEHOLDERS: dict[str, str] = {
    "market_overview": (
        "Two to three sentences: what drove the session, where the market "
        "closed relative to the range, and the single thing a reader should "
        "take away."
    ),
    "client_flows": (
        "Two to three sentences: who was on the other side, which segment "
        "dominated, and whether the axes are likely to persist tomorrow."
    ),
    "risk": (
        "Two to three sentences: where the book is positioned, what drove "
        "P&L, and any limit or greek that needs watching."
    ),
    "technicals": (
        "Two to three sentences: the level that mattered today, the level "
        "that matters next, and whether the trend label has changed."
    ),
    "etf_flows": (
        "Two to three sentences: direction and size of ETF demand, whether "
        "it confirms or contradicts price, and the metal that stands out."
    ),
    "positioning": (
        "Two to three sentences: what open interest and COT say about "
        "positioning, and whether EFP is signalling stress."
    ),
    "physical": (
        "Two to three sentences: where physical metal is tight or loose, "
        "what premiums and lease rates imply, and any inventory shift."
    ),
    "look_ahead": (
        "Two to three sentences: the events that could move the market, what "
        "we are positioned for, and the risk to that view."
    ),
}

#: Email palette — quiet greys, white, one accent, direction colours only.
EMAIL_COLOURS: dict[str, str] = {
    "accent": "#1f4e5f",
    "text": "#222222",
    "muted": "#6b6b6b",
    "rule": "#dddddd",
    "band": "#f5f5f3",
    "up": "#1a7f37",
    "down": "#b42318",
    "flat": "#6b6b6b",
    "flag": "#b42318",
}

EMAIL_MAX_WIDTH_PX: int = 800
EMAIL_FONT_STACK: str = "Arial, Helvetica, sans-serif"

#: On-screen chart palette, one entry per theme. The seven ``segment_*`` hues
#: are assigned to client segments in the fixed order of ``CLIENT_SEGMENTS`` and
#: are never cycled or reordered; the three ``ma_*`` hues colour the moving
#: averages. Both sets were checked for colour-vision separation and contrast
#: against their own surface in each theme.
CHART_COLOURS: dict[str, dict[str, str]] = {
    "light": {
        "ink": "#0b0b0b",
        "muted": "#898781",
        "grid": "#e1e0d9",
        "axis": "#c3c2b7",
        "price": "#0b0b0b",
        "ma_50": "#2a78d6",
        "ma_100": "#eb6834",
        "ma_200": "#1baf7a",
        "level": "#898781",
        "segment_1": "#2a78d6",
        "segment_2": "#eb6834",
        "segment_3": "#1baf7a",
        "segment_4": "#eda100",
        "segment_5": "#e87ba4",
        "segment_6": "#008300",
        "segment_7": "#4a3aa7",
    },
    "dark": {
        "ink": "#ffffff",
        "muted": "#898781",
        "grid": "#2c2c2a",
        "axis": "#383835",
        "price": "#ffffff",
        "ma_50": "#3987e5",
        "ma_100": "#d95926",
        "ma_200": "#199e70",
        "level": "#898781",
        "segment_1": "#3987e5",
        "segment_2": "#d95926",
        "segment_3": "#199e70",
        "segment_4": "#c98500",
        "segment_5": "#d55181",
        "segment_6": "#008300",
        "segment_7": "#9085e9",
    },
}
