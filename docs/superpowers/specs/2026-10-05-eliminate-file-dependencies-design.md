# Eliminate CSV / JSON / YAML runtime dependencies — design and implementation plan

> **Sequencing and staffing are superseded by [`2026-10-05-master-plan-tiers-and-file-elimination.md`](2026-10-05-master-plan-tiers-and-file-elimination.md).** This document remains the authority for the design detail it covers; the master plan decides order, merged phases, models and effort.


Status: approved by the owner on 2026-10-05 (decisions 1-9 in section 1A). Ready for per-phase planning.
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

## 1A. Confirmed decisions

| # | Decision |
|---|---|
| 1 | Plan data is a row store plus typed tables. |
| 2 | Shipped reference data is a read-only `reference.db`, never edited at runtime; user edits are overrides stored in the plan. |
| 3 | Databases: `plan.db` (the `.rpx` plan file) and `app.db` (install state) are the only databases a user ever has; `reference.db` is a shipped asset like the frontend. A single database was considered and rejected: plan files are shared and replaced, so they must not carry secrets, preferences or reference data. |
| 4 | One-time conversion on first launch; the user's old files are left untouched. |
| 5 | API keys live in the operating system credential store, not in any file or database. |
| 6 | The sibling apps (`financial_trends_reporter`, `Monarch Extractor`) are out of scope; they keep working from the bulk CSV export. |
| 7 | `#` comment lines in plan CSVs: a comment attached to a row becomes that row's note; free-floating header comments are dropped. |
| 8 | The demo plan and the actual plan coexist as separate plan files, one active at a time (section 5A). No swapping, no restore. |
| 9 | The release tool builds one seed demo plan file from source data. |

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
| `rental_properties`, `rental_improvements`, `rental_year_overrides` | none (new feature) | typed tables for the Rental Properties module (design `2026-10-05-rental-property-module-design.md`), added in master plan WP12b |
| `plan_revisions(id, created_at, source, note, rows_sha256)` plus a retained row copy | `plan_snapshots`, pre-recovery backups, demo backups | undo / compare / restore; retention-capped |
| `build_results(build_id, summary_json, explorer_json, package_json, snapshot_json)` | `plan_summary.json`, `results_explorer_model.json`, `report_package.json`, `build_snapshot.json` | the server reads these instead of re-reading files |
| `kpi_snapshots`, `build_events`, `result_snapshots` | same names | already in SQLite |
| `workbook_format` | `workbook_format_overrides.json`, `workbook_format_alignments.json` | per-sheet widths and alignment |
| `custom_cma`, `custom_correlations`, `security_overrides` | writes into `reference_data/` by the admin and import routes | user edits are overrides over reference.db, never edits to shipped data |
| Engine settings (Rebalancing, Asset Class Assumptions, Annuity Calibration, Plan Settings) | those sections of `system_config.csv` | they are already merged into the plan data at load (`config_backend.py:143`), so they become ordinary `plan_rows` |

Row notes: a CSV `#` comment attached to a row is stored in that row's `notes`; free-floating header comments are not kept.

Dropped outright: `client_files` (raw file text), the unused `build_jobs` table, the relational summary tables nothing reads (`plan_members`, `plan_accounts`, `plan_income_streams`, `plan_spending_policy`) unless a consumer is found in P3.

## 5. reference.db and app.db

**reference.db** is built at release time by `tools/build_reference_db.py` from dev-only source tables. Runtime never sees the sources. The annual tax update becomes: edit source tables, run the tool, run the golden tests. Table groups: `tax_law` (structured by year / status / key), `cma`, `correlations`, `mortality`, `real_loss`, `state_tax`, `security_master`, `schema_fields` (this also carries the tier column planned in the feature-tiers design), `zip_metrics`, `top_cities`, `tax_update_status`, `monarch_field_map`, `template_layout`. `tax_constants.csv` is a fallback used only if the tax-law load fails (`taxes.py:420-425`), so it is deleted rather than ported.

**app.db** holds: `plan_registry` and `active_plan` (section 5A), `settings(key, value)` (runtime flags from `system_config.csv`, `prefs.json`, backup scheduler, Monarch policy and status), `audit_events` (the `audit_log.jsonl` duplicate is dropped), `admin_change_log`, `run_history`, `last_build`, `backup_manifest`, `price_cache`, `price_snapshots`, `pricing_freezes`, `pricing_diagnostics`. API keys are not stored in any database: they go to the operating system credential store through one `SecretStore` wrapper (Windows Credential Manager, and the platform equivalents). Locating the databases needs no config file: platform runtime paths (`platform_runtime.py`) plus one environment override and a command-line flag.

## 5A. Plans, the demo plan, and the active plan

- Every plan is its own file: the user's plan (for example `My Plan.rpx`), `demo.rpx`, and any saved case. `app.db.plan_registry` lists known plan files (path, name, kind, last opened); `app.db.active_plan` names the one in use.
- **Open demo** creates `demo.rpx` from the bundled seed if it does not exist, then switches the active plan to it. **Exit demo** switches back. The user's plan file is never modified, copied over or restored by this. **Reset demo** re-copies the seed.
- Load Saved Plan, restore from backup and Save As all become registry operations over files; `plan_db_replace.py`'s validate-then-swap safeguards are kept for restoring a backup into a plan file.
- Builds and outputs are per plan: the output folder is derived from the plan's registry id, so the demo's workbook never overwrites the real one.
- Removed: `demo_mode_marker.json`, `local_state/demo_plan/*`, every `*.before_demo` file and the file-swapping code in `demo_plan_service.py`.

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
4. Write the converted plan to a new plan file (named from the household), register it as the active plan, fill app.db settings (from `system_config.csv`, `prefs.json`, the old backup and Monarch state) and move API keys from `secrets.local.json` into the operating system credential store. The old plain-text secrets file is the one original the converter offers to delete after confirmation, since it is the only unprotected copy of the keys. Then write the marker.
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
| **P6** App state | Split `system_config.csv` (flags to `app.db`, engine settings to plan rows); prefs, secrets, audit, change log, run history, backup policy and manifests, price cache and freezes, diagnostics, Monarch state; demo mode becomes the plan registry and per-plan files of section 5A (no swapping); API keys move to the credential store (`SecretStore`) | `system_config.py`, `runtime_config.py`, `security_audit.py`, `local_backup_scheduler.py`, `market_data.py`, `demo_plan_service.py`, `base_service.py` |
| **P7** `csv_exchange` | Consolidate all import / export into the one package; preview and diff; per-dataset export; remove the admin file editor and folder-sync routes; replace with reference-override screens | `import_preview.py`, `monarch_import.py`, `plan_routes.py`, `admin_service.py`, frontend folder-IO modules |
| **P8** Conversion | Finish `legacy_conversion/`: all dataset steps, verification, marker, UI notice; rehearse on copies of the demo plan, the frozen sample plan, and (with permission) the owner's real plan | new `legacy_conversion/` |
| **P9** Cleanup and packaging | Delete everything in the audit's dead-code list (`export_latest_plan*`, `latest_plan_input`, stub client registry, `forecast_package`, CSV backend branch, ten `system_config` path rows, env defaults); ship `reference.db` and the seed demo `.rpx` instead of `reference_data/` and `input/demo`; update `retirement_planner.spec` and smoke tests; turn the static test to enforcing; update docs; migrate or regenerate the 609-file test suite's fixtures through the helper | `retirement_planner.spec`, `scripts/pyinstaller_smoke*.py`, `tests/` |

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
- **Multiple plan files:** the active-plan switch must close and reopen connections cleanly (no builds or writes in flight), and every per-plan path (outputs, backups) must derive from the plan, not from a fixed folder.
- **Credential store availability:** headless or frozen environments without a credential service need a clear error path; the app must not silently fall back to plain text.
- **Spending tracker re-platform** is the single largest piece (about 2,000 lines, nine files).
- **Frozen app paths.** `system_config.csv` is already missing from the PyInstaller data list, so frozen behavior of today's config load is unverified.
- **Test churn** across about 300 test files; mitigated by the fixture helper.
- **Annual tax update** gains a build step; document it in the maintenance runbook.
- **Interaction with the feature-tiers design:** feature switches and the tier row become `plan_rows`; the field tier column lives in `schema_fields`. Tiers P1-P3 do not touch storage and can proceed in parallel; tiers P4-P5 are easier after P3 here.

## 12. Open items

None. Each phase gets its own implementation plan and PR before work starts.

---

# 13. Implementation plan (NOT STARTED — do not execute until the owner gives a go for a specific phase)

This section turns the design above into ordered, reviewable work. It is a plan only: no code, schema or file has been changed. Each phase needs an explicit owner go before its first PR.

## 13.1 Conventions and definition of done (apply to every PR)

1. **One dataset, one PR, no coexistence.** A PR switches all readers and writers of its dataset together and deletes the old path in the same PR. There is never dual-writing and never a fallback to files. The only legacy code allowed is in `legacy_conversion/` (section 8).
2. **Gates that must be green:** the five CI jobs (`fast-gates`, `test (windows-latest, 3.14)`, `frontend-tests`, `build`, `e2e-tests`), the golden equality test from P0, the frontend size ratchet, the architecture-diagram freshness test (regenerate with `tools/generate_system_diagram.py`), and the JS codemod census if frontend JS changes.
3. **Sanctioned regeneration only:** golden fixtures and the full-row snapshot change only through their regeneration tools with a dated entry in `GOLDEN_MASTER_CHANGELOG.md`. A storage change must not change any computed number; if one does, it is a bug, not a fixture update.
4. **Each PR carries its conversion step** (section 13.4) and its own tests; docs for the touched area are updated in the same PR.
5. **Docs-only and tool-only PRs** follow the same rules but skip CI where the workflow ignores them.
6. **Size rule:** a PR that cannot be reviewed in one sitting is split by module, not by half-finished behavior.

## 13.2 Order, dependencies and parallelism

```
P0 safety net ─► P1 stores ─┬─► P2 reference.db (8 slices, parallelizable)
                            ├─► P3 plan rows ─► P4 datasets ─► P5 build I/O ─┐
                            └─► P6 app state (independent after P1) ─────────┤
                                                       P7 csv_exchange ◄─────┤ (needs P3, P4)
                                                       P8 conversion (grows with every phase; finished last)
                                                       P9 cleanup and packaging
```

- **Critical path:** P0 → P1 → P3 → P4 → P5 → P7 → P8 → P9.
- **Parallel lanes:** P2 slices are independent of each other and of P3; P6 can run beside P3/P4; the feature-tiers design's phases 1-3 do not touch storage and can run in parallel with all of this (tiers phases 4-5 are easier after P3).
- **Relative size:** S = small, M = medium, L = large, XL = the single largest piece. About 50 PRs in total (P0 3, P1 3, P2 8, P3 7, P4 7, P5 3, P6 4, P7 4, P8 5, P9 6).

## 13.3 Phase-by-phase plan

### P0 — Safety net (3 PRs; S, M, S)

Objective: make "nothing computed changed" mechanically checkable before any storage moves.

| PR | Scope | Files |
|---|---|---|
| P0.1 | Golden before/after harness: build the frozen sample plan and the demo plan in a temp workspace; record full-row engine output, the workbook cell values of the required sheets, and the headline KPIs from `plan_summary.json`; baseline committed once; `tests/test_phase_golden_equality.py` compares live output to the baseline | `tools/golden_compare.py`, `tests/fixtures/golden_phase_baseline/`, new test |
| P0.2 | Plan-fixture helper `tests/plan_fixture.py` (`make_plan(tmp_path, fixture=...)`). Today it still lays down the CSV folder. Mechanically move the ~150 tests that name `sample_plan_frozen`, `client_data.csv` or `client_holdings.csv` onto it, in codemod batches, so later phases change only the helper's internals | `tests/plan_fixture.py`, ~150 test files |
| P0.3 | Static file-I/O audit test in report mode: AST scan for `csv`, `json.load/dump`, `yaml`, `open()` of data files, outside an allowlist; writes a count and a ratchet that can only go down | `tests/test_no_data_file_io_report.py` |

Exit: golden test green on main; every plan-creating test goes through the helper; audit count recorded.
Rollback: revert the PR (tests and tools only; no product change).

### P1 — Stores (3 PRs; M, M, S)

Objective: the three access layers exist and are tested in isolation; nothing uses them yet.

| PR | Scope |
|---|---|
| P1.1 | `src/stores/`: connection helpers (WAL, pragmas, transactions), forward-only schema versioning with `PRAGMA user_version`, schema defined as Python strings (no `.sql` files), in-memory test harness |
| P1.2 | `PlanStore` skeleton and API (rows by section, get/set/insert/delete, `transaction()`, typed repository interfaces, deterministic `revision()` hash, revisions retention); `AppStore` with `plan_registry` and `active_plan`; path derivation `plan_paths(plan_id)` (outputs, backups) |
| P1.3 | `RefData` skeleton: read-only open, version table, content hash, getters that return plain Python structures; error if the file is missing or the hash is wrong |

Exit: unit tests for every store API; no product code imports them yet; audit ratchet unchanged.
Rollback: delete the package.

### P2 — reference.db (8 slices; S to M each, parallelizable)

Objective: all shipped reference data comes from one read-only database; `reference_data/` and the two shipped JSON files leave the runtime.

| PR | Scope | Consumers switched |
|---|---|---|
| P2.1 | `tools/build_reference_db.py`, dev-only source folder `reference_src/`, deterministic build (sorted rows, no timestamps), schema and content hash, golden test: each `RefData` getter equals the structure the old loader returned (captured as fixtures before the old loaders are deleted) | none yet |
| P2.2 | Tax law | `tax_law.py:16,168-176`, `taxes.py:51,114`, `planning_engines.py:1965,1982`, `data_io.py:877`, `result_contract.py:257`; `tools/bump_version.py` filename reference |
| P2.3 | State tax and the dead `tax_constants` path | `taxes.py:335-443`; the admin state-tax editor (`strategy_asset_service.py:958-974`) writes plan-side `state_tax_overrides`, not shipped data |
| P2.4 | CMAs and correlations, including the custom-file option replaced by plan-side `custom_cma` / `custom_correlations` | `data_io.py:96-135`, `optimization.py:241-262,381-409`, `parsing/allocation_optimizer_inputs.py`, import routes `plan_routes.py:754-772` |
| P2.5 | Mortality, real-loss curves, tax-update dashboard | `planning_engines.py:759-762`, `real_loss_curves.py:119,144`, `allocation_policy.py`, `governance.py:12,28` |
| P2.6 | Security master with plan-side `security_overrides` | `data_io.py:1949-1965`, `tlh.py:42`, `portfolio_analytics.py:21,227`, `import_preview.py:223-229`, `tools/analyze_drift.py`, `tools/refresh_prices.py` |
| P2.7 | Field schema (`schema.csv`) and coverage report | `schema_registry.py:10,42,70,83`, `app_core.py:165`, `tools/generate_schema_coverage.py` |
| P2.8 | ZIP metrics and top cities, Monarch field map, workbook template layout | `housing/zip_screen/table.py`, `housing/api.py:667-682`, `monarch_import.py:49,97`, `reporting/workbook_common.py:793-799`, `scripts/build_zip_metrics.py` |

Exit: no runtime read of `reference_data/` or the shipped JSON; PyInstaller `datas` lists `reference.db`; golden test green after every slice.
Rollback: per slice; the old loader is restored by reverting that slice's PR (reference sources are retained in `reference_src/`).

### P3 — Plan rows (7 PRs; M, M, L, L, L, L, M)

Objective: the sectioned plan data lives in `plan_rows`; the CSV files stop being the edit surface.

| PR | Scope | Main files |
|---|---|---|
| P3.1 | `plan_rows` schema and `PlanStore` row API; minimal `csv_exchange` importer (used by the fixture helper and the converter); helper now builds `plan.db` from the CSV fixtures | `src/stores/`, `tests/plan_fixture.py` |
| P3.2 | Read path: `load_active_config`/`load_sqlite` replaced by `PlanStore` sectioned view; `_client_csv_rows`, `_client_section_path`; `module_catalog` and `config_service` reads | `config_backend.py`, `app_core.py:1103-1152`, `config_service.py:293,452,479`, `module_catalog.py` |
| P3.3 | Grid write path: `update_config_rows_payload`, stable `row_index`, schema validation, unification of `/api/plan/forms` with the row store (removes the split-brain) | `config_service.py:483-538`, `plan_forms_service.py:17-36` |
| P3.4a | Asset and liability endpoints | `strategy_asset_service.py` (assets, liabilities, holdings-adjacent sections) |
| P3.4b | Roth, strategy and policy endpoints; `roth_ui_build_guard.py` | `strategy_asset_service.py`, `roth_ui_build_guard.py:142-158` |
| P3.4c | Allocation, liquidity and housing endpoints; `app_core._replace_*` (5 functions), `plan_data_backfill.py`, `_ensure_user_ui_plan_data_rows` and its ~20 row tables | `strategy_asset_service.py`, `app_core.py:940-1100,1490-1850`, `plan_data_backfill.py:106-112` |
| P3.5 | Delete `_sync_config_backends`, the 20 JSON/YAML mirrors and their references (`PLAN_DATA_FILES` in `dashboard.js:978-1010`, `runtime_config.py:68-69,165-166`, `bootstrap.py:50-51`, `system_config` path rows), `client_files` for sectioned parts, `/api/csv` anchor routes, `plan_data_file_service` JSON/YAML types, `tools/sync_config_backends.py`, `tools/init_backend.py`; keep the startup row migration only until the converter replaces it (P8) | many |

Conversion step C3: sectioned CSV set (and `plan_snapshots.sectioned_json` for anything missing) → `plan_rows`, applying the legacy row renames once.
Exit: grid editing, strategy pages and module toggles work on `plan.db`; golden test green; the audit count drops by the sectioned-file readers.
Risks specific to P3: duplicate labels, row ordering, notes and units (decision 7: comments to notes); concurrency of a build reading while the grid writes (build takes one read transaction).

### P4 — Tabular datasets (7 PRs; M, S, L, L, M, M, L)

Objective: every dataset the build still reads from `input/` moves to a typed table.

| PR | Scope | Main files |
|---|---|---|
| P4.1 | Holdings lots, liabilities, target allocation | `holdings_service.py`, `data_io.py:1767-1813`, `ytd_tracking.py:1082,1155`, `portfolio_analytics.py:19,232,247`, `app_core.py:1541-1590`, `tools/refresh_prices.py`, `tools/analyze_drift.py` |
| P4.2 | HSA schedule; the default schedule is created through `PlanStore` when needed, never as a build side effect | `parsing/hsa_policy.py:136-144`, `hsa_schedule.py`, `workbook_builder.py:925-937` |
| P4.3a | `SpendingRepo` interface plus taxonomy and aliases | `spending_tracker.py` (68 functions), `import_preview.py:56-64` |
| P4.3b | Budget, budget lines, tier overrides | `spending_budget_resolver.py:182-251`, `data_io.py:1038-1044`, `app_core.py:352-374` (`_spending_budget_save_result` diff on rows) |
| P4.3c | Rules, category map; recovery copies become `plan_revisions` | `spending_tracker.py`, `tools/migrate_spending_model.py` (deleted; its one-time purpose folds into converter step C4b) |
| P4.4 | YTD transactions, accounts, import history | `ytd_tracking.py` (64 functions), `ytd_service.py`, `monarch_db_sync.py`, `monarch_autoimport_job.py`, `spending_tracker.py:86,368` |

Conversion steps: C4a (holdings, liabilities, HSA, targets), C4b (spending set, including rules, category map, tier overrides, recovery seed handling), C4c (YTD).
Exit: `input/` is not read by any product path; audit count drops accordingly; golden test green with spending history and YTD present (the P0 fixtures must include both).

### P5 — Build I/O (3 PRs; L, L, S)

| PR | Scope | Main files |
|---|---|---|
| P5.1 | The build receives `PLAN_DB` and `REVISION` (environment) and reads one read transaction through `PlanStore`/`RefData`; delete `candidate_input_files` (11 callers), `workspace_file` (8 callers), `local_plan_data_sync.py`, `materialize_workspace_files`, `build_entry._materialize_server_working_copy` | `build_entry.py`, `data_io.py`, `workspace_context.py`, `report_compute.py`, `workbook_builder.py:945-1010` |
| P5.2 | `build_results` table replaces `plan_summary.json`, `results_explorer_model.json`, `report_package.json`, `build_snapshot.json`; `interpret_build_result` reads the table; fingerprint hashes rows at the revision; JSON sidecar writers and readers deleted; `pricing_diagnostics`, `price_refresh_result`, `portfolio_drift` and `forecast_package` JSON replaced by in-process return or `app.db` rows | `build_service.py:45-49,141`, `report_package.py`, `results_model.py:733-743`, `detailed_results.py`, `build_snapshot.py`, `admin_service.py:256`, `market_data.py:1604`, `tools/refresh_prices.py`, `tools/analyze_drift.py` |
| P5.3 | Per-plan output folder derived from the plan registry id; xlsx/html/pdf remain files | `workspace_context.py`, `runtime_config.py`, `report_service.py` |

Exit: a build with an empty `input/` folder succeeds and equals the golden baseline.

### P6 — App state (4 PRs; M, M, L, L)

| PR | Scope | Main files |
|---|---|---|
| P6.1 | Split `system_config.csv`: runtime flags to `app.db.settings`; engine knobs become `plan_rows` sections; the app version string moves to a Python constant (so `bump_version` and `check_version_surfaces` stop editing a data file); `tools/set_local_mode.py` becomes a settings command | `system_config.py`, `runtime_config.py:150-185`, `data_io.py:615`, `config_backend.py:143,259`, `admin_service.py:136-186`, `tools/bump_version.py`, `tools/check_version_surfaces.py` |
| P6.2 | `SecretStore` over the operating system credential store (new third-party dependency, `keyring` or equivalent: **approval gate before this PR**), PyInstaller hidden imports for the platform backend, explicit error path when no credential service exists (never a silent plain-text fallback) | `secrets_store.py`, `retirement_planner.spec`, `scripts/pyinstaller_smoke*.py` |
| P6.3 | Preferences, audit log (drop the `.jsonl` duplicate), admin change log, run history, last-build record, backup policy and manifests, Monarch policy and status, price cache | `base_service.py:59-87`, `security_audit.py:111-139,280-330`, `report_service.py:118-139`, `local_backup_scheduler.py`, `monarch_autoupdate.py`, `market_data.py:205,393,407` |
| P6.4 | Plan registry and active plan (section 5A): Load / Save As / restore / backup over plan files, demo and actual plans as separate files, demo seed creation and reset, frontend plan switcher (list, open demo, exit demo, reset demo); delete demo file swapping | `plan_file_service.py`, `desktop_api.py:264-353`, `plan_db_replace.py`, `demo_plan_service.py`, `platform_runtime.py`, frontend plan-file modules |

Conversion steps: C6a (settings from `system_config.csv`, `prefs.json`, backup and Monarch state), C6b (keys from `secrets.local.json` to the credential store, then offer to delete the plain file), C6c (the converted plan registered as the active plan).

### P7 — csv_exchange (4 PRs; L, M, M, L)

| PR | Scope |
|---|---|
| P7.1 | Package skeleton: file-shape to table mapping declared once, parse, validate against `schema_fields`, preview, diff, single-transaction commit |
| P7.2 | Plan CSV set import and export (zip), including the legacy file names the converter needs; per-dataset export |
| P7.3 | Holdings, YTD, Monarch, CMA, correlation and security-master adapters re-pointed at the package; `import_preview.py`, `monarch_import.py`, `plan_routes.py:924-1000` |
| P7.4 | Frontend: folder import/export posts rows to the import API; remove the mirror names; admin screens for reference overrides; delete the raw admin file editor and `/api/admin/csv-file/...`, `/api/admin/reference-files`, `plan_data_files.py` allowlists, `local_plan_data_dir` folder sync, `tools/sync_plan_data_from_folder.py`, `tools/check_plan_data_sync.py` |

Exit: the static audit shows CSV access only inside `csv_exchange`.

### P8 — One-time conversion (5 PRs; M, L, M, M, S)

| PR | Scope |
|---|---|
| P8.1 | `legacy_conversion/` skeleton: runner, per-step markers, dry-run mode, report, "originals are never modified" guard (opens source files read-only) |
| P8.2 | Assemble steps C3, C4a-c, C6a-c in order; source precedence (files in `input/` first, then `client_files` and the latest `plan_snapshots`); the row renames from `plan_data_migration.py` move here and leave the runtime |
| P8.3 | Verification: the converter reads the last results the old version produced (`output/plan_summary.json`, `kpi_snapshots`), builds the converted plan, and compares the deterministic KPIs; any difference is shown to the user and blocks the done marker |
| P8.4 | First-launch UI: notice, progress, report, "view differences", and a clear message that originals are untouched |
| P8.5 | Rehearsals: the demo plan, the frozen sample plan, a plan with spending history and YTD, a plan with a legacy database and no `input/` files, and (with the owner's permission) a copy of the owner's real plan; results recorded in a rehearsal log |

Rollback: converter steps are idempotent and write only to new files; deleting the new plan file and the marker lets the step run again.

### P9 — Cleanup and packaging (6 PRs)

| PR | Scope |
|---|---|
| P9.1 | Delete the dead code listed in the audit: `export_latest_plan*`, `latest_plan_input`, the stub client registry and `local_plan_registry.csv` constant, `forecast_package`, the CSV backend branch, the ten `system_config` path rows, env defaults, `build_jobs` table, `live_pricing_test_results.json` exclusions |
| P9.2 | Packaging: `retirement_planner.spec` ships `reference.db` and the seed demo `.rpx`; remove `reference_data/` and `input/demo` from `datas`; update `scripts/pyinstaller_smoke*.py`, `tools/build_release_package.py`, `tools/check_package_clean.py`; `seed_frozen_workspace` creates the plan and app databases |
| P9.3 | Turn the static audit into an enforcing test (zero allowed outside the allowlist) |
| P9.4 | Test suite finalization: CSV fixtures kept only for the importer and converter tests (`tests/fixtures/csv_exchange/`); remove tests of deleted behavior; regenerate sanctioned fixtures with changelog entries |
| P9.5 | Documentation: `FUNCTIONAL_SPEC`, `CURRENT_SYSTEM_DESIGN_SPEC`, `API_CONTRACTS`, `CLAUDE.md`, `CONTRIBUTING`, `ANNUAL_MAINTENANCE_RUNBOOK` (tax update = edit `reference_src/` + run the reference build tool), release notes, architecture diagram |
| P9.6 | **Later release, not part of the first:** delete `legacy_conversion/` once every active install has converted |

## 13.4 Conversion rollout and release cadence

- Each phase adds its conversion step to the same removable module, with a per-step marker, so any build on `main` converts the owner's live plan safely and incrementally.
- Recommended cadence: merge a phase to `main` only after its conversion step has run on a copy of the owner's plan (P8.5 rehearsal, brought forward per phase), then update the live install.
- The old `input/` folder and legacy database are never modified or deleted by any step, so every step can be re-run from the originals.

## 13.5 Test and gate matrix

| Phase | Golden equality | Converter rehearsal | Static audit | Packaging smoke |
|---|---|---|---|---|
| P0 | creates baseline | n/a | report | unchanged |
| P1 | green | n/a | report | unchanged |
| P2 | green after each slice | n/a | ratchet down | `reference.db` present |
| P3 | green | C3 | ratchet down | unchanged |
| P4 | green with spending and YTD | C4a-c | ratchet down | unchanged |
| P5 | green, `input/` empty | all prior | ratchet down | unchanged |
| P6 | green | C6a-c | ratchet down | credential store path |
| P7 | green | all prior | CSV only in `csv_exchange` | unchanged |
| P8 | green | full rehearsals | unchanged | unchanged |
| P9 | green | final | **enforcing** | full smoke on frozen build |

## 13.6 Start conditions and approval gates

Before any phase begins, the owner confirms: the go for that phase; a copy of the live plan available for rehearsals (from P3 on); and, before P6.2, approval of the new credential-store dependency and its frozen-build behavior.

## 13.7 Deliberately deferred

Running the build in-process instead of a subprocess; multi-user or hosted storage; moving the sibling apps onto the stores; encrypting `plan.db` at rest.
