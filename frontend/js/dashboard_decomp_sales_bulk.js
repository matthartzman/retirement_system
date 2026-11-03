// Bulk review of the sale queue (Sales Ledger page, plan step 2.2 follow-up, section 6 item 6): tick several unmatched
// sales, review each one's suggested lots (FIFO draft, FIFO / HIFO / Lowest gain chips as in the single panel), then
// validate and confirm them in one call. Logic and validation live on the server (src/sales_confirm_bulk.py,
// /api/sales/candidates/bulk/*); this only collects drafts. A failing item is reported and does not block the others, and
// one Undo returns the whole batch. Helpers are bare globals; the Sales Ledger page calls renderSalesBulk().

const SB_CLASSES = [["taxable", "Taxable"], ["pre_tax", "Pre-tax"], ["roth", "Roth"], ["hsa", "HSA"]];
const SB_AIDS = [["fifo", "FIFO"], ["hifo", "HIFO"], ["lowest_gain", "Lowest gain"]];
const SB_EPS = 1e-6;

let sbList = null;
let sbSel = new Set();
let sbItems = null; // reviewed items: the server's panel per candidate
let sbDrafts = {}; // candidate_id -> { allocation, tradeDate, taxClass }
let sbResults = {}; // candidate_id -> { ok, error } from the last validate / confirm
let sbMessage = null; // { text, error, undo: { kind, ids } }
let sbLoading = false;
let sbBusy = false;

const sbMoney = (v) => (v === null || v === undefined ? "—" : (Number(v) < 0 ? "-$" : "$") + Math.abs(Number(v)).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }));

// One item's draft: shares allocated, lots over their remaining shares, and whether it is ready to send.
export function sbItemState(item, allocation) {
  const remaining = Object.fromEntries((item.lots || []).map((l) => [l.lot_id, l.remaining]));
  let total = 0;
  const over = [];
  for (const [id, raw] of Object.entries(allocation || {})) {
    const q = Number(raw) || 0;
    if (q < 0 || !(id in remaining) || q > remaining[id] + SB_EPS) over.push(id);
    total += q;
  }
  const target = Number(item.shares) || 0;
  return { total, over, ok: item.ok !== false && item.confirmable !== false && target > 0 && !over.length && Math.abs(total - target) <= SB_EPS };
}

export function sbQueueHtml(candidates, selected) {
  if (!candidates || !candidates.length) return `<p class="muted">No sales are waiting to be matched to lots.</p>`;
  const rows = candidates.map((c) => `<tr><td><input type="checkbox" aria-label="Select the ${esc(c.symbol || "")} sale on ${esc(c.sale_date)}" ${selected.has(c.candidate_id) ? "checked" : ""} onchange="sbToggle(${Number(c.candidate_id)}, this.checked)"></td>` +
    `<td>${esc(c.sale_date)}</td><td>${esc(accountDisplayLabel(c.account))}</td><td>${esc(c.symbol || "needs detail")}</td>` +
    `<td class="rc-num">${c.shares == null ? "—" : esc(String(c.shares))}</td><td class="rc-num">${sbMoney(c.amount)}</td></tr>`).join("");
  return `<div class="rc-scroll"><table class="rc-table"><thead><tr><th><input type="checkbox" aria-label="Select all waiting sales" ${selected.size === candidates.length ? "checked" : ""} onchange="sbToggleAll(this.checked)"></th>` +
    `<th>Date</th><th>Account</th><th>Symbol</th><th class="rc-num">Shares</th><th class="rc-num">Amount</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

export function sbStatusHtml(item, draft, result) {
  if (result && !result.ok) return `<span class="field-error">${esc(result.error)}</span>`;
  if (item.refusal) return `<span class="field-error">${esc(item.refusal)}</span>`;
  const s = sbItemState(item, draft.allocation);
  const tally = `${esc(String(+s.total.toFixed(6)))} of ${esc(String(item.shares ?? "?"))} shares`;
  if (s.over.length) return `${tally} <span class="field-error">A lot is over-allocated.</span>`;
  return s.ok ? `${tally} <span class="muted">ready${result && result.ok ? " (checked)" : ""}</span>` : `${tally} <span class="muted">must equal the shares sold</span>`;
}

export function sbItemHtml(item, draft, result) {
  const id = Number(item.candidate_id);
  if (item.ok === false) return `<div class="sb-item"><p><strong>Sale ${id}</strong> <span class="field-error">${esc(item.error)}</span></p></div>`;
  const c = item.candidate;
  const aids = SB_AIDS.map(([k, label]) => item.aids && item.aids[k] ? `<button class="btn" type="button" onclick="sbFill(${id}, '${k}')">${label}${item.aids[k].gain == null ? "" : ` (gain ${sbMoney(item.aids[k].gain)})`}</button>` : "").join(" ");
  const lots = item.lots.map((l) => `<tr><td>${esc(l.purchase_date || "unknown")}</td><td class="rc-num">${esc(String(l.remaining))}</td><td class="rc-num">${sbMoney(l.basis_per_share)}</td>` +
    `<td>${esc(l.holding_period)}</td><td class="rc-num">${sbMoney(l.implied_gain)}</td>` +
    `<td><input type="number" step="any" min="0" aria-label="Shares to sell from the ${esc(l.purchase_date || "undated")} lot of sale ${id}" value="${esc(String(draft.allocation[l.lot_id] ?? ""))}" ` +
    `oninput="sbSetAlloc(${id}, '${esc(l.lot_id)}', this.value)"></td></tr>`).join("");
  const classes = SB_CLASSES.map(([v, l]) => `<option value="${v}" ${v === draft.taxClass ? "selected" : ""}>${l}</option>`).join("");
  return `<div class="sb-item" id="sbItem${id}"><h4>${esc(item.symbol || "Sale")} · ${esc(accountDisplayLabel(c.account))} · ${esc(String(item.shares ?? "?"))} shares, ${sbMoney(c.amount)} on ${esc(c.sale_date)}</h4>` +
    `<div class="field-grid"><label>Trade date<input type="date" value="${esc(draft.tradeDate)}" onchange="sbSetDate(${id}, this.value)"></label>` +
    `<label>Account type<select onchange="sbSetClass(${id}, this.value)">${classes}</select></label></div>` +
    (item.year_end_case ? `<p class="field-error" role="status">Year-end: settled in ${esc(String(c.sale_date).slice(0, 4))}, suggested trade date is in the prior tax year.</p>` : "") +
    `<p>Fill a draft: ${aids}</p>` +
    (item.lots.length ? `<div class="rc-scroll"><table class="rc-table"><thead><tr><th>Bought</th><th class="rc-num">Remaining</th><th class="rc-num">Basis/share</th><th>Term</th><th class="rc-num">Gain if sold</th><th>Sell shares</th></tr></thead><tbody>${lots}</tbody></table></div>` : `<p class="muted">No lots found for this account and symbol.</p>`) +
    `<p id="sbStatus${id}" role="status">${sbStatusHtml(item, draft, result)}</p></div>`;
}

// The items that would be sent: ready drafts only. The rest stay on screen to be fixed or left.
export const sbReadyItems = (items, drafts) => (items || []).filter((i) => i.ok !== false && sbItemState(i, (drafts[i.candidate_id] || {}).allocation).ok);

function sbPayload(items) {
  return items.map((i) => { const d = sbDrafts[i.candidate_id]; return { candidate_id: i.candidate_id, allocation: d.allocation, tax_class: d.taxClass, trade_date: d.tradeDate, symbol: i.symbol || undefined, shares: i.shares ?? undefined }; });
}

function sbReviewHtml() {
  if (!sbItems) return "";
  const ready = sbReadyItems(sbItems, sbDrafts).length;
  return `<h4>Review (${sbItems.length})</h4>` + sbItems.map((i) => sbItemHtml(i, sbDrafts[i.candidate_id] || { allocation: {}, tradeDate: "", taxClass: "taxable" }, sbResults[i.candidate_id])).join("") +
    `<p><button class="btn" type="button" onclick="sbValidate()" ${sbBusy ? "disabled" : ""}>Check all</button> ` +
    `<button class="btn primary" id="sbConfirmAll" type="button" onclick="sbConfirmAll()" ${ready && !sbBusy ? "" : "disabled"}>Confirm ${ready} ready sale${ready === 1 ? "" : "s"}</button> ` +
    `<button class="btn" type="button" onclick="sbClose()">Close review</button></p>`;
}

function sbBodyHtml() {
  const m = sbMessage;
  const msg = m ? `<p class="${m.error ? "field-error" : "muted"}" role="status">${esc(m.text)}${m.undo ? ` <button class="btn" type="button" onclick="sbUndoBatch()">Undo batch</button>` : ""}</p>` : "";
  const n = sbSel.size;
  return `<h3>Bulk review${sbList ? ` (${sbList.candidates.length} waiting)` : ""}</h3>${msg}` +
    (sbList ? sbQueueHtml(sbList.candidates, sbSel) : `<p class="muted">Loading…</p>`) +
    `<p><button class="btn" type="button" onclick="sbReview()" ${n && !sbBusy ? "" : "disabled"}>Review ${n} selected</button> ` +
    `<button class="btn" type="button" onclick="sbDismiss('before_ledger_start')" ${n && !sbBusy ? "" : "disabled"}>Before ledger start</button> ` +
    `<button class="btn" type="button" onclick="sbDismiss('not_a_sale')" ${n && !sbBusy ? "" : "disabled"}>Not a sale</button></p>` + sbReviewHtml();
}

function sbPaint() {
  const root = document.getElementById("sbRoot");
  if (root) root.innerHTML = sbBodyHtml();
}

export function renderSalesBulk() {
  if (sbList === null && !sbLoading) setTimeout(loadSalesBulk, 0);
  return `<div class="sq-queue sb-bulk" id="sbRoot">${sbBodyHtml()}</div>`;
}

export async function loadSalesBulk() {
  sbLoading = true;
  try {
    const out = await api("/api/sales/candidates?state=unmatched");
    sbList = out && out.success ? out : null;
    if (sbList) sbSel = new Set([...sbSel].filter((id) => sbList.candidates.some((c) => c.candidate_id === id)));
  } catch (e) {
    sbList = null;
    sbMessage = { text: "The sale queue could not be loaded: " + e.message, error: true };
  }
  sbLoading = false;
  sbPaint();
}

async function sbCall(action, body) {
  return api(`/api/sales/candidates/bulk/${action}`, { method: "POST", body: JSON.stringify(body) });
}

// After any change the single-sale queue and the ledger reload too, so every view agrees.
async function sbSync() {
  if (window.loadSalesLedger) window.loadSalesLedger();
  if (window.loadSalesQueue) window.loadSalesQueue();
  await loadSalesBulk();
}

export function sbToggle(id, on) { if (on) sbSel.add(id); else sbSel.delete(id); sbPaint(); }
export function sbToggleAll(on) { sbSel = new Set(on && sbList ? sbList.candidates.map((c) => c.candidate_id) : []); sbPaint(); }

export async function sbReview() {
  sbBusy = true;
  try {
    const out = await sbCall("review", { candidate_ids: [...sbSel] });
    sbItems = out.items;
    sbResults = {};
    sbDrafts = Object.fromEntries(out.items.filter((i) => i.ok).map((i) => [i.candidate_id, { allocation: { ...i.allocation }, tradeDate: i.suggested_trade_date, taxClass: i.tax_class || "taxable" }]));
    sbMessage = null;
  } catch (e) {
    sbMessage = { text: e.message, error: true };
  }
  sbBusy = false;
  sbPaint();
}

export function sbClose() { sbItems = null; sbResults = {}; sbPaint(); }

function sbRefresh(id) {
  const item = (sbItems || []).find((i) => i.candidate_id === id);
  const el = document.getElementById("sbStatus" + id);
  if (item && el) el.innerHTML = sbStatusHtml(item, sbDrafts[id], sbResults[id]);
  const btn = document.getElementById("sbConfirmAll");
  if (btn) { const n = sbReadyItems(sbItems, sbDrafts).length; btn.disabled = !n || sbBusy; btn.textContent = `Confirm ${n} ready sale${n === 1 ? "" : "s"}`; }
}

export function sbSetAlloc(id, lotId, value) {
  const a = sbDrafts[id].allocation;
  if (value === "" || Number(value) === 0) delete a[lotId]; else a[lotId] = Number(value);
  delete sbResults[id];
  sbRefresh(id);
}
export function sbSetDate(id, v) { sbDrafts[id].tradeDate = v; delete sbResults[id]; }
export function sbSetClass(id, v) { sbDrafts[id].taxClass = v; }

// A chip only fills the inputs; the user can edit them, and nothing is saved until Confirm.
export function sbFill(id, method) {
  const item = sbItems.find((i) => i.candidate_id === id);
  const a = item && item.aids[method];
  if (!a) return;
  sbDrafts[id].allocation = { ...a.allocation };
  delete sbResults[id];
  sbPaint();
}

export async function sbValidate() {
  const ready = sbReadyItems(sbItems, sbDrafts);
  if (!ready.length) { sbMessage = { text: "No sale is ready to check yet.", error: true }; return sbPaint(); }
  sbBusy = true;
  try {
    const out = await sbCall("validate", { items: sbPayload(ready) });
    for (const r of out.results) sbResults[r.candidate_id] = r;
    sbMessage = { text: `${out.succeeded} of ${out.results.length} checked sales would be confirmed${out.failed ? `; ${out.failed} would be refused (see below)` : ""}. Nothing was saved.`, error: out.failed > 0 };
  } catch (e) {
    sbMessage = { text: e.message, error: true };
  }
  sbBusy = false;
  sbPaint();
}

export async function sbConfirmAll() {
  const ready = sbReadyItems(sbItems, sbDrafts);
  if (!ready.length) return;
  sbBusy = true;
  try {
    const out = await sbCall("confirm", { items: sbPayload(ready) });
    const done = new Set(out.confirmed);
    for (const r of out.results) if (!r.ok) sbResults[r.candidate_id] = r;
    sbItems = sbItems.filter((i) => !done.has(i.candidate_id));
    sbSel = new Set([...sbSel].filter((id) => !done.has(id)));
    const skipped = (sbItems || []).filter((i) => !sbResults[i.candidate_id]).length;
    sbMessage = { text: `Confirmed ${out.succeeded} sale${out.succeeded === 1 ? "" : "s"}${out.failed ? `; ${out.failed} failed and stay in the review with the reason` : ""}${skipped ? `; ${skipped} not ready were left alone` : ""}.`,
      error: out.failed > 0, undo: out.confirmed.length ? { kind: "confirm", ids: out.confirmed } : null };
    if (!sbItems.length) sbItems = null;
    sbBusy = false;
    return await sbSync();
  } catch (e) {
    sbMessage = { text: e.message, error: true };
  }
  sbBusy = false;
  sbPaint();
}

export async function sbDismiss(reason) {
  sbBusy = true;
  try {
    const out = await sbCall("dismiss", { candidate_ids: [...sbSel], reason });
    const bad = out.results.filter((r) => !r.ok);
    sbItems = null;
    sbMessage = { text: `Dismissed ${out.succeeded} sale${out.succeeded === 1 ? "" : "s"}${bad.length ? `; ${bad.length} refused: ${bad[0].error}` : ""}.`, error: bad.length > 0,
      undo: out.dismissed.length ? { kind: "dismiss", ids: out.dismissed } : null };
    sbSel = new Set();
    sbBusy = false;
    return await sbSync();
  } catch (e) {
    sbMessage = { text: e.message, error: true };
  }
  sbBusy = false;
  sbPaint();
}

export async function sbUndoBatch() {
  const u = sbMessage && sbMessage.undo;
  if (!u) return;
  sbBusy = true;
  try {
    const out = await sbCall(u.kind === "confirm" ? "undo" : "restore", { candidate_ids: u.ids });
    const bad = out.results.filter((r) => !r.ok);
    sbMessage = { text: `Returned ${out.succeeded} sale${out.succeeded === 1 ? "" : "s"} to the queue${u.kind === "confirm" ? " and restored their lots" : ""}${bad.length ? `; ${bad.length} could not be undone: ${bad[0].error}` : ""}.`, error: bad.length > 0 };
    sbItems = null;
  } catch (e) {
    sbMessage = { text: e.message, error: true };
  }
  sbBusy = false;
  await sbSync();
}

Object.assign(window, {
  renderSalesBulk, loadSalesBulk, sbToggle, sbToggleAll, sbReview, sbClose, sbSetAlloc, sbSetDate, sbSetClass, sbFill, sbValidate,
  sbConfirmAll, sbDismiss, sbUndoBatch,
});
