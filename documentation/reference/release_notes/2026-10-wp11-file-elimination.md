# Storage changes: file elimination (WP11), October 2026

Record of the WP11 storage work. It describes where data lives now. It is not a
change to the model: for results that moved, see
`2026-09-changes-334-339.md`.

## What changed

- **Plan data lives in the plan file.** Each plan is one SQLite file
  (`plan.rpx`), and the plan registry is in `app.db`. The sectioned plan rows,
  the holdings, liabilities, HSA schedule, target allocation, spending and YTD
  tables, and each build's results all sit in the plan file.
- **Per-install state lives in `local_state/app.db`.** Runtime settings,
  preferences, backup and Monarch policies, audit events, backup manifests, the
  price cache and the last-build record are in `app.db`. The runtime no longer
  reads or writes `system_config.csv` or `secrets.local.json`, and it does not
  read the `input/*.csv` plan files except two fallbacks: the source-run demo
  seed (`input/demo`, when the shipped seed is absent) and the account-setup
  recovery search.
- **Secrets are in the OS credential store** (`keyring`). Only the secret names
  are indexed in `app.db`. There is no plain-text fallback.
- **CSV only through import and export.** `src/csv_exchange` is the one CSV
  reader and writer: plan-set and per-dataset import (preview, then commit) and
  export, at `/api/import/*` and `/api/export/*`. The admin CSV backup is the
  same plan-set export.
- **The seed demo plan ships as a plan file.** A frozen build includes
  `src/reference/demo_seed.rpx`, built from `input/demo` by
  `python tools/build_demo_seed.py` (`--check` reports drift). A fresh
  workspace and Open demo and Reset demo copy it. The `input/demo` CSV folder is
  not bundled.
- **The file-I/O audit is enforcing.**
  `tests/test_no_data_file_io_enforcing_regression.py` fails on any csv, json,
  yaml, `open()` or `Path` read or write under `src/` that is not on its
  reasoned allowlist. The allowlist covers the `csv_exchange` package, the
  legacy converter, files the user picks for import, generated outputs and
  caches.
- **Dead code removed.** The candidates in the WP11.1 reachability report
  (`tools/wp11_reachability.py`) were deleted where nothing else referenced
  them. Examples: `src/server/plan_data_files.py` and its `/api/plan-data/*`
  routes, the `build_jobs` table, and `reference_src/tax_constants.csv`.
- **The legacy converter stays for one more release.** The first-launch
  conversion (`src/legacy_conversion`, WP10) is still present and is removed in
  a later release. Its reads of the old files, and the legacy helpers it relies
  on, are the entries on the audit allowlist.

## What still uses files or the legacy database

- `local_state/retirement_system_v10.db` (legacy) still receives KPI and result
  snapshots, pricing snapshots and pricing freezes. It holds no plan data.
- Build outputs are files: the workbook, the HTML dashboard and the PDF, in
  `output/plans/<plan_id>/`. The build snapshot's plan-file copy,
  `plan_database_snapshot.rpx`, sits beside them.
- Scheduled plan backups (`*.auto_<stamp>.rpx`) are files in
  `saved_plans/auto_backups/`, and their manifests are rows of `app.db`.

## For maintainers

- Tax-law updates: edit `reference_src/`, then run
  `python tools/build_reference_db.py`. Use `--check` to confirm the committed
  `src/reference/reference.db` is current.
- Household premium and Social Security wage base fields are plan rows, edited
  in the app. They are not read from `input/client_household.csv`.
- CSV test fixtures are under `tests/fixtures/csv_exchange/`.
