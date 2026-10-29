// Sales Ledger page (Reports & Review): record a realized sale by hand or from a CSV and list the ledger.
// Logic lives on the server (src/sales_service.py, /api/sales*): the page collects a row, posts it, and
// lists the result. One row is one lot (or part of a lot) sold, with that lot's basis and purchase date.
// Nothing reads the ledger yet (Phase 1). Helpers are bare globals; renderMain() calls renderSalesLedger().

const SL_CLASSES = [["taxable", "Taxable"], ["pre_tax", "Pre-tax (IRA/401k)"], ["roth", "Roth"], ["hsa", "HSA"]];
const SL_TERM = { short: "Short", long: "Long", unknown: "Unknown" };

let slData = null;
let slYear = String(new Date().getFullYear());
let slShowVoided = false;
let slPreview = null;
let slMessage = null; // { text, error }
let slLoading = false;
let slError = "";

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
  const action = voided
    ? `<button class="btn" type="button" onclick="slUnvoid(${Number(s.sale_id)})">Restore</button>`
    : `<button class="btn" type="button" onclick="slVoid(${Number(s.sale_id)})">Void</button>`;
  return `<tr class="${voided ? "sl-voided" : ""}"><td>${esc(s.sale_date)}</td><td>${esc(s.account)}</td><td>${esc(s.symbol)}</td>` +
    `<td class="rc-num">${esc(String(s.shares))}</td><td class="rc-num">${slMoney(s.proceeds)}</td><td class="rc-num">${slMoney(s.fees)}</td>` +
    `<td class="rc-num">${slMoney(s.basis)}</td><td>${slGainHtml(s.gain)}</td><td>${esc(SL_TERM[s.holding_period] || "")}</td><td>${action}</td></tr>`;
}

export function slTableHtml(sales) {
  if (!sales || !sales.length) return `<p class="muted">No sales recorded for this selection.</p>`;
  return `<div class="rc-scroll"><table class="rc-table"><thead><tr><th>Sale date</th><th>Account</th><th>Symbol</th><th class="rc-num">Shares</th>` +
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

function slFormHtml() {
  const input = (id, label, type = "text", extra = "") => `<label>${label}<input id="${id}" type="${type}" ${extra}></label>`;
  return `<div class="sl-form"><h3>Record a sale</h3><div class="field-grid">` +
    input("slDate", "Sale date", "date") + input("slAccount", "Account") +
    `<label>Account type<select id="slClass">${SL_CLASSES.map(([v, l]) => `<option value="${v}">${l}</option>`).join("")}</select></label>` +
    input("slSymbol", "Symbol") + input("slShares", "Shares sold", "number", 'step="any" min="0"') +
    input("slProceeds", "Proceeds ($)", "number", 'step="any"') + input("slFees", "Fees ($)", "number", 'step="any" min="0"') +
    input("slBasis", "Cost basis of these shares ($)", "number", 'step="any"') + input("slPurchase", "Lot purchase date", "date") +
    `</div><p class="muted">One row per lot sold. Gain is proceeds − fees − basis; it is left blank for pre-tax, Roth and HSA accounts.</p>` +
    `<button class="btn primary" type="button" onclick="slSubmit()">Add sale</button></div>`;
}

function slImportHtml() {
  return `<div class="sl-import"><h3>Import from CSV</h3><p class="muted">Columns: sale_date, account, tax_class, symbol, shares, proceeds, basis (required); fees, purchase_date.</p>` +
    `<textarea id="slCsv" rows="5" aria-label="Sales CSV" placeholder="Paste CSV text here"></textarea>` +
    `<input type="file" accept=".csv,text/csv" aria-label="Choose a CSV file" onchange="slCsvFile(this)">` +
    `<button class="btn" type="button" onclick="slImportPreview()">Preview</button>${slPreview ? slPreviewHtml(slPreview) : ""}</div>`;
}

function slBodyHtml() {
  const msg = slMessage ? `<p class="${slMessage.error ? "field-error" : "muted"}" role="status">${esc(slMessage.text)}</p>` : "";
  const list = slError ? `<p class="field-error">${esc(slError)}</p>` : slData ? slTotalsHtml(slData.totals) + slTableHtml(slData.sales) : `<p class="muted">Loading…</p>`;
  return `<h2>Sales Ledger</h2>${msg}${slFormHtml()}${slImportHtml()}<h3>Ledger</h3>` +
    `<label>Year <input id="slYear" type="number" value="${esc(slYear)}" onchange="slSetYear(this.value)"></label> ` +
    `<label><input type="checkbox" ${slShowVoided ? "checked" : ""} onchange="slSetShowVoided(this.checked)"> Show voided</label>${list}`;
}

export function renderSalesLedger() {
  if (slData === null && !slLoading && !slError) setTimeout(loadSalesLedger, 0);
  return `<div class="field-list sl-page" id="slRoot">${slBodyHtml()}</div>`;
}

function slPaint() {
  const root = document.getElementById("slRoot");
  if (root) root.innerHTML = slBodyHtml();
}

export async function loadSalesLedger() {
  slLoading = true;
  slError = "";
  try {
    const q = new URLSearchParams();
    if (slYear) q.set("year", slYear);
    if (slShowVoided) q.set("include_voided", "1");
    const out = await api("/api/sales?" + q);
    slData = out && out.success ? out : null;
    if (!slData) slError = "The ledger could not be loaded.";
  } catch (e) {
    slData = null;
    slError = "The ledger could not be loaded: " + e.message;
  }
  slLoading = false;
  slPaint();
}

const val = (id) => { const el = document.getElementById(id); return el ? el.value : ""; };

async function slPost(url, body, okText) {
  let out;
  try {
    out = await api(url, { method: "POST", body: JSON.stringify(body || {}) });
    slMessage = { text: okText, error: false };
    slPreview = null;
  } catch (e) {
    slMessage = { text: e.message, error: true };
  }
  await loadSalesLedger();
  return out;
}

export async function slSubmit() {
  await slPost("/api/sales", {
    sale_date: val("slDate"), account: val("slAccount"), tax_class: val("slClass"), symbol: val("slSymbol"), shares: val("slShares"),
    proceeds: val("slProceeds"), fees: val("slFees"), basis: val("slBasis"), purchase_date: val("slPurchase"),
  }, "Sale recorded.");
}

export const slVoid = (id) => slPost(`/api/sales/${Number(id)}/void`, null, "Sale voided. Use Restore to bring it back.");
export const slUnvoid = (id) => slPost(`/api/sales/${Number(id)}/unvoid`, null, "Sale restored.");
export function slSetYear(v) { slYear = String(v || "").trim(); return loadSalesLedger(); }
export function slSetShowVoided(on) { slShowVoided = !!on; return loadSalesLedger(); }

export function slCsvFile(input) {
  const file = input.files && input.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => { const el = document.getElementById("slCsv"); if (el) el.value = String(reader.result || ""); };
  reader.readAsText(file);
}

export async function slImportPreview() {
  try {
    slPreview = await api("/api/sales/import/preview", { method: "POST", body: JSON.stringify({ content: val("slCsv") }) });
    slMessage = null;
  } catch (e) {
    slPreview = null;
    slMessage = { text: e.message, error: true };
  }
  slPaint();
}

export async function slImportCommit() {
  const out = await slPost("/api/sales/import/commit", { content: val("slCsv") }, "Import complete.");
  if (out && out.written !== undefined) {
    slMessage = { text: `Added ${out.written} sale${out.written === 1 ? "" : "s"}.`, error: false };
    slPaint();
  }
}

Object.assign(window, {
  slMoney, slGainHtml, slRowHtml, slTableHtml, slTotalsHtml, slPreviewHtml, renderSalesLedger, loadSalesLedger, slSubmit, slVoid, slUnvoid,
  slSetYear, slSetShowVoided, slCsvFile, slImportPreview, slImportCommit,
});
