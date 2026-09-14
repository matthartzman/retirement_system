# Phase C: Architectural Decisions (Fable 5 Review)

**Date:** 2026-07-07  
**Reviewer:** Claude Fable 5 (Senior Architect)  
**Status:** APPROVED — ready for Opus 4.8 implementation

---

## Decision 1: Schema Versioning Format

**Question:** Metadata file (Option B) or header-embedded (Option A)?

**Decision: OPTION B — Separate metadata file (`plan_metadata.json`)**

**Rationale:**
- **Cleaner queries:** Multiple CSV files (client_data.csv, client_holdings.csv, client_liabilities.csv, client_spending_budget_lines.csv) share one metadata file, avoiding version inconsistencies
- **No header pollution:** Plan data CSVs remain human-readable; version info stays in machine-only metadata
- **Future-proof:** As plan data evolves to YAML/JSON, metadata format can normalize independently
- **Existing precedent:** `schema_registry.py` already manages versioning; this extends that pattern

**Implementation:**
```json
// plan_metadata.json (stored in input/ directory)
{
  "schema_version": "1.0",
  "migration_timestamp": "2026-07-07T12:34:56Z",
  "format_description": "Unified budget lines, healthcare terminology, multi-note layout",
  "migrated_from": "0.9"
}
```

**Validation:**
- Loader reads `plan_metadata.json` first
- If missing or version < 1.0, invoke migrator
- If version == 1.0, proceed normally
- Post-migration, metadata is regenerated with current version

---

## Decision 2: Wellness Terminology Scope

**Question:** Rename in migrator (Phase C, Option A) or UI-only alias (Phase E, Option B)?

**Decision: OPTION A — Migrate data in Phase C**

**Rationale:**
- **Eliminates aliases:** Once data is canonical, `terminology_aliases.py` can be deleted entirely (shim 8 retirement)
- **Single source of truth:** All layers (backend, UI, reports, saved files) use "healthcare" uniformly
- **Cleaner Phase E:** Usability phase focuses on help-text architecture, not data surgery
- **Future-proofs bequest rename:** When we rename `roth_legacy_*` → `roth_bequest_*` (Phase G), wellness-to-healthcare is already done, reducing collision risk

**Implementation:**
- Migrator renames 11 keys during Phase C:
  - Wellness premiums: `pre_65_wellness_premium` → `pre_65_healthcare_premium`, `wellness_premium` → `healthcare_premium` (8 total)
  - OOP caps: `wellness_oop_cap_*` → `healthcare_oop_cap_*` (3 total)
- Updated CSV column headers reflect new names
- Post-migration: Phase E UI sweep changes only `dashboard.js` labels from "Wellness" → "Healthcare"

---

## Decision 3: Backup Retention Policy

**Question:** All backups (A), last 5 (B), or last 1 (C)?

**Decision: OPTION B — Retain last 5 pre-migration backups**

**Rationale:**
- **Audit trail:** 5 backups span ~5 app sessions, enough to recover from user error
- **Disk balance:** Modern SSDs can handle 5 × ~100KB CSVs easily; won't bloat git
- **Recovery window:** User who notices corruption within 5 sessions can revert
- **Cleanup burden:** Manual cleanup needed for >5; automatic purge is safe here

**Implementation:**
- File naming: `client_data.csv.pre_migration_<YYYYMMDD_HHMMSS>`
- Location: `local_state/` (never synced, survives app restarts)
- Purge logic: On each migration, list all `.pre_migration_*` files, delete oldest beyond 5
- User-facing: "Backup created: `client_data.csv.pre_migration_20260707_143022`" in app log

**Example retention:**
```
local_state/
  client_data.csv.pre_migration_20260701_090000  ← deleted (6th oldest)
  client_data.csv.pre_migration_20260702_140000
  client_data.csv.pre_migration_20260703_120000
  client_data.csv.pre_migration_20260704_150000
  client_data.csv.pre_migration_20260705_110000
  client_data.csv.pre_migration_20260706_160000
  client_data.csv.pre_migration_20260707_140000  ← newest
```

---

## Decision 4: Error Handling

**Question:** Fail explicitly (A), auto-rollback (B), or skip (C)?

**Decision: OPTION A — Fail explicitly with rollback offered**

**Rationale:**
- **Data integrity > convenience:** If migration fails, user must consent to recovery
- **Visibility:** User sees the error, not a silent fallback
- **Audit trail:** Failed migration logged so support can investigate
- **No data loss:** Backup exists; user can rollback or seek help

**Implementation:**
```python
try:
    migrated_data = run_migrator(plan_data)
except MigrationError as e:
    return {
        "success": False,
        "error": str(e),
        "backup_path": f"local_state/client_data.csv.pre_migration_{timestamp}",
        "offer_rollback": True
    }
```

**User flow:**
1. App detects old schema on load
2. Attempts migration
3. If error occurs:
   - App shows modal: "Migration failed. Backup saved to: [path]. Rollback to backup or contact support."
   - User can click "Restore from backup" → loads pre-migration data
   - Alternatively, user can exit and report the error

**Acceptance criteria:** No plan is silently loaded with partially-migrated data.

---

## Decision 5: Purge Window

**Question:** 2 releases (B), 6 months (C), or never (A)?

**Decision: OPTION B — 2 stable releases, with deprecation warning in v10.1**

**Rationale:**
- **Incentivizes upgrade:** Users who haven't upgraded by v10.2 are outliers; keeping pre-v10.0 support 2+ releases is generous
- **Maintainability:** The migrator is valuable for 2 releases (handles all incoming v9.x plans); after that, maintenance cost outweighs benefit
- **Deprecation signal:** v10.1 warns "Migrator will be deleted in v10.2; save a backup now if using plans from v9.x"
- **Beware: v10.2 ships, pre-v10.0 files can't load without manual migrator re-installation**

**Timeline:**
- **v10.0 (now):** Phase C launches; migrator available, data migrated
- **v10.1 (1 month):** Deprecation warning added; migrator still active
- **v10.2 (2 months):** Migrator deleted, only v10.0+ files load
- **v10.3+:** Only version-N-1 → N support kept (v10.1 → v10.2, etc.)

**Documentation:** `CLAUDE.md` updated with: "Migrator was deleted in v10.2. Pre-v10.0 plans require manual re-migration via tools/migrate_plan_data.py (archived in git tags/v10.1)."

---

## Decision 6: Migrator Testing Approach

**Question:** Test each legacy format separately or just end-to-end smoke test?

**Decision: HYBRID — Smoke test all paths + targeted unit tests for 2 highest-risk shims**

**Rationale:**
- **Risk: shims 1 & 7** (spending model changes) are most likely to silently corrupt data
- **Shim coverage:** Existing test fixtures likely cover most formats (Phase A tests data_io edge cases)
- **Cost: time vs benefit** — separate fixtures for each shim → 9 fixtures (expensive) vs smoke test all at once (cheap)

**Implementation:**
1. **End-to-end smoke test:**
   - Create a synthetic "v9.x plan" by removing `plan_metadata.json` (triggers migrator)
   - Run migrator, verify output format matches v10.0 canonical
   - Run golden-master test on migrated plan: `pytest tests/test_2_recommendations.py --tb=short`
   - Verify numbers match within tolerance (2.0 delta for net worth)

2. **Targeted unit tests for high-risk shims:**
   - **Shim 1 (legacy spending rows):** Create a plan without `client_spending_budget_lines.csv`, verify `extra_N` rows are migrated to budget-lines format
   - **Shim 7 (legacy tracking map):** Create a plan with old `_LEGACY_TRACKING_MAP` keys, verify they're renamed to unified model
   - Run these 2 unit tests in isolation: `pytest tests/test_legacy_spending_migration.py tests/test_legacy_tracking_migration.py`

3. **Regression check:**
   - After migration, grep for legacy aliases: `grep -r "wellness" src/` should return 0 in data_io/spending_tracker (passes)

---

## Implementation Guidance for Opus 4.8

### Priority order (do in this sequence):

1. **Design phase (Opus, 1 day):**
   - Write migrator pseudocode with error paths
   - Map which shim serves which field in canonical output
   - Define `plan_metadata.json` schema

2. **Implementation phase (Opus, 1.5 days):**
   - Implement `tools/migrate_plan_data.py` following decisions above
   - Test on fixtures (smoke + 2 unit tests)
   - Migrate all files: `input/`, `saved_plans/`, `tests/fixtures/`

3. **Cleanup phase (Opus, 0.5 days):**
   - Delete shims 1–9 from source
   - Add deprecation warning (v10.1 prep)
   - Regenerate `plan_data_manifest`, golden-master fixtures

4. **Review phase (Fable, 0.5 days):**
   - Verify golden-master byte-diff: `pytest tests/test_2_recommendations.py --tb=short -v`
   - Spot-check migrated plan files (3–5 samples)
   - Approve or request fixes before merge

### Mandatory gates:

- Golden-master test passes: `pytest tests/test_2_recommendations.py --tb=short`
- All tests pass: `pytest tests/ --tb=short -q`
- Regression check: `grep -riE 'legacy|backward|deprecated' src/ frontend/js/` (should match only bequest-domain + migrator)
- Manual smoke test: Load a saved plan from `saved_plans/`, verify load succeeds and numbers match expected

---

## Sequencing Notes

- **Phase B must complete first** (test modernization removes string-matching tests that would break on data-structure changes)
- **Phase D's data_io/spending_tracker splits follow Phase C** (smaller modules after shim removal)
- **Phase E's wellness UI sweep follows Phase C** (can rename UI labels after data is canonical)
- **All other phases independent** (Phase A hygiene, Phase F enhancements can proceed in parallel)

---

## Approval

✅ **APPROVED for implementation by Opus 4.8**

All 6 decisions are documented. Opus 4.8 has clear requirements:

1. Schema versioning: Separate `plan_metadata.json`
2. Wellness scope: Migrate data keys in Phase C (not Phase E)
3. Backup policy: Last 5 backups in `local_state/`
4. Error handling: Explicit failure with rollback option
5. Purge window: 2 releases (v10.0 → v10.1 → delete in v10.2)
6. Testing: Smoke test + 2 unit tests for high-risk shims

**Next:** Opus 4.8 designs detailed implementation, then executes Phase C.

---

Generated by Claude Fable 5

