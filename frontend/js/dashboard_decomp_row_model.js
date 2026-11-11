// ── Row-model + app-shell core (Wave 6.4 domain-module-split, shared-core extraction) ──
// Extracted from dashboard.js verbatim: the 172 functions every
// other domain page's render logic is built on top of (section/norm/valOf/
// isEditable/fieldHtml/rowsForStep/humanLabel/... plus app-shell orchestration
// like api/showMessage/setStep/loadAll/saveAll). Selected as the fan-in >= 3
// hub set from the internal call-graph analysis in
// documentation/archive/superpowers/plans/2026-08-06-dashboard-js-domain-module-split-SCOPE.md.
// renderMain and showStepHelp stay in dashboard.js: other leaf modules
// reassign them as a monkey-patch decorator chain, which this pass does not
// touch. A real ES module (type="module"), same export+window-bridge pattern
// as every other Wave 6.4 leaf. Named dashboard_decomp_*.js (not
// dashboard_row_model.js) so existing tests that glob that pattern for a
// multi-file "full dashboard source" read/smoke-exec pick it up automatically.

let moduleTaxonomy = { modules: {} };
// W5 kept `moduleTaxonomy` module-private on the stated grounds that
// moduleOffImpactWarning() was its only reader. W4's Plan Features page is the
// second: it groups by `domain` and filters by `kind`, both of which live in
// the same payload. Exposed as a getter rather than a window accessor on the
// binding, so this module stays the only writer.
export function planModuleTaxonomy() {
  return moduleTaxonomy || { modules: {} };
}

// WP5.1: `isOn(featureKey)` optionally replaces the live switch reads, so the
// tier picker can ask "which pages would this preset show?" through the same
// rules (tierPageCount in dashboard_decomp_plan_tiers.js). Omitted, every read
// is the live plan's, exactly as before.
export function stepGatedByOptionalModule(stepId, isOn) {
  const on = isOn || optionalFunctionEnabled;
  // §5.3 (W6): steps gated by a plan-data feature flag, not a
  // client_optional_functions.csv toggle. The catalog declares the flag's
  // (section, subsection, label) as gate_ref and flag_gates serves it, exactly
  // as step_gates serves the toggle half below -- replacing the hand-written
  // HELOC and Special Strategies branches that used to sit here.
  const flagGate = (moduleGates.flag_gates || {})[stepId];
  if (flagGate) {
    if (isOn) return !isOn(flagGate.key);
    const r = flagGate.ref || [];
    return !sectionFlagEnabled(r[0], r[1], r[2]);
  }
  // Ticket 323: Stress Test is a screen of four optional sections, so unlike
  // Optimize and Scenarios (each of which has a never-gated section) it can
  // end up with nothing live at all -- hide it when all four of its modules
  // are off. The module keys are read out of step_gates for the four legacy
  // step ids rather than hand-listed, for the same reason as the comment
  // below: server-declared gating is the single source of truth.
  if (stepId === "strategy_stress") {
    const gates = moduleGates.step_gates || {};
    return ["monte_carlo_options", "survivor_stress", "ltc_stress", "divorce_options"]
      .map((id) => gates[id])
      .every((m) => m && !on(m));
  }
  // Ticket 340: Charitable Giving should be reachable whenever either DAF or
  // QCD is on, independent of the (now-decoupled, see
  // dashboard_decomp_estate_insurance.js) charitable_giving workbook toggle
  // that module_catalog otherwise wires up as this step's step_gate.
  if (stepId === "entity_charitable") {
    if (isOn) return !isOn("daf_giving") && !isOn("qcd_giving");
    return (
      !sectionFlagEnabled("DAF", "Settings", "enabled") &&
      !sectionFlagEnabled("Cashflow", "Charitable Giving", "qcd_enabled")
    );
  }
  // WP12.6: Rental Properties hides while off, unless properties are stored: the page then
  // stays in the nav and shows its off state ("Off . N rows entered", data kept).
  if (stepId === "rental_properties") {
    if (isOn) return !isOn("rental_property_income");
    return !on("rental_property_income") && !(typeof rentalKeptCount === "function" && rentalKeptCount() > 0);
  }
  // §7.4: every other module-gated step is server-declared (module_catalog's
  // dashboard_step, via moduleGates.step_gates) rather than hand-listed here —
  // when the module is off, no computation runs and no sheet is built, so the
  // input page is hidden.
  // WP1.3: the Family & Business hub fronts two modules; it hides only when
  // both are off (like entity_charitable above, a hand-written any-of rule).
  // WP1.4: Harvesting is one Optimize section over two modules (loss, gain).
  if (stepId === "harvesting") {
    return !on("tax_loss_harvesting") && !on("gain_harvesting");
  }
  if (stepId === "family_business") {
    return !on("education_funding_529") && !on("equity_compensation");
  }
  const gateModule = (moduleGates.step_gates || {})[stepId];
  if (gateModule) return !on(gateModule);
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

// #330 P8 / Q6 (W13): moved here from dashboard.js, unchanged apart from the
// new entry and the gating guard below. The guided walk's forward links are
// nav structure, and they belong beside visibleSteps()/stepGatedByOptional
// Module(), which is what decides whether the step they name is reachable at
// all. Moving them out is also what pays for W13's new lines under
// tests/test_frontend_size_ratchet.py's DASHBOARD_JS_MAX_LINES.
export const SUGGESTED_NEXT = {
  // Set up chain, in nav order (2026-11-04 redesign): Household & Cash Flow, then Accounts & Property,
  // Protection & Legacy, Taxes, Analyze. Targets that are module-gated are dropped by suggestedNext() below.
  household_people: "income_work",
  income_work: "income_retirement",
  income_retirement: "spending_core",
  spending_core: "cash_accounts",
  cash_accounts: "holdings",
  holdings: "assets_home_cash",
  assets_home_cash: "assets_special",
  assets_special: "annuity_death_benefits",
  annuity_death_benefits: "estate",
  estate: "roth_conversion",
  roth_conversion: "entity_charitable",
  entity_charitable: "strategy_optimize",
  strategy_optimize: "strategy_stress",
  strategy_stress: "reports_and_review",
  // lifestyle_spending and ytd_transactions removed: both redirect onto spending_core before
  // activeStep is set (navigation.js WORKSPACE_TAB_REDIRECTS), so they could never be looked up.
};
export function suggestedNext(stepId) {
  const nav = window.RPNav;
  const maintain = nav && nav.currentMode(overallStats().missing.length, planLoaded) === "maintain";
  const nextId = (maintain && nav.maintainNext(stepId)) || SUGGESTED_NEXT[stepId]; // off the Maintain chain: Set up chain
  const st = STEPS.find((s) => s.id === nextId);
  // W13: a suggestion pointing at a module-gated step whose module is off is
  // a link to a page the nav does not show -- the dead end this workstream's
  // own e2e check exists to keep out. Cheaper to skip the footer than to
  // hand-maintain a parallel "is this one gated" list per entry.
  if (!st || stepGatedByOptionalModule(st.id)) return "";
  return `<div class="suggested-next">Suggested next: <button class="link-button" type="button" data-step-id="${esc(st.id)}">${esc(st.title)} &rarr;</button></div>`;
}

// #330 P8 / Q6 (W13): moved here from dashboard.js, unchanged. renderMain()
// picks between this footer and suggestedNext() on one line -- they are the
// two halves of "what does this page point at next", so they belong in one
// place. Moving them out is also what pays for W13's new lines under
// tests/test_frontend_size_ratchet.py's DASHBOARD_JS_MAX_LINES.
// ytd_transactions and spending_dashboard used to have their own entries
// here (each a distinct standalone step at the time), but both ids now
// redirect onto spending_core before activeStep is ever set to them
// (navigation.js's WORKSPACE_TAB_REDIRECTS) -- spendingFlowFooterHtml() below
// is only ever called with the literal activeStep, so those two entries
// could never be looked up again. Removed rather than left dead.
export const SPENDING_COMPLETION = {
  spending_core: {
    note: "Done when: budget amounts are entered for the categories you track.",
    isDoneFn: () =>
      !!(planLoaded && !stepStats("spending_core").missing.length),
    nextStep: "actual_spending",
    nextLabel: "Import Transactions",
  },
};
export function spendingFlowFooterHtml(stepId) {
  const cfg = SPENDING_COMPLETION[stepId];
  if (!cfg) return "";
  const done = cfg.isDoneFn();
  let html = `<div class="spending-completion-note${done ? " done" : ""}"><span class="scomp-icon">${done ? "&#10003;" : "&#9675;"}</span><span>${esc(cfg.note)}</span></div>`;
  if (done && cfg.nextStep) {
    html += `<div class="spending-advance-prompt"><b>Step complete.</b> Ready for: <button class="btn primary" type="button" data-step-id="${esc(cfg.nextStep)}">${esc(cfg.nextLabel)} &rarr;</button></div>`;
  }
  return html;
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

// UX-003 (system review 2026-09-25, WI-504): callers routinely build error
// toasts as "Error building: " + e.message, and an unhandled server
// exception's message is the raw "<ExceptionClass>: <text>" string
// (src/server/app_core.py _json_unhandled_error). Split that into a
// plain-language summary plus the raw text, which showMessage then puts in
// its existing "Technical details" disclosure instead of the headline.
// Returns null when the message does not carry a raw exception string.
const RAW_EXCEPTION_RE =
  /^([\s\S]*?)\b([A-Z][A-Za-z0-9_]*(?:Error|Exception|Warning|Interrupt|Exit)):\s*([\s\S]*)$/;
export function splitRawErrorText(msg) {
  const text = String(msg ?? "");
  const m = text.match(RAW_EXCEPTION_RE);
  if (!m) return null;
  const prefix = m[1].replace(/[\s:\-–—]+$/, "").trim();
  const summary =
    (prefix || "Something went wrong") +
    ". The app reported an internal problem; open Technical details for the exact message, or try again.";
  return { summary: summary, detail: (m[2] + ": " + m[3]).trim() };
}

export function showMessage(msg, kind = "info", opts) {
  const el = document.getElementById("actionMessage");
  if (!el) return;
  const isError = kind === "error";
  // Errors stay until dismissed (WCAG 2.2.1) unless a caller explicitly
  // opts out with {persistent:false}; other kinds keep the 10 s auto-hide.
  const persistent =
    opts && typeof opts.persistent === "boolean"
      ? opts.persistent
      : isError;
  let techDetail =
    opts && opts.technicalDetail ? String(opts.technicalDetail) : "";
  if (isError) {
    const split = splitRawErrorText(msg);
    if (split) {
      msg = split.summary;
      techDetail = techDetail ? split.detail + "\n" + techDetail : split.detail;
    }
  }
  // Announce through the persistent regions (UX-003): errors assertively, everything else politely.
  announce(msg, { error: isError });
  // An unread error stays on screen until dismissed: a later info message is announced but does not replace it.
  if (!isError && el.classList.contains("bad") && el.classList.contains("persistent") && !el.classList.contains("hidden")) return;
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
    lcv_all_in_including_taxes: firstFinite(summary.lcv_all_in_including_taxes),
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
  // #309/#331: an entry saved before some `kpi` field the dials/suggestions
  // panel now require was added has nothing to migrate to (LCV/NPV of Future
  // Taxes/Worst-Case Ending Wealth/EFTR/All-In LCV require re-running the
  // build, which this load path must not do), so drop it rather than render
  // dials with missing/undefined values. schemaVersion generalizes this:
  // bumping BUILD_HISTORY_SCHEMA_VERSION when a required field is added (or
  // removed) is now the whole fix, instead of writing a new bespoke filter
  // predicate here every time. An entry with no schemaVersion at all predates
  // this mechanism and is always dropped.
  const before = buildHistory.length;
  buildHistory = buildHistory.filter(
    (e) =>
      e &&
      e.kpi &&
      Number.isFinite(Number(e.kpi.lcv)) &&
      e.schemaVersion === BUILD_HISTORY_SCHEMA_VERSION,
  );
  if (buildHistory.length !== before) saveBuildHistory();
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

// UX-008 (system review 2026-09-25, WI-508): single source for the steps
// that render without a loaded plan. navigation.js owns the list (setStep()
// routes by it); the fallback only covers the brief window before
// navigation.js has published window.RetirementNavigation, and matches it.
const PLAN_INDEPENDENT_STEPS_FALLBACK = [
  "start",
  "system_configuration",
  "workbook_formatting",
  "detailed_results",
  "strategy_scenarios",
  "strategy_workbench",
  "reports_and_review",
];
export function planIndependentSteps() {
  const nav = window.RetirementNavigation;
  return nav && Array.isArray(nav.PLAN_INDEPENDENT_STEPS)
    ? nav.PLAN_INDEPENDENT_STEPS
    : PLAN_INDEPENDENT_STEPS_FALLBACK;
}

export function stepTitleById(id) {
  const s = STEPS.find((x) => x.id === id);
  return s ? s.title : String(id || "");
}

export function sourceStepForRow(row) {
  if (!row) return "";
  if (rowIsNextHousingMoveInput(row)) return "strategy_optimize";
  if (primaryHomeRows([row]).length) return "assets_special";
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
  // WP1.3: a feature registered without a CSV row reads its registry default.
  if (!row) return !!(moduleGates.rowless_defaults || {})[labelName];
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

// #338 W-E: the housing PLAN inputs the Next Housing Move switch owns
// (design 2026-09-24 §6) -- the current home's sale and next housing steps
// 1 & 2. Residency periods and sale splits are table rows, not plan rows.
// Off, the engine ignores them (data_io.parse_client) and the CSV keeps them.
export function rowIsNextHousingMoveInput(r) {
  const sec = String(r.section || "").trim();
  const sub = norm(r.subsection || "");
  const lbl = norm(r.label);
  return (
    (sec === "Other Assets" &&
      sub === "home" &&
      (lbl.startsWith("home_sale_") || lbl === "planned_home_sale_year")) ||
    (sec === "Housing" && (sub === "next_step_1" || sub === "next_step_2"))
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
  // #323 gap S7.6: the State residency over time table is now a collapsible
  // on the Housing page. Its own edit-tracking flag was already read by the
  // global unsaved-changes guard (unsavedChangeCount()) but was never wired
  // into ANY step's stepStats() -- editing the table has never raised an
  // "Edited" nav badge on its own page. The gap moved with the table onto
  // spending_mortgage_events; it does not fix itself.
  if (
    (id === "spending_mortgage_events" || id === "spending_core") &&
    residencyScheduleChanged
  )
    d.push({});
  if (
    (id === "ytd_transactions" || id === "actual_spending") &&
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
        "Build reports to create the workbook, dashboard, and Results Explorer model.";
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

// UX-008 / WI-021: nav groups the user opened stay open across the re-renders an edit triggers
// (scheduleStatusUpdate), and a focused nav button keeps focus.
const navGroupsOpenedByUser = new Set();
let navGroupListenerBox = null;
// Only groups the USER opened or closed are remembered: a group that is open merely because it
// holds the active step is ignored here, so it still collapses when the user moves elsewhere.
function watchNavGroupToggles(box) {
  if (!box || navGroupListenerBox === box || !box.addEventListener) return;
  navGroupListenerBox = box;
  box.addEventListener(
    "toggle",
    (e) => {
      const d = e.target;
      const name = d && d.getAttribute && d.getAttribute("data-group");
      if (!name) return;
      const holdsActive = !!(d.querySelector && d.querySelector('[aria-current="step"]'));
      if (d.open) {
        if (!holdsActive) navGroupsOpenedByUser.add(name);
      } else navGroupsOpenedByUser.delete(name);
    },
    true,
  );
}
export function renderSteps() {
  const box = document.getElementById("steps");
  watchNavGroupToggles(box);
  const focusedStepId =
    box && box.contains && document.activeElement && box.contains(document.activeElement)
      ? document.activeElement.getAttribute && document.activeElement.getAttribute("data-step-id")
      : null;
  let html = "";
  const stats = overallStats();
  const pct = stats.total ? Math.round(100 * (stats.done / stats.total)) : 0;
  document.getElementById("progressBar").style.width = pct + "%";
  const _mpb = document.getElementById("mobileProgressBar");
  if (_mpb) _mpb.style.width = pct + "%";
  const navMode = window.RPNav ? window.RPNav.currentMode(stats.missing.length, planLoaded) : "setup";
  const progressText = window.RPNav
    ? window.RPNav.progressTexts(navMode, pct, stats.missing.length, planLoaded)
    : { progress: planLoaded ? `${pct}% complete` : "Open local plan", required: planLoaded ? `${stats.missing.length} required missing` : "" };
  document.getElementById("progressLabel").textContent = progressText.progress;
  document.getElementById("requiredLabel").textContent = progressText.required;
  const q = String(navSearchText || "")
    .trim()
    .toLowerCase();
  let stepNumber = 0;
  const allSteps = visibleSteps();
  const statsMemo = new Map(); // each step's stats once per render: nav search re-renders on every typing pause
  const statsOf = (id) => statsMemo.get(id) || (statsMemo.set(id, stepStats(id)), statsMemo.get(id));
  function stepButton(s) {
    stepNumber += 1;
    const st = statsOf(s.id);
    const cls =
      s.id === activeStep
        ? "active"
        : st.missing.length
          ? "missing"
          : st.required.length
            ? "complete"
            : "";
    // #323 / UX-008 (WI-508): the steps usable before a plan is open come
    // from navigation.js's PLAN_INDEPENDENT_STEPS -- the same list setStep()
    // routes by -- so the nav, the router and renderMain cannot disagree.
    const navDisabled = !planLoaded && !planIndependentSteps().includes(s.id);
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
      s.id === "actual_spending" &&
      typeof window.getSpendingDivergencePct === "function" &&
      Number(window.getSpendingDivergencePct()) > 0.03;
    if (st.missing.length)
      badge = `<span class="badge bad">${st.missing.length}</span>`;
    else if (st.dirty.length) badge = `<span class="badge dirty">Edited</span>`;
    else if (spendingWarn)
      badge = `<span class="nav-badge nav-badge--warn" title="Annualized spending is more than 3% over the annual budget (details at the top of Actual Spending)">! &gt;3%</span>`;
    else if (reportStale) badge = `<span class="badge warn">Stale</span>`;
    else if (st.required.length) badge = `<span class="badge ok">OK</span>`;
    // UX-010 (WI-509): the current step is announced, not shown by colour only.
    const current = s.id === activeStep ? ' aria-current="step"' : "";
    return `<button class="stepbtn ${cls}" type="button" data-step-id="${s.id}"${current} ${navDisabled ? "disabled" : ""} ><span class="num">${stepNumber}</span><span><span class="step-title">${esc(s.title)}</span><br><span class="step-desc">${esc(s.desc)}</span></span>${badge}</button>`;
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
  const orderedGroups = window.RPNav ? window.RPNav.orderGroups(groups, navMode) : groups;
  if (window.RPNav && !q)
    window.RPNav.seedOpenGroup(
      navGroupsOpenedByUser,
      orderedGroups,
      navMode,
      (g) => g.steps.reduce((n, s) => n + statsOf(s.id).missing.length, 0),
      planLoaded,
    );
  orderedGroups.forEach((g) => {
    // Plan Status is a pinned link, not a one-page heading.
    if (g.name === "Plan Status") {
      html += g.steps.map(stepButton).join("");
      return;
    }
    const isActive = g.steps.some((s) => s.id === activeStep);
    const gMissing = g.steps.reduce(
      (n, s) => n + statsOf(s.id).missing.length,
      0,
    );
    const badge = gMissing ? `<span class="badge bad">${gMissing}</span>` : "";
    const open = isActive || navGroupsOpenedByUser.has(g.name) ? "open" : "";
    html += `<details class="nav-group" data-group="${esc(g.name)}" ${open}><summary class="nav-group-summary"><span class="nav-group-name">${esc(g.name)}${badge}</span>${window.RPNav ? window.RPNav.iconHtml(g.name) : ""}</summary><div class="nav-group-steps">`;
    g.steps.forEach((s) => {
      html += stepButton(s);
      // Workspace tabs (e.g. Actual Spending's This year / Analysis) are
      // switched inside the page itself, so they no longer get left-nav
      // children. detailed_results is a hidden step (only appears in this
      // loop when it IS activeStep, see the `s.hidden && s.id !== activeStep`
      // filter above), so its sheet-picker nav only renders while viewing it.
      if (s.id === "detailed_results") {
        html += renderDetailedResultsNav();
      }
    });
    html += `</div></details>`;
  });
  box.innerHTML = html;
  if (window.RPNav) window.RPNav.afterRender(navMode);
  if (focusedStepId && box.querySelector) {
    const again = box.querySelector('[data-step-id="' + focusedStepId + '"]');
    if (again && again.focus) again.focus({ preventScroll: true });
  }
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
  // exclusion_ratio is stored as a raw 0-1 fraction (0.738), unlike every
  // other percent field in this app (stored already on a 0-100 scale, e.g.
  // "5.00%") -- it needs its own kind so display/storage can scale by 100
  // instead of just appending "%". Must be checked before the generic
  // "exclusion" dollar-keyword match below, which would otherwise catch it
  // (that keyword is for genuine dollar exclusions like
  // section_121_exclusion_mfj and annual_exclusion_per_donee).
  if (r && l === "exclusion_ratio") return "percent_fraction";
  // Every *_weight setting (Roth optimizer and legacy weights, real-loss
  // weight) is stored as a raw multiplier (0.35, 1.00) and shown as a percent
  // (35%, 100%). Checked before the keyword matching below, which reads a
  // "tax" in the label as a dollar amount.
  if (r && /_weight$/.test(l)) return "percent_fraction";
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
  if (kind === "percent_fraction") {
    const n = numberFromDisplay(value);
    return n === null ? String(value ?? "").trim() : decimalTrim(String(n / 100));
  }
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
  if (kind === "percent_fraction") {
    const n = numberFromDisplay(value);
    if (n === null) return String(value ?? "");
    const scaled = n * 100;
    // percentDisplayDecimals reads decimal-place counts straight off the raw
    // text (row.value etc.), which is correct for a normal percent field but
    // would misfire here: the *stored* fraction "0.738" has 3 decimal
    // digits, while the *scaled* "73.8" needs only 1 -- ×100 shifts the
    // decimal point left by 2. Subtract that shift from each source's raw
    // decimal count instead of reusing percentDisplayDecimals directly.
    const fractionDecimals = (text) => {
      const m = String(text ?? "").match(/\.(\d+)/);
      return m ? Math.max(0, Math.min(6, m[1].length - 2)) : 0;
    };
    const decimals = Math.max(
      fractionDecimals(value),
      fractionDecimals(row?.value),
      fractionDecimals(row?.schema?.default),
    );
    return percentDisplay(scaled, decimals);
  }
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

// UX-003 (WI-504): row_index values the backend's save validation rejected
// on the last failed save. fieldHtml marks those controls aria-invalid; the
// set is replaced on every failed save and cleared on a successful one.
export const saveValidationInvalidRows = new Set();
// WI-020 / UX-004: the server's message for each rejected row (row_index -> text), shown
// under the control (aria-describedby) and listed, with links, in the #saveErrorSummary region.
export const saveValidationErrors = new Map();
export function saveFieldErrorId(rowIndex) {
  return "field-" + rowIndex + "-err";
}
export function saveFieldErrorHtml(rowIndex) {
  return (
    '<div class="field-error" id="' +
    saveFieldErrorId(rowIndex) +
    '"><span aria-hidden="true">&#9888; </span><span class="sr-only">Error: </span>' +
    esc(saveValidationErrors.get(rowIndex) || "") +
    "</div>"
  );
}

// UX-002 (system review 2026-09-25, WI-503): stable ids tying each plan-data
// control to its visible label and its describing text (unit caption,
// Required badge, inactive-value note), so assistive tech announces the
// field name, required state and help rather than "edit text"/"YES".
export function fieldControlId(rowIndex) {
  return "field-" + rowIndex + "-ctl";
}

export function fieldHtml(r, opts) {
  const hideUnit = !!(opts && opts.hideUnit);
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
  const ctlId = fieldControlId(r.row_index);
  const lblId = "field-" + r.row_index + "-lbl";
  const unitId = "field-" + r.row_index + "-unit";
  const reqId = "field-" + r.row_index + "-req";
  const inactiveId = "field-" + r.row_index + "-inactive";
  const inactiveState = rowBuildUsageState(r, activeStep);
  const inactiveRevealed =
    inactiveEditReveals.has(r.row_index) && !inactiveState.active;
  const saveErr = saveValidationErrors.has(r.row_index);
  const errId = saveFieldErrorId(r.row_index);
  const describedBy = [
    saveErr ? errId : "",
    missing ? reqId : "",
    units && !hideUnit ? unitId : "",
    inactiveRevealed ? inactiveId : "",
  ].filter(Boolean);
  const invalid = missing || saveValidationInvalidRows.has(r.row_index);
  // Shared by every control branch below. Checkboxes additionally get
  // aria-labelledby: they sit inside the .toggle-switch <label>, whose own
  // YES/NO text would otherwise become their accessible name.
  const a11y =
    ` id="${ctlId}"` +
    (describedBy.length ? ` aria-describedby="${describedBy.join(" ")}"` : "") +
    (isRequired(r) ? ' aria-required="true"' : "") +
    (invalid ? ' aria-invalid="true"' : "");
  let control = "";
  if (
    lblNorm === "allocation_selection_mode" ||
    lblNorm === "allocation_mode"
  ) {
    const mode = allocationSelectionMode();
    control = `<select${a11y} data-row="${r.row_index}" onchange="editValue(${r.row_index},this.value,this);renderMain()" onfocus="showFieldHelp(${r.row_index})"><option value="user_target" ${mode === "user_target" ? "selected" : ""}>Use user-specified allocation</option><option value="optimizer_recommendation" ${mode === "optimizer_recommendation" ? "selected" : ""}>Use allocation optimizer recommendation</option><option value="max_sharpe" ${mode === "max_sharpe" ? "selected" : ""}>Best risk-adjusted mix, staying within the risk limits you set (max-Sharpe)</option><option value="tangency" ${mode === "tangency" ? "selected" : ""}>Best risk-adjusted mix, ignoring your risk limits (tangency)</option><option value="real_loss_aware" ${mode === "real_loss_aware" ? "selected" : ""}>Match each dollar to when you’ll spend it, minimizing the chance of a loss after inflation</option></select>`;
  } else if (boolish) {
    const yes =
      String(value).toUpperCase() === "YES" ||
      String(value).toUpperCase() === "TRUE";
    control = `<label class="toggle-switch" data-row="${r.row_index}"><input type="checkbox"${a11y} aria-labelledby="${lblId}" ${yes ? "checked" : ""} onchange="editValue(${r.row_index},this.checked?'YES':'NO',this)" onfocus="showFieldHelp(${r.row_index})"><span class="toggle-track" aria-hidden="true"></span><span class="toggle-text toggle-text-yes" aria-hidden="true">YES</span><span class="toggle-text toggle-text-no" aria-hidden="true">NO</span></label>`;
  } else if (type === "choice" || norm(units) === "choice" || window.STATE_INPUT_LABELS.has(lblNorm)) {
    const opts = choiceOptions(r);
    if (opts.length) {
      const cur = String(value || "").trim();
      const rerender =
        lblNorm === "core_spending_growth_mode" ||
        lblNorm === "roth_conversion_policy" ||
        lblNorm === "irmaa_guardrail_mode" ||
        lblNorm === "hsa_withdrawal_mode";
      control = `<select${a11y} data-row="${r.row_index}" onchange="editValue(${r.row_index},this.value,this);${rerender ? "renderMain()" : ""}" onfocus="showFieldHelp(${r.row_index})">${opts
        .map((o) => {
          const ov = choiceValue(o),
            ol = choiceLabel(o);
          return `<option value="${esc(ov)}" ${norm(ov) === norm(cur) ? "selected" : ""}>${esc(translatePersonPlaceholders(formatAcronyms(ol.replace(/_/g, " "))))}</option>`;
        })
        .join("")}</select>`;
    } else {
      // #<housing focus loss>: a stable data-focus-key lets ticket 285's
      // captureMainPaneFocus/restoreMainPaneFocus revive this exact input
      // (and its caret) if something -- e.g. a Housing row's reestimate
      // ripple -- calls renderMain() synchronously while it's focused.
      control = `<input type="text"${a11y} data-row="${r.row_index}" data-focus-key="field:${r.row_index}" value="${esc(String(value || ""))}" placeholder="${esc(r.schema?.default || "")}" oninput="editValue(${r.row_index},this.value,this)" onfocus="beginEdit(${r.row_index},this)" onblur="finishEdit(${r.row_index},this)">`;
    }
  } else {
    const inputType = isDateField(r) ? "date" : "text";
    const inputValue = displayValueForInput(r, value);
    control = `<input type="${inputType}"${a11y} data-row="${r.row_index}" data-focus-key="field:${r.row_index}" value="${esc(inputValue)}" placeholder="${esc(r.schema?.default || "")}" oninput="editValue(${r.row_index},this.value,this)" onfocus="beginEdit(${r.row_index},this)" onblur="finishEdit(${r.row_index},this)">`;
  }
  const note = formatAcronyms(r.schema?.description || r.notes || "");
  const req = missing
    ? `<span class="badge req" id="${reqId}">Required</span>`
    : "";
  const inactiveBadge = inactiveRevealed
    ? '<span class="badge warn">Inactive unless activated</span>'
    : "";
  // hideUnit: some callers (e.g. the Next Housing Step editor) render their
  // own compact hint and opt out of this raw type-token caption.
  const unit = units && !hideUnit
    ? `<div class="unit" id="${unitId}">${esc(formatAcronyms(units))}</div>`
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
  const saveErrHtml = saveErr ? saveFieldErrorHtml(r.row_index) : "";
  return `<div class="field ${missing ? "missing" : ""} ${saveErr ? "invalid" : ""} ${dirtyHere ? "dirty" : ""} ${inactiveRevealed ? "inactive-edit" : ""}${paired ? " paired" : ""}${flow ? " flow" : ""}${sizeClass ? " " + sizeClass : ""}${negClass}" id="field-${r.row_index}" onclick="showFieldHelp(${r.row_index})"><div><div class="field-label"><label id="${lblId}"${boolish ? "" : ` for="${ctlId}"`}>${esc(opts && opts.dropRoth ? humanLabel(r.label, r).replace(/^Roth\s+/i, "") : humanLabel(r.label, r))}${fieldLabelNoteHtml(r)}</label>${fieldTooltipHtml(lblNorm, r)}</div><div class="field-meta">${req}${dirtyHere ? '<span class="badge dirty">Edited</span>' : ""}${inactiveBadge}</div></div><div>${control}${saveErrHtml}${unit}${inactiveRevealed ? `<div class="unit" id="${inactiveId}">${esc(formatAcronyms(inactiveState.activation || "Change this value or its controlling setting to make it active in the build."))}</div>` : ""}</div></div>`;
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
  // #323: allocation_assets and distribution_strategy were both legacy step
  // ids for pages that hosted the Allocation & Location panel; both now
  // redirect to strategy_optimize (SECTION_REDIRECTS in navigation.js), and
  // activeStep can never actually equal either of them once the redesign's
  // nav is in place. strategy_optimize is the only id the panel is shown
  // under now -- this is a replacement, not an additional accepted value.
  if (!planLoaded || activeStep !== "strategy_optimize") return;
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
      if (seq === allocationPreviewSeq && activeStep === "strategy_optimize")
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
  const tierView = fieldTierView(step, rs, !!searchText.trim());
  rs = tierView.rows;
  const missing = rs.filter(isMissing);
  let html = tierView.controlHtml;
  html += missing.length
    ? `<div class="missing-list"><h3>${missing.length} required field${missing.length === 1 ? "" : "s"} missing in this view</h3><ul>${missing
        .slice(0, 8)
        .map((r) => `<li>${esc(humanLabel(r.label, r))}</li>`)
        .join("")}</ul></div>`
    : "";
  if (["assets_special"].includes(step))
    html += `<div class="section-note" data-kind="state" data-help-section="assets_special.reporting_fields">Some fields here are reporting-only. ${window.RPHelp?.sectionButtonHtml("assets_special.reporting_fields") || ""}</div>`;
  // Phase 3b: the prose for these pages lives in HELP_SECTIONS (help_registry.js); the key wraps the page body.
  const helpKey = { scenarios: "strategy_scenarios.stress_rows", roth_conversion: "roth_conversion.bracket_targets", all_assumptions: "all_assumptions.field_list", monte_carlo_options: "strategy_stress.monte_carlo_mode" }[step];
  const wrapHelp = (inner) => (helpKey ? `<div data-help-section="${helpKey}">${inner}</div>` : inner);
  // #330 §5.2 (W12): a step-owning module that is off gets a note, not a
  // blackout -- the earlier hand-written versions of these branches each
  // `return`ed a static "hidden" paragraph in place of the step's rows,
  // which is exactly the no-hidden-data invariant violation §5.2 exists to
  // close (a search hit or a direct step visit must not make already-entered
  // data disappear just because its module is off). featureGatedNote() now
  // supplies the note -- registry-driven, so a plan-flag step (via
  // flag_gates) and a module-toggle step (divorce_qdro/long_term_care_stress/
  // charitable_giving) resolve through the same call -- and rs still renders
  // below it rather than being replaced by it.
  const _flagGate = (moduleGates.flag_gates || {})[step];
  const gateKey = _flagGate
    ? _flagGate.key
    : step === "divorce_options"
      ? "divorce_qdro"
      : step === "ltc_stress"
        ? "long_term_care_stress"
        : null;
  const gateOff = _flagGate
    ? !sectionFlagEnabled(..._flagGate.ref)
    : gateKey
      ? !optionalFunctionEnabled(gateKey)
      : false;
  if (gateKey && gateOff) html += featureGatedNote(gateKey, { rows: rs });
  if (step === "all_assumptions") return wrapHelp(html + renderFieldFinderGroups(rs));
  // #358: the ACA section sits directly above the Tax Assumptions table, which
  // the tax-assumptions module appends after this page's fields.
  if (step === "economic_tax_assumptions") {
    const isAca = (r) => norm(r.subsection).startsWith("aca");
    const aca = rs.filter(isAca);
    if (aca.length)
      return (
        html +
        renderFieldGroups(rs.filter((r) => !isAca(r))) +
        `<div class="field-list"><h3 class="group-title">${esc(friendlyGroup(aca[0]))}</h3>${sortRowsByDependency(aca).map(fieldHtml).join("")}</div>`
      );
  }
  return wrapHelp(html + renderFieldGroups(rs));
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
  // Older files predate the payoff-month / carry-zero columns; add them so edits serialize.
  ["payoff_month", "carry_zero"].forEach((h) => {
    if (!header.includes(h)) header.splice(Math.max(0, header.indexOf("notes")), 0, h);
  });
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
  markBuildStale();
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

export function _isViewingDetailedResults() {
  return activeStep === "detailed_results";
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
  const goingToYtd = step === "actual_spending" && next === "This year";
  // Ticket 290: setStep(step) below triggers a full synchronous renderMain()
  // of the spending workspace, which measured ~1.5s even before any YTD data
  // loads -- so EVERY tab into spending_core (not just YTD) pays this cost,
  // matching the reported "Spending Model is also slow with no progress bar"
  // symptom. Previously the overlay was shown only for the YTD tab, and only
  // AFTER this render (inside loadYtdStatus), so the render always ran behind
  // a locked, affordance-free screen. Show the overlay and yield one frame so
  // the browser actually paints it BEFORE the blocking render begins --
  // painting an overlay you never yield to is why it used to appear late.
  const isSpendingWorkspace = step === "actual_spending";
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
  if (saveValidationErrors.has(idx)) clearFieldSaveError(idx);
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
  if (row && row.section === "Housing" && dirty.has(idx)) {
    const adjusted = reestimateHousingCostsOnValueChange(row, original, stored);
    if (adjusted) {
      renderMain();
      showMessage(
        `Re-estimated ${adjusted} housing cost field${adjusted === 1 ? "" : "s"} (utilities/maintenance/insurance) for the updated ${norm(row.label) === "purchase_price" ? "home value" : "rent"}. Review and adjust as needed.`,
      );
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
  if (l === "net_monthly_payment")
    return {
      purpose: "The monthly amount that actually lands in your bank account from this pension or annuity, after the payer withholds income tax. Withholding = gross payment minus this amount.",
      impact: "None on the projection: the plan taxes the gross payment itself and shows taxes separately. This is kept so you can match the plan to your bank deposits.",
      consider: "Copy the net (after-withholding) amount from the payer's statement or your bank deposit. Leave blank if nothing is withheld; net is then the same as gross.",
    };
  if (l === "annuity_pv_discount_rate")
    return {
      purpose: "Net worth counts your annuities and pension as the present value of their remaining payments. This is the rate used to discount those future payments back to today. Leave it blank to use your portfolio return.",
      impact: "A lower rate gives your guaranteed income a higher value today, raising net worth (and the estate-tax estimate the Roth conversion planner uses). It does not change the payments or your cash flow.",
      consider: "Guaranteed income is usually valued like a high-quality bond, so 4-5% is common. Your portfolio return is higher and values the same payments lower.",
    };
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
  document.body.classList.add("help-open");
}

export function showFieldHelp(idx) {
  const row = rows.find((r) => r.row_index === idx);
  if (!row) return;
  // Contextual help Phase 1: with help_registry.js loaded, field help follows focus without
  // opening the panel; explicit openers ("i", aria-controls="helpPanel") open it there.
  if (window.RPHelp) window.RPHelp.pinned("field", idx);
  else ensureHelpPanelVisible();
  const label = humanLabel(row.label, row);
  const note = translatePersonPlaceholders(
    formatAcronyms(row.schema?.description || row.notes || ""),
  );
  const g = { ...fieldGuidance(row), ...(window.RPHelp?.fieldEntry(row.label) || {}) };
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
    // #<reports-redesign>: Reports & Review's header Build button is only
    // active when there's something to build (reportsAndReviewCanBuild()) --
    // without this marker, this loop's unconditional `b.disabled = !on`
    // silently clears whatever disabled state the button was rendered with
    // whenever the app is reachable, regardless of that button's own logic.
    const needsEdit = b.getAttribute("data-requires-edit") === "1";
    // Reports & Review's header Download button: gated on report artifacts
    // actually existing, not lastBuildOk -- see reportsAndReviewDownloadWorkbook()
    // for why lastBuildOk (forced false by any unsaved edit) is the wrong
    // signal for "is there a workbook to download at all."
    const needsArtifacts = b.getAttribute("data-requires-artifacts") === "1";
    b.disabled =
      !on ||
      (needsBuild && !lastBuildOk) ||
      (needsEdit && !reportsAndReviewCanBuild()) ||
      (needsArtifacts && !planStateArtifactsReady());
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
  // One request path (W1-06): RetirementApiClient owns timeouts and the error shape
  // {message, status, errors, fieldErrors}; there is no inline fetch fallback.
  window.RetirementApiClient.setBase(apiBase || "");
  return await window.RetirementApiClient.request(path, opts);
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
    opts.overlayId || "loadPlan",
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
    moduleGates = cfg.module_gates || { step_gates: {}, section_gates: {}, flag_gates: {} };
    // #330 phase 2 + §3.4: both classification axes and the soft-dependency
    // relation, for the Plan Features switch UI. Module-private on purpose --
    // moduleOffImpactWarning() below is the only reader, so unlike
    // moduleStatus/moduleGates this needs no window accessor.
    moduleTaxonomy = cfg.module_taxonomy || { modules: {} };
    // WP5.1: the plan profile and tier presets for the Plan Features picker.
    if (typeof setPlanTierPayload === "function") setPlanTierPayload(cfg);
    if (window.RetirementAppStore)
      window.RetirementAppStore.set({
        rows: rows,
        runtime: runtime,
        planLoaded: true,
        planSource: opts.source || "Local database",
      });
    resetAllocationPreview();
    // W10a: same reason, one plan over. The Roth result panel caches the last
    // /api/summary read so it survives a reload; without this a plan switch
    // would keep showing the PREVIOUS plan's optimizer result, since
    // lastBuildSummary is null until this plan is built in this session.
    rothResultCacheReset();
    // W10c: the housing search's last result is retained for apply-to-plan,
    // and it is a result about the PREVIOUS plan's home and finances. Left
    // behind, its apply strip would offer to write that answer into this one.
    housingOptResultReset();
    await loadTravelExtras();
    await loadBudgetLines(false);
    await loadLiquidityBuffers();
    await loadForcedConversions();
    await loadHomeSaleSplits();
    await loadResidencySchedule();
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
  // WP8.4: header plan switcher shows the active plan.
  if (typeof window.refreshPlanSwitcher === "function") window.refreshPlanSwitcher();
  // WP10.4: first-launch conversion notice.
  if (typeof window.refreshConversionNotice === "function") window.refreshConversionNotice();
}

export function updates() {
  return [...dirty.entries()].map(([row_index, value]) => {
    const row = rows.find((r) => r.row_index === row_index);
    return { row_index, value: normalizeValueForSave(row, value) };
  });
}

export function hasUnsavedPlanChanges() {
  return !!(
    dirty.size ||
    window.holdingsChanged ||
    liabilitiesChanged ||
    travelExtrasChanged ||
    liquidityChanged ||
    forcedConversionsChanged ||
    homeSaleSplitsChanged ||
    residencyScheduleChanged ||
    ytdTransactionsChanged ||
    ytdAccountsChanged ||
    rulesChanged ||
    taxBudgetChanged ||
    budgetLinesChanged ||
    !!(window.spendingAdjustmentsDirty && window.spendingAdjustmentsDirty())
  );
}

export async function saveWorkingCopy() {
  if (!planLoaded) {
    showMessage("Start or open the local plan before saving.", "error");
    return false;
  }
  if (!validateAllocationTargetsOrMessage()) return false;
  if (
    homeSaleSplits.length &&
    Math.abs(homeSaleSplitPctTotal() - 100) >= 0.01
  ) {
    setStep("spending_mortgage_events");
    showMessage(
      `Home sale split percentages must total 100% before saving (currently ${homeSaleSplitPctTotal().toFixed(1)}%).`,
      "error",
    );
    return false;
  }
  for (let i = 0; i < residencySchedule.length; i++) {
    const p = residencySchedule[i];
    const isLast = i === residencySchedule.length - 1;
    if (!p.state || !p.start_year) {
      activeStep = "state_residency";
      renderMain();
      showMessage(
        `Residency row ${i + 1} needs a state and a start year before saving.`,
        "error",
      );
      return false;
    }
    if (isLast && p.end_year) {
      activeStep = "state_residency";
      renderMain();
      showMessage(
        "The last residency row must be open-ended — clear its end year before saving.",
        "error",
      );
      return false;
    }
    if (!isLast && !p.end_year) {
      activeStep = "state_residency";
      renderMain();
      showMessage(
        `Residency row ${i + 1} needs an end year — only the last row may be open-ended.`,
        "error",
      );
      return false;
    }
  }
  await saveChanges(false);
  await saveTravelExtras(false);
  await saveLiquidityBuffers(false);
  await saveForcedConversions(false);
  await saveHomeSaleSplits(false);
  await saveResidencySchedule(false);
  await saveYtdPending();
  if (rulesChanged) await saveMappingRulesData();
  if (taxBudgetChanged) await saveTaxonomyBudgetData();
  if (budgetLinesChanged) await saveBudgetLines();
  if (window.saveSpendingAdjustments) await window.saveSpendingAdjustments(false);
  if (window.withdrawalAccountOrderIsDirty && window.withdrawalAccountOrderIsDirty() && window.saveWithdrawalAccountOrder)
    await window.saveWithdrawalAccountOrder();
  await saveHoldings();
  await saveLiabilities();
  await saveHsaSchedule();
  updateUnsaved();
  return true;
}


// UX-001 / WI-018: every in-page add/delete/seed handler ends in loadAll(),
// which re-reads rows from the server and clears the dirty map. Call this
// first: it saves any staged edits (saveWorkingCopy, same as the plan-tier
// actions) and returns false -- after showing the usual field-aware save
// error -- when the save fails, so the caller must abort and the structural
// change never runs on top of unsaved edits.
export async function saveBeforeStructuralChange() {
  try {
    if (!hasUnsavedPlanChanges()) return true;
    if (!planLoaded) return true;
    const saved = await saveWorkingCopy();
    if (!saved) return false;
    clearSaveValidationErrors();
    return true;
  } catch (e) {
    reportSaveFailure(e);
    return false;
  }
}

export async function saveAll(sync = true) {
  try {
    if (!planLoaded) {
      showMessage("Start or open a plan before saving.", "error");
      return false;
    }
    const saved = await saveWorkingCopy();
    if (!saved) return false;
    clearSaveValidationErrors();
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
    reportSaveFailure(e);
    return false;
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

Object.assign(window, {
  _isViewingDetailedResults,
  _updateDetailGroupStatus,
  accountDisplayLabel,
  allocationModeRow,
  allocationSelectionMode,
  allocationTargetRows,
  allocationTargetTotalPct,
  allocationTotalHtml,
  api,
  apiUrl,
  assetCategory,
  beginEdit,
  blurBudgetMoney,
  budgetMoneyInputValue,
  budgetMoneyNumber,
  buildHistoryProvenance,
  choiceValue,
  currencyRaw,
  currentKpi,
  deriveAfterTaxTerminalNw,
  displayValueForInput,
  editValue,
  ensureHelpPanelVisible,
  ensureLiabilityRows,
  fieldGuidance,
  fieldHtml,
  findEditableRow,
  findTargetRow,
  finishEdit,
  firstFinite,
  fmtDelta,
  fmtPctDelta,
  focusBudgetMoney,
  hasAny,
  hasUnsavedPlanChanges,
  helocModuleEnabled,
  homeValueLabelIsCanonical,
  householdPersonRow,
  isDateField,
  isEditable,
  isMissing,
  isRequired,
  loadAll,
  loadBuildHistory,
  loadDetailedResultSheet,
  ltcLifePolicyModuleEnabled,
  markLiabilitiesDirty,
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
  pushBuildHistoryEntry,
  
  planModuleTaxonomy,
  recAdd,
  refreshBuildStatus,
  refreshPreflightForReview,
  renderAllocationPolicy,
  renderFieldGroups,
  renderFields,
  renderSteps,
  reportsUiContext,
  requestAllocationPreview,
  rowActionValue,
  rowByNormLabel,
  rowIsBaseHomeSaleInput,
  rowIsNextHousingMoveInput,
  rowIsCanonicalHomeValue,
  rowIsDivorceScenario,
  rowIsMonteCarlo,
  rowIsRetiredScenarioHomeDuplicate,
  rowIsStressSellHomeInput,
  rowsForStep,
  saveAll,
  saveFieldErrorHtml,
  saveBeforeStructuralChange,
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
  setStep,
  showFieldHelp,
  showMessage,
  planIndependentSteps,
  shutdownAndClose,
  sortRowsByDependency,
  sourceStepForRow,
  stepGatedByOptionalModule,
  stepStats,
  goToStrategyTab,
  stepTitleById,
  storageValueForInput,
  spendingFlowFooterHtml,
  SPENDING_COMPLETION,
  strategyTabKey,
  suggestedNext,
  SUGGESTED_NEXT,
  toIsoDateValue,
  unsavedChangeCount,
  updatePlanStateBanner,
  updateUnsaved,
  updates,
  valOf,
  valueKind,
  visibleSteps,
});
