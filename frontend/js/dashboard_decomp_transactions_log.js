// Activity: the transaction log, mounted on Investment Holdings (dashboard_decomp_holdings_tabs.js). One view over one filter bar:
// start the log from existing imports and holdings, then add, revise, void and transfer. Changes save immediately and rewrite the
// holdings of the accounts the log manages. The drift list ("log health") is also mounted on the Sales Ledger's To fix tab.
// Logic lives on the server (src/transactions.py, /api/transactions/*). Helpers are bare globals.

const TL_TYPES = [["buy", "Buy"], ["reinvest", "Reinvest"], ["sell", "Sale / redemption"], ["opening", "Opening lot"]];
const TL_LABEL = { buy: "Buy", reinvest: "Reinvest", sell: "Sale / redemption", transfer_out: "Transfer out", transfer_in: "Transfer in", opening: "Opening lot" };
let tlLog = null;
let tlEdit = null; // txn_id being revised, or null when adding
let tlForm = { txn_date: "", account: "", type: "buy", symbol: "", shares: "", price: "" };
let tlXfer = { from_account: "", to_account: "", symbol: "", txn_date: "", picks: {} };
let tlMessage = null;
let tlHealthAll = false; // health list: false shows the first TL_HEALTH_MAX rows
const TL_PAGE = 25;
let tlFilter = { account: "", symbol: "", year: "", type: "", showCashOpening: false };
let tlShown = TL_PAGE; // entries rows currently shown; reset to one page whenever a filter changes
let tlDrawer = { add: false, xfer: false }; // drawers the user has open (kept across repaints)
let tlLoadFailed = false; // the last log load failed: the state is unknown, so no alert is published for it
let tlSlotStarted = null; // started state last painted into the health slot
let tlBank = []; // bank accounts that still have opening rows in the log (GET /api/transactions/bank-cleanup)
const TL_HEALTH_MAX = 5;

const tlNum = (v) => esc(String(Math.round(Number(v) * 1e6) / 1e6));
const tlAccounts = (log) => [...new Set([...(log.rows || []).map((r) => r.account), ...(log.open || []).map((l) => l.account)])].sort();
const tlSelect = (id, opts, cur, fn) => `<select id="${id}" onchange="${fn}(this.value)">${opts.map(([v, t]) => `<option value="${esc(v)}"${v === cur ? " selected" : ""}>${esc(t)}</option>`).join("")}</select>`;
const tlLink = (account, symbol) => (window.hsActivityLink ? window.hsActivityLink({ account, symbol, back: "sales" })
  : `#holdings/activity?account=${encodeURIComponent(account)}&symbol=${encodeURIComponent(symbol)}&back=sales`);
const tlMsgHtml = () => tlMessage ? `<p role="status" class="${tlMessage.error ? "error" : "muted"}">${esc(tlMessage.text)}</p>` : "";
const tlNotStartedHtml = (msg) => `<h3>Activity</h3>${msg}<p class="muted">The log is not started. Starting builds it from your broker imports and holdings; the holdings are not changed.</p>` +
  `<button type="button" class="btn" id="tlStartBtn" onclick="tlStart()">Start the transaction log</button>`;

export function tlHealthHtml(log) {
  const drift = (log && log.drift) || [];
  if (!drift.length) return `<p class="muted">The log agrees with the holdings.</p>`;
  const shown = tlHealthAll ? drift : drift.slice(0, TL_HEALTH_MAX);
  return `<div role="alert"><b>The log and the holdings differ:</b><ul>` + shown.map((d) =>
    `<li>${esc(accountDisplayLabel(d.account))} ${esc(d.symbol)} ${esc(d.purchase_date)}: holdings ${tlNum(d.holdings_shares)}, log ${tlNum(d.log_shares)}. ${esc(d.reason)} ` +
    `<a href="${esc(tlLink(d.account, d.symbol))}">Show in Activity</a></li>`).join("") + `</ul>` +
    (drift.length > TL_HEALTH_MAX ? `<button type="button" class="btn" id="tlHealthToggle" onclick="tlShowAllHealth(${!tlHealthAll})">${tlHealthAll ? "Show fewer" : `Show all ${drift.length}`}</button>` : "") + `</div>`;
}

// "Log agrees with holdings" for the Positions toolbar; loads the log when nothing has yet.
export function tlStatusHtml() {
  if (tlLog === null) setTimeout(tlLoad, 0);
  const n = tlLog && tlLog.started ? new Set((tlLog.drift || []).map((d) => d.account)).size : -1;
  return `<span id="tlStatusRoot" class="muted">${n < 0 ? "" : n ? `Log differs for ${n} account${n === 1 ? "" : "s"} → <a href="${esc(window.hsActivityLink ? window.hsActivityLink({}) : "#holdings/activity")}">Activity</a>` : "Log agrees with holdings"}</span>`;
}
const tlHealthInner = () => !tlLog ? `<p class="muted">Loading…</p>` : !tlLog.started ? tlNotStartedHtml(tlMsgHtml()) : tlHealthHtml(tlLog);
export function renderLogHealth() {
  if (tlLog === null) setTimeout(tlLoad, 0);
  return `<div id="tlHealthRoot">${tlHealthInner()}</div>`;
}
// The open lot a Positions row is, when it carries a wash-sale add-back (the holdings hold the adjusted cost and the tacked date).
export function tlWashFor(account, symbol, date, unitCost) {
  return ((tlLog && tlLog.open) || []).find((l) => l.account === account && String(l.symbol).toUpperCase() === String(symbol).toUpperCase() && l.wash_adjustment &&
    (l.tacked_date || l.purchase_date) === date && Math.abs(Number(l.adjusted_unit_cost) - Number(unitCost)) < 1e-6) || null;
}
export const tlStarted = () => !(tlLog && tlLog.started === false); // false only once the log is known to be not started

const tlIsCashOpening = (r) => r.type === "opening" && String(r.symbol).toUpperCase() === "CASH";
export function tlFilterRows(rows, f = {}) {
  const sym = String(f.symbol || "").trim().toUpperCase();
  return (rows || []).filter((r) => (!f.account || r.account === f.account) && (!sym || String(r.symbol).toUpperCase() === sym) &&
    (!f.year || String(r.txn_date).startsWith(String(f.year))) && (!f.type || r.type === f.type) && (f.showCashOpening || !tlIsCashOpening(r)));
}
export function tlPage(rows, shown) {
  const n = Math.max(0, Number(shown) || 0);
  return { rows: rows.slice(0, n), remaining: Math.max(0, rows.length - n) };
}
const tlRowId = (r) => `tlRow${Number(r.txn_id)}`;
const tlNewestFirst = (log) => tlFilterRows(((log && log.rows) || []).slice().reverse(), tlFilter);
function tlEntriesHtml(log) {
  if (!(log.rows || []).length) return `<p class="muted">The log is empty.</p>`;
  const f = tlNewestFirst(log), pg = tlPage(f, tlShown);
  if (!f.length) return `<p class="muted">No transactions match.</p>`;
  const rows = pg.rows.map((r) => `<tr id="${tlRowId(r)}" tabindex="-1"><td>${esc(r.txn_date)}</td><td>${esc(accountDisplayLabel(r.account))}</td><td>${esc(TL_LABEL[r.type] || r.type)}</td><td>${esc(r.symbol)}</td>` +
    `<td class="rc-num">${tlNum(r.shares)}</td><td class="rc-num">${r.price == null ? "" : tlNum(r.price)}</td><td>${esc(r.source)}</td><td>${esc(r.note || "")}${r.type === "sell" ? ` <a href="#sales_ledger?tab=ledger">Sale in Sales Ledger</a>` : ""}</td>` +
    `<td><button type="button" onclick="tlEditRow(${Number(r.txn_id)})">Edit</button></td></tr>`).join("");
  return `<p class="muted tl-count">Showing ${pg.rows.length} of ${f.length}</p><div class="tl-table-wrap"><table class="rc-table"><thead><tr><th>Date</th><th>Account</th><th>Type</th><th>Symbol</th><th class="rc-num">Shares</th><th class="rc-num">Price</th><th>Source</th><th>Note</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>` +
    (pg.remaining > 0 ? `<button type="button" class="btn" id="tlShowMore" onclick="tlShowMore()">Show ${TL_PAGE} more</button>` : "");
}
const tlFilterBarHtml = (log, accts) => {
  const years = [...new Set((log.rows || []).map((r) => String(r.txn_date || "").slice(0, 4)).filter(Boolean))].sort().reverse();
  const keep = (list, v) => (v && !list.includes(v) ? [...list, v] : list); // keep the active filter selectable
  const sel = (id, label, opts, key) => `<label for="${id}">${label} ` + tlSelect(id, opts, tlFilter[key], `tlSetFilter.bind(null,'${key}')`) + `</label>`;
  const cash = (log.rows || []).filter(tlIsCashOpening).length;
  return `<div class="sl-filters tl-filters">` + sel("tlFYear", "Year", [["", "All years"], ...keep(years, tlFilter.year).map((y) => [y, y])], "year") +
    sel("tlFAcct", "Account", [["", "All accounts"], ...keep(accts, tlFilter.account).map((a) => [a, accountDisplayLabel(a)])], "account") +
    `<label for="tlFSym">Symbol <input id="tlFSym" size="7" value="${esc(tlFilter.symbol)}" onchange="tlSetFilter('symbol',this.value)"></label>` +
    sel("tlFType", "Type", [["", "All types"], ...Object.entries(TL_LABEL), ...(tlFilter.type && !TL_LABEL[tlFilter.type] ? [[tlFilter.type, tlFilter.type]] : [])], "type") +
    `<label for="tlFCash"><input type="checkbox" id="tlFCash"${tlFilter.showCashOpening ? " checked" : ""} onchange="tlSetFilter('showCashOpening',this.checked)"> Show cash opening rows (${cash})</label></div>`;
};
function tlPaintEntries() {
  const el = tlLog && document.getElementById("tlEntries");
  if (el) el.innerHTML = tlEntriesHtml(tlLog);
}
export function tlSetFilter(key, value) {
  tlFilter = { ...tlFilter, [key]: key === "showCashOpening" ? !!value : String(value || "") }; tlShown = TL_PAGE;
  tlPaintEntries();
}
// A deep link from the ledger or Holdings sets the filters before the first paint.
export function tlApplyFilters(f = {}) {
  tlFilter = { account: f.account || "", symbol: f.symbol || "", year: f.year || "", type: f.type || "", showCashOpening: !!f.showCashOpening || f.source === "backfill" };
  tlShown = TL_PAGE; tlPaintRoot();
}
export function tlShowMore() {
  const first = tlNewestFirst(tlLog)[tlShown];
  tlShown += TL_PAGE; tlPaintEntries();
  const el = first && document.getElementById(tlRowId(first));
  if (el && el.focus) el.focus();
  if (window.slAnnounce) window.slAnnounce(`${TL_PAGE} more rows shown`);
}
export function tlShowAllHealth(on) {
  tlHealthAll = !!on;
  const root = document.getElementById("tlHealthRoot");
  if (root) { root.innerHTML = tlHealthInner(); const b = document.getElementById("tlHealthToggle"); if (b && b.focus) b.focus(); }
}
export function tlDrawerToggle(key, open) { tlDrawer = { ...tlDrawer, [key]: !!open }; }

const tlBankHtml = () => tlBank.length ? `<div role="alert" class="error tl-bank">${tlBank.length} bank account${tlBank.length === 1 ? " has" : "s have"} log rows that do not belong here: ${tlBank.map((a) => esc(accountDisplayLabel(a))).join(", ")}. ` +
  `<button type="button" class="btn" onclick="tlCleanBank()">Clean up</button></div>` : "";

export function tlHtml(log, form = tlForm, xfer = tlXfer, edit = tlEdit) {
  const msg = tlMsgHtml();
  if (!log) return `<h3>Activity</h3>${msg}<p class="muted">Loading…</p>`;
  if (!log.started) return tlNotStartedHtml(msg);
  const accts = tlAccounts(log);
  const acctOpts = [["", "Account"], ...accts.map((a) => [a, accountDisplayLabel(a)])];
  const field = (k, ph, size) => `<input aria-label="${ph}" placeholder="${ph}" value="${esc(form[k])}" size="${size}" onchange="tlSetForm('${k}',this.value)">`;
  const addForm = `<div class="sl-filters">` +
    `<input type="date" id="tlFDate" aria-label="Date" value="${esc(form.txn_date)}" onchange="tlSetForm('txn_date',this.value)">` + tlSelect("tlAcct", acctOpts, form.account, "tlSetFormAccount") +
    tlSelect("tlType", TL_TYPES, form.type, "tlSetFormType") + field("symbol", "Symbol", 7) + field("shares", "Shares", 8) + field("price", "Price", 8) +
    `<button type="button" onclick="tlSave()">${edit ? "Save revision" : "Add"}</button>${edit ? ` <button type="button" onclick="tlCancel()">Cancel</button> <button type="button" class="btn" onclick="tlVoid(${Number(edit)})">Void this transaction</button>` : ""}</div>` +
    (form.type === "sell" ? `<p class="muted">A sale takes the oldest lots first.</p>` : "");
  const lotsForSymbol = (log.open || []).filter((l) => l.account === xfer.from_account && (!xfer.symbol || l.symbol.toUpperCase() === xfer.symbol.toUpperCase()));
  const xferForm = `<div class="sl-filters">` + tlSelect("tlFrom", [["", "From"], ...accts.map((a) => [a, accountDisplayLabel(a)])], xfer.from_account, "tlSetXferFrom") +
    tlSelect("tlTo", [["", "To"], ...accts.map((a) => [a, accountDisplayLabel(a)])], xfer.to_account, "tlSetXferTo") +
    `<input placeholder="Symbol" value="${esc(xfer.symbol)}" size="7" onchange="tlSetXfer('symbol',this.value)">` +
    `<input type="date" value="${esc(xfer.txn_date)}" onchange="tlSetXfer('txn_date',this.value)"></div>` +
    (lotsForSymbol.length ? `<table class="rc-table"><thead><tr><th>Lot</th><th class="rc-num">Open</th><th class="rc-num">Move</th></tr></thead><tbody>` +
      lotsForSymbol.map((l) => `<tr><td>${esc(l.symbol)} ${esc(l.purchase_date)} @ ${tlNum(l.price)}</td><td class="rc-num">${tlNum(l.shares)}</td>` +
        `<td class="rc-num"><input size="7" value="${esc(xfer.picks[l.lot_txn_id] || "")}" onchange="tlPick(${Number(l.lot_txn_id)},this.value)"></td></tr>`).join("") + `</tbody></table>` : `<p class="muted">Choose the source account to list its open lots.</p>`) +
    `<button type="button" onclick="tlTransfer()">Transfer</button>`;
  const drawer = (key, id, title, body, open) => `<details class="drawer" id="${id}"${open ? " open" : ""} ontoggle="tlDrawerToggle('${key}',this.open)"><summary>${title}</summary>${body}</details>`;
  const drawers = `<div class="tl-drawers">` + drawer("add", "tlAddDrawer", edit ? "＋ Revise transaction" : "＋ Add transaction", addForm, edit || tlDrawer.add) +
    drawer("xfer", "tlXferDrawer", "⇄ Transfer", xferForm, tlDrawer.xfer) + `</div>`;
  return `<h3>Activity</h3>${msg}${tlBankHtml()}<p class="muted">Changes here save immediately.</p>${drawers}${tlFilterBarHtml(log, accts)}<div id="tlEntries">${tlEntriesHtml(log)}</div>`;
}

export function renderTransactionLog() {
  if (tlLog === null) setTimeout(tlLoad, 0);
  return `<div class="sl-import" id="tlRoot">${tlHtml(tlLog)}</div>`;
}

export function tlSummary() {
  if (tlLoadFailed) return { health: { count: 0, tone: "", text: "" } }; // a transient failure is not "log not started"
  if (tlLog && !tlLog.started) return { health: { count: 1, tone: "bad", text: "log not started" } };
  const n = new Set(((tlLog && tlLog.drift) || []).map((d) => d.account)).size;
  return { health: { count: n, tone: n > 0 ? "bad" : "", text: n > 0 ? `drift: ${n} accounts` : "" } };
}

function tlPaintRoot() {
  const root = document.getElementById("tlRoot");
  if (root) root.innerHTML = tlHtml(tlLog);
}
function tlPaint() {
  tlPaintRoot();
  const st = document.getElementById("tlStatusRoot");
  if (st) st.outerHTML = tlStatusHtml();
  const slot = document.getElementById("tlHealthSlot"), hroot = document.getElementById("tlHealthRoot");
  const started = tlStarted();
  if (slot && window.slHealthSlotHtml && started !== tlSlotStarted) slot.innerHTML = window.slHealthSlotInnerHtml ? window.slHealthSlotInnerHtml() : ""; // content only: the slot node stays, never a nested wrapper; shell <-> bare prompt only when the started state flips
  else if (hroot) hroot.innerHTML = tlHealthInner();
  tlSlotStarted = started;
  if (window.slPublish) window.slPublish("health", tlSummary().health);
}

export async function tlLoad() {
  const first = tlLog === null;
  tlLoadFailed = false;
  try { tlLog = await api("/api/transactions/log"); } catch (e) { tlLoadFailed = true; tlLog = { started: false, rows: [], open: [], drift: [] }; tlMessage = { text: e.message, error: true }; }
  try { tlBank = ((await api("/api/transactions/bank-cleanup")) || {}).accounts.map((a) => a.account); } catch (e) { tlBank = []; }
  tlPaint();
  if (first && window.activeStep === "holdings" && typeof renderMain === "function") renderMain(); // Positions markers need the log
}

async function tlPost(url, body, done) {
  try { await api(url, { method: "POST", body: JSON.stringify(body || {}) }); tlMessage = { text: done, error: false }; }
  catch (e) { tlMessage = { text: e.message, error: true }; tlPaint(); return false; }
  await tlLoad();
  return true;
}
export const tlReloadAll = () => tlLoad();

// Proceeds when no dialog is available, by design (tests, embedded views).
const tlConfirmed = (msg) => !(typeof window !== "undefined" && typeof window.confirm === "function") || window.confirm(msg);
export const tlStart = () => !tlConfirmed("Starting the log means holdings will now be written by the log.") ? Promise.resolve(false) : tlPost("/api/transactions/backfill", {}, "The transaction log was started.");
export const tlCleanBank = () => (!tlBank.length || !tlConfirmed(`Void the opening rows of ${tlBank.length} bank account(s)? They are cash accounts, not investments; their cash balances stay as they are.`)) ? Promise.resolve(false) :
  tlPost("/api/transactions/bank-cleanup", { accounts: tlBank }, "Bank-account rows were voided.");
export function tlSetForm(k, v) { tlForm = { ...tlForm, [k]: v }; }
export function tlSetFormAccount(v) { tlSetForm("account", v); }
export function tlSetFormType(v) { tlSetForm("type", v); tlPaint(); }
export async function tlSave() {
  const body = { ...tlForm };
  if (!body.txn_date || !body.account || !body.symbol || !body.shares) { tlMessage = { text: "Date, account, symbol and shares are required.", error: true }; tlPaint(); return; }
  const ok = await tlPost(tlEdit ? `/api/transactions/${Number(tlEdit)}/revise` : "/api/transactions", body, tlEdit ? "Transaction revised." : "Transaction added.");
  if (ok) { if (tlEdit) tlDrawer = { ...tlDrawer, add: false }; tlEdit = null; tlForm = { ...tlForm, symbol: "", shares: "", price: "" }; tlPaint(); }
}
export function tlEditRow(id) {
  const r = ((tlLog && tlLog.rows) || []).find((x) => x.txn_id === id);
  if (!r) return;
  tlEdit = id; tlDrawer = { ...tlDrawer, add: true }; tlForm = { txn_date: r.txn_date, account: r.account, type: r.type, symbol: r.symbol, shares: String(r.shares), price: r.price == null ? "" : String(r.price) };
  tlPaint();
  const dr = document.getElementById("tlAddDrawer"), el = document.getElementById("tlFDate");
  if (dr && dr.scrollIntoView) dr.scrollIntoView({ block: "start" });
  if (el && el.focus) el.focus();
}
export function tlOnKeydown(e) {
  const r = document.getElementById("tlRoot"); // Esc elsewhere (another drawer, tab or page) must not drop a revision in progress
  if (!r || typeof r.contains !== "function" || !r.contains(e.target)) return;
  if (e.key === "Escape" && !e.defaultPrevented && (tlEdit || tlDrawer.add)) tlCancel();
}
export function tlCancel() { tlEdit = null; tlDrawer = { ...tlDrawer, add: false }; tlPaint(); }
if (typeof document !== "undefined" && document.addEventListener) {
  document.addEventListener("keydown", tlOnKeydown);
}
export async function tlVoid(id) {
  if (!tlConfirmed("Void this transaction? It stays in the history as voided.")) return false;
  const ok = await tlPost(`/api/transactions/${Number(id)}/void`, {}, "Transaction voided.");
  if (ok && tlEdit === Number(id)) tlCancel();
  return ok;
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

Object.assign(window, { tlWashFor, tlStatusHtml, tlHealthHtml, renderLogHealth, tlStarted, tlShowAllHealth, tlSummary, renderTransactionLog, tlHtml, tlFilterRows, tlPage, tlSetFilter, tlApplyFilters, tlReloadAll, tlShowMore, tlDrawerToggle, tlLoad, tlStart, tlCleanBank, tlSetForm, tlSetFormAccount, tlSetFormType, tlSave, tlEditRow, tlCancel, tlOnKeydown, tlVoid,
  tlSetXfer, tlSetXferFrom, tlSetXferTo, tlPick, tlTransfer });
