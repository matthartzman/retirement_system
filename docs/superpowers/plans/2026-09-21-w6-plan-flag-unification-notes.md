# W6 — Plan-flag unification: what was built, and the judgment calls

> Execution record for **W6** of
> `docs/superpowers/plans/2026-09-19-optimizers-modules-housing-master-plan.md` §4,
> implementing #330 P5 + Q2 (`docs/superpowers/specs/2026-09-19-modular-feature-nav-design.md`
> §5.3, "Module toggles vs plan-data feature flags").

## Status

**Commit 1 — HELOC alone, end to end — is landed and green.** The plan's own
pacing instruction is a checkpoint, not advice:

> Do HELOC alone, end to end, first. If HELOC alone is not clean, stop: the
> mechanism is wrong.

**The mechanism is clean.** HELOC's gate now resolves from a catalog
declaration through a generic frontend lookup, with no `if` naming it
anywhere, and nothing user-visible changed. Hybrid LTC, DAF and QCD are
repetitions of a proven pattern and are the remaining work (see
"What is still open" below).

## What landed in commit 1

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

## Not in scope, deliberately left alone

- **`rowsForStep()`'s `step === "heloc_strategy" && !helocModuleEnabled()`**
  (`dashboard_decomp_row_model.js`) is a *different* hand-written HELOC gate —
  an empty-page note, not step visibility. The scope line names
  `stepGatedByOptionalModule()` and `strategySectionGatedNote()` only. It is a
  natural W9 follow-up: it reads `flag_gates` with the same two lines.
- **Listing plan flags on the Plan Features page.** §5.3 says both mechanisms
  should appear there, with a link (not a toggle) for a plan flag. The Plan
  Features page is driven by the CSV's toggle *rows*, not by the taxonomy
  payload, so the new catalog entries add nothing to it and nothing there
  changed. Adding the link rows is a UI change, not a refactor, and belongs
  with W9's UI section registry.

## Verification

- `tests/test_module_catalog.py`, `tests/test_strategy_workspace_module_gating.py`,
  `tests/test_ui_dependency_ordering_functional.py`,
  `tests/test_optional_module_gating.py`,
  `tests/test_module_catalog_prereq_gating.py`,
  `tests/test_module_toggle_call_site_enforcement.py`,
  `tests/test_sheet_table_consistency.py`,
  `tests/test_strategy_workspace_screens_functional.py`,
  `tests/test_planning_levers_layout_functional.py` — all pass.
- `npm test`: 477 pass, 2 fail — both in
  `tests/frontend/js_codemod_parser_offsets.test.mjs`, **pre-existing on this
  branch** (confirmed by stashing the W6 diff and re-running), unrelated to
  plan-flag gating.
- `tests/test_frontend_size_ratchet.py` passes: `frontend/js` totals exactly
  33,604 lines, the existing ceiling, and `dashboard.js` did not grow. The
  new declarative block is net line-neutral against the two branches it
  replaced — comments were compressed to keep it so rather than raising a
  ratchet for a refactor that removes hand-maintained code.

## What is still open

The three remaining plan-flag entries, each a repetition of HELOC's pattern:

| Feature | `gate_ref` | Notes |
|---|---|---|
| Hybrid LTC | `("Hybrid LTC", "Settings", "enabled")` | read today by `ltcLifePolicyModuleEnabled()`; owns no `dashboard_step` — confirm before assuming one |
| DAF | `("DAF", "Settings", "enabled")` | **also** requires dropping `charitable_giving`'s `csv_sections=("DAF",)` (#330 Q2) |
| QCD | `("Cashflow", "Charitable Giving", "qcd_enabled")` | already correct in the product; catalogued for symmetry with DAF |

Two things to work out when they land:

1. `flag_gate_map()` is keyed by `dashboard_step`. DAF and QCD own no step —
   their rows live inside pages that stay visible — so either the map grows a
   second keying or they are declared without a step and the map skips them.
   The latter is probably right for W6 and leaves the Plan Features listing
   (above) to W9.
2. Dropping `csv_sections=("DAF",)` is the one **deliberately user-visible**
   change in W6: DAF rows stop being hidden when the `charitable_giving`
   module is off, and are governed by the DAF plan flag alone, exactly as QCD
   rows already are. The spec calls this out (§5.3, Q2) and it deletes no
   user-set plan row. It needs its own before/after check, unlike commit 1.

## Consequences for later workstreams

- **W9** inherits three things named above: the `rowsForStep()` gate, the Plan
  Features link rows for plan flags, and — if it wants `special_strategies`-style
  bundle steps back — a real "any of these gates" declaration, which W6
  deliberately did not invent.
- **W8b** makes Hybrid LTC and DAF+QCD optional *modules*. Note the tension:
  `validate()` now asserts a module cannot be `optional=True` **and**
  `gate_kind="plan_flag"`, because that combination is precisely the DAF
  double-gate Q2 exists to end. W8b must therefore convert, not layer.
