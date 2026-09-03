"""The trading simulator - Practical A (Ch. 3).

Task A sets up a ticking mid-market spot; Task B adds a two-way price and price-taking
controls; Task C adds price-making via simulated market participants. The book's
extensions - risk limits and P&L targets, volatility-based spot evolution, directional
participants and variable notionals - are implemented too.

``market.py`` and ``trader.py`` are headless and steppable, so the simulator can be
run in a batch of a thousand sessions for the P&L distribution experiment as easily as
it can be clicked through one tick at a time in ``app.py``.

The lesson the practical is built around, in one line: **the price taker pays half the
spread on every trade in either direction and is structurally negative carry; the price
maker earns it but does not choose the resulting position.**
"""

from .engine import (
    Simulator,
    Strategy,
    TickRecord,
    over_trading,
    passive,
    risk_reducing,
    run_many,
)
from .market import (
    Market,
    MarketAction,
    MarketParticipants,
    ParticipantBias,
    SpotProcess,
    TwoWayPrice,
)
from .trader import LimitBreach, RiskLimits, Trader, TraderAction

__all__ = [
    "LimitBreach", "Market", "MarketAction", "MarketParticipants", "ParticipantBias",
    "RiskLimits", "Simulator", "SpotProcess", "Strategy", "TickRecord", "Trader",
    "TraderAction", "TwoWayPrice", "over_trading", "passive", "risk_reducing",
    "run_many",
]
