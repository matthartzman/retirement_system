# Alternative-asset gain tax, and the Change breakdown on the Liquid pop-up — design and plan

Status: approved

Date: 2026-11-06. Decisions confirmed by the user the same day (see section 1).

## 1. Requests and decisions

**A. Alternative investments need their own tax treatment.** Autos stay "Not taxed". Start-up equity
(hucu.ai) and fractional art (Masterworks) are taxed on the gain, so each needs a basis and a purchase date
(held more than one year or not). This affects the Current Snapshot's non-liquid tax estimate and the
Retirement Planner's projection.

- **Single source:** the Planner's *Other Assets* rows (Assets & Protection > Other Asset Items) carry basis,
  purchase date and tax treatment. The Snapshot finds them by name, the way it already finds Notes.
  Accounts & Sources does not get a second copy of these fields.
- **Collectibles:** art and collectibles get a *Taxed on gains (collectible)* treatment (federal long-term
  rate capped at 28%). It is a choice on every Other Asset row, now and for any asset added later, and the
  default for the Art and Collectible types.

**B. The Change line on the Liquid Investments and Cash pop-up gets broken down.** Under "Change since
<date>", three lines that always add up to it:

| Line | What it holds |
|---|---|
| Deposits & withdrawals | Money in from outside the included accounts (paychecks, contributions) minus money out (spending, transfers to excluded accounts). Moves between two included accounts cancel. |
| Income less fees | Cash dividends, interest, fund capital-gain distributions and return of capital, minus fees, commissions and foreign tax withheld. Can be negative. |
| Market gain/loss | Everything else: the price change of what is held. It is the remainder, so the three lines always add up to Change. |

The words: "Gains" and "Yield" both read oddly when negative, and the user asked for terms that work
either way. *Market gain/loss* and *Income less fees* do.

## 2. What exists today (verified 2026-11-06)

- `src/parsing/client_sections.py::parse_housing_and_other_assets` reads each Other Asset (`type, name,
  value, as_of_date, annual_appreciation_pct, basis, sell_date`). It then rolls every non-vehicle item into
  one `startup_eq` total with a single `startup_sale_year`, the earliest one. **`basis` is read and never
  used.**
- `src/projection_stages/appreciation_divorce_qlac.py` deposits the sale proceeds into the first taxable
  account. **No tax is charged on the gain.**
- The Snapshot (`financial_trends_reporter/live_snapshot.py::_monarch_sections`, `compute`) classes Monarch
  "Other" rows as Alternatives with treatment `none` unless Accounts & Sources says otherwise. The
  treatments are `pre_tax | after_tax | none`, plus `note_interest`, which comes from matching a note by
  name.
- The pop-up is `financial_trends_reporter/frontend/charts.js::rolloverHtml` / `changeLineHtml`, opened
  from `index.html::showRollover` for `chartHoldings`. Snapshot log rows already carry
  `investment_flows_daily` (`{account: {day: {to_checking, from_checking}}}`).
- Broker activity rows (`src/stores/broker_repo.py`, kinds in `src/broker_activity/normalized.py`) are the
  record of investment-account dividends, interest, distributions, fees and commissions. Monarch
  transactions cover the cash accounts. The Investment-account trade and income rows are dropped on
  import (`ytd_tracking.BROKER_COVERED_CATEGORIES`).

## 3. Design

### 3.1 Other Asset fields (Phase 1)

Two new rows per Other Asset: `purchase_date` (date) and `tax_treatment` (choice). The treatments are:

| Value | Label | Default for type |
|---|---|---|
| `none` | Not taxed | Auto, Boat |
| `gains` | Taxed on gains | Start-up Equity, Other |
| `collectible_gains` | Taxed on gains (collectible) | Art, Collectible |

A blank `tax_treatment` means "use the type's default", so existing plans keep working without being
rewritten. `add_other_asset_payload` writes both rows for new assets. For existing assets, a missing row is
created the first time the plan is opened (the same path other added fields use; we confirm which one in
Phase 1). The basis help text changes to "Purchase price or tax basis (needed to tax the gain)".

**Holding period:** long-term when the sale date (Planner) or today (Snapshot) is more than one year after
`purchase_date`. With no purchase date, the asset counts as long-term and the Snapshot names it in a note,
the same way it names a missing annuity premium today. With no basis, the gain is the whole value and the
asset is named in the same note.

### 3.2 Planner engine (Phase 2)

- The parser also keeps a per-item list of taxable sales: `{name, sale_year, proceeds, basis, long_term,
  collectible}`. `startup_eq` / `startup_sale_year` stay as they are for net worth and reports, so items
  without a sale date change nothing.
- In the sale year, the AGI/tax stage computes the gain tax next to `resolve_home_sale_gain_tax`:
  - `gains`, long-term: `tax_kernel.ltcg_tax_on_gain`, stacked on ordinary taxable income.
  - `collectible_gains`, long-term: the gain at min(the marginal ordinary rate, 28%).
  - Short-term (either kind): added to ordinary taxable income.
  - NIIT and state tax on capital gains follow the existing capital-gain paths
    (`test_state_tax_on_capital_gains_engine_unit.py` pins those).
- New row fields: `other_asset_sale_gain` and `other_asset_sale_tax`. Both feed `total_tax` and appear in
  the projection tax sheet.
- At death, heirs get a stepped-up basis, so the terminal after-tax estimate adds nothing for these assets.

### 3.3 Snapshot (Phase 3)

- `planner_cfg` gains `other_asset_items`. A Monarch non-liquid row is matched to an item by name, ignoring
  case, and the row's name may start with the item's name (as with notes). An explicit Accounts & Sources
  treatment still wins.
- A matched item's `gains` or `collectible_gains` adds `max(0, value - basis)` to a new
  `alternatives_gain` bucket. It is taxed at the LTCG rate (or 28%, capped by the ordinary rate, for
  collectibles), or at the ordinary rate when short-term. The tax card gets an "Alternatives: tax on gains"
  line, and the Non-liquid table's Tax column shows the new labels.

### 3.4 Change breakdown (Phase 4)

- **Server** (`trends_metrics.py`, beside `investment_flows_daily`): `liquid_income_daily` =
  `{account: {day: amount}}`. It is built from broker activity rows of the income kinds, net of `fees` and
  `commission` and with foreign tax as a negative. Monarch cash-account transactions in the interest,
  dividend and fee categories are added in. Only days that have income are stored.
- **Client:** the deposits line is the change in the summed balance of the included accounts, minus market
  gain and income. Computed directly instead: for the window `(prior.date, date]`, sum
  `liquid_income_daily` over the included accounts (the Accounts ▾ toggles), and sum the external flows
  from the same daily ledgers that feed the flows chart, counting only flows whose other side is not an
  included account. Market gain/loss = Change − deposits − income.
- **Coverage note:** an account with no broker file has its dividends inside Market gain/loss. The pop-up
  then says "Income covers accounts with broker activity imported" and lists how many accounts it covers.
- In % view, all three lines are shown as % of the prior total.

## 4. Implementation plan

Check `/usage` after each phase against these estimates. They are relative, not token counts.

| Phase | Work | Model / effort | Usage vs a 5-hour Pro session | What drives context |
|---|---|---|---|---|
| 1 | Other Asset fields: add payload, field schema (`dashboard.js` ~4835, grep only), parser, table columns, missing-row backfill, help text, unit tests | Sonnet / medium | Light–moderate | `dashboard.js` is 7,287 lines: grep the field schema and never read it whole. `dashboard_decomp_assets_other.js` is small. |
| 2 | Engine gain tax: parser sale list, tax-stage function, row fields, tax-sheet column, engine unit tests, golden measure | Opus / high | **Heavy** | `roth_conversion_and_agi_tax.py` is large (read only around line 875). Golden drift is a risk. |
| 3 | Snapshot match + tax line + labels; tests in `test_live_snapshot_compute_unit.py` | Sonnet / medium | Light–moderate | `live_snapshot.py`: read only lines 760–1000. |
| 4 | Change breakdown: server income ledger, client window sums, 3 lines, coverage note; Node tests for `rolloverHtml`, Python unit for the ledger | Opus / medium | Moderate | `index.html` and `charts.js`, by region. Broker repo queries. |
| 5 | Verify: `tools/fast_gates.py`, diagram regen if files are added, frontend size ratchet, `pytest -m "not slow"` into a log, phase golden test, a live check in the browser pane | Sonnet / low | Moderate | Test-loop iterations. Run pytest in the background into a log. |

**Flagged as expensive:**

- **Phase 2 golden drift.** Only plans with a dated sale of a non-vehicle asset change. Run
  `tools/regen_golden_master.py measure` and `pytest tests/test_phase_golden_equality_regression.py` once.
  Hand-verify one delta (gain × rate) before any `golden_compare.py record`. Never loop regen.
- **The frontend size ratchet (`frontend/js`).** Phase 1 adds about 10 lines to `frontend/js`; offset them
  by trimming elsewhere, never by raising the ceiling. Phase 4's files are under
  `financial_trends_reporter/frontend`, so first confirm whether the ratchet covers that folder.
- **Running the full suite after every edit.** Run each phase's targeted tests, and the fast suite once per
  phase.

**Can run in parallel:** Phase 4 is independent of Phases 1–3 (different files, no shared data) and can run
in its own session. Phases 1 → 2 → 3 are sequential: 2 and 3 read the fields Phase 1 adds.

## 5. Open points, not in scope

- **QSBS (§1202).** Qualifying start-up stock held five years can exclude most or all of the gain. If
  hucu.ai qualifies, a future "QSBS excluded" treatment would be the fix. It is not modeled here.
- Losses on a sale are not deducted. Personal-use autos never are; investment losses would be a later
  refinement.
