# Phase C: Legacy & Backwards-Compat Removal — Design Brief for Fable 5

**Status:** Design phase — ready for Fable 5 architectural review  
**Risk Level:** CRITICAL — user plan data at stake  
**Date:** 2026-07-07

---

## Executive Summary

This phase removes 13 backwards-compatibility shims that exist to read old saved plan data. The work is high-risk because:

1. **User data is at stake** — Mistakes corrupt plan files, snapshots, exports
2. **Two different "legacy"s exist** — Bequest domain identifiers (`roth_legacy_*`, `legacy_objective_mode`) must NOT be removed; only data-migration shims should be retired
3. **Sequence matters** — Must migrate all existing plan files first, then gate reads on schema version, then delete shims
4. **Acceptance criteria are strict** — Old saved plans must still load (via migrator); golden-master numbers must not change

---

## The Two "Legacy"s — Critical Distinction

### ❌ DO NOT REMOVE (Domain Terminology)

These are **bequest/estate domain identifiers**, not backwards-compat shims. Removing them breaks the Roth conversion scorer.

- `roth_legacy_score` — bequest value (estate planning)
- `legacy_objective_mode` — bequest objective weight
- `roth_legacy_objective_mode` — bequest objective setting
- `LEGACY_TARGETED` — bequest-focused Roth strategy
- `legacy_adjustment` — bequest-value computation
- `rebalance_legacy_gain_deferral_pct` — bequest-tax deferral
- `roth_bequest_preference_bonus_pct` — bequest preference scoring
- All "legacy/survivor/estate" UI copy phrases

**Why:** These control how the system values and plans for assets left to heirs. Removing them silently breaks bequest-focused plans without error.

### ✅ DO REMOVE (Data Migration Shims)

These exist only to read old plan data formats. Once migrated, they're dead code.

---

## The 13 Shims to Retire

### Shim Group 1: Pre-unified spending model (7 shims)

**Location:** `src/spending_tracker.py` + `src/data_io.py`  
**What they do:** Fold old "wellness" terminology and old budget line formats into the unified budget/tracking model.

| # | Shim | Location | What it tolerates |
|---|---|---|---|
| 1 | `_LEGACY_TRACKING_MAP`, `_legacy_source_page_for_tracking_type` | `spending_tracker.py:476,733` | Maps old tracking-type names (e.g. "wellness" → "healthcare") |
| 2 | `_legacy_budget_to_unified`, legacy CSV header acceptance | `spending_tracker.py:~1447–1610` | Folds old "extra_N" spending rows and legacy scalars into unified budget lines |
| 3 | `contains_user_facing_legacy_wellness()` guard | `terminology_aliases.py` + tests | Prevents UI from showing old "wellness premium" text after migration |
| 4 | Legacy keyword-key alias exposure (2 sites) | `spending_tracker.py:~2195–2252` | Exposes unified aliases with old keyword names for backwards compatibility |
| 5 | Legacy mirror file written on every export | `spending_tracker.py` | Writes `spending_tracker_legacy.csv` on every export for manual user fallback |
| 6 | "Treat old model_managed as housing" | `spending_tracker.py:227` | Classifies old `model_managed` tracking type as housing |
| 7 | Terminology alias layer (8 legacy IDs) | `terminology_aliases.py:23–43` | Maps legacy "wellness_premium", "pre65_wellness_premium", etc. to canonical "healthcare_premium" |

---

### Shim Group 2: Plan data read-side fallbacks (4 shims)

**Location:** `src/data_io.py`  
**What they do:** Accept old plan data shapes and convert them to current shapes during load.

| # | Shim | Location | What it tolerates |
|---|---|---|---|
| 8 | Legacy `extra_N` rows suppressed when budget-lines file exists | `data_io.py:~584–695` | Pre-budget-taxonomy plans with old spending row format |
| 9 | Legacy single Note Receivable layout re-homed under `__legacy_summary__` | `data_io.py:~838–878` | Plans with single note vs. multi-note structure |
| 10 | Legacy `withdrawal_window` honored beside controlled-window control | `data_io.py:~894` | Old withdrawal policy config format |
| 11 | Legacy "Near Term / Long Term / Through YYYY" spending-phase rows | `data_io.py:~935` | Old spending-timeline phase layout |

---

### Shim Group 3: One-time row purges (2 shims)

**Location:** `src/server/csv_migration.py`  
**What they do:** Drop rows that were retired in earlier schema versions (allocated count scalars, old scenario home fields).

| # | Shim | Location | What it tolerates |
|---|---|---|---|
| 12 | `DEPRECATED_ALLOCATION_COUNT_LABELS` | `csv_migration.py:20–28` | Rows that counted allocation targets (feature removed) |
| 13 | `RETIRED_SCENARIO_HOME_ROW_KEYS` | `csv_migration.py:30–40` | Old home-sale scenario fields (consolidated into main home row) |

---

### Hygiene (not plan-data affecting, already mostly done)

- ✅ Untracked `output/` directory (Phase A)
- ✅ Deleted stub launchers (Phase A)
- Deprecation message on `warehouse_compat.py` rename (if any remain)

---

## Migration Strategy

### Current state
- 13 shims scattered across `data_io.py`, `spending_tracker.py`, `csv_migration.py`
- Every plan load re-applies all shims lazily (hidden tax on every read)
- Old saved plan files (`*.rpx` exports, `input/client_data.csv`, test fixtures) still use old formats
- No explicit schema versioning for plan data

### Safe retirement sequence (do not reorder)

#### Step 1: Design the migrator (Fable 5)
- Define plan-data schema versions (`v1` = current, `v0` = pre-unified)
- Design `tools/migrate_plan_data.py` that:
  1. Loads a v0 plan through current readers (shims still active)
  2. Rewrites it in canonical v1 form only
  3. Stamps `"schema_version": "v1"` marker
  4. Backs up original to `{filename}.v0.backup`

#### Step 2: Implement + test (Opus 4.8)
- Write `migrate_plan_data.py` command-line tool
- Test it migrates real plans (golden-master cases + `input/client_data.csv`)
- Migrate in-place: `input/`, `saved_plans/*.rpx`, test fixtures
- Regenerate `plan_data_manifest` and golden-master fixtures
- Verify projection numbers unchanged byte-for-byte (golden-master test)

#### Step 3: Gate reads on schema version (Opus 4.8)
- Modify `data_io.load_csv()` to:
  1. Check for `"schema_version"` marker
  2. If missing → assume v0, invoke migrator once (with backup), retry read
  3. If v0/v1 mismatch → error with helpful message
- Keep shims active (no change yet) so migrated plans load correctly

#### Step 4: Delete the shims (Opus 4.8)
- `spending_tracker.py`: Delete `_LEGACY_TRACKING_MAP`, `_legacy_budget_to_unified`, legacy mirror-file write
- `data_io.py`: Delete all legacy read-side fallbacks (shims 8–11)
- `terminology_aliases.py`: Delete `HEALTHCARE_PREMIUM` alias mappings + guard function (shim 7)
- `csv_migration.py`: Evaluate whether purge window has passed; if so, delete purges (shims 12–13)
- Test that old plans still load via the migrator

#### Step 5: Wellness → healthcare UI copy sweep (Sonnet 5)
- After data migration, `wellness` no longer appears in saved data
- Rename 37 occurrences of "wellness" in `frontend/js/dashboard.js` to "healthcare"
- Update help text that refers to "wellness bridge" → "retirement funding bridge"
- Regenerate `output/` workbook to verify no "wellness" in reports

#### Step 6: After one stable release, evaluate deleting migrator
- If no v0 plans exist in the wild, delete `migrate_plan_data.py`
- Keep only v0→v1 support if any users still have old exports

---

## Critical Safety Considerations

### 1. The Bequest-vs-Compat Ambiguity

**Risk:** A naive find-and-delete for "legacy" in the codebase will delete bequest scoring.

**Mitigation:** Grep patterns for what to delete are exact and listed in this document. Fable 5 must review every deletion by hand.

```bash
# Safe patterns to delete:
grep -r "_legacy_tracking_map\|_legacy_budget_to_unified\|DEPRECATED_ALLOCATION_COUNT_LABELS"

# ❌ DANGEROUS — will match bequest code:
grep -r "legacy" src/
```

### 2. Backwards compatibility window

**Risk:** A v0 plan loaded before the migrator is deployed will silently corrupt.

**Mitigation:** Schema-version gate prevents this. Any load triggers migration once, with backup.

### 3. Golden-master regression

**Risk:** Deleting a shim changes projection numbers by 0.01%, silently breaking long-term plans.

**Mitigation:** Every commit must verify `pytest tests/test_2_recommendations.py` — the golden-master byte-diff test.

### 4. Test fixtures

**Risk:** Old test fixtures still using v0 format will break.

**Mitigation:** Migrate `tests/fixtures/golden_master_engine_cases.json` and all CSV test fixtures at step 2. Regenerate.

---

## Acceptance Criteria

1. ✅ `tools/migrate_plan_data.py` exists, documented, tested
2. ✅ All user-facing plan files migrated (input/, saved_plans/, fixtures)
3. ✅ `data_io.load_csv()` gates on schema version
4. ✅ Old v0 plans still load (via migrator, with backup)
5. ✅ Golden-master projections unchanged byte-for-byte
6. ✅ 13 shims deleted
7. ✅ "Wellness" terminology replaced with "healthcare" in UI
8. ✅ No test failures (golden-master + new migration tests pass)
9. ✅ Migration documented in CLAUDE.md

---

## Key Decisions for Fable 5

**These must be decided before implementation begins:**

1. **Schema versioning format:** Store in plan data as JSON key, or in a separate metadata file?
2. **Migrator scope:** Should it be a one-shot CLI tool, or also callable from Python for tests?
3. **Backup retention:** Keep v0 backups forever, or rotate after N migrations?
4. **Error handling:** If migration fails, should we fall back to v0 read (risky) or error (safe)?
5. **One-time purges:** Have we crossed the migration window for `DEPRECATED_ALLOCATION_COUNT_LABELS` and `RETIRED_SCENARIO_HOME_ROW_KEYS`? Can we delete them immediately, or keep them?
6. **Wellness terminology:** Is "wellness bridge" still used in any user-facing text/reports, or can we rename it all to "retirement funding bridge"?

---

## Timeline & Model Assignment

| Step | Work | Model | Days | Notes |
|---|---|---|---|---|
| 1 | Design migrator, schema versioning, sequence | **Fable 5** | 0.5 | This document + decisions above |
| 2 | Implement migrator, migrate files, test | Opus 4.8 | 1.5 | Golden-master byte-diff mandatory |
| 3 | Gate reads on schema version | Opus 4.8 | 0.5 | Straightforward change to data_io.load_csv |
| 4 | Delete 13 shims | Opus 4.8 | 1 | Review every deletion; grep patterns are exact |
| 5 | Wellness→healthcare UI sweep | Sonnet 5 | 0.5 | After data migration, 37 occurrences in dashboard.js |
| 6 | Code review + final verification | **Fable 5** | 0.5 | Byte-diff test passes; golden-master unchanged |

**Total: ~4–5 days, 2–3 PRs, zero user-facing breakage if done correctly.**

---

## Reference: Full Shim Details

### Shim 1: `_LEGACY_TRACKING_MAP`
**File:** `spending_tracker.py:476`  
**Code:**
```python
_LEGACY_TRACKING_MAP = {
    "wellness": "healthcare",
    "wellness_premium": "healthcare",
    # ... 6 more mappings
}
```
**Purpose:** Map old CSV labels to current canonical names  
**Delete:** Yes, after data migrated

### Shim 2: `_legacy_source_page_for_tracking_type`
**File:** `spending_tracker.py:733`  
**Purpose:** Route old spending-line types to the right source page  
**Delete:** Yes

### Shim 3: `_legacy_budget_to_unified`
**File:** `spending_tracker.py:~1447`  
**Purpose:** Fold old "extra_N" spending rows into unified budget lines  
**Delete:** Yes, after migration

### Shim 4: Legacy CSV header acceptance
**File:** `spending_tracker.py:1092`  
**Purpose:** Accept both old "section/subsection/label/value" and new unified headers  
**Delete:** Yes

### Shim 5: Legacy mirror-file write
**File:** `spending_tracker.py` (export code)  
**Purpose:** Write `spending_tracker_legacy.csv` on every export for manual fallback  
**Delete:** Yes (users should export `spending_budget_lines.csv` instead)

### Shim 6: "Treat old model_managed as housing"
**File:** `spending_tracker.py:227`  
**Code:**
```python
if tracking_type == "model_managed":
    tracking_type = "housing"
```
**Purpose:** Old plans used `model_managed` tracking; reclassify as housing  
**Delete:** Yes

### Shim 7: Terminology alias layer
**File:** `terminology_aliases.py:23–43`  
**Code:**
```python
HEALTHCARE_PREMIUM = TerminologyAlias(
    canonical_id="healthcare_premium",
    legacy_ids=("wellness_premium", "pre65_wellness_premium", ...),
)
```
**Purpose:** Map 8 old "wellness" CSV IDs to canonical "healthcare"  
**Delete:** Yes (after data migrated, all CSVs use canonical IDs)

### Shim 8: Legacy `extra_N` row suppression
**File:** `data_io.py:~584`  
**Purpose:** Suppress old `extra_1`, `extra_2`, ... spending rows if budget-lines file exists  
**Condition:** "Plans without the budget-lines file keep legacy behavior"  
**Delete:** Yes, if budget-lines is now mandatory

### Shim 9: Legacy note layout re-homing
**File:** `data_io.py:~838–878`  
**Purpose:** If plan has single "Note Receivable" section, re-home it under synthetic `__legacy_summary__` subsection  
**Why:** Old schema had flat note layout; new schema has nested structure  
**Delete:** Yes

### Shim 10: Legacy `withdrawal_window`
**File:** `data_io.py:~894`  
**Purpose:** Honor old `withdrawal_window` config alongside new controlled-window config  
**Code:**
```python
# Legacy withdrawal_window is still honored when present.
controlled_window = ...
if legacy_withdrawal_window:
    controlled_window = legacy_withdrawal_window
```
**Delete:** Yes

### Shim 11: Legacy spending-phase rows
**File:** `data_io.py:~935`  
**Purpose:** Accept old "Near Term / Long Term / Through YYYY" phase layout  
**Delete:** Yes (new schema uses explicit year ranges)

### Shim 12: `DEPRECATED_ALLOCATION_COUNT_LABELS`
**File:** `csv_migration.py:20–28`  
**Purpose:** Purge old "count_*_toward_target" rows (feature removed)  
**Decision:** Has the migration window passed? If so, delete immediately. If not, keep purge active.

### Shim 13: `RETIRED_SCENARIO_HOME_ROW_KEYS`
**File:** `csv_migration.py:30–40`  
**Purpose:** Purge old home-sale scenario rows (consolidated into main home row)  
**Decision:** Same as shim 12 — has migration window passed?

---

## Out of Scope (Already Done or Phase D+)

- ✅ Phase A removed drifted `output/` directory
- ✅ Phase A deleted stub launchers (`launch_ui.py`, `run_wsgi_server.py`)
- Phase B will modernize tests (separate concern)
- Phase D will decompose oversized modules (separate concern)

---

## Related Files & Tests

**Read these before starting:**
- `documentation/SYSTEM_MODERNIZATION_PLAN.md` Section 2 (full inventory)
- `src/spending_tracker.py` (lines 200–2300, the consolidation)
- `src/data_io.py` (lines 500–950, plan-data parsing)
- `src/server/csv_migration.py` (rows purges)
- `tests/test_2_recommendations.py` (golden-master — must pass byte-for-byte)
- `tests/fixtures/golden_master_engine_cases.json` (baseline numbers)

**Will need to migrate:**
- `input/client_data.csv` (canonical test plan)
- `saved_plans/*.rpx` (exported plans)
- All test fixtures in `tests/fixtures/`
- Golden-master expectations

---

## Next Steps

1. **Fable 5:** Review this brief, answer 6 key decisions, confirm sequence
2. **Opus 4.8:** Implement per Fable 5's design, migrate files, test golden-master byte-diff
3. **Sonnet 5:** Execute wellness→healthcare sweep
4. **Fable 5:** Final review before merge
