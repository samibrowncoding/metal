"""Trader position, P&L and actions - Practical A, Task B.

The tick ordering matters and follows the book exactly: mark the existing position to
the new spot first, then move spot, then process the trade and charge half the spread.
Getting this order wrong quietly changes the P&L by one tick's worth of drift.
"""
