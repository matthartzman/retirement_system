// ── Row-model + app-shell core (Wave 6.4 domain-module-split, shared-core extraction) ──
// Extracted from dashboard.js verbatim: the 172 functions every
// other domain page's render logic is built on top of (section/norm/valOf/
// isEditable/fieldHtml/rowsForStep/humanLabel/... plus app-shell orchestration
// like api/showMessage/setStep/loadAll/saveAll). Selected as the fan-in >= 3
// hub set from the internal call-graph analysis in
// docs/superpowers/plans/2026-08-06-dashboard-js-domain-module-split-SCOPE.md.
// renderMain and showStepHelp stay in dashboard.js: other leaf modules
// reassign them as a monkey-patch decorator chain, which this pass does not
// touch. A real ES module (type="module"), same export+window-bridge pattern
// as every other Wave 6.4 leaf. Named dashboard_decomp_*.js (not
// dashboard_row_model.js) so existing tests that glob that pattern for a
// multi-file "full dashboard source" read/smoke-exec pick it up automatically.

export function stepGatedByOptionalModule(stepId) {
  // HELOC isn't a client_optional_functions.csv toggle (module_catalog has no
  // entry for it) — it's a plan-data feature flag (HELOC/Setup/heloc_enabled),
  // so it and the bundle step that depends on it stay special-cased here.
  if (stepId === "heloc_strategy") return !helocModuleEnabled();
  // Special Strategies bundles the HELOC and Charitable Giving input pages, so
  // it only appears in navigation once at least one of those optional modules
  // is enabled. Visibility follows capability — there is no separate
  // "advanced workflow" preference.
  if (stepId === "special_strategies")
    return !helocModuleEnabled() && !optionalFunctionEnabled("charitable_giving");
  // §7.4: every other module-gated step is server-declared (module_catalog's
  // dashboard_step, via moduleGates.step_gates) rather than hand-listed here —
  // when the module is off, no computation runs and no sheet is built, so the
  // input page is hidden.
  const gateModule = (moduleGates.step_gates || {})[stepId];
  if (gateModule) return !optionalFunctionEnabled(gateModule);
  return false;
}

export function visibleSteps() {
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

export function saveWorkbookViewState() {
  try {
    localStorage.setItem("wbSheet", activeDetailedSheet || "");
    localStorage.setItem("wbGroups", JSON.stringify(detailedColumnGroupsOpen));
  } catch (_e) {}
}

export function apiUrl(p) {
  return (apiBase || "") + p;
}

export function showMessage(msg, kind = "info", opts) {
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
  if (r.section === "DAF") return "DAF";
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

export function fmtDelta(v) {
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

export function fmtPctDelta(v) {
  if (v === undefined || v === null || v === "") return "Not available";
  const n = Number(v);
  if (!Number.isFinite(n)) return "Not available";
  const sign = n > 0 ? "+" : "";
  return (
    sign + n.toLocaleString(undefined, { maximumFractionDigits: 1 }) + " pts"
  );
}

export function firstFinite(...vals) {
  for (const v of vals) {
    const n = finiteOrNull(v);
    if (Number.isFinite(n)) return n;
  }
  return NaN;
}

export function deriveAfterTaxTerminalNw(summary) {
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

export function currentKpi(summary) {
  summary = summary || {};
  const afterTax = deriveAfterTaxTerminalNw(summary);
  return {
    terminal_nw: firstFinite(
      summary.terminal_nw,
      summary.terminal_net_worth,
      // inheritable_nw is the key name pushBuildHistoryEntry/rememberBuildCompare
      // actually store terminal net worth under (see dashboard.js ~1852, ~1898) —
      // metricSummary() in planning_workbench_ui.js already checks this alias;
      // currentKpi() needs it too so build-history-sourced summaries resolve.
      summary.inheritable_nw,
    ),
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
    // #202: success_rate requires BOTH not running out of money AND keeping
    // the configured reserve floor -- success_rate_no_ruin drops the reserve
    // requirement so a change to the reserve setting doesn't get misread as
    // a change in the plan's actual resilience.
    mc_success_no_ruin: firstFinite(
      summary.mc_success_no_ruin,
      summary.success_rate_no_ruin,
    ),
    total_roth_conversions: deriveTotalRothConversions(summary),
    blended_return_info: firstFinite(summary.blended_return_info),
    // #293: the 3 Impact-page dial metrics, plus EFTR (Effective Future Tax
    // Rate) as a 4th supplemental stat -- already computed by
    // compute_future_lcv_and_eftr (its "from today, no upper bound" row set
    // already covers the current year through plan end).
    lcv: firstFinite(summary.lcv),
    npv_future_taxes: firstFinite(summary.npv_future_taxes),
    terminal_nw_mc_p5: firstFinite(summary.terminal_nw_mc_p5),
    eftr: firstFinite(summary.eftr),
  };
}

export function loadBuildHistory() {
  try {
    const raw = localStorage.getItem(BUILD_HISTORY_LS_KEY);
    buildHistory = raw ? JSON.parse(raw) : [];
  } catch (_e) {
    buildHistory = [];
  }
}

export function pushBuildHistoryEntry(entry) {
  loadBuildHistory();
  buildHistory.unshift(entry);
  if (buildHistory.length > BUILD_HISTORY_MAX)
    buildHistory = buildHistory.slice(0, BUILD_HISTORY_MAX);
  saveBuildHistory();
  lastBuildCompare = buildHistory[0];
}

export function buildHistoryProvenance(preflight) {
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

export function stepTitleById(id) {
  const s = STEPS.find((x) => x.id === id);
  return s ? s.title : String(id || "");
}

export function sourceStepForRow(row) {
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
  if (sec === "Wellness")
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

export function capturedSessionChanges() {
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

export function planningLeverBase() {
  // lastBuildCompare/lastBuildSummary are in-memory only and reset to null on
  // every fresh app launch; they only repopulate once a NEW build runs in the
  // current session. On a reload of an already-built saved plan they're both
  // empty, which used to fall through silently to the terminal:0/success:40
  // placeholders below even though real results exist. Fall back to the
  // persisted build history (same source Reports & Review > Impact and the
  // Planning Workbench use) before giving up to the hardcoded defaults.
  loadBuildHistory();
  const histEntry = (buildHistory && buildHistory[0]) || null;
  // buildHistory[*].kpi is a minimal 3-field cache (inheritable_nw,
  // lifetime_tax, mc_success) meant for lightweight badges; it has none of
  // the fields deriveAfterTaxTerminalNw()/PTI need, so a history-fallback
  // summary built from .kpi alone silently produces PTI: NaN (renders "--")
  // even though the full raw KPI snapshot was captured right alongside it in
  // .after. Prefer .after (falling back to .kpi only if a snapshot predates
  // that field being captured) so PTI/estate-tax figures actually resolve.
  const historyKpi = (histEntry && (histEntry.after || histEntry.kpi)) || {};
  const summary =
    (lastBuildCompare && lastBuildCompare.after) ||
    lastBuildSummary ||
    historyKpi;
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
  // currentKpi().mc_success is the raw backend fraction (0-1), same as every
  // other consumer of currentKpi() output -- buildImpactCardsHtml() multiplies
  // by 100 before display for exactly this reason. This call site skipped that
  // conversion, so a 99% success rate rendered as "1%" (fmtPct treats its
  // input as already on a 0-100 scale, it does not itself multiply by 100).
  const success = Number.isFinite(k.mc_success) ? k.mc_success * 100 : 40;
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

export function planningLeverRows() {
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
    "Work Income",
    "income_work",
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

export function analysisFrame(body, kind) {
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

export function planningWorkbenchContext() {
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

export function renderBuildImpactPage() {
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
  // #293: the three dials read LCV / NPV-of-future-taxes / 5th-percentile
  // worst-case ending wealth instead of raw terminal net worth / nominal
  // lifetime tax / Monte Carlo pass-fail probability. Object keys
  // (nwHeat/taxHeat/mcHeat) are unchanged so buildHistoryEntryHtml's
  // consumer code in dashboard_decomp_build_history.js needs no edits --
  // only which kpi field feeds each dial has changed.
  const allNw = buildHistory
    .map((e) => e.kpi && e.kpi.lcv)
    .filter((v) => v !== null && v !== undefined && Number.isFinite(Number(v)))
    .map(Number);
  const allTax = buildHistory
    .map((e) => e.kpi && e.kpi.npv_future_taxes)
    .filter((v) => v !== null && v !== undefined && Number.isFinite(Number(v)))
    .map(Number);
  const allMc = buildHistory
    .map((e) => e.kpi && e.kpi.terminal_nw_mc_p5)
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

export function isEditable(r) {
  return (
    r &&
    !r.is_header &&
    !r.is_comment &&
    r.label &&
    !rowIsRetiredScenarioHomeDuplicate(r)
  );
}

export function isRequired(r) {
  return String(r.schema?.required || "").toUpperCase() === "TRUE";
}

export function valOf(r) {
  return dirty.has(r.row_index) ? dirty.get(r.row_index) : r.value || "";
}

export function isMissing(r) {
  return isEditable(r) && isRequired(r) && String(valOf(r) || "").trim() === "";
}

export function norm(s) {
  return String(s || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_");
}

export function hasAny(s, terms) {
  s = norm(s);
  return terms.some((t) => s.includes(norm(t)));
}

export function section(r, s) {
  return r.section === s;
}

export function optionalFunctionEnabled(labelName) {
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

export function helocModuleEnabled() {
  return sectionFlagEnabled("HELOC", "Setup", "heloc_enabled");
}

export function ltcLifePolicyModuleEnabled() {
  return sectionFlagEnabled("Hybrid LTC", "Settings", "enabled");
}

export function homeValueLabelIsCanonical(label) {
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

export function rowIsCanonicalHomeValue(r) {
  return (
    String(r.section || "").trim() === "Other Assets" &&
    norm(r.subsection || "") === "home" &&
    homeValueLabelIsCanonical(r.label)
  );
}

export function rowIsRetiredScenarioHomeDuplicate(r) {
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

export function rowIsBaseHomeSaleInput(r) {
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

export function rowIsStressSellHomeInput(r) {
  return (
    String(r.section || "").trim() === "Scenarios" &&
    norm(r.subsection || "") === "sell_home" &&
    !rowIsRetiredScenarioHomeDuplicate(r)
  );
}

export function rowIsDivorceScenario(r) {
  return (
    r.section === "Scenarios" &&
    /^Demo_Divorce|^Divorce_/i.test(String(r.subsection || ""))
  );
}

export function rowIsMonteCarlo(r) {
  return (
    r.section === "Model Constants" && norm(r.subsection) === "monte_carlo"
  );
}

export function rawRowsForStep(id) {
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
              sub === "s_corp" ||
              sub === "retirement_contributions")) ||
          sec === "Payroll Tax" ||
          // #239: moved here from Economic & Tax Assumptions' Retirement
          // section (its own section is "Model Constants", not "Cashflow" --
          // grouped under "Retirement Contributions" via friendlyGroup
          // regardless of its actual "Retirement" subsection).
          lbl === "rollover_401k_year"
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
        return sec === "Estate Planning" || sec === "Account Titling";
      case "annuity_death_benefits":
        return sec === "Annuity Death Benefits" || sec === "Insurance In Force";
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
          ((sec === "Economic Assumptions" &&
            // #235: reinvest_dividends_default/cash_yield_rate moved to
            // Investment Holdings -- a per-holding-account behavior, not a
            // system-wide economic assumption.
            // #236: annuity_default_dividend_rate/annuity_default_additional_income_pct
            // moved to SS, Pensions & Annuities' "Plan-wide income stream settings".
            ![
              "reinvest_dividends_default",
              "cash_yield_rate",
              "annuity_default_dividend_rate",
              "annuity_default_additional_income_pct",
            ].includes(lbl)) ||
            sec === "Account Policy" ||
            // #238/#237: Payroll Tax / Medicare and / Self-Employment (FICA
            // rates) already live on Work Income (sec === "Payroll Tax" is
            // unconditional there) -- were also showing here, the same
            // editable fields in two places.
            (sec === "Payroll Tax" &&
              !["medicare", "self_employment"].includes(sub)) ||
            (sec === "Wellness" && !rowIsRetirementWellness(r)) ||
            (sec === "Model Constants" &&
              ["retirement", "capital_gains"].includes(sub) &&
              // #239: rollover_401k_year moved to Work Income; RMD start ages
              // moved to the Household & People table.
              ![
                "spending_freeze_year",
                "rollover_401k_year",
                "member_1_rmd_start_age",
                "member_2_rmd_start_age",
              ].includes(lbl)))
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
        return (
          sec === "DAF" ||
          (sec === "Cashflow" && sub === "charitable_giving")
        );
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

export function fieldNumericValue(row) {
  const raw = String(valOf(row) || "").replace(/[$,%\s,]/g, "");
  const n = Number(raw);
  return Number.isFinite(n) ? n : 0;
}

export function rowModuleGate(section) {
  return (moduleGates.section_gates || {})[section] || null;
}

export function rowBuildUsageState(row, stepId = "") {
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
        "Choose Match each dollar to when you’ll spend it, minimizing the chance of a loss after inflation as the allocation mode.",
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

export function rowsForStep(id, opts = {}) {
  const rs = rawRowsForStep(id);
  if (opts && opts.includeInactive) return rs;
  return rs.filter(
    (r) =>
      rowBuildUsageState(r, id).active || inactiveEditReveals.has(r.row_index),
  );
}

export function recAdd(list, level, title, body, row, stepId, impact, actionLabel) {
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

export function stepStats(id) {
  const rs = rowsForStep(id);
  const req = rs.filter(isRequired);
  const missing = req.filter(isMissing);
  const d = rs.filter((r) => dirty.has(r.row_index));
  if (id === "spending_travel_extras" && travelExtrasChanged) d.push({});
  if (id === "assets_home_cash" && liquidityChanged) d.push({});
  if (id === "roth_conversion" && forcedConversionsChanged) d.push({});
  if (id === "holdings" && window.holdingsChanged) d.push({});
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

export function overallStats() {
  const req = rows
    .filter(isEditable)
    .filter((r) => rowBuildUsageState(r, "all_assumptions").active)
    .filter(isRequired);
  const missing = req.filter(isMissing);
  return { total: req.length, missing, done: req.length - missing.length };
}

export function unsavedChangeCount() {
  return (
    dirty.size +
    (window.holdingsChanged ? 1 : 0) +
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

export function planStateArtifactsReady() {
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

export function planStateFresh() {
  return !!(
    buildPreflight &&
    buildPreflight.current &&
    !unsavedChangeCount() &&
    lastBuildOk
  );
}

export function updatePlanStateBanner() {
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

export async function refreshBuildStatus() {
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

export function updateUnsaved() {
  const u = document.getElementById("unsavedStatus");
  const has = !!unsavedChangeCount();
  u.classList.toggle("hidden", !has);
  lastBuildOk = lastBuildOk && !has;
  document.getElementById("planSource").textContent = planSource;
  const sb = document.getElementById("saveChangesBtn");
  if (sb) sb.disabled = !has;
  updatePlanStateBanner();
}

export function reportsUiContext() {
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

export function renderSteps() {
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
        // U1: landing on this tab keeps activeStep "reports_and_review", but
        // setDetailedResultSheet() (picking a specific sheet) flips activeStep
        // to "detailed_results" directly, bypassing setStep()'s redirect —
        // _isViewingDetailedResults() already covers both cases.
        if (_isViewingDetailedResults()) {
          html += renderDetailedResultsNav();
        }
      } else if (STRATEGY_TABS[s.id]) {
        html += renderWorkspaceSubtabsNav(s.id);
      }
    });
    html += `</div></details>`;
  });
  box.innerHTML = html;
  updateUnsaved();
}

export function toIsoDateValue(value) {
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

export function isDateField(r) {
  const l = norm(r.label);
  return (
    (l.includes("dob") || l.includes("date")) &&
    !l.includes("year") &&
    !l.includes("end_year")
  );
}

export function currencyRaw(value) {
  const n = numberFromDisplay(value);
  return n === null ? String(value ?? "").trim() : decimalTrim(String(n));
}

export function budgetMoneyInputValue(value) {
  if (value === undefined || value === null || String(value).trim() === "")
    return "";
  return currencyDisplay(value);
}

export function focusBudgetMoney(el) {
  if (el) el.value = currencyRaw(el.value);
}

export function blurBudgetMoney(el) {
  if (el) el.value = budgetMoneyInputValue(el.value);
  if (taxBudgetChanged) renderMain();
}

export function budgetMoneyNumber(value) {
  const n = numberFromDisplay(value);
  return n === null ? 0 : n;
}

export function valueKind(r) {
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
  if (["year", "integer", "int", "number", "numeric"].includes(type))
    return "number";
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
  return "plain";
}

export function choiceValue(o) {
  return typeof o === "object" ? String(o.value ?? o.label ?? "") : String(o);
}

export function storageValueForInput(row, value) {
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

export function displayValueForInput(row, value) {
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

export function beginEdit(idx, el) {
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

export function finishEdit(idx, el) {
  const row = rows.find((r) => r.row_index === idx);
  if (!row || !el) return;
  const stored = storageValueForInput(row, el.value);
  editValue(idx, stored, el);
  if (el.tagName && el.tagName.toLowerCase() === "input" && !isDateField(row)) {
    el.value = displayValueForInput(row, stored);
  }
}

export function fieldHtml(r) {
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
    control = `<select data-row="${r.row_index}" onchange="editValue(${r.row_index},this.value,this);renderMain()" onfocus="showFieldHelp(${r.row_index})"><option value="user_target" ${mode === "user_target" ? "selected" : ""}>Use user-specified allocation</option><option value="optimizer_recommendation" ${mode === "optimizer_recommendation" ? "selected" : ""}>Use allocation optimizer recommendation</option><option value="max_sharpe" ${mode === "max_sharpe" ? "selected" : ""}>Best risk-adjusted mix, staying within the risk limits you set (max-Sharpe)</option><option value="tangency" ${mode === "tangency" ? "selected" : ""}>Best risk-adjusted mix, ignoring your risk limits (tangency)</option><option value="real_loss_aware" ${mode === "real_loss_aware" ? "selected" : ""}>Match each dollar to when you’ll spend it, minimizing the chance of a loss after inflation</option></select>`;
  } else if (boolish) {
    const yes =
      String(value).toUpperCase() === "YES" ||
      String(value).toUpperCase() === "TRUE";
    control = `<label class="toggle-switch" data-row="${r.row_index}"><input type="checkbox" ${yes ? "checked" : ""} onchange="editValue(${r.row_index},this.checked?'YES':'NO',this)" onfocus="showFieldHelp(${r.row_index})"><span class="toggle-track" aria-hidden="true"></span><span class="toggle-text toggle-text-yes">YES</span><span class="toggle-text toggle-text-no">NO</span></label>`;
  } else if (type === "choice" || norm(units) === "choice" || window.STATE_INPUT_LABELS.has(lblNorm)) {
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
  const kind = valueKind(r);
  const negClass = kind === "currency" ? moneyNegativeClass(value) : "";
  // U2: currency, date, and dependency-linked (mode/policy/enabling) fields stay
  // full-width — pairing them beside an unrelated field raises mis-entry and
  // mislabeling risk for exactly the fields where getting it wrong matters most.
  const paired =
    kind !== "currency" && !isDateField(r) && dependencyRank(r.label) > "01";
  // Gating fields (mode/policy/enabled) keep the full row so the settings they
  // control read as subordinate to them. Everything else — including currency
  // and dates, which U2 previously pinned full-width — now flows into the
  // column grid, since the control is sized to its value and the label stays
  // inside the same bordered card.
  const sizeClass = fieldSizeClass(r);
  const flow = dependencyRank(r.label) > "01" && sizeClass !== "w-long";
  return `<div class="field ${missing ? "missing" : ""} ${dirtyHere ? "dirty" : ""} ${inactiveRevealed ? "inactive-edit" : ""}${paired ? " paired" : ""}${flow ? " flow" : ""}${sizeClass ? " " + sizeClass : ""}${negClass}" id="field-${r.row_index}" onclick="showFieldHelp(${r.row_index})"><div><div class="field-label">${esc(humanLabel(r.label, r))}${fieldLabelNoteHtml(r)}${fieldTooltipHtml(lblNorm, r)}</div><div class="field-meta">${req}${dirtyHere ? '<span class="badge dirty">Edited</span>' : ""}${inactiveBadge}</div></div><div>${control}${unit}${inactiveRevealed ? `<div class="unit">${esc(formatAcronyms(inactiveState.activation || "Change this value or its controlling setting to make it active in the build."))}</div>` : ""}</div></div>`;
}

export function sortRowsByDependency(rs) {
  return (rs || []).slice().sort((a, b) => {
    const ka = dependencyRank(a.label) + norm(a.label),
      kb = dependencyRank(b.label) + norm(b.label);
    return ka.localeCompare(kb);
  });
}

export function renderFieldGroups(rs) {
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

export function parsePercentInput(value) {
  const raw = String(value ?? "").trim();
  if (!raw) return 0;
  const hasPct = raw.includes("%");
  const cleaned = raw.replace(/[,%$\s]/g, "");
  const n = Number(cleaned);
  if (!Number.isFinite(n)) return 0;
  return hasPct ? n : Math.abs(n) > 1 ? n : n * 100;
}

export function findEditableRow(sectionName, subsectionName, labelName) {
  return rows
    .filter(isEditable)
    .find(
      (r) =>
        r.section === sectionName &&
        norm(r.subsection) === norm(subsectionName) &&
        norm(r.label) === norm(labelName),
    );
}

export function allocationModeRow() {
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

export function allocationSelectionMode() {
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

export function allocationTargetRows() {
  return rows
    .filter(isEditable)
    .filter(
      (r) =>
        r.section === "Asset Allocation Policy" &&
        norm(r.subsection) !== "global" &&
        norm(r.label) === "target_pct",
    );
}

export function optimizerOverrideRows() {
  return rows
    .filter(isEditable)
    .filter(
      (r) =>
        r.section === "Asset Class Optimizer Controls" &&
        norm(r.subsection) !== "global" &&
        norm(r.label) === "optimizer_override_pct",
    );
}

export function selectionActionRows() {
  return rows
    .filter(isEditable)
    .filter(
      (r) =>
        r.section === "Asset Class Optimizer Controls" &&
        norm(r.subsection) !== "global" &&
        norm(r.label) === "selection_action",
    );
}

export function assetCategory(asset) {
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

export function findTargetRow(assetClass) {
  const key = norm(assetClass);
  return allocationTargetRows().find((r) => norm(r.subsection) === key);
}

export function rowActionValue(row) {
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

export function requestAllocationPreview() {
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

export function allocationTargetTotalPct() {
  return allocationTargetRows().reduce((s, r) => {
    const a = selectionActionRows().find(
      (x) => norm(x.subsection) === norm(r.subsection),
    );
    return (
      s + (rowActionValue(a) === "exclude" ? 0 : parsePercentInput(valOf(r)))
    );
  }, 0);
}

export function optimizerOverrideTotalPct() {
  return optimizerOverrideRows().reduce(
    (s, r) => s + parsePercentInput(valOf(r)),
    0,
  );
}

export function optimizerOverrideHasEntries() {
  return optimizerOverrideRows().some(
    (r) => String(valOf(r) || "").trim() !== "",
  );
}

export function optimizerOverrideValid() {
  if (!optimizerOverrideHasEntries()) return true;
  return Math.abs(optimizerOverrideTotalPct() - 100) <= 0.01;
}

export function allocationTotalHtml() {
  const total = allocationTargetTotalPct();
  const ok = Math.abs(total - 100) <= 0.01;
  return `<div class="section-note" id="allocationTargetTotal"><b>User-specified allocation total:</b> ${total.toFixed(2)}% ${ok ? "✓" : "— must equal 100.00% before saving or building in user-specified mode."}</div>`;
}

export function renderAllocationPolicy() {
  const rs = allocationPolicyRows();
  if (!rs.length)
    return '<div class="holdings"><div class="field-list"><p>No optimizer input rows were found. Reload the current plan so optimizer inputs can be backfilled.</p></div></div>';
  return `<div class="holdings"><details><summary>Optimizer inputs</summary><div class="field-list">${rs.map(fieldHtml).join("")}</div></details></div>`;
}

export function renderFields(step) {
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

export function personDisplayName(n) {
  const nick = householdPersonRow(n, "nickname");
  const name = householdPersonRow(n, "name");
  const v =
    String(nick ? valOf(nick) : "").trim() ||
    String(name ? valOf(name) : "")
      .trim()
      .split(/\s+/)[0];
  return v || `Member ${n}`;
}

export function householdPersonRow(n, suffix) {
  return (
    rows.find(
      (r) =>
        isEditable(r) &&
        r.section === "Household" &&
        norm(r.label) === `member_${n}_${suffix}`,
    ) || null
  );
}

export function showInAppConfirm(message, opts) {
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

export function showSaveDiscardStayModal(message, opts) {
  opts = opts || {};
  return new Promise(function (resolve) {
    const overlay = document.createElement("div");
    overlay.className = "inapp-modal-overlay";
    const title = opts.title || "Unsaved Changes";
    const bodyHtml = opts.bodyIsHtml ? message : "<p>" + esc(message) + "</p>";
    overlay.innerHTML =
      '<div class="inapp-modal modal-warn"><b class="inapp-modal-title">' +
      esc(title) +
      '</b><div class="inapp-modal-body">' +
      bodyHtml +
      '</div><div class="inapp-modal-actions"><button class="btn sds-stay" type="button">Stay</button> <button class="btn warn sds-discard" type="button">Discard changes</button> <button class="btn primary sds-save" type="button">Save &amp; leave</button></div></div>';
    document.body.appendChild(overlay);
    function close(v) {
      overlay.remove();
      resolve(v);
    }
    overlay.querySelector(".sds-save").onclick = function () {
      close("save");
    };
    overlay.querySelector(".sds-discard").onclick = function () {
      close("discard");
    };
    overlay.querySelector(".sds-stay").onclick = function () {
      close("stay");
    };
    overlay.onclick = function (e) {
      if (e.target === overlay) close("stay");
    };
    function onKey(e) {
      if (e.key === "Escape") {
        close("stay");
        document.removeEventListener("keydown", onKey);
      }
    }
    document.addEventListener("keydown", onKey);
    setTimeout(function () {
      const b = overlay.querySelector(".sds-stay");
      if (b) b.focus();
    }, 30);
  });
}

export function showInAppPrompt(message, defaultValue, opts) {
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

export function noteReceivableRows() {
  return rows.filter(isEditable).filter((r) => r.section === "Note Receivable");
}

export function accountDisplayLabel(account) {
  const s = String(account || "");
  const m = /^member[ _]([12])[ _](.+)$/i.exec(s);
  if (!m) return s;
  return (
    personDisplayName(Number(m[1])) + "'s " + m[2].replace(/_/g, " ").trim()
  );
}

export function ensureLiabilityRows() {
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

export function markLiabilitiesDirty() {
  serializeLiabilities();
  liabilitiesChanged = true;
  lastBuildOk = false;
  updateUnsaved();
  setAppControls(appReady);
  scheduleStatusUpdate();
}

export function matrixRows(section) {
  const target = norm(section);
  return rows.filter(isEditable).filter((r) => norm(r.section) === target);
}

export function rowByNormLabel(label) {
  const key = norm(label);
  return (
    rawRowsForStep("roth_conversion").find((r) => norm(r.label) === key) ||
    rows.find((r) => isEditable(r) && norm(r.label) === key)
  );
}

export function scenarioRowsForManagement(rs) {
  const input = Array.isArray(rs) ? rs : rawRowsForStep("scenarios");
  return input.filter(
    (r) =>
      String(r.section || "").trim() === "Scenarios" &&
      !rowIsDivorceScenario(r) &&
      norm(r.subsection) !== "base",
  );
}

export function scenarioRowKey(row) {
  return scenarioRowKeyFromParts(
    row && row.section,
    row && row.subsection,
    row && row.label,
  );
}

export function scenarioFieldName(row) {
  return `${friendlyGroup(row)} · ${humanLabel(row.label, row)}`;
}

export function scenarioFindRow(subsection, label) {
  const wanted = scenarioRowKeyFromParts("Scenarios", subsection, label);
  return (
    scenarioRowsForManagement(rawRowsForStep("scenarios")).find(
      (r) => scenarioRowKey(r) === wanted,
    ) || null
  );
}

export function scenarioStoredSets() {
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

export function mcEngineModeValue() {
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

export function ytdRawMoney(v) {
  return String(v ?? "")
    .replace(/[$,]/g, "")
    .trim();
}

export function ytdTxnMoneyDisplay(v) {
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

export function ytdAmountIsNegative(v) {
  const n = Number(ytdRawMoney(v));
  return Number.isFinite(n) && n < 0;
}

export async function loadYtdStatus(silent = false) {
  // #201: loadAll() calls this as one sub-step among many -- it must not
  // clobber loadAll's own overlay message (e.g. "Saving changes") with
  // "Loading transactions" partway through an unrelated operation.
  if (!silent) showYtdLoadOverlay();
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
    if (!silent) hideYtdLoadOverlay();
  }
}

export function setYtdDirtyButtonStates() {
  const txBtn = document.getElementById("ytdSaveTransactionsBtn");
  if (txBtn) txBtn.disabled = !ytdTransactionsChanged;
  const acctBtn = document.getElementById("ytdSaveAccountSetupBtn");
  if (acctBtn) acctBtn.disabled = !ytdAccountsChanged;
}

export function markYtdTransactionsDirty() {
  ytdTransactionsChanged = true;
  lastBuildOk = false;
  updateUnsaved();
  setAppControls(appReady);
  setYtdDirtyButtonStates();
}

export function markYtdAccountsDirty() {
  ytdAccountsChanged = true;
  lastBuildOk = false;
  updateUnsaved();
  setAppControls(appReady);
  setYtdDirtyButtonStates();
}

export function updateYtdTxn(i, field, val) {
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

export function updateYtdAccount(i, field, val) {
  if (!ytdData.account_setup[i]) return;
  ytdData.account_setup[i][field] = val;
  if (field === "Role" && val === "Investment")
    ytdData.account_setup[i]["Current Value"] = "";
  markYtdAccountsDirty();
  if (field === "Role") renderMain();
}

export function ytdExistingValues(field) {
  return [
    ...new Set(
      (ytdData?.transactions || [])
        .map((r) => String(r[field] || "").trim())
        .filter(Boolean),
    ),
  ].sort((a, b) => a.localeCompare(b));
}

// The three transaction columns constrained to values already present
// somewhere in the transaction history.
const YTD_EXISTING_FIELDS = ["Merchant", "Category", "Account"];

export function ytdDatalistId(field) {
  return (
    "ytd-existing-" + String(field).toLowerCase().replace(/[^a-z0-9]+/g, "-")
  );
}

// One shared <datalist> per field, rendered once for the whole table.
//
// These columns used to inline a full <option> list into a per-row <select>,
// which is O(rows x distinct values): on a real plan that was 1,525 distinct
// merchants repeated on every visible row -- 825,635 <option> nodes and a
// ~62MB DOM for one page of the Transactions step. Sharing the lists makes it
// O(rows + distinct values), ~1.5k nodes, and gives type-ahead filtering
// instead of scrolling a 1,525-entry dropdown.
export function ytdExistingDatalistsHtml() {
  return YTD_EXISTING_FIELDS.map(
    (field) =>
      `<datalist id="${ytdDatalistId(field)}">${ytdExistingValues(field)
        .map((v) => `<option value="${esc(v)}"></option>`)
        .join("")}</datalist>`,
  ).join("");
}

// Cheap emptiness probe. ytdSelectFieldHtml runs once per row per field, so it
// must not rebuild (and sort) the whole distinct-value set the way the old
// per-row ytdExistingValues().length check did.
export function ytdHasExistingValues(field) {
  return (ytdData?.transactions || []).some((r) =>
    String(r[field] || "").trim(),
  );
}

// A <select> could only ever yield an existing value; a datalist-backed <input>
// also accepts free text, so enforce the same contract here -- anything typed
// that isn't already an existing value snaps back to the row's stored value.
// Matching is case-insensitive and commits the canonical casing, so picking
// from the list and typing the same text by hand land on the same value.
export function commitYtdExistingValue(i, field, el) {
  const row = ytdData?.transactions?.[i];
  const cur = row ? String(row[field] || "") : "";
  const typed = String(el.value || "").trim();
  const match = typed
    ? ytdExistingValues(field).find(
        (v) => v.toLowerCase() === typed.toLowerCase(),
      )
    : "";
  if (!match) {
    el.value = cur;
    return;
  }
  el.value = match;
  if (match !== cur) updateYtdTxn(i, field, match);
}

export function ytdSelectFieldHtml(i, field, value) {
  const has = ytdHasExistingValues(field);
  const disabled = has ? "" : " disabled";
  const placeholder = has ? `Select existing ${field}` : "No existing values";
  return `<input class="ytd-existing-select" list="${ytdDatalistId(field)}"${disabled} placeholder="${esc(placeholder)}" value="${esc(value || "")}" onchange="commitYtdExistingValue(${i},'${field}',this)">`;
}

export function ytdTransactionAccounts() {
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

export function renderYtdAccounts() {
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

export function _isViewingDetailedResults() {
  return (
    activeStep === "detailed_results" ||
    (activeStep === "reports_and_review" && reportsActiveTab === "Results")
  );
}

export async function loadDetailedResultSheet(name, force = false) {
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

export function _updateDetailGroupStatus(el) {
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

export async function refreshPreflightForReview() {
  try {
    buildPreflight = await api("/api/build/preflight");
    updatePlanStateBanner();
    renderMain();
    showMessage("Build preflight refreshed.");
  } catch (e) {
    showMessage("Preflight failed: " + e.message, "error");
  }
}

export async function loadTaxonomy(force) {
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

export async function loadSpendingModel(force) {
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

export function clearSpendingCaches() {
  spendingModelData = null;
  spendingModelError = "";
  taxonomyData = null;
  taxonomyFlat = {};
  taxonomyError = "";
  taxBudgetLoaded = false;
  budgetLinesLoaded = false;
}

export async function saveMappingRulesData() {
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

export async function loadBudgetLines(force) {
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

export async function loadTaxonomyBudget(force) {
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

export async function saveBudgetLines() {
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

export function markBudgetLinesDirty() {
  budgetLinesChanged = true;
  taxBudgetChanged = true;
  lastBuildOk = false;
  updateUnsaved();
  setAppControls(appReady);
  scheduleStatusUpdate();
}

export function catDetailLines(catId) {
  return (budgetLines || []).filter((l) => l.category_id === catId);
}

export function budgetAmount(value) {
  return budgetMoneyNumber(value);
}

export function catDetailSum(catId) {
  let s = 0;
  catDetailLines(catId).forEach((l) => {
    s += budgetAmount(l.amount_per_year) || 0;
  });
  return s;
}

export function hasExplicitBudget(key) {
  const b = taxBudget[key];
  return !!(
    b &&
    b.annual_budget !== undefined &&
    b.annual_budget !== null &&
    b.annual_budget !== ""
  );
}

export function groupCatSum(tt, grp) {
  const ids = groupCatIds(tt, grp);
  if (!ids.length) {
    const mg = groupModelData(tt, grp);
    return budgetAmount(mg && mg.budget);
  }
  return ids.reduce((s, id) => s + (catEffectiveBudget(id) || 0), 0);
}

export function groupKeyFor(tt, grp) {
  return "grp::" + tt + "::" + grp;
}

export function groupIsSummary(tt, grp) {
  return groupBudgetMode[tt + "::" + grp] === "summary";
}

export function syncCategoryTotal(catId) {
  if (!taxBudget[catId]) taxBudget[catId] = { annual_budget: 0, notes: "" };
  taxBudget[catId].annual_budget = Math.round(catDetailSum(catId));
  taxBudgetChanged = true;
  syncTaxonomyBudgetToBudgetLines();
}

export function updateCategoryDetail(lineId, field, val, catId) {
  const l = budgetLines.find((x) => x.line_id === lineId);
  if (l) l[field] = val;
  syncCategoryTotal(catId);
  markBudgetLinesDirty();
}

export function syncTaxonomyBudgetToBudgetLines() {
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

export async function saveTaxonomyBudgetData() {
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

export function updateTaxBudget(catId, field, val) {
  if (!taxBudget[catId]) taxBudget[catId] = { annual_budget: 0, notes: "" };
  taxBudget[catId][field] = val;
  taxBudgetChanged = true;
  syncTaxonomyBudgetToBudgetLines();
}

export function domainBudgetTitle(domain) {
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

export function renderDomainBudgetPage(domain, opts) {
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

export function setReportsTab(tab) {
  reportsActiveTab = REPORTS_TABS.includes(tab) ? tab : "Preflight";
  try {
    localStorage.setItem("reports_active_tab", reportsActiveTab);
  } catch (_e) {}
  renderMain();
}

export function goToReportsTab(tab) {
  activeStep = "reports_and_review";
  setReportsTab(tab);
}

export function strategyTabKey(step) {
  return "strategy_tab_" + step;
}

// Jump to a strategy workspace tab from the left nav. Persists the tab first,
// then routes through setStep so the plan-loaded navigation guard applies (the
// strategy workspace requires a loaded plan, unlike the plan-independent
// Reports workspace).
//
// Moved here from dashboard.js (ticket 290) to fit the size ratchet after
// its overlay-ordering fix -- setStep and loadYtdStatus are both real
// imports in this file already; showYtdLoadOverlay/hideYtdLoadOverlay,
// STRATEGY_TABS, and renderMain reach through the window bridge dashboard.js
// already exposes them on, same as every other cross-module onclick target.
export async function goToStrategyTab(step, tab) {
  const tabs = window.STRATEGY_TABS[step] || [];
  const next = tabs.includes(tab) ? tab : tabs[0] || "";
  try {
    localStorage.setItem(strategyTabKey(step), next);
  } catch (_e) {}
  const goingToYtd = step === "spending_core" && next === "Actual Spending (YTD)";
  // Ticket 290: setStep(step) below triggers a full synchronous renderMain()
  // of the spending workspace, which measured ~1.5s even before any YTD data
  // loads -- so EVERY tab into spending_core (not just YTD) pays this cost,
  // matching the reported "Spending Model is also slow with no progress bar"
  // symptom. Previously the overlay was shown only for the YTD tab, and only
  // AFTER this render (inside loadYtdStatus), so the render always ran behind
  // a locked, affordance-free screen. Show the overlay and yield one frame so
  // the browser actually paints it BEFORE the blocking render begins --
  // painting an overlay you never yield to is why it used to appear late.
  const isSpendingWorkspace = step === "spending_core";
  // Final-review finding (2026-08-19): showYtdLoadOverlay() sets the
  // no-cancel class, so a throw from setStep/loadYtdStatus/renderMain below
  // used to leave the user stranded behind an undismissable overlay --
  // exactly the locked-screen symptom this ticket exists to fix, just moved
  // to a new trigger (an exception instead of a slow render). The overlay
  // is guaranteed to hide on any exit path, not only the happy one.
  try {
    if (isSpendingWorkspace) {
      window.showYtdLoadOverlay();
      // Not requestAnimationFrame: browsers throttle or entirely suspend rAF
      // callbacks for a document that has lost visibility/compositing (tab
      // backgrounded, window minimized) -- exactly the case a user alt-tabbing
      // away during a slow load would hit, which would hang this await
      // indefinitely and leave the app looking permanently frozen. A
      // macrotask yield (setTimeout 0) still fires while backgrounded and
      // reliably lets the browser paint the overlay before the blocking
      // render below begins.
      await new Promise((r) => setTimeout(r, 0));
    }
    setStep(step);
    if (goingToYtd) {
      // silent=true: the overlay is already up from above; loadYtdStatus must
      // not show/hide its own second copy on top of it (that would leave the
      // depth-counted overlay stuck open after only one of the two hides).
      await loadYtdStatus(true);
      window.renderMain();
    }
  } finally {
    if (isSpendingWorkspace) window.hideYtdLoadOverlay();
  }
}

export function navigationContext() {
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
    saveWorkingCopy: saveWorkingCopy,
    saveAll: saveAll,
    confirmSaveDiscardStay: function (msg, opts) {
      return showSaveDiscardStayModal(msg, opts);
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

export function setStep(id) {
  return window.RetirementNavigation.setStep(navigationContext(), id);
}

export function scheduleStatusUpdate() {
  clearTimeout(statusTimer);
  statusTimer = setTimeout(() => {
    renderSteps();
    setAppControls(appReady);
  }, 120);
}

export function editValue(idx, val, el) {
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

export function fieldGuidance(row) {
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
  } else if (
    l.startsWith("h_qcd_") ||
    l.startsWith("w_qcd_") ||
    l === "h_qcd_annual_amount" ||
    l === "w_qcd_annual_amount"
  ) {
    // #219/#220: per-member QCD (Qualified Charitable Distribution) amount/
    // start/end fields all share the same underlying concept -- one shared
    // explanation instead of six near-duplicate FIELD_GUIDANCE_OVERRIDES entries.
    if (l.includes("start_year")) {
      purpose =
        "QCDs (Qualified Charitable Distributions) let an IRA owner age 70½+ send money straight from their IRA to charity, tax-free. This optional override sets the first plan year this member's QCD giving begins.";
      impact =
        "Leaving this blank starts QCD giving automatically the year this member turns 70½-eligible. Setting a later year delays when the tax-free giving (and any RMD credit it provides) begins.";
      consider =
        "Only fill this in if giving should start later than 70½-eligibility (e.g. charitable giving isn't planned until a later year); otherwise leave it blank.";
    } else if (l.includes("end_year")) {
      purpose =
        "QCDs (Qualified Charitable Distributions) let an IRA owner age 70½+ send money straight from their IRA to charity, tax-free. This optional override sets the last plan year this member's QCD giving applies.";
      impact =
        "Leaving this blank continues QCD giving through the end of the plan. Setting an earlier year stops the tax-free giving (and its RMD credit) after that year, reverting to normal taxable withdrawals for any remaining RMD.";
      consider =
        "Only fill this in if QCD giving should stop before the plan ends (e.g. a giving plan with a defined end date); otherwise leave it blank.";
    } else {
      purpose =
        "QCDs (Qualified Charitable Distributions) let an IRA owner age 70½+ send money straight from their own IRA to charity, excluded from taxable income entirely. This is the annual dollar amount this member gives this way, capped at that year's own RMD and the statutory per-person QCD limit.";
      impact =
        "This amount is excluded from Adjusted Gross Income and can count toward satisfying this member's own Required Minimum Distribution for the year — typically lowering taxable income, Medicare IRMAA exposure, and NIIT exposure more than an equivalent itemized charitable deduction would.";
      consider =
        "Set this to the amount this member actually plans to give from IRA assets each year once 70½-eligible; leave at $0 if this member's charitable giving isn't coming from IRA assets.";
    }
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
    // #219: layman-quality example the user provided verbatim (lightly
    // split across purpose/impact/consider) -- the standard to match for
    // every non-intuitive field, not just this one.
    purpose =
      "It's an opt-in setting (off by default) that changes how the tool's asset-allocation recommendation is built — but only for the \"optimizer recommendation\" and \"max Sharpe\" modes; it does nothing if you're using a manually-set target allocation. The idea it's based on: there's a well-known chart showing that whether cash or stocks are \"safer\" depends on how long you're holding. Cash is safe if you need the money next year, but risky if you sit on it for 20 years (inflation quietly eats it). Stocks are the opposite — risky short-term, but historically the safer bet over long stretches once you account for inflation.";
    impact =
      "What flipping it on actually does: the tool already knows, from your own retirement projection, roughly when each dollar in your portfolio will actually get spent (it simulates your future withdrawals year by year). With this setting on, it uses that withdrawal timeline to sort your money into \"buckets\" by how soon it's needed — money needed in the next 0–2 years vs. money that won't be touched for 16+ years — and then nudges the recommended allocation: money you'll need soon gets nudged toward more cash (safety for near-term spending); money you won't touch for a long time gets nudged toward more stocks/growth investments (since historically it's the safer place for money over long horizons). It also shifts the bond portion toward shorter-duration bonds instead of long ones, since the underlying data shows long bonds don't buy you much extra safety. Guardrail: it only ever raises these amounts — it won't push you into less cash or less stock than your existing risk-tolerance settings already call for. A separate \"strength\" dial (0–100%) lets you turn the effect up or down without switching it off entirely.";
    consider =
      "Bottom line: it makes the recommended allocation a little more personalized to your actual spending schedule, rather than one generic risk-tolerance number applied to your whole portfolio. Selecting allocation_selection_mode=real_loss_aware enables the same withdrawal-schedule discovery automatically, so this toggle is mainly for nudging the existing optimizer/max-Sharpe modes rather than switching to that dedicated mode.";
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

export function ensureHelpPanelVisible() {
  document.body.classList.remove("help-collapsed");
}

export function showFieldHelp(idx) {
  const row = rows.find((r) => r.row_index === idx);
  if (!row) return;
  ensureHelpPanelVisible();
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

export function setAppControls(on) {
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

export async function api(path, opts = {}) {
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

export async function loadAll(opts = {}) {
  // #201: loadAll is reused for the initial load AND the post-save refresh
  // (saveAll calls it to re-sync from the DB) -- it always said "Loading
  // plan" even when the user had just clicked Save Changes. Let the caller
  // say what's actually happening.
  setBuildOverlay(
    true,
    opts.overlayTitle || "Loading plan",
    opts.overlayDetail || "",
    "waiting",
  );
  try {
    await checkAppStatus(false);
    runtime = await api("/api/runtime");
    try {
      const demoStatus = await api("/api/plan/demo-status");
      demoModeActive = !!(demoStatus && demoStatus.active);
    } catch (_e) {
      demoModeActive = false;
    }
    const cfg = await api("/api/config/rows");
    rows = cfg.rows || [];
    moduleStatus = cfg.module_status || {};
    moduleGates = cfg.module_gates || { step_gates: {}, section_gates: {} };
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
    await loadYtdStatus(true);
    const h = await fetch(apiUrl("/api/holdings"));
    window.holdingsText = await h.text();
    window.holdingRowsCache = null;
    window.currentHoldingAccount = "ALL";
    try {
      const lr = await fetch(apiUrl("/api/liabilities"));
      liabilitiesText = await lr.text();
    } catch (_e) {
      liabilitiesText = "";
    }
    liabilityRowsCache = null;
    liabilitiesChanged = false;
    try {
      const hr = await fetch(apiUrl("/api/hsa-schedule"));
      loadHsaScheduleFromCsv(await hr.text());
    } catch (_e) {
      loadHsaScheduleFromCsv("");
    }
    dirty.clear();
    if (window.RetirementAppStore) window.RetirementAppStore.resetPlanFlags();
    window.holdingsChanged = false;
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
  } finally {
    hideBuildOverlay();
  }
}

export function updates() {
  return [...dirty.entries()].map(([row_index, value]) => {
    const row = rows.find((r) => r.row_index === row_index);
    return { row_index, value: normalizeValueForSave(row, value) };
  });
}

export async function syncBackends() {
  return await api("/api/config/sync", {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export async function readPlanDataFolderContents(dirHandle, requireRequired = true) {
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

export function hasUnsavedPlanChanges() {
  return !!(
    dirty.size ||
    window.holdingsChanged ||
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

export async function saveWorkingCopy() {
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
  if (window.withdrawalAccountOrderIsDirty && window.withdrawalAccountOrderIsDirty() && window.saveWithdrawalAccountOrder)
    await window.saveWithdrawalAccountOrder();
  await saveHoldings();
  await saveLiabilities();
  await saveHsaSchedule();
  await syncBackends();
  updateUnsaved();
  return true;
}

export async function saveAll(sync = true) {
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
      overlayTitle: "Saving changes",
      overlayDetail: "Writing your edits to the local database and refreshing the on-screen plan.",
    });
    maybeRunLocalBackup("save");
    return true;
  } catch (e) {
    showMessage("Error saving: " + e.message, "error");
    return false;
  }
}

export async function runBuild(queue = false, opts = {}) {
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
      if (window.invalidateWorkbookFormatCache) window.invalidateWorkbookFormatCache();
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

export async function downloadWithBuild(url, label) {
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

export async function shutdownAndClose() {
  appExiting = true;
  dirty.clear();
  window.holdingsChanged = false;
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

Object.defineProperty(window, "ACRONYMS", { get: () => ACRONYMS, configurable: true });
Object.defineProperty(window, "ACRONYM_DEFINITIONS", { get: () => ACRONYM_DEFINITIONS, configurable: true });
Object.assign(window, {
  _isViewingDetailedResults,
  _updateDetailGroupStatus,
  accountDisplayLabel,
  acronymDefinitionsHtml,
  allocationModeRow,
  allocationSelectionMode,
  allocationTargetRows,
  allocationTargetTotalPct,
  allocationTotalHtml,
  analysisFrame,
  api,
  apiUrl,
  assetCategory,
  beginEdit,
  blurBudgetMoney,
  budgetAmount,
  budgetMoneyInputValue,
  budgetMoneyNumber,
  buildHistoryProvenance,
  capturedSessionChanges,
  catDetailLines,
  catDetailSum,
  choiceValue,
  clearSpendingCaches,
  commitYtdExistingValue,
  currencyRaw,
  currentKpi,
  deriveAfterTaxTerminalNw,
  displayValueForInput,
  domainBudgetTitle,
  downloadWithBuild,
  editValue,
  ensureHelpPanelVisible,
  ensureLiabilityRows,
  escapeRegExp,
  fieldGuidance,
  fieldHtml,
  fieldNumericValue,
  findEditableRow,
  findTargetRow,
  finishEdit,
  firstFinite,
  fmtDelta,
  fmtPctDelta,
  focusBudgetMoney,
  formatAcronyms,
  friendlyGroup,
  goToReportsTab,
  groupCatSum,
  groupIsSummary,
  groupKeyFor,
  hasAny,
  hasExplicitBudget,
  hasUnsavedPlanChanges,
  helocModuleEnabled,
  homeValueLabelIsCanonical,
  householdPersonRow,
  humanLabel,
  isDateField,
  isEditable,
  isMissing,
  isRequired,
  loadAll,
  loadBudgetLines,
  loadBuildHistory,
  loadDetailedResultSheet,
  loadSpendingModel,
  loadTaxonomy,
  loadTaxonomyBudget,
  loadYtdStatus,
  ltcLifePolicyModuleEnabled,
  markBudgetLinesDirty,
  markLiabilitiesDirty,
  markYtdAccountsDirty,
  markYtdTransactionsDirty,
  matrixRows,
  mcEngineModeValue,
  navigationContext,
  norm,
  noteReceivableRows,
  optimizerOverrideHasEntries,
  optimizerOverrideRows,
  optimizerOverrideTotalPct,
  optimizerOverrideValid,
  optionalFunctionEnabled,
  overallStats,
  parsePercentInput,
  personDisplayName,
  planStateArtifactsReady,
  planStateFresh,
  planningLeverBase,
  planningLeverRows,
  planningWorkbenchContext,
  pushBuildHistoryEntry,
  
  rawRowsForStep,
  readPlanDataFolderContents,
  recAdd,
  refreshBuildStatus,
  refreshPreflightForReview,
  renderAllocationPolicy,
  renderBuildImpactPage,
  renderDomainBudgetPage,
  renderFieldGroups,
  renderFields,
  renderSteps,
  renderYtdAccounts,
  reportsUiContext,
  requestAllocationPreview,
  rowActionValue,
  rowBuildUsageState,
  rowByNormLabel,
  rowIsBaseHomeSaleInput,
  rowIsCanonicalHomeValue,
  rowIsDivorceScenario,
  rowIsMonteCarlo,
  rowIsRetiredScenarioHomeDuplicate,
  rowIsStressSellHomeInput,
  rowModuleGate,
  rowsForStep,
  runBuild,
  saveAll,
  saveBudgetLines,
  saveMappingRulesData,
  saveTaxonomyBudgetData,
  saveWorkbookViewState,
  saveWorkingCopy,
  scenarioFieldName,
  scenarioFindRow,
  scenarioRowKey,
  scenarioRowsForManagement,
  scenarioStoredSets,
  scheduleStatusUpdate,
  section,
  selectionActionRows,
  setAppControls,
  setReportsTab,
  setStep,
  setYtdDirtyButtonStates,
  showFieldHelp,
  showInAppConfirm,
  showInAppPrompt,
  showMessage,
  showSaveDiscardStayModal,
  shutdownAndClose,
  sortRowsByDependency,
  sourceStepForRow,
  stepGatedByOptionalModule,
  stepStats,
  goToStrategyTab,
  stepTitleById,
  storageValueForInput,
  strategyTabKey,
  syncBackends,
  syncCategoryTotal,
  syncTaxonomyBudgetToBudgetLines,
  titleWord,
  toIsoDateValue,
  translatePersonPlaceholders,
  unsavedChangeCount,
  updateCategoryDetail,
  updatePlanStateBanner,
  updateTaxBudget,
  updateUnsaved,
  updateYtdAccount,
  updateYtdTxn,
  updates,
  valOf,
  valueKind,
  visibleSteps,
  ytdAmountIsNegative,
  ytdDatalistId,
  ytdExistingDatalistsHtml,
  ytdExistingValues,
  ytdHasExistingValues,
  ytdRawMoney,
  ytdSelectFieldHtml,
  ytdTransactionAccounts,
  ytdTxnMoneyDisplay,
});
