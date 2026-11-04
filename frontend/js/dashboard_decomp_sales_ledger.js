// Sales Ledger page (Reports & Review): record a realized sale by hand or from a CSV and list the ledger.
// Logic lives on the server (src/sales_service.py, /api/sales*): the page collects a row, posts it, and
// lists the result. One row is one lot (or part of a lot) sold, with that lot's basis and purchase date.
// The tax-year panel (dashboard_decomp_sales_tax.js) and the brokerage import (dashboard_decomp_broker_import.js) are
// mounted here. A manual sale is edited in the form (the old row is voided); a sale confirmed from the queue goes Back
// to queue to pick its lots again. Helpers are bare globals; renderMain() calls renderSalesLedger().

const SL_CLASSES = [["taxable", "Taxable"], ["pre_tax", "Pre-tax (IRA/401k)"], ["roth", "Roth"], ["hsa", "HSA"]];
const SL_TERM = { short: "Short", long: "Long", unknown: "Unknown" };

let slData = null;
let slYear = String(new Date().getFullYear());
let slShowVoided = false;
let slPreview = null;
let slMessage = null; // { text, error }
let slLoading = false;
let slError = "";
let slEditId = null;
let slAccounts = [];
let slDraft = {}; // form field id -> text, kept on input so a repaint or reload never loses a half-filled sale
let slCsvText = ""; // pasted CSV text, kept on input for the same reason
let slCsvMessage = null; // { text, error }: feedback for the CSV box itself (the Ledger-tab message line is hidden on the Import tab)
let slCsvDone = null; // set after a successful CSV import: drives the next-step links
let slHiddenVoids = 0; // voided rows the current selection hides (one extra fetch when Show voided is off)

export function slMoney(v) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "—";
  const n = Number(v);
  return (n < 0 ? "-$" : "$") + Math.abs(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function slGainHtml(v) {
  if (v === null || v === undefined) return "—";
  const cls = Math.abs(v) < 0.005 ? "" : v > 0 ? " sl-up" : " sl-down";
  return `<span class="rc-num${cls}">${esc((v > 0 ? "+" : "") + slMoney(v))}</span>`;
}

export function slRowHtml(s) {
  const voided = s.status === "voided";
  const id = Number(s.sale_id);
  const btn = (fn, label) => `<button class="btn" type="button" onclick="${fn}(${id})">${label}</button>`;
  const action = voided ? btn("slUnvoid", "Restore")
    : s.source === "manual" ? btn("slEdit", "Edit") + " " + btn("slVoid", "Void")
    : s.source === "broker" || s.source === "monarch" ? btn("slRequeue", "Back to queue")
    : btn("slVoid", "Void");
  return `<tr class="${voided ? "sl-voided" : ""}"><td>${esc(s.sale_date)}</td><td>${esc(accountDisplayLabel(s.account))}</td><td>${esc(s.symbol)}</td>` +
    `<td class="rc-num">${esc(String(s.shares))}</td><td class="rc-num">${slMoney(s.proceeds)}</td><td class="rc-num">${slMoney(s.fees)}</td>` +
    `<td class="rc-num">${slMoney(s.basis)}</td><td>${s.gain === null || s.gain === undefined ? `<span class="sl-chip">tax-deferred — no gain reported</span>` : slGainHtml(s.gain)}</td><td>${esc(SL_TERM[s.holding_period] || "")}</td><td>${action}</td></tr>`;
}

export function slTableHtml(sales) {
  if (!sales || !sales.length) return `<p class="muted">No sales recorded for this selection.</p>`;
  return `<div class="rc-scroll sl-scroll" role="region" aria-label="Sales" tabindex="0"><table class="rc-table"><thead><tr><th>Sale date</th><th>Account</th><th>Symbol</th><th class="rc-num">Shares</th>` +
    `<th class="rc-num">Proceeds</th><th class="rc-num">Fees</th><th class="rc-num">Basis</th><th class="rc-num">Gain</th><th>Term</th><th></th></tr></thead>` +
    `<tbody>${sales.map(slRowHtml).join("")}</tbody></table></div>`;
}

export function slTotalsHtml(t) {
  return `<p><strong>${Number(t.count)}</strong> sale${t.count === 1 ? "" : "s"} · short-term net ${slGainHtml(t.short_gain)} · long-term net ${slGainHtml(t.long_gain)}</p>`;
}

export function slPreviewHtml(p) {
  const errs = (p.errors || []).map((e) => `<li>Line ${Number(e.line)}: ${esc(e.error)}</li>`).join("");
  const ok = !(p.errors || []).length;
  const add = p.will_write.length;
  return `<div class="sl-preview"><p>${Number(p.received)} rows read: ${add} to add, ${p.duplicates.length} already in the ledger` +
    `${ok ? "" : `, ${p.errors.length} with problems`}.</p>` +
    `${errs ? `<ul class="field-error">${errs}</ul><p>Fix these lines and preview again; nothing is saved until the file is clean.</p>` : ""}` +
    `${ok && add ? `<button class="btn primary" type="button" onclick="slImportCommit()">Add ${add} sale${add === 1 ? "" : "s"}</button>` : ""}</div>`;
}

export function slDraftSet(id, v) { if (id === "slCsv") slCsvText = String(v ?? ""); else slDraft[id] = String(v ?? ""); }
const slSel = (id, v) => (slDraft[id] === v ? " selected" : "");
const slAccountSelect = () => `<label>Account<select id="slAccount" oninput="slDraftSet('slAccount',this.value)"><option value=""></option>` +
  slAccounts.map((a) => `<option value="${esc(a)}"${slSel("slAccount", a)}>${esc(accountDisplayLabel(a))}</option>`).join("") + `</select></label>`;

function slFormHtml() {
  const input = (id, label, type = "text", extra = "") => `<label>${label}<input id="${id}" type="${type}" value="${esc(slDraft[id] || "")}" oninput="slDraftSet('${id}',this.value)" ${extra}></label>`;
  return `<div class="sl-form"><h3>${slEditId ? "Edit sale" : "Record a sale"}</h3><div class="field-grid">` +
    input("slDate", "Sale date", "date") + slAccountSelect() +
    `<label>Account type<select id="slClass" oninput="slDraftSet('slClass',this.value)">${SL_CLASSES.map(([v, l]) => `<option value="${v}"${slSel("slClass", v)}>${l}</option>`).join("")}</select></label>` +
    input("slSymbol", "Symbol") + input("slShares", "Shares sold", "number", 'step="any" min="0"') +
    input("slProceeds", "Proceeds ($)", "number", 'step="any"') + input("slFees", "Fees ($)", "number", 'step="any" min="0"') +
    input("slBasis", "Cost basis of these shares ($)", "number", 'step="any"') + input("slPurchase", "Lot purchase date", "date") +
    `</div><p class="muted">One row per lot sold. Gain is proceeds − fees − basis; it is left blank for pre-tax, Roth and HSA accounts.</p>` +
    `<button class="btn primary" type="button" onclick="slSubmit()">${slEditId ? "Save changes" : "Add sale"}</button>` +
    `${slEditId ? ` <button class="btn" type="button" onclick="slCancelEdit()">Cancel</button>` : ""}</div>`;
}

const slSteps = (n) => (window.slStepsHtml ? window.slStepsHtml(n) : "");
export const slCsvStateText = () => (slPreview ? `Preview ready · ${slPreview.will_write.length} rows` : slCsvMessage && !slCsvMessage.error ? slCsvMessage.text : "Paste or choose a CSV");
function slImportHtml() {
  const msg = slCsvMessage ? `<p class="${slCsvMessage.error ? "field-error" : "muted"}" role="status">${esc(slCsvMessage.text)}</p>` : "";
  return `<div class="sl-import">${slSteps(slPreview ? 2 : 1)}<h3>Import from CSV</h3><p class="muted">Columns: sale_date, account, tax_class, symbol, shares, proceeds, basis (required); fees, purchase_date.</p>` +
    `<textarea id="slCsv" rows="5" aria-label="Sales CSV" placeholder="Paste CSV text here" oninput="slDraftSet('slCsv',this.value)">${esc(slCsvText)}</textarea>` +
    `<input type="file" accept=".csv,text/csv" aria-label="Choose a CSV file" onchange="slCsvFile(this)">` +
    `<button class="btn" type="button" onclick="slImportPreview()">Preview</button>${msg}${slPreview ? slPreviewHtml(slPreview) : ""}${slCsvDone && window.slNextStepHtml ? window.slNextStepHtml(slCsvDone) : ""}</div>`;
}

function slYearOptions() {
  const now = new Date().getFullYear();
  const years = new Set(Array.from({ length: 12 }, (_, i) => String(now + 1 - i)));
  if (slYear) years.add(slYear);
  return `<option value=""${slYear ? "" : " selected"}>All years</option>` +
    [...years].sort().reverse().map((y) => `<option value="${y}"${y === slYear ? " selected" : ""}>${y}</option>`).join("");
}

export const slHiddenVoidCount = () => slHiddenVoids;
const slHiddenText = () => (slHiddenVoids > 0 ? ` (${slHiddenVoids} hidden)` : "");
function slHeadHtml() {
  return `<h2>Sales Ledger</h2><label>Sale year <select id="slYear" onchange="slSetYear(this.value)">${slYearOptions()}</select></label> ` +
    `<label><input type="checkbox" ${slShowVoided ? "checked" : ""} onchange="slSetShowVoided(this.checked)"> Show voided<span id="slVoidedCount">${slHiddenText()}</span></label>`;
}

function slListHtml() {
  const msg = slMessage ? `<p class="${slMessage.error ? "field-error" : "muted"}" role="status">${esc(slMessage.text)}</p>` : "";
  const bar = `<div class="sl-toolbar">${slData ? slTotalsHtml({ ...slData.totals, count: slData.sales.length }) : ""}<button class="btn" type="button" onclick="slOpenForm()">＋ Record a sale</button></div>`;
  return msg + bar + (slError ? `<p class="field-error">${esc(slError)}</p>` : slData ? slTableHtml(slData.sales) : `<p class="muted">Loading…</p>`);
}

let slHashApplied = null;
const SL_SECS = ["queue", "health", "log", "wash", "cf", "b1099", "cash", "imports", "csv"];
const slPanels = (names) => names.map((n) => (window[n] ? window[n]() : "")).join("");

// Deep link: #sales_ledger?tab=import&sec=b1099. Only read when the hash is ours; location may not exist (node tests).
export function slHashTarget() {
  let hash = "";
  try { hash = (typeof location !== "undefined" && location && location.hash) || ""; } catch (e) { hash = ""; }
  if (!hash.startsWith("#sales_ledger") || !window.slParseHash) return { tab: null, sec: null };
  const p = window.slParseHash(hash);
  return { tab: p.tab, sec: SL_SECS.includes(p.sec) ? p.sec : null };
}

const slTabsHtml = (active) => window.slTabBarHtml(active, window.slMarkers(window.slSummaries())) +
  `<div class="sl-secctl"><button type="button" class="btn" id="slExpandAll" onclick="slSecAll(window.slUiLoad().tab,true)">Expand all</button> ` +
  `<button type="button" class="btn" id="slCollapseAll" onclick="slSecAll(window.slUiLoad().tab,false)">Collapse all</button></div>`;
// Wrap a panel in the collapsible section shell; the panel's own markup is passed through untouched.
function slSection(key, title, fn, stateFn) {
  if (!window[fn]) return "";
  const sum = window.slSummaries()[key] || {};
  const badges = sum.text ? [{ text: sum.text, tone: sum.tone || "none" }] : [];
  const open = window.slSecWantOpen(window.slUiLoad(), key, window.slAlertCountOf(sum));
  return window.slSecHtml({ key, title, badges, state: stateFn && window[stateFn] ? window[stateFn]() : "", alertCount: window.slAlertCountOf(sum), open, body: window[fn]() });
}
// Log health: a collapsible section once the log is started; the bare Start prompt (never inside a collapsible) before that.
export function slHealthSlotHtml() {
  const bare = window.tlStarted && window.tlStarted() === false && window.renderLogHealth;
  return `<div id="tlHealthSlot">${bare ? window.renderLogHealth() : slSection("health", "Log health", "renderLogHealth")}</div>`;
}
export const slLedgerBodyHtml = () => `<details class="drawer" id="slFormDrawer"><summary>Record a sale</summary><div id="slFormRoot">${slFormHtml()}</div></details>` +
  `<div id="slListRoot">${slListHtml()}</div>`;
export const slCsvBodyHtml = () => `<div id="slCsvRoot">${slImportHtml()}</div>`;
const slDrawer = (open) => { const d = typeof document !== "undefined" && document.getElementById("slFormDrawer"); if (d) d.open = open; };
export function slOpenForm() { slDrawer(true); const f = typeof document !== "undefined" && document.getElementById("slDate"); if (f && f.focus) f.focus(); }
function slPaintTabs() { // repaint the strip and tab bar without losing keyboard focus inside the tab bar
  const act = typeof document !== "undefined" && document.activeElement;
  const id = act && act.id;
  slPaintInto("slStripRoot", () => window.slStripHtml(window.slSummaries()));
  slPaintInto("slTabsRoot", () => slTabsHtml(window.slUiLoad().tab));
  const el = id && document.getElementById(id);
  if (el && el !== document.activeElement && el.focus) el.focus();
}
let slSumSub = false;
function slSubscribeSummaries() { // repaint only the strip and tab bar; panels keep their state
  if (slSumSub || !window.slOnSummary) return;
  slSumSub = true;
  window.slOnSummary(slPaintTabs);
}

function slBodyHtml() {
  const hashTab = slHashTarget().tab;
  if (hashTab && hashTab !== slHashApplied) { // a deep link applies once; after that storage (slSetTab) decides
    slHashApplied = hashTab;
    window.slUiSave(window.slUiSetTab(window.slUiLoad(), hashTab));
  }
  const active = window.slUiLoad().tab;
  const panel = (id, body) => window.slTabPanelHtml(id, body, active);
  const fix = slSection("queue", "Sales waiting for lots", "renderSalesQueue") + slHealthSlotHtml() + slSection("log", "Transaction log", "renderTransactionLog") +
    `<div class="divider sl-divider">More views</div>` + slPanels(["renderCashInvestment"]);
  const ledger = slSection("ledger", "Sales", "slLedgerBodyHtml");
  return `<div id="slHeadRoot">${slHeadHtml()}</div>${window.slLiveHtml()}<div id="slStripRoot">${window.slStripHtml(window.slSummaries())}</div>` +
    `<div id="slTabsRoot">${slTabsHtml(active)}</div>` +
    panel("fix", fix) + panel("ledger", ledger) + panel("tax", slSection("wash", "Realized gains & wash sales", "renderSalesTaxYear")) +
    panel("import", slSection("imports", "Broker imports", "renderBrokerImport", "biStateText") + slSection("b1099", "Broker 1099-B", "renderSalesBroker1099b", "bbStateText") +
      slSection("csv", "Sales CSV import", "slCsvBodyHtml", "slCsvStateText"));
}

export function renderSalesLedger() {
  slSubscribeSummaries();
  if (slData === null && !slLoading && !slError) setTimeout(loadSalesLedger, 0);
  return `<div class="field-list sl-page" id="slRoot">${slBodyHtml()}</div>`;
}

function slPaintInto(id, html) { const el = document.getElementById(id); if (el) el.innerHTML = html(); }
function slPaint() { slPaintInto("slListRoot", slListHtml); }
const slPaintForm = () => slPaintInto("slFormRoot", slFormHtml);
const slPaintCsv = () => { slPaintInto("slCsvRoot", slImportHtml); if (window.slSecSetState) window.slSecSetState("csv", slCsvStateText()); };

export async function loadSalesLedger() {
  const year = slYear; // a year/Show-voided change mid-load must not pair the count with another selection
  const showVoided = slShowVoided;
  slLoading = true;
  slError = "";
  try {
    const q = new URLSearchParams();
    if (year) q.set("year", year);
    if (showVoided) q.set("include_voided", "1");
    const out = await api("/api/sales?" + q);
    try { slAccounts = (await api("/api/sales/broker/imports")).accounts || []; } catch (e) { slAccounts = []; }
    // Checking & Savings accounts have their own page; keep them out of the ledger's rows and account picker.
    let cash = new Set();
    try { cash = cashOnlyAccounts(ensureHoldingRows().data); } catch (e) { /* holdings not loaded: nothing to hide */ }
    const isCash = (a) => cash.has(String(a || "").trim().toLowerCase());
    if (out && out.sales) out.sales = out.sales.filter((x) => !isCash(x.account));
    slAccounts = slAccounts.filter((a) => !isCash(a));
    if (out && out.sales) slAccounts = [...new Set([...slAccounts, ...out.sales.map((x) => x.account)])].sort();
    slData = out && out.success ? out : null;
    if (!slData) slError = "The ledger could not be loaded.";
    await slLoadHiddenVoids(year, showVoided);
    if (window.slPublish && slData) window.slPublish("ledger", { count: slData.sales.length, tone: "", text: `${slData.sales.length} sale${slData.sales.length === 1 ? "" : "s"}` });
    if (window.loadSalesTaxYear && slYear) window.loadSalesTaxYear(slYear);
  } catch (e) {
    slData = null;
    slError = "The ledger could not be loaded: " + e.message;
  }
  slLoading = false;
  slPaint();
}

async function slLoadHiddenVoids(year, showVoided) { // one extra read, only when voided rows are hidden; a failure just shows nothing
  slHiddenVoids = 0;
  if (!showVoided) {
    try {
      const q = new URLSearchParams({ include_voided: "1" });
      if (year) q.set("year", year);
      const all = await api("/api/sales?" + q);
      slHiddenVoids = ((all && all.sales) || []).filter((x) => x.status === "voided").length;
    } catch (e) { slHiddenVoids = 0; }
  }
  const el = typeof document !== "undefined" && document.getElementById("slVoidedCount");
  if (el) el.textContent = slHiddenText();
}

const val = (id) => { const el = document.getElementById(id); return el ? el.value : (slDraft[id] ?? ""); };
const csvVal = () => { const el = document.getElementById("slCsv"); if (el) slCsvText = el.value; return slCsvText; };

async function slPost(url, body, okText) {
  let out;
  try {
    out = await api(url, { method: "POST", body: JSON.stringify(body || {}) });
    slMessage = { text: okText, error: false };
    if (slPreview) { slPreview = null; slPaintCsv(); }
  } catch (e) {
    slMessage = { text: e.message, error: true };
  }
  await loadSalesLedger();
  return out;
}

const SL_FORM = { slDate: "sale_date", slAccount: "account", slClass: "tax_class", slSymbol: "symbol", slShares: "shares",
  slProceeds: "proceeds", slFees: "fees", slBasis: "basis", slPurchase: "purchase_date" };

export async function slSubmit() {
  const body = Object.fromEntries(Object.entries(SL_FORM).map(([id, k]) => [k, val(id)]));
  const editing = slEditId;
  const sent = slDraft;
  slDraft = {}; // typing while the save is in flight lands in the fresh draft
  const out = await slPost(editing ? `/api/sales/${Number(editing)}/replace` : "/api/sales", body,
    editing ? "Sale updated; the old row is kept as voided." : "Sale recorded.");
  if (out) { slEditId = null; slPaintForm(); slDrawer(false); } else slDraft = { ...sent, ...slDraft };
}

export function slEdit(id) {
  const s = slData && slData.sales.find((x) => Number(x.sale_id) === Number(id));
  if (!s) return;
  slEditId = Number(id);
  slDrawer(true); // open first, then set the values
  slDraft = Object.fromEntries(Object.entries(SL_FORM).map(([elId, k]) => [elId, s[k] === null || s[k] === undefined ? "" : String(s[k])]));
  slPaintForm();
}

export function slCancelEdit() { slEditId = null; slDraft = {}; slDrawer(false); slPaintForm(); }
export async function slRequeue(id) {
  const out = await slPost(`/api/sales/${Number(id)}/requeue`, null, "Sale sent back to the queue; its shares are back in their lots. It is waiting on the Fix tab.");
  if (out && window.sqReload) window.sqReload();
  if (out && window.slGo) window.slGo("fix", "queue");
}

export async function slVoid(id) {
  const s = slData && slData.sales.find((x) => Number(x.sale_id) === Number(id));
  const gain = s && s.gain !== null && s.gain !== undefined ? (s.gain > 0 ? "+" : "") + slMoney(s.gain) : "this sale";
  const year = s && s.sale_date ? String(s.sale_date).slice(0, 4) : slYear || "all-years";
  if (typeof window !== "undefined" && window.confirm && !window.confirm(`Remove ${gain} from ${year} totals?`)) return undefined;
  return slPost(`/api/sales/${Number(id)}/void`, null, "Sale voided. Use Restore to bring it back.");
}
export const slUnvoid = (id) => slPost(`/api/sales/${Number(id)}/unvoid`, null, "Sale restored.");
export function slSetYear(v) { slYear = String(v || "").trim(); return loadSalesLedger(); }
export function slSetShowVoided(on) { slShowVoided = !!on; return loadSalesLedger(); }

export function slCsvFile(input) {
  const file = input.files && input.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => { slCsvText = String(reader.result || ""); slPaintCsv(); };
  reader.readAsText(file);
}

export async function slImportPreview() {
  slCsvDone = null;
  try {
    slPreview = await api("/api/sales/import/preview", { method: "POST", body: JSON.stringify({ content: csvVal() }) });
    slMessage = null; slCsvMessage = null;
  } catch (e) {
    slPreview = null;
    slMessage = { text: e.message, error: true }; slCsvMessage = slMessage;
  }
  slPaint();
  slPaintCsv();
}

export async function slImportCommit() {
  const out = await slPost("/api/sales/import/commit", { content: csvVal() }, "Import complete.");
  if (out) { slCsvText = ""; slCsvDone = {}; }
  if (out && out.written !== undefined) {
    slMessage = { text: `Added ${out.written} sale${out.written === 1 ? "" : "s"}.`, error: false };
    slPaint();
  }
  slCsvMessage = slMessage; // success text or the failure the post caught; both belong in the CSV box too
  slPaintCsv();
}

Object.assign(window, {
  slMoney, slGainHtml, slRowHtml, slTableHtml, slTotalsHtml, slPreviewHtml, renderSalesLedger, slHashTarget, loadSalesLedger, slSubmit, slVoid, slUnvoid,
  slSetYear, slSetShowVoided, slCsvFile, slImportPreview, slImportCommit, slEdit, slCancelEdit, slRequeue, slDraftSet, slHealthSlotHtml, slLedgerBodyHtml, slOpenForm, slHiddenVoidCount, slCsvBodyHtml, slCsvStateText,
});
