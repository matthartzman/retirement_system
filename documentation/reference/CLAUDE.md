# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

**Run in desktop mode (default, PyWebView native window, no HTTP):**
```
python main.py
```

**Run in browser/server mode (stdlib local HTTP on port 5050, opens browser):**
```
python main.py --mode server
```

**Run tests (pytest):**
```
pytest tests/
pytest tests/test_v11_architecture_functional.py          # single test file
pytest tests/test_v11_architecture_functional.py::test_name  # single test
```

**Run regression checks (static analysis, not pytest):**
```
python tools/run_regression.py
```

**Build the standalone exe (preferred — builds, then backs up to OneDrive):**
```
python build.py            # PyInstaller build + timestamped OneDrive zip backup
python build.py --no-backup  # build only
```
Or double-click `launchers/BUILD.bat`. The raw build step alone is still:
```
pyinstaller retirement_planner.spec --noconfirm
```
Output lands at `dist/retirement_planner/retirement_planner.exe` (onedir layout). After any change to `frontend/`, `src/`, or `tools/`, rebuild the exe to bundle updates. `build.py` runs `tools/backup_to_onedrive.py` after a successful build, dropping a full zip into the OneDrive `Retirement Planning/Backups` folder (keeps the last 10).

### Project location (moved off OneDrive)

The current working copy lives at `C:\RetirementPlanning\Version 12` on the local drive. It is deliberately **outside** OneDrive to avoid sync-induced file corruption (a OneDrive partial write once truncated `frontend/js/dashboard.js`). OneDrive is used only as the backup target via `tools/backup_to_onedrive.py`. All launcher/shortcut scripts resolve paths relative to their own location, so the tree is relocatable. To (re)create the desktop icon after a move, run `python tools/INSTALL_DESKTOP_ICON.py` (or double-click `launchers/install_desktop_shortcut.bat`). Launcher scripts (`START_APP.bat`, `BUILD.bat`, desktop-shortcut installers) live in `launchers/`; scheduled plan backups (`*.rpx`) in the workspace's `saved_plans/auto_backups/` (Save As writes to a path you choose); long-form docs in `documentation/`.

**Install dependencies:**
```
pip install -r requirements.txt
```

## Testing Discipline

Test tiers, commands, markers, naming rules, isolation rules, the "search tests/ first" checklist and what CI runs are in `documentation/reference/TESTING_AND_CI.md`. Golden-master pins are changed only through `python tools/regen_golden_master.py` (run `measure` first); see `documentation/reference/GOLDEN_MASTER_RECOVERY_RUNBOOK.md`. Do not point a script at the live plan file (`<workspace>/plan.rpx`) to regenerate pins: it is real client data, gitignored, and the tests use the committed `tests/fixtures/csv_exchange/sample_plan_frozen/` fixture instead. Do not mark a task complete without running at least the fast tier.

## Architecture

### Two launch modes, one local route registry

`main.py` is the entry point. It sets `RETIREMENT_SYSTEM_*` environment variables for local mode and then chooses between:

- **Desktop mode** (`src/desktop_app.py`): Opens a PyWebView native window pointed at `frontend/index.html`. All `fetch('/api/...')` calls in JS are intercepted by `frontend/js/pywebview_bridge.js` and routed through `src/desktop_api.py`, which calls the stdlib route-registry test client in-process — no HTTP socket is ever opened.
- **Server mode**: Starts the stdlib local HTTP runtime on `127.0.0.1:5050` and opens a browser tab.

Both modes run the same local route registry defined in `src/server/` and served by `src/http_runtime/`.

### Local server (`src/server/` + `src/http_runtime/`)

The server is assembled by importing from multiple route files, each doing `from .app_core import *` to share a common namespace:

- `app_core.py` — local route-registry `app` object, all shared helpers (`_sqlite_db()`, `_read_plan_data_file()`, `_write_plan_data_file()` for the flat datasets (plan-file tables), `_edit_active_plan()` / `_read_active_plan()` for the plan rows), and base API routes
- `plan_routes.py` — plan load/save/export, "Load Saved Plan", "Start New Plan"
- `workbook_routes.py` — Excel workbook build trigger, build progress polling, Results Explorer API
- `admin_routes.py` — system config, admin UI

`src/server/__init__.py` imports from all route files to register their routes on the local app.

### Data storage and the canonical source hierarchy

Plan data lives in the plan file, and per-install state in `app.db` (`documentation/reference/CURRENT_SYSTEM_DESIGN_SPEC.md` §4.1 and §4.6):

1. **`plan.rpx`** (the plan file, a SQLite `PlanStore`; `src/active_plan.py` finds it: `<workspace>/plan.rpx` or `RETIREMENT_SYSTEM_PLAN_DB`) — the **only store of the sectioned plan data** (household, income, spending, assets, policy, switches, tier ... as `plan_rows`). Readers use `active_plan_data()` / `load_active_config()`; every writer (grid, `/api/plan/forms`, the strategy endpoints) edits through `active_plan.edit_active_plan()` in one transaction. Nothing mirrors it into CSV, JSON or YAML files; CSV import/export is `src/csv_exchange` (WP9). The flat datasets are tables of the same file (`holdings_lots`, `liabilities`, `hsa_schedule`, `target_allocation`, `spending_*`, `ytd_*`), and `build_results` holds each build's JSON parts.
2. **`local_state/app.db`** — per-install state: settings (runtime settings, preferences, policies), the plan registry (`plan_registry`, `active_plan`), audit events, backup manifests, the price cache and the last build. Secret values are in the OS credential store (`src/secrets_store.py`), never in a file or in `app.db`.
3. **`local_state/retirement_system_v10.db`** — the legacy local database, no longer a plan store. Still written by KPI and result snapshots (`src/local_store.py`) and pricing snapshots (`src/portfolio_analytics.py`). Its `client_files` table is read only by the one-time converter (`src/legacy_conversion`, WP10).

`_read_plan_data_file()` / `_write_plan_data_file()` (`app_core.py`) read and write the flat datasets' tables through `plan_datasets`; nothing is written to `client_files` or to a CSV file. The sectioned CSV set (`client_data.csv` and its part files) and the JSON/YAML mirrors are gone: CSV is read and written only through `csv_exchange` (`/api/import/*`, `/api/export/*`). Old files remain only as the converter's source (`src/legacy_conversion`, WP10) and as test fixtures under `tests/fixtures/csv_exchange/`.

**Flat datasets (not section/subsection/label rows)**: plan-file tables, rendered as CSV text by the routes —
- `holdings_lots` — `account, symbol, purchase_date, shares, purchase_price, lot_type`
- `liabilities` — auto / HELOC / student-loan / credit-card / other debts (amortized into the projection cash flow)
- `spending_budget_lines` — per-line spending budget rows (`section, line_id, label, category_id, start_year, end_year, one_time_year, amount_per_year, mode, notes`)

### "Start New Plan" vs "Load Saved Plan"

- **"Start New Plan"** (`start_blank_plan` in `workbook_routes.py`, delegated to `BlankPlanService.start_blank_payload()`): backs up the plan file (`plan.rpx.before_blank_<ts>`) and the legacy database, then clears the household facts in the plan rows (`src/blank_plan.py`: policy and settings sections and the curated system defaults keep their values) and blanks holdings, liabilities and the HSA schedule.
- **"Load Saved Plan"** (`plan_load_file` in `plan_routes.py`, `plan_file_service.py`): by default registers the chosen `.rpx` and activates it, with no copy. `mode: "restore"` instead replaces `plan.rpx` with it through `plan_db_replace.replace_active_db` (validated copy, WAL checkpoint and sidecar removal, backup to `plan.rpx.before_load_<ts>`, then the row-rename migration). **Save As** copies the plan file to a path you choose and activates the copy. A saved plan file holds the flat datasets too (they are plan-file tables).

### Frontend (`frontend/`)

- `frontend/index.html` + `frontend/js/dashboard.js` — main UI, a single-page app with no build step
- `frontend/js/admin.js` — admin panel
- `frontend/js/pywebview_bridge.js` — intercepts `fetch()` in desktop mode and routes through `window.pywebview.api.request()`
- `frontend/js/spending_dashboard.js` — spending detail sub-view

`dashboard.js` is the central frontend file (several thousand lines, readable source, split further across the `dashboard_decomp_*.js` files beside it; check the current size with `wc -l`). Key patterns:
- `STEPS` array (top of file) defines the left nav; each step has an `id`, `group`, `title`, and optional custom render function. The nav renders a group header whenever `group` changes, so all steps sharing a group must be contiguous in the array.
- `rows` array holds all plan data fields fetched from `/api/config/rows`
- `renderMain()` dispatches to per-step render functions (`renderIncomeWork`, `renderFieldGroups`, etc.)
- `renderFieldGroups(rs)` re-sorts rows by `sortRowsByDependency()` (dependency rank + label name). Steps needing explicit section order must build their own group map from a pre-sorted array rather than delegating to `renderFieldGroups`.

### Projection and build pipeline

The Excel workbook build is triggered via `/api/build/start` and runs `tools/build_workbook.py` as a subprocess (via `sys.executable`). In the frozen exe, `main.py`'s script-runner mode handles this: any argument ending in `.py` is `runpy.run_path`'d.

`src/projection_pipeline.py` — named pipeline facade  
`src/projection_stages/deterministic_engine.py` — year-by-year deterministic projection  
`src/reporting/workbook_builder.py` — assembles the Excel output  
`src/detailed_results.py` — parses completed Excel for the Results Explorer; `workbook_detailed_index()` prefers the semantic model stored in the build's `build_results` row (`explorer`) and merges in any additional tabs found by reading the actual Excel file directly.

### Path resolution in the frozen exe

`BASE_DIR = Path(__file__).resolve().parents[2]` in `app_core.py` resolves to `_internal/` (the PyInstaller bundle root), not the exe's parent directory. Writable user data (the plan file, `app.db`, `output/`, `local_state/`) must be resolved relative to `sys._MEIPASS` or the exe path, not `BASE_DIR`, when adding new file I/O in frozen mode.

### Backup naming conventions

Backups the app writes (kept on the local drive, not OneDrive; see `documentation/reference/CURRENT_SYSTEM_DESIGN_SPEC.md` §4.3):
- `plan.rpx.version_<timestamp>` (beside the plan file) and `local_state/retirement_system_v10.db.version_<timestamp>` — created on **Save & Exit** (`/api/plan/exit-snapshot`), last 10 of each kept
- `plan.rpx.before_load_<timestamp>` — created before a `mode: "restore"` load
- `plan.rpx.before_snapshot_restore_<timestamp>` — created before a build-snapshot restore
- `plan.rpx.before_blank_<timestamp>` (and the legacy database's `before_blank` copy) — created before "Start New Plan" clears the household facts
- Scheduled plan backups (`*.auto_<stamp>.rpx`) go to `saved_plans/auto_backups/` by default; their manifests are rows of `app.db`

Full-project zip backups are written to OneDrive `Retirement Planning/Backups` by `tools/backup_to_onedrive.py` on each `build.py` rebuild. The repo is under git; generated/heavy dirs (`dist/`, `build/`, `output/`, `local_state/`) are listed in `.gitignore` for source-control hygiene.
