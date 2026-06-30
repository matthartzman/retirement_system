# Retirement Planning v10 Project Manifest

Generated: 2026-06-29

Verification: `python -m pytest` passed 550 tests on 2026-06-29 after the
Phase 1-4 roadmap continuation, workbook/report rebuild, manifest refresh, and
service-extraction compatibility cleanup.

## Root Files

- `.gitignore` - repository ignore rules.
- `build.py` - PyInstaller build entrypoint; retained at root because launchers and package docs call `python build.py`.
- `main.py` - desktop/server application entrypoint; retained at root because the PyInstaller spec and user docs call it directly.
- `PROJECT_MANIFEST.md` - current project map and cleanup notes.
- `requirements.txt` - Python dependency list; retained at root for packaging/test contracts.
- `retirement_planner.spec` - PyInstaller package specification; retained at root for direct `pyinstaller retirement_planner.spec` builds.
- `system_config.csv` - local runtime/system configuration; retained at root because runtime loaders, tests, and admin UI contracts use this canonical path.

## Root Directories

- `.claude/` - local Codex/assistant metadata.
- `data/` - desktop runtime preferences and webview profile data.
- `documentation/` - project documentation, API contracts, changelog, design notes, and archived assistant instructions.
- `frontend/` - browser UI assets.
- `input/` - canonical local Plan Data files and `plan_data_manifest.json`.
- `launchers/` - desktop launcher support.
- `local_state/` - local SQLite/runtime state.
- `output/` - generated workbook, dashboard, summaries, build snapshots, report package manifests, and report artifacts.
- `reference_data/` - static reference assumptions and lookup data.
- `saved_plans/` - persisted user plan snapshots.
- `src/` - Python application, projection, server, and reporting code.
- `tests/` - pytest regression and behavior coverage.
- `tools/` - developer and maintenance scripts, including `run_regression.py`.

## Cleaned From Root

- Removed legacy `CHANGE_MANIFEST*.md` patch logs.
- Removed legacy `README_APPLY_OVERLAY*.txt` overlay instructions.
- Moved `CLAUDE.md` to `documentation/CLAUDE.md`.
- Moved `run_regression.py` to `tools/run_regression.py`.
- Removed transient/generated folders: `__pycache__/`, `.pytest_cache/`, `build/`, and `dist/`.
- Removed legacy duplicate/recovery folders: `Version 10/` and `_recovery_local_state_20260621_182858/`.
- Retained only active root entry/config/package files that are directly referenced by runtime code, launchers, documentation, or tests.

## Recent Roadmap Continuation

- Planning Workbench and report package routes are covered by Phase 1-4 tests.
- Report, config, pricing, housing, portfolio, security, spending, holdings, and Plan Data route adapters now delegate to service modules.
- `tools/build_workbook.py` no longer depends on optional/nonexistent HTML builder or Results Explorer model paths; it writes current workbook, dashboard, results model, build snapshot, plan summary, and report package artifacts.
- Workbook layout generation now applies final width/wrap optimization before save and includes cached allocation pie chart label/value points.
- Current golden-master expectations match the synchronized canonical Plan Data.
- `input/plan_data_manifest.json` was refreshed from the current canonical Plan Data.
- Clean release packages now exclude local user/runtime state folders: `.claude/`, `data/`, `input/`, `local_state/`, `output/`, and `saved_plans/`.

## Common Commands

- Build workbook/report artifacts: `python tools/build_workbook.py`
- Run targeted tests: `python -m pytest tests --tb=short -q`
- Run curated regression checks: `python tools/run_regression.py`
- Build desktop package: `python build.py`
- Refresh Plan Data manifest: `python tools/check_plan_data_sync.py --write`

## Notes

Generated folders such as `build/`, `dist/`, `__pycache__/`, and `.pytest_cache/` are intentionally absent from the cleaned root and can be recreated by normal build/test commands. Workspace user/runtime folders (`input/`, `local_state/`, `saved_plans/`, `data/`, and `output/`) are preserved locally but excluded from clean release zips. Successful report builds now include `output/build_snapshot.json` with output fingerprints/build metadata and `output/report_package.json` as the canonical advisor package manifest.
