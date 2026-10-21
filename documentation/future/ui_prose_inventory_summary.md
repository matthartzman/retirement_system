Status: draft (Phase 0 measured 2026-10-21; class column is an automated guess awaiting human review).

# UI prose inventory: Phase 0 summary

Source: `python tools/extract_ui_prose.py --coupled-tests` -> `ui_prose_inventory.csv` (551 rows). Plan: `Contextual Help Panel Design and Implementation plan.md`.

## Measured counts (level x class guess)

| Level | A move to panel | B state | C warn | D duplicate | Total |
|---|---|---|---|---|---|
| Page (STEPS `desc`/`intro`/`help` = 84; `pageHelp` args across 43 STEP_HELP keys = 166) | 250 | 0 | 0 | 6 | 256 |
| Section (`section-note`, `rc-sub` etc.) | 76 | 23 | 11 | 2 | 112 |
| Field (`title=` tooltips 30, field-level `pageHelp` e.g. SYSTEM_CONFIG_FIELD_HELP) | 52 | 2 | 2 | 3 | 59 |
| Message (`small`, `muted`, banners, empty states) | 77 | 29 | 14 | 4 | 124 |
| **Total** | **455** | **54** | **27** | **15** | **551** |

Source kinds: 237 prose-class nodes, 200 `pageHelp` args, 84 STEPS fields, 30 `title=` tooltips. Largest modules by section/field/message rows: allocation optimizer (29), checklist closeout (26), housing scenarios (19), admin (16), housing optimizer, Monarch reconciliation, planning workbench, reports UI (12 each).

## How the guesses were made
- A: default for page-level help and any prose-class text that is not B/C.
- B: text starting "No/Not/Loading/Empty..." or ending "yet/saved/ready..." under 120 chars.
- C: `warn` class, or warning vocabulary (must, cannot, override, delete, error...).
- D: automated only: same step id (or identical text), at least 80% of the shorter string's content words are in a longer surviving string. Survivor order: most information, then STEPS/pageHelp source. `merged_into` = survivor `file:line`; `unique_info_kept` lists words to fold in (or `none`).
- `step_id` is exact for STEPS and `pageHelp`; for other modules it is a per-module guess (`MODULE_STEPS` in the script), blank where a module serves many pages.

## Tests coupled to center text
Quote inventory text (found by the scan): `tests/frontend/next_housing_move_section.test.mjs`, `tests/test_field_finder_category_grouping_functional.py`, `tests/test_glossary_single_source_of_truth.py`, `tests/test_housing_trajectory_comparison_sheet_functional.py`, `tests/test_lcv_feasibility_gate_regression.py`, `tests/test_roth_objective_deflator_regression.py`, `tests/test_secondary_sheets_lcv_conversion.py`.

Assert on structure (`.intro`, `.help`, `.desc`, `STEP_HELP`, `section-note`, `.question`, `class="small"`): `tests/test_housing_optimizer_panel_functional.py` (14 hits), `tests/frontend/strategy_section_lazy_body.test.mjs` (6), `tests/test_mobile_responsive_shell_functional.py` (4), `tests/test_help_text_no_html_entities_regression.py`, `tests/test_frontend_size_ratchet.py`, `tests/e2e/workbook-format-stale-cache.spec.js`, `tests/frontend/plain_english_help.test.mjs`, `tests/frontend/field_help_icon_coverage.test.mjs`, `tests/frontend/monarch_reconciliation_page.test.mjs`, `tests/frontend/load_dashboard.mjs`, plus one hit each in `test_planning_workbench_consolidation_functional.py`, `test_after_tax_roth_build_impact_functional.py`.

## Corrections to the plan's estimates
- STEP_HELP: 43 distinct step keys carry `pageHelp(...)` in the STEP_HELP map (plan: 56 entries; `STEP_HELP.actual_spending` is an alias). `pageHelp` calls after the map are field help, not page help.
- Section notes: 112 section-level strings with 3+ words (plan: about 200; the 198 `section-note` grep hits include dynamic or data-only nodes).
- Message level: 124 captured (plan: about 240 `small` + 24 banners); the 268 `small` hits include many data fragments such as `Annualized ${x}`.
- Tooltips: 30 `title=` attributes with 3+ words (plan: 63).
- The center "question" box (`dashboard.js:3429`) is built from `st.desc` + `st.help` at run time, so it is not a separate string. Phase 2 removing it needs no extra text handling.
- Capture is a lower bound: 464 prose-class occurrences were found by grep and about 190 had no row within 3 lines (mostly label fragments or text assembled across `+` with dynamic parts). Phase 3 batches should re-grep their module for leftovers.
- D count is low (15) because the automated pass is conservative. The aggressive rule 3.1 needs human review, mainly STEPS `desc` vs `intro` vs `help` vs `pageHelp` per page; those pairs are still marked A where each carries different facts.

## Exit status
Every row has a class guess and a destination. Human correction of the class column is the remaining Phase 0 step before Phase 1.
