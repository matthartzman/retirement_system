# Plan rows model (`plan.db` / `.rpx`)

Status: WP4.1 (owner review checkpoint). The summary below is the PR-body text.

## Row-model summary

**Tables.** plan.db schema v1 is unchanged; WP4.1 needs no migration.
- `plan_rows(row_id, section, subsection, label, value, units, notes, sort_order)`: every sectioned plan field, including settings and feature switches. `row_id` is stable and never reused (it becomes the grid's `row_index`).
- `plan_revisions` + `revision_rows` (snapshots, retention) and `plan_meta` (key/value facts such as conversion markers).

**Keys and order.**
- A field is addressed by `(section, subsection, label)`. A key may repeat (the old CSV set has two such duplicates); the last row in display order is the effective one, as `load_csv` read it.
- Rows inside a section are ordered by `(sort_order, row_id)`, and sections by creation (lowest `row_id`). After an import this is the old CSV order.
- `PlanStore.sectioned_data()` is the engine view `{section: {subsection: {label: value}}}`. It uses the same rules and key order as `load_csv`, proven equal for `sample_frozen` and `demo` (dict, key order and `parse_client` output).
- Writes: `set_value(section, subsection, label, value)` updates the effective row or appends one. The grid uses `get_row` / `set_row` / `insert_row` / `delete_row` by `row_id`, plus `transaction()` and `revision()`.

**Import (`src/csv_exchange`, the one CSV reader from now on).**
- Reads the plan CSV set (`client_data.csv` plus 9 parts) in the old order into an empty plan, in one transaction. It returns a report: files read and missing, rows, comments attached and dropped, skipped records.
- Cells are stripped. Year-stamped labels are stored under their canonical name, as every reader did. Unquoted commas in notes are joined back.
- `#` comments (decision 7): a comment directly above a data row is appended to that row's notes after `"; "`. The file's opening comment block, comments followed by a blank line, and `====` lines are dropped and counted.
- Records with a section but no label (or a label but no section) are skipped and listed in the report. No legacy renames are applied here.
- **Step C3** (`src/legacy_conversion/steps/c3_plan_rows.py`, not wired into startup) does this import, then the `plan_data_migration` renames once (the current key wins), then drops the retired Sell Home home-value labels, then writes the marker `plan_meta['legacy_conversion.c3']`. The result equals `migrate_sectioned_data(old loader)`. The originals are only read.

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

**Writers until WP4.3-4.5.** The CSV set is still what the writers edit. Every CSV writer ends with `app_core._sync_config_backends()`, which now:
1. reads the CSV set once (`csv_exchange.read_plan_csv_set`) and makes the plan rows equal to it (`csv_exchange.sync_plan_rows`). A row keeps its `row_id` while its key's occurrence survives. If nothing changed, nothing is written. It still applies the old loader's two load-time drops: retired `Scenarios / Sell Home` value labels and `label` header rows;
2. stores each part file's text in the legacy database's `client_files`. Save As, Load Saved Plan, Open/Close Demo and snapshot restore carry the plan as that database file and rebuild the CSV set from `client_files`. The snapshot copy used to cover this;
3. writes the JSON/YAML mirrors from the plan's view.
Save As and Open Demo call it before they copy the database. Load Saved Plan, snapshot restore and Close Demo call it after they rebuild the CSV set. The at-rest migration (`plan_data_migration`) renames legacy keys in the plan file's rows in place (ticket 287's snapshot sweep, moved).

Not switched here, because their reads belong to a read-modify-write pair with a CSV writer. Switching only the read would make the pair disagree:
- `_client_csv_rows` is the grid. `row_index` is a position in the CSV set, read by `_csv_rows_payload` and written by `update_config_rows_payload`. WP4.3 moves both to `row_id`.
- `_client_section_path` / `_read_client_section_rows` / `_write_client_rows`, and the endpoint GETs that read sections from CSV, are the strategy endpoints and `_replace_*`. That is WP4.4.
- `_backfill_optional_function_rows_to_disk` and `set_feature` persistence are WP4.5.

**Behaviour notes.** The snapshot round trip (`plan_input_from_sectioned_data(...).to_sectioned_data()`, JSON with sorted keys) is gone. Engine input now keeps the plan's row order instead of sorted keys, and the round trip's filled-in defaults are no longer added. The golden comparison (`sample_frozen`, `demo`) is unchanged. A plan saved before WP4.2 whose `client_files` lack a part file loads that file from the current CSV set. WP8.4 replaces Save As and Load with plan-file operations.

**Conversion.** Nothing new beyond C3. The runtime no longer reads `plan_snapshots`, but its tables stay. WP10's source precedence ("`input/` first, then `client_files` and the latest `plan_snapshots` for anything missing", F section 8) reads them directly. `local_store` keeps only the table definitions.

## Where it is used next

- WP4.3 / 4.4: the grid and the strategy endpoints write by `row_id` and by key. A row is inserted after row X with `insert_row(section, sort_order=X.sort_order)`; the tie goes to the newer id.
- WP4.5: `set_feature()` writes `feature_row_key(key)` with `set_value`, and the CSV mirrors are deleted.
- WP9 grows `csv_exchange` (preview, diff, export); WP10 assembles C3 with source precedence (files first, then the old database snapshot).

Tests: `tests/test_plan_rows_fixture_equivalence_regression.py` (key invariant), `test_csv_exchange_plan_csv_unit.py`, `test_plan_rows_feature_storage_unit.py`, `test_legacy_conversion_c3_unit.py`, `test_stores_plan_store_unit.py`. Fixtures: `tests/plan_fixture.make_plan` builds `plan.rpx` beside `input/` (`ws.plan_db`, `ws.store()`, `ws.store_data()`).
