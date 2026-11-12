// ── Labels, acronyms and group names ──
// Extracted verbatim from dashboard_decomp_row_model.js (W4-06, ARC-005): acronym glossary, humanLabel /
// friendlyGroup and person-placeholder translation. Bare-global bridge below.
// Moved from dashboard.js: acronymDefinitionsHtml below is its only caller.
export function escapeRegExp(s) {
  return String(s).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// Moved from dashboard.js: formatAcronyms/acronymDefinitionsHtml/titleWord
// below are their only consumers, and dashboard.js's own bare
// ACRONYM_DEFINITIONS reference (loadCanonicalGlossary()'s Object.assign)
// still resolves fine via the window bridge at the bottom of this file --
// this module's <script> tag loads before dashboard.js's.
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
  se: "SE",
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
  ytd: "YTD",
};
export const ACRONYM_DEFINITIONS = {
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
  QSS: "Qualifying Surviving Spouse — the filing status available to a surviving spouse with a dependent for up to two years after the year of death, using MFJ tax brackets",
  CST: "Credit-Shelter Trust — an estate-planning trust that shelters up to the deceased spouse's federal exemption from estate tax at the survivor's later death",
  Sharpe: "Sharpe ratio — a measure of risk-adjusted return: how much extra return a portfolio earns per unit of volatility risk taken",
  tangency: "Tangency portfolio — the single asset mix that maximizes the Sharpe ratio, with no additional risk-limit constraint applied",
  Basis: "The original cost of an asset, used to figure capital gain or loss when it's sold",
  "Credit-Shelter Trust": "An estate-planning trust that shelters up to the deceased spouse's federal exemption from estate tax at the survivor's later death",
  ILIT: "Irrevocable Life Insurance Trust — keeps life insurance proceeds out of the taxable estate",
  "Joint-and-Survivor": "An annuity or pension feature (J&S) that pays a reduced benefit to a surviving spouse after the primary annuitant's death",
  "Percentile Band": "The value at or below which a given share of Monte Carlo simulation results fall",
  "SALT Cap": "The federal cap on deducting State And Local Taxes on itemized returns",
  "Sec. 121 Exclusion": "Up to $500,000 (MFJ) of home-sale gain excluded from federal income tax",
  "Sequence-of-Returns Risk": "The risk that poor investment returns early in retirement permanently impair a portfolio, even when average returns are fine over the full horizon",
  "Spousal Rollover": "A surviving spouse's option to inherit a deceased spouse's IRA as their own, deferring RMDs to their own age",
  "Standard Deduction": "The flat deduction amount (MFJ base plus over-65 add-ons) that reduces taxable income without itemizing",
  "Step-Up in Basis": "Reset of an asset's cost basis to fair market value at death for non-retirement assets, erasing built-in gain for the heir",
};

export function formatAcronyms(text) {
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

export function acronymDefinitionsHtml(parts) {
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

export function titleWord(w) {
  const low = w.toLowerCase();
  if (ACRONYMS[low]) return ACRONYMS[low];
  return low.charAt(0).toUpperCase() + low.slice(1);
}

export function humanLabel(label, row) {
  const _annuityDb = /^([hw])_(single|joint)$/i.exec(String(label || "").trim());
  if (_annuityDb)
    return `${personDisplayName(/^h$/i.test(_annuityDb[1]) ? 1 : 2)} ${titleWord(_annuityDb[2])}`;
  if (
    row &&
    row.section === "Account Policy" &&
    norm(row.label) === "reinvest_dividends"
  )
    return accountDisplayLabel(row.subsection);
  // Gross vs net (FUNCTIONAL_SPEC §6).
  if (row && row.section === "Income Streams" && norm(row.label) === "initial_guaranteed_income_payment")
    return "Monthly Payment (Gross)";
  if (row && row.section === "Income Streams" && norm(row.label) === "net_monthly_payment")
    return "Monthly Payment (Net, After Withholding)";
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
  if (row && row.section === "Housing" && norm(row.label) === "mortgage_rate_pct") return "Mortgage Rate";
  // Note Receivable installment-sale inputs (Form 8949 figures; src/note_installment_tax.py).
  const _p = /^(st|lt)_(proceeds|basis)$/.exec(row && row.section === "Note Receivable" ? norm(row.label) : "");
  if (_p) return `${_p[1] === "st" ? "Short" : "Long"}-term ${_p[2]} per payment (8949 Part ${_p[1] === "st" ? "I" : "II"})`;
  if (row && row.section === "Housing" && norm(row.label) === "down_payment")
    return "Down Payment";
  if (row && row.section === "Housing" && norm(row.label) === "bedrooms")
    return "Bedrooms";
  if (row && row.section === "Housing" && norm(row.label) === "bathrooms")
    return "Bathrooms";
  if (row && row.section === "Housing" && norm(row.label) === "property_type")
    return "Property Type";
  if (row && row.section === "Housing" && norm(row.label) === "sqft_band")
    return "Square Footage";
  if (row && row.section === "Housing" && norm(row.label) === "built_within_years")
    return "Built Within (Years)";
  if (
    row &&
    row.section === "Wellness" &&
    norm(row.label) === "medical_annual"
  )
    return "Annual Medical Out-of-Pocket";
  if (
    row &&
    row.section === "Wellness" &&
    norm(row.label) === "dental_annual"
  )
    return "Annual Dental Out-of-Pocket";
  if (
    row &&
    row.section === "Wellness" &&
    norm(row.label) === "vision_annual"
  )
    return "Annual Vision Out-of-Pocket";
  if (
    row &&
    row.section === "Wellness" &&
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
    row.section === "Wellness" &&
    row.subsection === "Pre-65 Bridge" &&
    norm(label) === "annual_premium_base_year"
  )
    return "Pre-65 Healthcare Premium";
  if (
    row &&
    row.section === "Wellness" &&
    row.subsection === "Medicare" &&
    norm(label) === "part_b_base_premium_monthly"
  )
    return "Monthly Medicare Part B";
  if (
    row &&
    row.section === "Wellness" &&
    row.subsection === "Medicare" &&
    norm(label) === "part_d_base_premium_monthly"
  )
    return "Monthly Medicare Part D";
  if (
    row &&
    row.section === "Wellness" &&
    row.subsection === "Medicare" &&
    norm(label) === "part_g_base_premium_monthly"
  )
    return "Monthly Medicare Part G";
  if (
    row &&
    row.section === "Wellness" &&
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

export function translatePersonPlaceholders(text) {
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

export function friendlyGroup(r) {
  if (
    r.section === "Account Policy" ||
    (r.section === "Economic Assumptions" &&
      norm(r.label) === "reinvest_dividends_default")
  )
    return "Dividend Reinvestment";
  // #239: moved here from Economic & Tax Assumptions' Retirement section.
  if (norm(r.label) === "rollover_401k_year") return "Retirement Contributions";
  if (
    r.section === "Other Assets" &&
    norm(r.subsection).startsWith("other_asset")
  )
    return "Other Asset Items";
  if (r.section === "Note Receivable" && norm(r.subsection) === "summary")
    return "Note Receivable";
  if (r.section === "HSA Policy") return "HSA";
  if (r.section === "DAF") return "Donor Advised Fund (DAF)";
  if (
    r.section === "Cashflow" &&
    norm(r.subsection) === "charitable_giving"
  )
    return "Qualified Charitable Distribution (QCD)";
  if (r.section === "Hybrid LTC" || r.section === "Insurance In Force")
    return "LTC/Life Policy";
  if (r.section === "Education Funding") return "529 Plans";
  if (
    (r.section === "Asset Class Assumptions" ||
      r.section === "Asset Allocation Policy") &&
    r.subsection
  )
    return translatePersonPlaceholders(
      formatAcronyms(humanizeGroupKey(stripUiLabelPrefix(r.subsection))),
    );
  if (r.section === "Asset Correlations") return "Pairwise Correlations";
  let s = r.subsection || r.section || "General";
  return translatePersonPlaceholders(
    formatAcronyms(humanizeGroupKey(stripUiLabelPrefix(s))),
  );
}
Object.assign(window, {
  acronymDefinitionsHtml, escapeRegExp, formatAcronyms, friendlyGroup,
  humanLabel, titleWord, translatePersonPlaceholders,
});
Object.defineProperty(window, "ACRONYMS", { get: () => ACRONYMS, configurable: true });
Object.defineProperty(window, "ACRONYM_DEFINITIONS", { get: () => ACRONYM_DEFINITIONS, configurable: true });
