# Plan: Incorporate "Probability of Real Loss by Holding Period" into Allocation Optimization

## 1. What the chart teaches, and why it maps onto *this* system

The Discipline Funds chart plots the probability of a **real (inflation-adjusted) loss**
against **holding period** for four sleeves. Its four lessons are really four allocation
rules that depend on *time*, not on a static risk score:

| Lesson (from chart) | Allocation implication |
|---|---|
| 1. Cash is safe short-term, **risky long-term** (real-loss prob rises with horizon) | Money not needed for a long time should **not** sit in cash. |
| 2. Stocks are risky short-term, **safe(r) long-term** | Long-horizon dollars belong in equities. |
| 3. Long bonds barely beat intermediate bonds on safety (bond curve is nearly flat) | Don't reach for duration to buy safety; short-intermediate is enough. |
| 4. A 60/40 blend improves **intermediate-term** safety while keeping long-term safety | For mid-horizon dollars, blend beats a cash/stock barbell. |

The key unlock the user identified: **the cash-flow forecast already knows the holding
period of every dollar.** The deterministic engine draws down accounts in a defined
cascade (HSA → pre-tax elective → taxable/trust → Roth → home equity) and records
per-account, per-year withdrawals (`row['_account_withdrawals']`,
`_trust_by_account`, `_pretax_elective_by_account`, etc. in
`src/projection_stages/deterministic_engine.py`). From that we can build a
**liability schedule** — how many real dollars leave the portfolio in each future
year — and therefore a **holding-period distribution** of today's balance. That is
exactly the x-axis of the chart. Today the optimizer instead uses a **single manual
global horizon** (`capital_market_config['horizon_years']`, one of 1/3/5/10/20/25/30),
which is a blunt proxy for what the projection can compute precisely.

## 2. Current state we build on (no rework needed)

- **`src/optimization.py`** — `compute_optimal_allocation(c, force_mode)` supports
  `user_target`, `optimizer_recommendation`, `max_sharpe`, `tangency`. It already:
  - scales expected return/volatility **by horizon** via `_horizon_adjustment()` and
    `apply_capital_market_config()` (short horizons de-rate equity return, inflate vol);
  - has per-class caps/bounds (`_asset_class_bounds`, `EQUITY_SLEEVE_CLASS_CAPS`,
    `TANGENCY_CLASS_CAPS`) and a pluggable objective (`optimize_equity_sleeve`,
    `objective_mode`);
  - resolves eligible classes through Include / Exclude / Consider-alternate-first and
    non-liquid coverage.
- **Horizon machinery already exists** — we can *feed it a computed number* instead of a
  manual pick, which is the smallest-footprint integration point.
- **Liquidity buffer already exists** — `c['liquidity_buffer_schedule']`,
  `near_term_buffer_years`, `long_term_buffer_years` (data_io.py ~986–1031) and
  `liquidity_buffer_years_for_year()` in the engine. This is the natural home for the
  "cash is safe short-term" floor.
- **Reference-data pattern exists** — `reference_data/capital_market_assumptions.csv` and
  `asset_correlations.csv` are loaded by horizon/preset. Real-loss curves can ship the
  same way (editable, horizon-keyed), so nothing is hardcoded.
- **Testing guardrails** — frozen pricing via `RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1`
  (see memory `testing_frozen_pricing`) and golden-master tests
  (`tests/test_183_efficient_frontier_sharpe.py`, `test_184_max_sharpe_tangency_allocation.py`).

## 3. New building block A — Real-loss-probability curves (reference data)

Ship `reference_data/real_loss_probability.csv`, digitized from the chart and editable
like the CMAs:

```
asset_class,holding_years,real_loss_prob,notes
Cash,0,0.08
Cash,3,0.14
...
US Large Cap,0,0.38
...
Bonds,0,0.22          # "short-intermediate real bonds" curve
Blend 60-40,0,0.28
```

- Map each optimizer asset class to a curve (equities → equity curve; Bonds/Short-Term
  Bonds/TIPS/Muni → bond curve; Cash → cash curve; blends interpolate). Store the mapping
  next to `ASSET_CLASS_CATEGORIES` in `allocation_policy.py`.
- New module `src/real_loss_curves.py`: `load_real_loss_curves(c)` and
  `real_loss_prob(asset_class, holding_years)` with monotone interpolation between the
  chart's node years (0,3,5,7,9,11,13,15,17,19,21).
- Curves are **planning assumptions, not forecasts** — same disclaimer language as the
  CMA block. Advanced users can override via CSV, mirroring
  `_load_capital_market_assumption_rows`.

## 4. New building block B — Holding-period profile from the projection

New module `src/holding_period.py`:

- `withdrawal_liability_schedule(rows, c)` → `{year_offset: real_dollars_withdrawn}`
  built from the projection's per-year net portfolio outflow (gap funded by withdrawals,
  net of income), deflated to today's dollars using the plan inflation path.
- `holding_period_profile(rows, c)` → assigns today's liquid balance to holding-period
  buckets by matching the liability schedule **FIFO in withdrawal-cascade order**
  (near-term dollars are spent first): produces
  `{bucket: {'dollars':…, 'avg_holding_years':…, 'share':…}}` for buckets
  e.g. `0–2, 3–5, 6–10, 11–15, 16+`.
- `withdrawal_weighted_horizon(rows, c)` → single dollar-weighted mean holding period
  (the scalar that feeds §5a).
- Guard the degenerate/accumulation case (no withdrawals yet, or inflows > outflows):
  fall back to `plan_end - now` so behavior is unchanged for young accumulators.

This is read-only over an already-computed projection — it does **not** change the
projection itself, avoiding golden-master drift in the cash-flow numbers.

## 5. Integration into the optimizer — three levers, phased

Ordered smallest-blast-radius → deepest. Each phase is independently shippable.

### 5a. Auto-derive the planning horizon (smallest change, high value)
- Add `capital_market_config['horizon_source']` = `manual` (default, unchanged) |
  `auto_from_withdrawals`.
- When `auto`, set the effective horizon from `withdrawal_weighted_horizon()` (snapped to
  the nearest supported horizon) **before** `apply_capital_market_config()`. Everything
  downstream (return/vol de-rating) then reflects the household's real spend timeline
  instead of a guessed global number.
- Delivers lessons 1 & 2 immediately through existing machinery: a household spending
  down over 5 years gets short-horizon de-rated equity assumptions; a legacy-oriented
  household with a 25-year effective horizon gets long-horizon assumptions.

### 5b. Time-segmented real-loss floors (delivers lessons 1, 3, 4)
- For each near-term bucket from `holding_period_profile`, look up the **max tolerable
  real-loss probability** (`c['max_real_loss_prob_by_bucket']`, default e.g. 15%).
- Translate to floors/caps fed into `_asset_class_bounds` for the recommendation modes:
  - `0–2 yr` share → **minimum Cash / Short-Term Bonds** weight (chart: only cash/short
    bonds clear a low real-loss bar at short horizons). This generalizes / can *derive*
    `near_term_buffer_years` instead of it being a manual input.
  - `16+ yr` share → **minimum growth** weight (equities clear the bar at long horizons;
    cash fails it → cap cash).
  - Mid buckets → prefer **blend** (lesson 4): don't force a barbell; keep bounds loose so
    the mean-variance/Sharpe solve lands on a diversified mix. Lesson 3 → keep long-bond
    (`Bonds`) ceiling modest vs `Short-Term Bonds`, since duration buys little extra safety.
- Applied as **bounds**, so it composes with the existing SLSQP solve, per-class user
  overrides, and coverage logic already in `_asset_class_bounds`.

### 5c. Real-loss-probability objective term (deepest, optional)
- New `objective_mode='real_loss_aware'` in `optimize_equity_sleeve` /
  `compute_optimal_allocation`, plus a new `ALLOCATION_MODE_REAL_LOSS_AWARE` in
  `allocation_policy.py` (`"Use holding-period real-loss-aware allocation"`).
- Objective adds a penalty = Σ_bucket share_bucket · Σ_class w_class ·
  `real_loss_prob(class, bucket_mid_years)`, i.e. minimize the **holding-period-weighted
  probability of a real loss** alongside (or instead of) variance. This is the most direct
  encoding of the chart, but it introduces a new recommendation mode and needs its own
  golden master — hence last.

**Recommendation:** ship **5a + 5b** first (they reuse existing horizon + bounds +
buffer machinery, are explainable, and cover all four lessons), and treat **5c** as a
follow-up "expert" mode once 5a/5b are validated in reports.

## 6. Reporting & education (make the lesson visible)

- New workbook section (follows the `sheets_*` pattern, e.g. alongside
  `sheets_projection_charts.py` / efficient-frontier work in item 183): reproduce the
  chart's four curves and **overlay this household's holding-period profile** and the
  resulting allocation, so the client sees *why* near-term dollars are in cash and
  long-term dollars in equities.
- Extend the optimizer `diagnostics` dict with `holding_period_profile`,
  `withdrawal_weighted_horizon`, `horizon_source`, per-bucket max-real-loss inputs, and
  which floors/caps were triggered — same disclosure style as existing diagnostics.
- Add a plain-language note (like `OPTIMIZER_RECOMMENDATION_COMMENT`) explaining the
  holding-period logic and the four lessons.

## 7. Config / UI surface

- `system_config.csv` / `client_data.*`: `horizon_source`, `max_real_loss_prob_by_bucket`,
  bucket edges, `real_loss_curves_file`, and a master toggle
  `holding_period_allocation_enabled` (default **off** so existing plans are byte-stable
  until opted in).
- Schema registration in `schema_registry.py` / `reference_data/schema.csv`, and the
  allocation-policy admin UI (`frontend/js/dashboard_assets_module.js`,
  `strategy_assets` service) gets the new mode + inputs, mirroring how the Sharpe/tangency
  modes were surfaced.

## 8. Testing

- Unit: `real_loss_curves` interpolation/monotonicity; `holding_period` schedule &
  bucketing on synthetic projections (spend-down, accumulator, legacy).
- Integration: new golden masters for 5b (and 5c if built) under frozen pricing
  (`RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1`); assert existing modes are
  **unchanged** when `holding_period_allocation_enabled` is off.
- Guard against the known "pytest mutates input files" issue (memory
  `pytest_mutates_input_files`) — check `git status` on `input/` after runs.

## 9. Phasing summary

1. **Phase 1** — reference curves (§3) + holding-period module (§4) + diagnostics only.
   No allocation change yet; purely additive and observable in reports. Lowest risk.
2. **Phase 2** — 5a auto-horizon (behind `horizon_source=auto`).
3. **Phase 3** — 5b real-loss floors + educational workbook chart (§6).
4. **Phase 4 (optional)** — 5c real-loss-aware objective mode.

## 10. Open decisions for the user

- **Scope/aggressiveness:** educational overlay only (Phase 1), soft influence
  (Phases 1–3, *recommended*), or full new optimizer mode (all phases)?
- **Default posture:** ship opt-in/off (byte-stable, recommended) vs on-by-default.
- **Buffer relationship:** should the derived near-term bucket **replace** the manual
  `near_term_buffer_years` input, or only cross-check/inform it?
```
