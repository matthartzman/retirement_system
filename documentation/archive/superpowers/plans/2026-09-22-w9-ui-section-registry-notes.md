# W9 — UI section registry: what was built, and the judgment calls

> Execution record for **W9** of
> `docs/superpowers/plans/2026-09-19-optimizers-modules-housing-master-plan.md`
> §4, implementing #329 P4 + #330. Requires W3, W6 — both landed on this branch.

## Scope, as the plan states it

> Scope: `strategySection()` registry edits to match #329 §3.3's UI list;
> restore Withdrawal Sequencing, Asset Location and Scenario Analysis (each
> its own tab); move HELOC to Assets & Protection; add Divorce/QDRO's
> workbook sheet; `navigation.js` redirects.
> **Cost driver:** the redirects are the fiddly part, not the registry.

## Triage of the five items PR #132 handed W9

PR #132's "What's left on the master plan" section named five inherited
items and explicitly asked this workstream to triage them against its own
scope rather than silently doing all five or dropping them. The call:

| Item | Call | Reasoning |
| --- | --- | --- |
| `rowsForStep()`'s hand-written HELOC gate (`dashboard_decomp_row_model.js`) | **IN SCOPE** | Directly entangled with "move HELOC to Assets & Protection" — touching HELOC's page context makes this a few-line generalization to read `flag_gates` like the two branches W6 already converted, not a new task. |
| Plan Features link rows for plan flags (HELOC, Hybrid LTC, DAF, QCD) | **IN SCOPE** | W6's own notes assign this here explicitly: "Adding the link rows is a UI change, not a refactor, and belongs with W9's UI section registry." `gate_ref`/`gate_enable_label` already carry everything a link row needs. |
| A real "any of these gates" bundle declaration, if `special_strategies`-style steps come back | **OUT — no consumer** | Nothing in #329 §3.3's UI list revives a bundle-gated step. W6 deliberately did not invent this field for a hypothetical; W9 doesn't create the hypothetical either. Stays deferred. |
| Hide the YTD tab within `spending_core` when Spending Tracker/YTD is off | **OUT — belongs to W12** | This is a `rowsForStep`/tab-visibility change matching W12's own scope line verbatim: "implement the three off-states (Hidden/Collapsed-with-note/Disabled-in-place) chosen from declared data." Building one more hand-written tab-hide here pre-empts the generalization W12 exists to do, the same over-building W6 itself cut back on its first Hybrid LTC pass. |
| Hybrid LTC soft dependency (`long_term_care_stress` → `degrades_without`) | **OUT — needs new plumbing, not a link row** | W8b's notes are explicit: satisfying it needs a *new catalog field* mapping `gate_ref` to its parsed config key, plus a parallel sweep test for plan-flag reads (today's sweep only recognizes module-toggle read spellings). That is W5-shaped dependency-declaration work, not UI registry work, and building it minimally here risks exactly the aspirational-declaration trap `test_every_soft_declaration_is_backed_by_a_swept_call_site` exists to catch. Deferred to whichever workstream next touches `degrades_without`. |
| Housing Location Search catalog entry (`src/housing/`, "Where to live") | **OUT — W1-shaped, per the task brief itself** | Confirmed against W8b's own notes: no `CATALOG` entry exists, and making one optional is a catalog addition plus UI-panel gating, not a toggle row. Not touched. |

## What "restore ... each its own tab" means

`_hidden()` vs `_visible()` (W3) is a **workbook nav** distinction — a hidden
sheet is still built and gated normally, just absent from the lettered tab
strip. All three of Withdrawal Sequencing (`retirement_strategy`), Asset
Location (`asset_location`) and Scenario Analysis (`what_if_analysis`)
already carry `optional=True`, an existing `module_key`, and an existing
`TRUE`-defaulted toggle row in `input/demo/client_optional_functions.csv` —
this is a pure nav-visibility change, not a gating change. Confirmed none of
the three collide with `test_every_optional_module_has_a_toggle_row` or the
build-gating tests before starting.

Note the master plan's phrase names three *workbook* restorations. Only two
of the three also get a **UI** panel per #329 §3.3's own final list ("Roth
Conversion · HSA Drawdown · Asset Allocation · Withdrawal Sequencing · Social
Security · Next Housing Move · Charitable Giving · Harvesting") — Asset
Location is not in that list and stays workbook-only, exactly as the spec's
§3.3 table has it (only Asset *Allocation* appears there, unchanged).

## What landed

Two commits, each independently tested and pushed.

**Commit 1 (workbook registry).** The three restorations above, plus a real
workbook sheet for Divorce/QDRO (`divorce_qdro`, previously `sheet=None` —
"a UI-only stress test with no workbook counterpart... the mirror image of
the workbook-only optimizers", #329 §1.2). `build_sheet39` reuses the exact
`run_scenario()` re-projection Sheet 16's own "Divorce/QDRO Asset Split" row
already computes (`divorce_split_yr`/`divorce_split_pct` overrides from the
plan's `scen_divorce_yr`/`scen_divorce_split_pct`), rather than inventing new
modeling — consistent with the global "no calculation changes except where a
spec names one" constraint. Five pinned workbook tab-strip tests updated for
the reshuffled letters.

**Commit 2 (UI registry).** `strategySection()` gains four new Optimize
entries (HSA Drawdown, Withdrawal Sequencing, Social Security, Harvesting),
HELOC moves to a real Assets & Protection nav step, the `rowsForStep()` HELOC
gate generalizes, and Plan Features gains plan-flag link rows.

## Judgment call — new Optimize panels reuse existing renderers, not new UI

#329 §3.3's own text warns that four of the five existing Optimize sections
are "input forms" with "nothing on screen to apply" (§1.3) — that asymmetry
is explicitly W10's subject to fix (Roth result panel first, then "one per
session" for the rest), not W9's. Building rich result displays for HSA
Drawdown/Withdrawal Sequencing/Social Security/Harvesting here would have
pre-empted that workstream and turned a "sonnet · medium · light-moderate"
registry edit into the kind of heavy, open-ended session #330's own phasing
table warns against. Instead, each new section is exactly what §3.3 asks for
— *visibility* — built from data pages that already exist:
`hsaWithdrawalPolicyBlock`/`taxLossHarvestingBlock`/`gainHarvestBlock` are
the same blocks the Spending workspace's "Withdrawal Order" tab already
rendered (extracted into `dashboard_decomp_strategy_workspace.js` so both
callers share one filter predicate per concept instead of duplicating it),
and the new `socialSecurityOptimizePanelHtml()` filters
`rowsForStep("income_retirement")` to its own section. This closes #330
§3.3's stated gap ("HSA Drawdown... currently reachable only by setting a
mode field with no visible consequence") without inventing the optimizer
result UI that gap's sibling problem — "nothing to apply" — asks W10 to
solve.

**None of the four is module-gated (`gate: null`).** The task brief's own
global constraint — "no switch may render a row invisible when that row
holds a user-entered value" — rules out gating a section whose fields may
already carry data (HSA Drawdown, Withdrawal Sequencing and Harvesting are
all `optional=True` modules a household may have used for years before this
workstream). This matches the existing precedent for Asset Allocation,
Next Housing Move and HELOC — every other optional-module Optimize panel
that is itself an input form, not a gated preview.

## Judgment call — the Plan Features link destination is a small lookup table, not a catalog field

`gate_ref`/`gate_enable_label` (W6) carry the CSV cell and its display name,
but not *which nav step renders that cell for editing*. The obvious generic
answer, `sourceStepForRow()` (the resolver `BUILD_IMPACT_SOURCE_STEP_IDS`
drives), gets HELOC right (`heloc_strategy`) but Hybrid LTC wrong: it
attributes `sec === "Hybrid LTC"` rows to `"ltc_stress"` for readiness-stats
purposes, while the actual editable row group renders on `assets_special`
(Other Assets and Liabilities), via a *third* hand-written gate
(`optionalModuleState()`'s `sec === "Hybrid LTC"` branch) that W6's notes
already named as out of its own two-branch scope. Rather than invent a new
catalog field for a four-entry mapping, or risk sending a household to the
wrong page, `PLAN_FLAG_DESTINATION_STEP` in
`dashboard_decomp_plan_features.js` names all four destinations directly —
the same three-line shape the "Open HELOC strategy page" button on
`assets_special` already hardcodes for the same reason.

## Verification

- `tools/regen_golden_master.py measure` — exact match, `+0.00` on both pins,
  measured after the workbook-registry commit and again after the
  Divorce/QDRO addition.
- `pytest -m "not slow"` — full suite green on the branch head (confirmed with
  a fresh, from-scratch dependency install — `numpy`, `scipy`, `pandas`,
  `openpyxl`, `lxml`, `pytest` — to rule out container-specific skips, the
  same caveat W8a's own verification section recorded).
- `tests/test_divorce_qdro_stress_sheet_functional.py` — the registration
  half (fast) plus `@pytest.mark.slow` subprocess builds proving the toggle
  actually gates the sheet, both on and off, not just that a build survives
  either way (the same strengthening W8b applied to the Housing Comparison
  toggle test).
- Five pinned workbook tab-strip tests updated
  (`test_workbook_numbered_section_tabs_functional.py`,
  `test_workbook_system_cleanup_and_widths_functional.py`,
  `test_advanced_planning_modules.py`) — the letters read directly off a real
  build rather than hand-computed, the same discipline W3's own notes
  describe for this exact kind of drift.
- `npm test` — 482/484; the two failures are the pre-existing
  `js_codemod_parser_offsets.test.mjs` environment difference W6/W8b's notes
  already recorded, reproduced identically with this diff stashed.
- `tests/frontend/plan_features.test.mjs` — 19/19 (15 existing + 4 new for
  the plan-flag link rows: a plan flag renders from the taxonomy alone with
  no toggle row, respects the kind filter, is never listed twice even if a
  toggle row somehow also names it, and its kind reaches the filter chips
  even when no toggle module shares it).
- `node tools/js_codemod/census.mjs --check` — regenerated after each
  frontend commit, no drift.

## What is still open

The three items this workstream deliberately deferred (bundle-gate
declaration, YTD tab hide, Hybrid LTC soft dependency) — each with its
reasoning recorded in the triage table above, not silently dropped. Housing
Location Search's missing `CATALOG` entry remains untouched, confirmed
W1-shaped by both W8b's notes and this workstream's own read of the task
brief.

## Consequences for later workstreams

- **W10** (Optimizer results and apply-to-plan) is unblocked — its own scope
  line already requires W9. The four new Optimize panels this workstream
  added are exactly the "input form, nothing to apply" shape §1.3 describes;
  W10a's Roth result panel is the proven pattern the rest, including these
  four, will eventually follow "one per session."
- **W12** (Off-state rendering) inherits the YTD tab-hide item explicitly,
  plus the general lesson that a plan-flag's or bundle's off-state needs the
  generalized `featureGatedNote`/three-state mechanism W12 exists to build,
  not another one-off hand-written branch.
- Whichever workstream next extends `degrades_without` inherits the Hybrid
  LTC soft-dependency item, with the shape of what it needs already scoped
  (a new field mapping `gate_ref` to its parsed config key, plus a sweep for
  plan-flag reads) rather than left to be rediscovered.
