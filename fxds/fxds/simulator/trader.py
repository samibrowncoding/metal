"""Trader position, P&L and actions - Practical A, Task B.

The tick ordering matters and follows the book exactly: mark the existing position to
the new spot first, then move spot, then process the trade and charge half the spread.
Getting this order wrong quietly changes the P&L by one tick's worth of drift.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class TraderAction(str, Enum):
    """What the trader chose to do on a tick (Practical A, Task B, Step 2).

    The book wires these to grouped Option Buttons that reset to "Do Nothing" after
    every tick. Same three choices here, and the same reset.

    ``BUY`` lifts the offer and ``SELL`` hits the bid - in both cases the trader is
    the price *taker* and pays half the spread. That symmetry is the point of Task B.
    """

    NOTHING = "nothing"
    BUY = "buy"
    SELL = "sell"


class LimitBreach(str, Enum):
    """Why a trade was blocked, or why a session stopped.

    The book's first suggested extension is risk limits and P&L targets, with the
    instruction to start them in line and then deliberately push them out of line to
    see what misalignment does to trading behaviour.
    """

    NONE = "none"
    POSITION_LIMIT = "position limit"
    STOP_LOSS = "stop loss"
    PROFIT_TARGET = "profit target"


@dataclass
class RiskLimits:
    """Position limit, stop loss and profit target (Practical A, extension 1).

    Chapter 3 makes the point these are meant to illustrate: risk limits and P&L
    targets should be *in line* with each other. Greater risk offers the opportunity
    for greater reward but guarantees only greater P&L volatility. A tight position
    limit paired with an ambitious profit target is not a cautious configuration -
    it is an impossible one, and the simulator lets you watch that happen.

    Args:
        max_position: Largest absolute position allowed. ``None`` for no limit.
        stop_loss: P&L level at which the session stops, as a negative number.
            ``None`` for no stop.
        profit_target: P&L level at which the session stops on the upside. ``None``
            for no target.

    Raises:
        ValueError: If ``max_position`` is negative, ``stop_loss`` is positive, or
            ``profit_target`` is negative.
    """

    max_position: float | None = None
    stop_loss: float | None = None
    profit_target: float | None = None

    def __post_init__(self) -> None:
        if self.max_position is not None and self.max_position < 0:
            raise ValueError(f"max_position cannot be negative, got {self.max_position}")
        if self.stop_loss is not None and self.stop_loss > 0:
            raise ValueError(
                f"stop_loss should be negative (a loss), got {self.stop_loss}"
            )
        if self.profit_target is not None and self.profit_target < 0:
            raise ValueError(
                f"profit_target should be positive, got {self.profit_target}"
            )

    def blocks_position(self, proposed_position: float) -> bool:
        """Whether a proposed position would breach the position limit."""
        return self.max_position is not None and abs(proposed_position) > self.max_position

    def breach_from_pnl(self, pnl: float) -> LimitBreach:
        """Whether a P&L level has hit the stop loss or the profit target."""
        if self.stop_loss is not None and pnl <= self.stop_loss:
            return LimitBreach.STOP_LOSS
        if self.profit_target is not None and pnl >= self.profit_target:
            return LimitBreach.PROFIT_TARGET
        return LimitBreach.NONE


@dataclass
class Trader:
    """The trader's position and P&L (Practical A, Task B, Step 2).

    Position is held in units of notional: positive is long CCY1, negative is short,
    following the Chapter 1 convention that long and short always refer to CCY1.
    P&L is in CCY2, which is where it is naturally generated.

    Args:
        limits: Risk limits to enforce. Defaults to no limits, which is the book's
            starting point before the extension.
        trade_notional: Default size for a price-taking trade.
    """

    limits: RiskLimits = field(default_factory=RiskLimits)
    trade_notional: float = 1.0

    position: float = field(init=False, default=0.0)
    pnl: float = field(init=False, default=0.0)
    trades_taken: int = field(init=False, default=0)
    trades_made: int = field(init=False, default=0)
    spread_paid: float = field(init=False, default=0.0)
    spread_earned: float = field(init=False, default=0.0)
    blocked_trades: int = field(init=False, default=0)

    def mark_to_market(self, spot_increment: float) -> None:
        """Mark the existing position to the new spot (Task B, tick step 3).

        ``P&L_CCY2 = Notional_CCY1 * (S_new - S_old)`` from Chapter 1, applied one
        tick at a time. This runs on the position held *before* any trade this tick,
        which is why the book's ordering puts it first.

        Args:
            spot_increment: The move in the mid rate this tick.
        """
        self.pnl += self.position * spot_increment

    def take_price(self, action: TraderAction, half_spread: float) -> LimitBreach:
        """Cross the spread as a price taker (Task B, tick step 6).

        Buying lifts the offer, selling hits the bid. **Both cost half the spread**,
        which is the structural fact Practical A exists to demonstrate: a price taker
        is negative carry, and every trade starts underwater by exactly this much.

        Args:
            action: What the trader chose to do.
            half_spread: Half the current bid-offer spread, per unit of notional.

        Returns:
            ``LimitBreach.POSITION_LIMIT`` if the position limit blocked the trade,
            otherwise ``LimitBreach.NONE``.
        """
        if action is TraderAction.NOTHING:
            return LimitBreach.NONE

        signed = self.trade_notional if action is TraderAction.BUY else -self.trade_notional
        proposed = self.position + signed

        if self.limits.blocks_position(proposed):
            self.blocked_trades += 1
            return LimitBreach.POSITION_LIMIT

        self.position = proposed
        cost = half_spread * self.trade_notional
        self.pnl -= cost
        self.spread_paid += cost
        self.trades_taken += 1
        return LimitBreach.NONE

    def make_price(self, market_buys: bool, notional: float, half_spread: float) -> None:
        """Get dealt on as a price maker (Task C).

        The mirror image of :meth:`take_price`. The trader **earns** half the spread
        but does not choose the direction - the position moves against whatever the
        market wanted to do.

        Sign convention, which is the thing to get right: the market *buying* means
        the trader sold, so the position gets **shorter**.

        Note the position limit is deliberately not enforced here. A price maker
        cannot decline a trade that has already happened, and watching an unwanted
        position accumulate past a limit is exactly the risk Chapter 3 describes.
        The breach is reported by the simulator rather than prevented.

        Args:
            market_buys: True if the market bought from the trader.
            notional: Size the market traded in.
            half_spread: Half the current bid-offer spread, per unit of notional.
        """
        self.position += -notional if market_buys else notional
        earned = half_spread * notional
        self.pnl += earned
        self.spread_earned += earned
        self.trades_made += 1

    def check_pnl_limits(self) -> LimitBreach:
        """Whether P&L has hit the stop loss or the profit target."""
        return self.limits.breach_from_pnl(self.pnl)

    def reset(self) -> None:
        """Clear the position, P&L and all counters."""
        self.position = 0.0
        self.pnl = 0.0
        self.trades_taken = 0
        self.trades_made = 0
        self.spread_paid = 0.0
        self.spread_earned = 0.0
        self.blocked_trades = 0
