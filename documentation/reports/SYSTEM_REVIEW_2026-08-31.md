# System Review — Retirement Planning System

**Date:** 2026-08-31
**Scope:** Entire system (engine, server, frontend, reporting, tests, documentation, financial modelling)
**Method:** Five independent expert reviews — architecture, usability, documentation/content, quality/test, CFP-level financial planning — followed by an adversarial cross-check pass in which a separate reviewer re-opened every cited file and attempted to refute each finding.
**Cross-check result: zero findings refuted.** A small number were confirmed-with-correction; those corrections are carried inline below and marked *(corrected on cross-check)*. There is therefore no "refuted findings" section in this report — the absence is a result, not an omission.
**Status of this document:** analysis and proposal only. No source file was modified in producing it.

### How to read this document

Every finding is presented as: *what it is* → *evidence (file:line)* → *options considered with tradeoffs* → *recommendation*. The options are kept visible on purpose. The recommendation is the reviewer's call, not a decision — a reader who disagrees should be able to pick a different option from the same evidence without re-doing the investigation.

File paths are given as they exist in the repository today (e.g. the deterministic engine lives at `src/projection_stages/deterministic_engine.py`, not at the repository root). Line numbers were re-verified while writing this report.

---

## 1. Executive summary

This is a mature and unusually serious system. The financial modelling is far better than typical: statutory Social Security phase-in, a real two-year IRMAA MAGI lookback with SSA-44 relief, QCD, ACA premium-tax-credit bridge modelling, the SECURE 2.0 RMD age ramp, §1014 step-up branched by death order, credit-shelter-trust funding, and an exhaustive 81-pair Social Security claim-age sweep driven through the full projection. The test suite is large (313 files) with genuinely good fixture infrastructure. The UI has been iterated on repeatedly and shows it.

The problems are not "this system is bad." They are the accumulated cost of many rounds of consolidation and re-splitting, plus a handful of modelling choices that quietly narrow what the tool can advise. Eight things matter:

1. **The household's cashflow rules are implemented three separate times, and the shipped default engine is the least-exercised one.** The deterministic engine, the vectorized Monte Carlo, and the exact-scalar Monte Carlo each re-derive the same withdrawal/tax mechanism. Config defaults ship `exact_scalar`, but every test fixture and the demo plan ship `quick_vectorized` — so the default path a real user runs is the one the golden master does *not* cover. A documented CI-timeout performance fix (`survivor_buckets`) is silently a no-op on that default path. **Payoff of fixing:** correctness confidence on the path users actually run, plus roughly an order of magnitude of build-time headroom that every other improvement in this report wants to spend.

2. **Two exhaustive strategy sweeps run unconditionally on every build.** A ~30-candidate Roth sweep (which runs even when the user has chosen an explicit policy, purely to populate a disclosure table) and an 81-pair Social Security grid, each candidate costing a full projection plus a 200-simulation Monte Carlo. Under the shipped `exact_scalar` default that is on the order of 20,000 projections per build. **Payoff:** builds get dramatically faster, and the freed budget is exactly what the planner's proposed richer analyses need.

3. **The one lever a financial planner reaches for first — withdrawal sequencing — is not a lever.** The cascade (RMDs → HSA → tax-sensitive pre-tax → taxable/trust → final pre-tax → Roth last → home equity) is enforced by the engine's tax true-up logic and cannot be reordered. *(Corrected on cross-check: the UI is already honest about this; it discloses the fixed cascade verbatim. The actionable defect is the engine limitation, not the copy.)* **Payoff:** a bracket-target hybrid policy would let the tool model what most CFPs actually implement.

4. **The Executive Summary publishes recommendations that fire on boolean toggles, and one fabricated dollar figure.** The credit-shelter-trust recommendation fires whenever `cst_enabled` is false, regardless of estate size, and its savings number is computed as `sheltered * 0.08` — a flat 8% with no reference to whether the estate exceeds any exemption at all. **Payoff:** removes the single largest professional-credibility risk in the deliverable.

5. **Roth conversions hard-stop before the primary member's RMD age**, excluding the two highest-value conversion windows (the pre-RMD gap and the widow's-bracket years), and anchoring solely to the primary member's date of birth with no reference to a younger spouse. **Payoff:** materially better conversion recommendations, which is the flagship output of the tool.

6. **"Probability of success" — the headline number of the whole product — appears unglossed on the first screen and 26 pages before its only definition.** The glossary machinery exists and is well designed; it is simply wired to one text field out of five. **Payoff:** the cheapest large usability win available; it is a wiring fix, not new design.

7. **The test pyramid is inverted.** 159 of 313 files carry a `_regression` suffix; only 3 are true unit tests. Core calculation modules (`src/taxes.py`, `src/after_tax.py`, `src/gain_harvest.py`, `src/tlh.py`) have no dedicated unit coverage — their correctness is only provable by running the entire pipeline. Meanwhile the one full-journey end-to-end spec has documented evidence of catching a real production bug nothing else would have found. **Payoff:** every engine refactor in this report becomes safe to attempt.

8. **A 3-column fixed grid overflows horizontally on the most common laptop widths** (~1180–1416px, which covers 1280×800, 1366×768, and non-maximized 1440–1536px screens), largely because a 370px always-visible help column duplicates copy that is already inline on the page. **Payoff:** the product stops looking broken on the majority of screens, for a small CSS change.

---

## 2. Panel findings by discipline

### 2.1 Architecture

> **Panel summary.** The layering intent is real and mostly sound — `src/taxes.py` / `tax_law` as data source, `src/report_compute.py` as orchestration, `src/server/` services with injected I/O. Three structural problems undercut it: core cashflow rules implemented three times, four functions of 600–3,000 lines each owning an entire subsystem apiece, and plan data persisted into four stores re-synced on every field save. On top sits a meaningful amount of provably dead scaffolding.

---

#### A1. Three projection engines — and the shipped default is the least-tested
*impact: critical · effort: XL · cross-check: confirmed, no correction*

**What it is.** The household cashflow and withdrawal rules exist in three independent implementations, and the one configured as the shipping default is not the one the tests exercise.

**Evidence.**
- `src/projection_stages/deterministic_engine.py:66` — `run_deterministic_projection_stage`, 3,073 lines in a 3,139-line file.
- `src/planning_engines.py:4586` — `_mc_vectorized_projection`, 497 lines.
- `src/planning_engines.py:3495` — `monte_carlo_exact_scalar`, 575 lines; its own docstring admits it re-derives the vectorized mechanism.
- `src/data_io.py:1736-1743` — defaults `mc_engine_mode` to `exact_scalar` (from CSV value `advanced_exact_scalar`), while `tests/fixtures/sample_plan_frozen/client_policy.csv` and `input/demo/client_policy.csv` both ship `quick_vectorized`.
- `monte_carlo()` accepts `survivor_buckets` — a real, documented CI-timeout performance fix — but the `exact_scalar` branch drops the argument entirely (`monte_carlo_exact_scalar` has no such parameter). The fix is a no-op on the shipped default.

**Options.**

| Option | Tradeoff |
|---|---|
| 1. Retire exact-scalar; vectorized becomes the single MC path | Simplest end state. Loses the independent oracle that can catch vectorization bugs. |
| 2. Keep both; flip the default to vectorized; demote exact-scalar to a test-only validation oracle behind a fidelity-tolerance test | Cheap, immediate, keeps the oracle. Does not reduce the three-implementations maintenance load. |
| 3. Unify on one rule kernel with two drivers (scalar and array) | Correct destination. XL effort; touches the highest-risk code in the system. |

**Recommendation: Option 2 now, Option 3 as the destination.** Flipping the default and adding a tolerance test costs days and immediately aligns "what ships" with "what is tested". Option 3 is the right architecture but should follow the tax-kernel extraction (A2), not precede it.

**Risk.** Flipping the default changes every projection number a real user sees. The frozen golden master will *not* catch it, because the golden master already runs vectorized. This needs an explicit before/after diff on the demo plan and financial sign-off, not just a green suite.

---

#### A2. `run_deterministic_projection_stage` is one 3,073-line function owning fourteen behaviours
*impact: high · effort: XL · depends on: A9 · cross-check: confirmed, no correction*

**What it is.** A single function is the entire deterministic engine. A pipeline module exists that names the fourteen stages, but implements none of them.

**Evidence.** `src/projection_stages/deterministic_engine.py:66`, spanning nearly the whole 3,139-line file. `src/projection_pipeline.py` declares 14 stages in `DEFAULT_STAGE_ORDER`, but `STAGE_IMPLEMENTATIONS` at `src/projection_pipeline.py:81` is an empty dict never written to — verified: `implemented = stage_summary.stage in STAGE_IMPLEMENTATIONS` at line 147 can only ever be false.

**Options.**

| Option | Tradeoff |
|---|---|
| 1. Extract the pure tax kernel first (bracket / IRMAA / LTCG closures) into a `tax_kernel.py` | Cheap, low-risk, and it is the same work A6 needs. Does not shrink the function much by line count. |
| 2. Introduce an explicit `YearState`, split the loop body into real registered stage callables incrementally, golden-master-gated at each step | The real fix. Long, and each step carries silent-wrongness risk. |
| 3. Leave it; invest in characterization tests instead | Cheapest. Accepts the function as permanent and makes every future change expensive. |

**Recommendation: Option 1 first, then Option 2 incrementally.** Option 1 is the shared prerequisite with A6 (see §3) and pays for itself immediately.

**Risk.** Circular tax/withdrawal true-ups mean a naive cut is *silently wrong* rather than loudly broken. Every step must be golden-master-gated.

---

#### A3. Plan data lives in four stores re-synced on every field save
*impact: high · effort: L · cross-check: confirmed, no correction*

**What it is.** Saving one field writes four representations of the same plan.

**Evidence.** `src/server/app_core.py:706-757` writes both the SQLite `client_files` table and `input/*.csv`. `src/server/app_core.py:1686-1751` documents a third store, `local_store.plan_snapshots` — the one `load_active_config()` actually reads — and records a real, reverted attempt to remove a sync that broke `test_real_build_journey_reflects_a_user_edited_input`, at a measured ~200ms per saved field. `src/config_backend.py` adds a fourth representation (JSON/YAML export). All four are refreshed per save via `_sync_config_backends()`.

**Options.**

| Option | Tradeoff |
|---|---|
| 1. Collapse the two SQLite stores into one | Removes the real duplication. Touches the path that determines which config a build reads. |
| 2. Retire the JSON/YAML backends outright (untested, user-switchable, nothing reads them under shipped config) | Cheap and safe. Removes a user-visible switch — confirm nobody uses it. |
| 3. Keep all four; add a consistency-check test | Cheapest. Institutionalises the 200ms-per-field cost. |

**Recommendation: Option 2 first, then Option 1.**

**Risk.** Option 1 touches the config-resolution path; a mistake means silent stale-data builds — the exact failure already observed once and reverted.

---

#### A4. Two unbounded strategy sweeps run on every build
*impact: high · effort: M · depends on: A1 · cross-check: confirmed, no correction*

**What it is.** Every build runs two exhaustive sweeps, each re-implementing the same enumerate/evaluate/rank pattern, and one of them runs even when its result cannot change the plan.

**Evidence.** `optimize_roth_conversion_strategy` scores ~30 candidates, each via a full `project()` plus a 200-simulation `monte_carlo`. `src/reporting/sheets_strategy.py` runs a 9×9 = 81-pair Social Security claim-age grid, each also with a 200-sim MC. Under the shipped `exact_scalar` default each 200-sim MC is 200 further full projections — on the order of 20,000 projections per build from these two sweeps alone. `src/report_compute.py` confirms the Roth sweep runs even when the user has picked an explicit policy, purely to populate a disclosure table.

**Options.**

| Option | Tradeoff |
|---|---|
| 1. Gate sweeps on need — full set only when optimizing; explicit policy gets policy + a small fixed comparison set; SS grid becomes coarse-then-refine | Biggest speed win. Coarse-then-refine can in principle miss a non-convex optimum. |
| 2. Extract a shared sweep runner (enumerate / evaluate / rank / disclose) used by all three sweep sites | Removes the triplicated pattern; makes gating a one-place change. Refactor without immediate user-visible benefit. |
| 3. Make sweeps async / on-demand, off the synchronous build path | Best perceived latency. Adds another artifact-drift surface to a system that already struggles with it. |

**Recommendation: Option 2, with Option 1's gating implemented inside it.** Avoid Option 3.

**Risk.** Reducing the SS grid or the Roth candidate set changes which strategy the plan *recommends*. Validate against the golden master **and** financial sign-off, not code review alone.

---

#### A5. `parse_client` is a ~1,940-line function, and `data_io` also owns projection validation
*impact: high · effort: L · cross-check: confirmed — with the correction that the engine callback is a **documented deliberate compromise**, not an overlooked layering violation*

**Evidence.** `src/data_io.py:638` — `parse_client`, ~1,942 lines. It calls back into `src/report_compute.py` (deliberately, per an in-repo comment, to avoid an import cycle while preserving synchronous behaviour), which itself calls the real engine — so parsing still triggers preliminary `project()` runs despite the general "parsing must not call the engine" rule. `src/data_io.py` additionally owns `validate_projection` / `summarize_validation`, i.e. post-projection validation living in a parsing module.

**Options.**

| Option | Tradeoff |
|---|---|
| 1. Split `parse_client` by config domain into `src/parsing/` siblings (household, accounts, income, spending, tax_policy, insurance_estate, modules); move validation out | Correct shape. Large diff; the function sets hundreds of engine keys. |
| 2. Unify the two entry points (CSV `parse_client`, JSON `build_plan_from_json`) behind one normalizer first | Removes a real duplication risk before splitting. Delays the readability win. |
| 3. Narrow scope: finish removing the engine calls from parsing | Small; completes an already-started fix. Leaves the 1,940 lines. |

**Recommendation: Option 3 immediately, then Option 1.**

**Risk.** Split one section at a time, golden master green after each.

---

#### A6. The LTCG bracket-stacking rule is implemented three times with two different inflation indices
*impact: high · effort: M · cross-check: confirmed, **with correction** — three full re-implementations, not four. `src/gain_harvest.py` mirrors only the 0%-bracket-top edge, deliberately and per its own docstring; it is not a fourth copy. The two-different-inflation-index claim is confirmed accurate.*

**Evidence.** `src/core.py:1295-1313` (`ltcg_tax_on_gain`) and `src/projection_stages/deterministic_engine.py:476-488` (`_ltcg_tax_on_gain_path`) are the same algorithm but index bracket tops by **different config fields** — `irmaa_inflator` versus `brk_inf` / `fed_tax_bracket_inflator` — which are independently settable and do diverge in at least one fixture (0.028 vs 0.02). `src/tlh.py:159-172` (`_ltcg_marginal_rate`) is a third independent copy.

**Options.**

| Option | Tradeoff |
|---|---|
| 1. One function in a new `tax_kernel.py`, injected bracket factor, sourced from `src/taxes.py`'s centralized tables | Correct, and shares work with A2. If the indices genuinely diverge today, unifying changes reported LTCG tax. |
| 2. De-duplicate only the pure copies (`core` / `tlh`), leave the engine closure alone | Smaller diff. Leaves the inflation-index divergence — the actual defect — in place. |
| 3. Add a cross-implementation equivalence test first; defer the refactor | One hour, and it tells you whether this is a latent bug or a live one. Not a fix. |

**Recommendation: Option 3 as a one-hour diagnostic, then Option 1.** The diagnostic determines whether Option 1 is a refactor or a bug fix, which changes the sign-off it needs.

**Risk.** Requires golden-master regeneration and financial sign-off if the indices diverge in shipped configs.

---

#### A7. The frontend's "ES module" decomposition has zero imports in its largest file
*impact: high · effort: L · cross-check: confirmed, **with correction** — `dashboard_decomp_row_model.js` does export its own definitions; its `window.*` usage is specifically to reach `dashboard.js`, which exports nothing. This is a real but one-directional coupling, not "global-only across all files".*

**Evidence.** `frontend/index.html` loads 25 scripts (22 as `type=module`) in a hand-maintained order. `frontend/js/dashboard.js` (7,503 lines) contains zero `import` statements; other modules reach it only via `window.*`. `frontend/js/modules/phase3_module_manifest.js` documents a real 2026-07-22 outage caused by script load order — converting one file to deferred-module execution broke boot sequencing — now guarded by a regression test.

**Options.**

| Option | Tradeoff |
|---|---|
| 1. Convert leaves to real imports bottom-up, starting with shared helpers, shrinking the ordered script-tag list incrementally | No new tooling; each step independently verifiable. Slow; `dashboard.js` is last and hardest. |
| 2. Introduce a bundler (esbuild/rollup), single entry, one script tag | Architecturally correct and fastest to a clean end state. Adds a build step to a deliberately build-free desktop app. |
| 3. Keep globals but make the contract explicit via one `window.RP` namespace + a lint check | Cheapest; documents reality. Does not fix the load-order fragility. |

**Recommendation: Option 1.** Option 2 is the better architecture in the abstract but conflicts with a standing product constraint (no build step). If that constraint is negotiable, Option 2 becomes the better answer — this is a decision for the reader, and it is listed in the appendix.

**Risk.** Script-order changes are exactly what caused the prior outage. The load-order regression test and the e2e specs are the real safety net.

---

#### A8. Provably dead scaffolding
*impact: medium · effort: S · depends on: A11 · not sent for cross-check (evidence was exhaustive full-repo-grep verified)*

**Evidence.** `src/server/features/` — eight modules (`admin.py`, `build_results.py`, `plan_data.py`, `pricing.py`, `spending.py`, `strategy_assets.py`, `ytd.py`), zero importers. `src/server/__init__.py`'s `_ensure_test_url_map` (unreachable fallback). `src/dashboard_ui/template.py` — `STATIC_DIR` points at a directory that does not exist, so its exports are permanently `""`. `src/core.py`'s dead events section (17 unused namedtuples plus `EventLog`) and its unused `Invariant` / `INVARIANTS` / `validate_projection` framework. Roughly 15 other unreferenced single functions.

**Options.** (1) Delete all in one pass. (2) Delete in three risk-tiered tranches. (3) Mark deprecated, delete next release.

**Recommendation: Option 2.** The `src/server/features/` tranche is unarguable and should go first.

**Risk.** Low — but `from ..core import *` means the star-import surface must be grep-verified before removing any `core.py` name.

---

#### A9. The 14-stage projection pipeline is decorative
*impact: medium · effort: S · not sent for cross-check*

**Evidence.** `src/projection_pipeline.py:81` — `STAGE_IMPLEMENTATIONS` is never written to; the "stage contract completed" branch at line 147 is unreachable; every stage emits `event_type="inlined"`. The module's own comment admits this.

**Options.** (1) Keep the facade, delete the dead branch, drop the unnecessary per-row dict copy. (2) Make the registry real, starting with one stage (the tax kernel). (3) Delete the module entirely.

**Recommendation: Option 1 now, Option 2 as A2 proceeds. Do not delete the module** — its stage list is the best available map of the engine and is the natural target shape for A2.

---

#### A10. An 80-block dual-import shim whose fallback cannot fire
*impact: medium · effort: M · not sent for cross-check*

**Evidence.** AST-verified: 80 `try/except ImportError` blocks across 41 files, all importing identical name sets (zero drift today). The fallback branch is unreachable in every shipping configuration — the PyInstaller spec and all tools/tests set `sys.path` such that relative imports always succeed. The broad `except ImportError` can mask genuine transitive import errors.

**Options.** (1) Mechanical removal via codemod, keep the relative branch, add a lint rule against the pattern returning. (2) Narrow the `except` to an `if __package__` guard instead of removing. (3) Do nothing.

**Recommendation: Option 1.** It is mechanical, fully covered by the existing suite, and zero drift today is precisely the right moment — drift is what would make it expensive later.

---

#### A11. `workbook_common` is a barrel that hides the reporting layer's engine dependency
*impact: medium · effort: M · not sent for cross-check*

**Evidence.** `src/reporting/workbook_common.py` (1,086 lines) star-imports `core`, re-exports stdlib and openpyxl names, and re-exports both `report_compute` **and** the projection engine (`project`, `monte_carlo`, `optimize_roth_conversion_strategy`, `run_scenario`). Sheet builders import engine functions *through* this barrel, hiding the real dependency. It also contains a duplicate `__all__` and stale comments referencing a star-import pattern that does not exist in the reporting package.

**Options.** (1) Split into `workbook_style.py` / `workbook_layout.py` / `workbook_registry.py` and delete the engine re-exports. (2) Keep one module; remove only the pass-through re-exports; fix the duplicate `__all__` and the stale comments. (3) Fix only the stale comments.

**Recommendation: Option 2** — achieves the layering clarity for a much smaller diff.

---

#### A12. The browser results view reverse-engineers the app's own generated .xlsx
*impact: medium · effort: L · cross-check: confirmed, **with correction** — the registered sheet-builder count is closer to 32 than "~25"; the core ratio holds*

**Evidence.** `src/detailed_results.py` (1,005 lines, roughly 900 of them parsing logic) infers cell kinds from openpyxl number formats, guesses section boundaries from row shape, and reconstructs charts from a hidden sheet. `src/results_model.py` — the semantic sidecar meant to replace this — covers only 6 pages against 32 registered sheet builders. Most of the Results Explorer is still rendered by scraping Excel.

**Options.** (1) Extend `results_model` page by page, deleting parser paths as coverage grows. (2) Invert the dependency — build the model first, render Excel from it. (3) Freeze the scraper, cap the model at 6 key pages, document the boundary.

**Recommendation: Option 1, prioritized by which sheets users actually open.** Option 2 is the right end state but is a reporting-layer rewrite; it should not be started until the engine work has settled.

---

#### A13. `report_spec` is computed twice per projection and read by nothing
*impact: low · effort: S · not sent for cross-check*

**Evidence.** `src/report_compute.py` and `src/result_contract.py` each independently derive `report_spec`. Grep finds zero consumers outside two test files; `report_spec.py` has no renderer.

**Options.** (1) Delete entirely. (2) Compute once and keep it — fixes the double-derivation defect at minimal cost. (3) Make it load-bearing by pointing the Results Explorer at it.

**Recommendation: Option 2**, deferring the delete-or-keep decision to whoever owns the reporting roadmap (see appendix).

---

#### A14. UI regression tests assert against commented-out code
*impact: medium · effort: S · depends on: A8 · not sent for cross-check*

**Evidence.** `src/dashboard_ui/template.py:22-52` is a fully commented-out block (`UI_COMPONENT_MANIFEST_FOR_REGRESSION_CHECKS`). Five tests read this file as text and assert on strings that exist **only inside that comment**. Those tests would keep passing if the real frontend feature were deleted entirely.

**Options.** (1) Repoint the five tests at the real `frontend/` files and delete `template.py`. (2) Replace marker-grep with behavioural e2e assertions. (3) Delete the marker tests entirely.

**Recommendation: Option 1 immediately; migrate the highest-value ones to Option 2 over time.** This is the most clear-cut correctness defect in the test suite: five tests currently assert nothing.

> **Architect's own call if only three items are actioned:** A1 (three engines), A3 (four data stores), A4 (unbounded sweeps).

---

### 2.2 Usability

> **Panel summary.** A mature single-page 3-column dashboard (nav | content | help) with real, iterative density fixes already in place. Remaining problems are structural: a fixed-width grid that overflows on common laptops, a help column duplicating on-page copy, deep multi-click disclosure with no exceptions shortcut, and related tasks split across distant nav destinations forcing lossy round trips.

---

#### U1. The fixed 3-column grid overflows on the most common laptop widths
*impact: high · effort: S · depends on: U2 · cross-check: confirmed, **with correction** — the actual overflow window is ~1180–1416px, not 1180–1460px*

**Evidence.** `frontend/css/dashboard.css:3` — `main{max-width:1760px; grid-template-columns:310px minmax(700px,1fr) 370px; gap:18px}`, with the only breakpoint at `max-width:1180px` (single-column collapse). Minimum width before overflow is 310 + 370 + 2×18 + 700 = **1416px**. Between 1180px and 1416px the page overflows horizontally. That band covers 1280×800, 1366×768, and non-maximized windows on 1440–1536px laptops.

**Options.** (1) Add an intermediate breakpoint at ~1416–1460px that drops the help column. (2) Make the grid fluid (minmax-based proportional columns). (3) Do nothing; rely on browser scrollbars.

**Recommendation: Option 1, combined with the U2 help-pane fix.** Option 2 is more elegant but risks reflowing every page's layout, which is a much larger visual-regression surface for the same user-visible benefit.

---

#### U2. The always-visible 370px help column duplicates the inline page description
*impact: medium · effort: M*

**Evidence.** `frontend/js/dashboard.js:4056` already inlines `st.desc` / `st.help` into the on-page `.question` box; `showStepHelp()` independently fills `#helpPanel` from `STEP_HELP` with a longer, overlapping write-up. The column is a fixed 370px sticky pane — a permanent ~21% tax on content width for content the user has already read.

**Options.** (1) Remove the fixed column; fold help into an on-demand popover / `<details>` next to the title. (2) Make the pane collapsible with remembered state. (3) Split the content so the two surfaces do not overlap (see D5).

**Recommendation: Option 1** — the inline box already carries the load-bearing summary. Note that D5 (documentation panel) recommends *differentiating* the two texts rather than removing one; §3 resolves this apparent tension.

---

#### U3. No jump-to-exceptions view in the spending drill-down
*impact: high · effort: S · cross-check: confirmed*

**Evidence.** `frontend/js/spending_dashboard.js:242-246` computes over/watch/ok status at *every* level, but reaching category detail requires two sequential clicks per group (`toggleSpendingType`, then `toggleSpendingGroup`) — up to 24 disclosures for a 6×4 household. The only bulk affordance is "Collapse all". The data needed to skip straight to the problems is already computed and thrown away.

**Options.** (1) Add an "Exceptions" quick-filter chip that auto-expands/filters to non-ok rows, reusing the existing `statusFor()` data. (2) Auto-expand groups and types containing any flagged category on first render. (3) Add a compact top-of-page exceptions summary table.

**Recommendation: Option 1** — least code, most consistent with the existing collapse/expand model, and it is opt-in so it cannot annoy a user whose plan has no exceptions (which Option 2 could).

---

#### U4. Roth conversion, Social Security timing and work income live on three distant pages
*impact: high · effort: L · cross-check: confirmed, **with correction** — the "coordinate" language lives in the step-definition `help` field, not `STEP_HELP` as originally cited; the underlying UX problem is confirmed*

**Evidence.** The `income_work` and `income_retirement` steps carry a `helpLink` to `distribution_strategy`, a distant page under Strategy; their help text explicitly instructs the user to "coordinate" the two pages. There is no inline summary of the other page's current values, and each navigation fully re-renders `#mainPane`, losing context.

**Options.** (1) Add a compact read-only "coordination summary" card inline on both pages showing the other page's values, with one click-through to edit. (2) Let the Planning Workbench (which already exists for baseline-vs-change-set comparison) become the coordination surface. (3) Physically relocate Roth conversion under People and Income.

**Recommendation: Option 1** — lowest-risk cut to full-navigation round trips. Option 2 is attractive but the Workbench is explicitly browser-local and never mutates the saved plan (see F13), so it cannot be where a user *edits* these values. Option 3 moves the problem rather than solving it, since allocation and spending also interact.

---

#### U5. Allocation policy is hidden behind a collapsed disclosure on the allocation page
*impact: medium · effort: S · depends on: U1 · cross-check: confirmed exactly*

**Evidence.** `frontend/js/dashboard.js:4123-4124` — the `allocation_assets` step wraps `renderAllocationPolicy()` in a `<details>` element with no `open` attribute. It is collapsed by default on the very page users navigate to in order to set allocation policy.

**Options.** (1) Default the `<details>` open. (2) Remember open/closed state per user via `localStorage`. (3) Promote to a two-pane layout (recommendation | policy) instead of a nested disclosure.

**Recommendation: Option 1** — a one-line, zero-risk fix. Do this on day one.

---

#### U6. The build → review → download workflow spans three tab clicks that the header already bypasses
*impact: medium · effort: M*

**Evidence.** `renderReportsAndReview()` switches between Preflight / Build / Impact / Results / Downloads / Plan Data Review tabs; the intro copy describes a four-tab sequence, while the header's one-click Download buttons already bypass it entirely. The documented workflow and the actual fastest path disagree.

**Options.** (1) Merge Preflight readiness into the Build screen. (2) Add a persistent status strip across all tabs. (3) Leave as-is and rely on the header shortcut for experienced users.

**Recommendation: Option 1** — removes a whole tab from the most common action, and brings the copy back in line with reality.

---

#### U7. Wide-viewport whitespace in field lists
*impact: low · effort: S*

**Evidence.** `frontend/css/dashboard.css:45` caps `.field-list` at `max-width:1180px`; the auto-fit third-column track only forms at ≥1760px `main` width. Between roughly 1180px and 1760px of available content-column width, rows stop expanding and the space goes unused.

**Options.** (1) Tie `.field-list` max-width to the actual content-column width. (2) Use the freed width for a persistent KPI summary strip. (3) Accept it as an intentional readability ceiling.

**Recommendation: Option 1** — recalibrate the trigger to the content column rather than the outer container. Low priority.

---

### 2.3 Documentation and content

> **Panel summary.** The plain-language machinery — `TERM_NOTES`, `ACRONYM_DEFINITIONS`, per-sheet "What that means" notes, the PDF truncation marker — is genuinely well designed. The problems are wiring and placement, not design.

---

#### D1. The glossary hook reaches one text field out of five
*impact: critical · effort: S · cross-check: confirmed exactly (minor line correction only)*

**What it is.** The product's headline metric appears unglossed on the first screen a user sees, 26 pages before its only definition, with no fallback anywhere.

**Evidence.**
- `frontend/js/dashboard.js:448-469` defines `TERM_NOTES` and `addParentheticals`.
- `addParentheticals` is applied **only** to `st.intro`, at `frontend/js/dashboard.js:4053` — verified as the only substantive call site repo-wide.
- `pageHelp()` (`frontend/js/dashboard.js:962-970`) renders its `meaning` / `connections` / `options` / `impact` fields directly through `esc()`, never glossed.
- "Probability of success" appears unglossed at `frontend/js/dashboard.js:507` (the `income_retirement` step — 5th of 45), while its only definition sits on `monte_carlo_options` (31st step).
- The home-page KPI tile "Probability of Success" (`frontend/js/dashboard_decomp_home_panels.js:36`) has no tooltip at all, and `ACRONYM_DEFINITIONS` / `src/glossary.py` has no entry for the term either — so no fallback mechanism reaches it.

**Options.** (1) Extend the existing glossary hook to `pageHelp()`'s four fields, and add a tooltip to KPI tile labels using the same `TERM_NOTES` map. (2) Fix only the worst offender (the home KPI tile). (3) Reorder navigation so the definition comes first.

**Recommendation: Option 1.** The mechanism, the term list and the regex all already exist. This is a wiring fix, not new design work, and it has the highest ratio of user benefit to engineering cost anywhere in this review.

---

#### D2. "Advisor-ready" is used as a quality label but never defined
*impact: medium · effort: S · depends on: D1*

**Evidence.** `frontend/js/dashboard.js` lines 275, 344, 646, 2178 and 6754 all use the term; `TERM_NOTES` has no entry for it. A user with no advisor has no way to know what it promises.

**Options.** (1) Add it to `TERM_NOTES` alongside the D1 fix. (2) Replace the term with a concrete phrase instead of defining it.

**Recommendation: Option 1**, since the same code path is being touched anyway. Option 2 is defensible and arguably better writing — flagged in the appendix.

---

#### D3. Ten "Source of truth" banners expose storage implementation nouns
*impact: high · effort: M · cross-check: confirmed exactly*

**Evidence.** `frontend/js/dashboard_source_truth_banners.js:3-24` defines ten banners (`SOURCE_TRUTH_STEPS`), rendered via `sourceTruthHtml()` / `insertAfterPaneHead()` on pages including holdings and system_configuration. They contain verbatim "SQLite", "adapter", and literal CSV filenames (`client_holdings.csv`, `system_config.csv`) with no rewording for an end user. These answer no question a retiree has.

**Options.** (1) Delete the banner wherever it carries no actionable fact (4–5 pages that state only storage mechanics). (2) Rewrite all ten in outcome language ("changes here save automatically" / "this is a preview until you Save"). (3) Collapse to a generated one-liner derived from two booleans per step.

**Recommendation: delete on the pages that state only mechanics; rewrite in outcome language the two that carry a genuine staleness warning (`build_impact`, `review`).** Option 3 is tempting but a generated one-liner will read as boilerplate and be ignored, which is the same outcome as deleting it for more code.

---

#### D4. The Executive Summary leaks an internal config path
*impact: medium · effort: S*

**Evidence.** `src/reporting/sheets_summary_builder.py:261-276`, specifically line 271: `"Auto Depreciation: Straight-line over 7 years (CSV: Other Assets > Autos > depreciation_years)"`. This is on Sheet 1 of every build — the first page anyone opens.

**Options.** (1) Delete the config-path parenthetical. (2) Relocate the technical pointer to the QC/Reference sheet, already the designated home for maintainer detail. (3) Rename the section and audit the other three bullets at the same time.

**Recommendation: Option 2 plus Option 3.** The pointer is genuinely useful to a maintainer — move it, do not destroy it — and while the block is open, audit the other bullets, one of which ("Release Notes") is misnamed for what it contains.

---

#### D5. Two independently authored blocks narrate the same page
*impact: medium · effort: M*

**Evidence.** For `household_people`, `STEPS[].intro` and `STEP_HELP`'s `connections` field both describe birth-date effects on Social Security, RMDs, Medicare, survivor status and estate, in near-identical but separately written prose, displayed in two different UI locations. Every edit must be made twice.

**Options.** (1) Merge into one source of truth. (2) Differentiate by design: intro = "what to enter here", help panel = "what this affects elsewhere". (3) Leave as-is.

**Recommendation: Option 2 as the pragmatic middle path; full merge (Option 1) only where the overlap is verbatim.**

---

#### D6. The one README marked "shipped to end users" is written for a developer
*impact: low · effort: S*

**Evidence.** `PROJECT_MANIFEST.md` states that `documentation/readme/` is "shipped to end users"; the actual `README.md` content is Python CLI commands (`python main.py`, `python -m pytest`) that are meaningless to someone running a packaged executable.

**Options.** (1) Split by audience — add a two-line end-user section above the dev commands. (2) Leave it, since real exposure is limited.

**Recommendation: Option 1.** Cheap; low priority.

---

### 2.4 Quality and test suite

> **Panel summary.** A large (313-file) regression-heavy suite with genuinely good fixture infrastructure — `conftest.py` workspace isolation, a frozen plan fixture, provenance-gated golden masters. The weak spots cluster at the edges: true unit tests are nearly absent, so core financial math is only provable by running the whole pipeline; admin/roth UI "fix log" tests duplicate and partially rot; only one of thirteen e2e specs exercises the full journey; negative paths are thin.

---

#### Q1. Admin UI "fix log" tests duplicate and partially rot
*impact: medium · effort: M*

**Evidence.** Eight `admin_*_functional.py` files each re-read the admin HTML, CSS and JS and assert overlapping literals about the same nav-refactor lineage; one file already documents a prior byte-identical removal.

**Options.** (1) Consolidate into one admin-UI structure file, keeping only the newest assertion per superseded literal. (2) Leave as historical layers and add a mechanical dedupe guard. (3) Do nothing.

**Recommendation: Option 1** — the files are small and low-risk to merge, and the precedent already exists in-repo.

---

#### Q2. Byte-identical assertions duplicated across two Roth UI test files
*impact: low · effort: S · depends on: Q1*

**Options.** (1) Merge the two files. (2) Keep them separate and remove the duplicated literal.

**Recommendation: merge**, following the Q1 precedent.

---

#### Q3. Core financial calculation modules have almost no unit tests
*impact: high · effort: L · cross-check: confirmed exactly*

**Evidence.** Only 3 of 313 test files carry a `_unit.py` suffix. `src/taxes.py`, `src/after_tax.py`, `src/gain_harvest.py`, `src/tlh.py`, `src/allocation_policy.py` and `src/withdrawal_strategy_comparison.py` have zero dedicated unit test files — and `src/tlh.py` and `src/withdrawal_strategy_comparison.py` have zero test references *at all*. Their correctness is asserted only through full-pipeline golden-master regressions, which means a wrong number is detected but never localized.

**Options.** (1) Add targeted unit suites per calc module with hand-computed expected values. (2) Extract characterization tests from existing golden-master fixture data — faster, and reuses values already trusted. (3) Accept the golden master as the de facto unit layer.

**Recommendation: Option 2 first, then Option 1 for the highest-risk modules (`src/taxes.py`, `src/gain_harvest.py`).** Characterization tests pin current behaviour cheaply and are exactly the safety net the engine refactors (A1, A2, A6) need. Hand-computed values then upgrade the highest-risk modules from "this is what it does" to "this is what it should do".

---

#### Q4. Only one true end-to-end journey spec
*impact: high · effort: M · depends on: Q5 · cross-check: confirmed exactly*

**Evidence.** Thirteen Playwright specs exist; only `build-and-results.spec.js` drives the full data-in → build → results journey. Its own header comment records that it found a genuine, previously undetected server-side bug (a workspace-root path bug) purely by running in a real browser. The other twelve cover narrower UI mechanics. Nothing covers new-plan creation, admin config changes, or build-failure UI states.

**Options.** (1) Add three targeted specs: new-plan-creation, admin-config-change, build-failure. (2) Extend `build-and-results.spec.js` into one longer session. (3) Rely on Node frontend tests plus contract tests as proxies.

**Recommendation: Option 1.** The cost/benefit here is not speculative — this is the single place in the suite with documented evidence of catching a real bug nothing else would have. Option 2 makes one spec slow and hard to diagnose when it fails.

---

#### Q5. Negative and failure paths are thinly covered
*impact: high · effort: M*

**Evidence.** Only 24 of 313 files touch malformed/invalid/corrupt input or `raises(` handling, and most of those are tolerant-parsing tests rather than genuine rejection paths. No test asserts what the *user sees* when `parse_client` or `build_plan_from_json` receives structurally invalid input, or when a build subprocess crashes mid-run.

**Options.** (1) Add dedicated error-path test files per layer (malformed input; build-failure surfacing). (2) Extend existing contract tests with negative cases.

**Recommendation: Option 1 for build-failure surfacing (highest user-visible impact), Option 2 for input validation.**

---

#### Q6. "Regression" is half the suite and conflates three different things
*impact: medium · effort: M · depends on: Q1 · cross-check: confirmed exactly*

**Evidence.** 159 of 313 files end in `_regression.py` — 51% of the whole suite, 75% of the typed subset. The label covers golden-master comparisons, grep-based UI literal pinning, and genuine bug-fix regression tests, with no way to tell them apart. `documentation/CLAUDE.md` confirms the suffix convention is "not separately enforced" beyond a mechanical tracking-id check.

**Options.** (1) Split into `_regression` (documented prior bug fix) versus `_functional` (structural/DOM checks) via rename. (2) Add a mechanical suffix-shape checker. (3) Leave the taxonomy loose.

**Recommendation: Option 1** — a low-risk rename pass with a clear, checkable rule. Add Option 2 afterwards to stop it re-inflating.

---

#### Q7. Only one file is typed "integration", and it is not one
*impact: medium · effort: M · cross-check: confirmed exactly*

**Evidence.** `tests/test_engine_integration.py` is the only `*_integration.py` file, and it calls engine functions directly via a `base_cfg` fixture — never through the server/HTTP layer, never through a real build. The genuine gap between unit-level calls and full subprocess builds is untested.

**Options.** (1) Add real cross-layer integration tests (route handler → service layer → engine → serialized response, without the subprocess build). (2) Rename the existing file to match its real shape.

**Recommendation: Option 1** — do the rename too, but the rename alone leaves the gap.

---

#### Q8. Golden-master and fixture infrastructure is strong — preserve it
*impact: low · effort: S*

**Evidence.** `conftest.py`'s workspace redirect and write guard, provenance-gated pins, and the synthetic-versus-frozen fixture split.

**Recommendation: leave it alone and use it as the template for other consolidation work.** This is explicitly *not* a target for reduction; several recommendations in this report depend on it.

---

#### Q9. HSA and YTD test clusters warrant the same audit
*impact: low · effort: S*

**Evidence.** HSA (11 files) and YTD (6 files) clusters resemble the admin/roth pattern but were **not** confirmed duplicative in this pass.

**Recommendation: schedule as a fast follow-up using the same method. Do not act without first confirming actual duplication.**

---

#### Q10. Target test pyramid
*impact: high · effort: XL · depends on: Q1–Q7 · cross-check: confirmed — count and shape verified*

**Current shape:** regression 159, functional 36, contract 13, smoke 1, unit 3, integration 1, plus 13 e2e and 12 Node frontend specs. Nearly inverted from healthy.

**Target shape:** unit ~40–60 (one per pure calc module); integration ~10–15 (service↔engine seams); golden-master/contract kept at ~170 (do **not** shrink it — but split the DOM-literal checks out of the `_regression` suffix); e2e 18–20 (up from 13).

**Recommendation: execute Q1–Q7 independently, prioritized by impact. Do not attempt this as a single XL rewrite project.** The target is a direction, not a milestone.

---

### 2.5 Financial planning (CFP-level)

> **Panel summary.** Very little a CFP would ask about is simply absent. The weaknesses are that the first lever a planner pulls is hardcoded; the Executive Summary's recommendation table fires on booleans rather than the household's numbers and publishes a fabricated dollar figure; Roth conversions stop before the two most valuable windows; the heir-side tax that dominates the Roth objective is biased low in two independent directions; and state coverage is 13 states with only Illinois estate tax actually computed.
>
> **The planner's closing note:** *the tool models the household's future with real rigor and then hands the planner a narrower set of decisions than the modelling could support.*

---

#### F1. Withdrawal order is not a lever
*impact: critical · effort: L · cross-check: confirmed, **with an important correction** — the frontend control (`frontend/js/dashboard.js`, `renderWithdrawalOrderTable`, ~lines 2911–2918) explicitly and honestly discloses the fixed cascade verbatim. It is **not** misleading. The engine limitation itself is fully confirmed.*

**What it is.** The withdrawal cascade draws pre-tax before taxable and cannot be reordered by the user. The app is honest about this; the limitation is nonetheless a real constraint on the planning the tool can do.

**Evidence.** `src/taxes.py:474-494` documents the fixed, engine-enforced order: RMDs → HSA → tax-sensitive pre-tax → taxable/trust → final pre-tax/HSA → Roth last → home equity. `account_draw_priority` (`src/data_io.py:2336-2341`) only reorders accounts *within* an already-tax-type-filtered bucket (`src/core.py:213-233`) and can never move taxable ahead of pre-tax. `src/withdrawal_strategy_comparison.py` states outright that named strategies are a separate, lower-fidelity tool because the true-up logic assumes this exact order.

**Options.**

| Option | Tradeoff |
|---|---|
| 1. Make bucket order a real input by restructuring the tax true-up to solve iteratively for any order | Highest payoff and highest risk. An engine rewrite touching the most delicate code in the system. |
| 2. Add a bracket-target hybrid policy — fill ordinary income to a target bracket from pre-tax, then draw taxable — without full reordering | Covers the policy most CFPs actually implement, and fits inside the existing cascade rather than replacing it. Does not support arbitrary user-specified orders. |
| 3. *(Superseded by cross-check — the UI copy is already accurate; no fix needed here.)* | — |

**Recommendation: Option 2 now; Option 1 on the roadmap.** Note explicitly for the reader: the original panel finding proposed a UI/copy fix as part of this item. Cross-check established that the copy is already correct, so **the only actionable work here is in the engine.** Do not spend effort rewording the withdrawal-order screen.

**Risk.** Any change moves golden-master pins and interacts with the Roth optimizer's bracket-capping assumption.

---

#### F2. Executive Summary recommendations are not materiality-gated, and the CST savings figure is fabricated
*impact: critical · effort: M · cross-check: confirmed exactly — both the boolean gating and the flat-8% fabricated figure*

**What it is.** The client-facing recommendation table fires on configuration toggles rather than the household's numbers, and attaches a dollar figure that is not computed from anything.

**Evidence.** `src/reporting/sheets_summary_builder.py:214-247` gates the credit-shelter-trust, long-term-care, S-Corp and QTIP recommendations purely on config boolean flags — the CST recommendation fires whenever `cst_enabled` is false, regardless of estate size. There is no reference anywhere in that block to projected estate, income, or exposure. `src/reporting/summary_figures.py:102-108` computes CST savings as `sheltered * 0.08` with a hardcoded `'avg_rate': 0.08`, and contains **no** comparison of gross estate against any exemption. Verified directly in the source.

**Options.**

| Option | Tradeoff |
|---|---|
| 1. Materiality gate plus computed savings, using the household's actual projected estate and the real `illinois_estate_tax()` delta | Correct. Only produces a number for the one state whose estate tax is actually computed (see F5). |
| 2. Demote to a review checklist and drop dollar figures entirely | Safest and fastest. Loses the quantification that makes the summary useful. |
| 3. Rank by computed value and show the top N, with a "reviewed, not material" line for the rest | Best client-facing shape — shows diligence without publishing a wrong number. Needs Option 1's predicates underneath. |

**Recommendation: Option 3, built on Option 1's predicates. Fix the fabricated CST figure standalone and first** — it can ship in isolation and is the highest-severity single item in this report from a professional-liability standpoint.

---

#### F3. Roth conversions hard-stop before RMD age
*impact: high · effort: L · depends on: F4 · cross-check: confirmed exactly, including the ~30-candidate count and the primary-member-only anchoring*

**What it is.** The conversion window closes before the two highest-value conversion opportunities: the late pre-RMD gap years and the survivor's compressed-bracket years.

**Evidence.** `src/planning_engines.py:1668-1685` — `conversion_window_end_year()` anchors solely to the primary member's date of birth, with no reference to a younger spouse's DOB; enforced at line 1863. The ~30 candidate strategies are all constant-rate across the window — none vary by year or phase. The survivor filing-status switch is already modelled elsewhere in the engine but does not extend this window.

*Added by the planner's review pass:* the bracket-target lookup at `src/planning_engines.py:1872` — `top_target = next((hi for _lo, hi, rate in brk if rate == target_rate), 400000)` — falls back to a hardcoded `400000` bracket top whenever the configured `roth_target_rate` matches no bracket rate. That is a silent wrong answer waiting for a rate typo (or a bracket-table edit), and it is worth fixing while item 3.2 is already inside this function.

**Options.**

| Option | Tradeoff |
|---|---|
| 1. Extend the default window to plan end and let the optimizer's existing caps size conversions to zero when unprofitable | Simple and lets the existing machinery do the work. Widens the search space, costing build time (see §3). |
| 2. Add explicit named phase candidates (e.g. "fill 24% until SS claim, then 22% to RMD age") | Matches how planners actually describe strategies, and is cheap to score. Hand-curated, so it can miss cases. |
| 3. Per-year optimization over bracket targets | Theoretically right; computationally heavy and likely infeasible until A1 and A4 land. |

**Recommendation: Options 1 + 2. Defer Option 3.**

**Risk.** Extending the window without the guardrails firing correctly in late years could recommend conversions that raise Medicare premiums. **Verify the guardrail age gate before extending the window**, not after.

---

#### F4. The heir tax rate that dominates the Roth objective is biased low in two directions
*impact: high · effort: M*

**Evidence.** `src/after_tax.py:58-85` — `effective_heir_ten_year_rate()` treats each of ten equal slices as the heir's *only* ordinary income. `per_beneficiary_ten_year_drawdown` is federal-only, with no state tax. Every beneficiary shares one assumed filing status. Every non-spouse beneficiary is treated as subject to the 10-year rule, with no branch for eligible designated beneficiaries (surviving spouse, minor child, disabled or chronically ill, or a beneficiary less than ten years younger) — which is legally incorrect, not merely conservative.

**Options.** (1) Add heir baseline income, state, and beneficiary class per account, all defaulting to zero/current behaviour so existing plans are unchanged. (2) Show the Roth recommendation's sensitivity to the heir rate at three assumptions instead of refining the point estimate. (3) Add eligible-designated-beneficiary classes only — fixes the part that is legally wrong.

**Recommendation: Options 1 + 3 together, with Option 2 as the presentation layer.** This is the single assumption with the most leverage over the flagship Roth recommendation, and it is biased low in two independent ways, so the errors compound rather than cancel.

---

#### F5. Thirteen states, one computed estate tax, and one deliberate hole
*impact: high · effort: L · cross-check: confirmed exactly — 13 states, hard `ValueError` for others, NY genuinely `not_modeled` despite being one of the 13 listed. **Cross-check adds nuance:** `not_modeled` is a deliberate, documented contract designed to avoid publishing a silently wrong number, not an oversight.*

**Evidence.** `reference_data/state_tax.csv` / `STATE_TAX_DEFAULTS` list exactly 13 states; `src/core.py` raises `ValueError` for any other state. `state_estate_tax()` computes a real figure only for Illinois. New York has `estate=True` and `estate_exempt=$6.94M` but `estate_calc='not_modeled'`, returning 0.0 with an explicit disclosure contract.

**Options.** (1) Complete the estate-tax mechanism for NY — the graduated table plus the 105%-of-exemption cliff — and audit the other twelve. (2) Expand to all 50 states at flat-rate income-tax fidelity, keeping `not_modeled` honest for unimplemented estate mechanisms. (3) Move the CA/NY bracket tables into a data-driven, dated reference dataset and extend retirement exclusions to age-tiered.

**Recommendation: Option 1 first, and Option 1 must include the three-year gift add-back** (see §5.4) — otherwise the cliff calculation completes but still under-reports NY estate tax for any household that gifted within three years of death. New York's estate cliff is the highest-consequence single omission among states the tool already claims to support — a household just over the exemption faces a discontinuity the tool currently reports as zero. Then Option 2, with Option 3 as the structure that makes the whole thing maintainable.

---

#### F6. No adoptable spending policy
*impact: high · effort: M*

**Evidence.** `FUNCTIONAL_SPEC.md` states that Guyton-Klinger is "shown for comparison only; it never feeds back into the real plan." `src/planning_engines.py` tracks a shadow portfolio in parallel, but nothing consumes its output as policy. Adaptive spending appears only reactively inside Monte Carlo (cutting by tier when a path runs short). No go-go/slow-go or real-decline logic exists anywhere.

**Options.** (1) Promote guardrails to an adoptable policy selector (fixed real / Guyton-Klinger / floor-ceiling band), running in both engines. (2) Add a simple age-phased real spending curve — discretionary declines X% between ages A and B. (3) Report the shadow more prominently instead of making it adoptable.

**Recommendation: Option 1, with Option 2 as a separate, independent control.** A static-real-spending-forever assumption overstates ruin risk for households with meaningful discretionary spending, because it models a retiree who never adjusts. The size of the effect is household-specific. Either way it affects the headline probability-of-success number directly. *(Wording corrected on the planner's review pass — the original "systematically overstates ruin risk" overclaimed a uniform direction and magnitude.)*

**Risk.** Both options make plans look better. Pair either with **mandatory disclosure of the modelled spending cut's size and duration** — otherwise the tool is trading an honest pessimism for a hidden optimism. Note further that under any policy other than fixed-real, "probability of success" silently changes meaning: it becomes *survived having cut* rather than *funded as asked*, while reporting the same percentage. See §5.4 for the disclosure this requires.

---

#### F7. Lifetime gifts consume the federal exemption in one place out of three
*impact: medium · effort: S*

**Evidence.** `src/projection_stages/deterministic_engine.py` accumulates `lifetime_exemption_used_cumulative`, but only the Estate sheet (`src/reporting/sheets_strategy.py:1614-1626`) subtracts it. `src/after_tax.py`'s `estimate_terminal_estate_tax` and the Roth optimizer's estate-tax penalty do not — so three consumers can disagree about the same household's remaining exemption.

**Options.** (1) Thread the used exemption through the shared estate function so all three consumers agree. (2) Model gifts as an explicit gift-versus-bequest comparison including the carryover-basis-versus-step-up tradeoff. (3) Disclose the divergence instead of fixing it.

**Recommendation: Option 1 immediately** — small, and it removes an internal contradiction where the same workbook reports two different exemption balances. Schedule Option 2 separately as a feature.

---

#### F8. First-death step-up is 100% in one function and 50% in another
*impact: medium · effort: M*

**Evidence.** `src/planning_engines.py:430-436` returns 1.0 for the common-law-state first-death step-up; `src/after_tax.py:363-377` returns 0.5 for the same case, with a docstring that *incorrectly claims* it mirrors the other function. Separately, `src/core.py`'s `_infer_owner` assigns joint and household-named accounts entirely to `member_1`, producing an asymmetric step-up outcome depending on which spouse dies first.

**Options.** (1) Default joint-named accounts to JTWROS titling (50/50 split) and reconcile the two step-up functions' documented basis. (2) Add a first-class joint-ownership flag to the account registry. (3) Surface it as an audit prompt in the existing `beneficiary_titling_audit`.

**Recommendation: Options 1 + 3** — removes an indefensible asymmetry and catches the remaining cases through the audit that already exists.

---

#### F9. Account taxonomy gaps
*impact: medium · effort: M*

**Evidence.** `src/core.py`'s `ACCOUNT_TYPES` has no inherited/beneficiary IRA type (so an existing one gets the wrong RMD divisor and no depletion deadline); no basis field on pre-tax accounts (so 100% of every conversion dollar is taxed and a backdoor Roth is unmodelable); maps `'trust'` to individual tax brackets rather than the compressed trust schedule; has no NUA/employer-stock type; and **silently reclassifies unrecognized account names as `'taxable'`**.

**Options.** (1) Add IRA basis (pro-rata) and an inherited-IRA type, both defaulting to today's behaviour. (2) Add a trust tax-schedule branch. (3) Make unmodelled types explicit and blocking rather than silently misclassified.

**Recommendation: Option 3 first as a guardrail, then Option 1.** Silent misclassification is the immediate danger: a user can type an account name the tool does not know, get a fully confident plan, and never learn it was modelled as the wrong tax type. **This is the only finding in the entire review that produces a wrong answer today, silently, and it is S effort with no prerequisite — so the guardrail is scheduled in Wave 1 (item 1.16), beside the other silent-wrongness fix, 1.10.** Whether it blocks outright or warns first for already-saved plans is an open question in the appendix.

---

#### F10. RMDs use the Uniform Lifetime table only
*impact: medium · effort: S*

**Evidence.** `src/core.py`'s `rmd_divisor(age)` looks up a single table keyed on owner age alone, with no reference to a spouse's age or beneficiary designation. It therefore understates the RMD reduction available when the sole beneficiary spouse is more than ten years younger, where the Joint Life table applies.

**Options.** (1) Add the Joint Life table with automatic detection via titling plus an age-gap fallback. (2) Manual per-account override. (3) Leave as-is with a disclosure.

**Recommendation: Option 1 with an age-gap fallback.** The error is one-directional — RMDs come out too large — and it flows straight into the Roth conversion recommendation, inflating the apparent value of conversions.

---

#### F11. The Social Security sweep is scored against a single longevity assumption
*impact: medium · effort: M*

**Evidence.** `src/reporting/sheets_strategy.py`'s 81-pair claim-age sweep — genuinely strong work — is scored against fixed mortality ages defaulting to 92/95, with Monte Carlo survivor buckets built once and reused. Mortality uncertainty, which is the dominant driver of claiming decisions, does not differentiate the 81 pairs at all.

**Options.** (1) Re-run the winning neighbourhood at three longevity assumptions. (2) Add a cumulative breakeven presentation — nearly free, using rows already computed. (3) Score against the full mortality distribution (theoretically right; reopens a real prior performance problem).

**Recommendation: Option 2 first (cheap, high client value), then Option 1 restricted to the winner's neighbourhood.** Option 3 becomes affordable only if A1 and A4 land — see §3.

---

#### F12. No consolidated bracket-capacity view
*impact: medium · effort: M*

**Evidence.** Year-by-year tax capacity is split across four places: Sheet 11 shows bracket headroom for conversions only; Sheet 7 shows realized tax but excludes IRMAA and ACA cliffs and shows no remaining capacity; 0%-LTCG headroom is current-year only; QCD lands on cash-flow rows. A planner must reconcile four sheets to make one year's decision.

**Options.** (1) A new tax-capacity worksheet — one row per year, all headroom types plus actions taken. (2) Add capacity columns to the existing (already very wide) tax sheet. (3) An in-app single-year capacity panel rather than a workbook sheet.

**Recommendation: Option 1 as a new sheet.** This has the highest ratio of planner value to engineering cost in the entire review — the data is already computed, it is merely scattered. **It derives nothing new and has no prerequisite, so it is scheduled in Wave 1 (item 1.17), not mid-Wave-2** — the earlier draft placed it in Wave 2, which contradicted this priority claim.

---

#### F13. Plan monitoring compares assumptions, not outcomes
*impact: medium · effort: M*

**Evidence.** YTD tracking is single-year (prior-year-end comparison only). Build Impact compares admin and assumption changes between builds, not projected versus actual. The Planning Workbench is explicitly browser-local and never mutates the saved plan. Nothing retains a series of past projections, so there is no way to ask "how are we doing against the plan we made two years ago?"

**Options.** (1) Archive each build's KPI snapshot and diff outcomes with attribution (market / spending / assumption). (2) Snapshot-only comparison, no attribution. (3) Extend YTD tracking to multi-year actuals.

**Recommendation: Option 2 first, then Option 1's attribution once a real snapshot series exists.** Attribution logic built before any snapshots exist cannot be validated. **Schedule the snapshot archive itself in Wave 1 (item 1.15), not Wave 3** — four items in this programme move the headline probability of success, and a snapshot archive installed after those movements cannot explain any of them. It is an instrument, not a payoff. See §3.2.

---

## 3. Cross-cutting analysis

### 3.1 Where the experts agree

**Duplication is the dominant maintenance cost, and it is the same shape everywhere.** The architect found the cashflow rules implemented three times (A1), the LTCG formula three times (A6), the sweep pattern three times (A4), plan data in four stores (A3). The quality reviewer found the same pattern in tests: admin UI tests layered on each other (Q1), Roth UI assertions byte-identical across files (Q2). The documentation reviewer found the same pattern in content: two independently authored blocks narrating the same page (D5), help text duplicated between the inline box and the help pane (U2/D5). Four reviewers, working independently, described the same organizational habit — *add a new implementation beside the old one rather than change the old one* — in four different layers. That is the single most important structural observation in this report.

**Honesty is a strength here, and should be preserved.** Three separate findings turned out, on cross-check, to be cases where the system already disclosed its own limitation accurately: the withdrawal-order UI (F1), New York's `not_modeled` estate tax (F5), and `src/projection_pipeline.py`'s own comment admitting the registry is empty (A9). This is unusual and valuable. Several recommendations below (F2's materiality gating, F6's mandatory disclosure of modelled spending cuts) are explicitly designed to *extend* that habit rather than trade it away.

**The bottleneck for almost everything is engine performance and engine safety.** Usability wants faster builds. The planner wants richer sweeps. Quality wants unit tests that do not require a full pipeline run. All three route through the same two architectural facts: three engines, and unbounded sweeps.

### 3.2 Conflicts, named and resolved

**Conflict 1 — Usability wants to delete the help pane; Documentation wants to keep two differentiated texts.**
U2 recommends removing the fixed 370px help column entirely, on the grounds that the inline `.question` box already carries the load-bearing summary. D5 recommends *differentiating* the two texts by design — intro says "what to enter here", help says "what this affects elsewhere" — which presupposes two surfaces.

*Resolution: both, in sequence, and they do not actually conflict once the surfaces are separated from the layout.* D5's editorial split is right: the two texts should say different things. U2's layout objection is also right: a permanently visible 370px column is not the correct container for the secondary text, because it costs 21% of content width on every page whether or not the user wants it. So: **apply D5's editorial differentiation, then present the differentiated "what this affects elsewhere" text in an on-demand disclosure next to the title rather than a fixed column.** The content survives; the column does not. This also removes the largest single contributor to U1's overflow window.

**Conflict 2 — The architect wants to shrink the strategy sweeps; the planner wants to enrich them.**
A4 recommends gating sweeps on need and making the SS grid coarse-then-refine, to cut roughly 20,000 projections per build. F3 wants the Roth conversion window extended to plan end (a wider candidate space), and F11 wants the SS winner's neighbourhood re-scored at three longevity assumptions (3× the cost in that neighbourhood). These pull in opposite directions on the same compute budget.

*Resolution: the conflict is real but it is sequenced away, and the sequencing is the single most important insight in this section.* A1 (flip the default to the vectorized engine) and A4 (gate the sweeps) together reduce the per-build cost by roughly an order of magnitude — the 200-sim Monte Carlo under `exact_scalar` costs 200 full projections per candidate, and both the engine flip and the gating attack that multiplier. **The freed budget is exactly what F3 and F11 want to spend.** So: do A1 and A4 *first*, and the planner's richer analyses become affordable without a regression in build time. Attempting F3 or F11 before A1/A4 would make an already-slow build materially worse and would likely be rejected on performance grounds — which is how good planning proposals get killed by unrelated architecture. Order matters more than priority here.

**A precondition that is easy to mis-schedule: KPI snapshotting comes before the number-moving work, not after it.**
Four separate items move the headline probability of success — 1.1 (the engine-default flip), 3.2 (the extended conversion window), 3.4 (the bracket-target withdrawal policy) and 3.5 (the adoptable spending policy). F13's build KPI snapshot archive is the only mechanism in the system that can later explain *why* the number moved, and a snapshot archive is worthless for a flip that already happened. It is therefore a **precondition of the number-moving work, not a payoff of it**, and is scheduled as Wave 1 item 1.15 rather than in Wave 3. This was the planner's first blocking edit and it is correct.

A secondary note on this resolution: A4's coarse-then-refine SS grid and F11's "re-run the winner's neighbourhood at three longevity assumptions" are *the same mechanism*. A coarse-then-refine sweep already has a "refine the neighbourhood of the winner" phase. F11's longevity sensitivity should be implemented as a second dimension of that refine phase, not as a separate pass. This makes the two findings cheaper together than either is alone.

**Conflict 3 — Quality wants more tests; the architect wants to delete tests.**
Q3/Q4/Q5 all ask for new test files. A14 and Q1/Q2/Q6 ask to delete or merge existing ones.

*Resolution: no real conflict — they target disjoint sets.* The deletions target tests that assert nothing (A14: five tests asserting against a commented-out block) or that assert the same literal repeatedly (Q1, Q2). The additions target layers with no coverage at all (unit, integration, error paths, e2e journeys). Total file count may barely move; the *information content* of the suite rises substantially. Frame this to reviewers as "rebalancing", not "adding tests" or "cutting tests", because either framing alone will be resisted.

### 3.3 What one change unlocks several others

**Tax kernel extraction is the highest-leverage single piece of work.** A2 (decompose the 3,073-line engine function) recommends extracting the pure tax kernel — bracket, IRMAA and LTCG closures — as its first step. A6 (LTCG implemented three times with two different inflation indices) recommends consolidating into exactly such a kernel. These are *the same work item*, arrived at independently by the same reviewer from two different directions. Doing it once:
- gives A2 its first safe cut, establishing the extraction pattern for the remaining thirteen stages;
- resolves A6's inflation-index divergence, which is a live correctness question, not merely a tidiness one;
- gives Q3 its first genuinely unit-testable module — the kernel is pure, so it can be tested with hand-computed values rather than golden-master extracts, which is precisely what Q3 asks for on the highest-risk modules;
- gives A9 its first real pipeline stage, converting `STAGE_IMPLEMENTATIONS` from permanently-empty to populated-with-one.

Four findings, one piece of work. It is the first thing to do after the engine default is flipped.

**Engine consolidation (A1) is the second unlock.** Beyond the sweep budget discussed above, it removes the situation where the golden master validates a code path that no user runs. Every subsequent engine change — F1's bracket-target policy, F3's extended conversion window, F6's adoptable spending policy — is currently being proposed against three implementations. After A1, they are proposed against one plus a test oracle.

**The glossary wiring fix (D1) unlocks D2 for free** and is the template for any future term added to `TERM_NOTES` — right now, adding a term only helps on one of five text surfaces, so the term list is worth less than it appears.

**The materiality-gating predicates (F2 Option 1) are reusable.** "Does this household's projected estate exceed the applicable exemption?" is the predicate F2 needs for the CST recommendation, F5 needs for the New York cliff, and F7 needs to reconcile the three disagreeing exemption consumers. Build it once, in the shared estate function.

---

## 4. Recommendation

### The plan

**A single coherent programme in three waves, sequenced so that architecture work pays for the planning work that follows it.**

*Wave 1 — make the ground safe, install the instrument, and take the free wins.* Stand up the build KPI snapshot archive **first**, so that every subsequent change to the headline number is attributable in a series rather than asserted. Flip the Monte Carlo default to the engine that is actually tested, and add the fidelity-tolerance test that makes exact-scalar a validation oracle instead of an untested shipping path. Fix the five tests that assert against a commented-out block. Delete the provably dead scaffolding. Close the one finding that produces a wrong answer *today, silently* — the account-taxonomy guardrail. Ship the tax-capacity worksheet, which derives nothing new and has no prerequisite. In parallel, take the cheap high-value user-facing fixes that touch nothing structural: the glossary wiring, the collapsed allocation-policy disclosure, the grid overflow breakpoint, the source-of-truth banner jargon, and the whole fabricated-CST recommendation row. Independently, extract characterization tests from golden-master fixture data so the engine work in Wave 2 has a safety net.

*Wave 2 — extract the kernel, gate the sweeps, fix the modelling errors.* Extract the tax kernel (serving A2, A6, Q3 and A9 simultaneously). Extract the shared sweep runner with need-based gating built in. Fix the internal contradictions the planner found: the exemption threaded through all three consumers, the two step-up fractions reconciled, the Joint Life RMD table. Generalize Wave 1's CST materiality predicate to the remaining recommendation rows (LTC, S-Corp, QTIP). Build the real integration and error-path test layers.

*Wave 3 — spend the budget the first two waves created.* Extend the Roth conversion window and add phase candidates. Fix the heir tax model. Add the bracket-target hybrid withdrawal policy. Add the adoptable spending policy with mandatory cut disclosure *and* the conditional-success relabelling it requires. Complete New York's estate tax, including the three-year gift add-back. Add the SS breakeven presentation and longevity refinement. Continue the engine decomposition into real pipeline stages, and continue converting frontend leaves to real imports.

### What this plan is deliberately NOT doing, and why

- **Not unifying the three engines into one rule kernel with two drivers (A1 Option 3) in this programme.** It is the correct destination and it is named as such. But it is XL work on the most delicate code in the system, and attempting it before the tax kernel is extracted and before real unit coverage exists would be a large refactor performed blind. Flip the default now; unify later, from a better position.

- **Not introducing a bundler (A7 Option 2).** It is architecturally the right answer and it would eliminate the load-order fragility that already caused one outage. It is rejected here only because it adds a build step to a deliberately build-free desktop application — a product constraint, not a technical judgment. **If that constraint is negotiable, this decision should be revisited, and it is the first question in the appendix.**

- **Not making sweeps asynchronous (A4 Option 3).** Best perceived latency, but it adds another artifact-drift surface to a system that already has documented trouble with artifact drift. The synchronous path gets fast enough via gating.

- **Not attempting the target test pyramid (Q10) as a project.** It is a direction to steer by, not a milestone to hit. The individual findings Q1–Q7 move toward it; a dedicated "fix the pyramid" project would be XL, would compete with the engine work for the same reviewers, and would deliver its value more slowly than the pieces do individually.

- **Not expanding state coverage beyond completing New York (F5 Option 2).** Fifty-state coverage is a real product gap, but the current 13-state list with a hard `ValueError` is *honest* — a user outside those states is told so. Completing New York fixes a case where the tool claims support and silently returns zero. That asymmetry makes New York urgent and the other 37 states merely desirable.

- **Not touching the withdrawal-order UI copy.** The original finding proposed it; cross-check established the copy is already accurate. Explicitly out of scope so nobody re-derives it.

- **Not acting on the HSA/YTD test clusters (Q9) yet.** They were not confirmed duplicative. Audit first.

- **Not deleting `report_spec` (A13) or `src/projection_pipeline.py` (A9).** Both look dead; both are cheap to keep, and the pipeline's stage list is the best available map of the engine and the target shape for its decomposition.

---

## 5. Design — target state

### 5.1 Engine and modules

**`src/tax_kernel.py` (new).** Pure functions, no config mutation, no I/O. Owns: federal bracket lookup and marginal rate; the LTCG bracket-stacking calculation (one implementation, taking an injected bracket-inflation factor rather than reading a config field itself); IRMAA tier lookup against the two-year MAGI lookback; NIIT threshold. Bracket tables sourced from `src/taxes.py`'s centralized data, never redefined locally. `src/core.py:1295`, `src/projection_stages/deterministic_engine.py:476`, and `src/tlh.py:159` all become thin call sites. The inflation-index question (`irmaa_inflator` vs `brk_inf`) is resolved explicitly at each call site rather than implicitly by which copy happens to run.

**`src/projection_pipeline.py` (existing, made real).** `STAGE_IMPLEMENTATIONS` gains its first entry: the tax stage, delegating to `tax_kernel`. The unreachable "stage contract completed" branch and the per-row dict copy are removed. The 14-stage `DEFAULT_STAGE_ORDER` remains the canonical map of the engine and becomes the decomposition plan.

**`src/strategy_sweep.py` (new).** One runner with a four-phase contract: *enumerate* candidates, *evaluate* each (projection + optional Monte Carlo, with simulation count as a parameter), *rank* by objective, *disclose* the comparison table. Three call sites adopt it: the Roth conversion optimizer, the SS claim-age grid, and the withdrawal-strategy comparison. Gating lives in `enumerate`: when the user has chosen an explicit policy, the enumeration returns that policy plus a small fixed comparison set rather than the full candidate space. The SS grid's enumeration becomes two-phase — coarse pass over the 9×9 at a reduced simulation count, then a refine pass over the winner's neighbourhood at full fidelity, with longevity as a second refine dimension (see 5.4).

**Monte Carlo.** `quick_vectorized` becomes the default in `src/data_io.py:1736-1743` and the CSV default value. `monte_carlo_exact_scalar` remains, reachable by config and by a new fidelity test asserting the two engines agree within tolerance on the frozen fixture. The `survivor_buckets` parameter either reaches exact-scalar or exact-scalar is documented as not supporting it — the current silent drop is the defect.

**Plan storage.** JSON/YAML config backends removed from `src/config_backend.py` and from `_sync_config_backends()`. The two SQLite stores collapse to one, with `load_active_config()` and the save path reading and writing the same table. Target: one write per saved field, not four.

**`src/reporting/workbook_common.py`.** Engine re-exports (`project`, `monte_carlo`, `optimize_roth_conversion_strategy`, `run_scenario`) deleted; sheet builders import from the engine directly, making the reporting layer's real dependency visible. Duplicate `__all__` resolved; stale star-import comments removed.

### 5.2 Screen layouts

**Main grid.** New breakpoint at 1416px. Below it: two columns (nav 310px | content), help column removed from the layout. Above it: unchanged. The 1180px single-column collapse stays. Net effect: no horizontal overflow at any width.

**Help.** The right-hand `#helpPanel` column is retired as a fixed layout element. Its content moves to an on-demand disclosure beside the page title, opened by the existing help affordance. Content is D5-differentiated: the inline `.question` box answers "what do I enter here"; the disclosure answers "what does this affect elsewhere".

**Allocation page.** `renderAllocationPolicy()`'s `<details>` gets `open` (`frontend/js/dashboard.js:4123-4124`). One line.

**Spending drill-down.** A filter chip row above the tree: `All | Exceptions`. "Exceptions" filters to rows where the existing `statusFor()` returns over or watch, auto-expanding their ancestors. State is per-session, not persisted. No new data is computed — `frontend/js/spending_dashboard.js:242-246` already produces everything needed.

**Income and strategy coordination.** A read-only "coordination summary" card rendered inline on `income_work`, `income_retirement` and `distribution_strategy`, showing the other pages' current values (claim ages, conversion policy, work-income end year) with an edit link. Read-only by design — it is a context restorer, not a second editor.

**Reports and Review.** Preflight readiness folds into the Build tab as a readiness block above the build button. The four-tab sequence in the intro copy is rewritten to match the actual flow.

### 5.3 Content and wording

- `addParentheticals` applied to `pageHelp()`'s `meaning`, `connections`, `options` and `impact` fields, and to KPI tile labels in `frontend/js/dashboard_decomp_home_panels.js`.
- `TERM_NOTES` gains entries for "probability of success" (currently absent from `TERM_NOTES`, `ACRONYM_DEFINITIONS` and `src/glossary.py` alike) and "advisor-ready". **The "probability of success" wording is specified now rather than left to Wave 3**, so that it survives the later changes that alter what the number means: it must say the figure is *the share of simulated paths that funded the plan under this plan's assumptions* — not a general or industry figure — and the **same string** must be used for the `TERM_NOTES` entry and for the new KPI-tile tooltip, so the two surfaces cannot drift. When item 3.5 lands, that same string is what gains the conditional-success qualifier described in §5.4.
- Of the ten `SOURCE_TRUTH_STEPS` banners in `frontend/js/dashboard_source_truth_banners.js:3-24`: delete those that state only storage mechanics; rewrite `build_impact` and `review` in outcome language ("this is a preview until you Save"). No banner mentions SQLite, adapters, or a CSV filename.
- `src/reporting/sheets_summary_builder.py:271`: the `(CSV: Other Assets > Autos > depreciation_years)` parenthetical moves to the QC/Reference sheet. The "Release Notes" section is renamed to match its actual content (modelling assumptions and build provenance), and its other three bullets are audited at the same time.
- `documentation/readme/README.md` gains a two-line end-user section above the developer commands.
- `household_people`'s `intro` and `STEP_HELP.connections` are edited to the D5 split rather than both describing birth-date effects.

### 5.4 New planning capabilities and what they must compute

**Materiality predicates (shared).** A single function answering: projected gross estate at each death, applicable federal and state exemption for that year net of lifetime exemption already consumed, and the resulting exposure. Consumed by the Executive Summary recommendation gate, the CST savings figure, the Roth optimizer's estate penalty, and `estimate_terminal_estate_tax` — the three consumers that currently disagree (F7).

**CST savings and the CST recommendation row.** Replaces `sheltered * 0.08` at `src/reporting/summary_figures.py:106`. Must compute the actual `illinois_estate_tax()` delta with and without the trust, and must return *no figure at all* when the projected estate does not exceed the applicable exemption. **The same predicate must also suppress the recommendation row itself** — fixing only the figure while leaving the boolean gate for a later wave would publish an unqualified bare recommendation with no number attached, which is worse than the fabricated number it replaced. A recommendation with no material value shows as "reviewed — not material for this household", not as a dollar amount and not as a bare row. Item 2.11 then *generalizes this same predicate* to the LTC, S-Corp and QTIP rows; it does not introduce it.

**Roth conversion window.** `conversion_window_end_year()` extends to plan end rather than the primary member's RMD age, and considers both members' dates of birth — **and must remain open through the survivor's single-filer years, which the engine already models elsewhere.** The widow's-bracket case is a filing-status transition, not merely a date-of-birth one, and it is the more valuable of the two windows. **Both existing window controls (`roth_max_conversion_years`, `conv_window_offset`) remain authoritative when explicitly set; the extension changes only the default.** Candidate set gains phase-varying strategies ("fill bracket X until SS claim, then bracket Y"). The hardcoded `400000` bracket-top fallback at `src/planning_engines.py:1872` is replaced with an explicit error or a nearest-bracket resolution while this function is open. The existing guardrails must be verified to fire correctly in late years *before* the window is widened — an unguarded late conversion can raise Medicare premiums.

**Heir tax model.** `effective_heir_ten_year_rate()` gains per-beneficiary baseline ordinary income, state of residence, and a beneficiary class (spouse / minor child / disabled or chronically ill / less-than-ten-years-younger / other). Eligible designated beneficiaries take the life-expectancy stretch, not the 10-year rule. **Baseline income and state default to today's values. Beneficiary class defaults to the class inferred from the account's existing beneficiary and titling data where that data exists**; plans whose after-tax legacy figure moves as a result should be flagged in the build notes as a **correction, not suppressed**. *(Corrected on the planner's review pass: the earlier "all default to today's values so existing plans do not move" framing was right for baseline income and state but wrong for beneficiary class — today's default of "everyone gets the 10-year rule" is legally incorrect for spouse, minor-child, disabled-or-chronically-ill, and less-than-ten-years-younger beneficiaries, so preserving it is preserving a known-wrong answer.)*

**Bracket-target withdrawal policy.** A policy option that fills ordinary income to a configured target bracket from pre-tax accounts, then draws taxable, then follows the existing cascade. Implemented inside the existing true-up rather than replacing it. This is the policy most CFPs actually implement, and it is the 80% case of arbitrary reordering.

**Adoptable spending policy.** A selector: fixed-real (today's behaviour, remains the default), Guyton-Klinger guardrails, or a floor-ceiling band. The chosen policy runs in *both* the deterministic and Monte Carlo engines, and the shadow portfolio in `src/planning_engines.py` becomes the live one. Mandatory output: the size and duration of every modelled spending cut.

**Mandatory relabelling when a non-fixed-real policy is active.** When any policy other than fixed-real is selected, the probability-of-success label and its glossary note must state that success is **conditional on the modelled spending cuts**, and the KPI tile must display **the worst modelled cut alongside the percentage**. Without this, the same percentage silently changes meaning — *survived having cut* rather than *funded as asked* — with no signal to the reader that it did. This is the same string specified in §5.3, gaining a qualifier; it is not a second, separately authored sentence.

Separately, an optional age-phased real spending curve (discretionary declines X% between ages A and B).

**New York estate tax.** `state_estate_tax()` gains the real NY mechanism — the graduated rate table plus the 105%-of-exemption cliff — replacing `estate_calc='not_modeled'` for NY only. **This must include the three-year gift add-back**, which brings prior taxable gifts back into the NY gross estate. That add-back consumes the same lifetime-gift series threaded in F7 (item 2.6, already 3.6's prerequisite), so the data is available. Without it, the cliff calculation completes but still under-reports NY estate tax for any household that gifted late — which is precisely the household most likely to be sitting near the cliff.

**Tax-capacity worksheet (new sheet).** One row per projection year. Columns: ordinary income, remaining headroom to the next federal bracket, remaining 0% LTCG headroom, distance to the next IRMAA tier, distance to the ACA cliff (during bridge years), remaining QCD capacity, and the actions actually taken that year (conversion, harvest, QCD). Every value is already computed somewhere; this sheet consolidates rather than derives.

**RMD Joint Life table.** `rmd_divisor()` (`src/core.py:754`) takes a spouse age and sole-beneficiary flag, applying the Joint Life table when the sole beneficiary spouse is more than ten years younger, with an age-gap fallback when titling is not explicit. While the function is open, confirm that its **hardcoded age-72 floor cannot fire ahead of `statutory_rmd_start_age()`** — the latter implements the SECURE 2.0 §107 73/75 ramp, and the two are currently independent constants in the same module. This is a pure age-keyed table lookup and has **no dependency on the tax-kernel extraction**.

**SS breakeven and longevity.** A cumulative breakeven presentation over the rows the 81-pair sweep already computes (essentially free), plus a refine pass re-scoring the winner's neighbourhood at three longevity assumptions — implemented as a second dimension of `strategy_sweep`'s refine phase, not a separate sweep.

**Build KPI snapshots.** Each build archives its headline KPIs with a timestamp. Comparison-only at first (F13 Option 2); attribution added once a real series exists.

### 5.5 Test pyramid shape

Target (from Q10, as a direction rather than a milestone):

| Layer | Now | Target | Notes |
|---|---|---|---|
| Unit | 3 | 40–60 | One per pure calc module. `tax_kernel` is the first and is hand-computable. |
| Integration | 1 | 10–15 | Route handler → service → engine → serialized response, without the subprocess build. |
| Golden-master / contract | ~170 | ~170 | **Do not shrink.** Split DOM-literal checks out of the `_regression` suffix. |
| E2E (Playwright) | 13 | 18–20 | Add new-plan-creation, admin-config-change, build-failure. |
| Node frontend | 12 | ~12 | Unchanged. |

Plus: five tests repointed from `src/dashboard_ui/template.py`'s commented-out block to the real `frontend/` files; eight admin functional files merged to one; two Roth UI files merged; a `_regression` vs `_functional` rename pass with a mechanical suffix-shape checker to stop re-inflation.

---

## 6. Implementation plan

Effort scale: **S** ≤ 1 day · **M** ≈ 2–5 days · **L** ≈ 1–2 weeks · **XL** > 2 weeks.
"Verification" is what proves the item worked — a green suite alone is insufficient for anything that changes a reported number.

### Wave 1 — Safety, deletions, and free wins

| # | Item | Finding | Prereq | Effort | Risk | Verification | Parallel? |
|---|---|---|---|---|---|---|---|
| 1.1 | Flip MC default to `quick_vectorized`; add exact-scalar fidelity-tolerance test | A1 | — | M | **High** | Before/after projection diff on the demo plan, reviewed and signed off by a planner. Golden master will NOT catch this — it already runs vectorized. KPI snapshot archive (1.15) in place so the flip is attributable in the series. Tolerance answered per appendix Q3 before starting. | Yes |
| 1.2 | Repoint 5 marker tests at real `frontend/` files; delete `src/dashboard_ui/template.py` | A14 | — | S | Low | The 5 tests fail if the corresponding frontend feature is removed (verify by temporary deletion). | Yes |
| 1.3 | Delete `src/server/features/` (8 modules, zero importers) + tier-1 dead scaffolding | A8 | 1.2 | S | Low | Full suite green; grep confirms zero remaining references, including through `from ..core import *`. | Yes |
| 1.4 | Remove the 80-block dual-import shim via codemod; add a lint rule | A10 | — | M | Low | Full suite green; PyInstaller build succeeds; a deliberate broken transitive import now fails loudly rather than silently. | Yes |
| 1.5 | Glossary wiring: `addParentheticals` → `pageHelp()` 4 fields + KPI tiles; add 2 `TERM_NOTES` entries | D1, D2 | — | S | Low | "Probability of success" renders glossed on the home KPI tile and on the `income_retirement` step. | Yes |
| 1.6 | Grid breakpoint at 1416px dropping the help column; `.field-list` width recalibration | U1, U7 | — | S | Low | No horizontal overflow at 1280, 1366 and 1440px viewport widths. | Yes |
| 1.7 | `<details open>` on allocation policy | U5 | — | S | None | Policy fields visible on first render of `allocation_assets`. | Yes |
| 1.8 | Spending "Exceptions" filter chip | U3 | — | S | Low | With one over-budget category in a 6×4 household, it is reachable in one click. | Yes |
| 1.9 | Source-of-truth banners: delete mechanics-only, rewrite `build_impact` / `review` | D3 | — | M | Low | No banner contains "SQLite", "adapter", or a `.csv` filename. | Yes |
| 1.10 | Fix the fabricated CST savings figure **and suppress the CST recommendation row when the projected estate is below the applicable exemption** | F2 (partial) | — | S | Medium | `src/reporting/summary_figures.py` no longer returns a dollar figure when the projected estate is below the exemption, **and the row itself does not render** — no bare unqualified recommendation is left behind; a hand-worked household reproduces the `illinois_estate_tax()` delta. | Yes |
| 1.11 | Release-notes config-path relocation + section rename + bullet audit | D4 | — | S | Low | Sheet 1 contains no CSV path; the QC sheet does. | Yes |
| 1.12 | LTCG cross-implementation equivalence test (diagnostic only) | A6 | — | S | None | The test either passes (A6 is a refactor) or fails (A6 is a bug fix). **This result determines Wave 2 scope.** | Yes |
| 1.13 | Characterization tests extracted from golden-master fixture data for `taxes.py`, `after_tax.py`, `gain_harvest.py`, `tlh.py` | Q3 | — | M | Low | Each module has a test that fails on a deliberately introduced one-cent change. | Yes |
| 1.14 | Merge 8 admin functional files → 1; merge 2 Roth UI files | Q1, Q2 | — | M | Low | Assertion count preserved or deliberately reduced with each removal justified. | Yes |
| 1.15 | Build KPI snapshot archive + comparison view *(moved from Wave 3 item 3.9)* | F13 | — | M | Low | Two builds a week apart produce a comparable KPI series. **Must exist before 1.1, 3.2, 3.4 and 3.5 land**, since those four move the headline probability of success and this is the only mechanism that can explain why. | Yes |
| 1.16 | Account-taxonomy guardrail: unrecognized account names error rather than silently becoming `taxable` *(moved from Wave 2 item 2.8)* | F9 | — | S | Medium | An unknown account name produces a clear user-facing error, not a confident plan. | Yes |
| 1.17 | Tax-capacity worksheet (new sheet) *(moved from Wave 2 item 2.10)* | F12 | — | M | Low | One row per year; every headroom figure reconciles against its existing source sheet. When 2.1 lands, the sheet's bracket/IRMAA/LTCG reads are repointed at `tax_kernel` — no figures should move. | Yes |

**All 17 Wave 1 items can run concurrently** — they touch disjoint files. 1.3 waits only on 1.2 (which deletes `template.py`). 1.1 is the only high-risk item and should not be batched with others in the same review.

**Why 1.15, 1.16 and 1.17 are here rather than in later waves** (all three moved on the planner's review pass):
- **1.15 (KPI snapshots)** is an instrument, and an instrument installed after the measurement is worthless. Four items in this programme move the flagship percentage; this is the only one that records the series they move through.
- **1.16 (account-taxonomy guardrail)** is the sole finding in the entire review that produces a **wrong answer today, silently** — an unrecognized account name is modelled as `taxable` and the user is never told. It is S effort with no prerequisite; there is no defensible reason it waits a wave. It belongs beside 1.10, the other silent-wrongness fix.
- **1.17 (tax-capacity worksheet)** is called the highest planner-value-to-engineering-cost item in the review (§2.5 F12). It derives nothing new and has no prerequisite. Scheduling it mid-Wave-2 contradicted the document's own priority claim.

### Wave 2 — Kernel, sweeps, and modelling corrections

| # | Item | Finding | Prereq | Effort | Risk | Verification | Parallel? |
|---|---|---|---|---|---|---|---|
| 2.1 | Extract `src/tax_kernel.py`; repoint `core.py:1295`, `deterministic_engine.py:476`, `tlh.py:159` | A2, A6, A9 | 1.12, 1.13 | L | **High** | Golden master green **or** an explained, signed-off diff if 1.12 showed the inflation indices diverge. Kernel gets hand-computed unit tests. | No — everything downstream waits on it |
| 2.2 | Register the tax stage in `STAGE_IMPLEMENTATIONS`; delete the dead branch and per-row dict copy | A9 | 2.1 | S | Low | `STAGE_IMPLEMENTATIONS` non-empty; the previously unreachable branch now executes. | No |
| 2.3 | Extract `src/strategy_sweep.py` with need-based gating; adopt at 3 call sites | A4 | 1.1 | L | **High** | Build wall-clock time measured before/after. Recommended strategy unchanged on the frozen fixture, or the change is planner-signed-off. | Yes (with 2.4–2.7) |
| 2.4 | Retire JSON/YAML config backends | A3 | — | S | Low | `_sync_config_backends()` writes 3 stores, not 4; suite green. | Yes |
| 2.5 | Collapse the two SQLite stores into one | A3 | 2.4 | L | **High** | `test_real_build_journey_reflects_a_user_edited_input` green (this is the test that caught the prior revert); per-field save latency measured. | No — sequence after 2.4 |
| 2.6 | Thread lifetime exemption through all 3 estate consumers | F7 | — | S | Medium | All three consumers report the same remaining exemption for a household with lifetime gifts. | Yes |
| 2.7 | Reconcile the two step-up fractions; default joint accounts to JTWROS; add the titling audit prompt | F8 | — | M | Medium | `planning_engines.py:430` and `after_tax.py:363` agree; first-death outcome no longer depends on which spouse dies first. | Yes |
| 2.8 | *(moved to Wave 1 as item 1.16 — number retired, not reused, so existing cross-references stay unambiguous)* | F9 | — | — | — | — | — |
| 2.9 | RMD Joint Life table with age-gap fallback; **confirm the age-72 floor in `rmd_divisor` (`src/core.py:754`) cannot fire ahead of `statutory_rmd_start_age`** (SECURE 2.0 73/75 ramp) | F10 | — | S | Medium | A 12-year age gap produces the Joint Life divisor; no owner receives an RMD before their statutory start age; golden master diff explained. | **Yes** |
| 2.10 | *(moved to Wave 1 as item 1.17 — number retired, not reused)* | F12 | — | — | — | — | — |
| 2.11 | **Generalize 1.10's materiality predicate** to the remaining Executive Summary recommendations (LTC, S-Corp, QTIP); top-N ranking with "reviewed, not material" | F2 | 1.10, 2.6 | M | Medium | No recommendation row fires for a household well under the relevant threshold; the CST row (already gated in 1.10) is refactored onto the shared predicate rather than re-implemented. | No — after 1.10 and 2.6 |
| 2.12 | Cross-layer integration tests (route → service → engine → response) | Q7 | — | M | Low | 10+ integration tests; a deliberately broken service-layer contract is caught without a subprocess build. | Yes |
| 2.13 | Error-path tests: build-failure surfacing and malformed-input rejection | Q5 | — | M | Low | A crashed build subprocess produces an asserted user-visible error state. | Yes |
| 2.14 | 3 new e2e specs: new-plan-creation, admin-config-change, build-failure | Q4 | 2.13 | M | Low | 16 specs green in CI. | No — after 2.13 |
| 2.15 | `_regression` → `_functional` rename pass + suffix-shape checker | Q6 | 1.14 | M | Low | Checker fails on a deliberately mis-suffixed new file. | Yes |
| 2.16 | `workbook_common` cleanup: drop engine re-exports, fix duplicate `__all__` and stale comments | A11 | — | M | Medium | Sheet builders import the engine directly; suite green. | Yes |
| 2.17 | `report_spec` computed once instead of twice | A13 | — | S | Low | One derivation site; the two consuming tests green. | Yes |
| 2.18 | Help-pane retirement + D5 editorial differentiation | U2, D5 | 1.6 | M | Low | No fixed help column; the differentiated text is reachable in one click; e2e specs green. | Yes |
| 2.19 | Merge Preflight into Build; correct the tab-sequence copy | U6 | — | M | Low | Build reachable without a Preflight click; copy matches the flow. | Yes |
| 2.20 | Coordination summary cards on income/strategy pages | U4 | — | L | Low | Claim ages and conversion policy visible without leaving the income page. | Yes |
| 2.21 | End-user section in the shipped README | D6 | — | S | None | README's first section is meaningful to someone running the packaged app. | Yes |

**Concurrency inside Wave 2:** 2.1 runs alone and first (everything with a *tax-kernel* dependency waits). Once 2.1 lands, three independent tracks run in parallel — *engine/sweep* (2.2, 2.3), *data and modelling* (2.4→2.5, 2.6→2.11, 2.7), *tests and UI* (2.12, 2.13→2.14, 2.15, 2.16, 2.17, 2.18, 2.19, 2.20, 2.21). **2.9 no longer waits on 2.1 and can start immediately** — `rmd_divisor` is a pure table lookup keyed on owner age (`src/core.py:754`) and touches none of the tax kernel's bracket, IRMAA or LTCG closures; the earlier prerequisite was an error, corrected on the planner's review pass. 2.5 must follow 2.4; 2.11 must follow both 1.10 and 2.6; 2.14 must follow 2.13. Items 2.8 and 2.10 have moved to Wave 1.

### Wave 3 — Spend the budget

| # | Item | Finding | Prereq | Effort | Risk | Verification | Parallel? |
|---|---|---|---|---|---|---|---|
| 3.1 | Verify Roth guardrails fire correctly in late years, **and verify that post-RMD-age conversion headroom is computed net of the year's RMD** | F3 (gate) | 2.1 | S | Medium | Guardrails demonstrably fire past RMD age before the window is widened. `pre_non_ss` (`src/planning_engines.py:1874`) does include `rmd_total` today, **but this code path has never actually executed in a window extending past RMD age — this needs an explicit test, not an assumption.** **Blocks 3.2.** | No |
| 3.2 | Extend the conversion window to plan end (default only — `roth_max_conversion_years` and `conv_window_offset` stay authoritative when explicitly set); keep it open through the survivor's single-filer years; consider both members' DOB; add phase-varying candidates; replace the hardcoded `400000` bracket-top fallback at `src/planning_engines.py:1872` | F3 | 3.1, 2.3 | L | **High** | Build time within budget post-2.3; the widow's-bracket years are inside the window for a two-member household; an unmatched `roth_target_rate` now fails loudly instead of defaulting to a 400k bracket top; recommendation change planner-signed-off and visible in the 1.15 KPI series. | No |
| 3.3 | Heir tax model: baseline income, state, beneficiary class, EDB branch | F4 | 2.1 | M | Medium | An EDB beneficiary takes the stretch, not the 10-year rule. Baseline income and state default to today's values; **beneficiary class defaults to the class inferred from existing beneficiary/titling data where present.** Plans whose after-tax legacy figure moves are flagged in the build notes as a **correction, not suppressed** — "existing plans unchanged" is explicitly *not* the acceptance criterion for the class field. | Yes |
| 3.4 | Bracket-target hybrid withdrawal policy | F1 | 2.1, 2.2 | L | **High** | The policy produces the intended bracket fill; golden master diff explained; interaction with the Roth optimizer's bracket cap verified. | Yes |
| 3.5 | Adoptable spending policy selector + mandatory cut disclosure + **conditional-success relabelling** | F6 | 2.1, 1.5, 1.15 | M | **High** | Policy runs in both engines; every plan reports modelled cut size and duration. **With any non-fixed-real policy active, the probability-of-success label and its glossary note state that success is conditional on the modelled spending cuts, and the KPI tile displays the worst modelled cut alongside the percentage** (same string as 1.5's `TERM_NOTES` entry, qualified — not a second sentence). | Yes |
| 3.6 | Complete the New York estate tax (graduated table + 105% cliff + **three-year gift add-back**) | F5 | 2.6 | L | Medium | A household just over the NY exemption shows the cliff; a household that gifted within three years of death has those gifts added back into the NY gross estate, consuming the same lifetime-gift series threaded in 2.6; `not_modeled` removed for NY only. | Yes |
| 3.7 | SS cumulative breakeven presentation | F11 | — | S | Low | Breakeven age shown per claim pair from rows already computed. | Yes |
| 3.8 | SS longevity refinement as a second refine dimension of `strategy_sweep` | F11 | 2.3, 3.7 | M | Medium | The winner's neighbourhood scored at 3 longevity assumptions; build time within budget. | No — after 2.3 and 3.7 |
| 3.9 | *(moved to Wave 1 as item 1.15 — number retired, not reused)* | F13 | — | — | — | — | — |
| 3.10 | Continue engine decomposition into registered pipeline stages | A2 | 2.1, 2.2 | XL | High | Each extracted stage golden-master-gated; `STAGE_IMPLEMENTATIONS` grows monotonically. | Yes (ongoing) |
| 3.11 | Frontend: convert leaf modules to real imports bottom-up | A7 | — | L | Medium | The ordered script-tag list in `frontend/index.html` shrinks; the load-order regression test and e2e specs green after each step. | Yes (ongoing) |
| 3.12 | Extend `results_model` page by page, deleting scraper paths | A12 | — | L | Medium | Model coverage rises from 6 pages; `src/detailed_results.py` parsing paths shrink correspondingly. | Yes (ongoing) |
| 3.13 | Split `parse_client` into `src/parsing/` siblings; move validation out | A5 | 1.13 | L | High | One section at a time, golden master green after each. | Yes (ongoing) |
| 3.14 | HSA/YTD test-cluster duplication audit, then act if confirmed | Q9 | 2.15 | S | Low | Audit report; merge only what is confirmed duplicative. | Yes |

**Concurrency inside Wave 3:** 3.1 gates 3.2 and must complete first. 3.8 follows 3.7 and 2.3. Everything else runs concurrently; 3.10–3.13 are ongoing background tracks rather than discrete deliverables. Item 3.9 has moved to Wave 1 as 1.15 — and because 3.2, 3.4 and 3.5 all move the flagship percentage, none of them should land before that snapshot archive is collecting.

### Wave table with minimal effective model per item

Model selection principle: **haiku** for mechanical, pattern-uniform sweeps with an unambiguous correct answer; **sonnet** for scoped changes within one or two files with clear acceptance criteria; **opus** for design-heavy, cross-cutting, or financially consequential work where a wrong-but-plausible answer is expensive.

**Wave 1 — all concurrent**

| Item | Model | Why |
|---|---|---|
| 1.1 Flip MC default + fidelity test | **opus** | Changes every number a user sees, and the golden master cannot catch it. |
| 1.2 Repoint 5 marker tests | sonnet | Scoped, but requires understanding what each test *should* assert. |
| 1.3 Delete dead scaffolding | sonnet | Mechanical, but the `import *` surface needs judgment before deletion. |
| 1.4 Dual-import codemod | **haiku** | 80 structurally identical blocks; textbook mechanical sweep. |
| 1.5 Glossary wiring | sonnet | Small, scoped; needs care that glossing does not break HTML escaping. |
| 1.6 Grid breakpoint + field-list width | sonnet | Scoped CSS with a measurable pass condition. |
| 1.7 `<details open>` | **haiku** | One attribute. |
| 1.8 Spending exceptions chip | sonnet | New UI affordance over existing data. |
| 1.9 Banner rewrite/delete | sonnet | Editorial judgment about which banners carry a real fact. |
| 1.10 CST figure fix + row suppression | **opus** | Financially consequential; must decide when to publish no figure *and no row* at all. |
| 1.11 Release-notes relocation | **haiku** | Move one string, rename one heading. |
| 1.12 LTCG equivalence test | sonnet | Scoped diagnostic; the interpretation is what matters and comes later. |
| 1.13 Characterization tests | sonnet | Repetitive but each module needs its own extraction judgment. |
| 1.14 Merge admin/roth test files | **haiku** | Mechanical dedupe with a clear "keep newest assertion" rule. |
| 1.15 Build KPI snapshots | sonnet | Scoped persistence plus a comparison view. |
| 1.16 Account-taxonomy guardrail | sonnet | Scoped; the hard part is choosing where to fail. |
| 1.17 Tax-capacity worksheet | sonnet | New sheet over already-computed data. |

**Wave 2**

| Item | Model | Why |
|---|---|---|
| 2.1 Tax kernel extraction | **opus** | The highest-leverage and highest-risk item in the programme; four findings depend on it. |
| 2.2 Register the tax stage | sonnet | Scoped, once 2.1 defines the shape. |
| 2.3 Shared sweep runner + gating | **opus** | Cross-cutting, three call sites, and it changes recommendations. |
| 2.4 Retire JSON/YAML backends | sonnet | Scoped deletion with a user-visible switch to remove. |
| 2.5 Collapse SQLite stores | **opus** | Touches the config-resolution path; this exact change failed once before. |
| 2.6 Thread lifetime exemption | sonnet | Scoped, three known call sites. |
| 2.7 Step-up reconciliation | **opus** | Requires deciding which fraction is *correct*, not just making them agree. |
| 2.9 RMD Joint Life table + statutory-start-age check | sonnet | Well-specified table lookup with a defined fallback; the start-age cross-check is a bounded reading task. |
| 2.11 Materiality gating (generalization) | **opus** | Client-facing recommendation logic; wrong gating is a liability. |
| 2.12 Integration tests | sonnet | Scoped new test layer against a defined seam. |
| 2.13 Error-path tests | sonnet | Scoped; requires deciding the correct user-visible behaviour. |
| 2.14 Three e2e specs | sonnet | Scoped Playwright work following an existing pattern. |
| 2.15 Suffix rename + checker | **haiku** | Mechanical rename under a stated rule, plus a small checker. |
| 2.16 `workbook_common` cleanup | sonnet | Scoped; import fan-out needs care. |
| 2.17 `report_spec` once | **haiku** | Delete one of two identical derivations. |
| 2.18 Help-pane retirement + editorial split | **opus** | Resolves a named cross-discipline conflict; layout plus content design. |
| 2.19 Merge Preflight into Build | sonnet | Scoped UI restructure with copy changes. |
| 2.20 Coordination cards | sonnet | New read-only component on three pages. |
| 2.21 README end-user section | **haiku** | Two lines of prose. |

**Wave 3**

| Item | Model | Why |
|---|---|---|
| 3.1 Guardrail + RMD-net-headroom verification | sonnet | Focused investigation with a binary outcome; must produce a test, not a reading of the code. |
| 3.2 Extend conversion window | **opus** | Changes the flagship recommendation; interacts with guardrails and build budget. |
| 3.3 Heir tax model | **opus** | Legal correctness (EDB classes) plus the highest-leverage assumption in the Roth objective. |
| 3.4 Bracket-target withdrawal policy | **opus** | New engine policy inside the most delicate true-up logic. |
| 3.5 Adoptable spending policy + conditional-success relabelling | **opus** | Runs in both engines, moves the headline success probability, and changes what that number *means* — the relabelling is not optional polish. |
| 3.6 New York estate tax + three-year gift add-back | **opus** | Statutory table plus a cliff plus an add-back; getting it subtly wrong is worse than `not_modeled`. |
| 3.7 SS breakeven presentation | sonnet | Presentation over existing rows. |
| 3.8 SS longevity refinement | sonnet | Adds one dimension to a runner 2.3 already designed. |
| 3.10 Engine decomposition (ongoing) | **opus** | The remaining thirteen stages of the highest-risk refactor. |
| 3.11 Frontend real imports (ongoing) | sonnet | Repetitive and scoped, but load order caused a real outage — needs care. |
| 3.12 `results_model` extension (ongoing) | sonnet | Page-by-page, each with a clear before/after. |
| 3.13 `parse_client` split (ongoing) | **opus** | Hundreds of engine keys; a wrong cut is silent. |
| 3.14 HSA/YTD audit | **haiku** | Mechanical comparison; act only on confirmed duplication. |

---

## 7. Appendix — open questions for the user

These are decisions the review cannot make on the reader's behalf. Each names the finding it affects and what changes depending on the answer.

1. **Is the "no build step" constraint on the frontend negotiable?** (A7) If it is, a bundler is the better answer than incremental import conversion — faster to a clean end state and it eliminates the load-order fragility that caused the 2026-07-22 outage outright. The recommendation of Option 1 rests entirely on treating that constraint as fixed.

2. **Does anyone use the JSON/YAML config backends?** (A3) They are user-switchable and untested, and nothing reads them under the shipped configuration. Retiring them is the cheap first step toward collapsing the four data stores — but it removes a switch someone may be relying on.

3. **What tolerance is acceptable between the vectorized and exact-scalar Monte Carlo engines?** (A1) **Blocks 1.1. Must be answered before Wave 1 begins.** The fidelity test needs a number. This is a financial judgment (how much probability-of-success drift is acceptable?), not an engineering one — and 1.1 cannot be verified without it, so it is a gate rather than a background question.

4. **After the LTCG equivalence diagnostic (1.12): if the two inflation indices genuinely diverge in shipped configs, which one is correct?** (A6) `irmaa_inflator` and `brk_inf` / `fed_tax_bracket_inflator` are independently settable and differ in at least one fixture (0.028 vs 0.02). Unifying changes reported LTCG tax and requires golden-master regeneration.

5. **Should the Executive Summary show non-material recommendations at all?** (F2) Option 3 shows them as "reviewed — not material for this household", which demonstrates diligence. Option 2 drops them entirely, which is cleaner but loses the evidence of consideration. This is a client-communication preference.

6. **Is "advisor-ready" worth defining, or should it be replaced?** (D2) Defining it in `TERM_NOTES` is nearly free since the code path is being touched anyway. Replacing it with a concrete phrase is arguably better writing but touches five call sites.

7. **Should `report_spec` ultimately be deleted or made load-bearing?** (A13) The recommendation is to compute it once and defer. Whoever owns the reporting roadmap should decide whether the Results Explorer should eventually consume it.

8. **How much build-time regression is acceptable in exchange for the richer planning analyses?** (§3.2, F3, F11) A1 and A4 create the budget; F3 and F11 spend it. If the target is "no slower than today", the sweeps must be gated before the window is extended. If some regression is acceptable, the sequencing loosens.

9. **Is 50-state coverage a product goal?** (F5) The plan completes New York only, on the grounds that it is the one case where the tool claims support and silently returns zero. Broader expansion is a product decision with a real maintenance tail.

10. **Who signs off on recommendation changes?** (A4, F2, F3) **Blocks 2.3. Must be answered before that item starts.** Several items change *which strategy the plan recommends*. Code review is not sufficient for these. The plan assumes a planner sign-off gate exists; if it does not, one needs to be created before Wave 2 item 2.3 — and 1.1 in Wave 1 also carries a sign-off requirement, so in practice the gate is needed earlier than 2.3 even though 2.3 is where it becomes structurally blocking.

11. **Should the account-taxonomy guardrail (1.16) block, or warn first?** (F9) The item as written makes an unrecognized account name a hard, user-facing error. That is the right end state — it is the only finding producing a silently wrong answer today. But a saved plan that has been building happily with a misclassified account will begin failing on the first build after upgrade, which is a support event even though the plan was already wrong. A warn-loudly-then-block-next-release phasing avoids that at the cost of leaving the wrong answer in circulation for one more release. This is a product call about existing users, not a modelling question, and the review does not make it.

### Noted disagreements with the planner's review pass

Both positions are recorded rather than resolved, per the review's convention of leaving decisions visible.

**D-1. Should item 1.15 (KPI snapshots) be a hard blocker on item 1.1 (the engine-default flip)?**

*Planner's position:* yes. Items 1.1, 3.2, 3.4 and 3.5 all move the headline probability of success; F13's snapshot archive is the only mechanism that can explain why, and it must exist before those land. Otherwise the largest single movement in the number — the engine flip — is the one movement with no series to place it in.

*Reviewer's position:* the move of F13 from Wave 3 to Wave 1 is accepted without reservation and is a genuine improvement. The narrower question is whether 1.1 should *wait* on 1.15. 1.1 is the highest-leverage and highest-risk item in the programme, it already carries its own attribution mechanism (a before/after projection diff on the demo plan with planner sign-off), and 1.15 is M effort. Hard-blocking a High-risk M item on a Low-risk M item that shares no files inverts the usual priority. The verification line has been added to 1.1 as requested; what has *not* been asserted is that 1.1 must be the later of the two to merge.

*Practical effect either way:* small. Both items sit in the same wave and both are marked parallel-safe. If 1.15 lands first the question is moot; if 1.1 lands first, the flip's before/after diff should be retained and back-filled into the snapshot series once 1.15 exists, so nothing is lost.

**D-2. Placement of item 1.17 (tax-capacity worksheet) relative to the tax-kernel extraction (2.1).**

*Planner's position:* Wave 1. It derives nothing new, has no prerequisite, and the document elsewhere calls it the highest planner-value-to-engineering-cost item in the review — leaving it mid-Wave-2 makes the document contradict its own priority claim.

*Reviewer's position:* agreed, and the move is made. The one caveat worth recording is that the sheet reads bracket, IRMAA and 0%-LTCG headroom from the same computations 2.1 will later repoint at `tax_kernel`. Building the sheet first means a small, mechanical follow-up inside 2.1, and it means the sheet is a useful *detector* for 2.1 — any figure that moves when the kernel is extracted is a bug in the extraction. That is a reason to sequence it first, not a reason to defer it, but the follow-up should be planned rather than discovered. It is written into 1.17's verification column.

---

## 8. Planner sign-off

The CFP-level reviewer re-read this document in full against the source and returned a verdict plus fourteen edits. All fourteen were spot-checked against the repository (`src/core.py:754`, `src/planning_engines.py:1872` and `:1874` among them) and all fourteen have been applied. Two carry a recorded disagreement in the appendix (D-1, D-2); neither disagreement blocked the edit.

**Verdict.** All thirteen financial-planning findings are present, evidenced accurately, and none were softened. The F1 cross-check correction — that the withdrawal-order UI copy is honest and the engine is the defect — is handled correctly, and §4 explicitly forbids re-deriving the copy fix. The core sequencing insight in §3.2 is right and is the document's best work: A1 and A4 create the compute budget that F3 and F11 spend, and F11's longevity refinement genuinely is the second dimension of A4's refine phase rather than a separate pass. **Waves 1–3 are not reordered wholesale.**

**The one structural weakness found, and how it was closed.** Four separate items move the flagship probability-of-success percentage — 1.1, 3.2, 3.4 and 3.5 — and only one of them (3.5, from F6) was originally asked to disclose why. Three changes close this together:
1. F13's KPI snapshot archive moved from Wave 3 to Wave 1 (item 1.15), reframed as a **precondition** of the number-moving work rather than a payoff of it;
2. item 3.5 now carries mandatory **conditional-success relabelling** — under any non-fixed-real spending policy, the label, the glossary note and the KPI tile must say that success is conditional on the modelled cuts, and the tile must show the worst modelled cut beside the percentage;
3. item 1.5 now **specifies the "probability of success" `TERM_NOTES` string immediately**, as one shared string across the glossary entry and the new KPI-tile tooltip, so that the Wave 3 qualifier attaches to a single definition rather than to two that have drifted.

**What changed as a result — the complete list.**

*Schedule changes (three items moved, one prerequisite deleted):*
- **3.9 → 1.15** — build KPI snapshots, moved to Wave 1; it is the instrument for the rest of the programme.
- **2.8 → 1.16** — account-taxonomy guardrail, moved to Wave 1; it is the only finding producing a wrong answer today, silently, and it is S effort with no prerequisite.
- **2.10 → 1.17** — tax-capacity worksheet, moved to Wave 1; the document called it the highest value-to-cost item in the review while scheduling it mid-Wave-2.
- **2.9 prerequisite "2.1" deleted** — `rmd_divisor` is a pure age-keyed table lookup unrelated to the tax kernel's bracket/IRMAA/LTCG closures; the item now runs in parallel from the start of Wave 2.
- Moved numbers are **retired, not reused**, so cross-references elsewhere remain unambiguous.

*Scope widened on five items:*
- **1.10** — no longer just the fabricated CST figure; it must also suppress the CST recommendation row below the exemption. Fixing the figure alone would have left an unqualified bare recommendation with no number attached for a whole wave — worse than the fabricated number. **2.11** is correspondingly re-described as *generalizing* this predicate to LTC/S-Corp/QTIP rather than introducing it.
- **2.9** — must confirm the age-72 floor in `rmd_divisor` cannot fire ahead of `statutory_rmd_start_age` (the SECURE 2.0 73/75 ramp).
- **3.1** — must verify with an explicit test that post-RMD-age conversion headroom is net of the year's RMD. `pre_non_ss` does include `rmd_total` today, but that path has never executed in a window extending past RMD age, so it is an assumption rather than a verified behaviour.
- **3.2** — the window must stay open through the survivor's single-filer years (the widow's-bracket case is a filing-status transition, and is the more valuable of the two windows); both existing controls stay authoritative when explicitly set, with only the default changing; and the hardcoded `400000` bracket-top fallback is fixed while the function is open.
- **3.6** — must include New York's three-year gift add-back, which consumes the lifetime-gift series already threaded by its own prerequisite (2.6). Without it the cliff calculation completes but still under-reports for exactly the households most likely to be near the cliff.

*Corrections to stated positions:*
- **F6 evidence softened.** "Systematically overstates ruin risk" overclaimed a uniform direction and magnitude; it now reads as an overstatement *for households with meaningful discretionary spending*, because the model assumes a retiree who never adjusts, with a household-specific effect size.
- **F4 / item 3.3 default corrected.** "Defaults to today's values so existing plans do not move" is right for heir baseline income and state but wrong for beneficiary class: today's "everyone gets the 10-year rule" default is legally incorrect for spouse, minor-child, disabled-or-chronically-ill, and less-than-ten-years-younger beneficiaries. Class now defaults to the class inferred from existing beneficiary and titling data, and plans whose after-tax legacy figure moves are flagged as a **correction, not suppressed**.
- **F3 evidence extended** with the `400000` bracket-top fallback at `src/planning_engines.py:1872`.

*Appendix:*
- Open question 3 (vectorized-versus-exact-scalar tolerance) marked **"Blocks 1.1. Must be answered before Wave 1 begins."**
- Open question 10 (recommendation-change sign-off gate) marked **"Blocks 2.3."**
- New open question 11 added: whether the account-taxonomy guardrail should block outright or warn first for existing plans.
- Two noted disagreements recorded with both positions stated (D-1: whether 1.15 should hard-block 1.1; D-2: 1.17's placement relative to the tax-kernel extraction).

**Planner's closing note.** *"Nothing in the plan hides a number a planner needs or degrades planning quality as such."*

---

*End of review. Cross-check pass completed with zero findings refuted; corrections from that pass are carried inline and marked throughout. A subsequent financial-planner sign-off pass produced fourteen edits, all applied and summarized in §8, with two noted disagreements recorded in the appendix. No source file was modified in producing this document.*
