"""Market data providers.

Everything in this repository runs on synthetic data by default and no test ever
requires a terminal. Select a provider with the ``FXDS_PROVIDER`` environment
variable: ``fake`` (default), ``book``, ``bloomberg`` or ``eikon``.

* ``fake``      - deterministic, seeded, plausible. The default.
* ``book``      - the exact input values used in the book's practicals, so the
                  numbers in the text can be reproduced.
* ``bloomberg`` - via xbbg. Guarded import; needs a running terminal.
* ``eikon``     - via the eikon package. Guarded import; needs Workspace running
                  under your own licensed seat.

Vols are decimals internally (0.085, not 8.5). Units are normalised at the provider
boundary and nowhere else.
"""
