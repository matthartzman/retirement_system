// ── Step gating, visibleSteps and suggested-next (W4-06): extracted verbatim from row_model; bridge below ──
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
Object.assign(window, {
  SPENDING_COMPLETION, SUGGESTED_NEXT, spendingFlowFooterHtml, stepGatedByOptionalModule,
  suggestedNext, visibleSteps,
});
