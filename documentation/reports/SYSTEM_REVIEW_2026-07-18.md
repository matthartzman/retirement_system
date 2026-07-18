# System Review — Retirement Planning (Version 10)

**Scope:** whole-system review by a five-expert panel (architecture, usability, documentation/content,
test quality, financial-planning domain). Findings were cross-checked; corrections and refutations are
recorded inline and in the Appendix.

**Status of this document:** analysis and proposal only. No source file was modified during the review.
Every claim below cites a file and, where the reviewer read it, a line number. Line numbers reflect the
tree at review time (branch `main`, tip `2cb59c6`); re-verify before editing.

**How to read it:** Section 2 preserves every option each expert considered, including the ones I did not
recommend. If you disagree with a recommendation, the alternative and its tradeoff are sitting next to it.
Section 4 is the single plan I am proposing; Section 6 is how to execute it.

---

## 1. Executive summary

Eight things matter. Everything else in this document is either downstream of these or is cheap cleanup
you can batch opportunistically.

**1. A live financial-correctness defect: the Roth optimizer is charging capital-gains tax on assets that
get a step-up in basis at death.** `src/after_tax.py:120-147` computes federal LTCG + NIIT + state tax on
the entire unrealized gain in terminal taxable accounts, and `:219` subtracts it from terminal net worth
to produce `after_tax_terminal_nw` — which `src/planning_engines.py:1327-1329,1452` makes the dominant
term of the Roth conversion objective. But the same codebase models §1014 correctly during life
(`planning_engines.py:317-323,333-335` set `basis_free` to full balance at each death). The plan end *is*
death. **Payoff:** removes a systematic bias toward over-conversion that an advisor could not defend in a
review meeting. This is the single highest-value fix in the report.

**2. A second correctness defect in the same objective: RMDs start two years late for anyone born
1951-1959.** `rmd_start_age` is a static input defaulting to 75 (`src/data_io.py:852-853`,
`reference_data/schema.csv:27`, shipped as 75 in `input/client_policy.csv:27`), never derived from date of
birth, and nothing in the codebase maps birth year to the SECURE 2.0 schedule (73 for 1951-1959, 75 for
1960+). Because `planning_engines.py:850` also anchors the conversion window end to this field, the error
moves the RMD ramp, the conversion window, *and* the IRMAA path together. **Payoff:** correct default for
every new plan; the live client plan currently runs at the wrong age.

**3. ~650 lines of unreachable code in the highest-traffic spending module, arranged as a trap.**
`src/spending_tracker.py` defines 15 module-scope function names two or three times —
`load_mapping_rules` at `:603`, `:1437`, `:2240`; `load_taxonomy` at `:502` and `:1104`; and 13 more. The
last definition wins; the earlier bodies are dead. The implementations differ materially (the dead
`load_taxonomy` parses the raw legacy CSV header; the live one delegates to `_taxonomy_rows()` and honours
origin/status). A maintainer who greps for `load_taxonomy` finds the wrong one first and edits code that
never runs. **Payoff:** closes a class of silent-no-op bug; the deletion itself cannot change behaviour,
because Python already discarded these bindings at import.

**4. A working feature was orphaned by the recent dashboard decomposition.** Detailed Results ships a
fully-built, stateful hierarchical workbook-sheet navigator — CSS (`frontend/css/dashboard.css:71-75`),
persisted open/closed state (`dashboard.js:992-998,5147-5149`, localStorage key
`retirementDetailedResultsNavOpen`), and a comment at `dashboard.js:12154-12159` reading "Only auto-open
sidebar on very first visit" — but `renderDetailedResultsNav()` has **zero call sites** outside its own
definition at `dashboard.js:5173-5176`. Users navigate 25+ workbook sheets through a flat alphabetical
`<select>` (`reports_ui.js:1204-1209`). This looks like fallout from commit `2cb59c6`. **Payoff:** a
materially better Results Explorer for roughly one line of code.

**5. Every report build runs the deterministic projection twice and deep-copies the whole config six
times.** `src/report_compute.py:134` runs the full projection; `:145` calls `monte_carlo(cfg)`, and
`planning_engines.py:2634` / `:2052` each *restart* with `base_rows = project(c)` — a second complete run
of the same 1,940-line year loop, discarding rows the caller already holds. Separately
`ensure_engine_config` is called six times per build with no idempotency check, each time doing a full
recursive freeze into `MappingProxyType`/tuple/frozenset and an immediate full thaw
(`plan_config.py:96,99-111`) — even though `:110` sets a `config_immutable_boundary=True` marker that
re-entry ignores. **Payoff:** roughly half the deterministic compute per build, for a small diff.

**6. The projection "pipeline" is decorative, and the fiction is persisted.**
`src/projection_pipeline.py:103-104` emits a `scheduled` event for each of 14 stages, `:107` runs the whole
projection in one opaque call, and `:110-112` emits `completed` for all 14 with metrics derived by
re-scanning the finished rows — **14 separate full passes** over the output. No stage owns any computation.
`report_compute.py:136-138,168` then writes this stage order and event log into the saved snapshot, so the
claim that fourteen stages ran surfaces in the Results Explorer. **Payoff:** honest observability, minus 13
redundant passes; and it is the prerequisite for ever breaking up the 1,940-line engine function honestly.

**7. Most guided-step forms waste 35-45% of the content column.** `fieldHtml()`
(`dashboard.js:5825-5885`) emits every field as its own block-level row; `.field-list` has no grid or flex,
and `.field`'s internal grid caps each row at roughly 440-650px inside a 700-1050px content column
(`main{grid-template-columns:310px minmax(700px,1fr) 370px}`). Sections with 29, 22 and 17 fields
(`reference_data/schema.csv` — Social Security, Withdrawal Policy, Cashflow) therefore scroll a long way
past a column of blank space. **Payoff:** the single most generalizable UI improvement available; one CSS
rule affects ~30 screens.

**8. No test drives a real end-to-end journey, and the one file named for it fakes the build.**
`tests/test_161_phase2_live_workflow_journeys.py:34-44` replaces `_run_build_progress_job` with a fake that
never calls the workbook builder, and `:70-75` replaces `report_service.detailed_results_payload` with a
hand-written dict. The only fixture that runs a real subprocess build (`conftest.py:34-76`,
`built_workbook_dir`) is used by 5 of 180 test files, none of which go through `/api/build/start`. PDF
output is verified by a magic-byte check only (`test_phase5_validation_maturity.py:204-213`). **Payoff:**
for an application whose deliverable *is* the workbook/PDF/dashboard, this is the coverage gap that matters.

---

## 2. Panel findings by discipline

Impact and effort labels are the reviewing expert's. Recommendations are mine; each option is preserved so
you can overrule.

### 2.1 Architecture

#### A1. `spending_tracker.py` shadows 15 function names; ~650 lines unreachable — **critical / M**

*What it is.* `src/spending_tracker.py` contains unconditional column-0 `def` statements that redefine the
same module-scope name two or three times. Python keeps the last one.

*Evidence.* `load_mapping_rules` at `:603`, `:1437`, `:2240`; `load_taxonomy` `:502`/`:1104`;
`taxonomy_flat` `:527`/`:1130`; `spending_dashboard` `:362`/`:2123`; `monthly_series` `:318`/`:2083`;
`load_category_map` `:81`/`:2255`; `save_category_map` `:172`/`:2274`; `apply_mapping_rules`
`:643`/`:1412`; `save_mapping_rules` `:627`/`:1450`; `save_taxonomy_category` `:541`/`:1159`;
`update_taxonomy_category` `:552`/`:1175`; `delete_taxonomy_category` `:576`/`:1195`;
`load_budget_by_category` `:707`/`:1627`; `save_budget_by_category` `:726`/`:1650`; `load_aliases`
`:1317`/`:2186`. Additionally `_legacy_source_page_for_tracking_type` (`:747`), `_legacy_nonzero_amount`
(`:760`) and `_legacy_spending_summary_taxonomy` (`:766`, ~140 lines) have zero references in `src/`,
`tests/` or `tools/`. `__all__` at `:22` lists several shadowed names but binds the surviving definition,
so it does not rescue the dead bodies.

*Options.*
1. **Delete in place + CI guard.** Remove the 17 unreachable defs and the three `_legacy_*` functions; add
   an AST test asserting no `src/` module redefines a top-level name. *Tradeoff:* purely subtractive and
   behaviour-preserving by construction, but leaves a 1,400-line grab-bag behind.
2. **Delete, then split.** As above, then split along the seams already visible: `spending_taxonomy.py`
   (`:1036-1315`), `spending_mapping.py` (`:1317-1460`), `spending_budget_store.py` (`:1462-1700`),
   `spending_actuals.py` (`:1687-2185`), with `spending_tracker.py` reduced to a re-export facade.
   *Tradeoff:* addresses the root cause but needs the import surface re-verified across ~40 call sites,
   and the facade becomes its own shim if not retired.
3. **Lint gate only.** Enable ruff F811 / pylint E0102 and file the 17 as known debt. *Tradeoff:* cheapest,
   stops the bleeding, leaves the trap armed.

*Recommendation.* **Option 1 now, Option 2 later.** Ship deletion + the AST/F811 guard as one commit so
the hazard closes immediately. Defer the split — it is valuable but competes with higher-impact work in
Section 4, and the guard already makes recurrence structurally detectable.

*Risk.* Deletion cannot change runtime behaviour. Option 2's facade must be verified against every
importer by import-graph inspection, **not** by running the suite (project memory: some tests overwrite
`input/client_data.*`).

#### A2. `projection_pipeline` advertises 14 stages that never execute — **high / L**

*Evidence.* `src/projection_pipeline.py:29-44` (`DEFAULT_STAGE_ORDER`), `:103-104` (scheduled events),
`:107` (single `engine_project(config)` call), `:110-112` + `_summarize_stage` `:75-95` (completed events
whose metrics come from re-scanning finished rows — `:78` sums `r['earned']`, `:90` sums `r['total_tax']`,
`:92` sums five withdrawal keys; 14 passes total). Event detail at `:112` literally reads "deterministic
stage contract completed". `report_compute.py:136-138,168` persists this into saved snapshots.

*Options.*
1. **Make the facade honest.** Drop per-stage events; keep one engine started/completed pair and one
   single-pass metric summary. *Tradeoff:* small and safe, but deletes the seam the module's own docstring
   says is meant to "progressively absorb individual stage implementations".
2. **Make the stages real, incrementally.** Keep the contract; extract genuine stage functions from
   `deterministic_engine`, starting with the nearly-pure ones (PayrollTax, RMDs, SocialSecurity). Stages
   with no registered callable report `inlined`, not `completed`. *Tradeoff:* delivers the intended
   architecture and stage-level testability; expensive, must run under golden-master protection.
3. **Collapse entirely.** Delete the module; `report_compute` calls `planning_engines.project()` directly.
   *Tradeoff:* smallest surface, but discards working observability hooks and forecloses decomposition.

*Recommendation.* **Option 2, with Option 1's honesty fix applied immediately as step one.** The dishonest
event log is the urgent part; change `completed` → `inlined` for unregistered stages and collapse 14 passes
to one. Do not delete the contract — it is the only articulated plan for breaking up A3.

*Risk.* Event shape is a persisted contract. Check `tests/fixtures/results_model_v10_contract.json` before
altering keys.

#### A3. The deterministic engine is one 1,940-line function reached via a circular star-import — **high / XL**

*Evidence.* `src/projection_stages/deterministic_engine.py` declares exactly one top-level function,
`run_deterministic_projection_stage` at `:30`, running to `:1970`; all calculation lives in nested closures
(`_add_account_flow` `:49`, `_tag_deposit_source` `:54`, `_mortgage_payment_and_balance` `:64`). The module
does `from ..planning_engines import *` at `:14` while `planning_engines.py:1205` does a deferred
function-scoped import back — a deliberate cycle break. Because star imports cannot carry
underscore-prefixed names, `:22-27` reach into another module's privates:
`_ar = _legacy_pe._ar`, plus `_aa`, `_we`, `_ce`, `_ie`, `_ge`. `planning_engines.py:1182` carries a comment
acknowledging it holds an import solely for this consumer.

*Options.*
1. **Break the cycle first.** Move the shared primitives into a neutral `src/projection_stages/
   engine_primitives.py` imported explicitly by name from both sides; delete the star import and private
   rebinding. *Tradeoff:* removes the mechanism no linter or refactoring tool can see; leaves the monolith.
2. **Break the cycle, then extract stages** behind A2's contract, using the existing `MutableYearState`
   (`projection_stages/year_state.py`, imported at `:13`). *Tradeoff:* the only route to stage-level unit
   tests; multi-session effort against dense shared mutable state.
3. **Leave it, invest in characterization tests.** *Tradeoff:* cheapest, but a rename inside
   `planning_engines` breaks the rebinding at import time and no test catches it beforehand.

*Recommendation.* **Option 1 now; Option 2 as the long arc, sequenced behind A2.** The private-alias
rebinding is the actively dangerous part and is cheap and independently verifiable to fix.

*Risk.* High. This function's own docstring (`:31-34`) calls it the single projection source of truth for
workbook, PDF, API and scenario builds. Validate against
`tests/fixtures/golden_master_engine_cases.json` with `RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1`.

#### A4. Every build runs the projection twice and deep-copies the config six times — **high / S**

*Evidence.* `report_compute.py:134` runs the projection; `:145` calls `monte_carlo(cfg)`, and
`planning_engines.py:2634` (vectorized) and `:2052` (exact scalar) each begin `base_rows = project(c)`.
`ensure_engine_config` is called at `report_compute.py:113,119,125,128,133`, again at
`deterministic_engine.py:36`, again at `planning_engines.py:2050/2633`. `plan_config.py:188-190`
unconditionally re-normalizes; `PlanConfig.__post_init__` `:96` runs `_freeze_value` over the whole config
(`:61-70`) and `as_engine_dict` `:99-111` immediately runs the inverse `_thaw_value` (`:73-79`). `:110` sets
`config_immutable_boundary=True` — a marker ignored on re-entry. Commit `b72270b` improved the constant
factor, not the repetition.

*Options.*
1. **Pass `base_rows` into `monte_carlo`; short-circuit `ensure_engine_config`** when the input is already
   a plain dict carrying `config_immutable_boundary=True` and a matching contract version (with a `force`
   escape). *Tradeoff:* removes ~half the deterministic compute and five of six deep copies for a tiny
   diff; slightly weakens the immutability guarantee — though the engine already mutates its working copy
   (`deterministic_engine.py:42-44` pops cache keys), so that guarantee is softer than it looks.
2. **Memoize normalization by config digest.** *Tradeoff:* helps all call sites, but introduces
   cache-invalidation risk in a system that deliberately deep-copies configs for scenario isolation.
3. **Normalize once at the boundary; convert defensive calls to assertions.** *Tradeoff:* cleanest end
   state, riskiest — those defensive calls protect entry points reached from tests and `tools/`.

*Recommendation.* **Option 1.** Both halves are independently verifiable. Avoid Option 2's cache in a
codebase that relies on deep-copy isolation.

*Risk.* `base_rows` feeds `base_years` (`planning_engines.py:2635`), which shapes the MC path grid — verify
success rates are bit-identical against golden masters with live pricing disabled. The short-circuit must
not skip source-tagging at `plan_config.py:107`.

#### A5. 1,640 lines of frontend "decomposition" modules that nothing loads — **high / S**

*Evidence.* `frontend/index.html` loads 19 scripts at `:92-111`; `dashboard_module_loader.js`,
`dashboard_income_module.js`, `dashboard_spending_module.js`, `dashboard_assets_module.js` and
`dashboard_strategy_module.js` are **not** among them. Their only references are each other
(`dashboard_module_loader.js:22,29,36,43`, self-referenced at `:454`), an orphaned
`tests/test_phase_d_tier_3b_dashboard_modules.js` (a `.js` file in a pytest-only directory, collected by no
runner), and `documentation/archive/PHASE_D_TIER_3B_DASHBOARD_MODULARIZATION.md`. Line counts: 402 + 454 +
350 + 296 + 138 = 1,640. `dashboard_income_module.js:141-142` queries `[data-label*="h_ss_benefit"]` /
`[data-label*="w_ss_benefit"]` — no `h_`/`w_`-prefixed data-labels exist anywhere in the live frontend
today, so this code has already drifted out of sync with a completed migration.

*Options.* (1) Delete all five plus the orphan test. (2) Wire them into `index.html` and finish the
decomposition. (3) Keep them with an "experimental" header comment.

*Recommendation.* **Option 1.** Option 2 is closer to writing new code than activating existing code —
these modules match neither convention actually in use, and the income module is 138 lines of DOM
validation stubs with a placeholder integration point at `:110-114`. Option 3 preserves a trap that
1,640 lines of confident-looking code will win against a comment.

*Risk.* Essentially none. Verify `retirement_planner.spec` does not glob `frontend/js/*.js` in a way some
path enumerates.

*Correction applied.* The original finding cited commits `e809367` and `84d8384` as the husband/wife
migration. **Neither hash exists in this repository** (`git cat-file -t` fails for both). The underlying
claim stands on direct evidence; the commit attribution is dropped. See Appendix.

#### A6. `dashboard.js` is 16,613 lines and 806 functions; the house doc claims ~1,670 — **high / XL**

*Evidence.* `frontend/js/dashboard.js` — 16,613 lines, 806 top-level function declarations, 114 `render*`
entry points. `documentation/CLAUDE.md:156` states "dashboard.js is the largest file (~1670 lines, heavily
minified — roughly one statement per line)": off by an order of magnitude, and the file is conventionally
formatted, not minified. Cohesive near-contiguous clusters: YTD tracking/transactions `:10638-11856`
(~1,200 lines, ~90 functions); spending taxonomy/budget `:12471-13930` (~1,450); allocation/optimizer
`:6050-6972` (~920); field help/guidance `:14687-15473` (~790); plan-data file IO/save/build `:15473-16616`
(~1,140); build history/change impact `:1742-2812` (~1,070); holdings/liabilities/pricing `:8844-9550`
(~700).

*Options.*
1. **Verbatim extraction into `dashboard_decomp_*` siblings** (shared global scope, plain function
   declarations, listed in `index.html`) — the pattern already shipped in `2cb59c6` across six live files.
   *Tradeoff:* low-risk, reviewable cluster by cluster; textual movement, not encapsulation.
2. **IIFE namespaces with explicit context objects** — the `planning_workbench_ui.js` / `reports_ui.js`
   pattern (`dashboard.js:3432-3436` delegates via `window.RetirementPlanningWorkbench.renderWorkbench(
   planningWorkbenchContext())`). *Tradeoff:* genuine encapsulation and testable units; substantially more
   work per cluster, with wide context objects for YTD and spending.
3. **Freeze and document.** Correct `CLAUDE.md`, add section banners, route new work to new files.
   *Tradeoff:* near-zero cost, stops it getting worse, leaves 16,613 lines hostile to review.

*Recommendation.* **Option 1 for the bulk; Option 2 only where tests are wanted.** Start with the YTD
cluster — largest contiguous block, clearest boundary. **Fix `documentation/CLAUDE.md:156` regardless of
which option you choose**: a house-rules file understating its largest file by 10x actively misleads every
future contributor and agent, and it demonstrably misled this review's own recon pass.

*Risk.* Load order matters (`index.html:93-111`, `dashboard.js` at `:104`). `tests/frontend/
load_dashboard.mjs` assembles the scripts and must move in lockstep;
`test_39_active_input_recursion_guard.py:15` depends on that harness.

#### A7. Twelve near-identical Plan Data backfill functions, disabled under test — **medium / M**

*Evidence.* `src/server/app_core.py` defines `_ensure_*_ui_plan_data_rows`, orchestrated by
`_ensure_user_ui_plan_data_rows` (`:833`, sequence `:849-859`). Each repeats the same five-step body —
compare `_ensure_wellness_*` (`:913-926`), `_ensure_heloc_*` (`:929-945`), `_ensure_monte_carlo_*`
(`:948-970`), `_ensure_hsa_withdrawal_*` (`:862-877`). A generic helper exists (`_ensure_row_in_csv`
`:792-813`) but only `_ensure_core_spending_*` uses it — once per row in a loop (`:817-820`), so each row
triggers a full file read and rewrite. Because targets overlap, one call reads and rewrites
`client_policy.csv` five times (`:767,931,956,981,1453`) and `client_household.csv` twice (`:896,914`).
`:847` short-circuits the entire family with `if 'pytest' in sys.modules or 'unittest' in sys.modules:
return` — the only such guard in `src/` — so this path, which runs on every folder import and browser save,
has **zero test coverage by construction**. The docstring at `:841-845` says so.

*Options.* (1) Collapse to a declarative `(target_file, rows, anchor_predicate)` table over a batched
writer. (2) Do that **and** move it to `src/plan_data_backfill.py` taking an explicit target directory, so
the pytest guard can be deleted and the path finally tested. (3) Fix only the per-row loop at `:817-820`.

*Recommendation.* **Option 2.** Production code branching on test-framework presence, with a docstring
admitting it writes to the live `input/` directory, means this backfill has never been executed by a test —
uncomfortable for code that mutates user plan data on every folder import. Parameterising the directory is
what makes the guard removable, and it matches the Wave-2 pattern set by `plan_data_migration.py`.

*Risk.* Moderate; there is no existing safety net to regress against, so **write the characterization tests
first, then refactor**.

#### A8. `workbook_common` is a 954-line star-exported hub — **medium / L**

*Evidence.* Twelve modules do `from .workbook_common import *`: `workbook_builder.py:1`,
`sheets_summary.py:1`, `sheets_strategy.py:1`, `sheets_stress.py:1`, `sheets_qc_reference.py:1`,
`sheets_wealth.py:16`, `sheets_protection.py:16`, `sheets_projection_cashflow.py:15`,
`sheets_projection_charts.py:15`, `sheets_projection_net_worth.py:15`, `sheets_projection_tax.py:10`,
`dashboard.py:1`. `workbook_common.py` itself imports all of openpyxl (`:19-26`), star-imports engine core
(`:16`), and reaches into IO/orchestration: `data_io`'s `load_csv`/`parse_client`/`build_plan_from_json`
(`:31`), `config_backend.load_active_config` (`:32`), `workspace_context` (`:33`),
`report_compute.prepare_config_from_sectioned_data`/`run_projection_artifacts` (`:34`). Consequence: every
sheet module's namespace transitively contains the CSV parser, the active-config loader and the projection
runner, named by no import statement. The clearest symptom is `reporting/dashboard.py` — a pure inline-SVG
HTML generator whose docstring (`:20-24`) stresses it has no external chart dependency — inheriting the
whole openpyxl and engine surface via a line-1 star import.

*Options.* (1) Replace star imports with explicit named imports across the twelve consumers.
(2) Do that, then split into `workbook_styles.py` / `workbook_data_access.py` so sheet builders can no
longer reach the CSV parser or trigger a projection. (3) Bless it as a prelude and add `__all__`.

*Recommendation.* **Option 1 as a prerequisite for Option 2.** You cannot safely choose a split boundary
until you know what each consumer actually pulls — and with F403 suppressed across twelve modules, no tool
can answer that today. Option 3's `__all__` is a worthwhile consolation prize if Option 1 is deferred.

*Risk.* Low per step, broad in reach. Names may currently resolve *through* `workbook_common` from `core`
or `market_data`; converting will surface these as NameErrors. Do it one module at a time against
`tests/fixtures/workbook_snapshot_expectations.json`.

#### A9. Optional-module gating lives in the Excel helper module — **medium / S**

*Evidence.* `module_status` is defined at `src/reporting/workbook_common.py:366`. Its consumers are not
workbook code: `src/server_services/config_service.py:105` builds the UI's `module_status` payload (`:82`),
and `tests/test_module_catalog_prereq_gating.py:182,197` asserts prerequisite gating. `config_service.py:
88-93` documents the awkwardness itself, noting the reporting package is "openpyxl-backed and otherwise
unused by config_service", lazily importing it and degrading to `{}` rather than failing. Meanwhile
`src/module_catalog.py` is a dedicated 478-line registry for exactly this concern (`optional_keys` `:424`,
`core_keys` `:429`, `prerequisite_outputs` `:434`, `resolve_selection` `:454`, `validate` `:492`) — but not
the status function the API and the module-catalog test both need.

*Options.* (1) Move `module_status` into `module_catalog`. (2) Extract a third `module_gating.py` service.
(3) Leave it; the lazy import contains the cost.

*Recommendation.* **Option 1.** The intended home is unambiguous — the test exercising `module_status` is
named `test_module_catalog_prereq_gating.py`. Moving one function deletes a layering violation, removes a
lazy-import workaround, and eliminates a silent-degradation path (config_service returning `{}` on a broken
reporting import means the UI silently loses module gating with no signal). Option 2 solves a fragmentation
problem that does not exist yet.

#### A10. `planning_query_api.py` has zero callers — **medium / S**

*Evidence.* `src/planning_query_api.py` (106 lines) is referenced nowhere in `src/`, `tests/`, `tools/` or
`frontend/` — not an import, not a string. Its four functions are thin passthroughs (`project_scenario`
`:37` returns `project(c)` verbatim; `compare_scenarios` `:80` and `monte_carlo_run` `:123` each call
`project(c)` again). Its docstring `:1-13` describes an architecture never adopted — and that docstring is
what led the recon pass to describe it as "the query layer consumed by frontend". The frontend reaches the
engine through `/api` routes in `src/server/`.

*Options.* (1) Delete. (2) Adopt it as the real query layer. (3) Move to `tools/` as an example.

*Recommendation.* **Option 1.** This is the clearest "unused today" rather than "load-bearing compat" case
in the codebase, and it is actively harmful as documentation. Option 2 would import A4's
redundant-projection problem rather than solve it.

#### A11. 57 dual-import fallbacks guard a mode no entry point uses — **medium / M**

*Evidence.* 57 `try/except` blocks in `src/` retry a relative import as absolute — e.g.
`config_service.py:94-102` tries `from ..reporting import workbook_common`, retries `from src.reporting
import workbook_common` on any `Exception`, then returns `{}`. Concentration: `app_core.py` 12,
`holdings_service.py` 8, `workbook_routes.py` 7, `config_service.py` 6, `plan_routes.py` 5,
`security_audit.py` 5, `desktop_api.py` 4, `base_routes.py` 4. But every entry point imports as a package
after putting the repo root on `sys.path`: `main.py:75,84,85,86`; `tools/build_workbook.py:23-25,33`. The
frozen exe runs the same script via runpy (`documentation/CLAUDE.md:164`). Under all of these the relative
import succeeds and the fallback is unreachable. Several catch bare `Exception` and swallow it, so a
genuine import error is indistinguishable from a disabled feature.

*Options.* (1) Add a package-import guard test, then remove fallbacks in batches. (2) Narrow
`except Exception` → `except ImportError` without removing anything. (3) Keep as defensive coding.

*Recommendation.* **Option 2 first as an immediate partial fix, then Option 1.** Narrowing is a one-pass
change that stops real bugs being disguised as missing modules and can land before the guard test exists.
Do not skip the guard test — PyInstaller resolves paths differently (`CLAUDE.md:171-173` on `BASE_DIR`), so
validate a **built exe** before touching `desktop_api.py` and `app_core.py` specifically.

#### A12. Husband/wife nomenclature remains the engine's internal row contract — **medium / L**

*Evidence.* At-rest migration is done (`src/plan_data_migration.py`), but row keys were never migrated:
`wife_`/`husband_` identifiers appear 75 times across `src/` — `deterministic_engine.py` 23,
`plan_data_migration.py` 11, `data_io.py` 8, `planning_engines.py` 6, `sheets_stress.py` 5,
`results_model.py` 4, `sheets_projection_cashflow.py` 3, `sheets_projection_charts.py` 2,
`schema_registry.py` 2 — plus ~40 bare `h_ss`/`w_ss` occurrences. They are load-bearing:
`projection_pipeline.py:80` sums `r['h_ss'] + r['w_ss']`, `:82` sums `wife_single_ann`, `wife_joint_ann`,
`h_single_ann`, `h_joint_ann`; `deterministic_engine.py:42` clears cache keys named `'wife_pension'`,
`'wife_single'`, `'wife_joint'`, `'h_single'`, `'h_joint'`. Because the internal contract is gendered,
every consumer translates at its own edge — the structural cause of the duplication across `core.py`,
`plan_data_migration.py`, `person_labels.py` and `workbook_common.py`.

*Options.* (1) Leave the contract, consolidate all translation through `person_labels.render_label`.
(2) Rename ~115 occurrences to member-indexed keys and regenerate golden masters. (3) Add member-indexed
accessors (`member_ss(row, i)`, `member_annuity(row, i)`) over the existing keys and migrate consumers
incrementally.

*Recommendation.* **Option 3, paired with Option 1's cheap edge consolidation.** Option 2 is the correct
end state but the row dict is consumed simultaneously by workbook builders, `results_model`, persisted
snapshots and the frontend, and project memory records a prior ~$9.5M golden-master swing from a subtle
resolver bug. That is not a codebase for a 115-site rename of the engine's core contract in one move.
Accessors stop the bleeding immediately and make the eventual rename strictly easier.

*Note.* The original finding cited the same non-existent commits `e809367`/`84d8384` as A5. Treat the
commit attribution as unsupported; the substantive claim is verified by direct code inspection.

#### A13. Three competing frontend extraction conventions; shared helpers duplicated — **medium / M**

*Evidence.* (1) Verbatim global extraction, documented at `dashboard_decomp_home_panels.js:1-6`. (2) IIFE
namespace with injected context, `planning_workbench_ui.js:2` + `dashboard.js:3432-3436`. (3) The unloaded
ModuleLoader registry (A5). The cost: `esc` is defined four times — `dashboard.js:1171`, `reports_ui.js:7`,
`planning_workbench_ui.js:13`, `dashboard_batch_assumption_edit.js:10`; `escJs` three times
(`dashboard.js:1180`, `reports_ui.js:21`, `planning_workbench_ui.js:26`); `fmtPct` twice
(`dashboard.js:1616`, `spending_dashboard.js:61`). These are **HTML-escaping functions with divergent
implementations** in a UI that builds HTML by string concatenation. Separately `dashboard_utils.js` exports
five helpers via `window.RPDashboardUtils` (`:38-44`), and `dashboard.js` delegates to each but retains
verbatim inline fallback copies (`decimalTrim` `:5347-5352`, `currencyDisplay` `:5417-5426`) that are
unreachable because `index.html:95` loads `dashboard_utils.js` before `dashboard.js:104`.

*Options.* (1) Standardise on IIFE-plus-context and centralise helpers. (2) Standardise on verbatim global
extraction and centralise helpers. (3) Deduplicate helpers only; leave conventions mixed.

*Recommendation.* **Option 3's deduplication immediately and independently, then Option 2 as the stated
convention.** Four divergent `esc` implementations is a security-relevant drift risk and is orthogonal to
the convention question; the unreachable `RPDashboardUtils` fallbacks are pure deletion. On convention,
verbatim global extraction is what six live files and the most recent decomposition commit use, and forcing
the large remaining clusters through context-object plumbing would slow the A6 breakup that matters more.
Reserve IIFE for modules that genuinely warrant isolated tests.

*Risk.* A centralised helper file must load before all consumers in `index.html:92-111`;
`tests/frontend/load_dashboard.mjs` must be updated together.

#### A14. `meta_optimizer.py` is kept alive solely by one architecture test — **low / S**

*Evidence.* `src/meta_optimizer.py` (31 lines) exposes `run_meta_optimizer` at `:35`. Its only references
are `tests/test_90_v10_architecture.py:12` (import) and `:63-64` (one test asserting it picks the
higher-scoring of two lambdas returning fixed scores).

*Options.* (1) Delete module and test case. (2) Keep as a documented extension point. (3) Wire it into the
optimizer path.

*Recommendation.* **Option 1.** A 31-line module whose sole consumer is a test over two lambdas is a
fixture with a `src/` path. Option 3 is adding a feature to justify keeping code, which is backwards.

---

### 2.2 Usability

The frontend targets a fixed three-column desktop layout
(`main{grid-template-columns:310px minmax(700px,1fr) 370px}` in `frontend/css/dashboard.css`) that reflows
only below 1180px; a secondary phone/tablet mode (≤768px) gets a drawer nav and collapsible help sheet
that desktop never gets.

#### U1. Detailed Results' hierarchical navigator is built, stateful, and never rendered — **high / S**

*Evidence.* `dashboard.js:5173-5176` defines `renderDetailedResultsNav()` as a wrapper around
`window.RetirementReportsUI.renderDetailedResultsNav()`; a repo-wide grep for the invocation finds **zero**
call sites outside that definition. The tree it would produce (category groups of workbook sheets with
row/section counts, `reports_ui.js:1105-1168`) has real CSS (`dashboard.css:71-75`:
`.detailed-results-nav` / `.detail-nav-category` / `.detail-sheet-btn`) and persisted state
(`dashboard.js:992-998,5147-5149,5167-5176`; `reports_ui.js:1095-1104`; localStorage
`retirementDetailedResultsNavOpen`). `setDetailedResultSheet()` (`dashboard.js:12154-12159`) still calls
`setDetailedResultsNavOpen(true)` with the comment "Only auto-open sidebar on very first visit" — code
written assuming the tree is on screen. Today the Results Explorer offers only a flat alphabetical
`<select>` (`reports_ui.js:1204-1209`).

*Options.* (1) Reinstate the render call (prepend to `#steps`, or to the top of `renderDetailedResults()`).
(2) Delete the orphaned state/render/CSS and instead group the existing `<select>` into `<optgroup>`s.
(3) Surface the tree as a "Jump to sheet" popover from the existing toolbar.

*Recommendation.* **Option 1.** The feature is already built and its state machinery already exists; this
is the cheapest path to materially better navigation on a screen that can hold 25+ sheets. Only redesign if
the restored tree proves too tall in the 310px sidebar in practice. Option 3 introduces an interaction
pattern used nowhere else in the app.

*Note on precedent.* U1 and A5 look superficially similar (dead frontend code) but are opposite cases and
should be treated differently — see §3.

#### U2. Every guided-step form is one field per full-width row — **high / M**

*Evidence.* `fieldHtml()` (`dashboard.js:5825-5885`) emits each field as its own block-level
`<div class="field">`. `renderFieldGroups()` (`:6025-6049`) only wraps a group in a collapsible `<details>`
when `rs.length>14 || groups.length>3` **and** `groups.length>1` (`:6038`) — so steps at or under the
threshold render fully expanded, one field per row. `.field-list` has no grid or flex
(`.field-list{padding:0 20px 18px}`), so `.field` children stack; `.field{grid-template-columns:
minmax(230px,1.05fr) minmax(210px,.9fr)...}` caps each row at roughly 440-650px inside a 700-1050px column.
`reference_data/schema.csv` shows Social Security 29 rows, Withdrawal Policy 22, Cashflow 17, Asset
Allocation Policy 17, Household 12.

*Options.* (1) Make `.field-list` a responsive grid
(`repeat(auto-fit, minmax(360px, 1fr))`). (2) Wire up the already-styled-but-unused `.two-col-inline` class
that exists in `dashboard.css`. (3) Lower the collapse threshold at `:6038` so more groups default closed.

*Recommendation.* **Option 1.** It fixes the actual cause — unused horizontal space — rather than trading
scrolling for clicks (Option 3), and unlike Option 2 it scales past two columns on the widest content
column. Cap max column width so text inputs are not squeezed on very large monitors. The dormant
`.two-col-inline` rule is a useful starting point for the styling.

#### U3. Context Help is pinned at 370px on desktop with no collapse — **medium / S**

*Evidence.* `main{grid-template-columns:310px minmax(700px,1fr) 370px}` reserves 680px of every desktop
screen on every step. `.help-toggle{...cursor:default}` (`dashboard.css:711`) is explicitly inert outside
mobile; the only collapse behaviour (`body.help-open aside.card.help #helpPanel{display:block}`) is scoped
inside `@media(max-width:768px)` (`:734-741`). Meanwhile `.ytd-tx-table{min-width:1420px}`,
`.inactive-values-table{min-width:1180px}` and `.matrix-table{min-width:850px}` all need their own
horizontal scroll that a wider content column would reduce.

*Options.* (1) Desktop collapse toggle mirroring the mobile `help-open` pattern, widening the grid when
collapsed (`body.help-collapsed main{grid-template-columns:310px 1fr}`) and persisting the preference.
(2) Replace the column with a field-anchored popover. (3) Shrink the fixed width to ~300px.

*Recommendation.* **Option 1** — smallest change that gives users control while preserving the always-on
pane for those who want it, and it is the direct source of the width wide tables are missing. Persist the
preference so it does not reset on every step navigation.

#### U4. Spending Analysis keeps only one Type and one Group open at a time — **medium / S**

*Evidence.* `spending_dashboard.js:119-132` stores expansion as scalars — `spendingExpandedType`,
`spendingExpandedGroup`, `spendingExpandedCat` — not sets. `toggleSpendingType` (`:131-132`) sets a new
type without clearing the stale group, so a previously visible group silently vanishes when its composite
key stops matching. The render loop (`:233-263`) uses `if (!typeExpanded) return;` and
`if (!gExpanded) return;` per row.

*Options.* (1) Convert to Sets (or one `expandedKeys` Set of composite keys). (2) Add a pinned "Compare"
strip. (3) Replace the accordion with a flat filterable table.

*Recommendation.* **Option 1.** Cheapest, and it matches how disclosure already works elsewhere in the app
(independent per-row `<details>` in Detailed Results and the Reports workspace). Pair with a "collapse all"
control if height becomes a complaint. Option 3 would discard the budget-bar affordance that makes
over/under status scannable.

#### U5. Detailed Results year columns default to collapsed groups — **medium / S**

*Evidence.* `reports_ui.js:586` renders each column-group header with class `collapsed` and a `▶` marker by
default; only `i===g.sumIdx` renders visibly as `cg-summary` (`:594-596,617`), every other year gets
`cg-hidden` until `toggleDetailColGroup()` (`dashboard.js:12191`) runs. The same pattern repeats in the
auto-generated fallback grouping (`reports_ui.js:662-693`). A 30-year Cash Flow sheet shows one
representative year per group until each header is clicked.

*Options.* (1) Default-expand the group nearest the current plan year. (2) Add an "Expand all columns"
button to the existing toolbar (`reports_ui.js:1204`). (3) Show a richer default summary (first/mid/last
year per group).

*Recommendation.* **Option 2** — smallest change, serves users who came to read numbers rather than browse,
and preserves the compact default. Option 1 is a reasonable additive follow-up if users report that the
near-term case dominates.

---

### 2.3 Documentation and content

The guided-workflow copy (`dashboard.js` `STEPS[]` and `STEP_HELP{}` via `pageHelp()`) is unusually good
for a novice-facing product — distinct per-page text, auto-glossed jargon via `ACRONYM_DEFINITIONS`,
specific rather than boilerplate. Defects cluster at four seams.

#### D1. Literal `&amp;` is visible to users in two help panels — **medium / S**

*Evidence.* `dashboard.js:303` (STEPS `ltc_stress` help) contains the source literal "...entered on
Insurance &amp;amp; LTC Policies." and `:665` (the `pageHelp` 'connections' arg for `spending_dashboard`)
contains "Transactions from Income &amp;amp; Expense Transactions feed...". Both render through `esc()`
(`:1171-1177`, which replaces `&` with `&amp;`): `st.help` is escaped at `:14489`, and `pageHelp()`'s args
at `:1128`. Pre-escaped input therefore double-escapes and the browser renders the visible text `&amp;`.

*Options.* (1) Fix the two literals. (2) Fix them and add a grep-based regression check that no
STEPS/STEP_HELP/pageHelp literal contains an HTML entity. (3) Make `esc()` idempotent by decoding first.

*Recommendation.* **Option 2.** Option 3 masks the authoring mistake at the render layer and makes the next
instance harder to notice. Display-only; no effect on saved plan data.

#### D2. Internal file names and pricing-vendor chains leak onto client-facing sheets — **high / S**

*Evidence.* `src/reporting/sheets_summary.py:1058` writes into the Release Notes block of Sheet 1
(Executive Summary, per the `qc()` call at `:1068`): "Law assumptions are data-driven in tax_data.py /
tax_constants.csv; see Methodology for tax-year provenance." `:1061` on the same sheet reads "Live ETF
prices use FMP → Yahoo → Alpha Vantage → Stooq → cache → cost basis...".
`src/reporting/sheets_qc_reference.py:123` (Sheet 22, Glossary) defines SALT Cap as "State and Local Tax
deduction cap — schedule sourced from tax_data.py" instead of stating the cap. Both references are also
**stale**: `tax_data.py` was merged into `taxes.py`, evidenced by the `# ===== BEGIN tax_data.py =====`
banner and embedded docstring at `src/taxes.py:1-16`.

*Options.* (1) Rewrite in plain language, sourcing the SALT figures from the schedule already computed in
`sheets_summary.py:1249-1254`. (2) Delete internal provenance from the client-facing Executive Summary and
Glossary entirely; move build detail to the existing advisor-facing "21. QC Summary" sheet. (3) Just swap
`tax_data.py` for `taxes.py`.

*Recommendation.* **Option 2, with Option 1's plain-language SALT definition.** The consolidation has
already broken this reference once, and the Executive Summary is the most-viewed sheet — the fix should
stop internal build detail reaching it at all, not re-point it at the current filename.

*Correction applied.* The original finding cited a "Consolidations section" in `documentation/CLAUDE.md` as
proof of the merge. **That section does not exist**, and `CLAUDE.md` mentions none of `taxes.py`,
`tax_data.py` or `tax_constants`. The proof is `src/taxes.py:1-16` itself. Substantive finding confirmed;
citation corrected.

#### D3. RMD age: the QC note claims a birth-year nuance the engine does not implement — **medium / S**

*Evidence.* `src/reporting/sheets_qc_reference.py:70-72` (Sheet 21, Modeling Adjustments) states "RMDs
computed at year-start balance; satisfied before year-end; SECURE 2.0 age-75 for those born 1960+" —
implying a cohort rule. `:121` (Sheet 22, client Glossary) states flatly "mandatory annual withdrawals from
tax-deferred accounts starting at age 75" with no qualifier.

*Options.* (1) Add the birth-year qualifier to the glossary entry ("age 73 or 75 depending on birth year").
(2) Keep the glossary generic and point to the computed value ("the starting age depends on birth year
under current law — see this household's applicable age on the RMD & Conversions sheet"). (3) Cross-
reference only.

*Recommendation.* **Option 2 — but sequenced *after* the engine fix (P2).** The reviewer's original framing
(two contradictory ages in one tab) was corrected on cross-check: these are two different sheets with two
different audiences, and — critically — **the engine implements no birth-year-conditional RMD age at all**;
it is a flat configurable default. So today the QC note is the wrong one, not the glossary. Once P2 makes
the engine derive the age from DOB, Option 2's wording becomes true and the QC note becomes accurate. Fixing
the copy first would document behaviour the system does not have.

*Severity note.* Downgraded from the reviewer's "high" to medium, for the reason above.

#### D4. `write_cell()` has no wrap option; long narrative strings go into merged cells — **medium / M**

*Evidence.* `src/reporting/workbook_common.py:107-118` defines `write_cell(...)`; its `Alignment()` call at
`:111` never sets `wrap_text` and there is no parameter for it — unlike the column-autofit logic in the same
file (`:653`, `:812-831`). `sheets_summary.py:1063-1066` writes ~140-character strings via `write_cell()`
then merges A:F (`:1065`) at default row height; `sheets_qc_reference.py:135-138` does the same for the
Glossary Definition column, merging B:D per row.

*Options.* (1) Add `wrap_text=False` to `write_cell()` and opt in at the ~3 narrative call sites.
(2) Add a `write_narrative_cell()` (wrap + row-height autofit by default) alongside `write_cell()`, mirroring
the existing `write_hdr` / `write_cell` split. (3) Build a workbook and check visually before changing code.

*Recommendation.* **Option 3 first, then Option 2 if confirmed.** This defect is inferred from code, not
observed in a rendered workbook — this review was read-only. Verify by building and inspecting the Executive
Summary Release Notes and the Glossary Definition column before spending effort. If confirmed, Option 2
makes prose vs. tabular content structurally distinct so the omission cannot silently recur.

#### D5. PDF margins are 0.22" on all sides — **medium / S**

*Evidence.* `src/reporting/enterprise_pdf.py:60` sets `MARGIN = 0.22 * inch`, applied symmetrically at
`:384` for every landscape-letter page. The module docstring (`:15`) confirms the intent. Common consumer
and office printers enforce a non-printable margin of roughly 0.17"-0.25", so content laid to the edge can
clip when physically printed even though it displays correctly.

*Options.* (1) Raise `MARGIN` uniformly to 0.3"-0.35". (2) Differentiate by sheet type (tight for wide data
tables, 0.5" for narrative sheets). (3) No code change; document the workbook and in-app explorer as the
print-safe paths.

*Recommendation.* **Option 1.** One-line constant change with no layout-strategy risk, since the module
already re-flows wide sheets into repeating column bands — a larger margin only shifts where band
boundaries fall. **Unverified**: flagged from the constant and docstring, not from a printed sample.

#### D6. "Roth conversion" nav label is lowercase-c while every cross-reference capitalizes it — **low / S**

*Evidence.* `dashboard.js:212` sets `title: "Roth conversion"`. Cross-references at `:43`, `:52` and `:245`
all say "Roth Conversion page". Sibling STEPS entries use Title Case ("Household & People", "Work Income",
"Special Strategies").

*Options.* (1) Capitalize the nav title (1 line). (2) Lowercase the 3 cross-references plus the STEP_HELP
title at `:614` (4 locations). (3) Leave it.

*Recommendation.* **Option 1.** Smallest diff, matches the existing convention. No routing depends on
titles (STEP ids are used).

---

### 2.4 Test quality

180 files, ~975 test functions, all in one flat `tests/` directory with no convention separating unit,
integration, golden-master and e2e. The same behaviour is asserted at multiple altitudes while some real
journeys are never exercised end-to-end.

#### Q1. Many tests grep raw source text instead of calling the code — **high / M**

*Evidence.* Confirmed in `tests/test_126_service_extraction.py:22-48`,
`test_153_report_service_extraction.py:5-28`, `test_154_spending_service_extraction.py:4-29`,
`test_155_strategy_asset_service_extraction.py:4-28`,
`test_156_plan_data_budget_service_extraction.py:4-33`,
`test_159_portfolio_security_service_extraction.py:8-34` (same shape across all 10
`tests/*extraction*.py`), plus `test_93_architecture_completion_exhaustive.py:14-90`,
`test_149_roadmap_steps_1_11_static.py:10-38`, `test_137_roadmap_usability_surfaces.py:6-70`. Pattern:
`text = Path('src/....py').read_text(); assert 'def some_func' in text; assert '@app.route' not in text`.

*Options.* (1) Delete the grep pairs, keep the behavioral tests each file already has. (2) Replace with one
shared AST-based check that walks `src/server_services/*.py` and asserts no `flask`/`werkzeug` import.
(3) Leave as-is.

*Recommendation.* **Option 2.** Consolidate the "no HTTP leakage" guardrail into one static check, delete
the ~18 duplicated substring assertions, and keep the genuine behavioral tests (e.g.
`test_155:69-108`, `test_156:36-69`).

*Correction applied.* The finding's framing ("instead of calling the code") was overstated: every cited
file **also** contains real behavioral tests — `test_155:31-108` constructs `StrategyAssetService` with
fake context callbacks; `test_156:36-69` round-trips real CSV writes; `test_153:31-61` does real I/O. The
accurate statement is "text assertions live alongside behavioral tests in the same files". Also, some
substring checks are *negative structural* claims about where code lives, which a call-the-code test
genuinely cannot make — those are candidates for AST-hardening, not conversion.

#### Q2. No test drives a real HTTP journey against a real build — **high / M**

*Evidence.* `tests/test_161_phase2_live_workflow_journeys.py:34-44` replaces `_run_build_progress_job` with
`fake_progress_job`; `:70-75` replaces `report_service.detailed_results_payload` with a hand-written dict.
`conftest.py:34-76` (`built_workbook_dir`, the only real subprocess build) is consumed by exactly 5 files
(`test_94, 95, 97, 100, 101`), none of which touch `/api/build/start` or `/api/results-explorer`.
`test_optional_module_gating.py:38-50` runs a second real build but stays at the filesystem/zip level.

*Options.* (1) Add one true e2e test: `test_client` POSTs `/api/build/start` with real workspace data, polls
`/api/build/progress` to real completion, GETs `/api/results-explorer/index`, asserts on real sheet content.
(2) Point the read-side routes at the already-built session fixture's output dir — cheaper, but does not
prove the trigger path. (3) Rename `test_161` to reflect that it tests route plumbing, and track the gap.

*Recommendation.* **Option 1, with Option 2 as a cheap add-on, and Option 3's rename regardless.** Mark the
e2e test slow/optional so it does not run on every commit (`built_workbook_dir` already uses a 180s
timeout). The rename is free and stops the file claiming coverage it does not provide.

#### Q3. PDF output is checked for existence only — **medium / M**

*Evidence.* `tests/test_phase5_validation_maturity.py:204-213` asserts `pdf_path.exists()`, first 5 bytes
`%PDF-`, and size >1024 bytes. No test opens the PDF. `src/reporting/enterprise_pdf.py` (win32com
Excel→PDF) is referenced by no other test file.

*Options.* (1) Extract text with pypdf/pdfminer and assert on section titles and key figures. (2) Assert
page count (~20) and per-page size bounds. (3) Leave as-is.

*Recommendation.* **Option 2 as a fast baseline; Option 1 behind a slow marker for the sections that
matter.** COM-exported PDFs can embed text as images, so text extraction is inherently more brittle than
xlsx cell checks — do not over-invest. Option 2 still catches the real failure mode ("half the report
rendered blank").

#### Q4. Frontend test coverage is thin relative to the JS surface — **high / L**

*Evidence.* `dashboard.js` is 16,613 lines (not ~1,670 as the briefing claimed — see A6), and
`reports_ui.js`, `planning_workbench_ui.js`, `spending_dashboard.js` and the `dashboard_decomp_*` files add
roughly 6,000-7,000 more. `tests/frontend/` has exactly 6 files (~1,419 lines) importing only
`frontend/js/modules/{tax_helpers,allocation,admin_ui,roth_ui}.mjs` plus a pure-function sandbox
(`tests/frontend/load_dashboard.mjs`).

*Options.* (1) Extract more pure logic into `frontend/js/modules/*.mjs` following the existing pattern and
add `node:test` suites. (2) Add DOM-level tests via jsdom or Playwright component tests. (3) Rely on
Python-side API contract tests.

*Recommendation.* **Option 1 first, targeting the *live* modules** — `reports_ui.js`,
`planning_workbench_ui.js`, `spending_dashboard.js`, and the `dashboard_decomp_*` files. Option 2 for the
highest-traffic screens once the extraction backlog is smaller.

*Conflict resolved.* The reviewer named `dashboard_spending_module.js` and `dashboard_strategy_module.js`
as test targets. Those are two of the five **dead** files A5 recommends deleting — nothing loads them.
Retarget to the live modules above. See §3.

#### Q5. `person_labels.py` has no dedicated test file — **medium / S**

*Evidence.* `src/person_labels.py` defines `member_nick`, `display_accounts_in_text`, `display_account`
(`:11`, `:27`, `:40`) and is imported by 5 reporting modules (`reporting/dashboard.py`,
`sheets_summary.py`, `sheets_stress.py`, `sheets_strategy.py`, `sheets_qc_reference.py`). No test file
imports `person_labels` or `render_label` — zero matches.

*Options.* (1) Add `tests/test_person_labels.py` exercising the three functions against nicknamed,
unnamed/default and single-filer configs, with no workbook or projection involved. (2) Rely on incidental
coverage via `workbook_snapshot_expectations.json` text checks.

*Recommendation.* **Option 1.** Cheapest, highest-value gap in the whole review: S effort, pure functions,
and it protects a rule the team has already had to write into project memory once. Option 2's feedback loop
is a giant workbook diff, and the sample plan exercises only one nickname combination.

#### Q6. The primary golden master is pinned to a live, frequently-edited real plan — **medium / M**

*Evidence.* `tests/test_2_recommendations.py:31-150+` carries ~120 lines of changelog-style comments (items
141, 142, 143, 165, 166, 167, 168, 169, 185) each explaining a terminal-net-worth or lifetime-tax shift
after a plan-data or engine edit, with exact dollar figures requiring manual re-derivation
(`documentation/CLAUDE.md:70-86`). Meanwhile `tests/fixtures/golden_master_engine_cases.json` defines 5
isolated synthetic scenarios (`baseline_balanced_couple`, `no_voluntary_roth_policy`,
`high_spending_pressure`, `lower_return_environment`, `early_survivor_compression`) used by **one** file,
`test_phase5_validation_maturity.py`.

*Options.* (1) Demote `test_2`'s dollar-exact pins to structural assertions (row count, zero validation
failures — `:114-116`), keeping them as a warn-only diagnostic. (2) Promote the 5-scenario synthetic fixture
to the mandatory CI gate; make `test_2` informational. (3) Leave as-is.

*Recommendation.* **Option 1 combined with Option 2.** This separates "did the engine break" (synthetic
scenarios, stable) from "did the sample plan's data change" (expected and frequent). The 9 dated comment
entries are evidence that the current design fights routine data churn. **This is the enabling change for
the entire financial-planning workstream** — see §3.

*Caveat.* Synthetic scenarios may not catch bugs that only manifest with the real plan's feature
combination (DAF, dividend reinvestment, TLH); periodically sync scenario coverage against real-plan feature
usage.

#### Q7. `tests/test_scenario_canonical_run_validation.py` contains zero test functions — **low / S**

*Evidence.* Full file (7 lines): imports `Path`, `subprocess`, `sys`, defines `ROOT`, nothing else.

*Options.* (1) Delete. (2) Reconstruct the intended test from git history.

*Recommendation.* **Option 1**, and if the name points at a real gap (scenario save/restore determinism),
track it as a new, intentionally-scoped test rather than resurrecting a stub with no surviving intent.

#### Q8. Six overlapping Roth-UI point-fix test files — **low / M**

*Evidence.* `test_28_roth_legacy_objective.py`, `test_v8_3_roth_ui_build_handoff.py`,
`test_104_roth_comparison_component_scores.py`, `test_withdrawal_roth_ui_cleanup.py`,
`test_roth_controls_visible.py`, `test_roth_user_ui_render_fix.py` each independently assert Roth
schema/field presence — e.g. `test_withdrawal_roth_ui_cleanup.py:18` and `test_roth_controls_visible.py:35`
both check the same Roth user-page layout from different historical bugs, with no shared fixture.

*Options.* (1) Consolidate into one `test_roth_ui_behavior.py` organized by behaviour area rather than fix
date. (2) Rename for discoverability only.

*Recommendation.* **Option 1, low priority.** Hygiene, not risk — batch it opportunistically the next time
someone touches Roth UI schema.

---

### 2.5 Financial planning

The engine is unusually deep for a single-practitioner tool: the SS claiming sweep
(`sheets_strategy.py:113-250`), the IRMAA two-year MAGI lookback (`core.py:738`), the survivor filing-status
switch and SS step-down (`deterministic_engine.py:481-494,853-873`), the ACA premium-tax-credit guardrail
on conversions (`planning_engines.py:1040-1047`), and asset-class-covariance Monte Carlo with stochastic
mortality and health shocks are all things most commercial software omits or hides. Weaknesses cluster in
three places: terminal/legacy math, absent statutory mechanics, and a handful of point defects.

#### P1. Post-Tax Inheritance charges capital-gains tax on stepped-up assets — **critical / S**

*Evidence.* `src/after_tax.py:120-147` computes federal LTCG, NIIT and state tax on the full unrealized
gain in terminal taxable accounts; `:219` subtracts it to produce `after_tax_terminal_nw`; `:229` defines
`post_tax_inheritance` from it. `src/planning_engines.py:1327-1329` makes `after_tax_terminal_nw` the
dominant term of the Roth objective (`:1452`: `terminal_component = terminal_weight * after_tax_terminal_nw`).
The projection models §1014 correctly during life: `planning_engines.py:317-323,333-335` set `basis_free`
to full balance at first and second death, and `input/client_insurance_estate.csv` documents
`Estate Planning,Step-Up,basis_step_up_at_death,TRUE`.

*Options.* (1) Apply step-up in the terminal metric — zero the deferred gain when `basis_step_up_at_death`
is true and the terminal year is a death year, scaled by `_basis_step_fraction_for_death` so the
community-property/common-law regime switch still matters. (2) Report both
`post_tax_inheritance_if_liquidated` and `post_tax_inheritance_at_death`, pointing the optimizer at the
death version. (3) Add a `terminal_step_up_in_pti` toggle defaulting on.

*Recommendation.* **Option 1, with the property-regime fraction respected.** This is not a modelling
preference: charging capital-gains tax on assets whose basis the same codebase steps up two functions away
is internally inconsistent, and because the term dominates the Roth objective it systematically recommends
more conversion than the tax law justifies. Option 2's two similar-looking client-facing numbers invite
confusion; Option 3 leaves a wrong default reachable.

*Risk.* Every scenario comparison and Roth recommendation shifts; the direction (less conversion) may
contradict advice already given to the live client. Requires golden-master regeneration and a
`GOLDEN_MASTER_CHANGELOG.md` entry.

*Depends on:* P9 (estate-tax penalty scoping) — do them together so the terminal metric is coherent.

#### P2. RMD start age is a static 75, never derived from DOB — **critical / S**

*Evidence.* `src/planning_engines.py:459-463` reads `rmd_start_age` (default 75) plus per-member overrides;
`src/data_io.py:852-853` and `:1570-1571` parse it from `Model Constants,Retirement,rmd_start_age` with a
hardcoded '75' fallback; `reference_data/schema.csv:27` declares default 75; `input/client_policy.csv:27`
and `input/client_data.yaml:660-662` ship 75 for both members. Nothing maps birth year to the SECURE 2.0
schedule. `tests/fixtures/legacy_plans/legacy_household.csv:14-15` uses 73, showing the field is expected to
be hand-set.

*Options.* (1) Add `statutory_rmd_start_age(dob_year)` (73 for 1951-1959, 75 for 1960+, 72 earlier), use it
as the default in `data_io.py:852-853`, and keep the explicit field as an override that warns on
disagreement. (2) Validation-only: leave the input authoritative, emit a blocking QC warning. (3) Remove the
field and compute purely from DOB.

*Recommendation.* **Option 1.** The two-year deferral is not a rounding difference — it moves the RMD ramp,
the conversion window end (`planning_engines.py:850` anchors to the same field) and the IRMAA path
together. Option 2 leaves a wrong default for every new plan and warnings get lost in a 25-sheet workbook;
Option 3 loses the ability to model proposed legislation or reproduce a third-party plan.

*Risk.* The live client plan currently runs at 75; correcting it changes RMDs, taxes and the conversion
window for that plan.

*Unlocks:* D3 (the QC-sheet copy becomes true only after this lands).

#### P3. QCDs are recommended in the workbook but modeled nowhere — **high / M**

*Evidence.* `sheets_strategy.py:17` tells the client "Use QCDs for charitable giving to reduce AGI" and
`:424` titles a sheet "CHARITABLE GIVING — Cash vs DAF vs QCD". A case-insensitive search for `\bqcd\b`
across `src/` matches only reporting and UI label files (`sheets_summary.py`, `sheets_strategy.py`,
`sheets_qc_reference.py`, `dashboard.js`, `module_catalog.py`) — **zero** in `planning_engines.py`,
`projection_stages/deterministic_engine.py` or `taxes.py`. No config key reduces `rmd_total` or AGI for a
charitable distribution.

*Options.* (1) Model as an RMD-satisfying AGI exclusion: a per-year `qcd_schedule` (amount, member,
start/end year) with the statutory per-person cap; subtract from the RMD amount entering AGI, deduct cash
from the IRA balance, reduce charitable spending so it is not double-counted; gate eligibility at 70½.
(2) Model as an above-the-line deduction. (3) Add a what-if calculator outside the projection.

*Recommendation.* **Option 1.** The engine already has every hook (`compute_rmds` returns per-owner
amounts; `irmaa_magi_current` and `social_security_taxable_amount` both key off AGI). **Do not take Option
2** — the entire point of a QCD is that it never enters AGI, so a deduction-based model would still let the
excluded dollars drive IRMAA tiers, SS provisional income and the NIIT threshold, producing
plausible-looking but wrong numbers. That is worse than the current honest silence. Option 3 leaves the
projection, Monte Carlo and Roth optimizer blind.

*Risk.* Touching the RMD→AGI path risks regressions in RMD audit, IRMAA and SS taxability. Needs
golden-master coverage before merge.

#### P4. A DAF contribution is cash out with no deduction — **high / M**

*Evidence.* `deterministic_engine.py:961-966` adds `daf_contrib_yr` to `lump_yr` (a spending outflow). The
itemized stack at `:1364-1370` uses `char = max(0, c['char_low'] - 0.005*agi)` and
`item_ded = salt + char + mort_interest_yr` — `char_low` is a fixed annual figure from `data_io.py:865`
(`annual_charitable_giving_low`, default 3000) with no connection to `daf_amount` (`data_io.py:1914`).
Meanwhile `sheets_strategy.py:457` advises "Bundle 3 years of charitable giving into a DAF contribution...
Deduction maximized" and `:549-550` quotes a tax saving computed outside the projection.

*Options.* (1) Route DAF and recurring giving into the itemized stack — annual charitable total = recurring
+ DAF in the contribution year, with the AGI percentage limitation (60% cash / 30% appreciated) and a
five-year carryforward; stop treating DAF grant years as new charitable cash. (2) Deduction without
carryforward. (3) On top of (1), allow DAF funding from appreciated taxable lots using the existing lot
engine.

*Recommendation.* **Option 1 now, Option 3 as a follow-on.** The current state is the worst of both worlds:
the workbook recommends bunching while the projection charges for it and returns nothing, so the Roth
optimizer and Monte Carlo both see DAF funding as pure wealth destruction. Carryforward is required, not
optional, because bunching is by definition large relative to AGI — Option 2 would silently destroy
deduction value in exactly the case the sheet recommends.

*Risk.* The standard-vs-itemized flip in the bunching year moves federal tax materially and ripples into
the withdrawal cascade.

#### P5. The SECURE Act 10-year rule is absent; heirs are scored with a flat rate — **high / L**

*Evidence.* `planning_engines.py:256-257` states IRAs "remain in place as inherited beneficiary accounts
for later SECURE Act handling" and `:330` repeats it, but no later handling exists —
`apply_death_transition` returns at `:338` and the projection ends. The heir cost is a scalar:
`planning_engines.py:1355` reads `roth_heir_ordinary_tax_rate_assumption` and `:1391-1392` multiplies a
blended pre-tax exposure by it; `src/server/app_core.py:706` defaults it to 24%. No beneficiary ages,
incomes or distribution schedules are captured anywhere.

*Options.* (1) Post-death heir drawdown module: capture beneficiary records (relationship, birth year,
assumed bracket, eligible-designated-beneficiary status); after the terminal year run a 10-year schedule per
non-spouse beneficiary, including annual RMDs within the 10 years where the decedent had reached RBD;
report after-tax inheritance per beneficiary. (2) Improve the flat rate to an *effective* 10-year rate by
running the terminal pre-tax balance through a level 10-year distribution against an assumed heir bracket.
(3) Beneficiary-aware bequest routing only, without post-death tax.

*Recommendation.* **Option 2 immediately, Option 1 as the target.** The 10-year rule is the central reason
Roth conversions and charitable IRA beneficiary designations are on the table for high-pre-tax-balance
households, and a flat 24% cannot distinguish a $2M IRA left to a retired child from one left to a surgeon
in peak earnings. Option 2 gets the optimizer honest at low cost while Option 1 is built.

*Depends on:* P8 (beneficiary capture) for Option 1.

*Correction applied.* The finding stated `after_tax.py:31-35` "applies the same flat rate". It applies a
**separate** field (`roth_optimize_terminal_tax_rate`, falling back to `roth_target_rate`, default 0.24) —
so the codebase has *two* independent flat heir/terminal rate assumptions, not one shared rate. This
strengthens rather than weakens the thesis.

#### P6. The IRMAA conversion guardrail is MFJ-hardcoded — **high / S**

*Evidence.* `planning_engines.py:1024-1028` (`fill_to_irmaa`) and `:1050-1054` (the cap inside
`fill_to_bracket`) both read `roth_irmaa_target_threshold_mfj`, falling back to `irmaa_base` / 268000, with
no filing-status branch — even though `filing` is a parameter of `plan_roth_conversion` (`:910`) and is used
for brackets (`:956-959`) and SS taxability (`:970`). The assessment side does it correctly:
`deterministic_engine.py:354-360` selects `IRMAA_TIERS_BASE_YEAR.get(filing, ...)`, and the tables are keyed
by filing status (`src/taxes.py:82`). The survivor filing switch is real
(`deterministic_engine.py:481-493`).

*Options.* (1) Resolve the target threshold from `IRMAA_TIERS_BASE_YEAR[filing]` at the configured
`roth_irmaa_target_tier`, keeping the scalar as an explicit override. (2) Halve the MFJ threshold when
filing is not MFJ. (3) Warn only.

*Recommendation.* **Option 1.** The dataset is already keyed by filing status and the assessment path
already uses it — this is a one-line lookup closing an inconsistency between how the model *prices* IRMAA
and how it *avoids* it. Widow's-penalty years are exactly where IRMAA discipline matters most. Option 2 is
a hidden fudge factor that is wrong at the top tiers, where Single and MFJ are not a clean 2:1.

*Risk.* Cuts survivor-year conversions sharply; changes golden masters.

#### P7. Spousal SS is paid before the worker spouse files — **high / S**

*Evidence.* `deterministic_engine.py:831-844` computes the spousal top-up as
`max(own_benefit, 0.5 * other_pia * factor)` and folds it into `h_monthly_claim`/`w_monthly_claim`. Payment
is gated only on the claimant's own start year: `:846-851` pay `h_ss` whenever `year >= h_ss_yr` and `w_ss`
whenever `year >= w_ss_yr`, with no reference to the other spouse's claim year. The comment at `:832-834`
says "once both spouses have claimed" — the code does not enforce it. The FRA cap on the spousal factor
(`:835-842`) is correct, so the defect is specifically the missing filing precondition.

*Options.* (1) Compute the top-up per year rather than once, applying it only when the other member's claim
year has been reached; pay the claimant's own reduced benefit before that and step up when the worker files.
(2) Warn on the inconsistent combination. (3) Default `spousal_benefits_enabled` to FALSE
(`data_io.py:809` currently TRUE).

*Recommendation.* **Option 1.** The classic case — higher earner delays to 70, lower earner claims at 62 —
is precisely the pattern the claiming sweep at `sheets_strategy.py:113-250` explores, and it is the case
this defect overstates, by up to eight years of an inflated benefit. Because the sweep scores all 81 age
pairs against the full projection, the error also distorts which claiming strategy the tool recommends.
Option 2 would fire constantly on the most common strategy while leaving the numbers wrong; Option 3
understates income for single-earner households.

*Risk.* Reduces early-retirement income in split-claiming plans, cascading into larger portfolio draws and
possibly different recommended claim ages. Requires moving the calculation inside the year loop — a small
restructure of a hot path.

#### P8. No beneficiary designation or titling capture for retirement/taxable accounts — **high / M**

*Evidence.* `input/client_holdings.csv` carries only `account,symbol,purchase_date,shares,purchase_price,
lot_type`. The account registry in `src/core.py` (`build_registry_from_balances`,
`build_registry_from_json`) keys on owner index and tax treatment only — `_infer_owner`/`_infer_type` derive
from the account name string. No titling field (JTWROS, tenants in common, TOD/POD, trust-titled) exists
anywhere. The estate section of `input/client_insurance_estate.csv` captures CST, QTIP, portability and the
step-up regime, but nothing about who is named on which account.

*Options.* (1) Account-level beneficiary and titling fields plus an audit sheet flagging the classic
failures: no contingent named, ex-spouse still primary, minor named outright, trust named as IRA
beneficiary without see-through language, estate named by default, JTWROS defeating a credit-shelter plan,
community-property assets titled to defeat the double step-up. (2) A household-level designation checklist
with a last-reviewed date. (3) Titling only, driving `_basis_step_fraction_for_death`
(`planning_engines.py:237-243`) per account instead of one household `property_regime`.

*Recommendation.* **Option 1, with the titling half wired into the step-up model as in Option 3.**
Beneficiary designations override the will and are the most frequent real-world estate failure; a tool that
models QTIP funding and credit-shelter trusts in detail but cannot say whether the IRA still names an
ex-spouse has an inverted priority. The audit sheet is also the highest-value *client-facing* deliverable in
this entire report, because it produces action items rather than projections. Option 2 cannot reconcile
against actual accounts and will drift from the holdings file.

*Correction applied.* The finding claimed 529s and special-needs are "the only beneficiary fields in the
system". Life insurance policies in `input/client_insurance_estate.csv` also carry a `beneficiary` field
(e.g. `Insurance In Force,Life_Term_Matthew,beneficiary,Member 2`), parsed at `src/data_io.py:527` and
surfaced at `src/reporting/sheets_protection.py:70`. This does not rescue the finding — the gap for
retirement and taxable accounts is real as described — and the life-insurance field is a useful **precedent
pattern already in the schema** to model the new fields on.

*Risk.* Beneficiary data is sensitive and will sit in the local SQLite store and CSV exports; confirm backup
and export paths handle it appropriately.

#### P9. The estate-tax penalty uses the maximum estate tax across every row — **medium / S**

*Evidence.* `planning_engines.py:1438-1447`: `_estate_tax_for_row` computes federal and Illinois estate tax
on a row's `total_nw`, and
`estate_tax_penalty = estate_mult * max((_estate_tax_for_row(r) for r in rows), default=0.0)`. This
penalizes peak net worth in any single year — typically early or mid-plan — rather than the estate actually
transferred at the second death. The correctly-scoped version already exists at `src/after_tax.py:188-206`
(`estimate_terminal_estate_tax`, using the terminal row plus business interests and the CST exclusion). The
penalty feeds the objective at `:1455` and is doubled in ESTATE_TAX_AWARE mode (`:1472-1473`).

*Options.* (1) Evaluate at the death rows, reusing `estimate_terminal_estate_tax` so objective and reported
PTI agree. (2) As (1), but present-value it using the existing `roth_tax_discount_rate` so it is
commensurate with the already-discounted `lifetime_tax` term (`:1335-1337`). (3) Keep max-across-rows,
renamed `peak_estate_tax_exposure`, as a reported risk indicator.

*Recommendation.* **Option 2, retaining the peak as a reported metric per Option 3.** The lifetime-tax term
is already present-valued, so a nominal estate tax thirty years out is not commensurate with it. The
Illinois cliff structure (implemented at `core.py:916`; `client_insurance_estate.csv` notes "no
portability; cliff structure") does make peak exposure worth *showing* — just not worth optimizing against.

*Risk.* Changes strategy ranking in ESTATE_TAX_AWARE and LEGACY_OPTIMIZED modes.

#### P10. Unlisted states are silently taxed as Illinois; state brackets never inflate — **medium / M**

*Evidence.* `src/core.py:746`:
`rules = STATE_TAX_RULES.get(state, STATE_TAX_RULES.get('Illinois', ...))` — an unrecognized state falls
back to Illinois' 4.95% flat rate with `exempt_retirement: True`, **with no warning**. `src/taxes.py:119-175`
defines only Illinois, Indiana, Florida, Texas, Tennessee, North Carolina, Arizona, Colorado, Nevada,
California and New York. Graduated schedules at `core.py:777-787` cover only CA and NY, and `_bracket_tax`
(`:768-774`) applies them with **no inflation factor**, unlike federal brackets which use `inflate_brackets`
(`:675-678,683`). Cost-of-living factors (`taxes.py:201-214`) cover the same eleven states, falling back
to 1.0.

*Options.* (1) Fail loudly and expand to 50 states via `reference_data/state_tax.csv` (the overlay loader
at `taxes.py:257-305` already supports it), and inflate state brackets with `brk_inf`. (2) Fail loudly,
keep current coverage, document the tool as covering those eleven states. (3) Zero-rate fallback with a
prominent caveat.

*Recommendation.* **Option 2 now, Option 1 as an annual-maintenance project; fix bracket inflation
alongside either.** The immediate defect is the silence, not the coverage: a planner running a Minnesota or
New Jersey client today gets a plausible-looking Illinois number with a retirement-income exemption those
states do not grant, and nothing on any of the 25 sheets says so. The State Residency optimizer sheet makes
this worse by inviting exactly the cross-state comparison the data cannot support. Option 3 replaces a
wrong number with an optimistic one. Fifty states of exclusions, thresholds and estate regimes is a real
annual commitment that the maintenance runbook must own.

*Risk.* Turning the fallback into an error may break saved plans or fixtures carrying an unrecognized state
string — inventory those first.

#### P11. Lifetime gifting is display-only — **medium / M**

*Evidence.* `src/data_io.py:1368` parses `gift_excl` from
`Estate Planning,Gifting,annual_exclusion_per_donee`; its only consumer is
`sheets_strategy.py:984`, which prints it as text. `data_io.py:2482-2483` sets `c['gift_exclusion'] = 19000`
and `c['gifting_plan'] = {}` — the plan dict is never read anywhere. The estate base is computed from
`total_nw` (`after_tax.py:197-203`, `planning_engines.py:1439-1442`), so nothing reduces the estate for
gifts made and no lifetime-exemption use is tracked against `fed_exempt`.

*Options.* (1) Gifting schedule with exemption tracking: donee, annual amount, start/end year, funding
account; remove gifted dollars from the funding account and the estate base; track cumulative lifetime-
exemption use; handle direct 529 and medical/tuition payments as separate non-exclusion categories.
(2) Annual-exclusion gifting only. (3) Gifting as a Planning Workbench scenario lever.

*Recommendation.* **Option 1, and carryover basis on gifted appreciated assets must be part of the build** —
the gift-versus-bequest tradeoff is precisely basis step-up against estate-tax exclusion, so omitting it
would produce a systematically pro-gifting answer. The plan already models an Illinois estate with a $4M
exemption and a cliff against a household well past it, and systematic gifting is the standard response.
Option 2 cannot model the large lifetime-exemption gift that is the actual planning decision; Option 3 does
not persist or compound.

*Risk.* Introduces a second path mutating account balances outside the withdrawal cascade; needs care
around the reserve floor and Monte Carlo.

#### P12. IRMAA's first two plan years use current-year AGI; no SSA-44 modelling — **medium / S**

*Evidence.* `src/core.py:738-742`: `irmaa_lookback_magi` returns `current_agi` whenever
`len(rows) < lookback_years`, so plan years one and two are assessed on their own AGI rather than the
client's actual MAGI from the final working years. There is no config field for historical MAGI — a search
for `magi_lag`/`lookback` across `src/` returns only `core.py:738` and `deterministic_engine.py:1400-1405`.
Nothing models an SSA-44 life-changing-event appeal.

*Options.* (1) Capture two historical MAGI inputs to seed the lookback, plus a per-member "work stoppage —
SSA-44 filed" flag suppressing the surcharge from a stated year. (2) Historical MAGI only, with the appeal
as a note. (3) Leave as-is and document the approximation.

*Recommendation.* **Option 1.** For a client retiring into Medicare, the first two IRMAA years are driven by
peak working-year income and are frequently the largest surcharge they will ever face — the current model
shows them a low retirement AGI and therefore no surcharge, which is precisely backwards. The SSA-44 flag is
the necessary counterweight; without it, Option 2 swings the error to the other extreme. Caveat the flag as
an outcome that is *granted*, not guaranteed.

*Risk.* Adds onboarding data existing saved plans will not have; needs a sensible default and a preflight
prompt.

#### P13. Monte Carlo holds spending fixed in every path — **medium / M**

*Evidence.* `planning_engines.py:1671-1691` defines `_funding_success` as a binary threshold on spendable
assets (home-equity variant `:1691-1717`); `_percentiles` (`:1737-1760`) reports `success` as the share of
paths above it. The paths are sophisticated — asset-class covariance (`:1862`), serial correlation
(`:1896`), stochastic inflation (`:1910-1912`), health shocks (`:1947-1949`), stochastic mortality
(`:359-380`) — but a search for guardrail/Guyton/ratchet/dynamic-spend logic in the withdrawal path returns
only the IRMAA and ACA guardrails on *conversions*. No path reduces spending in response to a drawdown, and
no output states the cut a client would have to make.

*Options.* (1) Guardrail spending policy per path (Guyton-Klinger, or a withdrawal-rate band), reporting the
realized-spending distribution alongside the success rate. (2) Keep spending fixed but, for each failing
path, compute the uniform spending reduction that would have made it succeed, and report the distribution of
required cuts. (3) Essential-vs-discretionary success tiers using the existing category structure.

*Recommendation.* **Option 2 first, then Option 1.** Option 2 is cheap, does not disturb the success
definition or the golden masters, and immediately converts an unhelpful binary ("you have a 78% chance")
into the sentence a planner actually says ("in the worst outcomes you would need to trim about 12% of
discretionary spending from your mid-70s"). Option 1 is the more realistic model but should follow, with
the spending distribution reported next to the success rate so the higher number is never read alone —
otherwise it reads as gaming the metric. Option 3 requires essential/discretionary tagging the current
taxonomy may not cleanly support.

*Risk.* Adding a dynamic policy changes the meaning of the headline success rate; previously published
figures become non-comparable.

---

## 3. Cross-cutting analysis

### 3.1 Where the experts agree

**Consolidation waves left residue, and the residue lies.** Architecture, usability and quality
independently found artifacts of prior refactors that no longer match reality: 1,640 lines of unloaded
frontend modules (A5), a 14-stage pipeline where nothing runs (A2), a `CLAUDE.md` line understating its
largest file by 10x (A6), a zero-caller query module whose docstring misled this review's own recon pass
(A10), a zero-test stub file (Q7), and a working navigator whose call site vanished (U1). Separately,
documentation found a client-facing sheet citing a Python module that no longer exists (D2). The common
failure is not the leftover code — it is that the leftovers make **confident, false claims** about the
system, and each one has already misled a reader.

**Test structure fights routine change instead of catching regressions.** Quality found the primary golden
master pinned to a live plan that changes often (Q6, nine dated changelog entries) while an isolated
synthetic fixture sits used by one file. Architecture independently found a production code path disabled
whenever pytest is imported (A7). Both are the same pathology: the suite is shaped around what was easy to
assert, not around what would break.

**The engine's internals are more honest than its narrative layer.** The projection models §1014 correctly
during life but not at the terminal metric (P1); it assesses IRMAA by filing status but avoids it by an
MFJ-only threshold (P6); it names the SECURE Act in comments but scores heirs with a flat rate (P5); it
recommends QCDs and DAF bunching in the workbook while modeling neither (P3, P4). Documentation found the
mirror image: sheets asserting nuance the engine does not implement (D3). In every case the *prose* is
ahead of the *code*.

### 3.2 Conflicts, named and resolved

**Conflict 1 — delete the dead frontend modules (A5) vs. write tests for them (Q4).** The quality reviewer
named `dashboard_spending_module.js` and `dashboard_strategy_module.js` as targets for new `.mjs` test
suites. These are two of the five files A5 recommends deleting: `index.html:92-111` does not load them,
`dashboard_module_loader.js` is referenced only by itself, and
`dashboard_income_module.js:141-142` still queries `h_ss_benefit`/`w_ss_benefit` selectors that match
nothing in the live frontend.

*Resolution: A5 wins; Q4 is retargeted.* Q4's reasoning — "these large modules have no tests" — is correct
and its target list was simply built from a filename glob rather than from `index.html`'s script list. The
correct targets are the modules that actually load: `reports_ui.js`, `planning_workbench_ui.js`,
`spending_dashboard.js`, and the six live `dashboard_decomp_*` files. Delete the five dead files first, so
the test backlog is written against the real surface.

**Conflict 2 — U1 says restore orphaned frontend code; A5/A10/A14/Q7 say delete orphaned code.** Both
positions are stated as general principles and they point opposite directions on superficially identical
evidence ("this code has no caller").

*Resolution: the distinguishing test is whether the code was ever wired.* U1's navigator has CSS shipped in
the stylesheet, persisted localStorage state, and a *live* function (`setDetailedResultsNavOpen`, still
called from `dashboard.js:12154-12159` with a comment assuming the tree is visible) — it is a **regression**:
working code whose call site was lost, most likely in `2cb59c6`. A5's modules, A10's query API and A14's
optimizer were **never wired**: no HTML loads them, no route reaches them, and A5's modules contain field
names that a completed migration removed, proving nobody has maintained them. Restore regressions; delete
never-wired scaffolding. Adopt this as the standing rule, because this codebase now has four instances of
the latter and will accumulate more.

**Conflict 3 — A6/A13 recommend verbatim global extraction; Q4 recommends `.mjs` module extraction.**
Global-scope extraction is untestable in isolation by construction; `.mjs` extraction is testable but far
slower per cluster and requires surfacing every implicit global into an explicit context.

*Resolution: split by content type, not by file.* Use verbatim global extraction for the **bulk movement**
of render/DOM code — 16,613 lines need navigability more than they need encapsulation, and this matches the
six live files and the most recent decomposition commit. Use `.mjs` extraction for **pure computation
only** (formatting, budget math, YTD blend logic, allocation preview math), which is what
`tax_helpers.mjs`/`allocation.mjs` already demonstrate and what Q4 actually needs to write tests against.
These are complementary passes over the same clusters, not competing strategies: extract the cluster
verbatim first, then lift its pure functions into a sibling `.mjs`.

**Conflict 4 — D3 wants the RMD glossary copy fixed; P2 wants the RMD engine behaviour fixed.** Fixing the
copy first would document a birth-year rule the engine does not implement; fixing the engine first makes
one of the two existing prose statements true and the other actionable.

*Resolution: engine first, copy second, as a single sequenced pair.* This also resolves the cross-check
correction on D3 — the reviewer read it as a same-sheet self-contradiction, but the two statements sit on
different sheets for different audiences, and the QC note (Sheet 21) is the one making a claim the code
cannot back. After P2 lands, update both.

**Conflict 5 (implicit) — Q6 wants golden masters loosened; P1/P2/P6/P7/P9 will all move golden masters.**
These are not opposed, but their ordering is load-bearing and neither reviewer saw the other's list.

*Resolution: Q6 is a hard prerequisite for the planning workstream.* See below.

### 3.3 The one change that unlocks the most

**Restructure the golden-master gate (Q6) before touching the engine.**

Five of the six financial-planning fixes I am recommending — P1 (step-up), P2 (RMD age), P6 (IRMAA filing
status), P7 (spousal SS gating), P9 (estate-tax scoping) — each move terminal net worth and lifetime tax on
the live sample plan. Under the current design, each one requires manually re-deriving dollar-exact pins in
`tests/test_2_recommendations.py` and writing a changelog paragraph
(`documentation/CLAUDE.md:70-86`). Five sequential fixes therefore cost five rounds of golden-master surgery
*and* make it nearly impossible to tell whether a given dollar shift came from the fix you intended or from
an unrelated plan-data edit.

Promoting the 5-scenario synthetic fixture (`tests/fixtures/golden_master_engine_cases.json`) to the
mandatory gate, and demoting `test_2`'s pins to structural assertions plus a warn-only diff, separates *did
the engine change* from *did the data change*. That in turn makes the whole planning workstream
parallelizable rather than strictly serial — the single biggest schedule lever in this report.

Two smaller unlocks worth naming:

- **A2 (honest pipeline) gates A3 (engine decomposition).** You cannot verify an extracted stage against an
  event log that reports `completed` for stages that never ran.
- **A8 Option 1 (explicit imports) gates A8 Option 2 (splitting the hub) and A9 (moving `module_status`).**
  With F403 suppressed across twelve modules, no tool can currently tell you what depends on what.

---

## 4. Recommendation

### The plan

**Four waves, in this order. The engine work is deliberately gated behind a test-infrastructure change.**

**Wave 1 — Free deletions, honest documentation, and the test gate.** Everything here is either purely
subtractive, purely additive, or a one-line copy fix. Nothing depends on anything else, so it all runs
concurrently. This wave also lands the golden-master restructure (Q6) and the `person_labels` unit tests
(Q5) that Wave 2 depends on.

**Wave 2 — Financial correctness.** P1+P9 together (coherent terminal metric), P2 (RMD age from DOB), P6
(IRMAA by filing status), P7 (spousal SS gating). These are the defects that produce numbers an advisor
could not defend. They run in parallel once Wave 1's gate exists; each lands with a regenerated synthetic
baseline and a changelog entry.

**Wave 3 — Structural debt and user-facing improvements.** Restore the Detailed Results navigator (U1), the
multi-column form grid (U2), the help-pane collapse (U3), the spending accordion (U4), the
expand-all-columns control (U5); the A4 double-projection fix; A2's pipeline honesty; A3's cycle break;
A8's explicit imports and A9's module move; A7's backfill extraction; A13's helper deduplication; A11's
exception narrowing; the Q1/Q2/Q3 test restructuring.

**Wave 4 — New planning capability.** P3 (QCD), P4 (DAF deduction), P5 (heir 10-year rate, then module),
P8 (beneficiary/titling capture and audit sheet), P10 (state fallback), P11 (gifting), P12 (IRMAA
lookback + SSA-44), P13 (MC required-cut reporting). These are genuine feature builds and should be
prioritized by the practice's actual client mix.

### What I am deliberately not doing, and why

**Not splitting `spending_tracker.py` (A1 Option 2) in this cycle.** The deletion and the F811 guard close
the correctness hazard completely and cost almost nothing. The split is real cleanup, but it touches ~40
import sites for zero behaviour change, and it competes with Wave 2's financial defects. The CI guard makes
recurrence detectable, which was the actual risk.

**Not decomposing `dashboard.js` (A6) beyond correcting the documentation.** The 16,613-line file is a real
problem, but it is a navigability problem, not a correctness problem, and it is XL effort that would consume
the cycle. Correct `CLAUDE.md:156` immediately — a house-rules file off by 10x has already misled this
review — adopt verbatim global extraction as the stated convention (A13), route all new UI work into
sibling files, and take the YTD cluster (`:10638-11856`) as the first extraction only when there is slack.

**Not renaming the husband/wife row keys (A12 Option 2).** ~115 sites across the engine, `results_model`,
persisted snapshots, workbook builders and the frontend, with golden masters keyed off the names, in a
codebase where project memory records a prior ~$9.5M golden-master swing from a subtle resolver bug. The
accessor layer (Option 3) stops new code from hardcoding gendered keys and makes the eventual rename
strictly easier. Take the rename when the engine is otherwise quiet.

**Not attempting the full 50-state tax table (P10 Option 1).** Fifty states of retirement-income exclusions,
exemption thresholds and estate regimes is an ongoing annual-maintenance commitment, not a one-time build.
Make the silent Illinois fallback loud (Option 2) and fix bracket inflation now; own the expansion in the
annual maintenance runbook if the client mix justifies it.

**Not fixing D4 (Excel wrap) without rendering first.** It is inferred from `write_cell`'s signature, not
observed. Build a workbook and look before spending M effort.

**Not building Q3's PDF text extraction beyond a page-count baseline.** COM-exported PDFs frequently embed
text in ways that defeat extraction; the structural check catches the failure mode that actually occurs.

---

## 5. Design — target state

### 5.1 Modules and responsibilities

| Module | Change | Responsibility after |
|---|---|---|
| `src/spending_tracker.py` | Delete 17 shadowed defs + 3 `_legacy_*` (A1) | Same public surface, one definition per name |
| *new* `tests/test_no_redefinition.py` | New (A1) | AST walk of `src/`: no module redefines a top-level name |
| `src/projection_pipeline.py` | A2 step 1 | One-pass metric summary; stages without a registered callable report `inlined`, never `completed` |
| `src/projection_stages/engine_primitives.py` | New (A3) | Home for `_ar/_aa/_we/_ce/_ie/_ge` and shared helpers; imported explicitly by both `planning_engines` and `deterministic_engine`; no star import, no private rebinding |
| `src/report_compute.py` / `planning_engines.py` | A4 | `monte_carlo(cfg, base_rows=...)`; `ensure_engine_config` short-circuits on `config_immutable_boundary=True` + matching contract version, with a `force` escape |
| `src/plan_data_backfill.py` | New (A7) | Declarative `(target_file, rows, anchor_predicate)` table over a batched writer; takes an explicit target directory; **no pytest guard** |
| `src/module_catalog.py` | A9 | Gains `module_status`; owns all optional-module gating. `config_service` imports it directly; `workbook_common` imports it from here |
| `src/reporting/workbook_common.py` | A8 step 1 | Unchanged contents; all twelve consumers convert `import *` to explicit named imports |
| Deleted | A5, A10, A14, Q7 | `frontend/js/dashboard_{module_loader,income,spending,assets,strategy}_module.js`; `tests/test_phase_d_tier_3b_dashboard_modules.js`; `src/planning_query_api.py`; `src/meta_optimizer.py` + its case in `test_90`; `tests/test_scenario_canonical_run_validation.py` |
| *new* `frontend/js/dashboard_shared_helpers.js` | A13 | Single `esc`, `escJs`, `fmtMoney`, `fmtPct` + the five `RPDashboardUtils` helpers; loaded **first** in `index.html`; all duplicate definitions and the unreachable inline fallbacks (`dashboard.js:5347-5352,5417-5426`) deleted |

### 5.2 Screen layouts

**Guided steps (U2).** `.field-list` becomes
`display:grid; grid-template-columns:repeat(auto-fit,minmax(360px,1fr)); gap:...`, with a max column width
so inputs are not stretched on ultrawide monitors. `.field`'s internal label/input grid is unchanged. Two
columns at the 700px minimum content width, three when the help pane is collapsed on a wide monitor.
Expected effect: a 29-field Social Security step drops from ~29 rows to ~10-15.

**Help pane (U3).** Add `body.help-collapsed main{grid-template-columns:310px 1fr}` and make `.help-toggle`
active on desktop, mirroring the existing mobile `help-open` pattern. Persist the choice in localStorage so
it survives step navigation. When collapsed, `.ytd-tx-table` (1420px) and `.inactive-values-table` (1180px)
gain ~370px before needing internal horizontal scroll.

**Detailed Results (U1, U5).** Restore `renderDetailedResultsNav()` at the top of `renderDetailedResults()`
or prepended to `#steps`; the existing localStorage state and `setDetailedResultsNavOpen(true)`
first-visit behaviour then work as written. Add an "Expand all columns" button to the existing toolbar
(`reports_ui.js:1204`) alongside Search and Sheet; collapsed-by-default column groups otherwise unchanged.

**Spending Analysis (U4).** Replace `spendingExpandedType` / `spendingExpandedGroup` /
`spendingExpandedCat` with one `expandedKeys` Set of composite keys; the `if (!typeExpanded) return;` guards
become set membership tests. Add a "collapse all" control.

### 5.3 Content and wording

- `dashboard.js:303` and `:665`: replace the literal `&amp;` with `&` (D1). Add a source-literal entity
  check to the frontend test suite.
- `dashboard.js:212`: `title: "Roth Conversion"` (D6).
- `documentation/CLAUDE.md:156`: correct the `dashboard.js` size to ~16,600 lines and drop the "heavily
  minified" characterisation (A6).
- `sheets_summary.py:1058,1061`: remove the `tax_data.py / tax_constants.csv` provenance line and the
  `FMP → Yahoo → Alpha Vantage → Stooq` chain from the Executive Summary Release Notes. If build provenance
  is wanted, move it to the advisor-facing "21. QC Summary" sheet (D2).
- `sheets_qc_reference.py:123`: SALT Cap becomes a plain-language definition citing the figures already
  computed at `sheets_summary.py:1249-1254` — e.g. "the federal cap on state and local tax deductions if you
  itemize; currently $40,000, phasing up through 2029, then reverting to $10,000" (D2).
- `sheets_qc_reference.py:70-72` and `:121`, **after P2 lands**: the QC note keeps the cohort caveat (now
  true), and the Glossary entry becomes "the starting age depends on birth year under current law — see this
  household's applicable age on the RMD & Conversions sheet" (D3).
- `enterprise_pdf.py:60`: `MARGIN = 0.32 * inch` (D5).

### 5.4 Test pyramid shape

| Tier | Target | Content |
|---|---|---|
| Unit | Grow | Pure functions called directly with in-memory configs: `taxes.py`, `spending_budget_resolver.py`, `person_labels.py` (Q5 — **new file**), `allocation_policy.py`. No subprocess, no filesystem |
| Integration | Hold, prune | Service and route tests through `app.test_client()`. Keep the behavioral tests already inside each `*_service_extraction.py`; delete the ~18 duplicated substring assertions; replace the "no HTTP leakage" guardrail with one AST check (Q1) |
| Golden master | **Narrow** | `tests/fixtures/golden_master_engine_cases.json` (5 synthetic scenarios) becomes the mandatory release gate. `test_2_recommendations.py` keeps row-count and zero-validation-failure assertions (`:114-116`); dollar pins become a warn-only diff (Q6) |
| E2E | **Create** | 5-10 tests, slow-marked: real `POST /api/build/start` → poll `/api/build/progress` → `GET /api/results-explorer/index`, asserting real sheet content. Extend `built_workbook_dir` (`conftest.py:34-76`) rather than `test_161`'s fakes. PDF: page count + per-page size bounds baseline (Q2, Q3) |
| Frontend | Grow | `.mjs` suites for pure logic extracted from the **live** modules — `reports_ui.js`, `planning_workbench_ui.js`, `spending_dashboard.js`, `dashboard_decomp_*` — following the `tax_helpers.mjs` pattern (Q4, retargeted) |

Also: rename `test_161_phase2_live_workflow_journeys.py` to reflect that it tests route plumbing.

### 5.5 New planning capabilities and what they must compute

**P1+P9 — coherent terminal metric.** `estimate_terminal_taxable_deferred_cap_gain_tax` zeros the deferred
gain when `basis_step_up_at_death` is true and the terminal year is a death year, scaled by
`_basis_step_fraction_for_death` so community-property vs. common-law still matters. `estate_tax_penalty`
is evaluated at the death rows via `estimate_terminal_estate_tax` and present-valued with
`roth_tax_discount_rate` to match the already-discounted `lifetime_tax` term; the old max-across-rows figure
survives as a reported `peak_estate_tax_exposure` metric only.

**P2 — statutory RMD age.** `statutory_rmd_start_age(dob_year)` → 72 / 73 (1951-1959) / 75 (1960+), used as
the default in `data_io.py:852-853`. The explicit field remains an override; a preflight warning fires when
it disagrees with the member's birth year. `conversion_window_end_year` (`planning_engines.py:850`) follows
automatically.

**P6 — IRMAA guardrail by filing status.** Resolve the target threshold from
`IRMAA_TIERS_BASE_YEAR[filing]` at the configured `roth_irmaa_target_tier`, matching what the assessment
path at `deterministic_engine.py:354-360` already does. `roth_irmaa_target_threshold_mfj` remains as an
explicit override.

**P7 — spousal SS filing precondition.** Move the top-up calculation inside the year loop. Pay the
claimant's own reduced benefit until the *other* member's claim year is reached, then step up to
`max(own, 0.5 × other_pia × factor)`, keeping the existing FRA cap on the factor
(`deterministic_engine.py:835-842`).

**P3 — QCD (Wave 4).** A `qcd_schedule` of (amount, member, start year, end year), capped at the statutory
per-person limit from the tax-law dataset and gated at age 70½. The QCD reduces the RMD amount that enters
AGI (never a deduction), removes cash from the IRA balance, and reduces charitable spending by the same
amount so it is not double-counted. IRMAA tiers, SS provisional income and the NIIT threshold must all see
the *reduced* AGI.

**P4 — DAF deduction (Wave 4).** Annual charitable total = recurring giving + DAF contribution in the
contribution year, replacing the fixed `char_low` at `deterministic_engine.py:1364-1370`. Apply the AGI
percentage limitation (60% cash / 30% appreciated to a DAF) with a five-year carryforward. DAF grant years
must not be counted as new charitable cash.

**P5 — heir taxation (Wave 4).** Phase 1: derive the heir rate by running the terminal pre-tax balance
through a level 10-year distribution against an assumed heir bracket, replacing the flat 24% in *both*
`roth_heir_ordinary_tax_rate_assumption` and `roth_optimize_terminal_tax_rate`. Phase 2: per-beneficiary
10-year schedules including intra-period RMDs where the decedent had reached RBD, reporting after-tax
inheritance per beneficiary. Label heir income as scenario sensitivity, never prediction.

**P8 — beneficiary and titling (Wave 4).** Account-level primary/contingent beneficiary and titling
(JTWROS / tenants in common / TOD-POD / trust-titled), modeled on the existing life-insurance `beneficiary`
field (`data_io.py:527`, `sheets_protection.py:70`). Titling drives `_basis_step_fraction_for_death` per
account instead of one household `property_regime`. An audit sheet flags: no contingent, ex-spouse still
primary, minor named outright, trust named as IRA beneficiary without see-through language, estate named by
default, JTWROS defeating a credit-shelter plan, community-property assets titled to defeat the double
step-up. Framed as review prompts, not verdicts.

**P13 — MC required-cut reporting (Wave 4, phase 1).** For each failing path, compute the uniform spending
reduction that would have made it succeed; report the distribution of required cuts alongside the existing
success rate. No change to the success definition, so golden masters are untouched.

---

## 6. Implementation plan

Effort: S ≤ half day · M ≈ 1-3 days · L ≈ 1-2 weeks · XL > 2 weeks.
"Parallel" means it can run concurrently with its wave siblings without conflict.

### Wave 1 — Deletions, honesty, and the test gate

| # | Item | Prereq | Effort | Risk | Verification | Parallel | Model | Why that model |
|---|---|---|---|---|---|---|---|---|
| 1.1 | Delete 17 shadowed + 3 `_legacy_*` defs in `spending_tracker.py`; add AST no-redefinition test (A1 Opt 1) | — | M | Low | AST test passes; spending routes return identical payloads | Yes | **sonnet** | Mechanical but requires judging which definition survives |
| 1.2 | Delete 5 dead frontend modules + orphan `.js` test (A5) | — | S | None | `index.html` unchanged; app loads; check `retirement_planner.spec` does not glob `frontend/js/*.js` | Yes | **haiku** | Pure file deletion after one spec check |
| 1.3 | Delete `planning_query_api.py`, `meta_optimizer.py` + its `test_90` case, `test_scenario_canonical_run_validation.py` (A10, A14, Q7) | — | S | None | Import graph clean; suite collects | Yes | **haiku** | Pure deletion, zero callers verified |
| 1.4 | Fix `CLAUDE.md:156` line count; fix D1 `&amp;` literals; fix D6 nav capitalization | — | S | None | Rendered help panels show `&`; nav reads "Roth Conversion" | Yes | **haiku** | Three one-line text edits |
| 1.5 | Rewrite Executive Summary / Glossary copy (D2) | — | S | None | Sheet 1 Release Notes and Sheet 22 SALT entry contain no source filenames or vendor names | Yes | **sonnet** | Requires writing client-facing prose |
| 1.6 | PDF margin 0.22" → 0.32" (D5) | — | S | Low | Build a PDF; confirm band boundaries still sane; print one page | Yes | **haiku** | One constant |
| 1.7 | **Golden-master restructure (Q6)** — promote the 5-scenario synthetic fixture to the mandatory gate; demote `test_2` pins to structural + warn-only diff | — | M | **Medium** | Synthetic gate fails on a deliberately injected engine change; a plan-data-only edit no longer fails CI | Yes | **opus** | Changes the release gate; needs judgement on what still blocks |
| 1.8 | Add `tests/test_person_labels.py` (Q5) | — | S | None | New tests pass against nicknamed / default / single-filer configs | Yes | **sonnet** | Needs real edge cases chosen, not boilerplate |
| 1.9 | Narrow `except Exception` → `except ImportError` in 57 dual-import blocks (A11 Opt 2) | — | M | Low | Suite green; a deliberately broken import now raises instead of returning `{}` | Yes | **haiku** | Mechanical sweep, single pattern |
| 1.10 | Rename `test_161_phase2_live_workflow_journeys.py` to reflect route-plumbing scope (Q2 Opt 3) | — | S | None | File name and docstring match what it asserts | Yes | **haiku** | Rename + docstring |

**Do not run the test suite to verify Wave 1.** Project memory: some tests overwrite `input/client_data.*`.
Check `git status` on `input/` after any run, and prefer import-graph inspection for 1.1-1.3.

### Wave 2 — Financial correctness (requires 1.7)

| # | Item | Prereq | Effort | Risk | Verification | Parallel | Model | Why that model |
|---|---|---|---|---|---|---|---|---|
| 2.1 | **P1 + P9 together** — step-up in terminal metric; estate penalty at death rows, present-valued; retain `peak_estate_tax_exposure` | 1.7 | M | **High** | Synthetic baselines regenerated with `RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1`; recommended conversion amounts fall; `GOLDEN_MASTER_CHANGELOG.md` entry | Yes | **opus** | Cross-cutting objective change with tax-law judgement |
| 2.2 | P2 — `statutory_rmd_start_age(dob_year)` as default + disagreement warning | 1.7 | S | **High** | RMD ramp starts at 73 for a 1955-born test member; conversion window end moves with it; preflight warns on override | Yes | **sonnet** | Scoped, statute is unambiguous |
| 2.3 | P6 — IRMAA guardrail resolves threshold by filing status | 1.7 | S | Medium | Survivor-year conversions no longer cross the Single-filer tier; MFJ years unchanged | Yes | **sonnet** | One-line lookup with a clear reference implementation at `deterministic_engine.py:354-360` |
| 2.4 | P7 — gate spousal top-up on the worker spouse's claim year | 1.7 | M | **High** | A 62/70 split-claiming fixture shows the lower earner's own reduced benefit until year of the worker's filing, then the step-up | Yes | **opus** | Requires restructuring a hot year loop; SS rules are subtle |
| 2.5 | D3 — update QC note + Glossary RMD wording | **2.2** | S | None | Both sheets consistent with the engine's now-cohort-aware behaviour | No (blocked) | **haiku** | Two sentences, after the fact is established |

### Wave 3 — Structural debt and UX

| # | Item | Prereq | Effort | Risk | Verification | Parallel | Model | Why that model |
|---|---|---|---|---|---|---|---|---|
| 3.1 | U1 — reinstate `renderDetailedResultsNav()` call site | — | S | Low | Tree renders in Results Explorer; localStorage open/closed persists across reloads | Yes | **haiku** | Restore one call; feature already built |
| 3.2 | U2 — `.field-list` auto-fit grid | — | M | Low | Social Security step renders 2-3 columns at 1440px; no input squeezed below usable width at 1180px | Yes | **sonnet** | CSS with responsive judgement calls |
| 3.3 | U3 — desktop help-pane collapse + grid widen + persistence | — | S | Low | Toggle collapses and widens `main`; preference survives step navigation | Yes | **sonnet** | Small JS + CSS + storage |
| 3.4 | U4 — spending accordion Sets + collapse-all | — | S | Low | Two Types stay open simultaneously; no group silently vanishes | Yes | **haiku** | Scalars → Set, mechanical |
| 3.5 | U5 — "Expand all columns" toolbar control | — | S | None | One click reveals all years on a 30-year sheet | Yes | **haiku** | One button, existing toggle function |
| 3.6 | A4 — `monte_carlo(base_rows=...)` + `ensure_engine_config` short-circuit | 1.7 | S | Medium | Build wall time drops materially; MC success rates bit-identical vs. baseline with pricing disabled | Yes | **sonnet** | Scoped perf change with a precise correctness check |
| 3.7 | A2 step 1 — one-pass metrics; `inlined` instead of false `completed` | — | M | Medium | `results_model_v10_contract.json` reconciled; Results Explorer shows accurate stage status | Yes | **opus** | Persisted contract change |
| 3.8 | A3 Opt 1 — extract `engine_primitives.py`; delete star import + private rebinding | 3.7 | M | **High** | Golden masters unchanged; no `_legacy_pe` reference remains; import graph acyclic | No (after 3.7) | **opus** | Circular-import surgery on the engine's core |
| 3.9 | A13 — centralise `esc`/`escJs`/`fmtMoney`/`fmtPct` + delete unreachable `RPDashboardUtils` fallbacks | — | M | Medium | One `esc` definition repo-wide; `load_dashboard.mjs` updated; `test_39` still passes | Yes | **sonnet** | Load-order sensitive, security-relevant |
| 3.10 | A8 step 1 — explicit imports across the 12 `workbook_common` consumers | — | L | Medium | Each sheet's output byte-identical vs. `workbook_snapshot_expectations.json`; no NameErrors | Yes (one module at a time) | **sonnet** | Repetitive but each module needs real resolution |
| 3.11 | A9 — move `module_status` to `module_catalog`; drop the lazy import | **3.10** | S | Low | `config_service` imports directly; `test_module_catalog_prereq_gating` passes; no reporting import from the API layer | No (after 3.10) | **haiku** | Single function move once deps are visible |
| 3.12 | A7 — characterization tests first, then extract `plan_data_backfill.py` with an injected directory; delete the pytest guard | — | M | **Medium** | New tests run against a temp dir and pass; `input/` untouched after a run (`git status`); folder import still backfills | Yes | **opus** | Untested code path that writes user data |
| 3.13 | Q1 — one AST "no HTTP leakage" check; delete ~18 substring assertions | — | M | Low | AST check fails on a deliberately added `import flask` in `server_services/`; behavioral tests retained | Yes | **sonnet** | Needs care to keep the behavioral tests |
| 3.14 | Q2 — one real e2e journey (slow-marked) + read-side routes against `built_workbook_dir` | 1.7 | M | Medium | Test drives `/api/build/start` to real completion and asserts real sheet content | Yes | **opus** | New infrastructure spanning HTTP, subprocess and artifacts |
| 3.15 | Q3 — PDF page-count + size-bounds baseline | 3.14 | S | Low | A deliberately truncated PDF fails the check | No (after 3.14) | **haiku** | Two assertions |
| 3.16 | D4 — build a workbook, inspect wrapping; add `write_narrative_cell()` only if confirmed | — | M | Low | Release Notes and Glossary Definition text fully visible at default row height | Yes | **sonnet** | Verify-then-decide |
| 3.17 | A12 Opt 3 — member-indexed accessors over existing row keys | — | M | Low | Accessors return values identical to the literal keys; new consumers use them | Yes | **sonnet** | Additive read-only layer |

### Wave 4 — New planning capability (prioritize by client mix)

| # | Item | Prereq | Effort | Risk | Verification | Parallel | Model | Why that model |
|---|---|---|---|---|---|---|---|---|
| 4.1 | P3 — QCD as an AGI exclusion | 2.2 | M | **High** | A QCD-year fixture shows reduced AGI flowing through IRMAA tier, SS taxability and NIIT; RMD still satisfied | Yes | **opus** | Touches the RMD→AGI path, the engine's highest-risk seam |
| 4.2 | P4 — DAF into the itemized stack with AGI limits + carryforward | — | M | **High** | A bunching-year fixture flips to itemized; carryforward consumes in later years; grant years add no new charity | Yes | **opus** | Tax-limitation logic with multi-year state |
| 4.3 | P5 phase 1 — effective 10-year heir rate replacing both flat 24% fields | 2.1 | M | Medium | Heir rate varies with terminal pre-tax balance and assumed bracket; objective shifts accordingly | Yes | **opus** | Requires designing the derivation |
| 4.4 | P13 phase 1 — required-cut distribution on failing MC paths | — | M | Low | Report shows median and worst-decile required cut; success rate unchanged | Yes | **sonnet** | Additive post-processing, no policy change |
| 4.5 | P12 — historical MAGI inputs + SSA-44 flag | — | S | Medium | First two plan years show the surcharge from actual prior MAGI; SSA-44 flag suppresses it from the stated year | Yes | **sonnet** | Two inputs and a branch |
| 4.6 | P10 Opt 2 — fail loudly on unlisted states; inflate CA/NY brackets with `brk_inf` | — | M | Medium | An unrecognized state raises a preflight error naming the supported set; 30-year CA state tax no longer drifts upward | Yes | **sonnet** | Scoped, but inventory saved plans and fixtures first |
| 4.7 | P8 — beneficiary/titling capture + audit sheet; titling drives per-account step-up | — | L | Medium | Audit sheet flags each seeded failure case; per-account step-up fraction replaces the household regime | Yes | **opus** | Schema, UI, reporting and engine together |
| 4.8 | P11 — gifting schedule with lifetime-exemption tracking and carryover basis | 2.1 | L | **High** | Gifted dollars leave the funding account and the estate base; exemption use accumulates; gifted appreciated assets carry over basis rather than stepping up | Yes | **opus** | New balance-mutating path outside the withdrawal cascade |
| 4.9 | P5 phase 2 — per-beneficiary 10-year drawdown module | 4.3, 4.7 | L | Medium | Per-beneficiary after-tax inheritance reported; intra-10-year RMDs applied where the decedent reached RBD | No | **opus** | Full new module |
| 4.10 | P13 phase 2 — guardrail spending policy in MC | 4.4 | M | Medium | Success rate rises and the realized-spending distribution is reported with equal prominence | No | **opus** | Redefines the headline metric |

### Wave summary

- **Wave 1** — 10 items, all parallel. Mostly haiku/sonnet; **1.7 is opus** and is the gate for Wave 2.
- **Wave 2** — 4 parallel items (2.1-2.4) + 1 blocked (2.5). Two opus, two sonnet, one haiku.
- **Wave 3** — 15 parallel items + 2 blocked (3.11 after 3.10, 3.8 after 3.7, 3.15 after 3.14). Mixed.
- **Wave 4** — 8 parallel + 2 blocked. Mostly opus; these are design-heavy domain builds.

---

## 7. Appendix

### 7.1 Refuted during cross-check

**Refuted: "Withdrawal sequencing is a four-bucket global order with a hard-enforced Trust-before-Roth rule
and no year-by-year tax awareness."**

The finding's central causal claim is wrong. `DEFAULT_CASCADE_ORDER` / `validate_cascade_order`
(`taxes.py:469-497`) is **not** what enforces withdrawal order at runtime — it is dead-end config plumbing.
Its only product, `c['cascade_order_list']` (set at `src/data_io.py:1253,1255`), is read in exactly one
other place: `src/reporting/sheets_qc_reference.py:250`, purely to print a label
("Cascade: IRA → Trust → Roth → Home"). Grepping `src/planning_engines.py` and
`src/projection_stages/deterministic_engine.py` — the modules that actually run withdrawals — for
`cascade_order` returns **zero matches**.

The real sequence is hardcoded as explicit priority passes in `deterministic_engine.py`, documented verbatim
at `sheets_qc_reference.py:158` ("RMDs → HSA window → tax-sensitive pre-tax → taxable/trust → final
pre-tax/HSA → Roth last → Home Equity") and mirrored independently in the vectorized Monte Carlo path
(`planning_engines.py:2544-2556`, looping over `('cash','taxable','pretax','roth','hsa')`). So a planner who
edits the CSV Withdrawal Policy is not "silently reordered" — their input has **zero effect either way**,
because `cascade_order_list` never reaches the withdrawal functions. The recommendation's premise (let the
planner's deliberate Roth-before-Trust choice take effect) is moot.

The finding's secondary claim — "no lot, basis or gain awareness" — is also inaccurate: `src/core.py:483-520`
implements a full HIFO/LIFO/FIFO tax-lot engine with long-term-vs-short-term preferencing, invoked from
`deterministic_engine`'s `_realize_taxable_gain` (~`:1719-1721`) whenever `lot_engine.use_lots` is true. Gain
realization *is* lot-aware; only cross-account allocation *within* a bucket is balance-pro-rata
(`planning_engines.py:585-623`).

*Residual issue worth tracking separately (not a finding):* `cascade_order_list` is config that reaches only
a display label. It is a candidate for either wiring up or deleting, but it is not the defect described.

### 7.2 Corrections applied to findings that survived

| Finding | Correction |
|---|---|
| A5, A12 | Commits `e809367` and `84d8384`, cited as the husband/wife migration, **do not exist** in this repository (`git cat-file -t` fails for both). The substantive claims stand on direct code evidence; the attribution is dropped. A5's stale selectors are at `dashboard_income_module.js:141-142`, not `:140-141` |
| D2 | `documentation/CLAUDE.md` has **no "Consolidations" section** and mentions none of `taxes.py`, `tax_data.py` or `tax_constants`. The proof that `tax_data.py` merged into `taxes.py` is the banner and docstring at `src/taxes.py:1-16`. Finding confirmed; citation corrected |
| D3 | Reframed from "two contradictory ages in the same tab" to a cross-sheet inconsistency between the Sheet 21 QC note and the Sheet 22 client Glossary. More importantly, **the engine implements no birth-year-conditional RMD age at all** — it is a flat configurable default — so the QC note is currently the inaccurate one. Severity downgraded high → medium; sequenced after P2 |
| P5 | `after_tax.py:31-35` uses a **separate** field (`roth_optimize_terminal_tax_rate`, falling back to `roth_target_rate`, default 0.24), not the same field as `roth_heir_ordinary_tax_rate_assumption`. The codebase has two independent flat rate assumptions, not one — which strengthens the finding |
| P8 | Life insurance policies **do** carry a `beneficiary` field (`input/client_insurance_estate.csv`, parsed at `src/data_io.py:527`, surfaced at `src/reporting/sheets_protection.py:70`), so "529 and special-needs only" was wrong. The retirement/taxable gap is real as described, and the life-insurance field is a useful precedent pattern |
| Q1 | "Instead of calling the code" overstated: every cited file **also** contains real behavioral tests (`test_155:31-108`, `test_156:36-69`, `test_153:31-61`). Accurate framing is "text assertions alongside behavioral tests". Also, some substring checks make negative structural claims ("X no longer lives in file Y") that a behavioral test cannot make — those need AST-hardening, not conversion |
| A6, Q4 | `documentation/CLAUDE.md:156` claims `dashboard.js` is ~1,670 lines and "heavily minified". It is 16,613 lines and conventionally formatted. This stale line misled the review's own recon briefing |

### 7.3 Open questions for you to decide

1. **P1 changes advice already given.** Applying step-up in the terminal metric will reduce recommended Roth
   conversions for the live client. Has conversion advice already been acted on for the current tax year,
   and does the corrected recommendation need to be communicated?
2. **P2 changes the live plan's RMD age from 75 to 73** if either member was born 1951-1959. Confirm the
   members' birth years before running; if both are 1960+, this is a correctness fix with no effect on the
   current client.
3. **Golden-master policy (1.7).** Are you willing to have the release gate stop enforcing dollar-exact
   figures on the real sample plan? My recommendation assumes yes, on the grounds that data churn and engine
   regression are different risks. If you want dollar-exact pinning retained on the real plan, Wave 2 becomes
   strictly serial and roughly doubles in elapsed effort.
4. **State coverage (P10).** Is the practice's client base confined to the eleven modeled states? If yes,
   fail-loudly (Option 2) is sufficient indefinitely. If not, the 50-state table becomes a Wave 4 priority
   and an annual maintenance commitment.
5. **Wave 4 prioritization.** P3 (QCD), P4 (DAF), P8 (beneficiary audit) and P11 (gifting) are all L-effort
   builds serving different client profiles: charitably-inclined-at-RMD-age, bunching itemizers, estate-review
   clients, and above-exemption estates respectively. Which one or two match your actual book?
6. **`cascade_order_list` (Appendix 7.1).** Config that reaches only a QC display label. Wire it to the
   withdrawal engine, or delete it and make the hardcoded sequence explicitly non-configurable?
7. **D4 (Excel text wrapping) and D5 (PDF margins) are unverified.** Both are inferred from code, not from a
   rendered artifact. Someone should build one workbook and print one PDF page before either is scheduled.
8. **Documentation ownership.** Three separate stale claims were found in prose that a reader would
   reasonably trust (`CLAUDE.md:156`, the Executive Summary's `tax_data.py` reference, the QC sheet's RMD
   cohort caveat). Is there a checkpoint where docs are re-verified against code after a consolidation, or
   should one be added to the maintenance runbook?
