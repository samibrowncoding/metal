"""Vanilla structures: straddle, strangle, risk reversal, fly, spreads - Ch. 8.

No practical attaches to Chapter 8, but the structures are where the greek intuition
from Chapter 6 turns into something a desk actually trades. Covers the straddle
(including the zero-delta straddle strike and how it differs under CCY1 versus CCY2
premium), the strangle, the butterfly, the risk reversal, the leveraged forward, the
ATM calendar spread, call and put spreads and the seagull.

Each structure is built from vanillas priced in ``blackscholes.py`` - nothing is
special-cased, so the payoff and vega profiles come out of the same engine.
"""
