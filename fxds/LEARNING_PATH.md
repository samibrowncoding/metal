# Learning path

The ordered route through *FX Derivatives Trader School* (Jewitt, Wiley 2015) and this
repository. Chapters 1–12, Practicals A–F.

Read the book chapter first, then run the notebook. The notebooks assume you have read
the chapter — they demonstrate and stress-test the ideas rather than re-explaining them
from nothing.

**Time estimates are honest, not encouraging.** They assume you are new to derivatives,
comfortable with Python and market data, and actually doing the experiments rather than
running all cells and scrolling. If a stage takes you half the estimate you probably
skipped the experiments; if it takes double, that is normal for Stages 5 and 8.

Total: roughly **35–45 hours**. This is a fortnight of evenings, not a weekend.

---

## Before you start

```bash
cd fxds
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                      # everything should pass on synthetic data
jupyter lab notebooks/
```

No market data connection is needed for any of this. `FXDS_PROVIDER` defaults to `fake`.

---

## Stage 0 — Orientation · ~30 min
**Notebook:** `00_orientation.ipynb`
**Read:** the book's Preface; this file; `notes/source_notes.md` skim.

What the repo contains, how the package and notebooks relate, how to run the tests, and
where the simplifications are recorded. Also sets the register: the book keeps its maths
at "advanced high school" level deliberately, and so do we.

---

## Stage 1 — FX and derivatives basics · ~2 h
**Read:** Chapters 1–2
**Notebook:** `01_fx_basics.ipynb`
**Module:** `conventions.py`

CCY1/CCY2, pips and big figures, spot and forward, the two P&L formulas and why the CCY1
one is curved. Then calls and puts, the apple-orchard framing the book uses, contract
details, and the fact that a single FX option is simultaneously a call on one currency
and a put on the other.

**You will get this wrong at least once:** which side of the pair the notional is in, and
that the strike (not spot) converts notionals between currencies.

---

## Stage 2 — How trading works, and the simulator · ~3 h
**Read:** Chapter 3, then Practical A
**Notebook:** `02_practical_A_simulator.ipynb`
**Modules:** `simulator/`
**App:** `streamlit run fxds/simulator/app.py`

Bids and offers, price takers versus price makers, and why the price taker is
structurally negative-carry. Build the simulator, then run it: five seconds between ticks
to start with, until the interaction between market, position and P&L is second nature.

Do the batch experiment at the end — 1,000 headless sessions, passive versus over-trading
— before you decide you already believe the lesson. Seeing the two P&L distributions side
by side is different from being told.

**Budget most of this stage on the app, not the reading.**

---

## Stage 3 — Market structure · ~1 h
**Read:** Chapter 4
**Notebook:** `03_market_structure.ipynb`

Conceptual, no practical. OTC versus exchange, client types, the interbank broker market
mechanics, direct calls. Short, and skippable if you only care about the maths — but it
is what makes the tenor and convention machinery later on make sense rather than seem
arbitrary.

---

## Stage 4 — Black-Scholes and the integration pricer · ~4 h
**Read:** Chapter 5, then Practical B
**Notebook:** `04_practical_B_numerical.ipynb`
**Module:** `numerical.py`

The SDE, drift versus uncertainty, why zero volatility does not mean static spot, the Itō
correction, and log-normality. Then build the terminal spot distribution and integrate a
payoff against it.

**The single chart this stage exists to produce** is the payoff overlaid on the density.
Sit with it. Move the volatility slider and watch the distribution widen; move the rate
differential and watch it shift.

Acceptance tests: forward struck at the forward prices to zero; the `S=K=100`, zero-rate,
one-year call prices just under 4.00 CCY1%.

---

## Stage 5 — Black-Scholes closed form and the greeks · ~5 h
**Read:** Chapter 5 again (the formula section), then Practical C, then Chapter 6
**Notebooks:** `05_practical_C_blackscholes.ipynb`, then `06_greeks.ipynb`
**Modules:** `blackscholes.py`, `greeks.py`

The longest stage and the most important. Garman–Kohlhagen, notional handling, the
premium conversions, and put–call parity — including working out for yourself why the
undiscounted version fails before reading the answer.

Then greeks twice over: closed form and finite difference. Sweep the bump size and watch
accuracy fall apart at both ends. Then Chapter 6 for what delta, gamma and vega actually
mean on a desk, and put–call parity in greek terms.

**Run the cross-validation test here** (`tests/test_cross_validation.py`): Practical B's
integration and Practical C's closed form agreeing to a stated tolerance is the moment
both halves stop being exercises and start being a pricing engine.

**Traps this stage:** delta sign conventions; pips versus percent; that delta-hedged calls
and puts with the same strike are the same position.

---

## Stage 6 — Pricing, structures and risk management · ~4 h
**Read:** Chapters 7, 8, 9
**Notebooks:** `07_pricing_and_structures.ipynb`, `08_risk_management.ipynb`
**Modules:** `structures.py`, `greeks.py`

No practicals attach here, which makes it tempting to skim. Don't — this is where the
intuition lives.

Chapter 7 gives you the volatility surface as a concept, the three competing ATM
definitions, and bid–offer spread structure. Chapter 8 builds the structures. Chapter 9 is
gamma trading, theta, spot ladders and bucketed vega: the actual job.

**Traps:** ATM meaning delta-neutral straddle rather than at-the-forward; premium-included
versus premium-excluded delta; spot versus forward versus delta-neutral ATM.

---

## Stage 7 — Tenor dates · ~2 h
**Read:** Chapter 10, then Practical D
**Notebook:** `09_practical_D_dates.ipynb`
**Module:** `dates.py`

Discounting conventions, the four dates, and the tenor rules. Short and mechanical, but
everything in Part II depends on it.

Pay attention to the asymmetry: weeks are added to the horizon directly, while months and
years go out to a delivery date from the spot date and come back two business days. That
is not a quirk — month contracts are defined by delivery.

---

## Stage 8 — The ATM curve · ~6 h
**Read:** Chapter 11, then Practical E
**Notebook:** `10_practical_E_atm_curve.ipynb`
**Module:** `atm_curve.py`

The hardest stage, and the one that most changes how you read a volatility screen.

Variance first: non-negative and additive, which volatility is not. Then the two
interpolation methods and the genuine tradeoff between them — linear-in-vol looks right
but can produce negative forward variance; linear-in-variance is safe but looks wrong.
Then the parametric model. Then day weights.

**Task C is the centre of the whole practical.** Set every weight to 1 and get a flat
curve. Set weekend weights to zero and the saw-tooth appears. Then raise the weight on the
Non-Farm Payrolls date and watch that date *and every date after it* rise. Do not read
ahead to the charts; predict first.

Finish with forward variance and the implied forward overnight vol — that strip is what a
trader reads to judge whether the curve is rich or cheap over an event.

---

## Stage 9 — The volatility smile · ~4 h
**Read:** Chapter 12, then Practical F
**Notebook:** `11_practical_F_smile.ipynb`
**Module:** `smile.py`

The Malz formula, then strike-from-delta, then the strike placement experiments. Each
experiment gets a prediction before a chart.

**Traps:** the true negative put delta inside the formulas versus the positive quoted
delta; smile versus skew as terms; and the big one — the broker fly the market actually
trades is not the strike fly this practical builds. The book says so; the module docstring
says so; believe both.

---

## Stage 10 — Assembling the surface · ~3 h
**Notebook:** end of `11_practical_F_smile.ipynb`
**Module:** `surface.py`

Tenor dates → ATM curve with weights → smile per tenor → `vol(expiry_date, strike)`. The
book never joins these three up. Doing it yourself is the point.

Read `SIMPLIFICATIONS` in the module before you trust a number out of it.

---

## Stage 11 — Market data · ~2 h
**Read:** `docs/ticker_verification.md`
**Modules:** `marketdata/`

How the provider seam works, what the fake provider generates and why, and — if you have
a terminal — how to verify every ticker before trusting it. Optional if you are working
purely synthetically, which is a perfectly reasonable way to do all of the above.

---

## Where to go next (out of scope for this pass)

Chapter 13 and Practical G build a probability density function from option prices, which
is the natural continuation. Chapters 14–17 are vanilla trading proper: adapted vega,
weighted vega, premium-adjusted delta — all the things this repo flags as simplifications
and defers. Part IV is exotics.

None of that is built here. When you get there, the surface object in `surface.py` is the
thing you would extend.

---

## Reference material in this repo

| File | What it is |
|---|---|
| `notes/source_notes.md` | The working spec: every formula, convention and test value, chapter by chapter |
| `notes/glossary.md` | Every term of art in plain English, alphabetical, with the chapter it first appears in |
| `notes/deviations.md` | Everywhere this implementation departs from the book, and why |
| `docs/ticker_verification.md` | How to verify each market data ticker before relying on it |
