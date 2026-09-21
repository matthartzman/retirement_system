# W0 — Pre-flight verification findings

> Deliverable of **W0** in
> `docs/superpowers/plans/2026-09-19-optimizers-modules-housing-master-plan.md` §3.
> Three cheap checks whose answers change the size or content of W1, W3 and W5.
> Read-only: no code changed in this workstream.

Executed 2026-09-21. Each finding states the answer, the evidence that decided
it, and the consequence for the workstream that was waiting on it.

---

## V1 — Does a toggle change raise a `build_impact` notice today?

**YES — on both legs, through the generic plan-data path. W5 has nothing to
wire here.**

`client_optional_functions.csv` is an ordinary plan-data file
(`src/plan_data_registry.py:34`, inside `PLAN_DATA_FILES`), and its toggle rows
are rendered by the generic boolean field renderer, so a toggle edit travels the
same rail as any other row edit. No branch anywhere special-cases the
`"Optional Functions"` section.

**Unsaved edit.** `editValue()` sets `dirty.set(idx, …)` and `lastBuildOk = false`
(`frontend/js/dashboard_decomp_row_model.js:4049-4065`) with no section branch.
`hasUnsavedPlanChanges()` is `dirty.size || …` (same file, `:4622-4638`), so
`addStaleAdvisorNotice()`'s condition
`!lastBuildOk && hasUnsavedPlanChanges()`
(`frontend/js/dashboard_source_truth_banners.js:331-343`) is satisfied and the
"Advisor-ready disabled: plan inputs changed after the last successful build"
banner renders on the `review` / `build_impact` / `detailed_results` steps.

**Saved edit.** `optional_functions` is in `AUTOSAVE_STEPS`
(`frontend/js/navigation.js:14`), so the edit is usually saved before the user
reaches `build_impact`, which clears `dirty` — but the saved case is covered
server-side instead. Saving touches the SQLite working copy, and
`build_preflight_payload()` compares the DB mtime against each essential
artifact's mtime (`src/server_services/build_service.py:125-137`), emitting
"Saved plan data is newer than one or more report outputs. Rebuild reports…" and
reporting `current: false`. `lastBuildOk` is only restored to `true` when
`/api/build/status` reports `current` (`frontend/js/dashboard.js:6999-7007`), so
it stays false until an actual rebuild.

**Consequence for W5.** Drop the contingent "wire `build_impact` on toggle
change" task. It does not exist.

**One nuance W5 should record rather than fix.** The coverage is *generic* — it
says "your build is stale", at file and DB granularity. It cannot say *which*
sheets a specific toggle added or removed, because nothing module-aware
participates in the staleness signal. That is fine: #330's requirement is that a
toggle change not silently leave a stale build presented as current, and it does
not. A per-module "turning this off removes sheets X and Y" preview is the W4
off-impact line, a different surface with a different source, and it must not be
built on the staleness path.

---

## V2 — Are the three held-coverage modules inventories or sizing analyses?

**All three are inventories. `domain = "Assets & Protection"` for all three.
#330 §4.3's owned-vs-needed split stands exactly as written; no `domain` value
moves.**

| Module | Verdict | Domain |
|---|---|---|
| `existing_life_insurance` | Inventory | Assets & Protection |
| `disability_income_insurance` | Inventory | Assets & Protection |
| `property_casualty_umbrella` | Inventory | Assets & Protection |
| `life_insurance_need` *(contrast)* | Sizing | Risk & Resilience |

**The deciding evidence is the empty-policy path, not the section list.** Each of
the three builders returns early with a "no policies on file" placeholder and a
QC note before computing anything: `build_existing_life`
(`src/reporting/sheets_protection.py:60-68`), `build_disability` (same file,
`:150-157`) and `build_pc_umbrella` (`:230-238`). A module that has nothing to say when the household
holds no policy is reporting on coverage held. The module docstring states the
same relationship directly — these sheets are "the in-force counterpart to the
Life Insurance *need* analysis (Sheet 19)" (`sheets_protection.py:1-14`).

**Why the adequacy sections do not change the answer.** All three sheets do carry
an adequacy verdict — DI's replacement ratio against a 60–70% target
(`sheets_protection.py:182-195`), P&C's `recommended = net_worth × target_multiple`
and gap (`:262-276`). Read alone, those look like sizing. But each is computed
*about the policies the household already holds* and is unreachable without them,
which is the opposite of `life_insurance_need`: `build_sheet19`'s Need / Gap
Analysis (`src/reporting/sheets_stress.py:1201-1253`) derives a needed amount
from the survivor stress scenario and nets existing death benefits out of it, so
it produces a recommendation whether or not any policy exists. That is the line
§4.3 draws — "do I own disability insurance" (a fact about the balance sheet)
versus "how much should I buy" (an analysis) — and the three fall on the owned
side of it.

An earlier read of this question weighed the Section B adequacy verdicts and
came out the other way for DI and P&C. The empty-policy early return is what
settles it; recording the near-miss here so W1 does not relitigate it.

**Consequence for W1.** Write §4.2's table unchanged. All four protection
modules keep workbook section 4.2 under Risks regardless — `section` derives from
`kind`, not `domain`, so the two surfaces disagreeing here is the intended
design, not drift.

---

## V3 — Is Tax Capacity's home Reports, or its own Reference section?

**Reports. Confirmed; no Reference section is created.**

`11B. Tax Capacity` sits in section `2` (Optimizers) today —
`_spec('2', '2', 16, '2', 14, 'Tax Capacity')`, `src/module_catalog.py:603` —
with no `CATALOG` entry, which is why #329 §2 reclassified it as a Worksheet
("derives nothing new"; a consolidated headroom view assembled from four other
sheets).

The alternative #329 §5.1 left open was a one-tab Reference section. Two facts
close it:

1. **The one-tab premise holds.** The `REFERENCE`-kind modules are
   `planning_levers_echo`, `assumptions_ref`, `plan_data_ref`,
   `methodology_rerun` and `glossary` (`src/module_catalog.py:435-462`). Every
   one of the last four already lives in the System section (`4A`, `4B`, `4F`,
   `4G`), and `planning_levers_echo` is retired in W11. So a Reference section
   created for Tax Capacity would hold exactly one tab, permanently.
2. **The System section is not its home either.** `_SECTION_META['4']`
   (`src/reporting/workbook_common.py:206-211`) describes section 4 as the plan
   data snapshot, assumptions, QC, RMD audit, methodology and glossary — the
   auditability surface. Tax Capacity is plan *content* a reader acts on, not
   documentation of how the run was produced.

A consolidated headroom view reads naturally as a report, so it joins section 1.

**Consequence for W3.** Move `11B. Tax Capacity` into the Reports section,
appended after the existing Reports sheets; give it a `CATALOG` entry in W1 with
the Worksheet classification and `domain = "Taxes"` (#330 §4.2 row 5, which
already lists Tax Capacity under Taxes). No new section code is introduced, and
`_SECTION_META` gains no fifth entry on account of this module.

---

## Carried into W1 and W3

- W1 writes `domain` for all 40 modules using #330 §4.2's table verbatim; V2
  changed nothing in it.
- W1's `CATALOG` entry for Tax Capacity carries `domain = "Taxes"`.
- W3 places Tax Capacity in Reports and does **not** create a Reference section.
- W5 drops its contingent `build_impact` task.

---

## Addendum (2026-09-21) — V3 overridden by explicit direction

**Tax Capacity now files in System, not Reports.** The user gave a direct
instruction to move it there, overriding the reading above. Recorded rather
than silently edited out, since the reasoning above is still sound *as an
inference* — it is simply not what shipped.

The move required reclassifying `tax_capacity`'s `kind` from `WORKSHEET` to
`REFERENCE`: `WORKSHEET`'s letter group is Reports (shared with
`current_vs_proposed`, which stays there), and `REFERENCE`'s is System
(alongside Plan Data, Assumptions, Methodology, Glossary). The `domain` axis
(Taxes, #330 §4.2) is unaffected — placement changed, not which category a
future switch nav groups it under. See
`docs/superpowers/plans/2026-09-21-w1-catalog-foundation-notes.md` for the
implementation.
