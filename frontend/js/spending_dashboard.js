/* Spending Dashboard — comprehensive income and expense tracker (excludes internal transfers).
   Loaded by index.html, renders when activeStep === 'spending_dashboard'. */

// This shared mutable state is written from OUTSIDE this module too
// (dashboard.js clears window.spendingData directly to invalidate the
// cache), so it lives on window explicitly rather than as module-local
// state a module conversion would otherwise hide from that caller.
window.spendingData = null;
window.spendingLoading = false;
window.spendingError = '';
// One Set of composite keys ('type:', 'group:', 'cat:' prefixed) tracks every
// expanded row independently, so expanding one Type/Group/Category no longer
// collapses another that happens to share the same scalar slot.
window.spendingExpandedKeys = new Set();
// U3 (system review 2026-08-31): "Show over/watch only" filter chip -- when
// active, renderSpendingBars() auto-expands and hides every 'ok' row so
// flagged categories are reachable in one click instead of manually
// expanding every Type/Group disclosure (up to 24 clicks for a 6x4
// household).
window.spendingExceptionsOnly = false;
window.spendingDivergencePct = 0;
export function getSpendingDivergencePct() { return window.spendingDivergencePct || 0 }
window.getSpendingDivergencePct = getSpendingDivergencePct;

// Wave 6.2 (system review 2026-08-04, finding `ui-spending-domain-fragmentation`):
// same shape as the tabbed workspaces the ticket 323 Strategy redesign later
// adopted (Optimize/Stress Test/Scenarios). Each tab still calls the
// same render function its old standalone step used, so behavior (including
// the Wave 1.4 jump-to-field fix inside renderLifestyleSpending()'s accordions)
// is unchanged -- only the navigation surface merges Spending Model, Actual
// Spending (YTD), and Spending Analysis into one workspace. Other Spending's
// former tab is gone too, but not by merging navigation surfaces -- its
// content (renderLifestyleSpending()) is now folded directly into the
// Spending Model tab's own output (renderCoreSpendingUnified(),
// dashboard_decomp_spending_taxonomy.js), since it belongs there, not beside
// it as a separate stop.
// Lives here (not dashboard.js) to keep dashboard.js under its size ratchet --
// this module runs after dashboard.js's own top-level code, so its globals
// (getStrategyTab, renderStrategyTabs, renderYtdTransactionsStep, etc.) are
// already attached to window by the time a user triggers a render.
// #330 §3.3/§5.2 (W12, inherited from W9's own triage: "hiding the YTD tab
// within spending_core... belongs to W12's own scope"). Actual Spending
// (YTD) and Spending Analysis are both views over ytd_transactions data via
// the Spending Tracker / YTD bundle (spending_tracker_ytd, gating
// spending_summary + account_reconciliation as one switch, #330 §3.3/W8b);
// neither can compute without it. Collapsed-with-a-note, not removed from
// the tab strip -- the tab stays reachable and switchable in place, matching
// every other module-owned section that lives inside a page which stays
// visible (§5.2). No entered-row count: spending_tracker_ytd owns no
// dashboard_step/csv_sections rows of its own (its inputs are imported
// transactions, not typed plan rows), the same reason Plan Features shows no
// "N items entered" for it either.
// #338 W-C: these two tabs are the Actual Spending step under Reports &
// Review now (ytd_transactions + spending_dashboard merged), not tabs of
// Spending Model.
// Explains the "! >3%" left-nav badge (same 3% threshold as stepButton): all
// spending Tracking Types, annualized, vs. the annual budget for those same types.
export function spendingDivergenceNoteHtml() {
  var pct = Number(getSpendingDivergencePct()) || 0;
  if (pct <= 0.03) return '';
  var d = window.spendingData || {};
  return '<div class="section-note warning spending-divergence-note"><b>! &gt;3% &mdash; annualized spending is ' +
    (pct * 100).toFixed(1) + '% over the annual budget.</b> Annualized spending (all Tracking Types, including taxes) is <b>' +
    fmtSpend(d.annualized_total) + '</b> vs. an annual budget of <b>' + fmtSpend(d.budget_total) + '</b>.' +
    ' The "! &gt;3%" badge in the left nav appears when this exceeds 3%. Review the categories below, or raise the budget if this is the right run rate.</div>';
}
window.spendingDivergenceNoteHtml = spendingDivergenceNoteHtml;

export function renderActualSpendingWorkspace(tabs) {
  var tab = window.getStrategyTab('actual_spending');
  var ytdOn = window.optionalFunctionEnabled('spending_tracker_ytd');
  var body;
  if (tab === 'Analysis')
    body = ytdOn ? window.renderSpendingDashboardOrLoad() : window.featureGatedNote('spending_tracker_ytd', { title: 'Spending Analysis' });
  else
    body = ytdOn ? window.renderYtdTransactionsStep() : window.featureGatedNote('spending_tracker_ytd', { title: 'Actual Spending' });
  return '<div class="tabbed-workspace spending-workspace">' + spendingDivergenceNoteHtml() + window.renderStrategyTabs('actual_spending', tabs, tab) + '<div class="workspace-tab-body">' + body + '</div></div>';
}
window.renderActualSpendingWorkspace = renderActualSpendingWorkspace;

export function fmtSpend(n) { var v = Math.round(Number(n) || 0); return (v < 0 ? '-$' : '$') + Math.abs(v).toLocaleString('en-US') }
// Signed variance display (e.g. "+3.2%" over budget) — distinct from the
// global fmtPct (dashboard_shared_helpers.js), which has no +sign and
// returns "Not available" for invalid input. Renamed (A13) so this file no
// longer silently shadows the shared fmtPct for the rest of the page.
export function fmtVariancePct(n) { var v = Number(n) || 0; return (v > 0 ? '+' : '') + v.toFixed(1) + '%' }
export function spendYtd(row){return Number(row && (row.ytd_actual !== undefined ? row.ytd_actual : row.actual)) || 0}
export function spendAnnualized(row){return Number(row && (row.annualized_actual !== undefined ? row.annualized_actual : row.annualized)) || 0}
export function spendBudget(row){return Number(row && (row.annual_budget !== undefined ? row.annual_budget : row.budget)) || 0}
export function spendProjectionSeed(row){return Number(row && (row.projection_seed !== undefined ? row.projection_seed : (row.annual_budget !== undefined ? row.annual_budget : row.budget))) || 0}
export function spendHasReconcileValue(row){return !!(spendYtd(row)||spendAnnualized(row)||spendBudget(row)||spendProjectionSeed(row))}

export function loadSpendingDashboard(force) {
  if (window.spendingLoading && !force) return;
  window.spendingLoading = true;
  window.spendingError = '';
  renderMain(); var yr = selectedSpendingYear();
  api('/api/spending/dashboard?year=' + yr).then(function (data) {
    window.spendingLoading = false; if (yr !== selectedSpendingYear()) return; // stale: newer year picked
    if (data && data.success) { window.spendingData = data; window.spendingError = '' }
    else { window.spendingError = (data && data.error) || 'Failed to load spending data.' }
    renderMain();
  }).catch(function (err) {
    window.spendingLoading = false;
    window.spendingError = err.message || 'Network error loading spending dashboard.';
    renderMain();
  });
}

export function seedSpendingBudget() {
  api('/api/spending/budget/seed', { method: 'POST', body: '{}' }).then(function (res) {
    if (res && res.success) {
      showMessage('Budget seeded from actuals. Reload to see allocations.', 'ok');
      loadSpendingDashboard(true);
    } else {
      showMessage((res && res.error) || 'Seed failed.', 'error');
    }
  }).catch(function (e) { showMessage('Seed error: ' + e.message, 'error') });
}

export function applySpendingForecast() {
  if (!window.spendingData) return;
  if(ytdTransactionsChanged||ytdAccountsChanged){
    showMessage('Transaction data has changed since the dashboard loaded. Refresh the Spending tab before syncing.','warn');
    return;
  }
  var forecast = window.spendingData.forecast_total;
  if (!forecast || forecast <= 0) { showMessage('No forecast to apply.', 'warn'); return }
  var label = 'annual_spending_base_year';
  var row = (typeof rows !== 'undefined' ? rows : []).find(function (r) {
    return r && String(r.label || '').trim() === label &&
           String(r.section || '').trim() === 'Cashflow' &&
           String(r.subsection || '').toLowerCase() === 'spending';
  });
  if (!row) { showMessage('Core spending row not found in loaded plan data.', 'error'); return }
  var formatted = '$' + Math.round(forecast).toLocaleString('en-US');
  dirty.set(row.row_index, formatted);
  lastBuildOk = false;
  updateUnsaved();
  showMessage('Applied ' + fmtSpend(forecast) + ' as spending categories. Save Changes to persist.', 'ok');
  renderMain();
}

export function toggleSpendingKey(key) {
  if (window.spendingExpandedKeys.has(key)) window.spendingExpandedKeys.delete(key);
  else window.spendingExpandedKeys.add(key);
  renderMain();
}

export function toggleSpendingGroup(group) { toggleSpendingKey('group:' + group) }

export function toggleSpendingCat(key) { toggleSpendingKey('cat:' + key) }

export function toggleSpendingType(tt) { toggleSpendingKey('type:' + tt) }

export function collapseAllSpending() {
  window.spendingExpandedKeys.clear();
  renderMain();
}

export function toggleSpendingExceptionsOnly() {
  window.spendingExceptionsOnly = !window.spendingExceptionsOnly;
  renderMain();
}

export function renderSpendingDashboard() {
  if (!window.spendingData && !window.spendingLoading && !window.spendingError) {
    setTimeout(function () { loadSpendingDashboard(false) }, 0);
  }
  if (window.spendingLoading) {
    return '<div class="holdings spending-dashboard"><div class="detail-loading-card">' +
      '<h3>Loading spending tracker</h3><p class="small">Aggregating transactions and computing budget comparisons...</p></div></div>';
  }
  if (window.spendingError && !window.spendingData) {
    return '<div class="holdings spending-dashboard"><div class="missing-list"><h3>Spending data unavailable</h3>' +
      '<p>' + esc(window.spendingError) + '</p></div>' +
      '<div class="table-actions"><button class="btn" onclick="loadSpendingDashboard(true)">Retry</button></div></div>';
  }
  var d = window.spendingData || {};
  // Same scope on both sides: annualized spending and the annual budget cover
  // the same Tracking Types (not the core-only model assumption).
  var prevOver = Number(window.spendingDivergencePct) > 0.03;
  if (d.year == null || d.year === new Date().getFullYear()) window.spendingDivergencePct = Number(d.budget_total) > 0 ? (Number(d.annualized_total || 0) - Number(d.budget_total)) / Number(d.budget_total) : 0;
  if (prevOver !== (window.spendingDivergencePct > 0.03)) setTimeout(function () { if (window.renderSteps) window.renderSteps(); }, 0);
  if (!d.enabled) {
    return '<div class="holdings spending-dashboard"><div class="question"><b>No transaction data loaded.</b> ' +
      'Import transactions on the <a href="#" onclick="setStep(\'ytd_transactions\');return false">Income &amp; Expense Transactions tab</a> first, then return here to track budget vs actuals.</div></div>';
  }

  var html = '<div class="holdings spending-dashboard">';
  html += '<div class="spend-taxonomy-card"><b>How spending is organized:</b> ' +
    '<span><b>Hierarchy</b> — Tracking Type → Group → Category;</span> ' +
    '<span><b>Included</b> — all Income and all expense Tracking Types, including Taxes;</span> ' +
    '<span><b>Excluded</b> — internal transfers only.</span></div>';
  // This-year performance summary (badges + charts + top categories)
  var ytdSummaryHtml = (typeof renderYtdSummary === 'function') ? renderYtdSummary() : '';
  if (ytdSummaryHtml) {
    html += '<h3 class="group-title" style="margin:0 20px 12px">' + (d.year || selectedSpendingYear()) + ' Performance</h3>';
    html += ytdSummaryHtml;
    html += '<h3 class="group-title" style="margin:16px 20px 8px">Spending Budget Tracker</h3>';
  }
  html += renderSpendingSummary(d);
  html += renderSpendingBars(d);
  html += renderSpendingMonthly(d);
  if (d.model_managed && Object.keys(d.model_managed).length) html += renderModelManaged(d);
  // Business now appears inside the main Tracking Type hierarchy; no separate section below Monthly Trajectory.
  if (d.unmapped_categories && d.unmapped_categories.length) html += renderUnmappedWarning(d);
  html += '<div class="table-actions">';
  html += '<button class="btn" onclick="loadSpendingDashboard(true)">Refresh</button>';
  if (!d.budget_total) html += '<button class="btn primary" data-requires-app="1" onclick="seedSpendingBudget()" title="Creates category budget targets based on current actual spending proportions">Initialize Budget from Actual Spending</button>';
  if (d.forecast_total > 0 && d.year === new Date().getFullYear()) html += '<button class="btn good" data-requires-app="1" onclick="applySpendingForecast()" title="Updates the spending categories assumption used by the 30-year retirement projection">Sync Actual Rate → 30-Year Model</button>';
  html += '</div>';
  html += '</div>';
  return html;
}

export function renderSpendingSummary(d) {
  var annualized = d.annualized_total || 0;
  var budget = d.budget_total || 0;
  // Apples-to-apples: both annualized_total and budget_total sum the same
  // set of Tracking Types, unlike d.variance_pct (backend), which compares
  // annualized_total against model_core_spending -- the retirement model's
  // Core-only spending assumption, a much narrower scope that made the old
  // "Actual vs. Model" figure misleading (see spending_dashboard blue-box
  // removal, 2026-09).
  var vpct = budget ? ((annualized - budget) / budget) * 100 : 0;
  var annualizedAllIn = d.annualized_total_all_in || 0;
  var budgetAllIn = d.annual_budget_total_all_in || 0;
  var html = '<div class="spend-summary">';
  // This Year Income / Expenses tiles removed: they duplicate the YTD income
  // and YTD spending cards in This Year Performance (same classifier).
  html += '<div class="spend-kpi"><span class="spend-kpi-value">' + fmtSpend(annualized) + '</span><span class="spend-kpi-label">Annualized Expenses</span>';
  if (annualized > 0) {
    html += '<button class="btn tiny good" data-requires-app="1" onclick="applySpendingForecast()" title="Updates the retirement model\'s core spending assumption to this annualized rate">Sync Actual Rate → 30-Year Model</button>';
  }
  html += '</div>';
  html += '<div class="spend-kpi"><span class="spend-kpi-value">' + fmtSpend(budget || d.model_core_spending) + '</span><span class="spend-kpi-label">' + (budget ? 'Annual Budget' : 'Model Spending Categories') + '</span></div>';
  var cls = vpct > 15 ? 'spend-kpi over' : vpct > 5 ? 'spend-kpi watch' : 'spend-kpi ok';
  html += '<div class="' + cls + '"><span class="spend-kpi-value">' + fmtVariancePct(vpct) + '</span><span class="spend-kpi-label">' + (budget ? 'Annualized vs. Annual Budget' : 'Annualized vs. Model Spending Categories') + '</span></div>';
  html += '</div>';
  // Companion all-in figures (incl. internal transfers, e.g. credit card
  // payments, brokerage buys/sells, 401k/HSA contributions) -- kept as a
  // separate row rather than folded into the KPI tiles above, so the
  // Actual-vs-Budget comparison stays scoped to real spending. Taxes are
  // already included in the KPI tiles above as of the Taxes tracking type
  // (see spending_tracker.py); this row now only ever differs when a
  // household has transfer-categorized transactions with real dollars.
  // Only rendered when it actually differs from the KPI tiles above.
  var transferAnnualized = annualizedAllIn - annualized;
  var transferBudget = budgetAllIn - budget;
  var hasAllInDelta = Math.abs(transferAnnualized) >= 0.5 || Math.abs(transferBudget) >= 0.5;
  if (hasAllInDelta) {
    html += '<div class="spend-summary spend-summary-all-in">';
    html += '<div class="spend-kpi"><span class="spend-kpi-value">' + fmtSpend(annualizedAllIn) + '</span><span class="spend-kpi-label">Annualized, All-In (Incl. Transfers)</span></div>';
    html += '<div class="spend-kpi"><span class="spend-kpi-value">' + fmtSpend(budgetAllIn) + '</span><span class="spend-kpi-label">Annual Budget, All-In (Incl. Transfers)</span></div>';
    html += '</div>';
  }
  html += '<p class="small" style="margin:0 0 12px">' + d.days_elapsed + ' days elapsed &middot; annualization factor ' + (d.annualization_factor || 1).toFixed(2) + 'x &middot; the five KPI tiles above include income taxes and exclude only internal transfers' +
    (hasAllInDelta ? '; the All-In row adds transfer transactions back in' : '; no transfer transactions are logged in ' + (d.year || selectedSpendingYear()) + ', so the All-In totals would match the tiles above and are omitted') + '</p>';
  return html;
}

export function renderSpendingBars(d) {
  // Full Tracking Type -> Group -> Category hierarchy from the taxonomy summary
  // (each level carries annualized actual + budget). Income and Taxes are included; internal transfers are filtered in the backend.
  var tax = (d.taxonomy_summary && d.taxonomy_summary.tracking_types) || [];
  var types = tax.filter(function (t) { return t.groups && t.groups.length; });
  if (!types.length) return '';
  var maxVal = 0;
  types.forEach(function (t) { maxVal = Math.max(maxVal, spendAnnualized(t), spendBudget(t), spendProjectionSeed(t)); (t.groups || []).forEach(function (g) { maxVal = Math.max(maxVal, spendAnnualized(g), spendBudget(g), spendProjectionSeed(g)); }); });
  if (maxVal <= 0) maxVal = 1;

  function statusFor(ann, bud) {
    if (!bud) return { cls: 'ok', vpct: null };
    var vpct = ((ann - bud) / bud) * 100;
    return { cls: vpct > 15 ? 'over' : vpct > 5 ? 'watch' : 'ok', vpct: Math.round(vpct * 10) / 10 };
  }
  var exceptionsOnly = !!window.spendingExceptionsOnly;
  // Reuses statusFor() (not a recomputation) to decide whether a Type/Group
  // row contains any non-'ok' descendant, so the exceptions filter can hide
  // whole branches that are entirely on-budget.
  function groupHasException(g) {
    if (statusFor(spendAnnualized(g), spendBudget(g)).cls !== 'ok') return true;
    return (g.categories || []).some(function (c) {
      return statusFor(spendAnnualized(c), spendBudget(c)).cls !== 'ok';
    });
  }
  function typeHasException(t) {
    if (statusFor(spendAnnualized(t), spendBudget(t)).cls !== 'ok') return true;
    return (t.groups || []).some(groupHasException);
  }
  function barCell(ann, bud) {
    var barPct = Math.min(100, ((ann || 0) / maxVal) * 100);
    var budPct = bud ? Math.min(100, (bud / maxVal) * 100) : 0;
    var h = '<div class="spend-bar-track"><span class="spend-bar-fill" style="width:' + barPct.toFixed(1) + '%"></span>';
    if (budPct > 0) h += '<span class="spend-bar-budget" style="left:' + budPct.toFixed(1) + '%"></span>';
    return h + '</div>';
  }
  function valCell(ytd, ann, bud, seed, st) {
    var h = '<div class="spend-bar-values"><span>' + (window.spendingData && window.spendingData.year || selectedSpendingYear()) + ' ' + fmtSpend(ytd) + '</span>';
    h += '<span class="small">Annualized ' + fmtSpend(ann) + '</span>';
    h += '<span class="small">Budget ' + fmtSpend(bud) + '</span>';
    h += '<span class="small">Projection ' + fmtSpend(seed) + '</span>';
    if (bud && typeof st.vpct === 'number') h += '<span class="small ' + st.cls + '">' + fmtVariancePct(st.vpct) + '</span>';
    return h + '</div>';
  }

  var html = '<h3 class="group-title">Income and Expenses by Tracking Type / Group / Category' +
    ' <button class="btn tiny' + (exceptionsOnly ? ' primary' : '') + '" type="button" onclick="toggleSpendingExceptionsOnly()">' +
    (exceptionsOnly ? 'Show all' : 'Show over/watch only') + '</button>' +
    (window.spendingExpandedKeys.size ? ' <button class="btn tiny" type="button" onclick="collapseAllSpending()">Collapse all</button>' : '') +
    '</h3>';
  html += '<div class="spend-bars">';
  html += '<div class="spend-bar-header"><span>Tracking type · Group · Category</span><span>Annualized vs. Annual Budget</span><span>YTD Actual | Annualized | Annual Budget | Projection</span></div>';

  var shownAny = false;
  types.forEach(function (t) {
    if (exceptionsOnly && !typeHasException(t)) return;
    shownAny = true;
    var tt = t.tracking_type;
    var typeExpanded = exceptionsOnly || window.spendingExpandedKeys.has('type:' + tt);
    var tytd = spendYtd(t), tann = spendAnnualized(t), tbud = spendBudget(t), tseed = spendProjectionSeed(t);
    var st = statusFor(tann, tbud);
    html += '<div class="spend-bar-row spend-type-row ' + st.cls + '" onclick="toggleSpendingType(\'' + esc(tt).replace(/'/g, "\\'") + '\')">';
    html += '<div class="spend-bar-label spend-type-label"><span class="spend-level-pill">Tracking Type</span><span class="spend-caret' + (typeExpanded ? ' open' : '') + '"></span><b>' + esc(tt) + '</b></div>';
    html += barCell(tann, tbud) + valCell(tytd, tann, tbud, tseed, st);
    html += '</div>';
    if (!typeExpanded) return;

    (t.groups || []).forEach(function (g) {
      if (exceptionsOnly && !groupHasException(g)) return;
      var gkey = tt + '::' + g.group;
      var gExpanded = exceptionsOnly || window.spendingExpandedKeys.has('group:' + gkey);
      var gytd = spendYtd(g), gann = spendAnnualized(g), gbud = spendBudget(g), gseed = spendProjectionSeed(g);
      var gs = statusFor(gann, gbud);
      html += '<div class="spend-bar-row spend-group-row ' + gs.cls + '" onclick="event.stopPropagation();toggleSpendingGroup(\'' + esc(gkey).replace(/'/g, "\\'") + '\')">';
      html += '<div class="spend-bar-label spend-group-label"><span class="spend-level-pill">Group</span><span class="spend-caret' + (gExpanded ? ' open' : '') + '"></span>' + esc(g.group) + '</div>';
      html += barCell(gann, gbud) + valCell(gytd, gann, gbud, gseed, gs);
      html += '</div>';
      if (!gExpanded) return;
      html += '<div class="spend-bar-detail">';
      (g.categories || []).forEach(function (c) {
        var cann = spendAnnualized(c), cbud = spendBudget(c);
        var cs = statusFor(cann, cbud);
        if (exceptionsOnly && cs.cls === 'ok') return;
        var cytd = spendYtd(c), cseed = spendProjectionSeed(c);
        html += '<div class="spend-cat-row"><span><span class="spend-level-pill">Category</span>' + esc(c.label || c.id) + '</span>' +
          '<span>YTD ' + fmtSpend(cytd) + ' · Annualized ' + fmtSpend(cann) + ' · Budget ' + fmtSpend(cbud) + ' · Projection ' + fmtSpend(cseed) + (cbud ? ' <span class="small ' + cs.cls + '">' + fmtVariancePct(cs.vpct || 0) + '</span>' : '') + '</span></div>';
      });
      html += '</div>';
    });
  });
  if (exceptionsOnly && !shownAny) {
    html += '<div class="section-note">No categories are currently over budget or in the watch range.</div>';
  }
  html += '</div>';
  return html;
}

export function renderSpendingMonthly(d) {
  var series = d.monthly_series || [];
  if (!series.length) return '';
  var html = '<h3 class="group-title">Monthly Trajectory <span class="small">(all spending except internal transfers)</span></h3>';
  html += '<div class="section-note">Includes Housing, Wellness/healthcare, Travel, Large Discretionary, Business, Core Expense, and Taxes outflows when present in transactions. Internal transfers are excluded.</div>';
  html += '<div class="lot-table-wrap"><table class="lot-table spend-monthly-table">';
  html += '<thead><tr><th>Month</th><th>Actual</th><th>Budget</th><th>Cum Actual</th><th>Cum Budget</th><th>Cum Δ</th></tr></thead>';
  html += '<tbody>';
  series.forEach(function (m) {
    var delta = m.cumulative_actual - m.cumulative_budget;
    var cls = delta > 0 ? 'over' : 'ok';
    html += '<tr>';
    html += '<td>' + esc(m.label) + '</td>';
    html += '<td>' + fmtSpend(m.actual) + '</td>';
    html += '<td>' + fmtSpend(m.budget) + '</td>';
    html += '<td>' + fmtSpend(m.cumulative_actual) + '</td>';
    html += '<td>' + fmtSpend(m.cumulative_budget) + '</td>';
    html += '<td class="spend-delta ' + cls + '">' + fmtSpend(delta) + '</td>';
    html += '</tr>';
  });
  html += '</tbody></table></div>';
  return html;
}

export function renderModelManaged(d) {
  var MM_LABELS = {housing:'Housing',wellness:'Wellness',travel:'Travel',large_disc:'Large Discretionary Expenses',model_managed:'Other Model-Managed'};
  var mm = d.model_managed || {};
  var typeKeys = Object.keys(mm);

  if (!typeKeys.length) return '';

  var html = '<h3 class="group-title">Model-Managed (Not in Core Budget)</h3>';
  html += '<div class="section-note">These categories are tracked separately by the projection model and excluded from the spending categories budget.</div>';

  typeKeys.forEach(function(typeKey) {
    var cats = mm[typeKey] || {};
    var catKeys = Object.keys(cats);
    var typeTotal = catKeys.reduce(function(s, k) { return s + (cats[k] || 0); }, 0);
    var label = MM_LABELS[typeKey] || typeKey;

    html += '<details class="spend-mm-group" open><summary class="spend-mm-summary">';
    html += '<span>' + esc(label) + '</span><span>' + fmtSpend(typeTotal) + ' YTD</span>';
    html += '</summary><div class="spend-mm-list spend-mm-detail">';
    catKeys.sort().forEach(function(cat) {
      html += '<div class="spend-mm-item"><span>' + esc(cat) + '</span><span>' + fmtSpend(cats[cat]) + ' YTD</span></div>';
    });
    html += '</div></details>';
  });

  return html;
}

export function renderBusinessSection(d) {
  var biz = d.business;
  if (!biz || !biz.actual) return '';
  var html = '<h3 class="group-title">Business Expenses</h3>';
  html += '<div class="section-note">Business expenses tracked separately from personal core budget.</div>';
  html += '<div class="spend-mm-item"><span>Total Business</span><span>' + fmtSpend(biz.actual) + ' YTD / ' + fmtSpend(biz.annualized) + ' annualized</span></div>';
  if (biz.categories && biz.categories.length) {
    html += '<div class="spend-bar-detail">';
    biz.categories.forEach(function (c) {
      var catKey = 'Business::' + c.category;
      var hasMerchants = c.merchants && c.merchants.length > 1;
      var catExpanded = window.spendingExpandedKeys.has('cat:' + catKey);
      html += '<div class="spend-cat-row' + (hasMerchants ? ' expandable' : '') + '"' +
        (hasMerchants ? ' onclick="toggleSpendingCat(\'' + esc(catKey).replace(/'/g, "\\'") + '\')"' : '') + '>' +
        '<span>' + (hasMerchants ? '<span class="spend-caret' + (catExpanded ? ' open' : '') + '"></span>' : '') + esc(c.category) +
        (hasMerchants ? ' <span class="spend-merch-count">' + c.merchants.length + '</span>' : '') + '</span>' +
        '<span>' + fmtSpend(c.actual) + '</span></div>';
      if (catExpanded && c.merchants) {
        html += '<div class="spend-merchant-detail">';
        c.merchants.forEach(function (m) {
          html += '<div class="spend-merch-row"><span>' + esc(m.merchant) + '</span><span>' + fmtSpend(m.actual) + ' <span class="spend-merch-txn">' + m.count + ' txn</span></span></div>';
        });
        html += '</div>';
      }
    });
    html += '</div>';
  }
  return html;
}

// "Map to category" on the unmapped warning. Confirming POSTs either
// /api/spending/alias (existing category) or /api/spending/category (new
// category + exact alias in one call); the alias matches the raw Monarch text
// and load_category_map/_resolve_alias compare case-insensitively.
export function spendMapRequest(rawCat, choice) {
  var raw = String(rawCat || '').trim();
  if (!raw) return { error: 'Missing category text.' };
  if (choice && choice.mode === 'new') {
    var label = String(choice.label || '').trim();
    var group = String(choice.group || '').trim();
    var tt = String(choice.tracking_type || '').trim();
    if (!label || !group || !tt) return { error: 'Tracking type, group and label are required.' };
    return { path: '/api/spending/category', body: { label: label, tracking_type: tt, group: group, match_value: raw, match_field: 'category', exact: true } };
  }
  var id = String((choice && choice.category_id) || '').trim();
  if (!id) return { error: 'Pick a category.' };
  return { path: '/api/spending/alias', body: { match_value: raw, match_field: 'category', exact: true, category_id: id } };
}

export function spendMapOptionsHtml(taxonomy) {
  return (taxonomy || []).map(function (t) {
    return (t.groups || []).map(function (g) {
      var cats = (g.categories || []);
      if (!cats.length) return '';
      return '<optgroup label="' + esc(t.tracking_type + ' > ' + g.group) + '">' + cats.map(function (c) {
        return '<option value="' + esc(c.id) + '">' + esc(c.label || c.id) + '</option>';
      }).join('') + '</optgroup>';
    }).join('');
  }).join('');
}

export function spendMapOpen(idx) {
  var d = window.spendingData || {};
  var cat = (d.unmapped_categories || [])[idx];
  if (cat === undefined) return;
  if (window.spendMapState && window.spendMapState.idx === idx) { window.spendMapState = null; renderMain(); return; }
  window.spendMapState = { idx: idx, cat: cat, taxonomy: null, error: '' };
  renderMain();
  api('/api/spending/taxonomy').then(function (res) {
    if (!window.spendMapState || window.spendMapState.idx !== idx) return;
    if (res && res.success) window.spendMapState.taxonomy = res.taxonomy || [];
    else window.spendMapState.error = (res && res.error) || 'Could not load categories.';
    renderMain();
  }).catch(function (e) {
    if (window.spendMapState) { window.spendMapState.error = e.message || 'Network error.'; renderMain(); }
  });
}

export function spendMapFilter(idx, q) {
  var sel = document.getElementById('spendMapSel' + idx);
  if (!sel) return;
  q = String(q || '').toLowerCase().trim();
  Array.prototype.forEach.call(sel.querySelectorAll('option'), function (o) {
    if (o.value === '__new__') return;
    o.hidden = !!q && o.textContent.toLowerCase().indexOf(q) < 0 && (o.parentNode.label || '').toLowerCase().indexOf(q) < 0;
  });
}

export function spendMapSelChanged(idx) {
  var sel = document.getElementById('spendMapSel' + idx);
  var box = document.getElementById('spendMapNew' + idx);
  if (box && sel) box.style.display = sel.value === '__new__' ? '' : 'none';
}

export function spendMapConfirm(idx) {
  var st = window.spendMapState;
  if (!st || st.idx !== idx) return;
  var val = function (id) { var el = document.getElementById(id); return el ? el.value : ''; };
  var sel = val('spendMapSel' + idx);
  var choice = sel === '__new__'
    ? { mode: 'new', tracking_type: val('spendMapTT' + idx), group: val('spendMapGrp' + idx), label: val('spendMapLbl' + idx) }
    : { mode: 'existing', category_id: sel };
  var req = spendMapRequest(st.cat, choice);
  if (req.error) { st.error = req.error; renderMain(); return; }
  st.busy = true;
  api(req.path, { method: 'POST', body: JSON.stringify(req.body) }).then(function (res) {
    if (res && res.success) { window.spendMapState = null; loadSpendingDashboard(true); }
    else { st.busy = false; st.error = (res && res.error) || 'Mapping failed.'; renderMain(); }
  }).catch(function (e) { st.busy = false; st.error = e.message || 'Network error.'; renderMain(); });
}

function spendMapPanelHtml(st) {
  var i = st.idx;
  if (!st.taxonomy) return '<div class="spend-map-panel small">' + (st.error ? esc(st.error) : 'Loading categories...') + '</div>';
  var tts = st.taxonomy.map(function (t) { return t.tracking_type; });
  var groups = {};
  st.taxonomy.forEach(function (t) { (t.groups || []).forEach(function (g) { groups[g.group] = 1; }); });
  return '<div class="spend-map-panel">' +
    '<input type="search" placeholder="Search categories..." oninput="spendMapFilter(' + i + ',this.value)"> ' +
    '<select id="spendMapSel' + i + '" onchange="spendMapSelChanged(' + i + ')"><option value="">Choose a category...</option>' +
    spendMapOptionsHtml(st.taxonomy) + '<option value="__new__">New category...</option></select>' +
    '<div id="spendMapNew' + i + '" style="display:none;margin-top:6px">' +
    '<label>Tracking type <select id="spendMapTT' + i + '">' + tts.map(function (t) { return '<option>' + esc(t) + '</option>'; }).join('') + '</select></label> ' +
    '<label>Group <input id="spendMapGrp' + i + '" list="spendMapGrpList' + i + '" value="Other"></label>' +
    '<datalist id="spendMapGrpList' + i + '">' + Object.keys(groups).map(function (g) { return '<option value="' + esc(g) + '">'; }).join('') + '</datalist> ' +
    '<label>Label <input id="spendMapLbl' + i + '" value="' + esc(st.cat) + '"></label></div>' +
    '<div style="margin-top:6px"><button class="btn primary" type="button"' + (st.busy ? ' disabled' : '') + ' onclick="spendMapConfirm(' + i + ')">Map</button> ' +
    '<button class="btn" type="button" onclick="spendMapOpen(' + i + ')">Cancel</button>' +
    (st.error ? ' <span class="small" style="color:#b00020">' + esc(st.error) + '</span>' : '') + '</div></div>';
}

export function renderUnmappedWarning(d) {
  var cats = d.unmapped_categories || [];
  if (!cats.length) return '';
  var open = window.spendMapState;
  return '<div class="missing-list"><h3>' + cats.length + ' unmapped categories</h3>' +
    '<p>These transaction categories do not yet have a canonical Spending Category assignment and default to the Other group. Use <b>Map to category</b> to assign one.</p>' +
    '<ul>' + cats.map(function (c, i) {
      return '<li>' + esc(c) + ' <button class="btn" type="button" onclick="spendMapOpen(' + i + ')">Map to category</button>' +
        (open && open.idx === i ? spendMapPanelHtml(open) : '') + '</li>';
    }).join('') + '</ul></div>';
}

// Wave 6.4 (system review 2026-08-04, architect finding
// frontend-single-global-namespace, §3.2 "leaves inward"): this is the first
// file converted to a real ES module. dashboard.js and the other
// still-classic scripts loaded earlier in index.html call these functions as
// bare globals (and this file's own rendered HTML uses inline
// onclick="toggleSpendingGroup(...)" handlers, which always look up
// window.<name>) -- ES module top-level declarations do NOT auto-attach to
// window the way classic-script declarations do, so every export needed by
// an existing non-module caller is re-attached here explicitly. New code
// should prefer `import { fn } from './spending_dashboard.js'` instead of
// the window.* form; this bridge exists only for callers that can't be
// converted in the same pass.
Object.assign(window, {
  fmtSpend, fmtVariancePct, spendYtd, spendAnnualized,
  spendBudget, spendProjectionSeed, spendHasReconcileValue, loadSpendingDashboard,
  seedSpendingBudget, applySpendingForecast, toggleSpendingKey, toggleSpendingGroup,
  toggleSpendingCat, toggleSpendingType, collapseAllSpending, toggleSpendingExceptionsOnly,
  renderSpendingDashboard,
  renderSpendingSummary, renderSpendingBars, renderSpendingMonthly, renderModelManaged,
  renderBusinessSection, renderUnmappedWarning,
  spendMapOpen, spendMapFilter, spendMapSelChanged, spendMapConfirm,
});
