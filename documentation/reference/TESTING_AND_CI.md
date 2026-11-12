# Testing and CI

Status: implemented 2026-11-12

How to run the tests locally, which tier to run for which change, and what the real CI runs. This replaces the old `TEST_RUN_GUIDE.md` and `CI_SETUP.md` (the latter described a CI that did not exist). The workflow files are the source of truth: `.github/workflows/ci.yml` (PR gate) and `.github/workflows/nightly.yml` (everything, once a day).

## Setup

```
pip install -r requirements.txt -r requirements-dev.txt
npm ci
```

`scipy` and `keyring` are core runtime requirements (`requirements.txt`), not optional: the solver and efficient-frontier tests need scipy and the secrets-store tests need keyring, so they are never skipped. The dashboard codemod tests and the Playwright suite need `node_modules` (`npm ci`). `pytest` runs from the repo root with no `PYTHONPATH` (`pythonpath` is set in `pyproject.toml`). Node 22 is needed for `node --test` glob patterns.

## Which tier to run

| Change | Minimum before moving on | Also before calling it done |
|---|---|---|
| Iterating on one function or file | Targeted: `pytest tests/test_x.py -v` (or `::test_name`) | Fast tier |
| Any other non-trivial change | Fast tier | none |
| `workbook_builder.py`, `projection_pipeline.py`, anything under `src/reporting/`, or the build/report pipeline | Fast tier | Full suite |
| A golden-master fixture or the frozen sample plan (`tests/fixtures/csv_exchange/sample_plan_frozen/`) | Fast tier | Full suite, after `python tools/regen_golden_master.py measure` (see `GOLDEN_MASTER_RECOVERY_RUNBOOK.md`) |
| Module switches, `module_catalog.py`, or anything the module on/off sweep exercises | Fast tier | Full suite (`test_all_modules_off_build_functional.py` is what catches this) |
| Any change to engine output (new tax, rate or rule) | Fast tier | `pytest tests/test_phase_golden_equality_regression.py -v` (it is `slow`, so PR CI only runs it when engine files changed) |
| About to push | `python tools/fast_gates.py` | Full suite when code changed |

Docs-only changes (everything under `documentation/` or a `.md` file) skip CI entirely: both workflows ignore those paths.

## Commands

| Goal | Command |
|---|---|
| Fast loop | `pytest -m "not slow"` |
| Fast gate (what the PR job runs) | `pytest tests/ -m "not slow and not nightly" -n auto --dist loadfile --max-worker-restart=0 --timeout=300 --timeout-method=thread -q` |
| Full suite (what nightly runs) | `pytest tests/ -n auto --dist loadfile --timeout=600 --timeout-method=thread -q` |
| Single test | `pytest tests/test_x.py::test_name -v` |
| Serial re-run of failures | `pytest tests/ --lf -q` |
| Profile | `pytest tests/ -m "not slow and not nightly" -n 4 --dist loadfile --durations=40 -q` |
| Frontend unit tests | `npm test` (`node --test "tests/frontend/**/*.test.mjs"`) |
| Browser end-to-end | `npx playwright test` |
| Static regression checks | `python tools/run_regression.py` |
| Cheap pre-push gates | `python tools/fast_gates.py` (about two minutes) |

`--dist loadfile` keeps each file on one worker so module-scoped fixtures stay shared. If a failure under `-n auto` is a `PermissionError` or `WinError 5` on a `retirement_system_test_workspace_*` temp path, it is a Windows file-lock flake (antivirus scanning a just-written file); rerun that file without `-n` before treating it as a break.

Run pytest with `-v` and `-rfE`, redirected to a log file, so progress and failures are readable while it runs (long runs go in the background).

### Markers

Defined in `pyproject.toml`. `slow` marks tests that spawn a workbook-build subprocess or request the `built_workbook_dir` / `built_workbook_path` fixtures (one build is about 90 seconds). `nightly` marks engine-internals-only equivalence checks and sweep-breadth checks that an ordinary UI or config change cannot trigger; PR CI excludes it. Also `unit`, `integration`, `golden_master`, `contract`, `e2e` and `requires_live_input` (skips itself when the gitignored `input/` files are absent). Mark a new test `nightly` only when it fits that description; a cheap vectorized-only assertion for the same behavior should stay unmarked.

New tests that build a workbook must be `@pytest.mark.slow`. Prefer the shared `built_workbook_*` fixtures; when a different module configuration is needed, use a `module`-scoped fixture so the build is paid once per file.

### Writing tests

- **Naming:** `tests/test_<succinct_scope>_<type>.py`, where type is one of `regression`, `functional`, `contract`, `smoke`, `unit`, `integration`. A file without a type suffix fails `test_test_file_suffix_shape_functional.py` (a ratchet; never raise `LEGACY_NO_SUFFIX_CEILING`). Never put a tracking id in the name (`test_<N>_`, `test_wave<N>_`, `test_phase<N>_`, `test_item_<N>_`); `test_no_tracking_id_test_names_regression.py` enforces it. To find coverage for a module, grep by module name, for example `grep -l "from src.optimization" tests/*.py`.
- **Do not assert string literals against frontend source text** (`test_freeze_frontend_source_grep`). Use Playwright, the Node vm sandbox (`tests/frontend/load_dashboard.mjs`) or an API response. Some older Python tests read panel JS as text (for example `tests/test_zip_screen_panel_functional.py`); read them before editing panel JS and treat their assertions as an interface contract.
- **Search `tests/` before changing** a route URL, a JS string, an API dict key, a public function, or a workbook sheet name, and update every match in the same change. Sheet names and phrases are pinned in `tests/fixtures/workbook_snapshot_expectations.json`.
- **Share expensive Monte Carlo runs** within a file with a `scope="module"` fixture keyed by what varies (seed), and prefer the session-scoped `mc_sims` / `mc_sensitivity_sims` fixtures to a hardcoded `n_sims`.
- **Fixtures:** `tests/fixtures/golden_master_engine_cases.json` (per-scenario NW, taxes, RMDs, conversions), `tests/fixtures/workbook_snapshot_expectations.json` (sheet names and required phrases) and `tests/fixtures/irs_style_examples.json` (IRS-example tax calculations). When a sheet is renamed, update the fixture and any hardcoded names in test source. Sheet letters (`1A. Executive Summary`) are recomputed per build from `SHEET_REGISTRY` in `src/module_catalog.py`, so never hardcode one.
- **Routes** are `/api/...`, with no version prefix.
- `refresh_api_keys()` re-reads keys from the environment; a test that sets provider keys to `None` must also patch it to a no-op.

### Isolation rules (xdist)

Each xdist worker gets its own throwaway workspace (`tests/conftest.py`), shared by every test that worker runs. A test that mutates the workspace (blanking the plan, activating another plan, rewriting `input/` files) must restore it, or the change leaks into whichever tests the scheduler places next on that worker, producing order-dependent failures. See `_restore_workspace_after_blank_plan` in `tests/test_security_gate_csrf_origin_regression.py` for the pattern.

### Speed notes

Scenario configs from `tests/synthetic_plans.py` are expensive because `Scenario.build()` runs the Roth optimizer. Tests that only read plan inputs the optimizer never touches should call `build(optimize=False)`.

## What CI runs

All jobs run on `windows-latest` with Python 3.14 and Node 22. There is no Linux or macOS job and no Python 3.11 or 3.12 matrix. Both workflows ignore `**/*.md`, `documentation/**` and `docs/**`, so a docs-only change triggers no CI. A newer push to the same ref cancels the in-flight run.

`ci.yml` runs on every push to `main` and every pull request to `main`:

| Job | What it does |
|---|---|
| `fast-gates` | Account-number pattern scan (`tools/check_no_account_numbers.py`), `ruff check src/ tests/`, the source-text-only test files (those importing no `src`, numpy, openpyxl, scipy or matplotlib) with `-m "not slow and not nightly"`, then `tools/run_regression.py`. Reports in well under a minute. `python tools/fast_gates.py` runs the same set locally. |
| `test` | 45-minute limit. mypy (`mypy src/ --ignore-missing-imports`, informational, so not a merge gate). The fast gate command above, with a serial `--lf` retry only when the parallel run failed without a worker crash or timeout. The frozen golden-master pin (`test_frozen_plan_dollar_figures_are_exact`) is then run directly. On pull requests that touch `src/`, `tools/golden_compare.py` or `tests/fixtures/golden_phase_baseline/`, the phase golden-equality test runs with `-m golden_master`. Finally it fails if the suite mutated `input/`. pytest output is uploaded as an artifact when the job fails. |
| `frontend-tests` | `node --test "tests/frontend/**/*.test.mjs"`. |
| `e2e-tests` | Playwright Chromium against the real app (`npx playwright test`; retries are configured). Kept separate so a flaky browser run never muddies the frontend unit signal. |
| `build` | PyInstaller build (`python build.py --no-backup`), a smoke test of the frozen executable (`scripts/pyinstaller_smoke.py`), and a 30-day artifact upload. Runs in parallel with `test`, not after it. |

`nightly.yml` runs daily at 09:00 UTC (and on `workflow_dispatch`): the complete suite including `slow` and `nightly`, with coverage uploaded to Codecov, and the same `input/` mutation check. On failure it opens or comments on a single `nightly-failure` issue.

Coverage is collected only in the nightly run, not on PRs.

### Recurring CI failures and their fixes

Run `python tools/fast_gates.py` before every push; a PreToolUse hook blocks `git push` when it fails. The per-failure rules are in `.claude/CLAUDE.md` ("Recurring CI failures"). In short: new design documents need a `Status:` line; regenerate the architecture diagram after structural changes; the frontend size ratchet is never raised; navigation changes need the `wi015-navigation-baseline` re-recorded; engine-output changes need the phase golden test run locally; Playwright `ERR_NO_BUFFER_SPACE`, "browser has been closed" and single-spec 120-second timeouts are runner noise (re-run once before investigating).

### Troubleshooting

- **Passes locally, fails in CI:** CI is Windows with Python 3.14 and a fresh `npm ci`. Check `python --version` and reinstall both requirement files.
- **Lint differs:** `pip install --upgrade ruff`; the ruleset is in `pyproject.toml` (`[tool.ruff.lint]`).
- **Build fails in CI only:** try `python build.py --no-backup` locally, and check that `requirements.txt` holds every runtime dependency.
- **A hung test:** CI uses `--timeout=300 --timeout-method=thread`; a test that needs longer carries `@pytest.mark.timeout(N)`.
- **Skipping CI:** only docs-only changes skip it, through the path filters above. Do not use `[skip ci]` for code.

## Type checking and linting

`ruff check src/ tests/` is a merge gate in `fast-gates`; `mypy src/ --ignore-missing-imports` is informational (a large backlog, much of it false positives from the `from .app_core import *` pattern; see `[tool.mypy]` in `pyproject.toml`).
