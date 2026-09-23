# W12 — Off-state rendering: what was built, and the judgment calls

> Execution record for **W12** of
> `docs/superpowers/plans/2026-09-19-optimizers-modules-housing-master-plan.md`
> §4, implementing #330 P7. Requires W4, W9 — both landed on this branch.

## Scope, as the plan states it

> Scope: generalize `strategySectionGatedNote()` into a registry-driven
> `featureGatedNote`; implement the three off-states (Hidden /
> Collapsed-with-note / Disabled-in-place) chosen from declared data; enforce
> the no-hidden-data invariant; inline switches on the gated note and on the
> owning page.
> **The invariant is the work, and it needs a test per off-state.**

Spec source: `docs/superpowers/specs/2026-09-19-modular-feature-nav-design.md`
§5.2/§5.3 (the three-off-states table and the module-toggle/plan-flag
unification), and §1 observation 4 (the Insurance In Force worked example).

## Triage of the two items PR #132 handed W12

PR #132's "What's left on the master plan" section named two inherited
items and asked this workstream to triage them against its own scope, the
way W9 triaged its own five, rather than assuming both belong here.

| Item | Call | Reasoning |
| --- | --- | --- |
| Hide the YTD tab within `spending_core` when Spending Tracker/YTD is off | **IN SCOPE** | This is exactly a "the module owns a section inside a page that stays visible" off-state (§5.2's second row) — Collapsed-with-a-note, built on the same `featureGatedNote()` this workstream exists to generalize. W9's own triage note named this as belonging here verbatim. |
| Hybrid LTC soft dependency (`long_term_care_stress` → `degrades_without`) | **OUT — not off-state-rendering work** | W9's own triage already characterized this precisely: it needs "a *new* catalog field mapping `gate_ref` to its parsed config key, plus a parallel sweep test for plan-flag reads... W5-shaped dependency-declaration work, not UI registry work." Nothing in that description is about *rendering* an off-state — it is about extending W5's enforcement-test sweep (`test_every_soft_declaration_is_backed_by_a_swept_call_site`) to recognize a plan-flag read site in Python (`sheets_stress.py`'s configured-policy column) the same way it already recognizes `module_enabled(`/`c['opt']` reads. Forcing it into W12 would be exactly the aspirational-declaration trap that test exists to catch: a `degrades_without` entry with no swept call site backing it. Still deferred, to whichever workstream next extends `degrades_without` — the shape of what it needs is already scoped by W9, not rediscovered here. |

## What was found reading the code first (per the task's own instruction)

The brief said: read what `strategySectionGatedNote()` and the sections it
gates actually do before generalizing, rather than trusting the plan's or
the PR's characterization. Three things surfaced that the plan's phrasing
didn't anticipate:

**1. `strategySectionGatedNote()` was already partially generalized.**
W6/W9 had already replaced its hand-written `if (gateStepId ===
"heloc_strategy")` branch with a read of `moduleGates.flag_gates` — the note
was already registry-driven for the *plan-flag* half. What remained
un-generalized: the *module-toggle* half still only ever said "enable X on
Plan Features," with no inline switch for either mechanism (§5.1: "It
should offer the switch inline, because the user who is reading that note
has already decided" — not yet true for either kind before this workstream).

**2. The no-hidden-data invariant was not merely unenforced somewhere — it
was actively being violated, and the spec's own §1 observation 4 was
describing a real, current bug, not a hypothetical.** Three concrete
call sites returned a static "this is hidden" message (or silently omitted
a group) in place of the gated rows, with no check for entered data at all:

- `renderInsurancePolicies()` (`dashboard_decomp_estate_insurance.js`) — when
  `existing_life_insurance` is off, this used to hide **every** Insurance In
  Force row, including Disability, LTC, Umbrella, Auto, Home, and P&C
  policies that module has nothing to do with. This is the spec's own named
  example, word for word: "a household can enter disability policies and
  have them vanish behind a switch named for life insurance."
- `renderAssetsSpecial()` (`dashboard_decomp_assets_other.js`) — the 529
  Plans, Equity Compensation, and LTC/Life Policy groups each `return`ed
  with nothing rendered when their gate was off, regardless of data.
- `renderEntityCharitable()` (`dashboard_decomp_estate_insurance.js`) — gated
  its *entire* page render on `charitable_giving`'s own module toggle, which
  took DAF and QCD down with it even though each has its own independent
  plan-flag gate and can be on (with data) while `charitable_giving` itself
  is off. This directly undoes what W6 already fixed on the *data* side: the
  catalog's own comment on `charitable_giving` says "DAF rows simply stop
  disappearing when this module is off" — true of the CSV gate, but the page
  was still gating entry to the whole render on the same toggle.
- `renderFields()` (`dashboard_decomp_row_model.js`, the search-mode/generic
  step renderer used by several steps including `assets_special` and
  `entity_charitable` when a search is active) carried the same shape of
  bug for `divorce_options`, `ltc_stress`, every plan-flag-gated step
  generically (via a loop over `moduleGates.flag_gates` — already
  reasonably registry-driven, just still hide-only), and `entity_charitable`
  again.

None of these were an "unfinished W12," in the sense of a declared
mechanism nobody had wired up yet — they were the *actual current
production behavior*, silently dropping a household's own data whenever the
right module happened to be off. Fixing them (not merely building the
mechanism and leaving the call sites as they were) is treated as the literal
content of "enforce the no-hidden-data invariant," per the task brief's own
instruction that the invariant "is the work."

Two of the four sites (`renderInsurancePolicies`, `renderAssetsSpecial`)
also needed `rowsForStep(..., { includeInactive: true })` instead of the
default call: these rows are `csv_sections`/`Hybrid LTC`-matched by
`optionalModuleState()`, so `rowsForStep()`'s own default active-only filter
was *already* dropping them before the page-level `return` even ran. Fixing
only the `return` without this would have "fixed" the bug into an empty
`<details>` block instead of a visible one. `renderEntityCharitable()`
didn't need it — `charitable_giving` has no `csv_sections` (W6 deliberately
removed the one it had, for DAF), so `optionalModuleState()` never touches
`entity_charitable`'s own rows in the first place.

**3. `moduleOwnedRows()`/`enteredRowCount()` (W4, `dashboard_decomp_
plan_features.js`) already did most of the "how many rows are affected"
work the spec's Collapsed-with-a-note row asks for** ("the note says how
many rows are affected"). `enteredRowCount()` is reused as-is (called as a
bare global, the established cross-file pattern in this codebase); nothing
new was built for it. `moduleOwnedRows()` itself was not reused — it only
resolves a module's rows via `dashboard_step`/`section_gates`, neither of
which covers Hybrid LTC/DAF/QCD (plan flags with no `dashboard_step`) or the
per-group slices this fix needs (`renderAssetsSpecial()` renders three
separately-gated groups off one step's rows) — each fixed call site already
has its own correctly-scoped row array in hand and passes it straight to
`featureGatedNote({ rows })`.

## Design: `featureGatedNote(key, opts)`

Single function, in `dashboard_decomp_strategy_workspace.js` (where
`strategySectionGatedNote()` lived), replacing it. Driven by the module's
own declared data rather than branching on the gate mechanism per call site:

- `opts.gateKind`/`opts.gateRef`/`opts.gateEnableLabel` let a caller that
  already resolved the gate (`strategySection()`, via a legacy step id and
  `moduleGates`) pass that declaration straight through — this keeps the
  existing `strategySection(key, title, bodyFn, gateStepId, defaultOpen)`
  contract, and every test that pins it
  (`tests/test_strategy_workspace_module_gating.py`,
  `tests/frontend/strategy_section_lazy_body.test.mjs`), completely
  unchanged. A caller with only a module key (every new off-page fix above)
  omits these and falls back to `planModuleTaxonomy()`, which already
  carries `gate_kind`/`gate_ref`/`gate_enable_label` per module (W9 added
  these for the Plan Features plan-flag link rows) — both paths read the
  same underlying catalog fields, so behavior is identical either way.
- Inline switch: `planFlagInlineSwitch()` finds the flag's own plan row (by
  `section`/`subsection`/`label`) and wires `editValue(row_index,'YES',
  null);saveAll(false);renderMain()` — the exact pattern Plan Features'
  own toggle button already uses. `moduleToggleInlineSwitch()` does the same
  against the toggle's row on `optional_functions`. When the row isn't
  loaded on the current page (a real possibility — e.g. a plan-flag note
  rendered on a page that doesn't happen to have that row in its own
  `rowsForStep()` result), the note falls back to `opts.destStep` (a
  navigable link, preserving `strategySectionGatedNote()`'s old behavior for
  the step-based callers) and finally to a generic Plan Features link when
  neither is available.
- `opts.rows`, when given, drives `enteredRowCount()` for the "N
  already-entered items are retained" text.

## What landed

One commit (plus this notes doc and the two ratchet/PR-body updates).

- `featureGatedNote()` + `planFlagInlineSwitch()`/`moduleToggleInlineSwitch()`/
  `gateDescriptorForStep()` (`dashboard_decomp_strategy_workspace.js`),
  replacing `strategySectionGatedNote()`.
- `renderFields()`'s divorce/LTC-stress/flag-gated/entity_charitable hide
  branches generalized into one `gateKey`/`gateOff` check that renders
  `featureGatedNote()` **and still renders the rows below it**
  (`dashboard_decomp_row_model.js`).
- `renderInsurancePolicies()` — Collapsed-with-a-note, every policy type,
  whether or not the household has entered any (`dashboard_decomp_
  estate_insurance.js`).
- `renderAssetsSpecial()`'s 529/Equity Compensation/Hybrid LTC groups —
  same fix, each independently (`dashboard_decomp_assets_other.js`).
- `renderEntityCharitable()` — stopped gating page entry on
  `charitable_giving`'s own toggle; `entityCharitableGatedRows()`'s existing
  per-flag DAF/QCD visibility now actually runs regardless of
  `charitable_giving`'s state (`dashboard_decomp_estate_insurance.js`).
- The YTD tab-hide (`spending_dashboard.js`'s `renderSpendingWorkspace()`):
  "Actual Spending (YTD)" and "Spending Analysis" tab bodies show
  `featureGatedNote('spending_tracker_ytd', ...)` when the bundle
  (`spending_summary`+`account_reconciliation`) is off — the tab stays in
  the strip and reachable, only its body changes. No entered-row count:
  `spending_tracker_ytd` owns no `dashboard_step`/`csv_sections` rows of its
  own (its inputs are imported transactions, not typed plan rows).
- `tests/test_strategy_workspace_module_gating.py` updated for the rename
  and the new inline-switch behavior (2 tests changed/added).
- `tests/frontend/feature_gated_note_off_states.test.mjs` (new, 12 tests):
  `featureGatedNote()` itself (module-toggle and plan-flag, with and without
  the row loaded, the entered-count line), the no-hidden-data invariant at
  each of the four fixed call sites (with a seeded row proving the data
  survives), a Disabled-in-place regression check (`rowBuildUsageState()`'s
  Hybrid LTC branch, confirming this workstream's `includeInactive` changes
  didn't disturb it), and a Hidden regression check (a data-free
  module-toggle-gated step is still absent, matching today's
  `stepGatedByOptionalModule()` behavior unchanged).

## What was deliberately NOT done

- **The Hybrid LTC soft-dependency plumbing** — see the triage table above.
  Deferred, with the same reasoning W9 already gave it.
- **`optionalModuleState()`/`rowBuildUsageState()` themselves** — the spec
  calls this mechanism "already written and already good," and reading it
  confirmed that: the reason/activation/effect triple is correct and
  complete for every row it already covers. Nothing about Disabled-in-place
  needed building; the bug was entirely upstream of it (rows never reaching
  it because a page-level `return` cut them off first, or `rowsForStep()`'s
  default filter dropped them before a caller could even try).
- **A generic "has this module's data survived" check for every
  `dashboard_step`-owned nav step** (the Hidden↔Collapsed choice at the
  top-level-nav granularity spec §5.2 also describes). Investigated one
  candidate (`entity_charitable`'s own `dashboard_step` gate, which — before
  this fix — hid the whole step from nav when `charitable_giving` was off,
  even with DAF/QCD data present) and found the actual fix did not need to
  touch `visibleSteps()`/`stepGatedByOptionalModule()` at all: Plan
  Features' own `PLAN_FLAG_DESTINATION_STEP` link (`data-step-id=
  "entity_charitable"`) already reaches the page directly regardless of nav
  hiding, so the invariant violation lived entirely in what the page showed
  once you got there — fixed by the `renderEntityCharitable()` change above.
  No other `dashboard_step`-owning module was found with a plan-flag or
  independently-gated feature living on its page the way DAF/QCD do on
  Charitable Giving, so a broader Hidden→Collapsed generalization at the nav
  level was not built for lack of a second case to generalize from — adding
  one now would be exactly the aspirational-mechanism risk `test_every_
  soft_declaration_is_backed_by_a_swept_call_site` exists to catch on the
  Python side, applied here to the frontend.
- **A defensive null-check on `rowModuleGate(...).key`**
  (`dashboard_decomp_assets_other.js`'s 529/Equity Compensation branches).
  Pre-existing code already accessed `.key` unconditionally on the result;
  writing this workstream's own test surfaced that it throws if
  `moduleGates.section_gates` doesn't carry that section (only reachable in
  practice if the server payload were ever stale/incomplete — every
  `csv_sections`-declared module's section is always present in production,
  per `config_service.py`'s `_module_gates()`). Left as found: this
  workstream's fix doesn't touch that access pattern's safety, and hardening
  it is a separate, unrelated concern from off-state rendering.

## Verification

- `tools/regen_golden_master.py measure` — exact match, `+0.00` on both
  pins. Expected for a UI-rendering-shaped workstream, verified rather than
  assumed (no Python file outside `tests/` changed; `deterministic_engine.py`
  and every `src/reporting/*` file are untouched).
- `pytest -m "not slow and not nightly" -n auto --dist loadfile` — full
  suite green. This container had neither the Python runtime deps
  (`numpy`/`scipy`/`lxml`/`openpyxl`/`matplotlib`/`pillow`/
  `pytest-xdist`/`pytest-timeout`) nor `node_modules` installed; a fresh
  install of both was required before the suite would even collect —
  without `node_modules`, 8 tests that shell out to `tools/js_codemod/*.mjs`
  failed on `ERR_MODULE_NOT_FOUND` for `@babel/parser`, matching the same
  caveat W8a/W8b/W9's own verification sections recorded for their
  containers. All 8 pass once `npm install` runs; re-ran the full suite
  after both installs for the number that actually counts.
- `npm test` — 641/643 after `npm install` (up from 597/598 before it — the
  install itself fixed several tests that were failing only because
  `node_modules` didn't exist, not because of this diff). The remaining 2
  are both inside `js_codemod_parser_offsets.test.mjs`, the pre-existing
  jscodeshift-offset environment difference W6/W8b/W9's notes already
  recorded, reproduced identically with this diff present.
- `tests/frontend/feature_gated_note_off_states.test.mjs` — 12/12 (new).
- `tests/test_strategy_workspace_module_gating.py` — 6/6 (2 changed/added).
- `tests/test_frontend_size_ratchet.py` — 4/4 after raising
  `TOTAL_JS_MAX_LINES` 35,121 → 35,289 (`dashboard.js` itself untouched,
  still 7,201 — no change to `DASHBOARD_JS_MAX_LINES`).

## Consequences for later workstreams

- **W13** (Left-nav realignment) is unblocked — its own scope line already
  requires W12.
- Whichever workstream next extends `degrades_without` inherits the Hybrid
  LTC soft-dependency item, already scoped twice now (W9's triage, this
  workstream's confirmation) rather than left to be rediscovered a third
  time.

## Addendum (2026-09-23): the deferred null-check, picked up

The "What was deliberately NOT done" item above (`rowModuleGate(...).key`
accessed unconditionally in `familyBusinessGroupsHtml()`,
`dashboard_decomp_assets_other.js`) was picked up as a small, isolated
hardening fix, out of scope for any numbered workstream. Both call sites
(529 Plans / Equity Compensation) now hold the `rowModuleGate()` result in a
local and only read `.key` when it is non-null, falling back to `true`
("not gated off") otherwise -- the same missing-gate convention
`dashboard.js`'s `rowGateStatus()` already uses at its own `rowModuleGate()`
call (`const gate = rowModuleGate(sec); if (gate) { ... }`), matched rather
than invented. No calculation change; the normal case (server payload
always present) is unaffected since `gate` is never null in production.
Covered by a new test
(`tests/frontend/feature_gated_note_off_states.test.mjs`, "a missing
section_gates entry degrades gracefully instead of throwing") that seeds
`section_gates` with only one of the two sections and confirms
`renderAssetsSpecial()` no longer throws and still renders the other
section's row. `TOTAL_JS_MAX_LINES` raised 35,621 -> 35,631 for the guard's
few extra lines.
