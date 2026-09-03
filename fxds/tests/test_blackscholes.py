"""Tests for fxds.blackscholes - Practical C (Ch. 5-6).

Every acceptance value the book states is asserted here, with a comment naming the
practical and task it came from.
"""

from __future__ import annotations

import numpy as np
import pytest

from fxds.blackscholes import (
    d1_d2,
    delta_closed_form,
    delta_finite_difference,
    forward,
    gamma_closed_form,
    payoff,
    price,
    put_call_parity_rhs,
    vega_closed_form,
    vega_finite_difference,
    vega_market,
)
from fxds.conventions import OptionType

# The book's reference contract: Practical C, Task A, Step 2.
BOOK = dict(spot=1.0, strike=1.0, T=1.0, r_ccy1=0.0, r_ccy2=0.0, sigma=0.10)


class TestForward:
    def test_equal_rates_give_forward_equal_to_spot(self):
        # Practical C, Task A, Step 1: "note what happens when rCCY1 = rCCY2".
        assert forward(1.30, 1.0, 0.03, 0.03) == pytest.approx(1.30)

    def test_higher_ccy2_rate_gives_positive_drift(self):
        # Ch. 5: r2 > r1 pushes the forward above spot.
        assert forward(1.30, 1.0, 0.00, 0.10) > 1.30

    def test_higher_ccy1_rate_gives_negative_drift(self):
        # Ch. 5: r1 > r2 pulls the forward below spot.
        assert forward(1.30, 1.0, 0.10, 0.00) < 1.30

    def test_matches_exponential_formula(self):
        assert forward(1.30, 2.0, 0.02, 0.05) == pytest.approx(1.30 * np.exp(0.03 * 2.0))


class TestPrice:
    def test_book_acceptance_value(self):
        # Practical C, Task A, Step 2: S = K = 1.0, T = 1.0, sigma = 10%, zero
        # rates => "very slightly under 0.04 pips (0.0399 pips)".
        assert price(OptionType.CALL, **BOOK) == pytest.approx(0.0399, abs=5e-5)

    def test_atm_call_and_put_equal_when_strike_is_the_forward(self):
        # Practical C, Task A, Step 4: strike at the forward => call price == put.
        spot, T, r1, r2, sigma = 1.30, 1.0, 0.02, 0.05, 0.12
        k = forward(spot, T, r1, r2)
        call = price(OptionType.CALL, spot, k, T, r1, r2, sigma)
        put = price(OptionType.PUT, spot, k, T, r1, r2, sigma)
        assert call == pytest.approx(put)

    def test_example_1_higher_strike_cheapens_call_richens_put(self):
        # Practical C, Task A, Step 2, Example 1.
        base = dict(spot=100.0, T=1.0, r_ccy1=0.0, r_ccy2=0.0, sigma=0.10)
        assert price(OptionType.CALL, strike=110.0, **base) < price(
            OptionType.CALL, strike=100.0, **base
        )
        assert price(OptionType.PUT, strike=110.0, **base) > price(
            OptionType.PUT, strike=100.0, **base
        )

    @pytest.mark.parametrize("option_type", [OptionType.CALL, OptionType.PUT])
    def test_example_2_more_vol_or_time_richens_both_sides(self, option_type):
        # Practical C, Task A, Step 2, Example 2: a wider distribution brings
        # larger payoffs into play, so BOTH calls and puts get more expensive.
        base = dict(spot=1.25, strike=1.25, r_ccy1=0.0, r_ccy2=0.0)
        low_vol = price(option_type, T=1.0, sigma=0.10, **base)
        high_vol = price(option_type, T=1.0, sigma=0.20, **base)
        assert high_vol > low_vol

        short_t = price(option_type, T=0.5, sigma=0.10, **base)
        long_t = price(option_type, T=2.0, sigma=0.10, **base)
        assert long_t > short_t

    @pytest.mark.parametrize("option_type", [OptionType.CALL, OptionType.PUT])
    def test_example_3_equal_rates_higher_cheapens_both_via_discounting(self, option_type):
        # Practical C, Task A, Step 2, Example 3: raising both rates to the same
        # level leaves the forward unchanged but increases discounting.
        base = dict(spot=1.0, strike=1.0, T=1.0, sigma=0.10)
        assert forward(1.0, 1.0, 0.0, 0.0) == pytest.approx(forward(1.0, 1.0, 0.08, 0.08))
        low = price(option_type, r_ccy1=0.0, r_ccy2=0.0, **base)
        high = price(option_type, r_ccy1=0.08, r_ccy2=0.08, **base)
        assert high < low

    def test_prices_are_non_negative(self):
        for k in [0.5, 0.9, 1.0, 1.1, 2.0]:
            assert price(OptionType.CALL, 1.0, k, 1.0, 0.01, 0.02, 0.1) >= 0
            assert price(OptionType.PUT, 1.0, k, 1.0, 0.01, 0.02, 0.1) >= 0

    @pytest.mark.parametrize("bad_spot", [0.0, -1.0])
    def test_rejects_nonpositive_spot(self, bad_spot):
        with pytest.raises(ValueError, match="Spot must be positive"):
            price(OptionType.CALL, bad_spot, 1.0, 1.0, 0.0, 0.0, 0.1)

    @pytest.mark.parametrize("bad_strike", [0.0, -1.0])
    def test_rejects_nonpositive_strike(self, bad_strike):
        with pytest.raises(ValueError, match="Strike must be positive"):
            price(OptionType.CALL, 1.0, bad_strike, 1.0, 0.0, 0.0, 0.1)


class TestExpiryAndVolGuards:
    """Practical C, Task B: non-positive T or sigma must return the payoff.

    The book's printed VBA has the comparison inverted; see notes/deviations.md.
    """

    @pytest.mark.parametrize("T", [0.0, -1.0])
    def test_expired_call_returns_payoff(self, T):
        assert price(OptionType.CALL, 1.10, 1.0, T, 0.0, 0.0, 0.1) == pytest.approx(0.10)
        assert price(OptionType.CALL, 0.90, 1.0, T, 0.0, 0.0, 0.1) == pytest.approx(0.0)

    @pytest.mark.parametrize("T", [0.0, -1.0])
    def test_expired_put_returns_payoff(self, T):
        assert price(OptionType.PUT, 0.90, 1.0, T, 0.0, 0.0, 0.1) == pytest.approx(0.10)
        assert price(OptionType.PUT, 1.10, 1.0, T, 0.0, 0.0, 0.1) == pytest.approx(0.0)

    @pytest.mark.parametrize("sigma", [0.0, -0.1])
    def test_zero_vol_returns_payoff_against_the_forward(self, sigma):
        # With no volatility spot follows the forward path exactly (Ch. 5), so the
        # option is worth its discounted payoff against the forward.
        spot, strike, T, r1, r2 = 1.0, 0.90, 1.0, 0.0, 0.0
        expected = payoff(OptionType.CALL, forward(spot, T, r1, r2), strike)
        assert price(OptionType.CALL, spot, strike, T, r1, r2, sigma) == pytest.approx(expected)

    def test_guard_does_not_fire_on_valid_inputs(self):
        # Regression guard for the book's inverted comparison: a normal contract
        # must NOT collapse to its intrinsic value.
        intrinsic = payoff(OptionType.CALL, 1.0, 1.0)
        assert price(OptionType.CALL, **BOOK) > intrinsic


class TestPutCallParity:
    def test_discounted_parity_holds(self):
        # Practical C, Task A, Step 4.
        spot, strike, T, r1, r2, sigma = 1.0, 1.05, 1.0, 0.02, 0.05, 0.10
        call = price(OptionType.CALL, spot, strike, T, r1, r2, sigma)
        put = price(OptionType.PUT, spot, strike, T, r1, r2, sigma)
        assert call - put == pytest.approx(put_call_parity_rhs(spot, strike, T, r1, r2))

    def test_undiscounted_parity_fails_when_rates_are_nonzero(self):
        # The point of the task: the undiscounted form is wrong by exactly the
        # CCY2 discount factor, because (F - K) is realised in the future.
        spot, strike, T, r1, r2, sigma = 1.0, 1.05, 1.0, 0.02, 0.05, 0.10
        call = price(OptionType.CALL, spot, strike, T, r1, r2, sigma)
        put = price(OptionType.PUT, spot, strike, T, r1, r2, sigma)
        naive = put_call_parity_rhs(spot, strike, T, r1, r2, discounted=False)
        assert call - put != pytest.approx(naive, rel=1e-6)
        # And the discrepancy is precisely the discount factor.
        assert (call - put) == pytest.approx(np.exp(-r2 * T) * naive)

    def test_undiscounted_parity_coincides_when_ccy2_rate_is_zero(self):
        spot, strike, T, r1, r2, sigma = 1.0, 1.05, 1.0, 0.02, 0.0, 0.10
        call = price(OptionType.CALL, spot, strike, T, r1, r2, sigma)
        put = price(OptionType.PUT, spot, strike, T, r1, r2, sigma)
        assert call - put == pytest.approx(
            put_call_parity_rhs(spot, strike, T, r1, r2, discounted=False)
        )

    @pytest.mark.parametrize("seed", range(20))
    def test_parity_as_property_over_random_inputs(self, seed):
        # Property test across random valid inputs, per the testing brief.
        rng = np.random.default_rng(seed)
        spot = rng.uniform(0.5, 150.0)
        strike = spot * rng.uniform(0.6, 1.6)
        T = rng.uniform(0.01, 5.0)
        r1 = rng.uniform(-0.02, 0.12)
        r2 = rng.uniform(-0.02, 0.12)
        sigma = rng.uniform(0.02, 0.60)

        call = price(OptionType.CALL, spot, strike, T, r1, r2, sigma)
        put = price(OptionType.PUT, spot, strike, T, r1, r2, sigma)
        expected = put_call_parity_rhs(spot, strike, T, r1, r2)
        assert call - put == pytest.approx(expected, rel=1e-9, abs=1e-12)


class TestGreeks:
    def test_book_delta_acceptance_value(self):
        # Practical C, Task C: delta "close to 50%".
        delta = delta_closed_form(OptionType.CALL, **BOOK)
        assert delta == pytest.approx(0.52, abs=0.03)

    def test_book_vega_acceptance_value(self):
        # Practical C, Task C: vega "a shade under 0.40%".
        vega = vega_market(**BOOK)
        assert vega == pytest.approx(0.00399, abs=5e-5)
        assert vega < 0.0040

    def test_put_delta_is_negative(self):
        # Ch. 6: the true put delta is negative. The market quotes it positive.
        assert delta_closed_form(OptionType.PUT, **BOOK) < 0

    def test_call_and_put_delta_differ_by_the_ccy1_discount_factor(self):
        # Ch. 6, put-call parity in greek terms: delta_put = delta_call - df_ccy1.
        args = dict(spot=1.30, strike=1.25, T=2.0, r_ccy1=0.03, r_ccy2=0.01, sigma=0.15)
        call_d = delta_closed_form(OptionType.CALL, **args)
        put_d = delta_closed_form(OptionType.PUT, **args)
        assert call_d - put_d == pytest.approx(np.exp(-args["r_ccy1"] * args["T"]))

    def test_call_and_put_vega_are_identical(self):
        # Ch. 6: a forward has no volatility exposure, so vega is shared.
        args = dict(spot=1.30, strike=1.25, T=2.0, r_ccy1=0.03, r_ccy2=0.01, sigma=0.15)
        assert vega_finite_difference(OptionType.CALL, **args) == pytest.approx(
            vega_finite_difference(OptionType.PUT, **args)
        )

    def test_vega_is_positive(self):
        # Ch. 6: long vanillas are always long vega.
        assert vega_closed_form(**BOOK) > 0

    def test_vega_scales_with_root_time(self):
        # Practical C, Task D: "look at the formula for vega and confirm the
        # relationship". Quadrupling T should roughly double vega.
        one_year = vega_closed_form(1.0, 1.0, 1.0, 0.0, 0.0, 0.10)
        four_year = vega_closed_form(1.0, 1.0, 4.0, 0.0, 0.0, 0.10)
        assert four_year / one_year == pytest.approx(2.0, rel=0.02)

    def test_gamma_is_positive(self):
        # Ch. 6: long vanillas are always long gamma.
        assert gamma_closed_form(**BOOK) > 0

    def test_gamma_is_the_gradient_of_delta(self):
        # Practical C, Task D notes the gradient of the delta chart is gamma.
        args = dict(spot=1.0, strike=1.0, T=1.0, r_ccy1=0.0, r_ccy2=0.0, sigma=0.10)
        h = 1e-5
        numeric = (
            delta_closed_form(OptionType.CALL, **{**args, "spot": args["spot"] + h})
            - delta_closed_form(OptionType.CALL, **{**args, "spot": args["spot"] - h})
        ) / (2 * h)
        assert numeric == pytest.approx(gamma_closed_form(**args), rel=1e-5)

    def test_peak_vega_sits_near_the_strike(self):
        # Ch. 6: peak vega occurs at the strike, where optionality is maximised.
        strike = 1.0
        spots = np.linspace(0.7, 1.4, 351)
        vegas = [vega_closed_form(s, strike, 1.0, 0.0, 0.0, 0.10) for s in spots]
        assert spots[int(np.argmax(vegas))] == pytest.approx(strike, abs=0.02)


class TestFiniteDifferenceAgreement:
    """Practical C, Task C: the two methods must agree."""

    @pytest.mark.parametrize("option_type", [OptionType.CALL, OptionType.PUT])
    def test_delta_methods_agree(self, option_type):
        args = dict(spot=1.30, strike=1.25, T=2.0, r_ccy1=0.03, r_ccy2=0.01, sigma=0.15)
        closed = delta_closed_form(option_type, **args)
        finite = delta_finite_difference(option_type, **args, spot_flex=1e-6)
        assert finite == pytest.approx(closed, rel=1e-6)

    @pytest.mark.parametrize("option_type", [OptionType.CALL, OptionType.PUT])
    def test_vega_methods_agree(self, option_type):
        args = dict(spot=1.30, strike=1.25, T=2.0, r_ccy1=0.03, r_ccy2=0.01, sigma=0.15)
        closed = vega_market(**args)
        finite = vega_finite_difference(option_type, **args, vol_flex=1e-6)
        assert finite == pytest.approx(closed, rel=1e-6)

    def test_bump_size_sweep_degrades_at_both_extremes(self):
        # Practical C, Task C asks what happens as the flex grows and shrinks.
        # Large bumps carry truncation error from the curvature of the price;
        # tiny bumps lose precision to floating-point cancellation. The best
        # accuracy sits in the middle, which is the point the notebook plots.
        args = dict(spot=1.0, strike=1.0, T=1.0, r_ccy1=0.0, r_ccy2=0.0, sigma=0.10)
        exact = delta_closed_form(OptionType.CALL, **args)

        def rel_error(flex: float) -> float:
            approx = delta_finite_difference(OptionType.CALL, **args, spot_flex=flex)
            return abs(approx - exact) / abs(exact)

        huge, sweet, tiny = rel_error(1e-1), rel_error(1e-6), rel_error(1e-13)
        assert sweet < huge, "a large bump should be less accurate than 1e-6"
        assert sweet < tiny, "an over-small bump should be less accurate than 1e-6"

    def test_rejects_nonpositive_flex(self):
        with pytest.raises(ValueError, match="must be positive"):
            delta_finite_difference(OptionType.CALL, **BOOK, spot_flex=0.0)
        with pytest.raises(ValueError, match="must be positive"):
            vega_finite_difference(OptionType.CALL, **BOOK, vol_flex=-1e-6)


class TestD1D2:
    def test_d2_is_d1_less_sigma_root_t(self):
        d1, d2 = d1_d2(1.30, 1.25, 2.0, 0.03, 0.01, 0.15)
        assert d1 - d2 == pytest.approx(0.15 * np.sqrt(2.0))

    def test_d1_is_zero_at_the_zero_delta_straddle_strike(self):
        # Ch. 8: the zero-delta straddle strike is where N(d1) = 1/2, i.e. d1 = 0.
        spot, T, r1, r2, sigma = 1.30, 1.0, 0.02, 0.05, 0.12
        strike = spot * np.exp((r2 - r1 + sigma**2 / 2) * T)
        d1, _ = d1_d2(spot, strike, T, r1, r2, sigma)
        assert d1 == pytest.approx(0.0, abs=1e-12)


class TestPayoff:
    def test_call_payoff(self):
        assert payoff(OptionType.CALL, 1.10, 1.0) == pytest.approx(0.10)
        assert payoff(OptionType.CALL, 0.90, 1.0) == pytest.approx(0.0)

    def test_put_payoff(self):
        assert payoff(OptionType.PUT, 0.90, 1.0) == pytest.approx(0.10)
        assert payoff(OptionType.PUT, 1.10, 1.0) == pytest.approx(0.0)
