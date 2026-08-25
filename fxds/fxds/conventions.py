"""Market conventions: CCY1/CCY2, pips, premium and quote conventions.

Implements the conventions introduced in Chapter 1 (currency pairs, pips, big
figures), Chapter 2 (notional conversion via the strike), Chapter 7 (the three ATM
definitions, the out-of-the-money trading convention) and Chapter 10 (premium
quotation in CCY1%, CCY2 pips, CCY2%, CCY1 pips).

A currency pair is written CCY1/CCY2 and the rate is the number of CCY2 required to
buy one CCY1. Every sign and unit decision in this package follows from that.
"""
