"""Tests for fxds.surface - Practicals D, E and F assembled.

Not in the book: the book builds the ATM curve and the smile separately and never
joins them. These tests check the join is coherent.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest

from fxds.atm_curve import WEEKEND_ZERO_WEIGHTS, Interpolation, WeightedATMCurve
from fxds.smile import put_delta_from_strike
from fxds.surface import (
    SIMPLIFICATIONS,
    TenorSmile,
    VolatilitySurface,
    example_surface,
)

HORIZON = date(2014, 6, 11)


@pytest.fixture
def surface():
    return example_surface(HORIZON)


class TestConstruction:
    def test_expiries_come_from_practical_d(self, surface):
        from fxds.dates import expiry_from_tenor

        for ts, expiry in zip(surface.tenor_smiles, surface.expiries):
            assert expiry == expiry_from_tenor(HORIZON, ts.tenor)

    def test_expiries_are_ascending(self, surface):
        assert surface.expiries == sorted(surface.expiries)

    def test_rejects_empty_tenors(self):
        with pytest.raises(ValueError, match="at least one tenor"):
            VolatilitySurface(HORIZON, 1.30, 0.0, 0.0, [])

    def test_rejects_nonpositive_spot(self):
        with pytest.raises(ValueError, match="Spot must be positive"):
            VolatilitySurface(HORIZON, 0.0, 0.0, 0.0, [TenorSmile("1M", 0.1, 0.0, 0.0)])

    def test_rejects_out_of_order_tenors(self):
        with pytest.raises(ValueError, match="ascending maturity order"):
            VolatilitySurface(HORIZON, 1.30, 0.0, 0.0,
                              [TenorSmile("1Y", 0.1, 0.0, 0.0),
                               TenorSmile("1M", 0.1, 0.0, 0.0)])


class TestATMBackbone:
    def test_atm_hits_the_quoted_level_at_each_tenor(self, surface):
        for ts, expiry in zip(surface.tenor_smiles, surface.expiries):
            assert surface.atm(expiry) == pytest.approx(ts.atm)

    def test_atm_interpolates_between_tenors(self, surface):
        a, b = surface.expiries[2], surface.expiries[3]
        mid = a + (b - a) / 2
        vol = surface.atm(mid)
        assert min(surface.atm(a), surface.atm(b)) < vol < max(surface.atm(a), surface.atm(b))

    def test_the_example_curve_is_upward_sloping(self, surface):
        atms = [surface.atm(e) for e in surface.expiries]
        assert atms == sorted(atms)


class TestSmileDimension:
    def test_smile_reproduces_the_quoted_instruments_at_each_tenor(self, surface):
        for ts, expiry in zip(surface.tenor_smiles, surface.expiries):
            smile = surface.smile_at(expiry)
            assert smile.atm == pytest.approx(ts.atm)
            assert smile.rr25 == pytest.approx(ts.rr25)
            assert smile.fly25 == pytest.approx(ts.fly25)

    def test_negative_risk_reversal_makes_downside_strikes_richer(self, surface):
        # The example surface is EUR/USD-shaped: downside rich.
        expiry = surface.expiries[4]
        smile = surface.smile_at(expiry)
        assert smile.volatility(0.25) > smile.volatility(0.75)

    def test_wings_are_above_the_atm(self, surface):
        # Positive butterfly throughout.
        for expiry in surface.expiries:
            smile = surface.smile_at(expiry)
            assert smile.volatility(0.10) > smile.volatility(0.50)
            assert smile.volatility(0.90) > smile.volatility(0.50)

    def test_smile_parameters_interpolate_between_tenors(self, surface):
        a, b = surface.expiries[0], surface.expiries[1]
        mid = a + (b - a) / 2
        rr = surface.smile_at(mid).rr25
        assert min(surface.tenor_smiles[0].rr25, surface.tenor_smiles[1].rr25) <= rr
        assert rr <= max(surface.tenor_smiles[0].rr25, surface.tenor_smiles[1].rr25)


class TestVolByExpiryAndStrike:
    """The point of the whole thing."""

    def test_returns_a_plausible_volatility(self, surface):
        expiry = surface.expiries[4]
        vol = surface.volatility(expiry, surface.spot)
        assert 0.01 < vol < 1.0

    def test_the_atm_strike_prices_near_the_atm_volatility(self, surface):
        expiry = surface.expiries[4]
        atm_strike = surface.strike_for_delta(expiry, 0.50)
        assert surface.volatility(expiry, atm_strike) == pytest.approx(
            surface.atm(expiry), rel=1e-6
        )

    def test_round_trip_delta_to_strike_to_volatility(self, surface):
        # Solve for the strike at a delta, then ask the surface for that strike's
        # volatility. It must agree with the smile at that delta.
        expiry = surface.expiries[5]
        for delta in (0.10, 0.25, 0.50, 0.75, 0.90):
            strike = surface.strike_for_delta(expiry, delta)
            expected = float(surface.smile_at(expiry).volatility(delta))
            assert surface.volatility(expiry, strike) == pytest.approx(expected, rel=1e-6)

    def test_iteration_lands_on_a_consistent_fixed_point(self, surface):
        # The returned volatility must be the smile value at the delta that
        # volatility itself implies. That self-consistency is what the iteration is
        # solving for, and it is worth asserting directly.
        expiry = surface.expiries[4]
        strike = 1.20
        vol = surface.volatility(expiry, strike)
        T = surface.years_to(expiry)
        delta = put_delta_from_strike(surface.spot, strike, T,
                                      surface.r_ccy1, surface.r_ccy2, vol)
        assert float(surface.smile_at(expiry).volatility(-delta)) == pytest.approx(vol, rel=1e-9)

    def test_downside_strikes_price_above_topside_on_this_surface(self, surface):
        expiry = surface.expiries[5]
        down = surface.strike_for_delta(expiry, 0.10)
        up = surface.strike_for_delta(expiry, 0.90)
        assert surface.volatility(expiry, down) > surface.volatility(expiry, up)

    def test_rejects_nonpositive_strike(self, surface):
        with pytest.raises(ValueError, match="Strike must be positive"):
            surface.volatility(surface.expiries[0], 0.0)

    def test_works_for_dates_between_tenors(self, surface):
        a, b = surface.expiries[3], surface.expiries[4]
        mid = a + (b - a) / 2
        vol = surface.volatility(mid, surface.spot)
        assert 0.01 < vol < 1.0


class TestNoArbitrage:
    def test_the_example_surface_has_no_calendar_arbitrage(self, surface):
        check = surface.check_no_calendar_arbitrage()
        assert not check["negative"].any()

    def test_total_variance_is_non_decreasing_across_tenors(self, surface):
        check = surface.check_no_calendar_arbitrage()
        assert check["total_variance"].is_monotonic_increasing

    def test_the_check_catches_a_deliberately_bad_surface(self):
        # Flat 20% out to 1yr then 10% at 2yr: variance falls, so the later expiry
        # claims to be LESS uncertain than the earlier one. Sell the near option,
        # buy the far one, and you are short variance for free.
        bad = VolatilitySurface(
            HORIZON, 1.30, 0.0, 0.0,
            [TenorSmile("6M", 0.20, 0.0, 0.0),
             TenorSmile("1Y", 0.20, 0.0, 0.0),
             TenorSmile("2Y", 0.10, 0.0, 0.0)],
            interpolation=Interpolation.LINEAR_VOLATILITY,
        )
        assert bad.check_no_calendar_arbitrage()["negative"].any()


class TestWeightedSurface:
    def test_day_weights_introduce_the_saw_tooth(self):
        weights = WeightedATMCurve(HORIZON, 0.08,
                                   weekday_weights=dict(WEEKEND_ZERO_WEIGHTS))
        surface = example_surface(HORIZON)
        weighted = VolatilitySurface(
            horizon=HORIZON, spot=surface.spot,
            r_ccy1=surface.r_ccy1, r_ccy2=surface.r_ccy2,
            tenor_smiles=surface.tenor_smiles, weights=weights,
        )
        start = surface.expiries[1]
        vols = [weighted.atm(start + timedelta(days=i)) for i in range(28)]
        assert float(np.std(vols)) > 1e-4

    def test_without_weights_the_curve_is_smooth(self, surface):
        start = surface.expiries[1]
        vols = [surface.atm(start + timedelta(days=i)) for i in range(28)]
        diffs = np.diff(vols)
        # Monotone and gently sloping - no saw-tooth.
        assert (diffs > 0).all()
        assert float(np.std(diffs)) < 1e-4


class TestViews:
    def test_grid_has_a_row_per_tenor(self, surface):
        grid = surface.grid()
        assert len(grid) == len(surface.tenor_smiles)
        for column in ("10%P", "25%P", "50%P", "25%C", "10%C"):
            assert column in grid.columns

    def test_grid_atm_column_matches_the_quotes(self, surface):
        grid = surface.grid()
        assert np.allclose(grid["50%P"], [ts.atm for ts in surface.tenor_smiles])

    def test_surface_mesh_covers_every_tenor(self, surface):
        mesh = surface.surface_mesh(points=12)
        assert set(mesh["expiry"]) == set(surface.expiries)
        assert len(mesh) == len(surface.expiries) * 12

    def test_mesh_strikes_are_positive(self, surface):
        assert (surface.surface_mesh(points=12)["strike"] > 0).all()


class TestHonesty:
    """The surface has to say what it is ignoring."""

    def test_simplifications_are_documented(self):
        assert len(SIMPLIFICATIONS) >= 6

    def test_the_broker_fly_simplification_is_named_first(self):
        # Ch. 12's largest gap between this model and the traded market.
        assert "broker fly" in SIMPLIFICATIONS[0].lower()

    def test_explain_returns_readable_text(self, surface):
        text = surface.explain_simplifications()
        assert "broker fly" in text.lower()
        assert all(s[:30] in text for s in SIMPLIFICATIONS)
