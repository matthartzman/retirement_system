// ── Strategy tab navigation context (strategyTabKey, goToStrategyTab, navigationContext) ──
// Extracted verbatim from dashboard_decomp_row_model.js (W4-06, ARC-005). Bridge below.
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
Object.assign(window, { goToStrategyTab, navigationContext, strategyTabKey });
