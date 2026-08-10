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

// ── #276: individual-account withdrawal draw-order override ────────────────
// The account-TYPE cascade is fixed by the engine (see
// FIXED_WITHDRAWAL_CASCADE_DESCRIPTION in dashboard.js); this is the
// individual-ACCOUNT-level override within whichever type-slot an account
// falls into (e.g. which of two taxable brokerage accounts drains first).
// State lives here, not on window via defineProperty, because nothing
// outside this file's own render/update functions reads or assigns it.
let withdrawalAccountOrder = null,
  withdrawalAccountOrderChanged = false;

async function loadWithdrawalAccountOrder(force) {
  if (withdrawalAccountOrder && !force) return;
  try {
    const out = await window.api("/api/withdrawal-account-order");
    withdrawalAccountOrder = (out && out.accounts) || [];
  } catch (e) {
    withdrawalAccountOrder = [];
  }
  withdrawalAccountOrderChanged = false;
  window.renderMain();
}
function updateWithdrawalAccountOrder(i, value) {
  if (!withdrawalAccountOrder || !withdrawalAccountOrder[i]) return;
  withdrawalAccountOrder[i].priority = value;
  withdrawalAccountOrderChanged = true;
  window.renderMain();
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
function resetWithdrawalAccountOrderToDefault() {
  if (!withdrawalAccountOrder) return;
  withdrawalAccountOrder.forEach((r, i) => (r.priority = String(i + 1)));
  withdrawalAccountOrderChanged = true;
  window.renderMain();
}
// Renders the editable account list; dashboard.js's renderWithdrawalOrderTable()
// calls this for the part below the fixed-cascade note.
function withdrawalAccountOrderEditorHtml() {
  if (!withdrawalAccountOrder) setTimeout(() => loadWithdrawalAccountOrder(false), 0);
  const esc = window.esc;
  const rowsHtml = (withdrawalAccountOrder || [])
    .map(
      (r, i) =>
        `<tr><td>${esc(r.account_id)}</td><td><input type="number" min="1" step="1" value="${esc(r.priority)}" style="width:70px" oninput="updateWithdrawalAccountOrder(${i},this.value)"></td></tr>`,
    )
    .join("");
  if (!withdrawalAccountOrder) return '<p class="small">Loading accounts…</p>';
  if (!withdrawalAccountOrder.length)
    return '<p class="small">No accounts found yet. Add accounts on Investment Holdings first.</p>';
  return `<div class="table-actions"><button class="btn primary" type="button" ${withdrawalAccountOrderChanged ? "" : "disabled"} onclick="saveWithdrawalAccountOrder()">Save account order</button><button class="btn" type="button" onclick="resetWithdrawalAccountOrderToDefault()">Reset to optimized order</button><button class="btn" type="button" onclick="loadWithdrawalAccountOrder(true)">Reload</button></div><div class="lot-table-wrap"><table class="lot-table"><thead><tr><th>Account</th><th>Draw priority (1 = drawn first)</th></tr></thead><tbody>${rowsHtml}</tbody></table></div>`;
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
  updateWithdrawalAccountOrder,
  saveWithdrawalAccountOrder,
  resetWithdrawalAccountOrderToDefault,
  withdrawalAccountOrderEditorHtml,
  unifiedBuildChangeSummaryHtml,
});
