"""Tests for fxds.smile - Practical F (Ch. 12)."""

from __future__ import annotations

import numpy as np
import pytest

from fxds.smile import (
    DELTA_CAP,
    DELTA_FLOOR,
    STANDARD_PUT_DELTAS,
    MalzSmile,
    max_attainable_put_delta,
    put_delta_from_strike,
    smile_by_strike,
    strike_from_put_delta,
    strike_placement,
)

BASE = dict(spot=1.30, T=1.0, r_ccy1=0.02, r_ccy2=0.05)


class TestMalzTaskA:
    """Practical F, Task A: verify the formula against the standard approximations."""

    def test_fifty_delta_returns_the_atm(self):
        smile = MalzSmile(atm=0.10, rr25=-0.02, fly25=0.005)
        assert smile.volatility(0.5) == pytest.approx(0.10)

    def test_twenty_five_delta_put(self):
        # sigma_25dP = ATM + fly - RR/2
        smile = MalzSmile(atm=0.10, rr25=-0.02, fly25=0.005)
        assert smile.volatility(0.25) == pytest.approx(0.10 + 0.005 - 0.5 * (-0.02))
        assert smile.volatility(0.25) == pytest.approx(smile.put_25d)

    def test_twenty_five_delta_call(self):
        # sigma_25dC = ATM + fly + RR/2, at a 75% put delta
        smile = MalzSmile(atm=0.10, rr25=-0.02, fly25=0.005)
        assert smile.volatility(0.75) == pytest.approx(0.10 + 0.005 + 0.5 * (-0.02))
        assert smile.volatility(0.75) == pytest.approx(smile.call_25d)

    def test_ten_delta_expansions(self):
        # Ch. 12: sigma_10dP = ATM - 0.8*RR + 2.56*fly, and the mirror for the call.
        smile = MalzSmile(atm=0.10, rr25=-0.02, fly25=0.005)
        assert smile.volatility(0.10) == pytest.approx(0.10 - 0.8 * (-0.02) + 2.56 * 0.005)
        assert smile.volatility(0.90) == pytest.approx(0.10 + 0.8 * (-0.02) + 2.56 * 0.005)

    def test_rr25_recovers_from_the_two_strikes(self):
        smile = MalzSmile(atm=0.10, rr25=-0.02, fly25=0.005)
        assert smile.call_25d - smile.put_25d == pytest.approx(smile.rr25)

    def test_fly25_recovers_from_the_two_strikes(self):
        smile = MalzSmile(atm=0.10, rr25=-0.02, fly25=0.005)
        assert (smile.call_25d + smile.put_25d) / 2 - smile.atm == pytest.approx(smile.fly25)

    def test_the_model_implies_a_10d_multiplier_of_exactly_1_6(self):
        # Ch. 12 derives this and notes the market value is usually nearer 1.8, so
        # the Malz form understates 10 delta skew. A known limitation, not a bug.
        smile = MalzSmile(atm=0.10, rr25=-0.025, fly25=0.006)
        assert smile.rr10_implied == pytest.approx(1.6 * smile.rr25)

    def test_zero_rr_and_fly_gives_a_flat_smile(self):
        smile = MalzSmile(atm=0.09)
        deltas = np.linspace(0.05, 0.95, 30)
        assert np.allclose(smile.volatility(deltas), 0.09)

    def test_positive_butterfly_lifts_both_wings_symmetrically(self):
        flat = MalzSmile(atm=0.10)
        winged = MalzSmile(atm=0.10, fly25=0.01)
        lift_down = winged.volatility(0.25) - flat.volatility(0.25)
        lift_up = winged.volatility(0.75) - flat.volatility(0.75)
        assert lift_down > 0
        assert lift_down == pytest.approx(lift_up)

    def test_positive_risk_reversal_tilts_topside_up(self):
        smile = MalzSmile(atm=0.10, rr25=+0.02)
        assert smile.volatility(0.75) > smile.volatility(0.25)

    def test_negative_risk_reversal_tilts_downside_up(self):
        # The EUR/USD shape Ch. 7 describes.
        smile = MalzSmile(atm=0.10, rr25=-0.02)
        assert smile.volatility(0.25) > smile.volatility(0.75)

    def test_atm_is_unchanged_by_the_risk_reversal(self):
        for rr in (-0.05, 0.0, 0.05):
            assert MalzSmile(atm=0.10, rr25=rr).volatility(0.5) == pytest.approx(0.10)

    def test_nonpositive_atm_rejected(self):
        with pytest.raises(ValueError, match="must be positive"):
            MalzSmile(atm=0.0)

    def test_curve_spans_the_delta_range(self):
        curve = MalzSmile(atm=0.10, rr25=-0.02, fly25=0.005).curve()
        assert curve["put_delta"].iloc[0] == pytest.approx(DELTA_FLOOR)
        assert curve["put_delta"].iloc[-1] == pytest.approx(DELTA_CAP)


class TestStrikeFromDeltaTaskC:
    def test_round_trip_strike_to_delta_to_strike(self):
        # Practical F, Task C: "If the strike input and output are equal as other
        # inputs change, this confirms that the formulas are correctly implemented."
        strike = 1.25
        delta = put_delta_from_strike(strike=strike, sigma=0.10, **BASE)
        recovered = strike_from_put_delta(put_delta=delta, sigma=0.10, **BASE)
        assert recovered == pytest.approx(strike, rel=1e-12)

    @pytest.mark.parametrize("seed", range(30))
    def test_round_trip_as_a_property_over_random_inputs(self, seed):
        rng = np.random.default_rng(seed)
        spot = rng.uniform(0.5, 150.0)
        strike = spot * rng.uniform(0.6, 1.7)
        T = rng.uniform(0.02, 5.0)
        r1 = rng.uniform(-0.01, 0.10)
        r2 = rng.uniform(-0.01, 0.10)
        sigma = rng.uniform(0.03, 0.60)

        delta = put_delta_from_strike(spot, strike, T, r1, r2, sigma)
        # Skip degenerate corners where the delta saturates and the inverse normal
        # loses all precision - a real numerical limit, not a formula error.
        if not -0.999 < delta < -0.001:
            pytest.skip("delta saturated at the boundary")
        recovered = strike_from_put_delta(spot, delta, T, r1, r2, sigma)
        assert recovered == pytest.approx(strike, rel=1e-8)

    def test_put_delta_is_always_negative(self):
        for strike in (0.9, 1.3, 1.8):
            assert put_delta_from_strike(strike=strike, sigma=0.12, **BASE) < 0

    def test_lower_strike_gives_a_smaller_absolute_put_delta(self):
        # A far-downside put is less likely to finish in the money.
        near = put_delta_from_strike(strike=1.30, sigma=0.12, **BASE)
        far = put_delta_from_strike(strike=1.00, sigma=0.12, **BASE)
        assert abs(far) < abs(near)

    def test_positive_delta_is_rejected_with_a_helpful_message(self):
        # The classic error the book flags twice.
        with pytest.raises(ValueError, match="For a 25 delta put pass -0.25"):
            strike_from_put_delta(put_delta=0.25, sigma=0.10, **BASE)

    @pytest.mark.parametrize("bad", [-1.0, 0.0, -1.5])
    def test_delta_outside_the_open_interval_rejected(self, bad):
        with pytest.raises(ValueError, match="strictly between -1 and 0"):
            strike_from_put_delta(put_delta=bad, sigma=0.10, **BASE)

    def test_strike_increases_as_the_put_delta_gets_larger(self):
        strikes = [strike_from_put_delta(put_delta=-x, sigma=0.10, **BASE)
                   for x in (0.10, 0.25, 0.50, 0.75, 0.90)]
        assert strikes == sorted(strikes)


class TestStrikePlacementTaskE:
    """Practical F, Task E: each experiment the book asks you to reproduce."""

    def test_returns_a_row_per_delta_with_market_labels(self):
        smile = MalzSmile(atm=0.10)
        frame = strike_placement(smile, **BASE)
        assert list(frame["put_delta"]) == list(STANDARD_PUT_DELTAS)
        assert list(frame["label"]) == ["10% put", "25% put", "50% put", "25% call", "10% call"]

    def test_no_smile_gives_roughly_even_spacing_wider_on_the_topside(self):
        # The book: "With no volatility smile, the strikes for these deltas are
        # roughly equally spaced, with relatively slightly larger differences for
        # topside strikes due to the log-normality of the terminal spot distribution."
        frame = strike_placement(MalzSmile(atm=0.10), **BASE)
        atm = frame.loc[frame["put_delta"] == 0.50, "strike"].iloc[0]
        down = atm - frame.loc[frame["put_delta"] == 0.10, "strike"].iloc[0]
        up = frame.loc[frame["put_delta"] == 0.90, "strike"].iloc[0] - atm
        assert up > down
        assert up / down == pytest.approx(1.0, abs=0.25), "should be roughly even"

    def test_lower_vol_pulls_strikes_in(self):
        wide = strike_placement(MalzSmile(atm=0.20), **BASE)
        tight = strike_placement(MalzSmile(atm=0.05), **BASE)
        assert tight["pct_from_atm"].abs().max() < wide["pct_from_atm"].abs().max()

    def test_shorter_tenor_pulls_strikes_in(self):
        smile = MalzSmile(atm=0.10)
        long_dated = strike_placement(smile, spot=1.30, T=2.0, r_ccy1=0.02, r_ccy2=0.05)
        short_dated = strike_placement(smile, spot=1.30, T=0.1, r_ccy1=0.02, r_ccy2=0.05)
        assert short_dated["pct_from_atm"].abs().max() < long_dated["pct_from_atm"].abs().max()

    def test_higher_butterfly_pushes_strikes_out_more_in_the_wings(self):
        flat = strike_placement(MalzSmile(atm=0.10), **BASE)
        winged = strike_placement(MalzSmile(atm=0.10, fly25=0.02), **BASE)

        def spread(frame, delta):
            return abs(frame.loc[frame["put_delta"] == delta, "pct_from_atm"].iloc[0])

        # Both wings move further out...
        assert spread(winged, 0.10) > spread(flat, 0.10)
        assert spread(winged, 0.90) > spread(flat, 0.90)
        # ...and the 10 delta moves more than the 25 delta, because the butterfly
        # lifts volatility more out there.
        wing_shift = spread(winged, 0.10) - spread(flat, 0.10)
        body_shift = spread(winged, 0.25) - spread(flat, 0.25)
        assert wing_shift > body_shift

    def test_risk_reversal_places_strikes_asymmetrically(self):
        # The book: "further away from the ATM on the high side of the volatility
        # smile and closer to the ATM on the low side."
        flat = strike_placement(MalzSmile(atm=0.10), **BASE)
        skewed = strike_placement(MalzSmile(atm=0.10, rr25=-0.03), **BASE)

        def spread(frame, delta):
            return abs(frame.loc[frame["put_delta"] == delta, "pct_from_atm"].iloc[0])

        # Negative RR makes the downside rich, so the downside strike moves out
        # and the topside strike comes in.
        assert spread(skewed, 0.10) > spread(flat, 0.10)
        assert spread(skewed, 0.90) < spread(flat, 0.90)

    def test_higher_ccy1_rate_moves_the_smile_lower(self):
        # The book: "Moving CCY1 interest rates higher or CCY2 interest rates lower
        # causes the forward to move lower and hence the whole volatility smile
        # moves lower."
        #
        # True for strikes comfortably inside the attainable delta range. See
        # test_the_claim_breaks_down_near_the_attainability_cap for where it does not
        # hold - a boundary effect the book's examples never reach.
        smile = MalzSmile(atm=0.10, rr25=-0.02, fly25=0.005)
        deltas = (0.10, 0.25, 0.50, 0.75)
        base = strike_placement(smile, spot=1.30, T=1.0, r_ccy1=0.02, r_ccy2=0.05,
                                put_deltas=deltas)
        high_r1 = strike_placement(smile, spot=1.30, T=1.0, r_ccy1=0.10, r_ccy2=0.05,
                                   put_deltas=deltas)
        assert (high_r1["strike"] < base["strike"]).all()

    def test_the_claim_breaks_down_near_the_attainability_cap(self):
        """A boundary effect worth knowing about, not a bug.

        A put delta can never exceed exp(-r1*T) in absolute terms. As the CCY1 rate
        rises, a 90 delta put approaches that ceiling, ``exp(r1*T)*delta + 1``
        collapses toward zero, and the inverse normal dives - pushing the strike OUT
        faster than the lower forward pulls it IN.

        So the book's blanket statement holds for the body of the smile and reverses
        in the deep wing once the rate is high enough. The book's own examples use
        modest rates and never reach the turn.
        """
        smile = MalzSmile(atm=0.10, rr25=-0.02, fly25=0.005)
        deep = (0.90,)
        base = strike_placement(smile, spot=1.30, T=1.0, r_ccy1=0.02, r_ccy2=0.05,
                                put_deltas=deep)
        high_r1 = strike_placement(smile, spot=1.30, T=1.0, r_ccy1=0.10, r_ccy2=0.05,
                                   put_deltas=deep)
        # 0.90 is still attainable at r1 = 10% (the cap is about 0.9048)...
        assert max_attainable_put_delta(0.10, 1.0) > 0.90
        # ...but the strike moves the other way.
        assert high_r1["strike"].iloc[0] > base["strike"].iloc[0]

    def test_deltas_beyond_the_cap_are_omitted_rather_than_raising(self):
        smile = MalzSmile(atm=0.10)
        # At r1 = 20% over 2 years the cap is about 0.670, so 0.75 and 0.90 vanish.
        frame = strike_placement(smile, spot=1.30, T=2.0, r_ccy1=0.20, r_ccy2=0.05)
        assert max_attainable_put_delta(0.20, 2.0) == pytest.approx(0.6703, abs=1e-3)
        assert list(frame["put_delta"]) == [0.10, 0.25, 0.50]

    def test_lower_ccy2_rate_moves_the_whole_smile_lower(self):
        smile = MalzSmile(atm=0.10, rr25=-0.02, fly25=0.005)
        base = strike_placement(smile, spot=1.30, T=1.0, r_ccy1=0.02, r_ccy2=0.05)
        low_r2 = strike_placement(smile, spot=1.30, T=1.0, r_ccy1=0.02, r_ccy2=0.00)
        assert (low_r2["strike"] < base["strike"]).all()

    def test_higher_ccy2_rate_moves_the_whole_smile_higher(self):
        smile = MalzSmile(atm=0.10, rr25=-0.02, fly25=0.005)
        base = strike_placement(smile, spot=1.30, T=1.0, r_ccy1=0.02, r_ccy2=0.05)
        high_r2 = strike_placement(smile, spot=1.30, T=1.0, r_ccy1=0.02, r_ccy2=0.12)
        assert (high_r2["strike"] > base["strike"]).all()

    def test_strikes_are_ascending_in_delta(self):
        frame = strike_placement(MalzSmile(atm=0.10, rr25=-0.02, fly25=0.005), **BASE)
        assert list(frame["strike"]) == sorted(frame["strike"])

    def test_atm_row_is_the_zero_reference(self):
        frame = strike_placement(MalzSmile(atm=0.10, rr25=-0.02), **BASE)
        assert frame.loc[frame["put_delta"] == 0.50, "pct_from_atm"].iloc[0] == pytest.approx(0.0)


class TestSmileByStrike:
    def test_sorted_ascending_in_strike(self):
        frame = smile_by_strike(MalzSmile(atm=0.10, rr25=-0.02, fly25=0.005), **BASE)
        assert list(frame["strike"]) == sorted(frame["strike"])

    def test_volatilities_match_the_delta_smile(self):
        smile = MalzSmile(atm=0.10, rr25=-0.02, fly25=0.005)
        frame = smile_by_strike(smile, **BASE)
        assert np.allclose(frame["volatility"], smile.volatility(frame["put_delta"].to_numpy()))

    def test_no_finite_strike_at_the_extremes(self):
        # Practical F, Task D: "It is not possible to find strikes for 0 or 100
        # delta options", which is why the sweep stops just short of both.
        with pytest.raises(ValueError):
            strike_from_put_delta(put_delta=-1.0, sigma=0.10, **BASE)
        with pytest.raises(ValueError):
            strike_from_put_delta(put_delta=0.0, sigma=0.10, **BASE)
