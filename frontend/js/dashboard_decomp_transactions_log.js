// Transaction log panel (phase 2 of the transaction log plan): one section with two modes over one filter bar. "Edit log"
// starts the log from existing imports and holdings, then adds, revises, voids and transfers; "History & held lots" is the
// read-only list of dashboard_decomp_transactions.js (trLoad/trHtml), fetched with the same filters.
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
let tlFilter = { account: "", symbol: "", year: "", type: "", held: false }; // shared: client-side in edit mode, server-side in history
let tlMode = "edit"; // "edit" | "history"
let tlHistKey = null; // filters of the last history load (JSON), or null before the first one
let tlHistView = null; // the history view loaded for tlHistKey
let tlHistSeq = 0; // number of the latest history request
let tlShown = TL_PAGE; // entries rows currently shown; reset to one page whenever a filter changes
let tlDrawer = { add: false, xfer: false }; // drawers the user has open (kept across repaints)
let tlSlotStarted = null; // started state last painted into the health slot
const TL_HEALTH_MAX = 5;

const tlNum = (v) => esc(String(Math.round(Number(v) * 1e6) / 1e6));
const tlAccounts = (log) => [...new Set([...(log.rows || []).map((r) => r.account), ...(log.open || []).map((l) => l.account)])].sort();
const tlSelect = (id, opts, cur, fn) => `<select id="${id}" onchange="${fn}(this.value)">${opts.map(([v, t]) => `<option value="${esc(v)}"${v === cur ? " selected" : ""}>${esc(t)}</option>`).join("")}</select>`;

const tlJs = (v) => esc(String(v).replace(/[\\']/g, "\\$&"));
const tlMsgHtml = () => tlMessage ? `<p role="status" class="${tlMessage.error ? "error" : "muted"}">${esc(tlMessage.text)}</p>` : "";
const tlNotStartedHtml = (msg) => `<h3>Transaction log</h3>${msg}<p class="muted">The log is not started. Starting builds it from your broker imports and holdings; the holdings are not changed.</p>` +
  `<button type="button" class="btn" onclick="tlStart()">Start the transaction log</button>`;
const tlManagedListHtml = (log, accts) => {
  const managed = new Set((log.managed || []).map((a) => a.toLowerCase()));
  return `<p class="muted">A managed account's holdings are written by this log; edit it here, not in Holdings. Turning it off leaves the last holdings as they are.</p><ul class="tl-managed">` +
    accts.map((a) => `<li><label><input type="checkbox" data-managed="${esc(a)}"${managed.has(a.toLowerCase()) ? " checked" : ""} onchange="tlSetManaged('${esc(a)}',this.checked)"> ${esc(accountDisplayLabel(a))}</label></li>`).join("") + `</ul>`;
};

export function tlHealthHtml(log) {
  const drift = (log && log.drift) || [];
  if (!drift.length) return `<p class="muted">The log agrees with the holdings.</p>`;
  const shown = tlHealthAll ? drift : drift.slice(0, TL_HEALTH_MAX);
  return `<div role="alert"><b>The log and the holdings differ:</b><ul>` + shown.map((d) =>
    `<li>${esc(accountDisplayLabel(d.account))} ${esc(d.symbol)} ${esc(d.purchase_date)}: holdings ${tlNum(d.holdings_shares)}, log ${tlNum(d.log_shares)}. ${esc(d.reason)} ` +
    `<button type="button" class="btn" onclick="tlFocusRow('${tlJs(d.account)}','${tlJs(d.symbol)}','${tlJs(d.purchase_date)}')">Show in log</button></li>`).join("") + `</ul>` +
    (drift.length > TL_HEALTH_MAX ? `<button type="button" class="btn" id="tlHealthToggle" onclick="tlShowAllHealth(${!tlHealthAll})">${tlHealthAll ? "Show fewer" : `Show all ${drift.length}`}</button>` : "") + `</div>`;
}

export function tlManagedChipsHtml(log) {
  const managed = (log && log.managed) || [];
  return `<div class="tl-managed-chips"><b>Managed accounts (${managed.length}):</b> ` +
    (managed.length ? managed.map((a) => `<span class="sl-sec-badge sl-tone-none">${esc(accountDisplayLabel(a))} · managed</span>`).join(" ") : "none") +
    ` <details class="tl-managed-edit"><summary>Edit…</summary>${tlManagedListHtml(log, tlAccounts(log))}</details></div>`;
}

const tlHealthInner = () => !tlLog ? `<p class="muted">Loading…</p>` : !tlLog.started ? tlNotStartedHtml(tlMsgHtml()) : tlHealthHtml(tlLog);
export function renderLogHealth() {
  if (tlLog === null) setTimeout(tlLoad, 0);
  return `<div id="tlHealthRoot">${tlHealthInner()}</div>`;
}
export const tlStarted = () => !(tlLog && tlLog.started === false); // false only once the log is known to be not started

export function tlFilterRows(rows, f = {}) {
  const sym = String(f.symbol || "").trim().toUpperCase();
  return (rows || []).filter((r) => (!f.account || r.account === f.account) && (!sym || String(r.symbol).toUpperCase() === sym) &&
    (!f.year || String(r.txn_date).startsWith(String(f.year))) && (!f.type || r.type === f.type));
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
    `<td class="rc-num">${tlNum(r.shares)}</td><td class="rc-num">${r.price == null ? "" : tlNum(r.price)}</td><td>${esc(r.source)}</td><td>${esc(r.note || "")}</td>` +
    `<td><button type="button" onclick="tlEditRow(${Number(r.txn_id)})">Edit</button> <button type="button" onclick="tlVoid(${Number(r.txn_id)})">Void</button></td></tr>`).join("");
  return `<p class="muted tl-count">Showing ${pg.rows.length} of ${f.length}</p><div class="tl-table-wrap"><table class="rc-table"><thead><tr><th>Date</th><th>Account</th><th>Type</th><th>Symbol</th><th class="rc-num">Shares</th><th class="rc-num">Price</th><th>Source</th><th>Note</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>` +
    (pg.remaining > 0 ? `<button type="button" class="btn" id="tlShowMore" onclick="tlShowMore()">Show ${TL_PAGE} more</button>` : "");
}
const TL_HIST_TYPES = [["buy", "Buy"], ["reinvest", "Reinvest"], ["sell", "Sale / redemption"]]; // the types the history view knows
// The mode shown: history whenever the log is not started (history comes from imports, sales and holdings, not the log).
const tlModeOf = (log) => (log && log.started === false ? "history" : tlMode);
const tlFilterBarHtml = (log, accts) => {
  const hist = tlModeOf(log) === "history", hv = (hist && tlHistView) || {}, hRows = hv.rows || [];
  const years = [...new Set([...(log.rows || []).map((r) => r.txn_date), ...hRows.map((r) => r.date)].map((d) => String(d || "").slice(0, 4)).filter(Boolean))].sort().reverse();
  const all = [...new Set([...accts, ...hRows.map((r) => r.account), ...(hv.held || []).map((h) => h.account)])].sort();
  const keep = (list, v) => (v && !list.includes(v) ? [...list, v] : list); // keep the active filter selectable
  const types = hist ? TL_HIST_TYPES : Object.entries(TL_LABEL);
  const sel = (id, label, opts, key) => `<label for="${id}">${label} ` + tlSelect(id, opts, tlFilter[key], `tlSetFilter.bind(null,'${key}')`) + `</label>`;
  return `<div class="sl-filters tl-filters">` + sel("tlFAcct", "Account", [["", "All accounts"], ...keep(all, tlFilter.account).map((a) => [a, accountDisplayLabel(a)])], "account") +
    `<label for="tlFSym">Symbol <input id="tlFSym" size="7" value="${esc(tlFilter.symbol)}" onchange="tlSetFilter('symbol',this.value)"></label>` +
    sel("tlFYear", "Filter year", [["", "All years"], ...keep(years, tlFilter.year).map((y) => [y, y])], "year") +
    sel("tlFType", "Type", [["", "All types"], ...types, ...(tlFilter.type && !types.some(([v]) => v === tlFilter.type) ? [[tlFilter.type, TL_LABEL[tlFilter.type] || tlFilter.type]] : [])], "type") +
    (hist ? `<label for="tlFHeld"><input type="checkbox" id="tlFHeld"${tlFilter.held ? " checked" : ""} onchange="tlSetFilter('held',this.checked)"> Held only</label>` : "") + `</div>`;
};
const tlModeHtml = (log) => `<div class="tl-mode" role="group" aria-label="Log view">` + [["edit", "tlModeEdit", "Edit log"], ["history", "tlModeHistory", "History &amp; held lots"]].map(([k, id, t]) =>
  `<button type="button" class="btn" id="${id}" aria-pressed="${tlModeOf(log) === k}"${k === "edit" && log.started === false ? " disabled" : ""} onclick="tlSetMode('${k}')">${t}</button>`).join(" ") + `</div>`;
const tlFilterKey = () => JSON.stringify(tlFilter);
const tlHistoryHtml = () => { // history for the current filters, once loaded
  const v = tlHistKey === tlFilterKey() && tlHistView;
  if (!v || !window.trHtml) return `<p class="muted">Loading…</p>`;
  const n = (v.rows || []).length;
  return `<p class="muted tl-count">${n} transaction${n === 1 ? "" : "s"}</p>` + window.trHtml(v, tlFilter);
};
const tlBodyHtml = (log) => (tlModeOf(log) === "history" ? tlHistoryHtml() : tlEntriesHtml(log));
function tlPaintEntries() {
  const el = tlLog && document.getElementById("tlEntries");
  if (el) el.innerHTML = tlBodyHtml(tlLog);
}
async function tlLoadHistory() { // latest request wins: an older response never replaces a newer one
  if (!window.trLoad) return;
  const f = { ...tlFilter }, seq = ++tlHistSeq;
  const view = await window.trLoad(f);
  if (seq !== tlHistSeq) return;
  tlHistView = view; tlHistKey = JSON.stringify(f);
  if (tlModeOf(tlLog) === "history") tlPaintEntries();
}
// Edit mode filters the loaded rows; history mode asks the server with the same filters.
export function tlSetFilter(key, value) {
  tlFilter = { ...tlFilter, [key]: key === "held" ? !!value : String(value || "") }; tlShown = TL_PAGE;
  if (tlModeOf(tlLog) === "history") return tlLoadHistory();
  tlPaintEntries();
}
// Switching keeps the filters and the edit-mode paging; history is fetched only when not loaded for these filters.
export function tlSetMode(mode) {
  tlMode = mode === "history" ? "history" : "edit";
  tlPaintRoot();
  const hist = tlModeOf(tlLog) === "history", b = document.getElementById(hist ? "tlModeHistory" : "tlModeEdit");
  if (b && b.focus) b.focus(); // the pressed button was repainted
  return hist && tlHistKey !== tlFilterKey() ? tlLoadHistory() : Promise.resolve();
}
export function tlShowMore() {
  const first = tlNewestFirst(tlLog)[tlShown];
  tlShown += TL_PAGE; tlPaintEntries();
  const el = first && document.getElementById(tlRowId(first));
  if (el && el.focus) el.focus();
  if (window.slAnnounce) window.slAnnounce(`${TL_PAGE} more rows shown`);
}
export function tlFocusRow(account, symbol, purchase_date) { // purchase_date identifies the health row; the log filters by account and symbol
  tlFilter = { account, symbol, year: "", type: "", held: false }; tlShown = TL_PAGE; tlMode = "edit";
  tlPaint(); // full log repaint so the filter controls show the new values
  if (typeof window.slGo === "function") window.slGo("fix", "log");
}
export function tlShowAllHealth(on) {
  tlHealthAll = !!on;
  const root = document.getElementById("tlHealthRoot");
  if (root) { root.innerHTML = tlHealthInner(); const b = document.getElementById("tlHealthToggle"); if (b && b.focus) b.focus(); }
}
export function tlDrawerToggle(key, open) { tlDrawer = { ...tlDrawer, [key]: !!open }; }

export function tlHtml(log, form = tlForm, xfer = tlXfer, edit = tlEdit, opts = { health: true }) {
  const msg = tlMsgHtml();
  if (!log) return `<h3>Transaction log</h3>${msg}<p class="muted">Loading…</p>`;
  if (!log.started) return opts.health ? tlNotStartedHtml(msg) : `<h3>Transaction log</h3>${msg}<p class="muted">The log is not started. Start it in the log health section.</p>` +
    `${tlModeHtml(log)}${tlFilterBarHtml(log, tlAccounts(log))}<div id="tlEntries">${tlHistoryHtml()}</div>`; // history works without the log
  const drift = opts.health ? (log.drift || []).length ? `<div role="alert" class="error"><b>The log and the holdings differ:</b><ul>` +
    log.drift.map((d) => `<li>${esc(accountDisplayLabel(d.account))} ${esc(d.symbol)} ${esc(d.purchase_date)}: holdings ${tlNum(d.holdings_shares)}, log ${tlNum(d.log_shares)}. ${esc(d.reason)}</li>`).join("") + `</ul></div>` : `<p class="muted">The log agrees with the holdings.</p>` : "";
  const accts = tlAccounts(log);
  const acctOpts = [["", "Account"], ...accts.map((a) => [a, accountDisplayLabel(a)])];
  const managedBox = opts.health ? `<h4>Managed accounts</h4>${tlManagedListHtml(log, accts)}` : tlManagedChipsHtml(log);
  const field = (k, ph, size) => `<input aria-label="${ph}" placeholder="${ph}" value="${esc(form[k])}" size="${size}" onchange="tlSetForm('${k}',this.value)">`;
  const addForm = `<div class="sl-filters">` +
    `<input type="date" id="tlFDate" aria-label="Date" value="${esc(form.txn_date)}" onchange="tlSetForm('txn_date',this.value)">` + tlSelect("tlAcct", acctOpts, form.account, "tlSetFormAccount") +
    tlSelect("tlType", TL_TYPES, form.type, "tlSetFormType") + field("symbol", "Symbol", 7) + field("shares", "Shares", 8) + field("price", "Price", 8) +
    `<button type="button" onclick="tlSave()">${edit ? "Save revision" : "Add"}</button>${edit ? ` <button type="button" onclick="tlCancel()">Cancel</button>` : ""}</div>` +
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
    drawer("xfer", "tlXferDrawer", "＋ Transfer between accounts", xferForm, tlDrawer.xfer) + `</div>`;
  const editOnly = tlMode === "edit" ? `${managedBox}${drawers}` : "";
  return `<h3>Transaction log</h3>${msg}${drift}${tlModeHtml(log)}${editOnly}${tlFilterBarHtml(log, accts)}<div id="tlEntries">${tlBodyHtml(log)}</div>`;
}

export function renderTransactionLog() {
  if (tlLog === null) setTimeout(tlReloadAll, 0); // a not-started log shows history, so it loads too
  return `<div class="sl-import" id="tlRoot">${tlHtml(tlLog, undefined, undefined, undefined, { health: false })}</div>`;
}

export function tlSummary() {
  if (tlLog && !tlLog.started) return { health: { count: 1, tone: "bad", text: "log not started" }, log: { count: 0, tone: "", text: "" } };
  const n = new Set(((tlLog && tlLog.drift) || []).map((d) => d.account)).size;
  return { health: { count: n, tone: n > 0 ? "bad" : "", text: n > 0 ? `drift: ${n} accounts` : "" }, log: { count: tlLog ? (tlLog.rows || []).length : 0, tone: "", text: "" } };
}

function tlPaintRoot() {
  const root = document.getElementById("tlRoot");
  if (root) root.innerHTML = tlHtml(tlLog, undefined, undefined, undefined, { health: false });
}
function tlPaint() {
  tlPaintRoot();
  const slot = document.getElementById("tlHealthSlot"), hroot = document.getElementById("tlHealthRoot");
  const started = tlStarted();
  if (slot && window.slHealthSlotHtml && started !== tlSlotStarted) slot.innerHTML = window.slHealthSlotHtml(); // shell <-> bare prompt only when the started state flips
  else if (hroot) hroot.innerHTML = tlHealthInner();
  tlSlotStarted = started;
  if (window.slPublish) { const s = tlSummary(); window.slPublish("health", s.health); window.slPublish("log", s.log); }
}

export async function tlLoad() {
  try { tlLog = await api("/api/transactions/log"); } catch (e) { tlLog = { started: false, rows: [], open: [], drift: [] }; tlMessage = { text: e.message, error: true }; }
  tlPaint();
}

async function tlPost(url, body, done) {
  try { await api(url, { method: "POST", body: JSON.stringify(body || {}) }); tlMessage = { text: done, error: false }; }
  catch (e) { tlMessage = { text: e.message, error: true }; tlPaint(); return false; }
  await tlReloadAll();
  return true;
}
// Refresh the log and, when history is shown or was loaded, the history once (with the current filters).
export async function tlReloadAll() {
  await tlLoad();
  if (tlModeOf(tlLog) === "history" || tlHistKey !== null) await tlLoadHistory();
}

// Proceeds when no dialog is available, by design (tests, embedded views).
const tlConfirmed = (msg) => !(typeof window !== "undefined" && typeof window.confirm === "function") || window.confirm(msg);
export const tlStart = () => !tlConfirmed("Starting the log means holdings will now be written by the log.") ? Promise.resolve(false) : tlPost("/api/transactions/backfill", {}, "The transaction log was started.");
function tlRevertManaged(account) { // re-check only this checkbox; no repaint, so an open "Edit…" details stays open
  const boxes = typeof document !== "undefined" && document.querySelectorAll ? document.querySelectorAll("input[data-managed]") : [];
  for (const b of boxes) if (b.getAttribute("data-managed") === account) b.checked = true;
}
export function tlSetManaged(account, on) {
  if (!on && !tlConfirmed("Holdings freeze at their last state and the log stops updating them.")) { tlRevertManaged(account); return Promise.resolve(false); }
  return tlPost(`/api/transactions/accounts/${encodeURIComponent(account)}/managed`, { managed: !!on },
    on ? "The account is now managed by the log." : "The account is no longer managed; its holdings stay as they are.").then((ok) => {
    if (ok && window.loadManagedHoldingAccounts) window.loadManagedHoldingAccounts();
    if (!ok) tlLoad();
    return ok;
  });
}
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
export function tlOnKeydown(e) { if (e.key === "Escape" && !e.defaultPrevented && (tlEdit || tlDrawer.add)) tlCancel(); }
export function tlCancel() { tlEdit = null; tlDrawer = { ...tlDrawer, add: false }; tlPaint(); }
if (typeof document !== "undefined" && document.addEventListener) {
  document.addEventListener("keydown", tlOnKeydown);
}
export function tlVoid(id) {
  if (!tlConfirmed("Void this transaction? It stays in the history as voided.")) return Promise.resolve(false);
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

Object.assign(window, { tlHealthHtml, tlManagedChipsHtml, renderLogHealth, tlStarted, tlFocusRow, tlShowAllHealth, tlSummary, renderTransactionLog, tlHtml, tlFilterRows, tlPage, tlSetFilter, tlSetMode, tlReloadAll, tlShowMore, tlDrawerToggle, tlLoad, tlStart, tlSetManaged, tlSetForm, tlSetFormAccount, tlSetFormType, tlSave, tlEditRow, tlCancel, tlOnKeydown, tlVoid,
  tlSetXfer, tlSetXferFrom, tlSetXferTo, tlPick, tlTransfer });
