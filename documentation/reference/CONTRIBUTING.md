# Contributing

## Setup

```
pip install -r requirements.txt -r requirements-dev.txt
```

`requirements.txt` covers the runtime dependencies; `requirements-dev.txt` adds
`pytest`, `pytest-cov`, `pytest-timeout`, `ruff`, and `mypy` for local development.

## Running the app

```
python main.py                # desktop mode (PyWebView native window)
python main.py --mode server  # browser/server mode, stdlib HTTP on port 5050
```

## Running tests

```
pytest tests/                 # full suite (also runs from repo root with no PYTHONPATH needed)
pytest -m "not slow"          # skip the build-pipeline smoke test for a faster loop
pytest tests/test_x.py -k name  # a single test
```

Run the full suite after any non-trivial change and resolve every new
failure before considering a change complete. A handful of pre-existing
failures are environment-specific (missing optional `lxml`, a stale Plan
Data manifest checksum, and one tax-aware-rebalance edge case) — see
`documentation/archive/legacy/SYSTEM_REVIEW_AND_REFACTOR_PLAN.md` Section 1 if a fresh
clone shows failures beyond what you introduced.

## Running frontend JS tests

```
node --test "tests/frontend/**/*.test.mjs"
```

Requires Node 18+ (built-in test runner, no new dependency). Coverage is
currently limited to the pure/stateless helper functions in
`frontend/js/dashboard.js` — see `tests/frontend/load_dashboard.mjs` for why
(most of the file's ~810 functions are tightly coupled to shared UI state and
aren't yet safely unit-testable in isolation).

## Linting

```
ruff check .
```

Currently scoped to syntax errors and undefined names (`E9`, `F821`) — see
the comment in `pyproject.toml` for why the broader ruleset isn't a CI gate
yet.

## Type checking

```
mypy src/ --ignore-missing-imports
```

Runs in CI informationally (doesn't fail the build yet) — there's a ~264-error
pre-existing backlog, over a third of it false positives from this codebase's
`from .app_core import *` wildcard-import pattern. See the comment in
`pyproject.toml`'s `[tool.mypy]` section for the breakdown.

## Building the desktop package

```
python build.py            # PyInstaller build + local backup
python build.py --no-backup  # build only, skip the backup step
```

## Where things live

- `src/` — application, projection engine, and reporting code.
- `frontend/` — the browser UI (vanilla JS/CSS, no bundler). This is the
  single source of truth; `output/js`, `output/css`, and `output/index.html`
  are generated copies for offline workbook bundles and are gitignored.
- `tests/` — pytest suite. Files are numbered by the feature/patch that
  added them rather than by module under test; grep by module name to find
  related coverage (e.g. `grep -l "from src.optimization" tests/*.py`).
- `tools/` — build, packaging, and maintenance scripts. `tools/build_workbook.py`
  is the CLI entry point for generating the workbook/report artifacts.
- `documentation/` — three tiers, see "Documentation layout" below; start
  from `documentation/DOCUMENTATION_INDEX.md`.

See `documentation/reference/CLAUDE.md` for the fuller architecture and testing-discipline
notes originally written for AI-assisted development sessions — most of it
applies equally to a human contributor.

## Documentation layout

All documentation lives under `documentation/` (commit 88f6559 consolidated the
former `docs/` tree into it). There are three tiers, chosen by what the
document *is*, not by when it was written:

| Tier | Holds | Rule |
|---|---|---|
| `documentation/reference/` | Living documents that describe the system as it is today: README, runbooks, functional/design specs, API contracts, this file, changelogs. | Must be kept true. If code changes behavior a reference doc describes, update the doc in the same change. Nothing historical, no prompts, no one-off reports. |
| `documentation/future/` | Plans and specs for work that is not yet implemented (`future/superpowers/{plans,specs}`). | Move the file to `archive/` when the work ships, and record what shipped. |
| `documentation/archive/` | Implemented, superseded or obsolete material, including dated system reviews (`archive/reports/`), shipped specs/plans (`archive/superpowers/`) and legacy notes (`archive/legacy/`). | Never cited as "current". Do not edit except to fix links. |

Do not create new files under a top-level `docs/` directory. `docs/superpowers/`
reappeared after the consolidation and still holds some specs and plans; treat
it as a legacy location: new specs and plans go to `documentation/future/`,
and existing ones move to `documentation/archive/` when their work ships. The
index of what lives where is `documentation/DOCUMENTATION_INDEX.md`.

When you move or rename a document, grep the repository for its old path
(code comments, tests, tools and other docs cite paths); a test
(`tests/test_documentation_path_citations_regression.py`) fails on a citation
of a documentation path that does not exist.
