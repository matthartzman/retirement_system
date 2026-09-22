# W8b — Newly-optional, medium risk: execution notes

> Execution record for **W8b** of
> `docs/superpowers/plans/2026-09-19-optimizers-modules-housing-master-plan.md`
> §4 ("W8a / W8b — Newly-optional modules"), implementing #330 P6b.
> Requires W2, W6, W7 and W8a — all landed on this branch.

## Scope, as the plan states it

> W8b (medium risk): HSA Drawdown, Hybrid LTC, DAF+QCD, Housing "Where to
> live", and Spending Tracker / YTD — which **bundles `spending_summary` and
> `account_reconciliation` under one switch**, since all three are
> YTD-dependent and none can compute without the others' data.

Five sub-steps, landed and pushed separately, plus an isolated golden-master
step. Two of the five turned out to need **no conversion at all**, for reasons
recorded below rather than assumed from the plan's summary line — which is the
single most important finding in this workstream.

---

## 1. HSA Drawdown — the sheet toggle, and one dangling cross-reference

`hsa_drawdown` gained `optional=True`, a `module_key` on its `SHEET_REGISTRY`
entry, and a `TRUE`-defaulted toggle row. Per W8a's finding, `optional=True`
alone does not stop a sheet from being built — `OPTIONAL_MODULE_SHEETS` is
derived from `SHEET_REGISTRY.module_key`, not from `CATALOG.optional` — so both
halves landed together. Unlike two of W8a's four, the build call site
(`workbook_builder.py`'s `if '11C. HSA Drawdown' in sheets:`) was already
membership-guarded.

### Judgment call — the toggle stops at the sheet

#330 §3.2's off-column for this module reads:

> Sheet not built; `hsa_withdrawal_mode` stops being honored

**Only the first half is implemented.** `hsa_withdrawal_mode` is a *planning
lever* the household sets on Planning Levers, read by
`planning_engines.withdraw_hsa_window` (the live `optimize` branch) and by
`workbook_builder._ensure_hsa_schedule_file` (which writes
`client_hsa_schedule.csv` when the mode asks for one and none exists). Letting
a feature switch suppress it would:

* put a second, invisible gate on a *calculation* lever — structurally the same
  shape as the DAF double gate #330 Q2 exists to end; and
* leave `mode == 'optimize'` matching no engine branch at all, rather than
  falling back to a named mode, because the three named modes are matched by
  equality and `optimize` is the fourth.

So `engine_participation` stays `False` and stays true: turning this module off
removes the analysis sheet, not the drawdown the plan models. The module is
"the HSA drawdown *analysis*", and the user-visible promise is the one the
switch page already makes. Recorded here rather than decided silently.

### One real bug found by "check that nothing assumes it's always on"

`build_sheet11` (Roth Conversion) renders one sentence pointing the reader at
`'11C. HSA Drawdown'`, gated on `hsa_withdrawal_mode == 'optimize'` alone.
Before W8b that gate was sufficient — the sheet was unconditional. With the
toggle, the mode can say `optimize` on a workbook that does not contain that
sheet, and Sheet 11 would name a tab that is not there.

Fixed by ANDing `module_enabled(c, 'hsa_drawdown')` onto the existing mode
gate, declared as `degrades_without` on `roth_conversion_plan` (soft, not hard:
Sheet 11's own analysis is byte-identical either way — only the pointer line
differs), and recorded as a `SOFT` entry in W5's call-site sweep fixture.

**No fixture pins this.** Neither `tests/fixtures/sample_plan_frozen/` nor
`input/demo/` sets `hsa_withdrawal_mode = optimize` (both ship
`smooth_window`), so no golden master and no pinned build combination can reach
the defect. `tests/test_hsa_drawdown_toggle_regression.py` constructs the
divergence directly instead of waiting for a fixture that happens to hit it —
the same shape, and for the same reason, as W7's engine-gate regression.
Verified against the unfixed gate by reverting `sheets_strategy.py` alone: 1 of
its 6 tests fails without the fix, 6/6 pass with it.

---

## 2 & 3. Hybrid LTC and DAF+QCD — nothing to convert, and why

**These two sub-steps produced no conversion, on purpose.** The plan's summary
line lists them as "newly optional"; W6 had already given all three a switch,
and `validate()` now actively rejects the only thing W8b could add on top.
W6's own handoff note said so in advance:

> **W8b** makes Hybrid LTC and DAF+QCD optional *modules*. Note the tension:
> `validate()` now asserts a module cannot be `optional=True` **and**
> `gate_kind="plan_flag"`, because that combination is precisely the DAF
> double-gate Q2 exists to end. W8b must therefore convert, not layer.

Confirmed directly rather than taken on trust (`git log --grep="Hybrid LTC"`,
then reading `0772663` and `30ae09f`): `hybrid_ltc_policy`, `daf_giving` and
`qcd_giving` all carry `gate_kind=GATE_PLAN_FLAG` with a complete `gate_ref`
and `gate_enable_label`, own no workbook sheet, and are in neither
`core_keys()` nor `optional_keys()`. `charitable_giving` no longer declares
`csv_sections=("DAF",)`, so DAF is gated by its plan flag alone, exactly as QCD
always was.

### Judgment call — "convert" would delete a switch, not move one

The literal reading of "convert, not layer" is: change `gate_kind` to
`GATE_MODULE_TOGGLE`, add three toggle rows, drop `gate_ref`. That was
rejected. The plan flags are not metadata about where a switch lives — they
**are** the switch, and they are read as plan *data* by the projection:

* `spending_and_rmd.py` reads `c['daf_enabled']` (contribution year and grant
  schedule) and `c['qcd_enabled']` (the RMD-satisfying distribution);
* `spending_and_rmd.py` reads `c['ltc_enabled']` for the Hybrid LTC premium,
  and `sheets_stress.py` reads it for the configured-policy column of the LTC
  stress table.

Each flag also sits inside a plan-data section that carries the feature's
*parameters*, not just its on/off state (`Hybrid LTC/Settings` holds face
value, premium, start year, insured). Converting would either orphan those
rows or leave the engine reading the flag while the switch page read a toggle —
which is the double gate again, one level down. So the switch these features
have is the switch they keep.

### What W8b landed instead: the hole `validate()` cannot see

`validate()` rejects `optional=True` on a plan flag, and W6 pinned that
(`test_a_feature_may_not_carry_both_kinds_of_switch`). But the double gate can
also arrive **from the data side**, and that path was unguarded: a
`client_optional_functions.csv` row whose label names a plan-flag module. The
catalog would still say `optional=False`, so every existing assertion passes —
and the row is worse than inert. Plan Features renders one switch per toggle
row (`rowsForStep("optional_functions")` → `taxonomy.modules[r.label]`), so
the page would show a live ON/OFF control for a module whose real switch is
somewhere else, driving nothing at all: a plan flag owns no sheet, so it
appears in no `OPTIONAL_MODULE_SHEETS` entry for the build gate to read.

Two guards added to `tests/test_module_catalog.py` (which is where the
CSV-reading guard already lives, for the reason W1 documented — `validate()`
must not depend on a file on disk):

1. **`test_every_optional_module_has_a_toggle_row`** gains a third check: no
   toggle row may name a plan-flag module. Verified live by appending a
   `daf_giving` row and watching it fail with that message.
2. **`test_every_module_has_exactly_one_kind_of_switch_or_none`** asserts the
   three partitions are not only disjoint (W6 pinned that) but **exhaustive**:
   `core_keys() | optional_keys() | plan_flag_keys()` is the whole catalog —
   today 11 + 32 + 4 = 47 — so "which switch does this feature have?" has an
   answer for every module, not just the ones someone remembered to classify.
   It also pins the three W8b names on the flag side with the reason attached,
   so a future workstream that moves one has to read why first.

### Deliberately left to W9, per W6's own handoff

* **Plan Features link rows for plan flags.** Making the three findable on the
  switch page means rendering a row that links to the flag's own plan row
  (`gate_ref` + `gate_enable_label` already carry everything needed). W6
  assigned this to W9 and W8b does not pre-empt it.
* **The soft dependency #330 §3.2 asks for on Hybrid LTC** ("`long_term_care_stress`
  reads the policy. Needs a declared soft dependency"). Blocked by two
  invariants, and blocked for a good reason. `validate()` requires a
  `degrades_without` target to be `optional`, and
  `test_every_soft_declaration_is_backed_by_a_swept_call_site` requires
  declarations and swept call sites to match **exactly** — but W5's sweep
  recognizes two spellings of a *toggle* read (`module_enabled(`, `c['opt']`),
  and a plan flag is read as data (`c['ltc_enabled']`). Satisfying both would
  need a new catalog field mapping `gate_ref` to its parsed config key, plus a
  parallel sweep — to produce a warning string whose only consumer is the Plan
  Features link row that does not exist yet. That is the aspirational
  declaration those two tests exist to prevent, so it waits for its consumer.
  Recorded here so W9 inherits it explicitly rather than rediscovering it.

---

## 4. Housing — confirming the off state, and a name that points at two things

W1 already added this module's missing toggle row, defaulted `TRUE`
(`2026-09-21-w1-catalog-foundation-notes.md`: "a `FALSE` row would have turned
the module off and moved golden masters, and W1 is behavior-neutral by
contract"). `housing_trajectory_comparison` was therefore already
`optional=True`, already had `module_key='38. Housing Comparison'`'s registry
wiring, and already had a row. **No catalog change was needed here, and none
was made.** What W8b owed was the other half: proving the `off` state works end
to end rather than that a row exists.

### The gap that was actually there

`tests/test_housing_trajectory_comparison_sheet_functional.py::test_full_workbook_build_succeeds_with_the_module_on_and_off`
built the workbook with the module force-enabled and force-disabled — and
asserted only that the build returned 0 and produced a file. That is a claim
about *surviving*, not about *gating*: a build that force-disables a module it
never actually gates passes both assertions identically. Strengthened so the
off case asserts the Housing Comparison tab is absent and the on case asserts
it is present.

The assertion matches on the stable display suffix (`endswith("Housing
Comparison")`) rather than on `2G.`, because that letter shifts whenever any
other Optimizers module is toggled — #1.1's shifting-letters defect, which is
what W2's slugs exist to stop tests from re-introducing. This workstream hit it
immediately: with `hsa_drawdown` off, Housing Comparison moves from `2G.` to
`2F.`.

Confirmed by a pinned real build against a workspace seeded from the frozen
sample plan: module off → 39 sheets, no Housing Comparison tab, letters reflow
cleanly, build clean. The expensive part is gated too, not just the write — the
whole three-axis coordinate-descent sweep lives inside
`build_sheet_housing_comparison`, whose only call site is
`workbook_builder.py`'s `if '38. Housing Comparison' in sheets:`.

### Judgment call — the plan's "Housing 'Where to live'" names an uncatalogued feature

The master plan's W8b scope line says `Housing "Where to live"`, and the task
instruction resolves that to `housing_trajectory_comparison`. #330's own spec
does **not** treat those as the same thing:

| Spec §4.2 name | What it is | Catalogued? |
| --- | --- | --- |
| Housing Comparison ("When to move") | `housing_trajectory_comparison`, sheet 38, the sale-year × step-type sweep | yes |
| Housing Location Search ("Where to live") | `src/housing/`, the ZIP/city screen behind `/api/housing/optimize` and `/api/housing/zip-screen` | **no** |

Verified directly: `src/housing/` has no `OutputModule` anywhere in `CATALOG`
(the only housing entry is `housing_trajectory_comparison`), and #330 §3.2's
off-semantics for "Where to live" — "The UI panel is hidden; `src/housing/` is
not invoked" — describes the location search, which has no workbook sheet at
all.

**The call:** W8b did what the task instruction names — verified
`housing_trajectory_comparison`'s off state end to end — and did **not**
catalogue the location search. Making that one optional is not a toggle row; it
is a W1-shaped catalog addition (a new `OutputModule` with no sheet) plus
UI-panel gating, and panel/nav gating is W9's and W12's subject, not W8b's.
Flagged here rather than silently doing either half, so whoever picks it up
starts from "this was never catalogued" instead of from "W8b presumably handled
it".
