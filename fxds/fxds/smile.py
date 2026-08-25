"""The Malz volatility smile and strike-from-delta - Practical F (Ch. 12).

Implements Practical F: the Malz (1997) smile parameterisation in delta space, put
delta from strike and its inversion, and the strike placement experiments that show
what the ATM, risk reversal and butterfly each do to where strikes land.

Sign convention, which trips everyone up at least once: the put delta used inside the
Black-Scholes formulas here is the true, negative value. The market quotes put deltas
as positive numbers ("ten delta put" means -10%), and the Malz formula itself takes
that positive quoted delta. Each function's docstring says which it expects.

Simplification carried throughout: this is the outright-delta smile, not the broker
fly the interbank market actually trades. See Chapter 12 and ``notes/deviations.md``.
"""
