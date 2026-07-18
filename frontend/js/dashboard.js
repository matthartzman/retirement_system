// v10 other asset display ordering: {'Note Receivable':0,'HSA':1,'DAF':2,'529 Plans':3}
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
const DASHBOARD_UTILS = window.RPDashboardUtils || {};
const APP_UNAVAILABLE_MESSAGE =
  "Application not ready. Saving, build, download, pricing refresh, Plan Chat, and CSV import/export utilities are unavailable";
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
    group: "Profile",
    title: "Household & People",
    desc: "Names, birth dates, state of residence, tax filing status, retirement dates, planning horizon, and survivor income and filing assumptions.",
    intro:
      "Birth dates determine ages for Social Security timing, required minimum distributions, Medicare eligibility, survivor horizon, and retirement period length. The retirement date ends earned income and starts the withdrawal period. Choose a conservative planning horizon — the projection runs through this age for both members.",
    help: "Filing status affects tax brackets across the entire projection — changing it after plan entry can materially shift lifetime taxes and survivor results. Survivor assumptions drive the Survivor stress report and also appear there for review before a rebuild.",
  },
  {
    id: "income_work",
    group: "Profile",
    title: "Work Income",
    desc: "Salary or self-employment income, payroll assumptions, and retirement plan contributions while still working.",
    intro:
      "Contribution amounts here add to account balances annually until the retirement date. Business salary level affects payroll tax and business-income deductions.",
    help: "High earned income in late working years compresses Roth conversion room below the bracket ceiling — coordinate with the Roth Conversion page when the retirement date is near.",
  },
  {
    id: "income_retirement",
    group: "Profile",
    title: "Income & Social Security",
    desc: "Social Security claiming age and benefit for each person, plus pension amounts, annuity income, start ages, survivor percentages, and cost-of-living settings.",
    intro:
      "Enter each person’s Social Security benefit from their statement along with the planned claiming age and the household spousal/survivor policy. Delaying past full retirement age adds about 8% per year up to age 70; the higher earner’s delay has the greatest survivor income impact. Survivor percentages control how much pension or annuity income continues after the first death.",
    help: "Early claiming opens gap years for Roth conversion if other income is low — model the joint timing strategy with the Roth Conversion page. Pensions and annuities with survivor protection can be treated as fixed-income-equivalent coverage in the allocation analysis — set the coverage option on the Asset Allocation page.",
  },
  {
    id: "spending_core",
    group: "Spending",
    title: "Spending Model",
    desc: "Comprehensive income/expense category hierarchy, budget references, and projection spending controls.",
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
  },
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
  },
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
    title: "Special Income, Annuities & Insurance",
    desc: "Year-by-year carrier illustration values for annuities and special income, plus life insurance policies.",
    intro:
      "Enter values from each policy illustration; use 0 for years with no benefit. These totals appear in the Survivor and Estate report sections. Life insurance policy details — owner, insured, beneficiary, face amount, and premiums — are entered here as well.",
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
    desc: "Federal and state exemptions, trust structure, beneficiary needs, lifetime gifting, charitable intent, and non-life protection policies (disability, long-term care, umbrella, and property and casualty).",
    intro:
      "Estate tax exposure is estimated from current exemptions and projected asset values at each mortality date. Trust structure choices affect how assets pass to the survivor and to beneficiaries. Disability, long-term-care hybrid, umbrella, and property/casualty policies are also entered here; premiums flow into the cash-flow projection and benefit amounts appear in the Survivor and Long-Term Care Stress report sections.",
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
      "Use only when the plan intentionally includes home-equity borrowing, entity planning, or charitable giving strategies.",
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
    group: "Strategy",
    title: "Roth Conversion",
    desc: "Conversion policy, ceiling (bracket or fixed dollar), Medicare income surcharge guardrails, and objective weights for tax, legacy, survivor, and estate.",
    intro:
      "Choose the policy first — the page shows only controls relevant to that policy. Forced conversion rows run before the optimizer and reduce the space available for voluntary conversions.",
    help: "Medicare income surcharge guardrails prevent projected income from crossing premium tiers during conversion years. Bracket-fill policies convert up to a marginal rate ceiling determined by the filing status on Household People.",
    hidden: true,
  },
  {
    id: "allocation_assets",
    group: "Strategy",
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
    group: "Strategy",
    title: "Withdrawal sequencing",
    desc: "Bucket draw order, trust withdrawals, and spousal rollover election. HSA withdrawal timing is set on Other Assets and Liabilities.",
    intro:
      "Earlier priority means a bucket is drawn sooner. Drawing taxable accounts first can manage required distributions but may realize capital gains; preserving Roth typically maximizes tax-free compounding for legacy.",
    help: "When required distributions exceed annual spending needs, the excess is reinvested in taxable unless converted to Roth — Roth conversion policy is set on the Roth Conversion page. HSA timing controls are under Other Assets and Liabilities.",
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
    desc: "Entity election and charitable vehicle — direct gift, donor-advised fund, or qualified charitable distribution.",
    intro:
      "S-Corp election can reduce self-employment tax on business income above a reasonable salary. Qualified charitable distributions are available at age 70½ and satisfy required distributions tax-free. Annual giving amounts are set on Core spending.",
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
    desc: "Build and download the workbook and PDF — downloads automatically save first when there are pending changes.",
    intro:
      "A build saves all current inputs, runs the full projection engine (cash flow, taxes, RMDs, Monte Carlo, scenarios), and writes the workbook. The PDF is an advisor-ready formatted summary. Both are read-only snapshots — edit values here, then rebuild.",
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
function stepGatedByOptionalModule(stepId) {
  if (stepId === "divorce_options")
    return !optionalFunctionEnabled("divorce_qdro");
  if (stepId === "ltc_stress")
    return !optionalFunctionEnabled("long_term_care_stress");
  // Probability analysis (Monte Carlo), scenario change sets, and the survivor
  // stress test each map 1:1 to an optional workbook module. When the module is
  // off no computation runs and no sheet is built, so the input page is hidden.
  if (stepId === "monte_carlo_options")
    return !optionalFunctionEnabled("market_luck_stress_test");
  if (stepId === "scenarios")
    return !optionalFunctionEnabled("what_if_analysis");
  if (stepId === "survivor_stress")
    return !optionalFunctionEnabled("survivor_stress_test");
  // Single-module optimizer input pages.
  if (stepId === "state_residency")
    return !optionalFunctionEnabled("state_residency");
  if (stepId === "roth_conversion")
    return !optionalFunctionEnabled("roth_conversion_plan");
  if (stepId === "heloc_strategy") return !helocModuleEnabled();
  if (stepId === "entity_charitable")
    return !optionalFunctionEnabled("charitable_giving");
  // Special Strategies bundles the HELOC and Charitable Giving input pages, so
  // it only appears in navigation once at least one of those optional modules
  // is enabled. Visibility follows capability — there is no separate
  // "advanced workflow" preference.
  if (stepId === "special_strategies")
    return !helocModuleEnabled() && !optionalFunctionEnabled("charitable_giving");
  return false;
}
function visibleSteps() {
  const q = String(navSearchText || "")
    .trim()
    .toLowerCase();
  return STEPS.filter((s) => {
    if (stepGatedByOptionalModule(s.id) && s.id !== activeStep) return false;
    if (s.group === null && s.id !== activeStep) return false;
    if (s.hidden && s.id !== activeStep) return false;
    if (!q) return true;
    return stepSearchText(s).includes(q) || s.id === activeStep;
  });
}
const ACRONYMS = {
  js: "JS",
  dob: "DOB",
  rmd: "RMD",
  niit: "NIIT",
  ss: "SS",
  mfj: "MFJ",
  irmaa: "IRMAA",
  fmp: "FMP",
  api: "API",
  ltcg: "LTCG",
  pct: "PCT",
  hsa: "HSA",
  daf: "DAF",
  ltc: "LTC",
  qcd: "QCD",
  qbi: "QBI",
  w2: "W-2",
  s_corp: "S-Corp",
  sdi: "SDI",
  ssdi: "SSDI",
  ssi: "SSI",
  able: "ABLE",
  qtip: "QTIP",
  ira: "IRA",
  roth: "Roth",
  pv: "PV",
  agi: "AGI",
  magi: "MAGI",
  cpi: "CPI",
  cola: "COLA",
  etf: "ETF",
  reit: "REIT",
  reits: "REITs",
  tips: "TIPS",
  pdf: "PDF",
  csv: "CSV",
  yaml: "YAML",
  json: "JSON",
  sqlite: "SQLite",
  ui: "UI",
  mc: "Monte Carlo",
  oop: "OOP",
  sehi: "SEHI",
  pdia: "PDIA",
  pia: "PIA",
  fra: "FRA",
  iso: "ISO",
  rsu: "RSU",
  sn: "Special Needs",
  heloc: "HELOC",
};
const ACRONYM_DEFINITIONS = {
  DOB: "Date of birth",
  RMD: "Required minimum distribution",
  NIIT: "Net investment income tax",
  SS: "Social Security",
  MFJ: "Married filing jointly",
  IRMAA: "Income-related monthly adjustment amount",
  FMP: "Financial Modeling Prep",
  API: "Application programming interface",
  LTCG: "Long-term capital gains",
  PCT: "Percent",
  HSA: "Health savings account",
  DAF: "Donor-advised fund",
  LTC: "Long-term care",
  QCD: "Qualified charitable distribution",
  QBI: "Qualified business income",
  "W-2": "Wage and Tax Statement",
  "S-Corp": "S corporation",
  SDI: "State disability insurance",
  SSDI: "Social Security Disability Insurance",
  SSI: "Supplemental Security Income",
  ABLE: "Achieving a Better Life Experience",
  QTIP: "Qualified terminable interest property",
  IRA: "Individual retirement account",
  Roth: "Roth retirement account",
  PV: "Present value",
  AGI: "Adjusted gross income",
  MAGI: "Modified adjusted gross income",
  CPI: "Consumer Price Index",
  COLA: "Cost-of-living adjustment",
  ETF: "Exchange-traded fund",
  REIT: "Real estate investment trust",
  REITs: "Real estate investment trusts",
  TIPS: "Treasury Inflation-Protected Securities",
  PDF: "Portable Document Format",
  CSV: "Comma-separated values",
  YAML: "YAML Ain’t Markup Language",
  JSON: "JavaScript Object Notation",
  SQLite: "SQLite database",
  UI: "User interface",
  "Monte Carlo": "Repeated simulation analysis",
  OOP: "Out-of-pocket",
  SEHI: "Self-employed health insurance",
  PDIA: "Participating deferred income annuity",
  PIA: "Primary Insurance Amount — Social Security’s base monthly benefit at Full Retirement Age before early-claiming reductions or delayed-retirement credits",
  FRA: "Full Retirement Age — the Social Security age when the unreduced base benefit is available",
  HELOC: "Home equity line of credit",
};

const TERM_NOTES = {
  "Monte Carlo": "(repeated random simulation)",
  "terminal net worth": "(projected final portfolio value)",
  "Terminal net worth": "(projected final portfolio value)",
  "Terminal Net Worth": "(projected final portfolio value)",
  "Monte Carlo success":
    "(percentage of simulated scenarios where the plan stays solvent)",
  "probability of success":
    "(percentage of simulated scenarios where the plan stays solvent)",
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
    "This page captures estate-tax, trust, beneficiary, legacy-planning, and non-life protection-policy assumptions (disability, long-term care, umbrella, and property and casualty). It tells the model how assets should be interpreted after death or for survivor planning, and records protection coverage that is not investment return.",
    "Federal/state exemptions, CST/QTIP settings, beneficiary needs, special-needs planning, gifting, and insurance benefits connect to legacy value, estate-tax exposure, survivor analysis, Roth strategy scoring, and executor-oriented workbook notes. Non-life policy premiums connect to cash flow; benefits connect to survivor and Long-Term Care Stress report sections. Life insurance policies are entered on Special Income, Annuities & Insurance.",
    "Use monitor/balanced/strong estate objectives depending on whether estate tax is a watch item or a decision driver. Enter trust and beneficiary facts only when they are part of the intended plan. Use policy type, premium end, term end, benefit amount, and owner/insured fields consistently for protection policies.",
    "More aggressive estate-tax planning may reduce projected estate tax and improve legacy quality, but can reduce flexibility if assets are transferred, restricted, or earmarked too early. More non-life coverage can reduce downside risk and improve survivor/LTC stress results, but premiums may lower terminal net worth if no claim occurs.",
  ),
  annuity_death_benefits: pageHelp(
    "Special Income, Annuities & Insurance",
    "This page records policy-by-year death benefits for annuities or riders, and life insurance policy details. It combines a year-by-year schedule with individual policy records — not a generic account balance table.",
    "Each annuity policy row connects to survivor, estate, and legacy reporting. Year columns show how protection changes over time and whether a benefit disappears before the end of the plan. Life insurance premiums connect to cash flow each year; benefit amounts appear in the Survivor report sections.",
    "Enter the carrier illustration values for each year for annuities. Use 0 when no death benefit is available in that year. For life insurance, use policy type, premium end, term end, benefit amount, and owner/insured fields consistently. Keep policy names consistent with other insurance/annuity entries.",
    "Higher death benefits improve survivor/legacy protection but may come with lower investment growth, liquidity restrictions, or ongoing rider costs that should be reflected elsewhere. More life insurance coverage can reduce downside risk but premiums may lower terminal net worth if no claim occurs.",
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
    "Save Changes stores all entered values. Download Workbook and Download PDF each save, build, and deliver in one click when there are unsaved changes or no current build.",
    "Use Save Changes when you want to save without triggering a rebuild. Use Download when ready for final output. Resolve any required-field warnings before downloading. Bulk import/export is in Settings → System Configuration.",
    "A successful build refreshes projected net worth, lifetime taxes, Monte Carlo success, allocation recommendations, and all narrative sections. The downloaded file reflects the last successful build — download again after each rebuild to get the latest.",
  ),
  build_impact: pageHelp(
    "Build impact",
    "This page explains what changed in the latest build compared with the session baseline. It is a review and revert tool, not a data-entry page.",
    "The comparison uses values captured before this editing session and values after the last successful build. It helps connect changed assumptions to terminal net worth, lifetime taxes, Roth conversions, liquidity, and output warnings.",
    "Revert restores captured before-values for edited inputs. Rebuild confirms whether the reverted or edited plan changes the authoritative workbook/PDF outputs.",
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
    "Entity and charitable giving",
    "This strategy page covers two related decisions: business-entity choice (S-Corp vs LLC) and charitable giving vehicle (cash, DAF, QCD). Annual giving amounts are entered on Core spending.",
    "Entity choice connects to payroll taxes and QBI; charitable vehicle choice connects to deductions, lifetime taxes, and legacy. Both appear in dedicated workbook sheets.",
    "Set the entity assumptions if self-employed, and choose how charitable gifts are funded. Use QCDs after RMD age where appropriate.",
    "Entity optimization can reduce payroll/self-employment tax; charitable vehicle choice can lower taxes and increase legacy, but may reduce near-term liquidity.",
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
  holdingsText = "",
  liabilitiesText = "",
  liabilitiesChanged = false,
  dirty = new Map(),
  holdingsChanged = false,
  travelExtras = [],
  travelTypes = [],
  travelExtrasChanged = false,
  liquidityBuffers = [],
  liquidityChanged = false,
  forcedConversions = [],
  forcedConversionsChanged = false,
  forcedConversionAccounts = [],
  estateStateOptions = [],
  planLoaded = false,
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
  ytdTxPage = 0;
const YTD_ACTUALS_PERIOD_LS_KEY = "retirement.ytd_actuals_period.v1";
function normalizeYtdActualsPeriod(v) {
  return String(v || "").toLowerCase() === "last_year" ? "last_year" : "ytd";
}
function readYtdActualsPeriod() {
  try {
    return normalizeYtdActualsPeriod(
      localStorage.getItem(YTD_ACTUALS_PERIOD_LS_KEY) || "ytd",
    );
  } catch (_e) {
    return "ytd";
  }
}
let ytdActualsPeriod = readYtdActualsPeriod();
function setYtdActualsPeriod(period) {
  const next = normalizeYtdActualsPeriod(period);
  if (next === ytdActualsPeriod) return;
  ytdActualsPeriod = next;
  try {
    localStorage.setItem(YTD_ACTUALS_PERIOD_LS_KEY, ytdActualsPeriod);
  } catch (_e) {}
  loadYtdStatus().then(() => renderMain());
}
function ytdActualsPeriodToggleHtml(idSuffix) {
  const id = "ytdActualsPeriod_" + String(idSuffix || "default");
  const isLastYear = ytdActualsPeriod === "last_year";
  return (
    `<div class="ytd-actuals-period-toggle segmented-toggle" role="radiogroup" aria-label="Actuals period">` +
    `<button type="button" class="seg-btn${isLastYear ? "" : " active"}" role="radio" aria-checked="${!isLastYear}" onclick="setYtdActualsPeriod('ytd')">Year-to-date</button>` +
    `<button type="button" class="seg-btn${isLastYear ? " active" : ""}" role="radio" aria-checked="${isLastYear}" onclick="setYtdActualsPeriod('last_year')">Last year</button>` +
    `</div>`
  );
}
let taxonomyData = null,
  taxonomyFlat = {},
  taxonomyLoading = false,
  taxonomyError = "";
let taxFreshnessData = null,
  taxFreshnessLoading = false;
let holdingsPriceData = null,
  holdingsPriceLoading = false;
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
const YTD_TX_PAGE_SIZE = 500;
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
function saveWorkbookViewState() {
  try {
    localStorage.setItem("wbSheet", activeDetailedSheet || "");
    localStorage.setItem("wbGroups", JSON.stringify(detailedColumnGroupsOpen));
  } catch (_e) {}
}
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
  buildOverlayExpectedLabel = "",
  buildOverlayLastTitle = "",
  buildOverlayLastDetail = "",
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
let planFileHandles = { clientData: null, clientHoldings: null };
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
function pageHelp(title, meaning, connections, options, impact) {
  const acronyms = acronymDefinitionsHtml([
    title,
    meaning,
    connections,
    options,
    impact,
  ]);
  return `<div class="help-title">${esc(title)}</div><div class="help-body"><h3>What this page is for</h3><p>${esc(meaning)}</p><h3>How the values work together</h3><p>${esc(connections)}</p><h3>How to choose values</h3><p>${esc(options)}</p><h3>Likely planning impact</h3><p>${esc(impact)}</p>${acronyms}</div>`;
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
function showConfigCardHelp(key) {
  document.getElementById("helpPanel").innerHTML =
    SYSTEM_CONFIG_FIELD_HELP[key] || STEP_HELP.system_configuration;
}
function esc(s) {
  return String(s ?? "").replace(
    /[&<>"']/g,
    (m) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        m
      ],
  );
}
function escJs(s) {
  return String(s ?? "")
    .replace(/\\/g, "\\\\")
    .replace(/'/g, "\\'")
    .replace(/\n/g, "\\n")
    .replace(/\r/g, "");
}
function apiUrl(p) {
  return (apiBase || "") + p;
}
async function logoutSaas() {
  return true;
} // v10 local-only: no login/logout flow
function showMessage(msg, kind = "info", opts) {
  const el = document.getElementById("actionMessage");
  if (!el) return;
  const persistent = !!(opts && opts.persistent);
  const techDetail =
    opts && opts.technicalDetail ? String(opts.technicalDetail) : "";
  const actionHtml =
    opts && opts.action
      ? `<button class="msg-action" onclick="${escJs(opts.action.fn)}">${esc(opts.action.label)}</button>`
      : "";
  const dismissHtml =
    persistent || techDetail
      ? `<button class="msg-dismiss" onclick="dismissMessage()" aria-label="Dismiss">&#215;</button>`
      : "";
  const detailHtml = techDetail
    ? `<details class="msg-detail-wrap"><summary>Technical details</summary><pre class="msg-detail-pre">${esc(techDetail)}</pre></details>`
    : "";
  el.innerHTML = `<span class="msg-text">${esc(msg)}</span>${detailHtml}${actionHtml}${dismissHtml}`;
  el.className =
    "message" +
    (kind === "error" ? " bad" : kind === "warn" ? " warn" : "") +
    (persistent || techDetail ? " persistent" : "") +
    (techDetail ? " has-detail" : "");
  el.classList.remove("hidden");
  clearTimeout(showMessage._t);
  if (!persistent && !techDetail)
    showMessage._t = setTimeout(() => el.classList.add("hidden"), 10000);
}
function dismissMessage() {
  const el = document.getElementById("actionMessage");
  if (el) el.classList.add("hidden");
}
function formatAcronyms(text) {
  let out = String(text ?? "");
  out = out.replace(/\bMC\b/g, "Monte Carlo");
  for (const [k, v] of Object.entries(ACRONYMS)) {
    const re = new RegExp(
      "\\b" + k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\b",
      "gi",
    );
    out = out.replace(re, v);
  }
  return out
    .replace(/\bUi\b/g, "UI")
    .replace(/\bApi\b/g, "API")
    .replace(/\bJs\b/g, "JS")
    .replace(/\bCsv\b/g, "CSV")
    .replace(/\bPdia\b/g, "PDIA")
    .replace(/\bPia\b/g, "PIA")
    .replace(/\bFra\b/g, "FRA");
}
function escapeRegExp(s) {
  return String(s).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
function acronymDefinitionsHtml(parts) {
  const joined = formatAcronyms(
    (Array.isArray(parts) ? parts : [parts]).filter(Boolean).join(" "),
  );
  const found = [];
  Object.entries(ACRONYM_DEFINITIONS).forEach(([abbr, definition]) => {
    const re = new RegExp("\\b" + escapeRegExp(abbr) + "\\b");
    if (re.test(joined) && !found.some((x) => x.abbr === abbr))
      found.push({ abbr, definition });
  });
  if (!found.length) return "";
  return `<h3>Acronym definitions</h3><ul>${found.map((x) => `<li><b>${esc(x.abbr)}</b>: ${esc(x.definition)}</li>`).join("")}</ul>`;
}
function titleWord(w) {
  const low = w.toLowerCase();
  if (ACRONYMS[low]) return ACRONYMS[low];
  return low.charAt(0).toUpperCase() + low.slice(1);
}
function stripUiLabelPrefix(text) {
  return String(text || "")
    .replace(/^[^/]{1,80}\s*\/\s*/, "")
    .trim();
}
function humanLabel(label, row) {
  const _annuityDb = /^([hw])_(single|joint)$/i.exec(String(label || "").trim());
  if (_annuityDb)
    return `${personDisplayName(/^h$/i.test(_annuityDb[1]) ? 1 : 2)} ${titleWord(_annuityDb[2])}`;
  if (
    row &&
    row.section === "Account Policy" &&
    norm(row.label) === "reinvest_dividends"
  )
    return accountDisplayLabel(row.subsection);
  if (row && row.section === "Housing" && norm(row.label) === "hoa_pct")
    return "HOA Fee %";
  if (row && row.section === "Housing" && norm(row.label) === "hoa_annual")
    return "HOA Annual Fee";
  if (row && row.section === "Housing" && norm(row.label) === "re_tax_pct")
    return "RE Tax Rate";
  if (row && row.section === "Housing" && norm(row.label) === "city_type")
    return "Area Type";
  if (row && row.section === "Housing" && norm(row.label) === "population_size")
    return "Population (approx.)";
  if (
    row &&
    row.section === "Housing" &&
    norm(row.label) === "mortgage_rate_pct"
  )
    return "Mortgage Rate";
  if (row && row.section === "Housing" && norm(row.label) === "down_payment")
    return "Down Payment";
  if (
    row &&
    row.section === "healthcare" &&
    norm(row.label) === "medical_annual"
  )
    return "Annual Medical Out-of-Pocket";
  if (
    row &&
    row.section === "healthcare" &&
    norm(row.label) === "dental_annual"
  )
    return "Annual Dental Out-of-Pocket";
  if (
    row &&
    row.section === "healthcare" &&
    norm(row.label) === "vision_annual"
  )
    return "Annual Vision Out-of-Pocket";
  if (
    row &&
    row.section === "healthcare" &&
    norm(row.label) === "pharmacy_annual"
  )
    return "Annual Pharmacy Out-of-Pocket";
  if (row && norm(row.label) === "annual_spending_base_year")
    return "Core Spending Base";
  if (
    row &&
    row.section === "Cashflow" &&
    row.subsection === "Mortgage" &&
    norm(row.label) === "monthly_payment"
  )
    return "Current Monthly Mortgage Payment";
  if (
    row &&
    row.section === "Cashflow" &&
    row.subsection === "Mortgage" &&
    norm(row.label) === "balance_as_of_plan_start"
  )
    return "Current Loan Amount";
  if (
    row &&
    row.section === "Cashflow" &&
    row.subsection === "Mortgage" &&
    norm(row.label) === "last_payment_year"
  )
    return "Last Payment Year";
  if (
    row &&
    row.section === "Cashflow" &&
    row.subsection === "Mortgage" &&
    norm(row.label) === "last_payment_date"
  )
    return "Last Payment Date";
  if (
    row &&
    row.section === "Cashflow" &&
    row.subsection === "Mortgage" &&
    norm(row.label) === "annual_real_estate_taxes"
  )
    return "Annual Real Estate Taxes";
  if (
    row &&
    row.section === "Cashflow" &&
    row.subsection === "Mortgage" &&
    norm(row.label) === "real_estate_tax_annual_adjustment_pct"
  )
    return "Annual RE Tax Adjustment";
  if (row && norm(row.label) === "core_spending_growth_mode")
    return "Core Spending Increase Method";
  if (row && norm(row.label) === "core_spending_manual_growth_rate")
    return "Manual Core Spending Increase";
  if (row && norm(row.label) === "spending_freeze_year")
    return "Core Spending Increase Stops";
  if (row && norm(row.label) === "inflation_general")
    return "General CPI Inflation";
  if (row && norm(row.label) === "mc_engine_mode") return "Monte Carlo Engine";
  if (row && norm(row.label) === "monthly_pia_at_fra_today_dollars")
    return "Monthly at FRA";
  if (row && /^ss_benefit_age_(\d+)$/.test(String(row.label || "")))
    return `Benefit at ${String(row.label).match(/(\d+)$/)[1]}`;
  if (row && norm(row.label) === "ss_funding_discount_year")
    return "Discount Starts";
  if (row && norm(row.label) === "ss_funding_discount_pct")
    return "Benefit Reduction";
  if (row && norm(row.label) === "roth_target_bracket_rate")
    return "Roth Tax-Bracket Ceiling";
  if (row && norm(row.label) === "roth_irmaa_target_tier")
    return "Medicare IRMAA Tier Ceiling";
  if (row && norm(row.label) === "irmaa_guardrail_mode")
    return "IRMAA Guardrail Behavior";
  if (row && norm(row.label) === "roth_irmaa_headroom_usage_pct")
    return "IRMAA Headroom Used";
  if (row && norm(row.label) === "irmaa_annual_inflator")
    return "IRMAA Threshold Inflation";
  if (
    row &&
    row.section === "Other Assets" &&
    norm(row.subsection) === "home" &&
    norm(label) === "value_as_of_plan_start"
  )
    return "Home Value";
  if (
    row &&
    row.section === "Other Assets" &&
    row.subsection === "Cash" &&
    norm(label) === "value"
  )
    return "Checking Accounts";
  if (
    row &&
    row.section === "healthcare" &&
    row.subsection === "Pre-65 Bridge" &&
    norm(label) === "annual_premium_base_year"
  )
    return "Pre-65 Healthcare Premium";
  if (
    row &&
    row.section === "healthcare" &&
    row.subsection === "Medicare" &&
    norm(label) === "part_b_base_premium_monthly"
  )
    return "Monthly Medicare Part B";
  if (
    row &&
    row.section === "healthcare" &&
    row.subsection === "Medicare" &&
    norm(label) === "part_d_base_premium_monthly"
  )
    return "Monthly Medicare Part D";
  if (
    row &&
    row.section === "healthcare" &&
    row.subsection === "Medicare" &&
    norm(label) === "part_g_base_premium_monthly"
  )
    return "Monthly Medicare Part G";
  if (
    row &&
    row.section === "healthcare" &&
    row.subsection === "Out-of-Pocket" &&
    norm(label) === "annual_oop_estimate_today"
  )
    return "Annual Household Medical OOP Cap";
  if (
    row &&
    (norm(row.label) === "selling_cost_pct" ||
      norm(row.label) === "home_sale_selling_cost_pct")
  )
    return "Commission %";
  if (
    row &&
    (norm(row.label) === "selling_cost" ||
      norm(row.label) === "home_sale_selling_cost")
  )
    return "Commission";
  if (row && row.section === "Income Streams" && norm(row.label) === "type")
    return "Type";
  if (row && row.section === "Income Streams" && norm(row.label) === "js_pct")
    return "Joint-and-Survivor Percentage";
  if (
    row &&
    row.section === "Income Streams" &&
    norm(row.label) === "principal_recovery_age"
  )
    return "Principal Recovery Age";
  if (
    row &&
    row.subsection === "Tax-Loss Harvesting" &&
    norm(row.label) === "tlh_policy"
  )
    return "Policy";
  if (
    row &&
    row.subsection === "Tax-Loss Harvesting" &&
    norm(row.label) === "tlh_min_loss_dollars"
  )
    return "Minimum Loss ($)";
  if (
    row &&
    row.subsection === "Tax-Loss Harvesting" &&
    norm(row.label) === "tlh_min_loss_pct"
  )
    return "Minimum Loss (%)";
  if (
    row &&
    row.subsection === "Tax-Loss Harvesting" &&
    norm(row.label) === "tlh_annual_ceiling"
  )
    return "Annual Ceiling";
  if (
    row &&
    row.subsection === "Tax-Loss Harvesting" &&
    norm(row.label) === "tlh_transaction_cost_bps"
  )
    return "Transaction Cost (bps)";
  if (
    row &&
    row.subsection === "Tax-Loss Harvesting" &&
    norm(row.label) === "tlh_fraction_sold_before_death"
  )
    return "Fraction Sold Before Death";
  let s = stripUiLabelPrefix(label)
    .replace(/_pct$/i, "")
    .replace(/_pct_/gi, "_")
    .replace(/pct$/i, "")
    .replace(/_/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  s = s.replace(/\bnw\b/gi, "Net Worth");
  s = s.split(" ").map(titleWord).join(" ");
  s = s
    .replace(/\bMember 1\b/g, personDisplayName(1))
    .replace(/\bMember 2\b/g, personDisplayName(2));
  return formatAcronyms(s);
}
function fieldLabelNoteHtml(row) {
  const lbl = norm(row?.label);
  if (
    row &&
    row.section === "healthcare" &&
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
    row.section === "healthcare" &&
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
function translatePersonPlaceholders(text) {
  const withCompounds = String(text ?? "").replace(
    /\b(Member[ _]([12])|Husband|Wife)_([A-Za-z0-9]+)\b/g,
    (_m, whole, num, rest) =>
      personDisplayName(num ? Number(num) : /^husband/i.test(whole) ? 1 : 2) +
      "'s " +
      rest.replace(/_/g, " "),
  );
  return withCompounds
    .replace(/\bMember 1\b/g, personDisplayName(1))
    .replace(/\bMember 2\b/g, personDisplayName(2))
    .replace(/\bHusband\b/g, personDisplayName(1))
    .replace(/\bWife\b/g, personDisplayName(2));
}
function friendlyGroup(r) {
  if (
    r.section === "Account Policy" ||
    (r.section === "Economic Assumptions" &&
      norm(r.label) === "reinvest_dividends_default")
  )
    return "Dividend Reinvestment";
  if (
    r.section === "Other Assets" &&
    norm(r.subsection).startsWith("other_asset")
  )
    return "Other Asset Items";
  if (r.section === "Note Receivable" && norm(r.subsection) === "summary")
    return "Note Receivable";
  if (r.section === "HSA Policy") return "HSA";
  if (r.section === "DAF") return "DAF";
  if (r.section === "Hybrid LTC" || r.section === "Insurance In Force")
    return "LTC/Life Policy";
  if (r.section === "Education Funding") return "529 Plans";
  if (
    (r.section === "Asset Class Assumptions" ||
      r.section === "Asset Allocation Policy") &&
    r.subsection
  )
    return translatePersonPlaceholders(formatAcronyms(stripUiLabelPrefix(r.subsection)));
  if (r.section === "Asset Correlations") return "Pairwise Correlations";
  let s = r.subsection || r.section || "General";
  return translatePersonPlaceholders(formatAcronyms(stripUiLabelPrefix(s)));
}
function fmtMoney(v) {
  if (v === undefined || v === null || v === "") return "Not available";
  const n = Number(String(v).replace(/[^0-9.-]/g, ""));
  if (!Number.isFinite(n)) return "Not available";
  return n.toLocaleString(undefined, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  });
}
function fmtDelta(v) {
  if (v === undefined || v === null || v === "") return "Not available";
  const n = Number(v);
  if (!Number.isFinite(n)) return "Not available";
  const sign = n > 0 ? "+" : "";
  return (
    sign +
    n.toLocaleString(undefined, {
      style: "currency",
      currency: "USD",
      maximumFractionDigits: 0,
    })
  );
}
function fmtPct(v) {
  if (v === undefined || v === null || v === "") return "Not available";
  const n = Number(String(v).replace(/[^0-9.-]/g, ""));
  if (!Number.isFinite(n)) return "Not available";
  return n.toLocaleString(undefined, { maximumFractionDigits: 1 }) + "%";
}
function fmtPctDelta(v) {
  if (v === undefined || v === null || v === "") return "Not available";
  const n = Number(v);
  if (!Number.isFinite(n)) return "Not available";
  const sign = n > 0 ? "+" : "";
  return (
    sign + n.toLocaleString(undefined, { maximumFractionDigits: 1 }) + " pts"
  );
}
function finiteOrNull(v) {
  if (v === undefined || v === null || v === "") return null;
  const n = Number(String(v).replace(/[^0-9.-]/g, ""));
  return Number.isFinite(n) ? n : null;
}
function firstFinite(...vals) {
  for (const v of vals) {
    const n = finiteOrNull(v);
    if (Number.isFinite(n)) return n;
  }
  return NaN;
}
function deriveAfterTaxTerminalNw(summary) {
  summary = summary || {};
  const direct = firstFinite(
    summary.after_tax_terminal_nw,
    summary.after_tax_terminal_net_worth,
    summary.after_tax_nw,
    summary.after_tax_net_worth,
  );
  if (Number.isFinite(direct)) return direct;
  const terminal = firstFinite(summary.terminal_nw, summary.terminal_net_worth);
  const deferred = firstFinite(
    summary.terminal_deferred_tax_total,
    summary.terminal_deferred_pretax_tax,
    summary.terminal_deferred_taxable_cap_gain_tax,
    summary.deferred_pretax_tax,
    summary.embedded_deferred_tax,
  );
  if (Number.isFinite(terminal) && Number.isFinite(deferred))
    return terminal - deferred;
  const pretax = firstFinite(
    summary.terminal_pretax_nw,
    summary.terminal_pretax_net_worth,
    summary.pretax_terminal_nw,
  );
  const rate = firstFinite(
    summary.terminal_after_tax_rate_used,
    summary.roth_optimize_terminal_tax_rate,
    summary.roth_target_rate,
  );
  if (
    Number.isFinite(terminal) &&
    Number.isFinite(pretax) &&
    Number.isFinite(rate)
  )
    return (
      terminal -
      Math.max(0, pretax) * Math.max(0, Math.abs(rate) > 1 ? rate / 100 : rate)
    );
  return NaN;
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
function currentKpi(summary) {
  summary = summary || {};
  const afterTax = deriveAfterTaxTerminalNw(summary);
  return {
    terminal_nw: firstFinite(summary.terminal_nw, summary.terminal_net_worth),
    lifetime_tax: firstFinite(
      summary.lifetime_tax,
      summary.total_taxes,
      summary.total_tax,
    ),
    after_tax_terminal_nw: afterTax,
    post_tax_inheritance: firstFinite(summary.post_tax_inheritance, afterTax),
    terminal_estate_tax: firstFinite(summary.terminal_estate_tax),
    mc_success: firstFinite(
      summary.mc_success,
      summary.monte_carlo_success,
      summary.success_rate,
    ),
    total_roth_conversions: deriveTotalRothConversions(summary),
    blended_return_info: firstFinite(summary.blended_return_info),
  };
}
function kpiHasValues(summary) {
  const k = currentKpi(summary);
  return (
    Number.isFinite(k.terminal_nw) ||
    Number.isFinite(k.lifetime_tax) ||
    Number.isFinite(k.after_tax_terminal_nw) ||
    Number.isFinite(k.mc_success) ||
    Number.isFinite(k.total_roth_conversions) ||
    Number.isFinite(k.blended_return_info)
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
function cacheChart(html, title) {
  var id = "cc" + ++chartCacheSeq;
  chartCache[id] = { html: html, title: title || "" };
  return id;
}
function openCachedChart(id) {
  var c = chartCache[id];
  if (!c) return;
  var modal = document.getElementById("chartModal");
  if (!modal) return;
  var titleEl = document.getElementById("chartModalTitle");
  var bodyEl = document.getElementById("chartModalBody");
  if (titleEl) titleEl.textContent = c.title;
  if (bodyEl) bodyEl.innerHTML = c.html;
  modal.style.display = "flex";
  document.body.classList.add("chart-modal-open");
}
function closeChartModal() {
  var modal = document.getElementById("chartModal");
  if (modal) modal.style.display = "none";
  document.body.classList.remove("chart-modal-open");
}
function loadBuildHistory() {
  try {
    const raw = localStorage.getItem(BUILD_HISTORY_LS_KEY);
    buildHistory = raw ? JSON.parse(raw) : [];
  } catch (_e) {
    buildHistory = [];
  }
}
function saveBuildHistory() {
  try {
    localStorage.setItem(BUILD_HISTORY_LS_KEY, JSON.stringify(buildHistory));
  } catch (_e) {}
}
function pushBuildHistoryEntry(entry) {
  loadBuildHistory();
  buildHistory.unshift(entry);
  if (buildHistory.length > BUILD_HISTORY_MAX)
    buildHistory = buildHistory.slice(0, BUILD_HISTORY_MAX);
  saveBuildHistory();
  lastBuildCompare = buildHistory[0];
}
function shortHash(v) {
  v = String(v || "").trim();
  return v ? v.slice(0, 12) : "";
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
function buildHistoryProvenance(preflight) {
  preflight = preflight || buildPreflight || {};
  const snapshot = preflight.snapshot || {};
  const input = snapshot.input_fingerprint || {};
  return {
    schema: snapshot.schema || preflight.snapshot_schema || "",
    build_id: snapshot.build_id || "",
    code_version: snapshot.version || "",
    pricing_mode: preflight.pricing_mode || "",
    pricing_status: preflight.pricing_status || "",
    input_fingerprint: input.sha256 || "",
    workbook_fingerprint: artifactHashFromPreflight(
      preflight,
      "retirement_plan.xlsx",
    ),
    results_model_fingerprint: artifactHashFromPreflight(
      preflight,
      "results_explorer_model.json",
    ),
  };
}
function buildHistoryProvenanceHtml(entry) {
  const p = (entry && entry.provenance) || {};
  const chips = [];
  const pricing = [p.pricing_mode, p.pricing_status]
    .filter(Boolean)
    .join(" / ");
  if (pricing) chips.push(["Pricing", pricing]);
  if (p.input_fingerprint)
    chips.push(["Input", shortHash(p.input_fingerprint)]);
  if (p.workbook_fingerprint)
    chips.push(["Workbook", shortHash(p.workbook_fingerprint)]);
  if (p.results_model_fingerprint)
    chips.push(["Results", shortHash(p.results_model_fingerprint)]);
  if (p.code_version) chips.push(["Version", p.code_version]);
  if (!chips.length) return "";
  return (
    '<div class="build-history-provenance" aria-label="Build provenance">' +
    chips
      .map(
        ([k, v]) =>
          '<span title="' +
          esc(k + ": " + v) +
          '"><b>' +
          esc(k) +
          "</b> " +
          esc(v) +
          "</span>",
      )
      .join("") +
    "</div>"
  );
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
      mc_success: Number.isFinite(after.mc_success) ? after.mc_success : null,
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
      mc_success: Number.isFinite(kpis.mc_success) ? kpis.mc_success : null,
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
async function revertToBuildHistoryEntry(id) {
  loadBuildHistory();
  const entry = buildHistory.find((e) => e.id === id);
  if (!entry) {
    showMessage("Snapshot not found.", "error");
    return;
  }
  if (
    !(await showInAppConfirm(
      "Tracked field changes will be restored to their before-values from this snapshot.",
      { title: "Revert to Snapshot", confirmLabel: "Revert", variant: "warn" },
    ))
  )
    return;
  const changes = (entry.changes || []).filter(
    (c) => !c.special && c.row_index !== undefined,
  );
  if (!changes.length) {
    showMessage("No tracked field changes to revert in this snapshot.", "warn");
    return;
  }
  try {
    const updates = changes.map((c) => ({
      row_index: c.row_index,
      value: String(
        c.beforeStorage != null
          ? c.beforeStorage
          : c.before != null
            ? c.before
            : "",
      ),
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
    activeStep = "build_impact";
    renderMain();
    showMessage("Reverted to snapshot state. Save Changes to persist.");
  } catch (e) {
    showMessage("Error reverting to snapshot: " + e.message, "error");
  }
}
function buildKpiDial(label, value, heatFn, fmtFn) {
  const hasVal =
    value !== null && value !== undefined && Number.isFinite(Number(value));
  const heat = hasVal ? Math.max(0, Math.min(1, heatFn(Number(value)))) : null;
  const color =
    heat !== null ? "hsl(" + Math.round(heat * 120) + ",70%,40%)" + "" : "#999";
  const r = 28,
    circ = Math.round(2 * Math.PI * r);
  const dash = heat !== null ? Math.round((1 - heat) * circ) : circ;
  const svg =
    '<svg width="72" height="72" viewBox="0 0 72 72"><circle cx="36" cy="36" r="' +
    r +
    '" fill="none" stroke="#e0e0e0" stroke-width="8"/><circle cx="36" cy="36" r="' +
    r +
    '" fill="none" stroke="' +
    color +
    '" stroke-width="8" stroke-dasharray="' +
    circ +
    '" stroke-dashoffset="' +
    dash +
    '" transform="rotate(-90 36 36)" stroke-linecap="round"/><text x="36" y="40" text-anchor="middle" font-size="9" fill="' +
    color +
    '" font-weight="bold">' +
    esc(hasVal ? fmtFn(Number(value)).slice(0, 8) : "N/A") +
    "</text></svg>";
  return (
    '<div class="kpi-dial">' +
    svg +
    '<div class="kpi-dial-label">' +
    esc(label) +
    "</div></div>"
  );
}
function buildHistoryEntryHtml(entry, isCurrent, heat) {
  const kpi = entry.kpi || {};
  const nwDial = buildKpiDial(
    "Post-Tax Inheritance",
    kpi.inheritable_nw,
    heat.nwHeat,
    fmtMoney,
  );
  const taxDial = buildKpiDial(
    "Lifetime Tax",
    kpi.lifetime_tax,
    heat.taxHeat,
    fmtMoney,
  );
  const mcDial = buildKpiDial(
    "Success %",
    kpi.mc_success,
    heat.mcHeat,
    function (v) {
      return fmtPct(v * 100);
    },
  );
  const badge = entry.isSnapshot
    ? '<span class="badge">Snapshot</span>'
    : '<span class="badge good">Build</span>';
  const currentBadge = isCurrent
    ? '<span class="badge primary">Latest</span>'
    : "";
  const elapsed = entry.elapsed ? " · " + esc(entry.elapsed) : "";
  const changesHtml =
    entry.changes && entry.changes.length
      ? buildChangeSummaryHtml(entry.changes)
      : '<p class="small">No user field changes recorded in this entry.</p>';
  const revertBtn = !isCurrent
    ? '<button class="btn" type="button" data-requires-app="1" onclick="revertToBuildHistoryEntry(\'' +
      escJs(entry.id || "") +
      "')\" >Revert to this snapshot</button>"
    : "";
  const deleteBtn =
    '<button class="btn danger-link" type="button" onclick="deleteBuildHistoryEntry(\'' +
    escJs(entry.id || "") +
    "')\" >Delete</button>";
  const actionsHtml =
    revertBtn || deleteBtn
      ? '<div class="build-history-actions">' + revertBtn + deleteBtn + "</div>"
      : "";
  return (
    '<div class="build-history-entry' +
    (isCurrent ? " current" : "") +
    '"><div class="build-history-header"><span class="build-history-label">' +
    esc(entry.label || "") +
    " " +
    badge +
    " " +
    currentBadge +
    '</span><span class="build-history-ts small">' +
    esc(new Date(entry.timestamp).toLocaleString()) +
    elapsed +
    '</span></div><div class="build-history-dials">' +
    nwDial +
    taxDial +
    mcDial +
    "</div>" +
    buildHistoryProvenanceHtml(entry) +
    "<details><summary>Changes in this entry</summary>" +
    changesHtml +
    "</details>" +
    actionsHtml +
    "</div>"
  );
}
async function deleteBuildHistoryEntry(id) {
  if (
    !(await showInAppConfirm("This cannot be undone.", {
      title: "Delete Build History Entry",
      confirmLabel: "Delete",
      variant: "danger",
    }))
  )
    return;
  loadBuildHistory();
  buildHistory = buildHistory.filter(function (e) {
    return e.id !== id;
  });
  saveBuildHistory();
  if (lastBuildCompare && lastBuildCompare.id === id)
    lastBuildCompare = buildHistory[0] || null;
  renderMain();
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
function stepTitleById(id) {
  const s = STEPS.find((x) => x.id === id);
  return s ? s.title : String(id || "");
}
function sourceStepForSpecialLabel(label) {
  const l = norm(label);
  if (l.includes("holding")) return "holdings";
  if (l.includes("liabil")) return "assets_home_cash";
  if (l.includes("large_discretionary") || l.includes("travel_extras"))
    return "spending_travel_extras";
  if (l.includes("liquidity")) return "assets_home_cash";
  if (l.includes("forced_conversion")) return "roth_conversion";
  if (l.includes("transaction") || l.includes("account"))
    return "ytd_transactions";
  if (l.includes("budget") || l.includes("category") || l.includes("spending"))
    return "spending_core";
  return "all_assumptions";
}
function sourceStepForRow(row) {
  if (!row) return "";
  try {
    for (const id of BUILD_IMPACT_SOURCE_STEP_IDS) {
      if (rawRowsForStep(id).some((x) => x.row_index === row.row_index))
        return id;
    }
  } catch (_e) {}
  const sec = String(row.section || ""),
    sub = norm(row.subsection || ""),
    lbl = norm(row.label || "");
  if (sec === "Household") return "household_people";
  if (sec === "Social Security") return "income_retirement";
  if (sec === "Income Streams") return "income_retirement";
  if (sec === "Cashflow" && sub === "earned_income") return "income_work";
  if (sec === "Cashflow" && sub === "spending") return "spending_core";
  if (sec === "Cashflow" && sub === "mortgage")
    return "spending_mortgage_events";
  if (sec === "healthcare")
    return rowIsRetirementWellness(row)
      ? "retirement_wellness"
      : "economic_tax_assumptions";
  if (sec === "Other Assets" && sub === "home")
    return "spending_mortgage_events";
  if (sec === "Other Assets" && sub === "cash") return "assets_home_cash";
  if (sec === "Estate Planning") return "estate";
  if (sec === "Withdrawal Policy" && sub === "roth_conversion")
    return "roth_conversion";
  if (sec === "Withdrawal Policy") return "withdrawal_strategy";
  if (
    sec === "Asset Allocation Policy" ||
    sec === "Asset Class Optimizer Controls"
  )
    return "allocation_assets";
  if (sec === "Model Constants" && sub === "monte_carlo")
    return "monte_carlo_options";
  if (sec === "Scenarios") return "scenarios";
  if (sec === "Optional Functions") return "optional_functions";
  if (sec === "Economic Assumptions" || sec === "Payroll Tax")
    return "economic_tax_assumptions";
  return "all_assumptions";
}
function stepIdForRow(row) {
  return sourceStepForRow(row);
}
function buildSourceJumpHtml(stepId, label) {
  if (!stepId) return "";
  const title = stepTitleById(stepId);
  return `<button class="btn tiny build-source-jump" type="button" data-step-id="${esc(stepId)}" title="Open source page: ${esc(title)}">${esc(label || title)}</button>`;
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
  }
  const rec = sessionChanges.get(key);
  if (String(rec.beforeStorage) === String(rec.afterStorage))
    sessionChanges.delete(key);
}
function noteSpecialSessionChange(label) {
  sessionSpecialChanges.add(label);
}
function capturedSessionChanges() {
  const changes = [...sessionChanges.values()];
  const specials = [...sessionSpecialChanges].map((label) => {
    const sourceStep = sourceStepForSpecialLabel(label);
    return {
      label,
      group: "Plan Data",
      before: "",
      after: "Updated",
      special: true,
      sourceStep,
      sourceTitle: stepTitleById(sourceStep),
    };
  });
  return [...changes, ...specials];
}
function buildChangeSummaryHtml(changes) {
  const all = Array.isArray(changes) ? changes : capturedSessionChanges();
  if (!all.length)
    return '<p class="small">No user UI edits were captured before this build.</p>';
  const scenarioOnly = all.filter((c) =>
    String(c.scope || "")
      .toLowerCase()
      .includes("scenario analysis"),
  );
  let html = scenarioOnly.length
    ? `<div class="section-note warning"><b>${scenarioOnly.length} scenario-only change${scenarioOnly.length === 1 ? "" : "s"} captured.</b> These values are used in the workbook Scenario Analysis sheet but do not move the headline Build Impact cards unless the matching base-plan input is also changed.</div>`
    : "";
  html +=
    '<table class="change-table"><thead><tr><th>Factor</th><th>Source page</th><th>Before</th><th>After</th></tr></thead><tbody>';
  all.slice(0, 25).forEach((c) => {
    const source = c.sourceStep
      ? buildSourceJumpHtml(
          c.sourceStep,
          c.sourceTitle || stepTitleById(c.sourceStep),
        )
      : "";
    html += `<tr><td><div class="change-factor">${esc(c.label)}</div>${c.group ? `<div class="change-context">${esc(c.group)}${c.scope ? ` · ${esc(c.scope)}` : ""}</div>` : ""}</td><td>${source || esc(c.group || "—")}</td><td>${esc(c.before || "blank")}</td><td>${esc(c.after || "blank")}</td></tr>`;
  });
  if (all.length > 25)
    html += `<tr><td colspan="4" class="small">${all.length - 25} more user change${all.length - 25 === 1 ? "" : "s"} captured.</td></tr>`;
  html += "</tbody></table>";
  return html;
}
function adminBuildChangeSummaryHtml(events) {
  const evs = Array.isArray(events) ? events : [];
  if (!evs.length)
    return '<p class="small">No admin configuration changes were recorded since the previous build.</p>';
  let rows = [];
  evs.forEach((ev) => {
    (ev.changes || [])
      .slice(0, 8)
      .forEach((ch) =>
        rows.push({
          file: ev.file || ev.kind || "admin config",
          by: ev.changed_by || "",
          label: ch.label || "",
          before: ch.before || "",
          after: ch.after || "",
          count: ev.change_count || 1,
        }),
      );
  });
  if (!rows.length) {
    rows = evs.map((ev) => ({
      file: ev.file || ev.kind || "admin config",
      by: ev.changed_by || "",
      label: `${ev.change_count || 1} change${(ev.change_count || 1) === 1 ? "" : "s"}`,
      before: "",
      after: "updated",
      count: ev.change_count || 1,
    }));
  }
  let html =
    '<table class="change-table"><thead><tr><th>Admin file / setting</th><th>Before</th><th>After</th></tr></thead><tbody>';
  rows.slice(0, 25).forEach((r) => {
    html += `<tr><td><div class="change-factor">${esc(r.label)}</div><div class="change-context">${esc(r.file)}${r.by ? ` · ${esc(r.by)}` : ""}</div></td><td>${esc(r.before || "blank")}</td><td>${esc(r.after || "blank")}</td></tr>`;
  });
  if (rows.length > 25)
    html += `<tr><td colspan="3" class="small">${rows.length - 25} more admin setting change${rows.length - 25 === 1 ? "" : "s"} captured.</td></tr>`;
  html += "</tbody></table>";
  return html;
}
function impactCardHtml(
  title,
  delta,
  beforeVal,
  afterVal,
  valueFormatter,
  help,
  deltaFormatter = fmtDelta,
) {
  const headline = Number.isFinite(Number(delta))
    ? deltaFormatter(delta)
    : Number.isFinite(Number(afterVal))
      ? valueFormatter(afterVal)
      : "Not available";
  const headlineLabel = Number.isFinite(Number(delta))
    ? "Change"
    : "Current build";
  const hNeg = Number.isFinite(Number(delta))
    ? Number(delta) < 0
    : Number(afterVal) < 0;
  const bNeg = Number(beforeVal) < 0,
    aNeg = Number(afterVal) < 0;
  return `<div class="impact-card"><span>${esc(title)}</span><b class="${hNeg ? "negative-money" : ""}">${headline}</b><div class="impact-headline-label">${headlineLabel}</div><div class="impact-row"><span>Before</span><strong class="${bNeg ? "negative-money" : ""}">${valueFormatter(beforeVal)}</strong></div><div class="impact-row"><span>After</span><strong class="${aNeg ? "negative-money" : ""}">${valueFormatter(afterVal)}</strong></div>${help ? `<div class="small">${esc(help)}</div>` : ""}</div>`;
}
function buildImpactCardsHtml(before, after) {
  const dNw =
    Number.isFinite(after.terminal_nw) && Number.isFinite(before.terminal_nw)
      ? after.terminal_nw - before.terminal_nw
      : null;
  const dTax =
    Number.isFinite(after.lifetime_tax) && Number.isFinite(before.lifetime_tax)
      ? after.lifetime_tax - before.lifetime_tax
      : null;
  const dAfterTax =
    Number.isFinite(after.after_tax_terminal_nw) &&
    Number.isFinite(before.after_tax_terminal_nw)
      ? after.after_tax_terminal_nw - before.after_tax_terminal_nw
      : null;
  const mcBefore = Number.isFinite(before.mc_success)
    ? before.mc_success * 100
    : before.mc_success;
  const mcAfter = Number.isFinite(after.mc_success)
    ? after.mc_success * 100
    : after.mc_success;
  const dMc =
    Number.isFinite(mcAfter) && Number.isFinite(mcBefore)
      ? mcAfter - mcBefore
      : null;
  const riskCard =
    Number.isFinite(mcAfter) || Number.isFinite(mcBefore)
      ? impactCardHtml(
          "Probability of Success",
          dMc,
          mcBefore,
          mcAfter,
          fmtPct,
          "Higher is generally better. This is the clearest risk-adjusted plan outcome when Monte Carlo results are available.",
          fmtPctDelta,
        )
      : `<div class="impact-card"><span>Risk indicator</span><b>Not available</b><div class="impact-row"><span>Before</span><strong>${Number.isFinite(before.blended_return_info) ? fmtPct(before.blended_return_info) : "Not available"}</strong></div><div class="impact-row"><span>After</span><strong>${Number.isFinite(after.blended_return_info) ? fmtPct(after.blended_return_info) : "Not available"}</strong></div><div class="small">Probability of success was not available for this comparison.</div></div>`;
  const afterTaxCard = impactCardHtml(
    "Post-Tax Inheritance (PTI)",
    dAfterTax,
    before.after_tax_terminal_nw,
    after.after_tax_terminal_nw,
    fmtMoney,
    "Post-Tax Inheritance (PTI): gross terminal net worth minus the embedded taxes heirs would owe — deferred ordinary tax on remaining pre-tax retirement assets and deferred capital-gains tax on taxable brokerage assets. PTI is what beneficiaries actually keep, so it jointly rewards higher terminal net worth and lower taxes.",
  );
  return `<div class="impact-grid impact-grid-four">${impactCardHtml("Terminal net worth", dNw, before.terminal_nw, after.terminal_nw, fmtMoney, "Gross projected terminal net worth before embedded tax on remaining pre-tax assets.")} ${impactCardHtml("Lifetime taxes", dTax, before.lifetime_tax, after.lifetime_tax, fmtMoney, "Estimated taxes paid during the projection.")} ${afterTaxCard} ${riskCard}</div>`;
}

function impactDirectionWord(delta, kind) {
  if (!Number.isFinite(Number(delta))) return "stayed hard to quantify";
  const d = Number(delta);
  if (Math.abs(d) < 0.000001) return "held flat";
  if (kind === "tax") return d > 0 ? "increased" : "decreased";
  return d > 0 ? "improved" : "declined";
}
function buildImpactSourceLinksHtml(changes) {
  const byStep = new Map();
  (changes || []).forEach((c) => {
    const step = c.sourceStep || sourceStepForSpecialLabel(c.label || "");
    if (!step) return;
    const rec = byStep.get(step) || {
      title: c.sourceTitle || stepTitleById(step),
      count: 0,
      labels: [],
    };
    rec.count += 1;
    if (c.label && rec.labels.length < 3) rec.labels.push(c.label);
    byStep.set(step, rec);
  });
  if (!byStep.size)
    return '<p class="small">No source-page links were captured for this build.</p>';
  const items = [...byStep.entries()]
    .slice(0, 8)
    .map(
      ([step, rec]) =>
        `<li>${buildSourceJumpHtml(step, rec.title)}<span>${rec.count} captured change${rec.count === 1 ? "" : "s"}${rec.labels.length ? `: ${rec.labels.map(esc).join(", ")}` : ""}</span></li>`,
    )
    .join("");
  return `<ul class="build-impact-source-list">${items}</ul>`;
}
function buildImpactNarrativeHtml(entry) {
  entry = entry || {};
  const before = currentKpi(entry.before || {}),
    after = currentKpi(entry.after || {});
  const dNw =
    Number.isFinite(after.terminal_nw) && Number.isFinite(before.terminal_nw)
      ? after.terminal_nw - before.terminal_nw
      : null;
  const dTax =
    Number.isFinite(after.lifetime_tax) && Number.isFinite(before.lifetime_tax)
      ? after.lifetime_tax - before.lifetime_tax
      : null;
  const dAfterTax =
    Number.isFinite(after.after_tax_terminal_nw) &&
    Number.isFinite(before.after_tax_terminal_nw)
      ? after.after_tax_terminal_nw - before.after_tax_terminal_nw
      : null;
  const dMc =
    Number.isFinite(after.mc_success) && Number.isFinite(before.mc_success)
      ? (after.mc_success - before.mc_success) * 100
      : null;
  const changed = (entry.changes || []).length,
    adminChanged = (entry.admin_changes || []).length;
  let lead =
    "This build compared the saved plan before the last edit batch with the latest successful output package.";
  if (changed || adminChanged)
    lead = `This build compared ${changed} user input change${changed === 1 ? "" : "s"}${adminChanged ? ` plus ${adminChanged} admin/config event${adminChanged === 1 ? "" : "s"}` : ""} against the session baseline.`;
  const points = [];
  if (Number.isFinite(dAfterTax))
    points.push(
      `Post-Tax Inheritance ${impactDirectionWord(dAfterTax)} by ${fmtDelta(dAfterTax)}.`,
    );
  if (Number.isFinite(dNw))
    points.push(
      `Gross terminal net worth ${impactDirectionWord(dNw)} by ${fmtDelta(dNw)}.`,
    );
  if (Number.isFinite(dTax))
    points.push(
      `Lifetime taxes ${impactDirectionWord(dTax, "tax")} by ${fmtDelta(dTax)}.`,
    );
  if (Number.isFinite(dMc))
    points.push(
      `Probability of success ${impactDirectionWord(dMc)} by ${fmtPctDelta(dMc)}.`,
    );
  if (!points.length)
    points.push(
      "The latest summary did not contain enough before/after KPIs to calculate a numeric impact. Use the source links below to review what changed, then rebuild from a saved snapshot.",
    );
  let riskNote =
    "Use the source links below to inspect the inputs behind the measured changes before accepting the build as the new baseline.";
  if (Number.isFinite(dMc) && dMc < 0)
    riskNote =
      "Risk moved down, so treat higher net worth or lower tax results as tentative until you recover Monte Carlo success or explicitly accept more downside risk.";
  else if (
    Number.isFinite(dTax) &&
    dTax > 0 &&
    Number.isFinite(dAfterTax) &&
    dAfterTax > 0
  )
    riskNote =
      "Taxes rose, but after-tax inheritance also improved; review allocation or income timing sources to confirm the tradeoff was intentional.";
  else if (Number.isFinite(dAfterTax) && dAfterTax < 0)
    riskNote =
      "After-tax inheritance fell; start with the largest source-page change and test one rollback or lever at a time.";
  return `<div class="impact-narrative"><h4>Plain-English Build Impact summary</h4><p>${esc(lead)}</p><ul>${points.map((p) => `<li>${esc(p)}</li>`).join("")}</ul><p class="small"><b>Next check:</b> ${esc(riskNote)}</p><h4>Source-page links</h4>${buildImpactSourceLinksHtml(entry.changes || [])}</div>`;
}
function latestBuildImpactHtml(entry) {
  if (!entry || entry.isSnapshot) return "";
  const before = currentKpi(entry.before || {}),
    after = currentKpi(entry.after || {});
  return `<div class="latest-build-impact"><h3>Latest Build Impact</h3>${buildImpactNarrativeHtml(entry)}${buildImpactCardsHtml(before, after)}${buildImpactSuggestionsHtml(before, after, entry.after || {})}${modelHeardHtml(entry.after || {})}<details><summary>User input changes and source links</summary>${buildChangeSummaryHtml(entry.changes || [])}</details><details><summary>Admin/config changes</summary>${adminBuildChangeSummaryHtml(entry.admin_changes || [])}</details></div>`;
}

function mhBool(v) {
  return (
    v === true ||
    String(v).toLowerCase() === "true" ||
    String(v).toLowerCase() === "yes" ||
    String(v) === "1"
  );
}
function mhPct(v) {
  const n = Number(v);
  if (!Number.isFinite(n)) return "not set";
  const pct = Math.abs(n) <= 1 ? n * 100 : n;
  return pct.toLocaleString(undefined, { maximumFractionDigits: 2 }) + "%";
}
function mhMoney(v) {
  const n = Number(v);
  if (!Number.isFinite(n)) return "not set";
  return n.toLocaleString(undefined, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  });
}
function mhText(v, fallback = "not set") {
  if (v === undefined || v === null || v === "") return fallback;
  return String(v);
}
function mhOnOff(v) {
  return mhBool(v) ? "On" : "Off";
}
function mhRow(title, impact, action, detail) {
  return `<li><b>${esc(title)}</b><span>${esc(impact)}<br><em>Action:</em> ${esc(action)}${detail ? `<br><span class="small">${esc(detail)}</span>` : ""}</span></li>`;
}
function modelHeardHtml(summary) {
  const h = (summary && summary.model_heard_assumptions) || {};
  if (!Object.keys(h).length) return "";
  const ss = h.social_security || {},
    home = h.home_and_property_tax || {},
    hc = h.healthcare || {},
    taxable = h.taxable_income || {},
    roth = h.roth_and_irmaa || {},
    estate = h.tax_and_estate || {},
    mc = h.monte_carlo || {},
    alloc = h.allocation || {},
    rep = h.reporting || {};
  const rows = [];
  if (h.plan_years) {
    rows.push(
      mhRow(
        "Time horizon",
        "The model projected the plan over " +
          mhText(h.plan_years) +
          ". A wrong start or end year shifts every income, tax, spending, and estate calculation.",
        "Verify the plan years match the horizon you intend to compare before interpreting terminal net worth.",
      ),
    );
  }
  rows.push(
    mhRow(
      "Social Security income",
      "The build used husband claim age " +
        mhText(ss.husband_claim_age) +
        " and wife claim age " +
        mhText(ss.wife_claim_age) +
        ". Benefits are reduced by " +
        mhPct(ss.funding_discount_pct) +
        " starting in " +
        mhText(ss.funding_discount_year) +
        " for the funding-shortfall stress.",
      "To isolate this drag, set Social Security funding discount percent to 0%, rebuild, and compare terminal net worth and withdrawal needs.",
      `PIA inputs: ${mhOnOff(ss.uses_pia)}; spousal benefits: ${mhOnOff(ss.spousal_benefits_enabled)}; survivor uses deceased claim age: ${mhOnOff(ss.survivor_uses_deceased_claim_age)}.`,
    ),
  );
  rows.push(
    mhRow(
      "Home sale and real-estate tax",
      "The base projection heard annual real estate taxes of " +
        mhMoney(home.annual_real_estate_taxes_today) +
        " growing at " +
        mhPct(home.real_estate_tax_growth_rate) +
        ". Current Home Value is " +
        mhMoney(home.current_home_value) +
        ". Base Plan Home Sale Year is " +
        mhText(home.base_home_sale_year, "0") +
        " with canonical Home Basis " +
        mhMoney(home.canonical_home_basis) +
        ".",
      "If property tax or base home sale year changed but headline impact did not move, confirm these heard values changed. Scenario-only Sell Home year affects the Scenario Analysis sheet, not the headline Build Impact cards.",
      `Sell Home stress-test year: ${mhText(home.sell_home_stress_year, "0")}; stress basis source: ${mhText(home.sell_home_stress_basis_source)}.`,
    ),
  );
  rows.push(
    mhRow(
      "healthcare cash flow",
      "The model is spending healthcare and healthcare costs instead of treating those fields as notes: ACA bridge premiums " +
        mhMoney(
          hc.bridge_premium_monthly_today ||
            (Number(hc.bridge_premium_today) || 0) / 12,
        ) +
        " per covered person per month today, Medicare B/D/G " +
        mhMoney(
          (Number(hc.part_b_monthly_today) || 0) +
            (Number(hc.part_d_monthly_today) || 0) +
            (Number(hc.part_g_monthly_today) || 0),
        ) +
        " per person per month today, and medical OOP cap/reference " +
        mhMoney(hc.oop_estimate_today) +
        ".",
      "If recent terminal net worth fell, test healthcare premium and medical-spending impact by temporarily setting bridge, Medicare, and non-premium medical assumptions to zero, then restore realistic values.",
      `ACA premium tax credit: ${mhOnOff(hc.aca_ptc_enabled)}; benchmark premium today: ${mhMoney(hc.aca_benchmark_premium_today)}; OOP cap utilization: ${mhPct(hc.oop_utilization_pct)}.`,
    ),
  );
  rows.push(
    mhRow(
      "Taxable portfolio income",
      "Taxable holdings now create annual dividends/interest using " +
        mhText(taxable.portfolio_distributions_mode) +
        ". This can raise AGI, Social Security taxation, IRMAA, NIIT, and reduce Roth-conversion room.",
      "If taxes jumped, review taxable account asset location and the admin capital-market distribution-yield assumptions before changing spending assumptions.",
      `Tax-exempt interest included in MAGI/provisional income: ${mhOnOff(taxable.tax_exempt_interest_in_magi)}. Gain mode: ${mhText(taxable.trust_gain_mode)}.`,
    ),
  );
  rows.push(
    mhRow(
      "Estate and survivor treatment",
      "The build used survivor/QSS, basis step-up, federal portability, and credit-shelter settings when calculating survivor cash flow and terminal estate values. CST funded/excluded amount shown by the last projection year is " +
        mhMoney(estate.cst_funded_total) +
        ".",
      "If terminal net worth or after-tax estate changed sharply, compare one rebuild with CST disabled or estate objective off, then restore the estate plan settings.",
      `Basis step-up: ${mhOnOff(estate.basis_step_up_at_death)} (${mhText(estate.basis_step_up_property_regime)}); CST: ${mhOnOff(estate.credit_shelter_trust_enabled)}; federal portability: ${mhOnOff(estate.federal_portability_enabled)}.`,
    ),
  );
  if (mc.engine_mode || mc.simulation_count) {
    rows.push(
      mhRow(
        "Monte Carlo risk mode",
        "The risk comparison used " +
          mhText(mc.engine_mode) +
          " Monte Carlo with " +
          mhText(mc.simulation_count) +
          " main paths and " +
          mhText(mc.sensitivity_simulation_count) +
          " sensitivity paths. Exact scalar is slower but more tax-faithful.",
        "For interactive work use moderate path counts; for final advisor review raise simulations and max_build_seconds, then rebuild once.",
        "If the build appears slow, lower path counts or increase System Configuration → Build timeout.",
      ),
    );
  }
  rows.push(
    mhRow(
      "Allocation and real-dollar reporting",
      "The allocation source is " +
        mhText(alloc.selection_mode) +
        ". Today-dollar output rows are " +
        mhOnOff(rep.real_dollar_rows_available) +
        " using " +
        mhText(rep.real_dollar_base_year) +
        " as the base year.",
      "Use real-dollar outputs when judging purchasing power; use nominal terminal net worth only when comparing like-for-like workbook runs.",
    ),
  );
  return `<details class="impact-suggestions model-used-panel collapsible-impact-section"><summary class="collapsible-summary"><span class="collapse-caret" aria-hidden="true"></span><span class="collapsible-title">What the model used in this build</span><span class="small collapsible-meta">${rows.length} impact checks</span></summary><div class="collapsible-content"><p class="small">Plain-English checks for assumptions that materially change cash flow, taxes, risk, and terminal net worth. These are not extra recommendations; they explain which model switches were actually consumed so you can run targeted what-if tests.</p><ol>${rows.join("")}</ol></div></details>`;
}
function buildImpactSuggestionsHtml(before, after, summary = {}) {
  const dNw =
    Number.isFinite(after.terminal_nw) && Number.isFinite(before.terminal_nw)
      ? after.terminal_nw - before.terminal_nw
      : null;
  const dTax =
    Number.isFinite(after.lifetime_tax) && Number.isFinite(before.lifetime_tax)
      ? after.lifetime_tax - before.lifetime_tax
      : null;
  const dMc =
    Number.isFinite(after.mc_success) && Number.isFinite(before.mc_success)
      ? after.mc_success - before.mc_success
      : null;
  const heard = (summary && summary.model_heard_assumptions) || {};
  const hc = heard.healthcare || {};
  const roth = heard.roth_and_irmaa || {};
  const mc = heard.monte_carlo || {};
  const alloc = heard.allocation || {};
  const suggestions = [];
  const add = (title, text, context) =>
    suggestions.push([title, text, context]);
  const riskAvailable =
    Number.isFinite(after.mc_success) || Number.isFinite(before.mc_success);
  const riskWorse = Number.isFinite(dMc) && dMc < 0;
  const riskLow = Number.isFinite(after.mc_success) && after.mc_success < 80;
  const riskFloor = Number.isFinite(after.mc_success)
    ? fmtPct(after.mc_success)
    : "the current Monte Carlo result";
  if (riskWorse) {
    add(
      "Recover Monte Carlo success before optimizing TNW",
      `This build lowered Monte Carlo success by ${fmtPctDelta(dMc)}. Undo or offset the change before accepting any higher terminal net worth or lower tax result.`,
      `Current risk floor: ${riskFloor}.`,
    );
  } else if (riskLow) {
    add(
      "Lift the risk floor first",
      `Monte Carlo success is ${riskFloor}, so the next what-if should improve probability of success before chasing terminal net worth. Start with flexible spending, large discretionary expenses, or retirement timing.`,
      `Treat ${riskFloor} as the minimum acceptable result until you intentionally choose a different risk level.`,
    );
  } else if (riskAvailable) {
    add(
      "Protect the current risk result",
      `Use ${riskFloor} as a floor when testing tax or net-worth improvements; reject changes that lower it unless you intentionally accept more risk.`,
      `Before/after risk move: ${Number.isFinite(dMc) ? fmtPctDelta(dMc) : "not available"}.`,
    );
  } else {
    add(
      "Turn on a risk comparison",
      "Run Monte Carlo or refresh the forecast package so Build Impact can judge whether a change improves taxes or net worth without lowering probability of success.",
      "No probability-of-success result was available for this build.",
    );
  }
  if (Number.isFinite(dTax) && dTax > 0) {
    add(
      "Look for tax-neutral or tax-lowering alternatives",
      `Lifetime taxes increased by ${fmtDelta(dTax)}. Test Roth conversion caps, LTCG harvesting limits, and taxable-gain budgets while keeping Monte Carlo success flat or better.`,
      `After-tax total: ${fmtMoney(after.lifetime_tax)}.`,
    );
  } else if (Number.isFinite(after.lifetime_tax)) {
    add(
      "Preserve the tax result while improving the plan",
      `Lifetime taxes are ${fmtMoney(after.lifetime_tax)}${Number.isFinite(dTax) ? ` (${fmtDelta(dTax)} vs. prior build)` : ""}. Keep this tax result as a constraint while testing allocation, spending, or timing changes.`,
      "Prefer tests that do not increase taxes unless they also improve risk-adjusted outcomes.",
    );
  }
  if (Number.isFinite(dNw) && dNw < 0) {
    add(
      "Recover terminal value without adding volatility",
      `Terminal net worth fell by ${fmtDelta(dNw)}. Test lower cash drag, planned-spending timing, lower-cost ETF substitutions, or tax-aware turnover limits before increasing portfolio risk.`,
      `After-build TNW: ${fmtMoney(after.terminal_nw)}.`,
    );
  } else if (Number.isFinite(after.terminal_nw)) {
    add(
      "Stress-test the terminal net-worth result",
      `Terminal net worth is ${fmtMoney(after.terminal_nw)}${Number.isFinite(dNw) ? ` (${fmtDelta(dNw)} vs. prior build)` : ""}. Rerun with conservative return and inflation assumptions to confirm the value did not come from added downside risk.`,
      "Keep Monte Carlo success flat or better during this stress test.",
    );
  }
  const bridgePremium = Number(hc.bridge_premium_today || 0);
  const medMonthly =
    Number(hc.part_b_monthly_today || 0) +
    Number(hc.part_d_monthly_today || 0) +
    Number(hc.part_g_monthly_today || 0);
  if (bridgePremium > 50000 || medMonthly > 800) {
    add(
      "Audit healthcare assumptions before changing investment risk",
      `The model heard ACA bridge premiums of ${mhMoney(bridgePremium)} per year and Medicare B/D/G of ${mhMoney(medMonthly)} per person per month. Normalize these if they are placeholders before taking more allocation risk.`,
      "healthcare cash flow can dominate withdrawals and Monte Carlo success.",
    );
  }

  if (
    String(alloc.selection_mode || "")
      .toLowerCase()
      .includes("user")
  ) {
    add(
      "Run the optimizer as a controlled allocation test",
      "Allocation is currently using the user target. Try the optimizer recommendation or optimizer override with the current Monte Carlo success as the floor, then reject changes that reduce probability of success.",
      "This tests risk-adjusted return without manually increasing risk first.",
    );
  } else if (alloc.selection_mode) {
    add(
      "Compare allocation modes one at a time",
      `Allocation mode is ${mhText(alloc.selection_mode)}. Compare it to the user target with the same spending and tax settings so Build Impact isolates the allocation effect.`,
      "Do not change Roth, spending, and allocation in the same run.",
    );
  }
  add(
    "Change one practical lever at a time",
    "Change only one lever—spending, retirement date, Roth conversions, allocation target, or rebalancing limits—then rebuild so the impact cards identify the tradeoff clearly.",
    "This keeps suggestions tied to measured risk, tax, and TNW moves.",
  );
  const shown = suggestions.slice(0, 6);
  return `<details class="impact-suggestions collapsible-impact-section dynamic-suggestions-panel"><summary class="collapsible-summary"><span class="collapse-caret" aria-hidden="true"></span><span class="collapsible-title">Suggestions to improve the plan without lowering risk</span><span class="small collapsible-meta">${shown.length} dynamic tests</span></summary><div class="collapsible-content"><p class="small">These are generated from this build's terminal net worth, lifetime taxes, Monte Carlo result, and model-heard assumptions. Keep probability of success flat or better when improving terminal net worth or lifetime taxes.</p><ol>${shown.map((s) => `<li><b>${esc(s[0])}</b><span>${esc(s[1])}</span>${s[2] ? `<span class="change-context">${esc(s[2])}</span>` : ""}</li>`).join("")}</ol></div></details>`;
}

function parseDollarLike(v) {
  const n = Number(
    String(v ?? "")
      .replace(/[$,%]/g, "")
      .replace(/,/g, ""),
  );
  return Number.isFinite(n) ? n : 0;
}
function planningLeverBase() {
  const summary =
    (lastBuildCompare && lastBuildCompare.after) || lastBuildSummary || {};
  const k = currentKpi(summary);
  const spend = Math.max(
    1,
    parseDollarLike(rowConfigValue("annual_spending_base_year", "200000")),
  );
  const earned = Math.max(
    0,
    parseDollarLike(rowConfigValue("annual_earned_income", "290000")),
  );
  const start =
    Number(
      rowConfigValue("plan_start_year", rowConfigValue("plan_start", "2026"))
        .toString()
        .replace(/[^0-9]/g, ""),
    ) || 2026;
  const end =
    Number(
      rowConfigValue("plan_end_year", rowConfigValue("plan_end", "2056"))
        .toString()
        .replace(/[^0-9]/g, ""),
    ) || 2056;
  const years = Math.max(1, end - start + 1);
  const success = Number.isFinite(k.mc_success) ? k.mc_success : 40;
  return {
    terminal: Number.isFinite(k.terminal_nw) ? k.terminal_nw : 0,
    pti: Number.isFinite(k.post_tax_inheritance)
      ? k.post_tax_inheritance
      : Number.isFinite(k.after_tax_terminal_nw)
        ? k.after_tax_terminal_nw
        : NaN,
    lifetime_tax: Number.isFinite(k.lifetime_tax) ? k.lifetime_tax : NaN,
    success,
    spend,
    earned,
    years,
  };
}
function leverPctPoints(v) {
  return Math.max(-30, Math.min(30, Number(v) || 0));
}
function planningLeverRows() {
  const b = planningLeverBase(),
    x = planningLeverInputs;
  const rows = [];
  function add(
    focus,
    lever,
    key,
    unit,
    tnw,
    success,
    note,
    source,
    sourceStep,
  ) {
    rows.push({
      focus,
      lever,
      key,
      unit,
      tnw,
      success: leverPctPoints(success),
      note,
      source,
      sourceStep,
    });
  }
  add(
    "TNW",
    "Reduce recurring/core spending",
    "spendingCut",
    "$/year",
    x.spendingCut * b.years * 0.55,
    (x.spendingCut / b.spend) * 25,
    "Improves both TNW and success by lowering annual withdrawals.",
    "Spending Categories",
    "spending_core",
  );
  add(
    "TNW",
    "Work longer / retire later",
    "retireLaterYears",
    "years",
    x.retireLaterYears * (b.earned * 0.45 + b.spend * 0.25),
    x.retireLaterYears * 8,
    "Usually the strongest lever because it adds income and delays withdrawals.",
    "Retirement Timing",
    "household_people",
  );
  add(
    "TNW",
    "Cut or delay large discretionary spending",
    "largeExpenseCut",
    "$ one-time",
    x.largeExpenseCut,
    (x.largeExpenseCut / b.spend) * 4,
    "Directly preserves liquidity and compounding capital.",
    "Large Discretionary",
    "spending_travel_extras",
  );
  add(
    "TNW",
    "Preserve annual S-Corp tax advantage",
    "sCorpBenefit",
    "$/year",
    x.sCorpBenefit * Math.min(5, b.years) * 0.9,
    (x.sCorpBenefit / b.spend) * 3,
    "Use actual entity-analysis benefit if different.",
    "Entity & Charitable",
    "entity_charitable",
  );
  add(
    "TNW",
    "Roth/tax optimization savings",
    "rothTaxSavings",
    "$ total",
    x.rothTaxSavings,
    0,
    "Improves after-tax legacy, but confirm it does not weaken near-term liquidity.",
    "Roth Conversion",
    "roth_conversion",
  );
  add(
    "TNW",
    "Improve return without raising volatility",
    "returnBps",
    "bps/year",
    b.terminal * (x.returnBps / 10000) * b.years * 0.35,
    (x.returnBps / 25) * 1,
    "Only positive if risk does not rise enough to hurt Monte Carlo success.",
    "Asset Allocation",
    "allocation_assets",
  );
  add(
    "Success",
    "Dedicated liquidity reserve",
    "cashReserve",
    "$ reserve",
    0,
    (x.cashReserve / b.spend) * 8,
    "Raises probability by reducing forced sales after bad early returns.",
    "Cash Reserves",
    "assets_home_cash",
  );
  add(
    "Success",
    "Home-equity backstop",
    "homeEquityBackstop",
    "$ available",
    0,
    (x.homeEquityBackstop / b.spend) * 6,
    "Improves success only if there is a real plan to access home equity.",
    "Housing",
    "spending_mortgage_events",
  );
  add(
    "Success",
    "Use HELOC or turn it off",
    "helocCredit",
    "$ credit line",
    x.helocCredit * 0.1,
    (x.helocCredit / b.spend) * 3,
    "Tests whether a HELOC backstop improves liquidity enough to justify interest cost and reduced home equity.",
    "HELOC Strategy",
    "heloc_strategy",
  );
  add(
    "Success",
    "Dynamic spending guardrail",
    "guardrailPct",
    "% cut in bad markets",
    b.spend * (x.guardrailPct / 100) * b.years * 0.25,
    x.guardrailPct * 0.6,
    "Flexing discretionary spending after poor markets is often a high-impact risk lever.",
    "Spending Categories",
    "spending_core",
  );
  add(
    "Success",
    "LTC / catastrophic-care protection",
    "ltcCoverage",
    "$ coverage",
    -x.ltcCoverage * 0.05,
    (x.ltcCoverage / b.spend) * 4,
    "May lower expected TNW slightly but protects downside paths.",
    "Estate Inputs",
    "estate",
  );
  return rows.sort(
    (a, b) =>
      Math.abs(b.success) +
      Math.abs(b.tnw) / 100000 -
      Math.abs(a.success) -
      Math.abs(a.tnw) / 100000,
  );
}
function setPlanningLeverInput(key, val) {
  const n = Number(
    String(val || "")
      .replace(/[$,%]/g, "")
      .replace(/,/g, ""),
  );
  planningLeverInputs[key] = Number.isFinite(n) ? n : 0;
  renderMain();
}
function analysisFrame(body, kind) {
  const b =
    typeof planningLeverBase === "function"
      ? planningLeverBase()
      : { terminal: 0, success: 0 };
  const isStress = kind === "stress";
  const intro = `<div class="section-note">${isStress ? "Set the assumptions below, rebuild, then open the full result in the workbook." : "Set the inputs below, preview the directional impact on Planning Overview, then rebuild to confirm."}</div>`;
  const chip = `<div class="ytd-status-grid"><div class="pill"><b>Current terminal NW</b><span>${fmtMoney(b.terminal)}</span></div><div class="pill"><b>Monte Carlo success</b><span>${fmtPct(b.success)}</span></div></div>`;
  const footer = `<div class="section-note"><div class="pane-actions"><button class="btn" type="button" data-step-id="planning_levers">Preview impact (Planning overview)</button> <button class="btn good" type="button" onclick="setStep('detailed_results')">View full result in workbook</button></div></div>`;
  return intro + chip + (body || "") + footer;
}
function renderStateResidency() {
  const rs = rowsForStep("state_residency");
  const stateComp = rs.filter(
    (r) => String(r.section || "").trim() === "State Comparison",
  );
  let html = `<div class="section-note">Baseline state is set on <a href="#" onclick="setStep('household_people');return false">Household People</a>. Enter the target state and cost differences below — the workbook State Residency sheet shows annual and lifetime impact.</div>`;
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
  let html = `<div class="section-note">S-Corp election reduces self-employment tax on income above a reasonable salary. Qualified charitable distributions (age 70½+) satisfy required distributions without the amount appearing as taxable income. Annual giving amounts are set on <a href="#" onclick="setStep('spending_core');return false">Core spending</a>.</div>`;
  return html + renderFields("entity_charitable");
}
function renderSurvivorStress() {
  const rs = rowsForStep("survivor_stress");
  let html = `<div class="section-note">These are the key inputs driving the Survivor workbook sheet. The primary risks: single-filer tax bracket compression, loss of one Social Security stream, and accelerated required distributions. Change mortality ages or filing status on <a href="#" onclick="setStep('household_people');return false">Household &amp; People</a> to adjust the base assumptions. After rebuilding, view the full Survivor analysis on <a href="#" onclick="setStep('detailed_results');return false">Retirement Plan Workbook</a>.</div>`;
  return (
    html +
    (rs.length
      ? renderFieldGroups(rs)
      : `<div class="field-list"><p>Survivor inputs are entered on Household &amp; People. The full survivor result appears in the workbook after a build.</p></div>`)
  );
}
function renderLtcStress() {
  if (!optionalFunctionEnabled("long_term_care_stress"))
    return '<div class="field-list"><p>Long-Term Care Stress inputs are hidden until the Long-Term-Care Stress optional workbook module is enabled on <a href="#" onclick="setStep(\'optional_functions\');return false">Optional Modules</a>.</p></div>';
  const rs = rowsForStep("ltc_stress");
  let html = `<div class="section-note">Set care cost and duration, then rebuild. Policy details (benefit amount, elimination period) are on <a href="#" onclick="setStep('assets_special');return false">Other assets</a>.</div>`;
  return (
    html +
    (rs.length
      ? renderFieldGroups(rs)
      : `<div class="field-list"><p>No long-term-care policy inputs found yet. Add a Hybrid LTC policy on Other assets.</p></div>`)
  );
}
function planningLeversBaselineReady() {
  return !!(
    planLoaded &&
    (lastBuildOk ||
      planStateArtifactsReady() ||
      kpiHasValues(lastBuildSummary) ||
      (lastBuildCompare && kpiHasValues(lastBuildCompare.after)))
  );
}
function planningLeversPlaceholder() {
  if (!buildPreflight)
    setTimeout(() => refreshBuildStatus().catch(function () {}), 0);
  return `<div class="holdings planning-levers planning-levers-empty"><div class="empty-state-panel"><span class="eyebrow">Baseline required</span><h3>Build once before using Strategy Levers</h3><p>Planning Levers rank changes against the latest successful baseline. Build reports first so the page can use real terminal net worth, post-tax inheritance, lifetime tax, and Monte Carlo success values instead of placeholder zeros.</p><div class="pane-actions"><button class="btn primary" type="button" data-requires-app="1" onclick="runBuild(false)">Build Reports</button><button class="btn" type="button" data-step-id="review">Open Review and Build</button><button class="btn" type="button" onclick="refreshPreflightForReview()">Refresh Preflight</button></div></div><div class="feature-grid optimizer-hub" style="margin:10px 0 14px"><div class="feature-card"><h3>What unlocks after build</h3><p class="small">Ranked lever estimates, measured baseline KPIs, and source-page jumps for changing the actual plan.</p></div><div class="feature-card"><h3>Where to work meanwhile</h3><p class="small">Use Roth Conversion, Asset Allocation, Spending Categories, Scenarios, and Monte Carlo pages to stage inputs before the first baseline build.</p></div></div></div>`;
}
function renderPlanningLevers() {
  if (!planningLeversBaselineReady()) return planningLeversPlaceholder();
  const b = planningLeverBase();
  const rows = planningLeverRows();
  const tnw = rows
    .slice()
    .sort((a, b) => b.tnw - a.tnw)
    .slice(0, 6);
  const suc = rows
    .slice()
    .sort((a, b) => b.success - a.success)
    .slice(0, 6);
  function inputCell(r) {
    return `<span class="lever-input-wrap"><input class="compact-input lever-test-input" value="${esc(planningLeverInputs[r.key])}" onchange="setPlanningLeverInput('${escJs(r.key)}',this.value)"><small class="lever-unit">${esc(r.unit)}</small></span>`;
  }
  function sourceCell(r) {
    if (!r.source) return "—";
    return `<button class="btn tiny source-jump" type="button" data-step-id="${esc(r.sourceStep || "")}" title="Open ${esc(r.source)}">${esc(r.source)}</button>`;
  }
  function tr(r) {
    return `<tr><td>${esc(r.focus)}</td><td><b>${esc(r.lever)}</b><div class="small">${esc(r.note)}</div></td><td class="lever-source-cell">${sourceCell(r)}</td><td>${inputCell(r)}</td><td>${fmtMoney(r.tnw)}</td><td>${fmtPct(r.success)}</td></tr>`;
  }
  return `<div class="holdings planning-levers"><h3 class="group-title">Strategy Levers</h3><p class="small"><button class="btn tiny" type="button" data-step-id="planning_workbench">Back to Planning Workbench</button></p><p class="small">Estimates assume all other inputs stay fixed. Change the test amount to resize any estimate without affecting your plan. Use the Source column beside each lever to jump to the page where the actual plan value is changed, then rebuild to confirm the real effect.</p><div class="feature-grid optimizer-hub" style="margin:10px 0 14px"><div class="feature-card"><h3>Strategy · decide</h3><div class="pane-actions"><button class="btn" type="button" data-step-id="roth_conversion">Roth conversion</button> <button class="btn" type="button" data-step-id="allocation_assets">Asset allocation</button> <button class="btn" type="button" data-step-id="withdrawal_strategy">Withdrawal sequencing</button> <button class="btn" type="button" data-step-id="income_retirement">Social Security</button> <button class="btn" type="button" data-step-id="state_residency">State residency</button> <button class="btn" type="button" data-step-id="entity_charitable">Entity &amp; charitable</button> <button class="btn" type="button" data-step-id="heloc_strategy">HELOC strategy</button></div></div><div class="feature-card"><h3>Stress tests · resilience</h3><div class="pane-actions"><button class="btn" type="button" data-step-id="monte_carlo_options">Monte Carlo</button> <button class="btn" type="button" data-step-id="scenarios">Scenarios</button> <button class="btn" type="button" data-step-id="survivor_stress">Survivor</button> <button class="btn" type="button" data-step-id="ltc_stress">Long-term care</button> <button class="btn" type="button" data-step-id="divorce_options">Divorce / QDRO</button></div></div></div><div class="ytd-status-grid"><div class="pill"><b>Current terminal NW</b><span>${fmtMoney(b.terminal)}</span></div><div class="pill" title="Post-Tax Inheritance: terminal net worth minus the embedded taxes heirs would owe on pre-tax accounts and unrealized gains — what beneficiaries actually keep."><b>Post-Tax Inheritance (PTI)</b><span>${Number.isFinite(b.pti) ? fmtMoney(b.pti) : "—"}</span></div><div class="pill"><b>Lifetime taxes</b><span>${Number.isFinite(b.lifetime_tax) ? fmtMoney(b.lifetime_tax) : "—"}</span></div><div class="pill"><b>Current success rate</b><span>${fmtPct(b.success)}</span></div><div class="pill"><b>Core annual spending</b><span>${fmtMoney(b.spend)}</span></div><div class="pill"><b>Earned income assumption</b><span>${fmtMoney(b.earned)}</span></div></div><div class="section-note small" style="margin:4px 0 10px"><b>TNW</b> = Terminal Net Worth (projected portfolio at end of plan horizon) · <b>PTI</b> = Post-Tax Inheritance (TNW minus embedded taxes heirs would owe) · <b>Success rate</b> = Monte Carlo trials where the plan maintains the reserve floor through the planning horizon</div><div><div><h3>Ranked by estimated TNW lift</h3><div class="lot-table-wrap"><table class="lot-table planning-lever-table"><thead><tr><th>Focus</th><th>Lever</th><th>Source</th><th>Test amount</th><th>Est. Δ TNW</th><th>Est. Δ success</th></tr></thead><tbody>${tnw.map(tr).join("")}</tbody></table></div></div><div><h3>Ranked by estimated success lift</h3><div class="lot-table-wrap"><table class="lot-table planning-lever-table"><thead><tr><th>Focus</th><th>Lever</th><th>Source</th><th>Test amount</th><th>Est. Δ TNW</th><th>Est. Δ success</th></tr></thead><tbody>${suc.map(tr).join("")}</tbody></table></div></div></div><p class="section-note">After ranking, use the Source button beside a lever to change the actual input → rebuild → check Build History to see the measured effect on projected net worth and success rate.</p></div>`;
}

function chatMessageHtml(m) {
  const role = m.role === "user" ? "user" : "assistant";
  const label = role === "user" ? "You" : m.pending ? "Plan Chat" : "Plan Chat";
  const source = m.source
    ? `<div class="chat-source">Source: ${esc(m.source)}</div>`
    : "";
  return `<div class="chat-msg ${role}"><div class="chat-meta">${esc(label)}</div>${esc(m.content || "")}${source}</div>`;
}

function renderWorkbenchStressHtml() {
  let html = '<div class="wb-stress-suite">';
  html +=
    '<details open><summary><b>Probability Analysis (Monte Carlo)</b><span class="small"> engine mode, trial count, and volatility settings</span></summary>' +
    analysisFrame(renderMonteCarloOptions(), "stress") +
    "</details>";
  html +=
    '<details><summary><b>Survivor / Early Death</b><span class="small"> mortality ages, survivor filing status, and account rollover</span></summary>' +
    analysisFrame(renderSurvivorStress(), "stress") +
    "</details>";
  if (optionalFunctionEnabled("long_term_care_stress")) {
    html +=
      '<details><summary><b>Long-Term Care</b><span class="small"> annual care cost, duration, and coverage benefit</span></summary>' +
      analysisFrame(renderLtcStress(), "stress") +
      "</details>";
  }
  if (optionalFunctionEnabled("divorce_qdro")) {
    html +=
      '<details><summary><b>Divorce Planning</b><span class="small"> account transfer, alimony, and asset division</span></summary>' +
      analysisFrame(renderDivorceOptions(), "stress") +
      "</details>";
  }
  html += "</div>";
  return html;
}
function renderWorkbenchLeverEditorHtml() {
  if (!planningLeversBaselineReady())
    return '<p class="small" style="color:var(--muted)">Build reports once to unlock lever estimates in this panel.</p><div class="pane-actions"><button class="btn primary" type="button" data-requires-app="1" onclick="runBuild(false)">Build Reports</button></div>';
  const lrows = planningLeverRows();
  const inp = planningLeverInputs;
  function srcBtn(r) {
    return r.sourceStep
      ? `<button class="btn tiny source-jump" type="button" data-step-id="${esc(r.sourceStep)}">${esc(r.source)}</button>`
      : "—";
  }
  function inputCell(r) {
    return `<span class="lever-input-wrap"><input class="compact-input lever-test-input" value="${esc(inp[r.key])}" onchange="setPlanningLeverInput('${escJs(r.key)}',this.value)"><small class="lever-unit">${esc(r.unit)}</small></span>`;
  }
  const trs = lrows
    .map(
      (r) =>
        `<tr><td><b>${esc(r.lever)}</b><div class="small">${esc(r.note)}</div></td><td>${srcBtn(r)}</td><td>${inputCell(r)}</td><td>${fmtMoney(r.tnw)}</td><td>${fmtPct(r.success)}</td></tr>`,
    )
    .join("");
  return `<div class="wb-lever-editor"><p class="small">Test amounts resize estimates without changing the plan. Use Source to open the page where the actual value is changed — save and rebuild to confirm the effect.</p><div class="lot-table-wrap"><table class="lot-table planning-lever-table"><thead><tr><th>Lever</th><th>Source</th><th>Test amount</th><th>Est. Δ TNW</th><th>Est. Δ success</th></tr></thead><tbody>${trs}</tbody></table></div><div class="pane-actions" style="margin-top:8px"><button class="btn" type="button" data-step-id="distribution_strategy">Open Distribution Strategy &rarr;</button></div></div>`;
}

function planningWorkbenchContext() {
  return {
    esc: esc,
    escJs: escJs,
    fmtMoney: fmtMoney,
    fmtPct: fmtPct,
    renderMain: renderMain,
    showMessage: showMessage,
    setStep: setStep,
    getActiveStep: () => activeStep,
    getDirty: () => dirty,
    getRows: () => rows,
    getPlanningLeverInputs: () => planningLeverInputs,
    getBuildHistory: () => buildHistory,
    getLastBuildSummary: () => lastBuildSummary,
    loadBuildHistory: loadBuildHistory,
    rowsForStep: rowsForStep,
    stepIdForRow: stepIdForRow,
    stepTitleById: stepTitleById,
    humanLabel: humanLabel,
    displayValueForInput: displayValueForInput,
    scenarioActiveOverrideItems: scenarioActiveOverrideItems,
    planningLeverRows: planningLeverRows,
    renderWorkbenchLeverEditorHtml: renderWorkbenchLeverEditorHtml,
    renderScenarios: renderScenarios,
    renderWorkbenchStressHtml: renderWorkbenchStressHtml,
    confirm: function (msg, opts) {
      return showInAppConfirm(msg, opts);
    },
    prompt: function (msg, def, opts) {
      return showInAppPrompt(msg, def, opts);
    },
  };
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
function renderBuildImpactPage() {
  loadBuildHistory();
  const unsaved = hasUnsavedPlanChanges();
  let promptBar = "";
  if (unsaved && buildHistory.length > 0)
    promptBar =
      '<div class="section-note warning build-snapshot-prompt"><b>You have unsaved changes.</b> Take a snapshot now to preserve the current state before rebuilding. <button class="btn" type="button" data-requires-app="1" onclick="takeBuildSnapshot()">Take Snapshot</button></div>';
  const headerActions =
    '<div class="pane-actions"><button class="btn" type="button" data-requires-app="1" onclick="takeBuildSnapshot()">Take Snapshot</button> <button class="btn danger" type="button" data-requires-app="1" onclick="revertLastBuildChanges()">Revert User Changes</button> <button class="btn" data-requires-app="1" data-download="1" onclick="downloadWithBuild(\'/api/xlsx\',\'Workbook\')">Download Workbook</button> <button class="btn" data-requires-app="1" data-download="1" onclick="downloadWithBuild(\'/api/pdf\',\'PDF\')">Download PDF</button> <button class="btn primary" type="button" data-step-id="review">Back to Download Reports</button></div>';
  if (!buildHistory.length)
    return (
      '<div class="build-impact"><div class="impact-panel">' +
      promptBar +
      "<h3>No build history yet</h3><p>Download your workbook or PDF from the Download Reports step to see before/after impact here, or take a snapshot to record the current state.</p>" +
      headerActions +
      "</div></div>"
    );
  const allNw = buildHistory
    .map((e) => e.kpi && e.kpi.inheritable_nw)
    .filter((v) => v !== null && v !== undefined && Number.isFinite(Number(v)))
    .map(Number);
  const allTax = buildHistory
    .map((e) => e.kpi && e.kpi.lifetime_tax)
    .filter((v) => v !== null && v !== undefined && Number.isFinite(Number(v)))
    .map(Number);
  const allMc = buildHistory
    .map((e) => e.kpi && e.kpi.mc_success)
    .filter((v) => v !== null && v !== undefined && Number.isFinite(Number(v)))
    .map(Number);
  function heatRange(vals, higher) {
    if (!vals.length)
      return function () {
        return 0.5;
      };
    const mn = Math.min.apply(null, vals),
      mx = Math.max.apply(null, vals);
    if (mn === mx)
      return function () {
        return higher ? 1 : 0;
      };
    return function (v) {
      return higher ? (v - mn) / (mx - mn) : (mx - v) / (mx - mn);
    };
  }
  const heat = {
    nwHeat: heatRange(allNw, true),
    taxHeat: heatRange(allTax, false),
    mcHeat: heatRange(allMc, true),
  };
  let historyHtml = "";
  buildHistory.forEach(function (entry, idx) {
    historyHtml += buildHistoryEntryHtml(entry, idx === 0, heat);
  });
  const latestImpact =
    planningWorkbenchBuildImpactHtml() + latestBuildImpactHtml(buildHistory[0]);
  return (
    '<div class="build-impact"><div class="impact-panel">' +
    promptBar +
    '<h3>Impact & Build History</h3><p class="small">Up to ' +
    BUILD_HISTORY_MAX +
    " builds and snapshots. Dials are heat-mapped: green = best across all entries, red = worst. Post-Tax Inheritance (PTI) is projected net worth minus the embedded taxes heirs would owe on pre-tax accounts and unrealized gains.</p>" +
    headerActions +
    latestImpact +
    '<div class="build-history-list">' +
    historyHtml +
    "</div></div></div>"
  );
}
function buildSessionSummaryHtml() {
  return renderBuildImpactPage();
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
function isEditable(r) {
  return (
    r &&
    !r.is_header &&
    !r.is_comment &&
    r.label &&
    !rowIsRetiredScenarioHomeDuplicate(r)
  );
}
function isRequired(r) {
  return String(r.schema?.required || "").toUpperCase() === "TRUE";
}
function valOf(r) {
  return dirty.has(r.row_index) ? dirty.get(r.row_index) : r.value || "";
}
function isMissing(r) {
  return isEditable(r) && isRequired(r) && String(valOf(r) || "").trim() === "";
}
function norm(s) {
  return String(s || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_");
}
function hasAny(s, terms) {
  s = norm(s);
  return terms.some((t) => s.includes(norm(t)));
}
function section(r, s) {
  return r.section === s;
}
function optionalFunctionEnabled(labelName) {
  const row = rows.find(
    (r) =>
      isEditable(r) &&
      r.section === "Optional Functions" &&
      norm(r.label) === norm(labelName),
  );
  if (!row) return false;
  const v = String(valOf(row) || "")
    .trim()
    .toUpperCase();
  return ["TRUE", "YES", "1", "ON", "ENABLED"].includes(v);
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
function helocModuleEnabled() {
  return sectionFlagEnabled("HELOC", "Setup", "heloc_enabled");
}
function ltcLifePolicyModuleEnabled() {
  return sectionFlagEnabled("Hybrid LTC", "Settings", "enabled");
}
function rowIsRetirementWellness(r) {
  const lbl = norm(r.label);
  const sub = norm(r.subsection || "");
  return (
    r.section === "healthcare" &&
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
function homeValueLabelIsCanonical(label) {
  const l = norm(label);
  return (
    l === "home_value" ||
    l === "house_value" ||
    l === "value_as_of_plan_start" ||
    l === "current_home_value" ||
    l === "current_value" ||
    l === "market_value" ||
    /^value_\d{1,2}_\d{1,2}_\d{4}$/.test(l)
  );
}
function rowIsCanonicalHomeValue(r) {
  return (
    String(r.section || "").trim() === "Other Assets" &&
    norm(r.subsection || "") === "home" &&
    homeValueLabelIsCanonical(r.label)
  );
}
function rowIsRetiredScenarioHomeDuplicate(r) {
  const sec = String(r.section || "").trim(),
    sub = norm(r.subsection || ""),
    lbl = norm(r.label);
  return (
    sec === "Scenarios" &&
    sub === "sell_home" &&
    (lbl === "home_basis" ||
      lbl === "home_sale_price" ||
      homeValueLabelIsCanonical(r.label))
  );
}
function rowIsCanonicalHomeBasis(r) {
  return (
    String(r.section || "").trim() === "Other Assets" &&
    norm(r.subsection || "") === "home" &&
    norm(r.label) === "home_basis"
  );
}
function rowIsBaseHomeSaleInput(r) {
  const sec = String(r.section || "").trim();
  const sub = norm(r.subsection || "");
  const lbl = norm(r.label);
  return (
    rowIsCanonicalHomeValue(r) ||
    (sec === "Other Assets" &&
      sub === "home" &&
      (lbl.startsWith("home_sale_") || lbl === "home_basis")) ||
    (sec === "Model Constants" && sub === "home_sale")
  );
}
function rowIsStressSellHomeInput(r) {
  return (
    String(r.section || "").trim() === "Scenarios" &&
    norm(r.subsection || "") === "sell_home" &&
    !rowIsRetiredScenarioHomeDuplicate(r)
  );
}
function rowIsHomeSaleAssumption(r) {
  return rowIsBaseHomeSaleInput(r) || rowIsStressSellHomeInput(r);
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
function homeSaleActivationYearRow(stepId = "") {
  const baseYear = baseHomeSaleYearRow();
  const scenarioYear = stressHomeSaleYearRow();
  if (stepId === "scenarios_stress") return scenarioYear || baseYear || null;
  return baseYear || scenarioYear || null;
}

function visibleAssetSpecialRow(r) {
  if (
    ["Equity Compensation", "DAF", "Education Funding"].includes(r.section) &&
    !optionalFunctionEnabled(ROW_MODULE_GATES[r.section].key)
  )
    return false;
  if (r.section === "Hybrid LTC" && !ltcLifePolicyModuleEnabled()) return false;
  return true;
}
function rowIsDivorceScenario(r) {
  return (
    r.section === "Scenarios" &&
    /^Demo_Divorce|^Divorce_/i.test(String(r.subsection || ""))
  );
}
function rowIsMonteCarlo(r) {
  return (
    r.section === "Model Constants" && norm(r.subsection) === "monte_carlo"
  );
}
function rowIsEconomyScenario(r) {
  return (
    r.section === "Scenarios" &&
    ["high_inflation", "low_return"].includes(norm(r.subsection))
  );
}
function rowIsLifeInsurancePolicy(r) {
  return (
    r.section === "Insurance In Force" &&
    /^life(_|$)/i.test(String(r.subsection || "").trim())
  );
}
function rawRowsForStep(id) {
  return rows.filter(isEditable).filter((r) => {
    const lbl = norm(r.label),
      sub = norm(r.subsection),
      sec = r.section;
    switch (id) {
      case "household_people":
        return (
          sec === "Household" &&
          hasAny(r.label, [
            "name",
            "dob",
            "state",
            "filing_status",
            "retirement",
            "mortality",
            "survivor",
          ])
        );
      case "retirement_wellness":
        return rowIsRetirementWellness(r);
      case "income_work":
        return (
          (sec === "Cashflow" &&
            ((sub === "earned_income" &&
              [
                "annual_earned_income",
                "earned_income_start_year",
                "earned_income_annual_increase",
                "entity_type",
                "ytd_remainder_earned_income_override",
              ].includes(lbl)) ||
              sub === "self_employment" ||
              sub === "retirement_contributions")) ||
          sec === "Payroll Tax"
        );
      case "income_retirement":
        return sec === "Income Streams" || sec === "Social Security";
      case "spending_core":
        return (
          (sec === "Cashflow" &&
            sub === "spending" &&
            lbl !== "daf_annual_contribution" &&
            lbl !== "annual_spending_base_year") ||
          (sec === "Economic Assumptions" &&
            sub === "" &&
            lbl === "inflation_general") ||
          (sec === "Model Constants" &&
            sub === "retirement" &&
            lbl === "spending_freeze_year")
        );
      case "spending_travel_extras":
        return false;
      case "spending_mortgage_events":
        return (
          (sec === "Cashflow" && sub === "mortgage") ||
          (sec === "Other Assets" && sub === "home") ||
          (sec === "Model Constants" && sub === "home_sale") ||
          (sec === "Housing" &&
            [
              "current_home",
              "next_step_1",
              "next_step_2",
              "home_improvements",
            ].includes(sub))
        );
      case "assets_home_cash":
        return sec === "Other Assets" && sub === "cash";
      case "assets_special":
        return (
          (sec === "Other Assets" && sub.startsWith("other_asset")) ||
          (sec === "HSA Policy" && sub !== "window") ||
          [
            "Education Funding",
            "Equity Compensation",
            "Note Receivable",
            "Hybrid LTC",
          ].includes(sec)
        );
      case "estate":
        return (
          sec === "Estate Planning" ||
          (sec === "Insurance In Force" && !rowIsLifeInsurancePolicy(r))
        );
      case "annuity_death_benefits":
        return (
          sec === "Annuity Death Benefits" ||
          (sec === "Insurance In Force" && rowIsLifeInsurancePolicy(r))
        );
      case "allocation_policy":
        return (
          (sec === "Model Constants" && sub === "allocation") ||
          (sec === "Asset Class Assumptions" && sub === "global")
        );
      case "allocation_assets":
        return (
          (sec === "Asset Allocation Policy" &&
            sub === "global" &&
            [
              "allocation_selection_mode",
              "allocation_mode",
              "use_allocation_optimizer",
              "holding_period_allocation_enabled",
              "holding_period_floor_strength",
              "real_loss_aware_risk_aversion",
              "real_loss_aware_weight",
            ].includes(lbl)) ||
          (sec === "Asset Allocation Policy" &&
            sub !== "global" &&
            lbl === "target_pct") ||
          (sec === "Asset Class Optimizer Controls" &&
            [
              "selection_action",
              "alternate_asset_class",
              "optimizer_override_pct",
            ].includes(lbl))
        );
      case "capital_market":
        return false;
      case "market_pricing":
        return false;
      case "economic_tax_assumptions":
        return (
          !rowIsHomeSaleAssumption(r) &&
          (sec === "Economic Assumptions" ||
            sec === "Account Policy" ||
            sec === "Payroll Tax" ||
            (sec === "healthcare" && !rowIsRetirementWellness(r)) ||
            (sec === "Model Constants" &&
              ["retirement", "capital_gains"].includes(sub) &&
              lbl !== "spending_freeze_year"))
        );
      case "scenarios":
        return (
          (sec === "Scenarios" && !rowIsDivorceScenario(r)) ||
          (sec === "Model Constants" && sub === "home_sale") ||
          (sec === "Other Assets" &&
            sub === "home" &&
            (lbl.startsWith("home_sale_") ||
              lbl === "home_basis" ||
              homeValueLabelIsCanonical(r.label)))
        );
      case "monte_carlo_options":
        return (
          rowIsMonteCarlo(r) || hasAny(r.label, ["monte_carlo", "simulation"])
        );
      case "divorce_options":
        return rowIsDivorceScenario(r);
      case "state_residency":
        return sec === "State Comparison";
      case "heloc_strategy":
        return sec === "HELOC";
      case "entity_charitable":
        return (sec === "Cashflow" && sub === "s_corp") || sec === "DAF";
      case "survivor_stress":
        return (
          sec === "Household" && hasAny(r.label, ["survivor", "mortality"])
        );
      case "ltc_stress":
        return sec === "Hybrid LTC";
      case "withdrawal_strategy":
        return sec === "Withdrawal Policy" && sub !== "roth_conversion";
      case "optional_functions":
        return sec === "Optional Functions";
      case "roth_conversion":
        return (
          (sec === "Withdrawal Policy" &&
            sub === "roth_conversion" &&
            lbl !== "roth_irmaa_cap") ||
          (sec === "Model Constants" && sub === "roth_conversion") ||
          (sec === "Model Constants" &&
            sub === "irmaa" &&
            lbl === "irmaa_annual_inflator")
        );
      case "all_assumptions":
        return true;
      case "assumption_signoff":
        return false;
      case "review":
        return false;
      default:
        return false;
    }
  });
}
function fieldNumericValue(row) {
  const raw = String(valOf(row) || "").replace(/[$,%\s,]/g, "");
  const n = Number(raw);
  return Number.isFinite(n) ? n : 0;
}
function rowValueIsMeaningful(row, state) {
  const raw = String(valOf(row) || "").trim();
  if (state && state.listAlways) return true;
  if (raw === "") return false;
  const clean = raw.replace(/[$,%\s,]/g, "").toLowerCase();
  if (["0", "0.0", "0.00", "false", "no", "none", "off"].includes(clean))
    return false;
  return true;
}
function assetActionForSubsection(subsection) {
  const a = selectionActionRows().find(
    (x) => norm(x.subsection) === norm(subsection),
  );
  return rowActionValue(a);
}
const ROW_MODULE_GATES = {
  "Education Funding": {
    key: "education_funding_529",
    label: "Education Funding optional workbook module",
  },
  "Equity Compensation": {
    key: "equity_compensation",
    label: "Equity Compensation optional workbook module",
  },
  "Insurance In Force": {
    key: "existing_life_insurance",
    label: "Existing Life Insurance optional workbook module",
  },
  DAF: { key: "charitable_giving", label: "Charitable Giving optional workbook module" },
};
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
  if (ROW_MODULE_GATES[sec]) {
    const { key: flag, label } = ROW_MODULE_GATES[sec];
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
function rowBuildUsageState(row, stepId = "") {
  if (!row) return { active: true };
  const optional = optionalModuleState(row);
  if (optional) return optional;
  const l = norm(row.label),
    s = String(row.section || ""),
    sub = norm(row.subsection || "");
  if (
    s === "Social Security" &&
    l === "monthly_pia_at_fra_today_dollars" &&
    fieldNumericValue(row) <= 0
  )
    return {
      active: false,
      reason:
        "Monthly at FRA/PIA is blank or zero, so the build uses the age-67 (Full Retirement Age) entry from this person's benefit table instead.",
      activation:
        "Reveal this inactive value and enter a nonzero monthly FRA/PIA amount to override the benefit-table entry.",
      effect:
        "Can materially change projected Social Security income, Roth conversion room, Medicare IRMAA exposure, lifetime taxes, portfolio withdrawals, survivor income, and terminal net worth.",
      listAlways: true,
    };
  if (
    s === "Cashflow" &&
    sub === "spending" &&
    l === "core_spending_manual_growth_rate" &&
    coreSpendingGrowthMode() !== "manual_override"
  )
    return {
      active: false,
      reason: "Core spending is set to CPI/general inflation mode.",
      activation:
        "Change Core Spending Increase Method to Manual spending increase override.",
      effect:
        "Would change annual lifestyle spending growth, which can materially affect portfolio withdrawals, lifetime taxes, Monte Carlo success, and terminal net worth.",
    };
  if (
    (s === "Other Assets" &&
      sub === "home" &&
      l.startsWith("home_sale_") &&
      l !== "home_sale_year") ||
    (s === "Model Constants" && sub === "home_sale")
  ) {
    const yr = baseHomeSaleYearRow();
    if (!yr || fieldNumericValue(yr) <= 0)
      return {
        active: false,
        reason: "No home sale year is active for the base plan.",
        activation: "Enter a Base Plan Home Sale Year.",
        effect:
          "Base home sale assumptions change headline Build Impact metrics: home equity timing, sale taxes/costs, reinvested proceeds, future housing, liquidity, lifetime taxes, and terminal net worth.",
        listAlways: l !== "home_sale_price",
      };
  }
  if (
    rowIsStressSellHomeInput(row) &&
    l !== "home_sale_year" &&
    l !== "planned_home_sale_year"
  ) {
    const yr = stressHomeSaleYearRow();
    if (!yr || fieldNumericValue(yr) <= 0)
      return {
        active: false,
        reason: "No Sell Home stress-test year is active.",
        activation:
          "Enter a Sell Home stress-test year. These rows affect the Scenario Analysis sheet, not the headline Build Impact cards.",
        effect:
          "Scenario-only sell-home assumptions change workbook scenario/stress outputs. They do not change base-plan terminal net worth unless you also set the Base Plan Home Sale Year.",
        listAlways: l !== "home_sale_price",
      };
  }
  if (
    s === "Cashflow" &&
    sub === "mortgage" &&
    l === "real_estate_tax_annual_adjustment_pct"
  ) {
    const tax = rows.find(
      (x) =>
        isEditable(x) &&
        x.section === "Cashflow" &&
        norm(x.subsection) === "mortgage" &&
        norm(x.label) === "annual_real_estate_taxes",
    );
    if (!tax || fieldNumericValue(tax) <= 0)
      return {
        active: false,
        reason:
          "Annual Real Estate Taxes is zero, so the annual adjustment percentage has nothing to adjust.",
        activation: "Enter a nonzero Annual Real Estate Taxes amount.",
        effect:
          "Would increase or decrease future property-tax cash flow, withdrawals, taxes, and terminal net worth.",
      };
  }
  if (s === "Model Constants" && sub === "monte_carlo") {
    const mode = mcEngineModeValue();
    const advancedOnly = new Set([
      "mc_sensitivity_simulations",
      "stochastic_tax_brackets",
      "stochastic_irmaa",
      "healthcare_cost_shocks",
      "healthcare_shock_annual_prob",
      "healthcare_shock_mean_cost",
      "recenter_regime_returns",
      "stochastic_inflation",
      "inflation_sigma",
      "return_inflation_correlation",
      "return_serial_correlation",
    ]);
    if (mode === "quick_vectorized" && advancedOnly.has(l))
      return {
        active: false,
        reason: "Monte Carlo is set to Simple / Quick Vectorized mode.",
        activation:
          "Switch Monte Carlo Engine to Complex / Advanced Exact Scalar.",
        effect:
          "Would affect advisor-ready probability of success, downside ranges, tax/IRMAA stochasticity, Wellness shocks, sensitivity grids, and build time.",
        listAlways: true,
      };
  }
  if (s === "Asset Allocation Policy" && l === "target_pct") {
    const mode = allocationSelectionMode(),
      action = assetActionForSubsection(row.subsection);
    if (allocationModeIsComputed(mode))
      return {
        active: false,
        reason:
          "A computed allocation mode is selected, so saved user target percentages are reference-only.",
        activation: "Choose Use user-specified allocation.",
        effect:
          "Would replace the computed allocation with the user target mix, changing expected return/risk, drift analysis, ETF ideas, Monte Carlo results, and terminal net worth.",
        listAlways: true,
      };
    if (action === "exclude")
      return {
        active: false,
        reason: "This asset class is set to Exclude.",
        activation:
          "Change the selection action to Include or Consider alternate first.",
        effect:
          "Would allow this class into the active allocation target and can change optimizer/user target allocations and risk results.",
      };
  }
  if (
    s === "Asset Class Optimizer Controls" &&
    l === "alternate_asset_class" &&
    assetActionForSubsection(row.subsection) !== "consider_alternate_first"
  )
    return {
      active: false,
      reason: "Selection action is not Consider alternate first.",
      activation:
        "Change Selection to Consider alternate first for this asset class.",
      effect:
        "Would credit an existing asset/source against this class before recommending new liquid exposure.",
    };
  if (
    s === "Asset Class Optimizer Controls" &&
    l === "optimizer_override_pct" &&
    allocationSelectionMode() !== "optimizer_recommendation"
  )
    return {
      active: false,
      reason:
        "User-specified allocation mode is selected; optimizer overrides are ignored.",
      activation: "Choose Use allocation optimizer recommendation.",
      effect:
        "If a full 100% override is entered in optimizer mode, it replaces the computed optimizer target and can change allocation, risk, and projected outcomes.",
    };
  if (s === "Asset Allocation Policy" && l === "holding_period_floor_strength") {
    const globalRow = rows.find(
      (x) =>
        isEditable(x) &&
        x.section === "Asset Allocation Policy" &&
        norm(x.subsection) === "global" &&
        norm(x.label) === "holding_period_allocation_enabled",
    );
    const globalOn =
      String(globalRow ? valOf(globalRow) : "NO").toUpperCase() === "YES" ||
      String(globalRow ? valOf(globalRow) : "").toUpperCase() === "TRUE";
    if (!globalOn)
      return {
        active: false,
        reason:
          "Holding-Period Allocation Enabled (above) is off, so near-term/long-horizon floors are not applied.",
        activation: "Turn on Holding-Period Allocation Enabled above.",
        effect:
          "Scales how strongly near-term liquid balance is floored toward Cash and durable balance toward growth classes on the optimizer/max-Sharpe recommendation modes.",
        listAlways: true,
      };
  }
  if (
    s === "Asset Allocation Policy" &&
    (l === "real_loss_aware_risk_aversion" || l === "real_loss_aware_weight") &&
    allocationSelectionMode() !== "real_loss_aware"
  )
    return {
      active: false,
      reason:
        "Holding-period real-loss-aware allocation is not the selected allocation mode, so this tuning value is unused.",
      activation:
        "Choose Use holding-period real-loss-aware allocation as the allocation mode.",
      effect:
        "Tunes the per-holding-period-bucket solve that mode uses (mean-variance risk aversion, and the weight of the added real-loss-probability penalty).",
      listAlways: true,
    };
  if (s === "Account Policy" && l === "reinvest_dividends") {
    const globalRow = rows.find(
      (x) =>
        isEditable(x) &&
        x.section === "Economic Assumptions" &&
        norm(x.label) === "reinvest_dividends_default",
    );
    const globalOn =
      String(globalRow ? valOf(globalRow) : "NO").toUpperCase() === "YES" ||
      String(globalRow ? valOf(globalRow) : "").toUpperCase() === "TRUE";
    if (globalOn)
      return {
        active: false,
        reason:
          "Reinvest Dividends Default (global) is turned on, so every investment account reinvests dividends regardless of this per-account setting.",
        activation:
          "Turn off Reinvest Dividends Default above to set per-account overrides.",
        effect:
          "This account would only reinvest dividends independently once the global default is off.",
        listAlways: true,
      };
  }
  if (s === "HSA Policy" && sub === "withdrawals") {
    const modeRow = rows.find(
      (x) =>
        isEditable(x) &&
        x.section === "HSA Policy" &&
        norm(x.subsection) === "withdrawals" &&
        norm(x.label) === "hsa_withdrawal_mode",
    );
    const mode = String(modeRow ? valOf(modeRow) : "spend_as_needed")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_");
    if (
      ["hsa_withdrawal_pct", "hsa_annual_spend_pct"].includes(l) &&
      !["annual_pct", "annual_percent"].includes(mode)
    )
      return {
        active: false,
        reason: "HSA withdrawal mode is not annual percentage.",
        activation: "Change HSA withdrawal mode to annual_pct.",
        effect:
          "Would force annual HSA withdrawals and can change taxable income, HSA depletion, portfolio withdrawals, and terminal net worth.",
      };
    if (
      [
        "hsa_withdrawal_start_year",
        "hsa_withdrawal_end_year",
        "withdrawal_window",
      ].includes(l) &&
      !["annual_pct", "annual_percent", "smooth_window", "window"].includes(
        mode,
      )
    )
      return {
        active: false,
        reason: "HSA withdrawal mode is spend as needed.",
        activation:
          "Change HSA withdrawal mode to annual_pct or smooth_window.",
        effect:
          "Would impose a specific HSA drawdown schedule that can affect cash-flow funding and account depletion timing.",
      };
  }
  if (s === "Withdrawal Policy" && sub === "roth_conversion") {
    const policy = rothPolicyValue();
    const none = [
        "none",
        "off",
        "disabled",
        "no_voluntary_conversions",
      ].includes(policy),
      fixed = policy === "fixed_dollar" || policy === "fixed_amount",
      bracket =
        policy === "fill_to_bracket" ||
        policy === "fill_current_bracket" ||
        policy === "fill_target_bracket",
      irmaa = policy === "fill_to_irmaa" || policy === "irmaa_guarded",
      opt =
        policy.includes("optimize") ||
        policy.includes("optimizer") ||
        policy === "balanced_retirement";
    if (none && l !== "roth_conversion_policy")
      return {
        active: false,
        reason: "Roth Conversion Policy is set to no voluntary conversions.",
        activation: "Choose a Roth conversion policy other than none/off.",
        effect:
          "Would enable voluntary conversions that can change lifetime taxes, future RMD pressure, IRMAA exposure, survivor taxes, and terminal/after-tax net worth.",
        listAlways: true,
      };
    if (l === "roth_fixed_annual_amount" && !fixed && !opt)
      return {
        active: false,
        reason:
          "The active Roth policy does not use a fixed annual conversion amount.",
        activation:
          "Choose Fixed-dollar conversion or an optimizer policy that can use a fixed amount.",
        effect:
          "Would add or size annual Roth conversions, changing taxable income, Roth balances, RMDs, IRMAA, and terminal net worth.",
      };
    if (
      [
        "roth_bracket_strategy",
        "roth_target_bracket_rate",
        "roth_headroom_usage_pct",
      ].includes(l) &&
      !bracket &&
      !opt
    )
      return {
        active: false,
        reason: "The active Roth policy does not fill to a tax bracket.",
        activation: "Choose Fill to bracket or an optimizer policy.",
        effect:
          "Would cap or size conversions by bracket headroom, affecting current taxes, future RMDs, IRMAA, and after-tax wealth.",
      };
    if (
      [
        "roth_optimize_terminal_weight",
        "roth_optimize_lifetime_tax_weight",
        "roth_tax_discount_rate",
        "roth_objective_mode",
        "estate_tax_objective_mode",
        "legacy_objective_mode",
        "future_tax_rate_stress_pct",
        "future_tax_risk_weight",
        "inheritance_tax_burden_weight",
        "heir_ordinary_tax_rate_assumption_pct",
        "pre_tax_bequest_penalty_pct",
        "roth_bequest_preference_bonus_pct",
        "survivor_tax_risk_weight",
      ].includes(l) &&
      !opt &&
      !bracket
    )
      return {
        active: false,
        reason:
          "The active Roth policy is not using optimizer or bracket calibration.",
        activation: "Choose an optimizer-style Roth policy.",
        effect:
          "Would change Roth strategy scoring, lifetime tax tradeoffs, survivor protection, estate/legacy weighting, and recommended conversions.",
      };
  }
  if (
    s === "Model Constants" &&
    sub === "irmaa" &&
    l === "irmaa_annual_inflator"
  ) {
    const policy = rothPolicyValue(),
      mode = irmaaModeValue();
    if (
      !["fill_to_irmaa", "irmaa_guarded"].includes(policy) &&
      IRMAA_OFF_MODES.includes(mode)
    )
      return {
        active: false,
        reason:
          "IRMAA guardrails are ignored/warn-only for the active Roth policy.",
        activation:
          "Choose Fill to IRMAA or set IRMAA Guardrail Behavior to a cap/avoidance mode.",
        effect:
          "Would change Medicare-premium threshold growth and can affect Roth conversion headroom, IRMAA warnings, lifetime taxes, and terminal net worth.",
      };
  }
  return { active: true };
}
function rowsForStep(id, opts = {}) {
  const rs = rawRowsForStep(id);
  if (opts && opts.includeInactive) return rs;
  return rs.filter(
    (r) =>
      rowBuildUsageState(r, id).active || inactiveEditReveals.has(r.row_index),
  );
}
function inactiveRowsForStep(id) {
  return rawRowsForStep(id)
    .map((r) => ({ row: r, state: rowBuildUsageState(r, id) }))
    .filter(
      (x) =>
        !x.state.active &&
        !x.state.optionalModuleOff &&
        rowValueIsMeaningful(x.row, x.state),
    );
}
function inactiveValueDisplay(row, state = {}) {
  if (state && state.suppressValue) return "retired value ignored";
  const v = displayValueForInput(row, valOf(row));
  return v === "" ? "blank" : v;
}
function revealInactiveRow(idx) {
  inactiveEditReveals.add(Number(idx));
  renderMain();
  setTimeout(() => {
    const el = document.querySelector(`[data-row="${idx}"]`);
    if (el) {
      el.focus();
      if (el.select) el.select();
    }
  }, 0);
}
function inactiveValuesPanel(stepId) {
  const skip = new Set([
    "start",
    "review",
    "build_impact",
    "detailed_results",
    "assumption_signoff",
  ]);
  if (skip.has(stepId) || !planLoaded) return "";
  const items = inactiveRowsForStep(stepId);
  const title = "Inactive values";
  if (!items.length) return "";
  const rowsHtml = items
    .slice(0, 12)
    .map(({ row, state }) => {
      const action = state.noReveal
        ? `<span class="small">${esc(state.actionLabel || "Edit the active source instead")}</span>`
        : `<button class="btn" type="button" onclick="revealInactiveRow(${row.row_index})">${esc(state.actionLabel || "Edit to activate")}</button>`;
      const label = state.displayLabel || humanLabel(row.label, row);
      return `<tr><td><b>${esc(label)}</b><div class="small">${esc(friendlyGroup(row))}</div></td><td>${esc(inactiveValueDisplay(row, state))}</td><td>${esc(formatAcronyms(state.reason || "This value is currently not consumed by the build."))}</td><td>${esc(formatAcronyms(state.activation || "Change the controlling setting for this page."))}</td><td>${esc(formatAcronyms(state.effect || fieldGuidance(row).impact))}</td><td>${action}</td></tr>`;
    })
    .join("");
  const more =
    items.length > 12
      ? `<p class="small">${items.length - 12} additional inactive value${items.length - 12 === 1 ? "" : "s"} are hidden from this summary. Use page search or All assumptions to review broader configuration.</p>`
      : "";
  return `<details class="inactive-values-panel" open><summary>${title}: ${items.length} saved value${items.length === 1 ? "" : "s"} not used by the next build</summary><div class="inactive-values-body"><p class="small">Inactive values are saved in Plan Data but are hidden as ordinary inputs because the current build settings will not consume them. Use the action column only when you intentionally want to change the controlling setting or value so the build starts using it.</p><div class="lot-table-wrap"><table class="lot-table inactive-values-table"><thead><tr><th>Inactive value</th><th>Saved value</th><th>Why inactive</th><th>What would activate it</th><th>Likely effect on impacts</th><th></th></tr></thead><tbody>${rowsHtml}</tbody></table></div>${more}</div></details>`;
}

const RECOMMENDATION_ENGINE_VERSION = "page_recommendations_v1";
const RECOMMENDATION_STEP_IDS = new Set([
  "roth_conversion",
  "allocation_assets",
  "allocation_policy",
  "spending_core",
  "income_retirement",
]);
function recRowValue(row) {
  return row
    ? String(displayValueForInput(row, valOf(row)) || valOf(row) || "").trim()
    : "";
}
function recStepRows(stepId) {
  try {
    return rowsForStep(stepId, { includeInactive: true }) || [];
  } catch (_e) {
    return [];
  }
}
function recFindStepRow(stepId, labels) {
  const wanted = (Array.isArray(labels) ? labels : [labels]).map(norm);
  return (
    recStepRows(stepId).find((r) => wanted.includes(norm(r.label))) ||
    rows.find((r) => isEditable(r) && wanted.includes(norm(r.label))) ||
    null
  );
}
function recFindBy(sectionName, subsectionName, labelName) {
  return (
    rows.find(
      (r) =>
        isEditable(r) &&
        String(r.section || "") === sectionName &&
        norm(r.subsection) === norm(subsectionName) &&
        norm(r.label) === norm(labelName),
    ) || null
  );
}
function recAdd(list, level, title, body, row, stepId, impact, actionLabel) {
  list.push({
    level: level || "info",
    title,
    body,
    row: row || null,
    stepId: stepId || activeStep,
    impact: impact || "",
    actionLabel: actionLabel || "Review input",
  });
}
function recYes(row) {
  const v = String(valOf(row) || "")
    .trim()
    .toLowerCase();
  return ["yes", "true", "1", "on", "enabled"].includes(v);
}
function jumpRecommendationSource(stepId, rowIndex) {
  if (rowIndex !== undefined && rowIndex !== null && rowIndex !== "")
    inactiveEditReveals.add(Number(rowIndex));
  setStep(stepId || activeStep);
  setTimeout(() => {
    let el = null;
    if (rowIndex !== undefined && rowIndex !== null && rowIndex !== "")
      el =
        document.querySelector(`[data-row="${rowIndex}"]`) ||
        document.getElementById("field-" + rowIndex);
    if (el) {
      if (el.scrollIntoView)
        el.scrollIntoView({ behavior: "smooth", block: "center" });
      if (el.focus) el.focus({ preventScroll: true });
      if (el.select) el.select();
    }
  }, 80);
}
function recommendationSourceButton(item) {
  const row = item.row;
  if (!row)
    return `<button class="btn tiny" type="button" data-step-id="${esc(item.stepId || activeStep)}">${esc(item.actionLabel || "Open page")}</button>`;
  return `<button class="btn tiny recommendation-source-jump" type="button" onclick="jumpRecommendationSource('${escJs(item.stepId || activeStep)}',${Number(row.row_index)})">${esc(item.actionLabel || "Review input")}</button>`;
}
function rothPageRecommendations() {
  const recs = [];
  const policy = recFindStepRow("roth_conversion", "roth_conversion_policy");
  const policyVal = String(policy ? valOf(policy) : "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_");
  const targetBracket = recFindStepRow("roth_conversion", [
    "roth_target_bracket_rate",
    "roth_conversion_target_bracket_base_year",
  ]);
  const irmaa = recFindStepRow("roth_conversion", "irmaa_guardrail_mode");
  const irmaaVal = String(irmaa ? valOf(irmaa) : "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_");
  const headroom = recFindStepRow("roth_conversion", "roth_headroom_usage_pct");
  const headroomPct = headroom ? parsePercentInput(valOf(headroom)) : 0;
  const fixed = recFindStepRow("roth_conversion", "roth_fixed_annual_amount");
  const fixedAmt = fixed ? fieldNumericValue(fixed) : 0;
  const end = recFindStepRow("roth_conversion", [
    "roth_conv_window_end_offset",
    "conversion_window_end_offset",
    "max_conversion_years",
  ]);
  if (!policy || !policyVal) {
    recAdd(
      recs,
      "warn",
      "Choose a Roth conversion policy",
      "A missing policy leaves the workbook without a clear voluntary-conversion strategy. Pick none, bracket-fill, IRMAA-guarded, fixed-dollar, or optimizer mode intentionally.",
      policy || targetBracket,
      "roth_conversion",
      "Changes current taxes, future RMDs, Medicare thresholds, survivor tax compression, and after-tax inheritance.",
      "Choose policy",
    );
  } else if (
    ["none", "off", "disabled", "no_voluntary_conversions"].includes(policyVal)
  ) {
    recAdd(
      recs,
      "info",
      "Run one bounded Roth comparison",
      "The current policy disables voluntary conversions. Keep that as the base case, but compare one bracket-fill or IRMAA-guarded build before ruling conversions out.",
      policy,
      "roth_conversion",
      "May raise current taxes while lowering lifetime taxes, RMDs, and survivor tax risk.",
      "Review policy",
    );
  } else if (
    irmaa &&
    ["ignore", "off", "none", "warn_only"].includes(irmaaVal)
  ) {
    recAdd(
      recs,
      "warn",
      "Add a hard Medicare IRMAA guardrail for final review",
      "The active Roth policy can generate useful tax savings, but warn-only/ignored IRMAA behavior may let conversions cross Medicare premium cliffs. Use an avoidance mode for an advisor-ready comparison.",
      irmaa,
      "roth_conversion",
      "Affects conversion size, Medicare premiums, lifetime tax, and cash-flow headroom.",
      "Review guardrail",
    );
  } else {
    recAdd(
      recs,
      "info",
      "Keep Roth tests bounded by a clear ceiling",
      `Policy ${recRowValue(policy)} is active. Confirm the bracket or IRMAA ceiling reflects the highest current-tax cost the household is willing to accept.`,
      targetBracket || irmaa || policy,
      "roth_conversion",
      "Keeps tax savings, terminal net worth, and Medicare-premium tradeoffs explainable.",
      "Review ceiling",
    );
  }
  if (
    headroom &&
    headroomPct >= 100 &&
    policyVal &&
    !["none", "off", "disabled", "no_voluntary_conversions"].includes(policyVal)
  ) {
    recAdd(
      recs,
      "info",
      "Consider leaving threshold headroom",
      "Headroom is set to 100%, which uses the full available bracket/IRMAA room. For final plans, a 90–95% guardrail can reduce accidental cliff exposure from dividends, interest, or data updates.",
      headroom,
      "roth_conversion",
      "Reduces risk of crossing a tax or Medicare threshold because of small income-estimate changes.",
      "Review headroom",
    );
  }
  if (fixed && fixedAmt > 0 && end && String(valOf(end) || "").trim() === "") {
    recAdd(
      recs,
      "warn",
      "Set a fixed-conversion window",
      "Fixed-dollar conversions are active but the window/end control appears blank. Define when conversions stop so the recommendation does not persist longer than intended.",
      end,
      "roth_conversion",
      "Changes the years where current taxes rise and future RMDs fall.",
      "Review window",
    );
  }
  return recs.slice(0, 4);
}
function allocationPageRecommendations(stepId) {
  const recs = [];
  const mode = allocationSelectionMode();
  const modeRow = allocationModeRow();
  if (mode === "user_target") {
    const total = allocationTargetTotalPct();
    if (Math.abs(total - 100) > 0.01) {
      recAdd(
        recs,
        "warn",
        "Balance active targets to 100%",
        "User-specified allocation is active, but included/alternate target rows total " +
          total.toFixed(2) +
          "%. Rebalance the target table before saving or building.",
        allocationTargetRows()[0] || modeRow,
        "allocation_assets",
        "Prevents misleading drift, expected-return, and Monte Carlo comparisons.",
        "Review targets",
      );
    } else {
      recAdd(
        recs,
        "info",
        "Compare the optimizer before finalizing the user target",
        "User-specified allocation is valid. Use the optimizer as a second opinion before locking the target mix for a final report.",
        modeRow,
        "allocation_assets",
        "Tests whether risk tolerance, glide path, human capital, and concentrated assets imply a different mix.",
        "Review mode",
      );
    }
  } else {
    if (optimizerOverrideHasEntries() && !optimizerOverrideValid()) {
      recAdd(
        recs,
        "warn",
        "Fix optimizer override total",
        "Optimizer override rows are partly filled but total " +
          optimizerOverrideTotalPct().toFixed(2) +
          "%. Complete them to 100% or clear all override cells to use the computed recommendation.",
        optimizerOverrideRows()[0] || modeRow,
        "allocation_assets",
        "Avoids accidentally replacing the optimizer with an invalid override.",
        "Review overrides",
      );
    } else {
      recAdd(
        recs,
        "info",
        "Document why the optimizer target is acceptable",
        "Optimizer mode is active. Confirm the supporting risk, glide path, capital-market preset, and concentration assumptions before relying on the computed target.",
        modeRow,
        "allocation_assets",
        "Makes allocation recommendations easier to defend in Build Impact and reports.",
        "Review allocation mode",
      );
    }
  }
  const cash = findTargetRow("Cash");
  if (cash && parsePercentInput(valOf(cash)) < 2 && mode === "user_target") {
    recAdd(
      recs,
      "info",
      "Check whether cash target supports the reserve floor",
      "Cash target is below 2%. Confirm separate cash-reserve rules are enough before reducing liquid ballast.",
      cash,
      "allocation_assets",
      "Can affect liquidity failures, rebalancing pressure, and downside comfort.",
      "Review cash target",
    );
  }
  const risk = recFindBy("Model Constants", "Allocation", "risk_tolerance");
  const glide = recFindBy("Model Constants", "Allocation", "glide_path");
  if (stepId === "allocation_policy" && risk) {
    recAdd(
      recs,
      "info",
      "Keep risk tolerance and glide path paired",
      "Risk tolerance should match the glide path used near retirement. Review both together when a plan is close to the retirement date.",
      risk,
      "allocation_policy",
      "Controls the optimizer recommendation and can affect Monte Carlo success and terminal value.",
      "Review risk input",
    );
  }
  if (stepId === "allocation_policy" && glide) {
    recAdd(
      recs,
      "info",
      "Confirm the glide path before final reports",
      "A glide path can de-risk over time; a static target keeps risk more constant. Choose deliberately before comparing stress results.",
      glide,
      "allocation_policy",
      "Changes age-based allocation and long-horizon risk/reward.",
      "Review glide path",
    );
  }
  return recs.slice(0, 4);
}
function spendingPageRecommendations() {
  const recs = [];
  const base = recFindStepRow("spending_core", "annual_spending_base_year");
  const growth = recFindStepRow("spending_core", "core_spending_growth_mode");
  const manual = recFindStepRow(
    "spending_core",
    "core_spending_manual_growth_rate",
  );
  const freeze = recFindStepRow("spending_core", "spending_freeze_year");
  const inflation = recFindStepRow("spending_core", "inflation_general");
  const baseAmt = base ? fieldNumericValue(base) : 0;
  if (!base || baseAmt <= 0) {
    recAdd(
      recs,
      "warn",
      "Enter a realistic core spending base",
      "Core spending is blank or zero, so the projection cannot reliably estimate withdrawals, taxes, or plan risk. Use Spending Analysis or budget lines to seed it.",
      base || growth,
      "spending_core",
      "Spending is usually one of the largest drivers of terminal net worth and probability of success.",
      "Review spending base",
    );
  } else {
    recAdd(
      recs,
      "info",
      "Reconcile core spending with actuals before building",
      "Core spending is " +
        fmtMoney(baseAmt) +
        ". Compare it with recent transactions and budget lines before treating a report as final.",
      base,
      "spending_core",
      "Aligns the 30-year model with real household behavior and reduces false precision.",
      "Review spending base",
    );
  }
  if (growth && norm(valOf(growth)) === "manual_override") {
    const manualPct = manual ? parsePercentInput(valOf(manual)) : 0;
    const cpi = inflation ? parsePercentInput(valOf(inflation)) : NaN;
    if (Number.isFinite(cpi) && manualPct > cpi + 1) {
      recAdd(
        recs,
        "warn",
        "Explain why spending grows faster than CPI",
        "Manual spending growth is more than one point above general inflation. That may be intentional, but it should be documented before final review.",
        manual,
        "spending_core",
        "Raises withdrawals, taxes, and Monte Carlo failure risk over the retirement horizon.",
        "Review growth rate",
      );
    } else {
      recAdd(
        recs,
        "info",
        "Document the manual spending-growth assumption",
        "Manual spending growth overrides CPI. Add notes or confirm the rate so future comparisons are interpretable.",
        manual || growth,
        "spending_core",
        "Changes long-term spending, withdrawals, and terminal net worth.",
        "Review growth mode",
      );
    }
  } else if (growth) {
    recAdd(
      recs,
      "info",
      "Use a scenario for non-CPI spending stress",
      "Core spending currently follows CPI/general inflation. For pressure testing, keep the base case stable and use Scenarios for a higher-spending case.",
      growth,
      "spending_core",
      "Keeps base-plan spending clean while still testing lifestyle risk.",
      "Review growth mode",
    );
  }
  if (freeze && fieldNumericValue(freeze) > 0) {
    recAdd(
      recs,
      "info",
      "Confirm the spending freeze year is intentional",
      "A spending freeze can improve long-term results materially. Confirm it represents real lifestyle behavior, not a placeholder.",
      freeze,
      "spending_core",
      "Can raise terminal net worth and success probability by stopping inflation growth after the freeze year.",
      "Review freeze year",
    );
  }
  return recs.slice(0, 4);
}
function socialSecurityPageRecommendations() {
  const recs = [];
  const claims = recStepRows("income_retirement").filter(
    (r) => norm(r.label) === "claim_age",
  );
  const survivor =
    recFindBy(
      "Social Security",
      "Policy",
      "survivor_benefit_uses_deceased_claim_age",
    ) ||
    recFindBy("Social Security", "Policy", "survivor_pct_of_higher_benefit");
  const early = claims.find(
    (r) => fieldNumericValue(r) > 0 && fieldNumericValue(r) < 67,
  );
  const not70 = claims.find(
    (r) => fieldNumericValue(r) >= 67 && fieldNumericValue(r) < 70,
  );
  if (early) {
    recAdd(
      recs,
      "warn",
      "Stress-test early claiming",
      "At least one claim age is before full retirement age. Compare a later-claim scenario before finalizing because early claiming can permanently reduce survivor income.",
      early,
      "income_retirement",
      "Affects annual income, Roth conversion room, taxes, withdrawals, survivor benefits, and terminal value.",
      "Review claim age",
    );
  } else if (not70) {
    recAdd(
      recs,
      "info",
      "Compare delaying the higher earner to 70",
      "A claim age is between full retirement age and 70. Test delaying the higher benefit to age 70, especially when survivor protection matters.",
      not70,
      "income_retirement",
      "May improve longevity and survivor income but can increase bridge withdrawals before claiming.",
      "Review claim age",
    );
  } else if (claims.length) {
    recAdd(
      recs,
      "info",
      "Document why age-70 claiming is acceptable",
      "Claim ages appear set to 70. Confirm the bridge years are affordable and the Roth window before Social Security is intentional.",
      claims[0],
      "income_retirement",
      "Delaying benefits can improve inflation-linked income and survivor protection.",
      "Review claim age",
    );
  }
  if (
    survivor &&
    !recYes(survivor) &&
    norm(survivor.label).includes("survivor_benefit_uses")
  ) {
    recAdd(
      recs,
      "warn",
      "Review survivor benefit treatment",
      "Survivor benefit handling affects the income floor for the surviving member. Confirm this setting before relying on survivor stress outputs.",
      survivor,
      "income_retirement",
      "Changes survivor cash flow, withdrawals, taxes, and downside risk.",
      "Review survivor setting",
    );
  }
  return recs.slice(0, 4);
}
function pageRecommendationsForStep(stepId) {
  if (!RECOMMENDATION_STEP_IDS.has(stepId) || !planLoaded) return [];
  try {
    if (stepId === "roth_conversion") return rothPageRecommendations();
    if (stepId === "allocation_assets" || stepId === "allocation_policy")
      return allocationPageRecommendations(stepId);
    if (stepId === "spending_core") return spendingPageRecommendations();
    if (stepId === "income_retirement")
      return socialSecurityPageRecommendations();
    return [];
  } catch (e) {
    return [
      {
        level: "warn",
        title: "Recommendations unavailable",
        body: "The page-local recommendation engine could not interpret the current values on this page. Save and reload, then review the source fields manually.",
        stepId,
        row: null,
        impact: String((e && e.message) || e),
        actionLabel: "Open page",
      },
    ];
  }
}
function pageRecommendationsHtml(stepId) {
  const items = pageRecommendationsForStep(stepId);
  if (!items.length) return "";
  const rowsHtml = items
    .map(
      (item) =>
        `<div class="recommendation-card ${esc(item.level || "info")}"><div><span class="recommendation-level">${esc(item.level || "info")}</span><h4>${esc(item.title)}</h4><p>${esc(formatAcronyms(item.body))}</p>${item.impact ? `<p class="small"><b>Why it matters:</b> ${esc(formatAcronyms(item.impact))}</p>` : ""}</div><div class="recommendation-actions">${recommendationSourceButton(item)}</div></div>`,
    )
    .join("");
  return `<section class="page-recommendations" data-contract="${RECOMMENDATION_ENGINE_VERSION}"><div class="page-recommendations-head"><div><span class="eyebrow">Page recommendations</span><h3>Suggested reviews before the next build</h3><p class="small">Explainable suggestions only — nothing is changed automatically. Each item links back to the input that controls the recommendation.</p></div></div><div class="page-recommendation-list">${rowsHtml}</div></section>`;
}
function stepStats(id) {
  const rs = rowsForStep(id);
  const req = rs.filter(isRequired);
  const missing = req.filter(isMissing);
  const d = rs.filter((r) => dirty.has(r.row_index));
  if (id === "spending_travel_extras" && travelExtrasChanged) d.push({});
  if (id === "assets_home_cash" && liquidityChanged) d.push({});
  if (id === "roth_conversion" && forcedConversionsChanged) d.push({});
  if (id === "holdings" && holdingsChanged) d.push({});
  if (
    [
      "spending_core",
      "spending_setup",
      "spending_travel",
      "spending_travel_extras",
      "spending_mortgage_events",
      "retirement_wellness",
    ].includes(id) &&
    (rulesChanged || taxBudgetChanged || budgetLinesChanged)
  )
    d.push({});
  if (
    id === "ytd_transactions" &&
    (ytdTransactionsChanged || ytdAccountsChanged)
  )
    d.push({});
  if (id === "ytd_transactions" && ytdTransactionsChanged) d.push({});
  return { required: req, missing, dirtY: d, dirty: d };
}
function overallStats() {
  const req = rows
    .filter(isEditable)
    .filter((r) => rowBuildUsageState(r, "all_assumptions").active)
    .filter(isRequired);
  const missing = req.filter(isMissing);
  return { total: req.length, missing, done: req.length - missing.length };
}
function unsavedChangeCount() {
  return (
    dirty.size +
    (holdingsChanged ? 1 : 0) +
    (liabilitiesChanged ? 1 : 0) +
    (travelExtrasChanged ? 1 : 0) +
    (liquidityChanged ? 1 : 0) +
    (forcedConversionsChanged ? 1 : 0) +
    (ytdTransactionsChanged ? 1 : 0) +
    (ytdAccountsChanged ? 1 : 0) +
    (rulesChanged ? 1 : 0) +
    (taxBudgetChanged ? 1 : 0) +
    (budgetLinesChanged ? 1 : 0)
  );
}
function planStateArtifactsReady() {
  const a = (buildPreflight && buildPreflight.artifacts) || {};
  return !!(
    a.workbook &&
    a.workbook.exists &&
    a.results_model &&
    a.results_model.exists &&
    a.summary &&
    a.summary.exists
  );
}
function planStateFresh() {
  return !!(
    buildPreflight &&
    buildPreflight.current &&
    !unsavedChangeCount() &&
    lastBuildOk
  );
}
function updatePlanStateBanner() {
  const el = document.getElementById("planStateBanner");
  if (!el) return;
  const unsaved = unsavedChangeCount();
  const stats = planLoaded ? overallStats() : { missing: [] };
  let cls = "plan-state-banner";
  let title = "Open a plan";
  let detail = "Start a new plan or open the saved local database.";
  let action = "";
  if (planLoaded) {
    if (unsaved) {
      cls += " warn";
      title = "Unsaved edits";
      detail = `${unsaved} pending change${unsaved === 1 ? "" : "s"} must be saved before reports are current.`;
      action = `<button class="btn primary" type="button" data-requires-app="1" onclick="saveAll(true)">Save Changes</button>`;
    } else if (stats.missing && stats.missing.length) {
      cls += " warn";
      title = "Required inputs missing";
      detail = `${stats.missing.length} required value${stats.missing.length === 1 ? "" : "s"} still need review before advisor-ready output.`;
      action = `<button class="btn" type="button" data-step-id="review">Review</button>`;
    } else if (!planStateArtifactsReady()) {
      cls += " warn";
      title = "No current report package";
      detail =
        "Build reports to create the workbook, PDF, dashboard, and Results Explorer model.";
      action = `<button class="btn primary" type="button" data-requires-app="1" onclick="runBuild(false)">Build Reports</button>`;
    } else if (!planStateFresh()) {
      cls += " warn";
      title = "Reports may be stale";
      detail =
        "Saved plan data or build status changed after the last confirmed build.";
      action = `<button class="btn primary" type="button" data-requires-app="1" onclick="runBuild(false)">Rebuild</button>`;
    } else {
      cls += " ok";
      title = "Reports current";
      detail = "Saved plan data matches the latest local build outputs.";
      action = `<button class="btn" type="button" data-step-id="detailed_results">Open Results</button>`;
    }
  }
  el.className = cls;
  el.innerHTML = `<div><b>${esc(title)}</b><span>${esc(detail)}</span></div><div class="plan-state-actions"><span>${esc(planSource || "Local database")}</span>${action}</div>`;
}
async function refreshBuildStatus() {
  try {
    const r = await api("/api/build/status");
    if (r && r.success !== false) {
      buildPreflight = r;
      lastBuildOk = !!r.current && !unsavedChangeCount();
      updatePlanStateBanner();
      setAppControls(appReady);
      return r;
    }
  } catch (_e) {}
  updatePlanStateBanner();
  return null;
}
function updateUnsaved() {
  const u = document.getElementById("unsavedStatus");
  const has = !!unsavedChangeCount();
  u.classList.toggle("hidden", !has);
  lastBuildOk = lastBuildOk && !has;
  document.getElementById("planSource").textContent = planSource;
  const sb = document.getElementById("saveChangesBtn");
  if (sb) sb.disabled = !has;
  updatePlanStateBanner();
}
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
        "Build Reports, Download Workbook, and Download PDF save the working copy before preflight and report generation.",
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

function reportsUiContext() {
  return {
    esc: esc,
    getActiveStep: () => activeStep,
    getDetailedResultsNavOpen: () => detailedResultsNavOpen,
    setDetailedResultsNavOpenValue: (v) => {
      detailedResultsNavOpen = !!v;
    },
    getDetailedResultsData: () => detailedResultsData,
    getDetailedResultsLoading: () => detailedResultsLoading,
    getDetailedResultsError: () => detailedResultsError,
    getDetailedResultSheetLoading: () => detailedResultSheetLoading,
    getDetailedResultSheetError: () => detailedResultSheetError,
    getActiveDetailedSheet: () => activeDetailedSheet,
    getDetailResultsSearchText: () => detailResultsSearchText,
    loadDetailedResults: loadDetailedResults,
    loadDetailedResultSheet: loadDetailedResultSheet,
    detailedProgressHtml: detailedProgressHtml,
    chooseDefaultDetailedSheet: chooseDefaultDetailedSheet,
    detailedSheetByName: detailedSheetByName,
    getColumnGroupOpen: (key) => detailedColumnGroupsOpen[key],
    cacheChart: cacheChart,
  };
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
function renderSteps() {
  const box = document.getElementById("steps");
  let html = "";
  const stats = overallStats();
  const pct = stats.total ? Math.round(100 * (stats.done / stats.total)) : 0;
  document.getElementById("progressBar").style.width = pct + "%";
  const _mpb = document.getElementById("mobileProgressBar");
  if (_mpb) _mpb.style.width = pct + "%";
  document.getElementById("progressLabel").textContent = planLoaded
    ? `${pct}% complete`
    : "Open local plan";
  document.getElementById("requiredLabel").textContent = planLoaded
    ? `${stats.missing.length} required missing`
    : "";
  const q = String(navSearchText || "")
    .trim()
    .toLowerCase();
  let stepNumber = 0;
  const allSteps = visibleSteps();
  function stepButton(s) {
    stepNumber += 1;
    const st = stepStats(s.id);
    const cls =
      s.id === activeStep
        ? "active"
        : st.missing.length
          ? "missing"
          : st.required.length
            ? "complete"
            : "";
    const navDisabled =
      !planLoaded &&
      ![
        "start",
        "system_configuration",
        "detailed_results",
        "planning_workbench",
        "reports_and_review",
      ].includes(s.id);
    let badge = "";
    const reportStale =
      [
        "review",
        "build_impact",
        "detailed_results",
        "reports_and_review",
      ].includes(s.id) &&
      planLoaded &&
      !planStateFresh();
    const spendingWarn =
      s.id === "ytd_transactions" &&
      typeof window.getSpendingDivergencePct === "function" &&
      Math.abs(Number(window.getSpendingDivergencePct())) > 0.03;
    if (st.missing.length)
      badge = `<span class="badge bad">${st.missing.length}</span>`;
    else if (st.dirty.length) badge = `<span class="badge dirty">Edited</span>`;
    else if (spendingWarn)
      badge = `<span class="nav-badge nav-badge--warn">!</span>`;
    else if (reportStale) badge = `<span class="badge warn">Stale</span>`;
    else if (st.required.length) badge = `<span class="badge ok">OK</span>`;
    return `<button class="stepbtn ${cls}" type="button" data-step-id="${s.id}" ${navDisabled ? "disabled" : ""} ><span class="num">${stepNumber}</span><span><span class="step-title">${esc(s.title)}</span><br><span class="step-desc">${esc(s.desc)}</span></span>${badge}</button>`;
  }
  const groups = [];
  let cg = null;
  allSteps.forEach((s) => {
    if (!s.group) return;
    if (!cg || cg.name !== s.group) {
      cg = { name: s.group, steps: [] };
      groups.push(cg);
    }
    cg.steps.push(s);
  });
  groups.forEach((g) => {
    const isActive = g.steps.some((s) => s.id === activeStep);
    const gMissing = g.steps.reduce(
      (n, s) => n + stepStats(s.id).missing.length,
      0,
    );
    const badge = gMissing ? `<span class="badge bad">${gMissing}</span>` : "";
    const open = isActive ? "open" : "";
    html += `<details class="nav-group" ${open}><summary class="nav-group-summary">${esc(g.name)}${badge}</summary><div class="nav-group-steps">`;
    g.steps.forEach((s) => {
      html += stepButton(s);
      // Workspace parents expose their tabs as indented nav children, so the
      // left nav is a complete map of every reachable destination and clicking
      // a child opens the workspace on that tab.
      if (s.id === "reports_and_review") {
        html += `<div class="nav-subtabs">`;
        REPORTS_TABS.forEach(function (tab) {
          const isActiveTab =
            activeStep === "reports_and_review" && reportsActiveTab === tab;
          html += `<button class="nav-subtab${isActiveTab ? " active" : ""}" type="button" onclick="goToReportsTab('${escJs(tab)}')">${esc(tab)}</button>`;
        });
        html += `</div>`;
      } else if (s.id === "distribution_strategy") {
        const activeTab = getStrategyTab("distribution_strategy");
        html += `<div class="nav-subtabs">`;
        STRATEGY_TABS.distribution_strategy.forEach(function (tab) {
          const isActiveTab =
            activeStep === "distribution_strategy" && activeTab === tab;
          html += `<button class="nav-subtab${isActiveTab ? " active" : ""}" type="button"${!planLoaded ? " disabled" : ""} onclick="goToStrategyTab('distribution_strategy','${escJs(tab)}')">${esc(tab)}</button>`;
        });
        html += `</div>`;
      }
    });
    html += `</div></details>`;
  });
  box.innerHTML = html;
  updateUnsaved();
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
  const open = document.body.classList.toggle("help-open");
  const btn = document.querySelector("#helpPane .help-toggle");
  if (btn) btn.setAttribute("aria-expanded", open ? "true" : "false");
}
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
function toIsoDateValue(value) {
  const v = String(value || "").trim();
  if (!v) return "";
  if (/^\d{4}-\d{2}-\d{2}$/.test(v)) return v;
  let m = v.match(/^(\d{4})[\/\-](\d{1,2})[\/\-](\d{1,2})$/);
  if (m) {
    return `${m[1].padStart(4, "0")}-${m[2].padStart(2, "0")}-${m[3].padStart(2, "0")}`;
  }
  m = v.match(/^(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{2,4})$/);
  if (m) {
    let y = m[3];
    if (y.length === 2) y = (Number(y) > 40 ? "19" : "20") + y;
    return `${y.padStart(4, "0")}-${m[1].padStart(2, "0")}-${m[2].padStart(2, "0")}`;
  }
  if (/^\d{4}$/.test(v)) return `${v}-01-01`;
  return v;
}
function isDateField(r) {
  const l = norm(r.label);
  return (
    (l.includes("dob") || l.includes("date")) &&
    !l.includes("year") &&
    !l.includes("end_year")
  );
}
function decimalTrim(text) {
  if (DASHBOARD_UTILS.decimalTrim) return DASHBOARD_UTILS.decimalTrim(text);
  return String(text)
    .replace(/\.0+$/, "")
    .replace(/(\.\d*?)0+$/, "$1");
}
function numberFromDisplay(value) {
  if (DASHBOARD_UTILS.numberFromDisplay)
    return DASHBOARD_UTILS.numberFromDisplay(value);
  const raw = String(value ?? "").trim();
  if (!raw) return null;
  const neg = /^\(.*\)$/.test(raw) || /^\s*-/.test(raw);
  const cleaned = raw.replace(/[,$%\s]/g, "").replace(/[()]/g, "");
  const n = Number(cleaned);
  if (!Number.isFinite(n)) return null;
  return neg ? -Math.abs(n) : n;
}
function formatNumberValue(value, maxDecimals = 2, minDecimals = 0) {
  if (DASHBOARD_UTILS.formatNumberValue)
    return DASHBOARD_UTILS.formatNumberValue(value, maxDecimals, minDecimals);
  const n = numberFromDisplay(value);
  if (n === null) return String(value ?? "");
  const opts = {
    useGrouping: false,
    minimumFractionDigits: minDecimals,
    maximumFractionDigits: maxDecimals,
  };
  return n.toLocaleString(undefined, opts);
}
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
function currencyRaw(value) {
  const n = numberFromDisplay(value);
  return n === null ? String(value ?? "").trim() : decimalTrim(String(n));
}
function percentRaw(value) {
  const n = numberFromDisplay(value);
  return n === null ? String(value ?? "").trim() : decimalTrim(String(n));
}
function currencyDisplay(value, maxDecimals = 2) {
  if (DASHBOARD_UTILS.currencyDisplay)
    return DASHBOARD_UTILS.currencyDisplay(value, maxDecimals);
  const n = numberFromDisplay(value);
  if (n === null) return String(value ?? "");
  const max = Math.max(2, Math.min(6, Number(maxDecimals) || 2));
  const opts = {
    minimumFractionDigits: Number.isInteger(n) ? 0 : 2,
    maximumFractionDigits: max,
  };
  return (n < 0 ? "-" : "") + "$" + Math.abs(n).toLocaleString(undefined, opts);
}
function moneyNegativeClass(value) {
  const n = numberFromDisplay(value);
  return n !== null && n < 0 ? " negative-money" : "";
}
function moneyHtml(value) {
  const text = currencyDisplay(value);
  return `<span class="money-value${moneyNegativeClass(value)}">${esc(text)}</span>`;
}
function budgetMoneyInputValue(value) {
  if (value === undefined || value === null || String(value).trim() === "")
    return "";
  return currencyDisplay(value);
}
function focusBudgetMoney(el) {
  if (el) el.value = currencyRaw(el.value);
}
function blurBudgetMoney(el) {
  if (el) el.value = budgetMoneyInputValue(el.value);
  if (taxBudgetChanged) renderMain();
}
function budgetMoneyNumber(value) {
  const n = numberFromDisplay(value);
  return n === null ? 0 : n;
}
function updateTaxBudgetMoney(catId, field, el) {
  updateTaxBudget(catId, field, budgetMoneyNumber(el && el.value));
}
function updateCategoryDetailMoney(lineId, field, el, catId) {
  updateCategoryDetail(
    lineId,
    field,
    String(budgetMoneyNumber(el && el.value)),
    catId,
  );
}
function updateLargeDiscLineMoney(lineId, field, el) {
  updateLargeDiscLine(lineId, field, String(budgetMoneyNumber(el && el.value)));
}
function percentDisplay(value, decimals = 0) {
  if (DASHBOARD_UTILS.percentDisplay)
    return DASHBOARD_UTILS.percentDisplay(value, decimals);
  const n = numberFromDisplay(value);
  if (n === null) return String(value ?? "");
  const d = Math.max(0, Math.min(6, Number(decimals) || 0));
  return (
    n.toLocaleString(undefined, {
      minimumFractionDigits: d,
      maximumFractionDigits: d,
    }) + "%"
  );
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
function valueKind(r) {
  const units = String(r?.units || "");
  const u = norm(units);
  const l = norm(r?.label);
  const type = String(r?.schema?.type || "").toLowerCase();
  if (r && norm(r.label) === "down_payment") return "percent";
  if (r && l === "heloc_repayment_years") return "number";
  if (r && l === "tlh_transaction_cost_bps") return "number";
  if (
    !r ||
    isDateField(r) ||
    ["boolean", "choice", "secret", "path"].includes(type)
  )
    return "plain";
  if (/^(yes\/no|true\/false)$/i.test(units)) return "plain";
  if (["percent", "pct", "percentage"].includes(type)) return "percent";
  if (["dollars", "currency", "usd", "money"].includes(type)) return "currency";
  if (
    units.includes("%") ||
    u.includes("pct") ||
    u.includes("percent") ||
    l.endsWith("pct") ||
    l.includes("percentage") ||
    l.includes("rate") ||
    l.includes("return") ||
    l.includes("volatility") ||
    l.includes("correlation") ||
    l.includes("inflation") ||
    l.includes("cola")
  )
    return "percent";
  if (l.endsWith("_year")) return "number";
  if (u === "years" || u === "year" || u === "age") return "number";
  if (
    units.includes("$") ||
    u.includes("usd") ||
    u.includes("dollar") ||
    u.includes("money") ||
    hasAny(l, [
      "amount",
      "balance",
      "value",
      "price",
      "cost",
      "basis",
      "proceeds",
      "spending",
      "income",
      "salary",
      "bonus",
      "rent",
      "payment",
      "mortgage",
      "premium",
      "benefit",
      "contribution",
      "expense",
      "asset",
      "liability",
      "equity",
      "face_amount",
      "funding",
      "transfer",
      "taxable_income",
      "taxes",
      "tax",
      "exclusion",
      "sale_price",
      "purchase_price",
      "gross_sell",
      "net_sell",
      "capital_gain",
      "ltcg",
      "fmv",
      "fair_market_value",
      "market_value",
      "cashflow",
      "cash_flow",
      "insurance",
      "utilities",
    ])
  )
    return "currency";
  if (["year", "integer", "int", "number", "numeric"].includes(type))
    return "number";
  return "plain";
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
    filing_status: ["MFJ", "Single", "HOH", "MFS"],
    survivor_filing_status: ["Single", "HOH", "MFS"],
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
    hsa_withdrawal_mode: ["spend_as_needed", "annual_pct", "smooth_window"],
    city_type: ["urban", "suburban", "rural"],
    type: ["purchase", "rent"],
    allocation_selection_mode: [
      { value: "user_target", label: "Use user-specified allocation" },
      { value: "optimizer_recommendation", label: "Use allocation optimizer recommendation" },
      { value: "max_sharpe", label: "Use max-Sharpe allocation (risk-budgeted)" },
      { value: "tangency", label: "Use max-Sharpe allocation (pure tangency, no risk budget)" },
      { value: "real_loss_aware", label: "Use holding-period real-loss-aware allocation" },
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
function choiceValue(o) {
  return typeof o === "object" ? String(o.value ?? o.label ?? "") : String(o);
}
function choiceLabel(o) {
  return typeof o === "object" ? String(o.label ?? o.value ?? "") : String(o);
}
function storageValueForInput(row, value) {
  if (row && isDateField(row)) return toIsoDateValue(value);
  const kind = valueKind(row);
  if (kind === "currency") return currencyRaw(value);
  if (kind === "percent") return percentRaw(value);
  if (kind === "number")
    return decimalTrim(
      String(numberFromDisplay(value) ?? String(value ?? "").trim()),
    );
  return String(value ?? "");
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
function displayValueForInput(row, value) {
  if (row && isDateField(row)) return toIsoDateValue(value);
  // Some account-reference fields (e.g. home_sale_proceeds_account) are
  // schema-typed as currency/number even though their stored value is a
  // person/account token like "Member_2_Trust" — translate those before
  // falling into numeric formatting, which would otherwise blank them out.
  if (PERSON_VALUE_TOKEN_RE.test(String(value ?? "").trim()))
    return translatePersonValueLabel(value);
  const kind = valueKind(row);
  if (kind === "currency") return currencyDisplay(value);
  if (kind === "percent")
    return percentDisplay(value, percentDisplayDecimals(row, value));
  if (kind === "number")
    return formatNumberValue(
      value,
      numberDisplayDecimals(row, value),
      numberDisplayDecimals(row, value),
    );
  return translatePersonValueLabel(value);
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
function beginEdit(idx, el) {
  const row = rows.find((r) => r.row_index === idx);
  if (!row) return;
  showFieldHelp(idx);
  if (
    el &&
    el.tagName &&
    el.tagName.toLowerCase() === "input" &&
    !isDateField(row)
  ) {
    el.value = storageValueForInput(row, valOf(row));
  }
}
function finishEdit(idx, el) {
  const row = rows.find((r) => r.row_index === idx);
  if (!row || !el) return;
  const stored = storageValueForInput(row, el.value);
  editValue(idx, stored, el);
  if (el.tagName && el.tagName.toLowerCase() === "input" && !isDateField(row)) {
    el.value = displayValueForInput(row, stored);
  }
}
const FIELD_TOOLTIPS = {
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
};
function fieldTooltipHtml(lbl) {
  const tip = FIELD_TOOLTIPS[lbl];
  if (!tip) return "";
  return `<span class="field-tooltip" tabindex="0" title="${esc(tip)}" aria-label="Hint: ${esc(tip)}">?</span>`;
}
function fieldHtml(r) {
  const value = valOf(r);
  const missing = isMissing(r);
  const dirtyHere = dirty.has(r.row_index);
  const units = String(r.units || "").trim();
  const type = (r.schema?.type || "text").toLowerCase();
  const lblNorm = norm(r.label);
  const boolish =
    type === "boolean" ||
    /^(yes\/no|true\/false)$/i.test(units) ||
    /^(YES|NO|TRUE|FALSE)$/i.test(value);
  let control = "";
  if (
    lblNorm === "allocation_selection_mode" ||
    lblNorm === "allocation_mode"
  ) {
    const mode = allocationSelectionMode();
    control = `<select data-row="${r.row_index}" onchange="editValue(${r.row_index},this.value,this);renderMain()" onfocus="showFieldHelp(${r.row_index})"><option value="user_target" ${mode === "user_target" ? "selected" : ""}>Use user-specified allocation</option><option value="optimizer_recommendation" ${mode === "optimizer_recommendation" ? "selected" : ""}>Use allocation optimizer recommendation</option><option value="max_sharpe" ${mode === "max_sharpe" ? "selected" : ""}>Use max-Sharpe allocation (risk-budgeted)</option><option value="tangency" ${mode === "tangency" ? "selected" : ""}>Use max-Sharpe allocation (pure tangency, no risk budget)</option><option value="real_loss_aware" ${mode === "real_loss_aware" ? "selected" : ""}>Use holding-period real-loss-aware allocation</option></select>`;
  } else if (boolish) {
    const yes =
      String(value).toUpperCase() === "YES" ||
      String(value).toUpperCase() === "TRUE";
    control = `<label class="toggle-switch" data-row="${r.row_index}"><input type="checkbox" ${yes ? "checked" : ""} onchange="editValue(${r.row_index},this.checked?'YES':'NO',this)" onfocus="showFieldHelp(${r.row_index})"><span class="toggle-track" aria-hidden="true"></span><span class="toggle-text toggle-text-yes">YES</span><span class="toggle-text toggle-text-no">NO</span></label>`;
  } else if (type === "choice" || norm(units) === "choice") {
    const opts = choiceOptions(r);
    if (opts.length) {
      const cur = String(value || "").trim();
      const rerender =
        lblNorm === "core_spending_growth_mode" ||
        lblNorm === "roth_conversion_policy" ||
        lblNorm === "irmaa_guardrail_mode" ||
        lblNorm === "hsa_withdrawal_mode";
      control = `<select data-row="${r.row_index}" onchange="editValue(${r.row_index},this.value,this);${rerender ? "renderMain()" : ""}" onfocus="showFieldHelp(${r.row_index})">${opts
        .map((o) => {
          const ov = choiceValue(o),
            ol = choiceLabel(o);
          return `<option value="${esc(ov)}" ${norm(ov) === norm(cur) ? "selected" : ""}>${esc(translatePersonPlaceholders(formatAcronyms(ol.replace(/_/g, " "))))}</option>`;
        })
        .join("")}</select>`;
    } else {
      control = `<input type="text" data-row="${r.row_index}" value="${esc(String(value || ""))}" placeholder="${esc(r.schema?.default || "")}" oninput="editValue(${r.row_index},this.value,this)" onfocus="beginEdit(${r.row_index},this)" onblur="finishEdit(${r.row_index},this)">`;
    }
  } else {
    const inputType = isDateField(r) ? "date" : "text";
    const inputValue = displayValueForInput(r, value);
    control = `<input type="${inputType}" data-row="${r.row_index}" value="${esc(inputValue)}" placeholder="${esc(r.schema?.default || "")}" oninput="editValue(${r.row_index},this.value,this)" onfocus="beginEdit(${r.row_index},this)" onblur="finishEdit(${r.row_index},this)">`;
  }
  const note = formatAcronyms(r.schema?.description || r.notes || "");
  const req = missing ? '<span class="badge req">Required</span>' : "";
  const inactiveState = rowBuildUsageState(r, activeStep);
  const inactiveRevealed =
    inactiveEditReveals.has(r.row_index) && !inactiveState.active;
  const inactiveBadge = inactiveRevealed
    ? '<span class="badge warn">Inactive unless activated</span>'
    : "";
  const unit = units
    ? `<div class="unit">${esc(formatAcronyms(units))}</div>`
    : "";
  const negClass = valueKind(r) === "currency" ? moneyNegativeClass(value) : "";
  return `<div class="field ${missing ? "missing" : ""} ${dirtyHere ? "dirty" : ""} ${inactiveRevealed ? "inactive-edit" : ""}${negClass}" id="field-${r.row_index}" onclick="showFieldHelp(${r.row_index})"><div><div class="field-label">${esc(humanLabel(r.label, r))}${fieldLabelNoteHtml(r)}${fieldTooltipHtml(lblNorm)}</div><div class="field-meta">${req}${dirtyHere ? '<span class="badge dirty">Edited</span>' : ""}${inactiveBadge}</div></div><div>${control}${unit}${inactiveRevealed ? `<div class="unit">${esc(formatAcronyms(inactiveState.activation || "Change this value or its controlling setting to make it active in the build."))}</div>` : ""}</div></div>`;
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
function sortRowsByDependency(rs) {
  return (rs || []).slice().sort((a, b) => {
    const ka = dependencyRank(a.label) + norm(a.label),
      kb = dependencyRank(b.label) + norm(b.label);
    return ka.localeCompare(kb);
  });
}
function fieldFinderStepOrder(stepId) {
  const i = STEPS.findIndex((s) => s.id === stepId);
  return i < 0 ? 9999 : i;
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
  if (!rs.length)
    return '<div class="field-list"><p>No fields match.</p></div>';
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
  return html;
}
function renderFieldGroups(rs) {
  if (!rs.length)
    return '<div class="field-list"><p>No fields in this step.</p></div>';
  const groups = [];
  sortRowsByDependency(rs).forEach((r) => {
    const g = friendlyGroup(r);
    let group = groups.find((x) => x.name === g);
    if (!group) {
      group = { name: g, rows: [] };
      groups.push(group);
    }
    group.rows.push(r);
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
function parsePercentInput(value) {
  const raw = String(value ?? "").trim();
  if (!raw) return 0;
  const hasPct = raw.includes("%");
  const cleaned = raw.replace(/[,%$\s]/g, "");
  const n = Number(cleaned);
  if (!Number.isFinite(n)) return 0;
  return hasPct ? n : Math.abs(n) > 1 ? n : n * 100;
}
function findEditableRow(sectionName, subsectionName, labelName) {
  return rows
    .filter(isEditable)
    .find(
      (r) =>
        r.section === sectionName &&
        norm(r.subsection) === norm(subsectionName) &&
        norm(r.label) === norm(labelName),
    );
}
function allocationModeRow() {
  return (
    findEditableRow(
      "Asset Allocation Policy",
      "Global",
      "allocation_selection_mode",
    ) ||
    findEditableRow("Asset Allocation Policy", "Global", "allocation_mode") ||
    findEditableRow(
      "Asset Allocation Policy",
      "Global",
      "use_allocation_optimizer",
    )
  );
}
function allocationSelectionMode() {
  const r = allocationModeRow();
  const v = String(r ? valOf(r) : "user_target")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_");
  if (v.includes("tangency") || v === "pure_tangency" || v === "unconstrained_sharpe")
    return "tangency";
  if (v.includes("real_loss") || v.includes("loss_aware") || v === "holding_period_aware")
    return "real_loss_aware";
  if (v.includes("max_sharpe") || v === "sharpe" || v === "sharpe_optimal")
    return "max_sharpe";
  if (v.includes("optimizer") || v === "yes" || v === "true" || v === "auto")
    return "optimizer_recommendation";
  return "user_target";
}
// True for any mode where the plan is driven by a computed recommendation
// rather than the user's manually-entered target_pct rows.
function allocationModeIsComputed(mode) {
  return (mode || allocationSelectionMode()) !== "user_target";
}
function setAllocationSelectionMode(mode) {
  const r = allocationModeRow();
  if (!r) {
    showMessage(
      "Allocation mode row is missing. Reload the current plan once so defaults can be created, then try again.",
      "error",
    );
    return;
  }
  editValue(r.row_index, mode, null);
  renderMain();
}
function allocationModeHtml() {
  const mode = allocationSelectionMode();
  const modeButtons = [
    ["user_target", "Use user-specified allocation"],
    ["optimizer_recommendation", "Use allocation optimizer recommendation"],
    ["max_sharpe", "Use max-Sharpe allocation (risk-budgeted)"],
    ["tangency", "Use max-Sharpe allocation (pure tangency)"],
    ["real_loss_aware", "Use holding-period real-loss-aware allocation"],
  ];
  const activeLabel =
    modeButtons.find(([v]) => v === mode)?.[1] || "Using user-specified allocation";
  const r = allocationModeRow();
  const disabled = r ? "" : " disabled";
  const buttonsHtml = modeButtons
    .map(
      ([v, label]) =>
        `<button class="btn ${mode === v ? "primary" : ""}" type="button" onclick="setAllocationSelectionMode('${v}')"${disabled}>${esc(label)}</button>`,
    )
    .join("");
  return `<div class="holdings"><h3 class="group-title">Allocation Mode</h3><div class="section-note allocation-mode-panel" id="allocationModeNote">Active: ${esc(activeLabel)}. Choose the source below; the page then shows only controls for that source.<div class="table-actions">${buttonsHtml}</div>${r ? "" : '<p class="small">The CSV row for allocation_selection_mode was not found. Reload the current plan so required allocation rows are present.</p>'}</div></div>`;
}
function allocationOptimizerRecommendationHtml() {
  const risk = findEditableRow(
    "Model Constants",
    "Allocation",
    "risk_tolerance",
  );
  const glide = findEditableRow("Model Constants", "Allocation", "glide_path");
  const cash = findTargetRow("Cash");
  const hc = findEditableRow(
    "Model Constants",
    "Allocation",
    "human_capital_stability",
  );
  const infl = findEditableRow(
    "Model Constants",
    "Allocation",
    "inflation_sensitive_spending_pct",
  );
  const cap = findEditableRow(
    "Asset Class Assumptions",
    "Global",
    "capital_market_assumption_preset",
  );
  const horizon = findEditableRow(
    "Asset Class Assumptions",
    "Global",
    "capital_market_assumption_horizon_years",
  );
  return `<div class="section-note" id="allocationOptimizerExplanation"><b>Optimizer recommendation:</b> this is a second-opinion mix based on risk tolerance or auto risk score, age, withdrawal rate, years to retirement, human-capital stability, existing assets credited against class targets, concentration flags, enabled asset classes, capital-market assumptions, correlations, glide path, and inflation-sensitive spending. Consider it because it can reflect household-specific risk capacity and diversification relationships that a static mix cannot see.<br><br><b>Current inputs used by the optimizer:</b> risk tolerance ${esc(risk ? displayValueForInput(risk, valOf(risk)) : "auto")}; glide path ${esc(glide ? displayValueForInput(glide, valOf(glide)) : "default")}; cash target ${esc(cash ? displayValueForInput(cash, valOf(cash)) : "default")}; human-capital stability ${esc(hc ? displayValueForInput(hc, valOf(hc)) : "default")}; inflation-sensitive spending ${esc(infl ? displayValueForInput(infl, valOf(infl)) : "default")}; capital-market preset ${esc(cap ? displayValueForInput(cap, valOf(cap)) : "baseline")}; horizon ${esc(horizon ? displayValueForInput(horizon, valOf(horizon)) : "30")} years.</div>`;
}
function allocationTargetRows() {
  return rows
    .filter(isEditable)
    .filter(
      (r) =>
        r.section === "Asset Allocation Policy" &&
        norm(r.subsection) !== "global" &&
        norm(r.label) === "target_pct",
    );
}
function optimizerOverrideRows() {
  return rows
    .filter(isEditable)
    .filter(
      (r) =>
        r.section === "Asset Class Optimizer Controls" &&
        norm(r.subsection) !== "global" &&
        norm(r.label) === "optimizer_override_pct",
    );
}
function selectionActionRows() {
  return rows
    .filter(isEditable)
    .filter(
      (r) =>
        r.section === "Asset Class Optimizer Controls" &&
        norm(r.subsection) !== "global" &&
        norm(r.label) === "selection_action",
    );
}
function alternateAssetRows() {
  return rows
    .filter(isEditable)
    .filter(
      (r) =>
        r.section === "Asset Class Optimizer Controls" &&
        norm(r.subsection) !== "global" &&
        norm(r.label) === "alternate_asset_class",
    );
}
function assetCategory(asset) {
  const a = norm(asset);
  if (
    [
      "us_large_cap",
      "us_mid_cap",
      "us_small_cap",
      "international",
      "emerging_markets",
    ].includes(a)
  )
    return "Equity";
  if (
    [
      "bonds",
      "short_term_bonds",
      "tips",
      "municipal_bonds",
      "private_credit",
      "cash",
    ].includes(a)
  )
    return "Fixed income";
  return "Other";
}
function assetClassNamesForAllocation() {
  const names = [];
  function add(x) {
    x = String(x || "").trim();
    if (x && !names.some((n) => norm(n) === norm(x))) names.push(x);
  }
  allocationTargetRows().forEach((r) => add(r.subsection));
  selectionActionRows().forEach((r) => add(r.subsection));
  optimizerOverrideRows().forEach((r) => add(r.subsection));
  alternateAssetRows().forEach((r) => add(r.subsection));
  const order = { Equity: 0, "Fixed income": 1, Other: 2 };
  return names.sort(
    (a, b) =>
      order[assetCategory(a)] - order[assetCategory(b)] || a.localeCompare(b),
  );
}
function findAssetRow(assetClass, labels) {
  const key = norm(assetClass);
  return rows.find(
    (r) =>
      isEditable(r) &&
      r.section === "Asset Class Optimizer Controls" &&
      norm(r.subsection) === key &&
      labels.includes(norm(r.label)),
  );
}
function findTargetRow(assetClass) {
  const key = norm(assetClass);
  return allocationTargetRows().find((r) => norm(r.subsection) === key);
}
function rowActionValue(row) {
  const v = String(row ? valOf(row) : "include")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_");
  if (["exclude", "excluded", "no", "false", "disabled", "disable"].includes(v))
    return "exclude";
  if (
    [
      "consider_alternate",
      "consider_alternate_first",
      "alternate",
      "alternate_first",
      "alternative",
      "alternative_first",
    ].includes(v)
  )
    return "consider_alternate_first";
  return "include";
}
function setSelectionAction(idx, value) {
  editValue(idx, value, null);
  renderMain();
}
function selectionActionSelect(row, assetClass) {
  if (!row) return '<span class="small">Missing row</span>';
  const val = rowActionValue(row);
  return `<select aria-label="Selection action for ${esc(assetClass)}" onchange="setSelectionAction(${row.row_index},this.value)"><option value="include" ${val === "include" ? "selected" : ""}>Include</option><option value="exclude" ${val === "exclude" ? "selected" : ""}>Exclude</option><option value="consider_alternate_first" ${val === "consider_alternate_first" ? "selected" : ""}>Consider alternate first</option></select>`;
}
function normalizedAssetSourceName(x) {
  return String(x || "")
    .trim()
    .replace(/\s+/g, " ");
}
function addAltOption(list, name, group) {
  name = normalizedAssetSourceName(name);
  if (!name) return;
  if (!list.some((o) => norm(o.name) === norm(name)))
    list.push({ name, group });
}
function alternateAssetSourceOptions() {
  const opts = [];
  addAltOption(
    opts,
    "Guaranteed income + note receivable",
    "Built-in coverage sources",
  );
  addAltOption(opts, "Social Security", "Built-in coverage sources");
  addAltOption(opts, "Pension", "Built-in coverage sources");
  addAltOption(opts, "Annuities", "Built-in coverage sources");
  addAltOption(opts, "Note Receivable", "Built-in coverage sources");
  addAltOption(opts, "Home Equity", "Built-in coverage sources");
  addAltOption(opts, "Cash / checking", "Built-in coverage sources");
  rows.forEach((r) => {
    if (!r || !r.section) return;
    const sec = String(r.section || ""),
      sub = String(r.subsection || ""),
      lbl = norm(r.label),
      val = String(valOf(r) || "").trim();
    if (
      sec === "Other Assets" &&
      sub &&
      [
        "value",
        "face_value",
        "market_value",
        "current_value",
        "value_as_of_plan_start",
      ].includes(lbl)
    ) {
      if (val && val !== "0" && val !== "$0")
        addAltOption(
          opts,
          sub === "Home" ? "Home Equity" : sub,
          "Existing non-liquid / other assets",
        );
    }
    if (sec === "Note Receivable" && sub === "Summary" && lbl === "face_value")
      addAltOption(
        opts,
        "Note Receivable",
        "Existing non-liquid / other assets",
      );
  });
  try {
    const h = ensureHoldingRows();
    h.data.forEach((row) => {
      const sym = String(row.symbol || "").trim();
      if (sym) addAltOption(opts, `Holding: ${sym}`, "Current holdings");
    });
  } catch (_e) {}
  return opts;
}
function alternateSelect(row, assetClass, action) {
  if (!row) return '<span class="small">Missing row</span>';
  const opts = alternateAssetSourceOptions();
  const cur = String(valOf(row) || "").trim();
  const disabled = action !== "consider_alternate_first" ? " disabled" : "";
  let html = `<select aria-label="Existing asset to credit against ${esc(assetClass)} target" onchange="editValue(${row.row_index},this.value,this)"${disabled}><option value="" ${cur ? "" : "selected"}>No existing asset selected</option>`;
  let currentGroup = "";
  opts.forEach((o) => {
    if (o.group !== currentGroup) {
      if (currentGroup) html += "</optgroup>";
      currentGroup = o.group;
      html += `<optgroup label="${esc(currentGroup)}">`;
    }
    html += `<option value="${esc(o.name)}" ${norm(cur) === norm(o.name) ? "selected" : ""}>${esc(o.name)}</option>`;
  });
  if (currentGroup) html += "</optgroup>";
  html += "</select>";
  return html;
}
function targetPctInput(row, assetClass, action) {
  if (!row) return '<span class="small">Missing target row</span>';
  const disabled = action === "exclude" ? " disabled" : "";
  const label = "Target percent for " + assetClass;
  return `<input class="tiny" type="text" value="${esc(displayValueForInput(row, valOf(row)))}" aria-label="${esc(label)}" oninput="editValue(${row.row_index},this.value,this)" onfocus="beginEdit(${row.row_index},this)" onblur="finishEdit(${row.row_index},this)"${disabled}>`;
}
// Legacy regression marker: target_pct rows are inactive in optimizer mode and now appear in the Inactive values summary instead of the active allocation table.
function fmtPctCell(value) {
  const n = Number(value || 0);
  if (!Number.isFinite(n) || Math.abs(n) < 0.0000001)
    return '<span class="small">0.00%</span>';
  return (n * 100).toFixed(2) + "%";
}
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
    holdingsChanged: !!holdingsChanged,
    holdingsLen: String(holdingsText || "").length,
  });
}
function requestAllocationPreview() {
  // "allocation_assets" is the legacy standalone step id; the current
  // guided-steps UI hosts the Allocation & Location tab inside the combined
  // "distribution_strategy" step. Accept both so the preview actually loads
  // on the current UI instead of silently never firing.
  if (
    !planLoaded ||
    (activeStep !== "allocation_assets" && activeStep !== "distribution_strategy")
  )
    return;
  const key = allocationPreviewFingerprint();
  if (allocationPreviewLoading && allocationPreviewKey === key) return;
  if (
    allocationPreview &&
    allocationPreviewKey === key &&
    !allocationPreviewError
  )
    return;
  allocationPreviewKey = key;
  allocationPreviewLoading = true;
  allocationPreviewError = "";
  const seq = ++allocationPreviewSeq;
  api("/api/allocation-preview", {
    method: "POST",
    body: JSON.stringify({
      rows: allocationPreviewRowsForPost(),
      mode: allocationSelectionMode(),
    }),
  })
    .then((out) => {
      if (seq !== allocationPreviewSeq) return;
      allocationPreviewLoading = false;
      if (out && out.success !== false) {
        allocationPreview = out;
        allocationPreviewError = "";
      } else {
        allocationPreview = null;
        allocationPreviewError =
          (out && out.error) || "Allocation preview failed";
      }
    })
    .catch((e) => {
      if (seq !== allocationPreviewSeq) return;
      allocationPreviewLoading = false;
      allocationPreview = null;
      allocationPreviewError = e.message || String(e);
    })
    .finally(() => {
      if (
        seq === allocationPreviewSeq &&
        (activeStep === "allocation_assets" || activeStep === "distribution_strategy")
      )
        renderMain();
    });
}
function resetAllocationPreview() {
  allocationPreview = null;
  allocationPreviewKey = "";
  allocationPreviewError = "";
  allocationPreviewLoading = false;
  allocationPreviewSeq++;
}
function optimizerPreviewTarget(asset, kind) {
  const p = allocationPreview || {};
  const key = norm(asset);
  const src =
    kind === "total"
      ? p.optimizer_total_targets || {}
      : p.optimizer_liquid_targets || {};
  for (const [k, v] of Object.entries(src)) {
    if (norm(k) === key) return Number(v || 0);
  }
  return 0;
}
function activeOptimizerUsedTarget(asset) {
  const p = allocationPreview || {};
  const key = norm(asset);
  const src = p.selected_liquid_targets || {};
  for (const [k, v] of Object.entries(src)) {
    if (norm(k) === key) return Number(v || 0);
  }
  return optimizerPreviewTarget(asset, "liquid");
}
function optimizerPreviewStatusCell(asset, action) {
  if (allocationPreviewLoading)
    return '<span class="small">Calculating…</span>';
  if (allocationPreviewError)
    return `<span class="small bad">${esc(allocationPreviewError)}</span>`;
  if (!allocationPreview) {
    setTimeout(requestAllocationPreview, 0);
    return '<span class="small">Preview pending</span>';
  }
  const diag = allocationPreview.optimizer_diagnostics || {};
  const covered = (diag.covered_existing_asset_classes || []).some(
    (x) => norm(x) === norm(asset),
  );
  if (action === "exclude") return '<span class="badge bad">Excluded</span>';
  if (covered) return '<span class="badge ok">Covered by alternate</span>';
  const used = activeOptimizerUsedTarget(asset);
  if (used > 0) return '<span class="badge ok">Recommended</span>';
  return '<span class="small">No liquid target</span>';
}
function renderOptimizerPreviewNote() {
  if (allocationPreviewLoading)
    return '<div class="section-note" id="allocationPreviewNote"><b>Optimizer preview:</b> calculating from the current UI values…</div>';
  if (allocationPreviewError)
    return `<div class="section-note" id="allocationPreviewNote"><b>Optimizer preview unavailable:</b> ${esc(allocationPreviewError)}. Save/build still uses the backend calculation; this message only affects the on-screen preview.</div>`;
  if (!allocationPreview) {
    setTimeout(requestAllocationPreview, 0);
    return '<div class="section-note" id="allocationPreviewNote"><b>Optimizer preview:</b> waiting to calculate computed targets.</div>';
  }
  const mode =
    allocationPreview.optimizer_policy_mode || "optimizer_recommendation";
  const cov =
    allocationPreview.optimizer_diagnostics &&
    allocationPreview.optimizer_diagnostics.coverage_adjustments
      ? Object.keys(
          allocationPreview.optimizer_diagnostics.coverage_adjustments,
        ).length
      : 0;
  return `<div class="section-note" id="allocationPreviewNote"><b>Optimizer preview:</b> computed targets shown below are read-only and are not written into the user-defined allocation file. <b>Active target used</b> reflects optimizer overrides plus covered/excluded classes. Coverage adjustments detected: ${cov}. Policy mode: ${esc(mode)}.</div>`;
}
function renderAssetClassSelectionTable() {
  const names = assetClassNamesForAllocation();
  if (!names.length)
    return `<div class="holdings"><div class="section-note">Asset-class selection rows were not found. Reload the current plan so asset_class_optimizer_controls.csv can be backfilled with the compact selection policy rows.</div></div>`;
  const mode = allocationSelectionMode();
  const optMode = allocationModeIsComputed(mode);
  if (optMode) setTimeout(requestAllocationPreview, 0);
  let header = optMode
    ? `<tr><th>Subcategory</th><th>Asset class</th><th>Selection</th><th>Computed Optimizer Target %</th><th>Active Target Used %</th><th>Status</th><th>Existing asset/source credited to this class</th></tr>`
    : `<tr><th>Subcategory</th><th>Asset class</th><th>Selection</th><th>User Target %</th><th>Existing asset/source credited to this class</th></tr>`;
  let note;
  if (mode === "optimizer_recommendation") {
    note = `<div class="section-note"><b>Optimizer mode is active.</b> User target percentages are hidden because the next build will not use them; they are listed in Inactive values above when saved. The workbook uses the computed optimizer target, unless you enter a full optional optimizer override. Excluded rows and covered rows are removed from the active liquid target before the remaining recommendation is normalized.</div>${renderOptimizerPreviewNote()}`;
  } else if (mode === "max_sharpe") {
    note = `<div class="section-note"><b>Max-Sharpe (risk-budgeted) mode is active.</b> User target percentages are hidden because the next build will not use them. This mode keeps the same risk level as the optimizer recommendation (risk tolerance, glide path, guaranteed-income/home-equity coverage) but chooses the equity sleeve with the best risk-adjusted (Sharpe) return, using the same Selection-driven candidate classes as the optimizer recommendation (Excluded classes, and classes already covered by a mapped guaranteed-income/home-equity source, are left out); it does not support a manual override.</div>${renderOptimizerPreviewNote()}`;
  } else if (mode === "tangency") {
    note = `<div class="section-note"><b>Pure tangency mode is active.</b> User target percentages are hidden because the next build will not use them. This mode ignores risk tolerance and glide path entirely and solves for the single portfolio with the highest Sharpe ratio across the enabled/uncovered classes below (Excluded classes, and classes already covered by a mapped guaranteed-income/home-equity source, are left out); it does not support a manual override. Review the recommended risk level carefully before using it to drive the plan.</div>${renderOptimizerPreviewNote()}`;
  } else if (mode === "real_loss_aware") {
    note = `<div class="section-note"><b>Holding-period real-loss-aware mode is active.</b> User target percentages are hidden because the next build will not use them. This mode splits today's liquid balance into holding-period buckets from this household's own projected withdrawal schedule and solves each bucket separately across the enabled/uncovered classes below with an added real-loss-probability penalty (Excluded classes, and classes already covered by a mapped guaranteed-income/home-equity source, are left out); it does not support a manual override.</div>${renderOptimizerPreviewNote()}`;
  } else {
    note = `<div class="section-note"><b>User-defined mode is active.</b> This table edits the active user target %. Rows are grouped by Equity, Fixed income, and Other. Choose exactly one action per row. <b>Include</b> and <b>Consider alternate first</b> activate the user target %. <b>Exclude</b> ignores that row's target.</div>`;
  }
  let html = `<div class="holdings"><h3 class="group-title">Asset-class allocation policy</h3>${note}<div class="lot-table-wrap"><table class="lot-table allocation-selection-table"><thead>${header}</thead><tbody>`;
  let cat = "";
  names.forEach((asset) => {
    const actionRow = findAssetRow(asset, ["selection_action"]);
    const altRow = findAssetRow(asset, ["alternate_asset_class"]);
    const targetRow = findTargetRow(asset);
    const action = rowActionValue(actionRow);
    const c = assetCategory(asset);
    if (optMode) {
      html += `<tr><td>${c !== cat ? `<b>${esc(c)}</b>` : ""}</td><td><b>${esc(asset)}</b></td><td>${selectionActionSelect(actionRow, asset)}</td><td>${fmtPctCell(optimizerPreviewTarget(asset, "total"))}</td><td><b>${fmtPctCell(activeOptimizerUsedTarget(asset))}</b></td><td>${optimizerPreviewStatusCell(asset, action)}</td><td>${alternateSelect(altRow, asset, action)}</td></tr>`;
    } else {
      html += `<tr><td>${c !== cat ? `<b>${esc(c)}</b>` : ""}</td><td><b>${esc(asset)}</b></td><td>${selectionActionSelect(actionRow, asset)}</td><td>${targetPctInput(targetRow, asset, action)}</td><td>${alternateSelect(altRow, asset, action)}</td></tr>`;
    }
    cat = c;
  });
  html += `</tbody></table></div>${optMode ? "" : allocationTotalHtml()}</div>`;
  return html;
}
function optimizerInputRows() {
  const wanted = new Set([
    "risk_tolerance",
    "human_capital_stability",
    "concentration_employer_stock",
    "concentration_real_estate",
    "concentration_business",
    "glide_path",
    "inflation_sensitive_spending_pct",
  ]);
  const rows1 = rows
    .filter(isEditable)
    .filter(
      (r) =>
        r.section === "Model Constants" &&
        norm(r.subsection) === "allocation" &&
        wanted.has(norm(r.label)),
    );
  const rows2 = rows
    .filter(isEditable)
    .filter(
      (r) =>
        r.section === "Asset Class Assumptions" &&
        norm(r.subsection) === "global",
    );
  return rows1.concat(rows2);
}
function allocationPolicyRows() {
  return rows.filter(isEditable).filter((r) => {
    const sec = r.section,
      sub = norm(r.subsection);
    return (
      (sec === "Model Constants" && sub === "allocation") ||
      (sec === "Asset Class Assumptions" && sub === "global")
    );
  });
}
function allocationCommonRows() {
  const r = allocationModeRow();
  return r ? [r] : [];
}
function allocationTargetTotalPct() {
  return allocationTargetRows().reduce((s, r) => {
    const a = selectionActionRows().find(
      (x) => norm(x.subsection) === norm(r.subsection),
    );
    return (
      s + (rowActionValue(a) === "exclude" ? 0 : parsePercentInput(valOf(r)))
    );
  }, 0);
}
function allocationTargetsValid() {
  const rs = allocationTargetRows();
  if (!rs.length) return true;
  return Math.abs(allocationTargetTotalPct() - 100) <= 0.01;
}
function optimizerOverrideTotalPct() {
  return optimizerOverrideRows().reduce(
    (s, r) => s + parsePercentInput(valOf(r)),
    0,
  );
}
function optimizerOverrideHasEntries() {
  return optimizerOverrideRows().some(
    (r) => String(valOf(r) || "").trim() !== "",
  );
}
function optimizerOverrideValid() {
  if (!optimizerOverrideHasEntries()) return true;
  return Math.abs(optimizerOverrideTotalPct() - 100) <= 0.01;
}
function allocationTotalHtml() {
  const total = allocationTargetTotalPct();
  const ok = Math.abs(total - 100) <= 0.01;
  return `<div class="section-note" id="allocationTargetTotal"><b>User-specified allocation total:</b> ${total.toFixed(2)}% ${ok ? "✓" : "— must equal 100.00% before saving or building in user-specified mode."}</div>`;
}
function optimizerOverrideTotalHtml() {
  const total = optimizerOverrideTotalPct();
  const used = optimizerOverrideHasEntries();
  const ok = !used || Math.abs(total - 100) <= 0.01;
  return `<div class="section-note" id="optimizerOverrideTotal"><b>Optimizer override total:</b> ${used ? total.toFixed(2) + "%" : "blank — computed optimizer target will be used"} ${ok ? "✓" : "— must equal 100.00% when any optimizer override is entered."}</div>`;
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
function classKey(row) {
  return norm(row?.subsection || "");
}
function copyOptimizerOverrideToUserTargets() {
  if (!optimizerOverrideHasEntries()) {
    showMessage(
      "Enter optimizer override percentages first, or leave them blank to use the computed optimizer recommendation.",
      "error",
    );
    return;
  }
  if (!optimizerOverrideValid()) {
    showMessage(
      "Optimizer override must total 100.00% before it can overwrite the user-defined allocation.",
      "error",
    );
    return;
  }
  const targets = allocationTargetRows();
  let copied = 0;
  optimizerOverrideRows().forEach((o) => {
    const t = targets.find((r) => classKey(r) === classKey(o));
    if (t) {
      editValue(t.row_index, valOf(o), null);
      copied++;
    }
  });
  showMessage(
    `Copied ${copied} optimizer override percentages into the user-defined allocation. Review and save Plan Data.`,
    copied ? "info" : "error",
  );
  renderMain();
}
function allocationRowsOrNote(rs, msg) {
  return rs.length
    ? renderFieldGroups(rs)
    : `<div class="holdings"><div class="section-note">${msg}</div></div>`;
}
function renderAllocationPolicy() {
  const rs = allocationPolicyRows();
  if (!rs.length)
    return '<div class="holdings"><div class="field-list"><p>No optimizer input rows were found. Reload the current plan so optimizer inputs can be backfilled.</p></div></div>';
  return `<div class="holdings"><details open><summary>Optimizer inputs</summary><div class="field-list">${rs.map(fieldHtml).join("")}</div></details></div>`;
}
function renderCurrentAllocationModeNote() {
  return allocationModeHtml();
}
function renderHoldingPeriodSettingsHtml() {
  // allocationPolicyRows()/renderAllocationPolicy() only render for
  // optimizer_recommendation mode, so these Asset Allocation Policy > Global
  // rows (relevant to optimizer_recommendation, max_sharpe, and
  // real_loss_aware alike) need their own explicit lookup here to be
  // reachable at all on the current Allocation & Location tab.
  const enabledRow = findEditableRow(
    "Asset Allocation Policy",
    "Global",
    "holding_period_allocation_enabled",
  );
  const strengthRow = findEditableRow(
    "Asset Allocation Policy",
    "Global",
    "holding_period_floor_strength",
  );
  if (!enabledRow && !strengthRow) return "";
  const fields = [enabledRow, strengthRow]
    .filter(Boolean)
    .map(fieldHtml)
    .join("");
  return `<div class="holdings"><details><summary>Holding-period allocation settings</summary><div class="section-note">Optional: use this household's own projected withdrawal schedule to nudge the optimizer/max-Sharpe recommendation toward Cash for near-term money and growth for long-horizon money. Has no effect on user_target or tangency modes; selecting the holding-period real-loss-aware mode above enables the underlying discovery automatically regardless of this toggle.</div><div class="field-list">${fields}</div></details></div>`;
}
function renderRealLossAwareTuningHtml() {
  const riskRow = findEditableRow(
    "Asset Allocation Policy",
    "Global",
    "real_loss_aware_risk_aversion",
  );
  const weightRow = findEditableRow(
    "Asset Allocation Policy",
    "Global",
    "real_loss_aware_weight",
  );
  if (!riskRow && !weightRow) return "";
  const fields = [riskRow, weightRow].filter(Boolean).map(fieldHtml).join("");
  return `<div class="holdings"><details><summary>Real-loss-aware tuning</summary><div class="field-list">${fields}</div></details></div>`;
}
function renderOptimizerOverrideTable() {
  const names = assetClassNamesForAllocation();
  const rowsByClass = optimizerOverrideRows();
  if (!rowsByClass.length)
    return `<div class="holdings"><div class="section-note">Optimizer override rows were not found. Reload the current plan so optional optimizer_override_pct rows can be backfilled.</div></div>`;
  let html = `<div class="holdings"><h3 class="group-title">Optional optimizer override allocation</h3><div class="section-note">Leave override rows blank to use the computed optimizer target. Enter percentages only when you want to override the computed result; if any are entered, the override total must equal 100%.</div><div class="lot-table-wrap"><table class="lot-table allocation-override-table"><thead><tr><th>Subcategory</th><th>Asset class</th><th>Override target %</th></tr></thead><tbody>`;
  let cat = "";
  names.forEach((asset) => {
    const r = rowsByClass.find((x) => norm(x.subsection) === norm(asset));
    if (!r) return;
    const c = assetCategory(asset);
    html += `<tr><td>${c !== cat ? `<b>${esc(c)}</b>` : ""}</td><td><b>${esc(asset)}</b></td><td><input class="tiny" type="text" value="${esc(displayValueForInput(r, valOf(r)))}" placeholder="blank" oninput="editValue(${r.row_index},this.value,this)" onfocus="beginEdit(${r.row_index},this)" onblur="finishEdit(${r.row_index},this)"></td></tr>`;
    cat = c;
  });
  html += `</tbody></table></div>${optimizerOverrideTotalHtml()}<div class="table-actions"><button class="btn" type="button" onclick="copyOptimizerOverrideToUserTargets()">Copy optimizer override to user-defined</button></div></div>`;
  return html;
}
function allocationCoverageCalloutHtml() {
  const p = allocationPreview || {};
  const cov = p.coverage_summary || {};
  const fiPv = Number(cov.fixed_income_coverage_pv || 0);
  const hePv = Number(cov.home_equity_reit_coverage_value || 0);
  const sources = cov.fixed_income_included_sources || [];
  const heIncluded = !!cov.home_equity_counts_toward_reit;
  if (fiPv <= 0 && hePv <= 0) return "";
  const fmt = (v) => "$" + Math.round(v).toLocaleString();
  let parts = [];
  if (fiPv > 0) {
    const label = sources.length ? sources.join(", ") : "Guaranteed income";
    parts.push(
      `<b>Fixed Income:</b> ${fmt(fiPv)} PV from ${esc(label)} credited against your fixed income target — liquid bond allocation reduced accordingly.`,
    );
  }
  if (hePv > 0) {
    parts.push(
      `<b>Real Estate:</b> ${fmt(hePv)} home equity credited against your REIT/real estate target — liquid REIT allocation reduced accordingly.`,
    );
  }
  if (fiPv <= 0 && !heIncluded && Number(cov.gross_home_equity || 0) > 0) {
    parts.push(
      `<b>Real Estate:</b> ${fmt(Number(cov.gross_home_equity || 0))} home equity available but not counting toward REIT sleeve (policy off).`,
    );
  }
  return `<div class="section-note allocation-coverage-callout" id="allocationCoverageCallout"><b>Alternative asset coverage:</b> ${parts.join(" ")}</div>`;
}
function renderTotalWealthAllocationHtml() {
  const p = allocationPreview || {};
  const cov = p.coverage_summary || {};
  const liquidTargets = p.selected_liquid_targets || {};
  const fmt = (v) => "$" + Math.round(v).toLocaleString();
  const fmtPct = (v) => (Number(v || 0) * 100).toFixed(1) + "%";
  // Sum liquid holdings from rows
  let liquidNw = 0;
  rows.forEach((r) => {
    if (isEditable(r)) {
      const l = norm(r.label);
      if (
        [
          "pretax_nw",
          "roth_nw",
          "taxable_nw",
          "trust_nw",
          "hsa_nw",
          "other_liquid_nw",
        ].includes(l)
      ) {
        const v = Number(String(valOf(r) || "").replace(/[$,]/g, ""));
        if (Number.isFinite(v)) liquidNw += v;
      }
    }
  });
  const fiCovPv = Number(cov.fixed_income_coverage_pv || 0);
  const heVal = Number(cov.home_equity_allocation_value || 0);
  const heReit = Number(cov.home_equity_reit_coverage_value || 0);
  const heHaircut = heVal > 0 ? heVal * 0.8 : 0;
  const total = liquidNw + fiCovPv + heHaircut;
  if (total <= 0) return "";
  // Build rows
  const rows2 = [];
  // Liquid by category
  const equityPct = Object.entries(liquidTargets)
    .filter(([k]) =>
      [
        "US Large Cap",
        "US Mid Cap",
        "US Small Cap",
        "International",
        "Emerging Markets",
      ].some((e) => norm(e) === norm(k)),
    )
    .reduce((s, [, v]) => s + Number(v || 0), 0);
  const fiPct = Object.entries(liquidTargets)
    .filter(([k]) =>
      [
        "Bonds",
        "Short-Term Bonds",
        "TIPS",
        "Municipal Bonds",
        "Cash",
        "Private Credit",
      ].some((e) => norm(e) === norm(k)),
    )
    .reduce((s, [, v]) => s + Number(v || 0), 0);
  const rePct = Object.entries(liquidTargets)
    .filter(([k]) => ["REITs"].some((e) => norm(e) === norm(k)))
    .reduce((s, [, v]) => s + Number(v || 0), 0);
  const otherPct = Math.max(0, 1 - equityPct - fiPct - rePct);
  if (liquidNw > 0) {
    if (equityPct > 0)
      rows2.push({
        label: "Equity (liquid)",
        value: liquidNw * equityPct,
        note: "",
        tradeable: true,
      });
    if (fiPct > 0)
      rows2.push({
        label: "Fixed Income (liquid)",
        value: liquidNw * fiPct,
        note: "",
        tradeable: true,
      });
    if (rePct > 0)
      rows2.push({
        label: "Real Estate (liquid/REIT)",
        value: liquidNw * rePct,
        note: "",
        tradeable: true,
      });
    if (otherPct > 0.001)
      rows2.push({
        label: "Other (liquid)",
        value: liquidNw * otherPct,
        note: "",
        tradeable: true,
      });
  }
  if (fiCovPv > 0) {
    const src =
      (cov.fixed_income_included_sources || []).join(", ") ||
      "Guaranteed income";
    rows2.push({
      label: "Fixed Income (illiquid)",
      value: fiCovPv,
      note: `PV of ${src}`,
      tradeable: false,
    });
  }
  if (heHaircut > 0) {
    rows2.push({
      label: "Real Estate (home equity)",
      value: heHaircut,
      note: "Gross equity at 80% (non-tradeable)",
      tradeable: false,
    });
  }
  let html = `<div class="holdings total-wealth-allocation-panel"><h3 class="group-title">Total Wealth Allocation <span class="small" style="font-weight:normal;color:var(--muted)">(display only)</span></h3><div class="section-note">Combines liquid portfolio with illiquid sources credited against allocation targets. Illiquid values use a 20% haircut on home equity and present-value of guaranteed income. This panel is read-only.</div><div class="lot-table-wrap"><table class="lot-table"><thead><tr><th>Asset class</th><th>Value</th><th>% of Total</th><th>Type</th><th>Notes</th></tr></thead><tbody>`;
  rows2.forEach((row2) => {
    const pct = total > 0 ? row2.value / total : 0;
    html += `<tr><td>${esc(row2.label)}</td><td>${fmt(row2.value)}</td><td>${fmtPct(pct)}</td><td>${row2.tradeable ? "Liquid" : '<span class="badge">Illiquid</span>'}</td><td class="small">${esc(row2.note)}</td></tr>`;
  });
  html += `</tbody><tfoot><tr><td><b>Total</b></td><td><b>${fmt(total)}</b></td><td><b>100.0%</b></td><td></td><td></td></tr></tfoot></table></div></div>`;
  return html;
}
function renderOptimizerAllocationPanel() {
  let html = `<div class="holdings"><h3 class="group-title">Optimizer recommendation active</h3>${allocationOptimizerRecommendationHtml()}<div class="section-note">The table above controls which asset classes the optimizer may use and whether existing holdings satisfy a sleeve before new trades are recommended. Override percentages below lock a specific target, bypassing the optimizer.</div></div>`;
  html += renderOptimizerOverrideTable();
  return html;
}
function renderMaxSharpeAllocationPanel() {
  return `<div class="holdings"><h3 class="group-title">Max-Sharpe (risk-budgeted) recommendation active</h3><div class="section-note">Keeps the same risk level as the allocation optimizer recommendation (risk tolerance/auto risk score, glide path, guaranteed-income/home-equity coverage), but chooses the equity sleeve's sub-class weights to maximize the sleeve's own Sharpe ratio (return in excess of the risk-free rate, per unit of volatility) instead of a fixed risk-aversion utility. The sleeve's candidate classes are driven by the Selection column below: a class set to Exclude never enters it, and a class set to Consider alternate first and mapped to a covered source (guaranteed income, home equity, ...) is left out once that source meets the target &mdash; so large annuities/home equity already covering the bond/real-estate sleeves keeps this scoped to the classes it doesn't already decide. It does not itself re-optimize the equity/bond/cash split, and does not support a manual override.</div>${allocationOptimizerRecommendationHtml()}</div>`;
}
function renderTangencyAllocationPanel() {
  return `<div class="holdings"><h3 class="group-title">Pure tangency recommendation active</h3><div class="section-note warn"><b>No risk budget:</b> this solves for the single long-only portfolio, across the enabled/uncovered asset classes, with the highest possible Sharpe ratio. It still respects the Selection column below: Excluded classes are never candidates, and a class set to Consider alternate first and mapped to a covered source (guaranteed income, home equity, ...) is left out once that source meets the target &mdash; so if this household's annuities/home equity already cover the bond/real-estate sleeves, tangency is automatically scoped to the remaining liquid classes, driven by that configuration rather than a fixed list. Risk tolerance and glide path are not applied, and it does not support a manual override. It can concentrate heavily in a single class depending on the configured capital-market assumptions &mdash; review it as an analytical reference before using it to drive the plan.</div></div>`;
}
function renderRealLossAwarePanel() {
  const diag = (allocationPreview || {}).selected_diagnostics || {};
  const shares = diag.real_loss_aware_bucket_shares || {};
  const bucketRows = Object.entries(shares)
    .filter(([, share]) => Number(share) > 0)
    .map(
      ([label, share]) =>
        `<tr><td>${esc(label)}</td><td>${(Number(share) * 100).toFixed(1)}%</td></tr>`,
    )
    .join("");
  const bucketTable = bucketRows
    ? `<div class="section-note">Holding-period buckets used for this blend (derived from this household's own projected withdrawal schedule):</div><div class="lot-table-wrap"><table class="lot-table"><thead><tr><th>Holding-period bucket</th><th>Share of liquid balance</th></tr></thead><tbody>${bucketRows}</tbody></table></div>`
    : "";
  return `<div class="holdings"><h3 class="group-title">Holding-period real-loss-aware recommendation active</h3><div class="section-note warn"><b>No risk budget:</b> today's liquid balance is split into holding-period buckets based on this household's own projected withdrawal schedule, and each bucket is solved separately across the enabled/uncovered asset classes with an added penalty for that bucket's probability of a real (inflation-adjusted) loss at that holding period &mdash; near-term buckets are penalized for holding equities, long-horizon buckets are penalized for sitting in cash. The final recommendation blends each bucket's solution by its dollar share of today's balance. It still respects the Selection column below: Excluded classes are never candidates, and a class set to Consider alternate first and mapped to a covered source (guaranteed income, home equity, ...) is left out once that source meets the target. Risk tolerance and glide path are not applied, and it does not support a manual override.</div>${bucketTable}</div>${renderRealLossAwareTuningHtml()}`;
}
function renderAllocationRecommendation() {
  const mode = allocationSelectionMode();
  let html = renderCurrentAllocationModeNote() + renderHoldingPeriodSettingsHtml();
  if (mode === "optimizer_recommendation") html += renderAllocationPolicy();
  html += renderAssetClassSelectionTable() + allocationCoverageCalloutHtml();
  if (mode === "optimizer_recommendation") html += renderOptimizerAllocationPanel();
  else if (mode === "max_sharpe") html += renderMaxSharpeAllocationPanel();
  else if (mode === "tangency") html += renderTangencyAllocationPanel();
  else if (mode === "real_loss_aware") html += renderRealLossAwarePanel();
  html += renderTotalWealthAllocationHtml();
  return html;
}
function coreSpendingGrowthMode() {
  const r =
    findEditableRow("Cashflow", "Spending", "core_spending_growth_mode") ||
    rows.find(
      (x) => isEditable(x) && norm(x.label) === "core_spending_growth_mode",
    );
  const v = String(r ? valOf(r) : "cpi")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_");
  return v === "manual" || v === "manual_override" ? "manual_override" : "cpi";
}
function renderSpendingCore() {
  if (searchText.trim()) return renderFields("spending_core");
  /* DAF contributions are intentionally routed to Entity & Charitable Giving, not Core Spending. */ const rs =
    rowsForStep("spending_core").filter(
      (r) => norm(r.label) !== "daf_annual_contribution",
    );
  const mode = coreSpendingGrowthMode();
  const hidden = new Set([
    "core_spending_manual_growth_rate",
    "inflation_general",
    "daf_annual_contribution",
    "annual_charitable_giving_low",
    "annual_charitable_giving_high",
  ]);
  const labels =
    mode === "manual_override"
      ? [
          "core_spending_growth_mode",
          "annual_spending_base_year",
          "spending_freeze_year",
          "core_spending_manual_growth_rate",
        ]
      : [
          "core_spending_growth_mode",
          "annual_spending_base_year",
          "spending_freeze_year",
          "inflation_general",
        ];
  const ordered = [];
  labels.forEach((l) => {
    const r = rs.find((x) => norm(x.label) === norm(l));
    if (r) ordered.push(r);
  });
  rs.forEach((r) => {
    if (!ordered.includes(r) && !hidden.has(norm(r.label))) ordered.push(r);
  });
  const have = Object.fromEntries(
    [
      "annual_spending_base_year",
      "core_spending_growth_mode",
      "core_spending_manual_growth_rate",
      "inflation_general",
      "spending_freeze_year",
    ].map((l) => [l, !!rs.find((x) => norm(x.label) === norm(l))]),
  );
  let missingMsg = "";
  if (
    !have.core_spending_growth_mode ||
    !have.spending_freeze_year ||
    (!have.inflation_general && mode === "cpi") ||
    (!have.core_spending_manual_growth_rate && mode === "manual_override")
  )
    missingMsg = `<div class="section-note warning" id="coreSpendingRowsMissing"><b>Core spending controls are being created:</b> save or reload Plan Data if any control is missing. Expected rows are Core Spending Base, Core Spending Increase Stops, Core Spending Increase Method, and the relevant increase-rate field.</div>`;
  let html = `<div class="section-note"><b>Projection controls:</b> Core spending base/growth controls feed recurring lifestyle spending. The category hierarchy below is the comprehensive income/expense model except taxes/transfers. Category assignment happens here; Accounts & Sources lives on Income & Expense Transactions.</div>${missingMsg}`;
  html += `<div class="field-list core-spending-flat">${ordered.map(fieldHtml).join("")}</div>`;
  return html;
}
function renderFields(step) {
  let rs = rowsForStep(step);
  if (searchText.trim()) {
    const q = searchText.toLowerCase();
    rs = rowsForStep(step).filter((r) =>
      [
        r.section,
        r.subsection,
        r.label,
        r.notes,
        r.value,
        r.schema?.description,
      ]
        .join(" ")
        .toLowerCase()
        .includes(q),
    );
  }
  const missing = rs.filter(isMissing);
  let html = missing.length
    ? `<div class="missing-list"><h3>${missing.length} required field${missing.length === 1 ? "" : "s"} missing in this view</h3><ul>${missing
        .slice(0, 8)
        .map((r) => `<li>${esc(humanLabel(r.label, r))}</li>`)
        .join("")}</ul></div>`
    : "";
  if (["assets_special"].includes(step))
    html += `<div class="section-note">Some fields on this page feed reporting and workbook narrative only — they do not directly affect cash-flow or tax calculations. Review the workbook output after a rebuild to confirm what affected each projection year.</div>`;
  if (step === "scenarios")
    html += `<div class="section-note">Home sale stress-test rows apply to scenario workbook outputs only. Base-plan sale year, future rent, renters insurance, and rental utilities are managed on the Housing page.</div>`;
  if (step === "roth_conversion")
    html += `<div class="section-note">Tax bracket target rows appear here rather than in Economic &amp; Tax Assumptions because they are strategy inputs — they define the conversion ceiling, not a general economic forecast.</div>`;
  if (step === "all_assumptions")
    html += `<div class="section-note">Grouped by plan area, matching the left navigation, alphabetical within each area. Each field shows its own source page beneath its label.</div>`;
  if (step === "monte_carlo_options")
    html += `<div class="section-note">Advanced mode runs more trials with higher precision and is suitable for final outputs. Quick mode is faster and appropriate for working sessions. Raise trial count for final runs only when the build time budget allows.</div>`;
  if (step === "divorce_options" && !optionalFunctionEnabled("divorce_qdro"))
    return '<div class="field-list"><p>Divorce options are hidden until the Divorce/QDRO optional workbook module is enabled.</p></div>';
  if (
    step === "ltc_stress" &&
    !optionalFunctionEnabled("long_term_care_stress")
  )
    return '<div class="field-list"><p>Long-Term Care Stress inputs are hidden until the Long-Term-Care Stress optional workbook module is enabled on Optional Modules.</p></div>';
  if (step === "heloc_strategy" && !helocModuleEnabled())
    return '<div class="field-list"><p>HELOC strategy inputs are hidden until Enable HELOC Strategy is turned on (HELOC → Setup).</p></div>';
  if (
    step === "entity_charitable" &&
    !optionalFunctionEnabled("charitable_giving")
  )
    return '<div class="field-list"><p>Charitable Giving inputs are hidden until the Charitable Giving optional workbook module is enabled on Optional Modules.</p></div>';
  if (step === "all_assumptions") return html + renderFieldFinderGroups(rs);
  return html + renderFieldGroups(rs);
}
const PERSON_TABLE_LABELS = [
  "name",
  "nickname",
  "dob",
  "retirement_date",
  "mortality_age",
];
function personDisplayName(n) {
  const nick = householdPersonRow(n, "nickname");
  const name = householdPersonRow(n, "name");
  const v =
    String(nick ? valOf(nick) : "").trim() ||
    String(name ? valOf(name) : "")
      .trim()
      .split(/\s+/)[0];
  return v || `Member ${n}`;
}
function householdPersonRow(n, suffix) {
  return (
    rows.find(
      (r) =>
        isEditable(r) &&
        r.section === "Household" &&
        norm(r.label) === `member_${n}_${suffix}`,
    ) || null
  );
}
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
    }))
    .filter((p) => p.name || p.nickname || p.dob);
  const nickMissing = people.some(
    (p) =>
      p.name &&
      String(valOf(p.name) || "").trim() &&
      p.nickname &&
      !String(valOf(p.nickname) || "").trim(),
  );
  let html = `<div class="holdings"><h3 class="group-title">People</h3><div class="section-note">One row per person. <b>Nickname</b> is the short name used everywhere the plan names a person — reports, charts, and workbook labels. ${nickMissing ? "<b>Add a nickname for each person</b> (or leave blank to use their first name)." : ""}</div><div class="lot-table-wrap"><table class="lot-table people-table"><thead><tr><th></th><th>Full name</th><th>Nickname (used in reports)</th><th>Date of birth</th><th title="Year is parsed from this date; base retirement assumption">Retirement date</th><th title="Plan horizon = birth year + this age">Mortality age</th></tr></thead><tbody>`;
  people.forEach((p) => {
    const who = String(p.name ? valOf(p.name) : "").trim() || `Person ${p.n}`;
    html += `<tr><td><b>Person ${p.n}</b></td><td>${personCellInput(p.name, `Full name for ${who}`)}</td><td>${personCellInput(p.nickname, `Nickname for ${who}`, personNickPlaceholder(p.name))}</td><td>${personCellInput(p.dob, `Date of birth for ${who}`)}</td><td>${personCellInput(p.retire, `Retirement date for ${who}`)}</td><td>${personCellInput(p.mortality, `Mortality age for ${who}`)}</td></tr>`;
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
function hasAnnuityDeathBenefits() {
  return matrixRows("Annuity Death Benefits").length > 0;
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
function recentChangesLogHtml() {
  const changes = [...sessionChanges.values()];
  const specials = [...sessionSpecialChanges];
  if (!changes.length && !specials.length)
    return '<p class="small" style="margin:4px 0;color:var(--muted)">No field changes in this session yet.</p>';
  let html =
    '<div class="recent-changes-log"><table class="change-table"><thead><tr><th>Field</th><th>Source</th><th>Before</th><th>After</th><th></th></tr></thead><tbody>';
  changes.slice(0, 20).forEach((c) => {
    const src = c.sourceStep
      ? `<button class="btn tiny" type="button" data-step-id="${esc(c.sourceStep)}">${esc(c.sourceTitle || c.sourceStep)}</button>`
      : esc(c.group || "—");
    html += `<tr><td>${esc(c.label)}</td><td>${src}</td><td>${esc(c.before || "blank")}</td><td>${esc(c.after || "blank")}</td><td><button class="btn tiny" type="button" onclick="undoSessionFieldChange(${c.row_index})">Undo</button></td></tr>`;
  });
  if (changes.length > 20)
    html += `<tr><td colspan="5" class="small">${changes.length - 20} more changes.</td></tr>`;
  if (specials.length)
    html += `<tr><td colspan="5" class="small"><b>Table edits:</b> ${specials.map((s) => esc(s)).join(", ")}</td></tr>`;
  html += "</tbody></table></div>";
  return html;
}
function undoSessionFieldChange(rowIndex) {
  const entry = [...sessionChanges.values()].find(
    (c) => c.row_index === Number(rowIndex),
  );
  if (!entry) {
    showMessage("Cannot undo: change not found in this session.", "error");
    return;
  }
  editValue(entry.row_index, entry.beforeStorage || entry.before, null);
  showMessage("Undone: " + entry.label);
  renderMain();
  renderSteps();
}

function showInAppConfirm(message, opts) {
  opts = opts || {};
  return new Promise(function (resolve) {
    const overlay = document.createElement("div");
    overlay.className = "inapp-modal-overlay";
    const variant = opts.variant || "";
    const title = opts.title || "Confirm";
    const confirmLabel = opts.confirmLabel || "Confirm";
    const cancelLabel = opts.cancelLabel || "Cancel";
    const bodyHtml = opts.bodyIsHtml ? message : "<p>" + esc(message) + "</p>";
    overlay.innerHTML =
      '<div class="inapp-modal' +
      (variant ? " modal-" + variant : "") +
      '"><b class="inapp-modal-title">' +
      esc(title) +
      '</b><div class="inapp-modal-body">' +
      bodyHtml +
      '</div><div class="inapp-modal-actions"><button class="btn inapp-cancel" type="button">' +
      esc(cancelLabel) +
      '</button><button class="btn primary inapp-confirm" type="button">' +
      esc(confirmLabel) +
      "</button></div></div>";
    document.body.appendChild(overlay);
    function close(v) {
      overlay.remove();
      resolve(v);
    }
    overlay.querySelector(".inapp-confirm").onclick = function () {
      close(true);
    };
    overlay.querySelector(".inapp-cancel").onclick = function () {
      close(false);
    };
    overlay.onclick = function (e) {
      if (e.target === overlay) close(false);
    };
    function onKey(e) {
      if (e.key === "Escape") {
        close(false);
        document.removeEventListener("keydown", onKey);
      }
    }
    document.addEventListener("keydown", onKey);
    setTimeout(function () {
      const b = overlay.querySelector(".inapp-cancel");
      if (b) b.focus();
    }, 30);
  });
}
function showYtdBlendChoiceModal(summary) {
  return new Promise(function (resolve) {
    const actual = (summary && summary.actual) || {};
    const spend = Number(actual.spending || 0);
    const earned = Number(actual.earned_income || 0);
    const asOf = summary && summary.ytd_end ? summary.ytd_end : "today";
    const parts = [];
    if (spend > 0)
      parts.push(
        "$" +
          spend.toLocaleString(undefined, { maximumFractionDigits: 0 }) +
          " of actual spending",
      );
    if (earned > 0)
      parts.push(
        "$" +
          earned.toLocaleString(undefined, { maximumFractionDigits: 0 }) +
          " of actual earned income",
      );
    const figures = parts.length
      ? parts.join(" and ")
      : "real transaction activity";
    const body =
      "<p>This workspace has " +
      esc(figures) +
      " tracked through <b>" +
      esc(asOf) +
      "</b>, independent of any plan you build here.</p>" +
      "<p><b>Use real actuals (recommended):</b> the new plan's current-year projection blends this real activity in for the remainder of the year — matches how the app models your actual ongoing plan.</p>" +
      '<p><b>Model as fully hypothetical:</b> ignores the real activity above and projects the whole current year from your entered assumptions only — use this for a detached "what-if" scenario that should not inherit real bank/brokerage activity.</p>' +
      '<p class="small">You can change this later from the YTD Account Setup page.</p>';
    const overlay = document.createElement("div");
    overlay.className = "inapp-modal-overlay";
    overlay.innerHTML =
      '<div class="inapp-modal"><b class="inapp-modal-title">New plan and real year-to-date actuals</b><div class="inapp-modal-body">' +
      body +
      '</div><div class="inapp-modal-actions"><button class="btn ytd-choice-cancel" type="button">Cancel</button><button class="btn ytd-choice-hypothetical" type="button">Model as fully hypothetical</button><button class="btn primary ytd-choice-blend" type="button">Use real actuals (recommended)</button></div></div>';
    document.body.appendChild(overlay);
    function close(v) {
      overlay.remove();
      resolve(v);
    }
    overlay.querySelector(".ytd-choice-blend").onclick = function () {
      close("blend");
    };
    overlay.querySelector(".ytd-choice-hypothetical").onclick = function () {
      close("hypothetical");
    };
    overlay.querySelector(".ytd-choice-cancel").onclick = function () {
      close(null);
    };
    overlay.onclick = function (e) {
      if (e.target === overlay) close(null);
    };
    function onKey(e) {
      if (e.key === "Escape") {
        close(null);
        document.removeEventListener("keydown", onKey);
      }
    }
    document.addEventListener("keydown", onKey);
    setTimeout(function () {
      const b = overlay.querySelector(".ytd-choice-blend");
      if (b) b.focus();
    }, 30);
  });
}
function showInAppPrompt(message, defaultValue, opts) {
  defaultValue = defaultValue || "";
  opts = opts || {};
  return new Promise(function (resolve) {
    const overlay = document.createElement("div");
    overlay.className = "inapp-modal-overlay";
    const title = opts.title || message;
    const placeholder = opts.placeholder || "";
    overlay.innerHTML =
      '<div class="inapp-modal"><b class="inapp-modal-title">' +
      esc(title) +
      '</b><div class="inapp-modal-body"><input class="inapp-modal-input compact-input" type="text" value="' +
      esc(defaultValue) +
      '" placeholder="' +
      esc(placeholder) +
      '"></div><div class="inapp-modal-actions"><button class="btn inapp-cancel" type="button">Cancel</button><button class="btn primary inapp-confirm" type="button">OK</button></div></div>';
    document.body.appendChild(overlay);
    const input = overlay.querySelector(".inapp-modal-input");
    function close(v) {
      overlay.remove();
      resolve(v);
    }
    overlay.querySelector(".inapp-confirm").onclick = function () {
      close(input.value.trim() || null);
    };
    overlay.querySelector(".inapp-cancel").onclick = function () {
      close(null);
    };
    overlay.onclick = function (e) {
      if (e.target === overlay) close(null);
    };
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter") close(input.value.trim() || null);
      else if (e.key === "Escape") close(null);
    });
    setTimeout(function () {
      input.focus();
      input.select();
    }, 30);
  });
}
function nbaPanelHtml() {
  let state,
    msg,
    action,
    cls = "nba-panel";
  if (!planLoaded) {
    state = "No plan loaded";
    msg =
      "Use Start New Plan or load a saved plan from the welcome page below to begin.";
    action = "";
    cls += " nba-idle";
  } else {
    const unsaved = unsavedChangeCount();
    const stats = overallStats();
    const artifacts = planStateArtifactsReady();
    const fresh = planStateFresh();
    const p = buildPreflight || {};
    if (unsaved) {
      state = "Unsaved changes";
      msg =
        unsaved +
        " pending change" +
        (unsaved === 1 ? "" : "s") +
        " — save before rebuilding.";
      action =
        '<button class="btn primary" type="button" data-requires-app="1" onclick="saveAll(true)">Save Changes</button>';
      cls += " nba-warn";
    } else if (stats.missing && stats.missing.length) {
      const n = stats.missing.length;
      state = "Required fields missing";
      msg =
        n +
        " required field" +
        (n === 1 ? " is" : " are") +
        " blank — complete before building advisor-ready reports.";
      action =
        '<button class="btn" type="button" data-step-id="all_assumptions">Review Fields</button>';
      cls += " nba-warn";
    } else if (!artifacts) {
      state = "Ready to build";
      msg =
        "All required fields are complete. Build outputs to generate the workbook and results.";
      action =
        '<button class="btn primary" type="button" data-requires-app="1" onclick="runBuild(false)">Build Reports</button>';
      cls += " nba-action";
    } else {
      const wbMtime = ((p.artifacts || {}).workbook || {}).mtime;
      const daysSince = wbMtime ? (Date.now() / 1000 - wbMtime) / 86400 : null;
      if (daysSince !== null && daysSince > 30) {
        const d = Math.round(daysSince);
        state = "Reports are stale";
        msg =
          "Last build was " +
          d +
          " day" +
          (d === 1 ? "" : "s") +
          " ago — rebuild to reflect any recent changes.";
        action =
          '<button class="btn primary" type="button" data-requires-app="1" onclick="runBuild(false)">Rebuild</button>';
        cls += " nba-warn";
      } else if (!fresh) {
        state = "Plan changed since last build";
        msg =
          "Plan data was saved after the last build — rebuild to keep reports current.";
        action =
          '<button class="btn primary" type="button" data-requires-app="1" onclick="runBuild(false)">Rebuild</button>';
        cls += " nba-warn";
      } else {
        state = "Reports are current";
        msg =
          "Plan is saved, required fields complete, and reports match the latest build.";
        action =
          '<button class="btn" type="button" data-step-id="detailed_results">View Results</button> <button class="btn" type="button" data-step-id="reports_and_review">Download</button>';
        cls += " nba-ok";
      }
    }
  }
  return (
    '<div class="' +
    cls +
    '"><div class="nba-status">' +
    esc(state) +
    '</div><div class="nba-message">' +
    esc(msg) +
    '</div><div class="nba-action">' +
    action +
    "</div></div>"
  );
}
function renderWelcome() {
  var _autoLoad = _autoLoadPref !== null ? _autoLoadPref : false;
  try {
    if (_autoLoadPref === null)
      _autoLoad = localStorage.getItem("rpAutoLoad") === "1";
  } catch (_e) {}
  return `<div class="pane-head"><div class="eyebrow">Welcome</div><h2>Retirement planning workspace</h2><p>Enter source facts first, then model strategy and stress tests, run preflight, build reports, and review the workbook results.</p><div class="pane-actions"><button class="btn primary" data-requires-app="1" onclick="startNewPlan()">Start New Plan</button><button class="btn" data-requires-app="1" onclick="loadAll({source:'Local database',preferLocal:false})">Open Current Plan</button><button class="btn" onclick="savePlanAs()">Save Plan As</button><button class="btn" onclick="loadSavedPlan()">Load Saved Plan</button></div><div style="margin:8px 0 4px;font-size:13px"><label style="cursor:pointer;user-select:none"><input type="checkbox" id="autoLoadCheck"${_autoLoad ? " checked" : ""} onchange="setAutoLoad(this.checked)"> Auto-load plan on next start</label></div></div>${nbaPanelHtml()}${taxFreshnessBannerHtml()}${planKpiMetricsHtml()}${firstRunChecklistHtml(false)}<div class="feature-grid"><div class="feature-card"><h3>Your plan</h3><ul><li><b>The saved plan</b> is the active source for all projections.</li><li><b>Plan Data files</b> can be exported for backup, sharing, or recovery.</li><li><b>Reports</b> are generated snapshots — edit the plan, then rebuild to update them.</li></ul></div><div class="feature-card"><h3>Save and build</h3><ul><li><b>Save Changes</b> stores ordinary fields, tables, category budgets, transaction edits, holdings, liabilities, and strategy-table edits.</li><li><b>Build Reports</b>, <b>Download Workbook</b>, and <b>Download PDF</b> save first, run preflight, then rebuild reports.</li><li>Use page-level reload buttons only when discarding unsaved page edits.</li></ul></div><div class="feature-card"><h3>Spending flow</h3><ul><li>Spending Categories defines the Tracking Type, Group, and Category model.</li><li>Housing, Wellness, and Travel are authoritative detail pages.</li><li>Income &amp; Expense Transactions feeds Spending Analysis and actual-vs-model review.</li></ul></div><div class="feature-card"><h3>Final review</h3><ol class="small"><li>Open Reports &amp; Review.</li><li>Check the Preflight tab for missing fields.</li><li>Resolve blockers, then build.</li><li>Review Impact and Results, then download the workbook.</li></ol></div></div>${closeoutChecklistHtml()}`;
}
function renderSystemConfiguration() {
  return `<div class="system-config-panel"><div class="section-note">Maintenance utilities for this workspace — pricing snapshots, backups, CSV export, the recent-change log, and the raw System Configuration Console. Plan assumptions, optional modules, the field finder, and workbook formatting are now pages in the left nav under Settings.</div><section class="system-config-section"><div class="system-config-grid"><div class="feature-card" tabindex="0" onclick="showConfigCardHelp('pricing_mode')" onfocus="showConfigCardHelp('pricing_mode')"><h3>Pricing mode</h3><p class="small">Check live/cache/fallback pricing status, refresh live quotes when the cache looks stale, then freeze a saved price snapshot when reports need reproducible advisor values.</p><button class="btn" type="button" data-step-id="build_impact" onfocus="event.stopPropagation();showConfigCardHelp('pricing_mode')">Open Build History</button> <button class="btn primary" type="button" onclick="event.stopPropagation();refreshLivePrices()" onfocus="event.stopPropagation();showConfigCardHelp('pricing_mode')">Refresh Prices</button> <button class="btn" type="button" onclick="event.stopPropagation();freezePricingSnapshot()" onfocus="event.stopPropagation();showConfigCardHelp('pricing_mode')">Freeze latest prices</button> <button class="btn" type="button" onclick="event.stopPropagation();unfreezePricingSnapshot()" onfocus="event.stopPropagation();showConfigCardHelp('pricing_mode')">Unfreeze prices</button></div>${localBackupControlsHtml()}<div class="feature-card" tabindex="0" onclick="showConfigCardHelp('session_changes')" onfocus="showConfigCardHelp('session_changes')"><h3>Session changes</h3>${recentChangesLogHtml()}</div><div class="feature-card" tabindex="0" onclick="showConfigCardHelp('system_config_console')" onfocus="showConfigCardHelp('system_config_console')"><h3>System configuration console</h3><p class="small">Maintain pricing providers, build timeout, tax constants, reference files, diagnostics, and raw system configuration rows. Opens as its own page.</p><button class="btn primary" type="button" onclick="event.stopPropagation();openSystemConfigurationConsole()" onfocus="event.stopPropagation();showConfigCardHelp('system_config_console')">Open System Configuration Console</button></div><div class="feature-card" tabindex="0" onclick="showConfigCardHelp('csv_backup')" onfocus="showConfigCardHelp('csv_backup')"><h3>CSV backup</h3><p class="small">Export a CSV backup of holdings, transactions, target allocations, and reference data for recovery or external review.</p><button class="btn" type="button" onclick="event.stopPropagation();exportCsvBackup()" onfocus="event.stopPropagation();showConfigCardHelp('csv_backup')">Export CSV backup</button></div></div></section></div>`;
}

// Workbook formatting (Settings → Manage Workbook Formatting) moved to
// dashboard_decomp_workbook_formatting.js (first modularization increment).

async function refreshLivePrices() {
  try {
    showMessage("Refreshing prices from live providers...");
    const out = await api("/api/prices/refresh", {
      method: "POST",
      body: JSON.stringify({}),
    });
    const r = out.result || {};
    const resolved = Number(r.prices_resolved || 0);
    const requested = Number(r.symbols_requested || 0);
    const live = Number(r.live_prices_resolved || 0);
    showMessage(
      out.success
        ? `Prices refreshed: ${live} live quote${live === 1 ? "" : "s"}, ${resolved}/${requested} symbols resolved.`
        : "Price refresh completed with warnings — open Build History or pricing diagnostics to review.",
      out.success ? "success" : "error",
    );
    buildPreflight = null;
    await refreshPreflightForReview();
  } catch (e) {
    showMessage(
      "Price refresh failed: " + (e && e.message ? e.message : e),
      "error",
    );
  }
}
async function freezePricingSnapshot() {
  try {
    const out = await api("/api/prices/freeze", {
      method: "POST",
      body: JSON.stringify({}),
    });
    showMessage(
      `Frozen pricing snapshot with ${Number(out.symbol_count || 0)} symbol${Number(out.symbol_count || 0) === 1 ? "" : "s"}.`,
      "success",
    );
    buildPreflight = null;
    await refreshPreflightForReview();
  } catch (e) {
    showMessage(
      "Pricing freeze failed: " + (e && e.message ? e.message : e),
      "error",
    );
  }
}
async function unfreezePricingSnapshot() {
  try {
    await api("/api/prices/unfreeze", {
      method: "POST",
      body: JSON.stringify({}),
    });
    showMessage(
      "Pricing snapshot freeze removed. Future builds will use the configured pricing mode.",
      "success",
    );
    buildPreflight = null;
    await refreshPreflightForReview();
  } catch (e) {
    showMessage(
      "Pricing unfreeze failed: " + (e && e.message ? e.message : e),
      "error",
    );
  }
}
function exportCsvBackup() {
  const url = "/api/admin/csv-backup";
  showMessage("Exporting CSV backup...");
  if (window.__is_desktop_app__) {
    fetch(apiUrl(url))
      .then(function (r) {
        return r.json ? r.json() : r;
      })
      .then(function (out) {
        if (out && out.success === false)
          showMessage(
            "CSV backup failed: " + (out.error || "unknown error"),
            "error",
          );
        else showMessage("CSV backup exported.", "success");
      })
      .catch(function (e) {
        showMessage(
          "CSV backup error: " + (e && e.message ? e.message : e),
          "error",
        );
      });
    return;
  }
  window.location.href = apiUrl(url);
}
function openSystemConfigurationConsole() {
  if (window.__is_desktop_app__) {
    // Call the pywebview bridge directly instead of relying on
    // location.href interception: WebView2/EdgeChromium does not always
    // allow pywebview_bridge.js to override Location.prototype.href (see
    // the try/catch there), so that path can silently fall through to a
    // real file:// navigation to a URL that doesn't exist on disk.
    if (window.pywebview && window.pywebview.api) {
      window.pywebview.api.navigate("/system-configuration");
    } else {
      window.addEventListener(
        "pywebviewready",
        function () {
          window.pywebview.api.navigate("/system-configuration");
        },
        { once: true },
      );
    }
    return;
  }
  location.href = "/system-configuration";
}

const DEFAULT_TRAVEL_TYPES = ["Wedding", "Large Gifts", "Other"];
function travelTypeList() {
  return [
    ...new Set([
      ...(travelTypes || []),
      ...DEFAULT_TRAVEL_TYPES,
      ...travelExtras.map((e) => e.type).filter(Boolean),
    ]),
  ].sort((a, b) => a.localeCompare(b));
}
function setAutoLoad(v) {
  try {
    localStorage.setItem("rpAutoLoad", v ? "1" : "0");
  } catch (_e) {}
  // Also persist server-side so the preference survives WebView2 session resets.
  fetch("/api/prefs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rpAutoLoad: v }),
  }).catch(function () {});
}
function checklistItemStatus(stepIds) {
  if (!planLoaded) return { cls: "todo", label: "Open plan" };
  let missing = 0,
    required = 0,
    dirtyCount = 0;
  stepIds.forEach((id) => {
    const st = stepStats(id);
    missing += st.missing.length;
    required += st.required.length;
    dirtyCount += st.dirty.length;
  });
  if (dirtyCount) return { cls: "warn", label: "Edited" };
  if (missing) return { cls: "warn", label: missing + " missing" };
  if (required) return { cls: "done", label: "Ready" };
  return { cls: "todo", label: "Optional" };
}
function firstRunChecklistHtml(compact = false) {
  const items = [
    {
      title: "Household foundation",
      desc: "People, dates, filing status, state, retirement timing, and planning horizon.",
      steps: ["household_people"],
      next: "household_people",
    },
    {
      title: "Income",
      desc: "Work income, Social Security, pensions, annuities, and retirement income streams.",
      steps: ["income_work", "income_retirement"],
      next: "income_work",
    },
    {
      title: "Spending and actuals",
      desc: "Categories, housing, Wellness, travel, large discretionary items, and current-year transactions.",
      steps: [
        "spending_core",
        "retirement_wellness",
        "spending_mortgage_events",
        "spending_travel",
        "spending_travel_extras",
        "ytd_transactions",
        "spending_dashboard",
      ],
      next: "spending_core",
    },
    {
      title: "Assets and protection",
      desc: "Holdings, cash reserves, annuity death benefits, life insurance, other assets, liabilities, and estate inputs.",
      steps: [
        "holdings",
        "assets_home_cash",
        "annuity_death_benefits",
        "assets_special",
        "estate",
      ],
      next: "holdings",
    },
    {
      title: "Strategy",
      desc: "Distribution strategy, investment strategy, state residency analysis, and optional advanced strategies.",
      steps: [
        "planning_levers",
        "roth_conversion",
        "allocation_assets",
        "allocation_policy",
        "withdrawal_strategy",
        "state_residency",
        "heloc_strategy",
        "entity_charitable",
      ],
      next: "distribution_strategy",
    },
    {
      title: "Stress tests",
      desc: "Monte Carlo, survivor, long-term care, and optional divorce/QDRO stress.",
      steps: [
        "monte_carlo_options",
        "survivor_stress",
        "ltc_stress",
        "divorce_options",
      ],
      next: "monte_carlo_options",
    },
    {
      title: "Review and build",
      desc: "Run preflight, build reports, review impact and results, and download the final workbook.",
      steps: ["review", "build_impact", "detailed_results", "plan_data_report"],
      next: "reports_and_review",
    },
  ];
  let html = `<div class="first-run-checklist ${compact ? "compact" : ""}"><div class="first-run-head"><div><h3>${compact ? "Workflow checklist" : "Recommended workflow"}</h3><p class="small">A low-risk path through the plan: enter source data first, then strategy, stress tests, preflight, build, and review.</p></div>${compact ? "" : '<button class="btn primary" type="button" data-step-id="reports_and_review">Review and Build</button>'}</div><div class="first-run-items">`;
  items.forEach((item) => {
    const st = checklistItemStatus(item.steps);
    html += `<button class="first-run-item ${st.cls}" type="button" data-step-id="${esc(item.next)}"><span class="check-status">${esc(st.label)}</span><b>${esc(item.title)}</b><small>${esc(item.desc)}</small></button>`;
  });
  html += "</div></div>";
  return html;
}
async function savePlanAs() {
  if (!window.pywebview) {
    showMessage("File dialogs require the desktop app.", "error");
    return;
  }
  try {
    const result = await window.pywebview.api.show_save_dialog("myplan.rpx");
    if (!result || result.cancelled) return;
    if (hasUnsavedPlanChanges()) {
      showMessage("Saving current changes before exporting...");
      const ok = await saveWorkingCopy();
      if (!ok) {
        showMessage(
          "Could not save current changes before exporting. Plan file not saved.",
          "error",
        );
        return;
      }
    }
    const resp = await api("/api/plan/save-as", {
      method: "POST",
      body: JSON.stringify({ path: result.path }),
    });
    if (resp && resp.success) showMessage("Plan saved to: " + result.path);
    else
      showMessage(
        "Save failed: " + ((resp && resp.error) || "unknown error"),
        "error",
      );
  } catch (e) {
    showMessage("Error saving plan: " + e.message, "error");
  }
}
async function loadSavedPlan() {
  if (
    hasUnsavedPlanChanges() &&
    !(await showInAppConfirm(
      "You have unsaved changes. Load a saved plan anyway? All unsaved changes will be lost.",
      {
        title: "Load Saved Plan",
        confirmLabel: "Discard & Load",
        cancelLabel: "Keep Editing",
        variant: "warn",
      },
    ))
  )
    return;
  if (!window.pywebview) {
    showMessage("File dialogs require the desktop app.", "error");
    return;
  }
  if (
    !(await showInAppConfirm(
      "This replaces the current plan in the local database.",
      { title: "Load Saved Plan", confirmLabel: "Load Plan", variant: "warn" },
    ))
  )
    return;
  try {
    const result = await window.pywebview.api.show_open_dialog();
    if (!result || result.cancelled) return;
    const resp = await api("/api/plan/load-file", {
      method: "POST",
      body: JSON.stringify({ path: result.path }),
    });
    if (resp && resp.success) {
      showMessage("Plan loaded from " + result.path);
      await loadAll({ source: "Loaded from file", preferLocal: false });
      renderMain();
    } else
      showMessage(
        "Load failed: " + ((resp && resp.error) || "unknown error"),
        "error",
      );
  } catch (e) {
    showMessage("Error loading plan: " + e.message, "error");
  }
}
/* Large Discretionary Expenses (travel extras), liquidity reserve buffers, and
   forced Roth conversions moved to frontend/js/dashboard_decomp_supplemental_tables.js
   (loaded before dashboard.js). */
function findRows(sectionName, subsectionName, labels) {
  return labels
    .map((l) => findEditableRow(sectionName, subsectionName, l))
    .filter(Boolean);
}
function ssPersonRows(person) {
  return findRows("Social Security", person, [
    "claim_age",
    "monthly_pia_at_fra_today_dollars",
    "fra_age",
  ]);
}
function ssActiveCell(row) {
  if (!row) return '<span class="small">Missing</span>';
  return fieldControlOnly(row);
}
// Mirrors src/projection_stages/deterministic_engine.py _fra_for_birth_year /
// _ss_claim_factor closely enough for this preview cell. The workbook build
// always uses the authoritative Python engine; this is a display estimate.
function ssClaimFactor(claimAge, fra) {
  const months = Math.round((Number(claimAge || fra) - fra) * 12);
  if (months >= 0) return 1.0 + months * (0.08 / 12.0);
  const early = Math.abs(months);
  const first36 = Math.min(36, early) * (5.0 / 900.0);
  const extra = Math.max(0, early - 36) * (5.0 / 1200.0);
  return Math.max(0.0, 1.0 - first36 - extra);
}
function ssMonthlyAtClaimAgeCell(person, claimAgeRow) {
  if (!claimAgeRow) return '<span class="small">Missing</span>';
  const age = Math.max(
    62,
    Math.min(70, Math.round(fieldNumericValue(claimAgeRow) || 70)),
  );
  const benefitRow = findEditableRow(
    "Social Security",
    person,
    `ss_benefit_age_${age}`,
  );
  const amount = benefitRow ? fieldNumericValue(benefitRow) : 0;
  if (benefitRow && amount)
    return `<span class="computed-value">${esc(fmtMoney(amount))}</span>`;
  // No SSA-quoted figure for this exact age — derive it from FRA/PIA using
  // the SSA reduction/delayed-credit factor instead of just asking the user
  // to fill in the table, so a claim-age change always shows a value.
  const fraRow = findEditableRow("Social Security", person, "fra_age");
  const fra = (fraRow ? fieldNumericValue(fraRow) : 0) || 67;
  const piaRow = findEditableRow(
    "Social Security",
    person,
    "monthly_pia_at_fra_today_dollars",
  );
  const age67Row = findEditableRow("Social Security", person, "ss_benefit_age_67");
  const pia =
    (piaRow ? fieldNumericValue(piaRow) : 0) ||
    (age67Row ? fieldNumericValue(age67Row) : 0);
  if (!pia)
    return `<span class="small">Enter Monthly at FRA</span>`;
  const derived = pia * ssClaimFactor(age, fra);
  return `<span class="computed-value">~${esc(fmtMoney(derived))} <span class="small">(derived from FRA)</span></span>`;
}
function renderSsCompactTable() {
  const people = [
    { key: "Member 1", n: 1 },
    { key: "Member 2", n: 2 },
  ];
  let html = `<div class="holdings retirement-income-section"><h3 class="group-title">Social Security</h3><div class="section-note">Enter each person’s FRA Age, Monthly at FRA, and claiming age. Monthly at Claim Age is calculated: it’s looked up from a saved SSA benefit-table entry for that exact age when available, otherwise it’s derived from FRA Age and Monthly at FRA using the SSA reduction/delayed-credit factor. FRA Age defaults to 67 (SSA birth-year rule) if left blank.</div><div class="lot-table-wrap"><table class="lot-table compact-table ss-compact-table"><thead><tr><th>Person</th><th>FRA Age</th><th>Monthly at FRA</th><th>Claim Age</th><th>Monthly at Claim Age</th></tr></thead><tbody>`;
  people.forEach((p) => {
    const r = ssPersonRows(p.key);
    const by = {};
    r.forEach((x) => (by[norm(x.label)] = x));
    html += `<tr><td><b>${esc(personDisplayName(p.n))}</b></td><td>${ssActiveCell(by.fra_age)}</td><td>${ssActiveCell(by.monthly_pia_at_fra_today_dollars)}</td><td>${ssActiveCell(by.claim_age)}</td><td>${ssMonthlyAtClaimAgeCell(p.key, by.claim_age)}</td></tr>`;
  });
  return html + "</tbody></table></div></div>";
}
function fieldControlOnly(r) {
  const html = fieldHtml(r);
  const m = html.match(
    /<div>(<input[\s\S]*?<\/input>|<select[\s\S]*?<\/select>|<input[\s\S]*?>)(?:<div class="unit">[\s\S]*?<\/div>)?<\/div><\/div>$/,
  );
  if (m) return m[1];
  const wrap = document.createElement("div");
  wrap.innerHTML = html;
  const ctrl = wrap.querySelector("input,select,textarea");
  return ctrl ? ctrl.outerHTML : html;
}
function incomeStreamSubsections() {
  return [
    ...new Set(
      rows
        .filter(isEditable)
        .filter(
          (r) =>
            r.section === "Income Streams" &&
            ![
              "joint_and_survivor_percentage",
              "recovery_age",
            ].includes(norm(r.subsection)),
        )
        .map((r) => String(r.subsection || ""))
        .filter(Boolean),
    ),
  ];
}
function renderIncomeStreamsSection() {
  const globalRows = findRows(
    "Income Streams",
    "Joint-and-Survivor Percentage",
    ["js_pct"],
  ).concat(
    findRows("Income Streams", "Recovery Age", ["principal_recovery_age"]),
  );
  let html = `<div class="holdings retirement-income-section"><h3 class="group-title">Pensions and annuities</h3><div class="section-note">Each card starts with Type, then the payment and valuation fields for that income stream. Recovery Age is the age at which each stream's cash dividend payout stops (the guaranteed payment continues for life).</div>`;
  incomeStreamSubsections().forEach((sub) => {
    let rs = rows
      .filter(isEditable)
      .filter((r) => r.section === "Income Streams" && r.subsection === sub);
    const typeRow = rs.find((r) => norm(r.label) === "type");
    rs = rs.filter((r) => norm(r.label) !== "type");
    const ordered = [...(typeRow ? [typeRow] : []), ...rs];
    html += `<details><summary>${esc(translatePersonPlaceholders(sub))}</summary><div class="field-list">${ordered.map(fieldHtml).join("")}</div></details>`;
  });
  if (globalRows.length)
    html += `<details open><summary>Plan-wide income stream settings</summary><div class="field-list">${globalRows.map(fieldHtml).join("")}</div></details>`;
  return html + "</div>";
}
function renderSsPolicySection() {
  const compactLabels = new Set([
    "claim_age",
    "monthly_pia_at_fra_today_dollars",
    "fra_age",
  ]);
  // Per-age SSA benefit-table entries (62-70) still drive the Monthly at
  // Claim Age lookup in the compact table above and the engine's benefit
  // calculation, but are not shown as an editable table on this page.
  const hiddenLabels = new Set(
    Array.from({ length: 9 }, (_, i) => `ss_benefit_age_${62 + i}`),
  );
  const excludedSubs = new Set(["funding discount"]);
  const rs = rows
    .filter(isEditable)
    .filter(
      (r) =>
        r.section === "Social Security" &&
        !compactLabels.has(norm(r.label)) &&
        !hiddenLabels.has(norm(r.label)) &&
        !excludedSubs.has(String(r.subsection || "").toLowerCase()),
    );
  const fundingRows = [
    findEditableRow("Social Security", "Funding Discount", "ss_funding_discount_year"),
    findEditableRow("Social Security", "Funding Discount", "ss_funding_discount_pct"),
  ].filter(Boolean);
  if (!rs.length && !fundingRows.length) return "";
  const bySub = {};
  rs.forEach((r) => {
    const k = String(r.subsection || "");
    (bySub[k] = bySub[k] || []).push(r);
  });
  if (fundingRows.length) {
    const policyKey =
      Object.keys(bySub).find((k) => k.toLowerCase() === "policy") || "Policy";
    bySub[policyKey] = (bySub[policyKey] || []).concat(fundingRows);
  }
  let html = `<div class="holdings retirement-income-section"><h3 class="group-title">Social Security policy &amp; benefit details</h3><div class="section-note">Household-wide spousal, survivor, and funding-discount policy settings.</div>`;
  Object.keys(bySub).forEach((sub) => {
    if (sub && sub.toLowerCase() !== "policy")
      html += `<div class="subsection-label">${esc(friendlyGroup({ section: "Social Security", subsection: sub }) || sub)}</div>`;
    html += `<div class="field-list inline-row">${bySub[sub].map(fieldHtml).join("")}</div>`;
  });
  return html + "</div>";
}
function renderRetirementIncome() {
  const ssInner = renderSsCompactTable() + renderSsPolicySection();
  const ssSummary =
    "Claim ages, FRA, per-age benefit tables, spousal/survivor policy, and funding discount";
  const ssSection =
    `<details class="allocation-policy-collapsed"><summary><b>Social Security</b><span class="small" style="margin-left:8px;font-weight:normal;color:var(--muted)">${esc(ssSummary)}</span></summary>` +
    ssInner +
    "</details>";
  return ssSection + renderIncomeStreamsSection();
}
async function seedWellnessOop() {
  try {
    const out = await api("/api/healthcare/seed", { method: "POST" });
    if (out && out.seeded > 0) {
      await loadAll({ source: planSource, preferLocal: false, silent: true });
      activeStep = "retirement_wellness";
      renderMain();
      showMessage(
        "Out-of-pocket detail fields added (" +
          out.seeded +
          " rows). Save Changes to persist.",
      );
    } else {
      showMessage("Out-of-pocket detail fields already present.");
    }
  } catch (e) {
    showMessage("Error seeding OOP fields: " + e.message, "error");
  }
}
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
async function estimateHousingFromState(stepNum) {
  const sub = "next_step_" + stepNum;
  const stateRow = rows.find(
    (r) =>
      r.section === "Housing" &&
      norm(r.subsection || "") === "next_step_" + stepNum &&
      norm(r.label) === "state",
  );
  const typeRow = rows.find(
    (r) =>
      r.section === "Housing" &&
      norm(r.subsection || "") === "next_step_" + stepNum &&
      norm(r.label) === "type",
  );
  const cityTypeRow = rows.find(
    (r) =>
      r.section === "Housing" &&
      norm(r.subsection || "") === "next_step_" + stepNum &&
      norm(r.label) === "city_type",
  );
  const popRow = rows.find(
    (r) =>
      r.section === "Housing" &&
      norm(r.subsection || "") === "next_step_" + stepNum &&
      norm(r.label) === "population_size",
  );
  const stateVal = stateRow
    ? String(valOf(stateRow) || "")
        .trim()
        .toUpperCase()
    : "";
  const typeVal = typeRow
    ? String(valOf(typeRow) || "purchase").toLowerCase()
    : "purchase";
  const isPurchase = typeVal === "purchase";
  if (!stateVal) {
    showMessage("Enter a state abbreviation first (e.g. IL, TX, FL).", "error");
    return;
  }
  if (isPurchase && cityTypeRow && !String(valOf(cityTypeRow) || "").trim()) {
    showMessage("Select an Area Type before estimating.", "error");
    return;
  }
  if (isPurchase && popRow && !String(valOf(popRow) || "").trim()) {
    showMessage("Enter a Population before estimating.", "error");
    return;
  }
  const cityTypeVal = cityTypeRow
    ? String(valOf(cityTypeRow) || "suburban").trim()
    : "suburban";
  const popVal = popRow
    ? String(valOf(popRow) || "20000").replace(/[^0-9]/g, "")
    : "20000";
  try {
    const out = await api("/api/housing/state-estimate", {
      method: "POST",
      body: JSON.stringify({
        state: stateVal,
        step: sub,
        type: typeVal,
        city_type: cityTypeVal,
        population_size: parseInt(popVal) || 20000,
      }),
    });
    if (!out || !out.estimate) {
      showMessage("No estimate available for " + stateVal, "error");
      return;
    }
    const e = out.estimate;
    const fieldMap = {
      purchase_price: isPurchase ? e.purchase_price : null,
      monthly_rent: !isPurchase ? e.monthly_rent : null,
      insurance_annual: e.insurance_annual,
      utilities_annual: e.utilities_annual,
      maintenance_annual: isPurchase ? e.maintenance_annual : null,
      re_tax_pct: isPurchase ? e.re_tax_pct : null,
      hoa_pct: isPurchase ? e.hoa_pct : null,
      mortgage_rate_pct: isPurchase ? e.mortgage_rate_pct : null,
    };
    let applied = 0;
    for (const [label, val] of Object.entries(fieldMap)) {
      if (val === null || val === undefined) continue;
      const r = rows.find(
        (x) =>
          x.section === "Housing" &&
          norm(x.subsection || "") === "next_step_" + stepNum &&
          norm(x.label) === label,
      );
      if (r) {
        const display =
          typeof val === "number" &&
          (label.includes("pct") ||
            label === "re_tax_pct" ||
            label === "hoa_pct" ||
            label === "mortgage_rate_pct")
            ? (val * 100).toFixed(2) + "%"
            : String(val);
        editValue(r.row_index, display, null);
        applied++;
      }
    }
    renderMain();
    showMessage(
      "Estimated values applied for " +
        stateVal +
        " (" +
        applied +
        " fields). Review and adjust as needed.",
    );
  } catch (err) {
    showMessage("Error fetching estimate: " + err.message, "error");
  }
}

function housingRentMonthlyValue() {
  const rentLabels = new Set(["monthly_rent"]);
  let maxRent = 0;
  (rows || []).forEach(function (r) {
    const lbl = norm((r && r.label) || "");
    if (rentLabels.has(lbl)) {
      const n = numberFromDisplay(valOf(r));
      if (n !== null && n > maxRent) maxRent = n;
    }
  });
  return maxRent;
}
function housingRentIsConfigured() {
  return housingRentMonthlyValue() > 0;
}
function rowIsRentInput(r) {
  const l = norm((r && r.label) || "");
  return l === "monthly_rent";
}
function housingAreaTypeSelect(row) {
  const cur = String(valOf(row) || "")
    .trim()
    .toLowerCase();
  const opts = ["urban", "suburban", "rural"];
  return `<select data-row="${row.row_index}" onchange="editValue(${row.row_index},this.value,this)" onfocus="showFieldHelp(${row.row_index})"><option value="">Select area type</option>${opts.map((o) => `<option value="${o}" ${norm(o) === norm(cur) ? "selected" : ""}>${titleWord(o)}</option>`).join("")}</select>`;
}

async function clearHousingNextStep(stepNum) {
  if (
    !(await showInAppConfirm(
      "All fields in Next Step " + stepNum + " will be reset.",
      { title: "Clear Next Step", confirmLabel: "Clear", variant: "warn" },
    ))
  )
    return;
  var sub = "next_step_" + stepNum;
  rows
    .filter(function (r) {
      return r.section === "Housing" && norm(r.subsection || "") === sub;
    })
    .forEach(function (r) {
      dirty.set(r.row_index, "");
    });
  renderMain();
}
function renderNextHousingStepSection(stepRows, stepLabel, stepNum) {
  if (!stepRows || !stepRows.length) return "";
  var typeRow = stepRows.find(function (r) {
    return norm(r.label) === "type";
  });
  var typeVal = typeRow
    ? String(valOf(typeRow) || "purchase").toLowerCase()
    : "purchase";
  var isPurchase = typeVal !== "rent";
  var stateRow = stepRows.find(function (r) {
    return norm(r.label) === "state";
  });
  var cityTypeRow = stepRows.find(function (r) {
    return norm(r.label) === "city_type";
  });
  var popRow = stepRows.find(function (r) {
    return norm(r.label) === "population_size";
  });
  var stateVal = stateRow ? String(valOf(stateRow) || "").trim() : "";
  var cityTypeVal = cityTypeRow ? String(valOf(cityTypeRow) || "").trim() : "";
  var popVal = popRow ? String(valOf(popRow) || "").trim() : "";

  // Purchase: State → Area Type → Population → [Estimate] → remaining fields
  // Rent: State → [Estimate] → remaining fields (no Area Type, Population, or HOA)
  var PURCHASE_FIRST = ["state", "city_type", "population_size"];
  var PURCHASE_REST = [
    "start_year",
    "end_year",
    "purchase_price",
    "down_payment",
    "mortgage_rate_pct",
    "insurance_annual",
    "utilities_annual",
    "maintenance_annual",
    "re_tax_pct",
    "hoa_pct",
  ];
  var RENT_FIRST = ["state"];
  var RENT_REST = [
    "start_year",
    "end_year",
    "monthly_rent",
    "insurance_annual",
    "utilities_annual",
  ];

  function pickRows(labels) {
    var out = [];
    labels.forEach(function (lbl) {
      var r = stepRows.find(function (x) {
        return norm(x.label) === lbl && x !== typeRow;
      });
      if (r) out.push(r);
    });
    return out;
  }
  var firstRows = pickRows(isPurchase ? PURCHASE_FIRST : RENT_FIRST);
  var restRows = pickRows(isPurchase ? PURCHASE_REST : RENT_REST);

  // Estimate button: Purchase requires all 3 inputs; Rent requires state only
  var estimateReady = isPurchase
    ? stateVal && cityTypeVal && popVal
    : !!stateVal;
  var estimateHint = isPurchase
    ? "Enter State, Area Type, and Population to enable"
    : "Enter State to enable";
  var estimateBtn =
    '<div class="section-note" style="margin-top:4px;margin-bottom:8px">' +
    '<button class="btn btn-sm" type="button" data-requires-app="1"' +
    (estimateReady ? "" : ' disabled title="' + estimateHint + '"') +
    ' onclick="estimateHousingFromState(' +
    stepNum +
    ')">' +
    "Estimate fields" +
    (stateVal ? " (" + esc(stateVal.toUpperCase()) + ")" : "") +
    "</button>" +
    ' <span class="small">Fills typical ' +
    (isPurchase ? "purchase" : "rental") +
    " costs for a 3BR/2BA home with at least a 40×40 ft backyard. All values are editable.</span></div>";

  var typeToggle = "";
  if (typeRow) {
    typeToggle =
      '<div class="field housing-type-field"><div class="field-label">Rent or Buy</div>' +
      '<div class="btn-toggle-group">' +
      '<button type="button" class="btn-toggle' +
      (isPurchase ? " active" : "") +
      '" onclick="editValue(' +
      typeRow.row_index +
      ",'purchase',null);renderMain()\">Buy</button>" +
      '<button type="button" class="btn-toggle' +
      (!isPurchase ? " active" : "") +
      '" onclick="editValue(' +
      typeRow.row_index +
      ",'rent',null);renderMain()\">Rent</button>" +
      '</div><div class="field-hint">Choose whether this housing step is a purchase or a rental. Rent stays visible even when the saved rent amount is currently zero.</div></div>';
  }

  var html =
    '<details open><summary class="section-header">' +
    esc(stepLabel) +
    '</summary><div class="section-body">';
  html +=
    '<button class="btn danger" type="button" onclick="clearHousingNextStep(' +
    stepNum +
    ')">Clear This Step</button>';
  html += typeToggle;
  if (firstRows.length)
    html +=
      '<div class="field-list">' +
      firstRows
        .map(function (r) {
          return norm(r.label) === "city_type"
            ? '<div class="field"><div class="field-label">Area Type</div>' +
                housingAreaTypeSelect(r) +
                "</div>"
            : fieldHtml(r);
        })
        .join("") +
      "</div>";
  html += estimateBtn;
  if (restRows.length)
    html +=
      '<div class="field-list">' + restRows.map(fieldHtml).join("") + "</div>";
  html += "</div></details>";
  return html;
}
function renderCollapsibleDomainBudgetSection(domain, openByDefault) {
  const title = domainBudgetTitle(domain);
  return `<details ${openByDefault ? "open" : ""} class="domain-budget-section" data-dkey="domain-budget:${esc(domain)}"><summary class="section-header">${esc(title)}</summary><div class="section-body">${renderDomainBudgetPage(domain, { embedded: true })}</div></details>`;
}
function renderSpendingHousing() {
  const rs = rowsForStep("spending_mortgage_events");
  const _CURRENT_MORTGAGE_EXCL = ["annual_real_estate_taxes"];
  const mortgage = rs.filter(
    (r) =>
      String(r.section || "").trim() === "Cashflow" &&
      norm(r.subsection || "") === "mortgage" &&
      !_CURRENT_MORTGAGE_EXCL.includes(norm(r.label || "")),
  );
  const homeRows = rs.filter(
    (r) =>
      String(r.section || "").trim() === "Other Assets" &&
      norm(r.subsection || "") === "home",
  );
  const _CURRENT_HOME_EXCL = [
    "city_type",
    "population_size",
    "hoa_pct",
    "hoa_annual",
    "homeowners_insurance_annual",
    "home_maintenance_annual",
    "utilities_annual",
  ];
  const housingOpRows = rs.filter(
    (r) =>
      String(r.section || "").trim() === "Housing" &&
      norm(r.subsection || "") === "current_home" &&
      !_CURRENT_HOME_EXCL.includes(norm(r.label || "")),
  );
  const homeImprovRows = rs.filter(
    (r) =>
      String(r.section || "").trim() === "Housing" &&
      norm(r.subsection || "") === "home_improvements",
  );
  const nextStep1Rows = rs.filter(
    (r) =>
      String(r.section || "").trim() === "Housing" &&
      norm(r.subsection || "") === "next_step_1",
  );
  const nextStep2Rows = rs.filter(
    (r) =>
      String(r.section || "").trim() === "Housing" &&
      norm(r.subsection || "") === "next_step_2",
  );
  const keyHomeRows = homeRows.filter((r) => {
    const l = norm(r.label || "");
    return homeValueLabelIsCanonical(r.label) || l === "home_basis";
  });

  // Determine if any next housing step is a Purchase — home improvements only show then.
  const nextStep1TypeRow = nextStep1Rows.find((r) => norm(r.label) === "type");
  const nextStep2TypeRow = nextStep2Rows.find((r) => norm(r.label) === "type");
  const nextStep1IsBuy =
    !nextStep1TypeRow ||
    String(valOf(nextStep1TypeRow) || "purchase").toLowerCase() === "purchase";
  const nextStep2IsBuy =
    !nextStep2TypeRow ||
    String(valOf(nextStep2TypeRow) || "purchase").toLowerCase() === "purchase";
  const anyNextStepIsBuy = nextStep1IsBuy || nextStep2IsBuy;

  let html = "";

  html += renderCollapsibleDomainBudgetSection("housing", true);

  html +=
    '<details><summary class="section-header">Current home</summary><div class="section-body">';
  html +=
    '<div class="section-note">Current mortgage payment timing and home value. Real-estate taxes, homeowners insurance, maintenance, and utilities are entered in Housing Budget Detail below. Click <button class="btn btn-sm" type="button" onclick="seedHousingRows()">Seed Housing Fields</button> to add insurance, utilities, maintenance, and next-housing-step fields if not yet present.</div>';
  if (mortgage.length)
    html +=
      '<div class="field-list">' + mortgage.map(fieldHtml).join("") + "</div>";
  if (housingOpRows.length)
    html +=
      '<div class="field-list">' +
      housingOpRows.map(fieldHtml).join("") +
      "</div>";
  if (keyHomeRows.length)
    html +=
      '<div class="field-list">' +
      keyHomeRows.map(fieldHtml).join("") +
      "</div>";
  html += "</div></details>";

  html += renderBaseHomeSaleRows(rs);

  if (nextStep1Rows.length) {
    html += renderNextHousingStepSection(
      nextStep1Rows,
      "Next Housing Step 1",
      1,
    );
  }
  if (nextStep2Rows.length) {
    html += renderNextHousingStepSection(
      nextStep2Rows,
      "Next Housing Step 2",
      2,
    );
  }
  if (!nextStep1Rows.length && !nextStep2Rows.length) {
    html +=
      '<details><summary class="section-header">Next Housing Step (Purchase)</summary><div class="section-body">';
    html +=
      '<div class="section-note">Next-step housing fields not found. Click <button class="btn btn-sm" type="button" onclick="seedHousingRows()">Seed Housing Fields</button> to add fields for future housing steps.</div>';
    html += "</div></details>";
  }

  // Home improvement projects — only relevant for purchase (not rent).
  if (homeImprovRows.length && anyNextStepIsBuy) {
    html +=
      '<details><summary class="section-header">Home improvement projects</summary><div class="section-body">';
    html +=
      '<div class="section-note">Planned improvement costs are entered here as part of Housing. Other pages may reference them read-only.</div>';
    html +=
      '<div class="field-list">' +
      homeImprovRows.map(fieldHtml).join("") +
      "</div>";
    html += "</div></details>";
  }

  return html;
}

const OTHER_ASSET_TYPES = [
  "Auto",
  "Boat",
  "Start-up Equity",
  "Art",
  "Collectible",
  "Other",
];
function otherAssetRows() {
  return rows
    .filter(isEditable)
    .filter(
      (r) =>
        r.section === "Other Assets" &&
        norm(r.subsection).startsWith("other_asset"),
    );
}
function otherAssetSubsections() {
  return [
    ...new Set(
      otherAssetRows()
        .map((r) => String(r.subsection || ""))
        .filter(Boolean),
    ),
  ].sort((a, b) => {
    const na = Number((a.match(/(\d+)/) || [])[1] || 0),
      nb = Number((b.match(/(\d+)/) || [])[1] || 0);
    return na - nb || a.localeCompare(b);
  });
}
function otherAssetRow(sub, label) {
  return otherAssetRows().find(
    (r) => r.subsection === sub && norm(r.label) === norm(label),
  );
}
function otherAssetTypeCell(r) {
  if (!r) return '<span class="small">—</span>';
  const cur = String(valOf(r) || "").trim();
  return `<select data-row="${r.row_index}" onchange="editValue(${r.row_index},this.value,this)" onfocus="showFieldHelp(${r.row_index})">${OTHER_ASSET_TYPES.map((t) => `<option value="${esc(t)}" ${norm(t) === norm(cur) ? "selected" : ""}>${esc(t)}</option>`).join("")}</select>`;
}
function otherAssetInputCell(sub, label, placeholder = "") {
  const r = otherAssetRow(sub, label);
  if (!r) return '<span class="small">—</span>';
  return `<input class="year-cell" type="${isDateField(r) ? "date" : "text"}" value="${esc(displayValueForInput(r, valOf(r)))}" placeholder="${esc(placeholder || r.schema?.default || "")}" oninput="editValue(${r.row_index},this.value,this)" onfocus="beginEdit(${r.row_index},this)" onblur="finishEdit(${r.row_index},this)">`;
}
function renderOtherAssetItemsTable() {
  const subs = otherAssetSubsections();
  let html = `<details open><summary>Other Asset Items</summary><div class="field-list"><div class="section-note">One row per non-portfolio asset — auto, boat, start-up equity, art, or collectible. Enter today's estimated value and as-of date. Use a positive annual rate for appreciating assets (e.g., collectibles, equity) and a negative rate for depreciating ones (e.g., vehicles).</div>`;
  html += `<div class="table-actions"><select id="newOtherAssetType">${OTHER_ASSET_TYPES.map((t) => `<option value="${esc(t)}">${esc(t)}</option>`).join("")}</select><button class="btn" type="button" data-requires-app="1" onclick="addOtherAssetItem()">Add asset</button></div>`;
  if (!subs.length) {
    return (
      html +
      "<p>No typed other assets yet. Add an asset to track an auto, boat, start-up equity, art, or other non-portfolio item.</p></div></details>"
    );
  }
  html += `<div class="matrix-wrap" role="region" aria-label="Other assets" tabindex="0"><table class="matrix-table"><thead><tr><th>Type</th><th>Name</th><th>Value</th><th>As-of date</th><th>Annual +/- %</th><th>Basis</th><th>Sell date</th><th></th></tr></thead><tbody>`;
  subs.forEach((sub) => {
    html += `<tr><td>${otherAssetTypeCell(otherAssetRow(sub, "type"))}</td><td>${otherAssetInputCell(sub, "name")}</td><td>${otherAssetInputCell(sub, "value")}</td><td>${otherAssetInputCell(sub, "as_of_date")}</td><td>${otherAssetInputCell(sub, "annual_appreciation_pct")}</td><td>${otherAssetInputCell(sub, "basis")}</td><td>${otherAssetInputCell(sub, "sell_date")}</td><td><button class="danger-link" type="button" onclick="deleteOtherAssetItem('${escJs(sub)}')">Delete</button></td></tr>`;
  });
  html +=
    '</tbody></table></div><p class="small">For appreciating assets such as start-up equity, art, or collectibles, enter a basis when you know the purchase price or tax basis. For depreciating assets, basis can be left blank unless it matters for a later sale scenario.</p></div></details>';
  return html;
}
async function addOtherAssetItem() {
  try {
    const typ =
      (document.getElementById("newOtherAssetType") || {}).value || "Auto";
    const out = await api("/api/other-asset/add", {
      method: "POST",
      body: JSON.stringify({ asset_type: typ }),
    });
    await loadAll({ source: planSource, preferLocal: false, silent: true });
    activeStep = "assets_special";
    showMessage(out.message || "Other asset added.");
  } catch (e) {
    showMessage("Error adding other asset: " + e.message, "error");
  }
}
async function deleteOtherAssetItem(subsection) {
  if (!subsection) return;
  if (
    !(await showInAppConfirm("This cannot be undone.", {
      title: "Delete Asset",
      confirmLabel: "Delete",
      variant: "danger",
    }))
  )
    return;
  try {
    const out = await api("/api/other-asset/delete", {
      method: "POST",
      body: JSON.stringify({ subsection }),
    });
    dirty.clear();
    lastBuildOk = false;
    await loadAll({ source: planSource, preferLocal: false, silent: true });
    activeStep = "assets_special";
    renderMain();
    showMessage(out.message || "Other asset deleted.");
  } catch (e) {
    showMessage("Error deleting other asset: " + e.message, "error");
  }
}

function noteReceivableRows() {
  return rows.filter(isEditable).filter((r) => r.section === "Note Receivable");
}
function noteReceivableSubsections() {
  return [
    ...new Set(
      noteReceivableRows()
        .map((r) => String(r.subsection || ""))
        .filter((sub) => /^Note\s+\d+$/i.test(sub) || sub === "Summary"),
    ),
  ].sort((a, b) => {
    const na = Number((a.match(/(\d+)/) || [])[1] || 0),
      nb = Number((b.match(/(\d+)/) || [])[1] || 0);
    return na - nb || a.localeCompare(b);
  });
}
function noteReceivableRow(sub, label) {
  return noteReceivableRows().find(
    (r) => r.subsection === sub && norm(r.label) === norm(label),
  );
}
function renderNoteInterestTable(sub) {
  const interestSub =
    sub === "Summary" ? "Interest by Year" : `${sub} Interest`;
  const rs = rows
    .filter(isEditable)
    .filter(
      (r) => r.section === "Note Receivable" && r.subsection === interestSub,
    );
  if (!rs.length) return "";
  const years = [
    ...new Set(rs.map((r) => String(r.label || "")).filter(Boolean)),
  ].sort(
    (a, b) =>
      (Number(a) || 0) - (Number(b) || 0) || String(a).localeCompare(String(b)),
  );
  let html = `<div class="section-note"><b>Interest by year:</b> Enter the expected taxable interest income from this note for each calendar year. This affects cash flow, taxable income, NIIT exposure, and projected note income.</div><div class="matrix-wrap" role="region" aria-label="Note receivable interest schedule" tabindex="0"><table class="matrix-table"><thead><tr><th>Schedule</th>${years.map((y) => `<th>${esc(y)}</th>`).join("")}</tr></thead><tbody><tr><td>Interest income</td>`;
  years.forEach((y) => {
    const r = rs.find((x) => String(x.label) === String(y));
    html += `<td>${r ? `<input class="year-cell" type="text" value="${esc(displayValueForInput(r, valOf(r)))}" aria-label="Note interest ${esc(y)}" oninput="editValue(${r.row_index},this.value,this)" onfocus="beginEdit(${r.row_index},this)" onblur="finishEdit(${r.row_index},this)">` : '<span class="small">—</span>'}</td>`;
  });
  html += `</tr></tbody></table></div><p class="small">Years run across the top. Enter dollars for each year the note is expected to pay interest.</p>`;
  return html;
}
function renderNoteReceivableTable() {
  const subs = noteReceivableSubsections();
  let html = `<div class="section-note">One or more promissory notes receivable. Each note has a descriptive name plus its own face value, payment schedule, and interest-by-year detail. The current note is named "RedMane Note".</div>`;
  html += `<div class="table-actions"><button class="btn" type="button" data-requires-app="1" onclick="addNoteReceivable()">Add note</button></div>`;
  if (!subs.length)
    return (
      html +
      "<p>No notes receivable yet. Add a note to track a promissory note.</p>"
    );
  subs.forEach((sub) => {
    const nameRow = noteReceivableRow(sub, "name");
    const label = nameRow ? String(valOf(nameRow) || sub) : sub;
    const body =
      noteReceivableRows()
        .filter((r) => r.subsection === sub && norm(r.label) !== "name")
        .map(fieldHtml)
        .join("") + renderNoteInterestTable(sub);
    html += `<details><summary><span>${esc(label)}</span> <button class="danger-link" type="button" onclick="deleteNoteReceivable('${escJs(sub)}')">Delete</button></summary><div class="field-list">${nameRow ? fieldHtml(nameRow) : ""}${body}</div></details>`;
  });
  return html;
}
async function addNoteReceivable() {
  try {
    const out = await api("/api/note-receivable/add", {
      method: "POST",
      body: JSON.stringify({}),
    });
    await loadAll({ source: planSource, preferLocal: false, silent: true });
    activeStep = "assets_special";
    showMessage(out.message || "Note added.");
  } catch (e) {
    showMessage("Error adding note: " + e.message, "error");
  }
}
async function deleteNoteReceivable(subsection) {
  if (!subsection) return;
  if (
    !(await showInAppConfirm("This cannot be undone.", {
      title: "Delete Note",
      confirmLabel: "Delete",
      variant: "danger",
    }))
  )
    return;
  try {
    const out = await api("/api/note-receivable/delete", {
      method: "POST",
      body: JSON.stringify({ subsection }),
    });
    dirty.clear();
    lastBuildOk = false;
    await loadAll({ source: planSource, preferLocal: false, silent: true });
    activeStep = "assets_special";
    renderMain();
    showMessage(out.message || "Note deleted.");
  } catch (e) {
    showMessage("Error deleting note: " + e.message, "error");
  }
}

function renderHsaPolicyOnOtherAssets(rs) {
  const gr = (rs || []).filter((r) => r.section === "HSA Policy");
  if (!gr.length) return "";
  const modeRow = gr.find(
    (r) =>
      norm(r.subsection) === "withdrawals" &&
      norm(r.label) === "hsa_withdrawal_mode",
  );
  const withdrawalRows = sortRowsByDependency(
    gr.filter((r) => norm(r.subsection) === "withdrawals"),
  );
  const contribRows = sortRowsByDependency(
    gr.filter((r) => norm(r.subsection) === "contributions"),
  );
  const rolloverRows = sortRowsByDependency(
    gr.filter((r) => norm(r.subsection) === "spousal_rollover"),
  );
  const otherRows = sortRowsByDependency(
    gr.filter(
      (r) =>
        !["withdrawals", "contributions", "spousal_rollover"].includes(
          norm(r.subsection),
        ),
    ),
  );
  let html = `<details open><summary>HSA Withdrawal Timing</summary><div class="field-list"><div class="section-note"><b>Projection control:</b> choose how the HSA is used in Cash Flow. <b>Spend as needed</b> uses HSA for qualified Wellness costs/gaps. <b>Annual percentage</b> and <b>Smooth window</b> use the start/end years below to schedule HSA withdrawals across the cash-flow projection.</div>${withdrawalRows.map(fieldHtml).join("")}</div></details>`;
  if (contribRows.length)
    html += `<details><summary>HSA Contributions</summary><div class="field-list"><div class="section-note">Contribution limits and eligibility feed annual HSA additions before Medicare eligibility.</div>${contribRows.map(fieldHtml).join("")}</div></details>`;
  if (rolloverRows.length)
    html += `<details><summary>HSA Spousal Rollover</summary><div class="field-list">${rolloverRows.map(fieldHtml).join("")}</div></details>`;
  if (otherRows.length)
    html += `<details><summary>Other HSA controls</summary><div class="field-list">${otherRows.map(fieldHtml).join("")}</div></details>`;
  return html;
}

function renderAssetsSpecial() {
  if (searchText.trim()) return renderFields("assets_special");
  const rs = rowsForStep("assets_special");
  const groups = [
    "Other Asset Items",
    "Note Receivable",
    "HSA",
    "529 Plans",
    "Equity Compensation",
    "LTC/Life Policy",
  ];
  let html = "";
  groups.forEach((g, idx) => {
    const gr = rs.filter((r) => friendlyGroup(r) === g);
    if (g === "Other Asset Items") {
      html += renderOtherAssetItemsTable();
      return;
    }
    if (g === "Note Receivable") {
      html += `<details open><summary>Note Receivable</summary><div class="field-list">${renderNoteReceivableTable()}</div></details>`;
      return;
    }
    if (g === "HSA") {
      html += renderHsaPolicyOnOtherAssets(rs);
      return;
    }
    if (g === "529 Plans") {
      if (optionalFunctionEnabled(ROW_MODULE_GATES["Education Funding"].key)) {
        html += `<details ${gr.length ? "" : "open"}><summary>529 Plans</summary><div class="field-list"><div class="section-note"><b>Purpose:</b> 529 plans are education savings accounts. Enter one section per beneficiary or goal, then add another 529 when a different beneficiary or goal should be tracked separately.</div>${gr.map(fieldHtml).join("")}<div class="table-actions"><button class="btn" type="button" data-requires-app="1" onclick="addEducation529Section()">Add 529 section</button></div></div></details>`;
      }
      return;
    }
    if (g === "LTC/Life Policy" && !ltcLifePolicyModuleEnabled()) return;
    if (
      g === "Equity Compensation" &&
      !optionalFunctionEnabled(ROW_MODULE_GATES["Equity Compensation"].key)
    )
      return;
    if (gr.length)
      html += `<details><summary>${esc(g)}</summary><div class="field-list">${gr.map(fieldHtml).join("")}</div></details>`;
  });
  html += renderHELOCInputsOnOtherPage();
  html += renderLiabilitiesTable();
  return html || '<div class="field-list"><p>No fields in this step.</p></div>';
}
async function addEducation529Section() {
  try {
    const out = await api("/api/education-529/add", {
      method: "POST",
      body: JSON.stringify({}),
    });
    await loadAll({ source: planSource, preferLocal: false, silent: true });
    activeStep = "assets_special";
    showMessage(out.message || "529 section added.");
  } catch (e) {
    showMessage("Error adding 529 section: " + e.message, "error");
  }
}

function renderHELOCInputsOnOtherPage() {
  const rs = rows.filter(
    (r) => isEditable(r) && r.section === "HELOC" && r.subsection === "Setup",
  );
  if (!rs.length) return "";
  const enabledRow = rs.find((x) => norm(x.label) === "heloc_enabled");
  if (!helocModuleEnabled())
    return enabledRow
      ? `<details><summary>HELOC modeling inputs</summary><div class="field-list"><div class="section-note">HELOC strategy is turned off. Turn it on below to reveal the borrowing assumptions.</div>${fieldHtml(enabledRow)}</div></details>`
      : "";
  const ordered = [
    "heloc_enabled",
    "heloc_credit_limit",
    "heloc_draw_end_year",
    "heloc_initial_rate_pct",
    "heloc_rate_drift_bps_yr",
    "heloc_repayment_years",
  ];
  const list = [];
  ordered.forEach((l) => {
    const r = rs.find((x) => norm(x.label) === l);
    if (r) list.push(r);
  });
  rs.forEach((r) => {
    if (!list.includes(r)) list.push(r);
  });
  return `<details open><summary>HELOC modeling inputs</summary><div class="field-list"><div class="section-note"><b>Current modeling source:</b> These are the same HELOC rows used by the projection. They are shown here with other liabilities so the borrowing assumption is not stranded on the Strategy page.</div>${list.map(fieldHtml).join("")}<div class="table-actions"><button class="btn" type="button" data-step-id="heloc_strategy">Open HELOC strategy page</button></div></div></details>`;
}

let holdingRowsCache = null,
  currentHoldingAccount = "ALL";
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
function csvEscape(v) {
  v = String(v ?? "");
  return /[",\n\r]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
}

function clientDataKey(row) {
  return [
    String(row?.[0] || "").trim(),
    String(row?.[1] || "").trim(),
    String(row?.[2] || "").trim(),
  ].join("\x1f");
}
function parseCsvTable(text) {
  const lines = String(text || "").split(/\r?\n/);
  const rows = [];
  let cur = "",
    q = false,
    row = [];
  function pushCell() {
    row.push(cur);
    cur = "";
  }
  function pushRow() {
    rows.push(row);
    row = [];
  }
  for (let li = 0; li < lines.length; li++) {
    const line = lines[li];
    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      if (ch === '"') {
        if (q && line[i + 1] === '"') {
          cur += '"';
          i++;
        } else q = !q;
      } else if (ch === "," && !q) {
        pushCell();
      } else cur += ch;
    }
    if (q) {
      cur += "\n";
    } else {
      pushCell();
      pushRow();
      cur = "";
    }
  }
  if (cur || row.length) {
    pushCell();
    pushRow();
  }
  while (
    rows.length &&
    rows[rows.length - 1].every((c) => !String(c || "").trim())
  )
    rows.pop();
  return rows;
}
function serializeCsvTable(rows) {
  return rows.map((r) => r.map(csvEscape).join(",")).join("\n") + "\n";
}
function mergeProtectedClientData(primary, fallback) {
  if (!fallback) return primary;
  const rows = parseCsvTable(primary);
  const fallbackRows = parseCsvTable(fallback);
  const keep = {};
  fallbackRows.forEach((r) => {
    const k = clientDataKey(r);
    if (PROTECTED_CLIENT_DATA_KEYS.has(k) && String(r[3] || "").trim())
      keep[k] = r[3];
  });
  let changed = false;
  rows.forEach((r) => {
    const k = clientDataKey(r);
    if (
      PROTECTED_CLIENT_DATA_KEYS.has(k) &&
      keep[k] &&
      !String(r[3] || "").trim()
    ) {
      while (r.length < 4) r.push("");
      r[3] = keep[k];
      changed = true;
    }
  });
  return changed ? serializeCsvTable(rows) : primary;
}
function isHoldingDateColumn(col) {
  return /date/i.test(String(col || ""));
}
function normalizeHoldingDateValue(v) {
  const raw = String(v ?? "").trim();
  if (!raw) return "";
  let m = raw.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
  if (m) {
    const y = +m[1],
      mo = +m[2],
      d = +m[3];
    if (mo >= 1 && mo <= 12 && d >= 1 && d <= 31)
      return `${String(y).padStart(4, "0")}-${String(mo).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
  }
  m = raw.match(/^(\d{1,2})[\/.-](\d{1,2})[\/.-](\d{2}|\d{4})$/);
  if (m) {
    let mo = +m[1],
      d = +m[2],
      y = +m[3];
    if (y < 100) y += y >= 70 ? 1900 : 2000;
    if (mo >= 1 && mo <= 12 && d >= 1 && d <= 31)
      return `${String(y).padStart(4, "0")}-${String(mo).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
  }
  return raw;
}
function ensureHoldingRows() {
  if (holdingRowsCache) return holdingRowsCache;
  const lines = String(holdingsText || "")
    .split(/\r?\n/)
    .filter((x) => x.trim());
  const parsed = lines.map(parseCsvLine);
  const header = (
    parsed[0] || [
      "account",
      "symbol",
      "purchase_date",
      "shares",
      "purchase_price",
      "lot_type",
      "note",
    ]
  ).map((x) => String(x || "").trim());
  const data = (parsed.length > 1 ? parsed.slice(1) : []).map((r) => {
    const o = {};
    header.forEach((h, i) => {
      let v = r[i] ?? "";
      if (isHoldingDateColumn(h)) v = normalizeHoldingDateValue(v);
      else v = String(v).trim();
      o[h] = v;
    });
    return o;
  });
  holdingRowsCache = { header, data };
  return holdingRowsCache;
}
function serializeHoldings() {
  const h = ensureHoldingRows();
  const lines = [h.header.map(csvEscape).join(",")];
  h.data.forEach((r) =>
    lines.push(h.header.map((col) => csvEscape(r[col] ?? "")).join(",")),
  );
  holdingsText = lines.join("\n") + "\n";
  return holdingsText;
}
function markHoldingsDirty() {
  serializeHoldings();
  holdingsChanged = true;
  lastBuildOk = false;
  updateUnsaved();
  setAppControls(appReady);
  scheduleStatusUpdate();
}
function holdingAccounts() {
  const h = ensureHoldingRows();
  return [
    ...new Set(
      h.data.map((r) => String(r.account || "").trim()).filter(Boolean),
    ),
  ].sort();
}
// Display-only: turn an internal account key like "Member_1_401k" into the
// person's nickname form ("Matt's 401k"). The stored account value stays the
// internal key (it is a data join key for pricing, YTD mapping, etc.); only
// the label shown to the user changes. Non-member accounts pass through as-is.
function accountDisplayLabel(account) {
  const s = String(account || "");
  const m = /^member[ _]([12])[ _](.+)$/i.exec(s);
  if (!m) return s;
  return (
    personDisplayName(Number(m[1])) + "'s " + m[2].replace(/_/g, " ").trim()
  );
}
function updateHolding(i, col, val) {
  ensureHoldingRows().data[i][col] = val;
  markHoldingsDirty();
}
function addHoldingLot(account = "") {
  const h = ensureHoldingRows();
  if (!account || account === "ALL")
    account =
      currentHoldingAccount !== "ALL"
        ? currentHoldingAccount
        : holdingAccounts()[0] || "New_Account";
  const row = {};
  h.header.forEach((c) => (row[c] = ""));
  row.account = account;
  row.symbol = "";
  row.purchase_date = "";
  row.shares = "";
  row.purchase_price = "";
  row.lot_type = "buy";
  h.data.push(row);
  currentHoldingAccount = account;
  markHoldingsDirty();
  renderMain();
  setTimeout(() => {
    const f = document.querySelector('.lot-table input[data-hcol="symbol"]');
    if (f) f.focus();
  }, 0);
}
async function addHoldingAccount() {
  const name = await showInAppPrompt("New account name:", "", {
    title: "Add Account",
    placeholder: "e.g. Fidelity IRA",
  });
  if (!name) return;
  currentHoldingAccount = name.trim();
  addHoldingLot(currentHoldingAccount);
}
async function deleteHoldingLot(i) {
  if (
    !(await showInAppConfirm("This cannot be undone.", {
      title: "Delete Lot",
      confirmLabel: "Delete",
      variant: "danger",
    }))
  )
    return;
  ensureHoldingRows().data.splice(i, 1);
  markHoldingsDirty();
  renderMain();
}
async function deleteHoldingAccount() {
  if (currentHoldingAccount === "ALL") {
    showMessage("Choose an account first.", "warn");
    return;
  }
  if (
    !(await showInAppConfirm(
      "All lots in " +
        accountDisplayLabel(currentHoldingAccount) +
        " will be permanently removed.",
      {
        title: "Delete Account",
        confirmLabel: "Delete All Lots",
        variant: "danger",
      },
    ))
  )
    return;
  const h = ensureHoldingRows();
  h.data = h.data.filter(
    (r) => String(r.account || "") !== currentHoldingAccount,
  );
  currentHoldingAccount = "ALL";
  markHoldingsDirty();
  renderMain();
}
function setHoldingAccount(v) {
  currentHoldingAccount = v;
  renderMain();
}
function holdingsImportPreviewMessage(out) {
  const d = out.date_range || {},
    dup = out.duplicate_candidates || {},
    acct = out.account_summary || {},
    sym = out.symbol_summary || {},
    dq = out.data_quality || {};
  const lines = [
    "Review holdings import preview before the table is replaced:",
    "",
    `Rows in file: ${out.received || 0}`,
    `Current rows: ${out.current_rows || 0}`,
    `Rows that would be staged: ${out.rows_added || 0}`,
    `Rows that would be replaced: ${out.rows_replaced || 0}`,
    `Total rows after staging: ${out.total_after || 0}`,
    `Purchase date range: ${d.earliest || "—"} through ${d.latest || "—"}`,
    `Duplicate candidates: ${dup.total || 0}`,
    `Estimated cost basis in file: ${ytdMoney(out.estimated_cost_basis)}`,
  ];
  if ((acct.new_accounts || []).length)
    lines.push(`New holding accounts: ${importPreviewList(acct.new_accounts)}`);
  if ((sym.symbols_not_in_security_master || []).length)
    lines.push(
      `Symbols not in security master: ${importPreviewList(sym.symbols_not_in_security_master)}`,
    );
  if (
    dq.missing_account_rows ||
    dq.missing_symbol_rows ||
    dq.invalid_share_rows ||
    dq.invalid_price_rows ||
    dq.unparseable_date_rows
  )
    lines.push(
      `Data quality flags: missing account ${dq.missing_account_rows || 0}, missing symbol ${dq.missing_symbol_rows || 0}, invalid shares ${dq.invalid_share_rows || 0}, invalid price ${dq.invalid_price_rows || 0}, date warnings ${dq.unparseable_date_rows || 0}`,
    );
  (out.warnings || []).forEach((w) => lines.push("Warning: " + w));
  lines.push(
    "",
    "Staged lots are held in the browser — use Save Changes to write them to disk.",
  );
  return lines.join("\n");
}
async function handleHoldingsCsvImport(input) {
  try {
    const file = input && input.files && input.files[0];
    if (!file) return;
    const text = await file.text();
    const preview = await api("/api/holdings/preview", {
      method: "POST",
      body: JSON.stringify({ mode: "replace", csv_text: text }),
    });
    if (
      !(await showInAppConfirm(holdingsImportPreviewMessage(preview), {
        title: "Confirm Holdings Import",
        confirmLabel: "Stage Import",
        variant: "warn",
      }))
    )
      return;
    holdingsText = text;
    holdingRowsCache = null;
    currentHoldingAccount = "ALL";
    markHoldingsDirty();
    noteSpecialSessionChange(
      "Investment holdings import staged",
      `CSV import preview accepted: ${preview.received || 0} lots staged.`,
    );
    renderMain();
    showMessage(
      `Holdings import staged: ${preview.received || 0} lots. Save Changes to persist.`,
    );
  } catch (e) {
    showMessage("Error previewing holdings import: " + e.message, "error");
  } finally {
    if (input) input.value = "";
  }
}

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
const LIABILITY_TYPES = [
  { v: "auto", t: "Auto loan" },
  { v: "heloc", t: "HELOC" },
  { v: "student_loan", t: "Student loan" },
  { v: "other", t: "Other" },
];
const LIABILITY_LABELS = {
  liability_id: "ID",
  type: "Type",
  label: "Name",
  balance: "Balance",
  interest_rate: "Interest rate %",
  monthly_payment: "Monthly payment",
  start_year: "Start year",
  payoff_year: "Payoff year",
  notes: "Notes",
};
// Fields revealed per type. balance + interest_rate are always shown; payment-style
// fields differ by how each liability is forecast.
const LIABILITY_TYPE_FIELDS = {
  auto: ["balance", "interest_rate", "monthly_payment", "payoff_year"],
  heloc: [
    "balance",
    "interest_rate",
    "monthly_payment",
    "start_year",
    "payoff_year",
  ],
  student_loan: ["balance", "interest_rate", "monthly_payment", "payoff_year"],
  other: [
    "balance",
    "interest_rate",
    "monthly_payment",
    "start_year",
    "payoff_year",
  ],
};
function liabilityFieldsForType(type) {
  return (
    LIABILITY_TYPE_FIELDS[String(type || "other").toLowerCase()] ||
    LIABILITY_TYPE_FIELDS.other
  );
}
function ensureLiabilityRows() {
  if (liabilityRowsCache) return liabilityRowsCache;
  const lines = String(liabilitiesText || "")
    .split(/\r?\n/)
    .filter((x) => x.trim());
  const parsed = lines.map(parseCsvLine);
  const header = (parsed[0] || LIABILITY_HEADER.slice()).map((x) =>
    String(x || "").trim(),
  );
  const data = (parsed.length > 1 ? parsed.slice(1) : []).map((r) => {
    const o = {};
    header.forEach((h, i) => {
      o[h] = String(r[i] ?? "").trim();
    });
    return o;
  });
  liabilityRowsCache = { header, data };
  return liabilityRowsCache;
}
function serializeLiabilities() {
  const h = ensureLiabilityRows();
  const lines = [h.header.map(csvEscape).join(",")];
  h.data.forEach((r) =>
    lines.push(h.header.map((col) => csvEscape(r[col] ?? "")).join(",")),
  );
  liabilitiesText = lines.join("\n") + "\n";
  return liabilitiesText;
}
function markLiabilitiesDirty() {
  serializeLiabilities();
  liabilitiesChanged = true;
  lastBuildOk = false;
  updateUnsaved();
  setAppControls(appReady);
  scheduleStatusUpdate();
}
function updateLiability(i, col, val) {
  const d = ensureLiabilityRows().data;
  if (d[i]) {
    d[i][col] = val;
    markLiabilitiesDirty();
  }
}
function setLiabilityType(i, val) {
  const d = ensureLiabilityRows().data;
  if (d[i]) {
    d[i].type = val;
    markLiabilitiesDirty();
    renderMain();
  }
}
function addLiability() {
  const h = ensureLiabilityRows();
  const row = {};
  h.header.forEach((c) => (row[c] = ""));
  row.liability_id = "liab_" + Date.now().toString(36);
  row.type = "auto";
  row.label = "";
  h.data.push(row);
  markLiabilitiesDirty();
  renderMain();
  setTimeout(() => {
    const f = document.querySelector('.lot-table input[data-lcol="label"]');
    if (f) f.focus();
  }, 0);
}
async function deleteLiability(i) {
  if (
    !(await showInAppConfirm("This cannot be undone.", {
      title: "Delete Liability",
      confirmLabel: "Delete",
      variant: "danger",
    }))
  )
    return;
  ensureLiabilityRows().data.splice(i, 1);
  markLiabilitiesDirty();
  renderMain();
}
function renderLiabilitiesTable() {
  const h = ensureLiabilityRows();
  const cols = [
    "label",
    "balance",
    "interest_rate",
    "monthly_payment",
    "start_year",
    "payoff_year",
    "notes",
  ];
  let html = `<details open><summary>Liabilities</summary><div class="field-list"><div class="section-note"><b>Purpose:</b> Track loans the plan must pay down over time. Choose a type, then enter the fields needed to forecast its cash flow. Each liability is amortized into the yearly cash-flow forecast and its outstanding balance reduces net worth. Auto and student loans use standard fixed amortization; HELOC line items amortize over the years to payoff. Leave a field blank to use sensible defaults (no monthly payment = interest-only unless a payoff year is set).</div><div class="table-actions"><button class="btn" type="button" data-requires-app="1" onclick="addLiability()">Add liability</button></div><div class="lot-table-wrap"><table class="lot-table"><thead><tr><th>Type</th>${cols.map((c) => `<th>${esc(LIABILITY_LABELS[c] || humanLabel(c))}</th>`).join("")}<th>Actions</th></tr></thead><tbody>`;
  if (!h.data.length) {
    html += `<tr><td colspan="${cols.length + 2}"><span class="small">No liabilities yet. Click "Add liability" to add one.</span></td></tr>`;
  }
  h.data.forEach((r, i) => {
    const type = String(r.type || "other").toLowerCase();
    const allowed = liabilityFieldsForType(type);
    html += "<tr>";
    html += `<td data-label="Type"><select onchange="setLiabilityType(${i},this.value)">${LIABILITY_TYPES.map((o) => `<option value="${o.v}" ${type === o.v ? "selected" : ""}>${esc(o.t)}</option>`).join("")}</select></td>`;
    cols.forEach((c) => {
      const lbl = esc(LIABILITY_LABELS[c] || humanLabel(c));
      if (c === "label" || c === "notes") {
        html += `<td data-label="${lbl}"><input data-lcol="${esc(c)}" type="text" value="${esc(r[c] || "")}" oninput="updateLiability(${i},'${esc(c)}',this.value)"></td>`;
        return;
      }
      const shown = allowed.includes(c);
      if (!shown) {
        html += `<td data-label="${lbl}"><span class="small">—</span></td>`;
        return;
      }
      const isMoney = c === "balance" || c === "monthly_payment";
      const isYear = c === "start_year" || c === "payoff_year";
      if (isMoney) {
        html += `<td data-label="${lbl}"><input class="tiny" data-lcol="${esc(c)}" type="text" value="${esc(currencyDisplay(r[c] || ""))}" oninput="updateLiability(${i},'${esc(c)}',currencyRaw(this.value))" onfocus="this.value=currencyRaw(this.value);this.select&&this.select()" onblur="this.value=currencyDisplay(this.value)"></td>`;
      } else if (isYear) {
        html += `<td data-label="${lbl}"><input class="tiny" data-lcol="${esc(c)}" type="number" step="1" value="${esc(r[c] || "")}" oninput="updateLiability(${i},'${esc(c)}',this.value)"></td>`;
      } else {
        html += `<td data-label="${lbl}"><input class="tiny" data-lcol="${esc(c)}" type="number" step="0.01" value="${esc(r[c] || "")}" oninput="updateLiability(${i},'${esc(c)}',this.value)"></td>`;
      }
    });
    html += `<td data-label="Actions"><button class="danger-link" onclick="deleteLiability(${i})">Delete</button></td></tr>`;
  });
  html += `</tbody></table></div></div></details>`;
  return html;
}
async function saveLiabilities() {
  if (!liabilitiesChanged) return { updated: 0 };
  const content = serializeLiabilities();
  const res = await fetch(apiUrl("/api/liabilities"), {
    method: "POST",
    headers: { "Content-Type": "text/csv" },
    body: content,
  });
  if (!res.ok) throw new Error(await res.text());
  liabilitiesText = content;
  liabilitiesChanged = false;
  return { updated: 1 };
}

function renderUserPricingSymbolTester() {
  return `<div id="userPricingSymbolTester" class="section-note"><b>Single-symbol live pricing tester:</b> Type one ticker to see every live pricing command and response trace without relying on the workbook build. <div class="row" style="margin-top:8px"><input id="userPricingTestSymbol" placeholder="Ticker, e.g. VTI" style="max-width:210px;text-transform:uppercase" onkeydown="if(event.key==='Enter')runUserLivePriceSymbolTest()"><button class="btn primary" type="button" onclick="runUserLivePriceSymbolTest()">Test live quote</button><span id="userPricingTestStatus" class="small"></span></div><div id="userPricingTestResult" style="margin-top:10px"></div></div>`;
}
function fmtUserPriceDiagnostic(v) {
  const n = Number(v);
  return Number.isFinite(n) && n > 0
    ? "$" +
        n.toLocaleString(undefined, {
          minimumFractionDigits: 2,
          maximumFractionDigits: 4,
        })
    : esc(v ?? "");
}
function renderUserJsonBlock(obj) {
  return `<pre class="code" style="display:block;white-space:pre-wrap;max-height:220px;overflow:auto;margin:6px 0">${esc(JSON.stringify(obj, null, 2))}</pre>`;
}
function renderUserProviderAttempt(a) {
  return `<div class="impact-card" style="margin:8px 0"><b>${esc(a.transport || "transport")}</b> · ${a.ok ? "ok" : "failed"} ${a.status_code ? "· HTTP " + esc(a.status_code) : ""} · ${esc(a.elapsed_ms ?? "")} ms<h4>Command sent</h4>${renderUserJsonBlock(a.command || {})}${a.cause ? `<h4>Failure cause</h4><p class="small">${esc(a.cause)}</p>` : ""}${a.exception ? `<h4>Exception</h4><p class="small">${esc(a.exception)}</p>` : ""}${a.response_preview ? `<h4>Response preview</h4><pre class="code" style="display:block;white-space:pre-wrap;max-height:160px;overflow:auto">${esc(a.response_preview)}</pre>` : ""}</div>`;
}
function renderUserProviderStep(s) {
  const ok = s.outcome === "success";
  return `<details ${ok ? "open" : ""}><summary><b>${esc(s.provider || "provider")} · ${esc(s.endpoint || "endpoint")}</b> — ${esc(s.outcome || "unknown")}${s.parsed_price ? " · " + fmtUserPriceDiagnostic(s.parsed_price) : ""}</summary><div style="padding:8px"><p class="small">${esc(s.parse_note || s.cause || "")}</p>${(s.attempts || []).map(renderUserProviderAttempt).join("") || `<p class="small">${esc(s.cause || "No command was sent for this provider.")}</p>`}</div></details>`;
}
function renderUserPricingTrace(r) {
  return `<div class="impact-card"><b>${esc(r.symbol || "")}</b> — ${esc(r.summary || "No summary")}<div class="mini-grid"><div><b>Selected provider</b><span>${esc(r.selected_provider || "none")}</span></div><div><b>Selected price</b><span>${r.selected_price ? fmtUserPriceDiagnostic(r.selected_price) : "—"}</span></div><div><b>Order</b><span>${esc((r.provider_order || []).join(" → "))}</span></div></div></div><details open><summary><b>Runtime and key diagnostics</b></summary>${renderUserJsonBlock({ generated_at_utc: r.generated_at_utc, config_backend: r.config_backend, timeout_seconds: r.timeout_seconds, max_retries: r.max_retries, requests_available: r.requests_available, effective_api_key_sources: r.effective_api_key_sources, proxy_environment_keys: r.proxy_environment_keys, cache_record: r.cache_record })}</details><h4>Provider command / response trace</h4>${(r.steps || []).map(renderUserProviderStep).join("")}`;
}
async function pollUserLivePriceSymbolJob(jobId, status, result) {
  for (let i = 0; i < 240; i++) {
    await new Promise((r) => setTimeout(r, 500));
    const out = await api(
      "/api/prices/test-symbol/status/" + encodeURIComponent(jobId),
      { timeoutMs: 9000 },
    );
    const trace = out.result || {
      symbol: out.symbol,
      summary: "Calling live providers...",
      steps: out.steps || [],
    };
    if (out.steps && (!trace.steps || !trace.steps.length))
      trace.steps = out.steps;
    if (result) result.innerHTML = renderUserPricingTrace(trace);
    const count = (trace.steps || []).length;
    if (status)
      status.textContent =
        out.status === "running"
          ? `Calling live providers... ${count} step${count === 1 ? "" : "s"} returned`
          : out.status === "completed"
            ? out.live_pricing_working
              ? "Live quote found"
              : "No live quote found"
            : "Diagnostic error";
    if (out.status === "completed" || out.status === "error") return out;
  }
  throw new Error(
    "Pricing tester timed out waiting for the local diagnostic job. A provider call may still be running; try a shorter timeout in Market Pricing settings.",
  );
}
async function runUserLivePriceSymbolTest() {
  const input = document.getElementById("userPricingTestSymbol");
  const status = document.getElementById("userPricingTestStatus");
  const result = document.getElementById("userPricingTestResult");
  const symbol = (input?.value || "").trim().toUpperCase();
  if (!symbol) {
    showMessage("Enter one ticker symbol first", "error");
    return;
  }
  if (status) status.textContent = "Starting diagnostic...";
  if (result)
    result.innerHTML =
      '<p class="small">Starting local diagnostic job. Provider commands and responses will appear as each service returns.</p>';
  try {
    const started = await api("/api/prices/test-symbol/start", {
      method: "POST",
      body: JSON.stringify({ symbol }),
      timeoutMs: 9000,
    });
    if (status) status.textContent = "Calling live providers...";
    const out = await pollUserLivePriceSymbolJob(
      started.job_id,
      status,
      result,
    );
    const liveOk = !!(
      out.live_pricing_working ||
      (out.result && out.result.success)
    );
    showMessage(
      liveOk
        ? "Live pricing tester found a quote"
        : "Live pricing tester completed with failures",
      liveOk ? "success" : "warn",
    );
  } catch (e) {
    const detail = String((e && e.message) || e || "Unknown error");
    if (result)
      result.innerHTML = `<div class="section-note warn"><b>Pricing tester could not reach the local API.</b><br>${esc(detail)}<br><br>Endpoint: <code>/api/prices/test-symbol/start</code>. If the browser says "Failed to fetch", restart the app and confirm the status indicator shows Ready.</div>`;
    if (status) status.textContent = "Error";
    showMessage("Pricing tester error: " + detail, "error");
  }
}
function renderHoldings() {
  const h = ensureHoldingRows();
  const accounts = holdingAccounts();
  const visible = h.data
    .map((r, i) => ({ r, i }))
    .filter(
      (x) =>
        currentHoldingAccount === "ALL" ||
        String(x.r.account || "") === currentHoldingAccount,
    );
  const cols = h.header.length
    ? h.header
    : [
        "account",
        "symbol",
        "purchase_date",
        "shares",
        "purchase_price",
        "lot_type",
        "note",
      ];
  let html = `<div class="holdings"><h3 class="group-title">Plan Holdings</h3><div class="section-note">Enter investment holdings by account and lot. A lot is a separate purchase, reinvestment, or cash position. Use CASH with price 1 for cash balances.</div><div class="section-note small"><b>CSV import columns:</b> <code>account, symbol, purchase_date, shares, purchase_price, lot_type, note</code> — date as YYYY-MM-DD, lot_type as <code>standard</code>, <code>reinvestment</code>, or <code>cash</code>. Download a template from your broker CSV export or use Export CSV backup in Settings first.</div>${renderUserPricingSymbolTester()}<input type="file" id="holdingsImportInput" accept=".csv,text/csv" style="display:none" onchange="handleHoldingsCsvImport(this)"><div class="table-actions"><select onchange="setHoldingAccount(this.value)"><option value="ALL" ${currentHoldingAccount === "ALL" ? "selected" : ""}>All accounts</option>${accounts.map((a) => `<option value="${esc(a)}" ${currentHoldingAccount === a ? "selected" : ""}>${esc(accountDisplayLabel(a))}</option>`).join("")}</select><button class="btn" onclick="addHoldingLot()">Add Lot</button><button class="btn" onclick="addHoldingAccount()">Add Account</button><button class="btn" type="button" data-requires-app="1" onclick="document.getElementById('holdingsImportInput').click()">Preview &amp; replace CSV</button><button class="btn danger" ${currentHoldingAccount === "ALL" ? "disabled" : ""} onclick="deleteHoldingAccount()">Delete Account</button></div><div class="lot-table-wrap"><table class="lot-table"><thead><tr>${cols.map((c) => `<th>${esc(humanLabel(c))}</th>`).join("")}<th>Actions</th></tr></thead><tbody>`;
  visible.forEach(({ r, i }) => {
    html +=
      "<tr>" +
      cols
        .map((c) => {
          const isDate = c.includes("date");
          const isPrice =
            norm(c).includes("price") ||
            norm(c).includes("cost") ||
            norm(c).includes("value");
          const isAccount = c === "account";
          const type = isDate ? "date" : "text";
          const cls = ["shares", "purchase_price"].includes(c) ? "tiny" : "";
          const display = isPrice
            ? currencyDisplay(r[c] || "", 4)
            : isAccount
              ? accountDisplayLabel(r[c] || "")
              : r[c] || "";
          const focus = isPrice
            ? `onfocus="showStepHelp('holdings');this.value=currencyRaw(this.value);this.select&&this.select()"`
            : isAccount
              ? `onfocus="showStepHelp('holdings');this.value=ensureHoldingRows().data[${i}].account||'';this.select&&this.select()"`
              : `onfocus="showStepHelp('holdings')"`;
          const input = isPrice
            ? `oninput="updateHolding(${i},'${esc(c)}',currencyRaw(this.value))" onblur="this.value=currencyDisplay(this.value,4)"`
            : isAccount
              ? `oninput="updateHolding(${i},'account',this.value)" onblur="this.value=accountDisplayLabel(this.value)"`
              : `oninput="updateHolding(${i},'${esc(c)}',this.value)"`;
          return `<td data-label="${esc(humanLabel(c))}"><input class="${cls}" data-hcol="${esc(c)}" type="${type}" value="${esc(display)}" ${input} ${focus}></td>`;
        })
        .join("") +
      `<td data-label="Actions"><button class="danger-link" onclick="deleteHoldingLot(${i})">Delete</button></td></tr>`;
  });
  html += `</tbody></table></div></div>`;
  return html;
}

function matrixKey(section) {
  return "matrix:" + section;
}
function markMatrixDirty(section) {
  lastBuildOk = false;
  updateUnsaved();
  if (
    row &&
    row.section === "Asset Allocation Policy" &&
    norm(row.label).includes("target_pct")
  ) {
    const box = document.getElementById("allocationTargetTotal");
    if (box) box.outerHTML = allocationTotalHtml();
  }
  scheduleStatusUpdate();
}
function matrixRows(section) {
  const target = norm(section);
  return rows.filter(isEditable).filter((r) => norm(r.section) === target);
}
function matrixYears(rs) {
  return [
    ...new Set(rs.map((r) => String(r.subsection || "")).filter(Boolean)),
  ].sort(
    (a, b) =>
      (Number(a) || 0) - (Number(b) || 0) || String(a).localeCompare(String(b)),
  );
}
function matrixPolicies(rs) {
  return [
    ...new Set(rs.map((r) => String(r.label || "")).filter(Boolean)),
  ].sort((a, b) => humanLabel(a).localeCompare(humanLabel(b)));
}
function findMatrixCell(rs, policy, year) {
  return rs.find(
    (r) => String(r.label) === policy && String(r.subsection) === year,
  );
}
function renderYearMatrix(section, title, intro, opts = {}) {
  const rs = matrixRows(section);
  if (!rs.length)
    return `<div class="holdings"><h3 class="group-title">${esc(title)}</h3><div class="section-note">No year-by-year rows were found for ${esc(section)}.</div></div>`;
  const years = matrixYears(rs);
  const policies = matrixPolicies(rs);
  const frozen = opts.frozenLabel || "Policy";
  let html = `<div class="holdings"><h3 class="group-title">${esc(title)}</h3><div class="section-note">${esc(intro)}</div>`;
  html += `<div class="table-actions"><button class="btn" type="button" onclick="showStepHelp(activeStep)">How to use this table</button></div>`;
  html += `<div class="matrix-wrap" role="region" aria-label="${esc(title)} matrix" tabindex="0"><table class="matrix-table"><thead><tr><th>${esc(frozen)}</th>${years.map((y) => `<th>${esc(y)}</th>`).join("")}</tr></thead><tbody>`;
  policies.forEach((pol) => {
    html += `<tr><td><span>${esc(humanLabel(pol))}</span></td>`;
    years.forEach((y) => {
      const r = findMatrixCell(rs, pol, y);
      html += `<td>${r ? `<input type="text" value="${esc(displayValueForInput(r, valOf(r)))}" aria-label="${esc(humanLabel(pol))} ${esc(y)}" oninput="editValue(${r.row_index},this.value,this)" onfocus="beginEdit(${r.row_index},this)" onblur="finishEdit(${r.row_index},this)">` : '<span class="small">—</span>'}</td>`;
    });
    html += "</tr>";
  });
  html += "</tbody></table></div>";
  html += `<p class="small">Tip: use <span class="kbd">Tab</span> or <span class="kbd">Return</span> to move across the editable year cells. Scroll horizontally to reach later years; the ${esc(frozen.toLowerCase())} column remains visible.</p>`;
  html += "</div>";
  return html;
}
function renderDeathBenefitsTable() {
  return renderYearMatrix(
    "Annuity Death Benefits",
    "Annuity death benefits",
    "Each row is a separate annuity policy. Each column is a calendar year. Enter the benefit payable to heirs if death occurs in that year.",
    { frozenLabel: "Policy" },
  );
}
function renderSpecialIncomeAnnuitiesInsurance() {
  if (searchText.trim()) return renderFields("annuity_death_benefits");
  return renderDeathBenefitsTable() + renderLifeInsurancePolicies();
}

const WITHDRAWAL_TYPES = [
  "RMD",
  "HSA",
  "IRA_elective",
  "Trust",
  "Roth",
  "Home_equity_tap",
];
const WITHDRAWAL_OPTIONS = {
  RMD: ["mandatory"],
  HSA: ["spend_as_needed", "annual_pct", "smooth_window"],
  IRA_elective: ["gross_up_tax", "net_amount", "skip_until_needed"],
  Trust: ["with_buffer", "spend_first", "preserve"],
  Roth: ["tax_free", "last_resort", "preserve_for_legacy"],
  Home_equity_tap: ["heloc_or_downsize", "heloc", "downsize", "never"],
};
function withdrawalPriorityRows() {
  return rows
    .filter(isEditable)
    .filter(
      (r) =>
        r.section === "Withdrawal Policy" &&
        /^Priority\s+\d+$/i.test(String(r.subsection || "")),
    )
    .sort(
      (a, b) =>
        (parseInt(String(a.subsection).replace(/\D+/g, "")) || 0) -
        (parseInt(String(b.subsection).replace(/\D+/g, "")) || 0),
    );
}
function withdrawalPriorityNumber(row) {
  return parseInt(String(row.subsection || "").replace(/\D+/g, "")) || 1;
}
function withdrawalOtherRows() {
  return rowsForStep("withdrawal_strategy").filter(
    (r) =>
      !(
        r.section === "Withdrawal Policy" &&
        /^Priority\s+\d+$/i.test(String(r.subsection || ""))
      ),
  );
}
function withdrawalOptionSelect(row, type) {
  const opts = WITHDRAWAL_OPTIONS[type] || [""];
  const cur = String(valOf(row) || opts[0] || "");
  return `<select aria-label="Withdrawal option for ${esc(type)}" onchange="setWithdrawalOrderField(${row.row_index},'option',this.value)">${opts.map((o) => `<option value="${esc(o)}" ${norm(o) === norm(cur) ? "selected" : ""}>${esc(humanLabel(o))}</option>`).join("")}</select>`;
}
function withdrawalTypeSelect(row) {
  const cur = String(row.label || "");
  return `<select aria-label="Withdrawal type for priority ${withdrawalPriorityNumber(row)}" onchange="setWithdrawalOrderField(${row.row_index},'type',this.value)">${WITHDRAWAL_TYPES.map((t) => `<option value="${esc(t)}" ${norm(t) === norm(cur) ? "selected" : ""}>${esc(formatAcronyms(humanLabel(t)))}</option>`).join("")}</select>`;
}
function withdrawalPrioritySelect(row) {
  const cur = withdrawalPriorityNumber(row);
  const max = Math.max(6, withdrawalPriorityRows().length);
  let html = `<select aria-label="Withdrawal priority" onchange="setWithdrawalOrderField(${row.row_index},'priority',this.value)">`;
  for (let i = 1; i <= max; i++)
    html += `<option value="${i}" ${i === cur ? "selected" : ""}>${i}</option>`;
  return html + "</select>";
}
async function setWithdrawalOrderField(rowIndex, field, value) {
  const priorityRows = withdrawalPriorityRows();
  const item = priorityRows.find((r) => r.row_index === rowIndex);
  if (!item) return;
  let order = priorityRows.map((r) => ({
    row_index: r.row_index,
    priority: withdrawalPriorityNumber(r),
    type: String(r.label || ""),
    option: String(valOf(r) || ""),
  }));
  const rec = order.find((x) => x.row_index === rowIndex);
  if (!rec) return;
  if (field === "priority") {
    const newPri = parseInt(value) || rec.priority;
    const other = order.find(
      (x) => x.priority === newPri && x.row_index !== rowIndex,
    );
    if (other) other.priority = rec.priority;
    rec.priority = newPri;
  } else if (field === "type") {
    rec.type = value;
    rec.option = (WITHDRAWAL_OPTIONS[value] || [""])[0] || "";
  } else if (field === "option") rec.option = value;
  order = order
    .sort((a, b) => a.priority - b.priority)
    .map((x, i) => Object.assign({}, x, { priority: i + 1 }));
  try {
    await api("/api/withdrawal-order", {
      method: "POST",
      body: JSON.stringify({ rows: order }),
    });
    dirty.clear();
    lastBuildOk = false;
    await loadAll({ source: planSource, preferLocal: false, silent: true });
    activeStep = "withdrawal_strategy";
    renderMain();
    showMessage("Withdrawal order updated. Save Changes when ready.");
  } catch (e) {
    showMessage("Could not update withdrawal order: " + e.message, "error");
  }
}
function renderWithdrawalOrderTable() {
  const prs = withdrawalPriorityRows();
  let html = `<details><summary>Withdrawal order</summary><div class="field-list"><div class="section-note"><b>Purpose:</b> Set the withdrawal cascade in a compact table. This directly affects the workbook cash-flow schedule, taxable income, RMD pressure, Roth preservation, trust withdrawals, HSA drawdown, and final liquidity timing.</div><div class="lot-table-wrap"><table class="lot-table withdrawal-order-table"><thead><tr><th>Priority</th><th>Withdrawal type</th><th>Option</th></tr></thead><tbody>`;
  if (!prs.length)
    html +=
      '<tr><td colspan="3"><span class="small">No withdrawal priority rows found. Reload the current plan to initialize withdrawal order rows.</span></td></tr>';
  prs.forEach((r) => {
    html += `<tr><td>${withdrawalPrioritySelect(r)}</td><td>${withdrawalTypeSelect(r)}</td><td>${withdrawalOptionSelect(r, String(r.label || ""))}</td></tr>`;
  });
  html +=
    '</tbody></table></div><p class="small">RMDs are mandatory income. Roth is normally preserved until non-Roth liquid sources are exhausted unless you intentionally change the cascade.</p></div></details>';
  return html;
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
  const misc = other.filter(
    (r) =>
      !(r.section === "HSA Policy" && r.subsection === "Withdrawals") &&
      !(
        r.section === "Withdrawal Policy" &&
        r.subsection === "Tax-Loss Harvesting"
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
    else
      visible = visible.concat(
        hsa.filter(
          (r) =>
            ![
              "hsa_withdrawal_pct",
              "hsa_withdrawal_start_year",
              "hsa_withdrawal_end_year",
              "withdrawal_window",
            ].includes(norm(r.label)) && r !== modeRow,
        ),
      );
    html += `<details><summary>HSA withdrawal policy</summary><div class="field-list"><div class="section-note"><b>Start here:</b> choose HSA withdrawal mode. The schedule fields below change based on that mode. Default is spend as needed, which hides annual-percentage and window controls.</div>${sortRowsByDependency(visible).map(fieldHtml).join("")}</div></details>`;
  }
  if (tlh.length)
    html += `<details><summary>Tax Loss Harvesting</summary><div class="field-list"><div class="section-note">Controls whether and how the projection harvests capital losses from taxable-account lots each year.</div>${sortRowsByDependency(tlh).map(fieldHtml).join("")}</div></details>`;
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
function rowsByLabel(labels) {
  const want = new Set(labels.map(norm));
  return rowsForStep("roth_conversion").filter((r) => want.has(norm(r.label)));
}
function rowByNormLabel(label) {
  const key = norm(label);
  return (
    rawRowsForStep("roth_conversion").find((r) => norm(r.label) === key) ||
    rows.find((r) => isEditable(r) && norm(r.label) === key)
  );
}
function orderedRowsByLabel(labels) {
  return labels.map(rowByNormLabel).filter(Boolean);
}
function rowsNotIn(labels) {
  const used = new Set(labels.map(norm));
  return rowsForStep("roth_conversion").filter((r) => !used.has(norm(r.label)));
}
function rothPolicyValue() {
  const r = rowByNormLabel("roth_conversion_policy");
  return String(r ? valOf(r) : "optimize_terminal_tax")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_");
}
function irmaaModeValue() {
  const r = rowByNormLabel("irmaa_guardrail_mode");
  return String(r ? valOf(r) : "AVOID_NEXT_TIER")
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, "_");
}
function boolishValue(r) {
  const v = String(r ? valOf(r) : "")
    .trim()
    .toLowerCase();
  return ["1", "true", "yes", "y", "on"].includes(v);
}
function renderRothRows(title, description, rs, open = false) {
  if (!rs.length) return "";
  return `<details class="roth-section" ${open ? "open" : ""}><summary>${esc(title)}</summary><div class="field-list"><div class="section-note">${esc(description)}</div>${sortRowsByDependency(rs).map(fieldHtml).join("")}</div></details>`;
}
function renderRothMissingNotice() {
  const present = new Set(
    rowsForStep("roth_conversion").map((r) => norm(r.label)),
  );
  const missing = ["roth_conversion_policy", "max_conversion_years"].filter(
    (x) => !present.has(norm(x)),
  );
  if (!missing.length) return "";
  return `<div class="missing-list"><h3>Roth controls need to be backfilled</h3><p>The page is missing ${missing.length} primary control${missing.length === 1 ? "" : "s"}: ${missing.map(humanLabel).join(", ")}. Reload the current plan or start the app again; v10 now backfills these rows into client_policy.csv without overwriting existing values.</p></div>`;
}
function renderRothConversion() {
  if (searchText.trim()) return renderFields("roth_conversion");
  const policy = rothPolicyValue();
  const irmaaMode = irmaaModeValue();
  const control = orderedRowsByLabel(["roth_conversion_policy"]);
  let strategy = [];
  let guardrail = [];
  let calibration = [];
  let scoring = [];
  const policyIsNone = [
    "none",
    "off",
    "disabled",
    "no_voluntary_conversions",
  ].includes(policy);
  const policyIsFixed = policy === "fixed_dollar" || policy === "fixed_amount";
  const policyIsBracket =
    policy === "fill_to_bracket" ||
    policy === "fill_current_bracket" ||
    policy === "fill_target_bracket";
  const policyIsIrmaa =
    policy === "fill_to_irmaa" || policy === "irmaa_guarded";
  const policyIsOptimizer =
    policy.includes("optimize") ||
    policy.includes("optimizer") ||
    policy === "balanced_retirement";
  if (policyIsFixed) {
    strategy = orderedRowsByLabel([
      "roth_fixed_annual_amount",
      ...ROTH_WINDOW_LABELS,
      "roth_headroom_usage_pct",
    ]);
  } else if (policyIsBracket) {
    strategy = orderedRowsByLabel([
      "roth_bracket_strategy",
      "roth_target_bracket_rate",
      "roth_headroom_usage_pct",
      ...ROTH_WINDOW_LABELS,
    ]);
  } else if (policyIsIrmaa) {
    strategy = orderedRowsByLabel([
      "roth_irmaa_target_tier",
      "roth_irmaa_headroom_usage_pct",
      "irmaa_annual_inflator",
      ...ROTH_WINDOW_LABELS,
    ]);
  } else if (policyIsOptimizer) {
    strategy = orderedRowsByLabel([
      "roth_objective_mode",
      "roth_bracket_strategy",
      "roth_target_bracket_rate",
      "roth_headroom_usage_pct",
      "roth_fixed_annual_amount",
      ...ROTH_WINDOW_LABELS,
    ]);
  } else if (policyIsNone) {
    strategy = orderedRowsByLabel(["max_conversion_years"]);
  } else {
    strategy = orderedRowsByLabel([
      "roth_bracket_strategy",
      "roth_target_bracket_rate",
      "roth_fixed_annual_amount",
      "roth_headroom_usage_pct",
      ...ROTH_WINDOW_LABELS,
    ]);
  }
  if (!policyIsNone && !policyIsIrmaa) {
    guardrail = orderedRowsByLabel(["irmaa_guardrail_mode"]);
    if (!IRMAA_OFF_MODES.includes(irmaaMode))
      guardrail = guardrail.concat(
        orderedRowsByLabel([
          "roth_irmaa_target_tier",
          "roth_irmaa_headroom_usage_pct",
          "irmaa_annual_inflator",
        ]),
      );
    if (irmaaMode === "CUSTOM_MAGI_CAP")
      guardrail = guardrail.concat(
        rowsForStep("roth_conversion").filter(
          (r) =>
            norm(r.label).includes("custom") && norm(r.label).includes("magi"),
        ),
      );
  }
  if (policyIsOptimizer) {
    calibration = orderedRowsByLabel([
      "roth_optimize_terminal_weight",
      "roth_optimize_lifetime_tax_weight",
      "roth_tax_discount_rate",
    ]);
    scoring = orderedRowsByLabel(ROTH_LEGACY_LABELS);
  } else if (policyIsBracket) {
    calibration = orderedRowsByLabel(["roth_tax_discount_rate"]);
  }
  const used = new Set(
    [...control, ...strategy, ...guardrail, ...calibration, ...scoring]
      .map((r) => r && norm(r.label))
      .filter(Boolean),
  );
  const other = rowsForStep("roth_conversion").filter(
    (r) =>
      !used.has(norm(r.label)) &&
      !norm(r.label).startsWith("roth_conversion_") &&
      !norm(r.label).startsWith("forced_"),
  );
  let html = renderRothMissingNotice();
  html += `<div class="field-list"><div class="section-note">Choose a conversion policy first — the page shows only the controls relevant to that choice. Fill-to-IRMAA uses the Medicare premium tier boundary as the conversion ceiling; choosing it hides the separate IRMAA guardrail to avoid duplicate controls. Bracket strategy options appear only for bracket-fill and optimizer policies.</div>${control.map(fieldHtml).join("")}</div>`;
  const policyLabel = policyIsFixed
    ? "Fixed-dollar conversion controls"
    : policyIsBracket
      ? "Bracket-fill controls"
      : policyIsIrmaa
        ? "IRMAA-fill controls"
        : policyIsOptimizer
          ? "Optimizer strategy controls"
          : policyIsNone
            ? "No voluntary Roth conversion"
            : "Active Roth strategy controls";
  const policyDesc = policyIsIrmaa
    ? "Fill-to-IRMAA uses the Medicare premium tier boundary as the conversion ceiling. Separate IRMAA guardrail controls are hidden to avoid duplication."
    : policyIsNone
      ? "No voluntary conversion controls are shown. Forced conversions remain available below — these represent decisions already made or imposed for this scenario."
      : "";
  html += renderRothRows(policyLabel, policyDesc, strategy, true);
  html += renderRothRows(
    "IRMAA guardrails",
    "For non-IRMAA-fill policies, this single behavior control determines whether IRMAA is ignored, warned only, or used as a sizing cap. Target tier and headroom appear only for cap-style modes.",
    guardrail,
    false,
  );
  html += renderRothRows(
    "Optimizer calibration",
    "Shown only when the active policy uses optimizer scoring or bracket calibration.",
    calibration,
    false,
  );
  html += renderRothRows(
    "Legacy, survivor, and estate scoring",
    "Shown only when the optimizer can use these scoring weights.",
    scoring,
    false,
  );
  html += renderForcedConversionsTable();
  html += renderRothRows(
    "Other Roth-related controls",
    "Rows found in Plan Data that are not part of the active simplified policy flow.",
    other,
    false,
  );
  return html;
}

function homeSaleScenarioYearRow(home) {
  return (
    home.find(
      (r) =>
        String(r.section || "").trim() === "Scenarios" &&
        norm(r.subsection) === "sell_home" &&
        (norm(r.label) === "home_sale_year" ||
          norm(r.label) === "planned_home_sale_year"),
    ) ||
    home.find(
      (r) =>
        norm(r.label) === "home_sale_year" ||
        norm(r.label) === "planned_home_sale_year",
    )
  );
}
function addUniqueRow(target, row) {
  if (row && !target.includes(row)) target.push(row);
}
function renderBaseHomeSaleRows(rs) {
  const base = rs
    .filter(rowIsBaseHomeSaleInput)
    .filter((r) => !rowIsRetiredScenarioHomeDuplicate(r));
  if (!base.length) return "";
  const year = base.find(
    (r) =>
      String(r.section || "").trim() === "Other Assets" &&
      norm(r.subsection) === "home" &&
      norm(r.label) === "home_sale_year",
  );
  const currentYear = new Date().getFullYear();
  const yearNum = year
    ? Number(String(valOf(year) || "0").replace(/[^0-9]/g, "")) || 0
    : 0;
  const active = yearNum >= currentYear; // Year always first; remaining fields only when a year is entered
  let yearFirst = [year].filter(Boolean);
  let restVisible = [];
  if (active) {
    base
      .filter(
        (r) =>
          r !== year &&
          !rowIsCanonicalHomeValue(r) &&
          !rowIsCanonicalHomeBasis(r),
      )
      .forEach((r) => {
        if (!restVisible.includes(r)) restVisible.push(r);
      });
  }
  const introNote = active
    ? '<div class="section-note">Sale year set — enter sale price, commission, and related details. Home value and basis are managed in Current Home above.</div>'
    : '<div class="section-note">Enter a home sale year to reveal sale detail fields.</div>';
  return `<details ${active ? "open" : ""}><summary class="section-header">Home Sale</summary><div class="field-list">${introNote}${yearFirst.map(fieldHtml).join("")}${restVisible.map(fieldHtml).join("")}</div></details>`;
}
function renderStressSellHomeRows(rs) {
  const stress = rs.filter(rowIsStressSellHomeInput);
  if (!stress.length) return "";
  const year = homeSaleScenarioYearRow(stress);
  const active = year && (Number(currencyRaw(valOf(year) || 0)) || 0) > 0;
  const canonicalValue = rs.find(rowIsCanonicalHomeValue);
  const canonicalBasis = rs.find(rowIsCanonicalHomeBasis);
  let visible = [];
  addUniqueRow(visible, canonicalValue);
  addUniqueRow(visible, canonicalBasis);
  if (active)
    stress
      .filter((r) => housingRentIsConfigured() || !rowIsRentInput(r))
      .forEach((r) => addUniqueRow(visible, r));
  else
    addUniqueRow(
      visible,
      year || stress.find((r) => norm(r.label).includes("home_sale_year")),
    );
  return `<details ${active ? "open" : ""}><summary>Sell Home stress test — scenario sheet only</summary><div class="field-list"><div class="section-note warning"><b>Scenario-only:</b> these Sell Home stress-test rows are used by the Scenario Analysis workbook sheet, but they do <b>not</b> change the base-plan Build Impact cards. To change headline terminal net worth, set the Base Plan Home Sale Year above. The Home Value and Home Basis shown here are shared canonical Home asset facts. The sale value used by this stress test is projected from canonical Home Value and appreciation.</div>${sortRowsByDependency(visible).map(fieldHtml).join("")}</div></details>`;
}
function renderHomeSaleScenarioRows(rs) {
  const has = rs.some(
    (r) => rowIsBaseHomeSaleInput(r) || rowIsStressSellHomeInput(r),
  );
  if (!has) return "";
  return renderBaseHomeSaleRows(rs) + renderStressSellHomeRows(rs);
}

const SCENARIO_SET_STORAGE_KEY = "retirement.scenario_sets.v1";
const SCENARIO_TEMPLATES = [
  {
    id: "conservative_markets",
    title: "Conservative markets",
    desc: "Raise inflation and lower portfolio return, then include both shocks in the combined stress test.",
    changes: [
      {
        subsection: "High Inflation",
        label: "inflation_override",
        value: "4.50%",
        why: "Tests sustained purchasing-power pressure.",
      },
      {
        subsection: "Low Return",
        label: "portfolio_return_override",
        value: "4.00%",
        why: "Tests lower expected portfolio growth.",
      },
      {
        subsection: "Combined Stress Test",
        label: "include_high_inflation",
        value: "TRUE",
        why: "Includes inflation in the combined stress case.",
      },
      {
        subsection: "Combined Stress Test",
        label: "include_low_return",
        value: "TRUE",
        why: "Includes low returns in the combined stress case.",
      },
    ],
  },
  {
    id: "spending_pressure",
    title: "Spending pressure",
    desc: "Model a higher-spending case and include it in the combined stress test.",
    changes: [
      {
        subsection: "Higher Spending",
        label: "spend_multiplier",
        value: "1.20",
        why: "Increases scenario spending by 20%.",
      },
      {
        subsection: "Combined Stress Test",
        label: "include_spend_more",
        value: "TRUE",
        why: "Includes the higher-spending case in the combined stress test.",
      },
    ],
  },
  {
    id: "retire_later_income",
    title: "Retire later bridge",
    desc: "Turn on the retire-later scenario with continued earned income assumptions.",
    changes: [
      {
        subsection: "Retire Later",
        label: "member_1_retire_year",
        value: "2029",
        why: "Moves the scenario retirement year later.",
      },
      {
        subsection: "Retire Later",
        label: "salary_override",
        value: "$50,000",
        why: "Adds scenario earned income during the bridge period.",
      },
      {
        subsection: "Retire Later",
        label: "income_growth_rate_override",
        value: "0.00%",
        why: "Keeps the bridge-income case easy to read.",
      },
      {
        subsection: "Combined Stress Test",
        label: "include_retire_later",
        value: "TRUE",
        why: "Includes retire-later in the combined case.",
      },
    ],
  },
  {
    id: "home_sale_liquidity",
    title: "Home-sale liquidity",
    desc: "Turn on the Sell Home stress case and include it in the combined stress test.",
    changes: [
      {
        subsection: "Sell Home",
        label: "home_sale_year",
        value: "2045",
        why: "Activates the scenario-only home sale timing.",
      },
      {
        subsection: "Sell Home",
        label: "home_sale_proceeds_account",
        value: "Member_2_Trust",
        why: "Routes proceeds to the configured account for the stress case.",
      },
      {
        subsection: "Combined Stress Test",
        label: "include_sell_home",
        value: "TRUE",
        why: "Includes home sale in the combined case.",
      },
    ],
  },
];
function scenarioRowsForManagement(rs) {
  const input = Array.isArray(rs) ? rs : rawRowsForStep("scenarios");
  return input.filter(
    (r) =>
      String(r.section || "").trim() === "Scenarios" &&
      !rowIsDivorceScenario(r) &&
      norm(r.subsection) !== "base",
  );
}
function scenarioRowKeyFromParts(section, subsection, label) {
  return [norm(section || "Scenarios"), norm(subsection), norm(label)].join(
    "::",
  );
}
function scenarioRowKey(row) {
  return scenarioRowKeyFromParts(
    row && row.section,
    row && row.subsection,
    row && row.label,
  );
}
function scenarioFieldName(row) {
  return `${friendlyGroup(row)} · ${humanLabel(row.label, row)}`;
}
function scenarioFindRow(subsection, label) {
  const wanted = scenarioRowKeyFromParts("Scenarios", subsection, label);
  return (
    scenarioRowsForManagement(rawRowsForStep("scenarios")).find(
      (r) => scenarioRowKey(r) === wanted,
    ) || null
  );
}
function scenarioTemplateById(id) {
  return SCENARIO_TEMPLATES.find((t) => t.id === id) || null;
}
function scenarioStoredSets() {
  try {
    const raw = localStorage.getItem(SCENARIO_SET_STORAGE_KEY);
    const arr = JSON.parse(raw || "[]");
    return Array.isArray(arr)
      ? arr.filter((x) => x && Array.isArray(x.items))
      : [];
  } catch (_e) {
    return [];
  }
}
function scenarioWriteSets(list) {
  try {
    localStorage.setItem(
      SCENARIO_SET_STORAGE_KEY,
      JSON.stringify((list || []).slice(0, 20)),
    );
    return true;
  } catch (e) {
    showMessage("Could not save scenario set locally: " + e.message, "error");
    return false;
  }
}
function scenarioCurrentItems() {
  const seen = new Set();
  return scenarioRowsForManagement(rawRowsForStep("scenarios"))
    .filter((r) => {
      const k = scenarioRowKey(r);
      if (seen.has(k)) return false;
      seen.add(k);
      return true;
    })
    .map((r) => ({
      key: scenarioRowKey(r),
      section: r.section,
      subsection: r.subsection,
      label: r.label,
      value: String(valOf(r) || ""),
      display_value: displayValueForInput(r, valOf(r) || ""),
      name: scenarioFieldName(r),
    }));
}
function scenarioActiveOverrideItems(rs) {
  return scenarioRowsForManagement(rs)
    .filter((r) => rowValueIsMeaningful(r) && norm(r.subsection) !== "base")
    .map((r) => ({
      key: scenarioRowKey(r),
      subsection: r.subsection,
      label: humanLabel(r.label, r),
      value: displayValueForInput(r, valOf(r) || ""),
      group: friendlyGroup(r),
    }));
}
function scenarioSetDiffItems(set) {
  const map = {};
  scenarioRowsForManagement(rawRowsForStep("scenarios")).forEach((r) => {
    map[scenarioRowKey(r)] = r;
  });
  return (set.items || [])
    .map((item) => {
      const r = map[item.key] || scenarioFindRow(item.subsection, item.label);
      if (!r)
        return {
          name: item.name || `${item.subsection} · ${item.label}`,
          current: "Not found",
          saved: item.display_value || item.value || "",
          missing: true,
        };
      const cur = displayValueForInput(r, valOf(r) || "");
      const saved = displayValueForInput(r, item.value || "");
      return {
        name: item.name || scenarioFieldName(r),
        current: cur || "blank",
        saved: saved || "blank",
        changed: String(cur) !== String(saved),
      };
    })
    .filter((x) => x.changed || x.missing);
}
function scenarioDiffTableHtml(items, emptyText) {
  const list = (items || []).slice(0, 10);
  if (!list.length)
    return `<p class="small">${esc(emptyText || "No differences from the current scenario values.")}</p>`;
  let html =
    '<table class="lot-table scenario-diff-table"><thead><tr><th>Assumption</th><th>Current</th><th>Saved / template</th></tr></thead><tbody>';
  list.forEach((x) => {
    html += `<tr><td>${esc(x.name || `${x.group || ""} ${x.label || ""}`)}</td><td>${esc(x.current || "blank")}</td><td>${esc(x.saved || x.value || "blank")}</td></tr>`;
  });
  html += "</tbody></table>";
  if ((items || []).length > list.length)
    html += `<p class="small">+${(items || []).length - list.length} additional difference${(items || []).length - list.length === 1 ? "" : "s"}.</p>`;
  return html;
}
function scenarioTemplateDiffItems(tpl) {
  return (tpl.changes || []).map((c) => {
    const r = scenarioFindRow(c.subsection, c.label);
    return {
      name: r ? scenarioFieldName(r) : `${c.subsection} · ${c.label}`,
      current: r ? displayValueForInput(r, valOf(r) || "") : "Not found",
      saved: c.value || "",
      changed: true,
    };
  });
}
function applyScenarioTemplate(id) {
  const tpl = scenarioTemplateById(id);
  if (!tpl) return;
  let applied = 0,
    missing = [];
  (tpl.changes || []).forEach((c) => {
    const r = scenarioFindRow(c.subsection, c.label);
    if (!r) {
      missing.push(`${c.subsection} / ${c.label}`);
      return;
    }
    editValue(r.row_index, c.value, null);
    applied++;
  });
  renderMain();
  showMessage(
    `${tpl.title} template applied to ${applied} scenario assumption${applied === 1 ? "" : "s"}${missing.length ? "; " + missing.length + " field(s) were not found." : ""}`,
  );
}
async function saveCurrentScenarioSet() {
  const name = await showInAppPrompt("Name this scenario set:", "", {
    title: "Save Scenario Set",
  });
  if (!name || !name.trim()) return;
  const items = scenarioCurrentItems();
  const set = {
    id: "scen_" + Date.now(),
    schema: "scenario_set_v1",
    name: name.trim(),
    created_at: new Date().toISOString(),
    items,
  };
  const sets = scenarioStoredSets().filter((s) => s.name !== set.name);
  sets.unshift(set);
  if (scenarioWriteSets(sets)) {
    showMessage("Scenario set saved locally.");
    renderMain();
  }
}
function applySavedScenarioSet(id) {
  const set = scenarioStoredSets().find((s) => s.id === id);
  if (!set) return;
  let applied = 0,
    missing = 0;
  (set.items || []).forEach((item) => {
    const r =
      scenarioRowsForManagement(rawRowsForStep("scenarios")).find(
        (x) => scenarioRowKey(x) === item.key,
      ) || scenarioFindRow(item.subsection, item.label);
    if (!r) {
      missing++;
      return;
    }
    editValue(r.row_index, item.value || "", null);
    applied++;
  });
  renderMain();
  showMessage(
    `Applied saved scenario set "${set.name}" to ${applied} assumption${applied === 1 ? "" : "s"}${missing ? "; " + missing + " saved field(s) were not found." : ""}`,
  );
}
async function deleteSavedScenarioSet(id) {
  const sets = scenarioStoredSets();
  const set = sets.find((s) => s.id === id);
  if (!set) return;
  if (
    !(await showInAppConfirm(
      '"' + set.name + '" will be permanently removed.',
      {
        title: "Delete Scenario Set",
        confirmLabel: "Delete",
        variant: "danger",
      },
    ))
  )
    return;
  if (scenarioWriteSets(sets.filter((s) => s.id !== id))) {
    showMessage("Scenario set deleted.");
    renderMain();
  }
}
function renderScenarioTemplatesHtml() {
  let html = '<div class="scenario-template-grid">';
  SCENARIO_TEMPLATES.forEach((t) => {
    html += `<div class="scenario-template-card"><div><h4>${esc(t.title)}</h4><p class="small">${esc(t.desc)}</p></div>${scenarioDiffTableHtml(scenarioTemplateDiffItems(t), "Template assumptions are already set this way.")}<button class="btn" type="button" onclick="applyScenarioTemplate('${escJs(t.id)}')">Apply template</button></div>`;
  });
  html += "</div>";
  return html;
}
function renderSavedScenarioSetsHtml() {
  const sets = scenarioStoredSets();
  if (!sets.length)
    return '<p class="small">No saved scenario sets yet. Save the current scenario assumptions when you want a reusable package of what-if overrides.</p>';
  let html = '<div class="scenario-set-list">';
  sets.forEach((set) => {
    const diffs = scenarioSetDiffItems(set);
    const date = set.created_at
      ? new Date(set.created_at).toLocaleString()
      : "";
    html += `<details class="scenario-set-card"><summary><b>${esc(set.name)}</b><span>${esc(date)} · ${(set.items || []).length} assumption${(set.items || []).length === 1 ? "" : "s"}</span></summary><div class="scenario-set-body">${scenarioDiffTableHtml(diffs, "This saved set matches the current scenario assumptions.")}<div class="table-actions"><button class="btn" type="button" onclick="applySavedScenarioSet('${escJs(set.id)}')">Apply saved set</button><button class="danger-link" type="button" onclick="deleteSavedScenarioSet('${escJs(set.id)}')">Delete</button></div></div></details>`;
  });
  html += "</div>";
  return html;
}
function renderCurrentScenarioOverridesHtml(rs) {
  const items = scenarioActiveOverrideItems(rs);
  if (!items.length)
    return '<p class="small">No active scenario-only overrides have meaningful values yet.</p>';
  let html =
    '<table class="lot-table scenario-overrides-table"><thead><tr><th>Scenario</th><th>Assumption</th><th>Current value</th></tr></thead><tbody>';
  items.slice(0, 16).forEach((x) => {
    html += `<tr><td>${esc(x.group)}</td><td>${esc(x.label)}</td><td>${esc(x.value)}</td></tr>`;
  });
  html += "</tbody></table>";
  if (items.length > 16)
    html += `<p class="small">+${items.length - 16} additional active override${items.length - 16 === 1 ? "" : "s"}.</p>`;
  return html;
}
function renderScenarioManagementPanel(rs) {
  return `<section class="scenario-management"><div class="scenario-management-head"><div><span class="eyebrow">Planning Workbench</span><h3>Scenario Change Sets</h3><p class="small">Templates stage common deterministic what-if overrides. Saved sets are browser-local change sets; review the diff, apply a set, then Save Changes, rebuild, and compare in the Planning Workbench.</p></div><button class="btn primary" type="button" onclick="saveCurrentScenarioSet()">Save current scenario set</button></div><details open><summary>Scenario templates</summary>${renderScenarioTemplatesHtml()}</details><details><summary>Saved named scenario sets</summary>${renderSavedScenarioSetsHtml()}</details><details><summary>Current scenario overrides</summary>${renderCurrentScenarioOverridesHtml(rs)}</details></section>`;
}

function renderScenarios() {
  if (searchText.trim()) return renderFields("scenarios");
  const rs = rowsForStep("scenarios");
  const economy = rs.filter(rowIsEconomyScenario);
  const stateComp = rs.filter(
    (r) => String(r.section || "").trim() === "State Comparison",
  );
  const homeSale = rs.filter((r) => rowIsHomeSaleAssumption(r));
  const other = rs.filter(
    (r) =>
      !rowIsEconomyScenario(r) &&
      !homeSale.includes(r) &&
      !stateComp.includes(r),
  );
  let html = `<div class="field-list"><div class="section-note"><b>Scenario Change Sets are deterministic planning cases.</b> Use the Stress Suite & Monte Carlo page for probabilistic or adverse-assumption testing. Economy shocks and scenario enable/year controls are grouped first because they determine which dependent assumptions matter. Home sale is split into a base-plan panel that affects Build Impact and a stress-test panel that affects scenario sheets only.</div></div>`;
  html += renderScenarioManagementPanel(rs);
  html += economy.length
    ? `<details open><summary>Economy</summary><div class="field-list">${sortRowsByDependency(economy).map(fieldHtml).join("")}</div></details>`
    : "";
  html += renderHomeSaleScenarioRows(rs);
  if (stateComp.length) {
    const hwRows = stateComp.filter(
      (r) => norm(r.subsection || "") === "homeowners_insurance",
    );
    const autoRows = stateComp.filter(
      (r) => norm(r.subsection || "") === "auto_insurance",
    );
    html += `<details><summary>State comparison — insurance costs</summary><div class="field-list"><div class="section-note">Compare insurance costs between Illinois (baseline) and a target relocation state. These are reference inputs only — they do not feed the projection model but appear in the scenario outputs for advisor review.</div>`;
    if (hwRows.length) {
      html += `<div class="subsection-label">Homeowners insurance</div>`;
      html += hwRows.map(fieldHtml).join("");
    }
    if (autoRows.length) {
      html += `<div class="subsection-label">Auto insurance</div>`;
      html += autoRows.map(fieldHtml).join("");
    }
    html += `</div></details>`;
  }
  html += renderFieldGroups(other);
  return html;
}

function mcEngineModeValue() {
  const r =
    rows.find(
      (x) =>
        isEditable(x) &&
        rowIsMonteCarlo(x) &&
        norm(x.label) === "mc_engine_mode",
    ) || rows.find((x) => isEditable(x) && norm(x.label) === "mc_engine_mode");
  const v = String(r ? valOf(r) : "advanced_exact_scalar")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_");
  return v === "quick_vectorized" || v === "vectorized"
    ? "quick_vectorized"
    : "advanced_exact_scalar";
}
function mcEngineRow() {
  return (
    rows.find(
      (x) =>
        isEditable(x) &&
        rowIsMonteCarlo(x) &&
        norm(x.label) === "mc_engine_mode",
    ) || rows.find((x) => isEditable(x) && norm(x.label) === "mc_engine_mode")
  );
}
function setMcEngineMode(value) {
  const r = mcEngineRow();
  if (!r) {
    showMessage(
      "Monte Carlo engine row is missing from Plan Data. Reload the current plan with this package to backfill it.",
      "error",
    );
    return;
  }
  editValue(r.row_index, value, null);
  renderMain();
}
function mcEngineToggleHtml(engine) {
  const mode = mcEngineModeValue();
  if (!engine)
    return '<p class="small">Monte Carlo engine row is missing from Plan Data. Reloading Plan Data with this package will add it automatically.</p>';
  return `<div class="mc-mode-toggle" role="radiogroup" aria-label="Monte Carlo engine mode"><button type="button" class="mc-mode-option ${mode === "quick_vectorized" ? "active" : ""}" aria-pressed="${mode === "quick_vectorized" ? "true" : "false"}" onclick="setMcEngineMode('quick_vectorized')"><b>Simple</b><span>Runs in seconds. Good for testing changes during plan entry. Approximate — not for final outputs.</span></button><button type="button" class="mc-mode-option ${mode === "advanced_exact_scalar" ? "active" : ""}" aria-pressed="${mode === "advanced_exact_scalar" ? "true" : "false"}" onclick="setMcEngineMode('advanced_exact_scalar')"><b>Complex</b><span>Runs fuller paths per trial. Use for final and advisor-ready workbooks where precision matters.</span></button></div><div class="small mc-mode-current">Saved value: ${esc(valOf(engine) || "advanced_exact_scalar")}</div>`;
}
function renderMonteCarloOptions() {
  if (searchText.trim()) return renderFields("monte_carlo_options");
  const rs = rowsForStep("monte_carlo_options");
  const engine = mcEngineRow();
  const mode = mcEngineModeValue();
  const quick = new Set([
    "mc_engine_mode",
    "mc_simulations",
    "mc_portfolio_sigma",
    "success_liquid_floor",
    "use_asset_class_covariance",
    "mc_home_equity_contingency",
    "mc_home_equity_haircut",
    "mc_home_equity_access_lag_years",
  ]);
  const advancedOnly = new Set([
    "mc_sensitivity_simulations",
    "stochastic_tax_brackets",
    "stochastic_irmaa",
    "healthcare_cost_shocks",
    "healthcare_shock_annual_prob",
    "healthcare_shock_mean_cost",
    "recenter_regime_returns",
    "stochastic_inflation",
    "inflation_sigma",
    "return_inflation_correlation",
    "return_serial_correlation",
  ]);
  const rowsToShow = rs.filter((r) => {
    const l = norm(r.label);
    if (l === "mc_engine_mode") return false;
    if (mode === "quick_vectorized") return quick.has(l);
    return (
      quick.has(l) ||
      advancedOnly.has(l) ||
      l.includes("monte_carlo") ||
      l.includes("simulation")
    );
  });
  let html =
    '<div class="field-list"><div class="section-note mc-engine-card"><b>Start here: choose the Monte Carlo engine.</b><p>Use <b>Simple</b> for fast assumption testing. Use <b>Complex</b> for final/advisor-ready workbooks because each simulated path runs the fuller planning engine.</p>' +
    mcEngineToggleHtml(engine) +
    "</div></div>";
  html += `<div class="field-list"><div class="section-note"><b>Showing ${mode === "quick_vectorized" ? "simple / quick-mode" : "complex / advanced-mode"} options.</b> ${mode === "quick_vectorized" ? "Only the settings that materially affect the faster approximation are shown. Switch to Complex to see sensitivity grids, stochastic tax/IRMAA, inflation-path, serial-correlation, and Wellness-shock controls." : "Advanced controls are shown because Complex mode runs fuller scalar paths and can use tax/IRMAA, inflation, sensitivity, Wellness-shock, and serial-correlation settings."}</div></div>`;
  html += renderFieldGroups(rowsToShow);
  return html;
}

function renderDivorceOptions() {
  return optionalFunctionEnabled("divorce_qdro")
    ? renderFields("divorce_options")
    : '<div class="field-list"><p>Divorce options are hidden until the Divorce/QDRO optional workbook module is enabled on Optional workbook modules.</p></div>';
}

function ytdMoney(v) {
  if (v === null || v === undefined || v === "") return "Not available";
  const n = Number(String(v).replace(/[$,]/g, ""));
  if (!Number.isFinite(n)) return "Not available";
  return n.toLocaleString(undefined, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  });
}
function ytdPct(v) {
  const n = Number(v);
  if (!Number.isFinite(n)) return "0.00%";
  return (n * 100).toFixed(2) + "%";
}
function ytdRawMoney(v) {
  return String(v ?? "")
    .replace(/[$,]/g, "")
    .trim();
}
function ytdTxnMoneyDisplay(v) {
  const raw = ytdRawMoney(v);
  if (raw === "") return "";
  const n = Number(raw);
  if (!Number.isFinite(n)) return String(v ?? "");
  const opts = {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: Number.isInteger(n) ? 0 : 2,
    maximumFractionDigits: 2,
  };
  return n.toLocaleString(undefined, opts);
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
function ytdAmountIsNegative(v) {
  const n = Number(ytdRawMoney(v));
  return Number.isFinite(n) && n < 0;
}
function updateYtdTxnAmount(i, input) {
  const raw = ytdRawMoney(input?.value);
  if (input)
    input.classList.toggle("ytd-negative-amount", ytdAmountIsNegative(raw));
  updateYtdTxn(i, "Amount", raw);
}
function focusYtdTxnAmount(input) {
  if (input) input.value = ytdRawMoney(input.value);
}
function blurYtdTxnAmount(i, input) {
  const raw = ytdRawMoney(input?.value);
  if (input) {
    input.value = ytdTxnMoneyDisplay(raw);
    input.classList.toggle("ytd-negative-amount", ytdAmountIsNegative(raw));
  }
  updateYtdTxn(i, "Amount", raw);
}
function ytdDate(v) {
  return String(v || "");
}
function showYtdLoadOverlay() {
  setBuildOverlay(
    true,
    "Loading transactions",
    "Reading saved transactions and account mappings. Large transaction histories can take a few seconds.",
    "waiting",
    "",
  );
  const overlay = document.getElementById("buildOverlay");
  if (overlay) overlay.classList.add("no-cancel");
}
function hideYtdLoadOverlay() {
  const overlay = document.getElementById("buildOverlay");
  if (overlay) overlay.classList.remove("no-cancel");
  hideBuildOverlay();
}
async function loadYtdStatus() {
  showYtdLoadOverlay();
  try {
    const out = await api(
      "/api/ytd/status?period=" + encodeURIComponent(ytdActualsPeriod),
    );
    ytdData = out;
    ytdTransactionsChanged = false;
    ytdAccountsChanged = false;
  } catch (e) {
    ytdData = {
      success: false,
      error: e.message,
      transactions: [],
      account_setup: [],
      summary: { enabled: false },
    };
  } finally {
    hideYtdLoadOverlay();
  }
}
async function loadTaxFreshnessStatus() {
  if (taxFreshnessLoading || taxFreshnessData) return;
  taxFreshnessLoading = true;
  try {
    const out = await api("/api/admin/tax-law-dashboard");
    taxFreshnessData = out;
  } catch (e) {
    taxFreshnessData = { success: false, rows: [] };
  }
  taxFreshnessLoading = false;
  renderMain();
}
// Last cached/live price per symbol, from the most recent build's pricing_diagnostics.json.
// Used to show current market value in Plan Data Review instead of cost basis.
async function loadHoldingsPriceData() {
  if (holdingsPriceLoading || holdingsPriceData) return;
  holdingsPriceLoading = true;
  try {
    const out = await api("/api/admin/diagnostics");
    const f = ((out && out.files) || []).find(function (x) {
      return x.name === "pricing_diagnostics.json";
    });
    holdingsPriceData = (f && f.json && f.json.prices) || {};
  } catch (e) {
    holdingsPriceData = {};
  }
  holdingsPriceLoading = false;
  renderMain();
}
function holdingsCurrentPrice(symbol) {
  const sym = String(symbol || "")
    .trim()
    .toUpperCase();
  if (sym === "CASH") return 1;
  if (
    holdingsPriceData &&
    Object.prototype.hasOwnProperty.call(holdingsPriceData, sym)
  ) {
    const n = Number(holdingsPriceData[sym]);
    if (Number.isFinite(n)) return n;
  }
  return null;
}
// Current value uses the last cached/live price; falls back to cost basis
// (purchase_price) only when no price is available for the symbol.
function holdingLotCurrentValue(h) {
  const shares = Number(h.shares || 0);
  const live = holdingsCurrentPrice(h.symbol);
  const price = live !== null ? live : Number(h.purchase_price || 0);
  return { price: price, value: shares * price, isEstimate: live === null };
}
function taxFreshnessBannerHtml() {
  if (!taxFreshnessData) {
    if (!taxFreshnessLoading) setTimeout(loadTaxFreshnessStatus, 0);
    return "";
  }
  const rows = (taxFreshnessData.rows || []).filter((r) => {
    const status = String(r.status || "").toUpperCase();
    if (status.includes("UNTIL_LAW_CHANGE")) return false;
    return r.blocking || status.includes("STALE") || status.includes("REVIEW");
  });
  if (!rows.length) return "";
  const items = rows
    .slice(0, 6)
    .map(
      (r) =>
        `<li><b>${esc(r.constant || "")}</b> (${esc(r.category || "")}) — last confirmed for ${esc(r.year || "unknown")}${r.last_reviewed ? ", reviewed " + esc(r.last_reviewed) : ""}: ${esc(r.status || "REVIEW_REQUIRED")}</li>`,
    )
    .join("");
  return `<div class="section-note warning"><b>${rows.length} reference constant${rows.length === 1 ? " needs" : "s need"} annual review.</b> These drive tax brackets, IRMAA, Social Security, state tax, and capital market return calculations — confirm against the current-year source before relying on projections.<ul class="inapp-modal-list">${items}</ul><button class="btn tiny" type="button" onclick="setStep('system_configuration');setTimeout(()=>openSystemConfigurationConsole(),0)">Open tax-law dashboard</button></div>`;
}
function setYtdDirtyButtonStates() {
  const txBtn = document.getElementById("ytdSaveTransactionsBtn");
  if (txBtn) txBtn.disabled = !ytdTransactionsChanged;
  const acctBtn = document.getElementById("ytdSaveAccountSetupBtn");
  if (acctBtn) acctBtn.disabled = !ytdAccountsChanged;
}
function markYtdTransactionsDirty() {
  ytdTransactionsChanged = true;
  lastBuildOk = false;
  updateUnsaved();
  setAppControls(appReady);
  setYtdDirtyButtonStates();
}
function markYtdAccountsDirty() {
  ytdAccountsChanged = true;
  lastBuildOk = false;
  updateUnsaved();
  setAppControls(appReady);
  setYtdDirtyButtonStates();
}
function updateYtdTxn(i, field, val) {
  if (!ytdData)
    ytdData = {
      transactions: [],
      account_setup: [],
      summary: { enabled: false },
    };
  if (!ytdData.transactions[i]) return;
  if (String(ytdData.transactions[i][field] ?? "") === String(val ?? ""))
    return;
  ytdData.transactions[i][field] = val;
  markYtdTransactionsDirty();
}
function addYtdTxn() {
  if (!ytdData)
    ytdData = {
      transactions: [],
      account_setup: [],
      summary: { enabled: false },
    };
  ytdData.transactions = ytdData.transactions || [];
  ytdData.transactions.unshift({
    Date: new Date().toISOString().slice(0, 10),
    Merchant: ytdFirstExistingValue("Merchant"),
    Category: ytdFirstExistingValue("Category"),
    Account: ytdFirstExistingValue("Account"),
    "Original Statement": "Manual",
    Notes: "",
    Amount: "0",
    Tags: "",
    Owner: "",
  });
  markYtdTransactionsDirty();
  renderMain();
}
async function deleteYtdTxn(i) {
  if (
    !(await showInAppConfirm("This cannot be undone.", {
      title: "Delete Transaction",
      confirmLabel: "Delete",
      variant: "danger",
    }))
  )
    return;
  ytdData.transactions.splice(i, 1);
  markYtdTransactionsDirty();
  renderMain();
}
async function saveYtdTransactions() {
  try {
    await api("/api/ytd/transactions/bulk", {
      method: "PUT",
      body: JSON.stringify({ transactions: ytdData.transactions || [] }),
    });
    await loadYtdStatus();
    setYtdDirtyButtonStates();
    spendingData = null;
    renderMain();
    showMessage("YTD transactions saved.");
  } catch (e) {
    showMessage("Error saving YTD transactions: " + e.message, "error");
  }
}
function updateYtdAccount(i, field, val) {
  if (!ytdData.account_setup[i]) return;
  ytdData.account_setup[i][field] = val;
  if (field === "Role" && val === "Investment")
    ytdData.account_setup[i]["Current Value"] = "";
  markYtdAccountsDirty();
  if (field === "Role") renderMain();
}
function addYtdAccount() {
  addSelectedYtdAccount();
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
async function downloadYtdTemplate() {
  try {
    const text = await fetchText("/api/ytd/transactions/template");
    downloadBlob("ytd_transactions_template.csv", text);
  } catch (e) {
    showMessage("Error downloading YTD template: " + e.message, "error");
  }
}
function importPreviewList(items, limit = 6) {
  items = Array.isArray(items) ? items : [];
  const shown = items.slice(0, limit).join(", ");
  return shown + (items.length > limit ? ` +${items.length - limit} more` : "");
}
function ytdImportPreviewMessage(out) {
  const d = out.date_range || {},
    dup = out.duplicate_candidates || {},
    acct = out.account_summary || {};
  const lines = [
    "Review transaction import preview before anything is written:",
    "",
    `Mode: ${out.mode || "replace"}`,
    `Rows in file: ${out.received || 0}`,
    `Current-year rows kept: ${out.valid_current_year_rows || 0}`,
    `Rows that would be added: ${out.rows_added || 0}`,
    `Rows that would be replaced: ${out.rows_replaced || 0}`,
    `Rows skipped: ${out.rows_skipped || 0}`,
    `Total rows after import: ${out.total_after || 0}`,
    `Date range: ${d.earliest || "—"} through ${d.latest || "—"}`,
    `Duplicate candidates: ${dup.total || 0}`,
  ];
  if (out.skipped_not_current_year)
    lines.push(
      `Non-current-year rows skipped: ${out.skipped_not_current_year}`,
    );
  if (out.unmapped_category_count)
    lines.push(
      `Unmapped categories: ${importPreviewList(out.unmapped_categories || [])}`,
    );
  if ((acct.new_accounts || []).length)
    lines.push(`New accounts/sources: ${importPreviewList(acct.new_accounts)}`);
  (out.warnings || []).forEach((w) => lines.push("Warning: " + w));
  lines.push("", "Save Changes after importing to persist the transactions.");
  return lines.join("\n");
}
async function handleYtdTransactionUpload(input) {
  try {
    const file = input && input.files && input.files[0];
    if (!file) return;
    const mode =
      (document.getElementById("ytdUploadMode") || {}).value || "replace";
    const text = await file.text();
    const preview = await api("/api/ytd/transactions/preview", {
      method: "POST",
      body: JSON.stringify({ mode, csv_text: text }),
    });
    if (
      !(await showInAppConfirm(ytdImportPreviewMessage(preview), {
        title: "Confirm Transaction Import",
        confirmLabel: "Import",
        variant: "warn",
      }))
    )
      return;
    const out = await api("/api/ytd/transactions/upload", {
      method: "POST",
      body: JSON.stringify({ mode, csv_text: text }),
    });
    await loadYtdStatus();
    renderMain();
    showMessage(
      `YTD transactions loaded: ${out.added || 0} added, ${out.skipped || 0} skipped (${out.skipped_not_current_year || 0} non-current-year), ${out.total || 0} current-year total.`,
    );
  } catch (e) {
    showMessage("Error uploading transactions: " + e.message, "error");
  } finally {
    if (input) input.value = "";
  }
}
async function deleteAllYtdTransactions() {
  const txCount =
    ytdData && ytdData.transactions ? ytdData.transactions.length : 0;
  const countLabel = txCount > 0 ? String(txCount) + " " : "all ";
  if (
    !(await showInAppConfirm(
      countLabel +
        "YTD transactions will be permanently deleted. Account setup rows will remain.",
      {
        title: "Delete All Transactions",
        confirmLabel: "Delete All",
        variant: "danger",
      },
    ))
  )
    return;
  try {
    await api("/api/ytd/transactions", {
      method: "DELETE",
      body: JSON.stringify({}),
    });
    await loadYtdStatus();
    renderMain();
    showMessage("All YTD transactions deleted.");
  } catch (e) {
    showMessage("Error deleting YTD transactions: " + e.message, "error");
  }
}
function ytdFilterOptions(field) {
  const vals = [
    ...new Set(
      (ytdData?.transactions || [])
        .map((r) => String(r[field] || "").trim())
        .filter(Boolean),
    ),
  ].sort((a, b) => a.localeCompare(b));
  return vals
    .map((v) => `<option value="${esc(v)}">${esc(v)}</option>`)
    .join("");
}
function ytdExistingValues(field) {
  return [
    ...new Set(
      (ytdData?.transactions || [])
        .map((r) => String(r[field] || "").trim())
        .filter(Boolean),
    ),
  ].sort((a, b) => a.localeCompare(b));
}
function ytdFirstExistingValue(field) {
  const vals = ytdExistingValues(field);
  return vals.length ? vals[0] : "";
}
function ytdSelectOptions(field, selected) {
  const cur = String(selected || "").trim();
  const vals = ytdExistingValues(field);
  if (cur && !vals.some((v) => v.toLowerCase() === cur.toLowerCase()))
    vals.unshift(cur);
  if (!vals.length) return '<option value="">No existing values</option>';
  let html = cur
    ? ""
    : '<option value="" selected disabled>Select existing ' +
      esc(field) +
      "</option>";
  html += vals
    .map(
      (v) =>
        `<option value="${esc(v)}" ${String(v) === cur ? "selected" : ""}>${esc(v)}</option>`,
    )
    .join("");
  return html;
}
function ytdSelectFieldHtml(i, field, value) {
  const disabled = ytdExistingValues(field).length ? "" : " disabled";
  return `<select class="ytd-existing-select"${disabled} onchange="updateYtdTxn(${i},'${field}',this.value)">${ytdSelectOptions(field, value)}</select>`;
}
function ytdTransactionAccounts() {
  const saved =
    ytdData?.summary?.transaction_accounts ||
    ytdData?.transaction_accounts ||
    [];
  const local = (ytdData?.transactions || [])
    .map((r) => String(r.Account || "").trim())
    .filter(Boolean);
  return [...new Set([...saved, ...local].filter(Boolean))].sort((a, b) =>
    a.localeCompare(b),
  );
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
function ytdAccountOptions(selected, includeBlank = false) {
  const opts = ytdTransactionAccounts();
  let html = includeBlank ? '<option value=""></option>' : "";
  html += opts
    .map(
      (o) =>
        `<option value="${esc(o)}" ${String(selected || "") === o ? "selected" : ""}>${esc(o)}</option>`,
    )
    .join("");
  if (selected && !opts.includes(selected))
    html += `<option value="${esc(selected)}" selected>${esc(selected)} (not in current transactions)</option>`;
  return html;
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
function ytdMissingAccountOptions() {
  const existing = new Set(
    (ytdData?.account_setup || [])
      .map((r) => String(r.Account || "").trim())
      .filter(Boolean),
  );
  return ytdTransactionAccounts()
    .filter((a) => !existing.has(a))
    .map((o) => `<option value="${esc(o)}">${esc(o)}</option>`)
    .join("");
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
function addSelectedYtdAccount() {
  if (!ytdData)
    ytdData = {
      transactions: [],
      account_setup: [],
      summary: { enabled: false },
    };
  ytdData.account_setup = ytdData.account_setup || [];
  const sel = document.getElementById("ytdAddAccountSelect");
  const acct = sel
    ? String(sel.value || "").trim()
    : ytdTransactionAccounts().find(
        (a) =>
          !(ytdData.account_setup || []).some(
            (r) => String(r.Account || "") === a,
          ),
      ) || "";
  if (!acct) {
    showMessage(
      "No unmapped transaction accounts are available to add. Use the inline Account/source name and Account type controls for pensions, annuities, offline assets, and other non-transaction rows.",
      "error",
    );
    return;
  }
  if (
    ytdData.account_setup.some((r) => String(r.Account || "").trim() === acct)
  ) {
    showMessage(
      "That transaction account is already in the mapping table.",
      "error",
    );
    return;
  }
  ytdData.account_setup.push(makeYtdAccountRow(acct, "Cash / spending", ""));
  markYtdAccountsDirty();
  renderMain();
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
function resetYtdTxnPage() {
  ytdTxPage = 0;
}
function setYtdTxnPage(page, total) {
  ytdTxPage = Math.max(0, Number(page) || 0);
  renderMain();
}
function ytdDateAwarePageBoundaries(rows, maxPerPage) {
  // Navigation is by date: never split a single day's transactions across two
  // pages. Pages accumulate rows until they reach maxPerPage, then close at
  // the next day boundary rather than mid-day (a single day busier than
  // maxPerPage becomes its own oversized page, which is expected/rare).
  const n = rows.length;
  if (!n) return [{ start: 0, end: 0 }];
  const pages = [];
  let start = 0;
  for (let i = 1; i <= n; i++) {
    const atEnd = i === n;
    const dayChanged = !atEnd && rows[i].r.Date !== rows[i - 1].r.Date;
    if (atEnd) {
      pages.push({ start, end: i });
      break;
    }
    if (dayChanged && i - start >= maxPerPage) {
      pages.push({ start, end: i });
      start = i;
    }
  }
  return pages;
}
function ytdTxPageBoundaries(rows) {
  return ytdTxSort.field === "Date"
    ? ytdDateAwarePageBoundaries(rows, YTD_TX_PAGE_SIZE)
    : null;
}
function ytdShortDate(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ""));
  if (!m) return String(iso || "");
  return `${Number(m[2])}/${Number(m[3])}`;
}
function ytdTxnPager(total, start, end, pages, firstDate, lastDate) {
  pages = Math.max(1, pages || 1);
  if (total <= YTD_TX_PAGE_SIZE && pages <= 1)
    return `<p class="small">Showing ${total} of ${total} matching transactions.</p>`;
  const canShowRange = ytdTxSort.field === "Date" && firstDate && lastDate;
  const rangeLabel = canShowRange
    ? `Showing ${ytdShortDate(firstDate)}–${ytdShortDate(lastDate)}`
    : `Showing ${start + 1}–${end} of ${total} matching transactions`;
  return `<div class="ytd-tx-pager"><span>${rangeLabel} · Page ${ytdTxPage + 1} of ${pages}${ytdTxSort.field === "Date" ? " · pages break on day boundaries" : ""}</span><div class="ytd-tx-pager-buttons"><button class="btn" type="button" ${ytdTxPage <= 0 ? "disabled" : ""} onclick="setYtdTxnPage(0,${total})">First</button><button class="btn" type="button" ${ytdTxPage <= 0 ? "disabled" : ""} onclick="setYtdTxnPage(${ytdTxPage - 1},${total})">Previous</button><button class="btn" type="button" ${ytdTxPage >= pages - 1 ? "disabled" : ""} onclick="setYtdTxnPage(${ytdTxPage + 1},${total})">Next</button><button class="btn" type="button" ${ytdTxPage >= pages - 1 ? "disabled" : ""} onclick="setYtdTxnPage(${pages - 1},${total})">Last</button></div></div>`;
}
// Extracts the 4-digit calendar year from a transaction Date value. Stored
// rows are normalized to ISO "YYYY-MM-DD" on save, but in-progress edits or
// freshly-imported rows may still be in another supported format, so fall
// back to the first 4-digit run in the string.
function ytdTxYear(dateStr) {
  const s = String(dateStr || "");
  const iso = /^(\d{4})-\d{2}-\d{2}/.exec(s);
  if (iso) return Number(iso[1]);
  const m = /\d{4}/.exec(s);
  return m ? Number(m[0]) : null;
}
// The calendar year the currently selected actuals period reports on
// (this year for Year-to-date, last calendar year for Last Year).
function ytdPeriodTargetYear() {
  return Number(ytdData?.summary?.current_year) || new Date().getFullYear();
}
// Rows matching the currently selected actuals period, independent of the
// search/category/account filters -- used to tell "no transactions for this
// period" apart from "the current filters matched nothing".
function ytdTxnsForPeriod() {
  const targetYear = ytdPeriodTargetYear();
  return (ytdData?.transactions || [])
    .map((r, i) => ({ r, i }))
    .filter((x) => ytdTxYear(x.r.Date) === targetYear);
}
function ytdFilteredTxns() {
  let rows = ytdTxnsForPeriod();
  const q = String(ytdTxSearch || "")
    .toLowerCase()
    .trim();
  if (q) {
    rows = rows.filter((x) =>
      Object.values(x.r).join(" ").toLowerCase().includes(q),
    );
  }
  if (ytdCategoryFilter)
    rows = rows.filter((x) => String(x.r.Category || "") === ytdCategoryFilter);
  if (ytdAccountFilter)
    rows = rows.filter((x) => String(x.r.Account || "") === ytdAccountFilter);
  const f = ytdTxSort.field,
    dir = ytdTxSort.dir === "asc" ? 1 : -1;
  rows.sort((a, b) => {
    let av = a.r[f] || "",
      bv = b.r[f] || "";
    if (f === "Amount") {
      av = Number(ytdRawMoney(av)) || 0;
      bv = Number(ytdRawMoney(bv)) || 0;
      return (av - bv) * dir;
    }
    return String(av).localeCompare(String(bv)) * dir;
  });
  return rows;
}
function setYtdSort(field) {
  if (ytdTxSort.field === field)
    ytdTxSort.dir = ytdTxSort.dir === "asc" ? "desc" : "asc";
  else ytdTxSort = { field, dir: "asc" };
  resetYtdTxnPage();
  renderMain();
}
function ytdHeader(label, field) {
  const mark =
    ytdTxSort.field === field ? (ytdTxSort.dir === "asc" ? " ▲" : " ▼") : "";
  return `<th><button class="table-sort" type="button" onclick="setYtdSort('${escJs(field)}')">${esc(label)}${mark}</button></th>`;
}
function ytdSparkline(series, actualKey, forecastKey, opts = null) {
  series = series || [];
  const vals = [];
  series.forEach((p) => {
    if (actualKey && Number.isFinite(Number(p[actualKey])))
      vals.push(Number(p[actualKey]));
    if (forecastKey && Number.isFinite(Number(p[forecastKey])))
      vals.push(Number(p[forecastKey]));
  });
  let min =
    opts && opts.scale === "range" ? Math.min(...vals) : Math.min(0, ...vals);
  let max = Math.max(...vals);
  if (!Number.isFinite(min)) min = 0;
  if (!Number.isFinite(max)) max = 1;
  if (max === min) max = min + 1;
  // Layout: y-axis labels at left (x=0-44), plot area x=50-330, x-axis labels below y=125
  const X0 = 50,
    X1 = 330,
    Y_TOP = 14,
    Y_BOT = 118;
  function px(i) {
    return X0 + i * ((X1 - X0) / Math.max(1, series.length - 1));
  }
  function py(v) {
    return (
      Y_BOT -
      (((Number.isFinite(v) ? v : min) - min) / (max - min)) * (Y_BOT - Y_TOP)
    );
  }
  function points(key) {
    if (!key) return "";
    return series
      .map((p, i) => {
        const v = Number(p[key]);
        return `${px(i).toFixed(1)},${Math.max(Y_TOP, Math.min(Y_BOT, py(v))).toFixed(1)}`;
      })
      .join(" ");
  }
  function fmtY(v) {
    const abs = Math.abs(v);
    if (abs >= 1000000) return "$" + (v / 1000000).toFixed(1) + "M";
    if (abs >= 1000) return "$" + Math.round(v / 1000) + "K";
    return "$" + Math.round(v);
  }
  const midVal = (min + max) / 2;
  const yLabels = `<text class="spark-axis" x="44" y="${(Y_BOT + 4).toFixed(0)}" text-anchor="end">${esc(fmtY(min))}</text><text class="spark-axis" x="44" y="${(py(midVal) + 4).toFixed(0)}" text-anchor="end">${esc(fmtY(midVal))}</text><text class="spark-axis" x="44" y="${(Y_TOP + 4).toFixed(0)}" text-anchor="end">${esc(fmtY(max))}</text>`;
  const xLabels = series
    .map(
      (p, i) =>
        `<text class="spark-axis" x="${px(i).toFixed(0)}" y="136" text-anchor="middle">${esc(p.label || "")}</text>`,
    )
    .join("");
  const forecastLine = forecastKey
    ? `<polyline class="forecast" points="${points(forecastKey)}"/>`
    : "";
  var svgStr = `<svg class="ytd-chart" viewBox="0 0 340 145" role="img" aria-label="YTD chart"><line x1="${X0}" y1="${Y_BOT}" x2="${X1}" y2="${Y_BOT}"/><line x1="${X0}" y1="${Y_TOP}" x2="${X0}" y2="${Y_BOT}"/>${yLabels}${forecastLine}<polyline class="actual" points="${points(actualKey)}"/>${xLabels}</svg>`;
  var sparkId = cacheChart(svgStr, "Chart");
  return (
    '<div class="ytd-chart-wrap chart-expandable" onclick="openCachedChart(\'' +
    sparkId +
    '\')" title="Click to expand"><div class="chart-expand-hint">&#x2922; Expand</div>' +
    svgStr +
    "</div>"
  );
}
function ytdMetricCard(
  title,
  actual,
  forecast,
  series,
  actualKey,
  forecastKey,
  extra = "",
  forecastLabel = "Projected full year",
  sparkOptions = null,
) {
  const isLastYear = !!ytdData?.summary?.is_last_year;
  const actualLabel = isLastYear ? "Actual (last year)" : "Actual YTD";
  return `<div class="ytd-metric"><h3>${esc(title)}</h3><div class="ytd-metric-values"><span><b>${ytdMoney(actual)}</b><small>${esc(actualLabel)}</small></span><span><b>${ytdMoney(forecast)}</b><small>${esc(forecastLabel)}</small></span></div>${ytdSparkline(series, actualKey, forecastKey, sparkOptions)}${extra ? `<p class="small">${esc(extra)}</p>` : ""}</div>`;
}
function renderYtdTopIncomeCategories() {
  return "";
}
function renderYtdTopCategories() {
  return "";
}
function renderYtdUploadPanel(enabled) {
  return `<div class="ytd-upload-panel"><input type="file" id="ytdUploadInput" accept=".csv,text/csv" style="display:none" onchange="handleYtdTransactionUpload(this)"><div><h3>Import transactions</h3><p class="small">Required CSV header: <code>Date, Merchant, Category, Account, Original Statement, Notes, Amount, Tags, Owner</code>. All rows with a valid date are imported, regardless of year. Use the Year-to-date / Last year toggle above to choose which calendar year's actuals are shown.</p></div><div class="table-actions"><select id="ytdUploadMode"><option value="replace">Replace all</option><option value="incremental">Add without replacing</option></select><button class="btn primary" type="button" data-requires-app="1" onclick="document.getElementById('ytdUploadInput').click()">Preview &amp; import CSV</button><button class="btn" type="button" data-requires-app="1" onclick="downloadYtdTemplate()">Download Template</button>${enabled ? `<button class="btn" type="button" data-requires-app="1" onclick="deduplicateYtdTransactions()">Remove Duplicates</button>` : ""} ${enabled ? `<button class="btn danger" type="button" data-requires-app="1" onclick="deleteAllYtdTransactions()">Delete All</button>` : ""}</div></div>`;
}
function renderYtdSummary() {
  const s = ytdData?.summary || { enabled: false };
  if (!s.enabled)
    return `<div class="section-note ytd-disabled"><b>YTD tracking is not enabled yet.</b> Upload transaction data to enable YTD spending, income, growth charts, transaction editing, and account mapping. All years of transaction history are kept; use the Year-to-date / Last year toggle to choose the reporting window once enabled.</div>`;
  const inv = s.investment_balance || {};
  const growthExtra = inv.actual_growth_available
    ? `Actual growth = mapped account current value − 12/31 prior-year balance. Investment rows use current holdings prices; non-investment rows use Current Value/Current Balance. Net investment cashflow is shown for diagnostics only.`
    : "Actual growth needs account setup rows with prior-year balances and either mapped holdings or current values.";
  const comp = s.cashflow_components || {};
  const spc = s.forecast?.spending_plan_components || {};
  const spendingExtra = s.forecast?.spending_annual_plan
    ? `Expected YTD = annual plan ${ytdMoney(s.forecast.spending_annual_plan)} × year complete (${esc(s.ytd_days || 0)}/${esc(s.year_days || 365)}). Core: ${ytdMoney(spc.core_spending)}. Mortgage and RE Tax: ${ytdMoney(spc.mortgage_and_re_tax ?? spc.mortgage)} (mortgage ${ytdMoney(spc.mortgage_payment)}, RE tax ${ytdMoney(spc.real_estate_taxes)}, annual adjustment ${ytdPct(spc.real_estate_tax_annual_adjustment_pct)}). Large discretionary: ${ytdMoney(spc.large_discretionary)}.`
    : s.forecast?.spending_plan_benchmark
      ? `Current annual core-spending benchmark: ${ytdMoney(s.forecast.spending_plan_benchmark)}.`
      : "";
  const growthSeries = s.growth_series || [];
  const windowLabel = s.is_last_year
    ? "Last year reporting window"
    : "YTD reporting window";
  return `<div class="ytd-status-grid"><div class="pill"><b>Earliest transaction</b><span>${esc(s.earliest_transaction_date || "—")}</span></div><div class="pill"><b>Latest transaction</b><span>${esc(s.latest_transaction_date || "—")}</span></div><div class="pill"><b>${esc(windowLabel)}</b><span>${esc(s.ytd_start || "—")} through ${esc(s.through_date || "—")}</span></div><div class="pill"><b>Transactions</b><span>${esc(s.transaction_count || 0)}</span></div><div class="pill"><b>Earned income</b><span>${ytdMoney(s.actual?.earned_income)}</span></div><div class="pill"><b>Investment income</b><span>${ytdMoney(s.actual?.investment_income)}</span></div><div class="pill"><b>Tax payments</b><span>${ytdMoney(s.actual?.taxes)}</span></div><div class="pill"><b>Net investment cashflow</b><span>${ytdMoney(inv.net_ytd_investment_cashflow)}</span></div></div><div class="ytd-metric-grid">${ytdMetricCard("YTD spending", s.actual?.spending, s.forecast?.spending, s.series, "actual_spending", "forecast_spending", spendingExtra, "Expected YTD")}${ytdMetricCard("YTD income", s.actual?.income, s.forecast?.income, s.series, "actual_income", "forecast_income", `Income categories only: ${(s.allowed_income_categories || []).join(", ") || "No income categories configured"}. Earned forecast remaining: ${ytdMoney(s.forecast?.earned_income_remaining)}. Note receivable included to date only: ${ytdMoney(comp.note_receivable_income)}. Investment/other income straight-lined: ${ytdMoney(s.forecast?.investment_income_annualized)} / ${ytdMoney(s.forecast?.other_income_annualized)}.`)}${ytdMetricCard("YTD growth", s.actual?.growth, inv.current_balance, growthSeries, "balance", null, growthExtra, "Current value", { scale: "range" })}</div>`;
}
function renderYtdTransactions() {
  if (ytdDuplicateGroups) return renderYtdDuplicateReview();
  const enabled = !!ytdData?.summary?.enabled;
  if (!enabled)
    return `<div class="ytd-disabled-table"><h3>Transactions</h3><p class="small">Upload a transaction CSV to enable the compact table.</p></div>`;
  const tx = ytdFilteredTxns();
  const total = tx.length;
  const periodHasAnyTx = ytdTxnsForPeriod().length > 0;
  const emptyMessage = periodHasAnyTx
    ? "No transactions match the current filters."
    : ytdActualsPeriod === "last_year"
      ? `No transactions from last year (${ytdPeriodTargetYear()}) — please import.`
      : `No transactions from this year (${ytdPeriodTargetYear()}) yet — please import.`;
  const boundaries = ytdTxPageBoundaries(tx);
  const pages = boundaries
    ? boundaries.length
    : Math.max(1, Math.ceil(total / YTD_TX_PAGE_SIZE));
  if (ytdTxPage >= pages) ytdTxPage = pages - 1;
  if (ytdTxPage < 0) ytdTxPage = 0;
  let start, end, pageRows;
  if (boundaries) {
    const b = boundaries[ytdTxPage] || { start: 0, end: total };
    start = b.start;
    end = b.end;
    pageRows = tx.slice(start, end);
  } else {
    start = ytdTxPage * YTD_TX_PAGE_SIZE;
    pageRows = tx.slice(start, start + YTD_TX_PAGE_SIZE);
    end = start + pageRows.length;
  }
  const firstDate = pageRows.length ? pageRows[0].r.Date : "";
  const lastDate = pageRows.length ? pageRows[pageRows.length - 1].r.Date : "";
  const pagerHtml = ytdTxnPager(total, start, end, pages, firstDate, lastDate);
  return `<div class="holdings ytd-section"><h3 class="group-title">Transactions</h3><div class="table-actions"><input class="search" style="max-width:260px" placeholder="Search transactions..." value="${esc(ytdTxSearch)}" oninput="ytdTxSearch=this.value;resetYtdTxnPage();renderMain()"><select onchange="ytdCategoryFilter=this.value;resetYtdTxnPage();renderMain()"><option value="">All categories</option>${ytdFilterOptions("Category").replace(`value=\"${esc(ytdCategoryFilter)}\"`, `value=\"${esc(ytdCategoryFilter)}\" selected`)}</select><select onchange="ytdAccountFilter=this.value;resetYtdTxnPage();renderMain()"><option value="">All accounts</option>${ytdFilterOptions("Account").replace(`value=\"${esc(ytdAccountFilter)}\"`, `value=\"${esc(ytdAccountFilter)}\" selected`)}</select><button class="btn" type="button" onclick="addYtdTxn()">Add transaction</button><button class="btn primary" id="ytdSaveTransactionsBtn" type="button" ${ytdTransactionsChanged ? "" : "disabled"} onclick="saveYtdTransactions()">Save transaction edits</button></div>${pagerHtml}<div class="lot-table-wrap ytd-table-wrap ytd-tx-table-wrap"><table class="lot-table ytd-tx-table"><thead><tr>${ytdHeader("Date", "Date")}${ytdHeader("Merchant", "Merchant")}${ytdHeader("Category", "Category")}${ytdHeader("Account", "Account")}${ytdHeader("Amount", "Amount")}<th>Statement</th><th>Notes</th><th>Tags</th><th>Owner</th><th></th></tr></thead><tbody>${pageRows.map(({ r, i }) => `<tr><td class="ytd-date-cell"><input class="ytd-date-input" value="${esc(r.Date || "")}" oninput="updateYtdTxn(${i},'Date',this.value)"></td><td>${ytdSelectFieldHtml(i, "Merchant", r.Merchant)}</td><td>${ytdSelectFieldHtml(i, "Category", r.Category)}</td><td>${ytdSelectFieldHtml(i, "Account", r.Account)}</td><td class="ytd-amount-cell"><input class="ytd-amount-input${ytdAmountIsNegative(r.Amount) ? " ytd-negative-amount" : ""}" value="${esc(ytdTxnMoneyDisplay(r.Amount))}" onfocus="focusYtdTxnAmount(this)" oninput="updateYtdTxnAmount(${i},this)" onblur="blurYtdTxnAmount(${i},this)"></td><td><input value="${esc(r["Original Statement"] || "")}" oninput="updateYtdTxn(${i},'Original Statement',this.value)"></td><td><input value="${esc(r.Notes || "")}" oninput="updateYtdTxn(${i},'Notes',this.value)"></td><td><input value="${esc(r.Tags || "")}" oninput="updateYtdTxn(${i},'Tags',this.value)"></td><td><input value="${esc(r.Owner || "")}" oninput="updateYtdTxn(${i},'Owner',this.value)"></td><td><button class="danger-link" type="button" onclick="deleteYtdTxn(${i})">Delete</button></td></tr>`).join("") || `<tr><td colspan="10"><span class="small">${esc(emptyMessage)}</span></td></tr>`}</tbody></table></div>${pagerHtml}</div>`;
}
function renderYtdAccounts() {
  const enabled = !!ytdData?.summary?.enabled;
  if (!enabled) return "";
  const accounts = ytdData.account_setup || [];
  const holdingCount = ytdInvestmentHoldingAccounts().length;
  const addSourceControls = `<input id="ytdManualAccountName" class="search ytd-add-source-name" placeholder="Account/source name"><select id="ytdManualAccountRole" title="Account/source type to add">${ytdAccountRoleOptions("Offline asset")}</select><button class="btn" type="button" title="Add the typed account/source with the selected type. No pop-up required." onclick="addManualYtdAccount()">Add account/source</button>`;
  return `<div class="holdings ytd-section"><h3 class="group-title">Accounts &amp; Sources</h3>${ytdRolloverBannerHtml()}<div class="section-note"><b>Where the money came from or is held:</b> Transaction accounts are added automatically from uploaded transactions. This section does not assign spending categories; it identifies account/source type, prior-year balance, current value, and any mapped investment account. Add non-transaction sources for annuities, pensions, Social Security, offline assets, real estate, notes, credit cards, loans, or other manual assets/liabilities. Investment current value is derived from mapped client_holdings.csv accounts.</div><div class="table-actions ytd-account-actions">${addSourceControls}<button class="btn primary" id="ytdSaveAccountSetupBtn" type="button" ${ytdAccountsChanged ? "" : "disabled"} onclick="saveYtdAccountSetup()">Save Accounts &amp; Sources</button><button class="btn" type="button" title="One-time recovery from a previous SQLite mirror, local Plan Data folder, or sibling extracted package." onclick="recoverYtdAccountSetup()">Recover previous setup</button></div>${holdingCount ? "" : '<p class="small">No investment holding accounts found in client_holdings.csv yet. Account mapping dropdowns will be blank until holdings are loaded.</p>'}<div class="lot-table-wrap ytd-account-wrap"><table class="lot-table ytd-account-table"><thead><tr><th>Account / Source</th><th>Account Type</th><th>Mapped Account</th><th>Prior Year End Balance</th><th>Current Value</th><th class="ytd-delete-cell">Action</th></tr></thead><tbody>${
    accounts
      .map((r, i) => {
        const role = String(r.Role || "Cash / spending");
        const isInv = role === "Investment";
        const isGrowth = ytdIsGrowthRole(role);
        return `<tr><td><input list="ytdAccountChoices" value="${esc(r.Account || "")}" oninput="updateYtdAccount(${i},'Account',this.value)" placeholder="Account or source name"></td><td><select onchange="updateYtdAccount(${i},'Role',this.value)">${ytdAccountRoleOptions(role)}</select></td><td><select onchange="updateYtdAccount(${i},'Mapped Investment Account',this.value)" ${isGrowth ? "" : "disabled"}>${ytdInvestmentOptions(r["Mapped Investment Account"] || "")}</select></td><td><input class="ytd-money-input" value="${esc(ytdAccountMoneyDisplay(r["Prior Year End Balance"]))}" onfocus="focusYtdAccountMoney(this)" oninput="updateYtdAccountMoney(${i},'Prior Year End Balance',this)" onblur="blurYtdAccountMoney(${i},'Prior Year End Balance',this)" placeholder="$0"></td><td><input class="ytd-money-input" value="${esc(ytdAccountMoneyDisplay(r["Current Value"]))}" ${(() => {
          const mapped = r["Mapped Investment Account"] || "";
          const annuityPension =
            ytdData?.summary?.annuity_pension_accounts || [];
          const isMappedAnnuity =
            isGrowth && !isInv && mapped && annuityPension.includes(mapped);
          return isInv
            ? 'disabled placeholder="From holdings"'
            : isMappedAnnuity
              ? 'disabled placeholder="From income stream"'
              : 'placeholder="$0"';
        })()} onfocus="focusYtdAccountMoney(this)" oninput="updateYtdAccountMoney(${i},'Current Value',this)" onblur="blurYtdAccountMoney(${i},'Current Value',this)"></td><td class="ytd-delete-cell"><button class="danger-link" type="button" onclick="deleteYtdAccount(${i})">Delete</button></td></tr>`;
      })
      .join("") ||
    `<tr><td colspan="6"><span class="small">No accounts yet. Upload transactions to seed transaction accounts automatically, or use the inline account/source controls for manual rows.</span></td></tr>`
  }</tbody></table><datalist id="ytdAccountChoices">${ytdTransactionAccounts()
    .map((o) => `<option value="${esc(o)}"></option>`)
    .join("")}</datalist></div></div>`;
}
function ytdBlendEnabledRow() {
  return rows.find(
    (r) =>
      r.section === "Cashflow" &&
      norm(r.subsection) === "spending" &&
      norm(r.label) === "ytd_blend_enabled",
  );
}
function ytdBlendToggleHtml() {
  if (!ytdData?.summary?.enabled) return "";
  const row = ytdBlendEnabledRow();
  if (!row) return "";
  const val = String(valOf(row) || "TRUE").toUpperCase();
  const on = val === "TRUE" || val === "YES";
  const dirtyHere = dirty.has(row.row_index);
  return `<div class="section-note${on ? "" : " warn"}"><b>Blend real YTD actuals into this plan's current-year projection:</b> ${on ? "On (recommended) — the current-year Net Worth/Cash Flow projection blends real spending/income tracked below into the remainder of this year." : "Off — this plan is modeled as fully hypothetical for the current year; real activity tracked below is not blended in."} <select onchange="editValue(${row.row_index},this.value,this);renderMain()"><option value="TRUE" ${on ? "selected" : ""}>On (recommended)</option><option value="FALSE" ${on ? "" : "selected"}>Off (fully hypothetical)</option></select>${dirtyHere ? ' <span class="badge dirty">Edited — Save Changes to apply</span>' : ""}</div>`;
}
function renderYtdTracking() {
  const enabled = !!ytdData?.summary?.enabled;
  return `<div class="holdings ytd-tracking"><h3 class="group-title">YTD spending and growth progress</h3>${enabled ? ytdActualsPeriodToggleHtml("tracking") : ""}${ytdBlendToggleHtml()}${renderYtdUploadPanel(enabled)}${renderYtdSummary()}</div>${renderYtdTransactions()}${renderYtdAccounts()}`;
}
function renderYtdCategoriesStep() {
  if (!ytdData && typeof loadYtdStatus === "function") {
    setTimeout(() => loadYtdStatus().then(() => renderMain()), 0);
  }
  return renderYtdAccounts();
}
function renderYtdTransactionsStep() {
  const enabled = !!ytdData?.summary?.enabled;
  return `<div class="holdings ytd-tracking"><h3 class="group-title">Income &amp; Expense Transactions</h3><div class="section-note"><b>Step 1 of 2 — Import transactions here.</b> After importing, go to <a href="#" onclick="setStep('spending_core');return false">Spending Categories</a> (step 2) to assign categories to your transactions. Use Accounts &amp; Sources below to identify account/source type and balances.</div>${enabled ? ytdActualsPeriodToggleHtml("transactions_step") : ""}${ytdBlendToggleHtml()}${renderYtdUploadPanel(enabled)}${renderYtdTransactions()}${renderYtdAccounts()}</div>`;
}

function deduplicateYtdTransactions() {
  if (!ytdData || !ytdData.transactions) {
    showMessage("No transactions loaded.");
    return;
  }
  const txns = ytdData.transactions;
  const keyFn = (r) =>
    [r.Date, r.Merchant, String(r.Amount || ""), r.Account, r.Category].join(
      "\x1f",
    );
  const groupMap = new Map();
  txns.forEach((r, i) => {
    const k = keyFn(r);
    if (!groupMap.has(k)) groupMap.set(k, []);
    groupMap.get(k).push(i);
  });
  const groups = [...groupMap.values()].filter((g) => g.length > 1);
  if (!groups.length) {
    showMessage("No duplicate transactions found.");
    return;
  }
  ytdDuplicateGroups = groups;
  ytdDuplicateSelected = new Set();
  groups.forEach((g) => g.slice(1).forEach((i) => ytdDuplicateSelected.add(i)));
  renderMain();
}
function ytdUpdateDedupDeleteBtn() {
  const btn = document.querySelector(".ytd-dedup-delete-btn");
  if (btn)
    btn.textContent = ytdDuplicateSelected.size
      ? "Delete " + ytdDuplicateSelected.size + " selected"
      : "Delete Selected";
}
function ytdToggleDuplicateSelect(i) {
  if (ytdDuplicateSelected.has(i)) ytdDuplicateSelected.delete(i);
  else ytdDuplicateSelected.add(i);
  const sel = ytdDuplicateSelected.has(i);
  const row = document.querySelector('tr[data-ytd-dup-row="' + i + '"]');
  if (row) {
    row.classList.toggle("ytd-dedup-sel-row", sel);
    const cb = row.querySelector("input[type=checkbox]");
    if (cb) cb.checked = sel;
    const gi = row.dataset.ytdDupGidx;
    const group = ytdDuplicateGroups && ytdDuplicateGroups[gi];
    if (group) {
      const allSel = group.every((idx) => ytdDuplicateSelected.has(idx));
      const ghdr = document.querySelector('tr[data-ytd-dup-ghdr="' + gi + '"]');
      if (ghdr) {
        const gcb = ghdr.querySelector("input[type=checkbox]");
        if (gcb) gcb.checked = allSel;
      }
    }
  }
  ytdUpdateDedupDeleteBtn();
}
function ytdToggleDuplicateGroup(gi, checked) {
  const group = ytdDuplicateGroups && ytdDuplicateGroups[gi];
  if (!group) return;
  group.forEach((i) => {
    if (checked) ytdDuplicateSelected.add(i);
    else ytdDuplicateSelected.delete(i);
    const row = document.querySelector('tr[data-ytd-dup-row="' + i + '"]');
    if (row) {
      row.classList.toggle("ytd-dedup-sel-row", checked);
      const cb = row.querySelector("input[type=checkbox]");
      if (cb) cb.checked = checked;
    }
  });
  ytdUpdateDedupDeleteBtn();
}
function ytdSelectAllDuplicates() {
  if (ytdDuplicateGroups)
    ytdDuplicateGroups.forEach((g) =>
      g.slice(1).forEach((i) => ytdDuplicateSelected.add(i)),
    );
  renderMain();
}
function ytdDeleteSelectedDuplicates() {
  if (!ytdDuplicateSelected.size) {
    showMessage("No rows selected for deletion.");
    return;
  }
  const sorted = [...ytdDuplicateSelected].sort((a, b) => b - a);
  sorted.forEach((i) => ytdData.transactions.splice(i, 1));
  markYtdTransactionsDirty();
  ytdDuplicateGroups = null;
  ytdDuplicateSelected = new Set();
  renderMain();
  showMessage(
    sorted.length +
      " duplicate transaction" +
      (sorted.length === 1 ? "" : "s") +
      " removed. Save to persist.",
  );
}
function ytdCancelDedup() {
  ytdDuplicateGroups = null;
  ytdDuplicateSelected = new Set();
  renderMain();
}
function renderYtdDuplicateReview() {
  const groups = ytdDuplicateGroups || [];
  const txns = (ytdData && ytdData.transactions) || [];
  let html = '<div class="holdings ytd-section">';
  html +=
    '<h3 class="group-title">Review Duplicates — ' +
    groups.length +
    " group" +
    (groups.length === 1 ? "" : "s") +
    "</h3>";
  html +=
    '<p class="small">Rows marked <b>Dup</b> are pre-checked for deletion. Uncheck any to keep, then click Delete Selected.</p>';
  html += '<div class="table-actions">';
  html +=
    '<button class="btn danger ytd-dedup-delete-btn" type="button" onclick="ytdDeleteSelectedDuplicates()">' +
    (ytdDuplicateSelected.size
      ? "Delete " + ytdDuplicateSelected.size + " selected"
      : "Delete Selected") +
    "</button>";
  html +=
    ' <button class="btn" type="button" onclick="ytdSelectAllDuplicates()">Re-select defaults</button>';
  html +=
    ' <button class="btn" type="button" onclick="ytdCancelDedup()">Cancel</button>';
  html += "</div>";
  html +=
    '<div class="lot-table-wrap ytd-dedup-wrap"><table class="lot-table ytd-dedup-table"><thead><tr><th></th><th>Date</th><th>Merchant</th><th>Category</th><th>Account</th><th>Amount</th><th>Statement</th></tr></thead><tbody>';
  groups.forEach((group, gi) => {
    const allSel = group.every((i) => ytdDuplicateSelected.has(i));
    html +=
      '<tr class="ytd-dedup-group-hdr" data-ytd-dup-ghdr="' +
      gi +
      '"><td colspan="7"><label style="cursor:pointer;display:flex;align-items:center;gap:6px"><input type="checkbox" ' +
      (allSel ? "checked" : "") +
      ' onchange="ytdToggleDuplicateGroup(' +
      gi +
      ',this.checked)"> <b>Group ' +
      (gi + 1) +
      "</b> — " +
      group.length +
      " rows</label></td></tr>";
    group.forEach((i, rowIdx) => {
      const r = txns[i] || {};
      const sel = ytdDuplicateSelected.has(i);
      html +=
        '<tr class="' +
        (sel ? "ytd-dedup-sel-row " : "") +
        (rowIdx === 0 ? "ytd-dedup-orig" : "") +
        '" data-ytd-dup-row="' +
        i +
        '" data-ytd-dup-gidx="' +
        gi +
        '"><td><label style="cursor:pointer;display:flex;align-items:center;gap:4px"><input type="checkbox" ' +
        (sel ? "checked" : "") +
        ' onchange="ytdToggleDuplicateSelect(' +
        i +
        ')">' +
        (rowIdx === 0
          ? '<span class="badge ok">Keep</span>'
          : '<span class="badge bad">Dup</span>') +
        "</label></td><td>" +
        esc(r.Date || "") +
        "</td><td>" +
        esc(r.Merchant || "") +
        "</td><td>" +
        esc(r.Category || "") +
        "</td><td>" +
        esc(r.Account || "") +
        '</td><td class="ytd-amount-cell">' +
        esc(ytdTxnMoneyDisplay(r.Amount)) +
        "</td><td>" +
        esc(r["Original Statement"] || "") +
        "</td></tr>";
    });
    html += '<tr class="ytd-dedup-spacer"><td colspan="7"></td></tr>';
  });
  html += "</tbody></table></div></div>";
  return html;
}
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
function _isViewingDetailedResults() {
  return (
    activeStep === "detailed_results" ||
    (activeStep === "reports_and_review" && reportsActiveTab === "Results")
  );
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
async function loadDetailedResultSheet(name, force = false) {
  name = String(name || "");
  if (!name) return Promise.resolve(null);
  if (detailedResultSheets[name] && !force)
    return Promise.resolve(detailedResultSheets[name]);
  if (detailedResultSheetInFlight[name] && !force)
    return detailedResultSheetInFlight[name];
  const seq = ++detailedResultSheetSeq;
  const isChartDashboardSheet = /chart/i.test(name) && /dashboard/i.test(name);
  const isAssetAllocationSheet = /asset\s+allocation/i.test(name);
  detailedResultSheetLoading = true;
  detailedResultSheetLoadingName = name;
  detailedResultSheetError = "";
  startDetailedResultsProgress("sheet");
  if (isChartDashboardSheet || isAssetAllocationSheet) {
    detailedResultsProgress = {
      active: true,
      pct: 22,
      phase: isChartDashboardSheet
        ? "Loading Chart Dashboard"
        : "Loading Asset Allocation",
      detail: isChartDashboardSheet
        ? "Building browser-friendly charts from workbook chart data. Data tables are not rendered here."
        : "Loading a UI-bounded allocation result view so the browser does not freeze on dense workbook ranges.",
      startedAt: detailedResultsProgress.startedAt,
      mode: "sheet",
    };
    renderDetailedResultsProgressTick();
  }
  detailedResultSheetInFlight[name] = (async () => {
    try {
      const out = await api(
        "/api/detailed-results?sheet=" + encodeURIComponent(name),
        {
          timeoutMs: isChartDashboardSheet
            ? 20000
            : isAssetAllocationSheet
              ? 30000
              : 60000,
        },
      );
      if (seq !== detailedResultSheetSeq) return null;
      detailedResultsProgress = {
        active: true,
        pct: 96,
        phase: isChartDashboardSheet
          ? "Rendering charts"
          : "Rendering selected result",
        detail: isChartDashboardSheet
          ? "Preparing the chart-only dashboard view."
          : "Preparing result sections for display.",
        startedAt: detailedResultsProgress.startedAt,
        mode: "sheet",
      }; // Support both the Excel-parser format {success,sheet:{...}} and the
      // semantic-model format where the page IS the response object.
      const sheetData =
        out && out.success
          ? out.sheet || (out.kind || out.sections || out.charts ? out : null)
          : null;
      if (sheetData) {
        detailedResultSheets[name] = sheetData;
        mergeDetailedSheetMeta(sheetData);
        return sheetData;
      } else {
        detailedResultSheetError =
          (out && out.error) || "Selected result page is not available.";
        return null;
      }
    } catch (e) {
      if (seq !== detailedResultSheetSeq) return null;
      const msg = e && e.message ? e.message : String(e);
      const timed =
        msg.toLowerCase().includes("timed out") || msg.includes("aborted");
      detailedResultSheetError = timed
        ? isChartDashboardSheet
          ? "Chart Dashboard loading timed out while preparing browser-native charts. Try Refresh results, rebuild reports, or choose another result page."
          : isAssetAllocationSheet
            ? "Asset Allocation loading timed out while preparing a browser-friendly view. Use Download Workbook for the full Excel sheet, or retry this page."
            : "Selected result page loading timed out. This page may be very large. Try Refresh results or choose another page."
        : msg;
      return null;
    } finally {
      delete detailedResultSheetInFlight[name];
      if (seq !== detailedResultSheetSeq) return;
      detailedResultSheetLoading = false;
      detailedResultSheetLoadingName = "";
      stopDetailedResultsProgress(detailedResultSheetError ? 0 : 100);
      if (_isViewingDetailedResults()) renderMain();
      else renderSteps();
    }
  })();
  return detailedResultSheetInFlight[name];
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
function detailColumnGroupKey(section, groupIndex) {
  return `${String(section?.title || "section")
    .replace(/[^a-z0-9]+/gi, "_")
    .slice(0, 42)}_${Number(section?.start_row || 0)}_${groupIndex}`;
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
function _updateDetailGroupStatus(el) {
  const wrap = el.closest(".detail-single-table-wrap");
  if (!wrap) return;
  const table = wrap.querySelector("table");
  const status = wrap.querySelector(".detail-col-group-status");
  if (!table || !status) return;
  const groups = Array.from(table.querySelectorAll(".detail-col-group-th"));
  const expanded = groups.filter(function (g) {
    return !g.classList.contains("collapsed");
  }).length;
  const total = groups.length;
  status.textContent =
    total +
    " group" +
    (total !== 1 ? "s" : "") +
    " · " +
    (expanded === 0 ? "all collapsed" : expanded + " expanded");
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
function renderDetailedResults() {
  return window.RetirementReportsUI.renderDetailedResults(reportsUiContext());
}
function renderBuildPreflightPanel() {
  const p = buildPreflight || {};
  const blockers = p.blockers || [],
    warnings = p.warnings || [],
    recs = p.recommendations || [];
  let cls = blockers.length
    ? "bad"
    : warnings.length
      ? "warn"
      : p.current
        ? "ok"
        : "warn";
  let title = blockers.length
    ? "Build preflight blocked"
    : warnings.length
      ? "Build preflight warnings"
      : p.current
        ? "Report package current"
        : "Build preflight ready";
  let body = "";
  if (!buildPreflight) {
    body =
      '<p class="small">Preflight checks run automatically before build. Click Refresh Preflight to check saved Plan Data, outputs, pricing diagnostics, and validation now.</p>';
  } else {
    body += `<p class="small">Readiness: <b>${esc(p.readiness || "unknown")}</b>. Saved rows checked: ${Number(p.row_count || 0)}. Required missing: ${Number(p.missing_required_count || 0)}. Schema issues: ${Number(p.schema_error_count || 0)}.</p>`;
    const items = [
      ...blockers.map((x) => ["Blocker", x]),
      ...warnings.map((x) => ["Warning", x]),
      ...recs.map((x) => ["Next", x]),
    ];
    if (items.length) {
      body +=
        "<ul>" +
        items
          .slice(0, 10)
          .map(([k, v]) => `<li><b>${esc(k)}:</b> ${esc(v)}</li>`)
          .join("") +
        "</ul>";
    } else
      body +=
        '<p class="small">No preflight warnings found for the saved local plan.</p>';
  }
  return `<div class="preflight-panel ${cls}"><div><h3>${esc(title)}</h3>${body}</div><div class="preflight-actions"><button class="btn" type="button" onclick="refreshPreflightForReview()">Refresh Preflight</button></div></div>`;
}
async function refreshPreflightForReview() {
  try {
    buildPreflight = await api("/api/build/preflight");
    updatePlanStateBanner();
    renderMain();
    showMessage("Build preflight refreshed.");
  } catch (e) {
    showMessage("Preflight failed: " + e.message, "error");
  }
}
function reportFreshnessNotice() {
  if (planStateFresh()) return "";
  let msg = "These report outputs may not match the current saved plan.";
  if (unsavedChangeCount())
    msg =
      "There are unsaved edits. Save and rebuild before using these reports as final.";
  else if (
    buildPreflight &&
    buildPreflight.warnings &&
    buildPreflight.warnings.length
  )
    msg = buildPreflight.warnings[0];
  return `<div class="section-note warning report-freshness-notice"><b>Reports may be stale.</b> ${esc(msg)} <button class="btn" type="button" onclick="goToReportsTab('Build')">Go to Build →</button></div>`;
}
function closeoutItem(cls, title, body, action) {
  return `<div class="closeout-item ${esc(cls)}"><span class="closeout-status">${esc(cls === "done" ? "Done" : cls === "warn" ? "Review" : "Next")}</span><div><b>${esc(title)}</b><p>${esc(body)}</p>${action || ""}</div></div>`;
}
function renderReviewCloseoutChecklist(stats, ready, unsaved) {
  const p = buildPreflight || {},
    pricing = p.pricing_status || p.pricing_mode || "not checked",
    artifacts = planStateArtifactsReady();
  const qc =
    (lastBuildSummary && lastBuildSummary.qc_result) ||
    (p.summary && p.summary.qc_result) ||
    "not reviewed";
  let html =
    '<section class="review-closeout"><div class="review-closeout-head"><div><span class="eyebrow">Review-and-Build closeout</span><h3>Final report sequence</h3><p class="small">Use this order for a low-risk final package: validate inputs, save, confirm pricing, run preflight, build, inspect QC, review Plan Data Summary, then download.</p></div><button class="btn primary" type="button" data-requires-app="1" onclick="runBuild(false)">Build Reports</button></div><div class="closeout-list">';
  html += closeoutItem(
    ready ? "done" : "warn",
    "Validate required inputs",
    ready
      ? "Required fields and holdings are ready."
      : "Complete required fields and add at least one valid holding before final reports.",
    `<button class="btn tiny" type="button" data-step-id="review">Review missing inputs</button>`,
  );
  html += closeoutItem(
    unsaved ? "warn" : "done",
    "Save working copy",
    unsaved
      ? `${unsaved} pending change${unsaved === 1 ? "" : "s"} need to be saved or will be saved by the build.`
      : "No unsaved edits are currently staged.",
    `<button class="btn tiny" type="button" data-requires-app="1" onclick="saveAll(true)">Save Changes</button>`,
  );
  html += closeoutItem(
    p.pricing_status || p.pricing_mode ? "done" : "warn",
    "Refresh or freeze pricing",
    `Pricing mode/status: ${pricing}. Freeze prices when reports need reproducible advisor values.`,
    `<button class="btn tiny" type="button" onclick="freezePricingSnapshot()">Freeze latest prices</button> <button class="btn tiny" type="button" onclick="unfreezePricingSnapshot()">Unfreeze</button>`,
  );
  html += closeoutItem(
    buildPreflight
      ? p.blockers && p.blockers.length
        ? "warn"
        : "done"
      : "todo",
    "Run preflight",
    buildPreflight
      ? `Readiness: ${p.readiness || "checked"}. Warnings: ${(p.warnings || []).length}. Blockers: ${(p.blockers || []).length}.`
      : "Refresh preflight before starting a long build.",
    `<button class="btn tiny" type="button" onclick="refreshPreflightForReview()">Refresh Preflight</button>`,
  );
  html += closeoutItem(
    artifacts ? "done" : "todo",
    "Build report package",
    artifacts
      ? "Workbook, summary, and results model artifacts are present."
      : "Build reports to create the workbook, PDF, dashboard, and Results Explorer model.",
    `<button class="btn tiny primary" type="button" data-requires-app="1" onclick="runBuild(false)">Build Reports</button>`,
  );
  html += closeoutItem(
    planStateFresh() ? "done" : "warn",
    "Inspect QC and Build History",
    planStateFresh()
      ? `Reports are current. QC: ${qc}.`
      : "Open Build History after a successful current build and check QC/fingerprints.",
    `<button class="btn tiny" type="button" data-step-id="build_impact">Open Build History</button>`,
  );
  html += closeoutItem(
    "todo",
    "Inspect Plan Data Summary",
    "Print or save the read-only input packet before sharing final reports.",
    `<button class="btn tiny" type="button" data-step-id="plan_data_report">Open Plan Data Summary</button>`,
  );
  html += closeoutItem(
    artifacts ? "done" : "todo",
    "Download final outputs",
    artifacts
      ? "Outputs can be downloaded; downloads rebuild first if needed."
      : "Download after build, or use Download Workbook/PDF to save, build, and deliver in one action.",
    `<button class="btn tiny good" type="button" data-requires-app="1" onclick="downloadWithBuild('/api/xlsx','Workbook')">Workbook</button> <button class="btn tiny good" type="button" data-requires-app="1" onclick="downloadWithBuild('/api/pdf','PDF')">PDF</button>`,
  );
  html += "</div></section>";
  return html;
}
function renderReview() {
  const fresh = planStateFresh();
  const arts = planStateArtifactsReady();
  const unsaved = unsavedChangeCount();
  let statusHtml = "";
  if (unsaved)
    statusHtml = `<div class="section-note warning"><b>${unsaved} unsaved change${unsaved === 1 ? "" : "s"}.</b> Changes are saved automatically before download. <button class="btn tiny" type="button" data-requires-app="1" onclick="saveAll(true)">Save Now</button></div>`;
  else if (!fresh)
    statusHtml = `<div class="section-note warning"><b>Outputs may be stale.</b> Inputs changed since last build. <button class="btn tiny" type="button" onclick="goToReportsTab('Build')">Go to Build →</button></div>`;
  else if (arts)
    statusHtml =
      '<div class="section-note ok">Report outputs are current.</div>';
  else
    statusHtml =
      '<div class="section-note">No report outputs yet — build first, then download.</div>';
  return `<div class="reports-panel"><h3>Downloads</h3><p class="small">Download the workbook or PDF. Downloads save and rebuild automatically if outputs are not current.</p>${statusHtml}<div class="pane-actions"><button class="btn good" data-requires-app="1" onclick="downloadWithBuild('/api/xlsx','Workbook')">Download Workbook</button><button class="btn good" data-requires-app="1" onclick="downloadWithBuild('/api/pdf','PDF')">Download PDF</button></div></div>`;
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

function renderTaxonomyManager() {
  if (!taxonomyData && !taxonomyLoading && !taxonomyError) {
    setTimeout(() => loadTaxonomy(false), 0);
  }
  let html =
    '<div class="holdings taxonomy-manager"><h3 class="group-title">Category Manager</h3>';
  html +=
    '<div class="section-note">Manage the canonical <b>Tracking Type → Group → Category</b> tree. Transaction assignment uses these canonical categories, so there is no separate group-mapping table to maintain.</div>';
  if (taxonomyLoading) {
    html += '<div class="question"><b>Loading taxonomy…</b></div>';
  } else if (taxonomyError && !taxonomyData) {
    html += `<div class="missing-list"><p>${esc(taxonomyError)}</p></div><button class="btn" onclick="loadTaxonomy(true)">Retry</button>`;
  } else if (taxonomyData) {
    html +=
      '<div class="table-actions"><button class="btn" onclick="showTaxonomyAddForm()">+ Add Category</button><button class="btn" onclick="loadTaxonomy(true)">Reload</button></div>';
    html += '<div id="taxonomyAddForm" style="display:none"></div>';
    html += '<div class="taxonomy-tree">';
    (taxonomyData || []).forEach(function (typeData) {
      const totalCats = (typeData.groups || []).reduce(
        (s, g) => s + (g.categories || []).length,
        0,
      );
      html += `<details class="taxonomy-type-section"><summary><b>${esc(typeData.tracking_type)}</b> <span class="small">(${totalCats} categories)</span></summary>`;
      (typeData.groups || []).forEach(function (grp) {
        html += `<div class="taxonomy-group"><h4 class="taxonomy-group-title">${esc(grp.group)} <span class="small">(${(grp.categories || []).length})</span></h4>`;
        html +=
          '<table class="lot-table taxonomy-cat-table"><thead><tr><th>ID</th><th>Label</th><th>Notes</th><th></th></tr></thead><tbody>';
        (grp.categories || []).forEach(function (cat) {
          html += `<tr><td><code class="small">${esc(cat.id)}</code></td><td>${esc(cat.label)}</td><td class="small">${esc(cat.notes || "")}</td><td><button class="danger-link" onclick="deleteTaxonomyCat('${esc(cat.id)}','${esc(cat.label)}')">Delete</button></td></tr>`;
        });
        html += "</tbody></table></div>";
      });
      html += "</details>";
    });
    html += "</div>";
  } else {
    html +=
      '<div class="question"><b>No taxonomy loaded.</b> <button class="btn" onclick="loadTaxonomy(true)">Load Taxonomy</button></div>';
  }
  html +=
    '<details class="advanced-mapping-rules" style="margin-top:32px"><summary><b>Advanced Auto-Mapping Rules</b><span class="small" style="margin-left:8px;font-weight:400;color:var(--muted)">merchant/category text rules</span></summary>' +
    renderCategoryMappingRules() +
    "</details>";
  html += "</div>";
  return html;
}

function showTaxonomyAddForm() {
  const form = document.getElementById("taxonomyAddForm");
  if (!form) return;
  const types = taxonomyData || [];
  let typeOpts = types
    .map(
      (t) =>
        `<option value="${esc(t.tracking_type)}">${esc(t.tracking_type)}</option>`,
    )
    .join("");
  form.style.display = "block";
  form.innerHTML = `<div class="taxonomy-add-inner" style="padding:12px;border:1px solid var(--line);border-radius:6px;margin:12px 0"><h4>Add Custom Category</h4><div class="field-row" style="display:flex;gap:12px;align-items:center;margin:6px 0"><label style="width:120px">Tracking Type</label><select id="taxAddType" onchange="updateTaxAddGroups()">${typeOpts}</select></div><div class="field-row" style="display:flex;gap:12px;align-items:center;margin:6px 0"><label style="width:120px">Group</label><select id="taxAddGroup"></select><span class="small" style="margin-left:8px">or new: <input id="taxAddNewGroup" placeholder="New group name" style="width:160px"></span></div><div class="field-row" style="display:flex;gap:12px;align-items:center;margin:6px 0"><label style="width:120px">Category key</label><input id="taxAddId" placeholder="e.g. my_category (lowercase_underscores)" style="width:220px" oninput="this.value=this.value.replace(/[^a-z0-9_]/g,'')"></div><div class="field-row" style="display:flex;gap:12px;align-items:center;margin:6px 0"><label style="width:120px">Label</label><input id="taxAddLabel" placeholder="Display name" style="width:220px"></div><div class="field-row" style="display:flex;gap:12px;align-items:center;margin:6px 0"><label style="width:120px">Notes</label><input id="taxAddNotes" placeholder="Optional description" style="width:220px"></div><div class="table-actions"><button class="btn primary" onclick="submitAddTaxonomy()">Add Category</button><button class="btn" onclick="document.getElementById('taxonomyAddForm').style.display='none'">Cancel</button></div></div>`;
  updateTaxAddGroups();
}

function updateTaxAddGroups() {
  const typeEl = document.getElementById("taxAddType");
  const groupEl = document.getElementById("taxAddGroup");
  if (!typeEl || !groupEl) return;
  const sel = typeEl.value;
  const typeData = (taxonomyData || []).find((t) => t.tracking_type === sel);
  const groups = typeData ? (typeData.groups || []).map((g) => g.group) : [];
  groupEl.innerHTML = groups
    .map((g) => `<option value="${esc(g)}">${esc(g)}</option>`)
    .join("");
}

async function loadTaxonomy(force) {
  if (taxonomyData && !force) return;
  taxonomyLoading = true;
  renderMain();
  try {
    const out = await api("/api/spending/taxonomy");
    if (out && out.success) {
      taxonomyData = out.taxonomy || [];
      taxonomyFlat = out.flat || {};
      taxonomyError = "";
    } else {
      taxonomyError = (out && out.error) || "Failed to load taxonomy.";
    }
  } catch (e) {
    taxonomyError = e.message || "Error loading taxonomy.";
  }
  taxonomyLoading = false;
  renderMain();
}
function showSpendingModelLoadOverlay() {
  setBuildOverlay(
    true,
    "Loading Spending Model",
    "Reading transaction history and computing category rollups. This can take a few seconds on large transaction histories.",
    "waiting",
    "",
  );
  const overlay = document.getElementById("buildOverlay");
  if (overlay) overlay.classList.add("no-cancel");
}
function hideSpendingModelLoadOverlay() {
  const overlay = document.getElementById("buildOverlay");
  if (overlay) overlay.classList.remove("no-cancel");
  hideBuildOverlay();
}
async function loadSpendingModel(force) {
  if (spendingModelData && !force) return;
  const cold = !spendingModelData;
  spendingModelLoading = true;
  if (cold) showSpendingModelLoadOverlay();
  try {
    const out = await api("/api/spending/model");
    if (out && out.success) {
      spendingModelData = out;
      spendingModelError = "";
    } else {
      spendingModelData = null;
      spendingModelError =
        (out && out.error) || "Failed to load spending model.";
      if (force) showMessage(spendingModelError, "error");
    }
  } catch (e) {
    spendingModelData = null;
    spendingModelError = e.message || "Error loading spending model.";
    if (force) showMessage(spendingModelError, "error");
  }
  spendingModelLoading = false;
  if (cold) hideSpendingModelLoadOverlay();
  renderMain();
}
function clearSpendingCaches() {
  spendingModelData = null;
  spendingModelError = "";
  taxonomyData = null;
  taxonomyFlat = {};
  taxonomyError = "";
  taxBudgetLoaded = false;
  budgetLinesLoaded = false;
}
async function reloadDomainBudget(domain) {
  clearSpendingCaches();
  await Promise.all([
    loadTaxonomy(true),
    loadSpendingModel(true),
    loadBudgetLines(true),
    loadTaxonomyBudget(true),
  ]);
  renderMain();
}
function currentSpendingTreeForDomain(domain) {
  const wanted = new Set(trackingBudgetTypesForDomain(domain));
  const modelTypes =
    spendingModelData && Array.isArray(spendingModelData.tracking_types)
      ? spendingModelData.tracking_types
      : [];
  if (modelTypes.length) {
    return modelTypes.filter((t) => wanted.has(t.tracking_type));
  }
  return (taxonomyData || []).filter((t) => wanted.has(t.tracking_type));
}
function dollars0(v) {
  return "$" + Math.round(budgetMoneyNumber(v) || 0).toLocaleString();
}

async function submitAddTaxonomy() {
  const tt = ((document.getElementById("taxAddType") || {}).value || "").trim();
  const newGrp = (
    (document.getElementById("taxAddNewGroup") || {}).value || ""
  ).trim();
  const grp =
    newGrp ||
    ((document.getElementById("taxAddGroup") || {}).value || "").trim();
  const catId = (
    (document.getElementById("taxAddId") || {}).value || ""
  ).trim();
  const label = (
    (document.getElementById("taxAddLabel") || {}).value || ""
  ).trim();
  const notes = (
    (document.getElementById("taxAddNotes") || {}).value || ""
  ).trim();
  if (!tt || !grp || !catId || !label) {
    showMessage(
      "Tracking Type, Group, Category key, and Label are all required.",
      "error",
    );
    return;
  }
  try {
    const out = await api("/api/spending/taxonomy/category", {
      method: "POST",
      body: JSON.stringify({
        tracking_type: tt,
        group: grp,
        id: catId,
        label: label,
        notes: notes,
      }),
    });
    if (out && out.success) {
      showMessage('Category "' + label + '" added.');
      await Promise.all([loadTaxonomy(true), loadSpendingModel(true)]);
    } else
      showMessage((out && out.error) || "Failed to add category.", "error");
  } catch (e) {
    showMessage("Error: " + e.message, "error");
  }
}

async function deleteTaxonomyCat(catId, label) {
  if (
    !(await showInAppConfirm(
      '"' + label + '" (' + catId + ") will be permanently deleted.",
      { title: "Delete Category", confirmLabel: "Delete", variant: "danger" },
    ))
  )
    return;
  try {
    const out = await api(
      "/api/spending/taxonomy/category/" + encodeURIComponent(catId),
      { method: "DELETE" },
    );
    if (out && out.success) {
      showMessage("Category deleted.");
      await Promise.all([loadTaxonomy(true), loadSpendingModel(true)]);
    } else showMessage((out && out.error) || "Failed to delete.", "error");
  } catch (e) {
    showMessage("Error: " + e.message, "error");
  }
}

async function deleteTaxonomyGroup(tt, grp) {
  if (
    !(await showInAppConfirm('"' + grp + '" will be removed from ' + tt + ".", {
      title: "Delete Group",
      confirmLabel: "Delete",
      variant: "danger",
    }))
  )
    return;
  try {
    const out = await api("/api/spending/taxonomy/group", {
      method: "DELETE",
      body: JSON.stringify({ tracking_type: tt, group: grp }),
    });
    if (out && out.success) {
      showMessage("Group deleted.");
      await Promise.all([loadTaxonomy(true), loadSpendingModel(true)]);
    } else
      showMessage((out && out.error) || "Failed to delete group.", "error");
  } catch (e) {
    showMessage("Error: " + e.message, "error");
  }
}

async function loadMappingRules(force) {
  if (mappingRules && !force) return;
  try {
    const out = await api("/api/spending/rules");
    mappingRules = out && out.success ? out.rules || [] : [];
    if (!taxonomyFlat || !Object.keys(taxonomyFlat).length)
      await loadTaxonomy(false);
  } catch (e) {
    mappingRules = [];
  }
  renderMain();
}

async function saveMappingRulesData() {
  try {
    await api("/api/spending/rules/save", {
      method: "POST",
      body: JSON.stringify({ rules: mappingRules || [] }),
    });
    rulesChanged = false;
    renderMain();
    showMessage("Advanced auto-mapping rules saved.");
  } catch (e) {
    showMessage("Error saving rules: " + e.message, "error");
  }
}

function addMappingRule() {
  if (!mappingRules) mappingRules = [];
  mappingRules.unshift({
    keyword: "",
    category_id: "",
    match_field: "category",
    exact: false,
    priority: 50,
  });
  rulesChanged = true;
  renderMain();
}

function updateMappingRule(i, field, val) {
  if (!mappingRules || !mappingRules[i]) return;
  mappingRules[i][field] = val;
  rulesChanged = true;
}

function deleteMappingRule(i) {
  if (!mappingRules) return;
  mappingRules.splice(i, 1);
  rulesChanged = true;
  renderMain();
}

function renderCategoryMappingRules() {
  if (!mappingRules && !rulesChanged) {
    setTimeout(() => loadMappingRules(false), 0);
  }
  let html =
    '<div class="holdings"><h3 class="group-title">Advanced Auto-Mapping Rules</h3>';
  html +=
    '<div class="section-note">Optional rules auto-assign imported merchant or category text to a canonical Spending Category. Most users should use the category picker in Spending Categories; use these rules only when the same text should be classified automatically every time.</div>';
  const rules = mappingRules || [];
  html +=
    '<div class="table-actions"><button class="btn" onclick="addMappingRule()">+ Add rule</button>';
  html += `<button class="btn primary" ${rulesChanged ? "" : "disabled"} onclick="saveMappingRulesData()">Save Changes</button>`;
  html +=
    '<button class="btn" onclick="loadMappingRules(true)">Reload</button></div>';
  html +=
    '<div class="lot-table-wrap"><table class="lot-table"><thead><tr><th>Match text</th><th>Match source</th><th>Exact?</th><th>Target category</th><th>Priority</th><th></th></tr></thead><tbody>';
  if (!rules.length) {
    html +=
      '<tr><td colspan="6" class="small" style="padding:12px">No auto-mapping rules defined. Add a rule only for merchant/category text that should be classified the same way every time.</td></tr>';
  } else {
    const catIds = Object.keys(taxonomyFlat || {}).sort((a, b) =>
      a.localeCompare(b),
    );
    rules.forEach(function (rule, i) {
      const current = String(rule.category_id || "");
      let opts = catIds
        .map(
          (id) =>
            `<option value="${esc(id)}" ${id === current ? "selected" : ""}>${esc(id)}${taxonomyFlat[id] && taxonomyFlat[id].label ? " — " + esc(taxonomyFlat[id].label) : ""}</option>`,
        )
        .join("");
      if (current && !catIds.includes(current))
        opts =
          `<option value="${esc(current)}" selected>${esc(current)}</option>` +
          opts;
      html += `<tr><td><input value="${esc(rule.keyword)}" oninput="updateMappingRule(${i},'keyword',this.value)" style="width:160px"></td><td><select onchange="updateMappingRule(${i},'match_field',this.value)"><option value="category"${rule.match_field === "category" ? " selected" : ""}>Category text</option><option value="merchant"${rule.match_field === "merchant" ? " selected" : ""}>Merchant text</option></select></td><td style="text-align:center"><input type="checkbox" ${rule.exact ? "checked" : ""} onchange="updateMappingRule(${i},'exact',this.checked)"></td><td><select onchange="updateMappingRule(${i},'category_id',this.value)" style="min-width:260px"><option value="" ${current ? "" : "selected"}>Select category…</option>${opts}</select></td><td><input type="number" value="${rule.priority || 50}" oninput="updateMappingRule(${i},'priority',parseInt(this.value)||50)" style="width:70px"></td><td><button class="danger-link" onclick="deleteMappingRule(${i})">Delete</button></td></tr>`;
    });
  }
  html += "</tbody></table></div></div>";
  return html;
}

const BUDGET_SECTION_DEFS = [
  [
    "large_discretionary",
    "Large Discretionary",
    "Wedding, Large Gifts, and Other projection rows.",
  ],
  [
    "home_improvement",
    "Home Improvements",
    "Remodels and home projects. These flow into housing costs in the projection.",
  ],
  ["travel", "Travel", "Vacations and trips."],
  [
    "gifts_charity",
    "Gifts / Charity",
    "Gifts given and charitable donations (budget tracking target).",
  ],
];
async function loadBudgetLines(force) {
  if (budgetLinesLoaded && !force) return;
  try {
    const out = await api("/api/spending/budget-lines");
    budgetLines = out && out.success ? out.lines || [] : [];
    if (!taxonomyData) await loadTaxonomy(false);
  } catch (e) {
    budgetLines = [];
  }
  budgetLines.forEach((l) => {
    if (l.mode === "summary") budgetSectionMode[l.section] = "summary";
    if (l.section === "category_budget" && l.category_id)
      categoryBudgetMode[l.category_id] = "detail";
  });
  budgetLinesLoaded = true;
  budgetLinesChanged = false;
  renderMain();
}
async function loadTaxonomyBudget(force) {
  if (taxBudgetLoaded && !force) return;
  try {
    const out = await api("/api/spending/budget/taxonomy");
    if (out && out.success) {
      taxBudget = out.budget || {};
    } else {
      taxBudget = {};
      if (force)
        showMessage(
          (out && out.error) || "Unable to load category budgets.",
          "error",
        );
    }
  } catch (e) {
    taxBudget = {};
    if (force)
      showMessage("Error loading category budgets: " + e.message, "error");
  }
  taxBudgetLoaded = true;
  taxBudgetChanged = false;
  restoreGroupBudgetModes();
  renderMain();
}
async function saveBudgetLines() {
  try {
    await api("/api/spending/budget-lines", {
      method: "POST",
      body: JSON.stringify({ lines: budgetLines }),
    });
    budgetLinesChanged = false;
    renderMain();
    showMessage("Spending category changes saved.");
  } catch (e) {
    showMessage("Error saving spending budget: " + e.message, "error");
  }
}
async function reloadBudgetLineDefaults() {
  if (
    !(await showInAppConfirm(
      "All spending budget rows will be replaced with defaults. Unsaved edits will be lost.",
      {
        title: "Reload Defaults",
        confirmLabel: "Replace with Defaults",
        variant: "warn",
      },
    ))
  )
    return;
  try {
    const out = await api("/api/spending/budget-lines/defaults");
    budgetLines = out && out.success ? out.lines || [] : [];
    budgetSectionMode = {};
    budgetLines.forEach((l) => {
      if (l.mode === "summary") budgetSectionMode[l.section] = "summary";
    });
    budgetLinesChanged = true;
    markBudgetLinesDirty();
    renderMain();
  } catch (e) {
    showMessage("Error loading defaults: " + e.message, "error");
  }
}
function markBudgetLinesDirty() {
  budgetLinesChanged = true;
  taxBudgetChanged = true;
  lastBuildOk = false;
  updateUnsaved();
  setAppControls(appReady);
  scheduleStatusUpdate();
}
function budgetSectionLines(section) {
  return budgetLines.filter((l) => l.section === section);
}
function budgetSectionIsSummary(section) {
  return budgetSectionMode[section] === "summary";
}
function setBudgetSectionMode(section, mode) {
  budgetSectionMode[section] = mode;
  budgetLines.forEach((l) => {
    if (l.section === section) l.mode = mode;
  });
  markBudgetLinesDirty();
  renderMain();
}
function addBudgetLine(section) {
  const prefix =
    {
      large_discretionary: "ld",
      home_improvement: "hi",
      travel: "tr",
      gifts_charity: "gc",
    }[section] || "bl";
  budgetLines.push({
    section,
    line_id: prefix + "_" + (Date.now() % 100000),
    label: "",
    category_id: "",
    start_year: "",
    end_year: "",
    one_time_year: "",
    amount_per_year: "",
    mode: budgetSectionIsSummary(section) ? "summary" : "detail",
    notes: "",
  });
  markBudgetLinesDirty();
  renderMain();
}
async function deleteBudgetLine(lineId) {
  if (
    !(await showInAppConfirm("This cannot be undone.", {
      title: "Delete Budget Row",
      confirmLabel: "Delete",
      variant: "danger",
    }))
  )
    return;
  budgetLines = budgetLines.filter((l) => l.line_id !== lineId);
  markBudgetLinesDirty();
  renderMain();
}
function updateBudgetLine(lineId, field, val) {
  const l = budgetLines.find((x) => x.line_id === lineId);
  if (!l) return;
  l[field] = val;
  markBudgetLinesDirty();
}
function taxonomyCategoryOptionsHtml(selected) {
  let html = '<option value="">— map to category —</option>';
  (taxonomyData || [])
    .filter((t) => t.tracking_type !== "Income")
    .forEach((t) => {
      (t.groups || []).forEach((g) => {
        (g.categories || []).forEach((c) => {
          html += `<option value="${esc(c.id)}"${c.id === selected ? " selected" : ""}>${esc(t.tracking_type)} › ${esc(g.group)} › ${esc(c.label)}</option>`;
        });
      });
    });
  return html;
}
function catDetailLines(catId) {
  return (budgetLines || []).filter((l) => l.category_id === catId);
}
function budgetAmount(value) {
  return budgetMoneyNumber(value);
}
function catDetailSum(catId) {
  let s = 0;
  catDetailLines(catId).forEach((l) => {
    s += budgetAmount(l.amount_per_year) || 0;
  });
  return s;
}
function hasExplicitBudget(key) {
  const b = taxBudget[key];
  return !!(
    b &&
    b.annual_budget !== undefined &&
    b.annual_budget !== null &&
    b.annual_budget !== ""
  );
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
function groupCatIds(tt, grp) {
  const ids = [];
  (taxonomyData || []).forEach((t) => {
    if (t.tracking_type === tt)
      (t.groups || []).forEach((g) => {
        if (g.group === grp)
          (g.categories || []).forEach((c) => ids.push(c.id));
      });
  });
  return ids;
}
function groupCatSum(tt, grp) {
  const ids = groupCatIds(tt, grp);
  if (!ids.length) {
    const mg = groupModelData(tt, grp);
    return budgetAmount(mg && mg.budget);
  }
  return ids.reduce((s, id) => s + (catEffectiveBudget(id) || 0), 0);
}
function groupKeyFor(tt, grp) {
  return "grp::" + tt + "::" + grp;
}
function groupIsSummary(tt, grp) {
  return groupBudgetMode[tt + "::" + grp] === "summary";
}
function groupEffectiveBudget(tt, grp) {
  if (groupIsSummary(tt, grp)) {
    const gk = groupKeyFor(tt, grp);
    if (hasExplicitBudget(gk)) return budgetAmount(taxBudget[gk].annual_budget);
    return groupCatSum(tt, grp);
  }
  return groupCatSum(tt, grp);
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
function spendingRowYtd(row) {
  return budgetAmount(
    row && (row.ytd_actual !== undefined ? row.ytd_actual : row.actual),
  );
}
function spendingRowAnnualized(row) {
  return budgetAmount(
    row &&
      (row.annualized_actual !== undefined
        ? row.annualized_actual
        : row.annualized),
  );
}
function spendingRowBudget(row) {
  return budgetAmount(
    row && (row.annual_budget !== undefined ? row.annual_budget : row.budget),
  );
}
function spendingRowProjectionSeed(row) {
  return budgetAmount(
    row &&
      (row.projection_seed !== undefined
        ? row.projection_seed
        : row.annual_budget !== undefined
          ? row.annual_budget
          : row.budget),
  );
}
function spendingRowHasValue(row) {
  return !!(
    spendingRowYtd(row) ||
    spendingRowAnnualized(row) ||
    spendingRowBudget(row) ||
    spendingRowProjectionSeed(row)
  );
}
function setGroupBudgetMode(tt, grp, mode) {
  groupBudgetMode[tt + "::" + grp] = mode;
  const gk = groupKeyFor(tt, grp);
  if (mode === "summary") {
    const sum = groupCatSum(tt, grp);
    if (!taxBudget[gk]) taxBudget[gk] = { annual_budget: 0, notes: "" };
    if (!(Number(taxBudget[gk].annual_budget) > 0))
      taxBudget[gk].annual_budget = Math.round(sum);
    taxBudget[gk]._mode = "summary";
  } else {
    if (taxBudget[gk]) taxBudget[gk]._mode = "detail";
  }
  taxBudgetChanged = true;
  syncTaxonomyBudgetToBudgetLines();
  markBudgetLinesDirty();
  renderMain();
}
function syncCategoryTotal(catId) {
  if (!taxBudget[catId]) taxBudget[catId] = { annual_budget: 0, notes: "" };
  taxBudget[catId].annual_budget = Math.round(catDetailSum(catId));
  taxBudgetChanged = true;
  syncTaxonomyBudgetToBudgetLines();
}
function setCategoryBudgetMode(catId, mode) {
  categoryBudgetMode[catId] = mode;
  if (mode === "detail") syncCategoryTotal(catId);
  markBudgetLinesDirty();
  renderMain();
}
function addCategoryDetailRow(catId) {
  budgetLines.push({
    section: "category_budget",
    line_id: "cb_" + (Date.now() % 1000000),
    label: "",
    category_id: catId,
    start_year: "",
    end_year: "",
    one_time_year: "",
    amount_per_year: "",
    mode: "detail",
    notes: "",
  });
  categoryBudgetMode[catId] = "detail";
  syncCategoryTotal(catId);
  markBudgetLinesDirty();
  renderMain();
}
function addGroupDetailRow(tt, grp) {
  const cats = groupCatIds(tt, grp);
  const catId = cats[0] || "";
  budgetLines.push({
    section: "category_budget",
    line_id: "cb_" + (Date.now() % 1000000),
    label: "",
    category_id: catId,
    start_year: "",
    end_year: "",
    one_time_year: "",
    amount_per_year: "",
    mode: "detail",
    notes: "",
  });
  if (catId) {
    categoryBudgetMode[catId] = "detail";
    syncCategoryTotal(catId);
  }
  markBudgetLinesDirty();
  renderMain();
}
function updateGroupDetailCategory(lineId, newCatId, oldCatId) {
  const l = budgetLines.find((x) => x.line_id === lineId);
  if (!l) return;
  l.category_id = newCatId;
  if (newCatId) {
    categoryBudgetMode[newCatId] = "detail";
    syncCategoryTotal(newCatId);
  }
  if (oldCatId && oldCatId !== newCatId) syncCategoryTotal(oldCatId);
  markBudgetLinesDirty();
  renderMain();
}
function deleteCategoryDetailRow(lineId, catId) {
  budgetLines = budgetLines.filter((l) => l.line_id !== lineId);
  syncCategoryTotal(catId);
  markBudgetLinesDirty();
  renderMain();
}
async function deleteCategoryBudget(catId, label) {
  if (
    !(await showInAppConfirm(
      'All budget entries for "' + label + '" will be cleared.',
      {
        title: "Remove Budget Entries",
        confirmLabel: "Remove",
        variant: "warn",
      },
    ))
  )
    return;
  budgetLines = (budgetLines || []).filter((l) => l.category_id !== catId);
  taxBudget[catId] = { annual_budget: 0, notes: "", _delete: true };
  delete categoryBudgetMode[catId];
  taxBudgetChanged = true;
  syncTaxonomyBudgetToBudgetLines();
  markBudgetLinesDirty();
  renderMain();
}
function updateCategoryDetail(lineId, field, val, catId) {
  const l = budgetLines.find((x) => x.line_id === lineId);
  if (l) l[field] = val;
  syncCategoryTotal(catId);
  markBudgetLinesDirty();
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

async function loadAnnualizedActuals() {
  if (
    !(await showInAppConfirm(
      "Load annualized current spend into EVERY category budget? This overwrites all category totals and adds any new transaction categories to the taxonomy.",
      {
        title: "Load Annualized Actuals",
        confirmLabel: "Load",
        variant: "warn",
      },
    ))
  )
    return;
  try {
    const out = await api("/api/spending/budget/load-actuals", {
      method: "POST",
      body: JSON.stringify({}),
    });
    if (!out || out.success === false)
      throw new Error((out && out.error) || "Failed to load actuals.");
    const a = out.actuals || {};
    Object.keys(a).forEach((id) => {
      const v = Math.round(Number(a[id]) || 0);
      if (!taxBudget[id]) taxBudget[id] = { annual_budget: 0, notes: "" };
      taxBudget[id].annual_budget = v;
      if (!taxBudget[id].notes) taxBudget[id].notes = "Annualized actual";
    });
    taxBudgetChanged = true;
    await loadTaxonomy(true);
    await saveTaxonomyBudgetData();
    showMessage(
      (out.merged_count
        ? out.merged_count +
          " new transaction categor" +
          (out.merged_count > 1 ? "ies" : "y") +
          " merged. "
        : "") + "Annualized actuals loaded into category budgets.",
    );
    renderMain();
  } catch (e) {
    showMessage("Error loading actuals: " + e.message, "error");
  }
}
async function saveSpendingBudgetAll() {
  try {
    if (budgetLinesChanged)
      await api("/api/spending/budget-lines", {
        method: "POST",
        body: JSON.stringify({ lines: budgetLines }),
      });
    if (taxBudgetChanged) {
      await api("/api/spending/budget/taxonomy/save", {
        method: "POST",
        body: JSON.stringify({ budget: taxBudget }),
      });
      syncTaxonomyBudgetToBudgetLines();
    }
    budgetLinesChanged = false;
    taxBudgetChanged = false;
    renderMain();
    showMessage("Spending category changes saved.");
  } catch (e) {
    showMessage("Error saving spending budget: " + e.message, "error");
  }
}

function renderTaxonomyBudgetTable() {
  if (!taxBudgetLoaded) {
    setTimeout(() => loadTaxonomyBudget(false), 0);
  }
  const data = taxonomyData || [];
  const expenseTypes = data.filter((t) => t.tracking_type !== "Income");
  if (!expenseTypes.length)
    return '<div class="question"><b>Loading…</b></div>';
  let html = "";
  html +=
    '<div class="table-actions"><button class="btn" onclick="loadAnnualizedActuals()" title="Overwrite every category budget with its annualized current-year spend; new transaction categories are merged into the taxonomy">Load annualized current spend</button></div>';
  html +=
    '<div class="section-note small">Each <b>group</b> can be set as a single <b>Summary</b> total or expanded to <b>Detail</b> per category. In Detail mode each category supports multiple rows with optional start / end years — useful for time-bounded spending like travel or large events.</div>';
  let grandTotal = 0;
  expenseTypes.forEach(function (t) {
    (t.groups || []).forEach(function (g) {
      grandTotal += groupEffectiveBudget(t.tracking_type, g.group);
    });
  });
  html += '<div class="taxonomy-tree">';
  expenseTypes.forEach(function (typeData) {
    const tt = typeData.tracking_type;
    if (tt === "Housing") {
      html += `<details class="taxonomy-type-section" data-dkey="budgtt:Housing"><summary><b>Housing</b> <span class="small" style="font-weight:400;color:var(--muted)">managed on Housing page</span></summary><div class="taxonomy-group"><div class="section-note">Mortgage, insurance, utilities, maintenance, and home improvements are entered on the Housing page and flow into the projection automatically. <button class="btn" style="padding:2px 10px;font-size:12px" data-step-id="spending_mortgage_events">Go to Housing page →</button></div></div></details>`;
      return;
    }
    if (tt === "Wellness") {
      html += `<details class="taxonomy-type-section" data-dkey="budgtt:Wellness"><summary><b>Wellness</b> <span class="small" style="font-weight:400;color:var(--muted)">managed on Wellness page</span></summary><div class="taxonomy-group"><div class="section-note">Bridge premiums, Medicare costs, and out-of-pocket estimates are entered on the Wellness page and flow into the projection directly. <button class="btn" style="padding:2px 10px;font-size:12px" data-step-id="retirement_wellness">Go to Wellness page →</button></div></div></details>`;
      return;
    }
    let ttTotal = 0;
    (typeData.groups || []).forEach((g) => {
      ttTotal += groupEffectiveBudget(tt, g.group);
    });
    html += `<details class="taxonomy-type-section" data-dkey="budgtt:${esc(tt)}"${ttTotal > 0 ? " open" : ""}><summary><b>${esc(tt)}</b>${ttActual || ttAnnualized || ttTotal ? ` <span class="small">Actual ${dollars0(ttActual)} · Annualized ${dollars0(ttAnnualized)} · Budget ${dollars0(ttTotal)}/yr</span>` : ""}</summary>`;
    (typeData.groups || []).forEach(function (grp) {
      const gname = grp.group;
      const gj = esc(gname).replace(/'/g, "\\'");
      const gmode = groupIsSummary(tt, gname) ? "summary" : "detail";
      const gk = groupKeyFor(tt, gname);
      const catSum = groupCatSum(tt, gname);
      const eff = groupEffectiveBudget(tt, gname);
      const catCount = (grp.categories || []).length;
      html += `<div class="taxonomy-group"><h4 class="taxonomy-group-title" style="display:flex;align-items:center;gap:8px;flex-wrap:wrap"><span>${esc(gname)}</span><span class="small" style="font-weight:400">Actual ${dollars0(grp.actual)} · Annualized ${dollars0(grp.annualized)} · Budget ${dollars0(eff)}/yr</span><span style="margin-left:auto"><button class="btn ${gmode === "summary" ? "primary" : ""}" style="padding:0 8px" ${readOnlyRef ? "disabled " : ""}onclick="setGroupBudgetMode('${esc(tt)}','${gj}','summary')">Summary</button> <button class="btn ${gmode === "detail" ? "primary" : ""}" style="padding:0 8px" ${readOnlyRef ? "disabled " : ""}onclick="setGroupBudgetMode('${esc(tt)}','${gj}','detail')">Detail</button></span></h4>`;
      if (gmode === "summary") {
        html += `<div class="table-actions"><label class="small">Group budget / yr&nbsp;</label><input ${readOnlyRef ? "disabled " : ""}type="text" class="budget-money-input" value="${esc(budgetMoneyInputValue((taxBudget[gk] || {}).annual_budget))}" placeholder="${catSum > 0 ? dollars0(catSum) : "$0"}" onfocus="focusBudgetMoney(this)" oninput="updateTaxBudgetMoney('${esc(gk)}','annual_budget',this)" onblur="blurBudgetMoney(this)" style="width:140px"> <span class="small">categories hidden</span></div>`;
      } else {
        html += '<div class="budget-cat-detail-list">';
        (grp.categories || []).forEach(function (cat) {
          const catId = cat.id;
          const cidEsc = esc(catId);
          const lines = catDetailLines(catId);
          const b = taxBudget[catId] || {};
          const hasData = lines.length > 0 || Number(b.annual_budget) > 0;
          const lineTotal = catDetailSum(catId);
          const displayTotal = lineTotal || Number(b.annual_budget) || 0;
          html += `<div class="budget-cat-entry"><div class="budget-cat-header" style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--line)"><span class="budget-cat-name" style="font-weight:500">${esc(cat.label)}</span>${hasData ? `<span class="small" style="color:var(--muted)">$${Math.round(displayTotal).toLocaleString()}/yr</span>` : ""}${hasData ? `<span style="margin-left:auto"><button class="danger-link" style="font-size:11px" onclick="deleteCategoryBudget('${cidEsc}','${esc(cat.label)}')">Delete</button></span>` : `<span style="margin-left:auto"></span>`}<button class="btn" style="padding:0 8px;font-size:11px" ${readOnlyRef ? "disabled " : ""}onclick="addCategoryDetailRow('${cidEsc}')">+ Add row</button></div>`;
          if (lines.length > 0) {
            html += `<table class="lot-table budget-cat-lines-table" style="margin:0 0 4px 12px;width:calc(100% - 12px)"><thead><tr><th>Label</th><th>Start year</th><th>End year</th><th>Amount / yr</th><th></th></tr></thead><tbody>`;
            lines.forEach(function (l) {
              const lid = esc(l.line_id);
              html += `<tr><td><input value="${esc(l.label || "")}" placeholder="e.g. Europe trip" oninput="updateCategoryDetail('${lid}','label',this.value,'${cidEsc}')" style="width:140px"></td><td><input type="number" value="${esc(l.start_year || "")}" placeholder="—" oninput="updateCategoryDetail('${lid}','start_year',this.value,'${cidEsc}')" style="width:80px"></td><td><input type="number" value="${esc(l.end_year || "")}" placeholder="forever" oninput="updateCategoryDetail('${lid}','end_year',this.value,'${cidEsc}')" style="width:80px"></td><td><input type="text" class="budget-money-input" value="${esc(budgetMoneyInputValue(l.amount_per_year))}" placeholder="$0" onfocus="focusBudgetMoney(this)" oninput="updateCategoryDetailMoney('${lid}','amount_per_year',this,'${cidEsc}')" onblur="blurBudgetMoney(this)" style="width:110px"></td><td><button class="danger-link" onclick="deleteCategoryDetailRow('${lid}','${cidEsc}')">×</button></td></tr>`;
            });
            html += `</tbody></table>`;
          }
          html += `</div>`;
        });
        html += "</div>";
      }
      html += `</div>`;
    });
    html += `</details>`;
  });
  html += `<div class="section-note" style="margin-top:12px"><b>Total annual budget: $${Math.round(grandTotal).toLocaleString()}</b></div>`;
  html += `</div>`;
  return html;
}

function syncTaxonomyBudgetToBudgetLines() {
  try {
    if (!budgetLines || !taxBudget) return;
    const domainCategories = {
      travel: [
        "travel_plane",
        "travel_housing",
        "travel_meals",
        "travel_vacation",
      ],
      healthcare: [
        "medical",
        "dental",
        "vision",
        "healthcare_premium",
        "drugs_rx",
      ],
      housing: [
        "mortgage",
        "rent",
        "property_tax",
        "homeowners_insurance",
        "utilities",
        "maintenance",
      ],
    };
    Object.entries(domainCategories).forEach(([domain, catIds]) => {
      const domainTotal = catIds.reduce((sum, catId) => {
        const budget = taxBudget[catId];
        return (
          sum +
          (budget && budget.annual_budget
            ? parseFloat(budget.annual_budget)
            : 0)
        );
      }, 0);
      if (domainTotal > 0) {
        const existingLine = budgetLines.find(
          (l) => l.section === domain && l.category_id === domain + "_total",
        );
        if (existingLine) {
          existingLine.amount_per_year = String(domainTotal);
        } else {
          const newLine = {
            section: domain,
            line_id: domain + "_total_" + Date.now(),
            label:
              domain.charAt(0).toUpperCase() +
              domain.slice(1) +
              " Budget Total",
            category_id: domain + "_total",
            start_year: "",
            end_year: "",
            one_time_year: "",
            amount_per_year: String(domainTotal),
            mode: "summary",
            notes: "Auto-synced from taxonomy budget",
          };
          budgetLines.push(newLine);
        }
      }
    });
    budgetLinesChanged = true;
  } catch (e) {
    console.warn("Sync error between taxonomy budget and budget lines:", e);
  }
}

async function saveTaxonomyBudgetData() {
  try {
    await api("/api/spending/budget/taxonomy/save", {
      method: "POST",
      body: JSON.stringify({ budget: taxBudget }),
    });
    syncTaxonomyBudgetToBudgetLines();
    taxBudgetChanged = false;
    renderMain();
    showMessage("Spending category changes saved.");
  } catch (e) {
    showMessage("Error saving budget: " + e.message, "error");
  }
}

function updateTaxBudget(catId, field, val) {
  if (!taxBudget[catId]) taxBudget[catId] = { annual_budget: 0, notes: "" };
  taxBudget[catId][field] = val;
  taxBudgetChanged = true;
  syncTaxonomyBudgetToBudgetLines();
}

function trackingBudgetTypesForDomain(domain) {
  if (domain === "core")
    return [
      "Core Expenses",
      "Wellness",
      "Housing",
      "Travel",
      "Large Discretionary",
      "Business",
    ];
  if (domain === "housing") return ["Housing"];
  if (domain === "healthcare") return ["Wellness"];
  if (domain === "travel") return ["Travel"];
  if (domain === "large_discretionary") return ["Large Discretionary"];
  return [];
}
function domainBudgetTitle(domain) {
  return (
    {
      core: "Spending Categories",
      housing: "Housing Budget Detail",
      healthcare: "Wellness Budget Detail",
      travel: "Travel Budget Detail",
      large_discretionary: "Large Discretionary Budget Detail",
    }[domain] || "Budget Detail"
  );
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
function domainLineSections(domain) {
  if (domain === "housing") return ["home_improvement"];
  if (domain === "travel") return ["travel"];
  if (domain === "large_discretionary") return ["large_discretionary"];
  return ["category_budget"];
}
function lineBelongsToDomain(line, domain) {
  const secs = domainLineSections(domain);
  return secs.includes(String(line.section || ""));
}
function visibleBudgetLinesForDomain(domain) {
  return (budgetLines || []).filter((l) => lineBelongsToDomain(l, domain));
}
function loadTemplateGroup(tt, grp) {
  api("/api/spending/restore-template", {
    method: "POST",
    body: JSON.stringify({ tracking_type: tt, group: grp }),
  })
    .then(function (out) {
      if (out && out.success) {
        showMessage(
          (out.count || 0) + " template categories loaded for " + grp + ".",
        );
        clearSpendingCaches();
        loadTaxonomy(true);
        loadSpendingModel(true);
        loadTaxonomyBudget(true);
        loadBudgetLines(true);
      } else
        showMessage(
          (out && out.error) || "Unable to load template categories.",
          "error",
        );
    })
    .catch(function (e) {
      showMessage("Error loading template categories: " + e.message, "error");
    });
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
function renderDomainBudgetTable(domain) {
  if (!taxBudgetLoaded) {
    setTimeout(() => loadTaxonomyBudget(false), 0);
  }
  if (!spendingModelData && !spendingModelLoading) {
    setTimeout(() => loadSpendingModel(false), 0);
  }
  const data = currentSpendingTreeForDomain(domain);
  if (spendingModelError && !data.length)
    return (
      '<div class="missing-list"><p>' +
      esc(spendingModelError) +
      '</p><button class="btn" onclick="reloadDomainBudget(\'' +
      esc(domain) +
      "')\">Reload</button></div>"
    );
  if (!data.length)
    return (
      '<div class="question"><b>No ' +
      esc(domainBudgetTitle(domain)) +
      ' transaction categories loaded.</b><p class="small">Spending Categories shows Tracking Types, Groups, and Categories with non-zero YTD Actual, Annualized Actual, Annual Budget, or Projection Seed. Use Income &amp; Expense Transactions to import transactions, or add budget/projection values on the source page, then Reload.</p></div>'
    );
  let grandTotal = 0;
  data.forEach(function (t) {
    (t.groups || []).forEach(function (g) {
      grandTotal += groupEffectiveBudget(t.tracking_type, g.group);
    });
  });
  let html = "";
  if (domain === "core") {
    html += `<details class="section-note help-detail"><summary style="cursor:pointer;font-weight:500;list-style:none;display:flex;align-items:center;gap:6px"><span style="font-size:13px">▸</span> Annual Budget vs. Projection Seed — when do they differ?</summary><div style="margin-top:8px"><p class="small"><b>Annual Budget</b> is what you entered. <b>Projection Seed</b> is what the engine uses as the year-one spending base for that category. In most cases they are equal. They diverge in four scenarios:</p><ul class="small" style="margin:6px 0 0 18px;line-height:1.8"><li><b>Cap/reference categories</b> (e.g., Medical OOP Cap in Wellness): Annual Budget holds the cap value so you can see it; Projection Seed is forced to <b>$0</b> because a cap is a ceiling on out-of-pocket costs, not a recurring spending input.</li><li><b>Group in Summary mode</b>: The single group-level override number becomes the Projection Seed for the whole group. Any per-category Annual Budget values that were entered before switching to Summary are stale — the engine ignores them and uses the group total.</li><li><b>Detail-line total disagrees with the Annual Budget override</b>: In Detail mode, Projection Seed equals the sum of the detail lines. If you also typed a manual value in the Annual field, it is stored but overridden by the line sum in the projection.</li><li><b>$0 budget categories with transaction history</b>: The category appears in the table because transactions were imported, but Projection Seed = $0, so it contributes nothing to the projected spend base.</li></ul><p class="small" style="margin-top:8px">The <b>Projection Seed</b> column in each group header shows the value that feeds the projection. If it looks wrong compared to Annual Budget, check whether Summary mode is active or whether a cap/reference flag is set on that category.</p></div></details>`;
  }
  html += '<div class="taxonomy-tree">';
  data.forEach(function (typeData) {
    const tt = typeData.tracking_type;
    let ttTotal = 0,
      ttActual = 0,
      ttAnnualized = 0,
      ttProjection = 0;
    (typeData.groups || []).forEach((g) => {
      const eff = groupEffectiveBudget(tt, g.group);
      ttTotal += eff;
      ttProjection += spendingRowProjectionSeed(g) || eff;
      ttActual += spendingRowYtd(g);
      ttAnnualized += spendingRowAnnualized(g);
    });
    const readOnlyRef =
      domain === "core" && ["Housing", "Wellness", "Travel"].includes(tt);
    html += `<details class="taxonomy-type-section" data-dkey="budget:${esc(domain)}:${esc(tt)}"${ttTotal > 0 ? " open" : ""}><summary><b>${esc(tt)}</b> <span class="small">YTD ${dollars0(ttActual)} · Annualized ${dollars0(ttAnnualized)} · Budget ${dollars0(ttTotal)} · Projection Seed ${dollars0(ttProjection || ttTotal)}</span>${tt === "Business" ? ` <span class="small" style="font-weight:400;color:var(--muted)">modeled; excluded from core spend base</span>` : ""}${readOnlyRef ? ` <span class="small" style="font-weight:400;color:var(--muted)">read-only reference</span>` : ""}</summary>`;
    if (readOnlyRef)
      html +=
        '<div class="section-note">This Tracking Type is budgeted on its source page. Values appear here as read-only reference so Spending Categories remains comprehensive without creating duplicate inputs.</div>';
    (typeData.groups || []).forEach(function (grp) {
      const gname = grp.group;
      const gj = esc(gname).replace(/'/g, "\\'");
      const gmode = groupIsSummary(tt, gname) ? "summary" : "detail";
      const gk = groupKeyFor(tt, gname);
      const catSum = groupCatSum(tt, gname);
      const eff = groupEffectiveBudget(tt, gname);
      const catCount = (grp.categories || []).length;
      html += `<div class="taxonomy-group"><h4 class="taxonomy-group-title" style="display:flex;align-items:center;gap:8px;flex-wrap:wrap"><span>${esc(gname)}</span><span class="small" style="font-weight:400">YTD ${dollars0(spendingRowYtd(grp))} · Annualized ${dollars0(spendingRowAnnualized(grp))} · Budget ${dollars0(eff)} · Projection Seed ${dollars0(spendingRowProjectionSeed(grp) || eff)}</span><span style="margin-left:auto"><button class="btn" style="padding:0 8px" ${readOnlyRef ? "disabled " : ""}onclick="loadTemplateGroup('${esc(tt)}','${gj}')">Load template categories for group</button> ${catCount === 0 ? `<button class="danger-link" style="font-size:11px" onclick="deleteTaxonomyGroup('${esc(tt)}','${gj}')">Delete group</button>` : ""} <button class="btn ${gmode === "summary" ? "primary" : ""}" style="padding:0 8px" ${readOnlyRef ? "disabled " : ""}onclick="setGroupBudgetMode('${esc(tt)}','${gj}','summary')">Summary</button> <button class="btn ${gmode === "detail" ? "primary" : ""}" style="padding:0 8px" ${readOnlyRef ? "disabled " : ""}onclick="setGroupBudgetMode('${esc(tt)}','${gj}','detail')">Detail</button></span></h4>`;
      if (gmode === "summary") {
        html += `<div class="table-actions"><label class="small">Group budget / yr&nbsp;</label><input ${readOnlyRef ? "disabled " : ""}type="text" class="budget-money-input" value="${esc(budgetMoneyInputValue((taxBudget[gk] || {}).annual_budget))}" placeholder="${catSum > 0 ? dollars0(catSum) : "$0"}" onfocus="focusBudgetMoney(this)" oninput="updateTaxBudgetMoney('${esc(gk)}','annual_budget',this)" onblur="blurBudgetMoney(this)" style="width:140px"> <span class="small">category and line detail disabled — group number wins</span></div>`;
      } else {
        html += '<div class="budget-cat-detail-list">';
        (grp.categories || []).forEach(function (cat) {
          const catId = cat.id;
          const cidEsc = esc(catId);
          const b = taxBudget[catId] || {};
          const catHasExplicitBudget = hasExplicitBudget(catId);
          const lineTotal = catDetailSum(catId);
          const displayTotal =
            lineTotal ||
            (catHasExplicitBudget
              ? budgetAmount(b.annual_budget)
              : spendingRowBudget(cat));
          const hasData =
            catDetailLines(catId).length > 0 ||
            catHasExplicitBudget ||
            spendingRowBudget(cat) > 0 ||
            spendingRowProjectionSeed(cat) > 0;
          html += `<div class="budget-cat-entry"><div class="budget-cat-header" style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--line)"><span class="budget-cat-name" style="font-weight:500">${esc(cat.label)}</span><span class="small" style="color:var(--muted)">${cat.actual || cat.annualized || hasData ? `YTD Actual ${dollars0(spendingRowYtd(cat))} · Annualized Actual ${dollars0(spendingRowAnnualized(cat))}${hasData ? ` · Annual Budget ${dollars0(displayTotal)}/yr · Projection Seed ${dollars0(spendingRowProjectionSeed(cat) || displayTotal)}` : ""}` : ""}</span><span style="margin-left:auto"><button class="danger-link" style="font-size:11px" ${readOnlyRef ? "disabled" : ""} onclick="deleteTaxonomyCat('${cidEsc}','${esc(cat.label)}')">Delete</button></span><label class="small">Annual <input ${readOnlyRef ? "disabled " : ""}type="text" class="budget-money-input" value="${esc(budgetMoneyInputValue(b.annual_budget))}" placeholder="$0" onfocus="focusBudgetMoney(this)" oninput="updateTaxBudgetMoney('${cidEsc}','annual_budget',this)" onblur="blurBudgetMoney(this)" style="width:100px"></label></div></div>`;
        });
        html += "</div>";
        const allGroupLines = [];
        (grp.categories || []).forEach(function (cat) {
          catDetailLines(cat.id).forEach(function (l) {
            allGroupLines.push(l);
          });
        });
        if (allGroupLines.length > 0) {
          html += `<table class="lot-table budget-cat-lines-table" style="margin:4px 0;width:100%"><thead><tr><th>Category</th><th>Label</th><th>Start year</th><th>End year</th><th>One-time year</th><th>Amount / yr</th><th></th></tr></thead><tbody>`;
          allGroupLines.forEach(function (l) {
            const lid = esc(l.line_id);
            const cidEsc = esc(l.category_id || "");
            html += `<tr><td><select ${readOnlyRef ? "disabled " : ""} onchange="updateGroupDetailCategory('${lid}',this.value,'${cidEsc}')">${(grp.categories || []).map((c) => `<option value="${esc(c.id)}"${c.id === l.category_id ? " selected" : ""}>${esc(c.label)}</option>`).join("")}</select></td><td><input value="${esc(l.label || "")}" placeholder="description" oninput="updateCategoryDetail('${lid}','label',this.value,'${cidEsc}')" style="width:120px"></td><td><input type="number" value="${esc(l.start_year || "")}" placeholder="—" oninput="updateCategoryDetail('${lid}','start_year',this.value,'${cidEsc}')" style="width:72px"></td><td><input type="number" value="${esc(l.end_year || "")}" placeholder="forever" oninput="updateCategoryDetail('${lid}','end_year',this.value,'${cidEsc}')" style="width:72px"></td><td><input type="number" value="${esc(l.one_time_year || "")}" placeholder="—" oninput="updateCategoryDetail('${lid}','one_time_year',this.value,'${cidEsc}')" style="width:72px"></td><td><input type="text" class="budget-money-input" value="${esc(budgetMoneyInputValue(l.amount_per_year))}" placeholder="$0" onfocus="focusBudgetMoney(this)" oninput="updateCategoryDetailMoney('${lid}','amount_per_year',this,'${cidEsc}')" onblur="blurBudgetMoney(this)" style="width:100px"></td><td><button class="danger-link" onclick="deleteCategoryDetailRow('${lid}','${cidEsc}')">×</button></td></tr>`;
          });
          html += "</tbody></table>";
        }
        html += `<div class="table-actions" style="margin-top:4px"><button class="btn" style="font-size:12px" ${readOnlyRef ? "disabled " : ""} onclick="addGroupDetailRow('${esc(tt)}','${gj}')">+ Add row</button></div>`;
      }
      html += "</div>";
    });
    html += "</details>";
  });
  html += `<div class="section-note" style="margin-top:12px"><b>${esc(domainBudgetTitle(domain))} total: $${Math.round(grandTotal).toLocaleString()}/yr</b></div>`;
  html += "</div>";
  return html;
}
function renderDomainBudgetPage(domain, opts) {
  opts = opts || {};
  if (
    !taxonomyData ||
    !spendingModelData ||
    !budgetLinesLoaded ||
    !taxBudgetLoaded
  ) {
    setTimeout(() => {
      loadTaxonomy(false);
      loadSpendingModel(false);
      loadBudgetLines(false);
      loadTaxonomyBudget(false);
    }, 0);
  }
  let html = '<div class="holdings">';
  if (!opts.embedded)
    html +=
      '<h3 class="group-title">' + esc(domainBudgetTitle(domain)) + "</h3>";
  html +=
    '<div class="section-note">' + esc(domainBudgetNote(domain)) + "</div>";
  html +=
    '<div class="table-actions"><button class="btn primary" ' +
    (budgetLinesChanged || taxBudgetChanged ? "" : "disabled") +
    ' onclick="saveAll(true)">Save Changes</button><button class="btn" onclick="reloadDomainBudget(\'' +
    esc(domain) +
    "')\">Reload</button>" +
    (domain === "core"
      ? '<button class="btn" onclick="recoverPriorSpendingBudget()">Recover prior budget values</button><button class="btn" onclick="hideUnusedTemplateCategories()">Hide unused template categories</button>'
      : "") +
    "</div>";
  if (!taxonomyData) {
    html += '<div class="question"><b>Loading…</b></div></div>';
    return html;
  }
  html += renderDomainBudgetTable(domain);
  html += "</div>";
  return html;
}
function renderCoreSpendingUnified() {
  let html = renderSpendingCore();
  html +=
    '<div style="margin-top:32px">' + renderDomainBudgetPage("core") + "</div>";
  html += '<div style="margin-top:32px">' + renderTaxonomyManager() + "</div>";
  return html;
}
function renderTravelBudgetPage() {
  return renderDomainBudgetPage("travel");
}
const LARGE_DISC_TYPES = ["Wedding", "Large Gifts", "Other"];
function largeDiscTypeFromLine(line) {
  const cid = String(line.category_id || "").toLowerCase();
  const label = String(line.label || "").toLowerCase();
  if (
    cid === "weddings" ||
    cid === "children_weddings" ||
    label.includes("wedding")
  )
    return "Wedding";
  if (
    cid === "significant_gifts" ||
    cid === "large_gifts" ||
    label.includes("gift")
  )
    return "Large Gifts";
  return "Other";
}
function largeDiscCategoryFromType(type) {
  if (type === "Wedding") return "weddings";
  if (type === "Large Gifts") return "significant_gifts";
  return "other_large_discretionary";
}
function updateLargeDiscLine(lineId, field, val) {
  const l = (budgetLines || []).find((x) => x.line_id === lineId);
  if (!l) return;
  if (field === "type") {
    l.category_id = largeDiscCategoryFromType(val);
    if (!String(l.label || "").trim()) l.label = val;
  } else {
    l[field] = val;
  }
  markBudgetLinesDirty();
}
function addLargeDiscLine() {
  budgetLines.push({
    section: "large_discretionary",
    line_id: "ld_" + (Date.now() % 1000000),
    label: "",
    category_id: "other_large_discretionary",
    start_year: "",
    end_year: "",
    one_time_year: "",
    amount_per_year: "",
    mode: "detail",
    notes: "",
  });
  markBudgetLinesDirty();
  renderMain();
}
async function deleteLargeDiscLine(lineId) {
  if (
    !(await showInAppConfirm("This cannot be undone.", {
      title: "Delete Budget Detail",
      confirmLabel: "Delete",
      variant: "danger",
    }))
  )
    return;
  budgetLines = (budgetLines || []).filter((l) => l.line_id !== lineId);
  markBudgetLinesDirty();
  renderMain();
}
const LARGE_DISC_CATEGORY_IDS = [
  "weddings",
  "children_weddings",
  "significant_gifts",
  "other_large_discretionary",
];
function renderLargeDiscretionaryBudgetPage() {
  if (!budgetLinesLoaded) {
    setTimeout(() => loadBudgetLines(false), 0);
  }
  const lines = (budgetLines || []).filter(
    (l) =>
      String(l.section || "") === "large_discretionary" ||
      LARGE_DISC_CATEGORY_IDS.includes(String(l.category_id || "")),
  );
  let total = 0;
  lines.forEach((l) => {
    total += Number(String(l.amount_per_year || "").replace(/[$,]/g, "")) || 0;
  });
  let html =
    '<div class="holdings"><div class="table-actions"><button class="btn primary" ' +
    (budgetLinesChanged ? "" : "disabled") +
    ' onclick="saveAll(true)">Save Changes</button><button class="btn" onclick="loadBudgetLines(true)">Reload</button><button class="btn" onclick="addLargeDiscLine()">Add Row</button></div>';
  html +=
    '<div class="lot-table-wrap"><table class="lot-table travel-table"><thead><tr><th>Type</th><th>Description</th><th>Amount</th><th>Year</th><th>Repeat Start</th><th>Repeat End</th><th>Notes</th><th>Actions</th></tr></thead><tbody>';
  if (!lines.length) {
    html +=
      '<tr><td colspan="8" class="small" style="padding:12px">No Large Discretionary projection rows. Add Wedding, Large Gifts, or Other as needed.</td></tr>';
  }
  lines.forEach(function (l) {
    const lid = esc(l.line_id);
    const typ = largeDiscTypeFromLine(l);
    html += `<tr><td><select onchange="updateLargeDiscLine('${lid}','type',this.value)">${LARGE_DISC_TYPES.map((t) => `<option value="${esc(t)}" ${t === typ ? "selected" : ""}>${esc(t)}</option>`).join("")}</select></td><td><input value="${esc(l.label || "")}" placeholder="Description" oninput="updateLargeDiscLine('${lid}','label',this.value)" style="width:160px"></td><td><input type="text" class="budget-money-input" value="${esc(budgetMoneyInputValue(l.amount_per_year))}" onfocus="focusBudgetMoney(this)" oninput="updateLargeDiscLineMoney('${lid}','amount_per_year',this)" onblur="blurBudgetMoney(this)" style="width:110px"></td><td><input type="number" value="${esc(l.one_time_year || "")}" placeholder="one-time" oninput="updateLargeDiscLine('${lid}','one_time_year',this.value)" style="width:90px"></td><td><input type="number" value="${esc(l.start_year || "")}" placeholder="—" oninput="updateLargeDiscLine('${lid}','start_year',this.value)" style="width:90px"></td><td><input type="number" value="${esc(l.end_year || "")}" placeholder="forever" oninput="updateLargeDiscLine('${lid}','end_year',this.value)" style="width:90px"></td><td><input value="${esc(l.notes || "")}" placeholder="Optional" oninput="updateLargeDiscLine('${lid}','notes',this.value)" style="width:180px"></td><td><button class="danger-link" onclick="deleteLargeDiscLine('${lid}')">Delete</button></td></tr>`;
  });
  html +=
    '</tbody></table></div><div class="section-note"><b>Total Large Discretionary rows: $' +
    Math.round(total).toLocaleString() +
    "/yr or scheduled amount</b></div></div>";
  return html;
}

function renderSpendingBudgetInput() {
  return renderDomainBudgetPage("core");
}

function renderSpendingSetup() {
  return renderCoreSpendingUnified();
}

async function saveSpendingSetupAll() {
  try {
    await Promise.all([
      rulesChanged ? saveMappingRulesData() : Promise.resolve(),
      taxBudgetChanged ? saveTaxonomyBudgetData() : Promise.resolve(),
      budgetLinesChanged ? saveBudgetLines() : Promise.resolve(),
    ]);
    showMessage("Spending Categories saved.", "success");
    renderMain();
  } catch (e) {
    showMessage("Error saving spending setup: " + e.message, "error");
  }
}
async function reloadSpendingSetup() {
  clearSpendingCaches();
  mappingRules = null;
  await Promise.all([
    loadTaxonomy(true),
    loadSpendingModel(true),
    loadBudgetLines(true),
    loadTaxonomyBudget(true),
    loadMappingRules(true),
  ]);
  renderMain();
}

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
function renderPlanDataReport() {
  var REPORT_SECS = [
    {
      id: "household",
      label: "Household & Timing",
      stepIds: ["household_people"],
    },
    {
      id: "income",
      label: "Income",
      stepIds: ["income_work", "income_retirement"],
    },
    {
      id: "spending",
      label: "Spending",
      stepIds: [
        "spending_core",
        "retirement_wellness",
        "spending_mortgage_events",
        "spending_travel",
        "spending_travel_extras",
        "ytd_transactions",
      ],
    },
    { id: "healthcare", label: "Wellness", stepIds: ["retirement_wellness"] },
    { id: "housing", label: "Housing", stepIds: ["spending_mortgage_events"] },
    {
      id: "assets",
      label: "Assets & Holdings",
      stepIds: [
        "holdings",
        "assets_home_cash",
        "assets_special",
        "annuity_death_benefits",
      ],
    },
    { id: "estate", label: "Estate", stepIds: ["estate"] },
    {
      id: "risk",
      label: "Risk & Assumptions",
      stepIds: ["monte_carlo_options", "scenarios", "allocation_policy"],
    },
  ];
  var active = activePlanReportSection || "household";
  var sec =
    REPORT_SECS.find(function (s) {
      return s.id === active;
    }) || REPORT_SECS[0];

  var nav = '<div class="plan-report-nav">';
  REPORT_SECS.forEach(function (s) {
    var cls = s.id === active ? "plan-report-tab active" : "plan-report-tab";
    nav +=
      '<button class="' +
      cls +
      '" type="button" onclick="setPlanReportSection(\'' +
      s.id +
      "')\">" +
      esc(s.label) +
      "</button>";
  });
  nav += "</div>";
  var tools =
    '<div class="plan-data-preview-tools"><div><b>Plan Data Summary preview</b><span>Read-only saved input packet for final review. Print or save this section as PDF before sharing reports.</span></div><div class="pane-actions"><button class="btn primary" type="button" onclick="window.print()">Print / Save PDF</button><button class="btn" type="button" onclick="goToReportsTab(\'Build\')">Go to Build</button></div></div>';

  var body = "";

  if (sec.id === "assets") {
    body += '<div class="plan-report-section">';
    body += '<h3 class="group-title">Investment Holdings</h3>';
    if (holdingsPriceData === null) {
      if (!holdingsPriceLoading) setTimeout(loadHoldingsPriceData, 0);
      body += '<div class="section-note">Loading current prices...</div>';
    }
    var holdingData = (ensureHoldingRows().data || []).slice();
    holdingData.sort(function (a, b) {
      var t = String(a.symbol || "").localeCompare(String(b.symbol || ""));
      if (t !== 0) return t;
      return String(a.purchase_date || "").localeCompare(
        String(b.purchase_date || ""),
      );
    });
    var byAccount = {};
    var acctOrder = [];
    var anyEstimate = false;
    holdingData.forEach(function (h) {
      var acct = String(h.account || "Unknown").trim();
      if (!byAccount[acct]) {
        byAccount[acct] = { byTicker: {}, tickerOrder: [] };
        acctOrder.push(acct);
      }
      var tk = String(h.symbol || "").trim() || "(no ticker)";
      if (!byAccount[acct].byTicker[tk]) {
        byAccount[acct].byTicker[tk] = [];
        byAccount[acct].tickerOrder.push(tk);
      }
      byAccount[acct].byTicker[tk].push(h);
    });
    if (acctOrder.length) {
      // Alphabetize accounts by their display (nickname) label for the review.
      acctOrder.sort(function (a, b) {
        return accountDisplayLabel(a).localeCompare(accountDisplayLabel(b));
      });
      body += '<div class="holdings-report">';
      acctOrder.forEach(function (acct) {
        var acctData = byAccount[acct];
        // Per-symbol totals and the account total up front so both are shown in
        // the collapsed <summary> lines, not only when the group is expanded.
        // Totals use current market value (last cached/live price), not cost basis.
        var tickerTotals = {};
        var acctTotal = 0;
        acctData.tickerOrder.forEach(function (tk) {
          var t = 0;
          acctData.byTicker[tk].forEach(function (h) {
            var lv = holdingLotCurrentValue(h);
            t += lv.value;
            if (lv.isEstimate) anyEstimate = true;
          });
          tickerTotals[tk] = t;
          acctTotal += t;
        });
        // Alphabetize symbols within the account, but always sort CASH last.
        var tickers = acctData.tickerOrder.slice().sort(function (a, b) {
          var ca = /^cash$/i.test(a),
            cb = /^cash$/i.test(b);
          if (ca !== cb) return ca ? 1 : -1;
          return String(a).localeCompare(String(b));
        });
        body +=
          '<details class="holdings-account-group" open><summary>' +
          esc(accountDisplayLabel(acct)) +
          ' <span class="small holdings-group-total">' +
          esc(currencyDisplay(acctTotal)) +
          '</span></summary><div class="holdings-ticker-list">';
        tickers.forEach(function (tk) {
          var lots = acctData.byTicker[tk];
          var tickerTotal = tickerTotals[tk];
          body +=
            '<details class="holdings-ticker-group" open><summary>' +
            esc(tk) +
            ' <span class="small holdings-group-total">' +
            esc(currencyDisplay(tickerTotal)) +
            "</span></summary>";
          body +=
            '<div class="lot-table-wrap"><table class="lot-table"><thead><tr><th>Date</th><th>Shares</th><th>Cost Basis/sh</th><th>Current Value</th><th>Lot Type</th></tr></thead><tbody>';
          lots.forEach(function (h) {
            var lv = holdingLotCurrentValue(h);
            var estMark = lv.isEstimate
              ? ' <span class="small" title="No cached/live price found for this symbol; showing cost basis as a fallback estimate.">≈</span>'
              : "";
            body +=
              "<tr><td>" +
              esc(h.purchase_date || "") +
              "</td><td>" +
              esc(h.shares || "") +
              "</td><td>" +
              esc(currencyDisplay(h.purchase_price || 0)) +
              "</td><td>" +
              esc(currencyDisplay(lv.value)) +
              estMark +
              "</td><td>" +
              esc(h.lot_type || "") +
              "</td></tr>";
          });
          body += "</tbody></table></div></details>";
        });
        body +=
          '</div><div class="holdings-account-subtotal"><b>' +
          esc(accountDisplayLabel(acct)) +
          " total: " +
          esc(currencyDisplay(acctTotal)) +
          "</b></div></details>";
      });
      body += "</div>";
      if (anyEstimate)
        body +=
          '<div class="section-note small">≈ No cached/live price was found for one or more symbols; cost basis is shown as a fallback estimate for those lots.</div>';
    } else {
      body +=
        '<p class="small">No holdings loaded. Add holdings on the Investment Holdings tab.</p>';
    }
    body += "</div>";
  }

  (sec.stepIds || []).forEach(function (stepId) {
    if (stepId === "holdings") return;
    var stepRows = rowsForStep(stepId);
    // For the estate step: hide Special Needs rows unless the Special Needs
    // Planning optional workbook module is enabled.
    if (
      stepId === "estate" &&
      !optionalFunctionEnabled("special_needs_planning")
    ) {
      stepRows = stepRows.filter(function (r) {
        return !norm(r.subsection || "").startsWith("sn_");
      });
    }
    if (!stepRows.length) return;
    var stepDef = STEPS.find(function (s) {
      return s.id === stepId;
    });
    var stepTitle = stepDef ? stepDef.title : stepId;
    body += '<div class="plan-report-section">';
    body += '<h3 class="group-title">' + esc(stepTitle) + "</h3>";
    var bySub = {};
    var subOrder = [];
    stepRows.forEach(function (r) {
      var sub = r.subsection || "";
      if (!bySub[sub]) {
        bySub[sub] = [];
        subOrder.push(sub);
      }
      bySub[sub].push(r);
    });
    subOrder.forEach(function (sub) {
      var subRows = bySub[sub];
      if (sub) {
        var subLabel = humanLabel(sub, null);
        if (subLabel && subLabel !== sub)
          body +=
            '<div class="plan-report-subsection">' + esc(subLabel) + "</div>";
      }
      body += '<div class="plan-report-rows">';
      subRows.forEach(function (r) {
        var val = valOf(r);
        var display = String(val || "");
        if (typeof displayValueForInput === "function")
          try {
            display = displayValueForInput(r, val) || display;
          } catch (e) {}
        var isEmpty =
          !display || display.trim() === "" || display.trim() === "0";
        body +=
          '<div class="plan-report-row' +
          (isEmpty ? " plan-report-empty" : "") +
          '">';
        body +=
          '<span class="plan-report-label">' +
          esc(humanLabel(r.label, r)) +
          "</span>";
        body +=
          '<span class="plan-report-value' +
          (isEmpty ? " muted" : "") +
          '">' +
          esc(isEmpty ? "—" : display) +
          "</span>";
        body += "</div>";
      });
      body += "</div>";
    });
    body += "</div>";
  });

  if (!body && sec.id !== "assets") {
    body =
      '<div class="section-note">No data found for this section. Fill in the input tabs and save to see data here.</div>';
  }

  return (
    '<div class="holdings plan-report-wrap">' + tools + nav + body + "</div>"
  );
}
const REPORTS_TABS = [
  "Preflight",
  "Build",
  "Impact",
  "Results",
  "Downloads",
  "Plan Data Review",
];
let reportsActiveTab = "Results";
try {
  reportsActiveTab = localStorage.getItem("reports_active_tab") || "Results";
} catch (_e) {}
function setReportsTab(tab) {
  reportsActiveTab = REPORTS_TABS.includes(tab) ? tab : "Preflight";
  try {
    localStorage.setItem("reports_active_tab", reportsActiveTab);
  } catch (_e) {}
  renderMain();
}
function goToReportsTab(tab) {
  activeStep = "reports_and_review";
  setReportsTab(tab);
}
function renderTabbedWorkspace(tabs, active, handlerName) {
  return `<div class="workspace-tabs" role="tablist">${tabs.map((t) => `<button class="workspace-tab ${t === active ? "active" : ""}" type="button" role="tab" aria-selected="${t === active ? "true" : "false"}" onclick="${handlerName}('${escJs(t)}')">${esc(t)}</button>`).join("")}</div>`;
}
function renderStrategyTabs(step, tabs, active) {
  return `<div class="workspace-tabs" role="tablist">${tabs.map((t) => `<button class="workspace-tab ${t === active ? "active" : ""}" type="button" role="tab" aria-selected="${t === active ? "true" : "false"}" onclick="setStrategyTab('${escJs(step)}','${escJs(t)}')">${esc(t)}</button>`).join("")}</div>`;
}
function renderReportsPreflight() {
  const stats = overallStats();
  const missing = stats.missing || [];
  let html =
    '<div class="reports-panel"><h3>Preflight</h3><p class="small">Check whether the plan is complete enough to build reports.</p>' +
    firstRunChecklistHtml(true) +
    renderBuildPreflightPanel();
  if (missing.length) {
    html += `<div class="missing-list"><h3>Needs attention</h3><ul>${missing
      .slice(0, 20)
      .map(
        (r) =>
          `<li>${esc(humanLabel(r.label, r))} <span class="small">(${esc(friendlyGroup(r))})</span></li>`,
      )
      .join("")}</ul></div>`;
  } else {
    html +=
      '<div class="section-note ok"><b>Plan is ready to build.</b> Warnings may still appear, but no required fields are missing.</div>';
  }
  html += `<div class="pane-actions"><button class="btn primary" type="button" onclick="setReportsTab('Build');runBuild(false)">Build Now</button></div></div>`;
  return html;
}
function renderReportsBuild() {
  const fresh = planStateFresh();
  const arts = planStateArtifactsReady();
  let statusHtml = "";
  if (lastBuildSummary) {
    const ts =
      lastBuildSummary.timestamp || lastBuildSummary.build_timestamp || "";
    const qc = lastBuildSummary.qc_result || "not reviewed";
    statusHtml = `<div class="section-note ${fresh ? "ok" : "warn"}">Last build${ts ? " — " + esc(ts) : ""} — QC: ${esc(qc)}. ${fresh ? "Outputs are current." : "Inputs changed since last build — rebuild for current outputs."}</div>`;
  } else if (arts) {
    statusHtml =
      '<div class="section-note ok">Report outputs are present but no build summary is on record.</div>';
  } else {
    statusHtml =
      '<div class="section-note">No build on record. Build Reports creates the workbook, PDF, and Results Explorer.</div>';
  }
  return `<div class="reports-panel"><h3>Build</h3><p class="small">Save the current plan and run the full projection engine. Creates the workbook, PDF, and Results Explorer model. Progress appears in the build overlay.</p><div class="pane-actions"><button class="btn primary" type="button" data-requires-app="1" onclick="runBuild(false)">Build Reports</button><button class="btn" type="button" onclick="refreshBuildStatus()">Refresh Status</button></div>${statusHtml}</div>`;
}
function renderReportsAndReview() {
  const active = REPORTS_TABS.includes(reportsActiveTab)
    ? reportsActiveTab
    : "Preflight";
  let body = "";
  if (active === "Preflight") body = renderReportsPreflight();
  else if (active === "Build") body = renderReportsBuild();
  else if (active === "Impact") body = renderBuildImpactPage();
  else if (active === "Results") body = renderDetailedResults();
  else if (active === "Downloads") body = renderReview();
  else if (active === "Plan Data Review") body = renderPlanDataReport();
  return `<div class="tabbed-workspace reports-workspace">${renderTabbedWorkspace(REPORTS_TABS, active, "setReportsTab")}<div class="workspace-tab-body">${body}</div></div>`;
}
const STRATEGY_TABS = {
  distribution_strategy: [
    "Levers",
    "Roth Conversion",
    "Withdrawal Order",
    "Allocation & Location",
  ],
};
function strategyTabKey(step) {
  return "strategy_tab_" + step;
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
// Jump to a strategy workspace tab from the left nav. Persists the tab first,
// then routes through setStep so the plan-loaded navigation guard applies (the
// strategy workspace requires a loaded plan, unlike the plan-independent
// Reports workspace).
function goToStrategyTab(step, tab) {
  const tabs = STRATEGY_TABS[step] || [];
  const next = tabs.includes(tab) ? tab : tabs[0] || "";
  try {
    localStorage.setItem(strategyTabKey(step), next);
  } catch (_e) {}
  setStep(step);
}
function renderDistributionStrategy() {
  const tab = getStrategyTab("distribution_strategy");
  let body;
  if (tab === "Roth Conversion")
    body = analysisFrame(renderRothConversion(), "strategy");
  else if (tab === "Withdrawal Order")
    body = analysisFrame(renderWithdrawalStrategy(), "strategy");
  else if (tab === "Allocation & Location")
    body = analysisFrame(renderAllocationRecommendation(), "strategy");
  else body = renderPlanningLevers();
  return `<div class="tabbed-workspace strategy-workspace">${renderStrategyTabs("distribution_strategy", STRATEGY_TABS.distribution_strategy, tab)}<div class="workspace-tab-body">${body}</div></div>`;
}
function renderSpecialStrategies() {
  let html = '<div class="special-strategy-workspace">';
  if (helocModuleEnabled())
    html += `<details open><summary>Home Equity Line</summary>${analysisFrame(renderFields("heloc_strategy"), "strategy")}</details>`;
  if (optionalFunctionEnabled("charitable_giving"))
    html += `<details open><summary>Charitable Giving</summary>${analysisFrame(renderEntityCharitable(), "strategy")}</details>`;
  if (!helocModuleEnabled() && !optionalFunctionEnabled("charitable_giving"))
    html +=
      '<div class="section-note">Both strategies on this page are optional modules that are currently turned off. Enable HELOC (HELOC → Setup → Enable HELOC Strategy) or Charitable Giving (Optional Modules) to use them.</div>';
  html += "</div>";
  return html;
}
function renderDafConfig() {
  if (!optionalFunctionEnabled("charitable_giving"))
    return `<div class="section-note">Donor-advised fund inputs are hidden until Charitable Giving is enabled under <a href="#" onclick="setStep('optional_functions');return false">Optional Modules</a>.</div>`;
  const rs = rows.filter(
    (r) => isEditable(r) && friendlyGroup(r) === "DAF",
  );
  if (!rs.length)
    return `<div class="section-note">No DAF rows found in Plan Data. Reload Plan Data, or add a [DAF][Settings] section.</div>`;
  return `<div class="section-note">Contribution amount/year fund the DAF in a lump sum (tax-deductible up to 60% of AGI in the contribution year); annual grant amount/start/end schedule ongoing charitable distributions out of the DAF balance. See Charitable Giving in the workbook report for a sizing recommendation.</div><div class="field-list">${rs.map(fieldHtml).join("")}</div>`;
}
function renderLifestyleSpending() {
  return `<div class="lifestyle-workspace"><details open><summary>Travel</summary>${renderTravelBudgetPage()}</details><details open><summary>Large Items</summary>${renderLargeDiscretionaryBudgetPage()}</details><details ${optionalFunctionEnabled("charitable_giving") ? "open" : ""}><summary>Donor-Advised Fund (DAF)</summary>${renderDafConfig()}</details></div>`;
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
  spending_core: "ytd_transactions",
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
function renderMain() {
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
    content += `<button class="btn good" data-requires-app="1" onclick="downloadWithBuild('/api/xlsx','Workbook')">Download Workbook</button><button class="btn good" data-requires-app="1" onclick="downloadWithBuild('/api/pdf','PDF')">Download PDF</button>`;
  content += `</div></div><div class="question"><b>${esc(st.desc)}</b>${esc(st.help)}</div>`;
  content += inactiveValuesPanel(activeStep);
  content += pageRecommendationsHtml(activeStep);
  if (SPENDING_WORKFLOW_INDEX[activeStep] !== undefined) {
    content += renderSpendingWorkflowBanner(activeStep);
  }
  if (activeStep === "start") content += renderWelcome();
  else if (activeStep === "spending_core")
    content += renderCoreSpendingUnified();
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
    content += analysisFrame(renderAllocationRecommendation(), "strategy");
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
  document.getElementById("mainPane").innerHTML = content;
  document.querySelectorAll("#mainPane details").forEach(function (d) {
    const k = _dKey(d);
    if (k && Object.prototype.hasOwnProperty.call(_dOpen, k))
      d.open = _dOpen[k];
  });
  setAppControls(appReady);
  showStepHelp(activeStep);
}

function navigationContext() {
  return {
    getPlanLoaded: () => planLoaded,
    getActiveStep: () => activeStep,
    setActiveStep: (v) => {
      activeStep = v;
    },
    getLastBuildCompare: () => lastBuildCompare,
    getLastBuildOk: () => lastBuildOk,
    getDetailedResultsData: () => detailedResultsData,
    setSearchText: (v) => {
      searchText = v;
    },
    getSearchText: () => searchText,
    setNavSearchText: (v) => {
      navSearchText = v;
    },
    getNavSearchText: () => navSearchText,
    setSearchScope: (v) => {
      searchScope = v;
    },
    getSearchScope: () => searchScope,
    renderMain: renderMain,
    renderSteps: renderSteps,
    setReportsTab: setReportsTab,
    setAppControls: setAppControls,
    showStepHelp: showStepHelp,
    showMessage: showMessage,
    loadDetailedResults: loadDetailedResults,
    focusableEntries: focusableEntries,
    saveYtdPending: saveYtdPending,
    saveMappingRulesData: saveMappingRulesData,
    saveTaxonomyBudgetData: saveTaxonomyBudgetData,
    saveBudgetLines: saveBudgetLines,
    getRulesChanged: () => rulesChanged,
    getTaxBudgetChanged: () => taxBudgetChanged,
    getBudgetLinesChanged: () => budgetLinesChanged,
    hasUnsavedPlanChanges: hasUnsavedPlanChanges,
    confirm: function (msg, opts) {
      return showInAppConfirm(msg, opts);
    },
    jumpRecommendationSource: jumpRecommendationSource,
    planningCaseCreate: planningCaseCreate,
    planningCaseDelete: planningCaseDelete,
    planningCaseArchive: planningCaseArchive,
    planningCaseAdopt: planningCaseAdopt,
    setPlanningCaseActive: setPlanningCaseActive,
    setDetailedResultSheet: setDetailedResultSheet,
    setDetailedResultsNavOpen: setDetailedResultsNavOpen,
    loadDetailedResultSheet: loadDetailedResultSheet,
    toggleDetailColumnGroup: toggleDetailColumnGroup,
    setAllDetailColumnGroups: setAllDetailColumnGroups,
    setDetailColGroupOpen: function (key, open) {
      detailedColumnGroupsOpen[key] = !!open;
      saveWorkbookViewState();
      setTimeout(renderMain, 0);
    },
    visibleSteps: visibleSteps,
    setStep: setStep,
  };
}
function setStep(id) {
  return window.RetirementNavigation.setStep(navigationContext(), id);
}
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
function setSearch(q) {
  searchText = q;
  renderMain();
  updateSearchToggle();
}
let statusTimer = null;
function scheduleStatusUpdate() {
  clearTimeout(statusTimer);
  statusTimer = setTimeout(() => {
    renderSteps();
    setAppControls(appReady);
  }, 120);
}
function editValue(idx, val, el) {
  const row = rows.find((r) => r.row_index === idx);
  const stored = storageValueForInput(row, val);
  const original = storageValueForInput(row, row?.value || "");
  if (String(stored) === String(original)) {
    dirty.delete(idx);
  } else {
    dirty.set(idx, String(stored));
    noteSessionFieldChange(
      row,
      displayValueForInput(row, row?.value || ""),
      displayValueForInput(row, stored),
      original,
      stored,
    );
  }
  lastBuildOk = false;
  const field = el?.closest(".field");
  if (field) {
    const isDirty = dirty.has(idx);
    field.classList.toggle("dirty", isDirty);
    const showReq = isRequired(row) && String(stored).trim() === "";
    field.classList.toggle("missing", showReq);
    const meta = field.querySelector(".field-meta");
    if (meta) {
      meta.innerHTML =
        (showReq ? '<span class="badge req">Required</span>' : "") +
        (isDirty ? '<span class="badge dirty">Edited</span>' : "");
    }
  }
  if (
    row &&
    (activeStep === "allocation_assets" || activeStep === "allocation_policy")
  ) {
    const l = norm(row.label);
    if (
      [
        "allocation_selection_mode",
        "allocation_mode",
        "use_allocation_optimizer",
        "selection_action",
        "alternate_asset_class",
        "target_pct",
        "optimizer_override_pct",
        "holding_period_allocation_enabled",
        "holding_period_floor_strength",
        "real_loss_aware_risk_aversion",
        "real_loss_aware_weight",
        "capital_market_assumption_horizon_source",
      ].includes(l)
    )
      resetAllocationPreview();
    if (
      l === "allocation_selection_mode" ||
      l === "allocation_mode" ||
      l === "use_allocation_optimizer" ||
      l === "selection_action"
    ) {
      renderMain();
      return;
    }
    if (l === "target_pct") {
      const box = document.getElementById("allocationTargetTotal");
      if (box) box.outerHTML = allocationTotalHtml();
    }
    if (l === "optimizer_override_pct") {
      const box = document.getElementById("optimizerOverrideTotal");
      if (box) box.outerHTML = optimizerOverrideTotalHtml();
    }
  }
  updateUnsaved();
  if (window.RetirementAppStore)
    window.RetirementAppStore.markDirty(unsavedChangeCount());
  scheduleStatusUpdate();
}
function showStepHelp(id) {
  document.getElementById("helpPanel").innerHTML =
    STEP_HELP[id] || STEP_HELP.start;
}
const FIELD_GUIDANCE_OVERRIDES = {
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
      "This share compounds the guaranteed payment every future year. The remaining share (1 minus this) pays out as cash income each year until Recovery Age, then stops. Applies from the first-distribution year (first_payment); before that year the full dividend is reinvested regardless of this setting.",
    consider:
      "Ask: what reinvestment/additional-income split does the illustration show? Leave blank to use the household default (Economic Assumptions > annuity_default_additional_income_pct).",
  },
  deferral_years: {
    purpose:
      "Contract years before first_payment where the dividend is 100% reinvested and no income is paid yet.",
    impact:
      "During this window the guaranteed payment grows by dividend_rate x Deferral Dampening each year instead of being paid out. A longer deferral produces a higher starting guaranteed payment once income begins.",
    consider:
      "Use the number of years between contract purchase and the first_payment date shown on the illustration.",
  },
  deferral_dampening: {
    purpose:
      "Dampens how fast the guaranteed payment grows during the deferral period (growth rate = dividend_rate x this value, per deferral year).",
    impact:
      "Lower values slow guaranteed-payment growth before income starts; higher values approach full dividend_rate growth during deferral. Only matters when Deferral Years is greater than zero.",
    consider:
      "Use the value calibrated to the carrier illustration; the model default is 0.55 if left blank.",
  },
  reserve_factor: {
    purpose:
      "The fraction of the account-value base used to anchor the annuity's starting actuarial reserve (reserve_start = base x reserve_factor).",
    impact:
      "The reserve then follows a fixed decay/mortality-credit/growth curve over the payout years, and that reserve is what dividend_rate is credited against each year — so this scales both the compounding guaranteed payment and the cash dividend for the life of the contract.",
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
      "The account bucket the plan should try to preserve for this cash reserve rule.",
    impact:
      "This affects which assets are protected from spending first when the withdrawal engine funds annual needs.",
    consider:
      "Choose Cash for checking/money-market reserves, Taxable/Trust for brokerage reserves, or a retirement/HSA bucket only if that is the intentional reserve source.",
  },
  years_of_expenses: {
    purpose:
      "How many years of spending the plan should try to keep in reserve during this date range.",
    impact:
      "A larger reserve can protect liquidity but may force the model to draw from different accounts sooner.",
    consider: "Use 0 if there is no special reserve requirement.",
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
function fieldGuidance(row) {
  const l = norm(row.label),
    s = norm(row.section),
    sub = norm(row.subsection);
  if (FIELD_GUIDANCE_OVERRIDES[l]) return FIELD_GUIDANCE_OVERRIDES[l];
  let purpose = fieldDefaultMeaning(row);
  let impact =
    "This can affect user-facing results such as annual cash flow, terminal net worth, lifetime taxes, post-terminal estate taxes, Medicare premiums, probability of success, downside risk, or workbook recommendations.";
  let consider =
    "Ask: is this a documented fact, a best estimate, or a scenario lever? If better information supports a higher value, raise it; if the current value is overstated, outdated, or intentionally being stress-tested lower, reduce it.";
  if (l.includes("dob")) {
    purpose = "Sets a person's age for the plan.";
    impact =
      "Affects retirement age, life expectancy horizon, Social Security timing, RMD timing, healthcare years, and tax filing phases.";
    consider =
      "Use the actual birth date. If privacy is a concern in a demo, use a realistic placeholder age.";
  } else if (l.includes("filing_status")) {
    purpose = "Defines the tax filing assumption.";
    impact =
      "Affects federal tax brackets, NIIT thresholds, deductions, and survivor tax modeling.";
    consider =
      "Use the current filing status; update after marriage, divorce, or widowhood.";
  } else if (l.includes("state")) {
    purpose = "Sets the resident state for tax and planning assumptions.";
    impact = "Affects state tax lookup and report labeling.";
    consider =
      "Use the state expected for the modeled retirement period, or update when relocation plans change.";
  } else if (l.includes("retirement")) {
    purpose = "Defines when work income or savings behavior changes.";
    impact =
      "Affects income, payroll tax, contributions, withdrawals, healthcare bridge costs, and Monte Carlo timing.";
    consider =
      "Use the best current target date; test alternatives as scenarios.";
  } else if (
    l.includes("spending") ||
    l.includes("expense") ||
    l.includes("vacation") ||
    l.includes("travel") ||
    l.includes("wedding") ||
    l.includes("home_project")
  ) {
    purpose =
      "Defines planned spending the portfolio or income sources must support.";
    impact =
      "Usually one of the largest drivers of projected cash-flow shortfalls, terminal net worth, Monte Carlo success, and stress-test narratives in the workbook.";
    consider =
      "Use Large Discretionary Expenses for flexible items such as vacations, weddings, home projects, gifts, vehicle purchases, and family support.";
  } else if (
    l.includes("social_security") ||
    l === "ss" ||
    l.includes("pension") ||
    l.includes("annuity")
  ) {
    purpose = "Captures recurring retirement income.";
    impact =
      "Reduces required portfolio withdrawals and may count as fixed-income-like coverage when enabled.";
    consider =
      "Use conservative values and note whether the amount is inflation-adjusted.";
  } else if (l.includes("mortgage") || l.includes("real_estate_taxes")) {
    purpose =
      "Captures home debt, mortgage payments, or real-estate tax cash flow.";
    impact =
      "Affects net worth, cash-flow needs, tax deductions, and retirement spending pressure.";
    consider =
      "Update balance, rate, payment, real-estate tax amount, annual RE tax adjustment, and payoff timing annually.";
  } else if (l.includes("expected_return")) {
    purpose =
      "Sets the long-term return assumption for this asset class in the allocation optimizer.";
    impact =
      "Higher values make the optimizer more willing to recommend the class; lower values reduce its appeal.";
    consider =
      "Use long-term capital-market assumptions, not recent performance. Pair with volatility and correlation.";
  } else if (l.includes("volatility")) {
    purpose = "Sets the risk level for this asset class.";
    impact =
      "Higher volatility makes an asset class less attractive unless return or diversification benefits offset the risk.";
    consider =
      "Volatility should reflect downside experience over the selected horizon.";
  } else if (
    l.includes("allocation_selection_mode") ||
    l === "allocation_mode"
  ) {
    purpose = "Chooses which allocation target the workbook uses.";
    impact =
      "user_target applies the editable target_pct rows; optimizer_recommendation and max_sharpe are risk-tolerance-driven model recommendations; tangency is an unconstrained max-Sharpe reference; real_loss_aware blends a per-holding-period-bucket solve based on this household's own projected withdrawal schedule.";
    consider =
      "Review the recommendation rationale (shown below once selected) and compare it with the user target mix. Keep user target_pct rows totaling 100% even when a computed mode is selected.";
  } else if (l === "holding_period_allocation_enabled") {
    purpose =
      "Opt-in: lets the optimizer/max-Sharpe recommendation modes use this household's own projected withdrawal schedule.";
    impact =
      "When on, near-term (0-2yr) withdrawal-derived liquid balance is floored toward Cash and durable (16+yr) balance is floored toward growth classes, instead of a flat risk-tolerance split alone. Has no effect on user_target or tangency modes.";
    consider =
      "Selecting allocation_selection_mode=real_loss_aware enables the same withdrawal-schedule discovery automatically, so this toggle is mainly for nudging the existing optimizer/max-Sharpe modes rather than switching to the dedicated real-loss-aware mode.";
  } else if (l === "holding_period_floor_strength") {
    purpose =
      "Dials how strongly the holding-period floors (above) are applied.";
    impact =
      "100% applies the full near-term-Cash / long-horizon-growth floor; 0% disables the floor's effect without turning holding_period_allocation_enabled off.";
    consider = "Only has an effect while holding_period_allocation_enabled is on.";
  } else if (
    l === "real_loss_aware_risk_aversion" ||
    l === "real_loss_aware_weight"
  ) {
    purpose =
      "Tunes the per-holding-period-bucket solve used by the real_loss_aware allocation mode.";
    impact =
      l === "real_loss_aware_risk_aversion"
        ? "Higher values penalize variance more heavily within each bucket's solve (same scale as the optimizer's own internal risk aversion)."
        : "Higher values weight each bucket's real-loss-probability penalty more heavily relative to variance and expected return.";
    consider =
      "Only has an effect while allocation_selection_mode is real_loss_aware.";
  } else if (l === "capital_market_assumption_horizon_source") {
    purpose =
      "Chooses how the capital-market planning horizon (above) is determined.";
    impact =
      "manual uses the horizon selected above as-is; auto_from_withdrawals derives the effective horizon from this household's own projected withdrawal schedule instead.";
    consider =
      "Affects every allocation mode's expected-return/volatility assumptions, not just real_loss_aware.";
  } else if (l === "optimizer_override_pct") {
    purpose =
      "Optional manual override for the optimizer recommendation for this asset class.";
    impact =
      "When optimizer mode is selected and any override is entered, the optimizer override percentages replace the computed optimizer target. The override total must equal 100%.";
    consider =
      "Leave all optimizer override rows blank to use the computed optimizer recommendation. Use Copy optimizer override to user-defined when you want these edits to overwrite the user-defined allocation.";
  } else if (l.includes("target_pct")) {
    purpose = "Sets the user-specified target percentage for this asset class.";
    impact =
      "Affects allocation recommendations, drift analysis, and ETF idea guidance when allocation mode is user-specified. All user target_pct rows must total 100%.";
    consider =
      "Start with the default mix in the comment, then adjust with advisor review. Cash is included as its own class.";
  } else if (l.includes("maximum_target")) {
    purpose = "Caps how much the optimizer can allocate to the class.";
    impact =
      "Controls concentration and prevents the optimizer from overusing a high-return or low-risk assumption.";
    consider =
      "Set tighter caps for illiquid, specialized, or hard-to-access asset classes.";
  } else if (l === "selection_action") {
    purpose = "Sets the compact asset-class selection policy.";
    impact =
      "Include allows target exposure, Exclude prevents new recommendation exposure, and Consider alternate first counts the selected existing asset/source toward this class before recommending new exposure.";
    consider =
      "Use Consider alternate first when another plan asset should satisfy the role before this asset class is recommended directly.";
  } else if (l === "alternate_asset_class") {
    purpose =
      "Selects the existing asset or non-liquid source used when the row is set to Consider alternate first.";
    impact =
      "The chosen source is credited against this class before recommending new exposure.";
    consider =
      "Choose an existing asset that reasonably satisfies the same portfolio role, such as pension income toward bonds or home equity toward real estate.";
  } else if (l.includes("pricing_mode") || s.includes("market_pricing")) {
    purpose = "Controls how the system prices holdings.";
    impact = "Affects account totals, allocation, drift, and diagnostics.";
    consider =
      "CACHE is usually best for normal use; LIVE is best for testing; OFFLINE avoids external calls. Cost basis is now a last-resort estimate only when there is no cached quote.";
  } else if (l.includes("sehi")) {
    purpose =
      "Captures SEHI — self-employed health insurance — treatment for S-Corp or self-employed income.";
    impact =
      "Affects adjusted gross income, above-the-line deductions, payroll/W-2 presentation, QBI calculations, and income tax projections.";
    consider =
      "For S-Corp owners, SEHI is commonly included in W-2 Box 1 and then deducted on Schedule 1 when eligibility rules are met. Confirm with the tax preparer.";
  } else if (l.includes("ss_funding_discount")) {
    purpose =
      "Models a Social Security funding shortfall haircut from the configured year onward.";
    impact =
      "Reduces gross Social Security income in the projection, which can lower taxable income, portfolio withdrawals, survivor income, and workbook cash-flow schedules.";
    consider =
      "Ask: do you want to model the current-law funding risk, a no-haircut optimistic case, or a harsher stress? Use 0% for no funding cut; use a higher percentage or earlier year for a more conservative Social Security stress.";
  } else if (l.includes("roth") || sub.includes("roth_conversion")) {
    purpose = "Controls how Roth conversions are sized or scored.";
    impact =
      "Affects the Roth Conversion sheet, current taxable income, future RMD pressure, Medicare IRMAA exposure, survivor tax compression, Roth legacy value, estate-tax-aware strategy ranking, and Executive Summary explanation.";
    consider =
      "Ask: is the goal lower lifetime taxes, higher terminal net worth, survivor protection, or legacy value? A tax-focused answer points to bracket/tax controls; a beneficiary or survivor answer points to Legacy and survivor scoring; a Medicare-premium answer points to IRMAA guardrails.";
  } else if (l.includes("irmaa") || sub.includes("irmaa")) {
    purpose =
      "Controls the Medicare premium threshold guardrail used by Roth conversion and tax planning.";
    impact =
      "Affects the Roth Conversion schedule, projected MAGI, Medicare premium warnings, and any workbook explanation of why conversions stop in a year.";
    consider =
      "Ask: would crossing an IRMAA tier be acceptable for this household? If avoiding Medicare premium jumps matters, use an avoidance guardrail and leave headroom; if tax savings are more important than premium cliffs, loosen or warn-only the guardrail.";
  } else if (l.includes("estate_tax_objective")) {
    purpose =
      "Controls whether estate-tax exposure affects Roth strategy scoring.";
    impact =
      "When active, the optimizer penalizes strategies that increase projected federal or state estate tax; if no estate tax is projected, the impact should be zero.";
    consider =
      "Default Balanced keeps estate awareness active without inventing an estate-tax cost. State estate tax is included only when the selected state rules create projected exposure.";
  } else if (l === "mc_engine_mode") {
    purpose = "Chooses the Monte Carlo engine for this build.";
    impact =
      "Advanced Exact Scalar gives the most realistic probability of success and downside-risk results because every simulated path uses the full projection logic. Quick Vectorized is faster but approximate, so it is best for quick diagnostics and UI testing.";
    consider =
      "Ask: am I experimenting or producing final guidance? Choose Quick Vectorized when you need a fast directional answer; choose Advanced Exact Scalar when the result will be used for recommendations, client review, or final decisions.";
  } else if (l.includes("monte_carlo") || s.includes("monte_carlo")) {
    purpose =
      "Controls how the plan tests uncertainty rather than one fixed projection path.";
    impact =
      "Affects probability of success, downside terminal net worth, liquidity-floor failures, risk ranges, sensitivity grids, and build time.";
    consider =
      "Ask: is build speed or statistical confidence more important right now? Lower counts or Quick mode speed up drafts; higher counts and Advanced mode are better when the success rate will influence a recommendation.";
  } else if (s.includes("annuity_death_benefits")) {
    purpose = "Sets the death benefit payable for a specific policy and year.";
    impact = "Affects estate, survivor, and legacy benefit reporting by year.";
    consider =
      "Enter the value shown on the policy schedule. If a benefit is no longer available in a year, enter 0.";
  }
  return {
    purpose: formatAcronyms(purpose),
    impact: formatAcronyms(impact),
    consider: formatAcronyms(consider),
  };
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
    s.includes("healthcare") ||
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
function showFieldHelp(idx) {
  const row = rows.find((r) => r.row_index === idx);
  if (!row) return;
  const label = humanLabel(row.label, row);
  const note = translatePersonPlaceholders(
    formatAcronyms(row.schema?.description || row.notes || ""),
  );
  const g = fieldGuidance(row);
  const meaning = formatAcronyms(
    g.purpose || note || `${label} is an input used by the planner.`,
  );
  const options = fieldAllowedValues(row);
  const connections = formatAcronyms(fieldConnection(row));
  const impact = formatAcronyms(fieldLikelyImpact(row, g));
  const acronyms = acronymDefinitionsHtml([
    label,
    note,
    meaning,
    connections,
    impact,
    row.units,
  ]);
  const sourceNote =
    note &&
    ![meaning, impact, connections].some((x) => String(x || "").includes(note))
      ? `<h3>Source note</h3><p>${esc(note)}</p>`
      : "";
  const required = isMissing(row)
    ? `<div class="help-callout">This required field still needs a value before the plan is complete.</div>`
    : "";
  document.getElementById("helpPanel").innerHTML =
    `<div class="help-title">${esc(label)}</div><div class="help-body"><h3>What this value means</h3><p>${esc(meaning)}</p><h3>Value options and how to choose</h3>${options}<h3>How it relates to this page</h3><p>${connections}</p><h3>Likely impact of changing it</h3><p>${esc(impact)}</p>${sourceNote}${acronyms}${required}</div>`;
}

async function fetchWithTimeout(url, opts = {}, timeoutMs = 1200) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...opts, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}
let appCheckInFlight = false;
async function checkAppStatus(show = false) {
  if (appCheckInFlight) return appReady;
  appCheckInFlight = true;
  const wasOnline = appReady;
  if (!show && (detailedResultsLoading || detailedResultSheetLoading)) {
    const busy = document.getElementById("appStatus");
    if (busy && appReady) {
      busy.className = "status ok";
      busy.textContent = "Ready";
    }
    appCheckInFlight = false;
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
        appCheckInFlight = false;
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
  appCheckInFlight = false;
  return false;
}
function setAppControls(on) {
  document.querySelectorAll('[data-requires-app="1"]').forEach((b) => {
    const needsBuild = b.getAttribute("data-download") === "1";
    b.disabled = !on || (needsBuild && !lastBuildOk);
  });
  if (on) {
    const has = !!unsavedChangeCount();
    const sb = document.getElementById("saveChangesBtn");
    if (sb) sb.disabled = !has;
  }
}
async function api(path, opts = {}) {
  if (!appReady) await checkAppStatus(false);
  if (!appReady)
    throw new Error(
      "Application is not available. Start with tools/launchers/start_ui.bat or python tools/launchers/START_UI.py.",
    );
  opts = Object.assign({}, opts || {});
  window.__retirementCsrfToken = csrfToken || "";
  window.__retirementApiBase = apiBase || "";
  if (window.RetirementApiClient) {
    window.RetirementApiClient.setBase(apiBase || "");
    return await window.RetirementApiClient.request(path, opts);
  }
  const timeoutMs = Number(opts.timeoutMs) || 0;
  delete opts.timeoutMs;
  opts.headers = Object.assign(
    { "Content-Type": "application/json" },
    opts.headers || {},
  );
  if (csrfToken && String(opts.method || "GET").toUpperCase() !== "GET")
    opts.headers["X-CSRF-Token"] = csrfToken;
  let timer = null;
  if (timeoutMs > 0) {
    const controller = new AbortController();
    opts.signal = controller.signal;
    timer = setTimeout(() => controller.abort(), timeoutMs);
  }
  try {
    const res = await fetch(apiUrl(path), opts);
    const text = await res.text();
    let data;
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
    if (!res.ok)
      throw new Error((data && data.error) || text || res.statusText);
    return data;
  } catch (e) {
    if (e && e.name === "AbortError")
      throw new Error(
        `Request timed out after ${Math.round(timeoutMs / 1000)} seconds.`,
      );
    throw e;
  } finally {
    if (timer) clearTimeout(timer);
  }
}
async function seedHousingRows() {
  try {
    const resp = await api("/api/housing/seed", { method: "POST" });
    if (resp && resp.seeded !== undefined) {
      await loadAll({ source: planSource, preferLocal: false, silent: true });
      activeStep = "spending_mortgage_events";
      renderMain();
      showMessage(
        "Housing fields added (" +
          resp.seeded +
          " rows). Save Changes to persist.",
      );
    } else {
      showMessage("Housing seed returned unexpected response.", "warn");
    }
  } catch (e) {
    showMessage("Error seeding housing fields: " + e.message, "error");
  }
}

async function loadAll(opts = {}) {
  try {
    await checkAppStatus(false);
    runtime = await api("/api/runtime");
    const cfg = await api("/api/config/rows");
    rows = cfg.rows || [];
    moduleStatus = cfg.module_status || {};
    if (window.RetirementAppStore)
      window.RetirementAppStore.set({
        rows: rows,
        runtime: runtime,
        planLoaded: true,
        planSource: opts.source || "Local database",
      });
    resetAllocationPreview();
    await loadTravelExtras();
    await loadBudgetLines(false);
    await loadLiquidityBuffers();
    await loadForcedConversions();
    await loadEstateStateOptions();
    await loadYtdStatus();
    const h = await fetch(apiUrl("/api/holdings"));
    holdingsText = await h.text();
    holdingRowsCache = null;
    currentHoldingAccount = "ALL";
    try {
      const lr = await fetch(apiUrl("/api/liabilities"));
      liabilitiesText = await lr.text();
    } catch (_e) {
      liabilitiesText = "";
    }
    liabilityRowsCache = null;
    liabilitiesChanged = false;
    dirty.clear();
    if (window.RetirementAppStore) window.RetirementAppStore.resetPlanFlags();
    holdingsChanged = false;
    travelExtrasChanged = false;
    liquidityChanged = false;
    forcedConversionsChanged = false;
    ytdTransactionsChanged = false;
    ytdAccountsChanged = false;
    budgetLinesChanged = false;
    planLoaded = true;
    planSource = opts.source || "Local database";
    if (!sessionBaselineCaptured) {
      fetchCurrentSummaryKpi()
        .then((k) => {
          sessionBaselineSummary = k;
          sessionBaselineCaptured = true;
        })
        .catch(() => {});
    }
    if (!opts.silent) showMessage("Local database loaded.");
    renderMain();
    refreshBuildStatus().catch(() => {});
  } catch (e) {
    showMessage("Error loading local database: " + e.message, "error");
    renderMain();
  }
}
async function startNewPlan() {
  if (hasUnsavedPlanChanges()) {
    if (
      !(await showInAppConfirm(
        "You have unsaved changes. Start a new plan anyway? All unsaved changes will be lost.",
        {
          title: "Start New Plan",
          confirmLabel: "Discard & Start New",
          cancelLabel: "Keep Editing",
          variant: "warn",
        },
      ))
    )
      return;
  }
  let ytdBlendChoice = null;
  try {
    const status = await api("/api/ytd/status");
    const summary = (status && status.summary) || {};
    const actual = summary.actual || {};
    if (
      summary.enabled &&
      (Number(actual.spending || 0) > 0 ||
        Number(actual.earned_income || 0) > 0)
    ) {
      const choice = await showYtdBlendChoiceModal(summary);
      if (choice === null) return;
      ytdBlendChoice = choice === "blend";
    }
  } catch (e) {
    /* YTD status unavailable — proceed with default blend-on behavior */
  }
  try {
    planFolderHandle = null;
    planFolderName = "";
    await api("/api/plan-data/blank", {
      method: "POST",
      body: JSON.stringify(
        ytdBlendChoice === null ? {} : { ytd_blend_enabled: ytdBlendChoice },
      ),
    });
    sessionChanges.clear();
    sessionSpecialChanges.clear();
    dirty.clear();
    holdingsChanged = false;
    liabilitiesChanged = false;
    travelExtrasChanged = false;
    liquidityChanged = false;
    forcedConversionsChanged = false;
    ytdTransactionsChanged = false;
    ytdAccountsChanged = false;
    taxonomyData = null;
    taxonomyFlat = {};
    taxonomyError = "";
    spendingModelData = null;
    spendingModelError = "";
    mappingRules = null;
    rulesChanged = false;
    taxBudget = {};
    taxBudgetChanged = false;
    taxBudgetLoaded = false;
    budgetLines = [];
    budgetLinesChanged = false;
    budgetLinesLoaded = false;
    budgetSectionMode = {};
    categoryBudgetMode = {};
    groupBudgetMode = {};
    ytdData = null;
    sessionBaselineSummary = null;
    sessionBaselineCaptured = false;
    await loadAll({
      source: "New blank plan",
      preferLocal: false,
      silent: true,
    });
    activeStep = "household_people";
    lastBuildOk = false;
    planChatMessages = [];
    showMessage(
      "New blank plan started in the local database. User data is blank; option defaults are retained." +
        (ytdBlendChoice === false
          ? " This plan is modeled as fully hypothetical — real YTD actuals are excluded from the current-year projection."
          : ""),
    );
    renderMain();
    window.scrollTo({ top: 0 });
  } catch (e) {
    showMessage("Error starting new plan: " + e.message, "error");
  }
}
function normalizeValueForSave(row, value) {
  return saveValueForRow(row, value);
}
function updates() {
  return [...dirty.entries()].map(([row_index, value]) => {
    const row = rows.find((r) => r.row_index === row_index);
    return { row_index, value: normalizeValueForSave(row, value) };
  });
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
async function saveHoldings() {
  if (!holdingsChanged) return { updated: 0 };
  const content = serializeHoldings();
  const res = await fetch(apiUrl("/api/holdings"), {
    method: "POST",
    headers: { "Content-Type": "text/csv" },
    body: content,
  });
  if (!res.ok) throw new Error(await res.text());
  holdingsText = content;
  holdingsChanged = false;
  return { updated: 1 };
}
async function syncBackends() {
  return await api("/api/config/sync", {
    method: "POST",
    body: JSON.stringify({}),
  });
}
async function fetchText(path) {
  if (window.RetirementApiClient) {
    window.RetirementApiClient.setBase(apiBase || "");
    return await window.RetirementApiClient.text(path);
  }
  const res = await fetch(apiUrl(path), { cache: "no-store" });
  if (!res.ok) throw new Error(await res.text());
  return await res.text();
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
async function writeFileHandle(handle, content) {
  const writable = await handle.createWritable();
  await writable.write(content);
  await writable.close();
}
async function fetchPlanDataFiles(opts = {}) {
  const out = {};
  const mergeProtected = opts.mergeProtectedClientData !== false;
  for (const name of PLAN_DATA_FILES) {
    try {
      out[name] = await fetchText("/api/plan-data/" + encodeURIComponent(name));
    } catch (e) {
      if (name.startsWith("ytd_")) {
        out[name] = "";
        continue;
      }
      throw e;
    }
    if (mergeProtected && planFolderHandle && name.startsWith("client_")) {
      try {
        const localText = await readFileFromFolder(planFolderHandle, name);
        out[name] = mergeProtectedClientData(out[name], localText);
      } catch (_e) {}
    }
  }
  return out;
}
async function ensurePlanFolderPermission(dirHandle, mode = "readwrite") {
  if (!dirHandle || !dirHandle.queryPermission) return true;
  let perm = await dirHandle.queryPermission({ mode });
  if (perm === "granted") return true;
  perm = await dirHandle.requestPermission({ mode });
  return perm === "granted";
}
async function readPlanDataFolderContents(dirHandle, requireRequired = true) {
  if (!dirHandle) throw new Error("No CSV adapter folder selected.");
  const contents = {};
  for (const name of PLAN_DATA_FILES) {
    try {
      contents[name] = await readFileFromFolder(dirHandle, name);
    } catch (e) {
      if (requireRequired && REQUIRED_PLAN_DATA_FILES.includes(name))
        throw new Error(
          "The selected folder does not contain a complete Plan Data CSV set.",
        );
    }
  }
  return contents;
}

function hasUnsavedPlanChanges() {
  return !!(
    dirty.size ||
    holdingsChanged ||
    liabilitiesChanged ||
    travelExtrasChanged ||
    liquidityChanged ||
    forcedConversionsChanged ||
    ytdTransactionsChanged ||
    ytdAccountsChanged ||
    rulesChanged ||
    taxBudgetChanged ||
    budgetLinesChanged
  );
}
function normalizePlanDataTextForCompare(v) {
  return String(v ?? "")
    .replace(/\r\n/g, "\n")
    .replace(/\r/g, "\n")
    .trimEnd();
}
async function selectedFolderDiffersFromLoadedPlan() {
  if (!planFolderHandle) return false;
  const local = await readPlanDataFolderContents(planFolderHandle, false);
  const saved = await fetchPlanDataFiles({ mergeProtectedClientData: false });
  return PLAN_DATA_FILES.some(
    (name) =>
      normalizePlanDataTextForCompare(local[name] || "") !==
      normalizePlanDataTextForCompare(saved[name] || ""),
  );
}
async function saveCurrentPlanToSelectedFolderForBuild() {
  if (!planFolderHandle) return false;
  const planFiles = await fetchPlanDataFiles();
  await savePlanDataToCurrentFolder(planFiles);
  return true;
}

async function listFolderFileNames(dirHandle) {
  const names = [];
  if (!dirHandle || !dirHandle.values) return names;
  try {
    for await (const entry of dirHandle.values()) {
      if (entry.kind === "file") names.push(entry.name);
    }
  } catch (_e) {}
  return names.sort((a, b) => a.localeCompare(b));
}
function showPlanDataFileManifest(title, names) {
  showMessage(title || "CSV adapter folder selected.");
  activeStep = planLoaded ? "review" : "start";
  renderMain();
}
async function pushPlanDataContents(contents) {
  if (!contents["client_data.csv"] || !contents["client_holdings.csv"])
    throw new Error(
      "The selected folder does not contain a complete Plan Data CSV set.",
    );
  for (const name of PLAN_DATA_FILES) {
    if (Object.prototype.hasOwnProperty.call(contents, name))
      await postPlanDataFile(name, contents[name]);
  }
  await syncBackends();
  return true;
}
async function refreshFromPlanFolder(opts = {}) {
  if (!planFolderHandle) return false;
  const ok = await ensurePlanFolderPermission(planFolderHandle, "readwrite");
  if (!ok)
    throw new Error(
      "Permission to read the selected CSV adapter folder was not granted.",
    );
  const contents = await readPlanDataFolderContents(
    planFolderHandle,
    opts.requireRequired !== false,
  );
  await pushPlanDataContents(contents);
  lastBuildOk = false;
  if (!opts.silent) showMessage("CSV set imported from the selected folder.");
  return true;
}
function versionPrefixSuggestion() {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `v${y}${m}${day}_${hh}${mm}_`;
}
async function writePlanDataFilesToFolder(dir, files, prefix = "") {
  for (const name of PLAN_DATA_FILES) {
    const h = await dir.getFileHandle(prefix + name, { create: true });
    await writeFileHandle(h, files[name] || "");
  }
}
function openPathPrompt(opts = {}) {
  return new Promise((resolve) => {
    const modal = document.getElementById("pathModal");
    const title = document.getElementById("pathModalTitle");
    const help = document.getElementById("pathModalHelp");
    const input = document.getElementById("pathModalInput");
    const note = document.getElementById("pathModalNote");
    const browse = document.getElementById("pathModalBrowseBtn");
    const cancel = document.getElementById("pathModalCancelBtn");
    const primary = document.getElementById("pathModalPrimaryBtn");
    title.textContent = opts.title || "Plan Data Folder";
    help.textContent = opts.help || "Enter or browse to a CSV adapter folder.";
    input.value = opts.defaultPath || "";
    note.textContent =
      opts.note ||
      "Path save/load is available in local mode. Browse uses your browser folder picker when supported.";
    browse.style.display = opts.allowBrowse === false ? "none" : "";
    primary.textContent = opts.primaryText || "Continue";
    function close(result) {
      modal.style.display = "none";
      browse.onclick = cancel.onclick = primary.onclick = null;
      resolve(result);
    }
    browse.onclick = async () => {
      if (window.showDirectoryPicker) {
        try {
          const pickerOpts = {
            id: opts.pickerId || "retirement-plan-data",
            mode: "readwrite",
          };
          if (planFolderHandle) pickerOpts.startIn = planFolderHandle;
          const dir = await window.showDirectoryPicker(pickerOpts);
          close({ action: "browse", dir });
          return;
        } catch (e) {
          if (e && e.name === "AbortError") return;
          showMessage("Folder browse error: " + e.message, "error");
          return;
        }
      }
      document.getElementById("planImport").click();
      close({ action: "file_input" });
    };
    cancel.onclick = () => close({ action: "cancel" });
    primary.onclick = () => close({ action: "path", path: input.value.trim() });
    modal.style.display = "flex";
    setTimeout(() => {
      input.focus();
      input.select();
    }, 0);
  });
}
async function savePlanDataToPath(pathText, files) {
  const out = await api("/api/plan-data/save-to-path", {
    method: "POST",
    body: JSON.stringify({ path: pathText, files }),
  });
  if (!out || out.success === false)
    throw new Error(
      out && out.error
        ? out.error
        : "Failed to save Plan Data to the selected path.",
    );
  planFolderHandle = null;
  planFolderName = "";
  showMessage("Changes saved to " + out.path);
  return true;
}
async function savePlanDataToFolder(files) {
  const def = await defaultPlanDataPath();
  const choice = await openPathPrompt({
    title: "Save Changes Folder",
    help: "Review or edit the folder path where Plan Data should be saved.",
    defaultPath: def,
    primaryText: "Save to path",
    pickerId: "retirement-plan-data-save",
  });
  if (!choice || choice.action === "cancel") return false;
  if (choice.action === "path") {
    const path = String(choice.path || "").trim();
    if (!path) return false;
    return await savePlanDataToPath(path, files);
  }
  if (choice.action === "browse" && choice.dir) {
    const dir = choice.dir;
    await writePlanDataFilesToFolder(dir, files, "");
    planFolderHandle = dir;
    planFolderName = dir.name || "CSV adapter folder";
    showPlanDataFileManifest(
      "Changes saved to selected folder",
      await listFolderFileNames(dir),
    );
    return true;
  }
  if (!window.showDirectoryPicker) {
    for (const name of PLAN_DATA_FILES) downloadBlob(name, files[name] || "");
    return true;
  }
  return false;
}
async function promptSavePlanDataFiles(files) {
  return await savePlanDataToFolder(files);
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
async function saveWorkingCopy() {
  if (!planLoaded) {
    showMessage("Start or open the local plan before saving.", "error");
    return false;
  }
  if (!validateAllocationTargetsOrMessage()) return false;
  await saveChanges(false);
  await saveTravelExtras(false);
  await saveLiquidityBuffers(false);
  await saveForcedConversions(false);
  await saveYtdPending();
  if (rulesChanged) await saveMappingRulesData();
  if (taxBudgetChanged) await saveTaxonomyBudgetData();
  if (budgetLinesChanged) await saveBudgetLines();
  await saveHoldings();
  await saveLiabilities();
  await syncBackends();
  updateUnsaved();
  return true;
}
async function saveAll(sync = true) {
  try {
    if (!planLoaded) {
      showMessage("Start or open a plan before saving.", "error");
      return false;
    }
    const saved = await saveWorkingCopy();
    if (!saved) return false;
    showMessage("Changes saved.");
    await loadAll({
      source: "Local database",
      preferLocal: false,
      silent: true,
    });
    maybeRunLocalBackup("save");
    return true;
  } catch (e) {
    showMessage("Error saving: " + e.message, "error");
    return false;
  }
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
async function runBuild(queue = false, opts = {}) {
  const fromDownload = !!(opts && opts.fromDownload);
  const stepBeforeBuild = activeStep;
  try {
    if (!validateAllocationTargetsOrMessage()) return false;
    setBuildOverlay(
      true,
      "Preparing build",
      "Capturing the current workbook baseline...",
      0,
    );
    const before = await captureBuildBaseline();
    const hadUnsaved = hasUnsavedPlanChanges();
    const buildChanges = capturedSessionChanges().map((c) =>
      Object.assign({}, c),
    );
    updateBuildOverlay(
      "Saving current plan",
      "Saving the on-screen inputs to the local database before building outputs.",
      6,
    );
    const saved = await saveWorkingCopy();
    if (!saved) {
      showMessage(
        "Could not save the plan before building. Check disk space and try again.",
        "error",
      );
      hideBuildOverlay();
      return false;
    }
    updateBuildOverlay(
      "Checking build preflight",
      "Reviewing saved Plan Data, report freshness, pricing diagnostics, and validation warnings.",
      10,
    );
    buildPreflight = await api("/api/build/preflight");
    updatePlanStateBanner();
    const blockers = (buildPreflight && buildPreflight.blockers) || [];
    const warnings = (buildPreflight && buildPreflight.warnings) || [];
    if (blockers.length) {
      hideBuildOverlay();
      showMessage("Build preflight blocked: " + blockers[0], "error", {
        persistent: true,
      });
      if (activeStep !== "review") {
        activeStep = "review";
        renderMain();
      }
      return false;
    }
    if (warnings.length && !fromDownload && !opts.skipPreflightConfirm) {
      hideBuildOverlay();
      const warnHtml =
        "<p>Build preflight found <b>" +
        warnings.length +
        " warning" +
        (warnings.length === 1 ? "" : "s") +
        '</b>:</p><ul class="inapp-modal-list">' +
        warnings
          .slice(0, 5)
          .map((w) => "<li>" + esc(w) + "</li>")
          .join("") +
        "</ul><p>Continue building anyway?</p>";
      const proceed = await showInAppConfirm(warnHtml, {
        title: "Preflight Warnings",
        confirmLabel: "Continue Build",
        cancelLabel: "Review Preflight",
        variant: "warn",
        bodyIsHtml: true,
      });
      if (!proceed) {
        if (activeStep !== "review") {
          activeStep = "review";
          renderMain();
        }
        return false;
      }
      setBuildOverlay(
        true,
        "Starting build",
        "Continuing after preflight warning review.",
        12,
      );
    }
    let folderWarning = "";
    if (planFolderHandle) {
      folderWarning =
        "CSV folder import/export is available in System Configuration, but this build used the saved local database snapshot as the source of truth.";
    }
    let buildBody = {
      queue,
      ui_saved_working_copy: true,
      build_input_source: "sqlite_snapshot",
    };
    lastBuildOk = false;
    setAppControls(appReady);
    showMessage("Building outputs...");
    updateBuildOverlay(
      "Starting build",
      "Launching generated workbook, PDF, and report outputs from the saved database snapshot.",
      0,
    );
    const out = await buildWithProgress(buildBody);
    if (out && out.success !== false) {
      detailedResultsData = null;
      detailedResultSheets = {};
      detailedResultsError = "";
      detailedResultSheetError = "";
      activeDetailedSheet = "";
      updateBuildOverlay(
        "Preparing Build Impact",
        "Comparing changes, terminal net worth, after-tax net worth, lifetime taxes, Monte Carlo success probability, and Roth conversions.",
        96,
      );
      lastBuildOk = true;
      lastBuildSummary = summaryFromApiPayload(out);
      if (!kpiHasValues(lastBuildSummary)) lastBuildSummary = out.kpi || {};
      const postBuildStatus = await refreshBuildStatus();
      rememberBuildCompare({
        before: kpiHasValues(before) ? before : {},
        after: lastBuildSummary,
        changes: buildChanges,
        admin_changes: out.admin_changes || [],
        qc: out.qc_result || lastBuildSummary.qc_result || "Complete",
        elapsed: out.elapsed_seconds ? `Built in ${out.elapsed_seconds}s` : "",
        provenance: buildHistoryProvenance(postBuildStatus || buildPreflight),
      });
      sessionBaselineSummary = cloneSummary(lastBuildSummary);
      sessionBaselineCaptured = true;
      sessionChanges.clear();
      sessionSpecialChanges.clear();
      updateBuildOverlay(
        "Build complete",
        fromDownload ? "Build complete." : "Opening the Build Impact page.",
        100,
        "done",
      );
      if (fromDownload) {
        setTimeout(hideBuildOverlay, 400);
        showMessage("Build successful.");
        renderMain();
      } else {
        renderBuildImpactAfterBuild("Build successful. Build impact is ready.");
      }
      maybeRunLocalBackup("build");
      if (folderWarning)
        setTimeout(() => showMessage(folderWarning, "warn"), 250);
    } else throw new Error(JSON.stringify(out));
  } catch (e) {
    stopBuildProgressTicker();
    lastBuildOk = false;
    setAppControls(appReady);
    updateBuildOverlay(
      "Build failed",
      "The build stopped before the Build Impact page could be displayed.",
      100,
      "error",
    );
    setTimeout(hideBuildOverlay, 700);
    showMessage("Error building: " + e.message, "error");
  }
  return lastBuildOk;
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
async function downloadWithBuild(url, label) {
  try {
    if (lastBuildOk && !unsavedChangeCount()) {
      downloadFile(url);
      return;
    }
    const ok = await runBuild(false, { fromDownload: true });
    if (ok) downloadFile(url);
  } catch (e) {
    showMessage("Error building for download: " + e.message, "error");
  }
}
function holdingsComplete() {
  return (
    (holdingsText || "")
      .split(/\r?\n/)
      .filter((x) => x.trim() && !x.toLowerCase().startsWith("account,"))
      .length > 0
  );
}
function findCsvByName(files, needle) {
  needle = String(needle || "").toLowerCase();
  return Array.from(files || []).find((f) => {
    const nm = String(f.name || "").toLowerCase();
    const rel = String(f.webkitRelativePath || "").toLowerCase();
    return nm === needle || rel.endsWith("/" + needle);
  });
}
async function readLocalCsvFile(files, label) {
  if (!files || !files.length) throw new Error("No Plan Data selected");
  const f = files[0];
  return await f.text();
}
async function postPlanDataFile(name, content) {
  try {
    await api("/api/plan-data/" + encodeURIComponent(name), {
      method: "POST",
      body: JSON.stringify({ csv_content: content }),
    });
  } catch (e) {
    let msg = String(e && e.message ? e.message : e);
    if (msg.toLowerCase().includes("<!doctype html>"))
      msg = "An internal error occurred while saving the file.";
    throw new Error("Could not import " + name + ": " + msg);
  }
}
async function importPlanDataContents(contents, sourceLabel) {
  if (!contents["client_data.csv"] || !contents["client_holdings.csv"])
    throw new Error(
      "The selected folder does not contain a complete Plan Data CSV set.",
    );
  await pushPlanDataContents(contents);
  lastBuildOk = false;
  planLoaded = true;
  planSource = sourceLabel || "Imported Plan Data CSV set";
  planFileNames.clientData = "client_data.csv";
  planFileNames.clientHoldings = "client_holdings.csv";
  await loadAll({ source: planSource, preferLocal: false, silent: true });
  return true;
}
async function readFileFromFolder(dirHandle, name) {
  const h = await dirHandle.getFileHandle(name);
  const f = await h.getFile();
  return await f.text();
}
async function handleImportPlanFolder(dirHandle) {
  const okPerm = await ensurePlanFolderPermission(dirHandle, "readwrite");
  if (!okPerm)
    throw new Error(
      "Permission to read the selected CSV adapter folder was not granted.",
    );
  const contents = await readPlanDataFolderContents(dirHandle, true);
  const ok = await importPlanDataContents(
    contents,
    "Imported Plan Data CSV set",
  );
  if (ok) {
    planFolderHandle = dirHandle;
    planFolderName = dirHandle.name || "CSV adapter folder";
    showPlanDataFileManifest(
      "CSV set imported from selected folder",
      await listFolderFileNames(dirHandle),
    );
  }
}
async function defaultPlanDataPath() {
  try {
    const out = await api("/api/config/backends");
    if (out && out.csv_path)
      return String(out.csv_path).replace(/[\\/][^\\/]*$/, "");
  } catch (_e) {}
  return "input";
}
async function selectPlanDataForImport() {
  try {
    const def = await defaultPlanDataPath();
    const choice = await openPathPrompt({
      title: "Import Plan Data CSV set",
      help: "Import a Plan Data CSV adapter folder into the local database.",
      defaultPath: def,
      primaryText: "Import path",
      pickerId: "retirement-plan-data",
    });
    if (!choice || choice.action === "cancel") return;
    if (choice.action === "path" && String(choice.path || "").trim()) {
      const out = await api("/api/plan-data/load-from-path", {
        method: "POST",
        body: JSON.stringify({ path: String(choice.path).trim() }),
      });
      if (!out || out.success === false)
        throw new Error(
          out && out.error ? out.error : "Failed to import CSV set.",
        );
      await loadAll({
        source: "Imported CSV set: " + choice.path,
        preferLocal: false,
        silent: true,
      });
      activeStep = "household_people";
      showMessage("CSV set imported from " + choice.path);
      return;
    }
    if (choice.action === "browse" && choice.dir) {
      await handleImportPlanFolder(choice.dir);
      return;
    }
  } catch (e) {
    if (e && e.name === "AbortError") return;
    showMessage("Error importing CSV set: " + e.message, "error");
  }
}
async function handleImportPlanFiles(files) {
  try {
    const contents = {};
    for (const name of PLAN_DATA_FILES) {
      const f = findCsvByName(files, name);
      if (f) contents[name] = await f.text();
    }
    await pushPlanDataContents(contents);
    lastBuildOk = false;
    planLoaded = true;
    await loadAll({
      source: "Imported Plan Data CSV set",
      preferLocal: false,
      silent: true,
    });
  } catch (e) {
    showMessage("Error importing Plan Data: " + e.message, "error");
  } finally {
    const inp = document.getElementById("planImport");
    if (inp) inp.value = "";
  }
}
function openSystemAdmin() {
  setStep("system_configuration");
}
function openExitModal() {
  document.getElementById("exitModal").style.display = "flex";
}
function closeExitModal() {
  document.getElementById("exitModal").style.display = "none";
}
async function shutdownAndClose() {
  appExiting = true;
  dirty.clear();
  holdingsChanged = false;
  travelExtrasChanged = false;
  liquidityChanged = false;
  forcedConversionsChanged = false;
  ytdTransactionsChanged = false;
  ytdAccountsChanged = false;
  updateUnsaved();
  try {
    if (appReady)
      await api("/api/shutdown", { method: "POST", body: JSON.stringify({}) });
  } catch (e) {}
  document.getElementById("mainPane").innerHTML =
    '<div class="pane-head"><h2>Safe to close</h2><p>You can close this window.</p></div>';
  setAppControls(false);
  try {
    window.close();
  } catch (e) {}
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
  holdingsChanged = false;
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

wireStepNavigation();
restoreWorkbookViewState();
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
});
setInterval(function () {
  checkAppStatus(false);
}, 15000);
