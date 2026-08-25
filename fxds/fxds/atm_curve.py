"""ATM curve construction: interpolation, model and day weights - Practical E (Ch. 11).

Implements Practical E:

* Task A - linear-in-volatility and linear-in-total-variance interpolation between
  market tenors, with explicit errors outside the quoted range.
* Task B - the parametric curve sigma_T = sigma_short + (sigma_long - sigma_short) *
  (1 - exp(-lambda * T)), plus a least-squares calibration that goes beyond the book.
* Task C - day weights, economic versus calendar time, the weekend saw-tooth, event
  weighting, and daily forward variance with a check for the negative-forward-variance
  arbitrage.

Variance, not volatility, is the quantity that has to stay well behaved: it must be
non-negative and it is additive across time. Volatility is neither.
"""
