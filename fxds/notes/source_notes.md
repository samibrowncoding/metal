# Source notes — *FX Derivatives Trader School*, Giles Jewitt (Wiley, 2015)

Working spec for the `fxds` package. Covers **Chapters 1–12** and **Practicals A–F**
(the first half of the book). Practical G and Chapter 13 onwards are explicitly out of
scope for this pass.

**How to read this file.** Everything here is my own paraphrase of the book's concepts,
written as a build specification. Mathematical formulas are reproduced because they are
standard results (Garman–Kohlhagen, Malz, the variance identities) and are the same in any
textbook. No VBA source and no extended prose from the book is copied. Where I need to
point at the book I cite it by chapter and practical number, e.g. "see Practical C, Task C".
Read the book alongside this; these notes are a spec, not a substitute.

**Notation used throughout.**

| Symbol | Meaning |
|---|---|
| `S` | spot rate, CCY2 per CCY1 |
| `K` | strike, CCY2 per CCY1 |
| `F_T` | forward outright to time `T` |
| `T` | time to expiry in years |
| `r1`, `r2` | continuously compounded interest rates in CCY1 and CCY2 (book: `rCCY1`, `rCCY2`) |
| `σ` | implied volatility of spot log returns, as a decimal (0.10 = 10%) |
| `N(x)` | cumulative standard normal distribution |
| `n(x)` | standard normal probability density |
| `N⁻¹(x)` | inverse cumulative standard normal |

---

## Part I — The Basics

### Chapter 1 — Introduction to Foreign Exchange

**Currency pair notation.** Pairs are written CCY1/CCY2. The rate is *the number of CCY2
it costs to buy one CCY1*. EUR/USD at 1.3105 means one euro costs 1.3105 dollars. Rate up
⇒ CCY1 stronger. Rate down ⇒ CCY1 weaker.

This one convention drives almost every sign and unit decision downstream. Implement it in
`conventions.py` and never re-derive it inline.

**Spot date.** Cash settles on the spot date, normally T+2 business days after the trade
date. Some pairs (USD/CAD, USD/TRY) are T+1.

**Pips.** The smallest normally quoted increment of the rate. EUR/USD quotes to four
decimals ⇒ pip = 0.0001. USD/JPY quotes to two decimals ⇒ pip = 0.01. Pip size is a
per-pair property, not a constant. A **big figure** is 100 pips.

**Forwards and swap points.** A forward exchanges cash on a date other than the spot date.
`swap points = F_T − S`. Quoted as a number of pips. Spot and forwards are linked by the two
interest rates via no-arbitrage (Chapter 5).

**Position language.** Long/short always refers to the **CCY1** position. "Long ten
dollar-cad" = bought USD10m against CAD.

**P&L formulas** (needed for the simulator, Practical A):

```
P&L_CCY2 = Notional_CCY1 · (S_T − S_0)          # linear in spot
P&L_CCY1 = Notional_CCY1 · (S_T − S_0) / S_T    # curved, because the CCY2 P&L is
                                                # converted back at the prevailing rate
```

Short positions carry a negative notional. The CCY1 version is curved: an amount of CCY2 is
worth relatively more CCY1 at lower spot. This curvature is a real teaching point — the
"linear" spot P&L is only linear in the currency it is naturally generated in.

**Quote-convention ordering** for G10: EUR > GBP > AUD > NZD > USD > CAD > CHF > NOK > SEK > JPY.
The pair is quoted with whichever currency comes first in that list as CCY1. There are
exceptions (some UK corporates trade GBP/EUR), so this is a default, not a law.

### Chapter 2 — Introduction to FX Derivatives

**Vanilla options.** A call is the right to buy CCY1 (sell CCY2) at the strike; a put is
the right to sell CCY1 (buy CCY2). A single FX option is *simultaneously* a call on one
currency and a put on the other — a "EUR/USD call" means EUR call / USD put. Only the
CCY1 direction is normally spoken.

**European vs American.** European = exercisable only at maturity. That is the FX market
standard and the only kind in scope here.

**Payoffs, in CCY2 pips per one CCY1:**

```
call payoff = max(S_T − K, 0)
put  payoff = max(K − S_T, 0)
```

**Contract details required:** currency pair, call/put, expiry date, **cut** (the exact
time of day the option matures — NY cut is 10am New York, TOK cut is 3pm Tokyo), strike,
notional (normally CCY1).

**Notional conversion:** `Notional_CCY2 = Notional_CCY1 · K`. The strike is the level at
which the two currencies are potentially exchanged, so the strike is the correct conversion
rate — *not* spot.

**ITM/OTM.** For a call, ITM is above the strike. For a put with all else equal, the ITM
and OTM sides flip.

**Delivery date** is derived from the expiry date exactly as the spot date is derived from
the horizon. That symmetry is the whole basis of the month/year tenor rules in Practical D.

**Volatility vs premium.** The market quotes vanillas in *implied volatility* terms and
uses Black-Scholes purely as the translation layer into a cash premium. This is the single
most important framing in the book: Black-Scholes is a quoting convention here, not a
belief about the world.

### Chapter 3 — Introduction to Trading → **Practical A**

**Bid and offer.** Bid = the rate a price maker will buy at. Offer (ask) = the rate they
will sell at. A **price taker** must buy at the offer and sell at the bid; a **price
maker** buys at their own bid and sells at their own offer.

Consequence, and the core lesson of Practical A: *the price taker pays half the spread on
every trade, in both directions.* Every price-taker trade has an immediate negative P&L
impact. The price maker earns that half spread but does not choose their resulting
position.

**Bid–offer spread** is a function of contract volatility and expected holding period
until an offsetting trade arrives. Wider spread ⇒ less likely to trade, more protection.

**Order types.** Take-profit order = sells above / buys below the current market. Stop-loss
order = buys above / sells below.

**Risk limits and P&L targets should be in line.** Greater risk gives the opportunity for
greater reward but guarantees only greater P&L volatility. This motivates the risk-limit
extension in Practical A.

---

## Practical A — Building a Trading Simulator (Ch. 3)

Excel/VBA original driven by `Application.OnTime` and Form Control buttons. In Python:
a headless `Simulator` class that can be stepped, plus a Streamlit front end. See
`notes/deviations.md` for the Excel-only mechanics and what replaces them.

### Task A — ticking mid-market spot
Inputs: initial spot, time between ticks, spot increment.
Outputs: current step, current mid.
Each tick: with probability ½ move mid up by `spot_increment`, else down by the same.
Increment the step counter. Record the path; chart it live.

### Task B — two-way price and price taking
Add `bid_offer_spread` as an input:

```
bid   = mid − bid_offer_spread / 2
offer = mid + bid_offer_spread / 2
```

Trader action each tick is one of {do nothing, buy at offer, sell at bid}.

**Ordering within a tick matters and must be reproduced exactly** (Practical A, Task B):

1. Record the current step, mid, position and P&L.
2. Draw the spot increment (±`spot_increment`).
3. `pnl += position · spot_increment` — mark the *existing* position to the new spot.
4. `mid += spot_increment`; `step += 1`.
5. Recompute bid and offer.
6. Process the trader action: buy ⇒ `position += 1`, `pnl −= spread/2`;
   sell ⇒ `position −= 1`, `pnl −= spread/2`.
7. Reset the action to "do nothing".

Note step 6: **both** buying and selling cost half the spread. That is the point.

Charts: spot, position, P&L.

### Task C — price making
Add `market_buy_prob` and `market_sell_prob`. Draw one uniform `u` per tick:

- `u < market_buy_prob` → the market buys from the trader: `position −= 1`, `pnl += spread/2`.
- `market_buy_prob ≤ u < market_buy_prob + market_sell_prob` → the market sells to the
  trader: `position += 1`, `pnl += spread/2`.
- otherwise no market trade.

Sign convention to get right: *the market buying makes the trader shorter*, and the trader
**earns** half the spread. This is the mirror image of Task B.

With roughly symmetric probabilities the theoretically correct behaviour is to sit and wait
for offsetting flow, reducing the position only when it gets large enough that P&L swings
are uncomfortable.

### Extensions (the book lists these; all are in scope)
- Risk limits and P&L targets — start aligned, then deliberately misalign them and observe.
- Volatility-based spot evolution instead of a fixed increment.
- Market participants whose direction depends on where spot has moved (e.g. more likely to
  buy after spot falls). If the trader knows the rule, managing the flow gets easier.
- Variable trade notionals — in practice larger size trades further from mid.
- (Most complex, book flags it as such) the trader manually making prices with fill
  probability depending on where their price sits versus the market. Implemented as the
  optional price-making mode.

### Teaching experiment to add (beyond the book)
Run 1,000 headless sessions for a passive strategy vs an over-trading strategy and plot the
two P&L distributions. This makes the "don't over-trade when there is spread cross" lesson
quantitative rather than anecdotal.

---

### Chapter 4 — FX Derivatives Market Structure

Conceptual chapter, no practical. Needed for notebook 03.

- The FX derivatives market is **OTC** — no central exchange, and a clear bank/client
  distinction. Contracts are not standardised; that flexibility is the point.
- Client types: corporates (hedging real FX exposure), institutional (real money, hedge
  funds, sovereigns), regional banks, retail (e.g. dual currency deposits, where the client
  has effectively sold a call and receives an enhanced coupon).
- Desk roles: traders, structurers, quants, middle office.
- Bank-to-bank trading happens via the **interbank broker market** (most volume) or
  **direct calls**.
- Broker market mechanics: a trader gives their broker an *interest*; brokers canvass the
  market; the best composite two-way rate comes back; the interest counters; the
  negotiation narrows; the rate may be *shown out* to the whole market; a trade *prints*.
  Market size in major G10 is roughly USD30–50m.
- Vanillas are dealt in volatility terms; spot, forward and deposit rate are agreed
  afterwards and Black-Scholes converts to premium.
- Convention within direct calls: notional in CCY1; if no year is given, the next occurrence
  of the date; the **out-of-the-money side is always dealt**.

### Chapter 5 — The Black-Scholes Framework → **Practicals B and C**

**The SDE.** Spot follows geometric Brownian motion:

```
dS_t / S_t = (r2 − r1) dt + σ dW_t
```

Relative (not absolute) changes, so spot can never reach zero. Two parts: deterministic
**drift** from the rate differential, and **uncertainty** from the volatility term.

`r1` is sometimes called the foreign rate and `r2` the domestic rate, because P&L on
standard FX contracts is naturally generated in CCY2.

**Drift ⇒ the forward.** With `σ = 0`:

```
F_T = S · e^((r2 − r1)·T)
```

Zero volatility does **not** mean spot is static — it means spot follows the forward path
exactly. Worth stating explicitly in the notebook; it is a common misreading.

- `r1 = r2` ⇒ forward equals spot.
- `r2 > r1` ⇒ positive drift, forward above spot.
- `r1 > r2` ⇒ negative drift, forward below spot.

**Solving the SDE** (Itō):

```
ln(S_T / S_0) = (r2 − r1 − σ²/2)·T + σ·W_T
```

Two things to carry forward: we are in **log space**, and the drift picks up the Itō
correction `−σ²/2`. The random term `σ·W_T` is normal with mean 0 and standard deviation
`σ√T`.

Because variance scales with `T` and volatility with `√T`, multiplying time to expiry by
four does the same thing to the distribution as doubling volatility.

**Log-normality.** Log returns are normally distributed, so spot itself is log-normal:
longer right tail in spot space, never negative. A move 1.0 → 0.5 is equal and opposite to
1.0 → 2.0 in log terms. Only visible at high volatility or long maturity; at 1mth and 8%
the distribution looks like a plain bell curve.

**Pricing by integration.** For any payoff depending only on `S_T`, the value is the
payoff integrated against the terminal spot distribution. This is Practical B.

**The Garman–Kohlhagen formula** (the FX extension of Black-Scholes), in CCY2 pips:

```
call = S·e^(−r1·T)·N(d1) − K·e^(−r2·T)·N(d2)
put  = K·e^(−r2·T)·N(−d2) − S·e^(−r1·T)·N(−d1)

d1 = [ln(S/K) + (r2 − r1 + σ²/2)·T] / (σ√T)
d2 = d1 − σ√T
```

The derivation assumes continuous costless delta hedging, which removes every risk except
volatility. The assumptions do not hold in practice; that is not a day-to-day concern
because the formula's job here is translation between volatility and premium.

---

## Practical B — Numerical Integration Option Pricer (Ch. 5)

### Task A — build the terminal spot distribution

Inputs: `S`, `r1`, `r2`, `T`, `σ`.

```
μ  = (r2 − r1 − σ²/2)·T          # expected log return
sd = σ·√T                        # standard deviation of the log return
```

For each `X` in −5.0 … +5.0 stepping by 0.1 (101 points):

```
return_level = μ + X·sd
spot_level   = S · e^(return_level)
```

**Bucket probability** is the difference of two cumulative normals. Row `i` holds the
probability that spot ends between `spot_level[i]` and `spot_level[i+1]`:

```
prob[i] = N(X[i+1]) − N(X[i])
```

The row alignment matters and is easy to get wrong: the probability on a row belongs to the
interval running to the *next* row. The last row has no bucket.

Plot density against spot. Expected behaviour to verify:

- shorter maturity or lower vol ⇒ tighter distribution
- longer maturity or higher vol ⇒ wider distribution
- higher `r2` or lower `r1` ⇒ distribution shifts higher (forward higher)
- higher `r1` or lower `r2` ⇒ distribution shifts lower

### Task B — payoff column and the integration

Payoffs at each terminal spot level, all in **CCY2 pips**:

```
long forward  : S_T − K
short forward : K − S_T
vanilla call  : max(S_T − K, 0)
vanilla put   : max(K − S_T, 0)
```

Integration: for each bucket, multiply the bucket probability by the **average payoff
across the bucket** (the mean of the payoff at the two bounding spot levels), then sum.

Then present value and convert units:

```
value_ccy2_pips = e^(−r2·T) · Σ_i prob[i] · (payoff[i] + payoff[i+1]) / 2
value_ccy1_pct  = value_ccy2_pips / S
```

### Acceptance tests (Practical B, Testing)
1. A forward payoff struck at the forward prices to approximately zero.
2. A vanilla call with `S = K = 100`, `r1 = r2 = 0%`, `T = 1.0` prices very slightly under
   **4.00 CCY1%**. (The book's screenshot uses σ = 10%; the closed-form ATM value is
   `0.3989·σ·√T ≈ 3.99%`, which is the "very slightly under 4.00" being described.)

### Interactive requirement
Sliders for vol and time so the distribution can be watched widening, and for the rate
differential so it can be watched shifting. The payoff overlaid on the density chart is the
single picture the whole practical exists to produce.

---

## Practical C — Black-Scholes Option Pricer (Ch. 5–6)

### Task A — pricer

Step 1: forward, `F_T = S·e^((r2 − r1)·T)`. Check what happens when `r1 = r2`.

Step 2: Garman–Kohlhagen as above, in CCY2 pips.

**Acceptance test** (Practical C, Task A, Step 2): `S = K = 1.0`, `T = 1.0`, `σ = 10%`,
`r1 = r2 = 0%` ⇒ price **0.0399 pips**, described as "very slightly under 0.04".

Parameter-flex checks the book asks for:
- Example 1 — raise the strike on a 100.00 call: call cheapens (payoff moved further from
  the forward), put richens.
- Example 2 — raise vol or `T` on a 1.2500 strike: **both** call and put richen, because the
  distribution widens and brings bigger payoffs into play.
- Example 3 — raise `r1` and `r2` together to the same level: forward unchanged, but both
  call and put cheapen due to increased discounting.

Step 3: notional handling and premium conversions:

```
CCY2 cash = CCY2 pips · Notional_CCY1
CCY1 cash = CCY2 cash / S
```

Step 4: **put–call parity**. The book states it as `call − put = F − K`, then immediately
shows the subtlety: option prices are present valued while the `(F − K)` difference is
realised in the future. So the correct relation is

```
call − put = e^(−r2·T) · (F − K)
```

The undiscounted version only works when `r2 = 0` or `K = F`. Show the failure explicitly
and explain why — this is the point of the task, not a footnote.

### Task B — pricing function
The Excel-original point was moving from cell formulas to a VBA function. In Python this is
just the module function. Keep the guard the book asks for: clamp `T ≤ 0` and `σ ≤ 0` to a
tiny positive value (the book suggests 1e-10) so the formula returns the payoff at maturity
rather than raising. **Note:** the book's printed VBA has `If (T >= 0) Then T = ...`, which
is a typo for `<=`; implemented correctly here and recorded in `notes/deviations.md`.

### Task C — first-order greeks, two ways

Closed form:

```
Δ_call = e^(−r1·T)·N(d1)
Δ_put  = e^(−r1·T)·[N(d1) − 1]
vega   = S·e^(−r1·T)·n(d1)·√T          # same for call and put
```

Finite difference: bump the parameter up and down, take the central difference:

```
Δ  ≈ [P(S + h) − P(S − h)] / (2h)
ν  ≈ [P(σ + h) − P(σ − h)] / (2h)
```

**Market quote conventions** (Practical C, Task C):
- Delta quoted as a % of CCY1 notional.
- Vega quoted in CCY1 terms (divide by spot) **and** per 1% vol move (divide by 100).
  So `vega_market = 0.01 · vega_raw / S`.

**Acceptance test:** same inputs as Task A (`S = K = 1.0`, `T = 1.0`, `σ = 10%`, zero rates)
⇒ delta close to **50%**, vega **a shade under 0.40%**.

Book suggests starting with a 1e-6 flex and testing what happens as the flex grows and
shrinks. Beyond the book: sweep the bump size and plot the error, showing truncation error
at large bumps and floating-point noise at small ones.

### Task D — plot exposures
- Delta vs spot (its gradient is gamma); try extreme `r1`/`r2`.
- Vega vs spot; note where the peak sits; try extreme rates.
- Vega vs time to expiry; confirm the `√T` relationship from the formula.
- Option value vs volatility, for near-the-money vs far strikes.
- Beyond the book: 3D surfaces (value / delta / vega over spot × time).

---

### Chapter 6 — Vanilla FX Derivatives Greeks

Stylized analysis: zero rates throughout, so forward = spot and discounting drops out.

**Option value = intrinsic value + time value.** Intrinsic is the payoff at maturity; time
value is what the remaining optionality is worth. Time value is maximised when the forward
equals the strike, and decays to zero away from the strike on both sides because there is
little chance of crossing it.

**Delta** `Δ = ∂P/∂S`. Quoted as % of notional or as cash (`Δ_cash = Δ% × notional`).
Delta is the spot notional that must be traded in the opposite direction to be delta
neutral. At maturity delta is a step from 0% to 100% at the strike; before maturity the
transition is smooth and wider. Delta ≈ the probability of finishing ITM. Calls have
positive delta, puts negative.

Market shorthand: a "twenty-five delta call" has 25% delta; a "ten delta put" has −10% delta
and the minus sign is dropped in speech. **This sign convention is a standing trap** and
must be called out in the notebooks and in `smile.py`.

**Put–call parity in greek terms.** The call and put delta profiles are identical up to a
100% shift: `Δ_put = Δ_call − 1` (times the discount factor). So a call becomes a put by
selling the forward in the same strike, maturity and notional. Consequences:
- Delta hedged calls and puts with the same strike and maturity have **identical** greeks.
  Traders therefore talk about strikes and notionals, not calls and puts.
- Same strike and maturity must be valued at the **same implied volatility** or the forward
  is an arbitrage.

**Gamma** `Γ = ∂Δ/∂S = ∂²P/∂S²`. Long options are always long gamma. Peak gamma sits at
the strike and grows and concentrates into maturity.

**Vega** `ν = ∂P/∂σ`. Long options are always long vega. Peak vega sits at the strike; peak
vega **falls** over time while peak gamma rises. Longer-dated options are vega-dominated,
shorter-dated are gamma-dominated; the book puts the crossover around the two-month tenor.

Approximate ATM vega reference points traders carry in their heads (Ch. 9):
`O/N ≈ 0.02%`, `1mth ≈ 0.10%`, `3mth ≈ 0.20%`, `1yr ≈ 0.40%`. Vega scales as `√T`.

### Chapter 7 — Vanilla FX Derivatives Pricing

**The volatility surface** splits into the **ATM curve** (term structure, the backbone) and
the **volatility smile** (strike dimension at each tenor).

**ATM contracts** are quoted at market tenors: O/N, 1wk, 2wk, 1mth, 2mth, 3mth, 6mth, 1yr,
2yr. Their strike is near, not necessarily at, the forward — the exact definition is a
market convention (below).

Because tenors are fixed but dates are not, the liquid contract changes every day: today's
1mth has a different expiry date from yesterday's. That is what makes Practical D necessary.

Curve shapes: **upward sloping** if the back end is higher than the front, **downward
sloping** / **inverted** if the front is higher (typical of stressed markets). Curves move
in **parallel** shifts or **weighted** shifts (front end moves more than back end).

**Bid–offer spreads.** Standard ATM volatility spreads are wide in short dates, tightest
from 1mth to 1yr, and widen again at long tenors:

| Tenor | ATM vol spread |
|---|---|
| O/N | 3.0% |
| 1wk | 1.0% |
| 2wk | 0.6% |
| 1mth–1yr | 0.3% |
| 2yr | 0.35% |
| 3yr | 0.4% |
| 4yr | 0.45% |
| 5yr | 0.5% |

Comparing volatility spreads across tenors is misleading, because vega differs. Multiply by
vega to get the premium spread, and the 1mth turns out to be the tightest in premium terms —
which matches it being the most liquid contract. Away from the ATM, spread widens in
volatility terms (lower vega) but by less than constant-premium spreading would imply.

**ATM definitions — three of them, and they are not the same thing:**
1. **Zero-delta straddle** — strike set so `Δ_call = −Δ_put`, hence zero delta on the
   package. This is the G10 (and some EM) convention.
2. **ATMF** — strike exactly equal to the forward, traded as a single option plus a forward
   hedge. Used in some EM pairs.
3. **ATMS** — strike equal to current spot.

"ATM" defaulting to *delta-neutral straddle* rather than *at-the-forward* is a classic
misconception and belongs in the notebook trap list.

**Out-of-the-money convention.** For strikes away from the ATM the market always trades the
OTM side — the call or put with the lower absolute delta. Strike above the ATM ⇒ traded as
a CCY1 call. Strike below ⇒ traded as a CCY1 put. The reason is credit: the OTM direction
has smaller premium and smaller expected payoff.

**Rounding.** Volatility quotes round to 0.05% in short tenors and 0.025% in longer ones
(inflection around 2mth). CCY1% premium rounds to a quarter or half basis point. A basis
point is 0.01% of notional.

**Delta hedged vs live.** Quoted in volatility ⇒ traded delta hedged (spot or forward hedge
transacted at the same rate the deal was priced). Quoted in premium ⇒ traded live, and the
two-way premium must then use two-way spot and forward as well as two-way volatility,
because those spreads get crossed on the hedge.

### Chapter 8 — Vanilla FX Derivatives Structures

Vega is the focus; at short tenors read "gamma" for "vega" throughout.

**Straddle** — call + put, same strike, notional, expiry, cut. Priced as one volatility for
both legs. Vega profile identical to a single option in the combined notional.

**Zero-delta straddle strike.** Setting `Δ_call = −Δ_put` gives `N(d1) = ½`, hence `d1 = 0`,
hence:

```
K = S · e^((r2 − r1 + σ²/2)·T)        # CCY2 premium (standard Black-Scholes)
K = S · e^((r2 − r1 − σ²/2)·T)        # CCY1 premium (premium-adjusted delta)
```

So with CCY2 premium the ATM straddle strike is **above** the forward by the Itō term, and
with CCY1 premium it is **below**. The gap grows with volatility and time. EUR/USD is CCY2
premium; USD/JPY is CCY1 premium. Premium-included vs premium-excluded delta is another
standing trap for the notebook list. Full premium-adjusted delta treatment is Chapter 14 —
out of scope here, and flagged as such.

**Strangle** — call and put at different strikes, both OTM, so `K_call > K_put`. Often
quoted at a given delta ("25 delta strangle"). Approximate volatility, vega-weighted:

```
σ_strangle ≈ (σ1·ν1 + σ2·ν2) / (ν1 + ν2)
```

With equal-delta strikes the vegas are close and it is nearly the simple average.

**Butterfly (fly)** — long strangle + short straddle. Buying the fly means buying the wings.
The **broker fly** traded in the interbank market has equal-notional strangle strikes and
the ATM notional set so the package is initially **vega neutral**; the butterfly notional is
quoted as the strangle notional. Because it has zero vega and minimal gamma by construction
it is quoted much tighter than the strangle alone. Broker fly strike placement is a whole
topic — see Chapter 12 below.

**Risk reversal (RR)** — long one strike, short the other, same notional, expiry and cut,
one call one put. Deltas **compound** rather than offset: hedging a 25d RR requires
25% × 2 = 50% of one leg's notional. Quoted as a volatility differential when the strikes
are the same delta. Market convention on spread contracts: one leg **choice** (a single
price, "CH"), the other leg carries the entire two-way spread. Corporates call these
**collars** when used to cap and floor an FX exposure; a zero-premium collar is a popular
structure.

**Leveraged forward** — synthetic forward with unequal notionals, e.g. buy `N` of the call
and sell `2N` of the put. Decomposes into a forward in the matched notional plus a vanilla
in the unmatched notional; both the vega risk and the volatility price equal that of the
unmatched vanilla. Sold to clients wanting a better-than-forward rate for zero premium,
funded by the larger sell leg.

**ATM calendar spread** — buy one tenor's ATM, sell another's. Vega-neutral version sets
the notionals so net vega is zero. Gives exposure to the *shape* of the ATM curve. Standard
spread quoting: spread the leg with more vega (the far date), choice the near.

**Call / put spreads** — two legs same direction (both calls or both puts), same maturity
and notional, one bought one sold. Cheaper than the outright for a directional view, with
the payoff capped at the further strike. Once delta hedged, the vega exposure is the same
shape as a risk reversal's: long vega at the long strike, short at the short strike.

**Seagull** — call/put spread plus an additional short option on the other side. Usually
sold for zero premium to clients hedging an underlying exposure.

### Chapter 9 — Vanilla FX Derivatives Risk Management

Risk groupings traders use: short-date risk (delta/gamma/theta), ATM risk
(vega/weighted vega/bucketed vega), smile risk, interest rate risk, cross-exposures.

**Spot ladder** — the main position view: P&L, delta and gamma across a range of spot
levels, holding all other market data fixed. Spot spacings should scale with the pair's
spot volatility. Gamma is quoted per 1% spot move.

**Trading long gamma.** Spot up + long gamma ⇒ delta gets longer ⇒ long delta + spot up ⇒
positive P&L. Spot down + long gamma ⇒ delta gets shorter ⇒ short delta + spot down ⇒
positive P&L again. Either direction makes money as long as spot *moves*. Hedging that
delta means selling high and buying low — "trading the gamma". The cost is **theta**.

Net result: long gamma wins if realised volatility exceeds implied; short gamma wins if
realised is below implied. That is the essence of the whole business.

**Trading short gamma** is the exact mirror: every spot move produces negative P&L change,
the trader earns theta, and the decision is whether to stop-loss the delta or let it run.
The book's rule of thumb: expect to lose at least half the theta earned through stopping
out.

**Consistency checks** on any position (useful as assertions in a risk module):
```
long gamma  + spot higher → delta longer
long gamma  + spot lower  → delta shorter
short gamma + spot higher → delta shorter
short gamma + spot lower  → delta longer
long delta  + spot higher → P&L up
short delta + spot lower  → P&L up
```
A delta *jump* that breaks the smooth gamma pattern means there is a **strike** expiring
today at that level. Options expiring on the horizon are shown at expiry: an instantaneous
delta jump of the option notional, not a gamma profile.

**P&L balance** — whether equal-sized up and down spot moves give similar P&L changes.
Traders look at roughly 1.5 standard deviations of a one-day move (about 0.75%–1% in a 10%
vol pair). Rebalance by trading spot: to shift P&L by `X` at a spot distance `d`, trade
`X/d` of notional.

**Theta.** Quoted as the change in position value from one trading day to the next. Long
gamma ⇒ negative theta and vice versa. In Black-Scholes world gamma and theta are
proportional. Other sources of theta (smile decay, roll down the ATM curve, funding) exist
but are Chapter 14.

**Vega and bucketed vega.** `P&L_change ≈ σ_change × vega`. Vega is bucketed at the option's
own maturity; an option between two market tenors splits its vega across them. **Weighted
vega** is the exposure to a weighted (front-end-heavy) curve shift rather than a parallel
one — detail in Chapter 14.

Hedging vega across tenors is not flat risk: it leaves gamma exposure, spot-dependent vega,
and curve-shape exposure.

**Mark-to-market P&L.** Positions are revalued as a whole rather than tracked trade by
trade. A new deal's P&L on entry is the difference between the traded price and the
prevailing mid — so crossing a spread books an immediate loss equal to the spread crossed,
which is the same lesson as Practical A in a different setting.

**Good and bad dates.** Days with data releases are expected to be more volatile; holiday
periods less so. Being long good days and short bad days is an easier position to manage,
but only at a sensible price — which is exactly what the day weights in Practical E let you
express and value.

### Chapter 10 — Miscellaneous Topics → **Practical D**

**Discounting.** Discount factors by compounding convention:

```
zero rate         df = 1 / (1 + r0·T)
annual compound   df = 1 / (1 + rA)^T
m times a year    df = 1 / (1 + rm/m)^(T·m)
continuous        df = e^(−r·T)          # the Black-Scholes convention
```

Only the continuous form is used in this repo. Real curve building is bootstrapped from
many instruments; the book explicitly sets that aside and so do we.

**The four dates:**
- **Horizon** — today, the date the trade originates.
- **Spot date** — when the premium and any spot hedge settle. Normally T+2.
- **Expiry date** — when the contract expires.
- **Delivery date** — when the final funds move; forward hedges settle here. Derived from
  the expiry date exactly as the spot date is derived from the horizon.

All four can only be weekdays.

**Tenor rules** (this is the specification for `expiry_from_tenor`):

- **Overnight** — expiry is the next weekday after the horizon. Delivery derived from
  expiry as spot is from horizon. Note the O/N expiry can precede the spot date.
- **Days / weeks** — expiry is `v` or `7x` **calendar days after the horizon**, directly.
  If that lands on a weekend or 1 January the tenor is invalid.
- **Months** — compute the spot date, add `y` months to reach the delivery date, roll
  forward to an acceptable business day if needed, then take the **inverse spot date**
  (come back two business days) to get the expiry.
- **Years** — same as months with `z` years.

Note the asymmetry: weeks are added to the *horizon*; months and years go via the *spot
date* and come back. That is not an arbitrary quirk — it is because month and year
contracts are defined by their delivery date.

**Special cases the practical skips** (implement as documented TODOs, per the ground rules):
1. **End-end** — if the spot date is the last business day of its month, the delivery date
   is by convention the last business day of the target month.
2. **Month overflow** — if the spot date is before month end but the natural delivery date
   would fall beyond the end of the target month, the delivery date is the last business day
   of the target month (e.g. spot date 30 January, 1M ⇒ delivery 28 February).

Also skipped: holiday calendars (the practical is weekends-only), the USD-clearing rule
(no settlement on US holidays even in non-USD pairs), the T+1 pairs, and the fact that
expiry dates can differ by cut and time zone within the same trading day.

**Premium conversions.** Premiums can be quoted four ways: CCY1%, CCY2 pips, CCY2%, CCY1
pips. `%` prices share notional and premium currency; `pips` prices do not. Pairs where
premium is paid in CCY1 are **left-hand side (LHS)**; in CCY2, **right-hand side (RHS)**.
EUR/USD is CCY2 pips; EUR/JPY is CCY1%. Conversions require the contract to have a strike.

---

## Practical D — Generating Tenor Dates (Ch. 10)

Weekend-only business day logic; no holiday calendar — but the code should take an
injectable calendar so one can be added later, and say so in the docstring.

Required functions:
- `next_business_day(d)` — Sat → +2, Fri → +3, else +1.
- `previous_business_day(d)` — Sun → −2, Mon → −3, else −1.
- `business_day_increment(d, n)` / `business_day_decrement(d, n)` — iterate the above.
- `spot_date_from_horizon(d)` = increment 2 business days (T+2 assumed throughout).
- `horizon_from_spot_date(d)` = decrement 2 business days.
- `expiry_from_tenor(horizon, tenor)`:
  - `ON` → `next_business_day(horizon)`
  - `nW` → `horizon + 7n` calendar days
  - `nM` → delivery = spot date + n months; expiry = `horizon_from_spot_date(delivery)`
  - `nY` → delivery = spot date + n years; expiry = `horizon_from_spot_date(delivery)`
  - anything else → raise a clear exception. The book pops a message box and returns −1;
    a sentinel return value is worse than useless in Python. Recorded in deviations.

**Deliverable table:** ON, 1W, 2W, 1M, 2M, 3M, 6M, 9M, 1Y, 2Y with expiry date, delivery
date, day of week and day count.

---

### Chapter 11 — ATM Curve Construction → **Practical E**

**Variance is the master quantity.**

```
variance(T) = σ² · T
```

Two properties that make it the right thing to work in:
1. Variance over any period must be **non-negative**.
2. Variance is **additive** across time.

Volatility has neither property, which is exactly why interpolating in volatility can
produce arbitrage.

**Forward volatility** between `T1 < T2`:

```
σ_fwd = √[ (σ2²·T2 − σ1²·T1) / (T2 − T1) ]
```

Worked example from the book: 6mth at 10.5% and 1yr at 11.7% ⇒ forward vol from 6mth to
1yr ≈ 12.8%. Good regression test value.

**Two interpolation methods, and the tradeoff:**

```
linear in volatility:  σ(t) = σ1 + (σ2 − σ1)·(t − T1)/(T2 − T1)
linear in variance:    var(t) = var1 + (var2 − var1)·(t − T1)/(T2 − T1)
                       σ(t)   = √( var(t) / t )
```

- Linear volatility gives intuitive-looking curves but **does not guarantee non-negative
  forward variance**. The book's counterexample (curve B): flat 20% out to 1yr, then 15% at
  2yr. Variance to 1yr = 0.04; to 18mth (17.5% interpolated) = 0.046; to 2yr = 0.045.
  Variance falls between 18mth and 2yr — negative forward variance, from perfectly valid
  inputs.
- Linear variance guarantees non-negative forward variance given valid inputs, but produces
  odd volatility shapes: a sharp rise then a flattening between each pair of tenors, and
  daily variance that jumps discontinuously at each tenor date. There is no reason the day
  before the 3mth tenor should differ from the day after.

In practice desks combine both, building in variance terms with more sophisticated control
of how daily variance evolves.

**Parametric model** (the book is explicit that this exact form would never be used in
practice because it can generate arbitrageable curves):

```
σ_T = σ_short + (σ_long − σ_short)·(1 − e^(−λ·T))
```

`(1 − e^(−λT))` runs from 0 to 1; higher `λ` gets there faster. Plot at monthly (1/12)
intervals. Model-based curves also need per-tenor overrides so the surface hits market mids;
an override is itself information (a −0.1% override at 2mth says the 2mth is cheap).

**Short-date variance arithmetic.** Worked examples worth turning into tests:
- 1wk (7-day) ATM at 12.0%, five weekdays of equal variance and zero over the weekend.
  8-day ATM = `√( variance_1wk · (6/5) / (8/365) )` = **12.3%**.
- Same 1wk at 12.0% but the 8th day is completely static:
  8-day ATM = `√( variance_1wk / (8/365) )` = **11.25%**. This is a lower bound.

**Weekend effect.** With five open days and zero weekend variance,
`σ_1wk = σ_O/N · √(5/7)`, so the overnight is **higher** than the 1wk. Generalising: for a
fixed horizon, a future Monday expiry almost always prices below the Friday after it,
because Friday has a higher open-days-to-calendar-days ratio. This is the **ATM saw-tooth**,
and it damps out at longer tenors as the ratio stabilises.

**Discrete daily T.** The market prices with `T` in whole days. Consequence: as the day
passes, real variance to a fixed expiry falls, but `T` does not — so *implied volatility*
falls instead. The overnight jumps up at the start of each trading day and grinds lower
through it. The book works the example: O/N at 15.0% at 9am London, NY cut 30 hours away;
after one hour, 29/30 of the variance remains, giving 14.75%.

**Friday overnight.** On a Friday the "overnight" spans three days, so `T = 3/365`. With
equal weekday variance and zero weekend variance the premium is the same each day, so
`σ_3day = σ_1day / √3`. A Friday overnight quote is therefore **not comparable** to other
days' without multiplying by `√3`.

**NY vs TOK cut.** NY cut contains about nine more hours of optionality, so TOK always
trades at a discount: `σ_TOK = σ_NY · √(T_TOK / T_NY)` in real time terms. The differential
widens through the trading day (0.84× at 9am GMT, 0.77× at 5pm GMT for the overnight) and
vanishes past about 3mth (0.998× at 3mth).

**Events and holidays.** Events (NFP, elections) get higher variance on the date, which
raises the ATM for that expiry **and every expiry after it**. Holidays get lower variance.
Intraday, realised variance builds through Asia, peaks around 08:00 GMT with London, dips
at London lunch, peaks again around 14:00 GMT with New York in, then falls after 15:00.

---

## Practical E — Constructing an ATM Curve (Ch. 11)

### Task A — interpolation
Inputs: expiry dates at market tenors (from Practical D) plus an ATM vol at each. Start
with a simple upward-sloping test curve.

Implement **both** linear-in-volatility and linear-in-variance. Times are measured as
`(date − horizon) / 365`.

**Four test cases the book calls out:**
1. Query date before the first tenor expiry.
2. Query date after the last tenor expiry.
3. Query date exactly on a tenor expiry.
4. Query date between two tenor expiries.

The book returns `−1` outside the range. A magic sentinel is a bug waiting to happen —
raise instead. Recorded in deviations.

Chart daily ATM vols out to two years, and chart total variance beside it.

### Task B — parametric model
`σ_T = σ_short + (σ_long − σ_short)·(1 − e^(−λT))`. Plot at monthly intervals, then attach
it to the market tenor expiry dates and their `T`s.

Beyond the book: least-squares calibration of `(σ_short, σ_long, λ)` to a set of tenor vols,
reporting the fit error.

### Task C — day weights (the important one)
One row per calendar date, starting one day after the horizon, running at least a year.

- Assign each date a weight by weekday, from a lookup table.
- `economic_time = cumulative_weight_sum / 365`
- `total_variance = σ² · Σ(ω_i · dt)` with `dt = 1/365`
- Recover ATM volatility from total variance using **calendar** time:
  `σ_ATM(t) = √( total_variance(t) / calendar_time(t) )`

The calendar-vs-economic-time distinction is the entire mechanism and belongs in the
misconception list.

**Staging (this is what the practical is built around):**
1. All weights = 1 ⇒ economic time equals calendar time ⇒ the curve is flat.
2. Set weekend weights to 0 and re-plot ⇒ the **saw-tooth** appears. Monday's expiry prices
   below the preceding Friday's because economic time stops over the weekend.
   Present these two charts side by side.
3. Note that the level tends toward something *below* the flat input volatility, because the
   economic-to-calendar time ratio is now below 1. Real desks adjust for this when they have
   target levels to hit. In practice desks assign a small non-zero weekend weight rather
   than exactly zero, because weekend news can gap spot on the Monday open.
4. Add an event: raise the weight on the Non-Farm Payrolls date — the book uses **Thursday
   3 July 2014** — and show that the ATM rises for that date **and all subsequent dates**.

**Forward variance and forward overnight vol.** Take the difference in total variance
between consecutive dates to get daily variance, then convert to a daily/forward overnight
ATM volatility. This strip of forward overnight vols is what a trader actually reads to
judge whether the curve is rich or cheap over an event.

Add an explicit check for **negative forward variance** and flag it loudly: it means the
variance to the later date is lower than to the earlier one, which is a calendar arbitrage
— sell the near option, buy the far one, and the variance you are short is free.

The book notes that real desks combine a proper core curve (Task A or B) with weights on
top, constructed so non-negative forward variance is guaranteed. Our version does not
guarantee it — hence the check.

---

### Chapter 12 — Volatility Smile Market Instruments → **Practical F**

**Three instruments per tenor:** ATM (level), butterfly (height of the wings), risk
reversal (tilt/skew). Fly and RR are quoted at 25 delta and 10 delta.

**The standard approximations:**

```
σ_25d_call = σ_ATM + σ_fly25 + ½·σ_RR25
σ_25d_put  = σ_ATM + σ_fly25 − ½·σ_RR25

σ_RR25  = σ_25d_call − σ_25d_put
σ_fly25 = (σ_25d_call + σ_25d_put)/2 − σ_ATM
```

**The Malz (1997) formula**, generalising these to any delta, in terms of the **positive
quoted put delta** `X` between 0 and 1:

```
σ(X) = σ_ATM + 2·σ_RR25·(X − 0.5) + 16·σ_fly25·(X − 0.5)²
```

Sanity checks that fall straight out:
- `X = 0.5` ⇒ `σ_ATM`.
- `X = 0.25` ⇒ `σ_ATM + σ_fly25 − ½σ_RR25` (25d put).
- `X = 0.75` ⇒ `σ_ATM + σ_fly25 + ½σ_RR25` (25d call).
- `X = 0.10` ⇒ `σ_ATM − 0.8·σ_RR25 + 2.56·σ_fly25`.
- `X = 0.90` ⇒ `σ_ATM + 0.8·σ_RR25 + 2.56·σ_fly25`.
- Hence `σ_RR10 = 1.6 · σ_RR25` inside the Malz model. The book notes the market value is
  usually nearer **1.8**, so the model understates the 10d skew. Worth stating in the
  notebook: it is a known limitation, not a bug.

Zero RR and zero fly ⇒ flat smile. Positive fly lifts both wings symmetrically. Positive RR
tilts topside up; negative RR tilts downside up.

**Smile shapes in practice:** FX smiles differ by pair, unlike equities where downside
strikes are systematically bid. Higher implied volatility sits on the *weaker* side of spot
— the direction spot is more likely to jump. USD/EM pairs quoted USD/CCY have topside-rich
smiles because the tail risk is EM devaluation.

**The three vega exposures** — this is why the market uses these three instruments:

| Instrument | Vega | Vanna `∂ν/∂S` | Volga `∂ν/∂σ` |
|---|---|---|---|
| ATM | **yes** | no | no |
| Risk reversal | no | **yes** (sign depends on smile direction) | no |
| Butterfly | no (by construction) | no | **yes** |

So: ATM trades the *level* of volatility, RR trades the *spot-vs-volatility relationship*,
fly trades the *volatility of volatility*.

Vanna has a dual reading: `∂ν/∂S` and `∂Δ/∂σ`. An OTM topside call gets longer delta when
volatility rises (wider distribution ⇒ more chance of finishing ITM) ⇒ long vanna. An ITM
downside call strike gets shorter delta ⇒ short vanna.

Neat observation the book makes: the ATM's vanna profile has the same shape as the RR's
vega profile, and the ATM's volga profile the same shape as the fly's vega profile.

**Position-level smile greeks:** vanna and volga explain how vega moves; **rega** `∂P/∂RR`
and **sega** `∂P/∂fly` explain P&L against the quoted instruments themselves. Out of scope
for the practicals but defined in the glossary.

**Broker fly vs strike fly — a real trap.** The fly quoted and traded in the broker market
is the **broker fly**, and its strikes are *not* the outright 25d strikes. Definition: the
broker fly is the volatility at which the strangle, with strikes generated *and* priced at
`σ_ATM + σ_fly`, costs the same as those same strikes priced on the full smile. Crucially,
strike generation ignores the risk reversal. The **strike fly** (built from the true
outright 25d strikes) is rarely traded.

Consequence: on the rich side of the smile the broker fly strike sits closer to the ATM than
the outright strike; on the cheap side, further away. In high-skew or long-dated pairs the
gap is large. Because of the strike placement, a broker fly carries vanna when valued on the
smile — which is why AUD/JPY 25d flies go *more negative* at longer tenors even as ATM and
RR rise.

**Practical F uses the Malz model on outright deltas, not broker flies.** That is the
book's own simplification and must be stated plainly wherever the smile is used.

---

## Practical F — Constructing a Volatility Smile (Ch. 12)

### Task A — Malz model
Implement `σ(X)` per the formula above. Verify the three anchor points.

### Task B — plot vol vs delta
Sweep 0–100% delta. Interactive controls for ATM, RR and fly. **Fix the y-axis limits** so
the shape changes rather than the axis rescaling — the book is explicit about this and it
genuinely matters for seeing what the parameters do.

### Task C — strike from delta

Put delta from strike:

```
Δ_put = e^(−r1·T)·[N(d1) − 1]        # true, negative
```

Inverted:

```
K = S / exp( N⁻¹( e^(r1·T)·Δ_put + 1 )·σ√T − (r2 − r1 + σ²/2)·T )
```

Split into three parts for legibility, as the book does:
```
part1 = e^(r1·T)·Δ_put + 1
part2 = σ·√T
part3 = (r2 − r1 + σ²/2)·T
K     = S / exp( N⁻¹(part1)·part2 − part3 )
```

**The put delta used inside these formulas is the true negative value, not the positive
quoted delta.** The book flags this twice. The docstring must be explicit about it.

Round-trip test: strike → delta → strike must return the input across a grid of parameters.

### Task D — combine
Plot implied volatility versus delta and versus strike. 0% and 100% delta have no finite
strike, so substitute e.g. 0.01% and 99.99%.

### Task E — strike placement
Solve for the 10d, 25d, 50d, 75d and 90d put-delta strikes **using the smile volatility at
each delta**. Note this is implicit — the volatility depends on the delta, which depends on
the strike. In the Malz parameterisation the smile is quoted *in delta space*, so the
volatility at a given delta is known directly and no iteration is required; state that
explicitly rather than leaving the reader to wonder.

Reproduce each experiment as a chart with a written mechanism:

| Change | Effect on strike placement |
|---|---|
| No smile (RR = fly = 0) | Roughly even spacing; topside slightly wider from log-normality |
| Lower vol or shorter tenor | Distribution tightens ⇒ strikes pull in toward the ATM |
| Higher vol or longer tenor | Distribution widens ⇒ strikes push out |
| Higher butterfly | Strikes further out, with more effect in the wings (higher vol there) |
| Risk reversal | Asymmetric: further out on the rich side, closer on the cheap side |
| Higher `r1` or lower `r2` | Forward lower ⇒ whole smile shifts lower |
| Higher `r2` or lower `r1` | Forward higher ⇒ whole smile shifts higher |

---

## Assembled volatility surface (beyond the book)

The book stops at "here is an ATM curve" and "here is a smile" and never joins them.
`fxds/surface.py` assembles:

```
tenor dates (Practical D)
    → ATM curve with day weights (Practical E)
        → Malz smile per tenor (Practical F)
            → vol(expiry_date, strike)
```

Simplifications this assembly carries, to be stated in the module docstring and the
notebook:
- Malz smile, so no broker fly treatment and the 10d skew is understated (1.6× vs ~1.8×).
- Smile parameters interpolated across tenors in a chosen (documented) way; real desks
  differ on whether to interpolate in delta, strike or model-parameter space.
- Spot delta throughout; no forward-delta or premium-adjusted-delta conventions.
- Weekends-only calendar, no holidays.
- Flat continuously compounded rates, no curve.
- Non-negative forward variance is checked, not guaranteed by construction.

---

## Consolidated test values

| # | Source | Inputs | Expected |
|---|---|---|---|
| 1 | Practical B, Test 1 | forward payoff struck at the forward | ≈ 0 |
| 2 | Practical B, Test 2 | `S=K=100`, `r1=r2=0`, `T=1`, `σ=10%`, call | slightly under 4.00 CCY1% |
| 3 | Practical C, Task A | `S=K=1.0`, `T=1`, `σ=10%`, `r1=r2=0` | 0.0399 CCY2 pips |
| 4 | Practical C, Task C | same inputs | delta ≈ 50% |
| 5 | Practical C, Task C | same inputs | vega a shade under 0.40% |
| 6 | Practical C, Task A Step 4 | `K = F` | call price = put price |
| 7 | Practical C, Task A Step 4 | `K ≠ F` | `call − put = e^(−r2·T)(F − K)`; undiscounted fails |
| 8 | Ch. 11 | 6mth 10.5%, 1yr 11.7% | forward vol 6mth→1yr ≈ 12.8% |
| 9 | Ch. 11 | 1wk 12.0%, 5 open days, weekend zero | 8-day ATM = 12.3% |
| 10 | Ch. 11 | 1wk 12.0%, 8th day static | 8-day ATM = 11.25% |
| 11 | Ch. 11 | O/N 15.0% at 9am, 30h to NY cut | after 1h ⇒ 14.75% |
| 12 | Ch. 11 | weekend zero variance | `σ_1wk = σ_O/N·√(5/7)` |
| 13 | Ch. 11 | Friday overnight | `σ_3day = σ_1day/√3` |
| 14 | Practical F, Task A | Malz at `X = 50%` | `σ_ATM` |
| 15 | Practical F, Task A | Malz at `X = 25%` / `75%` | `σ_ATM + σ_fly ∓ ½σ_RR` |
| 16 | Ch. 12 | Malz at 10d | `σ_RR10 = 1.6·σ_RR25` |
| 17 | Practical F, Task C | strike → delta → strike | round-trips |
| 18 | Practical E, Task C | all weights = 1 | curve is flat |
| 19 | Practical E, Task C | weekend weights = 0 | saw-tooth; Monday below preceding Friday |
| 20 | Practical E, Task C | raised NFP weight | that date **and all later dates** rise |
| 21 | Practical E, Task A | query outside tenor range | explicit error, not a sentinel |
| 22 | Cross-validation | Practical B integration vs Practical C closed form | agree for vanillas |

Test 22 is not in the book. It is the headline test of the repo: two independent routes to
the same number.
