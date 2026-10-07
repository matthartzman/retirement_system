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

## Where it is used next

- WP4.2: the read path (`load_active_config`, `_client_csv_rows`, `module_catalog` / `config_service` reads) uses `sectioned_data()` and `all_rows()`.
- WP4.3 / 4.4: the grid and the strategy endpoints write by `row_id` and by key. A row is inserted after row X with `insert_row(section, sort_order=X.sort_order)`; the tie goes to the newer id.
- WP4.5: `set_feature()` writes `feature_row_key(key)` with `set_value`, and the CSV mirrors are deleted.
- WP9 grows `csv_exchange` (preview, diff, export); WP10 assembles C3 with source precedence (files first, then the old database snapshot).

Tests: `tests/test_plan_rows_fixture_equivalence_regression.py` (key invariant), `test_csv_exchange_plan_csv_unit.py`, `test_plan_rows_feature_storage_unit.py`, `test_legacy_conversion_c3_unit.py`, `test_stores_plan_store_unit.py`. Fixtures: `tests/plan_fixture.make_plan` builds `plan.rpx` beside `input/` (`ws.plan_db`, `ws.store()`, `ws.store_data()`).
