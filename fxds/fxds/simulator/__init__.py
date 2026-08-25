"""The trading simulator - Practical A (Ch. 3).

Task A sets up a ticking mid-market spot; Task B adds a two-way price and price-taking
controls; Task C adds price-making via simulated market participants. The book's
extensions - risk limits and P&L targets, volatility-based spot evolution, directional
participants and variable notionals - are implemented too.

``market.py`` and ``trader.py`` are headless and steppable, so the simulator can be
run in a batch of a thousand sessions for the P&L distribution experiment as easily as
it can be clicked through one tick at a time in ``app.py``.
"""
