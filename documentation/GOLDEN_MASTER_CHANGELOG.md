

## 2026-07-20 — Item 2.4 (P7): excess-spousal Social Security — timing gate + SSA amount

`deterministic_engine.py`'s spousal Social Security top-up was wrong in two ways.
(1) It was paid regardless of whether the *worker* (whose PIA the spousal amount
derives from) had actually filed — real SSA law bars a spousal benefit until the
worker files. (2) The amount used `max(own_benefit, 0.5*worker_PIA*factor)`, which
both discards the claimant's permanent early-claim reduction on their own record
and applies the *own-benefit* reduction schedule to the spousal amount.

Replaced with the SSA "excess spousal" method, computed per year inside the
projection loop:

    own_reduced_benefit + max(0, 0.5*worker_PIA - own_PIA) * excess_factor

paid only from the worker's claim year onward and only while both spouses are
alive. `excess_factor` is a new helper (`_ss_spousal_excess_factor`) implementing
the spousal reduction schedule — 25/36 of 1%/month for the first 36 months before
FRA, then 5/12 of 1%/month, and **no** delayed-retirement credits past FRA
(capped at 1.0) — keyed to the claimant's age when the spousal benefit first
becomes payable (the later of their own filing and the worker's filing). The
own-benefit records (`h_monthly_claim`/`w_monthly_claim`) are now kept free of any
spousal amount, which also makes the downstream survivor benefit derive purely
from the deceased's own retirement record (a correctness improvement, not a
separate change).

Judgment call, flagged: the plan's one-line "correct formula" wrote the reduction
factor against `0.5*worker_PIA` and subtracted own PIA afterward. That conflicts
with its own prose ("only THEN has its own reduction schedule applied to the
excess"). Per SSA's published dual-entitlement methodology the age reduction
applies to the *excess* (0.5*worker_PIA − own_PIA), so the reduction is applied
after the own-PIA offset, as coded above.

Golden-master impact:
- **Synthetic gate** (`tests/fixtures/synthetic_golden_master_cases.json`): all 9
  pre-existing scenarios are UNCHANGED to the cent. Each has a dominant
  higher-earner PIA and symmetric (both-age-70) claiming, so half the worker's PIA
  never exceeds the claimant's own PIA — the old `max()` and the new excess method
  both resolve to own-benefit-only. Added one new scenario,
  `split_claiming_spousal` (higher earner delays to 70, lower earner claims at 62),
  the only scenario in which the excess-spousal path is live, so the mandatory gate
  now exercises the fix (terminal NW 12,238,486.87; lifetime tax 710,025.22).
- **Frozen sample plan** (`tests/test_199_frozen_sample_plan_golden_master.py`):
  pins UNCHANGED (6,536,759.61 / 1,527,729.93) — that household has no live
  excess-spousal situation. No regeneration was required.

New coverage: `tests/test_200_spousal_ss_excess_benefit.py` pins the 62/70 timing
gate and step-up, a reduced-excess case (spousal begins at age 63 → 0.70 excess
factor, distinct from the 0.75 own-benefit factor at the same 48 months), and the
no-top-up case where both spouses' own PIAs dominate.


## 2026-07-18 — Sample-plan golden-master baselines demoted to warn-only

`tests/test_2_recommendations.py` pinned two dollar figures from the live sample
plan (`input/client_data.csv` plus the sibling `client_*.csv` files `load_csv`
merges into it). Because that data is edited routinely, the pin failed on ordinary
plan-data churn, and each failure was resolved by regenerating the number and
appending an explanatory comment — about 130 lines of them by 2026-07.

Those two assertions are now a warn-only diagnostic. The structural assertions
(zero validation failures, zero warnings, 2026-2056 across 31 rows) still block.
Engine regressions are gated by the synthetic golden master, which reads no client
data and so cannot be moved by a plan edit.

The per-item history that used to live in the test body is preserved below.

- Golden-master constants are tied to input/client_data.csv (and its transaction/budget-derived spend base) as of this commit. Regenerate them deliberately after intentional plan-data changes; a mismatch otherwise usually means a real projection-engine regression.
- **Item 141 (2026-07)** — the projection spend_base dropped from 129,059 to 124,059 after fixing a double-count in spending_budget_resolver — a Core Expenses category (charitable giving) that carried BOTH a category budget row and a detail line was counted twice. The 5,000/yr lower spend reinvests as surplus, so terminal net worth and later-year taxes rise.
- **Item 142 (2026-07-07 12:09 PM)** — spending budget line items updated manually (dentist, medical, gifts, health club, vitamins) and miscellaneous/uncategorized cleared out after taxonomy changes. Terminal net worth increased to ~12.4M.
- **Item 143 (2026-07-08)** — one-time $40k family gift modeled as a significant_gifts Large Discretionary line for 2026, plus an app re-sync of client_spending_budget.csv (several category budgets adjusted, e.g. entertainment/furniture/lawn lowered). This projection path does not apply the current-year YTD blend, so the gift's effect here is just the $40k 2026 lump; net of the re-synced budgets, terminal net worth settles to ~11.32M and lifetime tax to ~1.46M. Regenerate from a clean `git worktree` checkout (no untracked local state) — a plain working-tree run can pick up gitignored local caches (e.g. output/pricing_diagnostics.json, live holdings snapshots) that inflate balances by $1M+ versus CI's committed-only checkout.
- **Item 165 (2026-07-08)** — DAF (Donor Advised Fund) feature activated (input/client_assets.csv `enabled` flipped FALSE->TRUE). DAF contributions reduce taxable income/AGI which lowers lifetime tax and, combined with the tax savings compounding as reinvested surplus, raises terminal net worth to ~12.24M and lifetime tax to ~1.55M.
- **Item 166 (2026-07-09)** — dividend reinvestment feature. Dividends/interest no longer directly fund spending as "Portfolio Income" — they either compound into the holding or convert to account-internal cash (Reinvest Dividends toggle, per account and a global override; this sample plan's client_household.csv has the global switch on). Removing that free cash from the income funding calc means the withdrawal cascade sells more to cover the same spending, realizing capital gains tax the old model avoided. Terminal net worth drops to ~12.11M and lifetime tax to ~1.50M.
- **Item 167 (2026-07-09)** — tax-loss harvesting feature (tlh_policy defaults to off, so the engine change itself is a no-op) landed alongside plan-data edits made through the running app during that work: annual_earned_income raised to $309,620 (from $290,000), a Liquidity Buffer reserve activated for 2027-2029, a $5,000 charitable-giving budget line removed, and Medicare Part B/D/Medigap premiums rebalanced. Net effect: terminal net worth drops to ~9.40M and lifetime tax to ~1.31M — a real plan-data change, not an engine regression.
- **Item 185 (2026-07-14)** — the elective pre-tax IRA/401(k) withdrawal used to size itself off a flat federal-marginal-rate gross-up (withdraw_pretax_elective's `gross_up`), which ignores state tax and bracket integration, and its ordinary income was never added to agi/taxable_inc. Added a bounded fixed-point true-up (mirroring the existing LTCG/NIIT loop) that re-solves against the real progressive fed+state tax and folds the withdrawal into agi/taxable_inc/irmaa_magi. This is why some rows previously showed both an elective withdrawal and a "reinvested surplus" in the cash-bridge sheet at the same time. Also fixed a second, related bug the true-up exposed: `new_gap` was reduced by a flat-rate-estimated `net_cash`, while required_portfolio_ draws (the cash-bridge sheet and this true-up) count the full gross withdrawal — the two conventions double-booked/mis-booked the tax and left the cash-bridge reconciliation off by the mismatch (confirmed via `git stash` against the pre-Item-185 code — this reconciliation gap, smaller but present, pre-dates this fix). `new_gap` now reduces by the full gross amount, matching withdraw_taxable_trust's convention, so the true-up's real tax delta is the only tax accounting in play. Elective withdrawals end up smaller (correctly sized, not over-drawn), letting more compound tax-deferred: terminal net worth rises to ~7.32M and lifetime tax rises to ~1.62M.
- These constants are now fully reproducible: tests/conftest.py pins holdings pricing to OFFLINE, so starting balances come from the committed cache snapshot rather than live market data. Confirmed identical across Python 3.12 and 3.14 on Windows (both interpreters agree to the cent); regenerate deliberately after an intentional engine/plan-data change. Baselines reflect the committed sample inputs plus two intentional engine changes: item 182 (pre-65 bridge premium applies to any pre-65 person regardless of retirement year) and item 184 (real-estate tax is funded as a cash need, not only used for the SALT deduction). Values were regenerated against clean committed inputs — a fresh checkout / CI reproduces them (holdings are pinned OFFLINE via tests/conftest.py).
- **Item 168 (2026-07-14)** — `load_csv` merges every sibling client_*.csv file, so this sample config picks up client_household.csv's real per-age SS benefit tables even though client_data.csv itself has no SS fields. Fixing the SS benefit self-cancellation bug (13b089a) moved the claimed amount from a flat back-solved number to a real per-age table lookup (a small change: ~$5,080/mo flat -> the real age-70 figure), and separately fixed Social Security's present value being silently excluded from the fixed-income coverage calculation (ss_pv was always 0 before the fix). Together these ripple through the withdrawal/tax cascade to shift terminal net worth by ~$33k. Verified via `git worktree` bisection: the prior pin (6,745,962.88 / 971,088.96) reproduces exactly at commit dcfe794, and the intermediate value (6,712,722.02 / 965,325.67) reproduces exactly at 13b089a, in a clean checkout free of gitignored local cache files (which can inflate a plain working-tree run by $800k+ - see item 143).
- **Item 169 (2026-07-14)** — household plan update - Social Security claim age moved from 70 to 69 for both spouses (matching Sheet 10's projection-sweep recommendation), and FRA Age set explicitly to 67 (same as the auto-derived default, no behavior change). Claiming one year earlier changes which ss_benefit_age_* table entry is used and shifts the whole withdrawal/tax cascade.
- **Item 185 (2026-07-14)** — elective pre-tax IRA/401(k) withdrawal ordinary-tax true-up + gap/net_cash convention fix (see deterministic_engine.py's _ira_elective_ordinary_tax_delta) — terminal net worth rises to ~7.32M, lifetime tax to ~1.62M.
- **Item 186 (2026-07-14)** — household plan update - Member 1 Social Security claim age moved from 69 to 68 (Member 2 unchanged at 69). Terminal net worth rises to ~7.36M, lifetime tax to ~1.63M.
- The previously-noted order-dependency (this value shifting ~$800k depending on whether test_forecast_api_service_uses_same_config_ contract ran first) was the same pricing-cache leak fixed by the tests/conftest.py _reset_market_data_price_cache autouse fixture; this value is now stable both in full-suite and isolated runs.
- Regenerated 2026-07-17 against the committed frozen-price snapshot (tests/golden_pricing.py) after the b246d19 plan-data drift — SS claim age, annuity dividend rates, and liquidity buffer changed under a UI-titled commit ("Combine SS policy fields onto one row"). Holdings pricing is now frozen rather than read from the untracked local OFFLINE cache, so this pin is deterministic and portable across machines.


## 2026-07-15 — Remove advisor/household language mode and the Advanced Workflow Steps toggle
- Removed the browser-local advisor/household display language mode entirely (state, Settings card, page-header banner, and text-substitution engine). Page copy now renders as authored, with no display-mode preference. No calculations, saved values, build snapshots, or exports were ever affected by it.
- Removed the "Advanced Workflow Steps" preference toggle and its Settings "Workflow view" card. Its only real effect was surfacing the Special Strategies page, whose content is already gated by Optional Modules.
- Special Strategies navigation visibility now follows capability: the page appears once the HELOC or Charitable Giving optional module is enabled, so Optional Modules is the single source of truth. The other advanced-flagged pages were already `hidden` and reachable only via Settings/links; that is unchanged.


## 2026-06-27 - Strategy/Asset Service Modularization
- Added `src/server_services/strategy_asset_service.py` as the feature-owned service for strategy, asset, estate, insurance, reference-import, seed-row, and config-sync helper behavior.
- Refactored `src/server/plan_routes.py` strategy/assets/estate/insurance routes into thin adapters for permissions, CSV-write checks, request extraction, and JSON serialization.
- Preserved existing route URLs and payload shapes for withdrawal order, large discretionary expenses, forced Roth conversions, liquidity buffers, other assets, 529 plans, estate states, trust accounts, insurance policies, capital-market imports, housing seed, healthcare OOP seed, and config sync.
- Extended route ownership, API contracts, packaging checks, and clean-overlay validation for the new service seam.
# v10 Planning Workbench consolidation
- Implemented `PLANNING_WORKBENCH_CONSOLIDATION_PROPOSAL.md` as a dedicated Planning Workbench guided step.
- Added browser-local `planning_case_v1` cases and shared `src/planning_workbench.py` contract helpers.
- Unified manual edits, strategy levers, scenario overrides, and stress-suite assumptions into one change-set/override vocabulary.
- Renamed legacy surfaces in-place: Strategy Levers, Scenario Change Sets, Stress Suite & Monte Carlo, and Impact & Build History.
- Added Build Impact comparison context for selected planning cases while preserving the guardrail that cases never mutate the saved plan automatically.


## 2026-06-26 — Flask-free local HTTP runtime

- Implemented the Flask removal proposal with `src/http_runtime`, a dependency-free local route registry, request/response facade, test client, and `ThreadingHTTPServer` adapter.
- Updated desktop mode so pywebview API calls use the local route registry instead of a Flask test client.
- Updated server mode to launch the stdlib local HTTP runtime.
- Removed Flask/Werkzeug/Jinja/Click/ItsDangerous/MarkupSafe/Waitress from runtime requirements and PyInstaller packaging hints.
- Added regression coverage for importing and calling server routes without third-party web framework dependencies.

# v10 page-local recommendation engine

- Added `page_recommendations_v1` as an explainable, non-automatic recommendation layer on Roth conversion, allocation, core spending, and Social Security pages.
- Each recommendation explains why it matters and links back to the editable source input that controls the suggestion.
- The change is UI-only: it stages no values automatically and does not alter calculations, saved plan data, build snapshots, projection formulas, tax logic, exports, or workbook sheet definitions.

# v10 local backup scheduler

- Added opt-in `local_backup_scheduler_v1` for retention-limited local `.rpx` SQLite backups.
- Added Normal Settings controls for daily/per-build cadence, manual backup, and retention count.
- Backups are opportunistic after Save Changes or successful builds; no background service is started and projection formulas, tax logic, workbook sheets, and saved plan values are unchanged.

# v10 import preview contracts

- Added side-effect-free `import_preview_v1` previews for YTD transaction CSV uploads and holdings CSV replacement.
- Transaction previews report row counts, current-year filtering, date range, duplicate candidates, unmapped categories, and new transaction accounts before writing.
- Holdings previews report row counts, duplicate lot candidates, purchase-date range, account/symbol summaries, security-master gaps, data-quality flags, and estimated cost basis before staging the imported table.
- The change is additive: existing upload/save routes remain, and holdings imports are staged in the browser until Save Changes persists them.

# v10 household/advisor language mode

- Added browser-local household/advisor display language mode in Normal Settings.
- Page headers and help framing now use the selected display mode where safe, with a visible mode banner on workflow pages.
- The change is display-only: saved plan data, calculations, build snapshots, exports, projection formulas, tax logic, and workbook sheet definitions are unchanged.

# v10 scenario templates and saved scenario sets

- Added a Scenarios-page management panel with deterministic templates for conservative markets, spending pressure, retire-later bridge, and home-sale liquidity.
- Added browser-local `scenario_set_v1` saved named scenario sets, including apply/delete controls and side-by-side diff previews against current scenario assumptions.
- The change is UI-only: it stages scenario assumption edits through existing fields and does not alter projection formulas, tax logic, workbook sheet definitions, or build contracts.

# v10 Build Impact narrative source links

- Added a natural-language Build Impact summary for the latest successful build.
- Captured edited fields now carry source-page metadata, and Build Impact links changes back to the guided workflow page where the value should be reviewed.
- The change is UI/reporting-only: projection formulas, tax logic, and workbook sheet definitions are unchanged.

# v10 pricing snapshot freeze

- Added `pricing_snapshot_freeze_v1` as the next Phase 2 roadmap contract for advisor-report reproducibility.
- Added freeze/unfreeze API routes, Normal Settings controls, build-preflight status, frozen-price build application, and regression coverage.
- Frozen pricing is additive: projection formulas, tax logic, and workbook sheet definitions are unchanged.

# v10 migration architecture refactor

- Implemented local-only v10 architecture layer with typed PlanInput, SQLite snapshots, versioned tax law dataset, projection pipeline contract, report specs, what-if scenarios, and local meta-optimizer.
- Results Explorer continues to use the semantic result model first, with workbook parsing as legacy fallback.
- Removed hosted/multi-user behavior from v10 runtime/UI surfaces and updated release/cache labels to v10.
- Completed three validation/repair rounds; full collected repository suite passed in chunks: 271 tests plus 16 subtests.

## v10 Results Explorer semantic model refactor
- Added a shared semantic Results Explorer model (`results_explorer_model.json`) generated from projection artifacts during workbook builds.
- Results Explorer now prefers the semantic model and only uses Excel workbook parsing as a backward-compatible fallback.
- Added semantic Chart Dashboard, Cash Flow, Net Worth, Lifetime Tax, Asset Allocation, and Executive Summary pages.
- Labeled the build as 8.4 and updated dashboard cache-busters.

## v8.3 YTD transaction pagination and chart dashboard projection fallback
- Added YTD Transactions pagination for filtered result sets over 500 rows, with First, Previous, Next, and Last controls.
- Reset transaction pagination when search, filters, or sorting changes so the user stays on a valid page.
- Added browser-native Chart Dashboard fallback charts derived from ordinary projection result sheets when hidden chart-source ranges and embedded Excel chart references are not readable.
- Removed the rebuild-only Chart Dashboard fallback message for workbooks that still contain enough projection data to chart in the UI.
- Bumped frontend/static cache-busters and synced dashboard assets.


## v8.3 Results Explorer cashflow heading/progress UX fix
- Smoothed Results Explorer load progress so it updates continuously and stays capped until the server returns real page data.
- Changed progress label to an estimated percentage to avoid implying exact server-side progress during a single request.
- Improved result table heading detection so Cashflow and other wide sheets use workbook-derived heading rows instead of generic Measure labels.
- Replaced generic column-group button labels with human-readable workbook labels or year ranges.
- Added sticky section/table heading support so the meaningful heading row stays visible while scrolling.
- Bumped frontend/static cache-busters and synced dashboard assets.


## v8.3 Results Explorer browser chart rendering fallback
- Added Results Explorer chart reconstruction from embedded Excel chart objects and their source-range formulas when the hidden chart data sheet is missing or stale.
- Kept Chart Dashboard chart-only in the UI while avoiding the fallback message that asked users to download the workbook for charts.
- Added compatibility fallback for older visible chart-helper tables so existing workbooks can still display charts in the browser.
- Updated Chart Dashboard progress/help text to describe workbook chart data rather than hidden ranges only.
- Bumped frontend/static cache-busters and added regression coverage for embedded-chart fallback rendering.


## v8.3 UI startup bootfix
- Restored missing frontend startup/save/build API helper functions removed during the Results Explorer polling patch.
- Fixed full UI hanging at the initial “Checking server...” status before any /api/v8/ping request was sent.
- Bumped frontend/static cache-busters.


## 2026-06-13 - YTD Transaction Table Amount Formatting Fix
- Tightened the YTD Transactions Date column to reduce wasted horizontal space.
- Displayed transaction Amount cells as USD currency while preserving raw numeric values for save/export.
- Highlighted negative transaction amounts in red with tabular-number alignment for faster scanning.
- Added focus/blur behavior so Amount fields edit as raw numbers and return to currency display after editing.
- Bumped dashboard JS/CSS cache-busters and synced frontend/static dashboard assets.


## 2026-06-13 - Results Explorer loading resilience
- Renamed remaining user-facing workbook-result language to Results Explorer.
- Added browser-safe selected-page loading for dense Result Explorer sheets, including Asset Allocation, so they return a bounded UI preview instead of hanging at the progress bar.
- Added chart dashboard series/slice compaction so native UI chart rendering stays responsive while the downloadable workbook remains the full Excel source.
- Added selected-sheet request sequencing so stale in-flight result loads cannot overwrite the newly selected result page.
- Bumped dashboard JS/CSS cache-busters and kept frontend/static dashboard assets in sync.


## 2026-06-13 - YTD Account Mapping Liability and Current Value UI Fix
- Removed Prior Year End Date from the visible YTD account/source mapping table; the backend still defaults legacy/internal 12/31 dates for growth series anchoring.
- Kept editable Current Value immediately after Prior Year End Balance for non-investment account/source types.
- Removed the disabled Add transaction account selector/button from the mapping UI; uploaded transaction accounts continue to seed automatically.
- Replaced the flat account-type pulldown with grouped Assets and income sources, Liabilities, and Other sections.
- Replaced the generic Liability option with Credit card, Mortgage, HELOC, Loan, and Other liability options, while normalizing legacy Liability values forward.
- Bumped dashboard JS/CSS cache-busters and synced frontend/static dashboard assets.


## 2026-06-13 - Detailed Results Chart-Only Dashboard and UI Grouping Fix
- Changed the workbook Chart Dashboard sheet to show charts only; chart source data is written to a hidden `_Chart Dashboard Data` sheet.
- Changed the Detailed Results explorer Chart Dashboard page to render native UI chart cards instead of chart-helper data tables.
- Hid workbook helper sheets from the Detailed Results navigation.
- Removed Excel row numbers and column-letter fallbacks from the explorer tables.
- Added UI-native column grouping for wide result tables, with detail column groups collapsed by default.
- Kept search behavior usable by expanding all columns while a sheet search is active.
- Bumped dashboard JS/CSS cache-busters and synced frontend/static dashboard assets.

## 2026-06-13 - YTD Account Current Value Inline Add Fix
- Added a Current Value column to YTD account/source mapping for non-investment account types.
- Investment current values remain disabled in the YTD table because they are derived from mapped client_holdings.csv holdings.
- Replaced the Add account/source prompt modal with inline account/source name and account-type controls.
- Removed the Notes column from the YTD account/source table to save horizontal space.
- Added sticky action-column styling so the Delete button remains visible while horizontally scrolling.
- Bumped dashboard JS/CSS cache-busters and synced frontend/static dashboard assets.


## 2026-06-13 - Detailed Results Nav Persistence Fix
- Preserved the View Detailed Results left-nav expansion state across dashboard re-renders, progress ticks, workbook refreshes, and route changes.
- Saved the expanded/collapsed state in browser localStorage so the nav remains open after refresh until the user closes it.
- Automatically keeps the detailed-results nav open when the detailed-results screen or a workbook sheet is selected.
- Broadened regression checks for the detailed-results nav state wiring and cache-buster.
- Bumped dashboard JS/CSS cache-busters.

## 2026-06-13 - Detailed Results Loading Progress Fix
- Added a visible staged progress display for View Detailed Results while the workbook explorer loads.
- The progress display now appears both in the main detailed-results screen and the left-nav detailed-results group.
- Added a 120-second timeout for the detailed-results API request so the UI reports a recoverable error instead of staying indefinitely on Loading workbook results.
- Added detailed-results refresh/error guidance and regression checks for the progress UI.
- Bumped dashboard JS/CSS cache-busters.


## 2026-06-13 - Detailed Workbook Results Explorer
- Added a collapsed bottom-left navigation group labeled View Detailed Results.
- Added a read-only workbook result explorer that parses retirement_plan.xlsx into topic-grouped sheets and natural blank-row-separated sections.
- Added /api/v8/detailed-results for workbook-aware JSON output, preserving all non-blank workbook rows and cell values.
- Added section-level accordions, sheet/category navigation, in-sheet search, sticky row/column headers, and workbook download/refresh actions.
- Bumped dashboard JS/CSS cache-busters.


## 2026-06-13 - YTD Income Category Whitelist Fix
- Changed YTD income classification to use only the explicit income categories: Paychecks, RedMane Annual Note P&I, Dividends and Capital Gains, other Income, and Interest.
- Treated positive cash/spending-account transactions outside those categories as refunds that reduce spending by category.
- Kept Transfer, Buy, Sell, and other ignored flows out of YTD income.
- Exposed the allowed income-category list in the YTD summary and added it to the YTD income chart helper text.
- Bumped dashboard JS cache-buster.

## 2026-06-13 - YTD Growth Straight-Line Holdings Chart Fix
- Changed displayed YTD investment growth to current mapped holdings value from client_holdings.csv minus the 12/31 prior-year balance.
- Left net investment cashflow visible as diagnostics only; it no longer reduces the YTD growth chart/value.
- Added a dedicated two-point growth_series from the 12/31 value to today's mapped holdings value so the YTD growth chart renders as a straight line.
- Updated the YTD growth card to show current value as the comparison value and use range scaling so the line movement is visible.
- Bumped dashboard JS cache-buster.

## 2026-06-13 - YTD Account Setup Save Button Activation Fix
- Fixed YTD account-mapping dirty-state behavior so Save account setup activates immediately after editing mapped account, prior-year balance/date, notes, or role without requiring a full table re-render.
- Fixed Save transaction edits to activate immediately after inline transaction edits using the same explicit dirty-button refresh helper.
- Added tooltips clarifying that “All transaction accounts already added” only disables adding new rows; existing account-mapping rows remain editable and saveable.
- Bumped dashboard JS cache-buster.

## v8.3 - Temporary YTD Income Category QA Patch

- Added temporary Top 20 YTD income categories ranked by filtered YTD income amount.
- Placed the income-category QA table immediately before the Top 20 YTD spending categories table.
- Bumped the dashboard JS cache-buster.

## v8.3 - Real Estate Tax Annual Adjustment Patch

- Added Annual RE Tax Adjustment under Cashflow / Mortgage in the Mortgage and RE Tax guided UI.
- Backfilled the new real_estate_tax_annual_adjustment_pct row for older Plan Data folders.
- Updated cash-flow projection logic so real-estate taxes use the dedicated RE-tax adjustment rate rather than general CPI.
- Exposed the RE-tax adjustment in YTD expected-spending plan components and UI detail text.

## v8.3 - Mortgage Real Estate Tax and YTD Category QA Patch

- Added an annual real-estate/property tax input under Cashflow / Mortgage and surfaced it in the User UI as Annual Real Estate Taxes.
- Renamed the guided step to Mortgage and RE Tax and the cash-flow/reporting bucket to Mortgage + RE Tax.
- Included real-estate taxes with mortgage/housing cash flow instead of core spending, including YTD expected-spending plan components.
- Added a temporary Top 20 YTD spending categories table sorted by filtered YTD spending amount for QA/testing.


## v8.3 - YTD Expected Spending Cleanup

- Excluded Buy, Sell, Transfer, Credit Card Payment, 401k Match, 401k Contribution, and HSA Contribution transaction flows from actual YTD spending.
- Expanded tax classification to catch plural tax categories such as Income Taxes and Real Estate Taxes.
- Changed the YTD spending comparison from annualized actual spending to expected YTD planned spending: core spending + mortgage + current-year large discretionary expenses, prorated through the latest transaction date.
- Updated the YTD spending card to label the comparison as Expected YTD and show the plan components used.

## Items 73-75 Core Spending UI Label/Order Patch

- Renamed Annual Spending Base Year to Core Spending Base.
- Renamed Stop Increasing Core Spending After Year to Core Spending Increase Stops.
- Ordered Core Spending Base, Core Spending Increase Stops, Core Spending Increase Method, then the relevant increase-rate field.
- Removed the extra Core spending growth controls heading/panel from the Spending UI.
- Kept CPI/manual conditional visibility intact.

# Golden Master Changelog

## 2026-07-08 — DAF activation baseline

Item 165: the Donor Advised Fund feature was activated (`input/client_assets.csv`
`enabled` flipped FALSE -> TRUE). DAF contributions reduce taxable income/AGI,
which lowers lifetime tax and lets more of the tax savings compound as
reinvested surplus, raising terminal net worth. Re-pinned golden-master anchors
to the new DAF-on baseline (`RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1`):

- `tests/test_2_recommendations.py` sample projection: terminal NW
  11,322,944.15 -> 12,240,766.96; lifetime tax 1,457,473.34 -> 1,553,887.13.
- `tests/fixtures/golden_master_engine_cases.json` (all fields regenerated via
  `_load_engine_config()`/`_project_metrics()` for each stress case):
  - baseline_balanced_couple terminal NW: 11,302,319.79 -> 12,271,511.44
  - no_voluntary_roth_policy terminal NW: 11,322,944.15 -> 12,240,766.96
  - high_spending_pressure terminal NW: 9,650,443.84 -> 10,507,510.24
  - lower_return_environment terminal NW: 6,834,296.87 -> 7,301,149.28
  - early_survivor_compression terminal NW: 9,660,911.67 -> 10,541,882.92
- Regenerated `input/plan_data_manifest.json` via
  `python tools/check_plan_data_sync.py --write` to resync `client_assets.csv`
  (DAF flag) and `client_spending.csv` (pre-existing drift unrelated to DAF,
  cleaned up in the same pass).

## 2026-06-10 — v8.3 expert-assessment remediation

The sample-plan golden masters were recertified after implementing the independent expert-assessment recommendations that materially change plan arithmetic:

- deterministic wellness spending now includes pre-65 bridge premiums, Medicare Part B/D base premiums, and household OOP estimates;
- taxable-account portfolio distributions now enter AGI, Social Security provisional income, IRMAA MAGI, NIIT, state tax, and cash-flow funding;
- taxable-account price appreciation is reduced by modeled distribution yield to conserve total return;
- property tax and mortgage interest now enter itemized deductions;
- Social Security claim age is honored and survivor benefits are symmetrical;
- S-corp Additional Medicare Tax and QBI/distribution treatment were corrected;
- the temporary senior deduction and Illinois estate-tax cliff/interrelated calculation were added;
- Roth strategy scoring now discounts lifetime taxes to plan-start present value.

New certified sample-plan anchors:

- no-voluntary-Roth terminal net worth: $3,153,697.55;
- no-voluntary-Roth lifetime tax: $664,993.51;
- optimizer baseline terminal net worth: $3,153,697.55;
- optimizer baseline lifetime tax: $660,749.77.

The terminal net-worth decrease versus the previous pin is expected and is mainly the result of previously collected wellness costs and taxable portfolio income now being modeled.

## 2026-06-11 — Full checklist completion pass

- Re-pinned deterministic golden anchors after replacing the home-sale LTCG prior-year stacking approximation with current-year ordering and enabling per-year tax-index paths in projection/Monte Carlo plumbing.
- Expected first-order drift: small lifetime-tax movement from current-year LTCG ordering; small RMD/tax drift in stress fixtures from per-spouse/path-indexed logic.
- Validation: full unittest suite and release gate logs in the full-checklist package artifacts.

## v8.3 Core Spending final UI cleanup
- Removed DAF Annual Contribution from Core Spending.
- Made Core Spending fields render in a flat, no-subheading list.
- Enforced order: Core Spending Base, Core Spending Increase Stops, Core Spending Increase Method, then CPI/manual growth rate.

## v8.3 - YTD Spending & Growth Tracking

- Added a gated YTD spending/income/growth module in the User UI.
- Added transaction CSV upload with strict header validation and replace/incremental import modes.
- Added editable transaction table with search, filter, sort, manual add/edit/delete, and bulk save.
- Added account mapping and 12/31 prior-year balance table for growth calculations.
- Added `ytd_transactions.csv`, `ytd_account_setup.csv`, and `ytd_import_history.csv` as clean Plan Data files.
- Added initial YTD spending, income, and growth forecast charts.

## v8.3 - YTD Refund Netting and Holdings-Derived Balances

- Treat positive transactions in Cash / spending accounts as refunds that reduce spending in the same category instead of counting as YTD income.
- Keep Buy, Sell, Transfer, Credit Card Payment, 401k Match, 401k Contribution, and HSA Contribution out of both spending and income totals.
- Removed the Current Balance field from the YTD account-mapping UI and account setup CSV schema.
- Derive current investment balance for YTD growth from mapped client_holdings.csv accounts.
- Updated YTD regression tests and bumped the dashboard JavaScript cache-buster.

## 2026-06-13 - YTD Account Source Mapping + Core Spending Order
- Moved Core Spending Increase Method to the first field in the Core Spending page so dependent fields appear after the controlling choice.
- Added an always-available Add account/source action to YTD account mapping for pensions, annuities, Social Security, offline assets, real estate, note receivables, liabilities, and other manual rows.
- Broadened YTD account Role/Type options while preserving automatic transaction-account seeding.
- Preserved broader account/source role values in ytd_account_setup.csv for future income/net-worth workflows.

## 2026-06-13 - YTD Current Values + Detailed Results On-Demand Loading
- Added editable Current Value input for non-Investment YTD account/source rows while keeping Investment current value derived from mapped client_holdings.csv holdings.
- Removed the YTD Account Mapping Notes column to reclaim table width and keep the Delete action visible.
- Replaced the manual Add account/source pop-up with inline account/source name and type controls.
- Changed Detailed Results loading to a lightweight workbook-index request followed by selected-sheet on-demand loading, avoiding one large all-workbook JSON request that could stall at 92%.
- Added separate progress and timeout handling for selected-sheet parsing.
- Synced canonical frontend and build-time static dashboard assets and bumped cache-busters.

## 2026-06-13 - Results Explorer Polling and Server Status Stability
- Prevented the Results Explorer nav open/close state from triggering extra detailed-results sheet loads.
- Added in-flight request de-duplication for the results index and selected result sheets so the same sheet is not requested repeatedly while cached or already loading.
- Removed detailed-results progress text from the left nav; progress remains in the main Results Explorer pane only.
- Made periodic server health checks silent when the server is already online and avoided marking the server stopped while a known Results Explorer request is in flight.
- Reduced sidebar re-renders from the health poll so the UI no longer flips between “Checking server” and “Server stopped” during active explorer work.

## v10 roadmap items 1–8 completion build

- Expanded canonical `PlanResult` to include projection rows, summary metrics, semantic result pages, renderer-neutral report spec, event log, validation, and tax-law dataset summary.
- Completed the local typed plan store by writing relational member/account/income/spending tables in SQLite and making SQLite snapshots the runtime source before legacy settings rows.
- Preserved CSV/JSON/YAML as import/export adapters and legacy display-string round-trip surfaces, not as the canonical runtime model.
- Replaced new-code tax-law access with a dated local `tax_law_v10` dataset containing values and ordinary bracket tables; `tax_constants.csv` remains a compatibility adapter.
- Completed the projection pipeline contract with explicit per-stage completion events and stage summary metrics while preserving the deterministic engine as the validation oracle.
- Added regression coverage for roadmap items 1–8 completion.


## 2026-06-26 - Roadmap steps 1-11 execution pass

- Added Phase 3 frontend and server ownership seams: `frontend/js/modules/phase3_module_manifest.js`, `frontend/js/dashboard_source_truth_banners.js`, and `src/server/route_manifest.py` group existing behavior by plan-state/build, detailed results, navigation, spending, holdings, strategy, settings, and route domains without moving decorators yet.
- Extended `build_snapshot_v1` with active SQLite database metadata and an immutable `plan_database_snapshot.rpx` copy beside output artifacts.
- Added snapshot compare/restore helpers and `/api/plan/snapshot/compare` plus `/api/plan/snapshot/restore` routes with hash validation and pre-restore database backup.
- Added dependency-free typed API contract registry in `src/api_contracts.py` and exposed it at `/api/contracts`.
- Added route ownership and deprecated-spending-wrapper manifests for future route splitting.
- Added roadmap journey guard tests for first-run build, transactions-to-spending-sync, holdings-to-allocation, and snapshot restore surfaces.
- Expanded explainable recommendations to state residency and withdrawal sequencing pages.
- Added first-run optional skip reason and Review-and-Build closeout UI.
- Added source-of-truth labels to data-heavy/report pages.
- Added spending-flow breadcrumbs and next-step actions.
- Added Plan Data Summary print/save-PDF preview controls.
- Added Detailed Results readability tools: important-row jump list and sheet search support.
- Added glossary-on-hover titles and keyboard shortcuts for Save, Build, Search, Review, and next/previous step navigation.
## 2026-06-26 - Roadmap continuation: batch assumption editing

- Added `dashboard_batch_assumption_edit.js` with preview-first batch edit tools for All Assumptions and guarded System Configuration rows.
- Plan assumption batch edits are staged through the existing dirty-row save model and require Save Changes before persistence.
- System Configuration batch edits require a field filter, before/after preview, explicit confirmation, and then write through `/api/admin/system-config`.
- Added preview CSV download for batch edits and documented the `batch_assumption_edit_v1` UI contract.
- Added typed API contract registry entries for `/api/admin/system-config` GET/POST.

## 2026-06-26 — Architecture and spending coherence follow-up

- Added `documentation/FLASK_REMOVAL_ARCHITECTURE.md`, proposing a dependency-free local HTTP runtime, transport-neutral request/response contracts, and a phased migration path that preserves existing `/api/...` URLs while removing Flask/Werkzeug from the packaged app.
- Added `documentation/PLANNING_WORKBENCH_CONSOLIDATION_PROPOSAL.md`, rationalizing Build Impact, Scenarios, Stress Tests, and Strategy into one Planning Workbench model with Baseline, Change Set, Run Type, and Impact concepts.
- Renamed user-facing premium language from legacy premium wording to Healthcare Premium.
- Consolidated healthcare premium taxonomy rows under one Healthcare Premium group, including Pre-65 Healthcare Premium, Medicare Part B, Medicare Part D, and Medicare Part G/Medigap premiums.
- Reclassified Annual Household Medical OOP Cap as a cap/reference rather than a standalone expense budget.
- Collapsed legacy travel-detail taxonomy rows into the Travel group and added normalization for legacy rows that still say Travel Detail.
- Updated Monthly Trajectory to include all non-tax spending actuals, including Housing, Wellness/healthcare, Travel, Large Discretionary, Business, and Core Expense outflows, while still excluding income, transfers, and taxes.
## 2026-06-26 — Flask-free service extraction pass

- Added `src/server_services/` as the feature-owned service layer for request-independent handler logic.
- Moved base/runtime payload logic into `base_service.py` while keeping `base_routes.py` as a thin HTTP adapter.
- Moved admin CSV/system-config/reference/diagnostics/server-status logic into `admin_service.py` while preserving existing admin URLs.
- Moved build summary, output metadata, and build-preflight readiness logic into `build_service.py`.
- Moved SQLite Plan Data form get/save/patch logic into `plan_forms_service.py`.
- Kept permission checks, request parsing, response serialization, file streaming, shutdown, audit hooks, and background build thread startup in route adapters.
- Documented remaining extraction targets: pricing, spending/YTD, holdings/assets/strategy, and build job orchestration.



## Immediate Next Actions Implementation

Implemented the first post-evaluation stabilization pass: restored documented contract/ownership files, exposed `/api/contracts`, added the healthcare terminology alias seam, started frontend extraction with `api_client.js` and `app_store.js`, started backend extraction with `pricing_service.py` and `holdings_service.py`, and added a clean-overlay validation tool.

## 2026-06-26 — Frontend modularization continuation

- Extracted navigation behavior into `frontend/js/navigation.js` with `RetirementNavigation` owning step changes, autosave-on-navigation guards, search-scope behavior, focus traversal, and global compatibility exports.
- Extracted Detailed Results shell rendering into `frontend/js/reports_ui.js` with `RetirementReportsUI` owning the workbook navigation tree and Results Explorer wrapper states while existing sheet/table/chart helpers remain in `dashboard.js` for the next pass.
- Extracted Planning Workbench browser-local case storage and workbench rendering into `frontend/js/planning_workbench_ui.js` with `RetirementPlanningWorkbench` owning `planning_case_v1`, comparison matrix rendering, adoption routing, and Build Impact context panels.
- Updated dashboard script loading order in both `frontend/index.html` and `output/index.html`; `dashboard.js` now keeps thin compatibility wrappers and context providers for the extracted modules.

## 2026-06-26 — Backend modularization continuation

- Added `src/server_services/ytd_service.py` and moved YTD transaction upload/add/update/delete/bulk-save, account setup save/recovery, SQLite mirroring, and legacy account setup recovery scoring out of `plan_routes.py`.
- Added `src/server_services/plan_file_service.py` and moved local plan save-as, load-file, and exit snapshot SQLite copy/checkpoint/retention logic out of `plan_routes.py`.
- Completed `/api/plan/load-file` behavior with source existence validation, pre-load database backup, stale WAL/SHM sidecar cleanup, database copy, and post-load `wal_checkpoint(TRUNCATE)`.
- Kept route modules as compatibility HTTP adapters that enforce permissions, parse request JSON, call feature services, and serialize responses.

## 2026-06-26 - Backend service extraction: async build jobs

- Added `src/server_services/build_job_service.py` as the feature-owned home for async build-job orchestration.
- Moved build progress registry, progress-line interpretation, desktop progress push fanout, stale-summary/build-id checks, and actionable build-error formatting out of `workbook_routes.py`.
- Kept `workbook_routes.py` as a thin adapter for authorization, request parsing, environment assembly, thread launch, and JSON/SSE progress responses.
- Updated release-package static checks and regression tests to validate the extracted build-job service instead of route-local progress globals.


## 2026-06-26 - Backend service extraction: report outputs

- Added `src/server_services/report_service.py` as the feature-owned service for report artifact lookup, Detailed Results model selection, local build-history persistence, and safe `/files/<path:filename>` validation.
- Refactored `/api/detailed-results`, `/api/history`, `/api/xlsx`, `/api/pdf`, and `/files/<path:filename>` so `workbook_routes.py` keeps only authorization, query parsing, response serialization, and audit hooks.
- Extended the route manifest and typed API contract registry with report/build-history ownership details.
- Updated clean-overlay validation to compile the new report service during pristine-baseline overlay checks.

## 2026-06-26 - Backend service extraction: spending model

- Added `src/server_services/spending_service.py` as the feature-owned service for spending dashboard, category-map compatibility routes, taxonomy CRUD, mapping rules, budget seeding/load-actuals, aliases, unified budget rows, and spending summary/model payloads.
- Refactored spending routes in `src/server/plan_routes.py` into thin adapters that enforce permissions, extract JSON/query arguments, delegate to `SpendingService`, and serialize payload/status results.
- Extended the route ownership manifest and typed API contract registry with additional spending taxonomy, summary, and budget contracts.
- Added regression tests that keep spending service logic framework-neutral and prevent `spending_tracker` mutations from returning to the route module.
