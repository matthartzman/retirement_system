// Sales queue panel (Sales Ledger page, plan step 2.2): the unmatched sales and the side panel where the user picks
// the specific lots, then Confirms. Logic and validation live on the server (src/sales_confirm.py,
// /api/sales/candidates*); this only collects a draft. FIFO / HIFO / lowest-gain chips fill the draft and save nothing.
// Helpers are bare globals; the Sales Ledger page calls renderSalesQueue() and the queue repaints #sqRoot.

const SQ_CLASSES = [["taxable", "Taxable"], ["pre_tax", "Pre-tax (IRA/401k)"], ["roth", "Roth"], ["hsa", "HSA"]];
const SQ_AIDS = [["fifo", "FIFO"], ["hifo", "HIFO"], ["lowest_gain", "Lowest gain"]];
const SQ_EPS = 1e-6;

let sqList = null;
let sqPanel = null;
let sqDraft = { allocation: {}, tradeDate: "", taxClass: "taxable" };
let sqMessage = null; // { text, error, undoId }
let sqLoading = false;

export const sqMoney = (v) => (v === null || v === undefined ? "—" : (Number(v) < 0 ? "-$" : "$") + Math.abs(Number(v)).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }));

// Where the draft stands: total allocated, lots over their remaining shares, and whether Confirm may be enabled.
export function sqAllocationState(panel, allocation) {
  const remaining = Object.fromEntries((panel.lots || []).map((l) => [l.lot_id, l.remaining]));
  let total = 0;
  const over = [];
  for (const [id, raw] of Object.entries(allocation || {})) {
    const q = Number(raw) || 0;
    if (q < 0 || !(id in remaining) || q > remaining[id] + SQ_EPS) over.push(id);
    total += q;
  }
  const target = Number(panel.shares) || 0;
  return { total, over, ok: panel.confirmable !== false && target > 0 && !over.length && Math.abs(total - target) <= SQ_EPS };
}

export function sqQueueHtml(candidates, selectedId) {
  if (!candidates || !candidates.length) return `<p class="muted">No sales are waiting to be matched to lots.</p>`;
  const rows = candidates.map((c) => `<tr class="${c.candidate_id === selectedId ? "sq-selected" : ""}"><td>${esc(c.sale_date)}</td><td>${esc(accountDisplayLabel(c.account))}</td>` +
    `<td>${esc(c.symbol || "needs detail")}</td><td class="rc-num">${c.shares == null ? "—" : esc(String(c.shares))}</td><td class="rc-num">${sqMoney(c.amount)}</td>` +
    `<td>${esc(c.source === "monarch" ? "Transaction feed" : "Holdings import")}</td><td><button class="btn" type="button" onclick="sqOpen(${Number(c.candidate_id)})">Review</button></td></tr>`).join("");
  return `<div class="rc-scroll"><table class="rc-table"><thead><tr><th>Date</th><th>Account</th><th>Symbol</th><th class="rc-num">Shares</th><th class="rc-num">Amount</th><th>Source</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

export function sqSummaryHtml(panel, draft) {
  const s = sqAllocationState(panel, draft.allocation);
  const msg = s.over.length ? `<span class="field-error">A lot is over-allocated.</span>` : s.ok ? "" : `<span class="muted">Allocated shares must equal the shares sold.</span>`;
  return `${esc(String(+s.total.toFixed(6)))} of ${esc(String(panel.shares ?? "?"))} shares allocated ${msg}`;
}

export function sqPanelHtml(panel, draft) {
  if (!panel) return "";
  const c = panel.candidate;
  const bare = !c.symbol || !c.shares;
  const lots = panel.lots.map((l) => `<tr class="${l.lot_id === panel.only_exact_fit ? "sq-exact" : ""}"><td>${esc(l.purchase_date || "unknown")}</td>` +
    `<td class="rc-num">${esc(String(l.remaining))}</td><td class="rc-num">${sqMoney(l.basis_per_share)}</td><td>${esc(l.holding_period)}</td>` +
    `<td class="rc-num">${sqMoney(l.implied_gain)}</td><td>${l.lot_id === panel.only_exact_fit ? `<span class="muted">only exact fit</span>` : ""}</td>` +
    `<td><input type="number" step="any" min="0" aria-label="Shares to sell from the ${esc(l.purchase_date || "undated")} lot" data-lot="${esc(l.lot_id)}" ` +
    `value="${esc(String(draft.allocation[l.lot_id] ?? ""))}" oninput="sqSetAlloc(this.dataset.lot, this.value)"></td></tr>`).join("");
  const aids = SQ_AIDS.map(([k, label]) => {
    const a = panel.aids[k];
    return a ? `<button class="btn" type="button" onclick="sqFill('${k}')">${label}${a.gain == null ? "" : ` (gain ${sqMoney(a.gain)})`}</button>` : "";
  }).join(" ");
  const classes = SQ_CLASSES.map(([v, l]) => `<option value="${v}" ${v === draft.taxClass ? "selected" : ""}>${l}</option>`).join("");
  return `<div class="sq-panel" id="sqPanel"><h3>${esc(panel.symbol || "Sale")} · ${esc(accountDisplayLabel(c.account))}</h3>` +
    `<p>${esc(String(panel.shares ?? "?"))} shares, ${sqMoney(c.amount)} on ${esc(c.sale_date)} (${esc(c.source)})</p>` +
    (panel.refusal ? `<p class="field-error">${esc(panel.refusal)}</p>` : "") +
    (bare ? `<div class="field-grid"><label>Symbol<input id="sqSymbol" value="${esc(panel.symbol || "")}"></label>` +
      `<label>Shares sold<input id="sqShares" type="number" step="any" value="${esc(String(panel.shares ?? ""))}"></label>` +
      `<button class="btn" type="button" onclick="sqReload()">Show lots</button></div>` : "") +
    `<div class="field-grid"><label>Trade date<input id="sqTrade" type="date" value="${esc(draft.tradeDate)}"></label>` +
    `<label>Account type<select id="sqClass" onchange="sqSetClass(this.value)">${classes}</select></label></div>` +
    (panel.year_end_case ? `<p class="field-error" role="status">Year-end: this sale settled in ${esc(String(c.sale_date).slice(0, 4))} but the suggested trade date is in the prior tax year. Check the date.</p>` : "") +
    (panel.settle_date ? `<p class="muted">The feed shows the settlement date (${esc(panel.settle_date)}); the suggested trade date is the prior business day.</p>` : "") +
    `<p>Fill a draft: ${aids}</p>` +
    (panel.lots.length ? `<div class="rc-scroll"><table class="rc-table"><thead><tr><th>Bought</th><th class="rc-num">Remaining</th><th class="rc-num">Basis/share</th><th>Term</th><th class="rc-num">Gain if sold</th><th></th><th>Sell shares</th></tr></thead><tbody>${lots}</tbody></table></div>` : `<p class="muted">No lots found for this account and symbol.</p>`) +
    `<p id="sqSummary" role="status">${sqSummaryHtml(panel, draft)}</p>` +
    `<button class="btn primary" id="sqConfirm" type="button" onclick="sqConfirm()" ${sqAllocationState(panel, draft.allocation).ok ? "" : "disabled"}>Confirm sale</button> ` +
    `<button class="btn" type="button" onclick="sqDismiss('before_ledger_start')">Before ledger start</button> ` +
    `<button class="btn" type="button" onclick="sqDismiss('not_a_sale')">Not a sale</button></div>`;
}

function sqBodyHtml() {
  const msg = sqMessage ? `<p class="${sqMessage.error ? "field-error" : "muted"}" role="status">${esc(sqMessage.text)}` +
    `${sqMessage.undoId ? ` <button class="btn" type="button" onclick="sqUndo(${Number(sqMessage.undoId)})">Undo</button>` : ""}</p>` : "";
  const waiting = sqList ? sqList.counts.unmatched : 0;
  return `<h3>Sales waiting for lots${sqList ? ` (${waiting})` : ""}</h3>${msg}` +
    (sqList ? sqQueueHtml(sqList.candidates, sqPanel && sqPanel.candidate.candidate_id) : `<p class="muted">Loading…</p>`) + sqPanelHtml(sqPanel, sqDraft);
}

function sqPaint() {
  const root = document.getElementById("sqRoot");
  if (root) root.innerHTML = sqBodyHtml();
}

export function renderSalesQueue() {
  if (sqList === null && !sqLoading) setTimeout(loadSalesQueue, 0);
  return `<div class="sq-queue" id="sqRoot">${sqBodyHtml()}</div>`;
}

export async function loadSalesQueue() {
  sqLoading = true;
  try {
    const out = await api("/api/sales/candidates?state=unmatched");
    sqList = out && out.success ? out : null;
  } catch (e) {
    sqList = null;
    sqMessage = { text: "The sale queue could not be loaded: " + e.message, error: true };
  }
  sqLoading = false;
  sqPaint();
}

async function sqLoadPanel(id, extra = "") {
  try {
    const out = await api(`/api/sales/candidates/${Number(id)}/panel${extra}`);
    sqPanel = out;
    sqDraft = { allocation: {}, tradeDate: out.suggested_trade_date, taxClass: out.tax_class || "taxable" };
  } catch (e) {
    sqMessage = { text: e.message, error: true };
  }
  sqPaint();
}

export const sqOpen = (id) => sqLoadPanel(id);
export function sqReload() {
  const q = new URLSearchParams({ symbol: (document.getElementById("sqSymbol") || {}).value || "", shares: (document.getElementById("sqShares") || {}).value || "" });
  return sqLoadPanel(sqPanel.candidate.candidate_id, "?" + q);
}

function sqRefresh() {
  const sum = document.getElementById("sqSummary");
  if (sum && sqPanel) sum.innerHTML = sqSummaryHtml(sqPanel, sqDraft);
  const btn = document.getElementById("sqConfirm");
  if (btn && sqPanel) btn.disabled = !sqAllocationState(sqPanel, sqDraft.allocation).ok;
}

export function sqSetAlloc(lotId, value) {
  if (value === "" || Number(value) === 0) delete sqDraft.allocation[lotId];
  else sqDraft.allocation[lotId] = Number(value);
  sqRefresh();
}

export function sqSetClass(v) { sqDraft.taxClass = v; }

// A chip only fills the inputs; the user can edit them, and nothing is saved until Confirm.
export function sqFill(method) {
  const a = sqPanel && sqPanel.aids[method];
  if (!a) return;
  sqDraft.allocation = { ...a.allocation };
  sqPaint();
}

async function sqPost(id, action, body, okText, undoId) {
  try {
    const out = await api(`/api/sales/candidates/${Number(id)}/${action}`, { method: "POST", body: JSON.stringify(body || {}) });
    sqMessage = { text: okText, error: false, undoId };
    sqPanel = null;
    if (window.loadSalesLedger) window.loadSalesLedger();
    await loadSalesQueue();
    return out;
  } catch (e) {
    sqMessage = { text: e.message, error: true };
    sqPaint();
  }
}

export function sqConfirm() {
  const c = sqPanel.candidate;
  const field = (id) => (document.getElementById(id) || {}).value;
  const tradeDate = field("sqTrade") || sqDraft.tradeDate;
  return sqPost(c.candidate_id, "confirm", {
    allocation: sqDraft.allocation, tax_class: sqDraft.taxClass, trade_date: tradeDate,
    symbol: field("sqSymbol") || undefined, shares: field("sqShares") || undefined,
  }, "Sale confirmed and the lots reduced.", c.candidate_id);
}

export const sqUndo = (id) => sqPost(id, "undo", null, "Confirmation undone; the sale is waiting again and the lots are restored.");
export const sqDismiss = (reason) => sqPost(sqPanel.candidate.candidate_id, "dismiss", { reason }, "Sale dismissed.");

Object.assign(window, {
  renderSalesQueue, loadSalesQueue, sqOpen, sqReload, sqSetAlloc, sqSetClass, sqFill, sqConfirm, sqUndo, sqDismiss,
});
