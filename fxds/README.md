# fxds — FX derivatives from first principles

A Python learning repository built alongside ***FX Derivatives Trader School*** by Giles
Jewitt (Wiley, 2015). It reproduces every practical from the first half of the book —
**Chapters 1–12, Practicals A–F** — as idiomatic Python, with enough teaching material
around the code to explain why each piece exists.

You need a copy of the book. This repo is a companion to it, not a replacement: the code
and explanations are original, and the book is cited by chapter and practical number
throughout.

| Practical | Title | Chapter | Module |
|---|---|---|---|
| A | Trading Simulator | 3 | `fxds/simulator/` |
| B | Numerical Integration Pricer | 5 | `fxds/numerical.py` |
| C | Black-Scholes Pricer | 5–6 | `fxds/blackscholes.py` |
| D | Tenor Dates | 10 | `fxds/dates.py` |
| E | ATM Curve | 11 | `fxds/atm_curve.py` |
| F | Volatility Smile | 12 | `fxds/smile.py` |
| — | Assembled surface (not in the book) | D+E+F | `fxds/surface.py` |

Practical G onwards (Chapter 13+) is out of scope.

## Getting started

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
jupyter lab notebooks/
```

Then follow **[LEARNING_PATH.md](LEARNING_PATH.md)** — it gives the ordered route through
book chapters and notebooks with time estimates.

Everything runs on synthetic data. No market data terminal is required, and no test ever
touches one.

## How this repo is organised

The **package implements, the notebooks demonstrate.** Notebooks import from `fxds/` and
never redefine the maths inline, so there is exactly one implementation of each formula
and the tests cover the thing the notebooks actually run.

```
fxds/            the package — one module per practical, plus shared conventions and plotting
notebooks/       one per stage of the learning path
notes/           source_notes.md (the working spec), glossary.md, deviations.md
tests/           one per module, plus the B-vs-C cross-validation test
docs/            ticker verification procedure
```

Three files worth reading before the code:

- **`notes/source_notes.md`** — the working spec. Every formula, convention and test value
  from Chapters 1–12, chapter by chapter.
- **`notes/deviations.md`** — everywhere this implementation departs from the book, and why.
- **`notes/glossary.md`** — every term of art in plain English.

## Design choices

**Explicit maths over library black boxes.** The teaching modules show `norm.cdf(d1)` and
the formula around it, not a one-line call into a pricing library. scipy supplies the
distribution functions and root finders; nothing more.

**Readability over cleverness.** No abstract base class hierarchies, no plugin framework.
Where a function does something non-obvious, the comment explains the *why*.

**Simplifications are stated, not smoothed over.** The book is candid about what it sets
aside — credit, rates curves, broker fly strike placement, premium-adjusted delta — and
those caveats are carried through rather than quietly dropped. Where the book leaves a
convention unspecified, the common one is implemented and flagged in the docstring and in
`notes/deviations.md`.

## Market data

Everything defaults to synthetic data. Select a provider with `FXDS_PROVIDER`:

| Value | Provider | Needs |
|---|---|---|
| `fake` *(default)* | Seeded, deterministic, plausible | nothing |
| `book` | The exact inputs used in the book's practicals | nothing |
| `bloomberg` | via `xbbg` | a running terminal |
| `eikon` | via `eikon` | Workspace running under your own licensed seat |

Tickers live in `fxds/marketdata/tickers.yaml`, never inline. Refinitiv volatility RICs
vary by contributor and are marked `verified: false` until you confirm them — see
`docs/ticker_verification.md`. A wrong ticker that silently returns something plausible is
worse than a missing one.

## Copyright

The book's VBA source and prose are not reproduced here. Concepts are paraphrased,
mathematical formulas are standard results reproduced as such, and references are by
chapter and practical number.

## Build status

Built in stages, with a checkpoint at each. See `LEARNING_PATH.md` for the reader's route
and the task list for the build order.

- [x] **Stage 1** — source notes, repo skeleton, learning path
- [ ] Stage 2 — Practicals B and C, notebooks and tests
- [ ] Stage 3 — Practical A simulator and Streamlit app
- [ ] Stage 4 — Practicals D, E, F and the assembled surface
- [ ] Stage 5 — Chapters 6–9 concept notebooks
- [ ] Stage 6 — market data layer
- [ ] Stage 7 — glossary, README polish, final learning path pass
