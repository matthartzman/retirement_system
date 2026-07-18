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
pytest tests/test_90_v10_architecture.py          # single test file
pytest tests/test_90_v10_architecture.py::test_name  # single test
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

The current working copy lives at `C:\RetirementPlanning\Version 10 - ChatpGPT` on the local drive. It is deliberately **outside** OneDrive to avoid sync-induced file corruption (a OneDrive partial write once truncated `frontend/js/dashboard.js`). OneDrive is used only as the backup target via `tools/backup_to_onedrive.py`. All launcher/shortcut scripts resolve paths relative to their own location, so the tree is relocatable. To (re)create the desktop icon after a move, run `python tools/INSTALL_DESKTOP_ICON.py` (or double-click `launchers/install_desktop_shortcut.bat`). Launcher scripts (`START_APP.bat`, `BUILD.bat`, desktop-shortcut installers) live in `launchers/`; saved plan exports (`*.rpx`) in `saved_plans/`; long-form docs in `documentation/`.

**Install dependencies:**
```
pip install -r requirements.txt
```

## Testing Discipline — MANDATORY

**Run the full test suite after every non-trivial change.** Do not mark any task complete without running `pytest tests/ --tb=short -q` and resolving every new failure. This is not optional. The cost of a broken suite compounds quickly; catching failures immediately is cheap.

```
pytest tests/ --tb=short -q
```

### When you change any of these, search tests/ first

| What changed | Command to run before changing |
|---|---|
| Local route URL | `grep -r "old/url/path" tests/` |
| JS function or string | `grep -r "old_string" tests/` |
| Dict key returned by an API or engine | `grep -r "old_key_name" tests/` |
| Public function or import in src/ | `grep -r "function_name" tests/` |
| Workbook sheet name | `grep -r "Old Sheet Name" tests/ tests/fixtures/` |
| Plan data input (`input/client_data.csv`) | Re-run golden master test and update expected values |

Update every matching test **in the same session as the code change** — not later.

### Golden master maintenance

`tests/test_2_recommendations.py` and `tests/fixtures/golden_master_engine_cases.json` store expected projection numbers. Whenever input data or engine constants change, regenerate and update them:

```python
# Get current values:
python -c "
from src.data_io import load_csv, parse_client, summarize_validation
from src.plan_config import ensure_engine_config
from src.planning_engines import project
from pathlib import Path
c = ensure_engine_config(parse_client(load_csv(Path('input/client_data.csv')), ''), source='test')
c.update({'roth_policy': 'none', 'mc_paths': 5, 'mc_sensitivity_sims': 1})
rows = project(c)
print('nw:', round(rows[-1]['total_nw'], 2), 'tax:', round(sum(r['total_tax'] for r in rows), 2))
"
```

### Fixture file locations

| File | What it tests |
|---|---|
| `tests/fixtures/golden_master_engine_cases.json` | Per-scenario projection metrics (NW, taxes, RMDs, conversions) |
| `tests/fixtures/workbook_snapshot_expectations.json` | Workbook sheet names and required text phrases |
| `tests/fixtures/irs_style_examples.json` | IRS-example tax calculations |

When workbook sheet names change (e.g. `'1. Executive Summary'` → `'1A. Executive Summary'`), update **both** the fixture file and any hardcoded names in test source.

### Specific breakage patterns to prevent

- **Route versioning**: routes in this codebase do NOT use a `/api/v8/` prefix — they are `/api/...`. Tests that use the old prefix will get 404.
- **JS string checks**: `dashboard.js` is the authoritative source. Before asserting a string is present, grep for it: `grep "the_string" frontend/js/dashboard.js`.
- **`refresh_api_keys()` clobbers manual test setup**: if a test manually sets provider API keys to `None`, also monkeypatch `refresh_api_keys` to a no-op, or the method will re-load keys from environment variables.
- **Workbook sheet names**: sheets use hierarchical naming (`1A. Executive Summary`, `2B. Asset Allocation`, not `1. Executive Summary`, `4. Asset Allocation`). The mapping lives in `src/reporting/workbook_builder.py`.
- **Regenerate plan_data_manifest**: after any schema change, run `python tools/check_plan_data_sync.py --write` to resync the manifest.

## Architecture

### Two launch modes, one local route registry

`main.py` is the entry point. It sets `RETIREMENT_SYSTEM_*` environment variables for local mode and then chooses between:

- **Desktop mode** (`src/desktop_app.py`): Opens a PyWebView native window pointed at `frontend/index.html`. All `fetch('/api/...')` calls in JS are intercepted by `frontend/js/pywebview_bridge.js` and routed through `src/desktop_api.py`, which calls the stdlib route-registry test client in-process — no HTTP socket is ever opened.
- **Server mode**: Starts the stdlib local HTTP runtime on `127.0.0.1:5050` and opens a browser tab.

Both modes run the same local route registry defined in `src/server/` and served by `src/http_runtime/`.

### Local server (`src/server/` + `src/http_runtime/`)

The server is assembled by importing from multiple route files, each doing `from .app_core import *` to share a common namespace:

- `app_core.py` — local route-registry `app` object, all shared helpers (`_sqlite_db()`, `_read_plan_data_file()`, `_write_plan_data_file()`, `_sync_config_backends()`), and base API routes
- `plan_routes.py` — plan load/save/export, "Load Saved Plan", "Start New Plan"
- `workbook_routes.py` — Excel workbook build trigger, build progress polling, Results Explorer API
- `admin_routes.py` — system config, admin UI

`src/server/__init__.py` imports from all route files to register their routes on the local app.

### Data storage and the canonical source hierarchy

Plan data (client facts, income, spending, assets, etc.) has one canonical store and mirrored import/export forms:

1. **`local_state/retirement_system_v10.db`** — SQLite, the **canonical source of truth**. Relevant tables:
   - `client_files` — raw CSV file content verbatim, read by `get_client_file()` / written by `set_client_file()`
2. **`input/client_*.csv`** — on-disk **import/export mirror**, not the canonical read source. Used to bootstrap the DB on a fresh checkout / first run / folder import, and for folder download/portability.
3. **`input/client_*.yaml` and `input/client_*.json`** — derived outputs regenerated by `export_client_json_yaml()`.

`_read_plan_data_file()` reads the DB (`get_client_file`) first and falls back to the on-disk CSV only to bootstrap — when it does, it lazily seeds the DB from that CSV so subsequent reads are DB-canonical. `_write_plan_data_file()` writes the DB first (authoritatively), then the CSV mirror. `client_data.csv` is the sectioned anchor and is intentionally not stored in the DB (always materialized on disk).

**Flat tables (not section/subsection/label format, no YAML counterpart)**: stored only in `client_files` and on disk —
- `client_holdings.csv` — `account, symbol, purchase_date, shares, purchase_price, lot_type`
- `client_liabilities.csv` — auto / HELOC / student-loan debts (amortized into the projection cash flow)
- `client_spending_budget_lines.csv` — per-line spending budget rows (`section, line_id, label, category_id, start_year, end_year, one_time_year, amount_per_year, mode, notes`)

### "Start New Plan" vs "Load Saved Plan"

- **"Start New Plan"** (`start_blank_plan_data` in `workbook_routes.py`, delegated to `PlanDataFileService.start_blank_payload()`): overwrites all `input/client_*.csv` files with blank templates. The individual YAML files (`client_household.yaml`, `client_income.yaml`, etc.) survive and can be used for recovery since they are derived outputs, not inputs.
- **"Load Saved Plan"** (`plan_load_file` in `plan_routes.py`): swaps `local_state/retirement_system_v10.db` with a saved copy. After copying, WAL sidecar files (`-wal`, `-shm`) are removed and a `PRAGMA wal_checkpoint(TRUNCATE)` is issued to prevent stale WAL data from silently rolling back the loaded plan.

### Frontend (`frontend/`)

- `frontend/index.html` + `frontend/js/dashboard.js` — main UI, a single-page app with no build step
- `frontend/js/admin.js` — admin panel
- `frontend/js/pywebview_bridge.js` — intercepts `fetch()` in desktop mode and routes through `window.pywebview.api.request()`
- `frontend/js/spending_dashboard.js` — spending detail sub-view

`dashboard.js` is the largest file (~1670 lines, heavily minified — roughly one statement per line). Key patterns:
- `STEPS` array (top of file) defines the left nav; each step has an `id`, `group`, `title`, and optional custom render function. The nav renders a group header whenever `group` changes, so all steps sharing a group must be contiguous in the array.
- `rows` array holds all plan data fields fetched from `/api/config/rows`
- `renderMain()` dispatches to per-step render functions (`renderIncomeWork`, `renderFieldGroups`, etc.)
- `renderFieldGroups(rs)` re-sorts rows by `sortRowsByDependency()` (dependency rank + label name). Steps needing explicit section order must build their own group map from a pre-sorted array rather than delegating to `renderFieldGroups`.

### Projection and build pipeline

The Excel workbook build is triggered via `/api/build/start` and runs `tools/build_workbook.py` as a subprocess (via `sys.executable`). In the frozen exe, `main.py`'s script-runner mode handles this: any argument ending in `.py` is `runpy.run_path`'d.

`src/projection_pipeline.py` — named pipeline facade  
`src/projection_stages/deterministic_engine.py` — year-by-year deterministic projection  
`src/reporting/workbook_builder.py` — assembles the Excel output  
`src/detailed_results.py` — parses completed Excel for the Results Explorer; `workbook_detailed_index()` prefers the semantic model from `output/results_explorer_model.json` and merges in any additional tabs found by reading the actual Excel file directly.

### Path resolution in the frozen exe

`BASE_DIR = Path(__file__).resolve().parents[2]` in `app_core.py` resolves to `_internal/` (the PyInstaller bundle root), not the exe's parent directory. Writable user data (`input/`, `output/`, `local_state/`) must be resolved relative to `sys._MEIPASS` or the exe path, not `BASE_DIR`, when adding new file I/O in frozen mode.

### Backup naming conventions

`local_state/` accumulates automatic DB copies (kept on the local drive, not OneDrive):
- `retirement_system_v10.db.version_<timestamp>` — created on **Save & Exit** (`/api/plan/exit-snapshot`), last 10 kept
- `retirement_system_v10.db.before_load_<timestamp>` — created before each "Load Saved Plan"
- `retirement_system_v10.db.overlaid_<timestamp>` — created after a plan overlay (e.g. "Start New Plan" on top of existing data)
- `retirement_system_v10.db.before_csv_import_<timestamp>` / `.overwritten_<timestamp>` — created before bulk CSV import / overwrite

Full-project zip backups are written to OneDrive `Retirement Planning/Backups` by `tools/backup_to_onedrive.py` on each `build.py` rebuild. The repo is under git; generated/heavy dirs (`dist/`, `build/`, `output/`, `local_state/`) are listed in `.gitignore` for source-control hygiene.
