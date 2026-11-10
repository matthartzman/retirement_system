// Investment Holdings, grouped view (ticket 374): the plan's lots as a collapsible tree like the Trends Snapshot.
// The levels (Asset class, Sub-class, Symbol, Account, then always Lot) can be added, removed and reordered with the
// chips above the tree; the choice is remembered in this browser. Read-only: lots are edited in the flat table below.
// Pure helpers are exported for tests; the render/handlers are bare globals like the other holdings modules.
export const HT_DIMENSIONS = { class: "Asset class", subclass: "Sub-class", symbol: "Symbol", account: "Account", lot: "Lot" };
export const HT_DEFAULT_ORDER = ["class", "symbol", "account", "lot"];
const HT_KEY = "holdingsTreeGroups_v1";
export function htNormalizeOrder(raw) {
  if (!Array.isArray(raw)) return [...HT_DEFAULT_ORDER];
  const levels = [];
  for (const d of raw) if (Object.hasOwn(HT_DIMENSIONS, d) && d !== "lot" && !levels.includes(d)) levels.push(d);
  return [...levels, "lot"];
}
export function htToggleDimension(order, dim) {
  if (dim === "lot" || !Object.hasOwn(HT_DIMENSIONS, dim)) return htNormalizeOrder(order);
  const levels = htNormalizeOrder(order).filter((d) => d !== "lot");
  return [...(levels.includes(dim) ? levels.filter((d) => d !== dim) : [...levels, dim]), "lot"];
}
export function htStepDimension(order, dim, delta) {
  const levels = htNormalizeOrder(order).filter((d) => d !== "lot");
  const at = levels.indexOf(dim), to = at + delta;
  if (at < 0 || to < 0 || to >= levels.length) return htNormalizeOrder(order);
  levels.splice(at, 1);
  levels.splice(to, 0, dim);
  return [...levels, "lot"];
}
const isCash = (sym) => String(sym || "").toUpperCase().startsWith("CASH");
const isTBill = (sym) => String(sym || "").toUpperCase().startsWith("CASH (T-BILL");
function htLabel(lot, dim) {
  switch (dim) {
    case "class": return lot.asset_class || "Other";
    case "subclass": return lot.subclass || lot.asset_class || "Other";
    case "symbol": return lot.symbol || "(no symbol)";
    case "account": return lot.account || "(no account)";
    default: return lot.purchase_date || "Undated";
  }
}
function htTotals(members) {
  let shares = 0, basis = 0, value = 0, unpriced = 0;
  for (const m of members) { shares += m.shares; basis += m.basis; value += m.value; if (m.estimate) unpriced += 1; }
  return { shares, basis, value, gain: value - basis, unpriced, unitCost: shares ? basis / shares : 0 };
}
// lots: [{account, symbol, purchase_date, shares, basis, value, asset_class, subclass}]. Returns {nodes, total}.
// A node is {dim, name, label, path, row, members, children, lot?}. A level that would only repeat its parent's name
// (one child, same label) is skipped, as in the Snapshot.
export function htBuildTree(lots, order, labelOf = (id) => id) {
  const dims = htNormalizeOrder(order);
  const total = htTotals(lots);
  const grow = (members, level, parent) => {
    const dim = dims[level];
    const groups = new Map();
    members.forEach((m, i) => {
      const key = dim === "lot" ? String(i) : htLabel(m, dim);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(m);
    });
    const nodes = [...groups].map(([key, ms]) => {
      const name = dim === "lot" ? htLabel(ms[0], "lot") : key;
      const node = { dim, name, label: dim === "account" ? labelOf(name) : name, path: `${parent || ""}/${encodeURIComponent(key)}`,
        row: htTotals(ms), members: ms, children: [], title: dim === "symbol" ? (ms[0].title || "") : "" };
      if (dim === "lot") { node.lot = ms[0]; return node; }
      let next = level + 1;
      while (dims[next] !== "lot" && ms.every((m) => htLabel(m, dims[next]) === htLabel(ms[0], dims[next]))
             && String(htLabel(ms[0], dims[next])).toLowerCase() === String(name).toLowerCase()) next += 1;
      node.children = dims[next] === "lot" && ms.length === 1 && isCash(ms[0].symbol) ? [] : grow(ms, next, node.path);
      return node;
    });
    return dim === "lot"
      ? nodes.sort((a, b) => String(b.lot.purchase_date || "").localeCompare(String(a.lot.purchase_date || "")))
      : nodes.sort((a, b) => String(a.label).localeCompare(String(b.label), undefined, { sensitivity: "base" }));
  };
  return { nodes: grow(lots, 0, null), total };
}
// ---- page glue ----
window.holdingsTreeOrder = window.holdingsTreeOrder || null;
window.holdingsTreeOpen = window.holdingsTreeOpen || new Set();
window.holdingsClassData = window.holdingsClassData === undefined ? null : window.holdingsClassData;
function htOrder() {
  if (!window.holdingsTreeOrder) {
    try { window.holdingsTreeOrder = htNormalizeOrder(JSON.parse(window.localStorage.getItem(HT_KEY))); } catch (e) { window.holdingsTreeOrder = [...HT_DEFAULT_ORDER]; }
  }
  return window.holdingsTreeOrder;
}
function htSetOrder(order) {
  window.holdingsTreeOrder = order;
  try { window.localStorage.setItem(HT_KEY, JSON.stringify(order.filter((d) => d !== "lot"))); } catch (e) { /* storage blocked: choice won't persist */ }
  renderMain();
}
export function toggleHoldingsTreeDim(dim) { htSetOrder(htToggleDimension(htOrder(), dim)); }
export function stepHoldingsTreeDim(dim, delta) { htSetOrder(htStepDimension(htOrder(), dim, delta)); }
export function toggleHoldingsTreeNode(path) {
  const open = window.holdingsTreeOpen;
  if (open.has(path)) open.delete(path); else open.add(path);
  renderMain();
}
export function setHoldingsTreeAll(open, paths) {
  window.holdingsTreeOpen = new Set(open ? paths : []);
  renderMain();
}
export async function loadHoldingsClasses() {
  if (window.holdingsClassData) return;
  window.holdingsClassData = {};
  try {
    const out = await api("/api/holdings/classes");
    window.holdingsClassData = (out && out.classes) || {};
  } catch (e) { /* no classes: Asset class groups fall under "Other" */ }
  if (window.activeStep === "holdings") renderMain();
}
function htLots(rows) {
  const classes = window.holdingsClassData || {};
  return rows.filter((r) => String(r.symbol || "").trim()).map((r) => {
    const sym = String(r.symbol).trim().toUpperCase();
    const shares = Number(r.shares || 0) || 0;
    const cls = classes[sym] || {};
    return { account: String(r.account || "").trim(), symbol: sym, purchase_date: String(r.purchase_date || "").trim(), shares,
      basis: shares * (Number(r.purchase_price || 0) || 0), value: holdingLotCurrentValue(r).value, estimate: holdingLotCurrentValue(r).isEstimate,
      asset_class: isCash(sym) && !isTBill(sym) ? "Cash" : cls.asset_class, subclass: cls.subclass, title: cls.name || "" };
  });
}
const htMoney = (n) => (typeof currencyDisplay === "function" ? currencyDisplay(String(Math.round(n * 100) / 100), 0) : String(Math.round(n)));
const htUnit = (n) => (Number.isFinite(n) && n ? "$" + n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 }) : "");
const htShares = (n) => (Math.round(n * 10000) / 10000).toLocaleString();
// No price for a lot yet (prices come from the last build): value falls back to cost, so a gain would read as $0.
function htGainCell(gain, unpriced) {
  return unpriced ? '<td class="ht-num" title="No price yet for some lots: build the plan to price them">—</td>' : `<td class="ht-num ${gain < 0 ? "neg" : "pos"}">${esc(htMoney(gain))}</td>`;
}
// Lot-row cross-links to Holdings > Activity: a managed account's lots are edited there, and an undated lot came from the log's backfill.
function htLotLinks(l) {
  if (!window.hsActivityLink || !l.account) return "";
  const a = (f, text) => ` <a class="ht-link" href="${esc(window.hsActivityLink({ account: l.account, symbol: l.symbol, ...f }))}">${text}</a>`;
  const managed = window.isManagedHoldingAccount && window.isManagedHoldingAccount(l.account);
  const w = window.tlWashFor && l.shares ? window.tlWashFor(l.account, l.symbol, l.purchase_date, l.basis / l.shares) : null;
  const mark = w ? ` <a class="sl-chip" href="#sales_ledger?tab=fix&amp;sec=wash" onclick="if(window.slGo){slGo('fix','wash');return false}" title="Includes $${esc(w.wash_adjustment.toFixed(2))} of a disallowed wash-sale loss; the holding period counts from ${esc(w.tacked_date)}">incl. $${esc(w.wash_adjustment.toFixed(2))} wash</a>` : "";
  return mark + (managed && !l.purchase_date ? ` <span class="sl-chip">date not on file</span>${a({ type: "opening", source: "backfill" }, "Fix date")}` : "") + a({}, "History") + (managed ? a({}, "Edit in Activity") : "");
}
function htRows(nodes, depth, total, out) {
  for (const n of nodes) {
    const open = window.holdingsTreeOpen.has(n.path), has = n.children.length > 0;
    const gain = n.row.gain, share = total.value ? (n.row.value / total.value) * 100 : 0;
    const lot = n.dim === "lot";
    out.push(`<tr class="ht-row ht-${n.dim}" data-depth="${depth}"><td style="padding-left:${depth * 18 + 6}px">`
      + (has ? `<button type="button" class="ht-twisty" aria-expanded="${open}" onclick="toggleHoldingsTreeNode('${esc(n.path.replace(/'/g, "\\'"))}')">${open ? "▾" : "▸"}</button> ` : '<span class="ht-twisty-gap"></span>')
      + `<span title="${esc(HT_DIMENSIONS[n.dim])}">${esc(n.label)}</span>${n.title ? ` <span class="muted ticker-title">${esc(n.title)}</span>` : ""}${lot ? htLotLinks(n.lot) : ""}</td>`
      + `<td class="ht-num">${esc(htShares(n.row.shares))}</td><td class="ht-num">${esc(htUnit(n.row.unitCost))}</td><td class="ht-num">${esc(htMoney(n.row.basis))}</td>`
      + `<td class="ht-num">${esc(htMoney(n.row.value))}</td>${htGainCell(gain, n.row.unpriced)}`
      + `<td class="ht-num">${lot ? "" : esc(share.toFixed(1) + "%")}</td></tr>`);
    if (has && open) htRows(n.children, depth + 1, total, out);
  }
  return out;
}
function htPaths(nodes, acc = []) {
  for (const n of nodes) if (n.children.length) { acc.push(n.path); htPaths(n.children, acc); }
  return acc;
}
// "as of <date>" under the Current value header: the oldest price date among the priced symbols (the last build's quotes).
function htAsOf() {
  const d = String(window.holdingsPriceAsOf || "").slice(0, 10);
  return d ? ` <span class="muted ht-asof">as of ${esc(d)}</span>` : "";
}
export function renderHoldingsTree(rows, labelOf) {
  if (window.holdingsClassData === null) setTimeout(loadHoldingsClasses, 0);
  if (!window.holdingsPriceData && !window.holdingsPriceLoading && typeof loadHoldingsPriceData === "function") setTimeout(loadHoldingsPriceData, 0);
  const order = htOrder(), levels = order.filter((d) => d !== "lot");
  const unused = Object.keys(HT_DIMENSIONS).filter((d) => d !== "lot" && !levels.includes(d));
  const tree = htBuildTree(htLots(rows), order, labelOf);
  const chips = levels.map((d, i) => `<span class="chip"><button type="button" ${i === 0 ? "disabled" : ""} aria-label="Move ${esc(HT_DIMENSIONS[d])} earlier" onclick="stepHoldingsTreeDim('${d}',-1)">◂</button>`
    + `<span>${esc(HT_DIMENSIONS[d])}</span><button type="button" ${i === levels.length - 1 ? "disabled" : ""} aria-label="Move ${esc(HT_DIMENSIONS[d])} later" onclick="stepHoldingsTreeDim('${d}',1)">▸</button>`
    + `<button type="button" aria-label="Stop grouping by ${esc(HT_DIMENSIONS[d])}" onclick="toggleHoldingsTreeDim('${d}')">×</button></span>`).join("")
    + `<span class="chip fixed" title="Lots are always the last level">Lot</span>`
    + unused.map((d) => `<button type="button" class="chip off" aria-label="Also group by ${esc(HT_DIMENSIONS[d])}" onclick="toggleHoldingsTreeDim('${d}')">+ ${esc(HT_DIMENSIONS[d])}</button>`).join("");
  const paths = JSON.stringify(htPaths(tree.nodes)).replace(/"/g, "&quot;");
  const body = htRows(tree.nodes, 0, tree.total, []).join("");
  return `<div class="holdings" data-help-section="holdings.plan_holdings"><h3 class="group-title">Plan Holdings</h3>`
    + `<div class="group-by"><span class="group-by-label">Group by</span>${chips}`
    + `<button class="btn" type="button" onclick="setHoldingsTreeAll(true, ${paths})">Expand all</button><button class="btn" type="button" onclick="setHoldingsTreeAll(false, [])">Collapse all</button></div>`
    + `<div class="lot-table-wrap pinned-col"><table class="lot-table ht-table"><thead><tr><th>Name</th><th>Shares</th><th>Unit cost</th><th>Cost basis</th><th>Current value${htAsOf()}</th><th>Gain</th><th>Share</th></tr></thead><tbody>`
    + (body || `<tr><td colspan="7" class="muted">No holdings yet.</td></tr>`)
    + `<tr class="ht-total"><td><b>Total</b></td><td class="ht-num">${esc(htShares(tree.total.shares))}</td><td class="ht-num"></td><td class="ht-num">${esc(htMoney(tree.total.basis))}</td><td class="ht-num">${esc(htMoney(tree.total.value))}</td>${htGainCell(tree.total.gain, tree.total.unpriced)}<td class="ht-num">100.0%</td></tr>`
    + `</tbody></table></div></div>`;
}
Object.assign(window, { renderHoldingsTree, toggleHoldingsTreeDim, stepHoldingsTreeDim, toggleHoldingsTreeNode, setHoldingsTreeAll, loadHoldingsClasses });