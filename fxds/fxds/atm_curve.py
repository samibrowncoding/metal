"""ATM curve construction: interpolation, model and day weights - Practical E (Ch. 11).

Implements Practical E:

* Task A - linear-in-volatility and linear-in-total-variance interpolation between
  market tenors, with explicit errors outside the quoted range.
* Task B - the parametric curve sigma_T = sigma_short + (sigma_long - sigma_short) *
  (1 - exp(-lambda * T)), plus a least-squares calibration that goes beyond the book.
* Task C - day weights, economic versus calendar time, the weekend saw-tooth, event
  weighting, and daily forward variance with a check for the negative-forward-variance
  arbitrage.

Variance, not volatility, is the quantity that has to stay well behaved: it must be
non-negative and it is additive across time. Volatility is neither.

    variance(T) = sigma^2 * T

Those two properties are why every curve in this module is built or checked in
variance terms even when the answer is quoted as a volatility.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum

import numpy as np
import pandas as pd
from scipy.optimize import least_squares

DAYS_PER_YEAR = 365.0
"""Day count used throughout Part II.

Practical E divides by 365 everywhere without discussing ACT/365 versus ACT/360 or a
business-day count. Kept as the book has it; flagged in ``notes/deviations.md``
because it is a real convention choice, not a neutral default.
"""


class Interpolation(str, Enum):
    """How to interpolate between market tenors (Practical E, Task A).

    Neither method is right. Chapter 11 sets out the tradeoff plainly:

    * ``LINEAR_VOLATILITY`` produces intuitively shaped curves but **does not
      guarantee non-negative forward variance**. The book's counterexample: a flat
      20% curve to 1yr with 15% at 2yr gives variance 0.04 at 1yr, 0.046 at 18mth and
      0.045 at 2yr - variance falling, from perfectly valid inputs.
    * ``LINEAR_VARIANCE`` guarantees non-negative forward variance given valid inputs,
      but produces odd volatility shapes - a sharp rise then a flattening between each
      pair of tenors, and daily variance that jumps discontinuously at every tenor
      date. There is no reason the day before the 3mth tenor should differ from the
      day after.

    Real desks combine both, building in variance terms with more sophisticated
    control of how daily variance evolves. This module gives you the two pure cases so
    you can see why neither survives on its own.
    """

    LINEAR_VOLATILITY = "linear_volatility"
    LINEAR_VARIANCE = "linear_variance"


class CurveRangeError(ValueError):
    """Raised when a query date falls outside the quoted tenor range.

    The book returns -1. A magic sentinel that is also a plausible volatility will
    propagate silently into a variance and produce something that looks like a number,
    so this raises instead. See ``notes/deviations.md``.
    """


# ---------------------------------------------------------------------------
# Variance helpers (Ch. 11)
# ---------------------------------------------------------------------------

def variance(volatility: float, T: float) -> float:
    """Total variance to time T: ``sigma^2 * T`` (Ch. 11).

    Args:
        volatility: ATM implied volatility as a decimal.
        T: Time in years.

    Returns:
        Total variance.
    """
    return volatility**2 * T


def volatility_from_variance(total_variance: float, T: float) -> float:
    """Recover volatility from total variance and time (Ch. 11).

    Args:
        total_variance: Total variance to time T.
        T: Time in years. Must be positive.

    Returns:
        The implied volatility.

    Raises:
        ValueError: If ``T`` is not positive, or the variance is negative.
    """
    if T <= 0:
        raise ValueError(f"Time must be positive, got {T}")
    if total_variance < 0:
        raise ValueError(
            f"Total variance is negative ({total_variance}), which is not a "
            f"meaningful quantity. Something upstream has produced an arbitrage."
        )
    return float(np.sqrt(total_variance / T))


def forward_volatility(vol_1: float, T_1: float, vol_2: float, T_2: float) -> float:
    """Forward volatility between two future dates (Ch. 11).

    ``sigma_fwd = sqrt[ (sigma_2^2 * T_2 - sigma_1^2 * T_1) / (T_2 - T_1) ]``

    Straight out of variance being additive: the variance between T1 and T2 is the
    difference of the two total variances.

    Args:
        vol_1: ATM volatility to the nearer date.
        T_1: Time to the nearer date, in years.
        vol_2: ATM volatility to the further date.
        T_2: Time to the further date, in years. Must exceed ``T_1``.

    Returns:
        The forward volatility between the two dates.

    Raises:
        ValueError: If ``T_2`` does not exceed ``T_1``, or the forward variance is
            negative - which is a calendar arbitrage, not a rounding issue.

    Examples:
        Chapter 11's worked example: 6mth at 10.5%, 1yr at 11.7%.

        >>> round(forward_volatility(0.105, 0.5, 0.117, 1.0), 3)   # the book says 12.8%
        0.128
    """
    if T_2 <= T_1:
        raise ValueError(f"T_2 ({T_2}) must be greater than T_1 ({T_1})")

    forward_variance = variance(vol_2, T_2) - variance(vol_1, T_1)
    if forward_variance < 0:
        raise ValueError(
            f"Forward variance between {T_1}y and {T_2}y is negative "
            f"({forward_variance:.6g}). Variance must be non-decreasing in time - "
            f"this curve is arbitrageable."
        )
    return float(np.sqrt(forward_variance / (T_2 - T_1)))


# ---------------------------------------------------------------------------
# Task A - interpolation
# ---------------------------------------------------------------------------

def interpolate_volatility(
    T_low: float, T_high: float, vol_low: float, vol_high: float, T_query: float
) -> float:
    """Linear-in-volatility interpolation (Practical E, Task A).

    ``sigma(t) = sigma_low + (sigma_high - sigma_low) * (t - T_low) / (T_high - T_low)``

    Intuitive, and unsafe: it does not guarantee non-negative forward variance.
    """
    if T_high == T_low:
        return vol_low
    weight = (T_query - T_low) / (T_high - T_low)
    return vol_low + (vol_high - vol_low) * weight


def interpolate_variance(
    T_low: float, T_high: float, vol_low: float, vol_high: float, T_query: float
) -> float:
    """Linear-in-total-variance interpolation (Practical E, Task A).

    Interpolate the total variances, then convert back to a volatility using the
    query time. Safe against negative forward variance given valid inputs; produces
    volatility shapes that look wrong between tenors.

    Note the book's printed VBA assigns its result to the wrong function name - a
    transcription error, recorded in ``notes/deviations.md``.
    """
    if T_high == T_low:
        return vol_low
    var_low, var_high = variance(vol_low, T_low), variance(vol_high, T_high)
    weight = (T_query - T_low) / (T_high - T_low)
    query_variance = var_low + (var_high - var_low) * weight
    return volatility_from_variance(query_variance, T_query)


@dataclass
class ATMCurve:
    """An ATM curve defined at market tenors, interpolated in between (Task A).

    Args:
        horizon: The trade date, from which all times are measured.
        expiries: Expiry dates at the market tenors, ascending.
        volatilities: ATM volatility at each expiry, as decimals.
        method: Interpolation method.

    Raises:
        ValueError: If the inputs are mismatched, empty, unordered, or contain a
            non-positive volatility.
    """

    horizon: date
    expiries: list[date]
    volatilities: list[float]
    method: Interpolation = Interpolation.LINEAR_VARIANCE

    def __post_init__(self) -> None:
        if len(self.expiries) != len(self.volatilities):
            raise ValueError(
                f"Got {len(self.expiries)} expiries and "
                f"{len(self.volatilities)} volatilities; they must match."
            )
        if not self.expiries:
            raise ValueError("An ATM curve needs at least one tenor")
        if any(b <= a for a, b in zip(self.expiries, self.expiries[1:])):
            raise ValueError("Expiry dates must be strictly ascending")
        if self.expiries[0] <= self.horizon:
            raise ValueError(
                f"First expiry {self.expiries[0]} is not after the horizon {self.horizon}"
            )
        if any(v <= 0 for v in self.volatilities):
            raise ValueError("Every ATM volatility must be positive")

    def years_to(self, day: date) -> float:
        """Time from horizon to a date, in years on a 365 basis."""
        return (day - self.horizon).days / DAYS_PER_YEAR

    @property
    def times(self) -> list[float]:
        """Time to each market tenor expiry, in years."""
        return [self.years_to(e) for e in self.expiries]

    def volatility(self, query: date) -> float:
        """ATM volatility for any expiry date within the quoted range (Task A).

        The four cases Practical E asks you to test:

        1. Before the first tenor expiry - raises.
        2. After the last tenor expiry - raises.
        3. Exactly on a tenor expiry - returns that tenor's volatility.
        4. Between two tenors - interpolates.

        Args:
            query: The expiry date to price.

        Returns:
            The ATM volatility as a decimal.

        Raises:
            CurveRangeError: If the query date is outside the quoted range. The book
                returns -1; see the class docstring.
        """
        if query < self.expiries[0]:
            raise CurveRangeError(
                f"Query date {query} is before the first tenor expiry "
                f"{self.expiries[0]}. This curve does not extrapolate."
            )
        if query > self.expiries[-1]:
            raise CurveRangeError(
                f"Query date {query} is after the last tenor expiry "
                f"{self.expiries[-1]}. This curve does not extrapolate."
            )

        # Exact hit on a tenor.
        for expiry, vol in zip(self.expiries, self.volatilities):
            if query == expiry:
                return vol

        # Otherwise find the bracketing pair and interpolate.
        index = next(i for i, e in enumerate(self.expiries) if e > query)
        T_low, T_high = self.years_to(self.expiries[index - 1]), self.years_to(self.expiries[index])
        vol_low, vol_high = self.volatilities[index - 1], self.volatilities[index]
        T_query = self.years_to(query)

        if self.method is Interpolation.LINEAR_VOLATILITY:
            return interpolate_volatility(T_low, T_high, vol_low, vol_high, T_query)
        return interpolate_variance(T_low, T_high, vol_low, vol_high, T_query)

    def daily_curve(self, until: date | None = None) -> pd.DataFrame:
        """The curve at daily intervals, with variance alongside (Task A).

        Args:
            until: Last date to include. Defaults to the final tenor expiry.

        Returns:
            A DataFrame with the date, years to expiry, ATM volatility, total
            variance and daily forward variance.
        """
        end = until or self.expiries[-1]
        rows = []
        day = self.expiries[0]
        while day <= end:
            T = self.years_to(day)
            vol = self.volatility(day)
            rows.append({"date": day, "years": T, "atm_vol": vol,
                         "total_variance": variance(vol, T)})
            day += timedelta(days=1)

        frame = pd.DataFrame(rows)
        frame["daily_variance"] = frame["total_variance"].diff()
        return frame

    def has_negative_forward_variance(self, until: date | None = None) -> bool:
        """Whether the curve implies negative forward variance anywhere (Ch. 11).

        This is the check that catches the failure mode of linear-in-volatility
        interpolation. Negative forward variance is a **calendar arbitrage**: the
        variance to a later date is lower than to an earlier one, so you could sell
        the near option, buy the far one, and be short variance for free.
        """
        frame = self.daily_curve(until)
        return bool((frame["daily_variance"].dropna() < 0).any())


# ---------------------------------------------------------------------------
# Task B - the parametric model
# ---------------------------------------------------------------------------

@dataclass
class ParametricATMCurve:
    """The simple parametric ATM curve from Chapter 11 (Practical E, Task B).

    ``sigma_T = sigma_short + (sigma_long - sigma_short) * (1 - exp(-lambda * T))``

    The ``(1 - exp(-lambda T))`` factor runs from 0 to 1; higher ``lambda`` gets there
    faster. So the curve starts at ``sigma_short`` and decays toward ``sigma_long``.

    Chapter 11 is explicit that this exact form **would never be used in practice**
    because it can generate arbitrageable curves - there is nothing in it that
    enforces non-negative forward variance. It is here because it makes the shape of
    a term structure concrete, not because it is a good model.

    Args:
        sigma_short: Short-term ATM volatility, as a decimal.
        sigma_long: Long-term ATM volatility, as a decimal.
        speed: Lambda, the speed of reversion from short to long.
    """

    sigma_short: float
    sigma_long: float
    speed: float

    def __post_init__(self) -> None:
        if self.speed <= 0:
            raise ValueError(f"Speed must be positive, got {self.speed}")

    def volatility(self, T: float | np.ndarray) -> float | np.ndarray:
        """ATM volatility at time T in years."""
        return self.sigma_short + (self.sigma_long - self.sigma_short) * (
            1 - np.exp(-self.speed * np.asarray(T, dtype=float))
        )

    def curve(self, months: int = 24) -> pd.DataFrame:
        """The curve at monthly intervals (Practical E, Task B).

        The book plots at 1/12 intervals within its stylised framework.
        """
        T = np.arange(1, months + 1) / 12.0
        vols = self.volatility(T)
        return pd.DataFrame({"months": np.arange(1, months + 1), "years": T,
                             "atm_vol": vols, "total_variance": vols**2 * T})

    def has_negative_forward_variance(self, months: int = 24) -> bool:
        """Whether the fitted curve implies negative forward variance."""
        frame = self.curve(months)
        return bool((frame["total_variance"].diff().dropna() < 0).any())


@dataclass
class CalibrationResult:
    """The outcome of fitting the parametric curve to market tenors.

    Attributes:
        curve: The fitted curve.
        rmse: Root mean squared error in volatility points, as a decimal.
        max_error: Largest absolute error at any tenor, as a decimal.
        errors: Per-tenor fitted-minus-market errors.
        success: Whether the optimiser reported convergence.
    """

    curve: ParametricATMCurve
    rmse: float
    max_error: float
    errors: np.ndarray
    success: bool


def calibrate_parametric(
    times: list[float] | np.ndarray,
    volatilities: list[float] | np.ndarray,
    initial_guess: tuple[float, float, float] | None = None,
) -> CalibrationResult:
    """Least-squares fit of the parametric curve to market tenor volatilities.

    **Beyond the book.** Practical E fits the model by eye - set the three parameters
    and look at the chart. A least-squares fit with a reported error is more useful
    and shows immediately where the functional form cannot reach the market, which is
    itself informative: a large residual at one tenor is the same signal as the
    manual "override" Chapter 11 describes.

    Args:
        times: Times to each market tenor, in years.
        volatilities: Market ATM volatility at each tenor, as decimals.
        initial_guess: Starting ``(sigma_short, sigma_long, speed)``. Sensible
            defaults are derived from the data when omitted.

    Returns:
        A :class:`CalibrationResult`.

    Raises:
        ValueError: If the inputs are mismatched or there are fewer than three points
            to fit three parameters.
    """
    T = np.asarray(times, dtype=float)
    market = np.asarray(volatilities, dtype=float)

    if T.shape != market.shape:
        raise ValueError("times and volatilities must be the same length")
    if T.size < 3:
        raise ValueError(
            f"Need at least 3 tenors to fit 3 parameters, got {T.size}"
        )

    if initial_guess is None:
        initial_guess = (float(market[0]), float(market[-1]), 1.0)

    def residuals(params: np.ndarray) -> np.ndarray:
        short, long, speed = params
        fitted = short + (long - short) * (1 - np.exp(-speed * T))
        return fitted - market

    solution = least_squares(
        residuals,
        x0=np.array(initial_guess, dtype=float),
        bounds=([1e-6, 1e-6, 1e-6], [5.0, 5.0, 100.0]),
    )
    short, long, speed = solution.x
    errors = residuals(solution.x)

    return CalibrationResult(
        curve=ParametricATMCurve(float(short), float(long), float(speed)),
        rmse=float(np.sqrt(np.mean(errors**2))),
        max_error=float(np.max(np.abs(errors))),
        errors=errors,
        success=bool(solution.success),
    )


# ---------------------------------------------------------------------------
# Task C - day weights, economic time, events
# ---------------------------------------------------------------------------

# Practical E's day-weight lookup table. The book starts with every weekday at 1.0
# to show calendar and economic time coinciding, then sets the weekend to zero to
# produce the saw-tooth.
DEFAULT_DAY_WEIGHTS: dict[int, float] = {
    0: 1.0,  # Monday
    1: 1.0,
    2: 1.0,
    3: 1.0,
    4: 1.0,  # Friday
    5: 1.0,  # Saturday
    6: 1.0,  # Sunday
}

WEEKEND_ZERO_WEIGHTS: dict[int, float] = {**DEFAULT_DAY_WEIGHTS, 5: 0.0, 6: 0.0}
"""Weekday weights with the weekend at zero - the setting that produces the saw-tooth.

Chapter 11 notes that desks in practice assign a **small but non-zero** weekend
weight, because there is a real chance that weekend news gaps spot on the Monday
open. Exactly zero is the practical's simplification, kept here because the effect it
demonstrates is the point.
"""


@dataclass
class WeightedATMCurve:
    """A flat volatility with per-date weights on top (Practical E, Task C).

    This is the most important part of the practical. The mechanism:

    * Each calendar date gets a **weight** from a weekday lookup, optionally
      overridden for specific dates (events, holidays).
    * **Economic time** is the cumulative weight divided by 365 - time adjusted for
      when the market is actually open and active.
    * **Total variance** accumulates in economic time:
      ``var(T) = sigma^2 * sum(w_i * dt)`` with ``dt = 1/365``.
    * **ATM volatility is recovered using calendar time**:
      ``sigma_ATM(t) = sqrt(var(t) / calendar_time(t))``.

    That last asymmetry - variance accumulated in economic time, volatility quoted
    against calendar time - is the whole trick. It is what produces the saw-tooth, and
    conflating the two times is the standard misconception.

    Args:
        horizon: The trade date.
        flat_volatility: The single volatility the model is built on, as a decimal.
        weekday_weights: Weight per weekday, keyed 0 (Monday) to 6 (Sunday).
        date_overrides: Per-date weight overrides, for events and holidays.

    Raises:
        ValueError: If the volatility is not positive, a weight is negative, or the
            weekday map is incomplete.
    """

    horizon: date
    flat_volatility: float
    weekday_weights: dict[int, float] = field(
        default_factory=lambda: dict(DEFAULT_DAY_WEIGHTS)
    )
    date_overrides: dict[date, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.flat_volatility <= 0:
            raise ValueError(f"Volatility must be positive, got {self.flat_volatility}")
        missing = set(range(7)) - set(self.weekday_weights)
        if missing:
            raise ValueError(f"weekday_weights is missing weekdays {sorted(missing)}")
        if any(w < 0 for w in self.weekday_weights.values()):
            raise ValueError("Day weights cannot be negative")
        if any(w < 0 for w in self.date_overrides.values()):
            raise ValueError("Date override weights cannot be negative")

    def weight(self, day: date) -> float:
        """The weight for a single date - override first, then the weekday table."""
        if day in self.date_overrides:
            return self.date_overrides[day]
        return self.weekday_weights[day.weekday()]

    def set_event(self, day: date, weight: float) -> None:
        """Raise the weight on an event date (Practical E, Task C).

        The book uses Non-Farm Payrolls on Thursday 3 July 2014. Raising the weight
        lifts the ATM volatility for that expiry **and every expiry after it**, because
        variance is cumulative - which is a real feature of ATM curves, not an
        artefact.

        Args:
            day: The event date.
            weight: The new weight. Above 1.0 means more expected variance than a
                normal day.

        Raises:
            ValueError: If the weight is negative.
        """
        if weight < 0:
            raise ValueError(f"Event weight cannot be negative, got {weight}")
        self.date_overrides[day] = weight

    def build(self, days: int = 400) -> pd.DataFrame:
        """The full table: one row per calendar date (Practical E, Task C).

        Args:
            days: How many calendar days to build, starting one day after the
                horizon. The book asks for at least a year.

        Returns:
            A DataFrame with, per date: the weekday, the weight, calendar time,
            economic time, total variance, the recovered ATM volatility, the daily
            forward variance and the implied forward overnight volatility.

        Raises:
            ValueError: If ``days`` is not positive.
        """
        if days <= 0:
            raise ValueError(f"days must be positive, got {days}")

        dt = 1.0 / DAYS_PER_YEAR
        rows = []
        cumulative_weight = 0.0

        for offset in range(1, days + 1):
            day = self.horizon + timedelta(days=offset)
            w = self.weight(day)
            cumulative_weight += w

            calendar_time = offset / DAYS_PER_YEAR
            economic_time = cumulative_weight / DAYS_PER_YEAR
            total_variance = self.flat_volatility**2 * cumulative_weight * dt

            rows.append({
                "date": day,
                "weekday": day.strftime("%a"),
                "weight": w,
                "calendar_time": calendar_time,
                "economic_time": economic_time,
                "total_variance": total_variance,
                # Volatility comes back out against CALENDAR time, not economic time.
                "atm_vol": np.sqrt(total_variance / calendar_time),
            })

        frame = pd.DataFrame(rows)

        # Daily forward variance, and the overnight volatility it implies. This strip
        # of forward overnight vols is what a trader actually reads to judge whether
        # the curve is rich or cheap over an event.
        frame["daily_variance"] = frame["total_variance"].diff()
        frame.loc[frame.index[0], "daily_variance"] = frame.loc[
            frame.index[0], "total_variance"
        ]
        frame["forward_overnight_vol"] = np.sqrt(
            np.maximum(frame["daily_variance"], 0.0) * DAYS_PER_YEAR
        )
        return frame

    def negative_forward_variance_dates(self, days: int = 400) -> list[date]:
        """Dates where forward variance goes negative (Ch. 11).

        Should be empty for any non-negative set of weights - variance can only
        accumulate. A non-empty result means something is badly wrong, and it is worth
        flagging loudly: negative forward variance is a **calendar arbitrage**. Sell
        the near-dated option and buy the far-dated one and you are short variance
        for nothing, because the market has told you the later date is *less*
        uncertain than the earlier one.
        """
        frame = self.build(days)
        bad = frame[frame["daily_variance"] < 0]
        return list(bad["date"])
