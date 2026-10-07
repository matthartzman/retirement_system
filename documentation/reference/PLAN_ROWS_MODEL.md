# Plan rows model (`plan.db` / `.rpx`)

Status: WP4.1 (owner review checkpoint; the row-model summary below is the PR-body text), WP4.2 read path, WP4.3 grid and forms write path.

## Row-model summary

**Tables.** plan.db schema v1 is unchanged; WP4.1 needs no migration.
- `plan_rows(row_id, section, subsection, label, value, units, notes, sort_order)`: every sectioned plan field, including settings and feature switches. `row_id` is stable and never reused (it becomes the grid's `row_index`).
- `plan_revisions` + `revision_rows` (snapshots, retention) and `plan_meta` (key/value facts such as conversion markers).

**Keys and order.**
- A field is addressed by `(section, subsection, label)`. A key is unique in a plan: the importer collapses a repeated key (the old CSV set has two such duplicates, the anchor's `Scenarios` copies) to ONE row, which keeps the first occurrence's position and takes the last occurrence's value, units and notes, as `load_csv` read it. A stale copy can therefore never come back after the effective row is edited or deleted. (`PlanStore.sectioned_data()` still reads "last row wins" for plans that hold a repeat from elsewhere.)
- Rows inside a section are ordered by `(sort_order, row_id)`, and sections by creation (lowest `row_id`). After an import this is the old CSV order.
- `PlanStore.sectioned_data()` is the engine view `{section: {subsection: {label: value}}}`. It uses the same rules and key order as `load_csv`, proven equal for `sample_frozen` and `demo` (dict, key order and `parse_client` output).
- Writes: `set_value(section, subsection, label, value)` updates the effective row or appends one. The grid uses `get_row` / `set_row` / `insert_row` / `delete_row` by `row_id`, plus `transaction()` and `revision()`.

**Import (`src/csv_exchange`, the one CSV reader from now on).**
- Reads the plan CSV set (`client_data.csv` plus 9 parts) in the old order into an empty plan, in one transaction. It returns a report: files read and missing, rows, comments attached and dropped, skipped records.
- Columns are found by header name, as the old `csv.DictReader` readers did: any order, extra columns ignored, `unit`/`type` and `note` accepted for units and notes, a missing `subsection`/`value` column reads as empty; only a file without `section` or `label` columns is refused. Cells are stripped. Year-stamped labels are stored under their canonical name, as every reader did (the table, and the retired Sell Home label set, live once in `src/plan_label_rules.py`). When the notes column is the last one, unquoted commas in notes are joined back.
- `#` comments (decision 7): a comment directly above a data row is appended to that row's notes after `"; "`. The file's opening comment block, comments followed by a blank line, and `====` lines are dropped and counted.
- Records with a section but no label (or a label but no section) are skipped and listed in the report. No legacy renames are applied here.
- **Step C3** (`src/legacy_conversion/steps/c3_plan_rows.py`, not wired into startup) does this import, then the `plan_data_migration` renames once (the current key wins; two legacy rows of one key were already collapsed last-wins, as `load_csv` then `migrate_sectioned_data` did), then drops the retired Sell Home home-value labels, then writes the marker `plan_meta['legacy_conversion.c3']`. The result equals `migrate_sectioned_data(old loader)`. The originals are only read.

**Settings, switches and tier are ordinary rows.** There are no new tables and no backfill.

| What | Row `(section / subsection / label)` | Values | No row means |
|---|---|---|---|
| Module toggle | `Optional Functions / "" / <feature key>` | `TRUE`/`FALSE` (`YES`, `1` read as on) | `default_on` |
| Plan flag | its `gate_ref`, e.g. `HELOC / Setup / heloc_enabled` | `TRUE`/`FALSE` | off |
| Plan tier | `Plan Settings / Profile / plan_tier` | `simple`, `standard`, `advanced`, `expert` | `expert` (today's behaviour) |
| "(customized)" | not stored: derived when the stored switches differ from the tier preset | | |

`module_catalog.feature_row_key(key)` names a feature's row. `set_feature()` / `feature_enabled()` keep their internals until WP4.5, which points `_read_switch` / `_write_switch` at these rows. The engine settings now in `system_config.csv` (Plan Settings, Rebalancing, ...) become rows in WP8.1.

**Old CSV file to sections.** `*` marks a section split across files.

| Old file | Sections |
|---|---|
| `client_data.csv` (anchor) | none of its own: two duplicate `Scenarios / Allocation ...` rows; `client_policy.csv`'s copies win |
| `client_household.csv` | Household, Economic Assumptions, Payroll Tax, Wellness*, Social Security*, State Comparison |
| `client_income.csv` | Social Security* (Funding Discount), Cashflow* (Earned Income, Retirement Contributions, S-Corp, Self-Employment), Income Streams |
| `client_spending.csv` | Cashflow* (Spending, Mortgage, Post-House-Sale Rent, Large Discretionary Expenses), Housing, Wellness* (four Out-of-Pocket rows) |
| `client_assets.csv` | Other Assets, Liquidity Buffer, HSA Policy*, Education Funding* (529 Plan 1), Note Receivable, DAF, Hybrid LTC, Positions |
| `client_policy.csv` | HSA Policy* (two Contributions rows), Account Policy, HELOC, Asset Allocation Policy, Asset Class Assumptions, Model Constants, Withdrawal Policy, Forced Actions, Scenarios, Reporting |
| `client_insurance_estate.csv` | Education Funding*, Annuity Death Benefits, Estate Planning, Insurance In Force, Equity Compensation |
| `client_business.csv` | Business Succession |
| `client_optional_functions.csv` | Optional Functions |
| `asset_class_optimizer_controls.csv` | Asset Class Optimizer Controls |

**Decision: no part-file column.** Rows do not record their old file. Nothing reads it: the frontend never used `source_file`, and the engine reads one merged view. Splits happen even inside one subsection, so only a per-row column could rebuild the old files exactly. For export, `csv_exchange.part_file_for_section()` gives a section's primary (first) file, which is also where the old writers put new rows. Re-importing such an export gives the same view.

## Read path (WP4.2)

**Where the plan file is.** `src/active_plan.py` is the one accessor until the plan registry (WP8.4): `active_plan_path()` is `<workspace>/plan.rpx` (where `make_plan` builds it too), or `RETIREMENT_SYSTEM_PLAN_DB` when set. The server sets that variable for the build subprocess, so the build reads the server's plan. `active_plan_store()` opens it.

**Readers.** `config_backend.load_active_config()` returns `active_plan_data()` (the plan's `sectioned_data()`) merged with the system configuration, as before. Its callers are the build (`workbook_builder.main`), `config_service` (backends payload, `module_status` for the config rows payload, allocation preview, DAF and QLAC recommendations), the housing search gate, the pricing provider and two tools. `/api/plan/forms` reads and writes the plan rows. The Plan Data file list reads the protected-field status from them. The old sectioned SQLite snapshot (`load_sqlite`, `import_csv_to_sqlite`, `local_store.latest_sectioned_data` and its writers) is deleted. A plan file with no rows is filled from the configured plan CSV set on first read, as the snapshot was.

**CSV writers until WP4.4-4.5.** The CSV set is still what the remaining writers edit (WP4.3 moved the grid and the forms; see "Write path (WP4.3)"). Every CSV writer ends with `app_core._sync_config_backends()`, which now:
1. reads the CSV set once (`csv_exchange.read_plan_csv_set`; an empty or missing set is a failure, `EmptyPlanCsvSet`, and the rows stay) and makes the plan rows equal to it (`csv_exchange.sync_plan_rows`). A row keeps its `row_id` while its key's occurrence survives. If nothing changed, nothing is written. It still applies the old loader's two load-time drops: retired `Scenarios / Sell Home` value labels and `label` header rows;
2. stores each part file's text in the legacy database's `client_files` (a part file deleted or emptied on disk is removed from it). Save As, Load Saved Plan, Open/Close Demo and snapshot restore carry the plan as that database file and rebuild the CSV set from `client_files`. The snapshot copy used to cover this;
3. writes the JSON/YAML mirrors from the plan's view.
The CSV folder comes from one resolver, `config_backend.configured_plan_csv_path()` / `configured_plan_input_dir()` (env `RETIREMENT_SYSTEM_CONFIG_FILE`, else the system configuration, else `<workspace>/input`), used by `CSV_PATH`, the sync, the first-read bootstrap and the at-rest migration. Save As and Open Demo call it before they copy the database (Save As refuses to save when it fails; snapshot restore reports a failed sync as a failed restore). Load Saved Plan, snapshot restore and Close Demo call it after they rebuild the CSV set. The at-rest migration (`plan_data_migration`) renames legacy keys in the plan file's rows in place (ticket 287's snapshot sweep, moved).

Not switched in WP4.2, because their reads belong to a read-modify-write pair with a CSV writer. Switching only the read would make the pair disagree:
- `_client_csv_rows` / `_csv_rows_payload` / `update_config_rows_payload`: the grid, moved to `row_id` in WP4.3.
- `_client_section_path` / `_read_client_section_rows` / `_write_client_rows`, and the endpoint GETs that read sections from CSV, are the strategy endpoints and `_replace_*`. That is WP4.4.
- `_backfill_optional_function_rows_to_disk` and `set_feature` persistence are WP4.5.
- Hand-off: once a writer writes `plan_rows` directly, the CSV-to-rows sync would overwrite its edits with the CSV set. WP4.3 chose the write-back below.

**Behaviour notes.** The snapshot round trip (`plan_input_from_sectioned_data(...).to_sectioned_data()`, JSON with sorted keys) is gone. Engine input now keeps the plan's row order instead of sorted keys, and the round trip's filled-in defaults are no longer added. The golden comparison (`sample_frozen`, `demo`) is unchanged. Loading a plan saved before WP4.2 whose `client_files` lack a part file keeps the workspace's current copy of that file. Before WP4.2, the build read the saved snapshot instead. WP8.4 replaces Save As and Load with plan-file operations.

**Conversion.** Nothing new beyond C3. The runtime no longer reads `plan_snapshots`, but its tables stay. WP10's source precedence ("`input/` first, then `client_files` and the latest `plan_snapshots` for anything missing", F section 8) reads them directly. `local_store` keeps only the table definitions. WP10 note: data that existed only in an old `plan_snapshots` row (no CSV copy on disk) is not read at runtime any more; C3's source precedence must pick it up from the latest snapshot, or it is lost.

## Write path (WP4.3)

**The grid.** `GET /api/config/rows` (`app_core._csv_rows_payload`, also the build preflight) serves one row per `plan_rows` row in display order (sections by creation, rows by `sort_order`). `row_index` is the row's `row_id`: the API field name is kept, its value is now stable while the row exists (a key deleted and added again gets a new id). Payload rows carry `section`, `subsection`, `label`, `value`, `units`, `notes`, `schema`, `choice_options`, `group`; the CSV-only fields (`source_file`, `source_row_index`, `columns`, `raw`, `is_header`, `is_comment`) are gone, because there are no header or comment rows in the plan. The payload also carries `revision` (`PlanStore.revision()`). `POST /api/config/rows` (`config_service.update_config_rows_payload`) writes `[{row_index, value}]` by `row_id` in one transaction: values normalized as before (dates for date fields, canonical Roth values) and stripped, the whole plan validated against the field schema (`schema_registry.validate_rows`, as before; year-stamped labels are now validated under their canonical name), a failure rolls every update back (422), an unknown id is skipped and reported ("out of range or stale row index"). The response carries the new `revision`. `sync: true` still also runs `_sync_config_backends` (JSON/YAML mirrors). The frontend needed no change: it already treated `row_index` as an opaque id and resolves build-history changes by key.

**`/api/plan/forms`.** Reads and writes the same rows through the same edit context (no separate store, no split brain). `GET` runs the bridge first, as the grid does. `POST` upserts by key: a posted key keeps its row and id, a new key is appended to its section, nothing is deleted. With `replace: true` (the payload is complete) every stored key of a section the payload names (with at least one key) and does not post is deleted too; sections not named are never touched (write-back would carry a deletion into the CSV set for good, so a partial payload must not delete). `GET` serves the stored rows with a `warning` when the CSV files cannot be read. `PATCH` sets values by key (`set_value`). Keys follow the CSV path's rules (`src/plan_label_rules.py`): cells stripped, year-stamped labels stored under the canonical name, and the rows the CSV path never keeps (`dropped_at_load`: `label` header rows, retired `Scenarios / Sell Home` labels) skipped and listed in `skipped`. Values get the CSV writer's canonical Roth form.

**One mechanism for the transition: write-back.** `plan_rows` is the plan's truth; the plan CSV set is a working copy kept equal to it for the writers that still edit CSV. Both directions run under the plan file's write lock (`BEGIN IMMEDIATE`) and an in-process lock, and each reads the CSV set inside that transaction, so no run can store a CSV set read before another run's write:
- CSV writers (strategy endpoints, `_replace_*`, Plan Data file editor, Load/restore/demo, GET-time backfills) still end with the bridge (`sync_active_plan_from_csv`, CSV set to rows).
- Row-store writers (grid, forms) edit through `active_plan.edit_active_plan(input_dir, write_file)` (`app_core._edit_active_plan`): in one transaction it (1) runs the bridge, so a CSV write not synced yet (a writer called with `sync` off, the GET backfill) is in the rows first; (2) yields the store for the edit; (3) writes every touched key (value set, row inserted or deleted) back into the CSV set with `csv_exchange.write_back_rows` through `_write_plan_data_file` (which also keeps `client_files` current); (4) runs the bridge again, so `_write_plan_data_file`'s own rules (canonical Roth values, protected retirement dates) reach the rows (the grid reports a row whose value those rules gave back as skipped, not updated). All new file texts are computed first (pure, read-back validated); if anything after the first file write fails, the previous texts are put back (files the edit created are removed) and the rows roll back, so a failed edit leaves neither side changed. A part file that does not parse fails an edit (409); reads (`GET /api/config/rows`, `/api/plan/forms`, build preflight) serve the stored rows with a `warning`. A read whose CSV set (file-bytes hash) and plan revision are as the last bridge run left them runs no bridge and takes no write lock. The next bridge run therefore reads the edit back instead of overwriting it, and a CSV writer that reads its part file sees it.
- `write_back_rows` (pure, texts in, texts out) changes only the touched keys: the value cell of every record of the key (comments and layout kept), a deleted key's records with the comment block attached to them (the comment lives on in the notes), a new key directly after the last record of its section (a new section: the end of its primary part file). It then requires the whole set to read back exactly as the rows (values, units, notes, order inside each section): a row whose notes moved (a removed comment re-attaching) gets explicit cells, anything else raises `PlanCsvError`, the edit rolls back and the grid answers 409. An edit is refused rather than lost.
- Rejected alternative: narrowing the bridge to the sections the CSV writers own. The Plan Data file editor, Load, restore and the demo swap write the whole set, the GET backfill writes into most sections, and the strategy endpoints read-modify-write whole part files that also hold grid-edited sections; no section is owned by the grid alone.
- Known limits: a bridge run that sees a new section placed before existing ones (the first GET backfill on an old plan, a strategy endpoint creating `Home Sale Split`) still renumbers every row (`sync_plan_rows` rewrite); a grid save sent with ids from before that is skipped and reported, never applied to another row (the old positional index could shift onto another field). Concurrent edits of the same part file by a CSV writer and a grid save can still lose one of them, as before.

**Deleted.** `_client_csv_rows`, the positional `row_index`/`source_row_index` map, `config_service._validate_all_workspace_plan_rows` and the grid's CSV read and write (file-I/O audit 198 to 194).

**Remaining CSV writers.** WP4.4: strategy endpoints (`strategy_asset_service`, `_client_section_path` / `_read_client_section_rows` / `_write_client_rows`, spending adjustments), `_replace_large_discretionary_expenses` / `_replace_forced_roth_conversions` / `_replace_liquidity_buffers` / `_replace_home_sale_splits` / `_replace_residency_schedule`, `_ensure_user_ui_plan_data_rows` (`plan_data_backfill`). WP4.5: `_backfill_optional_function_rows_to_disk` and `set_feature` persistence. P3.5: Plan Data file editor, folder import, Load Saved Plan / snapshot restore / demo swap (whole CSV set), then `write_back_rows`, `edit_active_plan`'s write-back, the bridge and `_sync_config_backends` are deleted and the grid path is the rows transaction alone.

Tests: `tests/test_csv_exchange_write_back_unit.py`, `tests/test_plan_rows_grid_write_path_functional.py` (grid edit then a still-CSV strategy edit of the same part file, the reverse order with an unsynced CSV write, validation rollback, stale ids, forms and grid sharing rows, forms label rules, forms replace by key, the file writer's canonical Roth values reaching the rows), and the slow `tests/test_e2e_build_journey.py::test_real_build_keeps_a_grid_edit_after_csv_and_form_edits` (grid, then strategy endpoint, then forms, then a real build).

## Where it is used next

- WP4.4: the strategy endpoints write by key through `edit_active_plan` (the grid and forms already do, WP4.3). A row is inserted after row X with `insert_row(section, sort_order=X.sort_order)`; the tie goes to the newer id. Each moved writer drops its CSV read; the write-back stays until the last CSV writer is gone.
- WP4.5: `set_feature()` writes `feature_row_key(key)` with `set_value`, and the CSV mirrors are deleted.
- WP9 grows `csv_exchange` (preview, diff, export); WP10 assembles C3 with source precedence (files first, then the old database snapshot).

Tests: `tests/test_plan_rows_fixture_equivalence_regression.py` (key invariant), `test_csv_exchange_plan_csv_unit.py`, `test_plan_rows_feature_storage_unit.py`, `test_legacy_conversion_c3_unit.py`, `test_stores_plan_store_unit.py`. Fixtures: `tests/plan_fixture.make_plan` builds `plan.rpx` beside `input/` (`ws.plan_db`, `ws.store()`, `ws.store_data()`).
