// ── Step stats, plan-state banner, unsaved tracking and renderSteps (W4-06): extracted verbatim from row_model ──
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
Object.assign(window, {
  overallStats, planStateArtifactsReady, planStateFresh, refreshBuildStatus, renderSteps,
  reportsUiContext, stepStats, unsavedChangeCount, updatePlanStateBanner, updateUnsaved,
});
