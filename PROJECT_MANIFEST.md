# Retirement Planning v10 Project Manifest

Generated: 2026-07-18

Map of what lives at the repository root and why. Every root entry below is
directly referenced by runtime code, launchers, packaging, or tests — anything
that is not stays out of the root.

## Root Files

- `.gitattributes` - line-ending and diff attributes.
- `.gitignore` - repository ignore rules.
- `build.py` - PyInstaller build entrypoint; retained at root because launchers and package docs call `python build.py`.
- `conftest.py` - pytest fixtures and path setup; must sit at the rootdir pytest resolves.
- `CONTRIBUTING.md` - contribution and review workflow.
- `main.py` - desktop/server application entrypoint; retained at root because the PyInstaller spec and user docs call it directly.
- `package.json` - Node toolchain for the frontend test runner.
- `PROJECT_MANIFEST.md` - this file.
- `pyproject.toml` - build metadata plus ruff/mypy/pytest configuration.
- `requirements.txt` / `requirements-dev.txt` - runtime and development dependency lists; retained at root for packaging/test contracts.
- `retirement_planner.spec` - PyInstaller package specification for direct `pyinstaller retirement_planner.spec` builds.
- `system_config.csv` - local runtime/system configuration; retained at root because runtime loaders, tests, and admin UI contracts use this canonical path.

## Root Directories

- `.claude/` - local assistant metadata, skills, and workflows.
- `.github/` - CI workflow definitions.
- `android/` - Android shell wrapper around the local UI.
- `data/` - desktop runtime preferences and webview profile data.
- `documentation/` - project documentation, API contracts, changelog, and design notes. Superseded plans live in `documentation/archive/`.
- `frontend/` - browser UI assets.
- `input/` - canonical local Plan Data files and `plan_data_manifest.json`.
- `launchers/` - thin desktop entry scripts that delegate to `tools/launchers/`.
- `local_state/` - local SQLite/runtime state.
- `output/` - generated workbook, dashboard, summaries, build snapshots, report package manifests, and report artifacts.
- `reference_data/` - static reference assumptions and lookup data.
- `saved_plans/` - persisted user plan snapshots.
- `src/` - Python application, projection, server, and reporting code.
- `tests/` - pytest regression and behavior coverage.
- `tools/` - developer and maintenance scripts, including `run_regression.py` and `launchers/`.

## Documentation Layout

- `documentation/` - active references: `CLAUDE.md`, `API_CONTRACTS.md`,
  `CURRENT_SYSTEM_DESIGN_SPEC.md`, `GOLDEN_MASTER_CHANGELOG.md`, runbooks, and
  in-flight plans.
- `documentation/archive/` - completed or superseded plans and roadmaps, kept
  for history. Nothing here describes current behavior.
- `documentation/readme/` - packaged-release READMEs shipped to end users.
- `documentation/release_notes/` - per-release notes.

## Common Commands

- Build workbook/report artifacts: `python tools/build_workbook.py`
- Run targeted tests: `python -m pytest tests --tb=short -q`
- Run curated regression checks: `python tools/run_regression.py`
- Build desktop package: `python build.py`
- Refresh Plan Data manifest: `python tools/check_plan_data_sync.py --write`

## Notes

Generated folders (`build/`, `dist/`, `__pycache__/`, `.pytest_cache/`,
`.mypy_cache/`, `.ruff_cache/`) and coverage artifacts (`.coverage`,
`coverage.xml`) are gitignored and recreated by normal build/test commands; they
can be deleted at any time to reclaim disk. Workspace user/runtime folders
(`input/`, `local_state/`, `saved_plans/`, `data/`, `output/`) are preserved
locally but excluded from clean release zips, along with `.claude/`. Successful
report builds write `output/build_snapshot.json` with output fingerprints/build
metadata and `output/report_package.json` as the canonical advisor package
manifest.
