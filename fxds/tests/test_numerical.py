"""Tests for fxds.numerical - Practical B (Ch. 5)."""

from __future__ import annotations

import numpy as np
import pytest

from fxds.blackscholes import forward
from fxds.conventions import OptionType
from fxds.numerical import (
    call_payoff,
    integrate_payoff,
    long_forward_payoff,
    price_vanilla,
    put_payoff,
    short_forward_payoff,
    terminal_distribution,
)


class TestTerminalDistribution:
    def test_grid_spans_plus_minus_five_sd_in_tenth_steps(self):
        # Practical B, Task A, Step 1: -5 to +5 standard deviations in 0.1 steps.
        table = terminal_distribution(100.0, 1.0, 0.0, 0.0, 0.10)
        assert len(table) == 101
        assert table["sd"].iloc[0] == pytest.approx(-5.0)
        assert table["sd"].iloc[-1] == pytest.approx(5.0)
        assert np.allclose(np.diff(table["sd"]), 0.1)

    def test_expected_return_carries_the_ito_correction(self):
        # Ch. 5: mu = (r2 - r1 - sigma^2 / 2) * T.
        spot, T, r1, r2, sigma = 100.0, 2.0, 0.01, 0.04, 0.20
        table = terminal_distribution(spot, T, r1, r2, sigma)
        expected_mu = (r2 - r1 - sigma**2 / 2) * T
        centre = table.loc[table["sd"].abs().idxmin()]
        assert centre["return_level"] == pytest.approx(expected_mu)

    def test_standard_deviation_is_sigma_root_t(self):
        spot, T, sigma = 100.0, 4.0, 0.20
        table = terminal_distribution(spot, T, 0.0, 0.0, sigma)
        one_sd = table.loc[(table["sd"] - 1.0).abs().idxmin()]
        centre = table.loc[table["sd"].abs().idxmin()]
        assert one_sd["return_level"] - centre["return_level"] == pytest.approx(
            sigma * np.sqrt(T)
        )

    def test_spot_levels_are_lognormal_and_strictly_positive(self):
        # Ch. 5: relative changes mean spot can never reach zero.
        table = terminal_distribution(100.0, 5.0, 0.0, 0.0, 0.30)
        assert (table["spot_level"] > 0).all()
        assert table["spot_level"].is_monotonic_increasing

    def test_lognormal_tail_is_longer_on_the_topside(self):
        # Ch. 5: a move 1.0 -> 0.5 is equal and opposite to 1.0 -> 2.0 in log space,
        # so in regular spot space the topside tail stretches further.
        spot = 100.0
        table = terminal_distribution(spot, 1.0, 0.0, 0.0, 0.10)
        up = table["spot_level"].iloc[-1] - spot
        down = spot - table["spot_level"].iloc[0]
        assert up > down

    def test_probabilities_are_bucket_differences_aligned_to_the_next_row(self):
        # Practical B, Task A, Step 2: the probability on a row is the chance of
        # finishing between that row's spot level and the NEXT row's.
        table = terminal_distribution(100.0, 1.0, 0.0, 0.0, 0.10)
        assert np.isnan(table["probability"].iloc[-1])
        assert table["probability"].iloc[:-1].notna().all()
        assert (table["probability"].iloc[:-1] > 0).all()

    def test_probabilities_sum_to_almost_one(self):
        # Five standard deviations each side leaves about 6e-7 in the tails.
        table = terminal_distribution(100.0, 1.0, 0.0, 0.0, 0.10)
        total = table["probability"].sum()
        assert total == pytest.approx(1.0, abs=1e-6)
        assert total < 1.0

    def test_shorter_maturity_or_lower_vol_tightens_the_distribution(self):
        # Practical B, Task A: the four behaviours the book asks you to observe.
        wide = terminal_distribution(100.0, 1.0, 0.0, 0.0, 0.20)
        tight_vol = terminal_distribution(100.0, 1.0, 0.0, 0.0, 0.05)
        tight_time = terminal_distribution(100.0, 0.25, 0.0, 0.0, 0.20)

        def width(t):
            return t["spot_level"].iloc[-1] - t["spot_level"].iloc[0]

        assert width(tight_vol) < width(wide)
        assert width(tight_time) < width(wide)

    def test_higher_ccy2_rate_shifts_the_distribution_higher(self):
        base = terminal_distribution(100.0, 1.0, 0.0, 0.0, 0.10)
        higher = terminal_distribution(100.0, 1.0, 0.0, 0.10, 0.10)
        assert higher["spot_level"].median() > base["spot_level"].median()

    def test_higher_ccy1_rate_shifts_the_distribution_lower(self):
        base = terminal_distribution(100.0, 1.0, 0.0, 0.0, 0.10)
        lower = terminal_distribution(100.0, 1.0, 0.10, 0.0, 0.10)
        assert lower["spot_level"].median() < base["spot_level"].median()

    @pytest.mark.parametrize(
        "kwargs, match",
        [
            (dict(spot=0.0), "Spot must be positive"),
            (dict(T=0.0), "Time to expiry must be positive"),
            (dict(sigma=0.0), "Volatility must be positive"),
            (dict(sd_step=0.0), "must both be positive"),
        ],
    )
    def test_rejects_invalid_inputs(self, kwargs, match):
        args = dict(spot=100.0, T=1.0, r_ccy1=0.0, r_ccy2=0.0, sigma=0.10)
        args.update(kwargs)
        with pytest.raises(ValueError, match=match):
            terminal_distribution(**args)


class TestPayoffs:
    def test_vanilla_payoffs(self):
        spots = np.array([80.0, 100.0, 120.0])
        assert np.allclose(call_payoff(100.0)(spots), [0.0, 0.0, 20.0])
        assert np.allclose(put_payoff(100.0)(spots), [20.0, 0.0, 0.0])

    def test_forward_payoffs_are_linear_and_opposite(self):
        spots = np.array([80.0, 100.0, 120.0])
        assert np.allclose(long_forward_payoff(100.0)(spots), [-20.0, 0.0, 20.0])
        assert np.allclose(
            short_forward_payoff(100.0)(spots), -long_forward_payoff(100.0)(spots)
        )


class TestIntegration:
    def test_book_test_1_forward_struck_at_the_forward_is_worth_nothing(self):
        # Practical B, Testing, Test 1: "A forward payoff struck at the forward
        # should give (approximately) zero value".
        spot, T, r1, r2, sigma = 1.30, 1.0, 0.02, 0.05, 0.12
        fwd = forward(spot, T, r1, r2)
        result = integrate_payoff(long_forward_payoff(fwd), spot, T, r1, r2, sigma)
        assert result.value_ccy2_pips == pytest.approx(0.0, abs=1e-4)

    def test_book_test_2_atm_call_prices_just_under_four_percent(self):
        # Practical B, Testing, Test 2: S = K = 100, zero rates, T = 1.0 => "very
        # slightly under 4.00 CCY1%". (Sigma is not stated in the text; 10% is the
        # value consistent with that figure and with Practical C - see
        # notes/deviations.md.)
        result = price_vanilla(OptionType.CALL, 100.0, 100.0, 1.0, 0.0, 0.0, 0.10)
        as_percent = result.value_ccy1_pct * 100
        assert as_percent == pytest.approx(4.0, abs=0.05)
        assert as_percent < 4.0

    def test_short_forward_is_the_negative_of_the_long(self):
        spot, T, r1, r2, sigma = 1.30, 1.0, 0.02, 0.05, 0.12
        long_v = integrate_payoff(long_forward_payoff(1.25), spot, T, r1, r2, sigma)
        short_v = integrate_payoff(short_forward_payoff(1.25), spot, T, r1, r2, sigma)
        assert long_v.value_ccy2_pips == pytest.approx(-short_v.value_ccy2_pips)

    def test_discounting_is_applied_on_top_of_the_maturity_value(self):
        spot, T, r1, r2, sigma = 100.0, 2.0, 0.01, 0.06, 0.15
        result = price_vanilla(OptionType.CALL, spot, 100.0, T, r1, r2, sigma)
        assert result.value_ccy2_pips == pytest.approx(
            result.undiscounted_ccy2_pips * np.exp(-r2 * T)
        )
        assert result.value_ccy2_pips < result.undiscounted_ccy2_pips

    def test_ccy1_pct_is_the_pips_value_divided_by_spot(self):
        result = price_vanilla(OptionType.CALL, 1.30, 1.30, 1.0, 0.0, 0.0, 0.10)
        assert result.value_ccy1_pct == pytest.approx(result.value_ccy2_pips / 1.30)

    def test_table_carries_the_working(self):
        result = price_vanilla(OptionType.CALL, 100.0, 100.0, 1.0, 0.0, 0.0, 0.10)
        for column in ("spot_level", "probability", "payoff", "average_payoff", "weighted_payoff"):
            assert column in result.table.columns

    def test_finer_grid_converges(self):
        # Refining the step must monotonically improve the estimate. This is the
        # discretisation error, and it is why the cross-validation test states a
        # tolerance rather than asserting equality.
        from fxds.blackscholes import price

        args = (100.0, 100.0, 1.0, 0.0, 0.0, 0.10)
        exact = price(OptionType.CALL, *args)
        errors = [
            abs(price_vanilla(OptionType.CALL, *args, sd_step=step).value_ccy2_pips - exact)
            for step in (0.5, 0.2, 0.1, 0.05, 0.01)
        ]
        assert errors == sorted(errors, reverse=True)

    def test_widening_beyond_five_sd_changes_nothing_material(self):
        # The tail past five standard deviations is negligible, which is exactly
        # why the book picks that range.
        args = (100.0, 100.0, 1.0, 0.0, 0.0, 0.10)
        five = price_vanilla(OptionType.CALL, *args, sd_range=5.0).value_ccy2_pips
        eight = price_vanilla(OptionType.CALL, *args, sd_range=8.0).value_ccy2_pips
        assert five == pytest.approx(eight, rel=1e-5)
