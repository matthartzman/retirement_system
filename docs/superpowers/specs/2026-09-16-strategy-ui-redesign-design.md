# Strategy Section UI Redesign

Ticket 323. Date: 2026-09-16.

## Problem

The Strategy section has drifted into a set of screens that do not match how the
work is actually done.

- The left nav's **Strategy** group shows three entries — Distribution Strategy,
  State Residency Analysis, Special Strategies — while eleven further strategy
  and stress-test screens exist as `hidden: true` steps reachable only through
  an eleven-button launcher grid embedded inside one of those pages.
- The **Stress Tests** group is declared in `STEPS` but every member is hidden,
  so the group never renders. Monte Carlo, Survivor, Long-Term Care and Divorce
  have no nav presence at all.
- **Distribution Strategy** renders exactly one thing, `renderPlanningLevers()`.
  It and "Strategy Levers" are the same screen under two names.
- **State Residency Analysis** is two unrelated things bolted together: a
  residency-over-time schedule that belongs with Housing, and a set of
  state-comparison inputs that are almost entirely dead.
- **Withdrawal Order** is reachable both as a Spending workspace tab and from
  the Strategy launcher grid.

## Goals

Three Strategy destinations that map to the three things a user actually does:
decide a strategy, test its resilience, compare alternatives. Every screen
reachable from the nav. No destination reachable under two names.

## Non-goals

No changes to the projection engine, the workbook, or any calculation. No new
optimizers. This is a navigation and composition change; every section body
reuses an existing renderer unchanged.

---

## 1. Navigation

The Strategy group becomes three step buttons with no indented children:

```
Strategy
  Optimize        strategy_optimize
  Stress Test     strategy_stress
  Scenarios       strategy_scenarios
```

The "Stress Tests" group label disappears; its four members become
`group: null`.

### Old step ids survive as shells

The old ids are **not** deleted from `STEPS`. `rowsForStep()` and
`sourceStepForRow()` (`dashboard_decomp_row_model.js`, the `switch` at ~1440)
key every plan row off those ids, and so do the Field Finder, the build change
summary, and every `source-jump` button in the app. Deleting `roth_conversion`
as an id would orphan row routing across unrelated screens.

So `distribution_strategy`, `state_residency` and `special_strategies` flip to
`group: null, hidden: true`. The rest are already in that state. Only three new
`STEPS` entries are added.

---

## 2. Section-anchored redirects

Roughly thirty buttons, `helpLink` entries and `SUGGESTED_NEXT` values navigate
to the old ids. Redirecting them to a flat step id would drop the user at the
top of a four-section screen.

Add a `SECTION_REDIRECTS` map in `frontend/js/navigation.js`, alongside the
existing `WORKSPACE_TAB_REDIRECTS`. It resolves to a step id plus a section key,
opens that collapsible, and scrolls to it.

| Old id | Lands on | Section opened |
| --- | --- | --- |
| `distribution_strategy`, `investment_strategy` | Optimize | *(top)* |
| `roth_conversion` | Optimize | Roth Conversion |
| `allocation_assets`, `allocation_policy` | Optimize | Asset Allocation |
| `entity_charitable` | Optimize | Charitable Giving |
| `heloc_strategy`, `special_strategies` | Optimize | HELOC |
| `monte_carlo_options` | Stress Test | Monte Carlo |
| `survivor_stress` | Stress Test | Survivor |
| `ltc_stress` | Stress Test | Long-Term Care |
| `divorce_options` | Stress Test | Divorce Planning |
| `planning_levers` | Scenarios | Strategy Levers |
| `scenarios` | Scenarios | Scenario Change Sets |
| `planning_workbench` | Scenarios | Planning Workbench |
| `state_residency`, `timing_tax` | Housing | State residency over time |
| `withdrawal_strategy` | Spending Model | *(tab: Withdrawal Order)* |

`withdrawal_strategy` moves from `STEP_REDIRECTS` to `WORKSPACE_TAB_REDIRECTS`,
so it lands on the Spending workspace tab that already owns it rather than
bouncing through Distribution Strategy.

Every existing caller keeps working and lands precisely. No call site is
rewritten.

---

## 3. The three screens

Every section is a collapsible heading with a **lazy body**: while collapsed it
renders a stub, and the real renderer runs on first open and on every pass while
open.

Open state is held in memory and persisted per section to `localStorage`.
Memory is the source of truth, not storage. If a storage write throws (private
mode, blocked site data, quota) and storage were authoritative, the persisted
map would stay stale while the DOM had already toggled; `renderMain()`'s restore
pass would then flip the element back, firing another toggle event, which would
fail to persist again — an unbounded render loop in exactly the environment the
`try`/`catch` exists to tolerate. A toggle that changes nothing is also a no-op,
as a second guard against re-entry.

On a first visit, the first section a reader can actually use opens by default,
so landing on a screen shows content rather than a stack of collapsed bars.
Gated-off sections are skipped when picking it — this matters on Optimize, whose
first section is module-gated, where defaulting that one open would greet a
reader with an enable-note and everything else collapsed. Once the reader opens
or closes anything, their stored choice wins from then on.

Lazy rather than eager because `renderMain()` re-renders the whole tree on every
field edit, and `renderAllocationRecommendation()` alone emits the mode note,
holding-period settings, the full allocation-policy field set, the asset-class
selection table, a coverage callout, an optimizer panel and the total-wealth
table. Stacking four such bodies eagerly would multiply per-keystroke cost on
the heaviest screen in the app.

### Section gating

Every section gates on `stepGatedByOptionalModule(shellId)` — the same
server-declared `module_catalog.dashboard_step → moduleGates.step_gates` map
every other nav surface already uses. No section hand-writes a module key, so a
future optional module is covered automatically. A gated-off section shows the
existing "enable it on Optional Modules" note in place of its body; that copy is
lifted verbatim from `renderSpecialStrategies()` before that function is
deleted.

`stepGatedByOptionalModule()`'s `special_strategies` special case is deleted —
that step is no longer a nav destination, and the bundle-visibility rule it
encoded is superseded by the screen-level rule below.

### Optimize (`strategy_optimize`)

| Section | Body | Gated by |
| --- | --- | --- |
| Roth Conversion | `renderRothConversion()` | `roth_conversion_plan` |
| Asset Allocation | `renderAllocationRecommendation()`, with the nested "Allocation policy settings" details | never — `asset_allocation` is not optional |
| Charitable Giving | `renderEntityCharitable()` | `charitable_giving` |
| HELOC | `renderFields("heloc_strategy")` | `heloc_enabled` plan-data flag, via the existing `heloc_strategy` special case |

Because Asset Allocation is never gated, the Optimize screen always has at least
one live section and is never itself hidden.

The Asset Allocation body is `renderAllocationRecommendation()` alone. An
earlier draft of this spec paired it with `allocationModeHtml()`; that was
wrong. `renderAllocationRecommendation()` already opens with
`renderCurrentAllocationModeNote()`, which is a one-line wrapper returning
`allocationModeHtml()`, so pairing them renders the mode selector twice.

There is no Social Security section. The only Strategy-side Social Security
artifact was a link to the People and Income page; the Social Security claiming
optimization itself is produced in the workbook by the 9×9 claim-age grid sweep
in `src/reporting/sheets_strategy.py`, and is unaffected. The
`ssClaimAgeCoordinationSummaryHtml()` line at the top of `renderRothConversion()`
is removed along with the function itself — it has exactly one caller and no
test or CSS depends on it.

### Stress Test (`strategy_stress`)

| Section | Body | Gated by |
| --- | --- | --- |
| Monte Carlo | `renderMonteCarloOptions()` | `market_luck_stress_test` |
| Survivor | `renderSurvivorStress()` | `survivor_stress_test` |
| Long-Term Care | `renderLtcStress()` | `long_term_care_stress` |
| Divorce Planning | `renderDivorceOptions()` | `divorce_qdro` |

All four are optional, so unlike Optimize this screen can end up with no live
sections. `strategy_stress` is therefore itself gated: hidden when all four
modules are off. This mirrors the `special_strategies` bundle rule being
deleted, but derives the module list from `moduleGates.step_gates` rather than
hand-listing it.

The Monte Carlo heading is renamed from the current step title "Probability
Analysis" to match the brief and the rest of the app's vocabulary.

### Scenarios (`strategy_scenarios`)

| Section | Body | Gated by |
| --- | --- | --- |
| Strategy Levers | `renderPlanningLevers()` | never |
| Scenario Change Sets | `renderScenarios()` — templates, saved sets, economy, home sale, housing move optimizer | `what_if_analysis` |
| Planning Workbench | `renderPlanningWorkbench()` | never |

Scenario Change Sets keeps a home so the housing move optimizer stays reachable
and the Housing page's existing link to it still resolves.

### Housing (`spending_mortgage_events`)

Gains one collapsible, "State residency over time", rendering
`renderResidencySchedule()`, placed after the "Current home" section.

---

## 4. Code removed

- `renderDistributionStrategy()` — a one-line wrapper around
  `renderPlanningLevers()`.
- `renderSpecialStrategies()` — replaced by two Optimize sections.
- `renderStateResidency()`'s State Comparison half.
- `ssClaimAgeCoordinationSummaryHtml()` and its call site.
- The dead State Comparison block in `renderScenarios()`
  (`dashboard_decomp_housing_scenarios.js`). It filters `rowsForStep("scenarios")`
  for `section === "State Comparison"`, but that switch case returns only
  `Scenarios`, `Model Constants/home_sale` and `Other Assets/home` rows — State
  Comparison rows route to `state_residency`. The filter is always empty and the
  block has never rendered.
- `renderPlanningLevers()`'s "Strategy · decide" and "Stress tests ·
  resilience" feature-card hub, and with it `leverNavButton()`. With real nav
  entries for all eleven destinations, an in-page launcher grid is precisely the
  duplication this redesign removes. The per-lever `Source` jump buttons stay —
  they point at input pages, not at strategy screens.

New code lands in a new `frontend/js/dashboard_decomp_strategy_workspace.js`.
The `dashboard_decomp_` prefix is load-bearing, not cosmetic: `tests/_decomp_dashboard.py`
globs `dashboard_decomp_*.js` to assemble the "full dashboard source" that every
content-assertion test reads, so a module outside that pattern would be invisible
to them. `dashboard.js` only
loses lines; `DASHBOARD_JS_MAX_LINES` drops to match in the same commit, because
`test_ratchet_is_not_slack` fails if more than 500 lines of headroom open up.

---

## 5. Verification of the two "drop" claims

### State Residency Analysis — confirmed redundant, with one live wire

The page is `renderResidencySchedule()` plus seven `State Comparison` rows. Of
those seven:

| Row | Status |
| --- | --- |
| `target_state` | Read into `c['residency_target_state']` at `src/data_io.py:1052` and **never consumed**. Dead. |
| `homeowners_insurance/target_state_annual`, `/notes` | No backend reader. Dead. |
| `auto_insurance/target_state_annual`, `/notes` | No backend reader. Dead. |
| `homeowners_insurance/current_state_baseline_annual` | Dead — the homeowners baseline comes from `Housing/current_home` at `src/data_io.py:1044`. |
| `auto_insurance/current_state_baseline_annual` | **Live.** `src/data_io.py:1056` uses it as the fallback auto-premium baseline for the workbook's "Auto Ins. Delta" column when no Auto insurance policy exists. |

The workbook's State Residency sheet computes all states in `STATE_TAX_RULES`
regardless of `target_state`, which is why the target-state inputs never
mattered.

**Resolution.** The live auto-insurance baseline moves to the Insurance page by
retargeting it in `sourceStepForRow`'s `annuity_death_benefits` case — a
UI-routing change only, so `src/data_io.py` is untouched and no plan-data
migration is required. It lands beside the Auto policies it falls back from.

The six dead rows stay in the CSV. Removing them would need a
`plan_data_migration` entry for no functional gain; they simply stop being
rendered.

### Withdrawal Order — redundant as a Strategy destination only

`renderWithdrawalStrategy()` is the only editor for the bucket draw-order table,
HSA withdrawal timing and mode, tax-loss harvesting, gain harvesting and the
spousal rollover election. Nothing else edits those rows.

**Resolution.** It stays as the Spending workspace's "Withdrawal Order" tab and
leaves Strategy scope entirely. Its launcher button disappears with the hub, and
`withdrawal_strategy` redirects to the Spending tab rather than to a Strategy
screen.

---

## 6. Backend

`src/module_catalog.py`'s `state_residency` module sets `dashboard_step=None`.
The module and workbook sheet "13. State Residency" both survive; it simply no
longer owns a nav step.

It cannot point at Housing instead: `stepGatedByOptionalModule()` hides whatever
step a module claims when that module is off, which would hide the entire
Housing page whenever State Residency is disabled.

Every other module keeps its `dashboard_step`, because those shell ids still
exist in `STEPS` and the new screens gate each section by calling
`stepGatedByOptionalModule(oldStepId)`.

---

## 7. Gaps this redesign must also close

1. **Nav readiness badges.** The Strategy group's badge sums `stepStats()` over
   its steps, and `stepStats(id)` calls `rowsForStep(id)`. The three new ids own
   no plan rows — every row still routes to a shell id — so Strategy would
   permanently show zero missing-required fields, silently losing a readiness
   signal that every other nav group provides. `rowsForStep()` must union the
   constituent ids for the three new steps; `stepStats()`, the group badge and
   the Field Finder then all work unchanged. **This is the only item requiring
   genuinely new logic rather than rewiring.**

2. **Plan-independent access.** `planning_workbench` is in
   `PLAN_INDEPENDENT_STEPS` and is reached by the "Compare & Decide" button in
   every page header, including before a plan is loaded. `strategy_scenarios`
   must join that list or the button breaks pre-plan.

3. **`AUTOSAVE_STEPS`** (`navigation.js`) lists `distribution_strategy`,
   `state_residency` and `special_strategies`. It needs the three new ids.

4. **`SUGGESTED_NEXT`** chains `distribution_strategy → state_residency →
   reports_and_review`. `state_residency` is no longer a destination; the chain
   becomes `strategy_optimize → strategy_stress → reports_and_review`.

5. **Housing page prose** names the path "Strategy → Scenario Change Sets" in a
   link; it becomes "Strategy → Scenarios → Scenario Change Sets".

6. **Residency dirty badge.** `residencyScheduleChanged` is checked by the
   global unsaved-changes guard but is absent from `stepStats()`, so editing the
   residency table never raises an "Edited" badge on its nav entry. Since the
   table is moving to Housing anyway, add
   `if (id === "spending_mortgage_events" && residencyScheduleChanged) d.push({})`
   to `stepStats()`.

---

## 8. Tests affected

| File | Why |
| --- | --- |
| `tests/test_distribution_strategy_buttons_regression.py` | Asserts on the removed hub buttons. |
| `tests/test_planning_levers_layout_functional.py` | Asserts on the levers page layout. |
| `tests/test_planning_levers_module_gating.py` | Its `LEVER_NAV_STEPS` list and `leverNavButton()` both die with the hub. The gating contract it protects moves to the new screens' section gates and must be re-asserted there, not dropped. |
| `tests/test_planning_workbench_consolidation_functional.py` | Workbench becomes a section. |
| `tests/test_optional_module_gating.py` | `state_residency` loses its `dashboard_step`. |
| `tests/frontend/step_help_live_links.test.mjs` | Help links retarget. |
| `tests/fixtures/frontend_source_grep_baseline.json` | Source census regenerates. |
| `tests/test_frontend_size_ratchet.py` | `DASHBOARD_JS_MAX_LINES` drops to the new size. |

New coverage: section gating on all three screens, `SECTION_REDIRECTS`
resolution for every row of the table in §2, and `rowsForStep()` aggregation for
the three new ids.

---

# Implementation Plan

Six phases, ordered so the app stays working at every commit. Phases 1–3 are
additive: the new screens go up while the old steps still exist as shells, so
nothing is deleted until the replacements are proven. Phase 5 is the only
destructive one.

Verification commands used throughout:

```
pytest -m "not slow"
npm test
```

## Phase 1 — New module and the three screens

Create `frontend/js/dashboard_decomp_strategy_workspace.js` (see the naming note
in §4) and register it in `frontend/index.html` alongside its siblings:

- `strategySection(key, title, renderFn, gateStepId)` — the lazy collapsible
  primitive. Renders a `<details>` whose body is a stub unless open; reads and
  writes open state in `localStorage` under a per-section key; short-circuits to
  the "enable it on Optional Modules" note when
  `stepGatedByOptionalModule(gateStepId)` is true.
- `renderStrategyOptimize()`, `renderStrategyStress()`, `renderStrategyScenarios()`.
- The usual `export` + `Object.assign(window, …)` bridge, matching every other
  `dashboard_decomp_*` leaf.

Add three `STEPS` entries with `group: "Strategy"`; flip `distribution_strategy`,
`state_residency`, `special_strategies` to `group: null, hidden: true`; set the
four Stress Tests members to `group: null`. Add three `renderMain()` branches.
Add the `strategy_stress` all-modules-off gate to
`stepGatedByOptionalModule()`.

At the end of this phase both old and new routes work. Nothing is removed.

**Model: Opus 5.** The lazy-section primitive is the one new abstraction in the
project and everything else composes on top of it; `renderMain()`'s existing
`_dOpen` open-state capture has to be reconciled with per-section persistence,
which is the subtle part.
**Effort: high. Estimated turns: 7–9.**

## Phase 2 — Redirects and reference retargeting

`SECTION_REDIRECTS` in `navigation.js` per the table in §2, resolving to
`{step, section}` and opening plus scrolling to that collapsible. Move
`withdrawal_strategy` from `STEP_REDIRECTS` to `WORKSPACE_TAB_REDIRECTS`. Update
`AUTOSAVE_STEPS`, `SUGGESTED_NEXT`, the three `helpLink` entries pointing at
`distribution_strategy`, and the Housing page's "Strategy → Scenario Change
Sets" prose.

**Model: Sonnet 5.** Mechanical once the table in §2 is fixed; the risk is
missing a call site, which grep covers.
**Effort: low. Estimated turns: 3–4.**

## Phase 3 — Row routing and readiness badges

Teach `rowsForStep()` to union constituent ids for the three new steps.
`stepStats()`, the Strategy group badge and the Field Finder then work unchanged
— this is the fix for gap §7.1. Add `strategy_scenarios` to
`PLAN_INDEPENDENT_STEPS` (gap §7.2). Add the `residencyScheduleChanged` line to
`stepStats()` (gap §7.6).

**Model: Opus 5.** The only genuinely new logic in the project. `rowsForStep()`
is a hub function with high fan-in — the Field Finder, the change summary and
every `source-jump` button read through it, so an aggregation that double-counts
rows would corrupt the progress percentage app-wide.
**Effort: medium. Estimated turns: 4–6.**

## Phase 4 — Housing, Insurance, and the module catalog

Add the "State residency over time" collapsible to `renderSpendingHousing()`.
Retarget `State Comparison/auto_insurance/current_state_baseline_annual` in
`sourceStepForRow`'s `annuity_death_benefits` case. Set
`dashboard_step=None` on the `state_residency` module in
`src/module_catalog.py`.

**Model: Sonnet 5.** Three small, well-specified edits in three files.
**Effort: low. Estimated turns: 2–3.**

## Phase 5 — Deletions and the ratchet

Remove everything in §4: `renderDistributionStrategy()`,
`renderSpecialStrategies()`, `renderStateResidency()`'s State Comparison half,
`ssClaimAgeCoordinationSummaryHtml()` and its call site, the dead State
Comparison block in `renderScenarios()`, and the levers hub plus
`leverNavButton()`. Delete the `special_strategies` case from
`stepGatedByOptionalModule()`. Drop each removed name from its module's
`Object.assign(window, …)` bridge. Lower `DASHBOARD_JS_MAX_LINES` to the new
line count in the same commit — `test_ratchet_is_not_slack` fails above 500
lines of headroom.

**Model: Sonnet 5.** Mechanical, but every removal must also leave the window
bridge, and a stale bridge entry throws at load. Run `npm test` after each
removal rather than batching.
**Effort: medium. Estimated turns: 4–5.**

## Phase 6 — Tests

Update the eight files in §8. Regenerate
`tests/fixtures/frontend_source_grep_baseline.json`. Add new coverage: section
gating on all three screens, `SECTION_REDIRECTS` resolution for every row of the
§2 table, and `rowsForStep()` aggregation for the three new ids.

`test_planning_levers_module_gating.py` needs judgment rather than deletion. It
protects a real contract — a module-gated destination must never be offered
while its module is off — that was previously carried by `leverNavButton()` and
now lives in `strategySection()`'s gate. Re-assert it against the new screens;
do not drop the file with the hub.

**Model: Opus 5** for the gating contract migration, **Sonnet 5** for the
fixture regeneration and the mechanical assertion updates.
**Effort: medium. Estimated turns: 5–7.**

## Totals

| Phase | Model | Effort | Turns |
| --- | --- | --- | --- |
| 1 — New module and screens | Opus 5 | High | 7–9 |
| 2 — Redirects | Sonnet 5 | Low | 3–4 |
| 3 — Row routing and badges | Opus 5 | Medium | 4–6 |
| 4 — Housing, Insurance, catalog | Sonnet 5 | Low | 2–3 |
| 5 — Deletions and ratchet | Sonnet 5 | Medium | 4–5 |
| 6 — Tests | Opus 5 / Sonnet 5 | Medium | 5–7 |
| **Total** | | | **25–34** |

Turn estimates include test-and-fix loops but assume no scope change. The two
most likely overruns are Phase 1, if per-section open-state persistence
conflicts with `renderMain()`'s existing `_dOpen` capture, and Phase 3, if
`rowsForStep()` aggregation turns out to double-count rows that route to more
than one shell id.

## Sequencing note

**Execution order is 4 → 1 → 2 → 3 → 5 → 6**, not the numbering above.

The original ordering was wrong. `frontend/js/dashboard.js` sits at exactly the
`DASHBOARD_JS_MAX_LINES` ratchet with zero headroom, and Phase 1 adds roughly 36
lines to it (three `STEPS` entries and three `renderMain` branches). The lines
Phase 1 needs are precisely the ones Phase 5 was scheduled to free, so Phase 1
as originally sequenced could not commit green, and
`test_frontend_size_ratchet.py` forbids raising the ceiling to compensate.

Resolution: Phase 4 runs first, so Housing owns the residency table. Phase 1
then deletes `renderStateResidency()` (~30 lines), `renderSpecialStrategies()`
(~17 lines) and the three superseded `renderMain` branches (~6 lines) in the
same commit that adds the new screens — net ~17 lines below the ratchet, which
drops to match. Those three deletions move out of Phase 5; Phase 5 keeps the
rest.

Phase 5 must still come after Phase 2, since the redirects are what keep the
deleted screens' inbound links alive. Phase 6 can start after Phase 1 for the
new coverage, but its updates to the eight existing files must land with or
after Phase 5.
