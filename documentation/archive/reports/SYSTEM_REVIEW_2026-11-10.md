# System Review — Retirement Planning System (2026-11-10)

Repository `matthartzman/retirement_system`, reviewed ref `fix-401k-hsa-agi-and-cash` @ `e75d6ac159210dc5127e8c42f5a71b41689f8a1f`. Scope: the entire system, with close attention to usability science. Depth: standard. Financial-planner sign-off applied: approved with changes (Section 14).

## 1. Executive summary

**Assessment.** The system is a mature, heavily tested, single-household planning application with deliberate work on security, plain-English help and accessibility. This static review found **37 material findings** (0 critical, 2 high, 18 medium, 17 low) after adversarial verification, plus one cross-expert duplicate. No finding is critical. The two high findings both affect how a new or partly completed plan is handled. Most medium findings fall into four themes:

1. **Silent defaults and validation gaps.** Blank or unreadable plan values become specific dollar figures that look like one real household's data, for example a $293,284 mortgage at 1.99% through 2034 (QA-001). Builds start without checking preflight blockers. Grid saves after Start New Plan probably fail until every required field is filled, although that was inferred statically and not run (QA-002). The 114 'dollars' fields are not format-checked (QA-003).
2. **Tax-engine simplifications in the federal deductions and the Illinois S-corp replacement tax.** The federal items understate federal tax: the QBI deduction without its statutory limits (FIN-001), SALT computed from AGI times a flat state rate, mainly in the 2025-2029 enhanced-cap window (FIN-003), a misapplied senior-deduction phase-out (FIN-002) and a self-employed health insurance double count (FIN-006). The missing Illinois replacement tax (FIN-008) is an entity-level state tax: leaving it out understates Illinois tax and, because the S corporation deducts it, slightly overstates federal taxable income. Estate figures may be overstated for Illinois estates of $4M-$5M (FIN-004, which needs attorney confirmation), and because the estate penalty feeds the Roth optimizer's score, this can also change which conversion schedule is recommended. Some estate-related outcomes are left out or simplified without telling the user (FIN-005; FIN-007, which also covers the missing IRC 2058 deduction for state estate tax).
3. **Error prevention and feedback on irreversible financial-record actions.** Native OK/Cancel dialogs understate permanence, and two guards fail open (UX-002). A void message promises a Restore that the app then refuses (UX-001). Status and error announcements are unreliable for screen-reader users (UX-003). Automatic backups can miss committed data, and schema upgrades leave no copy to roll back to (ARC-004).
4. **Maintainability and documentation drift.** The engine's core is a 1,700-line closure-heavy function behind wildcard imports (ARC-001). Layering is inverted in the housing and holdings modules (ARC-002). The frontend size guard is raised during feature work (ARC-005). Warnings bypass app.log (ARC-003). Help text, the README and the Concepts Guide still point to retired pages (DOC-001 to DOC-003). Document status lines (DOC-004) and the backlog (DOC-006) are out of date.

**Risks.** The main risk is wrong but plausible-looking results: phantom mortgages from blank rows, understated tax in high-income working years and Roth-conversion years, and overstated Illinois estate tax. Recoverability is the second risk: hard deletes behind native dialogs, backups that are opt-in and not always consistent, and forward-only upgrades.

**Opportunities.** Most fixes reuse code that already exists, so they are smaller and safer than they look:
- `showInAppConfirm`, `slAnnounce` and the Sales Ledger tab pattern for the interface fixes.
- `plan_db_replace._backup_with_api` for consistent backups.
- The AST import method already used in `deterministic_engine.py` for removing wildcard imports.
- `tax_table_currency_warnings` for year-end currency warnings.

The usability fixes should shrink the frontend rather than grow it.

**Planner verdict.** Approved with changes. Six material changes (PC-01 to PC-06) were re-verified: four were upheld and two partially upheld, and the supported parts are applied. Five non-material wording changes (PC-07 to PC-11) are applied. The sign-off depends on the CPA and estate-attorney gates in Section 11. It is not a professional confirmation of any rule value, because no primary sources were fetched. Planner dissent on FIN-003 severity and FIN-004 priority remains unresolved (Section 14).

**Top recommendations.**
1. **Stop silent household-specific defaults and gate builds.** Make blank mean zero or the schema default, make unreadable money values errors, and refuse /api/build/start while preflight blockers exist (QA-001, W1-04). Then relax save-time 'required' validation so Start New Plan works step by step (QA-002, W2-01), and validate the 114 'dollars' fields (QA-003, W2-02).
2. **Correct the federal deductions and the Illinois S-corp replacement tax in strict sequence.** Each fix gets a measured, hand-verified golden re-pin and the stated professional gates, with one batched CPA engagement for FIN-001, FIN-002, FIN-003 and FIN-008: Illinois replacement tax, QBI limits, SALT from the modeled state tax, the SEHI/medical exclusion, and the per-person senior deduction (FIN-008, FIN-001, FIN-003, FIN-006, FIN-002; W3-01 to W3-05). Ship the interim limitation notices, including the notice that the Illinois estate figure is an unverified approximation (FIN-004), and the corrected workbook text first, in one bundle (W2-03).
3. **Make irreversible financial-record actions recoverable and announced.** Use in-app confirmations that name the action and state permanence, make the guards fail closed, correct the void/Restore text, and add one persistent announce region (UX-001, UX-002, UX-003). Make backups consistent and keep a pre-upgrade copy before every schema migration (ARC-004).
4. **Lay cheap foundations before larger refactors.** Put every logger in the 'retirement_system' tree and log startup migration results (ARC-003), replace the wildcard imports (ARC-001 option 1), and add per-file frontend size caps with a recorded reason for any raise (ARC-005).
5. **Bring end-user help and tracking up to date.** Rewrite the stitched help records and add the headline-metric glossary entries (DOC-001), fix the README and Plan Status directions (DOC-002), and put every deferred or approval-gated item, including the CPA and attorney gates from this review, into BACKLOG.md (DOC-006) before archiving shipped plans (DOC-004).

## 2. Scope and methodology

| Item | Value |
|---|---|
| Scope | The entire system, with close attention to usability science |
| Review date | 2026-11-10 |
| Depth | standard |
| Repository | `matthartzman/retirement_system` (default branch `main`) |
| Reviewed ref / commit | `fix-401k-hsa-agi-and-cash` @ `e75d6ac159210dc5127e8c42f5a71b41689f8a1f` |
| Pull request context | PR #420 contains the reviewed commit and was merged into `main` on 2026-11-10 (merge `3c7bb121`). |
| Ref state | At synthesis the local checkout is `main` @ `3c7bb121`, clean. It differs from `e75d6ac1` only in four golden-fixture, test and changelog files (commit `11f6e809`, the golden re-pin), so `src/` and `frontend/` are identical to the reviewed commit. The reconnaissance passes read the working tree while those four files were uncommitted edits. |
| Runtime validation | None. This review is static and read-only. See Section 12. |
| Exclusions | Explicit scope exclusions are stated in Section 12 and apply throughout this report. |

**Roles and model tiers.** Capability tiers map to reasoning effort as follows: expert_reasoning = high, standard_reasoning = medium, recon = medium, synthesis = high, mechanical = low.

| Role | Charter | Tier |
|---|---|---|
| Architect | Architecture, efficiency, dead code, compatibility shims, modularity, coupling, data flow, performance | expert_reasoning (high) |
| Financial planner | Retirement, tax, benefits, healthcare, estate, survivor scenarios, domain correctness | expert_reasoning (high) |
| Usability / accessibility | Workflow, consistency, readability, accessibility, cognitive load, error handling | standard_reasoning (medium) |
| Documentation | Clarity for a 60-year-old non-expert, accuracy, discoverability, terminology | standard_reasoning (medium) |
| Quality | Test coverage, boundaries, regression risk, determinism, static test-quality assessment | standard_reasoning (medium) |
| Orchestrator (not an expert) | Recon, dependencies, deduplication, conflicts, synthesis, waves, validation | synthesis (high) |

**Phases.**
1. Repository resolution and access context.
2. GitHub work context.
3. Document and file inventory.
4. Three reconnaissance passes (engine/architecture/calculations; UI/workflows; tests/docs/data/config).
5. The shared system map and coverage matrix.
6. Five parallel expert reviews.
7. Adversarial verification of every finding.
8. Orchestrator synthesis (cross-expert deduplication, conflict resolution, implementation waves).
9. Financial-planner sign-off (approved with changes), re-verification of each material change, and application of the supported changes (Section 14).

**GitHub context.**
- The repository has **zero GitHub issues**, zero open pull requests, no releases and three `archive/*` tags.
- Pending or flagged work therefore comes only from merged PR descriptions (nine author-stated items) and in-repo trackers.
- A scope search matched 108 PRs. 30 were retrieved and 15 bodies were read.
- 16 merged PRs were treated as relevant: #420, #419, #418, #417, #390, #388, #387, #386, #385, #366, #268, #267, #259, #235, #234 and #233.
- Collaborator permissions could not be read (HTTP 403), and GitHub secret scanning is unavailable on this repository.
- GitHub metadata is used as context and provenance only. It never replaces file evidence.

Dispositions of every inspected issue, PR and flagged item are in Section 3.2.

## 3. Coverage matrix

Every area has an inspection status. "Inspected, no material finding" does not mean the area is healthy; see each area's residual uncertainty.

### 3.1 Area status

| # | Area | Status | Expert | Findings | GitHub items |
|---|---|---|---|---|---|
| 1 | Architecture, layering and module boundaries | finding identified | architect | ARC-001, ARC-002, ARC-005 | ENG-01, ENG-07, X-03, PR #390, PR #234 |
| 2 | Compatibility layers, legacy conversion and generated files | finding identified | architect | ARC-007, ARC-001 | ENG-10 |
| 3 | Dependencies and external integrations (market data, broker files, Monarch) | inspected, no material finding | architect | — | X-03 |
| 4 | Configuration and version surfaces | finding identified | architect | ARC-006 | X-01 |
| 5 | Persistence, schema migrations, import and export | finding identified | architect | ARC-004 | ENG-10 |
| 6 | Performance and computational efficiency | partially inspected | architect | ARC-007 | PR #388 |
| 7 | Privacy and security (local server, remote Trends access, secrets, exports) | inspected, no material finding | architect | ARC-003 | UIR-10 |
| 8 | Logging and observability | finding identified | architect | ARC-003 | ENG-03 |
| 9 | Calculation engine (deterministic year loop, withdrawal cascade, optimizers) | partially inspected | financial_planner | FIN-001, FIN-003, FIN-006, FIN-008, FIN-010 | ENG-04, PR #419, PR #420, ENG-01, Prior review FIN-001 (SYSTEM_REVIEW_2026-10-19), Prior review FIN-009 (CST double count) |
| 10 | Monte Carlo and capital market assumptions | partially inspected | financial_planner | FIN-012 | ENG-02, PR #416 |
| 11 | Financial logic: federal and state tax, IRMAA, AGI, capital gains, wash sales | finding identified | financial_planner | FIN-001, FIN-002, FIN-003, FIN-006, FIN-008 | ENG-05, ENG-06, PR #418, PR #420 |
| 12 | Canonical reference data currency (tax law, state tax, mortality, CMA) | requires external domain verification | financial_planner | FIN-011, FIN-004 | R-TDC-06, ENG-05 |
| 13 | Retirement income and withdrawal workflows (RMDs, Roth conversions, account sequencing) | inspected, no material finding | financial_planner | — | PR #419 |
| 14 | Tax planning workflows (Roth conversion, charitable giving, account tax basis, year-end) | partially inspected | financial_planner | FIN-002, FIN-003 | PR #386, PR #366 |
| 15 | Benefits workflows (Social Security claiming, pensions, annuities, employer plans) | partially inspected | financial_planner | FIN-010 | ENG-04 |
| 16 | Healthcare workflows (HSA, Medicare/IRMAA, ACA premium credits) | finding identified | financial_planner | FIN-006 | PR #420 |
| 17 | Estate, insurance and beneficiary workflows | finding identified | financial_planner | FIN-004, FIN-005, FIN-007 | — |
| 18 | Survivor and household-change workflows (death, filing status, spousal rollover, divorce) | finding identified | financial_planner | FIN-009, FIN-002 | PR #416 |
| 19 | Data integrity (missing, duplicate, stale, ownership, units) | finding identified | quality | QA-001, QA-005 | R-TDC-03, R-TDC-05 |
| 20 | Input validation (server field errors, client validation) | finding identified | quality | QA-002, QA-003 | — |
| 21 | Numeric precision and rounding (float engine vs Decimal boundaries, footing) | partially inspected | quality | — | ENG-08 |
| 22 | Dates, tax-year boundaries and frozen-today seams | partially inspected | quality | — | — |
| 23 | Error handling and failure behaviour (API error shapes, silent degradation) | finding identified | quality | QA-004, QA-001 | UIR-01, UIR-02, ENG-03 |
| 24 | Testing strategy, golden masters and regression baselines | finding identified | quality | QA-006, QA-002, QA-001, ARC-005 | R-TDC-01, R-TDC-02, R-TDC-08, R-TDC-09 |
| 25 | GitHub work context and author-stated pending items | partially inspected | quality | QA-006, ARC-005 | PR #418, PR #390, PR #366, PR #233, PR #388, PR #420 |
| 26 | User interface and interaction design (client dashboard) | finding identified | usability_accessibility | UX-004, UX-005, UX-006 | UIR-05, UIR-08 |
| 27 | Information architecture, navigation and wayfinding | inspected, no material finding | usability_accessibility | — | UIR-07, PR #390, PR #387, PR #385 |
| 28 | Usability science: cognitive load, progressive disclosure, learnability, consistency | finding identified | usability_accessibility | UX-002, UX-003, UX-005 | UIR-04, UIR-07 |
| 29 | Error prevention and recovery in irreversible financial-record actions | finding identified | usability_accessibility | UX-001, UX-002 | UIR-03 |
| 30 | Risk communication and comprehension of financial results | finding identified | usability_accessibility | UX-004 | PR #233 |
| 31 | Accessibility (keyboard, focus, semantics, screen reader, contrast, text size) | finding identified | usability_accessibility | UX-003, UX-005, UX-006 | UIR-04, UIR-06, UIR-08, UIR-09 |
| 32 | Secondary UI surfaces (Admin Control Center, Financial Trends reporter, Excel workbook) | partially inspected | usability_accessibility | — | UIR-09, UIR-10 |
| 33 | Terminology and inclusive language in UI and data | inspected, no material finding | usability_accessibility | — | R-TDC-07 |
| 34 | Contextual help, glossary and end-user documentation | finding identified | documentation | DOC-001, DOC-002, DOC-003 | PR #259, PR #267, PR #268, PR #235 |
| 35 | Design and implementation document status and eligibility | finding identified | documentation | DOC-004, DOC-007 | X-02, PR #391 |
| 36 | Developer and agent guidance documentation (CLAUDE.md, runbooks, backlog) | finding identified | documentation | DOC-005, DOC-006 | ENG-09, UIR-11, R-TDC-04, R-TDC-10, R-TDC-11 |

### 3.1a Evidence and residual uncertainty by area

**1. Architecture, layering and module boundaries** (finding identified; architect)

- src/projection_stages/deterministic_engine.py:91-1792 — run_deterministic_projection_stage — single function with 20+ nested helpers
- src/planning_engines.py:49-199 — re-export block, wildcard import, rmd_divisor rebinding, docstring breadcrumbs
- src/engine_kernels.py:19, src/reporting/workbook_common.py:16 — wildcard imports of core
- src/housing_comparison.py:53-57; src/housing/{api,optimizer,plan_variant,results}.py; src/housing/zip_screen/screen.py:14 — domain modules import from server_services
- src/server/workbook_routes.py:626 — src imports financial_trends_reporter.live_snapshot.classify_symbol
- documentation/reference/SYSTEM_ARCHITECTURE_DIAGRAM.md:39-50 — generated graph shows Core->Server Services and Core->HTTP Routes edges
- src/desktop_api.py:54-55,297-298 — Core->Routes edge is the in-process desktop adapter (acceptable host adapter)
- *Residual uncertainty:* No full import graph was computed. Edges were sampled by grep, so other inversions may exist. Whether the frozen exe bundles financial_trends_reporter (needed by /api/holdings/classes) was not verified.

**2. Compatibility layers, legacy conversion and generated files** (finding identified; architect)

- src/legacy_conversion/__init__.py:1-9 — removable module still present (2,993 lines), wired via src/server_services/conversion_service.py:49-50
- src/plan_data_migration.py:1-60,394-503 — at-rest migration plus parse-time migrate_sectioned_data still called at src/data_io.py:628 and src/domain_models.py:193
- src/detailed_results.py:944-996 — semantic model plus Excel parser fallback
- src/local_store.py:1-10,28-38 — legacy retirement_system_v10.db is imported once and no longer written (refutes the recon claim)
- documentation/reference/SYSTEM_ARCHITECTURE_DIAGRAM.md:1-5 — generated, with a do-not-hand-edit header
- *Residual uncertainty:* Generator freshness of the diagram and of reference.db/demo_seed.rpx was not checked (binaries not opened). The individual steps of legacy_conversion were not read.

**3. Dependencies and external integrations (market data, broker files, Monarch)** (inspected, no material finding; architect)

- src/market_data.py:41-64,555-596 — requests is optional, with a urllib fallback path
- src/broker_1099b/pdf_text.py:1-36 — pypdf is optional and raises a clear PdfUnavailable message
- Monarch Extractor/monarch_extract.py:15-25 — playwright import guarded; separate venv
- git status --ignored — Monarch Extractor/{.venv,monarch-browser,output,raw} and financial_trends_reporter/data/* are ignored, not tracked
- retirement_planner.spec:62-112 — hidden imports collect src submodules
- *Residual uncertainty:* Not having a requirements file for the Monarch venv is a reproducibility gap, not a runtime defect. The bodies of the broker parsers, the Monarch import modules and the provider error handling in market_data (35 broad excepts) were not read. Package-lock transitive deps were not inspected.

**4. Configuration and version surfaces** (finding identified; architect)

- src/version.py:4-9 — VERSION='12'
- main.py:97; src/server/__main__.py:16 — hard-coded v11 banners
- pyproject.toml:56; package.json:3 — 10.0.0
- tools/check_version_surfaces.py:30-37 — patterns miss the current stale strings
- frontend/admin.html:3,7 — fixed v11 cache-buster
- src/bootstrap.py:37-52 — local-mode env defaults (127.0.0.1:5050)
- *Residual uncertainty:* runtime_config.py and the system config CSV schema were not read. The project CLAUDE.md large-file table is stale (module_catalog.py is 2,568 lines, not 916; workbook_builder.py 1,560, not 1,443), which is noted for the documentation expert.

**5. Persistence, schema migrations, import and export** (finding identified; architect)

- src/stores/db.py:1-126 — forward-only, per-step atomic migrations; a newer schema is refused
- src/stores/_base.py:58-113 — auto-migrate on writable open, application_id check, read-only refuses an upgrade
- src/stores/plan_store.py:164-165,222-245 — 24 plan migrations; unused plan_paths backups_dir
- src/stores/broker_repo.py:59-60,82-83 — data-moving migration (INSERT...SELECT; DROP TABLE)
- src/local_backup_scheduler.py:27-31,151-160,309-350 — opt-in backups, unchecked checkpoint, copy2
- src/plan_db_replace.py:133-213 — replace with validation, backup API, atomic os.replace
- src/server/admin_routes.py:143-158 — CSV backup export gated by permission and allow_downloads
- *Residual uncertainty:* app_store migrations and the bodies of csv_exchange import/export were not read. The backup-integrity risk is inferred from code and was not reproduced. Interplay with OneDrive sync (onedrive_guard.py) was not inspected.

**6. Performance and computational efficiency** (partially inspected; architect)

- src/detailed_results.py:810-996 — per-request XLSX open for the Excel fallback; result model has a one-entry cache
- src/reporting/sheets_strategy_pair_worker.py:1-40; src/reporting/sheets_strategy.py:430-438 — claim-age sweep parallelised via ProcessPoolExecutor
- src/market_data.py:50-64,1362-1363,1469-1470 — shared requests.Session; thread-pooled quote fetches
- src/report_compute.py:313-330 — duplicate report_spec build already removed
- *Residual uncertainty:* This was a static review, so no timings were taken. Monte Carlo vectorized vs scalar cost, build wall-clock and front-end render cost were not measured. Severity of performance items is therefore conservative.

**7. Privacy and security (local server, remote Trends access, secrets, exports)** (inspected, no material finding; architect)

- src/http_runtime/host_guard.py:1-74 — loopback allow-list; refuses a non-loopback bind without a token; 64 MiB body cap
- src/server/app_core.py:1095-1182 — Host allow-list on every method (DNS-rebinding defence), Origin/Referer check, CSRF token, Content-Type restriction, no CORS
- financial_trends_reporter/access_routes.py:72-110 — local listener requires a loopback Host and refuses proxy headers; remote listener requires a session; owner-only paths return 404
- financial_trends_reporter/access_routes.py:150-157 — session cookie Secure, HttpOnly, SameSite=Strict
- financial_trends_reporter/access_store.py:1-200 — scrypt (n=2^15) with per-user salt, constant-time compare, lockout after 5 failures for 15 minutes, global throttle, dummy hash for unknown users
- financial_trends_reporter/sessions.py:1-60 — token_urlsafe(32), 10-minute idle timeout
- financial_trends_reporter/listeners.py:52-72 — refuses to start if Tailscale serves the unauthenticated local port
- src/secrets_store.py:1-30 — keyring only, no plain-text fallback
- src/bootstrap.py:59-104 — redacting formatter and account-number masking on the file handler
- *Residual uncertainty:* Remote guests can edit account mappings and start or cancel refreshes. This was confirmed as an owner decision in documentation/future/superpowers/plans/2026-10-27-trends-remote-access-design.md:19, so it is not a finding. The remote error handler (access_routes.py:112-116) returns exception text to signed-in non-percent guests, which is a minor disclosure. change_password does not end the user's other sessions. Git history was not scanned for secrets, and GitHub secret scanning was unavailable. The X-User-* identity path in _authorized_and_identity was not read.

**8. Logging and observability** (finding identified; architect)

- src/bootstrap.py:55-104 — the file handler is attached to the 'retirement_system' logger only
- src/sales_tax_year.py:25,170,342; src/year_end.py:18,184; src/data_io.py:69,328; src/market_data.py:298 — getLogger(__name__) outside that tree
- src/fallback_log.py:14; src/report_compute.py:31,283-338 — correctly named loggers; post-projection degradations are logged and surfaced as config_contract_warnings
- src/plan_data_migration.py:502-503; tools/launchers/START_DESKTOP.py:28; src/desktop_api.py:49; main.py:140-146 — migration failure reporting
- frontend/js/dashboard_decomp_local_backups.js:118-134 — swallowed auto-backup error
- git grep -c 'except Exception' src — 415 broad handlers (market_data.py 35, optimization.py 16, planning_engines.py 13)
- *Residual uncertainty:* The 415 broad except sites were not reviewed one by one. Many may be logged via fallback_log, some may be silent. report_compute degradations (ENG-03) were judged adequately logged.

**9. Calculation engine (deterministic year loop, withdrawal cascade, optimizers)** (partially inspected; financial_planner)

- src/projection_stages/income.py:234-372 — apply_income — the self-employment and S-corp paths, the 401(k) and HSA deposits, and the PR #420 AGI reduction (net_earned_taxable -= pretax_contributions at :369)
- src/projection_stages/withdrawal_cascade_gap_assembly.py:60-71 — apply_gap_assembly — take-home pay funds the gap (income_from_streams -= pretax_contributions at :68)
- src/engine_sections/roth_conversion.py:144-168 — _conversion_funding_cap — the PR #419 cap C <= room*(1-t)+S; the algebra checks out (draw W=(tC-S)/(1-t) and C+W<=room)
- src/projection_stages/roth_conversion_and_agi_tax.py:820-886 — apply_agi_and_tax — DAF limit and carryforward, deduction stack, QBI added outside the standard/itemized max
- src/projection_stages/withdrawal_cascade_investment_tax.py:250-297 — _refresh_investment_tax — brokerage gain now enters NIIT MAGI, ACA loss, extra taxable SS and state gain tax
- src/after_tax.py:582-628 — estimate_terminal_taxable_deferred_cap_gain_tax — the 1014 step-up is applied before the heir haircut
- *Residual uncertainty:* The stage order was not traced end to end, and neither were the optimizer objectives (optimization.py, daf_optimizer, qlac_optimizer, housing optimizer, strategy_sweep), hsa_schedule.py, the rental, equity-comp or home-sale stages, or rounding and float behavior (ENG-08). Nothing was executed; PR #419 and #420 were checked algebraically only.

**10. Monte Carlo and capital market assumptions** (partially inspected; financial_planner)

- src/engine_sections/monte_carlo.py:22-55 — vectorized setup — allocation='replay' zeroes tax_drag because replayed deterministic draws already include their tax, so taxes do not respond to each path's returns
- src/engine_sections/monte_carlo_headline.py:15-60 — _scalar_mc_setup — asset-class covariance mu/sigma; success floor = configured floor or buffer years x base spending
- src/engine_kernels.py:740-811 — mortality sampling — SSA table shape calibrated to the user's median age; positional sex
- reference_src/capital_market_assumptions.csv:1-5 — CMA presets dated 2026-06-09, labeled 'not a forecast'
- reference_src/mortality_table.csv:1-2 — SSA 2023 period table
- *Residual uncertainty:* Whether the CMA values are suitable, the mean versus geometric convention, regime and fat-tail sampling, and the agreement between the replay engine and the exact scalar engine (ENG-02) were not assessed. The replay design means path-dependent tax (RMDs and conversions scaling with returns) is approximated. That is a documented design choice, not proven to be a defect. Period rather than cohort mortality could understate longevity, but the user-calibrated median reduces that.

**11. Financial logic: federal and state tax, IRMAA, AGI, capital gains, wash sales** (finding identified; financial_planner)

- src/core.py:846-906 — compute_fed_tax, standard_deduction, senior_bonus_deduction, social_security_taxable_amount — SS provisional thresholds are correctly not indexed; senior phase-out defect (FIN-002)
- src/core.py:908-940 — irmaa_lookback_magi_and_filing — two-year lookback using the lookback year's filing status
- src/core.py:1170-1172 — niit_tax — statutory thresholds, not indexed
- src/core.py:1269-1295 — salt_cap — OBBBA 30% phase-down above the threshold, $10k floor, MFS half, 2030 reversion
- src/core.py:1215-1266 — tentative_minimum_tax / amt_tax — dated 2026 exemption and 50% phase-out
- src/core.py:1052-1109 — state_income_tax — retirement and SS exemptions; per-person exclusion count
- src/projection_stages/roth_conversion_and_agi_tax.py:761-791 — SALT proxy (FIN-003); 0.5% AGI charitable floor applied in every year, including 2025 when OBBBA's floor was not yet in effect (minor)
- src/wash_sales.py:91-185 — detect_wash_sales — W1-W3 implement the stated rules; IRA replacement disallowed with no basis add-back
- *Residual uncertainty:* No primary source was fetched; values were compared with the reviewer's recollection. The OBBBA 2/37 itemized-deduction limit for 37% bracket filers and the 2026 non-itemizer charitable deduction were not found in a grep and were not traced further. The W1 lot key (account, symbol, purchase_date) would skip an unsold same-day buy in the same account; that edge case was not tested. IRMAA MAGI inclusion of brokerage gains was not traced.

**12. Canonical reference data currency (tax law, state tax, mortality, CMA)** (requires external domain verification; financial_planner)

- reference_src/tax_law_v10.json — 2026 standard deduction 32,200 MFJ, LTCG 98,900/613,700, IRMAA 218k/274k/342k/410k/750k, Part B 202.90, AMT 140,200 / 1,000,000 at 50%, QCD 111,000, QLAC 210,000, estate 15,000,000, SS wage base 184,500, ACA 2026 applicable percentages 2.10%-9.96%. These match the reviewer's recollection of the cited IRS, CMS and SSA sources; no fetch
- reference_src/tax_update_dashboard.csv:2-14 — annual process; state_tax REVIEW_REQUIRED_BY_STATE blocking TRUE; the estate row says FIN-009 is still open, but src/after_tax.py:772-773 says it is fixed (documentation drift)
- reference_src/state_tax.csv:1-14 — 13 states, with Illinois estate calc il_credit_table and a $4M exemption
- *Residual uncertainty:* Whether 2027 IRS and CMS figures have been published, whether enhanced ACA credits were extended past 2025 (the dataset assumes they end in 2025), and the 12 non-Illinois state rows were not verified externally. reference.db was not opened, so its parity with the JSON is unconfirmed.

**13. Retirement income and withdrawal workflows (RMDs, Roth conversions, account sequencing)** (inspected, no material finding; financial_planner)

- src/core.py:752-781 — statutory_rmd_start_age — SECURE 2.0 ramp (72/73/75), treating 1959 as 73 per IRS administrative position
- src/engine_kernels.py:919-1002 — compute_rmds — per-owner base minus capped QLAC; Table II divisor for a spouse more than 10 years younger who is sole beneficiary; no de-minimis gate
- src/core.py:725-750 — joint_life_divisor / rmd_divisor — delegates to the kernel
- src/engine_sections/roth_conversion.py:144-168 — _conversion_funding_cap — PR #419 sizing cap
- src/projection_stages/roth_conversion_and_agi_tax.py:211-262 — irmaa_surcharge_for_year — shared IRMAA cash-need helper with SSA-44 relief
- *Residual uncertainty:* The full withdrawal priority order, depletion behavior, the pre-59.5 penalty path and the Roth five-year rules were not traced. No finding does not mean the area is healthy.

**14. Tax planning workflows (Roth conversion, charitable giving, account tax basis, year-end)** (partially inspected; financial_planner)

- src/projection_stages/roth_conversion_and_agi_tax.py:791-855 — charitable netting of QCD and DAF grants; DAF 60%/30% AGI limit with five-year carryforward
- src/core.py:1179-1196 — qcd_annual_limit / qcd_eligible_from_year — age 70.5 year rule
- src/engine_kernels.py:2191-2270 — plan_roth_conversion — pre-conversion AGI now uses earned_taxable (PR #420)
- *Residual uncertainty:* The Account Tax Basis page's Roth basis and HSA expense-bank logic and the year-end transition (src/year_end.py) were not read. Gain and loss harvesting (gain_harvest.py, tlh.py) was not read.

**15. Benefits workflows (Social Security claiming, pensions, annuities, employer plans)** (partially inspected; financial_planner)

- src/projection_stages/income.py:376-452 — Social Security — benefit-table lookup, excess-spousal (dual-entitlement) formula gated on the worker filing, payment in arrears in the claim year, earnings test for member 1
- src/projection_stages/income.py:455-521 — survivor benefit — RIB-LIM (greater of claimed amount and 82.5% of PIA), delayed credits up to death, COLA-indexed, age-60 gate, survivor reduction
- src/parsing/client_sections.py:385-386 — SS funding discount, 22% from 2032 (configurable)
- src/projection_stages/income.py:307-334 — 401(k) deferral and rollover to the IRA
- *Residual uncertainty:* PIA derivation, the claim-age sweep, pension and annuity pricing, joint-and-survivor annuities, and QLAC income were not read in this run. The earnings test is applied to member 1 only, which is consistent with the single-earner model.

**16. Healthcare workflows (HSA, Medicare/IRMAA, ACA premium credits)** (finding identified; financial_planner)

- src/projection_stages/income.py:344-358 — HSA contribution — the parsed base already includes a $1,000 catch-up, and the code indexes it by brk_inf even though the statutory catch-up is fixed; hsa_catchup is never set; min(x, x) is a no-op; the full family amount continues while either spouse is under 65
- src/parsing/hsa_policy.py:85-91 — hsa_contrib_base — the configured limit, not a chosen contribution
- src/engine_kernels.py:1985-2050 — aca_fpl_for_year / aca_applicable_percentage / aca_premium_tax_credit — 400% FPL cliff in the original regime; benchmark halved when one spouse is in bridge years
- src/projection_stages/spending_and_rmd.py:570-600 — prorated bridge and Medicare premiums by month
- src/projection_stages/deterministic_engine.py:446-480 — SEHI source (FIN-006)
- *Residual uncertainty:* The HSA withdrawal and optimizer logic (hsa_schedule.py) and the Medicare Part B/D/G premium inputs were not read. ACA household size after a death is a fixed input. Enhanced credits after 2025 need external confirmation of current law.

**17. Estate, insurance and beneficiary workflows** (finding identified; financial_planner)

- src/core.py:1298-1478 — state_death_tax_credit, illinois_estate_tax, new_york_estate_tax, state_estate_tax, indexed_federal_estate_exemption
- src/after_tax.py:729-783 — estimate_terminal_estate_tax — flat 40% federal tax on the combined indexed exemption less lifetime gifts; CST subtracted for state only
- src/engine_sections/roth_conversion.py:108-141 — _estate_tax_for_row — the same model in the optimizer
- src/projection_stages/deaths_and_spousal_rollover.py:136-232 — CST funding capped by the Illinois-derived shelter cap
- src/reporting/sheets_protection.py:1-14,53-110 — life insurance is report-only
- *Residual uncertainty:* beneficiary_titling_audit (engine_kernels.py:513), gifting logic, special-needs trusts and ABLE accounts, and the 10-year heir-rate derivation were not read. The federal tax has no IRC 2058 state-death-tax deduction at any of its three sites; this is now tracked in FIN-007 and W4-02. Attorney review is required for both the Illinois and the portability arithmetic.

**18. Survivor and household-change workflows (death, filing status, spousal rollover, divorce)** (finding identified; financial_planner)

- src/projection_stages/deaths_and_spousal_rollover.py:85-104 — apply_deaths_and_filing_status — MFJ in the year of death, then survivor filing, with an optional two-year QSS
- src/engine_kernels.py:412-478 — basis step-up fractions by property regime and titling (JTWROS 0.5, community 1.0)
- src/projection_stages/roth_conversion_and_agi_tax.py:855-864 — the age-65 add-on and senior bonus count only living members
- src/core.py:908-925 — survivor IRMAA assessed on the joint lookback return
- src/projection_stages/appreciation_divorce_qlac.py:116-134 — divorce split (FIN-009)
- *Residual uncertainty:* apply_death_transition's account-movement body, HSA transfer at the first death, remarriage, and the per-path survivor buckets in Monte Carlo (PR #416) were not inspected. During QSS years the engine passes 'MFJ', so the senior-deduction threshold is $150k where the reviewer reads the statute as $75k (not a joint return). Professional review is needed.

**19. Data integrity (missing, duplicate, stale, ownership, units)** (finding identified; quality)

- src/parsing/client_sections.py:458,520,547,553,668,1278,1292 — parser defaults — household-specific dollar fallbacks
- src/data_io.py:267-271,320-329 — _v/_n — a blank value turns into the code default
- src/blank_plan.py:69-81 — blank_plan_rows — new plans blank rows rather than deleting them
- src/data_io.py:858,885 — JSON config path — different defaults (home 0, roth 0.24)
- git ls-files tests/fixtures/csv_exchange/sample_plan_frozen vs input/demo — only README.md and client_hsa_schedule.csv differ; input/demo/client_hsa_schedule.csv is header-only (1 line)
- src/core.py:979-1012 — state errors cite a reference_data/ path that does not exist
- *Residual uncertainty:* Only the main money/home/mortgage/income defaults were traced end to end; the other 15 or so large literals in client_sections.py were counted but not traced. Ownership/household-relationship integrity, de-duplication of imports and unit consistency across Monarch/broker imports were not inspected.

**20. Input validation (server field errors, client validation)** (finding identified; quality)

- src/schema_registry.py:16-89 — validate_value/validate_rows — type set leaves out 'dollars'/'decimal'; required check runs on the whole plan
- src/server_services/config_service.py:518-545 — grid save validates all rows, returns 422 with errors and field_errors
- src/server_services/config_service.py:60-76 — structure_validation_errors — shape of the field errors
- src/server_services/plan_forms_service.py:43-104 — forms write path has no validation
- src/server_services/build_service.py:166-208 — preflight missing_required is advisory only; /api/build/start (workbook_routes.py:196-240) does not check it
- tests/test_plan_date_parsing_unit.py:98-103 — test types differ from the schema's types
- *Residual uncertainty:* Client-side WI-020 field validation (dashboard_decomp_row_model.js formatting kinds at 2645-2700) was only partly read, so whether the client rejects text in dollars fields is not confirmed. QA-002 is a static inference and was not run.

**21. Numeric precision and rounding (float engine vs Decimal boundaries, footing)** (partially inspected; quality)

- src/money.py:1-97 — parse_strict_number/strict_float — Decimal grammar at the boundary, float copy for the engine; rejects nan/inf/1e999
- src/data_io.py:320-329 — _n — boundary parse goes through strict_float
- src/results_model.py:30-34,286-299 — chart series rounded to whole dollars per component; display only
- *Residual uncertainty:* Footing between workbook totals and rounded components, rounding in the engine year loop, and cents storage at DB boundaries were not checked. No material finding, but this is not a clean bill of health.

**22. Dates, tax-year boundaries and frozen-today seams** (partially inspected; quality)

- src/platform_runtime.py:28-55 — today() — RETIREMENT_SYSTEM_FROZEN_TODAY seam
- tests/test_frozen_today_seam_regression.py:1-60 — allowlist guard on bare date.today() in src, with exact counts and reasons
- src/taxes.py:26 — TAX_REFERENCE_YEAR comes from the wall clock unless an env override is set, separate from the frozen-today seam
- tests/conftest.py:20-29,112-123 — tests pin TAX_REFERENCE_YEAR=2026 and FROZEN_TODAY=2026-08-04
- src/tax_law.py:64-112 — as_engine_tables/indexed_value — later years use the latest dated row plus inflation
- tests/e2e/fixtures.js, helpers.js, playwright.config.js — grep found no FROZEN_TODAY or TAX_REFERENCE_YEAR, so e2e runs on the real date
- *Residual uncertainty:* The tax year and plan 'today' are two separate seams. They agree in production but can disagree if only FROZEN_TODAY is set. No test runs the 1 Jan 2027 rollover (TAX_REFERENCE_YEAR 2027 with brackets dated 2025-2026). Year-keyed labels (client_sections.py:387,668; note_receivable.py:63) have non-year fallbacks, so rollover risk there looks contained, but it was not exercised.

**23. Error handling and failure behaviour (API error shapes, silent degradation)** (finding identified; quality)

- frontend/js/api_client.js:22-56 — no err.status; text() throws the raw body
- frontend/js/dashboard_decomp_row_model.js:4949-4993 — two error shapes
- frontend/js/dashboard_decomp_build_lifecycle.js:247-270 — 404 fallback that never runs
- src/report_compute.py:283-338 — failures after the projection are logged and turned into config_contract_warnings; a limitation_notices failure becomes [] with no user warning
- src/data_io.py:326-329 — unreadable number is logged and the default used
- *Residual uncertainty:* Direct fetch() calls that bypass the client (about 23 sites across 9 files, per recon) were not inspected one by one. The except-Exception counts in market_data/optimization were not reviewed.

**24. Testing strategy, golden masters and regression baselines** (finding identified; quality)

- git show --stat 11f6e809 — golden regen (phase goldens, pins, changelog) now committed and merged via #420; working tree clean
- documentation/reference/GOLDEN_MASTER_CHANGELOG.md:1-20 — top entry records old and new pins and a hand-checked AGI delta (-31,575)
- grep '^## ' GOLDEN_MASTER_CHANGELOG.md — 114 entries, many regenerations in Oct-Nov 2026
- tests/test_frontend_size_ratchet.py:695 plus git log -p — ceiling raised in 100 of 106 changes
- tests/e2e/new-plan-creation.spec.js:20-73 — /api/plan/blank mocked, so blank-then-save is untested
- tests/test_blank_plan_rows_functional.py:28-86 — blank-plan tests cover clearing rules and the forms path only
- *Residual uncertainty:* Golden masters come from the engine itself and use fully populated fixtures, so default/blank paths are not covered. Whether the IRS-style example fixtures act as independent oracles was not checked. No tests were run; test existence says nothing about outcomes. QA-006 is a cross-expert duplicate of ARC-005 (conflict C-01).

**25. GitHub work context and author-stated pending items** (partially inspected; quality)

- manifest.json review_run.github_context — zero issues, zero open PRs; flagged items come from PR descriptions
- git log --oneline — 9d4dc360 'Year-end transition Phase 3 ... (#380)' covers PR #366's pending Phase 3
- git log -p tests/test_frontend_size_ratchet.py — 425fd97a raised 43,298 to 43,620, matching PR #390's stated deviation
- git ls-files tests | grep wash — 8 wash-sale test files exist; the CPA confirmation of W1 cannot be checked in code
- *Residual uncertainty:* GitHub MCP was not called in this stage; I relied on the manifest's GitHub context plus local git. The PR #388 data-loss follow-ups and the PR #233 screen-reader request were not checked against code. QA-006 is a cross-expert duplicate of ARC-005 (conflict C-01).

**26. User interface and interaction design (client dashboard)** (finding identified; usability_accessibility)

- frontend/js/dashboard.js:6123-6157 — moveToNextEntry — Enter-to-next acts only on focusableEntries() (navigation.js:462-464), not on search or dialog inputs, so lead UIR-05 is mitigated
- frontend/js/dashboard_decomp_row_model.js:120-131 — suggestedNext — Maintain mode falls back to the Set up chain (left-nav follow-up workstream A landed)
- frontend/js/dashboard_decomp_plan_features.js:444-463 — offFeatureItemHtml — Turn on buttons landed (workstream D)
- frontend/js/dashboard_decomp_build_history.js:399-470 — impactCardHtml/buildImpactCardsHtml — see UX-004
- frontend/js/dashboard.js:2876-2878 — renderStrategyTabs — see UX-005
- *Residual uncertainty:* Static read only; no rendering, layout or interaction was observed. Large analysis panels (housing and allocation optimizer, Roth guardrails, Planning Workbench) were not read.

**27. Information architecture, navigation and wayfinding** (inspected, no material finding; usability_accessibility)

- frontend/js/dashboard.js:14-189 (via recon map; lines 186-189 opened) — STEPS desc from RPHelp.summary — nav one-liners come from the help registry
- frontend/js/dashboard_decomp_row_model.js:120-131 — suggestedNext — Maintain fallback and gated-target guard
- documentation/future/superpowers/plans/2026-11-04-left-nav-redesign-followups.md:3,22-55 — Status: planned — workstreams A, B (ALWAYS_ON_SECTIONS no longer present in nav_features.js) and D appear landed in code, so the plan's status line looks stale (a documentation issue, passed to the docs expert)
- frontend/js/dashboard_decomp_year_end.js:7-16 — yeHtml — Year-End checklist links each step to its page
- *Residual uncertainty:* IA churn (PRs #385-#390, #418) affects returning-user learnability, but that cannot be measured statically. I did not check workstreams C and E, the NAV_FEATURE_MAP doc, or the wi015 baseline JSON. 'No finding' does not mean the IA is healthy.

**28. Usability science: cognitive load, progressive disclosure, learnability, consistency** (finding identified; usability_accessibility)

- frontend/js/dashboard.js:214-224 — TERM_NOTES — the Monte Carlo success gloss is dense ('conditional on the modelled spending cuts ... non-fixed-real spending policy'), and 'terminal net worth' is glossed as 'projected final portfolio value', which conflates net worth with portfolio
- frontend/js/dashboard_decomp_sales_ledger_ui.js:51-56,100-109 versus four other tab bars — see UX-005
- Three feedback conventions — see UX-003
- Mixed native and in-app confirmations — see UX-002
- *Residual uncertainty:* No task-level or comprehension testing evidence exists (R-TDC-08). The TERM_NOTES wording issues are noted but not raised as a separate finding; the planner and docs experts should check the net-worth gloss.

**29. Error prevention and recovery in irreversible financial-record actions** (finding identified; usability_accessibility)

- frontend/js/dashboard_decomp_sales_ledger.js:255-261 and src/sales_service.py:215-232 — slVoid/_set_voided — the void message promises a Restore that is refused for log-linked sales (UX-001)
- frontend/js/dashboard_decomp_cash_accounts.js:59-66 and src/cash_accounts.py:98-113 — caDelete/delete_account — hard delete including Monarch mappings behind a one-line native confirm (UX-002)
- frontend/js/dashboard_decomp_transactions_log.js:183 — tlConfirmed — a missing confirm counts as consent
- frontend/js/dashboard_decomp_local_backups.js:31-36 — backups off by default
- frontend/js/dashboard_decomp_row_model.js:3385-3410,4490-4498 — openStaticDialog/showInAppConfirm — an accessible alternative already exists
- *Residual uncertainty:* Server-side void and close-year paths for the transaction log (transactions.py:229 void) and 1099-B supersede were not traced end to end. How native confirm() behaves under pywebview/WebView2 was not observed.

**30. Risk communication and comprehension of financial results** (finding identified; usability_accessibility)

- frontend/js/dashboard_decomp_build_history.js:436-470 — buildImpactCardsHtml — the headline cards use LCV, EFTR and 'Worst-Case' (5th percentile), with definitions in hover-only tooltips (UX-004)
- src/limitation_notices.py:71-124 — NOTICES — plain-language limitation notices exist; N7 is a terse 'Reference data status by family' line (wording passed to planner and docs)
- frontend/js/reports_ui.js:773-777,1319-1324 — chart SVGs have role=img with aria-label and aria-describedby summaries
- *Residual uncertainty:* I did not read how probability of success is worded on Plan Status or in the workbook. dashboard.js:4748 gives the guidance 'Aim for an 80-90% success rate', which is passed to the financial planner for appropriateness.

**31. Accessibility (keyboard, focus, semantics, screen reader, contrast, text size)** (finding identified; usability_accessibility)

- frontend/js/dashboard_decomp_row_model.js:195-241 — showMessage — role swap on a single slot, and a later message overwrites an earlier one (UX-003)
- Panel role=status injections — cash_accounts.js:18, sales_ledger.js:90, sales_1099b.js:105, transactions_log.js:26 (UX-003)
- Tablists — dashboard.js:2877, holdings_tabs.js:29, monarch_reconciliation.js:248, rental_properties.js:391 (UX-005)
- frontend/css/dashboard.css:3 :root — contrast computed: --muted #68645b on #fbfaf7 is 5.65:1, on #f6f5f0 is 5.4:1; --warn on white is 7.09:1 (passes AA)
- frontend/js/text_size.js:5-17 — 130% cap via CSS zoom (UX-006)
- *Residual uncertainty:* No assistive-technology, keyboard or zoom run was done. Contrast was checked for tokens only, not for every hard-coded colour in the minified CSS. Forced-colors and high-contrast mode are unsupported according to the recon grep, which I did not re-verify.

**32. Secondary UI surfaces (Admin Control Center, Financial Trends reporter, Excel workbook)** (partially inspected; usability_accessibility)

- frontend/admin.html:1-7 — shell — has a lang attribute and a polite live #msg. It has no skip link, and the search-scope toggle buttons carry their state only in the 'primary' class (no aria-pressed). Minor; not raised as a finding
- frontend/js/admin.js:786-792,1338-1340,1849 — settings and grid inputs have ids or aria-labels (prior UX-006 remediation appears to hold)
- financial_trends_reporter/frontend/signin.html:17-38 — labelled inputs with autocomplete, an error div with role=alert, and a network-error message
- financial_trends_reporter/frontend/charts.js:263,422-428,648,934 — charts have a visually-hidden data table, role=img with aria-label, and focusable points
- *Residual uncertainty:* I did not read change_password.html, access.js, the Trends index.html body, or the Excel workbook's sheets and formatting for readability. The Admin screen-reader pass requested in PR #233 has no recorded outcome.

**33. Terminology and inclusive language in UI and data** (inspected, no material finding; usability_accessibility)

- frontend/js/dashboard_decomp_row_model.js:669-679 — display rewrite — Husband/Wife/Member tokens are replaced with personDisplayName() on screen
- frontend/js/dashboard.js:1455-1465 — PERSON_VALUE_TOKEN_RE — choice values mapped to person names
- src/reporting/sheets_wealth.py:45 and sheets_stress.py:1306-1310 — the workbook maps husband/member_1 to nicknames
- reference_src/generated_schema_coverage.csv:2 — the developer reference still lists Husband_IRA | Wife_IRA as raw choices
- *Residual uncertainty:* Internal keys are gendered (h_/w_, Husband_IRA), and display mapping hides this in the main UI and workbook. I did not verify whether the Admin Control Center shows raw choice values (admin.js:786 renders choices with esc(c) and has no personDisplay mapping). If it does, it would show Husband_IRA to an admin user.

**34. Contextual help, glossary and end-user documentation** (finding identified; documentation)

- frontend/js/help_registry.js:1-5 — header — plain-English, high-school-reader target
- frontend/js/help_registry.js:140-147,248-255 — HELP_PAGES.spending_core / strategy_optimize — concatenated multi-page text, undefined TNW/KPIs/sleeve
- frontend/js/help_registry.js:6-102 — GLOSSARY — 91 terms, no terminal net worth / probability of success
- documentation/reference/readme/README.md:6-12,38-42 — end-user README — stale 'Welcome' and 'under Reports & Review'
- frontend/js/dashboard_decomp_checklist_closeout.js:285,289 — Plan Status pane and Concepts Guide card — retired page names; guide pointer is plain path text
- frontend/js/dashboard.js:14-185 — STEPS — current titles and groups
- documentation/reference/Retirement_Planner_Concepts_Guide.docx — word/document.xml — retired screen names; new pages absent
- documentation/future/page_help_review.md:1-14 — merge method — fact-preserving merge
- *Residual uncertainty:* Help text was read statically. It was not rendered in the app, so panel truncation and visual length were not observed. HELP_SECTIONS (lines 395-914) and HELP_FIELDS were sampled only. Whether the packaged build or release zip includes documentation/ (and so the Concepts Guide) was not established.

**35. Design and implementation document status and eligibility** (finding identified; documentation)

- documentation/DOCUMENTATION_INDEX.md:3-8,26-32 — layout rule — future/ = planned not built
- documentation/future/superpowers/plans/2026-10-26-trends-time-scope-design.md:3 — Status — 'not yet merged' vs merged #276
- documentation/future/superpowers/plans/2026-10-27-trends-drilldown-reconciliation-design.md:4 — Status — 'draft PRs' vs merged #288
- documentation/future/superpowers/plans/2026-11-04-left-nav-redesign-followups.md:3 — Status planned vs #391 merged
- documentation/future/page_help_review.md:1 — Status draft vs plan implemented
- First-20-line Status scan of all documentation/future/**/*.md (this run)
- *Residual uncertainty:* Status was compared with git merge history for about 6 documents only. The other future/ and archive/ documents marked status-uncertain by the inventory were not individually reconciled. Archive exclusions from the inventory stage were accepted as recorded, not re-verified.

**36. Developer and agent guidance documentation (CLAUDE.md, runbooks, backlog)** (finding identified; documentation)

- .claude/claude.md:15-30 — Reading Large Files — stale counts, moved path
- wc -l this run — measured sizes for all listed files
- .claude/hooks/large_file_guard.py:11,21-27 — GUARDED — stale counts, module_catalog unguarded
- documentation/reference/CLAUDE.md:42 — project location — wrong folder name
- conftest.py:1-6 — docstring — refers to untracked output xlsx
- documentation/reference/BACKLOG.md:3-26 — tracker — 8 items, last change 2026-10-20
- documentation/future/superpowers/plans/2026-11-04-left-nav-redesign-followups.md:11,57-58 — backlog item not added
- *Residual uncertainty:* The runbooks (ANNUAL_MAINTENANCE, GOLDEN_MASTER_RECOVERY, CONVERSION_*, TRENDS_REMOTE_ACCESS) were checked for presence and index listing only; their step accuracy was not validated against tools. Commands in reference/CLAUDE.md were checked for file existence only and were not run.


### 3.2 GitHub issues, pull requests and flagged work inspected

The repository has no GitHub issues. The items below are merged PRs, author-stated pending items from PR descriptions, and reconnaissance work-item leads (ENG-, UIR-, R-TDC-, X- identifiers from the system map). Where experts recorded different dispositions, the final disposition follows this order: confirmed > resolved > insufficient_evidence > duplicate > contextual_only > out_of_scope.

| Item | Expert dispositions | Final disposition | Notes |
|---|---|---|---|
| PR #233 | usability_accessibility: contextual_only; quality: insufficient_evidence | **insufficient_evidence** | Limitation notices and the Admin a11y request. src/limitation_notices.py was opened. The N7 wording is terse; passed to the planner and docs experts. / Requests for N7 heading prose and a screen-reader pass not checked |
| PR #234 | architect: resolved | **resolved** | src/server_services/build_job_service.py:175-192 request_cancel terminates the build subprocess. Whether ProcessPool grandchildren are cleaned up on Windows was not verified. |
| PR #235 | documentation: confirmed | **confirmed** | The author said the Concepts Guide 'Find it' labels were not walked against the app. Retired screen names were confirmed in the docx (DOC-003); the README location drift is in DOC-002. |
| PR #259 | usability_accessibility: contextual_only; documentation: contextual_only | **contextual_only** | Follow-focus help panel. help_registry.js:1076-1101 confirms only aria-controls=helpPanel openers work, which is the basis of UX-004. / Help registry and follow-focus panel. Establishes help_registry.js as the source; no defect taken from it directly. |
| PR #267 | usability_accessibility: contextual_only; documentation: insufficient_evidence | **insufficient_evidence** | Prose guard. Relevant as a constraint on fixes for UX-004. / Author-flagged judgement calls (restyled 'Why it matters', removed hover titles) were not individually inspected. |
| PR #268 | documentation: confirmed | **confirmed** | The content pass claimed retired page names were replaced, but 'Spending Categories' (7 uses) and 'Income & Expense Transactions' (3 uses) remain in help_registry.js, and long stitched records remain. Supports DOC-001. |
| PR #366 | financial_planner: contextual_only; quality: resolved | **resolved** | Relevant to FIN-011, because the first plan year will roll to 2027 without dated rows. year_end.py was not read. / Phase 3 shipped later as #380 (9d4dc360) |
| PR #385 | usability_accessibility: contextual_only | **contextual_only** | Nav search context only. |
| PR #386 | financial_planner: out_of_scope | **out_of_scope** | UI placement belongs to usability. The Roth basis and HSA expense-bank engine use was not traced. |
| PR #387 | usability_accessibility: contextual_only | **contextual_only** | IA churn context only. |
| PR #388 | architect: resolved; quality: insufficient_evidence | **resolved** | git grep finds no /api/year-end or wash-signature calls in frontend/js at the reviewed ref, so this was superseded by the #418 redesign. / Follow-ups may be moot after the #418 redesign; not checked |
| PR #390 | architect: confirmed; usability_accessibility: contextual_only; documentation: contextual_only; quality: confirmed | **confirmed** | Corroborated by local git log -L on tests/test_frontend_size_ratchet.py:695 (425fd97a). Recorded as ARC-005. / Left nav redesign. Follow-ups checked in code. / Left-nav redesign. It is the cause of the retired names found in DOC-002 and DOC-003. / Ceiling raise 43,298 to 43,620 confirmed in 425fd97a; part of QA-006 (duplicate of ARC-005) |
| PR #391 | documentation: contextual_only | **contextual_only** | Merged nav follow-ups A, B and E while the follow-up plan still says 'planned' (DOC-004). |
| PR #416 | financial_planner: contextual_only | **contextual_only** | Not opened in this run. Survivor Monte Carlo buckets not assessed. |
| PR #418 | architect: contextual_only; financial_planner: insufficient_evidence; usability_accessibility: contextual_only; documentation: contextual_only; quality: insufficient_evidence | **insufficient_evidence** | Schema v23/v24 DDL is additive (sales_repo.py:101-110, transactions_repo.py:66-78). The wash-sale rule correctness belongs to the financial planner. / The code in wash_sales.py:91-185 matches the stated rules. CPA confirmation of W1 is still appropriate. Possible edge case: the (account, symbol, purchase_date) key skips an unsold same-day buy in the same account. No finding raised. / The Sales Ledger v3 restructure is the provenance of the native confirms and the void/Restore wording in UX-001 and UX-002. Its body states several flows were not exercised in the app. / Wash-sale CPA confirmation pending; cited in DOC-006 as an untracked approval gate. Tax correctness is out of the documentation charter. / Pending CPA confirmation of wash-sale W1 cannot be checked from code; wash tests exist |
| PR #419 | architect: out_of_scope; financial_planner: contextual_only | **contextual_only** | Financial correctness belongs to the financial planner. Used only as evidence that the monolithic engine files change frequently (ARC-001). / _conversion_funding_cap is algebraically correct, and the IRMAA cash need is shared through irmaa_surcharge_for_year. Not executed. |
| PR #420 | architect: out_of_scope; financial_planner: contextual_only; quality: contextual_only | **contextual_only** | Financial correctness belongs to the financial planner. Used only as evidence that the monolithic engine files change frequently (ARC-001). / The 401(k) and HSA AGI and cash treatment was inspected in income.py:361-371, gap_assembly.py:60-71 and engine_kernels.py:2191-2270, and reads correctly. The remaining scope gaps are in FIN-010. The golden re-pin (11f6e809) was not verified value by value. / Merged engine change plus golden re-pin; the changelog records a hand check |
| ENG-01 | architect: confirmed | **confirmed** | Verified at deterministic_engine.py:91-1792 and planning_engines.py:49-199. Recorded as ARC-001. |
| ENG-02 | financial_planner: contextual_only | **contextual_only** | The replay allocation zeroes tax drag (monte_carlo.py:51-54). Parity was not measured. |
| ENG-03 | architect: contextual_only; quality: contextual_only | **contextual_only** | report_compute.py:283-338 logs each failure to 'retirement_system.report' and surfaces warnings, so this is not silent. The related logging gap is recorded under ARC-003. / report_compute turns step failures into warnings; limitation_notices failure gives an empty list with no warning |
| ENG-04 | financial_planner: confirmed | **confirmed** | The single-earner owner_idx=0 model, the missing age-based catch-up and Roth-catch-up rules, and the missing employer contributions are confirmed at income.py:307-318. Recorded as FIN-010 (low). |
| ENG-05 | financial_planner: confirmed | **confirmed** | Dated rows end in 2026, with inflation fallback after that (FIN-011). Wash-sale W1 is in the PR #418 entry. |
| ENG-06 | financial_planner: confirmed | **confirmed** | The 'IL corporate surcharge ... already captured' comment is incorrect (FIN-008). The il_exempt identifiers are cosmetic. |
| ENG-07 | architect: confirmed | **confirmed** | Verified at housing_comparison.py:53-57, the five housing modules and workbook_routes.py:626. The Core->Routes edge is only the desktop_api adapter. Recorded as ARC-002. |
| ENG-08 | financial_planner: insufficient_evidence; quality: contextual_only | **insufficient_evidence** | Rounding and footing were not inspected by this expert. / Float engine behind a Decimal boundary confirmed in money.py; footing not inspected |
| ENG-09 | documentation: confirmed | **confirmed** | Large-file table and reference CLAUDE.md location are stale (DOC-005). |
| ENG-10 | architect: contextual_only | **contextual_only** | The claim that the legacy v10 DB is still written is refuted by src/local_store.py:5-8 (imported once, no longer written). The schema counters are independent and each is guarded. The rollback and backup gap that was found is recorded as ARC-004. |
| Prior review FIN-001 (SYSTEM_REVIEW_2026-10-19) | financial_planner: resolved | **resolved** | withdrawal_cascade_investment_tax.py:256-297 now adds the gain to NIIT MAGI, ACA MAGI and taxable SS. IRMAA MAGI and the senior phase-out were not traced, so the fix may be partial. |
| Prior review FIN-009 (CST double count) | financial_planner: resolved | **resolved** | after_tax.py:772-775 and roth_conversion.py:119-121 no longer subtract the CST federally. tax_update_dashboard.csv still says 'remains open' (documentation drift). |
| R-TDC-01 | quality: resolved | **resolved** | The uncommitted golden regen is now committed in 11f6e809 and merged via #420 (3c7bb121); git status is clean |
| R-TDC-02 | quality: contextual_only | **contextual_only** | Regeneration is frequent, but the top entry has a recorded hand check; no wrong pin found |
| R-TDC-03 | quality: resolved | **resolved** | The demo client_hsa_schedule.csv is header-only, so leaving it out of the frozen fixture loses no data; HSA schedule has 16 dedicated test files |
| R-TDC-04 | documentation: duplicate | **duplicate** | Same as ENG-09; folded into DOC-005. |
| R-TDC-05 | quality: confirmed | **confirmed** | QA-005 |
| R-TDC-06 | financial_planner: confirmed | **confirmed** | Confirmed from tax_law_v10.json and state_tax.csv. Recorded as FIN-011. |
| R-TDC-07 | usability_accessibility: contextual_only | **contextual_only** | Gendered keys exist internally, but the UI and workbook map them to display names. No material on-screen finding. |
| R-TDC-08 | quality: contextual_only | **contextual_only** | E2E runs one desktop viewport and is not date-frozen; usability test bodies not opened |
| R-TDC-09 | quality: contextual_only | **contextual_only** | Unsuffixed-file ratchet at ceiling; not material by itself |
| R-TDC-10 | documentation: confirmed | **confirmed** | The conftest docstring refers to an untracked output file, and the two guidance files overlap; folded into DOC-005. |
| R-TDC-11 | documentation: confirmed | **confirmed** | BACKLOG.md is the sole tracker and is not receiving deferred items (DOC-006). |
| UIR-01 | usability_accessibility: out_of_scope; quality: confirmed | **confirmed** | The build-start 404 fallback and err.status are error-handling correctness, owned by quality. I did not verify it. / QA-004 |
| UIR-02 | usability_accessibility: out_of_scope; quality: contextual_only | **contextual_only** | API error shape consistency is owned by quality. UX-003 covers the user-facing feedback side. / Error shapes differ (folded into QA-004); one RetirementApiClient.text caller found (ytd_and_plan_folder_io.js:900), raw-body exposure not traced further |
| UIR-03 | usability_accessibility: confirmed | **confirmed** | Became UX-002. No confirm shim in pywebview_bridge.js (grep for confirm or alert returned nothing). The extra void/Restore defect became UX-001. |
| UIR-04 | usability_accessibility: confirmed | **confirmed** | Became UX-005. |
| UIR-05 | usability_accessibility: resolved | **resolved** | Enter-to-next is scoped to focusableEntries() field and table inputs (navigation.js:462-464). Nav search, dialogs and width fields are excluded (dashboard.js:6123-6145). |
| UIR-06 | usability_accessibility: confirmed | **confirmed** | Became UX-006 (readability). Token contrast passes AA by computation. |
| UIR-07 | usability_accessibility: contextual_only | **contextual_only** | Left-nav follow-up workstreams A, B and D appear landed in code, so the plan's Status: planned looks stale (docs expert). The flows PR #418 states were not exercised were not run (static review). |
| UIR-08 | usability_accessibility: confirmed | **confirmed** | Folded into UX-003. |
| UIR-09 | usability_accessibility: insufficient_evidence | **insufficient_evidence** | The Admin shell lacks a skip link and aria-pressed on scope toggles. Labels appear present. No screen-reader pass was possible. |
| UIR-10 | architect: contextual_only; usability_accessibility: contextual_only | **contextual_only** | Security controls inspected and judged sound. Guest edit rights are an owner decision per 2026-10-27-trends-remote-access-design.md:19. Usability and accessibility of the sign-in pages are left to the usability expert. / The Trends sign-in and charts show deliberate accessibility work. I did not read change_password.html or access.js. |
| UIR-11 | documentation: duplicate | **duplicate** | Same as ENG-09 / R-TDC-04; folded into DOC-005. |
| X-01 | architect: confirmed | **confirmed** | Recorded as ARC-006. |
| X-02 | documentation: confirmed | **confirmed** | future/ holds implemented documents, and several Status lines are stale against merge history (DOC-004). The unindexed reference/ docs are confirmed in DOC-007. |
| X-03 | architect: contextual_only | **contextual_only** | requests and pypdf are guarded with working fallbacks or clear errors. Playwright lives in a separate venv, and PyInstaller is build-only. No runtime defect. |

**Author-stated pending items from PR descriptions.**

| PR | Pending item (summary) | Final disposition | Basis |
|---|---|---|---|
| #418 | Wash-sale rule W1 needs the owner's CPA confirmation before release | insufficient_evidence | Cannot be checked from code. wash_sales.py:91-185 matches the stated rules. The confirmation gate is now tracked by W1-07. |
| #418 | Record sales entry, wash-card review and 1099-B apply were not exercised in the app | insufficient_evidence | Static review. These flows carry UX-001 and UX-002. |
| #390 | Spec deviations, including the size-ceiling raise and Business Succession having no UI | confirmed (ceiling, ARC-005); contextual_only (others) | 425fd97a raised 43,298 to 43,620. Maintain-mode suggested-next appears landed (row_model.js:120-131). Business Succession is untracked (DOC-006). |
| #388 | Ledger follow-ups (carryforward text loss, wash count scope, extra /api/year-end cost and others) | resolved (request cost); insufficient_evidence (other follow-ups) | The extra request cost is resolved (no such calls at the reviewed ref). The other follow-ups were not checked and may be moot after #418. |
| #366 | Year-end transition Phase 3 not included | resolved | Shipped later as #380 (9d4dc360). |
| #234 | Real server-side build cancellation not attempted | resolved | build_job_service.py:175-192 request_cancel terminates the subprocess. Cleanup of Windows ProcessPool grandchildren was not verified. |
| #233 | N7 notice heading prose needs planner review; Admin screen-reader pass requested | insufficient_evidence | No recorded outcome. N7 wording was judged terse. |
| #235 | Concepts Guide 'Find it' labels were not walked against the app | confirmed | DOC-003 |
| #267 | Judgement calls in the help prose pass | insufficient_evidence | Not individually inspected |

## 4. System health assessment

Ratings are relative judgements from static evidence. They are not measurements.

| Dimension | Assessment | Basis |
|---|---|---|
| Architecture | **Moderate concern.** Stage extraction, an explicit host guard and generated architecture documentation are strengths. The engine core is one closure-heavy function behind wildcard-import facades. Layering is inverted between the housing domain and the service layer, and the main app and the Trends reporter import each other. | ARC-001, ARC-002, ARC-007 |
| Usability and accessibility | **Moderate concern.** There is visible care: an accessible in-app dialog, the Sales Ledger tab pattern, chart text alternatives and token contrast that passes AA. That care is not applied consistently in the newest record-keeping flows (native confirms, three feedback conventions, inert help buttons, partial tab semantics, 9-10px labels). No assistive-technology run was possible. | UX-001 to UX-006 |
| Documentation | **Moderate concern.** The help registry, glossary and annual-maintenance runbooks exist. User-facing directions lag the November nav redesign, the main concepts document is hard to open, and status and backlog tracking has drifted. | DOC-001 to DOC-007 |
| Quality and testing (static) | **Moderate concern.** The project has extensive regression, golden-master and contract test structure, plus frozen-today seams. The blank and default paths are not covered (fixtures are fully populated, and the new-plan e2e test mocks the blank endpoint). The validator's type vocabulary does not match the schema. Test existence says nothing about test outcomes, and no tests were run. | QA-001 to QA-004, ARC-005 |
| Financial correctness | **Moderate concern, bounded.** RMD ages, IRMAA lookback, NIIT, SALT cap mechanics, AMT, Social Security survivor rules and the PR #419/#420 changes read correctly. Several federal deduction simplifications understate federal tax, the missing Illinois entity-level replacement tax understates state tax, and the estate calculations, which also feed Roth-conversion scoring, need professional review. Every financial statement here is bounded by its stated jurisdiction and rule year, rests on the reviewer's knowledge, and was not checked against primary sources fetched in this run. | FIN-001 to FIN-012 |
| Data integrity | **Elevated concern.** Blank values become household-specific defaults, and the CSV and JSON loaders disagree. Backups can miss committed data. Upgrades are forward-only with no copy. | QA-001, QA-003, ARC-004 |
| Security and privacy | **No material finding in the inspected scope.** Inspected: loopback host allow-listing, CSRF and Origin checks, scrypt credentials with lockout, secure session cookies, keyring-only secrets and log redaction. Gaps: records outside the logger tree bypass masking (ARC-003); git history was not scanned for secrets; GitHub secret scanning is unavailable. | Coverage area "Privacy and security"; ARC-003 |
| Performance | **Not measured.** One uncached XLSX parse on every Results Explorer index request. No timings were taken. | ARC-007 |

## 5. Material findings

Confirmed and partially confirmed findings only, ordered by severity. Duplicates and other dispositions are in Section 13. No finding remains in `unverified` status.

### QA-001 — Blank, missing or unreadable plan values silently become hard-coded household-specific dollar figures

| Field | Value |
|---|---|
| Expert | quality |
| Category | data-integrity |
| Severity | high |
| Confidence | high |
| Inspection status | finding_identified |
| Verification status | confirmed |
| Linked implementation items | W1-04 |

**Evidence**

- `src/parsing/client_sections.py:458, 520, 547, 553-554, 668, 1278, 1292` — parse_cashflow_* / parse_spending_and_home_sale / parse_ltc_and_holdings — Defaults applied when a value is blank or absent: annual_earned_income 290000, annual_spending_base_year 225000, mortgage monthly_payment 3000 (x12), balance_as_of_plan_start 293284 at interest_rate 0.0199 to last_payment_year 2034, home value 1313000, LTC face_value 250000, S-Corp reasonable_salary_annual 80000
- `src/data_io.py:267-271, 320-329` — _v / _n — _v returns the stored string, so a blank row gives ''. _n('' , default) passes the default into strict_float, which returns it for a blank cell. An unreadable value is only logged ('unparseable number ... using default') and the default is returned
- `src/money.py:44-58, 94-97` — parse_strict_number / strict_float — A blank or None cell returns the supplied default, so the code default is used and nothing is raised
- `src/blank_plan.py:1-15, 23-27, 69-81` — blank_plan_rows — Start New Plan keeps every row but sets household facts to ''. The docstring itself says blanking 'drops the engine onto whatever hardcoded fallback happens to exist in code'
- `src/parsing/client_sections.py:556-580` — mortgage amortization schedule — The default mortgage balance, rate and payment build mort_schedule and mort_interest_schedule
- `src/projection_stages/spending_and_rmd.py:336-338` — mort_pmt_configured — A positive default mort_pmt makes the mortgage payment count as a spending outflow up to mort_end
- `src/projection_stages/roth_conversion_and_agi_tax.py:767` — mort_interest_yr — Default-derived mortgage interest feeds the itemized-deduction calculation
- `reference_src/schema.csv:58, 62, 63, 68, 91` — schema rows — The schema has a blank default for mortgage balance (not required) and the other fields, and a 60000 default for reasonable_salary_annual. The parser uses 80000, so schema and parser disagree
- `src/data_io.py:858, 885` — JSON/wizard config path — The other config path defaults home_value to 0 and roth_brk to 0.24, so the two loaders give different results for the same missing value
- `src/server_services/build_service.py:166-208, 259-266` — build preflight — Blank required fields are reported as preflight 'blockers', but only fields with required=TRUE. The mortgage fields are not required, so a blank mortgage is never flagged
- `src/server/workbook_routes.py:196-240` — build_start — /api/build/start does not check preflight blockers before it starts the build subprocess

**Observed behavior:** On the CSV/plan-row config path, a blank, missing or unreadable value in these fields is replaced with a specific dollar figure. These figures do not look generic (for example $293,284 mortgage balance at 1.99% through 2034, $3,000/month payment, $1,313,000 home, $290,000 earned income, $225,000 spending). Start New Plan creates exactly this state, because it blanks the rows instead of deleting them. A household with no mortgage that leaves the mortgage rows blank is projected to have a $293,284 mortgage with $36,000/yr payments and deductible interest. Nothing tells the user, because the mortgage fields are not marked required.

**Impact:** Net worth, cash flow, itemized deductions, Roth sizing and survivor/insurance need (sheets_protection.py reads mort_bal) can be materially wrong for new plans or partly completed plans, and the output looks plausible. The same blank field also gives different values on the CSV and JSON config paths.

**Affected workflows:** Start New Plan then build; Households with no mortgage, no home, or no earned income that leave fields blank; Typos in dollar fields (unreadable value, so the default is used); Insurance need / protection sheet

**Root cause:** Code defaults in the CSV parser look like they were carried over from one real household's data, and the parser treats blank the same as 'use the code default' instead of 'none/zero'. Nothing enforces agreement between the schema default column and the parser defaults.

**Options and tradeoffs:**

1. No credible alternative; this is a correctness defect.

**Recommendation:** Make blank mean the schema default, or 0/none when the schema default is blank, for every dollar/rate field. Remove the household-specific literals from client_sections.py. Make an unreadable value a validation error, not a logged fallback. Add a contract test that parses a blank_plan_rows() plan and asserts mortgage balance, payment, home value, earned income and spending are zero or schema defaults. Add a test that each parser default equals the schema.csv default.

**Dependencies:** QA-003 (dollars-type validation) so unreadable values are rejected before they reach the parser

**Implementation considerations:** Golden masters use fully populated fixtures, so they should not move. Confirm that with tools/regen_golden_master.py measure before any regeneration. The JSON/wizard path (data_io.py:858-885) should share the same default source.

**Risk of change:** Low to medium. Plans that relied on the fallback without knowing it will change, so this needs a release note and a measure-first golden check.

**Verification method:** Static trace this run: blank_plan_rows -> '' -> _v -> _n -> strict_float default -> mort_schedule -> spending_and_rmd mort_yr. Confirm by a unit test that calls parse_client on a blanked frozen fixture and asserts c['mort_bal']==0 and c['home_val']==0.

**Adversarial verification:** I opened the cited code and could not refute it. src/parsing/client_sections.py:458, 520, 547, 553-555, 668, 1278 and 1292 hard-code defaults of 290000, 225000, 3000 a month, 293284 at 0.0199 to 2034, 1313000, 250000 and 80000. src/data_io.py:267-271 (_v) returns the stored '' for a blank row. src/data_io.py:320-329 (_n) hands the default to strict_float, and src/money.py:56-59 returns that default for a blank cell; an unreadable value only logs a warning and the default comes back. src/blank_plan.py:69-81 clears values to '' rather than deleting rows, and its docstring (lines 23-26) admits that blanking falls through to whatever fallback is hard-coded. reference_src/schema.csv lines 67-70 show the mortgage payment, balance, rate and end-year fields with required=FALSE and a blank default, and line 62 shows reasonable_salary_annual defaulting to 60000 where the parser uses 80000. In src/projection_stages/spending_and_rmd.py:336-338 a positive mort_pmt counts as a spending outflow up to mort_end, and src/projection_stages/roth_conversion_and_agi_tax.py:767 reads mort_interest_schedule. The JSON path in src/data_io.py (around 858) defaults home_value and mortgage_balance to 0, so the two loaders do disagree. Points I did not fully check: the roth_brk 0.24 claim (the line I saw sets roth_brk from roth_target_rate), and the build_service preflight logic. I did confirm that build_start in src/server/workbook_routes.py:196-240 contains no preflight or blocker reference. Mitigation: earned income, spending and home value are required=TRUE, so preflight should list them as blockers. The silent-default risk is therefore strongest for the mortgage, LTC and S-Corp fields, which are not required. High severity is justified, because a household with no mortgage gets a phantom $36k/yr mortgage and deductible interest with no warning. No jurisdiction or rule-year question applies; this is not a tax-rule finding.

### QA-002 — After Start New Plan, a grid save probably fails until every cleared required field is filled in the same save

| Field | Value |
|---|---|
| Expert | quality |
| Category | workflow-validation |
| Severity | high |
| Confidence | medium |
| Inspection status | finding_identified |
| Verification status | confirmed |
| Linked implementation items | W2-01 |

**Evidence**

- `src/server_services/config_service.py:518-545` — config rows save (/api/config/rows) — After applying the posted updates, it runs _schema_validate_rows_full(store.all_rows()) on the whole plan. Any error rolls back every update and returns 422
- `src/schema_registry.py:16-19, 75-89` — validate_value / validate_rows — Every row whose schema has required=TRUE and an empty value gets 'required value missing'
- `src/blank_plan.py:69-81` — blank_plan_rows — Clears household facts. Calling keeps_value() against reference_src/schema.csv (read-only import) shows 21 of 53 required fields are cleared, including member_1/2 name, dob, retirement_date, residence_state, filing_status, annual_earned_income, annual_spending_base_year and home value_as_of_plan_start
- `frontend/js/dashboard.js:1095, 5959` — api('/api/config/rows') — The UI saves through the validated grid endpoint
- `frontend/js/dashboard_decomp_row_model.js:5389-5401` — save error handling — The client expects a 422 'Plan Data validation failed' and marks field errors
- `tests/e2e/new-plan-creation.spec.js:20-73` — Start New Plan e2e — The test replaces /api/plan/blank with a mock, so the plan is never actually blanked and no save is tried afterward
- `tests/test_blank_plan_rows_functional.py:71-78` — test_a_blank_plan_then_a_form_edit_round_trip — Only the unvalidated /api/plan/forms path is tested after blanking, not /api/config/rows

**Observed behavior:** Every grid save checks the whole plan, and a blank plan has 21 empty required fields. So the first single-field save after Start New Plan should come back 422 with a list of 'required value missing' errors for fields the user has not reached yet. Single households also face required member_2 fields.

**Impact:** If confirmed, new-plan creation is badly broken: users cannot save step by step and see a wall of errors. No test exercises this path, so it would not be caught.

**Affected workflows:** Start New Plan guided flow; Single-person households (member_2 required)

**Root cause:** The save-time validation treats 'required' as a condition for saving at all, when it is really a condition for building. The new-plan tests mock or avoid the validated save path.

**Options and tradeoffs:**

1. Check 'required' only at build/preflight time, and validate only type/range of changed rows on save
2. Validate the whole plan but downgrade 'required value missing' to warnings returned with a 200
3. Keep the current behaviour but have the blank plan carry neutral values (0, None) for required dollar fields; this conflicts with QA-001's goal of an explicit blank

**Recommendation:** Option 1. Keep format/range checks on save, move 'required' to the build preflight (which already lists missing_required), and add a Python functional test: blank_plan_rows() then POST /api/config/rows with one field, expecting 200.

**Dependencies:** QA-001

**Implementation considerations:** WI-020 field-level validation UI relies on field_errors from the 422. Keep that shape for format errors. Required-ness is also used by build_service preflight, which should become the gate that blocks builds.

**Risk of change:** Low. This relaxes a save-time check and keeps the build-time one.

**Verification method:** Not run, because the review is static. Confirm with a test client: app_core._blank_plan_rows(), then POST /api/config/rows with one update, and check the status and errors list.

**Adversarial verification:** The static chain is complete in files I opened. In src/server_services/config_service.py:518-545 the save applies the updates, runs _schema_validate_rows_full(store.all_rows()) on the whole plan (imported at line 19 as schema_registry.validate_rows), rolls back on any error and returns 422. src/schema_registry.py:16-19 adds 'required value missing' for any required=TRUE field that is empty, and validate_rows (lines 75-89) applies it to every row. blank_plan_rows clears the household rows, and schema.csv marks annual_earned_income, annual_spending_base_year and Home value_as_of_plan_start required=TRUE. The frontend saves only through /api/config/rows (dashboard.js:1095 and 5959, build_history.js:173); a grep found no frontend caller of /api/plan/forms. tests/test_blank_plan_rows_functional.py:71-78 tests only the forms path after blanking. I did not reproduce the '21 of 53' count myself, and the review is static, so I have not shown runtime behavior. I also cannot rule out that reference.db's schema differs from schema.csv. Confidence stays medium. If the finding holds, high severity fits, because the Start New Plan flow would be unusable.

### ARC-001 — Projection engine is one 1,700-line closure-heavy function behind a wildcard-import facade

| Field | Value |
|---|---|
| Expert | architect |
| Category | architecture/modularity |
| Severity | medium |
| Confidence | high |
| Inspection status | finding_identified |
| Verification status | confirmed |
| Linked implementation items | W1-02, W4-05 |
| GitHub context | PR #419 (contextual_only); PR #420 (contextual_only) |

**Evidence**

- `src/projection_stages/deterministic_engine.py:91-1792` — run_deterministic_projection_stage — src/projection_stages/deterministic_engine.py:91-1792 — run_deterministic_projection_stage — it is the only top-level def in the file and spans about 1,700 lines. It holds 20+ nested helpers (_next_housing_for_year 152, _next_housing_sale_inputs 231, _medicare_month_fraction 421, _wellness_premium_for_age 446, _ss_first_claim_year_month_fraction 488, _inflate_brackets_path 516 ...), and none of them can be imported or unit-tested on their own.
- `src/planning_engines.py:3-21, 49-163, 177-183, 193-199` — module header / engine_kernels re-export / from .core import * / rmd_divisor rebinding / project docstring — src/planning_engines.py:177-183 — `from .core import *` then `rmd_divisor = _rmd_divisor_with_table_override` — shows that the wildcard import has already shadowed a function with a narrower signature (Wave 5 N5) and needed a manual rebinding. Lines 49-163 re-export about 110 kernel names (including the typing names Callable, Dict, Iterable) so that callers and monkeypatch targets keep working. Lines 193-199 keep code text in a docstring as 'migration breadcrumbs for legacy source-inspection regression tests'. The file is 3,050 lines.
- `src/engine_kernels.py:19` — from .core import * — src/engine_kernels.py:19 — wildcard import of core — a second 2,415-line engine module pulls in the whole of core's namespace.
- `src/reporting/workbook_common.py:16` — from ..core import * — src/reporting/workbook_common.py:16 — wildcard import — the reporting layer also takes all of core, and workbook_builder.py (comments at 595/662/835) relies on `from .workbook_common import *`.

**Observed behavior:** The year-by-year engine already has 26 extracted stage modules, but the orchestration and many domain calculations (housing steps, mortgage amortization, Medicare month fractions, survivor factors, bracket inflation) still live as closures inside one function. The facade modules use wildcard imports with no __all__ on core and keep a large re-export list so that older call sites and monkeypatch targets keep working.

**Impact:** These are the files that change in every engine fix (PRs #419 and #420 touched this area). The closures cannot be tested in isolation, so they are checked only through whole-projection golden masters, which makes each change risky and slow to verify. Wildcard imports have already caused one silent signature-shadowing defect and can cause another the next time core gains a name.

**Affected workflows:** deterministic projection; Monte Carlo replay (shares kernels); workbook reporting; engine maintenance and code review

**Root cause:** 8 engine files were consolidated into one to avoid circular imports (planning_engines.py:3-14), and stage extraction stopped at the stage boundary without lifting the shared per-year helpers.

**Options and tradeoffs:**

1. Replace the remaining wildcard imports (engine_kernels.py:19, planning_engines.py:177, workbook_common.py:16) with explicit name lists, using the AST method already applied in deterministic_engine.py:46-52, and give core an explicit __all__. Low effort; removes the shadowing class of defect.
2. Lift the nested helpers of run_deterministic_projection_stage into pure functions in projection_stages modules with explicit inputs, one group per change, each verified by golden-master equality. Medium-to-high effort, incremental.
3. Leave the structure and rely on golden masters. No effort, but the defect class and the review cost both remain.

**Recommendation:** Do option 1 first because it is cheap and mechanical. Then do option 2 incrementally, starting with the housing and Medicare helpers, which are the most self-contained. Narrow the planning_engines re-export list once callers import from engine_kernels directly.

**Dependencies:** Golden-master and phase-golden baselines must be stable before each extraction

**Implementation considerations:** Tests that monkeypatch facade names (for example tests/test_lcv_feasibility_gate_regression.py:103,116 patch planning_engines.LCV_FEASIBILITY_GATE_THRESHOLD) depend on where a name is bound. Moving a name changes which binding a patch affects. Remove the docstring breadcrumbs together with the source-inspection tests that need them.

**Risk of change:** Medium. These are pure refactors of financial-critical code, so any accidental behaviour change shows up only as golden-master drift.

**Verification method:** Run golden-master and phase-golden equality before and after each step with no regeneration. A static check that no `import *` remains in src/.

**Adversarial verification:** I opened src/projection_stages/deterministic_engine.py. Line 91 is the only top-level def, run_deterministic_projection_stage, and the file is 1,792 lines. It contains 37 nested defs at 4-space indent (for example _mortgage_payment_and_balance 125, _next_housing_for_year 152, _next_housing_sale_inputs 231), so the count of '20+ helpers' is an understatement. src/planning_engines.py:177-183 confirms the `from .core import *` and the rmd_divisor rebinding comment (W5-2/N5) that explicitly names the shadowing defect. The docstring breadcrumbs are at 193-199. src/engine_kernels.py:19 and src/reporting/workbook_common.py:16 confirm the wildcard imports. grep finds no __all__ in src/core.py. Mitigation already in place: deterministic_engine.py:46-52 uses an explicit AST-derived import list, which shows option 1 is workable. Medium severity holds: this is maintainability risk with one real past defect, not a current wrong output. I did not open the planning_engines re-export list at 49-163 line by line.

### ARC-002 — Layer inversion: housing domain and engine import pricing logic from the server-services layer, and src imports the separate Trends reporter

| Field | Value |
|---|---|
| Expert | architect |
| Category | architecture/coupling |
| Severity | medium |
| Confidence | high |
| Inspection status | finding_identified |
| Verification status | confirmed |
| Linked implementation items | W2-07 |

**Evidence**

- `src/server_services/strategy_asset_service.py:105, 218-260` — HOME_APPR_DEFAULT / estimate_housing_cost — src/server_services/strategy_asset_service.py:218-260 — estimate_housing_cost — the docstring calls it the 'pure pricing core'. It holds hard-coded city and population multipliers and STATE_ESTIMATES defaults inside a 1,256-line service module whose layer is described as request-independent business logic.
- `src/housing_comparison.py:53-57, 193` — import of estimate_housing_cost / INFLATION_GENERAL_DEFAULT — src/housing_comparison.py:53-57 — an engine-level domain module imports from the service layer.
- `src/housing/api.py:23` — HOME_APPR_DEFAULT import — src/housing/api.py:23, src/housing/optimizer.py:24, src/housing/plan_variant.py:14, src/housing/results.py:10, src/housing/zip_screen/screen.py:14 — five housing-domain modules import constants or functions from server_services.strategy_asset_service (git grep output).
- `src/housing/plan_variant.py:72-78` — _years_out — src/housing/plan_variant.py:72-78 — _years_out — its docstring says it re-implements the 'same formula estimate_housing_cost uses internally', which is duplicated logic caused by the misplaced owner.
- `documentation/reference/SYSTEM_ARCHITECTURE_DIAGRAM.md:39-50, 68-78` — generated layer flowchart / third-party table — documentation/reference/SYSTEM_ARCHITECTURE_DIAGRAM.md:39-50 — the generated import graph shows `Core Engine & Domain --> Server Services` and `--> HTTP Routes` edges. Lines 68-78 list `financial_trends_reporter` as an undeclared 'third-party' import of the HTTP Routes layer.
- `src/server/workbook_routes.py:620-639` — get_holding_classes — src/server/workbook_routes.py:626 — `from financial_trends_reporter.live_snapshot import classify_symbol` — the main app depends on the separately launched reporter package for asset-class classification. Meanwhile, ten reporter modules import from src (for example financial_trends_reporter/live_snapshot.py:134-1266 and financial_trends_reporter/main.py:30-45), so the two packages depend on each other.

**Observed behavior:** Housing pricing rules and constants live in a service module and are imported downward by the housing domain package and by housing_comparison. The main app's holdings route imports the classifier that the Trends reporter owns, while the reporter imports widely from src.

**Impact:** A change to the service layer can change engine and housing-optimizer results. The housing formula is already duplicated (plan_variant._years_out) because its owner sits in the wrong layer. The bidirectional src/reporter coupling means neither package can be versioned, packaged or tested alone, and a reporter refactor can break the main app's /api/holdings/classes route.

**Affected workflows:** housing scenarios and optimizer; housing comparison sheet; Investment Holdings grouped view; Financial Trends reporter

**Root cause:** Pricing was extracted from an HTTP payload function into the nearest module (strategy_asset_service, H8 slice 3) rather than into the housing domain package. classify_symbol was written for the reporter first and reused in place.

**Options and tradeoffs:**

1. Move estimate_housing_cost, STATE_ESTIMATES and the HOME_APPR/INFLATION defaults into a domain module (for example src/housing/pricing.py) and have strategy_asset_service import it. Move classify_symbol into src/portfolio_analytics.py and have the reporter import it from src. Add an import-direction rule (domain must not import server_services/server) to the diagram generator or fast gates.
2. Move the code only and do not add an enforcement rule. Cheaper, but the inversion can return.
3. Keep the current layout and document the exceptions in the module catalog.

**Recommendation:** Take option 1. The moves are mechanical. The import-direction rule turns the generated diagram's bidirectional edges into a check rather than just an observation.

**Dependencies:** Regenerate SYSTEM_ARCHITECTURE_DIAGRAM.md as required by project rules

**Implementation considerations:** Keep re-exports in strategy_asset_service for one release if external tools import the names. Python tests that read panel JS as text are not affected.

**Risk of change:** Low. These are pure moves with no formula change. Housing goldens should stay identical.

**Verification method:** Run housing and golden-master tests unchanged. The regenerated diagram should show no Core->Server Services or Core->HTTP Routes edges apart from the desktop_api adapter.

**Adversarial verification:** git grep confirms that src/housing/{api,optimizer,plan_variant,results,zip_screen/screen}.py and src/housing_comparison.py:53 import from server_services.strategy_asset_service. src/housing/plan_variant.py:72-78 _years_out says in its docstring that it duplicates estimate_housing_cost's internal formula. src/server/workbook_routes.py:626 imports financial_trends_reporter.live_snapshot.classify_symbol inside get_holding_classes, and 17 tracked files in financial_trends_reporter import from src, so the dependency runs both ways. Because the import is lazy and inside a function, a reporter break would fail only that route, not app startup. That limits the impact somewhat but does not refute the finding. I did not open SYSTEM_ARCHITECTURE_DIAGRAM.md lines 39-78, so that evidence item is unverified by me. The core claim stands on the import evidence alone.

### ARC-003 — Several modules log outside the 'retirement_system' logger tree, so their warnings never reach app.log or its redaction filters; startup migration failures are dropped on the desktop path

| Field | Value |
|---|---|
| Expert | architect |
| Category | logging-observability |
| Severity | medium |
| Confidence | high |
| Inspection status | finding_identified |
| Verification status | confirmed |
| Linked implementation items | W1-03 |

**Evidence**

- `src/bootstrap.py:55-104` — configure_logging / LOG_LOGGER_NAME — src/bootstrap.py:81-104 — configure_logging — the only file handler (rotating local_state/logs/app.log, with _RedactingFormatter and MaskingFilter) is attached to the 'retirement_system' logger only. No root handler is configured anywhere: a git grep for basicConfig or root handlers in src, main.py, financial_trends_reporter and tools/launchers found nothing.
- `src/sales_tax_year.py:25, 166-176, 342` — log = logging.getLogger(__name__) — src/sales_tax_year.py:25,170 — the logger is 'src.sales_tax_year', outside the configured tree. Its record 'wash detection failed; the loss is shown whole' (a tax-relevant degradation) and the automatic wash-scan failure (342) bypass app.log.
- `src/year_end.py:18, 184` — log = logging.getLogger(__name__) — src/year_end.py:184 — the year-end safe-default fallback is logged to 'src.year_end', which has no handler.
- `src/data_io.py:69, 328` — _log = getLogger(__name__) — src/data_io.py:328 — 'unparseable number ...; using default' goes to 'src.data_io', which has no handler.
- `src/market_data.py:290-298` — secret_store_warning — src/market_data.py:298 — 'Stored API keys unavailable' is logged via getLogger(__name__), which has no handler.
- `src/fallback_log.py:14` — _log — src/fallback_log.py:14 and src/report_compute.py:31 use 'retirement_system.*' names correctly, which shows the convention exists but is not applied consistently.
- `src/plan_data_migration.py:483-503` — run_startup_plan_data_migration — src/plan_data_migration.py:502-503 — the outer `except Exception: return {... 'skipped': True}` has no log call.
- `tools/launchers/START_DESKTOP.py:28` — run_startup_bootstrap() — tools/launchers/START_DESKTOP.py:28 and src/desktop_api.py:49 discard the migration result. Only main.py:140-146 prints the error, and only to the console, never to app.log.
- `frontend/js/dashboard_decomp_local_backups.js:118-134` — maybeRunLocalBackup — frontend/js/dashboard_decomp_local_backups.js:133 — `catch (_e) {}` — a failed automatic backup after save or build is silently ignored.

**Observed behavior:** Records from __name__-named loggers fall through to Python's lastResort handler, so WARNING and above go to stderr only (a console window in the frozen exe, retirement_planner.spec:142, with no file, no rotation and no redaction or account-number masking). Plan-data migration failures on the desktop-shortcut launch path are not recorded anywhere.

**Impact:** When a user reports a wrong number, app.log does not contain the fallback that caused it (wash-sale detection skipped, year-end default used, unparseable plan value defaulted). stderr output also bypasses the MaskingFilter the project relies on to protect account numbers. Startup migration failures on the most common launch path are invisible, so the retry-every-boot design can fail forever without notice.

**Affected workflows:** Sales Ledger tax year; Year-End transition; plan parsing; price refresh; startup migration; automatic local backups

**Root cause:** The file handler is scoped to a named logger tree, but modules created later used the `getLogger(__name__)` idiom. Nothing checks that logger names fall under the tree.

**Options and tradeoffs:**

1. Rename the four __name__ loggers to 'retirement_system.<module>' and add a fast-gate grep forbidding getLogger(__name__) in src/. Log the migration result (and errors) through the 'retirement_system' logger inside run_startup_bootstrap.
2. Attach the rotating handler and its filters to the root logger instead, so every library and module record is captured. Simpler, but third-party library noise lands in app.log.
3. Keep the setup and document that only 'retirement_system.*' records are persisted.

**Recommendation:** Take option 1, and log migration errors in bootstrap so every launch path records them. Have the frontend backup catch call showMessage on failure, as runLocalBackupNow already does.

**Dependencies:** None

**Implementation considerations:** Keep MaskingFilter and _RedactingFormatter on the handler. If option 2 is chosen, check that the filters also apply to the extra records.

**Risk of change:** Low. Only logging wiring changes.

**Verification method:** Unit-test that a record emitted from src.sales_tax_year's logger reaches a handler attached via configure_logging, and that run_startup_bootstrap logs an injected migration error.

**Adversarial verification:** src/bootstrap.py configure_logging attaches the rotating handler, _RedactingFormatter and MaskingFilter only to logging.getLogger('retirement_system'). git grep for basicConfig and getLogger() across src, main.py, financial_trends_reporter and tools/launchers returns nothing, so no root handler exists. src/sales_tax_year.py:25, src/year_end.py:18, src/data_io.py:69 and src/market_data.py:298 use getLogger(__name__), giving 'src.*' names outside the tree. I confirmed their call sites: sales_tax_year 170 ('wash detection failed; the loss is shown whole') and 342, year_end 184, data_io 328. Without a handler these reach Python's lastResort handler and go to stderr at WARNING and above. retirement_planner.spec:142 sets console=True. run_startup_plan_data_migration (plan_data_migration.py:502-503) swallows exceptions with no log call. run_startup_bootstrap (bootstrap.py:110-140) returns the result without logging it, and START_DESKTOP.py:28 discards it. frontend/js/dashboard_decomp_local_backups.js:133 has an empty catch. Observability is degraded, but the migration's own fallback is designed to keep reads correct, so medium severity is appropriate. The claim that the masking bypass matters is plausible but unproven: I did not confirm that any of these messages carry account numbers.

### ARC-004 — Plan-file backups can silently miss committed data, and forward-only schema upgrades run on open with no pre-upgrade copy

| Field | Value |
|---|---|
| Expert | architect |
| Category | persistence/data-integrity |
| Severity | medium |
| Confidence | medium |
| Inspection status | finding_identified |
| Verification status | partially_confirmed |
| Linked implementation items | W2-06 |

**Evidence**

- `src/local_backup_scheduler.py:151-160` — checkpoint_sqlite — src/local_backup_scheduler.py:151-160 — checkpoint_sqlite — runs `PRAGMA wal_checkpoint(FULL)` without reading its (busy, log, checkpointed) result row and swallows every exception. An incomplete checkpoint is therefore indistinguishable from a complete one.
- `src/local_backup_scheduler.py:309-350` — run_backup — src/local_backup_scheduler.py:324-339 — run_backup — calls checkpoint_sqlite, then shutil.copy2 of the main database file only (no -wal file, no SQLite backup API), then records a sha256 manifest of the copy as the backup.
- `src/local_backup_scheduler.py:27-31` — BackupPolicy — src/local_backup_scheduler.py:29 — `enabled: bool = False` — automatic backups are opt-in.
- `src/plan_db_replace.py:133-142, 176-185` — _backup_with_api / replace_active_db — src/plan_db_replace.py:133-142 — _backup_with_api — the codebase already has a consistent-snapshot helper based on sqlite3 backup() and uses it when replacing the active plan, but the scheduler does not reuse it.
- `src/stores/db.py:1-8, 94-123` — migrate — src/stores/db.py:94-123 — migrate — upgrades are forward-only ('There is no downgrade'). A newer file raises SchemaVersionError on older code.
- `src/stores/_base.py:94-113` — _check_and_migrate — src/stores/_base.py:113 — every writable open migrates the file in place. No copy is taken before the upgrade.
- `src/stores/plan_store.py:164-165, 222-245` — PLAN_MIGRATIONS / plan_paths — src/stores/plan_store.py:164-165 — 24 migrations. Some move data: src/stores/broker_repo.py:59-60,82-83 use INSERT...SELECT followed by DROP TABLE. plan_paths (222-245) derives a per-plan local_state/plan_backups/<id> folder but has no caller in src (git grep finds only re-exports in src/stores/__init__.py), so the designed per-plan backup location is unused.
- `frontend/js/dashboard_decomp_row_model.js:5455, 5664` — maybeRunLocalBackup('save'|'build') — frontend/js/dashboard_decomp_row_model.js:5455,5664 — automatic backups fire right after a save or build, when other connections are most likely to be active on the plan file.

**Observed behavior:** When the WAL checkpoint cannot finish, for example because another connection (a build or the Trends reporter process reading the active plan) is mid-read, the scheduled backup copies a main file that lacks recently committed transactions. Its manifest still reports success. Separately, opening a plan file on new code upgrades it in place with no copy, so reverting to the previous build means the file can no longer be opened.

**Impact:** A user who restores from an automatic backup may silently lose recent edits. A user hit by a faulty migration, or who rolls back the app, has no automatic way back unless they had opted into backups. This is a data-integrity risk on the household's only copy of plan data, which matters for a non-expert user who will not know to make manual copies.

**Affected workflows:** automatic and manual local backups; restore from backup; app upgrade / rollback; Load Saved Plan

**Root cause:** Two backup implementations grew separately. The upgrade path was designed for atomic steps, not for reversibility.

**Options and tradeoffs:**

1. Use the SQLite backup API (reuse plan_db_replace._backup_with_api) in run_backup, and check the checkpoint result. When _check_and_migrate finds version < current on a real file, write a one-time copy (for example into plan_paths(...).backups_dir) before migrating.
2. Only switch run_backup to the backup API and leave upgrades as they are. This fixes the silent-incomplete-backup risk only.
3. Enable daily backups by default instead. More coverage, but the copy method stays unsafe.

**Recommendation:** Take option 1. Both parts are small, and they reuse code and a folder layout that already exist.

**Dependencies:** ARC-003 (so that backup or pre-upgrade copy failures are logged)

**Implementation considerations:** The pre-upgrade copy must not run for :memory: stores or read-only opens, and it needs a retention cap. The backup API holds a read transaction, so a long build write can delay it, but it never produces a torn copy.

**Risk of change:** Low to medium. The change touches the open path of every store.

**Verification method:** Unit test: hold an open write transaction or a reader on a WAL database, run run_backup, and assert that the backup contains every committed row. Unit test: open a v23 fixture and assert that a pre-upgrade copy exists at v23.

**Adversarial verification:** Code facts confirmed. src/local_backup_scheduler.py:151-160 checkpoint_sqlite ignores the wal_checkpoint(FULL) result row and swallows all exceptions. run_backup (309-350) then copies only the main file with shutil.copy2 and records a sha256 manifest. BackupPolicy.enabled defaults to False (27). src/plan_db_replace.py:133-142 _backup_with_api uses sqlite3 backup() and is not reused. src/stores/db.py:1-8 states 'There is no downgrade', and stores/db.py:46 sets WAL mode. src/stores/_base.py:94-113 migrates in place on every writable open with no copy, and read-only opens refuse older versions. broker_repo.py:59-60,82-83 use INSERT...SELECT plus DROP TABLE. plan_paths has no caller in src apart from re-exports and docstring references. Reason for the downgrade to partial: the data-loss trigger is conditional and was not demonstrated. Python's sqlite3.connect sets a default 5-second busy timeout, so FULL waits for contending readers or writers before it gives up. Backups are opt-in, which shrinks exposure. The per-migration transaction (db.py) also means a failed migration step leaves the file at the last good version, which softens the 'faulty migration' half. The rollback/no-pre-upgrade-copy half is fully confirmed.

### ARC-005 — The frontend 'ratchet' line ceiling is raised during feature work and the decomposed modules are becoming new monoliths

| Field | Value |
|---|---|
| Expert | architect |
| Category | modularity/maintainability |
| Severity | medium |
| Confidence | high |
| Inspection status | finding_identified |
| Verification status | confirmed |
| Linked implementation items | W1-01, W1-08, W4-06 |
| GitHub context | PR #390 (confirmed); PR #388 (contextual_only) |

**Evidence**

- `tests/test_frontend_size_ratchet.py:1-18, 186, 695` — module docstring / DASHBOARD_JS_MAX_LINES / TOTAL_JS_MAX_LINES — tests/test_frontend_size_ratchet.py:8-18 — the docstring says 'The ceiling only ever moves DOWN ... the only supported way to change it'. Line 695 sets TOTAL_JS_MAX_LINES = 43_777.
- `tests/test_frontend_size_ratchet.py:695` — git log -L695,695 — Local git history of that line shows the ceiling going up in feature commits: 42,502 (e77c2975, 2026-11-03) -> 42,531 -> 42,570 -> 42,576 -> 42,579 -> 42,609 -> 43,298 (61a9d7f2, #388) -> 43,620 (425fd97a, nav redesign) -> 43,401 -> 43,752 -> 43,762 -> 43,818 (0bbfb472) -> 43,813 -> 43,777 (2c293e62, after removing 237 blank lines). That is a net rise of about 1,275 lines in one week.
- `frontend/js/dashboard_decomp_row_model.js:1-5974` — file length — wc -l: dashboard_decomp_row_model.js is 5,974 lines (the project CLAUDE.md table says 5,188), dashboard_decomp_housing_optimizer.js is 2,832 (table says 1,984) and dashboard.js is 6,474. Total frontend/js is 43,763 lines.
- `frontend/js/dashboard_decomp_local_backups.js:136-147` — bare-global bridge comment — frontend/js/dashboard_decomp_local_backups.js:136-147 — cross-module calls still go through bare globals (for example maybeRunLocalBackup called from row_model), so the 'decomp' files are coupled through a shared global namespace.

**Observed behavior:** The guard meant to force extraction is treated as a budget that each feature PR raises (PR #390 states it raised the ceiling from 43,298 to 43,620). The growth has moved into the 'decomp' files that were created to shrink dashboard.js.

**Impact:** Feature work in the main UI keeps landing in very large files coupled through globals. This raises regression risk, slows review, and reduces the value of the usability work the system relies on. The agent guidance table in CLAUDE.md, used to scope reads, is now stale by 800-850 lines on two files.

**Affected workflows:** all dashboard UI changes; Sales Ledger, Holdings, Year-End and nav features

**Root cause:** The ratchet caps only the total plus dashboard.js. It has no per-file cap on the decomp modules, and the rule against raising it is enforced only by convention.

**Options and tradeoffs:**

1. Add per-file ceilings for the decomp modules over about 1,500 lines and require a recorded reason line next to any ceiling increase, so a raise is a visible decision.
2. Plan a focused extraction of dashboard_decomp_row_model.js (for example by feature area) and lower the ceilings afterwards.
3. Accept the growth and rename the guard a budget, so the docstring matches practice.

**Recommendation:** Take options 1 and 2 together: per-file caps stop the shift of growth into the decomp files, and one scoped extraction pays down the current excess. Update the CLAUDE.md large-file table at the same time.

**Dependencies:** Usability findings that add UI will compete for the same line budget

**Implementation considerations:** Python tests that read panel JS as text constrain where code can move (see project CLAUDE.md). Check those before extracting.

**Risk of change:** Medium for the extraction (UI regressions). Low for the guard change.

**Verification method:** Static: per-file wc -l against the new ceilings. Run the existing frontend Node tests and Playwright e2e locally after the extraction.

**Adversarial verification:** tests/test_frontend_size_ratchet.py:1-18 docstring says 'This is a ratchet, not a budget. The ceiling only ever moves DOWN'. Line 186 is DASHBOARD_JS_MAX_LINES = 6_477 and line 695 is TOTAL_JS_MAX_LINES = 43_777. These are the only two MAX_LINES constants, so there is no per-file cap on the decomp modules. `git log -L695,695` confirms rises in feature commits: 42,502 (e77c2975) up to 43,298 (61a9d7f2, #388), 43,620 (425fd97a), 43,818 (0bbfb472), and back down to 43,777 (2c293e62). The history before that also shows rises from 41,7xx. wc -l gives row_model 5,974, housing_optimizer 2,832, dashboard.js 6,474, and a frontend/js total of 43,763, which matches the finding and shows the CLAUDE.md table is stale. local_backups.js:136-147 confirms the bare-global bridge. I did not open the PR #390 text.

### DOC-001 — Contextual help for key pages is stitched-together text from retired sub-pages, with undefined jargon and no definition of the two headline result measures

| Field | Value |
|---|---|
| Expert | documentation |
| Category | clarity-terminology |
| Severity | medium |
| Confidence | high |
| Inspection status | finding_identified |
| Verification status | confirmed |
| Linked implementation items | W2-08 |
| GitHub context | PR #268 (confirmed) |

**Evidence**

- `frontend/js/help_registry.js:1-5` — file header — Says the help text is written for a high-school reader with little financial experience. That is the standard the entries below fall short of.
- `frontend/js/help_registry.js:248-255` — HELP_PAGES.strategy_optimize — The Optimize 'whatFor' runs to about 200 words. It glues together several 'This page ...' sentences that describe former separate pages (relocation state, portfolio assumptions, allocation target, withdrawal order). It uses the undefined abbreviations TNW and KPIs and the term 'sleeve'. 'terms' lists only 2 glossary entries.
- `frontend/js/help_registry.js:140-147` — HELP_PAGES.spending_core — The Spending Model 'whatFor' (167 words) includes sentences from the old Housing, Large Discretionary and Travel pages ('This page captures all housing-related costs...', 'Travel is the only editable source...'). It also uses 'canonical category tree' and refers to 'Spending Categories', which is no longer a page title.
- `frontend/js/help_registry.js:6-102` — GLOSSARY — 91 entries. None defines terminal net worth or probability of success, even though TNW appears 9 times in the registry and line 485 expands it only once, in a section note.
- `documentation/future/page_help_review.md:1-14` — merge method — Page records were built by keeping or merging source sentences so no fact was lost ('dropped' was used only for repetition). That method produced the concatenated wording.
- `frontend/js/dashboard.js:14-185` — STEPS titles — No step is titled 'Spending Categories' or 'Income & Expense Transactions'. The registry still uses both names (7 and 3 times).

**Observed behavior:** The help panel, which opens by default on pre-build pages, shows very long multi-topic paragraphs for Optimize, Spending Model, Stress Test and Build & Results. Several slots exceed 100 words, and some sentences say 'This page' about pages that no longer exist. The text uses abbreviations and jargon that the glossary does not define, and leaves out definitions of the two outcome measures every page refers to.

**Impact:** A 60-year-old non-expert reading the help for the most decision-heavy page (Optimize) meets 200-word blocks describing things not on screen, plus undefined shorthand (TNW, KPIs, sleeve). That raises cognitive load and makes it easy to misread what a lever does. It also undercuts the help system's own plain-English promise.

**Affected workflows:** Optimize levers; Spending Model setup; Stress Test; Build & Results review; Contextual help panel

**Root cause:** Phase 2 fact-preserving merges folded legacy sub-page help into one record per page, and the Phase 5 content pass did not restructure the longest records or add glossary terms for the headline metrics.

**Options and tradeoffs:**

1. Rewrite the 4-6 longest page records into short page-scoped text (purpose, what to enter, what it changes), move sub-page detail into HELP_SECTIONS, and add glossary entries for terminal net worth, probability of success, allocation sleeve and KPI.
2. Keep the records but add a length and abbreviation guard (similar to the existing ui_prose_guard) that flags help slots over about 80 words or undefined abbreviations, then fix the flagged entries incrementally.
3. Add glossary entries only and spell out TNW everywhere: low effort, but leaves the stitched multi-page paragraphs in place.

**Recommendation:** Option 1 for Optimize and Spending Model now, with Option 2's guard added so the problem does not come back.

**Dependencies:** page_help_drafts.json and tools/page_help_ledger.py check --strict must accept the reworded records (accepted_losses); plain_english_help.test.mjs glossary/terms contract

**Implementation considerations:** Facts dropped from page records should move into section-level help, not disappear. The ledger tool supports accepted_losses for this. Coordinate with the usability reviewer on how long a panel slot should be.

**Risk of change:** Low; text-only change in the help registry, guarded by existing frontend tests on glossary/terms consistency.

**Verification method:** Word-count each HELP_PAGES slot, and check that every abbreviation used is either defined in GLOSSARY or spelled out. Read the Optimize and Spending Model panels in the running app at 1600px and below 1180px.

**Adversarial verification:** I opened frontend/js/help_registry.js. Lines 1-5 set the high-school-reader standard. strategy_optimize (lines 248-255): whatFor joins several 'This page ...' sentences from former pages (relocation state, portfolio assumptions, allocation target, withdrawal order). connections uses 'KPIs', options uses 'sleeve', impact uses TNW, and terms has only 2 entries. spending_core (lines 140-147) uses 'canonical category tree' and 'Spending Categories', and grep counts 7 uses of 'Spending Categories' in the registry, none of which matches a STEPS title in frontend/js/dashboard.js (lines 21-183). Grep found no glossary entry for terminal net worth or probability of success. One correction: TNW is also expanded inline at line 128 ('final net worth (TNW)'), not only at line 485, so the 'expanded only once' detail is slightly wrong. The core claim still holds. I did not open page_help_review.md lines 1-14 to check the merge method, and I did not count words per slot. Medium severity is reasonable for a text-only usability defect.

### DOC-002 — End-user README and the Plan Status (Welcome) page point to page names and locations that the November nav redesign retired

| Field | Value |
|---|---|
| Expert | documentation |
| Category | accuracy-discoverability |
| Severity | medium |
| Confidence | high |
| Inspection status | finding_identified |
| Verification status | confirmed |
| Linked implementation items | W2-09 |
| GitHub context | PR #390 (contextual_only) |

**Evidence**

- `documentation/reference/readme/README.md:6-8,38-42` — Where to start / Third-party import — Tells users to begin on the 'Welcome' page and says Account Reconciliation is 'under Reports & Review'.
- `frontend/js/dashboard.js:19-21,130-157` — STEPS — The first nav item is 'Plan Status' (group Plan Status). Account Reconciliation is in the group 'Track & Reconcile'. The report page is titled 'Build & Results'.
- `frontend/js/dashboard_decomp_checklist_closeout.js:285` — Plan Status pane HTML — The pane header is still labelled 'Welcome'. The 'Final review' card says 'Open Reports & Review. Check the Preflight tab'. The 'Spending flow' card names 'Spending Categories', 'Housing, Wellness, and Travel are authoritative detail pages' and 'Income & Expense Transactions'.
- `frontend/js/dashboard_decomp_checklist_closeout.js:1234` — comment — 'Reports & Review redesign: no tab strip', so there is no Preflight tab to open.
- `documentation/reference/NAV_FEATURE_MAP.md:84-88` — redirect table — Housing, Wellness, Travel, the YTD transactions page and 'review' are now redirects into Spending Model, Actual Spending and Build & Results.
- `tests/test_readme_end_user_feature_currency_regression.py:31,62` — SCREEN_NAMES — Checks only that four screen names exist as frontend titles. It does not check the group a page sits under or the 'Welcome' start-page name, which is why these stale locations can go unnoticed.

**Observed behavior:** The README and the first screen the user sees give directions that no longer match the nav: a 'Reports & Review' heading, a Preflight tab and stand-alone Housing, Wellness and Travel pages that no longer exist. The nav calls the first page 'Plan Status', but its header says 'Welcome'.

**Impact:** A non-expert following the on-screen 'Final review' steps or the README looks for headings and tabs that are not there. On a first-run screen that weakens trust and slows wayfinding.

**Affected workflows:** First run / orientation; Final review and build; Account reconciliation; Spending setup

**Root cause:** The 2026-11-04 left-nav regroup and the earlier Reports redesign updated STEPS and NAV_FEATURE_MAP but not the static Plan Status cards or the README location phrases. The README currency test checks names only, not locations.

**Options and tradeoffs:**

1. Update the README and Plan Status cards to the current nav (Plan Status; Analyze > Build & Results; Track & Reconcile > Account Reconciliation; Spending Model accordions; Actual Spending tabs), and extend the currency test to check group placement.
2. Generate the Plan Status orientation cards from STEPS and HELP_PAGES so the names cannot drift, and keep the README to stable top-level directions only.

**Recommendation:** Option 1 now (a small text fix). Consider Option 2 if nav changes keep happening.

**Dependencies:** DOC-003 (Concepts Guide uses the same retired names)

**Implementation considerations:** Rule from the project CLAUDE.md: new tests must not assert string literals against frontend source text. Any extended check should use the Node vm sandbox or Playwright rather than grepping JS source.

**Risk of change:** Low; text changes only.

**Verification method:** Walk the README and Plan Status card directions against the running app's nav in both Set up and Maintain modes.

**Adversarial verification:** documentation/reference/readme/README.md lines 6-8 say to start on the 'Welcome' page, and line 41 says Account Reconciliation is 'under Reports & Review'. In frontend/js/dashboard.js, STEPS starts with id 'start', group 'Plan Status', title 'Plan Status', and Account Reconciliation sits in the 'Track & Reconcile' group. In dashboard_decomp_checklist_closeout.js, line 285 (renderWelcome) has the eyebrow 'Welcome' and contains 'Reports & Review', 'Preflight tab', 'Spending Categories', 'Housing, Wellness, and Travel are authoritative detail pages' and 'Income & Expense Transactions'. Line 1234 says 'Reports & Review redesign: no tab strip'. tests/test_readme_end_user_feature_currency_regression.py SCREEN_NAMES checks names only, not locations. I did not open NAV_FEATURE_MAP lines 84-88. It overlaps with DOC-003 but is a separate defect (README and first-run screen, not the Concepts Guide).

### DOC-003 — Concepts Guide (the main plain-English end-user document) predates the nav redesign and new pages, and the app gives no usable way to open it

| Field | Value |
|---|---|
| Expert | documentation |
| Category | accuracy-discoverability |
| Severity | medium |
| Confidence | medium |
| Inspection status | finding_identified |
| Verification status | confirmed |
| Linked implementation items | W3-10 |
| GitHub context | PR #235 (confirmed) |

**Evidence**

- `documentation/reference/Retirement_Planner_Concepts_Guide.docx:word/document.xml (paragraphs 96-498 of 628)` — 'Find it:' lines — Uses screen names that no current STEPS title matches: 'Other Assets and Liabilities' (6 uses), 'SS, Pensions & Annuities' (5), 'Reserve Requirements', 'Data & Maintenance', 'Workbench', 'Balance Sheet', 'Model Constants'. There is no mention of Investment Sales Ledger, Year-End Transition, Account Tax Basis, Checking & Savings or wash sales.
- `frontend/js/dashboard.js:14-185` — STEPS titles — Current titles are Social Security & Pensions, Other Assets & Debts, Cash Reserves, Planning Workbench, Data & Backups, plus the four newer pages listed above.
- `frontend/js/dashboard_decomp_checklist_closeout.js:289` — Help: Concepts Guide card — The only in-app pointer is plain text ('Open documentation/reference/Retirement_Planner_Concepts_Guide.docx in the application folder with Word'). There is no link or button.
- `documentation/DOCUMENTATION_INDEX.md:14` — reference table — Says the guide is pointed to from the app's 'Data & Maintenance page'. That page name is retired; the page is now Data & Backups.
- `documentation/reference/readme/README.md:9-12` — Concepts Guide pointer — Says it is listed on Settings -> Data & Backups, which disagrees with the index.

**Observed behavior:** Git history shows the guide last changed on 2026-10-20, before the 2026-11-03/04 page additions and nav regroup. The PR #235 author recorded that its 'Find it' labels were never walked against the running app. Users reach it only by finding a repository path by hand and having Word installed.

**Impact:** The document meant for non-experts sends them to screens that do not exist and says nothing about the newer tax-sensitive pages (sales ledger, year-end, tax basis). Because it is hard to open, most users will never benefit from it.

**Affected workflows:** Learning the settings; Finding a field; Tax-lot and year-end workflows

**Root cause:** The guide is a binary Word file maintained by hand, outside the help registry, with no check that its labels are current. The in-app card was written as instructions, not as a link.

**Options and tradeoffs:**

1. Refresh the guide's 'Find it' labels and add sections for the new pages, add a currency check that extracts document.xml text and compares screen names with STEPS titles, and make the in-app card open the file (or an HTML export) through a server route.
2. Retire the .docx as the primary end-user reference: generate an HTML concepts page from the help registry glossary and field help, served in-app, and keep the Word file as a print export.
3. Leave it in place but mark the guide's version date and add a 'screen names may have changed' note: lowest effort, does not fix discoverability.

**Recommendation:** Option 2 if the help registry is to remain the one source of truth (it already holds the glossary). Otherwise Option 1.

**Dependencies:** DOC-001 (registry content quality); DOC-002 (same retired names)

**Implementation considerations:** Whether the packaged build or release zip includes documentation/ was not confirmed: retirement_planner.spec bundles only frontend, tools and src. Check this before relying on an in-app file-open route.

**Risk of change:** Low for content; moderate for a new file-serving route (it must stay local-only).

**Verification method:** Extract the guide text and diff every 'Find it' screen name against STEPS titles. Click through the in-app pointer on a packaged build.

**Adversarial verification:** I extracted word/document.xml from the Concepts Guide. It has 'Other Assets and Liabilities' 6 times, 'SS, Pensions' 5, 'Reserve Requirements' 1, 'Data &amp; Maintenance' 1, 'Balance Sheet' 1 and 'Model Constants' 2. It has zero mentions of Sales Ledger, Year-End, Tax Basis, Checking or wash. Git shows the last change on 2026-10-20 (9a92325d). 'Workbench' (3 uses) is a weak example, because the current title 'Planning Workbench' contains it. The in-app 'Help: Concepts Guide' card at checklist_closeout.js line 289 is plain text with no link. DOCUMENTATION_INDEX.md line 14 says 'Data & Maintenance page', while README lines 9-12 say Settings -> Data & Backups, so the two disagree as claimed. Not verified: the PR #235 author note. Also not verified: whether documentation/ ships with the packaged build; I saw only that the spec builds app_datas and did not inspect it. I lowered confidence to medium because the discoverability impact depends on how the app is packaged, which is unconfirmed.

### DOC-004 — Design-document Status lines and folder placement cannot be trusted: shipped work is still marked unmerged, in draft PRs, or planned

| Field | Value |
|---|---|
| Expert | documentation |
| Category | document-status-accuracy |
| Severity | medium |
| Confidence | high |
| Inspection status | finding_identified |
| Verification status | confirmed |
| Linked implementation items | W3-08 |
| GitHub context | PR #391 (contextual_only); PR #276 (contextual_only); PR #288 (contextual_only) |

**Evidence**

- `documentation/DOCUMENTATION_INDEX.md:3-8,26-32` — layout rule — Defines future/ as 'planned, not yet built' and archive/ as 'shipped, superseded or historical', and tells readers to read each file's Status line first.
- `documentation/future/superpowers/plans/2026-10-26-trends-time-scope-design.md:3` — Status — Reads 'implemented (branch trends-time-scope ...; not yet merged)'. Git log shows d5e63eb3, 'Financial Trends: one time scope ... (#276)', on main.
- `documentation/future/superpowers/plans/2026-10-27-trends-drilldown-reconciliation-design.md:4` — Status — Reads 'implementation in draft PRs #286 and #288'. Git log shows 28f0dee5, '... holdings drill-down ... (#288)', merged.
- `documentation/future/superpowers/plans/2026-11-04-left-nav-redesign-followups.md:3` — Status: planned — Git log shows 85ad4ad8 'Left nav follow-ups A, B, E' and merge 04c466db (#391) on main.
- `documentation/future/page_help_review.md:1` — Status — Reads 'draft for review ... nothing applied to the app yet'. The parent plan, 'documentation/future/Contextual Help Panel Design and Implementation plan.md', lines 1-20 and 140, says Phases 0-5 are implemented and the registry is now the source.
- `documentation/future/WI-033_glossary_draft.md:1-20` — Status: implemented — One of at least 10 future/ documents marked implemented. Others include trends-remote-access, annuity-plan-values (PR #328), financial-insight-readability, recent-projections and ui_prose_inventory_summary. All contradict the future/ = not-built rule.
- `documentation/future/superpowers/plans/2026-09-09-dashboard-js-modularization-design.md:1-20` — Status — Says it is planned but admits parts may already be done ('Confirm before acting on it'). Status is uncertain.

**Observed behavior:** documentation/future/ mixes not-built plans with merged features. Several Status lines still say 'not yet merged', 'in draft PRs' or 'planned' for work now on main. The inventory stage counted 35 of 126 design and implementation documents as status-uncertain.

**Impact:** Developers and agents treat Status as the deciding fact (the index says so). Stale lines lead to re-implementing shipped work, or to trusting a 'planned' doc that no longer describes the code. They also weaken document-eligibility decisions in reviews such as this one.

**Affected workflows:** Planning new work; Agent sessions choosing what to build; System review document eligibility

**Root cause:** Status lines are updated when a branch is built, not when it merges. Nothing moves shipped documents to archive/. The tested Status rule checks only that a status word is present, not that it is accurate.

**Options and tradeoffs:**

1. Do a one-time reconciliation pass: correct each Status against git merge history and move implemented or merged documents to archive/superpowers/ with a pointer, keeping in future/ only documents whose remaining open items are named in the Status line.
2. Keep documents where they are but add a status vocabulary rule: 'implemented' requires a merge reference (PR #N on main), and add a periodic check that flags 'not yet merged' or 'draft PR' text whose PR is merged.
3. Accept the drift and change the index text to say future/ holds 'recent and planned' work: cheap, but removes the signal folder placement was meant to give.

**Recommendation:** Option 1 now, plus the lightweight half of Option 2 (merge reference required for 'implemented').

**Dependencies:** test_design_documents_declare_a_status (allowed status words); DOC-006 (open sub-items currently live only in Status lines)

**Implementation considerations:** Some future/ documents are 'implemented' with live open sub-items: the Fidelity 1099-B parser, owner Phase 5 tasks and the pair-status turn-on. Move those open items to the backlog before archiving the parent document.

**Risk of change:** Low (docs-only), but the archive move changes paths cited from other documents and memory files.

**Verification method:** For each future/ document, compare its Status with git log --merges for the named branch or PR. After the fix, count documents in future/ marked implemented (target: 0, or each one names its open items).

**Adversarial verification:** The Status lines read as cited: trends-time-scope says 'implemented ... not yet merged', trends-drilldown says 'implementation in draft PRs #286 and #288', left-nav-followups says 'planned', and page_help_review.md says 'nothing applied to the app yet'. git log on main shows d5e63eb3 (#276), 28f0dee5 (#288), 85ad4ad8 and merge 04c466db (#391). DOCUMENTATION_INDEX.md lines 3-8 define future/ as 'planned, not yet built'. Grep finds 15 files under documentation/future with 'Status: implemented', which supports 'at least 10'. I did not reproduce the '35 of 126' inventory figure or open the contextual-help parent plan; neither is needed to establish the defect. Medium is reasonable because this affects developers and agents, not end users.

### DOC-006 — BACKLOG.md, the repository's only work tracker, is not receiving deferred items, including ones that wait on owner or CPA approval with tax impact

| Field | Value |
|---|---|
| Expert | documentation |
| Category | work-tracking-discoverability |
| Severity | medium |
| Confidence | high |
| Inspection status | finding_identified |
| Verification status | confirmed |
| Linked implementation items | W1-07 |
| GitHub context | PR #418 (contextual_only) |

**Evidence**

- `documentation/reference/BACKLOG.md:3-7,17-26` — tracker table — Says 'The repository has no GitHub issue tracker, so this file is the tracker'. It has 8 items and last changed on 2026-10-20 (82a69a40).
- `documentation/future/superpowers/plans/2026-11-04-left-nav-redesign-followups.md:11,57-58` — Decision 1 / Backlog item — Says 'Add a backlog item: build real inputs on Work Income' for Business Succession. BACKLOG.md does not mention succession.
- `documentation/future/superpowers/plans/2026-10-28-realized-sales-ledger-design-and-plan.md:3` — Status — The deferred Fidelity 1099-B parser (waiting on a sample, about February 2027) and automatic wash-sale disallowance and basis adjustment are recorded only here.
- `documentation/future/superpowers/plans/2026-11-03-cash-pair-status-tax-worked-example.md:5` — Status — Records that the pair-status tax floor is 'implemented, default OFF ... turn-on not approved', a pending owner decision that is not in the backlog.
- `documentation/future/superpowers/plans/2026-10-31-account-number-protection-design-and-plan.md:3` — Status — Says the redaction tool is 'built but not yet run on the live plan' and that Phase 5 is an owner task. Neither is in the backlog.

**Observed behavior:** Open and deferred work, including owner-approval gates on tax behaviour, is spread across long Status lines in about 30 plan documents. The single tracker the repository names holds 8 items, unchanged for three weeks of heavy merging.

**Impact:** Nobody can see in one place what is still undecided. That raises the risk that an approval gate (pair-status floor, wash-sale CPA confirmation from PR #418) or a privacy follow-up (redaction run) is forgotten.

**Affected workflows:** Work planning; Release readiness; Owner approvals for tax rules

**Root cause:** There is no step that copies a plan's 'not built' or 'awaits approval' items into BACKLOG.md when the plan's Status changes. The backlog's own rule ('when an item is picked up, move it to a spec') covers outflow only, not inflow.

**Options and tradeoffs:**

1. Add the missing items now and adopt a rule: any Status line that says 'not built', 'deferred', 'awaits' or 'owner task' must have a matching BACKLOG row, enforced by a small docs check.
2. Move tracking to GitHub issues (the repository has none today), with BACKLOG.md generated from or linking to them.

**Recommendation:** Option 1. It fits the current single-maintainer workflow; Option 2 is worth revisiting if collaborators join.

**Dependencies:** DOC-004 (archiving implemented plans requires their open items to live elsewhere first)

**Implementation considerations:** Follow the backlog's own DOC-009 numbering note: write 'PR #N' or 'item #N' explicitly.

**Risk of change:** Low.

**Verification method:** Search future/ Status lines for not built/deferred/awaits/owner and confirm each has a BACKLOG row.

**Adversarial verification:** BACKLOG.md lines 3-7 call itself the tracker, its last change was 2026-10-20 (82a69a40), and grep finds no mention of succession, wash, 1099-B, pair-status or redaction. The left-nav-followups plan, lines 11 and 57-58, explicitly says to add a Business Succession backlog item. The sales-ledger Status (line 4, not line 3 as cited) lists the Fidelity 1099-B parser and automatic wash-sale disallowance as not built. The pair-status worked example line 5 says 'turn-on not approved'. The account-number plan Status (line 5) says the redaction tool is 'built but not yet run on the live plan' and that 'Phase 5 is an owner task'. The line citations are off by one or two, but the substance holds. I did not verify the PR #418 CPA confirmation reference. Medium fits because the untracked items include pending tax-behaviour approvals.

### FIN-001 — The QBI (Section 199A) deduction is a flat 20% of business income with none of the statutory limits

| Field | Value |
|---|---|
| Expert | financial_planner |
| Category | financial-correctness |
| Severity | medium |
| Confidence | high |
| Inspection status | finding_identified |
| Verification status | confirmed |
| Jurisdiction | US federal (IRC 199A) |
| Rule year | 2018-present (made permanent by P.L. 119-21; the threshold phase-in range widens from 2026, and the minimum deduction applies to taxable years beginning after 2025) |
| Linked implementation items | W2-03, W3-02 |
| GitHub context | PR #419 (contextual_only) |

**Evidence**

- `src/projection_stages/income.py:249-251` — apply_income (sole_prop branch) — qbi_ded = qbi_base * 0.20 with qbi_base = net_se - half_se_ded - sehi_ded; there is no taxable-income cap, threshold or SSTB test
- `src/projection_stages/income.py:282-284` — apply_income (S-corp branch) — qbi_ded = max(0, (distribution - sehi_ded) * 0.20); there is no 50%-of-W-2-wages limit even though the S-corp salary is known in the same block
- `src/projection_stages/income.py:370-371` — apply_income — The only later change to qbi_ded is the sole-proprietor 401(k) reduction
- `src/projection_stages/roth_conversion_and_agi_tax.py:883-886` — apply_agi_and_tax — ded += qbi_ded and then taxable_inc = max(0, agi - ded), with no cap of 20% of (taxable income before QBI minus net capital gain)
- `src/parsing/client_sections.py:477` — parse_client — qbi_eligible defaults TRUE. It is the only QBI input, so there is no field for SSTB status, W-2 wages or UBIA

**Assumptions:** How large the effect is depends on whether the household's taxable income during working years is above the 199A threshold (about $394,600 MFJ for 2025) and whether the business is a specified service trade or business (SSTB). Neither is known from the code. Rule type: hard-coded (rate 0.20 is a literal; no threshold, SSTB or wage inputs exist). Authority: statute (authoritative); the implementation is unverified.

**Observed behavior:** Whenever qbi_eligible is on, the engine deducts 20% of the QBI base in every working year, whatever the income level. Grep found no SSTB, threshold, W-2-wage or taxable-income limit anywhere in src/, and no limitation notice discloses this.

**Impact:** Above the threshold, an SSTB owner's deduction phases to zero. The engine still deducts 20%, so with $300k of QBI it understates federal tax by about $21k a year at 35%. For a non-SSTB S-corp paying a $100k salary, the 50%-of-wages limit caps the deduction at $50k instead of $60k, about $3.5k a year. Below the threshold, the missing taxable-income cap matters only in years when deductions are large relative to income. Lifetime tax, net worth, the Roth sizing headroom and Monte Carlo replays all inherit the error. The commit message for PR #419 cites a real plan year with $640k of taxable income, so this household may be above the threshold. That income was not shown to come from business years.

**Affected workflows:** Self-employment and S-corp income years; Federal tax and taxable income; Roth conversion sizing during working years; Lifetime tax and terminal net worth

**Root cause:** QBI was modeled as a simple 20% rate on the base, and the statutory limitation layers were never added or disclosed.

**Options and tradeoffs:**

1. No credible alternative; this is a correctness defect.

**Recommendation:** Add two inputs: SSTB yes/no and, for the S-corp, the W-2 wages (already known as scorp_salary). Apply the threshold and phase-in, the SSTB phase-out, the greater of 50% of W-2 wages or 25% of wages plus 2.5% of UBIA, and the overall cap of 20% of (taxable income before QBI minus net capital gain). Take the 2026+ threshold and phase-in width from dated rows in tax_law_v10.json; the $394,600 MFJ figure in this finding is the 2025 threshold and is context only. Add OBBBA's minimum deduction (P.L. 119-21 sec. 70105: $400 when active QBI is at least $1,000, both indexed after 2026) as dated, indexed rows, applied regardless of the computed deduction. 'Net capital gain' in the overall cap is the section 1(h) amount, which includes qualified dividends. Until that is built, show a limitation notice when qbi_eligible is on. Qualified professional review required: a CPA should confirm the rule values and the household's SSTB status.

**Dependencies:** Dated 199A threshold and phase-in-width rows (2026+) in reference_src/tax_law_v10.json; Dated, indexed rows for the 2026+ minimum deduction ($400 when active QBI is at least $1,000); Golden-master re-pin process (tools/regen_golden_master.py measure first); CPA confirmation of rule values and SSTB status

**Implementation considerations:** The overall cap needs taxable income before QBI, which exists only after deductions in apply_agi_and_tax. Apply the cap there, not in income.py. The deduction stacks with the standard/itemized choice (ded = max(std, item) + qbi), so it should stay outside that max. LTCG and NIIT are resolved in a later fixed point (roth_conversion_and_agi_tax.py:901-924), so net capital gain, including qualified dividends, may not be final at line 883; the overall cap may need to run inside or after that fixed point. The minimum applies regardless of the computed amount, so the order of operations matters. The engine has no material-participation input, so the minimum's 'active QBI' test is assumed for an owner-operator.

**Risk of change:** Moderate. Engine output changes in every working year for qbi_eligible plans, and goldens must be re-pinned after one delta is checked by hand.

**Verification method:** Add closed-form unit cases: below the threshold; an SSTB inside and above the phase-in range; a non-SSTB S-corp where the wage limit binds; a low-income year where the taxable-income cap binds; a 2026+ minimum-deduction case where active QBI is $1,000-$2,000 so 20% falls below $400 and the $400 floor applies; and an overall-cap case with qualified dividends counted as net capital gain. Check one year of the real plan by hand against Form 8995-A.

**Adversarial verification:** Opened src/projection_stages/income.py:249-251 and 282-284. Both branches use a literal qbi_base*0.20. Lines 370-371 only apply the sole-prop 401(k) reduction. roth_conversion_and_agi_tax.py:883-886 adds qbi_ded after max(std, item) with no cap tied to taxable income. client_sections.py:477 defaults qbi_eligible to TRUE. Further evidence I found: client_sections.py:1295 parses c['scorp_qbi_phaseout'] (qbi_phaseout_applies), and grep shows nothing in src/ reads it. So the input exists and is ignored, which strengthens the finding. Also, sheets_strategy.py:162 describes the S-corp QBI as '20% of W-2 wages + allocable basis', which contradicts what the engine does. Jurisdiction (IRC 199A) and rule years are stated. The impact figures depend on the household's income and SSTB status, which are unknown. Medium severity is kept because the error grows with income and the household may be above the threshold. Planner sign-off (2026-11-10): PC-06 upheld on re-verification. The W3-02 rule list gains the 2026+ minimum deduction, the section 1(h) definition of net capital gain (including qualified dividends) and dated 2026+ threshold and phase-in rows, with matching closed-form tests. Rule values were not checked against primary sources; the CPA gate stays. Severity and confidence unchanged.

### FIN-003 — The SALT deduction's state income tax is AGI x the flat state rate, so it counts income the state does not tax

| Field | Value |
|---|---|
| Expert | financial_planner |
| Category | financial-correctness |
| Severity | medium |
| Confidence | high |
| Inspection status | finding_identified |
| Verification status | partially_confirmed |
| Jurisdiction | US federal itemized deduction (IRC 164) interacting with state income tax (Illinois and the other modeled states) |
| Rule year | 2025-2029 enhanced-cap window (full effect while MAGI is below the phase-down threshold, about $505k in 2026; partial up to the $10k floor at about $606k in 2026 and $626k in 2029); from 2030 only where the modeled state tax plus property tax is below $10k and the household itemizes |
| Linked implementation items | W3-03 |

**Evidence**

- `src/projection_stages/roth_conversion_and_agi_tax.py:761-777` — apply_agi_and_tax — il_tax_est = agi * rate (0.0495 fallback), salt_gross = il_tax_est + prop_tax_yr, salt = min(salt_gross, salt_cap(...))
- `src/core.py:1052-1109` — state_income_tax — The engine's actual state tax leaves out retirement distributions, Roth conversions and Social Security when exempt_retirement and exempt_ss are set, and it uses graduated brackets for CA and NY
- `reference_src/state_tax.csv:2` — Illinois row — Illinois has exempt_retirement=TRUE and exempt_ss=TRUE, so IRA withdrawals, RMDs and conversions are not taxed by Illinois
- `src/projection_stages/roth_conversion_and_agi_tax.py:876-881` — apply_agi_and_tax — item_ded = salt + char + mortgage interest + medical + senior bonus, and ded = max(std_ded, item_ded)
- `reference_src/tax_law_v10.json:386-474` — salt_cap / salt_phasedown_threshold rows — The SALT cap is $10,000 for 2018-2024, 40,000 (2025), 40,400 (2026), 40,804 (2027), 41,212 (2028) and 41,624 (2029), then $10,000 again from 2030 with no end year; the phase-down threshold is $500,000 for 2025, grown 1% a year through 2029
- `src/core.py:1269-1296` — salt_cap — Above the base cap, the cap is max(cap - 0.30 x (magi - threshold), base_cap); from 2030 the cap equals the base, so a flat $10k is returned

**Assumptions:** The effect appears only when the household itemizes, or when the inflated SALT figure is what tips it into itemizing. The impact depends on the cap window: from 2030 the $10k cap makes the proxy irrelevant for homeowners whose property tax reaches $10k. Rule type: approximation hard-coded in the stage. Authority: unverified.

**Observed behavior:** The SALT component uses a state tax of AGI x rate. It is not the state tax the engine computes a few lines later. For an Illinois retiree with $300k of AGI that is mostly conversions and RMDs, the estimate is $14,850, while the modeled Illinois tax on the remaining investment income is about $1k.

**Impact:** The effect is concentrated in the 2025-2029 enhanced-cap window. For itemizers with MAGI below the phase-down threshold (about $505k in 2026), SALT can be overstated by roughly $10k-$15k in Illinois conversion and RMD years (capped by the $40,400 2026 cap), which understates federal tax by about $2.4k-$3.6k a year at 24%; the $300k-AGI Illinois retiree example sits below the threshold and keeps this full impact. Between the threshold and about $606k (2026) to $626k (2029) of MAGI the cap is only partly reduced, and above that the $10k floor applies. From 2030 the cap reverts to $10k, so the proxy changes nothing for homeowners whose property tax reaches $10k; the effect survives only for itemizing renters and low-property-tax households whose modeled state tax plus property tax is below $10k, chiefly in states that exempt retirement income. The inflated figure can also flip a household from the standard deduction to itemizing. The Roth optimizer sees the same understated tax, and the window coincides with the planned conversion years. Graduated states (CA/NY) get a flat-rate figure instead of their brackets.

**Affected workflows:** Itemized deduction and federal tax; Roth conversion years in states that exempt retirement income; State residency comparisons

**Root cause:** State tax is computed after the deduction step, so the SALT step uses a flat proxy and does not call state_income_tax.

**Options and tradeoffs:**

1. No credible alternative; this is a correctness defect.

**Recommendation:** Feed SALT from state_income_tax (or a prior-year actual, matching cash-basis deduction timing) using the same income classification the state-tax call uses, in every projection year (this also covers the post-2029 tail and the bracket mismatch in graduated states). Keep the cap logic unchanged. The fix is time-sensitive because its main window closes after 2029. Qualified professional review required: CPA, to confirm whether the SALT state-income-tax component should use current-year computed state tax or prior-year actual payments under IRC 164 cash-basis timing; the closed-form test expectations depend on that choice.

**Dependencies:** FIN-001 (shares the deduction block); CPA confirmation of SALT timing (current-year computed vs prior-year actual)

**Implementation considerations:** state_income_tax needs earned_net and the retirement and SS classification, and all of them are known before line 764. Computing the state tax once and reusing it removes the circularity. The DAF makeup and HSA correction sub-stages recompute item_ded and must reuse the same SALT.

**Risk of change:** Moderate. Itemizing households in states with retirement exemptions see federal tax rise. Re-pin goldens.

**Verification method:** Closed-form cases: (1) an Illinois large-conversion household pinned in 2026 with MAGI under $505k and high property tax, where the delta should be large (compare salt_gross with the computed state_tax plus property tax); (2) the same case at MAGI of $620k or more in 2026, where the delta should be zero because of the $10k floor; (3) a 2030-or-later homeowner with property tax of $10k or more, where the delta should be zero; (4) a 2030-or-later Illinois renter who itemizes, where the delta is non-zero and bounded by $10k minus the actual SALT. Then measure the deltas (expected mainly in 2025-2029 rows) and check one year by hand.

**Adversarial verification:** roth_conversion_and_agi_tax.py:761-777 computes il_tax_est = agi * rate and feeds it into salt_gross. core.py:1052-1109 state_income_tax leaves out retirement_dist+roth_conv and SS when exempt flags are set, and it uses brackets for graduated states. state_tax.csv row 2 confirms Illinois exempt_retirement=TRUE and exempt_ss=TRUE. The SALT proxy therefore counts income Illinois does not tax. One mitigation limits the impact: when the property tax alone already reaches the SALT cap, the overstatement has no effect, so households with large Illinois property tax may see no change. The effect is otherwise real for itemizers and households near the itemizing threshold. Medium is kept. Planner sign-off (2026-11-10): PC-01 partially upheld. The rule year is narrowed to the 2025-2029 enhanced-cap window plus a post-2029 tail for itemizers whose state tax plus property tax is below $10k (tax_law_v10.json:386-474; core.py:1269-1296). The planner's 'nothing in high-MAGI conversion years' claim holds only above about $606k-$626k of MAGI. The requested downgrade to low and the W3-03 move to P2 were not adopted: the per-year effect is 2-3x FIN-002's, it falls in the Roth-conversion years and skews the optimizer, it can flip a household into itemizing, and its post-2029 tail is open-ended, which findings-schema.md:44-45 treats as a meaningful functional issue. Severity stays medium (planner dissent recorded). PC-04 upheld: CPA review of SALT timing added. Verification status set to partially_confirmed: the code behaviour is confirmed, but the original 'All projection years' scope is partly refuted for post-2029 homeowners (PC-01 finding update; PC-04's 're-confirmed' concerns the code evidence only).

### FIN-004 — Illinois estate tax runs the old state-death-tax-credit table on the whole estate, with no federal-tax limit and no $60,000 adjustment

| Field | Value |
|---|---|
| Expert | financial_planner |
| Category | financial-correctness |
| Severity | medium |
| Confidence | low |
| Inspection status | requires_external_domain_verification |
| Verification status | partially_confirmed |
| Jurisdiction | Illinois (35 ILCS 405/2(b), referencing IRC 2011 as in effect Dec 31, 2001) |
| Rule year | Current Illinois law ($4M exclusion) |
| Linked implementation items | W1-07, W2-03, W4-01 |

**Evidence**

- `src/core.py:1298-1318` — state_death_tax_credit — This is the 2011(b) table keyed directly on the value passed in. No $60,000 is subtracted to get the adjusted taxable estate
- `src/core.py:1321-1338` — illinois_estate_tax — Once the estate is over the exemption, the code solves T = credit(gross - T) with no limit at the federal tax over a $4M exclusion. The docstring calls it a cliff
- `src/after_tax.py:729-783` — estimate_terminal_estate_tax — Illinois tax on state_taxable feeds terminal estate tax and Post-Tax Inheritance
- `src/engine_sections/roth_conversion.py:108-141` — _estate_tax_for_row — The Roth optimizer's estate penalty uses the same state calculation
- `src/planning_engines.py:568-600` — _roth_strategy_metrics — estate_tax_penalty = estate_mult x estimate_terminal_estate_tax(c, row with total_nw = 0.65 x PV-average + 0.35 x peak total_nw), discounted to plan start; estate_mult is 0 for OFF/MONITOR_ONLY, 1.0 for BALANCED (the default) and 2.0 for STRONG
- `src/planning_engines.py:614-645` — _roth_strategy_metrics — estate_component = -estate_tax_penalty (doubled under ESTATE_TAX_AWARE) is summed into score
- `src/engine_sections/roth_conversion.py:412, 455` — Roth candidate sweep — Candidates are ranked by (score, after_tax_terminal_nw, -lifetime_tax), so the score selects the conversion schedule

**Assumptions:** This reviewer understands Illinois tax as the IRC 2011(b) credit on the adjusted taxable estate (taxable estate less $60,000), limited to the federal tax computed with a $4M exclusion amount, with the interrelated deduction of the Illinois tax itself. That limit produces a steep phase-in above $4M, not a cliff. No primary source or Illinois Attorney General calculator was consulted in this run. Rule type: hard-coded table and method in code. Authority: secondary/unverified. An estate attorney must review.

**Observed behavior:** For a $4.1M Illinois taxable estate, the iteration converges to about $269k of tax. A calculation limited by the federal tax with a $4M exclusion would be on the order of 40% of the $100k excess before the interrelated deduction, about $40k. Above about $5M the credit table becomes the binding limit again, and the code then overstates by only the $60k adjustment (about $6.7k-$9.6k).

**Impact:** For Illinois estates between about $4M and $5M, terminal estate tax and Post-Tax Inheritance may be overstated by up to roughly $230k. That also inflates the CST-funding logic. The overstated estate tax also enters the Roth optimizer's objective (1.0x in the default BALANCED estate mode, 2.0x under STRONG, doubled again under ESTATE_TAX_AWARE, zero under OFF/MONITOR_ONLY). Where the blended estate exposure (0.65 x PV-average plus 0.35 x peak net worth, so households with a nominal terminal estate well above $5M can still land in the band) falls just above the Illinois exclusion, it can change which conversion schedule is recommended, and with it lifetime tax and terminal net worth.

**Affected workflows:** Estate and legacy metrics; Post-Tax Inheritance; Roth optimizer estate penalty; Roth conversion schedule selection; Credit-shelter trust analysis

**Root cause:** The credit was implemented without the 2011(e)-style limit, which Illinois carries by reference, and without the adjusted-taxable-estate definition.

**Options and tradeoffs:**

1. No credible alternative; this is a correctness defect.

**Recommendation:** Start the estate-attorney review, or a comparison against the Illinois Attorney General estate tax calculator, in Wave 1 as a W1-07 backlog gate, so its elapsed time runs in parallel with Waves 2-3. In the W2-03 disclosure bundle, label the Illinois estate figure as an unverified approximation that may overstate tax for estates just above $4M, pending attorney review, wherever it feeds Post-Tax Inheritance, the estate sheet or the Roth strategy rationale. Once the method is confirmed, implement: adjusted taxable estate = TE - 60,000; credit = min(table(adjusted TE), tentative federal tax on TE with a $4M exclusion amount); and solve the interrelated deduction. Add calculator-matched test points at $4.05M, $4.5M, $5M and $10M. Escalate W4-01 to P1 if the review confirms the federal-tax limit and the household's blended estate exposure lies within about $4M-$5M. Qualified professional review required: estate attorney.

**Dependencies:** Estate-attorney review or Illinois AG calculator comparison, started in Wave 1 as a W1-07 gate; W2-03 interim disclosure

**Implementation considerations:** The limit needs a section 2001 rate schedule, which the code does not have today (federal estate tax is a flat 40%). The NY branch is independent.

**Risk of change:** Low code risk. Estate figures move for Illinois households above $4M.

**Verification method:** Compare against the Illinois Attorney General calculator at several estate sizes, with an attorney's sign-off. Check that the W2-03 disclosure renders for Illinois residents whose blended exposure exceeds the Illinois exclusion while estate_tax_objective_mode is not OFF/MONITOR_ONLY. After the W4-01 fix, compare the selected Roth candidate before and after for a representative $4.1M-$4.5M Illinois household; W4-01 moves selected-candidate outputs as well as estate figures, so hand-verify one delta before any re-pin.

**Adversarial verification:** The code behavior is confirmed. core.py:1298-1318 applies the 2011(b) table to the raw value, and that table's 40,000 floor is the adjusted-taxable-estate table, yet no $60,000 is subtracted. core.py:1321-1338 solves T = credit(gross - T) with no limit tied to federal tax and calls the result a 'cliff' in its docstring. I recomputed credit(~3.83M) at about $269k, which matches the finding. after_tax.py:729-783 and roth_conversion.py:110-141 both feed the state calculation. The legal claim is that Illinois limits the credit to federal tax computed with a $4M exclusion, which would produce a phase-in rather than a cliff. I did not verify that against the statute or the Illinois AG calculator, and the finding admits the same. The missing $60k adjustment is the most likely error. The size of the overstatement in the $4M-$5M band depends on the unverified limit. This stays requires_external_domain_verification. Severity stays medium if the limit is confirmed; confidence is low. Planner sign-off (2026-11-10): PC-02 partially upheld. 'Lifetime spending results are not affected' was removed: the estate penalty enters the Roth candidate score (planning_engines.py:568-600, 614-645; roth_conversion.py:412, 455), so the overstatement can change the selected conversion schedule. Spending invariance was not verified, so no claim is made either way. MAXIMIZE_PTI is not cited because roth_conversion_policy.py:101-105 coerces it to BALANCED_RETIREMENT. An interim W2-03 disclosure and a Wave 1 start of the attorney review were added. The unconditional raise of W4-01 to P1 was not adopted (confidence low, magnitude unverified); a conditional escalation is recorded instead (planner dissent recorded). Severity medium and confidence low unchanged.

### FIN-005 — In-force life insurance is report-only: death benefits never reach the survivor and are left out of the estate-tax base, without telling the user

| Field | Value |
|---|---|
| Expert | financial_planner |
| Category | scope-workflow-gap |
| Severity | medium |
| Confidence | medium |
| Inspection status | finding_identified |
| Verification status | confirmed |
| Jurisdiction | US federal (IRC 101(a), 2042) and state estate tax |
| Rule year | Current law |
| Linked implementation items | W2-03, W4-04 |

**Evidence**

- `src/reporting/sheets_protection.py:1-14` — module docstring — The protection sheets 'do not feed the projection engine'
- `src/parsing/advanced_modules.py:131-146` — parse_advanced_modules — Owner, insured, beneficiary, policy_type, face_amount, cash_value_today, term_end_year, cash_value_growth_rate and owned_by_ilit are parsed into c['life_policies']
- `src/reporting/sheets_protection.py:53-110` — build_existing_life — The sheet shows inventory and coverage versus need only. No text tells the user the projection leaves the policies out
- `src/after_tax.py:746-783` — estimate_terminal_estate_tax — The estate base is total_nw plus business value. Life-insurance face is not added

**Assumptions:** Applies when the Existing Life Insurance module is on and policies are entered. Estate inclusion is ownership-based (IRC 2042), not ILIT-only: proceeds of a policy on the decedent's life are included when the decedent held incidents of ownership or the estate is the beneficiary; policies owned by a spouse, child, other third party or an ILIT are excluded; a policy the decedent owned on another person's life is included at its value, not its face (IRC 2033). A blank owner is treated as the insured (conservative). The IRC 2035 three-year rule for policies transferred shortly before death is not modeled. Reported PTI is measured at the plan-end row, so 'in force at the second death' means the death year the estate row stands for. Rule type: not modeled. Authority: statute.

**Observed behavior:** Grep found life_policies consumed only by the protection sheet and the module catalog. A death in the deterministic or Monte Carlo projection pays no death benefit into the survivor's accounts, and policies not owned by an ILIT are not included in the gross estate.

**Impact:** Survivor scenarios understate the survivor's assets by the face amount (conservative). Estate tax is understated only for in-force policies the last decedent owned on their own life (or with the estate as beneficiary) that pay at the measured death, which matters most against Illinois's $4M exclusion. Term policies whose term_end_year falls before the modeled second death have no estate effect. A user who enters policies can reasonably assume they are part of the survivor analysis.

**Affected workflows:** Survivor scenarios (either spouse's death); Estate tax and Post-Tax Inheritance; Life-insurance need analysis

**Root cause:** The protection modules were delivered as Phase 1 report-only builders, and the projection was never integrated.

**Options and tradeoffs:**

1. Option A: integrate. Pay a first-death benefit (term in force at the death year) tax-free into the survivor's or beneficiary's taxable or cash account in the death year, and do not add it to the estate base again, because it is already in total_nw at the terminal or second-death row. Add face to the estate base only for a policy on the last decedent's life where the decedent held incidents of ownership or the estate is the beneficiary (IRC 2042); exclude policies owned by a spouse, child, other third party or an ILIT; include a policy the decedent owned on another person's life at its cash value projected from cash_value_today with cash_value_growth_rate, not its face (IRC 2033). Stop premiums after the death or term end. This is most accurate but changes engine output.
2. Option B: disclose. Add a limitation notice and a sheet banner saying policies are inventory-only and not in survivor or estate results. Low effort, but results stay incomplete.
3. Option C: do B now and A later behind a module switch.

**Recommendation:** Option C. Ship the disclosure now, worded so it does not imply that every non-ILIT policy belongs in the estate. Then integrate behind the existing module switch using the ownership-based inclusion rule in Option A, with financial-planner review of beneficiary routing and of how free-text owner and insured values resolve to household members.

**Dependencies:** Owner, insured, beneficiary, term_end_year, cash_value_today, cash_value_growth_rate and owned_by_ilit already parsed (advanced_modules.py:131-146); A resolver from the free-text owner and insured strings to household members, with a documented default for blanks

**Implementation considerations:** Death years differ per Monte Carlo path (sample_death_year), so the benefit has to be applied per path, not replayed from the deterministic rows. The estate base comes from the terminal row (rows[-1]) for reported terminal estate tax and PTI and from the second-death row for the optimizer penalty (planning_engines.py:590-599, 649-650), so a benefit already paid into the survivor's accounts is in that base and must not be added again.

**Risk of change:** Option B low; Option A moderate (survivor and estate outputs change).

**Verification method:** Scenario tests: (1) a first-death payout to the spouse raises the survivor's balance by the face amount and the estate base by no more than that balance change (no double count); (2) a policy on the survivor's life, owned by the survivor and in force at the second death, adds its face to the estate base; (3) third-party-owned and ILIT-owned policies on the survivor's life add nothing; (4) a term policy with term_end_year before the second death adds nothing to the estate or the survivor's balance; and preferably (5) a decedent-owned policy on another person's life adds its projected cash value, not its face. Then measure, hand-verify one delta, and re-pin.

**Adversarial verification:** sheets_protection.py:1-14 says the sheets 'do not feed the projection engine'. advanced_modules.py parses face_amount and owned_by_ilit. Grep shows life_policies used only in data_io defaults, module_catalog.py:918, advanced_modules and sheets_protection. No engine stage reads it, and I found no death-benefit payout for life policies anywhere outside reporting. after_tax.py:746-783 builds the estate base from total_nw plus business value only. The catalog entry (module_catalog.py:913-926) states no limitation. Leaving the benefit out of survivor assets is a conservative error. Leaving it out of the estate base is not. Whether users assume the policies are integrated is inferred, so confidence is lowered to medium. Medium severity is kept because estate tax against Illinois's $4M exclusion can move materially. Planner sign-off (2026-11-10): PC-03 upheld. Option A, the assumptions, impact, dependencies and test requirements now use ownership-based IRC 2042 inclusion with no double count of a first-death payout already in total_nw (after_tax.py:746-783; advanced_modules.py:131-146). Severity, wave placement and effort unchanged.

### QA-003 — Server checks numbers only for 'number' and 'currency', so the 114 'dollars' fields and the /api/plan/forms path accept text

| Field | Value |
|---|---|
| Expert | quality |
| Category | input-validation |
| Severity | medium |
| Confidence | high |
| Inspection status | finding_identified |
| Verification status | confirmed |
| Linked implementation items | W2-02 |

**Evidence**

- `src/schema_registry.py:16-48` — validate_value — Numeric format checks run only for typ in {'number','currency'} (and the finite check for integer/year/number/currency/percent/pct). 'dollars' and 'decimal' get no format check. The min/max check skips values that cannot be parsed
- `reference_src/schema.csv:whole file (counted this run)` — type column — Type counts: percent 125, dollars 114, choice 92, date 66, year 41, text 40, boolean 30, integer 28, number 17, currency 11, decimal 2
- `tests/test_plan_date_parsing_unit.py:98-103` — test_validate_value_rejects_non_finite_numbers — Parametrized over number/currency/integer/percent only. The main money type, 'dollars', is not tested
- `src/server_services/plan_forms_service.py:43-104` — save_forms_payload / patch_forms_payload / _value — /api/plan/forms POST/PATCH strips the value, normalizes Roth values and writes it with no schema validation
- `src/data_io.py:320-329` — _n — Downstream, an unreadable value is logged and replaced with the code default (see QA-001)

**Observed behavior:** A value like 'abc' or '12k' in a dollars field passes the grid save. On any write through /api/plan/forms nothing is validated. The parser then quietly uses the hard-coded default.

**Impact:** Bad money input reaches the engine without the user knowing. The test suite's type list does not match the schema's, so the gap is invisible to the existing tests.

**Affected workflows:** Plan Data grid edits; Automation/API writes through /api/plan/forms; Imports that land in plan rows

**Root cause:** The validator's type vocabulary was never matched to the schema's type vocabulary, and the two write paths have different validation contracts.

**Options and tradeoffs:**

1. Treat 'dollars' and 'decimal' the same as 'currency' in validate_value, using money.is_strict_number
2. Make one shared row validator that both /api/config/rows and /api/plan/forms call
3. Both, plus a contract test that every type value in schema.csv is handled by validate_value

**Recommendation:** Option 3. Normalize the type aliases, send forms writes through the same validator (format/range only, per QA-002), and add a test that fails when schema.csv contains a type validate_value does not handle.

**Dependencies:** QA-002 (so that adding validation to forms does not bring the required-field blocker with it)

**Implementation considerations:** Use money.parse_strict_number as the one grammar, so the server, the parser and the client accept the same strings.

**Risk of change:** Low to medium. Existing plans with bad dollar text will start failing validation on save, so a migration report helps.

**Verification method:** Static: compare the validate_value type sets with the schema.csv type counts. Confirm with validate_value('abc', {'type':'dollars'}) == [] before the fix.

**Adversarial verification:** src/schema_registry.py:26-28 checks number format only for {'number','currency'}, and the finite-number check at 32 omits 'dollars' and 'decimal'. _numeric_value (lines 62-74) returns None for text it cannot parse, so the min/max check is skipped. I re-counted the type column of reference_src/schema.csv this run: dollars 114, decimal 2, number 17, currency 11, which matches the finding. The finding's list leaves out yes/no 3 and secret 2; this is minor. tests/test_plan_date_parsing_unit.py:98-103 parametrizes only over number, currency, integer and percent. src/server_services/plan_forms_service.py (_value, save/patch) only strips and normalizes Roth values, with no schema validation. One mitigation: the shipped frontend does not appear to call /api/plan/forms, so that half of the impact is limited to API and automation callers. The dollars gap in grid saves is real, and together with QA-001's silent default it lets bad money input through. Medium severity is appropriate.

### UX-001 — Voiding a sale linked to the transaction log says 'Use Restore to bring it back', but Restore is then refused

| Field | Value |
|---|---|
| Expert | usability_accessibility |
| Category | error-recovery |
| Severity | medium |
| Confidence | high |
| Inspection status | finding_identified |
| Verification status | confirmed |
| Linked implementation items | W2-04 |
| GitHub context | PR #418 (contextual_only) |

**Evidence**

- `frontend/js/dashboard_decomp_sales_ledger.js:255-261` — slVoid — The confirm text is only 'Remove <gain> from <year> totals?'. On success it always shows 'Sale voided. Use Restore to bring it back.', whatever kind of sale it was.
- `src/sales_service.py:215-232` — _set_voided — For a sale whose lot_key has log_sell, voiding also voids the live transaction-log sell and rebuilds that account's holdings (materialize_managed). Unvoiding then raises ValidationError 'this lot's log sale was removed with the void; record the sale again'.
- `frontend/js/dashboard_decomp_sales_ledger.js:38-42` — slLotRowHtml — After the void, the Restore menu item for a log-linked lot is disabled with the reason 'its log sale was removed with the void: record the sale again'. So the UI knows ahead of time that this void cannot be undone, but the confirm and success text do not say so.

**Observed behavior:** For sales recorded through the transaction log, Void is effectively one-way: it voids the log sell, puts the shares back in their lots, and blocks Restore. The confirm dialog does not mention this. The success message promises the user can Restore.

**Impact:** A user who voids by mistake expects a one-click undo and finds Restore disabled. They then have to re-enter the sale by hand, with the lot choice and dates, to get their realized-gain and tax-year records right again. This is the kind of 'wrong recovery promise' slip that error-prevention guidance (Nielsen heuristic 5; ISO 9241-110 error tolerance) warns against for financial records.

**Affected workflows:** Track & Reconcile > Investment Sales Ledger > Sales tab > lot actions > Void / Restore; Investment Holdings > Activity (transaction log) consistency after a void

**Root cause:** slVoid builds its confirm and success text the same way for every sale and ignores the lot_key log_sell link. The row renderer already uses that link to disable Restore.

**Options and tradeoffs:**

1. No credible alternative; this is a correctness defect.

**Recommendation:** When lot_key has log_sell, change the confirm to say this void also removes the linked Activity sale and cannot be undone with Restore (the sale must be recorded again), and drop the 'Use Restore' sentence from the success message. Move this confirm to the in-app showInAppConfirm dialog together with UX-002.

**Dependencies:** UX-002

**Implementation considerations:** The log_sell test already exists in slLotRowHtml (lines 40-41); reuse it rather than adding a second check. Keep the message text in step with the server's ValidationError wording. Do not add a frontend test that matches source string literals (test_freeze_frontend_source_grep); use the Node vm sandbox harness.

**Risk of change:** Low; this changes message text and branching only and leaves void semantics alone.

**Verification method:** In the Node vm sandbox, render a voided sale with a log_sell lot_key and with a manual lot_key, call slVoid, and check that the confirm and success texts differ. In the app, void a log-recorded sale on the demo plan and check that the message does not offer Restore.

**Adversarial verification:** I opened frontend/js/dashboard_decomp_sales_ledger.js:255-261 (slVoid). The confirm text is 'Remove <gain> from <year> totals?' and the success text is always 'Sale voided. Use Restore to bring it back.', with no lot_key check. In the same file, lines 38-42 (slLotRowHtml), the Void menu item is enabled for log_sell-linked lots, and after the void Restore is disabled with the reason 'its log sale was removed with the void: record the sale again'. In src/sales_service.py:215-232 (_set_voided), voiding a sale with a log_sell link voids the live log sell and runs materialize_managed; unvoiding raises ValidationError when the sell is no longer active. So the success text promises a Restore that the UI and the server both refuse. Mitigation: the disabled Restore item does explain why, so the user is told afterward, not left confused. That keeps severity at medium, not high. The fix fits the problem and is narrow. This is not a financial-rule finding, so no jurisdiction applies.

### UX-002 — Irreversible financial-record actions use bare native confirm() dialogs that understate the consequences, although an in-app confirm dialog exists

| Field | Value |
|---|---|
| Expert | usability_accessibility |
| Category | error-prevention |
| Severity | medium |
| Confidence | high |
| Inspection status | finding_identified |
| Verification status | confirmed |
| Linked implementation items | W2-04 |
| GitHub context | PR #418 (contextual_only) |

**Evidence**

- `frontend/js/dashboard_decomp_cash_accounts.js:59-66` — caDelete — window.confirm('Delete <account>? Its balance is removed from the plan.') The text does not say the delete is permanent or that it removes other data.
- `src/cash_accounts.py:98-113` — delete_account — A hard delete: it removes the account's holdings rows and its ytd_account_setup row, and clears every Monarch mapping that points at it. There is no soft-delete or undo path.
- `frontend/js/dashboard_decomp_local_backups.js:31-36` — localBackupStatusLine — Local backups are opt-in ('Off — backups run only when enabled here'), so there is no default safety net for a mistaken delete.
- `frontend/js/dashboard_decomp_cash_investment.js:82-100` — ciCloseYear / ciReopenYear / ciMarkRollover — Close year, Reopen year (which 'discards' frozen figures) and Mark as rollover (which changes tax treatment) all use bare global confirm().
- `frontend/js/dashboard_decomp_sales_1099b.js:176-181` — bbApply — Replacing an earlier 1099-B statement is confirmed with window.confirm, and only when window.confirm exists.
- `frontend/js/dashboard_decomp_transactions_log.js:183-185,215` — tlConfirmed / tlStart / tlCleanBank — tlConfirmed returns true (consent) when window.confirm is not a function. This guards Start the log (holdings are written by the log from then on), voiding bank opening rows, and voiding a transaction.
- `frontend/js/dashboard_decomp_row_model.js:3385-3410,4490-4498` — openStaticDialog / ctx.confirm -> showInAppConfirm — An accessible in-app confirm already exists: it traps Tab, closes on Escape, takes a safe-default initial focus, and restores focus. The Planning Workbench uses it (planning_workbench_ui.js:287), and plan-folder import uses an in-app list confirm (dashboard_plan_folder_io.js:30).

**Observed behavior:** The newest record-keeping flows (cash accounts, cash-year close, rollover marking, 1099-B replace, transaction log, sale void) ask with the browser's native OK/Cancel box. The text is short, does not say whether the action can be undone, does not list side effects, and labels the buttons OK/Cancel instead of naming the action. In two helpers, a missing confirm() counts as consent.

**Impact:** Native OK/Cancel boxes give no information scent: the user is not told what OK does, OK is the default, and habituated users click through. In this desktop app, the Delete and Void actions are permanent, or reversible only with work. The pattern also goes against the in-app dialog direction the project took (WI-018/UX-011). It cannot be styled or sized with the app's text-size control, and its focus and announcement behavior under the WebView2 shell was not established.

**Affected workflows:** Checking & Savings > Delete account; Year-End Transition > Investment cash > Close / Reopen year, Mark as rollover; Investment Sales Ledger > 1099-B apply (replace), Void sale; Investment Holdings > Activity > Start the log, bank cleanup, Void transaction

**Root cause:** The record-keeping modules were written as standalone ES modules that call the global confirm() instead of the shared ctx.confirm/showInAppConfirm, and there is no project rule requiring the shared dialog for destructive actions.

**Options and tradeoffs:**

1. Route every destructive record action through showInAppConfirm, with an action-named primary button ('Delete account', 'Close 2026'), a consequences line (permanent or undoable, and what else changes), and Cancel as the initial focus. Moderate effort, about 8 call sites.
2. Keep confirm() but rewrite each message to state permanence and side effects, and make missing-confirm mean refusal. Low effort, but it keeps the native-dialog problems.
3. Add server-side soft delete or undo for cash-account delete and an automatic pre-action snapshot, then use lighter confirmations. Higher effort; it touches the store layer.

**Recommendation:** Option 1, plus changing tlConfirmed and the window.confirm && ... guards so that no dialog means no action. Consider turning on a local backup automatically before hard deletes as a follow-up.

**Dependencies:** None

**Implementation considerations:** showInAppConfirm returns a Promise. Callers such as caDelete and ciCloseYear are already async; tlConfirmed is synchronous and needs converting. The frontend line ceiling (test_frontend_size_ratchet) means the shared dialog should be reused, not a new one written. Write tests in the Node vm sandbox, not as source-text greps.

**Risk of change:** Low to moderate: async conversion of a few handlers, and existing frontend tests that stub window.confirm will need updating.

**Verification method:** Node sandbox tests that each destructive handler calls the in-app confirm and does nothing when it is dismissed, and that a missing confirm does not proceed. Do a manual keyboard pass (Tab, Escape, initial focus on Cancel) in the desktop shell.

**Adversarial verification:** Call sites I verified: caDelete (cash_accounts.js:59-66) uses window.confirm with 'Its balance is removed from the plan.' cash_accounts.py:98-113 (delete_account) is a hard delete that removes holdings rows and the ytd_account_setup row and clears the matching Monarch mappings, with no undo in that function. ciCloseYear, ciReopenYear and ciMarkRollover (cash_investment.js:82-100) use bare confirm(). bbApply (sales_1099b.js:176-181) is guarded by window.confirm &&. tlConfirmed (transactions_log.js:183) returns true when confirm is unavailable; a comment says this is 'by design (tests, embedded views)', which explains it but is still fail-open. local_backups.js:31-36 shows backups are off by default. showInAppConfirm and openStaticDialog (row_model.js:3312/3390, ctx.confirm at 4490-4493) exist, and planning_workbench_ui.js:287 and dashboard_plan_folder_io.js:30 use them. Caveats: some of the confirm texts do state consequences (Reopen says frozen figures are 'discarded'; Rollover explains the tax effect), so 'understates' applies most strongly to caDelete, tlVoid and the 1099-B replace. I did not open any dialog CSS, so I did not verify the claimed Cancel-first focus of showInAppConfirm. The sale-void site overlaps UX-001 but the scope is broader, so this is not a duplicate.

### UX-003 — Result and error feedback for the ledger and cash panels uses freshly injected role=status paragraphs, so errors are announced politely or not at all, and the shell message slot can overwrite an unread error

| Field | Value |
|---|---|
| Expert | usability_accessibility |
| Category | accessibility |
| Severity | medium |
| Confidence | medium |
| Inspection status | finding_identified |
| Verification status | confirmed |
| Linked implementation items | W2-05 |

**Evidence**

- `frontend/js/dashboard_decomp_cash_accounts.js:18` — caHtml — Both errors and successes are rendered as a new <p role="status"> inside the panel's re-rendered innerHTML.
- `frontend/js/dashboard_decomp_sales_ledger.js:90` — slMessage render — Same pattern: error messages use role=status (polite), not alert.
- `frontend/js/dashboard_decomp_sales_1099b.js:105` — bbMessage render — Same pattern. The same is true for sales_entry.js:94, sales_queue.js:112, sales_tax.js:88, sales_wash.js:28 and transactions_log.js:26.
- `frontend/js/dashboard_decomp_cash_investment.js:63` — ciError render — The cash/year-close panel instead uses an injected role=alert for errors. That is a second convention.
- `frontend/js/dashboard_decomp_sales_ledger_ui.js:140-149` — slLiveHtml / slAnnounce — A persistent live region pair (polite and alert) exists for the ledger, but the panel messages above do not use it.
- `frontend/js/dashboard_decomp_row_model.js:195-241` — showMessage — There is one header slot. Each call replaces innerHTML and switches role and aria-live on the same element, so any later info message replaces a persistent error the user has not read or dismissed.

**Observed behavior:** There are three feedback conventions: the shell #actionMessage, panel-local role=status or role=alert paragraphs injected with the content, and the ledger's persistent sr-only regions. Panel errors are often marked polite. Because the live-region element is created in the same update as its text, many screen-reader and browser combinations do not announce it.

**Impact:** After pressing Apply, Void, Delete or Close year, a screen-reader user may hear nothing on success or failure, or hear a failure only politely. Sighted users see feedback in different places on different pages, which adds cognitive load and weakens consistency (WCAG 4.1.3 Status Messages; Nielsen consistency and visibility of system status). An error in the shell slot can disappear when an unrelated info message replaces it.

**Affected workflows:** Investment Sales Ledger (all tabs); 1099-B apply; Checking & Savings add/delete; Year-End cash close/reopen; Transaction log actions; Any flow that calls showMessage after an earlier error

**Root cause:** Each module renders its own message markup inside its innerHTML repaint, and there is no shared announce helper that writes to a region already present in the DOM.

**Options and tradeoffs:**

1. Add one shared announce(text, {error}) helper that writes to persistent polite and assertive regions in index.html (generalizing slAnnounce). Keep the visible panel text without a live role. Make showMessage keep an unread error, for example by queuing or appending, instead of replacing it.
2. Standardize only the visible markup (errors role=alert, successes role=status) and accept that injected regions announce unreliably.
3. Route all panel feedback through showMessage. This loses the message's proximity to the panel that caused it.

**Recommendation:** Option 1. It keeps the feedback visible beside the panel and makes announcements reliable and uniform.

**Dependencies:** None

**Implementation considerations:** The project has tests named inapp_modal_accessibility and reflow-and-message-row (existence only; not run). The helper must stay inside the frontend line ceiling, so replacing the per-module message markup should be roughly line-neutral.

**Risk of change:** Low to moderate; it touches many modules' message rendering, but each change is mechanical.

**Verification method:** Run NVDA or Narrator in the WebView2 desktop shell: trigger a success and a failure on 1099-B apply, sale void and cash-account delete, and confirm each is announced once, with errors as assertive. Add a Node sandbox test that an info showMessage after an error leaves the error reachable.

**Adversarial verification:** Verified: caHtml (cash_accounts.js:18), slListHtml (sales_ledger.js:89-90), bbBodyHtml (sales_1099b.js:105) and tlMsgHtml (transactions_log.js:26) render errors and successes as <p role="status"> inside repainted markup. The cash/year-close panel (cash_investment.js:63) uses role=alert instead. slLiveHtml and slAnnounce (sales_ledger_ui.js:140-144) exist, but slPost (sales_ledger.js:237-245) only sets slMessage and never calls slAnnounce; the only callers I found are summary changes and transactions_log.js:106. showMessage (row_model.js:195-241) overwrites innerHTML and role on the single #actionMessage slot every time it is called, so a later info call replaces a persistent error. The claim that freshly inserted live regions announce unreliably is a well-known assistive-technology behavior but was not tested here, so medium confidence is right. I did not open sales_entry.js, sales_queue.js, sales_tax.js or sales_wash.js, so those extra sites are unverified.

### ARC-006 — Version surfaces disagree (12 / v11 / 10.0.0) and the surface checker cannot see the stale banners

| Field | Value |
|---|---|
| Expert | architect |
| Category | configuration/versioning |
| Severity | low |
| Confidence | high |
| Inspection status | finding_identified |
| Verification status | confirmed |
| Linked implementation items | W1-05 |

**Evidence**

- `src/version.py:4-9` — VERSION / RELEASE_LABEL / CACHE_SCHEMA_VERSION — src/version.py:5 — VERSION = '12' — declared as the 'single source of truth'.
- `main.py:95-102` — _run_server banner — main.py:97 — hard-coded 'RETIREMENT PLAN SYSTEM v11  [server mode]'. src/server/__main__.py:16 hard-codes the same 'v11' banner.
- `pyproject.toml:56` — version — pyproject.toml:56 and package.json:3 both say '10.0.0'. retirement_planner.spec:2 says 'v11'.
- `tools/check_version_surfaces.py:30-37` — STALE / USER_SURFACES — tools/check_version_surfaces.py:37 — the STALE patterns cover v8-era tokens and 'Retirement System v<old>'. Nothing matches the uppercase 'RETIREMENT PLAN SYSTEM v11' or the package manifests, so the drift is not detected.
- `frontend/admin.html:3, 7` — cache-buster query — frontend/admin.html:3,7 — the asset cache-buster is the fixed string '?v=v11-pricing-symbol-tester-msg-fix-1', so it does not change when the version changes.
- `tools/bump_version.py:1-20` — module docstring — tools/bump_version.py:6-12 — the bump updates version.py, index.html and admin.html text but not pyproject.toml, package.json, the server banners or the admin cache-buster.

**Observed behavior:** Server-mode users see 'v11' while the app reports v12 elsewhere. Package metadata says 10.0.0. The admin page's cache-busting tag never changes between releases.

**Impact:** Users and support see conflicting versions. In server mode a browser may keep a cached admin.js after an upgrade. The impact is low but recurring, and the bump tool gives false confidence.

**Affected workflows:** release / version bump; server-mode startup; admin page after upgrade

**Root cause:** Strings were hard-coded outside version.py, and the checker's patterns target older formats.

**Options and tradeoffs:**

1. Derive the banners from src.version.release_label(), make the cache-buster use VERSION (or a build hash), and add pyproject/package.json to bump_version.py and the checker.
2. Drop the version from pyproject/package.json (set it to a placeholder) and fix only the banners.

**Recommendation:** Take option 1. Each change is a one-line edit.

**Dependencies:** None

**Implementation considerations:** pyproject's version may be read by packaging tools, so keep it in sync rather than deleting it.

**Risk of change:** Low.

**Verification method:** Extend check_version_surfaces with a case-insensitive 'SYSTEM v\d+' pattern and a manifest-version comparison, then run it statically.

**Adversarial verification:** src/version.py:5 is VERSION='12'. main.py:97 and src/server/__main__.py:16 hard-code 'RETIREMENT PLAN SYSTEM v11'. pyproject.toml:56 and package.json:3 say 10.0.0, and retirement_planner.spec:2 says v11. tools/check_version_surfaces.py scans only src, frontend and tools: main.py at the repo root is not scanned. Its dynamic patterns (82-107) are 'Retirement System v<old>', 'RetirementPlanSystem/<old>' and '<span><old></span>', which are case-sensitive and do not match 'RETIREMENT PLAN SYSTEM v11' in src/server/__main__.py. frontend/admin.html:3,7 uses the fixed cache-buster '?v=v11-pricing-symbol-tester-msg-fix-1'. The bump_version.py docstring lists no pyproject or package.json step. The impact is cosmetic or cache-related, so low severity is correct.

### ARC-007 — Compatibility layers kept with no exit criteria: the Results Explorer re-parses the XLSX on every index call, and parse-time shims survive the at-rest migration

| Field | Value |
|---|---|
| Expert | architect |
| Category | compatibility-shims/performance |
| Severity | low |
| Confidence | medium |
| Inspection status | finding_identified |
| Verification status | confirmed |
| Linked implementation items | W3-11 |

**Evidence**

- `src/detailed_results.py:944-996` — _merge_model_index_with_excel / workbook_detailed_index / workbook_detailed_results — src/detailed_results.py:944-968 — even when the semantic model exists, every index request reopens retirement_plan.xlsx (load_workbook at 822) to append 'Excel-only legacy pages ... until all pages have been migrated'. The result is not cached, unlike the result model (923-940). workbook_detailed_results (990-996) returns an index-shaped payload when a model exists, despite its docstring 'Return all result pages'.
- `src/detailed_results.py:852-877, 880-910` — _excel_workbook_detailed_sheet / _excel_workbook_detailed_results — src/detailed_results.py:861,897 — chart-dashboard sheets and the full mode load the entire workbook with read_only=False, the slowest openpyxl mode.
- `src/plan_data_migration.py:1-15` — module docstring — src/plan_data_migration.py:2-9 — the at-rest migration exists 'so the read paths can assume the current schema and drop the shims'. Yet src/data_io.py:628 and src/domain_models.py:193 still call migrate_sectioned_data on every parse, and data_io.py:821-829 still uses wife_/h_ internal keys.
- `src/legacy_conversion/__init__.py:1-9` — package docstring — src/legacy_conversion/__init__.py:1-2 — 'the one removable module ... WP11.6 deletes it'. It is still 2,993 lines across 17 files and still wired through src/server_services/conversion_service.py:49-50.
- `src/market_data.py:35-39` — USER_AGENT fallback — src/market_data.py:38 — a fallback USER_AGENT 'RetirementPlanSystem/8.4' for an ImportError on src.version, which cannot happen inside the package.

**Observed behavior:** Several migration-era dual paths are still in place without a recorded condition for removal. One of them adds an uncached workbook parse to every Results Explorer navigation.

**Impact:** Results Explorer navigation pays an XLSX open per index request (cost not measured in this static review). Readers of the engine must understand both the old and the current plan shapes, and about 3k lines of conversion code remain to maintain.

**Affected workflows:** Results Explorer; plan parsing; first-launch conversion of old installs

**Root cause:** Migrations were completed in stages, and the shims were never given removal triggers.

**Options and tradeoffs:**

1. Record an exit criterion for each shim (for example: semantic model covers all sheets, then delete the Excel fallback; plan_data schema stamped everywhere, then drop the parse-time migrate_sectioned_data call), and cache the Excel index keyed on the workbook mtime meanwhile.
2. Only cache the Excel index (a quick performance win) and leave the shims.
3. Leave everything as it is.

**Recommendation:** Take option 1: cache now, and add the removal criteria to the module catalog or backlog so the shims eventually go away.

**Dependencies:** None

**Implementation considerations:** Keep legacy_conversion until there is evidence that no pre-v12 installs remain. The frontend distinguishes fallback sheets via source === 'excel_parser_fallback' (frontend/js/dashboard.js:2409, frontend/js/reports_ui.js:74).

**Risk of change:** Low for caching. Medium for removing the shims.

**Verification method:** Measure Results Explorer index latency before and after caching on a real workbook. Run Golden masters to confirm that removing a parse shim changes no output.

**Adversarial verification:** src/detailed_results.py:944-968 _merge_model_index_with_excel calls _excel_workbook_detailed_index on every index request, with no cache, while _RESULT_MODEL_CACHE (923-940) caches only the model. workbook_detailed_results (990-996) returns the merged index despite its docstring 'Return all result pages'. One correction: the index path opens the workbook with read_only=True (822), openpyxl's cheaper mode. read_only=False applies only to chart-dashboard sheets (861: read_only=not chart_target) and to the full-results path (897). So the cost per navigation is real but smaller than the finding implies, and it was not measured. plan_data_migration.py:2-9 states its purpose is to let read paths drop the shims, yet data_io.py:628 and domain_models.py:193 still call migrate_sectioned_data, and data_io.py:821-829 still uses wife_/h_ keys. src/legacy_conversion has 17 files and 2,993 lines, and its docstring says WP11.6 deletes it. It is still referenced from conversion_service.py:47-50. market_data.py:35-39 has the 8.4 fallback. Low severity holds.

### DOC-005 — Agent guidance (CLAUDE.md large-file table, read guard hook, reference CLAUDE.md) gives stale sizes, a moved path and an outdated project location

| Field | Value |
|---|---|
| Expert | documentation |
| Category | developer-guidance-accuracy |
| Severity | low |
| Confidence | high |
| Inspection status | finding_identified |
| Verification status | confirmed |
| Linked implementation items | W1-08 |

**Evidence**

- `.claude/claude.md:15-30` — Reading Large Files table — 'Verified line counts' lists dashboard.js 7,287, row_model 5,188, housing_optimizer 1,984, housing_scenarios 1,397, workbook_builder 1,443, workbook_common 1,161 and module_catalog 916. It calls module_catalog 'Readable whole', and lists src/housing/screen.py (402), api.py (498) and plan_variant.py (243).
- `frontend/js/dashboard.js:1-6474` — wc -l — Measured this run: 6,474 lines. Also measured: row_model 5,974, housing_optimizer 2,832, housing_scenarios 1,466, workbook_builder 1,560, workbook_common 1,230, module_catalog 2,568, housing/api.py 704, plan_variant.py 318. src/housing/screen.py does not exist; the file is now src/housing/zip_screen/screen.py (532).
- `.claude/hooks/large_file_guard.py:11,21-27` — GUARDED — The hook repeats the same stale counts in its refusal messages, says it should be kept in sync with the table, and does not guard module_catalog.py at all.
- `documentation/reference/CLAUDE.md:42` — Project location — Gives the working copy as 'C:\RetirementPlanning\Version 12 - ChatpGPT', not the actual checkout path, and contains a typo.
- `conftest.py:1-6` — module docstring — Refers to a 'git-tracked output/retirement_plan.xlsx'. git ls-files output returns nothing.

**Observed behavior:** The guidance that sets read strategy and cost estimates for agent sessions is wrong for every listed file. It tells agents a 2,568-line file is fine to read whole, points to a moved path, and the companion hook repeats the stale counts. There are two overlapping guidance files: .claude/claude.md (80 lines) and documentation/reference/CLAUDE.md (274 lines).

**Impact:** Agents may read module_catalog.py whole, about 2.8 times the size the table states, and under-estimate session cost. That works against the project's own rule that plans must estimate usage. Stale paths waste lookups. This affects maintainers, not end users.

**Affected workflows:** AI-assisted development sessions; Implementation-plan cost estimates

**Root cause:** Line counts were hard-coded as 'verified' in two places (the table and the hook), with no refresh step as the files grew or moved.

**Options and tradeoffs:**

1. Replace the fixed counts with size bands (for example '>5k lines, grep only') and have the hook compute wc -l at call time against a threshold. Add module_catalog.py and fix the zip_screen path.
2. Keep exact counts but add a fast_gates check that fails when a listed count is more than 10% off the measured size.

**Recommendation:** Option 1. Size bands do not go stale, and a threshold-based hook covers newly grown files without edits.

**Dependencies:** None

**Implementation considerations:** Also fix the reference/CLAUDE.md location line and the conftest docstring in the same docs pass. Decide which of the two CLAUDE files is authoritative for which audience, and cross-link them.

**Risk of change:** Low; guidance and hook only.

**Verification method:** Run wc -l on each listed file and compare with the table. Attempt a whole-file Read of module_catalog.py to confirm the hook now refuses it.

**Adversarial verification:** wc -l gives dashboard.js 6474, row_model 5974, housing_optimizer 2832, housing_scenarios 1466, workbook_builder 1560, workbook_common 1230, module_catalog 2568, housing/api.py 704, plan_variant.py 318 and zip_screen/screen.py 532. src/housing/screen.py does not exist. .claude/hooks/large_file_guard.py repeats the stale counts and leaves module_catalog.py out on purpose, with a comment saying it is 'small enough to read whole'; that reasoning no longer holds at 2,568 lines. documentation/reference/CLAUDE.md line 42 gives 'Version 12 - ChatpGPT'. conftest.py lines 1-6 refer to a git-tracked output/retirement_plan.xlsx, and git ls-files returns nothing. I lowered severity to low: this is internal guidance that only affects agent context cost. dashboard.js has shrunk, so the table overstates it rather than understates it. Bounded reads still work, so nothing is functionally broken.

### DOC-007 — Living reference layer is incomplete: the index omits 11 reference/ items and FUNCTIONAL_SPEC ('behavior today') leaves out the November pages

| Field | Value |
|---|---|
| Expert | documentation |
| Category | discoverability-accuracy |
| Severity | low |
| Confidence | high |
| Inspection status | finding_identified |
| Verification status | confirmed |
| Linked implementation items | W3-09 |

**Evidence**

- `documentation/DOCUMENTATION_INDEX.md:10-31` — reference table — Does not list CAPITAL_GAINS_IN_AGI.md, FRONTEND_HOOK_REGISTRY.md, H1_BEFORE_AFTER_FIXTURES.txt, MC_PARITY_MEASUREMENT_WI009.md, MC_PARITY_MEASUREMENT_WI036.md, RENTAL_TAX_RULES.md, TRENDS_REMOTE_ACCESS_RUNBOOK.md, WI037_KERNEL_SHARING_EVALUATION.md, WP11_REACHABILITY.md, wp12_screens/ or wp5_screens/. All are present in documentation/reference/.
- `documentation/reference/FUNCTIONAL_SPEC.md:135-372` — section 4 functional areas — There is no section for the Investment Sales Ledger, 1099-B import, wash sales, Year-End Transition, Account Tax Basis or Checking & Savings. Section 4.7 is still titled 'Reports and review'. The file last changed on 2026-10-29; those pages shipped 2026-11-03 (eb269f55, c0e8875f) and later (#418).
- `documentation/reference/NAV_FEATURE_MAP.md:30-78,109-133` — Detailed table — The new pages appear only in the order list (lines 109-133), not in the detailed gating table.

**Observed behavior:** Readers who start from the index cannot find the remote-access runbook (security-relevant), the rental and capital-gains tax rule notes, or the Monte Carlo parity studies. The functional spec does not describe several shipped, tax-relevant workflows.

**Impact:** Maintainers and reviewers miss key reference material and may assume the newer tax workflows are undocumented or unspecified.

**Affected workflows:** Onboarding/maintenance; Security operations (Trends remote access); Tax workflow review

**Root cause:** Nothing ties new reference/ files to an index entry, and the functional spec is not part of the feature-merge checklist.

**Options and tradeoffs:**

1. Add the missing index rows and FUNCTIONAL_SPEC sections now, plus a test that every reference/ file appears in the index.
2. Index only the durable documents and move one-off studies (WI009/WI036 parity, WI037, WP11, screen folders) to archive/reports/.

**Recommendation:** Do both: index the durable rule and runbook documents, archive the one-off studies, and add the index-coverage test.

**Dependencies:** DOC-004

**Implementation considerations:** BACKLOG.md:26 points to an archived MC diagnostic. Keep the WI036 study reachable from it if it is archived.

**Risk of change:** Low.

**Verification method:** List documentation/reference/ and confirm each entry appears in DOCUMENTATION_INDEX.md. Check FUNCTIONAL_SPEC headings against the STEPS titles.

**Adversarial verification:** Listing documentation/reference/ confirms all 11 cited items are present, and grep of DOCUMENTATION_INDEX.md finds zero matches for each. FUNCTIONAL_SPEC.md last changed on 2026-10-29 (3a0209ba). Its headings run from 4.1 to 4.13 with '4.7 Reports and review', and there is no section for the Sales Ledger, Year-End Transition, Account Tax Basis or Checking & Savings; grep finds no mention of these apart from a 'prior year-end close' phrase in the Financial Insight section. I did not open NAV_FEATURE_MAP lines 30-78 or 109-133, or the commits eb269f55 and c0e8875f. Low severity is appropriate. It is related to DOC-004 but not a duplicate.

### FIN-002 — The OBBBA senior deduction phase-out is applied once to the couple's combined $12,000, not to each spouse's $6,000

| Field | Value |
|---|---|
| Expert | financial_planner |
| Category | financial-correctness |
| Severity | low |
| Confidence | medium |
| Inspection status | finding_identified |
| Verification status | confirmed |
| Jurisdiction | US federal (IRC 151(d)(5)(C) as added by P.L. 119-21 sec. 70103) |
| Rule year | 2025-2028 |
| Linked implementation items | W3-05 |

**Evidence**

- `src/core.py:863-882` — senior_bonus_deduction — base = 6_000 * n_over_65 and phaseout = 0.06 * (magi - threshold), then the code returns max(0, base - phaseout). The reduction comes off the combined amount once, so an MFJ couple who both qualify keeps part of the deduction up to $350k MAGI
- `src/projection_stages/roth_conversion_and_agi_tax.py:862-864` — apply_agi_and_tax — n65 counts living members aged 65 or over, and the result is added to both the standard and the itemized deduction
- `src/engine_kernels.py:2277-2287` — Roth conversion tax estimate — The same function feeds the Roth sizer's deduction estimate
- `tests/test_survivor_deduction_alive_gating_regression.py:100-102` — tests — The existing tests check only MAGI = 0 cases. Grep found no test of the phase-out range for two qualifying spouses

**Assumptions:** This reviewer reads the statute as reducing each qualifying person's $6,000 amount by 6% of MAGI above $150k (MFJ), so a couple who both qualify loses the whole deduction at $250k MAGI. The reviewer also recalls that Form 1040 Schedule 1-A computes it per person. No primary source was fetched in this run, so a CPA should confirm. Rule type: hard-coded literals (6_000, 150_000/75_000, 0.06). Authority: statute; the implementation is unverified.

**Observed behavior:** For an MFJ couple who are both 65 or over, the deduction is 12,000 - 0.06 x (MAGI - 150,000). At $250k MAGI the engine allows $6,000, while the per-person reading gives $0. The gap is largest at $250k ($6,000) and closes at $350k.

**Impact:** Federal tax is understated by up to about $1,300-$1,450 a year (at 22-24%) for 2025-2028 when the couple's MAGI is between $150k and $350k. Roth-conversion years for retirees often fall in that band, so the Roth sizer's headroom and the optimizer's scores move too. It is bounded to four years.

**Affected workflows:** Federal tax for 65+ couples; Roth conversion sizing 2025-2028; Lifetime tax

**Root cause:** The phase-out was written against the aggregate deduction instead of each qualifying person's amount.

**Options and tradeoffs:**

1. No credible alternative; this is a correctness defect.

**Recommendation:** Once a CPA confirms the per-person reading, compute the deduction as sum over qualifying people of max(0, 6,000 - 0.06 x max(0, MAGI - threshold)). Add tests at $200k, $250k and $300k MAGI with two qualifiers.

**Dependencies:** CPA confirmation of the statutory reading

**Implementation considerations:** The fix is one function, and both the AGI stage and the Roth estimate call it. A QSS year passes filing='MFJ', but QSS is not a joint return, so its threshold should arguably be $75k. Settle that in the same change.

**Risk of change:** Low code risk. Golden values move for 2025-2028 years of 65+ couples.

**Verification method:** Unit cases against a hand-filled Schedule 1-A; then run tools/regen_golden_master.py measure and check one delta by hand.

**Adversarial verification:** src/core.py:863-882 confirms base = 6000*n_over_65 and a single 6% reduction taken off the combined amount. Both apply_agi_and_tax (lines 862-864) and the Roth estimate (engine_kernels.py:2283-2284) call it. The only direct test calls in tests/ use MAGI 0.0 (test_survivor_deduction_alive_gating_regression.py:100-102, test_fill_to_bracket_deduction_headroom_regression.py:69,92), so no test covers the phase-out range. The per-person reading (each $6,000 reduced, full phase-out at $250k MFJ) matches my understanding of P.L. 119-21 sec. 70103 and IRS guidance. I did not open a primary source, so confidence stays medium. I lowered severity to low because the gap is at most about $6k of deduction (about $1.3-1.4k of tax), only in 2025-2028, and only for couples in the $150k-$350k MAGI band. The QSS-threshold note is a fair side observation.

### FIN-006 — The self-employed health insurance deduction is counted again as itemized medical and is not reduced by the ACA premium credit

| Field | Value |
|---|---|
| Expert | financial_planner |
| Category | financial-correctness |
| Severity | low |
| Confidence | high |
| Inspection status | finding_identified |
| Verification status | confirmed |
| Jurisdiction | US federal (IRC 162(l)(3), 36B; Rev. Proc. 2014-41) |
| Rule year | Current law |
| Linked implementation items | W3-04 |

**Evidence**

- `src/projection_stages/deterministic_engine.py:446-480` — _wellness_premium_for_age / _sehi_deduction_source_amount — The SEHI source is the gross bridge premium plus Part B/D/G, with no reduction for the premium credit
- `src/projection_stages/income.py:247-248, 280` — apply_income — sehi_ded = min(source, net_se), or the S-corp version, is taken above the line
- `src/projection_stages/roth_conversion_and_agi_tax.py:872-873` — apply_agi_and_tax — medical_expense_yr = wellness_premium_yr + ..., which includes the same premiums, and sehi_ded is not subtracted
- `src/projection_stages/roth_conversion_and_agi_tax.py:698-707` — apply_agi_and_tax — The bridge premium is netted by the credit for cash, but the SEHI source still uses the gross premium

**Assumptions:** The double count matters only when the household itemizes and medical costs exceed 7.5% of AGI. The credit issue matters only when earned income and a marketplace credit occur in the same year. Rule type: not modeled. Authority: statute.

**Observed behavior:** Premiums already deducted under 162(l) are counted again as 213 medical expenses, and the SEHI deduction can exceed the premium the household actually pays after the credit.

**Impact:** In the years it applies, taxable income is understated by up to the premium amount. The usual size is small to moderate, a few hundred to a few thousand dollars of tax a year.

**Affected workflows:** Self-employment years with health premiums; Itemized medical deduction; ACA bridge years with business income

**Root cause:** The SEHI and medical deductions are computed from the same premium figures without the statutory exclusion between them.

**Options and tradeoffs:**

1. No credible alternative; this is a correctness defect.

**Recommendation:** Subtract sehi_ded from the premium part of medical_expense_yr. Cap the SEHI source at premiums net of the credit, using the simplified iterative method in Rev. Proc. 2014-41. Qualified professional review not required; optional CPA confirmation of the Rev. Proc. 2014-41 method (simplified iterative vs alternative calculation).

**Dependencies:** None

**Implementation considerations:** The SEHI and credit interaction is circular. One or two fixed-point passes in the existing ACA recompute block are enough.

**Risk of change:** Low.

**Verification method:** Unit test: an itemizing self-employed household with premiums. Medical deduction should exclude the premiums already deducted as SEHI. With a credit present, SEHI should be no more than the net premium.

**Adversarial verification:** deterministic_engine.py:446-480 builds the SEHI source from gross c['bridge_premium'] plus Part B/D/G. That gross figure is not net of the PTC, while roth_conversion_and_agi_tax.py:698-707 does net the bridge premium by aca_ptc_yr for wellness_premium_yr. Lines 872-873 put wellness_premium_yr in medical_expense_yr without subtracting sehi_ded, so premiums deducted under 162(l) are counted again under 213. The double count matters only when the household itemizes and medical costs exceed 7.5% of AGI. Low severity is appropriate. Planner sign-off (2026-11-10): PC-04 upheld: professional-review statement added (CPA optional). Severity unchanged.

### FIN-007 — After the first death, the deceased spouse's unused federal estate exemption (DSUE) keeps growing with inflation, and federal estate tax omits the IRC 2058 deduction for state estate tax

| Field | Value |
|---|---|
| Expert | financial_planner |
| Category | financial-correctness |
| Severity | low |
| Confidence | medium |
| Inspection status | finding_identified |
| Verification status | confirmed |
| Jurisdiction | US federal (IRC 2010(c)(4) and 2058) |
| Rule year | Current law (P.L. 119-21 base $15M per person, indexed after 2026) |
| Linked implementation items | W4-02 |

**Evidence**

- `src/after_tax.py:746-776` — estimate_terminal_estate_tax — The combined (both-spouse) fed_exempt is indexed from plan_start to the terminal year, then federal tax = 40% of the excess
- `src/core.py:1467-1478` — indexed_federal_estate_exemption — The whole base is compounded by brk_inf
- `src/data_io.py:964` — parse defaults — A couple's default exemption is two times the per-person amount
- `reference_src/tax_update_dashboard.csv:federal_estate_exclusion row` — dashboard notes — This reference data file itself says estate-attorney review of the portability arithmetic is not documented
- `src/after_tax.py:774-783` — estimate_terminal_estate_tax — federal_taxable = max(0, row_total + biz) and federal_tax = 0.40 x (federal_taxable - fed_exempt); state_tax is computed separately and never subtracted from the federal base
- `src/engine_sections/roth_conversion.py:122-141` — _estate_tax_for_row — The optimizer's estate model has the same pattern: federal_taxable = row_total, state tax added afterwards
- `src/reporting/sheets_strategy.py:2045-2065` — Estate sheet, Federal Estate Tax section — fed_estate_tax = max(0, est2 - fed_exempt) x 0.40 with no state-tax subtraction; it also drives the 'ACTION REQUIRED' message

**Assumptions:** Portability is assumed elected (a timely Form 706 at the first death); the code assumes this without saying so. A planner or attorney should review. State estate tax is computed only for Illinois and New York (core.py:1421-1466), so the 2058 gap affects those two states. Rule type: assumed / not modeled. Authority: statute.

**Observed behavior:** The first decedent's ported amount is fixed at that death under 2010(c)(4), but the engine grows it to the second death. For a first death in 2030 and a second in 2050 at 2.5%, the ported half is about $16.6M in the law but about $27M in the engine, so the correct combined exclusion is about $43.7M ($16.6M DSUE plus $27.1M own) against about $54.2M in the engine. Separately, the federal base is never reduced by the state estate tax (IRC 2058) at any of the three sites that compute federal estate tax.

**Impact:** The DSUE indexing understates federal estate tax by up to about 40% of the excess indexing (millions of dollars), for estates between the correctly frozen and the engine's fully indexed combined exclusion at the second death (about $30M in 2026 dollars). The missing 2058 deduction overstates federal tax for Illinois and New York estates above the federal exemption by 0.40 x min(state tax, excess over the exemption), so 'about 40% of the state estate tax' is an upper bound. The two errors pull in opposite directions on the same very-large-estate population. Few households are affected.

**Affected workflows:** Estate tax and Post-Tax Inheritance for very large estates; Roth optimizer estate penalty

**Root cause:** One combined exemption is indexed uniformly, and nothing tracks the first-death date. Federal and state estate tax are computed independently at three sites, with no shared helper applying the state-tax deduction.

**Options and tradeoffs:**

1. No credible alternative; this is a correctness defect.

**Recommendation:** Index the survivor's own exclusion to the terminal year and freeze the DSUE at the first-death year's indexed amount. Apply federal tax to (gross estate - computed state estate tax) under IRC 2058. Put both rules in one shared helper used by after_tax.estimate_terminal_estate_tax, roth_conversion._estate_tax_for_row and the Estate sheet in sheets_strategy.py, so the three consumers agree. State that a timely portability election is assumed. Fix and hand-verify both errors together under the same estate-attorney gate. Qualified professional review required: estate attorney.

**Dependencies:** Estate-attorney review (same review as FIN-004)

**Implementation considerations:** The first-death year is already tracked (c['first_death_yr']). All three sites (after_tax.py:774-783, roth_conversion.py:122-141, sheets_strategy.py:2045-2065) need the same change, or the Estate sheet will disagree with the after-tax and optimizer figures, the cross-consumer drift the comment at after_tax.py:754-760 describes. This is an engine-output change, so the phase golden check and golden masters move and need hand-verification before any regeneration.

**Risk of change:** Low.

**Verification method:** Unit test with known first-death and second-death years, compared against a hand calculation. Closed-form cases for an Illinois and a New York survivor estate above the indexed exemption, one case where the 2058 deduction pulls the estate below the exemption, and a check that all three sites agree.

**Adversarial verification:** after_tax.py:751-753 and core.py:1467-1478 compound the whole combined fed_exempt from plan_start to the terminal year. data_io.py:963-964 defaults a couple to twice the per-person amount. roth_conversion.py:121 does the same in _estate_tax_for_row. tax_update_dashboard.csv row 12 says estate-attorney review of the portability arithmetic is not documented. Freezing DSUE at the first death (2010(c)(4)) is standard law, so the model over-indexes the ported half. The portability election is assumed and not disclosed. This only matters for very large estates (about $30M or more), so low severity is kept. The dollar example depends on the inflation and death-year assumptions. Planner sign-off (2026-11-10): PC-05 upheld: the missing IRC 2058 state-death-tax deduction is folded into this finding (after_tax.py:774-783, roth_conversion.py:122-141, and a third site the planner did not cite, sheets_strategy.py:2045-2065). PC-08 applied: the threshold is restated against the second-death combined exclusion. Severity stays low.

### FIN-008 — S-corp income in Illinois leaves out the 1.5% Personal Property Replacement Income Tax, and a comment wrongly says it is already counted

| Field | Value |
|---|---|
| Expert | financial_planner |
| Category | financial-correctness |
| Severity | low |
| Confidence | high |
| Inspection status | finding_identified |
| Verification status | confirmed |
| Jurisdiction | Illinois (35 ILCS 5/201(c)) |
| Rule year | Current law |
| Linked implementation items | W2-03, W3-01 |

**Evidence**

- `src/projection_stages/income.py:285-286` — apply_income (S-corp branch) — The comment says 'IL corporate surcharge on distributable income (already captured in state_tax via AGI; no separate payroll item)'
- `src/core.py:1052-1109` — state_income_tax — Individual state tax is the flat 4.95%. There is no entity-level replacement tax
- `src/reporting/sheets_strategy.py:165, 195` — S-corp comparison table and note — The only readers of scorp_state_rate (client_sections.py:1294, default 0.015). Line 165 labels it '<resident state> Corp Surcharge' for any resident state, and line 195 says it 'applies on distributable income', although the engine never deducts it

**Assumptions:** Applies to an Illinois-resident S corporation. The user could be absorbing it in business expenses (biz_exp), which the code cannot show. Rule type: not modeled. Authority: statute.

**Observed behavior:** Grep found no replacement-tax or PPRT logic in src/. The 1.5% entity-level tax is not the individual 4.95% tax, so it is not 'captured via AGI'. The S-corp sheet labels the 1.5% default as '<resident state> Corp Surcharge' for any resident state, not only Illinois.

**Impact:** Illinois tax is understated by about 1.5% of the S-corp's replacement-tax base (roughly $3k a year on $200k) in working years. Because the S corporation deducts the tax, leaving it out also slightly overstates federal taxable income and the QBI base. The misleading comment could also stop someone from fixing it.

**Affected workflows:** S-corp working years in Illinois

**Root cause:** An entity-level state tax was mistaken for individual state income tax.

**Options and tradeoffs:**

1. No credible alternative; this is a correctness defect.

**Recommendation:** Add a state entity-tax rate (Illinois 1.5% for S-corps) as a dated state reference value applied to the replacement-tax base: the S corporation's Illinois net income after Illinois addition and subtraction modifications, allocated or apportioned to Illinois, less the standard exemption (35 ILCS 5/201(c)), not federal ordinary income. Correct the comment and the sheet label. Disclose that a PTE-tax election is not modeled, or model it once the CPA confirms. Qualified professional review required: CPA, to confirm the replacement-tax base, its interaction with the Illinois PTE-tax election (35 ILCS 5/201(p), including whether it is available for 2026 and later), and entity-level federal deductibility.

**Dependencies:** CPA confirmation of the replacement-tax base and PTE interaction

**Implementation considerations:** The tax is deductible by the S-corp, so it should reduce the distribution (and QBI) the same way employer FICA already does. The engine has no Illinois modification or apportionment inputs, so the base will be an approximation of Illinois net income; state that in the help.

**Risk of change:** Low.

**Verification method:** Unit test: an Illinois S-corp's distribution falls by 1.5% of the modeled replacement-tax base (Illinois net income after modifications, less the standard exemption), and federal taxable income falls by the deducted amount.

**Adversarial verification:** income.py:285-286 has the misleading comment. core.py state_income_tax has no entity-level tax. I also found a larger problem: client_sections.py:1294 parses c['scorp_state_rate'] (state_corporate_surcharge_rate, default 0.015), and grep shows only sheets_strategy.py:165,195 reads it. That sheet tells the user the 1.5% surcharge 'applies on distributable income', but the engine never deducts it. The output asserts a tax the projection does not include. Confidence is raised to high. The dollar impact is small, so severity stays low, with the misleading disclosure as an aggravating factor. Planner sign-off (2026-11-10): PC-04 upheld: CPA review of the replacement-tax base, PTE interaction and federal deductibility added, and the base corrected from 'S-corp ordinary income'. PC-07 applied: reframed as an Illinois entity-level understatement that slightly overstates federal taxable income. Severity unchanged.

### FIN-009 — The divorce stress scenario splits assets but keeps a married-filing-jointly two-person household

| Field | Value |
|---|---|
| Expert | financial_planner |
| Category | scope-workflow-gap |
| Severity | low |
| Confidence | high |
| Inspection status | finding_identified |
| Verification status | confirmed |
| Jurisdiction | US federal filing status; Social Security divorced-spouse rules |
| Rule year | Current law |
| Linked implementation items | W2-03, W4-07 |

**Evidence**

- `src/projection_stages/appreciation_divorce_qlac.py:116-134` — apply_appreciation_divorce_qlac — The split takes divorce_split_pct of every investment account in one year. Nothing else changes
- `src/projection_stages/deaths_and_spousal_rollover.py:85-104` — apply_deaths_and_filing_status — Filing status changes only on death or QSS. Divorce never changes it
- `src/reporting/sheets_stress.py:769-773` — stress scenario table — The label says 'asset split only, does not model ongoing spousal support'. It does not mention that filing status, household spending, both spouses' benefits and Medicare stay as before

**Assumptions:** This is a stress-test scenario, not the base plan. Rule type: simplified scenario. Authority: unverified.

**Observed behavior:** After the split year, the household keeps MFJ brackets, both people's spending and healthcare, both Social Security records and spousal benefits, and the joint IRMAA tiers.

**Impact:** The scenario's net-worth and tax figures mix pessimistic spending with optimistic taxes, so it does not describe a real post-divorce household. A user could misread it as a divorce analysis.

**Affected workflows:** Stress Test: Divorce/QDRO split; Household-change scenarios

**Root cause:** It was scoped as a one-time balance-sheet event only.

**Options and tradeoffs:**

1. Option A: widen the disclosure. State that filing status, household size, benefits and spending are unchanged.
2. Option B: model a post-divorce household: Single filing from the year after the split, one member's spending and benefits, divorced-spouse Social Security eligibility (married 10+ years), and per-member account ownership.

**Recommendation:** Do Option A now. Do Option B only if divorce planning is in declared scope. No qualified professional review required for the recommended Option A (disclosure only); financial-planner wording review applies. If Option B is built, the Single filing transition and divorced-spouse Social Security eligibility would need tax and benefits professional review.

**Dependencies:** None

**Implementation considerations:** Option B touches filing state, the alive flags used for spending and healthcare, and the Social Security logic. It is a substantial change.

**Risk of change:** Option A none; Option B moderate.

**Verification method:** Option A: check the label text. Option B: scenario tests for filing status and benefits after the split year.

**Adversarial verification:** appreciation_divorce_qlac.py:116-134 only reduces investment balances in the split year. deaths_and_spousal_rollover.py:85-104 changes filing status only on death or QSS. sheets_stress.py:769-773 says 'asset split only, does not model ongoing spousal support' and does not say that filing status, household size, benefits or spending stay unchanged. This is a stress scenario, so low severity is appropriate. Planner sign-off (2026-11-10): PC-04 upheld: professional-review statement added. Severity unchanged.

### FIN-010 — The 401(k) model has one earner and one limit with no age-based catch-up rules

| Field | Value |
|---|---|
| Expert | financial_planner |
| Category | scope-workflow-gap |
| Severity | low |
| Confidence | high |
| Inspection status | finding_identified |
| Verification status | confirmed |
| Jurisdiction | US federal (IRC 402(g), 414(v) as amended by SECURE 2.0 secs. 109 and 603) |
| Rule year | 2025-2026 onward (super catch-up at ages 60-63 from 2025; Roth-only catch-up from 2026 when prior-year FICA wages from the employer sponsoring the plan exceed $145,000 as indexed, i.e. $150,000 of 2025 wages for 2026) |
| Linked implementation items | W2-03, W4-07 |
| GitHub context | PR #420 (contextual_only) |

**Evidence**

- `src/projection_stages/income.py:307-318` — apply_income — k401_limit_yr is the user's k401_lim indexed by brk_inf. The deposit goes to owner_idx=0's 401(k) only, the cap is deferral_comp, and there is no age test
- `src/parsing/client_sections.py:479-481` — parse_client — One household monthly contribution and one base-year limit (default 32500)
- `src/projection_stages/income.py:361-369` — apply_income — Every deferral is treated as pre-tax and reduces AGI. There is no Roth deferral or Roth catch-up path
- `src/projection_stages/income.py:283-288` — apply_income (S-corp branch) — deferral_comp = max(0.0, salary): on the S-corp path deferrals come out of W-2 wages, which is the only path with FICA wages

**Assumptions:** The limit is entered by the user (default 32,500 = 2026 deferral plus the age-50 catch-up). Rule type: configurable, user-provided. Authority: user-provided.

**Observed behavior:** The engine has no second earner's 401(k), no employer or profit-sharing contribution, no automatic catch-up eligibility at 50, no 60-63 super catch-up, and no Roth-catch-up requirement for high-wage S-corp owners. PR #420 itself (the deferral cap and AGI treatment) reads correctly.

**Impact:** The tax-deferral amount and timing can be off. For example, an S-corp owner whose prior-year FICA wages from the employer sponsoring the plan exceed $145,000 as indexed ($150,000 of 2025 wages for 2026) must make the roughly $8,000 catch-up as Roth, but the engine deducts it. The rule does not apply to a sole proprietor with no FICA wages, so it bites only the S-corp salary path (income.py:283-288, deferral_comp = salary). Each such case is about $2k-$3k of tax a year in working years. Users can partly work around this through the limit field.

**Affected workflows:** Working-year contributions; AGI and Roth sizing in working years

**Root cause:** The contribution model is household-level and simplified, and SECURE 2.0 catch-up rules were not added.

**Options and tradeoffs:**

1. Option A: disclose the simplifications in help text next to the limit field.
2. Option B: model per-member deferral limits from dated reference rows, with age-based catch-ups and the Roth-catch-up wage test. Leave employer contributions as a separate input.

**Recommendation:** Do Option A now and Option B when contribution planning is prioritized. Have a planner confirm whether the household's S-corp wages exceed the Roth-catch-up threshold.

**Dependencies:** Dated 402(g)/414(v) rows if Option B

**Implementation considerations:** Earned income is modeled for member 1 only, so a second earner needs income modeling first.

**Risk of change:** Option A none; Option B moderate.

**Verification method:** Option B: unit tests at ages 49, 50, 60 and 64, and above and below the wage threshold.

**Adversarial verification:** income.py:307-318 deposits to owner_idx=0's 401(k) only, with one indexed user limit, a deferral_comp cap and no age test. client_sections.py:479-481 confirms a single monthly contribution and a 32500 default limit. income.py:361-369 treats every deferral as pre-tax. Users can partly work around this through the limit field, so this is a scope simplification and low severity is right. Whether the Roth-catch-up wage test applies to this household is unknown. Planner sign-off (2026-11-10): PC-09 applied: the Roth-catch-up trigger is stated precisely. Severity unchanged.

### FIN-011 — Reference tax tables stop at 2026 while the 2027 plan year is weeks away

| Field | Value |
|---|---|
| Expert | financial_planner |
| Category | reference-data-currency |
| Severity | low |
| Confidence | low |
| Inspection status | requires_external_domain_verification |
| Verification status | partially_confirmed |
| Jurisdiction | US federal; 13 modeled states |
| Rule year | 2027 |
| Linked implementation items | W2-10 |
| GitHub context | PR #366 (contextual_only) |

**Evidence**

- `reference_src/tax_law_v10.json:values/brackets arrays` — tax_law_v10 — Ordinary brackets exist for 2025-2026 only. Standard deduction, LTCG, IRMAA, AMT, QLAC and QCD stop at 2026. NIIT rows (2024-2025) are statutory and correctly not indexed
- `reference_src/tax_update_dashboard.csv:2-14` — dashboard — An annual process exists. The state_tax row is REVIEW_REQUIRED_BY_STATE with blocking TRUE, says remaining states are unreviewed, and California brackets are 2025 carried forward
- `src/core.py:846-861` — compute_fed_tax / standard_deduction — Years after the latest row are inflated by brk_inf from the latest value year
- `reference_src/mortality_table.csv:1-2` — mortality — SSA 2023 period life table, provided by the owner (2026-10-21)

**Assumptions:** Whether the IRS (inflation-adjustment Rev. Proc.) and CMS (2027 IRMAA and premiums) have published 2027 values as of 2026-11-10 was not checked. They usually come out in October and November. Rule type: sourced and dated, with a configurable inflation fallback. Authority: authoritative where marked 'verified', otherwise 'assumption'.

**Observed behavior:** 2027 values are projected by the plan's bracket inflator, not published figures. The annual refresh process exists, but no 2027 rows have been added.

**Impact:** Small differences in 2027 brackets and IRMAA thresholds, usually tens to low hundreds of dollars. Near an IRMAA tier edge the difference can be worth thousands. The Year-End Transition (PR #366) will soon make 2027 the first plan year.

**Affected workflows:** Year-end transition to 2027; IRMAA tier-edge Roth sizing; State residency comparisons

**Root cause:** Updates are manual and annual, and their timing depends on IRS and CMS release dates.

**Options and tradeoffs:**

1. Option A: add the 2027 rows when the Rev. Proc. and the CMS fact sheet are out, following the dashboard process.
2. Option B: also have the year-end transition warn when the new first plan year has no dated rows (tax_table_currency_warnings already exists).

**Recommendation:** Do Option A as soon as the sources are published. Do Option B to tie currency to the year-end workflow. Use primary sources, and have a CPA verify state rows before relying on state-specific advice.

**Dependencies:** IRS and CMS 2027 publications (external)

**Implementation considerations:** Add dated rows and never overwrite existing ones, as the dashboard says. Then rebuild reference.db.

**Risk of change:** Low. Goldens may move for 2027 rows.

**Verification method:** Compare each new row against the primary source PDF, and record the check in tax_update_dashboard.csv.

**Adversarial verification:** I enumerated reference_src/tax_law_v10.json. AMT and IRMAA rows exist for 2025 and 2026 only, and the federal estate exclusion for 2026 only, so there are no 2027 rows. tax_update_dashboard.csv row 8 marks state_tax REVIEW_REQUIRED_BY_STATE and blocking TRUE, with California brackets carried forward from 2025. Two mitigations exist: inflation-based extrapolation after the latest row, and the tax_table_currency_warnings mechanism (data_io.py:960). Whether official 2027 figures had been published by 2026-11-10 was not checked. If they had not, the absence is expected and not a defect. This reads as a scheduled-maintenance item, not a defect; low severity and low confidence.

### FIN-012 — Simulated death ages use the male table for member 1 and the female table for member 2, regardless of who they are

| Field | Value |
|---|---|
| Expert | financial_planner |
| Category | financial-correctness |
| Severity | low |
| Confidence | high |
| Inspection status | finding_identified |
| Verification status | confirmed |
| Jurisdiction | Not jurisdictional (actuarial assumption) |
| Rule year | SSA 2023 period life table |
| Linked implementation items | W2-03, W4-03 |

**Evidence**

- `src/engine_kernels.py:791-811` — sample_death_year — The code sets sex_idx = 0 if owner_idx == 0 else 1, commented 'h=male col, w=female col by registry convention'
- `src/planning_engines.py:1971-1985` — _mc_vectorized_sample_death_ages — The vectorized Monte Carlo path takes sex_idx from the caller's positional convention
- `src/engine_kernels.py:740-747` — _mortality_qx_table — The docstring still names the Actuarial Study No. 124 anchors, but the CSV is now the SSA 2023 period table (documentation drift)

**Assumptions:** The member's configured median lifespan rescales the table, so only the shape of the curve is affected. Rule type: hard-coded positional convention. Authority: secondary (SSA table).

**Observed behavior:** A household whose member 1 is female, or a same-sex couple, gets the opposite-sex hazard curve for one member. Grep found no sex field anywhere in the engine.

**Impact:** There is a modest shift in the spread of simulated death ages, and so in survivor years and estate timing, because the median is user-calibrated. It is also an inclusivity problem, given the codebase's move to neutral member_1/member_2 labels.

**Affected workflows:** Monte Carlo survivor and longevity paths; Estate timing

**Root cause:** A legacy husband/wife positional convention survived the label migration.

**Options and tradeoffs:**

1. Option A: add a per-member sex-at-birth (actuarial) field, defaulting to the current positional choice for existing plans.
2. Option B: use a unisex blend when the field is blank, and disclose the assumption.

**Recommendation:** Option A, labeled as an actuarial assumption, with planner wording review. No qualified professional review required beyond financial-planner wording review of the actuarial-assumption label; it is an actuarial table selection, not a tax, legal or benefits rule.

**Dependencies:** None

**Implementation considerations:** Both the scalar and the vectorized samplers must read the same field.

**Risk of change:** Low. Monte Carlo distributions shift slightly for affected plans.

**Verification method:** Unit test: a plan with member 1 set to female samples from the female column; the default plans are unchanged.

**Adversarial verification:** engine_kernels.py:797 sets sex_idx = 0 if owner_idx == 0 else 1 with the 'h=male col, w=female col' comment. planning_engines.py:1971-1985 takes sex_idx from the caller. The docstring at engine_kernels.py:740-747 still cites Actuarial Study No. 124 anchors, while reference_src/mortality_table.csv row 2 says the table is the SSA 2023 period table and replaces those anchors, so the documentation drift is confirmed. The median is rescaled per member, so only the shape of the curve is affected. Low severity. Planner sign-off (2026-11-10): PC-04 upheld: professional-review statement added. Severity unchanged.

### QA-004 — API error objects from RetirementApiClient carry no HTTP status, so the build 404 fallback can never run

| Field | Value |
|---|---|
| Expert | quality |
| Category | error-handling |
| Severity | low |
| Confidence | high |
| Inspection status | finding_identified |
| Verification status | confirmed |
| Linked implementation items | W1-06 |

**Evidence**

- `frontend/js/api_client.js:22-56` — RetirementApiClient.request / text — On !res.ok it throws Error(data.error||text) with err.errors and err.fieldErrors but no err.status. text() throws the raw response body
- `frontend/js/dashboard_decomp_row_model.js:4949-4993` — api() — Sends every call through RetirementApiClient when it exists (index.html:98 loads it first). Only the unused inline fallback sets err.status, and that fallback does not set fieldErrors
- `frontend/js/dashboard_decomp_build_lifecycle.js:247-270` — buildWithProgress — The ARC-004 fallback depends on e.status === 404, which is never set, so it never fires
- `tests/e2e/build-failure.spec.js:75-138` — ARC-004 test — Covers only the negative case (no fallback after a job id). Nothing tests that a 404 triggers the fallback

**Observed behavior:** The two request paths throw errors of different shapes (status vs fieldErrors), and the main path never includes the HTTP status. /api/build/start is always registered (workbook_routes.py:196), so there is no user-visible failure today, but the documented fallback does not work.

**Impact:** Little effect today. Any future code that branches on HTTP status will fail silently, and the ARC-004 fix looks done but is untested and does not work.

**Affected workflows:** Build start; Any status-dependent client error handling

**Root cause:** The API client extraction (api_client.js) dropped err.status, and the remaining test checks only the behaviour that never needs it.

**Options and tradeoffs:**

1. Set err.status = res.status in RetirementApiClient.request and delete the inline fallback in api()
2. Delete the 404 fallback branch as dead code

**Recommendation:** Option 1, plus a frontend vm-sandbox or e2e test that returns 404 from /api/build/start and asserts POST /api/build is called.

**Dependencies:** None

**Implementation considerations:** Keep one error shape {message, status, errors, fieldErrors} and record it in API_CONTRACTS.md.

**Risk of change:** Low.

**Verification method:** Static read of api_client.js:38-42 against build_lifecycle.js:258. A sandbox test with a mocked fetch returning 404.

**Adversarial verification:** In frontend/js/api_client.js:38-42, request() builds the Error with errors and fieldErrors but never sets err.status. text() throws the raw body. In frontend/js/dashboard_decomp_row_model.js the api() function (around 4958-4960) sends every call through window.RetirementApiClient when it exists. frontend/index.html:98 loads api_client.js before row_model at line 108. Only the inline fallback, at about line 4988, sets err.status. frontend/js/dashboard_decomp_build_lifecycle.js:258 depends on e.status === 404, which the main path never sets, so the fallback is dead code. Severity stays low, since /api/build/start is registered and nothing breaks for users today. I did not open the e2e spec, but this does not change the verdict.

### QA-005 — User-facing error messages tell users to edit reference_data/state_tax.csv, a path that does not exist

| Field | Value |
|---|---|
| Expert | quality |
| Category | data-integrity |
| Severity | low |
| Confidence | high |
| Inspection status | finding_identified |
| Verification status | confirmed |
| Linked implementation items | W2-03 |

**Evidence**

- `src/core.py:979-1012` — require_residence_state_for_build / _require_supported_state — The ValueError text says 'add a row to reference_data/state_tax.csv'
- `src/reporting/sheets_strategy.py:1709, 1803` — estate / cost-of-living notes — Workbook text points to reference_data/state_tax.csv
- `src/stores/ref_access.py:15` — module docstring — Says the old reference_data/ files were replaced by reference.db, with no coexistence
- `reference_src/state_tax.csv:n/a (git ls-files)` — tracked source — The actual source is reference_src/state_tax.csv, which is built into src/reference/reference.db. git ls-files shows 0 files under reference_data/

**Observed behavior:** When the state is blank or unsupported, the build error and workbook notes send the user to a file that does not exist. Adding a state really means editing reference_src and rebuilding reference.db.

**Impact:** A user who hits a blocking error is sent down a dead end. Low severity because the error still stops the build correctly.

**Affected workflows:** State residency setup; Unsupported-state build failure; Estate/cost-of-living notes in workbook

**Root cause:** The text was not updated when the reference data moved into reference.db.

**Options and tradeoffs:**

1. Change the text to describe the supported action (pick a supported state; ask for a rule to be added) with no file paths
2. Point to reference_src/state_tax.csv plus tools/build_reference_db.py (only suitable for developers)

**Recommendation:** Option 1 for user-facing strings. Add a test that no user-facing string names an untracked directory.

**Dependencies:** None

**Implementation considerations:** Some tests may assert on this message text, so grep tests before changing it.

**Risk of change:** Low.

**Verification method:** git ls-files reference_data/ returns nothing, while git grep finds the path in src/core.py and sheets_strategy.py.

**Adversarial verification:** git ls-files reference_data returns 0 files and the directory does not exist. src/core.py:985 and 1011 tell the user to add a row to reference_data/state_tax.csv. src/stores/ref_access.py:15 says there is no fallback to the old reference_data/ files, and reference_src/state_tax.csv is the tracked source. The impact is wider than reported: the stale path also appears in src/reporting/sheets_strategy.py:1709 and 1803, src/server_services/strategy_asset_service.py:1131 (a user-visible row description), src/tax_assumptions.py:73 (an assumption-source label that shows up in output), and src/taxes.py:286 (a comment). That string is pinned in the golden fixtures (tests/fixtures/golden_phase_baseline/demo.json:15766, sample_frozen.json:14171). Fixing it will therefore move golden masters and needs the measure-first process; the finding understates this implementation consideration. Low severity is still right.

### UX-004 — The headline Build Impact cards put their definitions (5th percentile, LCV, EFTR) only in a native hover tooltip; the 'i' button does nothing when clicked or tapped

| Field | Value |
|---|---|
| Expert | usability_accessibility |
| Category | risk-communication |
| Severity | low |
| Confidence | high |
| Inspection status | finding_identified |
| Verification status | partially_confirmed |
| Linked implementation items | W3-06 |
| GitHub context | PR #259 (contextual_only); PR #267 (contextual_only) |

**Evidence**

- `frontend/js/dashboard_decomp_build_history.js:399-435` — impactCardHtml — The help text goes only into title= and aria-label on a <button class="field-info-i">. The button has no onclick and no aria-controls="helpPanel".
- `frontend/js/help_registry.js:1096-1101` — onHelpClick — The help panel opens only for elements with aria-controls="helpPanel", so these card buttons never open it.
- `frontend/js/dashboard.js:1612-1617` — field info badge — Field-level 'i' badges include aria-controls="helpPanel" and so open the help panel. The result cards do not, which makes the two kinds of 'i' badge behave differently.
- `frontend/js/dashboard_decomp_build_history.js:436-470,596` — buildImpactCardsHtml / Latest Build Impact — The headline cards are 'Expected After-Tax LCV', 'Worst-Case Ending Wealth' and 'Effective Future Tax Rate (EFTR)'. The visible title deliberately drops '(5th %ile)', so the only statement that 'worst case' means the 5th percentile and not the true worst case is inside the tooltip.
- `frontend/css/dashboard.css:3 (minified)` — .impact-headline-label — The 'Change / Current build' label under each headline is 9px uppercase muted text.

**Observed behavior:** The primary result summary uses acronyms and statistical shorthand. The definitions are visible only when a mouse hovers over a tiny 'i'. Keyboard focus does not show a native title tooltip in Chromium or WebView2, and touch cannot hover. Activating the button does nothing.

**Impact:** Users are likely to misread the headline figures. Without the definition, 'Worst-Case Ending Wealth' reads as a floor, when 5% of simulated paths end lower. 'LCV' and 'EFTR' are unexplained jargon. Risk-communication research favors explicit, visible framing for probabilistic outcomes, not hidden glosses. Screen-reader users get the whole definition read as the button's name on every pass, which is verbose.

**Affected workflows:** Analyze > Build & Results > Latest Build Impact; Comparing before and after builds

**Root cause:** The card renderer predates the help-panel convention (aria-controls="helpPanel" with data-help keys), and the title was shortened for layout (#309) without moving the qualifier into visible text.

**Options and tradeoffs:**

1. Wire the card 'i' into the help panel the same way field badges are (aria-controls, a help key in help_registry), and add a short visible qualifier such as '5% of paths end lower' under the Worst-Case value.
2. Show a one-line plain-language definition under each card title at all times, which costs vertical space.
3. Keep the tooltip but switch to the existing data-tip or focusable tooltip pattern that also shows on focus and tap.

**Recommendation:** Option 1. It reuses the existing help system and puts the one qualifier that matters for risk (the percentile) in view.

**Dependencies:** None

**Implementation considerations:** help_registry entries must use glossary terms (the prose guard test, PR #267). The impact-card layout was tuned so titles do not wrap (#309 comment), so put the qualifier under the value, not in the title.

**Risk of change:** Low.

**Verification method:** Keyboard-only: Tab to each card 'i', press Enter, and the help panel shows the definition. Visually: the Worst-Case card shows its percentile qualifier without hover. Add a Node sandbox test that impactCardHtml output carries aria-controls="helpPanel".

**Adversarial verification:** Confirmed: impactCardHtml (build_history.js:431-433) renders a field-info-i button with only title and aria-label, with no aria-controls and no onclick. onHelpClick (help_registry.js:1097-1103) acts only on [aria-controls="helpPanel"], so the button does nothing when activated, while the field badges in dashboard.js:1617 do carry aria-controls. .impact-headline-label is 9px. Refuted in part: 'the only statement that worst case means the 5th percentile is inside the tooltip' is false whenever a before/after delta exists. buildImpactNarrativeHtml (build_history.js:565-568), rendered above the cards at line 596, visibly says 'Worst-case (5th percentile) ending wealth ...'. The qualifier is hidden only on a first build or when one side is missing. 'EFTR is unexplained jargon' is also false: the visible card title is 'Effective Future Tax Rate (EFTR)' (build_history.js:499). LCV is the only unexpanded acronym. The inert button is a real accessibility defect, but the risk-misreading impact is overstated, so I lowered severity to low.

### UX-005 — Secondary tab strips use role=tab without the matching tab-panel semantics, roving focus or arrow keys; only the Sales Ledger implements the pattern

| Field | Value |
|---|---|
| Expert | usability_accessibility |
| Category | accessibility |
| Severity | low |
| Confidence | high |
| Inspection status | finding_identified |
| Verification status | partially_confirmed |
| Linked implementation items | W3-07 |

**Evidence**

- `frontend/js/dashboard.js:2876-2878` — renderStrategyTabs — role=tablist with no accessible name, and role=tab buttons with onclick only: no aria-controls, no tabpanel, no roving tabindex, no arrow-key handler.
- `frontend/js/dashboard_decomp_holdings_tabs.js:29-31,42` — hsTabBarHtml — The tablist is named, but the panels below have no role=tabpanel or aria-controls link, and there is no key handling.
- `frontend/js/dashboard_decomp_monarch_reconciliation.js:243,248` — tabBtn — An unnamed tablist. The selected tab is shown with the generic 'btn good' class, so it looks different from the workspace-tab style used elsewhere.
- `frontend/js/dashboard_decomp_rental_properties.js:383,391` — RP tabs — An unnamed tablist with role=tab buttons, onclick only.
- `frontend/js/dashboard_decomp_sales_ledger_ui.js:51-56,100-109` — slTabBarHtml / slTabKeydown — The reference implementation: aria-controls, role=tabpanel with aria-labelledby, roving tabindex, and ArrowLeft/ArrowRight/Home/End.

**Observed behavior:** Five tab widgets follow three different interaction models. Four of them announce as ARIA tabs ('tab 1 of 3') but do not respond to the arrow keys that role implies, and they do not tie the tab to its content.

**Impact:** Screen-reader and keyboard users get a broken affordance on Strategy workspaces, Holdings, Reconciliation and Rental Properties, which are high-traffic pages. The visual style of the tabs also varies. This is a consistency and learnability cost (WCAG 4.1.2 Name, Role, Value; ARIA APG tabs pattern).

**Affected workflows:** Optimize / Stress Test / Scenarios workspaces; Investment Holdings Positions | Activity | Import; Account Reconciliation; Rental Properties

**Root cause:** Each module renders its own tab bar, and there is no shared tab component.

**Options and tradeoffs:**

1. Extract the Sales Ledger tab bar and keydown into a shared helper and use it in the other four.
2. Drop role=tab and role=tablist from the four and present them as a toggle-button group (aria-pressed). This is simpler and honest about what the widget does.
3. Leave as is.

**Recommendation:** Option 1. It is roughly line-neutral, because four bespoke tab bars collapse into one helper, which also helps the frontend line ceiling.

**Dependencies:** None

**Implementation considerations:** renderMain re-renders the page on each tab click, so the shared helper must restore focus to the newly selected tab (the Sales Ledger version passes {focus:true}). The focus-restore module already exists.

**Risk of change:** Low; existing selected_state_aria tests may need their expectations updated.

**Verification method:** Keyboard pass on each page (Tab reaches the strip, arrows move between tabs, focus stays on the tab after re-render). Add a Node sandbox test that each tab bar's output includes aria-controls and that the panel has role=tabpanel.

**Adversarial verification:** Confirmed: renderStrategyTabs (dashboard.js:2876-2878) has an unnamed tablist with role=tab and onclick only. tabBtn in the reconciliation module (monarch_reconciliation.js:243,248) uses an unnamed tablist with 'btn good' styling. The Rental Properties tabs (rental_properties.js:383,391) have an unnamed tablist, onclick only. The Sales Ledger (sales_ledger_ui.js:51-56,100-109) has aria-controls, a tabpanel with aria-labelledby, roving tabindex and arrow/Home/End keys. A grep for ArrowRight finds key handling only in sales_ledger_ui.js and source_truth_banners.js. Factual error: the Holdings content does have role=tabpanel (holdings_tabs.js:42, <div role="tabpanel" id="hs-p-...">). What it lacks is the aria-controls and aria-labelledby link, roving tabindex and key handling. The core inconsistency still holds, so the finding is partially confirmed at low severity.

### UX-006 — Primary results tables and status labels use 9–10px type, and the in-app text-size control tops out at 130%

| Field | Value |
|---|---|
| Expert | usability_accessibility |
| Category | readability |
| Severity | low |
| Confidence | medium |
| Inspection status | finding_identified |
| Verification status | confirmed |
| Linked implementation items | W2-11 |

**Evidence**

- `frontend/css/dashboard.css:3 (minified)` — .detail-result-table thead th / .detail-result-table td — The Results table header cells are 10px uppercase with letter-spacing in --muted. Body cells are 12px.
- `frontend/css/dashboard.css:3 (minified)` — .impact-headline-label, .spend-level-pill, .badge, .nav-badge, .closeout-status, .check-status, .rp-card dt — Status and KPI labels at 9–10px. The impact-card title span is 10.5px.
- `frontend/js/text_size.js:5-17` — TEXT_SIZE_OPTIONS / applyTextSize — The options are 100/115/130%, applied as CSS zoom, so a 10px header is at most 13px through the in-app control.
- `src/desktop_app.py:37-51` — create_window — zoomable=True, so WebView zoom is also available as a separate route to larger text.

**Observed behavior:** At the default size, column headers of the main results table and several status chips render at 9–10px. The token contrast is adequate: --muted #68645b on #fbfaf7 computes to 5.65:1, and on #fff to 5.89:1. The in-app enlargement cap leaves those headers small.

**Impact:** Smaller labels are harder to read, especially in dense numeric tables where the column header carries the meaning. The 130% cap is below the 200% WCAG 1.4.4 target unless the user finds the WebView zoom, which is not advertised. This is a readability and legibility issue, separate from contrast, which passes.

**Affected workflows:** Build & Results > Detailed results tables; Latest Build Impact cards; Plan Status checklist chips; Spending dashboard pills

**Root cause:** Compactness tuning (for example #309's 'general font/padding shrink') was applied with fixed px sizes, without a minimum-size token.

**Options and tradeoffs:**

1. Introduce a minimum label size token (11–12px) for table headers and status chips, and add a 150% and 200% step to the text-size control.
2. Only add larger text-size steps and document Ctrl+plus WebView zoom in help.
3. Leave as is and rely on WebView zoom.

**Recommendation:** Option 1 for the results table headers and KPI labels at minimum. Check the wrap regressions #309 was avoiding.

**Dependencies:** None

**Implementation considerations:** dashboard.css is minified on long lines, so edit it with care for line endings (repo hygiene hook). The reflow e2e specs (existence only) are the right check after the change.

**Risk of change:** Low to moderate; there is a layout wrap risk on the impact cards and wide tables.

**Verification method:** Visual check at 100%, 130% and a new 200% step on Build & Results at 1280px and 900px widths. Run the existing reflow e2e spec.

**Adversarial verification:** I checked dashboard.css. .detail-result-table thead th is font-size:10px, uppercase, color var(--muted); body cells are 12px. .spend-level-pill is 9px; .badge, .nav-badge, .closeout-status, .check-status and .rp-card dt are 10px; .impact-headline-label is 9px; .impact-card span is 10.5px. --muted is #68645b. text_size.js:5-17 sets TEXT_SIZE_OPTIONS = [100,115,130] and applies them as CSS zoom. desktop_app.py:37-51 sets zoomable=True. I did not recompute the contrast ratio. Calibration: because WebView zoom is enabled, WCAG 1.4.4 is very likely met through user-agent zoom, so this is a legibility issue, not a conformance failure. The finding already concedes this, and low severity is appropriate. The legibility impact is inferred and was not observed, so confidence stays medium.


## 6. Options and tradeoffs

Each finding in Section 5 lists its own options. Where a finding is an objective correctness defect, it says so and gives no alternatives. The cross-cutting choices that shape the plan are:

| Decision | Options considered | Tradeoff | Chosen |
|---|---|---|---|
| How to treat blank plan values | (a) keep code defaults; (b) blank means schema default or zero, with required blanks blocking builds; (c) write neutral values into new plans | (a) produces plausible but wrong output; (c) hides blanks from preflight | (b), per QA-001 and conflict C-03 |
| Where 'required' is enforced | (a) on every save; (b) at build start only; (c) warnings only | (a) blocks step-by-step entry; (c) lets incomplete plans build | (b), after builds are gated (C-02) |
| Engine tax corrections | (a) one combined change; (b) a strict sequence, each with a measured, hand-verified golden re-pin; (c) disclose only | (a) makes deltas unverifiable; (c) leaves understated tax | (b) for the numeric fixes, with interim disclosures first (C-05) |
| Destructive-action confirmation | (a) in-app confirm through the shared dialog; (b) better native confirm text; (c) server-side soft delete | (b) keeps the native-dialog problems; (c) touches the store layer | (a), with (c) as a later follow-up |
| Frontend size governance | (a) per-file caps plus a reason line; (b) a one-off extraction; (c) rename the guard a budget | (c) abandons the control | (a) now, (b) in Wave 4 (C-04) |
| Concepts Guide | (a) refresh the .docx with a currency check; (b) generate in-app HTML from the help registry; (c) add a date note | (a) keeps two sources; (c) does not fix discoverability | (b) if the registry is to stay the one source, otherwise (a). Owner decision in W3-10 |
| Life insurance in projections | (a) integrate, with ownership-based (IRC 2042) estate inclusion and no double count of a first-death payout; (b) disclose; (c) disclose now, integrate later | (a) moves outputs; (b) leaves estate tax understated for decedent-owned policies | (c) |
| Illinois estate tax while the method is unverified | (a) wait for W4-01; (b) interim disclosure in W2-03 plus a Wave 1 start of the attorney review; (c) raise W4-01 to P1 now | (a) leaves a possibly overstated figure steering Roth selection; (c) rests on an unverified legal reading | (b), with conditional escalation of W4-01 (PC-02) |

### 6.1 Cross-expert conflict records

**C-01**

- *Conflict:* QA-006 (quality, low) and ARC-005 (architect, medium) describe the same defect: the frontend line ceiling in tests/test_frontend_size_ratchet.py is raised in feature commits, so it does not constrain growth. The experts rated it differently and recommended different guard shapes (per-file budgets vs a required reason line).
- *Alternatives:* Keep both as separate findings; keep QA-006 as primary at low; keep ARC-005 as primary at medium and fold QA-006's tally into it.
- *Decision criterion:* Priority hierarchy: maintainability outranks documentation and cosmetic concerns; the stronger finding is the one with wider evidence and impact (decomp files becoming monoliths, stale size guidance).
- *Decision:* ARC-005 is kept at medium. QA-006 is marked duplicate (duplicate_of ARC-005). QA-006's re-tally (about 105 value changes, 100 raises, the one large cut from blank-line removal in 2c293e62) is treated as corroborating evidence for ARC-005.
- *Rationale:* ARC-005 covers the same governance gap plus the structural consequence (5,974-line row_model, 2,832-line housing optimizer, bare-global coupling). Its recommendation (per-file caps plus a recorded reason, then one extraction) contains both of QA-006's options.
- *Consequence:* One work item (W1-01) addresses both. The severity of the combined issue is medium.

**C-02**

- *Conflict:* QA-002 recommends removing the 'required value' check from grid saves so a new plan can be saved step by step (usability, functional correctness). QA-001 shows that builds can start without any preflight check (src/server/workbook_routes.py:196-240) and that blank values silently become household-specific defaults (data integrity).
- *Alternatives:* Relax save-time validation immediately; keep whole-plan required validation on save; relax save-time validation only after the build start path enforces preflight blockers.
- *Decision criterion:* Priority hierarchy: data integrity outranks usability. The integrity goal is that no projection runs on missing required facts; it does not require blocking partial saves.
- *Decision:* Relax save-time 'required' validation (W2-01) only after W1-04 makes /api/build/start refuse to run while preflight blockers exist and makes blank mean zero or the schema default.
- *Rationale:* If saves were relaxed first, a partly entered plan could be built with phantom defaults and no warning, which is worse than today's blocked save.
- *Consequence:* W2-01 depends on W1-04. The Start New Plan flow stays degraded until both land; that is accepted.

**C-03**

- *Conflict:* QA-002 option 3 (have Start New Plan write neutral values such as 0 into required dollar fields) conflicts with QA-001's goal that a blank stays an explicit, detectable blank.
- *Alternatives:* Write neutral values into the blank plan; keep blanks and treat blank as zero/schema default only at parse time while preflight still reports required blanks.
- *Decision criterion:* Priority hierarchy: financial safety and data integrity outrank convenience. A stored 0 is indistinguishable from a user who entered 0.
- *Decision:* Reject QA-002 option 3. Keep blanks in the stored plan; parse blank as zero or the schema default; keep required blanks visible as build blockers.
- *Rationale:* Preflight can only warn about values it can see are missing.
- *Consequence:* QA-002 is implemented with its option 1 only.

**C-04**

- *Conflict:* Usability and documentation fixes (UX-002, UX-003, UX-004, UX-005, DOC-001, DOC-002) change frontend/js, which is governed by a total line ceiling that ARC-005 wants enforced strictly and extended with per-file caps.
- *Alternatives:* Raise the ceiling for each usability fix; defer usability fixes until the row_model extraction; implement usability fixes through existing shared code so they are line-neutral or negative.
- *Decision criterion:* Priority hierarchy: maintainability outranks usability, but usability fixes for irreversible financial-record actions also protect data integrity, which outranks maintainability.
- *Decision:* No ceiling is raised for these fixes. They reuse showInAppConfirm, a generalized slAnnounce, and the Sales Ledger tab helper, which collapses four bespoke implementations. Any fix that still needs net lines takes them from a recorded extraction, with the reason line W1-01 introduces. UX-001/UX-002 are not deferred.
- *Rationale:* Reuse removes duplicated code, so the fixes should shrink the total; deferring the confirm fixes would leave a data-integrity risk open for the sake of a size metric.
- *Consequence:* All frontend items depend on W1-01. Items in different frontend lanes must each be line-neutral or negative, otherwise they are serialized.

**C-05**

- *Conflict:* Text corrections that users need (QA-005 stale reference_data/ path; FIN-001, FIN-004, FIN-005, FIN-008, FIN-009, FIN-010 disclosures) are pinned in golden fixtures (for example tests/fixtures/golden_phase_baseline/demo.json:15766), so each fix moves golden masters, while the project's golden discipline forbids repeated regeneration.
- *Alternatives:* Fix each string separately with its own re-pin; postpone text fixes until the engine corrections; bundle all text and disclosure changes into one measured re-pin.
- *Decision criterion:* Priority hierarchy: functional correctness (truthful disclosures) outranks documentation; golden stability serves functional correctness, so the number of re-pins should be minimized, not the fixes postponed.
- *Decision:* Bundle the text and disclosure changes into W2-03 with one measure, one hand check of each changed string, and one regeneration with a recorded reason, before the numeric engine corrections in Wave 3.
- *Rationale:* Text-only deltas are easy to verify by hand when they are not mixed with numeric deltas.
- *Consequence:* W3 engine items depend on W2-03; each Wave 3 item then has only numeric deltas to hand-verify.


## 7. Recommendation

Fix in this order:

1. **Data integrity and validation** (QA-001, then QA-002, then QA-003). These protect every downstream number and unblock Start New Plan.
2. **Cheap foundations** (ARC-003 logging, ARC-001 explicit imports, ARC-005 size guard, DOC-006 backlog intake). These make the later work observable, safe to refactor and tracked.
3. **Truthful disclosures, bundled into one measured re-pin** (W2-03), including the interim notice that the Illinois estate figure is an unverified approximation (FIN-004). Start the batched CPA engagement and the estate-attorney review in Wave 1 (W1-07), so their elapsed time runs alongside Waves 2-3.
4. **Numeric federal-deduction and Illinois replacement-tax corrections in strict sequence** (FIN-008, FIN-001, FIN-003, FIN-006, FIN-002). FIN-008, FIN-001, FIN-003 and FIN-002 are gated on CPA confirmation; FIN-006 has an optional CPA check. Each gets a hand-verified golden delta. The FIN-003 fix is time-sensitive, because its main window, the 2025-2029 enhanced SALT cap, closes after 2029.
5. **Recoverability and accessible feedback** (UX-001, UX-002, UX-003, ARC-004), in parallel with step 4.
6. **Documentation currency** (DOC-001, DOC-002, DOC-004, DOC-003, DOC-007).
7. **Professional-review-gated estate items and structural refactors last** (FIN-004; FIN-007 together with the IRC 2058 deduction; FIN-005 integration with ownership-based estate inclusion; ARC-001 helper lifting; ARC-005 extraction). W4-01 (FIN-004) escalates to P1 if the attorney review confirms the federal-tax limit and the household's blended estate exposure lies within about $4M-$5M.

The target design (Section 8), the waves (Section 9) and the validation plan (Section 10) follow this order.

## 8. Target design

**Boundaries and responsibilities.**
- Domain and engine modules (`src/core.py`, `src/engine_kernels.py`, `src/projection_stages/*`, `src/housing/*`) never import `src/server_services` or `src/server`. A rule in the architecture-diagram generator, or the local fast-gates script, enforces this.
- Housing pricing lives in `src/housing/pricing.py`.
- Asset-class classification lives in `src/portfolio_analytics.py`. The Trends reporter depends on `src`, never the reverse.
- `src/core.py` declares `__all__`. Facades import explicit names.

**Shared code.**
- One plan-default source: the schema default column, with the parser and the JSON/wizard loader both reading it.
- One number grammar: `money.parse_strict_number`, used by the server validator, the parser and the client.
- One confirmation dialog: `showInAppConfirm`, with action-named buttons, a consequence line, Cancel as initial focus, and fail-closed when no dialog is available.
- One announce helper writing to persistent live regions.
- One tab helper (the Sales Ledger pattern).
- One API error shape: `{message, status, errors, fieldErrors}`.

**Data and calculation flows.**
- Federal deductions are assembled in one place in `apply_agi_and_tax`. QBI is capped against taxable income before QBI minus net capital gain (including qualified dividends), with the 2026+ minimum deduction and thresholds from dated rows. SALT uses the state tax the engine actually computes, in every year. Premiums deducted as SEHI are excluded from medical expense. The senior deduction is computed per qualifying person.
- Entity-level state taxes come from dated state reference rows, applied to the state's own base (for Illinois, net income after Illinois modifications and apportionment, less the standard exemption), and reduce the S-corp distribution and QBI base.
- Estate tax uses the Illinois method with a federal-tax limit, once an attorney confirms it, a DSUE frozen at the first death, and a federal base reduced by the state estate tax (IRC 2058). One helper is shared by the after-tax model, the Roth optimizer and the Estate sheet. Until the Illinois method is confirmed, the figure is labelled as an unverified approximation wherever it is shown or feeds the Roth strategy.
- Life policies flow into survivor and estate results when their module switch is on. Estate inclusion follows ownership (IRC 2042): a policy on the last decedent's life that the decedent owned, or that is payable to the estate, enters at face; third-party-owned and ILIT-owned policies do not; a first-death payout already in the survivor's accounts is not counted again.

**Validation and errors.**
- Saves check format and range of changed rows.
- Builds refuse to start while preflight blockers exist.
- An unreadable money value is an error, never a silent fallback.
- User-facing messages never cite untracked repository paths.

**Logging.** All application loggers sit under `retirement_system.*`, so every warning reaches the rotating, redacting, account-masking `app.log`. Startup migration results are logged on every launch path.

**Persistence.**
- Backups use the SQLite backup API and check the checkpoint result.
- Every in-place schema upgrade of a real file first writes a pre-upgrade copy under `plan_paths(...).backups_dir`, with a retention cap.

**UI.**
- Minimum label size token (11-12px).
- Text-size steps up to 200%.
- Result-card help opens the help panel.
- The percentile qualifier is visible on the Worst-Case card.

**Tests.**
- Contract tests for parser-versus-schema defaults and for schema type coverage.
- A blank-plan save, then a build refused while incomplete.
- Closed-form tax cases for each corrected rule.
- Vm-sandbox tests for confirm and announce behaviour (never source-text greps).
- Golden masters changed only through measure, a hand-verified delta, and one regeneration with a reason.

**Documentation.**
- The help registry is the source of plain-English definitions, including terminal net worth, probability of success and LCV.
- README and Plan Status directions match the nav.
- Every `future/` document's Status line carries a merge reference when it says implemented.
- BACKLOG.md receives every deferred or approval-gated item.
- The agent large-file guidance uses size bands.

**Assumptions and migrations.**
- Interim disclosures state each unmodelled rule.
- Plans that silently relied on the old defaults will change when W1-04 lands, so it needs a release note.
- The phase-golden baselines move only in W2-03 and in the Wave 3 and 4 engine items.

## 9. Implementation waves

The waves are ordered by dependency. Work in different lanes ("parallel groups") can run at the same time only where no component is shared.

These components are shared across lanes:
- **Golden fixtures.** Every G-ENG item is serialized.
- **The total frontend line ceiling.** Items in G-FE, G-DOC-HELP, G-DOC-NAV and G-CSS must each be line-neutral or negative, otherwise they run one after another.
- **`SYSTEM_ARCHITECTURE_DIAGRAM.md`.** Structural items regenerate it one at a time: W2-07, then W3-10 if it adds a route, then W4-05 and W4-06.
- **`src/data_io.py`.** W1-03 comes before W1-04.
- **`strategy_asset_service.py`.** W2-03 comes before W2-07.

**Effort and usage estimates.** Estimates are relative: S, M or L for effort, and light, moderate or heavy for the Claude Code usage a step is likely to need against a 5-hour Pro session. They are not token counts. Steps marked FLAG are likely to be disproportionately expensive, and the drivers column says how to scope them down. Check `/usage` against these estimates as the plan executes, and re-plan if a step runs heavier than estimated.

### Wave 1 — Foundations and data-integrity guard

*Parallelism:* Can start together: W1-01, W1-02, W1-03, W1-05, W1-07 and W1-08 (no shared files). W1-04 follows W1-03 because both edit src/data_io.py. W1-06 follows W1-01 because of the frontend size guard.

| ID | Findings | Depends on | Priority | Effort | Risk | Owner | Parallel group | Model tier | Usage |
|---|---|---|---|---|---|---|---|---|---|
| W1-01 | ARC-005, QA-006 | — | P1 | S | Low | Frontend maintainer | G-FE | mechanical (low effort) | Light |
| W1-02 | ARC-001 | — | P1 | M | Medium | Engine maintainer | G-ENG | standard_reasoning (medium effort) | Moderate |
| W1-03 | ARC-003 | — | P1 | S | Low | Platform maintainer | G-PLAT | mechanical (low effort) | Light |
| W1-04 | QA-001 | W1-03 | P0 | M | Low-Medium | Engine maintainer with quality reviewer | G-VAL | expert_reasoning (high effort) | Moderate |
| W1-05 | ARC-006 | — | P3 | S | Low | Platform maintainer | G-VER | mechanical (low effort) | Light |
| W1-06 | QA-004 | W1-01 | P3 | S | Low | Frontend maintainer | G-FE | mechanical (low effort) | Light |
| W1-07 | DOC-006, FIN-004 | — | P1 | S | Low | Documentation owner; plan owner engages the CPA and estate attorney | G-DOC | mechanical (low effort) | Light |
| W1-08 | DOC-005, ARC-005 | — | P3 | S | Low | Maintainer | G-AGENT | mechanical (low effort) | Light |

**W1-01.** Frontend size guard: add per-file ceilings for every frontend/js file over about 1,500 lines and require a recorded reason line next to any ceiling increase (ARC-005 option 1).

- *Validation:* Run tests/test_frontend_size_ratchet.py locally; confirm a raised ceiling without a reason line fails; wc -l per file against the new caps.
- *Exit criteria:* Per-file caps exist for all large decomp modules and no ceiling is raised in this change.
- *Usage drivers:* One test file plus wc -l output.

**W1-02.** Replace the wildcard imports at src/engine_kernels.py:19, src/planning_engines.py:177 and src/reporting/workbook_common.py:16 (and the workbook_builder reliance on it) with explicit name lists using the AST method of deterministic_engine.py:46-52; give src/core.py an explicit __all__ (ARC-001 option 1).

- *Validation:* Golden-master and phase-golden equality with no regeneration; grep shows no `import *` in src/; monkeypatch-dependent tests (for example tests/test_lcv_feasibility_gate_regression.py) run locally.
- *Exit criteria:* Zero wildcard imports in src/; golden values unchanged.
- *Usage drivers:* planning_engines.py (3,050 lines) and engine_kernels.py (2,415) must be grep-located, not read whole; the slow phase-golden test. FLAG: run the phase-golden test once at the end, use `pytest -m "not slow"` while iterating.

**W1-03.** Rename the getLogger(__name__) loggers in src/sales_tax_year.py, src/year_end.py, src/data_io.py and src/market_data.py into the 'retirement_system.*' tree; log the startup migration result and errors inside run_startup_bootstrap; add a grep check forbidding getLogger(__name__) in src/; make the automatic-backup catch in dashboard_decomp_local_backups.js report failure (ARC-003 option 1).

- *Validation:* Unit test: a record from the sales_tax_year logger reaches the configure_logging handler with MaskingFilter applied; an injected migration error is logged by run_startup_bootstrap.
- *Exit criteria:* No getLogger(__name__) in src/; migration failures recorded on every launch path.
- *Usage drivers:* Five small edits and two unit tests.

**W1-04.** Data-integrity fix for plan defaults: blank means the schema default, or zero/none when the schema default is blank; remove the household-specific literals in src/parsing/client_sections.py; an unreadable dollar or rate value becomes a validation error instead of a logged fallback; the JSON/wizard path (data_io.py:858-885) uses the same default source; /api/build/start refuses to start while preflight blockers exist (QA-001).

- *Validation:* Contract test: parse_client on blank_plan_rows() gives mort_bal == 0, mort_pmt == 0, home_val == 0; test that every parser default equals the schema.csv default; test that build start is refused with a blocker; `tools/regen_golden_master.py measure` shows zero delta on populated fixtures before any regeneration.
- *Exit criteria:* No household-specific numeric default remains; a blank-mortgage plan projects no mortgage; builds cannot start with blockers.
- *Usage drivers:* client_sections.py is large (grep the cited lines), schema.csv, one measure run. Depends on W1-03 because both edit src/data_io.py.

**W1-05.** Version surfaces: derive the server banners in main.py and src/server/__main__.py from src.version.release_label(); make the admin.html cache-buster use VERSION; add pyproject.toml and package.json to tools/bump_version.py and to tools/check_version_surfaces.py with a case-insensitive 'SYSTEM v<digits>' pattern (ARC-006 option 1).

- *Validation:* Run the extended check_version_surfaces statically; confirm it flags a planted 'v11' banner.
- *Exit criteria:* All version surfaces agree with src/version.py or are checked against it.
- *Usage drivers:* Six small files.

**W1-06.** Set err.status in RetirementApiClient.request, delete the inline fallback in api() in dashboard_decomp_row_model.js, and add a Node vm-sandbox test that a 404 from /api/build/start triggers POST /api/build (QA-004 option 1).

- *Validation:* Sandbox test with mocked fetch returning 404; existing frontend tests run locally.
- *Exit criteria:* One error shape {message, status, errors, fieldErrors}; the 404 fallback is covered by a test.
- *Usage drivers:* FLAG: dashboard_decomp_row_model.js is 5,974 lines; grep the api() function, never read it whole.

**W1-07.** Backlog intake: add the untracked items to documentation/reference/BACKLOG.md (Business Succession inputs, Fidelity 1099-B parser, automatic wash-sale disallowance, pair-status turn-on approval, redaction run and Phase 5 owner task, wash-sale W1 CPA confirmation, and this review's professional-review gates: CPA for FIN-001, FIN-002, FIN-003 (SALT timing), FIN-008 (replacement-tax base and PTE interaction) and FIN-011; optional CPA check for FIN-006; estate attorney for FIN-004 and FIN-007, including the IRC 2058 treatment); adopt the inflow rule and a small docs check (DOC-006 option 1). Start the FIN-004 estate-attorney review or Illinois AG calculator comparison now, not just log it, so its elapsed time runs in parallel with Waves 2-3. Batch FIN-001, FIN-002, FIN-003 and FIN-008 (plus the optional FIN-006 check) into one CPA engagement.

- *Validation:* Grep the first 20 lines of documentation/future/**/*.md for not built / deferred / awaits / owner and confirm each has a BACKLOG row.
- *Exit criteria:* The docs check passes, every pending approval gate is in BACKLOG.md, and the FIN-004 attorney or calculator review has been started.
- *Usage drivers:* Status-line grep only; do not read plan bodies.

**W1-08.** Agent guidance: replace fixed line counts in .claude/claude.md with size bands, make .claude/hooks/large_file_guard.py compute size at call time against a threshold and guard module_catalog.py, fix the zip_screen path, the documentation/reference/CLAUDE.md location line and the conftest.py docstring (DOC-005 option 1; also the table update ARC-005 asks for).

- *Validation:* wc -l each listed file against its band; a whole-file Read of module_catalog.py is refused by the hook.
- *Exit criteria:* No stale count or path remains in the guidance or hook.
- *Usage drivers:* Two guidance files and one hook.

### Wave 2 — Validation, disclosures, recoverability and documentation currency

*Parallelism:* Parallel lanes: G-VAL (W2-01 then W2-02); G-ENG (W2-03, then W2-10 when the IRS/CMS sources are published); G-FE (W2-04 then W2-05); G-PLAT (W2-06); G-ARCH (W2-07 after W2-03, because both edit strategy_asset_service.py); G-DOC-HELP (W2-08); G-DOC-NAV (W2-09); G-CSS (W2-11). The frontend lanes share the total line ceiling, so each item must be line-neutral or negative, otherwise serialize it.

| ID | Findings | Depends on | Priority | Effort | Risk | Owner | Parallel group | Model tier | Usage |
|---|---|---|---|---|---|---|---|---|---|
| W2-01 | QA-002 | W1-04 | P0 | S | Low | Quality reviewer with platform maintainer | G-VAL | standard_reasoning (medium effort) | Light |
| W2-02 | QA-003 | W2-01 | P1 | S | Low-Medium | Quality reviewer | G-VAL | standard_reasoning (medium effort) | Light |
| W2-03 | FIN-001, FIN-004, FIN-005, FIN-008, FIN-009, FIN-010, FIN-012, QA-005 | W1-02 | P1 | M | Low | Engine maintainer; financial planner approves wording | G-ENG | standard_reasoning (medium effort) | Moderate |
| W2-04 | UX-001, UX-002 | W1-01 | P1 | M | Low-Medium | Frontend maintainer; usability reviewer | G-FE | standard_reasoning (medium effort) | Moderate |
| W2-05 | UX-003 | W2-04 | P2 | M | Low-Medium | Frontend maintainer; usability reviewer | G-FE | standard_reasoning (medium effort) | Moderate |
| W2-06 | ARC-004 | W1-03 | P1 | M | Low-Medium | Platform maintainer | G-PLAT | expert_reasoning (high effort) | Moderate |
| W2-07 | ARC-002 | W2-03 | P2 | M | Low | Architect / platform maintainer | G-ARCH | standard_reasoning (medium effort) | Moderate |
| W2-08 | DOC-001 | W1-01 | P2 | M | Low | Documentation owner; usability reviewer | G-DOC-HELP | standard_reasoning (medium effort) | Moderate |
| W2-09 | DOC-002 | W1-01 | P2 | S | Low | Documentation owner | G-DOC-NAV | mechanical (low effort) | Light |
| W2-10 | FIN-011 | W2-03 | P1 | S-M | Low | Financial planner with engine maintainer; CPA verifies state rows | G-ENG | standard_reasoning (medium effort) | Moderate |
| W2-11 | UX-006 | W1-01 | P3 | S | Low-Medium | Frontend maintainer | G-CSS | mechanical (low effort) | Light |

**W2-01.** Grid saves validate only format and range of the changed rows; 'required value missing' moves to the build preflight, which W1-04 made blocking (QA-002 option 1).

- *Validation:* Python functional test: blank_plan_rows() then POST /api/config/rows with one field returns 200; a build with a missing required field is refused; field_errors shape kept for format errors. Confirm the 422 behaviour exists before the change in an isolated test client.
- *Exit criteria:* Start New Plan can be saved field by field and still cannot be built incomplete.
- *Usage drivers:* config_service.py and schema_registry.py only.

**W2-02.** Treat 'dollars' and 'decimal' as 'currency' in schema_registry.validate_value using money.parse_strict_number; route /api/plan/forms writes through the same format/range validator; add a contract test that every type in reference_src/schema.csv is handled (QA-003 option 3).

- *Validation:* validate_value('abc', {'type': 'dollars'}) returns an error; schema-type coverage test; forms write with bad money text is rejected.
- *Exit criteria:* Server, parser and client accept the same number grammar for every money type.
- *Usage drivers:* Two modules and one test file.

**W2-03.** Disclosure and text bundle with one measured golden re-pin: limitation notice when qbi_eligible is on (FIN-001 interim); interim notice that the Illinois estate tax figure is an unverified approximation that may overstate tax for estates just above $4M, pending attorney review, wherever it feeds Post-Tax Inheritance, the estate sheet or the Roth strategy rationale (FIN-004 interim); life-policy inventory-only notice and sheet banner, worded so it does not imply that every non-ILIT policy is in the estate (FIN-005 option B); correct the income.py:285-286 comment and stop sheets_strategy.py:162,165,195 asserting a QBI basis and a 1.5% '<resident state> Corp Surcharge' the engine does not apply (FIN-008, FIN-001); widen the divorce scenario label (FIN-009 option A); help text on 401(k) limit simplifications (FIN-010 option A); fix the mortality docstring drift (FIN-012); replace the reference_data/state_tax.csv path in user-facing strings in core.py, sheets_strategy.py, strategy_asset_service.py:1131 and tax_assumptions.py:73 (QA-005 option 1).

- *Validation:* `regen_golden_master.py measure` shows text-only deltas; hand-check every changed string; one `regen --reason`; grep shows no user-facing reference_data/ path; the FIN-004 notice renders for an Illinois resident whose blended estate exposure exceeds the Illinois exclusion while estate_tax_objective_mode is not OFF/MONITOR_ONLY.
- *Exit criteria:* All listed disclosures shipped; no numeric golden delta.
- *Usage drivers:* FLAG: the phase-golden fixtures are about 10k lines; diff only the changed keys, never read the fixture whole.

**W2-04.** Route every destructive record action (caDelete, ciCloseYear, ciReopenYear, ciMarkRollover, bbApply replace, tlStart, tlCleanBank, tlVoid, slVoid) through showInAppConfirm with an action-named primary button, a consequence line and Cancel as initial focus; make tlConfirmed and the `window.confirm &&` guards fail closed; give log-linked sale voids a confirm that says Restore will not be available and drop the 'Use Restore' success text (UX-002 option 1, UX-001).

- *Validation:* Node vm-sandbox tests: each handler calls the in-app confirm and does nothing when dismissed or when no dialog exists; log_sell and manual voids produce different texts. Manual keyboard pass (Tab, Escape, initial focus) in the desktop shell.
- *Exit criteria:* No destructive record action uses native confirm() or proceeds without explicit confirmation; line total does not rise.
- *Usage drivers:* About 9 call sites across 6 modules; async conversion of tlConfirmed; row_model grep only.

**W2-05.** Add one shared announce(text, {error}) helper writing to persistent polite and assertive regions in frontend/index.html (generalizing slAnnounce); remove live roles from injected panel messages; make showMessage keep an unread error instead of replacing it (UX-003 option 1).

- *Validation:* Sandbox test that an info showMessage after an error leaves the error reachable; NVDA or Narrator pass in WebView2 on 1099-B apply, sale void and cash-account delete (each announced once, errors assertive).
- *Exit criteria:* One feedback convention; persistent regions exist at load.
- *Usage drivers:* Same modules as W2-04, hence serialized. If the helper is a new file, regenerate the architecture diagram after W2-07, not concurrently.

**W2-06.** run_backup uses the SQLite backup API (reuse plan_db_replace._backup_with_api) and checks the checkpoint result; _check_and_migrate writes a one-time pre-upgrade copy into plan_paths(...).backups_dir for real files, with a retention cap, skipping :memory: and read-only opens (ARC-004 option 1).

- *Validation:* Unit test: with an open reader or writer on a WAL database, the backup contains every committed row; unit test: opening a v23 fixture leaves a v23 pre-upgrade copy.
- *Exit criteria:* Backups are consistent snapshots; every in-place upgrade leaves a copy.
- *Usage drivers:* Touches the open path of every store; store tests run locally.

**W2-07.** Move estimate_housing_cost, STATE_ESTIMATES and the HOME_APPR/INFLATION defaults into src/housing/pricing.py and classify_symbol into src/portfolio_analytics.py with re-exports for one release; remove the duplicated plan_variant._years_out formula; add an import-direction rule (domain must not import server_services or server); regenerate SYSTEM_ARCHITECTURE_DIAGRAM.md (ARC-002 option 1).

- *Validation:* Housing and golden-master tests unchanged; regenerated diagram shows no Core->Server Services or Core->HTTP Routes edge apart from the desktop_api adapter; the import rule fails on a planted inversion.
- *Exit criteria:* No domain module imports server_services; src no longer imports financial_trends_reporter.
- *Usage drivers:* strategy_asset_service.py (1,256 lines) grep only. Depends on W2-03 because both edit strategy_asset_service.py.

**W2-08.** Rewrite the longest help records (Optimize, Spending Model, then Stress Test and Build & Results) into page-scoped text, move sub-page detail into HELP_SECTIONS, add glossary entries for terminal net worth, probability of success, LCV, allocation sleeve and KPI, and add a length and undefined-abbreviation guard (DOC-001 options 1 and 2). In the same rewrite, present 'Aim for an 80-90% success rate' (dashboard.js:4748) as a common planning convention, not a recommendation for this household, with financial-planner wording review.

- *Validation:* Word count per HELP_PAGES slot under the guard limit; every abbreviation defined or spelled out; tools/page_help_ledger.py check --strict passes with recorded accepted_losses; read the panels in the running app.
- *Exit criteria:* No help slot over the limit; no retired page names in help_registry.js.
- *Usage drivers:* help_registry.js is large; grep each record by key.

**W2-09.** Update documentation/reference/readme/README.md and the Plan Status cards in dashboard_decomp_checklist_closeout.js to the current nav, and extend the README currency test to check group placement through the Node vm sandbox (DOC-002 option 1).

- *Validation:* Walk every README and Plan Status direction against the running app in Set up and Maintain modes; extended test passes locally.
- *Exit criteria:* No retired page name or location in README or Plan Status.
- *Usage drivers:* Two files plus one test.

**W2-10.** Add dated 2027 rows to reference_src/tax_law_v10.json once the IRS inflation Rev. Proc. and the CMS 2027 fact sheet are published, rebuild reference.db, and make the year-end transition warn when the new first plan year has no dated rows (FIN-011 options A and B). External gate: primary-source publication.

- *Validation:* Compare each new row with the primary source and record it in tax_update_dashboard.csv; measure, hand-check one 2027 delta, then re-pin.
- *Exit criteria:* 2027 rows present and sourced, or a visible currency warning on year-end.
- *Usage drivers:* One golden re-pin; serialized with the other G-ENG items.

**W2-11.** Introduce a minimum label size token (11-12px) for results table headers and status chips in frontend/css/dashboard.css and add 150% and 200% steps to frontend/js/text_size.js (UX-006 option 1).

- *Validation:* Visual check at 100%, 130% and 200% on Build & Results at 1280px and 900px; existing reflow spec run locally.
- *Exit criteria:* No results header or status chip below the minimum token at 100%.
- *Usage drivers:* FLAG: dashboard.css is minified on long lines; edit with care and preserve line endings.

### Wave 3 — Sequential federal-deduction and Illinois S-corp replacement-tax corrections, and follow-on UI/doc work

*Parallelism:* G-ENG items W3-01 to W3-05 are strictly sequential, each with its own measure, hand-verified delta and re-pin. W3-01, W3-02, W3-03 and W3-05 now carry CPA gates, and W3-01 heads the chain, so a CPA gate there holds up the whole lane: batch FIN-001, FIN-002, FIN-003 and FIN-008 (plus the optional FIN-006 check) into one CPA engagement started under W1-07. W3-03 is time-sensitive because the enhanced SALT cap window closes after 2029. The other lanes can run alongside them: G-FE (W3-07), G-DOC-HELP (W3-06 then W3-10), G-DOC-STATUS (W3-08 then W3-09) and G-PLAT (W3-11).

| ID | Findings | Depends on | Priority | Effort | Risk | Owner | Parallel group | Model tier | Usage |
|---|---|---|---|---|---|---|---|---|---|
| W3-01 | FIN-008 | W2-03 | P2 | S | Low | Engine maintainer; financial planner; CPA | G-ENG | expert_reasoning (high effort) | Moderate |
| W3-02 | FIN-001 | W3-01 | P1 | M-L | Medium | Engine maintainer; financial planner; CPA | G-ENG | expert_reasoning (high effort) | Heavy |
| W3-03 | FIN-003 | W3-02 | P1 | M | Medium | Engine maintainer; financial planner; CPA | G-ENG | expert_reasoning (high effort) | Heavy |
| W3-04 | FIN-006 | W3-03 | P3 | S-M | Low | Engine maintainer; financial planner | G-ENG | expert_reasoning (high effort) | Moderate |
| W3-05 | FIN-002 | W3-04 | P3 | S | Low | Engine maintainer; CPA | G-ENG | expert_reasoning (high effort) | Light |
| W3-06 | UX-004 | W2-08 | P3 | S | Low | Frontend maintainer | G-DOC-HELP | mechanical (low effort) | Light |
| W3-07 | UX-005 | W2-05 | P3 | M | Low | Frontend maintainer | G-FE | standard_reasoning (medium effort) | Moderate |
| W3-08 | DOC-004 | W1-07 | P2 | M | Low | Documentation owner | G-DOC-STATUS | mechanical (low effort) | Moderate-Heavy |
| W3-09 | DOC-007 | W3-08 | P3 | S-M | Low | Documentation owner | G-DOC-STATUS | mechanical (low effort) | Light |
| W3-10 | DOC-003 | W2-08, W2-09 | P2 | M | Low-Medium | Documentation owner; platform maintainer if a route is added | G-DOC-HELP | standard_reasoning (medium effort) | Moderate |
| W3-11 | ARC-007 | W1-07 | P3 | S | Low | Platform maintainer | G-PLAT | mechanical (low effort) | Light |

**W3-01.** Add a dated state entity-tax rate (Illinois 1.5% replacement tax for S-corps) applied to the replacement-tax base (Illinois net income after modifications and apportionment, less the standard exemption; not federal ordinary income), reducing the distribution and the QBI base like employer FICA; disclose or model the PTE-tax election per the CPA's answer (FIN-008). Gate: CPA confirms the base and the PTE interaction.

- *Validation:* Unit test: an Illinois S-corp distribution falls by 1.5% of the modeled Illinois net-income base and federal taxable income falls by the deducted amount; measure, hand-check one delta, re-pin.
- *Exit criteria:* The engine and the S-corp sheet agree on the surcharge.
- *Usage drivers:* One golden cycle. Serialize after W2-10 if W2-10 lands first.

**W3-02.** QBI (IRC 199A) limits: SSTB and UBIA inputs, W-2 wages from scorp_salary, dated 2026+ threshold and phase-in-width rows, SSTB phase-out, wage/UBIA limit, the overall 20%-of-(taxable income before QBI minus net capital gain, which includes qualified dividends) cap applied in apply_agi_and_tax, and OBBBA's 2026+ minimum deduction ($400 when active QBI is at least $1,000, indexed) as dated rows; wire the parsed but unused scorp_qbi_phaseout input (FIN-001). Gate: CPA confirms rule values and the household's SSTB status.

- *Validation:* Closed-form unit cases (below threshold; SSTB inside and above phase-in; wage limit binding; taxable-income cap binding; minimum deduction where 20% of active QBI is below $400; overall cap with qualified dividends); one real-plan year checked by hand against Form 8995-A; measure, hand-verify, re-pin.
- *Exit criteria:* All four limit layers implemented and tested; the interim notice from W2-03 removed or narrowed.
- *Usage drivers:* FLAG: test-fix loops against goldens; iterate on closed-form unit tests and run the slow phase-golden test once per completed change. The overall cap may need to run after the LTCG/NIIT fixed point (roth_conversion_and_agi_tax.py:901-924).

**W3-03.** Feed the SALT state-income-tax component from state_income_tax (same income classification, or prior-year actual per the CPA's timing answer) in every projection year, keeping the cap logic; reuse the same SALT in the DAF makeup and HSA correction sub-stages (FIN-003). Time-sensitive: the main effect is in the 2025-2029 enhanced-cap window. Gate: CPA confirms SALT timing (current-year computed vs prior-year actual).

- *Validation:* Closed-form cases: (1) Illinois large conversion in 2026 with MAGI under $505k, delta large; (2) the same at MAGI of $620k or more, delta zero (floor); (3) a 2030+ homeowner with property tax of $10k or more, delta zero; (4) a 2030+ Illinois renter who itemizes, delta non-zero and bounded by $10k minus actual SALT; measure, hand-verify one year, re-pin.
- *Exit criteria:* No AGI-times-flat-rate proxy remains in the SALT calculation.
- *Usage drivers:* Shares the deduction block with W3-02; same golden-loop flag. Deltas are expected mainly in 2025-2029 rows; after 2029 only where state tax plus property tax is below $10k, which makes the one hand-verified delta easier to pick.

**W3-04.** Exclude premiums already deducted as self-employed health insurance from itemized medical expense and cap the SEHI source at premiums net of the premium tax credit with a one- or two-pass fixed point (FIN-006).

- *Validation:* Unit test for an itemizing self-employed household with and without a credit; measure, hand-verify, re-pin.
- *Exit criteria:* No premium is deducted under both 162(l) and 213.
- *Usage drivers:* Touches deterministic_engine.py:446-480; grep only.

**W3-05.** Compute the OBBBA senior deduction per qualifying person and settle the QSS threshold (FIN-002). Gate: CPA confirms the per-person reading.

- *Validation:* Unit cases at $200k, $250k and $300k MAGI with two qualifiers against a hand-filled Schedule 1-A; measure, hand-verify, re-pin.
- *Exit criteria:* Phase-out range is tested.
- *Usage drivers:* One function in core.py plus one golden cycle.

**W3-06.** Wire the Build Impact card 'i' buttons into the help panel (aria-controls=helpPanel plus help keys) and show a short visible percentile qualifier under the Worst-Case value (UX-004 option 1).

- *Validation:* Keyboard: Tab to each card 'i', Enter opens the definition; sandbox test that impactCardHtml carries aria-controls.
- *Exit criteria:* All three cards open help; Worst-Case shows its percentile without hover.
- *Usage drivers:* Shares help_registry.js with W2-08, hence after it.

**W3-07.** Extract the Sales Ledger tab bar and keydown into a shared helper and use it for the Strategy, Holdings, Reconciliation and Rental Properties tab strips, restoring focus after re-render (UX-005 option 1).

- *Validation:* Keyboard pass on each page; sandbox test that each tab bar emits aria-controls and a role=tabpanel panel.
- *Exit criteria:* One tab implementation; line total falls.
- *Usage drivers:* dashboard.js (6,474 lines) grep only; shares sales_ledger_ui.js with W2-05.

**W3-08.** Reconcile every documentation/future/ Status line against merge history, move shipped documents to archive/superpowers/ with pointers, and require a merge reference for 'implemented' (DOC-004 option 1 plus the light half of option 2).

- *Validation:* For each future/ document compare Status with `git log --merges`; afterwards count future/ documents marked implemented (target 0 or each names its open items).
- *Exit criteria:* Folder placement matches status; no 'not yet merged' line refers to a merged PR.
- *Usage drivers:* FLAG: about 35 status-uncertain documents; script the git lookups per branch or PR instead of reading bodies; update paths cited from other documents and memory files.

**W3-09.** Add the 11 missing reference/ items to DOCUMENTATION_INDEX.md (archiving one-off studies), add FUNCTIONAL_SPEC sections for Sales Ledger, 1099-B, wash sales, Year-End Transition, Account Tax Basis and Checking & Savings, and add an index-coverage test (DOC-007).

- *Validation:* Index-coverage test passes locally; FUNCTIONAL_SPEC headings checked against STEPS titles.
- *Exit criteria:* Every reference/ file indexed or archived.
- *Usage drivers:* Index and spec headings only.

**W3-10.** Concepts Guide: decide between generating an in-app HTML concepts page from the help registry (option 2) or refreshing the .docx with a currency check (option 1); first confirm whether the packaged build ships documentation/; make the Plan Status card a working link (DOC-003).

- *Validation:* Extract guide or page text and diff every 'Find it' screen name against STEPS titles; click through on a packaged build.
- *Exit criteria:* End-user concepts reference matches the nav and opens from the app.
- *Usage drivers:* Binary .docx handling, or a new local-only route plus diagram regeneration.

**W3-11.** Cache the Excel fallback index keyed on workbook mtime and record an exit criterion for each compatibility shim (Excel fallback, parse-time migrate_sectioned_data, legacy_conversion, market_data USER_AGENT fallback) in the backlog or module catalog (ARC-007 option 1).

- *Validation:* Measure Results Explorer index latency before and after on a real workbook (isolated environment); golden masters unchanged.
- *Exit criteria:* Each shim has a recorded removal trigger.
- *Usage drivers:* detailed_results.py only.

### Wave 4 — Professional-review-gated and structural work

*Parallelism:* G-ENG items are sequential (W4-01, W4-02, W4-03, W4-04, then W4-05). The FIN-004 attorney or calculator review starts in Wave 1 (W1-07), so W4-01 waits only on its outcome and on W3-05. W4-02 is fixed and hand-verified together with the IRC 2058 change under the same attorney gate. W4-06 (G-FE) can run alongside them. W4-07 is a decision item and can happen at any time after W1-07. Each structural item regenerates the architecture diagram in turn.

| ID | Findings | Depends on | Priority | Effort | Risk | Owner | Parallel group | Model tier | Usage |
|---|---|---|---|---|---|---|---|---|---|
| W4-01 | FIN-004 | W3-05, W1-07 | P2 | M | Low-Medium | Engine maintainer; estate attorney | G-ENG | expert_reasoning (high effort) | Moderate |
| W4-02 | FIN-007 | W4-01 | P3 | S | Low | Engine maintainer; estate attorney | G-ENG | expert_reasoning (high effort) | Light |
| W4-03 | FIN-012 | W4-02 | P3 | S-M | Low | Engine maintainer; financial planner reviews wording | G-ENG | standard_reasoning (medium effort) | Moderate |
| W4-04 | FIN-005 | W4-02, W2-03 | P2 | L | Medium | Engine maintainer; financial planner reviews beneficiary routing and owner/insured resolution | G-ENG | expert_reasoning (high effort) | Heavy |
| W4-05 | ARC-001 | W4-04 | P3 | L | Medium | Engine maintainer | G-ENG | expert_reasoning (high effort) | Heavy |
| W4-06 | ARC-005 | W1-06, W2-04, W2-05, W3-07 | P3 | L | Medium | Frontend maintainer | G-FE | expert_reasoning (high effort) | Heavy |
| W4-07 | FIN-009, FIN-010 | W1-07 | P3 | S (decision) | None until built | Owner; financial planner | G-DOC | mechanical (low effort) | Light |

**W4-01.** Illinois estate tax: after the estate attorney confirms the method (or the Illinois Attorney General calculator comparison started under W1-07 settles it), implement adjusted taxable estate = TE - 60,000, credit = min(table, tentative federal tax with a $4M exclusion) with a section 2001 rate schedule, and solve the interrelated deduction; then remove or narrow the W2-03 interim notice (FIN-004). Escalate to P1 if the review confirms the federal-tax limit and the household's blended estate exposure lies within about $4M-$5M.

- *Validation:* Calculator-matched test points at $4.05M, $4.5M, $5M and $10M; compare the selected Roth candidate before and after for a representative $4.1M-$4.5M Illinois household; measure, hand-verify one delta (estate figures and selected-candidate outputs both move), re-pin.
- *Exit criteria:* Attorney sign-off recorded; tests match the calculator.
- *Usage drivers:* The professional gate now starts in Wave 1 (W1-07), so its elapsed time is off the critical path; code work still follows W3-05.

**W4-02.** Freeze the DSUE at the first-death year's indexed amount and index only the survivor's own exclusion, and subtract the computed state estate tax from the federal base (IRC 2058), in one shared helper used by after_tax.estimate_terminal_estate_tax, roth_conversion._estate_tax_for_row and the Estate sheet in sheets_strategy.py; disclose the assumed portability election (FIN-007). Gate: the same estate-attorney review as W4-01, covering the 2058 treatment.

- *Validation:* Unit test with known first- and second-death years against a hand calculation; closed-form Illinois and New York estates above the exemption, one case where the 2058 deduction crosses the exemption boundary, and agreement across all three sites; measure, hand-verify, re-pin.
- *Exit criteria:* DSUE no longer indexed after the first death; federal estate tax is computed on the estate net of state estate tax at all three sites.
- *Usage drivers:* Same estate functions as W4-01, plus the Estate sheet block in sheets_strategy.py (grep only).

**W4-03.** Add a per-member actuarial sex field (default = current positional choice) read by both the scalar and vectorized mortality samplers (FIN-012 option A).

- *Validation:* Unit test: member 1 set to female samples the female column; default plans unchanged in golden and Monte Carlo baselines.
- *Exit criteria:* No positional sex assumption remains.
- *Usage drivers:* Schema change plus Monte Carlo baseline check.

**W4-04.** Integrate in-force life insurance behind the existing module switch: pay a first-death benefit into the survivor or beneficiary account in the death year (per Monte Carlo path) without adding it to the estate base again; add face to the estate base only for a policy on the last decedent's life that the decedent owned or whose beneficiary is the estate (IRC 2042), exclude third-party-owned and ILIT-owned policies, include a decedent-owned policy on another life at its projected cash value (IRC 2033); stop premiums after the death or term end; resolve free-text owner and insured to household members (FIN-005 option A).

- *Validation:* Scenario tests: first-death payout to the spouse not double counted; survivor-owned policy on the survivor's life in force at the second death included at face; third-party-owned and ILIT-owned excluded; expired term excluded; preferably a decedent-owned policy on another life included at projected cash value; measure, hand-verify, re-pin.
- *Exit criteria:* Survivor and estate outputs include in-force policies when the switch is on.
- *Usage drivers:* FLAG: per-path Monte Carlo death years; deterministic and Monte Carlo baselines both move.

**W4-05.** Lift the nested helpers of run_deterministic_projection_stage into pure functions in projection_stages modules, one group per change (housing and Medicare first), each verified by golden equality with no regeneration; then narrow the planning_engines re-export list (ARC-001 option 2).

- *Validation:* Golden-master and phase-golden equality before and after each extraction; new unit tests per lifted helper; regenerate the architecture diagram.
- *Exit criteria:* No domain calculation remains as a closure inside the stage function.
- *Usage drivers:* FLAG: deterministic_engine.py is 1,792 lines; read only the helper being lifted; one helper group per session.

**W4-06.** Extract dashboard_decomp_row_model.js by feature area and lower the per-file and total ceilings afterwards (ARC-005 option 2).

- *Validation:* Read the Python tests that assert on panel JS text before moving code; frontend Node tests and Playwright e2e run locally; regenerate the architecture diagram.
- *Exit criteria:* row_model below its new cap; ceilings lowered.
- *Usage drivers:* FLAG: 5,974-line file; grep only, one feature area per session.

**W4-07.** Owner scope decisions, recorded in the backlog before any build: post-divorce household modelling (FIN-009 option B) and per-member 401(k) limits with age-based and Roth catch-up rules (FIN-010 option B).

- *Validation:* Decision and rationale recorded in BACKLOG.md.
- *Exit criteria:* Each option is either scheduled with its own design or declined.
- *Usage drivers:* Decision only.


## 10. Validation plan

**Item-level validation.** Each work item in Section 9 has its own validation and exit criteria. Validation runs locally (pytest with `-v` into a log file, `npm test`, and Playwright where relevant) or in an isolated, disposable environment that follows the runtime-validation policy: source unchanged, no personal plan data, and artifacts kept outside the project.

**Finding-level validation.** Each finding's verification method in Section 5 becomes at least one test or one recorded manual check before the finding is closed.

**System acceptance criteria.**
1. A plan created with Start New Plan can be saved one field at a time.
2. The same plan cannot be built while required fields are blank.
3. When built with mortgage, LTC and S-corp rows blank, it projects no mortgage, no LTC face amount and the schema-default S-corp salary.
4. The CSV and JSON loaders give the same parsed values for the same missing input.
5. No destructive financial-record action proceeds without an in-app confirmation that names the action and states whether it can be undone. A keyboard-only pass and an NVDA or Narrator pass in the WebView2 shell are recorded for the Sales Ledger, Checking & Savings, Year-End cash and transaction-log flows.
6. Every engine-output change has one hand-verified representative delta recorded in `GOLDEN_MASTER_CHANGELOG.md`. No regenerate-run-regenerate loop occurs.
7. Closed-form tests exist for the corrected QBI (including the 2026+ minimum deduction and qualified dividends in the overall cap), SALT (inside and after the 2025-2029 cap window), SEHI, senior-deduction and replacement-tax (on the Illinois net-income base) rules, and for the DSUE and IRC 2058 estate changes.
8. CPA sign-off is recorded for FIN-001, FIN-002, FIN-003 and FIN-008, and for any 2027 state rows (FIN-011).
9. Estate-attorney sign-off is recorded for FIN-004 and FIN-007, including the IRC 2058 treatment. Until then, the FIN-004 interim notice renders for Illinois residents whose blended estate exposure exceeds the Illinois exclusion while estate scoring is on.
10. The financial planner approves the disclosure wording for FIN-004, FIN-005, FIN-009, FIN-010 and FIN-012, and the success-rate guidance wording rewritten in W2-08.
11. `grep` finds no `getLogger(__name__)` and no `import *` in `src/`.
12. An injected migration failure and an injected wash-detection failure both appear in `app.log`.
13. A backup taken while a reader is active contains every committed row.
14. Every in-place upgrade leaves a pre-upgrade copy.
15. README, Plan Status and the Concepts reference walk cleanly against the nav in both Set up and Maintain modes.
16. Every `documentation/reference/` file is indexed or archived.
17. Every deferred or approval-gated Status line has a BACKLOG row.
18. No frontend size ceiling is raised without a recorded reason, and the total falls after Wave 4.
19. When life policies are integrated (W4-04), scenario tests show no double count of a first-death payout and ownership-based estate inclusion.

## 11. Assumptions and open questions

**Technical.**
- `src/reference/reference.db` is assumed to match `reference_src/schema.csv` and `tax_law_v10.json`. The binary was not opened.
- It is unknown whether the packaged build includes `financial_trends_reporter`, which `/api/holdings/classes` needs, and `documentation/`, which the Concepts Guide needs.
- How native `confirm()` behaves under pywebview/WebView2 was not observed.
- Whether ProcessPool grandchildren are cleaned up when a build is cancelled on Windows was not verified.
- QA-002's 422 behaviour is inferred from code.

**Jurisdiction and rule year.** Each financial finding states its own jurisdiction, rule year, rule type and authority:
- US federal: IRC 199A, including the minimum deduction added by P.L. 119-21 sec. 70105 (FIN-001); IRC 151(d)(5)(C) as added by P.L. 119-21 sec. 70103, for 2025-2028 (FIN-002); IRC 164(b)(6)-(7) as amended by P.L. 119-21, with the enhanced cap for 2025-2029 and $10,000 from 2030 (FIN-003); IRC 101(a), 2033 and 2042 (FIN-005); IRC 162(l) and 36B with Rev. Proc. 2014-41 (FIN-006); IRC 2010(c)(4) and 2058 (FIN-007); IRC 402(g) and 414(v) as amended by SECURE 2.0 (FIN-010).
- Illinois: 35 ILCS 405 (FIN-004); 35 ILCS 5/201(c), and the PTE-tax election under 35 ILCS 5/201(p) (FIN-008).
- Rule values were compared with the reviewer's knowledge through mid-2026, not with primary sources fetched in this run.

**External facts.**
- Whether 2027 IRS inflation adjustments and CMS 2027 premium and IRMAA figures were published by 2026-11-10.
- Whether enhanced ACA premium credits were extended beyond 2025. The dataset assumes they ended.
- Whether the Illinois estate tax credit is limited by federal tax computed with a $4M exclusion.
- Whether the Illinois PTE-tax election is available for 2026 and later (FIN-008).

**Household facts that set the impact.**
- Whether working-year taxable income exceeds the 199A threshold, and whether the business is an SSTB (FIN-001).
- Whether S-corp wages exceed the Roth-catch-up wage threshold (FIN-010).
- Whether the household itemizes in conversion years, whether conversion-year MAGI is below the SALT phase-down threshold (about $505k in 2026), and, from 2030, whether modeled state tax plus property tax is below $10k (FIN-003).
- Estate size, and the Roth optimizer's blended estate exposure, relative to the Illinois $4M exclusion (FIN-004, FIN-005).
- Who owns each life policy and on whose life (FIN-005).

**Modeling assumptions recorded at sign-off.**
- FIN-003's effect is bounded by the SALT cap window. From 2030 the $10k cap makes the proxy irrelevant for homeowners whose property tax reaches $10k.
- A timely portability election (Form 706) at the first death is assumed (FIN-007).
- Life-policy owner and insured are free text. A blank owner is treated as the insured, and the IRC 2035 three-year rule is not modeled (FIN-005).
- The engine has no Illinois modification or apportionment inputs, so the replacement-tax base is an approximation (FIN-008).

**Professional review required.**
- CPA: FIN-001; FIN-002; FIN-003 (SALT timing: current-year computed vs prior-year actual under IRC 164); FIN-008 (replacement-tax base, PTE-election interaction and entity-level federal deductibility); FIN-011 state rows; and the PR #418 wash-sale W1 rule. Optional: FIN-006 (Rev. Proc. 2014-41 method). Batch these into one engagement started under W1-07.
- Estate attorney: FIN-004 (started in Wave 1 under W1-07) and FIN-007, including the IRC 2058 treatment.
- Financial planner: FIN-005 beneficiary routing and owner/insured resolution; the disclosure wording for FIN-004, FIN-009, FIN-010 and FIN-012; and the success-rate guidance wording (W2-08).
- Not required: FIN-006 (optional CPA check only), FIN-009 Option A (Option B would need tax and benefits review), and FIN-012 beyond planner wording review.

Nothing in this report is legal, tax, fiduciary or benefits advice. Findings concern arithmetic correctness and disclosure, not the suitability of any plan.

## 12. Review limitations

- Static, read-only review. No tests, builds, golden-master measurements or application runs were performed. Every dollar impact is a hand estimate from reading code, and every accessibility statement is based on markup and code paths. No assistive technology, keyboard, zoom or contrast-in-context run was done.
- No primary legal or tax sources were fetched: no IRS Rev. Procs., CMS fact sheets, SSA pages, statutes or the Illinois Attorney General calculator. Rule values and legal readings rest on the financial-planner reviewer's knowledge through mid-2026. FIN-001, FIN-002, FIN-003, FIN-004, FIN-007, FIN-008 and FIN-011 need professional confirmation.
- GitHub coverage is partial. A scope search matched 108 PRs, of which 30 were retrieved and 15 bodies read. Commit searches were truncated at 30. The repository has zero issues, so pending work was inferred from PR descriptions only. GitHub MCP tools were not called in the expert or synthesis stages; those stages used the shared manifest plus read-only local git. Collaborator permissions were unavailable (HTTP 403). Branch protection, deploy keys, webhooks and installed apps were not inspected.
- Secrets: GitHub secret scanning is unavailable on this repository because Advanced Security is not enabled, and git history was not scanned for previously committed secrets. An empty result means 'not scanned', not 'clean'.
- Ref state: the reconnaissance passes read the working tree at e75d6ac1 while four golden, test and changelog files were uncommitted. The expert stages read main @ 3c7bb121, which differs from e75d6ac1 only in those four files. src/ and frontend/ are identical.
- Not read, or only sampled: the bodies of most of the 26 projection stage modules; the optimizer objectives (optimization.py, daf, qlac, housing optimizer, strategy_sweep); the Monte Carlo regime and fat-tail sampling and the parity between the replay and scalar engines; hsa_schedule.py; year_end.py; gain_harvest.py and tlh.py; beneficiary_titling_audit; PIA derivation; pension and annuity pricing; the apply_death_transition body; app_store migrations; the csv_exchange, broker_1099b, broker_activity and Monarch import modules; the Trends reporter data modules, change_password.html and access.js; the housing, allocation and Roth guardrail panels; the Planning Workbench body; the full HELP_SECTIONS and HELP_FIELDS; the Excel workbook's visual formatting; and the runbook procedures, step by step.
- The 415 broad `except Exception` sites were counted, not reviewed individually. About 23 direct fetch() call sites that bypass the API client were not inspected.
- Binary assets were not opened: reference.db, demo_seed.rpx, zip_metrics.csv.gz and the PNG screenshot sets. The Concepts Guide was inspected only by extracting the text of word/document.xml. Freshness of generated files was not checked.
- Performance and backup-integrity risks are inferred from code and were neither measured nor reproduced. Monte Carlo cost, build wall-clock time and frontend render cost were not measured.
- Not established: whether the packaged PyInstaller build bundles financial_trends_reporter and documentation/; how native confirm() behaves under pywebview/WebView2; and whether build cancellation cleans up ProcessPool children on Windows.
- Document status was reconciled against merge history for a sample of about six future/ documents. The 35 status-uncertain documents counted by the inventory were otherwise taken from their first 20 lines. Third-party imports were inventoried by regex over import lines, so dynamic imports could be missed. package-lock.json transitive dependencies were not inventoried.
- Orchestrator edits to the verified register: QA-006 was marked duplicate of ARC-005 (C-01), and every finding received linked_implementation_items and, where relevant, github_context. One evidence label in QA-006 was reworded to name the project-rule section by its test name. No other disposition, severity or field was changed at synthesis.
- Sign-off edits to the register: FIN-001, FIN-003, FIN-004, FIN-005, FIN-006, FIN-007, FIN-008, FIN-009, FIN-010 and FIN-012 were amended as recorded in Section 14. No severity or confidence changed. FIN-003's verification status became partially_confirmed (its rule year was narrowed), and FIN-007's title and scope were widened to include the IRC 2058 deduction. The waves, coverage and conflict artifacts were updated to match.
- During synthesis the local checkout moved, outside this stage, to branch system-review-2026-11-10 @ 68679559 ('docs: save 2026-11-10 system review intermediate artifacts'). That commit only adds 10 review-artifact files on top of 3c7bb121, so no reviewed source changed. Evidence in this report refers to e75d6ac1 / 3c7bb121.
- The financial-planner stage recorded that its session scratch path differed from the task's scratch path. Its shared context was read from the task path, and it wrote no artifacts, so no input was lost.

CI was intentionally excluded from this review.

Runtime behavior was not validated during this review.

## 13. Finding disposition appendix

### 13.1 Duplicates

| Finding | Duplicate of | Reason |
|---|---|---|
| QA-006 — The frontend size ratchet keeps getting raised (100 of 106 changes), so it does not constrain size (quality, low) | ARC-005 | Cross-expert duplicate (conflict C-01): same defect as ARC-005 (frontend size ceiling raised in feature work). The stronger finding is kept; this one's tally is folded in as corroborating evidence. Linked work: W1-01. |

### 13.2 Refuted or narrowed claims inside verified findings

| Finding | Disposition | What was refuted, narrowed or left unverified |
|---|---|---|
| ARC-004 | partially_confirmed | The data-loss trigger is conditional and was not demonstrated. sqlite3's 5-second busy timeout makes FULL checkpoints wait, backups are opt-in, and per-step migration transactions soften the 'faulty migration' half. The no-pre-upgrade-copy half is fully confirmed. |
| ARC-007 | confirmed (corrected) | The index path opens the workbook with read_only=True. read_only=False applies only to chart sheets and the full-results path, so the cost per navigation is smaller than first stated, and it was not measured. |
| ARC-002 | confirmed (one item unverified) | The verifier did not open SYSTEM_ARCHITECTURE_DIAGRAM.md:39-78. The finding stands on the import evidence alone. |
| FIN-004 | partially_confirmed | The code behaviour is confirmed. The legal claim (an Illinois credit limited by federal tax at a $4M exclusion) is unverified, so the size of the overstatement in the $4M-$5M band is uncertain. The missing $60k adjustment is the most likely error. |
| FIN-011 | partially_confirmed | Whether 2027 IRS and CMS figures were published by 2026-11-10 was not checked. If they were not, the missing rows are expected maintenance rather than a defect. |
| FIN-002 | confirmed (severity lowered to low) | The gap is bounded to 2025-2028 and the $150k-$350k MAGI band. The per-person reading still needs CPA confirmation. |
| FIN-003 | partially_confirmed (rule year narrowed at sign-off) | The code behaviour is confirmed. The 'All projection years' scope is narrowed: the main effect is in the 2025-2029 enhanced-cap window, and from 2030 it survives only for itemizers whose modeled state tax plus property tax is below $10k. The planner's 'no effect in high-MAGI conversion years' holds only above about $606k-$626k of MAGI. Severity is kept at medium (planner dissent). |
| FIN-004 | partially_confirmed (impact corrected at sign-off) | 'Lifetime spending results are not affected' was removed: the estate penalty enters the Roth candidate score and can change the selected schedule. MAXIMIZE_PTI cannot be reached from input and is not cited. |
| FIN-005 | confirmed (recommendation refined at sign-off) | Estate inclusion is ownership-based (IRC 2042), not ILIT-only, and a first-death payout must not be double counted. |
| FIN-007 | confirmed (scope widened at sign-off) | The missing IRC 2058 deduction is folded in (three sites, including the Estate sheet). The '$30M' threshold is restated against the second-death combined exclusion. |
| UX-004 | partially_confirmed (severity lowered to low) | Refuted: the claim that the 5th-percentile qualifier appears only in the tooltip (the narrative above the cards states it whenever a before/after delta exists), and the claim that EFTR is unexplained (the visible title expands it). LCV is the only unexpanded acronym. The inert help button is confirmed. |
| UX-005 | partially_confirmed | Refuted: the Holdings content does have role=tabpanel (holdings_tabs.js:42). What it lacks is the aria-controls/aria-labelledby link, roving tabindex and key handling. |
| UX-003 | confirmed (four sites unverified) | sales_entry.js, sales_queue.js, sales_tax.js and sales_wash.js were not opened by the verifier. That freshly injected live regions announce unreliably is well-known assistive-technology behaviour but was not tested. |
| UX-002 | confirmed (scope narrowed) | Reopen and Rollover confirms do state their consequences. 'Understates' applies most strongly to caDelete, tlVoid and the 1099-B replace. The Cancel-first focus of showInAppConfirm was not verified. |
| DOC-001 | confirmed (detail corrected) | TNW is also expanded at help_registry.js:128, not only at line 485. |
| DOC-003 | confirmed (confidence medium) | The PR #235 author note and whether documentation/ ships in the packaged build were not verified. |
| DOC-006 | confirmed (citations off by one or two lines) | The substance holds. The PR #418 CPA reference was not verified. |
| QA-001 | confirmed (two sub-claims unverified) | The roth_brk 0.24 JSON-path default and the build_service preflight internals were not fully checked. Required=TRUE fields (earned income, spending, home value) are listed as preflight blockers, so the silent-default risk is strongest for the mortgage, LTC and S-corp fields. |
| QA-002 | confirmed (confidence medium) | The '21 of 53 required fields' count was not reproduced by the verifier, and runtime behaviour is inferred. reference.db could differ from schema.csv. |
| QA-005 | confirmed (impact widened) | The stale path also appears in strategy_asset_service.py:1131, tax_assumptions.py:73 and taxes.py:286, and is pinned in golden fixtures, so the fix moves golden masters (C-05). |

### 13.3 Reconnaissance leads and GitHub items refuted, resolved, superseded, duplicate or with insufficient evidence

| Item | Final disposition | Reason |
|---|---|---|
| PR #233 | insufficient_evidence | usability_accessibility: contextual_only — Limitation notices and the Admin a11y request. src/limitation_notices.py was opened. The N7 wording is terse; passed to the planner and docs experts. / quality: insufficient_evidence — Requests for N7 heading prose and a screen-reader pass not checked |
| PR #234 | resolved | architect: resolved — src/server_services/build_job_service.py:175-192 request_cancel terminates the build subprocess. Whether ProcessPool grandchildren are cleaned up on Windows was not verified. |
| PR #267 | insufficient_evidence | usability_accessibility: contextual_only — Prose guard. Relevant as a constraint on fixes for UX-004. / documentation: insufficient_evidence — Author-flagged judgement calls (restyled 'Why it matters', removed hover titles) were not individually inspected. |
| PR #366 | resolved | financial_planner: contextual_only — Relevant to FIN-011, because the first plan year will roll to 2027 without dated rows. year_end.py was not read. / quality: resolved — Phase 3 shipped later as #380 (9d4dc360) |
| PR #388 | resolved | architect: resolved — git grep finds no /api/year-end or wash-signature calls in frontend/js at the reviewed ref, so this was superseded by the #418 redesign. / quality: insufficient_evidence — Follow-ups may be moot after the #418 redesign; not checked |
| PR #418 | insufficient_evidence | architect: contextual_only — Schema v23/v24 DDL is additive (sales_repo.py:101-110, transactions_repo.py:66-78). The wash-sale rule correctness belongs to the financial planner. / financial_planner: insufficient_evidence — The code in wash_sales.py:91-185 matches the stated rules. CPA confirmation of W1 is still appropriate. Possible edge case: the (account, symbol, purchase_date) key skips an unsold same-day buy in the same account. No finding raised. / usability_accessibility: contextual_only — The Sales Ledger v3 restructure is the provenance of the native confirms and the void/Restore wording in UX-001 and UX-002. Its body states several flows were not exercised in the app. / documentation: contextual_only — Wash-sale CPA confirmation pending; cited in DOC-006 as an untracked approval gate. Tax correctness is out of the documentation charter. / quality: insufficient_evidence — Pending CPA confirmation of wash-sale W1 cannot be checked from code; wash tests exist |
| ENG-08 | insufficient_evidence | financial_planner: insufficient_evidence — Rounding and footing were not inspected by this expert. / quality: contextual_only — Float engine behind a Decimal boundary confirmed in money.py; footing not inspected |
| Prior review FIN-001 (SYSTEM_REVIEW_2026-10-19) | resolved | financial_planner: resolved — withdrawal_cascade_investment_tax.py:256-297 now adds the gain to NIIT MAGI, ACA MAGI and taxable SS. IRMAA MAGI and the senior phase-out were not traced, so the fix may be partial. |
| Prior review FIN-009 (CST double count) | resolved | financial_planner: resolved — after_tax.py:772-775 and roth_conversion.py:119-121 no longer subtract the CST federally. tax_update_dashboard.csv still says 'remains open' (documentation drift). |
| R-TDC-01 | resolved | quality: resolved — The uncommitted golden regen is now committed in 11f6e809 and merged via #420 (3c7bb121); git status is clean |
| R-TDC-03 | resolved | quality: resolved — The demo client_hsa_schedule.csv is header-only, so leaving it out of the frozen fixture loses no data; HSA schedule has 16 dedicated test files |
| R-TDC-04 | duplicate | documentation: duplicate — Same as ENG-09; folded into DOC-005. |
| UIR-05 | resolved | usability_accessibility: resolved — Enter-to-next is scoped to focusableEntries() field and table inputs (navigation.js:462-464). Nav search, dialogs and width fields are excluded (dashboard.js:6123-6145). |
| UIR-09 | insufficient_evidence | usability_accessibility: insufficient_evidence — The Admin shell lacks a skip link and aria-pressed on scope toggles. Labels appear present. No screen-reader pass was possible. |
| UIR-11 | duplicate | documentation: duplicate — Same as ENG-09 / R-TDC-04; folded into DOC-005. |
| ENG-10 sub-claim 'legacy v10 DB still written' | refuted | src/local_store.py:5-8: the database is imported once and no longer written (architect). |
| ENG-03 'silent degradation in post-projection steps' | refuted (as silent) | report_compute.py:283-338 logs each failure and surfaces config_contract_warnings. The remaining logging gap is ARC-003. |
| PR #388 'extra /api/year-end + wash-signature cost per ledger load' | superseded | No such calls at the reviewed ref; replaced by the #418 redesign. |
| R-TDC-01 'golden re-pin uncommitted' | superseded | Committed in 11f6e809 and merged via #420. |

### 13.4 Observations noted by experts but not raised as findings (insufficient evidence; candidates for follow-up)

- HSA contribution (src/projection_stages/income.py:344-358): the parsed base already includes a $1,000 catch-up and is indexed by brk_inf although the statutory catch-up is fixed. hsa_catchup is never set, and min(x, x) is a no-op (financial planner). Not raised as a finding; needs a closed-form check. Planner sign-off: a plausible low-severity gap to check before the Wave 3 deduction-block sequence closes, so the block is not re-pinned twice (unresolved dissent).
- The 0.5%-of-AGI charitable floor is applied in 2025, before OBBBA's floor takes effect (roth_conversion_and_agi_tax.py:761-791). The OBBBA 2/37 itemized-deduction limit and the 2026 non-itemizer charitable deduction were not found by grep and were not traced (financial planner). Planner sign-off: same position as the HSA item; closed-form checks before the Wave 3 sequence closes (unresolved dissent).
- Wash-sale W1 lot key (account, symbol, purchase_date) may skip an unsold same-day buy in the same account (wash_sales.py:91-185). Untested edge case; CPA confirmation of W1 is pending (PR #418).
- In QSS years the engine passes filing='MFJ' to the senior deduction, so the threshold is $150k where the reviewer reads $75k (folded into FIN-002's implementation considerations).
- tax_update_dashboard.csv still says the prior review's FIN-009 (CST double count) is open, although after_tax.py:772-775 fixes it (documentation drift).
- The Trends remote error handler (access_routes.py:112-116) returns exception text to signed-in guests, and change_password does not end the user's other sessions (architect; minor).
- The Admin Control Center may show raw gendered choice values such as Husband_IRA (admin.js:786 has no personDisplay mapping). The Admin shell also lacks a skip link and aria-pressed on its scope toggles (usability; not verified on screen).
- TERM_NOTES (dashboard.js:214-224) glosses terminal net worth as 'projected final portfolio value', which conflates net worth with the portfolio, and the Monte Carlo success gloss is dense. 'Aim for an 80-90% success rate' (dashboard.js:4748): the planner's position is that the UI should present it as a common planning convention, not a recommendation for this household. The wording review is routed into W2-08.
- The left-nav follow-up plan's 'Status: planned' is stale, because workstreams A, B and D appear landed in code (covered by DOC-004).
- A limitation_notices failure becomes an empty list with no user warning (report_compute.py:283-338; quality).
- Federal estate tax omits the IRC 2058 deduction for state estate tax (after_tax.py:774-783, roth_conversion.py:122-141, sheets_strategy.py:2045-2065). Raised by the planner at sign-off and folded into FIN-007 and W4-02 (low), not tracked separately.

### 13.5 Unverified findings

None. Every finding in the register has a verification disposition.

## 14. Financial planner sign-off

**Verdict: approved with changes.** The planner read the full synthesized report and the register (38 entries: 37 material plus QA-006 as a duplicate; the severity counts match). The planner spot-checked the FIN claims in `src/core.py` (state_death_tax_credit, illinois_estate_tax, senior_bonus_deduction, salt_cap), `reference_src/tax_law_v10.json` (SALT rows), `src/projection_stages/roth_conversion_and_agi_tax.py`, `src/projection_stages/income.py`, `src/after_tax.py`, `src/engine_sections/roth_conversion.py`, `src/planning_engines.py`, `src/parsing/advanced_modules.py` and `src/parsing/client_sections.py`. The FIN findings tested hold on the code evidence, and jurisdiction, rule year, rule type and authority are recorded. The report keeps arithmetic correctness separate from suitability and disclaims advice.

The sign-off depends on the CPA and estate-attorney gates in Section 11. It covers framing, severity and sequencing only. It is not a professional confirmation of any rule value or legal reading, because no primary sources were fetched in this run.

### 14.1 Requested changes and resolution

| ID | Material | Request (summary) | Re-verification | Resolution |
|---|---|---|---|---|
| PC-01 | yes | FIN-003: limit rule year and impact to the 2025-2029 enhanced-cap window; lower to low and W3-03 to P2; revisit the Heavy estimate | partially upheld | Rule year, assumptions and impact narrowed; four bounded validation cases added; W3-03 drivers note adds where deltas fall. Severity medium, W3-03 P1 and Heavy are kept. Verification status becomes partially_confirmed. Downgrade not adopted (dissent). |
| PC-02 | yes | FIN-004: correct 'lifetime spending results are not affected'; interim W2-03 disclosure; start attorney review early under W1-07; consider W4-01 at P1 | partially upheld | Impact restated (estate penalty drives Roth candidate selection); 'Roth conversion schedule selection' added to affected workflows; interim notice added to W2-03; attorney/AG-calculator review starts in Wave 1; W4-01 now also depends on W1-07. W4-01 stays P2 with a conditional escalation to P1 (dissent). MAXIMIZE_PTI is not cited. |
| PC-03 | yes | FIN-005: no double count of a first-death payout; IRC 2042 ownership-based inclusion; expired term has no estate effect; new tests | upheld | Option A, assumptions, impact, dependencies, implementation considerations and test requirements rewritten; W4-04 description, owner and validation updated; Section 6, Section 8 and the W2-03 disclosure wording aligned. |
| PC-04 | yes | Professional-review statement for FIN-003, FIN-006, FIN-008, FIN-009 and FIN-012; CPA gates for FIN-003 and FIN-008 | upheld | Statements added to each record. FIN-008's base corrected to Illinois net income after modifications and apportionment, less the standard exemption. CPA added to W3-01 and W3-03 owners with gate lines. W1-07 gate list, acceptance criterion 8, Section 11 and Section 12 updated. One batched CPA engagement is recommended because W3-01 heads the sequential lane. |
| PC-05 | yes | New low observation: federal estate tax omits the IRC 2058 state-death-tax deduction; pair with FIN-007 | upheld | Folded into FIN-007 (title, jurisdiction, evidence, impact, recommendation, tests) with a third site the planner did not cite (`sheets_strategy.py:2045-2065`). W4-02 widened; acceptance criterion 9, Section 11, coverage area 17 and 13.4 updated. Severity stays low. |
| PC-06 | yes | FIN-001/W3-02: add OBBBA's 2026+ minimum deduction; net capital gain includes qualified dividends; 2026+ thresholds from dated rows | upheld | Recommendation, dependencies, implementation considerations and tests updated; W3-02 change, validation and drivers updated; acceptance criterion 7 and Section 11 updated. |
| PC-07 | no | Reframe FIN-008 as an Illinois entity-level understatement, not part of the federal deduction block; note the generic sheet label | applied | Executive summary theme 2, top recommendation 2, Section 4, Section 7 and the Wave 3 title reworded. FIN-008 impact and observed behavior now note the slight federal overstatement and the '<resident state> Corp Surcharge' label at `sheets_strategy.py:165`. |
| PC-08 | no | FIN-007 threshold wording; state the portability assumption in Section 11 | applied | Threshold restated as the gap between the correctly frozen and the engine's fully indexed combined exclusion at the second death (about $30M in 2026 dollars; about $43.7M vs $54.2M in the 2030/2050 example). Portability assumption added to Section 11. |
| PC-09 | no | FIN-010: precise Roth-catch-up trigger | applied | Rule year and impact now state the prior-year FICA-wage test from the sponsoring employer ($150,000 of 2025 wages for 2026) and that it applies only on the S-corp salary path (`income.py:283-288`). |
| PC-10 | no | Present 'Aim for an 80-90% success rate' as a convention, not a recommendation; route to W2-08 | applied | Planner position recorded in 13.4; W2-08 change and acceptance criterion 10 updated. |
| PC-11 | no | Replace PENDING with the verdict; list material changes and dissent | applied | This section and the executive summary verdict line. |

### 14.2 Impact analysis for material changes

**PC-01 (FIN-003), partially upheld.** Evidence re-opened in this run: `reference_src/tax_law_v10.json:386-474` (cap $40,000-$41,624 for 2025-2029, back to $10,000 from 2030; $500k phase-down threshold growing 1% a year through 2029) and `src/core.py:1269-1296` (cap reduced by 30% of MAGI above the threshold, floored at $10k). What holds: from 2030 a household whose property tax alone reaches $10k sees no effect, so 'All projection years' was too broad. What is overstated: the floor binds only above about $606k of MAGI in 2026 ($626k in 2029); the finding's own $300k-AGI example sits below the threshold and keeps its full impact (about $10k-$15k of overstated SALT, $2.4k-$3.6k a year of understated federal tax). The FIN-002 comparison does not carry over: the per-year effect is 2-3x larger, it falls in the 2026-2029 conversion years and skews the optimizer, it can flip a household into itemizing, and its post-2029 tail is open-ended. Under `findings-schema.md:44-45` that is a meaningful functional issue, so medium stays. Because the window closes after 2029, delay is costly, so W3-03 stays P1; it still spans three sub-stages and shares W3-02's golden loop, so it stays Heavy. Touched: FIN-003 record and section; W3-03 change, validation and drivers; executive summary theme 2; Section 7 item 4; Sections 10, 11 and 13.2.

**PC-02 (FIN-004), partially upheld.** Evidence re-opened in this run: `src/planning_engines.py:568-600` (estate_tax_penalty = estate_mult x the terminal estate tax on a 0.65 PV-average plus 0.35 peak exposure; estate_mult 0 for OFF/MONITOR_ONLY, 1.0 for BALANCED, 2.0 for STRONG), `src/planning_engines.py:614-645` (estate_component summed into score, doubled under ESTATE_TAX_AWARE), `src/engine_sections/roth_conversion.py:412,455` (candidates ranked by score) and `src/server/app_core.py:354-355` (default BALANCED_RETIREMENT and BALANCED). The overstated Illinois tax therefore enters the default objective and can change the selected schedule, lifetime tax and terminal net worth. Corrections to the planner's evidence: MAXIMIZE_PTI cannot be reached because `src/parsing/roth_conversion_policy.py:101-105` coerces unknown modes to BALANCED_RETIREMENT; exposure is 1.0x by default and up to 4.0x under STRONG plus ESTATE_TAX_AWARE; the $4M-$5M band applies to the blended exposure, not the nominal terminal estate. Spending invariance was not verified, so the claim was dropped rather than reversed. The unconditional raise of W4-01 to P1 was not adopted, because confidence is low and the size of the overstatement rests on an unverified legal reading; the W2-03 notice and the Wave 1 review start address plan-selection risk sooner. Touched: FIN-004 record and section (impact, affected workflows, recommendation, dependencies, verification, linked items W1-07, W2-03, W4-01); W1-07, W2-03 and W4-01; Section 6, Section 7 items 3 and 7, Section 8; acceptance criteria 9 and 10. W4-01 will move selected-candidate outputs as well as estate figures and needs a hand-verified delta under the golden runbook.

**PC-03 (FIN-005), upheld.** `src/parsing/advanced_modules.py:131-146` already parses owner, insured, beneficiary, term_end_year, cash_value_today, cash_value_growth_rate and owned_by_ilit. `src/after_tax.py:746-783` builds the estate base from total_nw plus business value, taken from the terminal row (and from the second-death row for the optimizer, `planning_engines.py:590-599`), so a benefit paid into the survivor's accounts is already in that base. The old W4-04 text ('add non-ILIT face to the estate base') and the old test would both have double counted. Implementer refinements recorded in the finding: value a decedent-owned policy on another life at projected cash value; resolve free-text owner and insured to household members with a conservative default; IRC 2035 not modeled; PTI is measured at the plan-end row. Severity, wave placement and effort are unchanged.

**PC-04 (professional review), upheld.** `.claude/skills/system-review/references/financial-domain-governance.md` requires every tax, benefits or legal-rule finding to say whether qualified professional review is required, and the five records did not. Re-opened evidence: `income.py:285-286` (misleading comment), `client_sections.py:1294` and `sheets_strategy.py:165,195` (scorp_state_rate read only by the sheet), `roth_conversion_and_agi_tax.py:764-774` and `core.py:1052-1070` (FIN-003), `deterministic_engine.py:446-480` (FIN-006), `engine_kernels.py:797` (FIN-012). The CPA gate for FIN-008 is justified because the replacement-tax base is Illinois net income after modifications, not federal ordinary income, and the PTE-election status and entity-level deductibility were not checked against sources. The FIN-003 timing gate is a reasonable conservative choice. FIN-006 is 'not required, optional CPA check' and stays out of acceptance criterion 8. FIN-009 needs review only if Option B is built. FIN-012 is an actuarial table choice. Side effect: a CPA gate on W3-01, the head of the sequential G-ENG lane, now holds up the lane; batching one CPA engagement for FIN-001, FIN-002, FIN-003 and FIN-008 limits the delay.

**PC-05 (IRC 2058), upheld.** `src/after_tax.py:774-783` and `src/engine_sections/roth_conversion.py:122-141` compute federal tax as 40% of (estate - exemption) and add state tax afterwards; `src/reporting/sheets_strategy.py:2045-2065` (the Estate sheet, not in the planner's evidence) does the same and drives the 'ACTION REQUIRED' message. State estate tax is computed only for Illinois and New York (`core.py:1421-1466`). The overstatement is 0.40 x min(state tax, excess over the exemption), so 'about 40% of the state tax' is an upper bound. It pulls opposite to FIN-007's DSUE indexing on the same very-large-estate population, so both are fixed and hand-verified together in W4-02, in one helper used by all three sites. Severity stays low.

**PC-06 (FIN-001), upheld.** `income.py:249-251, 282-284` compute a literal 20%; `roth_conversion_and_agi_tax.py:882-886` adds it with no cap or floor; no 199A rows exist in `reference_src/`. The W3-02 rule list lacked OBBBA's minimum deduction from 2026, which every projected working year needs. Caveats recorded: the rule values are unverified against primary sources (CPA gate stays); the engine has no material-participation input; the overall cap may need to run after the LTCG/NIIT fixed point (`roth_conversion_and_agi_tax.py:901-924`). Severity and confidence are unchanged.

**Resolution of a conflicting finding update.** For FIN-003, the PC-01 re-verification set verification_status to partially_confirmed and the PC-04 re-verification set it to confirmed. The register uses partially_confirmed: the code behaviour is confirmed, but the original 'All projection years' scope is partly refuted, which matches how the register treats other findings with refuted sub-claims (for example UX-004 and UX-005). PC-04's update concerned the code evidence only.

**Unchanged by the sign-off.** No severity or confidence changed. The severity counts (0 critical, 2 high, 18 medium, 17 low) and the wave order are the same. The register was re-validated against `findings.schema.json` and the coverage matrix against `coverage.schema.json` after the edits.

### 14.3 Unresolved dissent

1. **FIN-004 priority.** The planner holds that an Illinois estate tax that may be overstated (about $269k against a possible $29k-$40k at $4.1M) and that feeds the Roth optimizer's objective is decision-affecting. In the planner's view it warrants W4-01 at P1 in addition to the Wave 2 disclosure and the earlier attorney engagement. The orchestrator keeps W4-01 at P2 with a conditional escalation. This is expected to stay unresolved until the attorney or the Illinois AG calculator settles the method: a cliff, as the docstring at `src/core.py:1321-1326` says, or a phase-in limited by federal tax.
2. **FIN-003 severity.** The planner holds low, because for typical Illinois homeowners the effect is bounded to the 2025-2029 enhanced-SALT window. The orchestrator keeps medium, because the in-window effect is 2-3x FIN-002's, it falls in the Roth-conversion years, and renters and low-property-tax households in states that exempt retirement income are still affected after 2029. W3-03 stays P1, not the planner's P2.
3. **Professional-review residual.** Every rule value and legal reading in the FIN findings (199A limits and the minimum deduction, the per-person senior-deduction phase-out, the Illinois estate method, DSUE freezing and IRC 2058, the PPRT base and PTE election, the SECURE 2.0 Roth catch-up) rests on reviewer knowledge, not primary sources fetched in this run. The planner's approval covers framing, severity and sequencing only, and cannot replace the CPA and estate-attorney gates.
4. **Unraised tax-engine items in 13.4.** The HSA catch-up indexing (the statutory catch-up is fixed), the 0.5%-of-AGI charitable floor applied in 2025, and the OBBBA 2/37 itemized limit and non-itemizer charitable deduction (not found) remain unraised. The planner considers them plausible low-severity gaps that need closed-form checks before the Wave 3 deduction-block sequence closes, so the block is not re-pinned twice. They are not in the register because the evidence was insufficient to raise them in this run.

**Governance residual.** No register record has a dedicated professional-review field. FIN-001, FIN-002, FIN-004, FIN-005, FIN-007, FIN-010 and FIN-011 meet the governance rule through their recommendation text and Section 11, not through a uniform per-record statement.

Nothing in this sign-off is legal, tax, fiduciary or benefits advice.
