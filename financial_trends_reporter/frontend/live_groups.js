// Live Snapshot Group By: groups the flat lot list (liquid.positions) by the levels the user picked, in
// the order they picked, and totals every group with the same formulas as live_snapshot.py's
// _summarize (a contract test runs this file against the server's own groups). Pure: no DOM.

export const DIMENSIONS = { subclass: "Sub-class", class: "Asset class", symbol: "Symbol", account: "Account", lot: "Lot" };
export const DEFAULT_ORDER = ["subclass", "symbol", "account", "lot"];
export const GROUPS_KEY = "trendsLiveGroups_v1";

const CLASS_ORDER = ["Equity", "Fixed Income", "Commodities", "Cash", "Other"];
export const ANNUALIZE_MIN_DAYS = 90;   // live_snapshot.py ANNUALIZE_MIN_DAYS (a contract test compares them)

export const isCashSymbol = (symbol) => String(symbol || "").toUpperCase().startsWith("CASH");

// ---- the order of levels: always ends with "lot", which cannot move or be removed ----

export function normalizeOrder(raw) {
  if (!Array.isArray(raw)) return [...DEFAULT_ORDER];
  const levels = [];
  for (const d of raw) if (Object.hasOwn(DIMENSIONS, d) && d !== "lot" && !levels.includes(d)) levels.push(d);
  return [...levels, "lot"];
}

export function parseSavedOrder(raw) {
  try { return normalizeOrder(JSON.parse(raw)); } catch (err) { return [...DEFAULT_ORDER]; }
}

const levelsOf = (order) => normalizeOrder(order).filter((d) => d !== "lot");

export function moveDimension(order, dim, toIndex) {
  const levels = levelsOf(order);
  if (dim === "lot" || !levels.includes(dim)) return normalizeOrder(order);
  const rest = levels.filter((d) => d !== dim);
  rest.splice(Math.max(0, Math.min(toIndex, rest.length)), 0, dim);
  return [...rest, "lot"];
}

export function stepDimension(order, dim, delta) {
  const levels = levelsOf(order), at = levels.indexOf(dim), to = at + delta;
  if (at < 0 || to < 0 || to >= levels.length) return normalizeOrder(order);
  return moveDimension(order, dim, to);
}

export function toggleDimension(order, dim) {
  if (dim === "lot" || !Object.hasOwn(DIMENSIONS, dim)) return normalizeOrder(order);
  const levels = levelsOf(order);
  return [...(levels.includes(dim) ? levels.filter((d) => d !== dim) : [...levels, dim]), "lot"];
}

// Drop ``dragged`` before or after ``target``. A chip that isn't in the order yet is added there; dropping
// on or after Lot means "last of the others".
export function dropOrder(order, dragged, target, after) {
  if (dragged === "lot" || !Object.hasOwn(DIMENSIONS, dragged) || dragged === target) return normalizeOrder(order);
  const rest = levelsOf(order).filter((d) => d !== dragged);
  const at = target === "lot" ? rest.length : rest.indexOf(target) + (after ? 1 : 0);
  rest.splice(at < 0 ? rest.length : at, 0, dragged);
  return [...rest, "lot"];
}

// ---- totals ----

const ratio = (numerator, denominator) => (numerator === null || numerator === undefined || !denominator ? null : numerator / denominator);

function annualized(returnPct, days) {
  if (returnPct === null || !(days >= ANNUALIZE_MIN_DAYS) || returnPct <= -1) return null;   // also no days: null
  return (1 + returnPct) ** (365 / days) - 1;
}

// One row's figures from its lots. ``totals`` = {current, gain} of the whole liquid book (for Share and
// Share of gain); ``days`` since the start date (for Annualized).
export function aggregate(members, totals, days) {
  let current = 0, start = 0, newMoney = 0, weighted = 0, day = 0, known = false;
  for (const m of members) {
    current += m.current; start += m.start; newMoney += m.new_money; weighted += m.weighted;
    if (m.day !== null && m.day !== undefined) { day += m.day; known = true; }
  }
  const gain = current - start - newMoney;
  const returnPct = ratio(gain, start + weighted);
  return {
    start, new_money: newMoney, current, share: ratio(current, totals.current),
    day: known ? day : null, day_pct: known ? ratio(day, current - day) : null,
    market_gain: gain, return_pct: returnPct, share_of_gain: ratio(gain, totals.gain), annualized_pct: annualized(returnPct, days),
  };
}

// ---- the tree ----

export function groupLabel(position, dim) {
  switch (dim) {
    case "subclass": return position.subclass || position.asset_class || "Other";
    case "class": return position.asset_class || "Other";
    case "symbol": return position.symbol;
    case "account": return position.account;
    default: return position.purchase_date || "Undated";
  }
}

const byName = (a, b) => String(a.name).localeCompare(String(b.name));
const byValue = (a, b) => b.row.current - a.row.current || byName(a, b);
const newestFirst = (a, b) => {
  const x = a.lot.purchase_date || "", y = b.lot.purchase_date || "";
  return x === y ? 0 : !x ? 1 : !y ? -1 : y.localeCompare(x);
};

function sortNodes(nodes, dim) {
  if (dim === "class") {
    const rank = (n) => { const i = CLASS_ORDER.indexOf(n.name); return i < 0 ? CLASS_ORDER.length : i; };
    return nodes.sort((a, b) => rank(a) - rank(b) || byName(a, b));
  }
  if (dim === "lot") return nodes.sort(newestFirst);
  // Accounts holding only cash read A to Z by the name shown; everything else, largest first.
  if (dim === "account" && nodes.every((n) => n.members.every((m) => isCashSymbol(m.symbol)))) {
    return nodes.sort((a, b) => a.label.localeCompare(b.label, undefined, { sensitivity: "base" }) || byName(a, b));
  }
  return nodes.sort(byValue);
}

// Returns {nodes, total}. A node is {dim, name, label, title, path, parent, row, members, children, lot?, inline?, skipped?}.
// ``labelOf`` turns an account id into the name shown. ``inline`` is a single cash lot's date, shown on its
// own row's line instead of as a child row. ``skipped`` lists the levels left out below a row because they
// would only repeat it: one child with the same name (e.g. sub-class Cash under asset class Cash).
export function buildTree(positions, order, { days, labelOf = (id) => id }) {
  const dims = normalizeOrder(order);
  const current = positions.reduce((s, p) => s + p.current, 0);
  const gain = positions.reduce((s, p) => s + p.current - p.start - p.new_money, 0);
  const totals = { current, gain };

  // True when every member falls in one group at ``dim`` and it has the parent's name (ignoring case).
  const repeats = (ms, dim, name) => {
    const key = groupLabel(ms[0], dim);
    return String(key).toLowerCase() === String(name).toLowerCase() && ms.every((m) => groupLabel(m, dim) === key);
  };

  const grow = (members, level, parent) => {
    const dim = dims[level];
    const groups = new Map();
    members.forEach((m, i) => {
      const key = dim === "lot" ? String(i) : groupLabel(m, dim);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(m);
    });
    const nodes = [...groups].map(([key, ms]) => {
      const name = dim === "lot" ? groupLabel(ms[0], "lot") : key;
      const node = {
        dim, name, label: dim === "account" ? labelOf(name) : name, title: dim === "symbol" ? (ms[0].title || "") : "",
        path: `${parent || ""}/${encodeURIComponent(key)}`, parent: parent || null,
        row: aggregate(ms, totals, days), members: ms, children: [],
      };
      if (dim === "lot") { node.lot = ms[0]; return node; }
      let next = level + 1;
      while (dims[next] !== "lot" && repeats(ms, dims[next], key)) next += 1;
      if (next > level + 1) node.skipped = dims.slice(level + 1, next);
      if (dims[next] === "lot" && ms.length === 1 && isCashSymbol(ms[0].symbol)) node.inline = ms[0].purchase_date || "Undated";
      else node.children = grow(ms, next, node.path);
      return node;
    });
    return sortNodes(nodes, dim);
  };

  return { nodes: grow(positions, 0, null), total: { ...aggregate(positions, totals, days), share: 1, share_of_gain: 1 } };
}
