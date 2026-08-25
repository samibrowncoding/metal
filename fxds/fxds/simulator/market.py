"""Ticking mid, bid/offer and market participants - Practical A, Tasks A and C.

The Excel original drove the clock with ``Application.OnTime`` and Form Control
buttons. Here the market is a plain object with a ``step()`` method: the Streamlit app
supplies the clock, and tests supply their own. See ``notes/deviations.md``.
"""
