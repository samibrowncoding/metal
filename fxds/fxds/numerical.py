"""Terminal spot distribution and the integration pricer - Practical B (Ch. 5).

Implements Practical B: build the log-normal terminal spot distribution across plus
or minus five standard deviations, attach a payoff that depends only on spot at
maturity, and integrate the two together to get the option value.

This is the slow, general route to a price: it works for any payoff that depends only
on the terminal spot, no matter how awkward. Practical C's closed form is the fast,
special-case route. That the two agree is the headline cross-validation test of this
repository - see ``tests/test_cross_validation.py``.
"""
