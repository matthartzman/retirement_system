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
pytest -m "not slow"            # fast loop
pytest tests/test_x.py -k name  # a single test
npm test                        # frontend JS unit tests (Node 22)
python tools/fast_gates.py      # cheap CI gates, before every push
```

Which tier to run for which change, the markers, the test naming rules, and
what CI actually runs (Windows, Python 3.14, fast gate plus nightly) are in
`documentation/reference/TESTING_AND_CI.md`. Run the fast tier after any
non-trivial change and resolve every new failure before calling it done.
`tests/frontend/load_dashboard.mjs` explains why frontend unit coverage is
limited to the helpers that can be loaded in a vm sandbox.

## Linting and type checking

```
ruff check src/ tests/
mypy src/ --ignore-missing-imports
```

Ruff is a merge gate and mypy is informational; the rules and the reasons are
in `pyproject.toml` (`[tool.ruff.lint]`, `[tool.mypy]`).

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
- `tests/` — pytest suite. Files are named `test_<scope>_<type>.py` (naming
  rules in `TESTING_AND_CI.md`); grep by module name to find related coverage
  (e.g. `grep -l "from src.optimization" tests/*.py`).
- `tools/` — build, packaging, and maintenance scripts. `tools/build_workbook.py`
  is the CLI entry point for generating the workbook/report artifacts.
- `documentation/` — three tiers, see "Documentation layout" below; start
  from `documentation/DOCUMENTATION_INDEX.md`.

See `documentation/reference/CLAUDE.md` for the fuller architecture notes
originally written for AI-assisted development sessions — most of it applies
equally to a human contributor.

## Documentation layout

All documentation lives under `documentation/` (commit 88f6559 consolidated the
former `docs/` tree into it). There are three tiers, chosen by what the
document *is*, not by when it was written:

| Tier | Holds | Rule |
|---|---|---|
| `documentation/reference/` | Living documents that describe the system as it is today: runbooks, functional/design specs, API contracts, this file, changelogs. | Must be kept true. If code changes behavior a reference doc describes, update the doc in the same change. Nothing historical, no prompts, no one-off reports. |
| `documentation/future/` | Plans and specs for work that is not yet implemented (`future/superpowers/{plans,specs}`). | Move the file to `archive/` when the work ships, and record what shipped. |
| `documentation/archive/` | Implemented, superseded or obsolete material, including dated system reviews (`archive/reports/`), shipped specs/plans (`archive/superpowers/`) and legacy notes (`archive/legacy/`). | Never cited as "current". Do not edit except to fix links. |

Do not create new files under a top-level `docs/` directory
(`tests/test_documentation_status_and_layout_regression.py` fails if any tracked
file is there). New specs and plans go to `documentation/future/`, and move to
`documentation/archive/` when their work ships. Each carries a first-lines
`Status: draft|approved|implemented|superseded|planned` line, which the same test checks. The
index of what lives where is `documentation/DOCUMENTATION_INDEX.md`.

When you move or rename a document, grep the repository for its old path
(code comments, tests, tools and other docs cite paths); a test
(`tests/test_documentation_path_citations_regression.py`) fails on a citation
of a documentation path that does not exist.
