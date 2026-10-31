// Brokerage activity import and income check, mounted on the Sales Ledger page (Reports & Review).
// Logic lives on the server (src/broker_import.py, src/broker_income.py, /api/sales/broker/*): the panel reads a
// broker's transaction-history CSV, shows the preview (new lots, sale orders, income, position check), and commits
// it, optionally confirming the fully covered sales with the chosen lot method. Helpers are bare globals.

const BI_METHODS = [["fifo", "FIFO (oldest lots first)"], ["hifo", "HIFO (highest cost first)"], ["lowest_gain", "Losses first"]];
const BI_STATUS = { ready: "Ready", short: "Not enough lots", no_lots: "No lots" };
const BI_BROKERS = [["", "Detect from the file"], ["fidelity", "Fidelity"], ["etrade", "E*Trade"], ["vanguard", "Vanguard"]];
const BI_KIND = { buy: "Buy", reinvest: "Reinvest", dividend: "Dividend", interest: "Interest", cap_gain_short: "ST cap gain",
  cap_gain_long: "LT cap gain", foreign_tax: "Foreign tax", return_of_capital: "Return of capital" };

let biText = "";
let biFile = "";
let biAccount = "";
let biBroker = ""; // "" = recognize the broker from the file's header
const BI_IN_FILE = "__in_file__"; // plan-account choice: take the account from each record of the file
let biAccounts = {}; // account hint -> plan account, for files that hold several accounts
let biMethod = "fifo";
let biConfirm = false;
let biHistory = false;
let biPreview = null;
let biImports = null;
let biIncome = null;
let biMessage = null; // { text, error }

const biMoney = (v) => (window.slMoney ? window.slMoney(v) : String(v));
const biNum = (v) => esc(String(Math.round(Number(v) * 1e6) / 1e6));

const biAcct = (rows, on) => (on ? `<td>${esc(accountDisplayLabel(rows.account || ""))}</td>` : "");

export function biLotsHtml(lots, multi) {
  if (!lots.length) return `<p class="muted">No new buys or reinvestments.</p>`;
  return `<table class="rc-table"><thead><tr>${multi ? "<th>Account</th>" : ""}<th>Date</th><th>Type</th><th>Symbol</th><th class="rc-num">Shares</th><th class="rc-num">Price</th><th>Result</th></tr></thead><tbody>` +
    lots.map((l) => `<tr>${biAcct(l, multi)}<td>${esc(l.run_date)}</td><td>${esc(BI_KIND[l.kind] || l.kind)}</td><td>${esc(l.symbol)}</td><td class="rc-num">${biNum(l.shares)}</td>` +
      `<td class="rc-num">${biMoney(l.price)}</td><td>${l.action === "add" ? "New lot" :
        `Already in holdings (${esc(l.lot_date)}${l.price_diff ? `, price differs by ${biMoney(l.price_diff)}` : ""})`}</td></tr>`).join("") + `</tbody></table>`;
}

export function biOrdersHtml(orders, multi) {
  if (!orders.length) return `<p class="muted">No new sales.</p>`;
  const lots = (o) => (o.lots || []).map((l) => `${biNum(l.shares)} from ${esc(l.purchase_date || "undated")}${l.origin === "import" ? " (new)" : ""}`).join("; ");
  return `<table class="rc-table"><thead><tr>${multi ? "<th>Account</th>" : ""}<th>Trade date</th><th>Symbol</th><th class="rc-num">Shares</th><th class="rc-num">Proceeds</th><th>Lots</th><th>Status</th></tr></thead><tbody>` +
    orders.map((o) => `<tr>${biAcct(o, multi)}<td>${esc(o.trade_date)}</td><td>${esc(o.symbol)}</td><td class="rc-num">${biNum(o.shares)}</td><td class="rc-num">${biMoney(o.proceeds)}</td>` +
      `<td>${lots(o) || "—"}</td><td>${esc(BI_STATUS[o.status] || o.status)}${o.status === "short" ? ` (${biNum(o.lots_short)} short)` : ""}</td></tr>`).join("") + `</tbody></table>`;
}

const biBrokerName = (id) => esc((BI_BROKERS.find(([v]) => v === id) || [id, id])[1]);

// One plan-account picker per account hint of a multi-account file (a Vanguard download holds every account).
export function biHintPickersHtml(hints, accounts, chosen) {
  if (!hints || hints.length < 2) return "";
  return `<div class="field-grid">` + hints.map((h) => `<label>Plan account for ${esc(h.hint)} (${Number(h.rows)} rows)` +
    `<select aria-label="Plan account for ${esc(h.hint)}" onchange="biSetHintAccount('${esc(h.hint)}', this.value)"><option value="">Choose…</option>` +
    accounts.map((a) => `<option value="${esc(a)}" ${a === (chosen[h.hint] || h.account) ? "selected" : ""}>${esc(accountDisplayLabel(a))}</option>`).join("") +
    `</select></label>`).join("") + `</div>`;
}

export function biPreviewHtml(p) {
  if (p.needs_account) {
    return `<p class="field-error">${(p.hints || []).length > 1 ? "Choose a plan account for each account in this file" : "Choose the plan account this file belongs to"}, then preview again.</p>`;
  }
  const multi = (p.hints || []).length > 1;
  const errs = (p.errors || []).map((e) => `<li>Line ${Number(e.line)}: ${esc(e.error)}</li>`).join("");
  const warns = (p.warnings || []).map((w) => `<li>${esc(w)}</li>`).join("");
  const inc = Object.entries(p.income_totals || {}).map(([k, v]) => `${esc(BI_KIND[k] || k)} ${biMoney(v)}`).join(" · ") || "none";
  const c = p.counts;
  const n = p.will_write.length;
  return `<div class="sl-preview"><p>${Number(p.received)} rows (${esc(p.date_from || "")} to ${esc(p.date_to || "")}): ${n} new, ` +
    `${Number(p.already_imported)} already imported. ${biBrokerName(p.broker)}, ${multi ? "accounts" : "account"} ${esc(String(p.account || "").split(", ").map(accountDisplayLabel).join(", "))}${p.tax_class ? ` (${esc(p.tax_class)})` : ""}.</p>` +
    (errs ? `<ul class="field-error">${errs}</ul><p>Nothing can be imported until these rows read cleanly.</p>` : "") +
    (warns ? `<ul class="field-warning">${warns}</ul>` : "") +
    `<h4>Lots (${c.lots_add} new, ${c.lots_present} already present)</h4>${biLotsHtml(p.lots, multi)}` +
    `<h4>Sales (${c.orders}, ${c.orders_ready} ready)</h4>${biOrdersHtml(p.orders, multi)}` +
    `<h4>Income</h4><p>${inc}</p>` +
    ((p.monarch_covered || []).length ? `<p class="muted">${p.monarch_covered.length} imported sale(s) in the queue are covered by this file and will be marked superseded.</p>` : "") +
    (!errs && n ? `<label><input type="checkbox" ${biHistory ? "checked" : ""} onchange="biSetHistory(this.checked)"> Record only: my holdings already include this history (income and trades are stored; no lots change, no sales are queued)</label> ` +
      (biHistory ? "" : `<label><input type="checkbox" ${biConfirm ? "checked" : ""} onchange="biSetConfirm(this.checked)"> Confirm the ${c.orders_ready} ready sale(s) with the lots shown</label> `) +
      `<button class="btn primary" type="button" onclick="biCommit()">Import ${n} row${n === 1 ? "" : "s"}</button>` : "") + `</div>`;
}

export function biImportsHtml(list) {
  if (!list || !list.length) return `<p class="muted">No imports yet.</p>`;
  return `<table class="rc-table"><thead><tr><th>#</th><th>Account</th><th>Range</th><th class="rc-num">New rows</th><th>Status</th><th></th></tr></thead><tbody>` +
    list.map((i) => `<tr><td>${Number(i.import_id)}</td><td>${esc(accountDisplayLabel(i.account))}</td><td>${esc(i.date_from || "")} to ${esc(i.date_to || "")}</td>` +
      `<td class="rc-num">${Number(i.rows_new)}</td><td>${esc(i.status)}</td><td>${i.status === "applied" ?
        `<button class="btn" type="button" onclick="biRevert(${Number(i.import_id)})">Revert</button>` : ""}</td></tr>`).join("") + `</tbody></table>`;
}

export function biIncomeHtml(r) {
  const t = r.totals;
  const rows = (r.months || []).map((m) => `<tr><td>${esc(m.month)}</td><td class="rc-num">${biMoney(m.broker)}</td><td class="rc-num">${biMoney(m.monarch)}</td>` +
    `<td class="rc-num${Math.abs(m.difference) >= 0.005 ? " sl-down" : ""}">${biMoney(m.difference)}</td></tr>`).join("");
  const only = (label, items, date, amt) => items.length ? `<p><strong>${label}:</strong> ${items.map((x) => `${esc(x[date])} ${esc(x.symbol || x.merchant || "")} ${biMoney(x[amt])}`).join("; ")}</p>` : "";
  return `<p>${Number(t.matched)} matched · broker ${biMoney(t.broker)} · account import ${biMoney(t.monarch)} · difference ${biMoney(t.difference)}` +
    `${r.monarch_accounts.length ? "" : " · no imported account is mapped to this plan account"}</p>` +
    `<table class="rc-table"><thead><tr><th>Month</th><th class="rc-num">Broker</th><th class="rc-num">Account import</th><th class="rc-num">Difference</th></tr></thead><tbody>${rows}</tbody></table>` +
    only("Only in the broker file", r.broker_only, "run_date", "amount") + only("Only in the account import", r.monarch_only, "date", "amount");
}

function biBodyHtml() {
  const accounts = (biImports && biImports.accounts) || [];
  const multiHints = !!(biPreview && (biPreview.hints || []).length > 1);
  const msg = biMessage ? `<p class="${biMessage.error ? "field-error" : "muted"}" role="status">${esc(biMessage.text)}</p>` : "";
  return `<h3>Import brokerage activity</h3>${msg}<p class="muted">Fidelity “History for Account”, E*Trade “Transaction History” or Vanguard “OfxDownload” CSV. Re-importing an overlapping file adds only new rows.</p>` +
    `<div class="field-grid"><label>Broker<select aria-label="Broker" onchange="biSetBroker(this.value)">${BI_BROKERS.map(([v, l]) => `<option value="${v}" ${v === biBroker ? "selected" : ""}>${l}</option>`).join("")}</select></label>` +
    `<label>File<input type="file" accept=".csv,text/csv" aria-label="Brokerage history file" onchange="biFileChosen(this)"></label>` +
    `<label>${multiHints ? "Income check account" : "Plan account"}<select id="biAccount" onchange="biSetAccount(this.value)"><option value="">${biPreview && biPreview.account ? "" : "Choose…"}</option><option value="${BI_IN_FILE}" ${biAccount === BI_IN_FILE ? "selected" : ""}>Account in file (one per record)</option>` +
    accounts.map((a) => `<option value="${esc(a)}" ${a === (biAccount || (biPreview && biPreview.account)) ? "selected" : ""}>${esc(accountDisplayLabel(a))}</option>`).join("") + `</select></label>` +
    `<label>Lot method<select onchange="biSetMethod(this.value)">${BI_METHODS.map(([v, l]) => `<option value="${v}" ${v === biMethod ? "selected" : ""}>${l}</option>`).join("")}</select></label></div>` +
    `${multiHints ? biHintPickersHtml(biPreview.hints, accounts, biAccounts) : ""}` +
    `<button class="btn" type="button" onclick="biPreviewFile()" ${biText ? "" : "disabled"}>Preview</button>${biPreview ? biPreviewHtml(biPreview) : ""}` +
    `<h4>Imports</h4>${biImportsHtml(biImports && biImports.imports)}` +
    `<h4>Income check (broker vs account import)</h4><button class="btn" type="button" onclick="biLoadIncome()">Check ${esc(biPlanAccount() ? accountDisplayLabel(biPlanAccount()) : "account")} for ${esc(String(new Date().getFullYear()))}</button>` +
    (biIncome ? biIncomeHtml(biIncome) : "");
}

export function renderBrokerImport() {
  if (biImports === null) setTimeout(biLoadImports, 0);
  return `<div class="sl-import" id="biRoot">${biBodyHtml()}</div>`;
}

function biPaint() {
  const root = document.getElementById("biRoot");
  const old = root && root.querySelector('input[type="file"]'); // repainting must not reset the chosen file
  if (root) root.innerHTML = biBodyHtml();
  const fresh = old && old.files.length && root.querySelector('input[type="file"]');
  if (fresh) fresh.replaceWith(old);
}

export async function biLoadImports() {
  try { biImports = await api("/api/sales/broker/imports"); } catch (e) { biImports = { imports: [], accounts: [] }; biMessage = { text: e.message, error: true }; }
  biPaint();
}

export function biFileChosen(input) {
  const file = input.files && input.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => { biText = String(reader.result || ""); biFile = file.name; biPreview = null; biAccounts = {}; biPaint(); };
  reader.readAsText(file);
}

export function biSetAccount(v) { biAccount = v; biIncome = null; }
const biPlanAccount = () => (biAccount === BI_IN_FILE ? "" : biAccount);
export function biSetBroker(v) { biBroker = v; biPreview = null; biAccounts = {}; biPaint(); }
export function biSetHintAccount(hint, v) { biAccounts = { ...biAccounts, [hint]: v }; }
export function biSetMethod(v) { biMethod = v; }
export function biSetConfirm(on) { biConfirm = !!on; }
export function biSetHistory(on) { biHistory = !!on; return biPreviewFile(); }

const biBody = () => {
  const single = !biPreview || (biPreview.hints || []).length < 2;
  return { broker: biBroker, content: biText, file_name: biFile, account: single ? (biAccount === BI_IN_FILE ? "" : biAccount || (biPreview && biPreview.account) || "") : "",
    accounts: biAccounts,
    history_only: biHistory ? (single ? [biPlanAccount() || (biPreview && biPreview.account) || ""] : Object.values(biAccounts)) : [] };
};

export async function biPreviewFile() {
  try {
    biPreview = await api("/api/sales/broker/preview", { method: "POST", body: JSON.stringify({ ...biBody(), method: biMethod }) });
    for (const h of biPreview.hints || []) if (h.account && !biAccounts[h.hint]) biAccounts = { ...biAccounts, [h.hint]: h.account };
    if (biPreview.account && (biPreview.hints || []).length < 2 && biAccount !== BI_IN_FILE) biAccount = biPreview.account;
    biMessage = null;
  } catch (e) { biPreview = null; biMessage = { text: e.message, error: true }; }
  biPaint();
}

export async function biCommit() {
  try {
    const out = await api("/api/sales/broker/commit", { method: "POST", body: JSON.stringify({ ...biBody(), confirm_method: biConfirm && !biHistory ? biMethod : "" }) });
    biMessage = { text: `Imported ${out.rows_new} rows: ${out.lots_added} new lots, ${out.confirmed.length} sales confirmed, ${out.queued.length} left in the queue.`, error: false };
    biPreview = null;
  } catch (e) { biMessage = { text: e.message, error: true }; }
  await biLoadImports();
  if (window.loadSalesLedger) window.loadSalesLedger();
  if (window.sqReload) window.sqReload();
}

export async function biRevert(id) {
  try {
    await api(`/api/sales/broker/imports/${Number(id)}/revert`, { method: "POST", body: "{}" });
    biMessage = { text: `Import ${Number(id)} reverted.`, error: false };
  } catch (e) { biMessage = { text: e.message, error: true }; }
  await biLoadImports();
  if (window.sqReload) window.sqReload();
}

export async function biLoadIncome() {
  if (!biPlanAccount()) { biMessage = { text: "Choose a plan account first.", error: true }; biPaint(); return; }
  try {
    biIncome = await api(`/api/sales/broker/income?account=${encodeURIComponent(biPlanAccount())}&year=${new Date().getFullYear()}`);
    biMessage = null;
  } catch (e) { biIncome = null; biMessage = { text: e.message, error: true }; }
  biPaint();
}

Object.assign(window, {
  biLotsHtml, biOrdersHtml, biPreviewHtml, biImportsHtml, biIncomeHtml, renderBrokerImport, biLoadImports, biFileChosen,
  biSetAccount, biSetBroker, biSetHintAccount, biHintPickersHtml, biSetMethod, biSetConfirm, biSetHistory, biPreviewFile, biCommit, biRevert, biLoadIncome,
});
