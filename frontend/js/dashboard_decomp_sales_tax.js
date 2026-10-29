// Sales Ledger tax-year panel (plan step 3a.3): the year's realized gain/loss netting, the prior-year carryforward
// entry and the possible-wash warnings. All figures come from the server (src/sales_tax_year.py, /api/sales/tax-year,
// /api/sales/carryforward, /api/sales/wash/refresh); this only displays them and posts the two inputs.
// Nothing here changes the projection. Helpers are bare globals; the Sales Ledger page calls renderSalesTaxYear()
// and reloads it with loadSalesTaxYear(year) whenever the ledger loads.

let stData = null;
let stMessage = null; // { text, error }
let stError = "";

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
    stRow("Carried to next year, short-term", n.carryforward_st) +
    stRow("Carried to next year, long-term", n.carryforward_lt) + `</tbody></table></div>`;
}

export function stCarryforwardHtml(s) {
  const cf = s.carryforward_in;
  const how = cf.entered ? "Entered from your Schedule D." : "Estimated from your earlier sales; enter last year's Schedule D figures to replace this.";
  const input = (id, label, v) => `<label>${label}<input id="${id}" type="number" min="0" step="any" value="${esc(String(v))}"></label>`;
  return `<div class="st-carry"><h4>Capital-loss carryforward into ${esc(String(s.year))}</h4>` +
    `<div class="field-grid">${input("stCfShort", "Short-term ($, positive)", cf.short)}${input("stCfLong", "Long-term ($, positive)", cf.long)}</div>` +
    `<p class="muted">${esc(how)}</p><button class="btn" type="button" onclick="stSaveCarryforward()">Save carryforward</button></div>`;
}

export function stWashHtml(w) {
  const check = `<button class="btn" type="button" onclick="stRefreshWash()">Check for wash sales</button>`;
  if (!w.count) return `<div class="st-wash"><h4>Wash sales</h4><p class="muted">No losses are flagged as possible wash sales.</p>${check}</div>`;
  const items = w.rows.map((r) => `<li>${esc(r.sale_date)} ${esc(r.symbol)} (${esc(stMoney(r.gain))}): ${esc(r.note)}</li>`).join("");
  return `<div class="st-wash"><h4>Wash sales</h4><p class="field-error" role="status">${esc(stMoney(w.flagged_loss))} of losses flagged as possible wash sales — this may overstate the deduction.</p>` +
    `<ul>${items}</ul><p class="muted">Flag only: nothing is disallowed or adjusted here, and a repurchase in an IRA loses the loss with no basis add-back.</p>${check}</div>`;
}

function stBodyHtml() {
  if (stError) return `<h3>Realized gains this year</h3><p class="field-error">${esc(stError)}</p>`;
  if (!stData) return `<h3>Realized gains this year</h3><p class="muted">Loading…</p>`;
  const msg = stMessage ? `<p class="${stMessage.error ? "field-error" : "muted"}" role="status">${esc(stMessage.text)}</p>` : "";
  return `<h3>Realized gains for ${esc(String(stData.year))}</h3>${msg}${stNettingHtml(stData)}${stCarryforwardHtml(stData)}${stWashHtml(stData.wash)}`;
}

export function renderSalesTaxYear() {
  return `<div class="st-panel" id="stRoot">${stBodyHtml()}</div>`;
}

function stPaint() {
  const root = document.getElementById("stRoot");
  if (root) root.innerHTML = stBodyHtml();
}

export async function loadSalesTaxYear(year) {
  stError = "";
  try {
    const out = await api("/api/sales/tax-year?year=" + encodeURIComponent(year));
    stData = out && out.success ? out : null;
    if (!stData) stError = "The tax-year summary could not be loaded.";
  } catch (e) {
    stData = null;
    stError = "The tax-year summary could not be loaded: " + e.message;
  }
  stPaint();
}

const stVal = (id) => { const el = document.getElementById(id); return el ? el.value : ""; };

async function stPost(url, body, okText) {
  const year = stData && stData.year;
  try {
    await api(url, { method: "POST", body: JSON.stringify(body || {}) });
    stMessage = { text: okText, error: false };
  } catch (e) {
    stMessage = { text: e.message, error: true };
  }
  if (year) await loadSalesTaxYear(year);
  else stPaint();
}

export function stSaveCarryforward() {
  if (!stData) return Promise.resolve();
  return stPost("/api/sales/carryforward", { year: stData.year, carryforward_short: stVal("stCfShort"), carryforward_long: stVal("stCfLong") }, "Carryforward saved.");
}

export const stRefreshWash = () => stPost("/api/sales/wash/refresh", null, "Wash-sale check done.");

Object.assign(window, { stNettingHtml, stCarryforwardHtml, stWashHtml, renderSalesTaxYear, loadSalesTaxYear, stSaveCarryforward, stRefreshWash });
