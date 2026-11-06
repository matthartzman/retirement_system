## Triage & Subagent Routing
- When a prompt is prefixed with `[SYSTEM DIRECTIVE: AUTOMATED TRIAGE ENFORCED]`, pass the evaluation task to `@triage-evaluator`.
- Do not attempt direct file edits until the `triage-evaluator` summary has been output and confirmed.

## Design Specs & Implementation Plans
- For each phase/step/task of an implementation plan:
    - Include recommended model and effort
    - Estimate expected Claude Code usage:
        - approximate tokens needed, 
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
first. See `documentation/reference/GOLDEN_MASTER_RECOVERY_RUNBOOK.md`.
## System Architecture Diagram — regenerate on every structural change
After adding, moving, renaming or deleting any file under `src/` or `frontend/`, changing imports between modules, or editing `module_catalog.py` / `route_manifest.py`, run `python tools/generate_system_diagram.py` and commit `documentation/reference/SYSTEM_ARCHITECTURE_DIAGRAM.md` in the same PR. CI (`tests/test_system_architecture_diagram_freshness_regression.py`) fails otherwise.

## Docs-only changes — never wait on CI
When every changed file is under `documentation/` or is a `.md` file, push and open the draft PR, then move on: do not wait for, poll, or re-run CI. Merge only when the user asks. If any code, test or tool file is also changed, CI applies as normal.

## Recurring CI failures — run `python tools/fast_gates.py` before every push
A review of 40 failed CI runs (2026-10-22 to 11-05) found the same few cheap checks failing again and again. A PreToolUse hook (`.claude/hooks/pre_push_fast_gates.py`) now blocks `git push` when `tools/fast_gates.py` fails; run it yourself after any structural edit. Per-failure rules:
- **`test_design_documents_declare_a_status`** — every new `.md` under `documentation/future/` (and dated specs/plans under `documentation/archive/superpowers/`) needs `Status: draft|approved|implemented|superseded|planned` in its first 20 lines. Add it when you create the file, including superpowers spec/plan files.
- **`test_system_architecture_diagram_freshness`** — see the diagram section above; regenerate and stage the diagram in the same commit.
- **`test_frontend_size_ratchet`** — `frontend/js` has a total line ceiling. Adding UI means moving or deleting lines elsewhere, or lowering the ceiling after real extraction. Never raise it to pass. Check `wc -l` on `frontend/js/*.js` before and after.
- **`test_freeze_frontend_source_grep`** — new tests must not assert string literals against frontend source text. Use Playwright, the Node vm sandbox (`tests/frontend/load_dashboard.mjs`), or an API response.
- **`test_no_data_file_io_enforcing`** — plan data goes through the store layer; no new direct data-file I/O outside the allowlist.
- **`wi015-navigation-baseline` (e2e)** — adding, removing or renaming a nav step changes the baseline. Re-record with `WI015_RECORD=1 npx playwright test tests/e2e/wi015-navigation-baseline.spec.js` and commit the JSON.
- **Phase golden drift (`test_phase_golden_equality_regression`, nightly only)** — it is `slow`, so PR CI never runs it and engine-output changes slip through to the nightly. After any change to engine output (new tax, rate or rule), run `pytest tests/test_phase_golden_equality_regression.py -v` locally. If the change is intentional, hand-verify one delta, then `python tools/golden_compare.py record --reason "..."`.
- **Playwright e2e flakes** — `ERR_NO_BUFFER_SPACE`, "browser has been closed" and 120s timeouts on a single spec are runner noise (retries=2 already). Don't change product code for them; re-run once, and only investigate if the same spec fails on two runs.

## File naming conventions (enforced by tests)
- **Test files:** `tests/test_<succinct_scope>_<type>.py`, where type is one of `regression`, `functional`, `contract`, `smoke`, `unit`, `integration`. A file with no type suffix fails `test_test_file_suffix_shape_functional.py` (a ratchet — never raise `LEGACY_NO_SUFFIX_CEILING`).
- **Never encode a tracking id in a test file name:** no `test_<N>_`, `test_wave<N>_`, `test_phase<N>_`, `test_item_<N>_` (`test_no_tracking_id_test_names_regression.py`). Name by what it covers, not which roadmap item shipped it.
- **Specs and plans:** `documentation/future/...` or `documentation/archive/superpowers/{specs,plans}/YYYY-MM-DD-<topic>-{design,plan}.md`, with a `Status:` line in the first 20 lines.
- Don't misspell a name to match source data (e.g. `withdrawl`) — name the file for the concept; the misspelling belongs only in test inputs.

## Script-written files — escaping and line endings
Ad-hoc scripts (heredocs, `python -c`, PowerShell here-strings) have repeatedly produced a literal backspace (0x08) where a regex `\b` belonged, and files with mixed or wrong line endings. `tools/check_text_hygiene.py` (run by `fast_gates.py`, CI via `tests/test_text_hygiene_regression.py`, and after every Write/Edit by `.claude/hooks/post_edit_text_hygiene.py`) now flags both. To avoid them:
- **Prefer the Edit/Write tools** over scripts that rewrite files.
- **Regexes are raw strings** (`r"\bword\b"`). In a plain Python string `"\b"` is a backspace, and `"\d"`/`"\s"` only work by accident. In JS use regex literals, not `new RegExp("\b...")` built through a shell.
- **Quote heredocs** (`<<'EOF'`) so the shell doesn't touch backslashes; in PowerShell use single-quoted here-strings (`@'...'@`).
- **Preserve line endings.** The repo stores LF; this Windows checkout is CRLF via `core.autocrlf`. Scripts must read and write with `newline=''` (or in binary mode) and keep the file's existing ending, never mix. Don't hand-convert a file to CRLF.
- If the hook reports a finding, fix the file before doing anything else.
