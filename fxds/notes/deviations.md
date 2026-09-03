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
| [EXCEL] | `Application.OnTime` schedules the next tick | `Simulator.step()` is called by whatever supplies the clock — Streamlit's `st.rerun()` after a sleep, or a `for` loop in a test | Excel has no other way to get a repeating timer out of VBA. Separating the clock from the model is what makes the batch experiment and the tests possible at all. **Implemented.** |
| [EXCEL] | Named cells (`Range("SpotMidMarket")`) as the data model | Typed attributes on dataclasses (`Market`, `Trader`, `MarketParticipants`) | Named ranges are Excel's substitute for variables. The book is explicit that naming beats cell references; in Python that is just an object. **Implemented.** |
| [EXCEL] | Go/Pause and Stop buttons from Form Controls; grouped option buttons for the trader action | Streamlit buttons over `st.session_state`; Buy/Sell buttons that reset after one tick, as the book's VBA does | Same intent, different widget toolkit. **Implemented.** |
| [EXCEL] | Chart pre-selected over ~500 mostly blank rows so it auto-resizes | Plotly figure redrawn from the recorded history each rerun | The blank-row trick is a workaround for Excel charts not growing with data. **Implemented.** |
| [EXCEL] | `Rnd()` for randomness | `numpy.random.Generator`, seedable | Reproducibility. The book's simulator cannot be replayed; ours can, which is what makes it testable. **Implemented**, with three independent generators per session — see the next row. |

| — | The book has one source of randomness | Three independent generators per session: market path, participant flow, and strategy | Without this the passive-versus-over-trading comparison is worthless: a strategy drawing from the market's generator would consume numbers and change the spot path, so the two strategies would face different markets. Splitting them makes it a genuine paired comparison, and `test_strategy_randomness_does_not_disturb_the_market_path` asserts it. |
| — | Not in the book | `engine.py`, holding the coordinating `Simulator` | The build spec named `market.py`, `trader.py` and `app.py`. The class that ties market and trader together has to live somewhere, and putting it in either of the first two would make one import the other. Re-exported from `fxds.simulator`, so the import path is unaffected. |
| [CONVENTION] | The book does not say whether a position limit should block price-making flow | It does not — only price *taking* is blocked | A price maker cannot decline a trade that has already happened. Watching an unwanted position build past the limit is precisely the risk Chapter 3 describes in its third scenario, so preventing it would remove the lesson. Stated in `Trader.make_price`'s docstring and asserted in `test_position_limit_does_not_block_price_making`. |
| [CONVENTION] | "Evolve the spot rate using a volatility-based approach, see Practical H for details" | Standard GBM discretisation, zero drift | Practical H is out of scope for this pass, so the reference could not be followed. The implemented form is the standard one and is stated in `SpotProcess.VOLATILITY`'s docstring. |

---

## Practical B — Numerical Integration Pricer

| Tag | Book | Here | Why |
|---|---|---|---|
| [EXCEL] | 101 rows on a sheet from −5 to +5 standard deviations | A numpy array over the same grid, returned as a DataFrame | Same numbers, same row alignment (a row's probability bounds the bucket running to the *next* row). Vectorised where it does not obscure the formula. **Implemented.** |
| [CONVENTION] | Test 2 gives `S = K = 100`, `r1 = r2 = 0`, `T = 1.0` and expects "very slightly under 4.00 CCY1%" but does not state σ in the text | σ = 10% | The closed-form ATM value `0.3989·σ·√T` gives 3.99% at σ = 10%, which is what "very slightly under 4.00" describes. Consistent with the σ used in Practical C's test. **Implemented**: `tests/test_numerical.py` asserts 3.9969%, and the integration agrees with the closed form to 2.3e-3 relative on the book's own grid. |

---

## Practical C — Black-Scholes Pricer

| Tag | Book | Here | Why |
|---|---|---|---|
| [FIX] | The printed VBA guard reads `If (T >= 0) Then T = 0.0000000001` (and likewise for volatility) | `if T <= 0: T = 1e-10` | As printed the guard fires on every valid input and destroys the price. The surrounding prose says the intent plainly: clamp non-positive time and volatility to a small positive value so the formula returns the payoff at maturity. Implemented per the prose. **Regression test**: `TestExpiryAndVolGuards::test_guard_does_not_fire_on_valid_inputs` fails if the comparison is ever inverted back. |
| [EXCEL] | Task B exists to move the calculation from cell formulas into a VBA function | The module function is the only implementation | In Python there is no cell-formula stage to graduate from. The task's actual content — the input signature, the guard, the structure — is implemented. **Implemented.** |
| [EXCEL] | `Application.WorksheetFunction.NormSDist` | `scipy.stats.norm.cdf` | Same function. `NORMDIST(x,0,1,FALSE)` for the density becomes `norm.pdf`. **Implemented.** |

| — | Practical C asks only for delta and vega | Gamma added as a closed form too | Task D asks you to notice that the gradient of the delta-versus-spot chart *is* gamma. Having gamma available makes that claim checkable rather than assertable, and `tests/test_blackscholes.py` verifies the two agree numerically. Additive; nothing from the practical is displaced. |
| — | The book suggests testing flex sizes by hand | A bump-size sweep with the error curve plotted | Practical C, Task C asks what happens as the flex grows and shrinks. Turning that into a measured U-shaped curve — truncation error on one side, floating-point cancellation on the other — makes the answer concrete. Notebook 05 plots it; `test_bump_size_sweep_degrades_at_both_extremes` asserts it. |
| [CONVENTION] | The book does not give a general rule for which currency pays the premium; it gives examples (EUR/USD is CCY2, EUR/JPY and USD/JPY are CCY1) | `CurrencyPair.premium_side` returns CCY1 when CCY2 is JPY, else CCY2 | Reproduces every example the book gives, but it is an inference from three data points, not a stated rule — and in practice the premium currency is agreed per trade. Flagged in the property's own docstring; override explicitly when it matters. |

---

## Practical D — Tenor Dates

| Tag | Book | Here | Why |
|---|---|---|---|
| [FIX] | Invalid tenor pops a `MsgBox` and returns `−1` | Raises `InvalidTenorError` | A sentinel return that is also a valid-looking date serial is a bug waiting to happen. The book's own Practical E code then has to test for it. **Implemented.** |
| [EXCEL] | Dates as `Long` (Excel serial numbers) | `datetime.date` | Excel stores dates as integers from 1900; Python does not need to. **Implemented.** |
| [SCOPE] | Chapter 10 describes end-end and month-overflow delivery-date conventions; Practical D explicitly ignores them | Documented `TODO`s in `dates.py` with the Chapter 10 rules written out, and demonstrated in notebook 09 | Matching the practical's scope. Worth noting `relativedelta` happens to agree with the month-overflow convention by arithmetic accident (it clamps 30 Jan + 1M to 28 Feb) but does **not** implement end-end. Code that accidentally agrees with a convention diverges the moment inputs change. **Implemented as documented gaps.** |
| [SCOPE] | No holiday calendar (weekends only) | Same, but every function takes an injectable `HolidayCalendar` callable | The practical's simplification, kept with the seam open. Notebook 09 measures what a calendar changes: expiries move too, not just deliveries, because month expiries are derived *backwards* from delivery through business-day stepping. **Implemented.** |
| [SCOPE] | T+2 settlement assumed throughout | Same, but `lag` is a parameter on every function | Chapter 10 notes T+1 pairs (USD/CAD, USD/TRY) and the USD-clearing rule (nothing settles on a US holiday even in non-USD pairs). The lag is parameterised; the USD-clearing rule is not implemented. |
| [CONVENTION] | Week tenors are added to the horizon with no business-day adjustment, so `horizon + 7n` can land on a weekend | Follows the practical's code; Chapter 10's stricter rule is exposed separately as `validate_day_week_expiry` | **The book contradicts itself here** — Chapter 10's prose says such a tenor is invalid, Practical D's VBA does no check. Following the code and making the prose rule available, rather than silently picking one. **Implemented.** |

---

## Practical E — ATM Curve

| Tag | Book | Here | Why |
|---|---|---|---|
| [FIX] | `getATMVol` returns `−1` for query dates outside the tenor range | Raises `CurveRangeError` | Same reasoning as Practical D. A `−1` volatility will propagate silently into a variance and produce something that looks like a number. **Implemented.** |
| [FIX] | The printed `LinearVolatilityInterpolation` function assigns to `LinearVarianceInterpolation` — the wrong name | Two separate, correctly named functions | Transcription error in the book — as printed the function returns nothing useful. **Implemented.** |
| [EXCEL] | Subroutines push values onto sheet ranges (`populateATMImpliedVolatilities`, `populateVariance`, `populateDayWeights`) | Functions returning DataFrames | The sheet is the book's data structure; a DataFrame is ours. **Implemented.** |
| [EXCEL] | `Weekday()` used as an offset into the day-weight lookup table | A weekday-keyed dict, plus per-date overrides for events and holidays | The book calls the offset trick "cunning", which is Excel for "fragile". **Implemented.** |
| [CONVENTION] | Day-count is 365 throughout | Same, as the module constant `DAYS_PER_YEAR` | The book uses `/365` everywhere without discussing ACT/365 versus ACT/360 or business-day counts. Kept as-is; noted because it is a real convention choice, not a neutral default. |
| — | Task B fits the model to market tenors visually | Adds a `calibrate_parametric` least-squares fit reporting RMSE and max error | Explicitly beyond the book. The per-tenor residual **is** the manual override Chapter 11 describes a trader inputting, computed rather than eyeballed. Additive; the manual path still works. **Implemented.** |
| — | Weekend weights set to exactly zero | Same for the staged demonstration; `WEEKEND_ZERO_WEIGHTS`' docstring and notebook 10 both carry Chapter 11's note that desks use a small non-zero weight because weekend news can gap spot on the Monday open | Chapter 11 flags it; the practical simplifies it. **Implemented.** |

---

## Practical F — Volatility Smile

| Tag | Book | Here | Why |
|---|---|---|---|
| [EXCEL] | 0% and 100% delta replaced with 0.01% and 99.99% to keep the strike finite | Same, as `DELTA_FLOOR` and `DELTA_CAP` | Not an Excel artefact — the strike genuinely diverges. **Implemented**, and see the attainability row below for a tighter bound the book never surfaces. |
| [SCOPE] | Malz smile on outright deltas | Same | Chapter 12 explains at length that the interbank market trades the **broker fly**, whose strikes are generated ignoring the risk reversal and so are not the outright strikes, and which carries vanna when valued on the smile. Chapter 12's 5yr AUD/JPY example has the outright 25d put at 46.05 against the broker fly's 49.60 — not a rounding difference. Practical F does not implement it and neither do we. **The single largest simplification in the surface**, stated first in `surface.SIMPLIFICATIONS`, in `smile.py`'s module docstring, and in notebook 11. |
| [SCOPE] | Spot delta throughout | Same | Chapter 12 notes long-dated G10 and EM risk reversals are usually quoted on forward delta; Chapter 8 notes premium-adjusted delta in CCY1-premium pairs moves the zero-delta straddle strike to the other side of the forward. Neither implemented; both flagged in `surface.SIMPLIFICATIONS`. |
| — | Malz gives a 25d/10d risk reversal multiplier of 1.6 | Same, exposed as `MalzSmile.rr10_implied` with the discrepancy in its docstring | Chapter 12 says the market value is usually around 1.8, so the model understates 10d skew. A limitation of the parameterisation, not of the implementation. **Implemented and asserted in tests.** |

| — | Not in the book | `max_attainable_put_delta(r_ccy1, T)` | Since `delta_put = exp(-r1*T)*[N(d1)-1]` and the bracket lies in `(-1, 0)`, the signed put delta is bounded by `-exp(-r1*T)`. **With a 10% CCY1 rate over a year there is no such thing as a 95 delta put.** The book's examples use modest rates and never reach the bound, so it is never mentioned. `strike_placement` omits unattainable deltas rather than raising; `smile_by_strike` clips its sweep. |
| — | The book states flatly that a higher CCY1 rate moves "the whole volatility smile lower" | True for the body of the smile; **reverses in the deep wing** near the attainability bound | As the CCY1 rate rises, `exp(r1*T)*delta + 1` collapses toward zero and the inverse normal dives, pushing the strike *out* faster than the lower forward pulls it *in*. Both behaviours are asserted in `tests/test_smile.py` rather than the inconvenient one being hidden. The book's claim is correct for the deltas its own examples use. |

---

## Assembled volatility surface (`surface.py`)

Not in the book at all — the book builds the ATM curve and the smile separately and never
joins them. Eight simplifications are listed in the module's `SIMPLIFICATIONS` constant,
printed by `explain_simplifications()`, and repeated in `notes/source_notes.md`.

Two composition choices worth calling out specifically, because the book gives no guidance
on either:

| Tag | Choice | Why |
|---|---|---|
| [CONVENTION] | Day weights compose **multiplicatively** with the interpolated core curve: the tenor ATM is scaled by the weighted-to-flat volatility ratio at that date | Chapter 11 says desks combine a core curve with weights on top but does not say how. This form keeps the quoted tenor levels roughly intact while letting the weights shape the days between. A different desk would do it differently. |
| [CONVENTION] | Smile parameters (RR and fly) interpolate **linearly in time** between tenors, held flat beyond the ends | Chapter 12 explicitly declines to pick a method, noting desks interpolate in delta, strike or model-parameter terms. Linear-in-time is the simplest defensible choice and is stated as such. |
| — | `volatility(expiry, strike)` solves by fixed-point iteration | This direction genuinely *is* circular (unlike strike-from-delta, which is not — see `strike_placement`'s docstring). The test asserts the fixed point is self-consistent, not merely that the loop terminates. |
| — | Non-negative forward variance is **checked**, not guaranteed | Chapter 11 notes real desks construct curves so the guarantee holds structurally. Notebook 10, Experiment 7 shows the day-weight layer *cannot* create the arbitrage — only the interpolation can — so the check targets the right place. |

---

## Repository-wide

| Tag | Note |
|---|---|
| [CONVENTION] | Volatilities are decimals internally (0.085, not 8.5). Conversion happens at the market data provider boundary and nowhere else. There is a test that fails if any provider returns a volatility above 1.0. *(planned)* |
| [CONVENTION] | Rates are continuously compounded everywhere, per Chapter 5 and Chapter 10. No curve building, no basis, no credit — the book sets all three aside explicitly in its Preface and so do we. |
| [SCOPE] | Practical G onwards (Chapter 13+) is out of scope for this pass. |
| — | **Cross-validation tolerances are measured, not guessed.** Practical B's integration agrees with Practical C's closed form to 2.3e-3 relative on the book's own grid (0.1 sd steps) and 5.7e-6 at 0.01 steps. The residual is trapezoidal discretisation error, and it converges second-order — halving the step cuts it roughly fourfold. `tests/test_cross_validation.py` asserts the convergence as well as the agreement, so a genuine regression cannot hide behind a loose tolerance. |
| — | **The forward payoff is checked in absolute terms, not relative.** A forward's value is a small difference of two large numbers, so relative error against it overstates disagreement by roughly the ratio between them. Same reason Practical B's Test 1 can only be stated as "approximately zero". |
| — | Doctests in the package run as part of the default `pytest` invocation (`addopts = "--doctest-modules"`), so the book's acceptance values embedded in docstrings fail loudly if they ever drift. |
