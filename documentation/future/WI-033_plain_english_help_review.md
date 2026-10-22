# WI-033 — Plain-English help layer: page list and draft for non-expert read-through

Source: DOC-008 in `documentation/archive/reports/SYSTEM_REVIEW_2026-10-19.md`.
Help text now lives in `HELP_PAGES` in `frontend/js/help_registry.js` (it used to be `desc`, `intro`, `help` in `STEPS`).
Status: implemented (applied in `frontend/js/help_registry.js` by Contextual Help Panel Phases 2 and 5; the registry is now the source for the summaries and text below).

## How to run the read-through

1. The reviewer reads only each page's `desc`, `intro` and `help`, with no coaching.
2. They mark every term they cannot explain in their own words (column "Terms to confirm").
3. Every term in "Terms to confirm" is defined in `WI-033_glossary_draft.md` (written for a high-school reader with little financial experience). The reviewer checks those definitions too. Confirmed terms become glossary entries. The "Draft summary" becomes the one-line plain summary.
4. A page with no flagged terms is left as is.

Acceptance (from the review): pages used before the first build have plain-language summaries.

## Part A — Used before the first build (11 pages)

| # | Page (`step id`) | Draft plain summary | Terms to confirm |
|---|---|---|---|
| 1 | Plan Status (`start`) | Open or create your plan, see what is still missing, and pick what to do next. | readiness |
| 2 | Household & People (`household_people`) | Who is in the household, when each person was born and plans to retire, and where you live and file taxes. | filing status, planning horizon, mortality age, survivor assumptions, tax brackets |
| 3 | Work Income (`income_work`) | Pay you still earn and what you save from it until you retire. | payroll assumptions, retirement plan contributions, business-income deductions, Roth conversion room, bracket ceiling |
| 4 | SS, Pensions, & Annuities (`income_retirement`) | Social Security, pension and annuity income: how much, when it starts, and what continues to a surviving spouse. | claiming age, full retirement age, spousal/survivor policy, cost-of-living settings, fixed-income-equivalent coverage |
| 5 | Spending Model (`spending_core`) | Everything you spend and earn, sorted into categories. | Tracking Type, Group, Category, internal transfers, Auto-Mapping Rules |
| 6 | Investment Holdings (`holdings`) | Each investment you own, one row per purchase. | tax lot, cost basis, ticker, tax-aware sell guidance |
| 7 | Reserve Requirements (`assets_home_cash`) | How much cash to keep on the side before the plan sells investments. | reserve floor, probability analysis |
| 8 | Other Assets and Liabilities (`assets_special`) | Things you own or owe that are not in your investment accounts, such as HSA, 529 and a note owed to you. | notes receivable, HSA, 529, equity compensation, illiquid, donor-advised fund |
| 9 | Insurance (`annuity_death_benefits`) | Your insurance policies and the yearly benefit values from each insurer's illustration. | carrier illustration, rider, beneficiary, face amount |
| 10 | Estate Inputs (`estate`) | What you plan to leave, to whom, and how, including gifts and charity. | federal/state exemption, trust structure, lifetime gifting |
| 11 | Build & Results (`reports_and_review`) | Check the plan is ready, build the reports, then review and download them. | readiness checks, impact |

## Part B — Used after the first build or optional (17 pages)

| # | Page (`step id`) | Draft plain summary | Terms to confirm |
|---|---|---|---|
| 12 | Home Equity Line (`heloc_strategy`) | Borrow against your home for big purchases instead of selling investments early. | credit limit, draw year, rate drift, discretionary spending, home sale proceeds |
| 13 | Rental Properties (`rental_properties`) | Income, costs and eventual sale of each rental property. | depreciation, passive-activity rules, Schedule E |
| 14 | Roth Conversion (`roth_conversion`) | Decide how much pre-tax money to move into a Roth account each year, and how to weigh the trade-offs. | Roth conversion, conversion policy, bracket ceiling, Medicare income surcharge, premium tiers, objective weights, marginal rate |
| 15 | Charitable Giving (`entity_charitable`) | How you give to charity: direct gifts, a donor-advised fund, or gifts straight from an IRA. | donor-advised fund, qualified charitable distribution, adjusted gross income, required distributions |
| 16 | Education & Equity Comp (`family_business`) | College savings plans and stock awards from an employer. | 529, vesting, exercise, optional module |
| 17 | Optimize (`strategy_optimize`) | One place to adjust the main levers: Roth conversions, investment mix, giving and home-equity borrowing. | asset allocation and location, lever |
| 18 | Stress Test (`strategy_stress`) | See how the plan holds up if things go badly: poor markets, early death, long-term care, divorce. | Monte Carlo, survivor stress, long-term care |
| 19 | Scenarios (`strategy_scenarios`) | Save "what if" versions of your plan, such as retiring two years later. | change set, deterministic, lever |
| 20 | Workbench (`strategy_workbench`) | Compare your plan with the saved what-ifs and decide which to adopt. | baseline, change set, run type, planning cases |
| 21 | Actual Spending (`actual_spending`) | Compare what you really spent this year with what the plan assumed. | annualized, sync actual rate, Accounts & Sources |
| 22 | Account Reconciliation (`monarch_reconciliation`) | Check the plan's account balances against your imported daily balances and fix differences. | reconciliation, report only, plan-start figures |
| 23 | Results (`detailed_results`) | View every report sheet and chart inside the app after a build. | column groups, conditional formatting |
| 24 | Economic & Tax Assumptions (`economic_tax_assumptions`) | Growth, inflation and tax-rule assumptions used for every year of the plan. | medical inflation, tax bracket indexing, COLA |
| 25 | Plan Features (`optional_functions`) | Turn optional parts of the plan on or off. Turning one off never deletes your entries. | optional module, nav steps |
| 26 | Field Finder (`all_assumptions`) | Search for any plan value that you cannot find on a guided page. | structured plan rows |
| 27 | Workbook Formatting (`workbook_formatting`) | Set Excel column widths for the downloaded workbook. | overrides |
| 28 | Data & Maintenance (`system_configuration`) | Backups, exports, price snapshots and the change log. Not plan inputs. | pricing snapshot, System Configuration Console |

## Next steps after the read-through

- Collect flagged terms into one glossary list (shared across pages).
- Add a plain `summary` field per `STEPS` entry plus glossary links in the help panel (frontend change, covered by a test that every page has a summary).
- Done: `desc`, `intro` and `help` were merged into one record per page (summary, what it is for, connections, options, impact); the summary is the left-nav one-liner.
