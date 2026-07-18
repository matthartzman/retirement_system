# Phase C: Legacy Removal & Data Migration — Design Brief for Fable 5

**Status:** Design phase — ready for architectural review  
**Risk Level:** HIGH — all saved plan files and historical data at stake  
**Date:** 2026-07-07

---

## Executive Summary

This phase removes 13 backwards-compatibility shims (read-side data migration logic) and replaces them with a single, versioned one-time migrator (`tools/migrate_plan_data.py`). The work is high-risk because:

1. **Saved plan files orphaned if wrong.** Every `.rpx` export and plan data CSV older than 6 months uses the pre-migration format; a bad migrator breaks all history.
2. **Bequest ≠ Legacy trap.** The word "legacy" appears in two unrelated contexts (backwards-compat shims AND bequest scoring); automated "remove legacy" sweeps break the Roth scorer.
3. **Silent numeric regression.** The golden-master byte-diff test gates every projection engine change; a migration error that slightly tweaks inputs silently breaks results.
4. **Cross-cutting data flow.** Shims hide in 7 different modules; each removal must re-wire data flow through the versioned migrator.

---

## Current State — Inventory of Backwards-Compat Shims

### Data-Read Shims (1–9, must be removed in order via migration)

| # | Shim | Location | When Introduced | What It Tolerates |
|---|---|---|---|---|
| 1 | Legacy `extra_N` spending rows suppressed if budget-lines file exists | `data_io.py:584-695` | Pre-unified spending model (~2024-Q3) | Plans without `client_spending_budget_lines.csv` |
| 2 | Legacy `annual_charitable_giving_*` scalar fields folded into taxonomy budget | `data_io.py:650` | Older versions | Charity as direct fields, not budget lines |
| 3 | Legacy single Note Receivable layout re-homed under `__legacy_summary__` | `data_io.py:838-878` | Very old | Single note (not multi-note/HELOC) |
| 4 | Legacy `withdrawal_window` honored alongside controlled-window control | `data_io.py:894` | Pre-withdrawal-sequencing (~2025-Q1) | Old withdrawal config format |
| 5 | Legacy "Near Term / Long Term / Through YYYY" rows accepted conditionally | `data_io.py:935` | Pre-unified spending model | Old spending-phase labels |
| 6 | "Forgiving" parse of older files storing values in wrong shapes | `data_io.py:917` | Legacy data-entry formats | String→number conversions, lenient field shapes |
| 7 | `_LEGACY_TRACKING_MAP`, `_legacy_budget_to_unified` fold-in, legacy tracking type alias exposure (2 sites), legacy mirror file export | `spending_tracker.py:227,476,733,1092,1303-1484,2195-2252` | Pre-unified spending (~2024-Q3) | Old budget-tracking model |
| 8 | Wellness→healthcare terminology alias layer (8 premium IDs, 3 OOP cap IDs) + `contains_user_facing_legacy_wellness` test guard | `terminology_aliases.py` (consumed by data_io, reporting, admin) | Pre-healthcare naming | Old CSV labels in snapshots |
| 9 | One-shot row purges: `DEPRECATED_ALLOCATION_COUNT_LABELS`, `RETIRED_SCENARIO_HOME_ROW_KEYS` | `server/csv_migration.py` | Previous versions | Rows retired in prior releases |

### Hygiene Items (10–13, independent, can be removed anytime)

| # | Item | Location | Impact |
|---|---|---|---|
| 10 | Deprecation stub launchers (`raise SystemExit` redirects) | `tools/launch_ui.py`, `tools/run_wsgi_server.py` | Nothing — just doc clutter |
| 11 | Tracked generated `output/` tree (drifted from `frontend/`) | `output/` (git-tracked) | Nothing — hygiene; untrack + gitignore |
| 12 | Case-collision doc duplicate | `documentation/release_notes/INDEX.md` vs `index.md` | Nothing — one redundant file |
| 13 | Roadmap/breadcrumb tests + source comments they pin | `tests/test_29_*.py`, `tests/test_92_*.py` | Nothing — pure changelog assertions |

### CRITICAL DISTINCTION: Bequest ≠ Legacy (DO NOT REMOVE)

**Keep (domain terminology, live features):**  
- `roth_legacy_score`, `legacy_objective_mode`, `roth_legacy_objective_mode`, `LEGACY_TARGETED`, `legacy_adjustment`, `rebalance_legacy_gain_deferral_pct`
- All "legacy/survivor/estate" phrases in UI copy

These refer to *bequest* (estate value left to heirs), NOT backwards-compat shims. Any automated "remove legacy" sweep that touches these breaks Roth conversion scoring.

**Future refactor (Phase G, not Phase C):** Rename identifiers to `bequest_*` to eliminate "legacy" ambiguity — but that is a domain rename requiring plan-data key migration, not a removal.

---

## Phase C Workstreams

### Workstream 1: Design Migrator Architecture (Fable 5)

**Scope:** Define the one-time migrator strategy, schema versioning, and shim-retirement order.

**Current flow:**  
```
load old plan CSV → ~9 scattered shims forgive format → data structure
                    (hidden in data_io.py, spending_tracker.py, etc.)
```

**Proposed flow:**  
```
detect schema version → if old: invoke migrator (once, with backup) → canonical format
                                                                     → write new schema version
load canonical plan → no shims, no format tolerance
```

**Design requirements:**

1. **Schema versioning:** Define how versioned data looks. Options:
   - **Option A:** `schema_version` field in every CSV section header (new row: `SCHEMA_VERSION, 1.0`)
   - **Option B:** Separate manifest file (`plan_metadata.json` with `{"schema_version": "1.0", "migration_timestamp": "..."}`)
   - **Option C:** Bumped file name (`client_data_v1.csv`, rolling rename on every migration)
   - **Recommendation:** Option B (metadata file) — allows multiple CSVs, easier to query without parsing headers
   
2. **Migrator scope:** Which shims fold into the one-time migrator?
   - **Must include:** 1–9 (read-side compatibility)
   - **Must NOT include:** 10–13 (hygiene items, independent deletions) or bequest identifiers
   - **Question:** Should wellness→healthcare rename happen in the migrator (Phase C) or separately (Phase E UI sweep)?
     - **Option A:** Rename in migrator → all saved data uses "healthcare" terminology
     - **Option B:** Rename only in display layer (Phase E) → saved data still has "wellness", alias on read
     - **Recommendation:** Option A (migrate data, then UI follows) — cleaner long-term, but more rework now
   
3. **Backup retention policy:** How many pre-migration backups to keep?
   - **Option A:** Keep all (slow disk usage, complete audit trail)
   - **Option B:** Keep last 5 (balance safety + disk usage)
   - **Option C:** Keep last 1, auto-delete older (minimal footprint, lose trail)
   - **File naming:** `client_data.csv.pre_migration_<timestamp>`
   - **Location:** `local_state/` (not synced to cloud, survives local app restarts)
   - **Recommendation:** Option B (last 5) with `local_state/` location — permits recovery without bloat
   
4. **Error handling:** What if migration fails mid-plan?
   - **Option A:** Fail load, offer "rollback to backup" button, raise to user
   - **Option B:** Fail load, auto-rollback, log error, retry on next load
   - **Option C:** Skip the plan (don't load), add to "damaged plans" list for manual review
   - **Recommendation:** Option A (fail explicitly) — data integrity > convenience, user can make informed choice
   
5. **Purge window:** When is it safe to delete the migrator?
   - **Option A:** Never — keep forever as a living archive of all format versions
   - **Option B:** After 2 stable releases — most plans will have been migrated by then
   - **Option C:** After 6 months — assume users who don't upgrade by then have archived plans
   - **Plan:** Step 5 in migration method (Section 2.3 of `SYSTEM_MODERNIZATION_PLAN.md`) says "After one stable release, evaluate deleting for pre-unified formats, keeping only N-1→N"
   - **Recommendation:** Option B (2 releases) with a deprecation warning in v10.1
   
6. **Wellness terminology scope in Phase C:**
   - **Option A:** Migrate data: rename saved-plan CSV keys from `wellness_premium` → `healthcare_premium`, etc. (8 + 3 = 11 key renames)
   - **Option B:** Leave saved-plan data unchanged, handle rename in UI/alias layer only (Phase E)
   - **Tradeoff:** Option A is cleaner (no aliases needed), but commits to 11 breaking data changes
   - **Recommendation:** Option A (migrate in Phase C) — aligns with Workstream 1's goal of "zero shims post-migration"; Phase E focuses on UI consistency, not data surgery

**Acceptance criteria:**
- ✅ Schema versioning strategy defined with sample metadata
- ✅ Migrator design documented (flowchart of which shims execute, in order)
- ✅ Backup retention policy specified (number, location, naming, TTL)
- ✅ Error-handling flow defined (fail/rollback/skip decision tree)
- ✅ Purge window decided with deprecation timeline
- ✅ Wellness scope clarified (data migration vs UI-only rename)
- ✅ All 6 decisions documented in implementation brief for Opus 4.8

---

### Workstream 2: Implement Migrator + Delete Shims (Opus 4.8)

**Scope:** Following Fable 5's design, implement `tools/migrate_plan_data.py` and retire shims.

**Implementation method (from Section 2.3 of plan):**

1. **Write one-time migrator** `tools/migrate_plan_data.py`:
   - Loads a plan through *current* forgiving readers (using shims 1–9 as written)
   - Rewrites in canonical form (unified budget, healthcare terminology, multi-note layout, canonical withdrawal window, purges applied)
   - Stamps schema version via `schema_registry.py`
   - Backs up pre-migration files

2. **Migrate in place:**
   - Run migrator over `input/client_*.csv`
   - Run migrator over all `saved_plans/*.rpx` files
   - Run migrator over test fixtures (`tests/fixtures/`)
   - Regenerate `tools/check_plan_data_sync.py --write` manifests
   - Regenerate golden-master fixtures (`tests/fixtures/golden_master_engine_cases.json`)

3. **Gate loads on schema version:**
   - Loader accepts current-version files directly
   - Loader detects old-version files, invokes migrator (once, with backup), proceeds
   - Replaces ~9 scattered shims with one explicit versioned migration path

4. **Delete shims:**
   - Remove items 1–9 from `data_io.py`, `spending_tracker.py`, `terminology_aliases.py`
   - Remove legacy mirror-file export
   - Remove alias payload endpoint if UI no longer needs it
   - Remove breadcrumb comments/tests (item 13, folded into Phase B test cleanup)

5. **Post-release evaluation:**
   - After one stable release, consider deleting pre-unified-format support
   - Keep only version-N-1 → N support long-term

**Acceptance criteria:**
- ✅ `tools/migrate_plan_data.py` successfully migrates all formats (1–9) to canonical
- ✅ Schema version stamped on migrated files
- ✅ Backups created with correct naming, location, retention
- ✅ `input/`, `saved_plans/`, test fixtures migrated
- ✅ `grep -riE 'legacy|backward|deprecated' src/ frontend/js/` returns only bequest-domain identifiers + migrator
- ✅ Golden-master projection numbers unchanged byte-for-byte (test with `pytest tests/test_2_recommendations.py --tb=short`)
- ✅ Loading a pre-migration `.rpx` still succeeds (migrator runs invisibly)
- ✅ All tests pass post-shim-deletion
- ✅ Manual smoke test: load a pre-migration saved plan, verify numbers match golden master

---

### Workstream 3: Wellness→Healthcare UI Sweep (Sonnet 5, after Phase C data migration)

**Scope:** After data migration eliminates wellness terminology from saved files, update UI to match.

**Files to update:**
- `frontend/js/dashboard.js` (37 occurrences of "wellness")
- Test files (5 occurrences)
- Documentation/help text

**Pattern:**
```
# Before (Phase C saves data with "healthcare" keys)
wellness_premium → healthcare_premium (in CSV)
dashboard.js: "Wellness Premium" → "Healthcare Premium" (UI label)

# After (Phase E focuses on help text architecture, not terminology)
```

**Acceptance criteria:**
- ✅ `grep -r "wellness" frontend/js/dashboard.js` returns 0 results
- ✅ `grep -r "wellness" tests/` returns 0 results (except comments explaining the old term)
- ✅ All UI references to "healthcare" consistent across pages

---

## 6 Key Decisions for Fable 5

1. **Schema versioning format:** Metadata file (Option B) or header-embedded (Option A)?
2. **Wellness terminology scope:** Rename in migrator (Phase C, Option A) or UI-only alias (Phase E, Option B)?
3. **Backup retention:** How many pre-migration backups to keep (Option A: all, B: last 5, C: last 1)?
4. **Error handling:** Fail explicitly (A), auto-rollback (B), or skip (C)?
5. **Purge window:** When to delete the migrator (2 releases, 6 months, or never)?
6. **Migrator testing:** Should we test by loading each legacy format separately, or just end-to-end smoke test?

---

## Sequencing & Dependencies

### Hard sequencing rules (do not reorder)

1. **Phase B (test modernization) MUST complete first**
   - String-matching tests break on every data-structure rename the migrator introduces
   - Once converted to behavior tests, migration won't break CI

2. **Phase C before Phase D's `data_io.py`/`spending_tracker.py` splits**
   - Shim removal shrinks these modules by 20–30%
   - Cleaner boundaries once shims are gone

3. **Phase C before Phase E's wellness→healthcare UI sweep**
   - UI copy can't drop "wellness" until saved data stops using it
   - Phase E assumes data already canonical

4. **Golden-master byte-diff test MANDATORY**
   - Run after every commit: `pytest tests/test_2_recommendations.py --tb=short`
   - Expected: numbers match to within 2.0 delta for net worth, 1.0 for individual cases

### Timeline

| Step | Work | Model | Days | Blocker? |
|---|---|---|---|---|
| 1 | Fable 5 review + answer 6 decisions | **Fable 5** | 0.5 | Must complete |
| 2 | Opus 4.8 design: data flow, migration order, error paths | Opus 4.8 | 1 | After Fable 5 |
| 3 | Implement migrator + test on fixtures | Opus 4.8 | 1.5 | Highest risk |
| 4 | Migrate `input/`, `saved_plans/`, regenerate golde masters | Opus 4.8 | 1 | After implementation |
| 5 | Delete shims 1–9, hygiene items 10–13 | Opus 4.8 | 0.5 | After migration verified |
| 6 | Wellness→healthcare UI sweep (Phase E, after Phase C merge) | Sonnet 5 | 0.5 | After Phase C |
| 7 | Code review + golden-master verification | **Fable 5** | 0.5 | Before merge |

**Total:** ~5–6 days, 2–3 PRs

---

## Risk Assessment

### High risks

1. **Migrator produces silent numeric changes**
   - **Mitigation:** Golden-master byte-diff gate on every commit; if baseline changes, document the reason in writing
   - **Catch:** Fable 5's pre-merge review catches hidden regressions

2. **Missing a shim location**
   - Previous passes found shims in 7 modules; a missed shim leaves old format readers active
   - **Mitigation:** Grep for `legacy|backward` post-deletion; CI guard catches this

3. **Wellness sweep breaks after-Phase-C plans**
   - **Mitigation:** Phase C migrates data; Phase E updates UI only; the two are independent

### Medium risks

1. **Backup clutter from repeated migrations**
   - **Mitigation:** Purge oldest backups beyond retention limit automatically

2. **Testing coverage of each legacy format**
   - Each shim handles a different pre-format; need fixtures for each
   - **Mitigation:** Existing test data may cover multiple formats; verify with `pytest tests/ --tb=short -q`

---

## Acceptance Criteria

1. ✅ Schema versioning strategy designed and documented
2. ✅ Migrator flowchart defined (which shims, in order, with error paths)
3. ✅ Backup policy specified (count, location, TTL)
4. ✅ Wellness scope decided (data migration vs UI-only)
5. ✅ `tools/migrate_plan_data.py` implemented and tested on fixtures
6. ✅ All plan files in `input/`, `saved_plans/` migrated with backups
7. ✅ Shims 1–9 deleted; grep returns 0 legacy-compat occurrences (outside migrator + bequest)
8. ✅ Hygiene items 10–13 cleaned up (output/ untracked, docs deduped, tests deleted)
9. ✅ Golden-master projection numbers unchanged byte-for-byte
10. ✅ All tests pass (`pytest tests/ --tb=short -q`)
11. ✅ Manual smoke test: load pre-Phase-C saved plan, verify it loads and numbers match
12. ✅ Migrations documented in CLAUDE.md

---

## Out of Scope (Phase D+)

- Module decomposition (Phase D)
- Usability improvements (Phase E)
- Enhancements (Phase F)
- Bequest → `bequest_*` rename (Phase G, future)

---

## Related Files

- `src/data_io.py` (shims 1–6, lines 584-935)
- `src/spending_tracker.py` (shim 7, lines 227-2252)
- `src/terminology_aliases.py` (shim 8)
- `src/server/csv_migration.py` (shim 9)
- `src/schema_registry.py` (version stamping)
- `tests/test_2_recommendations.py` (golden-master gate)
- `documentation/SYSTEM_MODERNIZATION_PLAN.md` Section 2 (full shim inventory)

---

## Next Steps

1. **Fable 5:** Review this brief, answer 6 key decisions, approve design
2. **Opus 4.8:** Design migrator implementation (flowchart, data structures, error paths)
3. **Opus 4.8:** Implement, test, and migrate all plan files
4. **Fable 5:** Pre-merge review for silent numeric regressions
5. **Sonnet 5:** Wellness→healthcare UI sweep (Phase E, after merge)

---

Generated by Claude Code

