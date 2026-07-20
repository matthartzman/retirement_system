# API Contracts

Generated: 2026-06-29

This document captures the stable local API contracts used by the v10 desktop UI. Routes remain under `/api/...`; schema names are carried in payloads instead of URL prefixes.

## Contract Rules

- All JSON endpoints return `success: true` on normal success unless documented otherwise.
- Write endpoints may return `403` when local runtime permissions disable the operation.
- Build/report contracts are versioned with explicit `schema` fields.
- The saved SQLite-backed working copy is the runtime source of truth. CSV endpoints are import/export or large-table adapters.
- Existing route names remain stable while newer contracts are added beside them.

## `/api/config/rows`

Purpose: canonical editable Plan Data rows for the guided UI.

Methods:
- `GET`: returns the current saved working-copy rows.
- `POST`: writes row-value updates by `row_index`.

GET response fields:
- `success`: boolean.
- `version`: app version string.
- `active_backend`: backend label, normally `SQLITE`.
- `csv_path`: configured CSV adapter path.
- `rows`: ordered row objects with `row_index`, `section`, `subsection`, `label`, `value`, `units`, `notes`, schema metadata, and source-file metadata.

POST request:

```json
{
  "updates": [
    {"row_index": 12, "value": "2028"}
  ],
  "sync": false
}
```

POST response:
- `success`: boolean.
- `updated`: count of written rows.
- `skipped`: skipped update records with reasons.
- `sync`: optional backend-sync result when requested.

Validation:
- Invalid `updates` shape returns `400`.
- Plan Data validation failures return `422` with `errors`.

## `/api/spending/model`

Purpose: canonical spending model read contract for category hierarchy, budgets, actuals, mapping state, and dashboard summaries.

Method:
- `GET`.

Query:
- `year`: optional integer year filter.

Response:
- Spending model object from `src.spending_tracker.spending_model`.
- Expected top-level fields include success/status fields, taxonomy/category structures, budget data, YTD actual summaries, mapping state, and recommendation/context fields as available.

Compatibility:
- Category, alias, mapping, and budget write routes remain separate. This endpoint is the read model used by the Spending pages.

## `/api/ytd/transactions`

Purpose: canonical transaction editing surface for current-year income/expense actuals.

Methods:
- `POST`: append one normalized transaction.
- `DELETE`: clear all transactions while preserving account setup.
- `PUT /api/ytd/transactions/<index>`: update one transaction.
- `DELETE /api/ytd/transactions/<index>`: delete one transaction.
- `PUT /api/ytd/transactions/bulk`: replace transaction list.
- `POST /api/ytd/transactions/upload`: import CSV text using `replace`, `add`, or dedupe-style modes.
- `GET /api/ytd/transactions/template`: returns CSV template text.

Transaction write response fields:
- `success`: boolean.
- `total`: transaction count when applicable.
- `index`: updated/deleted index when applicable.
- `summary`: recalculated YTD summary.

Side effects:
- Normalizes transaction rows.
- Ensures account setup rows for transaction accounts.
- Mirrors YTD CSV files into the SQLite client-file store.

## `/api/ytd/transactions/preview`

Purpose: side-effect-free transaction import preview.

Method:
- `POST`.

Schema:
- `import_preview_v1`.

Response:
- `success`: boolean.
- `schema`: `import_preview_v1`.
- `row_count`.
- `warnings`.
- `will_write`: false for preview responses; callers must confirm and then use the write route.
- Duplicate and unmapped-category diagnostics when available.

## `/api/holdings`

Purpose: canonical holdings CSV adapter for lot-level investment holdings.

Methods:
- `GET`: returns `text/csv`.
- `POST`: accepts raw CSV request body.

GET behavior:
- Returns workspace `client_holdings.csv` when present.
- Falls back to SQLite client-file content.
- Returns a header-only holdings CSV when no holdings file exists.

POST response:
- `success`: boolean.
- `path`: workspace CSV path written.

Side effects:
- Writes workspace holdings CSV.
- Mirrors content into the SQLite client-file store.

## `/api/holdings/preview`

Purpose: side-effect-free holdings CSV replacement preview.

Method:
- `POST`.

Schema:
- `import_preview_v1`.

Response:
- `success`: boolean.
- `schema`: `import_preview_v1`.
- `row_count`.
- `warnings`.
- `will_write`: false for preview responses; callers must confirm and then use the holdings write route.

## `/api/build/preflight`

Purpose: side-effect-free readiness/freshness contract before build.

Method:
- `GET`.

Response schema:
- `schema`: `build_preflight_v1`.
- `source`: `sqlite_snapshot`.
- `current`: whether essential outputs exist and are not older than saved plan data.
- `readiness`: `current`, `ready`, `warning`, or `blocked`.
- `blockers`, `warnings`, `recommendations`.
- `missing_required`, `missing_required_count`.
- `schema_errors`, `schema_error_count`.
- `row_count`.
- `db`: database file metadata.
- `artifacts`: workbook/PDF/dashboard/results/summary/snapshot/pricing metadata.
- `summary`: parsed `plan_summary.json` when available.
- `snapshot`: parsed `build_snapshot_v1` when available.
- `snapshot_schema`.
- `output_fingerprints`.
- `pricing_status`: `ok`, `warning`, `fallback`, or `unknown`.
- `pricing_mode`: configured pricing mode from diagnostics when available.

## Pricing Snapshot Freeze Contracts

Purpose: freeze the latest saved market-price snapshots so advisor report builds remain reproducible after market prices change.

Routes:
- `POST /api/prices/freeze`
- `POST /api/prices/unfreeze`
- `POST /api/prices/refresh`
- `GET /api/prices/snapshots`

Freeze response schema:
- `schema`: `pricing_snapshot_freeze_v1`.
- `success`: boolean.
- `active`: boolean.
- `workspace_id`.
- `frozen_at`.
- `source`.
- `symbol_count`.
- `symbols`: per-symbol frozen price records.

Build behavior:
- Active freeze data is applied as `FROZEN` market-pricing mode.
- Frozen symbols are reported as `frozen_snapshot`.
- Frozen pricing does not call live providers during the build.

## `/api/build/start`

Purpose: asynchronous build orchestration with in-memory progress telemetry.

Method:
- `POST`.

Request:

```json
{
  "queue": false,
  "ui_saved_working_copy": true,
  "build_input_source": "sqlite_snapshot"
}
```

Initial response:
- `success`: boolean.
- `job_id`: in-memory job id.
- `status`: job status.
- `phase`, `detail`, `progress`.

Follow-up routes:
- `GET /api/build/progress/<job_id>` returns the current job snapshot.
- `GET /api/build/events/<job_id>` streams server-sent events.
- `GET /api/build/events/<job_id>/snapshot` returns accumulated events.

Compatibility:
- `POST /api/build` remains the synchronous fallback and rejects direct CSV plan payloads.

## `/api/detailed-results`

Purpose: canonical in-app detailed report reader.

Method:
- `GET`.

Query modes:
- `?index=1`: return workbook/results index.
- `?sheet=<name>`: return one sheet/page.
- No query: return complete detailed-results payload.

Response:
- `success`: boolean.
- `schema`: `results_model_v10` when served from the semantic Results Explorer sidecar; Excel fallback payloads include compatible sheet/category structures.
- `categories`: grouped page/sheet metadata.
- `sheets` or `sheet`: detailed data, charts, sections, rows, and cells depending on query mode.

Failure:
- Returns `404` when report artifacts are missing.
- Returns `500` with `success: false` and `error` when parsing fails.

## `/api/report-package`

Purpose: canonical advisor report package manifest.

Method:
- `GET`.

Schema:
- `report_package_v1`.

Response:
- `success`: boolean indicating whether required package artifacts exist.
- `schema`: `report_package_v1`.
- `build_id`: build identifier shared with `plan_summary.json` and `build_snapshot.json` when available.
- `contracts`: component schema names, including `results_model_v10` and `build_snapshot_v1`.
- `artifacts`: workbook, PDF, dashboard, Results Explorer model, summary, snapshot, and pricing artifact metadata with hashes when files exist.
- `components`: concise component summaries for the semantic results model and build snapshot.
- `summary`: copied KPI summary from `plan_summary.json`.

Failure:
- Returns `404` when `report_package.json` is missing or not a valid `report_package_v1` file.

Build behavior:
- Successful builds write `output/report_package.json` after the Results Explorer model, plan summary, and build snapshot are produced.
- The package treats Excel/PDF/HTML as renderers of the advisor report bundle, while `results_model_v10` remains the canonical semantic report model.

## `/api/plan/backups`

Purpose: opt-in local backup scheduler status.

Method:
- `GET`.

Schema:
- `local_backup_scheduler_v1`.

Response:
- `success`: boolean.
- `schema`: `local_backup_scheduler_v1`.
- `policy`: enabled/cadence/retention settings.
- `backup_count`, `latest_backup`, `due`, and `due_reason`.
- `backup_dir` and `source_db`.

Related routes:
- `POST /api/plan/backups/config`: update policy settings.
- `POST /api/plan/backups/run`: run a manual or opportunistic backup.

Guardrails:
- Backups are opt-in unless `force: true` is provided for manual backup.
- Retention pruning is capped by policy.
- Backup files are `.rpx` SQLite copies with JSON manifests.

## `/api/plan/exit-snapshot`

Purpose: local database restore point on app exit.

Method:
- `POST`.

Response:
- `success`: boolean.
- `snapshot`: created file name when a database exists.
- `message`: informational message when no database exists.

Side effects:
- Runs SQLite WAL checkpoint when possible.
- Copies `local_state/retirement_system_v10.db` to `retirement_system_v10.db.version_<YYYYMMDD_HHMMSS>`.
- Keeps the latest 10 version snapshots.

## `/api/plan/snapshot/compare`

Purpose: compare the current local SQLite database to the database copy captured in a build snapshot.

Methods:
- `GET`: compares against `output/build_snapshot.json`.
- `POST`: accepts optional `snapshot_path` to compare a specific build snapshot.

Response:
- `success`: boolean.
- `schema`: `plan_snapshot_compare_v1`.
- `snapshot_schema`: source build snapshot schema.
- `snapshot_build_id`.
- `snapshot_database`.
- `current_database`.
- `database_matches`: whether the current database hash equals the snapshot database hash.
- `hashes_available`: whether both hashes were available.
- `snapshot_path`.

Failure:
- Returns `404` when the build snapshot is missing or invalid.

## `/api/plan/snapshot/restore`

Purpose: restore the active local SQLite database from the database copy captured in a build snapshot.

Method:
- `POST`.

Request:
- `snapshot_path`: optional path to a specific `build_snapshot.json`; defaults to `output/build_snapshot.json`.
- `backup_suffix`: optional deterministic suffix for the pre-restore backup name.

Response:
- `success`: boolean.
- `schema`: `plan_snapshot_restore_v1`.
- `restored_from`: build snapshot path.
- `restored_database`: snapshot-side SQLite database copy.
- `active_database`: replaced active SQLite database path.
- `backup_database`: pre-restore backup path written before replacement.
- `sha256`: restored database hash.

Guardrails:
- Validates the snapshot database hash before replacement.
- Writes a backup of the current active database before copying the snapshot database into place.
- Returns `400` if the snapshot or its database copy is missing or invalid.

## Related Snapshot Contract

Successful builds also write `output/build_snapshot.json`.

Schema:
- `build_snapshot_v1`.

Stable fields:
- `version`, `build_id`, `generated_at`, `source`.
- `input_fingerprint`.
- `system_config`.
- `pricing_diagnostics`.
- `artifacts`.
- `summary`.
- `environment`.

Snapshot compare and restore helpers use the build snapshot database copy.

Schemas:
- `plan_snapshot_compare_v1`.
- `plan_snapshot_restore_v1`.

Stable restore response fields:
- `success`: boolean.
- `schema`: `plan_snapshot_restore_v1`.
- `restored_database`: snapshot-side SQLite database copy.
- `active_database`: replaced active SQLite database path.
- `backup_database`: pre-restore backup path written before replacement.
- `restored_from`: build snapshot used for restore.
- `sha256`: restored database hash.

Guardrails:
- Restore validates the snapshot-side SQLite database hash before replacement.
- Restore writes a backup of the current database before copying the snapshot database into place.
- UI callers should reload Plan Data and rebuild outputs after a restore.

## `/api/admin/system-config`

Purpose: Advanced Maintenance System Configuration batch-edit support.

Methods:
- `GET`: returns current `system_config.csv` rows and raw CSV text.
- `POST`: writes confirmed row updates or replacement CSV content.

Schemas:
- `system_config_rows_v1`.
- `system_config_rows_update_v1`.

Guardrails:
- The user UI previews broad edits before posting.
- Batch tools require an explicit field filter before previewing broad System Configuration changes.
- Writes update `system_config.csv` immediately after confirmation.


## `planning_case_v1` Browser-Local Contract

`planning_case_v1` is stored in browser local storage under `retirement.planning_case_v1` and is intentionally not a server-side saved-plan mutation.

```json
{
  "schema": "planning_case_v1",
  "case_id": "case_example",
  "name": "Retire later bridge",
  "base_snapshot_id": "latest_saved_baseline",
  "source": "strategy|scenario|stress|manual",
  "overrides": [
    {
      "sourceStep": "scenarios",
      "sourceTitle": "Scenario Change Sets",
      "field": "retirement_year",
      "before": "2027",
      "after": "2029",
      "rationale": "Test bridge years before adopting the assumption."
    }
  ],
  "run_type": "quick_compare|full_build|stress_suite",
  "result_summary": {
    "success_probability": 0.86,
    "terminal_nw": 2400000,
    "lifetime_tax": 720000,
    "roth_conversion_total": 180000
  },
  "created_at": "2026-06-26T00:00:00Z"
}
```

Guardrail: a planning case may be adopted only by opening source pages, editing inputs, saving, and rebuilding. The contract itself never writes Plan Data.

## Report Artifact and Build History Service Contracts

The report-output routes remain URL-compatible, but route handlers now delegate path resolution and history persistence to `src/server_services/report_service.py`.

### `/api/history`

Methods:
- `GET`: returns the local build-history array stored in `output/run_history.json`; returns an empty array if no history exists or the file cannot be parsed.
- `POST`: appends the request JSON body as one history entry, retention-trims to the latest 50 entries, and returns `{ success, count, path }`.

### `/api/xlsx` and `/api/pdf`

Method:
- `GET`.

Behavior:
- Resolves the requested artifact from the active workspace output directory.
- Falls back to the package `output/` directory for non-local workspace portability.
- Returns a file download when present or `404` with a build-first message when missing.

### `/files/<path:filename>`

Method:
- `GET`.

Behavior:
- Serves only files below the active local output directory.
- Rejects path traversal with `403`.
- Returns `404` for missing files.

Ownership:
- HTTP permissions, response streaming, and audit events remain in `workbook_routes.py`.
- Artifact selection, history read/write, and path safety checks live in `report_service.py`.

## Strategy/Asset Service Contracts

The strategy/assets routes remain URL-compatible, but route handlers now delegate request-independent validation and Plan Data row manipulation to `src/server_services/strategy_asset_service.py`.

Service-owned route families:
- `/api/large-discretionary-expenses`
- `/api/forced-roth-conversions`
- `/api/liquidity-buffers`
- `/api/other-asset/add` and `/api/other-asset/delete`
- `/api/education-529/add`
- `/api/estate-state-options` and `/api/estate-state/add`
- `/api/trust-account/add`
- `/api/insurance-policy/add` and `/api/insurance-policy/delete`
- `/api/capital-market/assumptions` and `/api/capital-market/correlations`
- `/api/housing/seed`
- `/api/wellness/seed` route for healthcare OOP seed rows
- `/api/config/sync`

Ownership:
- HTTP permissions, CSV-write gating, request extraction, and JSON serialization remain in `plan_routes.py`.
- Row normalization, validation, seed row definitions, reference CSV writing, and audit payload composition live in `strategy_asset_service.py`.

Representative typed contracts are also exposed by `/api/contracts` using the `large_discretionary_expenses_v1`, `forced_roth_conversions_v1`, `liquidity_buffers_v1`, `insurance_policy_add_v1`, `insurance_policy_delete_v1`, and `config_sync_v1` schemas.

