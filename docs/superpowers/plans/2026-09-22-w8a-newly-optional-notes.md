# W8a — Newly-optional, low risk: execution notes

> Execution record for **W8a** of
> `docs/superpowers/plans/2026-09-19-optimizers-modules-housing-master-plan.md` §4
> ("W8a / W8b — Newly-optional modules"), implementing #330 P6a.

## Scope

Four modules gain a `client_optional_functions.csv` toggle: `asset_location`,
`scorp_vs_llc`, `tax_capacity`, `current_vs_proposed`. The plan's own
rationale for calling this "low risk" is that nothing in the catalog declares
`requires_outputs` on any of the four — verified directly (`grep
requires_outputs src/module_catalog.py`, cross-checked against every
`OutputModule` entry) rather than assumed from the plan's summary line.

## What landed

1. **`optional=True`** added to all four `CATALOG` entries.
2. **`module_key` wired into their `SHEET_REGISTRY` entries** — this is the
   half the plan's one-line "registry edits" summary elides. `optional=True`
   alone only makes a module appear on the Plan Features switch nav; the
   thing that actually stops a sheet from being *built* is
   `OPTIONAL_MODULE_SHEETS`, which is derived solely from `SHEET_REGISTRY`'s
   `module_key` field, not from `CATALOG.optional`. All four sheets
   (`11B. Tax Capacity`, `24. Asset Location`, `S-Corp vs LLC`,
   `37. Current vs Proposed`) had no `module_key` before this workstream —
   they were always built regardless of any toggle.
3. **Two unconditional build calls in `workbook_builder.py` needed a guard.**
   `build_sheet24(sheets['24. Asset Location'], ...)` and
   `build_sheet_current_vs_proposed(sheets['37. Current vs Proposed'], ...)`
   were called with no `if 'X' in sheets:` membership check, unlike every
   other optional sheet in that function. Once `disabled_sheets` starts
   pruning these two out of `sheets` (via the newly-set `module_key`), the
   unconditional calls would `KeyError` the moment either toggle is turned
   off. Added the same `if '<sheet>' in sheets:` guard every other optional
   sheet already uses. `build_sheet_tax_capacity` needed no change — it was
   already correctly guarded (`if '11B. Tax Capacity' in sheets:`), the one
   of the four that happened to be written defensively already.
4. **`S-Corp vs LLC` needed a different fix, not just a registry edit.** Its
   `SHEET_REGISTRY` entry has `v5_code=None`, so it was never part of
   `V5_LAYOUT`'s main sheet-creation loop (and therefore never covered by the
   generic `OPTIONAL_MODULE_SHEETS`/`disabled_sheets` pruning at all, whether
   or not `module_key` is set): the sheet is built by
   `_extract_scorp_sheet(wb)`, which copies rows straight out of the already-
   built `9. Retirement Strategy` sheet, unconditionally, every build. Gated
   its one call site in `apply_final_workbook_structure` with
   `if module_enabled(c, 'scorp_vs_llc'):` instead. Recorded as a new
   `OWN_GATE` entry in `tests/test_module_toggle_call_site_enforcement.py`'s
   `DECLARED_SITES` fixture (that sweep asserts every literal
   `module_enabled(` call site in `src/` is classified, so a new literal
   call — as opposed to the existing generic dynamic-key loop over
   `OPTIONAL_MODULE_SHEETS` — needed its own entry).
5. **Toggle rows added to `input/demo/client_optional_functions.csv`**, all
   defaulting `TRUE` (preserves current always-on behavior for the demo
   plan; nothing about this workstream should change what the demo plan's
   workbook contains by default). `tests/test_module_catalog.py`'s
   `test_every_optional_module_has_a_toggle_row` (the fourth W1 guard) covers
   this — it fails loudly if any of the four is missing its row.

## Judgment call — the plan's "registry edits" undersold the actual change

`SHEET_REGISTRY`/`module_key` wiring and the `workbook_builder.py` guards are
not optional polish on top of `CATALOG.optional=True` — without them, turning
any of the four toggles off would either do nothing (module_key unset, sheet
always builds regardless of the switch) or crash with a `KeyError`
(module_key set but the build call left unconditional). Confirmed by tracing
`OPTIONAL_MODULE_SHEETS`'s derivation and every one of the four sheets'
build-call sites in `workbook_builder.py` before touching anything, not by
pattern-matching against the nearest existing optional module.

## Build verification

Pinned three representative toggle combinations against a real
`src.build_entry.run_build()` (in-process, no subprocess) run over a
throwaway workspace seeded from `input/demo/`, read back with `openpyxl`:

1. **All four ON** (the default demo-plan state) — `11B. Tax Capacity`,
   `24. Asset Location`, `S-Corp vs LLC`, `37. Current vs Proposed` all
   present in `wb.sheetnames`.
2. **All four OFF** — none of the four present; build completes with no
   `KeyError` and no other sheet references a missing one badly enough to
   break the build (the rename pass and cross-reference text already guard
   on `wb.sheetnames` membership generically, per every other optional
   module).
3. **Mixed** (`asset_location` and `current_vs_proposed` ON,
   `scorp_vs_llc` and `tax_capacity` OFF) — confirms the four gates are
   independent of each other and of `retirement_strategy` (Sheet 9, which
   `S-Corp vs LLC` extracts from) rather than accidentally coupled.

`tools/regen_golden_master.py measure` against the frozen sample plan: no
change expected or observed — the frozen plan's own
`client_optional_functions.csv` carries no explicit `FALSE`/`TRUE` row for
any of the four (none existed before this workstream either), so
`module_enabled()`'s default-on-when-absent contract keeps it building
exactly the sheets it always did.

## Judgment call — one pre-existing test pinned the old always-on shape

`tests/test_current_vs_proposed_regression.py::test_sheet37_registered_in_the_workbook_layout`
asserted `SHEET_REGISTRY["37. Current vs Proposed"].module_key is None`,
with a comment claiming Sheet 37 was "always-on... matching other flagship
report sheets." That was true before this workstream and is now the thing
being changed on purpose. Updated the assertion to
`module_key == "current_vs_proposed"` with a comment explaining why. Swept
the rest of the suite for the same shape (`grep "module_key is None"
tests/`) — no other test pinned this assumption for the other three modules.

## Build verification

Ran three representative toggle combinations through a real
`src.build_entry.run_build()` (fresh subprocess per combo, workspace seeded
from `tests/fixtures/sample_plan_frozen/` plus an appended toggle-override
row per module), read back with `openpyxl`:

1. **All four ON** — `1H. Current vs. Proposed`, `3B. S-Corp vs LLC`, and
   `5I. Tax Capacity` all present in the final `wb.sheetnames`. (Asset
   Location has no distinguishing final sheet either way — see below.)
2. **All four OFF** — all three of those final sheet names correctly
   absent; build completes cleanly, no `KeyError`, `3. Comparisons`'
   section divider correctly lists only `3A. State Residency` once
   `3B. S-Corp vs LLC` is gone.
3. **Mixed** (`asset_location`/`current_vs_proposed` ON,
   `scorp_vs_llc`/`tax_capacity` OFF) — `1H. Current vs. Proposed` present,
   `3B. S-Corp vs LLC` and `5I. Tax Capacity` correctly absent, confirming
   the four gates are independent of each other and of `retirement_strategy`
   (Sheet 9, which `S-Corp vs LLC` extracts its content from).

**Asset Location has no observable on/off signal in the final sheet list,
by design, in every combination above.** `24. Asset Location` is a
`_hidden` build-time sheet that `_merge_asset_location_into_allocation`
copies into the always-on `4. Asset Allocation` / `2C. Asset Allocation`
tab; that merge function already guarded
`if '24. Asset Location' not in wb.sheetnames: return` before this
workstream, so toggling `asset_location` off changes 2C's row count, not
its presence. All three combos above did complete without error either
way, which is what the toggle's correctness actually rests on (no crash
where the sheet used to be unconditionally present).

`tools/regen_golden_master.py measure` against the frozen sample plan (its
own `client_optional_functions.csv` carries no row for any of the four,
before or after this workstream): exact match, `+0.00` on both pins, as
predicted — `module_enabled()`'s default-on-when-absent contract keeps the
frozen plan building exactly the sheets it always did.

## Verification summary

- `tools/regen_golden_master.py measure` — exact match, `terminal_nw +0.00`,
  `lifetime_tax +0.00`.
- `tests/test_module_catalog.py`, `tests/test_optional_module_gating.py`,
  `tests/test_module_toggle_call_site_enforcement.py`,
  `tests/test_sheet_table_consistency.py`,
  `tests/test_module_catalog_prereq_gating.py` — all pass with the four new
  `optional=True` entries and the new `scorp_vs_llc` `DECLARED_SITES` row.
- `tests/test_current_vs_proposed_regression.py` (after the one fix above),
  `tests/test_engine_module_gate_agrees_with_sheets_regression.py` — pass;
  neither of the four modules participates in the engine, and this
  workstream never touches `deterministic_engine.py`.
- `tests/test_workbook_five_area_tabs_functional.py`,
  `tests/test_workbook_numbered_section_tabs_functional.py`,
  `tests/test_workbook_system_cleanup_and_widths_functional.py` — pass
  against the default (all four ON) toggle state.
- `tests/test_synthetic_golden_master.py` +
  `tests/test_deterministic_engine_full_row_snapshot_regression.py` — 9/9,
  no fixture JSON changed.
- Three pinned toggle-combination real builds (above) — all green, correct
  sheet presence/absence in every case that has one.
- `pytest -m "not slow"` — full suite green, with two caveats, both
  confirmed unrelated to this workstream:
  - Four `tools/js_codemod/*`-dependent tests
    (`test_dashboard_codemod_census_report_regression.py`,
    `test_dashboard_extract_module_tool.py` x3,
    `test_dashboard_js_module_bridge_regression.py` x3) fail in this
    container because `node_modules/` (specifically `@babel/parser`) was
    never installed here — confirmed by `ls node_modules` (absent) and by
    this workstream's diff touching zero JS/node files. Same class of
    local-environment gap the W6 notes already documented for
    `js_codemod_parser_offsets.test.mjs`.
  - `test_the_sweep_finds_exactly_the_declared_call_sites` failed on one
    run because that background baseline process had started (and already
    imported `DECLARED_SITES`) before this workstream's edit landed, while
    its own `sweep_src()` re-reads `src/` from disk fresh on every run —
    a timing artifact of running a long baseline check concurrently with
    edits, not a real gap. Confirmed spurious: a fresh, isolated re-run
    after both edits landed passes 13/13.
