# System Review — 2026-09-25

**Scope:** The entire system. **Depth:** Standard. **Repository:** matthartzman/retirement_system, branch `main`, commit `92a5cd3` (working tree clean at time of review; local checkout was fast-forwarded from `5799063` to pick up `92a5cd3` — PR #140 — before this review began). No open issues, no open pull requests at review time.

**Orchestration note:** This review's own orchestration workflow (`Workflow({scriptPath: ".claude/workflows/system-review.js"})`) could not be invoked — the harness's permission handler rejected the call with a false-positive "script contains control characters" error (independently verified: the script file contains no control or astral characters). Per the `system-review` skill's own fallback procedure, this review was conducted **manually**: reconnaissance, expert panel, adversarial verification, and synthesis were each run as directly-dispatched subagents rather than through the `Workflow` tool's deterministic pipeline, applying the same rules (read-only boundary, CI exclusion, evidence citation, adversarial verification) at each step. This is a process-mechanics limitation, not a scope reduction — the same five-expert panel, verification discipline, and report structure were followed.

---

## 1. Executive Summary

This is a mature, actively-maintained retirement-planning application (443 test files, extensive golden-master regression infrastructure, a five-phase modernization history documented in `documentation/archive/`) that just landed a six-PR restructuring sequence (#134–#139, "W-A" through "W-F": taxonomy vocabulary, IRMAA indexing, spending-model consolidation, large-discretionary/spending-adjustments, housing restructure, and nav regrouping). The codebase's own engineering discipline — atomic file writes, golden-master pinning with provenance checks, cross-implementation equivalence tests, workspace-isolated test fixtures with an audit-hook write guard — is well above average for a project this size, and several reconnaissance leads that looked like real defects (duplicate IRMAA/RMD-divisor implementations, particularly) turned out on inspection to be resolved delegation patterns already covered by broad equivalence tests.

That said, this review identified **27 findings** (0 Critical, 6 High, 7 Medium, 14 Low) after adversarial verification refuted one and corrected two others. The most consequential:

- **A real, if not yet triggered, data-integrity gap**: the startup plan-data migration rewrites household CSV files in place with no atomic rename and no backup — the one persistence path in the codebase that doesn't use the project's own `atomic_write` helper, running unattended on every boot (**ARC-001**, High).
- **Two accessibility gaps that affect the primary use case**: the shared field-rendering helper used for nearly every input in the app produces controls with no programmatic accessible name (**UX-001**, High), and the single global save/error banner isn't an ARIA live region (**UX-002**, High).
- **Three test-coverage gaps that quietly remove safety nets the project believes it has**: a scalar-vs-vectorized survivor-economics equivalence test that never runs in any pipeline (**QA-002**, High), golden-master provenance enforcement that covers only 1 of 3 pinned-output mechanisms (**QA-003**, High), and a budget-corruption recovery function with zero direct test coverage despite existing specifically to prevent data loss (**QA-006**, High).

No finding rises to Critical. No finding indicates currently-wrong financial arithmetic reaching a user; the domain-correctness spot-checks performed (IRMAA, RMD divisors, Social Security taxability, IL/NY estate tax, Next-Housing-Move off-switch) held up under adversarial re-verification. However, **Roth conversion/AGI interaction, QLAC, withdrawal-cascade sequencing, and survivor/spousal-rollover paths were not inspected in this pass** and remain a genuine, stated coverage gap — not a clean bill of health.

**Financial planner verdict:** see [Section 14](#14-financial-planner-sign-off).

**Top recommendations** (detail in [Section 7](#7-recommendation)):
1. Route the at-rest CSV migration through the existing `atomic_write` helper (ARC-001) — highest-priority data-integrity fix, low engineering cost.
2. Wire an accessible name into the shared `fieldHtml()` field renderer and an ARIA live region into the global message banner (UX-001, UX-002) — highest-leverage accessibility fixes given how widely both are reused.
3. Close the three test-safety-net gaps (QA-002, QA-003, QA-006) before the next engine-consolidation or spending-recovery-adjacent change relies on them being real.
4. Schedule a follow-up pass on Roth conversion, QLAC, withdrawal-cascade sequencing, and survivor/spousal-rollover logic — explicitly not covered by this standard-depth review.
5. Clean up the small cluster of stale internal documentation (conftest.py's dead path reference, `.claude/CLAUDE.md`'s stale housing file-size table, the retired Husband/Wife terminology still served by `generated_schema_coverage.csv`) — cheap fixes that reduce the odds of a future session (human or AI) wasting time on wrong information.

---

## 2. Scope and Methodology

- **Scope:** the entire system (explicit user instruction: run with default scope).
- **Date:** 2026-09-25. **Depth:** standard.
- **Roles:** Architect, Financial Planner, Usability/Accessibility, Documentation, Quality (static-only), plus an orchestrator role (this synthesis) — no orchestrator findings; the orchestrator only deduplicates, sequences, and synthesizes.
- **Model tiers:** panel experts and their adversarial verifiers ran at this session's inherited model/effort; no per-stage tier override was configured (the capability-alias table in the skill maps to reasoning-effort tiers under `Workflow`, which was unavailable — see the orchestration note above).
- **Phases actually run:** (1) three parallel reconnaissance passes (engine/architecture/calculations; UI/workflows; tests/docs/data/config) merged into one system map; (2) five-expert panel, each independently investigating reconnaissance leads plus their own charter; (3) one adversarial verifier per expert, instructed to try to refute every finding; (4) this synthesis; (5) financial-planner sign-off ([Section 14](#14-financial-planner-sign-off)).
- **GitHub repository/ref/commit/PR context:** matthartzman/retirement_system, `main` @ `92a5cd3` (fast-forwarded from `5799063` at the start of this session to pick up PR #140's workflow-tooling fix — an environment/tooling change, not an application change). 0 open issues, 0 open PRs. Recently merged, in order: #131 (ZIP-optimizer test fixes), #132 (master implementation plan W0–W13), #133 (housing move-year valuation), #134 (W-A taxonomy vocabulary), #135 (W-B IRMAA indexing), #136 (W-C spending model consolidation), #137 (W-D large discretionary + spending adjustments), #138 (W-E housing restructure), #139 (W-F nav regroup + consistency guard), #140 (workflow-tooling fix, non-application). Every PR title was treated as unverified context and independently checked against source — see per-finding evidence.
- **Runtime-validation status:** `Runtime behavior was not validated during this review.` This review is static and read-only; no tests, builds, or the application were executed at any point.
- **CI exclusion:** `CI was intentionally excluded from this review.`

---

## 3. Coverage Matrix

| Area | Status | Expert | Findings | Residual Uncertainty |
|---|---|---|---|---|
| Architecture | finding_identified | Architect | ARC-001, ARC-002, ARC-003, ARC-004 | Large files (`dashboard.js`, `dashboard_decomp_row_model.js`, `workbook_builder.py`, `workbook_common.py`, `module_catalog.py`) were only grep-targeted per repo convention, not exhaustively audited. |
| Calculation engine | partially_inspected | Financial Planner / Architect | (none directly; IRMAA/RMD-divisor consolidation independently verified, no material finding) | Roth conversion/AGI interaction, QLAC, withdrawal-cascade sequencing, and the Monte Carlo simulation loop itself were not located/inspected — genuine gap, not "healthy." |
| Financial logic (tax/retirement/benefits/healthcare/estate/survivor) | partially_inspected | Financial Planner | FIN-001, FIN-002 | Survivor/spousal-rollover, remarriage/beneficiary, and inherited-account RMD paths not inspected. IRMAA/estate-tax dollar-table provenance is self-labeled "assumption" in `reference_data/tax_law_v10.json`, not independently cross-checked against a primary CMS/NY DTF source. |
| Data integrity | finding_identified | Architect / Quality | ARC-001, QA-006 | At-rest write-safety and budget-recovery paths both need re-inspection after remediation. |
| Validation | finding_identified | Usability/Accessibility | UX-003 | Only client-side (frontend) validation surfacing was assessed; backend validation-rule completeness was not separately audited. |
| Precision | inspected_no_material_finding | Financial Planner | — | NY estate-tax 100–105%-of-exemption phase-out band is a documented linear approximation, not the exact statutory formula — correctly disclosed in-code, but not independently verified against primary NY DTF guidance. |
| Dates | inspected_no_material_finding | Financial Planner | — | 1959-birth-cohort SECURE 2.0 age-73-vs-75 RMD-start ambiguity is a documented, deliberate interpretive choice (IRS Notice 2023-54 position) — correct as implemented, but a household born in 1959 should have this confirmed by a qualified professional. |
| UI | finding_identified | Usability/Accessibility | UX-001 through UX-006 | Full-file reads of `dashboard.js`/`dashboard_decomp_row_model.js` were not performed (grep-only per repo convention); sections outside cited regions not inspected. |
| Accessibility | finding_identified | Usability/Accessibility | UX-001, UX-002, UX-003, UX-005 | No live screen-reader (NVDA/VoiceOver/JAWS) session or contrast-ratio measurement was possible in this static, no-runtime review. |
| Performance | not_inspected | — | — | No expert charter in this standard-depth run performed a dedicated performance pass (e.g. workbook-build time, projection-loop cost). Genuine coverage gap. |
| Privacy / Security | partially_inspected | Architect | — | `src/secrets_store.py` and a high-level pass over `src/security.py` found no material issue; native GitHub secret-scanning alerts were not accessible to this review's tooling (the available `run_secret_scanning` tool scans supplied file content, not the whole repository) — repo-committed-secret risk is **not fully assessed**. |
| Documentation | finding_identified | Documentation | DOC-001, DOC-002, DOC-003, DOC-004, DOC-005, DOC-006, DOC-007, DOC-009 (DOC-008 refuted, see [§13](#13-finding-disposition-appendix)) | `documentation/archive/` and `docs/superpowers/` trees were sampled, not read exhaustively. |
| Testing | finding_identified | Quality | QA-001 through QA-007 | 443 test files cannot all be read individually; a representative sample plus every file directly implicated by a reconnaissance lead was read. No test was executed at any point. |
| Configuration | finding_identified | Documentation / Architect | DOC-005 (version-number mismatch) | Whether any process outside this repository depends on `pyproject.toml`'s frozen `10.0.0` value was not checked (out of scope). |
| Persistence / import-export | finding_identified | Architect | ARC-001, ARC-002 | Runtime crash/interruption behavior was not tested (static review only). |
| Error handling | finding_identified | Usability/Accessibility | UX-004 | Did not verify at runtime which backend endpoints actually emit a structured `errors` array; finding is about client-side inconsistency in handling the possibility. |
| Logging / observability | finding_identified | Architect | ARC-002 | Only the plan-data-migration startup path was inspected in depth; broader application logging conventions were not systematically surveyed. |
| GitHub work context | inspected_no_material_finding | Orchestrator | — | 0 open issues/PRs at review time; 10 recently-merged PRs (#131–#140) independently cross-checked against source rather than trusted by title — see per-finding evidence and the recon leads embedded throughout this report. |

---

## 4. System Health Assessment

**Architecture:** Sound overall design with a clear pipeline-stage decomposition (`src/projection_stages/*`) and an explicit, documented history of consolidating duplicate implementations (IRMAA, RMD divisor) behind single canonical functions with delegation wrappers and broad equivalence tests — this consolidation discipline is a genuine strength, verified independently rather than taken on faith. The one real gap found is persistence-layer: one write path (startup CSV migration) doesn't follow the project's own atomic-write convention. `src/data_io.py`'s size and coupling (2,530 lines, ~130–143 dependents) is accepted architectural debt, not an active defect.

**Usability / Accessibility:** This is the weakest area found in this review. The shared field-rendering helper and the global message banner — both used essentially everywhere in the app — have real, verified accessibility gaps (no programmatic field names, no live-region announcements) that would materially affect a screen-reader user attempting to enter financial data, which is not a hypothetical population for a retirement-planning tool used by "a 60-year-old non-expert" per this project's own stated documentation audience.

**Documentation:** Generally strong (a dedicated documentation-currency test pattern exists and is used for several key docs), but with a small, avoidable cluster of stale cross-references — most notably the project's own auto-loaded `.claude/CLAUDE.md`, which cites a housing-module file path and size table that no longer match the post-restructure codebase.

**Quality / Testing:** Extensive and thoughtfully engineered test infrastructure (golden masters with provenance checks, workspace-isolated fixtures with a write-guard audit hook, a documented test-taxonomy policy), but with three specific gaps where the infrastructure's own stated safety guarantee doesn't actually hold end-to-end (an untriggered nightly test, incomplete provenance coverage, an untested recovery function).

**Financial correctness:** No arithmetic defect was found in the areas inspected (IRMAA, RMD divisors, Social Security taxability, IL/NY estate tax, housing off-switch behavior) — each held up under independent, adversarial re-verification. This is a partial clearance, not a full one: Roth conversion/AGI interaction, QLAC, withdrawal-cascade sequencing, and survivor/spousal-rollover paths were not inspected in this standard-depth pass.

**Data integrity:** One real gap (ARC-001) in an unattended, boot-time write path; the household CSV/JSON/YAML input layer otherwise shows a mature, deliberate corruption-recovery design (`recover_spending_budget_from_seed`), just one that currently lacks direct test coverage (QA-006).

**Security / privacy:** No material issue found in the portions inspected; repo-wide committed-secret risk is not fully assessed given tooling limits in this review environment (see coverage matrix).

**Performance:** Not assessed in this standard-depth review — a stated gap, not a clean bill of health.

---

## 5. Material Findings

Findings are grouped by expert. IDs match the finding register (validated against `schemas/findings.schema.json` in structure). All findings below survived adversarial verification with disposition `confirmed` or `partially_confirmed`; refuted/duplicate/superseded/insufficient-evidence items are in [Section 13](#13-finding-disposition-appendix).

### Architect (ARC)

**ARC-001 — At-rest Plan Data CSV migration writes non-atomically and without backup, bypassing the codebase's own `atomic_write` utility**
- Severity: **High** · Confidence: High · Verification: confirmed (verifier found the gap is broader than originally scoped — see ARC-002)
- Evidence: `src/plan_data_migration.py:342-364` (`migrate_plan_data_at_rest` rewrites each changed CSV via plain `path.write_text(...)`, no temp file, no `os.replace`, no backup); `src/plan_file_io.py:67-99` (`atomic_write` — the established, documented pattern for exactly this reason, explicitly citing Windows `WinError 32` and POSIX row-interleaving as the failure modes it prevents); 8 confirmed call sites of `atomic_write`/`write_text_atomic` elsewhere in the codebase (`plan_data_backfill.py`, `server/app_core.py` ×3, `server_services/admin_service.py` ×3, `server_services/strategy_asset_service.py`, `system_config.py`, `ytd_tracking.py`) — none of which is this migration path; `main.py:144-163` (runs unattended on every boot before either desktop or server mode opens plan data).
- Observed behavior: the migration rewrites household CSV files directly against their real path with no atomic-rename safety net and no backup copy, unlike every other persistent writer in this codebase.
- Impact: a crash, kill, or power loss mid-write (plausible given this runs unattended at boot, often right after an app update) leaves the CSV truncated/corrupted with no recovery path — and because CSVs are only rewritten when content actually changes, the corrupted file could be the household's real financial data with no other copy at that moment.
- Affected workflows: any app boot where the stored Plan Data schema version is behind current.
- Root cause: the CSV rewrite loop was implemented with a plain `write_text` call rather than reusing the `atomic_write` helper that already existed in the same codebase for this exact purpose.
- Options: (1) wrap the rewrite in `plan_file_io.atomic_write`, matching every other writer; (2) at minimum, write a `.bak` copy before rewriting.
- Recommendation: route the CSV rewrite through `atomic_write` (or an equivalent temp-file + `os.replace` step).
- Dependencies: `src/plan_file_io.py` (helper already exists, import-ready).
- Implementation considerations: mechanical change (context-manager call instead of direct write); verify against `tests/test_plan_data_migration.py`.
- Risk of change: Low.
- Verification method: static review; recommend adding a test that simulates a mid-write interruption and asserts the original file is unchanged.

**ARC-002 — `run_startup_plan_data_migration`'s outer exception handler silently swallows failures with no error signal, across the entire migration path (broader than the DB-snapshot sweep alone)**
- Severity: **Medium** · Confidence: High · Verification: confirmed, scope corrected wider by verifier
- Evidence: `src/plan_data_migration.py:395-416` (outer `except Exception: return {'migrated': {}, 'total_changed': 0, 'skipped': True}` — no `error` key, no logging call anywhere in the block); the verifier confirmed this wraps the *entire* call including `workspace_root()` resolution and all of `migrate_plan_data_at_rest`, not just the inner DB-snapshot sweep; `src/plan_data_migration.py:366-387` (the narrower inner except block was deliberately fixed on 2026-08-19, per its own comment, specifically to stop this exact silent-failure pattern — that fix was not generalized to the outer wrapper); `main.py:156-163` (only prints a warning when an `error` key is present — this path produces none).
- Observed behavior: any exception raised before reaching the inner try (e.g. a bad `workspace_root()` resolution, a CSV read/glob failure) is caught and returned in a shape indistinguishable from "nothing needed to happen," with zero console/log output.
- Impact: a persistently-failing migration would retry silently forever with no visible sign to the user or in logs — the exact failure mode the 2026-08-19 fix was written to eliminate, still open one layer up.
- Options: extend the same `{..., "error": "..."}` shape to the outer except block, matching the inner block's already-established contract.
- Recommendation: as above; purely additive, no behavior change to the happy path.
- Risk of change: Low. Dependencies: none.

**ARC-003 — `reference_data/generated_schema_coverage.csv` is stale generated output, never regenerated, still actively serving retired "Husband/Wife" terminology through the live schema/help registry**
- Severity: **Medium** · Confidence: High · Verification: confirmed
- Evidence: `reference_data/generated_schema_coverage.csv` (row 2: `Husband_IRA | Husband_401k | Wife_IRA`); git history shows exactly one commit, the initial commit (2026-06-30) — never regenerated since; `reference_data/schema.csv` has zero matches for Husband/Wife terminology and no "Roth Conversion 1" entry at all; `src/schema_registry.py:37-59` (`load_schema` merges this file's rows into the live runtime schema whenever the key isn't already in `schema.csv` — confirmed **not dead code**, an active fallback); `src/parsing/advanced_modules.py:207-210` (current terminology is `Member_1`/`Member_2`).
- Observed behavior: the "Forced Actions / Roth Conversion 1 / source_account" field's live help text shows retired account-naming terminology to users.
- Impact: user-facing terminology confusion on this field; potentially incorrect if the underlying choice values were also renamed (not independently verified for this specific field).
- Options: (1) regenerate the file from current schema/terminology; (2) fold the 3 rows directly into `schema.csv` and stop shipping a separately-generated file nothing keeps fresh; (3) delete the row/file if the feature is retired.
- Recommendation: regenerate or fold in; verify first whether the "Forced Actions" feature is still live.
- Risk of change: Low (reference/help metadata, not calculation logic).

**ARC-004 — `src/data_io.py` is a very large (2,530-line), highly-coupled (~130–143 dependents) bridge module with a documented non-mechanical field-mapping contract**
- Severity: **Low** · Confidence: Medium · Verification: confirmed (dependent-count is approximate/order-of-magnitude, not exact)
- Evidence: `parse_client` at line 565, `build_plan_from_json` at line 2109; verifier's own recount within the actual project tree (excluding vendored/unrelated directories) found 143 importing files, 17 of them non-test source/tooling — same order of magnitude as originally stated; `src/module_catalog.py` comments (near lines 291, 1065, 1212) explicitly state its own field-mapping "is not a mechanical function" of the label, requiring other modules to hardcode cross-references.
- Impact: high blast radius for any change; implicit coupling contract easy to silently break.
- Recommendation: track as architecture debt; no action recommended now — consider a scoped extraction of the field-mapping table only if/when substantial new parsing logic is needed.
- Risk of change: N/A (no change recommended); high if pursued given the fan-in.

### Financial Planner (FIN)

**FIN-001 — Large Discretionary legacy-row migration silently drops malformed/zero-amount rows with no import notice**
- Severity: **Low** · Confidence: Medium · Verification: confirmed
- Jurisdiction/rule year: not applicable (data-handling, not tax law).
- Evidence: `src/large_discretionary.py:128-146` (`migrate_repeatable` — `if amount<=0 or _year(row.get('year')): continue`, and `if not start and not end: continue`, both silent, no notice emitted); `tests/test_large_discretionary_one_time_unit.py:24-50` (no coverage for either malformed-row shape).
- Impact: a legacy row with a positive amount but no year fields at all (or a negative/zero amount) disappears from migration with no trace — plausible for hand-edited CSV data, not verified against an actual client file.
- Recommendation: add an explicit notice branch for both silent `continue` paths, mirroring the pattern already used for successful expansions.
- Risk of change: Low.

**FIN-002 — Reserve Requirements legacy-checking-value warning can be suppressed by an unrelated `_Checking` account**
- Severity: **Low** · Confidence: Medium · Verification: confirmed
- Jurisdiction/rule year: not applicable.
- Evidence: `src/data_io.py:300-314` (`reserve_checking_import_warning` — suppressed by the mere *existence* of any `_Checking`-suffixed account, regardless of its balance); `src/data_io.py:1846-1857` (`cash_other` is genuinely sourced from `_Checking` holdings accounts only — confirming the warning is the sole signal a household gets).
- Impact: a household with a small, unrelated `_Checking` account plus a genuinely un-migrated legacy Reserve Requirements balance gets no warning at all, even though that legacy balance was never carried forward into `cash_other`.
- Recommendation: tighten the heuristic to compare the legacy value against the sum of actual `_Checking` balances rather than a bare existence check. This is a minor follow-up to an already-shipped, otherwise-correct fix — the underlying `cash_other` math is correct in every case inspected.
- Risk of change: Low.

*(Financial-domain spot-checks that found no material issue, independently re-verified: IRMAA consolidation to a single live implementation in `src/tax_kernel.py` sourced from `reference_data/tax_law_v10.json`, self-labeled "assumption" rather than a cited authoritative source — flagged for professional review, not a defect; RMD-divisor consolidation, backed by a 182-combination cross-implementation equivalence test; the "Next Housing Move" off-switch genuinely clears the engine config keys it claims to, not merely hiding UI.)*

### Usability / Accessibility (UX)

**UX-001 — Universal field-rendering helper produces form controls with no programmatic accessible name**
- Severity: **High** · Confidence: High · Verification: confirmed
- Evidence: `frontend/js/dashboard_decomp_row_model.js:2648-2727` (`fieldHtml()` — the shared function rendering the large majority of plan-data inputs app-wide; its `<select>`/`<input>` controls carry only `data-row`/`data-focus-key` attributes, never `id`, `aria-label`, or `aria-labelledby`; the visible label is a plain sibling `<div class="field-label">`, never wired via `for=` or `aria-labelledby`); `frontend/js/dashboard_decomp_housing_scenarios.js:708-713` (`zipFieldHtml`, identical gap); repo-wide grep confirms sparse ARIA usage relative to file size and that the large majority of `<label>` tags have no `for=` attribute.
- Impact: a screen-reader user tabbing through any guided step, Field Finder, or housing panel hears unnamed controls ("edit text, blank") repeated across hundreds of fields — a primary-task blocker, not a cosmetic gap, for a financial-planning app where a wrong entry has real consequences.
- Affected workflows: all guided-step data entry, Field Finder, Next Housing Move / housing panels, Spending Model.
- Recommendation: add a stable `id` to each generated control and change `.field-label` to a real `<label for=...>` (lowest-risk — CSS targets classes, not element type).
- Implementation considerations: `fieldHtml()` is invoked from many decomp modules; must be checked against panel-JS-as-text assertion tests per repo convention.
- Risk of change: low functional risk; regression risk is in test-string matching, not runtime behavior.
- Verification method: static confirmed; recommend an actual NVDA/VoiceOver pass before closing.

**UX-002 — The single global error/success banner is not an ARIA live region**
- Severity: **High** · Confidence: High · Verification: confirmed
- Evidence: `frontend/index.html:73` (`#actionMessage`, no `aria-live`/`role`) vs. `:74` (`#planStateBanner`, has `aria-live="polite"` — the pattern is known elsewhere in the same file, just not applied here); `frontend/js/dashboard_decomp_row_model.js:140-167` (`showMessage()`, auto-hides via 10-second timeout); 233 call sites confirmed repo-wide (originally estimated 80+ — actually more prevalent).
- Impact: screen-reader users get no proactive notification of save/build success or failure unless focus happens to be near the element; combined with UX-001, the feedback loop for financial data entry is effectively silent for that population.
- Recommendation: add `aria-live="polite" role="status"` by default, `aria-live="assertive"` only for error-kind messages (to avoid noisy interruption on routine autosave toasts).
- Risk of change: very low (attribute-only change).

**UX-003 — Field-level required/error state is visual-only, not programmatically associated with the input**
- Severity: **Medium** · Confidence: High · Verification: confirmed
- Evidence: `dashboard_decomp_row_model.js:2701,2727` (Required badge in a sibling div, not `aria-describedby`-linked); `:4201-4212` (`editValue()` toggles CSS classes only); zero repo-wide hits for `aria-invalid`/`is-invalid`/`field-error`/`validationError`.
- Impact: no screen-reader-associated error message exists for required/missing fields; malformed (non-required) numeric input is silently reformatted with no feedback of any kind.
- Recommendation: wire `aria-invalid`/`aria-describedby` into the existing required-badge path (depends on UX-001's `id` addition for a stable anchor).
- Risk of change: Low.

**UX-004 — Structured backend validation errors are surfaced consistently in only a minority of catch blocks (corrected: at least two of ~30+ sites, not exactly one)**
- Severity: **Medium** · Confidence: High · Verification: partially_confirmed — corrected count
- Evidence: `frontend/js/api_client.js:37-44` (attaches a structured `err.errors` array on non-OK responses); `dashboard_decomp_row_model.js:4877-4896` (`saveWorkingCopy()` catch block preserves the full list persistently); the verifier found a **second** site, `dashboard_decomp_build_history.js:197-202` (snapshot-revert catch), that also handles `e.errors`, differently (inlines up to 3 into the toast text rather than the persistent/expandable pattern) — so the underlying claim of inconsistency across ~30+ other `catch` blocks that drop `e.errors` entirely is real, but the precise framing should read "at least two differently-implemented handling patterns," not "only one."
- Recommendation: extract a shared `showApiError(e, prefix)` helper and route all catch blocks through it, degrading gracefully when `errors` is absent.
- Risk of change: Low.

**UX-005 — No `prefers-reduced-motion` or `prefers-color-scheme` support anywhere in CSS**
- Severity: Low · Confidence: High (submitted by expert; not independently re-verified — below the mandatory verification threshold)
- Evidence: zero matches for either media feature across `frontend/css/dashboard.css` and `admin.css`; fixed light-mode-only color tokens.
- Recommendation: add `prefers-reduced-motion` support opportunistically; treat dark mode as a separate, larger effort.
- Risk of change: very low.

**UX-006 — Duplicate, unscoped `.msg-dismiss`/`.msg-action` CSS rules — a later block silently overrides the sized/circular dismiss button with an undersized one**
- Severity: **Low** · Confidence: Medium → confirmed at High by verifier · Verification: confirmed
- Evidence: `frontend/css/dashboard.css:135-141` (first `.msg-dismiss` definition, 22×22px circular) vs. `:319-323` (second definition, transparent background, no explicit sizing, `opacity:.7`) — no media query separates them; the later rule wins the cascade outright. The same duplicate pattern also exists for `.msg-action` (lines 140 vs. 320).
- Impact: the effective dismiss-button hit target falls below the WCAG 2.5.8 24×24 CSS-px minimum, and the intended circular affordance never renders.
- Recommendation: delete the stale definition; keep one `.msg-dismiss` rule sized at least 24×24px.
- Risk of change: very low.

### Documentation (DOC)

**DOC-001 — `CURRENT_SYSTEM_DESIGN_SPEC.md`'s navigation-model section (§7.3) describes the pre-restructure nav groups, not the current ones**
- Severity: **Medium** · Confidence: High · Verification: confirmed (mismatch is real and substantial, not a minor rewording)
- Evidence: doc lines 486-492 list "People and Income," "Assets & Protection," "Stress Tests" — none of which match the current `frontend/js/dashboard.js` STEPS groups (Household, Income & Benefits, Investments & Property, Insurance & Care, Estate & Legacy, etc.); doc last touched 2026-09-14, before PRs #138/#139 (2026-09-2x) restructured this exact subsystem.
- Recommendation: regenerate §7.3 from the current `group:` literals in `dashboard.js`.
- Risk of change: none (documentation-only).

**DOC-002 — `conftest.py` cites a documentation path that no longer exists**
- Severity: **Low** · Confidence: High · Verification: confirmed
- Evidence: `conftest.py:1-6` cites `documentation/SYSTEM_REVIEW_AND_REFACTOR_PLAN.md`; the file actually lives at `documentation/archive/legacy/SYSTEM_REVIEW_AND_REFACTOR_PLAN.md` (confirmed: the root-level path does not exist, the archive path does).
- Recommendation: one-line docstring fix.
- Risk of change: none.

**DOC-003 — The project's auto-loaded `.claude/CLAUDE.md` cites a housing-module file (`src/housing/screen.py`) and size table that are stale post-restructure**
- Severity: **Medium** · Confidence: High · Verification: confirmed, and the verifier found the problem is *broader* than reported — the entire size table for this directory is stale, not just the one path
- Evidence: `.claude/CLAUDE.md:29-30` cites `screen.py` (402 lines), `api.py` (498 lines), `plan_variant.py` (243 lines); current tree has no `screen.py` at that path (`git log` confirms it never existed there — PR #138 restructured it away); the verifier found the file now actually exists at `src/housing/zip_screen/screen.py` at 532 lines, and that `api.py` is actually 692 lines (not 498) and `plan_variant.py` is 309 (not 243) — i.e. every number in this table is wrong post-restructure.
- Impact: this is the file every Claude Code session in this repo auto-loads; a future session following this table's guidance would grep for a nonexistent file and get wrong line-count expectations for the other two.
- Recommendation: update the footnote with current paths/line counts, or reword to avoid hardcoding filenames that will drift on the next restructure.
- Risk of change: none.

**DOC-004 — Two unrelated "W"-numbering schemes coexist in `docs/superpowers/`, contemporaneous and likely to cause search confusion**
- Severity: **Low** · Confidence: High · Verification: confirmed
- Evidence: `docs/superpowers/plans/2026-09-21..23-w0` through `w13`-named files (an earlier catalog-foundation/nav-realignment workstream) vs. the `W-A`..`W-F` lettering used by PR branch names #134–#139 and `docs/superpowers/specs/2026-09-24-taxonomy-and-spending-restructure-design.md` — both schemes reuse "W" for entirely different, contemporaneous work.
- Recommendation: add a brief disambiguating note rather than renaming completed/merged work.
- Risk of change: none (additive).

**DOC-005 — Version-number disagreement across `pyproject.toml`/`package.json` (10.0.0) vs. `src/version.py`/`system_config.csv` (12), with no documentation explaining the split — and the version tool's actual sweep scope is narrower than believed**
- Severity: **Low** · Confidence: High (mechanism corrected) · Verification: partially_confirmed
- Evidence: `pyproject.toml:56`, `package.json:3` both say `10.0.0`; `src/version.py:5` (`VERSION = '12'`, "single source of truth for product/version labels"); `system_config.csv:2` (`system_version=12`); `documentation/reference/CONTRIBUTING.md` has zero mentions of "version." **Correction from adversarial verification:** the original framing that `tools/bump_version.py` "only updates `src/version.py`" is inaccurate — its own docstring says it also updates `frontend/index.html`, `frontend/admin.html`, `system_config.csv`, and re-runs two sync-check scripts. The real gap is narrower and more precise: that documented sweep simply never mentions `pyproject.toml` or `package.json` at all.
- Recommendation: either wire `pyproject.toml`/`package.json` into `bump_version.py`'s sweep, or explicitly document why they're allowed to diverge.
- Risk of change: Low if done as an additive sweep entry.

**DOC-006 — `OPTIMIZATION_REFACTOR_STATUS.md` reads as a stale progress-tracker for a now-fully-completed refactor, with no content-currency test unlike its sibling docs**
- Severity: **Low** · Confidence: Medium → High after verification · Verification: confirmed
- Evidence: every item under its "## Not done" heading (lines 469-499) is struck through/marked done; `tests/test_optimization_docs_index_regression.py` only checks index-membership/cross-linking, not content currency — unlike `FUNCTIONAL_SPEC.md`'s dedicated `FEATURE_MARKERS` currency test.
- Recommendation: archive the file (with an index update) or add a minimal currency check if a new optimization phase is expected to reuse it.
- Risk of change: low, purely organizational.

**DOC-007 — `documentation/archive/MODULE_REFRAMING_INPUTS_OUTPUTS.md` is filed as historical but is cited as live, authoritative design rationale from inside actively-maintained source code**
- Severity: **Low** · Confidence: High · Verification: confirmed
- Evidence: `src/module_catalog.py:1-3` states it is "the codified form of `documentation/archive/MODULE_REFRAMING_INPUTS_OUTPUTS.md` (v2)" — an exact-path citation from a module this review's other findings confirm is central to the recent taxonomy restructure.
- Impact: a reader following this project's own archive/ = historical convention would skip load-bearing design context.
- Recommendation: add a short pointer in `documentation/reference/` noting this archived file remains live context for `module_catalog.py`.
- Risk of change: low if handled as an additive pointer rather than a file move.

**DOC-009 — The auto-loaded `.claude/CLAUDE.md` and the fuller `documentation/reference/CLAUDE.md` have entirely non-overlapping content, with no forward-pointer from the auto-loaded file**
- Severity: **Low** · Confidence: Medium → High after verification · Verification: confirmed
- Evidence: the 49-line auto-loaded file has no testing-discipline table, no architecture overview, and no mention of the 274-line fuller file, which contains a "Testing Discipline — MANDATORY" table and a full architecture section; only `CONTRIBUTING.md:88` links the two, and `CONTRIBUTING.md` is itself not auto-loaded.
- Impact: a session or developer relying only on the auto-loaded file can easily miss guidance this project describes elsewhere as mandatory.
- Recommendation: add a one-line forward-pointer in `.claude/CLAUDE.md`.
- Risk of change: none.

*(DOC-008, a jargon-density claim about `FUNCTIONAL_SPEC.md`, was refuted on adversarial verification — see [Section 13](#13-finding-disposition-appendix).)*

### Quality (QA)

**QA-002 — Scalar-vs-vectorized survivor-economics equivalence test never executes in any automated pipeline**
- Severity: **High** · Confidence: High · Verification: confirmed
- Evidence: `tests/test_scalar_vectorized_survivor_reconciliation.py:47` (`@unittest.skipUnless(os.environ.get('RUN_SLOW_MC_RECONCILIATION'), ...)`); repo-wide grep confirms this environment variable is never set anywhere — not in `.github/workflows/ci.yml`, not in `nightly.yml`, not in any `tox.ini`/`Makefile`/`package.json` script/`tools/` or `scripts/` shell script. The nightly workflow's unfiltered full-suite run selects this test (no `slow`/`nightly` marker excludes it) and then it immediately self-skips.
- Impact: this test — described in its own docstring as an acceptance criterion for a completed engine-optimization phase, and exactly the class of test that would catch scalar/vectorized divergence in survivor economics — provides **zero automated regression protection**, ever.
- Recommendation: add a `nightly`/`slow` pytest marker (removing the unwired env-var gate) so the nightly workflow's existing unfiltered run actually executes it; reduce `n_sims` if runtime is the blocker.
- Risk of change: low (test/CI-config-only change, does not touch `src/`).

**QA-003 — Golden-master provenance enforcement covers only 1 of 3 pinned-output mechanisms**
- Severity: **High** · Confidence: High (raised from Medium after verification) · Verification: confirmed
- Evidence: `tests/test_golden_master_pin_provenance.py:62-64` hardcodes its provenance check to a single file/two constants; `tests/test_synthetic_golden_master.py` and `tests/test_deterministic_engine_full_row_snapshot_regression.py` have **no test-level** provenance/reason/changelog binding at all — the latter's only safeguard is a CLI tool (`tools/regen_full_row_snapshot.py`) that refuses to run without a `--reason` string, which is a courtesy check on the regeneration path, not an enforcement point that fails the suite if the fixture is hand-edited directly.
- Impact: this project's own stated design principle — "a tool that merely asks nicely for a justification is not an enforcement point... it has to fail the suite, not just refuse a command" — is violated for two of the three golden-master mechanisms. A hand-edited fixture entry would silence a real engine regression with nothing to catch it.
- Recommendation: generalize the existing, well-designed provenance-marker pattern to both remaining fixtures.
- Risk of change: low, purely additive test/tooling change.

**QA-006 — The actual budget-corruption recovery logic has zero direct test coverage**
- Severity: **High** · Confidence: High (raised from Medium after verification) · Verification: confirmed
- Evidence: `src/spending_tracker.py:1023-1131` (`recover_spending_budget_from_seed`, its `force=False` "never overwrite nonzero rows" guard, its one-time `.pre_recovery_backup` write, and `load_unified_budget()`'s automatic zero-row-triggered recovery); repo-wide grep for these exact symbol names across `tests/*.py` returns **zero matches** — the only test touching the same seed-file path (`tests/test_demo_plan_open_restore.py:210-233`) exercises an unrelated demo-mode file-swap feature, not this function's merge/overwrite semantics.
- Impact: this function's entire purpose is protecting real user financial data after an autosave-regression event; recovery-artifact files present in `input/` (`.pre_recovery_backup`, `.recovery_seed.csv`) are consistent with this path having actually fired for a real user at some point. Untested, a future edit could invert the "never overwrite nonzero rows" guard and start silently clobbering real user data, or break the auto-trigger so a corrupted budget is never recovered — and nothing in the suite would catch either.
- Recommendation: add a functional test (seed a zeroed budget + nonzero recovery-seed file, assert auto-recovery; assert `force=False` doesn't overwrite nonzero rows; assert the one-time backup write behavior) using the existing `tmp_path`/workspace-isolation fixture pattern.
- Risk of change: low to add.

**QA-001 — Stale citation underpins the pytest marker-taxonomy retrofit decision**
- Severity: **Low** · Confidence: High · Verification: confirmed
- Evidence: `pyproject.toml:14-19`'s marker-taxonomy comment cites `tests/test_freeze_numbered_test_files.py`, which was deleted ~7 weeks before this review (commit `56c457a`); its actual replacement, `tests/test_no_tracking_id_test_names_regression.py`, enforces a materially narrower rule (blocks new tracking-id-style names, doesn't freeze the file tree).
- Recommendation: update the comment to cite the correct current guard and its actual (narrower) scope.
- Risk of change: none.

**QA-004 — The `dashboard.js` direct-read guard is pattern-based, not AST-based, with enumerable blind spots**
- Severity: **Medium** · Confidence: High · Verification: confirmed
- Evidence: `tests/test_dashboard_decomp_test_no_direct_reads_guard.py:58-94` — five literal regex patterns anchored on `.read_text`/`open(`; confirmed via direct trace that `.open(...).read()`, `.read_bytes()`, and `open(var).read()` (for a path bound to a variable) all evade detection.
- Recommendation: broaden detection (ideally AST-based) and extend the guard's own planted-violation self-test to cover these evasion shapes.
- Risk of change: low, test-only.

**QA-005 — Duplicate, independently-maintained `dashboard.js`-concatenation helpers, invisible to the guard test**
- Severity: **Low** · Confidence: High · Verification: confirmed
- Evidence: `tests/_decomp_dashboard.py:32-38` (`dashboard_js_text()`, the canonical helper) vs. `tests/conftest.py:260-277` (`dashboard_js_sources()`, an independent, functionally-identical reimplementation used by 3 other test files); the guard test only globs `test_*.py`, so neither `conftest.py` nor `_decomp_dashboard.py` is checked by it.
- Recommendation: consolidate to one implementation.
- Risk of change: low.

**QA-007 — `sample_config()` is redefined ~30 times across test files with subtly different bodies, not a shared fixture**
- Severity: **Low** · Confidence: High · Verification: confirmed
- Evidence: 30 independent `def sample_config()` occurrences confirmed via grep; `conftest.py` itself defines no such fixture; bodies diverge in whether they call `ensure_engine_config()`, set `roth_policy`/`mc_paths`, etc.
- Recommendation: consolidate common cases into a small number of named, documented builder functions, migrated incrementally; not urgent.
- Risk of change: medium if consolidated carelessly, low if done incrementally with review.

---

## 6. Options and Tradeoffs

Per-finding options are listed inline in [Section 5](#5-material-findings). System-level tradeoffs worth calling out explicitly:

- **ARC-001 fix timing:** could be bundled with ARC-002 (same file) in one PR, or split to keep the atomic-write fix (higher severity, more urgent) reviewable independently of the error-signaling improvement (lower severity, more discretionary). Recommendation: split — ARC-001 alone is a small, low-risk, high-value change that shouldn't wait on ARC-002's review.
- **UX-001 scope:** the shared `fieldHtml()` fix is high-leverage (covers the large majority of fields in one change) but touches a function reused across many decomp modules with panel-JS-as-text test assertions that may need updating. Options: do it in one pass (higher review burden, fixes everything at once) vs. incrementally per-panel (lower risk per change, longer time-to-full-fix, and a real chance some panels are missed). Recommendation: one pass, given the `id`/`for` change is additive and should not alter existing test-string matches unless a test literally asserts on the *absence* of an `id` attribute (unlikely).
- **QA-002/QA-003 cost vs. safety:** both fixes are cheap to make (a marker addition; extending an existing provenance pattern) relative to the risk they close (silent regression in exactly the areas — survivor economics, engine numeric consolidation — this project has previously needed golden-master protection for). No credible reason to defer these past the next engine-touching change.

---

## 7. Recommendation

Address in this order, reflecting the priority hierarchy (financial safety → data integrity → legal/regulatory correctness → security/privacy → functional correctness → maintainability → usability/accessibility → documentation → performance/cost → cosmetic polish):

1. **ARC-001** (data integrity, High) — atomic-write the plan-data CSV migration. Small, isolated, high-value.
2. **QA-006** (data integrity / test coverage, High) — cover the budget-recovery function before its "never overwrites nonzero data" guarantee is trusted any further.
3. **QA-002, QA-003** (test-safety-net integrity, High) — wire the orphaned equivalence test into the nightly run; extend golden-master provenance enforcement to the two uncovered fixtures.
4. **UX-001, UX-002** (accessibility, High) — accessible names in the shared field renderer; a live region on the global message banner. Bundle with UX-003 (depends on UX-001's `id` addition).
5. **ARC-002, ARC-003, UX-004, UX-006, QA-004, QA-005, FIN-001, FIN-002** (Medium/Low, functional/maintainability) — batch into a general cleanup wave.
6. **Documentation cluster** (DOC-001 through DOC-007, DOC-009) — cheap, no-risk fixes; worth doing in one pass since several are one-line corrections.
7. **Explicit follow-up, not covered by this standard-depth review:** Roth conversion/AGI interaction, QLAC, withdrawal-cascade sequencing, survivor/spousal-rollover paths (financial-domain correctness); a dedicated performance pass; a full repo-wide committed-secret scan (this review's available secret-scanning tool could only scan supplied content, not the whole repository).

---

## 8. Target Design

No architectural redesign is warranted by this review's findings — the existing architecture (pipeline-stage decomposition, atomic-write persistence convention, golden-master regression protection, delegation-based duplicate-implementation consolidation) is sound and should be *extended to cover its own gaps*, not replaced:

- **Persistence:** every writer of household data, including startup migration, should go through `plan_file_io.atomic_write` — no exceptions. Target state: a lint/test rule that fails if a new writer of `input/*` or `saved_plans/*` bypasses this helper.
- **Accessibility:** `fieldHtml()` and `zipFieldHtml()` should assign a stable `id` to every rendered control and change the sibling label div to a real `<label for=...>`; the global `#actionMessage` element should carry `aria-live="polite" role="status"` (assertive only for error-kind messages). Target state: any new field-rendering helper added later inherits this contract rather than reintroducing the gap.
- **Golden-master provenance:** every pinned-fixture mechanism (not just the frozen-sample-plan one) should carry a test-enforced provenance binding, not merely a CLI-tool courtesy check. Target state: a shared provenance-marker pattern usable by all three (and any future) golden-master fixtures.
- **Data flows/validation:** no change to the underlying calculation flow is recommended; the gaps found are at the edges (migration write-safety, recovery-function coverage, accessible-name wiring), not in the core projection pipeline.
- **Assumptions:** IRMAA and estate-tax dollar tables in `reference_data/` should carry an explicit provenance/citation field distinguishing "sourced from a named authority" from "assumption," rather than the current bare `"status": "assumption"` label with no further detail — this is a documentation/governance improvement, not a code defect.

---

## 9. Implementation Waves

Dependency-ordered; items in the same wave with no shared files/components are genuinely parallelizable.

**Wave 1 — Data integrity (highest priority, mostly independent files)**
| ID | Change | Findings | Depends on | Parallel group | Effort | Risk | Validation / exit criteria |
|---|---|---|---|---|---|---|---|
| W1-A | Route CSV migration rewrite through `atomic_write` | ARC-001 | — | A | Low | Low | New test simulates a mid-write interruption; asserts original file unchanged. Existing `tests/test_plan_data_migration.py` still passes (read the assertions, do not execute — this review does not claim pass/fail). |
| W1-B | Add `error` key to outer exception handler | ARC-002 | W1-A (same file, `src/plan_data_migration.py` — sequence after W1-A, not genuinely parallel) | A-2 (sequenced after group A, not concurrent with it) | Low | Low | New test forces `workspace_root()` to raise; asserts returned dict has an `error` key and `main.py`'s existing warning branch fires. |
| W1-C | Add direct test coverage for `recover_spending_budget_from_seed` | QA-006 | — | B | Medium | Low | New functional test covers auto-trigger, `force=False` non-overwrite guarantee, one-time backup-write behavior. |

**Wave 2 — Test-safety-net integrity**
| ID | Change | Findings | Depends on | Parallel group | Effort | Risk | Validation / exit criteria |
|---|---|---|---|---|---|---|---|
| W2-A | Wire scalar/vectorized survivor test into nightly (marker or explicit env var) | QA-002 | — | A | Low | Low | Confirm (statically) a `nightly`/`slow` marker or env-var assignment reaches this file from an actual workflow step. |
| W2-B | Extend golden-master provenance enforcement to the two uncovered fixtures | QA-003 | — | A | Medium | Low | New provenance test fails when either JSON fixture changes without an accompanying marker/changelog entry. |
| W2-C | Broaden dashboard-decomp direct-read guard detection | QA-004 | — | A | Low | Low | Add the identified evasion strings to the guard's own planted-violation self-test; confirm (statically) they'd now be caught. |

**Wave 3 — Accessibility (shared-component change, needs care)**
| ID | Change | Findings | Depends on | Parallel group | Effort | Risk | Validation / exit criteria |
|---|---|---|---|---|---|---|---|
| W3-A | Add `id`/`<label for>` to `fieldHtml()` and `zipFieldHtml()` | UX-001 | — | A | Medium | Low (functional); test-string-match risk | Re-grep `<label for=` count before/after; check against panel-JS-as-text test assertions; recommend a manual screen-reader pass before closing. |
| W3-B | Add `aria-live`/`role="status"` to `#actionMessage` | UX-002 | — | B (independent of W3-A) | Low | Very low | Manual NVDA/VoiceOver pass to confirm announcement timing. |
| W3-C | Wire `aria-invalid`/`aria-describedby` into required-field state | UX-003 | W3-A | — | Low | Low | Confirm both input and message element share a stable `id` pair. |

**Wave 4 — Medium/Low cleanup (batch, mostly independent)**
| ID | Change | Findings | Depends on | Parallel group | Effort | Risk |
|---|---|---|---|---|---|---|
| W4-A | Regenerate or fold in `generated_schema_coverage.csv` | ARC-003 | — | A | Low | Low |
| W4-B | Extract shared `showApiError()` helper | UX-004 | — | B | Medium | Low |
| W4-C | Consolidate duplicate `dashboard.js`-concat test helpers | QA-005 | — | C | Low | Low |
| W4-D | Add notice branches for silently-dropped legacy rows | FIN-001 | — | D | Low | Low |
| W4-E | Tighten Reserve Requirements warning heuristic | FIN-002 | — | D | Low | Low |
| W4-F | Delete stale `.msg-dismiss`/`.msg-action` CSS rule | UX-006 | — | E | Trivial | Very low |
| W4-G | Fix stale marker-taxonomy citation | QA-001 | — | E | Trivial | None |

**Wave 5 — Documentation (independent, batchable in one pass)**
| ID | Change | Findings |
|---|---|---|
| W5 | Fix all of DOC-001, DOC-002, DOC-003, DOC-004, DOC-005, DOC-006, DOC-007, DOC-009 | as listed |

**Explicitly not in any wave (out of this review's scope, needs a dedicated follow-up):** Roth conversion/AGI interaction, QLAC, withdrawal-cascade sequencing, survivor/spousal-rollover domain-correctness review; a dedicated performance pass; a full repo-committed-secret scan.

---

## 10. Validation Plan

- **Per-item:** validation/exit criteria are listed in each Wave 1–3 row above; Wave 4/5 items are small enough that a code-review-level check plus the item's own existing test suite (read, not executed, per this review's static scope) is sufficient.
- **System acceptance criteria:** after Waves 1–3 land, (a) no persistence writer of `input/*`/`saved_plans/*` bypasses `atomic_write` (spot-check via grep for `.write_text(` against those paths), (b) the three golden-master mechanisms all have test-enforced provenance, (c) an automated accessibility check (axe-core or equivalent, run by the implementing team — not part of this static review) reports no missing-accessible-name violations on at least one representative guided-step page.
- **Not validated by this review:** anything requiring test execution, a live browser, or a screen reader — `Runtime behavior was not validated during this review.` Whoever implements these waves should run the actual test suite and, for the accessibility items, a real assistive-technology pass, before closing them.

---

## 11. Assumptions and Open Questions

- **Technical:** whether any process outside this repository depends on `pyproject.toml`'s frozen `10.0.0` value (DOC-005) — not checked, out of scope.
- **Jurisdiction/rule-year:** IRMAA and estate-tax dollar tables in `reference_data/tax_law_v10.json` are self-labeled `"status": "assumption"` rather than citing a specific authoritative CMS/NY DTF publication — a qualified CPA/CFP (federal/Medicare) and estate attorney (IL/NY estate tax) should confirm current-year figures before they're relied on for a real client, especially for years where indexing is a modeled assumption rather than a published table.
- **External facts:** the original cause of the `client_spending_budget` recovery-artifact files (`*.pre_recovery_backup`, `*.recovery_seed.csv`) could not be determined from git history alone within this review's scope; if the user recalls the original incident, that context would sharpen QA-006's priority.
- **Professional-review needs:** the 1959-birth-cohort SECURE 2.0 RMD-start-age interpretation (documented, deliberate IRS-Notice-2023-54-aligned choice) should be reconfirmed by a qualified professional for any household actually in that cohort, since it reflects an administrative position, not settled law.
- **Open question for the user:** is the "Forced Actions / Roth Conversion 1" feature referenced in ARC-003 still live in the current UI? This determines whether the fix is "regenerate the stale reference data" or "delete the retired feature's leftover row."

---

## 12. Review Limitations

- `CI was intentionally excluded from this review.`
- `Runtime behavior was not validated during this review.`
- This review's own orchestration workflow (`Workflow` tool, `scriptPath: ".claude/workflows/system-review.js"`) failed to invoke due to an environment/permission-handler bug (a false-positive "control characters" validation error against a script file independently confirmed to contain none); the review was conducted manually per the skill's documented fallback procedure, using directly-dispatched subagents for reconnaissance, the five-expert panel, and adversarial verification, applying the same rules at each step. This is a process-mechanics note, not a scope reduction.
- Large files (`dashboard.js` 7,287 lines, `dashboard_decomp_row_model.js` 5,188 lines, `workbook_builder.py` 1,443 lines, `workbook_common.py` 1,161 lines, `module_catalog.py` 916 lines) were grep-targeted per this project's own documented convention, not read in full — a general-purpose quality/dead-code audit of their entire contents was not performed.
- Roth conversion/AGI interaction, QLAC, withdrawal-cascade sequencing, survivor/spousal-rollover, and state income tax (`load_state_tax`) were **not inspected** in this pass — a genuine coverage gap, not a clean bill of health.
- No dedicated performance review was performed.
- Repo-committed-secret risk is not fully assessed: the GitHub secret-scanning tool available to this review scans supplied file content only, not the whole repository, and native GitHub secret-scanning alerts were not accessible.
- No live screen-reader session, contrast-ratio measurement, or browser rendering was possible — all accessibility findings rest on markup/CSS inference.
- 443 test files cannot all be read individually; a representative sample plus every file directly implicated by a reconnaissance lead was read.
- `git log --all` and read-only git commands were used to establish provenance/history claims; no working-tree or index state was modified beyond the initial fast-forward pull of `.claude/workflows/system-review.js` (a tooling file, not application code) at the start of this session.
- A stray `.claude/worktrees/agent-a7c93ffbcc3098217/` directory containing a full parallel copy of `documentation/` from an apparently abandoned prior agent session was noticed but not investigated further (not a documentation-content issue; a maintainer may want to clean it up).

---

## 13. Finding Disposition Appendix

| ID | Original severity | Disposition | Reason |
|---|---|---|---|
| DOC-008 | Low | **Refuted** | Claimed `FUNCTIONAL_SPEC.md` uses 8 acronyms (LCV, ELTR, FCV, EFTR, TLH, QLAC, IRMAA, AMT) without inline plain-language glosses. Adversarial verification found 6 of the 8 *are* glossed at first use (LCV, ELTR, FCV/EFTR, TLH, QLAC), and AMT does not appear anywhere in the document at all (zero grep matches) — the finding cited a term not present in the file. Only IRMAA genuinely lacks an inline gloss. The premise does not hold as stated; this reads as a documentation-reading error rather than a defensible (if subjective) clarity finding, so it is refuted rather than retained at reduced severity. No replacement finding was written for the single IRMAA instance, since one ungrossed acronym in an otherwise well-glossed document falls below this review's material-finding bar. |

No findings were marked duplicate, superseded, or insufficient-evidence in this review. UX-004 and DOC-005 were `partially_confirmed` (retained, with corrected framing — see [Section 5](#5-material-findings)); all other findings were `confirmed` as originally scoped or with a severity/confidence adjustment noted inline.

---

## 14. Financial Planner Sign-off

**Verdict: Approved with changes.**

The financial planner read the complete synthesized report and independently spot-checked four findings directly against source (ARC-001/ARC-002 in `src/plan_data_migration.py`, UX-001 in `fieldHtml()`, QA-002's `RUN_SLOW_MC_RECONCILIATION` env-var gate, and DOC-003's stale housing-file table in `.claude/CLAUDE.md`) — all four held up exactly as described. Confirmed: both required verbatim disclaimer sentences are present in Section 12; no Critical/High finding was left unverified; the financial-domain content (FIN-001, FIN-002, and the IRMAA/RMD-divisor/estate-tax/housing-off-switch spot-checks) is properly caveated as needing professional review rather than presented as advice; the report never asserts a test pass/fail as a runtime fact anywhere.

**Requested changes — both material, both applied:**

1. **PC-1 (severity accounting):** the Executive Summary's Medium/Low breakdown did not match a recount of Section 5's per-finding severity tags (Medium was overstated at 9 instead of 7; Low was understated at 12 instead of 14 — total of 27 was correct). *Resolution: corrected in Section 1 to "6 High, 7 Medium, 14 Low," independently re-verified by the orchestrator against every finding's stated severity.*
2. **PC-2 (wave-sequencing consistency):** Wave 1's W1-A and W1-B were both assigned to parallel group "A" despite both targeting `src/plan_data_migration.py` and the table's own dependency note saying W1-B should sequence after W1-A — a direct violation of this report's own stated wave-construction rule ("items in the same wave with no shared files/components are genuinely parallelizable"). *Resolution: W1-B moved to group "A-2," explicitly sequenced after group A rather than concurrent with it.*

**Unresolved dissent (non-material, not acted on):** the planner noted UX-006's "Confidence: Medium → confirmed at High by verifier" phrasing reads ambiguously on first pass (could be misread as a severity escalation rather than a confidence escalation) but did not consider this material enough to require a wording change; left as-is.

**Impact analysis:** both changes are corrections to internal consistency (a count and a dependency-ordering label) — neither changes any finding's severity, recommendation, or the underlying evidence for any finding. No other finding, coverage-matrix entry, or wave assignment was affected.
