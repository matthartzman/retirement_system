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
  api,
  apiUrl,
  editValue,
  findEditableRow,
  hasAny,
  hasUnsavedPlanChanges,
  helocModuleEnabled,
  homeValueLabelIsCanonical,
  isEditable,
  isMissing,
  isRequired,
  loadAll,
  ltcLifePolicyModuleEnabled,
  norm,
  optionalFunctionEnabled,
  parsePercentInput,
  
  planModuleTaxonomy,
  recAdd,
  rowIsBaseHomeSaleInput,
  rowIsNextHousingMoveInput,
  rowIsCanonicalHomeValue,
  rowIsDivorceScenario,
  rowIsMonteCarlo,
  rowIsRetiredScenarioHomeDuplicate,
  rowIsStressSellHomeInput,
  rowsForStep,
  saveAll,
  saveBeforeStructuralChange,
  saveWorkbookViewState,
  saveWorkingCopy,
  scheduleStatusUpdate,
  section,
  setAppControls,
  setStep,
  showMessage,
  planIndependentSteps,
  shutdownAndClose,
  sourceStepForRow,
  stepTitleById,
  updates,
  valOf,
});
