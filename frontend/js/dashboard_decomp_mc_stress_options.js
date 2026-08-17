// Extracted from dashboard.js by tools/js_codemod/extract_module.mjs.

export function renderSurvivorStress() {
  const rs = rowsForStep("survivor_stress");
  let html = `<div class="section-note">These are the key inputs driving the Survivor workbook sheet. The primary risks: single-filer tax bracket compression, loss of one Social Security stream, and accelerated required distributions. Change mortality ages or filing status on <a href="#" onclick="setStep('household_people');return false">Household &amp; People</a> to adjust the base assumptions. After rebuilding, view the full Survivor analysis on <a href="#" onclick="setStep('detailed_results');return false">Retirement Plan Workbook</a>.</div>`;
  return (
    html +
    (rs.length
      ? renderFieldGroups(rs)
      : `<div class="field-list"><p>Survivor inputs are entered on Household &amp; People. The full survivor result appears in the workbook after a build.</p></div>`)
  );
}

export function renderLtcStress() {
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

export function renderWorkbenchStressHtml() {
  let html = '<div class="wb-stress-suite">';
  if (!stepGatedByOptionalModule("monte_carlo_options")) {
    html +=
      '<details><summary><b>Probability Analysis (Monte Carlo)</b><span class="small"> engine mode, trial count, and volatility settings</span></summary>' +
      analysisFrame(renderMonteCarloOptions(), "stress") +
      "</details>";
  }
  if (!stepGatedByOptionalModule("survivor_stress")) {
    html +=
      '<details><summary><b>Survivor / Early Death</b><span class="small"> mortality ages, survivor filing status, and account rollover</span></summary>' +
      analysisFrame(renderSurvivorStress(), "stress") +
      "</details>";
  }
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

export function mcEngineRow() {
  return (
    rows.find(
      (x) =>
        isEditable(x) &&
        rowIsMonteCarlo(x) &&
        norm(x.label) === "mc_engine_mode",
    ) || rows.find((x) => isEditable(x) && norm(x.label) === "mc_engine_mode")
  );
}

export function setMcEngineMode(value) {
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

export function mcEngineToggleHtml(engine) {
  const mode = mcEngineModeValue();
  if (!engine)
    return '<p class="small">Monte Carlo engine row is missing from Plan Data. Reloading Plan Data with this package will add it automatically.</p>';
  return `<div class="mc-mode-toggle" role="radiogroup" aria-label="Monte Carlo engine mode"><button type="button" class="mc-mode-option ${mode === "quick_vectorized" ? "active" : ""}" aria-pressed="${mode === "quick_vectorized" ? "true" : "false"}" onclick="setMcEngineMode('quick_vectorized')"><b>Simple</b><span>Runs in seconds. Good for testing changes during plan entry. Approximate — not for final outputs.</span></button><button type="button" class="mc-mode-option ${mode === "advanced_exact_scalar" ? "active" : ""}" aria-pressed="${mode === "advanced_exact_scalar" ? "true" : "false"}" onclick="setMcEngineMode('advanced_exact_scalar')"><b>Complex</b><span>Runs fuller paths per trial. Use for final and advisor-ready workbooks where precision matters.</span></button></div><div class="small mc-mode-current">Saved value: ${esc(valOf(engine) || "advanced_exact_scalar")}</div>`;
}

export function renderMonteCarloOptions() {
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

export function renderDivorceOptions() {
  return optionalFunctionEnabled("divorce_qdro")
    ? renderFields("divorce_options")
    : '<div class="field-list"><p>Divorce options are hidden until the Divorce/QDRO optional workbook module is enabled on Optional workbook modules.</p></div>';
}

// Every export above is also re-attached to window: dashboard.js calls these
// as bare globals, and this file's own rendered HTML uses inline
// onclick="..." handlers, which always resolve through window regardless of
// module scoping. New code should prefer `import` from this module; this
// bridge exists only for callers that cannot move to import in the same pass.
Object.assign(window, {
  renderSurvivorStress,
  renderLtcStress,
  renderWorkbenchStressHtml,
  mcEngineRow,
  setMcEngineMode,
  mcEngineToggleHtml,
  renderMonteCarloOptions,
  renderDivorceOptions,
});
