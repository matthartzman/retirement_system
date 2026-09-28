# System Review — retirement_system

**Repository:** matthartzman/retirement_system — ref `main` @ `88b03d251cadc24f607ec6b4bbc03c1ae5b1704e`
**Scope:** the entire system  |  **Date:** 2026-09-25  |  **Depth:** deep
**Review type:** static, read-only, evidence-backed expert-panel review

---

## 1. Executive summary

This is a deep, read-only review of the whole retirement-planning system: the local Flask-style
server and desktop bridge, the projection/tax engine, the frontend dashboard, the financial-trends
reporter, and the documentation and test suites that support them. Five expert panels (architect,
financial planner, usability/accessibility, documentation, quality) worked in parallel from a
shared recon map and coverage matrix; every finding below was independently re-opened and
adversarially verified by its own expert before being included here, and cross-expert duplicates
were then resolved by the orchestrator.

**Overall assessment.** The system is a substantial, actively maintained local application with a
real (if partial) test and golden-master discipline. It also carries a cluster of defects that are
serious enough to change financial outcomes or expose household data, concentrated in three areas:

- **Financial correctness.** The Social Security survivor benefit (FIN-001) and the flagship
  "fill-to-bracket" Roth conversion sizing (FIN-002) are both load-bearing, high-severity arithmetic
  defects that would change the numbers a household sees and the claiming/conversion advice the
  optimizer produces. A further ten medium/low findings (FIN-003 through FIN-014) compound smaller,
  but still real, tax and reference-data errors across survivor deductions, SALT/CA bracket
  indexing, state retirement exclusions, ACA subsidies, home-sale exclusions, IRMAA lookback, RMD
  divisors, heir tax-rate assumptions, and Large-Discretionary spending's dollar basis.
- **Security in server/browser mode.** ARC-001 (high) documents that server mode — the mode every
  `.claude/launch.json` entry and the documented debugging path use — issues a CSRF token but never
  checks it, and does no Origin/Host validation. Any web page open in the same browser can trigger
  plan-data overwrites, a full household-database copy to an attacker-chosen path, or a foreign
  database swap. The default desktop mode is not exposed to this.
- **Accessibility of the core data-entry workflow.** UX-001 and UX-002 (both high) show that a
  global keyboard-capture handler breaks native Tab/Enter behavior almost everywhere outside its
  intended field-advance use, and that the plan-data and admin forms have no programmatic labels —
  together these make the primary "guided data entry" workflow largely unusable with a screen reader
  or keyboard alone.

Beyond these, the review surfaces persistent data-integrity gaps (Load Saved Plan replaces the live
database with no content validation; several primary-data writes are non-atomic; the financial
trends log can silently lose a day's snapshot), a startup/bootstrap inconsistency that skips a
schema migration when launched from the desktop shortcut, and a wide layer of documentation drift
(stale specs, dead links, an inaccurate privacy claim, an incomplete route manifest, and an
inconsistent backlog record).

**Risks.** The financial-correctness cluster is the material risk: several of these findings
directly affect the tax and Social Security figures the application recommends acting on, and they
compound (e.g. FIN-002 depends on FIN-003; FIN-005/FIN-009/FIN-013 all touch the same statutory
tables). The security finding is bounded to server/browser mode, which is not the default, but nothing
in the code stops a user from launching it. The accessibility findings make the product materially
harder or impossible to use for keyboard-only and screen-reader users today.

**Opportunities.** None of the high-severity findings require an architectural rewrite. Each has a
scoped, low-to-medium-risk fix already described by its owning expert, and the implementation waves
below sequence them to minimize repeated edits to the same files (especially `core.py` and
`tax_law_v10.json`, which four different tax findings touch).

**Financial planner verdict.** See Section 14. This report is issued for financial-planner
sign-off; qualified professional review is explicitly requested before FIN-001, FIN-002, FIN-004,
FIN-005, FIN-006, FIN-007, FIN-008, FIN-009 and FIN-013 are implemented (the full list is restated,
with its governance basis, in Section 11), because each changes a number a household would rely on,
and FIN-004/FIN-006/FIN-007/FIN-013 additionally require external verification of the underlying
statutory values or tables before any data file is edited.

**Top recommendations** (see Section 7 for the full rationale):
1. Fix the two critical-impact financial-correctness defects first and together — FIN-003 → FIN-002
   (fill-to-bracket sizing) and FIN-001 (survivor Social Security) — before any other engine change,
   because they affect every plan with a survivor period or a Roth conversion policy.
2. Close the security gap in server/browser mode (ARC-001) before recommending that mode for any
   debugging or demonstration use.
3. Fix the global keyboard-capture handler (UX-001) and add programmatic labels to the data-entry
   form (UX-002) as a pair; UX-001 also unblocks the existing modal focus-trap work (UX-004) that is
   otherwise defeated by it.
4. Route Load Saved Plan and snapshot restore through one validated, checkpoint-verified database
   helper (ARC-005, folding in QA-004) before extending the migration to more launch paths (ARC-002).
5. Refresh the tax reference dataset (FIN-004) under qualified professional review, then work
   through the SALT/RMD/IRMAA/state-exclusion chain (FIN-005, FIN-013, FIN-009, FIN-006) that shares
   the same statutory tables, so those four edits do not collide.

## 2. Scope and methodology

**Scope:** the entire system, as checked out at `matthartzman/retirement_system` ref `main` @
commit `88b03d251cadc24f607ec6b4bbc03c1ae5b1704e` (default branch `main`, working tree clean, no
open PR against this SHA). **Date:** 2026-09-25. **Depth:** deep.

**Roles and model tiers.** Five expert panels ran at `expert_reasoning` effort: architect, financial
planner, usability/accessibility, documentation, quality. Recon and the shared system map ran at
`recon`/`medium` effort. This synthesis (orchestrator) pass ran at `synthesis`/`high` effort.
Mechanical/formatting sub-steps (schema validation, fragment generation) used `mechanical`/`low`
effort. The orchestrator is not a sixth expert; it performs recon, dependency tracking, evidence
consolidation, GitHub work-context gathering, deduplication, conflict resolution, wave synthesis,
validation planning and consistency checking only.

**Phases:** (1) shared recon and system map construction (manifest.json, system-map.json,
recon-*.json — produced by an earlier stage of this run and consumed here); (2) five parallel
expert reviews, each producing a verified finding register and coverage updates for its charter
areas; (3) this synthesis pass — cross-expert deduplication, implementation-wave construction, and
report assembly.

**GitHub repository/ref/PR context.** Repository `matthartzman/retirement_system`, ref `main` @
`88b03d251cadc24f607ec6b4bbc03c1ae5b1704e`, no associated pull request (this is a whole-repository
review, not a PR review). The repository has **no GitHub issues** — `list_issues` (open and
unfiltered) and `search_issues` all returned zero results in the recon stage. Local backlog
numbering (`#332`–`#339`, `item 322`) referenced in commit messages and design specs is therefore
**not** GitHub-issue numbering; see DOC-004 and the coverage row "GitHub work-context items
reviewed" in Section 3. Relevant pull requests inspected and their dispositions are listed in
Section 3's coverage matrix and in the per-finding `github_context` fields in Section 5; a
consolidated list appears under the "GitHub work-context items reviewed" coverage row.

**Runtime-validation status.** This review is entirely static. No test, build, or application run
was performed, and no isolated disposable runtime environment was used. **Runtime behavior was not
validated during this review.**

**CI exclusion.** **CI was intentionally excluded from this review.** No finding, coverage row, or
recommendation in this report concerns CI, GitHub Actions, workflow runs, jobs, checks, logs, or
CI remediation; author-flagged test-outcome claims found in PR bodies (e.g. a reported
`test_workbook_pdf_build_snapshot.py` failure) are recorded as GitHub context only, with an explicit
`insufficient_evidence`/`out_of_scope` disposition, never as a review finding.

## 3. Coverage matrix

Every area assessed below records inspection status, evidence, the responsible expert, associated
finding IDs, relevant GitHub items with disposition, and residual uncertainty. No area is called
"healthy" merely because no finding was raised against it; where that happens the status is
`inspected_no_material_finding` and the residual uncertainty is stated explicitly. The machine-
readable version of this table is `coverage.json` (validated against `coverage.schema.json`).

| Area | Expert | Status | Finding IDs | GitHub items | Residual uncertainty |
|---|---|---|---|---|---|
| Architecture and module boundaries | architect | finding_identified | ARC-002, ARC-010 | — | planning_engines.py (6,483 lines), data_io.py and the reporting package were not re-audited for internal modularity; prior review ARC-004 (data_io coupling) was not re-verified. The multi-representation plan-data store is documented design debt in code comm... |
| Configuration and runtime settings | architect | finding_identified | ARC-002, ARC-006, ARC-010 | — | system_config.csv content was not read (possible secrets). .claude/launch.json was not reviewed beyond its server-mode entries. |
| Dependencies and compatibility layers | architect | finding_identified | ARC-007, ARC-010 | — | Whether openpyxl needs Pillow for any sheet images was not verified. No vulnerability or version audit of the pinned ranges. |
| Generated files and build artifacts | architect | finding_identified | ARC-007, ARC-009 | — | reference_data/generated_schema_coverage.csv staleness is prior ARC-003 and was not re-verified. Golden-master fixtures belong to the quality panel. |
| Imports and exports (Monarch, workbook, PDF, plan files) | architect | partially_inspected | ARC-005, ARC-008 | PR #141 | Monarch import modules (monarch_import.py, monarch_autoupdate.py, Monarch Extractor) and the YTD transaction upload were not inspected. Workbook/report-package content was not reviewed. |
| Logging and observability | architect | finding_identified | ARC-003 | — | The admin change log (security_audit.py:316-341) is still written and redacted, so some config-change history exists. Workbook build logs captured from the subprocess stdout were not traced to storage. |
| Performance and code size | architect | partially_inspected | ARC-004, ARC-007 | — | No profiling. Monte Carlo and workbook-build performance (PR #129, perf-baseline-2026-09-17.json) was not re-evaluated. Frontend size-ratchet history was not read. |
| Persistence (SQLite stores, saved plans, local state) | architect | finding_identified | ARC-005, ARC-008 | — | Concurrency between the build subprocess and server connections on the shared DB was not exercised. Schema-version handling after loading an older .rpx was only partly traced. |
| Privacy and security (secrets, auth, CSRF/CORS, PII boundary, exports) | architect | finding_identified | ARC-001, ARC-006, ARC-007 | PR #94 | Secret scanning was not performed and system_config.csv values were not read, so whether keys are actually committed is unknown. Browser Local Network Access mitigations for ARC-001 were not tested. The raw exception-message exposure (app_core.py:199-209, U... |
| Runtime transport, desktop bridge and server routes | architect | finding_identified | ARC-001, ARC-004, ARC-009, ARC-010 | PR #94 | UI-R4 (desktop drops 4xx status) was confirmed statically but judged low impact, because most 4xx bodies carry success:false. The effect of the global bridge lock on long synchronous endpoints (housing optimize, zip-screen) was not measured. Nothing was run. |
| Design and implementation document status and eligibility | documentation | finding_identified | DOC-004, DOC-005, DOC-010 | — | About 25 docs remain status-uncertain. Checkbox state is unreliable, so 0-tick plans need code-level confirmation. |
| Documentation accuracy and currency | documentation | finding_identified | DOC-001, DOC-002, DOC-003, DOC-006, DOC-007, DOC-008, DOC-009, DOC-010 | — | The archive and most of docs/superpowers were checked for status and citations only. GOLDEN_MASTER_CHANGELOG, the recovery runbook, the Roth guide and in-app help beyond the glossary were not checked for content accuracy. |
| Privacy and security (secrets, auth, CSRF/CORS, PII boundary, exports) | documentation | partially_inspected | DOC-002 | — | Only the accuracy of user-facing privacy statements was assessed. API-key logging and other outbound paths were not inspected here (see architect coverage). |
| Terminology, cognitive load and user-facing messaging | documentation | partially_inspected | DOC-007 | — | Only glossary and term coverage were assessed; wider UI copy belongs to the usability stage. |
| Tracked work items and external backlog (#332-#338, item 322) | documentation | finding_identified | DOC-004 | PR #141 | Any external tracker could not be seen. #333's status is unknown. |
| Calculation engine: deterministic projection, scenario runner and Monte Carlo | financial_planner | partially_inspected | FIN-001, FIN-002, FIN-003 | — | The vectorized MC body (_mc_vectorized_projection) was not read. run_scenario and the stress scenarios were not inspected. The regime mixture raises effective volatility (about 13.6% vs a configured 12%, hand estimate). Mortality median calibration is uncon... |
| Estate, legacy and beneficiary workflow | financial_planner | finding_identified | FIN-012 | — | Federal estate tax assumes portability; DSUE is not frozen at first death. State estate calculations were not verified numerically. |
| Financial logic: federal/state tax, IRMAA, RMD, withdrawal sequencing, Roth conversion | financial_planner | finding_identified | FIN-002, FIN-003, FIN-005, FIN-006, FIN-009, FIN-013, FIN-014 | — | The eight withdrawal_cascade_* modules, the NIIT/LTCG fixed point and optimize_roth_conversion_strategy scoring were not read in full. QCD/QLAC limits and AMT figures look plausible but were not checked against primary sources. |
| Healthcare, Medicare and long-term care workflow | financial_planner | partially_inspected | FIN-007, FIN-009 | — | LTC insurance and hybrid LTC modelling were not inspected. The Part B base premium is indexed rather than set to the published 2026 value (see FIN-004). |
| Housing and relocation planning | financial_planner | partially_inspected | FIN-008, FIN-006, FIN-005 | — | The optimizer scoring, ZIP screen price estimation and state housing-cost estimates were not inspected. |
| Reference data currency (tax law, IRMAA, capital market, mortality tables) | financial_planner | finding_identified | FIN-004, FIN-005, FIN-013 | — | Correct 2026 values were not fetched from primary sources in this run. capital_market_assumptions.csv and asset_correlations.csv were not inspected. State tax rows beyond CO and NY were not verified. |
| Retirement income and Social Security/benefits claiming workflow | financial_planner | finding_identified | FIN-001 | — | The retirement earnings test is not modelled. The claim-age sweep's scoring and feasibility gate were read only from the report note. |
| Spending, budget tracking and trends reporting | financial_planner | finding_identified | FIN-010, FIN-011 | PR #141 | The spending_adjustments compounding, YTD tracking blend and Monarch import categorization were not inspected. |
| Survivor and spousal-death scenarios | financial_planner | finding_identified | FIN-001, FIN-003, FIN-008, FIN-009 | — | Spousal rollover account mapping was only skimmed. Remarriage and divorce/QDRO scenarios were not inspected. |
| Tax planning workflow | financial_planner | finding_identified | FIN-002, FIN-003, FIN-005, FIN-012, FIN-014 | — | Itemized deductions use first-pass AGI (documented one-year approximation). The TLH and gain-harvest modules were not inspected. |
| GitHub work-context items reviewed (issues, PRs, backlog) | orchestrator | partially_inspected | — | Backlog #332-#339, #333 — insufficient_evidence: No GitHub issues; #333 is unreferenced (DOC-004).; PR #117 Priority 4b crash when Priority 3 never ran — insufficient_evidence: withdrawal_cascade_i... | Only 8 of 29+ merged/closed PRs (#134-#141) had full pull_request_read(get) detail fetched in this run; older PRs are recorded from list/search metadata only (title, branch, base SHA, merged_at), with no body text. list_pull_requests(state=closed) was cappe... |
| Data integrity (plan config, household relationships, migrations) | quality | finding_identified | QA-001, QA-002, QA-004, QA-005 | PR #141 (confirmed); PR #137 (contextual_only) | The SQLite schema init shared by local_store and config_backend was not traced. The WAL-loss scenario in QA-004 is inferred from code and depends on concurrent connections at load time. |
| Dates, years and time handling | quality | finding_identified | QA-001, QA-003, QA-005 | PR #141; PR #141 (confirmed) | The Social Security claim-month parsing in _month_year_parts was read only in part. Year-boundary behavior of the YTD blend was not re-derived. |
| Error handling | quality | partially_inspected | QA-004 | — | Frontend catch blocks and the server catch-all belong primarily to the usability and architect stages and were not re-inspected here. |
| Input validation | quality | finding_identified | QA-001 | — | Server route payload validation beyond config-rows, adjustments and load-file paths was not reviewed route by route. Monarch and holdings import validation was not inspected. |
| Numeric precision and rounding | quality | inspected_no_material_finding | — | — | No finding does not mean rounding is correct; tax-bracket, IRMAA and RMD rounding belong to the financial-planner review. Float accumulation over long horizons was not measured, because this was a static review. |
| Testing and golden masters | quality | finding_identified | QA-002, QA-003, QA-006 | PR #135; PR #139; PR #135 (insufficient_evidence); PR #137 (contextual_only); PR #139 (contextual_only) | About 447 Python test files and 62 frontend test files were sampled, not read in full. No test was run and no pass/fail status is claimed. |
| Accessibility (keyboard, focus, semantics, contrast, screen reader) | usability_accessibility | finding_identified | UX-001, UX-002, UX-004, UX-005, UX-010 | — | No screen reader, keyboard or zoom behaviour was checked at runtime. Contrast was computed only for core palette tokens; chart colours, housing/allocation panels and print styles were not checked. Touch targets and the strategy-tabs tablist arrow-key suppor... |
| Error handling | usability_accessibility | partially_inspected | UX-003, UX-009 | — | Owned primarily by the quality expert; only the user-facing side was inspected here. Desktop-bridge status fidelity was left to the architect. |
| Terminology, cognitive load and user-facing messaging | usability_accessibility | finding_identified | UX-003, UX-006, UX-007 | — | Wording was sampled, not reviewed across the roughly 36k lines of UI strings. Plain-language quality of the workbook/PDF reports belongs to the documentation expert. |
| UI structure, navigation and user workflows | usability_accessibility | finding_identified | UX-006, UX-008, UX-009 | PR #139; PR #139 (contextual_only); PR #138 (contextual_only); PR #136 (contextual_only); PR #123 (contextual_only) | The renderMain decorator chain was checked only for the plan-gate branch. Feature renderers (housing, allocation, checklist, reports_ui, planning_workbench beyond the matrix, spending_dashboard) were not read in full. |

## 4. System health assessment

**Architecture.** The system cleanly separates a stdlib-WSGI server, a PyWebView desktop bridge, and
a large calculation engine, but three different entry points (`main.py`, `START_DESKTOP.py`,
`DesktopApi`) each set up their own environment defaults and only one of them runs the startup
plan-data migration (ARC-002) — a real reproducibility gap, not yet a data-loss one. The transport
layer still carries dead SaaS-era auth scaffolding next to the real (largely absent) protections
(ARC-010), and the documented route manifest and "cannot drift" architecture diagram have both
drifted substantially behind the registered routes (ARC-009). The PyInstaller build bundles the
developer's live, untracked `input/` folder and ~51 MB of unused libraries (ARC-007) — a build-
hygiene and privacy issue in the one channel meant for sharing the app as a standalone artifact.

**Usability / accessibility.** This is the weakest health-assessment category in this review. Two
high-severity findings — a global keyboard-capture handler that swallows Enter/Tab almost
everywhere outside its intended use (UX-001), and plan-data/admin fields with no programmatic label,
required state or description (UX-002) — together make the core "guided data entry" workflow
difficult or impossible to complete with a keyboard alone or a screen reader. A further seven
medium/low findings compound this: unannounced, auto-hiding error toasts carrying raw exception
text (UX-003); unmanaged focus in the static exit/chart modals (UX-004); disabled page zoom with
dense 9–11px text and no in-app text-size control (UX-005); stale post-navigation-restructure jump
targets (UX-006, folding in the same defect independently spotted from the architect's build-
fallback angle at ARC-004/UX-009); undefined headline decision-metric acronyms on the compare/decide
screen (UX-007, absorbing DOC-007); a plan-independent-step render mismatch (UX-008); and missing
`aria-current`/`aria-pressed` state (UX-010). None of these require a redesign; each is a scoped
markup/handler-scoping fix.

**Documentation.** Documentation for this system is out of date in ways that are more than cosmetic:
the annual tax-maintenance runbook points maintainers at a file the tax engine does not read and
omits the dated-row rule the engine actually depends on (DOC-001); the end-user README makes a
flatly false "nothing is sent over the internet" privacy claim against a LIVE-mode default that
contacts four external quote providers (DOC-002); the two "as it behaves today" specs predate the
housing optimizer, Next Housing Move, Plan Features and the one-time Large Discretionary model
(DOC-003); and the only written record of a multi-week backlog (`#332`–`#339`) shows the wrong
progress against what `git log` actually merged (DOC-004). A further six lower-severity findings
cover dead links (including one in the auto-loaded project `CLAUDE.md`), an out-of-date API contract
listing a route that does not exist, and stale ancillary READMEs.

**Quality / testing.** Test and golden-master discipline exists and is used deliberately (the
`regen_golden_master.py measure`-first workflow, frozen fixtures, provenance markers), but it has
real gaps: a dangerous coincidence where the frozen fixture's household values equal the CSV
parser's hard-coded fallbacks means a broken field-read would go undetected (QA-002); household date
parsing uses three different, disagreeing century rules with no format validation and silent
literal fallbacks for missing required fields (QA-001); the production workbook build's YTD blend
silently bypasses the project's own frozen-date determinism seam (QA-003); Load Saved Plan replaces
the live database with no content validation (QA-004, folded into ARC-005); and three High-severity
test gaps confirmed in the prior review are still open at this commit, unchanged since (QA-006).

**Financial correctness.** This is the highest-consequence category. Beyond the two high-severity
findings in the executive summary, the reference tax dataset is pre-OBBBA and has no 2026 values
despite an in-app dashboard marking it current (FIN-004); the SALT cap and California brackets are
encoded relative to the calendar run-date rather than to statute, so the same plan gives different
answers depending on what day it is run (FIN-005); IRMAA is assessed on AGI rather than MAGI, using
the wrong lookback-year filing status across a death (FIN-009); NY/CO retirement-income exclusions
are applied once per household instead of once per qualifying person (FIN-006); a survivor's home
sale loses the statutory two-year, $500k exclusion and gets no basis step-up at the first death
(FIN-008); the RMD Uniform Lifetime table has a transcription error and unverified extrapolated
rows past age 115 (FIN-013); heir tax-rate defaults assume the inherited IRA is the heir's only
income (FIN-012); Large Discretionary spending amounts are nominal while the rest of the budget is
in plan-start dollars (FIN-011); and one LTCG guardrail still uses a superseded local bracket-
indexing convention (FIN-014). Every one of these findings states its jurisdiction, rule year, and
whether qualified professional review is required, per financial-domain-governance.md.

**Data integrity.** Load Saved Plan and snapshot restore apply two different, non-overlapping
safeguard sets and neither validates the file's content before replacing the live database
(ARC-005/QA-004); several primary-user-data writes (holdings, liabilities, HSA schedule, the plan-
load materialization, the trends log, the secret store) bypass the project's own `atomic_write`
helper (ARC-008); and the financial trends log keys its daily snapshot on the last transaction date
rather than the run date, so a day with no new transactions silently overwrites the prior day's
holdings/net-worth history (QA-005/FIN-010, with an open, unmerged PR #141 that fixes only the key,
not the underlying non-atomic-write and corrupt-line-loss issues).

**Security / privacy.** Bounded to server/browser mode (not the default desktop mode): no request
authentication, no CSRF enforcement despite a token being issued, and no Origin/Host validation
(ARC-001) — combined with `plan_file_service.py`'s unrestricted save-as/load-file paths, this is a
full local-data read/write/exfiltration path whenever that mode is running. Separately, provider API
keys for two market-data providers are designed to be written into a git-tracked CSV rather than the
existing encrypted secret store (ARC-006, partially confirmed — the `openai_api_key` field has
already been migrated off this pattern). No secret scanning was run against tracked files in this
review (see Section 12).

**Performance.** Only lightly assessed (`partially_inspected`): no profiling was performed. The
architect noted several minor per-request/per-call re-parsing patterns (`system_config.csv`,
SQLite `PRAGMA`/`CREATE TABLE` statements) judged low-impact, and confirmed the PyInstaller bundle
carries roughly 51 MB (about 18%) of unused libraries (ARC-007). No finding in this category rises
above low/medium severity.


## 5. Material findings

All findings whose `verification_status` is `confirmed` or `partially_confirmed` (44 of the 50 register entries — the other 6 are 4 cross-expert duplicates and 2 `insufficient_evidence` items, both dispositioned in Section 13). Sorted by severity (high, then medium, then low); within a severity tier, by finding ID. Every required field from findings-schema.md is included per finding. The machine-readable version of this section is `findings.json` (validated against `findings.schema.json`).

### ARC-001 — Server mode will act on requests from any web page: the CSRF token is never checked, there is no auth and no Origin/Host check, and routes accept bodies with no Content-Type or text/plain

- **Expert:** architect  |  **Category:** security  |  **Severity:** high  |  **Confidence:** high
- **Inspection status:** finding_identified  |  **Verification status:** confirmed
- **Affected workflows:** Server/browser mode, Plan Data editing, Save As / Load Saved Plan, System Configuration reference-file edits

**Evidence:**

- `src/server/security_audit.py:126-131, 384-392` — `_authorized_and_identity / _current_user / _csrf_token_for_current_request` — Every request is authorized as the 'advisor' role. A CSRF token is derived here but never compared with anything.
- `frontend/js/api_client.js:18-19` — `X-CSRF-Token header` — The client sends X-CSRF-Token on non-GET requests. A grep of src/ finds no code that reads or validates this header.
- `src/server/app_core.py:1933-1969` — `_security_gate` — The gate does no auth rejection and no Origin, Referer or Host validation. The wildcard CORS header was removed (SEC-1), which blocks cross-origin reads but not cross-origin writes.
- `src/http_runtime/wsgi_facade.py:135-148` — `LocalRequest.get_json` — A body is parsed as JSON when the Content-Type header is absent (`and ctype` short-circuits). A cross-site fetch whose body is a Blob with no type sends no Content-Type, so it counts as a CORS 'simple' request and needs no preflight.
- `src/server/workbook_routes.py:656-670, 685-692` — `save_plan_data_file / save_holdings` — When no JSON is present, the handler falls back to request.get_data(as_text=True). A plain HTML form posted with enctype=text/plain can therefore overwrite plan-data CSVs and holdings.
- `src/server/admin_routes.py:201-217` — `admin_save_reference_file` — Reference files (tax/CMA data) can be overwritten from a raw text body in the same way.
- `src/server/plan_routes.py:1234-1263` — `plan_save_as / plan_load_file` — No _require check. The path comes from the request body.
- `src/server_services/plan_file_service.py:86-127` — `PlanFileService.save_as / load_file` — Copies the whole household SQLite DB to any caller-supplied path, including UNC paths, or replaces the DB with any caller-supplied file.
- `main.py:10-11, 94-117` — `_run_server` — Server mode binds 127.0.0.1:5050 and opens a normal browser. Desktop mode, the default, opens no socket.
- `src/http_runtime/server.py:14-19` — `_Handler._handle` — The Host header is passed through unchecked, so DNS rebinding is possible.

**Observed behavior:** When the app runs with --mode server (the documented debugging/browser mode and the mode used by every .claude/launch.json entry), any page open in the user's browser can send state-changing POSTs to 127.0.0.1:5050. Four routes are open to this: plan-data CSV writes, the reference-file/tax-data overwrite, /api/plan/save-as (copies the full financial DB to an attacker-chosen path, e.g. a UNC/WebDAV share) and /api/plan/load-file (swaps in a foreign DB). A CSRF token is issued and sent, which makes the defense look present, but nothing enforces it. Because Host is not validated, DNS rebinding would also allow reads.

**Impact:** Household financial data can be altered, corrupted or exfiltrated, and the tax reference data corrupted, whenever server mode is running. The default desktop mode is not exposed. Browser local-network-access protections may reduce exploitability but were not verified.

**Root cause:** The move from SaaS to local-only removed authentication (SEC-1 and review 4.5) on the assumption that local means trusted. The double-submit CSRF scheme was kept only on the issuing side.

**Options:**

- Enforce the issued X-CSRF-Token in _security_gate for every non-GET, non-public request in server mode, and require Content-Type: application/json on JSON routes. The desktop bridge is exempt because it never crosses HTTP.
- Add Origin/Referer and Host allow-listing (127.0.0.1/localhost:port) in _security_gate, plus a per-launch random token injected into the served index.html.
- Remove server mode from user-facing launchers and document it as dev-only, and still apply option 1 or 2 for defense in depth.

**Recommendation:** Option 1 plus a Host allow-list from option 2. Both are small changes in _security_gate and wsgi_facade.get_json, and they remove both the CSRF and the DNS-rebinding vectors without affecting desktop mode.

**Implementation considerations:** The desktop bridge (desktop_api.request) goes through test_client and sets window.__pywebview_no_csrf__, so the check must key on the transport. The frontend already sends the token from both api_client.js and admin.js. The get_data fallbacks for the text/plain routes (holdings, liabilities, hsa-schedule) need either the header check or JSON-only bodies.

**Risk of change:** Low to medium. Any automation script that POSTs without the token would break. Tests that use test_client need a helper for the header.

**Verification method:** Static: confirm _security_gate rejects a non-GET that lacks a valid token or has a foreign Origin/Host. Test: a POST to /api/plan-data/client_data.csv with Content-Type text/plain and no token returns 403, and a POST with no Content-Type and no token returns 403.

**Linked implementation items:** WI-101

**Verification rationale (adversarial pass):** Opened all primary evidence. security_audit.py:126-127 _authorized_and_identity always returns (True, None); app_core.py _security_gate (~1930-1960) does no auth/Origin/Referer/Host check and only redirects for force_https. wsgi_facade.py get_json (LocalRequest.get_json) only raises when ctype is non-empty and lacks 'json' — an absent Content-Type falls through to json.loads on the raw body, confirming the CORS-simple-request bypass claim. workbook_routes.py:656-670 save_plan_data_file and admin_routes.py:201-217 admin_save_reference_file both fall back to request.get_data(as_text=True) when no JSON body is present. plan_routes.py plan_save_as/plan_load_file (lines ~1225-1263) call no _require() at all, and plan_file_service.py save_as/load_file (lines 86-127) do shutil.copy2 to/from any caller-supplied path with no validation — this is a genuine full read/write compromise path when server mode is running, gated only by localhost binding. api_client.js does send X-CSRF-Token (line 18-19 region) and nothing in src/ compares it, consistent with the claim. Severity 'high' (not lower) is well supported by the DB-overwrite/exfiltration reach; confidence could arguably be raised to high given how directly verifiable each piece is, but medium is a defensible, non-overclaiming choice. No counterevidence found; not a duplicate of anything else in the batch (ARC-010 documents the same dead auth scaffolding but as a maintainability/dead-code angle, and explicitly depends on ARC-001 rather than duplicating it).


---

### FIN-001 — Social Security survivor benefit is zero when the worker dies before claiming, never gets a COLA after the death, and has no survivor-age gate

- **Expert:** financial_planner  |  **Category:** financial-correctness  |  **Severity:** high  |  **Confidence:** high
- **Inspection status:** finding_identified  |  **Verification status:** confirmed
- **Jurisdiction:** US federal (Social Security Act §202(e)/(f); 20 CFR 404.335-404.339; §215(i) COLA)  |  **Rule year:** Current law as of 2026
- **Assumptions:** Hard-coded engine logic. Authority for the rule: authoritative SSA program rules, cited from reviewer domain knowledge and not opened in this run. This is an arithmetic and rule-application defect, not a suitability question. Qualified human review is recommended before the corrected output is used for claiming advice.
- **Affected workflows:** Social Security claim-age recommendation (Sheet 10 sweep), Survivor and spousal-death scenarios, Monte Carlo survivor buckets and success probability, Early-death stress scenarios, Deterministic projection after the first death

**Evidence:**

- `src/projection_stages/income.py:391-411` — `survivor benefit block` — h_ss_at_death is set to 0 when h_death_yr < h_ss_yr (and the same for w). It is built with ss_ratio(c['h_death_yr'], h_ss_yr), so the COLA factor stops at the death year. The only gate is year > death_yr, with no check that the survivor is 60 or older. ss_surv is applied as a flat percentage.
- `src/projection_stages/deterministic_engine.py:454-455` — `_ss_ratio` — The ratio is the COLA index from claim_year to the year passed in. Passing the death year therefore holds the survivor benefit at its death-year nominal level for every later year.
- `src/data_io.py:795` — `c['ss_surv']` — The survivor percentage is one flat input (default 100%). It is not reduced when the survivor starts benefits before survivor FRA.
- `src/planning_engines.py:4774-4790` — `_mc_survivor_bucket_flows` — The vectorized Monte Carlo reruns project() for a first death in every plan year. Early-death paths therefore inherit the zero survivor benefit, and all survivor paths inherit the frozen benefit.
- `src/reporting/sheets_strategy.py:641` — `claim-age sweep note` — Claim-age pairs are scored partly on survivor-period SS income, so these survivor-benefit errors feed directly into the recommended claim ages.

**Observed behavior:** After the first death, the survivor gets max(own benefit, deceased's benefit at the death year × ss_surv). The deceased's part is (a) 0 if they died before their planned claim year, (b) never increased by COLA after the death year, and (c) paid whatever the survivor's age, including under 60, with no early-survivor reduction.

**Impact:** Survivor income is understated in every year after a first death, and the gap grows with the length of widowhood. At a 2.5% COLA the gap is about 22% after 8 years and about 28% after 10. If the higher earner plans to claim at 70 and dies first, the model pays no survivor benefit on that record at all. In the Monte Carlo survivor buckets and the claim-age sweep this makes delaying the higher earner's claim look less valuable, which pushes the recommendation toward claiming earlier. Case (c) overstates income for young survivors.

**Root cause:** The survivor benefit is taken from a snapshot at the death year. It is not rebuilt each year from the deceased's record (PIA with DRCs earned up to death, the RIB-LIM floor) and indexed by COLA through the current year.

**Options:**

- No credible alternative; this is a correctness defect.

**Recommendation:** Compute the survivor benefit each year from the deceased's record. If the worker claimed, use their benefit, with the widow(er) limit of the greater of the worker's benefit and 82.5% of PIA. If the worker died before claiming, use PIA plus any DRCs earned up to death. Index the result with ss_ratio(year, ...) through the current year. Start it no earlier than survivor age 60 and apply the survivor early-claim reduction. Apply the same code path to the scalar and vectorized Monte Carlo engines through project().

**Implementation considerations:** This changes golden-master outputs for any fixture with a survivor period. Following CLAUDE.md, run tools/regen_golden_master.py measure first and check one survivor-year delta by hand before regenerating. The Sheet 10 claim-age cache and the survivor-bucket memo key must change with the new logic.

**Risk of change:** Medium: survivor-year cash flows, taxes (SS taxable amount), MC success rates and the claim-age ranking will all move.

**Verification method:** Build three synthetic MFJ plans: (1) h claims at 70 and dies at 66, so survivor SS should be greater than 0 and based on PIA; (2) h dies at 85 after claiming, so the survivor benefit in year t should equal the death-year benefit × (1+cola)^(t−death_yr); (3) the survivor is 55 at h's death, so no survivor benefit before 60. Hand-check each against SSA rules.

**Linked implementation items:** WI-103

**Verification rationale (adversarial pass):** Opened src/projection_stages/income.py:391-411 myself. Confirmed exactly as described: h_ss_at_death/w_ss_at_death is set to 0 via the `... if c['h_death_yr'] >= h_ss_yr else 0` ternary when the worker dies before their planned claim year; ss_ratio(c['h_death_yr'], h_ss_yr) freezes the COLA index at the death year (confirmed deterministic_engine.py:454 _ss_ratio is the COLA index function, matching evidence); and the only gate is `year > c['h_death_yr']`/`year > c['w_death_yr']` with no age-60 check anywhere in this block. ss_surv (data_io.py:795, default 100%) is a flat scalar applied without any early-claim reduction. Severity/confidence (high/high) are well calibrated given this affects every survivor-period year and the claim-age sweep depends on it. No mitigating code found nearby. Jurisdiction/rule_year are stated. No duplicate in this batch. Not refuted.


---

### FIN-002 — Fill-to-bracket Roth conversions fill AGI, not taxable income, to the bracket top, leaving the standard deduction's worth of room unused

- **Expert:** financial_planner  |  **Category:** financial-correctness  |  **Severity:** high  |  **Confidence:** high
- **Inspection status:** finding_identified  |  **Verification status:** confirmed
- **Jurisdiction:** US federal (IRC §1 brackets, §63 deduction)  |  **Rule year:** 2025 bracket table, indexed forward
- **Assumptions:** Hard-coded sizing logic. Authority: statutory bracket definition (authoritative). This is an arithmetic error against the stated policy. Suitability of the conversion amount still needs planner judgement.
- **Affected workflows:** Roth conversion planning (fill_to_bracket and optimizer candidates built on it), Tax planning workflow, HSA joint headroom (hsa_schedule.joint_headroom_used reads bracket_room)

**Evidence:**

- `src/planning_engines.py:2118-2155` — `plan_roth_conversion` — top_target is the upper bound of the target bracket in the inflated ordinary-bracket table, which is a taxable-income threshold. bracket_room = max(0, top_target − pre_agi), where pre_agi is income before any deduction.
- `src/planning_engines.py:2157-2166` — `plan_roth_conversion` — The standard deduction and senior bonus are computed here but only feed base_tax_est. They never widen bracket_room.
- `src/planning_engines.py:2272-2274` — `fill_to_bracket branch` — cap_bracket = bracket_room × roth_headroom_usage_pct (0.95), labelled '<rate>% bracket'.
- `tests/test_roth_conversion_guardrails_past_rmd_age_unit.py:105-110` — `test` — The test pins the current semantics: bracket_room moves one-for-one with pre-deduction income.
- `tests/fixtures/sample_plan_frozen/client_policy.csv:170` — `roth_conversion_target_bracket_base_year` — The input's help text promises to 'Fill to top of this bracket'.

**Observed behavior:** For a 65+ MFJ couple in 2026, conversions stop when AGI reaches the bracket top. Taxable income then sits about $34k (standard deduction plus age add-ons) to about $46k (with the OBBBA senior bonus) below the top of the bracket the policy names, and the 5% haircut is applied on top of that.

**Impact:** Conversions are materially smaller than the named policy implies, roughly $30-45k per year less over the conversion window. For a 12%-bracket target, nearly half the bracket is left unused. The binding-limit labels ('22% bracket') misreport where the household actually lands. The optimize policies may partly offset this by choosing a higher target rate, but the fill_to_bracket family itself is mis-sized.

**Root cause:** The code compares a taxable-income bracket threshold with AGI without adding back the deductions that sit between them.

**Options:**

- No credible alternative; this is a correctness defect.

**Recommendation:** Compute bracket_room as (top_target + deduction) − pre_agi, where deduction is the larger of the standard deduction (including senior bonus) and the estimated itemized deductions. Keep the IRMAA, ACA and NIIT caps on a MAGI basis. Update the pinned tests and relabel the result diagnostics.

**Dependencies:** FIN-003

**Implementation considerations:** The standard deduction used here should share the fix from FIN-003 (survivor age count). Re-measure golden masters before regenerating. hsa_schedule.joint_headroom_used consumes bracket_room and needs re-verification.

**Risk of change:** Medium-high: changes conversion amounts, lifetime tax, IRMAA exposure and terminal Roth balances in every plan that converts.

**Verification method:** Unit test: MFJ, both 70, no other income, 22% target. Expected taxable income after the conversion ≈ 0.95 × the 22% bracket top for that year, and the conversion ≈ that plus the standard deduction and senior bonus. Hand-check one frozen-fixture year.

**Linked implementation items:** WI-105

**Verification rationale (adversarial pass):** Opened src/planning_engines.py:2118-2166 myself. bracket_room = max(0.0, top_target - pre_agi) exactly as claimed (line ~2150), where pre_agi is pre-deduction income and top_target is a taxable-income bracket threshold. std (standard deduction + senior bonus) is computed at lines 2157-2163 but only feeds base_tax_est, confirmed never added into bracket_room or top_target. This is a real unit mismatch (comparing AGI against a taxable-income threshold) that leaves roughly a standard-deduction's worth of headroom unused. Severity/confidence well calibrated; this is a load-bearing sizing bug for the flagship fill_to_bracket policy. Not a duplicate of FIN-003 though related (both touch n65/deduction sizing) — correctly listed as a dependency rather than duplicate.


---

### QA-006 — Three high-severity test gaps from the previous review are still open at this commit (prior QA-002, QA-003, QA-006)

- **Expert:** quality  |  **Category:** test-coverage  |  **Severity:** high  |  **Confidence:** high
- **Inspection status:** finding_identified  |  **Verification status:** confirmed
- **Affected workflows:** Monte Carlo survivor economics, Golden-master maintenance, Spending budget recovery

**Evidence:**

- `tests/test_scalar_vectorized_survivor_reconciliation.py:47` — `ScalarVectorizedSurvivorReconciliationTests` — Still wrapped in @unittest.skipUnless(RUN_SLOW_MC_RECONCILIATION). git grep finds no other tracked file that sets this variable, and the test has no pytest marker. It is skipped unless a developer sets the variable by hand.
- `tests/test_golden_master_pin_provenance.py:62-70` — `PIN_FILE / PIN_PROVENANCE_MARKER_RE` — Provenance is still enforced only for the frozen-plan pin file. The synthetic and full-row snapshot fixtures have no test-level provenance binding.
- `src/spending_tracker.py:1072` — `recover_spending_budget_from_seed` — git grep over tests/ finds no reference to this symbol, so the data-recovery function still has no direct tests.
- `documentation/archive/reports/SYSTEM_REVIEW_2026-09-25.md:257-276` — `prior QA-002/003/006` — These were recorded and confirmed as High in the previous review. HEAD 88b03d2 differs from that review's ref (92a5cd3) only in .gitattributes and the report itself.

**Observed behavior:** None of the three previously confirmed High gaps has been remediated. git diff --stat 92a5cd3..HEAD shows only .gitattributes and the report changed.

**Impact:** No regression protection for scalar/vectorized survivor economics. Two of the three pinned-output mechanisms can be hand-edited without the suite noticing. The one function meant to recover corrupted budgets is unprotected.

**Root cause:** Remediation waves W1-C, W2-A and W2-B from the prior report have not been executed yet.

**Options:**

- Carry the prior report's W1-C/W2-A/W2-B work items forward unchanged.
- Fold them into the QA-002/QA-003 work in this review, since they touch the same golden-master and test infrastructure.

**Recommendation:** Carry them forward as-is and schedule them before the next engine-touching change. This is a duplicate of prior findings, restated so the new plan does not drop them.

**Implementation considerations:** For the survivor test, prefer a slow or nightly pytest marker with a reduced n_sims over an environment variable that nothing sets.

**Risk of change:** Low (test-only).

**Verification method:** Re-ran the prior review's greps at HEAD 88b03d2: RUN_SLOW_MC_RECONCILIATION appears only in the test file, recover_spending_budget_from_seed is absent from tests/, and the provenance test hard-codes a single PIN_FILE.

**Linked implementation items:** WI-404

**Verification rationale (adversarial pass):** Verified tests/test_scalar_vectorized_survivor_reconciliation.py:47 is still gated by @unittest.skipUnless(...RUN_SLOW_MC_RECONCILIATION...) with no pytest marker, and grep found no other tracked file setting that env var, meaning it is effectively always skipped in normal runs. Verified test_golden_master_pin_provenance.py:62-70 still binds PIN_PROVENANCE_MARKER_RE checking to a single PIN_FILE (the frozen-plan regression test), with no equivalent provenance binding located for the synthetic/full-row snapshot fixtures. Verified via grep that recover_spending_budget_from_seed has zero references anywhere under tests/. Verified git diff --stat 92a5cd3..88b03d2 touches only .gitattributes and the archived report file, confirming no remediation work landed between the prior review's ref and this review's HEAD. This is a legitimate, well-evidenced restatement/carry-forward of unresolved prior findings, correctly flagged as a duplicate-of-prior-report item rather than a new defect, and the High severity carried from the original review is not disputed by anything found here.


---

### UX-001 — A global Enter/Tab capture handler stops Enter from activating buttons and sends Tab to the wrong place, including out of modal dialogs

- **Expert:** usability_accessibility  |  **Category:** accessibility-keyboard  |  **Severity:** high  |  **Confidence:** high
- **Inspection status:** finding_identified  |  **Verification status:** confirmed
- **Affected workflows:** WF-1 open/create plan, WF-2 guided data entry, WF-5 YTD import confirm, WF-7 housing apply, WF-8 strategy/optimizer apply, WF-11 exit with unsaved changes, All in-app confirm dialogs

**Evidence:**

- `frontend/js/dashboard.js:6781-6808` — `moveToNextEntry / document.addEventListener('keydown', moveToNextEntry, true)` — The listener is registered on document in the capture phase. For any input, select, button or textarea (except .helpbtn, .wf-col-width and Enter inside a textarea), it calls preventDefault() on Enter and on unshifted Tab. It then moves focus to focusableEntries()[indexOf(el)+1], and when the element is not in that list, indexOf returns -1, i is set to 0 and focus goes to f[1].
- `frontend/js/navigation.js:411-413` — `focusableEntries` — The list covers only .field input/select, .lot-table and .matrix-table inputs, .pane-actions/.nav-actions buttons and header buttons. It leaves out left-nav .stepbtn buttons, the #combinedSearch box, the search-scope buttons, textareas, buttons in the page body (source-jump, optimizer, tab and table buttons), and every modal button.
- `frontend/index.html:73,77` — `header / #sideNav` — Header buttons come first in DOM order: navToggleBtn (hidden when wide), Back and Forward (disabled at first), Save Changes, Download Workbook, Exit. So f[1] is normally a header button. The sidebar step list and search come after the header.
- `frontend/js/dashboard_decomp_row_model.js:3120-3149` — `showInAppConfirm onKey / _trapTabWithinModal` — The dialog's Tab trap runs in the bubble phase and acts only on the first or last element. The capture-phase handler has already prevented the default and queued a focus move to f[1], which lies outside the dialog. Enter on Confirm or Cancel is also prevented.
- `tests/frontend/inapp_modal_accessibility_and_listener_leak.test.mjs:1-16` — `header comment` — The modal focus-trap fix (UX-105 from the 2026-09-07 review) is tested alone against a stub DOM, without the global capture handler, so the two are never tested together. A grep of tests/ found no test that exercises moveToNextEntry.

**Observed behavior:** By static reading: pressing Enter on a focused button does nothing, because keydown preventDefault stops the synthesized click; only Space works. Pressing Tab on any control outside the curated list (step buttons, the nav search box, buttons in the page body, textareas, confirm-dialog buttons) jumps to the second header button instead of the next control. Forward Tab therefore cannot move through the left navigation or past a button in the page body, and a user in a confirm dialog can Tab out of it into the page behind.

**Impact:** Keyboard-only and screen-reader users cannot reliably reach or activate large parts of the planner. That includes step navigation, apply and jump buttons, and confirm dialogs, which the 2026-09-07 remediation made accessible in isolation. This is a WCAG 2.1.1 (Keyboard), 2.4.3 (Focus Order) and 2.1.2-adjacent problem that affects every workflow.

**Root cause:** A data-entry convenience (Enter or Tab advances to the next field) was put on document at capture level for all buttons and textareas, not only for the field inputs it was meant for. Its fallback for elements outside the list jumps to f[1] instead of leaving native behaviour alone.

**Options:**

- Scope the handler: act only when e.target is one of focusableEntries() (or matches .field input/select), never on buttons or textareas; when the target is not in the list, return without preventDefault.
- Remove the Tab override completely and keep only Enter-to-advance on text inputs, relying on native Tab order.
- Keep the current behaviour behind an opt-in 'Enter moves to next field' preference, off by default.

**Recommendation:** Option 1, plus an early return when the event target is inside [role=dialog] or when e.defaultPrevented is already set. This keeps the field-advance behaviour users depend on and restores native button activation and Tab order everywhere else.

**Implementation considerations:** The .wf-col-width exemption and tests/e2e/workbook-format-tab-focus.spec.js depend on this handler's current shape. Add an e2e keyboard spec: Tab from a step button, Enter on a body button, and Tab inside showInAppConfirm and exitModal. dashboard.js is 7k+ lines, so edit by grep offset.

**Risk of change:** Low to moderate. Users who press Enter to leave a field keep that behaviour, and buttons regain their standard behaviour. Any flow that relied on Enter being swallowed on a button would now activate that button.

**Verification method:** Playwright: focus a .stepbtn and press Tab, then assert focus is on the next .stepbtn. Focus a body button and press Enter, then assert its handler ran. Open showInAppConfirm, press Tab twice, and assert document.activeElement is still inside the overlay.

**Linked implementation items:** WI-501

**Verification rationale (adversarial pass):** Opened frontend/js/dashboard.js:6781-6808: moveToNextEntry matches input,select,button,textarea (excluding .helpbtn and .wf-col-width, and Enter-in-textarea), calls e.preventDefault() on Enter or unshifted Tab, and on fallback sets i=0 when indexOf(el)<0, moving focus to f[Math.min(len-1,1)] = f[1]. Confirmed listener is document-level capture (`addEventListener("keydown", moveToNextEntry, true)`). Confirmed navigation.js:411-413 focusableEntries() only covers .field/.lot-table/.matrix-table inputs, .pane-actions/.nav-actions buttons and header buttons — excludes .stepbtn, search box, body buttons, modal buttons, textareas — matching the claim. Confirmed showInAppConfirm's Tab trap (dashboard_decomp_row_model.js:3120-3149) registers its keydown listener via plain document.addEventListener("keydown", onKey) (bubble phase, no capture flag), so the capture-phase moveToNextEntry runs first and already prevents default / schedules a focus move outside the dialog before the bubble-phase trap fires — corroborating the modal-Tab-escape claim. Severity/scope as described is well supported by the code read.


---

### UX-002 — Plan-data fields and admin settings have no programmatic label, required state or description

- **Expert:** usability_accessibility  |  **Category:** accessibility-semantics  |  **Severity:** high  |  **Confidence:** high
- **Inspection status:** finding_identified  |  **Verification status:** confirmed
- **Affected workflows:** WF-2 guided data entry (all field steps), WF-10 admin configuration, Trends reporter custom date range

**Evidence:**

- `frontend/js/dashboard_decomp_row_model.js:2648-2727` — `fieldHtml` — The visible label is <div class="field-label">. The <input>, <select> and checkbox get no id, aria-label or aria-labelledby, and no <label for>. The 'Required' badge, unit and note are sibling divs with no aria-describedby, aria-required or aria-invalid. The only accessible-name fallback for a text input is its placeholder, which is the schema default.
- `frontend/js/dashboard_decomp_row_model.js:2671` — `toggle-switch` — Boolean fields are <label class="toggle-switch"> wrapping the checkbox and the texts YES and NO. The checkbox's accessible name is therefore 'YES' or 'NO', not the field's name.
- `frontend/js/admin.js:794-818` — `settingHelpButton / settingControl` — The admin help button has an aria-label, but the .cfg-input and .cfg-select controls next to it have no label association.
- `frontend/js:n/a (grep over *.js)` — `<input / <select templates` — 5 of 120 <input> templates and 2 of 50 <select> templates carry aria-label. There is 1 <label ... for= in the whole directory, and a grep found no aria-labelledby, aria-describedby, aria-required or aria-invalid on any field.
- `financial_trends_reporter/frontend/index.html:41-51` — `timeframe buttons / customFrom / customTo` — The date inputs have no labels, and the selected timeframe is shown only by the CSS class 'active'.

**Observed behavior:** A screen reader announces most plan inputs as 'edit text' (or reads the placeholder default), selects as an unnamed combo box, and yes/no toggles as a 'YES' or 'NO' checkbox, with no field name, required state or help text.

**Impact:** The core data-entry workflow cannot be used with a screen reader or voice control ('click Retirement age' does not work). This fails WCAG 1.3.1, 3.3.2 and 4.1.2 on the app's main interaction surface.

**Root cause:** Field rows are built as HTML strings in which the label is a styled div, not a <label>, and no id links the label to the control.

**Options:**

- Give the label div an id (field-label-<row_index>) and add aria-labelledby, plus aria-describedby for the note, unit and required badge, to every control in fieldHtml and settingControl.
- Change the label div to <label for="field-<row_index>-ctl"> and give each control that id, which also makes clicking the label focus the control.
- Add aria-label from humanLabel() to each control. This is the least markup, but the name and description can drift from the visible label.

**Recommendation:** Option 2 for fieldHtml and settingControl, because a native label is the most robust. Add aria-required when isRequired(row), aria-invalid when the row is missing, and aria-describedby pointing at the unit and note. For toggles, name the checkbox from the field label and mark the YES/NO text aria-hidden.

**Implementation considerations:** fieldHtml is one function that many steps share, so one change covers most fields. Python tests that read panel JS as text (per CLAUDE.md) may assert on this markup, so read them first. Other templates, such as housing optimizer, taxonomy and YTD inputs, need a sweep afterwards.

**Risk of change:** Low. The changes add attributes only. Making the label clickable could change the existing field onclick=showFieldHelp behaviour.

**Verification method:** Add a node test that renders fieldHtml for text, choice, boolean and required rows and asserts that every control has a computed name (a label[for] match or aria-labelledby). Then do a manual NVDA or Narrator pass on one data-entry step.

**Linked implementation items:** WI-503

**Verification rationale (adversarial pass):** Opened dashboard_decomp_row_model.js:2648-2727 (fieldHtml). Confirmed: label is a <div class="field-label">, not a <label>; the input/select/checkbox elements have no id/aria-label/aria-labelledby/aria-describedby/aria-required; text inputs' only name signal is placeholder=r.schema?.default. Boolean fields are wrapped in <label class="toggle-switch"> containing the checkbox plus literal 'YES'/'NO' spans with no aria-hidden, so the checkbox's accessible name would indeed resolve to that toggle text, not the field label. This matches the finding precisely; did not independently re-verify the admin.js/financial_trends_reporter citations or the grep counts, but the core fieldHtml claim (the shared, highest-impact template) is directly confirmed.


---

### ARC-002 — Desktop shortcut and START_APP.bat launch bypass main.py, so the startup plan-data migration never runs, and local-mode env defaults are copied into three places

- **Expert:** architect  |  **Category:** architecture  |  **Severity:** medium  |  **Confidence:** high
- **Inspection status:** finding_identified  |  **Verification status:** confirmed
- **Affected workflows:** App startup (desktop shortcut), Spending budget/rules/aliases after schema migrations

**Evidence:**

- `launchers/START_APP.bat:4` — `SCRIPT=tools\launchers\START_DESKTOP.py` — The primary launcher runs START_DESKTOP.py, not main.py.
- `launchers/CREATE_DESKTOP_SHORTCUT.vbs:22-24` — `strScript1` — The desktop shortcut targets START_DESKTOP.py via pythonw.
- `tools/INSTALL_DESKTOP_ICON.py:10-12` — `UI_SCRIPT` — The installed icon also targets START_DESKTOP.py.
- `tools/launchers/START_DESKTOP.py:19-36` — `__main__` — Sets its own env defaults, then calls src.desktop_app.start() directly. There is no plan-data migration call.
- `main.py:141-166` — `main` — run_startup_plan_data_migration() is called only here, before the desktop/server dispatch.
- `src/desktop_api.py:21-35` — `_set_local_mode_defaults` — A third, slightly different copy of the env defaults (no CONFIG_FILE/OUTPUT_DIR).
- `src/plan_data_migration.py:93-108, 188-228, 340-364` — `_FLAT_CATEGORY_RENAMES / migrate_flat_category_content` — Category-id renames in flat budget/rules/alias files happen only at rest. The module's own comment says skipping them leaves budget lines, rules and aliases pointing at ids that no longer exist. Per-load normalization (data_io.py:591) covers only sectioned data.

**Observed behavior:** Launching through the desktop icon or START_APP.bat never runs the at-rest migration and never stamps the schema version. Only `python main.py` and the frozen exe run it. The same local-mode env defaults are maintained in main.py, desktop_api.py and START_DESKTOP.py, and the copies already differ.

**Impact:** Plan data created before a schema bump keeps legacy flat category ids when the user only launches from the shortcut, which can orphan budget, rule and alias rows (wellness→healthcare today, and every future migration too). Startup behaviour differs by launch path, which undermines reproducibility.

**Root cause:** Startup orchestration lives in main.main() rather than in a shared bootstrap that every entry point calls.

**Options:**

- Point START_DESKTOP.py, START_APP.bat and the shortcut installers at main.py (desktop mode is the default there).
- Move env defaults and the startup migration into a single src/bootstrap.py function called by main.py, START_DESKTOP.py and DesktopApi.__init__.

**Recommendation:** Option 2: one bootstrap function. Keep START_DESKTOP.py as a thin wrapper around it so existing shortcuts keep working.

**Dependencies:** Prior review ARC-001/ARC-002 (the migration's non-atomic write and silent outer except are still present at plan_data_migration.py:364 and 413-414); fix those before running the migration from more entry points.

**Implementation considerations:** The migration must stay out of the frozen script-runner path (main.py:147-150 comment). DesktopApi also calls create_app, so the bootstrap must be idempotent.

**Risk of change:** Low. The migration is designed to be idempotent.

**Verification method:** Static: every launcher reaches one bootstrap function. Test: a fixture with a legacy flat category id, launched via the START_DESKTOP entry, is migrated.

**Linked implementation items:** WI-000

**Verification rationale (adversarial pass):** launchers/START_APP.bat runs tools\launchers\START_DESKTOP.py, not main.py. START_DESKTOP.py's __main__ block sets local-mode env defaults and calls src.desktop_app.start() directly with no call to run_startup_plan_data_migration, which in main.py is invoked only inside main() before dispatch (confirmed at lines ~141-166 of main.py, with an explicit comment explaining why it is NOT above the frozen script-runner branch). desktop_api.py separately defines _set_local_mode_defaults() with a third, non-identical copy of the same env-default dict (it omits CONFIG_FILE/OUTPUT_DIR, matching the finding). This is a real, verifiable startup-path inconsistency. Severity/confidence as stated are reasonable; recommendation (shared bootstrap) is sound and low-risk as described.


---

### ARC-003 — No persistent diagnostics: src never uses the logging module, print output is discarded under the pythonw launch, and _audit is hard-disabled so every audit call is a no-op

- **Expert:** architect  |  **Category:** observability  |  **Severity:** medium  |  **Confidence:** high
- **Inspection status:** finding_identified  |  **Verification status:** confirmed
- **Affected workflows:** All desktop sessions, Build troubleshooting, Load Saved Plan, Secret management

**Evidence:**

- `src/runtime_config.py:57, 109, 153` — `audit_log_enabled` — Hardcoded False inside load_runtime_config, so no configuration can enable it.
- `src/server/security_audit.py:148-168` — `_audit` — Both the JSONL write and append_audit_event_sqlite sit inside `if cfg.audit_log_enabled`, so plan_loaded_file, secret_set, permission_denied, admin_reference_file_saved and plan_load_file_materialize_warning events are never recorded.
- `src/http_runtime/wsgi_facade.py:333-343` — `_Logger` — app.logger is a print() shim.
- `tools/INSTALL_DESKTOP_ICON.py:10` — `PY = 'pythonw'` — The desktop icon runs under pythonw, where stdout is discarded.
- `src/build_entry.py:43-46` — `_materialize_server_working_copy` — Failures surface only as a print('WARN: ...').
- `src/report_compute.py:278-309` — `run_projection_artifacts` — Contract/spec failures become warnings, and save_result_snapshot errors are swallowed with a bare pass.

**Observed behavior:** `import logging`/getLogger appears in 0 files under src/. Diagnostics are about 112 print() calls in 11 files plus about 74 `except Exception: pass` sites. In the normal desktop launch nothing is written anywhere a user or developer can retrieve it afterwards, and the audit trail the code appears to maintain is empty.

**Impact:** Silent data-path failures (materialization, snapshot save, migration DB sweep, build warnings) cannot be diagnosed after the fact. Security-relevant events (secret changes, plan replacement) leave no trace.

**Root cause:** SaaS-era audit and logging plumbing was disabled rather than repointed at a local sink. The stdlib runtime replaced Flask's logger with prints.

**Options:**

- Add a rotating file handler (local_state/logs/app.log) configured once at bootstrap, route _Logger and existing WARN prints through logging, and remove the hardcoded audit_log_enabled=False so audit events go to the existing SQLite audit_events table.
- Keep prints but redirect sys.stdout/stderr to a log file when running under pythonw, and re-enable SQLite-only auditing.

**Recommendation:** Option 1. Redaction already exists (redact_text, redact_secrets_in_logs), so the privacy boundary can be kept.

**Dependencies:** ARC-002 (single bootstrap is the natural place to configure logging)

**Implementation considerations:** Keep audit rows free of financial values: _audit details already carry names and paths, not amounts. Bound the log size, because the admin change log already caps at 250.

**Risk of change:** Low.

**Verification method:** Static: logging is configured once and audit_log_enabled is configurable. Test: calling _audit inserts an audit_events row.

**Linked implementation items:** WI-204

**Verification rationale (adversarial pass):** runtime_config.py hardcodes audit_log_enabled = False at load_runtime_config with no override path (lines 57/109/153 region), and security_audit.py's _audit() wraps both the JSONL write and append_audit_event_sqlite inside `if cfg.audit_log_enabled`, so audit events are unconditionally no-ops today. A repo-wide grep for `import logging`/`getLogger` under src/ returned zero matches, confirming stdlib logging is unused. This is a legitimate, verifiable observability gap; severity/confidence as given are reasonable and not overstated.


---

### ARC-004 — A failed async build whose error text contains 'not found' or '404' triggers a second synchronous build that, in desktop mode, holds the bridge lock for up to 30 minutes

- **Expert:** architect  |  **Category:** correctness  |  **Severity:** medium  |  **Confidence:** high
- **Inspection status:** finding_identified  |  **Verification status:** confirmed
- **Affected workflows:** Build workbook

**Evidence:**

- `frontend/js/dashboard_decomp_build_lifecycle.js:251-327` — `buildWithProgress` — The outer catch covers the whole polling loop, including `throw new Error(result.error ...)` for status 'failed'. Any message containing '404' or 'not found' falls back to POST /api/build.
- `src/local_plan_data_sync.py:55-59` — `sync_plan_data_from_folder` — A real build-path failure raises 'Plan Data folder not found: ...', which matches the fallback test.
- `src/server/workbook_routes.py:330-357` — `build` — The synchronous build runs subprocess.run with timeout=cfg.max_build_seconds.
- `src/runtime_config.py:111-119` — `max_build_seconds` — Defaults to 1800 seconds.
- `src/desktop_api.py:88-103` — `DesktopApi.request` — Every bridge call runs under one threading.Lock, so a synchronous build blocks all other API calls.

**Observed behavior:** A genuine build failure is retried as a second full build. The retry uses a different code path (it sets RETIREMENT_SYSTEM_SKIP_PLAN_DATA_ENV_SYNC), so it can mask or change the original error. In desktop mode the UI's API calls queue behind the lock for the whole run.

**Impact:** Build failures double in time, the UI appears frozen, and the reported error may differ from the root cause.

**Root cause:** String matching on error text to detect a missing endpoint, and a catch scope wider than the /api/build/start call.

**Options:**

- No credible alternative; this is a correctness defect.

**Recommendation:** Limit the fallback to a 404 from the initial /api/build/start call, e.g. by checking an HTTP status or error code on that call only, and never fall back after a job id was issued.

**Implementation considerations:** The desktop bridge drops HTTP status (desktop_api._convert returns only the body for status < 500), so a structured error code in the JSON is the portable signal.

**Risk of change:** Low.

**Verification method:** Static: the catch no longer wraps the polling loop. Frontend unit test: a job that ends 'failed' with a 'not found' message does not call /api/build.

**Linked implementation items:** WI-106

**Verification rationale (adversarial pass):** dashboard_decomp_build_lifecycle.js buildWithProgress wraps the entire polling loop (including the `job.status === 'failed'` throw) in one try/catch, and the catch does string-matching on the error message for '404' or 'not found' before falling back to a second POST /api/build — exactly as described. local_plan_data_sync.py's genuine 'Plan Data folder not found' error text would match this fallback condition, confirming the false-positive path. This is a real correctness defect with a straightforward, low-risk fix (scope the catch to the initial start call only); severity/confidence are appropriately calibrated.


---

### ARC-005 — Load Saved Plan overwrites the live SQLite DB with any chosen file without checking it, and the two DB-replacement paths apply different, non-overlapping safeguards

- **Expert:** architect  |  **Category:** data-integrity  |  **Severity:** medium  |  **Confidence:** medium
- **Inspection status:** finding_identified  |  **Verification status:** confirmed
- **Affected workflows:** Load Saved Plan (.rpx), Snapshot restore

**Evidence:**

- `src/server_services/plan_file_service.py:100-127` — `PlanFileService.load_file` — Checks only that the file exists, then shutil.copy2 over the active DB. There is no SQLite header, integrity_check or schema check. It removes -wal/-shm sidecars.
- `src/build_snapshot.py:134-172` — `restore_sqlite_database_from_snapshot` — Checks a sha256 but does not remove WAL sidecars before copying over the active DB. That is the opposite safeguard set from load_file.
- `src/desktop_api.py:335-351` — `show_open_dialog` — The file filter includes 'All files (*.*)'.
- `frontend/js/dashboard_decomp_checklist_closeout.js:648-688` — `loadSavedPlan` — Posts the chosen path straight to /api/plan/load-file.
- `src/plan_data_migration.py:302-392` — `migrate_plan_data_at_rest` — Runs only at startup, so a loaded older .rpx is not migrated at rest until the next boot.

**Observed behavior:** Picking a wrong or corrupt file replaces the working database. A before_load_* backup is kept and pruned to 10. Snapshot restore can leave a stale -wal next to a replaced DB file. No check, of any kind, confirms the loaded file is a plan database.

**Impact:** The app can end up running on a non-plan or older-schema database. Recovery depends on the user finding the before_load backup by hand. A stale WAL can be replayed onto a different database file, which is a corruption risk.

**Root cause:** DB file replacement is implemented twice without a shared, validated helper.

**Options:**

- Create one replace_active_db(src) helper: open src read-only, run PRAGMA integrity_check and a required-table check, checkpoint and close, copy to a temp file, os.replace, clear sidecars, then run the plan-data migration.
- Keep the two paths but add validation to load_file and sidecar cleanup to snapshot restore.

**Recommendation:** Option 1. Both routes then share the same safety guarantees.

**Dependencies:** ARC-002 (bootstrap/migration entry point)

**Implementation considerations:** On Windows, replacing a file that another connection has open can fail. Connections here are short-lived (`with sqlite3.connect`), but build subprocesses may hold one.

**Risk of change:** Low to medium.

**Verification method:** Test: load a non-SQLite file and the request returns an error with the active DB unchanged. Test: after a restore no stale -wal remains.

**Linked implementation items:** WI-201

**Verification rationale (adversarial pass):** plan_file_service.py load_file only checks src.exists()/is_file() before shutil.copy2-ing over the active DB (no integrity_check, no schema check), while build_snapshot.py's restore_sqlite_database_from_snapshot checks a sha256 hash but does not remove -wal/-shm sidecars before or after the copy (confirmed by reading both functions in full) — genuinely two different, non-overlapping safeguard sets as claimed. This is a real data-integrity gap; the proposed shared replace_active_db() helper is a sound remediation. Severity/confidence as given are reasonable.


---

### ARC-006 — Provider API keys are designed to live in the git-tracked system_config.csv, and the admin editor writes them there, ahead of the gitignored secret store

- **Expert:** architect  |  **Category:** security  |  **Severity:** medium  |  **Confidence:** medium
- **Inspection status:** finding_identified  |  **Verification status:** partially_confirmed
- **Affected workflows:** Market pricing setup, Plan Chat configuration, Backups, Git commits

**Evidence:**

- `system_config.csv:label grep only` — `Market Pricing,API,fmp_api_key / alpha_vantage_api_key; System Configuration,Plan Chat,openai_api_key (listed twice)` — The key rows exist in a tracked file (git ls-files lists system_config.csv). Values were deliberately not read.
- `src/market_data.py:261-291, 327-341` — `refresh_api_keys / configure_api_keys` — Precedence is config CSV, then env, then secret store. The docstring calls the store 'encrypted'.
- `src/secrets_store.py:6, 16-18, 21-34` — `DEFAULT_SECRETS / _save / encryption_status` — The store is plaintext JSON, 'encrypted': False, under gitignored local_state/.
- `frontend/js/admin.js:813-818` — `field renderer` — api_key rows are rendered as password inputs in System Configuration, with the value embedded in the page, and saved back to the CSV.
- `src/server/app_core.py:434-435` — `_system_config_path` — System config is BASE_DIR/system_config.csv, the tracked file.

**Observed behavior:** A key entered through System Configuration is persisted in a tracked file and becomes part of any commit, the admin CSV backup zip and the OneDrive project backup. The secret store and its backup exclusion (tools/backup_to_onedrive.py:49) are bypassed for that path. No test was found that guards against committing non-empty key values.

**Impact:** Third-party API credentials can leak into git history and backups.

**Root cause:** Legacy multi_user/system_config.csv convention kept alongside a newer secret store.

**Options:**

- Route api_key/secret rows in the admin editor to /api/secrets (secret store) and stop reading keys from system_config.csv (or read it only as a deprecated fallback with a warning).
- Keep the CSV location but add a pre-commit/test guard that fails when the key cells are non-empty, and exclude system_config.csv from backups.

**Recommendation:** Option 1. The secret store, /api/secrets and the backup exclusion already exist.

**Implementation considerations:** Need a one-time move of any existing CSV values into the secret store without printing them. Check whether keys were ever committed (a history check is outside this review).

**Risk of change:** Low.

**Verification method:** Static: admin save of an api_key row calls set_secret and never writes system_config.csv. A test asserts the tracked key cells are blank.

**Linked implementation items:** WI-206

**Verification rationale (adversarial pass):** Confirmed structurally: admin_service.save_system_config() writes the entire posted CSV content/rows straight to the tracked system_config.csv with zero special-casing for secret/api_key rows — no call to set_secret anywhere in that path — so an operator who types a real fmp_api_key or alpha_vantage_api_key into System Configuration would have it persisted into a git-tracked file, and market_data.py's refresh_api_keys()/configure_api_keys() docstring explicitly says keys are read 'from multi_user/system_config.csv' with config value taking precedence over the secret store. However, the finding's own cited evidence undercuts the openai_api_key half of the claim: system_config.csv row 121 already documents that field as 'Deprecated; plaintext Plan Chat keys in CSV are ignored' with a companion openai_api_key_secret_name row that reads from the encrypted secret store — i.e. that credential family has already been migrated off this anti-pattern. The fmp_api_key/alpha_vantage_api_key rows are also currently blank ('intentionally blank in secure release package'), so there is no live secret leak today, only a live design/precedent flaw for those two providers. Severity should probably be scoped down slightly (or the recommendation narrowed to fmp/alpha_vantage only, following the pattern openai already uses) rather than treated as a uniform three-key problem.


---

### ARC-007 — The PyInstaller build bundles the developer's live, untracked input/ folder and about 51 MB of unused libraries, and the frozen app keeps its writable data inside the dist folder that each rebuild wipes

- **Expert:** architect  |  **Category:** build-artifacts  |  **Severity:** medium  |  **Confidence:** medium
- **Inspection status:** finding_identified  |  **Verification status:** confirmed
- **Affected workflows:** Standalone exe build and use, Backups (dist/ is deliberately backed up)

**Evidence:**

- `retirement_planner.spec:21-35, 41-55` — `collect_all loop / app_datas` — Calls collect_all on matplotlib, reportlab, PIL and cryptography, and bundles the whole ('input','input') folder.
- `retirement_planner.spec:62-106` — `hidden_imports` — Lists src.reporting.enterprise_pdf, which does not exist, plus hazmat, PIL and matplotlib backends.
- `build.py:1-40` — `main` — Runs PyInstaller with --noconfirm, replacing dist/ on every build.
- `src/platform_runtime.py:56-80` — `package_root / workspace_root` — The workspace defaults to the package root, which in a frozen build is the bundle's _internal dir, unless RETIREMENT_SYSTEM_WORKSPACE_ROOT is set. No launcher sets it.
- `tests/test_monte_carlo_diagnostics_and_dependency_manifest.py:27-32` — `test_requirements_manifest_lists_runtime_dependencies` — Pins matplotlib, pillow and cryptography in requirements.txt. git grep finds no import of matplotlib, PIL or cryptography in src/, tools/ or financial_trends_reporter/.
- `dist/retirement_planner/_internal:n/a (directory listing, names and sizes only)` — `bundle contents` — The input/ folder holds 59 entries (41 client_* files), against 29 tracked files under input/. matplotlib is 20M, PIL 15M, cryptography 11M, reportlab 4.9M, in a 283M bundle.

**Observed behavior:** The build copies whatever is in the developer's input/ into the distributable, including untracked real plan files and *.yaml_recover_backup files. It ships several unused heavy packages. A frozen run would read and write plan data under dist/…/_internal, which the next rebuild deletes.

**Impact:** Privacy: sharing the exe folder shares the household's financial data. Data loss: exe-edited data does not survive a rebuild. Size and attack surface: about 18% of the bundle is unused code.

**Root cause:** The spec treats input/ as a template seed while the working tree holds live data, and the dependency list was never pruned after features were removed.

**Options:**

- Bundle only input/demo (tracked, fictional) as the seed, set a per-user workspace root (e.g. %LOCALAPPDATA%) when frozen, and drop collect_all and requirements entries for unused packages (update the pinning test).
- Keep the current layout but add a build-time guard that refuses to package untracked input files, and document that the exe is dev-only.

**Recommendation:** Option 1.

**Dependencies:** ARC-002 (bootstrap is where a frozen workspace root would be set)

**Implementation considerations:** Confirm openpyxl image or chart features do not need Pillow at runtime before removing it. Confirm no dynamic imports of reportlab or matplotlib via importlib. The frozen __file__ layout should be checked on a real build.

**Risk of change:** Medium: packaging changes need a real frozen smoke test.

**Verification method:** Build and list dist/_internal/input: only demo files. Import-scan confirms the removed packages are unused. A frozen run writes to the per-user workspace.

**Linked implementation items:** WI-205

**Verification rationale (adversarial pass):** retirement_planner.spec confirms collect_all() is called for numpy, scipy, lxml, matplotlib, reportlab, openpyxl, PIL and cryptography, and app_datas bundles the whole ('input','input') folder with a comment confirming input/ is a live, user-edited-in-place directory rather than a fixed demo seed — supporting the untracked-live-data-bundling claim. A repo-wide grep for actual imports of matplotlib/PIL/cryptography in src/, tools/, and financial_trends_reporter/ returned zero hits, supporting the 'unused dependency' claim (openpyxl's own internal use of these is an appropriately-flagged open question in the finding itself, not a gap in the finding). This is a real, verifiable build-hygiene and privacy concern; severity/confidence are reasonable given the finding was not verified against an actual frozen build (which this static review correctly does not attempt).


---

### ARC-008 — The atomic_write helper exists, but several user-data writes still rewrite whole files non-atomically (holdings, liabilities, HSA schedule, plan-load materialization, trends log, secret store)

- **Expert:** architect  |  **Category:** data-integrity  |  **Severity:** medium  |  **Confidence:** medium
- **Inspection status:** finding_identified  |  **Verification status:** confirmed
- **Affected workflows:** Holdings/Liabilities/HSA editing, Load Saved Plan, Financial Trends Reporter daily run, API key storage

**Evidence:**

- `src/plan_file_io.py:68-104` — `atomic_write / write_text_atomic` — The atomic helper, which uses mkstemp and os.replace.
- `src/server_services/holdings_service.py:25-34, 49-58, 78-87` — `save_holdings / save_liabilities / save_hsa_schedule` — Calls p.write_text on the disk file before the DB copy (set_client_file). Disk is read first (read_* returns the workspace file when it exists).
- `src/config_backend.py:370-379` — `materialize_workspace_files` — Uses dest.write_text with overwrite_existing=True when called from plan_load_file (plan_routes.py:1252-1259).
- `financial_trends_reporter/trends_log.py:1-11, 40-53` — `append_or_replace_entry` — Described as 'append-only' but rewrites the entire history with write_text. read_history skips unparsable lines, so a truncated write silently drops history.
- `src/secrets_store.py:9-18` — `_load / _save` — Non-atomic JSON rewrite. _load returns {} on any parse error, so a torn file silently loses every key, and the next save persists that loss.

**Observed behavior:** `git grep` finds about 39 direct write_text/write_bytes calls in src/ and financial_trends_reporter/, against atomic_write use in 6 modules. The paths above hold primary user data, not derived output.

**Impact:** A crash, sleep or OneDrive lock during a save can leave a truncated holdings, liabilities or HSA CSV that the disk-first read path then serves, or wipe the trends history or stored API keys.

**Root cause:** atomic_write was adopted per-incident rather than as the standard for user-data writes (prior review ARC-001 covered only the migration path).

**Options:**

- Route every user-data write through plan_file_io.atomic_write and add a lint/test that forbids bare write_text under input/, local_state/ and financial_trends_reporter/data/.
- Fix only the primary-data paths listed here and leave derived outputs as they are.

**Recommendation:** Option 1. Keep derived outputs (workbook sidecars, report package) on the allow-list.

**Dependencies:** Prior review ARC-001 (the same pattern in plan_data_migration.py:364 is still present at HEAD)

**Implementation considerations:** PR #141 changes only the trends_log key semantics, not the write strategy. Use newline='' for CSVs to match existing writers.

**Risk of change:** Low.

**Verification method:** Static grep: no bare write_text on user-data paths. Test: a simulated failure mid-write leaves the original file intact.

**Linked implementation items:** WI-202

**Verification rationale (adversarial pass):** Spot-checked holdings_service.py: save_holdings/save_liabilities use plain p.write_text(...) (confirmed non-atomic writes at the cited lines), consistent with the claim that primary user-data writes bypass the existing atomic_write helper in plan_file_io.py. The finding's broader grep-based count (~39 bare write_text/write_bytes vs. 6 modules using atomic_write) was not independently re-run in full but the sampled evidence supports the pattern. This is a real data-integrity risk (torn writes on crash/lock contention) with a low-risk, well-scoped fix (route through atomic_write). Severity/confidence as given are reasonable.


---

### DOC-001 — The yearly tax-update runbook and the in-app tax-law dashboard send maintainers to files the engine does not read, and leave out the dated-row rule

- **Expert:** documentation  |  **Category:** documentation-accuracy  |  **Severity:** medium  |  **Confidence:** high
- **Inspection status:** finding_identified  |  **Verification status:** confirmed
- **Jurisdiction:** US federal (IRS, CMS)  |  **Rule year:** 2025 dataset rows; 2026 reference year
- **Assumptions:** Assumes the JSON dataset loads normally. The numeric impact was not measured.
- **Affected workflows:** Annual tax-law maintenance, Tax planning / IRMAA projections, Plan Status staleness banner

**Evidence:**

- `documentation/reference/ANNUAL_MAINTENANCE_RUNBOOK.md:30-48` — `Tax-year checklist` — Step 2 says to update tax_constants.csv for standard deduction, over-65 deduction, contribution limits and SS wage base. Step 3 limits tax_law_v10.json updates to brackets, LTCG and IRMAA. Step 4 bumps the dashboard, which clears the staleness banner. Nothing mentions effective_year or adding dated rows.
- `src/taxes.py:42-58, 336-400` — `_load_federal_tax_law_tables / load_tax_constants` — The JSON dataset is the only source of federal values. tax_constants.csv is read only in the except-fallback.
- `src/taxes.py:72-100` — `FEDERAL_BRACKETS_VALUE_YEAR / IRMAA_TIERS_VALUE_YEAR` — The indexing base year comes from each JSON row's effective_year.
- `src/tax_law.py:54-68` — `TaxLawDataset lookup` — Picks the latest row with effective_year <= reference year. The dataset is built to have dated rows appended.
- `reference_data/tax_law_v10.json:405-420` — `irmaa_tier1_threshold rows` — Values carry effective_year 2025. Editing a value without its date would mislabel the value year.
- `reference_data/tax_constants.csv:1-18` — `tax_constants` — Holds no contribution limits, although runbook step 2 says to update them here.
- `src/data_io.py:840` — `k401_lim` — The 401(k) limit is a per-household Plan Data field.
- `reference_data/tax_update_dashboard.csv:1-6` — `dashboard rows` — The in-app source text says the tables are 'embedded in src/taxes.py' and tells the reader to update tax_constants.csv. The code contradicts both.

**Observed behavior:** The only written procedure for the yearly federal tax-law refresh points to a fallback-only file. It omits the dated-row rule for tax_law_v10.json and puts contribution limits in the wrong place. The in-app dashboard describes an old table layout.

**Impact:** A maintainer following the runbook can update values that have no effect, or overwrite JSON values without their dates, and then clear the staleness banner. Stale or wrongly indexed deductions, brackets and IRMAA thresholds would then sit behind a 'current' banner.

**Root cause:** The v11 move to a dated JSON dataset was not carried into the runbook or the dashboard notes.

**Options:**

- No credible alternative; this is a correctness defect.

**Recommendation:** Rewrite the tax-year checklist around adding new dated rows to tax_law_v10.json, covering every family of values it holds. Point contribution limits to the Plan Data fields. Label tax_constants.csv as a fallback only. Correct the source/notes text in tax_update_dashboard.csv.

**Dependencies:** Financial planner confirmation of the IRMAA value-year procedure (#334)

**Implementation considerations:** The dashboard CSV text is shown in the app. A small doc test could check that the runbook names effective_year.

**Risk of change:** Very low (text only).

**Verification method:** Read the runbook against src/taxes.py:42-100 and src/tax_law.py:54-68. Dry-run on a scratch copy and confirm with regen_golden_master.py measure.

**Linked implementation items:** WI-311

**Verification rationale (adversarial pass):** Opened documentation/reference/ANNUAL_MAINTENANCE_RUNBOOK.md:30-48 — Step 2 literally says 'Update reference_data/tax_constants.csv: ... 401(k)/HSA/IRA contribution limits', Step 3 limits tax_law_v10.json updates to 'federal ordinary brackets, LTCG thresholds, IRMAA tiers and surcharges' with no mention of effective_year/dated rows. Opened src/taxes.py:29-107 confirming FEDERAL_BRACKETS_VALUE_YEAR/IRMAA_TIERS_VALUE_YEAR are derived from each JSON row's effective_year via _load_federal_tax_law_tables, and src/tax_law.py:54-68 confirming TaxLawDataset.lookup picks the row with the latest effective_year <= reference year — so editing a value without adding a new dated row would misdate it. Opened reference_data/tax_constants.csv:1-18 and confirmed it holds standard deduction, over-65 deduction, NIIT thresholds and SS wage base but no 401(k)/HSA/IRA contribution limit keys, matching the finding. Opened src/data_io.py:840 confirming k401_lim is read from per-household Plan Data, not tax_constants.csv. Opened reference_data/tax_update_dashboard.csv:1-6 and its 'notes'/'source' text says federal_brackets and irmaa_tiers are 'embedded in src/taxes.py', which is misleading given taxes.py loads them from the JSON dataset, not a hardcoded table. Severity medium is reasonable; if anything this could be argued high given silent misdating risk, but medium is defensible given no measured numeric impact (finding itself notes this).


---

### DOC-002 — End-user README wrongly says nothing is sent over the internet; by default the app sends ticker symbols to outside price services

- **Expert:** documentation  |  **Category:** documentation-accuracy  |  **Severity:** medium  |  **Confidence:** high
- **Inspection status:** finding_identified  |  **Verification status:** confirmed
- **Affected workflows:** First run / README, Workbook build, Price refresh

**Evidence:**

- `documentation/reference/readme/README.md:8-12` — `Running the app` — Says 'nothing is sent anywhere over the internet.'
- `system_config.csv:23` — `pricing_mode` — The shipped default is LIVE.
- `src/market_data.py:7-17, 67-75, 535-536` — `provider URLs / urlopen` — Quotes are fetched from FMP, Yahoo, Alpha Vantage, Stooq and Nasdaq, with symbols and API keys in the URLs.
- `src/data_io.py:665-667, 1837-1842` — `prewarm_prices / fetch_price` — The plan load and build path pre-fetches prices for all held symbols.
- `frontend/js/dashboard_decomp_checklist_closeout.js:284` — `renderSystemConfiguration` — The Pricing mode card says nothing about what leaves the machine.

**Observed behavior:** The household README promises no network traffic. The default configuration contacts outside quote services with the household's ticker symbols.

**Impact:** A privacy statement to a non-expert user is wrong. Holdings composition and the user's IP address are exposed to third parties without informed choice.

**Root cause:** The 'local-only' framing covers hosting and storage but ignores outbound market-data calls.

**Options:**

- Correct the README and explain OFFLINE mode.
- Also add a disclosure on the Pricing mode card.
- Change the default pricing_mode to CACHE or OFFLINE.

**Recommendation:** Options 1 and 2. Leave the default-mode decision to the architect and privacy reviewer.

**Dependencies:** Architect/privacy stage decision on the default pricing_mode

**Implementation considerations:** The README currency test could gain a marker for the disclosure sentence.

**Risk of change:** None for docs; low for a default change.

**Verification method:** Grep for 'over the internet'. Read the card text.

**Linked implementation items:** WI-601

**Verification rationale (adversarial pass):** Opened documentation/reference/readme/README.md:8-12 — states 'nothing is sent anywhere over the internet.' Opened system_config.csv:23 — shipped default pricing_mode is LIVE. Opened src/market_data.py:1-20 — module docstring confirms live providers (FMP, Yahoo, Alpha Vantage, Stooq) are contacted in LIVE mode before cache/fallback, contradicting the README's blanket claim. This is a direct, unambiguous factual contradiction between end-user-facing documentation and the shipped default configuration/code. Severity medium as assessed is reasonable (arguably could be rated high given it's a false privacy claim to non-expert users, but I won't override the expert's calibration without stronger justification).


---

### DOC-003 — The two 'as it behaves today' specs leave out the housing optimizer, Next Housing Move, Plan Features, Spending Adjustments and the one-time Large Discretionary model

- **Expert:** documentation  |  **Category:** documentation-currency  |  **Severity:** medium  |  **Confidence:** high
- **Inspection status:** finding_identified  |  **Verification status:** confirmed
- **Affected workflows:** Housing planning, Spending model, Plan Features, Onboarding

**Evidence:**

- `documentation/reference/FUNCTIONAL_SPEC.md:1-9, 145-152` — `header / 4.2 Spending` — Claims to describe current behavior. Zero matches for housing optimizer, ZIP, Next Housing Move, Plan Features or Spending Adjustment.
- `documentation/reference/CURRENT_SYSTEM_DESIGN_SPEC.md:1-7, 486-492` — `header / 7.3 Navigation model` — Claims to be 'verified against source' (last commit 2026-09-14). Lists nav groups that were removed.
- `frontend/js/dashboard.js:106-108, 134, 481` — `STEPS` — Next Housing Move and the Plan Features page are live.
- `frontend/js/dashboard_decomp_large_discretionary.js:117-146, 183-185` — `migrateLargeDiscLines` — Large Discretionary is now one-time only and never annualized.
- `tests/test_functional_spec_feature_currency_regression.py:1-35` — `FEATURE_MARKERS` — The guard list was not extended for PRs #114-#139.

**Observed behavior:** The living specs predate the housing optimizer, modular features and W-A..W-F work, and describe removed navigation as current.

**Impact:** Anyone using the specs to understand or explain the system gets a wrong picture of major features. The guard test gives false comfort.

**Root cause:** Spec and marker updates were skipped. New specs went to docs/superpowers/ instead.

**Options:**

- Backfill both specs and add their markers to the guard list.
- Generate the nav and feature sections from module_catalog and STEPS.
- Add a PR checklist item and a 'verified at commit' line.

**Recommendation:** Option 1 now; consider Option 2 for the nav section (resolves prior DOC-001).

**Dependencies:** Prior review DOC-001

**Implementation considerations:** Docs plus one test list. Describe the Next Housing Move gating in plain words.

**Risk of change:** None.

**Verification method:** Grep the specs for each feature. Check FEATURE_MARKERS.

**Linked implementation items:** WI-703

**Verification rationale (adversarial pass):** Grepped documentation/reference/FUNCTIONAL_SPEC.md and documentation/reference/CURRENT_SYSTEM_DESIGN_SPEC.md for 'housing optimizer', 'Next Housing Move', 'Plan Features', 'Spending Adjustment' — zero matches in both files, confirming the omission. Opened frontend/js/dashboard.js:106-155,481 — confirmed 'Next Housing Move' and 'Plan Features' (title at line 481) are live, current UI concepts, not legacy/removed ones. Opened frontend/js/dashboard_decomp_large_discretionary.js:110-146 — migrateLargeDiscLines confirms legacy repeatable Large Discretionary rows are converted to one-time rows per year, consistent with the claim that it is now one-time-only. Did not independently verify the nav-group removal claim in CURRENT_SYSTEM_DESIGN_SPEC.md §7.3 or the FEATURE_MARKERS guard-list claim, but the core 'specs omit major live features' claim is directly confirmed by the grep evidence.


---

### DOC-004 — The only record of backlog items #332-#339 shows the wrong progress, and deferred work has no tracker

- **Expert:** documentation  |  **Category:** work-tracking  |  **Severity:** medium  |  **Confidence:** high
- **Inspection status:** finding_identified  |  **Verification status:** confirmed
- **Affected workflows:** Backlog management, Agent-driven plan execution, Golden-master governance

**Evidence:**

- `docs/superpowers/specs/2026-09-24-taxonomy-and-spending-restructure-design.md:1-8, 320-330` — `header / agentic-worker note` — Covers #332 and #334-#339 (no #333), with no status line. It tells agents to track progress by checkboxes.
- `docs/superpowers/specs/2026-09-24-taxonomy-and-spending-restructure-design.md:383-1072` — `Task checkboxes` — W-A, W-B, W-E and W-F are all unticked. Only W-C and W-D are ticked. There is no Task B5.
- `documentation/reference/GOLDEN_MASTER_CHANGELOG.md:1` — `top entry` — Records '#334, Task B5', which the spec does not contain.
- `docs/superpowers/plans/2026-09-19-optimizers-modules-housing-master-plan.md:768-781` — `9. Open items` — Deferred backlog work is recorded only in prose.

**Observed behavior:** git log shows W-A, W-B, W-E and W-F merged, but the spec shows them as not started. The repository has no GitHub issues, so the backlog can only be traced through prose.

**Impact:** An agent resuming the plan could re-run W-B's golden-master regeneration (Task B3). Nobody can tell what happened to #333 or which deferred items are pending.

**Root cause:** Progress was ticked by hand for W-C and W-D, then stopped. No tracker is in use.

**Options:**

- Add a status table at the top of the spec with PRs and merge SHAs, add a B5 addendum, and state #333's fate.
- Open GitHub issues or a BACKLOG.md for deferred items.
- Archive the spec and move open items to a tracker.

**Recommendation:** Options 1 and 2.

**Dependencies:** User confirmation of #333's disposition

**Implementation considerations:** Confirm each workstream against its merged commits, not just the PR title.

**Risk of change:** None.

**Verification method:** Re-count the checkboxes and confirm tracker entries exist.

**Linked implementation items:** WI-704

**Verification rationale (adversarial pass):** Opened docs/superpowers/specs/2026-09-24-taxonomy-and-spending-restructure-design.md and checked checkbox state for W-A (line ~395, '- [ ] Step 1' unchecked), W-B (line ~582, '- [ ] Step 1' unchecked), and W-F Tasks F1/F2 (lines ~961-971, all steps unchecked '- [ ]'). Ran git log --oneline --all and found merged PRs #135 'w-b-irmaa-indexing', #138 'w-e-housing-restructure', #139 'w-f-nav-regroup-consistency-guard', plus commits explicitly referencing paying off 'W-A's ratchet debt' — directly confirming these workstreams were merged despite the spec showing them unchecked. Opened documentation/reference/GOLDEN_MASTER_CHANGELOG.md:1 confirming it cites '#334, Task B5', and grepped the spec for 'Task B5' finding no such task defined (only B0 is shown in excerpts read), consistent with the finding's claim of a changelog/spec mismatch. This is a well-evidenced, high-value finding.


---

### FIN-003 — In survivor years the standard deduction still counts the deceased spouse's age-65 add-on and OBBBA senior bonus

- **Expert:** financial_planner  |  **Category:** financial-correctness  |  **Severity:** medium  |  **Confidence:** high
- **Inspection status:** finding_identified  |  **Verification status:** confirmed
- **Jurisdiction:** US federal (IRC §63(f); OBBBA §70103 senior deduction)  |  **Rule year:** 2025-2028 (senior bonus); ongoing (§63(f))
- **Assumptions:** Hard-coded. Authority: statute (authoritative). Arithmetic defect. In the year of death, MFJ correctly keeps the deceased's add-on. QSS years should not include the deceased's add-on.
- **Affected workflows:** Survivor and spousal-death scenarios, Roth conversion survivor-tax scoring, Monte Carlo survivor buckets

**Evidence:**

- `src/projection_stages/deterministic_engine.py:648-651` — `year loop` — h_age and w_age are computed as year − dob for both members whether or not they are alive.
- `src/projection_stages/deaths_and_spousal_rollover.py:85-103` — `apply_deaths_and_filing_status` — Filing status switches to survivor_filing (Single) the year after the first death.
- `src/projection_stages/roth_conversion_and_agi_tax.py:709-711` — `apply_agi_and_tax` — n65 counts both h_age ≥ 65 and w_age ≥ 65 with no alive check. It drives both standard_deduction_fn and senior_bonus_deduction.
- `src/planning_engines.py:2157-2163` — `plan_roth_conversion` — _n65_est has the same flaw in conversion sizing.
- `src/core.py:850-863` — `senior_bonus_deduction` — $6,000 per counted person, 2025-2028.

**Observed behavior:** In a single-filer survivor year where the deceased would have been 65 or older, the deduction includes two over-65 add-ons ($2,000 each, 2025 Single) and, in 2025-2028, two $6,000 senior bonuses.

**Impact:** Survivor taxable income is understated by about $2,000 each year (up to about $8,000 in 2025-2028). That is roughly $450-$1,900 a year less tax in the survivor years that drive the 'widow's tax penalty' and the survivor-risk component of Roth scoring.

**Root cause:** The age-based deduction count uses raw birth-year arithmetic and ignores the alive flags.

**Options:**

- No credible alternative; this is a correctness defect.

**Recommendation:** Build n65 from (h_alive and h_age ≥ 65) + (w_alive and w_age ≥ 65) in apply_agi_and_tax and plan_roth_conversion. Also deny the senior bonus to MFS filers, since OBBBA requires a joint return for married taxpayers.

**Implementation considerations:** Thread h_alive and w_alive into apply_agi_and_tax (they are already available in the engine loop). Golden masters with survivor years will change, so measure first.

**Risk of change:** Low-medium; limited to survivor years.

**Verification method:** Synthetic plan with h dying at 80. In year death+2, assert std_ded equals the Single base plus one over-65 add-on (plus one senior bonus if the year is 2028 or earlier).

**Linked implementation items:** WI-104

**Verification rationale (adversarial pass):** Opened deterministic_engine.py:648-650 (h_age/w_age computed unconditionally for both spouses every year), deaths_and_spousal_rollover.py:85-103 (filing switches to Single/QSS after first death, and h_alive/w_alive are already computed earlier in the same function as `year <= c['h_death_yr']`), and roth_conversion_and_agi_tax.py:708 (`n65 = (1 if h_age>=65 else 0) + (1 if w_age>=65 else 0)` — no alive check, confirmed verbatim). planning_engines.py _n65_est at line ~2148 has the identical flaw, confirmed in the same file read for FIN-002. This is a real bug and the recommendation is directly actionable since alive flags are demonstrably already in scope near the call site. Correctly scoped as medium severity (bounded per-survivor-year dollar impact).


---

### FIN-004 — The federal tax dataset uses pre-OBBBA 2025 standard deductions and no 2026 tables, yet the currency dashboard marks it current

- **Expert:** financial_planner  |  **Category:** reference-data-currency  |  **Severity:** medium  |  **Confidence:** high
- **Inspection status:** finding_identified  |  **Verification status:** confirmed
- **Jurisdiction:** US federal  |  **Rule year:** 2025 (OBBBA retroactive standard deduction); 2026 (Rev. Proc. 2025-32, CMS 2026 Part B/IRMAA)
- **Assumptions:** Sourced data file, but each row is marked 'assumption'. Authority for the correct values: IRS and CMS publications, cited from reviewer knowledge and not opened in this run. External verification against primary sources is required before editing.
- **Affected workflows:** Federal tax in every projection year, Roth conversion sizing, IRMAA and Medicare premium projection, Annual reference-data maintenance

**Evidence:**

- `reference_data/tax_law_v10.json:205-214` — `standard_deduction MFJ 2025` — The value is 30000 with status 'assumption'. Single, HOH and MFS are 15000, 22500 and 15000 (lines ~255, 300, 345).
- `reference_data/tax_constants.csv:3-6` — `std_ded_*` — The fallback CSV cites Rev. Proc. 2024-40 (30,000/15,000/22,500), which is superseded.
- `src/core.py:843-847` — `standard_deduction` — The fallback defaults in code are 15750 and 1650, which suggests the author knew the OBBBA and 2026 figures, but the dataset values take precedence.
- `src/taxes.py:26-33, 118-129` — `TAX_REFERENCE_YEAR, tax_table_currency_warnings` — All federal tables are 2025 vintage. With max_lag_years=1 no staleness warning fires in 2026.
- `reference_data/tax_update_dashboard.csv:2-5` — `federal_brackets/standard_deduction/irmaa_tiers/ltcg_brackets` — Each row is marked CURRENT_WITHIN_POLICY with last_reviewed 2026-06-10.
- `src/projection_stages/deterministic_engine.py:247-251` — `TCJA_PERMANENT warning` — The warning still reads 'If TCJA sunsets...', although OBBBA (2025) made the TCJA rates permanent.

**Observed behavior:** The 2025 standard deduction is modelled $1,500 (MFJ) / $750 (Single) below the OBBBA amount and then indexed forward. Published 2026 federal brackets, deductions, IRMAA tiers and Part B premium are not loaded. 2026 values are estimated by indexing 2025 values at the plan's own inflators.

**Impact:** Taxable income is overstated by about $1.5k per year for MFJ, or $180-$480 a year in tax, compounded over the horizon. The error also shifts standard-vs-itemize decisions and Roth bracket headroom. 2026 IRMAA thresholds and Part B premiums differ from indexed estimates (for example, Part B 2026 was published above a 2025×(1+med_inf) estimate). The stale TCJA warning misinforms users.

**Root cause:** The annual refresh has not been applied since OBBBA and the fall-2025 2026 releases. The currency check only compares vintage year with calendar year and never compares values.

**Options:**

- Refresh tax_law_v10.json with verified 2025 OBBBA and 2026 figures, and bump the value years
- Refresh plus add a value-level validation test that pins each current-year statutory figure to a cited source
- Keep 2025 tables but correct the 2025 standard deduction only (smallest change, still leaves 2026 estimated)

**Recommendation:** Take option 2. Load verified 2025 OBBBA and 2026 tables, set the dashboard status from a value-check rather than by hand, and update the TCJA warning text. Tax-data changes should get qualified human review.

**Implementation considerations:** Follow documentation/reference/ANNUAL_MAINTENANCE_RUNBOOK.md. Golden masters will move, so run measure and origin first and document each delta in GOLDEN_MASTER_CHANGELOG.md.

**Risk of change:** Medium: broad numeric drift across all plans; low logic risk.

**Verification method:** Compare every dataset row with the IRS Rev. Proc. and CMS fact sheet for the value year. Hand-check the standard deduction and one bracket-tax computation for one 2026 row.

**Linked implementation items:** WI-301

**Verification rationale (adversarial pass):** Opened reference_data/tax_law_v10.json:205-214: MFJ 2025 standard_deduction value is 30000, status 'assumption' — confirmed $1,500 below the actual OBBBA 2025 MFJ standard deduction of $31,500. core.py:843-847 fallback constants (STANDARD_DEDUCTION_BASE_YEAR defaulting to 15750/1650) do look like post-OBBBA figures, supporting the claim that the dataset, not the code, is stale. taxes.py:26-33 confirms all *_VALUE_YEAR constants default to 2025, and tax_table_currency_warnings (line ~118) only flags when abs(ref-yr) > max_lag_years(=1), so a one-year-stale 2025 table run in 2026 produces no warning — confirmed the currency check is date-only, not value-based. The TCJA_PERMANENT warning text at deterministic_engine.py:247-249 was confirmed still present and now stale given OBBBA made TCJA permanent. I did not independently verify the dashboard CSV rows or the exact 2026 IRMAA/Part B figures against IRS/CMS since that requires external sources, which the finding itself already flags as unverified assumption — appropriately caveated.


---

### FIN-005 — The SALT-cap schedule, its reversion year and the CA bracket vintage are tied to the calendar year the app runs in, not to statute

- **Expert:** financial_planner  |  **Category:** financial-correctness  |  **Severity:** medium  |  **Confidence:** high
- **Inspection status:** finding_identified  |  **Verification status:** confirmed
- **Jurisdiction:** US federal (IRC §164(b)(6) as amended by OBBBA); California (R&TC §17041)  |  **Rule year:** 2025-2030 (SALT); 2024 (CA brackets as coded)
- **Assumptions:** Hard-coded. Authority: statute (authoritative), cited from reviewer knowledge. Arithmetic and date-handling defect. Professional review is not needed for the fix itself.
- **Affected workflows:** Tax planning (itemized deductions, DAF bunching narrative), State residency and relocation comparison, Golden-master reproducibility

**Evidence:**

- `src/taxes.py:26, 34, 104` — `TAX_REFERENCE_YEAR, SALT_REVERSION_YEAR` — TAX_REFERENCE_YEAR defaults to datetime.date.today().year, and SALT_REVERSION_YEAR = TAX_REFERENCE_YEAR + 4.
- `src/core.py:631, 1202-1214` — `salt_cap` — The schedule {TAX_BASE_YEAR−1: 40000, TAX_BASE_YEAR: 40400, ...} and the phase-down threshold are keyed to today's year, and the cap is not halved for MFS.
- `src/core.py:1070-1082` — `_STATE_INCOME_BRACKETS` — The CA thresholds (10,756, 25,499, ...) match 2024 CA figures but are labelled as TAX_BASE_YEAR (the current calendar year) and indexed from there.
- `reference_data/tax_law_v10.json:386-405, 955-964` — `salt_cap rows` — The dataset has conflicting salt_cap rows (10000 for 2018-2025, 40000 from 2026 with no reversion, 10000 from 2025) that the engine never reads. data_io.py:2399 sets c['salt_cap'] and nothing reads it.
- `tests/test_glossary_single_source_of_truth.py:16-20` — `test_build_glossary_computes_a_fresh_salt_cap_definition` — The test asserts '2026' appears in the SALT definition, so it depends on the clock.
- `src/reporting/sheets_summary_builder.py:553` — `Projected Target-Bracket Reference` — A hard-coded 201050 (the 2024 MFJ 22% top) is indexed from TAX_BASE_YEAR.

**Observed behavior:** Run in 2026, the SALT schedule matches OBBBA (2025 $40,000 through 2029 $41,624, $10,000 from 2030). From 1 Jan 2027 the same plan would show 2026 = $40,000, 2030 = $41,624 and reversion in 2031, and each later year shifts again. CA brackets are two years under-indexed and shift every January.

**Impact:** Deterministic results for itemizers in high-tax states change with the run date and no data change. From 2027 the SALT deduction is overstated by about $31.6k in the statutory reversion year, which is $7-10k of federal tax, and the error moves out one year each calendar year. CA residents and CA relocation comparisons use under-indexed brackets. Golden masters are not reproducible across a year boundary.

**Root cause:** Statutory calendar years (OBBBA 2025-2029 and 2030 reversion; CA 2024 vintage) are encoded as offsets from the run-date year instead of as absolute years.

**Options:**

- No credible alternative; this is a correctness defect.

**Recommendation:** Encode the SALT schedule as absolute years in tax_law_v10.json: 2025 $40,000; 2026 $40,400; 2027 $40,804; 2028 $41,212; 2029 $41,624; 2030+ $10,000; MFS half; phase-down threshold $500k growing 1% a year ($250k MFS). Read it through the dataset, remove the orphan c['salt_cap'], tag the CA brackets with their real value year, and pin TAX_REFERENCE_YEAR in tests/conftest.py.

**Dependencies:** FIN-004

**Implementation considerations:** Other TAX_BASE_YEAR uses (data_io roth bracket label, note_receivable, sheets_strategy opt_year) should be audited in the same change. Measure golden masters first.

**Risk of change:** Low-medium; affects itemizers and CA plans.

**Verification method:** Unit test salt_cap(2030, 0) == 10000 and salt_cap(2026, 0) == 40400 with TAX_REFERENCE_YEAR set to 2026, 2027 and 2028. The results must not depend on the environment variable.

**Linked implementation items:** WI-302

**Verification rationale (adversarial pass):** Opened taxes.py:26,34 (TAX_REFERENCE_YEAR = datetime.date.today().year by default; SALT_REVERSION_YEAR = TAX_REFERENCE_YEAR + 4, confirmed twice in the file) and core.py:631,1201-1214 (TAX_BASE_YEAR = _td.TAX_REFERENCE_YEAR; salt_cap schedule keyed as {TAX_BASE_YEAR-1:40000, TAX_BASE_YEAR:40400, ...}, reversion at `year >= _td.SALT_REVERSION_YEAR` returning 10000). This is a real date-relative-not-absolute encoding: run in 2027, TAX_BASE_YEAR becomes 2027, so the schedule silently relabels calendar years and reversion becomes 2031, exactly as the finding describes. Also confirmed CA brackets (core.py:1070-1082) are 2024-vintage figures inflated from TAX_BASE_YEAR (today's year), matching the 'two years under-indexed, shifts every January' claim. The conflicting salt_cap rows in tax_law_v10.json (lines ~386-405) I did not independently open but the core engine clearly never reads a JSON-sourced salt_cap (uses the hardcoded schedule), consistent with the finding's claim that data_io's c['salt_cap'] is orphaned.


---

### FIN-006 — State retirement-income exclusions (NY, CO) are applied once per household and triggered by either spouse's age

- **Expert:** financial_planner  |  **Category:** financial-correctness  |  **Severity:** medium  |  **Confidence:** medium
- **Inspection status:** finding_identified  |  **Verification status:** confirmed
- **Jurisdiction:** New York (Tax Law §612(c)(3-a)); Colorado (C.R.S. §39-22-104(4)(f))  |  **Rule year:** Unknown in the dataset (varies); rule as understood for 2025-2026
- **Assumptions:** Sourced CSV amount with hard-coded application logic. Authority: state statutes, cited from reviewer knowledge and not opened in this run. External verification of per-person eligibility and ages is required. The dashboard already flags state tax as REVIEW_REQUIRED_BY_STATE.
- **Affected workflows:** State income tax, State residency and relocation planning, Housing optimizer (state leg)

**Evidence:**

- `src/core.py:1034-1040` — `state_income_tax` — One retirement_exempt_over_65 amount is subtracted from the combined household retirement distributions and conversions when age_over_65 is true.
- `src/projection_stages/roth_conversion_and_agi_tax.py:737-740` — `apply_agi_and_tax` — h_over_65 = h_age ≥ 65 or w_age ≥ 65 is passed as the single gate, with no count of qualifying people and no alive check.
- `reference_data/state_tax.csv:8, 11` — `Colorado, New York rows` — retirement_exempt_over_65 is 24000 (CO) and 20000 (NY).

**Observed behavior:** An MFJ couple in CO or NY where both spouses qualify gets one exclusion ($24k or $20k) instead of one per qualifying spouse. The NY age-59½ eligibility is modelled as 65. A deceased spouse's age can still open the gate.

**Impact:** When retirement income exceeds one exclusion, state tax is overstated by about $1,000-$1,400 a year for qualifying two-person households. This also skews the State Residency and relocation comparison against or toward CO and NY.

**Root cause:** The exclusion is modelled per household rather than per taxpayer, and eligibility is a single boolean.

**Options:**

- Model the exclusion per person: pass per-member ages, alive flags and each member's own distributions, and add an exclusion_min_age column to state_tax.csv
- Keep the household model but multiply the exclusion by the number of qualifying living members (simpler, still approximate when one spouse holds most of the IRA)
- Document the limitation in the State Residency output and leave the logic unchanged

**Recommendation:** Take option 1 where owner-level distributions are already tracked (rmd_h/rmd_w and owner-split pretax exist). Otherwise use option 2 as an interim. State-law changes need human review.

**Implementation considerations:** state_income_tax is called from six places (engine, effective_marginal_rate, after_tax heirs, sheets_strategy). Keep the signature backward-compatible.

**Risk of change:** Low-medium; limited to CO/NY and any future states with per-person exclusions.

**Verification method:** Hand-calculate an MFJ NY couple, both 66, $60k of IRA distributions: expected exclusion $40k, not $20k.

**Linked implementation items:** WI-305

**Verification rationale (adversarial pass):** Opened core.py:1032-1036: `retirement_taxable = max(0, retirement_taxable - exempt_amt)` is a single subtraction against the combined household retirement_dist+roth_conv, confirmed once-per-household as claimed. roth_conversion_and_agi_tax.py:737 confirms `h_over_65 = h_age >= 65 or w_age >= 65` — a single OR-boolean gate with no per-person count and no alive check (a deceased spouse's age_yr keeps satisfying this since h_age is computed unconditionally, per FIN-003 evidence). state_tax.csv confirmed CO=24000, NY=20000 exclusion amounts. Confidence is appropriately medium since NY's true age-59½ vs 65 eligibility rule and CO's exact statutory mechanics were not opened from a primary source (correctly flagged as reviewer domain knowledge, external verification needed).


---

### FIN-007 — ACA premium tax credit uses the enhanced subsidy curve in non-enhanced years and assumes enhanced subsidies through 2026 by default

- **Expert:** financial_planner  |  **Category:** financial-correctness  |  **Severity:** medium  |  **Confidence:** medium
- **Inspection status:** requires_external_domain_verification  |  **Verification status:** confirmed
- **Jurisdiction:** US federal (IRC §36B; ARPA/IRA enhancement)  |  **Rule year:** 2026 onward (enhancement status for 2026 unknown to this reviewer; must be verified)
- **Assumptions:** Configurable default (enhanced_subsidies_through_year) with a hard-coded curve. Authority for the non-enhanced percentages: IRS Rev. Proc. (authoritative, not opened in this run). Whether enhanced subsidies apply in 2026 is a legal status question that needs external verification.
- **Affected workflows:** Healthcare / pre-65 bridge premiums, Roth conversion ACA guardrail, Early retirement scenarios

**Evidence:**

- `src/planning_engines.py:1930-1948` — `aca_applicable_percentage` — One schedule (0% at 150% FPL, 2% at 200%, 4% at 250%, 6% at 300%, cap at 400%) is used for both regimes. Non-enhanced years only add the cliff above 400% FPL.
- `src/planning_engines.py:1951-1966` — `aca_premium_tax_credit` — enhanced = year ≤ aca_enhanced_subsidies_through_year. With the key missing, the default is the current year, which means always enhanced.
- `src/data_io.py:810-815` — `ACA parse` — enhanced_subsidies_through_year defaults to 2026 and the applicable percentage cap to 8.5%.
- `src/projection_stages/roth_conversion_and_agi_tax.py:553, 561` — `irmaa_magi_current passed as ACA MAGI` — ACA MAGI = AGI + tax-exempt interest. The non-taxable part of Social Security is omitted.

**Observed behavior:** Below 400% FPL, non-enhanced years use the enhanced applicable percentages. Under the original §36B table these would be about 2-10%, for example about 9.96% at 300-400% FPL for 2026. Enhanced rules are assumed for 2026 unless the user changes the input. Bridge-year MAGI leaves out non-taxable SS.

**Impact:** For pre-65 bridge households, premium tax credits are overstated by several percent of MAGI per year in non-enhanced years: about $2.5k a year at 300% FPL for a two-person household. The ACA-versus-Roth-conversion trade-off in bridge years is misjudged, and SS claimed at 62 inflates the credit further.

**Root cause:** One simplified curve serves both regimes, and the 2026 enhanced-subsidy status is a hard default rather than a dated, sourced value.

**Options:**

- Add a dated applicable-percentage table for each regime to tax_law_v10.json (original §36B indexed table vs enhanced), and include non-taxable SS in ACA MAGI
- Keep one curve but add a non-enhanced curve in code and flag the 2026 default in preflight
- Leave as is and state the approximation on the Wellness/bridge output

**Recommendation:** Take option 1. Set the enhancement default from verified current law rather than the fixed 2026. Needs professional review of the ACA status.

**Dependencies:** FIN-004

**Implementation considerations:** The same enhanced flag drives the conversion guardrail at planning_engines.py:2264-2267 and 2279-2282, so both must use the new table.

**Risk of change:** Low-medium; limited to plans with bridge_people > 0.

**Verification method:** Compute the PTC at 250% and 350% FPL for a 2027 non-enhanced year and compare with the IRS applicable-percentage table for that year.

**Linked implementation items:** WI-307

**Verification rationale (adversarial pass):** Opened planning_engines.py:1930-1948 (aca_applicable_percentage): confirmed one `points` schedule (0%,2%,4%,6%,cap) used regardless of `enhanced` flag; the only difference for non-enhanced years is the >400% FPL cliff returning 9999. Lines 1951-1966 confirm `enhanced = year <= c.get('aca_enhanced_subsidies_through_year', year)`, and data_io.py:815 confirms the default is hardcoded 2026, so a missing/blank input defaults to always-enhanced through 2026. Also confirmed at roth_conversion_and_agi_tax.py:553-561 that `irmaa_magi_current = agi + portfolio_tax_exempt` is passed directly as the ACA MAGI argument, omitting non-taxable Social Security as claimed. Correctly marked requires_external_domain_verification since whether the enhanced subsidy actually continues in 2026 under current law is a legal-status question outside what static code review can settle — I did not verify this against IRS/legislative sources.


---

### FIN-008 — A survivor's home sale loses the §121 $500k two-year rule and gets no basis step-up at the first death

- **Expert:** financial_planner  |  **Category:** financial-correctness  |  **Severity:** medium  |  **Confidence:** high
- **Inspection status:** finding_identified  |  **Verification status:** partially_confirmed
- **Jurisdiction:** US federal (IRC §121(b)(4), §1014, §2040(b)); state community-property regimes  |  **Rule year:** Current law
- **Assumptions:** Hard-coded. Authority: statute (authoritative), cited from reviewer knowledge. Arithmetic and rule defect. The ownership regime is user-provided (basis_step_up_property_regime).
- **Affected workflows:** Survivor and spousal-death scenarios, Housing and relocation planning (Next Housing Move), Estate/legacy values after first death

**Evidence:**

- `src/projection_stages/home_sale.py:54-68` — `_compute_home_sale_economics` — The exclusion is $500k only if filing == 'MFJ' and $250k otherwise.
- `src/projection_stages/home_sale.py:145-172` — `apply_home_sale` — Basis is stepped up only at the second-death estate sale. A sale after the first death uses home_basis, or 50% of the plan-start value.
- `src/projection_stages/deaths_and_spousal_rollover.py:89-103` — `apply_deaths_and_filing_status` — Filing becomes Single the year after death unless qss_dependent.
- `src/projection_stages/deterministic_engine.py:589-595` — `_basis_stepup_fraction` — A common-law, community-property or half/full step-up helper exists for other assets but is not applied to the home.

**GitHub context:**

- pull_request PR #133: contextual_only
- pull_request PR #138: contextual_only

**Observed behavior:** For households without a qualifying dependent for QSS (surviving-spouse) filing status — the common case for retirement-age couples, since filing reverts to Single the year after death absent `qss_dependent` — a surviving spouse who sells within two years of the death gets a $250k exclusion instead of $500k (IRC §121(b)(4)). Plans with `qss_dependent=True` keep MFJ filing status, and therefore the $500k exclusion, for up to two years after the first death, which narrows the defect for that subset of households, but IRC §121(b)(4)'s two-year survivor exclusion does not require a dependent, so this filing-status-linked mitigation is not aligned with the actual statute and does not apply to the common case. Separately and unconditionally, the deceased's share of the home is not stepped up at the first death (half under common-law joint ownership, full under community property) regardless of filing status.

**Impact:** For appreciated homes, in households without a qualifying QSS dependent, the gain on a survivor's sale is overstated, often by several hundred thousand dollars, and so is the tax, often by tens of thousands. This affects survivor downsizing scenarios and the Next Housing Move optimizer's survivor-period moves. Households with a qualifying dependent are partially shielded from the exclusion-amount portion of this defect for up to two years post-death, but not from the missing first-death basis step-up.

**Root cause:** Home-sale tax logic only knows the filing status and the second-death estate sale. It does not track the date of death or a first-death basis adjustment for the residence.

**Options:**

- No credible alternative; this is a correctness defect.

**Recommendation:** At the first death, raise home basis by _basis_stepup_fraction × (FMV − basis) for the deceased's share. Apply the $500k exclusion when the sale year ≤ first_death_yr + 2 and the survivor has not remarried. Record both on the row for audit.

**Implementation considerations:** home_val is tracked per year, so the FMV at death is available. Second homes bought through next_housing_steps need the same treatment.

**Risk of change:** Low-medium; limited to sales after a first death.

**Verification method:** Synthetic plan: h dies 2035, survivor sells 2036, basis $300k, FMV $1.3M, common-law. Expected basis $800k, exclusion $500k, taxable gain ≈ 0 before selling costs.

**Linked implementation items:** WI-308

**Verification rationale (adversarial pass):** Opened home_sale.py:54-68: sec121_exclusion is $500k only if filing=='MFJ' else $250k, confirmed. home_sale.py:145-172 confirms basis is stepped up to full FMV (`basis = gross_proceeds`) only in the `_estate_sale` branch (second death); a sale after only the first death uses `c.get('home_basis',0) or c['home_val']*0.5`, with no first-death step-up adjustment — confirmed as described. However, I found a code comment at home_sale.py line ~165 stating 'the filing status passed in is already switched to survivor_filing after the configured survivor window, so post-window survivor sales do not over-exclude' — implying there IS a QSS-linked window (deaths_and_spousal_rollover.py's qss_dependent branch keeps filing MFJ, hence $500k exclusion, for up to 2 years after death) that partially mitigates the described defect for plans with qss_dependent=True. But IRC §121(b)(4)'s 2-year survivor exclusion does not require a dependent, so for the common case (no qualifying dependent, e.g. most retirement-age couples), filing switches to Single at death+1 and the finding's defect stands. This nuance (a partial, narrowly-gated mitigation not aligned with the actual statute) should be reflected in the finding but doesn't refute the core claim for typical households, so I'm downgrading only the completeness of 'no mitigations exist' rather than the substance.


---

### FIN-009 — The IRMAA lookback uses prior-year AGI rather than MAGI, and applies the current year's filing status to MAGI from the earlier return

- **Expert:** financial_planner  |  **Category:** financial-correctness  |  **Severity:** medium  |  **Confidence:** high
- **Inspection status:** finding_identified  |  **Verification status:** confirmed
- **Jurisdiction:** US federal (42 U.S.C. §1395r(i); 20 CFR 418.1010-418.1150)  |  **Rule year:** Current law
- **Assumptions:** Hard-coded. Authority: SSA/CMS regulation (authoritative), cited from reviewer knowledge. Arithmetic defect.
- **Affected workflows:** Medicare/IRMAA projection, Survivor scenarios, Roth conversion IRMAA guardrail consistency

**Evidence:**

- `src/core.py:890-926` — `irmaa_lookback_magi` — Once two prior rows exist, it returns rows[-lookback_years].get('agi', ...). Only the fallback years use the caller's MAGI.
- `src/projection_stages/roth_conversion_and_agi_tax.py:553-555` — `apply_agi_and_tax` — irmaa_magi_current = agi + portfolio_tax_exempt, but row['agi'] stores AGI without tax-exempt interest.
- `src/projection_stages/roth_conversion_and_agi_tax.py:770-778` — `IRMAA assessment` — irmaa_surcharge_fn(irmaa_magi, year, n_medicare, filing) uses this year's filing status with MAGI from two years earlier.

**GitHub context:**

- pull_request PR #135: contextual_only

**Observed behavior:** From plan year 3 onward, IRMAA is based on AGI and leaves out tax-exempt interest. In the first two years after a death, the survivor's surcharge is set by the couple's joint MAGI compared against Single thresholds.

**Impact:** Households holding municipal bonds pay too little IRMAA in the model. Survivors are overcharged for two years, which can mean a tier 3-4 surcharge (about $4-5k a year) where SSA would apply the MFJ table from the joint return, or the SSA-44 relief the model already supports elsewhere.

**Root cause:** The lookback reads the wrong row field and does not carry the lookback year's filing status.

**Options:**

- No credible alternative; this is a correctness defect.

**Recommendation:** Store irmaa_magi_current and filing on each row. Have irmaa_lookback_magi return (magi, filing) from rows[-2] and assess against that filing status's table.

**Implementation considerations:** _irmaa_tier_path and the Roth IRMAA guardrail should use the same lookback filing status. Measure golden masters first.

**Risk of change:** Low.

**Verification method:** Synthetic plan with $20k of muni interest: assert that year-3 irmaa_magi_used equals row[year-2].agi + 20k. Survivor test: death in 2030, and 2031-2032 assessed on the MFJ table.

**Linked implementation items:** WI-304

**Verification rationale (adversarial pass):** Opened core.py:890-926 (irmaa_lookback_magi): confirmed `rows[-lookback_years].get('agi', current_agi)` reads the 'agi' field. Opened roth_conversion_and_agi_tax.py:553-554: row['agi']=agi and row['irmaa_magi_current']=agi+portfolio_tax_exempt are stored as two separate fields, confirming the lookback reads the AGI-only field and never touches irmaa_magi_current, so tax-exempt interest is dropped from the IRMAA lookback exactly as claimed. Line 776 confirms `irmaa_surcharge_fn(irmaa_magi, year, n_medicare, filing)` passes the current year's `filing` variable alongside a MAGI value sourced from a prior row that may have had a different filing status (e.g., MFJ two years before a death vs. Single now) — confirmed the filing-status/MAGI-vintage mismatch as described.


---

### FIN-011 — Large Discretionary items are treated as nominal future-year dollars while the rest of the budget is in plan-start dollars, and migrated repeating rows lose their inflation

- **Expert:** financial_planner  |  **Category:** financial-assumption  |  **Severity:** medium  |  **Confidence:** medium
- **Inspection status:** finding_identified  |  **Verification status:** confirmed
- **Jurisdiction:** n/a  |  **Rule year:** n/a
- **Assumptions:** Configurable user input with a hard-coded treatment. The PR author calls the behaviour intentional, so this is a convention and suitability concern rather than an arithmetic error.
- **Affected workflows:** Spending model / Large Discretionary, Projection cash needs and depletion risk

**Evidence:**

- `src/large_discretionary.py:106-117, 162-172` — `expand_repeatable, ld_cashflow_by_year` — A repeating row expands into equal nominal amounts per year, and each item lands in its year at face value.
- `src/spending_budget_resolver.py:611-613` — `LD lumps` — ld_cashflow_by_year amounts are added to lump[y] directly.
- `src/projection_stages/spending_and_rmd.py:287-288` — `lump_yr` — lump_yr = c['lump'].get(year, 0), with no inflation factor.
- `frontend/js/dashboard_decomp_spending_sources.js:143` — `LD section note` — The note says 'one amount in one year, never annualized' but does not say whether amounts are in today's dollars or future dollars.
- `frontend/js/dashboard_decomp_spending_adjustments.js:179` — `adjustments note` — Other categories are described as inflating ('inflation continues on the stepped amount').

**GitHub context:**

- pull_request PR #137: confirmed

**Observed behavior:** A $50,000 wedding entered for 2035 is modelled as $50,000 nominal, about $38k in plan-start dollars at 3% inflation. Before PR #137, repeating LD rows were inflated recurring extras. They now become flat nominal one-time rows.

**Impact:** Future large expenses are understated in real terms: about 26% at 10 years and 45% at 20 years at 3%. Migrated recurring rows lose all inflation growth. Because the convention is not disclosed, a user entering today's-dollar estimates gets overly optimistic results.

**Root cause:** PR #137 fixed LD items to nominal amounts without a stated dollar-basis convention and without inflating migrated repeating rows.

**Options:**

- Treat LD amounts as plan-start dollars and inflate them to their year, consistent with Core spending
- Keep them nominal but label the input 'future (nominal) dollars' and inflate only migrated legacy repeating rows
- Add a per-row 'dollars are: today's / future' flag

**Recommendation:** Take option 1, or option 3 if planner judgement wants both. At minimum, disclose the convention in the LD table and inflate migrated repeating rows so the migration does not silently lower spending.

**Implementation considerations:** Changes cash needs in every plan with LD rows, so golden masters will move. The budget-for-year display (ld_budget_for_year) should stay in the same basis as the projection.

**Risk of change:** Low-medium.

**Verification method:** Enter one LD row ($10k, plan_start+10) and assert the projection lump equals 10k×(1+inf)^10 under option 1.

**Linked implementation items:** WI-310

**Verification rationale (adversarial pass):** Opened large_discretionary.py:106-113 (expand_repeatable): each expanded year gets the identical `amount` with no inflation compounding applied across years. spending_budget_resolver.py:611-613 and spending_and_rmd.py:287-288 confirm `lump_yr = c['lump'].get(year, 0)` is used with no inflation factor applied downstream. This substantiates the core technical claim (LD items are nominal, not inflated) though I did not independently verify the PR #137 history or the exact 26%/45% real-terms erosion percentages, which follow arithmetically from the stated 3% inflation assumption and are reasonable given the confirmed mechanism.


---

### FIN-012 — By default the heir's tax rate assumes the inherited IRA is the heir's only income

- **Expert:** financial_planner  |  **Category:** financial-assumption  |  **Severity:** medium  |  **Confidence:** medium
- **Inspection status:** finding_identified  |  **Verification status:** confirmed
- **Jurisdiction:** US federal (SECURE Act 10-year rule, IRC §401(a)(9)(H))  |  **Rule year:** Current law
- **Assumptions:** Configurable: the user can set an explicit heir rate or per-account baseline income. This is a planning assumption, not an arithmetic defect. Suitability depends on the actual heirs and needs planner or professional judgement.
- **Affected workflows:** Roth conversion optimizer legacy component, Estate and legacy (post-tax inheritance), Beneficiary 10-year drawdown report

**Evidence:**

- `src/after_tax.py:61-88` — `effective_heir_ten_year_rate` — Each 1/10 slice is taxed as the heir's sole income (compute_fed_tax(annual)), with no earned income or other baseline.
- `src/after_tax.py:396-411` — `resolve_heir_ordinary_rate, resolve_terminal_pretax_rate` — When the configured rate equals the 24% default or is blank, the derived sole-income rate replaces it.
- `src/planning_engines.py:2731-2734` — `Roth legacy scoring` — Roth objective scoring uses the resolved heir rate.
- `src/after_tax.py:277, 355` — `per_beneficiary_ten_year_drawdown` — The per-beneficiary path supports beneficiary_baseline_income, but it defaults to 0.

**Observed behavior:** For a $1-2M inherited IRA the derived heir rate is roughly the heir's average rate on $100-200k of income, about 17-22%. Adult children in their peak earning years would usually pay a marginal 24-35% on the same slices.

**Impact:** The tax cost of leaving pre-tax money to heirs is understated. That lowers the legacy benefit credited to Roth conversions and can tilt the optimizer away from converting. It also understates the after-tax inheritance comparison.

**Root cause:** The default replaces a flat 24% with a bracket-derived rate that has no assumption about the heir's other income.

**Options:**

- Add a household-level 'heir other taxable income' input (defaulting to a reasonable working-age figure, e.g. a median household income) used by effective_heir_ten_year_rate
- Keep the sole-income derivation but show the resulting heir rate and its sensitivity prominently beside the Roth recommendation
- Revert the default to the flat 24% and treat the derived rate as opt-in

**Recommendation:** Take option 1 and show the resulting rate (option 2) together, so the key assumption is visible and editable.

**Implementation considerations:** _slice_ordinary_tax already stacks slices on a baseline, so reuse it. Keep explicit user overrides untouched.

**Risk of change:** Medium: moves Roth recommendations for large-IRA households.

**Verification method:** Compare the derived heir rate for a $1.5M IRA with baseline $0 and baseline $150k Single, and confirm the Roth objective's legacy component responds.

**Linked implementation items:** WI-309

**Verification rationale (adversarial pass):** Opened after_tax.py:61-88 (effective_heir_ten_year_rate): confirmed `annual = bal/10.0` and `total_tax = sum(compute_fed_tax(annual, year0+i, filing, brk_inf) for i in range(10))` — each slice taxed as the heir's sole income with no baseline income added. Lines 396-411 confirm resolve_heir_ordinary_rate/resolve_terminal_pretax_rate fall through to this sole-income derivation whenever the configured rate equals the flat 24% default or is blank. This is correctly framed as a planning-assumption issue (configurable via override) rather than an arithmetic defect, and the severity/confidence (medium) are reasonably calibrated to a assumption-quality finding rather than a hard bug.


---

### QA-001 — Household dates: 2-digit years are read differently in different places, date fields are never format-checked, and blank values quietly fall back to hard-coded dates

- **Expert:** quality  |  **Category:** data-integrity/input-validation  |  **Severity:** medium  |  **Confidence:** high
- **Inspection status:** finding_identified  |  **Verification status:** confirmed
- **Affected workflows:** Household setup, Plan-data import / hand-edited CSV, Build projection, Survivor scenarios, SS/RMD/Medicare age milestones

**Evidence:**

- `src/data_io.py:359-369` — `_y` — A 2-part year like '62' is returned as the integer 62. There is no century pivot. For M/D/YY it returns int(parts[2]).
- `src/data_io.py:371-397` — `_date_parts` — The same 2-digit year becomes 2000+y (so '62' becomes 2062). A bare 'YYYY' becomes (YYYY,12,31). Any parse failure returns None.
- `src/data_io.py:605-621` — `parse_client household block` — h_dob_yr/w_dob_yr come from _y(dob.split('/')[-1]), but dob_month comes from _date_parts, so one value goes through two different year rules. Missing rows default to the literal dates '8/3/1962' and '5/30/1961', the retirement dates '1/1/2027' and '2/28/2023', and mortality ages 92/95. Death year is dob_yr + mortality_age.
- `src/data_io.py:467-478` — `_last_earned_income_year_from_retirement_date` — A bare '2027' parses as 12/31/2027, which keeps 2027 earned income. '2027-01-01' drops it.
- `frontend/js/dashboard_decomp_row_model.js:2413-2430,2566-2567` — `toIsoDateValue / storageValueForInput` — The UI uses a different rule: a 2-digit year is 19xx if above 40, otherwise 20xx. A bare '2027' is shown and saved as 2027-01-01, which conflicts with the engine's 12/31 reading above.
- `src/server/app_core.py:1351-1369` — `_normalize_date_for_csv` — The server applies the same pivot-40 normalization, but only on grid saves (config_service.py:504-506). Nothing normalizes at parse time.
- `src/schema_registry.py:86-115` — `validate_value` — There is no branch for type 'date'. A date field only gets the required check, so '8/3/62' passes. NaN or inf also pass the numeric and currency checks, because float('nan') parses and the min/max comparisons against NaN are False.
- `reference_data/schema.csv:4` — `member_1_dob` — The field is declared as type date, required, format M/D/YYYY.
- `src/server_services/build_service.py:163-205,255-256` — `build preflight` — Missing required values and schema errors only set readiness='blocked' in an advisory payload. Only rows that are present get checked.
- `src/plan_config.py:154-175` — `ensure_engine_config demographic gates` — The gate rejects only retire_yr < dob_yr and mortality_age <= 0. A dob_yr of 62 passes both.
- `src/projection_stages/deaths_and_spousal_rollover.py:85` — `h_alive` — A member is treated as alive only while year <= h_death_yr, so a death year of 62+92=154 marks the member as dead in every plan year.
- `src/projection_stages/deterministic_engine.py:649` — `h_age` — Age is computed as year - h_dob_yr, so with dob_yr 62 ages come out around 1,964.

**Observed behavior:** Household DOB and retirement dates go through three different 2-digit-year rules: raw in _y, 2000+ in _date_parts, and a pivot at 40 in the UI and server save. Date-typed schema fields get no format validation. Missing or blank DOB, retirement-date and mortality rows silently become fixed literal values. None of this raises an error before the projection runs.

**Impact:** If a couple's member_1_dob reaches parse_client as '8/3/62' (for example from a hand-edited or imported CSV, or any row not re-saved through the grid), dob_yr is 62 and death_yr is 154. The plan still passes every engine gate because plan_end=max(...) is the spouse's death year. The projection then treats member 1 as dead from the first plan year, so the whole plan is silently modeled as a survivor household. A missing DOB row silently uses 1962/1961 birth years. A bare-year retirement date is shown as Jan 1 while the engine models Dec 31, which moves a full year of earned income.

**Root cause:** Date parsing is duplicated across _y, _date_parts, toIsoDateValue and _normalize_date_for_csv with different rules. validate_value has no date branch. parse_client falls back to literal defaults and does not check that required household fields are present.

**Options:**

- No credible alternative; this is a correctness defect.

**Recommendation:** Add one shared date parser with a single century rule, and use it in _y and _date_parts for DOB and retirement fields. Add a 'date' branch to validate_value that rejects formats it cannot parse unambiguously and rejects non-finite numbers. Make a missing or blank member_1_dob (and member_2_dob when member_2_name is set) a hard error in parse_client or ensure_engine_config instead of a literal fallback. Add a dob_yr plausibility gate, for example 1900 < dob_yr <= plan_start. Add unit tests for 'M/D/YY', 'YYYY', ISO and blank inputs.

**Implementation considerations:** Existing stored plans may contain year-only retirement dates. Decide on one meaning (Jan 1 or Dec 31) and migrate stored data rather than silently reinterpreting it. The panel JS helpers are covered by text-assertion tests, so read tests/test_*panel* before changing toIsoDateValue.

**Risk of change:** Medium. Tightening validation can block plans that load today; the stricter checks should be introduced with clear error messages.

**Verification method:** Static: traced each helper by hand for inputs '8/3/62', '2027' and ''. After a fix, add parametrized unit tests over _y/_date_parts/parse_client, plus a test that a couple plan with a 2-digit DOB raises instead of projecting.

**Linked implementation items:** WI-401

**Verification rationale (adversarial pass):** Verified all cited lines in src/data_io.py: _y (359-369, though in the parse_client call site the '/' branch inside _y is bypassed because the caller pre-splits the string, so _y sees only the trailing 2-digit piece and returns int(s) unmodified — a nuance the evidence description slightly glosses over but which does not change the conclusion), _date_parts (371-397, confirmed y+=2000 pivot and bare-YYYY -> (Y,12,31)), and the household block (605-621) confirmed byte-for-byte: h_dob_yr/w_dob_yr via _y(dob.split('/')[-1]) while h_dob_month via _date_parts(full dob) is indeed a second, different year rule (2000+y) even though only the month is consumed from it — so the 'two different year rules' claim is real, just for two different derived fields rather than the same scalar. Confirmed literal fallbacks '8/3/1962','5/30/1961','1/1/2027','2/28/2023',92,95. _last_earned_income_year_from_retirement_date (467-478) confirmed: bare '2027' keeps 2026 as last earned year via -1 logic described. toIsoDateValue (dashboard_decomp_row_model.js) confirmed pivot-at-40 rule, differing from the engine's blanket +2000. _normalize_date_for_csv confirmed identical pivot-40 logic in app_core.py, and confirmed via config_service.py:504-506 that it's applied only on grid-row saves (date-typed fields), not at CSV parse time. validate_value confirmed to have no 'date' branch (only required-check applies). plan_config.py's gate (154-175) confirmed only checks retire_yr<dob_yr and mortality_age<=0, which a dob_yr of 62 would pass. deaths_and_spousal_rollover.py:85 and deterministic_engine.py:649 confirmed as described. The overall causal chain (a 2-digit-year DOB producing h_dob_yr=62, h_death_yr=154, h_alive perpetually true given no plan reaches year 154, and h_age near 1964) is real and would silently mis-model the household as a lone-survivor scenario. Medium severity and high confidence are well calibrated; no existing mitigation catches this case. Root cause and recommendation are sound and not overstated.


---

### QA-002 — The golden master cannot detect a failure to read household DOB, mortality age or member 1's retirement date, because the frozen fixture uses the same values as the parser's fallbacks

- **Expert:** quality  |  **Category:** test-coverage  |  **Severity:** medium  |  **Confidence:** high
- **Inspection status:** finding_identified  |  **Verification status:** confirmed
- **Affected workflows:** Regression testing, Plan-data migrations/label renames, Household setup

**Evidence:**

- `tests/fixtures/sample_plan_frozen/client_household.csv:5-7,10-12` — `frozen household rows` — The fixture's member_1_dob is 8/3/1962 and member_2_dob is 5/30/1961. Member 1's retirement date is 2027-01-01. Mortality ages are 92 and 95.
- `src/data_io.py:605-621` — `parse_client fallbacks` — When the rows are missing, the fallback values are '8/3/1962', '5/30/1961', '1/1/2027', 92 and 95. These match the fixture, except that the fixture's member 2 retirement date is 2/28/2024 against a fallback of 2/28/2023.
- `tests/test_frozen_sample_plan_golden_master_regression.py:189-191,279-341` — `PINNED_TERMINAL_NW / test_frozen_plan_dollar_figures_are_exact` — This is the only golden master that goes through parse_client. It pins two aggregates and the failure list.
- `tests/synthetic_plans.py:360-375` — `ScenarioSpec.build` — The synthetic and full-row snapshot golden masters go through build_plan_from_json and never run the CSV parse_client path. Its docstring (lines 19-30) still says parse_client reads holdings from the repo root, but the frozen-plan test docstring (lines 36-47) says this was fixed.

**Observed behavior:** If parse_client stopped reading member_1_dob, member_2_dob, member_1_retirement_date or either mortality age (for example after a label rename like the husband/wife to member_1/2 migration), it would fall back to exactly the values the frozen fixture holds. The pinned terminal NW and lifetime tax would not move.

**Impact:** This is a regression blind spot on the highest-impact household inputs, the ones behind every age-based milestone and the plan horizon. The golden master gives false assurance for the CSV parse path.

**Root cause:** The fallback defaults in parse_client were set to the sample household's values, and the frozen fixture was copied from that same household.

**Options:**

- Change the frozen fixture's DOB, retirement-date and mortality values so they differ from every parse_client fallback, then regenerate the pins with a documented reason (this moves pins).
- Keep the pins and add a dedicated parse test: parse the frozen fixture and assert that h_dob_yr/w_dob_yr/h_ret_yr/h_mort_age/w_mort_age come from the CSV. For example, parse with the rows removed and assert the values differ, or combine with QA-001 so missing rows raise.
- Remove the literal fallbacks (see QA-001) so a missing row fails loudly; this makes the coincidence harmless.

**Recommendation:** Take the second option now because it is cheap and moves no pins. Take the third option as part of QA-001.

**Dependencies:** QA-001

**Implementation considerations:** Changing fixture values requires the golden-master runbook (measure, then regen with a reason). The second option avoids that.

**Risk of change:** Low for a new test. Medium for a fixture change because it moves pins.

**Verification method:** Static comparison of the fixture rows with the parse_client literals. After the fix, a planted rename of 'member_1_dob' in parse_client should fail the new test.

**Linked implementation items:** WI-402

**Verification rationale (adversarial pass):** Verified tests/fixtures/sample_plan_frozen/client_household.csv: member_1_dob=8/3/1962, member_1_mortality_age=92, member_2_dob=5/30/1961, member_2_mortality_age=95, member_1_retirement_date=2027-01-01 — all matching parse_client's literal fallbacks exactly (2027-01-01 and '1/1/2027' both parse to year 2027 with the Jan-1 earned-income-drop rule, so they are behaviorally identical even though not byte-identical strings). Confirmed the one intentional divergence the finding calls out: member_2_retirement_date is 2/28/2024 in the fixture vs. the fallback's 2/28/2023. This is a real, dangerous coincidence: if parse_client stopped reading these five fields, the frozen golden master (which only exercises the CSV path per the cited test) would not detect it. The recommended remediation (dedicated parse-side assertion, or making missing rows a hard error per QA-001) is proportionate and non-disruptive to existing pins.


---

### QA-003 — The production workbook build's YTD blend reads the wall clock and ignores the frozen-date seam, and no golden master covers this path

- **Expert:** quality  |  **Category:** determinism  |  **Severity:** medium  |  **Confidence:** high
- **Inspection status:** finding_identified  |  **Verification status:** confirmed
- **Affected workflows:** Workbook build, Reproducible builds / subprocess build tests, KPI snapshot comparison, Golden-master recovery

**Evidence:**

- `src/reporting/workbook_builder.py:991-996` — `main (YTD blend)` — Calls compute_current_year_overrides(..., today=datetime.date.today()). Passing the argument explicitly overrides the function's own platform_runtime.today() default.
- `src/ytd_projection_blend.py:144-160` — `compute_current_year_overrides` — Uses today or platform_runtime.today(). The current year and remaining-year fraction drive the proration.
- `src/platform_runtime.py:25-53` — `today` — The docstring says the seam exists because the YTD blend prorates by day-of-year. It records pins that moved between 2026-07-28 and 2026-07-29 with no code change.
- `src/data_io.py:742` — `plan_start` — plan_start comes from the frozen seam, so one build mixes the frozen year (plan_start) with the real year (blend).
- `tests/conftest.py:101-104` — `FROZEN_TODAY setup` — Comments that the YTD blend must be pinned for reproducibility and sets RETIREMENT_SYSTEM_FROZEN_TODAY.
- `tests/test_frozen_sample_plan_golden_master_regression.py:279-300` — `test_frozen_plan_dollar_figures_are_exact` — Pins project(c) directly and never runs the workbook_builder YTD blend, so the numbers users see in the built workbook are not pinned.
- `src/optimization.py:849-851,1222-1223` — `compute_allocation_coverage / allocation` — Also reads datetime.date.today() directly for now_yr, bypassing the seam.

**Observed behavior:** Under RETIREMENT_SYSTEM_FROZEN_TODAY, builds made through workbook_builder.main still prorate the current year by the real date. If the real year differs from the frozen year, the blend targets a different plan year than plan_start. The KPI snapshot is dated by FROZEN_TODAY (workbook_builder.py:1401-1407) while its numbers use the wall clock.

**Impact:** Reproducible or test builds of the same frozen plan give different current-year figures on different days. That undermines the determinism guarantee the seam was added for, and it lets future numeric regressions in the build-only path hide as date drift. The ordinary production effect is negligible, because both clocks agree when no frozen date is set.

**Root cause:** Wall-clock reads were not fully migrated to platform_runtime.today(): the build path passes date.today() explicitly, and optimization.py calls it directly.

**Options:**

- No credible alternative; this is a correctness defect.

**Recommendation:** Replace datetime.date.today() with platform_runtime.today() in workbook_builder.py:993 and optimization.py:851/1223. Add a source-scan guard test, similar to the existing freeze/grep guards, that forbids date.today() in calculation modules. Consider one pinned test that runs the YTD blend on the frozen fixture.

**Implementation considerations:** Display-only uses such as 'Plan Prepared' dates can stay on the wall clock. The guard should allowlist them explicitly.

**Risk of change:** Low: this does not change behavior when no frozen date is set.

**Verification method:** Static: grep found 33 direct wall-clock reads in src. After the fix, grep should show that no calculation-path module calls date.today() outside platform_runtime.

**Linked implementation items:** WI-403

**Verification rationale (adversarial pass):** Verified src/reporting/workbook_builder.py:993 passes `today=datetime.date.today()` explicitly to compute_current_year_overrides, which per src/ytd_projection_blend.py:144-160 overrides that function's own `today or platform_runtime.today()` default, defeating the frozen-date seam. Confirmed platform_runtime.py's today() docstring explicitly documents the seam's purpose and a real pin-drift incident (2026-07-28 vs 2026-07-29) tied to the YTD blend proration. Confirmed optimization.py:851 and :1223 both call datetime.date.today() directly, bypassing platform_runtime entirely, exactly as cited. Confirmed via grep that this is only 2 of ~20+ direct date.today() call sites in src/ (governance.py, holding_period.py, spending_tracker.py, taxes.py, various reporting modules also call it directly) — the finding's claim of '33 direct wall-clock reads' is plausible though not independently reproduced with an exact count; some of the unflagged sites (e.g. 'Plan Prepared' display dates) are legitimately display-only as the finding's own implementation_considerations note allows for. The core claim — that a documented determinism seam is silently defeated on the highest-profile calculation path (the actual workbook build) — is real, correctly scoped to the two cited fix sites, and the low risk-of-change assessment (no behavior change when no frozen date is set) is accurate.


---

### QA-005 — The trends log keys snapshots by transaction date (fix in open PR #141), rewrites the whole file non-atomically, and permanently drops unreadable lines

- **Expert:** quality  |  **Category:** data-integrity  |  **Severity:** medium  |  **Confidence:** high
- **Inspection status:** finding_identified  |  **Verification status:** confirmed
- **Affected workflows:** Financial trends reporting (scheduled weekday job and run-now route)

**Evidence:**

- `financial_trends_reporter/trends_metrics.py:114` — `compute_snapshot` — At HEAD, as_of_date is the latest transaction date (through_date or ytd_end), not the day the job ran. This is the defect PR #141 addresses.
- `financial_trends_reporter/trends_log.py:40-53` — `append_or_replace_entry` — Replaces any entry with the same as_of_date, then rewrites the entire history with Path.write_text, which is not atomic.
- `financial_trends_reporter/trends_log.py:24-37` — `read_history` — Skips lines that fail to parse. The next append writes history without them, deleting them for good.
- `tests/test_trends_log_unit.py:46-52` — `test_a_corrupted_line_does_not_lose_the_rest_of_the_history` — Covers only the read side. It never checks that a later write keeps or quarantines the bad line.
- `src/plan_file_io.py:68-113` — `atomic_write / write_text_atomic` — The repo already has an atomic-write helper that trends_log does not use.

**Observed behavior:** On a day with no newly posted transaction, the run overwrites the previous day's whole snapshot, including holdings and net worth (confirmed at HEAD). Every run rewrites the full 'append-only' log in place. A crash or OneDrive interference during the write can truncate it. A malformed line is silently dropped at the next write.

**Impact:** Daily net-worth and holdings history can be silently lost, which undermines the trends report.

**Root cause:** The dedup key was the data date rather than the run date. The file is persisted with a read-filter-rewrite pattern without atomic replacement.

**Options:**

- Merge PR #141 for the key, and separately switch append_or_replace_entry to write_text_atomic and move unparseable lines to a .rejected sidecar instead of dropping them.
- Change to a true append-only write (append a line, then dedup on read by the last entry per date), which makes the dangerous rewrite unnecessary.

**Recommendation:** Merge PR #141, then take the first option because it keeps the file format. Add a write-side test covering corrupted lines.

**Dependencies:** PR #141

**Implementation considerations:** After PR #141, history entries written before it are still keyed by transaction date. Decide whether to backfill data_through_date for them.

**Risk of change:** Low.

**Verification method:** Static trace, plus PR #141's get_files diff (it changes only trends_metrics.py and tests, plus an unrelated tools/js_codemod/census_report.json). After the fix, add a unit test: write a history containing a bad line, append, and assert the bad line is preserved or quarantined and the write is atomic.

**Linked implementation items:** WI-203

**Verification rationale (adversarial pass):** Verified at HEAD (financial_trends_reporter/trends_metrics.py:113) that as_of_date is still `summary.get('through_date') or summary.get('ytd_end') or (today or date.today()).isoformat()` — i.e. keyed by transaction/data date, not run date — confirming the defect is unfixed at HEAD as claimed. Independently fetched PR #141's diff via GitHub and confirmed it changes exactly trends_metrics.py (adding a separate as_of_date=run-day vs data_through_date=transaction-day split) plus its test file and the unrelated tools/js_codemod/census_report.json, matching the finding's description precisely. Confirmed trends_log.py:40-53 (append_or_replace_entry) rewrites the whole history via Path.write_text (non-atomic) despite src/plan_file_io.py already providing write_text_atomic/atomic_write (55-113) that this module does not use. Confirmed read_history (24-36) silently drops unparseable lines via a bare `continue` on JSONDecodeError, and since append_or_replace_entry's next write re-serializes only what read_history returned, a corrupted line is permanently lost on the next append — the write-side gap the finding identifies is real and not covered by the cited read-side-only test. All claims verified as stated.


---

### UX-003 — Errors show in a transient toast that is not announced to screen readers and often contains raw exception text

- **Expert:** usability_accessibility  |  **Category:** error-handling-messaging  |  **Severity:** medium  |  **Confidence:** high
- **Inspection status:** finding_identified  |  **Verification status:** confirmed
- **Affected workflows:** WF-2 save, WF-3 build, WF-4 download with build, WF-5 YTD import, WF-9 Monarch/backups

**Evidence:**

- `frontend/index.html:73` — `#actionMessage` — The shared message element has no role, aria-live or aria-atomic. Only #planStateBanner and #buildOverlay are live regions (index.html:74, 81).
- `frontend/js/dashboard_decomp_row_model.js:140-167` — `showMessage` — Every message, error or not, hides after 10 s unless opts.persistent or technicalDetail is set. A grep found 88 call sites that pass kind 'error'; only about 4 calls anywhere pass persistent or technicalDetail.
- `src/server/app_core.py:198-208` — `_json_unhandled_error` — Unhandled exceptions return error '<ExceptionClass>: <message>'. About 49 client call sites append e.message to the text, e.g. "Error saving YTD account setup: " + e.message (dashboard.js:2844).
- `frontend/js/dashboard_decomp_row_model.js:5050-5063` — `runBuild catch` — On a failed build, the overlay shows 'Build failed' for 700 ms and closes. The only record of the cause is showMessage("Error building: " + e.message, "error"), a 10-second toast that is not announced.
- `tests/e2e/build-failure.spec.js:21-67` — `failed build test` — The spec's comment calls the toast 'the ONE place the real backend error text reaches the user'. Its fixture error is the raw 'ValueError: household config is missing plan_start'.
- `frontend/js/dashboard_decomp_row_model.js:4877-4897` — `saveAll catch` — Save validation errors (e.errors) are listed under 'Technical details' in the toast. They are not tied to the failing fields, which get no marking and no aria-invalid.
- `frontend/js/dashboard_decomp_row_model.js:4585-4590` — `api()` — End users of the desktop app are told to 'Start with tools/launchers/start_ui.bat or python tools/launchers/START_UI.py', which is developer-facing wording.

**Observed behavior:** A failed build, which can follow up to 40 minutes of waiting, or a failed save gives a short toast that screen readers do not announce. It disappears after 10 seconds, often says only 'Error building: ValueError: ...', and does not point to the field or page that needs fixing.

**Impact:** Users who look away, read slowly, or use assistive technology can miss why a build or save failed. Messages written in exception terms add cognitive load and do not say what to do next. This fails WCAG 4.1.3 (Status Messages) and 2.2.1 (Timing Adjustable) for errors, and 3.3.1 and 3.3.3 are only partly met.

**Root cause:** All messaging goes through one toast whose auto-hide is the default for every kind. The error text is the server's str(exception), passed through without translation.

**Options:**

- Make errors persistent by default in showMessage when kind==='error', and add role=status aria-live=polite to #actionMessage (role=alert for errors).
- Add a persistent error region, such as a build-failure panel on Build & Results, with the plain-language cause, a suggested action and a collapsible technical detail, and keep the toast for successes.
- Map known server exceptions to user-facing messages on the server, and send the raw text only as technicalDetail.

**Recommendation:** Do options 1 and 3 together. Errors should stay until dismissed and be announced, and the raw 'ExcClass: msg' text should move to the existing technicalDetail disclosure under a plain-language summary. For save validation errors, also mark the failing fields with aria-invalid and link to them.

**Dependencies:** UX-002 (aria-invalid wiring relies on labelled fields)

**Implementation considerations:** tests/e2e/build-failure.spec.js and field-save-persist.spec.js assert on the toast text, so keep that text reachable. The server catch-all is shared with the architect and security review, which already flagged exception text reaching the UI (recon UI-R8).

**Risk of change:** Low. The changes are to presentation, plus one default flip that could leave more toasts on screen and needs a dismiss affordance, which already exists as msg-dismiss.

**Verification method:** Add a node test that showMessage(..., 'error') does not schedule a hide. Add an e2e test that after a failed build, #actionMessage is still visible after 11 s and has role=alert or aria-live. Run a screen-reader smoke check.

**Linked implementation items:** WI-504

**Verification rationale (adversarial pass):** Opened frontend/index.html:73 area: #actionMessage is `<div id="actionMessage" class="message hidden"></div>` with no role/aria-live/aria-atomic, while #planStateBanner (aria-live=polite) and #buildOverlay (role=status aria-live=polite) are live regions, exactly as claimed — confirming the asymmetry. Did not re-verify the 88-call-site grep count or the exact 10s auto-hide constant in showMessage, but the central claim (shared error toast is not a live region, unlike other status surfaces) is directly confirmed from the markup, and independently corroborated by UX-009/UX-006 evidence showing raw exception-derived error strings are indeed passed into showMessage.


---

### UX-004 — The exit and chart modals do not move focus, trap focus, close on Escape or restore focus

- **Expert:** usability_accessibility  |  **Category:** accessibility-focus  |  **Severity:** medium  |  **Confidence:** high
- **Inspection status:** finding_identified  |  **Verification status:** confirmed
- **Affected workflows:** WF-11 exit with unsaved changes, Chart enlarge in results/reports

**Evidence:**

- `frontend/js/dashboard.js:6717-6729` — `openExitModal / closeExitModal / exitApp` — Opening and closing only toggle style.display. There is no focus() call, no keydown listener and no focus restore.
- `frontend/js/dashboard_decomp_ytd_and_plan_folder_io.js:44-55` — `openCachedChart` — The chart modal is shown with style.display='flex' and focus is not moved.
- `frontend/js/dashboard.js:1282-1286` — `closeChartModal` — Hides the modal but does not return focus to the button that opened it. A grep of dashboard.js found no Escape handler except closeNavDrawer (line 2051).
- `frontend/index.html:82-92` — `#exitModal, #pathModal, #chartModal` — All three have role=dialog, aria-modal and aria-labelledby, which promises modal behaviour that the code does not implement. A grep found no JS reference to #pathModal, so it is unused markup.
- `frontend/js/dashboard.js:6810-6817` — `beforeunload` — The unsaved-changes exit flow (WF-11) goes through exitModal. The recon found no test for it, and a grep of tests/ found no reference to exitModal or chartModal.

**Observed behavior:** After Exit with unsaved changes, focus stays on the header Exit button behind the backdrop. Because of UX-001, Tab from the Exit button goes to the first field under the backdrop, not to 'Save & Exit'. Escape does nothing. The chart modal behaves the same way.

**Impact:** Keyboard and screen-reader users can get stuck at the save-or-discard decision when exiting, which is the step that protects them from losing edits, and cannot close enlarged charts. This fails WCAG 2.4.3 and 2.1.1 for these dialogs.

**Root cause:** The focus-management fix (UX-105, 2026-09-07) went into the dynamic showInAppConfirm and showSaveDiscardStayModal dialogs but not into the static dialogs in index.html.

**Options:**

- Send exitModal and chartModal through one shared openStaticDialog/closeStaticDialog helper that reuses _trapTabWithinModal, focuses the safe default ('Keep Editing' or 'Close'), handles Escape and restores focus.
- Replace exitModal with showSaveDiscardStayModal, which already has trap, restore and Escape, and move the chart viewer to the same pattern.
- Use the native <dialog> element with showModal(), which provides inert background and Escape handling.

**Recommendation:** Option 2 for exit, since the same save, discard or stay decision already exists as an accessible component. Use option 1 or 3 for the chart viewer. Remove the unused #pathModal markup.

**Dependencies:** UX-001 (the capture handler would otherwise still pull focus out of any trapped dialog)

**Implementation considerations:** on_closing in src/desktop_app.py calls exitApp() through evaluate_js, so keep the entry point name. Add an e2e test for WF-11.

**Risk of change:** Low.

**Verification method:** Playwright: make an edit, click Exit, assert document.activeElement is inside #exitModal, press Escape and assert the modal closes and focus returns to Exit. Do the same for the chart modal.

**Linked implementation items:** WI-502

**Verification rationale (adversarial pass):** Opened dashboard.js:6717-6723: openExitModal/closeExitModal only toggle `.style.display`, with no focus() call, no keydown/Escape listener, and no stored reference for focus restore — directly confirming the core claim that the static exit modal lacks focus management, unlike showInAppConfirm which (per UX-001 evidence) does implement focus, Escape and a tab trap. This asymmetry (dynamic dialogs got the 2026-09-07 fix, static index.html dialogs did not) is well supported. Did not independently verify the chartModal/#pathModal citations, but the exitModal evidence alone substantiates a real, high-traffic gap (WF-11 exit-with-unsaved-changes).


---

### UX-005 — The default desktop mode disables page zoom, and the app has no text-size control despite dense 9-11px text

- **Expert:** usability_accessibility  |  **Category:** accessibility-readability  |  **Severity:** medium  |  **Confidence:** medium
- **Inspection status:** finding_identified  |  **Verification status:** confirmed
- **Affected workflows:** All desktop-mode screens

**Evidence:**

- `src/desktop_app.py:37-48` — `webview.create_window` — No zoomable argument is passed, so pywebview's default applies.
- `C:/Users/MattHartzman/AppData/Local/Programs/Python/Python312/Lib/site-packages/webview/window.py:106` — `Window.__init__ (pywebview 6.2.1, third-party)` — zoomable defaults to False. requirements.txt:19 pins pywebview>=4.0,<7.
- `C:/Users/MattHartzman/AppData/Local/Programs/Python/Python312/Lib/site-packages/webview/js/customize.js:96-108` — `zoomable === 'False' branch (third-party)` — With zoom disabled, pywebview blocks Ctrl+wheel and pinch zoom in the page.
- `C:/Users/MattHartzman/AppData/Local/Programs/Python/Python312/Lib/site-packages/webview/platforms/edgechromium.py:286-296` — `WebView2 settings (third-party)` — AreBrowserAcceleratorKeysEnabled is set to the debug flag, so it is False in normal runs. Keyboard zoom (Ctrl+Plus/Minus) is therefore likely unavailable too. Not verified at runtime.
- `frontend/css/dashboard.css:3,10,21,102-1059 (73 declarations)` — `font-size rules` — 73 declarations set text at 9, 10, 10.5 or 11px: step descriptions, badges, pills, impact-card captions, table headers. Body text is 14px. A grep of the main dashboard modules found no in-app text-size or zoom preference.

**Observed behavior:** In the default desktop launch, users most likely cannot enlarge the page with Ctrl+wheel or Ctrl+Plus. Much of the supporting text, including step descriptions, badges and table headers, is 9-11px.

**Impact:** Users with low vision can rely only on OS-wide display scaling. WCAG 1.4.4 (Resize Text) is at risk in the main distribution mode, and the small type in dense tables raises reading effort for everyone. This is a readability and resize problem, not a claim that the app is unfriendly to older users.

**Root cause:** pywebview's zoomable default was never overridden, and the stylesheet uses fixed small px sizes with no user-controlled scale.

**Options:**

- Pass zoomable=True in create_window. This is a one-line change that restores Ctrl+wheel and pinch zoom; keyboard zoom may still need accelerator keys.
- Add an in-app 'Text size' setting (for example 100/115/130%) that sets a root font-size or CSS zoom, stored in /api/prefs. This works whatever the WebView settings are.
- Raise the minimum text size to 12px and convert fixed px sizes to rem so any scaling cascades.

**Recommendation:** Do option 1 now and option 2 as the durable fix. Raise the 9-10px sizes (option 3) where tests allow, starting with badges and step descriptions.

**Implementation considerations:** The layout grid (310px / minmax(700px,1fr) / 370px) collapses at 1180px. Zooming exercises the narrow-window drawer path (tests/e2e/narrow-window-drawer.spec.js). Server mode in a browser is unaffected.

**Risk of change:** Low for option 1. Moderate for options 2 and 3 because of layout reflow in dense tables.

**Verification method:** Launch desktop mode and confirm that Ctrl+wheel and Ctrl+Plus change the zoom (before and after the change). Screenshot at 200% to confirm no content is lost.

**Linked implementation items:** WI-505

**Verification rationale (adversarial pass):** Opened src/desktop_app.py:37-48: webview.create_window() is called with title, url, js_api, width, height, min_size, maximized, text_select — no `zoomable` argument, confirming the default-applies claim. The pywebview internals citations (window.py, customize.js, edgechromium.py) are third-party library claims I did not re-verify by opening the installed package, but the conclusion (no override present in this codebase) is directly confirmed. The dense 9-11px font-size claim was not independently spot-checked but is plausible and orthogonal to the confirmed root cause.


---

### UX-006 — After the navigation restructure, cross-page jump buttons and messages name pages that no longer exist, and one points to a step id that does not exist

- **Expert:** usability_accessibility  |  **Category:** navigation-consistency  |  **Severity:** medium  |  **Confidence:** high
- **Inspection status:** finding_identified  |  **Verification status:** confirmed
- **Affected workflows:** WF-7 housing optimizer apply, WF-8 optimizer apply / change review, WF-3 build failure messaging

**Evidence:**

- `frontend/js/dashboard_decomp_housing_optimizer.js:2100-2106, 2118-2126, 2244-2250` — `housing change records / housingAdvisoryItem` — sourceStep is 'assets_home_cash' and sourceTitle is hard-coded to 'Home & Housing'. The advisory text says to set values 'on the Home & Housing page' and calls it 'The Housing step'.
- `frontend/js/dashboard.js:STEPS (extracted)` — `assets_home_cash / spending_mortgage_events / income_retirement` — assets_home_cash is titled 'Reserve Requirements'. The Housing step (spending_mortgage_events) is hidden and redirects to the Spending Model Housing accordion (navigation.js SECTION_REDIRECTS). income_retirement is titled 'SS, Pensions, & Annuities'.
- `frontend/js/dashboard_decomp_allocation_optimizer.js:120-128` — `allocation change record` — sourceStep is 'allocation' with the label 'Asset Allocation'. 'allocation' is not a STEPS id and is not in STEP_REDIRECTS, SECTION_REDIRECTS or WORKSPACE_TAB_REDIRECTS (navigation.js:51-120). Only allocation_assets and allocation_policy are redirected.
- `frontend/js/dashboard_decomp_income_streams.js:224-230` — `SS claim change record` — The hard-coded sourceTitle 'Income & Social Security' does not match the nav title.
- `frontend/js/dashboard_decomp_checklist_closeout.js:72` — `source jump button` — Renders the jump button as data-step-id=sourceStep with c.sourceTitle as its visible label. The same happens in dashboard_decomp_build_history.js:392/532 and dashboard_decomp_misc.js:192.
- `frontend/js/dashboard.js:3675, 3747-3762` — `renderMain` — For an unknown activeStep, st falls back to STEPS[0] ('Plan Status') and the body falls through to renderFields(activeStep).
- `frontend/js/dashboard_decomp_row_model.js:5056-5059` — `runBuild catch` — The failure overlay says 'The build stopped before the Build Impact page could be displayed'. build_impact is now hidden and redirects to 'Build & Results'.

**Observed behavior:** A jump labelled 'Home & Housing' opens Reserve Requirements, although housing inputs now live under Optimize > Next Housing Move and the Spending Model Housing accordion (PR #138). By static trace, a jump labelled 'Asset Allocation' navigates to the unknown step 'allocation' and would show a 'Plan Status' header over whatever renderFields returns for it. Help and error text still names pages that were renamed or merged.

**Impact:** After applying optimizer results, users are sent to the wrong page or an empty one when they try to review what changed. Labels that do not match the nav break wayfinding and trust (WCAG 3.2.4 Consistent Identification, 2.4.4 Link Purpose).

**Root cause:** Destination titles are hard-coded strings and step ids are free text instead of derived from STEPS through stepTitleById, and PRs #136-#139 renamed and moved pages without a check on these references.

**Options:**

- Replace every hard-coded sourceTitle with stepTitleById(sourceStep), fix sourceStep values ('allocation' to strategy_optimize with the asset_allocation section; housing rows to the step or section that now holds them), and add a unit test that every sourceStep or data-step-id literal resolves to a STEPS id or a redirect key.
- Add 'allocation' and similar legacy ids to SECTION_REDIRECTS as a stopgap and leave the labels alone.
- Extend the PR #139 'consistency guard' to scan JS string literals for stale page names such as 'Home & Housing', 'Build Impact page' and 'Housing step'.

**Recommendation:** Option 1 together with option 3's guard, so the next nav reorganization cannot silently break these links again.

**Implementation considerations:** Housing optimizer panel tests (tests/test_housing_optimizer_panel_functional.py, tests/frontend/housing_*.test.mjs) may assert on these strings. Read them before editing.

**Risk of change:** Low.

**Verification method:** Node test: collect every data-step-id and sourceStep literal and assert each resolves through setStep to a STEPS id. Manual check: apply a housing and an allocation optimizer result and click each jump button.

**Linked implementation items:** WI-506

**Verification rationale (adversarial pass):** Confirmed multiple hard-coded mismatches: dashboard_decomp_housing_optimizer.js:2103-2104 hard-codes sourceStep:"assets_home_cash", sourceTitle:"Home & Housing", while dashboard.js:129-131 shows assets_home_cash's actual title is "Reserve Requirements" — a real mismatch. dashboard_decomp_allocation_optimizer.js:126 hard-codes sourceStep:"allocation", which is not a STEPS id (STEPS ids seen use snake_case like assets_home_cash, workbook_formatting, strategy_workbench — 'allocation' alone is not among them), supporting the claim that this jump target does not resolve to a real step. Did not independently verify STEP_REDIRECTS/SECTION_REDIRECTS exhaustively to be certain 'allocation' has zero redirect entry, but the pattern of hard-coded, drift-prone sourceStep/sourceTitle literals is directly demonstrated in two independent files, supporting medium-severity navigation-consistency finding as described.


---

### UX-007 — The Workbench comparison shows its headline decision metrics as bare acronyms (LCV, ELTR, FCV, EFTR) that no glossary defines

- **Expert:** usability_accessibility  |  **Category:** terminology-cognitive-load  |  **Severity:** medium  |  **Confidence:** high
- **Inspection status:** finding_identified  |  **Verification status:** confirmed
- **Affected workflows:** WF-8 Strategy Workbench compare & decide, Build & Results impact review

**Evidence:**

- `frontend/js/planning_workbench_ui.js:358-359` — `impact matrix header` — The column headers are the bare labels 'LCV' and 'ELTR' in the case-comparison table where users record a Decision.
- `frontend/js/planning_workbench_ui.js:374-378` — `forwardLookingHtml` — The cards are labelled 'FCV' and 'EFTR' with no expansion.
- `src/glossary.py:22-81` — `canonical glossary` — The canonical glossary, which also feeds the workbook Glossary sheet (dashboard.js loadCanonicalGlossary comment), has no entry for LCV, ELTR, FCV or EFTR. The frontend ACRONYMS and ACRONYM_DEFINITIONS (dashboard_decomp_row_model.js:179-260) do not define them either.
- `frontend/js/dashboard_decomp_build_history.js:489` — `lcvCard tooltip` — The only expansion found is inside one Impact card tooltip: 'Lifetime Consumption-and-Transfer Value'. That phrase does not match the letters L-C-V.

**Observed behavior:** The screen meant for comparing and deciding between plans ranks cases by abbreviations that are never spelled out there and cannot be found through the help or glossary system.

**Impact:** Users are asked to adopt or archive plan changes based on metrics they may not understand. This adds cognitive load and risks misreading the numbers, for example confusing effective lifetime and future tax rates (WCAG 3.1.4 Abbreviations, AAA; a usability issue in its own right).

**Root cause:** The KPIs were added across #293 and #309 with inline tooltips instead of glossary entries, and the Workbench matrix was written with compact headers.

**Options:**

- Add LCV, ELTR, FCV and EFTR to src/glossary.py and use full column headers with the abbreviation in parentheses, e.g. 'Lifetime value (LCV)'.
- Keep the short headers but add <abbr title> and glossary tooltips through the existing decorateGlossary path.
- Rename the metrics in the UI to plain-language names and keep the acronyms only in the workbook.

**Recommendation:** Option 1. One canonical definition should serve the UI and the workbook, and the matrix headers should be readable without hovering.

**Implementation considerations:** This overlaps with the documentation expert's terminology charter. The workbook Glossary sheet renders from src/glossary.py, so workbook golden masters may change. Run the measure subcommand before any regeneration.

**Risk of change:** Low.

**Verification method:** Assert that glossary.canonical_glossary() contains the four terms, and that the Workbench matrix header text includes an expansion or a linked glossary tooltip.

**Linked implementation items:** WI-507

**Verification rationale (adversarial pass):** Opened frontend/js/planning_workbench_ui.js:358-378: table headers literally read <th>LCV</th><th>ELTR</th> and the forward-looking cards render bare '<span>FCV</span>' and '<span>EFTR</span>' with no inline expansion. Grepping src/glossary.py and this file for LCV/ELTR/FCV/EFTR found zero definitional matches (the only hits were the bare-acronym usages themselves), consistent with the claim that no glossary entry exists for these terms at this compare/decide screen. Confirms medium-severity cognitive-load finding.


---

### ARC-009 — Documented inventories have drifted with nothing checking them: route_manifest covers about half the routes, and the 'auto-generated, cannot drift' architecture diagram is stale

- **Expert:** architect  |  **Category:** maintainability  |  **Severity:** low  |  **Confidence:** high
- **Inspection status:** finding_identified  |  **Verification status:** confirmed
- **Affected workflows:** Maintenance and onboarding, API contract consumers

**Evidence:**

- `src/server/route_manifest.py:5-37` — `ROUTE_MODULES` — Lists 79 paths, against 148 distinct @app.route paths registered in src/server/*.py (script comparison). 70 are missing, including /api/build, /api/shutdown, /api/plan-data/<path>, /api/daf/recommendation, /api/qlac/recommendation and /api/housing/zip-screen, and /api/build/status/<job_id> is listed but not registered.
- `src/server/base_routes.py:145-150` — `contracts route` — The manifest is served to clients as part of /api/contracts.
- `tests/test_api_contracts_and_route_manifest_contract.py:36-41` — `test_phase3_route_manifest_groups_domains` — Asserts only a few memberships and does not compare against the registered routes.
- `documentation/reference/SYSTEM_ARCHITECTURE_DIAGRAM.md:1-5` — `header` — Claims it 'cannot drift' but records 129 Python / 19 JS files scanned. The tree now tracks 188 src .py and 44 frontend .js files. The generator also consumes route_manifest.py, so the diagram inherits its gaps.

**Observed behavior:** Two artifacts that describe the system are incomplete, and no test ties them to the code.

**Impact:** Contributors and review tooling get a wrong picture of the API surface, including security-relevant routes.

**Root cause:** Hand-maintained manifests and generated docs have no regeneration or equality check.

**Options:**

- Derive ROUTE_MODULES from app.url_map at import time (grouping by module or prefix) and add a test that every registered route is classified.
- Keep the hand list but add an equality test, plus a freshness test that reruns tools/generate_system_diagram.py and diffs the output.

**Recommendation:** Option 2. It is cheap and keeps the human grouping.

**Implementation considerations:** Documentation-panel findings about the diagram may duplicate this one. Keep a single owner.

**Risk of change:** Low.

**Verification method:** The new test fails on the current tree and passes after the manifest and diagram are updated.

**Linked implementation items:** WI-701

**Verification rationale (adversarial pass):** Directly verified: route_manifest.py's ROUTE_MODULES omits /api/build, /api/shutdown, /api/plan-data/<path:file_name> (both GET and POST), /api/daf/recommendation, /api/qlac/recommendation, and /api/housing/zip-screen, all of which are confirmed via grep to be registered as real @app.route entries in workbook_routes.py and plan_routes.py. This directly substantiates the core claim of significant manifest drift, including omission of security-relevant routes (build, shutdown, plan-data writes) called out in ARC-001. Severity 'low' and confidence 'high' are appropriately calibrated — this is a maintainability/documentation-accuracy issue, not itself a security hole.


---

### ARC-010 — Leftover SaaS auth scaffolding and dead compatibility shims remain in the transport and persistence layers

- **Expert:** architect  |  **Category:** dead-code  |  **Severity:** low  |  **Confidence:** high
- **Inspection status:** finding_identified  |  **Verification status:** confirmed
- **Affected workflows:** Maintenance, Security review

**Evidence:**

- `src/server/security_audit.py:57-127` — `_candidate_token / _has_bearer_or_api_header / _set_auth_cookie / _clear_auth_cookie / _identity_from_token` — _has_bearer_or_api_header, _set_auth_cookie, _clear_auth_cookie and _identity_from_token are referenced only in a comment (app_core.py:305). _authorized_and_identity always returns (True, None).
- `src/config_backend.py:322-355` — `create_user / create_api_token / lookup_api_token / upsert_client …` — Compatibility stubs. create_user and create_api_token have 0 call sites.
- `src/runtime_config.py:99-110, 130-133` — `load_runtime_config` — app_mode, force_https, require_api_token and audit flags are all hardcoded, yet _security_gate (app_core.py:1937-1942) parses system_config.csv on every request to check force_https.
- `src/housing_optimizer.py:1-18` — `module docstring` — Says plan_routes.py uses the shim, but git grep shows only two test modules import it.
- `src/dashboard_ui/builder.py:34-48` — `write_dashboard_ui` — No production caller (only tests and tools/check_package_clean.py, tools/generate_system_diagram.py).
- `frontend/js/pywebview_bridge.js:172-176` — `_binary branch` — Unreachable. src/desktop_api.py:125-199 (_convert) never returns a `_binary` key; it saves and opens files server-side.

**Observed behavior:** Unused auth, cookie and token code, and always-true gates, remain in the request path next to the real (absent) protections, together with shims kept only for tests.

**Impact:** This misleads readers about the security posture (see ARC-001), adds per-request config parsing and adds maintenance surface.

**Root cause:** Incremental removal of SaaS mode that kept function signatures for star-import compatibility.

**Options:**

- Delete the unused auth, cookie and token helpers and stubs, drop the force_https branch from _security_gate, and repoint tests from src.housing_optimizer to src.housing.
- Keep the stubs but mark them deprecated, with a test listing allowed dead symbols.

**Recommendation:** Option 1, done together with the ARC-001 change to _security_gate.

**Dependencies:** ARC-001

**Implementation considerations:** security_audit's __all__ exports everything to app_core, so check that route modules' explicit import lists (review 4.9) do not name removed symbols.

**Risk of change:** Low.

**Verification method:** Static grep shows no remaining references. The Python fast test tier still covers the imports (run by the implementer, not claimed here).

**Linked implementation items:** WI-102

**Verification rationale (adversarial pass):** security_audit.py confirms _has_bearer_or_api_header, _set_auth_cookie, _clear_auth_cookie, and _identity_from_token are defined but _authorized_and_identity (the only caller site in the gate) never invokes any of them — it just returns (True, None) unconditionally, consistent with 'referenced only in a comment' elsewhere. runtime_config.py hardcoding audit/app_mode flags while _security_gate still branches on cfg.force_https (parsed per-request) matches the claim of per-request config parsing for functionality that can't actually vary. This finding correctly notes it is dependent on / should land together with ARC-001, and does not duplicate it: ARC-001 is about missing enforcement, this one is about the resulting dead code being confusing and adding surface. Severity 'low'/confidence 'high' are appropriate for a dead-code/maintainability finding.


---

### DOC-006 — About 20 references in code, tests and docs point to documentation paths that no longer exist, including the runbook link in the auto-loaded project CLAUDE.md

- **Expert:** documentation  |  **Category:** documentation-accuracy  |  **Severity:** low  |  **Confidence:** high
- **Inspection status:** finding_identified  |  **Verification status:** confirmed
- **Affected workflows:** Golden-master recovery, Code-to-design traceability

**Evidence:**

- `.claude/claude.md:50` — `Golden Masters` — Cites documentation/GOLDEN_MASTER_RECOVERY_RUNBOOK.md; the file is under reference/.
- `src/api_contracts.py:141` — `contract notes` — The moved housing spec path is served through /api/contracts.
- `src/housing/__init__.py:45` — `docstring` — Moved spec path.
- `src/housing/zip_screen/__init__.py:7` — `docstring` — Moved spec path.
- `src/local_store.py:277` — `comment` — task-5-brief.md is not tracked anywhere.
- `documentation/reference/PLAN_METADATA_SCHEMA.md:158` — `See also` — PHASE_C file moved to archive/legacy.
- `documentation/reference/CONTRIBUTING.md:31` — `text` — Dead SYSTEM_REVIEW_AND_REFACTOR_PLAN.md path, also at src/planning_engines.py:13, src/server/security_audit.py:4, src/reporting/sheets_allocation_helpers.py:52, tests/test_market_data_module.py:3 and conftest.py:6.
- `frontend/js/dashboard_decomp_housing_scenarios.js:8` — `header` — Moved codemod spec path.

**Observed behavior:** Doc moves left dead citations, and no link check exists.

**Impact:** Design traceability breaks. The auto-loaded CLAUDE.md points to a missing recovery runbook.

**Root cause:** Hard-coded paths with no link test.

**Options:**

- Fix the citations.
- Add a path-existence test.
- Cite designs by stable ID plus an index.

**Recommendation:** Options 1 and 2. This supersedes prior DOC-002.

**Dependencies:** DOC-005

**Implementation considerations:** The /api/contracts note is served text.

**Risk of change:** Very low.

**Verification method:** Re-run the path sweep and confirm it is empty.

**Linked implementation items:** WI-706

**Verification rationale (adversarial pass):** Opened .claude/claude.md:50 — cites 'documentation/GOLDEN_MASTER_RECOVERY_RUNBOOK.md'. Confirmed via `ls` that this path does not exist, while the file actually lives at documentation/reference/GOLDEN_MASTER_RECOVERY_RUNBOOK.md. This directly confirms the most load-bearing claim in the finding (a dead link in the auto-loaded project CLAUDE.md, which is read on every session start). Did not verify all ~20 other cited dead references individually, but the anchor claim is solid and the severity/low-risk-of-change assessment is reasonable given it is a pure text-path fix.


---

### DOC-008 — API_CONTRACTS.md and the 'cannot drift' architecture diagram are out of date

- **Expert:** documentation  |  **Category:** documentation-currency  |  **Severity:** low  |  **Confidence:** high
- **Inspection status:** finding_identified  |  **Verification status:** confirmed
- **Affected workflows:** Maintenance, Architecture review

**Evidence:**

- `documentation/reference/API_CONTRACTS.md:1-5, 490-499` — `header / /api/pdf` — Dated 2026-06-29 for v10. Documents /api/pdf.
- `src/server/workbook_routes.py:458-460` — `get_xlsx` — Only /api/xlsx exists; no /api/pdf route was found.
- `src/server/route_manifest.py:6` — `build_results` — No /api/pdf.
- `tests/test_api_contract_docs_contract.py:12-55` — `tests` — Pins 9 endpoints. About 90 of about 142 routes are undocumented.
- `documentation/reference/SYSTEM_ARCHITECTURE_DIAGRAM.md:1-5` — `header` — Reports 129/19 files against 188/44 tracked, and does not mention src/housing.
- `tools/generate_system_diagram.py:158, 200, 281` — `generator` — Would produce different output; there is no freshness check.

**Observed behavior:** The API doc lists a route that does not exist. The generated diagram is stale.

**Impact:** Developer-facing reference docs give a wrong picture.

**Root cause:** Manual regeneration and subset-only tests.

**Options:**

- Regenerate the diagram, drop /api/pdf and add a scope note.
- Add a diagram freshness test.
- Generate the route table from route_manifest.

**Recommendation:** Options 1 and 2.

**Implementation considerations:** Expect a large but mechanical diff.

**Risk of change:** Very low.

**Verification method:** Regenerate and diff in a scratch copy.

**Linked implementation items:** WI-702

**Verification rationale (adversarial pass):** Opened documentation/reference/API_CONTRACTS.md:490 — has a section header '### `/api/xlsx` and `/api/pdf`', documenting /api/pdf as an existing endpoint. Grepped src/server/workbook_routes.py and found only an '/api/xlsx' route (line 458); no '/api/pdf' route exists anywhere in that file. Also grepped src/server/route_manifest.py for 'api/pdf' with no match. This directly confirms the doc references a non-existent endpoint. Did not independently verify the '~90 of ~142 undocumented routes' figure or the SYSTEM_ARCHITECTURE_DIAGRAM.md file-count staleness, but the core, most concrete claim is confirmed.


---

### DOC-009 — README files in input/ carry old version labels, dead references, a wrong menu path and a wrong estate-tax claim

- **Expert:** documentation  |  **Category:** documentation-accuracy  |  **Severity:** low  |  **Confidence:** high
- **Inspection status:** finding_identified  |  **Verification status:** confirmed
- **Affected workflows:** Demo, Plan Data packaging

**Evidence:**

- `input/README_INPUT_PACKAGE.md:1-11` — `file` — Labeled v8.3, with a missing doc reference and an untracked manifest.
- `input/demo/README.md:35-39` — `To use it` — Says Open Demo Plan is under Settings -> Data & Maintenance.
- `frontend/js/dashboard_decomp_checklist_closeout.js:274-284` — `renderWelcome / renderSystemConfiguration` — The demo buttons are on the Welcome page only.
- `input/demo/README.md:11-13` — `household` — Claims Illinois is the only modeled estate-tax state.
- `src/core.py:1339-1382` — `state_estate_tax` — New York is also computed.

**Observed behavior:** The ancillary READMEs are behind the product.

**Impact:** A non-expert is misdirected, and the model's coverage is understated.

**Root cause:** No currency coverage for input/ READMEs.

**Options:**

- Correct the statements.
- Retire README_INPUT_PACKAGE.md if the package is obsolete.

**Recommendation:** Option 1, and Option 2 if confirmed.

**Implementation considerations:** input/ is excluded from release zips.

**Risk of change:** None.

**Verification method:** Read the files and check the click path.

**Linked implementation items:** WI-707

**Verification rationale (adversarial pass):** Opened input/README_INPUT_PACKAGE.md:1 — literally titled 'Retirement System v8.3 Input Package', confirming the stale version label. Opened input/demo/README.md:11-13 — explicitly states 'Illinois is retained as the residence state on purpose: it is the only state the engine models an estate tax for.' Opened src/core.py:1338-1382 (state_estate_tax function and STATE_TAX_RULES dispatch) and found an explicit 'ny_graduated_cliff' branch calling new_york_estate_tax with status 'computed', plus a docstring note stating 'New York (item 3.6, F5) is no longer in this bucket' (i.e., was previously not_modeled, now is computed) — directly confirming the demo README's claim is factually wrong and stale relative to a real code change. This is a strong, directly-verified finding; did not independently verify the 'Open Demo Plan menu path' claim against dashboard_decomp_checklist_closeout.js.


---

### FIN-013 — The RMD Uniform Lifetime divisor for age 83 is 17.8 (IRS table: 17.7), and divisors above age 117 are extrapolated

- **Expert:** financial_planner  |  **Category:** reference-data-currency  |  **Severity:** low  |  **Confidence:** medium
- **Inspection status:** finding_identified  |  **Verification status:** confirmed
- **Jurisdiction:** US federal (Treas. Reg. §1.401(a)(9)-9(c), Uniform Lifetime Table)  |  **Rule year:** 2022+ table
- **Assumptions:** Hard-coded. Authority: IRS Pub. 590-B Table III (authoritative), from reviewer knowledge and not opened in this run, so verify against the primary source before editing.
- **Affected workflows:** RMD computation

**Evidence:**

- `src/core.py:646-653` — `RMD_DIVISORS` — 83:17.8. The table ends at 115:2.9.
- `src/tax_kernel.py:239-241` — `rmd_divisor` — Past 115, the divisor is 2.9 − 0.1×(age−115), giving 2.6, 2.5 and 2.4 at 118-120. The IRS table gives 2.5, 2.3 and 2.0.

**Observed behavior:** At age 83 the RMD is about 0.56% too low. At 118 and older RMDs are slightly understated.

**Impact:** Small. The RMD in the age-83 year is understated (for example about $56 per $1M), with minor knock-on effects on tax and IRMAA.

**Root cause:** A transcription error, and no table rows beyond 115.

**Options:**

- No credible alternative; this is a correctness defect.

**Recommendation:** Correct 83 to 17.7 and add rows 116-120+ (2.8, 2.7, 2.5, 2.3, 2.0) after checking against Pub. 590-B. Add a test that pins the full table.

**Implementation considerations:** Golden masters with a member aged 83 will shift slightly.

**Risk of change:** Low.

**Verification method:** Compare the table row by row with IRS Pub. 590-B Appendix B Table III.

**Linked implementation items:** WI-303

**Verification rationale (adversarial pass):** Opened core.py:646-650: RMD_DIVISORS confirms 83:17.8 hardcoded, and the table ends at 115:2.9 exactly as claimed. tax_kernel.py:239-241 confirms the age>115 extrapolation is `RMD_DIVISORS[115] - max(0, age_i-115)*0.1`, producing 2.6/2.5/2.4 at ages 118/119/120 as computed. I could not independently verify against IRS Pub. 590-B Table III (would require an external primary source not available in this repo), but the reviewer's domain-knowledge claim that 83 should be 17.7 is consistent with my own general knowledge of the published Uniform Lifetime Table, and the finding is appropriately low-severity/appropriately caveated as unverified against the primary source.


---

### FIN-014 — The LTCG-rate guardrail in Roth sizing indexes LTCG thresholds from plan_start, not from the table's value year

- **Expert:** financial_planner  |  **Category:** financial-correctness  |  **Severity:** low  |  **Confidence:** high
- **Inspection status:** finding_identified  |  **Verification status:** confirmed
- **Affected workflows:** Roth conversion sizing

**Evidence:**

- `src/planning_engines.py:2216-2222` — `_ltcg_niit_caps` — bracket_factor = (1+brk_inf)^(year − plan_start) is applied to the 2025-vintage LTCG tops.
- `src/tax_kernel.py:18-28, 49-67` — `module docstring, bracket_factor_for_year` — The kernel's signed-off convention compounds from FEDERAL_BRACKETS_VALUE_YEAR and names plan_start compounding as a fixed bug.

**Observed behavior:** For a plan starting in 2026, the LTCG tier cap in conversion sizing uses thresholds about one year of indexing lower than the thresholds that tax assessment uses.

**Impact:** The LTCG guardrail is slightly too tight, so conversions are marginally smaller when that cap binds. The deviation is small but inconsistent with the signed-off convention.

**Root cause:** A local re-implementation of bracket indexing was left behind when the rest moved to tax_kernel.bracket_factor_for_year.

**Options:**

- No credible alternative; this is a correctness defect.

**Recommendation:** Replace the local factor with _tk.bracket_factor_for_year(c, year).

**Implementation considerations:** tests/test_roth_ltcg_niit_guardrails.py asserts exact amounts and will need updating.

**Risk of change:** Low.

**Verification method:** Assert that the LTCG cap threshold equals the value tax_kernel.ltcg_tax_on_gain uses for the same year.

**Linked implementation items:** WI-306

**Verification rationale (adversarial pass):** Opened planning_engines.py:2216 (_ltcg_niit_caps): `bracket_factor = (1 + float(c.get('brk_inf', 0.02) or 0.0)) ** (year - plan_start)` — confirmed local re-implementation compounding from plan_start. tax_kernel.py's module docstring (lines ~18-28) and bracket_factor_for_year (lines 49-67) explicitly document this exact plan_start-vs-value-year compounding-base mismatch as bug #2 that was 'fixed by consolidating here' (compounding from taxes.FEDERAL_BRACKETS_VALUE_YEAR instead), proving the planning_engines.py LTCG cap was missed in that consolidation and still uses the old, acknowledged-buggy convention. This is a clean, high-confidence, low-severity consistency defect, exactly as described.


---

### UX-008 — With no plan loaded, the router lets Workbook Formatting open, but the main renderer shows the welcome screen

- **Expert:** usability_accessibility  |  **Category:** navigation-consistency  |  **Severity:** low  |  **Confidence:** high
- **Inspection status:** finding_identified  |  **Verification status:** confirmed
- **Affected workflows:** WF-12 workbook formatting

**Evidence:**

- `frontend/js/navigation.js:26, 197-203` — `PLAN_INDEPENDENT_STEPS / setStep` — workbook_formatting is listed as plan-independent, so setStep does not bounce it to 'start'.
- `frontend/js/dashboard.js:3652-3672` — `renderMain` — The inline plan-independent list (detailed_results, system_configuration, strategy_scenarios, strategy_workbench, reports_and_review) leaves out workbook_formatting and renders renderWelcome() instead.
- `frontend/js/dashboard_batch_assumption_edit.js:497-502` — `renderMain wrapper` — Neither renderMain decorator (this one, or dashboard_source_truth_banners.js:671-676) changes that branch.

**Observed behavior:** Before a plan is opened, choosing Settings > Workbook Formatting highlights that step but the page shows the Plan Status welcome content. Workbook Formatting is a system-level setting.

**Impact:** This is a confusing mismatch between where the user navigated and what is shown. Minor.

**Root cause:** The plan-independent list exists in two places that disagree.

**Options:**

- No credible alternative; this is a correctness defect.

**Recommendation:** Have renderMain read window.RetirementNavigation.PLAN_INDEPENDENT_STEPS instead of its own inline list.

**Implementation considerations:** Confirm that renderWorkbookFormatting works without plan data. It reads /api/workbook-format, which is system-level.

**Risk of change:** Low.

**Verification method:** Node test: with planLoaded=false and activeStep='workbook_formatting', renderMain output contains the Workbook Formatting page and not renderWelcome.

**Linked implementation items:** WI-508

**Verification rationale (adversarial pass):** Confirmed both halves directly: navigation.js:26 PLAN_INDEPENDENT_STEPS includes 'workbook_formatting'. dashboard.js's renderMain (~line 3652-3663) has its own inline array — ["detailed_results","system_configuration","strategy_scenarios","strategy_workbench","reports_and_review"] — that omits 'workbook_formatting'; when !planLoaded and activeStep is 'workbook_formatting', the condition `!includes(activeStep)` is true, so renderMain falls into `document.getElementById("mainPane").innerHTML = renderWelcome()`. This is an exact, directly-traced correctness defect as described.


---

### UX-010 — Selected and active states are shown only by colour or CSS class (step nav, search scope, trends timeframe)

- **Expert:** usability_accessibility  |  **Category:** accessibility-semantics  |  **Severity:** low  |  **Confidence:** high
- **Inspection status:** finding_identified  |  **Verification status:** confirmed
- **Affected workflows:** Left navigation, Nav/page search, Trends reporter

**Evidence:**

- `frontend/js/dashboard_decomp_row_model.js:2371` — `step button template` — The active and complete step is shown only by the class stepbtn active/complete/missing. There is no aria-current and no text equivalent other than a badge.
- `frontend/index.html:77` — `search-scope buttons` — Navigation/Page scope is shown by the 'primary' class only (navigation.js:355 toggles the class), with no aria-pressed.
- `financial_trends_reporter/frontend/index.html:41-50` — `timeframe buttons` — The selected timeframe is shown by class 'active' only.

**Observed behavior:** Screen-reader users cannot tell which step is current, which search scope is active, or which trend timeframe is selected.

**Impact:** Minor orientation problem (WCAG 4.1.2 and 1.4.1). Other widgets such as the MC engine toggle and the annualize toggle already expose aria-pressed, so this is also an internal inconsistency.

**Root cause:** Pattern not applied consistently.

**Options:**

- Add aria-current="step" to the active stepbtn and aria-pressed to the scope and timeframe toggles.
- Convert scope and timeframe toggles to radio groups.

**Recommendation:** Option 1, because it adds attributes only.

**Implementation considerations:** Several tests snapshot nav markup, so check tests/frontend for stepbtn string assertions.

**Risk of change:** Low.

**Verification method:** Node test asserting that the active stepbtn has aria-current and the scope buttons have aria-pressed that follows the state.

**Linked implementation items:** WI-509

**Verification rationale (adversarial pass):** Opened dashboard_decomp_row_model.js:2371: the stepbtn template is `<button class="stepbtn ${cls}" ... data-step-id=...>` with no aria-current attribute anywhere in the string, confirming the core claim for step navigation. Did not independently re-verify the search-scope button and trends-reporter timeframe citations, but the confirmed stepbtn case alone substantiates a real, low-severity WCAG 4.1.2 gap consistent with the finding.


---


## 6. Options and tradeoffs

Per-finding options and tradeoffs are recorded in full in each finding's **Options** field in
Section 5 (2–3 real alternatives where a genuine choice exists, or the explicit statement "No
credible alternative; this is a correctness defect." for objective bugs). This section summarizes
the tradeoffs that cut across findings, where an implementation choice made for one finding
constrains another.

- **Security enforcement scope (ARC-001).** Enforcing the CSRF token and an Origin/Host allow-list
  in `_security_gate` (recommended) is a small, targeted change but will break any external
  automation script that currently POSTs to server mode without the token — an acceptable tradeoff
  given the alternative (removing server mode from user-facing launchers entirely) would also
  remove its legitimate debugging/browser use.
- **Tax-dataset refresh sequencing (FIN-004/FIN-005/FIN-007).** All three touch
  `tax_law_v10.json`. Refreshing FIN-004's OBBBA/2026 values first, then re-encoding FIN-005's SALT
  schedule as absolute years, then adding FIN-007's dated ACA table, avoids three independent edits
  colliding on the same statutory-table structure — the tradeoff is a longer critical path (Wave 3)
  versus a higher risk of a merge conflict or a half-migrated dataset if done in parallel.
- **Fill-to-bracket sizing (FIN-002) after survivor-deduction fix (FIN-003).** FIN-002's own
  dependency field names FIN-003; fixing deduction sizing first means FIN-002's bracket_room
  formula is built on the corrected standard-deduction/senior-bonus count rather than needing a
  second pass. The tradeoff is that FIN-002's medium-high risk-of-change (it moves conversion
  amounts, lifetime tax, IRMAA exposure and terminal Roth balances in every converting plan) lands
  slightly later in the sequence.
- **Load Saved Plan validation depth (ARC-005/QA-004).** The chosen option (one shared
  `replace_active_db()` helper with `PRAGMA integrity_check`, a required-table check, and SQLite's
  backup API) is more work than either finding's minimal fix alone, but it closes both the
  missing-validation gap (ARC-005) and the un-verified-checkpoint gap (QA-004) with one change
  instead of two, and removes the current situation where the two DB-replacement code paths apply
  different, non-overlapping safeguards.
- **Keyboard-capture handler scope (UX-001).** Scoping `moveToNextEntry` to `focusableEntries()`
  targets only (recommended) preserves the field-advance convenience users rely on while restoring
  native Tab/Enter everywhere else. The alternative — removing the Tab override entirely — is
  simpler but would remove a convenience some users depend on; the recommended option was chosen
  because it is no more effort and preserves existing behavior for the fields it was built for.
- **Bootstrap unification (ARC-002) as a foundation dependency.** Building one shared
  `src/bootstrap.py` (recommended) versus simply repointing the desktop shortcut at `main.py`: the
  shared-function option costs more up front but is what ARC-003, ARC-005 and ARC-007 each already
  name as their own dependency, so it is treated as Wave 0 rather than deferred.

## 7. Recommendation

Proceed with all findings whose `verification_status` is `confirmed` or `partially_confirmed`
(44 of 50 register entries; see Section 5), sequenced per the implementation waves in Section 9.
Do not act on the 4 cross-expert duplicates as separate work (their fixes are already covered by
their canonical finding) or on the 2 `insufficient_evidence` findings (DOC-005, DOC-010) without
first re-opening the specific evidence this review could not independently confirm (Section 13).

**Sequencing logic, in order of what should not ship un-remediated:**

1. **Wave 1 first, in full, before any other engine change.** ARC-001 (security) and the
   FIN-003→FIN-002 / FIN-001 financial-correctness chain are the four highest-consequence items in
   the register. FIN-001 and FIN-002 both affect every plan with, respectively, a survivor period or
   a Roth-conversion policy — a large share of real households — and ARC-001 is a full local
   read/write/exfiltration path whenever server mode runs. None of the three has an architectural
   dependency on any other wave.
2. **Wave 0 before Wave 2.** ARC-002's shared bootstrap is a named dependency of ARC-003, ARC-005
   and ARC-007; landing it first avoids rework.
3. **Wave 3's tax-table chain (FIN-004→FIN-005→FIN-013→FIN-009→FIN-006, with FIN-007 also gated on
   FIN-004) requires qualified professional review of the underlying 2025/2026 statutory figures
   before merge** — per financial-domain-governance.md, this review's citations for the correct
   OBBBA/2026/IRS/CMS values come from reviewer domain knowledge, not an opened primary source, and
   must be independently verified before `tax_law_v10.json` is edited. FIN-007 additionally needs
   external confirmation of whether ACA's enhanced subsidies are actually in effect for 2026 under
   current law — a legal-status question outside what this static review can settle.
4. **Waves 2, 4 and 5 can run largely in parallel with Wave 3 and with each other**, since they
   touch disjoint files (persistence/security-hygiene, quality/determinism, and
   accessibility/frontend respectively) — see each wave's stated parallel groups.
5. **Wave 6 and Wave 7 (documentation)** are lowest-risk and can be picked up at any point, though
   WI-311 (the tax runbook rewrite) is sequenced after Wave 3's dataset changes so it documents the
   corrected procedure, not the current one.

**What "done" looks like:** every Wave-1 and Wave-3 item has passed its stated verification method
against a synthetic fixture (Section 5/9); the golden-master `measure` step has been run and every
resulting delta hand-checked before any `regen`, per this repository's own CLAUDE.md rule; and the
financial planner has recorded a sign-off disposition in Section 14 that covers at minimum every
`high`-severity financial finding (FIN-001, FIN-002) before those two land.

## 8. Target design

This review found no case requiring a structural rewrite; the target design is a set of targeted
consolidations layered onto the existing architecture.

**Boundaries and responsibilities (post-remediation).**
- **Startup/bootstrap:** one `src/bootstrap.py` function owns environment defaults and the
  at-rest plan-data migration; `main.py`, `START_DESKTOP.py` and `DesktopApi.__init__` each call it
  rather than maintaining their own copies (closes ARC-002).
- **Transport security:** `_security_gate` becomes the single place that (a) validates the
  CSRF token for non-GET, non-public requests in server mode, (b) allow-lists Origin/Referer/Host,
  and (c) requires `Content-Type: application/json` on JSON routes; the desktop bridge remains
  exempt because it never crosses HTTP (closes ARC-001, and removes the dead scaffolding ARC-010
  documents around it).
- **Database replacement:** one `replace_active_db(src)` helper in a shared location (e.g.
  `plan_file_io.py`) is the only code path that ever overwrites the live SQLite database — used by
  both Load Saved Plan and snapshot restore — performing validation, checkpoint-busy-flag checks,
  a backup via SQLite's backup API, atomic replace, sidecar cleanup, and the at-rest migration, in
  that order (closes ARC-005 and QA-004).
- **Statutory tax data:** `tax_law_v10.json` remains the single source of truth for dated federal
  tax-law values, but every family of values it holds (standard deduction, SALT cap, IRMAA tiers,
  ACA applicable percentages) is represented as absolute-year dated rows, and the annual-maintenance
  runbook is rewritten to describe exactly that convention (closes FIN-004, FIN-005, FIN-007,
  DOC-001).
- **Survivor economics:** the survivor Social Security benefit and the deceased-spouse standard-
  deduction/senior-bonus count are both derived every year from the deceased's own record and the
  household's current alive-flags, not from a snapshot taken at the death year, and both the scalar
  and vectorized Monte Carlo engines call the same derivation (closes FIN-001, FIN-003).
- **Data-entry accessibility:** `fieldHtml` and `settingControl` emit a native `<label for=...>`
  linked to each control's id, with `aria-required`/`aria-invalid`/`aria-describedby` wired to the
  existing required-badge/unit/note markup; the document-level keyboard handler only acts on
  `focusableEntries()` targets (closes UX-001, UX-002, and unblocks UX-003's aria-invalid wiring
  and UX-004's modal focus trap).
- **Diagnostics:** logging is configured once, at bootstrap, with a rotating file handler; the
  existing SQLite `audit_events` table receives real writes once `audit_log_enabled` is no longer
  hardcoded false (closes ARC-003).

**Data and calculation flows.** No change to the overall pipeline shape
(`data_io.parse_client` → `plan_config.ensure_engine_config` → `deterministic_engine`/
`planning_engines` → `reporting`). The changes above correct what several stages compute (survivor
SS, deductions, bracket_room, SALT/IRMAA/RMD/state-exclusion figures, home-sale basis) without
changing the stage boundaries.

**Validation.** A shared date parser (one century-pivot rule) replaces the three disagreeing
implementations across `data_io.py`, `dashboard_decomp_row_model.js` and `app_core.py`
(`_normalize_date_for_csv`); `schema_registry.validate_value` gains a `date` branch that rejects
unparseable formats and non-finite numbers, and a missing/blank required DOB becomes a hard error
rather than a silent literal fallback (closes QA-001).

**Persistence.** All primary-user-data writes (holdings, liabilities, HSA schedule, plan-load
materialization, the trends log, the secret store) route through the existing `atomic_write` helper
(closes ARC-008); the trends log separates its run-date de-duplication key from its data-coverage
date and quarantines rather than silently drops unparseable history lines (closes QA-005/FIN-010,
completing the already-open PR #141).

**Tests and golden masters.** A parse-side assertion decouples the golden master from the
coincidence that the frozen fixture's household values equal `parse_client`'s hard-coded fallbacks
(closes QA-002); `workbook_builder.py`'s YTD blend and `optimization.py` route through
`platform_runtime.today()` so the project's own frozen-date determinism seam actually holds for the
production build path (closes QA-003); and the three carried-forward High-severity test gaps from
the prior review (an always-skipped survivor-reconciliation test, pin-provenance limited to one
fixture, an untested budget-recovery function) are closed (closes QA-006).

**Documentation.** The annual tax-maintenance runbook, the two "as it behaves today" specs, the
backlog-progress record, and roughly twenty dead documentation-path citations (including the one in
the auto-loaded project `CLAUDE.md`) are brought back in sync with the code they describe; the
end-user README's network-privacy claim is corrected against the actual LIVE-mode default.

**Assumptions carried into this design:** the desktop bridge's transport exemption from CSRF
checking (it never crosses HTTP) is assumed safe and is not itself re-examined; the `.rpx` format
is assumed to remain a raw SQLite file for the validation helper's table-existence check; and no
change in this design alters the documented product scope (local-first, single-household planning).

## 9. Implementation waves

Waves are dependency-ordered; within a wave, items are genuinely parallelizable only where they
touch disjoint files or components — each item states its `parallel_group`, and items sharing a
group id may run concurrently, while items in a `-chain` group within the same wave must run in the
listed order because they touch the same file or dataset. `priority` here is this orchestrator's
implementation-sequencing judgment (distinct from each finding's own `severity` rating in Section
5). No wave or item concerns CI remediation.

### Wave 0 — Foundation / bootstrap

*Sequencing rationale:* Several later items (ARC-003, ARC-005, ARC-007, ARC-008) explicitly depend on a single startup bootstrap existing. Land it first so those items have one place to hook into.

| Item | Change | Finding IDs | Depends on | Priority | Effort | Risk | Owner | Parallel group | Model tier |
|---|---|---|---|---|---|---|---|---|---|
| WI-000 | Create one src/bootstrap.py function (env defaults + run_startup_plan_data_migration) called by main.py, START_DESKTOP.py and DesktopApi.__init__, so every launch path runs the same startup sequence. | ARC-002 | — | high | M | low | architect | 0-solo | standard_reasoning |

**Validation and exit criteria:**

- **WI-000** — Validation: A fixture with a legacy flat category id, launched via START_DESKTOP, is migrated at rest. Exit criteria: All three launch paths call the same bootstrap function; env-default dicts are no longer duplicated.

### Wave 1 — Critical security & high-severity financial correctness

*Sequencing rationale:* Highest-severity findings (one security, two financial-correctness) with no code dependency on the bootstrap wave; grouped so genuinely independent files run in parallel.

| Item | Change | Finding IDs | Depends on | Priority | Effort | Risk | Owner | Parallel group | Model tier |
|---|---|---|---|---|---|---|---|---|---|
| WI-101 | Enforce the issued X-CSRF-Token for every non-GET, non-public request in server mode and add an Origin/Referer/Host allow-list in _security_gate; require Content-Type: application/json on JSON routes. | ARC-001 | — | critical | M | medium | architect | 1-A | expert_reasoning |
| WI-102 | Delete the unused auth/cookie/token helpers (_has_bearer_or_api_header, _set_auth_cookie, _clear_auth_cookie, _identity_from_token, create_user, create_api_token) and drop the force_https per-request CSV parse from _security_gate. | ARC-010 | WI-101 | low | S | low | architect | 1-A | mechanical |
| WI-106 | Scope the build-failure fallback catch to only the initial /api/build/start call (checked by status/error-code, not free-text matching); never fall back once a job id has been issued or has reported failed. | ARC-004, UX-009 | — | medium | S | low | architect | 1-C | standard_reasoning |
| WI-103 | Rebuild the survivor Social Security benefit each projection year from the deceased's own record (PIA + DRCs earned to death, or claimed benefit with the widow(er) limit), index by COLA through the current year, gate on survivor age 60+, and apply the survivor early-claim reduction. Apply identically in the scalar and vectorized Monte Carlo paths. | FIN-001 | — | critical | L | medium | financial_planner | 1-B | expert_reasoning |
| WI-104 | Build n65 (over-65 deduction/senior-bonus count) from (h_alive and h_age>=65) + (w_alive and w_age>=65) in apply_agi_and_tax and plan_roth_conversion; deny the senior bonus to MFS filers. | FIN-003 | — | high | S | low | financial_planner | 1-B | expert_reasoning |
| WI-105 | Compute bracket_room as (top_target + deduction) - pre_agi, where deduction is the larger of the standard deduction (incl. senior bonus, using the WI-104 fix) and estimated itemized deductions; keep IRMAA/ACA/NIIT caps on a MAGI basis. | FIN-002 | WI-104 | critical | M | medium-high | financial_planner | 1-B | expert_reasoning |

**Validation and exit criteria:**

- **WI-101** — Validation: POST to /api/plan-data/client_data.csv with no token/foreign Origin returns 403; POST with no Content-Type and no token returns 403; desktop-bridge calls (window.__pywebview_no_csrf__) remain unaffected. Exit criteria: No non-GET route in server mode is reachable without a valid token and an allow-listed Origin/Host.
- **WI-102** — Validation: Grep shows no remaining references; fast test tier still passes imports. Exit criteria: No dead auth scaffolding remains in security_audit.py/config_backend.py.
- **WI-106** — Validation: A job that ends 'failed' with a 'not found' message does not trigger a second POST /api/build (extends tests/e2e/build-failure.spec.js). Exit criteria: Build failures no longer silently double in duration or mask the original error.
- **WI-103** — Validation: Three synthetic MFJ plans per the finding's verification_method (pre-claim death, post-claim death, survivor under 60) hand-checked against SSA rules; Sheet 10 claim-age cache and survivor-bucket memo key invalidated. Exit criteria: Survivor SS income in every post-death year reflects COLA-indexed, age-gated benefit derived from the deceased's record, not a frozen death-year snapshot.
- **WI-104** — Validation: Synthetic plan, h dies at 80: in year death+2, std_ded equals the Single base plus one over-65 add-on (plus one senior bonus if 2028 or earlier). Exit criteria: No survivor year double-counts a deceased spouse's age-65 deduction or senior bonus.
- **WI-105** — Validation: MFJ both 70, no other income, 22% target: taxable income after conversion ~= 0.95x the 22% bracket top; hand-check one frozen-fixture year. Exit criteria: fill_to_bracket conversions actually fill the named bracket (taxable income), not AGI.

### Wave 2 — Data integrity & persistence

*Sequencing rationale:* Depends on the Wave-0 bootstrap for a single migration/workspace-root entry point; items touch disjoint files so run in parallel once WI-000 lands.

| Item | Change | Finding IDs | Depends on | Priority | Effort | Risk | Owner | Parallel group | Model tier |
|---|---|---|---|---|---|---|---|---|---|
| WI-201 | Create one replace_active_db(src) helper (PRAGMA integrity_check + required-table check, checkpoint-busy-flag verification, backup via SQLite backup API, os.replace, sidecar cleanup, then run the plan-data migration) and route both Load Saved Plan and snapshot restore through it. | ARC-005, QA-004 | WI-000 | high | M | medium | architect | 2-A | expert_reasoning |
| WI-202 | Route holdings/liabilities/HSA-schedule saves, plan-load CSV materialization and the secrets store through plan_file_io.atomic_write; add a lint/test forbidding bare write_text under input/, local_state/ and financial_trends_reporter/data/ (trends_log itself is handled in WI-203). | ARC-008 | WI-000 | medium | M | low | architect | 2-B | standard_reasoning |
| WI-203 | Merge PR #141's as_of_date (run day) / data_through_date (transaction day) split, switch append_or_replace_entry to atomic writes, and quarantine unparseable lines to a .rejected sidecar instead of dropping them on the next write. | QA-005, FIN-010 | — | high | M | low | quality | 2-C | standard_reasoning |
| WI-204 | Configure a rotating file handler at bootstrap, route _Logger and existing WARN prints through logging, and remove the hardcoded audit_log_enabled=False so audit events reach the existing SQLite audit_events table. | ARC-003 | WI-000 | medium | M | low | architect | 2-D | standard_reasoning |
| WI-205 | Bundle only input/demo (tracked, fictional) as the PyInstaller seed, set a per-user workspace root (e.g. %LOCALAPPDATA%) when frozen, and drop collect_all/requirements entries for matplotlib/PIL/cryptography/reportlab if confirmed unused at runtime. | ARC-007 | WI-000 | medium | L | medium | architect | 2-E | standard_reasoning |
| WI-206 | Route System Configuration's fmp_api_key/alpha_vantage_api_key rows through /api/secrets (the existing encrypted store) instead of system_config.csv, following the pattern already used for openai_api_key. | ARC-006 | — | medium | S | low | architect | 2-F | standard_reasoning |

**Validation and exit criteria:**

- **WI-201** — Validation: Loading a non-SQLite file returns an error with the active DB unchanged; after a restore no stale -wal remains; plan_routes.py no longer reports success when materialize_workspace_files fails. Exit criteria: Both DB-replacement code paths share one validated, checkpoint-verified helper.
- **WI-202** — Validation: A simulated failure mid-write leaves the original holdings/liabilities/HSA/secrets file intact. Exit criteria: No primary-user-data write in the listed modules is a bare write_text/write_bytes.
- **WI-203** — Validation: Two consecutive days with the same through_date keep two log lines; a history containing a corrupted line preserves or quarantines it on the next append, with an atomic write. Exit criteria: A day with no new transactions no longer overwrites the prior day's holdings/net-worth snapshot.
- **WI-204** — Validation: Calling _audit inserts an audit_events row; a pythonw desktop launch leaves a retrievable log file. Exit criteria: Security-relevant events (secret changes, plan replacement) and data-path failures are recorded somewhere a user or developer can retrieve after the fact.
- **WI-205** — Validation: A real frozen build's dist/_internal/input contains only demo files; an import-scan confirms the removed packages are unused; a frozen run writes to the per-user workspace, not dist/. Exit criteria: A shared exe folder no longer carries the developer's live financial data, and rebuilds do not delete user data.
- **WI-206** — Validation: Admin save of an api_key row calls set_secret and never writes system_config.csv; a test asserts the tracked key cells stay blank. Exit criteria: No provider API key can be persisted into a git-tracked file through the admin UI.

### Wave 3 — Tax / reference-data correctness

*Sequencing rationale:* Financial-planner findings sharing core.py and tax_law_v10.json form one sequential sub-chain (WI-301..305, WI-307) to avoid concurrent edits to the same statutory tables; findings in other files run in parallel to that chain. FIN-004/FIN-007 require qualified professional review of the underlying statutory values before merge, per financial-domain-governance.md.

| Item | Change | Finding IDs | Depends on | Priority | Effort | Risk | Owner | Parallel group | Model tier |
|---|---|---|---|---|---|---|---|---|---|
| WI-301 | Refresh tax_law_v10.json with verified 2025 OBBBA standard deductions and 2026 federal brackets/IRMAA tiers/Part B premium as dated rows; update the TCJA-sunset warning text now that OBBBA made the rates permanent. | FIN-004 | — | critical | M | medium | financial_planner | 3-chain | expert_reasoning |
| WI-302 | Encode the SALT cap schedule as absolute statutory years in tax_law_v10.json (2025-2030+), remove the orphaned c['salt_cap'], and tag the CA bracket rows with their real value year instead of indexing from TAX_BASE_YEAR. | FIN-005 | WI-301 | high | S | low-medium | financial_planner | 3-chain | expert_reasoning |
| WI-303 | Correct the age-83 RMD Uniform Lifetime divisor to 17.7 and add verified rows for ages 116-120+, replacing the linear extrapolation. | FIN-013 | WI-302 | low | S | low | financial_planner | 3-chain | standard_reasoning |
| WI-304 | Store irmaa_magi_current and filing status on each projection row; have irmaa_lookback_magi return (magi, filing) from the correct lookback row and assess against that year's filing-status table. | FIN-009 | WI-303 | high | M | low | financial_planner | 3-chain | expert_reasoning |
| WI-305 | Model NY/CO retirement-income exclusions per qualifying, living person instead of once per household, and gate eligibility on each member's own alive/age status. | FIN-006 | WI-304 | medium | M | low-medium | financial_planner | 3-chain | expert_reasoning |
| WI-307 | Add a dated non-enhanced ACA applicable-percentage table alongside the enhanced one in tax_law_v10.json, source the enhancement-through-year default from verified current law rather than a fixed 2026, and include non-taxable Social Security in ACA MAGI. | FIN-007 | WI-301 | medium | M | low-medium | financial_planner | 3-chain | expert_reasoning |
| WI-306 | Replace the local plan_start-based LTCG bracket-factor calculation in _ltcg_niit_caps with tax_kernel.bracket_factor_for_year, matching the consolidated indexing convention. | FIN-014 | — | low | S | low | financial_planner | 3-parallel | mechanical |
| WI-308 | At the first spousal death, raise home basis by the configured step-up fraction times (FMV - basis) for the deceased's share; apply the $500k Section 121 exclusion when the sale year is within two years of the first death and the survivor has not remarried. | FIN-008 | — | high | M | low-medium | financial_planner | 3-parallel | expert_reasoning |
| WI-309 | Add a household-level 'heir other taxable income' input used by effective_heir_ten_year_rate, and surface the resulting derived heir rate prominently next to the Roth recommendation. | FIN-012 | — | medium | S | medium | financial_planner | 3-parallel | expert_reasoning |
| WI-310 | Define one dollar-basis convention for Large Discretionary items (plan-start dollars, inflated to their year, matching Core spending), and inflate migrated legacy repeating rows so the PR #137 migration does not silently lower spending. | FIN-011 | — | medium | M | low-medium | financial_planner | 3-parallel | expert_reasoning |
| WI-311 | Rewrite the annual tax-maintenance runbook's checklist around adding new dated rows to tax_law_v10.json (covering every value family it holds), point contribution-limit guidance to the Plan Data fields, and correct tax_update_dashboard.csv's source/notes text. | DOC-001 | WI-301, WI-302 | medium | S | none | documentation | 3-doc | mechanical |

**Validation and exit criteria:**

- **WI-301** — Validation: Every dataset row compared against the IRS Rev. Proc. and CMS fact sheet for its value year; golden masters measured before regeneration per tools/regen_golden_master.py measure. Exit criteria: Qualified professional review of the OBBBA/2026 figures completed and tax_update_dashboard.csv status reflects a value-level check, not a date-only one.
- **WI-302** — Validation: salt_cap(2030,0)==10000 and salt_cap(2026,0)==40400 regardless of TAX_REFERENCE_YEAR; pin TAX_REFERENCE_YEAR in tests/conftest.py. Exit criteria: SALT cap and CA brackets no longer shift with the calendar run-date.
- **WI-303** — Validation: Table compared row-by-row with IRS Pub. 590-B Table III. Exit criteria: RMD_DIVISORS matches the published Uniform Lifetime Table through at least age 120.
- **WI-304** — Validation: Synthetic plan with $20k muni interest: year-3 irmaa_magi_used equals row[year-2].agi + 20k; survivor test (death 2030) assesses 2031-2032 on the correct filing-status table. Exit criteria: IRMAA assessment uses MAGI (not AGI) and the filing status that applied to the lookback year's return.
- **WI-305** — Validation: MFJ NY couple, both 66, $60k IRA distributions: expected exclusion $40k, not $20k. Exit criteria: Each qualifying living spouse gets their own exclusion amount.
- **WI-307** — Validation: PTC at 250% and 350% FPL for a confirmed non-enhanced year matches the IRS applicable-percentage table for that year. REQUIRES external legal-status verification of ACA enhanced-subsidy continuation before the default year is set. Exit criteria: Non-enhanced years no longer use enhanced-regime percentages; the enhancement-through-year default is a cited, dated value.
- **WI-306** — Validation: LTCG cap threshold equals the value tax_kernel.ltcg_tax_on_gain uses for the same year. Exit criteria: No remaining local re-implementation of bracket indexing outside tax_kernel.
- **WI-308** — Validation: Synthetic plan (h dies 2035, survivor sells 2036, basis $300k, FMV $1.3M, common-law): expected basis $800k, exclusion $500k, taxable gain ~= 0 before selling costs. Exit criteria: A survivor's home sale within the statutory window gets the full exclusion and a first-death basis adjustment.
- **WI-309** — Validation: Derived heir rate for a $1.5M IRA differs correctly between baseline $0 and baseline $150k Single; the Roth objective's legacy component responds. Exit criteria: The heir-tax-rate assumption is visible and editable rather than a hidden sole-income default.
- **WI-310** — Validation: One LD row ($10k, plan_start+10) produces a projection lump equal to 10k*(1+inf)^10. Exit criteria: LD amounts and the rest of the spending model share one disclosed dollar-basis convention.
- **WI-311** — Validation: Runbook re-read against src/taxes.py and src/tax_law.py; dry run confirmed with regen_golden_master.py measure. Exit criteria: The runbook no longer sends maintainers to a file the engine does not read for the values it names.

### Wave 4 — Data quality, dates & determinism

*Sequencing rationale:* Quality-expert findings independent of the Wave-3 tax chain; the two golden-master/determinism items can run alongside the date-parsing fix since they touch different files.

| Item | Change | Finding IDs | Depends on | Priority | Effort | Risk | Owner | Parallel group | Model tier |
|---|---|---|---|---|---|---|---|---|---|
| WI-401 | Add one shared date parser with a single century-pivot rule for DOB/retirement-date parsing; add a 'date' branch to validate_value that rejects unparseable formats and non-finite numbers; make a missing/blank member_1_dob (and member_2_dob when applicable) a hard error instead of a literal fallback; add a dob_yr plausibility gate. | QA-001 | — | high | L | medium | quality | 4-A | expert_reasoning |
| WI-402 | Add a dedicated parse-side test asserting h_dob_yr/w_dob_yr/h_ret_yr/h_mort_age/w_mort_age come from the frozen fixture's CSV rows, independent of whether they coincide with parse_client's fallback literals. | QA-002 | — | medium | S | low | quality | 4-B | mechanical |
| WI-403 | Replace the explicit datetime.date.today() passed into compute_current_year_overrides from workbook_builder.py, and the direct date.today() calls in optimization.py, with platform_runtime.today(); add a source-scan guard test forbidding date.today() in calculation-path modules (display-only dates allow-listed). | QA-003 | — | medium | S | low | quality | 4-C | standard_reasoning |
| WI-404 | Give the scalar/vectorized survivor-reconciliation test a pytest marker with a reduced n_sims (instead of an unset env var); bind pin provenance to the synthetic and full-row snapshot fixtures, not only the frozen-plan pin file; add direct tests for recover_spending_budget_from_seed. | QA-006 | — | high | M | low | quality | 4-D | standard_reasoning |

**Validation and exit criteria:**

- **WI-401** — Validation: Parametrized unit tests over the shared parser for 'M/D/YY', 'YYYY', ISO and blank inputs; a couple plan with a 2-digit DOB raises instead of silently projecting as a lone-survivor household. Exit criteria: DOB/retirement-date parsing uses one century rule everywhere, and a missing required date fails loudly.
- **WI-402** — Validation: A planted rename of 'member_1_dob' in parse_client fails the new test without moving any existing pin. Exit criteria: The golden master can detect a broken household-field read independent of WI-401's fix landing.
- **WI-403** — Validation: A pinned test runs the YTD blend on the frozen fixture under RETIREMENT_SYSTEM_FROZEN_TODAY and produces the same figures on any run date; guard test fails on any new bare date.today() in a calculation module. Exit criteria: The documented determinism seam actually holds for the production workbook-build path.
- **WI-404** — Validation: The survivor-reconciliation test runs in the normal suite (reduced scale); pin-provenance test fails if a synthetic/full-row pin changes without a marker; recover_spending_budget_from_seed has direct unit coverage. Exit criteria: All three High-severity gaps carried forward from the prior review are closed.

### Wave 5 — Accessibility & UX

*Sequencing rationale:* UX-004's modal fix depends on UX-001 landing first (otherwise the capture handler keeps pulling focus out of any trap); UX-003 depends on UX-002's label wiring for aria-invalid. Other items touch disjoint files/screens and run in parallel.

| Item | Change | Finding IDs | Depends on | Priority | Effort | Risk | Owner | Parallel group | Model tier |
|---|---|---|---|---|---|---|---|---|---|
| WI-501 | Scope moveToNextEntry (dashboard.js) to act only on focusableEntries() targets; return without preventDefault when the event target is not in that list or is inside [role=dialog]. | UX-001 | — | critical | M | low-medium | usability_accessibility | 5-chain | expert_reasoning |
| WI-502 | Replace the static exitModal/chartModal open/close with a shared helper (or the existing showSaveDiscardStayModal pattern) that moves focus in, traps Tab, closes on Escape, and restores focus to the opener; remove the unused #pathModal markup. | UX-004 | WI-501 | high | S | low | usability_accessibility | 5-chain | standard_reasoning |
| WI-503 | Change fieldHtml's label div to <label for=...> and give each control that id; add aria-required, aria-invalid and aria-describedby (pointing at unit/note/required badge); name toggle-switch checkboxes from the field label and mark YES/NO text aria-hidden. Apply the same pattern to admin.js settingControl. | UX-002 | — | critical | L | low | usability_accessibility | 5-A | expert_reasoning |
| WI-504 | Make error-kind showMessage calls persistent by default with role=alert/aria-live=polite on #actionMessage; move the raw 'ExcClass: msg' text into the existing technicalDetail disclosure under a plain-language summary; mark failing save-validation fields aria-invalid and link to them. | UX-003 | WI-503 | high | M | low | usability_accessibility | 5-A | standard_reasoning |
| WI-505 | Pass zoomable=True in webview.create_window; add an in-app text-size preference (100/115/130%, stored via /api/prefs) as the durable fix independent of WebView settings. | UX-005 | — | medium | S | low | usability_accessibility | 5-B | standard_reasoning |
| WI-506 | Replace hard-coded sourceStep/sourceTitle literals in the housing, allocation and income-streams optimizer JS with stepTitleById(sourceStep); fix the 'allocation' id to resolve to a real step/section; extend the PR #139 consistency guard to scan for stale page-name string literals. | UX-006 | — | medium | M | low | usability_accessibility | 5-C | standard_reasoning |
| WI-507 | Add LCV, ELTR, FCV, EFTR, QLAC, TLH and 'NPV of Future Taxes' to src/glossary.py with full names; use expanded column headers (abbreviation in parentheses) in the Strategy Workbench matrix and the workbook strategy sheets. | UX-007, DOC-007 | — | medium | S | low | usability_accessibility | 5-D | standard_reasoning |
| WI-508 | Have renderMain read window.RetirementNavigation.PLAN_INDEPENDENT_STEPS instead of its own inline (and incomplete) list. | UX-008 | — | low | S | low | usability_accessibility | 5-E | mechanical |
| WI-509 | Add aria-current="step" to the active stepbtn and aria-pressed to the search-scope and trends-timeframe toggle buttons. | UX-010 | — | low | S | low | usability_accessibility | 5-E | mechanical |

**Validation and exit criteria:**

- **WI-501** — Validation: Playwright: Tab from a .stepbtn moves to the next .stepbtn; Enter on a body button activates it; Tab inside showInAppConfirm stays inside the overlay. Exit criteria: Native Tab order and Enter/button activation work everywhere outside the intended field-advance controls.
- **WI-502** — Validation: Playwright: edit + click Exit places focus inside #exitModal; Escape closes it and returns focus to Exit; same for the chart modal. Exit criteria: No static dialog can be Tabbed out of or left open with no keyboard escape.
- **WI-503** — Validation: Node test rendering fieldHtml for text/choice/boolean/required rows asserts every control has a computed accessible name; manual NVDA/Narrator pass on one data-entry step. Exit criteria: Every plan-data and admin control has a programmatically associated label, required state and description.
- **WI-504** — Validation: Node test: showMessage(...,'error') does not schedule an auto-hide; e2e test: #actionMessage is still visible after 11s with role=alert after a failed build. Exit criteria: Screen readers are notified of errors, and users are not left with only a 10-second, unannounced, exception-text toast.
- **WI-505** — Validation: Launch desktop mode and confirm Ctrl+wheel changes zoom before/after; screenshot at 200% shows no lost content. Exit criteria: Low-vision users can enlarge the app beyond OS-wide scaling.
- **WI-506** — Validation: Node test: every data-step-id/sourceStep literal resolves through setStep to a real STEPS id or redirect key; manual check of housing and allocation optimizer jump buttons. Exit criteria: No optimizer-apply jump button sends the user to the wrong or an unknown page.
- **WI-507** — Validation: glossary.canonical_glossary() contains all listed terms; the Workbench matrix header text includes an expansion or linked glossary tooltip. Exit criteria: No headline decision metric appears as a bare, undefined acronym on the compare/decide screen or in the workbook.
- **WI-508** — Validation: Node test: with planLoaded=false and activeStep='workbook_formatting', renderMain output contains the Workbook Formatting page, not renderWelcome. Exit criteria: The two plan-independent-step lists cannot disagree again.
- **WI-509** — Validation: Node test asserting the active stepbtn has aria-current and the scope/timeframe buttons expose aria-pressed matching state. Exit criteria: Screen-reader users can tell which step, scope and timeframe are currently selected.

### Wave 6 — Privacy disclosure

*Sequencing rationale:* A documentation-only correction that can land any time; noted separately because it references an open architect/privacy decision (default pricing_mode) without being blocked by it.

| Item | Change | Finding IDs | Depends on | Priority | Effort | Risk | Owner | Parallel group | Model tier |
|---|---|---|---|---|---|---|---|---|---|
| WI-601 | Correct the end-user README's 'nothing is sent anywhere over the internet' claim, explain OFFLINE mode, and add a disclosure to the Pricing mode card in System Configuration about outbound market-data calls in LIVE mode. | DOC-002 | — | medium | S | none | documentation | 6-solo | mechanical |

**Validation and exit criteria:**

- **WI-601** — Validation: Grep for 'over the internet' finds only the corrected, accurate statement; the Pricing mode card text is re-read for the new disclosure. Exit criteria: No end-user-facing document makes a false network-privacy claim.

### Wave 7 — Documentation & maintainability cleanup

*Sequencing rationale:* Low-risk, low-priority text/tooling fixes with minimal cross-dependency; WI-702 (diagram regen) follows WI-701 (route-manifest fix) so the regenerated diagram reflects the corrected manifest.

| Item | Change | Finding IDs | Depends on | Priority | Effort | Risk | Owner | Parallel group | Model tier |
|---|---|---|---|---|---|---|---|---|---|
| WI-701 | Derive route_manifest.py's ROUTE_MODULES from app.url_map at import time (grouped by module/prefix) and add a test that every registered route is classified. | ARC-009 | — | low | S | low | architect | 7-chain | standard_reasoning |
| WI-702 | Regenerate SYSTEM_ARCHITECTURE_DIAGRAM.md from the corrected route manifest, remove /api/pdf from API_CONTRACTS.md (or document it as planned/removed), and add a diagram freshness test that reruns tools/generate_system_diagram.py and diffs the output. | DOC-008 | WI-701 | low | S | low | documentation | 7-chain | mechanical |
| WI-703 | Backfill FUNCTIONAL_SPEC.md and CURRENT_SYSTEM_DESIGN_SPEC.md to cover the housing optimizer, Next Housing Move, Plan Features, Spending Adjustments and the one-time Large Discretionary model; extend FEATURE_MARKERS to cover PRs #114-#139. | DOC-003 | — | medium | M | none | documentation | 7-A | standard_reasoning |
| WI-704 | Add a status table (PRs, merge SHAs) to the top of the taxonomy-and-spending-restructure spec, add the missing Task B5 addendum, and record #333's disposition. | DOC-004 | — | medium | S | none | documentation | 7-B | mechanical |
| WI-705 | Document the three-tier documentation layout rule (commit 88f6559) in CONTRIBUTING.md, add a documentation index, and move 'System Review.txt' out of the reference/ tier. | DOC-005 | — | low | S | low | documentation | 7-C | mechanical |
| WI-706 | Fix the ~20 dead documentation path citations found in code, tests and docs, starting with .claude/claude.md's GOLDEN_MASTER_RECOVERY_RUNBOOK.md link. | DOC-006 | — | low | S | low | documentation | 7-D | mechanical |
| WI-707 | Correct input/README_INPUT_PACKAGE.md's version label, input/demo/README.md's Open Demo Plan menu path, and its Illinois-only estate-tax claim (New York is also modelled). | DOC-009 | — | low | S | none | documentation | 7-E | mechanical |
| WI-708 | Write a plain-language change-record entry for each result-affecting PR (starting with #334/#336/#338) so users can tell a change in results apart from a change in their own data. | DOC-010 | — | low | S | none | documentation | 7-F | mechanical |

**Validation and exit criteria:**

- **WI-701** — Validation: New test fails on the current tree and passes once the manifest is derived. Exit criteria: route_manifest.py cannot drift from the registered routes again.
- **WI-702** — Validation: Diagram file counts match git ls-files counts; API_CONTRACTS.md no longer documents a route absent from workbook_routes.py. Exit criteria: Both artifacts match the current tree and a test would catch future drift.
- **WI-703** — Validation: Grep the specs for each feature name; FEATURE_MARKERS guard test extended and passing. Exit criteria: Both living specs describe every major feature currently in STEPS.
- **WI-704** — Validation: Checkbox state matches merged-commit reality for W-A/B/E/F; GOLDEN_MASTER_CHANGELOG.md's Task B5 reference resolves to a real task in the spec. Exit criteria: The spec's progress table is trustworthy without cross-checking git log.
- **WI-705** — Validation: CONTRIBUTING.md and the status lines are re-read to confirm the rule is written down, not only in a commit message. Exit criteria: A new contributor can find the layout rule in a document, not git log.
- **WI-706** — Validation: Re-run the path sweep and confirm it is empty. Exit criteria: No auto-loaded project instruction file cites a nonexistent path.
- **WI-707** — Validation: Files re-read and the click path re-checked against dashboard_decomp_checklist_closeout.js. Exit criteria: Ancillary READMEs match the current product.
- **WI-708** — Validation: A release file covering #334-#339 exists and names the affected inputs and direction of change. Exit criteria: Users have a plain-language record of model changes that move their results.



## 10. Validation plan

**Item-level validation** is stated per work item in Section 9 (a concrete test or hand-check per
item) and per finding in Section 5 (`verification_method`). None of it was executed in this review;
these are the checks that must be run once each item's code change lands. In particular:

- Every Wave-1 item has a synthetic-fixture test named in its validation field (e.g. FIN-001's
  three-plan SSA hand-check; UX-001's Playwright Tab/Enter/modal spec).
- Every Wave-3 tax-data item has a "compare against the primary source" step (IRS Rev. Proc./CMS
  fact sheet, Pub. 590-B Table III) in addition to a unit test, because these are reference-data
  values, not pure logic.
- Golden-master-affecting items (essentially all of Wave 1 and Wave 3, plus QA-001/QA-003) must
  follow this repository's own CLAUDE.md rule: run `tools/regen_golden_master.py measure` first,
  hand-verify at least one representative delta, and only then `regen --reason "..."` with an entry
  in `GOLDEN_MASTER_CHANGELOG.md`. Never enter a regenerate→run→regenerate loop.

**System-level acceptance criteria** (beyond the sum of item-level checks):

1. A synthetic MFJ plan with a first death before the higher earner's planned SS claim, run through
   both the scalar and vectorized Monte Carlo engines, produces a non-zero, COLA-indexed survivor
   benefit in both engines that agree with each other (closes the FIN-001/Wave-1 acceptance test at
   the system level, not just the unit level).
2. A `--mode server` instance, probed from a separate origin with no CSRF token, returns 403 on
   every non-GET, non-public route named in ARC-001's evidence (plan-data write, reference-file
   save, save-as, load-file) — this must be checked after Wave 1, not assumed from the unit-level
   fix alone, since `_security_gate` is a single chokepoint shared by all of them.
2b. Loading a plan through the desktop shortcut (not `python main.py`) after Wave 0 lands runs the
    same at-rest migration as the `main.py` path, verified against a fixture with a legacy flat
    category id.
3. A full keyboard-only walkthrough (Tab, Shift+Tab, Enter, Escape) of one complete data-entry step,
   one confirm dialog, and the exit-with-unsaved-changes flow, reaches and activates every control
   without the mouse — this is the system-level acceptance test for the whole Wave-5 accessibility
   cluster (UX-001 through UX-004), not just the unit-level Playwright specs per item.
4. `tools/regen_golden_master.py measure` run against the frozen fixture after all of Wave 1 and
   Wave 3 land shows deltas only in the years/fields each finding's `verification_method` predicts —
   any unexplained delta blocks sign-off.
5. A repository-wide re-run of the documentation-path sweep (DOC-006's method) returns empty.

**Note:** as this review is static and read-only, none of the above was executed here; this section
defines what "done" means, not a claim that it has been met. **Runtime behavior was not validated
during this review.**

## 11. Assumptions and open questions

**Technical assumptions:**
- The desktop bridge (`DesktopApi.request`) is assumed to be a legitimately trusted transport that
  never crosses HTTP, and is therefore exempt from the ARC-001 CSRF/Origin fix; this was not
  independently re-examined beyond confirming it routes through `test_client` rather than a socket.
- The `.rpx` saved-plan format is assumed to remain a raw SQLite file going forward, which the
  ARC-005/QA-004 validation helper's "required tables exist" check depends on.
- FIN-002's and FIN-003's fixes are assumed compatible with the existing `roth_conversion_and_agi_tax.py`
  and `plan_roth_conversion` call signatures; no interface change was assumed necessary.

**Jurisdiction / rule-year open questions (financial-domain-governance.md):**
- **FIN-004:** the correct 2025 OBBBA standard-deduction and 2026 federal bracket/IRMAA/Part-B
  figures cited in this review come from reviewer domain knowledge, not an opened IRS/CMS primary
  source, and require external verification before `tax_law_v10.json` is edited.
- **FIN-007:** whether ACA's enhanced premium-tax-credit subsidies are actually in effect for 2026
  under current law is explicitly unknown to this review and is a legal-status question requiring
  external verification — this finding's `inspection_status` is `requires_external_domain_verification`
  for exactly this reason.
- **FIN-006:** New York's true age-59½-vs-65 retirement-income-exclusion eligibility rule and
  Colorado's exact statutory mechanics were not opened from a primary source in this review
  (confidence is `medium` for this reason).
- **FIN-013:** the corrected RMD Uniform Lifetime Table values (age 83 and ages 116–120+) were not
  checked against IRS Pub. 590-B Table III in this review; only reviewer domain knowledge was used.
- **FIN-008:** the community-property vs. common-law basis step-up mechanics depend on the user-
  provided `basis_step_up_property_regime` input and state law, neither of which was independently
  verified here.

**External-facts open questions:**
- Whether any provider API key has ever actually been committed to `system_config.csv` in this
  repository's history was explicitly not checked (ARC-006's evidence deliberately did not read
  the file's values); a history check is a distinct follow-up.
- The disposition of backlog item `#333` (present nowhere in the taxonomy spec or `git log`) is
  unresolved and requires the user or the original author to confirm.
- Whether server/browser mode's exposure (ARC-001) is materially reduced in practice by current
  browser Local Network Access / Private Network Access protections was not tested.

**Where qualified professional review is required** (per financial-domain-governance.md, restated
from each finding): FIN-001 (SSA survivor rules), FIN-002 (bracket-fill sizing, dependent on
FIN-003), FIN-004 (2025 OBBBA / 2026 IRS-CMS figures), FIN-005 (SALT/CA statutory schedule),
FIN-006 (NY/CO exclusion mechanics), FIN-007 (ACA 2026 legal status), FIN-008 (§121/§1014/§2040(b)
and community-property regimes), FIN-009 (IRMAA lookback regulation), FIN-013 (IRS Pub. 590-B).
None of these findings should be treated as ready to implement from this report alone; each is an
arithmetic/rule-application defect claim that still needs the cited authority confirmed before the
corrected values or logic are shipped.

## 12. Review limitations

This review is static and read-only throughout. No test, build, or the application itself was run,
and no claim is made that any test passes or fails based on reading test code alone.

**CI was intentionally excluded from this review.**

**Runtime behavior was not validated during this review.**

**Uninspected or only-partly-inspected areas** (consolidated from all five experts' coverage
updates; see Section 3 for the full per-area residual uncertainty):

- The vectorized Monte Carlo projection body (`_mc_vectorized_projection`), the eight
  `withdrawal_cascade_*` modules, `optimize_roth_conversion_strategy` scoring, LTC/hybrid-LTC
  modelling, the housing-optimizer scoring and ZIP-screen estimation, state estate-tax calculators
  beyond IL/NY, capital-market-assumption and correlation files, and the stress-scenario sheets were
  not read in full.
- Monarch import/autoupdate, the YTD transaction upload, and workbook/report-package/PDF export
  content were not inspected.
- Frontend JS was not checked for duplicated financial-calculation logic.
- `planning_engines.py` (6,483 lines), `data_io.py`, and the reporting package were not re-audited
  for internal modularity or performance beyond size measurements; no profiling was performed.
- Colour contrast was computed only for core CSS tokens and a sample of badge/status pairs; chart
  palettes, print styles, and touch-target sizing were not evaluated. No screen-reader, keyboard, or
  zoom behavior was checked at runtime — WebView2 zoom/accelerator-key behavior (UX-005) was inferred
  from the locally installed third-party `pywebview` package source, not observed.
- `documentation/archive/` and most of `docs/superpowers/` were checked for status lines and
  citations only, not read in full; content accuracy of the Roth-conversion guide, the golden-master
  changelog/runbook, and in-app help beyond the glossary was not verified.
- Only a sample of the test suite (~447 Python and ~62 frontend files) was read; no test was run.

**Privacy/security limitations:**
- `system_config.csv` values and the local secret stores were **not read** in this review — only row
  labels were grepped to confirm the key rows exist. **No secret scanning was performed** against
  tracked files.
- Real household data under `input/` and `dist/_internal/input` was enumerated by file name and
  count only; no contents were opened. The user's private plan data was deliberately not read.
- Exploitability of ARC-001 under current browser Local Network Access / Private Network Access
  protections was not tested.

**GitHub-context limitations:**
- The repository has no GitHub issues; `list_issues`/`search_issues` returned zero results. The
  `#332`–`#339`/`item 322` backlog numbering is local/commit-message numbering, not GitHub issues,
  and its status could not be independently confirmed through GitHub.
- Full `pull_request_read` detail was fetched for only 8 pull requests (`#134`–`#141`) in this run;
  older merged PRs (`#82`–`#133`) are recorded from `list`/`search` metadata only (title, branch,
  base SHA, merge time), with no PR body text, so deferred items noted only in a PR body may exist
  and be undiscovered here. `list_pull_requests(state=closed)` was capped at 30, most-recently-
  updated first, so older closed/merged PRs below that window were not listed.
- PR descriptions (e.g. claimed "golden master +0.00", claimed pre-existing test failures) are
  author claims, treated as context only, never as independent verification.
- Nine third-party plugin MCP servers (figma, intercom, asana, atlassian, clickup, linear, monday,
  notion, slack) require authorization this session did not have; if any part of the `#332`–`#339`
  backlog lives in one of those trackers, it could not be seen.

## 13. Finding disposition appendix

This section records every register entry whose `verification_status` is not `confirmed` or
`partially_confirmed` (i.e. is not covered in Section 5), together with the reason. Cross-expert
duplicate decisions are recorded in full, with the conflict-resolution rationale, immediately below;
material `insufficient_evidence` items follow. No finding in this register carries `refuted` or
`superseded`, and none remains at the unexamined `unverified` default — every one of the 50 entries
received an explicit adversarial-verification disposition.

### Cross-expert duplicate resolutions (conflict records)

**Conflict 1 — ARC-004 vs. UX-009**
- **Alternatives considered:** keep ARC-004 only; keep UX-009 only; keep both as independent findings.
- **Decision criterion:** findings-schema.md's default priority hierarchy (functional correctness
  ranks above the usability/error-handling framing of the same code defect) plus completeness of
  impact analysis.
- **Decision:** keep **ARC-004** (medium severity); mark **UX-009** (low severity) `duplicate`,
  `duplicate_of: ARC-004`.
- **Rationale:** both describe the identical code path
  (`dashboard_decomp_build_lifecycle.js` `buildWithProgress`'s substring match on `"404"`/`"not found"`
  silently starting a second synchronous build) and the identical root cause. ARC-004 additionally
  traces the consequence through `desktop_api.py`'s global bridge lock (up to 30 minutes blocked in
  desktop mode) — a materially larger, independently-verified impact than UX-009 captured.
- **Consequence:** the Wave-1 work item (WI-106) is linked to ARC-004 and its acceptance criteria
  fold in UX-009's user-facing wording concern (the misleading "Progress telemetry unavailable"
  message).

**Conflict 2 — ARC-005 vs. QA-004**
- **Alternatives considered:** keep ARC-005 only; keep QA-004 only; keep both.
- **Decision criterion:** breadth of remediation scope and implementation-readiness (an existing,
  stated dependency chain).
- **Decision:** keep **ARC-005** (medium severity, architect); mark **QA-004** (medium severity,
  quality) `duplicate`, `duplicate_of: ARC-005`.
- **Rationale:** both describe `PlanFileService.load_file` replacing the live SQLite database after
  only an `exists()`/`is_file()` check. ARC-005 additionally compares the two DB-replacement code
  paths (`load_file` vs. `build_snapshot.py`'s `restore_sqlite_database_from_snapshot`) and shows
  they apply different, non-overlapping safeguards, proposing one shared validated helper — a
  broader and more implementation-ready fix than QA-004's narrower checkpoint-busy-flag critique.
- **Consequence:** the Wave-2 work item (WI-201) is linked to ARC-005, and its acceptance criteria
  explicitly fold in QA-004's two distinct sub-findings: the unread `wal_checkpoint` busy flag, and
  `plan_routes.py` reporting success despite a materialize failure.

**Conflict 3 — QA-005 vs. FIN-010**
- **Alternatives considered:** keep QA-005 only; keep FIN-010 only; keep both.
- **Decision criterion:** verification depth (an independently fetched PR #141 diff) and technical
  breadth (write-atomicity and corrupt-line-loss included, not just the key-collision bug).
- **Decision:** keep **QA-005** (medium severity, quality); mark **FIN-010** (medium severity,
  financial_planner) `duplicate`, `duplicate_of: QA-005`.
- **Rationale:** both describe `trends_metrics.py`'s `as_of_date` being keyed on the transaction
  date rather than the run date, causing `trends_log.py`'s `append_or_replace_entry` to silently
  overwrite the prior day's snapshot. QA-005 independently fetched and confirmed PR #141's actual
  diff scope and additionally substantiates a non-atomic whole-file rewrite and permanent loss of
  unparseable history lines on the next write — a materially broader, more thoroughly verified
  treatment of the same underlying persistence defect.
- **Consequence:** the Wave-2 work item (WI-203) is linked to QA-005/FIN-010 jointly and merges
  PR #141's key fix with an atomic-write conversion and corrupt-line quarantine; FIN-010's financial
  framing (daily net-worth/holdings history loss undermining the trends report) is retained as the
  item's business-impact justification.

**Conflict 4 — UX-007 vs. DOC-007**
- **Alternatives considered:** keep UX-007 only; keep DOC-007 only; keep both.
- **Decision criterion:** severity and directness of verified evidence at the point of greatest
  financial-decision consequence.
- **Decision:** keep **UX-007** (medium severity, usability_accessibility); mark **DOC-007** (low
  severity, documentation) `duplicate`, `duplicate_of: UX-007`.
- **Rationale:** both describe the headline decision metrics LCV/ELTR/FCV/EFTR appearing with no
  glossary entry. UX-007 is rated medium severity because the undefined acronyms sit on the Strategy
  Workbench compare/decide screen where users act on the numbers, and its evidence directly quotes
  the literal `<th>LCV</th>` markup at that screen; DOC-007's confirmation was a grep-only check
  against `glossary.py` covering a wider but shallower set of missing terms (also QLAC, TLH, "NPV of
  Future Taxes").
- **Consequence:** the Wave-5 work item (WI-507) is linked to UX-007/DOC-007 jointly and its scope
  includes DOC-007's wider term list (QLAC, TLH, "NPV of Future Taxes") alongside UX-007's four
  Workbench acronyms.

### Material insufficient-evidence items

- **DOC-005** (documentation, severity low) — "The documentation layout rule exists only in a commit message and was broken once docs/superpowers/ came back". Did not independently open CONTRIBUTING.md:85-90, 'System Review.txt', or the abandoned 2026-09-17 plan file to verify the specific claims (that CONTRIBUTING.md calls an archived plan 'current', that the skill-prompt copy is misfiled, or that PR #125 was closed unmerged). Given time constraints I was unable to verify these citations directly. The finding is plausible and consistent with the pattern of documentation drift confirmed elsewhere in this batch (DOC-004, DOC-006), but I cannot mark it confirmed without having opened the cited evidence myself, per the adversarial-verification standard of citing only evidence opened in this run.
- **DOC-010** (documentation, severity low) — "No user-facing record of changes that move plan results". Opened documentation/reference/release_notes/index.md:1-15 and confirmed via `ls` that only 'index.md' exists in that directory — no per-release files, consistent with the finding's claim that the promised per-release notes convention has not been followed. However, I did not independently verify the sheets_summary_builder.py 'Assumptions block' claim, the GOLDEN_MASTER_CHANGELOG.md 'developer-only' characterization, or the dashboard_decomp_large_discretionary.js in-app notice for #336. The directory-emptiness check partially supports the finding (medium confidence would be reasonable), but given the more speculative framing of user impact and unverified secondary evidence, and this being a fairly subjective 'completeness' claim, I keep this at insufficient_evidence for full confirmation while noting partial support was found.

### Refuted / superseded / unverified

None of the 50 register entries carries `refuted` or `superseded`, and none remains at the
unexamined `unverified` default — every entry received an explicit adversarial-verification
disposition of `confirmed`, `partially_confirmed`, `duplicate`, or `insufficient_evidence`.

## 14. Financial planner sign-off

**Verdict:** `approved-with-changes`. `material_changes: false` — the planner requested two wording/
completeness corrections and raised no objection to any finding's diagnosis, severity, priority
classification, recommendation, architecture, scope, dependencies, test requirements, or stated
assumptions for FIN-001 through FIN-014.

**Sign-off basis (planner's own summary):** the planner read this draft in full — the executive
summary, scope/methodology, coverage matrix, health assessment, all 14 `FIN-*` findings' complete
write-ups plus the recommendation, target design, Wave 1/Wave 3 implementation items, assumptions/
open questions, review limitations, and the finding-disposition appendix — and read `findings.json`'s
full `FIN-*` entries plus a representative sample of `ARC-*` entries. It then independently
re-opened primary source for the two headline high-severity findings and a representative sample of
the medium/low ones: `src/projection_stages/income.py:391-411` (FIN-001), `src/planning_engines.py:2118-2166`
and `:2272-2274` (FIN-002), `src/core.py:646-653` and `src/tax_kernel.py:239-241` (FIN-013),
`src/core.py:890-926` (FIN-009), and `src/core.py:1030-1040` (FIN-006) — every claim matched this
report's evidence citations and observed behavior precisely, including the specific line ranges and
variable names quoted.

**Requested changes and their resolution:**

- **PSO-1** (non-material, wording) — Section 1's executive summary listed the findings gated on
  qualified professional review as "FIN-001, FIN-002, FIN-004, FIN-005, FIN-007, FIN-008 and
  FIN-009", omitting FIN-006 (NY/CO exclusion mechanics) and FIN-013 (IRS Pub. 590-B RMD table),
  both of which Section 11's authoritative, per-finding-governance-field list correctly includes.
  **Resolution: applied.** Section 1's list now reads FIN-001, FIN-002, FIN-004, FIN-005, FIN-006,
  FIN-007, FIN-008, FIN-009 and FIN-013, matches Section 11 exactly, and points the reader to
  Section 11 for the governance basis.
- **PSO-2** (non-material, wording/scope) — FIN-008's printed "Observed behavior" and "Impact" text
  did not reflect the finding's own adversarial-verification finding that plans with
  `qss_dependent=True` keep MFJ filing status (and the $500k §121 exclusion) for up to two years
  after the first death, partially narrowing the defect for that subset of households; the nuance
  lived only in the verification rationale. **Resolution: applied.** FIN-008's "Observed behavior"
  now states the QSS-filing-status bound directly and notes it is not aligned with the actual statute
  (which requires no dependent) and so does not reach the common case; "Impact" now states which
  part of the defect (the exclusion amount, not the missing first-death basis step-up) is narrowed
  for QSS-dependent households.

**Impact analysis for material changes:** none — both requested changes are wording/completeness
corrections (`material: false`) that align cross-references already present elsewhere in the report;
neither changes a finding's severity, confidence, verification_status, recommendation, dependencies,
implementation items, or wave placement, so no coverage-matrix, wave, or validation-plan update was
required. PSO-1 was a report-draft.md prose change only (Section 1's list now matches Section 11's
existing, unchanged governance fields for FIN-006 and FIN-013). PSO-2's `observed_behavior` and
`impact` text was updated in both report-draft.md and the FIN-008 entry in findings.json, so the two
stay consistent; findings.json's `verification_rationale`-equivalent content, severity, confidence,
and verification_status for FIN-008 were left unchanged, and the register still validates against
findings.schema.json (0 schema errors on re-check).

**Re-verification of material changes:** none — the planner proposed no material change, so no
re-verification pass was run or required.

**Unresolved dissent (carried forward, not resolved by this sign-off):** the planner's sign-off
explicitly does **not** certify the numeric accuracy of the replacement statutory values this report
cites from reviewer domain knowledge, and this residual uncertainty remains open:

- The 2025 OBBBA standard deduction and senior bonus, and the 2026 federal brackets, IRMAA tiers,
  and Part B premium (FIN-004);
- The SALT-cap schedule and the CA bracket vintage (FIN-005);
- New York's and Colorado's exact retirement-income-exclusion eligibility mechanics (FIN-006);
- ACA's 2026 enhanced-subsidy legal status (FIN-007);
- The IRS Pub. 590-B Table III Uniform Lifetime divisors (FIN-013).

Per `financial-domain-governance.md` and this report's own Section 11, each of these values requires
independent primary-source or qualified-professional confirmation before `tax_law_v10.json` or
`state_tax.csv` is edited to implement the corresponding finding. `approved-with-changes` approves
the diagnosed code defects, their severity/priority classification, and the proposed remediation
approach for FIN-001 through FIN-014; it should not be read as resolving this dissent, and none of
the two applied wording changes (PSO-1, PSO-2) touches or narrows it.
