"""BloombergProvider - live data via xbbg (or blpapi directly).

Guarded import: constructing this provider without a running terminal raises a clear,
actionable error rather than failing somewhere deep in a query. Tickers come from
``tickers.yaml``, never inline.
"""
