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

## Architecture (map)

The maintained description is `documentation/reference/CURRENT_SYSTEM_DESIGN_SPEC.md`; this file keeps only what a session needs to find its way, and the working tips that are not in the spec. When the two disagree, the spec and the code win.

| Topic | Where |
|---|---|
| Launch modes (desktop PyWebView with no HTTP, server mode on port 5050), request lifecycle | design spec section 3.1, 3.2 |
| Local route registry (`src/server/`, five route files, `route_manifest.py`) and services | design spec sections 3.3, 3.4 |
| Workspace, paths and the frozen exe (`BASE_DIR` is `_internal/`; user data resolves from the exe path or `sys._MEIPASS`, never `BASE_DIR`) | design spec section 3.5 |
| Where plan data lives: `plan.rpx`, `local_state/app.db`, the legacy database, `input/` | design spec section 4.1 |
| Row model, writers, CSV exchange, switch and tier rows | design spec section 4.6 |
| Save As, Load Saved Plan, Start New Plan, backups and their naming | design spec section 4.3 |
| Build pipeline and outputs | design spec sections 5 and 8 |
| Frontend structure, render hooks, navigation | design spec section 7 |
| One-time conversion of an old install | `LEGACY_CONVERSION.md` |

### Rules that bite

- **Plan data is plan rows.** The sectioned plan data and the flat datasets are tables of `plan.rpx`. There is no CSV, JSON or YAML copy to resync after a schema change; CSV is only `src/csv_exchange` import and export. Readers use `active_plan_data()` / `load_active_config()`; writers edit through `active_plan.edit_active_plan()`.
- **Start New Plan vs Load Saved Plan.** Start New Plan (`start_blank_plan` in `workbook_routes.py`) backs up the plan file and clears household facts in the rows (policy and settings sections and curated defaults keep their values). Load Saved Plan (`plan_load_file` in `plan_routes.py`) registers and activates the chosen `.rpx` without copying; `mode: "restore"` replaces `plan.rpx` instead. A saved `.rpx` is the whole plan file, flat datasets included.
- **Local server.** Routes are decorator side effects in the five files under `src/server/`, sharing one namespace through `from .app_core import *`. `route_manifest.py` is documentation only.
- **Writable data in the frozen exe** is resolved from the exe path, not `BASE_DIR`.
- **Backups** the app writes stay on the local drive (`plan.rpx.version_<ts>`, `before_load_`, `before_snapshot_restore_`, `before_blank_`); full-project zips go to OneDrive through `tools/backup_to_onedrive.py` on each `build.py` rebuild. `dist/`, `build/`, `output/` and `local_state/` are gitignored.

### Frontend working tips (`frontend/`)

`dashboard.js` is the central frontend file (several thousand lines, readable source, split further across the `dashboard_decomp_*.js` files beside it; check the current size with `wc -l`, and read it by Grep, not linearly). Key patterns:

- The `STEPS` array (top of the file) defines the left nav; each step has an `id`, `group`, `title`, and optional custom render function. The nav renders a group header whenever `group` changes, so all steps sharing a group must be contiguous in the array.
- The `rows` array holds all plan data fields fetched from `/api/config/rows`.
- `renderMain()` dispatches to per-step render functions (`renderIncomeWork`, `renderFieldGroups`, etc.).
- `renderFieldGroups(rs)` re-sorts rows by `sortRowsByDependency()` (dependency rank + label name). Steps needing explicit section order must build their own group map from a pre-sorted array rather than delegating to `renderFieldGroups`.

### Projection and build pipeline

The Excel workbook build is triggered via `/api/build/start` and runs `tools/build_workbook.py` as a subprocess (via `sys.executable`). In the frozen exe, `main.py`'s script-runner mode handles this: any argument ending in `.py` is `runpy.run_path`'d.

- `src/projection_pipeline.py`: named pipeline facade.
- `src/projection_stages/deterministic_engine.py`: year-by-year deterministic projection.
- `src/reporting/workbook_builder.py`: assembles the Excel output.
- `src/detailed_results.py`: parses the completed Excel for the Results Explorer; `workbook_detailed_index()` prefers the semantic model stored in the build's `build_results` row (`explorer`) and merges in any additional tabs found by reading the Excel file directly.
