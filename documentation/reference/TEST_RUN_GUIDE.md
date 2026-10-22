# Running the test suite

Status: implemented 2026-10-22

How to run pytest locally and what CI runs. CI wiring lives in `.github/workflows/ci.yml` (PR gate) and `nightly.yml` (everything).

## Setup

```
pip install -r requirements.txt -r requirements-dev.txt
npm ci
```

`scipy` and `keyring` are core runtime requirements (`requirements.txt`), not optional: the solver / efficient-frontier tests need scipy and the secrets-store tests need keyring, so they are never skipped. A bare container without them fails those tests; installing the requirements fixes it. The dashboard codemod tests also need `node_modules` (`npm ci`).

## Commands

| Goal | Command |
|---|---|
| Fast gate (what the PR job runs) | `pytest tests/ -m "not slow and not nightly" -n auto --dist loadfile --timeout=300 --timeout-method=thread -q` |
| Full suite (nightly) | `pytest tests/ -n auto --dist loadfile --timeout=600 --timeout-method=thread -q` |
| Serial re-run of failures | `pytest tests/ --lf -q` |
| Profile | `pytest tests/ -m "not slow and not nightly" -n 4 --dist loadfile --durations=40 -q` |

`--dist loadfile` keeps each file on one worker so module-scoped fixtures stay shared.

## Isolation rules (xdist)

Each xdist worker gets its own throwaway workspace (`tests/conftest.py`), shared by every test that worker runs. A test that mutates the workspace (blanking the plan, activating another plan, rewriting `input/` files) must restore it, or the change leaks into whichever tests the scheduler places next on that worker, producing order-dependent failures. See `_restore_workspace_after_blank_plan` in `tests/test_security_gate_csrf_origin_regression.py` for the pattern.

## Speed notes

Scenario configs from `tests/synthetic_plans.py` are expensive because `Scenario.build()` runs the Roth optimizer. Tests that only read plan inputs the optimizer never touches should call `build(optimize=False)`.
