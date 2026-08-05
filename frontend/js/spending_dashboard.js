/* Spending Dashboard — comprehensive income and expense tracker (excludes taxes/transfers).
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
window.spendingDivergencePct = 0;
export function getSpendingDivergencePct() { return window.spendingDivergencePct || 0 }
window.getSpendingDivergencePct = getSpendingDivergencePct;

export function renderModelStatusPanel(d) {
  var budget = d.budget_total || 0;
  var annualized = d.annualized_total || 0;
  var modelCore = d.model_core_spending || 0;
  var diff = annualized - modelCore;
  var absDiff = Math.abs(diff);
  var isOk = modelCore > 0 && absDiff < modelCore * 0.03;
  var statusMsg = '';
  if (!modelCore) {
    statusMsg = 'Retirement model spending categories not set. Set it on the Spending Categories tab or sync from actuals below.';
  } else if (isOk) {
    statusMsg = '✓ Annualized actual is within 3% of your retirement model — you\'re in sync.';
  } else if (diff > 0) {
    statusMsg = '⚠ Spending is running ' + fmtSpend(absDiff) + '/yr ABOVE the retirement model assumption.';
  } else {
    statusMsg = '↓ Spending is running ' + fmtSpend(absDiff) + '/yr below the retirement model assumption.';
  }
  var html = '<div class="spend-model-status">';
  html += '<h3>Retirement Model — Spending Status</h3>';
  html += '<div class="spend-model-grid">';
  html += '<div class="spend-model-card">';
  html += '<div class="spend-model-card-label">Annual Budget</div>';
  html += '<div class="spend-model-card-value">' + (budget ? fmtSpend(budget) : '—') + '</div>';
  html += '<div class="spend-model-card-sub">' + (budget ? 'Current-year category/group budget total' : 'Not set — initialize below') + '</div>';
  html += '</div>';
  html += '<div class="spend-model-card">';
  html += '<div class="spend-model-card-label">This Year Annualized Rate</div>';
  html += '<div class="spend-model-card-value">' + (annualized ? fmtSpend(annualized) : '—') + '</div>';
  html += '<div class="spend-model-card-sub">' + (d.days_elapsed ? 'Based on ' + d.days_elapsed + ' days of transactions' : 'No transactions loaded') + '</div>';
  html += '</div>';
  html += '<div class="spend-model-card highlight">';
  html += '<div class="spend-model-card-label">Projection Seed</div>';
  html += '<div class="spend-model-card-value">' + (modelCore ? fmtSpend(modelCore) : '—') + '</div>';
  html += '<div class="spend-model-card-sub">Current budget-derived amount used to seed projected cash flow</div>';
  html += '</div>';
  html += '</div>';
  html += '<div class="spend-model-status-row">';
  html += '<span class="spend-model-status-msg ' + (isOk ? 'ok' : 'warn') + '">' + statusMsg + '</span>';
  if (annualized > 0) {
    html += '<button class="btn good" data-requires-app="1" onclick="applySpendingForecast()" title="Updates the spending categories assumption used by the 30-year projection">Sync Actual Rate → 30-Year Model</button>';
  }
  html += '</div>';
  html += '</div>';
  return html;
}

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
  renderMain();
  api('/api/spending/dashboard').then(function (data) {
    window.spendingLoading = false;
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
  window.spendingDivergencePct = d.model_core_spending ? ((Number(d.annualized_total || 0) - Number(d.model_core_spending || 0)) / Number(d.model_core_spending || 1)) : (Number(d.variance_pct || 0) / 100);
  if (!d.enabled) {
    return '<div class="holdings spending-dashboard"><div class="question"><b>No transaction data loaded.</b> ' +
      'Import transactions on the <a href="#" onclick="setStep(\'ytd_transactions\');return false">Income &amp; Expense Transactions tab</a> first, then return here to track budget vs actuals.</div></div>';
  }

  var html = '<div class="holdings spending-dashboard">';
  html += '<div class="spend-taxonomy-card"><b>How spending is organized:</b> ' +
    '<span><b>Hierarchy</b> — Tracking Type → Group → Category;</span> ' +
    '<span><b>Included</b> — all Income and all expense Tracking Types;</span> ' +
    '<span><b>Excluded</b> — taxes and transfers.</span></div>';
  // This-year performance summary (badges + charts + top categories)
  var ytdSummaryHtml = (typeof renderYtdSummary === 'function') ? renderYtdSummary() : '';
  if (ytdSummaryHtml) {
    html += '<h3 class="group-title" style="margin:0 20px 12px">This Year Performance</h3>';
    html += ytdSummaryHtml;
    html += '<h3 class="group-title" style="margin:16px 20px 8px">Spending Budget Tracker</h3>';
  }
  html += renderModelStatusPanel(d);
  html += renderSpendingSummary(d);
  html += renderSpendingBars(d);
  html += renderSpendingMonthly(d);
  if (d.model_managed && Object.keys(d.model_managed).length) html += renderModelManaged(d);
  // Business now appears inside the main Tracking Type hierarchy; no separate section below Monthly Trajectory.
  if (d.unmapped_categories && d.unmapped_categories.length) html += renderUnmappedWarning(d);
  html += '<div class="table-actions">';
  html += '<button class="btn" onclick="loadSpendingDashboard(true)">Refresh</button>';
  if (!d.budget_total) html += '<button class="btn primary" data-requires-app="1" onclick="seedSpendingBudget()" title="Creates category budget targets based on current actual spending proportions">Initialize Budget from Actual Spending</button>';
  if (d.forecast_total > 0) html += '<button class="btn good" data-requires-app="1" onclick="applySpendingForecast()" title="Updates the spending categories assumption used by the 30-year retirement projection">Sync Actual Rate → 30-Year Model</button>';
  html += '</div>';
  html += '</div>';
  return html;
}

export function renderSpendingSummary(d) {
  var html = '<div class="spend-summary">';
  html += '<div class="spend-kpi"><span class="spend-kpi-value">' + fmtSpend(d.income_total||0) + '</span><span class="spend-kpi-label">This Year Income</span></div>';
  html += '<div class="spend-kpi"><span class="spend-kpi-value">' + fmtSpend(d.actuals_total) + '</span><span class="spend-kpi-label">This Year Expenses excl. taxes</span></div>';
  html += '<div class="spend-kpi"><span class="spend-kpi-value">' + fmtSpend(d.annualized_total) + '</span><span class="spend-kpi-label">Annualized Actual Expenses</span></div>';
  html += '<div class="spend-kpi"><span class="spend-kpi-value">' + fmtSpend(d.budget_total || d.model_core_spending) + '</span><span class="spend-kpi-label">' + (d.budget_total ? 'Annual Budget' : 'Model Spending Categories') + '</span></div>';
  var vpct = d.variance_pct || 0;
  var cls = vpct > 15 ? 'spend-kpi over' : vpct > 5 ? 'spend-kpi watch' : 'spend-kpi ok';
  html += '<div class="' + cls + '"><span class="spend-kpi-value">' + fmtVariancePct(vpct) + '</span><span class="spend-kpi-label">Actual vs. Model</span></div>';
  html += '</div>';
  html += '<p class="small" style="margin:0 0 12px">' + d.days_elapsed + ' days elapsed &middot; annualization factor ' + (d.annualization_factor || 1).toFixed(2) + 'x</p>';
  return html;
}

export function renderSpendingBars(d) {
  // Full Tracking Type -> Group -> Category hierarchy from the taxonomy summary
  // (each level carries annualized actual + budget). Income is included; taxes/transfers are filtered in the backend.
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
  function barCell(ann, bud) {
    var barPct = Math.min(100, ((ann || 0) / maxVal) * 100);
    var budPct = bud ? Math.min(100, (bud / maxVal) * 100) : 0;
    var h = '<div class="spend-bar-track"><span class="spend-bar-fill" style="width:' + barPct.toFixed(1) + '%"></span>';
    if (budPct > 0) h += '<span class="spend-bar-budget" style="left:' + budPct.toFixed(1) + '%"></span>';
    return h + '</div>';
  }
  function valCell(ytd, ann, bud, seed, st) {
    var h = '<div class="spend-bar-values"><span>This Year ' + fmtSpend(ytd) + '</span>';
    h += '<span class="small">Annualized ' + fmtSpend(ann) + '</span>';
    h += '<span class="small">Budget ' + fmtSpend(bud) + '</span>';
    h += '<span class="small">Projection Seed ' + fmtSpend(seed) + '</span>';
    if (bud && typeof st.vpct === 'number') h += '<span class="small ' + st.cls + '">' + fmtVariancePct(st.vpct) + '</span>';
    return h + '</div>';
  }

  var html = '<h3 class="group-title">Income and Expenses by Tracking Type / Group / Category' +
    (window.spendingExpandedKeys.size ? ' <button class="btn tiny" type="button" onclick="collapseAllSpending()">Collapse all</button>' : '') +
    '</h3>';
  html += '<div class="spend-bars">';
  html += '<div class="spend-bar-header"><span>Tracking type · Group · Category</span><span>Annualized Actual vs. Annual Budget</span><span>YTD Actual | Annualized Actual | Annual Budget | Projection Seed</span></div>';

  types.forEach(function (t) {
    var tt = t.tracking_type;
    var typeExpanded = window.spendingExpandedKeys.has('type:' + tt);
    var tytd = spendYtd(t), tann = spendAnnualized(t), tbud = spendBudget(t), tseed = spendProjectionSeed(t);
    var st = statusFor(tann, tbud);
    html += '<div class="spend-bar-row spend-type-row ' + st.cls + '" onclick="toggleSpendingType(\'' + esc(tt).replace(/'/g, "\\'") + '\')">';
    html += '<div class="spend-bar-label spend-type-label"><span class="spend-level-pill">Tracking Type</span><span class="spend-caret' + (typeExpanded ? ' open' : '') + '"></span><b>' + esc(tt) + '</b></div>';
    html += barCell(tann, tbud) + valCell(tytd, tann, tbud, tseed, st);
    html += '</div>';
    if (!typeExpanded) return;

    (t.groups || []).forEach(function (g) {
      var gkey = tt + '::' + g.group;
      var gExpanded = window.spendingExpandedKeys.has('group:' + gkey);
      var gytd = spendYtd(g), gann = spendAnnualized(g), gbud = spendBudget(g), gseed = spendProjectionSeed(g);
      var gs = statusFor(gann, gbud);
      html += '<div class="spend-bar-row spend-group-row ' + gs.cls + '" onclick="event.stopPropagation();toggleSpendingGroup(\'' + esc(gkey).replace(/'/g, "\\'") + '\')">';
      html += '<div class="spend-bar-label spend-group-label"><span class="spend-level-pill">Group</span><span class="spend-caret' + (gExpanded ? ' open' : '') + '"></span>' + esc(g.group) + '</div>';
      html += barCell(gann, gbud) + valCell(gytd, gann, gbud, gseed, gs);
      html += '</div>';
      if (!gExpanded) return;
      html += '<div class="spend-bar-detail">';
      (g.categories || []).forEach(function (c) {
        var cytd = spendYtd(c), cann = spendAnnualized(c), cbud = spendBudget(c), cseed = spendProjectionSeed(c);
        var cs = statusFor(cann, cbud);
        html += '<div class="spend-cat-row"><span><span class="spend-level-pill">Category</span>' + esc(c.label || c.id) + '</span>' +
          '<span>YTD ' + fmtSpend(cytd) + ' · Annualized ' + fmtSpend(cann) + ' · Budget ' + fmtSpend(cbud) + ' · Projection Seed ' + fmtSpend(cseed) + (cbud ? ' <span class="small ' + cs.cls + '">' + fmtVariancePct(cs.vpct || 0) + '</span>' : '') + '</span></div>';
      });
      html += '</div>';
    });
  });
  html += '</div>';
  return html;
}

export function renderSpendingMonthly(d) {
  var series = d.monthly_series || [];
  if (!series.length) return '';
  var html = '<h3 class="group-title">Monthly Trajectory <span class="small">(all spending except taxes/transfers)</span></h3>';
  html += '<div class="section-note">Includes Housing, Wellness/healthcare, Travel, Large Discretionary, Business, and Core Expense outflows when present in transactions. Taxes and transfers are excluded.</div>';
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

export function renderUnmappedWarning(d) {
  var cats = d.unmapped_categories || [];
  if (!cats.length) return '';
  return '<div class="missing-list"><h3>' + cats.length + ' unmapped categories</h3>' +
    '<p>These transaction categories do not yet have a canonical Spending Category assignment and default to the Other group.</p>' +
    '<ul>' + cats.map(function (c) { return '<li>' + esc(c) + '</li>' }).join('') + '</ul></div>';
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
  renderModelStatusPanel, fmtSpend, fmtVariancePct, spendYtd, spendAnnualized,
  spendBudget, spendProjectionSeed, spendHasReconcileValue, loadSpendingDashboard,
  seedSpendingBudget, applySpendingForecast, toggleSpendingKey, toggleSpendingGroup,
  toggleSpendingCat, toggleSpendingType, collapseAllSpending, renderSpendingDashboard,
  renderSpendingSummary, renderSpendingBars, renderSpendingMonthly, renderModelManaged,
  renderBusinessSection, renderUnmappedWarning,
});
