# API Contracts

Generated: 2026-06-29 (partially updated 2026-09-30)

Scope note: this document covers the high-value contracts only. The authoritative list of every registered route is `src/server/route_manifest.py` (served at `/api/contracts`), which `tests/test_api_contracts_and_route_manifest_contract.py` keeps equal to the registered routes.

This document captures the stable local API contracts used by the v10 desktop UI. Routes remain under `/api/...`; schema names are carried in payloads instead of URL prefixes.

## Contract Rules

- All JSON endpoints return `success: true` on normal success unless documented otherwise.
- Write endpoints may return `403` when local runtime permissions disable the operation.
- Build/report contracts are versioned with explicit `schema` fields.
- The plan file (`plan.rpx`, `plan_rows`) is the runtime source of truth for the sectioned plan data; no CSV, JSON or YAML file mirrors it (WP4.5). The CSV endpoints that remain are adapters for the flat datasets (holdings, liabilities, spending, YTD) until WP6.
- Existing route names remain stable while newer contracts are added beside them.

## `/api/config/rows`

Purpose: canonical editable Plan Data rows for the guided UI.

Methods:
- `GET`: returns the active plan's rows (`plan_rows`, WP4.3).
- `POST`: writes row-value updates by `row_index` in one transaction.

GET response fields:
- `success`: boolean.
- `version`: app version string.
- `active_backend`: backend label, normally `SQLITE`.
- `rows`: row objects in plan display order with `row_index`, `section`, `subsection`, `label`, `value`, `units`, `notes`, `schema`, `choice_options` and `group`. `row_index` is the plan row's id: stable while the row exists, never reused.
- `revision`: the plan's content revision (`PlanStore.revision()`).

POST request:

```json
{
  "updates": [
    {"row_index": 12, "value": "2028"}
  ]
}
```

POST response:
- `success`: boolean.
- `updated`: count of written rows.
- `skipped`: skipped update records with reasons (an unknown or stale `row_index`).
- `revision`: the plan's revision after the save.

Validation:
- Invalid `updates` shape returns `400`.
- Plan Data validation failures return `422` with `errors`; no update is written.

GET also carries the Plan Features tier data (WP5.1):
- `plan_profile`: `{tier, tier_stored, customized, label, differing}` from `module_catalog.plan_profile` (no tier row reads as `expert` with `tier_stored: false`; `differing` lists the switch keys whose stored state differs from the tier's preset; `label` is e.g. `Advanced (customized)`).
- `tier_presets`: `{default, switchable, tiers: [{key, label, description, features}]}`, smallest tier first; `features` are the switch keys the tier turns on (cumulative).

## `/api/plan/tier`

Purpose: pick the plan's tier (WP5.1). Schema `plan_tier_v1`.

POST request: `{"tier": "standard", "preview": true}`. `tier` is one of `simple`, `standard`, `advanced`, `expert`; `preview` (default false) makes it a dry run that writes nothing (needs only `read_config`).

Response (both modes): `success`, `preview`, `tier`, `label`, `turn_on` (`[{key, name}]`), `turn_off` (`[{key, name, entered_rows, engine_participation}]`; `entered_rows` is null when the catalog declares no data section for the feature), `engine_ignored` (`[{key, name}]`, the engine-participating features turning off), `unchanged`. A preview adds `current` (the plan profile now); an apply adds `profile` (after) and `revision`. Applying writes `Plan Settings / Profile / plan_tier` and every switch that differs from the preset in one edit transaction; entered data is kept. Audit event `plan_tier_applied`.

Validation: an unknown tier or a non-boolean `preview` returns `400`; nothing is written.

## `/api/plan/feature`

Purpose: override one feature switch (`module_catalog.set_feature`), e.g. a page switch that has no row yet. Schema `plan_feature_v1`.

POST request: `{"key": "planning_workbench", "on": false}`. Response: `success`, `key`, `on`, `profile` (after), `revision`. An unknown key, a feature with no switch of its own, or a non-boolean `on` returns `400`. Audit event `plan_feature_set`.

## `/api/plan/interview`

Purpose: the plan interview (WP5.3). `GET` returns `{success, questions: [{id, text, kind, options?}]}` (`kind` is `choice` for the first question, `yes_no` for the rest). Schemas `plan_interview_questions_v1`, `plan_interview_v1`.

POST request: `{"answers": {"detail": "standard", "heloc": true}, "apply": false}`. `detail` (a tier key) is required; the yes/no answers are optional booleans. Response: `success`, `applied`, `tier`, `label`, `extra_on` (switch keys the answers turn on beyond the tier preset, so a non-empty list makes the plan customized), `reasons` (`[{key, name, question}]`), `change` (the same shape as `/api/plan/tier`), and when applied `profile` and `revision`. Applying writes the tier preset and the extras in one edit transaction; entered data is kept. A missing or unknown answer, or a non-boolean `apply`, returns `400`. Audit event `plan_interview_applied`.

`GET /api/config/rows` also carries `feature_suggestions`: `[{key, name, entered_rows, text}]`, the off features that hold entered data (`text` reads "Turn on HELOC? You have 3 rows entered for it."), and each row carries `min_tier` (WP5.2; empty for rows the field catalog does not list).

## Removed in WP4.5 (the CSV bridge)

- `POST /api/config/sync` and the `sync` request flag / response key of the save endpoints: there is nothing to sync, the plan rows are the only store (the `config_sync_v1` contract is gone).
- `GET/POST /api/csv` (the sectioned plan anchor as CSV text) and the plan kind of `/api/admin/csv-file/<kind>/<file>` (the system kind stays). A request for `client_data.csv`, a plan part file or a JSON/YAML mirror through `/api/plan-data/...` answers `410`; the flat dataset files keep their routes until WP6.
- `GET /api/config/backends` no longer reports `csv_path`, `json_path` or `yaml_path`; it reports `plan_path`.
- `/api/plan/save-as`, `/api/plan/load-file`, `/api/plan/exit-snapshot`, `/api/plan/snapshot/*`, the demo routes and Start New Plan work on the plan file (`plan.rpx`). A `.rpx` that is not a plan file (for example an older Save As of the legacy database) is refused by Load with a validation error and the active plan is untouched.

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

## `/api/plan/monarch-autoupdate`

Purpose: opt-in daily Monarch Extractor transaction auto-import status (ticket 305).

Method:
- `GET`.

Schema:
- `monarch_autoupdate_v1`.

Response:
- `success` (implied by HTTP 200), `schema`: `monarch_autoupdate_v1`.
- `policy`: `enabled`, `source_dir`, `field_map_path`.
- `status`: the most recent run's `monarch_autoupdate_status_v1` payload (`last_run_at`, `success`, `files_consumed`, `rows_added`, `rows_updated`, `rows_skipped`, `errors`), or `null` if it has never run.

Related routes:
- `POST /api/plan/monarch-autoupdate/config`: update the policy; also best-effort registers/unregisters the OS-level Windows Task Scheduler entry (`task_registration` in the response — `{attempted, success, error}`; a failure here does not undo the saved policy).
- `POST /api/plan/monarch-autoupdate/run`: run the import now (`force: true` by default, bypassing the enabled check). Response includes `mark_delivered_errors` (see below).

Guardrails:
- Import is opt-in; the actual 4am trigger is an OS-level Task Scheduler entry, not an in-process timer (the app has no always-on background process).
- Upserts by a stored Monarch id (`upsert_transactions_by_monarch_id` in `src/ytd_tracking.py`): replaces a changed transaction, adds a new one, no-ops an unchanged one. A row with no Monarch id falls back to the pre-existing hash-based dedup.
- The headless job (`tools/monarch_autoimport.py` / `src/monarch_autoimport_job.py`) guards against OneDrive placeholder/truncated source files before reading, and mirrors the written CSVs into the SQLite plan-data store since it runs with no Flask request context.
- Reads only `new_transactions.csv` and `changed_transactions.csv` from the Monarch Extractor's output folder (never `transactions.csv`, its full history, or `duplicates_removed.csv`) — confirmed 2026-09-02 against the real `Monarch Extractor/monarch_extract.py`. Those two files hold every still-pending event across every past extractor run, each tagged with a `run_id`; after a successful upsert, the job runs `python monarch_extract.py --mark-delivered <run_id>` (via the extractor's own `.venv`, since it imports Playwright unconditionally) for every distinct `run_id` it just imported, so that run's rows stop reappearing. This is best-effort: a failure is reported in `mark_delivered_errors` but does not fail the (already-committed) import — an unmarked run just means the same, already-upserted rows harmlessly reappear next cycle.

## `/api/plan/exit-snapshot`

Purpose: local database restore point on app exit.

Method:
- `POST`.

Response:
- `success`: boolean.
- `snapshot`: created legacy-database file name when that database exists.
- `plan_snapshot`: created plan-file name when the plan file exists.
- `message`: informational message when no database exists.

Side effects:
- Runs SQLite WAL checkpoint when possible.
- Copies `local_state/retirement_system_v10.db` to `retirement_system_v10.db.version_<YYYYMMDD_HHMMSS>` and the plan file to `plan.rpx.version_<YYYYMMDD_HHMMSS>` (`plan_snapshot` in the response).
- Keeps the latest 10 of each.

## `/api/plan/snapshot/compare`

Purpose: compare the active plan file to the plan-file copy captured in a build snapshot (`plan_database_snapshot.rpx`).

- `GET`: compares against the latest build snapshot stored in the plan file.
- `GET`: compares against `output/build_snapshot.json`.
- `POST`: accepts optional `build_id` to compare a specific build snapshot (default: the latest build in the plan file).

Response:
- `success`: boolean.
- `schema`: `plan_snapshot_compare_v1`.
- `snapshot_schema`: source build snapshot schema.
- `snapshot_build_id`.
- `snapshot_database`.
- `current_database`.
- `database_matches`: whether the current database hash equals the snapshot database hash.
- `hashes_available`: whether both hashes were available.
- `build_id`.

Failure:
- Returns `404` when the build snapshot is missing or invalid.

## `/api/plan/snapshot/restore`

Purpose: restore the active plan file from the plan-file copy captured in a build snapshot (validated as a plan file first).

Method:
- `POST`.

Request:
- `build_id`: optional; the build whose snapshot to restore (default: the latest build in the plan file).
- `backup_suffix`: optional deterministic suffix for the pre-restore backup name.

Response:
- `success`: boolean.
- `schema`: `plan_snapshot_restore_v1`.
- `restored_from`: build snapshot path.
- `restored_database`: snapshot-side SQLite database copy.
- `active_database`: replaced active plan file path.
- `backup_database`: pre-restore backup path (`plan.rpx.before_snapshot_restore_<ts>`) written before replacement.
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
    "lcv": 3100000,
    "eltr": 0.18,
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

### `/api/xlsx`

Method:
- `GET`.

Behavior:
- There is no `/api/pdf` route; the PDF report route was removed and only the workbook download exists.
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
- `/api/capital-market/assumptions`, `/api/capital-market/correlations` and `/api/capital-market/real-loss-curves` (plan override rows: body `{"rows": [...]}`, validated; `400` without rows or with invalid rows (`errors`), `410` for a CSV body)
- `/api/housing/seed`
- `/api/wellness/seed` route for healthcare OOP seed rows

Ownership:
- HTTP permissions, CSV-write gating, request extraction, and JSON serialization remain in `plan_routes.py`.
- Row normalization, validation, seed row definitions, override-row validation and storage, and audit payload composition live in `strategy_asset_service.py`.

Representative typed contracts are also exposed by `/api/contracts` using the `large_discretionary_expenses_v1`, `forced_roth_conversions_v1`, `liquidity_buffers_v1`, `insurance_policy_add_v1`, and `insurance_policy_delete_v1` schemas.

