"""Garman-Kohlhagen pricing and first-order greeks - Practical C (Ch. 5-6).

Implements Practical C in full:

* Task A - forward, call and put prices in CCY2 pips, notional handling and the
  premium conversions, and put-call parity including why the undiscounted form fails.
* Task B - the pricing function itself, with the guard against non-positive time to
  expiry or volatility that the book asks for.
* Task C - delta and vega by closed form and by central finite difference, plus the
  market quotation conventions for each.
* Task D - the exposure profiles (delta, vega and value against spot, time and
  volatility) that the notebooks plot.

Prices are in CCY2 pips (CCY2 per one CCY1) unless a function says otherwise.
"""
