"""The headless Simulator - Practical A, Tasks A, B and C combined.

Not one of the three files the build spec named, but the coordinating object has to
live somewhere and putting it in ``market.py`` or ``trader.py`` would mean one of them
importing the other. Recorded in ``notes/deviations.md``.

The whole point of this class is that it is **steppable and has no clock of its own**.
Streamlit's rerun loop supplies the clock in the app; a ``for`` loop supplies it in
tests and in the thousand-session experiment. The book's version cannot be run without
Excel, cannot be replayed, and cannot be batched.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .market import Market, MarketAction, MarketParticipants, SpotProcess
from .trader import LimitBreach, RiskLimits, Trader, TraderAction

Strategy = Callable[["Simulator"], TraderAction]
"""A trading rule: look at the simulator, decide what to do this tick.

Deliberately just a function. A strategy needs no state of its own - everything it
could want is already on the simulator - and an abstract base class here would be
ceremony without benefit.
"""


@dataclass
class TickRecord:
    """One row of the session history.

    Attributes:
        step: Tick number, starting at 1.
        mid: Mid rate after this tick's move.
        bid: Bid after this tick's move.
        offer: Offer after this tick's move.
        position: Position after any trades this tick.
        pnl: Cumulative P&L after this tick.
        trader_action: What the trader did.
        market_action: What the simulated participants did.
        market_notional: Size the market traded in, zero if it did nothing.
        breach: Any limit breach triggered this tick.
    """

    step: int
    mid: float
    bid: float
    offer: float
    position: float
    pnl: float
    trader_action: str
    market_action: str
    market_notional: float
    breach: str


@dataclass
class Simulator:
    """A steppable trading session (Practical A).

    Args:
        market: The ticking market. Defaults to the book's fixed-increment process.
        trader: The trader's position and P&L.
        participants: Simulated price takers. ``None`` disables price making, which
            gives you Tasks A and B only.
        seed: Convenience seed. When given, fresh generators are built for the market
            and the participants so a whole session replays identically.

    Examples:
        Ten ticks of a market with nobody trading - Task A:

        >>> sim = Simulator(seed=0)
        >>> for _ in range(10):
        ...     _ = sim.step()
        >>> sim.trader.position
        0.0
    """

    market: Market = field(default_factory=Market)
    trader: Trader = field(default_factory=Trader)
    participants: MarketParticipants | None = None
    seed: int | None = None

    history: list[TickRecord] = field(init=False, default_factory=list)
    stopped: LimitBreach = field(init=False, default=LimitBreach.NONE)
    pending_action: TraderAction = field(init=False, default=TraderAction.NOTHING)
    strategy_rng: np.random.Generator = field(
        init=False, default_factory=np.random.default_rng
    )

    def __post_init__(self) -> None:
        if self.seed is not None:
            # Three independent generators from one seed: the market path, the
            # participant flow, and anything a strategy needs.
            #
            # Keeping the strategy's randomness separate is what makes the
            # passive-versus-over-trading experiment a controlled comparison. If a
            # strategy drew from the market's generator, deciding to trade would
            # consume a number and change the spot path - so the two strategies
            # would face different markets and the comparison would be worthless.
            market_seed, participant_seed, strategy_seed = np.random.SeedSequence(
                self.seed
            ).spawn(3)
            self.market.rng = np.random.default_rng(market_seed)
            self.strategy_rng = np.random.default_rng(strategy_seed)
            if self.participants is not None:
                self.participants.rng = np.random.default_rng(participant_seed)

    # -- controls ---------------------------------------------------------------

    def set_action(self, action: TraderAction) -> None:
        """Queue the trader's action for the next tick.

        The Excel original wires this to grouped Option Buttons and resets them to
        "Do Nothing" after each tick. Same behaviour: the action is consumed by one
        tick and then cleared.
        """
        self.pending_action = action

    def reset(self) -> None:
        """Clear the session - market, trader, history and stop state.

        This is the book's Stop button, which clears the outputs and the stored ticks.
        """
        self.market.reset()
        self.trader.reset()
        self.history.clear()
        self.stopped = LimitBreach.NONE
        self.pending_action = TraderAction.NOTHING

    # -- the tick ---------------------------------------------------------------

    def step(self, action: TraderAction | None = None) -> TickRecord:
        """Advance one tick (Practical A, Task B, ordering exactly as the book has it).

        The order is not arbitrary and is worth reading against the book's VBA:

        1. Draw the spot increment.
        2. **Mark the existing position to it** - before spot moves, using the
           position held before any trade this tick.
        3. Move spot and advance the step counter.
        4. Recompute bid and offer.
        5. Process the trader's action, charging half the spread either way.
        6. Process the market participants, earning half the spread.
        7. Reset the trader's action.

        Step 2 running before step 5 is what stops a trade you place this tick from
        earning this tick's spot move. Reorder those and the P&L drifts by one tick.

        Args:
            action: What the trader does this tick. If omitted, whatever was queued
                by :meth:`set_action` is used.

        Returns:
            The record for this tick.

        Raises:
            RuntimeError: If the session has already stopped on a limit.
        """
        if self.stopped is not LimitBreach.NONE:
            raise RuntimeError(
                f"Session stopped on {self.stopped.value}. Call reset() to start again."
            )

        if action is not None:
            self.pending_action = action

        # 1-3: draw, mark the existing position, then move spot.
        increment = self.market.draw_increment()
        self.trader.mark_to_market(increment)
        self.market.advance(increment)

        # 4: the new two-way price.
        price = self.market.price
        breach = LimitBreach.NONE

        # 5: the trader crosses the spread, if they chose to.
        taker_breach = self.trader.take_price(self.pending_action, price.half_spread)
        if taker_breach is not LimitBreach.NONE:
            breach = taker_breach

        # 6: the market deals on the trader, if anyone turned up.
        market_action, market_notional = MarketAction.NONE, 0.0
        if self.participants is not None:
            market_action, market_notional = self.participants.draw(increment)
            if market_action is not MarketAction.NONE:
                self.trader.make_price(
                    market_buys=market_action is MarketAction.BUYS,
                    notional=market_notional,
                    half_spread=price.half_spread,
                )

        record = TickRecord(
            step=self.market.step_count,
            mid=self.market.mid,
            bid=price.bid,
            offer=price.offer,
            position=self.trader.position,
            pnl=self.trader.pnl,
            trader_action=self.pending_action.value,
            market_action=market_action.value,
            market_notional=market_notional,
            breach=breach.value,
        )
        self.history.append(record)

        # 7: reset the action, as the book's VBA does.
        self.pending_action = TraderAction.NOTHING

        # A P&L limit stops the session; a position-limit block does not.
        pnl_breach = self.trader.check_pnl_limits()
        if pnl_breach is not LimitBreach.NONE:
            self.stopped = pnl_breach
            record.breach = pnl_breach.value

        return record

    def run(self, ticks: int, strategy: Strategy | None = None) -> pd.DataFrame:
        """Run many ticks headlessly.

        Args:
            ticks: How many ticks to run. Stops early on a P&L limit breach.
            strategy: Called once per tick to choose the action. ``None`` means the
                trader does nothing and only price-making flow moves the position.

        Returns:
            The session history as a DataFrame.
        """
        for _ in range(ticks):
            if self.stopped is not LimitBreach.NONE:
                break
            self.step(strategy(self) if strategy is not None else TraderAction.NOTHING)
        return self.to_frame()

    def to_frame(self) -> pd.DataFrame:
        """The session history as a DataFrame, one row per tick."""
        if not self.history:
            return pd.DataFrame(
                columns=[
                    "step", "mid", "bid", "offer", "position", "pnl",
                    "trader_action", "market_action", "market_notional", "breach",
                ]
            )
        return pd.DataFrame([vars(r) for r in self.history])

    @property
    def summary(self) -> dict[str, float | str | int]:
        """Headline numbers for the session so far."""
        return {
            "ticks": self.market.step_count,
            "final_mid": self.market.mid,
            "position": self.trader.position,
            "pnl": self.trader.pnl,
            "trades_taken": self.trader.trades_taken,
            "trades_made": self.trader.trades_made,
            "spread_paid": self.trader.spread_paid,
            "spread_earned": self.trader.spread_earned,
            "blocked_trades": self.trader.blocked_trades,
            "stopped": self.stopped.value,
        }


# ---------------------------------------------------------------------------
# Strategies for the batch experiment
# ---------------------------------------------------------------------------

def passive(_: Simulator) -> TraderAction:
    """Never cross the spread (Practical A, Task C).

    With roughly symmetric participant flow this is the theoretically correct
    behaviour the book describes: sit, collect the spread from both sides, and only
    reduce the position when it gets big enough that the P&L swings become
    uncomfortable.
    """
    return TraderAction.NOTHING


def over_trading(probability: float = 0.5) -> Strategy:
    """Cross the spread at random, often (Practical A, Task B).

    A caricature, deliberately. It has no view and no edge - it just trades. Every
    trade costs half the spread, so the expected P&L is negative and scales with how
    often it fires. This is the strategy the book's warning is about:
    *don't over-trade when there is spread cross involved.*

    Args:
        probability: Chance of trading on any given tick.

    Returns:
        A strategy function.
    """

    def strategy(sim: Simulator) -> TraderAction:
        # Draws from the strategy generator, not the market's, so choosing to trade
        # does not disturb the spot path.
        rng = sim.strategy_rng
        if rng.random() >= probability:
            return TraderAction.NOTHING
        return TraderAction.BUY if rng.random() < 0.5 else TraderAction.SELL

    return strategy


def risk_reducing(max_position: float = 5.0) -> Strategy:
    """Trade only to bring an oversized position back toward flat.

    The middle ground between the two caricatures, and closest to what Chapter 3
    actually describes a price maker doing: warehouse the flow, and cross the spread
    only when the position has grown past what you want to carry.

    Args:
        max_position: Absolute position beyond which the trader trims.

    Returns:
        A strategy function.
    """

    def strategy(sim: Simulator) -> TraderAction:
        position = sim.trader.position
        if position > max_position:
            return TraderAction.SELL
        if position < -max_position:
            return TraderAction.BUY
        return TraderAction.NOTHING

    return strategy


def run_many(
    sessions: int,
    ticks: int,
    strategy: Strategy | None = None,
    *,
    base_seed: int = 0,
    market_kwargs: dict | None = None,
    trader_kwargs: dict | None = None,
    participant_kwargs: dict | None = None,
) -> pd.DataFrame:
    """Run many independent sessions and collect their outcomes.

    This is the experiment that turns the book's advice into a measurement: run a
    thousand sessions of a passive strategy and a thousand of an over-trading one, and
    compare the P&L distributions rather than arguing about it.

    Args:
        sessions: How many sessions to run.
        ticks: Ticks per session.
        strategy: The trading rule. ``None`` for fully passive.
        base_seed: Sessions use ``base_seed + i``, so results are reproducible.
        market_kwargs: Overrides for :class:`~fxds.simulator.market.Market`.
        trader_kwargs: Overrides for :class:`~fxds.simulator.trader.Trader`.
        participant_kwargs: Overrides for
            :class:`~fxds.simulator.market.MarketParticipants`. ``None`` disables
            price making.

    Returns:
        One row per session, with the summary fields from :attr:`Simulator.summary`.
    """
    rows = []
    for i in range(sessions):
        sim = Simulator(
            market=Market(**(market_kwargs or {})),
            trader=Trader(**(trader_kwargs or {})),
            participants=(
                MarketParticipants(**participant_kwargs)
                if participant_kwargs is not None
                else None
            ),
            seed=base_seed + i,
        )
        sim.run(ticks, strategy)
        rows.append({"session": i, **sim.summary})
    return pd.DataFrame(rows)
