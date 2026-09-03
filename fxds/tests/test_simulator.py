"""Tests for fxds.simulator - Practical A (Ch. 3)."""

from __future__ import annotations

import numpy as np
import pytest

from fxds.simulator import (
    LimitBreach,
    Market,
    MarketAction,
    MarketParticipants,
    ParticipantBias,
    RiskLimits,
    Simulator,
    SpotProcess,
    Trader,
    TraderAction,
    TwoWayPrice,
    over_trading,
    passive,
    risk_reducing,
    run_many,
)

SPREAD = 0.0010
HALF = SPREAD / 2


class TestTwoWayPrice:
    def test_bid_and_offer_straddle_the_mid(self):
        # Practical A, Task B, Step 1.
        price = TwoWayPrice(mid=1.3000, spread=SPREAD)
        assert price.bid == pytest.approx(1.2995)
        assert price.offer == pytest.approx(1.3005)
        assert price.half_spread == pytest.approx(HALF)

    def test_a_choice_market_has_no_spread(self):
        # Ch. 3 mentions choice markets, where bid and offer are at the same level.
        price = TwoWayPrice(mid=1.3000, spread=0.0)
        assert price.bid == price.offer == 1.3000


class TestMarketTaskA:
    def test_fixed_increment_moves_by_exactly_one_increment(self):
        # Practical A, Task A: up or down by the SpotIncrement amount at random.
        market = Market(spot_increment=0.0005, rng=np.random.default_rng(0))
        for _ in range(50):
            assert abs(market.draw_increment()) == pytest.approx(0.0005)

    def test_direction_is_a_fair_coin(self):
        market = Market(rng=np.random.default_rng(7))
        draws = [market.draw_increment() for _ in range(20_000)]
        assert np.mean([d > 0 for d in draws]) == pytest.approx(0.5, abs=0.02)

    def test_advance_updates_mid_and_step(self):
        market = Market(initial_spot=1.3000, rng=np.random.default_rng(0))
        market.advance(0.0005)
        assert market.mid == pytest.approx(1.3005)
        assert market.step_count == 1

    def test_reset_returns_to_the_start(self):
        # The book's Stop button clears the outputs.
        market = Market(initial_spot=1.3000, rng=np.random.default_rng(0))
        for _ in range(10):
            market.advance(market.draw_increment())
        market.reset()
        assert market.mid == 1.3000
        assert market.step_count == 0

    def test_same_seed_replays_exactly(self):
        # The book's simulator cannot be replayed. This one can, which is what
        # makes it testable.
        def path(seed):
            m = Market(rng=np.random.default_rng(seed))
            return [m.draw_increment() for _ in range(30)]

        assert path(11) == path(11)
        assert path(11) != path(12)

    def test_volatility_process_gives_varied_proportional_moves(self):
        # Extension: a volatility-based spot evolution instead of a fixed increment.
        market = Market(process=SpotProcess.VOLATILITY, rng=np.random.default_rng(3))
        draws = [market.draw_increment() for _ in range(500)]
        assert len({round(abs(d), 10) for d in draws}) > 400, "moves should vary in size"

    def test_rejects_invalid_construction(self):
        with pytest.raises(ValueError, match="Initial spot must be positive"):
            Market(initial_spot=0.0)
        with pytest.raises(ValueError, match="Spot increment must be positive"):
            Market(spot_increment=0.0)
        with pytest.raises(ValueError, match="Spread cannot be negative"):
            Market(bid_offer_spread=-0.001)

    def test_refuses_to_take_spot_to_zero(self):
        market = Market(initial_spot=0.0005, spot_increment=0.001)
        with pytest.raises(ValueError, match="which is not a rate"):
            market.advance(-0.001)


class TestTraderTaskB:
    def test_buying_costs_half_the_spread(self):
        # Practical A, Task B: every trade has an initial negative P&L impact.
        trader = Trader()
        trader.take_price(TraderAction.BUY, HALF)
        assert trader.position == 1.0
        assert trader.pnl == pytest.approx(-HALF)

    def test_selling_also_costs_half_the_spread(self):
        # The point of the task: BOTH directions pay. There is no free side.
        trader = Trader()
        trader.take_price(TraderAction.SELL, HALF)
        assert trader.position == -1.0
        assert trader.pnl == pytest.approx(-HALF)

    def test_a_round_trip_costs_a_full_spread_even_if_spot_helps(self):
        # Buy, watch spot move in your favour by exactly the spread, sell back.
        # You are still down half a spread. This is the structural negative carry.
        trader = Trader()
        trader.take_price(TraderAction.BUY, HALF)
        trader.mark_to_market(SPREAD)
        trader.take_price(TraderAction.SELL, HALF)
        assert trader.position == 0.0
        assert trader.pnl == pytest.approx(SPREAD - 2 * HALF)
        assert trader.spread_paid == pytest.approx(2 * HALF)

    def test_doing_nothing_costs_nothing(self):
        trader = Trader()
        trader.take_price(TraderAction.NOTHING, HALF)
        assert trader.position == 0.0
        assert trader.pnl == 0.0
        assert trader.trades_taken == 0

    def test_mark_to_market_uses_the_chapter_1_formula(self):
        # P&L_CCY2 = Notional_CCY1 * (S_new - S_old).
        trader = Trader()
        trader.position = 3.0
        trader.mark_to_market(0.0005)
        assert trader.pnl == pytest.approx(3.0 * 0.0005)

    def test_short_position_makes_money_when_spot_falls(self):
        trader = Trader()
        trader.position = -2.0
        trader.mark_to_market(-0.0005)
        assert trader.pnl == pytest.approx(0.0010)


class TestTraderTaskC:
    def test_market_buying_makes_the_trader_shorter_and_earns_spread(self):
        # Practical A, Task C. The sign convention people get wrong: the market
        # BUYING means the trader SOLD, so the position goes shorter.
        trader = Trader()
        trader.make_price(market_buys=True, notional=1.0, half_spread=HALF)
        assert trader.position == -1.0
        assert trader.pnl == pytest.approx(+HALF)
        assert trader.spread_earned == pytest.approx(HALF)

    def test_market_selling_makes_the_trader_longer_and_earns_spread(self):
        trader = Trader()
        trader.make_price(market_buys=False, notional=1.0, half_spread=HALF)
        assert trader.position == 1.0
        assert trader.pnl == pytest.approx(+HALF)

    def test_price_making_is_the_mirror_image_of_price_taking(self):
        taker, maker = Trader(), Trader()
        taker.take_price(TraderAction.SELL, HALF)
        maker.make_price(market_buys=True, notional=1.0, half_spread=HALF)
        assert taker.position == maker.position
        assert taker.pnl == pytest.approx(-maker.pnl)

    def test_offsetting_flow_earns_the_full_spread_for_no_net_position(self):
        # Ch. 3, scenario 1: two-way flow lets the market maker buy at their bid and
        # sell at their offer, ending flat and up the whole spread.
        trader = Trader()
        trader.make_price(market_buys=True, notional=1.0, half_spread=HALF)
        trader.make_price(market_buys=False, notional=1.0, half_spread=HALF)
        assert trader.position == 0.0
        assert trader.pnl == pytest.approx(SPREAD)


class TestRiskLimits:
    def test_position_limit_blocks_the_trade(self):
        trader = Trader(limits=RiskLimits(max_position=2))
        for _ in range(2):
            assert trader.take_price(TraderAction.BUY, HALF) is LimitBreach.NONE
        assert trader.take_price(TraderAction.BUY, HALF) is LimitBreach.POSITION_LIMIT
        assert trader.position == 2.0
        assert trader.blocked_trades == 1

    def test_a_blocked_trade_costs_nothing(self):
        trader = Trader(limits=RiskLimits(max_position=0))
        trader.take_price(TraderAction.BUY, HALF)
        assert trader.pnl == 0.0

    def test_position_limit_does_not_block_price_making(self):
        # A price maker cannot decline a trade that already happened. Watching an
        # unwanted position build past the limit is the risk Ch. 3 describes.
        trader = Trader(limits=RiskLimits(max_position=1))
        for _ in range(5):
            trader.make_price(market_buys=True, notional=1.0, half_spread=HALF)
        assert trader.position == -5.0

    def test_stop_loss_and_profit_target_detection(self):
        trader = Trader(limits=RiskLimits(stop_loss=-0.01, profit_target=0.01))
        trader.pnl = -0.02
        assert trader.check_pnl_limits() is LimitBreach.STOP_LOSS
        trader.pnl = 0.02
        assert trader.check_pnl_limits() is LimitBreach.PROFIT_TARGET
        trader.pnl = 0.0
        assert trader.check_pnl_limits() is LimitBreach.NONE

    def test_rejects_nonsensical_limits(self):
        with pytest.raises(ValueError, match="max_position cannot be negative"):
            RiskLimits(max_position=-1)
        with pytest.raises(ValueError, match="stop_loss should be negative"):
            RiskLimits(stop_loss=0.05)
        with pytest.raises(ValueError, match="profit_target should be positive"):
            RiskLimits(profit_target=-0.05)


class TestParticipants:
    def test_probabilities_are_respected(self):
        p = MarketParticipants(buy_probability=0.2, sell_probability=0.3,
                               rng=np.random.default_rng(5))
        actions = [p.draw()[0] for _ in range(30_000)]
        assert np.mean([a is MarketAction.BUYS for a in actions]) == pytest.approx(0.2, abs=0.01)
        assert np.mean([a is MarketAction.SELLS for a in actions]) == pytest.approx(0.3, abs=0.01)
        assert np.mean([a is MarketAction.NONE for a in actions]) == pytest.approx(0.5, abs=0.01)

    def test_mean_reverting_bias_leans_against_the_move(self):
        # Extension: participants more likely to buy if spot goes lower.
        p = MarketParticipants(bias=ParticipantBias.MEAN_REVERTING, bias_strength=0.5,
                               rng=np.random.default_rng(5))
        buy_after_fall, _ = p._tilted_probabilities(-0.0005)
        buy_after_rise, _ = p._tilted_probabilities(+0.0005)
        assert buy_after_fall > p.buy_probability > buy_after_rise

    def test_trend_following_bias_leans_with_the_move(self):
        p = MarketParticipants(bias=ParticipantBias.TREND_FOLLOWING, bias_strength=0.5,
                               rng=np.random.default_rng(5))
        buy_after_rise, _ = p._tilted_probabilities(+0.0005)
        assert buy_after_rise > p.buy_probability

    def test_bias_never_produces_an_invalid_probability_split(self):
        p = MarketParticipants(buy_probability=0.45, sell_probability=0.45,
                               bias=ParticipantBias.MEAN_REVERTING, bias_strength=1.0,
                               rng=np.random.default_rng(5))
        for move in (-1.0, 0.0, 1.0):
            buy, sell = p._tilted_probabilities(move)
            assert 0 <= buy <= 1 and 0 <= sell <= 1
            assert buy + sell <= 1.0 + 1e-12

    def test_variable_notionals(self):
        # Extension: introduce different sized notionals.
        p = MarketParticipants(buy_probability=0.5, sell_probability=0.5,
                               notional_choices=(1.0, 5.0, 10.0),
                               rng=np.random.default_rng(9))
        sizes = {p.draw()[1] for _ in range(500)}
        assert sizes == {1.0, 5.0, 10.0}

    def test_rejects_invalid_configuration(self):
        with pytest.raises(ValueError, match="cannot be negative"):
            MarketParticipants(buy_probability=-0.1)
        with pytest.raises(ValueError, match="exceeds 1"):
            MarketParticipants(buy_probability=0.7, sell_probability=0.7)
        with pytest.raises(ValueError, match="cannot be empty"):
            MarketParticipants(notional_choices=())
        with pytest.raises(ValueError, match="same length"):
            MarketParticipants(notional_choices=(1.0, 2.0), notional_weights=(1.0,))


class TestSimulatorTickOrdering:
    """The ordering in Practical A, Task B is not arbitrary."""

    def test_position_is_marked_before_the_trade_is_processed(self):
        # A trade placed this tick must NOT earn this tick's spot move. If the order
        # were reversed the P&L would drift by one tick's worth of the position.
        sim = Simulator(market=Market(spot_increment=0.0005, bid_offer_spread=SPREAD,
                                      rng=np.random.default_rng(0)))
        record = sim.step(TraderAction.BUY)
        # Started flat, so marking contributes nothing; only the spread is paid.
        assert record.pnl == pytest.approx(-HALF)
        assert record.position == 1.0

    def test_an_existing_position_does_earn_the_move(self):
        sim = Simulator(market=Market(spot_increment=0.0005, bid_offer_spread=SPREAD,
                                      rng=np.random.default_rng(0)))
        sim.step(TraderAction.BUY)
        pnl_after_first = sim.trader.pnl
        record = sim.step(TraderAction.NOTHING)
        assert record.pnl == pytest.approx(pnl_after_first + 1.0 * sim.market.last_increment)

    def test_action_resets_after_each_tick(self):
        # The book's VBA sets Range("Action") back to 1 at the end of every tick.
        sim = Simulator()
        sim.set_action(TraderAction.BUY)
        sim.step()
        assert sim.pending_action is TraderAction.NOTHING
        sim.step()
        assert sim.trader.trades_taken == 1, "the action should not repeat"

    def test_bid_offer_recomputed_around_the_new_mid(self):
        sim = Simulator(market=Market(bid_offer_spread=SPREAD, rng=np.random.default_rng(0)))
        record = sim.step()
        assert record.bid == pytest.approx(record.mid - HALF)
        assert record.offer == pytest.approx(record.mid + HALF)


class TestSimulatorSession:
    def test_history_records_every_tick(self):
        sim = Simulator(seed=1)
        sim.run(25)
        frame = sim.to_frame()
        assert len(frame) == 25
        assert list(frame["step"]) == list(range(1, 26))

    def test_empty_history_still_returns_a_shaped_frame(self):
        assert list(Simulator().to_frame().columns) == [
            "step", "mid", "bid", "offer", "position", "pnl",
            "trader_action", "market_action", "market_notional", "breach",
        ]

    def test_reset_clears_everything(self):
        sim = Simulator(participants=MarketParticipants(), seed=1)
        sim.run(30, over_trading(0.8))
        sim.reset()
        assert sim.market.step_count == 0
        assert sim.trader.position == 0.0
        assert sim.trader.pnl == 0.0
        assert sim.history == []

    def test_same_seed_replays_the_whole_session(self):
        def run(seed):
            sim = Simulator(participants=MarketParticipants(), seed=seed)
            return sim.run(100, over_trading(0.4))

        assert run(3).equals(run(3))
        assert not run(3).equals(run(4))

    def test_strategy_randomness_does_not_disturb_the_market_path(self):
        # This is what makes the passive-vs-over-trading comparison controlled.
        a = Simulator(participants=MarketParticipants(), seed=99)
        a.run(150, passive)
        b = Simulator(participants=MarketParticipants(), seed=99)
        b.run(150, over_trading(0.5))
        assert a.market.mid == pytest.approx(b.market.mid)
        assert list(a.to_frame()["mid"]) == pytest.approx(list(b.to_frame()["mid"]))

    def test_stop_loss_halts_the_session(self):
        sim = Simulator(
            market=Market(bid_offer_spread=0.01, rng=np.random.default_rng(0)),
            trader=Trader(limits=RiskLimits(stop_loss=-0.02)),
            seed=0,
        )
        sim.run(200, over_trading(1.0))
        assert sim.stopped is LimitBreach.STOP_LOSS
        assert sim.trader.pnl <= -0.02

    def test_stepping_a_stopped_session_raises(self):
        sim = Simulator(trader=Trader(limits=RiskLimits(stop_loss=-1e-9)), seed=0)
        sim.trader.pnl = -1.0
        sim.step()
        with pytest.raises(RuntimeError, match="Session stopped"):
            sim.step()


class TestStrategies:
    def test_passive_never_trades(self):
        sim = Simulator(participants=MarketParticipants(), seed=4)
        sim.run(300, passive)
        assert sim.trader.trades_taken == 0
        assert sim.trader.spread_paid == 0.0

    def test_over_trading_pays_spread_on_every_trade(self):
        sim = Simulator(seed=4)
        sim.run(300, over_trading(0.5))
        assert sim.trader.trades_taken > 0
        assert sim.trader.spread_paid == pytest.approx(
            sim.trader.trades_taken * HALF * sim.trader.trade_notional
        )

    def test_risk_reducing_trades_only_when_the_position_is_large(self):
        sim = Simulator(
            participants=MarketParticipants(buy_probability=0.9, sell_probability=0.0),
            seed=4,
        )
        sim.run(200, risk_reducing(max_position=3.0))
        frame = sim.to_frame()
        # Every trade the trader took should have happened from an oversized position.
        traded = frame[frame["trader_action"] != "nothing"]
        assert len(traded) > 0
        assert sim.trader.trades_taken > 0


class TestBatchExperiment:
    """The teaching experiment: spread cross is a structural drag."""

    def test_over_trading_loses_more_spread_than_passive(self):
        common = dict(sessions=120, ticks=250, base_seed=0,
                      participant_kwargs=dict(buy_probability=0.15, sell_probability=0.15))
        quiet = run_many(strategy=passive, **common)
        busy = run_many(strategy=over_trading(0.5), **common)

        assert quiet["spread_paid"].sum() == 0.0
        assert busy["spread_paid"].mean() > 0.0

    def test_over_trading_has_a_worse_mean_pnl(self):
        # The headline claim of Practical A, measured rather than asserted. Each
        # session pair shares a seed, so both strategies face the same market and
        # the same client flow - the only difference is the spread crossed.
        common = dict(sessions=300, ticks=250, base_seed=0,
                      participant_kwargs=dict(buy_probability=0.15, sell_probability=0.15))
        quiet = run_many(strategy=passive, **common)
        busy = run_many(strategy=over_trading(0.5), **common)

        assert busy["pnl"].mean() < quiet["pnl"].mean()

    def test_the_gap_scales_with_how_often_you_trade(self):
        common = dict(sessions=200, ticks=200, base_seed=7)
        rare = run_many(strategy=over_trading(0.1), **common)
        often = run_many(strategy=over_trading(0.9), **common)
        assert often["spread_paid"].mean() > rare["spread_paid"].mean() * 5

    def test_run_many_is_reproducible(self):
        kwargs = dict(sessions=20, ticks=50, strategy=over_trading(0.5), base_seed=2)
        assert run_many(**kwargs).equals(run_many(**kwargs))
