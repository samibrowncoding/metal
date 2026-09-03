"""Tests for fxds.conventions - market conventions from Chapters 1, 2, 7 and 10."""

from __future__ import annotations

import pytest

from fxds.conventions import (
    BASIS_POINT,
    ATMConvention,
    CurrencyPair,
    OptionType,
    PremiumSide,
    big_figure,
    ccy1_pct_to_ccy2_pips,
    ccy2_cash_to_ccy1_cash,
    ccy2_pips_to_ccy1_pct,
    ccy2_pips_to_ccy2_cash,
    notional_ccy1_to_ccy2,
    notional_ccy2_to_ccy1,
    otm_option_type,
    pips_to_rate,
    rate_to_pips,
    spot_pnl_ccy1,
    spot_pnl_ccy2,
    vega_to_market_terms,
)


class TestCurrencyPair:
    def test_parse_with_and_without_slash(self):
        assert CurrencyPair.parse("EUR/USD") == CurrencyPair("EUR", "USD")
        assert CurrencyPair.parse("EURUSD") == CurrencyPair("EUR", "USD")
        assert CurrencyPair.parse("eurusd") == CurrencyPair("EUR", "USD")

    def test_name_and_code(self):
        pair = CurrencyPair.parse("EURUSD")
        assert pair.name == "EUR/USD"
        assert pair.code == "EURUSD"

    @pytest.mark.parametrize("bad", ["EUR", "EURUSDJPY", "EU/USD", ""])
    def test_rejects_malformed(self, bad):
        with pytest.raises(ValueError):
            CurrencyPair.parse(bad)

    def test_rejects_same_currency_twice(self):
        with pytest.raises(ValueError, match="two different currencies"):
            CurrencyPair("USD", "USD")

    def test_pip_size(self):
        # Ch. 1: EUR/USD quotes to four decimals, USD/JPY to two.
        assert CurrencyPair.parse("EURUSD").pip == 0.0001
        assert CurrencyPair.parse("USDJPY").pip == 0.01
        assert CurrencyPair.parse("EURJPY").pip == 0.01

    def test_premium_side(self):
        # Ch. 10: EUR/USD pays premium in CCY2 (RHS); EUR/JPY in CCY1 (LHS).
        assert CurrencyPair.parse("EURUSD").premium_side is PremiumSide.CCY2
        assert CurrencyPair.parse("EURJPY").premium_side is PremiumSide.CCY1
        assert CurrencyPair.parse("USDJPY").premium_side is PremiumSide.CCY1

    def test_premium_side_market_names(self):
        assert PremiumSide.CCY1.market_name == "LHS"
        assert PremiumSide.CCY2.market_name == "RHS"


class TestPips:
    def test_swap_points_example(self):
        # Ch. 1: EUR/USD spot 1.3105, 1yr forward 1.3245 => 140 pips.
        pair = CurrencyPair.parse("EURUSD")
        assert rate_to_pips(1.3245 - 1.3105, pair) == pytest.approx(140.0)
        assert pips_to_rate(140.0, pair) == pytest.approx(0.0140)

    def test_forty_pip_move(self):
        # Ch. 1: 1.3105 -> 1.3145 is "forty pips higher".
        pair = CurrencyPair.parse("EURUSD")
        assert rate_to_pips(1.3145 - 1.3105, pair) == pytest.approx(40.0)

    def test_big_figure_is_one_hundred_pips(self):
        # Ch. 1: USD/JPY 101.20 -> 100.20 is "a figure".
        pair = CurrencyPair.parse("USDJPY")
        assert big_figure(pair) == pytest.approx(1.00)
        assert rate_to_pips(101.20 - 100.20, pair) == pytest.approx(100.0)

    def test_roundtrip(self):
        pair = CurrencyPair.parse("EURUSD")
        assert rate_to_pips(pips_to_rate(37.5, pair), pair) == pytest.approx(37.5)


class TestSpotPnl:
    def test_long_position_profit(self):
        # Ch. 1: buy USD10m USD/CAD at 0.9780, sell at 0.9900 => CAD120k.
        assert spot_pnl_ccy2(10e6, 0.9780, 0.9900) == pytest.approx(120_000.0)

    def test_short_position_uses_negative_notional(self):
        # Ch. 1 uses the same formula for shorts, with a negative notional.
        assert spot_pnl_ccy2(-10e6, 0.9780, 0.9900) == pytest.approx(-120_000.0)

    def test_ccy1_pnl_is_curved_not_linear(self):
        # Ch. 1: converting CCY2 P&L back at the prevailing rate introduces
        # curvature, so equal spot moves up and down give unequal CCY1 P&L.
        up = spot_pnl_ccy1(100e6, 101.00, 102.00)
        down = spot_pnl_ccy1(100e6, 101.00, 100.00)
        assert up != pytest.approx(-down)
        # A gain converted at a higher rate is worth less CCY1 than the
        # equal-and-opposite loss converted at a lower rate.
        assert abs(up) < abs(down)

    def test_ccy1_pnl_rejects_nonpositive_spot(self):
        with pytest.raises(ValueError, match="Spot must be positive"):
            spot_pnl_ccy1(10e6, 1.0, 0.0)


class TestNotionalConversion:
    def test_notional_converts_at_strike_not_spot(self):
        # Ch. 2: the strike is the rate at which the currencies are potentially
        # exchanged, so it is the right conversion rate for a notional.
        assert notional_ccy1_to_ccy2(5e6, 80.00) == pytest.approx(400e6)

    def test_notional_roundtrip(self):
        assert notional_ccy2_to_ccy1(notional_ccy1_to_ccy2(5e6, 80.0), 80.0) == pytest.approx(5e6)

    def test_rejects_nonpositive_strike(self):
        with pytest.raises(ValueError, match="Strike must be positive"):
            notional_ccy2_to_ccy1(1e6, 0.0)


class TestPremiumConversion:
    def test_ccy2_pips_to_cash(self):
        # Practical C, Task A, Step 3.
        assert ccy2_pips_to_ccy2_cash(0.0399, 10e6) == pytest.approx(399_000.0)

    def test_ccy2_cash_to_ccy1_cash(self):
        assert ccy2_cash_to_ccy1_cash(399_000.0, 1.30) == pytest.approx(306_923.077, rel=1e-6)

    def test_pips_to_ccy1_pct_roundtrip(self):
        pct = ccy2_pips_to_ccy1_pct(0.0399, 1.30)
        assert ccy1_pct_to_ccy2_pips(pct, 1.30) == pytest.approx(0.0399)

    def test_basis_point_is_hundredth_of_a_percent(self):
        # Ch. 7 and Ch. 10: a basis point is 0.01% of notional.
        assert BASIS_POINT == pytest.approx(0.0001)

    def test_rejects_nonpositive_spot(self):
        with pytest.raises(ValueError, match="Spot must be positive"):
            ccy2_pips_to_ccy1_pct(0.04, -1.0)


class TestQuoteConventions:
    def test_otm_side_is_traded(self):
        # Ch. 7: strike above the ATM trades as a CCY1 call, below as a put.
        assert otm_option_type(1.35, 1.30) is OptionType.CALL
        assert otm_option_type(1.25, 1.30) is OptionType.PUT

    def test_option_type_sign(self):
        assert OptionType.CALL.sign == 1
        assert OptionType.PUT.sign == -1

    def test_atm_conventions_are_distinct(self):
        # Ch. 7 defines three different contracts that all get called "ATM".
        assert len({c.value for c in ATMConvention}) == 3


class TestVegaConvention:
    def test_market_terms(self):
        # Practical C, Task C: divide by spot for CCY1 terms, by 100 for a 1% move.
        assert vega_to_market_terms(0.398942, 1.0) == pytest.approx(0.00398942)
        assert vega_to_market_terms(0.398942, 2.0) == pytest.approx(0.00199471)

    def test_rejects_nonpositive_spot(self):
        with pytest.raises(ValueError, match="Spot must be positive"):
            vega_to_market_terms(0.4, 0.0)
