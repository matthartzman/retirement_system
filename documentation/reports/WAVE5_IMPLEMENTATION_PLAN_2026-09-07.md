# Wave 5 Implementation Plan — Corrections to Wave 2/3's Status Record and Remaining Medium/Low Findings

**Date:** 2026-09-07. **Source:** `documentation/reports/SYSTEM_REVIEW_2026-09-07.md` §9 (Wave 4/5 table),
continuing from Wave 4 (closed: SEC-1/SEC-2/SEC-3 via PR #92; N1 via PR #97 diagnostic + PR #98 disclosure).
Mirrors `WAVE4_IMPLEMENTATION_PLAN_2026-09-07.md`'s structure. Items below carry the review's own item IDs
(W4-6 through W4-9 are actually Wave-5-scheduled process-correction items despite the "W4-" prefix — that
numbering is the review's own; not renumbered here to keep traceability back to the source table).

**Status note:** all 14 items are independent (disjoint files, per the review's own concurrency note) and
can be parallelized. Grouped below by risk/sequencing convenience, not dependency.

---

## Group A — Process/status-record corrections (no code-behavior change, lowest risk)

### W4-9 — Correct the Wave 2/3 status record
- **Findings:** ARC-2, N7, N8, ARC-3
- **What:** Edit whatever tracking document records Wave 2/3 item status (likely `documentation/` roadmap/status
  file — locate via `grep -rl "2\.4\|2\.5" documentation/*.md` for the exact file) to read:
  - 2.4 → **partial** (write path retained by design — `src/server/app_core.py:1846-1905` documents the
    won't-fix rationale for 2.5 with a real cost measurement).
  - 2.5 → **won't-fix** (documented, not silently dropped).
  - 3.10, 3.12, 3.13 → **re-scoped** with monotonic metrics (line-count ratchet for 3.10/3.13 per ARC-3;
    registered-sheet-builder count for 3.12/N8, currently 6 of ~32).
- **Verification:** status document matches a fresh `grep`/line-count check of the cited files.
- **Effort:** S. **Risk:** None (documentation only).

### W4-8 — Regenerate `FUNCTIONAL_SPEC.md`; add a spec-currency guard
- **Finding:** DOC-201 — the doc claiming to describe "the system as the code currently behaves" omits all
  five features shipped since its stated generation date.
- **What:** (1) Update `FUNCTIONAL_SPEC.md` to mention the five missing features/terms and add the missing
  strategies to its §4.5-equivalent section. (2) Add a lightweight staleness guard (a test comparing the
  doc's stated generation date/commit against the newest commit touching a public engine surface — mirror
  the pattern of an existing `test_freeze_frontend_source_grep.py`-style ratchet test).
- **Verification:** spec mentions all four missing terms; new guard fails on the current (stale) doc, passes
  after the rewrite.
- **Effort:** S-M. **Risk:** None.

### DOC-202 — README still reads "v11" after the v12 bump *(Low, bundled here — same fix shape as W4-8)*
- **What:** Remove the version number from `documentation/readme/README.md`'s heading entirely (the app
  already reports its own version at runtime) rather than hand-fixing the string again; add
  `PROJECT_MANIFEST.md` to `bump_version.py`'s target list so this doesn't recur a third time.
- **Verification:** `bump_version.py --dry-run` (or equivalent) shows `PROJECT_MANIFEST.md` in its target set.
- **Effort:** S. **Risk:** None.

---

## Group B — Financial-domain corrections (require planner sign-off; move golden master)

### W5-1 — RMD Joint Life default inverted to require explicit spousal designation
- **Finding:** N4 (High confidence). `src/planning_engines.py:874-903` (near `rmd_divisor`,
  confirmed at :843-871 in the current diagnostic work) treats a missing beneficiary-titling record as
  "spouse is sole beneficiary," which **understates** RMDs (and understates the value of Roth conversions)
  for any household with a >10-year spousal age gap and no titling on file — the opposite-directional twin
  of the prior review's item 2.9 (which overstated RMDs).
- **What:** Invert the default: absent explicit titling data, fall back to the standard Uniform Lifetime
  table (not Joint Life relief). Reuse the existing beneficiary-titling-audit surface (the review references
  one already existing — locate via `grep -rn "sole_beneficiary_spouse\|beneficiary_titling" src/`) to flag
  households that *should* claim the relief but haven't recorded titling, rather than silently granting it.
- **Sign-off requirement:** per the review's own open question 4, this is "a financial-planning judgment
  call, not a pure engineering one" — **do not ship without the same explicit planner sign-off discipline**
  used for W4-3 (N2) and recorded in the review's §14. Surface the proposed default flip to the user/planner
  before implementing, exactly as the review's financial-planner sign-off section modeled for N2.
- **Verification:** a 12-year-gap household with no titling on file now computes RMDs under Uniform Lifetime,
  not Joint Life; a new audit-log/warning entry flags the missing titling.
- **Effort:** M. **Risk:** Medium — moves RMDs/taxes on any affected fixture; golden master will need
  regeneration for the frozen sample plan if it has this age-gap pattern (check first: `h_dob_yr`/`w_dob_yr`
  gap in `tests/fixtures/sample_plan_frozen/client_data.csv`).

### W5-2 — Cross-implementation equivalence test for `rmd_divisor`, then consolidate
- **Finding:** N5 (High confidence). `src/core.py:721-736` and `src/planning_engines.py:843-871` duplicate
  the same statutory lookup and floor logic.
- **What:** Sequence this **before** W5-1 if both are in flight (a consolidation is a much safer base to
  build W5-1's default-inversion logic on top of, and the review explicitly calls this "a cheap, proven
  pattern from the LTCG diagnostic"). Add a parametrized equality test over
  age × spouse-age × sole-beneficiary-flag grid comparing both implementations' output, confirm it passes
  (or find + fix the divergence it exposes), then consolidate into `tax_kernel.py` and have both call sites
  delegate to the single implementation.
- **Verification:** the new parametrized test passes; both original call sites now import from `tax_kernel.py`.
- **Effort:** S. **Risk:** Low.

### W5-3 — SS/annuity payment-timing convention parameterization (arrears default)
- **Finding:** N3 (Medium confidence, convention question). `src/core.py:1441-1458`,
  `deterministic_engine.py:405-421` treat SS/annuity entitlement-month as a payment month; SS and ordinary
  annuities pay in arrears, so a March entitlement should yield 9 checks that year, not 10.
- **What:** Parameterize the shared coverage-period helper by an explicit payment-timing convention
  (in-advance vs. in-arrears) rather than reusing it unmodified for both concepts — this is the same
  shared-root-cause fix the review's §8 target design calls out alongside N2. Default to arrears (SSA/annuity
  standard).
- **Verification:** a December claim yields zero SS cash that calendar year (arrears) vs. one payment today.
- **Effort:** S. **Risk:** Low, but confirm interaction with W4-3's (N2) already-shipped month-precision fix
  before implementing — both touch the same claim-month/payment-count logic; re-read that PR's diff first
  to avoid reintroducing the bug it fixed.

### W5-9 — Delete RMD $500 de-minimis threshold
- **Finding:** N6 (Low). An undocumented magic number inside a statutory calculation with no statutory basis.
- **What:** Delete the threshold (likely in `compute_rmds`/`apply_rmds`, `src/planning_engines.py` — grep
  `500` near those functions to confirm the exact line before touching).
- **Verification:** a $400 IRA at age 80 now produces a small positive RMD instead of being suppressed to zero.
- **Effort:** S. **Risk:** Low (golden master may shift by a trivial amount if the frozen fixture has a
  small pretax balance near this threshold — check first).

---

## Group C — Architecture status/consolidation (no user-facing behavior change)

### W4-6 — Reopen or formally close item 3.11 (frontend module extraction)
- **Finding:** ARC-1 — recorded complete against a criterion the current state does not meet.
- **What:** Either (a) reopen 3.11 with a measurable criterion (import count, `<script>` tag count in
  `frontend/index.html`) and continue extraction toward it, or (b) formally accept the current state and
  delete now-unused exports left behind by partial extraction. Recommend (b) unless there's a concrete reason
  to keep extracting — matches the review's own preference for status accuracy over continued churn on a
  track with weak measured progress.
- **Verification:** the chosen metric moves in the stated direction (if reopened), or unused exports are
  gone (if closed).
- **Effort:** M-L. **Risk:** Medium (touches `dashboard.js` module boundaries — run the full frontend test
  suite, not just fast tier, if choosing (a)).

### ARC-5 — `workbook_common`'s barrel-export problem, half-fixed *(Medium, bundled with W4-6's theme)*
- **What:** The module still star-imports `core` and generates `__all__` from `globals()`. Stop the
  `globals()`-derived `__all__`; export an explicit, curated list.
- **Verification:** `dir(workbook_common)` no longer includes stdlib/openpyxl names it merely imported.
- **Effort:** S. **Risk:** Low, but grep every consumer of `from workbook_common import *` first — an
  explicit `__all__` will silently break any caller relying on an accidentally-re-exported name.

---

## Group D — Accessibility and UI-contract fixes (frontend-only, disjoint surfaces)

### W4-7 — Annualize toggle accessibility
- **Finding:** UX-101 — conveys a budget-overwrite-triggering state by color alone.
- **What:** Add a non-color state indicator (icon/text, not just a color swatch), `aria-pressed` on the
  toggle control, and a `:focus-visible` tooltip. Locate in `frontend/js/dashboard.js` or
  `frontend/js/spending_dashboard.js` — grep `Annualize` to find the render site.
- **Verification:** grayscale render still distinguishes the two states; toggle is keyboard-reachable with a
  visible label on focus.
- **Effort:** S. **Risk:** Low.

### W5-7 — Confirm dialog semantics + listener-leak fix
- **Finding:** UX-105 — dynamically-built confirm dialogs lack `role="dialog"`/`aria-modal`, no focus
  trap/restore, and leak a `keydown` listener on every non-Escape close. These guard destructive actions
  including the same no-undo budget overwrite as UX-101.
- **What:** Add `role="dialog"`, `aria-modal="true"`, focus trap on open and focus restore on close; fix the
  listener leak (ensure the `keydown` handler is removed on every close path, not just Escape).
- **Verification:** `role="dialog"` present; listener count (via a test harness counting
  `addEventListener`/`removeEventListener` calls) does not grow across repeated open/close cycles.
- **Effort:** S. **Risk:** Low.

### W5-4 — Extend `no_internal_keys_on_screen` guard to PHASE_VARYING help text
- **Finding:** DOC-203 — `frontend/js/dashboard.js:6251-6268` surfaces `roth_phase_count`,
  `roth_phase_first_bracket_rate`, and the literal `"PHASE_VARYING"` to a non-expert end user.
- **What:** Rewrite the four affected help-text strings in plain language (no internal config-key names).
  Extend the existing `no_internal_keys_on_screen` guard (find it via
  `grep -rl "no_internal_keys_on_screen" tests/`) to cover the `PHASE_VARYING` help-text map so this can't
  regress.
- **Verification:** extended guard fails against the current strings before the rewrite, passes after.
- **Effort:** S. **Risk:** Low.

### W5-6 — Trends-reporter accessibility + escaping + error-state pass
- **Findings:** UX-102 (High), UX-106 (Low). No `role="img"`/labels/data-table fallback on trends-reporter
  charts; category names interpolated **unescaped** into SVG markup (a Monarch category containing `&`/`<`
  breaks rendering — this is a real injection-shaped bug, not just an a11y gap); 10px chart text; no error
  state for a failed history fetch/run (misattributed to "no data yet").
- **What:** In `financial_trends_reporter/frontend/index.html` (per QUA-302, chart logic is inline there):
  add `role="img"` + accessible labels + a data-table fallback; HTML-escape every interpolated category name
  before SVG string-building; bump chart text to a readable size; add an explicit error state distinct from
  "no data yet" for fetch/run failures.
- **Verification:** screen-reader pass on the chart; a category name containing `&`/`<` renders correctly
  (no broken SVG, no unescaped injection); a simulated fetch failure shows an error state, not an empty-state
  message.
- **Effort:** S-M. **Risk:** Low, but treat the escaping half as the priority — it's a correctness/injection
  bug wearing an accessibility finding's ID, not merely cosmetic.

### W5-8 — Monarch card: autosave + busy state; fix stale fallback path
- **Findings:** UX-103 (High), UX-104 (High). Manual "Save setting" button with no dirty/busy state in an
  otherwise-autosaving app; client-side fallback literal (`"../Monarch Extractor/output"`) is stale relative
  to the server default (`"Monarch Extractor/output"`, post W4-4's consolidation) — a first-run user can
  commit a nonexistent path before the status fetch resolves.
- **What:** Convert the Monarch settings card to the app's standard autosave pattern (dirty/busy indicator,
  no manual save button); give "Import now" a visible running/complete/failed state; fix the stale client
  literal to match the current server default (grep both to confirm exact match after W4-4's change).
- **Verification:** toggling a setting persists across navigation without an explicit save click; the
  client-side fallback path string matches the server default exactly.
- **Effort:** S. **Risk:** Low — but do this *after* confirming W4-4's server-side default landed as
  documented (it did, via PR #92) so the two strings are compared against the current, not stale, server value.

---

## Group E — Test coverage (additive only)

### W5-5 — One e2e spec for the Monarch settings card round-trip
- **Finding:** QUA-301 — the Monarch card exercises the exact fetch/module/global-bridge pattern that
  previously caused a real production outage (`tests/e2e/script-order-spike.spec.js` exists because of it),
  with zero e2e coverage of its own.
- **What:** Add one Playwright/e2e spec exercising: load card → change setting → verify persisted (post-W5-8,
  via autosave) → trigger "Import now" → verify status update. Deliberately break the module/global bridge
  in a throwaway branch first to confirm the new spec actually fails before restoring it (the review's own
  verification method).
- **Verification:** spec fails when the module/global bridge is deliberately broken; passes otherwise.
- **Effort:** S. **Risk:** Low. **Sequencing:** do this after W5-8 so the spec exercises the corrected
  autosave flow rather than the old manual-save one (avoids writing a test against soon-to-be-dead UI).

---

## Explicitly out of scope for Wave 5 (per the review's own limitations/assumptions)

- **ARC-4** (`financial_trends_reporter` standalone-vs-folded-in) — the review states this is "a
  product/architecture decision, not one this review resolves." Do not implement either direction without
  an explicit product decision; the review's only hard constraint is that whichever is chosen, it must never
  acquire SEC-1's wildcard-CORS pattern (worth a one-line regression test regardless of which direction is
  chosen, since the constraint holds either way).
- **QUA-302** (trends-reporter chart-logic extraction to a module) — bundle into W5-6 only if the escaping
  fix is cleaner with the logic already extracted; otherwise treat as a separate, larger follow-on (it's a
  refactor, not a defect fix, and the review doesn't schedule it into Wave 5's table).
- **DOC-204** (no end-user docs for Monarch/trends-reporter), **DOC-205** (five overlapping optimization-plan
  docs with no index), **QUA-303** (test-hygiene ratchets past headroom), **SEC-4/SEC-5** (audit-log
  financial-field redaction gap; misleading `encryption_status()` string), **ARC-6/ARC-7** (restated/copy-drift
  items), **UX-107** (no skip-link) — all Low-severity, not in the review's own Wave 5 table. Worth a Wave 6
  pass but not blocking; listed here only so they aren't lost.

---

## Suggested sequencing

1. **Group A** first (process-only, zero code risk, unblocks accurate status reporting for everything else).
2. **W5-2** (rmd_divisor consolidation) before **W5-1** (Joint Life default inversion) — consolidate the
   duplicated logic before changing its default behavior, so the fix lands once, not twice.
3. **W5-1** only after explicit planner sign-off is obtained (per the review's open question 4) — do not
   implement speculatively.
4. **Groups C, D, E** can run fully in parallel with each other and with Group B; they touch disjoint files.
5. **W5-3** (payment-timing convention) — implement after confirming interaction with the already-shipped
   W4-3 (N2) fix, since both touch SS/annuity payment-month logic in the same functions.

## Test discipline for this wave

Per `documentation/CLAUDE.md`: fast tier (`pytest tests/ -m "not slow" --tb=short -q`) after every item;
full suite before any PR touching `workbook_builder.py`/`projection_pipeline.py`/golden-master fixtures
(W5-1, W5-3, W5-9 all qualify) or before pushing. W5-1, W5-3, and possibly W5-9 will move the golden master —
regenerate via `tools/regen_golden_master.py regen --reason <file>` per the established provenance-gated
process, and report the shift as a **correction**, consistent with how N2's fix was handled (per the
review's §14 financial-planner sign-off), not silently absorbed.
