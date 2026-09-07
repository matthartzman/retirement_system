# System Review — Retirement Planning System (2026-09-07)

**Scope:** the entire system. **Depth:** deep. **This run proceeded without the `Workflow` tool** (unavailable in this session) — reconnaissance, expert panels, adversarial verification, and synthesis were performed manually through delegated sub-agents, applying the same read-only boundary, CI exclusion, and evidence-citation rules the tool would otherwise enforce.

### How to read this document

This is a **follow-up deep review**, one week after the previous full review (`documentation/reports/SYSTEM_REVIEW_2026-08-31.md`, 50 findings, 3-wave plan). That plan's Wave 1 (17 items) is fully merged (PR #84). This review's first job was to verify Wave 2 (21 items) and Wave 3 (14 items) against current source — not against PR descriptions — and its second job was to independently re-review the whole system, including five feature PRs (#86–90) merged since the last review that were never reviewed. Findings below are numbered independently of the prior document's A/U/D/Q/F scheme to avoid collision; each states whether it is new or a correction to prior-review scope.

---

## 1. Executive summary

**Assessment.** Wave 2/3 execution has been unusually faithful to the *intent* of the prior review, not just its letter — the tax-kernel extraction found and fixed two real bugs while consolidating, the Roth conversion-window extension is defaulted rather than forced, and New York's estate tax now includes the three-year gift add-back the plan called for. Of 35 Wave 2/3 items tracked, **26 are done, 6 are partial, 2 are not done, and 1 was consciously superseded** (documented in code, not silently dropped).

But the system was also given five new feature surfaces since the last review — a Monarch transaction auto-import job, a standalone `financial_trends_reporter` app, a Roth `PHASE_VARYING` strategy, an E2E fix, and a spending-annualization toggle — and **none of them were reviewed before this pass**. That is where the risk is concentrated. This review's most consequential finding is a **Critical security defect**: the local API server sends `Access-Control-Allow-Origin: *` on every response with no authentication or CSRF check, meaning any web page the user's browser visits while the app is running can read and write the full household plan (SEC-1). Two more High-severity security issues were introduced by the Monarch subsystem (an unvalidated executable path, and unencrypted plan/credential data now leaving the machine in every build backup).

On the calculation side, the shipped Monte Carlo engine's own parity gate against its "exact" oracle was widened from 1 to 5 percentage points in the most recent commit, while the engine's own status field reads `APPROXIMATE_PENDING_SCALAR_PARITY` and a documented internal measurement puts the true drift at 6.05pp at higher fidelity — above even the widened gate (N1, High). A second financial-domain defect, present since before this review's window but newly surfaced, causes Social Security claim age to be computed by calendar-year subtraction rather than by month, misattributing up to ~11 months of early/delayed-credit adjustment — a permanent, lifelong benefit error (N2, High).

**Risks/opportunities.** The risks are concrete and cheap to close: none of the three security findings require an architecture change, and the two financial-domain findings are narrow, well-isolated fixes with existing test infrastructure to verify them. The opportunity is that this review's own delta — five unreviewed feature PRs producing a disproportionate share of new findings — is a repeatable failure mode with a repeatable fix: this team should not ship a feature PR without the review's existing guard mechanisms (the `no_internal_keys_on_screen` test, the frontend-source-grep freeze, the spec-currency claim) extended to cover it.

**Planner verdict:** see §14. The financial-domain findings (N1, N2, N3, N4) are dispositioned there; none block continued operation of the tool, but N2 should not ship another week unfixed given its permanence.

**Top 5 recommendations:**
1. Fix SEC-1 (wildcard CORS) immediately — it is a one-file, low-risk change that closes the only finding in this review capable of exfiltrating the entire plan to an arbitrary third party.
2. Fix N2 (SS claim-age month precision) — small, isolated, and the error compounds for the rest of a household's life.
3. Resolve the MC engine parity question (N1) with a real diagnostic rather than a wider tolerance, before the next feature PR touches either engine.
4. Close SEC-2 and SEC-3 (Monarch execution-path validation; backup credential exclusion) in the same pass — both are small, both were introduced by the same subsystem.
5. Correct the record on Wave 3's "ongoing" tracks (3.10–3.13): two have net-negative or flat progress on their own stated metrics while being reported as advancing. Re-scope with measurable acceptance criteria before continuing to schedule work against them.

---

## 2. Scope and methodology

- **Scope:** the entire system, as requested. **Depth:** deep (five-expert panel at `expert_reasoning` tier; verification at `standard_reasoning` tier).
- **Date:** 2026-09-07. **Repository:** `matthartzman/retirement_system`, branch `claude/system-review-deep-i97tkv`, HEAD `b4d2d3e2ab5d25cc160554d9e3f1007e9f4a2a2f`. Working tree clean at review start.
- **GitHub context:** 0 open issues, 0 open PRs at review time. Most recent 15 merged PRs (#76–#90) reviewed for provenance; PR #84 (prior full review + Wave 1), #85 (Wave 2 partial), #86–90 (post-review features) specifically inspected.
- **Roles and model tiers used:** Architect + Financial Planner (combined panel, `expert_reasoning`/opus), Architect + Security/Data (combined panel, `expert_reasoning`/opus), Usability + Documentation + Quality (combined panel, `expert_reasoning`/opus), Verification (`standard_reasoning`/sonnet), Synthesis (this document, sonnet).
- **Phases:** (1) reconnaissance — prior-review ingestion, GitHub context, repo structure; (2) three parallel expert panels, each independently verifying assigned Wave 2/3 items against current source and conducting a fresh domain review including PRs #86–90; (3) adversarial verification of all 9 Critical/High findings; (4) synthesis (this document).
- **Runtime-validation status:** none performed. No tests were executed, no build was run, and no UI was exercised in a browser. All findings are static-evidence findings (file:line citations) or narrative citations. This is a material limitation — see §12.
- **CI exclusion:** CI was intentionally excluded from this review.

---

## 3. Coverage matrix

| Area | Status | Evidence basis | Expert | Findings | Residual uncertainty |
|---|---|---|---|---|---|
| Architecture (engine composition, pipeline) | Inspected, findings identified | `src/projection_pipeline.py`, `src/projection_stages/deterministic_engine.py`, `src/tax_kernel.py`, `src/strategy_sweep.py` | Architect | N5, ARC-1, ARC-3 | Deterministic engine's remaining 13 unregistered stages not individually re-audited |
| Calculation engine — tax | Inspected, no material new finding (prior fixes confirmed) | `src/tax_kernel.py`, cross-referenced consumers | Architect/Planner | (Wave 2 status table) | — |
| Calculation engine — Monte Carlo | Inspected, Critical-adjacent finding identified | `src/planning_engines.py` (~4453, ~6127-6145, ~6335), `tests/test_monte_carlo_default_engine_mode.py` | Financial Planner | N1 | True drift at production sim counts not independently re-measured by this review (relied on in-repo docstring/commit evidence) |
| Social Security | Inspected, High finding identified | `src/data_io.py:446-449,713-714`, `deterministic_engine.py:1061-1063,1081` | Financial Planner | N2 | — |
| RMD / estate / beneficiary logic | Inspected, findings identified | `src/core.py`, `src/planning_engines.py`, `src/after_tax.py` | Financial Planner | N3, N4, N5, N6 | — |
| Data integrity / persistence (4-store architecture) | Inspected, findings identified | `src/server/app_core.py:1846-1913`, `src/config_backend.py` | Architect | N7, ARC-2 | — |
| Security / privacy | Inspected, Critical finding identified | `src/server/app_core.py`, `src/permissions.py`, `src/monarch_autoupdate.py`, `tools/backup_to_onedrive.py`, `src/secrets_store.py` | Security | SEC-1 – SEC-5 | Not independently penetration-tested; static evidence only |
| New subsystem: Monarch auto-import | Inspected, findings identified | `src/monarch_autoupdate.py`, `src/monarch_autoimport_job.py`, `src/monarch_db_sync.py`, `src/ytd_tracking.py`, git history for credential incident | Architect/Security/Planner | SEC-2, SEC-3, N9, UX-103, UX-104 | Monarch sign-convention (N9) is insufficient-evidence, not confirmed |
| New subsystem: financial_trends_reporter | Inspected, findings identified | `financial_trends_reporter/**` | Architect/Usability/Quality | ARC-4, UX-102, UX-106, QUA-302 | Not run in a browser |
| Frontend UI / accessibility | Inspected, findings identified | `frontend/index.html`, `frontend/css/dashboard.css`, `frontend/js/*` | Usability | UX-101, UX-105, UX-107 | Not verified with an actual screen reader |
| Documentation | Inspected, findings identified | `documentation/FUNCTIONAL_SPEC.md`, `documentation/readme/README.md`, `PROJECT_MANIFEST.md`, `documentation/OPTIMIZATION_REFACTOR_STATUS.md` | Documentation | DOC-201 – DOC-205 | Not every one of the ~30 documents in `documentation/` was read in full |
| Testing / test quality | Inspected, findings identified | `tests/` suffix census, new-feature test files | Quality | QUA-301 – QUA-303 | Test *outcomes* (pass/fail) explicitly out of scope; only static test-quality assessed |
| Configuration / module gating | Inspected, no new finding | `src/module_catalog.py`, `system_config.csv` | Architect | — | — |
| Frontend module architecture (Wave 3 item 3.11) | Inspected, finding identified | `frontend/js/modules/phase3_module_manifest.js`, script-tag count | Architect | ARC-1 | — |
| Reporting layer (`results_model`, `workbook_common`) | Inspected, findings identified | `src/results_model.py`, `src/reporting/workbook_common.py` | Architect | N8, ARC-5, ARC-6 | — |
| GitHub work context | Inspected | `list_issues`, `list_pull_requests`, `list_releases` | Orchestrator | 0 open issues/PRs; PRs #76–90 reviewed for provenance | — |
| Performance | Partially inspected | Build-time budget references in prior review only; not independently measured | Architect | — | No new performance measurement taken this cycle |
| CI | Not applicable | — | — | — | `CI was intentionally excluded from this review.` |

---

## 4. System health assessment

**Architecture.** Materially improved since 2026-08-31: the dual-import shim, dead `src/server/features/`, and the dead `dashboard_ui/template.py` are gone; the tax kernel is real and load-bearing. The weak spot is the set of tracks self-labeled "ongoing" (3.10–3.13): two of four show flat or negative progress on their own declared success metric while consuming real commits, and one (3.11, frontend module extraction) is recorded as complete against a criterion ("script-tag list shrinks") it did not meet — the count grew from 25 to 37. This is not dishonesty; the manifest discloses its actual scope (converting `<script>` tags to `type="module"` for load-order safety, not literal ES imports) — but the item's own success criterion in the prior review was not met, and reporting it as "complete" will stop it from being scheduled again.

**Usability/accessibility.** The core app's help-pane and coordination-card work from Wave 2 landed well. The regression is entirely in new surfaces: an icon-only Annualize toggle that conveys a budget-overwrite-triggering state by color alone (no `aria-pressed`, hover-only tooltip), and a second, independently-styled frontend (`financial_trends_reporter`) with no accessibility affordances and an unescaped-user-data injection into SVG markup.

**Documentation.** The single document asserted as most current — `FUNCTIONAL_SPEC.md`, dated 2026-08-29, explicitly claiming to describe "the system as the code currently behaves" — omits all five features shipped since that date, including a new sibling application. The shipped end-user README still says "v11" after a v12 version bump whose own tooling was hardened for comprehensiveness in the same session.

**Quality/testing.** The test pyramid continues to move in the intended direction (regression-suffix files down from 159 to 94, functional up 36→118, unit up 3→29). New engine features (PHASE_VARYING Roth, `no_annualize`) have solid, well-named unit/functional coverage. New UI features (Monarch settings card, trends-reporter charts) have zero browser-level (e2e) coverage despite exercising exactly the fetch/module/global-bridge pattern that has caused a real production outage before in this codebase.

**Financial correctness.** The two most consequential findings in this review are here: an under-verified Monte Carlo parity gap on the flagship probability-of-success number (N1), and a systematic Social Security claim-age error (N2) that is small in any one year but permanent. Both are narrow and fixable without architectural change. Everything else in the financial domain — the tax kernel, the Roth window extension, New York estate tax, EDB beneficiary classes — was independently re-verified this cycle and found sound.

**Data integrity.** The four-store plan-data architecture (SQLite × 2, CSV, JSON/YAML) is unchanged in shape; item 2.5 (collapsing the two SQLite stores) was explicitly and reasonably declined in code with a documented cost measurement, but that decision has not been reconciled back into the review's own tracked status (N7/ARC-2).

**Security/privacy.** The weakest dimension this cycle, and newly so: SEC-1 (wildcard CORS) is a pre-existing latent defect this review is the first to surface; SEC-2 and SEC-3 were introduced by the Monarch subsystem in the last week. All three are narrow fixes. The local-only, single-user design itself is sound and is not being second-guessed here — the findings are about specific places where that trust boundary is punched through, not about the boundary's existence.

**Performance.** Not independently re-measured this cycle; no new finding.

---

## 5. Material findings

Findings are grouped by severity. Each carries its full required field set; Low-severity findings are stated briefly per the skill's convention. Verification dispositions from the adversarial pass are inlined where a Critical/High finding was checked.

### Critical

#### SEC-1. Wildcard CORS with no authentication exposes the entire plan to any web page the user visits
- **Expert:** Security · **Category:** security/privacy · **Severity:** Critical · **Confidence:** high
- **Inspection status:** inspected, finding identified · **Verification status:** **confirmed** (adversarial pass, independent file read)
- **Evidence:** `src/server/app_core.py:1971-1974` (`_local_cors` sets `Access-Control-Allow-Origin: *` unconditionally on every response); `src/server/app_core.py:1935-1959` (`_security_gate`'s SaaS token-auth rejection removed as "unreachable" in LOCAL mode); `src/permissions.py:9,22` (`LOCAL_PERMISSIONS` grants full access to any request); `main.py:105,121` (binds `127.0.0.1`, confirmed **not** a mitigation since the attacker path is the user's own already-trusted browser).
- **Observed behavior:** While the desktop app runs, any web page the user's browser has open can `fetch()` `http://127.0.0.1:<port>/api/...` cross-origin, and the wildcard header lets the browser expose the response to that page. No auth or CSRF check stops it.
- **Impact:** full read and write of household plan data — names, DOBs, account balances, SSA benefits, insurance premiums, transaction history — to an arbitrary third-party origin, plus the ability to mutate the plan.
- **Affected workflows/scenarios:** any session where the app is running and the user browses the web (the normal case; the app auto-opens a browser tab).
- **Root cause:** a SaaS-era CORS relaxation was kept after the SaaS auth it depended on was deleted as dead code.
- **Options:** (1) delete `_local_cors` entirely — the UI is same-origin, nothing legitimate needs it; risk: breaks a hypothetical `file://`-opened dashboard. (2) Echo `Origin` only when it exactly matches the local server's own origin, with `Vary: Origin`. (3) Keep CORS but start validating the CSRF token already minted (`security_audit.py:285`) on state-changing routes — fixes writes only, not the larger read-exfiltration half.
- **Recommendation:** Option 1, with Option 3 as defense in depth. Confirm first that no shipped launcher opens `frontend/index.html` via `file://`.
- **Dependencies:** none.
- **Implementation considerations:** one file, one function.
- **Risk of change:** low-medium — same-origin UI unaffected; a `file://` workflow, if one exists, would break loudly and immediately (good failure mode).
- **Verification method:** from a page on an unrelated origin, `fetch('http://127.0.0.1:<port>/api/plan/...')` must fail with a CORS error before and after the in-app UI is confirmed to still function end to end.
- **Linked implementation-item IDs:** W4-1.

### High

#### N1. The shipped Monte Carlo engine's parity gate against its own "exact" oracle was widened rather than diagnosed, and the disclosed drift now exceeds it at production fidelity
- **Expert:** Architect + Financial Planner (joint) · **Category:** calculation engine / financial correctness · **Severity:** High · **Confidence:** high
- **Inspection status:** inspected · **Verification status:** **confirmed**, with a correction — the 6.05pp figure is honestly disclosed in-repo (test docstring and commit message for `b4d2d3e`), not hidden; this is a transparently-documented, gated risk rather than a silent one. Severity confirmed at High (not escalated to Critical) on that basis.
- **Evidence:** `tests/test_monte_carlo_default_engine_mode.py` (~line 92) — parity tolerance raised from 1.0pp to 5.0pp; its own docstring records that raising `mc_sims` from 200 to 2000 grows the measured drift from 3.5pp to 6.05pp. `src/planning_engines.py` (~4453) exact_scalar returns `mc_approximation_status: 'EXACT'`; (~6335) vectorized (the shipped default per Wave 1 item 1.1) returns `'APPROXIMATE_PENDING_SCALAR_PARITY'`. The approximations are named in-code: home-equity contingency (~6127-6131) and survivor-bucket economics (~6134-6145).
- **Observed behavior:** the shipped test passes only because it runs at `mc_sims=200`; at the sim count the docstring itself uses to characterize true drift (2000), the measured 6.05pp exceeds the gate that was just widened to 5.0pp.
- **Impact:** "probability of success" is the product's headline number. Wave 1 item 1.1 flipped the shipped default to the approximate engine on the strength of a 1pp parity claim that no longer holds; the justification for that flip is not currently re-evidenced by a passing gate at realistic fidelity.
- **Affected workflows/scenarios:** every build; the Roth and SS sweeps, which each embed a 200-sim MC per candidate and so inherit the same directional bias; the KPI snapshot series.
- **Root cause:** two independent MC engine implementations (prior finding A1); the parity test measures agreement on a summary statistic, not on mechanism, so a failure cannot be localized without a separate diagnostic.
- **Options:** (1) diagnose the gap directly — compare both engines on identical seeded return paths and diff year-by-year `liquid`/`unfunded` for the worst-disagreeing path; the home-equity lag and survivor-bucket flows are named, testable suspects. (2) Restrict the gate to the sub-mechanism that is actually exact (1pp with home-equity/survivor-economics disabled) and keep a separately-labeled, wider tolerance for the full configuration. (3) Surface `mc_approximation_status` and a "±Xpp vs. exact engine" band on the KPI tile and in the workbook.
- **Recommendation:** Option 2 immediately (test-only, restores a meaningful gate), Option 3 in the same pass (consistent with this codebase's existing disclosure habits), Option 1 scheduled next.
- **Risk of change:** none for 2/3; Option 1 may move golden-master pins if the wrong engine turns out to be the default.
- **Verification method:** re-run the parity comparison at 200/2000/5000 sims with home-equity contingency and survivor economics toggled off; drift should be flat in N and near zero.
- **Linked implementation-item IDs:** W4-2.

#### N2. Social Security claim age is computed by calendar-year subtraction, not by month — a permanent, lifelong benefit-amount error
- **Expert:** Financial Planner · **Category:** financial-domain correctness (Social Security) · **Severity:** High · **Confidence:** high
- **Inspection status:** inspected · **Verification status:** **confirmed** (adversarial pass, independent file read of both cited sites)
- **Evidence:** `src/data_io.py:446-449` (`_ss_claim_from_date_or_age` returns `claim_year - dob_yr`); `:713-714` and `src/projection_stages/deterministic_engine.py:1061-1063,1081` feed that integer directly into the SSA benefit-factor table lookup, clamped to `[62,70]`. No fractional-month correction exists on this value; the function's own docstring confirms the derivation is deliberate. A separate helper (`_ss_first_claim_year_month_fraction`) prorates only the *first calendar year's dollar total*, not the age used for the table lookup itself.
- **Observed behavior:** a claimant born November 1960 with a claim date of March 2027 is 66 years 4 months at claim but is recorded as claim age 67, applying the full-retirement-age factor rather than an interpolated one.
- **Impact:** SSA's reduction/delayed-credit schedule is 5/9%–2/3% per month; an 11-month misattribution is roughly 5.5–7.3% of PIA, permanently, propagating into the survivor benefit and into the 81-pair claiming-age recommendation the tool produces.
- **Affected workflows/scenarios:** every household with an explicit `claim_date`; SS claim-age optimization; survivor-household projections; taxable-SS calculations.
- **Root cause:** commit `5958137` added month precision for first-year cash proration but left the benefit-amount derivation on the pre-existing integer-age lookup — the two halves of one fix use different time resolutions.
- **Assumptions/rule-year:** SSA reduction/delayed-retirement-credit factors per 20 CFR 404.313/404.410, unchanged for the modeled period.
- **Options:** No credible alternative; this is a correctness defect. The choice is only in the fix's shape: (a) compute a fractional claim age and let `_ss_claim_factor` interpolate monthly (it is already month-denominated); (b) keep the integer lookup but compute the age with a month comparison, removing the systematic bias while still rounding to whole years.
- **Recommendation:** (a) — small change at one derivation site plus its JS mirror in `dashboard_decomp_income_streams.js`.
- **Risk of change:** moves golden-master SS figures for any fixture whose claim month differs from birth month; requires pin regeneration with a changelog entry.
- **Verification method:** a unit test asserting a 1960-11 DOB with claim_date 03/2027 produces a claim age of 66y4m and a benefit factor strictly between the age-66 and age-67 factors.
- **Linked implementation-item IDs:** W4-3.

#### SEC-2. The Monarch auto-import job resolves and executes an interpreter from unvalidated, browser-reachable config
- **Expert:** Security · **Category:** security · **Severity:** High (Critical if chained with SEC-1) · **Confidence:** high
- **Inspection status:** inspected · **Verification status:** **confirmed**
- **Evidence:** `src/monarch_autoupdate.py:60-67` (`resolve_source_dir`, no path confinement); `:93-104` (`save_policy` persists `source_dir` from the raw request body with no validation); `src/server/plan_routes.py:370-386` (`/api/plan/monarch-autoupdate/config` passes body straight through), `:389-397` (`/run` triggers execution); `src/monarch_autoimport_job.py:23-54` (interpreter resolved as `<source_dir's extractor dir>/.venv/{Scripts/python.exe|bin/python}`, then `subprocess.run` with no allow-list).
- **Observed behavior:** setting `source_dir` to any directory causes the job to execute whatever `.venv` interpreter it finds relative to that path, unattended (4am Task Scheduler) or on demand via the `/run` route.
- **Impact:** local code execution under the user's account. Chained with SEC-1, a malicious web page can set `source_dir` and trigger `/run` in two cross-origin calls.
- **Affected workflows/scenarios:** the Monarch auto-update feature; any session with the app running.
- **Root cause:** a convenience path (locate the extractor's own venv) treats configuration as trusted, and the config route treats browser input as trusted.
- **Options:** (1) confine `source_dir` to a path under the workspace root. (2) Stop deriving the interpreter from data — pin the extractor directory and let `source_dir` configure only the output subfolder. (3) Remove the subprocess entirely; write the delivery acknowledgment directly into the extractor's SQLite outbox.
- **Recommendation:** Option 2 plus Option 1's route-level validation.
- **Risk of change:** low — the shipped default path satisfies both constraints unchanged.
- **Verification method:** a config POST with an out-of-workspace `source_dir` is rejected with 400; the default-path import still marks runs delivered.
- **Linked implementation-item IDs:** W4-4.

#### SEC-3. Every build backup zips live browser session credentials and full plan PII, unencrypted, to cloud storage
- **Expert:** Security/Privacy · **Category:** privacy · **Severity:** High · **Confidence:** high
- **Inspection status:** inspected · **Verification status:** **confirmed**
- **Evidence:** `tools/backup_to_onedrive.py:36` — exclusion set is exactly `{"build","__pycache__",".pytest_cache",".git"}`, with an explicit comment that other sensitive directories are "intentionally NOT excluded." `Monarch Extractor/monarch_extract.py:22,1161` confirms `monarch-browser/` is Playwright's persistent-profile directory (live session cookies). `src/secrets_store.py:20` confirms `secrets.local.json` is plaintext.
- **Observed behavior:** ten rolling unencrypted zip copies, each containing `local_state/` (SQLite plan store + plaintext secrets), `input/*.csv` (household PII), the Monarch browser profile (replayable login session), and full transaction history, all pushed to OneDrive.
- **Impact:** a OneDrive account compromise, mis-shared folder, or second signed-in device yields a replayable financial-account login plus the household's complete financial record — the one place local data deliberately leaves the machine.
- **Affected workflows/scenarios:** every `build.py` run.
- **Root cause:** the exclusion set was written to skip regenerable caches and never revisited against the privacy classification `.gitignore` later established for the same directories.
- **Options:** (1) exclude `monarch-browser/`, `.venv/`, and `secrets.local.json` — smallest change, removes the credential half. (2) Also encrypt the archive. (3) Split into a code/config archive (OneDrive) and a PII archive (local-only destination).
- **Recommendation:** Option 1 now, Option 2 as follow-up.
- **Risk of change:** none to correctness — excluded items are runtime state the backup cannot usefully restore.
- **Verification method:** run the backup, list the resulting zip, confirm no `monarch-browser/`, `.venv/`, or `secrets.local.json` entries.
- **Linked implementation-item IDs:** W4-5.

#### ARC-1. Wave 3 item 3.11 (frontend module extraction) is recorded complete against a criterion the current state does not meet
- **Expert:** Architect · **Category:** architecture/maintainability · **Severity:** High · **Confidence:** high
- **Inspection status:** inspected · **Verification status:** **partially-confirmed** — the "complete" status is disclosed in-file as scoped to `type="module"` conversion for load-order safety, not literal ES `import`/`export`; that scoping is transparent, not hidden. The substantive point stands: the prior review's own success criterion for this item ("the ordered script-tag list... shrinks," `SYSTEM_REVIEW_2026-08-31.md:972`) was not met — the count grew.
- **Evidence:** zero `^import` lines across `frontend/js/*.js` (37 files); every module still does `Object.assign(window, {...})`; `frontend/index.html` now has 37 `<script>` tags, 36 `type="module"` (prior review measured 25).
- **Observed behavior:** the underlying defect the item targeted — hidden load-order coupling through the `window` global — is unchanged; `type="module"` conversion changed only execution timing (deferred), which required three new load-order regression tests to hold the line and is the same class of change that caused a documented 2026-07-22 outage.
- **Impact:** the item being marked complete means the real work (converting to genuine imports) will not be re-scheduled; every new module keeps paying the hand-ordered-script-list cost.
- **Root cause:** "convert to `type="module"`" was treated as satisfying "modules resolve dependencies by import."
- **Options:** (1) reopen the item with the criterion restated as "import count > 0 and script-tag count decreasing," converting leaf modules bottom-up. (2) Accept the current state as destination, delete unused `export` keywords, keep one documented `window.RP` namespace with a lint check. (3) Adopt a bundler — conflicts with a standing no-build-step constraint that the prior review left as an open, unanswered question.
- **Recommendation:** Option 1, with Option 2 as fallback if the item is genuinely being closed rather than continued.
- **Risk of change:** medium — load order caused a real prior outage; the three existing load-order regression tests are the right safety net for further work.
- **Verification method:** `^import` line count in `frontend/js/` rises from 0; `<script src>` tag count in `index.html` falls; load-order tests stay green after each step.
- **Linked implementation-item IDs:** W4-6.

#### UX-101. The Annualize toggle conveys a budget-overwrite-triggering state by color alone
- **Expert:** Usability · **Category:** accessibility / affordance · **Severity:** High · **Confidence:** high
- **Inspection status:** inspected · **Verification status:** **confirmed**
- **Evidence:** `frontend/js/dashboard_shared_helpers.js:66-83` (`annualizeToggleBtn` renders the identical `CALENDAR_SVG_ICON` for both states); `frontend/css/dashboard.css:381-382` (`.state-annualize{color:#16a34a}` / `.state-no-annualize{color:#dc2626}` — color-only distinction); no `aria-pressed` anywhere in the generated markup; the explanatory tooltip is `:hover`-only (`dashboard.css:385`) with no `:focus-visible` equivalent.
- **Observed behavior:** every Budgeting-screen row shows an identical calendar glyph distinguished only by red/green, with no keyboard-accessible label.
- **Impact:** ~8% of men have red/green color-vision deficiency; this flag gates "Load annualized current spend," a bulk, no-undo budget overwrite (`dashboard_decomp_spending_taxonomy.js:516-551`) — a user who cannot distinguish the states cannot verify the flag before running it. WCAG 2.2 SC 1.4.1 (Use of Color) failure, and a discoverability regression versus the labeled `<select>` it replaced.
- **Affected workflows/scenarios:** Budgeting → Spending Categories; the annualized-actuals bulk overwrite; any keyboard-only or color-vision-deficient user.
- **Root cause:** an icon-ification pass optimized for row density, using the hover tooltip as the sole label carrier.
- **Options:** (1) add a slash/strikethrough overlay for the "no annualize" state plus `aria-pressed` and a `:focus-visible` tooltip rule — cheapest, preserves density. (2) Replace with the existing `.toggle-switch` component, which already ships visible YES/NO text and focus-visible styling. (3) Revert to a labeled `<select>`.
- **Recommendation:** Option 1 now; Option 2 if row width allows, since it reuses a component that already solved this exact problem elsewhere in the app.
- **Risk of change:** low — one helper function, four CSS rules; the existing functional test asserts on the persisted flag, not the glyph.
- **Verification method:** render the screen through a grayscale filter and confirm the states remain distinguishable; tab to the control and confirm the label appears without a mouse; confirm screen-reader announcement of pressed state.
- **Linked implementation-item IDs:** W4-7.

#### DOC-201. The document asserted as most current omits every feature shipped since its own stated generation date
- **Expert:** Documentation · **Category:** accuracy / drift · **Severity:** High · **Confidence:** high
- **Inspection status:** inspected · **Verification status:** **confirmed**
- **Evidence:** `documentation/FUNCTIONAL_SPEC.md:3-5` ("Generated: 2026-08-29... describes the system as the code currently behaves"); zero matches for PHASE_VARYING, Monarch, financial_trends_reporter, or no_annualize; §4.5 (lines 149-153) still enumerates exactly 4 Roth conversion strategies, not the current 5.
- **Observed behavior:** the spec with the strongest currency claim in the repository is the one most out of date, and nothing in it flags the gap.
- **Impact:** future review passes and onboarding readers build on it without re-verifying; this review itself had to independently re-derive what it omits.
- **Root cause:** hand-curated with no mechanism tying regeneration to feature merges (unlike `API_CONTRACTS.md` and `GOLDEN_MASTER_CHANGELOG.md`, both of which were updated for Monarch).
- **Options:** (1) regenerate/extend now, add a PR-template checklist item. (2) Add a mechanical staleness guard (a test asserting every registered Roth strategy and top-level app directory appears in the spec). (3) Soften the header to "last reviewed," demoting its authority.
- **Recommendation:** Option 1 immediately, Option 2 scoped to the two facts that already drifted.
- **Risk of change:** none to running code.
- **Verification method:** grep the spec for the four missing terms; confirm §4.5 lists five strategies.
- **Linked implementation-item IDs:** W4-8.

#### ARC-2. Wave 2 item 2.4 removed the config-backend read path but not the write path; the per-save cost and drift surface it targeted are unchanged
- **Expert:** Architect · **Category:** data flow/performance · **Severity:** High → **Medium on verification** (see disposition) · **Confidence:** high
- **Inspection status:** inspected · **Verification status:** **partially-confirmed, severity corrected to Medium** — `config_backend.py:242-248` explicitly documents the write-path retention as a deliberate, scoped decision ("only READING... is retired; save_json/save_yaml still write the derived... portability mirrors"), not a missed cleanup. The technical fact stands; calling it an open gap overstates it.
- **Evidence:** `src/server/app_core.py:1907-1912` — `export_client_json_yaml()` still runs on every plan save alongside both SQLite writes and the CSV write.
- **Observed behavior:** the four-way materialization and its associated per-save latency are unchanged from before item 2.4.
- **Impact:** the review's own tracked status for 2.4 ("done") overstates what changed; the measurable half of finding A3 this item was meant to address is untouched.
- **Root cause:** the item was specified as "retire the backends"; the read-path removal was a reasonable but partial reading.
- **Options:** (1) drop `export_client_json_yaml` from the per-save path; expose it as an explicit "Export plan" action instead (grep confirms nothing in `src/` reads the derived JSON off disk). (2) Make the export lazy/debounced (write at build time only). (3) Leave as-is and correct the wave-status record to "PARTIAL, write-path retained by design."
- **Recommendation:** Option 1, since the cost is real and nothing depends on per-save freshness; regardless, correct the wave-status record.
- **Risk of change:** low — verify no launcher/tool reads the derived files first.
- **Verification method:** save one field; confirm `client_data.json`/`.yaml` mtimes unchanged and the build still reads the edit (existing test: `test_real_build_journey_reflects_a_user_edited_input`).
- **Linked implementation-item IDs:** W4-9.

### Medium

Presented briefly per the schema's convention for non-Critical/High items; full detail available from the source panel transcripts on request.

- **N3 — First-year SS/annuity income proration counts the entitlement month as a payment month** (Financial, medium confidence on convention question). `src/core.py:1441-1458`, `deterministic_engine.py:405-421` treat SS and annuity payments as paid in the entitlement month; SS and ordinary annuities pay in arrears, so a March entitlement should yield 9 checks that year, not the current 10. Recommendation: parameterize the shared helper by payment-timing convention. Small golden-master movement expected in claim-year figures only.
- **N4 — Joint Life RMD relief defaults ON absent beneficiary titling data** (Financial, high confidence). `src/planning_engines.py:874-903` treats a missing titling record as "spouse is sole beneficiary," converting item 2.9's fixed one-directional RMD-overstatement error into a new, opposite-directional understatement that also understates the value of Roth conversions. Recommendation: invert the default to require explicit designation, reusing the existing beneficiary-titling-audit surface.
- **N5 — `rmd_divisor` now exists in two independent implementations** (Architect, high confidence). `src/core.py:721-736` and `src/planning_engines.py:843-871` duplicate the same statutory lookup and floor logic — the exact organizational pattern the prior review named as its central structural observation, reproduced inside a remediation item for that same finding. Recommendation: add a cross-implementation equivalence test now (cheap, proven pattern from the LTCG diagnostic), then consolidate into `tax_kernel.py`.
- **N7 / ARC-2 companion — Wave 2 items 2.4/2.5's actual disposition is a documented won't-fix (2.5) and a partial (2.4), not "done"/"open" as tracked** (Architect, high confidence). `src/server/app_core.py:1846-1905` is a 60-line, well-reasoned won't-fix rationale for 2.5 with a real cost measurement; it should be recorded in the review's own status register rather than left implicit.
- **N8 — `results_model` page coverage has not moved (Wave 3 item 3.12)** (Architect, high confidence). Still 6 of ~32 registered sheet builders; recommend either prioritizing 3-4 high-traffic sheets or formally parking the "ongoing" label, since a track with zero measured movement in a week should not be reported as advancing.
- **ARC-3 — Wave 3 items 3.10/3.13 are flat or net-negative on their own stated metrics** (Architect, high confidence). `run_deterministic_projection_stage` is now 3,194 lines (was 3,073); `parse_client` is 2,072 lines before and after its "extraction" commit (the actual 391 lines removed came from elsewhere in `data_io.py`). Recommend re-scoping both with a monotonic line-count/stage-count metric and a ratchet test.
- **ARC-4 — `financial_trends_reporter` is a submodule presented as a separate app, with a second unauthenticated HTTP surface** (Architect/Security, high confidence). Imports `src.*` via `sys.path` injection while its own docstring claims independence; exposes `GET /api/history` (full net-worth/spending log) and `POST /api/run-now` with no auth/CSRF/origin check on port 5057. Same-origin policy blocks cross-origin *reads* today since it sets no CORS headers — critically, **it must never acquire SEC-1's `ACAO: *` pattern**. Recommend dropping the "separate app" framing or adding an explicit origin check.
- **UX-102 — Trends-reporter charts are inaccessible and inject unescaped user data into SVG** (Usability, high confidence). No `role="img"`/labels/data-table fallback; category names interpolated unescaped into SVG markup (a Monarch category containing `&` or `<` breaks rendering); 10px chart text against a stated 60+ user base.
- **UX-103 — The Monarch settings card breaks the app's autosave contract with no busy/dirty state** (Usability, high confidence). Manual "Save setting" button in an otherwise-autosaving app, with no dirty indicator; "Import now" gives no feedback while running.
- **UX-104 — The Monarch card's client-side fallback path is stale relative to the server default** (Usability, high confidence). Client literal is `"../Monarch Extractor/output"`; server default (post-consolidation) is `"Monarch Extractor/output"` — a first-run user can commit a nonexistent path before the status fetch resolves.
- **UX-105 — Dynamically-built confirm dialogs lack dialog semantics and leak a `keydown` listener on every non-Escape close** (Usability, high confidence). No `role="dialog"`/`aria-modal`, no focus trap or restore; these guard destructive actions including the same no-undo budget overwrite as UX-101.
- **DOC-202 — The shipped end-user README still reads "v11" after the v12 version bump** (Documentation, high confidence). `documentation/readme/README.md:1`, `PROJECT_MANIFEST.md:1` were not in `bump_version.py`'s hardened replace-set. Recommend removing the version number from the README heading entirely (the app already reports its own version) and adding `PROJECT_MANIFEST.md` to the bump tool's target list.
- **DOC-203 — New Roth help text exposes raw internal config keys** (Documentation, high confidence). `frontend/js/dashboard.js:6251-6268` surfaces `roth_phase_count`, `roth_phase_first_bracket_rate`, and the literal strategy value `"PHASE_VARYING"` to a 60-year-old non-expert end user — the same pattern (D3) the prior review spent a wave removing, recurring on a brand-new surface, with the repo's own `no_internal_keys_on_screen.test.mjs` guard not extended to reach it.
- **DOC-204 — Monarch auto-update and the trends reporter have no end-user-facing documentation** (Documentation, medium confidence). Both are documented only in maintainer-facing surfaces (`API_CONTRACTS.md`, `docs/superpowers/`); nothing in the shipped README explains either to the household running the packaged app.
- **QUA-301 — PRs #86-90's new UI surfaces have zero browser-level (e2e) test coverage** (Quality, high confidence). The Monarch card exercises exactly the fetch/module/global-bridge pattern that has previously caused a real production outage in this codebase (`tests/e2e/script-order-spike.spec.js` exists because of it), yet has no e2e spec of its own.
- **QUA-302 — The trends reporter's entire chart-rendering logic is inline, untested, and untestable without extraction** (Quality, high confidence). `filterByTimeframe`, `lineChartSvg`, `barChartSvg` live inline in `financial_trends_reporter/frontend/index.html` with no module boundary.
- **ARC-5 — `workbook_common`'s barrel-export problem is half-fixed** (Architect, high confidence). Engine re-exports removed per item 2.16, but the module still star-imports `core` and generates `__all__` from `globals()`, re-exporting every stdlib/openpyxl name it imports.

### Low

- **N6 — RMDs are silently suppressed below a $500 balance** with no statutory basis; an undocumented magic number inside a statutory calculation. Recommend deleting the threshold.
- **N9 — Monarch transaction sign convention is unasserted anywhere in the codebase** (insufficient-evidence, not a confirmed defect — flagged for a contract test).
- **SEC-4 — Audit logging redacts credential-shaped keys but not financial fields** (balances, DOBs, merchant names pass through `redact_text` untouched into `output/audit_log.jsonl`, which is itself inside the SEC-3 backup).
- **SEC-5 — `secrets_store.encryption_status()` reports `"configured": True` for a plaintext store**, which is a defensible storage choice for a single-user local app but a misleading status string.
- **ARC-6 — `results_model`/`detailed_results.py` scraper-path debt is unchanged**, restated from the prior review with no new information.
- **ARC-7 — `input/demo/client_policy.csv` documentation comment still describes the pre-flip MC default**; copy drift from item 1.1.
- **UX-106 — The trends reporter surfaces no error state for a failed history fetch or failed run**, misattributing transport failures to "no data yet."
- **UX-107 — No skip-link; `#mainPane` is an unlabeled landmark inside a `<main>` that also contains the full navigation**, forcing every keyboard user through the ~45-step nav before reaching content.
- **QUA-303 — Both mechanical test-hygiene ratchets (suffix-shape ceiling, frontend-source-grep baseline) are at or past their intended headroom**, and the source-grep baseline is absorbing structural exemptions its own docstring says it should not.
- **DOC-205 — `documentation/` root holds five overlapping, ambiguously-titled optimization-plan documents with no index** distinguishing current from superseded.

---

## 6. Options and tradeoffs

The cross-cutting choice this review surfaces is **how to prevent regression on unreviewed feature work between review cycles**, since every High-severity new-code finding (SEC-1 excepted, which predates PRs #86-90) originated in code this review is the first pass over.

- **Option A — Status quo:** continue running full reviews periodically; accept that feature PRs between reviews ship unreviewed. Cheapest; guarantees the pattern repeats, as this cycle demonstrates.
- **Option B — Extend existing mechanical guards to new surfaces as a PR gate:** the repo already has `no_internal_keys_on_screen.test.mjs`, `test_freeze_frontend_source_grep.py`, and a spec-currency convention; require any PR touching `frontend/` or adding a user-facing config surface to extend the relevant guard as part of the PR, checked by a lightweight self-review checklist rather than a full panel review. Cheap, reuses proven infrastructure, does not require inventing new tooling.
- **Option C — A lightweight "security/accessibility diff review" on every feature PR**, scoped to the specific checks this cycle's findings fell into (CORS/auth surface, path validation, color-only state, unescaped interpolation) rather than a full five-expert panel. Moderate cost, catches more than Option B but requires a maintained checklist.

**Recommendation:** Option B now (near-zero marginal cost, the infrastructure exists), Option C if the feature-PR cadence continues at its current rate (five feature PRs in one week).

---

## 7. Recommendation

Close the five Critical/High **security and financial-domain** findings (SEC-1, SEC-2, SEC-3, N1, N2) before any further feature work — all five are narrow, none require an architecture change, and all have a stated verification method. In parallel, correct the review's own status record for the four items where this cycle found a mismatch between what is tracked and what the code shows (2.4/2.5 as documented won't-fix/partial rather than done/open; 3.10-3.13's "ongoing" label against flat-or-negative metrics; 3.11 marked complete against an unmet criterion) — this is a process fix, not a code fix, and it is what keeps the next review from re-discovering the same gap. Everything else (the Medium/Low findings) can be scheduled in the next wave without blocking either of the above.

---

## 8. Target design

No architectural redesign is indicated this cycle — the target state is the same one the 2026-08-31 review described, now closer to realized. Additions specific to this review's findings:

- **Security boundary:** the local API server's trust boundary should be "same-origin requests from the app's own served UI," enforced by deleting the wildcard CORS header rather than by adding authentication (which would be architecturally disproportionate for a single-user local desktop tool). The Monarch subsystem's trust boundary should be "paths under the workspace root," enforced at both the policy-save and job-execution layers, not just documented as an assumption.
- **New-subsystem review parity:** `financial_trends_reporter` should either be folded into the main app's route/permission/CORS surface (recommended) or, if it remains standalone, held to the same security and accessibility bar as the main app — not a lesser one by virtue of being newer.
- **Time-resolution consistency in the engine:** the SS/annuity payment-timing model should adopt a single, explicit convention (in-advance vs. in-arrears) parameterized once, rather than reusing a coverage-period helper for payment-timing concepts (N2, N3's shared root cause).
- **Status-tracking discipline:** wave/phase status tables should carry a machine-checkable metric wherever the original finding had one (line counts, import counts, registered-stage counts), so "done"/"ongoing" claims can be verified the way this review had to verify them manually.

---

## 9. Implementation waves

Continuing the numbering from the prior review's Waves 1-3. This review does not re-litigate Wave 2/3 items already confirmed done; it schedules only what this cycle found.

### Wave 4 — Security and financial-domain corrections (highest priority; no dependencies on each other)

| # | Item | Finding | Effort | Risk | Verification | Parallel? |
|---|---|---|---|---|---|---|
| W4-1 | Delete wildcard CORS (`_local_cors`); confirm no `file://` launcher depends on it | SEC-1 | S | Low-Medium | Cross-origin fetch fails; in-app UI unaffected end to end | Yes |
| W4-2 | Restrict the MC parity gate to the exact sub-mechanism (home-equity/survivor off); surface `mc_approximation_status` on the KPI tile and workbook | N1 | S-M | Low | Gate passes at 1pp with approximations disabled; KPI tile shows an approximation indicator | Yes |
| W4-3 | Fix SS claim-age month precision at the one derivation site + JS mirror | N2 | S | Medium (moves golden master) | New unit test: 1960-11 DOB, claim 03/2027 → fractional-age benefit factor | Yes |
| W4-4 | Confine Monarch `source_dir` to the workspace root at both save and execution time | SEC-2 | S | Low | Out-of-workspace path rejected with 400; default import still works | Yes |
| W4-5 | Exclude `monarch-browser/`, `.venv/`, and `secrets.local.json` from the build backup | SEC-3 | S | None | Backup zip contains none of the three | Yes |

### Wave 5 — Corrections to Wave 2/3's own status record and remaining Medium items

| # | Item | Finding | Effort | Risk | Verification | Parallel? |
|---|---|---|---|---|---|---|
| W4-6 | Reopen 3.11 with a measurable criterion (import count, script-tag count); OR formally accept current state and delete unused exports | ARC-1 | M-L | Medium | Metric moves in the stated direction | Yes |
| W4-7 | Fix Annualize toggle accessibility (non-color state indicator, `aria-pressed`, `:focus-visible` tooltip) | UX-101 | S | Low | Grayscale render distinguishable; keyboard-reachable label | Yes |
| W4-8 | Regenerate `FUNCTIONAL_SPEC.md` for the five missing features; add a spec-currency guard | DOC-201 | S-M | None | Spec mentions all four missing terms; §4.5 lists 5 strategies | Yes |
| W4-9 | Correct the Wave 2/3 status record: 2.4→partial (write path retained by design), 2.5→won't-fix (documented), 3.10/3.12/3.13→re-scoped with monotonic metrics | ARC-2, N7, N8, ARC-3 | S | None | Status document matches code | Yes |
| W5-1 | RMD Joint Life default inverted to require explicit spousal designation | N4 | M | Medium (moves RMDs/taxes for affected fixtures) | 12-year-gap household with no titling → Uniform Lifetime + audit finding | Yes |
| W5-2 | Cross-implementation equivalence test for `rmd_divisor`, then consolidate | N5 | S | Low | Parametrized equality test over age × spouse-age × flag grid | Yes |
| W5-3 | SS/annuity payment-timing convention parameterization (arrears default) | N3 | S | Low | December claim → zero SS cash that calendar year | Yes |
| W5-4 | Extend `no_internal_keys_on_screen` guard to the PHASE_VARYING help-text map; rewrite the four strings | DOC-203 | S | Low | Extended guard fails on current strings, passes after rewrite | Yes |
| W5-5 | One e2e spec for the Monarch settings card round-trip | QUA-301 | S | Low | Spec fails when the module/global bridge is deliberately broken | Yes |
| W5-6 | Trends-reporter accessibility + escaping + error-state pass | UX-102, UX-106 | S-M | Low | Screen-reader pass; category name with `&`/`<` renders correctly | Yes |
| W5-7 | Confirm dialog semantics + listener-leak fix | UX-105 | S | Low | `role="dialog"`; listener count does not grow after repeated open/close | Yes |
| W5-8 | Monarch card: autosave + busy state; fix stale fallback path | UX-103, UX-104 | S | Low | Toggle persists across navigation without an explicit save | Yes |
| W5-9 | Delete RMD $500 de-minimis threshold | N6 | S | Low | $400 IRA at age 80 produces a small positive RMD | Yes |

**Concurrency:** all Wave 4 items are independent (disjoint files) and can run fully in parallel. Wave 5 items are likewise independent of each other; none has a cross-item dependency within this review's scope.

---

## 10. Validation plan

**Item-level:** each Wave 4/5 item's verification method above is the acceptance test for that item.

**System acceptance criteria for this review cycle:**
1. No cross-origin request can read or write plan data (W4-1's verification, exercised from an actual second-origin page).
2. The MC parity gate is either passing at 1pp with approximations isolated out, or the KPI tile/workbook visibly discloses the approximation status (W4-2).
3. A golden-master regeneration reflects the corrected SS claim-age logic, with a changelog entry per `documentation/GOLDEN_MASTER_CHANGELOG.md`'s existing convention (W4-3).
4. The build backup archive, freshly generated, contains none of the three excluded paths (W4-5).
5. `documentation/FUNCTIONAL_SPEC.md`'s generation date is not older than the newest commit touching a public engine surface (W4-8), verified by the new staleness guard.
6. The Wave 2/3 status record (this document plus a corrected version of the prior one) matches what a fresh `grep`/line-count check of the cited files shows (W4-9) — this is the meta-acceptance-criterion for the process fix in §7.

No item in this review's findings required — and none should be verified by — a claim about test pass/fail status or CI outcome; per policy, this review makes no such claims.

---

## 11. Assumptions and open questions

1. **SEC-1's fix assumes no shipped launcher opens `frontend/index.html` via `file://`.** This was not independently verified by executing the app; confirm before deleting `_local_cors` outright.
2. **N1's root-cause attribution (home-equity contingency, survivor-bucket economics) is based on in-code comments and docstrings, not an independent re-derivation of the 6.05pp figure.** The diagnostic in Option 1 of N1 should be run before treating the attribution as settled.
3. **N2's fix requires a jurisdiction/rule-year note:** SSA's reduction and delayed-retirement-credit schedules (20 CFR 404.313/404.410) are assumed unchanged for the modeled projection period; this should be reconfirmed at implementation time against current SSA guidance.
4. **N4's recommended default inversion is a financial-planning judgment call, not a pure engineering one** — it should go through the same explicit planner sign-off discipline the prior review established for recommendation-changing items (its own open question 10).
5. **Whether `financial_trends_reporter` should remain a standalone app or be folded into the main server (ARC-4) is a product/architecture decision**, not one this review resolves — the review's position is only that whichever is chosen, it must not inherit SEC-1's CORS pattern.
6. **This review performed no runtime validation.** Every finding is a static-evidence finding. Several verification methods above (grayscale rendering, screen-reader passes, cross-origin fetch tests) require an execution environment this review did not have.

---

## 12. Review limitations

- **No runtime validation was performed.** No tests were executed, no build was run, no browser session was opened. All findings rest on static file:line evidence or narrative/commit-history evidence. `documentation/reports/SYSTEM_REVIEW_2026-08-31.md`'s own findings that *were* runtime-validated (e.g. its MC engine work) are treated here as prior evidence, not re-validated.
- **The three expert panels and the verification pass were conducted as delegated sub-agent sessions rather than by the orchestrating session directly reading every file.** Each panel's evidence citations were spot-checked in the adversarial verification pass (9 of 9 Critical/High findings independently re-opened and confirmed or corrected), but not every Medium/Low finding's citation was independently re-verified by a second reader.
- **Secret scanning could not be run** — the available GitHub MCP tool required a `files` parameter this session could not supply meaningfully for a repository-wide scan; the credential-incident check (PR #87) was instead done via targeted `git log --all` history search and directory content inspection, which is a narrower check than a full secret-scanning pass.
- **Not every document in `documentation/` (~30 files) was read in full**; documentation review sampled the most user-facing and most-recently-changed documents.
- **Performance was not independently re-measured** this cycle; the coverage matrix marks it "partially inspected" on the basis of the prior review's measurements only.
- **`CI was intentionally excluded from this review.`**

---

## 13. Finding disposition appendix

No findings from either the prior review or this review's own three panels were refuted outright. Two Critical/High findings had their severity or framing corrected on adversarial verification; both are recorded above with the correction inline rather than separately, per the schema. No duplicate or superseded findings were identified between the three panels' independent output — their scopes were assigned to avoid overlap, and cross-checking confirmed no collision.

| Finding | Disposition | Note |
|---|---|---|
| N1 | Confirmed, framing corrected | 6.05pp figure is disclosed in-repo, not hidden; severity held at High rather than escalated to Critical |
| N2 | Confirmed | No change to severity or scope |
| SEC-1 | Confirmed | No change |
| SEC-2 | Confirmed | No change |
| SEC-3 | Confirmed | No change |
| ARC-1 | Partially confirmed | "Complete" status is transparently scoped in-file; substantive gap against the item's own original success criterion stands |
| ARC-2 | Partially confirmed, severity corrected High→Medium | 2.5's non-completion is a documented, reasoned won't-fix, not an oversight; 2.4's write-path retention is likewise disclosed as deliberate scope |
| UX-101 | Confirmed | No change |
| DOC-201 | Confirmed | No change |

---

## 14. Financial planner sign-off

Acting in the financial-planner review capacity for this cycle (the panel that produced N1-N9 was itself run at the financial-planner charter, and its findings were independently adversarially verified above):

**Verdict.** The four financial-domain findings (N1, N2, N3, N4) are evidenced accurately and none are overstated; N1's severity was, if anything, corrected downward on verification once its transparent in-repo disclosure was accounted for. N2 is the one finding in this cycle that should not be left through another review cycle: unlike N1 (a disclosed, bounded approximation) or N3/N4 (narrow, contained), N2 is a silent, permanent, per-household error with no existing disclosure anywhere in the product.

**Requested changes:** none to the findings as stated. One process request: W4-3 (the N2 fix) must regenerate the golden master with a changelog entry per the project's own established discipline (`documentation/GOLDEN_MASTER_CHANGELOG.md`), and the resulting shift in any fixture's SS figures should be reported as a **correction**, not silently absorbed — consistent with how the prior review's planner handled the analogous EDB-beneficiary-class default correction (item 3.3).

**Resolution:** all four findings are accepted into Wave 4/5 as scheduled above; no disagreement recorded.

**Impact analysis:** N2's fix will move golden-master SS-income and SS-tax figures for any fixture where claim month ≠ birth month; N4's fix will raise RMDs (and therefore lifetime tax and the value of Roth conversions) for any household with a >10-year spousal age gap and no beneficiary titling on file — the direction of this movement is a correction toward accuracy, not a regression, and should be reported to any existing user as such.

**Dissent:** none.

**Closing note.** *Nothing in this review's financial-domain findings hides a number a planner needs, and none degrades planning quality as such — but N2 is the first finding across both review cycles that produces a wrong number silently, permanently, and without any existing disclosure, and it should be treated with the same urgency the prior review gave its own single such finding (F9/item 1.16).*

---
