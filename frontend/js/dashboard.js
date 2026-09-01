// v11 other asset display ordering: {'Note Receivable':0,'HSA':1,'DAF':2,'529 Plans':3}
// Dashboard extraction markers for no-build dashboard tests:
// Extracted reports_ui.js retains branch marker: if(sheet.kind==='chart_dashboard'&&Array.isArray(sheet.charts)).
// Extracted navigation/reports marker: data-detail-sheet.
// Extraction markers retained after modularization: planning_case_v1 browser-local store; window.setDetailedResultsNavOpen=setDetailedResultsNavOpen; Search this page...
// Frontend module ownership markers: planning_workbench_ui.js owns retirement.planning_case_v1; reports_ui.js renders setDetailedResultsNavOpen(this.open); Planning cases never mutate the saved plan automatically.
// reports_ui.js owns (Phase 3 extraction): DETAIL_MONEY_TERMS; detailCurrencyK; detailHeaderRowIndex; renderChartDashboardSheet; Column groups; function detailLabelForColumn; function detailGroupLabel; Years ${first}–${last}; detailIdentifierRowIndex; detail-super-head; has-super-head; detailCleanSectionTitle
// Earned Income End Year; lbl!=='earned_income_last_year'
// YTD Accounts & Sources save to the local database; CSV remains an import/export adapter
let csrfToken = "";
window.__retirementCsrfToken = csrfToken;
/* Retirement Planner dashboard behavior.
   First-class static asset loaded by the dashboard shell. */
const STEPS = [
  {
    id: "start",
    group: "Plan Status",
    title: "Plan Status",
    desc: "Open a plan, check readiness, and choose the next best action.",
    intro:
      "Use this as the home base for setup progress, report readiness, and the next action that moves the plan forward.",
    help: "Start with opening or creating a plan. Once a plan is loaded, save changes, build reports, and review results from here.",
  },
  {
    id: "household_people",
    group: "People and Income",
    title: "Household & People",
    desc: "Names, birth dates, state of residence, tax filing status, retirement dates, planning horizon, and survivor income and filing assumptions.",
    intro:
      "Birth dates determine ages for Social Security timing, required minimum distributions, Medicare eligibility, survivor horizon, and retirement period length. The retirement date ends earned income and starts the withdrawal period. Choose a conservative planning horizon — the projection runs through this age for both members.",
    help: "Filing status affects tax brackets across the entire projection — changing it after plan entry can materially shift lifetime taxes and survivor results. Survivor assumptions drive the Survivor stress report and also appear there for review before a rebuild.",
  },
  {
    id: "income_work",
    group: "People and Income",
    title: "Work Income",
    desc: "Salary or self-employment income, payroll assumptions, and retirement plan contributions while still working.",
    intro:
      "Contribution amounts here add to account balances annually until the retirement date. Business salary level affects payroll tax and business-income deductions.",
    help: "High earned income in late working years compresses Roth conversion room below the bracket ceiling — coordinate with the Roth Conversion tab when the retirement date is near.",
    helpLink: { id: "distribution_strategy", label: "Open Distribution Strategy (Roth conversion is on that page)" },
  },
  {
    id: "income_retirement",
    group: "People and Income",
    title: "SS, Pensions, & Annuities",
    desc: "Social Security claiming age and benefit for each person, plus pension amounts, annuity income, start ages, survivor percentages, and cost-of-living settings.",
    intro:
      "Enter each person’s Social Security benefit from their statement along with the planned claiming age and the household spousal/survivor policy. Delaying past full retirement age adds about 8% per year up to age 70; the higher earner’s delay has the greatest survivor income impact. Survivor percentages control how much pension or annuity income continues after the first death.",
    help: "Early claiming opens gap years for Roth conversion if other income is low — model the joint timing strategy with the Roth Conversion tab. Pensions and annuities with survivor protection can be treated as fixed-income-equivalent coverage in the allocation analysis — set the coverage option on the Asset allocation & location tab.",
    helpLink: { id: "distribution_strategy", label: "Open Distribution Strategy (Roth conversion and allocation are on that page)" },
  },
  {
    id: "spending_core",
    group: "Spending",
    title: "Spending Model",
    desc: "Comprehensive income/expense category hierarchy, budget references, and projection spending controls. Also the entry point for Actual Spending (YTD), Spending Analysis, and Other Spending -- see the tabs above the content.",
    intro:
      "Review the full Tracking Type → Group → Category model here. It should account for all income and all expenses except taxes/transfers; lifestyle detail pages still hold scheduled spending inputs.",
    help: "Spending Model is the category manager. Transaction assignment appears here as Advanced Auto-Mapping Rules only when needed.",
  },
  {
    id: "retirement_wellness",
    group: "Spending",
    title: "Wellness",
    desc: "Authoritative Wellness budget detail: healthcare premiums, medical, dental, vision, Rx/OTC, and medical OOP cap reference.",
    intro:
      "Enter healthcare premium assumptions and non-premium medical spending detail here. Other pages may reference these numbers, but this is the only editable source for Wellness.",
    help: "Include both Medicare and pre-Medicare premiums plus expected out-of-pocket medical, dental, vision, and drugs. Medical OOP Cap is a cap/reference for non-premium medical spending, not a standalone expense.",
  },
  {
    id: "spending_mortgage_events",
    group: "Spending",
    title: "Housing",
    desc: "Authoritative Housing budget detail: mortgage, homeowners insurance, maintenance, utilities, real-estate taxes, and home improvements.",
    intro:
      "Enter all housing budget detail here. Other pages may reference these numbers, but this is the only editable source for Housing.",
    help: "Housing includes current mortgage, homeowners insurance, maintenance, utilities, real-estate taxes, and home improvement projects. Rent is shown only when configured with a positive value.",
  },
  {
    id: "lifestyle_spending",
    group: "Spending",
    title: "Other Spending",
    desc: "Travel, large planned expenses, and donor-advised fund giving in one place.",
    intro:
      "Use this page for expenses that are scheduled, flexible, or easier to review together: travel, large one-time items, and DAF contribution/grant settings.",
    help: "The sections below keep their existing source inputs, but the combined page makes the spending flow simpler.",
    hidden: true,  },
  {
    id: "spending_travel",
    group: "Spending",
    title: "Travel",
    desc: "Authoritative Travel budget detail and time-bounded travel plans.",
    intro:
      "Enter Travel budget categories and scheduled trip spending here. Spending Categories and reports show Travel as reference where needed.",
    help: "Travel is its own Tracking Type and no longer lives on the Spending Categories budget editor.",
    hidden: true,
  },
  {
    id: "spending_travel_extras",
    group: "Spending",
    title: "Large Discretionary",
    desc: "Large occasional non-housing, non-Wellness, non-travel expenses such as weddings, vehicles, gifts, or family support.",
    intro:
      "Each row is an annual amount active from start year through end year. Set start year equal to end year for a single-year expense.",
    help: "Home Improvements are entered on Housing. Travel is entered on Travel. Keep this page for other flexible large expenses.",
    hidden: true,
  },
  {
    id: "ytd_transactions",
    group: "Spending",
    title: "Actual Spending (This Year)",
    desc: "Import, assign, review, and sync current-year income and expense transactions.",
    intro:
      "Import transactions, review assignments, and compare the current year with the spending model before updating the plan.",
    help: "Category assignment happens on Spending Model. Accounts & Sources controls account/source type, prior-year balances, and current values.",
    hidden: true,  },
  {
    id: "holdings",
    group: "Assets & Protection",
    title: "Investment Holdings",
    desc: "One row per tax lot: account, ticker, shares, purchase date, and cost basis.",
    intro:
      "Add holdings from your broker here. Account names must match those used on Withdrawal Sequencing and Asset Allocation.",
    help: "Lot-level cost basis enables tax-aware sell guidance in the allocation output. Use CASH at price 1.00 for money market and cash positions. Export before replacing to preserve a backup.",
  },
  {
    id: "assets_home_cash",
    group: "Assets & Protection",
    title: "Reserve Requirements",
    desc: "The cash reserve floor the plan protects before drawing investments, plus spendable checking cash.",
    intro:
      "Reserve rules set how many months of spending to hold outside the investment portfolio. Home value and home sale inputs are on the Housing page.",
    help: "The reserve floor is the last buffer in probability analysis — the plan counts as failing when it cannot maintain this floor without depleting all accounts.",
  },
  {
    id: "annuity_death_benefits",
    group: "Assets & Protection",
    title: "Insurance",
    desc: "Year-by-year carrier illustration values for annuities and special income, plus all insurance policies (life, disability, long-term care, umbrella, auto, home, property and casualty, and other).",
    intro:
      "Enter values from each policy illustration; use 0 for years with no benefit. These totals appear in the Survivor and Estate report sections. All insurance policy details — owner, insured, beneficiary, face amount, and premiums, across life and protection policy types — are entered here as well.",
    help: "Rider benefits that step down or expire early can leave the survivor without protection — compare benefit schedules against the planning horizon set on Retirement Timing. Policy names must match any cross-references on stress pages.",
  },
  {
    id: "assets_special",
    group: "Assets & Protection",
    title: "Other Assets and Liabilities",
    desc: "Non-portfolio assets: notes receivable, HSA, 529 plans, equity compensation, collectibles, and personal property.",
    intro:
      "Asset type controls where the value appears — estate, education, Wellness, or charitable planning. Planned sale dates connect illiquid assets to future cash flow.",
    help: "HSA balances grow tax-free and should reflect intended use. Donor-advised fund configuration is set on Other Spending.",
  },
  {
    id: "estate",
    group: "Assets & Protection",
    title: "Estate Inputs",
    desc: "Federal and state exemptions, trust structure, beneficiary needs, lifetime gifting, and charitable intent.",
    intro:
      "Estate tax exposure is estimated from current exemptions and projected asset values at each mortality date. Trust structure choices affect how assets pass to the survivor and to beneficiaries. Insurance policies (life, disability, long-term care, umbrella, and property and casualty) are entered on Insurance.",
    help: "The federal exemption can change with law updates — confirm the current-law amount in Settings and model the impact of any reduction in Scenarios. Long-term-care hybrid policies with an investment component should also appear on Other assets.",
  },
  {
    id: "planning_workbench",
    group: null,
    title: "Planning Workbench",
    desc: "Unified place to review the baseline, assemble change sets, compare scenarios, run stress suites, and decide what to adopt.",
    intro:
      "The workbench turns Strategy (with Scenario comparison), Stress Tests, and Build Impact into one flow: Baseline → Change Set → Run Type → Impact → Decision.",
    help: "Planning cases are browser-local change sets. They do not alter the saved plan until you explicitly jump to source pages, edit inputs, save, and rebuild.",
  },
  {
    id: "distribution_strategy",
    group: "Strategy",
    title: "Distribution Strategy",
    desc: "Planning levers, Roth conversions, withdrawal order, and allocation & location in one decision workspace.",
    intro:
      "Use this page to decide when money comes out, from which buckets, how the portfolio is allocated and located, and whether Roth conversions improve the plan.",
    help: "Tabs preserve the existing source pages while making distribution and investment decisions easier to review together.",
  },
  {
    id: "state_residency",
    group: "Strategy",
    title: "State Residency Analysis",
    desc: "Compare state income-tax treatment and estimate geographic cost differences for auto insurance, homeowners insurance, utilities, and maintenance if you relocate.",
    intro:
      "Baseline state is set on Household People and the current budgeted amounts are the baseline. Enter a target relocation state to see estimated annual and lifetime deltas.",
    help: "Relocation interacts with Roth conversion room, state taxes, insurance costs, utilities, and survivor income. The geographic cost deltas are estimates you can override with real quotes.",
  },
  {
    id: "special_strategies",
    group: "Strategy",
    title: "Special Strategies",
    desc: "Home equity and charitable strategies for advanced planning cases.",
    intro:
      "Use only when the plan intentionally includes home-equity borrowing or charitable giving strategies.",
    help: "These strategies can improve outcomes, but they add assumptions and should be isolated in comparisons.",  },
  {
    id: "planning_levers",
    group: "Strategy",
    title: "Strategy Levers",
    desc: "Ranked estimates for every major lever — spending, retirement timing, Roth, allocation, home sale, and risk. Launch point for Strategy and Stress Test tools.",
    intro:
      "Each row estimates the isolated impact of one change, assuming all other inputs stay fixed. Use the rankings to prioritize, then make the actual change on its source page and rebuild.",
    help: "Changing a test amount on any row resizes the estimate without changing your plan. Only changes made on source pages and rebuilt into outputs affect actual projections.",
    hidden: true,
  },
  {
    id: "roth_conversion",
    // Ticket 286: embedded in the Strategy decide box; no own nav entry.
    group: null,
    title: "Roth Conversion",
    desc: "Conversion policy, ceiling (bracket or fixed dollar), Medicare income surcharge guardrails, and objective weights for tax, legacy, survivor, and estate.",
    intro:
      "Choose the policy first — the page shows only controls relevant to that policy. Forced conversion rows run before the optimizer and reduce the space available for voluntary conversions.",
    help: "Medicare income surcharge guardrails prevent projected income from crossing premium tiers during conversion years. Bracket-fill policies convert up to a marginal rate ceiling determined by the filing status on Household People.",
    hidden: true,
  },
  {
    id: "allocation_assets",
    // Ticket 286: embedded in the Strategy decide box; no own nav entry.
    group: null,
    title: "Asset allocation & location",
    desc: "User-defined targets or optimizer recommendation, asset-class include/exclude/alternate settings, and optional overrides.",
    intro:
      "In optimizer mode, the table controls which asset classes are eligible and whether existing holdings satisfy a sleeve before new buys are recommended. In user-defined mode, the same table is the allocation editor.",
    help: "Alternate-first means an existing holding already counts toward a sleeve target before new trades are recommended — use it to avoid unnecessary buy recommendations when an equivalent is already held.",
    hidden: true,
  },
  {
    id: "allocation_policy",
    group: "Strategy",
    title: "Allocation policy settings",
    desc: "Risk tolerance, glide path, concentration limits, expected return, volatility, and correlation assumptions that drive optimizer recommendations.",
    intro:
      "Supporting inputs for the optimizer — configure before running an optimizer recommendation. Capital-market assumptions here also connect to probability analysis when enabled.",
    help: "Higher return assumptions increase expected terminal net worth but can overstate success if volatility is understated. Glide path controls whether the target allocation de-risks as retirement approaches.",
    hidden: true,  },
  {
    id: "withdrawal_strategy",
    // Ticket 286: now the Spending workspace’s "Withdrawal Order" tab.
    group: null,
    title: "Withdrawal sequencing",
    desc: "Bucket draw order, trust withdrawals, and spousal rollover election. HSA withdrawal timing is set on Other Assets and Liabilities.",
    intro:
      "Earlier priority means a bucket is drawn sooner. Drawing taxable accounts first can manage required distributions but may realize capital gains; preserving Roth typically maximizes tax-free compounding for legacy.",
    help: "When required distributions exceed annual spending needs, the excess is reinvested in taxable unless converted to Roth — Roth conversion policy is set on the Roth Conversion tab. HSA timing controls are under Other Assets and Liabilities.",
    helpLink: { id: "distribution_strategy", label: "Open Distribution Strategy (Roth conversion is on that page)" },
    hidden: true,
  },
  {
    id: "heloc_strategy",
    group: "Strategy",
    title: "Home Equity Line",
    desc: "Bridge large discretionary spending with home equity, keeping invested assets untouched in early retirement.",
    intro:
      "Set credit limit, last draw year, and initial rate with drift. The projection draws from the line when large discretionary spending creates a cash gap, then repays the balance from home sale proceeds.",
    help: "The strategy improves projected net worth when compound growth on the preserved liquid assets exceeds total borrowing costs. It worsens outcomes when interest drag or reduced home equity at sale outweigh the investment benefit.",
    hidden: true,  },
  {
    id: "entity_charitable",
    group: "Strategy",
    title: "Charitable Giving",
    desc: "Charitable giving vehicle — direct gift, donor-advised fund, or qualified charitable distribution.",
    intro:
      "Qualified charitable distributions are available at age 70½ and satisfy required distributions tax-free. Annual giving amounts are set on Core spending.",
    help: "Donor-advised funds are most effective when contributed in a high-income year and granted over time. Qualified charitable distributions also reduce adjusted gross income, which can lower income-related Medicare surcharge tiers — model in combination with Roth Conversion.",
    hidden: true,  },
  {
    id: "monte_carlo_options",
    group: "Stress Tests",
    title: "Probability Analysis",
    desc: "Adverse-assumption and probability settings: simulation engine, trial count, return volatility, liquidity floor, and Wellness shock settings.",
    intro:
      "Quick mode is appropriate for workbench comparisons. Advanced mode runs more trials with advisor-ready precision — use before downloading final outputs.",
    help: "Stress assumptions are adverse tests, not forecasts. Success counts only trials where the plan maintains the reserve floor through the planning horizon.",
    hidden: true,
  },
  {
    id: "scenarios",
    group: "Strategy",
    title: "Scenario Change Sets",
    desc: "Named deterministic planning cases with specific assumption overrides — returns, inflation, home sale timing, spending adjustments, or custom changes.",
    intro:
      "Each scenario is a named Change Set. Save reusable cases here, then compare them in the Planning Workbench and workbook scenario columns.",
    help: "Use scenario change sets for questions with a specific answer (retire 2 years later, sell home in 2028, returns at 4%). Use Monte Carlo or Stress Suite for probability ranges and adverse assumptions around the base plan.",
    hidden: true,
  },
  {
    id: "survivor_stress",
    group: "Stress Tests",
    title: "Survivor / Early Death",
    desc: "Mortality ages, survivor filing status, income reduction, and account rollover treatment.",
    intro:
      "Early death shifts the survivor to single-filer tax brackets with reduced Social Security income. Key assumptions live on Retirement Timing — this page surfaces them so you can review what drives the stress result.",
    help: "The primary survivor risks: single-filer tax bracket compression, loss of one Social Security stream, and accelerated required distributions. Roth balances and survivor-protected pension income are the strongest offsets.",
    hidden: true,
  },
  {
    id: "ltc_stress",
    group: "Stress Tests",
    title: "Long-Term Care",
    desc: "Annual care cost, duration, and coverage benefit — showing the net out-of-pocket gap the portfolio must fund.",
    intro:
      "Set care cost and duration, then rebuild. The workbook LTC section shows the net gap after coverage and its effect on portfolio balance during the care years.",
    help: "Enable this under Settings → Optional modules to include LTC results in workbook outputs. Policy details (benefit amount, elimination period) are entered on Insurance & LTC Policies.",
    hidden: true,
  },
  {
    id: "divorce_options",
    group: "Stress Tests",
    title: "Divorce Planning",
    desc: "Retirement account transfer, alimony terms, asset division, and post-divorce Wellness — applied as a scenario overlay on the base plan.",
    intro:
      "All inputs here apply only to the divorce scenario — filing status shifts to Single and account balances reflect the transfer amount. The base plan is not affected.",
    help: "Enter the projected transfer value, not the current account balance. Alimony is taxable to recipient and deductible to payor only under pre-2019 agreements — flag the agreement date when modeling.",
    hidden: true,  },
  {
    id: "reports_and_review",
    group: "Reports & Review",
    title: "Reports & Review",
    desc: "One workspace for readiness, build, impact, results, downloads, and plan data review.",
    intro:
      "Start with preflight, build current reports, review impact and results, then download or print the final package.",
    help: "Use this page for anything related to output. It keeps report readiness and results in one flow.",
  },
  {
    id: "spending_dashboard",
    group: "Reports",
    title: "Spending Analysis",
    desc: "Actual vs budget by spending group, portfolio growth year-to-date, and alignment with the 30-year model.",
    intro:
      "Use Sync Actual Rate to compare annualized current-year spending with the Spending Categories projection controls — the primary feedback loop between real spending data and the retirement projection.",
    help: "Growth tracking compares investment accounts to prior-year balances. Unmapped categories appear as Other until assigned on Spending Categories.",
    hidden: true,
  },

  {
    id: "review",
    group: "Reports",
    title: "Download Reports",
    desc: "Build and download the workbook — downloads automatically save first when there are pending changes.",
    intro:
      "A build saves all current inputs, runs the full projection engine (cash flow, taxes, RMDs, Monte Carlo, scenarios), and writes the workbook. It is a read-only snapshot — edit values here, then rebuild.",
    help: "A successful build updates projected final net worth, lifetime taxes, Monte Carlo success, and all narrative sections. Use Save Changes to save without triggering a rebuild.",
    hidden: true,
  },
  {
    id: "build_impact",
    group: "Reports",
    title: "Impact & Build History",
    desc: "Universal comparison surface for baseline builds, planning cases, scenario comparisons, and stress-suite results.",
    intro:
      "Use the Planning Workbench to define the comparison, then use Impact & Build History to inspect the latest built result, snapshots, and before/after movement.",
    help: "Revert applies only to user-entered plan inputs — it does not undo system configuration, pricing changes, or browser-local planning cases. After a revert, rebuild to propagate restored values to outputs.",
    hidden: true,
  },
  {
    id: "detailed_results",
    group: "Reports",
    title: "Results",
    desc: "In-app view of all workbook sheets, charts, and data tables after a build — column groups can be collapsed to focus on key metrics.",
    intro:
      "Sheet navigation and row-level search are in the left panel. Download the workbook for full Excel fidelity on complex charts and conditional formatting.",
    help: "The Cash Flow Projection, Monte Carlo, and Allocation sheets have the most complex rendering. If a chart or table looks incomplete in this view, the downloaded workbook is authoritative.",
    hidden: true,
  },
  {
    id: "plan_data_report",
    group: "Reports",
    title: "Plan Data Review",
    desc: "Printable summary of every plan input, grouped by section — not editable here.",
    intro:
      "Holdings are summarized by account total, not lot level. All values reflect the last saved state — unsaved changes are not shown.",
    help: "Use as a preflight check before sharing with a client or advisor, or to audit all inputs before downloading final outputs.",
    hidden: true,
  },
  {
    id: "economic_tax_assumptions",
    group: "Settings",
    title: "Economic & Tax Assumptions",
    desc: "Baseline return rates, inflation, medical cost escalation, tax bracket indexing, and COLA — applied system-wide across all projections.",
    intro:
      "Changes here affect every projection year simultaneously. Use Scenarios to test alternatives without altering the base assumptions.",
    help: "Medical inflation is the most sensitive late-life input — a 1% change compounds across 30 years and materially shifts Medicare and care costs. Return assumptions should reflect long-term expected rates, not recent performance.",
  },
  {
    id: "optional_functions",
    group: "Settings",
    title: "Optional Modules",
    desc: "Enable or disable advanced planning sections: long-term care stress, divorce planning, home equity line, special needs, and others.",
    intro:
      "Disabled modules are excluded from the build to keep outputs focused. Some modules also add their own input pages to the navigation when enabled.",
    help: "Modules that add nav steps must be enabled here before those steps appear. Modules that only add workbook output can be toggled without changing the navigation.",
  },
  {
    id: "all_assumptions",
    group: "Settings",
    title: "Field Finder",
    desc: "Use when a value doesn't appear on its guided page.",
    intro:
      "Search by label, section, or keyword. Changes here have the same effect as editing on the source page — prefer the source page when nearby related fields need to be consistent.",
    help: "Holdings, budget lines, transactions, and liabilities are not here — those are managed on their dedicated tabs. This view covers only structured plan rows.",
  },
  {
    id: "workbook_formatting",
    group: "Settings",
    title: "Workbook Formatting",
    desc: "Fine-tune Excel column widths per sheet, table, and column. Changes apply on the next build.",
    intro:
      "Each sheet expands to its tables and columns. Edit a column width and save — overrides are stored and applied the next time you build the workbook.",
    help: "Overrides apply on top of the automatic layout, so a width you set here wins over the default sizing. A built workbook is required to read the current column structure.",
  },
  {
    id: "system_configuration",
    group: "Settings",
    title: "Data & Maintenance",
    desc: "Pricing snapshots, local backups, CSV export, recent-change log, and the raw System Configuration Console.",
    intro:
      "Operational tools for this workspace: manage pricing snapshots, back up and export data, review recent changes, and open the raw configuration console.",
    help: "These are maintenance utilities, not plan inputs. Change how the plan is modeled on the other Settings pages (assumptions, optional modules, field finder, workbook formatting).",
  },
];
let navSearchText = "";
let searchScope = "nav";
function stepSearchText(s) {
  let text = [s.id, s.group, s.title, s.desc, s.intro, s.help].join(" ");
  try {
    const rs = rowsForStep(s.id) || [];
    text +=
      " " +
      rs
        .map((r) =>
          [r.section, r.subsection, r.label, r.notes, r.units].join(" "),
        )
        .join(" ");
  } catch (_e) {}
  return text.toLowerCase();
}


// ACRONYMS/ACRONYM_DEFINITIONS moved to dashboard_decomp_row_model.js: their
// only consumers (formatAcronyms/acronymDefinitionsHtml/titleWord) live
// there now. That module's <script> tag loads before this one, so bare
// references here (e.g. loadCanonicalGlossary()'s Object.assign below)
// still resolve via the window bridge -- same fallthrough every other
// cross-module function call in this file already relies on.
const TERM_NOTES = {
  "Monte Carlo": "(repeated random simulation)",
  "terminal net worth": "(projected final portfolio value)",
  "Terminal net worth": "(projected final portfolio value)",
  "Terminal Net Worth": "(projected final portfolio value)",
  "Monte Carlo success":
    "(percentage of simulated scenarios where the plan stays solvent)",
  "probability of success":
    "(percentage of simulated scenarios where the plan stays solvent)",
  "advisor-ready": "(built with the slower, more precise settings meant for a final review, not a quick draft)",
};
function addParentheticals(text) {
  let out = String(text || "");
  Object.entries(TERM_NOTES).forEach(([term, note]) => {
    const re = new RegExp(
      "(?<![A-Za-z\(])" +
        term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") +
        "(?![A-Za-z\(])",
    );
    out = out.replace(re, term + " " + note);
  });
  return out;
}

// Local backups (status/policy state, controls HTML, save/run/refresh) moved
// to dashboard_decomp_local_backups.js (first modularization increment).
const STEP_HELP = {
  start: pageHelp(
    "Getting started",
    "These two buttons are mutually exclusive starting points. Starting new clears all household-specific data but keeps system defaults (inflation, return, and tax assumptions).",
    "Starting new clears all entered client facts, income, spending, and asset values. Opening the current plan reloads everything previously saved: income, assets, Roth strategy, Social Security, account balances, and YTD transactions.",
    "Start New when building a first draft or testing a completely different household. Open Current to continue where you left off. Bulk import and export utilities are in Settings → System Configuration.",
    "Starting new on top of existing work permanently clears the saved data unless you have exported a backup first. If unsure, export a backup before starting new.",
  ),
  roth_conversion: pageHelp(
    "Roth conversion strategy",
    "This page sets how voluntary Roth conversions are sized and scored. It is a planning optimizer, not a record of taxes already paid. Forced conversion rows are separate and represent actions already taken or imposed for a scenario.",
    "The Roth objective, tax-bracket ceiling, IRMAA guardrail, legacy weight, estate-tax weight, and survivor-risk weight work together. Tight guardrails preserve near-term liquidity and Medicare premium control; loose guardrails allow larger conversions when long-term tax savings or legacy value justify the current tax cost.",
    "Bracket-fill options convert up to a tax bracket. IRMAA guardrails stop or warn near Medicare premium cliffs. Fixed-dollar options force a chosen annual amount. Objective weights tell the scorer whether taxes, terminal net worth, survivor outcomes, or legacy value matter most.",
    "Higher conversion amounts usually increase current-year taxes and may reduce liquid assets, but can lower future RMDs, survivor tax compression, and lifetime taxes. More conservative guardrails usually protect near-term cash flow and Medicare premiums, but may leave future tax savings unused.",
  ),
  household_people: pageHelp(
    "Household people",
    "This page defines the people, tax identity, state, and filing status used by the model, plus when earned income stops, when retirement spending begins, and how long the household should be projected. These are identity and tax-foundation inputs rather than strategy levers. Mortality age is a planning horizon, not a prediction.",
    "Birth dates set ages. Ages connect to retirement timing, Social Security, Medicare, RMDs, mortality horizon, survivor years, and estate planning. Filing status and state connect to tax brackets, state taxes, and survivor tax treatment. Retirement dates connect to work income, savings contributions, healthcare bridge years, withdrawals, Roth conversion room, and Monte Carlo sequence risk. Life expectancy and survivor assumptions determine late-life taxes, RMD pressure, and legacy values.",
    "Use actual dates when possible. Use MFJ for married filing jointly, Single after a survivor period when appropriate, HOH only when household rules truly apply, and the resident state expected for the modeled period. Earlier retirement increases years funded by assets. Later retirement adds income, reduces withdrawals, and shortens the funding horizon.",
    "Changing ages or filing status can materially change lifetime taxes, RMD timing, Social Security timing, Medicare years, survivor cash flow, and terminal net worth. Changing state may affect state tax, estate tax, and residency optimizer output. Retiring later usually increases terminal net worth and probability of success. Retiring earlier usually lowers liquidity and may reduce success unless spending, income, or home-equity assumptions compensate.",
  ),
  income_work: pageHelp(
    "Work income",
    "This page captures earned income, self-employment income, payroll assumptions, employer benefits, and savings while the household is still working.",
    "Earned income feeds cash flow, payroll taxes, retirement-plan contributions, taxable income, ACA/IRMAA-sensitive income in transition years, and the YTD income comparison. Contributions connect to account balances and future withdrawal sources.",
    "Salary/W-2 values are gross annual amounts. Self-employment or S-Corp fields should match the intended entity strategy. Contribution fields should reflect annual expected savings, not current account balances.",
    "Higher earned income generally improves near-term cash flow and terminal net worth, but can increase lifetime taxes and reduce ACA subsidy eligibility. Higher contributions usually improve terminal net worth but reduce spendable current cash.",
  ),
  income_retirement: pageHelp(
    "Retirement income",
    "This page captures Social Security, pension, annuity, and other retirement income streams. These are income floors that can reduce portfolio withdrawals.",
    "Claim ages, survivor percentages, COLA settings, and present-value horizons connect to cash flow, tax brackets, survivor results, and allocation coverage. Some guaranteed income can also be treated as fixed-income-like coverage in allocation analysis.",
    "Social Security fields should use SSA statement values when available. Joint/survivor percentages describe how much income continues to the survivor. COLA choices indicate whether the payment keeps pace with inflation.",
    "Higher guaranteed income usually improves probability of success and reduces withdrawals, but may increase taxable income and affect Roth conversion room. Delayed claiming may reduce early liquidity but raise later survivor-protected income.",
  ),
  spending_core: pageHelp(
    "Spending Categories",
    "This page is the comprehensive category model for income and expenses, excluding taxes/transfers. Projection spending controls remain here, while Housing, Wellness, and Travel detailed budget inputs stay on their own pages.",
    "Core spending flows directly into annual withdrawals, taxable income, liquidity stress, Monte Carlo success, and planning-lever sensitivity. Growth mode and freeze year determine how that spending changes over time.",
    "Use CPI/general inflation when spending should rise with inflation. Use manual override when lifestyle spending should grow at a different rate. Use the freeze year when spending increases stop or intentionally flatten.",
    "Higher recurring spending usually lowers terminal net worth and probability of success. Lower spending or earlier spending freezes usually improve both, especially in the first retirement decade.",
  ),
  spending_mortgage_events: pageHelp(
    "Housing",
    "This page captures all housing-related costs and plans: current mortgage, home operating costs, a planned home sale, and up to two next-step housing arrangements. Rent appears only when configured with a positive rent value.",
    "Mortgage payments and housing operating costs reduce annual cash flow. The home sale year and price affect net worth and liquidity. Next-step housing costs (rent or new mortgage) replace current housing spending in the projection.",
    "Enter insurance, utilities, and maintenance as annual amounts. For the next-step housing, enter the purchase price and financing plus the ongoing operating costs for that property. Rent fields appear only when a positive rent assumption is configured.",
    "Lower mortgage payments improve near-term cash flow. Selling and downsizing can unlock home equity. Renting instead of buying reduces balance-sheet exposure but may increase long-term housing costs.",
  ),
  spending_travel_extras: pageHelp(
    "Large Discretionary",
    "This page captures flexible large expenses that are not Housing, Wellness, Travel, taxes, or recurring Core Spending: weddings, vehicles, gifts, or family support.",
    "Each row adds cash-flow needs in a specific year or recurring range. These rows connect to the Planning Levers page because they are often adjustable if markets or liquidity are stressed.",
    "Use category budgets or detail lines to document whether the item is must-fund, flexible, or aspirational.",
    "Higher discretionary spending lowers terminal net worth and can sharply reduce probability of success when it occurs early. Delaying, reducing, or making these items conditional can improve success without changing core lifestyle assumptions.",
  ),
  spending_dashboard: pageHelp(
    "Spending Analysis",
    "Combines the current-year performance summary (spending, income, portfolio growth) with the budget vs actuals tracker and the link to the 30-year retirement model.",
    "Transactions from Income & Expense Transactions feed both the summary and the tracker. Spending Categories controls how transactions are assigned to the canonical Tracking Type → Group → Category hierarchy.",
    "The summary shows actual vs projected spending, income, and growth. The tracker compares annualized actuals to category budgets and to the retirement model core spending assumption. Use Sync Actual Rate to update the 30-year model.",
    "Spending rate above the model assumption reduces projected net worth. Identifying over-budget groups early — before the annual rebuild — gives time to recalibrate Core spending or adjust plans.",
  ),
  spending_travel: pageHelp(
    "Travel",
    "Travel is the only editable source for Travel budgets and scheduled trip spending.",
    "Travel budgets flow into the projection and can be referenced read-only elsewhere.",
    "Enter category budgets or time-bounded lines for trips and travel memberships.",
    "Separating Travel prevents double-counting with Core Spending and Large Discretionary.",
  ),
  spending_setup: pageHelp(
    "Spending Categories",
    "Manage the canonical category tree and optional transaction auto-mapping rules.",
    "Spending Categories controls how actual transactions roll up by Tracking Type, Group, and Category. Accounts & Sources live with Income & Expense Transactions because they classify where money came from, not what it was for.",
    "Most users should map categories directly in the Spending Categories hierarchy. Use Advanced Auto-Mapping Rules only for merchant/category text rules that should repeat automatically.",
    "Canonical categories carry their Tracking Type and Group, so a separate flat group-mapping table is no longer part of the workflow.",
  ),
  ytd_transactions: pageHelp(
    "Income & Expense Transactions",
    "Import and manage current-year income and expense transaction data.",
    "Upload a CSV from your bank or brokerage. Use Replace all to start fresh or Add to merge new transactions with existing ones. Remove Duplicates deduplicates by Date + Merchant + Amount + Account.",
    "Required CSV columns: Date, Merchant, Category, Account, Amount. Optional: Original Statement, Notes, Tags, Owner. Only current-year rows are imported.",
    "More complete transaction data improves the accuracy of the YTD spending, income, and growth analysis in Spending Analysis.",
  ),
  holdings: pageHelp(
    "Investment holdings",
    "One row per tax lot: each purchase or reinvestment of a security with shares, price, cost basis, and purchase date.",
    "Holdings drive account totals, allocation drift, pricing, tax-lot sell guidance, rebalancing recommendations, and year-to-date growth for investment accounts. Account names must match names used on Withdrawal Sequencing and Asset Allocation.",
    "Use CASH at price 1.00 for money market and cash positions. Keep separate lots per purchase when tax-basis guidance matters — blended basis reduces sell-guidance precision. For large broker downloads, export a backup before importing to replace all.",
    "More complete cost basis and purchase dates improve taxable sell guidance and estimated tax impact on trade recommendations.",
  ),
  assets_home_cash: pageHelp(
    "Cash reserves",
    "This page captures checking cash and liquidity reserve rules. Home value and related fields have moved to the Housing tab.",
    "Cash and reserve rules connect to withdrawal sequencing, liquidity floors, and Monte Carlo failure modes.",
    "Checking cash is spendable cash outside the holdings table. Reserve rules describe how many years of spending to preserve and which account bucket should be protected. Home value and home sale fields are now on the Housing tab.",
    "Higher cash reserves improve liquidity resilience but can reduce expected return if too much capital stays out of the portfolio.",
  ),
  assets_special: pageHelp(
    "Other assets",
    "This page captures non-portfolio assets such as note receivable, HSA, DAF, 529 plans, equity compensation, collectibles, vehicles, and policy-related assets.",
    "Asset type controls where the value appears, whether it is liquid, how it is taxed, and whether it affects estate, education, Wellness, charitable, or growth modules. Planned sale dates connect non-liquid assets to future cash flow.",
    "Use the asset type that best describes the economic purpose. Enter today's fair value, timing assumptions, and whether the asset is liquid or restricted. Notes receivable should use principal and schedule fields, not straight-line extrapolation.",
    "Higher liquid asset values usually improve success probability. Higher illiquid asset values increase terminal net worth and estate values but may not fund spending unless sale or borrowing is modeled.",
  ),
  estate: pageHelp(
    "Estate inputs",
    "This page captures estate-tax, trust, beneficiary, legacy-planning, and gifting assumptions. It tells the model how assets should be interpreted after death or for survivor planning.",
    "Federal/state exemptions, CST/QTIP settings, beneficiary needs, special-needs planning, gifting, and charitable intent connect to legacy value, estate-tax exposure, survivor analysis, Roth strategy scoring, and executor-oriented workbook notes. Insurance policies (life, disability, long-term care, umbrella, and property and casualty) are entered on Insurance.",
    "Use monitor/balanced/strong estate objectives depending on whether estate tax is a watch item or a decision driver. Enter trust and beneficiary facts only when they are part of the intended plan.",
    "More aggressive estate-tax planning may reduce projected estate tax and improve legacy quality, but can reduce flexibility if assets are transferred, restricted, or earmarked too early.",
  ),
  annuity_death_benefits: pageHelp(
    "Insurance",
    "This page records policy-by-year death benefits for annuities or riders, and all insurance policy details (life, disability, long-term care, umbrella, auto, home, property and casualty, and other). It combines a year-by-year schedule with individual policy records — not a generic account balance table.",
    "Each annuity policy row connects to survivor, estate, and legacy reporting. Year columns show how protection changes over time and whether a benefit disappears before the end of the plan. Policy premiums connect to cash flow each year; benefit amounts appear in the Survivor and Long-Term Care Stress report sections.",
    "Enter the carrier illustration values for each year for annuities. Use 0 when no death benefit is available in that year. For any insurance policy, use policy type, premium end, term end, benefit amount, and owner/insured fields consistently. Keep policy names consistent with other insurance/annuity entries.",
    "Higher death benefits improve survivor/legacy protection but may come with lower investment growth, liquidity restrictions, or ongoing rider costs that should be reflected elsewhere. More insurance coverage can reduce downside risk but premiums may lower terminal net worth if no claim occurs.",
  ),
  assumption_signoff: pageHelp(
    "Assumptions review",
    "This page is a pre-build interpretation checklist. It does not create new calculations; it helps confirm that the assumptions behind the report are coherent.",
    "Risk tolerance, spending flexibility, longevity, tax strategy, Roth objectives, inflation, returns, estate intent, and liquidity assumptions all connect to multiple workbook sections and recommendations.",
    "Use this page to decide whether assumptions are documented, estimated, or scenario-specific. If a checklist item reveals uncertainty, edit the source page before building.",
    "Better assumptions reduce false precision. Changing checklist-related inputs can affect TNW, lifetime taxes, Monte Carlo success, survivor results, and report narratives.",
  ),
  review: pageHelp(
    "Download Reports",
    "Downloads automatically save and build as needed — you do not need to save separately before downloading.",
    "Save Changes stores all entered values. Download Workbook saves, builds, and delivers in one click when there are unsaved changes or no current build.",
    "Use Save Changes when you want to save without triggering a rebuild. Use Download when ready for final output. Resolve any required-field warnings before downloading. Bulk import/export is in Settings → System Configuration.",
    "A successful build refreshes projected net worth, lifetime taxes, Monte Carlo success, allocation recommendations, and all narrative sections. The downloaded file reflects the last successful build — download again after each rebuild to get the latest.",
  ),
  build_impact: pageHelp(
    "Build impact",
    "This page explains what changed in the latest build compared with the session baseline. It is a review and revert tool, not a data-entry page.",
    "The comparison uses values captured before this editing session and values after the last successful build. It helps connect changed assumptions to terminal net worth, lifetime taxes, Roth conversions, liquidity, and output warnings.",
    "Revert restores captured before-values for edited inputs. Rebuild confirms whether the reverted or edited plan changes the authoritative workbook output.",
    "Large differences identify high-leverage assumptions. A positive terminal-net-worth change is not automatically better if it increases lifetime taxes, liquidity stress, survivor risk, or Monte Carlo failure.",
  ),
  planning_workbench: pageHelp(
    "Planning Workbench",
    "This page is the unified planning flow for comparing the baseline, named change sets, scenario ideas, stress assumptions, and final decisions. Planning cases are browser-local notes until you deliberately adopt changes on source pages.",
    "The workbench connects Strategy Levers, Scenario Change Sets, Stress Suite settings, and Build Impact around the same Baseline → Change Set → Run Type → Impact → Decision vocabulary. Saved cases help organize what you are testing without mutating the saved plan.",
    "Start with the baseline, save a staged edit or strategy as a case, choose whether to compare or stress it, then use the Decision panel to adopt, archive, or leave it as reference. Adopted changes still need to be made on the source pages, saved, and rebuilt.",
    "A planning case can clarify what to test next, but it does not change workbook results by itself. Only saved source-page edits followed by a rebuild affect terminal net worth, lifetime taxes, Monte Carlo success, and report outputs.",
  ),
  planning_levers: pageHelp(
    "Planning overview",
    "This is your decision hub. It shows your current projected outcome and screens the practical changes most likely to move terminal net worth or probability of success, then links to every strategy and stress test.",
    "Each lever estimates a separate effect using latest build KPIs and current plan inputs. Spending, retirement timing, reserve, home-equity, Roth, tax, and risk levers relate to source pages where actual values must be changed.",
    "Edit one test amount at a time to isolate the likely effect. Rank by terminal net worth when legacy/estate value is the goal; rank by probability of success when liquidity and funded-spending reliability are the goal.",
    "Levers that improve both TNW and success are strongest. Some levers trade one against the other: higher risk may increase TNW but lower success; larger reserves may improve success but reduce return; Roth conversions may lower lifetime taxes but reduce near-term liquidity.",
  ),
  detailed_results: pageHelp(
    "Retirement Plan Workbook",
    "In-app view of every workbook sheet after a build — Cash Flow Projection, Monte Carlo, Allocation, Lifetime Taxes, Estate, and all strategy comparisons.",
    "Each sheet matches the corresponding Excel tab. Column groups can be collapsed to focus on key metrics. Row-level search finds any value across all sheets.",
    "Use the sheet selector in the left panel to navigate between sections. Download the workbook when you need full chart fidelity or conditional formatting that can't be approximated here.",
    "If a sheet shows unexpected values, the issue is in the plan inputs — identify the relevant input page, correct the value, and rebuild.",
  ),
  plan_data_report: pageHelp(
    "Plan Data Summary",
    "A read-only view of everything you have entered across all plan sections.",
    "Every field from every input tab is shown here, grouped by section. Holdings are summarized by account.",
    "Use this after filling in the plan to do a final review before building outputs.",
    "If a field looks wrong here, navigate to the corresponding input tab to correct it.",
  ),
  monte_carlo_options: pageHelp(
    "Monte Carlo",
    "This page controls how uncertainty is simulated across market, inflation, tax-indexing, and Wellness-shock paths. It determines how probability of success is measured.",
    "Simulation count, engine mode, return volatility, liquidity floors, and stress assumptions connect to probability of success, downside wealth, failure timing, and build time.",
    "Quick/vectorized mode is faster and approximate. Advanced/exact mode is slower but advisor-ready. More trials reduce random noise. Tighter liquidity floors make success harder but more realistic.",
    "More conservative settings usually lower probability of success but make the risk result more reliable. Faster settings help drafts but should not drive final recommendations without confirmation.",
  ),
  scenarios: pageHelp(
    "Scenario analysis",
    "This page defines named deterministic what-if cases that compare a specific bundle of lever/assumption changes against the base plan. It is a comparison mode, not a random-draw stress test like Monte Carlo.",
    "Scenario rows can change returns, inflation, home sale assumptions, spending, tax, or timing for workbook scenario sheets and risk narratives. Economy and home-sale stress cases belong here.",
    "Use one scenario per clear question: retire later, sell home, inflation stress, low returns, spending cut, or tax change. Keep scenario labels descriptive so workbook comparisons are readable.",
    "Scenarios that lean adverse often reduce TNW and success indicators, but comparing bundles side by side shows which lever combinations protect the plan best.",
  ),
  divorce_options: pageHelp(
    "Divorce / QDRO stress",
    "This page models divorce-specific assumptions only when that optional module is enabled. It should not be used for ordinary married/survivor planning.",
    "Filing status, QDRO transfers, alimony, asset division, property assumptions, and health costs connect to taxes, ownership, cash flow, survivor-like outcomes, and risk.",
    "Turn the module on only for an explicit divorce scenario. Use actual legal or negotiated assumptions when available; otherwise label the case as hypothetical.",
    "Changing from married to split-household assumptions can materially reduce terminal net worth, raise lifetime taxes, change Wellness costs, and reduce probability of success.",
  ),
  state_residency: pageHelp(
    "State residency analysis",
    "This strategy page compares the baseline home state with a target relocation state for tax and geographic cost differences. The baseline state is set on Household people, and current budgeted amounts are the baseline.",
    "State income tax connects to net cash flow and lifetime taxes. Estimated geographic deltas for auto insurance, homeowners insurance, utilities, and home maintenance connect to the State Residency workbook sheet.",
    "Enter the target state. The workbook estimates the annual and lifetime change for each cost category from relative cost-of-living factors — replace them with real quotes when available.",
    "A lower-tax or lower-cost state can improve lifetime net cash flow, but verify housing, healthcare, and lifestyle differences before treating relocation as a plan decision.",
  ),
  heloc_strategy: pageHelp(
    "HELOC strategy",
    "Model a home equity line of credit that funds large discretionary spending in early retirement years instead of drawing from liquid assets.",
    "HELOC draw reduces gap filled by liquid assets, allowing taxable/IRA balances to compound longer. Interest is paid from cash flow annually. The outstanding balance is repaid from home sale proceeds.",
    "Enter a credit limit, the last year of the draw period, an initial interest rate, and an annual rate drift. The projection automatically draws from the HELOC when large discretionary spending creates a cash gap, up to available credit.",
    "HELOC improves TNW when the compound benefit of undisturbed liquid assets exceeds borrowing costs. It worsens outcomes when interest drag or reduced home equity at sale outweigh the investment benefit.",
  ),
  entity_charitable: pageHelp(
    "Charitable giving",
    "This strategy page covers the charitable giving vehicle: cash, donor-advised fund, or qualified charitable distribution. Annual giving amounts are entered on Core spending. Business-entity choice (S-Corp vs LLC) is entered on Work Income.",
    "Charitable vehicle choice connects to deductions, lifetime taxes, and legacy, and appears in a dedicated workbook sheet.",
    "Choose how charitable gifts are funded. Use QCDs after RMD age where appropriate.",
    "Charitable vehicle choice can lower taxes and increase legacy, but may reduce near-term liquidity.",
  ),
  survivor_stress: pageHelp(
    "Survivor / early death",
    "This stress test reviews how the plan holds up if one spouse dies early. Survivor and mortality assumptions also appear on Retirement timing.",
    "Mortality ages, survivor filing status, and spousal rollover connect to survivor tax compression, RMD timing, income loss, and late-life net worth. The full result is the Survivor workbook sheet.",
    "Review the surfaced survivor assumptions, then rebuild to see the survivor stress outcome. Adjust the source values on Retirement timing if needed.",
    "Early death often compresses tax brackets for the survivor and reduces household income; adequate insurance and Roth balances can soften the impact.",
  ),
  ltc_stress: pageHelp(
    "Long-term care",
    "This stress test models a long-term-care cost shock and how existing coverage absorbs it. LTC policy details also appear on Other assets.",
    "LTC cost, duration, and coverage connect to late-life spending shocks, liquidity, and the combined LTC / life insurance workbook section. Enable the Long-Term-Care Stress module to include it in outputs.",
    "Enter or review the LTC assumptions and coverage, then rebuild. Turn on the LTC stress module in Optional modules if results do not appear.",
    "A long-term-care event is a major downside risk; coverage reduces the shock but adds premium cost. Compare funded outcomes with and without coverage.",
  ),
  allocation_policy: pageHelp(
    "Asset allocation assumptions",
    "This page defines supporting assumptions for portfolio recommendation logic: risk tolerance, glide path, capital-market assumptions, and optimizer inputs.",
    "Risk tolerance and glide path connect household capacity to target allocation. Expected return, volatility, and correlations connect to optimizer scoring and Monte Carlo assumptions when enabled.",
    "Expected return is the long-term reward assumption. Volatility is downside bumpiness. Correlation describes diversification. Glide path controls whether the portfolio de-risks over time.",
    "Higher return assumptions usually increase recommended growth exposure and TNW projections, but can overstate success if risk is understated. Higher volatility usually lowers optimizer preference unless diversification benefits offset it.",
  ),
  allocation_assets: pageHelp(
    "Asset allocation optimizer",
    "This page chooses the allocation target, asset-class inclusion policy, alternates, user targets, optimizer overrides, and trade recommendation context.",
    "Selection mode determines whether user targets or optimizer recommendations drive the workbook. Include/exclude/alternate controls connect non-liquid assets, pensions, home equity, or notes to liquid target recommendations. Holdings and tax lots connect to trade guidance.",
    "Use user target when the allocation is advisor-directed. Use optimizer recommendation when model constraints should choose the mix. Include allows target exposure; Exclude prevents it; Consider alternate first lets an existing asset satisfy the sleeve before new trades are recommended.",
    "Increasing growth assets may raise expected TNW but can lower success in bad early markets. Excluding or covering an asset class can reduce unnecessary trades. Tax-aware sell guidance can lower realized tax cost but may leave more drift.",
  ),
  withdrawal_strategy: pageHelp(
    "Withdrawal strategy optimizer",
    "This page sets the order and constraints used to fund annual spending from available account buckets. HSA withdrawal timing is controlled on Other → Other assets.",
    "Withdrawal priority connects to taxable income, RMDs, Roth preservation, trust withdrawals, cash reserve rules, survivor cash flow, and annual cash-flow schedules. HSA scheduled withdrawals still feed the same cash-flow engine after they are set on Other.",
    "Earlier priority means the bucket is used sooner. Preserving Roth usually supports legacy and tax diversification; spending taxable first may manage RMDs but can trigger capital gains. Use Other assets when you want to intentionally spend HSA balances over a window.",
    "Changing withdrawal order can shift lifetime taxes, terminal net worth, liquidity failures, and survivor outcomes. It can improve one metric while worsening another, so rebuild and compare.",
  ),
  economic_tax_assumptions: pageHelp(
    "Economic and tax assumptions",
    "This System page holds default inflation, COLA, tax-indexing, payroll, Wellness, and return assumptions used across the model.",
    "Inflation connects spending, Social Security COLA, tax brackets, IRMAA thresholds, Wellness costs, and capital-market projections. Tax constants and indexing assumptions connect to Roth and lifetime-tax analysis.",
    "Use current-law/default assumptions for base plans; use scenarios to compare alternative assumption sets. Keep tax data source years current before relying on tax-sensitive recommendations.",
    "Higher inflation usually lowers real purchasing power and can reduce success unless income/assets adjust. Higher Wellness inflation raises late-life spending. Changing tax assumptions can materially change lifetime taxes and Roth recommendations.",
  ),
  system_configuration: pageHelp(
    "System Configuration",
    "Advanced configuration for build settings, market data pricing, state tax reference tables, and bulk data management. Changes here apply across all plans.",
    "Pricing mode determines how holding values are updated — live market data vs cached values. Tax and reference tables drive projection tax calculations, IRMAA thresholds, and bracket indexing. Build flags control what the workbook build includes.",
    "Use focused input pages for normal plan edits. Use bulk CSV adapters here only for reference table maintenance or data recovery. Rebuild after any change to pricing, tax, or optimizer settings.",
    "System changes affect account values, allocation recommendations, lifetime taxes, Monte Carlo results, and build output. Isolate one settings family at a time when diagnosing unexpected results.",
  ),
  all_assumptions: pageHelp(
    "All assumptions",
    "Every editable plan field in one searchable view — a safety net for values that don't surface clearly on their guided pages.",
    "Fields on this page belong to many different sections. Changing a field here has the same build effect as changing it on the source page, but without the surrounding related fields as context.",
    "Search by label, section, or keyword. Review field help before changing unfamiliar inputs. Prefer the source page when nearby related values need to be consistent.",
    "Because this page combines fields from every section, a change can affect almost any output. Holdings, budget lines, transactions, and liabilities are on their dedicated tabs — not here.",
  ),
  optional_functions: pageHelp(
    "Optional modules",
    "Enables or disables entire planning sections — long-term care stress, divorce planning, home equity line, charitable giving, special needs, equity compensation, 529 education funding, and others — that are excluded from the build when off.",
    "Some modules add their own nav pages (Special Strategies, Long-Term Care, Divorce Planning) that only appear once the module is enabled here; other modules only change workbook output without adding a page.",
    "Enable a module before entering its detail elsewhere in the plan — its input page won't appear in navigation until it's turned on. Turn a module off to exclude it from the build without deleting its saved data.",
    "Turning a module off removes its section from the workbook build entirely, not just from navigation. Turning one on can add new required fields to complete before the plan is build-ready.",
  ),
  workbook_formatting: pageHelp(
    "Workbook formatting",
    "Adjusts the Excel column widths in the generated workbook, organized by sheet, then by table (for multi-table sheets like Net Worth and Cash Flow), then by column.",
    "Widths are read from the most recently built workbook. Each edit is saved as a per-column override and layered on top of the standard layout; a column you never touch keeps its automatic width.",
    "Widen a column when its numbers or labels look cramped or clipped; narrow one to fit more columns on a printed page. Rebuild the workbook to see the change.",
    "No planning impact — this changes only the appearance of the Excel output, never any calculated value.",
  ),
};
let apiBase = "",
  appReady = false,
  rows = [],
  moduleStatus = {},
  // §7.4: server-computed {step_gates, section_gates} from module_catalog,
  // replacing the hand-maintained stepGatedByOptionalModule/ROW_MODULE_GATES.
  moduleGates = { step_gates: {}, section_gates: {} },
  liabilitiesText = "",
  liabilitiesChanged = false,
  dirty = new Map(),
  travelExtras = [],
  travelTypes = [],
  travelExtrasChanged = false,
  liquidityBuffers = [],
  liquidityChanged = false,
  forcedConversions = [],
  forcedConversionsChanged = false,
  forcedConversionAccounts = [],
  homeSaleSplits = [],
  homeSaleSplitsChanged = false,
  homeSaleSplitAccounts = [],
  residencySchedule = [],
  residencyScheduleChanged = false,
  estateStateOptions = [],
  planLoaded = false,
  demoModeActive = false,
  activeStep = "start",
  searchText = "",
  runtime = {},
  lastBuildOk = false,
  planSource = "Not loaded",
  appExiting = false,
  buildPreflight = null;
let inactiveEditReveals = new Set();
let ytdData = null,
  ytdTransactionsChanged = false,
  ytdAccountsChanged = false,
  ytdTxSearch = "",
  ytdTxSort = { field: "Date", dir: "desc" },
  ytdCategoryFilter = "",
  ytdAccountFilter = "",
  ytdTxPage = 0, ytdTxColsCollapsed = true;
const YTD_ACTUALS_PERIOD_LS_KEY = "retirement.ytd_actuals_period.v1";
let ytdActualsPeriod = readYtdActualsPeriod();
let taxonomyData = null,
  taxonomyFlat = {},
  taxonomyLoading = false,
  taxonomyError = "";
let taxFreshnessData = null,
  taxFreshnessLoading = false;
let spendingModelData = null,
  spendingModelLoading = false,
  spendingModelError = "";
let mappingRules = null,
  rulesChanged = false;
let taxBudget = {},
  taxBudgetChanged = false,
  taxBudgetLoaded = false;
let budgetLines = [],
  budgetLinesChanged = false,
  budgetLinesLoaded = false,
  budgetSectionMode = {},
  categoryBudgetMode = {},
  groupBudgetMode = {};
let ytdDuplicateGroups = null,
  ytdDuplicateSelected = new Set();
// Ticket 290: measured at 3000 transactions (a realistic full-year history),
// a 500-row page produced ~5,000 form-control DOM nodes for the transaction
// table alone (each row renders ~10 <input>/<select> elements, not plain
// text cells) and was a real, multi-second contributor to the renderMain()
// that builds this page. Lowered to 100 -- still several screens of rows
// before a planner needs "Next", and a direct, proportional cut to the
// dominant cost this ticket's own measurement identified, using pagination
// machinery that already existed rather than adding new code.
const YTD_TX_PAGE_SIZE = 100;
let detailedResultsData = null,
  detailedResultSheets = {},
  detailedResultsLoading = false,
  detailedResultSheetLoading = false,
  detailedResultSheetLoadingName = "",
  detailedResultsError = "",
  detailedResultSheetError = "",
  activeDetailedSheet = "",
  detailResultsSearchText = "",
  detailedResultSheetSeq = 0;
let detailedResultSheetInFlight = {},
  detailedResultsIndexInFlight = null;
let detailedResultsNavOpen = false;
try {
  detailedResultsNavOpen =
    window.localStorage &&
    window.localStorage.getItem("retirementDetailedResultsNavOpen") === "1";
} catch (e) {
  detailedResultsNavOpen = false;
}
let detailedResultsProgress = {
  active: false,
  pct: 0,
  phase: "",
  detail: "",
  startedAt: 0,
};
let detailedResultsProgressTimer = null;
let detailedColumnGroupsOpen = {};

function restoreWorkbookViewState() {
  try {
    var s = localStorage.getItem("wbSheet");
    if (s) activeDetailedSheet = s;
    var g = localStorage.getItem("wbGroups");
    if (g) detailedColumnGroupsOpen = JSON.parse(g) || {};
  } catch (_e) {}
}
let buildOverlayStartedAt = 0,
  buildOverlayTimer = null,
  buildOverlayDepth = 0,
  buildOverlayLastTitle = "",
  buildOverlayLastPct = 0;
let allocationPreview = null,
  allocationPreviewKey = "",
  allocationPreviewLoading = false,
  allocationPreviewError = "",
  allocationPreviewSeq = 0;
const PLAN_DATA_FILES = [
  "client_data.csv",
  "client_household.csv",
  "client_income.csv",
  "client_spending.csv",
  "client_assets.csv",
  "client_policy.csv",
  "client_insurance_estate.csv",
  "client_optional_functions.csv",
  "asset_class_optimizer_controls.csv",
  "client_holdings.csv",
  "target_allocation.csv",
  "ytd_transactions.csv",
  "ytd_account_setup.csv",
  "ytd_import_history.csv",
  "client_data.json",
  "client_data.yaml",
  "client_household.json",
  "client_income.json",
  "client_spending.json",
  "client_assets.json",
  "client_policy.json",
  "client_insurance_estate.json",
  "client_optional_functions.json",
  "asset_class_optimizer_controls.json",
  "client_household.yaml",
  "client_income.yaml",
  "client_spending.yaml",
  "client_assets.yaml",
  "client_policy.yaml",
  "client_insurance_estate.yaml",
  "client_optional_functions.yaml",
  "asset_class_optimizer_controls.yaml",
];
const REQUIRED_PLAN_DATA_FILES = ["client_data.csv", "client_holdings.csv"];
const PROTECTED_CLIENT_DATA_KEYS = new Set([
  "Household\x1f\x1fmember_1_retirement_date",
  "Household\x1f\x1fmember_2_retirement_date",
]);
let buildProgressTicker = null;
let _smoothDelayTimer = null,
  _smoothIntervalTimer = null,
  _smoothStart = 0,
  _smoothFromPct = 0,
  _smoothCap = 82,
  _smoothSpeed = 22;
let sessionChanges = new Map(),
  sessionSpecialChanges = new Set(),
  lastBuildSummary = null,
  lastBuildCompare = null,
  sessionBaselineSummary = null,
  sessionBaselineCaptured = false;
let buildHistory = [];
const BUILD_HISTORY_MAX = 10;
const BUILD_HISTORY_LS_KEY = "buildHistory_v1";
let planChatMessages = [];
var activePlanReportSection = "household";

let planningLeverInputs = {
  spendingCut: 10000,
  retireLaterYears: 1,
  largeExpenseCut: 25000,
  sCorpBenefit: 29000,
  rothTaxSavings: 50000,
  returnBps: 25,
  cashReserve: 50000,
  homeEquityBackstop: 250000,
  helocCredit: 200000,
  guardrailPct: 10,
  ltcCoverage: 250000,
};
// Build compare is session-only; populated after first successful build.
let planFileNames = {
  clientData: "client_data.csv",
  clientHoldings: "client_holdings.csv",
};
let planFolderHandle = null,
  planFolderName = "";
let _autoLoadPref = null; // null = not yet loaded from server; bool after first API check

function helpList(items) {
  const clean = (items || []).filter((x) => String(x || "").trim());
  if (!clean.length) return "";
  return `<ul>${clean.map((x) => `<li>${x}</li>`).join("")}</ul>`;
}
function stepHelpLinkHtml(st) {
  if (!st || !st.helpLink) return "";
  return ` <a href="#" onclick="setStep('${st.helpLink.id}');return false">${esc(st.helpLink.label)}</a>`;
}
function pageHelp(title, meaning, connections, options, impact) {
  const acronyms = acronymDefinitionsHtml([
    title,
    meaning,
    connections,
    options,
    impact,
  ]);
  return `<div class="help-title">${esc(title)}</div><div class="help-body"><h3>What this page is for</h3><p>${esc(addParentheticals(meaning))}</p><h3>How the values work together</h3><p>${esc(addParentheticals(connections))}</p><h3>How to choose values</h3><p>${esc(addParentheticals(options))}</p><h3>Likely planning impact</h3><p>${esc(addParentheticals(impact))}</p>${acronyms}</div>`;
}
const SYSTEM_CONFIG_FIELD_HELP = {
  local_backups: pageHelp(
    "Local backups",
    "Opt-in .rpx database backups with automatic retention, run opportunistically after Save Changes or a successful build.",
    "Cadence controls how often a backup is captured (daily or every build); retention controls how many backups are kept before the oldest is discarded.",
    "Enable automatic backups for ordinary households working over multiple sessions. Use Back up now before a risky bulk edit or import.",
    "No planning impact — backups protect saved data but do not change projections.",
  ),
  pricing_mode: pageHelp(
    "Pricing mode",
    "Checks live/cache/fallback pricing status, refreshes live quotes, and can freeze a saved price snapshot for reproducible advisor values.",
    "Refresh Prices pulls new quotes from live providers. Freeze latest prices locks the current snapshot so it stops changing between sessions; Unfreeze resumes normal pricing.",
    "Refresh Prices when the cache looks stale before a final build. Freeze prices only when you need the exact same holdings values to reproduce across multiple report runs.",
    "Different pricing modes change current market values used for account totals, allocation drift, and trade guidance — they do not change your saved cost basis or plan assumptions.",
  ),
  session_changes: pageHelp(
    "Session changes",
    "Lists the plan edits made during the current session, grouped by page, so you can review what changed before saving or building.",
    "This is a read-only log; it does not let you revert changes here — use Build Impact for compare-and-revert.",
    "Review this list before Save Changes if you want to confirm exactly what will be saved.",
    "No planning impact — this is a review log, not an input.",
  ),
  annualized_actuals: pageHelp(
    "Annualized actuals",
    "Overwrites every category's Annual Budget with its annualized current-year spend, and merges any new transaction categories into the taxonomy.",
    "This is a bulk, all-or-nothing overwrite across every tracking type — it cannot be applied to a single domain, group, or category, and there is no undo beyond restoring a backup. Categories touched are stamped with an 'Annualized actual' note. Groups left in Summary mode still project from their group-level override, so rewriting the per-category values under them will not change the projection until you switch the group back to Detail.",
    "Use it when seeding a brand-new plan from an imported transaction history, or when you want to re-baseline every budget against actual spending after a full year of data. Avoid it once budgets have been hand-tuned — take a backup first.",
    "Changes the year-one spending base for every category that receives a value, so it moves the projected spend base and everything downstream of it.",
  ),
  csv_backup: pageHelp(
    "CSV backup",
    "Exports a CSV backup of holdings, transactions, target allocations, and reference data for recovery or external review.",
    "This is separate from the automatic Local backups (.rpx); CSV backup produces plain files you can open, share, or archive outside the app.",
    "Export a CSV backup before a large bulk import or before making sweeping changes you might want to reference later.",
    "No planning impact — this only creates an export file.",
  ),
  system_config_console: pageHelp(
    "System configuration console",
    "Opens the separate administrator console for pricing providers, build timeout, tax constants, reference files, and diagnostics — settings that apply across every plan, not just the current household.",
    "This console edits application-level configuration (system_config.csv), which is distinct from household plan fields edited on guided pages.",
    "Open this only for diagnostics, reference-table maintenance, or recovery. Use guided pages for ordinary plan edits.",
    "Changes made in the console can affect pricing, tax calculations, IRMAA thresholds, and build behavior for every plan — change one setting at a time and rebuild to confirm the effect.",
  ),
};
 // v11 local-only: no login/logout flow

function dismissMessage() {
  const el = document.getElementById("actionMessage");
  if (el) el.classList.add("hidden");
}


function stripUiLabelPrefix(text) {
  return String(text || "")
    .replace(/^[^/]{1,80}\s*\/\s*/, "")
    .trim();
}
// Subsection keys are storage identifiers (SN_Beneficiary, PC_Homeowner,
// DI_Group_Matthew, Grandchild_A_529, ISO_2023, buffer_1). They used to be
// printed verbatim as section headings; nothing internal belongs on screen.
// Specific families get real copy; anything unrecognized still gets the
// generic underscores-to-words treatment rather than leaking raw.
const GROUP_KEY_LABELS = {
  sn_beneficiary: "Special-Needs Beneficiary",
  sn_trust: "Special-Needs Trust",
  sn_able: "ABLE Account",
  sn_govbenefits: "Government Benefits",
  pc_homeowner: "Homeowners Policy",
  pc_auto: "Auto Policy",
  pc_umbrella: "Umbrella Policy",
  pc_targets: "Coverage Targets",
  di_scenario: "Disability Scenario",
  divorce_settlement: "Settlement",
  demo_divorce_settlement: "Settlement (Example)",
  divorce_alimony: "Alimony",
  divorce_health: "Health Coverage",
  divorce_property: "Property Division",
  family_checking: "Family Checking",
  business_checking: "Business Checking",
};
// A trailing person token (Life_Whole_Patricia) is a first name captured when
// the row was created; show the household's current display name instead.
function personTokenLabel(token) {
  const raw = String(token || "").replace(/_/g, " ").trim();
  for (const n of [1, 2]) {
    const row = householdPersonRow(n, "name");
    const first = String(row ? valOf(row) : "").trim().split(/\s+/)[0];
    if (first && first.toLowerCase() === raw.toLowerCase()) return personDisplayName(n);
    if (new RegExp(`^member[ _]?${n}$`, "i").test(raw)) return personDisplayName(n);
  }
  return raw.split(" ").map(titleWord).join(" ");
}
function humanizeGroupKey(raw) {
  const s = String(raw || "").trim();
  // No underscore means it is already display copy ("Home", "529 Plan 1").
  if (!s || !/_/.test(s)) return s;
  const flat = s.toLowerCase();
  if (GROUP_KEY_LABELS[flat]) return GROUP_KEY_LABELS[flat];
  let m;
  if ((m = /^di_group_(.+)$/i.exec(s))) return `Group Disability — ${personTokenLabel(m[1])}`;
  if ((m = /^life_term_(.+)$/i.exec(s))) return `Term Life — ${personTokenLabel(m[1])}`;
  if ((m = /^life_whole_(.+)$/i.exec(s))) return `Whole Life — ${personTokenLabel(m[1])}`;
  if ((m = /^life_(\d+)$/i.exec(s))) return `Life Policy ${m[1]}`;
  if ((m = /^(iso|rsu|nso)_(\d{4})$/i.exec(s)))
    return `${m[1].toUpperCase()} Grant (${m[2]})`;
  if ((m = /^divorce_qdro_(.+)$/i.exec(s)))
    return `QDRO — ${accountDisplayLabel(m[1].replace(/member(\d)/i, "Member_$1_"))}`;
  if ((m = /^grandchild_([a-z])_529$/i.exec(s)))
    return `Grandchild ${m[1].toUpperCase()} — 529 Plan`;
  if ((m = /^grandchild_([a-z])_goal$/i.exec(s)))
    return `Grandchild ${m[1].toUpperCase()} — Education Goal`;
  if ((m = /^buffer_(\d+)$/i.exec(s))) return `Reserve Rule ${m[1]}`;
  if ((m = /^next_step_(\d+)$/i.exec(s))) return `Housing Step ${m[1]}`;
  if (/^member[ _][12][ _]/i.test(s)) return accountDisplayLabel(s);
  return s
    .replace(/_/g, " ")
    .split(" ")
    .filter(Boolean)
    .map(titleWord)
    .join(" ");
}

function fieldLabelNoteHtml(row) {
  const lbl = norm(row?.label);
  if (
    row &&
    row.section === "Wellness" &&
    row.subsection === "Medicare" &&
    [
      "part_b_base_premium_monthly",
      "part_d_base_premium_monthly",
      "part_g_base_premium_monthly",
    ].includes(lbl)
  )
    return ' <span class="field-label-note"><em>prior to IRMAA</em></span>';
  if (
    row &&
    row.section === "Wellness" &&
    row.subsection === "Pre-65 Bridge" &&
    lbl === "annual_premium_base_year"
  )
    return ' <span class="field-label-note"><em>Enter the total annual cost per person</em></span>';
  if (
    row &&
    row.section === "Income Streams" &&
    lbl === "dividend_rate" &&
    String(valOf(row) || "").trim()
  )
    return ' <span class="field-label-note" title="This stream has its own dividend rate, so editing the plan-wide Default Annuity Dividend Rate will not change it."><em>(override — ignores plan-wide default)</em></span>';
  return "";
}
// Display-only: rewrite "Member 1"/"Member 2"/"Husband"/"Wife" placeholder
// wording anywhere it appears inside a longer string (subsection labels,
// change-log context, help notes) into the household's configured nicknames.
// Also rewrites underscore-joined account-key tokens like "Husband_IRA" /
// "Member_1_IRA" into "Matt's IRA" form (choice-option lists in field notes
// use this compound form, e.g. "Husband_IRA | Husband_401k | Wife_IRA").


// fmtMoney lives in dashboard_shared_helpers.js (A13), loaded first.

// fmtPct lives in dashboard_shared_helpers.js (A13), loaded first.

function finiteOrNull(v) {
  if (v === undefined || v === null || v === "") return null;
  const n = Number(String(v).replace(/[^0-9.-]/g, ""));
  return Number.isFinite(n) ? n : null;
}


function deriveTotalRothConversions(summary) {
  summary = summary || {};
  return firstFinite(
    summary.total_roth_conversions,
    summary.total_roth_conversion,
    summary.roth_conversion_total,
    summary.roth_conversions_total,
    summary.total_conversions,
    summary.total_conversion,
    summary.lifetime_roth_conversions,
    summary.total_roth_conv,
  );
}

function summaryFromApiPayload(payload) {
  if (!payload) return {};
  return payload.kpi || payload.summary || payload || {};
}
function cloneSummary(summary) {
  try {
    return JSON.parse(JSON.stringify(summary || {}));
  } catch (e) {
    return Object.assign({}, summary || {});
  }
}
var chartCache = {};
var chartCacheSeq = 0;
function closeChartModal() {
  var modal = document.getElementById("chartModal");
  if (modal) modal.style.display = "none";
  document.body.classList.remove("chart-modal-open");
}


function artifactHashFromPreflight(preflight, fileName) {
  const artifacts =
    (preflight && preflight.output_fingerprints) ||
    (preflight && preflight.snapshot && preflight.snapshot.artifacts) ||
    [];
  fileName = String(fileName || "").toLowerCase();
  const found = (artifacts || []).find(
    (a) => String(a.file || "").toLowerCase() === fileName,
  );
  return found && found.sha256 ? found.sha256 : "";
}

function rememberBuildCompare(compare, opts) {
  if (!compare) return;
  lastBuildCompare = compare;
  opts = opts || {};
  const after = compare.after || {};
  const atNw = deriveAfterTaxTerminalNw(after);
  const changes = compare.changes || [];
  const adminChanges = compare.admin_changes || [];
  const entry = {
    id: "bh_" + Date.now(),
    timestamp: Date.now(),
    label: opts.label || "Build " + new Date().toLocaleString(),
    isSnapshot: !!opts.isSnapshot,
    kpi: {
      inheritable_nw: Number.isFinite(atNw)
        ? atNw
        : Number.isFinite(after.terminal_nw)
          ? after.terminal_nw
          : null,
      lifetime_tax: Number.isFinite(after.lifetime_tax)
        ? after.lifetime_tax
        : null,
      lcv: Number.isFinite(after.lcv) ? after.lcv : null, eltr: Number.isFinite(after.eltr) ? after.eltr : null, mc_success: Number.isFinite(after.mc_success) ? after.mc_success : null,
    },
    before: compare.before || {},
    after: compare.after || {},
    changes,
    admin_changes: adminChanges,
    qc: compare.qc || "",
    elapsed: compare.elapsed || "",
    provenance: compare.provenance || buildHistoryProvenance(),
  };
  loadBuildHistory();
  // A rebuild with no captured user/admin input changes since the last entry
  // is a no-op from the plan's perspective — skip cluttering history with a
  // duplicate row, unless this is the very first entry (nothing to compare
  // against yet) or an explicit user-taken snapshot.
  if (
    !opts.isSnapshot &&
    !changes.length &&
    !adminChanges.length &&
    buildHistory.length > 0
  )
    return;
  pushBuildHistoryEntry(entry);
}
async function takeBuildSnapshot() {
  if (!planLoaded) {
    showMessage("Open the local plan first.", "error");
    return;
  }
  const label = "Snapshot " + new Date().toLocaleString();
  const kpis = await fetchCurrentSummaryKpi();
  const atNw = deriveAfterTaxTerminalNw(kpis);
  const entry = {
    id: "bh_" + Date.now(),
    timestamp: Date.now(),
    label,
    isSnapshot: true,
    kpi: {
      inheritable_nw: Number.isFinite(atNw)
        ? atNw
        : Number.isFinite(kpis.terminal_nw)
          ? kpis.terminal_nw
          : null,
      lifetime_tax: Number.isFinite(kpis.lifetime_tax)
        ? kpis.lifetime_tax
        : null,
      lcv: Number.isFinite(kpis.lcv) ? kpis.lcv : null, eltr: Number.isFinite(kpis.eltr) ? kpis.eltr : null, mc_success: Number.isFinite(kpis.mc_success) ? kpis.mc_success : null,
    },
    before: cloneSummary(kpis),
    after: cloneSummary(kpis),
    changes: capturedSessionChanges(),
    admin_changes: [],
    qc: "",
    elapsed: "",
    provenance: buildHistoryProvenance(),
  };
  pushBuildHistoryEntry(entry);
  renderMain();
  showMessage("Snapshot saved.");
}
function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
function rowConfigValue(label, fallback = "") {
  const n = norm(label);
  const r = rows.find((x) => norm(x.label) === n);
  return r ? valOf(r) : fallback;
}
function changeKey(row) {
  return [row.section || "", row.subsection || "", row.label || ""].join(
    "\x1f",
  );
}
function changeImpactScope(row) {
  if (rowIsStressSellHomeInput(row))
    return "Scenario Analysis sheet only — not a base-plan Build Impact KPI";
  if (
    rowIsBaseHomeSaleInput(row) ||
    (row?.section === "Cashflow" && norm(row?.subsection) === "mortgage")
  )
    return "Base plan — should affect Build Impact when materially changed";
  return "";
}
const BUILD_IMPACT_SOURCE_STEP_IDS = [
  "household_people",
  "income_work",
  "income_retirement",
  "spending_core",
  "retirement_wellness",
  "spending_mortgage_events",
  "spending_travel",
  "spending_travel_extras",
  "ytd_transactions",
  "holdings",
  "assets_home_cash",
  "annuity_death_benefits",
  "assets_special",
  "estate",
  "roth_conversion",
  "allocation_assets",
  "allocation_policy",
  "withdrawal_strategy",
  "state_residency",
  "heloc_strategy",
  "entity_charitable",
  "monte_carlo_options",
  "scenarios",
  "survivor_stress",
  "ltc_stress",
  "divorce_options",
  "economic_tax_assumptions",
  "optional_functions",
  "system_configuration",
];


function stepIdForRow(row) {
  return sourceStepForRow(row);
}
function noteSessionFieldChange(
  row,
  before,
  after,
  beforeStorage,
  afterStorage,
) {
  if (!row) return;
  const key = changeKey(row);
  const scope = changeImpactScope(row);
  const sourceStep = sourceStepForRow(row);
  const sourceTitle = stepTitleById(sourceStep);
  if (!sessionChanges.has(key)) {
    sessionChanges.set(key, {
      row_index: row.row_index,
      section: row.section || "",
      subsection: row.subsection || "",
      rawLabel: row.label || "",
      label: humanLabel(row.label, row),
      group: friendlyGroup(row),
      scope,
      sourceStep,
      sourceTitle,
      before: String(before ?? ""),
      after: String(after ?? ""),
      beforeStorage: String(beforeStorage ?? before ?? ""),
      afterStorage: String(afterStorage ?? after ?? ""),
    });
  } else {
    const rec = sessionChanges.get(key);
    rec.after = String(after ?? "");
    rec.afterStorage = String(afterStorage ?? after ?? "");
    rec.label = humanLabel(row.label, row);
    rec.group = friendlyGroup(row);
    rec.scope = scope;
    rec.sourceStep = sourceStep;
    rec.sourceTitle = sourceTitle;
    rec.row_index = row.row_index;
    rec.section = row.section || "";
    rec.subsection = row.subsection || "";
    rec.rawLabel = row.label || "";
  }
  const rec = sessionChanges.get(key);
  if (String(rec.beforeStorage) === String(rec.afterStorage))
    sessionChanges.delete(key);
}
function noteSpecialSessionChange(label) {
  sessionSpecialChanges.add(label);
}

// #274: "User input changes" and "Admin/config changes" used to be two
// separately-headed sections, which implied admin/config changes only ever
// happen from the Settings/admin pages -- not true elsewhere in the app.
// unifiedBuildChangeSummaryHtml() (dashboard_decomp_misc.js) merges both
// change lists into one "Source" column instead, and adminBuildChangeSummaryHtml
// (the old admin-only renderer) was removed as dead code once that was its
// only caller.



function parseDollarLike(v) {
  const n = Number(
    String(v ?? "")
      .replace(/[$,%]/g, "")
      .replace(/,/g, ""),
  );
  return Number.isFinite(n) ? n : 0;
}

function leverPctPoints(v) {
  return Math.max(-30, Math.min(30, Number(v) || 0));
}


function renderStateResidency() {
  const rs = rowsForStep("state_residency");
  const stateComp = rs.filter(
    (r) => String(r.section || "").trim() === "State Comparison",
  );
  let html = renderResidencySchedule();
  html += `<div class="section-note">Baseline state is set on <a href="#" onclick="setStep('household_people');return false">Household People</a>. Enter the target state and cost differences below — the workbook State Residency sheet shows annual and lifetime impact.</div>`;
  if (!stateComp.length)
    return (
      html +
      `<div class="field-list"><p>No state comparison rows found. Reload the current plan to backfill them.</p></div>`
    );
  const hwRows = stateComp.filter(
    (r) => norm(r.subsection || "") === "homeowners_insurance",
  );
  const autoRows = stateComp.filter(
    (r) => norm(r.subsection || "") === "auto_insurance",
  );
  const otherRows = stateComp.filter(
    (r) => !hwRows.includes(r) && !autoRows.includes(r),
  );
  html += `<div class="field-list">`;
  if (otherRows.length) html += otherRows.map(fieldHtml).join("");
  if (hwRows.length)
    html +=
      `<div class="subsection-label">Homeowners insurance</div>` +
      hwRows.map(fieldHtml).join("");
  if (autoRows.length)
    html +=
      `<div class="subsection-label">Auto insurance</div>` +
      autoRows.map(fieldHtml).join("");
  html += `</div>`;
  return html;
}
function renderEntityCharitable() {
  let html = `<div class="section-note">Qualified charitable distributions (age 70½+) satisfy required distributions without the amount appearing as taxable income. S-Corp election is a self-employment decision, entered on <a href="#" onclick="setStep('income_work');return false">Work Income</a>.</div>`;
  return html + renderFields("entity_charitable");
}

function chatMessageHtml(m) {
  const role = m.role === "user" ? "user" : "assistant";
  const label = role === "user" ? "You" : m.pending ? "Plan Chat" : "Plan Chat";
  const source = m.source
    ? `<div class="chat-source">Source: ${esc(m.source)}</div>`
    : "";
  return `<div class="chat-msg ${role}"><div class="chat-meta">${esc(label)}</div>${esc(m.content || "")}${source}</div>`;
}



function planningCaseNowIso() {
  return window.RetirementPlanningWorkbench.nowIso();
}
function normalizePlanningCaseSource(v) {
  return window.RetirementPlanningWorkbench.normalizeSource(v);
}
function normalizePlanningCaseRunType(v) {
  return window.RetirementPlanningWorkbench.normalizeRunType(v);
}
function planningCaseReadAll() {
  return window.RetirementPlanningWorkbench.readAll();
}
function planningCaseSaveAll(cases) {
  return window.RetirementPlanningWorkbench.saveAll(cases);
}
function planningCaseActiveId() {
  return window.RetirementPlanningWorkbench.activeId();
}
function setPlanningCaseActive(id) {
  return window.RetirementPlanningWorkbench.setActive(
    id,
    planningWorkbenchContext(),
  );
}
function planningCaseId() {
  return window.RetirementPlanningWorkbench.caseId();
}
function planningCaseMetricSummary() {
  return window.RetirementPlanningWorkbench.metricSummary(
    planningWorkbenchContext(),
  );
}
function planningCaseBaseSnapshotId() {
  return window.RetirementPlanningWorkbench.baseSnapshotId(
    planningWorkbenchContext(),
  );
}
function planningCaseOverrideFromRow(row, source, reason) {
  return window.RetirementPlanningWorkbench.overrideFromRow(
    planningWorkbenchContext(),
    row,
    source,
    reason,
  );
}
function currentManualOverrideItems() {
  return window.RetirementPlanningWorkbench.currentManualOverrideItems(
    planningWorkbenchContext(),
  );
}
function currentScenarioOverrideItems() {
  return window.RetirementPlanningWorkbench.currentScenarioOverrideItems(
    planningWorkbenchContext(),
  );
}
function strategyLeverOverrideItems() {
  return window.RetirementPlanningWorkbench.strategyLeverOverrideItems(
    planningWorkbenchContext(),
  );
}
function stressOverrideItems() {
  return window.RetirementPlanningWorkbench.stressOverrideItems(
    planningWorkbenchContext(),
  );
}
function planningCaseOverridesForSource(source) {
  return window.RetirementPlanningWorkbench.overridesForSource(
    planningWorkbenchContext(),
    source,
  );
}
function planningCaseCreate(source) {
  return window.RetirementPlanningWorkbench.createCase(
    planningWorkbenchContext(),
    source,
  );
}
function planningCaseDelete(id) {
  return window.RetirementPlanningWorkbench.deleteCase(
    planningWorkbenchContext(),
    id,
  );
}
function planningCaseArchive(id) {
  return window.RetirementPlanningWorkbench.archiveCase(
    planningWorkbenchContext(),
    id,
  );
}
function planningCaseAdopt(id) {
  return window.RetirementPlanningWorkbench.adoptCase(
    planningWorkbenchContext(),
    id,
  );
}
async function promotePlanningCase(id) {
  const c = planningCaseReadAll().find((x) => x.case_id === id);
  if (!c) {
    showMessage("Planning case not found.", "error");
    return;
  }
  const promotable = (c.overrides || []).filter((x) => x.row_index != null);
  if (!promotable.length) {
    showMessage(
      'This case has no promotable overrides — only manually captured field edits can be promoted directly. Use "Adopt via source pages" for other cases.',
      "warn",
    );
    return;
  }
  const lines = promotable
    .map(
      (x) =>
        "• " +
        (x.label || x.field || "Field") +
        ": " +
        String(x.before != null ? x.before : "(blank)") +
        " → " +
        String(x.after != null ? x.after : "(blank)"),
    )
    .join("\n");
  const promoteHtml =
    "<p>Apply <b>" +
    promotable.length +
    " change" +
    (promotable.length === 1 ? "" : "s") +
    "</b> from <b>" +
    esc(c.name) +
    '</b> to the active plan?</p><ul class="inapp-modal-list">' +
    promotable
      .map(
        (x) =>
          "<li>" +
          esc(
            (x.label || x.field || "Field") +
              ": " +
              (x.before != null ? x.before : "(blank)") +
              " → " +
              (x.after != null ? x.after : "(blank)"),
          ) +
          "</li>",
      )
      .join("") +
    "</ul><p>Save Changes, then rebuild to see the effect.</p>";
  if (
    !(await showInAppConfirm(promoteHtml, {
      title: "Promote to Plan",
      confirmLabel: "Promote",
      variant: "warn",
      bodyIsHtml: true,
    }))
  )
    return;
  let applied = 0;
  promotable.forEach(function (x) {
    const val = x.afterRaw != null ? x.afterRaw : x.after;
    if (val == null) return;
    editValue(x.row_index, val, null);
    applied++;
  });
  if (applied) {
    showMessage(
      '"' +
        c.name +
        '" promoted — ' +
        applied +
        " change" +
        (applied === 1 ? "" : "s") +
        " staged. Save Changes, then rebuild.",
      "success",
    );
    renderMain();
    renderSteps();
  } else showMessage("No changes could be applied from this case.", "warn");
}
function planningCaseSourceButtons() {
  return window.RetirementPlanningWorkbench.sourceButtons(
    planningWorkbenchContext(),
  );
}
function planningCaseOverrideTable(items, empty) {
  return window.RetirementPlanningWorkbench.overrideTable(
    planningWorkbenchContext(),
    items,
    empty,
  );
}
function planningCaseMatrixHtml(cases) {
  return window.RetirementPlanningWorkbench.matrixHtml(
    planningWorkbenchContext(),
    cases,
  );
}
function planningCaseCardsHtml(cases, active) {
  return window.RetirementPlanningWorkbench.cardsHtml(
    planningWorkbenchContext(),
    cases,
    active,
  );
}
function planningWorkbenchStressSelectorHtml(cases) {
  return window.RetirementPlanningWorkbench.stressSelectorHtml(
    planningWorkbenchContext(),
    cases,
  );
}
function renderPlanningWorkbench() {
  return window.RetirementPlanningWorkbench.renderWorkbench(
    planningWorkbenchContext(),
  );
}
function planningWorkbenchBuildImpactHtml() {
  return window.RetirementPlanningWorkbench.renderBuildImpactContext(
    planningWorkbenchContext(),
  );
}

async function revertLastBuildChanges() {
  if (
    !(await showInAppConfirm(
      "Revert all field changes since the last build? This cannot be undone.",
      { title: "Revert Changes", confirmLabel: "Revert", variant: "warn" },
    ))
  )
    return;
  try {
    const sourceChanges =
      lastBuildCompare && Array.isArray(lastBuildCompare.changes)
        ? lastBuildCompare.changes
        : [...sessionChanges.values()];
    const changes = sourceChanges.filter(
      (c) => !c.special && c.row_index !== undefined,
    );
    if (!changes.length) {
      showMessage("No captured input fields are available to revert.", "error");
      return;
    }
    const updates = changes.map((c) => ({
      row_index: c.row_index,
      value: String(c.beforeStorage ?? c.before ?? ""),
    }));
    await api("/api/config/rows", {
      method: "POST",
      body: JSON.stringify({ updates, sync: false }),
    });
    await syncBackends();
    dirty.clear();
    sessionChanges.clear();
    sessionSpecialChanges.clear();
    lastBuildCompare = null;
    lastBuildOk = false;
    await loadAll({ source: planSource, preferLocal: false, silent: true });
    activeStep = "review";
    renderMain();
    showMessage("Changes reverted and saved to the app working copy.");
  } catch (e) {
    showMessage("Error reverting changes: " + e.message, "error");
  }
}


function sectionFlagEnabled(sectionName, subsectionName, labelName) {
  const row = rows.find(
    (r) =>
      isEditable(r) &&
      r.section === sectionName &&
      norm(r.subsection || "") === norm(subsectionName) &&
      norm(r.label) === norm(labelName),
  );
  if (!row) return false;
  const v = String(valOf(row) || "")
    .trim()
    .toUpperCase();
  return ["TRUE", "YES", "1", "ON", "ENABLED"].includes(v);
}


function rowIsRetirementWellness(r) {
  const lbl = norm(r.label);
  const sub = norm(r.subsection || "");
  return (
    r.section === "Wellness" &&
    ((sub === "pre_65_bridge" && lbl === "annual_premium_base_year") ||
      (sub === "medicare" &&
        [
          "part_b_base_premium_monthly",
          "part_d_base_premium_monthly",
          "part_g_base_premium_monthly",
        ].includes(lbl)) ||
      ([
        "out_of_pocket",
        "out_of_pocket_max",
        "out_of_pocket_wellness",
      ].includes(sub) &&
        (lbl === "annual_oop_estimate_today" ||
          lbl === "oop_utilization_pct" ||
          [
            "medical_annual",
            "dental_annual",
            "vision_annual",
            "pharmacy_annual",
          ].includes(lbl))))
  );
}


function baseHomeSaleYearRow() {
  return (
    rows.find(
      (x) =>
        isEditable(x) &&
        x.section === "Other Assets" &&
        norm(x.subsection) === "home" &&
        norm(x.label) === "home_sale_year",
    ) || null
  );
}
function stressHomeSaleYearRow() {
  return (
    rows.find(
      (x) =>
        isEditable(x) &&
        x.section === "Scenarios" &&
        norm(x.subsection) === "sell_home" &&
        (norm(x.label) === "home_sale_year" ||
          norm(x.label) === "planned_home_sale_year"),
    ) || null
  );
}
function assetActionForSubsection(subsection) {
  const a = selectionActionRows().find(
    (x) => norm(x.subsection) === norm(subsection),
  );
  return rowActionValue(a);
}
// §7.4: {section: {key, label}} is now server-declared (module_catalog's
// csv_sections, via moduleGates.section_gates) rather than hand-listed here.

function optionalModuleState(row) {
  const sec = String(row.section || "");
  if (sec === "Hybrid LTC" && !ltcLifePolicyModuleEnabled())
    return {
      active: false,
      reason:
        "LTC/Life Policy is turned off (Hybrid LTC → Settings → Enabled).",
      activation:
        "Turn on Enabled under Hybrid LTC → Settings on Other Assets and Liabilities.",
      effect:
        "The related workbook section will begin using these values in cash-flow, insurance, estate, legacy, or planning-module calculations.",
      listAlways: false,
      optionalModuleOff: true,
    };
  const gate = rowModuleGate(sec);
  if (gate) {
    const { key: flag, label } = gate;
    if (!optionalFunctionEnabled(flag))
      return {
        active: false,
        reason: `${label} is turned off.`,
        activation: `Turn on ${label} in Optional workbook modules.`,
        effect:
          "The related workbook section will begin using these values in cash-flow, insurance, estate, legacy, or planning-module calculations.",
        listAlways: false,
        optionalModuleOff: true,
      };
  }
  if (rowIsDivorceScenario(row) && !optionalFunctionEnabled("divorce_qdro"))
    return {
      active: false,
      reason: "Divorce/QDRO optional workbook module is turned off.",
      activation: "Turn on Divorce/QDRO in Optional workbook modules.",
      effect:
        "Divorce assumptions can change filing status, account ownership, alimony cash flow, Wellness costs, lifetime taxes, terminal net worth, and survivor/legacy reporting.",
      listAlways: false,
      optionalModuleOff: true,
    };
  return null;
}


const RECOMMENDATION_ENGINE_VERSION = "page_recommendations_v1";
const RECOMMENDATION_STEP_IDS = new Set([
  "roth_conversion",
  "allocation_assets",
  "allocation_policy",
  "spending_core",
  "income_retirement",
]);

// Expand every collapsed ancestor of `el`, then scroll/focus/select it.
//
// Content inside a closed <details> is not focusable and has no layout, so
// scrollIntoView/focus against it silently do nothing -- the user clicks a
// "jump to source field" link and the page appears not to respond. That is
// what happened for every Travel / Large Discretionary / DAF field, because
// renderLifestyleSpending() wraps each of those groups in a <details> with no
// `open` attribute, and STEP_REDIRECTS sends the old spending_travel /
// spending_travel_extras step ids there.
//
// This is a bug CLASS, not one call site: anything that scrolls to a row can
// hit it whenever the target is nested in a collapsed container. Route every
// such call through here rather than fixing the one path that was reported.



function pageSaveMode(stepId) {
  const autosave =
    (window.RetirementNavigation &&
      window.RetirementNavigation.AUTOSAVE_STEPS) ||
    [];
  if (stepId === "review")
    return {
      kind: "build-gated",
      label: "Build saves first",
      detail:
        "Build Reports and Download Workbook save the working copy before preflight and report generation.",
    };
  if (["build_impact", "detailed_results", "plan_data_report"].includes(stepId))
    return {
      kind: "read-only",
      label: "Read-only snapshot",
      detail:
        "This page reviews saved inputs or generated outputs. Edit source pages, save, then rebuild.",
    };
  if (
    [
      "planning_workbench",
      "planning_levers",
      "scenarios",
      "monte_carlo_options",
      "survivor_stress",
      "ltc_stress",
      "divorce_options",
    ].includes(stepId)
  )
    return {
      kind: "scenario",
      label: "Scenario review",
      detail:
        "Comparison cases and test amounts are previews until you edit a source page, save, and rebuild.",
    };
  if (autosave.includes(stepId))
    return {
      kind: "autosave",
      label: "Auto-save on navigation",
      detail:
        "This workflow page saves its pending table edits when you navigate away.",
    };
  if (stepId === "system_configuration")
    return {
      kind: "explicit",
      label: "Explicit save",
      detail:
        "Normal settings require Save Changes or a specific action button. Advanced tools confirm their own writes.",
    };
  return {
    kind: "explicit",
    label: "Save Changes",
    detail:
      "Edits are staged locally until you click Save Changes or start a build/download.",
  };
}
function pageSaveModeHtml(stepId) {
  const m = pageSaveMode(stepId);
  return `<div class="save-mode-chip ${esc(m.kind)}" title="${esc(m.detail)}"><b>${esc(m.label)}</b><span>${esc(m.detail)}</span></div>`;
}
function detailedProgressHtml(compact = false) {
  const p = detailedResultsProgress || {};
  const pct = Math.max(0, Math.min(100, Number(p.pct) || 0));
  const phase = p.phase || "Loading results";
  const detail = p.detail || "Preparing the results explorer.";
  return `<div class="detail-progress ${compact ? "compact" : ""}"><div class="detail-progress-top"><b>${esc(phase)}</b><span>Est. ${Math.round(pct)}%</span></div><div class="detail-progress-bar"><span style="width:${pct}%"></span></div><div class="detail-progress-detail">${esc(detail)}</div></div>`;
}


function setDetailedResultsNavOpen(open) {
  return window.RetirementReportsUI.setDetailedResultsNavOpen(
    reportsUiContext(),
    open,
  );
}
function renderDetailedResultsNav() {
  return window.RetirementReportsUI.renderDetailedResultsNav(
    reportsUiContext(),
  );
}


function openNavDrawer() {
  document.body.classList.add("nav-open");
  const btn = document.getElementById("navToggleBtn");
  if (btn) btn.setAttribute("aria-expanded", "true");
}
function closeNavDrawer() {
  document.body.classList.remove("nav-open");
  const btn = document.getElementById("navToggleBtn");
  if (btn) btn.setAttribute("aria-expanded", "false");
}
function toggleNavDrawer() {
  if (document.body.classList.contains("nav-open")) closeNavDrawer();
  else openNavDrawer();
}
function toggleHelpSheet() {
  // Mobile (<=768px) and desktop (>=1181px, U3) toggle different classes with
  // opposite defaults (help-open opts into showing; help-collapsed opts out).
  // Each must be read-and-flipped independently — deriving one from the
  // other's toggle() result breaks on the very first click, since a fresh
  // page has neither class present regardless of which breakpoint that
  // absence means "closed" (mobile) vs. "expanded" (desktop) for.
  const btn = document.querySelector("#helpPane .help-toggle");
  if (window.matchMedia && window.matchMedia("(min-width: 1181px)").matches) {
    const collapsed = document.body.classList.toggle("help-collapsed");
    try {
      if (window.localStorage)
        window.localStorage.setItem(
          "retirementHelpCollapsed",
          collapsed ? "1" : "0",
        );
    } catch (_e) {}
    if (btn) btn.setAttribute("aria-expanded", collapsed ? "false" : "true");
    return;
  }
  const open = document.body.classList.toggle("help-open");
  if (btn) btn.setAttribute("aria-expanded", open ? "true" : "false");
}
try {
  if (
    window.localStorage &&
    window.localStorage.getItem("retirementHelpCollapsed") === "1"
  )
    document.body.classList.add("help-collapsed");
} catch (_e) {}
function showHelpAutoCollapseNoticeOnce() {
  try {
    if (
      window.localStorage &&
      window.localStorage.getItem("retirementHelpAutoCollapseNoticeShown") ===
        "1"
    )
      return;
    if (window.localStorage)
      window.localStorage.setItem("retirementHelpAutoCollapseNoticeShown", "1");
  } catch (_e) {}
  showMessage(
    "Context Help moved into a toggle to fit this screen width. Click the Context Help heading to bring it back.",
    "info",
    { persistent: true },
  );
}
// Tracks whether autoCollapseHelpForNarrowLaptop currently holds the help
// pane collapsed on its own authority (as opposed to a user's manual click,
// which is tracked separately via the retirementHelpCollapsed localStorage
// key). Kept as a private flag rather than read back via
// document.body.classList.contains(), which some of this codebase's minimal
// Node smoke-test DOM mocks don't implement.
let _autoHelpCollapsedActive = false;
function autoCollapseHelpForNarrowLaptop() {
  // U1: 1280x800/1366x768/1440x900 render the 3-column grid but can't
  // satisfy its width floor (see dashboard.css main{} + the 1180px
  // breakpoint), causing horizontal overflow instead of the clean
  // single-column fallback. Below 1181px that fallback already applies, so
  // this only needs to act in the narrow desktop gap above it.
  let manual = null;
  try {
    manual = window.localStorage
      ? window.localStorage.getItem("retirementHelpCollapsed")
      : null;
  } catch (_e) {}
  if (manual !== null) return; // the user already made an explicit choice
  const w = window.innerWidth;
  const btn = document.querySelector("#helpPane .help-toggle");
  if (w > 1180 && w < 1500) {
    if (!_autoHelpCollapsedActive) {
      document.body.classList.add("help-collapsed");
      _autoHelpCollapsedActive = true;
      if (btn) btn.setAttribute("aria-expanded", "false");
      showHelpAutoCollapseNoticeOnce();
    }
  } else if (w >= 1500 && _autoHelpCollapsedActive) {
    document.body.classList.remove("help-collapsed");
    _autoHelpCollapsedActive = false;
    if (btn) btn.setAttribute("aria-expanded", "true");
  }
}
window.addEventListener("resize", autoCollapseHelpForNarrowLaptop);
autoCollapseHelpForNarrowLaptop();
(function wireMobileShellDismiss() {
  const stepsBox = document.getElementById("steps");
  if (stepsBox)
    stepsBox.addEventListener("click", function (e) {
      if (e.target && e.target.closest && e.target.closest("[data-step-id]"))
        closeNavDrawer();
    });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closeNavDrawer();
  });
})();
function renderMeta() {
  document.getElementById("planSource").textContent = planSource;
}


// decimalTrim/numberFromDisplay/formatNumberValue/currencyDisplay/percentDisplay
// live in dashboard_shared_helpers.js (A13), loaded first.
function decimalsFromText(value) {
  const m = String(value ?? "").match(/\.(\d+)/);
  return m ? Math.min(6, m[1].length) : 0;
}
function numberDisplayDecimals(row, value) {
  const l = norm(row?.label),
    units = String(row?.units || "");
  const schema = row?.schema || {};
  if (l === "fra_age") {
    const n = numberFromDisplay(value);
    return n !== null && Number.isInteger(n) ? 0 : decimalsFromText(value);
  }
  if (
    l.includes("weight") ||
    l.includes("factor") ||
    l.includes("correlation") ||
    l.includes("sigma") ||
    l.includes("reserve_factor") ||
    units.toLowerCase() === "number"
  )
    return Math.max(
      2,
      decimalsFromText(value),
      decimalsFromText(schema.default),
    );
  if (
    l.includes("year") ||
    String(schema.type || "").toLowerCase() === "year" ||
    String(schema.type || "").toLowerCase() === "integer"
  )
    return 0;
  return Math.max(0, decimalsFromText(value), decimalsFromText(schema.default));
}

function percentRaw(value) {
  const n = numberFromDisplay(value);
  return n === null ? String(value ?? "").trim() : decimalTrim(String(n));
}
function moneyNegativeClass(value) {
  const n = numberFromDisplay(value);
  return n !== null && n < 0 ? " negative-money" : "";
}
function percentDisplayDecimals(row, value) {
  const schema = row?.schema || {};
  return Math.max(
    decimalsFromText(value),
    decimalsFromText(row?.value),
    decimalsFromText(schema.default),
    0,
  );
}

function filterChoiceOptionsForRow(r, opts) {
  const label = String(r?.label || "").trim();
  if (
    activeStep === "annuity_death_benefits" &&
    r?.section === "Insurance In Force" &&
    norm(label) === "policy_type"
  ) {
    return (opts || []).filter((x) => norm(choiceValue(x)) === "life");
  }
  if (
    activeStep === "estate" &&
    r?.section === "Insurance In Force" &&
    norm(label) === "policy_type"
  ) {
    return (opts || []).filter(
      (x) =>
        !["life", "auto", "home", "property_and_casualty"].includes(
          norm(choiceValue(x)),
        ),
    );
  }
  return opts || [];
}
function choiceOptions(r) {
  const label = String(r?.label || "").trim();
  const type = String(r?.schema?.type || "").toLowerCase();
  const units = String(r?.units || "");
  const fixed = {
    filing_status: ["MFJ", "Single", "HOH", "MFS"], survivor_filing_status: ["Single", "HOH", "MFS"],
    state: _stateNameChoiceOptions(), residence_state: _stateNameChoiceOptions(), target_state: _stateAbbrChoiceOptions(),
    roth_conversion_policy: [
      "optimize_terminal_tax",
      "fill_to_bracket",
      "fill_to_irmaa",
      "fixed_dollar",
      "none",
    ],
    core_spending_growth_mode: [
      { value: "cpi", label: "Use CPI / General Inflation" },
      { value: "manual_override", label: "Manual spending increase override" },
    ],
    roth_bracket_strategy: [
      "NONE",
      "FILL_CURRENT_BRACKET",
      "FILL_TARGET_BRACKET",
      "PARTIAL_TARGET_BRACKET",
      "IRMAA_GUARDED",
      "SURVIVOR_TAX_AWARE",
      "RMD_REDUCTION",
      "LEGACY_TARGETED",
      "OPTIMIZER_CHOOSES",
      "FIXED_DOLLAR",
    ],
    roth_objective_mode: [
      "BALANCED_RETIREMENT",
      "MINIMIZE_LIFETIME_TAX",
      "MAXIMIZE_TERMINAL_NET_WORTH",
      "LEGACY_OPTIMIZED",
      "ESTATE_TAX_AWARE",
      "CUSTOM_WEIGHTED",
    ],
    estate_tax_objective_mode: ["OFF", "MONITOR_ONLY", "BALANCED", "STRONG"],
    irmaa_guardrail_mode: [
      "IGNORE",
      "WARN_ONLY",
      "AVOID_NEXT_TIER",
      "AVOID_TIER_2_OR_ABOVE",
      "CUSTOM_MAGI_CAP",
    ],
    legacy_objective_mode: ["OFF", "LOW", "BALANCED", "STRONG"],
    mc_engine_mode: [
      {
        value: "quick_vectorized",
        label: "Simple — Quick Vectorized (faster, approximate)",
      },
      {
        value: "advanced_exact_scalar",
        label: "Complex — Advanced Exact Scalar (slower, advisor-ready)",
      },
    ],
    city_type: ["urban", "suburban", "rural"],
    type: ["purchase", "rent"],
    allocation_selection_mode: [
      { value: "user_target", label: "Use user-specified allocation" },
      { value: "optimizer_recommendation", label: "Use allocation optimizer recommendation" },
      { value: "max_sharpe", label: "Best risk-adjusted mix within your risk limits (max-Sharpe, risk-budgeted)" },
      { value: "tangency", label: "Best risk-adjusted mix with no risk limits applied (max-Sharpe, pure tangency)" },
      { value: "real_loss_aware", label: "Match each dollar to when you’ll spend it, minimizing the chance of a loss after inflation" },
    ],
    capital_market_assumption_horizon_source: [
      { value: "manual", label: "Manual (use the horizon selected above)" },
      { value: "auto_from_withdrawals", label: "Auto-derive from projected withdrawals" },
    ],
    selection_action: ["include", "exclude", "consider_alternate_first"],
  };
  if (Array.isArray(r?.choice_options) && r.choice_options.length)
    return filterChoiceOptionsForRow(r, r.choice_options);
  if (fixed[label]) return filterChoiceOptionsForRow(r, fixed[label]);
  if (type !== "choice" && norm(units) !== "choice") return [];
  const text = [r?.schema?.description || "", r?.notes || "", units].join(" ");
  let candidate = text.split(";")[0];
  if (!candidate.includes("|")) candidate = text;
  let opts = candidate
    .split("|")
    .map((x) => x.trim())
    .filter((x) => x && x.length < 120 && !/[.]/.test(x))
    .filter(
      (x, i, a) =>
        a.findIndex(
          (y) =>
            norm(typeof y === "object" ? y.value : y) ===
            norm(typeof x === "object" ? x.value : x),
        ) === i,
    );
  return filterChoiceOptionsForRow(r, opts);
}

function choiceLabel(o) {
  return typeof o === "object" ? String(o.label ?? o.value ?? "") : String(o);
}

// Display-only: translate a stored field VALUE that is entirely a person
// placeholder token — "Member 1", "Husband", "Wife_Trust", "Member_2_Trust"
// — into nickname form ("Matt" / "Pat's Trust"). Anchored to the whole
// (trimmed) value so it never touches unrelated free text; the raw value is
// still what gets edited/saved (see beginEdit/finishEdit).
const PERSON_VALUE_TOKEN_RE = /^(member[ _]([12])|husband|wife)([ _](.+))?$/i;
function translatePersonValueLabel(value) {
  const s = String(value ?? "").trim();
  if (!s) return s;
  const m = PERSON_VALUE_TOKEN_RE.exec(s);
  if (!m) return translatePersonPlaceholders(s);
  const n = m[2] ? Number(m[2]) : /^husband/i.test(m[1]) ? 1 : 2;
  const rest = m[4] ? m[4].replace(/_/g, " ").trim() : "";
  return rest ? personDisplayName(n) + "'s " + rest : personDisplayName(n);
}

function saveValueForRow(row, value) {
  if (row && isDateField(row)) return toIsoDateValue(value);
  const kind = valueKind(row);
  if (kind === "currency") return currencyRaw(value);
  if (kind === "percent")
    return percentDisplay(value, percentDisplayDecimals(row, value));
  if (kind === "number")
    return formatNumberValue(
      value,
      numberDisplayDecimals(row, value),
      numberDisplayDecimals(row, value),
    );
  return String(value ?? "");
}


const FIELD_TOOLTIPS = {
  holding_period_allocation_enabled:
    "Nudges the recommended mix toward cash for money you'll need soon, and toward stocks for money you won't touch for years. Click for the full explanation.",
  portability_enabled:
    "Lets a surviving spouse use a deceased spouse's unused federal exemption. Federal only — most states don't honor it. Click for the full explanation.",
  portfolio_nominal_return:
    "Historical average: 6–7%. Conservative planners use 5–6%.",
  nominal_return: "Historical average: 6–7%. Conservative planners use 5–6%.",
  configured_portfolio_nominal_return:
    "Historical average: 6–7%. Conservative planners use 5–6%.",
  general_inflation:
    "Recent 10-year average: ~3%. The default 2.5% is a long-term assumption.",
  inflation_rate:
    "Recent 10-year average: ~3%. The default 2.5% is a long-term assumption.",
  inflation:
    "Recent 10-year average: ~3%. The default 2.5% is a long-term assumption.",
  mortality_age: "The plan runs until this age. Longer is more conservative.",
  life_expectancy: "The plan runs until this age. Longer is more conservative.",
  plan_end_age: "The plan runs until this age. Longer is more conservative.",
  member_1_life_expectancy:
    "The plan runs until this age for " +
    ((lastBuildSummary &&
      (lastBuildSummary.h_nick || lastBuildSummary.h_name)) ||
      "Member 1") +
    ". Longer is more conservative.",
  member_2_life_expectancy:
    "The plan runs until this age for " +
    ((lastBuildSummary &&
      (lastBuildSummary.w_nick || lastBuildSummary.w_name)) ||
      "Member 2") +
    ". Longer is more conservative.",
  monthly_pia_at_fra_today_dollars:
    "Enter the monthly benefit shown on your SSA statement for claiming at Full Retirement Age.",
  appreciation_rate:
    "For home value: national average 3–4%. Local markets vary.",
  home_appreciation_rate: "National average: 3–4%. Local markets vary.",
  state_income_tax_rate:
    "Enter your effective rate, not the top marginal bracket rate.",
  state_tax_rate:
    "Enter your effective rate, not the top marginal bracket rate.",
  effective_state_tax_rate:
    "Enter your effective rate, not the top marginal bracket rate.",
  social_security_cola:
    "The annual raise Social Security applies to keep pace with inflation. Click for the full explanation.",
  basis_step_up_at_death:
    "Under current law, an heir's taxable-account cost basis resets to date-of-death value, erasing lifetime gains. Click for the full explanation.",
  tax_loss_harvesting:
    "Deliberately selling losers to offset gains and reduce lifetime taxes. Click for the full explanation.",
  heloc_enabled:
    "Uses a home-equity credit line to fund large one-time expenses instead of selling investments. Click for the full explanation.",
  holding_period_floor_strength:
    "The strength dial for Holding Period Allocation — 100% = full effect, 0% = off. Click for the full explanation.",
  success_liquid_floor:
    "The minimum liquid cash a Monte Carlo year must keep to still count as a success. Click for the full explanation.",
  stochastic_irmaa:
    "Adds realistic year-to-year noise to IRMAA thresholds in Monte Carlo runs. Click for the full explanation.",
  return_inflation_correlation:
    "How much market returns and inflation surprises move together in the simulation. Click for the full explanation.",
  return_serial_correlation:
    "How much one simulated year's return predicts the next — captures market \"streakiness.\" Click for the full explanation.",
  niit_magi_threshold_mfj:
    "The income level above which the extra 3.8% investment-income tax applies. Click for the full explanation.",
  glide_path:
    "Static keeps the allocation strategy fixed; target_date automatically de-risks with age. Click for the full explanation.",
  roth_irmaa_cap:
    "Stops Roth conversions from pushing income across a Medicare surcharge tier. Click for the full explanation.",
  roth_irmaa_target_tier:
    "Which Medicare surcharge tier the Roth conversion guardrail treats as the line not to cross. Click for the full explanation.",
  roth_irmaa_headroom_usage_pct:
    "How much of the room below the IRMAA tier line conversions are allowed to use. Click for the full explanation.",
  qcd_enabled:
    "Lets an IRA owner 70½+ send money straight to charity tax-free, satisfying the RMD. Click for the full explanation.",
  daf_annual_contribution:
    "Donor-Advised Fund: get the deduction now, decide which charities get the money later. Click for the full explanation.",
  h_qcd_annual_amount:
    "This member's annual tax-free charity gift straight from their IRA. Click for the full explanation.",
  w_qcd_annual_amount:
    "This member's annual tax-free charity gift straight from their IRA. Click for the full explanation.",
  h_qcd_start_year:
    "Optional override for when this member's QCD giving begins. Click for the full explanation.",
  w_qcd_start_year:
    "Optional override for when this member's QCD giving begins. Click for the full explanation.",
  h_qcd_end_year:
    "Optional override for when this member's QCD giving stops. Click for the full explanation.",
  w_qcd_end_year:
    "Optional override for when this member's QCD giving stops. Click for the full explanation.",
};
// A hand-tuned FIELD_TOOLTIPS entry, once written, is worth more than the
// generic fallback -- keep curating it for fields where the generic text
// reads too dry. But #250: the icon itself must not be gated on that curated
// list, or "layman's helper text throughout the UI" only ever covers the
// ~30 fields someone got around to hand-writing. Every field already gets a
// full purpose/impact/consider explanation when clicked, via showFieldHelp's
// fieldGuidance()/row.notes -- this just surfaces the SAME source as a short
// hover preview so the icon (and the promise it makes) appears everywhere
// that explanation exists, not only where a bespoke one-liner was authored.
// Some CSV `notes` were written as terse dev-facing reminders ("Gross in
// earn_start_year", "s_corp | sole_prop | W2") that quote the storage label
// or enum codes verbatim -- fine as an internal comment, not as user-facing
// copy. Reuse the same snake_case-looking-token heuristic the group-heading
// cleanup uses so those notes get skipped in favor of fieldGuidance's
// already-humanized text instead of leaking the raw identifier to a tooltip.
const _LOOKS_INTERNAL = /[a-z][a-z0-9]*_[a-z0-9]+/;
function fieldTooltipPreview(row) {
  const lbl = norm(row?.label);
  const curated = FIELD_TOOLTIPS[lbl];
  if (curated) return curated;
  const note = String(row?.schema?.description || row?.notes || "").trim();
  if (note && !_LOOKS_INTERNAL.test(note)) {
    return note.length > 220 ? note.slice(0, 217) + "..." : note;
  }
  try {
    const purpose = fieldGuidance(row).purpose;
    if (purpose) return purpose.length > 220 ? purpose.slice(0, 217) + "..." : purpose;
  } catch (_e) {
    // fieldGuidance can reference lastBuildSummary/rows state that isn't
    // ready during early renders -- fall through to no tooltip that pass.
  }
  return "";
}
function fieldTooltipHtml(lbl, row) {
  const tip = row ? fieldTooltipPreview(row) : FIELD_TOOLTIPS[lbl];
  if (!tip) return "";
  const suffix = / Click for the full explanation\.?$/i.test(tip)
    ? ""
    : " Click for the full explanation.";
  // #219/#220: standard superscript-i info link. Hover/focus shows the short
  // hint via the native title tooltip; click bubbles to the field row's own
  // onclick, which opens the full purpose/impact/consider panel via
  // showFieldHelp -- the badge itself needs no separate click handler.
  const full = tip + suffix;
  return `<sup class="field-info-i" tabindex="0" title="${esc(full)}" aria-label="More info: ${esc(full)}">i</sup>`;
}
// Width of the control should match the width of the value people actually
// type: a 4-digit year does not need the same box as a free-text name. Kept
// separate from valueKind(), whose return values drive number formatting and
// must not shift. Returns a class consumed by the .field.w-* CSS rules.
function fieldSizeClass(r) {
  const units = String(r?.units || "");
  const u = norm(units);
  const l = norm(r?.label);
  const type = String(r?.schema?.type || "").toLowerCase();
  if (type === "boolean" || /^(yes\/no|true\/false)$/i.test(units)) return "";
  if (isDateField(r)) return "w-date";
  if (type === "choice" || u === "choice") return "";
  // Trust the rendered value over the label: several currency fields are named
  // *_base_year (ss_wage_base_base_year = $184,500) and would otherwise be
  // sized as if they held a 4-digit year, clipping the amount.
  const shown = String(displayValueForInput(r, valOf(r)) ?? "");
  if (/^\$/.test(shown) || /\d,\d{3}/.test(shown)) return "w-money";
  // Prose values (rate notes, trust descriptions) must not be squeezed into a
  // numeric-width cell just because the label contains "rate" or "note".
  const words = shown.trim().split(/\s+/).filter(Boolean).length;
  if (/[A-Za-z]/.test(shown) && (words >= 2 || shown.length > 16)) return "w-long";
  if (l.endsWith("_year") || l.endsWith("_age") || ["year", "years", "age"].includes(u))
    return "w-year";
  const kind = valueKind(r);
  if (kind === "percent") return "w-pct";
  if (kind === "currency") return "w-money";
  if (kind === "number") return "w-num";
  return "";
}

function dependencyRank(label) {
  const l = norm(label);
  if (
    [
      "enabled",
      "include",
      "active",
      "use",
      "apply",
      "policy_type",
      "type",
      "mode",
      "allocation_selection_mode",
      "allocation_mode",
      "use_allocation_optimizer",
      "mc_engine_mode",
      "core_spending_growth_mode",
      "roth_conversion_policy",
      "hsa_withdrawal_mode",
      "estate_tax_objective_mode",
      "legacy_objective_mode",
      "roth_objective_mode",
      "reinvest_dividends_default",
    ].includes(l)
  )
    return "00";
  if (
    l.includes("policy") ||
    l.includes("strategy") ||
    l.endsWith("_mode") ||
    l.includes("method")
  )
    return "01";
  if (
    l.includes("target") ||
    l.includes("bracket") ||
    l.includes("tier") ||
    l.includes("guardrail")
  )
    return "02";
  if (
    l.includes("amount") ||
    l.includes("pct") ||
    l.includes("percent") ||
    l.includes("rate") ||
    l.includes("headroom")
  )
    return "03";
  if (l === "survivor_has_dependent") return "50";
  if (
    l.includes("start") ||
    l.includes("end") ||
    l.includes("year") ||
    l.includes("date") ||
    l.includes("window")
  )
    return "04";
  return "50";
}

function fieldFinderCategoryName(group) {
  return group === "Reports" ? "Reports & Review" : group || "Uncategorized";
}
function fieldFinderCategoryOrder() {
  const order = [];
  STEPS.forEach((s) => {
    const name = fieldFinderCategoryName(s.group);
    if (!order.includes(name)) order.push(name);
  });
  return order;
}
function renderFieldFinderGroups(rs) {
  // #241: Travel's budget fields (group amount, start/end year, large-item
  // lines) live in a separate client-side store (taxBudget/budgetLines), not
  // the Plan Data `rows` this page searches, so a "travel" search here always
  // came up empty. Point to the real page instead of faking an editable row.
  const _ffQ = norm(searchText || "");
  const travelPointer =
    _ffQ && "travel".includes(_ffQ)
      ? `<div class="section-note">Travel budget (annual amount, start/end year) and Travel transaction detail are on <a href="#" onclick="setStep('lifestyle_spending');return false">Other Spending</a> — not indexed here yet.</div>`
      : "";
  if (!rs.length)
    return (
      travelPointer ||
      '<div class="field-list"><p>No fields match.</p></div>'
    );
  // (travelPointer, if any, is appended after the matched groups below --
  // some other field's note text can incidentally contain "travel" too, so
  // rs isn't necessarily empty even though no real Travel row exists.)
  const seen = new Set();
  const deduped = rs.filter((r) => {
    const key = [r.section || "", r.subsection || "", r.label || ""].join(
      "\x1f",
    );
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  const catOrder = fieldFinderCategoryOrder();
  const groups = new Map();
  deduped.forEach((r) => {
    const stepId = sourceStepForRow(r);
    const st = STEPS.find((s) => s.id === stepId);
    const name = st ? fieldFinderCategoryName(st.group) : "Uncategorized";
    if (!groups.has(name)) groups.set(name, { name, rows: [] });
    groups.get(name).rows.push(r);
  });
  const ordered = [...groups.values()].sort((a, b) => {
    const ai = catOrder.indexOf(a.name),
      bi = catOrder.indexOf(b.name);
    return (
      (ai < 0 ? 9999 : ai) - (bi < 0 ? 9999 : bi) ||
      a.name.localeCompare(b.name)
    );
  });
  let html = "";
  ordered.forEach((g) => {
    const body = g.rows
      .slice()
      .sort((a, b) => {
        const la = humanLabel(a.label, a),
          lb = humanLabel(b.label, b);
        return (
          la.localeCompare(lb) ||
          friendlyGroup(a).localeCompare(friendlyGroup(b))
        );
      })
      .map((r) => {
        const stepId = sourceStepForRow(r);
        const pageTitle = stepId ? stepTitleById(stepId) : "";
        const qualifier = friendlyGroup(r);
        const sourceLine = [
          pageTitle,
          qualifier && norm(qualifier) !== norm(pageTitle) ? qualifier : "",
        ]
          .filter(Boolean)
          .join(" · ");
        return `<div class="field-finder-row">${sourceLine ? `<div class="field-source-page small">${esc(sourceLine)}</div>` : ""}${fieldHtml(r)}</div>`;
      })
      .join("");
    html += `<details><summary><b>${esc(g.name)}</b><span class="small"> ${g.rows.length} field${g.rows.length === 1 ? "" : "s"}</span></summary><div class="field-list">${body}</div></details>`;
  });
  return travelPointer + html;
}


// True for any mode where the plan is driven by a computed recommendation
// rather than the user's manually-entered target_pct rows.





// Legacy regression marker: target_pct rows are inactive in optimizer mode and now appear in the Inactive values summary instead of the active allocation table.
function allocationPreviewRowsForPost() {
  return rows
    .filter(isEditable)
    .map((r) => ({
      section: r.section || "",
      subsection: r.subsection || "",
      label: r.label || "",
      value: dirty.has(r.row_index)
        ? String(dirty.get(r.row_index))
        : String(valOf(r) || ""),
    }));
}
function allocationPreviewFingerprint() {
  const rel = allocationPreviewRowsForPost().filter((r) => {
    const l = norm(r.label),
      s = r.section;
    return (
      s === "Asset Allocation Policy" ||
      s === "Asset Class Optimizer Controls" ||
      s === "Model Constants" ||
      s === "Asset Class Assumptions" ||
      s === "Other Assets" ||
      s === "Income Streams" ||
      s === "Note Receivable"
    );
  });
  return JSON.stringify({
    mode: allocationSelectionMode(),
    rows: rel,
    holdingsChanged: !!window.holdingsChanged,
    holdingsLen: String(window.holdingsText || "").length,
  });
}

function resetAllocationPreview() {
  allocationPreview = null;
  allocationPreviewKey = "";
  allocationPreviewError = "";
  allocationPreviewLoading = false;
  allocationPreviewSeq++;
}
function allocationTargetsValid() {
  const rs = allocationTargetRows();
  if (!rs.length) return true;
  return Math.abs(allocationTargetTotalPct() - 100) <= 0.01;
}


function validateAllocationTargetsOrMessage() {
  const mode = allocationSelectionMode();
  if (mode === "user_target" && !allocationTargetsValid()) {
    activeStep = "allocation_assets";
    renderMain();
    showMessage(
      "Active included/alternate target rows must total 100.00% before saving or building.",
      "error",
    );
    return false;
  }
  if (mode === "optimizer_recommendation" && !optimizerOverrideValid()) {
    activeStep = "allocation_assets";
    renderMain();
    showMessage(
      "Optimizer override allocation must total 100.00% when any override percentage is entered. Leave all optimizer override rows blank to use the computed optimizer target.",
      "error",
    );
    return false;
  }
  return true;
}

const PERSON_TABLE_LABELS = [
  "name",
  "nickname",
  "dob",
  "retirement_date",
  "mortality_age",
];


function personNickPlaceholder(nameRow) {
  const first =
    String(nameRow ? valOf(nameRow) : "")
      .trim()
      .split(/\s+/)[0] || "";
  return first ? `e.g. ${first}` : "Short name for reports";
}
function personCellInput(r, aria, placeholder) {
  if (!r)
    return '<span class="small">Reload the current plan to create this field.</span>';
  const isDate = isDateField(r);
  const type = isDate ? "date" : "text";
  const val = isDate ? toIsoDateValue(valOf(r)) : String(valOf(r) || "");
  return `<input class="person-input" type="${type}" value="${esc(val)}" placeholder="${esc(placeholder || "")}" aria-label="${esc(aria)}" oninput="editValue(${r.row_index},this.value,this)" onfocus="beginEdit(${r.row_index},this)" onblur="finishEdit(${r.row_index},this)">`;
}
function renderHouseholdPeople() {
  const people = [1, 2]
    .map((n) => ({
      n,
      name: householdPersonRow(n, "name"),
      nickname: householdPersonRow(n, "nickname"),
      dob: householdPersonRow(n, "dob"),
      retire: householdPersonRow(n, "retirement_date"),
      mortality: householdPersonRow(n, "mortality_age"),
      // #239: moved here from Economic & Tax Assumptions' Retirement section
      // -- its section is "Model Constants", not "Household", so it needs
      // its own lookup rather than householdPersonRow's Household-only match.
      rmdAge: rows.find(
        (r) => isEditable(r) && norm(r.label) === `member_${n}_rmd_start_age`,
      ) || null,
    }))
    .filter((p) => p.name || p.nickname || p.dob);
  const nickMissing = people.some(
    (p) =>
      p.name &&
      String(valOf(p.name) || "").trim() &&
      p.nickname &&
      !String(valOf(p.nickname) || "").trim(),
  );
  let html = `<div class="holdings"><h3 class="group-title">People</h3><div class="section-note">One row per person. <b>Nickname</b> is the short name used everywhere the plan names a person — reports, charts, and workbook labels. ${nickMissing ? "<b>Add a nickname for each person</b> (or leave blank to use their first name)." : ""}</div><div class="lot-table-wrap"><table class="lot-table people-table"><thead><tr><th></th><th>Full name</th><th>Nickname (used in reports)</th><th>Date of birth</th><th title="Year is parsed from this date; base retirement assumption">Retirement date</th><th title="Plan horizon = birth year + this age">Mortality age</th><th title="Age Required Minimum Distributions begin (SECURE 2.0)">RMD start age</th></tr></thead><tbody>`;
  people.forEach((p) => {
    const who = String(p.name ? valOf(p.name) : "").trim() || `Person ${p.n}`;
    html += `<tr><td><b>Person ${p.n}</b></td><td>${personCellInput(p.name, `Full name for ${who}`)}</td><td>${personCellInput(p.nickname, `Nickname for ${who}`, personNickPlaceholder(p.name))}</td><td>${personCellInput(p.dob, `Date of birth for ${who}`)}</td><td>${personCellInput(p.retire, `Retirement date for ${who}`)}</td><td>${personCellInput(p.mortality, `Mortality age for ${who}`)}</td><td>${personCellInput(p.rmdAge, `RMD start age for ${who}`)}</td></tr>`;
  });
  html += `</tbody></table></div><p class="small">Nicknames replace generic "Member 1 / Member 2" wording in every user-facing report. Leave Person 2 blank for a single-person household.</p></div>`;
  const personLabelSet = new Set(
    [1, 2].flatMap((n) => PERSON_TABLE_LABELS.map((s) => `member_${n}_${s}`)),
  );
  const rest = rawRowsForStep("household_people").filter(
    (r) => !personLabelSet.has(norm(r.label)),
  );
  const missing = rawRowsForStep("household_people").filter(isMissing);
  const banner = missing.length
    ? `<div class="missing-list"><h3>${missing.length} required field${missing.length === 1 ? "" : "s"} missing in this view</h3><ul>${missing
        .slice(0, 8)
        .map((r) => `<li>${esc(humanLabel(r.label, r))}</li>`)
        .join("")}</ul></div>`
    : "";
  return banner + html + renderFieldGroups(rest);
}
function rowSortKeyForIncomeWork(r) {
  const sub = norm(r.subsection || "");
  const sec = norm(r.section || "");
  if (sub === "earned_income") return "00";
  if (sub === "self_employment") return "10";
  if (sub === "s_corp") return "15";
  if (sec === "payroll tax" && sub === "social security") return "20";
  if (sec === "payroll tax" && sub === "medicare") return "25";
  if (sec === "payroll tax") return "28";
  if (sub === "retirement_contributions") return "40";
  return "99";
}
function renderIncomeWork() {
  if (searchText.trim()) return renderFields("income_work");
  const rs = rowsForStep("income_work")
    .slice()
    .sort((a, b) =>
      (rowSortKeyForIncomeWork(a) + humanLabel(a.label)).localeCompare(
        rowSortKeyForIncomeWork(b) + humanLabel(b.label),
      ),
    );
  if (!rs.length)
    return '<div class="field-list"><p>No fields in this step.</p></div>';
  const groups = [];
  const groupMap = {};
  rs.forEach((r) => {
    const g = friendlyGroup(r);
    if (!groupMap[g]) {
      groupMap[g] = { name: g, rows: [] };
      groups.push(groupMap[g]);
    }
    groupMap[g].rows.push(r);
  });
  const many = (rs.length > 14 || groups.length > 3) && groups.length > 1;
  let html = "";
  groups.forEach((g) => {
    const body = sortRowsByDependency(g.rows).map(fieldHtml).join("");
    if (many && g.rows.length > 1) {
      html += `<details><summary>${esc(g.name)}</summary><div class="field-list">${body}</div></details>`;
    } else {
      html += `<div class="field-list">${groups.length > 1 ? `<h3 class="group-title">${esc(g.name)}</h3>` : ""}${body}</div>`;
    }
  });
  return html;
}
function renderEstateWithAnnuityLink() {
  return renderEstateInformation();
}

// Plan KPI metrics panel (home screen) moved to dashboard_decomp_home_panels.js
// (first modularization increment).

/* ── 4.2 + 4.3 Spending step completion notes and auto-advance ── */
const SPENDING_COMPLETION = {
  spending_core: {
    note: "Done when: budget amounts are entered for the categories you track.",
    isDoneFn: () =>
      !!(planLoaded && !stepStats("spending_core").missing.length),
    nextStep: "ytd_transactions",
    nextLabel: "Import Transactions",
  },
  ytd_transactions: {
    note: "Done when: at least one transaction file has been imported.",
    isDoneFn: () =>
      !!(
        ytdData &&
        ytdData.summary &&
        ytdData.summary.enabled &&
        (ytdData.summary.transaction_count || 0) > 0
      ),
    nextStep: "spending_dashboard",
    nextLabel: "Review vs Plan",
  },
  spending_dashboard: {
    note: "Done when: you have reviewed the YTD rate vs. your spending model, and synced or decided no sync is needed.",
    isDoneFn: () => false,
    nextStep: null,
    nextLabel: null,
  },
};
function spendingFlowFooterHtml(stepId) {
  const cfg = SPENDING_COMPLETION[stepId];
  if (!cfg) return "";
  const done = cfg.isDoneFn();
  let html = `<div class="spending-completion-note${done ? " done" : ""}"><span class="scomp-icon">${done ? "&#10003;" : "&#9675;"}</span><span>${esc(cfg.note)}</span></div>`;
  if (done && cfg.nextStep) {
    html += `<div class="spending-advance-prompt"><b>Step complete.</b> Ready for: <button class="btn primary" type="button" data-step-id="${esc(cfg.nextStep)}">${esc(cfg.nextLabel)} &rarr;</button></div>`;
  }
  return html;
}

// Closeout checklist moved to dashboard_decomp_home_panels.js (first
// modularization increment).

/* ── 5.6 Session changes log and field undo ── */




// Workbook formatting (Settings → Manage Workbook Formatting) moved to
// dashboard_decomp_workbook_formatting.js (first modularization increment).


const DEFAULT_TRAVEL_TYPES = ["Wedding", "Large Gifts", "Other"];
/* Large Discretionary Expenses (travel extras), liquidity reserve buffers, and
   forced Roth conversions moved to frontend/js/dashboard_decomp_supplemental_tables.js
   (loaded before dashboard.js). */
// Mirrors src/projection_stages/deterministic_engine.py _fra_for_birth_year /
// _ss_claim_factor closely enough for this preview cell. The workbook build
// always uses the authoritative Python engine; this is a display estimate.
function renderRetirementWellness() {
  if (searchText.trim()) return renderFields("retirement_wellness");
  let html =
    '<div class="section-note"><b>Wellness Budget Detail is the authoritative view for healthcare spending.</b> Enter Pre-65 premiums, Medicare Part B/D/G premiums, and non-premium medical, dental, vision, Rx/OTC, and out-of-pocket estimates. The projection uses these values as-entered for cash flow and income impact; Medicare premium categories are split to match spending taxonomy.</div>';
  html += renderDomainBudgetPage("healthcare");
  return html;
}
function renderAssetsCashReserves() {
  if (searchText.trim())
    return renderFields("assets_home_cash") + renderLiquidityBuffers();
  const rs = rowsForStep("assets_home_cash");
  const cash = rs.filter((r) => norm(r.subsection || "") === "cash");
  let html =
    '<div class="section-note">Spendable cash outside the investment accounts, and the reserve floor the plan protects before drawing from the portfolio. <b>Home value and home sale inputs are on the <a href="#" onclick="setStep(\'spending_mortgage_events\');return false">Housing tab</a>.</b></div>';
  if (cash.length)
    html +=
      '<div class="field-list">' + cash.map(fieldHtml).join("") + "</div>";
  html += renderLiquidityBuffers();
  return html;
}
// #266: housing-estimate apply/restore helpers live in dashboard_decomp_misc.js.


let liabilityRowsCache = null;
function parseCsvLine(line) {
  const out = [];
  let cur = "",
    q = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      if (q && line[i + 1] === '"') {
        cur += '"';
        i++;
      } else q = !q;
    } else if (ch === "," && !q) {
      out.push(cur);
      cur = "";
    } else cur += ch;
  }
  out.push(cur);
  return out;
}


// Account-label formatting is used well beyond the holdings feature (QDRO
// labels, YTD account dropdowns, Plan Data Summary) -- stays a shared
// dashboard.js utility rather than moving into dashboard_decomp_holdings.js.


const LIABILITY_HEADER = [
  "liability_id",
  "type",
  "label",
  "balance",
  "interest_rate",
  "monthly_payment",
  "start_year",
  "payoff_year",
  "notes",
];
// Fields revealed per type. balance + interest_rate are always shown; payment-style
// fields differ by how each liability is forecast.




// #215: carrier-illustration schedules for Life policies -- the plan's
// projection years are read from the existing Annuity Death Benefits matrix
// (already correct for this household) rather than re-derived here.

// Excluded: "Priority N" is the removed legacy cascade table; "Account Order" is owned by the Withdrawal order drag editor above and would otherwise re-render as raw integers (ticket 285). See tests/frontend/withdrawal_other_rows.test.mjs.
function withdrawalOtherRows() {
  const isOwnedElsewhere = (r) => r.section === "Withdrawal Policy" && (r.subsection === "Account Order" || /^Priority\s+\d+$/i.test(String(r.subsection || "")));
  return rowsForStep("withdrawal_strategy").filter((r) => !isOwnedElsewhere(r));
}
// The withdrawal cascade order used to be an editable "compressed
// withdrawal-order table" here (Priority 1-6, saved via POST
// /api/withdrawal-order). It was removed: the projection engine
// (src/projection_stages/deterministic_engine.py) has always run a fixed,
// hardcoded cascade and never read that table's output, so editing it and
// clicking Save silently changed nothing in the workbook. See
// documentation/reports/SYSTEM_REVIEW_2026-07-18.md §10.1. This block now
// just states the fixed order as read-only text. Keep this string in sync
// with FIXED_WITHDRAWAL_CASCADE_DESCRIPTION in src/taxes.py (both describe
// the same hardcoded engine sequence) — test_withdrawal_roth_ui_cleanup.py
// checks the two stay identical.
const FIXED_WITHDRAWAL_CASCADE_DESCRIPTION =
  "RMDs → HSA window → tax-sensitive pre-tax → taxable/trust → final pre-tax/HSA → Roth last → Home Equity";
// #276: the account-TYPE cascade above is fixed by the engine (see the note
// above FIXED_WITHDRAWAL_CASCADE_DESCRIPTION); the individual-ACCOUNT-level
// override within whichever type-slot an account falls into (e.g. which of
// two taxable brokerage accounts drains first) is implemented in
// dashboard_decomp_misc.js (withdrawalAccountOrderEditorHtml() and friends)
// to keep this file under its line-count ratchet.
function renderWithdrawalOrderTable() {
  const editor = window.withdrawalAccountOrderEditorHtml ? window.withdrawalAccountOrderEditorHtml() : "";
  return `<details><summary>Withdrawal order</summary><div class="field-list"><div class="section-note"><b>Individual-account draw order is user-configurable below.</b> Each account defaults to its registry order and draws first within its account type when priority is tied; set a lower number to draw an account earlier relative to others of the same type (e.g. which of two taxable brokerage accounts drains first). The account-<i>type</i> sequence itself is fixed by the engine and not user-configurable, since it follows tax rules rather than preference: ${esc(FIXED_WITHDRAWAL_CASCADE_DESCRIPTION)}. RMDs are mandatory income; Roth and home equity are preserved until other liquid sources are exhausted.</div>${editor}</div></details>`;
}
function renderWithdrawalStrategy() {
  if (searchText.trim()) return renderFields("withdrawal_strategy");
  const other = withdrawalOtherRows();
  const hsa = other.filter(
    (r) => r.section === "HSA Policy" && r.subsection === "Withdrawals",
  );
  const tlh = other.filter(
    (r) =>
      r.section === "Withdrawal Policy" &&
      r.subsection === "Tax-Loss Harvesting",
  );
  // #277: Gain Harvest gets its own collapsible section, on par with TLH.
  const gainHarvest = other.filter(
    (r) => r.section === "Withdrawal Policy" && r.subsection === "Gain Harvesting",
  );
  const misc = other.filter(
    (r) =>
      !(r.section === "HSA Policy" && r.subsection === "Withdrawals") &&
      !(
        r.section === "Withdrawal Policy" &&
        r.subsection === "Tax-Loss Harvesting"
      ) &&
      !(
        r.section === "Withdrawal Policy" &&
        r.subsection === "Gain Harvesting"
      ),
  );
  let html = renderWithdrawalOrderTable();
  if (hsa.length) {
    const modeRow = hsa.find((r) => norm(r.label) === "hsa_withdrawal_mode");
    const mode = String(modeRow ? valOf(modeRow) : "spend_as_needed")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_");
    let visible = modeRow ? [modeRow] : [];
    if (mode === "annual_pct" || mode === "annual_percent")
      visible = visible.concat(
        hsa.filter((r) =>
          [
            "hsa_withdrawal_pct",
            "hsa_withdrawal_start_year",
            "hsa_withdrawal_end_year",
          ].includes(norm(r.label)),
        ),
      );
    else if (mode === "smooth_window" || mode === "window")
      visible = visible.concat(
        hsa.filter((r) =>
          [
            "hsa_withdrawal_start_year",
            "hsa_withdrawal_end_year",
            "withdrawal_window",
          ].includes(norm(r.label)),
        ),
      );
    else if (mode === "optimize")
      visible = visible.concat(hsaOptimizeVisibleRows(hsa));
    else
      visible = visible.concat(
        hsa.filter(
          (r) =>
            ![
              "hsa_withdrawal_pct",
              "hsa_withdrawal_start_year",
              "hsa_withdrawal_end_year",
              "withdrawal_window",
              "hsa_consume_by",
              "hsa_min_ending_balance",
            ].includes(norm(r.label)) && r !== modeRow,
        ),
      );
    html += `<details><summary>HSA withdrawal policy</summary><div class="field-list"><div class="section-note"><b>Start here:</b> choose HSA withdrawal mode. The schedule fields below change based on that mode. Default is spend as needed, which hides annual-percentage and window controls.</div>${sortRowsByDependency(visible).map(fieldHtml).join("")}</div></details>`;
  }
  if (tlh.length)
    html += `<details><summary>Tax Loss Harvesting</summary><div class="field-list"><div class="section-note">Controls whether and how the projection harvests capital losses from taxable-account lots each year.</div>${sortRowsByDependency(tlh).map(fieldHtml).join("")}</div></details>`;
  if (gainHarvest.length)
    html += `<details><summary>Gain Harvest</summary><div class="field-list"><div class="section-note">Controls whether and how the projection harvests capital gains from taxable-account lots each year (e.g. to fill up a low tax bracket).</div>${sortRowsByDependency(gainHarvest).map(fieldHtml).join("")}</div></details>`;
  if (misc.length)
    html += `<details><summary>Other funding and rollover settings</summary><div class="field-list"><div class="section-note">Annual funding tolerance and spousal rollover settings are operational assumptions. They affect workbook QC, survivor account consolidation, RMD timing, and late-life cash-flow output.</div>${sortRowsByDependency(misc).map(fieldHtml).join("")}</div></details>`;
  return html;
}

const ROTH_PRIMARY_LABELS = [
  "roth_conversion_policy",
  "roth_bracket_strategy",
  "roth_headroom_usage_pct",
  "roth_target_bracket_rate",
  "roth_fixed_annual_amount",
  "max_annual_conversion_pct_of_traditional_ira",
  "max_conversion_years",
];
const ROTH_IRMAA_LABELS = [
  "irmaa_guardrail_mode",
  "roth_irmaa_target_tier",
  "roth_irmaa_headroom_usage_pct",
  "irmaa_annual_inflator",
];
const ROTH_ENGINE_LABELS = [
  "roth_conv_window_end_offset",
  "roth_optimize_terminal_weight",
  "roth_optimize_lifetime_tax_weight",
  "roth_tax_discount_rate",
];
const ROTH_LEGACY_LABELS = [
  "roth_objective_mode",
  "estate_tax_objective_mode",
  "legacy_objective_mode",
  "roth_optimize_terminal_pretax_tax_rate",
  "future_tax_rate_stress_pct",
  "future_tax_risk_weight",
  "inheritance_tax_burden_weight",
  "heir_ordinary_tax_rate_assumption_pct",
  "pre_tax_bequest_penalty_pct",
  "roth_bequest_preference_bonus_pct",
  "survivor_tax_risk_weight",
];
const ROTH_WINDOW_LABELS = [
  "max_conversion_years",
  "roth_conv_window_end_offset",
  "max_annual_conversion_pct_of_traditional_ira",
];
const IRMAA_OFF_MODES = ["IGNORE", "WARN_ONLY", "NONE", "OFF"];
function boolishValue(r) {
  const v = String(r ? valOf(r) : "")
    .trim()
    .toLowerCase();
  return ["1", "true", "yes", "y", "on"].includes(v);
}


const SCENARIO_SET_STORAGE_KEY = "retirement.scenario_sets.v1";

function scenarioRowKeyFromParts(section, subsection, label) {
  return [norm(section || "Scenarios"), norm(subsection), norm(label)].join(
    "::",
  );
}






function ytdAccountMoneyDisplay(v) {
  return ytdTxnMoneyDisplay(v);
}
function focusYtdAccountMoney(input) {
  if (input) input.value = ytdRawMoney(input.value);
}
function updateYtdAccountMoney(i, field, input) {
  const raw = ytdRawMoney(input?.value);
  updateYtdAccount(i, field, raw);
}
function blurYtdAccountMoney(i, field, input) {
  const raw = ytdRawMoney(input?.value);
  if (input) input.value = ytdAccountMoneyDisplay(raw);
  updateYtdAccount(i, field, raw);
}

function showYtdLoadOverlay() {
  setBuildOverlay(
    true,
    "Loading transactions",
    "Reading saved transactions and account mappings. Large transaction histories can take a few seconds.",
    "waiting",
  );
  const overlay = document.getElementById("buildOverlay");
  if (overlay) overlay.classList.add("no-cancel");
}
function hideYtdLoadOverlay() {
  const overlay = document.getElementById("buildOverlay");
  if (overlay) overlay.classList.remove("no-cancel");
  hideBuildOverlay();
}




async function deleteYtdAccount(i) {
  if (
    !(await showInAppConfirm("This cannot be undone.", {
      title: "Delete Account Row",
      confirmLabel: "Delete",
      variant: "danger",
    }))
  )
    return;
  ytdData.account_setup.splice(i, 1);
  markYtdAccountsDirty();
  renderMain();
}
async function saveYtdAccountSetup() {
  try {
    await api("/api/ytd/account-setup", {
      method: "POST",
      body: JSON.stringify({ accounts: ytdData.account_setup || [] }),
    });
    await loadYtdStatus();
    setYtdDirtyButtonStates();
    renderMain();
    showMessage("Account setup saved.");
  } catch (e) {
    showMessage("Error saving YTD account setup: " + e.message, "error");
  }
}
async function recoverYtdAccountSetup() {
  try {
    const pathResult = await showInAppPrompt("Recovery path (optional):", "", {
      title: "Recover YTD Account Setup",
      placeholder: "Leave blank to auto-scan",
    });
    if (pathResult === null) return;
    const pathText = pathResult || "";
    const out = await api("/api/ytd/account-setup/recover", {
      method: "POST",
      body: JSON.stringify({ force: true, path: pathText.trim() }),
    });
    await loadYtdStatus();
    setYtdDirtyButtonStates();
    renderMain();
    if (out && out.recovered) {
      const after = out.after || {};
      showMessage(
        `Recovered YTD account setup from ${out.source || "a prior saved copy"}: ${after.rows || 0} rows, ${after.prior_balance_rows || 0} prior-year balances, ${after.mapped_rows || 0} mapped investment rows.`,
      );
    } else
      showMessage(
        (out && out.reason) ||
          "No richer YTD account setup recovery source was found.",
        "warn",
      );
  } catch (e) {
    showMessage("Error recovering YTD account setup: " + e.message, "error");
  }
}
function ytdStaleGrowthAccounts() {
  const currentYear =
    Number(ytdData?.summary?.current_year) || new Date().getFullYear();
  return (ytdData?.account_setup || []).filter((r) => {
    if (!ytdIsGrowthRole(String(r.Role || ""))) return false;
    const d = String(r["Prior Year End Date"] || "");
    const m = d.match(/\d{4}/);
    const y = m ? parseInt(m[0], 10) : 0;
    return y !== currentYear - 1;
  });
}
function ytdRolloverBannerHtml() {
  const currentYear =
    Number(ytdData?.summary?.current_year) || new Date().getFullYear();
  const stale = ytdStaleGrowthAccounts();
  if (!stale.length) return "";
  return `<div class="section-note warn"><b>Start ${currentYear} tracking:</b> ${stale.length} account${stale.length === 1 ? "" : "s"} still ${stale.length === 1 ? "has" : "have"} a Prior Year End Balance from an earlier year. Roll forward to copy each account's current value into Prior Year End Balance (dated 12/31/${currentYear - 1}), so growth tracking — and the current-year Net Worth/Cash Flow blend — starts fresh for ${currentYear}. <button class="btn" type="button" onclick="rollForwardYtdAccounts()">Start ${currentYear} tracking</button></div>`;
}
async function rollForwardYtdAccounts() {
  try {
    const out = await api("/api/ytd/account-setup/roll-forward", {
      method: "POST",
      body: JSON.stringify({}),
    });
    await loadYtdStatus();
    renderMain();
    showMessage(
      `Rolled forward ${out.accounts_updated || 0} account${(out.accounts_updated || 0) === 1 ? "" : "s"} for the new tracking year.`,
      "success",
    );
  } catch (e) {
    showMessage("Error starting new-year tracking: " + e.message, "error");
  }
}


function ytdInvestmentHoldingAccounts() {
  return [
    ...new Set(
      (
        ytdData?.summary?.investment_holding_accounts ||
        ytdData?.investment_holding_accounts ||
        []
      ).filter(Boolean),
    ),
  ].sort((a, b) => a.localeCompare(b));
}
function ytdAccountRoleOptions(selected) {
  let selectedValue = String(selected || "");
  if (selectedValue === "Liability") selectedValue = "Other liability";
  const groups = [
    [
      "Assets and income sources",
      [
        "Cash / spending",
        "Investment",
        "Annuity/Pension",
        "Annuity",
        "Pension",
        "Social Security",
        "Offline asset",
        "Real estate",
        "Business interest",
        "Note receivable",
        "Income source",
      ],
    ],
    [
      "Liabilities",
      ["Credit card", "Mortgage", "HELOC", "Loan", "Other liability"],
    ],
    ["Other", ["Ignore"]],
  ];
  const opts = groups.flatMap((g) => g[1]);
  return (
    groups
      .map(
        ([label, items]) =>
          `<optgroup label="${esc(label)}">${items.map((o) => `<option value="${esc(o)}" ${selectedValue === o ? "selected" : ""}>${esc(o)}</option>`).join("")}</optgroup>`,
      )
      .join("") +
    (selectedValue && !opts.includes(selectedValue)
      ? `<option value="${esc(selectedValue)}" selected>${esc(selectedValue)}</option>`
      : "")
  );
}
function ytdIsGrowthRole(role) {
  return (
    role === "Investment" ||
    role === "Annuity/Pension" ||
    role === "Annuity" ||
    role === "Pension"
  );
}
function ytdMappableAccounts() {
  const holding = ytdInvestmentHoldingAccounts();
  const annuityPension = (ytdData?.summary?.annuity_pension_accounts || [])
    .map((s) => String(s).trim())
    .filter(Boolean);
  return [...new Set([...holding, ...annuityPension])].sort((a, b) =>
    a.localeCompare(b),
  );
}
function ytdInvestmentOptions(selected) {
  const opts = ytdMappableAccounts();
  let html = '<option value=""></option>';
  html += opts
    .map(
      (o) =>
        `<option value="${esc(o)}" ${String(selected || "") === o ? "selected" : ""}>${esc(accountDisplayLabel(o))}</option>`,
    )
    .join("");
  if (selected && !opts.includes(selected))
    html += `<option value="${esc(selected)}" selected>${esc(accountDisplayLabel(selected))} (not in accounts)</option>`;
  return html;
}
function makeYtdAccountRow(acct = "", role = "Cash / spending") {
  return {
    Account: acct,
    Role: role,
    "Mapped Investment Account": "",
    "Prior Year End Date": `${new Date().getFullYear() - 1}-12-31`,
    "Prior Year End Balance": "0",
    "Current Value": role === "Investment" ? "" : "0",
  };
}
function addManualYtdAccount() {
  if (!ytdData)
    ytdData = {
      transactions: [],
      account_setup: [],
      summary: { enabled: false },
    };
  ytdData.account_setup = ytdData.account_setup || [];
  const nameEl = document.getElementById("ytdManualAccountName");
  const roleEl = document.getElementById("ytdManualAccountRole");
  let acct = String(nameEl?.value || "").trim();
  const role =
    String(roleEl?.value || "Offline asset").trim() || "Offline asset";
  if (!acct) {
    showMessage("Enter an account/source name before adding it.", "error");
    nameEl?.focus();
    return;
  }
  if (
    ytdData.account_setup.some(
      (r) =>
        String(r.Account || "")
          .trim()
          .toLowerCase() === acct.toLowerCase(),
    )
  ) {
    showMessage(
      "That account/source is already in the mapping table.",
      "error",
    );
    return;
  }
  ytdData.account_setup.push(makeYtdAccountRow(acct, role, ""));
  if (nameEl) nameEl.value = "";
  markYtdAccountsDirty();
  renderMain();
}
// Extracts the 4-digit calendar year from a transaction Date value. Stored
// rows are normalized to ISO "YYYY-MM-DD" on save, but in-progress edits or
// freshly-imported rows may still be in another supported format, so fall
// back to the first 4-digit run in the string.
// The calendar year the currently selected actuals period reports on
// (this year for Year-to-date, last calendar year for Last Year).
// Rows matching the currently selected actuals period, independent of the
// search/category/account filters -- used to tell "no transactions for this
// period" apart from "the current filters matched nothing".


function detailedSheetByName(name) {
  const key = String(name || "");
  return (
    detailedResultSheets[key] ||
    (detailedResultsData?.sheets || []).find((s) => s.name === key) ||
    null
  );
}
function chooseDefaultDetailedSheet() {
  const isExcelTab =
    (window.RetirementReportsUI &&
      window.RetirementReportsUI.isExcelTabSheet) ||
    function (s) {
      return (
        s.source === "excel_parser_fallback" ||
        /^\d+[A-Za-z]/.test(String(s.name || ""))
      );
    };
  const sheets = (detailedResultsData?.sheets || []).filter(isExcelTab);
  if (!sheets.length) return "";
  if (activeDetailedSheet && sheets.some((s) => s.name === activeDetailedSheet))
    return activeDetailedSheet;
  const content = sheets.filter((s) =>
    /^\d+[A-Za-z]/.test(String(s.name || "")),
  ); // Prefer a non-chart table sheet as the default landing page
  const tableFirst = content.find((s) => s.kind !== "chart_dashboard");
  activeDetailedSheet = (tableFirst || content[0] || sheets[0]).name;
  return activeDetailedSheet;
}

function renderDetailedResultsProgressTick() {
  try {
    if (_isViewingDetailedResults()) {
      renderMain();
      renderSteps();
    }
  } catch (_e) {}
}
function detailProgressState(mode, elapsed) {
  const isSheet = mode === "sheet";
  const base = isSheet ? 8 : 6;
  const cap = isSheet ? 94 : 90;
  const speed = isSheet ? 7.5 : 5.25;
  const curve = 1 - Math.exp(-Math.max(0, elapsed) / speed);
  const pct = Math.min(cap, base + (cap - base) * curve);
  let phase = isSheet ? "Opening result page" : "Opening results index";
  let detail = isSheet
    ? "Requesting the selected result page and preparing a browser-friendly view."
    : "Checking the generated results and loading navigation.";
  if (elapsed > 1) {
    phase = isSheet ? "Reading result data" : "Building results navigation";
    detail = isSheet
      ? "Reading result headings, values, and section breaks for this page."
      : "Grouping result pages into Results Explorer topics.";
  }
  if (elapsed > 3) {
    phase = isSheet
      ? "Finding headings and column groups"
      : "Preparing Results Explorer";
    detail = isSheet
      ? "Detecting sticky heading rows and human-readable column groups."
      : "Preparing the explorer shell; page details load on demand.";
  }
  if (elapsed > 6) {
    phase = isSheet ? "Formatting display" : "Rendering navigation";
    detail = isSheet
      ? "Formatting values and packaging the table or chart view."
      : "Rendering Results Explorer navigation.";
  }
  if (elapsed > 12) {
    phase = isSheet
      ? "Still working on this page"
      : "Still preparing navigation";
    detail = isSheet
      ? "Large pages can take longer. The estimate stays below complete until the result data arrives."
      : "The index is still loading; use Refresh results if this persists.";
  }
  return { pct, phase, detail };
}
function startDetailedResultsProgress(mode = "index") {
  if (detailedResultsProgressTimer) clearInterval(detailedResultsProgressTimer);
  const sheetMode = mode === "sheet";
  detailedResultsProgress = {
    active: true,
    pct: sheetMode ? 6 : 4,
    phase: sheetMode ? "Opening result page" : "Opening results index",
    detail: sheetMode
      ? "Locating the selected result page and reading only the visible UI data."
      : "Checking the generated workbook and loading result-page navigation.",
    startedAt: Date.now(),
    mode,
  };
  renderDetailedResultsProgressTick();
  detailedResultsProgressTimer = setInterval(() => {
    if (!(detailedResultsLoading || detailedResultSheetLoading)) return;
    const elapsed =
      (Date.now() - (detailedResultsProgress.startedAt || Date.now())) / 1000;
    const modeNow = detailedResultsProgress.mode || mode;
    const state = detailProgressState(modeNow, elapsed);
    detailedResultsProgress = {
      active: true,
      pct: Math.max(Number(detailedResultsProgress.pct) || 0, state.pct),
      phase: state.phase,
      detail: state.detail,
      startedAt: detailedResultsProgress.startedAt,
      mode: modeNow,
    };
    renderDetailedResultsProgressTick();
  }, 250);
}
function stopDetailedResultsProgress(finalPct = 100) {
  if (detailedResultsProgressTimer) {
    clearInterval(detailedResultsProgressTimer);
    detailedResultsProgressTimer = null;
  }
  detailedResultsProgress = Object.assign({}, detailedResultsProgress, {
    active: false,
    pct: finalPct || 100,
  });
}
function mergeDetailedSheetMeta(sheet) {
  if (!sheet || !detailedResultsData) return;
  const list = detailedResultsData.sheets || [];
  const idx = list.findIndex((s) => s.name === sheet.name);
  const meta = Object.assign({}, idx >= 0 ? list[idx] : {}, sheet, {
    loaded: true,
    section_count: (sheet.sections || []).length,
  });
  if (idx >= 0) list[idx] = meta;
  else list.push(meta);
  (detailedResultsData.categories || []).forEach((cat) => {
    (cat.sheets || []).forEach((s) => {
      if (s.name === sheet.name) {
        s.row_count = sheet.row_count;
        s.section_count = (sheet.sections || []).length;
        s.loaded = true;
      }
    });
  });
}
async function loadDetailedResults(force = false) {
  if (detailedResultsLoading && detailedResultsIndexInFlight)
    return detailedResultsIndexInFlight;
  if (detailedResultsData && !force) {
    const name = chooseDefaultDetailedSheet();
    if (name && !detailedResultSheets[name])
      loadDetailedResultSheet(name, false);
    return Promise.resolve(detailedResultsData);
  }
  detailedResultsLoading = true;
  detailedResultsError = "";
  detailedResultSheetError = "";
  if (force) {
    detailedResultSheets = {};
    detailedResultSheetInFlight = {};
    activeDetailedSheet = "";
  }
  startDetailedResultsProgress("index");
  detailedResultsIndexInFlight = (async () => {
    try {
      const out = await api("/api/detailed-results?index=1", {
        timeoutMs: 30000,
      });
      detailedResultsProgress = {
        active: true,
        pct: 96,
        phase: "Rendering explorer navigation",
        detail:
          "Preparing sheet navigation. Selected sheet data loads on demand.",
        startedAt: detailedResultsProgress.startedAt,
        mode: "index",
      };
      detailedResultsData = out;
      if (out && out.success) {
        chooseDefaultDetailedSheet();
      } else {
        detailedResultsError =
          (out && out.error) || "Detailed results are not available.";
      }
    } catch (e) {
      detailedResultsData = null;
      const msg = e && e.message ? e.message : String(e);
      detailedResultsError =
        msg.toLowerCase().includes("timed out") || msg.includes("aborted")
          ? "Results index loading timed out. The workbook may be unavailable or the app may be stuck opening it. Try Refresh results or rebuild reports."
          : msg;
    } finally {
      detailedResultsLoading = false;
      detailedResultsIndexInFlight = null;
      stopDetailedResultsProgress(detailedResultsError ? 0 : 100);
      if (_isViewingDetailedResults()) renderMain();
      else renderSteps();
      if (!detailedResultsError && activeDetailedSheet)
        loadDetailedResultSheet(activeDetailedSheet, force);
    }
  })();
  return detailedResultsIndexInFlight;
}

function setDetailedResultSheet(name) {
  // Only auto-open sidebar on very first visit
  if (localStorage.getItem("workbookNavOpened") === null) {
    localStorage.setItem("workbookNavOpened", "1");
    setDetailedResultsNavOpen(true);
  }
  activeStep = "detailed_results";
  activeDetailedSheet = String(name || "");
  saveWorkbookViewState();
  detailedResultSheetError = "";
  renderMain();
  loadDetailedResultSheet(activeDetailedSheet, false);
  setTimeout(() => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, 0);
}
function toggleDetailColumnGroup(key) {
  detailedColumnGroupsOpen[key] = detailedColumnGroupsOpen[key] === false;
  saveWorkbookViewState();
  renderMain();
}
function setAllDetailColumnGroups(keysStr, open) {
  keysStr
    .split(",")
    .filter(Boolean)
    .forEach((k) => {
      detailedColumnGroupsOpen[k] = !!open;
    });
  saveWorkbookViewState();
  setTimeout(renderMain, 0);
}
// DOM-based column group toggle — no re-render; mutates CSS classes directly.
function toggleDetailColGroup(th) {
  const table = th.closest("table");
  if (!table) return;
  const gi = th.dataset.group;
  const label = th.dataset.groupLabel || "";
  const wasCollapsed = th.classList.contains("collapsed"); // Only toggle cells tagged with data-col-group (summary cols with .cg-summary stay visible always)
  table.querySelectorAll('[data-col-group="' + gi + '"]').forEach(function (c) {
    c.classList.toggle("cg-hidden", !wasCollapsed);
  });
  th.classList.toggle("collapsed", !wasCollapsed);
  const lbl = th.querySelector(".col-group-toggle-label");
  if (lbl) lbl.textContent = (wasCollapsed ? "▼ " : "▶ ") + label;
  _updateDetailGroupStatus(th);
}

function expandAllDetailGroups(btn) {
  const wrap = btn.closest(".detail-single-table-wrap");
  if (!wrap) return;
  const table = wrap.querySelector("table");
  if (!table) return;
  table.querySelectorAll(".detail-col-group-th").forEach(function (th) {
    const gi = th.dataset.group;
    const label = th.dataset.groupLabel || "";
    table
      .querySelectorAll('[data-col-group="' + gi + '"]')
      .forEach(function (c) {
        c.classList.remove("cg-hidden");
      });
    th.classList.remove("collapsed");
    const lbl = th.querySelector(".col-group-toggle-label");
    if (lbl) lbl.textContent = "▼ " + label;
  });
  _updateDetailGroupStatus(btn);
}
function collapseAllDetailGroups(btn) {
  const wrap = btn.closest(".detail-single-table-wrap");
  if (!wrap) return;
  const table = wrap.querySelector("table");
  if (!table) return;
  table.querySelectorAll(".detail-col-group-th").forEach(function (th) {
    const gi = th.dataset.group;
    const label = th.dataset.groupLabel || "";
    table
      .querySelectorAll('[data-col-group="' + gi + '"]')
      .forEach(function (c) {
        c.classList.add("cg-hidden");
      });
    th.classList.add("collapsed");
    const lbl = th.querySelector(".col-group-toggle-label");
    if (lbl) lbl.textContent = "▶ " + label;
  });
  _updateDetailGroupStatus(btn);
}
// Toolbar-level control: expands every column-group table on the current
// sheet in one click, since a sheet can hold several sectioned tables and
// each otherwise needs its own "Expand all" click (U5).
function expandAllDetailColumnsOnPage() {
  document
    .querySelectorAll(".detailed-results .detail-single-table-wrap")
    .forEach(function (wrap) {
      const expandBtn = wrap.querySelector(
        '.detail-col-group-bar-btns button[onclick^="expandAllDetailGroups"]',
      );
      if (expandBtn) expandAllDetailGroups(expandBtn);
    });
}

if (typeof window !== "undefined" && !window.RetirementNavigation) {
  window.RetirementNavigation = {
    renderNav: function () {
      return "";
    },
    setStep: function (ctx, id) {
      ctx.setActiveStep(id);
      ctx.renderSteps();
      ctx.renderMain();
      ctx.showStepHelp(id);
      return false;
    },
    wireStepNavigation: function () {
      return false;
    },
    setNavSearch: function (ctx, q) {
      ctx.setNavSearchText(q || "");
      ctx.renderSteps();
      return false;
    },
    updateSearchToggle: function () {
      return false;
    },
    setSearchScope: function (ctx, scope) {
      ctx.setSearchScope(scope || "current");
      ctx.renderMain();
      return false;
    },
    setCombinedSearch: function (ctx, q) {
      ctx.setSearchText(q || "");
      ctx.renderMain();
      return false;
    },
    focusableEntries: function () {
      return [];
    },
  };
}
function renderNav() {
  return window.RetirementNavigation.renderNav(navigationContext());
}


function showSpendingModelLoadOverlay() {
  setBuildOverlay(
    true,
    "Loading Spending Model",
    "Reading transaction history and computing category rollups. This can take a few seconds on large transaction histories.",
    "waiting",
  );
  const overlay = document.getElementById("buildOverlay");
  if (overlay) overlay.classList.add("no-cancel");
}
function hideSpendingModelLoadOverlay() {
  const overlay = document.getElementById("buildOverlay");
  if (overlay) overlay.classList.remove("no-cancel");
  hideBuildOverlay();
}


function catEffectiveBudget(catId) {
  if (categoryBudgetMode[catId] === "detail") return catDetailSum(catId);
  if (hasExplicitBudget(catId))
    return budgetAmount(taxBudget[catId].annual_budget);
  return catDetailSum(catId);
}
function groupModelData(tt, grp) {
  const types =
    spendingModelData && Array.isArray(spendingModelData.tracking_types)
      ? spendingModelData.tracking_types
      : [];
  const type = types.find(
    (t) => String(t.tracking_type || "") === String(tt || ""),
  );
  if (!type) return null;
  return (
    (type.groups || []).find(
      (g) => String(g.group || "") === String(grp || ""),
    ) || null
  );
}


function restoreGroupBudgetModes() {
  groupBudgetMode = {};
  Object.keys(taxBudget || {}).forEach((k) => {
    if (k.startsWith("grp::")) {
      const m = (taxBudget[k] || {})._mode;
      if (m) groupBudgetMode[k.substring(5)] = m;
    }
  });
}

async function recoverPriorSpendingBudget() {
  if (
    !(await showInAppConfirm(
      "Fills missing and zero budget rows with previously saved values. Current nonzero edits will be preserved.",
      {
        title: "Recover Budget Values",
        confirmLabel: "Recover",
        variant: "warn",
      },
    ))
  )
    return;
  try {
    const out = await api("/api/spending/budget/recover", {
      method: "POST",
      body: JSON.stringify({}),
    });
    if (!out || out.success === false)
      throw new Error((out && out.error) || "Recovery failed.");
    clearSpendingCaches();
    await Promise.all([
      loadTaxonomy(true),
      loadSpendingModel(true),
      loadBudgetLines(true),
      loadTaxonomyBudget(true),
    ]);
    showMessage(
      "Recovered " +
        (out.recovered || 0) +
        " budget row" +
        ((out.recovered || 0) === 1 ? "" : "s") +
        ".",
    );
    renderMain();
  } catch (e) {
    showMessage("Error recovering budget values: " + e.message, "error");
  }
}

function domainBudgetNote(domain) {
  if (domain === "core")
    return "Spending Categories is comprehensive: Income and every expense Tracking Type except taxes/transfers should appear in the hierarchy. Detailed budget authority still lives on Housing, Wellness, and Travel where applicable; this view keeps the full accounting model visible. Each group header shows both Annual Budget (what you entered) and Projection Seed (the value the projection engine actually uses as the starting spend amount). They are usually equal — expand the help below to see when and why they can differ.";
  if (domain === "housing")
    return "Housing is the only editable place for mortgage/rent, homeowners insurance, home maintenance, utilities, real-estate taxes, and home improvement projects.";
  if (domain === "healthcare")
    return "Wellness is the only editable place for the Healthcare Premium group (Pre-65 Healthcare Premium plus Medicare Part B, Part D, and Part G), medical, dental, vision, drugs Rx/OTC, vitamins/supplements, and the medical OOP cap/reference.";
  if (domain === "travel")
    return "Travel is the only editable place for recurring travel projection inputs plus transaction-based travel detail. Domestic-travel and lifestyle labels are intentionally not used here.";
  return "Large Discretionary Budget Detail supports only Wedding, Large Gifts, and Other projection rows.";
}
async function hideUnusedTemplateCategories() {
  if (
    !(await showInAppConfirm(
      "Categories with transaction aliases, detail lines, or budget dollars will stay loaded.",
      {
        title: "Hide Unused Categories",
        confirmLabel: "Hide Unused",
        variant: "warn",
      },
    ))
  )
    return;
  api("/api/spending/hide-unused-templates", { method: "POST", body: "{}" })
    .then(function (out) {
      showMessage(
        ((out && out.count) || 0) + " unused template categories hidden.",
      );
      clearSpendingCaches();
      loadTaxonomy(true);
      loadSpendingModel(true);
      loadTaxonomyBudget(true);
      loadBudgetLines(true);
    })
    .catch(function (e) {
      showMessage("Error hiding templates: " + e.message, "error");
    });
}

const LARGE_DISC_TYPES = ["Wedding", "Large Gifts", "Other"];
const LARGE_DISC_CATEGORY_IDS = [
  "weddings",
  "children_weddings",
  "significant_gifts",
  "other_large_discretionary",
];

function renderSpendingDashboardOrLoad() {
  if (typeof renderSpendingDashboard === "function")
    return renderSpendingDashboard();
  if (!window.__spendingDashboardLoading) {
    window.__spendingDashboardLoading = true;
    const s = document.createElement("script");
    s.src = "js/spending_dashboard.js?v=10";
    s.onload = () => {
      window.__spendingDashboardLoading = false;
      renderMain();
    };
    s.onerror = () => {
      window.__spendingDashboardLoading = false;
      showMessage("Error loading spending tracker module.", "error");
    };
    document.head.appendChild(s);
  }
  return '<div class="question"><b>Loading Spending Tracker…</b><p>Initializing the spending dashboard module.</p></div>';
}
window.setPlanReportSection = function (id) {
  activePlanReportSection = id;
  renderMain();
};
function renderOptionalFunctions() {
  if (searchText.trim()) return renderFields("optional_functions");
  const rs = rowsForStep("optional_functions");
  if (!rs.length)
    return '<div class="section-note">No optional module rows found. Save Changes to initialize defaults, then reload.</div>';
  let html = '<div class="opt-module-list">';
  rs.forEach(function (r) {
    const on = boolishValue(r);
    const lbl = humanLabel(r.label, r);
    const desc = formatAcronyms(r.schema?.description || r.notes || "");
    const status = moduleStatus[r.label];
    html += '<div class="opt-module-row">';
    html +=
      '<div class="opt-module-info"><span class="opt-module-name">' +
      esc(lbl) +
      "</span>";
    if (desc) html += '<span class="opt-module-desc">' + esc(desc) + "</span>";
    if (status && status.auto_enabled) {
      html +=
        '<span class="badge auto">Auto-enabled — required by ' +
        esc(status.required_by.join(", ")) +
        "</span>";
    }
    html += "</div>";
    html +=
      '<button class="opt-module-toggle ' +
      (on ? "on" : "off") +
      '" type="button" data-requires-app="1" ' +
      'onclick="editValue(' +
      r.row_index +
      ",'" +
      (on ? "NO" : "YES") +
      "',null);saveAll(false);renderMain()\">" +
      (on ? "ON" : "OFF") +
      "</button>";
    html += "</div>";
  });
  html += "</div>";
  return html;
}
// #301: Reports & Review is primarily the Impact page (Build/Download live
// as buttons on it, not separate tabs -- see renderBuildImpactPage()'s
// headerActions), with Plan Data Review and Build History folded into
// collapsible <details> sections on that same page instead of their own
// tabs. Preflight and Results stay separate tabs -- distinct enough
// workflows (readiness checklist; full workbook sheet browser) that folding
// them in would bury rather than simplify.
const REPORTS_TABS = ["Preflight", "Impact", "Results"];
let reportsActiveTab = "Impact";
try {
  reportsActiveTab = localStorage.getItem("reports_active_tab") || "Impact";
} catch (_e) {}


function renderStrategyTabs(step, tabs, active) {
  return `<div class="workspace-tabs" role="tablist">${tabs.map((t) => `<button class="workspace-tab ${t === active ? "active" : ""}" type="button" role="tab" aria-selected="${t === active ? "true" : "false"}" onclick="setStrategyTab('${escJs(step)}','${escJs(t)}')">${esc(t)}</button>`).join("")}</div>`;
}
// Generic tab registry for "workspace" steps that tab-switch between what
// used to be several separate nav steps -- keyed by the merged step's own
// id, reused by getStrategyTab/setStrategyTab/goToStrategyTab/renderStrategyTabs
// below regardless of which workspace it's for.
// Ticket 286: distribution_strategy's sub-nav is gone. Its four tabs duplicated
// nav entries that already existed at top level; Withdrawal Order moved to the
// Spending workspace below, and Roth Conversion / Allocation & Location are now
// embedded in the Strategy decide box (renderPlanningLevers).
const STRATEGY_TABS = {
  spending_core: ["Spending Model", "Other Spending", "Actual Spending (YTD)", "Spending Analysis", "Withdrawal Order"],
};

// Shared left-nav sub-tab strip for any STRATEGY_TABS-registered workspace step.
function renderWorkspaceSubtabsNav(stepId) {
  const activeTab = getStrategyTab(stepId);
  return `<div class="nav-subtabs">${STRATEGY_TABS[stepId].map((tab) => `<button class="nav-subtab${activeStep === stepId && activeTab === tab ? " active" : ""}" type="button"${!planLoaded ? " disabled" : ""} onclick="goToStrategyTab('${escJs(stepId)}','${escJs(tab)}')">${esc(tab)}</button>`).join("")}</div>`;
}
function getStrategyTab(step) {
  const tabs = STRATEGY_TABS[step] || [];
  try {
    const saved = localStorage.getItem(strategyTabKey(step));
    if (tabs.includes(saved)) return saved;
  } catch (_e) {}
  return tabs[0] || "";
}
function setStrategyTab(step, tab) {
  const tabs = STRATEGY_TABS[step] || [];
  const next = tabs.includes(tab) ? tab : tabs[0] || "";
  try {
    localStorage.setItem(strategyTabKey(step), next);
  } catch (_e) {}
  renderMain();
}
// goToStrategyTab moved to dashboard_decomp_row_model.js (ticket 290, to fit
// the size ratchet after its overlay-ordering fix) -- it is still reachable
// as a bare global via that file's own window bridge, matching every other
// cross-module onclick target in this codebase.
// Ticket 286: the sub-nav is gone. Its four tabs were alternate routes into
// steps that already existed at top level, so every one of them appeared twice
// in the left nav. Withdrawal Order moved to the Spending workspace; Roth
// Conversion and Allocation & Location are embedded here, inside the decide
// box, and no longer carry their own nav entries.
function renderSpecialStrategies() {
  let html = '<div class="special-strategy-workspace">';
  if (helocModuleEnabled()) {
    html += `<details><summary>Home Equity Line</summary>${analysisFrame(renderFields("heloc_strategy"), "strategy")}</details>`;
  } else {
    html +=
      '<div class="section-note">Home Equity Line strategy is off. Enable it on <a href="#" onclick="setStep(\'heloc_strategy\');return false">HELOC → Setup → Enable HELOC Strategy</a> to use it.</div>';
  }
  if (optionalFunctionEnabled("charitable_giving")) {
    html += `<details><summary>Charitable Giving</summary>${analysisFrame(renderEntityCharitable(), "strategy")}</details>`;
  } else {
    html +=
      '<div class="section-note">Charitable Giving strategies are off. Enable Charitable Giving on <a href="#" onclick="setStep(\'optional_functions\');return false">Optional Modules</a> to use them.</div>';
  }
  html += "</div>";
  return html;
}
const SPENDING_WORKFLOW_STEPS = [
  { label: "Spending Model", stepId: "spending_core" },
  { label: "Import Transactions", stepId: "ytd_transactions" },
  { label: "Review vs Plan", stepId: "spending_dashboard" },
  { label: "Sync to Plan", stepId: null },
];
const SPENDING_WORKFLOW_INDEX = {
  spending_core: 0,
  ytd_transactions: 1,
  spending_dashboard: 2,
};
function renderSpendingWorkflowBanner(stepId) {
  const activeIdx = SPENDING_WORKFLOW_INDEX[stepId] ?? -1;
  if (activeIdx < 0) return "";
  const parts = [];
  SPENDING_WORKFLOW_STEPS.forEach((s, i) => {
    if (i > 0) parts.push(`<span class="spending-step-arrow">›</span>`);
    const isDone = i < activeIdx;
    const isActive = i === activeIdx;
    const cls = `spending-step${isActive ? " active" : isDone ? " done" : ""}`;
    const icon = isDone ? "✓" : isActive ? "▶" : "○";
    const label = s.stepId
      ? `<button class="link-button" type="button" data-step-id="${esc(s.stepId)}">${esc(s.label)}</button>`
      : esc(s.label);
    parts.push(
      `<div class="${cls}"><span class="step-icon">${icon}</span>${label}</div>`,
    );
  });
  return `<div class="spending-workflow-banner">${parts.join("")}</div>`;
}
const SUGGESTED_NEXT = {
  household_people: "income_work",
  income_work: "income_retirement",
  income_retirement: "holdings",
  holdings: "assets_home_cash",
  assets_home_cash: "spending_core",
  spending_core: "reports_and_review",
  distribution_strategy: "state_residency",
  state_residency: "reports_and_review",
  lifestyle_spending: "ytd_transactions",
  ytd_transactions: "reports_and_review",
};
function suggestedNext(stepId) {
  const nextId = SUGGESTED_NEXT[stepId];
  const st = STEPS.find((s) => s.id === nextId);
  if (!st) return "";
  return `<div class="suggested-next">Suggested next: <button class="link-button" type="button" data-step-id="${esc(st.id)}">${esc(st.title)} →</button></div>`;
}
function pageStatusHtml(stepId) {
  const st = stepStats(stepId);
  if (!planLoaded)
    return '<span class="page-status not-started">○ Not Started</span>';
  if (st.missing && st.missing.length)
    return `<span class="page-status needs-work">● Needs ${st.missing.length}</span>`;
  if (st.dirty && st.dirty.length)
    return '<span class="page-status in-progress">● Edited</span>';
  if (st.required && st.required.length)
    return '<span class="page-status complete">✓ Complete</span>';
  return '<span class="page-status in-progress">● Has Data</span>';
}
function primaryActionForStep(stepId) {
  if (stepId === "reports_and_review") return "";
  if (stepId === "planning_workbench")
    return `<button class="btn primary" type="button" onclick="planningCaseCreate('manual')">Save Case</button>`;
  if (hasUnsavedPlanChanges())
    return '<button class="btn primary" type="button" onclick="saveAll(true)">Save Changes</button>';
  return '<button class="btn" type="button" data-step-id="reports_and_review">Review Reports</button>';
}
// #285: preserve focus (and, when safe, selection) across the innerHTML
// replace that renderMain() performs below. This is a GENERAL fix, not a
// Workbook-Formatting-only patch: every field in this app that autosaves on
// change and then calls renderMain() synchronously (there are many --
// Holdings' account filter, several spending/YTD fields, workbook column
// widths...) has the same trap armed, since `#mainPane.innerHTML = content`
// destroys and rebuilds every node in the pane, including whatever was just
// focused. Any element that wants to survive a re-render opts in with a
// stable `data-focus-key` attribute; nothing else is touched. This must be a
// no-op -- never steal focus somewhere the user did not ask for -- when
// nothing was focused inside #mainPane, when the focused node has no
// data-focus-key, or when that key does not resolve to anything after the
// render.
let renderMain = function() {
  renderSteps();
  renderMeta();
  updateUnsaved();
  if (
    (!planLoaded &&
      ![
        "detailed_results",
        "system_configuration",
        "planning_workbench",
        "reports_and_review",
      ].includes(activeStep)) ||
    activeStep === "start"
  ) {
    document.getElementById("mainPane").innerHTML = renderWelcome();
    setAppControls(appReady);
    showStepHelp("start");
    return;
  }
  const st = STEPS.find((s) => s.id === activeStep) || STEPS[0];
  const _stIdx = visibleSteps().findIndex((x) => x.id === st.id) + 1;
  const _eyebrow = ["Reports", "Reports & Review", "Settings"].includes(
    st.group,
  )
    ? st.group
    : st.group === null
      ? "Compare & Decide"
      : `Step ${_stIdx} of ${visibleSteps().length}`;
  let content = `<div class="pane-head"><div class="eyebrow">${_eyebrow}</div><div class="page-title-row"><h2>${esc(st.title)}</h2>${pageStatusHtml(st.id)}</div><p>${esc(addParentheticals(st.intro))}</p>${pageSaveModeHtml(st.id)}<div class="pane-actions"><button class="btn" type="button" data-step-id="planning_workbench">Compare & Decide</button>${primaryActionForStep(st.id)}`;
  if (st.id === "review")
    content += `<button class="btn good" data-requires-app="1" onclick="downloadWithBuild('/api/xlsx','Workbook')">Download Workbook</button>`;
  content += `</div></div><div class="question"><b>${esc(st.desc)}</b>${esc(st.help)}${stepHelpLinkHtml(st)}</div>`;
  content += inactiveValuesPanel(activeStep);
  content += pageRecommendationsHtml(activeStep);
  if (SPENDING_WORKFLOW_INDEX[activeStep] !== undefined) {
    content += renderSpendingWorkflowBanner(activeStep);
  }
  if (activeStep === "start") content += renderWelcome();
  else if (activeStep === "spending_core")
    content += window.renderSpendingWorkspace(STRATEGY_TABS.spending_core);
  else if (activeStep === "lifestyle_spending")
    content += renderLifestyleSpending();
  else if (activeStep === "spending_travel")
    content += renderTravelBudgetPage();
  else if (activeStep === "spending_travel_extras")
    content += renderLargeDiscretionaryBudgetPage();
  else if (activeStep === "spending_setup") content += renderSpendingSetup();
  else if (activeStep === "ytd_transactions")
    content += renderYtdTransactionsStep();
  else if (activeStep === "spending_dashboard")
    content += renderSpendingDashboardOrLoad();
  else if (activeStep === "income_work") content += renderIncomeWork();
  else if (activeStep === "income_retirement")
    content += renderRetirementIncome();
  else if (activeStep === "retirement_wellness")
    content += renderRetirementWellness();
  else if (activeStep === "distribution_strategy")
    content += renderDistributionStrategy();
  else if (activeStep === "special_strategies")
    content += renderSpecialStrategies();
  else if (activeStep === "reports_and_review")
    content += renderReportsAndReview();
  else if (activeStep === "scenarios")
    content += analysisFrame(renderScenarios(), "strategy");
  else if (activeStep === "monte_carlo_options")
    content += analysisFrame(renderMonteCarloOptions(), "stress");
  else if (activeStep === "divorce_options")
    content += analysisFrame(renderDivorceOptions(), "stress");
  else if (activeStep === "state_residency")
    content += analysisFrame(renderStateResidency(), "strategy");
  else if (activeStep === "entity_charitable")
    content += analysisFrame(renderEntityCharitable(), "strategy");
  else if (activeStep === "survivor_stress")
    content += analysisFrame(renderSurvivorStress(), "stress");
  else if (activeStep === "ltc_stress")
    content += analysisFrame(renderLtcStress(), "stress");
  else if (activeStep === "holdings") content += renderHoldings();
  else if (activeStep === "spending_mortgage_events")
    content += renderSpendingHousing();
  else if (activeStep === "assets_home_cash")
    content += renderAssetsCashReserves();
  else if (activeStep === "assets_special") content += renderAssetsSpecial();
  else if (activeStep === "estate") content += renderEstateWithAnnuityLink();
  else if (activeStep === "annuity_death_benefits")
    content += renderSpecialIncomeAnnuitiesInsurance();
  else if (activeStep === "withdrawal_strategy")
    content += analysisFrame(renderWithdrawalStrategy(), "strategy");
  else if (activeStep === "roth_conversion")
    content += analysisFrame(renderRothConversion(), "strategy");
  else if (activeStep === "system_configuration")
    content += renderSystemConfiguration();
  else if (activeStep === "workbook_formatting")
    content += renderWorkbookFormatting();
  else if (activeStep === "optional_functions")
    content += renderOptionalFunctions();
  else if (activeStep === "review") content += renderReview();
  else if (activeStep === "allocation_policy")
    content += renderAllocationPolicy();
  else if (activeStep === "allocation_assets")
    content += analysisFrame(renderAllocationRecommendation(), "strategy") + `<details class="decide-embed-sub" open><summary>Allocation policy settings</summary>${renderAllocationPolicy()}</details>`;
  else if (activeStep === "build_impact") content += renderBuildImpactPage();
  else if (activeStep === "planning_workbench")
    content += renderPlanningWorkbench();
  else if (activeStep === "planning_levers") content += renderPlanningLevers();
  else if (activeStep === "detailed_results")
    content += renderDetailedResults();
  else if (activeStep === "plan_data_report") content += renderPlanDataReport();
  else if (activeStep === "household_people" && !searchText.trim())
    content += renderHouseholdPeople();
  else content += renderFields(activeStep);
  if (SPENDING_COMPLETION[activeStep])
    content += spendingFlowFooterHtml(activeStep);
  if (!SPENDING_COMPLETION[activeStep]) content += suggestedNext(activeStep);
  content += renderNav();
  const _dKey = function (d) {
    const dk = d.getAttribute("data-dkey");
    if (dk) return "k:" + dk;
    const b = d.querySelector("summary b");
    if (b) return "b:" + b.textContent.trim();
    const s = d.querySelector("summary");
    return s ? "s:" + s.textContent.trim() : "";
  };
  const _dOpen = {};
  document.querySelectorAll("#mainPane details").forEach(function (d) {
    const k = _dKey(d);
    if (k) _dOpen[k] = d.open;
  });
  // #285: preserve focus (and, when safe, selection) across the innerHTML
  // replace below -- see captureMainPaneFocus/restoreMainPaneFocus above for
  // the guards (no-op when nothing focused, when focus is outside
  // #mainPane, when the node has no data-focus-key, or when the key does
  // not resolve after re-render). Capture must happen BEFORE the innerHTML
  // write and restore AFTER it, synchronously within this call -- no await
  // may be introduced between them.
  const _mainPane = document.getElementById("mainPane");
  const _focusState = captureMainPaneFocus(_mainPane);
  _mainPane.innerHTML = content;
  document.querySelectorAll("#mainPane details").forEach(function (d) {
    const k = _dKey(d);
    if (k && Object.prototype.hasOwnProperty.call(_dOpen, k))
      d.open = _dOpen[k];
  });
  restoreMainPaneFocus(_focusState);
  setAppControls(appReady);
  showStepHelp(activeStep);
};


function wireStepNavigation() {
  return window.RetirementNavigation.wireStepNavigation(navigationContext());
}
function setNavSearch(q) {
  return window.RetirementNavigation.setNavSearch(navigationContext(), q);
}
function updateSearchToggle() {
  return window.RetirementNavigation.updateSearchToggle(navigationContext());
}
function setSearchScope(scope) {
  return window.RetirementNavigation.setSearchScope(navigationContext(), scope);
}
function setCombinedSearch(q) {
  return window.RetirementNavigation.setCombinedSearch(navigationContext(), q);
}
let statusTimer = null;


let showStepHelp = function(id) {
  ensureHelpPanelVisible();
  document.getElementById("helpPanel").innerHTML =
    STEP_HELP[id] || STEP_HELP.start;
};
const FIELD_GUIDANCE_OVERRIDES = {
  // #220: layman-quality example the user provided verbatim (split across
  // purpose/impact/consider) -- the standard to match for every non-intuitive
  // field, not just this one.
  portability_enabled: {
    purpose:
      "Federal estate tax exemption portability lets a surviving spouse add a deceased spouse's unused federal estate tax exemption (the DSUE amount) to their own, so the couple can shield a much larger combined amount from federal estate tax. It is not automatic: the executor must file IRS Form 706, due nine months after death, with an automatic six-month extension available.",
    impact:
      "Portability applies strictly to FEDERAL taxes. Many states with their own estate or inheritance taxes do not recognize portability at the state level, and state exemption thresholds are often much lower than the federal limit. Relying solely on federal portability can trigger high state estate taxes if proper state-level credit shelter or bypass trusts are ignored.",
    consider:
      "Ask: will the executor actually file Form 706 within the deadline? And does this household live in (or plan to retire to) a state with its own estate or inheritance tax? If so, don't rely on this setting alone — a state-level Credit Shelter Trust may still be needed (see that setting for Illinois specifically).",
  },
  monthly_pia_at_fra_today_dollars: {
    purpose:
      "Enter the monthly Social Security payment shown on this person’s SSA statement for claiming at Full Retirement Age, in today’s dollars. This is also called the PIA, or Primary Insurance Amount: Social Security’s base monthly benefit before early-claiming reductions or delayed-retirement credits.",
    impact:
      "This overrides the age-67 (FRA) entry from this person's benefit table as the PIA used for spousal benefit calculations. It can affect annual cash flow, Roth conversion room, Medicare IRMAA exposure, lifetime taxes, survivor income, and terminal net worth.",
    consider:
      "Ask: does the SSA statement show a Full Retirement Age amount that differs from the benefit table's age-67 entry? Enter it here to override; leave it at $0 to use the benefit table's age-67 figure as PIA.",
  },
  annual_premium_base_year: {
    purpose:
      "The current annual cost for one pre-65 person’s healthcare premium before Medicare starts, usually an ACA marketplace, COBRA, or retiree bridge policy.",
    impact:
      "This annual per-person amount is spent while each retired spouse is not yet 65, reduced by any modeled ACA premium tax credit. It also feeds the self-employed health-insurance deduction before age 65; after age 65 the deduction source switches to Medicare Part B/D/G costs. Higher premiums increase withdrawals and can reduce terminal net worth.",
    consider:
      "Ask: what would one pre-65 person actually pay per year before Medicare? Use the current policy quote or marketplace estimate; set to $0 only for a scenario that intentionally removes bridge healthcare premium costs.",
  },
  part_b_base_premium_monthly: {
    purpose:
      "The current monthly Medicare Part B base premium for one Medicare-enrolled person, before any IRMAA surcharge.",
    impact:
      "This amount is spent for each member on Medicare and grows with the medical inflation assumption. IRMAA is modeled separately.",
    consider:
      "Ask: what base Part B premium should each Medicare-enrolled person pay before IRMAA? Use the current standard premium unless the household has a better plan-specific estimate.",
  },
  part_d_base_premium_monthly: {
    purpose:
      "The current monthly Medicare Part D prescription-drug premium for one Medicare-enrolled person, before any IRMAA surcharge.",
    impact:
      "This amount is spent for each member on Medicare and grows with the Part D inflation assumption.",
    consider:
      "Ask: what prescription-drug plan premium should each Medicare-enrolled person expect before IRMAA? Use the known plan premium, or a conservative estimate if the plan is not selected yet.",
  },
  part_g_base_premium_monthly: {
    purpose:
      "The current monthly Medicare Supplement Plan G or similar Medigap premium for one Medicare-enrolled person.",
    impact:
      "This amount is spent for each member on Medicare in addition to Part B and Part D, and grows with medical inflation.",
    consider:
      "Ask: will the household carry Medigap Plan G or similar supplement coverage? Enter the expected monthly premium when yes; enter $0 when no supplement is expected.",
  },
  principal_recovery_age: {
    purpose:
      "The age (of the relevant annuitant) at which the annuity's original principal is treated as fully recovered through payments already made.",
    impact:
      "Before this age, each annuity/pension stream pays its compounding guaranteed payment PLUS a cash dividend (the un-reinvested share of that year's dividend, set by 1 minus Additional Income %). From this age onward the cash dividend stops and only the guaranteed payment continues. This directly changes annual cash flow, taxable income, and the annuity's present value in the Net Worth sheet every year until the switch takes effect.",
    consider:
      "Ask: at what age does the contract or illustration show principal fully paid back? Use the carrier illustration when available; the default (86) applies to every annuity/pension stream unless overridden per-stream.",
  },
  dividend_rate: {
    purpose:
      "The annual rate credited on this annuity's actuarial reserve (derived from its account-value base) each year.",
    impact:
      "Each year's dividend splits in two: the Additional Income % share compounds the guaranteed lifetime payment permanently higher, and the remaining share pays out as cash income on top of the guaranteed payment until Recovery Age. A higher rate raises both pieces every year of the plan.",
    consider:
      "Ask: what dividend/crediting rate does the current carrier illustration show? Leave blank to use the household default (Economic Assumptions > annuity_default_dividend_rate).",
  },
  additional_income_pct: {
    purpose:
      "The share of each year's annuity dividend that is reinvested to permanently raise the guaranteed payment, rather than paid out as cash.",
    impact:
      "This share compounds the guaranteed payment every future year. The remaining share (1 minus this) pays out as cash income each year until Recovery Age, then stops. Applies starting the year of the first payment; before that year the full dividend is reinvested regardless of this setting.",
    consider:
      "Ask: what reinvestment/additional-income split does the illustration show? Leave blank to use the household default (Economic Assumptions > Default Additional Income %).",
  },
  deferral_years: {
    purpose:
      "Contract years before the first payment where the dividend is 100% reinvested and no income is paid yet.",
    impact:
      "During this window the guaranteed payment grows by the Dividend Rate times Deferral Dampening each year instead of being paid out. A longer deferral produces a higher starting guaranteed payment once income begins.",
    consider:
      "Use the number of years between contract purchase and the first-payment date shown on the illustration.",
  },
  deferral_dampening: {
    purpose:
      "Dampens how fast the guaranteed payment grows during the deferral period (growth rate = Dividend Rate times this value, per deferral year).",
    impact:
      "Lower values slow guaranteed-payment growth before income starts; higher values approach full Dividend Rate growth during deferral. Only matters when Deferral Years is greater than zero.",
    consider:
      "Use the value calibrated to the carrier illustration; the model default is 0.55 if left blank.",
  },
  reserve_factor: {
    purpose:
      "The fraction of the account-value base used to anchor the annuity's starting actuarial reserve (starting reserve = base times Reserve Factor).",
    impact:
      "The reserve then follows a fixed decay/mortality-credit/growth curve over the payout years, and that reserve is what the Dividend Rate is credited against each year — so this scales both the compounding guaranteed payment and the cash dividend for the life of the contract.",
    consider:
      "Calibrate to match the carrier illustration's reserve or cash value in the first few contract years; leave blank to use the model default (0.853).",
  },
  exclusion_ratio: {
    purpose:
      "For non-qualified annuities only: the taxable fraction of each payment. The remaining fraction is treated as tax-free return of basis/principal.",
    impact:
      "Lowers reportable taxable income for this stream's payments each year it applies. Has no effect when Qualified is TRUE (qualified/IRA-sourced annuities are always fully taxable).",
    consider:
      "Use the exclusion ratio shown on the annuity's tax illustration (often stated as taxable amount / total payment at a given age).",
  },
  js_pct: {
    purpose:
      "The percentage of a joint pension or annuity payment that continues to the survivor after the first member dies.",
    impact:
      "This affects survivor cash flow, portfolio withdrawals, lifetime taxes, and terminal net worth.",
    consider:
      "Ask: how much of this payment continues after the first death? Use 100% for full continuation, 50% for half continuation, and 0% if the payment ends.",
  },
  type: {
    purpose: "Identifies whether this income stream is Individual or Joint.",
    impact:
      "This helps the workbook and UI explain whether the payment belongs to one person only or may continue to a survivor.",
    consider:
      "Ask: does this payment belong to one person only or continue for a survivor? Choose Joint when survivor continuation exists; choose Individual when it ends with the named person.",
  },
  annual_oop_estimate_today: {
    purpose:
      "The household medical out-of-pocket cap for non-premium medical costs after insurance, such as deductibles, copays, dental, vision, prescriptions, and uncovered services.",
    impact:
      "This field caps non-premium medical expense detail. It is not a standalone expense by itself; higher detail spending up to the cap can raise withdrawals and lower terminal net worth.",
    consider:
      "Use the household annual medical OOP cap as a conservative cap. Enter expected medical costs in the detail categories; do not duplicate them here.",
  },
  value: {
    purpose:
      "The current amount or fair market value for this asset or account.",
    impact:
      "This value affects starting net worth and may affect liquidity, allocation context, estate values, or cash-flow reporting depending on the row.",
    consider:
      "For Cash, this means checking-account cash outside the investment holdings table. For other assets, use today's fair market value.",
  },
  face_value: {
    purpose: "The outstanding principal still owed on the note receivable.",
    impact:
      "This drives projected note principal repayments and net worth until the note is paid off.",
    consider:
      "Use the remaining principal balance, not principal plus future interest.",
  },
  total_cash_flow: {
    purpose:
      "The total cash expected from the note over its remaining payment schedule.",
    impact:
      "This helps explain the note receivable in the workbook but does not replace the year-by-year interest schedule.",
    consider: "Use the total from the note amortization schedule if available.",
  },
  beneficiary: {
    purpose:
      "The person or education goal this 529 plan is intended to support.",
    impact:
      "This label separates education-funding assumptions by beneficiary or goal in the workbook module.",
    consider:
      "Add another 529 section when a different beneficiary or goal should be tracked separately.",
  },
  current_balance: {
    purpose: "The current balance in this 529 education account.",
    impact:
      "This affects the education-funding module and projected amount available for the beneficiary or goal.",
    consider: "Enter today's 529 account balance.",
  },
  annual_contribution: {
    purpose:
      "The amount expected to be added to this 529 each year during the contribution window.",
    impact:
      "This affects projected education funding and any workbook cash-flow reporting for that goal.",
    consider:
      "Enter planned annual contributions only if they should appear in the workbook module.",
  },
  reserve_account: {
    purpose:
      "The account bucket the plan preserves for this cash reserve rule.",
    impact:
      "The withdrawal engine holds this bucket's balance above the reserve while funding annual needs, and draws the other buckets first. An IRA reserve also caps Roth conversions, since converting empties the bucket just as spending it would.",
    consider:
      "Choose Taxable/Trust for brokerage reserves, or a retirement/HSA bucket only if that is the intentional reserve source. Cash accounts are never spent by the withdrawal cascade, so a Cash reserve is already preserved and the setting changes nothing.",
  },
  years_of_expenses: {
    purpose:
      "How many years of spending the plan should try to keep in reserve during this date range.",
    impact:
      "A larger reserve can protect liquidity but may force the model to draw from different accounts sooner.",
    consider: "Use 0 if there is no special reserve requirement.",
  },
  // #219/#220: applying the same layman-quality standard to the app's other
  // genuinely non-intuitive fields, not just the two fields the user gave as
  // examples of the target quality bar.
  social_security_cola: {
    purpose:
      "COLA stands for Cost-of-Living Adjustment — the annual raise Social Security applies to everyone's monthly benefit to keep pace with inflation. This setting is the assumed average COLA percentage used for every future year of the projection, not a promise from the government about any specific year.",
    impact:
      "A higher assumed COLA means Social Security income keeps growing faster relative to fixed spending, which generally helps terminal net worth and success rate; a lower COLA means Social Security's real purchasing power erodes faster over a multi-decade retirement.",
    consider:
      "Historically COLA has averaged a bit under general inflation over long periods. Using the same rate as the general inflation assumption is a reasonable default; only diverge if intentionally testing a scenario where Social Security under- or over-shoots broad inflation.",
  },
  basis_step_up_at_death: {
    purpose:
      "\"Basis\" is what was originally paid for an investment — the number the IRS uses to calculate taxable gain when it's sold. Normally, selling an investment for more than its basis triggers capital gains tax on the difference. When someone dies owning an investment in a regular (non-retirement) taxable account, current law resets — \"steps up\" — that basis to the investment's value on the date of death, erasing the taxable gain that built up during their lifetime.",
    impact:
      "When this is on (the current-law default), the plan assumes the heir who inherits taxable-account holdings owes no capital gains tax on the appreciation that happened before death, only on further growth after they inherit it. Turning it off models a scenario where step-up is unavailable or repealed — heirs would then owe capital gains tax on the full lifetime appreciation when they eventually sell, which raises the effective estate tax burden and lowers what heirs keep.",
    consider:
      "Leave this on to model current law. Only turn it off to stress-test a legislative-risk scenario (step-up has periodically been proposed for repeal or limitation) — don't turn it off just because it sounds conservative, since it would misrepresent today's actual tax rules.",
  },
  tax_loss_harvesting: {
    purpose:
      "Tax-loss harvesting means deliberately selling an investment that's currently worth less than what was paid for it, to realize (\"harvest\") a capital loss on paper — that loss can then offset capital gains elsewhere, and up to $3,000/year of any leftover loss can offset ordinary income. This toggle turns on a dedicated workbook sheet modeling that strategy.",
    impact:
      "When enabled, the projection assumes available paper losses are periodically harvested and used to reduce taxable gains/income, which can meaningfully lower lifetime taxes for a household with taxable-account holdings that fluctuate in value. It has no effect on tax-deferred or Roth accounts, since those aren't taxed on individual sales.",
    consider:
      "Only enable this if the household (or advisor) actually intends to harvest losses opportunistically — the model isn't assuming a specific market downturn, it's assuming a disciplined ongoing practice. Leave it off if this isn't part of the actual investment approach, since it would otherwise overstate expected tax savings.",
  },
  heloc_enabled: {
    purpose:
      "HELOC stands for Home Equity Line of Credit — a revolving credit line secured by the home, similar to a credit card but usually at a lower interest rate because the house backs it. This setting turns on a strategy where the plan draws from that credit line to cover large one-time discretionary expenses (vacations, weddings, home projects) instead of selling investments to pay for them.",
    impact:
      "When enabled, large discretionary spending is funded by HELOC draws during the draw period (configured below) instead of portfolio withdrawals, keeping invested assets untouched and compounding longer. The line accrues interest and is assumed to be repaid later, typically from home-sale proceeds — so this trades borrowing cost and reduced home equity at sale against the extra investment growth from not selling assets early.",
    consider:
      "This tends to help when portfolio growth outpaces the HELOC's interest cost; it tends to hurt when the interest rate is high or the home isn't expected to sell (or sells for less than expected) before the balance needs repaying. Model it both on and off and compare terminal net worth before committing to the strategy.",
  },
  holding_period_floor_strength: {
    purpose:
      "This is the \"strength dial\" mentioned in the Holding Period Allocation Enabled setting — it only does anything when that setting is turned on. It controls how firmly the near-term-needs-more-cash / long-horizon-needs-more-stocks adjustment is applied to the recommended allocation.",
    impact:
      "100% applies the full adjustment the withdrawal-timeline analysis calculates; 0% effectively disables the adjustment (allocation falls back to whatever the base optimizer/max-Sharpe mode would have recommended without it) without having to turn the feature off entirely. Values in between blend proportionally.",
    consider:
      "Start at 100% to see the full effect, then dial it down only if the resulting allocation shift feels too aggressive relative to comfort with the recommendation.",
  },
  success_liquid_floor: {
    purpose:
      "In each simulated year of a Monte Carlo run, this is the minimum dollar amount of liquid (spendable) assets the plan must still have on hand for that simulated path to count as a \"success.\" It's a stricter bar than simply not running out of money entirely — it treats getting dangerously close to zero as a failure too, even if the balance never technically hits $0.",
    impact:
      "Raising this floor makes the success rate more conservative (harder to pass) because paths that would have survived on paper but dipped uncomfortably low now count as failures. Setting it to $0 is the loosest standard — a plan only \"fails\" a simulated year if it truly runs out of money.",
    consider:
      "A floor of $0 answers \"will I ever go broke?\" A floor set to, say, one year of spending answers the more cautious question \"will I ever be down to my last few months of cushion?\" Pick the floor that matches how much of a buffer actually needs to feel safe.",
  },
  stochastic_irmaa: {
    purpose:
      "IRMAA is the Medicare income surcharge — higher-income retirees pay more for Medicare Part B/D based on income from two years earlier. The dollar thresholds that trigger each surcharge tier are set annually and, in real life, jump around a bit with inflation rather than growing on a perfectly smooth line. This setting tells the Monte Carlo simulation to add small random year-to-year noise to those thresholds instead of assuming they grow at a perfectly steady rate.",
    impact:
      "Turning this on makes IRMAA outcomes across simulated trials more realistic and slightly more variable — some simulated years will cross a surcharge tier a little earlier or later than a smooth-inflation assumption would suggest, which is closer to how thresholds actually move in practice. Turning it off simplifies the model to steady, predictable threshold growth.",
    consider:
      "Leave this on for a more realistic Monte Carlo distribution of IRMAA risk. There's little reason to turn it off other than isolating IRMAA's effect while debugging or comparing runs.",
  },
  return_inflation_correlation: {
    purpose:
      "\"Correlation\" measures how two things tend to move together, from -1 (perfectly opposite) to +1 (perfectly in lockstep). This setting tells the Monte Carlo simulator how market returns and inflation surprises tend to move relative to each other historically — a negative number (like the default) means that when inflation runs unexpectedly hot, market returns have historically tended to run a bit weaker in the same period, and vice versa.",
    impact:
      "This shapes how often the simulator generates the worst combination for a retiree — simultaneously bad markets and high inflation — in the same simulated year. A more negative correlation makes that painful combination somewhat less likely to occur together (since the model expects them to offset); a value near zero treats market returns and inflation as unrelated from year to year.",
    consider:
      "This is a capital-markets assumption, not a personal input — leave it at the research-informed default unless there's a specific reason (e.g. matching a particular economist's outlook or stress-testing sensitivity to this relationship) to override it.",
  },
  return_serial_correlation: {
    purpose:
      "\"Serial\" correlation (also called AR(1), or first-order autocorrelation) measures whether one year's market return tends to predict the next year's — for example, whether strong years tend to be followed by more strong years (momentum, positive serial correlation) or by weaker ones (mean-reversion, negative serial correlation). This setting controls how much of that year-to-year dependence the simulator builds into randomly generated returns, instead of treating every year as a completely independent coin flip.",
    impact:
      "A higher value makes simulated return sequences more likely to string together multi-year runs of good or bad markets (which is closer to some historical patterns and can produce more extreme best/worst-case outcomes); a value of 0 treats every simulated year's return as unrelated to the year before it.",
    consider:
      "This is a capital-markets assumption, not a personal input — leave it at the research-informed default unless intentionally testing sensitivity to how \"streaky\" markets are assumed to be.",
  },
  niit_magi_threshold_mfj: {
    purpose:
      "NIIT stands for Net Investment Income Tax — an extra 3.8% federal tax on investment income (interest, dividends, capital gains, rental income) for higher earners, on top of regular income tax. This is the Modified Adjusted Gross Income level, for a married-filing-jointly household, above which that extra 3.8% tax kicks in on investment income.",
    impact:
      "Income (including Roth conversions, which count as ordinary income) that pushes MAGI over this line causes investment income above the line to be taxed an additional 3.8% — this is one of the \"cliffs\" the Roth conversion optimizer already guards against when its NIIT cap is enabled.",
    consider:
      "This threshold is set by federal law and is NOT annually inflation-adjusted (unlike most tax brackets) — it's a fixed dollar figure until Congress changes it. Only edit this if federal law actually changes the threshold; don't inflate it year-to-year the way other tax parameters are.",
  },
  glide_path: {
    purpose:
      "A \"glide path\" is how a portfolio's stock/bond mix is allowed to change over time. \"Static\" keeps the allocation strategy fixed throughout retirement (same target logic every year). \"Target_date\" instead gradually shifts the mix to be more conservative (more bonds, less stock) as the household gets closer to and further into retirement — the same idea behind a target-date retirement fund.",
    impact:
      "Static is simpler and more predictable but doesn't automatically reduce risk with age. Target_date automatically de-risks over time, which can reduce sequence-of-returns risk late in retirement but also means less growth potential is retained in later years even if that growth would have been welcome.",
    consider:
      "Target_date is a reasonable default for households who want the model to automatically get more conservative with age without manually adjusting risk tolerance settings over time. Static suits households who prefer to make that call deliberately themselves.",
  },
  roth_irmaa_cap: {
    purpose:
      "This turns on a guardrail that stops the Roth conversion optimizer from converting so much in one year that it pushes the household's income across an IRMAA tier line (the income levels above which Medicare premiums jump to a higher surcharge bracket).",
    impact:
      "When enabled, the optimizer treats the IRMAA tier selected below (Target Tier) as a soft ceiling on voluntary conversions in years where crossing it would trigger a higher Medicare premium surcharge — trading some conversion size/tax-bracket-fill efficiency for lower ongoing Medicare costs. When disabled, conversions are sized purely by the tax-bracket target, ignoring any resulting IRMAA surcharge.",
    consider:
      "Leave this on for most households — an unplanned IRMAA surcharge from a large conversion year can be expensive and lasts for a full plan year based on income from two years earlier. Only disable it if intentionally testing an aggressive, IRMAA-indifferent conversion strategy.",
  },
  roth_irmaa_target_tier: {
    purpose:
      "IRMAA has multiple income tiers (Tier 1 through Tier 5), each with a higher Medicare Part B/D surcharge than the last. This setting picks which tier's income threshold the Roth conversion guardrail (above) treats as the line not to cross.",
    impact:
      "A lower tier (e.g. Tier 1) is more conservative — it keeps voluntary conversions smaller so income stays further below any Medicare surcharge threshold. A higher tier (e.g. Tier 4 or 5) allows larger conversions before the guardrail engages, accepting a higher Medicare premium tier as the cost of converting more.",
    consider:
      "Tier 2 is a common middle-ground default. Choose a lower tier when minimizing Medicare premiums matters more than maximizing how much gets converted; choose a higher tier when using up low tax brackets or reducing future RMDs matters more than the Medicare cost.",
  },
  roth_irmaa_headroom_usage_pct: {
    purpose:
      "\"Headroom\" is the gap between the household's current projected income and the IRMAA tier threshold selected above — the dollar amount of room left before crossing into a higher Medicare surcharge tier. This percentage controls how much of that available room the optimizer is willing to actually use for voluntary conversions.",
    impact:
      "100% lets the optimizer convert right up to the edge of the threshold. A lower percentage (e.g. 90%) leaves a safety cushion below the threshold, reducing the chance that a small income estimate error accidentally tips the household into the next IRMAA tier.",
    consider:
      "100% maximizes conversion room but leaves no margin for estimation error in other income sources. A slightly lower value (90-95%) is a reasonable way to build in a buffer without meaningfully reducing conversion opportunity.",
  },
  qcd_enabled: {
    purpose:
      "QCD stands for Qualified Charitable Distribution — once a person is age 70½ or older, they can send money directly from their own IRA to a qualifying charity, and that amount is excluded from taxable income entirely (unlike a normal IRA withdrawal, or even a regular charitable deduction which only helps if itemizing). This turns the strategy on for the household.",
    impact:
      "When enabled, each eligible member's QCD amount (set per-person below) is excluded from Adjusted Gross Income and can also count toward satisfying that year's Required Minimum Distribution — often lowering taxable income, Medicare IRMAA exposure, and NIIT exposure more than an equivalent charitable deduction would.",
    consider:
      "This is one of the most tax-efficient ways to give to charity once RMD-eligible — turn it on if charitable giving is already part of the plan and at least one member is or will be 70½+. It has no benefit for households that don't give to charity from IRA assets.",
  },
  daf_annual_contribution: {
    purpose:
      "DAF stands for Donor-Advised Fund — money (or appreciated securities) contributed to a DAF gets an immediate charitable tax deduction in the year contributed, even though the actual grants to specific charities can be decided and paid out over many future years. It's a way to \"bunch\" several years of giving into one high-income year for a bigger deduction, while still spreading the actual gifts out over time.",
    impact:
      "This annual dollar amount is modeled as a charitable contribution (and tax deduction) in the year it's made, funded from ongoing spending/cash flow rather than from an IRA (that's what QCD is for). It reduces taxable income in the contribution year and grows the household's outside-the-estate giving capacity for future years.",
    consider:
      "DAFs are most tax-efficient when contributed in an unusually high-income year (e.g. a big Roth conversion year or a business-sale year) since the deduction is worth more against a higher marginal rate. If giving is steady and modest, a DAF adds complexity without much extra benefit over direct annual gifts.",
  },
  ss_benefit_age_62: {
    purpose: "This is the estimated monthly Social Security benefit amount the Social Security Administration projects for you at a specific claiming age. These come from your official Social Security statement and show the dollar value of claiming at each age.",
    impact: "Estimates rise with each later claiming age, showing the delayed retirement credit — waiting from 62 to 70 typically pays roughly 76% more per month. The plan uses these estimates to model cash flow, tax situations, and longevity scenarios.",
    consider: "Get your official Social Security statement from ssa.gov if you don't have one — it's much more accurate than rules of thumb and takes just a few minutes.",
  },
  ss_benefit_age_63: {
    purpose: "This is the estimated monthly Social Security benefit amount the Social Security Administration projects for you at a specific claiming age. These come from your official Social Security statement and show the dollar value of claiming at each age.",
    impact: "Estimates rise with each later claiming age, showing the delayed retirement credit — waiting from 62 to 70 typically pays roughly 76% more per month. The plan uses these estimates to model cash flow, tax situations, and longevity scenarios.",
    consider: "Get your official Social Security statement from ssa.gov if you don't have one — it's much more accurate than rules of thumb and takes just a few minutes.",
  },
  ss_benefit_age_64: {
    purpose: "This is the estimated monthly Social Security benefit amount the Social Security Administration projects for you at a specific claiming age. These come from your official Social Security statement and show the dollar value of claiming at each age.",
    impact: "Estimates rise with each later claiming age, showing the delayed retirement credit — waiting from 62 to 70 typically pays roughly 76% more per month. The plan uses these estimates to model cash flow, tax situations, and longevity scenarios.",
    consider: "Get your official Social Security statement from ssa.gov if you don't have one — it's much more accurate than rules of thumb and takes just a few minutes.",
  },
  ss_benefit_age_65: {
    purpose: "This is the estimated monthly Social Security benefit amount the Social Security Administration projects for you at a specific claiming age. These come from your official Social Security statement and show the dollar value of claiming at each age.",
    impact: "Estimates rise with each later claiming age, showing the delayed retirement credit — waiting from 62 to 70 typically pays roughly 76% more per month. The plan uses these estimates to model cash flow, tax situations, and longevity scenarios.",
    consider: "Get your official Social Security statement from ssa.gov if you don't have one — it's much more accurate than rules of thumb and takes just a few minutes.",
  },
  ss_benefit_age_66: {
    purpose: "This is the estimated monthly Social Security benefit amount the Social Security Administration projects for you at a specific claiming age. These come from your official Social Security statement and show the dollar value of claiming at each age.",
    impact: "Estimates rise with each later claiming age, showing the delayed retirement credit — waiting from 62 to 70 typically pays roughly 76% more per month. The plan uses these estimates to model cash flow, tax situations, and longevity scenarios.",
    consider: "Get your official Social Security statement from ssa.gov if you don't have one — it's much more accurate than rules of thumb and takes just a few minutes.",
  },
  ss_benefit_age_67: {
    purpose: "This is the estimated monthly Social Security benefit amount the Social Security Administration projects for you at a specific claiming age. These come from your official Social Security statement and show the dollar value of claiming at each age.",
    impact: "Estimates rise with each later claiming age, showing the delayed retirement credit — waiting from 62 to 70 typically pays roughly 76% more per month. The plan uses these estimates to model cash flow, tax situations, and longevity scenarios.",
    consider: "Get your official Social Security statement from ssa.gov if you don't have one — it's much more accurate than rules of thumb and takes just a few minutes.",
  },
  ss_benefit_age_68: {
    purpose: "This is the estimated monthly Social Security benefit amount the Social Security Administration projects for you at a specific claiming age. These come from your official Social Security statement and show the dollar value of claiming at each age.",
    impact: "Estimates rise with each later claiming age, showing the delayed retirement credit — waiting from 62 to 70 typically pays roughly 76% more per month. The plan uses these estimates to model cash flow, tax situations, and longevity scenarios.",
    consider: "Get your official Social Security statement from ssa.gov if you don't have one — it's much more accurate than rules of thumb and takes just a few minutes.",
  },
  ss_benefit_age_69: {
    purpose: "This is the estimated monthly Social Security benefit amount the Social Security Administration projects for you at a specific claiming age. These come from your official Social Security statement and show the dollar value of claiming at each age.",
    impact: "Estimates rise with each later claiming age, showing the delayed retirement credit — waiting from 62 to 70 typically pays roughly 76% more per month. The plan uses these estimates to model cash flow, tax situations, and longevity scenarios.",
    consider: "Get your official Social Security statement from ssa.gov if you don't have one — it's much more accurate than rules of thumb and takes just a few minutes.",
  },
  ss_benefit_age_70: {
    purpose: "This is the estimated monthly Social Security benefit amount the Social Security Administration projects for you at a specific claiming age. These come from your official Social Security statement and show the dollar value of claiming at each age.",
    impact: "Estimates rise with each later claiming age, showing the delayed retirement credit — waiting from 62 to 70 typically pays roughly 76% more per month. The plan uses these estimates to model cash flow, tax situations, and longevity scenarios.",
    consider: "Get your official Social Security statement from ssa.gov if you don't have one — it's much more accurate than rules of thumb and takes just a few minutes.",
  },
  reinvest_dividends: {
    purpose: "Whether dividend payments from this account's investments are automatically reinvested back into the account, or if you want to withdraw them as cash. You can override the household default here for just this one account.",
    impact: "When enabled, dividends are reinvested to compound and grow your balance faster; when disabled, dividends are paid out as cash, slowing growth but giving you cash to spend.",
    consider: "Leave this on for retirement accounts where you won't need the cash, since reinvested dividends grow tax-efficiently. Turn it off only if you need the cash flow.",
  },
  contingent_beneficiary: {
    purpose: "The person (or institution) named to inherit this account if the primary beneficiary passes away before or at the same time as you. It's your backup plan.",
    impact: "If your primary beneficiary is no longer living when you die, this person receives the account instead, keeping it out of your estate and speeding the transfer to your chosen heir.",
    consider: "Name someone you trust and update it when life changes happen — births, deaths, marriages, or changes in relationships.",
  },
  primary_beneficiary: {
    purpose: "The person (or institution) named to inherit this account when you die. This person receives it directly, outside your will.",
    impact: "Your named beneficiary gets the account immediately at your death, bypassing probate. Without a named beneficiary, the account becomes part of your estate and is distributed by your will or state law, which takes longer.",
    consider: "Use a specific person's name and keep it current — review after marriage, divorce, or the birth of children.",
  },
  titling: {
    purpose: "The legal ownership structure of the account — whether it's in your name alone, jointly with someone else, held in a trust, or set up with a transfer-on-death arrangement. This determines who owns it, who can access it, and how it passes when you die.",
    impact: "Different titling structures change whether heirs get a tax 'step-up' (reset to current value at death), who can withdraw money while alive, and how quickly the account passes to heirs. Joint ownership means the survivor inherits directly; individual ownership passes through your will or estate.",
    consider: "Review your account titles with a tax or estate lawyer — the right structure can save heirs thousands in taxes.",
  },
  trust_see_through: {
    purpose: "Marks whether a trust you've named as beneficiary qualifies as a 'see-through trust' under tax law, which allows heirs to spread Required Minimum Distributions over a longer period and pay less tax.",
    impact: "A qualifying see-through trust lets heirs take smaller, tax-efficient withdrawals; a trust that doesn't qualify may force larger annual withdrawals and higher taxes.",
    consider: "If you're naming a trust as a beneficiary, ask your estate attorney to confirm it meets see-through requirements.",
  },
  holding_period_allocation_enabled: {
    purpose: "When turned on, the plan automatically adjusts how much of your portfolio is in safe, stable investments versus growth investments based on when you expect to spend the money.",
    impact: "This approach keeps money you'll need soon in safer assets (reducing the risk of a market crash right when you need it) while keeping longer-term money invested for growth. Without it, your portfolio mix stays the same regardless of your spending timeline.",
    consider: "Turn this on if your spending needs vary a lot over retirement and you want the plan to automatically protect near-term cash.",
  },
  real_loss_aware_risk_aversion: {
    purpose: "A number that controls how strongly the plan avoids portfolio losses when using real-loss-aware optimization mode. Higher numbers make the recommended portfolio more conservative.",
    impact: "Raising this value steers recommendations toward safer investments; lowering it allows more risk in search of higher returns.",
    consider: "Adjust this if the recommended portfolio feels too risky or too timid compared to your own comfort with short-term losses.",
  },
  real_loss_aware_weight: {
    purpose: "A number that controls how much weight the optimizer gives to avoiding real-world losses (like a market crash when you need to withdraw money) versus maximizing average returns.",
    impact: "Higher values prioritize loss protection over return growth; lower values give more weight to growth potential even if it means more risk.",
    consider: "Use higher values if you're worried about bad timing between market downturns and large spending needs.",
  },
  target_pct: {
    purpose: "The percentage of your portfolio you want to hold in a specific investment type, such as U.S. large-cap stocks, international stocks, bonds, or cash. All these percentages should add up to 100%.",
    impact: "Increasing a percentage increases your exposure to that type of investment and its risks and potential returns; decreasing it shifts your portfolio toward other types.",
    consider: "Start with the suggested allocation that matches your age and risk tolerance, then adjust individual categories only if you have a specific reason.",
  },
  capital_market_assumption_horizon_source: {
    purpose: "Whether the plan uses a fixed investment time horizon for its return forecasts, or whether it calculates the horizon based on when you actually expect to withdraw money.",
    impact: "Using a fixed horizon gives consistent, predictable assumptions; using your actual withdrawal timeline customizes the forecast to your specific needs.",
    consider: "Use the automatic calculation if your spending is uneven over retirement; use manual if you prefer simplicity.",
  },
  capital_market_assumption_horizon_years: {
    purpose: "How many years ahead the plan looks when forecasting what investment returns to expect. Common choices are 1, 3, 5, 10, 20, or 30 years.",
    impact: "A short horizon (1-5 years) assumes lower returns because markets are harder to predict in the near term; a long horizon (20-30 years) assumes higher returns because you can wait out market downturns.",
    consider: "Use a shorter horizon if you need the money soon; use a longer one if you have decades before needing significant withdrawals.",
  },
  capital_market_assumption_preset: {
    purpose: "Chooses whether the plan uses conservative, baseline, or aggressive return and volatility assumptions for different investment types. This shifts all the underlying forecasts at once.",
    impact: "Conservative assumptions show lower expected returns and are more pessimistic; aggressive assumptions show higher returns but more volatility. Baseline splits the difference.",
    consider: "Use conservative if you're nearing retirement or uncomfortable with risk; use aggressive only if you have decades and can tolerate downturns.",
  },
  alternate_asset_class: {
    purpose: "A backup investment type you can specify, in case your preferred investment isn't available or you want to compare a second option.",
    impact: "When you set this and choose 'Consider alternate first,' the optimizer will prefer this alternate if it's a better fit; otherwise your original choice is used.",
    consider: "Use this only if you have access to specific funds you prefer or want to test how a different investment would work.",
  },
  optimizer_override_pct: {
    purpose: "A custom percentage you can enter to override what the optimizer recommends for this investment type. Leave it blank to use the optimizer's suggestion.",
    impact: "Entering a percentage locks in your choice instead of using the optimizer's recommendation, which is helpful if you have a strong conviction about this investment.",
    consider: "Only override the optimizer if you have a specific reason, like coordinating with tax losses in another account. Otherwise, trust the recommendation.",
  },
  selection_action: {
    purpose: "Tells the optimizer what to do with this investment type: include it, exclude it, or consider an alternate first before using this one.",
    impact: "Include adds it to the portfolio; exclude removes it entirely; Consider alternate first tries your backup choice first.",
    consider: "Use exclude to remove investments you don't want; use Consider alternate first if you'd rather have your backup but are open to the original if needed.",
  },
  buy_sell_type: {
    purpose: "The type of buy-sell agreement for your business — cross-purchase means the other owners buy your share, entity-redemption means the business itself buys your share, and wait-and-see means no predetermined plan.",
    impact: "Cross-purchase and entity-redemption have different tax and cash-flow effects on the remaining owners and your heirs. Wait-and-see leaves the details uncertain.",
    consider: "Discuss with a business lawyer and accountant to pick the structure that makes sense for your business and situation.",
  },
  entity_name: {
    purpose: "The legal name of the business or entity you're documenting for succession planning.",
    impact: "This is for reference and record-keeping only. It doesn't affect the plan's calculations unless the business sale is specifically enabled.",
    consider: "Use the official business name registered with your state to keep your plan clear and organized.",
  },
  funding_amount: {
    purpose: "The amount of money you've set aside, insured, or earmarked to pay for a buy-sell agreement if an owner dies. This is usually funded through life insurance.",
    impact: "Higher funding means more money is available to pay for the buyout. Underfunding means the remaining owners or business may not have enough cash to complete the purchase.",
    consider: "Review this amount regularly with your insurance agent and lawyer to make sure it keeps pace with your business's current value.",
  },
  funding_vehicle: {
    purpose: "The method used to fund a buy-sell agreement — usually life insurance (proceeds from a policy at death), an installment note (the buyer pays over time), a sinking fund (money set aside now), or not yet funded.",
    impact: "Life insurance is the fastest and most reliable method because money is available immediately. Other methods may require the buyer to borrow or take years to pay.",
    consider: "Life insurance is the most practical choice because the proceeds arrive when you need them most.",
  },
  key_person_coverage: {
    purpose: "Key-person life insurance is a policy the business buys on the owner to protect itself if the owner dies. The payout helps cover the cost of finding and training a replacement, paying off business debt, or keeping the lights on until a successor can take over.",
    impact: "Raising the coverage amount increases the insurance protection and the annual cost to the business. Lowering it reduces cost but leaves the business more vulnerable if the owner passes suddenly.",
    consider: "Estimate how many months it would take to replace the owner and train a successor, plus any business debt tied to the owner's creditworthiness — that dollar amount is roughly what to insure.",
  },
  owner: {
    purpose: "This identifies which person owns the business or holds the account in question. The same label may appear across several different sections to mark ownership in each area.",
    impact: "Changing the owner reassigns income, taxes, and account value to a different person — which affects that person's tax bracket, benefit eligibility, and net worth.",
    consider: "Make sure this matches your actual ownership documents and tax filings. If ownership is shared, the system usually expects one primary owner to be named.",
  },
  ownership_pct: {
    purpose: "This is the percentage of the business one owner holds — for example, 60% or 40%. In a succession or sale, it determines how much of the business value belongs to each owner.",
    impact: "Raising ownership percentage increases that person's share of business value and their eventual proceeds from a sale or handoff. Lowering it reduces their stake.",
    consider: "All ownership percentages must add up to 100% across all owners. Make sure the percentages match how the business is actually structured and how profits are split.",
  },
  successor: {
    purpose: "This is the name of the person or organization intended to take over the business — a family member, trusted employee, outside buyer, or other buyer. It helps the plan model the succession.",
    impact: "Changing the successor itself doesn't affect the plan's numbers directly, but different successors may bring different assumptions about timing, financing, or sale price.",
    consider: "Write down who you'd ideally want to take over. If they don't have the skills or funding yet, the plan can help you think through the steps to prepare them.",
  },
  valuation_growth_rate: {
    purpose: "This is how fast the business value is expected to grow each year, as a percentage — for example, 3% per year. It forecasts the business's worth in future years.",
    impact: "A higher growth rate means the business is worth more at succession or sale time, increasing the owner's eventual payout. A lower rate means slower growth and a smaller eventual payout.",
    consider: "Use realistic growth for your industry and business stage — startups might grow 15%+ per year, but mature stable businesses typically grow 2-5% per year. Research similar businesses in your field.",
  },
  valuation_today: {
    purpose: "This is the fair market value of the business right now, in today's dollars. It's the starting point for forecasting what the business will be worth in the future.",
    impact: "A higher starting value multiplies through all future growth forecasts, significantly increasing the projected succession or sale payout. This is often the biggest lever in succession planning.",
    consider: "Get a professional business appraisal if you can. Otherwise, ask a business broker in your field what similar-sized businesses sell for. Don't guess.",
  },
  valuation_growth_default: {
    purpose: "This is a fallback growth rate applied to any business that doesn't have its own specific rate set. It's a system-wide default so you don't repeat the same number for every business.",
    impact: "Raising this default makes all businesses grow faster (unless overridden). Lowering it makes them all grow slower. It affects every business forecast that doesn't have a custom rate.",
    consider: "Set this to a realistic long-term business growth rate — typically 3-5% per year — so the plan doesn't make wild guesses. Individual businesses can always override it with their own rate.",
  },
  annual_earned_income: {
    purpose: "This is the gross income from a job or self-employment in the first year specified — usually the current year. It's the starting point for projecting future earnings.",
    impact: "Raising this amount means higher income in that first year and (usually) higher income in future years. Lowering it projects a smaller salary or business income.",
    consider: "Use your actual year-to-date income if we're partway through the year. If starting from a prior year, use the actual gross income before taxes and deductions.",
  },
  earned_income_annual_increase: {
    purpose: "This is how fast earned income is expected to grow each year, as a percentage — for example, 3% per year, or 0% if income is flat.",
    impact: "A higher growth rate means income rises faster each year, increasing the amount available for spending, saving, and taxes. A lower rate leaves less room in the budget.",
    consider: "Use your actual raise history or the long-term wage growth for your field — many people use 2-3% per year. Use 0% if your salary is fixed.",
  },
  earned_income_last_year: {
    purpose: "This is the final year earned income is expected — usually when you plan to retire. After this year, the income stops.",
    impact: "Moving this year earlier stops income sooner, leaving fewer years to save and more years to live off existing assets. Moving it later extends income, which typically improves retirement security.",
    consider: "Use your planned retirement year. If you're unsure, test the plan with retirement 2 years earlier and 2 years later to see the impact.",
  },
  earned_income_start_year: {
    purpose: "This is the first year earned income is expected in the plan — usually the current year, or the year a job or business starts. Before this year, income is zero.",
    impact: "Moving this year earlier extends the earning window and saves more. Moving it later delays income, reducing savings time.",
    consider: "Use the current year, or the year you expect income to begin if it's in the future.",
  },
  entity_type: {
    purpose: "This is the legal structure of the income — whether you're a W2 employee (no self-employment tax), a sole proprietor (self-employed without a separate business entity), or an S-Corp (a special structure that can reduce self-employment taxes).",
    impact: "S-Corp income typically has lower taxes than sole proprietor income because of different self-employment tax treatment. W2 income has no self-employment tax. Changing this affects how much you owe in taxes on the same gross income.",
    consider: "Make sure this matches your actual tax filings. If you're considering an S-Corp, talk to a tax professional — the wrong choice can lead to bad tax projections and costly compliance mistakes.",
  },
  ytd_remainder_earned_income_override: {
    purpose: "This optional field lets you override the plan's estimate for rest-of-year earned income. Normally, the plan assumes income grows evenly across the whole year. Use this if you know the remainder won't be average — for example, a big bonus coming, or reduced hours.",
    impact: "Raising this amount projects more income for the rest of this year than a linear estimate would. Lowering it projects less. This affects only this year's total, not future years.",
    consider: "Use this only if you have clear information about the rest of this year's actual income. If unsure, leave it blank.",
  },
  annual_real_estate_taxes: {
    purpose: "This is your annual property tax bill — the tax you pay to your county or municipality based on your home's assessed value. Instead of being mixed into everyday spending, it's shown separately alongside your mortgage.",
    impact: "Raising this amount increases your total annual housing costs; lowering it reduces them. The plan uses this to forecast how much cash you'll need each year.",
    consider: "Check your property tax bill or your county assessor's website for the actual amount; it's usually stated on your annual tax statement or mortgage statement.",
  },
  balance_as_of_plan_start: {
    purpose: "This is how much you still owe on your mortgage as of the start of your plan — the principal balance remaining, not including interest.",
    impact: "This starting point determines how much principal you pay down each year and when the mortgage will be fully paid off.",
    consider: "Look at your most recent mortgage statement or call your lender to find the current balance.",
  },
  interest_rate: {
    purpose: "This is the annual interest rate on your mortgage — the percentage you pay to the lender on top of the principal you borrowed.",
    impact: "A higher rate means more of each payment goes to interest instead of building equity; a lower rate means faster equity growth and lower total interest paid.",
    consider: "Find this on your mortgage statement or loan document; it's usually between 3% and 8% depending on when you borrowed and current market rates.",
  },
  last_payment_date: {
    purpose: "This is the date you'll make your final mortgage payment and own the home free and clear.",
    impact: "The plan calculates whether you'll pay off the mortgage before retirement or if the balance will carry into retirement years, affecting your future cash flow.",
    consider: "Check your mortgage paperwork — it usually states your loan's original term (like 30 years) and closing date, so you can calculate when it ends.",
  },
  last_payment_year: {
    purpose: "This is the year when the plan stops assuming you have mortgage payments — the year the loan is completely repaid.",
    impact: "After this year, no more monthly mortgage payments are included in your budget, freeing up that cash for other spending or savings.",
    consider: "This should match the maturity date from your loan documents; if you're refinancing or paying extra principal, adjust it to when you expect to be debt-free.",
  },
  monthly_payment: {
    purpose: "This is the amount you pay each month toward your mortgage — principal and interest combined.",
    impact: "This monthly amount flows into your annual cash-flow plan; raising or lowering it (via extra principal payments or refinancing) changes how much cash you need each year.",
    consider: "This is listed on your mortgage statement; if you have a variable-rate mortgage, use the current payment amount or ask your lender for the rate-adjusted payment.",
  },
  real_estate_tax_annual_adjustment_pct: {
    purpose: "This is the percentage by which property taxes are expected to increase each year — usually following inflation, but sometimes faster or slower depending on your area's assessment practices.",
    impact: "A higher percentage means property taxes grow faster over time, so your future years' cash flow needs are higher; a lower percentage keeps tax growth modest.",
    consider: "Look at your property tax history over three to five years to see the trend; many areas adjust between zero percent (frozen assessments) and three to four percent annually.",
  },
  monthly_rent_post_sale: {
    purpose: "If you plan to sell your home, this is what you expect to pay each month in rent afterward — like moving to an apartment or a rental house after downsizing.",
    impact: "Setting this amount means your plan includes rent expense starting the year you sell the home, replacing your mortgage payment as your main housing cost.",
    consider: "Research typical rent in your planned retirement location; the plan will increase this amount each year with inflation, so enter a realistic starting amount.",
  },
  annual_401k_limit_base_year: {
    purpose: "This is the maximum amount you're allowed to contribute to your 401(k) plan in the starting year, including any extra catch-up contributions if you're age 50 or older.",
    impact: "Raising this helps you save more for retirement with tax-deferred growth; the plan won't let you contribute beyond this legal limit, even if you want to.",
    consider: "The IRS sets this limit annually and increases it for inflation — check the IRS website each year for the current cap.",
  },
  index_401k_limit: {
    purpose: "This setting determines whether your 401(k) contribution limit automatically increases each year to keep up with inflation, or stays at the same dollar amount.",
    impact: "If enabled, your future contribution room grows with inflation, letting you save more in later years; if disabled, the limit stays flat.",
    consider: "The IRS already indexes the limit for most people, so leaving this enabled will match what the IRS allows.",
  },
  monthly_401k_contribution: {
    purpose: "This is the amount you contribute to your 401(k) plan each month while you're working, deducted from your paycheck before income tax.",
    impact: "A higher contribution reduces your taxable income and grows more for retirement; a lower contribution leaves more money in your paycheck but means less retirement savings.",
    consider: "Aim to contribute as much as your budget allows up to the legal limit — your contributions grow tax-free until retirement, making it one of the most powerful saving tools available.",
  },
  qbi_phaseout_applies: {
    purpose: "QBI stands for Qualified Business Income deduction — a tax break that lets business owners deduct up to 20% of their business profits. This setting indicates whether your income is high enough that the deduction becomes limited or disappears.",
    impact: "If this applies to you, your QBI deduction is reduced or eliminated, increasing your taxable income even though your actual business income hasn't changed.",
    consider: "This usually only matters for higher-income business owners; the IRS sets an exact income threshold each year (adjusted for inflation) above which the deduction starts shrinking. If your business income is comfortably below that threshold, this rarely applies.",
  },
  reasonable_salary_annual: {
    purpose: "For an S-Corp business, this is the W-2 wage you (the owner) must pay yourself — the amount subject to payroll taxes like Social Security and Medicare. Any profit beyond this is distributed to you as business income, not wages.",
    impact: "A higher salary reduces business income distributions and increases your payroll tax; the IRS requires the salary to be reasonable for the work you do, so setting it too high can trigger audits.",
    consider: "Talk to a tax professional to set a reasonable salary based on what similar workers in your field earn; this balance between W-2 and distribution can significantly affect your total tax bill.",
  },
  sehi_added_to_w2: {
    purpose: "SEHI stands for Self-Employed Health Insurance — a deduction for premiums you pay for health, dental, and vision coverage for yourself and your family as a business owner. This setting adds that deduction to your W-2 wages.",
    impact: "When enabled, the health insurance amount you pay appears as a deduction, lowering your taxable income dollar-for-dollar and potentially reducing your income tax.",
    consider: "Include all premiums you pay for health, dental, and vision insurance for yourself and dependents; this is one of the most valuable tax breaks for self-employed people.",
  },
  state_corporate_surcharge_rate: {
    purpose: "Some states, like Illinois, charge a separate surcharge on business income in addition to the normal state corporate tax — basically a tax on top of the base tax.",
    impact: "A higher surcharge rate increases your state income tax bill; a lower rate reduces it. This only affects state tax, not federal tax.",
    consider: "If you operate a business in a state with a surcharge, check the current rate with a tax professional or your state's revenue department — it's set by state law and can change.",
  },
  business_expenses_annual: {
    purpose: "These are ordinary, necessary deductions for running your business — things like supplies, equipment, office rent, utilities, professional services, and similar costs that you wouldn't incur without the business.",
    impact: "Higher expenses reduce your taxable business income dollar-for-dollar; lower expenses increase it. Only include legitimate business costs, not personal spending.",
    consider: "Keep receipts and records for everything you deduct; the IRS will ask for proof if audited. When in doubt, consult a tax professional about whether a specific expense qualifies.",
  },
  health_insurance_premiums_annual: {
    purpose: "These are the premiums you pay annually for health, dental, and vision insurance for yourself and your family as a self-employed person, claimed as a deduction above the line before calculating adjusted gross income.",
    impact: "This deduction reduces your taxable income, lowering both income tax and self-employment tax, making it one of the most valuable tax benefits for self-employed people.",
    consider: "Include all premiums you actually pay; if your spouse's employer covers you, you can't use this deduction. This gets special tax treatment separate from general business expenses.",
  },
  home_office_expenses_annual: {
    purpose: "If you use part of your home exclusively for business, you can deduct the related expenses — usually calculated as a percentage of your home's mortgage or rent, utilities, insurance, and maintenance based on the square footage of your office.",
    impact: "A higher home office deduction reduces your taxable income; however, if you sell the home later, a portion of your gain might be subject to capital gains tax. The tax savings now can create a tax bill later.",
    consider: "The simplified method is easier (about five dollars per square foot up to 300 sq ft); the regular method is more detailed but captures more actual expenses. Talk to a tax professional about which works better for you.",
  },
  qbi_eligible: {
    purpose: "QBI stands for Qualified Business Income. If you're self-employed or own a small business, you may be eligible for a tax deduction of up to 20% of your business income, which can lower your overall tax bill.",
    impact: "When enabled, the plan applies the 20% deduction to reduce your taxable business income for the year, lowering federal income tax. If you're not self-employed or this doesn't apply to your situation, disabling it has no effect.",
    consider: "Talk to a tax professional to confirm whether your business structure qualifies (sole proprietorship, partnership, and S-corp typically do; C-corporations do not).",
  },
  annual_charitable_giving_high: {
    purpose: "This is the higher amount of money you expect to give to charity in a year, used as the top of your giving range.",
    impact: "Raising this number increases how much the plan sets aside for charitable giving at the high end and may affect how much cash you need each year. Lowering it reduces the charitable-giving projection.",
    consider: "Use your actual giving history over the past few years to set both the high and low ends — patterns usually show whether you're at the top, bottom, or somewhere in between.",
  },
  annual_charitable_giving_low: {
    purpose: "This is the lower amount of money you expect to give to charity in a year, used as the bottom of your giving range.",
    impact: "Lowering this number reduces the minimum charitable giving the plan assumes, which may free up more cash for other spending. Raising it increases the minimum giving commitment.",
    consider: "Set this conservatively based on giving you're already committed to; the high end can capture wish-list amounts or unusually generous years.",
  },
  annual_spending_base_year: {
    purpose: "This is your total household spending in a reference year, excluding what you pay in taxes and mortgage principal.",
    impact: "The plan uses this as a starting point and adjusts it forward based on inflation and spending changes. Raising it increases the annual cash you'll need; lowering it reduces cash needs.",
    consider: "Use a recent year of actual spending to ground this number, covering everyday expenses like groceries, utilities, insurance, travel, and hobbies — but not taxes or mortgage payments, which the plan tracks separately.",
  },
  core_spending_growth_mode: {
    purpose: "This setting controls how your everyday spending is assumed to grow each year — either by the general inflation rate, or by a custom rate you specify.",
    impact: "If set to inflation, spending grows with the overall cost-of-living index. If set to manual, it grows by the custom rate you enter instead, letting you model spending growth that's higher or lower than general inflation.",
    consider: "Use inflation if you expect your spending to track the overall economy. Use manual if you're planning to cut spending over time or if you know your personal costs rise faster than general inflation.",
  },
  core_spending_manual_growth_rate: {
    purpose: "When you've chosen manual growth mode, this is the annual percentage rate at which your everyday spending increases each year.",
    impact: "Raising this rate means your annual spending grows faster, requiring more cash in later years. Lowering it slows the growth, reducing long-term cash needs.",
    consider: "Think about whether your actual costs are rising faster or slower than inflation — groceries might outpace general inflation while utilities might not, so a 1-2% difference is common.",
  },
  ytd_blend_enabled: {
    purpose: "When enabled, the plan blends in the actual income and spending you've tracked so far this year, making the projection realistic for the remainder of the year. When disabled, the plan models a purely hypothetical scenario starting fresh.",
    impact: "When enabled, the current-year forecast reflects real spending and income history to date, making it more accurate for cash planning. When disabled, the plan ignores actuals and projects a full-year scenario, which can mask how the year is actually going.",
    consider: "Leave this on for day-to-day cash planning (it tells you if you're on track). Turn it off if you want to model a hypothetical scenario untethered from this year's actual results.",
  },
  ytd_remainder_spending_override: {
    purpose: "This lets you manually set how much of your everyday core spending you expect in the rest of this year, overriding the plan's automatic estimate.",
    impact: "If you enter a number, the plan uses that instead of assuming spending will be spread evenly through the year. This is useful if you know the rest of the year will be lighter or heavier than a straight average.",
    consider: "Use this if you know something the plan doesn't — for example, you're taking unpaid leave in the fall or you have a big trip already booked.",
  },
  annuity_default_additional_income_pct: {
    purpose: "When you own an annuity, a portion of each payment can be reinvested to boost your guaranteed income in future years, with the rest paid out as cash now. This is the default percentage used for annuities that don't have their own custom setting.",
    impact: "Raising this percentage means more of each annuity payment is reinvested (increasing future payments but reducing today's cash), while lowering it means more cash now and smaller future payments.",
    consider: "This depends on your cash needs now versus later — reinvest more if you don't need the cash immediately and want stronger income in your 80s and 90s.",
  },
  annuity_default_dividend_rate: {
    purpose: "Annuities can earn a dividend or return on reinvested amounts. This is the default rate assumed for any annuity that doesn't specify its own.",
    impact: "A higher rate means reinvested portions grow faster, producing larger future guaranteed payments. A lower rate means smaller future payments.",
    consider: "Check your annuity contract or statement for the actual dividend rate, or ask your financial advisor what rate to assume for retirement planning.",
  },
  cash_yield_rate: {
    purpose: "When dividends or interest from your investments are paid as cash instead of being reinvested, this is the rate at which that cash balance keeps earning interest in the account.",
    impact: "A higher rate means your cash balance grows faster, adding to your account value over time. A lower rate means the cash grows more slowly.",
    consider: "This should reflect current money-market or high-yield savings rates available at your brokerage or bank — typically 4-5% in recent years.",
  },
  fed_tax_bracket_inflator: {
    purpose: "This is the annual percentage by which federal tax brackets are adjusted for inflation.",
    impact: "A higher inflator means tax brackets shift up each year faster, potentially keeping you in a lower tax bracket as your income rises. A lower inflator means brackets creep up slower, causing more of your income to be taxed at higher rates over time.",
    consider: "Use the actual inflation rate your government announces each year, or use your expected long-term inflation rate if forecasting multiple years ahead.",
  },
  inflation_general: {
    purpose: "This is your assumption for the overall annual inflation rate — the rate at which the cost of everyday goods, housing, and cars is expected to rise.",
    impact: "A higher inflation rate means your purchasing power erodes faster, requiring larger cash flow each year to maintain the same lifestyle. A lower rate means your money goes further and you need less cash.",
    consider: "Use the Federal Reserve's target inflation rate (typically 2%) or your own expectation based on recent trends, but remember actual inflation can be higher or lower in any given year.",
  },
  medicare_part_b_inflation: {
    purpose: "This is the assumed annual rate at which Medicare Part B premiums (the monthly charge for doctor visits and outpatient care) are expected to increase.",
    impact: "A higher rate means your Medicare costs escalate faster with age, requiring more annual cash for health insurance. A lower rate reduces expected health insurance costs.",
    consider: "Part B premiums have historically risen 5-7% annually, but your actual premiums depend on your income and are adjusted by Social Security each January.",
  },
  medicare_part_d_inflation: {
    purpose: "This is the assumed annual rate at which Medicare Part D premiums (the monthly charge for prescription drug coverage) are expected to increase.",
    impact: "A higher rate means your drug insurance costs rise faster, increasing out-of-pocket health-care expenses. A lower rate reduces expected prescription-drug costs.",
    consider: "Part D premiums vary widely by plan and region, and they typically rise 3-5% annually; check your actual plan's recent premium history to inform this assumption.",
  },
  portfolio_nominal_return: {
    purpose: "This is your assumption for the annual percentage return your investment portfolio will earn, before subtracting fees and expenses.",
    impact: "A higher return means your invested assets grow faster, producing more wealth and often less need for spending cuts or delayed retirement. A lower return means slower portfolio growth, potentially requiring a lower spending level to stay on track.",
    consider: "Historically, a diversified stock-heavy portfolio averages 8-10% annually over long periods, while a balanced portfolio averages 5-7%. Be realistic and consider your actual asset allocation.",
  },
  reinvest_dividends_default: {
    purpose: "When turned on, all dividends and interest from your investments automatically buy more of the same investment (reinvestment), instead of sitting as cash. Turning it off pays dividends out as cash.",
    impact: "Reinvestment causes growth to compound faster and can significantly increase portfolio value over decades. Paying dividends as cash gives you cash flow now but forgoes compounding growth.",
    consider: "For retirement planning, reinvestment is usually best if you don't need the cash to live on. Switch to cash dividends only if you're using this portfolio to fund spending.",
  },
  social_security_taxable_fraction: {
    purpose: "Depending on your total income, a portion of your Social Security benefits may be subject to federal income tax. This is the percentage of benefits assumed to be taxable.",
    impact: "A higher fraction means more of your Social Security is counted as taxable income, raising your federal income tax bill. A lower fraction means less is taxed.",
    consider: "The taxable portion depends on your income relative to specific thresholds; households with low income often pay tax on 0% of benefits, while high-income households can pay tax on up to 85%.",
  },
  account_count: {
    purpose: "This is how many separate education savings plans you're tracking in this plan.",
    impact: "Adding accounts increases the total contributions and growth the plan models; each account can have its own contribution strategy and spending timeline.",
    consider: "These plans are tax-advantaged education savings accounts. Families often open one per child, but you can use a single account for multiple beneficiaries.",
  },
  contribution_start_year: {
    purpose: "This is the year in which you intend to begin making contributions to this education savings plan.",
    impact: "Earlier start years mean more years of tax-free growth before education expenses; later start years compress the saving window, requiring larger annual contributions to reach the same goal.",
    consider: "If you already have an account with an existing balance, set this to the year you opened it (the plan needs to know when to start crediting your balance).",
  },
  expected_use_year: {
    purpose: "This is when you plan to start taking money out of the 529 plan to pay for education. The plan can estimate how much the account needs to grow to meet education costs based on this timeline.",
    impact: "Changing this date affects how long the money has to grow and changes the investment strategy. A later use year gives more time for growth; an earlier year means you'll be withdrawing soon.",
    consider: "Think carefully about when education expenses will actually start — high school, college, grad school, or trade school. The plan needs to have enough ready by that year.",
  },
  contribution_end_year: {
    purpose: "This is the last year you plan to add money into the 529 account. After this year, the account just sits and grows (or starts being used for education expenses).",
    impact: "Changing this affects your contribution strategy and taxes. Money added after this year won't be included in your plan; stopping contributions earlier frees up cash for other uses.",
    consider: "Many people contribute until education expenses start, but you might stop earlier if contributions would push you over state tax-deduction limits or if your cash flow changes.",
  },
  state_deduction_eligible: {
    purpose: "Some states let you deduct 529 contributions from your state income tax. This setting tracks whether contributions to this account get that tax break in your state.",
    impact: "If eligible, deductible contributions lower your state taxable income that year. States that do not offer a deduction toggle this off, so contributions have no state tax benefit.",
    consider: "Check your state's current rules — they can change. If you're moving, this might affect which 529 plan is best to use.",
  },
  annual_cost_today: {
    purpose: "This is how much one year of education costs right now, in today's dollars — tuition, room and board, books, all in.",
    impact: "A higher cost means the plan needs to save more; a lower cost means less savings is needed. The plan grows this number forward each year using the cost inflation rate to estimate future expenses.",
    consider: "Use the real, full cost for the kind of school you're planning for (public university, private, community college, grad school). Don't guess — look it up on school websites or the College Board.",
  },
  cost_inflation_rate: {
    purpose: "This is the rate at which education costs are expected to rise each year — how much tuition and fees increase annually. The plan uses this to project what education will cost in the future.",
    impact: "A higher inflation rate makes education look more expensive in the future and increases the target savings goal. A lower rate means lower future costs and a smaller savings target.",
    consider: "Education costs have historically risen faster than general inflation. Research recent trends for the type of school you're planning for, or use a conservative estimate if unsure.",
  },
  allow_secure_2_roth_rollover: {
    purpose: "This setting controls whether unused 529 funds can be rolled into a Roth IRA account — a tax-advantaged retirement account under recent SECURE 2.0 rules, a relatively new option for leftover 529 money.",
    impact: "When enabled, if education isn't fully used, leftover balances can roll into a Roth tax-free (subject to annual limits and account holding periods). When disabled, unused funds stay in the 529 and get taxed if withdrawn.",
    consider: "This can be valuable if education goals aren't fully met but retirement savings goals are. Only works if the 529 account meets holding requirements, so check eligibility before assuming this option is available.",
  },
  state_deduction_limit_annual: {
    purpose: "Some states cap how much you can deduct for 529 contributions each year. This is that annual limit, if your state has one.",
    impact: "If your state limit is $10,000 and you contribute $15,000, only $10,000 reduces your taxes that year. Excess contributions may roll forward or be lost, depending on your state's rules.",
    consider: "Once you know your state's limit, shape your annual contribution strategy around it. If you're over the limit, you might split contributions across household members or account types, or carry contributions into future years.",
  },
  exercise_price: {
    purpose: "For stock options, this is the price you agreed to pay to buy shares when you exercise the option. Restricted stock units don't have an exercise price — they vest as free shares.",
    impact: "For options, a lower exercise price means bigger gains if the stock price rises. A higher exercise price means smaller gains or losses if the stock stays flat or falls. This only applies to options, not restricted stock units.",
    consider: "For options, compare the exercise price to your expected future stock price to estimate potential gains. If you have restricted stock units, this field doesn't affect anything.",
  },
  fmv_growth_rate: {
    purpose: "This is your assumption about how fast the company stock price will grow each year, expressed as a percentage. The plan uses it to project the value of your equity as it vests and grows.",
    impact: "A higher growth rate projects bigger future gains; a lower rate projects smaller gains. Over many years, even small differences in this rate add up to big changes in projected net worth.",
    consider: "Be realistic. Check the company's long-term growth history and the broader market outlook, but don't assume every year will match the best year. Conservative is usually safer than optimistic.",
  },
  fmv_per_share_today: {
    purpose: "This is the current market price of one share of company stock — how much it's worth right now today.",
    impact: "A higher current price means your vested or exercised shares are worth more at that moment. Changes to this number immediately shift the current value of your equity holdings.",
    consider: "For a public company, use the latest closing price. For private companies, use your best estimate of fair value, and update it whenever you have new information (like a recent funding round).",
  },
  grant_date: {
    purpose: "This is the date when the company granted (gave you) the equity award. It's used to calculate holding periods for tax purposes and to track how long the grant has been pending.",
    impact: "For incentive stock option tax treatment, the grant date matters — you need to hold the shares for specific periods after exercising to get favorable tax treatment. For restricted stock units, it marks the starting point for any cliff-vesting calculations.",
    consider: "Check your grant documents to confirm the exact date. For tax planning around incentive stock options, note the grant date and understand how long you need to hold after exercise to avoid alternative minimum tax.",
  },
  grant_type: {
    purpose: "This is the kind of equity you received — restricted stock unit, incentive stock option, non-qualified option, or other types. Each type has different tax treatment and rules.",
    impact: "Restricted stock units are taxed when they vest; incentive stock options get preferential tax treatment if you hold long enough; non-qualified options are taxed on gains immediately when exercised. The type determines when and how much tax you owe.",
    consider: "Understand which type you have. If you have incentive stock options, learn the holding-period rules to qualify for long-term capital gains treatment. If you have restricted stock units, plan for the tax bill when they vest.",
  },
  planned_exercise_year: {
    purpose: "For stock options, this is the year you plan to convert the option into shares by paying the exercise price. Restricted stock units don't require exercise — they automatically become shares when they vest.",
    impact: "Exercising earlier locks in a price now but uses cash today; exercising later hopes the stock goes higher but delays building your position. The year you exercise affects cash flow and tax planning.",
    consider: "For options, consider when you have cash available and when you want to own the shares. For incentive stock options, timing the exercise and sale to hit the required holding periods can save a lot in taxes.",
  },
  planned_sale_year: {
    purpose: "This is the year you plan to sell (liquidate) your equity. Diversifying concentrated positions by selling gradually can reduce risk and spread out the tax impact.",
    impact: "Selling earlier converts equity into cash you can invest elsewhere; selling later keeps you exposed to the stock and hopes for more gains. The sale year also marks when you realize gains and owe capital gains tax.",
    consider: "Don't hold too much of your net worth in a single company stock — aim to diversify. Map out a realistic multi-year sale strategy rather than selling it all at once, which creates a big tax hit and market-timing risk.",
  },
  recipient: {
    purpose: "This field tracks who receives the equity (usually yourself or a family member). It's used mainly for reporting and display in the plan — it doesn't affect financial calculations unless you specifically enable that setting.",
    impact: "Changing the recipient label changes how the holding is labeled in reports and summaries. It doesn't change the dollar amounts or cash flow unless the plan is configured to treat different recipients' holdings differently.",
    consider: "Use clear, recognizable names (like 'Your name' or 'Spouse name') to make reports easy to understand. This is mainly a bookkeeping and reporting tool.",
  },
  shares_outstanding: {
    purpose: "This is the number of shares granted to you in this award. If it's a restricted stock unit, this is how many shares you'll receive when it vests. If it's an option, this is how many shares you can buy when you exercise.",
    impact: "A larger number of shares means bigger potential upside if the stock rises and bigger losses if it falls. The number directly scales the dollar value of your equity position.",
    consider: "Check your grant documents for the exact number. If the grant vests over time or has cliffs (chunks vesting at once), track the schedule separately to know how many shares are actually available each year.",
  },
  vest_schedule: {
    purpose: "This describes when your equity becomes yours — for example, 25 percent per year for four years (a common tech-industry schedule) or 50 percent after two years, then 50 percent after four years (a cliff-and-schedule). Understanding the schedule tells you when you can sell or use the shares.",
    impact: "A faster vesting schedule means you own the shares sooner and can diversify or sell earlier. A slower vesting schedule means you're locked in longer and face more risk.",
    consider: "Map out your vest schedule year by year — when do you get 25 percent, 50 percent, 75 percent, 100 percent? If you leave the company before full vesting, you may lose unvested shares. Factor that into your job stability plans.",
  },
  shelter_cap: {
    purpose: "A credit shelter trust (also called a bypass trust) lets you and your spouse each use your full estate-tax exemption instead of losing the second person's exemption when the first person dies. This setting captures that combined protection amount, which some states allow through a funded bypass trust.",
    impact: "A higher shelter cap means more wealth can pass to heirs tax-free at death. A lower cap means more of the estate may be subject to federal estate tax. Proper structuring can essentially double your family's tax exemption.",
    consider: "Work with an estate attorney — this is complex and state-specific. Review the shelter cap amount annually as federal exemption amounts change. A well-structured trust is important protection for larger estates.",
  },
  exemption_mfj: {
    purpose: "This is your household's current federal estate-tax exemption — the amount of wealth you can pass to heirs completely free of federal estate tax. Married couples filing jointly each have an exemption, so you can combine them (with proper planning).",
    impact: "A higher exemption protects more wealth from tax; a lower exemption means more of your estate is taxable. The exemption amount is set by federal law and changes over time (indexed for inflation).",
    consider: "Work with an estate-planning attorney to set up trusts and beneficiary designations that use both spouses' exemptions efficiently. Don't assume the exemption will stay high — plan assuming it may change, and structure documents to adapt.",
  },
  annual_exclusion_per_donee: {
    purpose: "Each year, you can give a limited amount of money to each person (a 'donee') without using up your lifetime exemption or paying gift tax. This is the annual amount, set by federal law and indexed for inflation.",
    impact: "Within this limit, you can give to as many people as you want tax-free each year and reduce your taxable estate with no paperwork. Gifts above this limit use up your exemption and may require a gift-tax return to report.",
    consider: "If you plan to give to family members, learn this number and use it efficiently each year — it's a free wealth-transfer tool. If you're married, you and your spouse each get this exclusion, so coordinate gifts to maximize it.",
  },
  state_estate_exemption: {
    purpose: "This is the amount of wealth your state won't tax when someone passes away — above this number, the state may take a cut as estate tax. Some states let married couples combine their exemptions (portability); others do not, meaning each spouse only gets one exemption to use.",
    impact: "A higher exemption means fewer assets are subject to state estate tax. If the exemption doesn't carry over between spouses and the first spouse's estate is under the limit but unused exemption is lost, the surviving spouse's estate could face tax it wouldn't have if portability were allowed.",
    consider: "Check with your estate attorney if your household wealth is close to this threshold, and confirm whether your state allows portability between spouses — it affects whether you need certain trust structures.",
  },
  state_estate_rate_note: {
    purpose: "This is a note about the tax rate schedule your state applies to any estate value above the exemption — the rate typically steps up as the taxable amount gets larger (a graduated schedule, similar to how income tax brackets work).",
    impact: "The exact tax owed depends on where your estate value falls on this schedule. The higher your taxable amount above the exemption, the higher the rate that applies to that portion.",
    consider: "Your estate attorney will reference your state's specific schedule when planning to minimize state estate tax.",
  },
  manages_annuity_after_first_death: {
    purpose: "This specifies who will manage an annuity or other assets in the trust after the first spouse dies — important if the plan includes annuity-based income.",
    impact: "Different managers may have different investment approaches, fees, or flexibility in distributing income to the surviving spouse.",
    consider: "Make sure whoever you name has the expertise and availability to handle ongoing investment decisions.",
  },
  note: {
    purpose: "A place to record important details, context, or instructions about this trust that should be kept with the legal documents.",
    impact: "Documentation helps executors and trustees understand the intent behind the trust structure and execute it correctly.",
    consider: "Write anything here that would help someone carrying out the trust understand what you wanted and why.",
  },
  annual_contribution_limit: {
    purpose: "The maximum amount that can be contributed to an ABLE account (a tax-sheltered savings account for people with disabilities) in one calendar year.",
    impact: "Contributions up to this limit grow tax-free and are not penalized. Any contributions over the limit are not allowed.",
    consider: "This limit is set by federal law and changes most years — check the current year's limit before planning contributions.",
  },
  monthly_contribution: {
    purpose: "The amount of money the household plans to set aside each month for this account (an ABLE account or a 529 education savings plan).",
    impact: "Higher monthly contributions build the account balance faster and create more tax-sheltered growth potential over time.",
    consider: "Think about whether this amount fits your household budget consistently over several years, not just one year.",
  },
  annual_support_today: {
    purpose: "What it costs right now, per year, to cover all the support needs for this person — housing, food, medical care, therapy, and activities.",
    impact: "This number is used to estimate future support costs by applying inflation, which affects how much the trust needs to hold to provide lifetime support.",
    consider: "Include everything — it's better to estimate high than to underfund the trust later. Think about direct costs, ongoing therapy, equipment, and personal care.",
  },
  dob: {
    purpose: "When this person was born — used to figure out their age, life expectancy, and how long support may be needed.",
    impact: "Age affects care planning timelines and the total amount of future support needed. Different life expectancies change how large the trust must be.",
    consider: "If medical conditions affect life expectancy, discuss this with your estate attorney when planning the trust size.",
  },
  inflation_rate: {
    purpose: "The percentage rate at which this person's care and support costs are expected to rise each year.",
    impact: "A higher inflation rate means support costs will grow faster, so the trust needs to be larger to cover a lifetime of support. A lower rate means slower cost growth.",
    consider: "Special-needs care costs sometimes outpace general inflation — if this person has specific high-cost needs, use a rate that reflects those trends.",
  },
  lifetime_to_age: {
    purpose: "The age at which you expect this person's support needs to end (often based on life expectancy or when public benefits take over).",
    impact: "A longer expected lifetime means the trust needs more money to cover more years of support. Shortening this age reduces the funding target.",
    consider: "Use medical guidance, family history, and life-expectancy tables for this person's condition — this is often the biggest cost driver in the plan.",
  },
  name: {
    purpose: "The name of this special-needs beneficiary — used to identify which person's settings and funding apply in the plan.",
    impact: "Tracking by name ensures each beneficiary's support needs and trust funding are kept separate and correct.",
    consider: "Use the same legal name consistently across all estate documents, account applications, and this plan.",
  },
  medicaid_enrolled: {
    purpose: "Whether this person is currently enrolled in Medicaid (the joint federal-state health insurance program for low-income or disabled people).",
    impact: "If enrolled, trust disbursements that count as income can reduce or eliminate Medicaid benefits — so trust structure matters. If not enrolled, the concern doesn't apply.",
    consider: "If Medicaid benefits are critical to this person's care, use a third-party trust and work with an attorney who specializes in special-needs planning.",
  },
  ssdi_monthly: {
    purpose: "The monthly payment this person receives from Social Security Disability Insurance — a federal benefit for people who have worked and become disabled.",
    impact: "This income reduces how much the trust needs to cover, so it directly lowers the funding target. If SSDI is expected to grow with cost-of-living adjustments, the trust burden shrinks over time.",
    consider: "Verify the current amount with the Social Security Administration; this benefit adjusts annually, so update the plan periodically.",
  },
  ssi_monthly: {
    purpose: "The monthly Supplemental Security Income benefit this person receives — a federal program that gives cash to disabled, blind, or elderly people with very low income and resources.",
    impact: "This income reduces what the trust must provide. However, SSI has strict resource limits — if the trust grows too large or makes certain payouts, it can reduce or eliminate this benefit.",
    consider: "If SSI is vital for this person, coordinate with a special-needs planning attorney to structure trust distributions so they don't jeopardize the SSI benefit.",
  },
  balance_today: {
    purpose: "How much money is in the Special Needs Trust right now — the starting point for calculating how much more funding is needed.",
    impact: "A larger starting balance means fewer future contributions are needed to reach the target funding goal. A smaller balance means higher required annual contributions.",
    consider: "Use the most recent account statement. After major gifts or payouts, update this figure before running a full financial plan.",
  },
  funding_schedule: {
    purpose: "How much money the household plans to add to the trust each year — the annual contribution that compounds alongside investment growth.",
    impact: "Higher annual contributions build trust assets faster. Larger annual amounts mean the trust reaches its funding goal sooner and with a bigger cushion for inflation or unexpected costs.",
    consider: "Be realistic about household cash flow — a commitment you can't maintain will leave the trust underfunded. Starting smaller and increasing over time is better than overcommitting early.",
  },
  growth_rate: {
    purpose: "The expected average yearly return on the trust's investments — how fast the money inside is expected to grow.",
    impact: "A higher expected return means the trust grows faster without needing as much contribution. A lower return means the household needs to contribute more or the trust will fall short.",
    consider: "Special-needs trusts often use conservative portfolios because the money is critical and must be reliably available. Use a modest growth rate assumption.",
  },
  is_third_party: {
    purpose: "Whether the trust was set up by someone else for this person's benefit (third-party trust) or by the person themselves (self-settled trust).",
    impact: "If third-party, the Medicaid program cannot reclaim trust assets after the person dies; if self-settled, it can. This is a major tax and estate-planning difference.",
    consider: "This is usually decided when the trust is created with an attorney. If you're not sure, check with the trust's attorney or trustee.",
  },
  former_spouse_name: {
    purpose: "A flag field — if an ex-spouse's name is entered here, the plan checks all your accounts to see if that person is still listed as a beneficiary anywhere (which is usually a mistake).",
    impact: "This doesn't change the plan itself, but it helps you find accounts that need updating to reflect your current wishes and avoid unintended inheritances.",
    consider: "After a divorce, review all bank accounts, investment accounts, life insurance, and retirement accounts to make sure beneficiaries are updated.",
  },
  property_regime: {
    purpose: "This describes which state's property laws apply to how you and your spouse own assets — common law states (each person owns what's in their name) versus community property states (spouses jointly own most assets acquired during marriage).",
    impact: "The property regime affects whether your assets automatically get a full basis step-up (tax-free increase in value to current market price) when you die, which has big tax consequences for your heirs.",
    consider: "If you moved to a different state or own property in multiple states, this can get complicated — an estate attorney can clarify which regime applies to which assets.",
  },
  trust_type: {
    purpose: "The type of trust structure you'll use for planning — revocable, irrevocable, or other forms — which determines how assets pass when you die and affects tax treatment during life.",
    impact: "Revocable trusts give you control and flexibility but no tax savings; irrevocable trusts can protect assets from creditors and reduce estate taxes but lock in decisions you can't easily change later.",
    consider: "Most households start with a revocable trust for simplicity and control; consider irrevocable trusts only if you have significant assets to shelter from taxes or creditors, and consult a lawyer.",
  },
  amount: {
    purpose: "The dollar amount you want to move from a pre-tax retirement account (like a 401(k) or IRA) into a Roth account in a given year. This is a forced action — it happens according to this schedule regardless of market conditions.",
    impact: "Higher amounts increase the taxes you owe that year but build a bigger tax-free Roth pool that grows untaxed later; lower amounts reduce this year's tax bill but leave less money growing tax-free for the future.",
    consider: "Time larger conversions to years when income dips (like right after you retire), so you pay less tax on the conversion and stay in a lower tax bracket.",
  },
  source_account: {
    purpose: "Which pre-tax account the Roth conversion will pull from — like a 401(k), traditional IRA, or other retirement savings account.",
    impact: "The account type affects mainly tax complexity and withdrawal rules; money from either account is taxed the same way when converted, but different account types have different restrictions on partial withdrawals.",
    consider: "If you have both a 401(k) and an IRA, starting conversions with the IRA is usually simpler because you can withdraw and convert any amount without triggering automatic distributions from the other account.",
  },
  year: {
    purpose: "The calendar year when the forced Roth conversion happens — this sets the tax and timing for moving money from pre-tax to Roth.",
    impact: "A conversion in a low-income year produces much less tax impact than one in a high-income year; the timing also affects when converted funds can be accessed and when they begin growing tax-free.",
    consider: "Schedule conversions for years with lower income — like the first year after retirement, a sabbatical, or a bonus year off — to keep the tax cost down.",
  },
  filing_status: {
    purpose: "Your federal tax filing status — Married Filing Jointly, Single, Head of Household, etc. — which determines your tax brackets, standard deduction, and eligibility for various tax credits each year.",
    impact: "Filing status directly affects how much tax you owe on the same income; married couples filing jointly typically get larger deductions and wider brackets than singles. The status changes from Married Filing Jointly to Single in the year after the first spouse dies.",
    consider: "This is determined by your legal household situation and is generally not something to adjust for planning — it's a fact that changes automatically at life events.",
  },
  member_1_dob: {
    purpose: "The birth date of the first household member, entered as M/D/YYYY, which the plan uses to calculate their age throughout retirement.",
    impact: "Accurate birthdates determine when major milestones apply — when Social Security benefits can start (62 or later), when Required Minimum Distributions begin (age 73), and when Medicare eligibility kicks in (age 65).",
    consider: "Get this exactly right — even a year off shifts when tax and benefit rules apply, which can significantly change your plan's projections.",
  },
  member_1_mortality_age: {
    purpose: "The age you expect this household member to live to, which sets when the plan ends (calculated as birth year plus this age). This is the planning horizon for this person's expenses and income.",
    impact: "A longer time horizon means the plan must fund more years of spending and includes more investment growth, but requires the portfolio to stretch further; a shorter horizon tightens the budget but may underestimate longevity risk.",
    consider: "Use actuarial life-expectancy tables for your age and health, but add a buffer for safety — running out of money at 95 is worse than having extra at 90.",
  },
  member_1_name: {
    purpose: "The full legal name of the first household member, used to identify this person throughout the plan.",
    impact: "This is mainly for identification and reporting; it has no effect on calculations unless you leave the nickname field blank, in which case the first name from here is used in charts and reports instead.",
    consider: "Use the full legal name as it appears on tax returns and Social Security records to avoid confusion, but set a separate nickname for cleaner-looking charts and reports.",
  },
  member_1_nickname: {
    purpose: "A short, friendly name used in all reports and charts for this household member — for example, 'Pat' instead of 'Patricia'. If left blank, the first name from the full name is used instead.",
    impact: "Purely cosmetic — shortens labels in charts and reports for readability but has no effect on calculations or tax treatment of any kind.",
    consider: "Use a single short name or initial for clean-looking charts, especially if you're sharing the plan with a spouse or advisor.",
  },
  member_1_retirement_date: {
    purpose: "The date this household member retires, set as a year. This marks when their employment income stops and when retirement spending begins for them.",
    impact: "An earlier retirement date extends the years you need to fund and reduces the time for investments to grow before spending begins; a later retirement date adds more working years of income and investment compounding.",
    consider: "This is a base assumption — use it to scenario-test questions like 'what if I retire at 62 instead of 67?' to see how different retirement ages change your plan's success.",
  },
  member_2_dob: {
    purpose: "The birth date of the second household member, entered as M/D/YYYY, which the plan uses to calculate their age throughout retirement.",
    impact: "Accurate birthdates determine when major milestones apply for this person — when their Social Security benefits can start, when their Required Minimum Distributions begin, and when their Medicare eligibility begins.",
    consider: "Get this exactly right — even a year off shifts when tax and benefit rules apply for this household member, which can materially change your plan's projections.",
  },
  member_2_mortality_age: {
    purpose: "The age you expect the second household member to live to, which extends the plan's time horizon if this person outlives the first. The plan ends when the longer-lived member reaches this age.",
    impact: "A longer time horizon means more years of spending to fund (especially if this person lives significantly longer than the first member) and more time for investment growth, but also means the portfolio must stretch longer.",
    consider: "In a couple, the second person's life expectancy is often the binding constraint — plan for the scenario where the longer-lived member reaches very old age.",
  },
  member_2_name: {
    purpose: "The full legal name of the second household member, used to identify this person throughout the plan.",
    impact: "This is mainly for identification and reporting; it has no effect on calculations unless you leave the nickname field blank, in which case the first name from here is used in charts and reports instead.",
    consider: "Use the full legal name as it appears on tax returns and Social Security records to avoid confusion, but set a separate nickname for cleaner-looking charts and reports.",
  },
  member_2_nickname: {
    purpose: "A short, friendly name used in all reports and charts for the second household member — for example, 'Alex' instead of 'Alexander'. If left blank, the first name from the full name is used instead.",
    impact: "Purely cosmetic — shortens labels in charts and reports for readability but has no effect on calculations or tax treatment of any kind.",
    consider: "Use a single short name or initial for clean-looking charts, especially if you're sharing the plan with a spouse or advisor.",
  },
  member_2_retirement_date: {
    purpose: "The date this household member retires, set as a year. This marks when their employment income stops and when retirement spending begins for them.",
    impact: "If this date differs from the first member's, the plan may have a period where one person is retired and one is still working, which changes household cash flow, tax filing status, and tax brackets until both are retired.",
    consider: "Test different retirement ages for each person separately — like 'what if one of us retires five years earlier?' — to see how a staggered retirement affects your plan's success and cash flow.",
  },
  residence_state: {
    purpose: "The state where you live, which determines what state income taxes apply to your household and affects residency for tax purposes.",
    impact: "State income taxes vary widely — some states (like Florida or Texas) have no income tax, while others heavily tax retirement income or pensions — materially affecting your after-tax spending power in retirement.",
    consider: "If you're close to retirement and have flexibility, moving to a no-income-tax state can be a significant planning lever, but weigh it against cost of living, property taxes, and where you want to spend your time.",
  },
  survivor_filing_status: {
    purpose: "Your tax filing status after the first household member dies — either Single or Head of Household (HOH) if you have qualifying dependents at that time.",
    impact: "Head of Household filing provides better tax brackets and a higher standard deduction than Single filing, but only applies if you have a qualifying dependent; claiming HOH incorrectly can trigger IRS problems, so accuracy matters.",
    consider: "This depends on whether minor children or other qualifying dependents live with you after the first death — Head of Household is only an option if one exists and you're paying more than half their support.",
  },
  survivor_has_dependent: {
    purpose: "Whether there are dependent children or other qualifying dependents in the household after the first member dies, which affects the survivor's tax brackets for exactly two years after that death.",
    impact: "Having a dependent enables special 'Qualifying Surviving Spouse' tax brackets for two years following the first death (in addition to Head of Household filing), giving significantly better tax treatment than Single filing; without dependents, the survivor drops to Single brackets immediately.",
    consider: "This mainly matters for households with minor children — if kids are aging out or already independent by the time of the first death, you may not qualify for the surviving spouse bracket benefit.",
  },
  city_type: {
    purpose: "The area type where the home is located — urban, suburban, or rural — which affects property taxes, home values, and typical costs of living and services in that region.",
    impact: "Urban areas often have higher property taxes and home prices but lower transportation costs; rural areas often have lower taxes and home prices but higher transportation costs and fewer available services.",
    consider: "This is a broad categorization that helps the model estimate cost-of-living differences — if you know your actual property tax rate or home value, using those specific numbers will give more precise results.",
  },
  hoa_annual: {
    purpose: "The annual Homeowners Association fee (if your home has one), which is a fixed annual cost added on top of mortgage, taxes, and insurance as a housing expense.",
    impact: "Higher HOA fees increase your fixed housing costs every year; lower fees reduce that burden. These fees often increase over time, so the plan typically applies annual growth assumptions to them.",
    consider: "If your HOA fees are likely to increase faster than inflation — common for aging communities with aging infrastructure — consider manually increasing this estimate in future years rather than assuming flat or inflation-level growth.",
  },
  home_maintenance_annual: {
    purpose: "This is how much you expect to spend each year fixing and maintaining your current home. Regular upkeep includes roof repairs, plumbing fixes, painting, and appliance replacements.",
    impact: "Raising this amount increases your yearly housing expenses in the plan. Lower amounts might underestimate the true cost of owning a home.",
    consider: "Look at your actual spending over the past few years, or use a rule of thumb like 1% of your home's value per year.",
  },
  homeowners_insurance_annual: {
    purpose: "This is your annual homeowners insurance bill — the insurance that protects your house and belongings against damage, theft, and liability. Most mortgage lenders require it.",
    impact: "Increasing this amount raises your total housing costs. It also affects how much money you'll need each year to cover all housing expenses.",
    consider: "Check your current policy renewal letter for your actual premium, since insurance costs vary widely by location and home age.",
  },
  population_size: {
    purpose: "This is the approximate population of the area where your home is or will be located. The plan uses this to estimate property taxes, insurance, and other housing costs typical for that area.",
    impact: "Changing it may adjust estimated property taxes and insurance costs, since these vary significantly between rural and urban areas.",
    consider: "A quick online search for your city or county population is enough — the plan doesn't require exact precision.",
  },
  utilities_annual: {
    purpose: "This is what you expect to pay annually for electricity, gas, water, and internet. These are fixed costs that happen every year.",
    impact: "Higher amounts increase your yearly housing expenses. Lower estimates might leave you short of cash in years when utility bills spike (especially in very hot or cold climates).",
    consider: "Add up your actual bills for the past 12 months, including seasonal highs and lows, then use that total.",
  },
  down_payment: {
    purpose: "This is the percentage of the purchase price you'll pay upfront when buying a home, with the rest financed through a mortgage. A 20% down payment is common and avoids mortgage insurance costs.",
    impact: "A larger down payment means a smaller mortgage and lower monthly payments and total interest paid over time, but uses more cash now. A smaller down payment stretches your cash but costs more in the long run.",
    consider: "If you're planning to buy within a few years, a larger down payment usually makes sense to minimize interest costs. If you may need liquidity, a smaller down payment keeps more cash available.",
  },
  hoa_pct: {
    purpose: "HOA stands for Homeowners Association — an organization that manages common areas and enforces neighborhood rules. This field is the annual HOA fee expressed as a percentage of the home's value (optional, only if you're buying in a community with an HOA).",
    impact: "A higher HOA percentage increases your annual housing costs. It's a mandatory expense if the home is in an HOA community, so it should not be understated.",
    consider: "Search for the specific HOA fees in any community you're considering — they can range from nearly zero to several thousand dollars per year depending on amenities.",
  },
  insurance_annual: {
    purpose: "This is the annual homeowners or renters insurance premium you expect to pay for the next home you plan to buy or rent. Most mortgage lenders require homeowners insurance.",
    impact: "Increasing this amount raises your projected annual housing costs for that home. It's a fixed expense that affects how much income you'll need in retirement.",
    consider: "Get a quote from an insurance company before finalizing this estimate, since premiums depend on the property, its age, location, and the coverage you choose.",
  },
  maintenance_annual: {
    purpose: "This is the annual cost to maintain and repair the next home you plan to buy. New homes may have lower maintenance costs initially, while older homes typically cost more to maintain.",
    impact: "Higher maintenance costs increase your yearly housing budget. Underestimating can leave you short of cash if major repairs come up unexpectedly.",
    consider: "If you know the specific home you're buying, research typical maintenance costs for that age and construction type, or use 1% of the purchase price as a rough estimate.",
  },
  monthly_rent: {
    purpose: "This is the monthly rent payment for the next home you plan to move to if you choose to rent instead of buy. It's the lease amount before utilities and renters insurance.",
    impact: "A higher rent payment increases your monthly housing expense and total spending through retirement. Changing it directly changes how much monthly income you'll need.",
    consider: "If you're planning a move in the next few years, research current rents in that area to get a realistic number.",
  },
  mortgage_rate_pct: {
    purpose: "This is the interest rate (shown as a percentage) you expect to pay on your next mortgage. It directly affects how much of each monthly payment goes toward interest versus principal.",
    impact: "A higher interest rate increases your total cost of borrowing and your monthly payment, costing thousands more over the life of the loan. A lower rate reduces both.",
    consider: "Current market rates are publicly available, but if you're buying years from now, using a conservative estimate (slightly higher than today's rates) is prudent, since rates fluctuate unpredictably.",
  },
  purchase_price: {
    purpose: "This is the purchase price of the home you plan to buy next. It's the full amount before your down payment, closing costs, or mortgage.",
    impact: "A higher purchase price increases the size of your mortgage, down payment, and property taxes. It directly affects how much housing wealth you have in retirement and how much cash you'll need to close.",
    consider: "Research home prices in the area and price range you're targeting. If you're buying within a few years, actual listings give you a realistic picture; if it's further out, plan for some price appreciation.",
  },
  re_tax_pct: {
    purpose: "This is your annual property tax expressed as a percentage of the home's market value. Property tax rates vary enormously by state and county and are one of the largest ongoing housing costs.",
    impact: "A higher tax rate increases your annual housing costs permanently. Some states have low property taxes (under 0.5% of value) while others can exceed 2%, so this assumption matters greatly for long-term planning.",
    consider: "Look up the property tax rate for the specific county or state where you plan to live — it's public information and a quick online search will give you an accurate number.",
  },
  state: {
    purpose: "This is the US state where your home is or will be located. The plan uses this to estimate property taxes, HOA fees, insurance, and other housing costs that vary by state and region.",
    impact: "Changing it may adjust estimated property taxes, insurance costs, and other location-based assumptions. Different states have very different housing and tax environments.",
    consider: "Enter the two-letter state abbreviation (such as CA, TX, or NY) where you own or plan to buy the home.",
  },
  catchup_amount: {
    purpose: "An HSA is a Health Savings Account — a tax-advantaged account for medical expenses. At age 55 or older, you can contribute an extra \"catch-up\" amount on top of the normal limit — this is that extra dollar amount.",
    impact: "Increasing this amount allows you to save more money tax-free for medical expenses in later years and grow it for retirement. The money rolls over year to year, so higher contributions build a larger cushion.",
    consider: "This catch-up feature is only available once you turn 55, and only if you stay enrolled in a qualifying high-deductible health plan — check your coverage status before assuming you'll qualify.",
  },
  catchup_eligible: {
    purpose: "This is a yes or no flag that indicates whether you're age 55 or older and therefore eligible to make the extra \"catch-up\" contributions to your HSA.",
    impact: "When yes, you're allowed to contribute the catch-up amount each year until you enroll in Medicare. When no, only the standard annual limit applies.",
    consider: "You become eligible the year you turn 55, and you can continue making catch-up contributions through the year you turn 64 (contributions stop when Medicare coverage begins).",
  },
  contribution_last_year: {
    purpose: "This is the final year you can contribute to your HSA. The IRS stops allowing new HSA contributions once you enroll in Medicare, typically at age 65, though you can still withdraw money tax-free for medical expenses after that.",
    impact: "Contributions stop after this year, so you can no longer add new money. However, money already in the account continues to grow and remains available for medical expenses forever.",
    consider: "Check your expected Medicare enrollment date — if you plan to delay Medicare past 65, you might be able to contribute a year or two longer.",
  },
  coverage_base_year_family_months: {
    purpose: "This is the number of months in 2026 that you or your family are covered by a qualifying high-deductible health plan. HSA contributions are limited based on how many months of coverage you have.",
    impact: "More months of coverage means a higher contribution limit that year (prorated if less than 12 months). Fewer months might occur if you change plans mid-year or retire mid-year.",
    consider: "Count the actual months you expect to have family HDHP coverage in 2026. If you're changing plans or retiring partway through the year, note the exact transition date.",
  },
  coverage_base_year_self_only_months: {
    purpose: "This is the number of months in 2026 that you have individual (self-only) high-deductible health plan coverage, as opposed to family coverage. HSA contribution limits are different for self-only versus family coverage.",
    impact: "More months of self-only coverage increases the contribution limit under the self-only cap. The plan uses this to calculate exactly how much you can contribute depending on your coverage type each month.",
    consider: "If you're a single person or if you switch from family to self-only coverage mid-year, count the months carefully — even one month changes the annual limit.",
  },
  family_annual_limit_base_year: {
    purpose: "This is the maximum dollar amount you can contribute to an HSA in 2026 if you have family or joint health plan coverage. The IRS sets this limit annually and it increases slightly each year.",
    impact: "Contributions above this limit may face penalties and taxes. This is the cap for the year — you can contribute less, but not more (except for the age-55+ catch-up if eligible).",
    consider: "Check the current year's IRS limits before planning your contribution — the plan should pre-fill this based on your coverage, but verify it matches official IRS numbers for accuracy.",
  },
  index_hsa_limit: {
    purpose: "This is a yes or no setting that tells the plan whether to automatically increase HSA contribution limits in future years to account for inflation. The IRS typically raises the limits annually.",
    impact: "When yes, the limits grow slightly each year as inflation adjusts them. When no, the limit stays fixed at the base-year amount, meaning you save less in later years.",
    consider: "Enable this if you want the plan to assume inflation-adjusted limits (the common IRS practice) — only disable it if you're using a flat limit for conservative planning.",
  },
  requires_hdhp: {
    purpose: "This setting controls whether the plan models regular HSA contributions each year. An HSA (Health Savings Account) is a tax-advantaged savings account that only people with a high-deductible health plan can contribute to. When you turn this on, the plan assumes annual contributions continue until you or your spouse reaches Medicare age and no longer qualifies.",
    impact: "Turning this on increases annual tax-free savings available for medical costs and adds to your invested assets over time. Turning it off stops modeling contributions entirely. Since HSA savings never expire and can grow tax-free, enabling this when you qualify can meaningfully boost long-term wealth.",
    consider: "Only turn this on if you or a spouse are enrolled in a qualifying high-deductible health plan and expect to stay that way until Medicare. If your coverage changes to a traditional PPO or HMO, you can no longer contribute, so update this setting when your coverage changes.",
  },
  self_only_annual_limit_base_year: {
    purpose: "This is the maximum dollar amount you can contribute to an HSA each year when you have self-only (individual) coverage. The IRS sets this limit annually and it changes slightly most years. This is the starting-year limit your plan uses to calculate future contributions.",
    impact: "Raising this increases the annual tax-free savings the plan models. Lowering it reduces contributions. Since HSA contributions are tax-deductible, raising the contribution limit means more tax savings and more compounding growth.",
    consider: "Look up the current year's HSA contribution limit for self-only coverage from the IRS or your HSA provider. If you have family coverage instead, you'd use a different higher limit (check your plan details). Update this annually if the IRS changes the limit.",
  },
  inherited_by_spouse: {
    purpose: "This controls what happens to your HSA when you pass away. If you turn this on, your spouse inherits your HSA as their own HSA and keeps the tax-free withdrawal benefit. If you turn it off, your spouse inherits the balance but loses the HSA's special tax treatment.",
    impact: "Turning this on preserves the HSA's tax-free status for your spouse after your death. Turning it off means the inherited balance becomes taxable income when withdrawn. This can save your spouse significant taxes on medical expenses in the years after you pass away.",
    consider: "Turn this on if you're married and want your spouse to benefit from your accumulated HSA balance. If you have no spouse or don't want HSA assets going to your spouse, leave it off.",
  },
  withdrawal_window: {
    purpose: "This number of years controls how quickly the plan drains your HSA balance toward zero. If set to 10, the plan withdraws an equal amount each year for 10 years. If left blank or set to 0, no scheduled drawdown happens.",
    impact: "A shorter window means larger annual withdrawals and faster depletion. A longer window spreads withdrawals smaller over more years. This only applies if you choose the 'smooth window' withdrawal mode below.",
    consider: "Use this if you want a predictable, even drawdown instead of taking it all at once or on-demand. Match the window to roughly when you expect to need the money or when you want a gradual systematic approach to spending it down.",
  },
  hsa_annual_spend_pct: {
    purpose: "This percentage controls how much of your current HSA balance gets withdrawn each year when you pick the 'annual percentage' withdrawal mode. If set to 5%, the plan withdraws 5% of whatever the balance is that year.",
    impact: "A higher percentage drains the balance faster each year. A lower percentage takes longer to spend down. Because the percentage is applied to the remaining balance, you withdraw less in later years as the balance shrinks.",
    consider: "Set this to a percentage that feels reasonable for your spending. If your HSA balance is $50,000 and you set 10%, the first year you withdraw $5,000. As the balance drops, so does the dollar amount withdrawn each year.",
  },
  hsa_withdrawal_end_year: {
    purpose: "This is the final year the plan will make scheduled HSA withdrawals (only applies to 'annual percentage' or 'smooth window' modes). Leave it blank to avoid any scheduled withdrawal deadline.",
    impact: "Setting an end year stops all planned withdrawals after that year. Leaving it blank means withdrawals continue indefinitely until manually changed. This lets you plan when you want scheduled HSA draws to finish.",
    consider: "Set this to match a major life event when you expect HSA needs to end, like when your spouse reaches Medicare, or leave it blank if you want maximum flexibility to adjust later.",
  },
  hsa_withdrawal_mode: {
    purpose: "This selects how the plan withdraws from your HSA: 'spend as needed' uses the HSA only when cash is tight, 'annual percentage' withdraws a set percentage each year, or 'smooth window' divides the balance evenly across a span of years. Each mode treats HSA differently in your plan.",
    impact: "'Spend as needed' preserves HSA for true emergencies and lets it grow longer. 'Annual percentage' forces regular withdrawals regardless of need, spending it faster. 'Smooth window' creates a predictable schedule. Choosing differently changes when and how much of the HSA gets depleted.",
    consider: "Use 'spend as needed' if you want HSA to stay invested as a backup fund. Use 'annual percentage' or 'smooth window' if you have a specific draw-down plan in mind. Most people pick 'spend as needed' unless they have strong reasons to systematically withdraw.",
  },
  hsa_withdrawal_start_year: {
    purpose: "This is the first year the plan will make scheduled HSA withdrawals (only applies to 'annual percentage' or 'smooth window' modes). Leave it blank to avoid any scheduled withdrawal start date.",
    impact: "Setting a start year delays withdrawals until that year arrives. Leaving it blank means withdrawals never automatically begin unless changed. This lets you plan when systematic HSA draws should kick in.",
    consider: "Set this to a year when you expect significant medical costs or when you want to begin a deliberate drawdown strategy. For example, set it to age 70 if you want withdrawals to start then, or leave blank if you prefer to decide later.",
  },
  first_payment: {
    purpose: "This is the date when your pension or annuity income starts being paid to you. The plan uses this date to know when payments begin and how long they will cover.",
    impact: "An earlier start date means income begins sooner, supporting expenses earlier in retirement. A later start date delays that income stream. The timing affects when other assets might need to cover expenses before this income starts.",
    consider: "Enter the date shown in your pension agreement or annuity contract. If you can choose when to start, an earlier date increases near-term spending power but may reduce the total lifetime payment.",
  },
  initial_guaranteed_income_payment: {
    purpose: "This is the monthly dollar amount your pension or annuity guarantees to pay you starting in the first year. This is the base payment that then grows (if your contract includes growth or dividends).",
    impact: "Raising this amount increases your guaranteed monthly income and improves plan safety. Lowering it reduces guaranteed income. Higher payments accelerate your transition out of portfolio withdrawals and reduce spending power later.",
    consider: "Look at your pension statement or annuity contract for the guaranteed monthly benefit amount. If you haven't claimed your pension yet, this is the monthly amount you'll receive when you do.",
  },
  payout_type: {
    purpose: "This selects how your income payment behaves in stress-test scenarios: 'Fixed' means it never changes, 'Variable' scales with portfolio returns, or 'COLA' scales with inflation. This has no effect on your base plan, only on Monte Carlo risk testing.",
    impact: "'Fixed' ignores market and inflation changes. 'Variable' can help if returns beat expectations but hurt if they underperform. 'COLA' protects you if inflation rises. The choice affects how realistic your stress-test scenarios are.",
    consider: "Most traditional pensions are fixed; if yours adjusts for inflation, pick COLA. If it's truly fixed, pick Fixed. If it varies with company earnings or fund performance, pick Variable. Ask your pension administrator how yours works.",
  },
  qualified: {
    purpose: "This marks whether your annuity or pension comes from an employer-sponsored retirement plan (qualified) or from personal after-tax savings (non-qualified). This determines how much of each payment is taxable.",
    impact: "Qualified income is fully taxable when you withdraw it. Non-qualified income uses an exclusion ratio so you recover your basis tax-free before the rest becomes taxable. Getting this wrong can significantly over- or under-estimate your tax burden.",
    consider: "If your income came from an employer pension or 401(k), it's qualified. If you bought an annuity with your own after-tax money, it's non-qualified. Check your contract or ask the company that issued it.",
  },
  base: {
    purpose: "This is the starting account value or reserve that the insurance company uses to calculate your annuity's growth and dividends each year. All future growth compounds on this base.",
    impact: "A higher base produces more total growth and more annual dividend credits (if your annuity includes dividends). A lower base produces less growth. The base anchors the long-term income potential of the annuity.",
    consider: "Find this on your most recent annuity statement under account value, contract value, or actuarial reserve. If your annuity has been running for years, this is the current accumulated value, not the original purchase price.",
  },
  benefit_period_years: {
    purpose: "This is how long your disability insurance will pay benefits if you become unable to work — in this case, until age 65. After that age, benefits stop regardless of whether you're still disabled.",
    impact: "Stopping at age 65 means you need other income sources after that age (Social Security, retirement savings, spousal income). If the period extended longer, you'd have disability support for more years. This is typical for group employer plans.",
    consider: "This is usually set by your employer's plan and can't be changed. Verify your actual benefit period by checking your disability insurance policy or summary of coverage.",
  },
  elimination_days: {
    purpose: "This is the waiting period before your disability insurance starts paying — the number of days you must be unable to work before your first payment arrives. Common waiting periods are 30, 60, or 90 days.",
    impact: "A longer elimination period means you wait longer before payments begin, so your emergency savings must cover more time. A shorter period starts payments sooner. Longer waiting periods usually have lower premiums.",
    consider: "Check your disability insurance policy for your elimination period. If you have 3-6 months of expenses saved, a 90-day wait is manageable; if not, that gap creates real risk. Some plans let you choose between waiting periods.",
  },
  monthly_benefit: {
    purpose: "This is the maximum monthly payment your disability insurance will pay if you become unable to work. It's typically 60-70% of your gross pre-disability salary.",
    impact: "A higher benefit means more income support if disabled, reducing the gap you'd need to fill from savings. A lower benefit means you'd rely more on personal assets. This is a key number determining if disability protection is adequate.",
    consider: "Find this amount on your disability insurance policy or benefits summary. If it's less than 60% of your current income, your savings would need to supplement it during a disability. If it's more than you need, the excess is just unused capacity.",
  },
  premium_annual: {
    purpose: "This is the annual cost you pay for your disability insurance coverage. For employer plans, it may come out of your paycheck automatically; for individual policies, you pay it yourself.",
    impact: "This cost reduces your net income or savings each year. The plan uses this to calculate your total out-of-pocket insurance costs. Lowering premiums saves cash but may mean lower benefits or longer waiting periods.",
    consider: "If your employer covers the full premium, you pay zero. If it's partially covered, find your employee contribution. For individual policies, check your policy document for the annual cost. If the premium seems high relative to benefits, get quotes from other providers.",
  },
  premium_pre_tax: {
    purpose: "This indicates whether your disability benefit is taxable when you receive it. If the premium is paid with pre-tax dollars, the benefit is taxable income. If paid with after-tax dollars, the benefit is tax-free.",
    impact: "Taxable benefits reduce your net income since you owe tax on the payments. Tax-free benefits are worth more in your pocket. This choice is usually determined by whether your employer deducts the premium before or after taxes, not something you control.",
    consider: "Ask your HR or benefits administrator whether your disability premium is deducted pre-tax or post-tax. If pre-tax, plan for taxes on disability income if you ever need it. If post-tax, the full benefit arrives tax-free.",
  },
  simulate_disability_year: {
    purpose: "This triggers a 'what-if' test to see how your plan holds up if you become disabled in the specified year. Enter a year number or leave at 0 for no simulation. This stress-tests whether your income and savings would survive a disability during that year.",
    impact: "Simulating a disability year shows you a worst-case scenario where disability income replaces your salary for a period. If the plan still succeeds, you know you're protected. If it fails, you may need more insurance or savings.",
    consider: "Try simulating disability in different years — early retirement, later years, or peak spending years — to see when you're most vulnerable. If the plan fails in any scenario you care about, increase disability insurance coverage or boost savings.",
  },
  policy_count: {
    purpose: "This is the total number of traditional life insurance policies you currently have in force, not counting any death benefits in annuities (which are tracked separately). If you have one term policy and one whole-life policy, enter 2.",
    impact: "This is mainly a tracking number to help organize your coverage. More policies mean more coverage (assuming sufficient death benefits per policy), but also more premiums and policies to manage.",
    consider: "Count only active policies you're paying premiums for right now. Don't count expired or lapsed policies. If you're unsure what you have, contact your insurance agent or review your most recent statements.",
  },
  annual_premium: {
    purpose: "The yearly cost to keep an insurance policy active. This amount is charged each year while the policy remains in force.",
    impact: "Higher premiums reduce cash available for other expenses or saving. Lower premiums reduce annual costs but might reflect less coverage or different policy terms.",
    consider: "Check whether the premium stays level throughout the coverage period or increases over time, as some policies reset or adjust their rates.",
  },
  cash_value_growth_rate: {
    purpose: "For whole life or universal life insurance, the annual growth rate of the cash value — the savings component you can borrow against or withdraw. This is the expected yearly percentage return on that savings portion.",
    impact: "A higher growth rate means the cash value accumulates faster, giving you more options later like policy loans or withdrawals. A lower rate means slower accumulation and less borrowing capacity as the policy ages.",
    consider: "Compare this rate to other savings vehicles (CDs, money market funds) to decide if whole life's guaranteed growth inside an insurance policy makes sense for your goal.",
  },
  cash_value_today: {
    purpose: "The current balance of the savings portion within a whole or universal life insurance policy. This is cash you can borrow against (usually tax-free under policy-loan rules) or sometimes withdraw.",
    impact: "A higher cash value gives you more flexibility to cover future premiums or emergencies through policy loans. A lower cash value limits those options and means you rely more on regular premium payments.",
    consider: "If you've held a whole life policy for many years, check your policy statement to see what cash value is actually available before changing your premium or coverage assumptions.",
  },
  face_amount: {
    purpose: "The lump-sum dollar amount the insurance company pays your beneficiaries when you pass away. This is the core death benefit of a life insurance policy.",
    impact: "A higher face amount means your heirs receive more money, but premiums are usually higher and harder to afford long-term. A lower face amount cuts premiums but leaves your family with less financial protection.",
    consider: "Think about what your family would need to replace your lost income, pay off debts, or fund education goals if you were gone. That's the starting point for how much death benefit to choose.",
  },
  insured: {
    purpose: "The person whose life is being insured by this policy.",
    impact: "Life insurance only pays a benefit if the insured person passes away during the coverage period. Changing who is insured changes the insurance risk and the premium.",
    consider: "Make sure the person named as insured matches who you intend to protect against financial loss.",
  },
  owned_by_ilit: {
    purpose: "An ILIT (Irrevocable Life Insurance Trust) is a legal trust that owns and controls the life insurance policy instead of the person being insured. This setting marks whether the policy is owned that way.",
    impact: "When owned by an ILIT, the policy death benefit is generally excluded from the insured person's taxable estate, saving estate taxes, but the insured loses direct access to cash value and flexibility. When owned directly, the benefit is taxable in their estate, but they keep full control.",
    consider: "ILIT ownership is mainly useful for high-net-worth households trying to reduce estate taxes. If your estate is much smaller than current exemption limits, direct ownership is simpler and keeps your control.",
  },
  policy_type: {
    purpose: "The category of insurance — such as term life, whole life, homeowners, auto, or umbrella. This determines how the coverage works and what is protected.",
    impact: "Different policy types have different costs, duration, and features. Term insurance is cheaper but only covers a set number of years; whole life is more expensive but covers for life and builds cash value. Property and casualty policies protect assets and liability but not life.",
    consider: "Match the policy type to your need — term life for temporary income replacement, whole life for permanent coverage, and property/casualty for asset and liability protection.",
  },
  premium_end_year: {
    purpose: "The year in which premium payments are no longer required for this policy. After this year, the policy can continue in force without you sending payment.",
    impact: "A near-term premium-end year reduces your future cash flow pressure but may require higher premium payments now or a sufficient cash value cushion. A later premium-end year spreads payments over more years and is easier on annual cash flow but extends the payment commitment.",
    consider: "For whole life policies, the premium-end year often means the policy will be paid up by then (cash value covers future premiums); check your policy to see if the cash value is expected to sustain it or if you'll keep paying.",
  },
  term_end_year: {
    purpose: "The year in which the insurance coverage ends and the policy is no longer in force. After this date, no death benefit is paid even if the insured person passes away.",
    impact: "An earlier term-end year means lower total premiums but less protection in later years. A later term-end year extends coverage into more of retirement, providing longer protection but higher total premiums paid.",
    consider: "For term life, aim to have coverage end around when your biggest financial obligations (mortgages, kids' education, income replacement needs) are expected to be paid off.",
  },
  coverage_limit: {
    purpose: "The maximum dollar amount the insurance company will pay out for a covered loss under this policy. For homeowners insurance, this is the limit for your house; for auto, the limit per accident.",
    impact: "A higher limit means you're protected against larger losses, but premiums are higher. A lower limit reduces your premium but leaves you exposed if a loss exceeds the limit — you'd have to pay the overage yourself.",
    consider: "Set limits based on what it would actually cost to rebuild or replace your home or car, and what liability exposure you face if someone is injured on your property or you're in an at-fault accident.",
  },
  deductible: {
    purpose: "The dollar amount you agree to pay out of your own pocket before the insurance company starts paying for a covered loss. A higher deductible means lower premiums; a lower deductible means higher premiums.",
    impact: "Choosing a higher deductible lowers your premium but means you absorb more of smaller claims. Choosing a lower deductible raises your premium but the insurance company picks up more of the cost if something happens.",
    consider: "Set your deductible based on what you can comfortably afford to pay if a loss happens — often $500 to $1,000 for homeowners or auto — then decide whether the premium savings from a higher deductible make sense for your budget.",
  },
  umbrella_target_multiple_of_nw: {
    purpose: "Umbrella insurance is a separate liability policy that kicks in after your homeowners and auto insurance limits are exhausted. This setting recommends how much umbrella coverage you should carry, expressed as a multiple of your total net worth.",
    impact: "A higher multiple (e.g., 2x net worth) means more umbrella coverage and higher premiums but protects you more completely against catastrophic liability judgments. A lower multiple cuts premiums but leaves a bigger gap if you're sued for a large amount.",
    consider: "High-net-worth households often carry 1 to 2 times net worth in umbrella coverage to guard against lawsuit risk. If your net worth is smaller, umbrella insurance is less urgent but still affordable.",
  },
  cash_target_pct: {
    purpose: "Cash target is the percentage of your investment portfolio you want to hold in cash or cash equivalents like money-market funds. This acts as a buffer protecting you from being forced to sell stocks at bad times to meet spending needs.",
    impact: "A higher cash target gives you more cushion and means you're not forced to sell investments when market prices are down. A lower cash target puts more money to work for growth but requires discipline about not raiding it for non-emergencies.",
    consider: "A common starting point is 1 to 2 years of annual spending in cash; this helps you weather a market downturn without selling stocks at poor prices.",
  },
  concentration_business: {
    purpose: "The percentage of your total wealth (home, investments, business, all assets combined) that is tied up in a business you own. This measures how concentrated your wealth is in a single business entity.",
    impact: "Higher business concentration means more of your net worth depends on one company's success, creating risk if the business struggles. Lower concentration spreads wealth across more assets and sources, reducing the impact of any single business's performance.",
    consider: "If your business is your largest asset, think about whether it's realistic to eventually sell it, pass it down, or what happens if it runs into trouble. Many successful business owners aim for business to be no more than 50 percent of total wealth for safety.",
  },
  concentration_employer_stock: {
    purpose: "The percentage of your total wealth that is in stock of the company where you work. This measures how much of your wealth is tied to one employer's success.",
    impact: "High employer stock concentration means your paycheck, retirement account, and wealth all depend on the same company. If the company struggles, you lose income and savings at the same time. Lower concentration spreads the risk.",
    consider: "Many people accumulate employer stock through options, matching, or RSUs. If it has grown to more than 10 to 15 percent of your portfolio, consider selling some to diversify and reduce the 'all eggs in one basket' risk.",
  },
  concentration_real_estate: {
    purpose: "The percentage of your total wealth that is in non-home real estate — such as rental properties, farmland, or commercial real estate. Your primary home is usually tracked separately.",
    impact: "Higher real-estate concentration means a large part of your wealth is illiquid (hard to sell quickly) and depends on local property markets and rental income. Lower concentration means easier access to cash, but you miss potential real-estate returns.",
    consider: "Real estate can be a good long-term investment and inflation hedge, but it requires management and is hard to liquidate. Make sure you're comfortable with illiquidity if a large portion of wealth is in rental properties.",
  },
  human_capital_stability: {
    purpose: "A score (typically 0.5 to 0.8) that reflects how stable and predictable your income is. 0.8 means stable (like a W-2 employee at an established company), and 0.5 means variable (self-employed, commission-based, or cyclical income).",
    impact: "Higher stability means your income is predictable, so the plan can assume more investment risk and a growth-oriented portfolio. Lower stability means income is uncertain, so the plan should be more conservative to cushion income swings.",
    consider: "If you have a guaranteed salary and pension, you're closer to 0.8. If you're self-employed with highly variable revenue, you're closer to 0.5. Use this to match your investment risk to your income stability.",
  },
  include_home_equity_in_allocation_view: {
    purpose: "This setting controls whether your primary home's equity is included in your overall portfolio allocation view. Home equity is the value of your house minus any mortgage balance.",
    impact: "When YES, home equity shows up as part of your total wealth and allocated to real estate, making your portfolio look more conservative and diversified. When NO, only your investments and other liquid assets are shown, which may look more growth-oriented.",
    consider: "Include home equity if you want to see your full wealth picture and think of the home as part of your long-term allocation. Exclude it if you plan to live in the home forever and want to focus on investment portfolio allocation only.",
  },
  inflation_sensitive_spending_pct: {
    purpose: "The percentage of your annual spending that is sensitive to inflation — tends to go up with prices — like groceries, utilities, and gas. The rest is relatively fixed like mortgage or insurance.",
    impact: "A higher inflation-sensitive percentage means more of your budget will be hit by inflation; the plan will be more conservative. A lower percentage means you're assuming much of your spending is fixed, so inflation hurts you less.",
    consider: "Start with about 15 percent for most households. If you drive a lot or heat a large home, go higher. If your mortgage is nearly paid off, inflation hurts you less, so go lower.",
  },
  liquid_reit_target_pct_when_home_not_counted: {
    purpose: "The target percentage of your investment portfolio that should be in liquid REITs (Real Estate Investment Trusts, which trade on stock exchanges like regular stocks) — used only if home equity is not already included in your allocation view. REITs give you stock-like real-estate exposure.",
    impact: "A higher REIT target means more real-estate exposure through the stock market without buying physical property. A lower target reduces that exposure and puts more weight on stocks and bonds.",
    consider: "REITs are a convenient way to get real-estate diversification without owning rental property. A default of 5 percent is a common starting point; if you already own rental properties, you might lower this target to avoid overconcentration in real estate.",
  },
  risk_tolerance: {
    purpose: "This setting controls how aggressive or conservative your investment mix is. Set it to 0 to let the plan automatically pick based on your age and spending rate, or choose 1-10 yourself for full control.",
    impact: "Higher risk tolerance means more stocks and faster growth potential but bigger portfolio swings. Lower tolerance means more bonds and steadier but slower growth.",
    consider: "If market drops keep you up at night, pick a lower number. If you can stay calm during downturns, you can go higher.",
  },
  cash_pct: {
    purpose: "This is the percentage of your portfolio kept in cash and money market accounts — readily available money that doesn't fluctuate. Cash is safe but grows slowly.",
    impact: "Higher cash allocation means less money working in stocks or bonds to grow long-term. Lower cash means more growth potential but less cushion for emergencies.",
    consider: "Most retirees hold 1-3 years of spending in cash; adjust this based on how quickly you might need access.",
  },
  commodity_pct: {
    purpose: "This is the portion of your portfolio in commodities and real assets like metals, energy, or real estate. They sometimes move independently of stocks and bonds, which can reduce overall portfolio wobbliness.",
    impact: "Higher commodity allocation adds diversification but also complexity and cost. Lower allocation simplifies your portfolio and leaves room for stocks or bonds.",
    consider: "Commodities are optional; many households do fine with just stocks and bonds.",
  },
  equity_pct: {
    purpose: "This is the percentage of your portfolio in stocks and equity-based funds. Stocks typically grow faster over long periods but bounce up and down more than bonds or cash.",
    impact: "Higher equity percentage means more growth potential but bigger short-term swings. Lower percentage means more stability but slower long-term growth.",
    consider: "Younger households often hold more stocks; older ones typically shift toward bonds. Adjust based on how long you'll need the money.",
  },
  ltcg_0pct_top_mfj_base_year: {
    purpose: "This is the top income level for the 0% federal tax rate on long-term investment gains if you're married filing jointly. Above this amount, gains face a 15% tax rate. The plan adjusts this each year for inflation.",
    impact: "When your income gets close to this threshold, selling appreciated investments can trigger higher taxes. Knowing the threshold helps you time sales to stay in the 0% bracket.",
    consider: "If your income lands near this threshold, consider spreading sales across years to minimize taxes.",
  },
  ltcg_15pct_top_mfj_base_year: {
    purpose: "This is the top income level for the 15% tax rate on long-term capital gains if married filing jointly. Above this, gains are taxed at 20%. The plan adjusts this each year for inflation.",
    impact: "When your income exceeds this threshold, all gains face the highest capital gains tax rate. This affects whether it makes sense to bunch or spread investment sales across years.",
    consider: "If you're close to this threshold, deferring some sales to lower-income years can save taxes.",
  },
  selling_cost_pct: {
    purpose: "This is the total cost to sell your home as a percentage of the sale price — realtor commissions, closing costs, title insurance, and other fees. Usually runs 5-10% in most areas.",
    impact: "Higher selling costs reduce the cash you receive after a home sale. The plan subtracts these costs when calculating how much proceeds are available to spend.",
    consider: "Contact your realtor and a title company to get an accurate total for your area and home value.",
  },
  irmaa_actual_magi_1yr_prior: {
    purpose: "Medicare premiums (IRMAA) are based on income from 1-2 years in the past. This field is where you enter your actual household income from the tax year right before your plan starts, from your filed tax return.",
    impact: "The plan uses this to calculate year 2 of Medicare premiums accurately. Leaving it blank forces the plan to estimate, which may be less precise.",
    consider: "Pull your tax return from last year and enter the exact figure; this makes your Medicare forecast more reliable.",
  },
  irmaa_actual_magi_2yr_prior: {
    purpose: "This is your actual household income from the tax year two years before your plan starts, from your filed tax return. Social Security uses this to calculate year 1 of Medicare premium surcharges.",
    impact: "Using the actual number gives a precise forecast for your first year of Medicare costs. Leaving it blank forces an estimate.",
    consider: "If your income was unusually high or low two years ago, using the real number matters even more.",
  },
  irmaa_annual_inflator: {
    purpose: "This is the annual percentage increase applied to Medicare IRMAA income thresholds each year. Congress sets this each year, and it usually runs 1-3%.",
    impact: "Higher inflation means thresholds rise faster, so you're less likely to cross into higher surcharge tiers. Lower inflation means thresholds stay lower.",
    consider: "Check Medicare.gov or Social Security's latest guidance for the current year's rate; ask your tax advisor if unsure.",
  },
  inflation_sigma: {
    purpose: "This measures how much inflation bounces around year-to-year in the plan's stress-test simulations. Higher values mean the model assumes inflation could swing wider in either direction.",
    impact: "Higher inflation volatility creates a wider range of possible spending-power outcomes in the simulations. Lower volatility means outcomes cluster more tightly.",
    consider: "This is an internal modeling parameter your advisor sets based on historical inflation data; you typically don't adjust it.",
  },
  mc_engine_mode: {
    purpose: "This chooses which Monte Carlo engine version to use. 'Exact scalar' is the standard, slower but precise path-by-path. 'Vectorized' is much faster but gives approximate results.",
    impact: "Exact mode takes longer to run but gives true individual simulation paths. Vectorized is much faster and fine for quick checks but should not be used for final client advice.",
    consider: "Use exact mode for actual client plans and final presentations. Use vectorized only for fast diagnostics and testing.",
  },
  mc_home_equity_access_lag_years: {
    purpose: "This is how many years must pass before your home equity can be tapped as a backup if investments run low. It represents the realistic time to sell your home if needed.",
    impact: "Longer lags mean home equity is treated as less immediately available in early retirement, making the plan more conservative. Shorter lags count it as a quicker safety net.",
    consider: "If you could realistically sell and move within one year, use 1. If it would take longer or feels uncertain, use 2-3.",
  },
  mc_home_equity_contingency: {
    purpose: "This turns on a safety net where the plan counts your home equity (after a realistic haircut) as spendable money if investments run out. It's a worst-case-scenario backup plan.",
    impact: "When enabled, success rates often improve because the plan assumes you could downsize or tap home equity as a last resort. When disabled, the plan is more conservative.",
    consider: "Enable this if you would actually be willing to sell and downsize in a crisis. Leave it off if home equity is not available to you.",
  },
  mc_home_equity_haircut: {
    purpose: "This is a discount applied to your home equity when it is used as a backup in stress scenarios. A 30% haircut means the plan counts only 70% of estimated home value as spendable.",
    impact: "A bigger haircut (higher percentage) means less available home equity in a pinch, making the plan more pessimistic. A smaller haircut counts more of the home's value.",
    consider: "Use 20-30% to account for selling costs, potential market declines, and timing risk. Ask a realtor or appraiser what's realistic in your area.",
  },
  mc_portfolio_sigma: {
    purpose: "This is a measure of how much your portfolio bounces up and down from year to year — its standard deviation. It captures how 'choppy' your investments are.",
    impact: "Higher sigma means bigger portfolio swings in the simulations; lower sigma means smoother returns. This directly affects how often the plan runs out of money in stress scenarios.",
    consider: "A typical stock/bond mix has sigma of 6-12%. Your advisor usually sets this based on your actual allocation and historical returns.",
  },
  mc_sensitivity_simulations: {
    purpose: "When the plan tests how sensitive results are to different market assumptions, this is how many simulation paths to run for each tested scenario. Higher numbers mean more thorough testing.",
    impact: "Higher number means more detailed sensitivity analysis with smoother results but slower runtime. Lower number runs faster with choppier answers.",
    consider: "Start with 100-500 for interactive work; bump to 1,000+ for final client presentations if time allows.",
  },
  mc_simulations: {
    purpose: "This is the total number of Monte Carlo simulation paths the plan runs to test your retirement plan. More paths mean more reliable and smoother results.",
    impact: "Higher number means more thorough testing and smoother outcomes but slower computer runtime. Lower number runs faster but produces less precise results.",
    consider: "Start with 1,000 for speed; use 5,000+ for final client advice if your computer can handle the run time.",
  },
  recenter_regime_returns: {
    purpose: "Adjusts random market return paths to ensure they match your assumed average long-term return. The calculator checks that its random scenarios average out correctly.",
    impact: "When on, randomness is adjusted so averages match your assumptions; when off, they might drift. This keeps your plan grounded in realistic long-term expectations.",
    consider: "Leave this on unless you're testing edge cases or have a specific reason to see raw unadjusted randomness.",
  },
  stochastic_inflation: {
    purpose: "Treats inflation as random year-to-year, with changes that move together with market performance, instead of assuming it's steady. Real inflation bounces around; this models that.",
    impact: "With this on, inflation varies; without it, inflation is flat. Variable inflation can make some years harder and others easier, making your plan more realistic but less predictable.",
    consider: "Turn this on for a realistic plan; off if you prefer smooth, simple scenarios for testing.",
  },
  stochastic_tax_brackets: {
    purpose: "Adds random variation to how tax brackets grow, instead of assuming they grow exactly with inflation. Tax law changes unpredictably.",
    impact: "With this on, tax brackets wander around inflation; off, they track it perfectly. This slightly changes how much tax you owe in edge cases.",
    consider: "Turn this on for realism, though the impact is usually small.",
  },
  use_asset_class_covariance: {
    purpose: "Uses historical correlations between stocks, bonds, and other investments (they don't all move the same way) to model returns realistically. When stocks fall, bonds often hold up, and vice versa.",
    impact: "With this on, diversification is captured in the random scenarios (different assets move together realistically); off, they're treated independently. This mostly matters during downturns.",
    consider: "Turn this on — it makes the plan's risk profile more accurate.",
  },
  wellness_cost_shocks: {
    purpose: "Models unexpected major health expenses as random events, instead of assuming health costs grow predictably. Real life includes surprise medical bills.",
    impact: "With this on, some scenarios include a large unexpected health cost; without it, spending is smooth. This makes your plan more resilient to real-world surprises.",
    consider: "Turn this on if health concerns you; it's a major unknown in retirement.",
  },
  wellness_shock_annual_prob: {
    purpose: "The yearly probability (as a percentage) that a major health expense happens. If you set 5%, there's a 5% chance each year.",
    impact: "Higher percentage makes big health events more likely to show up in your plan results; lower makes them rarer. Over 30+ years, even small percentages add up.",
    consider: "Think about your family's health history. Are major health events common or rare? Set the probability accordingly.",
  },
  wellness_shock_mean_cost: {
    purpose: "The average cost (in dollars) when a major health expense happens. This is what you expect to pay if a big health event occurs.",
    impact: "Higher cost means a bigger hit to the plan when (or if) it happens; lower means less disruption. This directly affects how much financial cushion you need.",
    consider: "Research typical costs for potential health scenarios that concern you and use a realistic average.",
  },
  rollover_401k_year: {
    purpose: "The year when a 401(k) balance moves into an IRA. A 401(k) is an employer retirement account; an IRA is an Individual Retirement Account. This usually happens when you leave a job or retire.",
    impact: "This year marks when the 401(k) is treated as an IRA for tax and withdrawal purposes going forward. It affects when required minimums kick in later.",
    consider: "Roll over soon after leaving the job. The exact year rarely matters unless it's very close to required minimum or penalty-free withdrawal ages.",
  },
  spending_freeze_year: {
    purpose: "The year when your base spending stops rising with inflation and stays flat in real dollars. Inflation continues around you, but your personal spending is locked.",
    impact: "Frozen spending means each year you spend a smaller percentage of total costs (because prices around you keep rising). You'll need to live on an increasingly lean budget or accept that the freeze doesn't actually apply.",
    consider: "Set this when you expect a major spending drop (kids grown, house paid off, big travel years end). If you're unsure, leave it years in the future.",
  },
  roth_conv_window_end_offset: {
    purpose: "The last year you'll do Roth conversions, measured as years before you start taking Required Minimum Distributions. A Roth conversion moves pre-tax money into a Roth account (taxable that year, but tax-free later). This setting determines when to stop.",
    impact: "Earlier cutoff means fewer conversions in later years (and less tax paid then but more later); later means conversions continue longer even after minimums start. Conversions are taxable, so the timing matters for tax planning.",
    consider: "Stopping a year or two before minimums is standard, since minimums are already forcing large withdrawals and might not leave room for conversions.",
  },
  annual_principal_base_period: {
    purpose: "The fixed annual payment amount for the first years (1-7) of a note you're receiving. A note is a loan you made where someone promises to pay you back over time.",
    impact: "This is your annual cash inflow from that loan during the early period. It goes into your income and helps fund your retirement.",
    consider: "Match this to your loan agreement. If payments decline or change mid-loan, you'll need to adjust it for later years.",
  },
  final_principal_2033: {
    purpose: "The remaining loan balance due as a final lump-sum payment in year 8. This completes the payoff of the note.",
    impact: "This lump-sum payment is a cash inflow in that final year. It should represent whatever principal is left after all the earlier annual payments.",
    consider: "Check your loan documents. Your total cash from the note (all yearly payments plus this lump sum) should equal your original loan amount.",
  },
  last_payment: {
    purpose: "The date when the entire note (loan) is fully paid off. This marks the end of cash flow from this note.",
    impact: "After this date, you no longer receive payments from the loan. It's mainly informational but helps ensure the plan doesn't expect phantom payments.",
    consider: "Match this to your loan agreement's final payment date.",
  },
  business_succession: {
    purpose: "A planning module for strategies to pass a business to family, a buyer, or a trust after you retire or pass away. It covers how to value the business, minimize taxes, and ensure a smooth transition.",
    impact: "When on, you can plan the business exit in detail; off, business transition isn't planned. Relevant mainly if you own a significant business.",
    consider: "Turn on if business succession is a major part of your estate plan or retirement strategy.",
  },
  charitable_giving: {
    purpose: "A planning module for optimizing charitable donations, including QCD (Qualified Charitable Distributions from an IRA at age 70½+), gift bunching, and deductions. It helps you give more tax-efficiently.",
    impact: "When on, you can model different giving strategies year-by-year and see tax impacts; off, giving strategies aren't analyzed. This is valuable if charity is important to you and you want to minimize taxes while giving.",
    consider: "Turn on if you plan to give to charity and want to optimize both the giving amount and your tax burden. Especially useful at age 70½+.",
  },
  charts_dashboard: {
    purpose: "A worksheet that pulls all of your plan's charts and graphs into one place for easy review. Instead of flipping through the workbook, you see the visuals together.",
    impact: "When on, you get a dedicated summary sheet with all charts; off, charts stay scattered through the workbook. This is purely for convenience and presentation.",
    consider: "Turn on if you like visual summaries or plan to present your plan to others (advisor, family, etc.). Otherwise it's optional.",
  },
  disability_income_insurance: {
    purpose: "A planning module for analyzing whether you have enough disability insurance to replace income if you can't work before retirement. It helps you size the coverage you need.",
    impact: "When on, you can model income-loss scenarios and coverage needs; off, disability risk is ignored. Mostly relevant for working-age members.",
    consider: "Turn on if you're still working and earning significant income. If you're retired, disability risk is lower.",
  },
  divorce_qdro: {
    purpose: "A planning module for modeling the financial impact of a divorce and court-ordered asset splits (QDRO — a Qualified Domestic Relations Order) on your retirement accounts. It lets you see how different settlements affect your plan.",
    impact: "When on, you can test divorce scenarios and settlement structures; off, divorce is not modeled. Specialized and only relevant if divorce is a possibility.",
    consider: "Turn on if you're considering or mediating a divorce and want to see scenarios. Otherwise leave it off.",
  },
  education_funding_529: {
    purpose: "A 529 plan is a tax-advantaged savings account for education costs. This setting lets the plan include education funding goals and track how money saved in 529 accounts contributes to future college or school tuition.",
    impact: "When enabled, the plan shows dedicated sheets for education goals and 529 balances, and calculates how much to save in 529s to cover future education expenses without draining retirement savings.",
    consider: "Turn this on if you have children or grandchildren whose college or school costs you want to plan for separately from retirement.",
  },
  equity_compensation: {
    purpose: "Equity compensation like RSUs (Restricted Stock Units), ISOs (Incentive Stock Options), NSOs (Non-Qualified Stock Options), and ESPPs (Employee Stock Purchase Plans) are ways employers pay part of your income in company stock. This setting lets you model when and how to sell or exercise these positions and the tax impact.",
    impact: "When enabled, the plan shows detailed sheets for when to exercise options, sell RSUs, or participate in an ESPP, and calculates the tax effects of capital gains and alternative minimum tax exposure.",
    consider: "Turn this on if your employer gives you stock options or RSUs as part of your compensation package.",
  },
  estate_legacy_plan: {
    purpose: "Estate planning covers what happens to your assets after you pass away — wills, trusts, life insurance proceeds, and passing wealth to heirs. This setting adds analysis for estate and legacy goals.",
    impact: "When enabled, the plan includes sheets for estate structure and legacy planning, and calculates how your assets will transfer and what taxes or costs apply.",
    consider: "Turn this on if you want to make sure your assets go where you intend, or if you have a complex estate with multiple heirs or trusts.",
  },
  existing_life_insurance: {
    purpose: "Life insurance pays a benefit to your family if you pass away. This setting lets you include existing life insurance policies in the plan and see how they affect your family's finances if something happens to you.",
    impact: "When enabled, the plan includes any existing life insurance benefits in calculations for survivor scenarios, which may reduce the need to liquidate investments or the amount of additional life insurance the plan would recommend.",
    consider: "Turn this on if you have life insurance through an employer, a private policy, or mortgage protection insurance.",
  },
  gain_harvesting: {
    purpose: "Gain harvesting is an investment strategy of intentionally selling investments at a profit during low-income years to take advantage of lower tax rates, then buying back similar investments. This setting analyzes when this strategy might save you taxes.",
    impact: "When enabled, the plan identifies years when gain harvesting might reduce lifetime taxes and calculates the tax savings from strategically realizing capital gains during favorable years.",
    consider: "This tends to help most in early retirement before Social Security starts, or in years with large charitable deductions that lower your tax rate.",
  },
  glossary: {
    purpose: "A glossary explains financial and retirement planning terms used throughout the plan. This setting shows or hides the glossary sheet in the workbook.",
    impact: "When enabled, a glossary sheet is included in the workbook to help you look up terms you're unfamiliar with.",
    consider: "Turn this on if you're new to retirement planning or want a handy reference for terms used in the plan.",
  },
  life_insurance_need: {
    purpose: "A life insurance need analysis calculates how much life insurance you should have to replace lost income and cover expenses if you pass away. This setting adds that analysis.",
    impact: "When enabled, the plan shows how much life insurance death benefit would be needed to protect your family if you die, which you can compare against existing coverage.",
    consider: "Use this to make sure you're not overinsured (paying for coverage you don't need) or underinsured (risking your family's security).",
  },
  lifetime_tax_projection: {
    purpose: "This shows your projected tax bill for each year throughout retirement. This setting turns on detailed tax projections.",
    impact: "When enabled, the plan includes a detailed sheet showing income taxes, capital gains taxes, and other taxes year by year, helping you understand and potentially reduce your lifetime tax burden.",
    consider: "Use this to spot high-tax years where strategies like Roth conversions or charitable giving might help reduce what you owe.",
  },
  long_term_care_stress: {
    purpose: "A long-term care stress test models what happens to your finances if you need extended nursing home, assisted living, or in-home care during retirement — often a major cost. This setting runs that scenario.",
    impact: "When enabled, the plan shows a scenario where you need years of paid long-term care and whether your assets are enough to cover it, helping you understand your vulnerability and whether long-term-care insurance might help.",
    consider: "The cost and duration of care vary widely by location and care type — model a few scenarios (1 year, 3 years, 5+ years) to understand your exposure.",
  },
  market_luck_stress_test: {
    purpose: "A Monte Carlo stress test runs hundreds of simulations with different random stock and bond returns to see how often your retirement plan stays on track even in unlucky market years. This setting adds that analysis.",
    impact: "When enabled, the plan shows what percent of scenarios result in your money lasting through retirement, helping you understand the risk that you might run short if markets perform poorly early in retirement.",
    consider: "Aim for an 80-90% success rate in typical models; higher rates require larger savings or lower spending, lower rates accept more risk of shortfall.",
  },
  methodology_rerun: {
    purpose: "This sheet explains how the plan was built, what assumptions it uses, and how to recalculate the plan if you change inputs. This setting shows or hides that reference sheet.",
    impact: "When enabled, a methodology sheet is included in the workbook documenting the assumptions and rebuild steps.",
    consider: "Turn this on if you want to understand how the numbers were generated or how to refresh the plan if you update information.",
  },
  property_casualty_umbrella: {
    purpose: "Property and casualty insurance covers damage to your home and car; umbrella liability insurance covers large lawsuits beyond your home and auto policy limits. This setting lets you model insurance coverage and gaps.",
    impact: "When enabled, the plan includes sheets for property, casualty, and umbrella coverage, and calculates whether your insurance limits are adequate or if a larger umbrella policy would help.",
    consider: "An umbrella policy is often inexpensive relative to your assets — if your net worth is significant, a $1-2 million umbrella can be cheap insurance against a catastrophic liability lawsuit.",
  },
  retirement_strategy: {
    purpose: "Retirement strategy covers how you'll withdraw from different types of accounts (taxable, pre-tax retirement accounts, Roth) and in what order. This setting provides detailed sequencing analysis.",
    impact: "When enabled, the plan shows a detailed withdrawal strategy and sequencing, which can significantly reduce taxes by taking from the right account types at the right time.",
    consider: "Generally, hold off on pre-tax retirement account withdrawals until required by law, live on taxable savings or Roth first, and manage conversions to fill low-tax years.",
  },
  rmd_audit: {
    purpose: "RMD stands for Required Minimum Distribution — once you're age 73, the IRS requires you to take a minimum amount from your retirement accounts each year, or pay a penalty. This setting checks that you're taking the right amount.",
    impact: "When enabled, the plan audits whether your projected withdrawals meet the RMD requirement each year, alerting you if you might face a penalty.",
    consider: "If you're over 73 or approaching it, set up RMD calculations early to avoid penalties and plan your withdrawal strategy around the requirement.",
  },
  roth_conversion_plan: {
    purpose: "A Roth conversion moves money from a traditional pre-tax retirement account into a Roth IRA, paying income tax on the amount converted. The plan can model years where converting makes sense (usually low-income years) to reduce future taxes.",
    impact: "When enabled, the plan identifies which years conversions would be tax-efficient and calculates the long-term tax savings from converting in favorable years.",
    consider: "Conversions tend to help most in early retirement, years with market downturns, or when temporarily in a low tax bracket between retirement and Social Security.",
  },
  social_security_timing: {
    purpose: "You can claim Social Security anywhere from age 62 to 70; claiming earlier gives smaller monthly checks, claiming later gives larger ones. This setting optimizes when each household member should claim.",
    impact: "When enabled, the plan models different claiming ages to find the strategy that maximizes your lifetime benefit, considering longevity, spousal benefits, and taxes.",
    consider: "For most people, waiting to claim until 67 or later is best; if you have reason to expect shorter life expectancy, claiming at 62 might make sense.",
  },
  special_needs_planning: {
    purpose: "Special-needs planning addresses how to provide for a family member with disabilities without disqualifying them from government benefits like SSI or Medicaid. This setting models Special Needs Trusts and ABLE accounts.",
    impact: "When enabled, the plan includes analysis of Special Needs Trusts and ABLE savings accounts, ensuring you can leave money to a disabled family member without jeopardizing their benefits.",
    consider: "If you have a disabled family member, a Special Needs Trust is essential to avoid Medicaid disqualification; ABLE accounts offer another tool for smaller amounts.",
  },
  state_residency: {
    purpose: "State income tax varies widely — some states have no income tax, others can take 10%+ of retirement income. This setting analyzes how your state income tax changes if you relocate.",
    impact: "When enabled, the plan shows how much taxes would change if you moved to a different state, helping you evaluate the financial impact of relocating in retirement.",
    consider: "States with no income tax can offer significant savings, but factor in cost of living, property tax, and other taxes before relocating just for tax reasons.",
  },
  survivor_stress_test: {
    purpose: "A survivor stress test models what happens to the surviving family's finances if one member passes away early in retirement. This setting runs that scenario.",
    impact: "When enabled, the plan shows a scenario where one member dies early, calculating whether surviving dependents have enough assets and income to maintain their lifestyle.",
    consider: "If results show a shortfall, that's a signal that larger life insurance, a larger emergency fund, or a more conservative spending plan may be needed.",
  },
  what_if_analysis: {
    purpose: "A what-if analysis lets you change assumptions (like delaying retirement 2 years, spending 20% less, or working part-time) and instantly see how each change affects your plan. This setting turns on scenario tools.",
    impact: "When enabled, the plan includes interactive sheets where you can model \"what if I retire at 67 instead of 65?\" or \"what if I spend less per year?\" to see the financial impact.",
    consider: "Use this to test your confidence in the plan — if small changes in assumptions cause large changes in outcomes, you might need more margin for error.",
  },
  depreciation_per_year: {
    purpose: "How much value the vehicle loses each year. This is the annual dollar amount the auto is expected to decline.",
    impact: "Higher depreciation reduces the asset's value faster, lowering net worth projections and shrinking the amount you'd recover if you sold it.",
    consider: "Think about what your vehicle typically loses in value per year, or look at used-car market values for the same make and model at different ages.",
  },
  depreciation_years: {
    purpose: "How many years it takes the vehicle to fully depreciate to scrap or residual value. After this period, the car is worth very little.",
    impact: "Affects how long the vehicle is modeled as a valuable asset; once this period ends, the plan treats the car as having minimal worth.",
    consider: "Most vehicles depreciate significantly over 10–15 years; set this based on when you expect the vehicle to become worthless or ready to discard.",
  },
  appreciation_rate: {
    purpose: "The expected annual percentage increase in home value. This is how much you expect the home's worth to grow each year.",
    impact: "Higher appreciation grows home equity faster, increasing net worth and boosting the amount available from a future home sale.",
    consider: "Base this on historical appreciation in your area and current real estate market conditions; be realistic rather than optimistic.",
  },
  home_basis: {
    purpose: "The original purchase price of the home, used for calculating taxes when you eventually sell. This is your tax starting point.",
    impact: "The lower the basis, the higher the capital gain when you sell (sale price minus basis), and thus the higher the tax owed on that gain.",
    consider: "Basis is typically the price you paid when you bought the home; certain home improvements can legally add to your basis.",
  },
  home_sale_price: {
    purpose: "The amount you expect to receive when you sell the home. This is your assumed sale proceeds before costs.",
    impact: "Capital gains tax is calculated from the difference between sale price and basis; higher sale price means higher potential tax and more net proceeds for other goals.",
    consider: "Use current estimated market value or a conservative projection; the plan can show you how different prices affect your overall picture.",
  },
  section_121_exclusion_mfj: {
    purpose: "The amount of profit from a primary home sale that is completely tax-free for married couples filing jointly. The IRS lets you exclude this gain entirely.",
    impact: "Reduces or eliminates capital gains tax on the home sale, letting you keep more money after selling.",
    consider: "You generally qualify if you owned and lived in the home at least two of the past five years; consult a tax pro for your specific situation.",
  },
  value_as_of_plan_start: {
    purpose: "Your home's estimated market value at the start of your retirement plan. This is the foundation for all future projections.",
    impact: "A higher starting value grows larger over time via appreciation; it also determines your net worth at the plan's beginning.",
    consider: "Use a recent appraisal, a Zillow/Redfin estimate, or a conservative local real-estate assessment—don't guess or use purchase price if the home has appreciated.",
  },
  annual_appreciation_pct: {
    purpose: "The expected annual percentage change in this asset's value, whether positive (appreciation) or negative (depreciation). This drives long-term growth or decline.",
    impact: "Higher appreciation makes the asset worth much more over time, affecting when and how much proceeds are available; negative rates shrink the asset's future worth.",
    consider: "Ground this in historical performance or realistic expectations for that type of asset; be cautious of over-optimistic projections.",
  },
  as_of_date: {
    purpose: "The date when you last checked or valued this asset. It tells you how current your estimate is.",
    impact: "An old valuation date may be outdated and could skew the plan's projections if markets or circumstances have changed significantly.",
    consider: "Update this date whenever you get a new market quote or professional assessment, so your plan stays accurate.",
  },
  sell_date: {
    purpose: "The optional date you plan to sell this asset. Leave it blank if you plan to hold it indefinitely.",
    impact: "If you enter a date, the plan assumes you sell on that date and the proceeds become available for spending; if blank, the asset is modeled as held forever.",
    consider: "Use this only if you have a specific sale planned—for example, if you're expecting a startup acquisition or a certain timeframe to liquidate.",
  },
  basis: {
    purpose: "The original cost of this asset for tax purposes. It's your tax starting point for calculating gains or losses when you eventually sell.",
    impact: "The lower your basis, the higher the capital gain (sale price minus basis) and thus the higher the tax owed.",
    consider: "Basis is usually the price you paid to acquire the asset; some assets allow cost-basis adjustments over time, so check with your tax adviser.",
  },
  sale_price: {
    purpose: "The amount you expect to receive when this asset is sold. This is your projected gross proceeds before taxes or fees.",
    impact: "Higher sale price increases the capital gain (and potential tax) and boosts the cash available for spending or reinvestment.",
    consider: "Use realistic market expectations or a professional valuation; avoid wishful thinking about future prices.",
  },
  sale_year: {
    purpose: "The year you plan to sell this asset. This determines when the capital gain is realized and when proceeds become available.",
    impact: "The timing of the sale affects when taxes are owed and when money is available for spending; it also influences your overall retirement cash flow.",
    consider: "For startup equity or business interests, this often depends on acquisition timelines or liquidity events outside your control—plan conservatively.",
  },
  additional_medicare_rate: {
    purpose: "The extra Medicare tax rate that applies to high earners. This is an additional tax on top of regular Medicare tax for income above a threshold.",
    impact: "Income above the threshold is taxed at this rate, increasing overall payroll tax burden.",
    consider: "This additional tax applies to wages, self-employment income, and certain investment income; the threshold varies by filing status.",
  },
  additional_medicare_threshold_mfj: {
    purpose: "The income level above which additional Medicare tax kicks in for married couples filing jointly. Income above this point triggers the extra tax.",
    impact: "Income exceeding this threshold is subject to the additional Medicare tax rate, raising your total tax bill.",
    consider: "Different filing statuses have different thresholds; this one applies specifically to married couples filing jointly.",
  },
  medicare_employee_rate: {
    purpose: "The standard Medicare tax rate that is automatically withheld from your paychecks. This is a fixed percentage of wages.",
    impact: "Reduces each paycheck and funds the Medicare program; the amount withheld counts toward your own eventual Medicare coverage.",
    consider: "This rate is the same for all employees; your employer usually pays an equal matching amount on your behalf.",
  },
  medicare_self_employment_rate: {
    purpose: "The Medicare tax rate self-employed individuals pay on their net business income. Self-employed people pay both the employee and employer portions.",
    impact: "Results in a higher total Medicare tax burden compared to regular wage earners, because you pay both sides of the tax.",
    consider: "You can deduct half of your self-employment tax, which offsets some of the extra burden.",
  },
  se_half_deductible: {
    purpose: "The deductible portion of self-employment tax that reduces your overall taxable income. Self-employed people get to deduct half their self-employment tax.",
    impact: "Lowers your income-tax bill by reducing taxable income, which partially offsets the burden of paying both employee and employer portions.",
    consider: "This deduction is automatic for self-employed filers; it's built into the calculation of your adjusted gross income.",
  },
  se_net_earnings_factor: {
    purpose: "The adjustment factor applied to self-employment income to calculate exactly how much is subject to Social Security and Medicare tax. This factor accounts for the tax already built in.",
    impact: "Ensures the correct portion of self-employment income is taxed—neither too much nor too little.",
    consider: "This is a technical factor used internally; understanding it matters mainly if you're reconciling self-employment tax calculations with a tax professional.",
  },
  ss_employee_rate: {
    purpose: "The Social Security tax rate automatically withheld from your wages. This percentage comes out of each paycheck.",
    impact: "Reduces each paycheck and funds the Social Security program; this tax history builds your future Social Security benefit.",
    consider: "This rate applies only to wages below an annual cap; wages above that ceiling are not subject to Social Security tax.",
  },
  ss_self_employment_rate: {
    purpose: "Self-employment tax is a set tax rate that self-employed people pay to fund Social Security and Medicare - it's like the payroll tax that salaried employees pay. This setting controls what rate the plan uses for that calculation.",
    impact: "Changing this rate adjusts how much tax is owed on self-employment income in any year where you have that income. A higher rate means more taxes paid; a lower rate means less.",
    consider: "Unless you've negotiated a special rate with the IRS or have reason to use a different rate, use the standard current rate - the plan can look up the official rate automatically.",
  },
  ss_wage_base_base_year: {
    purpose: "Social Security tax doesn't apply to all your wages - there's an annual maximum income level above which earnings aren't taxed for Social Security (though Medicare still applies to all income). This setting tells the plan what that wage-base threshold is.",
    impact: "If income exceeds the wage base, those extra earnings skip Social Security tax but still owe Medicare tax. Increasing the wage base cap means more of a high earner's income is subject to Social Security tax.",
    consider: "The wage base changes most years - the plan can look this up automatically from the Social Security Administration's current schedule, so you usually don't need to set it manually.",
  },
  real_dollar_reporting_enabled: {
    purpose: "Inflation makes a dollar worth less over time - a hundred dollars next year won't buy what a hundred dollars buys today. This setting controls whether the plan shows amounts in 'today's dollars' (adjusted for inflation) or 'future dollars' (the actual dollar amounts you'll spend in future years).",
    impact: "When enabled, all projection amounts are shown in today's purchasing power, making it easier to compare spending across years. When disabled, amounts show what you'll actually receive or spend in future dollars - which looks bigger, but that's just inflation.",
    consider: "Most people find today's dollars easier to understand - it's the same as saying 'how much is that worth in today's money?' If you're comparing plan outputs or explaining to an advisor, today's dollars usually make the conversation clearer.",
  },
  allocation_selection_mode: {
    purpose: "Asset allocation means how you split your investments between stocks, bonds, and other asset types - it's one of the biggest drivers of how much risk and return your portfolio experiences. This setting chooses WHO decides that split: you, or one of four different automatic methods.",
    impact: "There are five choices. (1) Use the allocation you specified - the plan uses your percentages exactly as entered. (2) Use the optimizer's recommendation - the plan picks an allocation based on your goals and constraints. (3) Best risk-adjusted mix, staying within your risk limits - finds the mix with the most return per unit of risk, but will not exceed the risk ceilings you set. (4) Best risk-adjusted mix, ignoring your risk limits - the same calculation with the limits removed, so it can come out noticeably more aggressive OR more conservative than you intended. (5) Match each dollar to when you'll spend it - money you need soon is held in safer assets and money you won't touch for decades in growth assets, aiming to reduce the chance of a loss after inflation.",
    consider: "Pick option 1 if you have an allocation you want to keep (like 60% stocks, 40% bonds). Options 3 and 4 look almost identical but differ in one important way: option 3 respects the risk limits you set and option 4 does not, so only use option 4 if you genuinely want to see the unconstrained answer. Option 5 is the most tailored to your actual spending timeline and is a good default if you're unsure. Whichever you pick, the page below shows only the controls that apply to it.",
  },
  description: {
    purpose: "This is a text field for you to name or describe the scenario - for example, 'Our current plan' or 'If we retire at 62'.",
    impact: "Changing this is purely for your own reference - it doesn't change any numbers or outcomes, just how the scenario is labeled in reports.",
    consider: "Use a short, clear label that describes what makes this scenario different from others, so you can find it easily later when reviewing multiple what-ifs.",
  },
  include_high_inflation: {
    purpose: "Inflation erodes buying power - a stress test with high inflation shows what your plan looks like if prices rise faster than you expect. This toggle adds that scenario to a combined test that runs several challenging conditions together.",
    impact: "When enabled, the plan runs a scenario where inflation is higher than the base assumption, showing lower purchasing power and higher spending needs. This can reveal whether your savings would still be sufficient in a high-inflation environment.",
    consider: "Turn this on if you're concerned about inflation risk or want to see how much higher your savings goal would need to be to handle sustained high inflation.",
  },
  include_low_return: {
    purpose: "Investment returns vary widely depending on market conditions - a stress test with low returns shows what happens if your portfolio grows slower than expected. This toggle adds that scenario to a combined test.",
    impact: "When enabled, the plan runs a scenario where investment growth is below your base assumption, revealing how much savings you'd need if markets underperform.",
    consider: "Turn this on if you're unsure about your expected-return assumptions or want to know your plan's safety margin if markets disappoint.",
  },
  include_pdia_5050: {
    purpose: "This tests a scenario where your portfolio allocation is split 50/50 between two categories. This toggle adds that allocation scenario to a combined test.",
    impact: "When enabled, the plan runs an outcome showing how your plan would work with a 50/50 split, allowing you to see whether a more balanced mix of investments changes your retirement feasibility.",
    consider: "Use this if you're considering shifting to a more balanced portfolio and want to see the impact before committing to the change.",
  },
  include_pdia_low_div: {
    purpose: "This tests a scenario with a specific dividend income assumption from your investments. This toggle adds that scenario to a combined test.",
    impact: "When enabled, the plan runs an outcome using this dividend assumption, showing how your retirement picture changes with that income scenario.",
    consider: "Use this if you're modeling different income strategies from your investments and want to see their impact on your overall plan.",
  },
  include_retire_later: {
    purpose: "Working longer before retiring gives you more time to save and lets your investments compound further. This toggle adds a scenario where you retire later than your base plan assumes.",
    impact: "When enabled, the plan shows an outcome where you continue working for additional years, revealing whether delaying retirement improves your plan's success or reduces required savings.",
    consider: "Turn this on if you're flexible about retirement age and want to see how working an extra year or two would strengthen your financial position.",
  },
  include_sell_home: {
    purpose: "For many people, home equity is their largest asset - selling the home late in retirement can provide a large injection of cash. This toggle adds a scenario where you sell your home.",
    impact: "When enabled, the plan shows an outcome where the home is sold (and assumes you transition to renting or move in with family), showing the impact of that sale proceeds on your retirement security.",
    consider: "Turn this on if you're willing to downsize or relocate late in retirement and want to see how that could strengthen your plan.",
  },
  include_spend_more: {
    purpose: "Retirement dreams sometimes cost more than expected - travel, hobbies, or helping family can push spending higher. This toggle adds a scenario where you spend more than the base plan assumes.",
    impact: "When enabled, the plan shows an outcome with higher spending, revealing whether your savings can cover a more generous lifestyle or where you'd need to cut back.",
    consider: "Turn this on if you want to test a more aspirational lifestyle against your savings, or if past spending suggests your current budget estimate is too conservative.",
  },
  divorce_year: {
    purpose: "This field is part of a demonstration scenario showing how divorce would affect the retirement plan - it's disabled by default since most households don't need it. If enabled, it sets the year the divorce would occur.",
    impact: "When enabled and activated, the plan shows a separate outcome showing how the plan would change if a divorce happened in the specified year, accounting for asset splits and alimony.",
    consider: "Only enable this if you're actively planning for a possible divorce scenario - it's an advanced what-if that doesn't apply to most households.",
  },
  end_year: {
    purpose: "This is the final year that alimony (or another ongoing obligation) continues - after this year, payments stop. In different parts of the plan, this field represents when other time-bound commitments end.",
    impact: "Setting an end year tells the plan when to stop including this cost in your retirement expenses. Extending the end year means more years of payments; moving it closer means the obligation ends sooner.",
    consider: "Set this to the year the alimony agreement is scheduled to end, or to the year you expect the obligation to naturally stop (for example, when the youngest child finishes college if that's part of your alimony terms).",
  },
  monthly_amount: {
    purpose: "This is the regular monthly dollar amount paid out for alimony. Each month, this amount goes to the ex-spouse.",
    impact: "A higher monthly amount means more cash flowing out each month, which reduces available retirement income. A lower amount means more money stays in the retirement plan.",
    consider: "Use the amount from your divorce agreement or custody arrangement - if it's subject to change (inflation adjustments, for example), model multiple what-if scenarios.",
  },
  payor: {
    purpose: "This identifies who pays the alimony - either you or your spouse.",
    impact: "The payor's cash flow is reduced by the monthly payment amount; the recipient's cash flow is increased by the same amount. This allocation matters for tax and retirement income planning.",
    consider: "The person paying alimony typically needs to plan for this outflow as part of their retirement income needs.",
  },
  start_year: {
    purpose: "This is the first year that alimony (or another ongoing obligation) begins - before this year, payments don't occur. In different parts of the plan, this field represents when other time-bound commitments start.",
    impact: "Setting a start year tells the plan when to begin including this cost. Moving the start year later delays the expense; moving it earlier means the obligation starts sooner.",
    consider: "Set this to the year the alimony agreement takes effect according to your divorce settlement or court order.",
  },
  taxable_pre_2019_rules: {
    purpose: "Tax rules for alimony changed in 2019 - before 2019, the payor could deduct alimony payments and the recipient paid tax on them; starting in 2019, neither deduction nor inclusion applies. This toggle chooses which tax treatment to use for your plan.",
    impact: "Using pre-2019 rules means the payor gets a tax deduction (lowering their taxable income) and the recipient must include the payment as taxable income. Using post-2019 rules means both treat alimony as after-tax with no deduction or income inclusion.",
    consider: "If the alimony was set before 2019, use the pre-2019 rules. If it was set in 2019 or later, use the post-2019 rules. If you're unsure which applies, check your divorce decree or ask your tax advisor.",
  },
  cobra_end_year: {
    purpose: "COBRA is a federal law that lets you keep your employer health insurance for a limited time after leaving a job (usually up to 18 months), though you pay the full premium yourself. This sets the year COBRA coverage ends.",
    impact: "COBRA coverage usually costs more than employer-sponsored insurance but less than buying individual insurance - setting when it ends tells the plan when to switch to a different health insurance cost or arrangement.",
    consider: "COBRA typically lasts 18 months after you leave a job, but can end earlier if you're no longer eligible. Set this to when you expect to move to another insurance arrangement (Medicare, spouse's plan, individual market, etc.).",
  },
  cobra_monthly: {
    purpose: "This is the monthly cost you'd pay for COBRA health insurance coverage. COBRA premiums are typically higher than what you paid as an employee, since you're covering both your employer's and employee's share.",
    impact: "A higher COBRA cost means larger health insurance expenses during the years you're on COBRA, reducing available income for other retirement spending. The plan accounts for this expense between when employer coverage ends and when you transition to another plan.",
    consider: "Get a quote from your employer's benefits department or health plan for what COBRA would actually cost in your situation - don't guess. Factor in that the premium will likely increase a bit each year with healthcare inflation.",
  },
  from_account: {
    purpose: "Which account to pull money from in the divorce property split. This identifies the source account whose balance will be reduced by the transfer.",
    impact: "Choosing a different source account changes which investments are sold and which balance decreases. The account chosen affects the tax consequences and the remaining portfolio mix after the split.",
    consider: "Pick an account that makes sense to reduce first—often a taxable account to minimize tax consequences, or an account in one spouse's name anyway.",
  },
  account_name: {
    purpose: "The name of the account receiving the QDRO transfer. A QDRO (Qualified Domestic Relations Order) lets divorce settlements split retirement accounts without early-withdrawal penalties.",
    impact: "The receiving account name identifies where the transferred funds land, affecting which spouse controls those assets and how they're taxed going forward.",
    consider: "Make sure this receiving account is already opened before the transfer year, or coordinate with your divorce attorney and the plan administrator on timing.",
  },
  transfer_amount: {
    purpose: "The dollar amount to transfer via QDRO to the receiving account. This is an alternative to entering a percentage.",
    impact: "A higher dollar amount moves more wealth to the other spouse, reducing the transferring spouse's account balance by that exact sum at the transfer year.",
    consider: "Dollar amounts can become outdated if accounts grow or shrink; percentages often adjust automatically with account growth, making them easier to maintain.",
  },
  transfer_pct: {
    purpose: "What percentage of the account transfers via QDRO—for example, 50% splits the account roughly in half. This is an alternative to entering a fixed dollar amount.",
    impact: "A higher percentage moves more of the account to the other spouse. Using a percentage automatically scales with the account balance, adapting as the account grows or shrinks.",
    consider: "Percentages are usually easier than fixed dollars because they keep the split proportional as account values change over time.",
  },
  transfer_year: {
    purpose: "The year the QDRO transfer occurs. This determines when the account split happens and when tax consequences are recognized.",
    impact: "Earlier transfers happen during active earning years; later transfers happen closer to retirement. The year affects which spouse controls the assets longer and when each can access the funds.",
    consider: "QDROs typically process in the year the divorce is final. Coordinate with your divorce settlement date and your plan administrator's processing timeline.",
  },
  filing_status_after_divorce: {
    purpose: "Your tax filing status after the divorce is final. This affects your tax brackets, standard deduction, and eligibility for various tax benefits.",
    impact: "Filing status changes your annual tax bill and can shift you into different brackets. Single filers and heads of household face different tax rates than married filing jointly.",
    consider: "Filing status is locked on December 31 of each year—if your divorce finalizes mid-year, you may still file as married for that year. Plan accordingly with your tax advisor.",
  },
  home_downsize_net_proceeds: {
    purpose: "The net cash you'll receive after selling the current home and buying a smaller one. This is the liquid proceeds added to the portfolio in the downsize year.",
    impact: "More proceeds increase portfolio assets available for spending and growth. Larger downsizes mean bigger cash boosts, but less housing equity later if the home is expected to appreciate.",
    consider: "Calculate this carefully: sale price minus realtor fees and closing costs, minus the purchase price of the smaller home. Don't double-count if you're also reducing a mortgage.",
  },
  home_downsize_year: {
    purpose: "The year you sell the current home and move to a smaller one. Leave blank if you're not downsizing; otherwise enter the year you plan to sell.",
    impact: "Earlier downsize unlocks cash sooner for portfolio growth and spending. Later downsize extends housing costs but delays the freed-up capital and may reduce the benefit if you need the proceeds urgently.",
    consider: "Downsizing works best when you've decided to genuinely move—it's not a great lever if you love your home. Test the scenario both with and without downsizing to see the financial trade-off.",
  },
  inflation_override: {
    purpose: "Override the plan's inflation assumption with a higher rate—for example, 4.5% annually instead of the plan's default. This stress-tests how your plan handles sustained high inflation.",
    impact: "Higher inflation increases costs faster and erodes purchasing power. All expenses grow quicker, requiring higher investment returns or accepting a lower standard of living in later years.",
    consider: "If you lived through recent high-inflation years, use this to test scenarios where inflation stays elevated. See if your plan survives a decade at 4.5% or higher inflation.",
  },
  spend_multiplier: {
    purpose: "Multiply your annual spending by a set percentage—for example, 1.20 means 20% higher spending every year. This tests whether your plan survives higher costs.",
    impact: "Higher spending drains portfolio faster, shortening how long your assets last. A 20% increase compounds year over year and can dramatically affect plan longevity.",
    consider: "Use this to answer \"What if we spent $30,000 more per year?\"; multiply your base spending by that percentage to find the multiplier and test it here.",
  },
  portfolio_return_override: {
    purpose: "Override the plan's investment return assumptions with a lower rate. This tests how your plan performs if markets deliver less growth than expected.",
    impact: "Lower returns slow wealth accumulation and portfolio growth. Your assets may run out sooner, or require higher savings or later retirement to stay solvent.",
    consider: "Model a conservative scenario (like 4-5% annual returns) alongside your base plan to see the range of outcomes and whether you're comfortable with the downside risk.",
  },
  onset_age_catastrophic_both: {
    purpose: "The age when both spouses begin catastrophic long-term care needs in this stress-test scenario. Catastrophic care is intensive, around-the-clock care for both members.",
    impact: "Earlier onset means longer duration and higher total cost—catastrophic care is very expensive and can strain portfolios if both spouses need it for years. Later onset means lower total cost but higher annual costs when they do begin.",
    consider: "Set this based on family health history or your own comfort level. If dementia or severe illness runs in your family, test an earlier age; otherwise, a later onset may be more realistic.",
  },
  onset_age_facility_memory_care: {
    purpose: "The age when the older spouse enters a memory-care facility in this what-if scenario. Memory care is specialized care for people with dementia or cognitive decline.",
    impact: "Earlier facility entry means longer cost duration and higher total spending. Memory care facilities are expensive but may be necessary if at-home care becomes unsafe or impractical.",
    consider: "Adjust based on family dementia risk or your personal preferences about assisted living. If dementia is common in your family, test an earlier entry age to prepare.",
  },
  onset_age_moderate_home_care: {
    purpose: "The age when moderate in-home care begins for the older spouse in this what-if scenario. Moderate care is part-time help—maybe a few hours daily for cooking, cleaning, or personal care.",
    impact: "Earlier onset increases total cost duration. Moderate home care costs less than facilities but compounds over many years. Timing affects both annual expenses and total lifetime care spending.",
    consider: "Moderate home care is often affordable and lets people stay at home. Use this scenario if aging in place with part-time help is your preference; compare cost to facility alternatives.",
  },
  onset_age_severe_home_care: {
    purpose: "The age when severe in-home care begins for the older spouse in this what-if scenario. Severe care is full-time or near-full-time assistance—overnight aides, constant supervision, or medical support at home.",
    impact: "Severe home care is expensive—sometimes nearly as costly as facilities—but lets you stay home. Earlier onset means longer duration and higher total cost, compounded year over year.",
    consider: "Severe home care appeals to people who want to age at home despite high costs. Test this scenario if staying home is a priority; it's often affordable in early years but grows expensive quickly if needed long-term.",
  },
  annuity_div_override: {
    purpose: "Override all annuity dividend rates to a lower percentage—for example, 4.50% instead of the illustrated 5.50%-5.75%. This tests whether your plan works if annuity payouts decline.",
    impact: "Lower dividends reduce your guaranteed income stream from the annuity year after year. You'd need to reduce spending or increase portfolio withdrawals, putting more pressure on investments to cover the gap.",
    consider: "Annuity rates can change if interest rates drop or the insurance company's dividend policy shifts. Test a lower rate to see if your plan still works even if guaranteed income shrinks.",
  },
  annuity_split_override: {
    purpose: "Change how the annuity payout is divided between the two members—for example, 50-50 instead of the current 80-20. Leave blank to keep the existing split.",
    impact: "A more even split (like 50-50) boosts the surviving spouse's income after the primary member dies but may reduce the primary member's current income. The total payout stays the same; only the split changes.",
    consider: "If one spouse will face significant income gap after the other passes, test a more even split to see if survivor income looks adequate. A perfectly even split offers mutual protection but may feel limiting now.",
  },
  income_growth_rate_override: {
    purpose: "Set how fast your income grows per year during the extra work years. Zero means flat income; a higher rate matches base-plan growth or your expected raises.",
    impact: "Faster growth accelerates savings in those extended work years. Flat income (0%) simplifies planning but may underestimate savings if you expect raises or promotions during the phase-down.",
    consider: "If you're reducing hours, use 0% for flat pay. If you expect normal raises or are staying full-time for a few extra years, use a growth rate that matches your past experience.",
  },
  member_1_retire_year: {
    purpose: "Override when Member 1 retires. For example, retiring in 2029 instead of the base case 2027 means 2 extra years of work and income.",
    impact: "More working years means more time to save and higher Social Security benefits at a later claiming age. It also shortens the retirement period you need to fund, strengthening the overall plan.",
    consider: "Delaying retirement even a year or two often makes a big difference. Test a later retirement to see how much it improves your security, then decide if those extra work years are worth it.",
  },
  salary_override: {
    purpose: "Set the W-2 salary you'll earn during the extended work years. A lower salary reflects reduced hours or phased, part-time work toward eventual full retirement.",
    impact: "Lower salary during extension years reduces income, savings, and retirement contributions. However, it reflects lower work stress and cost of working, which some people value highly.",
    consider: "If you're phasing out, estimate your realistic part-time or reduced-hour pay honestly. Even part-time income helps close the retirement funding gap and may be worth the continued work.",
  },
  home_sale_proceeds_account: {
    purpose: "The account where money from selling the home will be deposited. The plan calculates net proceeds (sale price minus selling costs like realtor commissions and closing fees) and deposits them here.",
    impact: "Changes the account balance in the home-sale year and after. If you choose a tax-deferred account like an IRA, the timing may be restricted; a regular investment or savings account is simpler and immediately available.",
    consider: "Pick an account you plan to keep open and access in and after the sale year. Most households direct proceeds to their primary savings or investment account.",
  },
  home_sale_year: {
    purpose: "The year you plan to sell your home in this scenario. The plan models all spending and investment growth up to and after that year.",
    impact: "Raises or lowers when proceeds become available and how much time remains for growth or spending. Selling earlier brings cash faster but gives up future home appreciation; selling later lets the home grow longer but delays the proceeds.",
    consider: "Use your best realistic estimate. The plan can show you the impact of different timelines, so test a few scenarios if you're uncertain.",
  },
  target_state: {
    purpose: "The state you are considering moving to. The plan uses this to compare estimated costs like taxes and insurance between that state and your current state.",
    impact: "Changes all numbers in the State Comparison sheet. Different states have different income taxes, property taxes, insurance rates, and living costs.",
    consider: "Enter the two-letter state abbreviation (like FL, TX, NV) of the place you are seriously considering or want to explore. Leave blank if you do not plan to move.",
  },
  current_state_baseline_annual: {
    purpose: "Your current auto insurance annual premium in your current state — the amount you actually pay today.",
    impact: "Becomes the baseline for the State Comparison sheet. The plan compares this against estimated target-state premiums to show potential insurance savings from moving.",
    consider: "Check your most recent auto insurance bill for the actual annual premium you pay, including any discounts like multi-policy bundling.",
  },
  notes: {
    purpose: "A free-text place to write down important details about this item — such as coverage differences, why an estimate might be unusually high or low, or any other context worth remembering.",
    impact: "This is reference information only; it does not change the plan's numbers. It helps you remember your reasoning when reviewing the plan later.",
    consider: "Write briefly and clearly — for example, 'quote includes higher liability coverage' or 'discount applied for bundling policies.' These notes carry over into your reports.",
  },
  target_state_annual: {
    purpose: "Your estimated homeowners insurance annual premium in the target state — a projection or quote for what the policy would cost there.",
    impact: "Changes the estimated cost of living in the target state. The plan subtracts this from your current-state premium to show potential insurance savings if you move.",
    consider: "Call an insurance agent, get a quote online, or research typical premiums in that state. Use a cost estimate for the same house and coverage level you have today so the comparison is fair.",
  },
  applicable_pct_cap: {
    purpose: "The maximum percentage of household income the law says you must contribute toward health insurance premiums to be eligible for federal subsidies. This threshold is set by law and may change year to year.",
    impact: "When ACA subsidies are enabled, the plan uses this cap to calculate how much subsidy you receive. A lower cap means larger subsidies; a higher cap means smaller subsidies.",
    consider: "This is a federal threshold set by law; you typically do not need to change it. Check the current IRS or healthcare.gov guidance if subsidy rules change.",
  },
  benchmark_silver_premium_annual: {
    purpose: "The annual cost of the lowest-cost 'silver' health insurance plan available in your area before any subsidies. This benchmark is used to calculate how much subsidy you qualify for.",
    impact: "When ACA subsidies are enabled, the plan compares your actual premium against this benchmark to calculate your subsidy amount. A higher benchmark can mean a larger subsidy is available.",
    consider: "Find this on healthcare.gov or your state's ACA marketplace for your zip code and household size. This number changes each year and varies by location.",
  },
  enabled: {
    purpose: "Turn on or off the calculation of ACA health insurance subsidies — tax credits that reduce premiums if you retire before 65 and buy individual insurance.",
    impact: "When enabled, years with lower household income may qualify for free or reduced-cost premiums, cutting healthcare costs significantly in pre-Medicare years. When disabled, the plan assumes you pay full premiums.",
    consider: "Enable this if you retire before 65 and plan to buy individual health insurance off the ACA marketplace. It can save thousands per year. Skip it if you'll stay on an employer plan or be covered by Medicare.",
  },
  enhanced_subsidies_through_year: {
    purpose: "The last year that current, more generous ACA subsidy rules are in effect. After this year, subsidy calculations may change to less generous rules unless Congress extends them.",
    impact: "Subsidy amounts in years through this date use enhanced rules; later years may use different (possibly smaller) subsidies. The plan changes subsidy calculations at this cutoff.",
    consider: "This is set by federal law and may be extended or expire. Use the current law's expiration date. The plan will show you how subsidies drop or change after this year.",
  },
  federal_poverty_level_base_year: {
    purpose: "The dollar amount the federal government defines as the poverty line for your household size in a reference year. ACA subsidy eligibility is calculated as a percentage of this threshold.",
    impact: "The plan uses this to determine subsidy eligibility — household income between 100% and 400% of this level typically qualifies for help. A higher FPL makes subsidy qualification harder.",
    consider: "The federal government publishes this annually for each household size. You usually do not need to adjust it; the system uses official thresholds. Verify the current year's number on healthcare.gov if needed.",
  },
  household_size: {
    purpose: "The number of people counted on the same tax return for federal subsidy purposes. Usually this is the taxpayer, spouse, and any dependents.",
    impact: "A larger household size raises the income threshold for subsidy eligibility — larger families can earn more and still qualify for help. A smaller household size lowers the threshold.",
    consider: "Count everyone who will file on the same tax return during the years you expect to claim subsidies — yourself, spouse, dependents you claim.",
  },
  dental_annual: {
    purpose: "How much you typically spend out of pocket on dental care each year — cleanings, exams, fillings, crowns, and other dental expenses not covered by insurance.",
    impact: "Raises or lowers your annual healthcare spending projection. The plan adds this to medical, vision, and pharmacy costs to estimate total healthcare expense.",
    consider: "Review your dental receipts from the past couple of years. Include routine care plus any big work you expect. Adjust if your needs are changing.",
  },
  medical_annual: {
    purpose: "How much you typically spend out of pocket on medical care each year — deductibles, copays, lab work, and services your insurance doesn't cover.",
    impact: "Raises or lowers your annual healthcare spending projection. This combines with dental, vision, and pharmacy to calculate total out-of-pocket healthcare costs.",
    consider: "Check your past few years' explanation-of-benefits statements from your health insurance. Add up all out-of-pocket amounts, including deductibles and copays.",
  },
  oop_utilization_pct: {
    purpose: "If you do not have detailed medical expenses, this is the estimated share of your annual out-of-pocket spending cap that counts as non-premium medical spending.",
    impact: "Raises or lowers projected medical expenses when detailed expense rows are not entered. A higher percentage means the plan assumes more spending; lower means less.",
    consider: "This is a rough estimate tool — use detailed medical expenses if you have them. If estimating, try 50-75% (most people spend half to three-quarters of their max-out-of-pocket limit in a typical year).",
  },
  pharmacy_annual: {
    purpose: "How much you typically spend out of pocket on prescription drugs each year — copays or coinsurance for medications not fully covered by insurance.",
    impact: "Raises or lowers your annual healthcare spending projection. The plan adds this to medical, dental, and vision to estimate total healthcare expense.",
    consider: "Check your pharmacy receipts from the past year. If you take several regular medications, add them up. Adjust if prescriptions are changing.",
  },
  vision_annual: {
    purpose: "How much you typically spend out of pocket on vision care each year — eye exams, glasses, contact lenses, and other vision expenses not covered by insurance.",
    impact: "Raises or lowers your annual healthcare spending projection. The plan adds this to medical, dental, and pharmacy to calculate total healthcare costs.",
    consider: "Include routine eye exams and the cost of glasses or contacts if you need them yearly. Factor in any specialty options like progressive lenses.",
  },
  gain_harvest_min_gain_dollars: {
    purpose: "The smallest dollar amount of profit on an investment that is worth selling in a single year for tax savings. This avoids tiny sales that don't save much in taxes.",
    impact: "Raises the threshold, so fewer small gains are harvested. Lowers the threshold, so more gains are harvested. Too low wastes money on trading costs; too high misses tax-saving opportunities.",
    consider: "Set this higher if you have high trading costs or already-low taxes. Set it lower if you have large capital gains and want to harvest aggressively. A typical range is $500 to $1,000 per lot.",
  },
  gain_harvest_min_gain_pct: {
    purpose: "The smallest profit (as a percentage of what you originally paid) that is worth harvesting for tax savings. This is a second hurdle to avoid harvesting tiny gains.",
    impact: "Raises the threshold, so fewer small-percentage gains are harvested. Lowers it, so more gains are harvested. A 5% gain might be worth harvesting; 0.5% usually is not.",
    consider: "Set this between 3% and 10% depending on how aggressive you want to be. Higher percentages (like 10%) are conservative; lower (like 3%) harvest more aggressively.",
  },
  gain_harvest_policy: {
    purpose: "Whether to harvest long-term investment gains that fall into a zero-percent capital gains tax bracket during low-income years, and whether to just show the opportunity or actually execute it.",
    impact: "\"Off\" ignores the opportunity. \"Analyze only\" shows which gains could be harvested tax-free each year without changing the plan. \"Apply\" actually sells and repurchases securities to lock in the tax-free gain. Applying can save significant taxes but adds trading activity.",
    consider: "If you expect low-income years (especially early retirement before Social Security), enable this — it is one of the most tax-efficient strategies available. Start with \"Analyze only\" to see the opportunity, then \"Apply\" if the numbers look good.",
  },
  gain_harvest_transaction_cost_bps: {
    purpose: "This is the cost charged by your brokerage each time you harvest (sell) a stock to lock in a capital loss. It's measured in basis points — think of it as hundredths of a percent of the amount you're selling. Most modern brokerages charge zero to five basis points (that's zero to 0.05% of the sale).",
    impact: "If you set this cost higher, the plan will harvest fewer losses, because the trading fee eats into the tax savings. If you set it lower, the plan will harvest more often since the cost is minimal.",
    consider: "Check your actual brokerage's fee schedule — many brokerages now charge zero commission per trade. Call and ask for the exact cost per round-trip if you're unsure.",
  },
  annual_funding_tolerance: {
    purpose: "This is how close your annual inflows and outflows need to be to each other. The plan tries to make sure you're not silently spending more than you're receiving, or receiving more than you're spending, within a small margin each year.",
    impact: "If you raise this tolerance, the plan allows bigger gaps between your inflows and outflows each year. If you lower it, the plan forces those numbers to balance more tightly.",
    consider: "Keep this tight unless you have a specific reason to allow big annual imbalances — like years where you're deliberately saving extra or drawing down savings.",
  },
  estate_tax_objective_mode: {
    purpose: "This controls how aggressively the plan tries to reduce estate taxes (the federal and state taxes owed on money you leave behind) by converting regular retirement accounts to Roth. It only matters if the plan projects you'll owe estate taxes.",
    impact: "OFF ignores estate tax completely. MONITOR_ONLY shows the risk but doesn't change recommendations. BALANCED considers it alongside other retirement goals. STRONG prioritizes reducing estate taxes even if it means paying more in lifetime income tax.",
    consider: "Most households don't owe estate taxes — they only apply if your total assets exceed federal limits (currently about $13-14 million per person, though this changes with tax law). Ask a tax professional if you're close to that range; if not, OFF is fine.",
  },
  future_tax_rate_stress_pct: {
    purpose: "This is an extra buffer added to your expected future tax rates, used only when the plan decides whether to do a Roth conversion. It helps protect you if tax rates rise more than expected.",
    impact: "If you raise this percentage, the plan treats future taxes as scarier and will do more conversions now. If you lower it, the plan will do fewer conversions.",
    consider: "Increase this if you're worried tax rates will rise in the next 10-20 years. Decrease it if you think rates will stay flat or drop. But large percentages will drive many conversions — test the impact before committing.",
  },
  future_tax_risk_weight: {
    purpose: "This is how much the plan should care about protecting you from the risk that tax rates climb faster than currently expected. It affects how many Roth conversions the plan suggests.",
    impact: "Higher weight means more conversions, trading today's tax bill for safety against higher future rates. Lower weight means fewer conversions and more confidence that current tax rates will hold.",
    consider: "Set this higher if you're naturally risk-averse about future tax changes, or if you think tax rates are unusually low right now. Set lower if you believe rates will stay stable or decline.",
  },
  heir_ordinary_tax_rate_assumption_pct: {
    purpose: "When you leave behind money in a regular (pre-tax) retirement account, your heirs have to pay income tax on it when they withdraw it. This is the tax rate you expect them to pay on those withdrawals.",
    impact: "If you assume heirs will pay a higher tax rate, the plan will do more Roth conversions since that looks cheaper in the long run. If you assume a lower rate, the plan will leave more money in pre-tax accounts.",
    consider: "Your heirs' tax rate depends on their income and tax bracket when they withdraw the money, not their wealth. If they'll be in a low-income year (right after retirement or between jobs), use a lower rate; if they're high earners, use higher.",
  },
  inheritance_tax_burden_weight: {
    purpose: "This is how much the plan should prioritize reducing the income-tax burden that gets passed to your heirs along with your pre-tax retirement accounts. It affects conversion decisions.",
    impact: "Higher weight means the plan favors Roth conversions to leave heirs with tax-free money instead of money they'll pay tax on. Lower weight means the plan is less concerned with heirs' future tax burden.",
    consider: "If leaving a clean financial legacy matters a lot to you, raise this weight. If your focus is mainly on your own retirement comfort, lower it.",
  },
  irmaa_guardrail_mode: {
    purpose: "IRMAA stands for Income-Related Monthly Adjustment Amount — it's the extra Medicare premium you pay if your income is high. This setting controls whether the plan avoids pushing your income into higher IRMAA brackets when converting to Roth.",
    impact: "IGNORE means the plan ignores IRMAA when deciding on conversions. WARN_ONLY flags the risk but still suggests conversions. AVOID_NEXT_TIER stops conversions if they'd push you into a higher bracket. AVOID_TIER_2_OR_ABOVE is stricter.",
    consider: "If you're on Medicare or will be soon, use at least AVOID_NEXT_TIER — IRMAA cliffs are steep hidden fees. If you're not on Medicare yet and won't be for years, IGNORE or WARN_ONLY is fine.",
  },
  legacy_objective_mode: {
    purpose: "This controls how much weight the plan gives to leaving behind a larger, tax-efficient estate for heirs. OFF ignores legacy entirely; BALANCED mixes it with your retirement comfort; STRONG prioritizes leaving wealth to heirs.",
    impact: "OFF focuses purely on your retirement lifestyle. LOW and BALANCED start factoring in heir concerns and tax-efficient handoff strategies. STRONG will suggest Roth conversions and other moves to maximize what you leave behind.",
    consider: "If you have significant wealth and want to pass it on tax-efficiently, use BALANCED or STRONG. If your priority is your own retirement, use OFF or LOW.",
  },
  max_annual_conversion_pct_of_traditional_ira: {
    purpose: "This is the most you're willing to convert from regular (pre-tax) retirement accounts to Roth in any single year, expressed as a percentage of how much was in those accounts at the start of the year.",
    impact: "If you set this high (say, 50%), the plan can do large conversions in a single year. If you set it low (say, 5%), conversions will be spread across many years and smaller.",
    consider: "Large single-year conversions trigger large tax bills upfront. If you have cash outside your retirement accounts to pay the tax and want to move a big balance to Roth quickly, use higher. If you want to spread tax pain over years, use lower.",
  },
  max_conversion_years: {
    purpose: "This is how many years the plan is allowed to do voluntary Roth conversions before you hit the age when you're required to start taking withdrawals from regular retirement accounts.",
    impact: "If you set this higher, the plan has more years to work with for conversions. If you set it lower, conversions have to happen faster or not at all.",
    consider: "If you want conversions spread over a long period to smooth out tax spikes, use a higher number. If you want to get them done quickly (maybe because you expect tax rates to rise soon), use a lower number.",
  },
  pre_tax_bequest_penalty_pct: {
    purpose: "This is a percentage reduction applied to the value of pre-tax retirement money you leave behind, to account for the income taxes your heirs will owe on it. It's a way to score that money lower when deciding how much wealth you're actually leaving.",
    impact: "Higher penalty means the plan sees pre-tax accounts as 'worth less' to your heirs and will favor Roth conversions to leave tax-free money instead. Lower penalty means pre-tax accounts look equally valuable.",
    consider: "If your heirs are high earners who'll pay 40% tax on distributions, you might use a 40% penalty. If they're in a lower bracket, use a lower penalty that reflects what distributions will actually cost them.",
  },
  roth_bequest_preference_bonus_pct: {
    purpose: "This is a percentage bonus applied to Roth money you leave behind, to reflect the fact that your heirs can withdraw it tax-free. It makes Roth look more valuable when the plan decides what to do.",
    impact: "Higher bonus means the plan will favor Roth conversions and hold Roth balances instead of spending them. Lower bonus means Roth and pre-tax accounts are scored more equally.",
    consider: "If you care a lot about leaving a clean, tax-free inheritance, use a higher bonus. If you're indifferent about leaving money behind, use a lower bonus.",
  },
  roth_bracket_strategy: {
    purpose: "This is the overall approach the plan uses to decide how much to convert to Roth each year. Different strategies prioritize different goals — some fill your current tax bracket, some protect against future rate changes, some focus on what heirs will pay.",
    impact: "Different strategies will suggest different conversion amounts and patterns. Some will be aggressive (large yearly conversions); others conservative (small or no conversions). The one you choose sets the baseline for recommendations.",
    consider: "Start with OPTIMIZER_CHOOSES if you want the plan to decide based on overall goals. Pick a specific strategy like FILL_CURRENT_BRACKET if you have a clear preference.",
  },
  roth_conversion_policy: {
    purpose: "This is the main decision rule for Roth conversions: does the plan optimize to minimize lifetime taxes, fill your tax bracket to the top, stay under IRMAA limits, convert a fixed dollar amount each year, or skip conversions?",
    impact: "Optimize will convert different amounts year to year based on tax-efficiency. Fill-to-bracket will convert until your income fills a bracket each year. Fixed-dollar will convert the same amount every year. None will skip conversions.",
    consider: "For most people, optimize or fill-to-bracket is reasonable. Fixed-dollar is simpler if you want predictability. None makes sense only if you've decided Roth conversions aren't right for you.",
  },
  roth_conversion_target_bracket_base_year: {
    purpose: "If you're using a 'fill to bracket' strategy, this is which tax bracket you want to fill up — are you targeting the 22% bracket, the 24% bracket, etc.?",
    impact: "Picking a higher bracket means larger conversions each year. Picking a lower bracket means smaller, more conservative conversions.",
    consider: "A common choice is to fill to the top of your current bracket, assuming that's cheaper than your expected post-retirement marginal rate. Ask your tax advisor which bracket makes sense for you.",
  },
  roth_fixed_annual_amount: {
    purpose: "If you're using a fixed-dollar conversion strategy, this is how much you convert each year (in dollars).",
    impact: "Higher amounts mean larger tax bills each year from conversions. Lower amounts mean smaller annual conversions and less tax impact, but slower Roth buildup.",
    consider: "Pick an amount your cash flow can handle tax-wise. If you expect $5,000 in cash flow that year and want to pay the tax out-of-pocket, don't convert more than that amount (accounting for the tax bill itself).",
  },
  roth_headroom_usage_pct: {
    purpose: "This is how much of your unused tax bracket space the plan should use for conversions. If you're in the 24% bracket and have room to add $50,000 of income before jumping to 32%, this setting says how much of that room to fill.",
    impact: "Higher percentage means the plan will use more of your available bracket (more aggressive conversions). Lower percentage means the plan will be more conservative and leave more room unused.",
    consider: "Use a lower percentage if you want a safety cushion to stay under important thresholds like IRMAA limits. Use a higher percentage if you want to 'fill up' your bracket efficiently.",
  },
  roth_objective_mode: {
    purpose: "This is the main goal the plan is optimizing for when it decides on Roth conversions. Each mode weighs different concerns — your retirement comfort, lifetime tax efficiency, total wealth at the end, what heirs inherit, or estate tax avoidance.",
    impact: "BALANCED_RETIREMENT focuses on lifestyle and modest tax optimization. MINIMIZE_LIFETIME_TAX pushes conversions to lower total taxes. MAXIMIZE_TERMINAL_NET_WORTH prioritizes ending wealth. LEGACY_OPTIMIZED and ESTATE_TAX_AWARE favor leaving more to heirs.",
    consider: "Pick BALANCED_RETIREMENT unless you have a specific priority. It balances all concerns reasonably.",
  },
  roth_optimize_lifetime_tax_weight: {
    purpose: "This is how much the plan cares about minimizing your total lifetime income taxes (all taxes paid over your entire retirement) when deciding on Roth conversions.",
    impact: "Higher weight means the plan will suggest more conversions to reduce lifetime tax. Lower weight means the plan considers lifetime taxes less important and may suggest fewer conversions.",
    consider: "Set this higher if you strongly believe tax rates will rise and want to move money to Roth before that happens. Set lower if you're more concerned about your annual cash flow than lifetime totals.",
  },
  roth_optimize_terminal_pretax_tax_rate: {
    purpose: "This assumes what income tax rate you'll pay on pretax retirement accounts eventually. The plan uses it to decide whether Roth conversions today—paying tax now to avoid tax later—are worthwhile.",
    impact: "A higher assumed rate pushes toward more Roth conversions to escape future taxes. A lower assumed rate suggests fewer conversions.",
    consider: "Use a realistic estimate of your late-retirement tax rate based on expected withdrawals and Social Security income.",
  },
  roth_optimize_terminal_weight: {
    purpose: "How much the plan should prioritize maximizing after-tax wealth at the end of your life, versus spending comfortably during retirement.",
    impact: "Higher weight drives more aggressive Roth conversions to preserve after-tax wealth for heirs. Lower weight allows more spending flexibility during life.",
    consider: "Set high if leaving money behind is a top priority; set low if comfortable retirement spending matters most.",
  },
  roth_target_bracket_rate: {
    purpose: "The federal tax bracket the plan will try to fill with Roth conversions each year without pushing you into a higher bracket. Choices: 10%, 12%, 22%, 24%, 32%, 35%, or 37%.",
    impact: "A higher bracket allows larger conversions (and bigger immediate taxes) while staying within it. A lower bracket keeps conversions smaller and safer.",
    consider: "Estimate where normal withdrawals and Social Security would land, then choose the bracket just below—this fills that bracket without jumping higher and wasting money.",
  },
  roth_tax_discount_rate: {
    purpose: "The discount rate used to compare paying taxes now versus later, accounting for investment growth and inflation. It helps the plan decide if today's Roth conversion is worth the immediate tax cost.",
    impact: "Higher rate means paying taxes later becomes more attractive, driving more conversions. Lower rate suggests waiting to pay taxes is better, driving fewer conversions.",
    consider: "Set this to your expected long-term investment return—usually 5-8%—so the comparison reflects realistic growth assumptions.",
  },
  survivor_tax_risk_weight: {
    purpose: "When one spouse dies, the survivor's tax brackets compress sharply, sometimes triggering a large unexpected tax bill. This controls how much the plan prioritizes shrinking pretax accounts beforehand to reduce that damage.",
    impact: "Higher weight drives more aggressive Roth conversions before a likely spouse death to shrink the pretax balance and protect against bracket compression. Lower weight does fewer conversions and accepts more risk.",
    consider: "Set higher if one spouse is significantly older or in poorer health, making a mortality gap likely. Set lower if both are similar age or if the survivor will have other income to cushion withdrawals.",
  },
  decedent_balances_pass_to_survivor: {
    purpose: "When one spouse dies, are all their retirement accounts—IRA, 401(k), Roth, HSA, and similar—rolled into the survivor's accounts as one consolidated pool?",
    impact: "When ON, accounts merge and Required Minimum Distributions are based on the survivor's (usually younger) age, often lowering mandatory withdrawals and increasing flexibility. When OFF, accounts stay separate with possibly higher RMD requirements.",
    consider: "Turn ON if the survivor is younger and will manage one unified account—this is simpler and more tax-efficient. Turn OFF if the survivor is older or if accounts have separate restrictions.",
  },
  tlh_annual_ceiling: {
    purpose: "Tax-loss harvesting uses investment losses to offset gains and lower taxes. This setting caps the amount of loss harvested per year, with zero meaning unlimited.",
    impact: "Higher ceiling allows more harvesting and greater tax savings. A zero (unlimited) ceiling captures every opportunity; a capped ceiling keeps activity and benefit predictable.",
    consider: "Unlimited (zero) usually maximizes tax efficiency. Cap it only if you want to stagger harvesting across multiple years or limit trading frequency.",
  },
  tlh_fraction_sold_before_death: {
    purpose: "After harvesting a loss, the plan replaces it with a similar investment. This assumes a fraction of those replacements will be sold before death (triggering capital gains tax and losing the tax-free step-up benefit) instead of held until death.",
    impact: "Higher percentage means more replacements get sold before death, reducing the total long-term tax benefit calculated. Lower percentage assumes you'll hold until death, keeping the full benefit intact.",
    consider: "Use lower if you plan to hold investments long-term with minimal selling before retirement ends. Use higher if you expect frequent rebalancing or years with large withdrawals.",
  },
  tlh_min_loss_dollars: {
    purpose: "The minimum dollar loss on a single position worth harvesting, to avoid trading tiny losses when the trading cost outweighs the tax benefit.",
    impact: "Higher minimum reduces trading activity and avoids trivial trades. Lower minimum harvests small losses, potentially creating many small trades.",
    consider: "Set roughly to your broker's round-trip trading cost—often $100-500 for retail investors—so you don't make trades where the cost exceeds the tax savings.",
  },
  tlh_min_loss_pct: {
    purpose: "The minimum loss as a percentage of what you originally paid for an investment, to avoid harvesting near-breakeven positions.",
    impact: "Higher percentage means only deeply underwater investments qualify for harvesting. Lower percentage includes modestly down investments, potentially increasing trading volume.",
    consider: "1-2% is typical for most portfolio positions. Too low and you're trading near-breakeven lots; too high and you might miss real harvesting opportunities.",
  },
  tlh_policy: {
    purpose: "Turns tax-loss harvesting on, off, or to analysis-only mode. 'Off' ignores harvesting; 'Analyze only' shows opportunities without changing the plan; 'apply' harvests losses in the projection.",
    impact: "'Off' has no effect on taxes or net worth. 'Analyze only' displays opportunities for your review without affecting the projection. 'Apply' harvests losses each year, typically lowering lifetime taxes and boosting after-tax wealth.",
    consider: "Start with 'Analyze only' to see if meaningful opportunities exist in your portfolio. If the tax savings look significant, switch to 'Apply' to make harvesting part of your strategy.",
  },
  tlh_transaction_cost_bps: {
    purpose: "The cost to buy and sell an investment, measured in basis points (hundredths of a percent). 2 basis points = 0.02%, 100 basis points = 1%. Typical low-cost brokers charge 0-5 basis points per round trip.",
    impact: "Higher cost means fewer harvesting opportunities pencil out because the tax savings must exceed the trading cost. Lower cost means more trades are worth doing.",
    consider: "Check your broker's fee schedule—many online brokers charge 0-5 basis points. If you use a financial advisor charging a percentage of assets under management, factor that into your estimate too.",
  },
  h_ssa44_relief_year: {
    purpose: "Form SSA-44 lets you ask Social Security to reduce or eliminate extra Medicare premiums (called IRMAA surcharges) after a major life change like retirement or a big income drop. This field records the first year that relief takes effect, if approved. Leave it blank if you have not filed or received approval.",
    impact: "When relief is approved, extra Medicare premiums drop in that year and beyond, lowering out-of-pocket health costs. Base Medicare premiums are still owed, only the surcharge is relieved.",
    consider: "Only enter a year here if Social Security has already approved your appeal. Do not guess or assume.",
  },
  w_ssa44_relief_year: {
    purpose: "Form SSA-44 lets you ask Social Security to reduce or eliminate extra Medicare premiums (called IRMAA surcharges) after a major life change like retirement or a big income drop. This field records the first year that relief takes effect, if approved. Leave it blank if you have not filed or received approval.",
    impact: "When relief is approved, extra Medicare premiums drop in that year and beyond, lowering out-of-pocket health costs. Base Medicare premiums are still owed, only the surcharge is relieved.",
    consider: "Only enter a year here if Social Security has already approved your appeal. Do not guess or assume.",
  },
  member_1_rmd_start_age: {
    purpose: "The age when each person must start taking Required Minimum Distributions (RMDs) from retirement accounts. Most people start in their early to mid-70s by law, but you can override the default.",
    impact: "Earlier start means smaller withdrawals per year but money stops compounding sooner; later means larger mandatory pulls later. This affects taxable income and ongoing growth.",
    consider: "Use the default age unless you have a good reason to change it. Don't start early just for access — early withdrawals have tax penalties until age 59½.",
  },
  member_2_rmd_start_age: {
    purpose: "The age when each person must start taking Required Minimum Distributions (RMDs) from retirement accounts. Most people start in their early to mid-70s by law, but you can override the default.",
    impact: "Earlier start means smaller withdrawals per year but money stops compounding sooner; later means larger mandatory pulls later. This affects taxable income and ongoing growth.",
    consider: "Use the default age unless you have a good reason to change it. Don't start early just for access — early withdrawals have tax penalties until age 59½.",
  },
  extra_1_amount: {
    purpose: "This is the dollar amount of a large discretionary expense — like a vacation, wedding, home project, or car. If it repeats every year, put the annual amount. If it's one-time, put the total cost.",
    impact: "Raising the amount means more spending on that item, requiring more income or savings to cover it. Lowering it reduces the spending assumption.",
    consider: "Break out big one-time or occasional expenses here so the plan doesn't confuse them with regular monthly spending — this helps you see whether you can actually afford them.",
  },
  extra_2_amount: {
    purpose: "This is the dollar amount of a large discretionary expense — like a vacation, wedding, home project, or car. If it repeats every year, put the annual amount. If it's one-time, put the total cost.",
    impact: "Raising the amount means more spending on that item, requiring more income or savings to cover it. Lowering it reduces the spending assumption.",
    consider: "Break out big one-time or occasional expenses here so the plan doesn't confuse them with regular monthly spending — this helps you see whether you can actually afford them.",
  },
  extra_3_amount: {
    purpose: "This is the dollar amount of a large discretionary expense — like a vacation, wedding, home project, or car. If it repeats every year, put the annual amount. If it's one-time, put the total cost.",
    impact: "Raising the amount means more spending on that item, requiring more income or savings to cover it. Lowering it reduces the spending assumption.",
    consider: "Break out big one-time or occasional expenses here so the plan doesn't confuse them with regular monthly spending — this helps you see whether you can actually afford them.",
  },
  extra_4_amount: {
    purpose: "This is the dollar amount of a large discretionary expense — like a vacation, wedding, home project, or car. If it repeats every year, put the annual amount. If it's one-time, put the total cost.",
    impact: "Raising the amount means more spending on that item, requiring more income or savings to cover it. Lowering it reduces the spending assumption.",
    consider: "Break out big one-time or occasional expenses here so the plan doesn't confuse them with regular monthly spending — this helps you see whether you can actually afford them.",
  },
  extra_5_amount: {
    purpose: "This is the dollar amount of a large discretionary expense — like a vacation, wedding, home project, or car. If it repeats every year, put the annual amount. If it's one-time, put the total cost.",
    impact: "Raising the amount means more spending on that item, requiring more income or savings to cover it. Lowering it reduces the spending assumption.",
    consider: "Break out big one-time or occasional expenses here so the plan doesn't confuse them with regular monthly spending — this helps you see whether you can actually afford them.",
  },
  extra_1_comment: {
    purpose: "This is an optional text note to remind you what the expense is for — for example, \"Kitchen renovation\" or \"Europe trip summer 2028\". It's purely for your reference.",
    impact: "This field has no impact on the plan's math.",
    consider: "Use short, clear descriptions so you can quickly remember what each expense line represents.",
  },
  extra_2_comment: {
    purpose: "This is an optional text note to remind you what the expense is for — for example, \"Kitchen renovation\" or \"Europe trip summer 2028\". It's purely for your reference.",
    impact: "This field has no impact on the plan's math.",
    consider: "Use short, clear descriptions so you can quickly remember what each expense line represents.",
  },
  extra_3_comment: {
    purpose: "This is an optional text note to remind you what the expense is for — for example, \"Kitchen renovation\" or \"Europe trip summer 2028\". It's purely for your reference.",
    impact: "This field has no impact on the plan's math.",
    consider: "Use short, clear descriptions so you can quickly remember what each expense line represents.",
  },
  extra_4_comment: {
    purpose: "This is an optional text note to remind you what the expense is for — for example, \"Kitchen renovation\" or \"Europe trip summer 2028\". It's purely for your reference.",
    impact: "This field has no impact on the plan's math.",
    consider: "Use short, clear descriptions so you can quickly remember what each expense line represents.",
  },
  extra_5_comment: {
    purpose: "This is an optional text note to remind you what the expense is for — for example, \"Kitchen renovation\" or \"Europe trip summer 2028\". It's purely for your reference.",
    impact: "This field has no impact on the plan's math.",
    consider: "Use short, clear descriptions so you can quickly remember what each expense line represents.",
  },
  extra_1_end_year: {
    purpose: "If a large discretionary expense repeats every year (like an annual vacation), this is the last year it continues. Leave it blank if you want it to repeat through the end of the plan.",
    impact: "Setting an end year stops the expense after that year, reducing future spending needs. Leaving it blank means the expense repeats as long as the plan runs.",
    consider: "Use this for expenses that won't last forever — for example, a vacation while kids are young, or a multi-year home project.",
  },
  extra_2_end_year: {
    purpose: "If a large discretionary expense repeats every year (like an annual vacation), this is the last year it continues. Leave it blank if you want it to repeat through the end of the plan.",
    impact: "Setting an end year stops the expense after that year, reducing future spending needs. Leaving it blank means the expense repeats as long as the plan runs.",
    consider: "Use this for expenses that won't last forever — for example, a vacation while kids are young, or a multi-year home project.",
  },
  extra_3_end_year: {
    purpose: "If a large discretionary expense repeats every year (like an annual vacation), this is the last year it continues. Leave it blank if you want it to repeat through the end of the plan.",
    impact: "Setting an end year stops the expense after that year, reducing future spending needs. Leaving it blank means the expense repeats as long as the plan runs.",
    consider: "Use this for expenses that won't last forever — for example, a vacation while kids are young, or a multi-year home project.",
  },
  extra_4_end_year: {
    purpose: "If a large discretionary expense repeats every year (like an annual vacation), this is the last year it continues. Leave it blank if you want it to repeat through the end of the plan.",
    impact: "Setting an end year stops the expense after that year, reducing future spending needs. Leaving it blank means the expense repeats as long as the plan runs.",
    consider: "Use this for expenses that won't last forever — for example, a vacation while kids are young, or a multi-year home project.",
  },
  extra_5_end_year: {
    purpose: "If a large discretionary expense repeats every year (like an annual vacation), this is the last year it continues. Leave it blank if you want it to repeat through the end of the plan.",
    impact: "Setting an end year stops the expense after that year, reducing future spending needs. Leaving it blank means the expense repeats as long as the plan runs.",
    consider: "Use this for expenses that won't last forever — for example, a vacation while kids are young, or a multi-year home project.",
  },
  extra_1_start_year: {
    purpose: "If a large discretionary expense repeats every year, this is the first year it starts. Leave it blank if it starts in the first year of the plan.",
    impact: "Moving the start year earlier means the expense appears sooner and for more years total. Moving it later delays the expense, reducing early-year spending.",
    consider: "Use this to model when major recurring expenses like annual vacations or home maintenance will actually begin.",
  },
  extra_2_start_year: {
    purpose: "If a large discretionary expense repeats every year, this is the first year it starts. Leave it blank if it starts in the first year of the plan.",
    impact: "Moving the start year earlier means the expense appears sooner and for more years total. Moving it later delays the expense, reducing early-year spending.",
    consider: "Use this to model when major recurring expenses like annual vacations or home maintenance will actually begin.",
  },
  extra_3_start_year: {
    purpose: "If a large discretionary expense repeats every year, this is the first year it starts. Leave it blank if it starts in the first year of the plan.",
    impact: "Moving the start year earlier means the expense appears sooner and for more years total. Moving it later delays the expense, reducing early-year spending.",
    consider: "Use this to model when major recurring expenses like annual vacations or home maintenance will actually begin.",
  },
  extra_4_start_year: {
    purpose: "If a large discretionary expense repeats every year, this is the first year it starts. Leave it blank if it starts in the first year of the plan.",
    impact: "Moving the start year earlier means the expense appears sooner and for more years total. Moving it later delays the expense, reducing early-year spending.",
    consider: "Use this to model when major recurring expenses like annual vacations or home maintenance will actually begin.",
  },
  extra_5_start_year: {
    purpose: "If a large discretionary expense repeats every year, this is the first year it starts. Leave it blank if it starts in the first year of the plan.",
    impact: "Moving the start year earlier means the expense appears sooner and for more years total. Moving it later delays the expense, reducing early-year spending.",
    consider: "Use this to model when major recurring expenses like annual vacations or home maintenance will actually begin.",
  },
  extra_1_type: {
    purpose: "This is the category you pick for a large, one-time or repeatable discretionary expense — like a vacation, home renovation, or wedding. You choose a label so the plan can track it separately from everyday spending.",
    impact: "Changing the category doesn't change the cost or when it happens — it's just for organizing and understanding what types of large expenses your plan includes.",
    consider: "Pick a category that makes sense to you for tracking; the exact label doesn't affect the math, just the clarity of your retirement plan.",
  },
  extra_2_type: {
    purpose: "This is the category you pick for a large, one-time or repeatable discretionary expense — like a vacation, home renovation, or wedding. You choose a label so the plan can track it separately from everyday spending.",
    impact: "Changing the category doesn't change the cost or when it happens — it's just for organizing and understanding what types of large expenses your plan includes.",
    consider: "Pick a category that makes sense to you for tracking; the exact label doesn't affect the math, just the clarity of your retirement plan.",
  },
  extra_3_type: {
    purpose: "This is the category you pick for a large, one-time or repeatable discretionary expense — like a vacation, home renovation, or wedding. You choose a label so the plan can track it separately from everyday spending.",
    impact: "Changing the category doesn't change the cost or when it happens — it's just for organizing and understanding what types of large expenses your plan includes.",
    consider: "Pick a category that makes sense to you for tracking; the exact label doesn't affect the math, just the clarity of your retirement plan.",
  },
  extra_4_type: {
    purpose: "This is the category you pick for a large, one-time or repeatable discretionary expense — like a vacation, home renovation, or wedding. You choose a label so the plan can track it separately from everyday spending.",
    impact: "Changing the category doesn't change the cost or when it happens — it's just for organizing and understanding what types of large expenses your plan includes.",
    consider: "Pick a category that makes sense to you for tracking; the exact label doesn't affect the math, just the clarity of your retirement plan.",
  },
  extra_5_type: {
    purpose: "This is the category you pick for a large, one-time or repeatable discretionary expense — like a vacation, home renovation, or wedding. You choose a label so the plan can track it separately from everyday spending.",
    impact: "Changing the category doesn't change the cost or when it happens — it's just for organizing and understanding what types of large expenses your plan includes.",
    consider: "Pick a category that makes sense to you for tracking; the exact label doesn't affect the math, just the clarity of your retirement plan.",
  },
  extra_1_year: {
    purpose: "For a one-time extra expense, enter the year it will happen — like 2028 for a planned vacation or home project. Leave this blank if the expense repeats every year.",
    impact: "If you enter a year, the expense appears in that year only. If you leave it blank, the expense repeats annually in your plan.",
    consider: "Use this for major one-time spending you know about in advance, like a wedding or milestone birthday celebration.",
  },
  extra_2_year: {
    purpose: "For a one-time extra expense, enter the year it will happen — like 2028 for a planned vacation or home project. Leave this blank if the expense repeats every year.",
    impact: "If you enter a year, the expense appears in that year only. If you leave it blank, the expense repeats annually in your plan.",
    consider: "Use this for major one-time spending you know about in advance, like a wedding or milestone birthday celebration.",
  },
  extra_3_year: {
    purpose: "For a one-time extra expense, enter the year it will happen — like 2028 for a planned vacation or home project. Leave this blank if the expense repeats every year.",
    impact: "If you enter a year, the expense appears in that year only. If you leave it blank, the expense repeats annually in your plan.",
    consider: "Use this for major one-time spending you know about in advance, like a wedding or milestone birthday celebration.",
  },
  extra_4_year: {
    purpose: "For a one-time extra expense, enter the year it will happen — like 2028 for a planned vacation or home project. Leave this blank if the expense repeats every year.",
    impact: "If you enter a year, the expense appears in that year only. If you leave it blank, the expense repeats annually in your plan.",
    consider: "Use this for major one-time spending you know about in advance, like a wedding or milestone birthday celebration.",
  },
  extra_5_year: {
    purpose: "For a one-time extra expense, enter the year it will happen — like 2028 for a planned vacation or home project. Leave this blank if the expense repeats every year.",
    impact: "If you enter a year, the expense appears in that year only. If you leave it blank, the expense repeats annually in your plan.",
    consider: "Use this for major one-time spending you know about in advance, like a wedding or milestone birthday celebration.",
  },
  heloc_credit_limit: {
    purpose: "This is the maximum amount of money the plan can borrow from the HELOC at any one time — like a credit limit. The plan won't borrow more than this amount, no matter what large expenses come up.",
    impact: "A lower limit means less cash is available for big one-time expenses; a higher limit gives more flexibility. If the limit is too low, you might be forced to sell investments or reduce spending when an expense hits.",
    consider: "Check what credit your lender actually offers, and use a number you're truly comfortable borrowing — not just the technical maximum.",
  },
  heloc_draw_end_year: {
    purpose: "This is the last year the plan is allowed to borrow from the HELOC. After this year, no new borrowing happens, though any outstanding balance keeps accruing interest until it's paid back.",
    impact: "An earlier end-year forces you to find other funding (savings or investment sales) for large expenses in later years. A later end-year keeps borrowing available longer but extends the time you're carrying debt.",
    consider: "Set this based on when you expect to stop having big one-time expenses — perhaps when the mortgage is paid off or when you're well into your late 70s.",
  },
  heloc_initial_rate_pct: {
    purpose: "This is the annual interest rate you'll pay on borrowed HELOC money — the cost of borrowing. It's typically lower than a credit card because the house backs the debt.",
    impact: "A higher rate makes borrowing more expensive each year in interest costs; a lower rate makes it cheaper. The rate directly affects how much cash you need set aside for interest payments annually.",
    consider: "Only borrow if you think your investments will grow faster than the interest you'll pay — otherwise it doesn't make financial sense.",
  },
  heloc_rate_drift_bps_yr: {
    purpose: "This models the HELOC interest rate rising over time (a basis point is 1/100th of a percent — so 25 basis points means a 0.25% annual rise). It accounts for the possibility that interest rates climb during the years you're borrowing.",
    impact: "Higher drift means your borrowing costs increase each year — it gets progressively more expensive. Zero drift assumes the rate stays flat throughout.",
    consider: "Use this if you expect broad interest rates to rise; set it to zero if you think rates will hold steady or fall.",
  },
  heloc_repayment_years: {
    purpose: "After the plan stops borrowing (at the draw-end year), this is how many years you have to pay back the HELOC balance in full. Each year you pay both principal and interest on a fixed schedule.",
    impact: "Shorter repayment (5 years) means bigger annual payments but you're debt-free faster and pay less total interest. Longer repayment (10 years) spreads payments smaller but you stay in debt longer and pay more total interest.",
    consider: "Seven to ten years is typical; try to align repayment with when you expect major cash inflows like home-sale proceeds.",
  },
  annual_grant_amount: {
    purpose: "This is how much money the Donor-Advised Fund sends to charities each year during the grant period. A Donor-Advised Fund is like a giving account where you deposit money upfront (and get an immediate tax deduction), then recommend grants to charities over time.",
    impact: "Larger annual grants mean faster drawdown of the fund but more charitable impact each year; smaller grants let the fund grow longer and preserve money for future years of giving. The size directly affects the fund's balance and longevity.",
    consider: "Start with grants equal to the fund's annual investment income, or commit to increasing grants gradually over time to let it compound.",
  },
  contribution_amount: {
    purpose: "This is the lump-sum amount you put into the Donor-Advised Fund in the contribution year — the initial deposit that kicks off the whole giving strategy.",
    impact: "A larger contribution gives a bigger upfront tax deduction (subject to income limits) and more money available for future grants. A smaller contribution is simpler but generates smaller upfront tax savings.",
    consider: "Use appreciated stock or a high-income year for a large contribution to maximize the tax benefit.",
  },
  contribution_is_appreciated: {
    purpose: "This marks whether your Donor-Advised Fund contribution is appreciated securities (like stock that's gained value) or cash. The tax rules treat them differently — appreciated securities hit a stricter deduction cap.",
    impact: "If true (securities), your deductible amount caps at 30% of adjusted gross income, with excess carried forward up to 5 years. If false (cash), the cap is 60%. Either way you get an upfront deduction, but securities need more years to use the full benefit if you contribute a large lump sum.",
    consider: "Appreciated securities avoid capital-gains tax on the gain while giving you a deduction — usually a huge win despite the tighter limit — so use them if you have them.",
  },
  contribution_year: {
    purpose: "The year you make the lump-sum contribution to the Donor-Advised Fund.",
    impact: "Earlier contribution means an earlier tax deduction and more years for the money to grow before you start making grants. Later contribution delays both the tax benefit and the compounding time.",
    consider: "Contribute in high-income years (bonuses, business sale proceeds, large investment gains) to maximize the tax-deduction value.",
  },
  grant_start_year: {
    purpose: "The first year the Donor-Advised Fund begins sending money out to charities.",
    impact: "Earlier start means charities receive grants sooner but the fund balance shrinks faster. Later start delays charitable giving but lets the fund grow larger before distributions begin.",
    consider: "You can wait months or years after contributing before starting grants — use this flexibility if you haven't yet decided which charities to support.",
  },
  grant_end_year: {
    purpose: "The last year the Donor-Advised Fund sends grants to charities. After this year, no more distributions are made.",
    impact: "An earlier end-year finishes your fund giving sooner; a later end-year extends charitable distributions over a longer span. The end-year affects how much the fund can grow and whether a balance remains.",
    consider: "Set this based on your charitable giving timeline — perhaps 10-20 years out, or whenever you expect other income sources to take over.",
  },
  ss_funding_discount_pct: {
    purpose: "This is a stress test for Social Security. It models what happens if Congress doesn't fix the trust-fund shortfall and benefits are cut to whatever incoming taxes can cover. The default is a 22% reduction — a middle-ground estimate based on trustee projections.",
    impact: "When the discount year arrives, your Social Security income gets cut by this percentage permanently. This shows whether your retirement plan still works even if Social Security benefits are trimmed from today's promised levels.",
    consider: "If your plan stays solid with a 22% cut, you have good cushion. If it breaks, you'll need to save more, spend less, or work longer.",
  },
  ss_funding_discount_year: {
    purpose: "The first year that Social Security benefits are reduced due to trust-fund underfunding. The default is 2032, based on the Social Security Trustees' current projection of when the trust fund runs out.",
    impact: "Benefits before this year are paid at full current-law amounts; from this year onward, they're cut by the discount percentage. This year marks when the stress test kicks in for your retirement plan.",
    consider: "Congress could change the solvency date through legislation; adjust this if you want to test an earlier or later cut-in scenario.",
  },
  claim_age: {
    purpose: "The age at which you claim your Social Security benefit. You can claim as early as 62 or as late as 70; each year you wait, your monthly benefit gets bigger (called a delayed retirement credit).",
    impact: "Claiming at 62 gives a smaller monthly check but payments start immediately; claiming at 70 gives a larger monthly check but you wait 8 years. The total lifetime benefit depends on how long you live — if you live into your 80s, waiting usually wins.",
    consider: "Test the plan at 62, 67, and 70 to see which claiming age balances your life expectancy with your cash-flow needs.",
  },
  fra_age: {
    purpose: "Full Retirement Age is the age when Social Security says you're 'fully retired' for benefit purposes — set by the Social Security Administration based on birth year. For anyone born 1960 or later, it's 67; for earlier birth years it's between 66 and 67. Enter 0 to have the app calculate it from your birth date.",
    impact: "Full Retirement Age is the anchor point for early/delayed multipliers — claim before and your benefit is permanently smaller; claim after and it's permanently bigger. It determines how much you receive relative to your claiming age.",
    consider: "Unless you've memorized your exact FRA from your Social Security statement, leave this at zero and let the app figure it from your birth year.",
  },
  spousal_benefits_enabled: {
    purpose: "Social Security allows a spouse with lower lifetime earnings to get an additional spousal benefit on top of their own benefit, based on the higher-earning spouse's record. This setting turns that strategy on or off.",
    impact: "When enabled, the plan checks whether a spousal top-up would help and includes it in household cash flow — can add several hundred dollars a month in high-earning households. When disabled, each spouse only gets their own benefit.",
    consider: "Turn this on if one spouse earned much less over their career than the other — there's no minimum-years-married rule for a current spouse (that 10-year rule only applies to divorced-spouse benefits).",
  },
  survivor_benefit_uses_deceased_claim_age: {
    purpose: "When one spouse dies, Social Security pays a survivor benefit to the surviving spouse. This setting determines whether the survivor's payment uses the deceased spouse's actual claiming age, or a different calculation.",
    impact: "If true, the survivor's benefit is computed from the deceased's chosen claiming age. If false, other Social Security rules apply. This affects the survivor's monthly cash flow after a spouse dies.",
    consider: "This is a technical Social Security rule; the actual benefit would be confirmed by Social Security after a death, so treat this as one planning scenario.",
  },
  survivor_pct_of_higher_benefit: {
    purpose: "This is what percentage of the higher-earning spouse's Social Security benefit continues to a surviving spouse after the higher earner dies. 100% means the survivor gets the full amount the higher earner was collecting; lower percentages mean the survivor gets less.",
    impact: "A higher percentage means better financial protection for the survivor; 100% is standard for a surviving spouse at their full retirement age or older. Some claiming scenarios may reduce this percentage.",
    consider: "The Social Security rules are fixed, not adjustable; use this field to match your understanding of what benefits your spouse would actually receive — usually close to 100% if the survivor doesn't claim very early.",
  },
};
function fieldDefaultMeaning(row) {
  const label = humanLabel(row.label, row);
  const l = norm(row.label),
    s = norm(row.section),
    sub = norm(row.subsection),
    kind = valueKind(row),
    group = friendlyGroup(row);
  if (l.includes("name") || l.includes("beneficiary") || l.includes("owner"))
    return `Identifies the person, entity, account owner, or planning goal associated with ${label}. This label lets the workbook separate otherwise similar rows and attach cash flows, assets, taxes, or benefits to the right household context.`;
  if (l.includes("dob") || l.includes("birth"))
    return `Records the actual birth date used to calculate age-based rules such as retirement timing, Social Security, Medicare, RMDs, survivor periods, and planning horizon.`;
  if (l.includes("date") || l.includes("year") || l.includes("age"))
    return `Places ${label} on the model timeline so the projection knows when the related income, expense, benefit, tax rule, account change, or planning event starts, ends, or is evaluated.`;
  if (l.includes("filing_status"))
    return "Selects the tax filing status used to apply federal and state tax brackets, deductions, Medicare thresholds, and survivor-year tax treatment.";
  if (l.includes("state") || l.includes("residency"))
    return `Specifies the state or residency assumption used for state income tax, estate-tax exposure, relocation analysis, and report labeling.`;
  if (
    l.includes("salary") ||
    l.includes("w2") ||
    l.includes("self_employment") ||
    l.includes("income") ||
    l.includes("earnings") ||
    l.includes("benefit") ||
    s.includes("income")
  )
    return `Describes a cash inflow the household expects to receive. The projection uses it to fund spending before drawing portfolio assets and to calculate taxable income, payroll tax, Roth conversion room, Medicare thresholds, and lifetime taxes.`;
  if (
    l.includes("spending") ||
    l.includes("expense") ||
    l.includes("premium") ||
    l.includes("cost") ||
    l.includes("tax") ||
    l.includes("tuition") ||
    l.includes("travel") ||
    l.includes("vacation") ||
    l.includes("wedding") ||
    l.includes("home_project")
  )
    return `Describes a cash outflow the plan must fund. The projection uses it to determine annual withdrawal needs, interim liquidity pressure, Monte Carlo failures, terminal net worth, and lifetime-tax side effects.`;
  if (
    l.includes("asset") ||
    l.includes("account") ||
    l.includes("balance") ||
    l.includes("value") ||
    l.includes("basis") ||
    l.includes("holding") ||
    s.includes("assets")
  )
    return `Quantifies or classifies an asset, account, holding, or basis item. The model uses it to set starting net worth, liquidity, asset allocation, tax-lot gain/loss estimates, estate values, and account-level reporting.`;
  if (
    l.includes("debt") ||
    l.includes("loan") ||
    l.includes("mortgage") ||
    l.includes("liability") ||
    l.includes("principal")
  )
    return `Describes an amount owed, payment obligation, interest assumption, or payoff timing. It reduces net worth and can create recurring cash-flow needs until the liability is repaid.`;
  if (
    l.includes("contribution") ||
    l.includes("saving") ||
    l.includes("deferral")
  )
    return `Defines money expected to move into an account or savings vehicle. Contributions can improve future net worth but may reduce current cash flow and change taxable income or payroll deductions.`;
  if (
    l.includes("withdrawal") ||
    l.includes("distribution") ||
    l.includes("rmd")
  )
    return `Defines money expected to leave an account or the rule used to take required distributions. It can affect taxable income, cash-flow funding, account depletion, and Medicare thresholds.`;
  if (
    kind === "percent" ||
    l.includes("rate") ||
    l.includes("pct") ||
    l.includes("growth") ||
    l.includes("inflation") ||
    l.includes("return") ||
    l.includes("yield") ||
    l.includes("volatility") ||
    l.includes("correlation")
  )
    return `Sets a percentage-based assumption that scales a projection behavior such as growth, inflation, return, tax rate, allocation, volatility, correlation, or guardrail headroom.`;
  if (l.includes("roth") || sub.includes("roth"))
    return `Controls a Roth conversion or Roth-scoring assumption used to compare current taxes against future RMDs, survivor tax compression, Medicare thresholds, estate exposure, and Roth legacy value.`;
  if (
    l.includes("allocation") ||
    l.includes("target") ||
    l.includes("optimizer") ||
    s.includes("asset_class")
  )
    return `Controls how an asset class or optimizer rule participates in the recommended portfolio. It can change target allocation, drift, trade size, tax-aware rebalancing, and whether existing non-liquid assets cover a sleeve.`;
  if (
    l.includes("insurance") ||
    l.includes("ltc") ||
    l.includes("death_benefit") ||
    l.includes("survivor")
  )
    return `Describes a protection or survivor-planning assumption. It helps the workbook measure risk transfer, late-life care exposure, survivor income, estate value, and downside liquidity needs.`;
  if (
    l.includes("pricing") ||
    l.includes("ticker") ||
    l.includes("symbol") ||
    s.includes("market")
  )
    return `Identifies how a holding or market-data input should be valued. Accurate pricing supports account totals, allocation drift, tax-lot gain/loss estimates, and trade recommendations.`;
  if (s.includes("ytd"))
    return `Classifies year-to-date activity or an account balance so the YTD dashboard can compare actual transactions, prior-year balances, current values, income extrapolation, spending categories, and growth diagnostics.`;
  if (s.includes("monte_carlo") || l.includes("success_probability"))
    return `Controls how the model tests uncertain future returns and spending paths instead of relying only on the base projection. It influences probability of success, downside wealth, liquidity failure timing, and build duration.`;
  if (kind === "currency")
    return `Records a dollar amount used by ${group}. The model treats the amount as cash flow, asset value, liability, tax, benefit, or reserve depending on the surrounding page and row context.`;
  if (kind === "number")
    return `Records a numeric planning assumption used by ${group}. The number may represent a count, age, year, limit, ranking, or model setting depending on the label and nearby fields.`;
  return `Documents the ${label} assumption within ${group}. The projection reads it with nearby fields to classify, time, or quantify this part of the household plan and carry the result into workbook outputs.`;
}

function yesNoOptionHelp(row) {
  const label = humanLabel(row.label, row).toLowerCase();
  return [
    `<b>YES</b>: include, enable, or assume this ${esc(label)} applies in the plan.`,
    `<b>NO</b>: exclude, disable, or assume this ${esc(label)} does not apply.`,
  ];
}
function choiceHelpText(row, opt) {
  const v = norm(choiceValue(opt)),
    l = norm(row.label);
  const display = esc(formatAcronyms(choiceLabel(opt).replace(/_/g, " ")));
  const maps = {
    user_target:
      "Use the editable user target percentages as the allocation recommendation.",
    optimizer_recommendation:
      "Let the optimizer choose the allocation using risk, return, volatility, correlation, and constraints.",
    include: "Allow this asset class or setting to be used directly.",
    exclude: "Do not recommend this asset class or setting.",
    consider_alternate_first:
      "Credit an existing asset or income source before recommending new exposure.",
    cpi: "Increase spending with the general inflation assumption.",
    manual_override: "Use the manual growth rate instead of CPI.",
    quick_vectorized:
      "Faster directional Monte Carlo approximation for drafts and diagnostics.",
    advanced_exact_scalar:
      "Slower advisor-ready Monte Carlo using the full projection path.",
    ignore: "Do not constrain the recommendation for this threshold.",
    warn_only: "Allow the action but flag the threshold crossing.",
    avoid_next_tier: "Stop or reduce the action before the next IRMAA tier.",
    avoid_tier_2_or_above:
      "Avoid larger Medicare premium jumps, not just the first tier.",
    custom_magi_cap: "Use a manually entered MAGI ceiling.",
    off: "Turn this objective or module off.",
    monitor_only:
      "Calculate and show exposure without materially steering the recommendation.",
    balanced: "Use this objective as one part of the recommendation score.",
    strong: "Give this objective more influence in scoring.",
    none: "Do not use this strategy or objective.",
    fixed_dollar:
      "Use the entered fixed-dollar amount instead of letting the model size it.",
  };
  return `<b>${display}</b>: ${esc(maps[v] || "Select this when it best matches the real-world assumption or planning objective for this field.")}`;
}
function fieldAllowedValues(row) {
  const units = String(row.units || "").trim();
  const type = String(row.schema?.type || "").toLowerCase();
  const boolish =
    type === "boolean" ||
    /^(yes\/no|true\/false)$/i.test(units) ||
    /^(YES|NO|TRUE|FALSE)$/i.test(valOf(row));
  if (boolish) return helpList(yesNoOptionHelp(row));
  const opts = choiceOptions(row);
  if (opts && opts.length)
    return helpList(opts.map((o) => choiceHelpText(row, o)));
  const kind = valueKind(row);
  if (isDateField(row))
    return "<p>Use a calendar date. Consistent dates allow the model to place the value in the right tax year, age year, or cash-flow year.</p>";
  if (kind === "currency")
    return "<p>Enter dollars. Higher dollar amounts usually increase the item being modeled; whether that helps or hurts depends on whether the field is an asset, income, tax, liability, contribution, or expense.</p>";
  if (kind === "percent")
    return "<p>Enter a percentage. For rates, higher values usually amplify the related growth, tax, return, inflation, allocation, or guardrail effect.</p>";
  if (kind === "number")
    return "<p>Enter a number, age, year, count, or ranking as described by the label. Whole-number fields should generally not include decimals.</p>";
  if (units) return `<p>Expected format: ${esc(formatAcronyms(units))}.</p>`;
  return "<p>Use the value that best matches the documented fact, current estimate, or scenario assumption. When unsure, open nearby related fields before changing it.</p>";
}
function fieldConnection(row) {
  const l = norm(row.label),
    s = norm(row.section),
    sub = norm(row.subsection);
  if (l.includes("retirement"))
    return "This connects work income, savings, healthcare bridge costs, withdrawals, Social Security timing, and Monte Carlo sequence risk.";
  if (
    l.includes("spending") ||
    l.includes("expense") ||
    l.includes("travel") ||
    l.includes("vacation") ||
    l.includes("wedding")
  )
    return "This connects to annual cash-flow needs, withdrawals, YTD spending comparisons, Planning Levers, terminal net worth, and probability of success.";
  if (
    l.includes("income") ||
    l.includes("salary") ||
    l.includes("w2") ||
    l.includes("self_employment")
  )
    return "This connects to annual cash flow, payroll taxes, savings capacity, taxable income, Roth conversion room, and lifetime taxes.";
  if (l.includes("roth") || sub.includes("roth"))
    return "This connects to current taxable income, future RMDs, IRMAA guardrails, survivor tax compression, Roth legacy value, and the Roth comparison table.";
  if (l.includes("irmaa"))
    return "This connects MAGI to Medicare premium tiers and can limit Roth conversions or other income-triggering actions.";
  if (
    l.includes("allocation") ||
    l.includes("target") ||
    s.includes("asset_class") ||
    s.includes("asset_allocation")
  )
    return "This connects holdings, capital-market assumptions, user targets, optimizer targets, non-liquid coverage, drift, and trade recommendations.";
  if (l.includes("mortgage") || l.includes("real_estate"))
    return "This connects housing value, debt, property-tax spending, liquidity pressure, net worth, and possible home-sale scenarios.";
  if (l.includes("tax") || s.includes("tax"))
    return "This connects taxable income, deductions, brackets, estate exposure, Roth scoring, and lifetime-tax reporting.";
  if (
    l.includes("premium") ||
    s.includes("wellness") ||
    s.includes("insurance") ||
    s.includes("ltc")
  )
    return "This connects annual spending, survivor and LTC stress tests, protection analysis, and late-life liquidity needs.";
  if (s.includes("ytd"))
    return "This connects imported transactions, account mapping, current values, prior-year balances, spending charts, income extrapolation, and growth diagnostics.";
  if (s.includes("monte_carlo"))
    return "This connects simulation assumptions, build time, probability of success, downside wealth ranges, and liquidity-failure diagnostics.";
  return `This value sits in ${esc(friendlyGroup(row))}. Review nearby fields in the same page because they are usually read together when the projection, workbook, or recommendation is built.`;
}
function fieldLikelyImpact(row, g) {
  const base = String(g.impact || "");
  const consider = String(g.consider || "");
  const kind = valueKind(row);
  const l = norm(row.label);
  let directional = "";
  if (kind === "currency") {
    if (
      hasAny(l, [
        "expense",
        "spending",
        "premium",
        "tax",
        "mortgage",
        "debt",
        "liability",
      ])
    )
      directional =
        "Higher values generally reduce free cash flow, terminal net worth, and probability of success; lower values generally improve them, unless the reduction removes needed protection.";
    else if (
      hasAny(l, [
        "income",
        "salary",
        "benefit",
        "asset",
        "balance",
        "value",
        "contribution",
      ])
    )
      directional =
        "Higher values generally improve cash flow or net worth, though they may also increase taxes, IRMAA exposure, or concentration risk depending on the field.";
  } else if (kind === "percent") {
    directional =
      "Higher percentages magnify the related assumption. Higher return or contribution rates may improve TNW, while higher inflation, tax, volatility, spending growth, or premium growth usually hurts success and/or lifetime taxes.";
  } else if (
    /boolean/i.test(String(row.schema?.type || "")) ||
    /yes\/no/i.test(String(row.units || ""))
  ) {
    directional =
      "Changing No to Yes usually activates this assumption in the build; changing Yes to No usually removes it. Review the affected report section after rebuilding.";
  }
  if (!directional)
    directional =
      "Changing this value can affect cash flow, terminal net worth, lifetime taxes, interim liquidity, risk metrics, recommendations, or workbook narratives depending on how the field is used.";
  return [base, directional, consider].filter(Boolean).join(" ");
}
// #250: autoCollapseHelpForNarrowLaptop() (U1) hides the help pane at typical
// laptop widths (1181-1499px) to avoid horizontal overflow. showFieldHelp
// only wrote into #helpPanel's innerHTML, so clicking a field -- or the "i"
// tooltip icon whose title text literally promises "Click for the full
// explanation" -- silently updated hidden content: nothing visibly happened.
// Every writer of #helpPanel must reveal it, not just fill it.


async function fetchWithTimeout(url, opts = {}, timeoutMs = 1200) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...opts, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}
let appCheckPromise = null;
function checkAppStatus(show = false) {
  // A concurrent caller must await the SAME in-flight check rather than
  // bailing out with whatever appReady happened to be at that instant --
  // returning the stale flag here starved every api() call made during the
  // brief window before the very first ping resolves (e.g. loadCanonicalGlossary's
  // api("/api/glossary") kicks off the first checkAppStatus(false); the explicit
  // startup checkAppStatus(true) two lines later, and everything chained off
  // it -- build/status, refreshLocalBackupStatus, prefs/autoload -- used to
  // see appCheckInFlight already true and each immediately throw "Application
  // is not available" instead of waiting the ~tens of ms for the real ping).
  if (appCheckPromise) return appCheckPromise;
  appCheckPromise = _checkAppStatusRun(show).finally(function () {
    appCheckPromise = null;
  });
  return appCheckPromise;
}
async function _checkAppStatusRun(show) {
  const wasOnline = appReady;
  if (!show && (detailedResultsLoading || detailedResultSheetLoading)) {
    const busy = document.getElementById("appStatus");
    if (busy && appReady) {
      busy.className = "status ok";
      busy.textContent = "Ready";
    }
    return appReady;
  }
  const s = document.getElementById("appStatus");
  if (s && show && !appReady) {
    s.className = "status";
    s.textContent = "Starting...";
  }
  const bases = [apiBase || "", "http://127.0.0.1:5050"].filter(
    (v, i, a) => a.indexOf(v) === i,
  );
  for (const b of bases) {
    try {
      const res = await fetchWithTimeout(
        b + "/api/ping",
        { cache: "no-store" },
        2500,
      );
      if (res && res.ok) {
        apiBase = b;
        window.__retirementApiBase = b;
        if (window.RetirementApiClient) window.RetirementApiClient.setBase(b);
        appReady = true;
        const ok = document.getElementById("appStatus");
        if (ok) {
          ok.className = "status ok";
          ok.textContent = "Ready";
        }
        setAppControls(true);
        if (wasOnline !== true) {
          try {
            renderSteps();
          } catch (_e) {}
        }
        if (show) showMessage("Application is ready.");
        return true;
      }
    } catch (e) {}
  }
  appReady = false;
  const el = document.getElementById("appStatus");
  if (el) {
    el.className = "status bad";
    el.textContent = "Unavailable";
  }
  setAppControls(false);
  if (wasOnline !== false) {
    try {
      renderSteps();
    } catch (_e) {}
  }
  if (show)
    showMessage("Application is not available. Try restarting.", "error");
  return false;
}


function normalizeValueForSave(row, value) {
  return saveValueForRow(row, value);
}

async function saveChanges(sync = true) {
  if (dirty.size) {
    const sent = [...dirty.entries()].map(([idx, value]) => ({ idx, value }));
    const out = await api("/api/config/rows", {
      method: "POST",
      body: JSON.stringify({ updates: updates(), sync }),
    });
    sent.forEach(({ idx, value }) => {
      const row = rows.find((r) => r.row_index === idx);
      if (row) row.value = saveValueForRow(row, value);
    });
    dirty.clear();
    if (window.RetirementAppStore)
      window.RetirementAppStore.markDirty(unsavedChangeCount());
    return out;
  }
  return { updated: 0 };
}

function downloadBlob(name, text) {
  const blob = new Blob([text], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name || "plan_data.csv";
  document.body.appendChild(a);
  a.click();
  setTimeout(() => {
    URL.revokeObjectURL(url);
    a.remove();
  }, 500);
}

function showPlanDataFileManifest(title, names) {
  showMessage(title || "CSV adapter folder selected.");
  activeStep = planLoaded ? "review" : "start";
  renderMain();
}

async function saveYtdPending() {
  var _anyChanged = false;
  if (ytdTransactionsChanged) {
    await api("/api/ytd/transactions/bulk", {
      method: "PUT",
      body: JSON.stringify({
        transactions: (ytdData && ytdData.transactions) || [],
      }),
    });
    ytdTransactionsChanged = false;
    _anyChanged = true;
  }
  if (ytdAccountsChanged) {
    await api("/api/ytd/account-setup", {
      method: "POST",
      body: JSON.stringify({
        accounts: (ytdData && ytdData.account_setup) || [],
      }),
    });
    ytdAccountsChanged = false;
    _anyChanged = true;
  }
  if (_anyChanged) spendingData = null;
  return { updated: 0 };
}


async function buildWithDesktopProgress(buildBody) {
  const started = await api("/api/build/start", {
    method: "POST",
    body: JSON.stringify(buildBody),
  });
  if (!started || !started.job_id)
    throw new Error("Build progress endpoint did not return a job id.");
  const initPct = Math.max(0, Number(started.progress) || 0);
  updateBuildOverlay(
    started.phase || "Preparing build",
    "Build started.",
    initPct,
  );
  startSmoothProgress(initPct, 82, 22, 5000);
  return new Promise(function (resolve, reject) {
    window.__desktopBuildResolve = function (result) {
      stopSmoothProgress();
      resolve(result);
    };
    window.__desktopBuildReject = function (err) {
      stopSmoothProgress();
      reject(err);
    };
    window.__desktopBuildTimeout = setTimeout(
      function () {
        stopSmoothProgress();
        window.__desktopBuildResolve = null;
        window.__desktopBuildReject = null;
        reject(new Error("Build progress timed out after about 40 minutes."));
      },
      40 * 60 * 1000,
    );
  });
}

function downloadFile(url) {
  if (!lastBuildOk) {
    showMessage(
      "Download is available after a successful build in this session. Click Build Reports first.",
      "error",
    );
    return;
  }
  if (window.__is_desktop_app__) {
    fetch(apiUrl(url)).catch(function (e) {
      showMessage("Download error: " + e.message, "error");
    });
    return;
  }
  window.location.href = apiUrl(url);
}

function openExitModal() {
  document.getElementById("exitModal").style.display = "flex";
}
function closeExitModal() {
  document.getElementById("exitModal").style.display = "none";
}

async function exitApp() {
  if (unsavedChangeCount()) {
    openExitModal();
    return;
  }
  await shutdownAndClose();
}
async function saveAndExit() {
  try {
    const ok = await saveAll(true);
    if (!ok) return;
    await api("/api/plan/exit-snapshot", {
      method: "POST",
      body: JSON.stringify({}),
    });
    closeExitModal();
    await shutdownAndClose();
  } catch (e) {
    showMessage("Error saving before exit: " + e.message, "error");
  }
}
async function discardAndExit() {
  dirty.clear();
  window.holdingsChanged = false;
  travelExtrasChanged = false;
  liquidityChanged = false;
  forcedConversionsChanged = false;
  ytdTransactionsChanged = false;
  ytdAccountsChanged = false;
  closeExitModal();
  await shutdownAndClose();
}

function focusableEntries() {
  return window.RetirementNavigation.focusableEntries();
}
function openNextCollapsedSectionFrom(el) {
  const details = el.closest("details");
  if (!details) return;
  const visible = Array.from(
    details.querySelectorAll("input,select,textarea,button"),
  ).filter(
    (x) =>
      !x.classList.contains("helpbtn") &&
      !x.disabled &&
      x.offsetParent !== null,
  );
  if (visible[visible.length - 1] !== el) return;
  let n = details.nextElementSibling;
  while (n) {
    if (n.tagName && n.tagName.toLowerCase() === "details" && !n.open) {
      n.open = true;
      return;
    }
    n = n.nextElementSibling;
  }
}
function moveToNextEntry(e) {
  const el = e.target;
  if (!el.matches("input,select,button,textarea")) return;
  if (el.classList.contains("helpbtn")) return;
  // Workbook Formatting's width fields have their own dedicated Tab handler
  // (wfWidthInputKeydown) that jumps specifically between width inputs,
  // opening only the Sheet/Table sections in that path. Leaving this generic
  // handler active too would race it via this function's deferred setTimeout
  // focus-move, sometimes stealing focus to an unrelated element.
  if (el.closest(".wf-col-width")) return;
  if (e.key === "Enter" && el.tagName.toLowerCase() === "textarea") return;
  if (e.key === "Enter" || (e.key === "Tab" && !e.shiftKey)) {
    e.preventDefault();
    openNextCollapsedSectionFrom(el);
    setTimeout(() => {
      const f = focusableEntries();
      let i = f.indexOf(el);
      if (i < 0) i = 0;
      const next = f[Math.min(f.length - 1, i + 1)];
      if (next) {
        next.focus();
        if (next.select && next.tagName.toLowerCase() === "input")
          next.select();
      }
    }, 0);
  }
}
document.addEventListener("keydown", moveToNextEntry, true);

window.addEventListener("beforeunload", function (e) {
  if (appExiting) return;
  if (unsavedChangeCount()) {
    e.preventDefault();
    e.returnValue = "You have unsaved changes. Save before leaving.";
    return e.returnValue;
  }
});

function loadCanonicalGlossary() {
  // Single source of truth (system review 2026-07-21, D3): src/glossary.py
  // is also what the workbook's Glossary sheet renders from. ACRONYM_DEFINITIONS
  // stays as a local fallback for the brief window before this resolves (or if
  // it fails) -- merging the fetched terms over it, rather than replacing it,
  // means a fetch failure degrades to the previously-shipped definitions
  // instead of blanking help panels.
  return api("/api/glossary")
    .then(function (r) {
      if (r && r.success && r.terms) Object.assign(ACRONYM_DEFINITIONS, r.terms);
    })
    .catch(function () {});
}

// Deferred via queueMicrotask, not called inline: this file's own bottom-of-
// file window bridge (below) hasn't run yet at this point in top-level
// evaluation, and wireStepNavigation() calls into dashboard_decomp_row_
// model.js's navigationContext(), which reads window.renderMain (this
// file's renderMain is a reassignable `let`, so cross-module code cannot
// see it directly -- only via the bridge's get/set pair). The codemod that
// generates that bridge always appends it at the literal end of the file
// (tools/js_codemod/convert_dashboard.mjs), so this can't be fixed by
// reordering text -- a microtask is the only ordering that survives
// regeneration regardless of where in the file this call sits.
queueMicrotask(function () {
wireStepNavigation();
restoreWorkbookViewState();
loadCanonicalGlossary();
// Restore lastBuildOk if build artifacts are current
checkAppStatus(true).then(function (ok) {
  api("/api/build/status")
    .then(function (r) {
      if (r) {
        buildPreflight = r;
        if (r.current) {
          lastBuildOk = true;
        }
        updatePlanStateBanner();
        renderMain();
      }
    })
    .catch(function () {});
  refreshLocalBackupStatus(true).catch(function () {});
  api("/api/prefs")
    .then(function (p) {
      var fromServer =
        p && p.prefs && typeof p.prefs.rpAutoLoad !== "undefined"
          ? !!p.prefs.rpAutoLoad
          : null;
      var fromLocal = null;
      try {
        var v = localStorage.getItem("rpAutoLoad");
        if (v !== null) fromLocal = v === "1";
      } catch (_e) {}
      var autoLoad =
        fromServer !== null
          ? fromServer
          : fromLocal !== null
            ? fromLocal
            : false;
      _autoLoadPref = autoLoad;
      if (autoLoad) {
        loadAll({ source: "Local database", preferLocal: false });
      } else {
        renderMain();
      }
    })
    .catch(function () {
      var autoLoad = false;
      try {
        autoLoad = localStorage.getItem("rpAutoLoad") === "1";
      } catch (_e) {}
      _autoLoadPref = autoLoad || false;
      if (autoLoad) {
        loadAll({ source: "Local database", preferLocal: false });
      } else {
        renderMain();
      }
    });
}).catch(function (e) {
  console.error("startup chain failed", e);
  renderMain();
});
setInterval(function () {
  checkAppStatus(false);
}, 15000);
});

// AUTO-GENERATED by tools/js_codemod/convert_dashboard.mjs
// Regenerate: node tools/js_codemod/census.mjs && node tools/js_codemod/convert_dashboard.mjs
// get+set accessors: reassigned functions (monkey-patch decorator chains) and
// externally read/written state variables. Object.assign below: every other
// top-level function, safe as a one-time value copy since it's never reassigned.
// Deliberately NO `export` statement anywhere in this file: nothing today
// does `import {x} from './dashboard.js'`, and several tests eval() the
// whole file (or a large slice of it) as a plain non-module script to
// smoke-test its runtime behavior -- any `export` keyword anywhere is a
// SyntaxError in that context. type="module" on the script tag alone (not
// any export statement) is what makes this file's top-level bindings
// private; the bridge below is the entire backward-compat mechanism.
Object.defineProperty(window, "BUILD_HISTORY_LS_KEY", { get: () => BUILD_HISTORY_LS_KEY, configurable: true });
Object.defineProperty(window, "BUILD_HISTORY_MAX", { get: () => BUILD_HISTORY_MAX, configurable: true });
Object.defineProperty(window, "BUILD_IMPACT_SOURCE_STEP_IDS", { get: () => BUILD_IMPACT_SOURCE_STEP_IDS, configurable: true });
Object.defineProperty(window, "DEFAULT_TRAVEL_TYPES", { get: () => DEFAULT_TRAVEL_TYPES, configurable: true });
Object.defineProperty(window, "FIELD_GUIDANCE_OVERRIDES", { get: () => FIELD_GUIDANCE_OVERRIDES, configurable: true });
Object.defineProperty(window, "IRMAA_OFF_MODES", { get: () => IRMAA_OFF_MODES, configurable: true });
Object.defineProperty(window, "LARGE_DISC_CATEGORY_IDS", { get: () => LARGE_DISC_CATEGORY_IDS, configurable: true });
Object.defineProperty(window, "LARGE_DISC_TYPES", { get: () => LARGE_DISC_TYPES, configurable: true });
Object.defineProperty(window, "LIABILITY_HEADER", { get: () => LIABILITY_HEADER, configurable: true });
Object.defineProperty(window, "PERSON_VALUE_TOKEN_RE", { get: () => PERSON_VALUE_TOKEN_RE, configurable: true });
Object.defineProperty(window, "PLAN_DATA_FILES", { get: () => PLAN_DATA_FILES, configurable: true });
Object.defineProperty(window, "PROTECTED_CLIENT_DATA_KEYS", { get: () => PROTECTED_CLIENT_DATA_KEYS, configurable: true });
Object.defineProperty(window, "RECOMMENDATION_ENGINE_VERSION", { get: () => RECOMMENDATION_ENGINE_VERSION, configurable: true });
Object.defineProperty(window, "RECOMMENDATION_STEP_IDS", { get: () => RECOMMENDATION_STEP_IDS, configurable: true });
Object.defineProperty(window, "REPORTS_TABS", { get: () => REPORTS_TABS, configurable: true });
Object.defineProperty(window, "REQUIRED_PLAN_DATA_FILES", { get: () => REQUIRED_PLAN_DATA_FILES, configurable: true });
Object.defineProperty(window, "ROTH_LEGACY_LABELS", { get: () => ROTH_LEGACY_LABELS, configurable: true });
Object.defineProperty(window, "ROTH_WINDOW_LABELS", { get: () => ROTH_WINDOW_LABELS, configurable: true });
Object.defineProperty(window, "SCENARIO_SET_STORAGE_KEY", { get: () => SCENARIO_SET_STORAGE_KEY, configurable: true });
Object.defineProperty(window, "STEPS", { get: () => STEPS, configurable: true });
Object.defineProperty(window, "STEP_HELP", { get: () => STEP_HELP, configurable: true });
Object.defineProperty(window, "STRATEGY_TABS", { get: () => STRATEGY_TABS, configurable: true });
Object.defineProperty(window, "SYSTEM_CONFIG_FIELD_HELP", { get: () => SYSTEM_CONFIG_FIELD_HELP, configurable: true });
Object.defineProperty(window, "YTD_ACTUALS_PERIOD_LS_KEY", { get: () => YTD_ACTUALS_PERIOD_LS_KEY, configurable: true });
Object.defineProperty(window, "YTD_TX_PAGE_SIZE", { get: () => YTD_TX_PAGE_SIZE, configurable: true });
Object.defineProperty(window, "_autoLoadPref", { get: () => _autoLoadPref, set: (v) => { _autoLoadPref = v; }, configurable: true });
Object.defineProperty(window, "_smoothCap", { get: () => _smoothCap, set: (v) => { _smoothCap = v; }, configurable: true });
Object.defineProperty(window, "_smoothDelayTimer", { get: () => _smoothDelayTimer, set: (v) => { _smoothDelayTimer = v; }, configurable: true });
Object.defineProperty(window, "_smoothFromPct", { get: () => _smoothFromPct, set: (v) => { _smoothFromPct = v; }, configurable: true });
Object.defineProperty(window, "_smoothIntervalTimer", { get: () => _smoothIntervalTimer, set: (v) => { _smoothIntervalTimer = v; }, configurable: true });
Object.defineProperty(window, "_smoothSpeed", { get: () => _smoothSpeed, set: (v) => { _smoothSpeed = v; }, configurable: true });
Object.defineProperty(window, "_smoothStart", { get: () => _smoothStart, set: (v) => { _smoothStart = v; }, configurable: true });
Object.defineProperty(window, "activeDetailedSheet", { get: () => activeDetailedSheet, set: (v) => { activeDetailedSheet = v; }, configurable: true });
Object.defineProperty(window, "activePlanReportSection", { get: () => activePlanReportSection, set: (v) => { activePlanReportSection = v; }, configurable: true });
Object.defineProperty(window, "activeStep", { get: () => activeStep, set: (v) => { activeStep = v; }, configurable: true });
Object.defineProperty(window, "allocationPreview", { get: () => allocationPreview, set: (v) => { allocationPreview = v; }, configurable: true });
Object.defineProperty(window, "allocationPreviewError", { get: () => allocationPreviewError, set: (v) => { allocationPreviewError = v; }, configurable: true });
Object.defineProperty(window, "allocationPreviewKey", { get: () => allocationPreviewKey, set: (v) => { allocationPreviewKey = v; }, configurable: true });
Object.defineProperty(window, "allocationPreviewLoading", { get: () => allocationPreviewLoading, set: (v) => { allocationPreviewLoading = v; }, configurable: true });
Object.defineProperty(window, "allocationPreviewSeq", { get: () => allocationPreviewSeq, set: (v) => { allocationPreviewSeq = v; }, configurable: true });
Object.defineProperty(window, "apiBase", { get: () => apiBase, set: (v) => { apiBase = v; }, configurable: true });
Object.defineProperty(window, "appExiting", { get: () => appExiting, set: (v) => { appExiting = v; }, configurable: true });
Object.defineProperty(window, "appReady", { get: () => appReady, set: (v) => { appReady = v; }, configurable: true });
Object.defineProperty(window, "budgetLines", { get: () => budgetLines, set: (v) => { budgetLines = v; }, configurable: true });
Object.defineProperty(window, "budgetLinesChanged", { get: () => budgetLinesChanged, set: (v) => { budgetLinesChanged = v; }, configurable: true });
Object.defineProperty(window, "budgetLinesLoaded", { get: () => budgetLinesLoaded, set: (v) => { budgetLinesLoaded = v; }, configurable: true });
Object.defineProperty(window, "budgetSectionMode", { get: () => budgetSectionMode, set: (v) => { budgetSectionMode = v; }, configurable: true });
Object.defineProperty(window, "buildHistory", { get: () => buildHistory, set: (v) => { buildHistory = v; }, configurable: true });
Object.defineProperty(window, "buildOverlayDepth", { get: () => buildOverlayDepth, set: (v) => { buildOverlayDepth = v; }, configurable: true });
Object.defineProperty(window, "buildOverlayLastPct", { get: () => buildOverlayLastPct, set: (v) => { buildOverlayLastPct = v; }, configurable: true });
Object.defineProperty(window, "buildOverlayLastTitle", { get: () => buildOverlayLastTitle, set: (v) => { buildOverlayLastTitle = v; }, configurable: true });
Object.defineProperty(window, "buildOverlayStartedAt", { get: () => buildOverlayStartedAt, set: (v) => { buildOverlayStartedAt = v; }, configurable: true });
Object.defineProperty(window, "buildOverlayTimer", { get: () => buildOverlayTimer, set: (v) => { buildOverlayTimer = v; }, configurable: true });
Object.defineProperty(window, "buildPreflight", { get: () => buildPreflight, set: (v) => { buildPreflight = v; }, configurable: true });
Object.defineProperty(window, "buildProgressTicker", { get: () => buildProgressTicker, set: (v) => { buildProgressTicker = v; }, configurable: true });
Object.defineProperty(window, "categoryBudgetMode", { get: () => categoryBudgetMode, set: (v) => { categoryBudgetMode = v; }, configurable: true });
Object.defineProperty(window, "chartCache", { get: () => chartCache, set: (v) => { chartCache = v; }, configurable: true });
Object.defineProperty(window, "chartCacheSeq", { get: () => chartCacheSeq, set: (v) => { chartCacheSeq = v; }, configurable: true });
Object.defineProperty(window, "csrfToken", { get: () => csrfToken, set: (v) => { csrfToken = v; }, configurable: true });
Object.defineProperty(window, "demoModeActive", { get: () => demoModeActive, set: (v) => { demoModeActive = v; }, configurable: true });
Object.defineProperty(window, "detailResultsSearchText", { get: () => detailResultsSearchText, set: (v) => { detailResultsSearchText = v; }, configurable: true });
Object.defineProperty(window, "detailedColumnGroupsOpen", { get: () => detailedColumnGroupsOpen, set: (v) => { detailedColumnGroupsOpen = v; }, configurable: true });
Object.defineProperty(window, "detailedResultSheetError", { get: () => detailedResultSheetError, set: (v) => { detailedResultSheetError = v; }, configurable: true });
Object.defineProperty(window, "detailedResultSheetInFlight", { get: () => detailedResultSheetInFlight, set: (v) => { detailedResultSheetInFlight = v; }, configurable: true });
Object.defineProperty(window, "detailedResultSheetLoading", { get: () => detailedResultSheetLoading, set: (v) => { detailedResultSheetLoading = v; }, configurable: true });
Object.defineProperty(window, "detailedResultSheetLoadingName", { get: () => detailedResultSheetLoadingName, set: (v) => { detailedResultSheetLoadingName = v; }, configurable: true });
Object.defineProperty(window, "detailedResultSheetSeq", { get: () => detailedResultSheetSeq, set: (v) => { detailedResultSheetSeq = v; }, configurable: true });
Object.defineProperty(window, "detailedResultSheets", { get: () => detailedResultSheets, set: (v) => { detailedResultSheets = v; }, configurable: true });
Object.defineProperty(window, "detailedResultsData", { get: () => detailedResultsData, set: (v) => { detailedResultsData = v; }, configurable: true });
Object.defineProperty(window, "detailedResultsError", { get: () => detailedResultsError, set: (v) => { detailedResultsError = v; }, configurable: true });
Object.defineProperty(window, "detailedResultsLoading", { get: () => detailedResultsLoading, set: (v) => { detailedResultsLoading = v; }, configurable: true });
Object.defineProperty(window, "detailedResultsNavOpen", { get: () => detailedResultsNavOpen, set: (v) => { detailedResultsNavOpen = v; }, configurable: true });
Object.defineProperty(window, "detailedResultsProgress", { get: () => detailedResultsProgress, set: (v) => { detailedResultsProgress = v; }, configurable: true });
Object.defineProperty(window, "dirty", { get: () => dirty, set: (v) => { dirty = v; }, configurable: true });
Object.defineProperty(window, "estateStateOptions", { get: () => estateStateOptions, set: (v) => { estateStateOptions = v; }, configurable: true });
Object.defineProperty(window, "forcedConversionAccounts", { get: () => forcedConversionAccounts, set: (v) => { forcedConversionAccounts = v; }, configurable: true });
Object.defineProperty(window, "forcedConversions", { get: () => forcedConversions, set: (v) => { forcedConversions = v; }, configurable: true });
Object.defineProperty(window, "forcedConversionsChanged", { get: () => forcedConversionsChanged, set: (v) => { forcedConversionsChanged = v; }, configurable: true });
Object.defineProperty(window, "groupBudgetMode", { get: () => groupBudgetMode, set: (v) => { groupBudgetMode = v; }, configurable: true });
Object.defineProperty(window, "homeSaleSplitAccounts", { get: () => homeSaleSplitAccounts, set: (v) => { homeSaleSplitAccounts = v; }, configurable: true });
Object.defineProperty(window, "homeSaleSplits", { get: () => homeSaleSplits, set: (v) => { homeSaleSplits = v; }, configurable: true });
Object.defineProperty(window, "homeSaleSplitsChanged", { get: () => homeSaleSplitsChanged, set: (v) => { homeSaleSplitsChanged = v; }, configurable: true });
Object.defineProperty(window, "inactiveEditReveals", { get: () => inactiveEditReveals, set: (v) => { inactiveEditReveals = v; }, configurable: true });
Object.defineProperty(window, "lastBuildCompare", { get: () => lastBuildCompare, set: (v) => { lastBuildCompare = v; }, configurable: true });
Object.defineProperty(window, "lastBuildOk", { get: () => lastBuildOk, set: (v) => { lastBuildOk = v; }, configurable: true });
Object.defineProperty(window, "lastBuildSummary", { get: () => lastBuildSummary, set: (v) => { lastBuildSummary = v; }, configurable: true });
Object.defineProperty(window, "liabilitiesChanged", { get: () => liabilitiesChanged, set: (v) => { liabilitiesChanged = v; }, configurable: true });
Object.defineProperty(window, "liabilitiesText", { get: () => liabilitiesText, set: (v) => { liabilitiesText = v; }, configurable: true });
Object.defineProperty(window, "liabilityRowsCache", { get: () => liabilityRowsCache, set: (v) => { liabilityRowsCache = v; }, configurable: true });
Object.defineProperty(window, "liquidityBuffers", { get: () => liquidityBuffers, set: (v) => { liquidityBuffers = v; }, configurable: true });
Object.defineProperty(window, "liquidityChanged", { get: () => liquidityChanged, set: (v) => { liquidityChanged = v; }, configurable: true });
Object.defineProperty(window, "mappingRules", { get: () => mappingRules, set: (v) => { mappingRules = v; }, configurable: true });
Object.defineProperty(window, "moduleGates", { get: () => moduleGates, set: (v) => { moduleGates = v; }, configurable: true });
Object.defineProperty(window, "moduleStatus", { get: () => moduleStatus, set: (v) => { moduleStatus = v; }, configurable: true });
Object.defineProperty(window, "navSearchText", { get: () => navSearchText, set: (v) => { navSearchText = v; }, configurable: true });
Object.defineProperty(window, "planChatMessages", { get: () => planChatMessages, set: (v) => { planChatMessages = v; }, configurable: true });
Object.defineProperty(window, "planFolderHandle", { get: () => planFolderHandle, set: (v) => { planFolderHandle = v; }, configurable: true });
Object.defineProperty(window, "planFolderName", { get: () => planFolderName, set: (v) => { planFolderName = v; }, configurable: true });
Object.defineProperty(window, "planLoaded", { get: () => planLoaded, set: (v) => { planLoaded = v; }, configurable: true });
Object.defineProperty(window, "planSource", { get: () => planSource, set: (v) => { planSource = v; }, configurable: true });
Object.defineProperty(window, "planningLeverInputs", { get: () => planningLeverInputs, set: (v) => { planningLeverInputs = v; }, configurable: true });
Object.defineProperty(window, "renderMain", { get: () => renderMain, set: (v) => { renderMain = v; }, configurable: true });
Object.defineProperty(window, "reportsActiveTab", { get: () => reportsActiveTab, set: (v) => { reportsActiveTab = v; }, configurable: true });
Object.defineProperty(window, "residencySchedule", { get: () => residencySchedule, set: (v) => { residencySchedule = v; }, configurable: true });
Object.defineProperty(window, "residencyScheduleChanged", { get: () => residencyScheduleChanged, set: (v) => { residencyScheduleChanged = v; }, configurable: true });
Object.defineProperty(window, "rows", { get: () => rows, set: (v) => { rows = v; }, configurable: true });
Object.defineProperty(window, "rulesChanged", { get: () => rulesChanged, set: (v) => { rulesChanged = v; }, configurable: true });
Object.defineProperty(window, "runtime", { get: () => runtime, set: (v) => { runtime = v; }, configurable: true });
Object.defineProperty(window, "searchScope", { get: () => searchScope, set: (v) => { searchScope = v; }, configurable: true });
Object.defineProperty(window, "searchText", { get: () => searchText, set: (v) => { searchText = v; }, configurable: true });
Object.defineProperty(window, "sessionBaselineCaptured", { get: () => sessionBaselineCaptured, set: (v) => { sessionBaselineCaptured = v; }, configurable: true });
Object.defineProperty(window, "sessionBaselineSummary", { get: () => sessionBaselineSummary, set: (v) => { sessionBaselineSummary = v; }, configurable: true });
Object.defineProperty(window, "sessionChanges", { get: () => sessionChanges, set: (v) => { sessionChanges = v; }, configurable: true });
Object.defineProperty(window, "sessionSpecialChanges", { get: () => sessionSpecialChanges, set: (v) => { sessionSpecialChanges = v; }, configurable: true });
Object.defineProperty(window, "showStepHelp", { get: () => showStepHelp, set: (v) => { showStepHelp = v; }, configurable: true });
Object.defineProperty(window, "spendingModelData", { get: () => spendingModelData, set: (v) => { spendingModelData = v; }, configurable: true });
Object.defineProperty(window, "spendingModelError", { get: () => spendingModelError, set: (v) => { spendingModelError = v; }, configurable: true });
Object.defineProperty(window, "spendingModelLoading", { get: () => spendingModelLoading, set: (v) => { spendingModelLoading = v; }, configurable: true });
Object.defineProperty(window, "statusTimer", { get: () => statusTimer, set: (v) => { statusTimer = v; }, configurable: true });
Object.defineProperty(window, "taxBudget", { get: () => taxBudget, set: (v) => { taxBudget = v; }, configurable: true });
Object.defineProperty(window, "taxBudgetChanged", { get: () => taxBudgetChanged, set: (v) => { taxBudgetChanged = v; }, configurable: true });
Object.defineProperty(window, "taxBudgetLoaded", { get: () => taxBudgetLoaded, set: (v) => { taxBudgetLoaded = v; }, configurable: true });
Object.defineProperty(window, "taxFreshnessData", { get: () => taxFreshnessData, set: (v) => { taxFreshnessData = v; }, configurable: true });
Object.defineProperty(window, "taxFreshnessLoading", { get: () => taxFreshnessLoading, set: (v) => { taxFreshnessLoading = v; }, configurable: true });
Object.defineProperty(window, "taxonomyData", { get: () => taxonomyData, set: (v) => { taxonomyData = v; }, configurable: true });
Object.defineProperty(window, "taxonomyError", { get: () => taxonomyError, set: (v) => { taxonomyError = v; }, configurable: true });
Object.defineProperty(window, "taxonomyFlat", { get: () => taxonomyFlat, set: (v) => { taxonomyFlat = v; }, configurable: true });
Object.defineProperty(window, "taxonomyLoading", { get: () => taxonomyLoading, set: (v) => { taxonomyLoading = v; }, configurable: true });
Object.defineProperty(window, "travelExtras", { get: () => travelExtras, set: (v) => { travelExtras = v; }, configurable: true });
Object.defineProperty(window, "travelExtrasChanged", { get: () => travelExtrasChanged, set: (v) => { travelExtrasChanged = v; }, configurable: true });
Object.defineProperty(window, "travelTypes", { get: () => travelTypes, set: (v) => { travelTypes = v; }, configurable: true });
Object.defineProperty(window, "ytdAccountFilter", { get: () => ytdAccountFilter, set: (v) => { ytdAccountFilter = v; }, configurable: true });
Object.defineProperty(window, "ytdAccountsChanged", { get: () => ytdAccountsChanged, set: (v) => { ytdAccountsChanged = v; }, configurable: true });
Object.defineProperty(window, "ytdActualsPeriod", { get: () => ytdActualsPeriod, set: (v) => { ytdActualsPeriod = v; }, configurable: true });
Object.defineProperty(window, "ytdCategoryFilter", { get: () => ytdCategoryFilter, set: (v) => { ytdCategoryFilter = v; }, configurable: true });
Object.defineProperty(window, "ytdData", { get: () => ytdData, set: (v) => { ytdData = v; }, configurable: true });
Object.defineProperty(window, "ytdDuplicateGroups", { get: () => ytdDuplicateGroups, set: (v) => { ytdDuplicateGroups = v; }, configurable: true });
Object.defineProperty(window, "ytdDuplicateSelected", { get: () => ytdDuplicateSelected, set: (v) => { ytdDuplicateSelected = v; }, configurable: true });
Object.defineProperty(window, "ytdTransactionsChanged", { get: () => ytdTransactionsChanged, set: (v) => { ytdTransactionsChanged = v; }, configurable: true });
Object.defineProperty(window, "ytdTxColsCollapsed", { get: () => ytdTxColsCollapsed, set: (v) => { ytdTxColsCollapsed = v; }, configurable: true });
Object.defineProperty(window, "ytdTxPage", { get: () => ytdTxPage, set: (v) => { ytdTxPage = v; }, configurable: true });
Object.defineProperty(window, "ytdTxSearch", { get: () => ytdTxSearch, set: (v) => { ytdTxSearch = v; }, configurable: true });
Object.defineProperty(window, "ytdTxSort", { get: () => ytdTxSort, set: (v) => { ytdTxSort = v; }, configurable: true });
Object.assign(window, {
  _checkAppStatusRun, addManualYtdAccount, addParentheticals, allocationPreviewFingerprint,
  allocationPreviewRowsForPost, allocationTargetsValid, artifactHashFromPreflight,
  assetActionForSubsection, autoCollapseHelpForNarrowLaptop, baseHomeSaleYearRow,
  blurYtdAccountMoney, boolishValue, buildWithDesktopProgress, catEffectiveBudget, changeImpactScope,
  changeKey, chatMessageHtml, checkAppStatus, choiceHelpText, choiceLabel, choiceOptions,
  chooseDefaultDetailedSheet, cloneSummary, closeChartModal, closeExitModal, closeNavDrawer,
  collapseAllDetailGroups, currentManualOverrideItems, currentScenarioOverrideItems,
  decimalsFromText, deleteYtdAccount, dependencyRank, deriveTotalRothConversions,
  detailProgressState, detailedProgressHtml, detailedSheetByName, discardAndExit, dismissMessage,
  domainBudgetNote, downloadBlob, downloadFile, exitApp, expandAllDetailColumnsOnPage,
  expandAllDetailGroups, fetchWithTimeout, fieldAllowedValues, fieldConnection, fieldDefaultMeaning,
  fieldFinderCategoryName, fieldFinderCategoryOrder, fieldLabelNoteHtml, fieldLikelyImpact,
  fieldSizeClass, fieldTooltipHtml, fieldTooltipPreview, filterChoiceOptionsForRow, finiteOrNull,
  focusYtdAccountMoney, focusableEntries, getStrategyTab, groupModelData, helpList,
  hideSpendingModelLoadOverlay, hideUnusedTemplateCategories, hideYtdLoadOverlay, humanizeGroupKey,
  leverPctPoints, loadCanonicalGlossary, loadDetailedResults, makeYtdAccountRow,
  mergeDetailedSheetMeta, moneyNegativeClass, moveToNextEntry, normalizePlanningCaseRunType,
  normalizePlanningCaseSource, normalizeValueForSave, noteSessionFieldChange,
  noteSpecialSessionChange, numberDisplayDecimals, openExitModal, openNavDrawer,
  openNextCollapsedSectionFrom, optionalModuleState, pageHelp, pageSaveMode, pageSaveModeHtml,
  pageStatusHtml, parseCsvLine, parseDollarLike, percentDisplayDecimals, percentRaw, personCellInput,
  personNickPlaceholder, personTokenLabel, planningCaseActiveId, planningCaseAdopt,
  planningCaseArchive, planningCaseBaseSnapshotId, planningCaseCardsHtml, planningCaseCreate,
  planningCaseDelete, planningCaseId, planningCaseMatrixHtml, planningCaseMetricSummary,
  planningCaseNowIso, planningCaseOverrideFromRow, planningCaseOverrideTable,
  planningCaseOverridesForSource, planningCaseReadAll, planningCaseSaveAll,
  planningCaseSourceButtons, planningWorkbenchBuildImpactHtml, planningWorkbenchStressSelectorHtml,
  primaryActionForStep, promotePlanningCase, recoverPriorSpendingBudget, recoverYtdAccountSetup,
  rememberBuildCompare, renderAssetsCashReserves, renderDetailedResultsNav,
  renderDetailedResultsProgressTick, renderEntityCharitable, renderEstateWithAnnuityLink,
  renderFieldFinderGroups, renderHouseholdPeople, renderIncomeWork, renderMeta, renderNav,
  renderOptionalFunctions, renderPlanningWorkbench, renderRetirementWellness,
  renderSpecialStrategies, renderSpendingDashboardOrLoad, renderSpendingWorkflowBanner,
  renderStateResidency, renderStrategyTabs, renderWithdrawalOrderTable, renderWithdrawalStrategy,
  renderWorkspaceSubtabsNav, resetAllocationPreview, restoreGroupBudgetModes,
  restoreWorkbookViewState, revertLastBuildChanges, rollForwardYtdAccounts, rowConfigValue,
  rowIsRetirementWellness, rowSortKeyForIncomeWork, saveAndExit, saveChanges, saveValueForRow,
  saveYtdAccountSetup, saveYtdPending, scenarioRowKeyFromParts, sectionFlagEnabled,
  setAllDetailColumnGroups, setCombinedSearch, setDetailedResultSheet, setDetailedResultsNavOpen,
  setNavSearch, setPlanningCaseActive, setSearchScope, setStrategyTab,
  showHelpAutoCollapseNoticeOnce, showPlanDataFileManifest, showSpendingModelLoadOverlay,
  showYtdLoadOverlay, sleep, spendingFlowFooterHtml, startDetailedResultsProgress, stepHelpLinkHtml,
  stepIdForRow, stepSearchText, stopDetailedResultsProgress, strategyLeverOverrideItems,
  stressHomeSaleYearRow, stressOverrideItems, stripUiLabelPrefix, suggestedNext,
  summaryFromApiPayload, takeBuildSnapshot, toggleDetailColGroup, toggleDetailColumnGroup,
  toggleHelpSheet, toggleNavDrawer, translatePersonValueLabel, updateSearchToggle,
  updateYtdAccountMoney, validateAllocationTargetsOrMessage, wireStepNavigation, withdrawalOtherRows,
  yesNoOptionHelp, ytdAccountMoneyDisplay, ytdAccountRoleOptions, ytdInvestmentHoldingAccounts,
  ytdInvestmentOptions, ytdIsGrowthRole, ytdMappableAccounts, ytdRolloverBannerHtml,
  ytdStaleGrowthAccounts,
});
