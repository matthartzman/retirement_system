# W6 — Plan-flag unification: what was built, and the judgment calls

> Execution record for **W6** of
> `docs/superpowers/plans/2026-09-19-optimizers-modules-housing-master-plan.md` §4,
> implementing #330 P5 + Q2 (`docs/superpowers/specs/2026-09-19-modular-feature-nav-design.md`
> §5.3, "Module toggles vs plan-data feature flags").

## Status

**All four features are landed and green: HELOC (commit 1), then Hybrid LTC,
DAF and QCD (commit 2), then a trim (commit 3) that brought Hybrid LTC's
shape back in line with the minimal pattern HELOC actually proved.** The
plan's own pacing instruction is a checkpoint, not advice:

> Do HELOC alone, end to end, first. If HELOC alone is not clean, stop: the
> mechanism is wrong.

**The mechanism is clean, and it generalized without needing to grow.**
Every plan flag but HELOC turned out to need *nothing* beyond the four
`OutputModule` fields commit 1 already added — no second gate map, no new
server payload key. See Judgment call 6 below for the one place W6 first
overbuilt this, then cut it back.

## What landed in commit 1 (HELOC)

1. **`gate_kind` / `gate_ref` / `gate_enable_label` on `OutputModule`**, plus
   the `GATE_MODULE_TOGGLE` / `GATE_PLAN_FLAG` constants and four new
   `validate()` guards.
2. **A catalog entry for HELOC** — the first `gate_kind="plan_flag"` module.
3. **`flag_gate_map()` beside `step_gate_map()`**, served on the config
   payload as `module_gates.flag_gates`.
4. **Both hand-written branches removed from `stepGatedByOptionalModule()`**
   (`dashboard_decomp_row_model.js`), and the `gateStepId === "heloc_strategy"`
   branch removed from `strategySectionGatedNote()`
   (`dashboard_decomp_strategy_workspace.js`).

## Judgment call 1 — `step_gate_map()` had to *lose* rows, not just gain a sibling

The obvious reading of "`flag_gate_map()` beside `step_gate_map()`" is additive.
It is not: `step_gate_map()` is `{step: toggle_key}` and the frontend feeds that
key to `optionalFunctionEnabled()`, which looks it up in the
`Optional Functions` CSV section. A plan-flag module has no row there, so
`optionalFunctionEnabled("heloc")` returns `false` unconditionally and the step
would be permanently hidden. `step_gate_map()` is therefore now filtered to
`gate_kind == GATE_MODULE_TOGGLE`, and the two maps partition the steps rather
than overlapping. `validate()` asserts `dashboard_step` uniqueness across
*both*, because one frontend lookup chain consults them in order.

## Judgment call 2 — `core_keys()` was silently wrong the moment a plan flag existed

`core_keys()` was `not m.optional`, and `optional` means "carries a
client_optional_functions.csv toggle". A plan-flag module is not optional by
that definition but is emphatically not always-on either — HELOC defaults to
`NO`. Left alone, the first plan-flag entry would have quietly promoted itself
into the always-on core set. `core_keys()` is now "no switch of any kind", and
`plan_flag_keys()` names the third category. This is exactly the axis-collapse
the catalog's own `domain`/`kind` comment warns about, one level down.

## Judgment call 3 — the `special_strategies` branch was deleted, not re-expressed

The spec says both hand-written branches go "in favour of reading
`moduleGates.flag_gates`". That works directly for `heloc_strategy`. It does
**not** work for `special_strategies`, which was a *bundle* gate — visible iff
HELOC **or** Charitable Giving was on — and `gate_ref` has no way to say "any
of these two", one of which is a toggle and the other a flag. Rather than
invent a bundle declaration that W6's scope does not call for, the branch was
deleted outright, because it is dead:

- its `STEPS` entry is `group: null, hidden: true` (a shell #323 kept only so
  row routing still keys off the id);
- `visibleSteps()` drops any `group === null` step regardless of gating;
- `navigation.js` `SECTION_REDIRECTS` sends `special_strategies` to
  `strategy_optimize`, so it can never become `activeStep` either — the one
  case where `visibleSteps()` ignores the group check;
- no `strategySection()` descriptor passes it as a `gate`.

`tests/test_ui_dependency_ordering_functional.py` used to pin the branch's
source text. It now pins the three facts the deletion rests on instead, so if
any of them is undone the test fails and the gate has to come back. That is a
stronger assertion than the one it replaced, not a weaker one.

## Judgment call 4 — `gate_enable_label` is a third field, and it earns its place

`gate_ref` alone cannot produce the note's click-path. The flag's CSV label is
`heloc_enabled`; the path the user actually sees is
"HELOC → Setup → **Enable HELOC Strategy**". That display name is not derivable
from the CSV label and has no override table anywhere — it existed only as
hand-typed copy inside `strategySectionGatedNote()`. Resolving the link "from
`gate_ref` instead of an `if`" while leaving the copy hand-typed in JS would
have moved the branch and kept the twin. So the copy moved into the catalog
beside the reference it describes, and `validate()` requires it on every plan
flag. This is one field beyond the scope line's literal `gate_kind`/`gate_ref`;
it is the smallest addition that actually removes the twin.

## Judgment call 5 — one word of copy changed, on an unreachable path

Old (plan-flag branch): `HELOC strategy is off. Enable it on …`
New (generic):          `HELOC is off. Enable it on …`

"strategy" was dropped because the sentence is now shared by every plan flag
and "Hybrid LTC strategy" / "DAF strategy" would not all read naturally. The
delta is unobservable today: no `strategySection()` descriptor passes
`gate: "heloc_strategy"` (the Optimize screen's HELOC section is deliberately
`gate: null`, so the toggle renders in place), so the plan-flag note has no
live caller. Recorded here rather than silently, because W9 may give it one.

## What landed in commits 2 and 3 (Hybrid LTC, DAF, QCD)

Three more `gate_kind="plan_flag"` catalog entries: `hybrid_ltc_policy`,
`daf_giving`, `qcd_giving`. DAF and QCD have no `dashboard_step` — their rows
live inside pages (Charitable Giving / Cashflow) that stay visible regardless
— so `flag_gate_map()` simply never lists them; no second keying was needed.

**The one deliberately user-visible change (#330 Q2): `charitable_giving`
drops `csv_sections=("DAF",)`.** DAF was double-gated — the module's toggle
*and* its own plan flag — while QCD, the same feature from the other side,
was already gated by its plan flag alone (QCD's rows live in the shared
`Cashflow` section, which a section gate would take out wholesale). DAF was
the anomaly; the plan flag now owns it exclusively, matching QCD.
`entityCharitableGatedRows()` (`dashboard_decomp_estate_insurance.js`)
already implements the right per-row gating for both — show the enable row,
hide the rest when off — so this needed no frontend change.

**Verified, not just asserted:** grepped the engine/tax layer for where the
DAF plan flag actually drives the projection
(`spending_and_rmd.py`'s `c.get('daf_enabled', False)`, read straight from
`client_assets.csv`'s `DAF/Settings/enabled` independent of the
`charitable_giving` toggle) — confirming the double-gate was a *dashboard*
artifact, not a calculation one, so removing it is within the "no calculation
changes" global constraint. Also found and fixed a small pre-existing
truthfulness bug as a side effect: `rowModuleGate("DAF")` fed
`rowBuildUsageState()`'s "inactive, module off" badge on DAF rows whenever
`charitable_giving` was off, even though `daf_enabled` meant the engine was
using them anyway. That badge is gone; DAF rows behave like QCD's always did.
`tests/test_daf_agi_limitation_and_carryforward.py`,
`test_daf_grant_deduction_and_inkind_funding.py`,
`test_daf_optimizer_recommendation.py`, `test_current_vs_proposed_regression.py`
and the frontend `strategy_screen_rows_aggregate.test.mjs` all still pass.

## Judgment call 6 — Hybrid LTC's row-group gate was over-built, then cut back

First pass gave `hybrid_ltc_policy` a `csv_sections=("Hybrid LTC",)`
declaration and a new `flag_section_gate_map()` (the section-keyed sibling of
`flag_gate_map()`), served as a new `module_gates.flag_section_gates` payload
key, intending it to replace `optionalModuleState()`'s hand-written
`sec === "Hybrid LTC"` branch in `dashboard.js`.

That branch is real, and it is the Hybrid LTC analogue of the
`rowsForStep()` branch "Not in scope, deliberately left alone" (below) already
leaves untouched for HELOC — a *third* hand-written gate, not one of the two
the scope line names for removal (`stepGatedByOptionalModule()`,
`strategySectionGatedNote()`).
Building new catalog fields and a new server payload key to replace it was
scope creep relative to what commit 1 actually proved: HELOC's pattern needed
exactly four `OutputModule` fields and zero new maps beyond
`flag_gate_map()`. Cut back to match: `hybrid_ltc_policy` now declares
neither `dashboard_step` nor `csv_sections`, exactly like `daf_giving` and
`qcd_giving`, and `flag_section_gate_map()` is gone. `section_gate_map()`
keeps the `GATE_MODULE_TOGGLE` filter it gained in the first pass — cheap
insurance against a future plan flag declaring `csv_sections` and silently
reading as permanently off, the same bug `step_gate_map()` had — but it is
now a no-op given today's catalog, not load-bearing.

## Not in scope, deliberately left alone

- **`rowsForStep()`'s `step === "heloc_strategy" && !helocModuleEnabled()`**
  (`dashboard_decomp_row_model.js`) is a hand-written HELOC gate — an
  empty-page note, not step visibility.
- **`optionalModuleState()`'s `sec === "Hybrid LTC" && !ltcLifePolicyModuleEnabled()`**
  (`dashboard.js`) is the same shape one level down: a hand-written row-group
  gate, not step or section visibility.
- Both are natural W9 follow-ups — each reads `flag_gates`
  (`dashboard_step`-keyed, HELOC) or a small local check
  (`ltcLifePolicyModuleEnabled()`, Hybrid LTC) with the same two or three
  lines a generic version would need — but the scope line names
  `stepGatedByOptionalModule()` and `strategySectionGatedNote()` only, and
  W6's own checkpoint is "prove the minimal pattern," not "eliminate every
  hand-written gate in the codebase."
- **Listing plan flags on the Plan Features page.** §5.3 says both mechanisms
  should appear there, with a link (not a toggle) for a plan flag. The Plan
  Features page is driven by the CSV's toggle *rows*, not by the taxonomy
  payload, so the new catalog entries add nothing to it and nothing there
  changed. Adding the link rows is a UI change, not a refactor, and belongs
  with W9's UI section registry.

## Verification

- `tests/test_module_catalog.py` (29 tests, including six added for W6:
  the four plan flags' shape, the two gate-map pairs partitioning rather
  than overlapping, DAF/QCD parity, and the toggle+plan-flag double-gate
  guard), `tests/test_strategy_workspace_module_gating.py`,
  `tests/test_ui_dependency_ordering_functional.py`,
  `tests/test_optional_module_gating.py`,
  `tests/test_module_catalog_prereq_gating.py`,
  `tests/test_module_toggle_call_site_enforcement.py`,
  `tests/test_sheet_table_consistency.py`,
  `tests/test_strategy_workspace_screens_functional.py`,
  `tests/test_planning_levers_layout_functional.py`,
  `tests/test_daf_agi_limitation_and_carryforward.py`,
  `tests/test_daf_grant_deduction_and_inkind_funding.py`,
  `tests/test_daf_optimizer_recommendation.py`,
  `tests/test_current_vs_proposed_regression.py` — all pass.
- `npm test`, including `tests/frontend/strategy_section_lazy_body.test.mjs`
  and `strategy_screen_rows_aggregate.test.mjs`: green except two failures in
  `tests/frontend/js_codemod_parser_offsets.test.mjs`, **pre-existing on this
  branch** (confirmed by stashing the W6 diff and re-running, and separately
  by CI's `frontend-tests` check passing green on PR #132's commit `45987a5`
  — those two are a local-environment difference, not something CI even
  sees), unrelated to plan-flag gating.
- `tests/test_frontend_size_ratchet.py` passes: `frontend/js` stayed at the
  existing 33,604-line ceiling through commit 1; commits 2–3 touch only
  `src/`, `tests/`, and this notes doc, so the ratchet is untouched.
- CI on PR #132's HELOC commit (`45987a5`): all five checks (`build`,
  `fast-gates`, `frontend-tests`, `test (windows-latest, 3.14)`,
  `e2e-tests`) passed.

## What is still open

Nothing in W6's own scope. All four features (HELOC, Hybrid LTC, DAF, QCD)
are catalogued with `gate_kind="plan_flag"`; both hand-written branches named
in the scope line are gone; `charitable_giving` no longer double-gates DAF.
The items in "Not in scope, deliberately left alone" above are the residue,
explicitly deferred rather than overlooked.

## Consequences for later workstreams

- **W9** inherits three things named above: the `rowsForStep()` gate, the Plan
  Features link rows for plan flags, and — if it wants `special_strategies`-style
  bundle steps back — a real "any of these gates" declaration, which W6
  deliberately did not invent.
- **W8b** makes Hybrid LTC and DAF+QCD optional *modules*. Note the tension:
  `validate()` now asserts a module cannot be `optional=True` **and**
  `gate_kind="plan_flag"`, because that combination is precisely the DAF
  double-gate Q2 exists to end. W8b must therefore convert, not layer.
