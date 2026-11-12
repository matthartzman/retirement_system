// Sales Ledger page (Reports & Review): record a realized sale by hand or from a CSV and list the ledger.
// Logic lives on the server (src/sales_service.py, /api/sales*): the page collects a row, posts it, and
// lists the result. One row is one lot (or part of a lot) sold, with that lot's basis and purchase date.
// The tax-year panel (dashboard_decomp_sales_tax.js) and the brokerage import (dashboard_decomp_broker_import.js) are
// mounted here. A manual sale is edited in the form (the old row is voided); a sale confirmed from the queue goes Back
// to queue to pick its lots again. Helpers are bare globals; renderMain() calls renderSalesLedger().
const SL_TERM = { short: "Short", long: "Long", unknown: "Unknown" };
let slData = null;
let slYear = String(new Date().getFullYear());
let slYears = []; // years that have ledger or log rows (GET /api/sales/years); the Year list offers only these
let slTaxAccts = []; // investment accounts that are taxable (named next to the Taxable-only switch)
let slYearChosen = false; // until the user picks one, the first load settles on the current year, else the latest with data
let slShowVoided = false;
let slMessage = null; // { text, error }
let slLoading = false;
let slError = "";
let slAccounts = [];
let slHp = null; // GET /api/sales/holding-period-check for the Year
let slSum = null; // GET /api/sales/summary for the current Year and switch
let slHiddenVoids = 0; // voided rows the current selection hides (one extra fetch when Voided rows is off)
export const slCurrentYear = () => slYear;
export const slTaxableOnly = () => (window.slUiLoad ? window.slUiLoad().taxableOnly !== false : true);
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
const slTermText = (t) => SL_TERM[t] || t || "";
const slGainCell = (v) => (v === null || v === undefined ? `<span title="not taxable">—</span>` : slGainHtml(v));
// A ⋯ menu: each item is [label, onclick, reason]; an item that does not apply is disabled and says why.
const slMenu = (items) => `<details class="sl-menu"><summary aria-label="Actions">⋯</summary><div class="sl-menu-items">${items.map(([label, fn, why]) =>
  `<button class="btn" type="button"${why ? ` disabled title="${esc(why)}"` : ` onclick="${fn}"`}>${label}${why ? ` <span class="muted">(${esc(why)})</span>` : ""}</button>`).join("")}</div></details>`;
export function slLotRowHtml(s) {
  const voided = s.status === "voided", id = Number(s.sale_id);
  const why = s.source !== "manual" ? "came from the queue: send the sale back to the queue to change it" : (s.lot_key || "").includes("log_sell") ? "linked to the transaction log: void it and record the sale again" : "";
  const items = voided ? [["Restore", `slUnvoid(${id})`, (s.lot_key || "").includes("log_sell") ? "its log sale was removed with the void: record the sale again" : ""]] : [["Edit", `slEdit(${id})`, why], ["Void", `slVoid(${id})`, ""]];
  return `<tr class="sl-lot${voided ? " sl-voided" : ""}"><td></td><td>lot bought ${esc(s.purchase_date || "(date unknown)")}</td><td></td><td></td><td class="rc-num">${esc(String(s.shares))}</td><td class="rc-num">${slMoney(s.proceeds)}</td>` +
    `<td class="rc-num">${slMoney(s.basis)}</td><td>${slGainCell(s.gain)}</td><td>${esc(slTermText(s.holding_period))}</td><td>${slMenu(items)}</td></tr>`;
}
let slGroupsNow = [];
const slOpenSales = new Set(); // sale keys whose lots are showing
export function slSaleRowHtml(g, i) {
  const open = slOpenSales.has(g.key), voided = g.lots.every((l) => l.status === "voided");
  const why = g.lots.every((l) => l.source === "manual") ? "a hand-recorded sale has no queue entry" : "";
  return `<tr class="sl-sale${voided ? " sl-voided" : ""}"><td><button class="btn" type="button" aria-expanded="${open}" aria-label="Lots of this sale" onclick="slToggleSale(${i})">${open ? "▾" : "▸"}</button></td><td>${esc(g.sale_date)}</td>` +
    `<td>${esc(accountDisplayLabel(g.account))}</td><td>${esc(g.symbol)}${g.wash ? ` <span class="sl-chip">wash?</span>` : ""}</td><td class="rc-num">${esc(String(+g.shares.toFixed(6)))}</td>` +
    `<td class="rc-num">${slMoney(g.proceeds)}</td><td class="rc-num">${slMoney(g.basis)}</td><td>${slGainCell(g.gain)}</td><td>${esc(slTermText(g.term))}</td>` +
    `<td>${voided ? "" : slMenu([["Send back to queue", `slRequeue(${Number(g.lots[0].sale_id)})`, why]])}</td></tr>` + (open ? g.lots.map(slLotRowHtml).join("") : "");
}
export function slTableHtml(sales) {
  if (!sales || !sales.length) return `<p class="muted">No sales recorded for this selection.</p>`;
  slGroupsNow = [...window.slGroupSales(sales.filter((x) => x.status !== "voided")), ...window.slGroupSales(sales.filter((x) => x.status === "voided"))];
  return `<div class="rc-scroll sl-scroll" role="region" aria-label="Sales" tabindex="0"><table class="rc-table"><thead><tr><th></th><th>Sale date</th><th>Account</th><th>Symbol</th><th class="rc-num">Shares</th>` +
    `<th class="rc-num">Proceeds</th><th class="rc-num">Basis</th><th class="rc-num">Gain</th><th>Term</th><th></th></tr></thead><tbody>${slGroupsNow.map(slSaleRowHtml).join("")}</tbody></table></div>`;
}
export function slToggleSale(i) { const g = slGroupsNow[Number(i)]; if (g) { if (!slOpenSales.delete(g.key)) slOpenSales.add(g.key); slPaint(); } }
// KPI strip: the server's summary (same filter as Tax year), realized before carryforward.
export function slKpiHtml(t) {
  if (!t) return "";
  return `<p class="sl-kpi"><strong>${Number(t.sales)}</strong> sale${t.sales === 1 ? "" : "s"} · short-term realized ${slGainHtml(t.st_gain)} · long-term realized ${slGainHtml(t.lt_gain)} · fees ${slMoney(t.fees)}</p>`;
}
// Year list: "All years" plus only the years the server says have rows. Before the list arrives the chosen year stands in for it.
export function slYearOptionsHtml(years, selected) {
  const list = years.length ? [...years].map(String) : selected ? [String(selected)] : [];
  return `<option value=""${selected ? "" : " selected"}>All years</option>` +
    [...new Set(list)].sort().reverse().map((y) => `<option value="${y}"${y === String(selected) ? " selected" : ""}>${y}</option>`).join("");
}
export const slHiddenVoidCount = () => slHiddenVoids;
const slHiddenText = () => `Voided rows (${slHiddenVoids})`;
// Names the accounts the Taxable-only switch covers, from the friendly label helper (never raw ids).
const slTaxableNames = () => {
  try { return slTaxAccts.map((a) => accountDisplayLabel(a)).join(", "); } catch (e) { return ""; }
};
export function slHeadHtml() {
  const hc = window.slHeadControlState ? window.slHeadControlState(window.slCurrentTab()) : { disabled: false, title: "" };
  const dis = hc.disabled ? ` disabled aria-disabled="true" title="${esc(hc.title)}"` : "";
  const cls = hc.disabled ? ' class="sl-ctl-off"' : "";
  const names = slTaxableNames();
  return `<label>Year <select id="slYear" onchange="slSetYear(this.value)">${slYearOptionsHtml(slYears, slYear)}</select></label> ` +
    `<label${cls}><input type="checkbox" id="slTaxableBox"${dis} ${hc.disabled || slTaxableOnly() ? "checked" : ""} onchange="slSetTaxableOnly(this.checked)"> Taxable accounts only</label>` +
    `${names ? ` <span class="muted" id="slTaxableNames">${esc(names)}</span>` : ""} ` +
    `<a href="#" class="sl-voided-link" id="slVoidedLink" aria-pressed="${slShowVoided}" onclick="slSetShowVoided(!${slShowVoided});return false">${slHiddenText()}</a>`;
}
function slListHtml() {
  const msg = panelMsgHtml("sl", slMessage);
  const bar = `<div class="sl-toolbar">${slKpiHtml(slSum)}</div>`;
  return msg + bar + (slError ? `<p class="field-error">${esc(slError)}</p>` : slData ? slTableHtml(slData.sales) : `<p class="muted">Loading…</p>`);
}
// Holding-period check: sales of the Year whose lot has no purchase date on file (the log's backfill), so the term is a guess.
export function slHpHtml(c = slHp, year = slYear) {
  if (!c || !c.lots) return "";
  const link = window.hsActivityLink ? window.hsActivityLink({ type: "opening", source: "backfill", year, back: "sales" }) : "#holdings/activity";
  return `<div class="sl-hp" role="alert"><b>Holding-period check:</b> ${c.sales} sale row${c.sales === 1 ? "" : "s"} use ${c.lots} lot${c.lots === 1 ? "" : "s"} with no purchase date on file, so short- or long-term is a guess. ` +
    `<a href="${esc(link)}">Review in Activity</a> <span class="muted">(sales in accounts the log does not manage are not covered)</span></div>`;
}
let slHashApplied = null;
const SL_SECS = ["queue", "health", "wash", "tax", "cf", "b1099"];
function slConsumeHash() { // true when the hash was dropped from the address
  try { history.replaceState(null, "", location.pathname + location.search); return true; } catch (e) { return false; }
}
// Deep link: #sales_ledger?tab=tax&sec=b1099. Only read when the hash is ours; location may not exist (node tests).
export function slHashTarget() {
  let hash = "";
  try { hash = (typeof location !== "undefined" && location && location.hash) || ""; } catch (e) { hash = ""; }
  if (!hash.startsWith("#sales_ledger") || !window.slParseHash) return { tab: null, sec: null };
  const p = window.slParseHash(hash);
  return { tab: p.tab, sec: SL_SECS.includes(p.sec) ? p.sec : null };
}
const slTabsHtml = (active) => window.slTabBarHtml(active, window.slMarkers(window.slSummaries())) +
  `<div class="sl-secctl"><button type="button" class="btn" id="slExpandAll" onclick="slSecAll(null,true)">Expand all</button> ` +
  `<button type="button" class="btn" id="slCollapseAll" onclick="slSecAll(null,false)">Collapse all</button></div>`;
// Wrap a panel in the collapsible section shell; the panel's own markup is passed through untouched.
function slSection(key, title, fn, stateFn) {
  if (!window[fn]) return "";
  const sum = window.slSummaries()[key] || {};
  const badges = sum.text ? [{ text: sum.text, tone: sum.tone || "none" }] : [];
  const alert = window.slSecAlert(key);
  const open = window.slSecWantOpen(window.slUiLoad(), key, alert);
  return window.slSecHtml({ key, title, badges, state: stateFn && window[stateFn] ? window[stateFn]() : "", alertCount: alert, open, body: window[fn]() });
}
// Log health: a collapsible section once the log is started; the bare Start prompt (never inside a collapsible) before that.
export function slHealthSlotInnerHtml() {
  const bare = window.tlStarted && window.tlStarted() === false && window.renderLogHealth;
  return bare ? window.renderLogHealth() : slSection("health", "Log health", "renderLogHealth", "slHealthStateText");
}
export const slHealthSlotHtml = () => `<div id="tlHealthSlot">${slHealthSlotInnerHtml()}</div>`;
// Closed-summary state text for the two sections that collapse when empty.
export function slQueueStateText() {
  const q = window.slSummaries().queue;
  return !q ? "" : q.count > 0 ? "oldest first — pick the lots sold" : "Nothing waiting";
}
export function slHealthStateText() {
  const h = window.slSummaries().health;
  return !h ? "" : h.count > 0 ? h.text : window.tlStarted && window.tlStarted() ? "Log agrees with holdings" : "";
}
export const slLedgerBodyHtml = () => `${window.renderSalesEntry ? window.renderSalesEntry() : ""}<div id="slListRoot">${slListHtml()}</div>`;
function slPaintTabs() { // repaint the strip and tab bar without losing keyboard focus inside the tab bar
  const act = typeof document !== "undefined" && document.activeElement;
  const id = act && act.id;
  slPaintInto("slStripRoot", () => window.slStripHtml(window.slSummaries()));
  slPaintInto("slTabsRoot", () => slTabsHtml(window.slCurrentTab()));
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
  const { tab: hashTab, sec: hashSec } = slHashTarget();
  if (hashTab && hashTab !== slHashApplied) { // a deep link applies once; after that the current tab (slSetTab) decides
    slHashApplied = slConsumeHash() ? null : hashTab; // consumed: the same link applies again; no history: remember it instead
    window.slSetCurrentTab(hashTab);
    if (hashSec && window.slGo) setTimeout(() => { window.slGo(hashTab, hashSec); slConsumeHash(); }, 0); // after the page mounts
  }
  const active = window.slCurrentTab();
  const panel = (id, body) => window.slTabPanelHtml(id, body, active);
  const fix = slHpHtml() + slSection("queue", "Sales waiting for lots", "renderSalesQueue", "slQueueStateText") + slHealthSlotHtml() + slSection("wash", "Wash sales", "renderSalesWash", "swStateText");
  const ledger = slSection("ledger", "Sales", "slLedgerBodyHtml");
  return `<div id="slHeadRoot">${slHeadHtml()}</div>${window.slLiveHtml()}<div id="slStripRoot">${window.slStripHtml(window.slSummaries())}</div>` +
    `<div id="slTabsRoot">${slTabsHtml(active)}</div>` +
    panel("fix", fix) + panel("ledger", ledger) +
    panel("tax", slSection("tax", "Tax year", "renderSalesTaxYear") + slSection("b1099", "Import a 1099-B", "renderSalesBroker1099b", "bbStateText"));
}
export function renderSalesLedger() {
  slSubscribeSummaries();
  if (slData === null && !slLoading && !slError) setTimeout(loadSalesLedger, 0);
  return `<div class="field-list sl-page" id="slRoot">${slBodyHtml()}</div>`;
}
function slPaintInto(id, html) { const el = typeof document !== "undefined" && document.getElementById(id); if (el) el.innerHTML = html(); }
function slPaint() { slPaintInto("slListRoot", slListHtml); }
export async function loadSalesLedger() {
  slLoading = true;
  slError = "";
  try {
    try {
      const y = await api("/api/sales/years");
      slYears = ((y && y.years) || []).map(Number);
      slTaxAccts = (y && y.taxable_accounts) || [];
      if (window.seSetAccounts) window.seSetAccounts(y && y.account_classes);
    } catch (e) { slYears = []; }
    if (!slYearChosen && slYears.length) { slYearChosen = true; slYear = String(slYears.includes(new Date().getFullYear()) ? new Date().getFullYear() : slYears[slYears.length - 1]); if (window.sqLoadHistory) window.sqLoadHistory(); }
    const year = slYear; // a year/Voided-rows change mid-load must not pair the count with another selection
    const showVoided = slShowVoided;
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
    if (out && out.sales && slTaxableOnly()) out.sales = out.sales.filter((x) => x.tax_class === "taxable");
    slData = out && out.success ? out : null;
    if (window.bbSetState) {
      const taxable = ((out && out.sales) || []).filter((x) => x.tax_class === "taxable" && x.status === "confirmed");
      window.bbSetState({ year: year ? Number(year) : null, taxableSales: taxable.length, has1099b: taxable.some((x) => x.statement_id != null) });
    }
    try { slSum = ((await api(`/api/sales/summary?${year ? `year=${encodeURIComponent(year)}&` : ""}taxable_only=${slTaxableOnly() ? 1 : 0}`)) || {}).summary || null; } catch (e) { slSum = null; }
    try { slHp = year ? ((await api(`/api/sales/holding-period-check?year=${encodeURIComponent(year)}`)) || {}).check || null : null; } catch (e) { slHp = null; }
    if (!slData) slError = "The ledger could not be loaded.";
    await slLoadHiddenVoids(year, showVoided);
    if (window.slPublish && slData) window.slPublish("ledger", { count: slData.sales.length, tone: "", text: `${slData.sales.length} sale${slData.sales.length === 1 ? "" : "s"}` });
    if (window.loadSalesWash) window.loadSalesWash();
    if (year && window.loadSalesTaxYear) window.loadSalesTaxYear(year);
    else if (window.stRepaint) window.stRepaint();
    slPaintInto("slHeadRoot", slHeadHtml);
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
      slHiddenVoids = ((all && all.sales) || []).filter((x) => x.status === "voided" && (!slTaxableOnly() || x.tax_class === "taxable")).length;
    } catch (e) { slHiddenVoids = 0; }
  }
}
async function slPost(url, body, okText) {
  let out;
  try {
    out = await api(url, { method: "POST", body: JSON.stringify(body || {}) });
    slMessage = { text: okText, error: false };
  } catch (e) {
    slMessage = { text: e.message, error: true };
  }
  await loadSalesLedger();
  return out;
}
export function slEdit(id) { const s = slData && slData.sales.find((x) => Number(x.sale_id) === Number(id)); if (s && window.seEdit) window.seEdit(s); }
export function slAfterEntry(text) { slMessage = { text, error: false }; return loadSalesLedger(); }
export async function slRequeue(id) {
  const out = await slPost(`/api/sales/${Number(id)}/requeue`, null, "Sale sent back to the queue; its shares are back in their lots. It is waiting on the Fix tab.");
  if (out && window.sqReload) window.sqReload();
  if (out && window.slGo) window.slGo("fix", "queue");
}
export async function slVoid(id) {
  const s = slData && slData.sales.find((x) => Number(x.sale_id) === Number(id));
  const gain = s && s.gain !== null && s.gain !== undefined ? (s.gain > 0 ? "+" : "") + slMoney(s.gain) : "this sale";
  const year = s && s.sale_date ? String(s.sale_date).slice(0, 4) : slYear || "all-years";
  const logLinked = !!s && (s.lot_key || "").includes("log_sell"); // its log sale is removed with the void, so Restore is unavailable
  const out = `It comes out of ${year} totals (${gain}). `;
  const consequence = out + (logLinked ? "This also removes the linked transaction-log sale and returns its shares to the lot. Restore will not be available for this sale; to bring it back you would record the sale again." : "Restore brings it back.");
  if (!(await confirmDestructive(consequence, { title: "Void this sale?", action: "Void sale" }))) return undefined;
  return slPost(`/api/sales/${Number(id)}/void`, null, logLinked ? "Sale voided." : "Sale voided. Use Restore to bring it back.");
}
export const slUnvoid = (id) => slPost(`/api/sales/${Number(id)}/unvoid`, null, "Sale restored.");
export function slSetYear(v) { slYear = String(v || "").trim(); slYearChosen = true; if (window.sqYearChanged) window.sqYearChanged(); return loadSalesLedger(); }
export function slSetShowVoided(on) { slShowVoided = !!on; return loadSalesLedger(); }
export function slSetTaxableOnly(on) {
  if (window.slUiLoad) window.slUiSave({ ...window.slUiLoad(), taxableOnly: !!on });
  return loadSalesLedger();
}
Object.assign(window, {
  slMoney, slGainHtml, slHpHtml, slLotRowHtml, slSaleRowHtml, slTableHtml, slToggleSale, slKpiHtml, renderSalesLedger, slHashTarget, loadSalesLedger, slAfterEntry, slVoid, slUnvoid,
  slSetYear, slSetShowVoided, slSetTaxableOnly, slCurrentYear, slTaxableOnly, slYearOptionsHtml, slHeadHtml, slEdit, slRequeue, slHealthSlotHtml, slHealthSlotInnerHtml, slQueueStateText, slHealthStateText, slLedgerBodyHtml, slHiddenVoidCount,
});