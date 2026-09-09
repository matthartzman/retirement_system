# Housing optimization — design

**Date:** 2026-09-09 · **Status:** design, approved · **Revision:** 1

**Scope:** given the current home, recommend the sale year, next-purchase year (or "rent
indefinitely"), and location for the household's next housing move, as a new action inside the
existing housing scenario manager.

**Stated assumptions and decisions:**
- **Reuses the real simulation/tax engine** for every candidate — no parallel or approximate tax
  model is built. All tax factors in scope (state income tax by residency, property tax, §121
  capital-gains exclusion, mortgage-interest/property-tax itemized deduction, estate tax, retirement
  income tax) are already produced by the existing engine and are covered "for free" by this reuse.
- **Search is a full grid** over (sale year × purchase year × candidate location), plus a
  rent-indefinitely branch per location, bounded by a user-set search window. No narrowed/gradient
  search in v1.
- **Objective is user-selectable** via a dropdown: ending net worth / plan longevity, lifetime
  after-tax housing cost, or Monte Carlo success rate.
- **Two-pass execution:** deterministic engine ranks the full grid; Monte Carlo re-runs only the
  top 3–5 candidates to produce a reliable success-rate figure.
- **"Never own two homes" is a default-on toggle**, not a hard-coded rule — sale year ≤ purchase
  year for every candidate unless the user relaxes it.
- **Family-presence is a hard filter**, not a soft objective penalty: a candidate is dropped if it
  leaves the designated region without an owned-or-rented residence during the required window.
- **Ships as a new action in the existing scenario manager** (`dashboard_decomp_housing_scenarios.js`),
  not a separate top-level page.

---

## 1. What exists today, and what this adds

The engine already models nearly everything a housing optimizer needs — it has never been exposed
as a *search*:

| Piece | Where | What it does |
|---|---|---|
| Home sale, appreciation, mortgage payoff, HELOC | `src/projection_stages/home_sale.py` | `apply_home_sale`, `resolve_home_sale_gain_tax`; §121 exclusion via `c['sec121']` |
| Next-home purchase cashflow | `src/projection_stages/deterministic_engine.py:150-199` | Down payment, amortized mortgage, appreciated value/equity, property tax, insurance, HOA |
| State tax by location/year | `src/core.py` (`state_for_year`) | Reads `residency_schedule` — a list of `{state, start_year, end_year}` rows |
| Mortgage-interest & property-tax (SALT) itemized deduction | `src/projection_stages/roth_conversion_and_agi_tax.py:625-727` | Standard-vs-itemized comparison already includes `mort_interest_schedule` and `real_estate_tax_yr`, capped by `salt_cap` |
| Location cost estimates | `src/server_services/strategy_asset_service.py:94-138` (`housing_state_estimate_v1`) | Purchase/rent cost estimates by state/city-type/population |
| Manual scenario comparison | `frontend/js/dashboard_decomp_housing_scenarios.js` | `SCENARIO_TEMPLATES`, scenario sets, a "Sell Home" stress-test panel — scenario-sheet-only today |

**The gap:** nothing today searches across candidate sale/purchase years or locations and ranks
them — a user has to hand-build one scenario at a time. This feature is an orchestration layer that
builds many candidate configs, runs the existing engine on each, and ranks the results. It adds no
new tax logic.

---

## 2. Inputs

New fields, entered in the scenario-manager UI:

- **Candidate locations** (2–4): each `{state, city_type, population_size, target_purchase_price_range}`.
  Pre-fillable from `housing_state_estimate_v1`.
- **Search window**: `{earliest_sale_year, latest_sale_year, earliest_purchase_year, latest_purchase_year}`,
  bounding the grid.
- **`no_dual_ownership`** (bool, default `true`): when true, only candidates with
  `sale_year <= purchase_year` are evaluated.
- **`family_presence`**: `{region, start_year, end_year}` (optional). When set, a candidate is
  dropped unless an owned-or-rented residence covers the entire window in that region — this can be
  satisfied by the current home, a rental, or the next-purchased home.
- **Objective** (dropdown): `net_worth` | `lifetime_cost` | `mc_success_rate`.
- **Rent-indefinitely** is not a separate input — it is generated automatically as one candidate per
  location (sale_year set, no purchase).

---

## 3. Candidate generation and constraints

For each location, and each `(sale_year, purchase_year)` pair in the bounded grid, plus the
rent-indefinitely branch:

1. Build a plan config variant by rewriting:
   - `next_housing_steps` — a sale event (routed through `home_sale.py`) and, unless
     rent-indefinitely, a purchase event (routed through the existing next-housing-step cost model
     in `deterministic_engine.py`).
   - `residency_schedule` — so `state_for_year` reflects the candidate's location from
     `purchase_year` (or `sale_year`, for rent-indefinitely) onward.
2. Filter out:
   - candidates violating `no_dual_ownership`,
   - candidates that leave `family_presence.region` uncovered for any year in its window,
3. **Do not** drop candidates that fail the §121 two-of-five-year ownership/use test — evaluate them
   normally (the engine's existing `sec121` logic already withholds the exclusion when the test
   fails), and flag them in the results table so the user can see the exclusion was lost.

No new tax modeling is introduced in this step. Every tax figure a candidate produces (state income
tax, property tax/SALT, itemized-vs-standard deduction, §121 gain tax, estate tax, ordinary
retirement income tax) comes from the unmodified engine acting on the rewritten config.

---

## 4. Execution: two-pass ranking

**Pass 1 — deterministic ranking.** Run the existing deterministic engine once per surviving
candidate. Score each by the selected objective:
- `net_worth`: ending net worth (or portfolio-survival horizon) at plan end.
- `lifetime_cost`: total after-tax housing-attributable cost over the plan horizon (mortgage
  interest, property tax, insurance, HOA, rent payments, minus any home-equity growth realized at
  sale) — computed from the same run's existing cashflow breakdown, not a separate cost model.
- `mc_success_rate`: not computed in Pass 1; Pass 1 falls back to `net_worth` to produce a
  provisional ranking so Pass 2 has a shortlist to work from.

**Pass 2 — Monte Carlo validation.** Re-run full Monte Carlo on the top 3–5 candidates from Pass 1
(top 3–5 by whichever score Pass 1 produced). If the selected objective is `mc_success_rate`,
re-rank this shortlist by the resulting success rate; the final recommendation is the top of that
re-ranked shortlist. For the other two objectives, Pass 2 still runs (as a confidence check) but does
not change the ranking.

Grid size should be capped (e.g., by the search-window inputs) to keep Pass 1 runtime reasonable;
this is a UI-level bound, not a new engine feature.

---

## 5. Output

- **Headline recommendation:** sale year, purchase year (or "Rent indefinitely"), location, and the
  objective's value for that candidate.
- **Ranked alternatives table:** next 5–10 candidates by score, same fields, plus a flag column for
  "lost §121 exclusion" and "family-presence: satisfied via rental" where relevant.
- Surfaces as a new "Optimize" action in the existing scenario manager, next to the current manual
  "Sell Home" scenario templates — reuses that panel's existing scenario-diffing display rather than
  introducing a new results UI.

---

## 6. New surface area

- **`src/housing_optimizer.py`** (new): candidate generation, constraint filtering, two-pass runner,
  scoring, ranking. Calls into `home_sale.py`, `deterministic_engine.py`, and the Monte Carlo runner
  as-is — no changes to those modules' tax logic.
- **New API endpoint**, e.g. `POST /api/housing/optimize`: accepts the inputs in §2, returns the
  output in §5.
- **Frontend**: new panel in `dashboard_decomp_housing_scenarios.js` — location list, search-window
  inputs, objective dropdown, family-presence region/dates, `no_dual_ownership` toggle, and the
  results table.

---

## 7. Out of scope for v1

- Narrowed/gradient search — full grid only.
- Optimizing over more than one "next home" simultaneously (e.g., planning a chain of three future
  moves) — this feature optimizes one transition (current home → next home/rent) at a time.
- New tax modeling of any kind — every tax factor in scope is already produced by the existing
  engine (see §1); if a future request needs a tax treatment the engine doesn't have, that is a
  separate spec.
