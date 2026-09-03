"""The MarketDataProvider protocol and the typed models every provider returns.

One canonical internal representation: volatilities are decimals (0.085 means 8.5%),
rates are continuously compounded decimals, and spot is CCY2 per CCY1. Providers
convert at their own boundary and nowhere else - there is a test that fails if any
provider hands back a volatility above 1.0.
"""
