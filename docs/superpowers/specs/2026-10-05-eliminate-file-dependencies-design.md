# Eliminate CSV / JSON / YAML runtime dependencies — design and implementation plan (DRAFT for review)

Status: draft. Decisions 1-4 were chosen by the owner on 2026-10-05; items under "Open items" need an answer before the phase that depends on them.
Evidence: a read-only audit of every runtime file dependency (counts and file:line citations are quoted from it below). It found that SQLite today holds only a *derived* plan snapshot, and that the real edit and build surface is still the `input/` files.

## 1. Goal, scope, rules

**Goal.** After this work no product code path reads or writes a CSV, JSON or YAML file, except the bulk **import / export adapters** (CSV in, CSV out).

**Rules from the owner**
- No legacy code and no backwards-compatibility code left in the product.
- A **one-time conversion** of an existing user's plan is allowed, so nobody is disrupted.

**Assumptions (flag if wrong)**
- Staying as files, by design: the Excel workbook / HTML / PDF outputs, the `.rpx` plan file (a SQLite copy), logs, and the browser's own `localStorage`.
- JSON *text stored inside a SQLite column* (opaque result payloads, event details) is not a file dependency and is allowed. Anything the code filters, sorts or edits by field gets typed columns.
- JSON used as the HTTP request/response format is not a file dependency.
- Dev-time authoring sources (for example the annual tax-law update) may live as source files in the repository, but nothing in the shipped runtime reads them.

## 2. What exists today (from the audit)

| Finding | Evidence |
|---|---|
| The on-disk sectioned CSVs are the real edit surface; `plan_snapshots` is a derived copy rebuilt by `_sync_config_backends` | `app_core.py:1871-1937`; about 25 endpoints in `strategy_asset_service.py`; grid save in `config_service.py:483-538` |
| A third write path (`/api/plan/forms`) writes only the snapshot and is overwritten by the next CSV save | `plan_forms_service.py:17-36` |
| The build reads sectioned data from the snapshot but opens holdings, liabilities, HSA schedule, budget lines, YTD and several `client_*.csv` files from `input/` | `data_io.py:1038-1044, 1767-1813`, `hsa_policy.py:136-144`, `workbook_builder.py:998` |
| The build itself writes a user-data file (`client_hsa_schedule.csv`) as a side effect | `workbook_builder.py:925-937` |
| `spending_tracker.py` (about 2,000 lines) is disk-only CSV, no SQLite mirror | `spending_tracker.py` |
| 20 JSON/YAML "mirror" files are written and never read | `config_backend.py:298`, `plan_data_registry.py:56-64` |
| Build success is decided by re-reading `plan_summary.json`; five JSON sidecars are re-read by the server | `build_service.py:45-49, 141` |
| `system_config.csv` mixes app flags with engine settings; it is not in the PyInstaller `datas` | `system_config.py`, `retirement_planner.spec` |
| Reference data is read from `reference_data/*.csv`, `tax_law_v10.json`, ZIP data, two `src/*.json` | 15 shipped files |
| Startup migration rewrites every `input/*.csv` and snapshot row | `plan_data_migration.py:279-375` |
| 13 SQLite tables exist, plus raw CSV text stored in `client_files` | `local_store.py`, `config_backend.py` |

## 3. Target architecture: three databases, one access layer

```
reference.db  (read-only, ships with the app)     tax law, CMAs, correlations, mortality, state tax,
                                                   real-loss curves, security master, field schema,
                                                   ZIP metrics, tax-update dashboard, layout/field maps
app.db        (per install, survives plan swaps)   settings, secrets, prefs, backup policy + manifest,
                                                   price cache and freezes, audit log, change log,
                                                   run history, Monarch state, pricing diagnostics
plan.db       (the plan; this is the .rpx file)    plan rows, tabular datasets, plan revisions,
                                                   build results, KPI history, user overrides
```

Why two writable databases: Load Saved Plan and snapshot restore replace the whole plan database (`plan_db_replace.py`). Anything that must survive a plan swap (secrets, preferences, backup policy) cannot live in it.

**Access layer (the only code that touches storage)**
- `PlanStore` over plan.db: `rows(section)`, `get/set/insert/delete row`, `transaction()`, typed repositories for each dataset, `revision()`.
- `RefData` over reference.db: read-only typed getters that return the same Python structures the loaders return today (no consumer changes shape).
- `AppStore` over app.db.
- `csv_exchange`: the only module allowed to read or write CSV (section 6).
- Enforced by a static test: no `csv`, `json.load/dump` on data files, `yaml`, or file `open()` outside `csv_exchange`, the three stores and the packaging code.

## 4. plan.db schema (first cut)

| Table | Replaces | Notes |
|---|---|---|
| `plan_rows(row_id, section, subsection, label, value, units, notes, sort_order)` | the 9 sectioned client CSVs, anchor `client_data.csv`, optional-function rows, optimizer controls | `row_id` becomes the stable `row_index` the grid and endpoints already use; `sort_order` keeps display order |
| `holdings_lots` | `client_holdings.csv` | typed columns (account, symbol, shares, price, date, basis) |
| `liabilities`, `hsa_schedule` | `client_liabilities.csv`, `client_hsa_schedule.csv` | the build stops writing the HSA file; the default schedule is created through `PlanStore` |
| `target_allocation` | `target_allocation.csv` | only the drift report reads it |
| `spending_taxonomy`, `spending_aliases`, `spending_budget`, `spending_budget_lines`, `spending_rules`, `spending_category_map`, `spending_tier_overrides` | the 9 spending files and recovery seeds | recovery copies become `plan_revisions`, not extra files |
| `ytd_transactions`, `ytd_accounts`, `ytd_import_history` | the 3 YTD files | indexed by year and account |
| `plan_revisions(id, created_at, source, note, rows_sha256)` plus a retained row copy | `plan_snapshots`, pre-recovery backups, demo backups | undo / compare / restore; retention-capped |
| `build_results(build_id, summary_json, explorer_json, package_json, snapshot_json)` | `plan_summary.json`, `results_explorer_model.json`, `report_package.json`, `build_snapshot.json` | the server reads these instead of re-reading files |
| `kpi_snapshots`, `build_events`, `result_snapshots` | same names | already in SQLite |
| `workbook_format` | `workbook_format_overrides.json`, `workbook_format_alignments.json` | per-sheet widths and alignment |
| `custom_cma`, `custom_correlations`, `security_overrides` | writes into `reference_data/` by the admin and import routes | user edits are overrides over reference.db, never edits to shipped data |
| Engine settings (Rebalancing, Asset Class Assumptions, Annuity Calibration, Plan Settings) | those sections of `system_config.csv` | they are already merged into the plan data at load (`config_backend.py:143`), so they become ordinary `plan_rows` |

Dropped outright: `client_files` (raw file text), the unused `build_jobs` table, the relational summary tables nothing reads (`plan_members`, `plan_accounts`, `plan_income_streams`, `plan_spending_policy`) unless a consumer is found in P3.

## 5. reference.db and app.db

**reference.db** is built at release time by `tools/build_reference_db.py` from dev-only source tables. Runtime never sees the sources. The annual tax update becomes: edit source tables, run the tool, run the golden tests. Table groups: `tax_law` (structured by year / status / key), `cma`, `correlations`, `mortality`, `real_loss`, `state_tax`, `security_master`, `schema_fields` (this also carries the tier column planned in the feature-tiers design), `zip_metrics`, `top_cities`, `tax_update_status`, `monarch_field_map`, `template_layout`. `tax_constants.csv` is a fallback used only if the tax-law load fails (`taxes.py:420-425`), so it is deleted rather than ported.

**app.db** holds: `settings(key, value)` (runtime flags from `system_config.csv`, `prefs.json`, backup scheduler, Monarch policy and status), `secrets` (see open items), `audit_events` (the `audit_log.jsonl` duplicate is dropped), `admin_change_log`, `run_history`, `last_build`, `backup_manifest`, `price_cache`, `price_snapshots`, `pricing_freezes`, `pricing_diagnostics`. Locating the databases needs no config file: platform runtime paths (`platform_runtime.py`) plus one environment override and a command-line flag.

## 6. Import / export (the only CSV left)

One `csv_exchange` package, schema-driven (file shape to table mapping declared once), replacing the scattered readers:
- **Import:** parse, validate against `schema_fields`, show a preview and a diff, then commit in one transaction. Covers the plan CSV set, holdings, YTD transactions and setup, Monarch files, CMA and correlation files, security master.
- **Export:** the plan CSV set, holdings, YTD, spending set, as a zip; per-dataset export buttons.
- Browser folder import / export keeps working through the File System Access API but posts rows to the import API; the 20 mirror names disappear from `PLAN_DATA_FILES` (`dashboard.js:978-1010`).
- Removed: `/api/csv` raw-anchor routes, the admin raw-file editor (`admin_service.py:73-186`), `local_plan_data_dir` folder sync, `tools/sync_*` and `check_plan_data_sync`.

## 7. Build pipeline

- The build receives the plan.db path and a revision id (environment variable), opens one read transaction, and passes `PlanStore` rows to `parse_client`. No `candidate_input_files`, no `reference_data` fallback path.
- Results are written to `build_results`; `interpret_build_result` reads them from the database instead of `plan_summary.json`. The workbook, HTML and PDF stay files.
- The build fingerprint hashes database content (rows and datasets at the revision), not files.
- The subprocess model is unchanged for now; running the build in-process is a later option.

## 8. One-time conversion (the only legacy code)

A single removable module, `legacy_conversion/`, run at first launch of the new version:
1. If the conversion marker is absent and an old `input/` folder or old database exists, convert; otherwise do nothing.
2. Source precedence: the files in `input/` first (the audit shows they are the real edit surface), then `client_files` and the latest `plan_snapshots` for anything missing.
3. Reuse `csv_exchange` import, extended with the legacy file names, plus the row renames from `plan_data_migration.py` applied once. That renaming machinery moves into the converter and leaves the runtime.
4. Write plan.db, app.db settings (from `system_config.csv`, `prefs.json`, the old backup and Monarch state) and the marker.
5. **Originals are never modified or deleted.** The user's old folder remains as the backup.
6. Verification, built in: build the converted plan and compare the result with the pre-conversion result using the existing full-row snapshot and workbook expectations; any difference is shown to the user and blocks the marker.
7. Because each phase adds its own conversion step with a per-dataset marker, an intermediate build never leaves the user's live plan half-converted. After the final release has shipped for one version, the module is deleted.

## 9. Implementation phases

Rule for every phase: the PR switches **readers and writers of one dataset together and deletes the old path in the same PR**. No dual writes, no fallbacks. Every phase ends green on the golden build comparison and the Windows CI.

| Phase | Work | Main files |
|---|---|---|
| **P0** Safety net | Golden before/after harness: build the frozen sample plan and the demo plan, record full-row output and workbook expectations; fixtures helper that creates a plan.db from the existing CSV fixtures | `tests/`, `tools/regen_*` |
| **P1** Stores | Create `PlanStore`, `AppStore`, `RefData` modules, forward-only schema versioning (`PRAGMA user_version`), connection and transaction helpers; static "no file I/O" test in report-only mode | new `src/stores/` |
| **P2** reference.db | Build tool and sources; switch each loader in its own small PR: tax law, state tax, CMAs and correlations, mortality, real-loss, security master, schema, ZIP, governance dashboard; delete `tax_constants.csv` path | `tax_law.py`, `taxes.py`, `optimization.py`, `planning_engines.py`, `real_loss_curves.py`, `data_io.py`, `schema_registry.py`, `housing/zip_screen/` |
| **P3** Plan rows | `plan_rows` and `PlanStore`; grid and `config_service`; the 25 `strategy_asset_service` endpoints; `app_core._replace_*`, backfill, row-ensure tables; `module_catalog` reads; remove `_sync_config_backends`, the 20 mirrors, `client_files`, `/api/plan/forms` split-brain, `/api/csv` | `app_core.py`, `config_service.py`, `strategy_asset_service.py`, `config_backend.py`, `plan_forms_service.py` |
| **P4** Tabular datasets | In order: holdings, liabilities, HSA (build stops writing a file), target allocation; then the spending set (re-platform `spending_tracker.py` onto repositories); then YTD | `holdings_service.py`, `data_io.py`, `hsa_policy.py`, `spending_tracker.py`, `spending_budget_resolver.py`, `ytd_tracking.py`, `ytd_service.py` |
| **P5** Build I/O | `parse_client` and `ytd_tracking` read through the stores; results to `build_results`; remove the JSON sidecars and the re-read logic; fingerprint from DB | `report_compute.py`, `workbook_builder.py`, `build_service.py`, `build_snapshot.py`, `results_model.py`, `report_package.py` |
| **P6** App state | Split `system_config.csv` (flags to `app.db`, engine settings to plan rows); prefs, secrets, audit, change log, run history, backup policy and manifests, price cache and freezes, diagnostics, Monarch state; demo mode becomes "load the seed plan into plan.db with a revision backup", not file swapping | `system_config.py`, `runtime_config.py`, `security_audit.py`, `local_backup_scheduler.py`, `market_data.py`, `demo_plan_service.py`, `base_service.py` |
| **P7** `csv_exchange` | Consolidate all import / export into the one package; preview and diff; per-dataset export; remove the admin file editor and folder-sync routes; replace with reference-override screens | `import_preview.py`, `monarch_import.py`, `plan_routes.py`, `admin_service.py`, frontend folder-IO modules |
| **P8** Conversion | Finish `legacy_conversion/`: all dataset steps, verification, marker, UI notice; rehearse on copies of the demo plan, the frozen sample plan, and (with permission) the owner's real plan | new `legacy_conversion/` |
| **P9** Cleanup and packaging | Delete everything in the audit's dead-code list (`export_latest_plan*`, `latest_plan_input`, stub client registry, `forecast_package`, CSV backend branch, ten `system_config` path rows, env defaults); ship `reference.db` and a seed `.rpx` instead of `reference_data/` and `input/demo`; update `retirement_planner.spec` and smoke tests; turn the static test to enforcing; update docs; migrate or regenerate the 609-file test suite's fixtures through the helper | `retirement_planner.spec`, `scripts/pyinstaller_smoke*.py`, `tests/` |

Phases P2 and P3 can overlap; P4 depends on P3; P5 depends on P3 and P4; P6 is independent after P1; P8 grows with every phase and is finished last.

## 10. Test strategy

- **Golden equality** after every phase: same full-row output and workbook expectations before and after (P0 harness).
- **Static enforcement:** the "no file I/O outside the allowlist" test from P1 (reporting) to P9 (failing).
- **Converter rehearsals:** demo plan, frozen sample plan, a plan with spending history and YTD, and a plan with a legacy database but no `input/` files.
- **Fixtures:** the CSV fixture directories stay as CSV for the import adapter's tests; a helper builds a plan.db from them so about 300 file-touching tests (about 150 of them name `client_holdings.csv` / `client_data.csv`) change one call, not their logic.
- **Packaging:** the PyInstaller smoke tests assert the databases are created and seeded, not that CSVs exist.

## 11. Risks

- **Row-edit semantics.** The UI addresses rows by `row_index` / `source_row_index`; the store must keep stable ids and ordering, and the CSV comment lines (`# ...`) need a decision (store as notes or drop).
- **Concurrency.** The build subprocess reads while the UI writes: WAL plus one read transaction per build.
- **Spending tracker re-platform** is the single largest piece (about 2,000 lines, nine files).
- **Frozen app paths.** `system_config.csv` is already missing from the PyInstaller data list, so frozen behavior of today's config load is unverified.
- **Test churn** across about 300 test files; mitigated by the fixture helper.
- **Annual tax update** gains a build step; document it in the maintenance runbook.
- **Interaction with the feature-tiers design:** feature switches and the tier row become `plan_rows`; the field tier column lives in `schema_fields`. Tiers P1-P3 do not touch storage and can proceed in parallel; tiers P4-P5 are easier after P3 here.

## 12. Open items

1. **Secrets** (API keys, today plain JSON in `local_state/secrets.local.json`): store in `app.db` (simple, plain) or in the operating system's credential store (better, more platform code)?
2. **Sibling apps** (`financial_trends_reporter`, `Monarch Extractor`) read `input/*.csv` and write JSON logs; in or out of scope?
3. **CSV comment lines** in plan files: keep as row notes, or drop?
4. **Demo plan:** seed as a bundled `.rpx` (recommended), or import the bundled CSV set through the adapter on first run?
