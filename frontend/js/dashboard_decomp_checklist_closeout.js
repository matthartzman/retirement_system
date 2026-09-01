// Extracted from dashboard.js by tools/js_codemod/extract_module.mjs.

export function showConfigCardHelp(key) {
  ensureHelpPanelVisible();
  document.getElementById("helpPanel").innerHTML =
    SYSTEM_CONFIG_FIELD_HELP[key] || STEP_HELP.system_configuration;
}

export function recentChangesLogHtml() {
  const changes = [...sessionChanges.values()];
  const specials = [...sessionSpecialChanges];
  if (!changes.length && !specials.length)
    return '<p class="small" style="margin:4px 0;color:var(--muted)">No field changes in this session yet.</p>';
  let html =
    '<div class="recent-changes-log"><table class="change-table"><thead><tr><th>Field</th><th>Source</th><th>Before</th><th>After</th><th></th></tr></thead><tbody>';
  changes.slice(0, 20).forEach((c) => {
    const src = c.sourceStep
      ? `<button class="btn tiny" type="button" data-step-id="${esc(c.sourceStep)}">${esc(c.sourceTitle || c.sourceStep)}</button>`
      : esc(c.group || "—");
    html += `<tr><td>${esc(c.label)}</td><td>${src}</td><td>${esc(c.before || "blank")}</td><td>${esc(c.after || "blank")}</td><td><button class="btn tiny" type="button" onclick="undoSessionFieldChange(${c.row_index})">Undo</button></td></tr>`;
  });
  if (changes.length > 20)
    html += `<tr><td colspan="5" class="small">${changes.length - 20} more changes.</td></tr>`;
  if (specials.length)
    html += `<tr><td colspan="5" class="small"><b>Table edits:</b> ${specials.map((s) => esc(s)).join(", ")}</td></tr>`;
  html += "</tbody></table></div>";
  return html;
}

export function undoSessionFieldChange(rowIndex) {
  const entry = [...sessionChanges.values()].find(
    (c) => c.row_index === Number(rowIndex),
  );
  if (!entry) {
    showMessage("Cannot undo: change not found in this session.", "error");
    return;
  }
  editValue(entry.row_index, entry.beforeStorage || entry.before, null);
  showMessage("Undone: " + entry.label);
  renderMain();
  renderSteps();
}

export function showYtdBlendChoiceModal(summary) {
  return new Promise(function (resolve) {
    const actual = (summary && summary.actual) || {};
    const spend = Number(actual.spending || 0);
    const earned = Number(actual.earned_income || 0);
    const asOf = summary && summary.ytd_end ? summary.ytd_end : "today";
    const parts = [];
    if (spend > 0)
      parts.push(
        "$" +
          spend.toLocaleString(undefined, { maximumFractionDigits: 0 }) +
          " of actual spending",
      );
    if (earned > 0)
      parts.push(
        "$" +
          earned.toLocaleString(undefined, { maximumFractionDigits: 0 }) +
          " of actual earned income",
      );
    const figures = parts.length
      ? parts.join(" and ")
      : "real transaction activity";
    const body =
      "<p>This workspace has " +
      esc(figures) +
      " tracked through <b>" +
      esc(asOf) +
      "</b>, independent of any plan you build here.</p>" +
      "<p><b>Use real actuals (recommended):</b> the new plan's current-year projection blends this real activity in for the remainder of the year — matches how the app models your actual ongoing plan.</p>" +
      '<p><b>Model as fully hypothetical:</b> ignores the real activity above and projects the whole current year from your entered assumptions only — use this for a detached "what-if" scenario that should not inherit real bank/brokerage activity.</p>' +
      '<p class="small">You can change this later from the YTD Account Setup page.</p>';
    const overlay = document.createElement("div");
    overlay.className = "inapp-modal-overlay";
    overlay.innerHTML =
      '<div class="inapp-modal"><b class="inapp-modal-title">New plan and real year-to-date actuals</b><div class="inapp-modal-body">' +
      body +
      '</div><div class="inapp-modal-actions"><button class="btn ytd-choice-cancel" type="button">Cancel</button><button class="btn ytd-choice-hypothetical" type="button">Model as fully hypothetical</button><button class="btn primary ytd-choice-blend" type="button">Use real actuals (recommended)</button></div></div>';
    document.body.appendChild(overlay);
    function close(v) {
      overlay.remove();
      resolve(v);
    }
    overlay.querySelector(".ytd-choice-blend").onclick = function () {
      close("blend");
    };
    overlay.querySelector(".ytd-choice-hypothetical").onclick = function () {
      close("hypothetical");
    };
    overlay.querySelector(".ytd-choice-cancel").onclick = function () {
      close(null);
    };
    overlay.onclick = function (e) {
      if (e.target === overlay) close(null);
    };
    function onKey(e) {
      if (e.key === "Escape") {
        close(null);
        document.removeEventListener("keydown", onKey);
      }
    }
    document.addEventListener("keydown", onKey);
    setTimeout(function () {
      const b = overlay.querySelector(".ytd-choice-blend");
      if (b) b.focus();
    }, 30);
  });
}

export function nbaPanelHtml() {
  let state,
    msg,
    action,
    cls = "nba-panel";
  if (!planLoaded) {
    state = "No plan loaded";
    msg =
      "Use Start New Plan or load a saved plan from the welcome page below to begin.";
    action = "";
    cls += " nba-idle";
  } else {
    const unsaved = unsavedChangeCount();
    const stats = overallStats();
    const artifacts = planStateArtifactsReady();
    const fresh = planStateFresh();
    const p = buildPreflight || {};
    if (unsaved) {
      state = "Unsaved changes";
      msg =
        unsaved +
        " pending change" +
        (unsaved === 1 ? "" : "s") +
        " — save before rebuilding.";
      action =
        '<button class="btn primary" type="button" data-requires-app="1" onclick="saveAll(true)">Save Changes</button>';
      cls += " nba-warn";
    } else if (stats.missing && stats.missing.length) {
      const n = stats.missing.length;
      state = "Required fields missing";
      msg =
        n +
        " required field" +
        (n === 1 ? " is" : " are") +
        " blank — complete before building advisor-ready reports.";
      action =
        '<button class="btn" type="button" data-step-id="all_assumptions">Review Fields</button>';
      cls += " nba-warn";
    } else if (!artifacts) {
      state = "Ready to build";
      msg =
        "All required fields are complete. Build outputs to generate the workbook and results.";
      action =
        '<button class="btn primary" type="button" data-requires-app="1" onclick="runBuild(false)">Build Reports</button>';
      cls += " nba-action";
    } else {
      const wbMtime = ((p.artifacts || {}).workbook || {}).mtime;
      const daysSince = wbMtime ? (Date.now() / 1000 - wbMtime) / 86400 : null;
      if (daysSince !== null && daysSince > 30) {
        const d = Math.round(daysSince);
        state = "Reports are stale";
        msg =
          "Last build was " +
          d +
          " day" +
          (d === 1 ? "" : "s") +
          " ago — rebuild to reflect any recent changes.";
        action =
          '<button class="btn primary" type="button" data-requires-app="1" onclick="runBuild(false)">Rebuild</button>';
        cls += " nba-warn";
      } else if (!fresh) {
        state = "Plan changed since last build";
        msg =
          "Plan data was saved after the last build — rebuild to keep reports current.";
        action =
          '<button class="btn primary" type="button" data-requires-app="1" onclick="runBuild(false)">Rebuild</button>';
        cls += " nba-warn";
      } else {
        state = "Reports are current";
        msg =
          "Plan is saved, required fields complete, and reports match the latest build.";
        action =
          '<button class="btn" type="button" data-step-id="detailed_results">View Results</button> <button class="btn" type="button" data-step-id="reports_and_review">Download</button>';
        cls += " nba-ok";
      }
    }
  }
  return (
    '<div class="' +
    cls +
    '"><div class="nba-status">' +
    esc(state) +
    '</div><div class="nba-message">' +
    esc(msg) +
    '</div><div class="nba-action">' +
    action +
    "</div></div>"
  );
}

export function renderWelcome() {
  var _autoLoad = _autoLoadPref !== null ? _autoLoadPref : false;
  try {
    if (_autoLoadPref === null)
      _autoLoad = localStorage.getItem("rpAutoLoad") === "1";
  } catch (_e) {}
  return `<div class="pane-head"><div class="eyebrow">Welcome</div><h2>Retirement planning workspace</h2><p>Enter source facts first, then model strategy and stress tests, build reports, and review the workbook results.</p>${demoModeActive ? '<div class="section-note" style="margin:6px 0">Viewing the demo plan (Alex &amp; Morgan). Your real plan is backed up — click <b>Open Current Plan</b> to switch back. Edits you make here are kept for next time you open the demo; on desktop, <b>Save Plan As</b> also lets you keep a named copy.</div>' : ""}<div class="pane-actions"><button class="btn primary" data-requires-app="1" onclick="startNewPlan()">Start New Plan</button><button class="btn" data-requires-app="1" onclick="openCurrentPlan()">Open Current Plan</button><button class="btn" data-requires-app="1" onclick="openDemoPlan()">Open Demo Plan</button>${demoModeActive ? "" : '<button class="btn" onclick="resetDemoToDefaults()">Reset Demo to Defaults</button>'}<button class="btn" onclick="savePlanAs()">Save Plan As</button><button class="btn" onclick="loadSavedPlan()">Load Saved Plan</button></div><div style="margin:8px 0 4px;font-size:13px"><label style="cursor:pointer;user-select:none"><input type="checkbox" id="autoLoadCheck"${_autoLoad ? " checked" : ""} onchange="setAutoLoad(this.checked)"> Auto-load plan on next start</label></div></div>${nbaPanelHtml()}${taxFreshnessBannerHtml()}${planKpiMetricsHtml()}${firstRunChecklistHtml(false)}<div class="feature-grid"><div class="feature-card"><h3>Your plan</h3><ul><li><b>The saved plan</b> is the active source for all projections.</li><li><b>Plan Data files</b> can be exported for backup, sharing, or recovery.</li><li><b>Reports</b> are generated snapshots — edit the plan, then rebuild to update them.</li></ul></div><div class="feature-card"><h3>Save and build</h3><ul><li><b>Save Changes</b> stores ordinary fields, tables, category budgets, transaction edits, holdings, liabilities, and strategy-table edits.</li><li><b>Build Reports</b>, <b>Download Workbook</b>, and <b>Download PDF</b> save first, run preflight, then rebuild reports.</li><li>Use page-level reload buttons only when discarding unsaved page edits.</li></ul></div><div class="feature-card"><h3>Spending flow</h3><ul><li>Spending Categories defines the Tracking Type, Group, and Category model.</li><li>Housing, Wellness, and Travel are authoritative detail pages.</li><li>Income &amp; Expense Transactions feeds Spending Analysis and actual-vs-model review.</li></ul></div><div class="feature-card"><h3>Final review</h3><ol class="small"><li>Open Reports &amp; Review.</li><li>On the Build tab, check the readiness block above the Build button for missing fields, and resolve any blockers.</li><li>Build Reports.</li><li>Review Impact and Results, then download the workbook.</li></ol></div></div>${closeoutChecklistHtml()}`;
}

export function renderSystemConfiguration() {
  return `<div class="system-config-panel"><div class="section-note">Maintenance utilities for this workspace — pricing snapshots, backups, CSV export, the recent-change log, and the raw System Configuration Console. Plan assumptions, optional modules, the field finder, and workbook formatting are now pages in the left nav under Settings.</div><section class="system-config-section"><div class="system-config-grid"><div class="feature-card" tabindex="0" onclick="showConfigCardHelp('pricing_mode')" onfocus="showConfigCardHelp('pricing_mode')"><h3>Pricing mode</h3><p class="small">Check live/cache/fallback pricing status, refresh live quotes when the cache looks stale, then freeze a saved price snapshot when reports need reproducible advisor values.</p><button class="btn" type="button" data-step-id="build_impact" onfocus="event.stopPropagation();showConfigCardHelp('pricing_mode')">Open Build History</button> <button class="btn primary" type="button" onclick="event.stopPropagation();refreshLivePrices()" onfocus="event.stopPropagation();showConfigCardHelp('pricing_mode')">Refresh Prices</button> <button class="btn" type="button" onclick="event.stopPropagation();freezePricingSnapshot()" onfocus="event.stopPropagation();showConfigCardHelp('pricing_mode')">Freeze latest prices</button> <button class="btn" type="button" onclick="event.stopPropagation();unfreezePricingSnapshot()" onfocus="event.stopPropagation();showConfigCardHelp('pricing_mode')">Unfreeze prices</button></div>${localBackupControlsHtml()}<div class="feature-card" tabindex="0" onclick="showConfigCardHelp('session_changes')" onfocus="showConfigCardHelp('session_changes')"><h3>Session changes</h3>${recentChangesLogHtml()}</div><div class="feature-card" tabindex="0" onclick="showConfigCardHelp('system_config_console')" onfocus="showConfigCardHelp('system_config_console')"><h3>System configuration console</h3><p class="small">Maintain pricing providers, build timeout, tax constants, reference files, diagnostics, and raw system configuration rows. Opens as its own page.</p><button class="btn primary" type="button" onclick="event.stopPropagation();openSystemConfigurationConsole()" onfocus="event.stopPropagation();showConfigCardHelp('system_config_console')">Open System Configuration Console</button></div><div class="feature-card" tabindex="0" onclick="showConfigCardHelp('annualized_actuals')" onfocus="showConfigCardHelp('annualized_actuals')"><h3>Annualized actuals</h3><p class="small">Re-baseline the plan by overwriting <b>every</b> category budget with its annualized current-year spend. New transaction categories are merged into the taxonomy. Bulk overwrite with no undo — export a backup first.</p><button class="btn" type="button" onclick="event.stopPropagation();loadAnnualizedActuals()" onfocus="event.stopPropagation();showConfigCardHelp('annualized_actuals')">Load annualized current spend</button></div><div class="feature-card" tabindex="0" onclick="showConfigCardHelp('csv_backup')" onfocus="showConfigCardHelp('csv_backup')"><h3>CSV backup</h3><p class="small">Export a CSV backup of holdings, transactions, target allocations, and reference data for recovery or external review.</p><button class="btn" type="button" onclick="event.stopPropagation();exportCsvBackup()" onfocus="event.stopPropagation();showConfigCardHelp('csv_backup')">Export CSV backup</button></div></div></section></div>`;
}

export async function refreshLivePrices() {
  try {
    showMessage("Refreshing prices from live providers...");
    const out = await api("/api/prices/refresh", {
      method: "POST",
      body: JSON.stringify({}),
    });
    const r = out.result || {};
    const resolved = Number(r.prices_resolved || 0);
    const requested = Number(r.symbols_requested || 0);
    const live = Number(r.live_prices_resolved || 0);
    showMessage(
      out.success
        ? `Prices refreshed: ${live} live quote${live === 1 ? "" : "s"}, ${resolved}/${requested} symbols resolved.`
        : "Price refresh completed with warnings — open Build History or pricing diagnostics to review.",
      out.success ? "success" : "error",
    );
    buildPreflight = null;
    await refreshPreflightForReview();
  } catch (e) {
    showMessage(
      "Price refresh failed: " + (e && e.message ? e.message : e),
      "error",
    );
  }
}

export async function freezePricingSnapshot() {
  try {
    const out = await api("/api/prices/freeze", {
      method: "POST",
      body: JSON.stringify({}),
    });
    showMessage(
      `Frozen pricing snapshot with ${Number(out.symbol_count || 0)} symbol${Number(out.symbol_count || 0) === 1 ? "" : "s"}.`,
      "success",
    );
    buildPreflight = null;
    await refreshPreflightForReview();
  } catch (e) {
    showMessage(
      "Pricing freeze failed: " + (e && e.message ? e.message : e),
      "error",
    );
  }
}

export async function unfreezePricingSnapshot() {
  try {
    await api("/api/prices/unfreeze", {
      method: "POST",
      body: JSON.stringify({}),
    });
    showMessage(
      "Pricing snapshot freeze removed. Future builds will use the configured pricing mode.",
      "success",
    );
    buildPreflight = null;
    await refreshPreflightForReview();
  } catch (e) {
    showMessage(
      "Pricing unfreeze failed: " + (e && e.message ? e.message : e),
      "error",
    );
  }
}

export function exportCsvBackup() {
  const url = "/api/admin/csv-backup";
  showMessage("Exporting CSV backup...");
  if (window.__is_desktop_app__) {
    fetch(apiUrl(url))
      .then(function (r) {
        return r.json ? r.json() : r;
      })
      .then(function (out) {
        if (out && out.success === false)
          showMessage(
            "CSV backup failed: " + (out.error || "unknown error"),
            "error",
          );
        else showMessage("CSV backup exported.", "success");
      })
      .catch(function (e) {
        showMessage(
          "CSV backup error: " + (e && e.message ? e.message : e),
          "error",
        );
      });
    return;
  }
  window.location.href = apiUrl(url);
}

export function openSystemConfigurationConsole() {
  if (window.__is_desktop_app__) {
    // Call the pywebview bridge directly instead of relying on
    // location.href interception: WebView2/EdgeChromium does not always
    // allow pywebview_bridge.js to override Location.prototype.href (see
    // the try/catch there), so that path can silently fall through to a
    // real file:// navigation to a URL that doesn't exist on disk.
    if (window.pywebview && window.pywebview.api) {
      window.pywebview.api.navigate("/system-configuration");
    } else {
      window.addEventListener(
        "pywebviewready",
        function () {
          window.pywebview.api.navigate("/system-configuration");
        },
        { once: true },
      );
    }
    return;
  }
  location.href = "/system-configuration";
}

export function setAutoLoad(v) {
  try {
    localStorage.setItem("rpAutoLoad", v ? "1" : "0");
  } catch (_e) {}
  // Also persist server-side so the preference survives WebView2 session resets.
  fetch("/api/prefs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rpAutoLoad: v }),
  }).catch(function () {});
}

export function checklistItemStatus(stepIds) {
  if (!planLoaded) return { cls: "todo", label: "Open plan" };
  let missing = 0,
    required = 0,
    dirtyCount = 0;
  stepIds.forEach((id) => {
    const st = stepStats(id);
    missing += st.missing.length;
    required += st.required.length;
    dirtyCount += st.dirty.length;
  });
  if (dirtyCount) return { cls: "warn", label: "Edited" };
  if (missing) return { cls: "warn", label: missing + " missing" };
  if (required) return { cls: "done", label: "Ready" };
  return { cls: "todo", label: "Optional" };
}

export function firstRunChecklistHtml(compact = false) {
  const items = [
    {
      title: "Household foundation",
      desc: "People, dates, filing status, state, retirement timing, and planning horizon.",
      steps: ["household_people"],
      next: "household_people",
    },
    {
      title: "Income",
      desc: "Work income, Social Security, pensions, annuities, and retirement income streams.",
      steps: ["income_work", "income_retirement"],
      next: "income_work",
    },
    {
      title: "Spending and actuals",
      desc: "Categories, housing, Wellness, travel, large discretionary items, and current-year transactions.",
      steps: [
        "spending_core",
        "retirement_wellness",
        "spending_mortgage_events",
        "spending_travel",
        "spending_travel_extras",
        "ytd_transactions",
        "spending_dashboard",
      ],
      next: "spending_core",
    },
    {
      title: "Assets and protection",
      desc: "Holdings, cash reserves, annuity death benefits, life insurance, other assets, liabilities, and estate inputs.",
      steps: [
        "holdings",
        "assets_home_cash",
        "annuity_death_benefits",
        "assets_special",
        "estate",
      ],
      next: "holdings",
    },
    {
      title: "Strategy",
      desc: "Distribution strategy, investment strategy, state residency analysis, and optional advanced strategies.",
      steps: [
        "planning_levers",
        "roth_conversion",
        "allocation_assets",
        "allocation_policy",
        "withdrawal_strategy",
        "state_residency",
        "heloc_strategy",
        "entity_charitable",
      ],
      next: "distribution_strategy",
    },
    {
      title: "Stress tests",
      desc: "Monte Carlo, survivor, long-term care, and optional divorce/QDRO stress.",
      steps: [
        "monte_carlo_options",
        "survivor_stress",
        "ltc_stress",
        "divorce_options",
      ],
      next: "monte_carlo_options",
    },
    {
      title: "Review and build",
      // Item 2.19 (finding U6): "Run preflight, build reports, ..." used to
      // describe Preflight as its own step before this checklist card
      // rendered on the Build tab too (it previously only appeared on the
      // now-retired separate Preflight tab). Rewritten for the merged flow
      // -- also avoids an accessible-name collision: this card's text
      // containing the substring "build reports" made Playwright's
      // getByRole('button', {name:'Build Reports'}) in the E2E suite match
      // this card instead of the real Build Reports button once both
      // rendered on the same tab (tests/e2e/helpers.js's
      // triggerBuildAndWaitForOverlay).
      desc: "Check readiness, run the build, review impact and results, and download the final workbook.",
      steps: ["review", "build_impact", "detailed_results", "plan_data_report"],
      next: "reports_and_review",
    },
  ];
  let html = `<div class="first-run-checklist ${compact ? "compact" : ""}"><div class="first-run-head"><div><h3>${compact ? "Workflow checklist" : "Recommended workflow"}</h3><p class="small">A low-risk path through the plan: enter source data first, then strategy, stress tests, build, and review.</p></div>${compact ? "" : '<button class="btn primary" type="button" data-step-id="reports_and_review">Review and Build</button>'}</div><div class="first-run-items">`;
  items.forEach((item) => {
    const st = checklistItemStatus(item.steps);
    html += `<button class="first-run-item ${st.cls}" type="button" data-step-id="${esc(item.next)}"><span class="check-status">${esc(st.label)}</span><b>${esc(item.title)}</b><small>${esc(item.desc)}</small></button>`;
  });
  html += "</div></div>";
  return html;
}

export async function savePlanAs() {
  if (!window.pywebview) {
    showMessage("File dialogs require the desktop app.", "error");
    return;
  }
  try {
    const result = await window.pywebview.api.show_save_dialog("myplan.rpx");
    if (!result || result.cancelled) return;
    if (hasUnsavedPlanChanges()) {
      showMessage("Saving current changes before exporting...");
      const ok = await saveWorkingCopy();
      if (!ok) {
        showMessage(
          "Could not save current changes before exporting. Plan file not saved.",
          "error",
        );
        return;
      }
    }
    const resp = await api("/api/plan/save-as", {
      method: "POST",
      body: JSON.stringify({ path: result.path }),
    });
    if (resp && resp.success) showMessage("Plan saved to: " + result.path);
    else
      showMessage(
        "Save failed: " + ((resp && resp.error) || "unknown error"),
        "error",
      );
  } catch (e) {
    showMessage("Error saving plan: " + e.message, "error");
  }
}

export async function openDemoPlan() {
  if (hasUnsavedPlanChanges()) {
    const choice = await showSaveDiscardStayModal(
      "You have unsaved changes. Save them before opening the demo plan, discard them, or stay here?",
      { title: "Open Demo Plan" },
    );
    if (choice === "stay") return;
    if (choice === "save") {
      const ok = await saveAll(true);
      if (!ok) return;
    }
  }
  if (
    !(await showInAppConfirm(
      'This swaps in a fictional demo household (Alex & Morgan) so you can explore the app. Your real plan is backed up automatically — use "Open Current Plan" to switch back anytime.',
      { title: "Open Demo Plan", confirmLabel: "Open Demo Plan", variant: "warn" },
    ))
  )
    return;
  try {
    const resp = await api("/api/plan/open-demo", {
      method: "POST",
      body: JSON.stringify({}),
    });
    if (resp && resp.success) {
      showMessage("Demo plan loaded.", "success");
      await loadAll({ source: "Demo plan", preferLocal: false });
      renderMain();
    } else
      showMessage(
        "Could not open demo plan: " + ((resp && resp.error) || "unknown error"),
        "error",
      );
  } catch (e) {
    showMessage("Error opening demo plan: " + e.message, "error");
  }
}

export async function openCurrentPlan() {
  try {
    if (demoModeActive) {
      const resp = await api("/api/plan/restore-current", {
        method: "POST",
        body: JSON.stringify({}),
      });
      if (!resp || !resp.success) {
        showMessage(
          "Could not restore your plan: " + ((resp && resp.error) || "unknown error"),
          "error",
        );
        return;
      }
      if (resp.restored) showMessage("Your plan is back.", "success");
    }
    await loadAll({ source: "Local database", preferLocal: false });
    renderMain();
  } catch (e) {
    showMessage("Error opening current plan: " + e.message, "error");
  }
}

export async function resetDemoToDefaults() {
  if (demoModeActive) {
    showMessage("Close the demo (Open Current Plan) before resetting it.", "error");
    return;
  }
  if (
    !(await showInAppConfirm(
      "This deletes any edits saved in the demo and resets it to the shipped Alex & Morgan fixtures. This cannot be undone.",
      { title: "Reset Demo to Defaults", confirmLabel: "Reset Demo", variant: "warn" },
    ))
  )
    return;
  try {
    const resp = await api("/api/plan/reset-demo", {
      method: "POST",
      body: JSON.stringify({}),
    });
    if (resp && resp.success) showMessage("Demo reset to defaults.", "success");
    else
      showMessage(
        "Could not reset demo: " + ((resp && resp.error) || "unknown error"),
        "error",
      );
  } catch (e) {
    showMessage("Error resetting demo: " + e.message, "error");
  }
}

export async function loadSavedPlan() {
  if (hasUnsavedPlanChanges()) {
    const choice = await showSaveDiscardStayModal(
      "You have unsaved changes. Save them before loading a different plan, discard them, or stay here?",
      { title: "Load Saved Plan" },
    );
    if (choice === "stay") return;
    if (choice === "save") {
      const ok = await saveAll(true);
      if (!ok) return;
    }
  }
  if (!window.pywebview) {
    showMessage("File dialogs require the desktop app.", "error");
    return;
  }
  if (
    !(await showInAppConfirm(
      "This replaces the current plan in the local database.",
      { title: "Load Saved Plan", confirmLabel: "Load Plan", variant: "warn" },
    ))
  )
    return;
  try {
    const result = await window.pywebview.api.show_open_dialog();
    if (!result || result.cancelled) return;
    const resp = await api("/api/plan/load-file", {
      method: "POST",
      body: JSON.stringify({ path: result.path }),
    });
    if (resp && resp.success) {
      showMessage("Plan loaded from " + result.path);
      await loadAll({ source: "Loaded from file", preferLocal: false });
      renderMain();
    } else
      showMessage(
        "Load failed: " + ((resp && resp.error) || "unknown error"),
        "error",
      );
  } catch (e) {
    showMessage("Error loading plan: " + e.message, "error");
  }
}

export async function loadTaxFreshnessStatus() {
  if (taxFreshnessLoading || taxFreshnessData) return;
  taxFreshnessLoading = true;
  try {
    const out = await api("/api/admin/tax-law-dashboard");
    taxFreshnessData = out;
  } catch (e) {
    taxFreshnessData = { success: false, rows: [] };
  }
  taxFreshnessLoading = false;
  renderMain();
}

export function taxFreshnessBannerHtml() {
  if (!taxFreshnessData) {
    if (!taxFreshnessLoading) setTimeout(loadTaxFreshnessStatus, 0);
    return "";
  }
  const rows = (taxFreshnessData.rows || []).filter((r) => {
    const status = String(r.status || "").toUpperCase();
    if (status.includes("UNTIL_LAW_CHANGE")) return false;
    return r.blocking || status.includes("STALE") || status.includes("REVIEW");
  });
  if (!rows.length) return "";
  const items = rows
    .slice(0, 6)
    .map(
      (r) =>
        `<li><b>${esc(r.constant || "")}</b> (${esc(r.category || "")}) — last confirmed for ${esc(r.year || "unknown")}${r.last_reviewed ? ", reviewed " + esc(r.last_reviewed) : ""}: ${esc(r.status || "REVIEW_REQUIRED")}</li>`,
    )
    .join("");
  return `<div class="section-note warning"><b>${rows.length} reference constant${rows.length === 1 ? " needs" : "s need"} annual review.</b> These drive tax brackets, IRMAA, Social Security, state tax, and capital market return calculations — confirm against the current-year source before relying on projections.<ul class="inapp-modal-list">${items}</ul><button class="btn tiny" type="button" onclick="setStep('system_configuration');setTimeout(()=>openSystemConfigurationConsole(),0)">Open tax-law dashboard</button></div>`;
}

export function renderDetailedResults() {
  return window.RetirementReportsUI.renderDetailedResults(reportsUiContext());
}

export function renderBuildPreflightPanel() {
  const p = buildPreflight || {};
  const blockers = p.blockers || [],
    warnings = p.warnings || [],
    recs = p.recommendations || [];
  let cls = blockers.length
    ? "bad"
    : warnings.length
      ? "warn"
      : p.current
        ? "ok"
        : "warn";
  let title = blockers.length
    ? "Build preflight blocked"
    : warnings.length
      ? "Build preflight warnings"
      : p.current
        ? "Report package current"
        : "Build preflight ready";
  let body = "";
  if (!buildPreflight) {
    body =
      '<p class="small">Preflight checks run automatically before build. Click Refresh Preflight to check saved Plan Data, outputs, pricing diagnostics, and validation now.</p>';
  } else {
    body += `<p class="small">Readiness: <b>${esc(p.readiness || "unknown")}</b>. Saved rows checked: ${Number(p.row_count || 0)}. Required missing: ${Number(p.missing_required_count || 0)}. Schema issues: ${Number(p.schema_error_count || 0)}.</p>`;
    const items = [
      ...blockers.map((x) => ["Blocker", x]),
      ...warnings.map((x) => ["Warning", x]),
      ...recs.map((x) => ["Next", x]),
    ];
    if (items.length) {
      body +=
        "<ul>" +
        items
          .slice(0, 10)
          .map(([k, v]) => `<li><b>${esc(k)}:</b> ${esc(v)}</li>`)
          .join("") +
        "</ul>";
    } else
      body +=
        '<p class="small">No preflight warnings found for the saved local plan.</p>';
  }
  return `<div class="preflight-panel ${cls}"><div><h3>${esc(title)}</h3>${body}</div><div class="preflight-actions"><button class="btn" type="button" onclick="refreshPreflightForReview()">Refresh Preflight</button></div></div>`;
}

export function renderReview() {
  const fresh = planStateFresh();
  const arts = planStateArtifactsReady();
  const unsaved = unsavedChangeCount();
  let statusHtml = "";
  if (unsaved)
    statusHtml = `<div class="section-note warning"><b>${unsaved} unsaved change${unsaved === 1 ? "" : "s"}.</b> Changes are saved automatically before download. <button class="btn tiny" type="button" data-requires-app="1" onclick="saveAll(true)">Save Now</button></div>`;
  else if (!fresh)
    statusHtml = `<div class="section-note warning"><b>Outputs may be stale.</b> Inputs changed since last build. <button class="btn tiny" type="button" onclick="goToReportsTab('Build')">Go to Build →</button></div>`;
  else if (arts)
    statusHtml =
      '<div class="section-note ok">Report outputs are current.</div>';
  else
    statusHtml =
      '<div class="section-note">No report outputs yet — build first, then download.</div>';
  return `<div class="reports-panel"><h3>Downloads</h3><p class="small">Download the workbook or PDF. Downloads save and rebuild automatically if outputs are not current.</p>${statusHtml}<div class="pane-actions"><button class="btn good" data-requires-app="1" onclick="downloadWithBuild('/api/xlsx','Workbook')">Download Workbook</button><button class="btn good" data-requires-app="1" onclick="downloadWithBuild('/api/pdf','PDF')">Download PDF</button></div></div>`;
}

export function renderPlanDataReport() {
  var REPORT_SECS = [
    {
      id: "household",
      label: "Household & Timing",
      stepIds: ["household_people"],
    },
    {
      id: "income",
      label: "Income",
      stepIds: ["income_work", "income_retirement"],
    },
    {
      id: "spending",
      label: "Spending",
      // Wellness and Housing each have their own dedicated tab below, so
      // they're intentionally not repeated here. Other Spending's DAF
      // settings are field-based (Travel and Large Discretionary are
      // matrix/table data not shown on this flat summary page).
      stepIds: [
        "spending_core",
        "spending_travel",
        "spending_travel_extras",
        "entity_charitable",
        "ytd_transactions",
      ],
    },
    { id: "healthcare", label: "Wellness", stepIds: ["retirement_wellness"] },
    { id: "housing", label: "Housing", stepIds: ["spending_mortgage_events"] },
    {
      id: "assets",
      label: "Assets & Holdings",
      stepIds: [
        "holdings",
        "assets_home_cash",
        "assets_special",
        "annuity_death_benefits",
      ],
    },
    { id: "estate", label: "Estate", stepIds: ["estate"] },
    {
      id: "risk",
      label: "Risk & Assumptions",
      stepIds: ["monte_carlo_options", "scenarios", "allocation_policy"],
    },
  ];
  var active = activePlanReportSection || "household";
  var sec =
    REPORT_SECS.find(function (s) {
      return s.id === active;
    }) || REPORT_SECS[0];

  var nav = '<div class="plan-report-nav">';
  REPORT_SECS.forEach(function (s) {
    var cls = s.id === active ? "plan-report-tab active" : "plan-report-tab";
    nav +=
      '<button class="' +
      cls +
      '" type="button" onclick="setPlanReportSection(\'' +
      s.id +
      "')\">" +
      esc(s.label) +
      "</button>";
  });
  nav += "</div>";
  var tools =
    '<div class="plan-data-preview-tools"><div><b>Plan Data Summary preview</b><span>Read-only saved input packet for final review. Print or save this section as PDF before sharing reports.</span></div><div class="pane-actions"><button class="btn primary" type="button" onclick="window.print()">Print / Save PDF</button><button class="btn" type="button" onclick="goToReportsTab(\'Build\')">Go to Build</button></div></div>';

  var body = "";

  if (sec.id === "assets") {
    body += '<div class="plan-report-section">';
    body += '<h3 class="group-title">Investment Holdings</h3>';
    if (window.holdingsPriceData === null) {
      if (!window.holdingsPriceLoading) setTimeout(loadHoldingsPriceData, 0);
      body += '<div class="section-note">Loading current prices...</div>';
    }
    var holdingData = (ensureHoldingRows().data || []).slice();
    holdingData.sort(function (a, b) {
      var t = String(a.symbol || "").localeCompare(String(b.symbol || ""));
      if (t !== 0) return t;
      return String(a.purchase_date || "").localeCompare(
        String(b.purchase_date || ""),
      );
    });
    var byAccount = {};
    var acctOrder = [];
    var anyEstimate = false;
    holdingData.forEach(function (h) {
      var acct = String(h.account || "Unknown").trim();
      if (!byAccount[acct]) {
        byAccount[acct] = { byTicker: {}, tickerOrder: [] };
        acctOrder.push(acct);
      }
      var tk = String(h.symbol || "").trim() || "(no ticker)";
      if (!byAccount[acct].byTicker[tk]) {
        byAccount[acct].byTicker[tk] = [];
        byAccount[acct].tickerOrder.push(tk);
      }
      byAccount[acct].byTicker[tk].push(h);
    });
    if (acctOrder.length) {
      // Alphabetize accounts by their display (nickname) label for the review.
      acctOrder.sort(function (a, b) {
        return accountDisplayLabel(a).localeCompare(accountDisplayLabel(b));
      });
      body += '<div class="holdings-report">';
      acctOrder.forEach(function (acct) {
        var acctData = byAccount[acct];
        // Per-symbol totals and the account total up front so both are shown in
        // the collapsed <summary> lines, not only when the group is expanded.
        // Totals use current market value (last cached/live price), not cost basis.
        var tickerTotals = {};
        var acctTotal = 0;
        acctData.tickerOrder.forEach(function (tk) {
          var t = 0;
          acctData.byTicker[tk].forEach(function (h) {
            var lv = holdingLotCurrentValue(h);
            t += lv.value;
            if (lv.isEstimate) anyEstimate = true;
          });
          tickerTotals[tk] = t;
          acctTotal += t;
        });
        // Alphabetize symbols within the account, but always sort CASH last.
        var tickers = acctData.tickerOrder.slice().sort(function (a, b) {
          var ca = /^cash$/i.test(a),
            cb = /^cash$/i.test(b);
          if (ca !== cb) return ca ? 1 : -1;
          return String(a).localeCompare(String(b));
        });
        body +=
          '<details class="holdings-account-group"><summary>' +
          esc(accountDisplayLabel(acct)) +
          ' <span class="small holdings-group-total">' +
          esc(currencyDisplay(acctTotal)) +
          '</span></summary><div class="holdings-ticker-list">';
        tickers.forEach(function (tk) {
          var lots = acctData.byTicker[tk];
          var tickerTotal = tickerTotals[tk];
          body +=
            '<details class="holdings-ticker-group"><summary>' +
            esc(tk) +
            ' <span class="small holdings-group-total">' +
            esc(currencyDisplay(tickerTotal)) +
            "</span></summary>";
          body +=
            '<div class="lot-table-wrap"><table class="lot-table"><thead><tr><th>Date</th><th>Shares</th><th>Cost Basis/sh</th><th>Current Value</th><th>Lot Type</th></tr></thead><tbody>';
          lots.forEach(function (h) {
            var lv = holdingLotCurrentValue(h);
            var estMark = lv.isEstimate
              ? ' <span class="small" title="No cached/live price found for this symbol; showing cost basis as a fallback estimate.">≈</span>'
              : "";
            body +=
              "<tr><td>" +
              esc(h.purchase_date || "") +
              "</td><td>" +
              esc(h.shares || "") +
              "</td><td>" +
              esc(currencyDisplay(h.purchase_price || 0)) +
              "</td><td>" +
              esc(currencyDisplay(lv.value)) +
              estMark +
              "</td><td>" +
              esc(h.lot_type || "") +
              "</td></tr>";
          });
          body += "</tbody></table></div></details>";
        });
        body +=
          '</div><div class="holdings-account-subtotal"><b>' +
          esc(accountDisplayLabel(acct)) +
          " total: " +
          esc(currencyDisplay(acctTotal)) +
          "</b></div></details>";
      });
      body += "</div>";
      if (anyEstimate)
        body +=
          '<div class="section-note small">≈ No cached/live price was found for one or more symbols; cost basis is shown as a fallback estimate for those lots.</div>';
    } else {
      body +=
        '<p class="small">No holdings loaded. Add holdings on the Investment Holdings tab.</p>';
    }
    body += "</div>";
  }

  (sec.stepIds || []).forEach(function (stepId) {
    if (stepId === "holdings") return;
    var stepRows = rowsForStep(stepId);
    // For the estate step: hide Special Needs rows unless the Special Needs
    // Planning optional workbook module is enabled.
    if (
      stepId === "estate" &&
      !optionalFunctionEnabled("special_needs_planning")
    ) {
      stepRows = stepRows.filter(function (r) {
        return !norm(r.subsection || "").startsWith("sn_");
      });
    }
    if (!stepRows.length) return;
    var stepDef = STEPS.find(function (s) {
      return s.id === stepId;
    });
    var stepTitle = stepDef ? stepDef.title : stepId;
    body += '<div class="plan-report-section">';
    body += '<h3 class="group-title">' + esc(stepTitle) + "</h3>";

    function renderReportRowGroup(groupRows, tight) {
      var out = '<div class="plan-report-rows' + (tight ? " plan-report-rows-tight" : "") + '">';
      groupRows.forEach(function (r) {
        var val = valOf(r);
        var display = String(val || "");
        if (typeof displayValueForInput === "function")
          try {
            display = displayValueForInput(r, val) || display;
          } catch (e) {}
        var isEmpty =
          !display || display.trim() === "" || display.trim() === "0";
        out +=
          '<div class="plan-report-row' +
          (isEmpty ? " plan-report-empty" : "") +
          '">';
        out +=
          '<span class="plan-report-label">' +
          esc(humanLabel(r.label, r)) +
          "</span>";
        out +=
          '<span class="plan-report-value' +
          (isEmpty ? " muted" : "") +
          '">' +
          esc(isEmpty ? "—" : display) +
          "</span>";
        out += "</div>";
      });
      out += "</div>";
      return out;
    }

    if (stepId === "household_people") {
      // One row per person (Matthew / Patricia), plus a third row for
      // household-level fields neither person owns (residence state, filing
      // status, survivor assumptions) -- rather than one flat grid that
      // interleaves both people's fields depending on how many columns
      // happen to fit at the viewport's current width.
      var personGroups = [1, 2]
        .map(function (n) {
          var prefix = "member_" + n + "_";
          var pRows = stepRows.filter(function (r) {
            return norm(r.label || "").indexOf(prefix) === 0;
          });
          return { n: n, rows: pRows };
        })
        .filter(function (g) {
          return g.rows.length;
        });
      var personLabels = new Set();
      personGroups.forEach(function (g) {
        g.rows.forEach(function (r) {
          personLabels.add(norm(r.label));
        });
      });
      var otherRows = stepRows.filter(function (r) {
        return !personLabels.has(norm(r.label));
      });
      personGroups.forEach(function (g) {
        body +=
          '<div class="plan-report-subsection">' +
          esc(personDisplayName(g.n)) +
          "</div>";
        body += renderReportRowGroup(g.rows, true);
      });
      if (otherRows.length) {
        body += '<div class="plan-report-subsection">Other</div>';
        body += renderReportRowGroup(otherRows, true);
      }
      body += "</div>";
      return;
    }

    if (stepId === "spending_mortgage_events") {
      // Current Home comes first (right under the "Housing" title, no
      // subsection label of its own -- this page is already about the
      // current home) and absorbs the current-home value/basis/appreciation
      // fields that otherwise live under a separate "Home" (Other Assets)
      // group at the end. Mortgage and any planned-move scenarios keep
      // their own labeled groups after it, in their existing order.
      var currentHomeRows = stepRows.filter(function (r) {
        return (
          (r.section === "Housing" && norm(r.subsection) === "current_home") ||
          (r.section === "Other Assets" && norm(r.subsection) === "home")
        );
      });
      var chSet = new Set(currentHomeRows);
      var housingRestRows = stepRows.filter(function (r) {
        return !chSet.has(r);
      });
      if (currentHomeRows.length) body += renderReportRowGroup(currentHomeRows, false);
      var byHousingSub = {};
      var housingSubOrder = [];
      housingRestRows.forEach(function (r) {
        var sub = r.subsection || "";
        if (!byHousingSub[sub]) {
          byHousingSub[sub] = [];
          housingSubOrder.push(sub);
        }
        byHousingSub[sub].push(r);
      });
      housingSubOrder.forEach(function (sub) {
        var subRows = byHousingSub[sub];
        if (sub) {
          var subLabel = humanLabel(sub, null);
          if (subLabel && subLabel !== sub)
            body +=
              '<div class="plan-report-subsection">' + esc(subLabel) + "</div>";
        }
        body += renderReportRowGroup(subRows, false);
      });
      body += "</div>";
      return;
    }

    var bySub = {};
    var subOrder = [];
    stepRows.forEach(function (r) {
      var sub = r.subsection || "";
      if (!bySub[sub]) {
        bySub[sub] = [];
        subOrder.push(sub);
      }
      bySub[sub].push(r);
    });
    subOrder.forEach(function (sub) {
      var subRows = bySub[sub];
      if (sub) {
        var subLabel = humanLabel(sub, null);
        if (subLabel && subLabel !== sub)
          body +=
            '<div class="plan-report-subsection">' + esc(subLabel) + "</div>";
      }
      body += renderReportRowGroup(subRows, false);
    });
    body += "</div>";
  });

  if (!body && sec.id !== "assets") {
    body =
      '<div class="section-note">No data found for this section. Fill in the input tabs and save to see data here.</div>';
  }

  return (
    '<div class="holdings plan-report-wrap">' + tools + nav + body + "</div>"
  );
}

export function renderTabbedWorkspace(tabs, active, handlerName) {
  return `<div class="workspace-tabs" role="tablist">${tabs.map((t) => `<button class="workspace-tab ${t === active ? "active" : ""}" type="button" role="tab" aria-selected="${t === active ? "true" : "false"}" onclick="${handlerName}('${escJs(t)}')">${esc(t)}</button>`).join("")}</div>`;
}

// Item 2.19 (finding U6): the "Preflight" tab merged into "Build" -- the
// readiness block (first-run checklist, build-preflight panel, and missing-
// required-fields list) now renders directly above the Build Reports
// button instead of requiring a separate tab click first. renderReadiness*
// kept as its own function (rather than inlined into renderReportsBuild)
// since it is still meaningfully reusable on its own.
function renderReportsReadinessBlock() {
  const stats = overallStats();
  const missing = stats.missing || [];
  let html =
    '<div class="reports-readiness"><h3>Readiness</h3><p class="small">Whether the plan is complete enough to build reports.</p>' +
    firstRunChecklistHtml(true) +
    renderBuildPreflightPanel();
  if (missing.length) {
    html += `<div class="missing-list"><h3>Needs attention</h3><ul>${missing
      .slice(0, 20)
      .map(
        (r) =>
          `<li>${esc(humanLabel(r.label, r))} <span class="small">(${esc(friendlyGroup(r))})</span></li>`,
      )
      .join("")}</ul></div>`;
  } else {
    html +=
      '<div class="section-note ok"><b>Plan is ready to build.</b> Warnings may still appear, but no required fields are missing.</div>';
  }
  html += "</div>";
  return html;
}

export function renderReportsBuild() {
  const fresh = planStateFresh();
  const arts = planStateArtifactsReady();
  let statusHtml = "";
  if (lastBuildSummary) {
    const ts =
      lastBuildSummary.timestamp || lastBuildSummary.build_timestamp || "";
    const qc = lastBuildSummary.qc_result || "not reviewed";
    statusHtml = `<div class="section-note ${fresh ? "ok" : "warn"}">Last build${ts ? " — " + esc(ts) : ""} — QC: ${esc(qc)}. ${fresh ? "Outputs are current." : "Inputs changed since last build — rebuild for current outputs."}</div>`;
  } else if (arts) {
    statusHtml =
      '<div class="section-note ok">Report outputs are present but no build summary is on record.</div>';
  } else {
    statusHtml =
      '<div class="section-note">No build on record. Build Reports creates the workbook, PDF, and Results Explorer.</div>';
  }
  return `<div class="reports-panel"><h3>Build</h3><p class="small">Save the current plan and run the full projection engine. Creates the workbook, PDF, and Results Explorer model. Progress appears in the build overlay.</p>${renderReportsReadinessBlock()}<div class="pane-actions"><button class="btn primary" type="button" data-requires-app="1" onclick="runBuild(false)">Build Reports</button><button class="btn" type="button" onclick="refreshBuildStatus()">Refresh Status</button></div>${statusHtml}</div>`;
}

export function renderReportsAndReview() {
  const active = REPORTS_TABS.includes(reportsActiveTab)
    ? reportsActiveTab
    : "Build";
  let body = "";
  if (active === "Build") body = renderReportsBuild();
  else if (active === "Impact") body = renderBuildImpactPage();
  else if (active === "Results") body = renderDetailedResults();
  else if (active === "Downloads") body = renderReview();
  else if (active === "Plan Data Review") body = renderPlanDataReport();
  return `<div class="tabbed-workspace reports-workspace">${renderTabbedWorkspace(REPORTS_TABS, active, "setReportsTab")}<div class="workspace-tab-body">${body}</div></div>`;
}

export async function startNewPlan() {
  if (hasUnsavedPlanChanges()) {
    const choice = await showSaveDiscardStayModal(
      "You have unsaved changes. Save them before starting a new plan, discard them, or stay here?",
      { title: "Start New Plan" },
    );
    if (choice === "stay") return;
    if (choice === "save") {
      const ok = await saveAll(true);
      if (!ok) return;
    }
  }
  let ytdBlendChoice = null;
  try {
    const status = await api("/api/ytd/status");
    const summary = (status && status.summary) || {};
    const actual = summary.actual || {};
    if (
      summary.enabled &&
      (Number(actual.spending || 0) > 0 ||
        Number(actual.earned_income || 0) > 0)
    ) {
      const choice = await showYtdBlendChoiceModal(summary);
      if (choice === null) return;
      ytdBlendChoice = choice === "blend";
    }
  } catch (e) {
    /* YTD status unavailable — proceed with default blend-on behavior */
  }
  try {
    planFolderHandle = null;
    planFolderName = "";
    await api("/api/plan-data/blank", {
      method: "POST",
      body: JSON.stringify(
        ytdBlendChoice === null ? {} : { ytd_blend_enabled: ytdBlendChoice },
      ),
    });
    sessionChanges.clear();
    sessionSpecialChanges.clear();
    dirty.clear();
    window.holdingsChanged = false;
    liabilitiesChanged = false;
    travelExtrasChanged = false;
    liquidityChanged = false;
    forcedConversionsChanged = false;
    ytdTransactionsChanged = false;
    ytdAccountsChanged = false;
    taxonomyData = null;
    taxonomyFlat = {};
    taxonomyError = "";
    spendingModelData = null;
    spendingModelError = "";
    mappingRules = null;
    rulesChanged = false;
    taxBudget = {};
    taxBudgetChanged = false;
    taxBudgetLoaded = false;
    budgetLines = [];
    budgetLinesChanged = false;
    budgetLinesLoaded = false;
    budgetSectionMode = {};
    categoryBudgetMode = {};
    groupBudgetMode = {};
    ytdData = null;
    sessionBaselineSummary = null;
    sessionBaselineCaptured = false;
    await loadAll({
      source: "New blank plan",
      preferLocal: false,
      silent: true,
    });
    activeStep = "household_people";
    lastBuildOk = false;
    planChatMessages = [];
    showMessage(
      "New blank plan started in the local database. User data is blank; option defaults are retained." +
        (ytdBlendChoice === false
          ? " This plan is modeled as fully hypothetical — real YTD actuals are excluded from the current-year projection."
          : ""),
    );
    renderMain();
    window.scrollTo({ top: 0 });
  } catch (e) {
    showMessage("Error starting new plan: " + e.message, "error");
  }
}

// Every export above is also re-attached to window: dashboard.js calls these
// as bare globals, and this file's own rendered HTML uses inline
// onclick="..." handlers, which always resolve through window regardless of
// module scoping. New code should prefer `import` from this module; this
// bridge exists only for callers that cannot move to import in the same pass.
Object.assign(window, {
  showConfigCardHelp,
  recentChangesLogHtml,
  undoSessionFieldChange,
  showYtdBlendChoiceModal,
  nbaPanelHtml,
  renderWelcome,
  renderSystemConfiguration,
  refreshLivePrices,
  freezePricingSnapshot,
  unfreezePricingSnapshot,
  exportCsvBackup,
  openSystemConfigurationConsole,
  setAutoLoad,
  checklistItemStatus,
  firstRunChecklistHtml,
  savePlanAs,
  openDemoPlan,
  openCurrentPlan,
  resetDemoToDefaults,
  loadSavedPlan,
  loadTaxFreshnessStatus,
  taxFreshnessBannerHtml,
  renderDetailedResults,
  renderBuildPreflightPanel,
  renderReview,
  renderPlanDataReport,
  renderTabbedWorkspace,
  renderReportsBuild,
  renderReportsAndReview,
  startNewPlan,
});
