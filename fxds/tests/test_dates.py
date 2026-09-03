"""Tests for fxds.dates - Practical D (Ch. 10)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from fxds.dates import (
    InvalidTenorError,
    business_day_decrement,
    business_day_increment,
    delivery_date_from_expiry,
    expiry_from_tenor,
    horizon_from_spot_date,
    is_business_day,
    next_business_day,
    previous_business_day,
    spot_date_from_horizon,
    tenor_dates,
    tenor_table,
    validate_day_week_expiry,
)

# The book's worked horizon: Wednesday 11 June 2014 (Excel serial 41801).
HORIZON = date(2014, 6, 11)

MON, TUE, WED, THU, FRI = (date(2014, 6, d) for d in (9, 10, 11, 12, 13))
SAT, SUN = date(2014, 6, 14), date(2014, 6, 15)


class TestBusinessDays:
    def test_weekdays_are_business_days(self):
        for day in (MON, TUE, WED, THU, FRI):
            assert is_business_day(day)

    def test_weekends_are_not(self):
        assert not is_business_day(SAT)
        assert not is_business_day(SUN)

    def test_next_business_day_from_friday_skips_the_weekend(self):
        # The book's VBA: Friday adds 3.
        assert next_business_day(FRI) == FRI + timedelta(days=3)
        assert next_business_day(FRI).weekday() == 0

    def test_next_business_day_from_saturday(self):
        # The book's VBA: Saturday adds 2.
        assert next_business_day(SAT) == SAT + timedelta(days=2)

    def test_next_business_day_otherwise_adds_one(self):
        assert next_business_day(WED) == THU

    def test_previous_business_day_from_monday_skips_the_weekend(self):
        # The book's VBA: Monday subtracts 3.
        monday = date(2014, 6, 16)
        assert previous_business_day(monday) == monday - timedelta(days=3)

    def test_previous_business_day_from_sunday(self):
        # The book's VBA: Sunday subtracts 2.
        assert previous_business_day(SUN) == SUN - timedelta(days=2)

    def test_previous_business_day_otherwise_subtracts_one(self):
        assert previous_business_day(THU) == WED

    def test_increment_and_decrement_are_inverse_across_a_weekend(self):
        assert business_day_decrement(business_day_increment(WED, 5), 5) == WED

    def test_zero_steps_is_a_no_op(self):
        assert business_day_increment(WED, 0) == WED
        assert business_day_decrement(WED, 0) == WED

    def test_negative_steps_rejected(self):
        with pytest.raises(ValueError, match="must not be negative"):
            business_day_increment(WED, -1)
        with pytest.raises(ValueError, match="must not be negative"):
            business_day_decrement(WED, -1)

    def test_injectable_holiday_calendar(self):
        # Practical D has no holiday calendar, but the seam is left open.
        holiday = date(2014, 6, 12)   # the Thursday
        cal = {holiday}.__contains__
        assert not is_business_day(holiday, cal)
        assert next_business_day(WED, cal) == FRI


class TestSpotDates:
    def test_spot_is_t_plus_two_business_days(self):
        assert spot_date_from_horizon(HORIZON) == date(2014, 6, 13)

    def test_spot_skips_the_weekend(self):
        # Thursday horizon: T+2 lands on Monday, not Saturday.
        assert spot_date_from_horizon(THU) == date(2014, 6, 16)

    def test_horizon_from_spot_is_the_inverse(self):
        assert horizon_from_spot_date(spot_date_from_horizon(HORIZON)) == HORIZON

    def test_t_plus_one_pairs_are_supported(self):
        # Ch. 10 notes USD/CAD and USD/TRY settle T+1.
        assert spot_date_from_horizon(HORIZON, lag=1) == THU

    def test_delivery_derives_from_expiry_as_spot_from_horizon(self):
        # The symmetry Ch. 10 sets out, and the basis of the month/year rules.
        expiry = date(2014, 9, 11)
        assert delivery_date_from_expiry(expiry) == spot_date_from_horizon(expiry)


class TestExpiryFromTenor:
    def test_overnight_is_the_next_business_day(self):
        assert expiry_from_tenor(HORIZON, "ON") == THU

    def test_overnight_on_a_friday_lands_on_monday(self):
        # Ch. 11: a Friday "overnight" actually spans three days, which is why its
        # quoted volatility is not comparable with other days'.
        assert expiry_from_tenor(FRI, "ON") == date(2014, 6, 16)

    def test_overnight_accepts_the_slashed_form(self):
        assert expiry_from_tenor(HORIZON, "O/N") == expiry_from_tenor(HORIZON, "ON")

    @pytest.mark.parametrize("weeks", [1, 2, 4])
    def test_weeks_are_added_to_the_horizon_directly(self, weeks):
        # Practical D: weeks go on the horizon, NOT via the spot date.
        assert expiry_from_tenor(HORIZON, f"{weeks}W") == HORIZON + timedelta(days=7 * weeks)

    def test_months_route_via_the_spot_date_and_back(self):
        # spot 13 Jun + 1M = Sun 13 Jul -> roll to Mon 14 Jul -> back 2bd = Thu 10 Jul.
        assert expiry_from_tenor(HORIZON, "1M") == date(2014, 7, 10)

    def test_years_route_the_same_way(self):
        # spot 13 Jun 2014 + 1Y = Sat 13 Jun 2015 -> Mon 15 Jun -> back 2bd = Thu 11 Jun.
        assert expiry_from_tenor(HORIZON, "1Y") == date(2015, 6, 11)

    def test_months_and_weeks_differ_because_of_the_routing(self):
        # 1M is not "4W plus a bit" - they are computed by different rules, and this
        # is the asymmetry the practical is teaching.
        assert expiry_from_tenor(HORIZON, "1M") != expiry_from_tenor(HORIZON, "4W")

    def test_expiries_are_ascending_across_the_market_tenors(self):
        expiries = [expiry_from_tenor(HORIZON, t)
                    for t in ("ON", "1W", "2W", "1M", "2M", "3M", "6M", "9M", "1Y", "2Y")]
        assert expiries == sorted(expiries)
        assert len(set(expiries)) == len(expiries)

    def test_case_insensitive(self):
        assert expiry_from_tenor(HORIZON, "3m") == expiry_from_tenor(HORIZON, "3M")
        assert expiry_from_tenor(HORIZON, " on ") == expiry_from_tenor(HORIZON, "ON")

    def test_month_and_year_expiries_are_business_days(self):
        for tenor in ("1M", "2M", "3M", "6M", "9M", "1Y", "2Y"):
            assert is_business_day(expiry_from_tenor(HORIZON, tenor))

    @pytest.mark.parametrize("bad", ["banana", "1X", "M1", "", "1.5M", "-1M"])
    def test_invalid_tenors_raise_rather_than_returning_a_sentinel(self, bad):
        # The book pops a MsgBox and returns -1. See notes/deviations.md.
        with pytest.raises(InvalidTenorError):
            expiry_from_tenor(HORIZON, bad)

    def test_zero_count_rejected(self):
        with pytest.raises(InvalidTenorError, match="must be positive"):
            expiry_from_tenor(HORIZON, "0M")


class TestChapterTenRuleForDayAndWeekTenors:
    """Ch. 10 says a day/week expiry on a weekend or 1 Jan is invalid.

    Practical D's own code does not check this, so expiry_from_tenor does not
    either - but the rule is real and is exposed separately.
    """

    def test_weekend_expiry_is_flagged(self):
        # A Saturday horizon plus one week lands on a Saturday.
        expiry = expiry_from_tenor(SAT, "1W")
        assert expiry.weekday() == 5
        with pytest.raises(InvalidTenorError, match="falls on a Saturday"):
            validate_day_week_expiry(expiry)

    def test_new_years_day_is_flagged(self):
        with pytest.raises(InvalidTenorError, match="1 January"):
            validate_day_week_expiry(date(2015, 1, 1))

    def test_a_normal_weekday_passes(self):
        validate_day_week_expiry(date(2014, 6, 18))


class TestTenorTable:
    def test_table_has_a_row_per_tenor_with_the_expected_columns(self):
        table = tenor_table(HORIZON)
        assert len(table) == 10
        for column in ("tenor", "expiry", "expiry_day", "delivery", "delivery_day",
                       "days", "years"):
            assert column in table.columns

    def test_years_is_days_over_365(self):
        table = tenor_table(HORIZON)
        assert (table["years"] * 365 - table["days"]).abs().max() < 1e-9

    def test_one_year_tenor_is_about_one_year(self):
        row = tenor_table(HORIZON, ["1Y"]).iloc[0]
        assert row["days"] == 365
        assert row["years"] == pytest.approx(1.0)

    def test_delivery_is_always_after_expiry(self):
        table = tenor_table(HORIZON)
        assert (table["delivery"] > table["expiry"]).all()

    def test_tenor_dates_object_matches_the_table(self):
        dates = tenor_dates(HORIZON, "3M")
        row = tenor_table(HORIZON, ["3M"]).iloc[0]
        assert dates.expiry == row["expiry"]
        assert dates.delivery == row["delivery"]
        assert dates.expiry_weekday == row["expiry_day"]
