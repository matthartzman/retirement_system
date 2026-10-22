Status: implemented (closed out in Phase 4, 2026-10-22). Phase 0 measurements below are historical; see "Phase 4 closeout" for the final counts.

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

## Phase 2a: `slot` column
`python tools/page_help_ledger.py slots` fills a `slot` column for every page-level row (STEPS and `pageHelp`): `HELP_PAGES[<page id>].<slot>`, several slots joined by `;`, or `D` when every sentence of the row is a pure repeat of a kept sentence. The slot column is the truth for page rows; the older automated `class` / `merged_into` guesses are unchanged and are superseded by the slot where they differ (for example a row guessed D that the ledger merged into a slot). Legacy sub-page keys map to their parent page. Review: `page_help_review.md`.

## Phase 3, batches 1-3 (Income and Benefits; Spending; Investments and Property)
Modules: `dashboard_decomp_income_streams`, `_death_benefits`, `_spending_taxonomy`, `_spending_sources`, `_spending_adjustments`, `_large_discretionary`, `spending_dashboard`, `_holdings`, `_rental_properties`, `_assets_other`. 83 rows now (50 from the scan, 33 added by a leftover Grep; the scan was a lower bound). `line` is the pre-change line number.

| Result | Scan rows | Leftover rows |
|---|---|---|
| Class A moved to `HELP_SECTIONS` (36 new records in `help_registry.js`) | 28 | 16 |
| Class D deleted (`merged_into` target exists) | 5 | 0 |
| Kept as one line, tagged `data-kind="state"` or `"warn"` (B/C, or A shortened with the rest folded into a record) | 17 | 13 |
| Deferred: `domainBudgetNote()` strings rendered by `dashboard_decomp_row_model.js`, a module outside these batches | 0 | 4 |

Notes: the scan guessed some rows A that are really B/C (for example "Showing {year} (not the current plan year)"); the class column now follows the code. Sections without a heading get a bare "?" row; headings, `<details>` and `table-actions` rows carry `data-help-section` where they exist. Two pointer lines that hold navigation links (Family & Business, Spending Model's Housing tail) stay as one-line `state` notes; their explanation moved to the records. The rental page id is `rental_properties` (the scan's `MODULE_STEPS` maps the module to `assets_special`).


## Phase 4 closeout (final counts)
`python tools/verify_ui_prose_inventory.py --counts` (also run by `tests/test_ui_prose_inventory_closeout.py`) checks that every row's `destination` starts with `moved:`, `deleted:` or `kept:`, that no class A row is `kept` except hover-only tooltips, and that every class D row's `merged_into` target exists (a file, a `file:line` within the file, or a registry key). The CSV grew from 551 to 584 rows because Phase 3a added rows for modules the first scan missed.

| Level | A moved to panel | B state (kept, one line) | C warn (kept, one line) | D deleted | Total |
|---|---|---|---|---|---|
| Page | 250 | 0 | 0 | 6 | 256 |
| Section | 72 | 41 | 15 | 0 | 128 |
| Field | 48 | 3 | 4 | 9 | 64 |
| Message | 42 | 67 | 17 | 10 | 136 |
| **Total** | **412** | **111** | **36** | **25** | **584** |

Dispositions: 406 moved, 25 deleted, 153 kept (including 7 class A hover-only tooltips on readouts, which are not in-flow prose).

Notes:
- Page rows are traced by the `slot` column (Phase 2a); section and field rows by the `destination` column. A `moved:` destination written by the automated pass names the target page, not always a specific key, so the check is on the class and disposition, not on a per-row registry key.
- Phase 4 found about 100 section-note / small nodes that Phases 2-3 had missed (dynamic or concatenated strings the first scan could not see). They were moved to 15 new and 15 extended `HELP_SECTIONS` records, deleted as duplicates of existing help, or shortened and tagged. Two exceptions are recorded in the PR: the recommendation card's "Why it matters" line is card content (class `recommendation-impact`, not `small`), and the Final review list on the welcome page lost its `small` class.
- Guard: `tests/frontend/ui_prose_guard.test.mjs` fails any `section-note` / `small` node with three or more words of static text that lacks `data-kind="state|warn"` or exceeds 120 characters. Nodes that interpolate values are treated as readouts (length rule only); `<button>` and `<label>` are exempt. `tests/e2e/contextual-help-panel.spec.js` repeats the check on rendered pages.
