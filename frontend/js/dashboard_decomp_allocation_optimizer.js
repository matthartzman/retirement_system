// Extracted from dashboard.js by tools/js_codemod/extract_module.mjs.

export function kpiHasValues(summary) {
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

export function setPlanningLeverInput(key, val) {
  const n = Number(
    String(val || "")
      .replace(/[$,%]/g, "")
      .replace(/,/g, ""),
  );
  planningLeverInputs[key] = Number.isFinite(n) ? n : 0;
  renderMain();
}

export function planningLeversBaselineReady() {
  return !!(
    planLoaded &&
    (lastBuildOk ||
      planStateArtifactsReady() ||
      kpiHasValues(lastBuildSummary) ||
      (lastBuildCompare && kpiHasValues(lastBuildCompare.after)))
  );
}

export function planningLeversPlaceholder() {
  if (!buildPreflight)
    setTimeout(() => refreshBuildStatus().catch(function () {}), 0);
  return `<div class="holdings planning-levers planning-levers-empty"><div class="empty-state-panel"><span class="eyebrow">Baseline required</span><h3>Build once before using Strategy Levers</h3><p>Planning Levers rank changes against the latest successful baseline. Build reports first so the page can use real terminal net worth, post-tax inheritance, lifetime tax, and Monte Carlo success values instead of placeholder zeros.</p><div class="pane-actions"><button class="btn primary" type="button" data-requires-app="1" onclick="runBuild(false)">Build Reports</button><button class="btn" type="button" data-step-id="review">Open Review and Build</button><button class="btn" type="button" onclick="refreshPreflightForReview()">Refresh Preflight</button></div></div><div class="feature-grid optimizer-hub" style="margin:10px 0 14px"><div class="feature-card"><h3>What unlocks after build</h3><p class="small">Ranked lever estimates, measured baseline KPIs, and source-page jumps for changing the actual plan.</p></div><div class="feature-card"><h3>Where to work meanwhile</h3><p class="small">Use Roth Conversion, Asset Allocation, Spending Categories, Scenarios, and Monte Carlo pages to stage inputs before the first baseline build.</p></div></div></div>`;
}

export function renderPlanningLevers() {
  if (!planningLeversBaselineReady()) return planningLeversPlaceholder();
  const b = planningLeverBase();
  const rows = planningLeverRows();
  // #256: quick-nav buttons for an optional-module-gated page must not show
  // when that module is off (was hardcoded per-button for divorce_qdro and
  // long_term_care_stress separately, which drifted -- reuses the same
  // server-declared stepGatedByOptionalModule() single source of truth
  // every other nav surface in the app already uses, so this covers every
  // current and future optional module uniformly, not just the ones
  // someone happened to special-case here).
  function leverNavButton(stepId, label) {
    return stepGatedByOptionalModule(stepId)
      ? ""
      : `<button class="btn" type="button" data-step-id="${esc(stepId)}">${esc(label)}</button> `;
  }
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
  const decideButtons =
    leverNavButton("roth_conversion", "Roth conversion") +
    leverNavButton("allocation_assets", "Asset allocation & location") +
    leverNavButton("spending_core", "Withdrawal order");
  const otherDecideButtons =
    leverNavButton("income_retirement", "Social Security") +
    leverNavButton("entity_charitable", "Charitable giving") +
    leverNavButton("heloc_strategy", "HELOC strategy");
  const resilienceButtons =
    leverNavButton("monte_carlo_options", "Monte Carlo") +
    leverNavButton("scenarios", "Scenarios") +
    leverNavButton("survivor_stress", "Survivor") +
    leverNavButton("ltc_stress", "Long-term care") +
    leverNavButton("divorce_options", "Divorce / QDRO");
  return `<div class="holdings planning-levers"><h3 class="group-title">Strategy Levers</h3><p class="small"><button class="btn tiny" type="button" data-step-id="planning_workbench">Back to Planning Workbench</button></p><p class="small">Estimates assume all other inputs stay fixed. Change the test amount to resize any estimate without affecting your plan. Use the Source column beside each lever to jump to the page where the actual plan value is changed, then rebuild to confirm the real effect.</p><div class="feature-grid optimizer-hub" style="margin:10px 0 14px"><div class="feature-card"><h3>Strategy · decide</h3><div class="pane-actions">${decideButtons}${otherDecideButtons}</div></div><div class="feature-card"><h3>Stress tests · resilience</h3><div class="pane-actions">${resilienceButtons}</div></div></div><div class="ytd-status-grid"><div class="pill"><b>Current terminal NW</b><span>${fmtMoney(b.terminal)}</span></div><div class="pill" title="Post-Tax Inheritance: terminal net worth minus the embedded taxes heirs would owe on pre-tax accounts and unrealized gains — what beneficiaries actually keep."><b>Post-Tax Inheritance (PTI)</b><span>${Number.isFinite(b.pti) ? fmtMoney(b.pti) : "—"}</span></div><div class="pill"><b>Lifetime taxes</b><span>${Number.isFinite(b.lifetime_tax) ? fmtMoney(b.lifetime_tax) : "—"}</span></div><div class="pill"><b>Current success rate</b><span>${fmtPct(b.success)}</span></div><div class="pill"><b>Core annual spending</b><span>${fmtMoney(b.spend)}</span></div><div class="pill"><b>Earned income assumption</b><span>${fmtMoney(b.earned)}</span></div></div><div class="section-note small" style="margin:4px 0 10px"><b>TNW</b> = Terminal Net Worth (projected portfolio at end of plan horizon) · <b>PTI</b> = Post-Tax Inheritance (TNW minus embedded taxes heirs would owe) · <b>Success rate</b> = Monte Carlo trials where the plan maintains the reserve floor through the planning horizon</div><div><div><h3>Ranked by estimated TNW lift</h3><div class="lot-table-wrap"><table class="lot-table planning-lever-table"><thead><tr><th>Focus</th><th>Lever</th><th>Source</th><th>Test amount</th><th>Est. Δ TNW</th><th>Est. Δ success</th></tr></thead><tbody>${tnw.map(tr).join("")}</tbody></table></div></div><div><h3>Ranked by estimated success lift</h3><div class="lot-table-wrap"><table class="lot-table planning-lever-table"><thead><tr><th>Focus</th><th>Lever</th><th>Source</th><th>Test amount</th><th>Est. Δ TNW</th><th>Est. Δ success</th></tr></thead><tbody>${suc.map(tr).join("")}</tbody></table></div></div></div><p class="section-note">After ranking, use the Source button beside a lever to change the actual input → rebuild → check Build History to see the measured effect on projected net worth and success rate.</p></div>`;
}

export function renderWorkbenchLeverEditorHtml() {
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

export function allocationModeIsComputed(mode) {
  return (mode || allocationSelectionMode()) !== "user_target";
}

export function setAllocationSelectionMode(mode) {
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

export function allocationModeHtml() {
  const mode = allocationSelectionMode();
  const modeButtons = [
    ["user_target", "Use user-specified allocation"],
    ["optimizer_recommendation", "Use allocation optimizer recommendation"],
    ["max_sharpe", "Best risk-adjusted mix within your risk limits (max-Sharpe, risk-budgeted)"],
    ["tangency", "Best risk-adjusted mix with no risk limits applied (max-Sharpe, pure tangency)"],
    ["real_loss_aware", "Match each dollar to when you’ll spend it, minimizing the chance of a loss after inflation"],
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

export function allocationOptimizerRecommendationHtml() {
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

export function alternateAssetRows() {
  return rows
    .filter(isEditable)
    .filter(
      (r) =>
        r.section === "Asset Class Optimizer Controls" &&
        norm(r.subsection) !== "global" &&
        norm(r.label) === "alternate_asset_class",
    );
}

export function assetClassNamesForAllocation() {
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

export function findAssetRow(assetClass, labels) {
  const key = norm(assetClass);
  return rows.find(
    (r) =>
      isEditable(r) &&
      r.section === "Asset Class Optimizer Controls" &&
      norm(r.subsection) === key &&
      labels.includes(norm(r.label)),
  );
}

export function setSelectionAction(idx, value) {
  editValue(idx, value, null);
  renderMain();
}

export function selectionActionSelect(row, assetClass) {
  if (!row) return '<span class="small">Missing row</span>';
  const val = rowActionValue(row);
  return `<select aria-label="Selection action for ${esc(assetClass)}" onchange="setSelectionAction(${row.row_index},this.value)"><option value="include" ${val === "include" ? "selected" : ""}>Include</option><option value="exclude" ${val === "exclude" ? "selected" : ""}>Exclude</option><option value="consider_alternate_first" ${val === "consider_alternate_first" ? "selected" : ""}>Consider alternate first</option></select>`;
}

export function normalizedAssetSourceName(x) {
  return String(x || "")
    .trim()
    .replace(/\s+/g, " ");
}

export function addAltOption(list, name, group) {
  name = normalizedAssetSourceName(name);
  if (!name) return;
  if (!list.some((o) => norm(o.name) === norm(name)))
    list.push({ name, group });
}

export function alternateAssetSourceOptions() {
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

export function alternateSelect(row, assetClass, action) {
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

export function targetPctInput(row, assetClass, action) {
  if (!row) return '<span class="small">Missing target row</span>';
  const disabled = action === "exclude" ? " disabled" : "";
  const label = "Target percent for " + assetClass;
  return `<input class="tiny" type="text" value="${esc(displayValueForInput(row, valOf(row)))}" aria-label="${esc(label)}" oninput="editValue(${row.row_index},this.value,this)" onfocus="beginEdit(${row.row_index},this)" onblur="finishEdit(${row.row_index},this)"${disabled}>`;
}

export function fmtPctCell(value) {
  const n = Number(value || 0);
  if (!Number.isFinite(n) || Math.abs(n) < 0.0000001)
    return '<span class="small">0.00%</span>';
  return (n * 100).toFixed(2) + "%";
}

export function optimizerPreviewTarget(asset, kind) {
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

export function activeOptimizerUsedTarget(asset) {
  const p = allocationPreview || {};
  const key = norm(asset);
  const src = p.selected_liquid_targets || {};
  for (const [k, v] of Object.entries(src)) {
    if (norm(k) === key) return Number(v || 0);
  }
  return optimizerPreviewTarget(asset, "liquid");
}

export function optimizerPreviewStatusCell(asset, action) {
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

export function renderOptimizerPreviewNote() {
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

export function renderAssetClassSelectionTable() {
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

export function allocationPolicyRows() {
  return rows.filter(isEditable).filter((r) => {
    const sec = r.section,
      sub = norm(r.subsection);
    return (
      (sec === "Model Constants" && sub === "allocation") ||
      (sec === "Asset Class Assumptions" && sub === "global")
    );
  });
}

export function optimizerOverrideTotalHtml() {
  const total = optimizerOverrideTotalPct();
  const used = optimizerOverrideHasEntries();
  const ok = !used || Math.abs(total - 100) <= 0.01;
  return `<div class="section-note" id="optimizerOverrideTotal"><b>Optimizer override total:</b> ${used ? total.toFixed(2) + "%" : "blank — computed optimizer target will be used"} ${ok ? "✓" : "— must equal 100.00% when any optimizer override is entered."}</div>`;
}

export function classKey(row) {
  return norm(row?.subsection || "");
}

export function copyOptimizerOverrideToUserTargets() {
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

export function renderCurrentAllocationModeNote() {
  return allocationModeHtml();
}

export function renderHoldingPeriodSettingsHtml() {
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

export function renderRealLossAwareTuningHtml() {
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

export function renderOptimizerOverrideTable() {
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

export function allocationCoverageCalloutHtml() {
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

export function renderTotalWealthAllocationHtml() {
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

export function renderOptimizerAllocationPanel() {
  let html = `<div class="holdings"><h3 class="group-title">Optimizer recommendation active</h3>${allocationOptimizerRecommendationHtml()}<div class="section-note">The table above controls which asset classes the optimizer may use and whether existing holdings satisfy a sleeve before new trades are recommended. Override percentages below lock a specific target, bypassing the optimizer.</div></div>`;
  html += renderOptimizerOverrideTable();
  return html;
}

export function renderMaxSharpeAllocationPanel() {
  return `<div class="holdings"><h3 class="group-title">Max-Sharpe (risk-budgeted) recommendation active</h3><div class="section-note">Keeps the same risk level as the allocation optimizer recommendation (risk tolerance/auto risk score, glide path, guaranteed-income/home-equity coverage), but chooses the equity sleeve's sub-class weights to maximize the sleeve's own Sharpe ratio (return in excess of the risk-free rate, per unit of volatility) instead of a fixed risk-aversion utility. The sleeve's candidate classes are driven by the Selection column below: a class set to Exclude never enters it, and a class set to Consider alternate first and mapped to a covered source (guaranteed income, home equity, ...) is left out once that source meets the target &mdash; so large annuities/home equity already covering the bond/real-estate sleeves keeps this scoped to the classes it doesn't already decide. It does not itself re-optimize the equity/bond/cash split, and does not support a manual override.</div>${allocationOptimizerRecommendationHtml()}</div>`;
}

export function renderTangencyAllocationPanel() {
  return `<div class="holdings"><h3 class="group-title">Pure tangency recommendation active</h3><div class="section-note warn"><b>No risk budget:</b> this solves for the single long-only portfolio, across the enabled/uncovered asset classes, with the highest possible Sharpe ratio. It still respects the Selection column below: Excluded classes are never candidates, and a class set to Consider alternate first and mapped to a covered source (guaranteed income, home equity, ...) is left out once that source meets the target &mdash; so if this household's annuities/home equity already cover the bond/real-estate sleeves, tangency is automatically scoped to the remaining liquid classes, driven by that configuration rather than a fixed list. Risk tolerance and glide path are not applied, and it does not support a manual override. It can concentrate heavily in a single class depending on the configured capital-market assumptions &mdash; review it as an analytical reference before using it to drive the plan.</div></div>`;
}

export function renderRealLossAwarePanel() {
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

export function renderAllocationRecommendation() {
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

export function orderedRowsByLabel(labels) {
  return labels.map(rowByNormLabel).filter(Boolean);
}

export function rothPolicyValue() {
  const r = rowByNormLabel("roth_conversion_policy");
  return String(r ? valOf(r) : "optimize_terminal_tax")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_");
}

export function irmaaModeValue() {
  const r = rowByNormLabel("irmaa_guardrail_mode");
  return String(r ? valOf(r) : "AVOID_NEXT_TIER")
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, "_");
}

export function renderRothRows(title, description, rs, open = false) {
  if (!rs.length) return "";
  return `<details class="roth-section"><summary>${esc(title)}</summary><div class="field-list"><div class="section-note">${esc(description)}</div>${sortRowsByDependency(rs).map(fieldHtml).join("")}</div></details>`;
}

export function renderRothMissingNotice() {
  const present = new Set(
    rowsForStep("roth_conversion").map((r) => norm(r.label)),
  );
  const missing = ["roth_conversion_policy", "max_conversion_years"].filter(
    (x) => !present.has(norm(x)),
  );
  if (!missing.length) return "";
  return `<div class="missing-list"><h3>Roth controls need to be backfilled</h3><p>The page is missing ${missing.length} primary control${missing.length === 1 ? "" : "s"}: ${missing.map(humanLabel).join(", ")}. Reload the current plan or start the app again; v11 now backfills these rows into client_policy.csv without overwriting existing values.</p></div>`;
}

export function ssClaimAgeCoordinationSummaryHtml() {
  const parts = [
    { key: "Member 1", n: 1 },
    { key: "Member 2", n: 2 },
  ]
    .map((p) => {
      // ssPersonRows() fetches claim_date (claim_age was replaced -- see
      // schema.csv); derive the age the same way the compact table's own
      // badge does, so this summary never disagrees with what's shown there.
      const claim = ssPersonRows(p.key).find(
        (x) => norm(x.label) === "claim_date",
      );
      const age = claim ? ssClaimAgeFromDate(p.key, claim) : 0;
      return age ? `${personDisplayName(p.n)}: age ${age}` : null;
    })
    .filter(Boolean);
  const claimText = parts.length
    ? `Social Security claim ages — ${esc(parts.join(" · "))}`
    : "Social Security claim ages are not yet set";
  return `<div class="section-note coordination-summary">${claimText} <button class="btn tiny" type="button" data-step-id="income_work">Open Work Income &rarr;</button> <button class="btn tiny" type="button" data-step-id="income_retirement">Open SS, Pensions, &amp; Annuities &rarr;</button></div>`;
}

export function renderRothConversion() {
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
  // Item 2.20 (U4): read-only coordination card -- this page's own help
  // text tells the user to model conversion timing jointly with work
  // income and Social Security claiming, both on distant pages. Surface
  // each person's claim age inline instead of making that a round trip.
  let html = ssClaimAgeCoordinationSummaryHtml();
  html += renderRothMissingNotice();
  // Ticket 289: disclose two Roth Conversion Modeling Guide levers this engine
  // does not implement. Gated on the ABSENCE of a row for either future
  // plan-data key, so building the lever removes its own disclosure -- see
  // the matching gate in sheets_strategy.py's Conversion Strategy notes.
  if (
    !rowByNormLabel("roth_conversion_tax_source") &&
    !rowByNormLabel("roth_conversion_asset_location_aware")
  ) {
    html += `<div class="section-note">This model does not yet choose <b>how</b> conversion taxes are paid (taxable cash vs. withholding from the IRA) or preferentially convert higher-growth holdings inside the IRA first (asset-location-aware conversion). Both apply the same conversion mechanics either way; see the workbook's Roth Conversion sheet for the full disclosure.</div>`;
  }
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
      : policyIsOptimizer
        ? 'To actually change behavior, changing Roth Conversion Policy away from optimize terminal tax is the blunt instrument. To keep auto-optimization but bias its search, use Roth Bracket Strategy. To keep the full search but change which candidate "wins" a close race, use Roth Objective Mode — and note it does nothing unless Roth Conversion Policy is left at optimize terminal tax.'
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

export function renderDistributionStrategy() {
  return `<div class="tabbed-workspace strategy-workspace"><div class="workspace-tab-body">${renderPlanningLevers()}</div></div>`;
}

// Every export above is also re-attached to window: dashboard.js calls these
// as bare globals, and this file's own rendered HTML uses inline
// onclick="..." handlers, which always resolve through window regardless of
// module scoping. New code should prefer `import` from this module; this
// bridge exists only for callers that cannot move to import in the same pass.
Object.assign(window, {
  kpiHasValues,
  setPlanningLeverInput,
  planningLeversBaselineReady,
  planningLeversPlaceholder,
  renderPlanningLevers,
  renderWorkbenchLeverEditorHtml,
  allocationModeIsComputed,
  setAllocationSelectionMode,
  allocationModeHtml,
  allocationOptimizerRecommendationHtml,
  alternateAssetRows,
  assetClassNamesForAllocation,
  findAssetRow,
  setSelectionAction,
  selectionActionSelect,
  normalizedAssetSourceName,
  addAltOption,
  alternateAssetSourceOptions,
  alternateSelect,
  targetPctInput,
  fmtPctCell,
  optimizerPreviewTarget,
  activeOptimizerUsedTarget,
  optimizerPreviewStatusCell,
  renderOptimizerPreviewNote,
  renderAssetClassSelectionTable,
  allocationPolicyRows,
  optimizerOverrideTotalHtml,
  classKey,
  copyOptimizerOverrideToUserTargets,
  renderCurrentAllocationModeNote,
  renderHoldingPeriodSettingsHtml,
  renderRealLossAwareTuningHtml,
  renderOptimizerOverrideTable,
  allocationCoverageCalloutHtml,
  renderTotalWealthAllocationHtml,
  renderOptimizerAllocationPanel,
  renderMaxSharpeAllocationPanel,
  renderTangencyAllocationPanel,
  renderRealLossAwarePanel,
  renderAllocationRecommendation,
  orderedRowsByLabel,
  rothPolicyValue,
  irmaaModeValue,
  renderRothRows,
  renderRothMissingNotice,
  ssClaimAgeCoordinationSummaryHtml,
  renderRothConversion,
  renderDistributionStrategy,
});
