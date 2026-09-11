# Housing optimization — design

**Date:** 2026-09-09 · **Status:** v1 shipped ([PR #109](https://github.com/matthartzman/retirement_system/pull/109)) · **Revision:** 5

**Revision 3 (2026-09-11):** v1 landed per this spec. Three implementation-time gaps were
discovered that the original design didn't anticipate — see §8. §8 also reprioritizes the
existing §7 out-of-scope list against those gaps for the next chunk of work.

**Revision 4 (2026-09-11):** §8.2 P0 landed — see the note at the end of §8.2.

**Revision 5 (2026-09-11):** §8.2 P2 landed — see the P2 note in §8.2. The full grid stays the
default (`search_mode='full'`); narrowed search is opt-in (`search_mode='narrowed'`).

**Scope:** given the current home, recommend the sale year, next-purchase year (or "rent
indefinitely"), and location for the household's next housing move — and optionally a **second**
subsequent move — as a new action inside the existing housing scenario manager.

**Stated assumptions and decisions:**
- **Reuses the real simulation/tax engine** for every candidate — no parallel or approximate tax
  model is built. All tax factors in scope (state income tax by residency, property tax, §121
  capital-gains exclusion, mortgage-interest/property-tax itemized deduction, estate tax, retirement
  income tax) are already produced by the existing engine and are covered "for free" by this reuse.
- **Search is a full grid** over (sale year × purchase year × candidate location) for move 1, plus a
  rent-indefinitely branch per location, bounded by a user-set search window. No narrowed/gradient
  search within a single move in v1.
- **A second move is supported, capped at two moves total** (current home → home/rent 2 →
  optionally home/rent 3). It is optional per candidate, not mandatory — "stop after move 1" remains
  a valid, competing outcome. Chains of three or more moves stay out of scope (§7).
- **Move 2 is searched by anchoring on move 1's winners**, not a full cross-product: Pass 1 ranks
  move-1-only candidates first, the top N of those (including their location) become anchors, and a
  move-2 grid is searched only on top of each anchor. See §4.
- **Objective is user-selectable** via a dropdown: ending net worth / plan longevity, lifetime
  after-tax housing cost, or Monte Carlo success rate. It applies to the whole plan (both moves when
  present), not per-move.
- **Two-pass execution:** deterministic engine ranks (per §4's staged approach); Monte Carlo re-runs
  only the top 3–5 final candidates to produce a reliable success-rate figure.
- **"Never own two homes" is a default-on toggle**, not a hard-coded rule — applied at every sale
  event in the timeline (sale 1 ≤ purchase 1, and sale 2 ≤ purchase 2 if move 2 exists), unless the
  user relaxes it.
- **Family-presence is a hard filter**, not a soft objective penalty: a candidate is dropped if it
  leaves the designated region without an owned-or-rented residence during the required window, at
  any point across the whole timeline.
- **The same candidate location list is used for both moves** — the household is assumed to be
  choosing among one set of areas for its remaining moves, not a distinct set per move.
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
  Pre-fillable from `housing_state_estimate_v1`. Shared across move 1 and move 2.
- **Search window for move 1**: `{earliest_sale_year, latest_sale_year, earliest_purchase_year, latest_purchase_year}`,
  bounding the move-1 grid.
- **Search window for move 2** (optional; only used if the user wants a second move considered):
  `{latest_sale_year_2, latest_purchase_year_2}`. The earliest bounds for move 2 are derived, not
  entered — sale 2 cannot precede purchase 1 (you can't sell a home you haven't bought yet), and
  purchase 2 cannot precede sale 2 unless `no_dual_ownership` is relaxed.
- **`anchor_count`** (default 5): how many top move-1 candidates are carried forward as anchors for
  the move-2 search (§4). Advanced/optional input; most users won't need to touch it.
- **`no_dual_ownership`** (bool, default `true`): when true, only candidates with
  `sale_year <= purchase_year` are evaluated, applied at both move 1 and move 2.
- **`family_presence`**: `{region, start_year, end_year}` (optional). When set, a candidate is
  dropped unless an owned-or-rented residence covers the entire window in that region — this can be
  satisfied by the current home, a rental, or either the move-1 or move-2 home.
- **Objective** (dropdown): `net_worth` | `lifetime_cost` | `mc_success_rate`.
- **Rent-indefinitely** is not a separate input — it is generated automatically as a candidate after
  move 1 (sale set, no purchase) and, if a move-2 search is run, after move 2 as well.

---

## 3. Candidate generation and constraints

### 3.1 Move-1 candidates

For each location, and each `(sale_year, purchase_year)` pair in the bounded move-1 grid, plus the
rent-indefinitely branch:

1. Build a plan config variant by rewriting:
   - `next_housing_steps` — a sale event (routed through `home_sale.py`) and, unless
     rent-indefinitely, a purchase event (routed through the existing next-housing-step cost model
     in `deterministic_engine.py`).
   - `residency_schedule` — so `state_for_year` reflects the candidate's location from
     `purchase_year` (or `sale_year`, for rent-indefinitely) onward.
2. Filter out:
   - candidates violating `no_dual_ownership`,
   - candidates that leave `family_presence.region` uncovered for any year in its window (checked
     against the full plan horizon, since a move-1-only candidate has nothing after it).
3. **Do not** drop candidates that fail the §121 two-of-five-year ownership/use test — evaluate them
   normally (the engine's existing `sec121` logic already withholds the exclusion when the test
   fails), and flag them in the results table so the user can see the exclusion was lost.

### 3.2 Move-2 candidates (anchored on move-1 winners)

Move-2 candidates are only built on top of the top `anchor_count` move-1 candidates by Pass 1 score
(§4) that end in ownership or a rental — i.e., anchors that still have a "next transaction" to make
(a rent-indefinitely-forever move-1 outcome is not extended; renting is only a step, not a plan end,
when a move 2 is available to follow it).

For each anchor, and each location × `(sale_year_2, purchase_year_2)` pair in the derived move-2
grid, plus a rent-indefinitely-after-move-2 branch:

1. Extend the anchor's plan config with a second sale/purchase event, appended to
   `next_housing_steps` and `residency_schedule` the same way as §3.1.
2. Filter out the same constraint violations as §3.1, now checked across the whole two-move
   timeline (e.g., `family_presence` must hold continuously from plan start through plan end, not
   just through move 1).
3. Apply the §121 test independently to each of the two sale events (a household can lose the
   exclusion on one sale and keep it on the other).

This keeps the search a genuine grid at each stage — reusing the real engine throughout — while
avoiding the full `(move-1 grid) × (move-2 grid)` cross-product, which would be intractable at
per-year resolution. The trade-off, recorded rather than argued: a move-1 candidate that scores
outside the top `anchor_count` is never given a chance to pair with a strong move 2, so the global
optimum is not guaranteed — only a good one anchored on the best individually-ranked first moves.

No new tax modeling is introduced anywhere in this section. Every tax figure a candidate produces
(state income tax, property tax/SALT, itemized-vs-standard deduction, §121 gain tax, estate tax,
ordinary retirement income tax) comes from the unmodified engine acting on the rewritten config.

---

## 4. Execution: staged, two-pass ranking

**Pass 1a — deterministic ranking of move-1 candidates.** Run the existing deterministic engine
once per move-1 candidate (§3.1). Score each by the selected objective, using the plan as if it ended
after move 1:
- `net_worth`: ending net worth (or portfolio-survival horizon) at plan end.
- `lifetime_cost`: total after-tax housing-attributable cost over the plan horizon (mortgage
  interest, property tax, insurance, HOA, rent payments, minus any home-equity growth realized at
  sale) — computed from the same run's existing cashflow breakdown, not a separate cost model.
- `mc_success_rate`: not computed in Pass 1; falls back to `net_worth` for this provisional ranking.

Take the top `anchor_count` results (default 5) that end in ownership or a rental as move-2 anchors
(§3.2). The remaining move-1 candidates — including every rent-indefinitely-forever outcome — stay
in contention as final single-move candidates in their own right; they are not discarded.

**Pass 1b — deterministic ranking of move-2 candidates.** Run the deterministic engine once per
move-2 candidate (§3.2), each covering the full two-move timeline. Score with the same objective
logic as Pass 1a, now over the whole plan.

**Combine.** Pool every move-1 candidate (§3.1) — a candidate promoted to anchor status stays in the
pool as a single-move outcome too, since being a good anchor doesn't mean its move-2 extensions beat
it — together with every move-2 candidate (§3.2) into one ranked list by Pass-1 score.

**Pass 2 — Monte Carlo validation.** Re-run full Monte Carlo on the top 3–5 candidates from the
combined pool. If the selected objective is `mc_success_rate`, re-rank this shortlist by the
resulting success rate; the final recommendation is the top of that re-ranked shortlist. For the
other two objectives, Pass 2 still runs (as a confidence check) but does not change the ranking.

Grid size at each stage should be capped (e.g., by the search-window and `anchor_count` inputs) to
keep Pass 1a/1b runtime reasonable; this is a UI/config-level bound, not a new engine feature.

---

## 5. Output

- **Headline recommendation:** for each move present in the winning candidate — sale year, purchase
  year (or "Rent indefinitely"), and location — plus the objective's value for the whole plan. A
  single-move winner shows one move; a two-move winner shows both.
- **Ranked alternatives table:** next 5–10 candidates by score, same fields (one or two moves each
  as applicable), plus a flag column for "lost §121 exclusion" (per sale) and "family-presence:
  satisfied via rental" where relevant.
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
- **Frontend**: new panel in `dashboard_decomp_housing_scenarios.js` — location list, move-1 and
  (optional) move-2 search-window inputs, `anchor_count`, objective dropdown, family-presence
  region/dates, `no_dual_ownership` toggle, and the results table (one or two moves per row).

---

## 7. Out of scope for v1

- Narrowed/gradient search within a single move's grid — full grid only.
- Chains of **three or more** future moves — v1 caps the plan at two moves (current home → move 1 →
  optionally move 2). A third move is a future extension of the same anchoring approach in §3.2/§4.
- Full cross-product search across move 1 and move 2 at full year-by-year resolution — v1 anchors
  move 2 on move 1's top candidates instead (§3.2), trading a guaranteed global optimum for
  tractability with the real engine.
- New tax modeling of any kind — every tax factor in scope is already produced by the existing
  engine (see §1); if a future request needs a tax treatment the engine doesn't have, that is a
  separate spec.

---

## 8. v1 implementation gaps and next-chunk priorities (Revision 3)

v1 shipped in `src/housing_optimizer.py` per §§1-6. Building it surfaced three gaps this design
didn't anticipate, because they come from a limit in the *engine*, not the optimizer's own search
logic — the engine has never had to model a second home sale before:

### 8.1 Gaps found during implementation

1. **Move 2's sale bypasses the engine's own sale pathway (accuracy gap, real). Closed by §8.2 P0.**
   `home_sale.py` has exactly one sale-with-capital-gain pathway, hard-tied to the household's
   *original* home (`c['home_sale_yr']`). A `next_housing_steps` entry — which is how the engine
   represents a purchased home after move 1 — only ever stops accruing cashflow at its
   `end_year`; it has no "sell this and compute gain/§121" step at all. So move 2's sale is priced
   by `housing_optimizer.py` itself: read the engine's own modeled home value/mortgage balance for
   the move-1 home just before its `next_housing_steps` entry ends, then apply the same
   `tax_kernel.ltcg_tax_on_gain` primitive and §121 arithmetic `home_sale.py` uses. Same tax math,
   applied one level outside the engine's own run loop rather than inside it. The net-after-tax
   proceeds are folded into net worth/lifetime cost as a one-time adjustment — a deposit the
   engine's own cascade never sees.
2. **Consequence of (1): Monte Carlo on two-move candidates is approximate. Closed by §8.2 P0.**
   Because move-2 proceeds aren't a deposit the engine's MC run can see, MC success rate on a
   two-move candidate doesn't reflect that cash coming in. Every two-move result is marked
   `mc_approximate: true` in the API response and flagged in the UI, so this is visible, not
   silent — but it means Pass 2 (§4) MC validation is weaker for two-move candidates than for
   single-move ones. *(Now that move 2's sale is a real deposit, MC sees it naturally — the
   `mc_approximate` flag has been removed from the API response and the UI note; there is no
   residual approximate case.)*
3. **No live-browser verification of the new panel in this environment.** Not a product gap, an
   environment one: this sandbox has no Playwright driver installed (`@playwright/test` is a
   declared devDependency but `node_modules` was never populated — the same pre-existing gap noted
   in the PR's CI section). The panel is covered by 9 passing unit tests
   (`tests/frontend/housing_optimize_panel.test.mjs`) plus a direct `POST /api/housing/optimize`
   round-trip against the demo plan, but nobody has clicked through it in an actual browser yet.

(§121-as-flag-only and the full-grid/no-gradient-search/two-move-cap items are **not** gaps — they
were explicit decisions in §3.1.3/§7 of this spec, not implementation shortfalls.)

### 8.2 Reprioritized next chunk of work

Ordered by (a) correctness first, (b) cost/effort to close, (c) how much it blocks trusting a
two-move recommendation at all:

1. **P0 — Give the engine a real second-sale pathway. Done (2026-09-11).** `home_sale.py` gained
   `apply_next_housing_sale`, sharing its gain/§121 arithmetic with the original-home path via a
   new `_compute_home_sale_economics` helper both call. A `next_housing_steps` purchase step is
   sold by setting `sale_year` on it; `deterministic_engine.py` fires the sale in its own year
   loop, depositing net proceeds onto the same cascade-visible ledger `apply_home_sale` uses (both
   sales' pending gains stack into one correct LTCG computation if they land in the same year).
   `housing_optimizer.py` now sets `sale_year` on move 1's purchase step for a two-move candidate
   instead of estimating move 2's gain/tax out-of-loop, and the `mc_approximate` flag/UI note are
   removed — every two-move candidate's `net_worth`/`lifetime_cost`/`mc_success_rate` now comes
   from the same real engine run a one-move candidate gets, with no residual approximate case.
   This removes gap (1) at the root and, as a consequence, gap (2). See
   `tests/test_next_housing_sale.py` for engine-level coverage of the gain/§121/cascade/Monte
   Carlo behavior, and `tests/test_housing_optimizer_integration.py` for the optimizer-level
   wiring.
2. **P1 — Manual/live smoke test of the panel in a real browser** once a Playwright-capable
   environment is available (or via `/run-skill-generator` to capture a working driver for this
   repo). Low effort, closes gap (3); do this before or alongside P0, whichever environment allows
   first.
3. **P2 — Narrowed/gradient search within a single move's grid. Done (2026-09-11).** `optimize_housing`
   gained an opt-in `search_mode='narrowed'` (default stays `'full'`, byte-for-byte unchanged) that
   replaces, per candidate location, the full `(sale_year x purchase_year)` grid with a bounded
   integer coordinate/pattern search — a handful of seed points followed by hill-climbing to the
   best-improving neighbor — plus the same style of 1D search for the rent-indefinitely branch and
   for move 2's window; scoring/filtering/ranking are reused unchanged. This is a local-search
   heuristic that can miss the global optimum on a non-unimodal score surface, by design (see
   `src/housing_optimizer.py`'s module docstring) — trading completeness for a small, documented
   cap on engine evaluations at larger search windows.
4. **P3 — Full cross-product search across move 1 and move 2** (§7), replacing the anchor-based
   approach in §3.2/§4. Highest effort, lowest urgency: the anchor approach already produces a
   *good* answer; this would only matter once P0 makes move-2 scoring trustworthy enough that the
   gap between "good" and "provably optimal" is worth the added runtime.
5. **P4 — Chains of three or more moves** (§7). No user request for this yet; lowest priority,
   revisit only if it comes up.

No action item here reopens §1's "no new tax logic" decision except P0, and P0 is reuse (applying
`home_sale.py`'s existing gain/§121 computation to a second home) rather than a new tax model —
consistent with the spirit of that decision, not a violation of it.
