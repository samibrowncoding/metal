"""EikonProvider - live data via the ``eikon`` package.

Guarded import, same as the Bloomberg provider.

Worth knowing before you try: the ``eikon`` package talks to a local proxy running as
part of your own Workspace session - port 9060 for Workspace, 9000 for legacy Eikon.
It is not a cloud endpoint. You need Workspace running under your own licensed seat
and your own App Key from the App Key Generator.

Refinitiv volatility RICs vary by contributor. The candidates in ``tickers.yaml`` are
marked ``verified: false`` and must be confirmed before use - see
``docs/ticker_verification.md``. A wrong ticker that silently returns something
plausible is worse than a missing one.
"""
