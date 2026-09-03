"""Greek exposures and risk profiles - Ch. 6 and Ch. 9.

Delta, gamma, vega and theta, plus the profile helpers the risk-management notebook
needs: spot ladders showing P&L, delta and gamma across spot levels, and bucketed
vega by tenor.

Chapter 6 defines the exposures; Chapter 9 shows what a trader does with them. The
consistency relations in Chapter 9 (long gamma with spot higher gets longer delta,
and so on) are implemented as checkable assertions, because they are the first thing
to verify when a position looks wrong.
"""
