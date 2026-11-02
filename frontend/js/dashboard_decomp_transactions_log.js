// Transaction log panel (phase 2 of the transaction log plan): the editable log beside the read-only list in
// dashboard_decomp_transactions.js. Start it from existing imports and holdings, then add, revise, void and transfer.
// Logic lives on the server (src/transactions.py, /api/transactions/*). Helpers are bare globals.

const TL_TYPES = [["buy", "Buy"], ["reinvest", "Reinvest"], ["sell", "Sale / redemption"], ["opening", "Opening lot"]];
const TL_LABEL = { buy: "Buy", reinvest: "Reinvest", sell: "Sale / redemption", transfer_out: "Transfer out", transfer_in: "Transfer in", opening: "Opening lot" };
let tlLog = null;
let tlEdit = null; // txn_id being revised, or null when adding
let tlForm = { txn_date: "", account: "", type: "buy", symbol: "", shares: "", price: "" };
let tlXfer = { from_account: "", to_account: "", symbol: "", txn_date: "", picks: {} };
let tlMessage = null;

const tlNum = (v) => esc(String(Math.round(Number(v) * 1e6) / 1e6));
const tlAccounts = (log) => [...new Set([...(log.rows || []).map((r) => r.account), ...(log.open || []).map((l) => l.account)])].sort();
const tlSelect = (id, opts, cur, fn) => `<select id="${id}" onchange="${fn}(this.value)">${opts.map(([v, t]) => `<option value="${esc(v)}"${v === cur ? " selected" : ""}>${esc(t)}</option>`).join("")}</select>`;

export function tlHtml(log, form = tlForm, xfer = tlXfer, edit = tlEdit) {
  const msg = tlMessage ? `<p role="status" class="${tlMessage.error ? "error" : "muted"}">${esc(tlMessage.text)}</p>` : "";
  if (!log) return `<h3>Transaction log</h3>${msg}<p class="muted">Loading…</p>`;
  if (!log.started) {
    return `<h3>Transaction log</h3>${msg}<p class="muted">The log is not started. Starting builds it from your broker imports and holdings; the holdings are not changed.</p>` +
      `<button type="button" onclick="tlStart()">Start the transaction log</button>`;
  }
  const drift = (log.drift || []).length ? `<div role="alert" class="error"><b>The log and the holdings differ:</b><ul>` +
    log.drift.map((d) => `<li>${esc(accountDisplayLabel(d.account))} ${esc(d.symbol)} ${esc(d.purchase_date)}: holdings ${tlNum(d.holdings_shares)}, log ${tlNum(d.log_shares)}. ${esc(d.reason)}</li>`).join("") + `</ul></div>` : `<p class="muted">The log agrees with the holdings.</p>`;
  const accts = tlAccounts(log);
  const acctOpts = [["", "Account"], ...accts.map((a) => [a, accountDisplayLabel(a)])];
  const rows = (log.rows || []).slice().reverse().map((r) => `<tr><td>${esc(r.txn_date)}</td><td>${esc(accountDisplayLabel(r.account))}</td><td>${esc(TL_LABEL[r.type] || r.type)}</td><td>${esc(r.symbol)}</td>` +
    `<td class="rc-num">${tlNum(r.shares)}</td><td class="rc-num">${r.price == null ? "" : tlNum(r.price)}</td><td>${esc(r.source)}</td><td>${esc(r.note || "")}</td>` +
    `<td><button type="button" onclick="tlEditRow(${Number(r.txn_id)})">Edit</button> <button type="button" onclick="tlVoid(${Number(r.txn_id)})">Void</button></td></tr>`).join("");
  const field = (k, ph, size) => `<input placeholder="${ph}" value="${esc(form[k])}" size="${size}" onchange="tlSetForm('${k}',this.value)">`;
  const addForm = `<h4>${edit ? "Revise transaction" : "Add transaction"}</h4><div class="sl-filters">` +
    `<input type="date" value="${esc(form.txn_date)}" onchange="tlSetForm('txn_date',this.value)">` + tlSelect("tlAcct", acctOpts, form.account, "tlSetFormAccount") +
    tlSelect("tlType", TL_TYPES, form.type, "tlSetFormType") + field("symbol", "Symbol", 7) + field("shares", "Shares", 8) + field("price", "Price", 8) +
    `<button type="button" onclick="tlSave()">${edit ? "Save revision" : "Add"}</button>${edit ? ` <button type="button" onclick="tlCancel()">Cancel</button>` : ""}</div>` +
    (form.type === "sell" ? `<p class="muted">A sale takes the oldest lots first.</p>` : "");
  const lotsForSymbol = (log.open || []).filter((l) => l.account === xfer.from_account && (!xfer.symbol || l.symbol.toUpperCase() === xfer.symbol.toUpperCase()));
  const xferForm = `<h4>Transfer between accounts</h4><div class="sl-filters">` + tlSelect("tlFrom", [["", "From"], ...accts.map((a) => [a, accountDisplayLabel(a)])], xfer.from_account, "tlSetXferFrom") +
    tlSelect("tlTo", [["", "To"], ...accts.map((a) => [a, accountDisplayLabel(a)])], xfer.to_account, "tlSetXferTo") +
    `<input placeholder="Symbol" value="${esc(xfer.symbol)}" size="7" onchange="tlSetXfer('symbol',this.value)">` +
    `<input type="date" value="${esc(xfer.txn_date)}" onchange="tlSetXfer('txn_date',this.value)"></div>` +
    (lotsForSymbol.length ? `<table class="rc-table"><thead><tr><th>Lot</th><th class="rc-num">Open</th><th class="rc-num">Move</th></tr></thead><tbody>` +
      lotsForSymbol.map((l) => `<tr><td>${esc(l.symbol)} ${esc(l.purchase_date)} @ ${tlNum(l.price)}</td><td class="rc-num">${tlNum(l.shares)}</td>` +
        `<td class="rc-num"><input size="7" value="${esc(xfer.picks[l.lot_txn_id] || "")}" onchange="tlPick(${Number(l.lot_txn_id)},this.value)"></td></tr>`).join("") + `</tbody></table>` : `<p class="muted">Choose the source account to list its open lots.</p>`) +
    `<button type="button" onclick="tlTransfer()">Transfer</button>`;
  const table = rows ? `<table class="rc-table"><thead><tr><th>Date</th><th>Account</th><th>Type</th><th>Symbol</th><th class="rc-num">Shares</th><th class="rc-num">Price</th><th>Source</th><th>Note</th><th></th></tr></thead><tbody>${rows}</tbody></table>` : `<p class="muted">The log is empty.</p>`;
  return `<h3>Transaction log</h3>${msg}${drift}${addForm}${xferForm}${table}`;
}

export function renderTransactionLog() {
  if (tlLog === null) setTimeout(tlLoad, 0);
  return `<div class="sl-import" id="tlRoot">${tlHtml(tlLog)}</div>`;
}

function tlPaint() { const root = document.getElementById("tlRoot"); if (root) root.innerHTML = tlHtml(tlLog); }

export async function tlLoad() {
  try { tlLog = await api("/api/transactions/log"); } catch (e) { tlLog = { started: false, rows: [], open: [], drift: [] }; tlMessage = { text: e.message, error: true }; }
  tlPaint();
}

async function tlPost(url, body, done) {
  try { await api(url, { method: "POST", body: JSON.stringify(body || {}) }); tlMessage = { text: done, error: false }; }
  catch (e) { tlMessage = { text: e.message, error: true }; return false; }
  await tlLoad();
  if (window.trLoad) window.trLoad();
  return true;
}

export const tlStart = () => tlPost("/api/transactions/backfill", {}, "The transaction log was started.");
export function tlSetForm(k, v) { tlForm = { ...tlForm, [k]: v }; }
export function tlSetFormAccount(v) { tlSetForm("account", v); }
export function tlSetFormType(v) { tlSetForm("type", v); tlPaint(); }
export async function tlSave() {
  const body = { ...tlForm };
  if (!body.txn_date || !body.account || !body.symbol || !body.shares) { tlMessage = { text: "Date, account, symbol and shares are required.", error: true }; tlPaint(); return; }
  const ok = await tlPost(tlEdit ? `/api/transactions/${Number(tlEdit)}/revise` : "/api/transactions", body, tlEdit ? "Transaction revised." : "Transaction added.");
  if (ok) { tlEdit = null; tlForm = { ...tlForm, symbol: "", shares: "", price: "" }; tlPaint(); }
}
export function tlEditRow(id) {
  const r = ((tlLog && tlLog.rows) || []).find((x) => x.txn_id === id);
  if (!r) return;
  tlEdit = id; tlForm = { txn_date: r.txn_date, account: r.account, type: r.type, symbol: r.symbol, shares: String(r.shares), price: r.price == null ? "" : String(r.price) };
  tlPaint();
}
export function tlCancel() { tlEdit = null; tlPaint(); }
export function tlVoid(id) {
  if (typeof confirm === "function" && !confirm("Void this transaction? It stays in the history as voided.")) return Promise.resolve(false);
  return tlPost(`/api/transactions/${Number(id)}/void`, {}, "Transaction voided.");
}
export function tlSetXfer(k, v) { tlXfer = { ...tlXfer, [k]: v }; }
export function tlSetXferFrom(v) { tlXfer = { ...tlXfer, from_account: v, picks: {} }; tlPaint(); }
export function tlSetXferTo(v) { tlSetXfer("to_account", v); }
export function tlPick(lot, v) { tlXfer = { ...tlXfer, picks: { ...tlXfer.picks, [lot]: v } }; }
export function tlTransfer() {
  const allocation = {};
  for (const [lot, v] of Object.entries(tlXfer.picks)) if (Number(v) > 0) allocation[lot] = Number(v);
  return tlPost("/api/transactions/transfer", { from_account: tlXfer.from_account, to_account: tlXfer.to_account, symbol: tlXfer.symbol, txn_date: tlXfer.txn_date, allocation }, "Shares transferred.");
}

Object.assign(window, { renderTransactionLog, tlHtml, tlLoad, tlStart, tlSetForm, tlSetFormAccount, tlSetFormType, tlSave, tlEditRow, tlCancel, tlVoid,
  tlSetXfer, tlSetXferFrom, tlSetXferTo, tlPick, tlTransfer });
