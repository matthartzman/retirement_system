# System Review — Retirement Planning Version 10

**Date:** 2026-07-21
**Scope:** Full-system expert panel — architecture, usability, documentation/content, test quality, and financial-planning correctness.
**Status:** Read-only review. No source was modified. This document is the only artifact produced.
**Method:** Five independent expert reviews of the entire system, each finding verified against the source before inclusion. Two architecture findings were refuted during cross-check and are recorded in the Appendix. Every file:line citation below was carried from a verified finding; a sample (`sheets_strategy.py:187`, `sheets_strategy.py:1100-1112`) was re-opened and confirmed while writing this report.

---

## 1. Executive Summary

The system is a mature, heavily-tested retirement-planning engine with a guided-input single-page app front end and an Excel/PDF/HTML reporting pipeline. It is not broken. The findings are about **finishing half-done migrations, removing traps, closing correctness gaps in the advice it gives, and pointing test effort at where the risk actually lives.** The eight things that matter most, in plain language:

1. **The Roth-conversion IRMAA guardrail is throttling the tool's single most valuable recommendation for non-ACA-bridge clients.** It caps conversions on *this year's* income even in ages 60–64, where the IRMAA surcharge (a 2-year-lagged, Medicare-age-gated Medicare premium add-on) cannot possibly apply yet. Pre-Medicare clients **not** on ACA coverage in the gap years (retiree-medical/COBRA/self-pay) get systematically smaller recommended conversions than they should. (For ACA-bridge clients a separate, tighter ACA premium-tax-credit MAGI guardrail already binds well before the IRMAA cap, so this fix unlocks little for them — see §2E-P1.) **Payoff: the core deliverable stops under-recommending in exactly the gap years where conversions are most valuable.** (planner, high)

2. **The Social Security claim-age recommendation is scored on a formula that double-counts benefits and ignores longevity.** The headline "recommended claim age" ranks 81 spouse-age pairs on `terminal + lifetime_ss − lifetime_tax − irmaa`, but terminal net worth *already* reflects Social Security. The genuine reason to delay — survivor and longevity protection — is explicitly excluded from the score. **Payoff: the headline advice stops pointing the wrong way for couples where delaying protects the survivor.** (planner, high)

3. **Two estate/relocation reporting defects destroy planner trust for the exact clients those sections target.** The federal-estate section prints "Estate well below $30M exemption — no federal tax likely" *unconditionally*, even directly beneath a computed positive tax. The state-residency comparison's "Delta vs IL" baseline is tied to dictionary iteration order, not to Illinois. **Payoff: high-net-worth and relocation-minded clients stop seeing self-contradicting output.** (planner, medium)

4. **The main 3-column layout overflows horizontally on the most common laptop widths.** The grid arithmetically needs ~1460px but only collapses to single-column below 1180px, so 1280×800, 1366×768, and 1440×900 all get horizontal scrollbars instead of the clean stacked layout the CSS already defines. **Payoff: the app stops looking broken on the majority of screens that view it.** (usability, high)

5. **The test suite's shape is inverted from where the product's risk lives.** ~91 test files assert literal source-code substrings (function names, CSS classes, doc phrases) rather than executed behavior; the 16,500-line front-end file every user touches has real behavioral coverage of about nine pure helpers; and there is near-zero coverage of malformed input or mid-plan insolvency in a tool where garbage-in must fail predictably. **Payoff: refactors stop being blocked by brittle string tests, and the highest-risk surfaces gain a real safety net.** (quality, high)

6. **User-facing jargon bypasses the app's own auto-glossary.** "QSS"/"CST" in the survivor narrative and "Sharpe"/"tangency" as primary dropdown labels appear with no plain-language framing, even though the app has a working acronym-definition mechanism it simply doesn't route these through. **Payoff: novice users can read the two densest decision surfaces; ~10-minute fixes reusing existing infrastructure.** (documentation, high)

7. **The build success/summary logic is hand-duplicated across the sync route and the async job.** The success predicate is byte-identical in two places (`workbook_routes.py:324`, `build_job_service.py:366`) — a real drift hazard where "did the build succeed?" could diverge between the two paths. **Payoff: one source of truth for build success.** (architecture, medium)

8. **The engine already computes every input for gain-harvesting into the 0% capital-gains bracket but never does it.** Loss harvesting exists; the symmetric, standard low-bracket-retiree strategy of realizing gains tax-free does not, and it isn't coordinated against Roth conversions competing for the same bracket space. **Payoff: a standard strategy the tool currently leaves on the table for its target clientele.** (planner, high)

Cross-cutting theme: the two highest-leverage *structural* moves are (a) finishing the extract-and-dedupe pattern the codebase already uses (build-result interpretation, glossary source, service-extraction test boilerplate), and (b) rebalancing test effort from string-presence checks toward behavior. Neither requires re-architecting the engine.

---

## 2. Panel Findings by Discipline

### 2A. Architecture

#### A1. Retire dead re-export facades `spending_model_facade` / `transaction_processor_facade` — *impact: low, effort: S*
- **What:** `src/spending_model_facade.py:13` is nothing but `from .data_io import load_csv, parse_client, validate_projection, summarize_validation` plus a matching `__all__`. A repo-wide search finds `spending_model_facade` referenced only in `src/__init__.py` and `tests/test_phase_d_tier_3a_spending_facades.py`; same for `transaction_processor_facade`. `src/__init__.py:4-5` mentions both in the docstring but does **not** list them in `__all__` (`:9-14`). The only test (`tests/test_phase_d_tier_3a_spending_facades.py:10-29`) is self-referential — it asserts the shim re-exports correctly. No production module imports either facade.
- **Options:**
  1. **Delete both facades + the self-referential test** (`src/spending_model_facade.py`, `src/transaction_processor_facade.py`, `tests/test_phase_d_tier_3a_spending_facades.py`, the two docstring bullets). Tradeoff: removes ~4 files of pure indirection; small risk an out-of-tree packaging script imports the name (none found in src+tools+tests, but external scripts aren't in this repo).
  2. **Keep them and make them the enforced public API** — add to `__all__`, migrate internal callers through the facade. Tradeoff: builds an API boundary nobody asked for; churns many call sites.
  3. **Leave as-is.** Tradeoff: modules keep implying a facade layer that doesn't exist; the green self-test gives false confidence.
- **Recommendation:** Option 1 — delete. Leftover Phase-D scaffolding with no caller and a test that only proves the shim is a shim.

#### A2. Deduplicate build success/summary interpretation across sync route and async job — *impact: medium, effort: M*
- **What:** The synchronous build (`src/server/workbook_routes.py:298-343`) and the async progress job (`src/server_services/build_job_service.py:300-390`) independently reimplement the same post-build sequence: env stamping, loading `plan_summary.json`, computing `stale_summary` via `*_matches_build`, the `QC:\s*(\d+)\s*/\s*(\d+)\s+PASS` regex, and the success formula. The success predicate is **byte-identical**: `workbook_routes.py:324` and `build_job_service.py:366` both read `success = returncode == 0 and (bool(qc_match) or summary.get("qc_result")) and bool(summary) and not stale_summary`. `build_runner.py:8-10` explicitly notes the subprocess path stays inline at its two call sites. `src/server_services/build_service.py` already exists and holds preflight + summary-read helpers but not this interpretation logic.
- **Options:**
  1. **Extract `interpret_build_result(...) -> BuildResultSummary` into `build_service.py`**, called from both sites; fold in `_build_error_message`/`extract_build_failure_message`. Tradeoff: single source of truth; requires threading the same inputs through both callers and equivalence testing (golden/contract tests `test_136`/`test_138` cover the shapes).
  2. **Unify the two drivers entirely** — sync route calls the async machinery with a no-op progress callback. Tradeoff: maximally DRY but merges two different control-flow contracts (blocking+JSON vs fire-and-forget+registry); more invasive.
  3. **Extract just the QC regex + success formula into shared constants.** Tradeoff: cheapest, kills the likeliest drift, but leaves the summary-load/stale logic duplicated.
- **Recommendation:** Option 1 — least invasive move that removes the real hazard (two hand-maintained copies of the success predicate) and populates the service module clearly meant to own this.

#### A3. Split `data_io.parse_client()` — separate parsing from side-effecting configuration — *impact: medium, effort: L*
- **What:** `src/data_io.py` is 2679 lines. `parse_client` (~`:670`) does far more than parse: triggers the at-rest migration (`:684`), then mid-parse performs global side effects — `configure_api_keys` (`:721`), `configure_holdings_pricing` (`:732`), a pricing-freeze DB lookup via `config_backend`/`portfolio_analytics` with `set_frozen_prices` (`:738-748`), reads an env var to override pricing mode for CI determinism (`:731`), resolves filing-status law (`:754-761`), builds the members abstraction (`:767+`), and constructs five annuity income streams via an inline `load_stream` closure (`:1513-1545`). One function couples CSV→dict parsing with market-data provider configuration, DB access, and env-driven test hooks.
- **Options:**
  1. **Extract pricing/provider configuration out of `parse_client`** into a `configure_pricing_for_build(c, data)` step the orchestrator calls, leaving `parse_client` a pure data→dict transform. Tradeoff: makes parse pure and testable without touching market_data/DB globals; the few callers relying on parse doubling as pricing setup must call the new step explicitly.
  2. **Break `data_io.py` into a package** (`parse_household`, `parse_income_streams`, `parse_spending`, `pricing_config`) with `parse_client` a thin orchestrator. Tradeoff: best cohesion, per-parser unit isolation; larger refactor, shared `_v/_n/_y/_sv` helpers and the `c` accumulator must be threaded.
  3. **Extract only the `load_stream` closure** to a module function. Tradeoff: small safe win, clarifies annuitant coupling; leaves pricing side effects and module size unaddressed.
- **Recommendation:** Option 1 — the buried side effects (network config, DB freeze lookup, env override) are the most surprising thing in a "parse" function and the highest-value separation; Option 2 is a reasonable follow-on once parsing is side-effect-free.

*(Two further architecture findings — decomposing `planning_engines.py` and "finishing" the h_/w_ person-label migration — were **refuted** during cross-check. See Appendix.)*

---

### 2B. Usability

#### U1. Main 3-column grid overflows on common laptop widths — *impact: high, effort: S*
- **What:** `frontend/css/dashboard.css:3` — `main{...display:grid;grid-template-columns:310px minmax(700px,1fr) 370px;gap:18px}` with `@media(max-width:1180px){main{grid-template-columns:1fr}}`. Minimum required width = 44px padding + 310 nav + 370 help + 36 gaps + 700 content floor = **1460px**. Viewports 1180–1460px (covering 1280×800, 1366×768, 1440×900) render the 3-column grid but can't satisfy the floor, forcing horizontal overflow instead of the single-column fallback the CSS already defines.
- **Options:**
  1. **Shrink fixed/floor widths** (nav ~280, help ~320, content floor ~560-600). Tradeoff: cramps labels/help; doesn't fix mid-range 1300-1450px unless cut aggressively.
  2. **Raise the single-column breakpoint** to `max-width:1479px`. Tradeoff: pushes most 13-14" laptops into always-stacked, losing the persistent help panel earlier than necessary.
  3. **Auto-collapse the help column in the tight range** — reuse the existing `body.help-collapsed` mechanism (`dashboard.css:728-733`, already frees 370px+gap) via a resize listener between ~1180-1500px. Tradeoff: small JS change; behavior differs by width so needs a one-time tooltip/explanation.
- **Recommendation:** Option 3 — reuses a tested mechanism, fixes overflow without permanently narrowing wide screens, least CSS restructuring.

#### U2. Per-account/per-policy detail panels default-collapsed, hiding review-critical values — *impact: high, effort: M*
- **What:** `frontend/js/dashboard_decomp_estate_insurance.js`: `renderTrustAccountsTable` (`:121`) opens the outer section `<details open>` but per-trust panels (`:130`) are collapsed `<details>` showing only name + type-select. `renderAccountTitlingTable` (`:142`) is itself collapsed (inconsistent with the sibling Trusts section) and its per-account panels (`:149`) hide all beneficiary/titling values until expanded. `renderInsurancePolicyGroup` (`:325`) repeats it: each policy is collapsed, hiding face amount/premium/benefit behind one click each.
- **Options:**
  1. **Inline summary previews** — extend each `<summary>` with the 1-2 most-checked values. Tradeoff: longer summary lines needing truncation rules; doesn't reduce edit clicks.
  2. **Default-open when list is short** (`open` when count ≤ ~5). Tradeoff: larger households still hit click-per-item; doesn't scale.
  3. **Replace with a compact one-row-per-entity table**, reusing the `lot-table`/`people-table` pattern already built for Holdings (`dashboard.js:9437-9494`) and Household People (`dashboard.js:7080-7118`). Tradeoff: more rework than 1-2 (new table renderer for two sections).
- **Recommendation:** Option 3 — the app already has a proven glanceable table component for exactly this data shape; reusing it removes the click-to-see problem entirely and keeps the pattern consistent.

#### U3. Two-column field layout excludes currency fields and is width-capped — *impact: medium, effort: M*
- **What:** `frontend/css/dashboard.css:40-43` caps `.field-list` at `max-width:780px` (comment "U2": deliberately at most two ~360px tracks). `frontend/js/dashboard.js:5825-5830`: `paired = kind !== "currency" && !isDateField(r) && dependencyRank(r.label) > "01"` — every dollar field (the bulk of a retirement tool's data entry) is excluded from side-by-side and always renders full-width. On a 1920px window (content column ~1000px) the list still caps at 780px, leaving ~220px idle beside every currency field and forcing extra vertical scrolling.
- **Options:**
  1. **Raise the max-width ceiling only** (~1000px) so a third auto-fit track can appear for non-currency fields; leave the currency exclusion. Tradeoff: only helps pages with non-currency fields; dollar-heavy pages see little benefit.
  2. **Relax the currency exclusion** for unambiguous currency fields. Tradeoff: reopens exactly the mis-entry risk the U2 comment guards against; higher regression risk, case-by-case validation.
  3. **Shrink per-field vertical footprint** (tighter padding/line-height), keep currency single-column. Tradeoff: doesn't reclaim horizontal whitespace, only vertical density.
- **Recommendation:** Option 1 — lowest risk, only changes the CSS ceiling, leaves the deliberate mis-entry-risk logic untouched, directly targets the reviewed defect for fields that already qualify for pairing.

#### U4. Help copy names retired standalone pages — *impact: medium, effort: S*
- **What:** `frontend/js/dashboard.js:42, 51, 244` reference "the Roth Conversion page" and "the Asset Allocation page" as nav destinations. But `roth_conversion` (`:216`) and `allocation_assets` (`:226`) are `hidden: true` and redirected via `STEP_REDIRECTS` (`navigation.js:19-22`) into tabs of the unified "Distribution Strategy" step (`dashboard.js:173-179`). A user scanning the left nav for those titles won't find them.
- **Options:**
  1. **Update the copy** to "Distribution Strategy" (naming the tabs). Tradeoff: purely textual; drifts again on the next rename.
  2. **Make the reference a live link** — `onclick="setStep('distribution_strategy')"`, the pattern already at `dashboard.js:3010` (`setStep('household_people')`). Tradeoff: slightly more markup; stays correct even if the tab label changes.
  3. **Add old names as search aliases** in Field Finder. Tradeoff: mitigates confusion but the visible copy stays factually wrong.
- **Recommendation:** Option 2 — the codebase already has this live-link pattern; applying it fixes the wording and is resilient to future renames.

#### U5. Admin console duplicates the main app's design tokens — *impact: low, effort: S*
- **What:** `frontend/css/admin.css:1-2` defines its own `:root{--bg:#f6f5f0;--surface:#fff;...}` and `.btn/.card/.stepbtn/.badge` rules that are near-identical hand-copied duplicates of `frontend/css/dashboard.css:3`'s tokens and component rules — two separately maintained files.
- **Options:**
  1. **Extract a shared base stylesheet** imported by both `index.html` and `admin.html`; keep page-specific layout local. Tradeoff: one-time refactor; re-test both pages for silently-overridden rules.
  2. **Leave separate + add a drift check** asserting the two `:root` blocks match. Tradeoff: catches drift after the fact rather than preventing it.
- **Recommendation:** Option 1 if a broader front-end refactor is planned; otherwise Option 2 as a low-cost tripwire — this is a maintenance-consistency risk, not a currently-visible defect.

---

### 2C. Documentation / Content

#### D1. Survivor/estate "What the Model Heard" narrative uses undefined QSS/CST and bypasses the auto-glossary — *impact: high, effort: S*
- **What:** `frontend/js/dashboard.js:2620-2626` (`modelHeardHtml`): "The build used survivor/QSS, basis step-up, federal portability, and credit-shelter settings..." and "CST: ...". Neither QSS nor CST appears in `ACRONYMS`/`ACRONYM_DEFINITIONS` (`:467-566`) nor the workbook glossary (`src/reporting/sheets_qc_reference.py:149-172`). The auto-glossary helper `acronymDefinitionsHtml()` is used elsewhere (`:1112`, `:15324`) but `modelHeardHtml`'s output is inserted at `:2490` (`latestBuildImpactHtml`) without passing through it.
- **Options:**
  1. **Wire into the existing auto-glossary** — add QSS/CST to the definitions and route the output through `acronymDefinitionsHtml()`. Tradeoff: ~10-min mechanical fix; only helps if the reader notices the appended list.
  2. **Rewrite the sentence in place**, spelling terms out inline once. Tradeoff: reads correctly with no lookup; one-off local edit that could drift.
  3. **Both.** Tradeoff: most robust, marginal extra effort.
- **Recommendation:** Do the rewrite **and** register QSS/CST. Suggested wording: *"The build used the survivor's Qualifying Surviving Spouse (QSS) filing status, taxable-basis step-up at death, federal estate-tax portability, and Credit-Shelter Trust (CST) settings when calculating survivor cash flow and terminal estate values. The CST amount funded (or excluded, if disabled) by the last projection year is {amount}."* / detail: *"Basis step-up at death: {on/off} ({regime}); Credit-Shelter Trust (CST): {on/off}; federal estate-tax portability: {on/off}."*

#### D2. Asset-allocation mode picker uses "Sharpe"/"tangency" as primary labels with no plain-language framing — *impact: high, effort: S*
- **What:** `frontend/js/dashboard.js:5602-5603`: `{value:"max_sharpe", label:"Use max-Sharpe allocation (risk-budgeted)"}`, `{value:"tangency", label:"Use max-Sharpe allocation (pure tangency, no risk budget)"}` (duplicated at `:6067-6068`). The only in-app elaboration is jargon-on-jargon at `:15016`: "tangency is an unconstrained max-Sharpe reference". Neither term is in `ACRONYM_DEFINITIONS` (`:519-566`) nor the workbook glossary, unlike comparably technical terms the product *does* define well (FRA/PIA at `:563-564`).
- **Options:**
  1. **Reword the visible labels**, leading with the plain-language outcome, technical name parenthetical (the FRA/PIA pattern). Tradeoff: fixes the point of decision; doesn't cover future occurrences elsewhere.
  2. **Register the terms in the glossary system.** Tradeoff: reuses infrastructure, covers future occurrences; raw jargon still sits in the control, help panel is opt-in.
  3. **Inline caption under the select.** Tradeoff: most novice-friendly (unavoidable at decision time); costs space on a dense page.
- **Recommendation:** Reword the two labels now **and** add the terms to `ACRONYM_DEFINITIONS`/`TERM_NOTES`. Suggested: *"Best risk-adjusted mix within your risk limits (max-Sharpe, risk-budgeted)"* / *"Best risk-adjusted mix with no risk limits applied (max-Sharpe, pure tangency)"*.

#### D3. Two independently maintained glossaries diverge and leave ~10 on-screen terms undefined — *impact: medium, effort: M*
- **What:** `frontend/js/dashboard.js:519-566` defines ~47 terms in `ACRONYM_DEFINITIONS`, live-rendered. `src/reporting/sheets_qc_reference.py:149-172` defines a separate hand-written 22-term list baked into the workbook's "4G. Glossary". Both define IRMAA with different wording (`dashboard.js:525` vs `sheets_qc_reference.py:155`). Terms existing *only* in the workbook — "Spousal Rollover" (`:169`), "Credit-Shelter Trust" (`:152`), "Step-Up in Basis" (`:171`), "Sequence-of-Returns Risk" (`:168`), "SALT Cap" (`:166`), "Sec. 121 Exclusion" (`:167`) — are used in on-screen narrative (`dashboard.js:241, 807, 2612-2626`) with no front-end entry, so a user who never opens the workbook never sees them defined.
- **Options:**
  1. **Single shared glossary source** — one JSON/python source; workbook builder generates rows from it, front end fetches via API. Tradeoff: removes drift permanently, matches the codebase's consolidation precedent; touches both a Python module and the front-end fetch/render path.
  2. **Backfill the ~10 missing terms into `TERM_NOTES`** (which already supports multi-word phrases). Tradeoff: small immediate fix closing the actual coverage gap; the two lists stay independent and can still drift.
  3. **Leave as-is, periodic manual review.** Tradeoff: zero cost now; gap and drift persist.
- **Recommendation:** Backfill into `TERM_NOTES` now (low-cost, closes the immediate gap), then treat single-source consolidation as a follow-up consistent with the project's existing "move duplicated logic into one tested module" pattern.

#### D4. Long text in merged multi-column workbook cells loses wrap and span in the PDF — *impact: medium, effort: S*
- **What:** `src/reporting/workbook_common.py:109-120` `write_cell()` has no `wrap_text` parameter, so long narrative values default to `wrap_text=False`. `src/reporting/enterprise_pdf.py:275-276` only wraps a cell's text into a word-wrapping Paragraph `if cell.alignment and cell.alignment.wrap_text and text` — otherwise the raw string is placed directly. `enterprise_pdf.py` never reconstructs data-cell merges (the only `ws.merged_cells.ranges` read is the header-band check at `:246-249`), so a value merged across B:D (e.g. the Glossary Definition column, `sheets_qc_reference.py:174-182`, `merge_cells(start_column=2, end_column=4)`) is placed using only column B's width (`colWidths` at `:261-266`) and, with no Paragraph wrapper, won't wrap into that narrower space.
- **Options:**
  1. **Add a `wrap=False`-default parameter to `write_cell()`**, set `True` at merged/long-text call sites; `enterprise_pdf.py`'s existing wrap-detection then picks it up free. Tradeoff: minimal change reusing a correct PDF path; requires a visual re-check of the rendered PDF.
  2. **Reconstruct merged ranges in the PDF renderer** — teach `_band_table` to detect merged data-cell ranges and emit a SPAN with combined width, independent of `wrap_text`. Tradeoff: fixes the root cause for all current/future merges; more invasive to the banding logic.
  3. **Leave as-is** and treat the .xlsx as authoritative (as `dashboard.js:361` states). Tradeoff: zero cost, but the PDF is marketed in-app as an "advisor-ready formatted summary", so a clipped glossary entry undercuts that.
- **Recommendation:** Option 1 as the immediate fix (starting with the Glossary sheet); file Option 2 as a follow-up. Confirm by visually inspecting a rendered PDF Glossary page — this finding is from code inspection, not an observed render.

---

### 2D. Test Quality

#### Q1. Dozens of files assert literal source-code substrings and call it coverage — *impact: high, effort: L*
- **What:** `tests/test_141_workflow_journey_guards.py:19-60` is pure `assert ... in js/routes` string checks (no build, no DOM, no fetch). `tests/test_137_roadmap_usability_surfaces.py:6-60` and `tests/test_149_roadmap_steps_1_11_static.py:10-48` assert `"..." in js/html/css` with no render. `tests/test_93_architecture_completion_exhaustive.py` (named "exhaustive") is mostly `inspect.getsource(...)`/`read(rel)` substring checks. The `read_text(encoding="utf-8")` idiom matches **91 files**. *(Cross-check corrections applied: the self-aware "nothing here proves the real trigger path works" docstring belongs to `tests/test_161_phase2_workflow_route_plumbing.py`, not test_141; test_161 already demonstrates the recommended fix — honest docstring + tracked follow-up; test_93 is *mostly*, not entirely, substring checks — several of its tests execute real code paths.)*
- **Options:**
  1. **Status quo** — treat as a cheap trip-wire against accidental deletion. Tradeoff: actively misleading; names like `_journey_guards`/`exhaustive` claim coverage they don't provide.
  2. **Convert journey-named files to real behavior tests** using `app.test_client()`, following `test_e2e_build_journey.py` and `test_126_service_extraction.py`'s `test_stdlib_route_smoke_after_service_extraction`. Tradeoff: real cost, slower than a grep; pays off the first time a refactor silently breaks a flow.
  3. **Rename-or-delete static-string files** to say what they are (`_static_strings_test`) or delete once strings are stable. Tradeoff: loses a weak fence; CLAUDE.md's "grep before renaming" discipline is the real safety net.
- **Recommendation:** Both — apply the **test_161 pattern** (honest docstring + tracked gap, then convert to real `test_client()` behavior) to `test_141`, and rename or retire the pure string-check files (`test_137`, `test_149`, most of `test_93`) so their names stop overstating what they verify.

#### Q2. Test files organized by chronological roadmap item, not subsystem — *impact: high, effort: XL*
- **What:** Allocation behavior alone spans ≥13 files (`test_4`…`test_103_asset_allocation_lot_guidance.py`, 2-10 tests each). A separate "did we finish the roadmap" cluster of ~10 files (`test_29`, `test_92`, `test_93`, `test_137`, `test_149`, `test_150`, `test_160`, `test_full_checklist_completion.py`, `test_full_checklist_remaining.py`, `test_release_completion.py`) shares no other organizing principle.
- **Options:**
  1. **Status quo** — keep one-file-per-item as an audit trail. Tradeoff: nobody can answer "what tests allocation?" without grepping 13 files; new item-files re-assert prior strings, accreting duplicate coverage.
  2. **Consolidate by subsystem** (`test_allocation.py`, `test_completion_static_checks.py`), de-duplicating. Tradeoff: XL diff across ~190 files, touches nothing at runtime; big discoverability win.
  3. **Freeze in place, fix forward** — hard rule that new tests land in subsystem files, plus a CI check flagging new `test_<number>_*.py`. Tradeoff: doesn't fix existing scatter; stops it worsening at near-zero cost.
- **Recommendation:** Freeze-and-fix-forward now, paired with a scoped one-time consolidation of the two worst offenders observed (the allocation cluster and the roadmap/completion cluster), rather than a full-suite XL rewrite.

#### Q3. The largest, most user-facing file has behavioral coverage of ~nine pure helpers — *impact: high, effort: L*
- **What:** `frontend/js/dashboard.js` is 16,485 lines / 771 top-level function declarations. `tests/frontend/dashboard_pure_functions.test.mjs` (124 lines) covers exactly `esc, norm, titleWord, stripUiLabelPrefix, formatAcronyms, fmtMoney, fmtPct, finiteOrNull, firstFinite`. The other four `.mjs` files add more of the same category. Everything else claimed as dashboard.js "coverage" is the Q1 string-presence pattern. *(Cross-check corrections: the "first JS test coverage of any kind in this repo" comment is in `dashboard_pure_functions.test.mjs:1-11`, not `load_dashboard.mjs`. Critically, the four extracted `.mjs` modules are **not wired into the running app** — no `<script>`/import in `index.html`/`admin.html`, only their own test files load them. `frontend/js/modules/roth_ui.mjs`'s `isValidRothObjectiveMode()` validates modes ("BALANCED", "TAX_MINIMIZED", "LEGACY_TARGETED", "ROTH_FOCUSED") that do **not** match dashboard.js's real enum at `:5569-5576` ("BALANCED_RETIREMENT", "MINIMIZE_LIFETIME_TAX", "MAXIMIZE_TERMINAL_NET_WORTH", "LEGACY_OPTIMIZED", "ESTATE_TAX_AWARE", "CUSTOM_WEIGHTED"); `isValidIrmaaGuardrailMode()` likewise mismatches. That module tests a fictional parallel implementation. `admin_ui.mjs`'s `rowCell/isHeader` faithfully match live duplicates in `admin.js` but are copy-paste fork-risk.)*
- **Options:**
  1. **Status quo, incremental** — grow the pure-function list opportunistically. Tradeoff: coverage capped at whatever fraction is pure; the stateful 99% stays manual-QA-only.
  2. **Extract-then-test** — continue pulling logic into smaller modules with explicit I/O, then unit-test them. Tradeoff: moderate effort; **but the existing extracted modules must first be audited** (roth_ui.mjs deleted-or-corrected-and-rewired) rather than cited uncritically as a proven template.
  3. **Targeted DOM/interaction tests** (jsdom or Playwright component tests) for a short list of critical flows: step nav, unsaved-changes guard, build-progress overlay. Tradeoff: new dependency/category; the only way to verify stateful flows; scope must stay narrow.
- **Recommendation:** Extract-then-test as the primary strategy, **preceded by an audit of the four existing `.mjs` modules for orphaning/drift**, reserving targeted DOM tests for the 3-5 highest-risk interactive flows (nav switching, dirty-state guard, build progress) that extraction can't make pure.

#### Q4. The one true end-to-end test never exercises a user-edited input — *impact: medium, effort: M*
- **What:** `tests/test_e2e_build_journey.py:44-112` posts `/api/build/start` and polls to completion, but against whatever `input/client_data.csv` already contains — it never PUTs/POSTs a changed field through the real plan-data route first. So there is no HTTP-level proof that "a user changes an input → the built report reflects the new value" works; that check exists only at the direct-engine-call level (`test_2_recommendations.py`, `test_qcd_agi_exclusion.py`), bypassing the server/route layer.
- **Options:**
  1. **Status quo** — rely on golden-master + unit tests for sensitivity and `test_161` for wiring. Tradeoff: the gap the e2e docstring itself calls out is only half-closed.
  2. **Extend the existing e2e file** — save a plan-data change via the real route (e.g. a spending amount or retirement age), build, assert the new value appears in the xlsx-derived results. Tradeoff: small targeted addition reusing existing machinery; ~90s more in the slow tier.
  3. **Persona matrix** — 2-3 canonical households each run through the full HTTP path, marked slow. Tradeoff: much stronger coverage; more CI time and three golden outputs to maintain.
- **Recommendation:** Option 2 first (cheapest way to close the specific gap its own docstring identifies); persona matrix as a stretch goal.

#### Q5. Near-zero coverage for malformed input and mid-plan insolvency — *impact: high, effort: M*
- **What:** A repo-wide search found only isolated cases: `test_154:33-37` (one malformed-CSV-cell smoke test), `test_secrets_store_module.py:88-89` (corrupt JSON), `test_78_ytd_spending_growth.py:100` (one YTD rejection), and `test_198_unsupported_state_preflight.py` (the one well-built example — `ValueError` with actionable message at `:30-50`). No test asserts what happens when a deterministic projection's portfolio goes negative mid-plan (forced-sale, negative net worth, surfaced warning), nor for demographic nonsense (DOB after retirement date, negative ages/incomes).
- **Options:**
  1. **Status quo** — rely on Monte Carlo `success_rate` for depletion; assume no nonsensical input. Tradeoff: a deterministic line that goes silently wrong on bad input has no safety net; a correctness/trust risk.
  2. **Targeted boundary tests** following `test_198`'s pattern (readable `ValueError` with actionable message) for the highest-risk cases: DOB after retirement, negative/zero life expectancy, spending exceeding all assets by year 1. Tradeoff: modest effort, reuses an in-repo pattern, closes the highest-value gap.
  3. **Property-based fuzzing** (Hypothesis) generating plausible configs, asserting no uncaught crash/NaN. Tradeoff: broad long-term coverage; new dependency and tuning burden, larger than the immediate gap justifies.
- **Recommendation:** Option 2 first, modeled on `test_198`; consider fuzzing later once a baseline of explicit boundary cases exists.

#### Q6. Eight near-identical "service exists + routes delegate" test files duplicate what one AST check already generalizes — *impact: medium, effort: S*
- **What:** `tests/test_153_report_service_extraction.py:5-27` and `test_154_spending_service_extraction.py:4-28` follow an identical template (grep service file for function names + grep routes for delegation), repeated in `test_157`/`test_158`/`test_159`. Both explicitly comment (`test_154:12-13`, `test_153:11-12`) that HTTP-runtime-independence is "asserted once, for every service module, by the AST-based check in `test_126_service_extraction.py`" (`:22-35`) — confirming the authors know the generic mechanism supersedes the repeated checks, but the "exists"/"delegates" halves were never folded in.
- **Options:**
  1. **Status quo** — keep all eight as a regression fence. Tradeoff: real behavior tests stay valuable but are diluted among boilerplate that breaks on any rename for little marginal safety.
  2. **Generalize the AST check, delete the boilerplate halves** — parametrize `test_126` over service/route pairs to also verify "route business-logic functions absent" and "service public functions called from its route file", then delete the redundant pairs, keeping each file's real behavior test. Tradeoff: small well-scoped change removing ~16 brittle tests while strengthening the guarantee.
  3. **Merge all eight into one parametrized file.** Tradeoff: improves discoverability with less design work; doesn't reduce the redundant-assertion count as much.
- **Recommendation:** Option 2 — generalize `test_126` and delete the exists/delegates halves in `test_153/154/157/158/159`, keeping every genuine behavior test (history round-trip, validation-before-mutation, CSV robustness) intact.

#### Q7. The separately-built HTML dashboard has thin coverage vs the 27-34 sheet workbook it mirrors — *impact: medium, effort: M*
- **What:** `src/reporting/dashboard.py:377` defines `build_html_dashboard(xlsx_path, html_path, rows, c)`, a standalone HTML builder separate from the sheet builders, generated from the same `rows`/`c` through its own code path (not derived from the built xlsx). Only 3 test files reference it (`test_194`, `test_offline_html_dashboard_charts.py`, `test_102`) vs dozens covering the xlsx sheets. Any bug that makes the two outputs disagree on a number has almost no dedicated cross-check.
- **Options:**
  1. **Status quo** — assume the 3 files suffice. Tradeoff: the divergence risk stays structurally unverified.
  2. **Add a targeted xlsx/HTML parity test** (slow tier, reusing `built_workbook_dir`) asserting a handful of anchor figures (terminal net worth, first-year cash flow, lifetime tax) match between HTML and xlsx. Tradeoff: closes the specific risk with one scoped test; must pick stable anchors to avoid a second golden-master.
  3. **Architectural: single source of truth** — derive HTML figures from the built xlsx/results_model. Tradeoff: eliminates the risk at root; a `src/` change with its own regression risk, outside a test review's scope.
- **Recommendation:** Option 2 (cheap, test-only, closes the flagged risk); leave the architectural fix as a separately-scoped team decision.

#### Q8. A ~10-file roadmap-completion cluster provides little value per file — *impact: medium, effort: M*
- **What:** `test_29`, `test_92`, `test_93`, `test_137`, `test_149`, `test_150`, `test_160`, `test_full_checklist_completion.py`, `test_full_checklist_remaining.py`, `test_release_completion.py` share nothing beyond "prove a milestone shipped." Sampled files are dominated by the Q1 substring pattern (`test_149`'s own function names end in `_static`). But `test_29:24-41` mixes in genuinely valuable behavioral checks (Monte Carlo CI bounds, requirements.txt presence), so wholesale deletion would lose real signal.
- **Options:**
  1. **Delete wholesale.** Tradeoff: fastest; loses `test_29`'s real assertions unless migrated first.
  2. **Triage-then-delete** — migrate genuine behavioral assertions into the relevant subsystem file, then delete each file. Tradeoff: careful (one pass per file); loses zero real coverage.
  3. **Archive, don't delete** to a non-collected `tests/archive/`. Tradeoff: zero risk; leaves dead weight and doesn't force triage.
- **Recommendation:** Triage-then-delete — migrate the handful of genuine behavioral tests (at least `test_29`'s) into proper subsystem files, then delete the cluster, since the string-only checks provide negative value (false confidence).

---

### 2E. Financial Planning

#### P1. Roth-conversion IRMAA guardrail caps same-year MAGI but IRMAA is 2-year-lagged and Medicare-age-gated — over-restricts pre-65 gap-year conversions — *impact: high, effort: M*
- **What:** `plan_roth_conversion` applies the IRMAA cap whenever `roth_irmaa_cap` is on and guard mode isn't IGNORE/WARN_ONLY, with no age or lag gate: `src/planning_engines.py:1229-1235` caps the conversion so *this-year* `pre_agi` stays below `irmaa_thr`. But the assessment side correctly models the 2-year lookback and Medicare-age gate: `src/projection_stages/deterministic_engine.py:1645-1648` (`irmaa_lookback_magi(..., irmaa_lookback_years=2)` and `irmaa_yr = ... if n_medicare > 0 else 0.0`). A conversion at age 60-62 drives MAGI that would set IRMAA at 62-64 — all pre-65, zero surcharge — yet the guardrail still throttles it.
- **Scope (planner correction):** This over-restriction bites only **non-ACA-bridge, pre-Medicare clients** (retiree-medical/COBRA/self-pay). The engine already carries a tighter, correct pre-65 brake for ACA-bridge clients: the ACA premium-tax-credit MAGI guardrail at `planning_engines.py:1221-1228` (MAGI ≤ ~400% FPL), plus a scored ACA-PTC-loss penalty at `:1677-1706`. For any ACA-bridge client that guardrail binds *well before* the IRMAA cap, and the bracket cap frequently binds first regardless — the caps are min'd via `_ranked_caps`. So P1 unlocks room only for clients not on ACA coverage in the gap years. The age-63 gate logic itself is correct; the earlier "every pre-65 client" framing was an overstatement and has been narrowed.
- **Adjacent gap found while verifying P1 (planner):** the `fill_to_irmaa` Roth policy (`planning_engines.py:1205-1216`) caps conversions **only** to the IRMAA threshold — the ACA PTC guardrail added in the `fill_to_bracket` branch (`:1221-1228`) is **absent** here. An ACA-bridge client on the "fill to IRMAA" policy gets conversions sized into subsidy-destroying MAGI (IRMAA thresholds sit far above 400% FPL). This is a live, money-losing gap for the tool's gap-year clientele and sits inside the exact function P1 already opens. Fold adding the ACA guardrail to the `fill_to_irmaa` caps list into the P1 change.
- **Options:**
  1. **Age/lag-gate the guardrail** — apply the cap only in years whose MAGI actually determines a future surcharge, i.e. when the member is ≥ (65 − `irmaa_lookback_years`) = 63, and only against the filing status/thresholds in force 2 years later. Pass `h_age`/`w_age` (already arguments) into the cap decision. Tradeoff: small, well-scoped, unlocks legitimate gap-year room; must handle mixed-age couples and the year-of-death filing flip landing on the lagged MAGI.
  2. **Two-year forward-projected guardrail** — cap using projected MAGI in the year the surcharge bites, reusing `irmaa_lookback` symmetrically. Tradeoff: most accurate; needs forward-looking state inside the year loop (or a second pass), more invasive.
  3. **Expose `guard_mode` default + document conservatism**, default to WARN_ONLY before Medicare age. Tradeoff: cheapest; leaves an incorrect default that silently shrinks conversions for every pre-65 client.
- **Recommendation:** Option 1 — the minimal change removing a systematic downward bias on gap-year conversions while staying consistent with the already-correct assessment-side lag model.
- **Risk:** Changing conversion sizing shifts golden-master totals; regen baselines and add a test showing a pre-65 client's conversions are no longer IRMAA-capped.

#### P2. No zero-bracket gain harvesting; not coordinated with Roth conversions — *impact: high, effort: L*
- **What:** TLH is loss-only: `src/tlh.py:101-152` (`select_harvest_lots` keeps only lots where `loss = basis − mv > 0`) and the engine applies only loss harvesting (`deterministic_engine.py:1917-1944`). The 0% LTCG ceiling is known to both engine (`_ltcg_tax_on_gain_path`, `deterministic_engine.py:389-401`, `top0 = ltcg_0_top`) and ledger (`_ltcg_marginal_rate`, `tlh.py:159-173`), yet no strategy realizes long-term gains up to `ltcg_0_top` to reset basis tax-free. Roth conversions consume the same ordinary-income headroom (`planning_engines.py:1145-1153`) with no cross-strategy tradeoff surfaced.
- **Options:**
  1. **Add a 0%-bracket gain-harvest strategy + sheet**, mirroring the TLH sheet: per year compute `headroom = ltcg_0_top*bracket_factor − (ordinary_income after deductions)`, recommend realizing appreciated long-term lots up to headroom (tax-free basis reset). Tradeoff: high value, symmetric with existing TLH machinery; competes with Roth conversions for the same low-income years — needs a clear ranking rule.
  2. **Coordinate conversions + gain-harvesting in one low-income-year optimizer** — extend the Roth optimizer to jointly allocate each gap year's bracket space, scored on the existing lifetime-tax + terminal-NW objective. Tradeoff: correct and defensible; most engineering; the objective must weigh tax-free basis step-up against tax-free Roth growth.
  3. **Diagnostic-only flag** — report unused 0% LTCG headroom per year without prescribing lots. Tradeoff: low effort, surfaces the opportunity; leaves sizing/execution manual.
- **Recommendation:** Start with Option 1 as a standalone sheet reusing the TLH ledger pattern, then fold into Option 2's joint optimizer. A standard low-bracket-retiree strategy the tool ignores despite computing every input.
- **Risk:** Must respect the **long-term holding-period test** already in `holding_period.py` and avoid double-counting headroom the Roth optimizer assumes. (Planner correction: **wash-sale rules do not apply to gain harvesting** — the wash-sale rule disallows *losses*, not gains, so a realized gain can be repurchased the same second. Do **not** impose a 30-day rebuy gap on the gain-harvest path; that would create needless out-of-market risk. Wash-sale handling belongs only where loss harvesting coexists.)

#### P3. SS timing score double-counts benefits and ignores longevity — *impact: high, effort: M*
- **What:** `src/reporting/sheets_strategy.py:187` sets `score = terminal + lifetime_ss − lifetime_tax − irmaa`, and `:216-220` ranks all 81 spouse-age pairs by it to pick the headline recommendation. But `terminal_nw` already reflects SS (higher SS → lower withdrawals → higher terminal NW), so adding `lifetime_ss` (an undiscounted flow summed at `:181`) rewards gross SS dollars a second time, biasing toward whichever pair maximizes total benefits received. The genuine case for delay — longevity/survivor insurance — is explicitly excluded: `:188-192` state the Monte Carlo success-rate and P10 columns are informational and do NOT feed the score. *(Cross-check refinement: the redundancy isn't a literal 1:1 duplication — the terminal channel amplifies extra SS/tax dollars via compounding while the raw terms are undiscounted sums — and the same redundant-term problem symmetrically double-penalizes `lifetime_tax` and `irmaa`, so the bias is if anything worse than the title implies, not overstated.)*
- **Options:**
  1. **Score on after-tax terminal wealth alone (or survivor-weighted)** — drop the additive `lifetime_ss` term; rank on after-tax terminal NW (the sheet already imports `estimate_after_tax_terminal_net_worth`), optionally weighting by the survivor years already computed (`:183`). Tradeoff: removes the double-count with a small change, keeps the deterministic ranking; still understates pure longevity risk unless survivor-weighted.
  2. **Rank on a longevity-probability-weighted objective** — expected value across mortality percentiles (the MC machinery is already invoked per pair at `:195-201`), crediting delay for protecting late-life/survivor cash flow. Tradeoff: what a planner actually defends; makes the recommendation stochastic and slower.
  3. **Show both, recommend neither mechanically** — present deterministic ranking + MC metrics side by side, label the recommendation as deterministic-mortality. Tradeoff: honest, low-effort; a tool that sweeps 81 pairs and prints a "Recommended Claim Age" will be read as advice, so leaving a double-counted score behind that label is worse than fixing it.
- **Recommendation (revised per planner — highest priority):** The de-double-count and the longevity/survivor weighting **must ship together in one change (T4b)** — never de-double-count first. Survivor/longevity weighting is **mandatory, not optional**. Critical direction note: because `lifetime_ss` is an *undiscounted* sum of benefits received, the current bug **rewards delay** (more lifetime SS collected out to the deterministic mortality age) — the generally-correct planning direction, for the wrong reason. Removing that term *without* mandatory survivor/longevity weighting removes the pro-delay thumb and shifts the headline **toward early claiming** under the plan's single fixed mortality assumption — reintroducing the exact self-contradiction P4 condemns: a prescriptive "Recommended Claim Age" sitting beside the MC longevity/P10 columns it contradicts. Ranking a Social Security claim on terminal net worth at one assumed death age is backwards from the actual reason to delay (longevity/survivor insurance). So: either make survivor/longevity weighting mandatory in the same change, **or hold the single "Recommended Claim Age" headline entirely** until the longevity-probability-weighted Option 2 exists, and in the interim present the 81-pair *ranking* with longevity columns rather than one prescriptive age.
- **Risk:** A terminal-NW-only ranking (i.e. shipping Option 1 *without* the mandatory survivor weighting) favors early claiming for short assumed lifespans — the wrong direction. This is why survivor/longevity weighting is not optional and must land in the same change; do not ship a bare de-double-count.

#### P4. Federal-estate section prints a hardcoded "no federal tax likely" note even with a computed positive tax — *impact: medium, effort: S*
- **What:** `src/reporting/sheets_strategy.py:1099-1111` computes `est2 = yr_second['total_nw']` and `fed_estate_tax = max(0, est2 − fed_exempt) * 0.40`, writing that figure. Line `:1112` then *unconditionally* writes "Estate well below $30M exemption — no federal tax likely" regardless of `est2`. An estate above the exemption shows a positive "Est. Federal Estate Tax" cell contradicted by a note asserting no tax is likely. The flat 0.40 rate at `:1100` also ignores the graduated schedule and any state-death-tax deduction. *(Re-verified at lines 1100 and 1112 while writing this report.)*
- **Options:**
  1. **Make the note conditional on `fed_estate_tax > 0`** — a taxable-estate warning with the computed liability and planning actions (ILIT, gifting, portability election) when positive; the "below exemption" note only when zero. Tradeoff: trivial fix that restores credibility for the high-net-worth clients this section serves.
  2. **Conditional note + graduated-rate calc + annual exemption indexing** — replace flat 40% with the graduated schedule and index the exemption forward. Tradeoff: marginally more precise for taxable estates. **Do NOT model a 2026 exemption sunset** (planner correction below).
  3. **Suppress the static note entirely.** Tradeoff: fastest; loses reassurance that is genuinely correct for sub-exemption estates.
- **Recommendation:** Option 1 now (conditional note) — this is the clear trust fix and should ship immediately. **Planner correction — the sunset modeling is struck:** the code already labels the field `'Federal Exemption (MFJ, OBBBA)'` (`sheets_strategy.py:1101`, verified) and uses the ~$30M couple figure, i.e. it already reflects the **post-OBBBA permanent ~$15M-indexed exemption**, under which the scheduled TCJA sunset does not occur. Recommending a sunset model would inject a repealed assumption and mislead the reader toward "use-it-or-lose-it" gifting urgency that no longer exists. Reframe Option 2 as "graduated-rate schedule + annual exemption **indexing**" only. Note that at these estate sizes the flat 40% is a fine approximation (the graduated schedule is 40% marginal above ~$1M of taxable transfer), so Option 2 is **low-value polish, not a correctness fix** — reprioritize accordingly (Option 1 is the only estate item worth scheduling with urgency).
- **Risk:** Low; guard against portability/DSUE double-counting if the surviving-spouse exemption transfer is added later.

#### P5. State residency analysis: limited hardcoded states, flat proxies, mislabeled baseline — *impact: medium, effort: M*
- **What:** `src/reporting/sheets_strategy.py:872-916` iterates only `STATE_TAX_RULES` (`supported_states()`), estimates comparison-state estate tax as a flat `excess * 0.08` (`:902`), property tax as `home_val * prop_rate`, sales tax as `spend_base * 0.4 * sales_rate` (`:894-895, :867`). The "Delta vs IL" baseline is set by `if il_total is None: il_total = total` (`:904-905`) *during the unsorted loop*, so it captures the first state iterated, not necessarily Illinois. The unmodeled-state guard (`:816-826`) confirms non-modeled states fall back to Illinois numbers.
- **Options:**
  1. **Expand modeled states to common relocation targets + fix the baseline** — anchor `il_total` explicitly to the base state, and add income-tax-free targets (FL, TX, TN, NV, SD, WY, AZ) to `reference_data/state_tax.csv`. **Planner correction — do NOT group Washington with the flat-proxy income-tax-free tier.** WA levies a **state estate tax** with a low (~$2–3M) exemption and top rates well above 20% — for this section's high-net-worth audience that estate tax is often the *dominant* relocation cost, dwarfing the income-tax saving the section highlights. Applying the flat `excess * 0.08` estate proxy to WA would badly understate the cost and could recommend an estate-tax-adverse move. Before adding any state, verify its **estate/inheritance regime**, not just its retirement-income treatment. Flag WA (and, if added later, OR/MN/MA) as estate-tax states requiring real modeling, or exclude them from the flat-proxy tier. Tradeoff: answers the relocation question for the no-estate-tax havens directly; flat proxies remain approximate and are invalid for estate-tax states.
  2. **Model per-state retirement-income treatment and estate tax properly** (SS/pension/IRA exemption rules, actual estate/inheritance structure) instead of flat 0.08. Tradeoff: materially more accurate for estate-taxing states; large per-state data + testing commitment.
  3. **Reframe as illustrative, label proxies, fix only the baseline.** Tradeoff: low effort and honest; leaves the tool unable to answer the concrete "should we move to Florida" question.
- **Recommendation:** Option 1 — broaden coverage to the states clients actually relocate to and correct the `il_total` baseline; the retirement-income exemption logic already exists for Illinois, so extending the table is highest-leverage, with per-state estate detail (Option 2) as a follow-up.
- **Risk:** Verify each added state's retirement-income exemption **and estate/inheritance regime** before shipping; a wrong exemption flag or an unmodeled state estate tax (WA especially) directly misstates a relocation recommendation. The `il_total` baseline fix is independent of the state-list question and should proceed regardless.

---

## 3. Cross-Cutting Analysis

### Where the experts agree
- **The codebase's own "extract duplicated logic into one tested module" pattern is the answer in three places at once:** build-result interpretation (A2), the dual glossary (D3), and the service-extraction test boilerplate (Q6). All three are the same move — collapse two hand-maintained copies into one source. Doing them together reinforces a single house habit rather than three ad-hoc fixes.
- **String-presence tests are a recurring liability** (Q1, Q2, Q8) and they specifically undermine the architect's and everyone's ability to refactor safely — the very renames A1/A2/D3 recommend are exactly what brittle substring tests punish. Test-shape reform is a *prerequisite enabler*, not an independent nicety.
- **User-facing correctness and credibility cluster on the estate/tax/relocation surfaces** (P3, P4, P5, D1, D3) — the planner and documentation reviewers independently flag the same sections. These are the screens high-value clients scrutinize, and they currently contain a self-contradiction (P4), a mislabeled baseline (P5), and undefined jargon (D1/D3).

### Where the experts conflict — named and resolved

**Conflict 1 — Test string-checks: "delete/rename" (Q1, Q8) vs the architect's implicit reliance on them.** The architect's A1 delete recommendation notes "grep of src+tools+tests shows no caller"; the quality reviewer wants to delete the very grep-style tests that would notice such a deletion. Are these tests worthless or a safety net?
**Resolution:** They are a *weak* net that overstates itself, and CLAUDE.md already documents a manual "grep tests/ before renaming" discipline that is the real safety net. Keep the discipline, retire the misleadingly-named files. There is no genuine conflict once you separate "a trip-wire against accidental code deletion" (worth keeping, honestly named) from "coverage of a user journey" (which these files falsely claim). Resolution: rename/retire per Q1, but do it *after* the behavioral e2e (Q4) and boundary tests (Q5) land, so the net is stronger before the weak strands are cut.

**Conflict 2 — Layout: "shrink widths" (U1 opt 1) vs "raise breakpoint" (U1 opt 2) vs U3's desire to *widen* content to ~1000px.** U1 opt 1 argues for a *narrower* content floor to fit; U3 argues the content column is *too narrow* on wide screens. Pulling in opposite directions?
**Resolution:** No real conflict — they operate in different viewport regimes. U1 is about the 1180-1460px overflow zone; U3 is about ≥1760px wide screens. The reconciling choice is U1 Option 3 (auto-collapse help in the tight zone, leaving the 3-column layout intact for genuinely wide screens) plus U3 Option 1 (raise the `.field-list` ceiling for wide screens). Together they make narrow screens stack cleanly and wide screens use their width — no contradiction.

**Conflict 3 — "Extract-then-test dashboard.js" (Q3) rests on a premise the cross-check demolished.** Q3's recommendation calls extraction a "proven pattern in-repo," but verification showed the four extracted `.mjs` modules are orphaned (not loaded by the app) and one (`roth_ui.mjs`) tests invented enum values that don't match the live code. So the recommended strategy's own evidence is unsound.
**Resolution:** Keep extract-then-test as the *direction* but insert a mandatory precondition: audit and fix (or delete) the existing four modules first. An extraction strategy that produces orphaned, drifting parallel implementations is worse than no extraction — it manufactures false confidence exactly like the string tests. This makes Q3 depend on a small cleanup (delete/rewire `roth_ui.mjs`) before any new extraction.

### The one change that unlocks several others
**Rebalancing the test suite toward behavior (Q1/Q4/Q5, gated by the Q3 module audit) is the keystone.** Every architecture and content refactor in this report (A1 delete, A2 extract, A3 split, D3 glossary consolidation, and every planner code change P1-P5 that "shifts golden-master totals") is safer and cheaper once real behavioral tests exist and brittle string tests stop blocking renames. Concretely: P1 and P2 both explicitly warn they change projection totals and need regenerated baselines plus a new behavioral test — that test infrastructure is the same investment Q4/Q5 propose. Build the behavioral net first; it pays for itself across at least eight downstream items.

---

## 4. Recommendation — The Proposed Plan

I propose a **four-track program**, sequenced so the test-behavior net is in place before the higher-risk engine changes, and so the cheap high-credibility fixes ship immediately.

**Track 1 — Ship-now credibility fixes (all S, low risk, parallelizable).** P4 (conditional estate note), P5 baseline fix, D1 (QSS/CST rewrite + register), D2 (Sharpe/tangency relabel + register), D3 backfill, U4 (live-link help), U1 (auto-collapse help). These are visible defects on the screens clients scrutinize, each self-contained, none touching the projection engine.

**Track 2 — Test-behavior net (the keystone).** Audit the four `.mjs` modules and delete/rewire `roth_ui.mjs` (Q3 precondition); extend the e2e file with an input-edit scenario (Q4); add the `test_198`-pattern boundary/insolvency file (Q5). This unblocks Tracks 3-4.

**Track 3 — Structural dedupe (the house pattern).** A2 (`interpret_build_result`), Q6 (generalize `test_126`, delete boilerplate halves), D3 single-source consolidation (follow-up to the Track 1 backfill), A1 (delete dead facades). Depends on Track 2 for safe renames.

**Track 4 — Engine correctness (highest value, highest risk).** P1 (IRMAA guardrail age/lag gate — scoped to non-ACA-bridge clients, and preserving the ACA PTC guardrail plus adding it to the `fill_to_irmaa` policy) and P3 first, as scoped fixes with clear tests. **P3 must de-double-count and add mandatory survivor/longevity weighting in the same change (T4b) — never ship a bare de-double-count, which biases the headline toward early claiming.** P2 (0%-bracket gain harvesting) as a larger new capability. All require Track 2's behavioral tests and golden-master regeneration.

### What I am deliberately NOT doing, and why
- **Not decomposing `planning_engines.py`** (refuted — documented circular-import risk between the MC, mortality, and projection sections; a prior Phase-2c investigation tried and broke the engine at import time). See Appendix.
- **Not renaming the internal h_/w_ engine contract** (refuted — this is the engine's computational contract, not backward-compat scaffolding; the project explicitly reviewed and declined it in Wave 2). See Appendix.
- **Not doing the XL full-suite test reorganization (Q2 Option 2)** — freeze-and-fix-forward plus consolidating only the two observed-duplication clusters captures most of the value at a fraction of the risk.
- **Not merging the two build drivers (A2 Option 2)** — extracting the shared predicate removes the actual hazard without regressing two deliberately different control-flow contracts.
- **Not building the joint Roth/gain-harvest optimizer (P2 Option 2) up front** — ship the standalone gain-harvest sheet first; the joint optimizer is a follow-on once the standalone strategy is validated.
- **Not the state-by-state estate-tax model (P5 Option 2) now** — expand the state table and fix the baseline first; deep per-state modeling is a later commitment.

---

## 5. Design — Target State for Each Accepted Recommendation

### 5A. Architecture

**A1 — Delete dead facades.** Target: `src/spending_model_facade.py`, `src/transaction_processor_facade.py`, and `tests/test_phase_d_tier_3a_spending_facades.py` removed; the two docstring bullets dropped from `src/__init__.py`. Callers already import `data_io`/`spending_tracker` directly, so no call-site changes.

**A2 — `interpret_build_result()` in `build_service.py`.** New function `interpret_build_result(*, returncode, stdout, summary_path, build_id) -> BuildResultSummary` (dataclass fields: `success: bool`, `qc_result`, `stale_summary: bool`, `error_message`). It owns: env stamping inputs, `plan_summary.json` load, `stale_summary` via `*_matches_build`, the QC regex, the success formula, and folds in `_build_error_message`/`extract_build_failure_message`. `workbook_routes.py:298-343` and `build_job_service.py:300-390` each replace their inline block with one call. Module responsibilities after: `build_service.py` = preflight + summary-read + *result interpretation* (its intended purpose); the two callers = orchestration only.

**A3 — Extract pricing config from `parse_client` (phase 1 only).** New `configure_pricing_for_build(c, data)` owning `configure_api_keys`, `configure_holdings_pricing`, the freeze-DB lookup + `set_frozen_prices`, and the env override. `parse_client` becomes a pure data→dict transform; the build orchestrator calls the new step explicitly after parse. The full package split (Option 2) is explicitly deferred.

### 5B. Usability

**U1 — Auto-collapse help.** A resize listener toggles the existing `body.help-collapsed` class when `1180 < innerWidth < 1500`, restoring it above 1500 unless the user manually collapsed. First auto-collapse shows a one-time dismissible tooltip explaining why the help moved. No grid-template changes.

**U2 — Compact entity tables (if accepted; not in the proposed first tracks).** Replace the `<details>`-per-item structure in `renderAccountTitlingTable` and `renderInsurancePolicyGroup` with the `lot-table`/`people-table` renderer: one row per account/policy, columns = the 3-4 most-referenced fields (titling: primary/contingent beneficiary; policy: face amount, premium, benefit), a secondary expander for the long tail.

**U3 — Field-list ceiling.** Raise `.field-list{max-width:780px}` toward the real content-column width (~1000px) so non-currency fields can form a third auto-fit track. The `kind !== "currency"` mis-entry-risk exclusion in `fieldHtml()` stays untouched.

**U4 — Live-link help.** The three strings at `dashboard.js:42, 51, 244` become inline `onclick="setStep('distribution_strategy')"` links naming the Roth Conversion / Asset allocation & location tabs, matching the `:3010` pattern.

### 5C. Documentation / Content

- **D1:** Reword `modelHeardHtml` (`:2620-2626`) to the spelled-out sentence in §2C-D1, and add `QSS` / `CST` to `ACRONYM_DEFINITIONS`; route `modelHeardHtml`'s output through `acronymDefinitionsHtml()` for defense in depth.
- **D2:** Replace the two labels (`:5602-5603` and the `:6067-6068` duplicate) with the plain-language-first wording in §2C-D2; add "Sharpe ratio" and "tangency portfolio" to `ACRONYM_DEFINITIONS`/`TERM_NOTES`.
- **D3:** Immediate — add the ~10 workbook-only terms (Spousal Rollover, Credit-Shelter Trust, Step-Up in Basis, Sequence-of-Returns Risk, SALT Cap, Sec. 121 Exclusion, etc.) to `TERM_NOTES`. Follow-up — a single glossary data source that the workbook builder and (via API) the front end both consume; reconcile the two IRMAA definitions.
- **D4:** Add `wrap=False` to `write_cell()`; set `True` on the Glossary Definition column and similarly-merged narrative cells. Verify against a rendered PDF Glossary page. Follow-up: merged-range reconstruction in `enterprise_pdf._band_table`.

### 5D. Test-pyramid target shape

Today: a wide, shallow base of string-presence "unit" tests, a strong middle of engine/tax closed-form tests, one true e2e. Target:
- **Base:** genuine pure-function/unit tests (JS helpers via non-orphaned modules; Python engine helpers). Brittle string-presence files renamed to `_static_strings_test` or retired.
- **Middle (unchanged strength):** IRS-anchored closed-form tax tests; the three-tier golden-master; behavioral tax-strategy tests. Add the `test_198`-pattern boundary/insolvency file here.
- **Top:** the e2e journey extended to include an input-edit-through-the-route scenario (Q4); one xlsx/HTML parity test (Q7).
- **Structural guard:** `test_126`'s AST check generalized to subsume the per-file exists/delegates halves (Q6).

### 5E. New planning capabilities and what they must compute

- **P1 (guardrail gate):** The cap decision must consult member age and apply only when age ≥ `65 − irmaa_lookback_years` (=63), against the filing status/thresholds in force at the surcharge year (2 years hence), handling mixed-age couples and the year-of-death filing flip. **The ACA PTC guardrail (`planning_engines.py:1221-1228`) must remain intact** as the operative pre-65 constraint — it is a separate entry in `_ranked_caps`, so gating/removing the IRMAA cap will not touch it, but the design must say so explicitly so an implementer does not "simplify" both away. **Also add the ACA PTC guardrail to the `fill_to_irmaa` policy caps list (`:1205-1216`)**, which currently lacks it. Output: conversions in ages ≤62 are no longer IRMAA-capped for non-ACA-bridge clients; ACA-bridge clients on any policy stay MAGI-guardrailed.
- **P2 (0%-bracket gain harvesting):** Per projection year compute `headroom = ltcg_0_top * bracket_factor − (ordinary_income after deductions)`; select appreciated long-term lots up to headroom (respecting the **long-term holding-period test** in `holding_period.py` — **not** wash-sale rules, which apply only to losses); realize them tax-free, reset basis; report on a new sheet mirroring the TLH sheet (lots sold, gain realized at 0%, lifetime basis voluntarily stepped up). Must not double-count headroom the Roth optimizer assumes.
- **P3 (SS score):** Replace `score = terminal + lifetime_ss − lifetime_tax − irmaa` with after-tax terminal NW (via `estimate_after_tax_terminal_net_worth`), **mandatorily** weighted by the already-computed survivor years (longevity/survivor weighting is not optional); keep the MC longevity columns and surface them prominently near the recommendation. The de-double-count and the survivor weighting land in the **same change** — a bare de-double-count would bias the headline toward early claiming under the fixed mortality assumption. If mandatory survivor weighting cannot ship in this change, hold the single "Recommended Claim Age" headline and present the ranked 81-pair table with longevity columns instead. Output: the 81-pair ranking no longer double-counts SS/tax/IRMAA and is not read as advice to claim early.
- **P4 (estate note):** Branch on `fed_estate_tax > 0` — taxable-estate warning with the computed liability + actions when positive; the "below exemption" note only when zero.
- **P5 (state table):** Add FL/TX/TN/NV/SD/WY/AZ (verified retirement-income exemptions) to `reference_data/state_tax.csv`; anchor `il_total` explicitly to the base state instead of first-iterated. **Do not add WA to the flat `excess * 0.08` proxy tier** — it has a state estate tax (~$2–3M exemption, >20% top rate) that the flat proxy badly understates; add WA (and OR/MN/MA) only with real per-state estate modeling, or exclude them. Verify each state's estate/inheritance regime, not just retirement-income treatment, before adding.

---

## 6. Implementation Plan

Effort key: S ≤ half-day, M ≈ 1-2 days, L ≈ 3-5 days, XL > 1 week. "Proves it worked" is the concrete verification.

| ID | Item | Prereqs | Effort | Risk | Proves it worked | Parallel with siblings? |
|----|------|---------|--------|------|------------------|-------------------------|
| T1a | P4 conditional estate note | — | S | Low | New unit test: estate above exemption shows warning, not "no tax likely" | Yes |
| T1b | P5 baseline fix + state-table expansion (no-estate-tax states only; verify estate regime) | — | M | Low-Med | Test: "Delta vs IL" baseline == base state; added states appear with correct exemption flags; WA/OR/MN/MA excluded from flat-proxy tier | Yes |
| T1c | D1 QSS/CST rewrite + register | — | S | Low | JS test: rendered narrative contains spelled-out terms; definitions present | Yes |
| T1d | D2 Sharpe/tangency relabel + register | — | S | Low | JS test: label strings updated in both locations; terms defined | Yes |
| T1e | D3 backfill missing terms into TERM_NOTES | — | S | Low | JS test: each of the ~10 terms resolves via `acronymDefinitionsHtml()` | Yes |
| T1f | U4 live-link help | — | S | Low | Clicking the help link navigates to `distribution_strategy` | Yes |
| T1g | U1 auto-collapse help | — | S | Low | Manual/resize test at 1366×768: no horizontal overflow; help collapses | Yes |
| T1h | U3 field-list ceiling raise | — | S | Low | Visual: non-currency fields form 3 tracks at ≥1760px; currency stays single | Yes |
| T2a | Q3 audit 4 `.mjs` modules; delete/rewire `roth_ui.mjs` | — | M | Med | roth_ui enum matches `dashboard.js:5569-5576`, or module removed; modules loaded or gone | Partly (with T2b) |
| T2b | Q4 extend e2e with input-edit scenario | — | M | Low | e2e edits a field via the real route, builds, asserts changed value in xlsx | Yes |
| T2c | Q5 boundary/insolvency test file (test_198 pattern) | — | M | Low | Tests: DOB-after-retirement, spending>assets-yr1, negative age → actionable `ValueError` | Yes |
| T3a | A2 extract `interpret_build_result` | T2b | M | Med | `test_136`/`test_138` green; both build paths call one helper; success predicate exists once | Yes |
| T3b | Q6 generalize `test_126`, delete boilerplate halves | T2a-c | S | Low | Generalized AST check green; ~16 redundant tests removed; behavior tests retained | Yes |
| T3c | A1 delete dead facades | T3b | S | Low | Suite green after removing facades + self-test; no import errors | Yes |
| T3d | Q1/Q8/Q2 rename-retire string files; freeze-forward CI check | T2a-c | M | Low | Named files renamed/retired; CI flags new `test_<n>_*.py`; suite green | Yes |
| T3e | D3 single glossary source (follow-up) | T1e | M | Med | Workbook + front end render from one source; IRMAA wording reconciled | Yes |
| T4a | P1 IRMAA guardrail age/lag gate (non-ACA scope; keep ACA guardrail + add it to `fill_to_irmaa`) | T2b, T2c | M | Med-High | Test: non-ACA pre-65 gap-year conversions no longer capped; ACA-bridge client stays MAGI-guardrailed on both policies; golden-master regenerated | Yes (with T4b) |
| T4b | P3 SS score de-double-count **+ mandatory survivor/longevity weighting (one change)** | T2b | M | Med | Test: ranking on survivor-weighted after-tax terminal NW; `lifetime_ss` term gone; headline not biased earlier; longevity context surfaced | Yes (with T4a) |
| T4c | P2 0%-bracket gain-harvest sheet | T2b, T2c | L | Med-High | Test: gains realized up to headroom at 0%; long-term holding-period respected (no wash-sale gap on gains); new sheet renders; golden-master regenerated | No (touches same engine bracket space as T4a) |
| T5a | A3 extract `configure_pricing_for_build` | T2b | L | Med | `parse_client` pure (no network/DB in parse path); pricing configured via new step; golden-master green | Yes |
| T5b | Q7 xlsx/HTML parity test | T2b | M | Low | Test: anchor figures (terminal NW, yr-1 cash flow, lifetime tax) match between HTML and xlsx | Yes |
| T5c | U2 compact entity tables | T1g | M | Med | Titling/policy values visible without per-item clicks; matches Holdings table pattern | Yes |
| T5d | D4 PDF wrap flag | — | S | Low | Rendered PDF Glossary page: Definition column wraps within its merged span | Yes |

### Dependency-ordered waves

**Wave 1 — Ship-now credibility + test net (all concurrent).**
- Concurrent: T1a, T1b, T1c, T1d, T1e, T1f, T1g, T1h (independent screen/content fixes) and T2a, T2b, T2c (test net).
- Minimal effective model per item:
  - T1a **haiku** — single conditional branch + one test.
  - T1b **sonnet** — data-file expansion needs per-state exemption verification (judgment).
  - T1c **haiku** — mechanical rewrite + dictionary entries.
  - T1d **haiku** — two label strings + dictionary entries.
  - T1e **haiku** — append ~10 dictionary entries.
  - T1f **haiku** — apply an existing link pattern to three strings.
  - T1g **sonnet** — resize-listener logic + one-time tooltip UX decision.
  - T1h **haiku** — one CSS value change.
  - T2a **sonnet** — enum reconciliation and rewire/delete decision requires reading live code carefully.
  - T2b **sonnet** — new e2e scenario threading a real route edit.
  - T2c **sonnet** — designing meaningful boundary cases and expected error messages.

**Wave 2 — Structural dedupe (depends on Wave-1 test net).**
- Concurrent: T3a, T3b, T3d, T3e; then T3c after T3b.
- Minimal effective model:
  - T3a **sonnet** — extraction with careful behavior-equivalence across two callers.
  - T3b **sonnet** — generalizing an AST check without losing intent.
  - T3c **haiku** — file deletion + docstring edit once the net exists.
  - T3d **sonnet** — triage which files hold real assertions before renaming/retiring.
  - T3e **opus** — cross-layer single-source design (Python builder + front-end fetch contract).

**Wave 3 — Engine correctness + deeper refactors (depends on Wave-2 dedupe and Wave-1 net).**
- Concurrent: T4a + T4b (different scoring/guardrail surfaces), T5a, T5b, T5c, T5d. **T4c runs alone** relative to T4a — both allocate the same low-income-year bracket space, so serialize T4c after T4a to avoid double-counting headroom.
- Minimal effective model:
  - T4a **opus** — tax-timing correctness with mixed-age-couple and year-of-death edge cases; golden-master implications.
  - T4b **opus** — scoring-objective redesign with survivor-weighting and advice-framing risk.
  - T4c **opus** — new strategy that must coordinate with the Roth optimizer and the long-term holding-period test (wash-sale rules do not apply to gains).
  - T5a **sonnet** — mechanical-but-careful side-effect extraction with a clear target boundary.
  - T5b **sonnet** — choosing stable anchor figures for a parity assertion.
  - T5c **sonnet** — reusing an existing table renderer for two sections.
  - T5d **haiku** — add a parameter and set it at known call sites.

---

## 7. Appendix

### 7A. Findings refuted during cross-check (do NOT action)

**R1 — "Decompose `planning_engines.py`; extract the Monte Carlo engine first."** File-size and function-inventory facts check out (2730 lines; cited line numbers accurate). But the "MC is the most self-contained slice" premise is false: `_run_one_mc_path` (`:2250`) calls `sample_household_death_years` (defined `:525`, mortality section) and both `monte_carlo_exact_scalar` (`:2287`) and the vectorized batch entrypoint (`:2930`) call `project()` (`:1364`, deterministic section) — hard cross-section dependencies. The file's own header (`:1-21`) warns against re-splitting without tracing these calls, and `documentation/archive/SYSTEM_REVIEW_AND_REFACTOR_PLAN.md` records that Phase 2c investigated this exact split, found the same coupling, broke the engine at import time (caught by golden-master diff), and concluded not to attempt a structural split without a dedicated investigation. **Refuted.**

**R2 — "Finish the member_1/member_2 migration at the engine contract layer (h_/w_ keys)."** All cited code facts check out (the at-rest migration, the `c` dict built from h_/w_ keys, ~266 h_/w_ occurrences across ~26 files). But the framing that this is unfinished migration debt is refuted by the project's own documented decision: memory file `backward-compat-migration.md` records the husband/wife→member_1/member_2 CSV/data-at-rest migration as DONE (commit e809367) and explicitly says the internal role classifiers are "internal, NOT CSV-data compat... leave them." The h_/w_ dict keys are the engine's internal computational contract, not backward-compat scaffolding. Also, `c['members']` — proposed as the migration target — is dead outside `data_io.py` (no engine/reporting consumer), so "pivot downstream onto members[]" means building consumption from zero across 25+ files with a working tested contract, exactly the churn the project already weighed and declined. **Refuted.**

### 7B. Open questions for the user to decide

1. **Golden-master regeneration policy.** P1, P2, and A3 all shift projection totals and require regenerated baselines. Do you want each regenerated independently as its item lands, or batched into a single baseline-refresh checkpoint at the end of Wave 3? (Batching reduces churn but couples the items' verification.)
2. **SS recommendation framing (P3).** Removing the `lifetime_ss` term biases the result *earlier* — the current bug's undiscounted-sum term happens to reward delay, so de-double-counting without survivor weighting shifts the headline toward early claiming under the single fixed mortality assumption. The planner therefore requires survivor/longevity weighting to be **mandatory and shipped in the same change** (not "optional"). Given that, are you comfortable shipping a deterministic-mortality, survivor-weighted "Recommended Claim Age" with prominent longevity context, or do you want to hold the single-age headline entirely (presenting the ranked 81-pair table with longevity columns) until the longevity-probability-weighted Option 2 is built? Either way, choose knowingly that the de-double-count alone would push earlier.
3. **Estate precision (P4 Option 2) — sunset modeling struck.** The planner verified the code already reflects **post-OBBBA permanent** exemption law (`'Federal Exemption (MFJ, OBBBA)'`, `sheets_strategy.py:1101`), under which the scheduled TCJA sunset does not occur; modeling a sunset would inject a repealed assumption and false gifting urgency, so it has been removed from the recommendation. The only open question is whether the **low-value** graduated-rate + exemption-indexing polish is worth doing at all, given the flat 40% is a fine approximation at these estate sizes. Recommended: defer Option 2 indefinitely; ship only the Option 1 conditional note.
4. **Test reorganization appetite (Q2).** I propose freeze-and-fix-forward plus consolidating only the allocation and roadmap-completion clusters. Do you want the full XL subsystem reorganization instead, or is the scoped version acceptable?
5. **State-table depth (P5).** Is the flat-proxy expanded table (Option 1) acceptable as the shipped state, or is per-state estate/inheritance and retirement-income modeling (Option 2) required before this section is client-facing for relocation advice?
6. **Glossary single-source (D3 follow-up).** The consolidation adds a front-end fetch/API dependency. Confirm you want the front end to fetch the glossary at runtime rather than keeping a build-time-generated static copy.

---

## 8. Planner Sign-off

**Verdict (practitioner review, 2026-07-21).** The document is sound, honest, and unusually well-verified — the refuted-findings appendix and the cross-check corrections are exactly what a reviewing planner wants to see. All five planning findings (P1–P5) point at real defects; P4 (the self-contradicting estate note) and the P3 double-count are genuine credibility-killers. The planner confirmed the load-bearing citations against source (`sheets_strategy.py:187`, `:1099-1112`, `:1101`; `planning_engines.py:1205-1216`, `:1221-1228`) and endorsed shipping P4 Option 1 immediately, along with P1's age-63 gate logic, P2's headroom formula, P3's double-count diagnosis, P5's `il_total` baseline fix, the D1/D2/D3 glossary fixes, and the R1/R2 refutations — all as written. The concerns were with three of the recommended *fixes*, one stale-tax-law recommendation, and two missed findings. Those have been incorporated.

**What the planner changed in this revision:**
1. **P1 magnitude narrowed (highest-scope correction).** Struck "every pre-65 client"; scoped the finding to **non-ACA-bridge, pre-Medicare** clients, because the ACA premium-tax-credit MAGI guardrail (`planning_engines.py:1221-1228`) already binds tighter for ACA-bridge clients. Added an explicit design requirement that the fix **preserve the ACA PTC guardrail** (separate `_ranked_caps` entry). §1 item 1, §2E-P1, §5E-P1, T4a.
2. **New finding folded into P1.** The `fill_to_irmaa` policy (`:1205-1216`) lacks the ACA guardrail entirely — a live subsidy-destroying gap for gap-year clients; adding it is folded into the P1 change. §2E-P1, §5E-P1, T4a.
3. **P3 under-protection fixed (top priority).** Made survivor/longevity weighting **mandatory, not optional**, and required the de-double-count and the weighting to **ship in the same change (T4b)** — because `lifetime_ss` is an undiscounted sum that currently *rewards delay*, so removing it alone biases the headline toward **early** claiming, reintroducing the exact self-contradiction P4 condemns. §2E-P3, §4 Track 4, §5E-P3, T4b, Open Q2.
4. **P4 stale tax law struck.** Removed the "2026 exemption-sunset" modeling recommendation: the code already reflects **post-OBBBA permanent** exemption law (`'Federal Exemption (MFJ, OBBBA)'`, `sheets_strategy.py:1101`, re-verified), under which no sunset occurs. Reframed Option 2 as graduated-rate + exemption-indexing polish and reprioritized it as **low-value** (flat 40% is a fine approximation). §5E-P4 (conditional note) was already correct and is unchanged. §2E-P4, Open Q3.
5. **P5 Washington correction.** Removed WA from the flat-`excess*0.08` proxy tier — WA has an aggressive state estate tax (~$2–3M exemption, >20% top rate) that often dominates a wealthy relocator's cost; required verifying each state's **estate/inheritance** regime, not just income treatment, and flagged WA/OR/MN/MA as estate-tax states. §2E-P5, §5E-P5, T1b.
6. **P2 wash-sale wording corrected.** Wash-sale disallows losses, not gains; gain harvesting has no rebuy waiting period. Reworded to the **long-term holding-period test** and warned implementers not to add a needless 30-day gap. §2E-P2, §5E-P2.

**Sequencing:** the one interaction that matters (P1/P2 competing for the same low-income-year bracket space) is already correctly serialized (T4c after T4a). The single sequencing correction is P3's — its de-double-count must not ship ahead of its survivor weighting. No noted planner/author disagreements remain open; the planner's corrections were accepted in full after source verification of the three most consequential claims (`fill_to_irmaa` ACA gap, the OBBBA exemption label, and the `_ranked_caps` guardrail structure).

---

*End of report. This document is read-only output; no source files were modified in its production.*
