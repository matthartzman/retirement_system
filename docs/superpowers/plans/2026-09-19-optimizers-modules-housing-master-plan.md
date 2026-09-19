# Optimizers, Modules & Housing — Master Implementation Plan

> **For agentic workers:** This is a **master sequencing plan**, not a task-level
> plan. It fixes the order, the merges and the cross-cutting constraints for three
> designs. Each workstream below gets its own bite-sized TDD task plan, written
> immediately before that workstream is executed, using
> `superpowers:writing-plans` and saved as
> `docs/superpowers/plans/2026-09-19-<workstream-id>.md`. Execute those with
> `superpowers:subagent-driven-development`.

**Goal:** Land three approved designs — optimizer/stress-test rationalization
(#329), modular features and feature-switch navigation (#330), and the housing
optimizer anchor flow and future-year valuation fix (#331) — in one coherent
order that merges their overlapping work and never regenerates golden masters
twice for the same reason.

**Architecture:** `module_catalog` becomes the single source of truth for two
independent axes — `kind` (what shape of answer a module produces, #329) and
`domain` (what part of life it concerns, #330) — with the workbook section
layout, the switch navigation and the input-page grouping all *derived* from it
rather than hand-maintained beside it. A stable `slug` decouples sheet identity
from presentation letters, which is the prerequisite for making more modules
optional. Housing (#331) is an independent subsystem touching `src/housing/` and
its panel, and runs in parallel.

**Tech Stack:** Python 3 backend (`src/`), `openpyxl` workbook generation,
vanilla-JS frontend (`frontend/js/`, no framework), `pytest` + `node --test`,
CSV-backed plan data.

## Global Constraints

These apply to **every** task in every workstream. Copied from the three specs.

- **No calculation changes except where a spec names one.** #329 and #330 are
  label, declaration and rendering changes only. The two deliberate exceptions
  are the engine-gate fix (W7) and the housing escalation fix (H1).
- **`deterministic_engine.py` is off-limits to H1.** #331 inherits the 2026-09-09
  directive 3: the engine's `infl = _infl_ratio(year, base=start)` and
  `home_value = price * (1 + home_appr) ** (year - start + 1)` stay byte-for-byte.
  The engine escalates *from* `start_year`; writing a move-year figure into a step
  whose `start_year` is that year is what the engine already expects and
  double-counts nothing. W7 edits that file for an unrelated reason (which modules
  participate) — the ban is on H1 changing escalation there, not a blanket freeze.
- **The housing budget is deflated exactly once, and never escalated.** The
  screen deflates the bounds (§6.4 site 4); `plan_variant` tier 1 consumes the
  midpoint unchanged (site 3). These are two halves of one convention — if a
  future change escalates it in `plan_variant`, the screen's deflation must be
  removed **in the same commit**.
- **`screen.estimate_price` and `_base_estimate` stay byte-for-byte**, and every
  funnel count is unchanged for a current-year window. Only the bounds move.
- **Never escalate a percentage.** `re_tax_pct`, `hoa_pct`, `mortgage_rate_pct`
  and `down_payment_pct` apply to an already-escalated price; escalating them
  compounds twice. `_effective_mortgage_rate` takes the three new parameters only
  because it shares the call — it does not escalate.
- **No rate travels on the wire.** `home_appr` and `plan_start` are read
  server-side from `c0`, the same two keys with the same fallbacks that
  `plan_variant` reads. A client-supplied rate could disagree with the one the
  optimizer then uses.
- **Three Python functional tests read panel JS as text** —
  `tests/test_zip_screen_panel_functional.py` and siblings. Read them *before*
  touching any panel JS and treat their assertions as an interface contract. A
  prior similar change broke 24 of them.
- **`test_zip_screen_panel_functional.py:72` asserts the shortlist-size control
  exists.** H2 deliberately inverts that assertion. It is not an accidental break.
- **Turning a module off never deletes plan data.** Re-enabling restores the
  prior state exactly. No toggle handler may clear rows.
- **No switch may render a row invisible when that row holds a user-entered
  value.** If it would, it renders collapsed-with-a-note instead, naming how many
  rows are affected.
- **Never derive `domain` from `kind` or vice versa.** They are independent axes.
  `validate()` asserts every module declares both.
- **The switch nav must never derive from `letter_prefix` or `section`.** Those
  are workbook presentation and change under W3.
- **Golden-master regeneration commits land alone.** Nothing else in the same
  commit; the fixture diff is the reviewable artifact.
- **Check `/usage` against the estimates in §7 as execution proceeds.** The
  relative weights are the signal, not absolute figures.

---

## 1. What holistic planning changed

Five things that neither design could see on its own. These are the reason this
plan exists rather than three independent ones.

**1. Three separate passes at `module_catalog` collapse into one.** #329 phase 1
(the `kind`↔`letter_prefix` invariant, missing `CATALOG` entries, the `3D`–`3F`
contradiction), #330 phase 1 (the catalog↔registry sheet-name join guards,
`scorp_vs_llc` and `plan_data_ref` name mismatches, the missing
`housing_trajectory_comparison` toggle row) and #330 phase 2 (the `domain` field)
all edit the same two files and all add assertions to the same `validate()`.
Merged into **W1**, they are one read of `module_catalog.py` instead of three.

**2. #329's own phasing contradicts its gate on Planning Levers.** #329 phase 3
retires `planning_levers_echo`, but #329 §3.2 gates that retirement on the §4.7
row badges being able to show lever provenance live — and those badges ship in
#329 phase 6. Retiring it in phase 3 would remove the only provenance view with
nothing in place of it. **W11 moves the retirement after W10.**

**3. #329 phase 7 should not exist as a phase.** It renames the two housing
engines and states each panel's question — which edits the same housing panel
that #331's A3 restructures wholesale. Done separately, the panel gets opened
twice and the rename risks being overwritten. **Folded into H2.**

**4. There are two golden-master regenerations, for unrelated reasons, and
neither design knew about the other.** W7 (engine gate fix) moves fixtures
because two modules start participating in the projection honestly; H1/B5 moves
fixtures because future housing is priced correctly. If they land close together
the second diff is unreviewable, because a reviewer cannot tell which change
caused which delta. **They are separated in §6's order, and each lands alone.**
W8b may move fixtures a third time; it is sequenced after both.

**5. #330 depends on #329's slug more tightly than #329 realises.** #330 §6.2
makes it a hard prerequisite: going from 27 optional modules to 40 means more
sheets absent per build, more letter collapse, and more cross-reference prose
resolving differently per household. **W2 gates W8 absolutely.**

---

## 2. Workstream map

| ID | Workstream | Source | Depends on |
|---|---|---|---|
| **W0** | Pre-flight verifications | #329 §5.1, #330 §7.1, §4.3 | — |
| **W1** | Catalog foundation: guards, `kind` invariant, `domain` | #329 P1 + #330 P1 + P2 | W0 |
| **W2** | Stable `slug` on `SheetSpec` | #329 P2 | W1 |
| **W3** | Workbook regrouping + `kind` derivation | #329 P3 + F7 | W2 |
| **W4** | Plan Features page (switch surface) | #330 P3 + Q7 | W1 |
| **W5** | Dependency declarations + enforcement test | #330 P4 | W1 |
| **W6** | Plan-flag unification (HELOC, Hybrid LTC, DAF, QCD) | #330 P5 + Q2 | W5 |
| **W7** | **Engine gate fix — golden regen #1** | #330 F3 | W5 |
| **W8a** | Newly-optional, low risk | #330 P6a | W2, W7 |
| **W8b** | Newly-optional, medium risk | #330 P6b | W8a, W6 |
| **W9** | UI section registry, restored modules, HELOC move | #329 P4 + #330 | W3, W6 |
| **W10** | Optimizer results (Roth) + apply-to-plan + §4.7 badges | #329 P5, P5b, P6 | W9 |
| **W11** | Planning Levers retirement | #329 §3.2 gate | W10 |
| **W12** | Off-state rendering + no-hidden-data invariant | #330 P7 | W4, W9 |
| **W13** | **Left-nav realignment** | #330 P8 / Q6 | W12 |
| **H1** | Housing PR 1 — valuation, **golden regen #2** | #331 B1–B6 | W0 |
| **H2** | Housing PR 2 — anchor flow + #329 P7 rename | #331 A1–A4 + #329 P7 | H1 |

`H1`/`H2` touch `src/housing/` and the housing panel only, and share no files
with W1–W13. They run in parallel, subject to §6's golden-master ordering.

---

## 3. W0 — Pre-flight verifications

Three cheap checks whose answers change later workstreams' size or content. Doing
them first costs one short session and prevents rework.

**V1 — Does a toggle change raise a `build_impact` notice today?**
(#330 Q5, §7.1.) Read `dashboard_source_truth_banners.js`'s notice conditions and
whether `client_optional_functions.csv` edits route through the same staleness
path as ordinary plan rows. *If yes*, W5 has nothing to do here. *If no*, W5
gains a task wiring it. Deliverable: one paragraph in the W5 task plan, no code.

**V2 — Are the three held-coverage modules inventories or sizing analyses?**
(#330 §4.3 ⚠.) Read the builders for `existing_life_insurance`,
`disability_income_insurance` and `property_casualty_umbrella`. The owned-vs-needed
split assigns them to Assets & Protection on the premise that they inventory
coverage the household holds. If any primarily *recommends* an amount, it belongs
in Risk & Resilience with `life_insurance_need`, and W1's `domain` values change
before they are written down. Deliverable: confirmed `domain` value per module.

**V3 — Is Tax Capacity's home Reports, or its own Reference section?**
(#329 §5.1.) Resolved by inference when Planning Levers was retired, leaving one
worksheet. Confirm before W3 writes the section layout. Deliverable: one line.

**Model · effort:** sonnet · low. **Turns:** ~8–12. **Weight:** Light.

---

## 4. Workstream detail

Each entry states scope, the files it owns, and what "done" means. Bite-sized TDD
steps are written per workstream immediately before execution.

### W1 — Catalog foundation
**Merges #329 P1, #330 P1, #330 P2.**

Scope: add `domain` to `OutputModule` and populate it for all 40 modules (using
V2's answer); add `CATALOG` entries for HSA Drawdown, Tax Capacity and
`37. Current vs Proposed`; fix the `3D`–`3F` `section`/`letter_prefix`
contradiction; fix `scorp_vs_llc.sheet` and `plan_data_ref.sheet` so they join
`SHEET_REGISTRY`; add the missing `housing_trajectory_comparison` toggle row.

Then four `validate()` assertions, all at import time:
1. A sheet's `letter_prefix` matches the group implied by its module's `kind`,
   and `section` matches `letter_prefix`. *(#329)*
2. Every `CATALOG[key].sheet` is a key of `SHEET_REGISTRY`. *(#330)*
3. Every `SHEET_REGISTRY` entry with a `display` has a catalog module. *(#330)*
4. Every module declares both `kind` and `domain`; every `optional=True` module
   has a toggle row in the default plan. *(#330)*

Files: `src/module_catalog.py`, `input/demo/client_optional_functions.csv`,
`tests/test_sheet_table_consistency.py`.
Done: all four assertions green at import; no behavior change.
**sonnet · medium · ~20–30 turns · Light–moderate.**

### W2 — Stable slugs
**#329 P2. Ships alone.**

Scope: `slug` on `SheetSpec`; every cross-reference resolves display text through
`FINAL_SHEET_RENAMES[slug]` at build time. Letters become presentation only.

Files: `src/reporting/workbook_common.py`, `src/reporting/workbook_builder.py`,
`_replace_text_refs` and its call sites.
Done: a workbook built with a different module set carries correct cross-references.
**Cost driver:** `_replace_text_refs` is a full-workbook string pass, so
verification is a build, not a unit test. **Pin two or three representative toggle
configurations rather than sweeping the space.**
**sonnet · medium · ~20–30 turns · Moderate.**

### W3 — Workbook regrouping
**#329 P3 + F7. Requires W2.**

Scope: restructure to `1. Reports` / `2. Optimizers` (with a "This year's actions"
divider for TLH + Gain Harvesting) / `3. Comparisons` / `4. Risks` (4.1 stress
tests, 4.2 protection decisions). Rename "Risk & Stress Tests" → "Risks"; section
2 keeps its name. Split `3C` into a stress tab and a protection tab. Move Tax
Capacity per V3. Full derivation of `section`/`letter_prefix` from `kind`.

**Does not retire Planning Levers** — that is W11.

Files: `src/reporting/workbook_common.py`, `src/reporting/workbook_builder.py`
(`_merge_ltc_into_life_insurance` is removed), `src/module_catalog.py`,
`tests/test_sheet_table_consistency.py`.
Done: tab strip matches the target structure; derived tables have no hand-typed twin.
**sonnet · medium · ~20–30 turns · Moderate.**

### W4 — Plan Features page
**#330 P3 + Q7. Requires W1.**

Scope: regroup `renderOptionalFunctions()` by `domain`; kind filter chips derived
from `CATALOG.kind`; per-row description, demand hint, auto-enable badge (exists),
off-impact line, and an "Off · N items entered" indicator. Rename the page
"Plan Features". Read-only disclosure when a `RETIREMENT_SYSTEM_FORCE_*` env
override is active.

Files: `frontend/js/dashboard.js` (`renderOptionalFunctions` and neighbours only),
`src/server/config_service` payload.
**Cost control:** `dashboard.js` is 7,287 lines and `renderOptionalFunctions()` is
about 35 of them. **Do not open the file linearly.**
**sonnet · medium · ~20–30 turns · Moderate.**

### W5 — Dependency declarations
**#330 P4 + V1. Requires W1.**

Scope: `degrades_without` (soft dependency, never auto-enables) and
`engine_participation` on `OutputModule`; the reverse-direction warning on the
switch ("Turning Monte Carlo off also removes the success-probability headline
from Executive Summary and the fan chart from Charts"); plus V1's `build_impact`
wiring if V1 found it absent.

Then the enforcement test: grep `src/` for `module_enabled(` and raw `c['opt']`
reads, and assert every call site outside the named module's own builder is
backed by a `requires_outputs` or `degrades_without` declaration. ~10 sites today.

**Scoping:** grep for the two exact strings, not a semantic search for "places
that read toggles", and write the findings into the test as a fixture list so the
sweep happens once rather than once per run.
**opus · high · ~25–35 turns · Moderate–heavy.**

### W6 — Plan-flag unification
**#330 P5 + Q2. Requires W5.**

Scope: `gate_kind` / `gate_ref` on `OutputModule`; catalog entries for HELOC,
Hybrid LTC, DAF **and QCD**; `flag_gate_map()` beside `step_gate_map()`; remove
both hand-written branches in `stepGatedByOptionalModule()` and the
`gateStepId === "heloc_strategy"` branch in `strategySectionGatedNote()`. Drop
`charitable_giving`'s `csv_sections=("DAF",)` so DAF matches QCD.

**Scoping:** behavior-preserving refactor with no user-visible change — the classic
shape for an open-ended session. **Do HELOC alone, end to end, first. If HELOC
alone is not clean, stop: the mechanism is wrong.** Hybrid LTC, DAF and QCD are
repetitions only once HELOC's pattern is proven.
**opus · high · ~25–35 turns · Heavy.**

### W7 — Engine gate fix · **golden regen #1**
**#330 F3. Requires W5. Lands alone.**

Scope: `deterministic_engine.py` reads `module_enabled` for `equity_compensation`
and `disability_income_insurance` like every other call site; regenerate golden
masters.

Rationale for treating this as a bug: `effective_enabled_modules()` auto-enables
prerequisites, so a module can be enabled for sheet purposes while the engine
models it as off — a sheet built from a projection excluding its own subject.
Reachable in ordinary use, not only under `FORCE_ALL_MODULES`.

**The golden diff is the deliverable.** Verify a representative fixture's delta by
hand before batch-regenerating. Nothing else in the commit.
**opus · high · ~15–25 turns · Moderate, high review burden.**

### W8a / W8b — Newly-optional modules
**#330 P6. Requires W2 (absolutely) and W7.**

W8a (low risk): `asset_location`, `scorp_vs_llc`, Tax Capacity, Current vs
Proposed. Registry edits plus a build per toggle combination. Nothing reads these.
**sonnet · medium · ~15–20 turns · Moderate.**

W8b (medium risk): HSA Drawdown, Hybrid LTC, DAF+QCD, Housing "Where to live",
and Spending Tracker / YTD — which **bundles `spending_summary` and
`account_reconciliation` under one switch**, since all three are YTD-dependent and
none can compute without the others' data.

**Do not batch W8a and W8b in one session.** W8a's cheapness comes entirely from
nothing reading its modules; W8b touches the engine and needs golden-master
reasoning. Pin two or three representative toggle combinations.
**opus · high · ~30–40 turns · Heavy.**

### W9 — UI section registry
**#329 P4 + #330. Requires W3, W6.**

Scope: `strategySection()` registry edits to match #329 §3.3's UI list; restore
Withdrawal Sequencing, Asset Location and Scenario Analysis (each its own tab);
move HELOC to Assets & Protection; add Divorce/QDRO's workbook sheet;
`navigation.js` redirects.
**Cost driver:** the redirects are the fiddly part, not the registry.
**sonnet · medium · ~15–20 turns · Light–moderate.**

### W10 — Optimizer results and apply-to-plan
**#329 P5, P5b, P6. Requires W9.**

Three commits inside one workstream:

**W10a — Roth result panel, end to end.** Path 1 (read from last build):
`roth_optimization` / `roth_strategy_result` are already attached to the plan
result, so this is a display change over existing data. **Scope to Roth only.**
*(opus · high · ~15–25 turns · Moderate.)*

**W10b — §4.7 disclosure badges.** Row-level badge for values that are live
optimizer output, plus a section banner stating the plan re-optimizes every
build. Built on `dashboard_source_truth_banners.js`, not a parallel indicator
system. **Separate commit, so a stalled apply path does not block work with
standalone value.** *(sonnet · medium · ~15–20 turns · Moderate.)*

**W10c — Apply-to-plan.** Optimizer patch in the existing `overrideFromRow()`
shape; construct a Planning Case with `source: "optimizer"` (one new enum value,
not per-optimizer) and hand it to `promotePlanningCase()`. Primary action "Let the
plan keep optimizing this", secondary "Lock in this schedule". Applied state is
*computed* by comparing the result against live row values — never a stored flag.
Un-apply is the reverse patch. Provenance stays in `localStorage`; the UI must not
imply it is durable.

**Scoping:** it writes plan data, so it invites a test-fix cycle. Cover one patch
shape (scalar adoption — Social Security) before the structural one (Housing).
*(opus · high · ~30–40 turns · **Heavy**.)*

Remaining result panels are repetitions of W10a's proven pattern, one per session.
**Do not batch them** — that rebuilds the heavy phase under a new name.

### W11 — Planning Levers retirement
**#329 §3.2 gate. Requires W10 (specifically W10b).**

Scope: retire `planning_levers_echo`; the Plan Features "Active Features" view
plus W10b's row badges together replace what the sheet showed — what the plan is
doing, and where each dial position came from.
Done: confirmed nothing else depends on it as the sole lever-provenance view.
**sonnet · low · ~8–12 turns · Light.**

### W12 — Off-state rendering
**#330 P7. Requires W4, W9.**

Scope: generalize `strategySectionGatedNote()` into a registry-driven
`featureGatedNote`; implement the three off-states (Hidden / Collapsed-with-note /
Disabled-in-place) chosen from declared data; enforce the no-hidden-data
invariant; inline switches on the gated note and on the owning page.
**The invariant is the work, and it needs a test per off-state.**
**sonnet · medium · ~15–25 turns · Moderate.**

### W13 — Left-nav realignment
**#330 P8 / Q6. Requires W12. Its own project.**

Scope: add Taxes and Family & Business nav groups; promote Housing out of
Spending, so "where I turn it on" matches "where I use it".

Files: `SECTION_REDIRECTS`, every `helpLink` target, `SUGGESTED_NEXT`, step
ordering in `dashboard.js`'s `STEPS`.

**This is the largest item in the plan and its entire risk is scope leak.** The
switch page (W4) is shippable without it; this is not shippable without the switch
page. **Ship W1–W12, use the result, then plan W13 against what the mismatch
actually feels like.** Do not let it share a session with W4.
**opus · high · ~40–60 turns · Heavy.**

### H1 — Housing PR 1: valuation as of the move year
**#331 B1–B6. Independent of W1–W13. Contains golden regen #2.**

- **B1** — thread `start_year` / `home_appr` / `inflation_general` through
  `plan_variant`; sites 1–2. Site 3 is a *deletion* of escalation, not an addition
  (OQ-2 resolved the budget to move-year dollars). *(sonnet · medium · 6–10 · Light.)*
- **B2** — deflate budget bounds in `screen.py`; `est_price_basis_year` on
  `ScreenedZip`; `acquisition_window` on the screen request. *(sonnet · medium · 6–10 · Light.)*
- **B3** — unit tests for B1–B2: escalation applied, rates correct per field,
  percentages untouched, `years_out=0` for a current-year move, budget deflated
  exactly once, funnel counts unchanged for a current-year window. **B2 before B3
  means a double-deflation cannot pass.** *(sonnet · medium · 6–10 · Light–moderate.)*
- **B4** — results display both years; P&I recomputed on the escalated price;
  the one-time dismissible notice. *(sonnet · medium · 6–10 · Light–moderate.)*
- **B5** — **golden-master regeneration.** Every optimizer result changes —
  objectives, rankings, very likely the rank-1 recommendation. Regenerate **one**
  representative fixture first and hand-verify its delta against a spreadsheet
  check of `(1 + home_appr) ** years_out`, then batch the rest. **Do not enter a
  regenerate-run-regenerate loop; a wrong rate looks exactly like a right one at
  scale.**

  **Know what a correct diff looks like before reading one.** The bias reverses in
  a specific direction: today the optimizer systematically prefers later moves,
  because a later move buys a today's-priced house further out and collects the
  appreciation free. After the fix, moves compare on equal footing, so
  **recommendations should shift earlier**. A diff that moves recommendations
  *later* is a red flag, not drift. The PR description must state the recompute
  explicitly — an uncalled-out drift of this size reads as a regression.
  *(opus · high · 10–20 · **Heavy**.)*
- **B6** — Spending screen re-estimate prompt and `lot_size_band`; audit
  `tools/housing_lab.py` for its own price-basis assumptions. *(sonnet · medium · 6–10 · Light–moderate.)*

### H2 — Housing PR 2: anchor flow
**#331 A1–A4, with #329 P7 folded in. Requires H1.**

- **A1** — per-anchor reserved slot in `run_multi_anchor_screen`, as a
  `per_anchor_quota` stage between `near_family` and `promoted`; two-pass fill
  (reserved pass in the user's declared anchor order, then the open pass in
  existing score order); `unrepresented_anchors` on `ScreenResult`. An anchor with
  no surviving ZIP is **skipped and recorded, never a failed run**. Costs nothing
  when the natural top-N already covers every anchor, which is why this went
  unnoticed. *(sonnet · medium · 6–10 · Light.)*

  **Two different gating rules here — do not conflate them.** *Anchor coverage* is
  a warning that never blocks: unchecking an anchor's last ZIP after seeing its
  price shows "Your selection no longer covers 60521" and *Continue* stays
  enabled. But *step 1 cannot be left until every enabled move has at least one
  selected ZIP* — that one is a real gate. The quota guarantees coverage of the
  **default** selection, which is what §1.1 broke; past that the choice is the
  user's.
- **A2** — `selected_zips` (1–10) on the wire; server-side validation that every
  entry appears in that move's `all_passing`, returning `{"success": false}`
  naming the ZIP rather than silently degrading into a smaller search. API stays
  `housing_optimize_v2` — the breaking half is on the *request*, so bumping a
  response id would be a misleading signal. `shortlist_size` leaves the request
  schema entirely but **survives internally** as `MultiAnchorRequest.shortlist_size`,
  a preview cap rather than a user-facing knob; the preview promotes
  `max(default_preview_size, len(anchors))`. *(sonnet · medium · 6–10 · Light–moderate.)*
- **A3** — the two-step panel. **The *Move n — when* row moves up into step 1**,
  which becomes "Where and when could you go?" (OQ-2a), with the window midpoint
  pricing the affordability filter (OQ-2b) and the reference year printed in the
  table header. Selection table, step gating, coverage warning,
  `HOUSING_OPT_STORAGE_KEY` → `retirement.housing_optimizer.v2`, client-side screen
  memo keyed on filter fingerprint.

  Step 1 is three rows per move (*where* / *when* / *what*), ending in **Find
  candidate locations**, which calls `POST /api/housing/zip-screen` once per
  enabled move and renders a **selection table** — checkbox rows pre-checked
  exactly as the quota promoted them, so *Continue* with no interaction reproduces
  today's behaviour plus the quota. One new column, **Anchor**
  (`nearest_anchor_zip`), with a *"covers {anchor}"* badge on reserved-pass rows,
  and a per-anchor coverage line above the table.

  **The reference-year disclosure is load-bearing, not decorative.** The header
  reads *"Estimated price — as of 2041, midpoint of 2036–2046"*. The midpoint
  filter can exclude a ZIP that would be affordable at the earliest year; naming
  the year is what keeps that exclusion visible rather than making it the same
  class of silent discard §1.1 exists to fix.

  **Validation splits across steps but the gate does not.** Anchor count and every
  year-window rule become step-1 rules; the rest stay on step 2. The Run button
  lives on step 2 and is disabled while any rule on **either** step fails, so the
  split cannot smuggle an invalid request through.

  **Folded in from #329 P7:** rename the two engines in panel copy — "Where to
  live" (this panel) and "When to move" (workbook Housing Comparison) — and state
  the question each answers and does not answer. Doing it here means the panel is
  opened once.

  **Read the three text-asserting Python functional tests first**, before touching
  the JS. *(opus · high · 15–25 · **Moderate–heavy**.)*
- **A4** — frontend tests: quota rendering, selection round-trip, stale-selection
  rejection, step gating, coverage warning does not block. *(sonnet · medium · 6–10 · Moderate.)*

---

## 5. Spec coverage check

| Spec requirement | Workstream |
|---|---|
| #329 definitions + reclassification | W1, W3 |
| #329 workbook structure, renames, `3C` split | W3 |
| #329 stable slugs | W2 |
| #329 UI section list, restored modules | W9 |
| #329 optimizer results in UI | W10a |
| #329 apply-to-plan, source enum, un-apply | W10c |
| #329 §4.7 disclosure | W10b |
| #329 housing engines kept + renamed (P7) | H2/A3 |
| #329 Tax Capacity placement | W0/V3, W3 |
| #329 Planning Levers retirement + gate | W11 |
| #330 `domain` axis + kind filter | W1, W4 |
| #330 registry join guards | W1 |
| #330 Plan Features page, admin disclosure | W4 |
| #330 `degrades_without`, enforcement test | W5 |
| #330 engine gate fix | W7 |
| #330 plan-flag unification, DAF/QCD | W6 |
| #330 40-of-49 optional | W8a, W8b |
| #330 off-states + no-hidden-data invariant | W12 |
| #330 build_impact on toggle change | W0/V1, W5 |
| #330 left-nav realignment | W13 |
| #331 valuation as of move year, all 7 sites | H1 |
| #331 anchor quota, two-step flow, timing move | H2 |
| #331 `housing_lab.py` audit, one-time notice | H1/B6, H1/B4 |

No spec requirement is unassigned.

---

## 6. Order of execution

Dependencies, stated as edges rather than drawn — the graph is not a tree and
ASCII misrepresents it:

```
W0   → W1, H1                    (pre-flight gates both streams)
W1   → W2, W4, W5                (catalog foundation fans out)
W2   → W3, W8a                   (slug gates regrouping AND new toggles)
W3   → W9
W4   → W12
W5   → W6, W7
W6   → W8b, W9
W7*  → W8a
W8a  → W8b
W9   → W10a, W12
W10a → W10b → W10c → W11
W12  → W13
H1(B1→B2→B3→B4→B5*→B6) → H2(A1→A2→A3→A4)
```
`*` = regenerates golden masters; lands alone.

Read that as: **W9 needs both W3 and W6. W8a needs both W2 and W7. W12 needs both
W4 and W9.** Those three joins are where a stream stalls if the other side is not
done, and they are the only places the order is not obvious from the numbering.

**Golden-master ordering — the one hard cross-stream rule.** W7, H1/B5 and
possibly W8b each move fixtures for unrelated reasons. Run them **in this order,
never concurrently, never in the same commit**:

1. **H1/B5** (housing escalation) — largest and best-understood delta, verifiable
   by hand against `(1 + home_appr) ** years_out`.
2. **W7** (engine gate) — deltas confined to two modules' participation.
3. **W8b** (if it moves fixtures at all) — by then the baseline is stable twice over.

Running H1/B5 first means the housing deltas are attributable before anything else
perturbs the fixtures. If W7 ran first, every housing delta would arrive on top of
an already-shifted baseline and the hand-verification in B5 would stop working.

**Parallelism.** The housing stream (H1, H2) shares no files with W1–W13 and can
run alongside it, subject only to the golden-master ordering above. Everything
else is sequential as drawn.

**Shippable checkpoints.** W3 (workbook is coherent), W4 (switch page is usable),
H1 (prices are correct), H2 (anchor flow works), W10c (optimizers apply), W12 (off
states are honest). Each is a reasonable place to stop.

---

## 7. Execution strategy — sessions, worktrees, agents, models, tools

The dominant cost in a 19-workstream plan is not the edits. It is **context that
accumulates and is then paid for on every subsequent turn**. Everything below
follows from that.

### 7.1 Sessions: one workstream, one session

Start a fresh session per workstream. A session that has finished W1 carries
W1's reads in every later turn whether or not they are still relevant, so
continuing into W2 in the same session pays for W1's context indefinitely.

- **Exception:** W10a → W10b may share a session (same files, same mental model).
  W10c gets its own regardless — it is heavy and correctness-critical.
- **Mid-task rule:** if a session passes roughly half its context before that
  workstream's tests are green, finish the current commit and start fresh rather
  than relying on compaction. Compaction preserves intent but loses the exact
  line numbers and signatures you are mid-edit on, which is when losing them
  costs most.
- The 1-hour prompt cache means a break in a session is cheap; **context growth
  within it is not**. Do not keep a session alive to "save the cache" — the cache
  is not the expensive part.

### 7.2 Worktrees: two long-lived, not nineteen

The plan has exactly two independent streams (§6): the catalog/UI stream
(W1–W13) and the housing stream (H1–H2). They share no files.

- Run **two worktrees**, one per stream, and keep each for the life of its
  stream. A worktree per workstream means a full checkout each time for no
  isolation benefit — the workstreams within a stream are sequential anyway.
- ⚠ **The git stash stack is shared across all worktrees in this repo.** Never
  use bare `git stash` / `git stash pop` — another session can pop your entry.
  Set work aside with a temporary WIP commit instead.
- The golden-master ordering in §6 is a cross-worktree constraint. It is the one
  thing the two streams must coordinate on, so agree the order before starting,
  not when a diff surprises someone.

### 7.3 Models and effort

Already per-workstream in §8. The rule behind the table:

- **sonnet · medium** for registry edits, CSV changes, renderer changes, and all
  test-writing. That is most of the plan.
- **opus · high** only for the six heavy workstreams (W6, W8b, W10c, W13, H1/B5,
  H2/A3). These are the ones where a wrong structural decision costs more than
  the model does.
- **sonnet · low** for W0 and W11 — verification and deletion, no design.
- Do **not** raise effort to compensate for missing context. If a task feels
  underspecified, the fix is reading the right 40 lines, not thinking harder
  about the wrong ones.

### 7.4 Subagents: use them as a context firewall

This is the highest-leverage tool choice in the plan, because of the file sizes
in `.claude/claude.md`.

- **Explore subagent for every "where is X" question.** A lookup in
  `dashboard.js` or `dashboard_decomp_row_model.js` returns a few line numbers to
  the main session instead of thousands of lines. The subagent's context is
  discarded; yours is not. Use it for locating call sites, finding which module
  owns a sheet, confirming a function's neighbours.
- **general-purpose subagent for W5's enforcement sweep.** The grep across `src/`
  for `module_enabled(` and raw `c['opt']` reads produces findings that need
  judgement per site. Have the subagent return **the fixture list**, not the raw
  matches, and write that list straight into the test so the sweep happens once
  ever rather than once per run.
- **Do not delegate the edits.** A subagent starts cold and re-derives the
  workstream's context, which is the expensive path. Delegate *reads and
  searches*; keep *decisions and edits* in the main session.

### 7.5 Tool discipline

- **Grep before Read. Always.** Then Read with `offset`/`limit` around the hit.
  `.claude/claude.md` lists the entry point for each large file.
- **`pytest -m "not slow"` is the working loop.** The full suite runs subprocess
  builds; save it for pre-commit.
- **Run long suites with `run_in_background`** and keep working rather than
  blocking on them.
- **`tools/regen_golden_master.py measure` before any `regen`.** `measure` prints
  the delta without writing; `origin` traces where a pin came from. The
  permission allowlist in `.claude/settings.json` permits the read-only
  subcommands and deliberately prompts on `regen`.
- **Batch independent shell calls** into one message — several `git`/`wc` checks
  in parallel cost one round-trip, not four.

### 7.6 The five ways this plan will overspend

In descending order of likely cost, each with its guard:

1. **Opening a large file linearly.** Guard: `.claude/claude.md`'s table; Explore
   subagent for lookups.
2. **Carrying a finished workstream's context into the next one.** Guard: one
   workstream per session.
3. **Regenerate-run-regenerate loops on golden masters** (W7, H1/B5, maybe W8b).
   Guard: `measure` first; verify one delta by hand; know the expected direction
   (H1/B5 should move recommendations *earlier*).
4. **Sweeping toggle combinations** (W2, W8a, W8b). Guard: pin two or three
   representative configurations. The space is combinatorial and the marginal
   build teaches nothing.
5. **Scope leak from W4 into W13.** Guard: they may not share a session. W4
   ships without W13; W13 does not ship without W4.

### 7.7 Environment changes already made

- **`.claude/claude.md`** gained three sections: verified line counts and the
  entry point for each large file; the test commands; and the golden-master
  `measure`-before-`regen` rule. This file is always loaded, so it reaches every
  session and every subagent without being asked for — which is why the
  large-file table lives there rather than only in this plan.
- **`.claude/settings.json`** (new, project-scoped and committed) allowlists the
  read-only and test commands this plan runs constantly — `pytest`, `npm test`,
  read-only `git`, `wc`/`ls`, and the non-destructive `regen_golden_master.py`
  subcommands — and explicitly routes `regen` to a prompt. Personal permissions
  stay in the uncommitted `settings.local.json`.

### 7.8 Environment changes you would need to make

These need your hands, not mine:

- **Prune `.claude/settings.local.json`.** It carries a one-off `Bash(sed ...)`
  allow entry from a past session that references `Version-10` paths and a
  temp-directory scratch file. It matches nothing now and is pure noise.
- **Consider `/config` → effort defaults.** This plan is mostly sonnet · medium;
  if your session default is higher, most workstreams will run hotter than the
  §8 table assumes.
- **Decide on Fast mode** for the six heavy workstreams. It does not downgrade
  the model, so it is a latency/throughput choice rather than a quality one.
- **`.claude/hooks/`** currently holds only `triage_interceptor.py`. If you want
  a guard that actually enforces §7.5 — for instance a `PreToolUse` hook on
  `Read` that warns when a path matches the large-file list without
  `offset`/`limit` — say so and I will write it. I have not added it unprompted
  because a hook that fires on every read is worth opting into deliberately.

## 8. Expected Claude Code usage

Per repo convention — relative to a 5-hour session on the Pro plan. **Proportions,
not measurements. Check `/usage` against these as execution proceeds.**

| Workstream | Model · effort | Turns | Weight |
|---|---|---|---|
| W0 | sonnet · low | 8–12 | Light |
| W1 | sonnet · medium | 20–30 | Light–moderate |
| W2 | sonnet · medium | 20–30 | Moderate |
| W3 | sonnet · medium | 20–30 | Moderate |
| W4 | sonnet · medium | 20–30 | Moderate |
| W5 | opus · high | 25–35 | Moderate–heavy |
| W6 | opus · high | 25–35 | **Heavy** |
| W7 | opus · high | 15–25 | Moderate (high review) |
| W8a | sonnet · medium | 15–20 | Moderate |
| W8b | opus · high | 30–40 | **Heavy** |
| W9 | sonnet · medium | 15–20 | Light–moderate |
| W10a | opus · high | 15–25 | Moderate |
| W10b | sonnet · medium | 15–20 | Moderate |
| W10c | opus · high | 30–40 | **Heavy** |
| W11 | sonnet · low | 8–12 | Light |
| W12 | sonnet · medium | 15–25 | Moderate |
| W13 | opus · high | 40–60 | **Heavy** |
| H1 (B1–B6) | mixed; B5 opus · high | 40–60 | **Heavy at B5** |
| H2 (A1–A4) | mixed; A3 opus · high | 33–55 | **Moderate–heavy at A3** |

**Six heavy items: W6, W8b, W10c, W13, H1/B5, H2/A3.** Do not run two in one
session. Each has a stated scope-down in §4 — use it; the scope-downs are the
difference between these estimates and roughly double.

**The three cheapest ways to overspend, and the guard for each:**

- **Opening a large file linearly.** `dashboard.js` (7,287), `dashboard_decomp_row_model.js`
  (5,188), `dashboard_decomp_housing_scenarios.js` (~1,800). Every workstream that
  touches one names the region to read. Read the region.
- **Sweeping toggle combinations.** W2, W8a and W8b all verify by building
  workbooks. Pin two or three representative configurations; the space is
  combinatorial and the marginal build teaches nothing.
- **Regenerate-run-regenerate loops.** Both golden workstreams. Verify one fixture
  by hand first. At scale a wrong rate is indistinguishable from a right one.

---

## 9. Open items carried into execution

- **V1–V3 (W0)** — must be answered before W1 writes `domain` values and before W3
  writes the section layout.
- **#331 backlog item, not in this plan:** automatic Move-2 strategy selection
  (try `cross_product`, fall back to `anchored` above `MOVE2_CROSS_PRODUCT_CAP`,
  report which ran). Deliberately excluded from H2/A3 as scope expansion landing
  in the same PR as the highest-risk change in that spec.
- **Deferred by #329, not planned:** chaining the two housing engines (location
  search feeding the schedule search); a YTD writeback driven by confirmed broker
  fills; a general stress-remediation optimizer; server-side Planning Cases.
- **Deferred by #330, not planned:** marking Build History snapshots
  unreproducible when their module set no longer matches; data-conditional
  auto-off.
