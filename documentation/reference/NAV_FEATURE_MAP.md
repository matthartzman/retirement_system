# Left Navigation Feature Map

Inventory of the dashboard's left navigation: what each item does, whether it can be switched on or off, its state in the demo plan, and where it appears when enabled.

> **Structure update (2026-11-04):** the nav was regrouped from twelve headings to eight (Plan Status pinned, Household & Cash Flow, Accounts & Property, Protection & Legacy, Taxes, Analyze, Track & Reconcile, Settings), with a Set up / Maintain switch and a per-heading Features popover (`frontend/js/dashboard_decomp_nav_features.js`). The "Nav group" and item names in the tables below follow the new structure; the page rows are not re-verified one by one. Source of truth: `STEPS` in `frontend/js/dashboard.js` and the design in `documentation/archive/superpowers/specs/2026-11-04-left-nav-redesign-design.md`.

## How the left nav works

- The nav is built from the `STEPS` array in `frontend/js/dashboard.js` (lines 14-296). `renderSteps()` (`frontend/js/dashboard_decomp_row_model.js:2386`) groups consecutive visible steps by `group` and numbers the pages 1..N (the group headings are not numbered in the UI).
- `visibleSteps()` (`dashboard_decomp_row_model.js:61-71`) drops a step when it is gated off, when `group` is `null`, or when `hidden: true`. The currently active step is always kept, so a hidden step reached by a link would appear while open.
- Hidden or `group: null` steps are redirect-only. `frontend/js/navigation.js:55-123` maps their old ids onto a visible page (`WORKSPACE_TAB_REDIRECTS`, `STEP_REDIRECTS`, `SECTION_REDIRECTS`, plus `REPORTS_REDIRECT_IDS` at line 33).
- Two kinds of switch gate a nav item:
  1. **Module toggle** - a plan row in section `Optional Functions` (the old `client_optional_functions.csv`; the runtime reads the plan file, not the CSV), switched on Settings > Plan Features. A module declared with `csv_row=False` has no row and uses its default (Account Reconciliation is one). The step-to-module map is `step_gate_map()` in `src/module_catalog.py`, served as `module_gates.step_gates` (`src/server_services/config_service.py:113-142`).
  2. **Plan flag** - a plan row (the old `client_assets.csv` / `client_policy.csv`) (`GATE_PLAN_FLAG` entries, `module_catalog.py:1035-1100`), also switched on Plan Features. Served as `module_gates.flag_gates`; today only HELOC has a nav step.
- Some switches gate only a section or tab inside a page, not the nav item. The page stays in the nav and the section shows an enable-note.
- `module_taxonomy` (`config_service.py:144-`) feeds Plan Features: per module `name`, `kind`, `domain`, `demand`, `optional`, `gated_by`, `engine_participation`, and soft dependents.
- **Current state** was read from the demo plan in its legacy CSV form: `input/demo/client_optional_functions.csv` for module toggles and `input/demo/client_assets.csv` / `client_policy.csv` for plan flags (the file:line references below point there). A flag with no demo row uses its loader default (`src/data_io.py:958`: `qcd_enabled` defaults FALSE). "Off" means the item is hidden or gated; "n/a" means always on.

### Charitable Giving (implemented)

- The Charitable Giving nav step (`entity_charitable`) is shown iff DAF is on **or** QCD is on.
- DAF (`daf_giving`: plan flag `DAF / Settings / enabled`) and QCD (`qcd_giving`: plan flag `Cashflow / Charitable Giving / qcd_enabled`) are independent features, each switched on Plan Features.
- There is no separate Charitable Giving toggle: the `charitable_giving` module is declared `gated_by_any_flag=("daf_giving", "qcd_giving")` in `src/module_catalog.py`, so the workbook sheet (2G Charitable Giving) is built iff either flag is on, and its `client_optional_functions.csv` row was removed.
- The nav rule is in `dashboard_decomp_row_model.js:43-50`.

## Detailed table

Legend: Optional? = Always on / Switchable. Position = group and ordinal in the nav when everything is enabled (see the last section). "Plan Features" = Settings > Plan Features.

| Nav group | Item | What it does | Optional? | Switch (key and where set) | Current state (demo) | Position when enabled |
|---|---|---|---|---|---|---|
| Plan Status | Plan Status (`start`) | Open a plan, check readiness, choose the next action | Always on | - | n/a | see STEPS order |
| Household & Cash Flow | Household & People (`household_people`) | Names, birth dates, state, filing status, retirement dates, horizon, survivor assumptions | Always on | - | n/a | see STEPS order |
| Household & Cash Flow | Work Income (`income_work`) | Salary or self-employment income, payroll assumptions, retirement contributions | Always on | - | n/a | see STEPS order |
| Household & Cash Flow | Social Security & Pensions (`income_retirement`) | Social Security claiming, pensions, annuity income, COLA settings | Always on | - | n/a | see STEPS order |
| Household & Cash Flow | Spending Model (`spending_core`) | Category hierarchy, budgets, projection controls; one accordion per Tracking Type (Housing, Wellness, Travel and Other Spending live here) | Always on | - | n/a | see STEPS order |
| Accounts & Property | Investment Holdings (`holdings`) | One row per tax lot: account, ticker, shares, date, basis | Always on | - | n/a | see STEPS order |
| Accounts & Property | Rental Properties (`rental_properties`) | Rental real estate: rent, expenses, mortgage, depreciation, passive-loss limits and sale per property; Convert my home; summary estimate and warnings | Switchable | `rental_property_income`, Plan Features (Advanced tier, default off) | Off (default): hidden while nothing is entered; with properties stored the page stays and shows its off state ("Off · N rows entered", data kept, preview) | see STEPS order |
| Accounts & Property | Home Equity Line (`heloc_strategy`) | Bridge large discretionary spending with home equity | Switchable | Plan flag `HELOC / Setup / heloc_enabled` (key `heloc`), Plan Features | Off (NO, `client_policy.csv:11`): nav item hidden | see STEPS order |
| Accounts & Property | Other Assets & Debts (`assets_special`) | Notes receivable, HSA, 529 plans, equity comp, collectibles, personal property | Always on | - | n/a | see STEPS order |
| Accounts & Property | Other Assets > 529 Plans section | 529 rows on this page (same rows as Education & Equity Comp) | Switchable | `education_funding_529`, Plan Features | Off (FALSE) | Section of 5.3 and 9.1 |
| Accounts & Property | Other Assets > Equity Compensation section | Equity comp rows on this page | Switchable | `equity_compensation`, Plan Features | Off (FALSE) | Section of 5.3 and 9.1 |
| Accounts & Property | Other Assets > Hybrid LTC row group | Hybrid LTC/life policy rows | Switchable | Plan flag `Hybrid LTC / Settings / enabled` (key `hybrid_ltc_policy`), Plan Features | Off (FALSE, `client_assets.csv:84`) | Row group of 5.3 |
| Accounts & Property | Cash Reserves (`assets_home_cash`) | Cash reserve floor protected before drawing investments | Always on | - | n/a | see STEPS order |
| Accounts & Property | 529 & Equity Compensation (`family_business`) | 529 and equity comp inputs (second entry to rows that live on Other Assets) | Always on (page) | - (page not gated; sections below are) | n/a | see STEPS order |
| Accounts & Property | 529 Plans section | One 529 section per beneficiary or goal | Switchable | `education_funding_529`, Plan Features | Off: section shows enable-note | Section of 9.1 |
| Accounts & Property | Equity Compensation section | Grants, vesting, exercise assumptions | Switchable | `equity_compensation`, Plan Features | Off: section shows enable-note | Section of 9.1 |
| Protection & Legacy | Insurance (`annuity_death_benefits`) | Carrier illustrations for annuities and special income, plus all insurance policies | Always on | - | n/a | see STEPS order |
| Protection & Legacy | Insurance > Existing Life Insurance rows (section `Insurance In Force`) | Policies in force | Switchable | `existing_life_insurance`, Plan Features (`section_gates`) | Off (FALSE) | Rows of 6.1 |
| Protection & Legacy | Estate Inputs (`estate`) | Exemptions, trust structure, beneficiary needs, gifting, charitable intent | Always on | - | n/a | see STEPS order |
| Taxes | Roth Conversion (`roth_conversion`) | Conversion policy, ceiling, IRMAA guardrails, objective weights | Switchable | `roth_conversion_plan`, Plan Features | On (TRUE) | see STEPS order |
| Taxes | Charitable Giving (`entity_charitable`) | Giving vehicle: direct gift, DAF, QCD | Switchable | Shown iff `daf_giving` (DAF/Settings/enabled) OR `qcd_giving` (Cashflow/Charitable Giving/qcd_enabled); both switched on Plan Features | On: DAF TRUE (`client_assets.csv:78`), QCD off by default (no demo row) | see STEPS order |
| Taxes | Charitable Giving > DAF rows | Contribution, grant years and amounts | Switchable | `daf_giving`, Plan Features | On | Rows of 8.2 |
| Taxes | Charitable Giving > QCD rows | Qualified charitable distributions | Switchable | `qcd_giving`, Plan Features | Off (default) | Rows of 8.2 |
| Analyze | Optimize (`strategy_optimize`) | Stack of collapsible lever sections | Always on | - | n/a | see STEPS order |
| Analyze | Optimize > HSA Drawdown | HSA withdrawal-policy block | Always on (section) | Module `hsa_drawdown` toggles the workbook tab only, not this section | n/a | Section 10.1.1 |
| Analyze | Optimize > Asset Allocation | Targets or optimizer recommendation, include/exclude, risk settings | Always on | - | n/a | Section 10.1.2 |
| Analyze | Optimize > Withdrawal Sequencing | Bucket draw order, trust withdrawals, spousal rollover | Always on (section) | Module `retirement_strategy` toggles the workbook sheet only | n/a | Section 10.1.3 |
| Analyze | Optimize > Social Security | SS optimization panel | Always on (section) | Module `social_security_timing` toggles the workbook sheet only | n/a | Section 10.1.4 |
| Analyze | Optimize > Next Housing Move | ZIP screening and ranking of places to move | Switchable | `housing_location_search`, Plan Features | On (TRUE) | Section 10.1.5 |
| Analyze | Optimize > Harvesting | Tax-loss and gain harvesting settings | Always on (section) | Modules `tax_loss_harvesting`, `gain_harvesting` toggle workbook sheets only | n/a | Section 10.1.6 |
| Analyze | Stress Test (`strategy_stress`) | Adverse-assumption tests | Switchable | Hidden when all four section modules are off | On: all four on | see STEPS order |
| Analyze | Stress Test > Monte Carlo | Probability, engine, trials, volatility, liquidity floor | Switchable | `market_luck_stress_test`, Plan Features | On (TRUE) | Section 10.2.1 |
| Analyze | Stress Test > Survivor | Mortality ages, survivor filing, income reduction | Switchable | `survivor_stress_test`, Plan Features | On (TRUE) | Section 10.2.2 |
| Analyze | Stress Test > Long-Term Care | Care cost, duration, coverage | Switchable | `long_term_care_stress`, Plan Features | On (TRUE) | Section 10.2.3 |
| Analyze | Stress Test > Divorce Planning | Account transfer, alimony, asset division overlay | Switchable | `divorce_qdro`, Plan Features | Off (FALSE); section omitted entirely | Section 10.2.4 |
| Analyze | Scenarios (`strategy_scenarios`) | Named scenario change sets | Always on (page) | - (page not hidden by any gate) | n/a | see STEPS order |
| Analyze | Scenarios > Scenario Change Sets | Change-set builder | Switchable | `what_if_analysis`, Plan Features | On (TRUE) | Section 10.3.1 |
| Analyze | Planning Workbench (`strategy_workbench`) | Compare baseline, change sets and stress results; decide what to adopt (sections: Strategy Levers, Change Set Builder, Unified Comparison Matrix, Decision, Saved Planning Cases) | Always on | - | n/a | see STEPS order |
| Analyze | Build & Results (`reports_and_review`) | Readiness, build, impact, results, downloads, plan data review | Always on | - | n/a | see STEPS order |
| Track & Reconcile | Actual Spending (`actual_spending`) | This year's imported transactions and comparison vs the spending model; tabs "This year" and "Analysis" | Always on (page) | - | n/a | see STEPS order |
| Track & Reconcile | Actual Spending tabs (This year, Analysis) | Transaction import/review and actual-vs-budget analysis | Switchable | `spending_tracker_ytd` (also switches Spending Summary and Account Reconciliation sheets), Plan Features | On (TRUE) | Tabs of 11.1 |
| Track & Reconcile | Account Reconciliation (`monarch_reconciliation`) | The app's account numbers beside the imported daily balances; update the app, ignore, always update or keep the app as source (`dashboard.js:225-232`) | Switchable | `account_import`, Plan Features (default on, no plan row) | On (default) | see STEPS order |
| Settings | Plan Features (`optional_functions`) | Switch page for every optional module and plan flag, grouped by life area | Always on | - (it is the switch surface) | n/a | see STEPS order |
| Settings | Economic & Tax Assumptions (`economic_tax_assumptions`) | Return rates, inflation, tax bracket indexing, COLA | Always on | - | n/a | see STEPS order |
| Settings | Find a Field (`all_assumptions`) | Find any value not on a guided page | Always on | - | n/a | see STEPS order |
| Settings | Workbook Formatting (`workbook_formatting`) | Excel column widths per sheet, table, column | Always on | - | n/a | see STEPS order |
| Settings | Data & Backups (`system_configuration`) | Pricing snapshots, backups, CSV export, change log, system console | Always on | - | n/a | see STEPS order |

### Hidden or redirect-only steps (never in the nav)

| Step id | Behavior | Source |
|---|---|---|
| `retirement_wellness`, `spending_mortgage_events` | Redirect to Spending Model (Wellness / Housing accordion) | `navigation.js:81-123`; `dashboard.js:71,117` |
| `spending_travel`, `spending_travel_extras`, `lifestyle_spending` | Redirect to Spending Model | `navigation.js:60-66` |
| `state_residency`, `timing_tax` | Redirect to Spending Model > Housing residency table | `navigation.js:114-115` |
| `ytd_transactions`, `spending_dashboard` | Redirect to Actual Spending tab "This year" / "Analysis" | `navigation.js:55-59` |
| `review`, `build_impact`, `plan_data_report` | Redirect to Build & Results | `navigation.js:33` |
| `detailed_results` | Hidden but reachable directly (linked from Build & Results); shows a sheet-picker sub-nav while active; not redirected | `navigation.js:30-33`; `row_model.js:2467-2472` |
| `planning_workbench`, `planning_levers` | Redirect to Workbench > Strategy Levers | `navigation.js:103-107` |
| `scenarios` | Redirect to Scenarios > Change Sets | `navigation.js:106` |
| `distribution_strategy`, `investment_strategy`, `allocation_assets`, `allocation_policy`, `withdrawal_strategy` | Redirect to Optimize (section opened) | `navigation.js:82-93` |
| `monte_carlo_options`, `survivor_stress`, `ltc_stress`, `divorce_options` | Redirect to Stress Test section | `navigation.js:100-103` |
| `special_strategies` | Redirect to Home Equity Line | `navigation.js:99` |
| `ss_timing` | Redirect to SS, Pensions, & Annuities | `navigation.js:66` |

## Left nav with everything enabled

Generated from `STEPS` (2026-11-04 structure). Plan Status is a pinned link; Maintain mode lifts only Track & Reconcile to the top.

1. **Plan Status**
   - Plan Status (`start`)
2. **Household & Cash Flow**
   - Household & People (`household_people`)
   - Work Income (`income_work`)
   - Social Security & Pensions (`income_retirement`)
   - Spending Model (`spending_core`)
3. **Accounts & Property**
   - Checking & Savings (`cash_accounts`)
   - Investment Holdings (`holdings`)
   - Rental Properties (`rental_properties`)
   - Home Equity Line (`heloc_strategy`)
   - Other Assets & Debts (`assets_special`)
   - Cash Reserves (`assets_home_cash`)
   - 529 & Equity Compensation (`family_business`)
4. **Protection & Legacy**
   - Insurance (`annuity_death_benefits`)
   - Estate Inputs (`estate`)
5. **Taxes**
   - Account Tax Basis (`account_tax_basis`)
   - Roth Conversion (`roth_conversion`)
   - Charitable Giving (`entity_charitable`)
6. **Analyze**
   - Optimize (`strategy_optimize`)
   - Stress Test (`strategy_stress`)
   - Scenarios (`strategy_scenarios`)
   - Planning Workbench (`strategy_workbench`)
   - Build & Results (`reports_and_review`)
7. **Track & Reconcile**
   - Actual Spending (`actual_spending`)
   - Account Reconciliation (`monarch_reconciliation`)
   - Investment Sales Ledger (`sales_ledger`)
   - Year-End Transition (`year_end`)
8. **Settings**
   - Plan Features (`optional_functions`)
   - Economic & Tax Assumptions (`economic_tax_assumptions`)
   - Find a Field (`all_assumptions`)
   - Workbook Formatting (`workbook_formatting`)
   - Data & Backups (`system_configuration`)

## Notes / discrepancies

1. **Charitable Giving catalog wiring.** `charitable_giving` still declares `dashboard_step="entity_charitable"`, so `step_gate_map()` still returns `entity_charitable -> charitable_giving`. The frontend rule at `dashboard_decomp_row_model.js:43-50` short-circuits it before the generic gate, so the entry is inert for the nav (a test pins it).
2. **Optional pages that stay in the nav when their module is off.** Scenarios (`what_if_analysis`) and Actual Spending (`spending_tracker_ytd`) have no step-level gate (no `strategy_scenarios` / `actual_spending` entry in `step_gate_map()`). Only the section or tab inside shows an enable-note. Stress Test is the one section-hub page that hides itself (`row_model.js:28-39`). Family & Business is never hidden even with both modules off (`dashboard_decomp_assets_other.js:330-378`).
3. **Optimize sections with a workbook toggle but no UI gate.** HSA Drawdown (`hsa_drawdown`), Withdrawal Sequencing (`retirement_strategy`), Social Security (`social_security_timing`) and Harvesting (`tax_loss_harvesting`, `gain_harvesting`) are `gate: null` (`dashboard_decomp_strategy_workspace.js:306-390`). Turning the module off removes the workbook sheet but not the input section.
4. **Plan-flag switches.** HELOC, Hybrid LTC, DAF and QCD are plan data rows, not `client_optional_functions.csv` toggles (`module_catalog.py:1035-1100`). They travel with the household's data. Only HELOC has a hidden nav step; Hybrid LTC gates a row group on Other Assets; DAF/QCD gate rows and the Charitable Giving step.
5. **Section-gated rows.** `section_gate_map()` currently gates the input sections `Education Funding`, `Equity Compensation` and `Insurance In Force` by their modules. Those rows disappear from their host pages when the module is off, but the nav item itself stays.
6. **Hidden entries still in `STEPS`.** About 24 steps are `hidden: true` or `group: null` (table above). `detailed_results` is the only hidden step not redirected; it is a real page reached from Build & Results. `ss_timing` appears in `STEP_REDIRECTS` but has no `STEPS` entry.
7. **QCD demo value.** The demo plan has no QCD row, so QCD is off by loader default (`data_io.py:958`). Charitable Giving is visible in the demo only because DAF is TRUE.
8. **Stale comments.** `dashboard.js` comments around the Housing/HELOC steps and the `entity_charitable` desc ("Annual giving amounts are set on Core spending") predate the Taxes grouping. Not behavioral.
