# EOD precious metals report — prototype

A working Streamlit prototype of an end-of-day precious metals report for a
bank trading desk. An analyst opens it after the London close, reads today's
desk and market data across seven sections, writes commentary beside each one,
then generates an email-ready HTML report covering the session just gone and
the session and week ahead.

**Every number in this app is fabricated.** There is no market data connection.
The prototype exists to pin down the data contract and the layout so a
production version can be built from it in Rust — the pydantic models in
`models.py` are the contract, and `schema/` is the machine-readable copy.

---

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate   # Python 3.11+
pip install -r requirements.txt
streamlit run app.py
```

Then, to regenerate the handoff bundle in `schema/`:

```bash
python export_schema.py                    # today's session, London
python export_schema.py --date 2026-08-24  # a specific session
```

Both commands run from inside `eod_report/`.

## How the app is used

1. Pick the report date and type your name in the sidebar. The date drives
   everything: the mock data for a given date is always identical.
2. Read each section on the left and write its commentary on the right. Boxes
   autosave whenever you leave them, so a refresh cannot lose work.
3. Open the **Report** tab and press **Generate report**.
4. Preview the email, download the `.html`, or copy the source.

Commentary lives in `commentary/{YYYY-MM-DD}.json`, one file per session, and
is gitignored. **Load yesterday's commentary** pulls in the most recent earlier
draft as a starting point — in practice that is the last session written up,
not literally yesterday, which is what you want after a weekend or a holiday.

## Repository layout

```
eod_report/
  app.py                  # Streamlit entry point, page config, layout
  config.py               # USE_MOCK flag, price anchors, metals list, constants
  models.py               # pydantic models — the data contract
  formatting.py           # shared number/date formatting (app and email)
  charts.py               # the two plotly figures (app and email)
  export_schema.py        # writes schema/ and the sample payloads
  data/
    provider.py           # DataProvider protocol + get_provider() factory
    mock_provider.py      # deterministic fabricated data
    live_provider.py      # stub, raises NotImplementedError, names real sources
  ui/
    sections.py           # one render function per report section
    commentary.py         # commentary editor + persistence
  report/
    template.html.j2      # email HTML (inline CSS, table-based)
    render.py             # models + commentary -> HTML string
    send.py.example       # where SMTP delivery would plug in; not implemented
  commentary/             # saved JSON drafts, gitignored
  schema/                 # JSON Schema exported from the pydantic models
  README.md
  requirements.txt
```

`formatting.py` and `charts.py` are the two additions to the layout as
originally specified. Both exist because the app and the email have to agree:
a number must read identically in both, and the two charts are built once and
rendered either to the browser or to a PNG.

## The data contract

`models.py` is the file to port. Conventions, applied without exception:

| suffix | meaning |
|---|---|
| `_oz` | troy ounces (1 oz = 31.1035 g) |
| `_tonnes` | metric tonnes (1 t = 32,150.7 oz) |
| `_usd` | United States dollars |
| `_usd_per_oz` | United States dollars per troy ounce |
| `_pct` | percent, written `12.5` for 12.5% — never a fraction |
| `_bp` | basis points, written `25.0` for 0.25% |
| `_lots` | exchange contracts (see `contract_size_oz`) |
| `_count` | an integer tally |
| `_date` / `_at` | calendar date / instant |

* **Signs.** Anything that can point two ways is signed and says so in its
  description. Desk positions are positive when long. Client flow is positive
  when the *client* buys and the desk sells. P&L is positive when the desk
  makes money. Inventory and holdings changes are positive when metal arrives.
* **Units** are in the field name or the description, never in a column header
  alone, and currency is never scaled ("in millions" does not appear).
* **Dates** are London dates; instants are timezone-aware London time.
* **Enums** are string enums, so they deserialise as tagged strings.
* `extra="forbid"` everywhere: an unexpected field is a contract breach and
  should fail loudly on both sides of the port.

Unit conversions live in exactly one place, `config.py`: `OZ_PER_TONNE`,
`GRAMS_PER_TROY_OZ`, `TONNES_PER_OZ`, and the `oz_to_tonnes` / `tonnes_to_oz` /
`oz_to_grams` helpers.

### Enumerations

| enum | values |
|---|---|
| `Metal` | `XAU`, `XAG`, `XPT`, `XPD` |
| `Direction` | `up`, `down`, `flat` |
| `TradeSide` | `buy`, `sell`, `flat` |
| `ClientSegment` | `central_bank`, `producer_hedger`, `refiner`, `investment_asset_manager`, `industrial`, `hedge_fund_cta`, `retail_wholesale` |
| `TrendLabel` | `uptrend`, `range`, `downtrend` |
| `LevelType` | `support`, `resistance` |
| `EventCategory` | `economic_release`, `central_bank`, `comex_first_notice`, `contract_expiry`, `roll_window`, `lbma_auction`, `holiday` |
| `EventImportance` | `high`, `medium`, `low` |
| `SectionKey` | `market_overview`, `client_flows`, `risk`, `technicals`, `etf_flows`, `positioning`, `physical`, `look_ahead` |

## Section-by-section field list

The root object is `EodReport`, holding `header`, `client_flows`, `risk`,
`technicals`, `etf`, `positioning`, `physical` and `look_ahead`. Commentary is
carried separately in `Commentary`, keyed by `SectionKey`, because it is
authored rather than sourced.

### Section 0 — header and snapshot

**`ReportHeader`** — Report identity plus the snapshot strip that opens the email.

| field | type | meaning |
|---|---|---|
| `report_date` | `date` | London trading date the report covers. |
| `generated_at_london` | `datetime` | Timezone-aware instant the report was generated, Europe/London. |
| `report_label` | `str` | Fixed label, e.g. "EOD — London close", shown beside the date. |
| `author_name` | `str` | Analyst publishing the report; free text. |
| `headline` | `str` | One-line headline typed by the analyst; empty is omitted from the email. |
| `snapshot` | `list[MetalSnapshot]` | One entry per metal in scope, in report order. |

**`MetalSnapshot`** — One metal's line in the header snapshot strip.

| field | type | meaning |
|---|---|---|
| `metal` | `Metal` | Enumerated value; see the enum table above. |
| `close_usd_per_oz` | `float` | Spot close at the London close. |
| `prior_close_usd_per_oz` | `float` | Previous session's spot close, the comparison basis. |
| `change_usd_per_oz` | `float` | close_usd_per_oz minus prior_close_usd_per_oz; signed. |
| `change_pct` | `float` | Session change in percent of prior close; signed, 1.25 = +1.25%. |
| `session_high_usd_per_oz` | `float` | Highest spot print of the session. |
| `session_low_usd_per_oz` | `float` | Lowest spot print of the session. |
| `lbma_pm_auction_usd_per_oz` | `float` | LBMA PM auction price for the session. For silver, which has a single daily auction, the noon auction price is reported here. |
| `direction` | `Direction` | Sign of change_usd_per_oz, driving the coloured indicator. |
| `price_decimals` | `int` | Decimal places this instrument is quoted to, for display consistency. |

### Section 1 — client flows

**`ClientFlowsSection`** — Section 1. Desk-facing client flow, net of internal transfers.

| field | type | meaning |
|---|---|---|
| `metals` | `list[MetalClientFlow]` | Enumerated value; see the enum table above. |
| `total_ticket_count` | `int` | Tickets across all metals. |
| `total_gross_usd` | `float` | Gross USD notional traded with clients across all metals. |

**`MetalClientFlow`** — Client activity in one metal across the session.

| field | type | meaning |
|---|---|---|
| `metal` | `Metal` | Enumerated value; see the enum table above. |
| `net_client_side` | `TradeSide` | Direction of the aggregate client flow: buy, sell or flat. |
| `net_client_oz` | `float` | Net troy ounces; positive when clients bought on balance. |
| `net_client_usd` | `float` | Net USD notional of client flow; sign matches net_client_oz. |
| `gross_client_oz` | `float` | Sum of absolute client volume in troy ounces (two-way turnover). |
| `segment_breakdown` | `list[ClientSegmentFlow]` | Net flow per client segment; sums to net_client_oz / net_client_usd. |
| `top_axes` | `list[str]` | Up to three short free-text axes, most significant first. |
| `unallocated_balance_change_oz` | `float` | Change in client unallocated (loco London) account balances in troy ounces; positive when client metal holdings with the desk increased. |
| `ticket_count` | `int` | Total tickets in this metal. |
| `average_ticket_size_oz` | `float` | Gross ounces divided by ticket_count. |
| `average_ticket_size_usd` | `float` | Gross USD notional divided by ticket_count. |

**`ClientSegmentFlow`** — Net client flow for one metal within one client segment.

| field | type | meaning |
|---|---|---|
| `segment` | `ClientSegment` | Enumerated value; see the enum table above. |
| `net_oz` | `float` | Net troy ounces; positive when the segment bought (desk sold). |
| `net_usd` | `float` | Net USD notional of the same flow; sign matches net_oz. |
| `ticket_count` | `int` | Tickets booked for this segment. |

### Section 2 — risk

**`RiskSection`** — Section 2. Position, P&L, VaR, greeks and limit usage.

| field | type | meaning |
|---|---|---|
| `positions` | `list[DeskPosition]` | — |
| `daily_pnl_usd` | `float` | Session P&L across the desk; positive is profit. |
| `mtd_pnl_usd` | `float` | Month-to-date P&L across the desk. |
| `ytd_pnl_usd` | `float` | Year-to-date P&L across the desk. |
| `pnl_attribution` | `PnlAttribution` | — |
| `desk_var_1d_99_usd` | `float` | Diversified desk-level 1-day 99% VaR in USD (positive loss). Lower than the sum of per-metal VaRs because of correlation benefit. |
| `greeks` | `list[OptionsGreeks]` | — |
| `limits` | `list[LimitUtilisation]` | — |
| `any_limit_flagged` | `bool` | True when at least one limit is at or above the warning threshold. |

**`DeskPosition`** — The desk's end-of-session position in one metal.

| field | type | meaning |
|---|---|---|
| `metal` | `Metal` | Enumerated value; see the enum table above. |
| `position_oz` | `float` | Outright position in troy ounces; positive long, negative short. |
| `delta_equivalent_oz` | `float` | Position including options delta, in troy ounces; positive long. Differs from position_oz by the options book's delta. |
| `usd_notional` | `float` | Delta-equivalent notional in USD; sign matches delta_equivalent_oz. |
| `var_1d_99_usd` | `float` | Standalone 1-day 99% VaR for this metal, in USD (positive loss). |

**`PnlAttribution`** — Daily P&L split by driver. Components sum to total_usd.

| field | type | meaning |
|---|---|---|
| `spot_usd` | `float` | P&L from outright spot exposure. |
| `carry_forward_usd` | `float` | P&L from forwards, leases and financing (carry). |
| `volatility_usd` | `float` | P&L from the options book's vol exposure. |
| `client_flow_usd` | `float` | P&L captured on client spread / franchise. |
| `other_usd` | `float` | Residual: fees, funding adjustments, rounding. |
| `total_usd` | `float` | Sum of the five components; the day's P&L. |

**`OptionsGreeks`** — Options book greeks for one metal, expressed per-metal not per-strike.

| field | type | meaning |
|---|---|---|
| `metal` | `Metal` | Enumerated value; see the enum table above. |
| `delta_oz` | `float` | Options delta in troy ounces; positive long. |
| `gamma_oz_per_pct` | `float` | Change in delta (troy ounces) for a +1% move in spot. |
| `vega_usd_per_vol_pt` | `float` | P&L in USD for a +1 volatility point move in implied vol. |
| `theta_usd_per_day` | `float` | Expected P&L in USD from one calendar day of time decay; usually negative when long options. |

**`LimitUtilisation`** — Utilisation of one desk risk limit.

| field | type | meaning |
|---|---|---|
| `limit_name` | `str` | Limit as named in the desk mandate. |
| `limit_usd` | `float` | Approved limit in USD. |
| `utilisation_usd` | `float` | Current usage in USD (absolute exposure against the limit). |
| `utilisation_pct` | `float` | utilisation_usd as a percent of limit_usd; 82.5 = 82.5%. |
| `above_warning_threshold` | `bool` | True when utilisation_pct is at or above the configured warning level (80%). |

### Section 3 — technicals

**`TechnicalsSection`** — Section 3. One technical block per metal plus charting defaults.

| field | type | meaning |
|---|---|---|
| `metals` | `list[MetalTechnicals]` | Enumerated value; see the enum table above. |
| `default_chart_metal` | `Metal` | Metal charted when the analyst has not chosen one. |
| `history_session_count` | `int` | Number of bars supplied per metal in price_history. |

**`MetalTechnicals`** — Technical picture for one metal at the London close.

| field | type | meaning |
|---|---|---|
| `metal` | `Metal` | Enumerated value; see the enum table above. |
| `close_usd_per_oz` | `float` | Close the technicals are measured against. |
| `ma_50_usd_per_oz` | `float` | 50-session simple moving average of closes. |
| `ma_100_usd_per_oz` | `float` | 100-session simple moving average of closes. |
| `ma_200_usd_per_oz` | `float` | 200-session simple moving average of closes. |
| `rsi_14` | `float` | 14-session Wilder RSI, 0-100. |
| `support_levels` | `list[TechnicalLevel]` | Key supports, nearest to the market first. |
| `resistance_levels` | `list[TechnicalLevel]` | Key resistances, nearest to the market first. |
| `trend_label` | `TrendLabel` | Enumerated value; see the enum table above. |
| `nearest_level_type` | `LevelType` | Whether the nearest level of any kind is support or resistance. |
| `nearest_level_usd_per_oz` | `float` | Price of that nearest level. |
| `distance_to_nearest_level_pct` | `float` | Absolute distance from close to the nearest level, in percent. |
| `realised_vol_1m_pct` | `float` | Annualised realised volatility over the last 21 sessions, in percent. |
| `implied_vol_1m_pct` | `float` | 1-month at-the-money implied volatility, in percent. |
| `vol_spread_pct` | `float` | implied_vol_1m_pct minus realised_vol_1m_pct, in volatility points. |
| `price_history` | `list[PriceBar]` | Daily bars ending on the report date, oldest first. Long enough to draw the 200-day moving average. |

**`TechnicalLevel`** — A single support or resistance level.

| field | type | meaning |
|---|---|---|
| `level_type` | `LevelType` | Enumerated value; see the enum table above. |
| `price_usd_per_oz` | `float` | — |
| `label` | `str` | Short human label, e.g. "prior range low", "38.2% retracement". |
| `distance_pct` | `float` | Signed distance from the current close to this level, in percent of the close; positive when the level is above the market. |

**`PriceBar`** — One daily OHLC bar of spot history, USD per troy ounce.

| field | type | meaning |
|---|---|---|
| `session_date` | `date` | — |
| `open_usd_per_oz` | `float` | — |
| `high_usd_per_oz` | `float` | — |
| `low_usd_per_oz` | `float` | — |
| `close_usd_per_oz` | `float` | — |

### Section 4 — ETF holdings and flows

**`EtfSection`** — Section 4. Physically backed ETF holdings and flows.

| field | type | meaning |
|---|---|---|
| `as_of_date` | `date` | Effective date of the holdings figures (report date minus one session). |
| `reporting_lag_note` | `str` | Human-readable note explaining the T+1 reporting lag. |
| `funds` | `list[EtfFundFlow]` | — |
| `metal_aggregates` | `list[EtfMetalAggregate]` | Enumerated value; see the enum table above. |

**`EtfFundFlow`** — Holdings and flows for one exchange traded product.

| field | type | meaning |
|---|---|---|
| `ticker` | `str` | Listing ticker, or "OTHER" for the aggregate line. |
| `fund_name` | `str` | — |
| `metal` | `Metal` | Enumerated value; see the enum table above. |
| `holdings_tonnes` | `float` | Total metal held, in metric tonnes. |
| `daily_change_tonnes` | `float` | Change in holdings vs the prior report, in tonnes; positive is a creation. |
| `daily_change_usd` | `float` | Daily change valued at the session close, in USD; sign matches tonnes. |
| `aum_usd` | `float` | Assets under management in USD. |
| `wtd_flow_tonnes` | `float` | Week-to-date cumulative flow in tonnes; signed. |
| `mtd_flow_tonnes` | `float` | Month-to-date cumulative flow in tonnes; signed. |
| `ytd_flow_tonnes` | `float` | Year-to-date cumulative flow in tonnes; signed. |
| `ytd_flow_usd` | `float` | Year-to-date cumulative flow valued in USD; signed. |

**`EtfMetalAggregate`** — All tracked funds in one metal, summed.

| field | type | meaning |
|---|---|---|
| `metal` | `Metal` | Enumerated value; see the enum table above. |
| `holdings_tonnes` | `float` | — |
| `daily_change_tonnes` | `float` | — |
| `daily_change_usd` | `float` | — |
| `wtd_flow_tonnes` | `float` | — |
| `mtd_flow_tonnes` | `float` | — |
| `ytd_flow_tonnes` | `float` | — |
| `aum_usd` | `float` | — |

### Section 5 — open interest and positioning

**`PositioningSection`** — Section 5. Exchange open interest, COT positioning and EFP levels.

| field | type | meaning |
|---|---|---|
| `contracts` | `list[ComexContractActivity]` | — |
| `cot` | `list[CotManagedMoney]` | — |
| `cot_report_date` | `date` | Survey date shared by the COT lines, surfaced for the heading. |
| `cot_lag_days` | `int` | Calendar days between cot_report_date and the report date. |
| `efp` | `list[EfpLevel]` | — |
| `any_efp_flagged` | `bool` | True when at least one EFP is outside its recent range. |

**`ComexContractActivity`** — Open interest and volume for one COMEX contract.

| field | type | meaning |
|---|---|---|
| `contract_code` | `str` | Exchange root, e.g. "GC", "SI", "PL", "PA". |
| `metal` | `Metal` | Enumerated value; see the enum table above. |
| `contract_size_oz` | `float` | Troy ounces per contract. |
| `open_interest_lots` | `int` | Total open interest in contracts. |
| `open_interest_change_lots` | `int` | Day-on-day change in open interest, in contracts; signed. |
| `session_volume_lots` | `int` | Session volume in contracts. |
| `volume_20d_average_lots` | `int` | Trailing 20-session average volume in contracts. |
| `volume_vs_20d_average_pct` | `float` | Session volume as a percent deviation from the 20-day average; signed. |
| `front_month_code` | `str` | Front month, e.g. "GCZ6". |
| `front_month_expiry_date` | `date` | — |
| `next_active_month_code` | `str` | Next active delivery month code. |
| `next_active_expiry_date` | `date` | — |

**`CotManagedMoney`** — Managed money positioning from the CFTC Commitments of Traders report.

| field | type | meaning |
|---|---|---|
| `metal` | `Metal` | Enumerated value; see the enum table above. |
| `report_date` | `date` | Tuesday the COT position was surveyed. |
| `published_date` | `date` | Friday the report was released by the CFTC. |
| `managed_money_long_lots` | `int` | — |
| `managed_money_short_lots` | `int` | — |
| `managed_money_net_lots` | `int` | Long minus short, in contracts; signed. |
| `net_change_wow_lots` | `int` | Week-on-week change in the net position, in contracts; signed. |
| `net_oz` | `float` | Net position converted to troy ounces using contract_size_oz. |

**`EfpLevel`** — Exchange for physical level for one metal, USD per troy ounce.

| field | type | meaning |
|---|---|---|
| `metal` | `Metal` | Enumerated value; see the enum table above. |
| `efp_usd_per_oz` | `float` | Front-month EFP: futures minus loco London spot; signed. |
| `recent_range_low_usd_per_oz` | `float` | Low of the trailing 20-session EFP range. |
| `recent_range_high_usd_per_oz` | `float` | High of the trailing 20-session EFP range. |
| `outside_recent_range` | `bool` | True when efp_usd_per_oz sits outside the trailing range — a dislocation flag. |

### Section 6 — physical inventories

**`PhysicalSection`** — Section 6. Inventories, regional premiums and lease rates.

| field | type | meaning |
|---|---|---|
| `comex_stocks` | `list[ComexStocks]` | — |
| `lbma_vault_holdings` | `list[LbmaVaultHolding]` | — |
| `lbma_monthly_note` | `str` | Human-readable note explaining the monthly LBMA publication lag. |
| `sge` | `list[SgeActivity]` | — |
| `loco_premiums` | `list[LocoPremium]` | — |
| `lease_rates` | `list[LeaseRate]` | — |

**`ComexStocks`** — COMEX depository stocks for one metal, in troy ounces.

| field | type | meaning |
|---|---|---|
| `metal` | `Metal` | Enumerated value; see the enum table above. |
| `registered_oz` | `float` | Registered (deliverable) stocks. |
| `eligible_oz` | `float` | Eligible (warranted but not offered) stocks. |
| `total_oz` | `float` | registered_oz plus eligible_oz. |
| `registered_change_oz` | `float` | Day-on-day change in registered stocks; positive is metal in. |
| `eligible_change_oz` | `float` | Day-on-day change in eligible stocks; positive is metal in. |
| `total_change_oz` | `float` | Day-on-day change in total stocks; signed. |

**`LbmaVaultHolding`** — LBMA London vaulted holdings for one metal.

| field | type | meaning |
|---|---|---|
| `metal` | `Metal` | Enumerated value; see the enum table above. |
| `holdings_tonnes` | `float` | Vaulted metal in London, in tonnes. |
| `month_change_tonnes` | `float` | Change vs the prior published month, in tonnes; signed. |
| `month_change_pct` | `float` | The same change in percent; signed. |
| `as_of_month_end` | `date` | Month-end the holdings refer to. |

**`SgeActivity`** — Shanghai Gold Exchange withdrawals and the Shanghai premium.

| field | type | meaning |
|---|---|---|
| `metal` | `Metal` | Enumerated value; see the enum table above. |
| `withdrawals_tonnes` | `float` | Metal withdrawn from SGE vaults over the reporting week, in tonnes. |
| `withdrawals_period_days` | `int` | Length of the withdrawal reporting period, in days. |
| `premium_usd_per_oz` | `float` | Shanghai price versus loco London in USD per troy ounce; positive is a premium, negative a discount. |
| `premium_pct` | `float` | The same premium as a percent of loco London; signed. |

**`LocoPremium`** — Physical premium in one location versus loco London.

| field | type | meaning |
|---|---|---|
| `location` | `str` | Trading centre, e.g. "Zurich", "Singapore". |
| `metal` | `Metal` | Enumerated value; see the enum table above. |
| `premium_usd_per_oz` | `float` | Premium over loco London in USD per troy ounce; negative is a discount. |

**`LeaseRate`** — Metal lease rates for one metal, annualised percent.

| field | type | meaning |
|---|---|---|
| `metal` | `Metal` | Enumerated value; see the enum table above. |
| `lease_rate_1m_pct` | `float` | 1-month lease rate, annualised percent. |
| `lease_rate_3m_pct` | `float` | 3-month lease rate, annualised percent. |

### Section 7 — look ahead

**`LookAheadSection`** — Section 7. Next session and next week.

| field | type | meaning |
|---|---|---|
| `next_session_date` | `date` | — |
| `next_session_events` | `list[CalendarEvent]` | — |
| `next_week_start_date` | `date` | — |
| `next_week_end_date` | `date` | — |
| `next_week_events` | `list[CalendarEvent]` | — |
| `roll_windows` | `list[ContractRollWindow]` | — |
| `holidays` | `list[CalendarEvent]` | Holiday entries affecting London, New York or Shanghai liquidity. |

**`CalendarEvent`** — One dated entry in the forward calendar.

| field | type | meaning |
|---|---|---|
| `event_date` | `date` | — |
| `event_time_london` | `str \| None` | Time of day in London as "HH:MM" (24h), or null for all-day entries. |
| `category` | `EventCategory` | Enumerated value; see the enum table above. |
| `region` | `str` | Market affected, e.g. "US", "UK", "Euro area", "China". |
| `event_name` | `str` | — |
| `consensus` | `str \| None` | Consensus expectation as displayed text, including its unit; null if none. |
| `previous` | `str \| None` | Prior reading as displayed text; null if none. |
| `importance` | `EventImportance` | Enumerated value; see the enum table above. |
| `note` | `str \| None` | Desk note, e.g. which metal is most exposed. |

**`ContractRollWindow`** — First notice, expiry and roll window for one COMEX contract.

| field | type | meaning |
|---|---|---|
| `metal` | `Metal` | Enumerated value; see the enum table above. |
| `contract_code` | `str` | Full contract code, e.g. "GCZ6". |
| `first_notice_date` | `date` | COMEX first notice day for the delivery month. |
| `last_trade_date` | `date` | Final trading day of the contract. |
| `roll_window_start_date` | `date` | — |
| `roll_window_end_date` | `date` | — |

### Commentary

**`Commentary`** — Analyst free text, persisted per report date.

| field | type | meaning |
|---|---|---|
| `report_date` | `date` | — |
| `author_name` | `str` | Analyst who wrote the commentary. |
| `headline` | `str` | One-line headline for the email subject area. |
| `market_overview` | `str` | Top-level paragraph. |
| `client_flows` | `str` | — |
| `risk` | `str` | — |
| `technicals` | `str` | — |
| `etf_flows` | `str` | — |
| `positioning` | `str` | — |
| `physical` | `str` | — |
| `look_ahead` | `str` | The "what we are watching" box. |
| `saved_at_london` | `datetime \| None` | When the draft was last saved; null if never saved. |


## Swapping mock data for live feeds

Everything the report displays comes through one seam: the `DataProvider`
protocol in `data/provider.py`, with one method per section.

1. Implement the eight methods in `data/live_provider.py`. Each already carries
   a docstring naming the likely source, its publication timing and the joins
   involved — Refinitiv/LSEG and the LBMA for prices and auctions, internal
   trade capture and the CRM for flows, the risk engine and product control for
   section 2, issuer files for ETFs, the CME daily bulletin and the CFTC COT for
   positioning, CME depository statistics and LBMA vault data for physical, and
   an economic calendar vendor for the look-ahead.
2. Set `USE_MOCK = False` in `config.py`.

That is the whole change. `get_provider()` imports the implementation lazily, so
the unused one — and in production its client libraries — never loads. The stub
already satisfies the protocol structurally, so the switch type checks today and
fails loudly at runtime until each method is filled in.

Implementations must be **pure with respect to the report date**: two calls for
the same date return equal data. The mock provider gets this from a date-derived
seed; a live provider gets it from the fact that an end-of-day snapshot is
immutable once the session has closed.

### How the mock data stays plausible

Prices are drawn inside the anchors in `config.PRICE_ANCHORS` — gold
$3,300–3,500, silver $38–42, platinum $1,200–1,400, palladium $1,000–1,200 —
and everything else is derived from them rather than fabricated separately. ETF
flows are valued at the session close, risk notionals divide by it, EFP quotes
sit on top of it, and limit utilisation falls out of the positions. Randomness
is seeded from `(report_date, stream_name, MOCK_SEED_SALT)` through `crc32`
rather than `hash()`, which Python salts per process; the same date renders the
same report in every process, and the streams are independent, so changing one
section never shifts the numbers beside it.

To re-anchor the whole app to a different market, edit `PRICE_ANCHORS`. To
re-roll every number without moving the date, change `MOCK_SEED_SALT`.

## The handoff bundle

`python export_schema.py` writes into `schema/`:

* `<ModelName>.schema.json` — JSON Schema for all 32 contract models, straight
  from `model_json_schema()`, descriptions included.
* `sample_payload.json` — one full day of fabricated data serialised from
  `EodReport`, to deserialise against. It round-trips through
  `EodReport.model_validate` unchanged.
* `sample_commentary.json` — a filled `Commentary`, matching what the app
  writes to `commentary/{YYYY-MM-DD}.json`.
* `index.json` — the model list, root model, provider and report date, so the
  bundle is self-describing.

## The email

`report/render.py` formats every number and picks every colour, then assembles a
plain view model of blocks — `table`, `notes`, `image` — which
`report/template.html.j2` places into HTML. The template contains no domain
logic, so reproducing the email in Rust means reproducing that view model.

The output is one self-contained HTML string: table-based layout, inline styles
on every element, no `<style>` block, no classes, no flexbox or grid, no
JavaScript, no external stylesheets and no remote images. Maximum width 800px,
Arial/Helvetica throughout, Outlook assumed as the worst case. Numbers are
right-aligned with thousands separators and per-instrument decimals; green and
red appear only on directional figures.

Charts embed as base64 PNGs when `config.EMBED_CHARTS_IN_EMAIL` is true and
kaleido can render them. When kaleido is absent — or has no Chrome binary to
drive — the images are dropped silently and the tables carry the same data.

Commentary is optional everywhere. An empty box produces no heading, no
spacing and no trace in the email.

`report/send.py.example` shows the intended delivery interface,
`send_report(html, recipients, subject)`, with the implementation commented out.
Nothing in the prototype sends mail.

## Assumptions

Choices made where the brief left a convention open. All follow market practice;
each is worth a second look before the production build.

* **Silver's auction.** Silver has one daily auction rather than an AM and a PM,
  so its noon price is reported in `lbma_pm_auction_usd_per_oz`.
* **VaR.** Reported per metal as a standalone figure plus a diversified
  desk-level number, which is lower than their sum by the assumed cross-metal
  correlation (`VAR_CROSS_METAL_CORRELATION`, 0.60).
* **EFP.** Quoted as front-month futures minus loco London spot, in USD per
  troy ounce, and flagged when it sits outside its trailing 20-session range.
* **Delta-equivalent.** `delta_equivalent_oz` is the outright position plus the
  options book's delta, so `position_oz + OptionsGreeks.delta_oz` ties to it.
* **Client flow sign.** Positive is a client buy, because the section is written
  from the desk's view of who did what, not from the desk's own book.
* **COT timing.** Surveyed on a Tuesday and published the following Friday; the
  report shows the most recent survey whose publication has already happened,
  with `cot_report_date` and `cot_lag_days` surfaced so nobody reads a week-old
  number as today's.
* **First notice day** is the last business day of the month before delivery;
  last trade day is approximated as the third-to-last business day of the
  delivery month. The roll window opens six business days before first notice
  (`ROLL_WINDOW_BUSINESS_DAYS`).
* **Percentages** are never fractions: `12.5` means 12.5% everywhere, on the
  wire and on the screen.
* **Business days** are weekdays. Market holidays are surfaced in the look-ahead
  but do not shift the price history or the contract calendar.

## Known simplifications

Things a production build has to deal with that this prototype does not.

* **Reporting lags are modelled but not reconciled.** ETF holdings are T+1, the
  CFTC COT is a weekly Tuesday survey published on the Friday, LBMA vault
  holdings are monthly and roughly three months in arrears, and SGE withdrawals
  are weekly. Each model carries its own effective date; nothing tries to
  align them onto a single as-of date, because they genuinely do not align.
* **No FX layer.** Everything is USD. There is no conversion, no fixing source
  and no non-USD reporting currency.
* **No intraday data.** The session is a single OHLC bar. The snapshot's high
  and low come from that bar, not from a tick history.
* **Moving averages are simple, not exponential**, and the support/resistance
  levels are derived from rolling extremes, round numbers and the moving
  averages themselves. A desk's published levels are usually a person's
  judgement; if that is the intent, they should become an input, not a
  calculation.
* **The look-ahead calendar is fabricated from templates.** Consensus figures
  are plausible strings, not a vendor feed, and the holiday table is
  year-agnostic, so moveable feasts (Easter, Lunar New Year) are approximate.
* **Phone width.** The email's natural minimum is about 557px because of the
  wide data tables, so a phone client scales it to roughly 70%. Getting to a
  true 390px would need either media queries — ruled out by the inline-CSS-only
  constraint — or dropping columns. The skim path at the top (headline,
  snapshot strip, market overview) fits without scaling. If mobile ever
  outranks Outlook, add a `<style>` block with `@media` rules and stack the
  tables.
* **Data-URI images.** Some Outlook desktop configurations block base64 images.
  If that shows up in testing, switch the renderer to `cid:` attachments in
  `send.py` rather than changing the template.
* **No authentication, no audit trail, no archive.** Commentary is a local JSON
  file. A real desk report needs authorship, versioning and journalling.
* **Single analyst, single desk.** No multi-user editing, no locking, and no
  notion of which desk or book the numbers belong to.
