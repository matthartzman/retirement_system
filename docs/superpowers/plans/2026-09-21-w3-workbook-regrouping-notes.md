# W3 — Workbook regrouping: what was built, and the judgment calls

> Execution record for **W3** of
> `docs/superpowers/plans/2026-09-19-optimizers-modules-housing-master-plan.md` §4.
> #329 P3 + F7. Follows W0/W1's addenda (Tax Capacity → System) and does not
> revisit that decision.

## Deviation from the trigger's stated premise — read this first

The task that kicked off this session stated "W0, W1 and W2 are done, committed,
and pushed on this branch" and pointed at
`docs/superpowers/plans/2026-09-21-w2-stable-slugs-notes.md` for W2's record.

**That premise is false.** `git log` on this branch shows only W0
(`c05163f`) and W1 (`fbe6149`, `22db141`, `a3f5d04`) landed; there is no W2
commit, no `slug` field on `SheetSpec`, and no W2 notes file anywhere in the
repo. This was verified directly (`git log --all --oneline`, `grep -r slug
src/module_catalog.py src/reporting/workbook_common.py`) before writing any
code, rather than trusted from the trigger text.

**W3 proceeded anyway**, for two reasons:

1. The master plan's own file-level scope for W3 (`workbook_common.py`,
   `workbook_builder.py`, `module_catalog.py`, `test_sheet_table_consistency.py`)
   does not actually touch anything slug-shaped. Cross-reference text still
   resolves through today's letter-based `FINAL_SHEET_RENAMES` mechanism,
   exactly as it did before W2 was even planned — W3 doesn't change that
   mechanism, only which letters a sheet gets.
2. W1's own notes already anticipated this ordering explicitly: "`tab=` ...
   remains documentation... **W3 removes the field when cross-references
   resolve through W2's slug**" — i.e. the `tab=` field's removal, not W3's
   substantive work, is what actually depends on the slug. Since the slug
   doesn't exist yet, `tab=` fields were *updated* (not removed) to their new
   letters, same as W1 did for eight stale ones. Removing `tab=` outright is
   left for whenever W2 actually lands.

**W2 is still owed.** It is not silently satisfied by anything in this
commit. A future session must still execute it as its own workstream before
the `tab=` field can be deleted per the plan's original intent.

## Open question resolved — System becomes group '5'

The master plan's W3 entry and W1's own `KIND_LETTER_PREFIX` comment both
say "COMPARISON moves to its own '3' and PROTECTION joins the renamed
'4. Risks'" without spelling out what happens to the group that already
held code `'4'` (System: Plan Data, Assumptions, QC, RMD Audit, Methodology,
Glossary, Planning Levers, Tax Capacity — `DIAGNOSTICS` and `REFERENCE`
kinds).

**Resolved: System becomes letter group `'5'`.** Checked against the full
spec (`docs/superpowers/specs/2026-09-19-optimizer-stress-test-rationalization-design.md`
§3.2): it names exactly four sections — `1. Reports`, `2. Optimizers`,
`3. Comparisons`, `4. Risks` — and the word "System" does not appear
anywhere in that document (confirmed by grep). System was never part of
#329's numbering scheme; it only happened to occupy the codebase's `'4'`
slot because that was the next unclaimed digit when the registry was built,
unrelated to #329's conceptual 1–4. Since `'4'` is now claimed by Risks,
System is renumbered to `'5'`, its internal sheet order and content
unchanged. `_SECTION_META` gained a `'5'` entry; no sheet moved into or out
of System on this account.

## What landed

**1. Full `section`/`letter_prefix` derivation from `kind`.** `SHEET_REGISTRY`
entries no longer hand-type a group digit. `_visible(name, v5_code,
section_rank, letter_rank, display, module_key)` derives both `section` and
`letter_prefix` from `KIND_LETTER_PREFIX[_SHEET_KIND[name]]`, where
`_SHEET_KIND` is a reverse map off `CATALOG` (`{module.sheet: module.kind}`).
`_hidden(name, v5_code, module_key)` is the parallel constructor for sheets
deliberately absent from the nav (`section`/`letter_prefix` stay `None`).
`validate()`'s classification-invariant assertion is unchanged in shape, but
is now structurally impossible to fail for any sheet built via `_visible` —
there is no hand-typed twin left for it to catch disagreement against. It
stays in place as a guardrail against a future direct `SheetSpec(...)`
construction that bypasses the constructors.

**2. `KIND_LETTER_PREFIX` regrouped**, per #329 §3.1/§3.2:

```
COMPARISON:   '2' -> '3'   (its own group: State Residency, S-Corp vs LLC)
PROTECTION:   '3' -> '4'   (joins STRESS_TEST under the renamed Risks)
STRESS_TEST:  '3' -> '4'   (renamed Risk & Stress Tests -> Risks)
DIAGNOSTICS:  '4' -> '5'   (System, renumbered -- see above)
REFERENCE:    '4' -> '5'   (System, renumbered -- see above)
```

`PROJECTION`/`WORKSHEET` (`'1'`, Reports) and `OPTIMIZATION` (`'2'`,
Optimizers) are unchanged.

**3. `_SECTION_META` / `SECTION_COLOR` updated** (`workbook_common.py`) to
five entries: Reports, Optimizers, Comparisons (new description), Risks
(renamed from "Risk & Stress Tests", new description), System (renumbered).
Comparisons got a new tab color (green, `548235`) since Risks now claims the
red that used to belong to the merged Risk & Stress Tests group.

**4. "This year's actions" divider.** Tax-Loss Harvesting and Gain
Harvesting keep `letter_prefix='2'` (they pass the search-score-rank test,
per #329 F3) but their `letter_rank` moved to `16`/`17` — after every other
Optimizers sheet, including Housing Comparison at `15` — so they sort last
and adjacent regardless of which optional modules are on. A labeled row
("This year's actions") is inserted in the `2. Optimizers` divider tab
(`build_workbook_section_divider`, `_SUBGROUP_DIVIDERS` in
`workbook_builder.py`) right before whichever of the two survives module
gating and appears first in that build. If both are off, no label renders.
This is the only mechanism available for a "subsection" — Excel's tab strip
is flat, so a real subsection doesn't exist; per spec §3.2, the divider row
is the whole of it.

**5. `3C` split** (#329 O10, the riskiest single piece — its own commit):

- `_merge_ltc_into_life_insurance()` removed outright from
  `workbook_builder.py`, along with the LTC→Life-Insurance-slot promotion
  hack in `apply_final_workbook_structure` (both existed only to make the
  merge survive one-sided module gating).
- `'17. LTC Stress Test'` changed from `_hidden(...)` (no section, deleted
  post-build) to `_visible(...)`: `letter_prefix='4'` (derived from its
  `STRESS_TEST` kind), `letter_rank=2` (between Survivor at `1` and the
  protection decisions at `3`+), `display='LTC Stress Test'`.
- `'19. Life Insurance'` (`life_insurance_need`, `PROTECTION`) keeps
  `letter_rank` effectively where it was (now `3`, one slot later to make
  room for LTC at `2`); its `display` changed from `'LTC + Life Insurance'`
  to `'Life Insurance Need'` — it is a protection decision alone now, not a
  merged tab.
- `31`/`32`/`33` (Existing Life Insurance / Disability / P&C) shifted
  `letter_rank` `3,4,5` → `4,5,6` to make room.
- `workbook_common.py`'s `_SHEET_NUM_TO_STABLE[17]` changed from
  `'19. Life Insurance'` (where "Sheet 17" text mentions used to resolve,
  back when 17's content lived inside 19) to `'17. LTC Stress Test'` (its
  own tab again) — this also fixes, not just relabels, a few pre-existing
  prose cross-references (`sheets_strategy.py`'s "LTC stress test on
  Sheet 17", `sheets_summary_builder.py`'s "See Sheet 17 for the modeled
  cost of self-funding care") that previously resolved to the wrong tab.
  `sheet_num_label_replacements()`'s `'Sheet 17) shows'` special case was
  updated the same way.
- `_PLAN_DATA_SCOPE_PURPOSES` gained a `'17. LTC Stress Test'` entry and
  `'19. Life Insurance'`'s purpose text changed from `'combined protection
  stress test'` to `'life insurance coverage decision'`.
- `CATALOG['long_term_care_stress'].tab` and
  `CATALOG['life_insurance_need'].tab` no longer share the same stale
  `'3C. LTC + Life Insurance'` string — each now documents its own letter
  under the default demo plan (`'4C. LTC Stress Test'`,
  `'4D. Life Insurance Need'`).

**6. `tab=` fields corrected**, not removed (see the W2 deviation note
above), for every module whose group or in-group order changed: State
Residency, S-Corp vs LLC, Social Security, Charitable Giving, Estate &
Legacy, Housing Comparison, Tax-Loss Harvesting, Gain Harvesting, Monte
Carlo, Survivor, LTC Stress Test, Life Insurance Need, Existing Life
Insurance, Disability Income, P&C Umbrella, Quality Control, RMD Audit,
Account Reconciliation, Planning Levers, Assumptions, Plan Data,
Methodology, Glossary, Tax Capacity, Scenario Analysis (hidden, but its
`tab=` was stale against a section that no longer exists as `'16.'` — given
a representative `'3C.'` value consistent with its `COMPARISON` kind's new
group, for whenever W9 restores it).

**7. Tests updated**: `test_workbook_five_area_tabs_functional.py`,
`test_workbook_numbered_section_tabs_functional.py`,
`test_workbook_system_cleanup_and_widths_functional.py`,
`test_optional_module_gating.py` — all pin the new five-group tab strip
(computed by hand against `input/demo/client_optional_functions.csv`'s
actual toggle state, then verified against a real subprocess build).
`test_sheet_table_consistency.py` needed no changes: it was already
shape-agnostic (referential integrity only, no literal section names).

## Verified demo-plan tab strip

With `input/demo/client_optional_functions.csv`'s toggles as committed
(Education Funding / Equity Compensation / Special-Needs / Business
Succession / Existing Life Insurance / Disability Income / P&C Umbrella all
`FALSE`; everything else referenced below `TRUE`):

```
1. Reports:     1A-1H (unchanged)
2. Optimizers:  2A Roth Conversion, 2B HSA Drawdown, 2C Asset Allocation,
                2D Social Security, 2E Charitable Giving,
                2F Estate & Legacy Planning, 2G Housing Comparison,
                2H Tax-Loss Harvesting, 2I Gain Harvesting
                  ("This year's actions" divider row before 2H)
3. Comparisons: 3A State Residency, 3B S-Corp vs LLC
4. Risks:       4A Monte Carlo, 4B Survivor, 4C LTC Stress Test,
                4D Life Insurance Need
5. System:      5A Plan Data, 5B Assumptions, 5C Account Reconciliation,
                5D Quality Control, 5E RMD Audit, 5F Methodology,
                5G Glossary, 5H Planning Levers, 5I Tax Capacity
```

## Does not retire Planning Levers

Confirmed out of scope per the master plan ("Does not retire Planning
Levers — that is W11"). It moved from letter group `'4'` to `'5'` along with
the rest of System, unchanged otherwise.

## Consequences for later workstreams

- **W9** (UI section registry) restores Withdrawal Sequencing, Asset
  Location and Scenario Analysis. Scenario Analysis (`what_if_analysis`,
  `COMPARISON`) will derive into group `'3'` (Comparisons) once it gets a
  `_visible(...)` entry — consistent with State Residency/S-Corp already
  landing there in this workstream.
- **W2** (stable slugs), when it lands, removes the `tab=` field entirely
  per its original plan — nothing in W3 blocks that; W3 only kept `tab=`
  current in the meantime.
- Golden-master dollar figures are unaffected — this workstream is labels
  and organization only, confirmed via `tools/regen_golden_master.py
  measure` before considering the workstream done.
