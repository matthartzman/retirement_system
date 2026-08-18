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
pytest tests/test_v11_architecture_regression.py          # single test file
pytest tests/test_v11_architecture_regression.py::test_name  # single test
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

Match the test tier to the size of the change. Do not mark any task complete without running at least the fast tier and resolving every new failure — this is not optional, the cost of a broken suite compounds quickly and catching failures immediately is cheap. Use the table to decide whether the fast tier is enough or you need to go further.

### What level of change needs what level of testing

| Change | Minimum tier before moving on | Also run before calling the task done |
|---|---|---|
| Iterating on one function/file, not yet finished | Targeted: `pytest tests/test_the_one_file.py -q` | Fast tier |
| Any other non-trivial change (the default case) | Fast tier | — |
| Touched `workbook_builder.py`, `projection_pipeline.py`, anything under `src/reporting/`, or the build/report pipeline | Fast tier | Full suite |
| Touched a golden-master fixture or `input/client_data.csv` | Fast tier | Full suite (regenerate expected values first — see Golden master maintenance below) |
| Changed `client_optional_functions.csv` module gating, `module_catalog.py`, or anything the module on/off sweep exercises | Fast tier | Full suite (this is what `test_all_modules_off_build_functional.py` exists to catch) |
| About to push / open a PR | — | Full suite (CI reruns it on every push regardless, but a red CI run is more expensive to debug than a local one) |

**Targeted tier** — while actively iterating on a single function or file, run just that file (or `::test_name` for one test). Seconds, not minutes. Do this as often as you like; it does not replace the fast tier before moving on.

**Fast tier** — the default for "did I break anything nearby":

```
pytest tests/ -m "not slow" --tb=short -q
```

This excludes tests marked `@pytest.mark.slow` — tests that spawn a subprocess to run a full workbook build (`tools/build_workbook.py`) or that request the `built_workbook_dir`/`built_workbook_path` fixtures in `conftest.py`, which trigger one on first use. It's the large majority of the suite and normally finishes in well under a minute; a single workbook build alone costs ~90 seconds, so one unmarked build test can silently dominate the whole run.

**Full suite** — before considering a task done (not after every edit) per the table above, or before pushing. Run it with `pytest-xdist` (`pip install -r requirements-dev.txt` picks it up) so the ~20+ independent build-subprocess tests in `test_all_modules_off_build_functional.py` (one real workbook build per registered optional module, ~90s each) run concurrently instead of serially — that sweep alone was the dominant cost of a full run, previously 30+ minutes end to end:

```
pytest tests/ -n auto --tb=short -q
```

If a failure under `-n auto` is a `PermissionError`/`WinError 5` touching a `retirement_system_test_workspace_*` temp path, that's a Windows file-lock flake (antivirus scanning a just-written temp file), not a real regression — rerun that one file without `-n` to confirm before treating it as a break:

```
pytest tests/ --tb=short -q   # no -n: serial fallback if a run looks flaky, or on a machine without pytest-xdist
```

**New tests that spawn a subprocess to build a workbook must be marked `@pytest.mark.slow`.** Prefer the shared `built_workbook_dir`/`built_workbook_path` fixtures over a bespoke `subprocess.run` when your test can use the same module/env configuration those fixtures already build with — that amortizes to one build per session instead of one per test. When your test genuinely needs a different module configuration (e.g. all-modules-off, a custom `RETIREMENT_SYSTEM_FORCE_DISABLE_MODULES` set), a fixture-shared build isn't safe to force — scope your own build to a `module`-or-narrower fixture so it's still paid for once per file, not once per test, and mark it `slow` regardless.

### Test file naming

`test_<succinct_scope>_<type>.py` — the name alone should say what it covers, not which roadmap item/wave/issue shipped it (that belongs in the docstring and git history, both of which survive; a "wave 5.6" or "item 172" reference in a filename does not mean anything once the roadmap moves on). `type` is one of `regression`, `functional`, `contract`, `smoke`, `unit`, `integration`. `tests/test_no_tracking_id_test_names_regression.py` enforces the "no wave/issue/phase number in the name" half of this mechanically; the type-suffix half is a convention to follow for new files, not separately enforced.

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

Absolute projection dollars for the frozen household are pinned in **one** place:
`tests/test_frozen_sample_plan_golden_master_regression.py` (`PINNED_TERMINAL_NW`,
`PINNED_LIFETIME_TAX`). Per-scenario metrics live in
`tests/fixtures/golden_master_engine_cases.json`. Regenerate only when a
golden-master fixture or an engine constant deliberately changed:

```
python -m tests.test_frozen_sample_plan_golden_master_regression
```

That file's `__main__` block prints the new constants, computed the same way the
test asserts them, and it is self-contained — `_frozen_config()` stages the whole
fixture directory through `RETIREMENT_SYSTEM_WORKSPACE_ROOT` and pins the clock,
so it does not depend on pytest's conftest. Use `-m`: running it as a path
(`python tests/test_..._regression.py`) puts `tests/` on `sys.path` instead of the
repo root and dies with `ModuleNotFoundError: No module named 'src'`.

**Do not regenerate these figures by pointing a script at `input/client_data.csv`.**
That path is the live plan — `/input/*` is gitignored real client data, so it is
absent on CI and in any fresh worktree, and on a developer machine it is whatever
household was last saved. The tests do not read it: `tests/conftest.py` stages
`input/` from the committed `tests/fixtures/sample_plan_frozen/` and pins the
clock via `RETIREMENT_SYSTEM_FROZEN_TODAY`. A regen snippet reading the live path
produces figures for the wrong household, which is exactly how these pins were
wrong twice — see the 2026-08-10 and 2026-08-12 entries in
`documentation/GOLDEN_MASTER_CHANGELOG.md`.

Because the fixture, the clock and the holdings prices are all frozen, a move in
these dollars is an **engine change**, never routine data drift. Investigate
before re-pinning: compute the figures at the commit that set the pin and at a
few commits since (the test's `__main__` block works at any commit). Identical
values across commits mean the pin was wrong, not the engine. Re-pin only once
you can name the change that moved them, and add a changelog entry saying what.

**Full recovery process (decision tree, tooling, and the two method traps that
previously produced a confidently wrong answer):** see
`documentation/GOLDEN_MASTER_RECOVERY_RUNBOOK.md`. Regenerate pins ONLY via
`py -3.14 tools/regen_golden_master.py regen --reason <file>` — hand-editing
`PINNED_TERMINAL_NW`/`PINNED_LIFETIME_TAX` directly is caught by the
test-enforced provenance gate, `tests/test_golden_master_pin_provenance.py`,
which fails the suite if the pin and its provenance comment disagree.

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

`dashboard.js` is the largest file (~16,700 lines, heavily minified — roughly one statement per line). Key patterns:
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
