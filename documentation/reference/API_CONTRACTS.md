# API Contracts

Generated: 2026-06-29 (partially updated 2026-09-30)

Scope note: this document covers the high-value contracts only. The authoritative list of every registered route is `src/server/route_manifest.py` (served at `/api/contracts`), which `tests/test_api_contracts_and_route_manifest_contract.py` keeps equal to the registered routes.

This document captures the stable local API contracts used by the v10 desktop UI. Routes remain under `/api/...`; schema names are carried in payloads instead of URL prefixes.

## Contract Rules

- All JSON endpoints return `success: true` on normal success unless documented otherwise.
- Write endpoints may return `403` when local runtime permissions disable the operation.
- Build/report contracts are versioned with explicit `schema` fields.
- The plan file (`plan.rpx`, `plan_rows`) is the runtime source of truth for the sectioned plan data; no CSV, JSON or YAML file mirrors it (WP4.5). CSV enters and leaves only through `csv_exchange`: `/api/import/*` and `/api/export/*` (WP9, below). The flat datasets (holdings, liabilities, spending, YTD) are plan-file tables (WP6); their feature endpoints (`/api/holdings`, `/api/spending/*`, `/api/ytd/*`) read and write those tables.
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

## `/api/rental/*`

Purpose: the Rental Properties page (WP12.6), reading and writing the typed rental tables through `store.rental`. Schemas `rental_properties_v1`, `rental_property_save_v1`.

- `GET /api/rental/properties?year=&magi=`: `success`, `enabled` (the feature switch), `count`, `max_properties`, `properties` (stored rows, the `parse_rental_properties` input shape with `improvements` and `overrides` lists), `table` (per property: `name`, `kind`, `value`, `annual_rent`, `operating_expenses`, `net_yield`, `sale_year`), `warnings` (`[{id, kind, level, title, text, property, action}]`: `double_count`, `passive_limit`, `section_121`), `summary` (`year`, `net_cash_flow`, `taxable_rental_income`, `suspended_loss`, `equity`; null when unavailable), `estimate` (`available`, `label`, `magi`, `years`, `notes`, `error`), `home` (the plan's home for Convert my home) and `field_tiers` (`min_tier` per field, `property`/`improvement`/`override`). The summary is an estimate from the stored properties with the projection's rental stage, not the last build; `magi` is the assumed other income for the passive-loss limit (default 0) and `year` defaults to the first projection year. It works while the feature is off (data kept, the page previews it).
- `GET /api/rental/property?name=`: `{success, property}`; `404` for an unknown name. `GET /api/rental/home`: `{success, home}`.
- `POST /api/rental/property`: `{property, original_name?}` adds the property or replaces the one named `original_name` (default: its own name) keeping its place. Unknown keys are dropped; the whole set is checked with `parse_rental_properties` (the build's check) and a bad property is refused with `400` and the parser's message. Audit event `rental_property_saved`.
- `POST /api/rental/property/duplicate` and `/delete`: `{name}`. A converted home cannot be duplicated (the plan has one home). Audit events `rental_property_duplicated`, `rental_property_deleted`.
- `POST /api/rental/improvements` `{name, improvements}` and `POST /api/rental/overrides` `{name, overrides}`: replace one property's capital improvements or per-year rent and expense overrides (same validation).

`GET /api/config/rows` also carries `rental_property_count` (WP12.6): the nav keeps the page, in its off state, while the feature is off but properties are stored.

## Removed in WP4.5 (the CSV bridge)

- `POST /api/config/sync` and the `sync` request flag / response key of the save endpoints: there is nothing to sync, the plan rows are the only store (the `config_sync_v1` contract is gone).
- `GET/POST /api/csv` (the sectioned plan anchor as CSV text) and the plan kind of `/api/admin/csv-file/<kind>/<file>` (the system kind stays). 
- `GET /api/config/backends` no longer reports `csv_path`, `json_path` or `yaml_path`; it reports `plan_path`.
- `/api/plan/save-as`, `/api/plan/load-file`, `/api/plan/exit-snapshot`, `/api/plan/snapshot/*`, the demo routes and Start New Plan work on the plan file (`plan.rpx`). A `.rpx` that is not a plan file (for example an older Save As of the legacy database) is refused by Load with a validation error and the active plan is untouched.

## Removed: `/api/plan-data/*` and `src/server/plan_data_files.py`

- `GET /api/plan-data/files`, `GET/POST /api/plan-data/<file>` are gone, with the file allowlists in `src/server/plan_data_files.py`. A dataset is addressed by `plan_datasets.DATASET_BY_FILE`; CSV import and export use the routes below.
- `POST /api/plan-data/blank` (Start New Plan) is now `POST /api/plan/blank` (body `{ytd_blend_enabled?}`; same behavior: backs up the plan file, blanks the household rows and the holdings, liabilities and HSA schedule tables).

## CSV import and export (WP9, `src/server/import_export_routes.py`)

- `POST /api/import/preview` (`read_config`): what an import would change; nothing is written.
- `POST /api/import/commit` (`write_config`, needs CSV writes enabled, else `403`): the same import in one transaction.
  - Body: `{"dataset": "<name>", "csv_text": "..."}` for one dataset; `{"files": {name: text}}` for a browser folder; `{"dataset": "plan-set", "zip_base64": "..."}` or a raw `application/zip` body for a plan-set zip.
  - `422` with `issues` when the import is rejected; `404` for an unknown dataset; `400` for a malformed body.
- `GET /api/export/<dataset>`: one dataset as CSV text (`404` for an unknown or import-only dataset).
- `GET /api/export/plan-set`: the whole plan set as a zip (`?format=files` returns `{files: {name: csv text}}` for a browser folder export).

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
- Writes the plan file's `ytd_*` tables (no CSV file and no client-file mirror).

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

Purpose: CSV-text adapter over the active plan's holdings table (`holdings_lots`) for lot-level investment holdings.

Methods:
- `GET`: returns `text/csv`.
- `POST`: accepts raw CSV request body (`403` unless CSV writes are enabled).

GET behavior:
- Renders the active plan's holdings table as CSV text.
- Returns a header-only holdings CSV when the table is empty.

POST response:
- `success`: boolean.
- `path`: always empty (kept for compatibility; no file is written).

Side effects:
- Replaces the active plan's holdings table in one transaction (audit event `holdings_saved`).
- Writes no CSV file and no client-file row.

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
- `db`: plan file metadata.
- `artifacts`: workbook/PDF/dashboard/results/summary/snapshot/pricing metadata.
- `summary`: the build's KPI summary (`build_results` row) when available.
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
- `build_id`: build identifier shared with the build's `build_results` row (summary and snapshot parts) when available.
- `contracts`: component schema names, including `results_model_v10` and `build_snapshot_v1`.
- `artifacts`: workbook, PDF, dashboard, Results Explorer model, summary, snapshot, and pricing artifact metadata with hashes when files exist.
- `components`: concise component summaries for the semantic results model and build snapshot.
- `summary`: copied KPI summary from the build's `build_results` row.

Failure:
- Returns `404` when `report_package.json` is missing or not a valid `report_package_v1` file.

Build behavior:
- Successful builds store the report package in the build's `build_results` row, after the Results Explorer model, KPI summary, and build snapshot are produced.
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
- Backup files are `.rpx` SQLite copies; their manifests are rows of `app.db` (`backup_manifest`), not files.

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
- The headless job (`tools/monarch_autoimport.py` / `src/monarch_autoimport_job.py`) guards against OneDrive placeholder/truncated source files before reading, and writes the plan file's `ytd_*` tables directly, since it runs with no Flask request context.
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
- `POST`: accepts optional `build_id` to compare a specific build snapshot (default: the latest build in the plan file).

Response:
- `success`: boolean.
- `schema`: `plan_snapshot_compare_v1`.
- `snapshot_schema`: source build snapshot schema.
- `snapshot_build_id`: the `build_results` row (`build_id`) the snapshot came from.
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
- `restored_from`: the `build_id` of the snapshot the restore used.
- `restored_database`: snapshot-side SQLite database copy.
- `active_database`: replaced active plan file path.
- `backup_database`: pre-restore backup path (`plan.rpx.before_snapshot_restore_<ts>`) written before replacement.
- `sha256`: restored database hash.

Guardrails:
- Validates the snapshot database hash before replacement.
- Writes a backup of the current active database before copying the snapshot database into place.
- Returns `400` if the snapshot or its database copy is missing or invalid.

## Related Snapshot Contract

Successful builds also store the snapshot in the build's `build_results` row (`snapshot_json`); the plan-file copy is `plan_database_snapshot.rpx`, beside the outputs.

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
- `active_database`: replaced active plan file path.
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
- `GET`: returns the system configuration rows (runtime settings from `app.db`, then the engine knobs from the active plan) and their raw CSV text for the editor.
- `POST`: writes confirmed row updates or replacement CSV content (`csv_content`). Runtime rows are saved to `app.db` settings; engine rows are saved to the active plan.

Schemas:
- `system_config_rows_v1`.
- `system_config_rows_update_v1`.

Guardrails:
- The user UI previews broad edits before posting.
- Batch tools require an explicit field filter before previewing broad System Configuration changes.
- Writes take effect after confirmation (audit event `admin_system_config_saved`). No `system_config.csv` file exists; the rows are not written to any file.


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
- `GET`: returns the local build-history array stored in `app.db` (`run_history`, one scope per output folder); returns an empty array if no history exists or the store cannot be read.
- `POST`: appends the request JSON body as one history entry, retention-trims to the latest 50 entries, and returns `{ success, count }`.

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


## `/api/reconcile`

Account reconciliation: the app's account numbers against Monarch's daily balances (imported into the plan file's `monarch_balances` table by the 04:00 job). Logic lives in `src/reconcile.py`; the routes are thin.

- `GET /api/reconcile?as_of=YYYY-MM-DD&tolerance=1`: comparison rows as of a Monarch date (default the latest). Response `{success, has_balances, as_of, latest, tolerance, dates, rows, unmatched, ignored, import, last_ok_import, app_targets}`. Each row has `id` (`setup:<account>`, `plan:home`, `plan:autos`, `plan:mortgage`), `label`, `group`, `app_value`, `monarch_value` (liabilities sign-flipped to the app's positive convention), `difference`, `status` (`match`, `differs`, `report_only`, `not_in_monarch`), `updatable`, `write` (what an update would change: `{kind, ref, field, old, new}`), `report_reason` and the matched `monarch_accounts`. `unmatched` lists Monarch accounts with no app match. `400` for a bad `as_of` or `tolerance`.
- `POST /api/reconcile/map`: body `{account_key, target}`; `target` is a row id, `ignore`, or empty to clear. Saves how a Monarch account matches an app number (several may map to one; their balances are summed). `400` for an unknown account or target.
- `POST /api/reconcile/preview`: body `{items: [{id}], as_of?}`. Returns `{changes, rejected}` (old to new for each row that would change) and writes nothing.
- `POST /api/reconcile/apply`: same body; each item may carry `expected_new` (the preview's number), and an item whose current number differs is rejected as stale. Returns `{applied: [{change_id, ...}], rejected}`; every change is logged. Investment accounts and income-stream annuities are report only and always rejected.
- `POST /api/reconcile/undo`: body `{change_id}`. Restores the old value only while the app still holds the number that change wrote; `400` otherwise or if already undone.
- `POST /api/reconcile/policy`: body `{account_key, policy}`; `policy` is `ask`, `auto` (copy Monarch's number at import, guarded), `app` (the app is the source, report only) or `ignore`. `400` for an unknown policy or an account with no saved match. Rows now also carry `policy` and `auto_hold` (why an `auto` change is waiting for you), and the response lists `closed_accounts` (closed and empty, nothing to decide) and `parked_accounts` (matched to something the page cannot update yet, policy app or ignore); a closed account that still holds money is in `unmatched` with status `closed_with_balance`.
- `POST /api/reconcile/undo-auto`: undoes every automatic change not yet undone; returns `{undone, skipped}` (a value edited since is skipped).
- `POST /api/reconcile/seed`: body `{csv_text}` (the Monarch-to-app mapping CSV). Saves matches and policies; returns `{seed: {saved, pending, ignored, not_in_monarch, skipped, kept}}`; a Monarch account that already has a saved match is left as it is (`kept`).
- `GET /api/reconcile/log`: `{log: [...]}`, newest first, each with `old_value`, `new_value`, `monarch_date` and `undone_at`.

Writes need the `write_config` permission; reads need `view_dashboard`.
