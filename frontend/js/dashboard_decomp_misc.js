// dashboard_decomp_misc.js -- small, unrelated leaf pieces extracted from
// dashboard.js purely to keep it under its line-count ratchet
// (tests/test_frontend_size_ratchet.py). Loaded as an ES module (like
// dashboard_decomp_workbook_formatting.js), so every function/var used from
// an inline onclick/oninput HTML attribute is explicitly bridged onto
// `window` at the bottom of this file.

// ── #266: Next Housing Step per-field "restore app estimate" ───────────────
// housingLastEstimate caches the last geography-computed estimate fetched
// per Next Housing Step (dashboard.js's estimateHousingFromState) so a
// single field can be reset to the app's computed value without a fresh API
// call and without touching any other field the user has since edited.
window.housingLastEstimate = {};
window.applyHousingEstimateField = function (stepNum, label, val) {
  if (val === null || val === undefined) return false;
  const r = window.rows.find(
    (x) =>
      x.section === "Housing" &&
      window.norm(x.subsection || "") === "next_step_" + stepNum &&
      window.norm(x.label) === label,
  );
  if (!r) return false;
  const display =
    typeof val === "number" && (label.includes("pct") || label === "mortgage_rate_pct")
      ? (val * 100).toFixed(2) + "%"
      : String(val);
  window.editValue(r.row_index, display, null);
  return true;
};
function restoreHousingEstimateField(stepNum, label) {
  const cached = window.housingLastEstimate[stepNum];
  if (!cached || !(label in cached)) {
    window.showMessage('Click "Estimate fields" first to compute a value to restore.', "error");
    return;
  }
  if (window.applyHousingEstimateField(stepNum, label, cached[label])) {
    window.renderMain();
    window.showMessage("Restored to the app-computed estimate.");
  }
}

// ── #270: DAF contribution recommendation + funding-account preference ─────
// Read-only recommendation fetched from /api/daf/recommendation (maximizes
// within the IRS AGI ceiling; see src/daf_optimizer.py). "Apply" writes the
// number into the plan's existing daf_amount field -- the projection engine
// already reads that field, so no engine change is needed here. The funding
// preference reuses #276's per-account withdrawal-priority override: picking
// an account here just bumps that account to draw-priority 1, so the normal
// cascade (which already draws tax-deferred before taxable) pulls the DAF
// cash from that specific account first.
window.dafRecommendation = null;
window.dafFundingAccounts = null;
async function loadDafFundingAccounts() {
  try {
    const out = await window.api("/api/withdrawal-account-order");
    window.dafFundingAccounts = (out && out.accounts) || [];
  } catch (e) {
    window.dafFundingAccounts = [];
  }
  window.renderMain();
}
async function fetchDafRecommendation(appreciated) {
  try {
    const out = await window.api("/api/daf/recommendation", {
      method: "POST",
      body: JSON.stringify({ appreciated: !!appreciated }),
    });
    window.dafRecommendation = out && out.success ? out : null;
    if (!window.dafRecommendation) window.showMessage((out && out.error) || "Could not compute a recommendation.", "error");
  } catch (e) {
    window.dafRecommendation = null;
    window.showMessage("Error fetching DAF recommendation: " + e.message, "error");
  }
  window.renderMain();
}
function applyDafRecommendation() {
  const rec = window.dafRecommendation;
  if (!rec) return;
  const amtRow = (window.rows || []).find((r) => r.section === "DAF" && window.norm(r.label) === "contribution_amount");
  const apprRow = (window.rows || []).find((r) => r.section === "DAF" && window.norm(r.label) === "contribution_is_appreciated");
  if (amtRow) window.editValue(amtRow.row_index, String(Math.round(rec.recommended_amount)), null);
  if (apprRow) window.editValue(apprRow.row_index, rec.appreciated ? "TRUE" : "FALSE", null);
  window.renderMain();
  window.showMessage("Applied recommended DAF contribution of $" + Math.round(rec.recommended_amount).toLocaleString() + ".");
}
async function setDafFundingAccount(acctId) {
  if (!acctId) return;
  try {
    const cur = await window.api("/api/withdrawal-account-order");
    const accounts = (cur && cur.accounts) || [];
    const payload = accounts.map((a) => ({ account_id: a.account_id, priority: a.account_id === acctId ? "1" : a.priority }));
    await window.api("/api/withdrawal-account-order", { method: "POST", body: JSON.stringify({ accounts: payload }) });
    window.showMessage(acctId + " set to draw first (Withdrawal Order page) so it funds the DAF contribution.");
  } catch (e) {
    window.showMessage("Could not set funding account preference: " + e.message, "error");
  }
}
function dafRecommendationPanelHtml() {
  const rec = window.dafRecommendation;
  const apprChecked = rec && rec.appreciated;
  let html = '<div class="section-note daf-recommendation">';
  html += '<b>Recommended contribution.</b> ';
  html +=
    '<button class="btn tiny" type="button" onclick="fetchDafRecommendation(false)">Recommend (cash, 60% AGI)</button> ' +
    '<button class="btn tiny" type="button" onclick="fetchDafRecommendation(true)">Recommend (appreciated holdings, 30% AGI)</button>';
  if (rec) {
    html +=
      '<div style="margin-top:6px"><b>$' +
      Math.round(rec.recommended_amount).toLocaleString() +
      '</b> for ' +
      rec.year +
      ' (' +
      (apprChecked ? "appreciated holdings" : "cash") +
      ') <button class="btn tiny primary" type="button" onclick="applyDafRecommendation()">Apply</button></div>';
    html += '<ul class="small">' + rec.notes.map((n) => "<li>" + window.esc(n) + "</li>").join("") + "</ul>";
  }
  html += "</div>";
  if (!window.dafFundingAccounts) setTimeout(() => loadDafFundingAccounts(), 0);
  const acctOpts = (window.dafFundingAccounts || [])
    .map((a) => '<option value="' + window.esc(a.account_id) + '">' + window.esc(a.account_id) + "</option>")
    .join("");
  html +=
    '<div class="section-note small"><b>Fund from:</b> prefer selling/transferring cash from a specific account (default/preferred: tax-deferred accounts first, per the plan\'s optimized withdrawal order). ' +
    '<select onchange="setDafFundingAccount(this.value)"><option value="">Use default optimized order</option>' +
    acctOpts +
    "</select></div>";
  return html;
}
Object.assign(window, { fetchDafRecommendation, applyDafRecommendation, setDafFundingAccount, dafRecommendationPanelHtml, loadDafFundingAccounts });

// ── #276: individual-account withdrawal draw-order override ────────────────
// The account-TYPE cascade is fixed by the engine (see
// FIXED_WITHDRAWAL_CASCADE_DESCRIPTION in dashboard.js); this is the
// individual-ACCOUNT-level override within whichever type-slot an account
// falls into (e.g. which of two taxable brokerage accounts drains first).
// State lives here, not on window via defineProperty, because nothing
// outside this file's own render/update functions reads or assigns it.
let withdrawalAccountOrder = null,
  withdrawalAccountOrderChanged = false,
  // Registry/discovery order as returned by the API (always the same array
  // order regardless of any saved priority override -- see
  // withdrawal_account_order_payload() in strategy_asset_service.py). Kept
  // separately from withdrawalAccountOrder (which is re-sorted to the
  // current EFFECTIVE order for display/dragging) so "Reset to default
  // order" can restore it without a round trip.
  withdrawalAccountOrderDefaultIds = null,
  _withdrawalOrderDragIdx = null;

async function loadWithdrawalAccountOrder(force) {
  if (withdrawalAccountOrder && !force) return;
  try {
    const out = await window.api("/api/withdrawal-account-order");
    const accounts = (out && out.accounts) || [];
    withdrawalAccountOrderDefaultIds = accounts.map((r) => r.account_id);
    withdrawalAccountOrder = [...accounts].sort(
      (a, b) => Number(a.priority || 0) - Number(b.priority || 0),
    );
  } catch (e) {
    withdrawalAccountOrder = [];
    withdrawalAccountOrderDefaultIds = [];
  }
  withdrawalAccountOrderChanged = false;
  window.renderMain();
}
function _renumberWithdrawalAccountOrder() {
  (withdrawalAccountOrder || []).forEach((r, i) => (r.priority = String(i + 1)));
}
function withdrawalOrderDragStart(e, i) {
  _withdrawalOrderDragIdx = i;
  if (e.dataTransfer) {
    e.dataTransfer.effectAllowed = "move";
    try {
      e.dataTransfer.setData("text/plain", String(i));
    } catch (_e) {}
  }
}
function withdrawalOrderDragOver(e) {
  e.preventDefault();
  if (e.dataTransfer) e.dataTransfer.dropEffect = "move";
}
function withdrawalOrderDrop(e, i) {
  e.preventDefault();
  const from = _withdrawalOrderDragIdx;
  _withdrawalOrderDragIdx = null;
  if (from === null || from === undefined || from === i || !withdrawalAccountOrder) return;
  const [moved] = withdrawalAccountOrder.splice(from, 1);
  withdrawalAccountOrder.splice(i, 0, moved);
  _renumberWithdrawalAccountOrder();
  withdrawalAccountOrderChanged = true;
  window.renderMain();
}
function withdrawalOrderDragEnd() {
  _withdrawalOrderDragIdx = null;
}
async function saveWithdrawalAccountOrder() {
  try {
    const out = await window.api("/api/withdrawal-account-order", {
      method: "POST",
      body: JSON.stringify({ accounts: withdrawalAccountOrder || [] }),
    });
    if (out && out.success) {
      withdrawalAccountOrderChanged = false;
      window.showMessage("Withdrawal account order saved.", "good");
    } else {
      window.showMessage((out && out.error) || "Save failed.", "error");
    }
  } catch (e) {
    window.showMessage("Save failed: " + e.message, "error");
  }
  window.renderMain();
}
// Plain primitive `let` isn't visible on window as a live value once
// reassigned, so autosave-on-navigation-away (saveWorkingCopy() in
// dashboard_decomp_row_model.js) reads dirtiness through this getter instead.
function withdrawalAccountOrderIsDirty() {
  return withdrawalAccountOrderChanged;
}
function resetWithdrawalAccountOrderToDefault() {
  if (!withdrawalAccountOrder || !withdrawalAccountOrderDefaultIds) return;
  const byId = new Map(withdrawalAccountOrder.map((r) => [r.account_id, r]));
  withdrawalAccountOrder = withdrawalAccountOrderDefaultIds.map(
    (aid) => byId.get(aid) || { account_id: aid, priority: "" },
  );
  _renumberWithdrawalAccountOrder();
  withdrawalAccountOrderChanged = true;
  window.renderMain();
}
// Renders the editable account list; dashboard.js's renderWithdrawalOrderTable()
// calls this for the part below the fixed-cascade note. Reordering is
// drag-and-drop (grab the 4-dot handle) rather than typed priority numbers --
// draw order is entirely defined by row position, so no number column is
// needed once dragging is available.
function withdrawalAccountOrderEditorHtml() {
  if (!withdrawalAccountOrder) setTimeout(() => loadWithdrawalAccountOrder(false), 0);
  const esc = window.esc;
  const displayName = window.translatePersonPlaceholders || ((s) => s);
  const dragHandle =
    '<svg class="drag-handle-icon" width="14" height="14" viewBox="0 0 14 14" aria-hidden="true" focusable="false"><circle cx="4" cy="4" r="1.7"></circle><circle cx="10" cy="4" r="1.7"></circle><circle cx="4" cy="10" r="1.7"></circle><circle cx="10" cy="10" r="1.7"></circle></svg>';
  const rowsHtml = (withdrawalAccountOrder || [])
    .map(
      (r, i) =>
        `<tr draggable="true" class="withdrawal-order-row" ondragstart="withdrawalOrderDragStart(event,${i})" ondragover="withdrawalOrderDragOver(event)" ondrop="withdrawalOrderDrop(event,${i})" ondragend="withdrawalOrderDragEnd()"><td class="drag-handle-cell" title="Drag to reorder">${dragHandle}</td><td>${esc(displayName(r.account_id))}</td></tr>`,
    )
    .join("");
  if (!withdrawalAccountOrder) return '<p class="small">Loading accounts…</p>';
  if (!withdrawalAccountOrder.length)
    return '<p class="small">No accounts found yet. Add accounts on Investment Holdings first.</p>';
  return `<div class="table-actions"><button class="btn primary" type="button" ${withdrawalAccountOrderChanged ? "" : "disabled"} onclick="saveWithdrawalAccountOrder()">Save account order</button><button class="btn" type="button" onclick="resetWithdrawalAccountOrderToDefault()">Reset to default order</button><button class="btn" type="button" onclick="loadWithdrawalAccountOrder(true)">Reload</button></div><div class="section-note small">Drag the <b>⠿</b> handle to reorder accounts drawn first within their type. Order saves automatically when you leave this section.</div><div class="lot-table-wrap"><table class="lot-table withdrawal-order-table"><thead><tr><th style="width:36px"></th><th>Account (drawn top to bottom)</th></tr></thead><tbody>${rowsHtml}</tbody></table></div>`;
}

// ── #274: unified Build Impact change summary ───────────────────────────────
// Merges "user input changes" and "admin/config changes" into one table with
// a Source column, instead of two separately-headed sections that implied
// admin/config changes only ever happen from Settings pages.
function unifiedBuildChangeSummaryHtml(changes, adminEvents) {
  const esc = window.esc;
  const userChanges = Array.isArray(changes) ? changes : window.capturedSessionChanges();
  const evs = Array.isArray(adminEvents) ? adminEvents : [];
  const rows = [];
  const scenarioOnly = userChanges.filter((c) =>
    String(c.scope || "")
      .toLowerCase()
      .includes("scenario analysis"),
  );
  userChanges.forEach((c) => {
    const source = c.sourceStep
      ? window.buildSourceJumpHtml(c.sourceStep, c.sourceTitle || window.stepTitleById(c.sourceStep))
      : esc(c.group || "—");
    rows.push({
      factor: esc(c.label),
      context: c.group ? `${esc(c.group)}${c.scope ? ` · ${esc(c.scope)}` : ""}` : "",
      source,
      before: esc(c.before || "blank"),
      after: esc(c.after || "blank"),
    });
  });
  evs.forEach((ev) => {
    const file = ev.file || ev.kind || "admin config";
    const by = ev.changed_by || "";
    const chs = (ev.changes || []).slice(0, 8);
    const list = chs.length
      ? chs
      : [{ label: `${ev.change_count || 1} change${(ev.change_count || 1) === 1 ? "" : "s"}`, before: "", after: "updated" }];
    list.forEach((ch) => {
      rows.push({
        factor: esc(ch.label || ""),
        context: "",
        source: `Admin: ${esc(file)}${by ? ` · ${esc(by)}` : ""}`,
        before: esc(ch.before || "blank"),
        after: esc(ch.after || "blank"),
      });
    });
  });
  if (!rows.length)
    return '<p class="small">No input or configuration changes were captured before this build.</p>';
  let html = scenarioOnly.length
    ? `<div class="section-note warning"><b>${scenarioOnly.length} scenario-only change${scenarioOnly.length === 1 ? "" : "s"} captured.</b> These values are used in the workbook Scenario Analysis sheet but do not move the headline Build Impact cards unless the matching base-plan input is also changed.</div>`
    : "";
  html +=
    '<table class="change-table"><thead><tr><th>Factor</th><th>Source</th><th>Before</th><th>After</th></tr></thead><tbody>';
  rows.slice(0, 40).forEach((r) => {
    html += `<tr><td><div class="change-factor">${r.factor}</div>${r.context ? `<div class="change-context">${r.context}</div>` : ""}</td><td>${r.source}</td><td>${r.before}</td><td>${r.after}</td></tr>`;
  });
  if (rows.length > 40)
    html += `<tr><td colspan="4" class="small">${rows.length - 40} more change${rows.length - 40 === 1 ? "" : "s"} captured.</td></tr>`;
  html += "</tbody></table>";
  return html;
}

Object.assign(window, {
  restoreHousingEstimateField,
  loadWithdrawalAccountOrder,
  saveWithdrawalAccountOrder,
  resetWithdrawalAccountOrderToDefault,
  withdrawalAccountOrderEditorHtml,
  withdrawalAccountOrderIsDirty,
  withdrawalOrderDragStart,
  withdrawalOrderDragOver,
  withdrawalOrderDrop,
  withdrawalOrderDragEnd,
  unifiedBuildChangeSummaryHtml,
});
