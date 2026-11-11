// Sales Ledger tax-year panel (plan step 3a.3): the year's realized gain/loss netting, the prior-year carryforward
// entry and the possible-wash warnings. All figures come from the server (src/sales_tax_year.py, /api/sales/tax-year,
// /api/sales/carryforward, /api/sales/wash/refresh); this only displays them and posts the two inputs.
// Nothing here changes the projection. Helpers are bare globals; the Sales Ledger page calls renderSalesTaxYear()
// and reloads it with loadSalesTaxYear(year) whenever the ledger loads.
let stData = null;
let stMessage = null; // { text, error }
let stError = "";
let stCfDraft = null; // { year, stCfShort, stCfLong }: typed carryforward text survives any repaint until it is saved
let stIncome = null; // GET /api/investment-income: the year's interest and dividends by type, taxable accounts only
let stYearEnd = null; // { year, open, total } from GET /api/year-end; null when unavailable
const stMoney = (v) => (Number(v) < 0 ? "-$" : "$") + Math.abs(Number(v) || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const stRow = (label, value, note = "") => `<tr><th scope="row">${label}</th><td class="rc-num">${stMoney(value)}</td><td class="muted">${note}</td></tr>`;
export function stNettingHtml(s) {
  if (!s.totals || !s.totals.count) return `<p class="muted">No taxable sales recorded for ${esc(String(s.year))}.</p>`;
  const n = s.netting;
  return `<div class="rc-scroll"><table class="rc-table"><tbody>` +
    stRow("Short-term net", n.net_st, "after any short-term carryforward in") +
    stRow("Long-term net", n.net_lt, "after any long-term carryforward in") +
    stRow("Taxed as ordinary income", n.gain_to_tax_ordinary, "short-term gain left after netting") +
    stRow("Taxed at long-term rates", n.gain_to_tax_ltcg, "long-term gain left after netting") +
    stRow("Loss deducted against other income", n.ordinary_offset, `${esc(stMoney(s.limit))} limit (${esc(s.filing)})`) +
    (s.wash && s.wash.disallowed ? stRow("Wash-sale losses disallowed", s.wash.disallowed, `deferred ${esc(stMoney(s.wash.deferred))} · lost in IRA ${esc(stMoney(s.wash.lost_permanently))} <a href="#sales_ledger?tab=fix&amp;sec=wash" onclick="if(window.slGo){slGo('fix','wash');return false}">See the wash sales</a>`) : "") +
    stRow("Carried to next year, short-term", n.carryforward_st) +
    stRow("Carried to next year, long-term", n.carryforward_lt) + `</tbody></table></div>`;
}
export function stTaxHtml(s) {
  const t = s.realized_tax;
  if (!t) return "";
  if (!t.available) return `<p class="muted">${esc(t.reason || "Tax on gains realized this year is not available.")}</p>`;
  return `<h4>Tax on gains realized in ${esc(String(s.year))}</h4><div class="rc-scroll"><table class="rc-table"><tbody>` +
    stRow("Federal tax on ordinary gain", t.ordinary_tax) + stRow("Federal tax on long-term gain", t.ltcg_tax) +
    stRow("Net investment income tax", t.niit) + stRow("State tax", t.state_tax) + stRow("Estimated tax on gains realized this year", t.total) +
    `</tbody></table></div><p class="muted">${esc(t.note)} Separate from the estimated tax on unrealized gains.</p>`;
}
export function stCarryforwardHtml(s) {
  const cf = s.carryforward_in;
  const how = cf.entered ? "Entered from your Schedule D." : "Estimated from your earlier sales; enter last year's Schedule D figures to replace this.";
  const d = stCfDraft && stCfDraft.year === s.year ? stCfDraft : {};
  const input = (id, label, v) => `<label>${label}<input id="${id}" type="number" min="0" step="any" value="${esc(String(d[id] ?? v))}" oninput="stCfDraftSet('${id}',this.value)"></label>`;
  return `<div class="st-carry"><h4>Loss carried in from ${esc(String(Number(s.year) - 1))}</h4>` +
    `<div class="field-grid">${input("stCfShort", "Short-term ($, positive)", cf.short)}${input("stCfLong", "Long-term ($, positive)", cf.long)}</div>` +
    `<p class="muted">${esc(how)}</p><button class="btn" type="button" onclick="stSaveCarryforward()">Save carryforward</button></div>`;
}
export function stCfDraftSet(id, v) {
  if (!stData || (id !== "stCfShort" && id !== "stCfLong")) return;
  if (!stCfDraft || stCfDraft.year !== stData.year) stCfDraft = { year: stData.year };
  stCfDraft[id] = String(v ?? "");
}
export function stTilesHtml(s) {
  const n = s.netting || {};
  const num = (v) => (Number.isFinite(Number(v)) ? Number(v) : 0);
  const tone = (v) => (v < 0 ? " dn" : v > 0 ? " up" : "");
  const tile = (label, v, text) => `<div class="tile sl-tile"><div class="l">${label}</div><div class="v${tone(v)}">${text}</div></div>`;
  const st = num(n.net_st), lt = num(n.net_lt), cf = num(n.carryforward_st) + num(n.carryforward_lt);
  const tax = s.realized_tax && s.realized_tax.available ? stMoney(num(s.realized_tax.total)) : "—";
  return `<div class="tiles sl-tiles">${tile("Short-term net", st, stMoney(st))}${tile("Long-term net", lt, stMoney(lt))}${tile("Estimated tax", 0, tax)}${tile("Carryforward out", 0, stMoney(cf))}</div>`;
}
export function st1099bStatusRowHtml(status) {
  const n = Number(status && status.count) || 0;
  const text = status && (status.tone === "warn" || status.tone === "bad") && n > 0 ? `${n} account${n === 1 ? "" : "s"} not tied` : "No 1099-B differences recorded";
  return `<p class="st-link-row">1099-B: ${esc(text)} <a href="#sales_ledger?tab=tax&amp;sec=b1099" onclick="if(window.slGo){slGo('tax','b1099');return false}">Review 1099-B</a></p>`;
}
export function stYearEndLinkHtml(openCount, total, year) {
  if (!(Number(total) > 0)) return "";
  return `<p class="st-link-row"><a href="#year_end" onclick="if(window.setStep){setStep('year_end');return false}">Year-end steps (${esc(String(year))}): ${Number(openCount) || 0} of ${Number(total)} open → Year-End Transition</a></p>`;
}
// Interest and dividends by type, for the accountant: totals per account, a per-symbol type chooser and a CSV.
export function stIncomeHtml(d) {
  if (!d || !d.rows || !d.rows.length) return "";
  const cols = Object.keys(d.totals).sort();
  const acct = Object.entries(d.by_account).map(([a, t]) => `<tr><th scope="row">${esc(accountDisplayLabel(a))}</th>${cols.map((c) => `<td class="rc-num">${t[c] === undefined ? "" : stMoney(t[c])}</td>`).join("")}</tr>`).join("");
  const total = `<tr><th scope="row">All taxable accounts</th>${cols.map((c) => `<td class="rc-num"><b>${stMoney(d.totals[c])}</b></td>`).join("")}</tr>`;
  const opts = (cur) => Object.entries(d.labels).map(([k, l]) => `<option value="${k}"${k === cur ? " selected" : ""}>${esc(l)}</option>`).join("");
  const syms = `<table class="rc-table st-types"><thead><tr><th>Symbol</th><th>Counted as</th></tr></thead><tbody>${d.symbols.map((x) => `<tr><th scope="row">${esc(x.symbol)}</th><td><select aria-label="Fund type of ${esc(x.symbol)}" onchange="stSetSymbolType('${esc(x.symbol)}', this.value)">${opts(x.type)}</select></td></tr>`).join("")}</tbody></table>`;
  return `<div class="st-income"><h4>Interest and dividends ${esc(String(d.year))} (taxable accounts)</h4><div class="rc-scroll"><table class="rc-table"><thead><tr><th></th>${cols.map((c) => `<th class="rc-num">${esc(d.labels[c] || c)}</th>`).join("")}</tr></thead><tbody>${acct}${total}</tbody></table></div>` +
    `<p class="muted">${esc(d.notes[d.notes.length - 1])}</p>${d.notes.slice(0, -1).map((n) => `<p class="field-error">${esc(n)}</p>`).join("")}` +
    `<details><summary>Fund types (change how a symbol is counted)</summary>${syms}</details>` +
    `<p><a href="/api/investment-income.csv?year=${encodeURIComponent(d.year)}" download>Download CSV for your accountant</a></p></div>`;
}
export function stSetSymbolType(symbol, type) {
  return stPost("/api/investment-income/symbol-type", { symbol, type }, "Fund type saved.");
}
function stBodyHtml() {
  if (window.slCurrentYear && window.slCurrentYear() === "") return `<h3>Tax year</h3><p class="muted">Pick a year above: tax is worked out one year at a time, so there is no all-years total.</p>`;
  if (stError) return `<h3>Realized gains this year</h3><p class="field-error">${esc(stError)}</p>`;
  if (!stData) return `<h3>Realized gains this year</h3><p class="muted">Loading…</p>`;
  const msg = panelMsgHtml("st", stMessage);
  const b = window.slSummaries && window.slSummaries().b1099;
  const ye = stYearEnd ? stYearEndLinkHtml(stYearEnd.open, stYearEnd.total, stYearEnd.year) : "";
  return `<h3>Tax year ${esc(String(stData.year))} · sales dated 1/1–12/31</h3>${msg}${stTilesHtml(stData)}${st1099bStatusRowHtml(b)}${ye}` +
    `<div class="sl-tax-cols"><div>${stNettingHtml(stData)}${stTaxHtml(stData)}</div><div>${stCarryforwardHtml(stData)}</div></div>${stIncomeHtml(stIncome)}`;
}
export function renderSalesTaxYear() {
  return `<div class="st-panel" id="stRoot">${stBodyHtml()}</div>`;
}
// Only a carryforward that is actually carried in but was never entered is a signal; "entered: false" alone is the normal
// state for anyone with no carryforward, so it would be a permanent false alarm. Saving the figures (even as zero) clears it.
function stCfUnsaved() {
  const cf = stData && stData.carryforward_in;
  return !!cf && cf.entered === false && (Number(cf.short) > 0 || Number(cf.long) > 0);
}
// Only a carryforward that is carried in but never entered is a signal (the wash cards publish their own summary in To fix).
export function stSummary() {
  return { cf: stCfUnsaved() ? { count: 0, tone: "warn", text: "carryforward not saved" } : { count: 0, tone: "", text: "" } };
}
function stPaint() {
  const root = document.getElementById("stRoot");
  if (root) root.innerHTML = stBodyHtml();
  if (window.slPublish) window.slPublish("cf", stSummary().cf);
}
export async function loadSalesTaxYear(year) {
  stError = "";
  const taxReq = api("/api/sales/tax-year?year=" + encodeURIComponent(year));
  try {
    const out = await taxReq;
    stData = out && out.success ? out : null;
    if (!stData) stError = "The tax-year summary could not be loaded.";
  } catch (e) {
    stData = null;
    stError = "The tax-year summary could not be loaded: " + e.message;
  }
  try { const inc = await api("/api/investment-income?year=" + encodeURIComponent(year)); stIncome = inc && inc.success ? inc : null; } catch (e) { stIncome = null; }
  stPaint();
  // /api/year-end rescans every purchase for the wash signature, so it is fetched only while the Tax tab is showing
  // (and again when the tab is next shown after a reload); the link row is the only thing that needs it.
  stYeStale = true;
  if (stTabShown()) await stLoadYearEnd();
}
const stTabShown = () => !window.slCurrentTab || window.slCurrentTab() === "tax";
let stYeStale = true;
let stYeBusy = false;
async function stLoadYearEnd() {
  if (stYeBusy) return;
  stYeBusy = true;
  stYeStale = false;
  try {
    const r = await api("/api/year-end");
    const steps = r && Array.isArray(r.steps) ? r.steps : [];
    stYearEnd = steps.length ? { year: r.year, total: steps.length, open: steps.filter((x) => x && x.state === "open").length } : null;
  } catch (e) { stYearEnd = null; }
  stYeBusy = false;
  stPaint();
}
// Called by the page when the Tax tab is shown: fetch the year-end counts if a load skipped them.
export function stOnShown() { if (stYeStale && stData) return stLoadYearEnd(); return undefined; }
async function stPost(url, body, okText, onOk) {
  const year = stData && stData.year;
  try {
    await api(url, { method: "POST", body: JSON.stringify(body || {}) });
    stMessage = { text: okText, error: false };
    if (onOk) onOk();
  } catch (e) {
    stMessage = { text: e.message, error: true };
  }
  if (year) await loadSalesTaxYear(year);
  else stPaint();
}
export function stSaveCarryforward() {
  if (!stData) return Promise.resolve();
  const d = stCfDraft && stCfDraft.year === stData.year ? stCfDraft : {};
  const pick = (id) => { const el = document.getElementById(id); return el ? el.value : (d[id] ?? ""); };
  return stPost("/api/sales/carryforward", { year: stData.year, carryforward_short: pick("stCfShort"), carryforward_long: pick("stCfLong") }, "Carryforward saved.", () => { stCfDraft = null; });
}
Object.assign(window, { stRepaint: stPaint, stTilesHtml, st1099bStatusRowHtml, stYearEndLinkHtml, stSummary, stNettingHtml, stTaxHtml, stCarryforwardHtml, stCfDraftSet, stOnShown, stIncomeHtml, stSetSymbolType, renderSalesTaxYear, loadSalesTaxYear, stSaveCarryforward });