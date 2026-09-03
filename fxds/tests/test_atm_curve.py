"""Tests for fxds.atm_curve - Practical E (Ch. 11)."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest

from fxds.atm_curve import (
    DEFAULT_DAY_WEIGHTS,
    WEEKEND_ZERO_WEIGHTS,
    ATMCurve,
    CurveRangeError,
    Interpolation,
    ParametricATMCurve,
    WeightedATMCurve,
    calibrate_parametric,
    forward_volatility,
    interpolate_variance,
    interpolate_volatility,
    variance,
    volatility_from_variance,
)
from fxds.dates import expiry_from_tenor

HORIZON = date(2014, 6, 11)
TENORS = ("1W", "1M", "3M", "6M", "1Y", "2Y")


def build_curve(vols, method=Interpolation.LINEAR_VARIANCE, tenors=TENORS):
    return ATMCurve(
        horizon=HORIZON,
        expiries=[expiry_from_tenor(HORIZON, t) for t in tenors],
        volatilities=list(vols),
        method=method,
    )


class TestVariance:
    def test_variance_is_vol_squared_times_time(self):
        # Ch. 11's worked example: 3mth ATM at 12% => 0.12^2 * 0.25 = 0.0036.
        assert variance(0.12, 0.25) == pytest.approx(0.0036)

    def test_roundtrip(self):
        assert volatility_from_variance(variance(0.12, 0.25), 0.25) == pytest.approx(0.12)

    def test_negative_variance_rejected(self):
        with pytest.raises(ValueError, match="negative"):
            volatility_from_variance(-0.01, 1.0)

    def test_nonpositive_time_rejected(self):
        with pytest.raises(ValueError, match="Time must be positive"):
            volatility_from_variance(0.01, 0.0)

    def test_forward_volatility_book_example(self):
        # Ch. 11: 6mth at 10.5%, 1yr at 11.7% => forward 6mth-1yr of 12.8%.
        assert forward_volatility(0.105, 0.5, 0.117, 1.0) == pytest.approx(0.128, abs=5e-4)

    def test_forward_variance_is_additive(self):
        # The property that makes variance the right quantity to build curves in.
        v1, T1, v2, T2 = 0.10, 0.5, 0.12, 1.0
        fwd = forward_volatility(v1, T1, v2, T2)
        assert variance(v1, T1) + variance(fwd, T2 - T1) == pytest.approx(variance(v2, T2))

    def test_negative_forward_variance_raises(self):
        # Variance falling with time is a calendar arbitrage, not a rounding issue.
        with pytest.raises(ValueError, match="arbitrageable"):
            forward_volatility(0.20, 1.0, 0.10, 1.5)

    def test_ordering_enforced(self):
        with pytest.raises(ValueError, match="must be greater than"):
            forward_volatility(0.10, 1.0, 0.12, 0.5)


class TestInterpolationMethods:
    def test_linear_volatility_is_linear_in_vol(self):
        assert interpolate_volatility(0.0, 1.0, 0.10, 0.20, 0.5) == pytest.approx(0.15)

    def test_linear_variance_is_linear_in_variance(self):
        # Halfway in time between var 0.01*0 and 0.04*1 => var 0.02, vol sqrt(0.04).
        result = interpolate_variance(0.5, 1.0, 0.10, 0.20, 0.75)
        expected_var = (0.10**2 * 0.5 + 0.20**2 * 1.0) / 2
        assert result == pytest.approx(np.sqrt(expected_var / 0.75))

    def test_both_agree_at_the_nodes(self):
        for method in (interpolate_volatility, interpolate_variance):
            assert method(0.5, 1.0, 0.10, 0.20, 0.5) == pytest.approx(0.10)
            assert method(0.5, 1.0, 0.10, 0.20, 1.0) == pytest.approx(0.20)


class TestCurveTaskA:
    """The four query cases Practical E, Task A asks you to test."""

    def setup_method(self):
        self.curve = build_curve([0.068, 0.072, 0.0765, 0.080, 0.0835, 0.087])

    def test_case_1_before_the_first_tenor_raises(self):
        with pytest.raises(CurveRangeError, match="before the first tenor"):
            self.curve.volatility(HORIZON + timedelta(days=1))

    def test_case_2_after_the_last_tenor_raises(self):
        with pytest.raises(CurveRangeError, match="after the last tenor"):
            self.curve.volatility(HORIZON + timedelta(days=2000))

    def test_case_3_exactly_on_a_tenor_returns_that_tenor(self):
        for expiry, vol in zip(self.curve.expiries, self.curve.volatilities):
            assert self.curve.volatility(expiry) == pytest.approx(vol)

    def test_case_4_between_two_tenors_interpolates(self):
        a, b = self.curve.expiries[1], self.curve.expiries[2]
        mid = a + (b - a) / 2
        result = self.curve.volatility(mid)
        assert min(self.curve.volatilities[1], self.curve.volatilities[2]) < result
        assert result < max(self.curve.volatilities[1], self.curve.volatilities[2])

    def test_the_error_is_explicit_not_a_sentinel(self):
        # The book returns -1, which would propagate silently into a variance.
        with pytest.raises(CurveRangeError):
            self.curve.volatility(HORIZON)


class TestInterpolationTradeoff:
    """Ch. 11's central point: neither method is right on its own."""

    def test_linear_volatility_can_produce_negative_forward_variance(self):
        # The book's counterexample, curve B: flat 20% to 1yr, then 15% at 2yr.
        curve = build_curve(
            [0.20, 0.20, 0.20, 0.20, 0.20, 0.15],
            method=Interpolation.LINEAR_VOLATILITY,
        )
        assert curve.has_negative_forward_variance()

    def test_linear_variance_does_not(self):
        # Same inputs, safe method.
        curve = build_curve(
            [0.20, 0.20, 0.20, 0.20, 0.20, 0.15],
            method=Interpolation.LINEAR_VARIANCE,
        )
        assert not curve.has_negative_forward_variance()

    def test_the_books_arithmetic_for_the_counterexample(self):
        # Variance to 1yr = 0.04; to 18mth at the interpolated 17.5% = 0.046;
        # to 2yr = 0.045. Variance falls, from valid inputs.
        assert variance(0.20, 1.0) == pytest.approx(0.04)
        assert variance(0.175, 1.5) == pytest.approx(0.0459, abs=1e-4)
        assert variance(0.15, 2.0) == pytest.approx(0.045)
        assert variance(0.175, 1.5) > variance(0.15, 2.0)

    def test_upward_sloping_curve_is_safe_under_both(self):
        vols = [0.068, 0.072, 0.0765, 0.080, 0.0835, 0.087]
        for method in Interpolation:
            assert not build_curve(vols, method=method).has_negative_forward_variance()


class TestCurveValidation:
    def test_mismatched_lengths_rejected(self):
        with pytest.raises(ValueError, match="they must match"):
            ATMCurve(HORIZON, [expiry_from_tenor(HORIZON, "1M")], [0.1, 0.2])

    def test_empty_curve_rejected(self):
        with pytest.raises(ValueError, match="at least one tenor"):
            ATMCurve(HORIZON, [], [])

    def test_unordered_expiries_rejected(self):
        with pytest.raises(ValueError, match="strictly ascending"):
            ATMCurve(HORIZON,
                     [expiry_from_tenor(HORIZON, "3M"), expiry_from_tenor(HORIZON, "1M")],
                     [0.1, 0.1])

    def test_nonpositive_volatility_rejected(self):
        with pytest.raises(ValueError, match="must be positive"):
            ATMCurve(HORIZON, [expiry_from_tenor(HORIZON, "1M")], [0.0])

    def test_single_tenor_curve_works_on_its_node(self):
        expiry = expiry_from_tenor(HORIZON, "1M")
        curve = ATMCurve(HORIZON, [expiry], [0.09])
        assert curve.volatility(expiry) == pytest.approx(0.09)
        with pytest.raises(CurveRangeError):
            curve.volatility(expiry + timedelta(days=1))


class TestParametricModelTaskB:
    def test_starts_at_short_and_tends_to_long(self):
        model = ParametricATMCurve(sigma_short=0.06, sigma_long=0.10, speed=2.0)
        assert model.volatility(1e-9) == pytest.approx(0.06, abs=1e-6)
        assert model.volatility(50.0) == pytest.approx(0.10, abs=1e-6)

    def test_higher_speed_converges_faster(self):
        slow = ParametricATMCurve(0.06, 0.10, speed=0.5)
        fast = ParametricATMCurve(0.06, 0.10, speed=5.0)
        assert fast.volatility(1.0) > slow.volatility(1.0)

    def test_downward_sloping_when_short_exceeds_long(self):
        model = ParametricATMCurve(sigma_short=0.15, sigma_long=0.08, speed=1.5)
        curve = model.curve(24)
        assert curve["atm_vol"].is_monotonic_decreasing

    def test_curve_has_a_row_per_month(self):
        assert len(ParametricATMCurve(0.06, 0.10, 1.0).curve(24)) == 24

    def test_speed_must_be_positive(self):
        with pytest.raises(ValueError, match="Speed must be positive"):
            ParametricATMCurve(0.06, 0.10, 0.0)

    def test_the_model_can_generate_arbitrageable_curves(self):
        # Ch. 11 is explicit that this form "would never be used in practice"
        # because nothing in it enforces non-negative forward variance. A sharply
        # downward-sloping fit demonstrates the failure.
        model = ParametricATMCurve(sigma_short=0.40, sigma_long=0.05, speed=6.0)
        assert model.has_negative_forward_variance(24)


class TestCalibration:
    """Beyond the book: least-squares fit with a reported error."""

    def test_recovers_parameters_from_its_own_output(self):
        truth = ParametricATMCurve(0.062, 0.095, 1.8)
        times = np.array([0.02, 0.08, 0.25, 0.5, 1.0, 2.0])
        result = calibrate_parametric(times, truth.volatility(times))
        assert result.success
        assert result.rmse < 1e-6
        assert result.curve.sigma_short == pytest.approx(0.062, abs=1e-4)
        assert result.curve.sigma_long == pytest.approx(0.095, abs=1e-4)
        assert result.curve.speed == pytest.approx(1.8, abs=1e-3)

    def test_reports_a_sensible_error_on_data_it_cannot_fit(self):
        # A curve with a kink the functional form cannot reach.
        times = np.array([0.02, 0.08, 0.25, 0.5, 1.0, 2.0])
        vols = np.array([0.06, 0.12, 0.07, 0.11, 0.08, 0.10])
        result = calibrate_parametric(times, vols)
        assert result.rmse > 0.005
        assert result.max_error >= result.rmse

    def test_fits_a_realistic_upward_sloping_curve_well(self):
        times = np.array([0.019, 0.079, 0.252, 0.501, 1.0, 2.0])
        vols = np.array([0.0685, 0.0720, 0.0765, 0.0800, 0.0835, 0.0870])
        result = calibrate_parametric(times, vols)
        assert result.rmse < 0.002

    def test_needs_at_least_three_points(self):
        with pytest.raises(ValueError, match="at least 3 tenors"):
            calibrate_parametric([0.1, 0.2], [0.1, 0.2])

    def test_mismatched_inputs_rejected(self):
        with pytest.raises(ValueError, match="same length"):
            calibrate_parametric([0.1, 0.2, 0.3], [0.1, 0.2])


class TestDayWeightsTaskC:
    """The heart of Practical E."""

    def test_all_weights_one_gives_a_flat_curve(self):
        # Stage 1 of the book's demonstration: calendar time == economic time.
        curve = WeightedATMCurve(HORIZON, 0.10)
        frame = curve.build(120)
        assert frame["atm_vol"].std() == pytest.approx(0.0, abs=1e-12)
        assert frame["atm_vol"].iloc[-1] == pytest.approx(0.10)

    def test_all_weights_one_means_economic_equals_calendar_time(self):
        frame = WeightedATMCurve(HORIZON, 0.10).build(120)
        assert (frame["economic_time"] - frame["calendar_time"]).abs().max() < 1e-12

    def test_weekend_zero_produces_the_saw_tooth(self):
        # Stage 2: "now comes the magic".
        curve = WeightedATMCurve(HORIZON, 0.10, weekday_weights=dict(WEEKEND_ZERO_WEIGHTS))
        frame = curve.build(120)
        assert frame["atm_vol"].std() > 0.001

    def test_monday_prices_below_the_preceding_friday(self):
        # Ch. 11: the defining signature of the saw-tooth. Economic time stops over
        # the weekend, so the Monday expiry has a lower open-to-calendar-days ratio.
        curve = WeightedATMCurve(HORIZON, 0.10, weekday_weights=dict(WEEKEND_ZERO_WEIGHTS))
        frame = curve.build(120).set_index("date")
        pairs = 0
        for day, row in frame.iterrows():
            if row["weekday"] != "Fri":
                continue
            monday = day + timedelta(days=3)
            if monday in frame.index:
                assert frame.loc[monday, "atm_vol"] < row["atm_vol"]
                pairs += 1
        assert pairs >= 15, "expected plenty of Friday/Monday pairs to check"

    def test_level_tends_below_the_flat_input(self):
        # Ch. 11: with the economic-to-calendar ratio below 1, ATM volatility tends
        # toward something lower than the flat input. Desks adjust for this when
        # they have target levels to hit.
        curve = WeightedATMCurve(HORIZON, 0.10, weekday_weights=dict(WEEKEND_ZERO_WEIGHTS))
        frame = curve.build(365)
        assert frame["atm_vol"].iloc[-1] < 0.10
        assert frame["atm_vol"].iloc[-1] == pytest.approx(0.10 * np.sqrt(5 / 7), abs=0.004)

    def test_economic_time_never_exceeds_calendar_time_with_weekends_off(self):
        frame = WeightedATMCurve(
            HORIZON, 0.10, weekday_weights=dict(WEEKEND_ZERO_WEIGHTS)
        ).build(200)
        assert (frame["economic_time"] <= frame["calendar_time"] + 1e-12).all()

    def test_variance_is_always_non_decreasing(self):
        for weights in (DEFAULT_DAY_WEIGHTS, WEEKEND_ZERO_WEIGHTS):
            frame = WeightedATMCurve(
                HORIZON, 0.10, weekday_weights=dict(weights)
            ).build(200)
            assert (frame["total_variance"].diff().dropna() >= -1e-15).all()

    def test_no_negative_forward_variance_for_valid_weights(self):
        curve = WeightedATMCurve(HORIZON, 0.10, weekday_weights=dict(WEEKEND_ZERO_WEIGHTS))
        assert curve.negative_forward_variance_dates(200) == []

    def test_negative_weights_rejected(self):
        with pytest.raises(ValueError, match="cannot be negative"):
            WeightedATMCurve(HORIZON, 0.10, weekday_weights={**DEFAULT_DAY_WEIGHTS, 5: -1.0})

    def test_incomplete_weekday_map_rejected(self):
        with pytest.raises(ValueError, match="missing weekdays"):
            WeightedATMCurve(HORIZON, 0.10, weekday_weights={0: 1.0})

    def test_nonpositive_volatility_rejected(self):
        with pytest.raises(ValueError, match="must be positive"):
            WeightedATMCurve(HORIZON, 0.0)


class TestEventWeighting:
    """Practical E, Task C, final stage: the Non-Farm Payrolls date."""

    NFP = date(2014, 7, 3)   # Thursday 3 July 2014, the book's example

    def _pair(self, weight=4.0):
        base = WeightedATMCurve(HORIZON, 0.10, weekday_weights=dict(WEEKEND_ZERO_WEIGHTS))
        event = WeightedATMCurve(HORIZON, 0.10, weekday_weights=dict(WEEKEND_ZERO_WEIGHTS))
        event.set_event(self.NFP, weight)
        return base.build(120), event.build(120)

    def test_the_event_date_itself_rises(self):
        base, event = self._pair()
        b = base.set_index("date").loc[self.NFP, "atm_vol"]
        e = event.set_index("date").loc[self.NFP, "atm_vol"]
        assert e > b

    def test_every_subsequent_date_rises_too(self):
        # Ch. 11: "a real feature observed when building ATM curves: if expected
        # variance for a given date increases, the ATM volatility for that date AND
        # SUBSEQUENT DATES rises."
        base, event = self._pair()
        merged = base[["date", "atm_vol"]].merge(
            event[["date", "atm_vol"]], on="date", suffixes=("_base", "_event")
        )
        after = merged[merged["date"] >= self.NFP]
        assert len(after) > 50
        assert (after["atm_vol_event"] > after["atm_vol_base"]).all()

    def test_nothing_before_the_event_changes(self):
        base, event = self._pair()
        merged = base[["date", "atm_vol"]].merge(
            event[["date", "atm_vol"]], on="date", suffixes=("_base", "_event")
        )
        before = merged[merged["date"] < self.NFP]
        assert len(before) > 10
        assert (before["atm_vol_event"] - before["atm_vol_base"]).abs().max() < 1e-15

    def test_a_bigger_event_weight_lifts_the_curve_more(self):
        _, small = self._pair(2.0)
        _, large = self._pair(8.0)
        day = self.NFP + timedelta(days=30)
        s = small.set_index("date").loc[day, "atm_vol"]
        l = large.set_index("date").loc[day, "atm_vol"]
        assert l > s

    def test_holiday_weighting_lowers_the_curve(self):
        # The mirror of an event: Ch. 11 notes public holidays get lower variance.
        base = WeightedATMCurve(HORIZON, 0.10, weekday_weights=dict(WEEKEND_ZERO_WEIGHTS))
        holiday = WeightedATMCurve(HORIZON, 0.10, weekday_weights=dict(WEEKEND_ZERO_WEIGHTS))
        holiday.set_event(date(2014, 7, 4), 0.2)   # US Independence Day
        day = date(2014, 8, 1)
        b = base.build(120).set_index("date").loc[day, "atm_vol"]
        h = holiday.build(120).set_index("date").loc[day, "atm_vol"]
        assert h < b

    def test_negative_event_weight_rejected(self):
        curve = WeightedATMCurve(HORIZON, 0.10)
        with pytest.raises(ValueError, match="cannot be negative"):
            curve.set_event(self.NFP, -1.0)


class TestForwardOvernightVolatility:
    """The strip a trader actually reads to judge an event."""

    def test_flat_weights_give_a_flat_forward_overnight_strip(self):
        frame = WeightedATMCurve(HORIZON, 0.10).build(120)
        assert frame["forward_overnight_vol"].std() == pytest.approx(0.0, abs=1e-12)
        assert frame["forward_overnight_vol"].iloc[-1] == pytest.approx(0.10)

    def test_weekend_days_have_zero_forward_overnight_vol(self):
        frame = WeightedATMCurve(
            HORIZON, 0.10, weekday_weights=dict(WEEKEND_ZERO_WEIGHTS)
        ).build(120)
        weekend = frame[frame["weekday"].isin(["Sat", "Sun"])]
        assert weekend["forward_overnight_vol"].abs().max() < 1e-12

    def test_the_event_date_stands_out_in_the_strip(self):
        # This is the whole point of looking at forward overnight vols: an event is
        # invisible in the ATM curve's level but obvious in the daily strip.
        curve = WeightedATMCurve(HORIZON, 0.10, weekday_weights=dict(WEEKEND_ZERO_WEIGHTS))
        nfp = date(2014, 7, 3)
        curve.set_event(nfp, 4.0)
        frame = curve.build(120).set_index("date")
        weekdays = frame[~frame["weekday"].isin(["Sat", "Sun"])]
        assert frame.loc[nfp, "forward_overnight_vol"] == weekdays["forward_overnight_vol"].max()
        assert frame.loc[nfp, "forward_overnight_vol"] == pytest.approx(0.10 * 2.0, abs=1e-9)
