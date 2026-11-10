// Sales Ledger: the Record sales grid (one row per sale, Lots chip, lot chooser). Pure helpers first, then the card.
// The server (src/sales_service.py add_sales, /api/sales/batch, /api/sales/open-lots) owns the rules; this collects rows.
const SE_EPS = 1e-6;
const SE_FIELDS = ["account", "symbol", "date", "shares", "proceeds", "fees"];
const seNum = (v) => { const n = Number(v); return Number.isFinite(n) ? n : 0; };
const seFmt = (x) => String(+seNum(x).toFixed(4));
const seMoney = (v) => (v < 0 ? "-$" : "$") + Math.abs(seNum(v)).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const seBasis = (p) => (p.basis !== undefined && p.basis !== "" ? seNum(p.basis) : seNum(p.shares) * seNum(p.unit_cost));
// Tick lots in order until `shares` are covered. "losses" takes the lowest gain per share first, at the row's sale price.
export function seFill(lots, shares, method, price = 0) {
  const by = { fifo: (a, b) => String(a.purchase_date).localeCompare(String(b.purchase_date)) || a.txn_id - b.txn_id,
    hifo: (a, b) => b.unit_cost - a.unit_cost || a.txn_id - b.txn_id, losses: (a, b) => (price - a.unit_cost) - (price - b.unit_cost) || a.txn_id - b.txn_id };
  let need = seNum(shares);
  const out = {};
  for (const l of [...lots].sort(by[method] || by.fifo)) {
    const take = Math.min(need, seNum(l.open_shares));
    if (need <= SE_EPS) break;
    if (take > SE_EPS) { out[l.txn_id] = +take.toFixed(6); need -= take; }
  }
  return out;
}
export function seRowState(r) {
  const picks = (r.picks || []).filter((p) => seNum(p.shares) > SE_EPS);
  const want = seNum(r.shares), got = picks.reduce((a, p) => a + seNum(p.shares), 0);
  const matched = want > SE_EPS && Math.abs(want - got) <= 1e-4;
  const basis = picks.reduce((a, p) => a + seBasis(p), 0);
  const gain = r.taxable === false ? null : seNum(r.proceeds) - seNum(r.fees) - basis;
  const terms = new Set(picks.map((p) => p.term).filter(Boolean));
  return { matched, basis, gain, gainText: gain === null ? "not taxable" : "", term: terms.size > 1 ? "Mixed" : [...terms][0] || "",
    label: matched ? `${picks.length} lot${picks.length === 1 ? "" : "s"} ✓` : `${seFmt(got)} / ${seFmt(want)} · pick` };
}
export const seCanSave = (rows) => rows.length > 0 && rows.every((r) => seRowState(r).matched);
// Enter in the last field of the last row adds a row; elsewhere Enter just moves on.
export const seKeyAction = (rows, ri, fi, key) => (key !== "Enter" ? "none" : ri === rows.length - 1 && fi === SE_FIELDS.length - 1 ? "add-row" : "next");
export const seActivityLink = (account, symbol) => (window.hsActivityLink ? window.hsActivityLink({ account, symbol, type: "buy", back: "sales" })
  : `#holdings/activity?account=${encodeURIComponent(account)}&symbol=${encodeURIComponent(symbol)}&type=buy&back=sales`);
// One request per lot row: proceeds and fees split by shares (the last takes the remainder), linked to its log lot when chosen.
export function seBatchRows(rows) {
  const out = [];
  for (const r of rows) {
    const picks = r.picks.filter((p) => seNum(p.shares) > SE_EPS), total = seNum(r.shares);
    let pLeft = seNum(r.proceeds), fLeft = seNum(r.fees);
    picks.forEach((p, i) => {
      const last = i === picks.length - 1, part = (x) => +(seNum(x) * seNum(p.shares) / total).toFixed(2);
      const proceeds = last ? +pLeft.toFixed(2) : part(r.proceeds), fees = last ? +fLeft.toFixed(2) : part(r.fees);
      pLeft -= proceeds; fLeft -= fees;
      out.push({ sale_date: r.date, account: r.account, symbol: r.symbol, shares: seNum(p.shares), proceeds, fees, basis: +seBasis(p).toFixed(2),
        purchase_date: p.purchase_date || "", ...(p.txn_id ? { txn_lot: p.txn_id } : {}) });
    });
  }
  return out;
}
let seRows = [], seNext = 1, seOpenId = null, seShown = false, seMsg = null, seEditSale = null;
let seAccounts = [], seClasses = {}, seLots = {}; // seLots[account|symbol|date] = server answer for the chooser
const seBlank = () => ({ id: seNext++, account: "", symbol: "", date: "", shares: "", proceeds: "", fees: "", picks: [] });
const seKey = (r) => `${r.account}|${String(r.symbol).toUpperCase()}|${r.date}`;
const seRow = (id) => seRows.find((r) => r.id === Number(id));
const seTaxable = (r) => !r.account || (seClasses[r.account] || "taxable") === "taxable";
const seView = (r) => ({ ...r, taxable: seTaxable(r) });
const seTax = { taxable: "taxable", pre_tax: "pre-tax", roth: "Roth", hsa: "HSA" };
export function seSetAccounts(classes) { seClasses = classes || {}; seAccounts = Object.keys(seClasses).sort(); }
export const seRowsForTest = () => seRows;
const sePaint = () => { const el = typeof document !== "undefined" && document.getElementById("seRoot"); if (el) el.innerHTML = seBodyHtml(); };
export function seChooserHtml(r, d) {
  if (!d) return `<p class="muted">Looking up open lots…</p>`;
  if (!d.log_started) return `<div class="se-blank">${r.picks.map((p, i) => `<div>Bought <input type="date" value="${esc(p.purchase_date || "")}" onchange="seBlankSet(${r.id},${i},'purchase_date',this.value)"> ` +
    `Shares <input type="number" step="any" value="${esc(p.shares ?? "")}" onchange="seBlankSet(${r.id},${i},'shares',this.value)"> Basis $ <input type="number" step="any" value="${esc(p.basis ?? "")}" onchange="seBlankSet(${r.id},${i},'basis',this.value)"></div>`).join("")}` +
    `${seEditSale ? "" : `<button class="btn" type="button" onclick="seAddBlankLot(${r.id})">＋ add lot</button>`}</div>`;
  if (!d.lots.length) return `<p class="muted">No open lots of ${esc(r.symbol)} in ${esc(accountDisplayLabel(r.account))} on that date. <a href="${esc(seActivityLink(r.account, r.symbol))}">Add the missing buy in Holdings › Activity</a></p>`;
  const price = seNum(r.shares) ? seNum(r.proceeds) / seNum(r.shares) : 0;
  const rows = d.lots.map((l) => {
    const p = r.picks.find((x) => x.txn_id === l.txn_id), sh = p ? seNum(p.shares) : 0;
    return `<tr><td><input type="checkbox" aria-label="Sell lot bought ${esc(l.purchase_date)}" ${p ? "checked" : ""} onchange="seTick(${r.id},${l.txn_id},this.checked)"></td><td>${esc(l.purchase_date)}</td><td class="rc-num">${seFmt(l.open_shares)}</td>` +
      `<td class="rc-num">${seMoney(l.unit_cost)}</td><td><input type="number" step="any" class="se-sell" value="${p ? seFmt(sh) : ""}" onchange="seSellShares(${r.id},${l.txn_id},this.value)"></td>` +
      `<td class="rc-num">${p ? seMoney(sh * l.unit_cost) : ""}</td><td class="rc-num">${p ? seMoney(sh * (price - l.unit_cost)) : ""}</td><td>${esc(l.term)}</td></tr>`;
  }).join("");
  const s = seRowState(seView(r));
  const fill = [["fifo", "FIFO"], ["hifo", "Highest cost"], ["losses", "Losses first"]].map(([m, t]) => `<button class="btn" type="button" onclick="seFillRow(${r.id},'${m}')">${t}</button>`).join(" ");
  return `<div class="se-chooser"><div>${fill} <button class="btn" type="button" onclick="seFillRow(${r.id},'clear')">Clear</button></div><table class="rc-table"><thead><tr><th></th><th>Bought</th><th class="rc-num">Open shares</th><th class="rc-num">Cost / share</th><th>Sell shares</th><th class="rc-num">Basis</th><th class="rc-num">Gain</th><th>Term</th></tr></thead>` +
    `<tbody>${rows}<tr><th colspan="2">Selected</th><td class="rc-num" colspan="2">${s.label}</td><td></td><td class="rc-num">${seMoney(s.basis)}</td><td class="rc-num">${s.gain === null ? "not taxable" : seMoney(s.gain)}</td><td>${esc(s.term)}</td></tr></tbody></table></div>`;
}
function seRowHtml(r, i) {
  const s = seRowState(seView(r)), d = seLots[seKey(r)];
  const inp = (f, type, extra = "") => `<td><input type="${type}" ${extra} value="${esc(r[f])}" aria-label="${f}" oninput="seSet(${r.id},'${f}',this.value)" onkeydown="seKeydown(event,${i},${SE_FIELDS.indexOf(f)})"></td>`;
  const opts = `<option value=""></option>` + seAccounts.map((a) => `<option value="${esc(a)}"${a === r.account ? " selected" : ""}>${esc(accountDisplayLabel(a))} (${seTax[seClasses[a]] || "taxable"})</option>`).join("");
  const near = d && s.gain !== null && s.gain < 0 && (d.nearby_buys || []).some((b) => !r.picks.some((p) => p.txn_id === b.txn_id));
  return `<tr><td><select aria-label="Account" onchange="seSet(${r.id},'account',this.value)" onkeydown="seKeydown(event,${i},0)">${opts}</select></td>${inp("symbol", "text")}${inp("date", "date")}${inp("shares", "number", 'step="any" min="0"')}${inp("proceeds", "number", 'step="any"')}${inp("fees", "number", 'step="any" min="0"')}` +
    `<td><button class="btn se-lots" type="button" aria-expanded="${seOpenId === r.id}" onclick="seToggle(${r.id})">${seOpenId === r.id ? "▾" : "▸"} ${esc(s.label)}</button></td>` +
    `<td class="rc-num">${s.gain === null ? (r.account && r.shares ? "not taxable" : "") : s.matched ? seMoney(s.gain) : "—"}${near ? ` <span class="sl-chip">wash?</span>` : ""}</td><td><button class="btn" type="button" aria-label="Remove row" onclick="seDel(${r.id})">✕</button></td></tr>` +
    (seOpenId === r.id ? `<tr><td colspan="9">${seChooserHtml(r, d)}</td></tr>` : "");
}
function seBodyHtml() {
  const n = seRows.length, ok = seCanSave(seRows.map(seView));
  const msg = seMsg ? `<p class="${seMsg.error ? "field-error" : "muted"}" role="status">${esc(seMsg.text)}</p>` : "";
  return `${msg}<table class="rc-table se-grid"><thead><tr><th>Account</th><th>Symbol</th><th>Sale date</th><th class="rc-num">Shares</th><th class="rc-num">Proceeds</th><th class="rc-num">Fees</th><th>Lots</th><th class="rc-num">Gain</th><th></th></tr></thead><tbody>${seRows.map(seRowHtml).join("")}</tbody></table>` +
    `<button class="btn" type="button" onclick="seAddRow()">＋ Add row</button> <button class="btn primary" id="seSave" type="button" ${ok ? "" : "disabled"} onclick="seSave()">${seEditSale ? "Save changes" : `Save ${n} sale${n === 1 ? "" : "s"}`}</button> <button class="btn" type="button" onclick="seClose()">Cancel</button>` +
    `<p class="muted">One row per sale. Gain is proceeds − fees − basis; IRA, Roth and HSA sales are not taxable, so no gain is reported.</p>`;
}
export const renderSalesEntry = () => `<div class="se-card" id="seCard">${seShown ? `<h3>${seEditSale ? "Edit sale" : "Record sales"}</h3><div id="seRoot">${seBodyHtml()}</div>` : `<button class="btn" type="button" onclick="seOpen()">＋ Record sales</button>`}</div>`;
const seRepaintCard = () => { const el = typeof document !== "undefined" && document.getElementById("seCard"); if (el) el.outerHTML = renderSalesEntry(); };
export function seOpen() { seShown = true; seEditSale = null; seMsg = null; if (!seRows.length) seRows = [seBlank()]; seRepaintCard(); }
export function seClose() { seShown = false; seEditSale = null; seRows = []; seOpenId = null; seRepaintCard(); }
export function seAddRow() { seRows.push(seBlank()); sePaint(); }
export function seDel(id) { seRows = seRows.filter((r) => r.id !== Number(id)); if (!seRows.length) seRows = [seBlank()]; sePaint(); }
export function seKeydown(e, ri, fi) { if (seKeyAction(seRows, ri, fi, e.key) === "add-row") { e.preventDefault(); seAddRow(); } }
export function seSet(id, f, v) {
  const r = seRow(id);
  if (!r) return;
  r[f] = v;
  if (f === "account" || f === "symbol" || f === "date") { r.picks = []; if (seOpenId === r.id) seLoadLots(r); }
  if (f === "account" || f === "shares") sePaint();
  else { const el = typeof document !== "undefined" && document.getElementById("seSave"); if (el) el.disabled = !seCanSave(seRows.map(seView)); }
}
export function seToggle(id) { const r = seRow(id); seOpenId = seOpenId === Number(id) ? null : Number(id); if (seOpenId && r) seLoadLots(r); sePaint(); }
async function seLoadLots(r) {
  if (!r.account || !r.symbol || !r.date) return;
  const key = seKey(r);
  if (!seLots[key]) {
    try { seLots[key] = await api(`/api/sales/open-lots?account=${encodeURIComponent(r.account)}&symbol=${encodeURIComponent(r.symbol)}&as_of=${encodeURIComponent(r.date)}`); }
    catch (e) { seLots[key] = { lots: [], log_started: false, nearby_buys: [] }; }
    if (!seLots[key].log_started && !r.picks.length) r.picks = [{ purchase_date: "", shares: "", basis: "" }];
    else if (seLots[key].lots.length && !r.picks.length && seNum(r.shares)) { // first look: tick lots by the import's lot method
      const m = window.biCurrentMethod ? window.biCurrentMethod() : "fifo";
      seFillRow(r.id, m === "lowest_gain" ? "losses" : m);
      return;
    }
  }
  sePaint();
}
export function seTick(id, txn, on) {
  const r = seRow(id), l = ((seLots[seKey(r)] || {}).lots || []).find((x) => x.txn_id === Number(txn));
  if (!r || !l) return;
  r.picks = r.picks.filter((p) => p.txn_id !== l.txn_id);
  if (on) r.picks.push({ txn_id: l.txn_id, purchase_date: l.purchase_date, shares: l.open_shares, unit_cost: l.unit_cost, term: l.term });
  sePaint();
}
export function seSellShares(id, txn, v) {
  const r = seRow(id), p = r && r.picks.find((x) => x.txn_id === Number(txn)), l = ((seLots[seKey(r)] || {}).lots || []).find((x) => x.txn_id === Number(txn));
  if (p && l) p.shares = Math.min(seNum(v), seNum(l.open_shares));
  if (r && !p && seNum(v) > 0) { seTick(id, txn, true); seSellShares(id, txn, v); return; }
  sePaint();
}
export function seFillRow(id, method) {
  const r = seRow(id), lots = ((seLots[seKey(r)] || {}).lots || []);
  if (!r) return;
  const got = method === "clear" ? {} : seFill(lots, r.shares, method, seNum(r.shares) ? seNum(r.proceeds) / seNum(r.shares) : 0);
  r.picks = lots.filter((l) => got[l.txn_id]).map((l) => ({ txn_id: l.txn_id, purchase_date: l.purchase_date, shares: got[l.txn_id], unit_cost: l.unit_cost, term: l.term }));
  sePaint();
}
export function seBlankSet(id, i, f, v) { const r = seRow(id); if (r && r.picks[i]) { r.picks[i][f] = v; r.picks[i].term = ""; } const el = typeof document !== "undefined" && document.getElementById("seSave"); if (el && r) el.disabled = !seCanSave(seRows.map(seView)); }
export function seAddBlankLot(id) { const r = seRow(id); if (r) { r.picks.push({ purchase_date: "", shares: "", basis: "" }); sePaint(); } }
export async function seSave() {
  if (!seCanSave(seRows.map(seView))) return;
  try {
    if (seEditSale) {
      const b = seBatchRows(seRows)[0];
      await api(`/api/sales/${Number(seEditSale.sale_id)}/replace`, { method: "POST", body: JSON.stringify({ ...b, tax_class: seEditSale.tax_class }) });
    } else await api("/api/sales/batch", { method: "POST", body: JSON.stringify({ rows: seBatchRows(seRows) }) });
  } catch (e) { seMsg = { text: e.message, error: true }; sePaint(); return; }
  const n = seRows.length; seClose(); seLots = {};
  if (window.slAfterEntry) window.slAfterEntry(seEditSale ? "Sale updated; the old row is kept as voided." : `Recorded ${n} sale${n === 1 ? "" : "s"}.`);
}
// Edit one lot row of a hand-entered sale in the same grid (the old row is voided on save).
export function seEdit(sale) {
  seShown = true; seEditSale = sale; seMsg = null; seOpenId = null;
  seRows = [{ id: seNext++, account: sale.account, symbol: sale.symbol, date: sale.sale_date, shares: sale.shares, proceeds: sale.proceeds, fees: sale.fees,
    picks: [{ purchase_date: sale.purchase_date || "", shares: sale.shares, basis: sale.basis, term: sale.holding_period === "long" ? "long" : "short" }] }];
  seLots[seKey(seRows[0])] = { lots: [], log_started: false, nearby_buys: [] };
  seOpenId = seRows[0].id;
  seRepaintCard();
}
Object.assign(window, { seFill, seRowState, seCanSave, seKeyAction, seBatchRows, seChooserHtml, renderSalesEntry, seSetAccounts, seOpen, seClose, seAddRow, seDel, seKeydown, seSet, seToggle, seTick, seSellShares, seFillRow, seBlankSet, seAddBlankLot, seSave, seEdit, seActivityLink });