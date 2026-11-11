// ── Planning levers and build-impact page ──
// Extracted verbatim from dashboard_decomp_row_model.js (W4-06, ARC-005): session-change capture, planning-lever
// rows/base, the planning workbench context and the build-impact page. Bare-global bridge below.
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
  const footer = `<div class="section-note" data-kind="state"><div class="pane-actions"><button class="btn" type="button" data-step-id="planning_levers">Preview impact (Planning overview)</button> <button class="btn good" type="button" onclick="navigateTo('detailed_results')">View full result in workbook</button></div></div>`;
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
    renderScenarios: renderScenarios,
    confirm: function (msg, opts) {
      return showInAppConfirm(msg, opts);
    },
    prompt: function (msg, def, opts) {
      return showInAppPrompt(msg, def, opts);
    },
  };
}

// #<reports-redesign>: split out of renderBuildImpactPage() so Reports &
// Review (which no longer embeds Build/Download/Plan-Data-Review here -- see
// renderReportsAndReview()) can render the actual Impact content without the
// blocks it now renders elsewhere. renderBuildImpactPage() below still
// composes this the same way it always has, so the separate "Impact & Build
// History" step this function also serves is unaffected.
export function unsavedChangesPromptBar() {
  loadBuildHistory();
  if (hasUnsavedPlanChanges() && buildHistory.length > 0)
    return '<div class="section-note warning build-snapshot-prompt" data-kind="warn"><b>You have unsaved changes.</b> Snapshot before rebuilding. <button class="btn" type="button" data-requires-app="1" onclick="takeBuildSnapshot()">Take Snapshot</button></div>';
  return "";
}

// WI-019: the build-warnings banner leads every page that shows the impact section.
export function renderImpactSectionContent() {
  return buildWarningsBannerHtml() + renderImpactSectionBody();
}
function renderImpactSectionBody() {
  loadBuildHistory();
  const headerActions =
    '<div class="pane-actions"><button class="btn" type="button" data-requires-app="1" onclick="takeBuildSnapshot()">Take Snapshot</button> <button class="btn danger" type="button" data-requires-app="1" onclick="revertLastBuildChanges()">Revert User Changes</button></div>';
  if (!buildHistory.length)
    return (
      "<h3>No build history yet</h3><p>Build or download your workbook above to see before/after impact here, or take a snapshot to record the current state.</p>" +
      headerActions
    );
  // #293/#309: four dials read LCV / NPV of Future Taxes / 5th-percentile
  // worst-case ending wealth / EFTR -- the same four headline KPIs as the
  // Build Impact cards -- instead of the retired Terminal Net Worth /
  // Lifetime Tax / Monte Carlo pass-fail probability trio.
  const allNw = buildHistory
    .map((e) => e.kpi && e.kpi.lcv)
    .filter((v) => v !== null && v !== undefined && Number.isFinite(Number(v)))
    .map(Number);
  const allNwAllIn = buildHistory
    .map((e) => e.kpi && e.kpi.lcv_all_in_including_taxes)
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
  const allEftr = buildHistory
    .map((e) => e.kpi && e.kpi.eftr)
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
    nwAllInHeat: heatRange(allNwAllIn, true),
    taxHeat: heatRange(allTax, false),
    mcHeat: heatRange(allMc, true),
    eftrHeat: heatRange(allEftr, false),
  };
  let historyHtml = "";
  buildHistory.forEach(function (entry, idx) {
    historyHtml += buildHistoryEntryHtml(entry, idx === 0, heat);
  });
  const latestImpact =
    planningWorkbenchBuildImpactHtml() + latestBuildImpactHtml(buildHistory[0]);
  return (
    "<h3>Impact " + (window.RPHelp ? window.RPHelp.sectionButtonHtml("reports_and_review.build_impact") : "") + "</h3>" +
    headerActions +
    latestImpact +
    '<details class="build-history-collapsible"><summary class="section-header">Build History (up to ' +
    BUILD_HISTORY_MAX +
    ' builds and snapshots)</summary><div class="build-history-list">' +
    historyHtml +
    "</div></details>"
  );
}

export function renderBuildImpactPage() {
  const promptBar = unsavedChangesPromptBar();
  // #301: Build and Download are buttons on the primary Impact page, not
  // separate tabs -- renderReportsBuild()/renderReview() are the same
  // status+action blocks the old standalone Build/Downloads tabs used.
  const buildAndDownload = renderReportsBuild() + renderReview();
  const planDataReviewSection =
    '<details class="plan-data-review-collapsible"><summary class="section-header">Plan Data Review</summary>' +
    renderPlanDataReport() +
    "</details>";
  return (
    '<div class="build-impact"><div class="impact-panel">' +
    promptBar +
    buildAndDownload +
    renderImpactSectionContent() +
    "</div>" +
    planDataReviewSection +
    "</div>"
  );
}
Object.assign(window, {
  analysisFrame, capturedSessionChanges, planningLeverBase, planningLeverRows,
  planningWorkbenchContext, renderBuildImpactPage, renderImpactSectionContent,
  unsavedChangesPromptBar,
});
