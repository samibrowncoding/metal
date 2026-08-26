"""Terminal spot distribution and the integration pricer - Practical B (Ch. 5).

Implements Practical B: build the log-normal terminal spot distribution across plus
or minus five standard deviations, attach a payoff that depends only on spot at
maturity, and integrate the two together to get the option value.

This is the slow, general route to a price: it works for any payoff that depends only
on the terminal spot, no matter how awkward. Practical C's closed form is the fast,
special-case route. That the two agree is the headline cross-validation test of this
repository - see ``tests/test_cross_validation.py``.

Prices come out in CCY2 pips unless a function says otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd
from scipy.stats import norm

from .conventions import OptionType, ccy2_pips_to_ccy1_pct

# Practical B, Task A, Step 1: the book steps from -5 to +5 standard deviations in
# increments of 0.1. Under a normal distribution that range covers essentially all
# theoretical returns - beyond five sigma there is about 6e-7 of probability left in
# both tails combined.
DEFAULT_SD_RANGE = 5.0
DEFAULT_SD_STEP = 0.1


# ---------------------------------------------------------------------------
# Task A - the terminal spot distribution
# ---------------------------------------------------------------------------

def terminal_distribution(
    spot: float,
    T: float,
    r_ccy1: float,
    r_ccy2: float,
    sigma: float,
    sd_range: float = DEFAULT_SD_RANGE,
    sd_step: float = DEFAULT_SD_STEP,
) -> pd.DataFrame:
    """Build the terminal spot distribution (Practical B, Task A).

    Under the log-normal dynamics of Chapter 5, the log return to expiry is normally
    distributed with

    ``mu = (r2 - r1 - sigma^2 / 2) * T``       (expected log return)
    ``sd = sigma * sqrt(T)``                   (standard deviation)

    The ``-sigma^2 / 2`` is the Ito correction that falls out of solving the SDE. For
    each point ``X`` standard deviations from the mean:

    ``return_level = mu + X * sd``
    ``spot_level   = S * exp(return_level)``

    The bucket probability is the difference of two cumulative normals. **Row
    alignment matters here and is easy to get wrong**: the probability on row ``i``
    is the probability of finishing between ``spot_level[i]`` and
    ``spot_level[i + 1]``, so it belongs to the interval running to the *next* row.
    The final row therefore has no bucket, and its probability is NaN.

    Args:
        spot: Current spot, CCY2 per CCY1. Must be positive.
        T: Time to expiry in years. Must be positive.
        r_ccy1: Continuously compounded CCY1 rate.
        r_ccy2: Continuously compounded CCY2 rate.
        sigma: Implied volatility as a decimal. Must be positive.
        sd_range: How many standard deviations to span each side. Defaults to 5.
        sd_step: Step size in standard deviations. Defaults to 0.1.

    Returns:
        A DataFrame with one row per grid point and columns:

        * ``sd`` - position in standard deviations
        * ``return_level`` - the log return at that point
        * ``spot_level`` - the corresponding terminal spot
        * ``probability`` - probability of finishing in the bucket between this row's
          spot level and the next one's. NaN on the last row.

    Raises:
        ValueError: If spot, T or sigma is not positive, or the grid parameters are
            not positive.
    """
    if spot <= 0:
        raise ValueError(f"Spot must be positive, got {spot}")
    if T <= 0:
        raise ValueError(f"Time to expiry must be positive, got {T}")
    if sigma <= 0:
        raise ValueError(f"Volatility must be positive, got {sigma}")
    if sd_range <= 0 or sd_step <= 0:
        raise ValueError("sd_range and sd_step must both be positive")

    mu = (r_ccy2 - r_ccy1 - sigma**2 / 2) * T
    sd = sigma * np.sqrt(T)

    # Build the grid inclusive of the upper bound. Adding a half-step to the stop
    # guards against the endpoint being dropped by floating-point error.
    sd_grid = np.arange(-sd_range, sd_range + sd_step / 2, sd_step)

    return_level = mu + sd_grid * sd
    spot_level = spot * np.exp(return_level)

    # Probability of landing between this grid point and the next, as the difference
    # of two cumulative standard normals. The last row bounds no bucket.
    cumulative = norm.cdf(sd_grid)
    probability = np.full_like(sd_grid, np.nan)
    probability[:-1] = np.diff(cumulative)

    return pd.DataFrame(
        {
            "sd": sd_grid,
            "return_level": return_level,
            "spot_level": spot_level,
            "probability": probability,
        }
    )


# ---------------------------------------------------------------------------
# Task B - payoffs
# ---------------------------------------------------------------------------

PayoffFn = Callable[[np.ndarray], np.ndarray]
"""A payoff as a function of terminal spot, vectorised over a numpy array.

All payoffs return CCY2 pips - CCY2 per one CCY1 - which is what makes them directly
comparable with the prices out of ``fxds.blackscholes``.
"""


def long_forward_payoff(strike: float) -> PayoffFn:
    """Payoff of a long forward struck at ``strike``: ``S_T - K`` (Practical B)."""
    return lambda s: s - strike


def short_forward_payoff(strike: float) -> PayoffFn:
    """Payoff of a short forward struck at ``strike``: ``K - S_T`` (Practical B)."""
    return lambda s: strike - s


def call_payoff(strike: float) -> PayoffFn:
    """Payoff of a vanilla CCY1 call: ``max(S_T - K, 0)`` (Practical B)."""
    return lambda s: np.maximum(s - strike, 0.0)


def put_payoff(strike: float) -> PayoffFn:
    """Payoff of a vanilla CCY1 put: ``max(K - S_T, 0)`` (Practical B)."""
    return lambda s: np.maximum(strike - s, 0.0)


def vanilla_payoff(option_type: OptionType, strike: float) -> PayoffFn:
    """Pick the vanilla payoff matching an :class:`OptionType`."""
    return call_payoff(strike) if option_type is OptionType.CALL else put_payoff(strike)


# ---------------------------------------------------------------------------
# Task B - the integration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class IntegrationResult:
    """What the numerical integration produced.

    Attributes:
        value_ccy2_pips: Present-valued option price, CCY2 per one CCY1. Directly
            comparable with :func:`fxds.blackscholes.price`.
        value_ccy1_pct: The same price as a decimal fraction of CCY1 notional
            (0.0399 means 3.99 CCY1%).
        undiscounted_ccy2_pips: The probability-weighted payoff *at maturity*, before
            the CCY2 discount factor is applied. Kept because seeing the discounting
            step separately is part of the point.
        total_probability: Sum of the bucket probabilities. Should be just under 1 -
            the shortfall is the tail beyond the grid, and it is worth looking at.
        table: The full working table, one row per grid point, so the notebook can
            plot the density and the payoff on the same axes.
    """

    value_ccy2_pips: float
    value_ccy1_pct: float
    undiscounted_ccy2_pips: float
    total_probability: float
    table: pd.DataFrame


def integrate_payoff(
    payoff_fn: PayoffFn,
    spot: float,
    T: float,
    r_ccy1: float,
    r_ccy2: float,
    sigma: float,
    sd_range: float = DEFAULT_SD_RANGE,
    sd_step: float = DEFAULT_SD_STEP,
) -> IntegrationResult:
    """Price any terminal-spot payoff by integrating it against the distribution.

    Practical B, Task B. The integration multiplies each bucket's probability by the
    **average payoff across that bucket** - the mean of the payoff at the two
    bounding spot levels - and sums:

    ``value_at_maturity = sum_i prob[i] * (payoff[i] + payoff[i+1]) / 2``

    Averaging across the bucket rather than taking one endpoint is what makes this a
    trapezoidal rule rather than a left-hand Riemann sum, and it is why the
    convergence against the closed form is as good as it is at only 101 points.

    The result is then present valued with the CCY2 discount factor and converted to
    CCY1% by dividing by spot, exactly as the practical lays out.

    Args:
        payoff_fn: Payoff as a function of terminal spot, returning CCY2 pips.
        spot: Current spot, CCY2 per CCY1.
        T: Time to expiry in years.
        r_ccy1: Continuously compounded CCY1 rate.
        r_ccy2: Continuously compounded CCY2 rate.
        sigma: Implied volatility as a decimal.
        sd_range: How many standard deviations to span each side. Defaults to 5.
        sd_step: Step size in standard deviations. Defaults to 0.1.

    Returns:
        An :class:`IntegrationResult` carrying the price and the working table.
    """
    table = terminal_distribution(
        spot, T, r_ccy1, r_ccy2, sigma, sd_range=sd_range, sd_step=sd_step
    )

    table["payoff"] = payoff_fn(table["spot_level"].to_numpy())

    # Average payoff across each bucket: this row's payoff and the next row's.
    average_payoff = (table["payoff"] + table["payoff"].shift(-1)) / 2
    table["average_payoff"] = average_payoff
    table["weighted_payoff"] = table["probability"] * average_payoff

    undiscounted = float(table["weighted_payoff"].sum())
    discount_factor = float(np.exp(-r_ccy2 * T))
    value_ccy2_pips = undiscounted * discount_factor

    return IntegrationResult(
        value_ccy2_pips=value_ccy2_pips,
        value_ccy1_pct=ccy2_pips_to_ccy1_pct(value_ccy2_pips, spot),
        undiscounted_ccy2_pips=undiscounted,
        total_probability=float(table["probability"].sum()),
        table=table,
    )


def price_vanilla(
    option_type: OptionType,
    spot: float,
    strike: float,
    T: float,
    r_ccy1: float,
    r_ccy2: float,
    sigma: float,
    sd_range: float = DEFAULT_SD_RANGE,
    sd_step: float = DEFAULT_SD_STEP,
) -> IntegrationResult:
    """Price a vanilla by numerical integration (Practical B).

    Convenience wrapper over :func:`integrate_payoff`. The signature deliberately
    mirrors :func:`fxds.blackscholes.price` so the two can be compared directly.

    Args:
        option_type: Call or put, on CCY1.
        spot: Current spot.
        strike: Strike.
        T: Time to expiry in years.
        r_ccy1: Continuously compounded CCY1 rate.
        r_ccy2: Continuously compounded CCY2 rate.
        sigma: Implied volatility as a decimal.
        sd_range: How many standard deviations to span each side.
        sd_step: Step size in standard deviations.

    Returns:
        An :class:`IntegrationResult`.

    Examples:
        Practical B, Test 2 - very slightly under 4.00 CCY1%:

        >>> from fxds.conventions import OptionType
        >>> r = price_vanilla(OptionType.CALL, 100.0, 100.0, 1.0, 0.0, 0.0, 0.10)
        >>> round(float(r.value_ccy1_pct) * 100, 4)   # very slightly under 4.00
        3.9969
    """
    return integrate_payoff(
        vanilla_payoff(option_type, strike),
        spot,
        T,
        r_ccy1,
        r_ccy2,
        sigma,
        sd_range=sd_range,
        sd_step=sd_step,
    )
