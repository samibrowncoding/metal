"""The Malz volatility smile and strike-from-delta - Practical F (Ch. 12).

Implements Practical F: the Malz (1997) smile parameterisation in delta space, put
delta from strike and its inversion, and the strike placement experiments that show
what the ATM, risk reversal and butterfly each do to where strikes land.

Sign convention, which trips everyone up at least once: the put delta used inside the
Black-Scholes formulas here is the true, negative value. The market quotes put deltas
as positive numbers ("ten delta put" means -10%), and the Malz formula itself takes
that positive quoted delta. Each function's docstring says which it expects.

Simplification carried throughout: this is the outright-delta smile, not the broker
fly the interbank market actually trades. See Chapter 12 and ``notes/deviations.md``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import norm

from .blackscholes import _clamp

# Practical F, Task D: there is no finite strike at 0% or 100% delta - the inverse
# normal diverges - so the book substitutes 0.01% and 99.99% when sweeping the smile.
DELTA_FLOOR = 0.0001
DELTA_CAP = 0.9999


def max_attainable_put_delta(r_ccy1: float, T: float) -> float:
    """The largest positive quoted put delta that exists, given a CCY1 rate.

    Not an implementation limit - a property of the formula, and one the book's
    zero-rate examples never surface.

    Since ``delta_put = exp(-r1*T) * [N(d1) - 1]`` and ``N(d1) - 1`` lies strictly in
    ``(-1, 0)``, the signed put delta is bounded below by ``-exp(-r1*T)``. So with a
    CCY1 rate of 10% and a year to expiry there is **no such thing** as a 95 delta
    put: the deepest attainable is about 90.5 delta.

    The same discount factor is why ``delta_call = exp(-r1*T) * N(d1)`` cannot reach
    100% either - a deep in-the-money call is worth slightly less than the forward
    because the CCY1 leg earns interest you do not receive until delivery.

    Args:
        r_ccy1: Continuously compounded CCY1 rate.
        T: Time to expiry in years.

    Returns:
        The supremum of the attainable positive quoted put delta. Deltas must be
        strictly below this.
    """
    return float(np.exp(-r_ccy1 * T))


def _attainable_delta_grid(r_ccy1: float, T: float, points: int) -> np.ndarray:
    """A delta grid clipped to what the CCY1 rate actually allows."""
    cap = min(DELTA_CAP, max_attainable_put_delta(r_ccy1, T) * (1 - 1e-6))
    if cap <= DELTA_FLOOR:
        raise ValueError(
            f"No attainable put deltas: exp(-r1*T) = "
            f"{max_attainable_put_delta(r_ccy1, T):.6g} is at or below the delta "
            f"floor. The CCY1 rate is too high for this maturity."
        )
    return np.linspace(DELTA_FLOOR, cap, points)


@dataclass(frozen=True)
class MalzSmile:
    """The Malz (1997) volatility smile (Practical F, Task A).

    ``sigma(X) = sigma_ATM + 2 * RR25 * (X - 0.5) + 16 * fly25 * (X - 0.5)^2``

    where ``X`` is the **positive quoted put delta** between 0 and 1.

    In words: the ATM sets the level, the risk reversal tilts the smile one way or
    the other, and the butterfly lifts both wings symmetrically. Three market
    instruments, three degrees of freedom, one quadratic.

    The formula reproduces the standard approximations exactly:

    * ``X = 0.50`` gives ``sigma_ATM``
    * ``X = 0.25`` gives ``sigma_ATM + fly25 - RR25/2``  (the 25 delta put)
    * ``X = 0.75`` gives ``sigma_ATM + fly25 + RR25/2``  (the 25 delta call)

    **Known limitation, from Chapter 12.** Substituting 10% and 90% gives
    ``RR10 = 1.6 * RR25``. The market value is usually nearer **1.8**, so this
    parameterisation systematically understates the 10 delta skew. That is a property
    of the functional form, not a bug in the implementation.

    Args:
        atm: ATM implied volatility, as a decimal.
        rr25: 25 delta risk reversal, as a decimal. Positive means topside strikes
            are richer; negative means downside strikes are richer.
        fly25: 25 delta butterfly, as a decimal. Positive lifts both wings.

    Raises:
        ValueError: If the ATM volatility is not positive.
    """

    atm: float
    rr25: float = 0.0
    fly25: float = 0.0

    def __post_init__(self) -> None:
        if self.atm <= 0:
            raise ValueError(f"ATM volatility must be positive, got {self.atm}")

    def volatility(self, put_delta: float | np.ndarray) -> float | np.ndarray:
        """Implied volatility at a given positive quoted put delta.

        Args:
            put_delta: Positive quoted put delta, between 0 and 1. **Not** the signed
                delta - pass 0.25 for a 25 delta put, not -0.25.

        Returns:
            Implied volatility as a decimal.
        """
        x = np.asarray(put_delta, dtype=float)
        offset = x - 0.5
        result = self.atm + 2 * self.rr25 * offset + 16 * self.fly25 * offset**2
        return float(result) if np.isscalar(put_delta) or result.ndim == 0 else result

    @property
    def call_25d(self) -> float:
        """Implied volatility of the 25 delta call (75% put delta)."""
        return self.atm + self.fly25 + 0.5 * self.rr25

    @property
    def put_25d(self) -> float:
        """Implied volatility of the 25 delta put."""
        return self.atm + self.fly25 - 0.5 * self.rr25

    @property
    def call_10d(self) -> float:
        """Implied volatility of the 10 delta call (90% put delta)."""
        return self.atm + 2.56 * self.fly25 + 0.8 * self.rr25

    @property
    def put_10d(self) -> float:
        """Implied volatility of the 10 delta put."""
        return self.atm + 2.56 * self.fly25 - 0.8 * self.rr25

    @property
    def rr10_implied(self) -> float:
        """The 10 delta risk reversal this model implies: ``1.6 * RR25`` (Ch. 12).

        Chapter 12 notes the market multiplier is usually around 1.8, so this is a
        touch low. Worth knowing before quoting a 10 delta off a 25 delta model.
        """
        return self.call_10d - self.put_10d

    def curve(self, points: int = 199) -> pd.DataFrame:
        """The smile swept across the delta range (Practical F, Task B).

        Args:
            points: How many points to sample between the delta floor and cap.

        Returns:
            A DataFrame of put delta and implied volatility.
        """
        deltas = np.linspace(DELTA_FLOOR, DELTA_CAP, points)
        return pd.DataFrame({"put_delta": deltas, "volatility": self.volatility(deltas)})


# ---------------------------------------------------------------------------
# Task C - strike from delta, and back
# ---------------------------------------------------------------------------

def put_delta_from_strike(
    spot: float, strike: float, T: float, r_ccy1: float, r_ccy2: float, sigma: float
) -> float:
    """Signed put delta for a strike (Practical F, Task C).

    ``delta_put = exp(-r1 * T) * [N(d1) - 1]``

    Returns the **true, negative** value. The market would quote this as a positive
    number with the sign dropped.

    Args:
        spot: Current spot.
        strike: Strike.
        T: Time to expiry in years.
        r_ccy1: Continuously compounded CCY1 rate.
        r_ccy2: Continuously compounded CCY2 rate.
        sigma: Implied volatility as a decimal.

    Returns:
        The signed put delta, between -1 and 0.
    """
    T, sigma = _clamp(T, sigma)
    d1 = (np.log(spot / strike) + (r_ccy2 - r_ccy1 + sigma**2 / 2) * T) / (sigma * np.sqrt(T))
    return float(np.exp(-r_ccy1 * T) * (norm.cdf(d1) - 1.0))


def strike_from_put_delta(
    spot: float, put_delta: float, T: float, r_ccy1: float, r_ccy2: float, sigma: float
) -> float:
    """Strike for a given signed put delta (Practical F, Task C).

    The inversion of :func:`put_delta_from_strike`:

    ``K = S / exp( N^-1( e^(r1*T) * delta_put + 1 ) * sigma*sqrt(T) - (r2 - r1 + sigma^2/2)*T )``

    Split into three parts as the book does, because it is easier to follow and to
    debug that way.

    **The delta must be the true, negative value.** Pass -0.25 for a 25 delta put, not
    0.25. Passing the positive quoted delta silently produces a strike on the wrong
    side of the forward, which is the classic way to get this wrong - the book flags
    it twice for good reason.

    Args:
        spot: Current spot.
        put_delta: **Signed** put delta, strictly between -1 and 0.
        T: Time to expiry in years.
        r_ccy1: Continuously compounded CCY1 rate.
        r_ccy2: Continuously compounded CCY2 rate.
        sigma: Implied volatility as a decimal.

    Returns:
        The strike.

    Raises:
        ValueError: If ``put_delta`` is not strictly between -1 and 0, or if the
            discount factor pushes ``part1`` outside the domain of the inverse normal.

    Examples:
        >>> k = strike_from_put_delta(1.30, -0.25, 1.0, 0.02, 0.05, 0.10)
        >>> round(k, 4)
        1.2605
    """
    if not -1.0 < put_delta < 0.0:
        raise ValueError(
            f"put_delta must be the signed value strictly between -1 and 0, got "
            f"{put_delta}. For a 25 delta put pass -0.25, not 0.25."
        )

    T, sigma = _clamp(T, sigma)

    part1 = np.exp(r_ccy1 * T) * put_delta + 1.0
    if not 0.0 < part1 < 1.0:
        raise ValueError(
            f"exp(r1*T)*delta + 1 = {part1:.6g}, which is outside (0, 1) and has no "
            f"inverse normal. The CCY1 rate and delta combination is not attainable."
        )

    part2 = sigma * np.sqrt(T)
    part3 = (r_ccy2 - r_ccy1 + 0.5 * sigma**2) * T
    return float(spot / np.exp(norm.ppf(part1) * part2 - part3))


# ---------------------------------------------------------------------------
# Task E - strike placement
# ---------------------------------------------------------------------------

STANDARD_PUT_DELTAS: tuple[float, ...] = (0.10, 0.25, 0.50, 0.75, 0.90)
"""The five strikes Practical F, Task E asks for, as positive quoted put deltas.

In market language these are the 10 delta put, 25 delta put, ATM, 25 delta call and
10 delta call - since a 75% put delta is a 25% call delta.
"""


def strike_placement(
    smile: MalzSmile,
    spot: float,
    T: float,
    r_ccy1: float,
    r_ccy2: float,
    put_deltas: tuple[float, ...] = STANDARD_PUT_DELTAS,
) -> pd.DataFrame:
    """Solve for the strikes at a set of deltas, on the smile (Practical F, Task E).

    **On whether this iterates: it does not, and it is worth being explicit about
    why.** The relationship looks circular - the volatility depends on the delta,
    which depends on the strike, which depends on the volatility. In a smile quoted in
    *strike* space it genuinely would be, and you would need a root find.

    But the Malz smile is quoted in **delta space**. Given a delta, the volatility is
    known immediately from the quadratic, with no strike involved. So the calculation
    is a straight two-step: delta to volatility, then delta and volatility to strike.
    The circularity is an artefact of the parameterisation, and Malz picks the one
    where it does not arise.

    Args:
        smile: The smile to place strikes on.
        spot: Current spot.
        T: Time to expiry in years.
        r_ccy1: Continuously compounded CCY1 rate.
        r_ccy2: Continuously compounded CCY2 rate.
        put_deltas: Positive quoted put deltas to solve for.

    Returns:
        A DataFrame with, per delta: the smile volatility, the strike, the strike's
        distance from the ATM strike in percent, and a market-style label. Deltas the
        CCY1 rate makes unattainable are omitted - see :func:`max_attainable_put_delta`.
    """
    cap = max_attainable_put_delta(r_ccy1, T)
    rows = []
    atm_strike = None

    for x in put_deltas:
        if x >= cap:
            # This delta does not exist at this CCY1 rate and maturity - see
            # max_attainable_put_delta. Skipping is more useful than raising,
            # because the rest of the placement is still perfectly valid.
            continue
        vol = float(smile.volatility(x))
        strike = strike_from_put_delta(spot, -x, T, r_ccy1, r_ccy2, vol)
        if abs(x - 0.5) < 1e-12:
            atm_strike = strike
        # Market naming: a put delta above 50% is quoted as the equivalent call.
        label = f"{x:.0%} put" if x <= 0.5 else f"{1 - x:.0%} call"
        rows.append({"put_delta": x, "label": label, "volatility": vol, "strike": strike})

    frame = pd.DataFrame(rows)
    if atm_strike is None:
        atm_strike = strike_from_put_delta(
            spot, -0.5, T, r_ccy1, r_ccy2, float(smile.volatility(0.5))
        )
    frame["pct_from_atm"] = (frame["strike"] / atm_strike - 1.0) * 100.0
    return frame


def smile_by_strike(
    smile: MalzSmile,
    spot: float,
    T: float,
    r_ccy1: float,
    r_ccy2: float,
    points: int = 199,
) -> pd.DataFrame:
    """The smile expressed against strike rather than delta (Practical F, Task D).

    Args:
        smile: The smile.
        spot: Current spot.
        T: Time to expiry in years.
        r_ccy1: Continuously compounded CCY1 rate.
        r_ccy2: Continuously compounded CCY2 rate.
        points: How many points to sample.

    Returns:
        A DataFrame of put delta, strike and implied volatility, ascending in strike.

    Raises:
        ValueError: If the CCY1 rate is so high for this maturity that no delta in
            the usable range is attainable. See :func:`max_attainable_put_delta`.
    """
    # The sweep is clipped to what the CCY1 rate allows rather than running to
    # DELTA_CAP blindly: with a positive CCY1 rate the deepest put delta that exists
    # is exp(-r1*T), not 100%.
    deltas = _attainable_delta_grid(r_ccy1, T, points)
    rows = []
    for x in deltas:
        vol = float(smile.volatility(x))
        rows.append({
            "put_delta": x,
            "strike": strike_from_put_delta(spot, -x, T, r_ccy1, r_ccy2, vol),
            "volatility": vol,
        })
    return pd.DataFrame(rows).sort_values("strike").reset_index(drop=True)
