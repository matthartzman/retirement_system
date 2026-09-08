# Wave 6 Implementation Plan

**Date:** 2026-09-08. **Source:** `documentation/reports/SYSTEM_REVIEW_2026-09-07.md`, the findings Wave 5
left explicitly unscheduled (ARC-4, ARC-6, ARC-7, DOC-204, DOC-205, N9, QUA-302, QUA-303, SEC-4, SEC-5,
UX-107) plus `documentation/reports/WAVE_2_3_STATUS_CORRECTIONS_2026-09-07.md`'s re-scoped architecture
tracks (3.10/3.12/3.13, ARC-3, N8), which that document already correctly reclassified rather than closed.

This plan covers every finding Wave 4/5 did not schedule, using the same discipline established in those
waves: real regression tests verified to fail against the pre-fix source and pass after; fast tier after
every item, full suite before any golden-master- or workbook-pipeline-touching change; explicit sign-off
before any item with a genuine product/architecture judgment call, not just a financial one this time.

---

## Group A — Security (small, isolated, no sign-off needed)

### W6-1 — `secrets_store.encryption_status()` reports a false "configured" status
- **Finding:** SEC-5 (Low, high confidence).
- **What:** `src/secrets_store.py:20-21` hardcodes `{"mode": "local-only", "encrypted": False, "configured":
  True}` — `encrypted: False` and `configured: True` contradict each other in the same payload, for a module
  that is a plaintext store by design (a defensible choice for a single-user local app, per the review — the
  *string* is what's wrong, not the storage choice). Fix: `configured` should reflect whether a store file
  actually exists / has entries, not a hardcoded `True`; keep `encrypted: False` accurate as-is. Grep every
  consumer of `encryption_status()` (admin UI status chip, `tests/`) before changing the payload shape.
- **Verification:** a new test asserts the payload is internally consistent (no `encrypted: False` +
  `configured: True` combination) and that `configured` actually varies with real store state.
- **Effort:** S. **Risk:** Low — status-string-only, no behavior change to secret storage itself.

### W6-2 — Audit logging doesn't redact financial fields
- **Finding:** SEC-4 (Low, informational-but-real gap).
- **What:** `src/security.py:17-36`'s `SECRET_PATTERNS` only matches credential-shaped keys
  (`api_key`/`token`/`secret`/`password`). Two concrete gaps:
  1. Extend the pattern set (or add a second, field-name-based pass) to also redact common financial/PII
     field names (`balance`, `dob`/`date_of_birth`, `ssn`, `merchant`, `account_number`) wherever they appear
     as `"key": value` pairs in logged text.
  2. `_record_admin_config_change()` (`src/server/security_audit.py:217-240`) writes an un-redacted
     before/after `"changes"` diff (via `_summarize_csv_row_changes()`) straight to
     `<workspace_output>/admin_config_change_log.json` — this path never calls `redact_text` at all, unlike
     `_audit()`'s own write path which does when `cfg.redact_secrets_in_logs` is set. Since admin-edited CSVs
     (`client_policy.csv`, reference files) can carry DOBs/balances, this is the more concrete sink to fix.
- **Verification:** a new test asserts a synthetic admin-config-change diff containing a balance/DOB-shaped
  value is redacted in the written log; existing `_audit()` redaction tests (grep `tests/` for
  `redact_secrets_in_logs`/`redact_text` first) still pass.
- **Effort:** S-M. **Risk:** Low — additive redaction only, changes log *content* going forward, not any
  read/write behavior. Grep `tests/` for exact-content assertions against `admin_config_change_log.json`
  before touching its write path, since redaction will change what's written.

### W6-3 — `financial_trends_reporter`'s second HTTP surface has no origin check
- **Finding:** ARC-4 (High confidence, security half only — see the Group F sign-off gate below for the
  standalone-vs-folded-in product question this finding also raises, which this item does NOT resolve).
- **What:** `financial_trends_reporter/main.py:35-52` registers `GET /api/history` and `POST /api/run-now`
  with zero auth/CORS/origin check — not even the same-origin-only posture the main app settled on for SEC-1
  (`src/server/app_core.py:1962-1970`'s reasoning: no CORS headers needed for same-origin use, and none
  should ever be added). Add an explicit `Origin`/`Referer` check on state-changing routes (`POST
  /api/run-now` at minimum; consider `GET /api/history` too, since it returns the full net-worth/spending
  log) that rejects cross-origin requests outright — mirroring the main app's SEC-1 posture, not inventing a
  new auth scheme. This is a scoped mitigation independent of whichever way the Group F product decision
  goes; it must land either way.
- **Verification:** a new test drives `financial_trends_reporter/main.py`'s Flask/WSGI app directly (or via
  its own test client) with a forged `Origin` header and confirms the request is rejected; a same-origin (no
  `Origin` header, or matching one) request still succeeds.
- **Effort:** S. **Risk:** Low — additive check, does not change any legitimate same-origin call path.

---

## Group B — Documentation correctness (trivial, disjoint)

### W6-4 — Stale Monte Carlo default description in demo/frozen fixture data
- **Finding:** ARC-7 (Low, copy drift from item 1.1's MC-default flip).
- **What:** `input/demo/client_policy.csv:32` and `tests/fixtures/sample_plan_frozen/client_policy.csv:32`
  both carry `mc_engine_mode,quick_vectorized,...` with a notes column describing exact-scalar as "the
  default" — self-contradictory as currently written, and stale relative to the live app's actual default
  (`input/client_policy.csv:15`, `advanced_exact_scalar`). Fix the **notes/description text only** to
  accurately describe what `quick_vectorized` is (a faster, approximate diagnostic mode) without implying
  it's the advisor-ready default — do not change either file's actual `mc_engine_mode` *value*, since the
  frozen fixture backs the golden-master pins and a value change would be a real behavior change requiring
  the full golden-master regen discipline, which this item does not warrant.
- **Verification:** before touching `tests/fixtures/sample_plan_frozen/client_policy.csv`, grep `tests/` for
  any test asserting this file's exact byte content/checksum (workbook snapshot expectations, golden master
  fixture-diff tests) — a notes-column-only edit must not move `PINNED_TERMINAL_NW`/`PINNED_LIFETIME_TAX`.
  Run the golden master test after to confirm zero movement (comment-only change).
- **Effort:** S. **Risk:** Low, but touches a golden-master-adjacent fixture — full suite before calling this
  one done, per `documentation/CLAUDE.md`'s fixture-change rule.

### W6-5 — No end-user documentation for Monarch auto-update or the trends reporter
- **Finding:** DOC-204 (Medium confidence).
- **What:** `documentation/readme/README.md` (25 lines) mentions neither subsystem at all; the only existing
  docs (`docs/superpowers/plans/2026-09-02-monarch-autoupdate-reporting-plan.md`,
  `docs/superpowers/specs/2026-09-02-monarch-autoupdate-reporting-design.md`) are maintainer-facing design
  docs, not household-facing usage instructions. Add a short, plain-language section to the README (or a new
  `documentation/readme/`-adjacent doc, matching whatever house style the README already uses) covering: what
  Monarch auto-update does and how to turn it on (referencing the actual card, post-W5-8's autosave UI), and
  what the trends reporter is and how to run it.
- **Verification:** a new lightweight regression test (mirroring `test_functional_spec_feature_currency_regression.py`'s
  marker-presence pattern from Wave 5) asserts the README mentions both subsystems by name.
- **Effort:** S. **Risk:** Low — documentation-only.

### W6-6 — Five overlapping, unindexed optimization-plan documents
- **Finding:** DOC-205 (Low).
- **What:** `documentation/` root holds at minimum `Final Optimization Implementation Plan.md`, `Final
  Optimization Upgrade Plan.md`, `Latest Optimization Implementation Plan.md` (whose title text is *identical*
  to the first file's despite the different filename), `OPTIMIZATION_REFACTOR_STATUS.md` (a status tracker
  against the "Latest" plan, predates the other three by 5 days), and — least certain which the review meant
  as the fifth — `F0_F1_F2_COMPLETION_SUMMARY.md` and/or `REMAINING_WORK_EXECUTION_PLAYBOOK.md` (a related but
  distinct F0-F5 phase-tracking pair). Rather than guess which is "superseded" and risk mischaracterizing a
  document, this item is purely additive: create one short index
  (`documentation/OPTIMIZATION_DOCS_INDEX.md`) listing every doc in this cluster with its actual date, one-line
  purpose (read from its own status line/opening paragraph), and — only where the document's own content
  already says it supersedes or tracks another (e.g. `OPTIMIZATION_REFACTOR_STATUS.md` explicitly tracks the
  "Latest" plan) — that relationship. No existing document is deleted, renamed, or edited beyond an optional
  one-line "see the index" pointer added at the very top of each.
- **Verification:** the new index file exists and links to every file in the cluster; no existing document's
  substantive content changes.
- **Effort:** S. **Risk:** Low — additive only.

---

## Group C — Accessibility

### W6-7 — No skip-link; unlabeled main content landmark
- **Finding:** UX-107 (Low).
- **What:** `frontend/index.html:75-77` — `<main>` wraps both the full nav `<aside id="sideNav"
  aria-label="Guided steps navigation">` and the content `<section id="mainPane">`, which has no
  `aria-label`/`aria-labelledby`. A keyboard user must tab through the entire ~45-step nav before reaching
  content on every page load. Add a standard visually-hidden-until-focused skip-link right after `<body>`
  (before `<header>`) targeting `#mainPane`, and give `#mainPane` an `aria-label="Main content"` (or
  `aria-labelledby` pointing at the active step's heading, if that's cheap to wire) plus `tabindex="-1"` so
  the skip-link's focus jump actually lands there.
- **Verification:** new frontend test (mirroring the `annualize_toggle_accessibility.test.mjs`/
  `inapp_modal_accessibility_and_listener_leak.test.mjs` pattern from Wave 5) asserts the skip-link element
  exists, targets `#mainPane`, and `#mainPane` carries an accessible name. Verified to fail pre-fix, pass
  after.
- **Effort:** S. **Risk:** Low.

---

## Group D — Test-quality (the two ratchets QUA-303 flagged, plus N9's coverage gap)

### W6-8 — Suffix-shape ceiling is at exactly zero headroom
- **Finding:** QUA-303, first half (Low).
- **What:** `tests/test_test_file_suffix_shape_functional.py`'s `LEGACY_NO_SUFFIX_CEILING = 97` exactly
  equals the current un-suffixed-file count (97) — the next new un-suffixed test file added anywhere in the
  suite fails this ratchet immediately, for reasons unrelated to whatever that new file is testing. Per the
  ratchet's own stated mechanism ("moves DOWN, by renaming a file onto one of the six types in the same
  commit that lowers this number"), rename 5 clearly-classifiable legacy files (read each file first to pick
  the correct suffix — `_functional` for build/DOM/behavior-driven tests, `_unit` for a single pure function,
  `_regression` only for a documented prior bug fix) and lower `LEGACY_NO_SUFFIX_CEILING` to 92 in the same
  commit. Grep `tests/`, `documentation/`, and any CI config for each renamed filename first, since other
  files may reference it by name.
- **Verification:** the ratchet test itself passes with real headroom restored (92 ceiling, ≤92 actual); each
  renamed file's own tests still pass (targeted run before/after rename).
- **Effort:** S. **Risk:** Low — pure rename, no test logic changes.

### W6-9 — Frontend-source-grep baseline may be absorbing structural (not behavioral) exemptions
- **Finding:** QUA-303, second half (Low).
- **What:** `tests/fixtures/frontend_source_grep_baseline.json` has 73 entries against 73 currently-matching
  files — also zero headroom, but with a real classification question underneath it: the file's own docstring
  says structural assertions ("this file exists", "under N lines") are legitimately text-based and not what
  the freeze protects, only behavioral/string-literal assertions are. A pattern-based scan surfaced ~12
  candidate files that may be structural-only (`test_allocation_policy_cleanup_functional.py`,
  `test_dashboard_extract_module_tool.py`, `test_governance_hardening.py`,
  `test_optional_module_gating.py`, `test_workbook_format_config_regression.py`, and others). Read each
  candidate individually — not by pattern alone — and remove from the baseline only the ones that are
  genuinely structural-only (no frontend string-literal/DOM-text assertion anywhere in the file). This
  directly restores headroom in the exact way the file's own docstring says it should be composed.
- **Verification:** for each removed entry, confirm (by reading the file) it truly contains no
  frontend-source-text assertion; the baseline test suite still passes with the smaller baseline; the
  75%-of-suite sanity check (`test_baseline_is_smaller_than_the_whole_suite`) stays comfortably clear.
- **Effort:** M — 12 files need individual judgment, not a mechanical rename. **Risk:** Low but do this
  conservatively: when a candidate's classification is ambiguous, leave it in the baseline rather than guess.

### W6-10 — Monarch transaction sign convention has no contract test
- **Finding:** N9 (insufficient-evidence per the review itself — not a confirmed defect, a coverage gap).
- **What:** `src/ytd_tracking.py`'s `classify_cash_transaction()`/`classify_investment_transaction()`
  (lines ~730-751) implicitly assume negative amount = spending/debit, positive amount = income/credit/refund
  — standard Monarch export convention, but never asserted anywhere in `tests/`. Add a short doc comment
  codifying the convention at the function definition, plus a contract test asserting it against both a
  synthetic negative-amount and positive-amount row.
- **Verification:** new test passes against current code (this is coverage-additive, not a bug fix — there is
  no pre-fix/post-fix pair here since the convention isn't being changed, only documented and pinned).
- **Effort:** S. **Risk:** Low — additive only.

---

## Group E — Larger, higher-value, test-only extraction

### W6-11 — Trends reporter chart logic: extract from inline `<script>` into a testable module
- **Finding:** QUA-302 (High confidence).
- **What:** `financial_trends_reporter/frontend/index.html:58-224` is one inline `<script>` block with no
  module boundary — `filterByTimeframe` (83-106), `lineChartSvg` (120-140), `barChartSvg` (142-156), plus
  `escSvg`, `dataTableFallbackHtml`, `render`, `renderFetchError`, `loadHistory`, and load-time event wiring,
  all untestable except by regex-extracting the whole block (which
  `tests/frontend/trends_reporter_chart_escaping_and_accessibility.test.mjs` already does, added in Wave 5
  for the escaping/accessibility fix). Extract the pure, side-effect-free functions
  (`filterByTimeframe`/`lineChartSvg`/`barChartSvg`/`escSvg`/`dataTableFallbackHtml`) into a real module file
  (e.g. `financial_trends_reporter/frontend/charts.js`), loaded via `<script type="module" src="charts.js">`,
  leaving only the DOM-wiring/fetch/render orchestration inline. Update the existing Wave-5 test to import the
  real module directly (`node --test` already supports ESM) instead of regex-extracting the HTML — this is a
  strictly stronger test, not a rewrite of its assertions.
- **Verification:** existing escaping/accessibility assertions from Wave 5's test continue to pass against the
  extracted module; new unit tests for `filterByTimeframe`/`lineChartSvg`/`barChartSvg` exercise them directly
  (edge cases: empty timeframe, single data point, a category name needing `escSvg`) without the HTML-regex
  indirection.
- **Effort:** M. **Risk:** Low-Medium — touches the one file `financial_trends_reporter` actually serves;
  smoke-test the page loads and renders a chart after the split (this subsystem has no e2e coverage of its
  own yet — a manual check via `python financial_trends_reporter/main.py` + browser, or a minimal Playwright
  smoke spec if time allows, is the verification of last resort since no automated e2e exists here).

---

## Group F — Explicitly out of scope for Wave 6 (sign-off gate, or genuinely not wave-sized)

- **ARC-4's product question** — whether `financial_trends_reporter` should be folded into the main server or
  remain a standalone app is, per the review's own §6, "a product/architecture decision, not one this review
  resolves." W6-3 above lands the hard security constraint (no CORS wildcard, explicit origin check) either
  way, but this wave does **not** restructure the subsystem's hosting model without explicit direction. **Ask
  before Wave 6 execution begins**, per the established Wave 5 sign-off pattern.
- **ARC-3 / N8 / items 3.10, 3.12, 3.13** (engine decomposition, `results_model` page coverage, `parse_client`
  size) — already correctly re-scoped by `WAVE_2_3_STATUS_CORRECTIONS_2026-09-07.md` as long-running
  architecture tracks with their own machine-checkable metrics, not point-fixes. Genuinely not wave-sized;
  re-attempting a "reduce `run_deterministic_projection_stage` by N lines" fix as a disjoint Wave 6 item risks
  exactly the kind of low-value churn the prior review criticized. Leave tracked as-is; a future dedicated
  decomposition effort (its own wave, scoped with a real target) is the right vehicle, not this one.
- **ARC-6** (`results_model`/`detailed_results.py` scraper-path debt) — restated from the prior review "with
  no new information." Same reasoning as above; it's the same long-running track as N8/3.12, not a new,
  disjoint finding.

---

## Suggested sequencing

1. **Sign-off gate first**: ask the ARC-4 hosting-model question (Group F) before touching
   `financial_trends_reporter/` at all — W6-3 (security mitigation) and W6-11 (extraction) both live in that
   subsystem, and the answer could affect how much investment either is worth.
2. **Group A** (W6-1, W6-2, W6-3) — security, fully disjoint from everything else, no sign-off blocking W6-1/
   W6-2; W6-3 needs only the Group F gate answered, not blocked on the fold-in-or-not decision itself.
3. **Group B** (W6-4, W6-5, W6-6) — documentation, fully disjoint, can run in parallel with anything.
4. **Group C** (W6-7) — accessibility, disjoint.
5. **Group D** (W6-8, W6-9, W6-10) — test-quality, disjoint from product code entirely.
6. **Group E** (W6-11) — sequence last among the touched-file items since it's the highest-effort,
   highest-blast-radius (relative to this wave) change, and benefits from W6-3's origin check already being in
   place first (defense in depth before extracting/refactoring the surface that check protects).

## Test discipline for this wave

Per `documentation/CLAUDE.md`: fast tier (`pytest tests/ -m "not slow" --tb=short -q`) after every item; full
suite before calling W6-4 done (touches a golden-master-adjacent fixture) and before any push. Frontend items
(W6-5's regression test, W6-7, W6-9's baseline edits, W6-11) verified via `node --test tests/frontend/`. Every
fix ships with a regression test verified to fail against the pre-fix source and pass after, except W6-4 (a
documentation-only column, verified instead by golden-master non-movement), W6-6 (purely additive, nothing to
regress), and W6-10 (coverage-additive, no behavior change to pin a before/after against).
