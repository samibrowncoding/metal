"""Market conventions: CCY1/CCY2, pips, premium and quote conventions.

Implements the conventions introduced in Chapter 1 (currency pairs, pips, big
figures), Chapter 2 (notional conversion via the strike), Chapter 7 (the three ATM
definitions, the out-of-the-money trading convention) and Chapter 10 (premium
quotation in CCY1%, CCY2 pips, CCY2%, CCY1 pips).

A currency pair is written CCY1/CCY2 and the rate is the number of CCY2 required to
buy one CCY1. Every sign and unit decision in this package follows from that.

Units, stated once and relied on everywhere else:

* Spot, strike and forward are CCY2 per CCY1.
* Volatilities are **decimals**: 0.085 means 8.5%. Conversion from the percent
  numbers a human types happens at the market data boundary, never mid-calculation.
* Rates are **continuously compounded decimals**, per Chapter 5 and Chapter 10.
* Option prices out of ``blackscholes`` and ``numerical`` are CCY2 pips - that is,
  CCY2 per one unit of CCY1 - unless the function name says otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# ---------------------------------------------------------------------------
# Currency pairs and pips
# ---------------------------------------------------------------------------

# Chapter 1: the market convention for which currency is CCY1 in a G10 pair follows
# this precedence. The pair is quoted with whichever currency appears first.
# The book is clear this is a convention with exceptions (some UK corporates trade
# GBP/EUR rather than EUR/GBP), so treat it as a default and not a law.
G10_PRECEDENCE: tuple[str, ...] = (
    "EUR", "GBP", "AUD", "NZD", "USD", "CAD", "CHF", "NOK", "SEK", "JPY",
)

# Chapter 1: a pip is the smallest increment normally quoted for a pair, which is a
# property of the pair rather than a universal constant. EUR/USD quotes to four
# decimal places so a pip is 0.0001; USD/JPY quotes to two so a pip is 0.01.
# JPY-quoted pairs are the common exception; everything else in G10 uses 0.0001.
_JPY_PIP = 0.01
_DEFAULT_PIP = 0.0001


@dataclass(frozen=True)
class CurrencyPair:
    """A currency pair quoted CCY1/CCY2.

    The exchange rate is the number of CCY2 needed to buy one CCY1. Rate up means
    CCY1 has strengthened; rate down means CCY1 has weakened.

    Attributes:
        ccy1: Three-letter code of the base currency - the one you are long or short
            when you take a position, and the one notionals are normally quoted in.
        ccy2: Three-letter code of the quote currency - the one P&L is naturally
            generated in.
    """

    ccy1: str
    ccy2: str

    def __post_init__(self) -> None:
        for code in (self.ccy1, self.ccy2):
            if len(code) != 3 or not code.isalpha() or not code.isupper():
                raise ValueError(
                    f"Currency code must be three uppercase letters, got {code!r}"
                )
        if self.ccy1 == self.ccy2:
            raise ValueError(f"A pair needs two different currencies, got {self.ccy1}")

    @classmethod
    def parse(cls, text: str) -> "CurrencyPair":
        """Build a pair from ``"EURUSD"`` or ``"EUR/USD"``.

        Args:
            text: Six-letter code, optionally with a separating slash.

        Returns:
            The parsed pair.

        Raises:
            ValueError: If the text is not six letters with an optional slash.
        """
        cleaned = text.replace("/", "").strip().upper()
        if len(cleaned) != 6:
            raise ValueError(f"Cannot parse {text!r} as a currency pair")
        return cls(cleaned[:3], cleaned[3:])

    @property
    def name(self) -> str:
        """The pair as ``"EUR/USD"``."""
        return f"{self.ccy1}/{self.ccy2}"

    @property
    def code(self) -> str:
        """The pair as ``"EURUSD"``, the form most tickers use."""
        return f"{self.ccy1}{self.ccy2}"

    @property
    def pip(self) -> float:
        """Size of one pip in this pair, in CCY2 per CCY1 (Ch. 1)."""
        return _JPY_PIP if self.ccy2 == "JPY" else _DEFAULT_PIP

    @property
    def premium_side(self) -> "PremiumSide":
        """Which currency the option premium is conventionally paid in (Ch. 10).

        Chapter 10 calls CCY1-premium pairs *left-hand side* and CCY2-premium pairs
        *right-hand side*. The book gives EUR/USD as CCY2 premium and EUR/JPY as
        CCY1 premium, and notes USD/JPY is CCY1 premium too.

        The rule implemented here - JPY as CCY2 means the premium is paid in CCY1,
        otherwise CCY2 - reproduces every example the book gives, but the book never
        states a general rule, and in practice the premium currency is agreed per
        trade. Flagged in ``notes/deviations.md``; override it explicitly when it
        matters rather than trusting this default.
        """
        return PremiumSide.CCY1 if self.ccy2 == "JPY" else PremiumSide.CCY2

    def __str__(self) -> str:
        return self.name


def pips_to_rate(pips: float, pair: CurrencyPair) -> float:
    """Convert a number of pips into a rate difference.

    Args:
        pips: Number of pips, e.g. 140 for EUR/USD 1yr swap points of 0.0140.
        pair: The pair, which sets the pip size.

    Returns:
        The equivalent move in CCY2 per CCY1.
    """
    return pips * pair.pip


def rate_to_pips(rate_difference: float, pair: CurrencyPair) -> float:
    """Convert a rate difference into a number of pips.

    Args:
        rate_difference: A difference in CCY2 per CCY1, e.g. 0.0140.
        pair: The pair, which sets the pip size.

    Returns:
        The equivalent number of pips.
    """
    return rate_difference / pair.pip


def big_figure(pair: CurrencyPair) -> float:
    """One big figure - a hundred pips (Ch. 1).

    Traders say "USD/JPY has dropped a figure" for a move of 101.20 to 100.20.
    """
    return 100.0 * pair.pip


# ---------------------------------------------------------------------------
# Spot P&L (Ch. 1)
# ---------------------------------------------------------------------------

def spot_pnl_ccy2(notional_ccy1: float, spot_initial: float, spot_final: float) -> float:
    """P&L from a spot position, in CCY2 (Ch. 1).

    Linear in spot. A short position is expressed as a negative notional rather than
    a separate formula - the book uses the same expression for both.

    Args:
        notional_ccy1: CCY1 notional. Negative for a short position.
        spot_initial: Rate the position was taken at.
        spot_final: Current or final rate.

    Returns:
        P&L in CCY2.
    """
    return notional_ccy1 * (spot_final - spot_initial)


def spot_pnl_ccy1(notional_ccy1: float, spot_initial: float, spot_final: float) -> float:
    """P&L from a spot position, converted back into CCY1 (Ch. 1).

    Curved, not linear - and that curvature is the point. The P&L is generated in
    CCY2 and converted at the *prevailing* rate, so a given CCY2 amount is worth
    more CCY1 at lower spot and less at higher spot.

    Args:
        notional_ccy1: CCY1 notional. Negative for a short position.
        spot_initial: Rate the position was taken at.
        spot_final: Current or final rate. Must be positive.

    Returns:
        P&L in CCY1.

    Raises:
        ValueError: If ``spot_final`` is not positive.
    """
    if spot_final <= 0:
        raise ValueError(f"Spot must be positive to convert P&L, got {spot_final}")
    return notional_ccy1 * (spot_final - spot_initial) / spot_final


# ---------------------------------------------------------------------------
# Notional and premium conversions (Ch. 2, Ch. 10)
# ---------------------------------------------------------------------------

def notional_ccy1_to_ccy2(notional_ccy1: float, strike: float) -> float:
    """Convert a CCY1 option notional into CCY2 terms (Ch. 2).

    Note this uses the **strike**, not spot. The strike is the rate at which the two
    currencies are potentially exchanged at maturity, so it is the right conversion
    rate for a notional. Using spot here is a common and quiet error.

    Args:
        notional_ccy1: Notional in CCY1.
        strike: Contract strike, CCY2 per CCY1.

    Returns:
        Notional in CCY2.
    """
    return notional_ccy1 * strike


def notional_ccy2_to_ccy1(notional_ccy2: float, strike: float) -> float:
    """Convert a CCY2 option notional into CCY1 terms (Ch. 2).

    Args:
        notional_ccy2: Notional in CCY2.
        strike: Contract strike, CCY2 per CCY1. Must be positive.

    Returns:
        Notional in CCY1.

    Raises:
        ValueError: If ``strike`` is not positive.
    """
    if strike <= 0:
        raise ValueError(f"Strike must be positive, got {strike}")
    return notional_ccy2 / strike


def ccy2_pips_to_ccy2_cash(price_ccy2_pips: float, notional_ccy1: float) -> float:
    """CCY2 pips to CCY2 cash (Practical B; Practical C, Task A, Step 3).

    Args:
        price_ccy2_pips: Option price in CCY2 per one CCY1.
        notional_ccy1: CCY1 notional.

    Returns:
        Cash premium in CCY2.
    """
    return price_ccy2_pips * notional_ccy1


def ccy2_cash_to_ccy1_cash(cash_ccy2: float, spot: float) -> float:
    """CCY2 cash to CCY1 cash, at spot (Practical C, Task A, Step 3).

    Args:
        cash_ccy2: Cash amount in CCY2.
        spot: Current spot, CCY2 per CCY1. Must be positive.

    Returns:
        Cash amount in CCY1.

    Raises:
        ValueError: If ``spot`` is not positive.
    """
    if spot <= 0:
        raise ValueError(f"Spot must be positive, got {spot}")
    return cash_ccy2 / spot


def ccy2_pips_to_ccy1_pct(price_ccy2_pips: float, spot: float) -> float:
    """CCY2 pips to CCY1 percent, as a decimal (Practicals B and C).

    Dividing a CCY2-per-CCY1 price by spot gives a price as a fraction of the CCY1
    notional. Both practicals do exactly this at the end of the pricing chain.

    The result is a decimal fraction: 0.0399 means 3.99 CCY1%. It is *not* multiplied
    by 100 here, because everything internal to this package stays in decimals.

    Args:
        price_ccy2_pips: Option price in CCY2 per one CCY1.
        spot: Current spot, CCY2 per CCY1. Must be positive.

    Returns:
        Price as a decimal fraction of the CCY1 notional.

    Raises:
        ValueError: If ``spot`` is not positive.
    """
    if spot <= 0:
        raise ValueError(f"Spot must be positive, got {spot}")
    return price_ccy2_pips / spot


def ccy1_pct_to_ccy2_pips(price_ccy1_pct: float, spot: float) -> float:
    """CCY1 percent (as a decimal) back to CCY2 pips.

    Args:
        price_ccy1_pct: Price as a decimal fraction of the CCY1 notional.
        spot: Current spot, CCY2 per CCY1.

    Returns:
        Price in CCY2 per one CCY1.
    """
    return price_ccy1_pct * spot


BASIS_POINT = 0.0001
"""One basis point: a hundredth of one percent of notional (Ch. 7, Ch. 10).

As a decimal fraction that is 0.0001. A price of 0.25 CCY1% is "twenty-five beeps".
"""


# ---------------------------------------------------------------------------
# Quote conventions (Ch. 7, Ch. 10)
# ---------------------------------------------------------------------------

class PremiumSide(str, Enum):
    """Which currency an option premium is paid in (Ch. 10).

    Chapter 10 names these left-hand side and right-hand side. The distinction is not
    cosmetic: under CCY1 premium the delta is premium-adjusted, which moves the
    zero-delta straddle strike to the other side of the forward (Ch. 8).
    """

    CCY1 = "CCY1"
    CCY2 = "CCY2"

    @property
    def market_name(self) -> str:
        """The desk name: LHS for CCY1 premium, RHS for CCY2 premium."""
        return "LHS" if self is PremiumSide.CCY1 else "RHS"


class ATMConvention(str, Enum):
    """Which contract "ATM" means in a given pair (Ch. 7).

    Three different things wear the same name, and they are not interchangeable:

    * ``DELTA_NEUTRAL_STRADDLE`` - strike set so the call and put deltas cancel, so
      the straddle has zero delta. The G10 convention, and the one people mean by
      "ATM" without qualification.
    * ``FORWARD`` - strike exactly equal to the forward (ATMF). Used in some EM
      pairs, traded as a single option plus a forward hedge.
    * ``SPOT`` - strike equal to current spot (ATMS).

    Assuming ATM means at-the-forward is one of the standard traps: under CCY2
    premium the delta-neutral strike sits *above* the forward, by the Ito term.
    """

    DELTA_NEUTRAL_STRADDLE = "delta_neutral_straddle"
    FORWARD = "forward"
    SPOT = "spot"


class OptionType(str, Enum):
    """Call or put, always on CCY1 (Ch. 2).

    An FX option is simultaneously a call on one currency and a put on the other. The
    market names only the CCY1 direction, so a "EUR/USD call" is a EUR call and a USD
    put. This enum follows that: ``CALL`` means the right to buy CCY1.
    """

    CALL = "call"
    PUT = "put"

    @property
    def sign(self) -> int:
        """+1 for a call, -1 for a put.

        Lets the two Garman-Kohlhagen branches collapse into one expression where
        that reads more clearly than an if-statement.
        """
        return 1 if self is OptionType.CALL else -1


def otm_option_type(strike: float, atm_strike: float) -> OptionType:
    """Which side the market would actually trade for this strike (Ch. 7).

    The convention away from the ATM is always to trade the out-of-the-money side -
    the call or put with the smaller absolute delta. Strike above the ATM trades as a
    CCY1 call; strike below trades as a CCY1 put.

    The reason is credit, not maths: the OTM direction carries a smaller premium and
    a smaller expected payoff, so less counterparty exposure. Chapter 7 notes that an
    in-the-money request should prompt the question of why the conventional side is
    not being traded.

    A strike exactly at the ATM is returned as a call; at that point the two are
    equivalent up to a forward and the choice is arbitrary.

    Args:
        strike: The contract strike.
        atm_strike: The ATM strike at the same tenor.

    Returns:
        The conventionally traded option type.
    """
    return OptionType.CALL if strike >= atm_strike else OptionType.PUT


# ---------------------------------------------------------------------------
# Greek quotation conventions (Practical C, Task C)
# ---------------------------------------------------------------------------

def vega_to_market_terms(vega_raw: float, spot: float) -> float:
    """Convert raw Black-Scholes vega into the market's quotation (Practical C).

    Two adjustments, and the book applies both:

    1. Into CCY1 terms, by dividing by spot.
    2. Per 1% move in implied volatility rather than per 1.0, by dividing by 100.

    So a raw vega of about 0.3989 at S = K = 1.0, T = 1.0 becomes roughly 0.00399,
    which is the "a shade under 0.40%" the practical asks you to check.

    Args:
        vega_raw: Vega straight out of the closed-form or finite-difference
            calculation, in CCY2 pips per unit change in volatility.
        spot: Current spot. Must be positive.

    Returns:
        Vega as a decimal fraction of CCY1 notional per 1% volatility move.

    Raises:
        ValueError: If ``spot`` is not positive.
    """
    if spot <= 0:
        raise ValueError(f"Spot must be positive, got {spot}")
    return 0.01 * vega_raw / spot


MARKET_TENORS: tuple[str, ...] = (
    "ON", "1W", "2W", "1M", "2M", "3M", "6M", "9M", "1Y", "2Y",
)
"""The standard market tenors used throughout Part II (Ch. 7, Ch. 11).

Chapter 7 lists O/N, 1wk, 2wk, 1mth, 2mth, 3mth, 6mth, 1yr and 2yr as the liquid
set. 9M is included here because Practical D's tenor table asks for it.
"""
