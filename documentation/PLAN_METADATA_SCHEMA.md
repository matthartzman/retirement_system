# Plan Metadata Schema (v1.0)

**File:** `plan_metadata.json` (located in `input/` directory alongside plan CSV files)

**Purpose:** Records the canonical schema version of a plan and migration history, enabling the loader to detect and migrate old formats on-demand.

## Schema Definition

```json
{
  "schema_version": "1.0",
  "migration_timestamp": "2026-07-07T12:34:56Z",
  "format_description": "Unified budget lines, healthcare terminology, multi-note layout, canonical withdrawal window, purges applied",
  "migrated_from": "0.9",
  "backup_path": "local_state/client_data.csv.pre_migration_20260707_123456"
}
```

## Fields

| Field | Type | Required | Example | Description |
|---|---|---|---|---|
| `schema_version` | string | ✅ | `"1.0"` | Current schema version. Format: `MAJOR.MINOR`. Bumped when format changes; loader gates on this value. |
| `migration_timestamp` | string (RFC3339) | ✅ | `"2026-07-07T12:34:56Z"` | When migration was applied (UTC). Used for audit trail and backup identification. |
| `format_description` | string | ✅ | `"Unified budget lines, healthcare terminology..."` | Human-readable description of what format was applied. Helps users understand their plan's structure. |
| `migrated_from` | string | ✅ | `"0.9"` | Previous schema version (or "legacy" if pre-versioning). Documents migration path. |
| `backup_path` | string | ⚠️ | `"local_state/client_data.csv.pre_migration_..."` | Relative path to backup (from repo root). Helps users locate recovery files. Optional if migration was successful and no rollback is needed. |

## Backwards Compatibility

**If `plan_metadata.json` is absent:**
- Loader treats it as pre-v10.0 format (schema version < 1.0)
- Automatically invokes migrator
- Migrator creates the metadata file post-migration

**If `plan_metadata.json` exists but `schema_version` < 1.0:**
- Loader invokes migrator
- Migrator updates `schema_version` to 1.0

**If `plan_metadata.json` exists and `schema_version` == 1.0:**
- Loader proceeds normally (no migration needed)

## Loading Logic Flow

```python
# In data_io.py _read_plan_data_file():

def load_plan(plan_csv_path):
    metadata_path = plan_csv_path.parent / "plan_metadata.json"
    
    if not metadata_path.exists():
        # Pre-v10.0 format (no metadata)
        migrator = run_migrator(plan_csv_path)
        plan = load_canonical_format(plan_csv_path)
    else:
        metadata = json.load(metadata_path)
        if metadata.get("schema_version", "0.0") < "1.0":
            # Old version exists, run migrator
            migrator = run_migrator(plan_csv_path)
            plan = load_canonical_format(plan_csv_path)
        else:
            # Current version, load directly
            plan = load_canonical_format(plan_csv_path)
    
    return plan
```

## Version Numbering

| Version | Status | Introduced | Format Notes |
|---|---|---|---|
| < 1.0 | Deprecated | v9.x | Legacy format with shims 1–9 active. Requires migration. |
| 1.0 | Current | v10.0 | Canonical format: unified budget, healthcare terminology, multi-note layout. |
| 1.1+ | Future | v10.1+ | Reserved for future schema evolution. |

## Migration Timeline

| Release | Metadata Format | Behavior |
|---|---|---|
| **v9.x** | None (implicit v0.9) | Loader uses shims 1–9 transparently. No metadata. |
| **v10.0** | Migrator writes `plan_metadata.json` with v1.0 | Loader detects missing metadata, runs migrator, writes metadata. |
| **v10.1** | Metadata exists with v1.0 | Loader reads metadata, skips migration. Deprecation warning added. |
| **v10.2+** | Migrator code deprecated (kept for reference) | Loader gates on v1.0+; v0.9 files require manual re-migration. |

## Purge Window

- **v10.0–v10.1:** Migrator actively invoked on first load of old files. Backups kept (last 5 in `local_state/`).
- **v10.2:** Migrator code removed from normal load path. Users can still manually run `tools/migrate_plan_data.py` if needed.
- **v10.3+:** Only version-N-1 → N support maintained. Pre-v10.0 files unsupported.

## Example Metadata Files

### v10.0 migrated from v9.x

```json
{
  "schema_version": "1.0",
  "migration_timestamp": "2026-07-07T14:30:22Z",
  "format_description": "Unified budget lines, healthcare terminology, multi-note layout, canonical withdrawal window, purges applied",
  "migrated_from": "0.9",
  "backup_path": "local_state/client_data.csv.pre_migration_20260707_143022"
}
```

### v10.0 created fresh (no migration)

```json
{
  "schema_version": "1.0",
  "migration_timestamp": "2026-07-07T10:00:00Z",
  "format_description": "Canonical format",
  "migrated_from": "1.0",
  "backup_path": null
}
```

## Deprecation Path

When schema version changes in future (e.g., v1.1):

1. Loader supports both v1.0 and v1.1
2. New files written with v1.1
3. Old v1.0 files auto-migrated to v1.1 on next load (with backup)
4. After 2 releases, v1.0 support removed, migrator code archived

## Edge Cases

### Manually edited metadata (not recommended)

If a user manually edits `plan_metadata.json`:
- Loader validates schema_version field exists and is parseable
- If invalid, loader logs warning and treats file as pre-migration
- Migrator runs, overwrites metadata with fresh version

### Backup file deleted

If backup path specified in metadata but file missing:
- Loader logs warning but proceeds (backup wasn't critical)
- Future migration attempts will create new backup

### Multiple plans in one directory

Each plan CSV gets its own metadata file:
```
input/
  client_data.csv
  plan_metadata.json          ← for client_data.csv
  client_holdings.csv         ← no metadata (mirrors client_data structure)
  client_liabilities.csv      ← no metadata (mirrors client_data structure)
  client_spending_budget_lines.csv ← no metadata (mirrors client_data structure)
```

---

**See also:**
- `tools/migrate_plan_data.py` — migrator implementation
- `src/data_io.py` — loader that gates on metadata
- `documentation/PHASE_C_ARCHITECTURAL_DECISIONS.md` — design rationale

