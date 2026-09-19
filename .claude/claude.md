## Triage & Subagent Routing
- When a prompt is prefixed with `[SYSTEM DIRECTIVE: AUTOMATED TRIAGE ENFORCED]`, pass the evaluation task to `@triage-evaluator`.
- Do not attempt direct file edits until the `triage-evaluator` summary has been output and confirmed.

## Design Specs & Implementation Plans
- For each phase/step/task of an implementation plan:
    - Include recommended model and effort
    - Estimate expected Claude Code usage:
        - approximate number of tool-use turns, 
        - what's driving context size (file sizes, search scope, test-loop iterations), and 
        - whether it's light/moderate/heavy relative to a 5-hour session on my ProPlan.
- Flag any step likely to be disproportionately expensive (broad searches, large file reads, repeated test-fix cycles) and suggest ways to scope it down. 
- Give relative estimates, not fabricated token count. Include a note to check /usage against these estimates as the plan executes.

## Reading Large Files — never open these linearly
Verified line counts. Reading one of these whole can cost more context than the
entire task warrants. Locate first with Grep, then Read with `offset`/`limit`.

| File | Lines | How to enter it |
|---|---|---|
| `frontend/js/dashboard.js` | 7,287 | Grep the function name. `renderOptionalFunctions()` is ~35 lines of it. |
| `frontend/js/dashboard_decomp_row_model.js` | 5,188 | Grep only. Never read whole. |
| `frontend/js/dashboard_decomp_housing_optimizer.js` | 1,984 | Grep the panel/render function. |
| `frontend/js/dashboard_decomp_housing_scenarios.js` | 1,397 | Read only the `estimateHousingFromState` region. |
| `src/reporting/workbook_builder.py` | 1,443 | Grep the builder or merge function. |
| `src/reporting/workbook_common.py` | 1,161 | Grep the table/rename function. |
| `src/module_catalog.py` | 916 | Readable whole when the task is catalog-wide; otherwise grep the module key. |

`src/housing/*` (`screen.py` 402, `api.py` 498, `plan_variant.py` 243) are small
and readable whole.

## Test Commands
- Python fast loop: `pytest -m "not slow"` (repo root; `pythonpath` is configured)
- Python single test: `pytest tests/test_x.py::test_name -v`
- Full suite incl. subprocess build tests: `pytest`
- Frontend: `npm test` (`node --test tests/frontend/**/*.test.mjs`)
- Some Python tests assert on **panel JS read as text** (e.g.
  `tests/test_zip_screen_panel_functional.py`). Read those before editing panel
  JS and treat their assertions as an interface contract.

## Golden Masters — measure before you regenerate
`tools/regen_golden_master.py` has subcommands; use them in this order:
- `measure` — prints computed values and delta vs. pins. **Always run this first.**
- `origin` — `git log -S<value>` on the pin file, to find where a value came from.
- `verify-endpoint <sha>` — checks whether a pin held at that commit.
- `regen --reason "..."` — rewrites pins and appends to the changelog. Last resort.

Never enter a regenerate-run-regenerate loop: at scale a wrong rate is
indistinguishable from a right one. Verify one representative delta by hand
first. See `documentation/GOLDEN_MASTER_RECOVERY_RUNBOOK.md`.