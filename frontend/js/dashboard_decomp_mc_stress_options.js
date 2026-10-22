// Extracted from dashboard.js by tools/js_codemod/extract_module.mjs.

export function renderSurvivorStress() {
  const rs = rowsForStep("survivor_stress");
  return `<div data-help-section="strategy_stress.survivor">${
    rs.length
      ? renderFieldGroups(rs)
      : `<div class="field-list"><p data-kind="state">Survivor inputs are entered on Household &amp; People.</p></div>`
  }</div>`;
}

export function renderLtcStress() {
  if (!optionalFunctionEnabled("long_term_care_stress"))
    return '<div class="field-list"><p>Long-Term Care Stress inputs are hidden until the Long-Term-Care Stress optional workbook module is enabled on <a href="#" onclick="navigateTo(\'optional_functions\');return false">Plan Features</a>.</p></div>';
  const rs = rowsForStep("ltc_stress");
  return `<div data-help-section="strategy_stress.long_term_care">${
    rs.length
      ? renderFieldGroups(rs)
      : `<div class="field-list"><p data-kind="state">No long-term-care policy inputs found yet.</p></div>`
  }</div>`;
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
    return '<p class="small" data-kind="warn">Monte Carlo engine row is missing from Plan Data; reload the current plan.</p>';
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
    '<div class="field-list"><div class="section-note mc-engine-card" data-kind="state"><b>Start here: choose the Monte Carlo engine.</b>' +
    mcEngineToggleHtml(engine) +
    "</div></div>";
  html += `<div class="field-list"><div class="section-note" data-kind="state"><b>Showing ${mode === "quick_vectorized" ? "simple / quick-mode" : "complex / advanced-mode"} options.</b></div></div>`;
  html += renderFieldGroups(rowsToShow);
  return `<div data-help-section="strategy_stress.monte_carlo_mode">${html}</div>`;
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
  mcEngineRow,
  setMcEngineMode,
  mcEngineToggleHtml,
  renderMonteCarloOptions,
  renderDivorceOptions,
});
