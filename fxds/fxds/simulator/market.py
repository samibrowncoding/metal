"""Ticking mid, bid/offer and market participants - Practical A, Tasks A and C.

The Excel original drove the clock with ``Application.OnTime`` and Form Control
buttons. Here the market is a plain object with a ``step()`` method: the Streamlit app
supplies the clock, and tests supply their own. See ``notes/deviations.md``.

Everything that consumes randomness takes a ``numpy.random.Generator``, so a whole
session replays identically from a seed. The book's simulator cannot be replayed;
this one can, which is what makes it testable and what makes the thousand-session
experiment in notebook 02 possible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np


class SpotProcess(str, Enum):
    """How spot evolves from one tick to the next.

    * ``FIXED_INCREMENT`` - the book's Task A: up or down by a fixed amount, each with
      probability one half. Crude, but it makes the mechanics obvious and every
      P&L number checkable by hand.
    * ``VOLATILITY`` - the first extension the book suggests. Geometric Brownian
      motion, discretised, so spot moves proportionally rather than in fixed steps
      and the size of each move varies.
    """

    FIXED_INCREMENT = "fixed_increment"
    VOLATILITY = "volatility"


class ParticipantBias(str, Enum):
    """How the simulated market participants choose their direction.

    * ``INDEPENDENT`` - the book's Task C: fixed probabilities, each tick independent
      of everything that came before.
    * ``MEAN_REVERTING`` - the book's third extension. Participants are more likely to
      buy after spot has fallen and sell after it has risen, so flow leans against
      the recent move. A trader who knows the rule can position for the flow.
    * ``TREND_FOLLOWING`` - the same extension with the sign flipped: participants
      chase the move. Harder to warehouse, because the flow arrives in the direction
      that is already hurting you.
    """

    INDEPENDENT = "independent"
    MEAN_REVERTING = "mean_reverting"
    TREND_FOLLOWING = "trend_following"


class MarketAction(str, Enum):
    """What the simulated participants did on a given tick.

    Named from the **market's** point of view, which is the direction that trips
    people up. ``BUYS`` means the market bought *from the trader*, so the trader ends
    up shorter.
    """

    NONE = "none"
    BUYS = "market buys"
    SELLS = "market sells"


@dataclass
class TwoWayPrice:
    """A bid and an offer around a mid (Practical A, Task B, Step 1).

    Attributes:
        mid: The mid-market rate.
        spread: Total bid-offer spread. Half of it sits either side of the mid.
    """

    mid: float
    spread: float

    @property
    def bid(self) -> float:
        """The rate at which the price maker will buy - what a seller receives."""
        return self.mid - self.spread / 2

    @property
    def offer(self) -> float:
        """The rate at which the price maker will sell - what a buyer pays."""
        return self.mid + self.spread / 2

    @property
    def half_spread(self) -> float:
        """The cost of crossing, per unit of notional.

        This single number is the whole lesson of Practical A: a price taker pays it
        on every trade in either direction, and a price maker earns it.
        """
        return self.spread / 2


@dataclass
class Market:
    """The ticking mid-market spot rate (Practical A, Task A).

    Args:
        initial_spot: Starting mid rate.
        spot_increment: Size of each move under ``FIXED_INCREMENT``.
        bid_offer_spread: Total spread quoted around the mid.
        process: Which spot process to use.
        volatility: Annualised volatility, used only under ``VOLATILITY``.
        ticks_per_year: How many ticks make up a year, used only under
            ``VOLATILITY``. The default of 252 * 24 treats a tick as roughly an hour
            of a trading day; it only affects how big a typical move looks.
        rng: Random source. Supply a seeded generator for a reproducible session.
    """

    initial_spot: float = 1.3000
    spot_increment: float = 0.0005
    bid_offer_spread: float = 0.0010
    process: SpotProcess = SpotProcess.FIXED_INCREMENT
    volatility: float = 0.10
    ticks_per_year: float = 252 * 24
    rng: np.random.Generator = field(default_factory=np.random.default_rng)

    mid: float = field(init=False)
    step_count: int = field(init=False, default=0)
    last_increment: float = field(init=False, default=0.0)

    def __post_init__(self) -> None:
        if self.initial_spot <= 0:
            raise ValueError(f"Initial spot must be positive, got {self.initial_spot}")
        if self.spot_increment <= 0:
            raise ValueError(f"Spot increment must be positive, got {self.spot_increment}")
        if self.bid_offer_spread < 0:
            raise ValueError(f"Spread cannot be negative, got {self.bid_offer_spread}")
        self.mid = self.initial_spot

    @property
    def price(self) -> TwoWayPrice:
        """The current two-way price around the mid."""
        return TwoWayPrice(self.mid, self.bid_offer_spread)

    def draw_increment(self) -> float:
        """Draw the next spot move, without applying it.

        Separated from ``advance`` because the tick ordering in Task B needs the
        increment *before* spot moves: the existing position is marked to the new
        spot using this increment, and only then does the mid update.

        Returns:
            The signed move in the mid rate.
        """
        if self.process is SpotProcess.FIXED_INCREMENT:
            # Task A: up or down by the same fixed amount, 50/50.
            return self.spot_increment if self.rng.random() > 0.5 else -self.spot_increment

        # Extension: geometric Brownian motion with zero drift. Returned as an
        # absolute move so the rest of the tick arithmetic is unchanged - the
        # position is marked in CCY2 per CCY1 either way.
        dt = 1.0 / self.ticks_per_year
        shock = self.rng.normal()
        new_mid = self.mid * np.exp(
            -0.5 * self.volatility**2 * dt + self.volatility * np.sqrt(dt) * shock
        )
        return float(new_mid - self.mid)

    def advance(self, increment: float) -> None:
        """Apply a drawn increment and advance the step counter.

        Args:
            increment: The move to apply, from :meth:`draw_increment`.

        Raises:
            ValueError: If the move would take spot to zero or below. Under the
                fixed-increment process that is possible in principle, since the
                move is absolute rather than proportional.
        """
        new_mid = self.mid + increment
        if new_mid <= 0:
            raise ValueError(
                f"Spot would go to {new_mid}, which is not a rate. Reduce the "
                f"increment or raise the initial spot."
            )
        self.mid = new_mid
        self.last_increment = increment
        self.step_count += 1

    def reset(self) -> None:
        """Return to the initial spot and clear the step counter."""
        self.mid = self.initial_spot
        self.step_count = 0
        self.last_increment = 0.0


@dataclass
class MarketParticipants:
    """Simulated price takers who trade on the trader's bid and offer (Task C).

    The book's framing: within this simplified world the participants transact at the
    *market* bid and offer rather than at a price the trader has made. What it shows
    is how a price maker has to deal with flow they did not choose.

    Args:
        buy_probability: Chance per tick that the market buys from the trader.
        sell_probability: Chance per tick that the market sells to the trader.
        bias: How direction is chosen. See :class:`ParticipantBias`.
        bias_strength: How far the bias tilts the probabilities, as a fraction of the
            base probability. 0.0 is no tilt; 1.0 can double one side and zero the
            other. Only used when ``bias`` is not ``INDEPENDENT``.
        notional_choices: Trade sizes the market can arrive in. The book's extension
            suggests varying notionals; the default of a single unit reproduces the
            original Task C exactly.
        notional_weights: Relative likelihood of each size. Defaults to uniform.
        rng: Random source.

    Raises:
        ValueError: If the probabilities are negative or sum above 1, or if the
            notional lists are empty or mismatched.
    """

    buy_probability: float = 0.15
    sell_probability: float = 0.15
    bias: ParticipantBias = ParticipantBias.INDEPENDENT
    bias_strength: float = 0.5
    notional_choices: tuple[float, ...] = (1.0,)
    notional_weights: tuple[float, ...] | None = None
    rng: np.random.Generator = field(default_factory=np.random.default_rng)

    def __post_init__(self) -> None:
        if self.buy_probability < 0 or self.sell_probability < 0:
            raise ValueError("Participant probabilities cannot be negative")
        if self.buy_probability + self.sell_probability > 1.0:
            raise ValueError(
                f"Participant probabilities sum to "
                f"{self.buy_probability + self.sell_probability}, which exceeds 1"
            )
        if not self.notional_choices:
            raise ValueError("notional_choices cannot be empty")
        if any(n <= 0 for n in self.notional_choices):
            raise ValueError("Every notional must be positive")
        if self.notional_weights is not None and len(self.notional_weights) != len(
            self.notional_choices
        ):
            raise ValueError("notional_weights must be the same length as notional_choices")

    def _tilted_probabilities(self, recent_move: float) -> tuple[float, float]:
        """Adjust the buy and sell probabilities for the recent spot move.

        Under ``MEAN_REVERTING`` a fall in spot makes buying more likely; under
        ``TREND_FOLLOWING`` it makes selling more likely. The tilt is capped so
        neither probability can go negative or push the pair above 1.
        """
        if self.bias is ParticipantBias.INDEPENDENT or recent_move == 0.0:
            return self.buy_probability, self.sell_probability

        direction = 1.0 if recent_move > 0 else -1.0
        # Mean reverting: spot up (direction +1) => buying less likely.
        # Trend following: spot up => buying more likely.
        sign = -direction if self.bias is ParticipantBias.MEAN_REVERTING else direction

        tilt = np.clip(self.bias_strength, 0.0, 1.0)
        buy = self.buy_probability * (1 + sign * tilt)
        sell = self.sell_probability * (1 - sign * tilt)

        # Keep the pair a valid probability split.
        buy = float(np.clip(buy, 0.0, 1.0))
        sell = float(np.clip(sell, 0.0, 1.0 - buy))
        return buy, sell

    def draw_notional(self) -> float:
        """Draw a trade size from the configured choices."""
        if len(self.notional_choices) == 1:
            return self.notional_choices[0]
        weights = self.notional_weights
        p = None if weights is None else np.asarray(weights, dtype=float) / sum(weights)
        return float(self.rng.choice(self.notional_choices, p=p))

    def draw(self, recent_move: float = 0.0) -> tuple[MarketAction, float]:
        """Decide what the market does this tick (Practical A, Task C).

        One uniform draw decides between three outcomes, exactly as the book has it:
        below the buy probability the market buys, in the next band it sells,
        otherwise nothing happens.

        Args:
            recent_move: The last spot move, used only when a bias is configured.

        Returns:
            The action and the notional it traded in. The notional is zero when
            nothing happened.
        """
        buy_p, sell_p = self._tilted_probabilities(recent_move)
        signal = self.rng.random()

        if signal < buy_p:
            return MarketAction.BUYS, self.draw_notional()
        if signal < buy_p + sell_p:
            return MarketAction.SELLS, self.draw_notional()
        return MarketAction.NONE, 0.0
