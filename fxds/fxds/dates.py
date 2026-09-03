"""Business days, spot dates and tenor expiry dates - Practical D (Ch. 10).

Implements Practical D: business day increment and decrement, spot date from horizon
(T+2) and back, and ``expiry_from_tenor`` handling ON, nW, nM and nY per the rules
set out in Chapter 10.

Weekends only - there is no holiday calendar here, matching the practical. The
functions take an injectable calendar so one can be added later without reworking
the call sites. The end-end and month-overflow special cases that Chapter 10
describes but Practical D skips are marked as TODOs and documented in
``notes/deviations.md``.

The four dates, from Chapter 10:

* **Horizon** - today, the date the trade originates.
* **Spot date** - when the premium and any spot hedge settle. T+2 here.
* **Expiry date** - when the contract expires.
* **Delivery date** - when the final funds move. Derived from the expiry date
  *exactly* as the spot date is derived from the horizon.

That last symmetry is not decoration - it is why month and year tenors are computed
by going out to a delivery date and coming back, rather than being added to the
horizon directly.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

# A holiday calendar is any callable that answers "is this date a holiday?".
# Deliberately a plain function rather than a class: nothing here needs more, and
# a caller can supply a set's ``__contains__``, a pandas calendar, or their own rule.
HolidayCalendar = Callable[[date], bool]

SPOT_LAG_DAYS = 2
"""Business days between horizon and spot date.

Chapter 10 notes some pairs settle T+1 (USD/CAD, USD/TRY). Practical D assumes T+2
throughout, and so does this module by default - but every function takes ``lag`` so
a T+1 pair can be handled without touching the internals.
"""

_TENOR_PATTERN = re.compile(r"^(\d+)([DWMY])$", re.IGNORECASE)


class InvalidTenorError(ValueError):
    """Raised for a tenor string that cannot be parsed.

    The book's VBA pops a message box and returns -1. A sentinel that is also a
    plausible-looking date serial is worse than useless in Python - Practical E's own
    code then has to test for it - so this raises instead. See
    ``notes/deviations.md``.
    """


def _no_holidays(_: date) -> bool:
    """The default calendar: weekends only, no holidays. Matches Practical D."""
    return False


def is_business_day(day: date, calendar: HolidayCalendar = _no_holidays) -> bool:
    """Whether a date is a business day.

    Args:
        day: The date to test.
        calendar: Holiday calendar. Defaults to weekends-only.

    Returns:
        True if the date is a weekday and not a holiday.
    """
    return day.weekday() < 5 and not calendar(day)


def next_business_day(day: date, calendar: HolidayCalendar = _no_holidays) -> date:
    """The next business day strictly after ``day`` (Practical D).

    The book's VBA special-cases Saturday (+2) and Friday (+3) and otherwise adds one.
    Stepping forward until a business day is found is the same thing for weekends and
    also handles holidays once a calendar is supplied.

    Args:
        day: Starting date.
        calendar: Holiday calendar. Defaults to weekends-only.

    Returns:
        The next business day.
    """
    candidate = day + timedelta(days=1)
    while not is_business_day(candidate, calendar):
        candidate += timedelta(days=1)
    return candidate


def previous_business_day(day: date, calendar: HolidayCalendar = _no_holidays) -> date:
    """The last business day strictly before ``day`` (Practical D).

    Args:
        day: Starting date.
        calendar: Holiday calendar. Defaults to weekends-only.

    Returns:
        The previous business day.
    """
    candidate = day - timedelta(days=1)
    while not is_business_day(candidate, calendar):
        candidate -= timedelta(days=1)
    return candidate


def business_day_increment(
    day: date, increment: int, calendar: HolidayCalendar = _no_holidays
) -> date:
    """Step forward ``increment`` business days (Practical D).

    Args:
        day: Starting date.
        increment: Number of business days. Must not be negative.
        calendar: Holiday calendar.

    Returns:
        The resulting date.

    Raises:
        ValueError: If ``increment`` is negative.
    """
    if increment < 0:
        raise ValueError(f"Increment must not be negative, got {increment}")
    result = day
    for _ in range(increment):
        result = next_business_day(result, calendar)
    return result


def business_day_decrement(
    day: date, decrement: int, calendar: HolidayCalendar = _no_holidays
) -> date:
    """Step back ``decrement`` business days (Practical D).

    Args:
        day: Starting date.
        decrement: Number of business days. Must not be negative.
        calendar: Holiday calendar.

    Returns:
        The resulting date.

    Raises:
        ValueError: If ``decrement`` is negative.
    """
    if decrement < 0:
        raise ValueError(f"Decrement must not be negative, got {decrement}")
    result = day
    for _ in range(decrement):
        result = previous_business_day(result, calendar)
    return result


def spot_date_from_horizon(
    horizon: date, lag: int = SPOT_LAG_DAYS, calendar: HolidayCalendar = _no_holidays
) -> date:
    """The spot date for a given horizon (Practical D).

    Args:
        horizon: The trade date.
        lag: Settlement lag in business days. Defaults to 2.
        calendar: Holiday calendar.

    Returns:
        The spot date.

    Examples:
        >>> from datetime import date
        >>> spot_date_from_horizon(date(2014, 6, 11))   # a Wednesday
        datetime.date(2014, 6, 13)
        >>> spot_date_from_horizon(date(2014, 6, 12))   # Thursday, so spot skips the weekend
        datetime.date(2014, 6, 16)
    """
    return business_day_increment(horizon, lag, calendar)


def horizon_from_spot_date(
    spot_date: date, lag: int = SPOT_LAG_DAYS, calendar: HolidayCalendar = _no_holidays
) -> date:
    """The horizon that would produce a given spot date - the inverse operation.

    Chapter 10 calls this the "inverse spot date" operation, and it is what turns a
    delivery date back into an expiry date for month and year tenors.

    Note it is not a perfect inverse in every case: stepping forward two business days
    and back again can land on a different date when the intervening days include a
    weekend or holiday in an asymmetric way. That is a property of the convention,
    not a bug, and the market lives with it.

    Args:
        spot_date: The settlement date.
        lag: Settlement lag in business days. Defaults to 2.
        calendar: Holiday calendar.

    Returns:
        The corresponding horizon.
    """
    return business_day_decrement(spot_date, lag, calendar)


def delivery_date_from_expiry(
    expiry: date, lag: int = SPOT_LAG_DAYS, calendar: HolidayCalendar = _no_holidays
) -> date:
    """The delivery date for an expiry (Ch. 10).

    Derived from the expiry exactly as the spot date is derived from the horizon -
    the symmetry Chapter 10 sets out.

    Args:
        expiry: The option expiry date.
        lag: Settlement lag in business days.
        calendar: Holiday calendar.

    Returns:
        The delivery date.
    """
    return business_day_increment(expiry, lag, calendar)


def expiry_from_tenor(
    horizon: date,
    tenor: str,
    lag: int = SPOT_LAG_DAYS,
    calendar: HolidayCalendar = _no_holidays,
) -> date:
    """The expiry date for a market tenor (Practical D; rules from Ch. 10).

    Four cases, and the asymmetry between them is the thing to understand:

    * ``ON`` - the next business day after the horizon.
    * ``nD`` / ``nW`` - **added to the horizon directly**, as calendar days.
    * ``nM`` / ``nY`` - go out to the **spot date**, add the months or years to reach
      the *delivery* date, then come back two business days to the expiry.

    Weeks are added to the horizon; months go via the spot date and back. That is not
    an arbitrary quirk: month and year contracts are defined by their delivery date,
    so the expiry has to be derived from it rather than the other way round.

    Args:
        horizon: The trade date.
        tenor: ``"ON"``, or a count and unit such as ``"1W"``, ``"3M"``, ``"2Y"``.
            Case-insensitive.
        lag: Settlement lag in business days.
        calendar: Holiday calendar.

    Returns:
        The expiry date.

    Raises:
        InvalidTenorError: If the tenor cannot be parsed, or the count is zero.

    Examples:
        >>> from datetime import date
        >>> horizon = date(2014, 6, 11)          # Wednesday
        >>> expiry_from_tenor(horizon, "ON")
        datetime.date(2014, 6, 12)
        >>> expiry_from_tenor(horizon, "1W")
        datetime.date(2014, 6, 18)
        >>> expiry_from_tenor(horizon, "1M")   # spot 13 Jun + 1M = Sun 13 Jul,
        datetime.date(2014, 7, 10)
    """
    cleaned = tenor.strip().upper()

    if cleaned in ("ON", "O/N"):
        return next_business_day(horizon, calendar)

    match = _TENOR_PATTERN.match(cleaned)
    if match is None:
        raise InvalidTenorError(
            f"Cannot parse tenor {tenor!r}. Expected 'ON' or a count and unit "
            f"such as '1W', '3M' or '2Y'."
        )

    count, unit = int(match.group(1)), match.group(2).upper()
    if count == 0:
        raise InvalidTenorError(f"Tenor count must be positive, got {tenor!r}")

    if unit in ("D", "W"):
        # Added to the horizon directly, as calendar days.
        #
        # Note: Chapter 10 says such a tenor is *invalid* if it lands on a weekend or
        # 1 January, whereas Practical D's own code just returns horizon + 7n with no
        # check. Following the practical's code, since that is what this module
        # implements; the chapter's stricter rule is recorded in
        # notes/deviations.md. Use ``validate_day_week_expiry`` below to apply it.
        days = count if unit == "D" else count * 7
        return horizon + timedelta(days=days)

    # Months and years: out to the delivery date from the spot date, then back.
    spot_date = spot_date_from_horizon(horizon, lag, calendar)
    step = relativedelta(months=count) if unit == "M" else relativedelta(years=count)
    delivery = spot_date + step

    # TODO(end-end): Chapter 10 special case 1. If the spot date is the last business
    # day of its month, the delivery date is by convention the last business day of
    # the target month. Practical D ignores this and so do we.
    #
    # TODO(month-overflow): Chapter 10 special case 2. If the natural delivery date
    # would fall beyond the end of the target month - spot date 30 January with a 1M
    # tenor implying 30 February - the delivery date is the last business day of the
    # target month. relativedelta already clamps 30 Jan + 1 month to 28/29 Feb, which
    # happens to agree with the convention here, but it does so by arithmetic
    # accident rather than by implementing the rule. Do not rely on it.

    # Roll forward to an acceptable delivery date if the natural one is not one.
    while not is_business_day(delivery, calendar):
        delivery += timedelta(days=1)

    return horizon_from_spot_date(delivery, lag, calendar)


def validate_day_week_expiry(expiry: date) -> None:
    """Apply Chapter 10's rule that a day or week tenor must not land badly.

    Chapter 10 states that for a days or weeks tenor the expiry is invalid if it falls
    on a weekend or on 1 January. Practical D's code does not check this, so
    :func:`expiry_from_tenor` does not either - but the rule is real, and this makes
    it available to callers who want it.

    Args:
        expiry: The computed expiry date.

    Raises:
        InvalidTenorError: If the expiry falls on a weekend or on 1 January.
    """
    if expiry.weekday() >= 5:
        raise InvalidTenorError(
            f"Expiry {expiry} falls on a {expiry.strftime('%A')}. Chapter 10 makes "
            f"this tenor invalid; Practical D's code does not check it."
        )
    if (expiry.month, expiry.day) == (1, 1):
        raise InvalidTenorError(f"Expiry {expiry} is 1 January, which cannot be an expiry.")


@dataclass(frozen=True)
class TenorDates:
    """The dates for one market tenor.

    Attributes:
        tenor: The tenor label.
        expiry: The expiry date.
        delivery: The delivery date.
        days_to_expiry: Calendar days from horizon to expiry.
        years_to_expiry: ``days_to_expiry / 365``, the time measure used throughout
            Part II.
    """

    tenor: str
    expiry: date
    delivery: date
    days_to_expiry: int
    years_to_expiry: float

    @property
    def expiry_weekday(self) -> str:
        """Day of the week of the expiry, e.g. ``"Wed"``."""
        return self.expiry.strftime("%a")


def tenor_dates(
    horizon: date,
    tenor: str,
    lag: int = SPOT_LAG_DAYS,
    calendar: HolidayCalendar = _no_holidays,
) -> TenorDates:
    """Every date for one tenor (Practical D).

    Args:
        horizon: The trade date.
        tenor: Tenor label.
        lag: Settlement lag in business days.
        calendar: Holiday calendar.

    Returns:
        A :class:`TenorDates`.
    """
    expiry = expiry_from_tenor(horizon, tenor, lag, calendar)
    days = (expiry - horizon).days
    return TenorDates(
        tenor=tenor.strip().upper(),
        expiry=expiry,
        delivery=delivery_date_from_expiry(expiry, lag, calendar),
        days_to_expiry=days,
        years_to_expiry=days / 365.0,
    )


def tenor_table(
    horizon: date,
    tenors: tuple[str, ...] | list[str] | None = None,
    lag: int = SPOT_LAG_DAYS,
    calendar: HolidayCalendar = _no_holidays,
):
    """The tenor table Practical D asks you to produce.

    Args:
        horizon: The trade date.
        tenors: Tenors to include. Defaults to
            :data:`fxds.conventions.MARKET_TENORS`.
        lag: Settlement lag in business days.
        calendar: Holiday calendar.

    Returns:
        A DataFrame with one row per tenor: expiry date, delivery date, day of week
        and day count.
    """
    import pandas as pd

    from .conventions import MARKET_TENORS

    chosen = tuple(tenors) if tenors is not None else MARKET_TENORS
    rows = []
    for tenor in chosen:
        dates = tenor_dates(horizon, tenor, lag, calendar)
        rows.append(
            {
                "tenor": dates.tenor,
                "expiry": dates.expiry,
                "expiry_day": dates.expiry_weekday,
                "delivery": dates.delivery,
                "delivery_day": dates.delivery.strftime("%a"),
                "days": dates.days_to_expiry,
                "years": dates.years_to_expiry,
            }
        )
    return pd.DataFrame(rows)
