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


COMEX_CONTRACTS: dict[str, ContractSpec] = {
    "XAU": ContractSpec("GC", 100.0, ("G", "J", "M", "Q", "Z")),
    "XAG": ContractSpec("SI", 5_000.0, ("H", "K", "N", "U", "Z")),
    "XPT": ContractSpec("PL", 50.0, ("F", "J", "N", "V")),
    "XPD": ContractSpec("PA", 100.0, ("H", "M", "U", "Z")),
}

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

#: Rough daily client turnover per metal in troy ounces, used to scale flows.
DAILY_CLIENT_TURNOVER_OZ: dict[str, float] = {
    "XAU": 420_000.0,
    "XAG": 12_500_000.0,
    "XPT": 130_000.0,
    "XPD": 55_000.0,
}

#: Desk risk limits in USD, keyed by limit name, used for utilisation lines.
RISK_LIMITS_USD: dict[str, float] = {
    "Desk VaR (1d, 99%)": 6_000_000.0,
    "Gold delta notional": 320_000_000.0,
    "Silver delta notional": 120_000_000.0,
    "PGM delta notional": 85_000_000.0,
    "Vega (per vol point)": 1_400_000.0,
}

#: Utilisation at or above this percentage raises a flag in the risk section.
LIMIT_WARNING_PCT: float = 80.0

# ---------------------------------------------------------------------------
# Physical market venues
# ---------------------------------------------------------------------------

#: Loco premium locations quoted in USD per troy ounce vs loco London.
PREMIUM_LOCATIONS: tuple[str, ...] = ("Zurich", "Dubai", "Singapore", "Hong Kong")

# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

#: Mixed into the per-date seed so a whole run of mock data can be re-rolled
#: without changing the report date.
MOCK_SEED_SALT: int = 20_260_101

#: Sessions of fabricated price history handed to the technicals section.
PRICE_HISTORY_SESSIONS: int = 180

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
