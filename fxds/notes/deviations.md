# Deviations from the book

Every place this implementation departs from *FX Derivatives Trader School* (Jewitt, 2015),
and why. Per the ground rules: nothing from the book's tasks, steps or test cases is
silently dropped. Where something could not be translated sensibly to Python, the nearest
equivalent is implemented and recorded here.

Three categories:

- **[EXCEL]** — the step exists only because Excel/VBA works the way it does. The intent is
  implemented; the mechanism differs.
- **[FIX]** — the book's printed code has a defect. Corrected here.
- **[CONVENTION]** — the book does not specify something. The common market convention is
  implemented and flagged in the relevant docstring.
- **[SCOPE]** — deliberately not built in this pass.

This file is updated as each stage lands. Entries marked *(planned)* describe decisions
already taken in `notes/source_notes.md` but not yet in code.

---

## Practical A — Trading Simulator

| Tag | Book | Here | Why |
|---|---|---|---|
| [EXCEL] | `Application.OnTime` schedules the next tick | `Simulator.step()` is called by whatever supplies the clock — Streamlit's rerun loop, or a `for` loop in a test | Excel has no other way to get a repeating timer out of VBA. Separating the clock from the model is what makes the batch experiment and the tests possible at all. *(planned)* |
| [EXCEL] | Named cells (`Range("SpotMidMarket")`) as the data model | Typed attributes on a dataclass | Named ranges are Excel's substitute for variables. The book is explicit that naming beats cell references; in Python that is just an object. *(planned)* |
| [EXCEL] | Go/Pause and Stop buttons from Form Controls; option buttons for the trader action | Streamlit buttons over session state; radio for the action | Same intent, different widget toolkit. *(planned)* |
| [EXCEL] | Chart pre-selected over ~500 mostly blank rows so it auto-resizes | Plotly chart redrawn from the recorded path | The blank-row trick is a workaround for Excel charts not growing with data. *(planned)* |
| [EXCEL] | `Rnd()` for randomness | `numpy.random.Generator`, seedable | Reproducibility. The book's simulator cannot be replayed; ours can, which is what makes it testable. *(planned)* |

---

## Practical B — Numerical Integration Pricer

| Tag | Book | Here | Why |
|---|---|---|---|
| [EXCEL] | 101 rows on a sheet from −5 to +5 standard deviations | A numpy array over the same grid | Same numbers. Vectorised where it does not obscure the formula. *(planned)* |
| [CONVENTION] | Test 2 gives `S = K = 100`, `r1 = r2 = 0`, `T = 1.0` and expects "very slightly under 4.00 CCY1%" but does not state σ in the text | σ = 10% | The closed-form ATM value `0.3989·σ·√T` gives 3.99% at σ = 10%, which is what "very slightly under 4.00" describes. Consistent with the σ used in Practical C's test. *(planned)* |

---

## Practical C — Black-Scholes Pricer

| Tag | Book | Here | Why |
|---|---|---|---|
| [FIX] | The printed VBA guard reads `If (T >= 0) Then T = 0.0000000001` (and likewise for volatility) | `if T <= 0: T = 1e-10` | As printed the guard fires on every valid input and destroys the price. The surrounding prose says the intent plainly: clamp non-positive time and volatility to a small positive value so the formula returns the payoff at maturity. Implemented per the prose. *(planned)* |
| [EXCEL] | Task B exists to move the calculation from cell formulas into a VBA function | The module function is the only implementation | In Python there is no cell-formula stage to graduate from. The task's actual content — the input signature, the guard, the structure — is implemented. *(planned)* |
| [EXCEL] | `Application.WorksheetFunction.NormSDist` | `scipy.stats.norm.cdf` | Same function. *(planned)* |

---

## Practical D — Tenor Dates

| Tag | Book | Here | Why |
|---|---|---|---|
| [FIX] | Invalid tenor pops a `MsgBox` and returns `−1` | Raises a specific exception | A sentinel return that is also a valid-looking number is a bug waiting to happen. The book's own Practical E code then has to test for it. *(planned)* |
| [EXCEL] | Dates as `Long` (Excel serial numbers) | `datetime.date` | Excel stores dates as integers from 1900; Python does not need to. *(planned)* |
| [SCOPE] | Chapter 10 describes end-end and month-overflow delivery-date conventions; Practical D explicitly ignores them | Marked as documented `TODO`s in `dates.py`, with the Chapter 10 rules written out | Matching the practical's scope, but the reader should know exactly what is missing and what the real rule is. *(planned)* |
| [SCOPE] | No holiday calendar (weekends only) | Same, but the business-day functions take an injectable calendar | The practical's simplification, kept — with the seam left open so it can be fixed without reworking call sites. *(planned)* |
| [SCOPE] | T+2 settlement assumed throughout | Same, parameterised | Chapter 10 notes T+1 pairs (USD/CAD, USD/TRY) and the USD-clearing rule. Neither is implemented. *(planned)* |
| [CONVENTION] | Week tenors are added to the horizon with no business-day adjustment, so `horizon + 7n` could in principle land on a weekend | Implemented as the book has it; Chapter 10's rule (such a tenor is invalid) is noted in the docstring | The practical's code and Chapter 10's prose differ slightly here. Following the code, documenting the prose. *(planned)* |

---

## Practical E — ATM Curve

| Tag | Book | Here | Why |
|---|---|---|---|
| [FIX] | `getATMVol` returns `−1` for query dates outside the tenor range | Raises an explicit exception | Same reasoning as Practical D. A `−1` volatility will propagate silently into a variance and produce something that looks like a number. *(planned)* |
| [FIX] | The printed `LinearVolatilityInterpolation` function assigns to `LinearVarianceInterpolation` — the wrong name | Two separate, correctly named functions | Transcription error in the book. *(planned)* |
| [EXCEL] | Subroutines push values onto sheet ranges (`populateATMImpliedVolatilities`, `populateVariance`, `populateDayWeights`) | Functions returning DataFrames | The sheet is the book's data structure; a DataFrame is ours. *(planned)* |
| [EXCEL] | `Weekday()` used as an offset into the day-weight lookup table | A weekday-keyed mapping | The book calls the offset trick "cunning", which is Excel for "fragile". *(planned)* |
| [CONVENTION] | Day-count is 365 throughout | Same | The book uses `/365` everywhere without discussing ACT/365 versus ACT/360 or business-day counts. Kept as-is; noted because it is a real convention choice. *(planned)* |
| — | Task B fits the model to market tenors visually | Adds a least-squares calibration reporting fit error | Explicitly beyond the book, as requested. Additive, not a replacement. *(planned)* |
| — | Weekend weights set to exactly zero | Same for the staged demonstration, but the chapter's note that desks use a small non-zero weekend weight is carried into the notebook | Chapter 11 flags it; the practical simplifies it. Both are worth knowing. *(planned)* |

---

## Practical F — Volatility Smile

| Tag | Book | Here | Why |
|---|---|---|---|
| [EXCEL] | 0% and 100% delta replaced with 0.01% and 99.99% to keep the strike finite | Same | Not an Excel artefact — the strike genuinely diverges. Kept and explained. *(planned)* |
| [SCOPE] | Malz smile on outright deltas | Same | Chapter 12 explains at length that the interbank market trades the **broker fly**, whose strikes are not the outright strikes and which carries vanna when valued on the smile. Practical F does not implement it, and neither do we. This is the single largest simplification in the vol surface and is stated in `smile.py`, `surface.py` and the notebook. *(planned)* |
| [SCOPE] | Spot delta throughout | Same | Chapter 12 notes that long-dated G10 and EM risk reversals are usually quoted on forward delta, and Chapter 8 notes premium-adjusted delta in CCY1-premium pairs. Neither is implemented; both are flagged. *(planned)* |
| — | Malz gives a 25d/10d risk reversal multiplier of 1.6 | Same, with the discrepancy stated | Chapter 12 says the market value is usually around 1.8, so the model understates 10d skew. A limitation of the parameterisation, not of the implementation. *(planned)* |

---

## Assembled volatility surface (`surface.py`)

Not in the book at all — the book builds the ATM curve and the smile separately and never
joins them. Simplifications it carries are listed in the module's `SIMPLIFICATIONS`
constant and repeated in `notes/source_notes.md`. *(planned)*

---

## Repository-wide

| Tag | Note |
|---|---|
| [CONVENTION] | Volatilities are decimals internally (0.085, not 8.5). Conversion happens at the market data provider boundary and nowhere else. There is a test that fails if any provider returns a volatility above 1.0. *(planned)* |
| [CONVENTION] | Rates are continuously compounded everywhere, per Chapter 5 and Chapter 10. No curve building, no basis, no credit — the book sets all three aside explicitly in its Preface and so do we. |
| [SCOPE] | Practical G onwards (Chapter 13+) is out of scope for this pass. |
