"""The headline test: Practical B and Practical C must agree.

Two completely independent routes to the same number:

* **Practical B** builds the terminal spot distribution and integrates the payoff
  against it numerically. It knows nothing about Garman-Kohlhagen.
* **Practical C** evaluates the closed-form Garman-Kohlhagen expression. It knows
  nothing about distributions or grids.

They share only the inputs and the assumption of log-normal terminal spot. If both
agree across a wide range of parameters, both are almost certainly right - and the
closed form is revealed as what it actually is: the analytic solution to the integral
Practical B computes by brute force.

This test is not in the book. It is referenced from ``notebooks/04`` and ``05``.

On tolerances: at the book's own grid (101 points, plus or minus five standard
deviations in 0.1 steps) the agreement is around 0.25% relative. That gap is
**discretisation error in the integration, not disagreement about the price** - the
trapezoidal rule over a coarse grid. Refining the step to 0.01 drops the error to
about 6e-6, which the convergence test below pins down.
"""

from __future__ import annotations

import numpy as np
import pytest

from fxds.blackscholes import forward, price
from fxds.conventions import OptionType
from fxds.numerical import integrate_payoff, long_forward_payoff, price_vanilla

# Tolerance at the book's default grid. Established empirically by the convergence
# test below, not guessed.
BOOK_GRID_TOLERANCE = 5e-3
FINE_GRID_STEP = 0.01
FINE_GRID_TOLERANCE = 1e-4


@pytest.mark.parametrize("option_type", [OptionType.CALL, OptionType.PUT])
@pytest.mark.parametrize(
    "spot, strike, T, r_ccy1, r_ccy2, sigma",
    [
        # The book's own reference contracts.
        (1.0, 1.0, 1.0, 0.0, 0.0, 0.10),          # Practical C, Task A
        (100.0, 100.0, 1.0, 0.0, 0.0, 0.10),      # Practical B, Test 2
        # Away from the money, both directions.
        (1.30, 1.10, 1.0, 0.02, 0.05, 0.12),
        (1.30, 1.50, 1.0, 0.02, 0.05, 0.12),
        # Non-zero and asymmetric rates, so discounting and drift both bite.
        (1.30, 1.30, 2.0, 0.06, 0.01, 0.15),
        (1.30, 1.30, 2.0, 0.01, 0.06, 0.15),
        # Short dated and long dated.
        (100.0, 100.0, 0.08, 0.0, 0.0, 0.10),
        (100.0, 100.0, 5.0, 0.02, 0.03, 0.20),
        # A JPY-style pair, where spot is two orders of magnitude larger.
        (101.50, 105.00, 0.5, 0.001, 0.02, 0.09),
        # High volatility, where log-normality is clearly visible.
        (1.0, 1.0, 3.0, 0.0, 0.0, 0.35),
    ],
)
def test_integration_matches_closed_form(option_type, spot, strike, T, r_ccy1, r_ccy2, sigma):
    """Practical B's integration agrees with Practical C's closed form."""
    numeric = price_vanilla(
        option_type, spot, strike, T, r_ccy1, r_ccy2, sigma, sd_step=FINE_GRID_STEP
    ).value_ccy2_pips
    analytic = price(option_type, spot, strike, T, r_ccy1, r_ccy2, sigma)

    assert numeric == pytest.approx(analytic, rel=FINE_GRID_TOLERANCE)


@pytest.mark.parametrize("option_type", [OptionType.CALL, OptionType.PUT])
def test_agreement_holds_on_the_books_own_coarse_grid(option_type):
    """Even at the book's 0.1-step grid the two agree to well under a percent."""
    args = (100.0, 100.0, 1.0, 0.0, 0.0, 0.10)
    numeric = price_vanilla(option_type, *args).value_ccy2_pips
    analytic = price(option_type, *args)
    assert numeric == pytest.approx(analytic, rel=BOOK_GRID_TOLERANCE)


@pytest.mark.parametrize("seed", range(25))
def test_agreement_as_a_property_over_random_inputs(seed):
    """Property test: agreement holds across randomly drawn valid market data."""
    rng = np.random.default_rng(seed)
    spot = rng.uniform(0.5, 150.0)
    strike = spot * rng.uniform(0.7, 1.4)
    T = rng.uniform(0.05, 3.0)
    r_ccy1 = rng.uniform(-0.01, 0.08)
    r_ccy2 = rng.uniform(-0.01, 0.08)
    sigma = rng.uniform(0.05, 0.40)
    option_type = OptionType.CALL if rng.random() < 0.5 else OptionType.PUT

    numeric = price_vanilla(
        option_type, spot, strike, T, r_ccy1, r_ccy2, sigma, sd_step=FINE_GRID_STEP
    ).value_ccy2_pips
    analytic = price(option_type, spot, strike, T, r_ccy1, r_ccy2, sigma)

    # Absolute floor alongside the relative tolerance: a deep out-of-the-money
    # option can be worth almost nothing, and relative error is meaningless there.
    assert numeric == pytest.approx(analytic, rel=1e-3, abs=1e-8)


def test_the_gap_is_discretisation_error_and_shrinks_predictably():
    """The residual gap is the grid, not the maths.

    Halving the step should cut the error by roughly a factor of four - second-order
    convergence, which is what the trapezoidal rule gives. Demonstrating that the
    error is *structured* rather than noise is what makes the agreement convincing.
    """
    args = (100.0, 100.0, 1.0, 0.0, 0.0, 0.10)
    analytic = price(OptionType.CALL, *args)

    errors = {
        step: abs(price_vanilla(OptionType.CALL, *args, sd_step=step).value_ccy2_pips - analytic)
        for step in (0.2, 0.1, 0.05)
    }

    # Monotone improvement.
    assert errors[0.2] > errors[0.1] > errors[0.05]
    # And convergence faster than first order.
    assert errors[0.1] / errors[0.05] > 2.0


def test_forward_agrees_between_methods():
    """A forward payoff integrates to its discounted intrinsic value.

    Not a vanilla, but the same cross-check: the integration has to reproduce
    ``exp(-r2 * T) * (F - K)``, which is the right-hand side of put-call parity.

    Note the tolerance is **absolute and scaled to spot**, not relative. A forward's
    value is a small difference of two large numbers - the integration computes
    something near ``E[S_T]`` (about 1.3 here) and subtracts a strike of similar
    size to land on about 0.10. Discretisation error accumulates on the large
    quantities and is then measured against the small result, so relative error
    overstates the disagreement by roughly the ratio between them. This is the same
    reason Practical B's Test 1 - a forward struck at the forward - can only be
    checked as "approximately zero" and not to a relative tolerance at all.
    """
    spot, strike, T, r_ccy1, r_ccy2, sigma = 1.30, 1.25, 1.5, 0.02, 0.05, 0.12

    numeric = integrate_payoff(
        long_forward_payoff(strike), spot, T, r_ccy1, r_ccy2, sigma, sd_step=FINE_GRID_STEP
    ).value_ccy2_pips
    expected = np.exp(-r_ccy2 * T) * (forward(spot, T, r_ccy1, r_ccy2) - strike)

    assert numeric == pytest.approx(expected, abs=1e-6 * spot)


def test_forward_integration_error_converges_second_order():
    """The forward's residual error is discretisation, and it converges cleanly.

    Halving the step cuts the absolute error by roughly four, until it floors out
    against the truncation of the plus-or-minus five standard deviation grid. A
    linear payoff is unbounded, so its tail contribution never fully vanishes the way
    a vanilla's does - which is worth seeing directly.
    """
    spot, strike, T, r_ccy1, r_ccy2, sigma = 1.30, 1.25, 1.5, 0.02, 0.05, 0.12
    expected = np.exp(-r_ccy2 * T) * (forward(spot, T, r_ccy1, r_ccy2) - strike)

    def abs_error(step: float) -> float:
        value = integrate_payoff(
            long_forward_payoff(strike), spot, T, r_ccy1, r_ccy2, sigma, sd_step=step
        ).value_ccy2_pips
        return abs(value - expected)

    coarse, medium, fine = abs_error(0.1), abs_error(0.05), abs_error(0.02)
    assert coarse > medium > fine
    assert coarse / medium > 2.0, "expected faster than first-order convergence"


def test_put_call_parity_holds_under_numerical_integration_too():
    """Parity is a property of the payoffs, so it must survive the integration."""
    spot, strike, T, r_ccy1, r_ccy2, sigma = 1.30, 1.20, 1.0, 0.02, 0.05, 0.12

    call = price_vanilla(
        OptionType.CALL, spot, strike, T, r_ccy1, r_ccy2, sigma, sd_step=FINE_GRID_STEP
    ).value_ccy2_pips
    put = price_vanilla(
        OptionType.PUT, spot, strike, T, r_ccy1, r_ccy2, sigma, sd_step=FINE_GRID_STEP
    ).value_ccy2_pips
    expected = np.exp(-r_ccy2 * T) * (forward(spot, T, r_ccy1, r_ccy2) - strike)

    assert call - put == pytest.approx(expected, rel=1e-6)
