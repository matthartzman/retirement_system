# System Modernization Plan

Generated: 2026-07-07

Scope: full-repository review of the retirement planning system (~42K lines of
Python in `src/`, ~6K lines of JS in `frontend/`, 158 pytest files, plus the
Android shell and `tools/`). This plan covers four workstreams:

1. Remove all legacy and backwards-compatible code
2. Improve code consistency, effectiveness, efficiency, and maintainability
3. Improve usability — consistency, eliminate redundant functionality and
   content, make helper text meaningful instead of boilerplate
4. Proposed enhancements

Each phase names the Claude model that should execute it (Section 6).

This plan is the successor to `SYSTEM_REVIEW_AND_REFACTOR_PLAN.md`
(2026-07-02, landed via PR #1). That plan's Phase 0 safety net is **done** —
CI (`ci.yml` with pytest, ruff, mypy-informational, a frontend `node --test`
job), `pyproject.toml` pytest/ruff/mypy config, root `conftest.py`,
`requirements-dev.txt`, `security_audit.py` extraction, the
`flask_compat.py` → `wsgi_facade.py` rename, and `csv_migration.py`
extraction all exist on `main` today. This plan does **not** re-litigate
those; it picks up what that plan left open and goes deeper on the four
workstreams above.

---

## 1. Current state — what the review found

### Verified still open from the previous plan

| Item | Evidence |
|---|---|
| Generated `output/` tree still tracked in git and drifted | `git ls-files output/` returns files; `output/js/dashboard.js` differs from `frontend/js/dashboard.js`; `output/js/` still contains `dashboard_roadmap11.js`/`dashboard_roadmap12.js`, which were renamed in `frontend/js/` |
| Wildcard route assembly | `from .app_core import *` remains in `workbook_routes.py`, `admin_routes.py`, `base_routes.py` (fixed in `plan_routes.py` only) |
| Oversized modules unsplit | `planning_engines.py` 2,710 lines; `sheets_summary.py` 2,685; `dashboard.js` 2,698; `data_io.py` 2,392; `spending_tracker.py` 2,258; `deterministic_engine.py` 1,689; `app_core.py` 1,608 |
| Case-collision doc duplicate re-appeared | `documentation/release_notes/INDEX.md` **and** `index.md` both exist again (one was deleted pre-merge in `24ef9f6`) |
| mypy backlog | ~162 genuine errors, gated informationally only; 102 false positives caused by the wildcard imports above |

### New findings from this review

- **The test suite is the single biggest drag on every other workstream.**
  121 of 156 test files read source files as text (`.read_text()` /
  `inspect.getsource`) and assert on strings — route URLs, JS snippets,
  sheet names, even comment text. `planning_engines.py:1147` literally
  maintains "Migration breadcrumbs for legacy source-inspection regression
  tests." These tests lock in implementation details, so *every* rename,
  helper-text rewrite, or module split in this plan pays a tax of updating
  string assertions that verify nothing about behavior. Several files are
  pure change-log tests (`test_29_roadmap_completion.py`,
  `test_92_v10_roadmap_items_1_8_complete.py`) that assert historical
  roadmap items were completed.
- **Backwards-compat code clusters in three places** (full inventory in
  Section 2): plan-data *read-side* shims in `data_io.py`, the legacy
  budget/tracking model in `spending_tracker.py`, and the
  wellness→healthcare terminology alias layer — which is only half-migrated:
  `terminology_aliases.py` declares "healthcare" canonical and even ships a
  `contains_user_facing_legacy_wellness()` guard, yet `frontend/js/dashboard.js`
  still says "wellness" in 37 places of live UI copy.
- **Helper text is generated boilerplate at scale.** `dashboard.js` builds
  field help by keyword-matching the field label and emitting template
  paragraphs (`fieldDefaultMeaning`, `fieldConnection`, per-page 4-paragraph
  `pageHelp` blocks). The fallback branch produces filler like "Documents
  the *X* assumption within *Y*. The projection reads it with nearby fields…"
  — text that is longer than the field name and adds nothing. Identical
  sentences repeat across pages (e.g. "premiums may lower terminal net worth
  if no claim occurs" appears verbatim on two pages; HSA withdrawal timing is
  re-explained on three).
- **`roth_legacy_*` is NOT legacy code.** In `planning_engines.py`,
  `result_contract.py`, and the Roth UI, "legacy" means *bequest* — the
  estate value left to heirs (`roth_legacy_score`, `legacy_objective_mode`,
  `LEGACY_TARGETED`). Any automated "remove legacy" sweep that touches these
  breaks the Roth conversion scorer. Section 2 separates the two meanings
  explicitly; this is the main reason Workstream 1 needs a capable model and
  not a find-and-delete pass.

---

## 2. Workstream 1 — Remove legacy and backwards-compatible code

### 2.1 Guardrail: two different "legacy"s

**Keep (domain terminology, live features):** `roth_legacy_score`,
`legacy_objective_mode`, `roth_legacy_objective_mode`, `LEGACY_TARGETED`,
`legacy_adjustment`, `rebalance_legacy_gain_deferral_pct`, and every
"legacy/survivor/estate" phrase in UI copy. These mean *bequest*. Optional
follow-up (Workstream 3): rename the identifiers to `bequest_*` so the word
"legacy" stops being ambiguous in this codebase — but that is a rename, not
a removal, and must migrate saved plan keys.

**Remove (true compatibility shims):** everything below.

### 2.2 Inventory of back-compat code to retire

| # | Shim | Location | What it tolerates |
|---|---|---|---|
| 1 | Legacy `extra_N` spending rows suppressed when budget-lines file exists; "Plans without the budget-lines file keep legacy behavior" | `data_io.py:~584-695` | Pre-budget-taxonomy plans |
| 2 | Legacy `annual_charitable_giving_*` scalar fields folded into taxonomy budget | `data_io.py:~650` | Old charitable inputs |
| 3 | Legacy single Note Receivable layout re-homed under `__legacy_summary__` synthetic subsection | `data_io.py:~838-878` | Old single-note plans |
| 4 | Legacy `withdrawal_window` honored beside the controlled-window control | `data_io.py:~894` | Old withdrawal config |
| 5 | Legacy "Near Term / Long Term / Through YYYY" rows accepted conditionally | `data_io.py:~935` | Old spending-phase rows |
| 6 | "Forgiving" parse of older files storing values in wrong shapes | `data_io.py:~917` | Old UI data entry |
| 7 | `_LEGACY_TRACKING_MAP`, `_legacy_source_page_for_tracking_type`, `_legacy_budget_to_unified` fold-in, legacy CSV header accepted, legacy keyword-key alias exposure (two sites), legacy mirror file written on every export, "treat old model_managed as housing" | `spending_tracker.py:227,476,733,1092,1303-1484,2195-2252` | Pre-unified spending/budget model |
| 8 | Wellness→healthcare terminology alias layer (8 legacy IDs for premiums, 3 for OOP cap) + `contains_user_facing_legacy_wellness` test guard | `terminology_aliases.py` (consumed by data_io, reporting, admin) | Old CSV labels and snapshots |
| 9 | One-shot row purges: `DEPRECATED_ALLOCATION_COUNT_LABELS`, `RETIRED_SCENARIO_HOME_ROW_KEYS` | `server/csv_migration.py` | Rows retired in earlier versions |
| 10 | Deprecation stub launchers (`raise SystemExit` redirects) | `tools/launch_ui.py`, `tools/run_wsgi_server.py` | Old launch entry points |
| 11 | Committed generated output incl. stale pre-rename JS (`dashboard_roadmap11/12.js`) | `output/` (tracked in git, drifted from `frontend/`) | Nothing — pure hygiene |
| 12 | Case-collision doc duplicate | `documentation/release_notes/INDEX.md` vs `index.md` | Nothing — pure hygiene |
| 13 | Roadmap/breadcrumb tests and the source comments they pin (`Migration breadcrumbs for legacy source-inspection regression tests`) | `tests/test_29_*.py`, `tests/test_92_*.py`, `planning_engines.py:1147` | Historical change-log assertions |

### 2.3 Removal method (the order matters)

Back-compat shims 1–9 exist to *read old saved plan data* (Plan Data CSVs,
`.rpx` exports, snapshots). Deleting the read-side first would orphan every
plan file written before the current schema. The safe sequence:

1. **Write a one-time migrator** — `tools/migrate_plan_data.py` that loads a
   plan through the *current* forgiving readers and rewrites it in canonical
   form only (unified budget lines, healthcare terminology, multi-note
   layout, canonical withdrawal window, purges applied), stamping a schema
   version via the existing `schema_registry.py`. Reuse the read-side shims
   themselves as the migration logic — they already are the migration, just
   running lazily on every load instead of once.
2. **Migrate in place**: run the migrator over `input/`, `saved_plans/*.rpx`,
   and reference fixtures; regenerate `plan_data_manifest`
   (`tools/check_plan_data_sync.py --write`) and the golden-master fixtures.
3. **Gate loads on schema version**: the loader accepts current-version files;
   for older files it invokes the migrator once (with an on-disk backup) and
   proceeds. This replaces ~9 scattered shims with one explicit,
   versioned migration path.
4. **Delete the shims** (items 1–9), the legacy mirror-file export, the
   alias payload endpoint if the UI no longer needs it, and the breadcrumb
   comments/tests (item 13, folded into the Workstream 2 test cleanup).
5. **After one stable release**, evaluate deleting the migrator itself for
   pre-unified formats, keeping only version-N-1 → N support.

Hygiene items 11–12 and stubs (10) need no migration: untrack `output/`
(add to `.gitignore`; `check_package_clean.py` already asserts it's excluded
from releases), delete one of the two release-notes index files, delete the
stub launchers.

**Acceptance criteria:** `grep -riE 'legacy|backward|deprecated' src/ frontend/js/`
returns only bequest-domain identifiers and the versioned migrator; loading a
pre-migration `.rpx` still succeeds (via the migrator, with backup);
golden-master projection numbers unchanged byte-for-byte.

---

## 3. Workstream 2 — Consistency, effectiveness, efficiency, maintainability

### 3.1 Test-suite modernization (do this first — it de-risks everything else)

The 121 source-text-matching test files are the root maintainability problem:
they make correct refactors fail and give false confidence (a string can be
present while the feature is broken — main's recent history shows exactly
this: "Fix Download PDF … (regression)", "Export CSV backup: was calling an
undefined function" both shipped through a green suite).

- Delete pure change-log tests (`test_29_roadmap_completion.py`,
  `test_92_v10_roadmap_items_1_8_complete.py`, and any test whose only
  assertions are "file X contains string Y" about *comments or docs*).
- Convert route/behavior tests to call the stdlib route-registry test client
  (it exists — desktop mode runs on it) and assert on responses, not on
  `plan_routes.py` source text.
- Convert JS string-matching tests into real `node:test` cases (the CI job
  and runner already exist) for the pure functions being asserted about.
- Keep and strengthen the golden-master engine tests and workbook snapshot
  fixtures — those are genuine behavior locks.
- Rename `test_<number>_<roadmap-item>.py` files by domain
  (`test_taxes_*.py`, `test_workbook_*.py`, …) so the suite reads as a spec,
  not a changelog.

Target: no test reads production source as text except a small linter-style
guard set (e.g. the flask-free-runtime check, the terminology guard while it
still exists).

### 3.2 Consistency

- **Finish the service extraction.** Kill the remaining
  `from .app_core import *` in `workbook_routes.py`, `admin_routes.py`,
  `base_routes.py`; route modules import the specific services/helpers they
  use. This also deletes mypy's 102 wildcard-import false positives and lets
  ruff's F403/F405 ignores be removed.
- **One pattern per concern**: all routes register via `route_manifest.py`;
  all business logic in `server_services/*` subclassing `base_service.py`
  (several services predate it); all money math through `money.py`; all
  schema access through `schema_registry.py`.
- **Frontend**: finish the stalled `dashboard.js` →
  `frontend/js/modules/` extraction (`phase3_module_manifest.js` is the
  started skeleton). Target: no JS file over ~800 lines, one shared
  `api_client.js` call path (no bare `fetch` outside it).

### 3.3 Effectiveness (make the code do its job verifiably)

- Decompose the six oversized modules, in dependency order and one PR each:
  1. `sheets_summary.py` — split the 1,415-line `build_sheet4` into
     module-level helpers (pure decomposition; styling helpers already exist
     in `workbook_common.py`).
  2. `app_core.py` — finish extracting what remains after the
     security_audit/csv_migration pulls.
  3. `data_io.py` — becomes much smaller after Workstream 1 deletes its
     shim code; then split parse/validate/summarize.
  4. `spending_tracker.py` — same: post-shim-removal, split
     tracking/taxonomy/reporting.
  5. `planning_engines.py` + `projection_stages/deterministic_engine.py` —
     **highest risk**. The engine relies on `from ..planning_engines import *`
     plus explicit `_legacy_pe._aa`-style rebinding of underscore aliases; a
     previous cleanup attempt broke it at import time. Split only behind the
     golden-master byte-diff harness, alias by alias.
  6. `dashboard.js` — per 3.2.
- Add direct unit tests where the prior plan found none:
  `optimization.py`, `market_data.py`, `secrets_store.py`, plus the
  services extracted above.

### 3.4 Efficiency

- Profile first (`tools/profile_projection.py` exists); fix measured, not
  assumed, hotspots. Known candidates from the prior review: per-request
  CSV disk copies and repeated `parse_client` recomputation in the request
  path; workbook XML assembly (an optimizer module exists —
  `workbook_xml_optimizer.py` — verify it's actually in the build path).
- Make the vectorized Monte Carlo path (`vectorized_fast_core.py`,
  `quick_vectorized` mode) the default where results are within tolerance;
  keep `advanced_exact_scalar` as the advisor-grade option.
- CI: cache pip, split the slow build-pipeline smoke test behind the
  existing `slow` marker on PRs, run it on main only.

### 3.5 Maintainability

- Burn down the ~162 genuine mypy errors module-by-module as each is touched;
  flip mypy from informational to gating once under ~20.
- Expand ruff selects (at minimum `B`, `UP`, `SIM`) once the wildcard
  imports are gone.
- Single version surface (`tools/check_version_surfaces.py` exists — wire it
  into CI).
- Consolidate the two READMEs (`documentation/readme/README.md` vs
  `CLEAN_PACKAGE_README.md`) into one, with a short release-package variant
  generated from it.

---

## 4. Workstream 3 — Usability

### 4.1 Helper text: curated, deduplicated, or absent

Today's model — keyword-matched template paragraphs generated in
`dashboard.js` (`fieldDefaultMeaning`, `fieldConnection`, `fieldExplain`,
`pageHelp`) — guarantees boilerplate: every field gets three paragraphs
whether or not there is anything to say. Replace it:

1. **Move help content out of code into the plan-data manifest/schema
   registry** (one source shared by the UI, the workbook QC sheets, and the
   admin console). Each field gets an optional `help` entry with up to three
   short, field-specific facts: what it changes, what commonly goes wrong,
   and a sensible default. No entry → no help panel; the label and units
   must carry self-evident fields.
2. **Delete the generated-fallback branches entirely.** "Documents the X
   assumption within Y…" text is strictly worse than nothing: it trains
   users to ignore the help.
3. **Write curated help only where the review found real leverage** —
   Roth conversion policy + objective weights, IRMAA guardrails, withdrawal
   sequencing, allocation optimizer modes, Monte Carlo engine mode, estate
   objective modes, spending growth mode. (~60–80 fields, not ~600.)
4. **Deduplicate page-level help.** Each concept is explained on exactly one
   page; other pages link to it ("HSA timing is set on Other Assets →
   HSA" as a link, not a re-explanation — it currently appears on three
   pages). Kill repeated stock sentences ("premiums may lower terminal net
   worth if no claim occurs" et al.).
5. **Acceptance criteria:** no help string appears twice in the UI; no help
   string is derivable from the field label alone; every remaining help
   string names a concrete behavior of *this* model, not generic financial
   advice.

### 4.2 Terminology and copy consistency

- Finish the wellness→healthcare migration in the UI: 37 "wellness"
  occurrences in `dashboard.js` copy contradict the canonical "healthcare"
  labels the backend and reports now use. After Workstream 1's data
  migration, the alias layer and the string guard both retire.
- One naming standard for user-visible surfaces: page titles in Title Case,
  fields in sentence case, the same term everywhere for the same concept
  (pick one of "probability of success" / "success probability"; one of
  "terminal net worth" / "TNW" with the abbreviation defined once per page).
- Consistent confirm/alert affordances (in-app dialogs are nearly universal
  now; sweep the remaining `window.confirm` fallback path in
  `navigation.js`).

### 4.3 Redundant functionality and content

- Continue the duplicate-control sweep main already started ("remove
  duplicate build/refresh buttons", `07c9ce0`): audit every page for
  multiple controls invoking the same route; keep one, placed consistently.
- Decide `PLANNING_WORKBENCH_CONSOLIDATION_PROPOSAL.md` (merge the planning
  workbench and Planning Levers hub or clearly separate their jobs) — both
  currently offer "estimate the effect of a change" entry points.
- One release-notes index, one README (per 3.5), and archive the completed
  plan/roadmap docs (`UX_REDESIGN_ROADMAP.md`,
  `IMMEDIATE_NEXT_ACTIONS_IMPLEMENTATION.md`, the 2026-07-02 refactor plan)
  under `documentation/archive/` so live docs are only current ones.

### 4.4 Accessibility (open item inherited from the previous plan)

Labels/roles/focus management on `index.html` + `admin.html`, keyboard-only
navigation of the sidebar and dialogs, and color-contrast check of the
status banners. Ship as its own PR with a checklist.

---

## 5. Workstream 4 — Proposed enhancements

Ordered by (user value ÷ effort), all deliberately post-cleanup:

1. **Scenario comparison view.** The engine already scores candidate
   strategies and `result_contract.py` already generates "why selected /
   why not" reasons — surface them: pick 2–3 saved builds or strategy
   candidates, show KPI deltas (TNW, lifetime tax, success probability,
   first-failure year) side-by-side with the existing reason strings.
2. **"What changed since last build."** `build_snapshot.py` and the build
   history already persist inputs+outputs; diff the current build against
   the previous one and show a one-screen digest (inputs that changed →
   KPIs that moved). Turns the black-box rebuild into a feedback loop.
3. **Schema-driven forms end-to-end.** Once help/validation live in the
   manifest (4.1), generate the input forms from it too — new fields then
   require zero hand-written UI, and Python/JS validation can't drift.
4. **Guided first-run / blank-plan flow.** A short wizard (household →
   accounts → spending → build) that fills the minimum viable plan, replacing
   the current "empty grid" cold start.
5. **Async build with progress streaming.** The build-job service exists;
   stream stage-level progress (parse → project → MC → workbook) to the UI
   instead of a spinner, and let users cancel.
6. **Advisor-grade PDF/workbook unification.** One report spec
   (`report_spec.py`) drives both the Excel workbook and the enterprise PDF
   so the two never disagree; today they are separate builders.
7. **Android completion** per `ANDROID_MOBILE_ENHANCEMENT_PLAN.md`, gated on
   the frontend module split (6.2) so mobile doesn't fork `dashboard.js`.

---

## 6. Phasing and model assignment

Rules used for the assignments:

- **Claude Fable 5 (`claude-fable-5`)** — highest-capability tier; reserve
  for work where a subtle mistake silently corrupts data or numbers:
  migration design, the projection-engine split, and final review of each
  phase.
- **Claude Opus 4.8 (`claude-opus-4-8`)** — deep multi-file refactors and
  design work below the "silent data corruption" bar.
- **Claude Sonnet 5 (`claude-sonnet-5`)** — the workhorse for well-specified
  implementation once the pattern is established; near-Opus coding quality
  at lower cost.
- **Claude Haiku 4.5 (`claude-haiku-4-5`)** — only truly inert mechanical
  work (docs, gitignore, file deletes with zero fan-in). **Caution:** until
  Phase B lands, even "mechanical" renames break the string-matching tests,
  so Haiku's lane is narrower than it looks.

| Phase | Work | Model | Why |
|---|---|---|---|
| **A. Hygiene** (1–2 PRs) | Untrack `output/` + gitignore; delete stale `output/js/dashboard_roadmap11/12.js`; release-notes index dedupe; delete stub launchers; archive completed docs | Haiku 4.5 | Zero-fan-in deletions and doc moves; verified by CI |
| **B. Test-suite modernization** (3–5 PRs) | Design the conversion pattern + triage all 121 source-matching files | Opus 4.8 | Judgment call per test: behavior-convert vs delete vs keep-as-guard |
| | Execute the bulk conversion/renames following the pattern | Sonnet 5 | High-volume, well-specified after triage |
| **C. Legacy removal** (2–3 PRs) | Design `tools/migrate_plan_data.py`, schema-version gate, shim-retirement order (Section 2.3) | **Fable 5** | User plan files are at stake; the bequest-vs-compat "legacy" ambiguity punishes shallow pattern-matching |
| | Implement migrator + delete shims 1–9 + regenerate manifests/golden masters | Opus 4.8 | Deep, cross-module, but following an explicit design |
| | Wellness→healthcare UI copy sweep after data migration | Sonnet 5 | Well-specified once aliases retire |
| **D. Decomposition & consistency** (5–7 PRs) | `planning_engines.py` / `deterministic_engine.py` split behind golden-master byte-diff | **Fable 5** | Known trap (underscore-alias rebinding) already broke one attempt |
| | `sheets_summary.py`, `app_core.py`, `data_io.py`, `spending_tracker.py` splits; kill remaining wildcard imports; service-pattern unification | Opus 4.8 | Architecturally significant, tests now protect it |
| | `dashboard.js` → modules per manifest; ruff expansion; mypy burn-down; new unit tests for optimization/market_data/secrets_store | Sonnet 5 | Pattern-following implementation |
| **E. Usability** (3–4 PRs) | Help-content architecture (manifest-driven, 4.1 steps 1–2) | Opus 4.8 | Cross-cutting Python/JS/report design |
| | Write the ~60–80 curated help entries; dedupe page help; terminology/copy sweep; duplicate-control audit | Sonnet 5 | Content work against clear acceptance criteria |
| | Accessibility pass | Sonnet 5 | Checklist-driven |
| **F. Enhancements** (1 PR each) | Scenario comparison; build diff; schema-driven forms; wizard; progress streaming; report unification | Opus 4.8 design → Sonnet 5 build | Standard feature-development split |
| **Cross-cutting** | Review every Phase C/D PR before merge | **Fable 5** | Cheapest place to catch a silent numeric regression |

### Sequencing constraints

- **A anytime.** **B before C and D** — otherwise every rename fights the
  string-matching tests. **C before the `data_io.py`/`spending_tracker.py`
  splits in D** (removing shims first makes those files dramatically smaller)
  and **before E's terminology sweep** (UI copy can't drop "wellness" until
  saved data stops using it). **E and F after D's frontend split** where they
  touch `dashboard.js`.
- One concern per PR, every PR gated by the existing CI, golden-master
  byte-diff mandatory for anything touching `src/planning_engines.py`,
  `src/projection_stages/`, `src/taxes.py`, or `src/data_io.py`.
- After each phase: `pytest tests/ --tb=short -q`, `python tools/run_regression.py`,
  and a manual smoke of desktop mode + one workbook build.

### Definition of done for the whole plan

1. No compatibility shim outside the versioned migrator; migrator covers
   every historical plan format with an on-disk backup.
2. No module over ~1,000 lines except deliberately-consolidated engine files
   documented as such; no wildcard imports in `src/server/`.
3. No test asserts on production source text except designated guards.
4. Every help string is unique, field-specific, and non-derivable from its
   label; one page per concept.
5. ruff (expanded) and mypy both gate CI.
6. Golden-master projection numbers unchanged throughout (or changes
   explicitly re-baselined with a written reason).
