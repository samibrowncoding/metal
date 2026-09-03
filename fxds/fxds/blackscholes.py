"""Garman-Kohlhagen pricing and first-order greeks - Practical C (Ch. 5-6).

Implements Practical C in full:

* Task A - forward, call and put prices in CCY2 pips, notional handling and the
  premium conversions, and put-call parity including why the undiscounted form fails.
* Task B - the pricing function itself, with the guard against non-positive time to
  expiry or volatility that the book asks for.
* Task C - delta and vega by closed form and by central finite difference, plus the
  market quotation conventions for each.
* Task D - the exposure profiles (delta, vega and value against spot, time and
  volatility) that the notebooks plot.

Prices are in CCY2 pips (CCY2 per one CCY1) unless a function says otherwise.

The formulas are written to look like the formulas. ``norm.cdf(d1)`` and the
expression around it are on the page rather than hidden behind a pricing library,
because the point of this module is to be read alongside Chapter 5.
"""

from __future__ import annotations

import numpy as np
from scipy.stats import norm

from .conventions import OptionType, vega_to_market_terms

# Practical C, Task B: the book asks for an explicit check for zero or negative
# implied volatility or time to maturity, clamping them to a small positive value so
# the formula returns the payoff at maturity rather than raising. It suggests 1e-10.
#
# The book's printed VBA reads `If (T >= 0) Then T = 0.0000000001`, which fires on
# every valid input and destroys the price. That is a transcription defect - the
# surrounding prose states the intent plainly - so the comparison is `<=` here.
# Recorded in notes/deviations.md.
_FLOOR = 1e-10


def _clamp(T: float, sigma: float) -> tuple[float, float]:
    """Floor time to expiry and volatility at a tiny positive value.

    With both floored to 1e-10, ``d1`` and ``d2`` diverge to plus or minus infinity
    depending on whether the option is in or out of the money, the cumulative normals
    saturate at 1 or 0, and the formula collapses to the payoff at maturity. That is
    exactly the behaviour Practical C asks for.
    """
    return (max(T, _FLOOR), max(sigma, _FLOOR))


def forward(spot: float, T: float, r_ccy1: float, r_ccy2: float) -> float:
    """Forward outright to time T (Practical C, Task A, Step 1).

    ``F_T = S * exp((r2 - r1) * T)``

    This comes out of the Black-Scholes SDE with volatility set to zero (Ch. 5). Zero
    volatility does not mean spot is static - it means spot follows this path exactly.

    When the two rates are equal the forward equals spot, which is the first thing
    the practical asks you to check.

    Args:
        spot: Current spot, CCY2 per CCY1.
        T: Time to expiry in years.
        r_ccy1: Continuously compounded CCY1 rate.
        r_ccy2: Continuously compounded CCY2 rate.

    Returns:
        The forward rate to time T, CCY2 per CCY1.
    """
    return spot * np.exp((r_ccy2 - r_ccy1) * T)


def d1_d2(
    spot: float,
    strike: float,
    T: float,
    r_ccy1: float,
    r_ccy2: float,
    sigma: float,
) -> tuple[float, float]:
    """The two Black-Scholes arguments (Ch. 5).

    ``d1 = [ln(S/K) + (r2 - r1 + sigma^2 / 2) * T] / (sigma * sqrt(T))``
    ``d2 = d1 - sigma * sqrt(T)``

    Args:
        spot: Current spot, CCY2 per CCY1. Must be positive.
        strike: Strike, CCY2 per CCY1. Must be positive.
        T: Time to expiry in years. Floored at a tiny positive value.
        r_ccy1: Continuously compounded CCY1 rate.
        r_ccy2: Continuously compounded CCY2 rate.
        sigma: Implied volatility as a decimal. Floored at a tiny positive value.

    Returns:
        The pair ``(d1, d2)``.

    Raises:
        ValueError: If spot or strike is not positive.
    """
    if spot <= 0:
        raise ValueError(f"Spot must be positive, got {spot}")
    if strike <= 0:
        raise ValueError(f"Strike must be positive, got {strike}")

    T, sigma = _clamp(T, sigma)
    sqrt_T = np.sqrt(T)

    d1 = (np.log(spot / strike) + (r_ccy2 - r_ccy1 + sigma**2 / 2) * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T
    return d1, d2


def price(
    option_type: OptionType,
    spot: float,
    strike: float,
    T: float,
    r_ccy1: float,
    r_ccy2: float,
    sigma: float,
) -> float:
    """European vanilla price in CCY2 pips (Practical C, Tasks A and B).

    Garman and Kohlhagen (1983), the FX extension of Black-Scholes that discounts at
    a different rate in each currency:

    ``call = S * exp(-r1 * T) * N(d1) - K * exp(-r2 * T) * N(d2)``
    ``put  = K * exp(-r2 * T) * N(-d2) - S * exp(-r1 * T) * N(-d1)``

    Args:
        option_type: Call or put, on CCY1.
        spot: Current spot, CCY2 per CCY1.
        strike: Strike, CCY2 per CCY1.
        T: Time to expiry in years. Non-positive values are floored, returning the
            payoff at maturity.
        r_ccy1: Continuously compounded CCY1 rate.
        r_ccy2: Continuously compounded CCY2 rate.
        sigma: Implied volatility as a decimal (0.10 is 10%). Non-positive values are
            floored, returning the payoff at maturity.

    Returns:
        Option price in CCY2 pips - CCY2 per one unit of CCY1.

    Examples:
        The acceptance test from Practical C, Task A, Step 2:

        >>> from fxds.conventions import OptionType
        >>> round(float(price(OptionType.CALL, 1.0, 1.0, 1.0, 0.0, 0.0, 0.10)), 4)
        0.0399
    """
    T, sigma = _clamp(T, sigma)
    d1, d2 = d1_d2(spot, strike, T, r_ccy1, r_ccy2, sigma)

    df_ccy1 = np.exp(-r_ccy1 * T)
    df_ccy2 = np.exp(-r_ccy2 * T)

    if option_type is OptionType.CALL:
        return spot * df_ccy1 * norm.cdf(d1) - strike * df_ccy2 * norm.cdf(d2)
    return strike * df_ccy2 * norm.cdf(-d2) - spot * df_ccy1 * norm.cdf(-d1)


def payoff(option_type: OptionType, spot_at_expiry: float, strike: float) -> float:
    """Value at maturity, in CCY2 pips (Ch. 2).

    ``call = max(S_T - K, 0)``, ``put = max(K - S_T, 0)``.

    Args:
        option_type: Call or put, on CCY1.
        spot_at_expiry: Spot at the option maturity.
        strike: Strike.

    Returns:
        The payoff in CCY2 per one CCY1.
    """
    if option_type is OptionType.CALL:
        return max(spot_at_expiry - strike, 0.0)
    return max(strike - spot_at_expiry, 0.0)


# ---------------------------------------------------------------------------
# Put-call parity (Practical C, Task A, Step 4)
# ---------------------------------------------------------------------------

def put_call_parity_rhs(
    spot: float,
    strike: float,
    T: float,
    r_ccy1: float,
    r_ccy2: float,
    *,
    discounted: bool = True,
) -> float:
    """The right-hand side of put-call parity (Practical C, Task A, Step 4).

    The book first states parity as ``call - put = F - K``, then shows the subtlety:
    option prices are present valued, while the ``F - K`` difference is a P&L
    realised in the *future*. So the correct relation carries the CCY2 discount
    factor:

    ``call - put = exp(-r2 * T) * (F - K)``

    The undiscounted version is not a rounding difference - it is wrong by the whole
    discount factor, and only coincides when ``r2 = 0`` or ``K = F``. Pass
    ``discounted=False`` to reproduce the failure deliberately, which is what the
    notebook does.

    Args:
        spot: Current spot.
        strike: Strike.
        T: Time to expiry in years.
        r_ccy1: Continuously compounded CCY1 rate.
        r_ccy2: Continuously compounded CCY2 rate.
        discounted: Whether to apply the CCY2 discount factor. Defaults to True,
            which is the correct relation.

    Returns:
        The value ``call - put`` should equal, in CCY2 pips.
    """
    fwd = forward(spot, T, r_ccy1, r_ccy2)
    gap = fwd - strike
    return np.exp(-r_ccy2 * T) * gap if discounted else gap


# ---------------------------------------------------------------------------
# Closed-form greeks (Practical C, Task C)
# ---------------------------------------------------------------------------

def delta_closed_form(
    option_type: OptionType,
    spot: float,
    strike: float,
    T: float,
    r_ccy1: float,
    r_ccy2: float,
    sigma: float,
) -> float:
    """Spot delta by closed form, as a fraction of CCY1 notional (Practical C).

    ``delta_call = exp(-r1 * T) * N(d1)``
    ``delta_put  = exp(-r1 * T) * [N(d1) - 1]``

    Sign convention: the put delta returned here is the **true, negative** value. The
    market quotes put deltas as positive numbers - a "ten delta put" has -10% delta -
    but every formula in this package takes the signed value. ``fxds.smile`` depends
    on that; see its docstring.

    The two profiles differ by exactly ``exp(-r1 * T)``, which is put-call parity in
    greek terms (Ch. 6): a call becomes a put by selling the forward.

    Args:
        option_type: Call or put, on CCY1.
        spot: Current spot.
        strike: Strike.
        T: Time to expiry in years.
        r_ccy1: Continuously compounded CCY1 rate.
        r_ccy2: Continuously compounded CCY2 rate.
        sigma: Implied volatility as a decimal.

    Returns:
        Delta as a decimal fraction of CCY1 notional. Positive for calls, negative
        for puts.
    """
    T, sigma = _clamp(T, sigma)
    d1, _ = d1_d2(spot, strike, T, r_ccy1, r_ccy2, sigma)
    df_ccy1 = np.exp(-r_ccy1 * T)

    if option_type is OptionType.CALL:
        return df_ccy1 * norm.cdf(d1)
    return df_ccy1 * (norm.cdf(d1) - 1.0)


def vega_closed_form(
    spot: float,
    strike: float,
    T: float,
    r_ccy1: float,
    r_ccy2: float,
    sigma: float,
) -> float:
    """Raw vega by closed form (Practical C, Task C).

    ``vega = S * exp(-r1 * T) * n(d1) * sqrt(T)``

    where ``n`` is the standard normal density. Calls and puts have identical vega -
    put-call parity again, since a forward has no volatility exposure (Ch. 6).

    This is the raw derivative, in CCY2 pips per unit change in volatility. For the
    number a trader would quote, pass it through
    :func:`fxds.conventions.vega_to_market_terms`, or call :func:`vega_market` below.

    Args:
        spot: Current spot.
        strike: Strike.
        T: Time to expiry in years.
        r_ccy1: Continuously compounded CCY1 rate.
        r_ccy2: Continuously compounded CCY2 rate.
        sigma: Implied volatility as a decimal.

    Returns:
        Raw vega, CCY2 pips per 1.0 change in volatility.
    """
    T, sigma = _clamp(T, sigma)
    d1, _ = d1_d2(spot, strike, T, r_ccy1, r_ccy2, sigma)
    return spot * np.exp(-r_ccy1 * T) * norm.pdf(d1) * np.sqrt(T)


def vega_market(
    spot: float,
    strike: float,
    T: float,
    r_ccy1: float,
    r_ccy2: float,
    sigma: float,
) -> float:
    """Vega in market quotation terms (Practical C, Task C).

    In CCY1 terms and per 1% volatility move - the number a trader says out loud.

    Returns:
        Vega as a decimal fraction of CCY1 notional per 1% volatility move.

    Examples:
        The acceptance test - "a shade under 0.40%":

        >>> round(float(vega_market(1.0, 1.0, 1.0, 0.0, 0.0, 0.10)), 5)
        0.00398
    """
    return vega_to_market_terms(
        vega_closed_form(spot, strike, T, r_ccy1, r_ccy2, sigma), spot
    )


def gamma_closed_form(
    spot: float,
    strike: float,
    T: float,
    r_ccy1: float,
    r_ccy2: float,
    sigma: float,
) -> float:
    """Gamma by closed form (Ch. 6).

    ``gamma = exp(-r1 * T) * n(d1) / (S * sigma * sqrt(T))``

    The rate of change of delta with spot, so the gradient of the delta-versus-spot
    profile. Calls and puts share it, for the same put-call parity reason as vega.
    Not asked for by Practical C - the practical stops at first-order greeks - but
    Chapter 6 defines it and Task D asks you to notice that the gradient of the delta
    chart *is* gamma, so it is worth having to check that claim directly.

    Args:
        spot: Current spot.
        strike: Strike.
        T: Time to expiry in years.
        r_ccy1: Continuously compounded CCY1 rate.
        r_ccy2: Continuously compounded CCY2 rate.
        sigma: Implied volatility as a decimal.

    Returns:
        Gamma: change in delta per unit change in spot.
    """
    T, sigma = _clamp(T, sigma)
    d1, _ = d1_d2(spot, strike, T, r_ccy1, r_ccy2, sigma)
    return np.exp(-r_ccy1 * T) * norm.pdf(d1) / (spot * sigma * np.sqrt(T))


# ---------------------------------------------------------------------------
# Finite-difference greeks (Practical C, Task C)
# ---------------------------------------------------------------------------

def delta_finite_difference(
    option_type: OptionType,
    spot: float,
    strike: float,
    T: float,
    r_ccy1: float,
    r_ccy2: float,
    sigma: float,
    spot_flex: float = 1e-6,
) -> float:
    """Spot delta by central finite difference (Practical C, Task C).

    Bump spot up and down by ``spot_flex``, reprice both times, and divide the price
    change by the total spot change:

    ``delta ~ [P(S + h) - P(S - h)] / (2h)``

    The closed form is faster, but it is not always available - notably for exotics.
    The finite difference is slower and applies to anything you can price. That
    tradeoff is the reason Practical C asks for both.

    On ``spot_flex``: smaller is more accurate until it isn't. Too large and the
    second-order curvature of the price shows up as truncation error; too small and
    the two prices differ in their last few floating-point digits and the subtraction
    loses precision catastrophically. The book suggests starting at 1e-6 and testing
    both directions; ``tests/test_blackscholes.py`` sweeps it and the notebook plots
    the resulting U-shaped error curve.

    Args:
        option_type: Call or put, on CCY1.
        spot: Current spot.
        strike: Strike.
        T: Time to expiry in years.
        r_ccy1: Continuously compounded CCY1 rate.
        r_ccy2: Continuously compounded CCY2 rate.
        sigma: Implied volatility as a decimal.
        spot_flex: Size of the spot bump. Defaults to 1e-6.

    Returns:
        Delta as a decimal fraction of CCY1 notional.

    Raises:
        ValueError: If ``spot_flex`` is not positive.
    """
    if spot_flex <= 0:
        raise ValueError(f"Spot flex must be positive, got {spot_flex}")

    up = price(option_type, spot + spot_flex, strike, T, r_ccy1, r_ccy2, sigma)
    down = price(option_type, spot - spot_flex, strike, T, r_ccy1, r_ccy2, sigma)
    return (up - down) / (2 * spot_flex)


def vega_finite_difference(
    option_type: OptionType,
    spot: float,
    strike: float,
    T: float,
    r_ccy1: float,
    r_ccy2: float,
    sigma: float,
    vol_flex: float = 1e-6,
) -> float:
    """Vega by central finite difference, in market terms (Practical C, Task C).

    Bump volatility up and down, reprice, take the central difference, then apply the
    market convention - into CCY1 terms and per 1% volatility move. The book's VBA
    folds the ``0.01 / S`` scaling into this function, so this returns the market
    number directly rather than the raw derivative.

    Args:
        option_type: Call or put, on CCY1.
        spot: Current spot.
        strike: Strike.
        T: Time to expiry in years.
        r_ccy1: Continuously compounded CCY1 rate.
        r_ccy2: Continuously compounded CCY2 rate.
        sigma: Implied volatility as a decimal.
        vol_flex: Size of the volatility bump. Defaults to 1e-6.

    Returns:
        Vega as a decimal fraction of CCY1 notional per 1% volatility move.

    Raises:
        ValueError: If ``vol_flex`` is not positive.
    """
    if vol_flex <= 0:
        raise ValueError(f"Vol flex must be positive, got {vol_flex}")

    up = price(option_type, spot, strike, T, r_ccy1, r_ccy2, sigma + vol_flex)
    down = price(option_type, spot, strike, T, r_ccy1, r_ccy2, sigma - vol_flex)
    return vega_to_market_terms((up - down) / (2 * vol_flex), spot)
