# Contributing

## Setup

```
pip install -r requirements.txt -r requirements-dev.txt
```

`requirements.txt` covers the runtime dependencies; `requirements-dev.txt` adds
`pytest`, `pytest-cov`, `pytest-timeout`, and `ruff` for local development.

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
`documentation/SYSTEM_REVIEW_AND_REFACTOR_PLAN.md` Section 1 if a fresh
clone shows failures beyond what you introduced.

## Linting

```
ruff check .
```

Currently scoped to syntax errors and undefined names (`E9`, `F821`) — see
the comment in `pyproject.toml` for why the broader ruleset isn't a CI gate
yet.

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
- `documentation/` — architecture notes, changelog, and
  `SYSTEM_REVIEW_AND_REFACTOR_PLAN.md` (the current cleanup/refactor plan).

See `documentation/CLAUDE.md` for the fuller architecture and testing-discipline
notes originally written for AI-assisted development sessions — most of it
applies equally to a human contributor.
