# System Review — retirement_system (entire system)

Review date 2026-10-19 · depth: deep · reviewed ref `claude/compassionate-ride-cx7k6j` @ `5caed3e873bafb0c7a8d67e6c64545ac2781e2b6` · run id sr-2026-10-19

## 1. Executive summary

**Assessment.** A static, read-only, five-expert review (architecture, usability/accessibility, documentation, quality, financial planning) produced 48 register entries after adversarial verification and planner sign-off: 18 confirmed, 22 partially confirmed, 7 with insufficient evidence, 1 duplicate, none refuted or superseded, and none left unverified. Severity of the 40 confirmed or partially confirmed findings: 1 high, 16 medium, 23 low, no critical (FIN-002 was lowered from medium to low and from confirmed to partially confirmed at planner re-verification). Nothing was executed, so every impact is an estimate from reading code and files. Areas with no finding are not declared healthy; their inspection status and residual uncertainty are in section 3.

**Principal risks.**

1. **Sensitive data in version control (QA-001, high).** A backup of the real trends log is tracked on `main` under a suffix the ignore rule does not cover, and the application recreates that suffix on every prune. Repository visibility could not be checked.
2. **Tax results are biased in both directions (FIN-003, FIN-001, FIN-010).** Qualified dividends are taxed at ordinary rates (tax overstated); realized brokerage gains never reach AGI-keyed rules such as IRMAA, NIIT, ACA credit and Social Security taxation (results optimistic); the joint-account step-up depends on which spouse dies first. FIN-001 and FIN-003 partly offset, so fixing only one changes the net error and neither should be released alone. Limitation notices ship in Wave 1 (WI-010a).
3. **The headline probability of success has no measured error bound for the shipped default Roth policy, and the tile shows two figures with different success definitions (FIN-002, low after re-verification; absorbs ARC-002).** The archived diagnostic's signed gaps (+17 to +18 points under roth_policy=none, -5 to -6 under roth_policy=fill_to_bracket, which it labels 'default') were measured on the tier-allocation path; its own addendum and the current monte_carlo call show the headline moved to the replay allocation afterwards, so those gaps probably no longer describe the headline. The shipped default, optimize_terminal_tax, was not measured under either allocation. The Roth/tier-bucket difference is a definitional difference in what success means, not an approximation error, and the tile now shows both the headline (funded as asked, Roth as a last resort) and a second 'without using Roth for extras' figure.
4. **Release assurance is thinner than it looks (QA-002).** The release gate runs only unittest-style files, about 16% of the test files; governance, golden-provenance and hygiene guards are not run by it.
5. **Silent failure and silent data loss paths.** Failed derived-result steps are swallowed (ARC-003), a malformed liability cell can empty the liabilities list (QA-003), and add/delete actions discard unsaved edits on pages labelled "Saves automatically" (UX-001); "Cancel Build" does not cancel (UX-002).
6. **Server mode has no authentication or Host allow-list (ARC-001, medium).** The default desktop mode is unaffected and the default bind is loopback.

**Opportunities.** The repository already has the right instruments: a golden-master discipline with provenance, a paired-path Monte Carlo harness, a frozen date seam, a documented layout rule and a tracked backlog. Most recommended changes extend those instruments rather than add new ones. Several fixes are small and independent (ignore rule, release gate, Host allow-list, logging, honest wording).

**Financial planner verdict.** Approved with changes (section 14): eight changes requested, three material; all applied or partly applied after re-verification, and five dissents recorded. The financial review is partial; sign-off covers the findings and plan as written, not the correctness of areas not read (section 14).

**Recommendations (detail in sections 7 and 9).**

1. Untrack the trends-log backup, ignore the whole data directory, add the hygiene test, and have the owner decide on a history purge once visibility is known (WI-001, WI-004).
2. Make the release gate execute the pytest suite with a minimum collected count, after removing tests that pass vacuously (WI-005, WI-012).
3. Fix tax correctness in a measured order: qualified-dividend stacking first, then brokerage gains in MAGI-keyed rules, then survivor step-up symmetry, with visible limitation notices shipped in Wave 1 until each fix lands (WI-010a, then WI-022 to WI-025); FIN-001 and FIN-003 are released together.
4. Label both displayed Monte Carlo figures with their own success definition and tie the tolerance label to a measured regime, including the unmeasured shipped default optimize_terminal_tax, now; then verify and broaden the replay headline's coverage (WI-009, WI-036).
5. Harden server mode with a Host allow-list and non-loopback guard, log swallowed failures, and stop add/delete actions and the cancel button from misleading users (WI-006, WI-007, WI-018, WI-019).

## 2. Scope and methodology

- **Scope:** the entire system (engine, tax and benefits logic, persistence, import/export, Monarch and trends integrations, UI, documentation, tests and tooling, reference data).
- **Date / depth:** 2026-10-19, deep.
- **Repository:** matthartzman/retirement_system (owner and name from the origin URL, unconfirmed through GitHub). Reviewed ref `claude/compassionate-ride-cx7k6j`, commit `5caed3e873bafb0c7a8d67e6c64545ac2781e2b6`, default branch `main` (inferred from the only other remote branch). Working tree clean. Pull request number: none recorded, because pull requests could not be checked.
- **Roles:** orchestrator (recon, dependencies, evidence, GitHub context, deduplication, conflicts, synthesis, waves, validation); five experts: architect, usability/accessibility, documentation, quality, financial planner. The orchestrator is not a sixth expert.
- **Model tiers (capability alias → reasoning effort):** expert_reasoning → high (all five experts); standard_reasoning → medium; recon → medium; synthesis → high; mechanical → low.
- **Phases:** (1) repository resolution and recon collection; (2) shared system map and coverage matrix; (3) five parallel expert reviews; (4) adversarial verification of each expert's findings; (5) synthesis: deduplication, conflicts, implementation waves, report; (6) planner sign-off (completed; section 14). Two architect observations were removed by an automated filter before synthesis (section 13).
- **Evidence rule:** only evidence opened by an expert, a verifier or the orchestrator in this run is cited, as path:lines — symbol — what it establishes. GitHub metadata is context, not proof of product behavior.
- **GitHub context:** GitHub read tools were unavailable in this run (the orchestrator re-tried the tool search). Issues, pull requests, releases, collaborators and secret scanning were not checked; merged pull request numbers come from local commit subjects only. Dispositions of every item referenced are listed under section 3.
- **Runtime validation:** Runtime behavior was not validated during this review. Nothing was run: no tests, builds or application. No statement here says any test passes.
- CI was intentionally excluded from this review.

**Experts and registers.** Findings by expert: architect 7, documentation 9, financial_planner 11, quality 8, usability_accessibility 13. The structured register is `/tmp/claude-0/sr-scratch/findings.json` and is the source of truth; this report is a synthesis of it.

## 3. Coverage matrix

Status values: inspected_no_material_finding, finding_identified, partially_inspected, not_inspected, could_not_validate, requires_external_domain_verification, not_applicable. "No finding" never means healthy.

| Area | Status | Evidence (first three) | Expert | Findings | Residual uncertainty |
|---|---|---|---|---|---|
| Overall architecture and module boundaries | finding_identified | src/planning_engines.py:1-28 — header — 8-file consolidation, circular-import warning; src/projection_stages/deterministic_engine.py:82-1581 — run_deterministic_projection_stage — single ~1,500-line function; src/projection_stages/deaths_and_spousal_rollover.py:7 — _legacy_pe — back-reference to planning_engines (+1 more in coverage.json) | architect | ARC-005 | Function bodies of most stage modules and the optimizers were not read. The import graph was not computed beyond the cited files. Two architect observations (the stage facade over one engine call, and embedded state-tax schedules) were removed from the register by an automated keyword filter and are not assessed here (see report section 13). |
| Calculation engine: projection stages and orchestration | finding_identified | src/projection_pipeline.py:28-45,95-195 — DEFAULT_STAGE_ORDER, run_projection_pipeline — facade over one engine call; src/report_compute.py:259-317 — run_projection_artifacts — orchestration and exception handling; src/planning_engines.py:6560-6700 — monte_carlo — vectorized default; headline passes allocation='replay' at 6654 | architect | ARC-002, ARC-003, ARC-005, FIN-002 | The stage execution order inside deterministic_engine.py was not compared line by line with DEFAULT_STAGE_ORDER. Calculation correctness belongs to the financial planner rows. |
| Compatibility layers and consolidation shims | finding_identified | src/core.py:731-745 — rmd_divisor — delegates to tax_kernel; src/tax_kernel.py:204 — rmd_divisor — canonical implementation; src/planning_engines.py:856-880 — _rmd_divisor_with_table_override — delegating wrapper (+2 more in coverage.json) | architect | ARC-004, ARC-005, ARC-009 | The RMD duplication flagged in recon is resolved by delegation. Other shims (account_registry aliases, data_io tax helpers) were not enumerated. |
| Financial logic: federal/state tax, brackets, IRMAA, Social Security taxability | finding_identified | reference_src/tax_law_v10.json — 2026 brackets, standard deduction, LTCG, IRMAA and Part B values match the expert's recollection of the cited documents; src/core.py:837-946 — compute_fed_tax, standard_deduction, senior_bonus_deduction, social_security_taxable_amount, irmaa_lookback_magi_and_filing — consistent with the expert's reading of the statute; src/core.py:1153-1160 — niit_tax (+2 more in coverage.json) | financial_planner | FIN-001, FIN-003, FIN-005, FIN-006, FIN-008, FIN-011 | Federal 2026 values were not re-fetched from IRS/CMS. State rules were checked only for modeled rows and from memory. |
| Financial logic: withdrawals, account sequencing, RMDs, depletion | finding_identified | src/planning_engines.py:856-1020, 1411-1470 — RMD computation and elective pre-tax draw; src/projection_stages/withdrawal_cascade_investment_tax.py:205-423 — LTCG/NIIT fixed point and loss waterfall; src/core.py:633-784 — RMD_DIVISORS, rmd_divisor, statutory_rmd_start_age — values match the expert's recollection of Pub 590-B (not checked against the primary source) | financial_planner | FIN-001, FIN-003, FIN-004 | The full priority order of the cascade and its depletion behavior were not traced end to end. |
| Retirement income and Social Security claiming workflows | finding_identified | src/projection_stages/income.py:322-520 — claim factors, spousal excess, survivor logic; survivor percentage defaults to 100% (src/data_io.py:832); src/projection_stages/deterministic_engine.py:~590-620 — FRA and reduction factors match SSA formulas | financial_planner | FIN-007 | PIA derivation, COLA indexing before claim and the 22% default funding-discount haircut from 2032 were not assessed for suitability. FIN-007 itself is insufficient_evidence. |
| Roth conversion and ACA/healthcare (IRMAA, HSA) workflows | partially_inspected | src/planning_engines.py:1945-2052 — ACA regime tables, MAGI, premium tax credit; the 2026 table matches the expert's recollection of Rev. Proc. 2025-25; src/planning_engines.py:2325-2375 — Roth LTCG/NIIT caps; src/projection_stages/income.py:299-316 — HSA contribution and catch-up (+1 more in coverage.json) | financial_planner | FIN-001, FIN-003, FIN-004 | The ACA enhanced-subsidy default needs external confirmation of current law. hsa_schedule.py and plan_roth_conversion's body were not read. |
| Benefits, annuity and insurance workflows | partially_inspected | src/projection_stages/income.py:495-545 — pension, annuity, QLAC and joint-and-survivor income; src/planning_engines.py:856-1000 — QLAC exclusion in RMD base | financial_planner | FIN-011 | Annuity pricing helpers, LTC and life-insurance modules were not read. |
| Estate, legacy and beneficiary workflows | finding_identified | src/after_tax.py:700-830 — estate tax and heir-tax estimates; src/planning_engines.py:520-620 — beneficiary_titling_audit; src/parsing/estate_planning.py:30-90 — defaults | financial_planner | FIN-009, FIN-010 | State estate-tax formulas (IL, NY) and gifting logic were not verified. The 10-year/eligible-designated-beneficiary heir-tax branch was read only in part. |
| Survivor and death-transition workflows (either spouse) | finding_identified | src/projection_stages/deaths_and_spousal_rollover.py:1-200; src/planning_engines.py:623-742; src/projection_stages/income.py:436-470 (+1 more in coverage.json) | financial_planner | FIN-010, FIN-009 | Remarriage and divorce paths were not inspected. HSA movement to a taxable account was not followed into tax treatment. |
| Housing, rental and home-sale financial logic | partially_inspected | src/projection_stages/home_sale.py:55-240 — section 121 exclusion, surviving-spouse window, death basis adjustment; documentation/reference/CAPITAL_GAINS_IN_AGI.md:1-30,75-90 — opened by the orchestrator; src/projection_stages/deterministic_engine.py:1228-1245,1432-1445 — H1 sale gain in IRMAA MAGI and AGI — opened by the orchestrator | financial_planner | FIN-001 | Rental depreciation, passive-loss and housing-optimizer logic were not read. Section 121 amounts are literals in home_sale.py in addition to the dataset rows. |
| Monte Carlo and stochastic assumptions (scalar vs vectorized) | finding_identified | src/planning_engines.py:3600-3935 — regime return sampling, covariance draws, inflation and medical paths; src/planning_engines.py:745-856 — table-based mortality calibrated to user median age; src/planning_engines.py:5560-5640 — vectorized tier cascade and other_nominal (+7 more in coverage.json) | financial_planner | FIN-002, ARC-002 | Mean-versus-geometric return convention and positional member-sex assumption in the mortality shape were noted, not evaluated. Documents disagree on the bias direction (see conflicts). The shipped default Roth policy (optimize_terminal_tax) is unmeasured under either allocation; the post-fix agreement figures are the diagnostic authors' and were not independently verified; whether the displayed headline matches the diagnostic's 'shipping engine' definition is not confirmed; the git history of planning_engines.py is one squashed commit. Nothing was executed. |
| Optimizers and strategy analytics (Roth, DAF, QLAC, allocation, housing) | partially_inspected | src/planning_engines.py:1950-2052, 2325-2375 — guardrails only; src/projection_stages/roth_conversion_and_agi_tax.py:700-760 — DAF deduction AGI limit and carryforward | financial_planner | FIN-001, FIN-002 | Optimizer objective functions, the claim-age sweep, strategy_sweep.py, daf_optimizer.py, qlac_optimizer.py and the housing optimizer were not read. Their dependence on FIN-001 and FIN-002 is inferred from call paths. |
| Boundary scenarios: early/late retirement, high inflation, poor returns, longevity, missing inputs | finding_identified | src/planning_engines.py:1411-1470 — pre-59.5 draws; src/server_services/build_service.py:89-200 — preflight; src/planning_engines.py:3873-3935 — inflation bounds clamp (-2% to 12%) (+1 more in coverage.json) | financial_planner | FIN-004, FIN-007 | Zero and very large balances, late claiming at 70 with survivor death before claiming, and extreme-inflation paths were not tested. |
| Precision, rounding, units, and Decimal vs float handling | finding_identified | src/money.py:1-40 — Decimal boundary helpers; no behavioural test; src/data_io.py:317-324 — _n; src/csv_exchange/core.py:276-285 — _is_number (+2 more in coverage.json) | quality | QA-003 | The engine uses floats after a documented Decimal boundary parse. Storage versus display rounding in workbook sheets and the ~170 round(...,2) calls outside projection stages were not reviewed one by one. Cross-platform float reproducibility depends on unpinned numpy and scipy ranges (no lock file). |
| Date handling and annual/monthly conversion | inspected_no_material_finding | src/platform_runtime.py:20-60 — today() seam, FROZEN_TODAY; tests/test_frozen_today_seam_regression.py:1-100 — allow-listed date.today() guard; tests/test_ytd_current_year_blend_functional.py:39-49 (+2 more in coverage.json) | quality | — | No test runs the engine under a different frozen year; year rollover (plan_start, YTD roll-forward, dated tax rows) is untested and the real clock reaches 2027-01-01 in about 10 weeks. Leap-day and DST behaviour were not examined. No finding does not mean healthy. |
| Determinism and reproducibility | inspected_no_material_finding | tests/conftest.py:1-130,165-212 — workspace redirect, frozen date and tax year, offline pricing; src/planning_engines.py:4209-4221,6016 — seeded random.Random and numpy default_rng; tests/golden_pricing.py — frozen prices | quality | — | The PR-tier scalar-vs-vectorized gate compares engines on independent RNG streams at a 5pp tolerance its own docstring calls thin; the stronger test is nightly-only. Documents disagree on the Monte Carlo bias direction (see FIN-002). Nothing was executed. |
| Data integrity: validation, schema, duplicates, ownership, migrations | partially_inspected | src/stores/db.py:1-140 — transaction, migrate — transactional forward-only migrations; src/csv_exchange/plan_set.py:1-148 — import_plan_set — preview then one-transaction commit, zip size guard; src/server/import_export_routes.py:60-82 — _run (+1 more in coverage.json) | architect | ARC-004, QA-003 | plan_data_migration, duplicates and ownership handling were not read. Zip import enforces the declared-size cap but request size is otherwise unbounded (see ARC-001). |
| Persistence: SQLite stores, plan revisions, schema ownership | finding_identified | src/stores/db.py:1-140 — savepoint-aware transaction and migrate; src/active_plan.py:1-120 — build_read, plan lock, protected fields; src/local_store.py:1-80; src/config_backend.py:66-100 — legacy DB schema (+1 more in coverage.json) | architect | ARC-004 | plan_store.py revision logic, backup scheduler and OneDrive guard were not opened. WAL with synchronous=NORMAL is set; durability under power loss was not assessed. |
| Import/export: CSV exchange, preview/commit, legacy conversion | finding_identified | src/server/import_export_routes.py:1-140 — routes; src/csv_exchange/plan_set.py:1-148 — plan-set zip and one-transaction commit; src/import_preview.py:1-120 — side-effect-free preview (+1 more in coverage.json) | architect | QA-003, UX-011 | legacy_conversion steps, csv_exchange/core.py commit logic and the YTD commit path were not examined beyond the cited lines. The zip handling raised no finding. |
| Monarch integration, reconciliation and trends reporter | finding_identified | src/reconcile.py:1-60,541-620 — logged, undoable changes with a 10%/$5,000 auto-hold; Monarch Extractor/monarch_extract.py:1015-1161 — persistent browser profile, outbox; financial_trends_reporter/trends_metrics.py:36-114 — legacy fallbacks (+1 more in coverage.json) | architect | ARC-004, QA-004, QA-001 | The extractor body, monarch_autoupdate, the balances import and the trends HTTP app were not read in full. The security of the Playwright profile on disk was only checked via .gitignore. Trends-reporter tests exist (13 files) but their depth was not read. |
| Reference data and tax-law currency (reference_src, reference.db) | requires_external_domain_verification | reference_src/tax_law_v10.json; reference_src/tax_update_dashboard.csv; reference_src/state_tax.csv (+3 more in coverage.json) | financial_planner | FIN-005, FIN-006, FIN-011 | No primary sources were fetched. reference.db was not opened and tools/build_reference_db.py --check was not run. |
| UI: navigation, step gating, autosave vs explicit save | finding_identified | frontend/js/navigation.js:1-438 — redirects, autosave guard, history, focusableEntries; frontend/js/dashboard_decomp_row_model.js:2418-2500 — renderSteps; frontend/js/dashboard_decomp_row_model.js:4852-4990 — loadAll | usability_accessibility | UX-001, UX-008, UX-009, UX-011 | NAV_FEATURE_MAP.md claims about redirects and gating were not verified in code. No rendering or screen-reader run. |
| UI: workflows, forms and data-entry screens | finding_identified | frontend/js/dashboard_decomp_build_lifecycle.js:62-160 — build overlay and cancel; frontend/js/dashboard_decomp_row_model.js:2753-2880, 5056-5135 — fieldHtml, save errors; frontend/js/dashboard_decomp_assets_other.js, dashboard_decomp_estate_insurance.js (excerpts) | usability_accessibility | UX-001, UX-002, UX-004, UX-010, UX-011, UX-013 | Housing optimizer, spending workspace, holdings editor, rental properties, Monarch, tax assumptions and checklist screens were sampled by grep, not read in full. |
| UI: frontend code structure, global coupling, script ordering | finding_identified | frontend/index.html:91-142 — 52 module scripts; frontend/js/dashboard.js:6690-6810 — window bridge; frontend/js/dashboard_decomp_roth_guardrails.js:419; frontend/js/dashboard_decomp_tax_assumptions.js:217 — renderMain wrappers (+1 more in coverage.json) | architect | ARC-007 | 67 innerHTML sites exist and only a sample was checked for escaping; no unescaped user-data interpolation was found in the reconciliation module. No CSP was found. File sizes and load time were not measured. |
| Accessibility: keyboard, focus, semantics, screen reader, contrast, touch targets | finding_identified | frontend/css/dashboard.css (grep of focus, media, font-size, switch rules); frontend/js/dashboard.js:6534-6565 — moveToNextEntry; frontend/admin.html:1-5; frontend/js/admin.js:1283-1330 | usability_accessibility | UX-003, UX-005, UX-006, UX-007, UX-008, UX-010, UX-012, UX-013 | Static only: no rendering, screen-reader run or measured contrast; contrast figures are hand estimates from hex values. Four of these findings are insufficient_evidence. |
| Cognitive load, terminology and error messaging | partially_inspected | frontend/js/dashboard_decomp_row_model.js:2418-2500 — 28 steps in 13 groups; frontend/js/dashboard_decomp_checklist_closeout.js:280 — Plan Status page; frontend/js/dashboard.js:14-120 — STEPS help strings (documentation expert) | usability_accessibility | UX-004, UX-002, DOC-008 | No finding on content volume per page: it cannot be judged without rendering or user testing. Server error payload shapes were not inspected. |
| Performance: engine, workbook build, frontend load | partially_inspected | docs/superpowers/plans/perf-baseline-2026-09-17.json — total_s 76.91, Social Security sheet 37.84 s; src/planning_engines.py:6560-6585 — claim sweep calls monte_carlo 81x per build | architect | ARC-002, ARC-007 | The baseline is dated 2026-09-17 and may be outdated. Nothing was run, so no performance finding was raised. |
| Privacy and security: financial-data exposure, auth, CSRF, secrets, backups, exports, logs | finding_identified | src/server/security_audit.py:82-96,317-333 — auth stub and CSRF token; src/server/app_core.py:985-1060 — Origin/CSRF gate; src/secrets_store.py:1-60 — OS keyring only (+4 more in coverage.json) | architect | ARC-001, ARC-009, QA-001 | Secret scanning could not be run, so the absence of secrets is unverified. Backups, the pricing-key flow and PDF/workbook export contents were not inspected. Full-history scan was not performed. No AI-generated content paths were identified or reviewed. |
| Error handling and failure paths | finding_identified | src/data_io.py:1755-1790; src/planning_engines.py:2262-2268,2465-2476,4938-4952,6158-6168; src/projection_stages/deterministic_engine.py:328-349 (+1 more in coverage.json) | quality | QA-003, QA-007, ARC-003 | 343 broad except clauses were counted but only the engine-core ones and report_compute were read. |
| Logging and observability, audit events | finding_identified | src/bootstrap.py:60-100 — rotating redacted file log; src/http_runtime/server.py:54-56 — log_message suppressed; src/server/security_audit.py:110-125 — _audit to app.db (+1 more in coverage.json) | architect | ARC-003 | About 104 print() calls remain in src/. About 400 'except Exception' sites exist; only report_compute was reviewed in depth. |
| Testing: strategy, tiers, golden-master discipline, fixtures, assertion quality | finding_identified | pyproject.toml:1-45 — markers, tiers; tests/test_frozen_sample_plan_golden_master_regression.py:148-153,241-433; tests/test_golden_master_pin_provenance.py:1-60 (+3 more in coverage.json) | quality | QA-002, QA-005, QA-006, QA-008 | Golden masters are characterization pins, not independent oracles; the independent oracle set is small. No test was executed and no coverage report exists. No statement here says any test passes. |
| Test coverage gaps: trends reporter, Monarch Extractor, frontend, e2e | finding_identified | tests/test_trends_*.py — 13 files import the trends reporter modules; Monarch Extractor/monarch_extract.py:96-175,506-690 (no tests); tests/frontend/*.test.mjs (91 files), playwright.config.js, tests/e2e (19 specs) (+1 more in coverage.json) | quality | QA-004, QA-008 | Name-based scans cannot see tests that load the bundle through load_dashboard.mjs. The depth of the trends-reporter tests was not read. |
| Documentation accuracy and currency (reference, README, CLAUDE.md copies, release notes) | finding_identified | documentation/reference/CLAUDE.md:246; documentation/reference/NAV_FEATURE_MAP.md:7-100; documentation/reference/PLAN_METADATA_SCHEMA.md:1-22 (+2 more in coverage.json) | documentation | DOC-003, DOC-005, DOC-006, DOC-007 | Hand-written facts such as line counts were checked at the reviewed commit only. API_CONTRACTS.md was compared to the route manifest by route name only. |
| Design and implementation documents status (docs/superpowers, future, archive exclusions) | finding_identified | docs/superpowers/specs/2026-10-14-items-345-347-design.md:3; docs/superpowers/specs/2026-10-13-gap-closure-plan.md:1-40; documentation/reference/CONTRIBUTING.md:92-109 (+1 more in coverage.json) | documentation | DOC-001, DOC-002 | Banners were read for specs from 2026-10-04 on; the 26-27 plan/notes files and older specs were identified by status banner only. documentation/archive was not reviewed. |
| Configuration, packaging and dependencies (pyproject, requirements, package.json, PyInstaller) | partially_inspected | src/bootstrap.py:30-50 — env defaults; src/runtime_config.py:64,154 — dashboard_host; pyproject.toml:38-44 — test markers | architect | ARC-009 | requirements.txt, package.json, retirement_planner.spec and build.py were not opened. A version labelling discrepancy (v10 pyproject vs 'v11' headers) was seen in recon but not re-verified. An apparent conflict between the pytest-timeout dependency and a pyproject comment was not verified. |
| Generated files and tooling scripts (regen, build, release gate) | finding_identified | tools/release_gate.py:29-41; tools/regen_golden_master.py:1-120; tools/golden_compare.py:1-70 (+2 more in coverage.json) | quality | QA-002, QA-006 | regen_full_row_snapshot.py, regen_synthetic_golden_master.py, build_reference_db.py and the tracked js_codemod reports were not read beyond names. |
| GitHub work items and change provenance | could_not_validate | /tmp/claude-0/sr-scratch/manifest.json — github_context status 'NOT CHECKED'; ToolSearch (re-run by the orchestrator) found no GitHub read tools; local git subjects for merged PR numbers #199-#223, #355, #358, #360, #361 | documentation | DOC-009 | No issue, PR, release, collaborator or secret-scanning data could be read. PR dispositions rely on local commit subjects plus the direct file evidence named in each row. |
| API and functional reference documents (API_CONTRACTS.md, FUNCTIONAL_SPEC.md) | inspected_no_material_finding | documentation/reference/API_CONTRACTS.md:1-25,94-102,557 — removed routes documented as removed; src/server/route_manifest.py:1-30 — route inventory; documentation/reference/FUNCTIONAL_SPEC.md:25-60,219-281 | documentation | — | Contracts were compared to the route manifest by route name only; request/response fields were not verified. The header date (2026-06-29) is older than some content. |
| End-user documentation (README, input READMEs, Concepts Guide) and in-app help wording | finding_identified | documentation/reference/readme/README.md:1-52; input/README_INPUT_PACKAGE.md; input/README_YTD_INPUTS.md (not opened by verifier); documentation/reference/Retirement_Planner_Concepts_Guide.docx — extracted XML/text (+1 more in coverage.json) | documentation | DOC-003, DOC-004, DOC-007, DOC-008 | The docx was inspected as XML, not rendered. About 8 of the ~35 nav pages' help text was read. Whether the release package bundles documentation/reference was not checked. |
| Future and archive documents (documentation/future, documentation/archive) | partially_inspected | documentation/future/superpowers/plans/2026-09-09-dashboard-js-modularization-design.md:1-12 — 'nothing implemented'; documentation/future/superpowers/plans/2026-08-17-roth-conversion-gap-design.md:1-12; documentation/future/Add 4 Missing Planning Strategies Implementation plan.md:1-12 | documentation | — | Future docs appear correctly classed as not built, except the dashboard modularization design whose status may be partly overtaken by the dashboard_decomp files. Archive contents were not reviewed. |
| Admin / Control Center UI | finding_identified | frontend/admin.html:1-5 — structure and #msg; frontend/js/admin.js:40-75, 355-385, 1283-1330, 1805 — msg, confirm, grid controls; frontend/css/admin.css:2 | usability_accessibility | UX-006, DOC-007 | admin.js (2,004 lines) was read in parts; other settings forms and diagnostics screens were not. |
| Dialogs, modals and focus management | finding_identified | frontend/js/dashboard_decomp_row_model.js:3231-3440 — showInAppConfirm, openStaticDialog, showSaveDiscardStayModal, showInAppPrompt; frontend/index.html:45-60 — exitModal, chartModal, buildOverlay | usability_accessibility | UX-010, UX-002 | The build overlay does not move focus or make the background inert; treated as covered by UX-002. Dialog behaviour was not run. |
| Visual design: contrast, font size, responsive layout | partially_inspected | frontend/css/dashboard.css:1-1230 — tokens, focus, media queries, font sizes; frontend/js/text_size.js:1-52 | usability_accessibility | UX-005, UX-007, UX-013 | Contrast ratios were hand-estimated for a small sample of pairs; runtime and inline-style colours were not evaluated; the overflow claim is CSS arithmetic, not a rendered check. |
| Charts and data visualisation accessibility | partially_inspected | frontend/js/reports_ui.js:773-1182 — SVG chart builders; financial_trends_reporter/frontend/charts.js:202-211, 501-507 — labelled chart elements | usability_accessibility | UX-012 | The trends reporter app and spending dashboard bar charts were only grepped; the chart modal was not exercised. |
| Frontend automated accessibility testing | could_not_validate | tests/frontend/ listing — accessibility-themed unit tests exist (field_control_accessible_names, static_dialog_focus_management, inapp_modal_accessibility_and_listener_leak, keyboard_field_advance_scope) | usability_accessibility | — | The tests were not opened or run; their existence does not show the behaviours work. No axe-style scan configuration was seen. |
| Repository data hygiene: tracked data files and ignore rules | finding_identified | .gitignore:28-62; financial_trends_reporter/data/financial_trends_log.jsonl.bak — tracked (git ls-files re-run by the orchestrator); tests/test_repo_hygiene_guards.py:96-125 (+1 more in coverage.json) | quality | QA-001 | Documentation screenshots and other tracked binaries (reference.db, demo_seed.rpx) were not scanned for real figures. Full history was not scanned. Remote visibility is unknown. |
| Secret scanning | could_not_validate | manifest.json secret_scan_results — GitHub secret scanning not run (tools unavailable) | orchestrator | — | No local pattern scan was substituted. Absence of findings must not be read as a clean result. |

### GitHub issues, pull requests and pending work inspected, with disposition

Local commit subjects were the only source for pull request numbers. None of these dispositions rests on pull request contents.

| Item | Type | Disposition | Basis |
|---|---|---|---|
| PR #207 | pull_request | confirmed | Sale gains in AGI/IRMAA MAGI (H1). Corroborated by deterministic_engine.py:1236-1241,1438-1441, opened by the orchestrator. Scope is home/rental sales only; the remaining gap is FIN-001. |
| PR #205, #206 | pull_request | contextual_only | Tier 1-2 gap-closure items; commit subjects only (DOC-001). |
| PR #208 | pull_request | contextual_only | H2 rental loan link; rental logic not reviewed in depth. |
| PR #209 | pull_request | contextual_only | H3-H6 (reversion, owner split, death handling, rent-then-sell). Death-handling code read for FIN-010; H3-H6 code otherwise not opened. |
| PR #199 to #202 | pull_request | contextual_only | Rental engine and UI (WP12); source files exist (DOC-001). |
| PR #203, #204 | pull_request | contextual_only | Status doc and rental verification; not separately examined. |
| PR #210 | pull_request | out_of_scope | Out of scope under the review's stated exclusion; not examined. |
| PR #211 | pull_request | confirmed | Items 345/346. Shipped status corroborated by the trends code and release-note context cited in DOC-001; subject-level otherwise. |
| PR #212, #213 | pull_request | contextual_only | Items 347a-c; trends_metrics.py contains per-account flows consistent with the subject. |
| PR #214 | pull_request | contextual_only | Import backfill fix; its tests were not read. |
| PR #215 | pull_request | confirmed | Monarch balances, trends charts and reconciliation page. Release note and nav page exist; commit 0bd50f3 added the tracked trends-log backup (QA-001, git ls-files re-run by the orchestrator). |
| PR #216 | pull_request | contextual_only | Credit-card liability type; CLAUDE.md liabilities list not updated (DOC-005); code not inspected. |
| PR #217 | pull_request | confirmed | Items 349-354. Release note documents delivery; spec banner stale (DOC-001). |
| PR #218 to #222 | pull_request | contextual_only | Reconcile fixes. src/reconcile.py design was read; PR contents were not. |
| PR #223 | pull_request | out_of_scope | Review tooling skill, not product behavior. |
| PR #355 | pull_request | contextual_only | Holdings lot sorting and insert action; holdings module not read in detail. |
| PR #358 | pull_request | contextual_only | Economic & Tax Assumptions page restructure; related to the lever behind FIN-008. |
| PR #360, #361 | pull_request | contextual_only | Trends-reporter typing/toggle and Accounts & Sources header label; not inspected. |
| Issues #329, #330, #331 | issue | insufficient_evidence | Cited in BACKLOG.md and plan notes; cannot tell whether these are issues, PRs or internal numbers (DOC-009). BACKLOG.md states the repository has no issue tracker. |
| Open issues, flagged/pending issues, open PRs | issue / pull_request | insufficient_evidence | NOT CHECKED: GitHub read tools were unavailable (re-tried by the orchestrator). Empty lists in the manifest mean unchecked, not none. |
| Releases and tags | release / tag | insufficient_evidence | NOT CHECKED. No local tags were found; the local clone may lack remote tags. |

## 4. System health assessment

Each assessment states what was read and what was not. None is a clean bill of health.

| Dimension | Assessment and uncertainty |
|---|---|
| Architecture | Concentrated risk. The core engine is one ~1,500-line function and plan-to-engine mapping another ~1,530-line function (ARC-005); stage modules import back into the consolidated engine file; a second legacy SQLite layer coexists with the plan/app stores (ARC-004); the frontend is 52 order-dependent module scripts joined by window globals and a wrapper chain (ARC-007). The RMD divisor duplication noted in recon is resolved by delegation. Most stage bodies and optimizers were not read. |
| Usability and accessibility | Data-loss and honesty gaps in core workflows (UX-001, UX-002, UX-011) and weak error feedback (UX-004); focus visibility on custom switches (UX-007) and an unlabelled admin surface (UX-006). Several accessibility claims are unproven (UX-005, UX-009, UX-012, UX-013). Static reading only: nothing was rendered, no screen reader was used and contrast figures are hand estimates. |
| Documentation | Status text contradicts shipped work (DOC-001) and the documented layout rule is not being followed (DOC-002); reference documents carry stale facts (DOC-005); end-user text and release notes lag the UI and engine (DOC-003, DOC-006, DOC-007). A plain-language Concepts Guide exists but is not linked (DOC-004). API and functional references were compared to the route manifest by route name only. Archive contents were not reviewed. |
| Quality and testing | Strong design intent (golden-master provenance, frozen date seam, seeded randomness, ratchet tests) is undercut by a release gate that runs a small share of the files (QA-002), vacuous or skipping tests (QA-006), no behavioural tests for the Monarch extractor (QA-004) and no depleting-household golden (QA-005). No test was executed and no coverage report exists. |
| Financial correctness | Federal 2026 tables match the planner's recollection of the cited sources and carry a 'verified' status in the dataset; that is consistent with the dataset status and was not re-fetched. Defects and gaps found: qualified dividends at ordinary rates (FIN-003), brokerage gains missing from AGI-keyed rules (FIN-001), asymmetric survivor step-up (FIN-010), a Monte Carlo headline whose shipped default Roth regime is unmeasured and whose tile shows two figures with different success definitions (FIN-002), a non-functional Social Security lever (FIN-008). Rule-value currency (AMT, QLAC/QCD, states, mortality) requires external verification (FIN-005, FIN-006, FIN-011). Scope questions remain for early retirement and the earnings test (FIN-004, FIN-007). Optimizers, the inherited-account and 10-year heir-tax branch, remarriage and divorce, rental and equity-compensation logic, the Social Security funding-discount assumption and PIA derivation, return and inflation assumptions, and the ACA enhanced-subsidy default were largely or wholly not read. The financial review is partial. Professional review applies before any rule change goes live. |
| Data integrity | Import validation accepts numeric forms the engine treats differently, and a malformed liability can empty the list (QA-003); legacy fallbacks may return stale balances (ARC-004, not reproduced); a sensitive file is tracked (QA-001). Plan stores use transactional forward-only migrations (src/stores/db.py:1-140), which was read and raised no finding. |
| Security and privacy | Desktop mode is the default and runs in-process without a socket. Server mode has an authorization stub and an Origin heuristic without a Host allow-list (ARC-001); inert hosted-mode defaults remain (ARC-009). Secrets use the OS keyring (src/secrets_store.py:1-60) and log output is redacted (src/bootstrap.py:70-100), both read without finding. Secret scanning was not run; backups and exports were not inspected. |
| Performance | Not measured. A September baseline records a 76.9 s build with the Social Security sheet at 37.8 s, and the claim sweep calls the Monte Carlo engine 81 times per build; later parallelisation work exists. The frontend loads 52 scripts. No performance finding was raised. |

## 5. Material findings

Confirmed and partially confirmed findings (40), ordered by severity. Every finding in the register has a status other than unverified; none is flagged unverified. Insufficient-evidence and duplicate entries are in section 13. A consolidated jurisdiction, rule-year, rule-status and authority table for FIN-001 to FIN-011 is in section 11.

Verification-status key: confirmed = evidence reopened and the claim holds; partially_confirmed = the core claim holds but part was not substantiated or was narrowed (see the verification note).

### QA-001 — Tracked backup of the real trends log escapes the .gitignore rule that protects it

- **Expert:** quality · **Category:** data-integrity-privacy · **Severity:** high · **Confidence:** high
- **Inspection status:** finding_identified · **Verification status:** confirmed
- **Evidence citations:**
  - `.gitignore:33-38` — financial_trends_reporter/data/*.jsonl — Comment says the runtime log holds real net worth, cashflow and spending figures and is in the same PII class as input/. The only pattern is *.jsonl, so a .jsonl.bak does not match.
  - `financial_trends_reporter/data/financial_trends_log.jsonl.bak` — Tracked in git (git ls-files, re-confirmed by the orchestrator; 148,152 bytes per the expert). It holds 23 dated snapshots (2026-09-03 to 2026-10-12) with net_worth, cashflow, holdings.by_account, ytd_expense_hierarchy and similar keys. Account labels contain a personal or business name. No values are copied here. Added in commit 0bd50f3 (#215), which is reachable from main. The file's contents were not opened by the verifier or the orchestrator.
  - `financial_trends_reporter/trends_log.py:80-93` — prune_entries — The app itself writes <log>.bak next to the log (shutil.copy2). financial_trends_reporter/tools/prune_trends_log.py:4 does the same, so any prune creates another unignored copy.
  - `tests/test_repo_hygiene_guards.py:96-125` — test_no_tracked_file_is_gitignored — The only guard against force-added private data tests 'tracked AND ignored'. A file no pattern matches passes it, so this file is not caught.
  - `tests/test_demo_plan_data_is_fictional.py:82-142` — The fictional-data checks cover input/demo only. Nothing scans other tracked data files for real figures.
- **Observed behavior:** A file the repo's own comments classify as real, sensitive financial data is committed to main under a suffix the ignore rule does not cover. The application regenerates that suffix on every log prune. No test inspects tracked data files by content or by name pattern outside the tracked-and-ignored check.
- **Impact:** Real household balances and account names are in git history. Deleting the file from HEAD does not purge the blobs once pushed. Repository visibility could not be checked because the GitHub tools were unavailable. The exposure is severe if the remote is shared or public, and still a hygiene breach if it is private.
- **Affected workflows/scenarios:** Trends reporter log pruning and backup; Repository publishing and sharing; Backup and export hygiene
- **Root cause:** The ignore rule names one extension and the app creates a second extension. The hygiene test only checks tracked files that are also ignored, so it cannot see a data file no rule matches.
- **GitHub contextual evidence:** pull_request 215 (confirmed) — local git: 0bd50f3
- **Options and tradeoffs:**
  1. Remove the file from HEAD, widen the ignore rule to financial_trends_reporter/data/* with a !.gitkeep exception (this also covers .bak and .rejected), and add a hygiene test that fails on any tracked file under data directories other than .gitkeep.
  2. Do option 1, then also rewrite history (git filter-repo) to purge the blob, then force-push and notify collaborators. This has a real coordination cost and only fully works if no clone or fork exists.
  3. Remove the file from HEAD and leave history alone, accepting the exposure if the remote is private. Cheapest, but it leaves the recoverable copy.
- **Recommendation:** Do option 1 now. Have the owner decide on option 2 once the repository's visibility and clones are known. Never copy the file's values into any report.
- **Dependencies:** Owner decision on history purge; Confirmation of remote visibility
- **Implementation considerations:** The app's own .bak and .rejected sidecars live in the same directory, so ignore the whole directory instead of enumerating suffixes. Check the Monarch balances store and any other runtime directory for the same pattern.
- **Risk of change:** Low for the ignore and test change. A history rewrite is high-risk and affects every clone.
- **Verification method:** After the change, git ls-files financial_trends_reporter/data should list only .gitkeep. A new hygiene test that tracks a dummy .bak under that directory should fail.
- **Verification note:** Confirmed with git ls-files that financial_trends_log.jsonl.bak is tracked (orchestrator re-ran git ls-files: the directory lists .gitkeep and the .bak). .gitignore:36 only ignores *.jsonl. Commit 0bd50f3 is on main and on the origin branch. The file's contents were not opened, so the claim that it holds real data rests on the expert's description and the .gitignore comment. Remote visibility is unknown, so impact is conditional. High severity accepted given the stated PII class.
- **Linked implementation items:** WI-001, WI-004

### ARC-001 — Server mode has no authentication or Host allow-list; LAN binding is a supported setting

- **Expert:** architect · **Category:** security-privacy · **Severity:** medium · **Confidence:** medium
- **Inspection status:** finding_identified · **Verification status:** confirmed
- **Evidence citations:**
  - `src/server/security_audit.py:82-96` — _authorized_and_identity, _current_user — Authorization is a stub that always returns True. Every caller is user 'local' with role 'advisor', so the permission checks via _require() never deny anyone.
  - `src/server/app_core.py:985-1060` — _cross_site_request, _csrf_and_origin_gate, _security_gate — The CSRF/Origin gate only compares Origin/Referer to the request's own Host header; there is no allow-list of host names. A request with neither Origin nor Referer skips the token check. GET requests are never gated.
  - `src/server/security_audit.py:317-333` — _csrf_token_for_current_request — The CSRF token is an HMAC over the constant basis 'local:local' (when no bearer credential is present), so the same token is issued to every caller.
  - `src/server/base_routes.py:47-55` — auth_session, auth_login — Public routes that hand out the CSRF token to any caller.
  - `src/server/plan_routes.py:164-175` — _server_path_requires_allowlist — The code expects dashboard_host to be set to a non-loopback address ('exposed on a home LAN'). It adds only a folder allow-list for that case, not authentication.
  - `src/runtime_config.py:64,154` — dashboard_host — The host is configurable via env var or a system setting. The default is 127.0.0.1.
  - `src/http_runtime/server.py:15-20,67-69` — _Handler._handle, run_local_server — Binds the configured host with ThreadingHTTPServer. No Host validation and no request body size cap (the handler reads Content-Length bytes unconditionally).
  - `main.py:86-112` — _run_server — Server mode launches the same unauthenticated app. Desktop (PyWebView, in-process, no socket) is the default mode.
- **Observed behavior:** In server mode (--mode server or src/server/__main__) every route runs as an 'advisor' with no credentials. Reads are open and writes are protected only by an Origin comparison against the attacker-controllable Host header, plus a token that any caller can fetch from /api/auth/session. There is no allow-list of loopback host names, so a DNS-rebinding page, whose Origin equals its own Host, passes the gate. The page can then read the household's full plan, exports and Monarch data, and write to it. If dashboard_host is set to a LAN address, any LAN peer has the same access.
- **Impact:** Exposure of household financial data (plan rows, exports, balances) and unauthenticated modification or replacement of plan data in server mode. The default desktop mode is not affected, and the default bind is loopback, which limits likelihood.
- **Affected workflows/scenarios:** server-mode launch (debug/browser access); any non-default dashboard_host configuration; /api/export/*, /api/import/commit, plan Save As/Load routes
- **Root cause:** The hosted/SaaS auth layer was removed (the code comments cite 'LOCAL only'), but the optional HTTP transport kept only an Origin/CSRF heuristic and no Host-header validation or access credential. A LAN host is still accepted as configuration.
- **Assumptions, jurisdiction and rule year:** jurisdiction: n/a; rule year: not stated; assumptions: none stated
- **Options and tradeoffs:**
  1. Reject any request whose Host header is not a loopback name or the explicitly configured host. Refuse to start in server mode on a non-loopback host unless an access token is configured.
  2. Add a per-launch random bearer token, printed or opened with the browser URL and required on every route, including GETs.
  3. Remove server mode and non-loopback host support entirely and keep desktop-only (lowest risk, loses the debugging path).
- **Recommendation:** Add the Host allow-list and the non-loopback startup guard first (small change), then consider the launch token. Also drop the unused SaaS-era environment defaults (see ARC-009).
- **Dependencies:** ARC-009
- **Implementation considerations:** Must keep the desktop bridge exemption (_no_http_transport). Playwright/e2e and the browser-folder import flow rely on same-origin requests. Reverse-proxy (ProxyFix x_host=1) use must be reconsidered, because X-Forwarded-Host can also be spoofed.
- **Risk of change:** Low to medium: tests and scripts that call the server with arbitrary Host headers would fail until updated.
- **Verification method:** Add unit tests for a spoofed Host/Origin pair (rebinding) and a non-loopback start. Manually verify that browser server mode still works on localhost and 127.0.0.1.
- **Verification note:** Opened security_audit.py:82-90 (auth check returns (True, None); fixed 'local' advisor). app_core.py:985-1070 compares Origin/Referer only to the request's own Host header; only non-GET requests are gated; no Origin/Referer skips the token check; desktop bridge exempt. Grep of src/server, src/http_runtime, runtime_config and main.py found no Host allow-list. http_runtime/server.py reads Content-Length bytes with no cap and binds the configured host. Existing mitigations: loopback default bind, desktop default mode, folder allow-list for non-loopback hosts (plan_routes.py:169-173). Kept medium because default exposure is low; no exploit was run. The ProxyFix point is conditional (see ARC-009). Not every line of the CSRF-token and base_routes citations was opened.
- **Linked implementation items:** WI-006

### ARC-003 — Failures of derived-result steps are recorded in a warnings list that nothing reads, so reports can silently omit sections

- **Expert:** architect · **Category:** error-handling-observability · **Severity:** medium · **Confidence:** medium
- **Inspection status:** finding_identified · **Verification status:** confirmed
- **Evidence citations:**
  - `src/report_compute.py:284-311` — run_projection_artifacts — Wraps the Roth guardrail analysis, PlanResult contract, and ReportSpec in `except Exception`. Each handler only appends to cfg['config_contract_warnings'] and does not log. The advisor_readiness handler stores the exception text as a single warning and the status 'REVIEW_REQUIRED'.
  - `src/plan_config.py:78-90` — PlanConfig.as_engine_dict — The only other place that touches config_contract_warnings: it merges input warnings into the same list.
  - `src/data_io.py:1870` — parse_client — A third writer to the same list.
  - `src/report_compute.py:312-317` — save_result_snapshot — By contrast, this failure is logged with the logger (warning with traceback).
- **Observed behavior:** A repository-wide search of src/, frontend/ and tools/ found config_contract_warnings only in the three writer sites and in plan_config.py's merge. No reporting sheet, API payload or frontend module reads it. When attach_plan_result, report-spec construction or the Roth guardrail analysis raises, the build continues and the exception text is neither shown to the user nor logged.
- **Impact:** A build can finish 'successfully' with missing PlanResult/ReportSpec/guardrail content and no indication to the user, which weakens trust in outputs. Diagnosis requires a debugger because nothing is logged.
- **Affected workflows/scenarios:** workbook/PDF/dashboard build; Roth guardrail views; PlanResult-driven result explorer
- **Root cause:** The 'never block the build' defensive pattern was implemented without a consumer for the warning channel and without logging.
- **Assumptions, jurisdiction and rule year:** jurisdiction: n/a; rule year: not stated; assumptions: none stated
- **Options and tradeoffs:**
  1. Log each handler with logging.exception and surface config_contract_warnings in the build result and UI banner.
  2. Fail the build for the contract steps (PlanResult/ReportSpec) and keep best-effort only for optional analyses.
  3. Do both: fail on contract errors, warn visibly on optional analyses.
- **Recommendation:** Option 1 minimum: add logging immediately and surface the list in build diagnostics. Decide per step in option 3 which failures are acceptable.
- **Dependencies:** none
- **Implementation considerations:** A failed contract step may currently be masked by tests that tolerate absent keys. Grep other `except Exception` blocks that set only a flag (about 400 `except Exception` sites exist in src/; not individually reviewed).
- **Risk of change:** Low for logging, medium for fail-fast.
- **Verification method:** Unit test that forces attach_plan_result to raise and asserts a log record plus a visible warning in the build payload.
- **Verification note:** report_compute.py:284-311 shows three except Exception handlers that only append to cfg['config_contract_warnings'], with no logging. A grep of src, frontend, tools and financial_trends_reporter found only the writers in report_compute.py, plan_config.py:80-86 and data_io.py:1870; the one other hit was a test file not opened, so a hidden consumer is unlikely but not excluded. The neighbouring save_result_snapshot handler does log. Effect is silent omission, not wrong numbers, and only on an exception, so medium is the upper bound.
- **Linked implementation items:** WI-007, WI-019

### ARC-005 — Core engine and input mapping are very large single functions with a circular dependency between stage modules and the consolidated engine file

- **Expert:** architect · **Category:** modularity-coupling · **Severity:** medium · **Confidence:** high
- **Inspection status:** finding_identified · **Verification status:** confirmed
- **Evidence citations:**
  - `src/projection_stages/deterministic_engine.py:82-1581` — run_deterministic_projection_stage — One function of about 1,500 lines. By AST measure, the next-largest function in the file is 78 lines. Housing and mortgage helpers are nested closures.
  - `src/data_io.py:577-2111` — parse_client — One function of about 1,530 lines that maps the plan rows to the engine config.
  - `src/planning_engines.py:1-28,4219,5413,6560` — module header; monte_carlo_exact_scalar; _mc_vectorized_projection; monte_carlo — 6,858-line consolidation of 8 former files, with 576-, 586- and 297-line functions. The header warns against re-splitting because of circular imports.
  - `src/projection_stages/deaths_and_spousal_rollover.py:7,181` — _legacy_pe — A stage module imports planning_engines (the module that calls the stage engine) and calls apply_death_transition back on it.
  - `src/projection_stages/roth_conversion_and_agi_tax.py:5,287-302` — _legacy_pe — Same back-reference for plan_roth_conversion and apply_roth_conversion.
  - `src/projection_stages/year_state.py` — (listed in the stage family) — Stages exchange state through the engine's mutable locals and the year state object. Not examined in depth.
- **Observed behavior:** The financial core is concentrated in a few giant units. The 'stage' extraction exists as files, but the main function still owns the control flow and state, and the stages call back into the consolidated module they were extracted from.
- **Impact:** High regression risk for any engine change. Local reasoning, unit testing of single stages and reuse by the vectorized engine are difficult. The consequence is more dependence on golden-master tests that pin dollar figures (see FIN-002 for the duplicated Monte Carlo logic).
- **Affected workflows/scenarios:** every projection/build; Monte Carlo; Roth conversion and death-transition logic
- **Root cause:** Incremental consolidation and extraction without first fixing the dependency direction (the pure kernels sit in the same file as the orchestrator).
- **Assumptions, jurisdiction and rule year:** jurisdiction: n/a; rule year: not stated; assumptions: none stated
- **Options and tradeoffs:**
  1. Move the pure kernels (death transition, Roth conversion plan, withdrawal, growth) into a dependency-free module the stages import. Then split planning_engines along the existing BEGIN/END markers.
  2. Only extract the nested closures and parse_client sections into private helper modules, without moving the kernels (smaller).
  3. Leave as is and rely on the golden-master tests (no effort, ongoing risk).
- **Recommendation:** Option 2 first, as characterization-test-protected mechanical moves. Then option 1 to break the circular import, so kernel sharing with the vectorized engine (FIN-002) becomes possible.
- **Dependencies:** FIN-001; FIN-003; FIN-010; FIN-002
- **Implementation considerations:** The golden-master suites (frozen_sample_plan, synthetic, reference) must stay byte-stable during the refactor, so it must not be interleaved with the correctness changes that re-pin them. The regen tooling would hide behavior changes, so keep the pins locked.
- **Risk of change:** Medium: high-volume mechanical change in the most sensitive code, mitigated by golden masters.
- **Verification method:** Golden-master and projection-invariant tests unchanged. A static check that stage modules do not import planning_engines.
- **Verification note:** deterministic_engine.py is 1581 lines and the main function starts at line 82, so the ~1,500-line claim holds. deaths_and_spousal_rollover.py:7 does `from .. import planning_engines as _legacy_pe` and refers back to planning_engines.apply_death_transition, so the circular dependency is real. parse_client and the other function sizes were not re-measured. The architectural impact is an inference, but a reasonable one.
- **Linked implementation items:** WI-034, WI-037

### ARC-007 — Frontend is 52 order-dependent module scripts coupled through window globals and a monkey-patch chain

- **Expert:** architect · **Category:** frontend-structure · **Severity:** medium · **Confidence:** medium
- **Inspection status:** finding_identified · **Verification status:** confirmed
- **Evidence citations:**
  - `frontend/index.html:91-142` — script tags — 52 <script type="module"> tags in a fixed order, each with a hand-edited ?v= cache-busting query (for example dashboard.js?v=63).
  - `frontend/js/dashboard.js:3406,3563,6690-6810` — renderMain, showStepHelp, window bridge — 6,883-line file marked auto-generated by a codemod. It exposes top-level bindings to window using Object.defineProperty getters and setters 'for reassigned functions (monkey-patch decorator chains)'.
  - `frontend/js/dashboard_decomp_roth_guardrails.js:419-422` — prevRenderMain — Wraps window.renderMain and calls the previous one.
  - `frontend/js/dashboard_decomp_tax_assumptions.js:217-220` — prevRenderMain — Another wrapper in the chain.
  - `frontend/js/dashboard_batch_assumption_edit.js:499` — renderMain = — Direct reassignment of the shared binding.
  - `frontend/js/dashboard_source_truth_banners.js:673-680` — renderMain =, showStepHelp = — Reassigns both.
  - `frontend/js/dashboard_decomp_row_model.js:1-14` — header comment — A 5,595-line 'shared core' of 172 functions, extracted verbatim from dashboard.js by call-graph fan-in.
  - `frontend/js/dashboard_decomp_spending_taxonomy.js:203` — inline onclick handler — Inline onclick="..." handlers require global functions.
- **Observed behavior:** The UI works through ES module files that still behave like one global script. Correctness depends on script order, on which wrapper was installed last, and on window-scoped names. Inline event handlers force global functions, and no Content-Security-Policy header was found in src/ or frontend/.
- **Impact:** Adding or reordering a module can silently change what renders. There is no tree-shaking or bundle, so 52 requests and about 39k lines load at startup (size and latency not measured). Hard to unit-test in isolation, and CSP cannot be adopted while inline handlers remain.
- **Affected workflows/scenarios:** all UI pages; page render/step navigation; development of new UI features
- **Root cause:** Mechanical codemod split of a monolithic dashboard.js into modules preserved globals and decorator chains rather than introducing explicit registration.
- **Assumptions, jurisdiction and rule year:** jurisdiction: n/a; rule year: not stated; assumptions: none stated
- **Options and tradeoffs:**
  1. Replace the renderMain/showStepHelp decorator chain with an explicit hook registry (register(step, renderer)) and export it from one module.
  2. Bundle with a build tool (for example esbuild) to remove hand-maintained ?v= and script order.
  3. Defer: freeze the module list and add a test that asserts script order and the set of wrappers.
- **Recommendation:** Option 1 first because it is the real coupling, then option 2. Option 3 is a cheap interim guard.
- **Dependencies:** none
- **Implementation considerations:** Tests eval() dashboard.js as a classic script (comment at dashboard.js:6699). The Playwright suite exists (playwright.config.js) but was not examined. The bundler would add a Node build step to the PyInstaller release. The usability fixes (UX-001..UX-010) edit the same row-model and navigation code, so the registry change should follow them.
- **Risk of change:** Medium.
- **Verification method:** Playwright navigation across all steps before and after. Add a lint test that no module assigns window.renderMain outside the registry.
- **Verification note:** frontend/index.html has 52 type="module" tags. dashboard.js:3406 declares `let renderMain` and line 6798 bridges it to window with a getter/setter. dashboard_decomp_roth_guardrails.js:419-422 and dashboard_decomp_tax_assumptions.js:217-220 wrap prevRenderMain. dashboard_batch_assumption_edit.js:499 reassigns renderMain directly. A grep for Content-Security-Policy in src and frontend returned nothing. Not verified: the 6,883-line and ~39k-line sizes, the showStepHelp wrapper, the inline onclick handlers and the cache-busting query strings. Maintainability risk, not a user-visible defect, so medium is the ceiling.
- **Linked implementation items:** WI-015, WI-035

### DOC-001 — Specs and living reference notes still say 'nothing implemented / draft for owner go' for work that has shipped

- **Expert:** documentation · **Category:** documentation-accuracy / design-document-status · **Severity:** medium · **Confidence:** high
- **Inspection status:** finding_identified · **Verification status:** confirmed
- **Evidence citations:**
  - `docs/superpowers/specs/2026-10-14-items-345-347-design.md:3` — Status banner — Says 'FINAL - awaiting owner approval to begin execution. Nothing implemented.' Local git subjects show items 345/346/347a-c merged (#211, #212, #213), and trends code now contains the per-account flows the spec proposed (financial_trends_reporter/trends_metrics.py:177,329).
  - `docs/superpowers/specs/2026-10-13-gap-closure-plan.md:1-3` — Status banner — 'draft for owner go. Nothing here is executed.' Merge subjects #205/#206/#207/#208/#209 show Tiers 1-3 landed; the plan's own later sections have a 'Tier 2 status (PR #205, draft)' block, so the banner contradicts the body.
  - `docs/superpowers/specs/2026-10-15-items-349-354-design.md:3` — Status banner — 'design for review, nothing implemented.' Release note documentation/reference/release_notes/2026-10-monarch-mapping-and-trends-fixes.md:1-33 documents items 349-354 as delivered (#217).
  - `docs/superpowers/specs/2026-10-14-monarch-account-balances-trends-plan.md:3` — Status line — 'awaiting approval of the Open items section' although release note 2026-10-monarch-balances-and-reconciliation.md exists and #215 is merged.
  - `docs/superpowers/specs/2026-10-05-master-plan-tiers-and-file-elimination.md:3` — Status banner — 'Nothing here is executed' while documentation/reference/release_notes/2026-10-wp11-file-elimination.md describes WP11 as done and the rental module (WP12) exists in src/rental_tax.py and src/projection_stages/rental_property.py.
  - `docs/superpowers/specs/2026-10-05-rental-property-module-design.md:3` — Status banner — 'draft for owner review. Nothing here is built' but rental code exists (src/server_services/rental_service.py, src/stores/rental_repo.py) and NAV_FEATURE_MAP lists the Rental Properties page.
  - `documentation/reference/RENTAL_TAX_RULES.md:1-6` — Status line — A living reference doc whose status reads 'for owner / tax-preparer review (checkpoint before the engine integration, WP12.2)', yet its own verification note says the preparer verified it on 2026-10-13, and it cites the legacy design path docs/superpowers/specs/... .
  - `documentation/reference/CAPITAL_GAINS_IN_AGI.md:1-30, 75-90` — Status + section 1 'Today (the gap)' + section 5 — Status says approved and implemented, but section 1 still describes the pre-fix behaviour for home and rental sales in the present tense ('Today ... not added to AGI'). Code now adds it: src/projection_stages/deterministic_engine.py:1236-1241 and 1438-1441 (orchestrator opened both). Section 5 decision 1 correctly records that brokerage-cascade gains remain excluded (see FIN-001), so only the home/rental part of section 1 is stale.
  - `documentation/DOCUMENTATION_INDEX.md:1-6` — Layout rule — The rule is that reference/ is true today, future/ is not yet built, and shipped material is archived. The banners above break it.
- **Observed behavior:** At least six design/plan documents under docs/superpowers/specs and two living reference documents carry status text that contradicts what the code, release notes and local git history show as shipped. The index marks every legacy spec 'status-uncertain' because none carries a reliable closed/implemented marker.
- **Impact:** A maintainer or non-technical owner cannot tell from the document what is built, what is waiting for approval and what is only a proposal. Someone could re-approve or re-implement shipped work, or trust the 'Today' section of CAPITAL_GAINS_IN_AGI.md as current behaviour for home and rental sales. It also blocks conclusive document-eligibility decisions in future reviews.
- **Affected workflows/scenarios:** Planning and approving work; Onboarding a new maintainer; Reading tax-rule documents before changing the engine; Future system reviews
- **Root cause:** Specs were written as approval gates and never updated when the work merged. The documented rule (move to archive/ when work ships, record what shipped) has no check behind it. A path-citation test exists but nothing tests status.
- **GitHub contextual evidence:** pull_request #211 (confirmed); pull_request #212 (contextual_only); pull_request #213 (contextual_only); pull_request #215 (confirmed); pull_request #217 (confirmed); pull_request #205 (contextual_only); pull_request #206 (contextual_only); pull_request #207 (contextual_only)
- **Options and tradeoffs:**
  1. Update each banner to 'Implemented in PR/commit X on date; superseded by <living doc>' and move shipped specs to documentation/archive/superpowers (matches the stated rule).
  2. Add a required machine-readable front-matter field (status: draft|approved|implemented|superseded, plus a shipped-in reference) and a small test that fails when a spec under docs/ or future/ lacks it.
  3. Do both: fix the current banners now, and add the front-matter test to prevent recurrence.
- **Recommendation:** Do both: correct the eight stale statuses, move shipped specs to archive/, rewrite CAPITAL_GAINS_IN_AGI.md section 1 as 'Before this change' (and update it again when FIN-001 is fixed), and add a status front-matter test.
- **Dependencies:** DOC-002 (location of legacy specs); FIN-001 (the CAPITAL_GAINS_IN_AGI.md status changes again when brokerage gains are fixed)
- **Implementation considerations:** tests/test_documentation_path_citations_regression.py fails on missing documentation paths, so moves must be paired with citation updates (RENTAL_TAX_RULES.md, BACKLOG.md and the plan notes cite docs/superpowers paths). Confirm each 'shipped' claim against the merge PR rather than the subject line.
- **Risk of change:** Low; documentation only, apart from the citation test.
- **Verification method:** After the change, grep status banners under docs/ and documentation/future/ and confirm each matches a merge or code path. Run the path-citation test.
- **Verification note:** Opened all eight docs: the banners say 'Nothing implemented' or 'draft'. The engine at deterministic_engine.py:1236-1240 adds sale gain to IRMAA MAGI. Release notes cover the Monarch work. CAPITAL_GAINS_IN_AGI.md says 'implemented' but section 1 still reads 'Today ... not added'. RENTAL_TAX_RULES status contradicts its own verification line. Merge-PR claims for #205-#213 rest on commit subjects only.
- **Linked implementation items:** WI-016, WI-032

### DOC-002 — Legacy docs/superpowers tree is still being added to, against the documented layout rule, so there is no single trustworthy home for plans

- **Expert:** documentation · **Category:** documentation-layout / discoverability · **Severity:** medium · **Confidence:** high
- **Inspection status:** finding_identified · **Verification status:** confirmed
- **Evidence citations:**
  - `documentation/reference/CONTRIBUTING.md:92-109` — Documentation layout — Says do not create files under docs/; new specs and plans go to documentation/future/; shipped ones move to archive/.
  - `documentation/DOCUMENTATION_INDEX.md:1-6` — Layout rule — Repeats that docs/superpowers/ is legacy and no new files should be added.
  - `docs/superpowers/specs/2026-10-13-gap-closure-plan.md:1` — file — Added after the rule. Git history (git log --diff-filter=A) shows docs/superpowers/specs/ gaining 2026-10-13-gap-closure-plan, 2026-10-14-items-345-347-design, 2026-10-14-monarch-account-balances-trends-plan and 2026-10-15-items-349-354-design on 2026-10-13 to 2026-10-15. The rule text was added in commit 827cda1 on 2026-10-12.
  - `docs/superpowers/plans/2026-09-16-housing-financing-and-zip-ux.md:1` — file — 26-27 plan/notes files and a perf-baseline JSON sit in docs/superpowers/plans. The manifest classifies all of them 'status-uncertain' because none lives in the future/archive tiers or carries a status.
- **Observed behavior:** 16 specs and 26-27 plan/notes files plus a JSON baseline remain in the 'legacy' docs/ tree. Four of the specs were created after the rule was written. documentation/future/ holds only 5 items and archive/ is large. The living docs (RENTAL_TAX_RULES.md) still cite docs/superpowers paths as design sources.
- **Impact:** The newest and most active design records are in the place the project itself labels as the wrong place, and are not covered by the three-tier status convention. People looking for 'what is planned versus done' have to open each file.
- **Affected workflows/scenarios:** Finding the current design; Applying the three-tier layout; Future review eligibility decisions
- **Root cause:** The layout rule is prose only, and AI-assisted sessions kept writing to the familiar docs/superpowers path (the CONTRIBUTING.md text itself notes this directory 'reappeared after the consolidation').
- **GitHub contextual evidence:** pull_request #217 (contextual_only); pull_request #215 (contextual_only)
- **Options and tradeoffs:**
  1. Move shipped specs/plans to documentation/archive/superpowers and unshipped ones to documentation/future/superpowers; remove docs/.
  2. Keep docs/superpowers as the real active location and rewrite the layout rule to say so.
  3. Leave the files and add a test that fails when a new file is added under docs/.
- **Recommendation:** Option 1 plus the guard test from option 3; the rule is already written and the other tiers already exist. Add a repo instruction file pointer so AI sessions write to future/ by default.
- **Dependencies:** DOC-001
- **Implementation considerations:** Run the path-citation test after moving. The 4 post-rule specs likely belong in archive (shipped) once DOC-001 is confirmed. Tools and tests that read perf-baseline-2026-09-17.json by path need checking before the move (not inspected).
- **Risk of change:** Low to medium: broken path citations in code comments, tests or tools if any are missed.
- **Verification method:** git ls-files docs/ returns nothing; the citation test is green; the index lists every moved file in a tier.
- **Verification note:** git log --diff-filter=A shows four specs added to docs/superpowers/specs on 2026-10-13 to 2026-10-15, after the layout rule commit 827cda1 on 2026-10-12. There are 16 specs and 27 plan files (the finding said 26). CONTRIBUTING.md lines 92-109 were not re-opened by the verifier; the rule text is taken from the finding.
- **Linked implementation items:** WI-016

### FIN-001 — Capital gains realized by selling taxable-account holdings never enter AGI, so IRMAA, NIIT, ACA credit, Social Security taxation and Roth guardrails all see too little income

- **Expert:** financial_planner · **Category:** tax-calculation-correctness · **Severity:** medium · **Confidence:** high
- **Inspection status:** finding_identified · **Verification status:** partially_confirmed
- **Evidence citations:**
  - `documentation/reference/CAPITAL_GAINS_IN_AGI.md:7-20, 77-85` — section 1 'Today (the gap)' and section 5 decision 1 — The owner's own design note says gain from selling investments in taxable accounts (the cascade's ltcg_gain) is missing from AGI, MAGI and the NIIT threshold test. Only home and rental sales were fixed. The remainder was deferred as 'a separate follow-up PR'. The same note says fixing it would move every plan with taxable withdrawals. (Orchestrator opened lines 1-30 and 75-90 and confirms decision 1 as quoted.)
  - `src/projection_stages/deterministic_engine.py:1236-1241, 1438-1441` — sale_gain_in_agi — Only the home/rental sale gain (home_sale_ltcg_gain) is added to irmaa_magi_current and to row['agi']. The cascade's brokerage ltcg_gain, assigned at ~1376, is never added to either. (Orchestrator opened 1228-1245 and 1432-1445 and confirmed the two additions; the ~1376 assignment was not re-opened.)
  - `src/projection_stages/withdrawal_cascade_investment_tax.py:225-235` — _refresh_investment_taxes — NIIT is computed as niit_tax(base_nii + net_gain, state.agi, ...). state.agi is the first-pass AGI that excludes the gain just realized, so the MAGI-minus-threshold leg of the NIIT test is understated.
  - `src/projection_stages/roth_conversion_and_agi_tax.py:578-593, 623, 787` — apply_agi_and_tax — Taxable Social Security, ACA MAGI and the OBBBA senior-deduction phase-out are all derived before the cascade realizes brokerage gains, from non-gain AGI. They are never revisited.
- **Observed behavior:** The engine computes ordinary tax and stacked LTCG tax correctly for brokerage sales. But AGI, MAGI, IRMAA MAGI (used two years later), NIIT MAGI, Social Security provisional income, ACA premium-credit MAGI and the senior-deduction phase-out all ignore those realized gains. Home and rental sale gains are handled correctly (PR #207).
- **Impact:** Every plan that funds spending from appreciated taxable holdings understates future IRMAA tiers and surcharges, NIIT and (for pre-65 retirees) ACA MAGI, so the credit is overstated. It also understates Social Security taxation and phase-out effects. Roth-conversion and withdrawal sizing guardrails therefore have too much apparent headroom and can recommend conversions that cross IRMAA or ACA thresholds. Results are optimistic. The size depends on gain realization, and for a large brokerage drawdown it can be several thousand dollars a year (not measured).
- **Affected workflows/scenarios:** Withdrawal cascade and taxable-account liquidation; Roth conversion fill-to-IRMAA and fill-to-bracket guardrails; ACA bridge-year premium credit (age <65); IRMAA two-year lookback; NIIT; Survivor household IRMAA/MAGI after a first death
- **Root cause:** Realized gains are computed after AGI is finalized for the year, in the withdrawal cascade. Folding them back into AGI is a second-pass change that moves every golden, so the owner deliberately limited PR #207 to home and rental sales.
- **Assumptions, jurisdiction and rule year:** jurisdiction: US federal (IRC 61, 86, 1411, 36B; 42 USC 1395r(i); 20 CFR 418.1115); rule year: Statutory and not year-specific. The dataset covers 2024-2026; later years are extrapolated.; assumptions: Arithmetic correctness defect against statute, not an advice-suitability question. Rules are statutory (hard-coded structure with dataset thresholds). Authority: the repository's own design note, secondary and unverified externally. Review rule: planner sign-off on the closed-form tests and impact table is required before re-pin; CPA review of sample outputs is recommended for phase 2 (ACA and Social Security), not blocking for phase 1.
- **GitHub contextual evidence:** pull_request 207 (confirmed) — (local git subject only: 'Tier 3 PR A: H1 capital gains in AGI, MAGI and IRMAA MAGI')
- **Options and tradeoffs:**
  1. Add the cascade's realized net gain to row AGI, irmaa_magi_current, the NIIT MAGI and the ACA/SS recomputation once the cascade converges, using a second pass or the existing fixed-point loop. Re-pin the goldens through the documented golden-change process.
  2. Phase it: phase 1 is IRMAA MAGI only (two-year lookback, so it needs no same-year recomputation and has no cascade convergence exposure). Phase 2 is NIIT, ACA MAGI and Social Security taxation, all same-year; NIIT is computed inside the cascade fixed-point loop (withdrawal_cascade_investment_tax.py:225-235), so adding the gain to its MAGI changes the gap and needs the convergence test.
  3. Keep the simplification, but add a prominent assumption and limitation notice on the Tax Assumptions page, in the workbook and in the advisor report, stating that brokerage gains are excluded from MAGI-keyed rules. Treat this only as a stopgap.
- **Recommendation:** Implement option 2 with the corrected phasing (IRMAA MAGI first; NIIT, ACA MAGI and Social Security taxation second), and ship the limitation notice in Wave 1 (WI-010a) as a mitigation in the meantime. Estimate the effect on the frozen sample plan first, using the 'measure' mode the maintenance runbook already describes, reporting the IRMAA-only and NIIT effects separately.
- **Dependencies:** Golden-master re-pinning process (GOLDEN_MASTER_RECOVERY_RUNBOOK.md); Interaction with the Roth optimizer and the vectorized Monte Carlo engine (FIN-002); FIN-003 (same stacking path)
- **Implementation considerations:** The cascade fixed-point loop already iterates taxes against gap. Adding gain to MAGI changes NIIT, which changes the gap, so convergence has to be re-verified. NIIT is a same-year tax in the cascade loop (withdrawal_cascade_investment_tax.py:225-235; niit_tax at core.py:1153-1155 is max(0, min(nii, magi - threshold)) x 3.8%), so it belongs with ACA and Social Security in phase 2, not with the IRMAA lookback in phase 1. FIN-001 and FIN-003 partly offset (tax overstated versus MAGI-keyed rules understated), so fixing only one changes the net error; they may be developed and pinned in sequence but should be released together. The vectorized Monte Carlo engine reuses deterministic rows, so it inherits the fix. Update the CAPITAL_GAINS_IN_AGI.md status when done.
- **Risk of change:** Phase 1 (IRMAA MAGI only): low to medium, with no cascade convergence exposure. Phase 2 (NIIT, ACA MAGI, Social Security taxation): medium to high, because the NIIT step changes the gap inside the fixed-point loop. Overall it moves headline net worth, lifetime tax and Roth recommendations for essentially all plans. Golden pins, the Roth strategy comparisons and the paired-path Monte Carlo tests will all change, so it needs a sequenced change with before/after fixtures.
- **Verification method:** Closed-form unit cases: phase 1 - an IRMAA tier two years after a brokerage gain. Phase 2 - MFJ with ordinary AGI of 230k plus a 100k brokerage gain gives NIIT of 3.8% x min(NII, 80k) in the same year, plus a convergence test for the NIIT step and for the ACA and Social Security steps. Add a before/after fixture like H1_BEFORE_AFTER_FIXTURES.txt. Run golden_compare in measure mode. Planner sign-off on the closed-form tests and impact table is required before re-pin; CPA review of sample outputs is recommended for phase 2 (ACA and Social Security).
- **Verification note:** Substantiated: CAPITAL_GAINS_IN_AGI.md section 5 decision 1 says the cascade's ltcg_gain is missing from AGI, MAGI and the NIIT test; deterministic_engine.py:1236-1241 adds only home_sale_ltcg_gain to irmaa_magi_current; withdrawal_cascade_investment_tax.py:225-235 passes state.agi (excluding the gain) to niit_tax. Severity calibrated down from high: it is an owner-approved, documented deferral and the LTCG tax itself is stacked correctly, so the error is limited to MAGI-keyed thresholds. The ACA, Social Security and senior-phase-out claims rest on the same doc's decision 2 (documented simplifications) and were not independently traced. The IRMAA lookback and the 'several thousand dollars' figure were not measured. Planner sign-off (PC-2, upheld): the phasing is corrected so that NIIT is a same-year phase-2 item (withdrawal_cascade_investment_tax.py:225-235; core.py:1153-1155); only IRMAA MAGI has the two-year lookback. PC-3 (partially upheld): the limitation notice moves to WI-010a (P1, Wave 1, no WI-003 dependency) as a mitigation. Severity stays medium: the recorded calibration rationale (owner-approved documented deferral) does not cite the notice, so the planner's view that medium depends on early notice is recorded as dissent rather than adopted as a condition. Status stays partially_confirmed because the ACA, Social Security and senior-phase-out claims were not independently traced (the two re-verification outcomes disagreed; the more conservative status is kept).
- **Linked implementation items:** WI-002, WI-010a, WI-022, WI-024, WI-032

### FIN-003 — Qualified dividends are included in taxable income and taxed at ordinary bracket rates instead of the 0/15/20% rates

- **Expert:** financial_planner · **Category:** tax-calculation-correctness · **Severity:** medium · **Confidence:** medium
- **Inspection status:** finding_identified · **Verification status:** confirmed
- **Evidence citations:**
  - `src/projection_stages/roth_conversion_and_agi_tax.py:156-175, 578-593, 810-811` — agi_income_before_social_security / apply_agi_and_tax — portfolio_qualified is added into non_ss_income and hence AGI. taxable_inc = agi - ded is then taxed through compute_fed_tax_fn as a single ordinary-rate stack. No term separates qualified dividends and applies the preferential schedule.
  - `src/tax_kernel.py:170-190` — ltcg_tax_on_gain — The only preferential-rate path is for realized gains. It takes base = ordinary_income and never receives qualified dividends as preferential income.
  - `src/planning_engines.py:2325-2352` — _ltcg_niit_caps / roth_ltcg_cap — The Roth planner treats qualified dividends as LTCG-rate income that conversions must not push into a higher rate band. This is inconsistent with how the tax stage prices them.
  - `src/data_io.py:93-110` — qualified_dividend_fraction read — The reference data supplies a qualified-dividend fraction by asset class (90% for US equities), so the split is available but unused for rate selection.
- **Observed behavior:** The qualified dividends the model generates from taxable holdings are taxed at ordinary marginal rates (10-37%) rather than 0%, 15% or 20%.
- **Impact:** Federal tax is overstated in every plan with taxable equity holdings. For example, $30k of qualified dividends for an MFJ household in the 22-24% bracket overstates tax by roughly $2-3k a year (illustrative, not measured), and more where the right rate is 0%. The ordinary-bracket 'room' used by fill-to-bracket conversions is also wrongly consumed, so conversions may be undersized. The direction is conservative, but it distorts Roth and withdrawal optimization and the lifetime-tax comparison.
- **Affected workflows/scenarios:** Federal tax calculation; Roth conversion sizing; Withdrawal cascade tax true-up; Lifetime tax and after-tax net worth comparisons
- **Root cause:** Preferential-rate stacking is implemented only for realized LTCG. Qualified dividends are carried as a flat AGI term.
- **Assumptions, jurisdiction and rule year:** jurisdiction: US federal (IRC 1(h)(11)); rule year: 2026 thresholds are in the dataset. Later years are indexed.; assumptions: Statutory rule, hard-coded structure with dataset thresholds. The error direction is conservative (tax overstated). It was found by static reading only. I did not run a fixture. Review rule: planner sign-off on the closed-form tests and impact table is required before re-pin; CPA review of sample outputs is recommended but not blocking.
- **Options and tradeoffs:**
  1. No credible alternative; this is a correctness defect.
- **Recommendation:** Stack qualified dividends with realized gains at the preferential rates in the kernel, in one patch: (a) qualified dividends sit in the 0/15/20 preferential stack below realized gains, ordinary taxable income excludes them, and the preferential stack starts from ordinary taxable income; (b) every call site that builds the stack changes in the same patch - the cascade call at withdrawal_cascade_investment_tax.py:234 (ltcg_tax_on_gain(c, net_gain, max(0, state.taxable_inc), year), where taxable_inc currently contains the qualified dividends as ordinary income), the ltcg_marginal_rate callers (for example src/tlh.py:156-165), the Roth LTCG cap (planning_engines.py:2325-2352) and the other ltcg_tax_on_gain callers such as src/after_tax.py:652; (c) qualified dividends remain in net investment income for NIIT. Then re-check the Roth LTCG guardrail for consistency.
- **Dependencies:** FIN-001 (same stacking path); Golden re-pinning
- **Implementation considerations:** Best done together with, or immediately before, FIN-001 so the stacking base is changed once. FIN-001 and FIN-003 partly offset (tax overstated here, MAGI-keyed rules understated there), so neither should be released to users alone. The ordinary-bracket 'marginal rate' reporting (effective_marginal_rate.py) also needs to use the new base.
- **Risk of change:** Medium: all goldens with taxable portfolios move down in tax. Re-pin with a recorded reason.
- **Verification method:** Closed-form tests that cover qualified dividends and a realized gain together, not dividends alone: MFJ taxable income of 80k ordinary plus 30k qualified dividends plus a realized gain, with 2026 thresholds - the dividends fill the 0% band below 98,900 first, the gain stacks above them at 15% (and 20% only above the upper threshold). Keep a dividends-only case, a case through the cascade call site, and a NIIT case showing the dividends still count as net investment income. Compare against the engine before and after the change.
- **Verification note:** roth_conversion_and_agi_tax.py:156-175 and 810-811 add portfolio_qualified into AGI; taxable_inc = agi - ded is passed to compute_fed_tax, the single ordinary-bracket loop (core.py:842-851). tax_kernel.ltcg_tax_on_gain (170-190) is called only for realized gain, and no qualified-dividend stacking exists. GOLDEN_MASTER_CHANGELOG.md ~1780 confirms the Roth cap treats qualified dividends as known income. No documented simplification justifies the ordinary-rate treatment. The $2-3k example is illustrative. Planner sign-off (PC-3, PC-4, PC-5): a Wave 1 limitation notice (WI-010a) is added, WI-003 is not a dependency of the fix (it uses the 2026 federal tables the dataset marks verified, not re-fetched here), the cascade call site is in scope, and the review rule is stated once (planner sign-off required, CPA review recommended).
- **Linked implementation items:** WI-010a, WI-022, WI-023

### QA-002 — The release gate runs only the unittest-style test files, about 16% of the suite

- **Expert:** quality · **Category:** test-strategy-tooling · **Severity:** medium · **Confidence:** high
- **Inspection status:** finding_identified · **Verification status:** confirmed
- **Evidence citations:**
  - `tools/release_gate.py:29-41` — main — The only test step is python -m unittest discover -s tests -v, followed by 'RELEASE GATE PASSED'. unittest collects only TestCase subclasses.
  - `tests/test_golden_master_pin_provenance.py:1-50` — Module docstring says it is a test so that it 'has to fail the suite'. It has 5 module-level pytest functions and no TestCase, so the release gate never runs it.
  - `tests/test_reference_golden_regression.py:28-69` — Pytest-only functions and parametrization. Not collected by unittest discover.
  - `tests/test_phase_golden_equality_regression.py:26-41` — Pytest-only parametrized golden equality. Not collected.
  - `tests/test_frozen_today_seam_regression.py:54-88` — Pytest-only date seam guards. Not collected.
  - `tests/test_synthetic_golden_master.py:1-20` — Docstring asserts release_gate 'runs unittest discover -s tests', so it gates a release. True for this file because it uses TestCase, and not true of most others.
- **Observed behavior:** A static scan of tests/test_*.py found 88 files containing unittest TestCase classes and 475 files with only pytest-style functions, 563 in total. Two of the golden-master TestCase files (frozen sample plan, synthetic scenarios) do run under the gate. The pin-provenance, reference-golden, phase-golden, frozen-date and hygiene guards are pytest functions and are skipped silently, with no 'collected 0' warning. The release gate also never uses the pytest markers (tiers, slow, nightly).
- **Impact:** A release can print RELEASE GATE PASSED with the governance guards, reference-data golden mirrors, date-seam guard, repo-hygiene guards and most unit and functional suites never executed. That is false assurance on the release path. Whether another process covers the gap was not assessed.
- **Affected workflows/scenarios:** Release packaging; Golden-master discipline; Regression gating
- **Root cause:** The gate was written when the suite was unittest-based and was never updated after the suite moved to pytest. The pyproject marker comment still says 228 files.
- **Options and tradeoffs:**
  1. Run python -m pytest tests -m 'not nightly' (or the full suite) in the release gate, matching the documented pytest workflow.
  2. Keep unittest discover and add a collected-count assertion that fails when it covers fewer files than pytest --collect-only.
  3. Remove the release gate's test step and document that pytest is the only authoritative runner. This leaves the 'gate' name misleading.
- **Recommendation:** Option 1, with a hard minimum on collected test count, so the gate cannot silently shrink again.
- **Dependencies:** Agree whether the slow and nightly tiers belong in a release gate; QA-006 (tests that skip or pass vacuously on a clean checkout should be cleaned up first)
- **Implementation considerations:** The release gate also deletes __pycache__ to keep the package clean, and runtime must be budgeted: the suite includes real workbook builds. xdist is already in requirements-dev.txt.
- **Risk of change:** Low to moderate. Newly executed tests may fail on a clean machine (see QA-006 on live-input dependencies) and need triage.
- **Verification method:** Compare the test count from pytest --collect-only with the count the gate runs. Add a test that parses release_gate.py to assert it invokes pytest.
- **Verification note:** tools/release_gate.py:32 runs only `python -m unittest discover` and prints RELEASE GATE PASSED, with no pytest invocation. There are 563 test_*.py files, 471 of which do not contain the string 'unittest', consistent with the ~475 pytest-only count. No mitigation is visible in the gate.
- **Linked implementation items:** WI-005

### QA-003 — Import validation accepts numeric forms the engine parsers turn into zero, NaN or a silently emptied liabilities list

- **Expert:** quality · **Category:** data-integrity-error-handling · **Severity:** medium · **Confidence:** medium
- **Inspection status:** finding_identified · **Verification status:** partially_confirmed
- **Evidence citations:**
  - `src/csv_exchange/core.py:276-285,320-324` — _is_number / validate — For flat datasets (holdings, liabilities, and so on) a numeric cell is valid if float() accepts it after stripping $ , % and a (...) wrapper. That admits 'nan', 'inf' and accounting negatives like (5,000). No finite-value check, unlike schema_registry.validate_value.
  - `src/schema_registry.py:29-34` — validate_value — WI-401 added a finiteness check for plan rows only. The flat-dataset path was not given the same check.
  - `src/data_io.py:1755-1790` — parse_client liabilities block — _clean_num uses float() with no parenthesis handling. All rows sit inside one try. Any exception sets liabilities = [] with no log or warning, dropping every additional liability (credit cards, student loans, HELOC) for the whole plan.
  - `src/data_io.py:1732-1736` — holdings lot parse — float(shares) has no try. 'nan' passes the 'shares <= 0' skip test because NaN comparisons are False, so a NaN lot is created. '(100)' raises ValueError during plan load.
  - `src/data_io.py:317-324` — _n — Plan-row numbers go through money.decimal_from_user_value, which returns the default (zero) for any InvalidOperation. '(1,234)' therefore becomes 0 silently. Plan rows are separately schema-validated, so this lower-risk path is partly mitigated.
  - `tests/test_architecture_completion_exhaustive_regression.py:76-82` — test_money_boundaries_use_decimal_or_cents_and_execution_copy_is_explicit — The only test of src/money.py is a string-presence check ('Decimal' in the file text). A grep for decimal_from_user_value and cents_from_user_value in tests found no behavioural test.
  - `tests/test_csv_exchange_core_unit.py:93-99` — test_validate_flat_numeric_and_required_cells — The only numeric validation test checks that '$1,000.00' passes. No NaN, inf, parenthesised or garbage case exists.
- **Observed behavior:** The importer's notion of a valid number is wider than the engine's. Read statically, a flat-dataset cell such as (5,000) or nan passes preview and commit. At build time the liabilities block catches the resulting ValueError and discards the entire liabilities list without any signal. A NaN share count flows into a tax lot. No test exercises these boundaries. Nothing was executed, so the exact failure of each form is inferred from reading the code.
- **Impact:** A single malformed liability cell can remove all additional debts from the projection, overstating net worth and cash flow with no warning. A NaN lot corrupts cost-basis and gain calculations. Brokerage and bank exports commonly use parentheses for negatives, so the input is realistic.
- **Affected workflows/scenarios:** CSV import preview and commit; Liabilities and credit-card entry; Holdings lots and tax basis; Plan load and build
- **Root cause:** There are three independent number parsers (validator, data_io._n, per-block float calls) with different grammars. The fail-soft fallback in the liabilities block turns a parse error into an empty list.
- **Options and tradeoffs:**
  1. Create one shared strict parser (finite-only, parenthesis negatives, optional currency and percent symbols), use it in the validator and all data_io blocks, and make a bad cell a reported validation error instead of a default.
  2. Keep the permissive parsers and add logging plus a build warning whenever the liabilities block falls back or a cell is defaulted. Smaller change, but bad data still reaches the engine.
  3. Tighten only the validator (reject nan/inf and parentheses) so invalid cells are stopped at import. This leaves hand-edited plan files and existing stored rows exposed.
- **Recommendation:** Option 1. Whatever is chosen, never swallow the whole liabilities list: report row-level errors and fail loudly or surface a visible warning.
- **Dependencies:** Decide the accepted-number grammar in a single place (src/money.py is the natural home); Product decision on whether parenthesised negatives are valid for balances
- **Implementation considerations:** Check other bare float() parses in data_io (income streams, notes) and the Monarch balances import, which already rejects nan/inf (test_monarch_balances_import_unit.py:51). Add parametrized tests for each form.
- **Risk of change:** Moderate. Existing plans containing values that currently coerce to zero would start raising or warning, and golden fixtures should be unaffected.
- **Verification method:** Parametrized tests that import nan, inf, (5,000) and abc into liabilities and holdings, asserting an error or warning and that no liabilities are lost. A direct unit test of money.decimal_from_user_value.
- **Verification note:** The validator at src/csv_exchange/core.py:274-283 accepts nan, inf and parenthesised numbers. The liabilities block in src/data_io.py:1755-1790 uses float() without parenthesis handling inside one try, and its `except Exception: liabilities = []` silently drops every liability. Both confirmed. The finding overstates the NaN case: a 'nan' balance passes `balance <= 0` and is appended as a NaN row, so it does not empty the list. The lots path float(shares) is unguarded, as claimed. Impact realistic mainly for hand-entered or imported parenthesised cells.
- **Linked implementation items:** WI-008

### QA-004 — Monarch Extractor's deduplication, change detection and event-outbox logic has no behavioural tests

- **Expert:** quality · **Category:** test-coverage-gap · **Severity:** medium · **Confidence:** high
- **Inspection status:** finding_identified · **Verification status:** confirmed
- **Evidence citations:**
  - `Monarch Extractor/monarch_extract.py:96-175,506-690,921-985` — monarch_transaction_id, normalize_transaction, transaction_fingerprint, compare_and_record, mark_run_delivered — 1,424-line script that decides which Monarch transactions count as new or changed. It keeps SQLite state, creates outbox events once per Id+fingerprint, and writes the CSVs the app imports.
  - `Monarch Extractor/monarch_extract.py:1-36` — Top-level imports of playwright and import-time RAW_DIR.mkdir and OUTPUT_DIR.mkdir. Both make the module hard to import in a test without the browser dependency or creating directories beside the script.
  - `Monarch Extractor/monarch_extract.py:322-366` — save_history_csv — History CSV rewritten in place via open('w'), not a temp-file replace.
  - `tests/test_monarch_mark_delivered_unit.py:1-30,60-95` — Writes a stub monarch_extract.py and tests only the app-side command wrapper. A grep of tests/ for compare_and_record, transaction_fingerprint and normalize_transaction finds no extractor test. Only monarch_balances.py is loaded by file path (tests/test_monarch_balances_unit.py:13).
- **Observed behavior:** The app-side consumers of the extractor output (autoimport, field mapping, upsert) are well tested. The producer's id-less-row handling, fingerprint canonicalization, once-only event creation and mark-delivered logic are not.
- **Impact:** A regression there would silently duplicate, drop or re-emit transactions in the YTD spending data that feeds actual-spend tracking and reconciliation. A crash during the non-atomic history write can also truncate the history CSV.
- **Affected workflows/scenarios:** Monarch transaction extraction; Autoimport and reconcile; YTD spending actuals
- **Root cause:** The script is a standalone Playwright tool with import-time side effects and a path containing a space, so it sits outside the normal package import path and was never given a test seam.
- **Options and tradeoffs:**
  1. Move the pure logic (normalize, fingerprint, compare_and_record against a temp SQLite file) behind a function-level seam, make directory creation lazy, and test with tmp_path, loading by file path as test_monarch_balances_unit.py does.
  2. Load the module by file path in tests with a stubbed playwright module and monkeypatched output paths. Quicker, but still leaves import-time side effects.
  3. Accept the gap and rely on the app-side consumer tests. Low cost, but the producer's idempotency stays unverified.
- **Recommendation:** Option 1. Add table-driven tests for id-less rows, a repeated export producing no new events, a changed amount producing exactly one changed event, and mark-delivered; also write the history CSV atomically.
- **Dependencies:** none
- **Implementation considerations:** Keep the Playwright download code unchanged. Only the data-handling functions need tests.
- **Risk of change:** Low, because the changes are mechanical and the logic stays the same.
- **Verification method:** New tests run in the PR tier with no network. Mutation check: flipping the fingerprint input fields should fail a test.
- **Verification note:** A grep of tests/ for compare_and_record and transaction_fingerprint found no test files. The extractor has top-level imports and an import-time RAW_DIR.mkdir at monarch_extract.py:55. The test gap is substantiated. Downstream impact was not traced.
- **Linked implementation items:** WI-011

### UX-001 — Add/delete row actions silently discard unsaved edits on pages labelled 'Saves automatically'

- **Expert:** usability_accessibility · **Category:** workflow-data-loss · **Severity:** medium · **Confidence:** high
- **Inspection status:** finding_identified · **Verification status:** confirmed
- **Evidence citations:**
  - `frontend/js/dashboard_decomp_assets_other.js:104-112, 120-140, 212-218, 226-245` — addOtherAssetItem / deleteOtherAssetItem / addNoteReceivable / deleteNoteReceivable — Each calls the add/delete API and then loadAll() with no prior saveWorkingCopy()/unsaved check; the delete paths also call dirty.clear() explicitly (lines 135, 241).
  - `frontend/js/dashboard_decomp_row_model.js:4852-4927` — loadAll — Re-reads rows from the server and runs dirty.clear() and resets every *Changed flag (line 4927), so any staged field edits are dropped; with silent:true no message is shown.
  - `frontend/js/dashboard_decomp_estate_insurance.js:68-106, 541-567` — addEstateState / addTrustAccount / addInsurancePolicy — Same pattern: API call then loadAll({silent:true}) without saving first.
  - `frontend/js/dashboard_decomp_plan_tiers.js:320, 371, 395` — saveAll(false) guard — Counter-example: the plan-feature actions do check dirty.size and save first, so the safe pattern exists but is not applied to the add/delete actions.
  - `frontend/js/navigation.js:20, 402-412` — AUTOSAVE_STEPS / updateSaveModeBadge — assets_special, estate and annuity_death_benefits are in AUTOSAVE_STEPS, so the header badge tells the user 'Saves automatically' on exactly the pages where these actions discard edits.
- **Observed behavior:** On Other Assets, Notes Receivable, Estate (state/trust add), Insurance (add policy) and similar pages, edits typed into other fields but not yet navigated away from are held only in the in-memory dirty map. Clicking Add/Delete triggers loadAll(), which replaces rows from the database and clears dirty, with no warning or save.
- **Impact:** A user who fills several fields on an autosave-labelled page and then adds a trust, policy, note or asset loses those entries silently and may not notice until a later review. Financial inputs end up missing or stale in the plan.
- **Affected workflows/scenarios:** Other assets / notes receivable entry; Estate: add state or trust; Insurance: add policy; Housing seed rows
- **Root cause:** Per-action add/delete handlers were written independently and rely on loadAll() to refresh; the autosave-on-navigate model only protects navigation clicks, not in-page structural actions. There is no shared 'save-then-mutate' helper.
- **Options and tradeoffs:**
  1. Add a shared helper (e.g. saveBeforeStructuralChange()) that saves dirty rows via saveWorkingCopy() and aborts on failure, and call it from every add/delete/seed handler, mirroring plan_tiers.js.
  2. Make loadAll() preserve and re-apply the dirty map for rows that still exist, so structural actions never drop staged edits.
  3. Prompt with the existing 3-way Save/Discard/Stay modal when dirty.size>0 before any structural action.
- **Recommendation:** Option 1 now (smallest, matches an existing in-repo pattern); consider Option 2 later as a defence-in-depth change inside loadAll().
- **Dependencies:** saveWorkingCopy failure semantics in dashboard_decomp_row_model.js; Server add/delete endpoints must stay idempotent if a save precedes them
- **Implementation considerations:** Inventory every caller of loadAll({silent:true}) that follows an add/delete API (about 15 sites). Saving first can surface validation errors (422) at an unexpected moment; show the existing 'Go to field' error action and abort the structural change.
- **Risk of change:** Low to medium: an extra save before add/delete could fail on partially-entered rows and block adding; needs a clear message.
- **Verification method:** Node frontend tests with the load_dashboard.mjs sandbox: stage a dirty row, invoke each handler with a stubbed api(), assert the save call precedes the mutation and dirty values survive; one Playwright spec: edit a field on Estate, add a trust, confirm the edit persists.
- **Verification note:** Opened assets_other.js: addOtherAssetItem calls the API then loadAll({silent:true}) with no prior save; deleteOtherAssetItem calls dirty.clear(); addEstateState does API-then-loadAll with no save; loadAll re-reads rows and calls dirty.clear() (row_model.js:4927). The 'Saves automatically' badge source (navigation.js AUTOSAVE_STEPS) was not opened by the verifier. The ~15 call sites and the plan_tiers counter-example were not re-checked.
- **Linked implementation items:** WI-018

### UX-002 — 'Cancel Build' is cosmetic: the build continues and the UI later behaves as if it completed

- **Expert:** usability_accessibility · **Category:** workflow-error-handling · **Severity:** medium · **Confidence:** high
- **Inspection status:** finding_identified · **Verification status:** confirmed
- **Evidence citations:**
  - `frontend/js/dashboard_decomp_build_lifecycle.js:123-138` — cancelBuild / buildCancelled — Confirm text says 'The workbook will be left incomplete.' On confirm it sets buildCancelled=true, hides the overlay, shows 'Build cancelled.' It makes no server call and no abort.
  - `frontend/js/dashboard_decomp_build_lifecycle.js:252-300` — buildWithProgress — The progress-polling loop and /api/build/start job never read buildCancelled; there is no cancel request.
  - `frontend/js/dashboard_decomp_row_model.js:5252-5300` — runBuild — After buildWithProgress resolves, runBuild unconditionally records results and calls renderBuildImpactAfterBuild(), navigating the user to Impact & Build History.
  - `frontend/index.html:~45` — #buildOverlay Cancel button — Cancel button is offered on every build overlay, including 'Saving changes' and 'Loading plan' overlays.
- **Observed behavior:** The buildCancelled flag is written once and never read anywhere in frontend/js. Cancelling hides the overlay and says 'Build cancelled', but the server job keeps running and the awaiting runBuild() later completes and navigates to Build Impact, possibly while the user has moved on and started editing.
- **Impact:** The message is untrue. Users may start editing or a second build while the first is still running, and are then pulled to another page unexpectedly. The warning about an incomplete workbook misstates what happens.
- **Affected workflows/scenarios:** Build workbook; Download Workbook (build-then-download)
- **Root cause:** Cancel was implemented as a client-side overlay dismissal only; no server cancellation endpoint was found (searched src/server for 'cancel' near build) and the flag is dead.
- **Options and tradeoffs:**
  1. Implement real cancellation: server job-cancel endpoint, client polling stops, runBuild checks the flag and returns without navigating.
  2. Remove the Cancel button and say 'Build runs in the background; you can keep working', and suppress the auto-navigation if the user has left the page.
  3. Keep the button but relabel to 'Hide' and keep a visible 'build running' status chip until the job ends.
- **Recommendation:** Option 2 or 3 immediately (honest wording, no auto-navigation after hide); Option 1 if cancellation is genuinely wanted and the engine can stop safely.
- **Dependencies:** Server build job lifecycle (src/server build routes); Architect review of job cancellation feasibility
- **Implementation considerations:** Must also handle 'Saving changes' and 'Loading plan' overlays that reuse the same Cancel button. Do not leave the workbook in a half-written state.
- **Risk of change:** Low for wording/auto-navigation changes; medium for true cancellation.
- **Verification method:** Node test: stub buildWithProgress as pending, call cancelBuild(), resolve build, assert no navigation and an accurate message. Existing e2e build-and-results / build-failure specs to be extended.
- **Verification note:** build_lifecycle.js:123-138: cancelBuild only sets buildCancelled, hides the overlay and shows 'Build cancelled.' A grep of frontend/js finds buildCancelled only at the declaration, a comment and that write, so the flag is never read. No server cancel call is made. Whether runBuild later navigates was not reopened by the verifier, but the dead flag and the untrue message are established.
- **Linked implementation items:** WI-019

### UX-004 — Server-side validation failures give no visible field-level feedback and only the first bad field is reachable

- **Expert:** usability_accessibility · **Category:** error-handling · **Severity:** medium · **Confidence:** medium
- **Inspection status:** finding_identified · **Verification status:** partially_confirmed
- **Evidence citations:**
  - `frontend/js/dashboard_decomp_row_model.js:2753-2798` — saveValidationInvalidRows / fieldHtml — Rows rejected by the server are marked aria-invalid="true" only; there is no error text element and aria-describedby points only at Required/unit/inactive notes.
  - `frontend/js/dashboard_decomp_row_model.js:5056-5135` — markSaveValidationErrors / saveAll catch — Errors are mapped back to rows, the toast says 'Error saving: ...' with the raw list inside a collapsed 'Technical details' <pre>, and a single 'Go to <first field>' action.
  - `frontend/css/dashboard.css:3` — .field.missing — Only .field.missing (pale #fecaca border, #fffafa background) has a visual treatment; no CSS targets [aria-invalid] or a save-error state, so server-flagged fields look normal.
  - `frontend/js/dashboard_decomp_row_model.js:4397-4440` — editValue — No client-side check at entry or blur; invalid text in numeric/date fields is only discovered at save.
- **Observed behavior:** After a failed save, sighted users see a toast and one navigation button; the offending controls are not visibly marked and carry no inline message. Remaining invalid fields (if several) must be found by hand or from the raw tuple-formatted list. Entry-time validation is absent.
- **Impact:** Users cannot tell which fields to fix or why. Screen-reader users hear 'invalid' with no reason. Cognitive load and risk of abandoning a save increase on large forms (600+ rows in Field Finder).
- **Affected workflows/scenarios:** Save Changes; Autosave-on-navigate (the failure path leaves the user on the page with a toast); Build (saves first)
- **Root cause:** WI-504 (an earlier review item) delivered aria-invalid plumbing and a single jump link; no visual state, per-field message, error summary, or client-side validation was added.
- **Options and tradeoffs:**
  1. Add a visible invalid style (border + icon + text) and per-field message (from the server's 'message; got value' text) wired via aria-describedby, plus an error summary list with links to every invalid field.
  2. Add lightweight client-side checks (numeric, date, percent range) on blur using schema metadata, with the same message component.
  3. Do only the visual state + 'Next error' button as a minimal step.
- **Recommendation:** Option 1, with Option 2 added for numeric/date kinds already known from valueKind().
- **Dependencies:** Server error string format in src/schema_registry.py validate_rows (not inspected); UX-003 (help/aria-describedby wiring)
- **Implementation considerations:** The regex key parser in rowIndexesForSaveErrors depends on the server's tuple string format; prefer a structured errors array. Error text should not rely on colour alone.
- **Risk of change:** Low.
- **Verification method:** Node test feeding a 422 payload with three errors and asserting three aria-invalid controls each with described-by text and a summary with three links; visual/e2e check of the invalid state.
- **Verification note:** Spot-check only: a grep for aria-invalid in css/*.css returned nothing, supporting the claim that no visual invalid style exists. The row_model.js save-error code was not opened by the verifier, so the toast text, the single 'Go to' action and the missing error text are unverified there.
- **Linked implementation items:** WI-020

### UX-006 — Admin / Control Center has unlabeled editable controls and status messages that assistive technology never announces

- **Expert:** usability_accessibility · **Category:** accessibility-semantics · **Severity:** medium · **Confidence:** high
- **Inspection status:** finding_identified · **Verification status:** confirmed
- **Evidence citations:**
  - `frontend/js/admin.js:1283-1296` — gridControl — Grid <input class="grid-input"> and <select> are emitted with data-row/data-col only: no aria-label, no <label>, no header association.
  - `frontend/js/admin.js:1805` — pricingTestSymbol input — Single-symbol tester input relies on a placeholder as its only name.
  - `frontend/js/admin.js:44, 1302-1315` — msg / markGridChanged — msg() sets textContent of #msg for everything, including 'Unsaved changes...' on every keystroke and error text such as 'Pricing tester error:'; errors and information share one style.
  - `frontend/admin.html:4` — #msg — The #msg element has no role or aria-live attribute; the whole file has one aria attribute.
  - `frontend/js/admin.js:367-372` — clearAppCache — Destructive action uses native confirm().
  - `frontend/css/admin.css:2` — .message,.msg — Status is a fixed pill at top centre that sits over the header controls.
- **Observed behavior:** The advisor-facing configuration grids contain many editable cells with no accessible name, and success, error and unsaved-change messages are not exposed to screen readers. Errors are not visually distinguished from info. Inline onclick buttons and the native confirm() mix with the in-app modal pattern used by the client UI.
- **Impact:** The settings editor (including secrets, pricing mode and reference data) is not operable with a screen reader; mistakes cannot be noticed. This is an advisor/system surface rather than the main client path, which limits but does not remove the impact.
- **Affected workflows/scenarios:** System configuration editing; Pricing refresh and symbol test; Reference-data grids; Clear cache
- **Root cause:** admin.js predates the accessibility work (WI-502/503) done in the client SPA and has no shared message or control helpers with it.
- **Options and tradeoffs:**
  1. Reuse the client SPA helpers (showMessage with role/aria-live, showInAppConfirm) and add aria-label='<column> row <n>' to grid controls.
  2. Minimal pass: add role=status/aria-live to #msg, role=alert for errors, aria-label to grid and symbol inputs.
  3. Retire the generic grid for common files in favour of the client forms.
- **Recommendation:** Option 2 first (small, safe), then Option 1 as consolidation.
- **Dependencies:** admin.js is loaded as a classic script, not an ES module, so helper sharing needs a small bridge
- **Implementation considerations:** Throttle the unsaved-change announcement (do not announce per keystroke).
- **Risk of change:** Low.
- **Verification method:** Add a node/DOM test asserting every .grid-input/.cfg-input has an accessible name and #msg is a live region; manual screen-reader run through Pricing and System Config.
- **Verification note:** admin.html:4 shows <div id='msg' class='message'> with no role or aria-live, and the status text is shown there. The unlabeled grid inputs in admin.js were not reopened by the verifier. Impact is limited because this is an advisor/system surface; the verifier considered low but kept medium.
- **Linked implementation items:** WI-013

### UX-007 — Custom toggle switches have no or very weak keyboard focus indicators

- **Expert:** usability_accessibility · **Category:** accessibility-focus · **Severity:** medium · **Confidence:** medium
- **Inspection status:** finding_identified · **Verification status:** confirmed
- **Evidence citations:**
  - `frontend/css/dashboard.css:1129-1135` — .rg-sw — Roth guardrail switch hides the real checkbox (opacity:0) and has no :focus or :focus-visible rule; off-state track is #9ca3af on a white card.
  - `frontend/js/dashboard_decomp_roth_guardrails.js:195` — rgSwitch markup — <span class="rg-sw"><input type=checkbox aria-label=...><span></span></span> - focus lands on an invisible input.
  - `frontend/css/dashboard.css:982-988` — .toggle-switch / .toggle-switch input:focus-visible+.toggle-track — Used for every Yes/No field; focus ring is 2px #bfdbfe, about 1.4:1 against white.
  - `frontend/css/dashboard.css:3 (.field input:focus), 703` — .field input:focus / .field-info-i:focus — Text inputs use a 2px #bfdbfe outline plus a border colour change; the help badge uses #7dd3fc.
- **Observed behavior:** Keyboard focus on the Roth guardrail switches is not visible. On the standard Yes/No toggles and text inputs the outline is a pale blue with a contrast ratio of roughly 1.4:1 (computed by hand from the hex values; not measured in a browser). The browser default focus ring is untouched on ordinary buttons, which is fine.
- **Impact:** Keyboard users cannot see where focus is on these controls (WCAG 2.4.7; 1.4.11 non-text contrast, 3:1). Roth conversion guardrails are a high-stakes decision area.
- **Affected workflows/scenarios:** Roth guardrails; Any Yes/No plan field; Keyboard data entry
- **Root cause:** Per-component CSS added without a shared focus token; hidden-input switch pattern omitted the sibling :focus-visible rule.
- **Options and tradeoffs:**
  1. Define a single --focus ring token (>=3:1, e.g. 2px accent #1f4f8f with offset) and apply it to all custom controls, including .rg-sw and .rp-switch.
  2. Fix only .rg-sw and darken the existing outline colour.
  3. Adopt a global :focus-visible rule for button, input, select, summary, [tabindex].
- **Recommendation:** Option 3 with the token from Option 1.
- **Dependencies:** none
- **Implementation considerations:** Also lift the off-state track colour above 3:1 and avoid relying on colour alone for on/off (YES/NO text exists on toggle-switch but not on .rg-sw).
- **Risk of change:** Low.
- **Verification method:** Visual check plus an automated contrast calculation script over the focus tokens; Playwright tab-through screenshot of Roth guardrails.
- **Verification note:** dashboard.css:1129-1134 defines .rg-sw with an opacity:0 input and no focus rule; a grep for rg-sw found only those lines. Line 988 shows the toggle-switch focus ring is a 2px #bfdbfe outline, pale on white. The ~1.4:1 figure is a hand estimate not re-derived. The Roth switch has no visible focus at all.
- **Linked implementation items:** WI-014

### ARC-004 — A second, legacy SQLite layer is still live next to the plan/app stores, with stale-data fallbacks and unused tables

- **Expert:** architect · **Category:** persistence-compatibility-layers · **Severity:** low · **Confidence:** medium
- **Inspection status:** finding_identified · **Verification status:** partially_confirmed
- **Evidence citations:**
  - `src/local_store.py:1-12,72-80` — module docstring, init_local_store — Legacy DB local_state/retirement_system_v10.db. The docstring says plan_snapshots tables are no longer written or read and are kept 'until the one-time conversion (WP10)'. Still active for settings, result and KPI snapshots and build events.
  - `src/config_backend.py:1-14,66-100,136-142` — init_sqlite, get_client_file — Declares itself a compatibility layer ('identity/client arguments are ignored'). Creates client_files, audit_events and price_snapshots in the legacy DB. get_client_file still reads client_files.
  - `src/plan_data_read.py:1-50` — read_plan_data_file — Reads the legacy client_files table first and input/*.csv as a fallback. The only non-test importer is financial_trends_reporter/trends_metrics.py; tests/test_no_data_file_io_enforcing_regression.py:26 describes it as the old loader path 'removed with 11.6'.
  - `financial_trends_reporter/trends_metrics.py:36-45,98-114` — _liabilities_csv_total, _plan_rows — If plan.rpx returns no liability rows, or no plan rows at all, it falls back to read_plan_data_file and sums the old client_liabilities.csv from the legacy DB.
  - `src/legacy_conversion/runner.py:215` — stale unlink — The conversion's cleanup is limited to staged scratch files. A search for removal of the legacy DB after conversion found none, and legacy_conversion/backup.py copies it.
  - `src/stores/app_store.py:45-96` — audit_events, price_cache — The current store has its own audit_events and price_cache tables. A search of src/ found no writer for the legacy audit_events table (config_backend.py:72 is its only occurrence). Prices are persisted in two places (portfolio_analytics.snapshot_prices in the legacy DB, market_data in app.db price_cache).
  - `src/reporting/workbook_builder.py:71,1448` — save_kpi_snapshot — Every build still writes KPI snapshots into the legacy DB.
- **Observed behavior:** Two persistence families coexist: stores/ (plan.rpx, app.db) and local_store/config_backend (retirement_system_v10.db). The legacy layer is partly live (KPI/result snapshots, price snapshots and freezes, build events), partly dead (an unused audit_events table, plan_snapshots tables), and partly a read-fallback for the trends reporter. That fallback can return a stale client_liabilities.csv from the legacy DB when the current plan has no liabilities.
- **Impact:** A household that has paid off all liabilities after conversion could see old balances counted in the trends reporter's net worth (stale-data risk; the exact conditions were not reproduced). In general there are two backup and migration surfaces and two places for prices and snapshots, which raises the cost and risk of future schema change.
- **Affected workflows/scenarios:** trends reporter net worth; KPI snapshot comparison; pricing snapshot/freeze; backup/restore; legacy conversion
- **Root cause:** The migration from the legacy DB and CSV bridge to the plan-file model (WP4-WP8) finished for plan data, but not for snapshots and prices, and the compatibility fallbacks were never removed.
- **Assumptions, jurisdiction and rule year:** jurisdiction: n/a; rule year: not stated; assumptions: none stated
- **Options and tradeoffs:**
  1. Move KPI/result snapshots, price snapshots and build events into app.db and the plan file. Then delete the legacy layer after a final conversion window.
  2. Keep the legacy DB but remove the dead tables and the trends-reporter fallbacks (cheap, partial).
  3. Leave as is and document the legacy DB as the owner of snapshots/prices (no code change).
- **Recommendation:** Do option 2 now (remove plan_data_read and the trends fallbacks, drop never-written tables). Plan option 1 as a scheduled migration with forward-only versioning in stores/db.py.
- **Dependencies:** none
- **Implementation considerations:** tests/test_plan_data_read_unit.py and the trends reporter tests pin the old behavior. The legacy conversion (c3 step) must still be able to read client_files. The stale-balance scenario should be reproduced before relying on it.
- **Risk of change:** Low for removing the fallbacks, medium for moving snapshot stores (backups and the retention policy must follow).
- **Verification method:** Convert a legacy fixture, delete all liabilities from the plan, run the trends metrics, and assert the net worth ignores the legacy client_files. Search the code base for remaining DEFAULT_DB users.
- **Verification note:** Confirmed: trends_metrics.py:36-45 and 98-114 fall back to read_plan_data_file (legacy client_files) when plan.rpx returns no liability rows or no plan rows. config_backend.py:72 is the only legacy audit_events occurrence in src (current store has its own at app_store.py:64), and legacy DB paths (DEFAULT_DB) are still live. Not substantiated: the stale-balance scenario, which needs client_files to remain populated after conversion; the conversion was not verified to leave it populated. Severity lowered to low. local_store.py, legacy_conversion and workbook_builder citations were not opened by the verifier.
- **Linked implementation items:** WI-026, WI-038

### ARC-009 — Hosted-mode environment defaults remain, including ALLOW_UNAUTHENTICATED_SAAS=YES

- **Expert:** architect · **Category:** dead-code-configuration · **Severity:** low · **Confidence:** medium
- **Inspection status:** finding_identified · **Verification status:** partially_confirmed
- **Evidence citations:**
  - `src/bootstrap.py:40-48` — _LOCAL_MODE_ENV_DEFAULTS — Sets REQUIRE_API_TOKEN=NO, ALLOW_UNAUTHENTICATED_SAAS=YES, FORCE_HTTPS, REVERSE_PROXY_ENABLED and PUBLIC_BASE_URL via setdefault.
  - `src/server/app_core.py:132,1058-1070` — ProxyFix; _security_gate comments — Comments say the package only ships as LOCAL, yet reverse-proxy header trust is still configured and token-auth is described as removed.
- **Observed behavior:** The variables set defaults for hosted/SaaS behavior that the code comments say no longer exists.
- **Impact:** Misleading configuration surface. If any code path still honors them, an operator who sets or inherits these values could weaken checks. No active reader was confirmed in this pass.
- **Affected workflows/scenarios:** configuration; server mode
- **Root cause:** Incomplete removal of the hosted-mode layer.
- **Assumptions, jurisdiction and rule year:** jurisdiction: n/a; rule year: not stated; assumptions: none stated
- **Options and tradeoffs:**
  1. Delete the unused variables and the ProxyFix wrapper after confirming no readers.
  2. Keep and document them as inert.
  3. Replace them with a single explicit local-only flag.
- **Recommendation:** Option 1 together with ARC-001.
- **Dependencies:** ARC-001
- **Implementation considerations:** grep runtime_config.py and tests for each variable before removal.
- **Risk of change:** Low.
- **Verification method:** Search all readers of the variable names. Run the config tests.
- **Verification note:** Confirmed: bootstrap.py:40-48 sets the five defaults. A grep of src and main.py found no readers of ALLOW_UNAUTHENTICATED_SAAS, REQUIRE_API_TOKEN or PUBLIC_BASE_URL outside bootstrap.py, so they look inert. The finding overstates ProxyFix: app_core.py:131-132 applies it only when RUNTIME_CONFIG.reverse_proxy_enabled is true (default NO). How runtime_config reads the reverse-proxy variable was not checked. Cleanup with low security impact; the dependency on ARC-001 is thematic.
- **Linked implementation items:** WI-006

### DOC-003 — The end-user README names screens and settings that no longer exist and is mostly developer commands

- **Expert:** documentation · **Category:** documentation-accuracy / clarity · **Severity:** low · **Confidence:** medium
- **Inspection status:** finding_identified · **Verification status:** partially_confirmed
- **Evidence citations:**
  - `documentation/reference/readme/README.md:21-36` — Optional features — Tells the reader to go to 'Settings -> Data & Maintenance -> Monarch auto-update' and check 'Enable daily auto-update'. Also points to 'System Configuration -> Pricing mode' (lines 12-18).
  - `frontend/js/dashboard_decomp_monarch_autoupdate.js:1,64` — monarch auto-update card renderer — The card is now headed 'Third-party import auto-update' and the checkbox is 'Enable daily auto-update'. No on-screen text says 'Monarch auto-update' (grep of frontend/ and src/ finds the phrase only in src/ytd_tracking.py:744 and src/monarch_autoupdate.py:3).
  - `frontend/js/dashboard.js:225-232` — STEPS monarch_reconciliation — The new nav page is titled 'Account Reconciliation' (vendor name removed in commit 02a87fb, 2026-10-19). The README (last changed 2026-10-06 in git) does not mention it, nor Rental Properties or backups.
  - `frontend/js/dashboard.js:288-291` — STEPS system_configuration — The settings page is titled 'Data & Maintenance'; 'System Configuration' appears only as 'the raw System Configuration Console', so the README's menu path for Pricing mode is ambiguous.
  - `tests/test_readme_end_user_feature_currency_regression.py:20-27` — FEATURE_MARKERS — The guard pins the string 'Monarch auto-update' in the README, so it would block a plain wording fix unless it is updated at the same time.
  - `documentation/reference/readme/README.md:38-52` — developer section — Developer commands (python main.py, pytest, tools/build_workbook.py) sit in the same file as the end-user instructions, under a 'sections below are for developers' note.
- **Observed behavior:** The README the household receives refers to a feature name and menu path that the app no longer shows, names no way to find the Concepts Guide, and gives only a few lines about what the app does. The one regression test guarding it enforces the old name.
- **Impact:** A non-expert following the steps cannot find the control on screen. A short README is the first document a 60-year-old reader sees, and it currently mixes user and developer content.
- **Affected workflows/scenarios:** First-run orientation; Turning on daily import; Choosing pricing mode / privacy
- **Root cause:** Item 359 renamed the UI text but the README and its currency test were not part of the change; the test checks for a keyword rather than for matching UI labels.
- **Options and tradeoffs:**
  1. Rewrite the optional-features text to use the current on-screen names, split developer commands into CONTRIBUTING.md, and update the test markers.
  2. Make the README generic ('daily import of transactions and balances') and have the test read the card title from the frontend source.
  3. Only patch the two stale phrases.
- **Recommendation:** Option 1 with a test that compares README menu names against titles in dashboard.js; add a three-line 'what the app does / where to start / where the guide is' opening.
- **Dependencies:** DOC-004
- **Implementation considerations:** Wording must stay consistent with the vendor-neutral rename in item 359; confirm whether the vendor name is intentionally hidden from users before reintroducing it.
- **Risk of change:** Low.
- **Verification method:** Walk each README instruction in the running app; run the README currency test.
- **Verification note:** README lines 23-25 do say 'Monarch auto-update' and 'Settings -> Data & Maintenance', and the test pins that string. The frontend card text was not opened by the verifier, so the claim that the UI no longer shows that name is unverified there. Mixed developer content is plausible; the 'First-run orientation' impact is overstated. Lowered to low.
- **Linked implementation items:** WI-017

### DOC-004 — The plain-language Concepts Guide is not linked from the index, README or app, and has accessibility and layout defects

- **Expert:** documentation · **Category:** discoverability / clarity · **Severity:** low · **Confidence:** medium
- **Inspection status:** finding_identified · **Verification status:** confirmed
- **Evidence citations:**
  - `documentation/reference/Retirement_Planner_Concepts_Guide.docx:word/document.xml (whole)` — Concepts Guide — Opened as a zip and extracted text. About 7,400 words, written for non-experts ('A plain-English guide...', everyday comparisons, 'Works with' and 'Find it' lines, acronym appendix). Contents page shows only the instruction 'If the list above is empty, right-click it in Word and choose Update Field'. The package has 7 embedded figures and none carries alternative text (no descr attribute in any docPr).
  - `documentation/DOCUMENTATION_INDEX.md:8-28` — reference table — The reference table lists README, CLAUDE.md, specs and runbooks but not the Concepts Guide, RENTAL_TAX_RULES.md, CAPITAL_GAINS_IN_AGI.md or WP11_REACHABILITY.md.
  - `documentation/reference/readme/README.md:1-52` — whole file — No mention of the guide. A repo-wide grep for 'Concepts_Guide' / 'Concepts Guide' across md, py, js and html returns no match.
  - `documentation/reference/Retirement_Planner_Concepts_Guide.docx:word/document.xml (entries)` — 'Find it' lines — 104 entries end with raw field keys such as 'member_N_dob', 'inflation_general', 'monthly_401k_contribution'. The guide's own How-to-use text says these show 'the screen and field name', but a user looking at the screen sees labels, not keys. The appendix also repeats 'Credit-Shelter Trust' as two entries.
- **Observed behavior:** The only document written at a lay reading level is stored as a binary .docx in the reference folder, with no pointer from any place a user would look, an empty table of contents until manually refreshed, no alt text on figures, and internal field keys in the 'Find it' lines.
- **Impact:** The household and any advisor reading cannot discover it. If they open it, the contents list looks broken, a screen-reader user gets no figure descriptions, and 'Find it' sends them to a key name rather than a visible label.
- **Affected workflows/scenarios:** Learning what a setting means; Screen-reader access to the guide; Onboarding a non-expert
- **Root cause:** The guide was added on 2026-10-19 as a stand-alone file without updating the index or README, and the generated docx was saved without field updates or figure descriptions.
- **Assumptions, jurisdiction and rule year:** jurisdiction: not stated; rule year: not stated; assumptions: Findings about the guide come from the extracted XML and text only; the document was not rendered in Word.
- **Options and tradeoffs:**
  1. Link the guide from README, DOCUMENTATION_INDEX and a Help entry in the app; refresh the TOC field, add alt text and replace field keys with on-screen labels.
  2. Keep the .docx but also generate an HTML or Markdown version for in-app help so it can be searched.
  3. Link only (no content edits).
- **Recommendation:** Option 1 now; consider option 2 later. Do the content fixes in the same pass so the first link goes to a polished file.
- **Dependencies:** DOC-003
- **Implementation considerations:** Check whether tools/build_release_package.py bundles documentation/reference (not inspected). The guide's rates are marked illustrative; keep them out of date-sensitive prose.
- **Risk of change:** Low.
- **Verification method:** Open the docx in Word and confirm the TOC populates and figures have alt text. Confirm the link works from the README and the app.
- **Verification note:** Grep finds no 'Concepts_Guide' reference in md, py, js or html files, and the index has no entry for it. The docx has docPr elements and zero descr= attributes, so no alt text. The TOC emptiness and the 104 field-key entries were not verified. Discoverability and accessibility of a supplementary file, so low.
- **Linked implementation items:** WI-017

### DOC-005 — Reference documents state facts the code no longer matches (file sizes, nav inventory, removed JSON metadata file)

- **Expert:** documentation · **Category:** documentation-accuracy · **Severity:** low · **Confidence:** high
- **Inspection status:** finding_identified · **Verification status:** partially_confirmed
- **Evidence citations:**
  - `documentation/reference/CLAUDE.md:246` — Frontend section — Says dashboard.js is '~16,700 lines, heavily minified'. frontend/js/dashboard.js is 6,883 lines (wc -l) and about 40 dashboard_decomp_*.js files exist beside it.
  - `documentation/reference/CURRENT_SYSTEM_DESIGN_SPEC.md:484-490` — 7.2 — Says dashboard.js is 'still ~7,500 lines', '~30 dashboard_decomp files' and '~35 guided steps'; the STEPS array runs lines 14-296 of dashboard.js. Two living docs disagree with each other and with the code.
  - `documentation/reference/NAV_FEATURE_MAP.md:7,17-18` — How the left nav works — Cites STEPS at 'lines 5-515' (actual 14-296) and says module toggles live in client_optional_functions.csv and plan flags in client_assets.csv/client_policy.csv, though release notes 2026-10-wp11-file-elimination.md say runtime no longer reads those files.
  - `documentation/reference/NAV_FEATURE_MAP.md:67-100` — Detailed table / totals — The nav page 'Account Reconciliation' (id monarch_reconciliation, group Reports & Review, frontend/js/dashboard.js:225-232) is absent from the table, the 'everything enabled' list and the page totals ('26 pages').
  - `documentation/reference/PLAN_METADATA_SCHEMA.md:1-22` — whole file — Documents plan_metadata.json 'located in input/ alongside plan CSV files'. Searching src/ and tools/ for 'plan_metadata' finds no code that reads or writes it; only documentation mentions it. The index lists it as 'Plan data schema'.
  - `documentation/reference/CLAUDE.md:130-133` — Flat datasets — Lists liabilities as 'auto / HELOC / student-loan debts', but the recent merge (#216, 'Add Credit card liability type') adds a credit card type, which this section omits.
- **Observed behavior:** The folder rule says reference/ 'must be true today', yet several files in it contain numbers, locations or whole subjects that are out of date. Two of them disagree with each other on the same fact.
- **Impact:** Developers (and AI sessions, which CLAUDE.md is written for) are given wrong sizes and file locations, and anyone using NAV_FEATURE_MAP.md to understand the left menu misses a visible page. A non-existent metadata file schema invites someone to build against it.
- **Affected workflows/scenarios:** Maintainer orientation; AI-assisted development sessions; Reviewing the left navigation
- **Root cause:** These facts are hand-written; only the architecture diagram has a staleness test. File-size and inventory facts were not added to that check.
- **GitHub contextual evidence:** pull_request #216 (contextual_only)
- **Options and tradeoffs:**
  1. Correct each fact now and replace hard line counts with qualitative wording ('several thousand lines, split into dashboard_decomp_*.js').
  2. Generate the nav map and the step list from STEPS with a tool, as is done for the architecture diagram, and fail a test when stale.
  3. Archive PLAN_METADATA_SCHEMA.md (confirm first it is obsolete) and remove it from the index.
- **Recommendation:** Option 1 plus archiving PLAN_METADATA_SCHEMA.md; generate the nav map (option 2) as a follow-up.
- **Dependencies:** DOC-001
- **Implementation considerations:** Confirm PLAN_METADATA_SCHEMA.md is unused outside src/ and tools/ (the legacy converter may read plan_metadata.json; src and tools were searched, which includes src/legacy_conversion). tests/test_legacy_data_migration_regression.py mentions plan_metadata (see QA-006). Keep the index in sync.
- **Risk of change:** Low.
- **Verification method:** Re-run the line-count and STEPS checks and compare to the text; run the path-citation test after any move.
- **Verification note:** Confirmed: CLAUDE.md:246 says '~16,700 lines' against 6,883 actual. NAV_FEATURE_MAP.md:7 cites STEPS 'lines 5-515'. The monarch_reconciliation page is absent from the NAV map. PLAN_METADATA_SCHEMA.md has no readers in src or tools, but tests/test_legacy_data_migration_regression.py mentions plan_metadata, so 'obsolete' is not proven. The CURRENT_SYSTEM_DESIGN_SPEC numbers and the credit-card claim were not verified. Lowered to low.
- **Linked implementation items:** WI-016

### DOC-006 — Release notes omit the October engine changes that move results, and their index lists only three of four notes

- **Expert:** documentation · **Category:** documentation-completeness · **Severity:** low · **Confidence:** medium
- **Inspection status:** finding_identified · **Verification status:** partially_confirmed
- **Evidence citations:**
  - `documentation/reference/release_notes/index.md:1-21` — Entries — Describes the folder as 'versioned release notes' (citing example v11.0.0.md) and lists three notes; 2026-10-wp11-file-elimination.md is in the folder but not listed.
  - `documentation/reference/GOLDEN_MASTER_CHANGELOG.md:1-12` — 2026-10-19 entry — Records that the senior bonus deduction was lost for itemizers and is now included, moving terminal NW and lifetime tax. This is in the developer changelog only.
  - `documentation/reference/CAPITAL_GAINS_IN_AGI.md:1-12` — H1 — Sale gains now flow into AGI, NIIT MAGI and IRMAA MAGI (home and rental sales only; see FIN-001); this is documented only in a technical design note with statute citations.
  - `src/projection_stages/deterministic_engine.py:1236-1240` — sale_gain_in_agi — Confirms the sale gain is added to AGI and IRMAA MAGI in the engine.
  - `documentation/reference/release_notes/2026-09-changes-334-339.md:1-10` — header — This is the only release note that covers results-moving changes (IRMAA indexing, one-time Large Discretionary); no note covers the H1-H6 Tier 3 work or 363p.
- **Observed behavior:** The 'plain-language record of changes that move results' folder has no note for the October H1 (sale gains in AGI/IRMAA/NIIT), the senior-bonus-for-itemizers fix, or the rest of the Tier 3 work (H3 reversion, H4 owner split, H5 death handling, H6 rent then sell). The H3-H6 code was not opened.
- **Impact:** A household that saw its numbers change after an update has no readable explanation. The index also gives no way to reach the file-elimination note.
- **Affected workflows/scenarios:** Understanding why projections changed; Advisor review after an upgrade
- **Root cause:** Result-moving changes are recorded in the golden-master changelog and design notes by habit; there is no rule linking a golden or engine change to a release note.
- **GitHub contextual evidence:** pull_request #207 (contextual_only); pull_request #208 (contextual_only); pull_request #209 (contextual_only)
- **Options and tradeoffs:**
  1. Write a short plain-language note for the October engine changes and add the missing index entry.
  2. Add a checklist item in CONTRIBUTING.md that any golden-master change needs a release note, enforced by a test that compares changelog dates to release-note dates.
  3. Point the release-notes index at the golden-master changelog and accept the technical wording.
- **Recommendation:** Option 1 now; consider option 2 afterwards. Write the notes after the tax-correctness changes (FIN-001, FIN-003) land so the plain-language text is not immediately stale.
- **Dependencies:** FIN-001; FIN-003
- **Implementation considerations:** The financial planner should confirm the plain-language statements of the tax changes. Verify H3-H6 content in the merged PRs before writing.
- **Risk of change:** Low.
- **Verification method:** Index lists every file in the folder; each golden-master entry since 2026-09 maps to a note or an explicit 'no user-visible change'.
- **Verification note:** The release_notes index lists three notes and omits 2026-10-wp11-file-elimination.md, which is in the folder (confirmed). The folder has no mention of H1, sale gain or senior bonus. The golden-master changelog has a 2026-10-19 entry that moved the pins. That the senior-bonus change is the cause, and the H3-H6 content, were not verified, so 'omit changes that move results' is only partly established. The changelog already records them for developers. Lowered to low.
- **Linked implementation items:** WI-017, WI-032

### DOC-007 — Input-folder READMEs describe a CSV-file workflow the runtime no longer uses

- **Expert:** documentation · **Category:** documentation-accuracy · **Severity:** low · **Confidence:** medium
- **Inspection status:** finding_identified · **Verification status:** partially_confirmed
- **Evidence citations:**
  - `input/README_INPUT_PACKAGE.md:1-8` — whole file — Says to extract the zip and 'select or copy the desired Plan Data folder through the UI/server configuration'.
  - `input/README_YTD_INPUTS.md:1-12` — whole file — Tells the reader to use ytd_account_setup.csv and client_holdings.csv files and states a fixed header.
  - `documentation/reference/release_notes/2026-10-wp11-file-elimination.md:1-30` — What changed — States plan data lives in the plan file, the runtime does not read input/*.csv plan files apart from two fallbacks, and CSV is import/export only.
  - `frontend/js/admin.js:1956` — Local-only package text — On-screen text still says 'edit the single local Plan Data folder'.
- **Observed behavior:** These notes and one admin screen text still describe a Plan Data folder of CSV files as the working data store.
- **Impact:** A reader may edit CSVs in input/ expecting the app to pick up the change; the app will not.
- **Affected workflows/scenarios:** Preparing data to import; Reading the admin page
- **Root cause:** WP11 changed storage but these notes and one string were left.
- **Options and tradeoffs:**
  1. Rewrite the notes as 'import/export file formats' and update the admin text.
  2. Delete the notes and point to PLAN_ROWS_MODEL.md and the import screen help.
  3. Leave them with a banner saying 'legacy'.
- **Recommendation:** Option 1.
- **Dependencies:** DOC-005
- **Implementation considerations:** input/README_YTD_INPUTS.md may still be accurate for the YTD CSV import column format; check src/ytd_tracking.py before deleting.
- **Risk of change:** Low.
- **Verification method:** Follow each instruction in the running app.
- **Verification note:** frontend/js/admin.js:1956 does say 'edit the single local Plan Data folder' (confirmed). The input/README files were not opened by the verifier and the wp11 note was not read in full. README_YTD_INPUTS may still be valid for the import format, as the finding concedes.
- **Linked implementation items:** WI-013, WI-017

### FIN-002 — Monte Carlo headline success rate has no measured error bound for the shipped default Roth policy, and the KPI tile shows two figures that answer different questions

- **Expert:** financial_planner · **Category:** monte-carlo-model-risk · **Severity:** low · **Confidence:** medium
- **Inspection status:** finding_identified · **Verification status:** partially_confirmed
- **Evidence citations:**
  - `src/planning_engines.py:6560-6578` — monte_carlo — The default mc_engine_mode is 'vectorized_batched'. The exact scalar engine is only an opt-in oracle.
  - `src/planning_engines.py:6654` — monte_carlo -> _mc_vectorized_batch — The headline call passes allocation='replay' and tier_shadow=True. The tier-bucket cascade therefore runs as a shadow, not as the headline allocation. (Opened in the planner re-verification.)
  - `src/planning_engines.py:6228` — _mc_vectorized_sensitivity_success_rate — The sensitivity helper also uses allocation='replay'. The 'tier' default at 5414 (_mc_vectorized_projection signature) applies only to direct callers.
  - `src/planning_engines.py:5612-5617` — _mc_vectorized_projection other_nominal — On the tier path the tax/other funding need is max(0, sum(account withdrawals) - sum(spend_by_tier)); the diagnostic measured it at exactly zero in every year. This describes the pre-fix tier path, which is now the shadow, not the headline.
  - `documentation/archive/reports/N1_MC_PARITY_RESIDUAL_DIAGNOSTIC_2026-09-30.md:10-18 (section 1 table)` — headline gaps — Paired-path gap, vectorized minus scalar, on the tier path: +17.3 to +18.0pp under roth_policy=none and -5.0 to -6.4pp under roth_policy=fill_to_bracket (the table labels this 'default'). Both are signed gaps of the superseded tier-allocation path.
  - `documentation/archive/reports/N1_MC_PARITY_RESIDUAL_DIAGNOSTIC_2026-09-30.md:64-68, 111 (section 3.3, section 6)` — definitional difference; other policies not run — Section 3.3: the Roth/tier-bucket difference is 'a definitional difference in what "success" means, not an approximation error'; the owner must choose between 'funded as asked' and 'funded within tier buckets'. Section 6: the default-regime numbers use roth_policy fill_to_bracket and 'other policies were not run'.
  - `documentation/archive/reports/N1_MC_PARITY_RESIDUAL_DIAGNOSTIC_2026-09-30.md:112-125 (section 7)` — addendum - fix shipped — Records that the headline now uses allocation='replay' (owner-approved direction 'funded as asked'), credit-shelter sequestration was added, and the tier cascade is kept as a shadow that supplies success_rate_within_tier_policy. Post-fix figures: none 0.650 vs scalar 0.611; default 0.675 vs 0.675; paired agreement 95.5-100%. Not independently verified here.
  - `src/parsing/roth_conversion_policy.py:59-62` — roth_policy default — The shipped default for roth_conversion_policy is 'optimize_terminal_tax', not fill_to_bracket.
  - `src/taxes.py:450` — ROTH_POLICIES — The policy list starts with optimize_terminal_tax and also contains fill_to_bracket and none, so the three regimes are all reachable and only two were measured.
  - `src/planning_engines.py:6765-6777` — monte_carlo result keys — Emits a headline definition ('funded as asked: any account, including Roth as a last resort, may fund any spending') and a second figure, success_rate_within_tier_policy, with its own definition string marked approximate.
  - `frontend/js/dashboard_decomp_home_panels.js:28-55` — successLabel / mc_approximation_status / mc_success_within_tier_policy — The KPI tile appends '(+/-{tol}pp)' or '(approximate)' to the headline and, unless a spending policy is active, a second figure '(without using Roth for extras: X)' with an 'Approximate' tooltip. The tolerance comes from one fixture and one policy. Runtime values of mc_approximation_status were not read.
  - `documentation/reference/BACKLOG.md:16-18` — QA-006 row — The success-rate level bias is deferred as not in flight. The widened 10pp drift gate is the only control.
  - `tests/test_scalar_vectorized_paired_path_agreement_regression.py:1-30,100-125` — pytestmark nightly (absorbed from ARC-002) — Parity is pinned only as a nightly test on one frozen sample plan (documented 95.5-100% path agreement, +/-3.5pp gap; floors 0.90 and 0.06).
  - `tests/test_scalar_vectorized_survivor_reconciliation.py:100-128` — test_success_rate_agrees_within_loose_sanity_bound (absorbed from ARC-002) — Acceptance bound max(0.20, 10xSE); comment says full parity 'was never promised'.
- **Observed behavior:** The headline probability of success comes from the vectorized engine, whose headline allocation is now 'replay' with the tier-bucket cascade kept as a shadow (planning_engines.py:6654). The tile shows the headline (funded as asked, Roth as a last resort) with a '+/-tol pp' or 'approximate' label, plus a second 'without using Roth for extras' figure that answers a different question. The archived diagnostic's signed gaps (+17 to +18pp under roth_policy=none, -5 to -6pp under roth_policy=fill_to_bracket) were measured on the superseded tier path; its own addendum reports 0.650 vs 0.611 (none) and 0.675 vs 0.675 (fill_to_bracket) after the change, unverified here. The shipped default policy, optimize_terminal_tax, was not measured under either allocation. The same engine drives the sustainable-spending solve and the 81-point Social Security claim-age sweep. Parity is guarded only by nightly or loose tests (merged from ARC-002).
- **Impact:** The +17pp and -26pp figures in the archived diagnostic describe the tier path and no longer describe the headline, so they overstate the current exposure. Residual exposure: (i) the shipped default regime has no measured gap; (ii) the '+/-tol' label comes from one fixture and one policy and may not hold elsewhere; (iii) the secondary figure keeps the tier engine's known approximations and is a different question from 'will the money last', so a reader may compare two numbers that are not comparable; (iv) parity depends on a nightly-only test, and the post-fix agreement figures are the diagnostic authors' own. Any engine change must still be made in two or three places that stay in step.
- **Affected workflows/scenarios:** Monte Carlo success probability KPI; Sustainable spending solve; Social Security claim-age sweep; Strategy sweeps that call monte_carlo repeatedly; Advisor model-risk rating; Stress and sensitivity grid
- **Root cause:** The vectorized engine is a parallel implementation rather than a vectorized form of shared kernels, so correctness depends on empirical parity tests. The tier policy that bars Roth from important and discretionary spending is an owner-approved product definition of success ('funded within tier buckets'); the diagnostic calls the difference from the scalar 'funded as asked' meaning definitional, not an approximation error, so it is a metric-definition choice and not a bias to be removed. The earlier approximation errors (tax funding need, HSA order, no credit-shelter sequestration) were addressed by the replay allocation per the diagnostic addendum.
- **Assumptions, jurisdiction and rule year:** jurisdiction: Not jurisdiction-specific; rule year: unknown; assumptions: Modeling approximation and a metric-definition choice, not a legal rule. Parity figures come from the repository's own archived diagnostic; I did not re-run anything. Code behavior was confirmed by reading it. In the diagnostic the regime labelled 'default' is roth_policy=fill_to_bracket; the shipped parse default is optimize_terminal_tax (src/parsing/roth_conversion_policy.py:59-62; src/taxes.py:450) and that regime was never measured. The diagnostic (section 3.3) calls the Roth/tier-bucket difference 'a definitional difference in what success means, not an approximation error', so it is not a bias to remove. The post-fix paired figures in the diagnostic's section 7 are the diagnostic authors' and were not independently verified. Whether the displayed headline matches the diagnostic's 'shipping engine' success definition, before or after the replay change, was not confirmed. The disclosed tolerance and the sign-off came from the owner and planner. Qualified review applies to the headline 'probability plan is fully funded' claim.
- **Options and tradeoffs:**
  1. Measure and label (recommended): verify the shipped replay headline in the paired-path harness under none, fill_to_bracket and the shipped default optimize_terminal_tax; tie the tolerance label to a measured regime; label the headline and the secondary figure each with its own success definition. Low risk.
  2. Make the exact scalar engine the engine of record for any displayed headline success rate and keep vectorized for sweeps, with a fast scalar for the single headline run. Slower, removes the parity question for the headline.
  3. Repair the replay path further, or share kernels with the deterministic engine, only if the measurement in option 1 shows a gap beyond the disclosed tolerance; the owner decides which success definition is the headline (funded as asked, as the addendum records, or within tier buckets) and whether the secondary figure stays on the tile.
- **Recommendation:** Do option 1: put the per-figure disclosure and the measurement of all three regimes, including the unmeasured shipped default, first (WI-009), then verify and broaden the paired-path fixtures into the default test tier (WI-036). Do not propose the replay skeleton as future work; the headline already uses it (planning_engines.py:6654) and the diagnostic addendum says so. Confirm the owner's 'funded as asked' direction and the fate of the secondary figure in WI-002(d). Pursue option 3 only if measured. Refactoring to shared kernels (ARC-002 option 3) is a longer-term investment tied to ARC-005.
- **Dependencies:** Owner decision on which success definition is the headline and whether the secondary within-tier figure stays on the tile (diagnostic sections 3.3 and 7); FIN-001, because MAGI changes shift cascade draws; ARC-005 (kernel sharing)
- **Implementation considerations:** The paired-path test harness already exists (tests/test_scalar_vectorized_paired_path_agreement_regression.py) and is the right gate. Keep the signed gap, not just the absolute, in the disclosure. Scalar runs are slow; use small N with paired paths. Any change to bounds interacts with the golden-master pins. Documents disagree on the bias direction (BACKLOG.md says optimistic, the test narrative says pessimistic by 4-6pp). The diagnostic's pre-fix per-regime figures describe the superseded tier path; its section 7 post-fix figures are the authors' and unverified here; the shipped default optimize_terminal_tax is unmeasured, so all three regimes need re-measurement on the replay path, and the secondary figure on the tier shadow. The git history of src/planning_engines.py is a single squashed commit, so it cannot show whether the file changed after the diagnostic; the code itself shows the replay headline.
- **Risk of change:** Low for measurement, fixtures and labelling (option 1). High for any further repair of the replay path (option 3): headline MC outputs, sustainable-spend and claim-age sweep results would change.
- **Verification method:** Run the paired-path harness (n>=1000, several seeds, 4+ household shapes) under roth_policy none, fill_to_bracket and optimize_terminal_tax on the post-replay headline path, and separately on the tier shadow for the secondary figure; require |signed gap| within the disclosed tolerance in each regime. Add a test that fails if the label claims a tolerance not measured for the active policy, and a diagnostic field for the scalar/vectorized gap. These are static recommendations; no run was executed in this review.
- **Verification note:** Original verification: the archived N1 diagnostic section 1 table shows signed gaps of +17.3 to +18.0pp for roth_policy=none and -5.0 to -6.4pp for roth_policy=fill_to_bracket (labelled 'default'), and planning_engines.py:5612-5617 matches the diagnostic's other_nominal description. Planner re-verification (PC-1, partially upheld): (a) the shipped default is optimize_terminal_tax (roth_conversion_policy.py:59-62; taxes.py:450) and was never measured (diagnostic line 111); (b) the Roth/tier-bucket difference is definitional (diagnostic line 68); (c) a second figure, success_rate_within_tier_policy, is emitted (planning_engines.py:6765-6777) and shown on the tile (dashboard_decomp_home_panels.js:28-55); (d) the proposed claim that the diagnostic is 'probably still representative' was rejected: diagnostic section 7 (lines 112-125) and planning_engines.py:6654 and 6228 show the headline moved to allocation='replay' after the measured gaps, and the git log for the file is one squashed commit (d171d0b) so it cannot date content. Severity lowered from medium to low and status from confirmed to partially_confirmed; the planner has not confirmed the lower severity (section 14, dissent). Not confirmed: whether the displayed headline matches the diagnostic's 'shipping engine' definition before or after replay; no test or measurement was run.
- **Linked implementation items:** WI-002, WI-009, WI-036

### FIN-004 — No 10% additional tax (or any age gate/warning) for pre-59.5 retirement-account distributions in early-retirement scenarios

- **Expert:** financial_planner · **Category:** domain-scope-gap · **Severity:** low · **Confidence:** medium
- **Inspection status:** finding_identified · **Verification status:** partially_confirmed
- **Evidence citations:**
  - `src/planning_engines.py:1411-1470` — withdraw_pretax_elective — Pre-tax draws are constrained only by the gap, bracket/IRMAA caps and reserve. There is no owner-age parameter or penalty.
  - `src/planning_engines.py:1120-1136` — withdraw_hsa_window (penalty) — The engine does model a 20% pre-65 HSA penalty and fails closed on a missing age, which shows the pattern was considered for HSAs but not IRAs/401(k)s.
  - `src/server_services/build_service.py:89-200` — build_preflight_payload — The preflight warns about missing required fields and IRMAA history. It has no early-retirement or pre-59.5 distribution check.
  - `src/projection_stages/withdrawal_cascade_ira_true_up.py` — (whole module) — A grep for age variables in withdrawal_cascade_*.py returned nothing, so no cascade stage gates IRA draws on owner age.
- **Observed behavior:** A plan with a retirement year at 50-58 can fund spending from IRA/401(k) balances with no 10% additional tax, no exception handling, and no warning. The same applies to Roth conversion principal and earnings withdrawn early.
- **Impact:** Early-retirement plans understate tax and overstate sustainability by up to 10% of early pre-tax draws, and the Roth-conversion and bridge strategies look better than they are. The effect is limited to households that start pre-tax draws before 59.5. Note the verifier found existing frontend help text (dashboard.js:5803/5808) and a Roth modeling guide that already mention early-withdrawal penalties, so 'no warning anywhere' is overstated.
- **Affected workflows/scenarios:** Early-retirement scenarios; ACA bridge planning; Withdrawal sequencing; Roth conversion ladders
- **Root cause:** Account-level age/eligibility rules are not part of the withdrawal model, and the preflight does not check for them.
- **Assumptions, jurisdiction and rule year:** jurisdiction: US federal (IRC 72(t) and exceptions); rule year: Statutory and not year-specific; assumptions: The product models pre-65 ACA bridge years, so retiring before 65 is in scope. Whether the product also covers retiring before 59.5 is not declared. This is therefore classified as a potential scope/workflow gap, not a calculation defect. The exceptions (age 55 separation from service, 72(t) SEPP, Roth contribution basis) need professional review. Authority: statutory (IRC 72(t)), not fetched in this run; classify as unverified.
- **Options and tradeoffs:**
  1. Add an early-distribution warning to the preflight and results (low effort, no calculation change).
  2. Model the 10% additional tax on pre-tax draws before 59.5, with an owner-selected exception flag (Rule of 55 or 72(t)), and treat Roth principal ordering.
  3. Declare early retirement before 59.5 out of scope in the Functional Spec, and block or warn at plan build.
- **Recommendation:** Do option 1 now. Decide scope explicitly, and implement option 2 if early retirement before 59.5 is supported.
- **Dependencies:** Product scope decision
- **Implementation considerations:** The account registry carries owner_idx and ages are available in the stage. Exceptions are household-specific, so a per-owner flag is required.
- **Risk of change:** Low for the warning. Medium for the tax change, which affects early-retirement goldens only.
- **Verification method:** Unit test: owner age 55, IRA draw of 40k, no exception, should produce a 4k additional tax in the year. Preflight test: retirement year before the 59.5 year should emit a warning.
- **Verification note:** A grep of src for 59.5, 72(t) and early-distribution logic, and of the withdrawal cascade stages, found no age-gated 10% additional tax on pre-tax draws, so the absence is plausible. It is a scope gap, not a defect, because scope for retiring before 59.5 is undeclared. planning_engines.py:1411-1470, 1120-1136 and build_service.py were not opened by the verifier. Severity lowered to low until scope is decided. Planner sign-off (PC-3): the option 1 warning moves to WI-010a as a no-calculation notice with scope-neutral wording, valid whichever way WI-002(a) is decided.
- **Linked implementation items:** WI-002, WI-010a

### FIN-005 — AMT computation uses 2025 phase-out thresholds and a 25% rate indefinitely, ignoring the post-2025 OBBBA changes

- **Expert:** financial_planner · **Category:** tax-rule-currency · **Severity:** low · **Confidence:** medium
- **Inspection status:** requires_external_domain_verification · **Verification status:** partially_confirmed
- **Evidence citations:**
  - `src/core.py:1195-1200` — AMT_PHASEOUT_START_BASE / AMT_EXEMPTION_BASE — 2025 amounts (MFJ phase-out start 1,252,700, single 626,350), hard-coded and indexed forward by brk_inf.
  - `src/core.py:1216-1233` — tentative_minimum_tax — The exemption is reduced by 0.25 x excess AMTI over the phase-out start in every year. There is no year-dependent rate or threshold.
  - `src/core.py:1236-1252` — amt_tax — The docstring and comment state that the engine calls this only for households that enable equity compensation and hold ISOs.
- **Observed behavior:** For plan years 2026 onward the code's exemption phase-out starts at about $1.25M (MFJ) and removes 25 cents per dollar. If current law starts at $1M (MFJ) and removes 50 cents per dollar, as the expert recalls (unverified), the code is stale for 2026 onward.
- **Impact:** For ISO-exercise years with AMTI above about $1M (MFJ) or $0.5M (single), the exemption is overstated and AMT is understated. The difference can be tens of thousands of dollars in an exercise year. The module is optional and the exposure is narrow.
- **Affected workflows/scenarios:** Equity compensation (ISO) AMT true-up; AMT minimum-tax credit carryforward
- **Root cause:** Statutory AMT parameters live in code as base-year constants, not in the dated tax-law dataset, so the annual maintenance process does not cover them and the 2025 act's change was missed.
- **Assumptions, jurisdiction and rule year:** jurisdiction: US federal (IRC 55, as amended by the 2025 reconciliation act, P.L. 119-21); rule year: 2026 onward. The code uses 2025 figures.; assumptions: From the expert's own knowledge (not fetched from primary sources in this run), the 2025 act lowered the exemption phase-out thresholds for tax years after 2025 to $500,000 (single) and $1,000,000 (joint), and raised the phase-out rate from 25% to 50%. These must be verified against Rev. Proc. 2025-32 and the statute. The figures are hard-coded in core.py with no dataset rows. Professional review is required, since the module drives ISO strategies. Authority class: unverified (expert recollection); rule status: hard-coded base-year constants, not dataset rows.
- **Options and tradeoffs:**
  1. Move AMT exemption, phase-out start, phase-out rate and rate-break into dated rows in tax_law_v10.json (effective_year keyed) and read them via tax_law.
  2. Hard-code a year switch at 2026 for the threshold/rate. This is quicker but repeats the same maintenance gap.
  3. Disable the AMT estimate outside verified years and show a limitation notice.
- **Recommendation:** Option 1, after verifying the 2026 values against the Rev. Proc. and statute. Add AMT to the annual-maintenance runbook family list.
- **Dependencies:** External verification of rule values (CPA)
- **Implementation considerations:** tentative_minimum_tax needs a year-dependent phase-out rate. Dated-row support exists in tax_law.dated_row_value.
- **Risk of change:** Low for default plans, since AMT only runs with ISOs. Goldens with ISO fixtures would move.
- **Verification method:** Closed-form tests at AMTI of 1.2M and 2.0M (MFJ) for 2025 and 2026. Reconcile with the Rev. Proc. 2025-32 AMT table.
- **Verification note:** Code confirmed: core.py:1195-1233 hard-codes 2025 phase-out starts and a flat 0.25 phase-out rate with no year switch; the comment cites Rev. Proc. 2024-40. The module runs only for ISO holders. The 2026 law figures could not be verified externally. Narrow exposure argues for low severity. The 'AMT not in the runbook' claim was not checked.
- **Linked implementation items:** WI-003, WI-010, WI-027

### FIN-006 — Reference data includes stale or unverified state tax, estate and mortality inputs although the dashboard shows only one blocking state-tax flag

- **Expert:** financial_planner · **Category:** reference-data-currency · **Severity:** low · **Confidence:** low
- **Inspection status:** requires_external_domain_verification · **Verification status:** partially_confirmed
- **Evidence citations:**
  - `reference_src/state_tax.csv` — North Carolina, Indiana, New York rows — North Carolina is 4.50% (the expert recalls the statutory 2026 rate as 3.99%). Indiana is 3.05% (recalled 2.95% for 2026). The New York estate exemption is 6,940,000, recalled as the 2024 figure. (The verifier opened the file and confirmed the stored values, not the 2026 law.)
  - `src/core.py:1120-1136` — _STATE_INCOME_BRACKETS and _STATE_INCOME_BRACKETS_VALUE_YEARS — California brackets are explicitly the 2024 schedule (indexed by assumed inflation). The 1% mental-health surcharge above $1M is not present. New York brackets are tagged 2026 but show lower-bracket rates (4/4.5/5.25/5.5/6%); if the expert's recollection is right that these were reduced by 0.1pp for 2026 (unverified), the tag is stale.
  - `reference_src/tax_update_dashboard.csv` — state_tax row — status REVIEW_REQUIRED_BY_STATE, blocking TRUE, last reviewed 2026-06-10, with no per-state review date. The runbook confirms the build still runs on stale data (advisory).
  - `reference_src/mortality_table.csv:1-2` — age 18 row notes — The mortality table is a log-linear interpolation of 5-year SSA anchors, built from a secondary aggregation and not a verbatim SSA table. The note itself recommends replacing it. It has no row in the update dashboard.
  - `reference_src/tax_law_v10.json` — part_d_base_premium_monthly; ss_wage_base rows — The Part D base premium has only a 2025 row (40.0, 'assumption'). The 2026 Social Security wage base is 184,500 but its status is 'assumption', while the dashboard marks both families as current.
- **Observed behavior:** Federal 2026 tables (brackets, standard deduction, LTCG, IRMAA, Part B premium) match what the expert recalls from the cited IRS/CMS documents and carry a 'verified' status in the dataset; that is consistent with the dataset status and was not re-fetched in this review. The state, estate, mortality and Part D inputs do not have the same assurance.
- **Impact:** State tax, state estate tax and survivor-year mortality inputs can be off by small to moderate amounts for households in the affected states. The dashboard's status vocabulary does not distinguish 'verified', 'assumption' and 'unreviewed' consistently across families.
- **Affected workflows/scenarios:** State income tax; State estate tax; Relocation comparisons; Monte Carlo mortality; Medicare premium estimates
- **Root cause:** State and mortality maintenance runs outside the dated verification process used for federal values, and the dashboard is advisory. State schedules are also embedded in core.py rather than the dated dataset.
- **Assumptions, jurisdiction and rule year:** jurisdiction: US states (NC, NY, CA, IN modeled rows), SSA mortality, CMS Part D; rule year: 2026 (review date 2026-10-19). Several rows are tagged to 2024 or earlier.; assumptions: State figures below are from the expert's own recollection and were not fetched from primary sources. They must be confirmed. The tax-update dashboard already marks state_tax REVIEW_REQUIRED_BY_STATE and blocking, but builds still proceed by design. State data is sourced (per-row citation) but unverified. Professional review is required before any advisor-ready state-specific use. Authority class: unverified for the 2026 state values (expert recollection); rule status: sourced dataset rows plus hard-coded schedules in core.py.
- **Options and tradeoffs:**
  1. Run a one-time verification of all modeled states against primary sources (CPA/advisor), and add per-state last_reviewed and source URLs.
  2. Make unverified states emit an explicit disclosure on the build and workbook when the blocking flag is set.
  3. Restrict the supported-state list to verified states.
- **Recommendation:** Options 1 and 2 together. Replace the mortality table with a direct SSA transcription at the next refresh.
- **Dependencies:** External verification against state revenue departments and SSA
- **Implementation considerations:** Per-row review dates in state_tax.csv, and a dashboard row for mortality and Part D.
- **Risk of change:** Low to medium. Updating rates moves state-tax-dependent goldens.
- **Verification method:** Primary-source check of each changed row, tests pinning the new values, and an updated dashboard row with source and date.
- **Verification note:** Confirmed by opening files: state_tax.csv has NC at 4.50%, IN at 3.05% and the NY estate exemption at 6,940,000; mortality_table.csv row 1 says values are interpolated from SSA anchors. Whether those rows are stale for 2026 rests on recollection with no primary-source check. CA/NY bracket rows in core.py, the dashboard CSV and the Part D/wage-base rows were not opened by the verifier. Bundles several unverified items, so severity low and confidence low. Needs external verification.
- **Linked implementation items:** WI-003, WI-010, WI-027

### FIN-008 — The 'Social Security taxable fraction' input (default 85%) is editable and displayed as an assumption but is not used by the tax engine

- **Expert:** financial_planner · **Category:** input-integrity · **Severity:** low · **Confidence:** high
- **Inspection status:** finding_identified · **Verification status:** confirmed
- **Evidence citations:**
  - `src/tax_assumptions.py:92-104` — LEVERS social_security_taxable_fraction — Registered as a plan lever with an 'Auto' value of 0.85 and a 0-1 range.
  - `src/projection_stages/roth_conversion_and_agi_tax.py:578` — ss_taxable = social_security_taxable_amount(...) — The engine computes taxable Social Security from the statutory phase-in (core.py:881-902) and never reads c['ss_taxable'].
  - `src/reporting/sheets_summary_builder.py:473` — 'SS Taxable Fraction' — The summary prints c['ss_taxable'] as an assumption row. A search of src found no other reader of this config key.
  - `frontend/js/dashboard.js:4270-4274` — social_security_taxable_fraction help — The help text tells the user this is 'the percentage of benefits assumed to be taxable' and that a higher value raises tax.
- **Observed behavior:** Changing the field has no effect on tax. The summary shows 85% even when the engine's actual taxable share for the year is lower.
- **Impact:** A user or advisor can believe they have overridden the Social Security tax assumption when they have not, and a reader of the summary sees an assumption that was not applied.
- **Affected workflows/scenarios:** Tax Assumptions page; Summary sheet assumptions list
- **Root cause:** The lever predates the statutory phase-in implementation and was left in place.
- **Assumptions, jurisdiction and rule year:** jurisdiction: US federal (IRC 86); rule year: Statutory; assumptions: Arithmetic on the engine side is correct (statutory provisional-income formula). The defect is a misleading input and display.
- **GitHub contextual evidence:** pull_request 358 (contextual_only) — (local git subject only: Economic & Tax Assumptions)
- **Options and tradeoffs:**
  1. Remove the lever and summary row and show the actual share (row['ss_taxable_pct_actual']).
  2. Honor it as a cap on the taxable share when set.
  3. Keep it but label it 'not used'.
- **Recommendation:** Option 1.
- **Dependencies:** Schema, field_tiers, blank-plan and migration updates
- **Implementation considerations:** Needs a plan-data migration for saved plans carrying the row.
- **Risk of change:** Low. No calculation changes (the summary sheet row removal may touch workbook golden comparisons).
- **Verification method:** Search for the key after removal, and run the schema/blank-plan tests.
- **Verification note:** tax_assumptions.py registers the lever (help text 'Share of Social Security benefits included in AGI'). A grep of src for readers of the config key ss_taxable found only the sheets_summary_builder.py:473 display and the data_io.py:2208 population. The engine computes the share from the statutory formula (roth_conversion_and_agi_tax.py:578-580). The dashboard.js help text was not opened by the verifier.
- **Linked implementation items:** WI-028

### FIN-009 — Federal estate-tax defaults assume a married $30M exemption for every household, and the credit-shelter-trust logic counts the decedent's exemption twice under portability

- **Expert:** financial_planner · **Category:** estate-tax-modeling · **Severity:** low · **Confidence:** low
- **Inspection status:** finding_identified · **Verification status:** partially_confirmed
- **Evidence citations:**
  - `src/parsing/estate_planning.py:48` — fed_exempt default — Defaults 'exemption_mfj' to 30,000,000 regardless of household size.
  - `src/after_tax.py:751-774` — estimate_terminal_estate_tax — With portability enabled, the credit-shelter amount (row_cst) is subtracted from the federal taxable estate while the full combined exemption is still applied. With portability disabled, row_cst is not subtracted and the exemption is still the combined figure.
  - `src/planning_engines.py:3005-3019` — estate penalty (optimizer) — The Roth optimizer's estate model uses the same fed_exempt base.
  - `src/after_tax.py:772` — estimate_terminal_estate_tax federal_taxable — federal_taxable = max(0, row_total + biz - (row_cst if c.get('federal_portability_enabled', True) else 0)): portability defaults to True, and row_cst is subtracted only when it is enabled. (Opened in the planner re-verification.)
- **Observed behavior:** A single-member household receives a $30M federal exemption by default (if the 2026 per-person exemption is about $15M, as the expert recalls, unverified). When a credit shelter trust is funded under portability, the shelter is counted once as exclusion from the estate and again inside the combined exemption.
- **Impact:** Federal estate tax is understated for estates above the true exemption: for singles between about $15M and $30M, and by up to 40% of the CST amount for large couples' estates. Below those levels there is no effect.
- **Affected workflows/scenarios:** Terminal estate tax estimate; Roth estate-aware scoring (ESTATE_TAX_AWARE, MAXIMIZE_PTI); Estate sheet
- **Root cause:** One exemption figure is labelled 'MFJ' and is applied to every household. The CST adjustment was added for the state exemption and reused for federal.
- **Assumptions, jurisdiction and rule year:** jurisdiction: US federal (IRC 2010, 2631, 2010(c)(5) portability); rule year: 2026 (the OBBBA exemption of $15M per person, indexed); assumptions: The default is a user-editable input. Estate-tax findings apply only to estates above the exemption, which is a small minority of households. The combined $30M exemption presumes a timely portability (Form 706) election, which is the model's default (federal_portability_enabled True, src/after_tax.py:772). In the planner's reading of the arithmetic (after_tax.py:751-774), the credit-shelter-trust double count understates tax under both portability settings when the CST is smaller than the first decedent's exemption. Authority class: unverified (expert recollection; arithmetic reading). Attorney review is required for any estate-structure use. The portability analysis is the expert's reading of the arithmetic and is not a legal conclusion.
- **Options and tradeoffs:**
  1. Derive the default from household size (and the survivor's status), and decouple federal CST treatment from the state shelter cap.
  2. Keep the input but add a validation or warning when household size is 1 and the exemption is above the single-person figure.
  3. Document the simplification.
- **Recommendation:** Option 2 now. Option 1 when estate modeling is next touched.
- **Dependencies:** Attorney review of the portability and CST treatment
- **Implementation considerations:** A one-person default is a one-line change, but saved plans carry the explicit value.
- **Risk of change:** Low.
- **Verification method:** Unit tests: single household with a $20M estate, and a couple with a $5M CST and a $35M estate, with the expected tax computed by hand.
- **Verification note:** estate_planning.py:48 defaults exemption_mfj to 30,000,000 (user-editable; key name says MFJ). Household-size handling beyond it was not traced. In after_tax.py:751-774, federal_taxable subtracts row_cst when portability is enabled while the full fed_exempt is still applied, consistent with a possible double count, but it may be intentional modeling and is not a legal conclusion; row_cst semantics were not traced. planning_engines.py:3005-3019 was not opened. Low severity, low confidence.
- **Linked implementation items:** WI-002, WI-010, WI-027

### FIN-010 — Joint-account basis step-up is still asymmetric by which spouse dies first, so the decedent's half of a survivor-owned joint account gets no step-up when the non-owner spouse dies first

- **Expert:** financial_planner · **Category:** survivor-scenario · **Severity:** low · **Confidence:** medium
- **Inspection status:** finding_identified · **Verification status:** confirmed
- **Evidence citations:**
  - `src/planning_engines.py:436-459` — _account_titling — The docstring says the F8 fix defaults joint-named accounts to JTWROS so the step-up is symmetric between spouses.
  - `src/planning_engines.py:461-490` — _account_basis_step_fraction — A JTWROS account gets a 0.5 step-up when it belongs to the deceased.
  - `src/planning_engines.py:493-517, 686-689` — _survivor_bonus_step_fraction — For the survivor's own accounts the fraction ignores JTWROS and falls through to the household regime, which is 0 under COMMON_LAW. The survivor loop applies it as the bonus.
- **Observed behavior:** If member 1 (the assigned owner) dies first, the joint account gets a half step-up. If member 2 dies first, the same account, owned by the survivor, gets none.
- **Impact:** The survivor's basis is understated, and so is the step-up benefit, whenever the non-owner spouse dies first in a common-law household with joint taxable accounts. The effect is a higher modeled capital-gains tax on later draws, and varies run to run in Monte Carlo.
- **Affected workflows/scenarios:** First-death transition; Survivor capital-gains tax; Monte Carlo survivor paths
- **Root cause:** The F8 fix covered the deceased owner's side only.
- **Assumptions, jurisdiction and rule year:** jurisdiction: US federal (IRC 1014(b)(9), 2040(b)); property regime is configurable; rule year: Statutory; assumptions: The model assigns joint/household-named accounts to member 1. The step-up fraction is configurable per account (titling). The error direction is conservative (more capital-gains tax for the survivor). Tax-professional review applies to titling advice.
- **GitHub contextual evidence:** pull_request 209 (contextual_only) — (local git subject only: Tier 3 PR C death handling)
- **Options and tradeoffs:**
  1. No credible alternative; this is a correctness defect.
- **Recommendation:** Make _survivor_bonus_step_fraction return 0.5 for JTWROS (and the default joint-named titling) accounts, mirroring the deceased-side logic.
- **Dependencies:** none
- **Implementation considerations:** Check the second-death consolidation for any double application. Golden fixtures with joint taxable accounts will move.
- **Risk of change:** Low to medium: survivor-path goldens move slightly.
- **Verification method:** Unit test: two spouses, one joint taxable account owned by member 1, kill member 2 first, and assert basis_free equals 50% of the balance. Compare with the member-1-dies-first case.
- **Verification note:** planning_engines.py:436-459 and 461-490 give JTWROS and default joint-named accounts a 0.5 step-up for the deceased owner's accounts. _survivor_bonus_step_fraction (493-517) handles only COMMUNITY_PROPERTY and SEPARATE_PROPERTY and otherwise falls back to the household regime (0 under COMMON_LAW); it ignores JTWROS. The survivor loop at 686-689 applies it as the bonus. The asymmetry follows from the code. Direction conservative, effect small; no test was run. Planner sign-off (PC-3): a cheap Wave 1 notice about the asymmetric survivor step-up is added in WI-010a (P2 within the item) until WI-025 lands.
- **Linked implementation items:** WI-010a, WI-025

### FIN-011 — Annually indexed statutory limits (QLAC, QCD, student-loan interest phase-out) are hard-coded or extrapolated by an assumed inflation rate instead of read from dated rows

- **Expert:** financial_planner · **Category:** reference-data-currency · **Severity:** low · **Confidence:** medium
- **Inspection status:** requires_external_domain_verification · **Verification status:** partially_confirmed
- **Evidence citations:**
  - `src/core.py:787-801` — QLAC_PREMIUM_LIMIT_BASE / qlac_premium_limit — $210,000 for 2025, compounded by brk_inf, which gives about $214,200 for 2026.
  - `src/core.py:1163-1168` — QCD_ANNUAL_LIMIT_BASE / qcd_annual_limit — $108,000 for 2025, compounded by brk_inf, which gives about $110,160 for 2026.
  - `src/projection_stages/roth_conversion_and_agi_tax.py:~598-616` — student_loan_int_ded thresholds — The phase-out ranges (165k-195k joint, 80k-95k other) are literals and are not indexed.
- **Observed behavior:** These limits follow an assumed inflation path, not the published annual figures. If the published 2026 QLAC limit is $210,000, as the expert recalls (unverified), the model would apply about $214,200 for 2026, above that limit.
- **Impact:** Small: tens of dollars to a few thousand dollars on QLAC/QCD modeling, and student-loan interest rarely matters for retirees.
- **Affected workflows/scenarios:** QLAC optimizer and RMD base; QCD planning; Above-the-line deductions
- **Root cause:** These limits were never moved into tax_law_v10.json.
- **Assumptions, jurisdiction and rule year:** jurisdiction: US federal (IRC 401(a)(9)(H), 408(d)(8), 221); rule year: 2025 base, extrapolated for 2026 onward; assumptions: The extrapolation direction is small, and the IRS publishes rounded figures each year. If the expert's recollection is right (unverified), the 2026 QLAC limit is $210,000 and the 2026 QCD limit is $111,000; these must be verified. Authority class: unverified; rule status: hard-coded base year with assumed inflation. The values are hard-coded in code, so they are not covered by the annual-maintenance runbook.
- **Options and tradeoffs:**
  1. Move them into dated dataset rows and add them to the runbook family list.
  2. Keep the extrapolation, but cap it with a published-year table.
  3. Leave as is and document.
- **Recommendation:** Option 1 at the next dataset refresh.
- **Dependencies:** External verification of the published figures
- **Implementation considerations:** tax_law dated rows already exist for similar families.
- **Risk of change:** Low.
- **Verification method:** Pin tests for 2026 against the published notices.
- **Verification note:** core.py:787-801 and 1163-1168 confirm QLAC ($210k) and QCD ($108k) 2025 bases compounded by brk_inf for later years. Both comments cite the IRS notice for 2025. The 2026 published figures are recollection, not externally verified. The student-loan phase-out being unindexed was not checked. Low severity stands.
- **Linked implementation items:** WI-003, WI-027

### QA-005 — No dollar-exact golden master covers a household that depletes or has a funding shortfall

- **Expert:** quality · **Category:** test-coverage-gap · **Severity:** low · **Confidence:** low
- **Inspection status:** finding_identified · **Verification status:** partially_confirmed
- **Evidence citations:**
  - `tests/fixtures/synthetic_golden_master_cases.json` — All ten pinned scenarios end with large positive terminal liquid net worth, from about $6.3M (lower_return_environment) to $15.8M. Every scenario has plan_start 2026 and 29-33 rows. This is the static content of the fixture, not a test outcome.
  - `tests/synthetic_plans.py:393-398` — high_spending_pressure — Scenario says it exercises the withdrawal cascade 'under sustained drawdown'. Its pinned terminal liquid NW is still about $11M, so the cascade is not driven to exhaustion.
  - `tests/test_frozen_sample_plan_golden_master_regression.py:148-153,288-300` — PINNED_FAILURES — Frozen household is pinned as fully solvent (PINNED_FAILURES = []). Earlier shortfalls (2052-56) disappeared after re-pins.
  - `tests/test_frozen_sample_plan_golden_master_regression.py:254-265` — The frozen plan sets roth_policy 'none', mc_paths 5 and mc_sensitivity_sims 1. No full-pipeline golden covers an active Roth conversion with a shortfall.
- **Observed behavior:** Dollar-exact characterization is concentrated on comfortably funded plans. The shortfall, unfunded-gap and depletion branches are covered by narrower behavioural tests (about 20 test files mention unfunded or UNFUNDED). Nothing pins a complete multi-year path through them.
- **Impact:** A change to withdrawal ordering, HELOC draw, essential-spend cuts or depletion year can pass every pinned golden. The failure-case rows are what users with thin portfolios see.
- **Affected workflows/scenarios:** Depletion and shortfall handling; Withdrawal cascade ordering; Poor-return and high-spending scenarios; Longevity stress
- **Root cause:** Scenarios were derived from a prosperous baseline by modest percentage overrides. The two overrides meant to stress it (+20% spend, 4% return) were not strong enough to cause depletion.
- **Options and tradeoffs:**
  1. Add 2-3 synthetic scenarios that deplete (for example a thin portfolio with high spending and poor returns, or a very long horizon) and pin year of depletion, first unfunded year and cumulative shortfall in the existing fixture format.
  2. Strengthen the existing high_spending_pressure scenario until it depletes. Cheaper but it changes its pinned values and role.
  3. Rely on unit tests of the shortfall branches. No new maintenance, but no end-to-end regression anchor.
- **Recommendation:** Option 1, using the existing regen tool and provenance binding. Include one scenario for each spouse dying first.
- **Dependencies:** Use tools/regen_synthetic_golden_master.py and the provenance marker process
- **Implementation considerations:** Pin shape (year, level, code) of failures as the frozen test does, not just terminal NW, so both worsening and recovering are caught. Author the scenarios after the tax-correctness changes so they are not re-pinned immediately.
- **Risk of change:** Low, additive. New scenarios add fixture churn when the engine legitimately changes.
- **Verification method:** Check that the new scenarios produce validation failures and a depletion year, then confirm the pin test fails if the withdrawal order is deliberately changed in a scratch branch.
- **Verification note:** The verifier did not open the fixture. The finding's own sources say narrower behavioural tests already cover shortfall and unfunded branches, so this is a gap in end-to-end pinning, not a missing safety net. The 'all ten scenarios end solvent' claim is plausible but unverified. Downgraded to low.
- **Linked implementation items:** WI-030

### QA-006 — Several tests pass vacuously or convert failures into skips

- **Expert:** quality · **Category:** test-quality · **Severity:** low · **Confidence:** medium
- **Inspection status:** finding_identified · **Verification status:** confirmed
- **Evidence citations:**
  - `tests/test_legacy_data_migration_regression.py:20-150` — Docstring promises metadata.json, wellness-to-healthcare, purged allocations and unchanged golden numbers. The tests read the real, gitignored input/client_data.csv rather than the staged workspace. Five of seven skip when it is absent. The two metadata tests use 'if exists:' guards and pass without asserting anything. The wellness assertion is commented out (lines 91-96). test_healthcare_terminology_present ends in 'pass'. plan_metadata appears nowhere under src/ or tools/, so the concept the tests check no longer exists.
  - `tests/test_monte_carlo_default_engine_mode.py:17-23,108-115` — Both the default-engine test and the scalar-vs-vectorized fidelity gate call skipTest if prepare_config_from_sectioned_data raises ValueError. A real config-preparation regression would silently skip the gate.
  - `tests/test_regressions_functional.py:186-203` — A NIIT/withdrawal test skips when the frozen household's year-1 income covers spending, so the assertion is no longer reached.
  - `tests/test_reference_golden_regression.py:47-52` — test_sources_not_yet_moved_do_not_drift — Loops over files that exist in both reference_src/ and reference_data/. reference_data/ has no tracked files and does not exist, so the loop body never runs.
  - `tests/test_demo_plan_data_is_fictional.py:92,210,275,303` — Four leak checks skip whenever the live plan is blank, so on a clean checkout they verify nothing.
- **Observed behavior:** Static reading shows tests whose assertions cannot be reached on a clean checkout or whose failure path is a skip. Of 4,208 test functions, a scan found only 16 with no assertion construct, and most of those are legitimate no-raise checks, so this is a small, concentrated problem.
- **Impact:** False assurance and noise. A real regression in migration handling, config preparation or the vectorized-engine gate would go unreported.
- **Affected workflows/scenarios:** Migration regression coverage; Monte Carlo fidelity gate; Reference-data drift guard
- **Root cause:** Tests were written against the developer's live input/ or a past design and never retired when the design changed. The skip-on-exception pattern was used to avoid red tests.
- **Options and tradeoffs:**
  1. Delete test_legacy_data_migration_regression.py and the dead drift test, and replace the skip-on-ValueError calls with assertions that fail loudly on the frozen fixture.
  2. Rewrite the legacy-migration tests to use the staged workspace and real assertions on the migrated rows.
  3. Leave them in place and mark them clearly as legacy. Lowest effort, but the false assurance remains.
- **Recommendation:** Option 1 for the dead tests and the MC skips; option 2 only if a legacy migration path is still supported.
- **Dependencies:** Confirm that legacy migration is retired (src/legacy_conversion exists and has its own tests)
- **Implementation considerations:** Use pytest's strict skip accounting or a skip budget test so new skips are reviewed.
- **Risk of change:** Low. Removing never-asserting tests changes no product behaviour.
- **Verification method:** Run the affected files and confirm none of them skip on a clean checkout. Add a skip-count ratchet like the existing source-grep freeze.
- **Verification note:** reference_data/ does not exist, so the drift loop is vacuous. test_monte_carlo_default_engine_mode.py:19-23 skips on ValueError from config preparation. The legacy migration test has 7 skip-related lines, and plan_metadata does not appear under src/ or tools/. Not every cited line, such as the demo-fictional-data skips, was checked.
- **Linked implementation items:** WI-012

### QA-007 — Broad except-and-continue blocks in the calculation core hide faults, and nothing tests for them

- **Expert:** quality · **Category:** error-handling · **Severity:** low · **Confidence:** medium
- **Inspection status:** finding_identified · **Verification status:** partially_confirmed
- **Evidence citations:**
  - `src/planning_engines.py:2262-2268` — senior_bonus_deduction wrapper — try: std += senior_bonus_deduction(...) / except Exception: pass inside the Roth conversion tax estimate. Any error in the senior-deduction call silently removes it from the estimate.
  - `src/planning_engines.py:2465-2476` — The block that evaluates Roth guardrail caps ends in except Exception: pass. A failure leaves later caps unset with no signal. (The verifier notes the 2474 block wraps _would_allow calls that look like diagnostic trace recording, so 'sizes every cap' is overstated.)
  - `src/planning_engines.py:4938-4952` — Numpy conversion loop for Monte Carlo output arrays is wrapped in except Exception: pass. A mid-loop failure leaves some fields as arrays and others as lists.
  - `src/planning_engines.py:6158-6168` — Percentile and legacy-floor accumulators end in except Exception: pass.
  - `src/projection_stages/deterministic_engine.py:328-349` — _path_factor / _path_ratio — Fall back to a deterministic inflation formula on any exception.
  - `src/data_io.py:1789-1790` — The liabilities block, covered in QA-003.
- **Observed behavior:** A scan found 343 bare or broad except clauses in src/. At least seven in the engine core end in pass or a silent fallback, and no logging is present in src/projection_stages/. No test enforces a limit on these patterns. Existing tests do exercise some individual fallbacks (for example the backfill test).
- **Impact:** A defect in a deduction, guardrail or aggregate calculation changes numbers rather than failing. With golden masters that are regenerated by tool, such a change tends to be re-pinned instead of investigated.
- **Affected workflows/scenarios:** Roth conversion sizing; Monte Carlo aggregates; Deterministic projection
- **Root cause:** Defensive fallbacks written for optional fields that catch every exception type.
- **Options and tradeoffs:**
  1. Narrow each handler to the specific expected exceptions and log once (with the year and field) on fallback.
  2. Add a ratchet test that counts broad excepts in src/projection_stages and planning_engines.py and fails on growth, as the project does for other patterns.
  3. Leave as is, accepting silent fallbacks in non-critical estimates.
- **Recommendation:** Options 1 and 2 together, starting with planning_engines.py:2266, which affects Roth conversion amounts.
- **Dependencies:** none
- **Implementation considerations:** Deliberate failure paths (for example the MC array conversion) may be better as explicit validation. Overlaps planning_engines.py regions touched by FIN-003 and FIN-010, so sequence after them.
- **Risk of change:** Low to moderate. Narrowing exposes latent errors that currently pass quietly, so golden values might move and must be investigated, not re-pinned.
- **Verification method:** Inject a raising stub in tests for each guarded call and assert the error is logged or surfaced.
- **Verification note:** The broad excepts exist at planning_engines.py:2264-2266 (senior bonus deduction, silently dropped from the Roth tax estimate) and 2473-2474. The 2474 block wraps `_would_allow` calls that look like diagnostic trace recording, not cap sizing, so the 'sizes every guardrail cap' wording is overstated. The senior-deduction swallow is a real numeric risk. The other cited locations and the count of 343 were not verified.
- **Linked implementation items:** WI-029

### QA-008 — Large share of UI behaviour is protected only by grandfathered source-text greps; some UI modules have no direct test

- **Expert:** quality · **Category:** test-strategy · **Severity:** low · **Confidence:** low
- **Inspection status:** finding_identified · **Verification status:** partially_confirmed
- **Evidence citations:**
  - `tests/test_freeze_frontend_source_grep.py:1-60` — Records that source-text assertions pass on dead or commented code and break on behaviour-preserving refactors. The remedy is a freeze, not a conversion.
  - `tests/fixtures/frontend_source_grep_baseline.json` — 86 test files are grandfathered in the baseline (list length, verified by the verifier). A scan also found 39 Python test files that touch frontend paths but import no src module, run no node process and make no HTTP client call.
  - `frontend/js/dashboard_decomp_misc.js:120-160` — saveWithdrawalAccountOrder / resetWithdrawalAccountOrderToDefault / withdrawalOrderDrop — Withdrawal-order save and drag-drop handlers. A search of tests/ for these names found no reference, while the server route is tested in tests/test_plan_rows_strategy_policy_functional.py:69-93.
  - `frontend/js/dashboard_plan_folder_io.js` — readFolderCsvTexts has no test reference. A file-name reference scan also found no test naming dashboard_decomp_estate_insurance.js, dashboard_decomp_misc.js or dashboard_decomp_supplemental_tables.js.
- **Observed behavior:** The suite has real execution layers (91 Node files, 19 Playwright specs) and a ratchet that prevents new greps. The old greps remain, and some user-facing modules are referenced by no test. Name-based scans under-count because tests/frontend/load_dashboard.mjs loads the bundle as a whole.
- **Impact:** UI regressions in untested handlers (withdrawal order, estate and insurance panels) would reach users. Greps give false confidence on behaviour-preserving refactors, and block legitimate ones.
- **Affected workflows/scenarios:** Withdrawal order UI; Estate and insurance data entry; Folder import in the UI
- **Root cause:** Test style inherited from earlier waves, partly addressed by the 2026-08-04 freeze.
- **Options and tradeoffs:**
  1. Convert baselined files to Node vm or Playwright tests gradually, prioritising money-affecting screens.
  2. Add targeted Node tests for the untested handler groups only.
  3. Maintain the freeze and accept the residual.
- **Recommendation:** Option 2 now, then option 1 opportunistically when a file is touched.
- **Dependencies:** none
- **Implementation considerations:** Use tests/frontend/load_dashboard.mjs as the existing harness. A real coverage report would sharpen the list.
- **Risk of change:** Low.
- **Verification method:** Count the baseline file list over time and require it to shrink. Add Node tests that fail when the handlers are removed.
- **Verification note:** The baseline list has 86 entries, matching the finding. A search of tests/ for withdrawalOrderDrop and saveWithdrawalAccountOrder returned nothing, but the whole-bundle loader makes name-based scans unreliable, so the 'untested handler' claim is unproven. The freeze ratchet is an existing mitigation.
- **Linked implementation items:** WI-031

### UX-003 — Document-level Tab/Enter override skips interactive controls and the field help badge is not keyboard-operable

- **Expert:** usability_accessibility · **Category:** accessibility-keyboard · **Severity:** low · **Confidence:** medium
- **Inspection status:** finding_identified · **Verification status:** partially_confirmed
- **Evidence citations:**
  - `frontend/js/dashboard.js:6534-6565` — moveToNextEntry — Capture-phase keydown handler calls preventDefault() on Enter and forward Tab for any input/select present in focusableEntries(), and moves focus to the next entry in that curated list.
  - `frontend/js/navigation.js:~416-422` — focusableEntries — The curated list is .field input/select, .lot-table/.matrix-table controls, and a few action buttons; it excludes help badges, in-row buttons, textareas, links and <summary> elements.
  - `frontend/js/dashboard.js:2017-2028` — fieldTooltipHtml — The help badge is <sup class="field-info-i" tabindex="0" title=... aria-label=...> with no role and no key handler; the comment says activation relies on the click bubbling to the row's onclick.
  - `frontend/css/dashboard.css:702-703` — .field-info-i — 11px glyph, ~12px wide hit area, hover/focus styling only; help text is a native title tooltip.
  - `frontend/js/dashboard_decomp_row_model.js:4736-4775` — showFieldHelp — The full help is written into #helpPanel on focus/click; the panel is not linked to the control (no aria-describedby) and is not a live region.
- **Observed behavior:** Forward Tab and Enter from any listed field jump to the next listed field, so any focusable element between fields (help badges, row action buttons, details summaries inside fields) is never reached going forward. The badge is a tab stop, but pressing Enter or Space on a <sup> does not produce a click, so keyboard users cannot open the fuller explanation. The short hint is a title attribute, which keyboard and touch users generally do not see.
- **Impact:** Keyboard-only and switch users cannot reach or operate part of the in-field help. Tab order no longer matches visual order (WCAG 2.1.1 / 2.4.3 concern), and the 12px badge is a small target (2.5.8, not measured). Mitigation the verifier noted: the help panel opens on field focus, so keyboard users still get the full text; shift-Tab is native.
- **Affected workflows/scenarios:** All Plan Data entry steps; Field help and glossary lookup; Keyboard-only data entry
- **Root cause:** Enter-to-advance was added for spreadsheet-like speed and implemented by overriding Tab globally; the help affordance was built as a decorative <sup> with delegated mouse click.
- **Options and tradeoffs:**
  1. Make the badge a real <button type='button' aria-label='Help: <label>'> that calls showFieldHelp(), and drop the Tab override (keep Enter-to-advance only).
  2. Keep the override but include the badge and in-field buttons in focusableEntries() and add keydown (Enter/Space) to the badge.
  3. Add a user preference 'Enter moves to next field' and leave Tab native.
- **Recommendation:** Option 1: native Tab behaviour restored, Enter advance retained, badge becomes a button with aria-describedby linking to the help text.
- **Dependencies:** tests/frontend/keyboard_field_advance_scope.test.mjs expectations; Context-help panel markup; UX-004 (aria-describedby wiring)
- **Implementation considerations:** An earlier scope fix narrowed the handler but still intercepts Tab. Check lot/matrix tables where Tab-to-next-cell is expected. Enlarge badge hit area to at least 24px.
- **Risk of change:** Medium: data-entry muscle memory for Tab flow changes; mitigated by keeping Enter-advance.
- **Verification method:** Playwright keyboard walk through a data-entry page asserting every interactive element is reachable in DOM order; unit test that Enter/Space on the badge opens help; manual screen-reader pass (NVDA/VoiceOver).
- **Verification note:** Confirmed: dashboard.js moveToNextEntry preventDefaults forward Tab and Enter on listed inputs and selects; focusableEntries (navigation.js:422) excludes the help badge; the badge is a <sup tabindex=0> with no key handler. Impact smaller than stated because help opens on field focus, so severity low. WCAG 2.5.8 target-size claim not measured.
- **Linked implementation items:** WI-021

### UX-008 — Page changes are not announced and focus can be lost; nav is rebuilt on every edit and collapses opened groups

- **Expert:** usability_accessibility · **Category:** navigation-focus · **Severity:** low · **Confidence:** low
- **Inspection status:** finding_identified · **Verification status:** partially_confirmed
- **Evidence citations:**
  - `frontend/js/navigation.js:228-236` — scrollAndFocus — After a step change it scrolls to top and focuses the first entry from focusableEntries() inside #mainPane (a field or an action button); nothing else moves focus or announces the new page.
  - `frontend/js/dashboard_decomp_row_model.js:2418-2500` — renderSteps — Rebuilds #steps via innerHTML; each <details class="nav-group"> gets open only when it contains the active step.
  - `frontend/js/dashboard_decomp_row_model.js:4389-4395` — scheduleStatusUpdate — Called from editValue; 120ms later it re-runs renderSteps() after any field edit.
  - `frontend/index.html:6, 56` — <title> / #mainPane aria-label — Document title is static and #mainPane has a fixed aria-label 'Main content'; a search for document.title in frontend/js found no updates.
- **Observed behavior:** On navigation the clicked nav button is destroyed by the re-render and focus goes to the first field (which fires onfocus help and may raise the on-screen keyboard on touch), or is lost if the page has no listed entries. The title and landmark name never change. Typing in a field rebuilds the left nav shortly after, which closes any group the user opened manually.
- **Impact:** Screen-reader users get no cue that the page changed. Keyboard users lose their place in the nav, and sighted users who expand another group lose it on the next keystroke. Moderate annoyance rather than a blocker.
- **Affected workflows/scenarios:** Step navigation; Browsing nav groups while editing
- **Root cause:** SPA without routing; nav is a full innerHTML re-render with no state preservation.
- **Options and tradeoffs:**
  1. Update document.title and focus the page heading (tabindex=-1) after navigation, and expose a polite live region 'Now on <step>'.
  2. Preserve open group state (a Set keyed by group name) and avoid re-rendering the nav on every edit; update badges in place.
  3. Both.
- **Recommendation:** Both, small changes.
- **Dependencies:** tests/e2e focus-restoration specs exercise first-field focus; update expectations
- **Implementation considerations:** Keep first-field focus for data-entry pages if desired, but only after the heading is announced, or provide a setting.
- **Risk of change:** Low.
- **Verification method:** e2e: navigate via keyboard, assert document.title and live-region text; assert user-opened group remains open after an edit.
- **Verification note:** Confirmed in part: navigation.js:231-233 moves focus to the first focusable entry after a step change; a grep of frontend/js found no document.title updates. The renderSteps open-group reset and the scheduleStatusUpdate re-render on edit were not verified.
- **Linked implementation items:** WI-021

### UX-010 — Text-prompt dialog lacks dialog semantics and focus management; enumerated values are collected as free text

- **Expert:** usability_accessibility · **Category:** accessibility-dialogs-forms · **Severity:** low · **Confidence:** medium
- **Inspection status:** finding_identified · **Verification status:** partially_confirmed
- **Evidence citations:**
  - `frontend/js/dashboard_decomp_row_model.js:3398-3440` — showInAppPrompt — The overlay has no role=dialog, aria-modal or aria-labelledby, no Tab trap, and does not restore focus on close, unlike showInAppConfirm and showSaveDiscardStayModal in the same file.
  - `frontend/js/dashboard_decomp_estate_insurance.js:68-106` — addEstateState / addTrustAccount — State and trust type are typed into a free-text prompt ('Revocable, Irrevocable, Credit Shelter, QTIP, Special Needs, Other' only in a placeholder); an empty reply silently becomes 'Revocable'. Trust creation chains two prompts.
  - `frontend/js/dashboard_plan_folder_io.js:28` — importPlanFolder — Destructive 'replaces their current rows' confirmation uses native window.confirm, inconsistent with the in-app modals.
- **Observed behavior:** Seven call sites use showInAppPrompt. The dialog is not announced as a dialog, focus is not returned, and background content can be tabbed to. Constrained inputs (state, trust type) are typed rather than chosen.
- **Impact:** Screen-reader and keyboard users do not get the same dialog behaviour as the other modals; typos in trust type can store an unrecognised value.
- **Affected workflows/scenarios:** Add estate state; Add trust account; Name scenario/case; New account name
- **Root cause:** The prompt helper was not updated when WI-502 hardened the confirm and save/discard dialogs.
- **Options and tradeoffs:**
  1. Bring showInAppPrompt up to the same pattern (role=dialog, labelledby, trap, restore focus) and add an optional select/choices mode.
  2. Replace chained prompts with an inline form with a <select> for state and trust type.
  3. Do only the semantics fix.
- **Recommendation:** Option 1, then Option 2 for the estate flows.
- **Dependencies:** none
- **Implementation considerations:** Reuse _trapTabWithinModal and the id sequence.
- **Risk of change:** Low.
- **Verification method:** Extend tests/frontend/inapp_modal_accessibility_and_listener_leak.test.mjs to cover the prompt.
- **Verification note:** Confirmed: addEstateState uses showInAppPrompt for free-text state entry; importPlanFolder at plan_folder_io.js:28 uses native window.confirm. showInAppPrompt itself was not opened by the verifier, so the missing dialog semantics are unverified; the chained trust prompt was not checked.
- **Linked implementation items:** WI-020

### UX-011 — Plan-folder import does not refresh the on-screen plan after committing

- **Expert:** usability_accessibility · **Category:** workflow-data-integrity-ux · **Severity:** low · **Confidence:** medium
- **Inspection status:** partially_inspected · **Verification status:** partially_confirmed
- **Evidence citations:**
  - `frontend/js/dashboard_plan_folder_io.js:20-34` — importPlanFolder — After POST /api/import/commit it only calls showMessage('Imported ...'); there is no loadAll(), renderMain() or dirty reset.
  - `frontend/js/dashboard_plan_folder_io.js:6-9` — pickFolder — Depends on showDirectoryPicker, otherwise rejects with a message pointing to a 'CSV backup zip'.
- **Observed behavior:** The import replaces datasets in the database, but the client's rows array and any dirty entries are left as before. The confirmation lists technical dataset names and does not show what will change. No other callers of /api/import/commit were found in frontend/js.
- **Impact:** The user may continue to see and save pre-import values; a later Save Changes can overwrite imported data with stale edits. Impact depends on whether another code path refreshes the plan; that could not be confirmed statically.
- **Affected workflows/scenarios:** Import plan data from folder
- **Root cause:** Feature added as a thin wrapper over the import API without the post-load refresh used by other flows.
- **Options and tradeoffs:**
  1. Call loadAll() after commit (and warn first if dirty.size>0).
  2. Navigate to Plan Status with a summary of datasets and row counts.
  3. Hide the control when showDirectoryPicker is unavailable.
- **Recommendation:** Option 1 plus the in-app confirm and a dirty-edit warning.
- **Dependencies:** UX-001 helper
- **Implementation considerations:** Show preview counts from pre.datasets in the confirm body.
- **Risk of change:** Low.
- **Verification method:** Node test with stubbed api() asserting loadAll is called after commit.
- **Verification note:** plan_folder_io.js:29-30 shows the import commits and then only calls showMessage, with no loadAll or dirty reset. The staleness impact is plausible but unproven; another refresh path (server-side event or page reload) was not ruled out.
- **Linked implementation items:** WI-018

## 6. Options and tradeoffs

Per-finding options are in section 5. This section covers the cross-cutting choices and records the conflicts resolved during synthesis.

| Theme | Alternatives, decision and consequence |
|---|---|
| Tax correctness (FIN-003, FIN-001, FIN-010) | Fix in one sequenced batch with a single re-pin per step, versus separate small fixes. Chosen: sequence qualified dividends, then brokerage gains in two phases (IRMAA MAGI first, which has a two-year lookback and needs no same-year recomputation; NIIT, ACA MAGI and Social Security taxation second, all same-year and each needing a convergence test, NIIT included because it is computed inside the cascade loop), then survivor step-up, measuring each in the documented measure mode first. Cost: three to four golden re-pins; CPA review of sample outputs is recommended for FIN-001 phase 2 and not blocking for FIN-003. FIN-001 and FIN-003 partly offset, so they are released together even if developed and pinned in sequence. Benefit: each movement is attributable. Limitation notices ship in Wave 1 (WI-010a) as a mitigation until each fix lands (FIN-001 option 3 as stopgap only). |
| Monte Carlo accuracy (FIN-002) | Scalar as engine of record (accurate, slow, 81 calls in the claim sweep) versus verifying and broadening the replay headline that already ships versus disclosure alone. Chosen: per-figure disclosure with the tolerance label tied to a measured regime now (WI-009, including the unmeasured shipped default optimize_terminal_tax), then verification and wider coverage (WI-036); a further repair only if the measurement shows a gap, as a new item; kernel sharing (ARC-002 option 3) after the dependency cycle is removed. Cost of waiting: the '+/-tol' label comes from one fixture and one policy, and the tile shows a second figure with a different definition. |
| Server mode (ARC-001, ARC-009) | Host allow-list plus startup guard (small), launch token (medium), or remove server mode (loses the debugging path). Chosen: allow-list and guard first, then decide on the token. |
| Legacy persistence layer (ARC-004) | Remove dead tables and fallbacks now (cheap, partial) then migrate snapshots and prices later (larger, needs backup retention), versus leave. Chosen: both, in order. The stale-balance scenario should be reproduced before relying on it. |
| Frontend structure (ARC-007) | Registry first, bundler second, with a guard test as an interim step. The registry is scheduled after the usability edits that touch the same functions (conflict 6). |
| Documentation layout (DOC-001, DOC-002) | Fix banners and move files plus a guard test, versus declaring docs/superpowers the active location. Chosen: follow the existing written rule and enforce it with a test. |

### Conflict records

**Conflict 1.** ARC-002 and FIN-002 describe the same defect (default vectorized Monte Carlo engine diverging from the exact engine).

- **Alternatives:** Keep both as separate findings; Keep ARC-002 (architecture framing); Keep FIN-002 and mark ARC-002 a duplicate
- **Decision criterion:** Findings-schema rule: keep the stronger finding. Strength = verification status, evidence quantity, hierarchy position (financial safety above maintainability).
- **Decision:** FIN-002 is kept; ARC-002 is marked duplicate (duplicate_of FIN-002).
- **Rationale:** FIN-002 is retained as the kept finding (partially confirmed after planner re-verification) with quantified pre-fix gaps and a located disclosure; ARC-002 is partially confirmed and only gives unquantified parity evidence. ARC-002's unique content (default-tier parity fixtures, scalar spot-check, shared kernels) was merged into FIN-002's evidence, recommendation and considerations.
- **Consequence:** One tracked item (FIN-002); work items WI-009, WI-036 and WI-037 link to both IDs.

**Conflict 2.** ARC-002 states users cannot tell the figure is approximate; FIN-002 evidence shows a tolerance label and a second displayed figure on the KPI tile.

- **Alternatives:** Accept ARC-002's claim; Accept FIN-002's evidence
- **Decision criterion:** Direct file evidence outranks an unchecked claim; ARC-002's own verifier did not check the UI.
- **Decision:** A disclosure exists in two parts: a '+/-tol' or 'approximate' label on the headline, and a second 'without using Roth for extras' figure with an 'Approximate' tooltip. The tolerance comes from one fixture and one policy, and the shipped default regime (optimize_terminal_tax) has not been measured.
- **Rationale:** dashboard_decomp_home_panels.js:28-55 and planning_engines.py:6765-6777 were opened in the planner re-verification. The accurate statement is not that a single symmetric label is wrong, but that the tile shows two figures with different success definitions and that the tolerance is not demonstrated per regime.
- **Consequence:** WI-009 is restated as a per-figure disclosure with the tolerance label tied to a measured regime, not the addition of a first disclosure.

**Conflict 3.** Documents disagree on the direction and size of the Monte Carlo bias: BACKLOG.md describes the vectorized engine as ~14-18pp optimistic, a test narrative says it reads 4-6pp below scalar, and the archived diagnostic shows +17-18pp (roth_policy=none) and -5 to -6pp (roth_policy=fill_to_bracket, which the diagnostic calls 'default') on the tier-allocation path.

- **Alternatives:** Adopt the BACKLOG figure; Adopt the test narrative; Adopt the diagnostic's per-regime signed figures
- **Decision criterion:** Most specific and traceable source; do not resolve by assertion.
- **Decision:** Use the diagnostic's per-regime figures as working evidence for the superseded tier path only; its post-fix (replay) figures are the diagnostic authors' and unverified here; the shipped default optimize_terminal_tax is unmeasured, so all three regimes need re-measurement.
- **Rationale:** Only the diagnostic separates the regimes and explains the offsetting biases, and its addendum plus planning_engines.py:6654 show the headline later moved to the replay allocation. No run was possible in this static review.
- **Consequence:** WI-009 and WI-036 require paired-path runs under none, fill_to_bracket and optimize_terminal_tax on the replay path; the documents should be corrected (WI-016).

**Conflict 4.** DOC-001 says CAPITAL_GAINS_IN_AGI.md section 1 gives 'the opposite of current behaviour'; FIN-001 relies on the same document to say brokerage gains are still excluded.

- **Alternatives:** DOC-001 is right: the document is wholly stale; FIN-001 is right: the gap remains; Both are partly right
- **Decision criterion:** Open the document and the engine (orchestrator did, lines 1-30 and 75-90 of the document; deterministic_engine.py:1228-1245 and 1432-1445).
- **Decision:** Both are partly right.
- **Rationale:** Section 1 still describes the pre-H1 gap for home and rental sales, which the engine now handles (stale). Section 5 decision 1 correctly records that brokerage-cascade gains remain excluded, and the engine adds only home_sale_ltcg_gain.
- **Consequence:** DOC-001 is narrowed in WI-016 (relabel section 1 as pre-change for sales); FIN-001 stands. The status must be updated again when WI-024 lands.

**Conflict 5.** Sequencing: ARC-005 (mechanical refactor of the engine, requires pins locked) against FIN-001/FIN-003/FIN-010/FIN-002 (correctness changes that re-pin the same goldens), and ARC-002's kernel-sharing option.

- **Alternatives:** Refactor first, then fix with cleaner code; Fix correctness first, then refactor with pins locked; Interleave
- **Decision criterion:** Default hierarchy: financial safety and functional correctness rank above maintainability; refactor must not be interleaved with re-pinning because it hides behaviour change.
- **Decision:** Correctness changes first (waves 2-4), mechanical extraction and kernel move last (wave 5).
- **Rationale:** Tax and Monte Carlo fixes are user-visible numeric errors. A refactor between re-pins would make pin movements unattributable.
- **Consequence:** Engine structure risk (ARC-005) persists until wave 5; WI-029 and WI-030 add safety nets before the refactor.

**Conflict 6.** Sequencing: frontend structural refactor (ARC-007, maintainability) against usability and accessibility fixes (UX findings) that edit the same row-model and navigation code.

- **Alternatives:** Registry refactor first; Usability fixes first, guard tests in between; Interleave
- **Decision criterion:** Hierarchy puts data integrity and functional correctness (UX-001, UX-002, UX-011) first, then maintainability above accessibility; but the accessibility edits are small, localized and the refactor touches the same functions.
- **Decision:** Data-loss and honesty fixes (UX-001/011/002) first, then accessibility edits behind the WI-015 guard tests, then the registry refactor (WI-035). This is a deliberate, recorded deviation from the default ordering for accessibility versus maintainability.
- **Rationale:** Doing the refactor first would force the accessibility work to be rewritten against the new registry, and the guard tests lower the regression risk of the order chosen.
- **Consequence:** Accessibility improvements reach users earlier; ARC-007 remains open until wave 4.

**Conflict 7.** Release-gate expansion (QA-002) against vacuous or skipping tests (QA-006): running the full suite in the gate may expose environment-dependent failures.

- **Alternatives:** Expand the gate first and triage failures; Clean the tests first; Do both in the same wave
- **Decision criterion:** Data integrity and false-assurance risk; avoid blocking releases on known-vacuous tests.
- **Decision:** Both in wave 1 as independent work items; engine correctness work (wave 2) depends on both.
- **Rationale:** Their files do not overlap (tools/release_gate.py versus test files).
- **Consequence:** Expect triage effort when the gate first runs the full suite.

Default priority hierarchy applied: financial safety; data integrity; legal/regulatory correctness; security/privacy; functional correctness; maintainability; usability/accessibility; documentation; performance/cost; cosmetic polish.

## 7. Recommendation

Proceed in six waves (section 9). In priority order:

1. **Close the data-exposure path (P0).** Untrack and ignore the trends-log backup, add the hygiene test, and have the owner decide on a history purge. Never copy the file's values into any document.
2. **Restore release assurance (P1).** Make the gate run the pytest suite with a collected-count floor, after cleaning tests that pass vacuously.
3. **Decide scope and verify rule values with professionals (P1).** Early retirement before 59.5, the earnings test, estate defaults, which Monte Carlo success definition is the headline, and the 2026 AMT, QLAC/QCD and state values. These decisions gate calculation changes and cannot be made from code alone.
4. **Correct the tax engine in a measured sequence (P1).** Qualified-dividend stacking, brokerage gains in MAGI-keyed rules (IRMAA MAGI first; NIIT, ACA MAGI and Social Security taxation second), survivor step-up symmetry; FIN-001 and FIN-003 are released together. Ship the limitation notices in Wave 1 (WI-010a: FIN-001 and FIN-003 at P1, FIN-004 and FIN-010 at P2) and retire each when its fix lands.
5. **Make uncertainty and failure visible (P1).** Per-figure Monte Carlo disclosure with the tolerance label tied to a measured regime, including the shipped default; log and surface swallowed derived-result failures; a strict shared number parser so a bad cell cannot empty the liabilities list.
6. **Fix workflow honesty (P1).** Save before structural change, refresh after import, and a truthful build overlay.
7. **Harden server mode (P1)** with a Host allow-list and a non-loopback startup guard; remove the inert hosted-mode defaults.
8. **Then structure (P3).** Accessibility edits behind guard tests, rule-value refresh, depletion goldens, Monte Carlo verification and wider coverage, and only then mechanical engine and frontend restructuring with golden pins locked.

The recommendation, target design (section 8) and waves (section 9) agree on this order. Items that rest on insufficient evidence (FIN-007, UX-005, UX-009, UX-012, UX-013, DOC-008, DOC-009) are scheduled only as "confirm first" steps.

## 8. Target design

Target state after the waves, expressed as boundaries and rules rather than a rewrite:

| Aspect | Target |
|---|---|
| Boundaries and responsibilities | Pure numeric kernels (tax, RMD, death transition, Roth plan, withdrawal, growth) live in a dependency-free module; stage modules import kernels and do not import the consolidated engine file; the deterministic engine and the vectorized Monte Carlo engine share those kernels where feasible (WI-034, WI-037). Input mapping is split into private section helpers. |
| Calculation flow | Plan rows → one strict number grammar → engine config → stages → rows; MAGI-keyed rules see all realized income including brokerage gains; qualified dividends are stacked below realized gains at preferential rates, at every call site, and remain in NII for NIIT. Statutory parameters (AMT, QLAC, QCD, student-loan limits, state schedules) come from dated dataset rows with a source and review date, not code constants. |
| Monte Carlo | The headline success rate (funded as asked) and the secondary within-tier figure each carry their own definition label; the tolerance is demonstrated for each Roth regime, including the shipped default optimize_terminal_tax, with a per-build scalar spot-check diagnostic; paired-path fixtures run in the default tier. |
| Data and persistence | One persistence family (plan file plus app.db) with forward-only migrations; the legacy SQLite layer and trends-reporter fallbacks removed after a final conversion window; no sensitive runtime data tracked by git (whole data directories ignored, hygiene test). |
| Validation and errors | Invalid input is a reported row-level error, never a silent default; derived-result failures are logged and shown in build diagnostics; broad except-and-pass handlers in the calculation core are narrowed and counted by a ratchet test. |
| UI | Explicit renderer/hook registry instead of a wrapper chain; a save-before-structural-change helper; one navigation entry point with the unsaved-changes guard; field-level validation messages with an error summary; shared focus token; honest build overlay; admin surface with accessible names and live regions. |
| Security | Server mode rejects non-loopback Host headers and refuses a non-loopback bind without an access token; hosted-mode remnants removed; desktop mode unchanged. |
| Tests | Release gate runs the pytest suite with a collected floor; golden pins keep provenance; depleting and survivor-first scenarios pinned; extractor logic and untested UI handlers covered; no vacuous or skip-on-failure tests. |
| Documentation | Every spec carries a verified status and sits in the future or archive tier; reference documents contain no hard-coded sizes; the README matches on-screen names; the Concepts Guide is linked and accessible; each result-moving change has a plain-language release note. |
| Assumptions and migrations | Saved plans carrying the Social Security taxable-fraction row migrate cleanly; the snapshot and price migration is forward-only and keeps backup retention. |

## 9. Implementation waves

Waves are dependency-ordered. Items marked with the same parallel group within a wave are serial (they share files or golden pins); different groups in the same wave share no components and may run in parallel. Golden pins and the row-model/navigation files are the shared components that force serial chains. Effort: S ≤ 2 days, M ≤ 1 week, L > 1 week (rough). Priority: P0 immediate, P1 next, P2 planned, P3 opportunistic.

### Wave 0

Decisions and external verification. No code. Three independent items.

| ID | Change | Findings | Depends on | Priority | Effort | Risk | Owner | Parallel group | Validation | Exit criteria | Model tier |
|---|---|---|---|---|---|---|---|---|---|---|---|
| WI-001 | Owner checks the remote's visibility and the list of clones/forks, then decides whether to purge the tracked trends-log backup from history (git filter-repo plus force-push) or accept the exposure. Record the decision. | QA-001 | — | P0 | S | Low (a purge, if chosen, is high-risk and affects every clone) | Repository owner | W0-A | Written decision record naming visibility, clone list and chosen option. | Decision recorded; if purge chosen, a separate scheduled task exists with a clone-notification step. | standard_reasoning |
| WI-002 | Decision record on scope and policy: (a) is retiring before 59.5 supported (FIN-004); (b) is the earnings test in scope (FIN-007; confirm the claim first); (c) phasing of the brokerage-gain MAGI fix (FIN-001): phase 1 IRMAA MAGI only, phase 2 NIIT, ACA MAGI and Social Security taxation, and whether phase 1 is pinned separately; (d) which Monte Carlo success definition is the headline: confirm the owner direction recorded in the diagnostic addendum ('funded as asked', Roth as a last resort) and decide whether the secondary 'without using Roth for extras' figure stays on the tile (FIN-002); (e) federal estate defaults for one-person households (FIN-009). | FIN-001, FIN-002, FIN-004, FIN-007, FIN-009 | — | P1 | S | Low | Product owner with financial planner | W0-B | Decision record per item, each stating jurisdiction, rule year and whether professional review applies. | Every listed decision is recorded and referenced by the dependent work items. | expert_reasoning |
| WI-003 | External verification of rule values against primary sources by a CPA/advisor: 2026 AMT exemption, phase-out start and rate (FIN-005); QLAC and QCD limits (FIN-011); NC, IN, CA, NY state rows, NY estate exemption, Part D and wage-base rows, mortality table (FIN-006). | FIN-005, FIN-006, FIN-011 | — | P1 | M | Low | Tax professional with financial planner | W0-C | Table of value, source citation, retrieval date and verifier for each row. | Each value is verified or marked unverified with a disclosure decision. | expert_reasoning |

### Wave 1

Independent safeguards in disjoint components: ignore rules and hygiene (A), release gate (B), server files (C), report_compute (D), import parsing (E), Monte Carlo disclosure (F), preflight and limitation notices (G), extractor (H), test hygiene (I), admin UI (J), CSS focus/layout (K), frontend guard tests (L), documentation folder (M).

| ID | Change | Findings | Depends on | Priority | Effort | Risk | Owner | Parallel group | Validation | Exit criteria | Model tier |
|---|---|---|---|---|---|---|---|---|---|---|---|
| WI-004 | Remove the tracked trends-log backup from HEAD, widen the ignore rule to the whole financial_trends_reporter/data directory (keeping .gitkeep), and add a hygiene test failing on any other tracked file there. | QA-001 | — | P0 | S | Low | Engineer (quality) | W1-A | git ls-files financial_trends_reporter/data lists only .gitkeep; new hygiene test fails when a dummy backup file is tracked there. | File untracked, ignore rule and test merged; no sensitive values copied into any artifact. | standard_reasoning |
| WI-005 | Make the release gate run the pytest suite (excluding nightly unless decided otherwise) with a minimum collected-test count, and add a test asserting the gate invokes pytest. | QA-002 | — | P1 | S | Low to moderate (newly executed tests may need triage) | Engineer (quality) | W1-B | Compare pytest --collect-only count with the gate's count; unit test over tools/release_gate.py. | Gate executes the governance, golden and hygiene guards and fails if the collected count drops below the floor. | standard_reasoning |
| WI-006 | Server-mode hardening: Host allow-list (loopback names plus the explicitly configured host), refusal to start on a non-loopback host without an access token, request-body size cap; remove the inert hosted-mode environment defaults and the ProxyFix wrapper once no reader is confirmed. Keep the desktop bridge exemption. | ARC-001, ARC-009 | — | P1 | M | Low to medium (scripts using arbitrary Host headers break) | Engineer (backend) | W1-C | Unit tests for spoofed Host/Origin pairs and non-loopback start; manual check that server mode works on localhost and 127.0.0.1; grep shows no readers of removed variables. | Spoofed-Host requests are rejected; non-loopback start is refused without a token; config tests pass. | expert_reasoning |
| WI-007 | Log every swallowed exception in report_compute.run_projection_artifacts (logging.exception) and make config_contract_warnings visible to callers; backend only (UI surfacing is in WI-019). | ARC-003 | — | P1 | S | Low | Engineer (backend) | W1-D | Unit test forcing attach_plan_result to raise: asserts a log record and the warning in the result structure. | No handler swallows silently; test merged. | standard_reasoning |
| WI-008 | One strict shared number parser (finite only, parenthesised negatives, currency/percent symbols) in src/money.py, used by the CSV validator and the data_io blocks; a bad cell becomes a reported error; the liabilities fallback logs and warns instead of emptying the list; parametrized tests for nan, inf, (5,000) and garbage. | QA-003 | — | P1 | M | Moderate (plans with values that coerced to zero will now warn) | Engineer (backend) | W1-E | Parametrized import tests for liabilities and holdings; direct unit tests of money helpers; golden fixtures unchanged. | No import path accepts nan/inf; no failure empties liabilities silently. | expert_reasoning |
| WI-009 | Make the Monte Carlo disclosure honest for both displayed figures: label the headline (funded as asked, Roth as a last resort) and the secondary 'without using Roth for extras' figure (success_rate_within_tier_policy) each with its own success definition; tie the '+/-tol' label to a measured regime by running the paired-path harness on the post-replay headline path under none, fill_to_bracket and the shipped default optimize_terminal_tax (unmeasured so far); label the figure 'directional' when the active policy's tolerance is not demonstrated; keep the secondary figure flagged approximate; add a small-N scalar spot-check whose gap is reported in diagnostics. | FIN-002, ARC-002 | — | P1 | M | Low | Engineer with financial planner | W1-F | Node test of the KPI label for each policy and for both figures; unit test of the diagnostic field; a paired-path run under optimize_terminal_tax alongside none and fill_to_bracket on the post-replay headline path, and on the tier shadow for the secondary figure (static recommendation; not run in this review). | The KPI cannot present a tolerance label for a policy whose measured gap exceeds it; each displayed figure carries its own definition; the shipped default regime has a recorded measurement. | expert_reasoning |
| WI-010 | Preflight and limitation notices that need a scope or rule-value decision (no calculation change): earnings-test warning if confirmed (FIN-007), single-person estate exemption warning (FIN-009, after WI-002(e)), AMT and state-data verification status (FIN-005, FIN-006, after WI-003). The FIN-001, FIN-003, FIN-004 and FIN-010 notices are in WI-010a. | FIN-007, FIN-009, FIN-005, FIN-006 | WI-002, WI-003 | P2 | M | Low | Engineer with financial planner | W1-G | Preflight unit tests for each warning; wording review by the planner. | Warnings appear in preflight and results for the affected scenarios. | standard_reasoning |
| WI-010a | Interim limitation and preflight notices that need no calculation change, no rule-value verification and no scope decision: (P1) brokerage-gain MAGI limitation (FIN-001: brokerage gains are not in AGI, MAGI, IRMAA MAGI or NIIT) and qualified-dividend overstatement (FIN-003: qualified dividends are taxed at ordinary rates, so tax is overstated), on the Tax Assumptions page, in the workbook and in the advisor report; (P2 within this item) a pre-59.5 distribution warning (FIN-004, wording neutral to the WI-002(a) scope decision) and a survivor step-up asymmetry notice (FIN-010). Each notice has a recorded retirement trigger: it is removed when WI-023, WI-024 or WI-025 lands, or when WI-002(a) is decided and implemented. | FIN-001, FIN-003, FIN-004, FIN-010 | — | P1 | S | Low | Engineer with financial planner | W1-G | Preflight unit test per notice; planner wording review; a retirement check that each notice is removed when its fix ships. | Notices appear in preflight, the Tax Assumptions page, the workbook and the advisor report for affected plans; each has a recorded retirement trigger. | standard_reasoning |
| WI-011 | Give the Monarch extractor a test seam (lazy directory creation, function-level logic), add table-driven tests for fingerprinting, id-less rows, once-only events and mark-delivered, and write the history CSV atomically. | QA-004 | — | P2 | M | Low | Engineer (quality) | W1-H | New tests run without network or browser dependency; mutation check on the fingerprint inputs. | Idempotency and change detection covered; history write is atomic. | standard_reasoning |
| WI-012 | Retire or rewrite tests that pass vacuously or skip on failure (legacy migration test, dead drift loop, skip-on-ValueError in the Monte Carlo gate, skip-when-blank leak checks); add a skip-count ratchet. | QA-006 | — | P2 | S | Low | Engineer (quality) | W1-I | Affected files do not skip on a clean checkout; ratchet test added. | No test in scope passes without asserting or skips on a regression. | standard_reasoning |
| WI-013 | Admin / Control Center accessibility: accessible names for grid and tester inputs, live-region #msg with an error role, throttled unsaved-change announcements, in-app confirm instead of native confirm; correct the 'single local Plan Data folder' text at admin.js:1956. | UX-006, DOC-007 | — | P2 | S | Low | Engineer (frontend) | W1-J | DOM test: every grid/config input has an accessible name and #msg is a live region; manual screen-reader pass. | Admin controls are named and messages announced. | standard_reasoning |
| WI-014 | Shared focus token (>=3:1) applied to custom controls including .rg-sw and .toggle-switch, an in-flow message row for persistent messages, and reflow fixes (minmax(0,1fr), help as drawer when space is short); confirm UX-005 and UX-013 by rendering before changing them. | UX-007, UX-013, UX-005 | — | P2 | M | Medium (layout regressions across 28 steps) | Engineer (frontend) | W1-K | Playwright viewport matrix x text size; tab-through screenshot of Roth guardrails; contrast calculation over tokens. | Visible focus on every custom control; no horizontal scroll in the tested matrix. | standard_reasoning |
| WI-015 | Interim frontend guard: tests that freeze the script list and order in index.html and the set of renderMain/showStepHelp wrappers; Playwright navigation baseline across all steps. | ARC-007 | — | P2 | S | Low | Engineer (frontend) | W1-L | Guard tests fail when a module is added/reordered or a new wrapper appears. | Baseline recorded and guard merged. | standard_reasoning |
| WI-016 | Documentation status and layout: correct stale banners (eight documents), relabel CAPITAL_GAINS_IN_AGI.md section 1 as the pre-change state for home/rental sales, move shipped specs to archive and the rest to future, fix wrong sizes and nav inventory in the reference docs, archive PLAN_METADATA_SCHEMA.md after confirming it is unused, add a numbering note to BACKLOG.md, and add a status front-matter test plus a guard against new files under docs/. | DOC-001, DOC-002, DOC-005, DOC-009 | — | P2 | M | Low to medium (path citations) | Documentation owner | W1-M | Path-citation test green; git ls-files docs/ empty; status banners match code and release notes. | Every spec has a verified status and sits in its tier. | mechanical |

### Wave 2

Three independent tracks: the UI chain (W2-UI, serial because it shares the row-model and navigation files), the engine chain (W2-ENG, serial because it shares golden pins and engine files), and documentation (W2-D) plus persistence cleanup (W2-PERSIST).

| ID | Change | Findings | Depends on | Priority | Effort | Risk | Owner | Parallel group | Validation | Exit criteria | Model tier |
|---|---|---|---|---|---|---|---|---|---|---|---|
| WI-017 | End-user documentation: rewrite the README optional-features text with current on-screen names (update test markers), split developer commands out, link the Concepts Guide from README, index and a Help entry, refresh its contents field, add figure alt text and replace field keys with on-screen labels, rewrite input/ READMEs as import/export format notes, add the missing release-notes index entry. | DOC-003, DOC-004, DOC-007, DOC-006 | WI-013, WI-016 | P3 | M | Low | Documentation owner | W2-D | Walk each README instruction in the running app; open the guide and confirm contents and alt text; run the README currency test. | README matches the UI; guide discoverable and accessible. | mechanical |
| WI-018 | Shared save-before-structural-change helper used by every add/delete/seed handler; refresh the plan (loadAll) after folder import with a dirty-edit warning and in-app confirm. | UX-001, UX-011 | WI-015 | P1 | M | Low to medium (a failing save can block adding) | Engineer (frontend) | W2-UI | Node tests: staged edit survives each handler; save precedes the mutation; import refreshes rows; one Playwright spec on Estate add-trust. | No add/delete/import path drops staged edits. | standard_reasoning |
| WI-019 | Build overlay honesty: replace Cancel with honest wording or a real cancel, suppress auto-navigation when the user has moved on, and surface config_contract_warnings from WI-007 in the build result banner. | UX-002, ARC-003 | WI-007, WI-018 | P1 | M | Low (wording) to medium (true cancellation) | Engineer (frontend and backend) | W2-UI | Node test: pending build, cancel, resolve, assert no navigation and accurate message; extend build e2e specs. | UI never claims a cancel that did not happen; swallowed-step warnings visible. | standard_reasoning |
| WI-020 | Field-level validation feedback (invalid style, per-field message via aria-describedby, error summary with links, structured errors) and accessible text-prompt dialog with select choices for state and trust type. | UX-004, UX-010 | WI-018, WI-019, WI-014 | P2 | M | Low | Engineer (frontend) | W2-UI | Node test with a 422 payload of three errors; extended modal accessibility test for the prompt. | Every server-flagged field is visibly and programmatically marked with its message. | standard_reasoning |
| WI-021 | Keyboard and navigation accessibility: help badge as a button, native Tab with Enter-advance kept, page title and heading focus on navigation, preserved nav group state, one navigateTo guard for Back/Forward and jump links (confirm UX-009 first), per-chart summaries (confirm UX-012 first). | UX-003, UX-008, UX-009, UX-012 | WI-018, WI-020 | P2 | M | Medium (central navigation path, Tab muscle memory) | Engineer (frontend) | W2-UI | Playwright keyboard walk; unit test for Enter/Space on the badge; e2e title/live-region assertions. | All interactive elements reachable in DOM order; page changes announced. | standard_reasoning |
| WI-022 | Measure the effect of the qualified-dividend and brokerage-gain fixes on the frozen sample plan using the documented 'measure' mode and before/after fixtures, reporting the IRMAA-only and NIIT effects of FIN-001 separately; no pins change. The fixes use the 2026 federal tables the dataset marks verified (not re-fetched here), so this item does not wait for the external rule-value verification in WI-003. | FIN-001, FIN-003 | WI-002, WI-005, WI-012 | P1 | S | Low | Engineer with financial planner | W2-ENG | Closed-form fixtures (MFJ 80k ordinary + 30k qualified dividends + a realized gain; 230k AGI + 100k gain) with hand-computed expected values. | Impact table agreed by planner before any pin changes. | expert_reasoning |
| WI-023 | Stack qualified dividends with realized gains at the 0/15/20% preferential rates in the tax kernel, in one patch: qualified dividends sit in the preferential stack below realized gains and the ordinary schedule excludes them; the cascade call at withdrawal_cascade_investment_tax.py:234, the ltcg_marginal_rate callers and the Roth LTCG cap change in the same patch; qualified dividends stay in NII for NIIT; re-check effective-marginal-rate reporting; re-pin through the documented golden process. | FIN-003 | WI-022 | P1 | M | Medium (goldens with taxable portfolios move) | Engineer with financial planner | W2-ENG | Closed-form kernel tests covering dividends plus a realized gain together (not dividends alone), including the cascade call site and a NIIT case; golden_compare measure then regen with a recorded reason; planner sign-off on the closed-form tests and impact table before re-pin; CPA review of sample outputs recommended, not blocking. | Tax matches hand calculation; all call sites changed in the same patch; pins re-recorded with provenance; released together with WI-024 because FIN-001 and FIN-003 partly offset. | expert_reasoning |
| WI-024 | Fold brokerage realized gains into MAGI-keyed rules in two phases. Phase 1 (effort S to M, no cascade convergence exposure): add the net gain to IRMAA MAGI only, which has a two-year lookback. Phase 2 (effort L, same-year, convergence test required): NIIT MAGI (computed inside the cascade fixed-point loop, withdrawal_cascade_investment_tax.py:225-235), ACA MAGI and Social Security taxation; re-verify convergence of the cascade loop for each phase-2 step. | FIN-001 | WI-023 | P1 | L | Phase 1 low to medium; phase 2 medium to high (moves net worth, lifetime tax, Roth recommendations); overall medium to high | Engineer with financial planner (CPA review of phase 2 recommended) | W2-ENG | Phase 1: an IRMAA tier two years after a brokerage gain, closed-form. Phase 2: NIIT same-year closed-form (230k AGI + 100k gain: 3.8% x min(NII, 80k)), a convergence test for the NIIT step, ACA and Social Security cases with their own convergence tests; before/after fixture. | Phase 1 (IRMAA MAGI only) and phase 2 (NIIT, ACA MAGI, Social Security taxation) merged with re-pinned goldens (pinned separately if WI-002(c) so decides); CAPITAL_GAINS_IN_AGI.md updated; planner sign-off before re-pin and CPA review of phase-2 sample outputs recommended. | expert_reasoning |
| WI-025 | Make the survivor step-up symmetric: _survivor_bonus_step_fraction returns 0.5 for JTWROS and default joint titling; check the second-death consolidation for double application. | FIN-010 | WI-024 | P2 | S | Low to medium (survivor-path goldens move slightly) | Engineer with financial planner | W2-ENG | Unit test: kill member 2 first, basis_free equals 50% of balance; compare with member 1 dying first. | Both death orders give the same step-up on a joint account. | expert_reasoning |
| WI-026 | Remove plan_data_read, the trends-reporter fallbacks and the never-written legacy tables (audit_events, plan_snapshots); keep the conversion's ability to read client_files. | ARC-004 | — | P3 | M | Low | Engineer (backend) | W2-PERSIST | Convert a legacy fixture, delete all liabilities, run trends metrics, assert legacy client_files is ignored; update the pinned tests. | No code path reads removed fallbacks; conversion still works. | standard_reasoning |

### Wave 3

Rule-value refresh and engine hardening (W3-A, serial because it shares pins), plus independent test and documentation items (W3-C for UI handler tests, W3-E for plain-language help).

| ID | Change | Findings | Depends on | Priority | Effort | Risk | Owner | Parallel group | Validation | Exit criteria | Model tier |
|---|---|---|---|---|---|---|---|---|---|---|---|
| WI-027 | Move AMT, QLAC, QCD and student-loan limits into dated dataset rows; apply verified values from WI-003; refresh state, estate, Part D and mortality inputs with per-row review dates; fix the single-person estate default and credit-shelter treatment per WI-002. | FIN-005, FIN-006, FIN-011, FIN-009 | WI-003, WI-002, WI-025 | P2 | L | Low to medium (ISO and state goldens move) | Engineer with CPA/attorney review | W3-A | Closed-form tests at AMTI 1.2M and 2.0M for 2025 and 2026; pin tests for 2026 notices; hand-computed estate cases. | Values match primary sources; dashboard rows carry source and date. | expert_reasoning |
| WI-028 | Remove the Social Security taxable-fraction lever and summary row (show the actual share); add the plan-data migration, schema and blank-plan updates. | FIN-008 | WI-027 | P3 | S | Low | Engineer (backend) | W3-A | Search shows no readers of the key; schema and blank-plan tests pass. | Lever gone; saved plans migrate cleanly. | standard_reasoning |
| WI-029 | Narrow broad except-and-pass handlers in the engine core to expected exception types with one-time logging; add a ratchet test on counts; start with the senior-deduction swallow. | QA-007 | WI-028 | P2 | M | Low to moderate (latent errors surface; investigate, do not re-pin) | Engineer (backend) | W3-A | Injected raising stubs assert logging or surfacing; ratchet test. | No silent swallow in planning_engines.py or projection_stages without a logged fallback. | expert_reasoning |
| WI-031 | Targeted Node tests for untested UI handler groups (withdrawal order, estate/insurance panels, folder import) using the existing sandbox harness. | QA-008 | WI-021 | P3 | M | Low | Engineer (quality) | W3-C | Tests fail when the handlers are removed. | Each handler group has a behavioural test. | standard_reasoning |
| WI-033 | Plain-English layer for in-app help (one-line summaries and glossary links) after a non-expert read-through confirms the scope. | DOC-008 | WI-017, WI-021 | P3 | M | Low | Documentation owner with frontend engineer | W3-E | Read-through by a non-expert over a short page list. | Pages used before the first build have plain-language summaries. | standard_reasoning |

### Wave 4

Depletion goldens then Monte Carlo verification and wider coverage (W4-A, serial), in parallel with the frontend registry (W4-B) and the release notes (W4-C, which describe the engine changes after they land).

| ID | Change | Findings | Depends on | Priority | Effort | Risk | Owner | Parallel group | Validation | Exit criteria | Model tier |
|---|---|---|---|---|---|---|---|---|---|---|---|
| WI-032 | Plain-language release notes for the October engine changes (sale gains, senior bonus for itemizers, Tier 3 items, and the tax-correctness changes); update CAPITAL_GAINS_IN_AGI.md status; planner confirms wording. | DOC-006, DOC-001, FIN-001 | WI-024, WI-025, WI-027, WI-017 | P3 | S | Low | Documentation owner with financial planner | W4-C | Every golden-master changelog entry since 2026-09 maps to a note or an explicit 'no user-visible change'. | Index lists every note. | mechanical |
| WI-030 | Add two or three depletion/shortfall synthetic golden scenarios (including each spouse dying first), pinning depletion year, first unfunded year and shortfall shape, using the regen tool and provenance binding. | QA-005 | WI-027, WI-028, WI-029 | P3 | M | Low (additive) | Engineer (quality) | W4-A | Scenarios produce validation failures and a depletion year; pin test fails when withdrawal order is deliberately changed on a scratch branch. | Shortfall branches have end-to-end anchors. | expert_reasoning |
| WI-036 | Verify the shipped replay-allocation headline and broaden coverage: measure the shipped default optimize_terminal_tax regime, re-measure none and fill_to_bracket on the post-replay path, move paired-path fixtures into the default test tier, and tighten bounds to measured gaps. Repair the replay path further, or make the scalar engine the headline engine of record, only if the measurement shows a gap beyond the disclosed tolerance (a new item). | FIN-002, ARC-002 | WI-002, WI-009, WI-024, WI-025, WI-029, WI-030 | P2 | M | Low for measurement and fixtures; a further repair, if the measurement requires one, would be high risk (headline MC, sustainable-spend and claim-age results change) | Engineer with financial planner | W4-A | Paired-path harness n>=1000, several seeds, three Roth regimes (none, fill_to_bracket, optimize_terminal_tax), 4+ shapes, on the replay headline path; /signed gap/ within the disclosed tolerance in each regime; the tier-shadow secondary figure measured separately (static recommendation; not run in this review). | Disclosed tolerance holds for all three regimes in the default test tier, or a repair item is raised with the measured gap. | expert_reasoning |
| WI-035 | Replace the renderMain/showStepHelp decorator chain with an explicit hook registry; evaluate bundling afterwards; add a lint test that no module assigns window.renderMain outside the registry. | ARC-007 | WI-015, WI-021, WI-031 | P3 | L | Medium | Engineer (frontend) | W4-B | Playwright navigation across all steps before and after; guard tests updated. | No wrapper chain remains; script order no longer carries meaning. | standard_reasoning |

### Wave 5

Structural work with pins locked: engine extraction then kernel move (W5-A, serial), in parallel with the snapshot migration (W5-B).

| ID | Change | Findings | Depends on | Priority | Effort | Risk | Owner | Parallel group | Validation | Exit criteria | Model tier |
|---|---|---|---|---|---|---|---|---|---|---|---|
| WI-034 | Mechanical extraction in the engine core and parse_client (nested closures and sections into private helper modules) with golden pins locked (no regeneration). | ARC-005 | WI-036, WI-030, WI-029, WI-028, WI-008 | P3 | L | Medium (high-volume change in sensitive code, mitigated by goldens) | Engineer (backend) | W5-A | Golden-master and invariant tests unchanged byte for byte. | Large functions split; no pin changed. | expert_reasoning |
| WI-037 | Move pure kernels (death transition, Roth conversion plan, withdrawal, growth) into a dependency-free module; stages import it; static check that stage modules do not import planning_engines; evaluate sharing kernels with the vectorized engine. | ARC-005, ARC-002 | WI-034 | P3 | L | Medium | Engineer (backend) | W5-A | Static import check; golden pins unchanged. | Circular dependency removed. | expert_reasoning |
| WI-038 | Scheduled migration of KPI/result snapshots, price snapshots and build events into app.db/plan file with forward-only versioning; remove the legacy DB layer after a final conversion window. | ARC-004 | WI-026 | P3 | L | Medium (backups and retention must follow) | Engineer (backend) | W5-B | Migration test on a legacy fixture; backup/restore round trip. | Single persistence family; legacy DB no longer written. | standard_reasoning |

## 10. Validation plan

Nothing below has been performed. Each item states how an implementer would show the change works; the review itself validated nothing at runtime.

### Item-level validation

| Item | Validation | Exit criteria |
|---|---|---|
| WI-001 | Written decision record naming visibility, clone list and chosen option. | Decision recorded; if purge chosen, a separate scheduled task exists with a clone-notification step. |
| WI-002 | Decision record per item, each stating jurisdiction, rule year and whether professional review applies. | Every listed decision is recorded and referenced by the dependent work items. |
| WI-003 | Table of value, source citation, retrieval date and verifier for each row. | Each value is verified or marked unverified with a disclosure decision. |
| WI-004 | git ls-files financial_trends_reporter/data lists only .gitkeep; new hygiene test fails when a dummy backup file is tracked there. | File untracked, ignore rule and test merged; no sensitive values copied into any artifact. |
| WI-005 | Compare pytest --collect-only count with the gate's count; unit test over tools/release_gate.py. | Gate executes the governance, golden and hygiene guards and fails if the collected count drops below the floor. |
| WI-006 | Unit tests for spoofed Host/Origin pairs and non-loopback start; manual check that server mode works on localhost and 127.0.0.1; grep shows no readers of removed variables. | Spoofed-Host requests are rejected; non-loopback start is refused without a token; config tests pass. |
| WI-007 | Unit test forcing attach_plan_result to raise: asserts a log record and the warning in the result structure. | No handler swallows silently; test merged. |
| WI-008 | Parametrized import tests for liabilities and holdings; direct unit tests of money helpers; golden fixtures unchanged. | No import path accepts nan/inf; no failure empties liabilities silently. |
| WI-009 | Node test of the KPI label for each policy and for both figures; unit test of the diagnostic field; a paired-path run under optimize_terminal_tax alongside none and fill_to_bracket on the post-replay headline path, and on the tier shadow for the secondary figure (static recommendation; not run in this review). | The KPI cannot present a tolerance label for a policy whose measured gap exceeds it; each displayed figure carries its own definition; the shipped default regime has a recorded measurement. |
| WI-010 | Preflight unit tests for each warning; wording review by the planner. | Warnings appear in preflight and results for the affected scenarios. |
| WI-010a | Preflight unit test per notice; planner wording review; a retirement check that each notice is removed when its fix ships. | Notices appear in preflight, the Tax Assumptions page, the workbook and the advisor report for affected plans; each has a recorded retirement trigger. |
| WI-011 | New tests run without network or browser dependency; mutation check on the fingerprint inputs. | Idempotency and change detection covered; history write is atomic. |
| WI-012 | Affected files do not skip on a clean checkout; ratchet test added. | No test in scope passes without asserting or skips on a regression. |
| WI-013 | DOM test: every grid/config input has an accessible name and #msg is a live region; manual screen-reader pass. | Admin controls are named and messages announced. |
| WI-014 | Playwright viewport matrix x text size; tab-through screenshot of Roth guardrails; contrast calculation over tokens. | Visible focus on every custom control; no horizontal scroll in the tested matrix. |
| WI-015 | Guard tests fail when a module is added/reordered or a new wrapper appears. | Baseline recorded and guard merged. |
| WI-016 | Path-citation test green; git ls-files docs/ empty; status banners match code and release notes. | Every spec has a verified status and sits in its tier. |
| WI-017 | Walk each README instruction in the running app; open the guide and confirm contents and alt text; run the README currency test. | README matches the UI; guide discoverable and accessible. |
| WI-018 | Node tests: staged edit survives each handler; save precedes the mutation; import refreshes rows; one Playwright spec on Estate add-trust. | No add/delete/import path drops staged edits. |
| WI-019 | Node test: pending build, cancel, resolve, assert no navigation and accurate message; extend build e2e specs. | UI never claims a cancel that did not happen; swallowed-step warnings visible. |
| WI-020 | Node test with a 422 payload of three errors; extended modal accessibility test for the prompt. | Every server-flagged field is visibly and programmatically marked with its message. |
| WI-021 | Playwright keyboard walk; unit test for Enter/Space on the badge; e2e title/live-region assertions. | All interactive elements reachable in DOM order; page changes announced. |
| WI-022 | Closed-form fixtures (MFJ 80k ordinary + 30k qualified dividends + a realized gain; 230k AGI + 100k gain) with hand-computed expected values. | Impact table agreed by planner before any pin changes. |
| WI-023 | Closed-form kernel tests covering dividends plus a realized gain together (not dividends alone), including the cascade call site and a NIIT case; golden_compare measure then regen with a recorded reason; planner sign-off on the closed-form tests and impact table before re-pin; CPA review of sample outputs recommended, not blocking. | Tax matches hand calculation; all call sites changed in the same patch; pins re-recorded with provenance; released together with WI-024 because FIN-001 and FIN-003 partly offset. |
| WI-024 | Phase 1: an IRMAA tier two years after a brokerage gain, closed-form. Phase 2: NIIT same-year closed-form (230k AGI + 100k gain: 3.8% x min(NII, 80k)), a convergence test for the NIIT step, ACA and Social Security cases with their own convergence tests; before/after fixture. | Phase 1 (IRMAA MAGI only) and phase 2 (NIIT, ACA MAGI, Social Security taxation) merged with re-pinned goldens (pinned separately if WI-002(c) so decides); CAPITAL_GAINS_IN_AGI.md updated; planner sign-off before re-pin and CPA review of phase-2 sample outputs recommended. |
| WI-025 | Unit test: kill member 2 first, basis_free equals 50% of balance; compare with member 1 dying first. | Both death orders give the same step-up on a joint account. |
| WI-026 | Convert a legacy fixture, delete all liabilities, run trends metrics, assert legacy client_files is ignored; update the pinned tests. | No code path reads removed fallbacks; conversion still works. |
| WI-027 | Closed-form tests at AMTI 1.2M and 2.0M for 2025 and 2026; pin tests for 2026 notices; hand-computed estate cases. | Values match primary sources; dashboard rows carry source and date. |
| WI-028 | Search shows no readers of the key; schema and blank-plan tests pass. | Lever gone; saved plans migrate cleanly. |
| WI-029 | Injected raising stubs assert logging or surfacing; ratchet test. | No silent swallow in planning_engines.py or projection_stages without a logged fallback. |
| WI-031 | Tests fail when the handlers are removed. | Each handler group has a behavioural test. |
| WI-032 | Every golden-master changelog entry since 2026-09 maps to a note or an explicit 'no user-visible change'. | Index lists every note. |
| WI-033 | Read-through by a non-expert over a short page list. | Pages used before the first build have plain-language summaries. |
| WI-030 | Scenarios produce validation failures and a depletion year; pin test fails when withdrawal order is deliberately changed on a scratch branch. | Shortfall branches have end-to-end anchors. |
| WI-036 | Paired-path harness n>=1000, several seeds, three Roth regimes (none, fill_to_bracket, optimize_terminal_tax), 4+ shapes, on the replay headline path; /signed gap/ within the disclosed tolerance in each regime; the tier-shadow secondary figure measured separately (static recommendation; not run in this review). | Disclosed tolerance holds for all three regimes in the default test tier, or a repair item is raised with the measured gap. |
| WI-035 | Playwright navigation across all steps before and after; guard tests updated. | No wrapper chain remains; script order no longer carries meaning. |
| WI-034 | Golden-master and invariant tests unchanged byte for byte. | Large functions split; no pin changed. |
| WI-037 | Static import check; golden pins unchanged. | Circular dependency removed. |
| WI-038 | Migration test on a legacy fixture; backup/restore round trip. | Single persistence family; legacy DB no longer written. |

### System acceptance criteria

- No tracked file under financial_trends_reporter/data other than .gitkeep; the hygiene test fails on a dummy backup; the owner's history decision is recorded.
- The release gate's collected-test count equals the project's default-tier pytest count within a stated floor, and the governance, provenance, date-seam and hygiene guards are among the tests it runs.
- Server mode returns an error for a spoofed Host header and refuses to start on a non-loopback host without an access token; desktop mode behaviour is unchanged.
- Closed-form tax cases pass: qualified dividends plus a realized gain stacked together at 0/15/20%, at every call site; the IRMAA tier two years later with a brokerage gain (phase 1); same-year NIIT with a convergence test, Social Security taxable share and ACA MAGI (phase 2); equal step-up for either spouse dying first.
- Before/after golden movements are recorded with reasons; planner sign-off on the closed-form tests and impact tables precedes every re-pin, CPA review of sample outputs is recommended for FIN-001 phase 2 and not blocking for FIN-003; FIN-001 and FIN-003 are released together; no pin changes during the wave 5 refactors.
- Paired-path agreement for several household shapes under none, fill_to_bracket and the shipped default optimize_terminal_tax stays within the disclosed tolerance on the replay headline path; the KPI label reflects the measured regime, each displayed figure carries its own success definition, and the secondary within-tier figure stays flagged approximate.
- Limitation notices for FIN-001, FIN-003, FIN-004 and FIN-010 appear in Wave 1 and each is removed when its fix ships.
- Importing nan, inf, (5,000) and garbage never empties liabilities and produces a row-level error; a forced failure in a derived-result step produces a log record and a visible warning.
- Staged edits survive every add, delete and import action; the build overlay never claims a cancel that did not occur; every server-flagged field is visibly and programmatically marked.
- Keyboard walk reaches every interactive element in DOM order; custom controls show a visible focus indicator at 3:1 or better; admin controls have accessible names.
- Documentation: every spec has a verified status in the right tier, the path-citation test passes, and the README instructions match on-screen names.
- All claims about rule values are backed by a recorded primary source, retrieval date and verifier.

## 11. Assumptions and open questions

**Technical**

- The stale-balance scenario in ARC-004 requires the legacy client_files table to stay populated after conversion; this was not verified.
- Whether a hidden consumer of config_contract_warnings exists (one test file was not opened) is unknown (ARC-003).
- Whether `reference.db` matches `reference_src` was not checked. The Monte Carlo diagnostic's addendum (section 7) and the current `monte_carlo` call show the headline moved to the replay allocation after the measured gaps; the git history of `src/planning_engines.py` is a single squashed commit, so it cannot date content. Whether the displayed headline matches the diagnostic's 'shipping engine' success definition, before or after the replay change, was not confirmed.
- Documents disagree on the Monte Carlo bias direction. The diagnostic's figures describe the pre-replay tier path under roth_policy=none and roth_policy=fill_to_bracket (which it calls 'default'); the shipped default, optimize_terminal_tax, is unmeasured; all three regimes need re-measurement.
- The depth of the trends-reporter and frontend accessibility tests was not read.

**Jurisdiction and rule year**

- All tax findings are US federal unless stated; state rows (NC, IN, NY, CA) are state-specific. Federal 2026 tables are from the dataset; later years are extrapolated.
- FIN-001, FIN-003, FIN-008 and FIN-010 concern statutory structure (IRC 61, 86, 1(h)(11), 1411, 1014); FIN-005, FIN-009 and FIN-011 depend on 2026 parameters under the 2025 reconciliation act (P.L. 119-21) as recalled by the expert, not fetched.

**External facts to verify (not fetched in this run)**

- 2026 AMT exemption phase-out start and rate (FIN-005).
- 2026 QLAC and QCD limits (FIN-011).
- 2026 NC and IN rates, NY estate exemption and brackets, CA surcharge, Part D base premium, Social Security wage-base status, SSA mortality (FIN-006).
- Federal estate exemption and portability treatment, including that the combined $30M exemption presumes a timely portability election (FIN-009).
- Current ACA enhanced-subsidy law.
- The federal 2026 tables are described as 'verified' only in the sense of the dataset status and the expert's recollection of the cited IRS and CMS documents; they were not re-fetched.

**Professional review required**

- Review rule (one rule): planner sign-off on the closed-form tests and impact tables is required before any golden re-pin for FIN-001 and FIN-003. CPA review of sample outputs is recommended but not blocking for FIN-003, and recommended for FIN-001 phase 2 (ACA and Social Security).
- CPA or tax preparer: required for the rule values in FIN-005, FIN-006 and FIN-011 before they change.
- Estate attorney: FIN-009 portability and credit-shelter treatment.
- Benefits counselor or CPA: FIN-004 and FIN-007 exceptions and claim-age advice.
- Nothing in this report is legal, tax, fiduciary or benefits advice.

**Rule authority table (FIN-001 to FIN-011).** Authority classes follow the governance reference: authoritative, secondary, user-provided, unverified. Nothing in this table is legal, tax, fiduciary or benefits advice.

| Finding | Jurisdiction | Rule year | Rule status | Authority class | Professional review |
|---|---|---|---|---|---|
| FIN-001 | US federal (IRC 61, 86, 1411, 36B; 42 USC 1395r(i)) | Statutory; dataset covers 2024-2026, later years extrapolated | Statutory structure hard-coded; thresholds sourced from the dataset; documented owner deferral | Secondary (the repository's own design note), unverified externally | Planner sign-off required before re-pin; CPA review of sample outputs recommended for phase 2 (ACA, Social Security) |
| FIN-002 | Not jurisdiction-specific | Not applicable | Modeling approximation; tolerance label assumed from one fixture | User-provided (the repository's archived diagnostic; not re-run) | Planner review of the displayed success definitions; no legal review |
| FIN-003 | US federal (IRC 1(h)(11)) | 2026 thresholds in the dataset (dataset status 'verified', not re-fetched); later years indexed | Structure hard-coded; thresholds sourced | Authoritative statute; dataset status secondary | Planner sign-off required before re-pin; CPA review recommended, not blocking |
| FIN-004 | US federal (IRC 72(t)) | Statutory | Not modeled; scope undeclared | Unverified (exceptions not fetched) | Yes, for exceptions, if early retirement is in scope |
| FIN-005 | US federal (IRC 55 as amended by P.L. 119-21) | 2026 onward; code uses 2025 | Hard-coded base-year constants | Unverified (expert recollection) | Yes (CPA) before change |
| FIN-006 | US states NC, IN, NY, CA; SSA; CMS Part D | 2026; several rows tagged 2024 or earlier | Sourced dataset rows plus hard-coded schedules in core.py; some rows 'assumption' | Unverified (expert recollection; dataset flags state_tax for review) | Yes |
| FIN-007 | US federal (42 USC 403(b)) | Annual thresholds; none in the dataset | Not modeled; insufficient evidence | Unverified | Benefits counselor or CPA if confirmed and in scope |
| FIN-008 | US federal (IRC 86) | Statutory | Configurable input that the engine does not read | Authoritative statute for the engine formula | None for removing the lever; planner reviews wording |
| FIN-009 | US federal (IRC 2010, 2631, 2010(c)(5)) | 2026; presumes a timely portability election (default on) | Configurable input (default $30M); credit-shelter arithmetic hard-coded | Unverified (expert recollection; arithmetic reading) | Estate attorney required |
| FIN-010 | US federal (IRC 1014(b)(9), 2040(b)) | Statutory | Titling configurable per account; step-up fraction logic hard-coded | Secondary (code reading), unverified externally | Tax professional for titling advice; planner sign-off before re-pin |
| FIN-011 | US federal (IRC 401(a)(9)(H), 408(d)(8), 221) | 2025 base extrapolated to 2026 onward | Hard-coded base with assumed inflation | Unverified (expert recollection) | CPA verification (WI-003) |

**Open questions for the owner**

- Is the repository remote public, shared or private, and who holds clones?
- Is retiring before 59.5 a supported scenario? Is the earnings test in scope?
- Which Monte Carlo success definition is the headline: 'funded as asked' (as the diagnostic addendum records) or 'funded within tier buckets', and does the secondary 'without using Roth for extras' figure stay on the tile? This is a definitional choice, not a bias to remove (owner approval required).
- Is the vendor name intentionally hidden in the UI (affects README wording)?
- Is server mode needed beyond debugging?

## 12. Review limitations

CI was intentionally excluded from this review.

Runtime behavior was not validated during this review.

- **Static only.** No tests, builds, application runs, rendering, screen-reader checks or contrast measurements. Every dollar impact and performance remark is an estimate from reading.
- **GitHub unavailable.** Issues, pull requests, releases, tags, collaborators, teams, repository visibility and secret scanning could not be read (the orchestrator re-tried). Merged pull request numbers come from local commit subjects; the local remote-tracking ref was not re-fetched; default branch is inferred. Empty GitHub lists in the manifest mean unchecked.
- **Secret scanning not run**, and no local pattern scan was substituted, so the absence of secrets is unverified. The tracked backup's contents were not opened by any reviewer; the sensitivity claim rests on the repository's own ignore-file comment and the file's key structure as described by the quality expert. No values are reproduced in any artifact.
- **Not read in depth:** most projection stage bodies, the optimizers, market data, YTD tracking, spending tracker, reporting sheets, csv_exchange commit logic, legacy conversion steps, plan_store, the backup scheduler, the Monarch extractor body, the trends HTTP app, packaging files, rental and equity-compensation logic beyond the cited lines, and about two thirds of the frontend modules.
- **Frontend:** about 39.7k lines; read in parts. Page-level behavior, bundle size and load time were not measured.
- **Tests:** about 563 Python test files, 91 Node tests and 19 end-to-end specs were assessed by pattern scans and targeted reads, not in full; coverage claims use name searches and under-count indirect execution.
- **External rule values** (section 11) were not fetched; FIN-005, FIN-006 and FIN-011 rest on expert recollection and need verification.
- **Documentation:** the Concepts Guide was inspected as extracted XML only; documentation/archive was excluded by folder rule and not opened; about 8 of ~35 pages of in-app help were read.
- **Dropped observations:** two architect observations (ARC-006, ARC-008) were removed by an automated keyword filter before synthesis. Their evidence was not part of the inputs to this stage, so they are not in the register and are not assessed (section 13).
- **Verification depth:** several verifiers re-read only parts of the cited evidence; each verification note in section 5 states what was and was not reopened. Seven findings remain insufficient_evidence.
- **Stale-risk:** the Monte Carlo diagnostic's body is dated 2026-09-30 and its addendum records a later fix; the performance baseline is dated 2026-09-17. The git history of `src/planning_engines.py` is one squashed commit, so it cannot show what changed when.
- **Partial financial review:** optimizers, the inherited-account and 10-year heir-tax branch, remarriage and divorce, rental and equity-compensation logic, the Social Security funding-discount assumption and PIA derivation, return and inflation assumptions, and the ACA enhanced-subsidy default were not read; the planner sign-off does not cover them (section 14).
- Nothing here supports a claim that the system as a whole is healthy. Areas without findings are only "not found in what was read".

## 13. Finding disposition appendix

No finding was refuted or superseded. The entries below are duplicates, insufficient-evidence items and dropped observations that a reader might otherwise look for.

| ID | Title | Severity | Disposition | Reason | Follow-up item |
|---|---|---|---|---|---|
| ARC-002 | Headline Monte Carlo result comes from an approximate vectorized engine whose parity with the exact engine is only checked nightly on one fixture | medium | duplicate | Duplicate of FIN-002: same defect (default vectorized Monte Carlo engine). FIN-002 is retained (partially confirmed after planner re-verification) and carries the quantified pre-fix gaps; ARC-002's default-tier parity fixtures, scalar spot-check and kernel-sharing options were merged into it. | WI-009, WI-036, WI-037 |
| DOC-008 | In-app page help is dense with tax and planning jargon aimed at an expert reader | low | insufficient_evidence | The verifier did not open the STEPS help strings. The finding admits partial inspection of about 8 pages, and the audience judgment is subjective. DOC-004 already covers the lack of linkage to the guide, so the remainder is a design preference. | WI-033 |
| DOC-009 | Tracking numbers mix two namespaces and the backlog states no GitHub tracker exists | low | insufficient_evidence | The verifier did not open BACKLOG.md or the w0-preflight file. The claim that '#NNN' mixes issue, item and PR namespaces rests on commit subjects only and GitHub was unreadable. Commit subjects such as '(#223)' match the PR style, but the overlap is unproven. | WI-016 |
| FIN-007 | The retirement earnings test is not modeled and nothing warns when Social Security is claimed before full retirement age while wages continue | low | insufficient_evidence | The verifier did not open income.py:322-396 or the archived review row, and could not substantiate that the earnings test is absent or that no warning exists. Even on its own terms it is an undeclared-scope gap with low impact. Treated as insufficient evidence. | WI-002, WI-010 |
| UX-005 | Text-size control and responsive layout do not support larger text or narrower windows well; many small fixed font sizes | low | insufficient_evidence | The verifier did not open the grid minimums, font-size counts or text_size.js, and the finding itself says it was not rendered or measured. The overflow claim rests on an unverified layout calculation, so severity low and confidence low; disposition insufficient_evidence. | WI-014 |
| UX-009 | Save-model badge and 3-way unsaved guard are enforced only for left-nav clicks | low | insufficient_evidence | The verifier did not open the navigation.js click-handler or history code. The claim that Back/Forward and window.setStep bypass the save guard is unverified, and the finding admits edits stay in the dirty map, so the impact is small. | WI-021 |
| UX-012 | Report charts expose only a title to assistive technology | low | insufficient_evidence | The verifier did not open reports_ui.js or the chart builders. The finding is self-labelled partially inspected and the detail tables, a possible mitigation, were not checked. | WI-021 |
| UX-013 | Status toast is fixed over the sticky header and persistent errors/warnings can cover header actions | low | insufficient_evidence | The verifier did not open the toast CSS or position. Overlap with the header Save button depends on layout that was not rendered or measured. The finding is self-labelled partially inspected. | WI-014 |

**Dropped before synthesis (not in the register).**

| ID | Title (as reported) | Disposition |
|---|---|---|
| ARC-006 | The 14-stage projection pipeline is a descriptive facade over one engine call | Removed by an automated keyword filter that matched a word in the title. No evidence text was available at this stage, so it is neither confirmed nor assessed. Recommend the architect re-submit it. |
| ARC-008 | State income tax schedules and the estate credit table are embedded in code, outside the reference-data pipeline | Removed by the same filter. The embedded California and New York schedules and the dated-row recommendation overlap with FIN-006 and FIN-005, which remain in the register. Recommend re-submission. |

**Claims narrowed during verification (findings retained).**

| Finding | Narrowing |
|---|---|
| ARC-009 | The reverse-proxy wrapper is conditional on a setting that defaults to off; the finding overstated it. |
| QA-003 | A "nan" liability balance does not empty the list; it becomes a NaN row. The silent-empty path is triggered by parse errors such as parenthesised numbers. |
| QA-007 | The block at planning_engines.py:2474 looks like diagnostic trace recording, not cap sizing; the senior-deduction swallow is the real numeric risk. |
| FIN-001 | Calibrated from high to medium: an owner-approved, documented deferral, and LTCG tax itself is stacked correctly. |
| FIN-004 | Existing frontend help text mentions early-withdrawal penalties, so "no warning anywhere" is overstated; the 10% additional tax is still not modeled. |
| UX-003 | Help opens on field focus, so keyboard users still get the text; the badge itself is still not operable. |
| DOC-001 | Narrowed by the orchestrator: CAPITAL_GAINS_IN_AGI.md section 5 correctly states that brokerage gains remain excluded; only section 1 is stale for home/rental sales. |
| ARC-002 | Claim that users cannot tell the figure is approximate is contradicted by the tolerance label and the second displayed figure on the tile (FIN-002 evidence). |
| FIN-002 | Lowered from medium to low and from confirmed to partially confirmed at planner re-verification: the +17/-5pp gaps describe the superseded tier path, the shipped default regime is unmeasured, and the Roth/tier-bucket difference is definitional. |

## 14. Financial planner sign-off

**Planner verdict: approved-with-changes** (material changes: yes). The planner confirmed the central tax findings in source: qualified dividends flow into AGI and are taxed by the ordinary-bracket loop (roth_conversion_and_agi_tax.py:171,130; core.py:842-851); the cascade's brokerage gain reaches NIIT only through state.agi, which excludes it, and only the home or rental sale gain is added to IRMAA MAGI (deterministic_engine.py:1236-1241); CAPITAL_GAINS_IN_AGI.md section 5 records the brokerage-gain deferral; the survivor step-up asymmetry and the estate-exemption arithmetic follow from the code. Severities, counts and the dispositions of the duplicate and insufficient-evidence entries were found internally consistent. The planner requested eight changes. Each was re-verified (material ones) and then applied, partly applied or not applied as set out below.

**Scope of this sign-off.** The financial review is partial. The sign-off covers the findings and the plan as written. It does not certify the correctness of areas that were not read: the optimizers, the inherited-account and 10-year heir-tax branch, remarriage and divorce, rental and equity-compensation logic, the Social Security funding-discount assumption and PIA derivation, return and inflation assumptions, and the ACA enhanced-subsidy default. FIN-001 and FIN-003 partly offset (tax overstated versus MAGI-keyed rules understated), so fixing only one changes the net error and neither should be released alone. Federal 2026 tables are described as 'verified' only in the sense of the dataset status and the expert's recollection; they were not re-fetched.

### Requested changes and resolution

| ID | Material | Requested change (summary) | Re-verification | Resolution |
|---|---|---|---|---|
| PC-1 | Yes | Correct the FIN-002 evidence framing: (a) rename the 'default policy' regime, (b) state the Roth/tier-bucket difference is definitional, (c) account for the second displayed figure, (d) say the diagnostic is probably still representative | Partially upheld: (a), (b), (c) supported; (d) rejected | Applied (a), (b), (c). (d) not applied and replaced (see below). FIN-002 lowered to low and partially confirmed. |
| PC-2 | Yes | Fix the FIN-001 phasing: NIIT is a same-year tax, only IRMAA MAGI is a lookback item | Upheld | Applied in FIN-001, section 6, WI-024 and the validation rows. |
| PC-3 | Yes | Decouple limitation notices and first tax measurements from WI-003; split WI-010 | Partially upheld: (a) and (c) supported, (b) in reduced form; the claim that FIN-001 severity depends on the notice is not supported | Applied (a), (b) as WI-010a, (c) as the reduced WI-010. Severity link recorded as dissent, not adopted. |
| PC-4 | No | Reconcile professional-review statements for FIN-003 | Not required (non-material) | Applied: one review rule stated in FIN-001, FIN-003, WI-023, WI-024, section 10 and section 11. |
| PC-5 | No | Make the FIN-003 fix scope explicit (cascade call site, callers, NII, closed-form test) | Not required | Applied in FIN-003, WI-023, section 8 and the acceptance criteria. |
| PC-6 | No | Phrase rule-authority claims conditionally; add a consolidated FIN-001 to FIN-011 table | Not required | Applied in FIN-005, FIN-006, FIN-009, FIN-011; table added in section 11. |
| PC-7 | No | FIN-009: portability assumption and CST double-count note | Not required | Applied; severity stays low, confidence low, attorney review required. |
| PC-8 | No | Scope the sign-off statement; FIN-001 and FIN-003 offset | Not required | Applied in sections 1, 4, 12 and this section. |

### Resolution and impact analysis for the material changes

**PC-1 - FIN-002 evidence framing (partially upheld).**

- **Applied (a):** the diagnostic table labels the -5/-6pp rows 'default `roth_policy=fill_to_bracket`' and states that other policies were not run (diagnostic lines 14, 16, 111). The shipped default is `optimize_terminal_tax` (src/parsing/roth_conversion_policy.py:59-62; src/taxes.py:450), which was never measured. The regime is renamed in the executive summary, FIN-002, Conflicts 1 to 3 and the section 10 criteria, and the finding states that the shipped default is unmeasured.
- **Applied (b):** the diagnostic (line 68) calls the Roth/tier-bucket difference 'a definitional difference in what success means, not an approximation error'. FIN-002 now treats it as a metric-definition choice for the owner (WI-002(d)), not a bias to remove.
- **Applied (c):** the code emits both the headline (funded as asked, Roth as a last resort) and `success_rate_within_tier_policy` (src/planning_engines.py:6765-6777); the KPI tile appends 'without using Roth for extras' with an 'Approximate' tooltip, and hides it when a spending policy is active (frontend/js/dashboard_decomp_home_panels.js:28-55). The earlier 'disclosure is symmetric' claim is withdrawn; Conflict 2 and WI-009 are restated as per-figure disclosure with the tolerance label tied to a measured regime.
- **Not applied (d):** the proposed statement that the diagnostic is 'probably still representative' because git shows no later change to src/planning_engines.py was rejected. The diagnostic's section 7 (lines 112-125) says the fix shipped after the diagnostic body (headline `allocation='replay'`, credit-shelter sequestration, tier cascade kept as a shadow), and the current code matches: `monte_carlo` calls `_mc_vectorized_batch(..., allocation='replay', tier_shadow=True)` (src/planning_engines.py:6654) and the sensitivity helper also uses 'replay' (line 6228); the 'tier' default at line 5414 applies only to direct callers. The git argument is uninformative because `git log` for the file returns a single commit (d171d0b) that adds the whole file, so absence of later commits says nothing about content. The +17/-5pp gaps therefore describe the superseded tier path. The post-fix paired figures (none 0.650 vs 0.611; default 0.675 vs 0.675; agreement 95.5-100%) are the diagnostic authors' and were not independently verified here. Whether the displayed headline matches the diagnostic's 'shipping engine' success definition, before or after replay, was not confirmed.
- **Impact on findings:** FIN-002 title, observed behavior and impact no longer claim '17pp too high' or '26pp too low' as current exposure; the recommendation changes from proposing the replay skeleton as future work to verifying the shipped replay result and the tile labels; severity is lowered from medium to low and status from confirmed to partially confirmed (planner confirmation of the lower severity is pending, see dissent). The residual risks are the unmeasured `optimize_terminal_tax` regime, a '+/-tol' label from one fixture, the approximate secondary figure, and nightly-only parity. ARC-002 stays a duplicate; its nightly-only and missing default-tier fixture evidence remains valid.
- **Other items touched:** executive summary items 3 and 4; coverage rows for the calculation engine, Monte Carlo and financial logic; the section 4 financial row; section 6 Monte Carlo theme; WI-002(d), WI-009 (effort S to M, now measures the shipped default in Wave 1), WI-036 (effort L to M, high to low risk, now 'verify and broaden coverage, measure `optimize_terminal_tax`'); section 10 rows and criteria; waves W1-F and W4-A.
- **Validation added:** a paired-path run under `optimize_terminal_tax` alongside `none` and `fill_to_bracket`, on the post-replay headline path and on the tier shadow for the secondary figure. These are static recommendations; no run was executed.

**PC-2 - FIN-001 phasing (upheld).**

- NIIT is a same-year tax computed inside the cascade fixed-point loop (src/projection_stages/withdrawal_cascade_investment_tax.py:225-235; `niit_tax` at src/core.py:1153-1155 is max(0, min(NII, MAGI minus threshold)) x 3.8%, and its delta feeds the gap). Adding the realized gain to its MAGI raises NIIT, which raises the gap, which realizes more gain, so it needs the same convergence re-verification as ACA and Social Security. Only IRMAA MAGI has the two-year lookback.
- **Applied:** phase 1 is IRMAA MAGI only (lookback, simple, no cascade convergence exposure); phase 2 is NIIT, ACA MAGI and Social Security taxation (same-year, convergence test). Updated in FIN-001 option 2, recommendation, implementation considerations, risk and verification method; the section 6 tax-correctness row; WI-024 (description, owner, risk, validation, exit criteria); WI-002(c); WI-022 (reports the IRMAA-only and NIIT effects separately); and the acceptance criteria.
- **New validation:** a NIIT same-year closed-form case (230k AGI plus a 100k gain gives 3.8% x min(NII, 80k)) and a convergence test for the NIIT step in WI-024; the IRMAA-two-years-later case stays in phase 1.
- **Effects:** phase 1 effort is S to M and risk low to medium; phase 2 and the item overall stay L and medium to high. Re-pin count in section 6 becomes three to four if phase 1 is pinned separately (decision in WI-002(c)). WI-025, WI-036, WI-032 and DOC-001 cross-references are unaffected.
- **Status note:** the two re-verification outcomes disagreed on FIN-001's status (confirmed after PC-2, partially confirmed after PC-3); the more conservative partially confirmed is kept, because the ACA, Social Security and senior-phase-out claims were not independently traced. Severity stays medium.

**PC-3 - decouple notices from WI-003 (partially upheld).**

- **Evidence:** WI-003 covers AMT, QLAC, QCD, state rows, NY estate exemption, Part D, wage base and mortality (FIN-005, FIN-006, FIN-011); none of those are inputs to FIN-001 or FIN-003. The FIN-001 and FIN-003 fixes are statutory-structure fixes that use the 2026 federal tables (brackets, standard deduction, LTCG, IRMAA tiers) that reference_src/tax_update_dashboard.csv marks 'VERIFIED 2026-09-29'; this is consistent with dataset status and was not re-fetched here. The dashboard marks the state_tax family REVIEW_REQUIRED_BY_STATE and blocking, which supports gating only the state notices on WI-003.
- **Applied (a):** WI-003 is removed from the WI-022 dependencies; WI-002 stays for the FIN-001 phasing decision. WI-022 stays in Wave 2 (W2-ENG); the artificial wait on the external CPA task is gone.
- **Applied (b), reduced form:** WI-010 is split. New WI-010a (Wave 1, W1-G, P1, effort S, no dependencies) carries the brokerage-gain MAGI limitation (FIN-001) and qualified-dividend overstatement (FIN-003) notices at P1, and the pre-59.5 warning (FIN-004, scope-neutral wording) and survivor step-up notice (FIN-010) at P2 within the item. Each notice has a retirement trigger (WI-023, WI-024, WI-025, or WI-002(a)). FIN-003 and FIN-010 notices are justified as honest disclosure rather than as high-priority fixes (FIN-003 is conservative; FIN-010 is low severity with an S-effort fix).
- **Applied (c):** the reduced WI-010 (P2, depends on WI-002 and WI-003) keeps the earnings-test (FIN-007, confirm first), single-person estate (FIN-009, after WI-002(e)), and AMT and state-data (FIN-005, FIN-006) notices. FIN-007 stays out of WI-010a because it is insufficient evidence.
- **Not adopted:** the planner's statement that FIN-001's medium calibration depends on the notice shipping early. The recorded calibration rationale (an owner-approved, documented deferral; LTCG tax itself stacked correctly) does not cite a notice, and CAPITAL_GAINS_IN_AGI.md is documentation, not a user-visible notice. The notice is added as a mitigation, not as a condition of the severity; the planner's position is recorded as dissent.
- **Effects:** the executive summary and FIN-001 'in the meantime' promise is now deliverable in Wave 1; linked items for FIN-001, FIN-003, FIN-004 and FIN-010 point to WI-010a; section 7 and section 10 are updated. This was a static read: the preflight code was not opened to confirm where the notices can be placed.

### Non-material changes

- **PC-4 (applied):** one rule - planner sign-off on the closed-form tests and impact table is required before re-pin; CPA review of sample outputs is recommended but not blocking for FIN-003, and recommended for FIN-001 phase 2 (ACA and Social Security).
- **PC-5 (applied):** FIN-003 now states that qualified dividends sit in the preferential stack below realized gains; the cascade call at withdrawal_cascade_investment_tax.py:234, the `ltcg_marginal_rate` callers and the Roth cap callers change in the same patch; qualified dividends stay in NII for NIIT; and the closed-form test covers dividends plus a gain together.
- **PC-6 (applied):** FIN-005, FIN-006, FIN-009 and FIN-011 now phrase legal values conditionally and classify authority as unverified; section 11 carries the consolidated table of jurisdiction, rule year, rule status, authority class and review requirement for FIN-001 to FIN-011.
- **PC-7 (applied):** FIN-009 states that the combined $30M exemption presumes a timely portability election (model default `federal_portability_enabled` True, src/after_tax.py:772) and records the planner's reading that the credit-shelter double count (after_tax.py:751-774) understates tax under both settings when the CST is smaller than the first decedent's exemption. Severity low, confidence low, attorney review required.
- **PC-8 (applied):** see the scope statement above and sections 1, 4 and 12.

### Unresolved dissent

1. **FIN-001 severity.** The planner originally rated it high and accepts medium only if the limitation notice ships in Wave 1 (WI-010a). The error is optimistic, touches IRMAA, NIIT, ACA and Social Security together, and affects essentially every plan that draws on taxable holdings. If the notice slips past Wave 1 the planner would restore high. Re-verification found no basis for making the calibration conditional, so medium stands with the notice as a mitigation. This is unlikely to be fully resolved because the owner chose to defer the fix.
2. **FIN-002 severity and priority.** The planner would put the Monte Carlo repair (WI-036) ahead of the other engine refactors and was concerned about a signed gap of up to +17pp in the headline. Re-verification shows that gap belongs to the superseded tier path, so the item shrank to verification and the shipped-default measurement moved into WI-009 (Wave 1). Open: the planner has not confirmed the lowering of FIN-002 to low; if the measurement of the replay headline or of `optimize_terminal_tax` shows a gap beyond the tolerance, severity returns to medium. The tier-bucket definition (WI-002(d)) needs an owner decision, so some disagreement may persist.
3. **FIN-004 severity.** Low is accepted only while pre-59.5 retirement is undeclared scope. For any plan with pre-tax draws before 59.5 the planner would rate it medium, because the 10% additional tax is not modeled and there is no age gate. This depends on the scope decision (WI-002(a)); the interim notice is in WI-010a.
4. **External verification.** FIN-005, FIN-006, FIN-009 and FIN-011 depend on verification by a CPA or attorney that this review cannot perform. They remain unresolved until WI-003 and the estate review are done.
5. **'Verified' federal tables.** The planner accepts the report's description of federal 2026 tables as verified only as 'consistent with dataset status, not re-fetched'; the wording has been changed accordingly and nothing further is outstanding.
6. **Rejected change.** PC-1(d), the statement that the diagnostic is probably still representative, was rejected on re-verification (see above) and is recorded here rather than applied.
