/* Spending Dashboard — budget-vs-actual tracker for core spending groups.
   Loaded by index.html, renders when activeStep === 'spending_dashboard'. */

var spendingData = null;
var spendingLoading = false;
var spendingError = '';
var spendingExpandedGroup = null;
var spendingExpandedCat = null;

function renderModelStatusPanel(d) {
  var budget = d.budget_total || 0;
  var annualized = d.annualized_total || 0;
  var modelCore = d.model_core_spending || 0;
  var diff = annualized - modelCore;
  var absDiff = Math.abs(diff);
  var isOk = modelCore > 0 && absDiff < modelCore * 0.03;
  var statusMsg = '';
  if (!modelCore) {
    statusMsg = 'Retirement model core spending not set. Set it on the Core Spending tab or sync from actuals below.';
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
  html += '<div class="spend-model-card-label">Annual Budget (by Category)</div>';
  html += '<div class="spend-model-card-value">' + (budget ? fmtSpend(budget) : '—') + '</div>';
  html += '<div class="spend-model-card-sub">' + (budget ? 'Sum of your spending group targets' : 'Not set — initialize below') + '</div>';
  html += '</div>';
  html += '<div class="spend-model-card">';
  html += '<div class="spend-model-card-label">YTD Annualized Rate</div>';
  html += '<div class="spend-model-card-value">' + (annualized ? fmtSpend(annualized) : '—') + '</div>';
  html += '<div class="spend-model-card-sub">' + (d.days_elapsed ? 'Based on ' + d.days_elapsed + ' days of transactions' : 'No transactions loaded') + '</div>';
  html += '</div>';
  html += '<div class="spend-model-card highlight">';
  html += '<div class="spend-model-card-label">30-Year Projection Uses</div>';
  html += '<div class="spend-model-card-value">' + (modelCore ? fmtSpend(modelCore) : '—') + '</div>';
  html += '<div class="spend-model-card-sub">This is what your retirement model is based on — does NOT update automatically</div>';
  html += '</div>';
  html += '</div>';
  html += '<div class="spend-model-status-row">';
  html += '<span class="spend-model-status-msg ' + (isOk ? 'ok' : 'warn') + '">' + statusMsg + '</span>';
  if (annualized > 0) {
    html += '<button class="btn good" data-requires-app="1" onclick="applySpendingForecast()" title="Updates the core spending assumption used by the 30-year projection">Sync Actual Rate → 30-Year Model</button>';
  }
  html += '</div>';
  html += '</div>';
  return html;
}

function fmtSpend(n) { var v = Math.round(Number(n) || 0); return (v < 0 ? '-$' : '$') + Math.abs(v).toLocaleString('en-US') }
function fmtPct(n) { var v = Number(n) || 0; return (v > 0 ? '+' : '') + v.toFixed(1) + '%' }

function loadSpendingDashboard(force) {
  if (spendingLoading && !force) return;
  spendingLoading = true;
  spendingError = '';
  renderMain();
  api('/api/spending/dashboard').then(function (data) {
    spendingLoading = false;
    if (data && data.success) { spendingData = data; spendingError = '' }
    else { spendingError = (data && data.error) || 'Failed to load spending data.' }
    renderMain();
  }).catch(function (err) {
    spendingLoading = false;
    spendingError = err.message || 'Network error loading spending dashboard.';
    renderMain();
  });
}

function seedSpendingBudget() {
  api('/api/spending/budget/seed', { method: 'POST', body: '{}' }).then(function (res) {
    if (res && res.success) {
      showMessage('Budget seeded from actuals. Reload to see allocations.', 'ok');
      loadSpendingDashboard(true);
    } else {
      showMessage((res && res.error) || 'Seed failed.', 'error');
    }
  }).catch(function (e) { showMessage('Seed error: ' + e.message, 'error') });
}

function applySpendingForecast() {
  if (!spendingData) return;
  if(ytdTransactionsChanged||ytdAccountsChanged){
    showMessage('Transaction data has changed since the dashboard loaded. Refresh the Spending tab before syncing.','warn');
    return;
  }
  var forecast = spendingData.forecast_total;
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
  showMessage('Applied ' + fmtSpend(forecast) + ' as core spending. Save Changes to persist.', 'ok');
  renderMain();
}

function toggleSpendingGroup(group) {
  if (spendingExpandedGroup === group) { spendingExpandedGroup = null; spendingExpandedCat = null; }
  else { spendingExpandedGroup = group; spendingExpandedCat = null; }
  renderMain();
}

function toggleSpendingCat(key) {
  spendingExpandedCat = spendingExpandedCat === key ? null : key;
  renderMain();
}

function renderSpendingDashboard() {
  if (!spendingData && !spendingLoading && !spendingError) {
    setTimeout(function () { loadSpendingDashboard(false) }, 0);
  }
  if (spendingLoading) {
    return '<div class="holdings spending-dashboard"><div class="detail-loading-card">' +
      '<h3>Loading spending tracker</h3><p class="small">Aggregating transactions and computing budget comparisons...</p></div></div>';
  }
  if (spendingError && !spendingData) {
    return '<div class="holdings spending-dashboard"><div class="missing-list"><h3>Spending data unavailable</h3>' +
      '<p>' + esc(spendingError) + '</p></div>' +
      '<div class="table-actions"><button class="btn" onclick="loadSpendingDashboard(true)">Retry</button></div></div>';
  }
  var d = spendingData || {};
  if (!d.enabled) {
    return '<div class="holdings spending-dashboard"><div class="question"><b>No transaction data loaded.</b> ' +
      'Import transactions on the <a href="#" onclick="setStep(\'ytd_transactions\');return false">Income &amp; Expense Transactions tab</a> first, then return here to track budget vs actuals.</div></div>';
  }

  var html = '<div class="holdings spending-dashboard">';
  html += '<div class="spend-taxonomy-card"><b>How spending is organized:</b> ' +
    '<span><b>Core Budget</b> — categories mapped from your imported transactions;</span> ' +
    '<span><b>Model-Managed</b> — Housing &amp; Healthcare entered in the Planning steps;</span> ' +
    '<span><b>Business</b> — self-employment costs modeled separately.</span></div>';
  // YTD Performance Summary (badges + charts + top categories)
  var ytdSummaryHtml = (typeof renderYtdSummary === 'function') ? renderYtdSummary() : '';
  if (ytdSummaryHtml) {
    html += '<h3 class="group-title" style="margin:0 20px 12px">YTD Performance</h3>';
    html += ytdSummaryHtml;
    html += '<h3 class="group-title" style="margin:16px 20px 8px">Spending Budget Tracker</h3>';
  }
  html += renderModelStatusPanel(d);
  html += renderSpendingSummary(d);
  html += renderSpendingBars(d);
  html += renderSpendingMonthly(d);
  if (d.model_managed && Object.keys(d.model_managed).length) html += renderModelManaged(d);
  if (d.business) html += renderBusinessSection(d);
  if (d.unmapped_categories && d.unmapped_categories.length) html += renderUnmappedWarning(d);
  html += '<div class="table-actions">';
  html += '<button class="btn" onclick="loadSpendingDashboard(true)">Refresh</button>';
  if (!d.budget_total) html += '<button class="btn primary" data-requires-app="1" onclick="seedSpendingBudget()" title="Creates category budget targets based on current actual spending proportions">Initialize Budget from Actual Spending</button>';
  if (d.forecast_total > 0) html += '<button class="btn good" data-requires-app="1" onclick="applySpendingForecast()" title="Updates the core spending assumption used by the 30-year retirement projection">Sync Actual Rate → 30-Year Model</button>';
  html += '</div>';
  html += '</div>';
  return html;
}

function renderSpendingSummary(d) {
  var html = '<div class="spend-summary">';
  html += '<div class="spend-kpi"><span class="spend-kpi-value">' + fmtSpend(d.actuals_total) + '</span><span class="spend-kpi-label">YTD Actual Spending</span></div>';
  html += '<div class="spend-kpi"><span class="spend-kpi-value">' + fmtSpend(d.annualized_total) + '</span><span class="spend-kpi-label">Annualized Rate</span></div>';
  html += '<div class="spend-kpi"><span class="spend-kpi-value">' + fmtSpend(d.budget_total || d.model_core_spending) + '</span><span class="spend-kpi-label">' + (d.budget_total ? 'Total Budget' : 'Model Core Spending') + '</span></div>';
  var vpct = d.variance_pct || 0;
  var cls = vpct > 15 ? 'spend-kpi over' : vpct > 5 ? 'spend-kpi watch' : 'spend-kpi ok';
  html += '<div class="' + cls + '"><span class="spend-kpi-value">' + fmtPct(vpct) + '</span><span class="spend-kpi-label">Actual vs. Model</span></div>';
  html += '</div>';
  html += '<p class="small" style="margin:0 0 12px">' + d.days_elapsed + ' days elapsed &middot; annualization factor ' + (d.annualization_factor || 1).toFixed(2) + 'x</p>';
  return html;
}

function renderSpendingBars(d) {
  var groups = d.groups || [];
  if (!groups.length) return '';
  var maxVal = 0;
  groups.forEach(function (g) { maxVal = Math.max(maxVal, g.annualized || 0, g.budget_amount || 0) });
  if (maxVal <= 0) maxVal = 1;

  var html = '<h3 class="group-title">Budget vs Annualized Actual by Group</h3>';
  html += '<div class="spend-bars">';
  html += '<div class="spend-bar-header"><span>Spending Group</span><span>Annualized vs. Budget</span><span>Amount / Budget</span></div>';
  groups.forEach(function (g) {
    var barPct = Math.min(100, ((g.annualized || 0) / maxVal) * 100);
    var budgetPct = g.budget_amount ? Math.min(100, (g.budget_amount / maxVal) * 100) : 0;
    var status = g.status || 'on_track';
    var statusClass = status === 'over_budget' ? 'over' : status === 'watch' ? 'watch' : 'ok';
    var isExpanded = spendingExpandedGroup === g.group;

    html += '<div class="spend-bar-row ' + statusClass + '" onclick="toggleSpendingGroup(\'' + esc(g.group).replace(/'/g, "\\'") + '\')">';
    html += '<div class="spend-bar-label">' + esc(g.group) + '</div>';
    html += '<div class="spend-bar-track">';
    html += '<span class="spend-bar-fill" style="width:' + barPct.toFixed(1) + '%"></span>';
    if (budgetPct > 0) html += '<span class="spend-bar-budget" style="left:' + budgetPct.toFixed(1) + '%"></span>';
    html += '</div>';
    html += '<div class="spend-bar-values">';
    html += '<span>' + fmtSpend(g.annualized) + '</span>';
    if (g.budget_amount) html += '<span class="small">budget ' + fmtSpend(g.budget_amount) + '</span>';
    if (g.variance && g.budget_amount) html += '<span class="small ' + statusClass + '">' + fmtPct(g.variance_pct) + '</span>';
    html += '</div>';
    html += '</div>';

    if (isExpanded && g.categories && g.categories.length) {
      html += '<div class="spend-bar-detail">';
      g.categories.forEach(function (c) {
        var catKey = g.group + '::' + c.category;
        var hasMerchants = c.merchants && c.merchants.length > 1;
        var catExpanded = spendingExpandedCat === catKey;
        html += '<div class="spend-cat-row' + (hasMerchants ? ' expandable' : '') + '"' +
          (hasMerchants ? ' onclick="event.stopPropagation();toggleSpendingCat(\'' + esc(catKey).replace(/'/g, "\\'") + '\')"' : '') + '>' +
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
  });
  html += '</div>';
  return html;
}

function renderSpendingMonthly(d) {
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

function renderModelManaged(d) {
  var MM_LABELS = {housing:'Housing',healthcare:'Healthcare',travel:'Travel',large_disc:'Large Discretionary Expenses',model_managed:'Other Model-Managed'};
  var mm = d.model_managed || {};
  var typeKeys = Object.keys(mm);

  if (!typeKeys.length) return '';

  var html = '<h3 class="group-title">Model-Managed (Not in Core Budget)</h3>';
  html += '<div class="section-note">These categories are tracked separately by the projection model and excluded from the core spending budget.</div>';

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

function renderBusinessSection(d) {
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
      var catExpanded = spendingExpandedCat === catKey;
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

function renderUnmappedWarning(d) {
  var cats = d.unmapped_categories || [];
  if (!cats.length) return '';
  return '<div class="missing-list"><h3>' + cats.length + ' unmapped categories</h3>' +
    '<p>These transaction categories are not in the category map and default to the Other group.</p>' +
    '<ul>' + cats.map(function (c) { return '<li>' + esc(c) + '</li>' }).join('') + '</ul></div>';
}
