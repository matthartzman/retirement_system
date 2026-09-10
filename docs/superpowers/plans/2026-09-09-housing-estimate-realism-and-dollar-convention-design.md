# Housing next-step estimate: realism + dollar-convention — design & implementation plan

**Status:** design only. Nothing in this document has been implemented. All
nine open decisions (§8) resolved 2026-09-10. Implementation plan (§7) phased
into four slices in a follow-up pass.
**Date:** 2026-09-09
**Subject:** `housing_state_estimate_payload()` (`src/server_services/strategy_asset_service.py:94-129`),
its route (`src/server/plan_routes.py:742`), its one frontend caller
(`estimateHousingFromState()`, `frontend/js/dashboard_decomp_housing_scenarios.js:139-233`),
and (§4, added 2026-09-09) a new workbook comparison sheet in
`src/reporting/sheets_strategy.py`, reusing `src/strategy_sweep.py`'s shared
sweep primitive.
**Origin:** investigation into whether a Housing next-step `purchase_price` is
present-day or future dollars (it's neither — see §1), extended after finding
the Estimate button that fills that field, then extended again into a
Buy-vs-Rent comparison sheet scored the same way the existing Social Security
and Roth Conversion sweep sheets already are.

---

## 1. What's actually wrong today, precisely

Three independent, verified findings, all in the same small piece of surface:

**(a) The engine treats every dollar field on a Housing next-step as already
being in that step's `start_year` dollars, with no translation from today.**
`purchase_price` is consumed literally
(`deterministic_engine.py:176`, `price = float(step.get('purchase_price', 0.0)
or 0.0)`), as are `monthly_rent`, `insurance_annual`, `utilities_annual`, and
`maintenance_annual` — each escalates only *within* the step, from `start_year`
forward, via `infl = _infl_ratio(year, base=start)` (`deterministic_engine.py:165`).
Nothing escalates them *from today to start_year* first. The field-guidance copy
half-acknowledges this ("if it's further out, plan for some price appreciation",
`dashboard.js:5188`) but puts the burden entirely on the user, with no UI signal
that this field is different from every other money field in the app.

**(b) The Estimate button actively produces today's-dollars numbers and inserts
them with zero translation.** `STATE_ESTIMATES` (`strategy_asset_service.py:86-91`)
is a hardcoded table of present-day typical prices/rents. `housing_state_estimate_payload`
has no `start_year` parameter and does no forward projection. This isn't a
hypothetical misuse mode of (a) — it's a shipped feature that produces the wrong
number for the exact users (no specific listing in mind) it exists to help, more
severely the further out the purchase is. The `note` field the backend already
computes to explain the estimate's basis is never rendered by the frontend.

**(c) The estimate profile is fixed at "3BR/2BA … at least a 40x40 ft backyard"
for every state, every city type, and both purchase and rent** (the `note` text
at `strategy_asset_service.py:127` is generated unconditionally). No bedroom,
bathroom, property-type, size, or age/vintage signal exists anywhere in the
Housing next-step fields today (confirmed: no match for `bedroom|bathroom|
property_type|sqft|condo|new_construction` anywhere in `strategy_asset_service.py`
or the frontend housing module).

A fourth, smaller asymmetry found in the same investigation: the rent UI never
solicits `city_type` or `population_size` at all
(`RENT_FIRST = ["state"]`, `dashboard_decomp_housing_scenarios.js:363`), so
every rent estimate silently runs with whatever stale value happens to be on
those (hidden) rows. Folded into this design since it's the same function.

---

## 2. Directives from the 2026-09-09 review (binding on this design)

1. **"Built within X years" instead of an age/new-construction framing, for both
   buy and rent.** The user hasn't found the actual future home yet, so asking
   for its "age" is the wrong frame — "built within the last N years" is
   forward-looking and matches what someone can actually specify about a home
   they're planning to buy or rent.
2. **All estimated dollar fields get the same today→start-year translation as
   purchase price and rent** — not just those two. `insurance_annual`,
   `utilities_annual`, and `maintenance_annual` must be treated identically.
3. **Do not touch the engine's existing ongoing escalation.** Once a step is
   active: mortgage principal & interest stays nominally flat for the life of
   the loan (already true — `_mortgage_payment_and_balance` computes one level
   payment from `loan`/`rate` at origination and never revisits it). Rent (and,
   already-consistently, the other recurring costs) escalate by CPI every year
   the step is active (already true — `infl = _infl_ratio(year, base=start)`).
   **This entire design is a one-time, at-estimate-time correction to what
   number gets written into a field. It is not an engine change.**

Directive 3 substantially bounds the blast radius: `deterministic_engine.py` is
untouched by this design. Everything happens in the Estimator function, its
route, and its one caller.

---

## 3. Design

### 3.1 Two distinct escalation mechanisms — name them so they don't get conflated

| | What it does | Where | Status |
|---|---|---|---|
| **Ongoing (within-step) escalation** | Mortgage flat; rent/insurance/utilities/maintenance/property-tax/HOA grow by CPI each year the step is active; home value grows by `home_appr` each year post-purchase | `deterministic_engine.py`'s year loop | **Already correct. Not touched by this design (directive 3).** |
| **Estimator (pre-step) translation** | One-time projection of a *today's-dollars* estimate forward to what it should read at `start_year`, before the value is ever written into a field | `housing_state_estimate_payload`, called once when the user clicks Estimate | **New. This is the entire scope of this design.** |

This separation is what makes directive 3 satisfiable without special-casing
anything in the engine: the engine has always assumed "the field already holds
the right start-year number." This design makes the Estimator actually produce
that number; it does not ask the engine to know or care where the number came
from.

### 3.2 The translation formula, per field

`years_out = max(0, start_year - plan_start)`, where `plan_start` is simply
`new Date().getFullYear()` computed client-side — it matches the engine's own
definition (`data_io.py:690`, `c['plan_start'] = platform_runtime.today().year`)
exactly, and needs no plan-file read to obtain.

| Field | Escalation rate | Rationale |
|---|---|---|
| `purchase_price` | `home_appr` (housing-specific appreciation, already a plan-level assumption) | Matches the rate the same field uses for its own *post-purchase* growth (`home_value = price * (1+home_appr)^…`, `deterministic_engine.py:189`) — one rate governs the home's value before and after the transaction, not two disagreeing ones. |
| `monthly_rent` | CPI (`inflation_general`) | Directive 3 confirms rent is CPI-indexed once active; using the same rate for the pre-step translation makes rent's treatment uniform from today straight through the life of the step — one rate, no seam at `start_year`. |
| `insurance_annual`, `utilities_annual`, `maintenance_annual` | CPI (`inflation_general`) | Directive 2. These are flat recurring dollar costs, not value-linked — CPI is the general-purpose rate the engine already uses to escalate them *within* a step, so using it for the pre-step translation too is the same rate applied one segment earlier, not a new assumption. |
| `re_tax_pct`, `hoa_pct` | **Not translated — already correct by construction** | Both are *percentages of home value* (`price * re_tax_pct * infl`, `deterministic_engine.py:187,192`). Once `purchase_price` is correctly escalated to `start_year`, these formulas are automatically consistent — translating the percentage itself would double-count. |
| `mortgage_rate_pct` | **Not translated** | This is a forward-looking rate assumption entered directly (what the user expects to pay when they originate the loan), not a monetary quantity that compounds with inflation. Stating this explicitly so a future reader doesn't "fix" it by adding a translation that doesn't apply. |
| `down_payment` (%) | **Not translated** | Percentage of price; scales automatically with the (now-correct) price. |

`estimate[field] *= (1 + rate) ** years_out`, applied **after** the existing
characteristic multipliers (§3.3) and **before** the existing rounding step —
i.e., it's inserted as one more multiplicative factor in the same pipeline that
already exists, not a parallel path.

If `start_year` is blank (user hasn't set it yet), `years_out = 0` and this
factor is `1.0` — the estimate behaves exactly as it does today. This keeps the
Estimate button usable at any point in filling out the step, matching current
behavior when information is incomplete.

### 3.3 Five characteristics, replacing the fixed 3BR/2BA profile

Same mechanism the code already uses for `city_type`/`population_size` —
multiplicative factors on the state base price, applied uniformly to purchase
and rent (per directive 1, symmetric across both housing types):

| Field | Type | Options / range | Default (matches today's fixed assumption) |
|---|---|---|---|
| `bedrooms` | `int` | clamped to `{2,3,4,5}` (5 = "5+") | `3` |
| `bathrooms` | `choice` | `1 \| 1.5 \| 2 \| 2.5 \| 3 \| 3.5+` | `2` |
| `property_type` | `choice` | `single_family \| townhome \| condo \| duplex` | `single_family` |
| `sqft_band` | `choice` | `under_1200 \| 1200_1800 \| 1800_2500 \| 2500_3500 \| over_3500` | `1800_2500` |
| `built_within_years` | `int` | blank = no preference; any non-negative integer | *(blank)* |

**Banded, not exact, for size and bathrooms.** `STATE_ESTIMATES` is four numbers
per state — it cannot actually support exact-square-footage precision, so
exposing an exact-number field would imply an accuracy the underlying data
doesn't have. Banding matches the data's real resolution. `bathrooms` is
`choice` rather than `int` specifically to represent half-baths (a real,
commonly-searched price signal that a whole-number field can't express) without
inventing a new numeric field type.

**`built_within_years` replaces "new construction" (directive 1).** A numeric
"built within the last N years" input, banded internally for the multiplier
lookup — not exposed as a band in the UI, so the user isn't forced to guess
which bucket they're in:

```python
def built_within_years_mult(years):
    if years is None:
        return 1.00        # no preference -- same as today
    if years <= 2:
        return 1.15        # new construction
    if years <= 10:
        return 1.05
    if years <= 30:
        return 1.00
    return 0.90
```

**Illustrative multiplier tables** (all values editable in the same sense the
existing `note` text already says "All values are editable" — these are
starting points for someone with real market data to tune, not sourced from a
dataset):

```python
BEDROOM_MULT       = {2: 0.85, 3: 1.00, 4: 1.15, 5: 1.30}
BATHROOM_MULT      = {1: 0.90, 1.5: 0.95, 2: 1.00, 2.5: 1.05, 3: 1.12, 3.5: 1.18}
PROPERTY_TYPE_MULT = {"single_family": 1.00, "townhome": 0.85, "condo": 0.75, "duplex": 0.90}
SQFT_BAND_MULT     = {"under_1200": 0.75, "1200_1800": 0.90, "1800_2500": 1.00,
                       "2500_3500": 1.20, "over_3500": 1.45}
```

`combined = city_mult * pop_mult * BEDROOM_MULT[bedrooms] * BATHROOM_MULT[bathrooms] * PROPERTY_TYPE_MULT[property_type] * SQFT_BAND_MULT[sqft_band] * built_within_years_mult(built_within_years)`,
then the §3.2 translation factor, then the existing rounding.

**Property type also sets a floor on `hoa_pct` and zeroes the "exterior
maintenance" assumption**, not just the price — a condo/townhome estimate that
prices in the condo discount but comes back with `hoa_pct: 0` is a worse
regression than not having the field at all, since HOA is frequently the
larger ongoing cost for that property type:

```python
if property_type in ("condo", "townhome"):
    estimate["hoa_pct"] = max(estimate.get("hoa_pct", 0.0), 0.004)
    estimate["maintenance_annual"] *= 0.4   # HOA typically covers exterior/structure
```

**Defaults, not requirements — a deliberate choice, not an oversight.** All
five characteristics default to values matching today's implicit assumption
(3BR/2BA/single-family/1800–2500 sqft/no preference), so the Estimate button
stays usable with zero new required fields — the user edits any characteristic
that doesn't match their plan before clicking, but nothing new blocks the
button. This was reconsidered from an earlier framing that would have gated the
button on five new required inputs; defaulting-to-current-assumption is
materially lower UX risk for the same accuracy gain.

### 3.4 Closing the rent/purchase asymmetry

`city_type` and `population_size` become required for rent too — added to
`RENT_FIRST` alongside `state` (§5.2). This is the smallest possible fix (two
fields moving from hidden to shown) for a bug that currently makes every rent
estimate silently assume "suburban, 20,000 population" regardless of the actual
area.

### 3.5 The note, made real

`estimate["note"]` already exists and is already discarded by the frontend.
Extend it to state the actual assumption plainly and render it:

> *"3BR/2BA single_family, 1800–2500 sqft, suburban area (~20,000 population) in
> IL: **$298,000 today's dollars → ~$387,000 projected for 2034** at 3.0%/yr
> appreciation (9 years out). Any field below can be edited directly."*

This is the direct fix for the silent-error mode described in the earlier
review — the user sees both numbers and the assumption that connects them,
rather than trusting an opaque single figure.

---

## 4. Comparison sheet — a three-axis housing-trajectory sweep, scored like the Social Security sweep

**Directive (2026-09-09, revised same day):** candidates are combinations of
**(a)** the current home's sale year, **(b)** Housing Step 1 (buy/rent + year +
location), and **(c)** Housing Step 2 (buy/rent + year + location) — a genuine
three-axis sweep of the household's whole future housing trajectory, not a
single binary choice at one step.

**This supersedes the first draft of §4** (a 2-candidate "As Configured vs.
Modeled Alternative" comparison at one step). That draft is wrong under the
revised scope in one specific, important way, corrected in §4.2 below: it
concluded SS's MC-cost-control machinery "doesn't need porting" because it only
ever had ≤4 candidates. A three-axis sweep does not have that luxury — §4.2
shows the honest candidate count and why the conclusion flips.

### 4.1 The three axes, precisely

**(a) Current-home sale year.** Swept in a window around the household's
configured `home_sale_yr` (`data_io.py:972`, `Other Assets/Home/home_sale_year`)
— a field that is **independent of, and not type-enforced against**, the
Housing next-steps' own `start_year` fields (confirmed: `c['home_sale_yr']` and
`c['next_housing_steps'][i]['start_year']` are parsed from entirely separate
CSV rows, `data_io.py:972` vs. `data_io.py:1028`). Default window: `home_sale_yr
± 3` years, clamped to `[plan_start, plan_end]`, plus a distinguished "never
sell" candidate (`home_sale_yr = 0`, the engine's own default/sentinel). If
`home_sale_yr` is unset (0) in the household's plan, the window centers on
Housing Step 1's `start_year` instead, since a first move typically implies a
sale even when the household never separately configured one — stated as a
fallback rule, not silently assumed.

**(b) Housing Step 1 — type × year, location fixed to configured (v1).** Type:
`{purchase, rent}` (the field's own existing choice set). Year: `start_year ± 3`,
clamped to plan bounds. Location and characteristics (`state`, `city_type`,
`population_size`, and the five §3.3 fields) are held at whatever the household
entered for this step — **not** swept in this design. §4.6 explains why and
what a real location sweep would need.

**(c) Housing Step 2 — identical shape to (b)**, only if `next_step_2` is
configured (has a `start_year`). If not configured, axis (c) collapses to a
single "no second move" candidate rather than being omitted — the sweep still
runs meaningfully for the (more common) single-future-move household.

### 4.2 Tractability — why the naive cross-product fails, and the coordinate-descent fix

**The honest count.** Axis (a): ~7 sale years + "never sell" = 8. Axis (b):
2 types × 7 years = 14. Axis (c): 14 (or 1, if unconfigured). A full joint
cross-product is `8 × 14 × 14 = 1,568` candidates in the two-step case. Even
SS's sweep — the most combinatorially ambitious thing this workbook already
does — caps at 81 claim-age pairs, and needed real engineering
(seed-reuse, survivor-bucket caching, `SWEEP_MC_SIMS=200`) to keep *that*
affordable. 1,568 full Monte Carlo runs per workbook build is not viable, full
stop. This is the correction from the first draft: **SS's cost-control
machinery is exactly what this design now needs, not something it can skip.**

**The fix — coordinate descent, not a joint grid, mirroring SS's own two-phase
"coarse-then-refine" structure rather than just borrowing its vocabulary:**

1. **Coarse pass, one axis at a time, deterministic-only** (`skip_mc=True`,
   the same flag SS's own longevity-refinement pass uses at
   `sheets_strategy.py`'s `_safe_project_pair` for the identical reason — its
   `objective_value`/`score` never depended on the MC block, so skipping it for
   a screening pass costs nothing in ranking quality and a great deal in
   speed):
   - Fix Step 1 and Step 2 at their configured (type, year); sweep axis (a)
     alone (≤8 `project()` calls); keep the best sale year.
   - Fix the sale year at that winner and Step 2 at configured; sweep axis (b)
     alone (≤14 calls); keep the best Step 1 (type, year).
   - Fix sale year and Step 1 at their winners; sweep axis (c) alone (≤14
     calls, or skip entirely if unconfigured).
   - **Total coarse-pass cost: ≤36 deterministic `project()` calls** — cheap,
     no Monte Carlo, no survivor-bucket cost at all.
2. **Refine pass, real Monte Carlo, small neighborhood only.** Take the
   coordinate-descent winner and run genuine `monte_carlo()` scoring on it plus
   a small neighborhood (±1 on each axis around the winner, echoing SS's own
   "every individual age around that region is scored" refine step) — on the
   order of **5–10 real MC runs**, not hundreds.
3. **Run the coarse pass twice, from two different axis orderings, and keep
   the better trajectory (open decision #8, resolved 2026-09-10).** Coordinate
   descent's known risk is missing a joint optimum that no single-axis move
   would find. Since the coarse pass is already ≤36 deterministic calls,
   running it a second time starting from a different axis order — (b)→(c)→(a)
   instead of (a)→(b)→(c) — roughly doubles coarse-pass cost to ≤72 calls,
   still cheap, and keeps whichever of the two resulting trajectories scores
   higher before the refine pass runs on it. This reduces, but does not
   eliminate, the joint-optimum-miss risk (decided: acceptable — see §8's
   resolution).
4. **This is coordinate descent (now run twice, per point 3), not an
   exhaustive joint search, and the sheet must disclose that**, the same way
   SS's own text row discloses its sweep is coarse-then-refine over a bounded
   grid rather than a true brute force (`sheets_strategy.py:667`). Say plainly
   that two axis orderings were tried and the better kept — not just "coarse
   then refine" — so the disclosure matches what actually ran.

### 4.3 Candidate pricing — a shared function, now needed by two callers instead of one

Every point on axes (a)/(b)/(c) *except* the household's exact
as-configured (type, year) pair needs a synthesized price/rent — the same
"Modeled Alternative" idea from the first draft, now generalized to every swept
point instead of one. Concretely: **extract `housing_state_estimate_payload`'s
pricing-plus-§3.2-translation core into a pure function** —

```python
def estimate_housing_cost(*, state, city_type, population_size, bedrooms,
                           bathrooms, property_type, sqft_band,
                           built_within_years, housing_type, start_year,
                           plan_start, home_appr, inflation_general) -> dict:
    ...
```

— callable **in-process** by both the HTTP endpoint (§3's existing scope,
unchanged) and this sweep (new). No HTTP round-trip for the sweep: it's already
server-side Python running in the same workbook-build process. This is a new,
necessary piece of touch surface the first draft didn't need, because the first
draft only ever synthesized one alternative per step, inline.

**A real technical trap this generalization surfaces, that the first draft's
narrower scope never hit:** `c['next_housing_steps'][i]['purchase_price']` is a
flat number, computed once at CSV-parse time (`data_io.py:1054`) — it does
**not** carry §3.2's translation logic with it. A sweep candidate that changes
a step's `start_year` (axis (b)/(c)) must **re-derive** `purchase_price` for the
new year via `estimate_housing_cost`, not reuse the parsed value — otherwise the
sweep would silently reintroduce this design's own bug (a stale-year price)
*inside the fix for it*. Every `mutate(c2)` closure in this sweep must go
through `estimate_housing_cost` whenever it changes `type` or `start_year`, and
must leave `purchase_price`/`monthly_rent`/etc. untouched only at the exact
as-configured point.

**"Real vs. modeled" labeling still applies, now per-cell rather than
per-candidate:** only the grid point matching the household's actual configured
(sale year, Step 1, Step 2) uses their real entered dollars end-to-end; every
other point the sweep visits — including ones on the coarse pass that never
reach the final table — is synthesized. The sheet's disclosure text (§4.2 point
3) should say this plainly, not just disclose the search methodology.

### 4.4 Scoring — unchanged from the first draft

The scoring formula, normalization, and feasibility gate are exactly as
originally designed and are not affected by the candidate-space revision:

| Element | Formula |
|---|---|
| Objective | `lcv_score = consumption_pv + after_tax_terminal_nw_pv` (PV via `_roth_discount_rate`, `sheets_strategy.py:417-418`), no survivor-income term (nothing housing-specific plays that role) |
| Normalization | `100 * (raw_score - score_lo) / score_span` (`sheets_strategy.py:1012`) |
| Feasibility gate | `feasibility_probability >= LCV_FEASIBILITY_GATE_THRESHOLD` |
| Mechanism | `strategy_sweep.run_sweep(specs, evaluate_fn, sort_key=..., feasibility_key=...)` — called once per coarse-pass axis, for *each* of the two axis orderings (§4.2 point 3), and once for the refine pass, not once for the whole sweep, since each stage has its own `specs` list |

### 4.5 Sheet layout

A full 1,568-candidate table can't be shown and would misrepresent the
coordinate-descent methodology as a real joint ranking if it tried. Instead:

1. **Recommended trajectory** — one row, matching SS's "Recommended
   spouse-pair" block (`sheets_strategy.py:610`): the refine pass's winning
   (sale year, Step 1, Step 2) combination.
2. **Refine-pass table** — the 5–10 real-MC candidates from §4.2 step 2,
   ranked, with the SS-mirrored column shape:
   ```
   ['Rank', 'Sale Year', 'Step 1 (Type / Year)', 'Step 2 (Type / Year)',
    'Score (0-100)', 'Objective Value', 'After-Tax Terminal NW', 'LCV',
    'Δ LCV', 'NPV of Future Taxes', 'Equity at Plan End',
    'Feasibility Gate Met', 'Worst-Case Ending Wealth (5th %ile)']
   ```
   `Equity at Plan End` is the housing-specific column (no SS analogue) —
   the single number that most directly explains why one trajectory beats
   another despite a higher monthly cost.
3. **Three sensitivity mini-tables** — one per axis, mirroring SS's own
   "Longevity sensitivity of the top-ranked pairs" section
   (`sheets_strategy.py:633`): for each axis, show the *winning* axis
   ordering's (§4.2 point 3) coarse-pass deterministic Objective Value across
   every point on that axis, holding the other two at the winning trajectory's
   values. Cheap (already computed in §4.2 step 1, nothing new to run) and far
   more honest than trying to compress a 1,568-point space into one table — it
   shows the reader "here's the full
   range we actually considered on each axis," which a top-10-of-1,568 table
   would not.

### 4.6 Explicit v1 limit: location is part of the candidate identity but not yet swept

Axis (b)/(c)'s location and characteristics are fixed to the household's single
entered value per step. This is a genuine, named gap against the literal
request — "location" is one of the three things a candidate combines, and v1
doesn't vary it. It's scoped out for a concrete reason, not convenience: sweeping
real alternative locations needs the household to be able to name **more than
one** candidate location per step, and no such input exists today (confirmed —
`strategy_asset_service.py`'s `HOUSING_SEED_ROWS` declares exactly one `state`/
`city_type`/`population_size` per `next_step_N`).

**Phase 2 (separate, sequenced after v1 ships and is verified):** extend the
existing `next_step_1`/`next_step_2` numbering convention one level deeper —
`next_step_1_alt_2`, `next_step_1_alt_3` — following the identical row shape
`HOUSING_SEED_ROWS` already uses, so this needs no new storage mechanism, only
more rows of an existing pattern. Each populated alt-slot becomes one more
option on that step's axis in §4.1(b)/(c), multiplying (not replacing) the
type×year sweep already designed. This is deliberately not bundled into v1:
it's a real UI addition (a repeatable sub-form) with its own review surface,
and bundling it would make v1 depend on unshipped UI before its own
coordinate-descent mechanics could even be verified.

### 4.7 Sheet registration

Unchanged from the first draft's mechanism — following
`module_catalog.py:557-630`'s existing registry pattern exactly, the same one
every other optional sheet (including `10. Social Security`,
`11. Roth Conversion`) is gated through:

```python
'X. Housing Comparison': _spec('2', '2', <rank>, '2', <rank>, 'Housing Comparison', 'housing_next_step_comparison'),
```

New `module_key='housing_next_step_comparison'`, toggled via
`client_optional_functions.csv` — **not** hardcoded on, since a household with
no configured Housing next-step has nothing for this sweep to vary. Section
`'2'` (Strategy) alongside `10. Social Security`, `11. Roth Conversion`,
`13. State Residency`. Exact numeric placement (`X.`/`<rank>`) is an
implementation-time decision — `SHEET_REGISTRY` already has non-sequential
ranks (11B/11C, 12B/12C) for exactly this reason.

Function: `build_sheet_housing_comparison(ws, c, rows)` in `sheets_strategy.py`,
alongside `build_sheet9`/`build_sheet10` — same file, same imports
(`monte_carlo`, `run_scenario`, `_roth_discount_rate`,
`LCV_FEASIBILITY_GATE_THRESHOLD`, `compute_baseline_lcv_and_eltr`,
`sheets_strategy.py:263-267`).

---

## 5. Touch surface

Enumerated by tracing every place `city_type` (the closest existing analogue)
is referenced, so effort estimates in §7 are grounded rather than guessed.

### 5.1 Backend

| File | Change |
|---|---|
| `strategy_asset_service.py` | `HOUSING_SEED_ROWS`: 5 new rows × 2 steps (`next_step_1`, `next_step_2`) = 10 new field declarations. `housing_state_estimate_payload`: accept `start_year`, `home_appr`, `inflation_general`, and the 5 characteristics; add the multiplier tables (§3.3); add the §3.2 translation; extend `note`. **Refactor its pricing core into `estimate_housing_cost(...)` (§4.3), a pure function, so `housing_state_estimate_payload` becomes a thin HTTP-shaped wrapper around it.** |
| `plan_routes.py:742` | No signature change — already passes the full request body through. |
| `sheets_strategy.py` (new) | `build_sheet_housing_comparison(ws, c, rows)`: the coordinate-descent coarse pass (§4.2 step 1), the refine pass (§4.2 step 2), sheet rendering including the three sensitivity mini-tables (§4.5). Imports `estimate_housing_cost` from `strategy_asset_service.py`. |
| `strategy_sweep.py` | No change — consumed as-is; called once per coarse-pass axis and once for the refine pass (§4.4), not once for the whole sweep. |
| `module_catalog.py` | One new `SHEET_REGISTRY` entry (§4.7). |
| `workbook_builder.py` | One new `if '<sheet>' in sheets: build_sheet_housing_comparison(...)` call, matching every existing optional-sheet call site. |

### 5.2 Frontend

| File | Change |
|---|---|
| `dashboard_decomp_housing_scenarios.js:139-233` (`estimateHousingFromState`) | Look up and send `start_year`, `home_appr`, `inflation_general` (with the same defaults the engine uses if the rows are blank — `0.03`/`0.025`, matching `data_io.py:969,695`), plus the 5 characteristic rows, in the POST body. Render `estimate.note` after a successful call instead of discarding it. |
| `dashboard_decomp_housing_scenarios.js:349-368` (`RENT_FIRST`/`PURCHASE_FIRST`/`PURCHASE_REST`/`RENT_REST`) | Add `city_type`, `population_size` to `RENT_FIRST` (§3.4). Add the 5 new fields to both `PURCHASE_REST` and `RENT_REST` (unblocked defaults, §3.3 — not added to the `_FIRST` gating arrays, since they're not required). |
| `dashboard.js:2142` (`filterChoiceOptionsForRow`'s options map) | 3 new choice-field entries: `bathrooms`, `property_type`, `sqft_band`. |
| `dashboard_decomp_row_model.js:~272` (friendly-label overrides, same pattern as `city_type` → "Area Type") | 5 new label overrides. |
| `dashboard.js:~5125` (`FIELD_GUIDANCE_OVERRIDES`) | 5 new purpose/impact/consider blocks, matching the existing `purchase_price`/`city_type` copy style. One is written out in full below as the pattern for the rest. |

Example copy block, establishing the pattern the other four follow:

```js
built_within_years: {
  purpose: "How new the next home should be, expressed as \"built within the last N years\" rather than a specific age -- you likely don't have the exact future home picked out yet, so this is a preference, not a fact about a property you own.",
  impact: "Newer construction typically costs more upfront but may need less near-term maintenance; leaving this blank uses a neutral (neither premium nor discount) assumption.",
  consider: "Leave blank if you have no preference. A small number (0-2) means new construction; 30+ means you're comfortable with an older, more established home.",
},
```

### 5.3 Not touched

- `deterministic_engine.py` — per directive 3, zero changes. The comparison
  sheet doesn't change this either: it runs `run_scenario()`/`monte_carlo()`
  against two Housing-step configurations, both consumed by the engine exactly
  as any other Housing step already is.
- Every other Housing field (`start_year`, `end_year`, `down_payment`,
  `mortgage_rate_pct`, `re_tax_pct`) — unaffected by this design (§3.2 states
  explicitly why the rate-type fields are exempt).
- The manual-entry convention for `purchase_price`/`monthly_rent` when the user
  types a number directly rather than clicking Estimate — this design closes
  the gap in the *Estimator's output*, not in what a user can type by hand. The
  field-guidance copy fix from the prior review (state the convention
  explicitly in the `purchase_price`/`monthly_rent` help text) is complementary
  and not superseded by this design; it should still land, since a user who
  never clicks Estimate gets no benefit from anything here.
- `strategy_sweep.py` itself — consumed unmodified, per its own design intent.

---

## 6. Verification

1. **New regression test: ongoing escalation is unchanged.** Build a 30-year
   purchase step and a multi-year rent step; assert mortgage P&I is bit-for-bit
   identical year-over-year post-origination, and rent grows by exactly
   `(1+inf)` each active year — both **before and after** this change, to prove
   directive 3 held. This is the one test that would catch an accidental engine
   edit.
2. **Estimator unit tests** (pure-function, no plan-file mocking needed per
   §3.2's `plan_start` design): each characteristic multiplier in isolation;
   the `years_out=0` (blank `start_year`) no-op case; the property-type
   HOA-floor interaction; rounding stability at typical values.
3. **Golden-master check.** This design touches no engine code, so
   `test_synthetic_golden_master.py` pins are expected to be unaffected — run it
   as confirmation, not as a gate that should ever fail here. A failure here
   would itself be a signal that §5.3's "not touched" boundary was violated.
4. Existing Housing-page functional/UI tests (`test_wellness_transaction_dropdowns_functional.py`-style
   suites reference this page's row model) — re-run for the new fields'
   presence and default values.

---

## 7. Implementation plan

Turn estimates assume Sonnet 5 at medium reasoning effort unless noted — this
is a well-specified feature addition with two concrete precedents to copy the
shape of (`city_type`/`population_size` for §3's fields; `build_sheet10`'s SS
sweep for §4's sheet), not an open-ended refactor, so it does not need the
higher tiers the two large modularization plans required.

### 7.0 Delivery is phased into four slices, not big-bang

Resolved in a follow-up session after §8's decisions (asked explicitly:
is there a natural phase-in of value, or does this ship as one unit).
Called **Slices** here, deliberately not
*Phases*, to avoid colliding with the already-named "Deferred — Phase 2"
(§4.6's alt-location sweep) later in this section — the two are unrelated
groupings. Each slice below is independently valuable and shippable on its
own; nothing later in the list is required to get value from something
earlier.

- **Slice 1 fixes the actual correctness bug** (§1a/b — today's-dollars
  numbers silently written into future-dollars fields) **with zero new UI.**
  This is the single highest-value item in the whole document and needs
  nothing else in this plan to ship.
- **Slice 2 adds the five realism characteristics** (§3.3) on top of an
  already-correct Slice 1. Real value, but strictly additive — nobody is
  blocked on it to get Slice 1's fix.
- **Slice 3 ships a sheet early, in the first draft's original shape** — a
  plain 2-candidate "as-configured vs. the opposite type" comparison at Step 1
  only, no sale-year or Step 2 sweep, no coordinate descent. This is
  literally the design this document's own §4 intro describes as superseded
  — resurrected here on purpose as a real, cheap, shippable interim version of
  the *same* sheet Slice 4 later upgrades in place.
- **Slice 4 upgrades that sheet to the full three-axis coordinate-descent
  sweep** (§4.1–§4.5, including the open-decision-#8 double-ordering
  mitigation) — same `SHEET_REGISTRY` entry, same disclosure convention,
  replacing Slice 3's candidate generation and rendering rather than adding a
  second sheet.

**This costs real rework, and that cost is stated plainly rather than
hidden.** Slice 3 builds a scoring/rendering shape that Slice 4 then replaces
rather than extends — H9a/H11a below are not wasted (they're what makes Slice
3 shippable at all, and H10/H11 in Slice 4 reuse the scoring block H9a
establishes), but they are real turns spent on something Slice 4 supersedes.
The phased total below (22–35) is a few turns higher than shipping
non-phased (19–31, §7's prior revision) for exactly this reason — the
trade is earlier delivered value for a small amount of throwaway-adjacent
work, not a free lunch.

**Dependencies across slices:** Slice 2 has no dependency on Slice 1 and may
run in parallel with it (same as H1–H6's original independence). Slice 3
depends on Slice 1 specifically (H8 extracts the function H2 writes the
translation logic into) — not on Slice 2. Slice 4 depends on Slice 3 (it
upgrades the same sheet H7/H8/H9a/H11a stand up). Recommended sequence:
**Slice 1 → Slice 3 → Slice 4**, with **Slice 2 run in parallel with Slice 1**
(it can land before or after Slice 3/4 with no effect on either).

#### Slice 1 — Dollar-convention fix (ship first)

| ID | Item | Model · effort | Turns |
|---|---|---|---:|
| H2 | Backend: §3.2 translation (start_year/home_appr/inflation_general params, per-field rates, exemption list respected); extend `note`. | sonnet · medium | 1–2 |
| H3 | Frontend: thread `start_year`/`home_appr`/`inflation_general` through `estimateHousingFromState`; render `note`; close the rent `city_type`/`population_size` gap (§3.4). | sonnet · medium | 1–2 |
| H5 | **The one item that needs a stronger check, not a stronger model.** The ongoing-escalation regression test (§6 item 1) — its value is in what it proves (directive 3 held), not in any judgment call, so it stays sonnet, but it must exist and pass before H2/H3 are considered done, not after. | sonnet · medium | 1–2 |
| | **Slice 1 subtotal** | | **3–6** |

#### Slice 2 — Realism characteristics (parallel-capable with Slice 1)

| ID | Item | Model · effort | Turns |
|---|---|---|---:|
| H1 | Backend: 5 new `HOUSING_SEED_ROWS` entries × 2 steps; multiplier tables; characteristic-combined pricing (§3.3). | sonnet · medium | 2–3 |
| H4 | Frontend: 5 new fields in `PURCHASE_REST`/`RENT_REST`, `filterChoiceOptionsForRow`, row_model label overrides, `FIELD_GUIDANCE_OVERRIDES` copy. | sonnet · medium | 2–3 |
| H6 | Estimator unit tests + golden-master confirmation run (§6 items 2–3). | sonnet · low | 1–2 |
| | **Slice 2 subtotal** | | **5–8** |

#### Slice 3 — Simple comparison sheet (v0: 2-candidate, no coordinate descent)

| ID | Item | Model · effort | Turns |
|---|---|---|---:|
| H7 | `SHEET_REGISTRY`/`OPTIONAL_MODULE_SHEETS`/`workbook_builder.py` wiring for the new sheet (§4.7) — mechanical, three files, each with an exact existing pattern to copy per row. | sonnet · low | 1 |
| H8 | Extract `estimate_housing_cost(...)` (§4.3) as a pure function out of `housing_state_estimate_payload`, which becomes a thin HTTP-shaped wrapper around it. Mechanical — H2 already wrote the logic being moved, this just gives it a second caller. Depends on Slice 1 (H2) landing first. | sonnet · low | 1 |
| H9a | **Slice 3's candidate scoring — the first draft's original shape, resurrected.** Exactly two candidates: the household's configured Step 1 (type, year, location) as entered, and the opposite type (buy↔rent swap) at the same year/location, priced via `estimate_housing_cost` (H8). Both scored with real `monte_carlo()` directly — no `skip_mc` coarse pass needed, two candidates is already cheap — using the `lcv_score`/PV/feasibility-gate block `build_sheet10` already establishes. **Superseded by H9 in Slice 4.** | sonnet · medium | 1–2 |
| H11a | **Slice 3's sheet rendering.** One row for the configured choice's score, one row for the alternative — with only two candidates, the table *is* the recommendation, so no separate recommended-trajectory block. A short disclosure line: "compares your configured Step 1 choice against the opposite (buy vs. rent) at the same year." No sensitivity tables — nothing swept yet to show sensitivity over. Registered under the same `SHEET_REGISTRY` entry H7 creates, so Slice 4 upgrades this sheet in place. **Superseded by H11 in Slice 4.** | sonnet · low | 1–2 |
| | **Slice 3 subtotal** | | **4–6** |

#### Slice 4 — Full three-axis coordinate-descent sweep (upgrades Slice 3's sheet in place)

| ID | Item | Model · effort | Turns |
|---|---|---|---:|
| H9 | Coarse pass (§4.2 steps 1 & 3): coordinate descent across the three axes, `skip_mc=True`, ≤36 `project()` calls, each stage fixing the other two axes at their current-best value before sweeping the third — run twice, from two different axis orderings (open decision #8), keeping whichever trajectory scores higher. **Supersedes H9a's 2-candidate scoring on the same sheet.** | **opus · medium** | 3–4 |
| H10 | Refine pass (§4.2 step 2) + scoring/`run_sweep()` wiring (§4.4): real `monte_carlo()` on the winning coarse-pass trajectory plus its neighborhood, reusing the `lcv_score`/PV/feasibility-gate block H9a already established rather than writing it fresh. | **opus · medium** | 2–3 |
| H11 | Sheet rendering (§4.5): recommended-trajectory row, refine-pass table, three per-axis sensitivity mini-tables (sourced from the winning ordering's coarse pass), the methodology-and-real-vs-modeled disclosure text (stating two axis orderings were tried and the better kept). **Extends H11a's rendering in place** — same sheet, same registry entry, the 2-row table becomes the refine-pass table. | sonnet · medium | 2–3 |
| H12 | New test: comparison-sheet scores are on the same scale as `10. Social Security`'s (a synthetic fixture where both sheets score the same underlying plan should produce comparable `Objective Value` magnitudes) — the concrete check that "scored like SS" was actually achieved, not just stated. | sonnet · medium | 1–2 |
| H13 | New test: coordinate-descent correctness — a synthetic fixture with a known-best (sale year, Step 1, Step 2) combination planted in it; assert each coarse-pass stage actually carries the prior stage's winner forward into `c2`, and that the two-orderings comparison in H9 actually keeps the higher-scoring trajectory (the concrete check for H9/H10's silent-failure risk, playing the same role H5 plays for directive 3). | sonnet · medium | 2–3 |
| | **Slice 4 subtotal** | | **10–15** |

| | **Total (v1, all four slices)** | | **22–35** |

**Why H9/H10 are opus · medium and nothing else in this plan is above
sonnet.** Every other item has a fully specified answer to copy (a formula, a
table, an existing file's pattern). H9/H10 are where getting something subtly
wrong — a coarse-pass stage that sweeps axis (b) without actually holding
axis (a)'s winner fixed in `c2`, a feasibility gate that silently always
passes, an off-by-one in the PV discount, or the two-orderings comparison
(open decision #8) silently keeping the wrong trajectory — produces a sheet
that *looks* right (renders, has plausible-looking numbers, ranks something)
while quietly failing the premise of the request: that the search is real and
the score means what it means on `10. Social Security`. Same silent-failure
shape the two modularization designs used to justify their opus-tier items.

**This total's history: 15–23 (first draft) → 18–29 (three-axis sweep) →
19–31 (open decision #8's double-ordering mitigation) → 22–35 (phased into
four slices).** Each growth is real, not padding. H9/H10/H13 didn't exist in
the first draft because the problem they solve (tractability of a
combinatorial candidate space) didn't exist at 4 candidates. H9a/H11a exist
only because of the phasing decision itself — the price of Slice 3 shipping
real value before Slice 4 is ready, paid once.

**Two lanes, four slices.** §3's fix (Slices 1–2, H1–H6) touches
`strategy_asset_service.py` and the frontend housing module; §4's sheet
(Slices 3–4, H7–H13) touches `sheets_strategy.py`, `module_catalog.py`,
`workbook_builder.py`, and `strategy_sweep.py` (read-only). H8 has a stated
dependency on Slice 1 (H2) — it extracts the function H2 writes the logic
into — and H9/H10 depend on H8/H9a. Recommended sequence: **Slice 1 → Slice 3
→ Slice 4**, with **Slice 2 running in parallel** at any point.

### Deferred (post-v1): alt-location sweep (§4.6), not in the total above

Named "Phase 2" in earlier revisions of this document, before Slice
terminology existed above for a different grouping — kept here as P1/P2 to
avoid renumbering, but read as "the post-v1 deferred work," not as a fifth
slice.

| ID | Item | Model · effort | Turns |
|---|---|---|---:|
| P1 | `next_step_N_alt_2`/`alt_3` `HOUSING_SEED_ROWS` rows + a repeatable sub-form UI for entering additional candidate locations per Housing step. A genuinely new UI pattern (repeatable sub-form), not just more fields — larger than H1/H4 individually. | sonnet · medium | 4–6 |
| P2 | Extend §4.1(b)/(c)'s axes to include each step's populated alt-slots as additional discrete options — multiplies, does not replace, the existing type×year sweep. | sonnet · medium | 2–3 |
| | **Deferred subtotal** | | **6–9** |

Sequenced after Slice 4 ships and its coordinate-descent mechanics are
verified (H9/H10/H13) — bundling this into v1 would make the sweep depend on
unshipped UI before its own search logic could be tested in isolation.

---

## 8. Open decisions

All nine resolved 2026-09-10, asked explicitly and answered one by one. Each
entry below keeps the original question for context, then records the
decision and where it changed (or confirmed unchanged) the design above.

1. ~~**Should `built_within_years` also feed the ongoing per-year math**
   (e.g., a newer home needing less maintenance escalation over time)?~~
   **Resolved: out of scope for v1.** Confirms directive 3 as originally
   stated — this design only changes what number the Estimator writes once,
   not any ongoing year-by-year engine behavior. No change to the design.
2. ~~**Multiplier table values are illustrative, not sourced.**~~
   **Resolved: ship as illustrative defaults, tune later.** Same treatment as
   the existing `city_type`/`population_size` multipliers already in
   production. No change to the design — §3.3's tables stand as written.
3. ~~**Does `home_appr` or a distinct "market appreciation until purchase"
   rate belong in §3.2's price translation?**~~ **Resolved: single `home_appr`
   rate, as originally designed.** No second rate added. No change to the
   design — §3.2's table and rationale stand as written.
4. ~~**Should the comparison sheet (§4) sweep more than Buy vs. Rent?**~~
   **Superseded 2026-09-09** — the directive that produced this open question
   also answered it: candidates are now a three-axis sweep (sale year × Step 1
   × Step 2), not a single binary choice. §4.1–§4.2 are the resolution.
5. ~~**Does the sheet compare `next_step_1` and `next_step_2` against each
   other?**~~ **Resolved: implicit is fine — no explicit "should I even do
   Step 2" disclosure line.** If a "no second move" trajectory scores highest,
   it already wins the ranking and appears as the Recommended trajectory
   (§4.5 item 1); H11 does not gain extra rendering work for this. No change
   to the design beyond this confirmation.
6. **Sheet placement number.** §4.7 deliberately leaves the exact `X.`/rank
   values for implementation time, per `SHEET_REGISTRY`'s own precedent of
   non-sequential ranks — but section `'2'` (Strategy) alongside SS/Roth/State
   Residency is a design commitment, not just a placeholder, since it's what
   makes "scored like SS" legible to a reader flipping between sheets in the
   same workbook section. Not asked as a decision (no real alternative was on
   the table) — recorded here as confirmed, not open.
7. ~~**Window size `K=3` for all three axes is a single, unjustified
   constant.**~~ **Resolved: uniform ±3 years for all three axes, as
   originally designed.** No asymmetric per-axis windows for v1. No change to
   the design — §4.1's window stands as written. Revisit only if the
   sensitivity tables (§4.5 item 3) show a winner sitting at the edge of its
   window.
8. ~~**Coordinate descent can miss a joint optimum a true grid search would
   find.**~~ **Resolved: add the mitigation now — run the coarse pass twice,
   from two different axis orderings, and keep the better trajectory.**
   **This changed the design**, not just this section: see §4.2 point 3 (new),
   §4.5's Mechanism row and sensitivity-table sourcing, and §7's H9/H10/H13
   turn estimates (total moved from 18–29 to 19–31). The residual risk —
   coordinate descent, even run twice, can still miss a joint optimum a true
   grid search would find — remains a disclosed limitation, not a solved
   problem; a real joint search is still not in v1's scope.
9. ~~**The `home_sale_yr` unset → fall back to Step 1's `start_year`** rule
   (§4.1(a)) assumes a household's first future move coincides with, or
   follows soon after, selling the current home.~~ **Resolved: accept as a
   known, pre-existing gap — out of scope for v1.** The "keep and rent out the
   current home while buying elsewhere" state doesn't exist anywhere in the
   Housing data model today (`home_sale_yr` is binary: sell at this year, or
   0/never) — fixing that is a separate, larger data-model change, not
   something this design's fallback rule should attempt. No change to the
   design — §4.1(a)'s fallback stands as written.
