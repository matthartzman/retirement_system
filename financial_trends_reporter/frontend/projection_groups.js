// Recent Projections: the column groups for the Net Worth and Cash Flow tables
// (design: documentation/future/superpowers/plans/2026-10-29-trends-recent-projections-design.md §4).
// Keys are the workbook builders' semantic column keys (projection_tables.json), never owner names.
// A collapsed group shows only its subtotal; an open one keeps its subtotal first and opens to the right.
// Pure: no DOM.

const sum = (vals) => {
  const nums = vals.filter((v) => typeof v === "number" && Number.isFinite(v));
  return nums.length ? nums.reduce((a, b) => a + b, 0) : null;
};
const pick = (row, keys) => keys.map((k) => row.values[k]);

// Other_Liab (negative; the sheet's Loans & Other Liabilities column) and CST (no sheet column,
// projection_tables.add_unshown_nw_lines) are inside TOTAL NW; each present only when non-zero.
const num = (v) => (typeof v === "number" ? v : 0);
const investable = (row) => sum(pick(row, ["Σ PreTax", "Σ Roth", "Σ Trust", "HSA_1", "Cash", "CST"]));
const homeOther = (row) => {
  const other = row.values["Σ Other"];
  if (typeof other !== "number") return null;
  return other - num(row.values.Cash) + num(row.values.Other_Liab);
};
const delta = (row) => {
  const now = row.values["TOTAL NW"];
  const before = row.prev ? row.prev["TOTAL NW"] : null;
  return typeof now === "number" && typeof before === "number" ? now - before : null;
};
const ira = (row) => sum(pick(row, ["H_IRA_RMD", "H_IRA_Elec", "W_IRA_RMD", "W_IRA_Elec"]));

// node: {id, label, subtotal: key | (row) => number|null, children: [node | key | RegExp], context?: [key], stock?: true,
//        rule?: true (the table's total: a heavier rule on its left)}
export const GROUPS = {
  nw: [
    { id: "investable", label: "Investable", subtotal: investable, children: [
      { id: "pretax", label: "Pre-Tax", subtotal: "Σ PreTax", children: [/^PreTax_\d+$/] },
      { id: "roth", label: "Roth", subtotal: "Σ Roth", children: [/^Roth_\d+$/] },
      { id: "trusts", label: "Trusts", subtotal: "Σ Trust", children: [/^Trust_\d+$/] },
      "HSA_1", "Cash", "CST",
    ] },
    { id: "annuities", label: "Annuities & Pension", subtotal: "Σ Ann",
      children: ["Pension PV", "W Single PV", "W Joint PV", "H Single PV", "H Joint PV"] },
    { id: "homeother", label: "Home & Other", subtotal: homeOther,
      children: ["Home Equity", "Next Housing Equity", "Rental Equity", "Startup", "Autos", "Note", "Other_Liab"] },
    { id: "total", label: "Total NW", subtotal: "TOTAL NW", children: [], stock: true, rule: true },
    { id: "delta", label: "Δ vs prior", subtotal: delta, children: [], stock: true },
  ],
  cf: [
    { id: "income", label: "Income", subtotal: "Σ_Inc",
      children: ["Earned", "H_SS", "W_SS", "Pension", "W_Sgl", "W_Jnt", "H_Sgl", "H_Jnt", "Note", "RMD", "Rental"] },
    { id: "taxes", label: "Taxes", subtotal: "Total_Tax",
      children: ["Fed", "State", "NIIT", "IRMAA", "Payroll", "LTCG", "Rental_Tax"], context: ["AGI", "Taxable"] },
    { id: "spending", label: "Spending", subtotal: "Σ_Spend", children: [
      "Spend_Base",
      { id: "housing", label: "Housing", subtotal: "Housing",
        children: ["Mort_PI", "Prop_Tax", "Housing_Utilities", "Home_Imp", "Housing_Maintenance", "Housing_Other", "Rent_Det"] },
      { id: "wellness", label: "Wellness", subtotal: "Wellness",
        children: ["Wellness_Premiums", "Wellness_Medical", "Wellness_Dental", "Wellness_Vision", "Wellness_Rx_Otc", "Wellness_Other", "HC_LTC"] },
      "Travel", "Other", "Business_Exp", "HELOC_PAI",
    ] },
    { id: "need", label: "Cash Need", subtotal: "Total_Cash_Need",
      children: ["Other_Cash_Need", "Income_Funding", "Other_Funding", "Cash_Bridge_Gap", "HELOC_Draw"], context: ["HELOC_Bal"] },
    { id: "draws", label: "Portfolio Draws", subtotal: "Σ_WD", children: [
      { id: "trust", label: "Trust", subtotal: "Σ_Trust", children: ["H_Trust_WD", "W_Trust_WD"] },
      "HSA_WD",
      { id: "rothwd", label: "Roth", subtotal: "Σ_Roth", children: ["H_Roth_WD", "W_Roth_WD"] },
      { id: "ira", label: "IRA", subtotal: ira, children: ["H_IRA_RMD", "H_IRA_Elec", "W_IRA_RMD", "W_IRA_Elec"] },
    ], context: ["Req_Portfolio_Draws"] },
    { id: "conv", label: "Roth Conv", subtotal: "Roth_Conv", children: ["H_IRA_Conv", "W_IRA_Conv"] },
    { id: "networth", label: "Net Worth", subtotal: "NW_Check", children: [], stock: true, rule: true },
  ],
};

// Keys the tables carry that no column shows on purpose (used only inside a computed subtotal, or
// the sum of columns shown elsewhere: an IRA Outflow is RMD + Elective + Conv).
const DROPPED = { nw: ["Σ Other"], cf: ["H_IRA_Tot", "W_IRA_Tot"] };

const valueOf = (subtotal) => (typeof subtotal === "function" ? subtotal : (row) => {
  const v = row.values[subtotal];
  return typeof v === "number" ? v : null;
});

// Resolve one config node against the table's columns: prune what isn't there, expand patterns.
function resolve(node, have, labelOf, used) {
  if (typeof node.subtotal === "string") used.add(node.subtotal);
  const children = [];
  for (const child of node.children) {
    if (typeof child === "string") {
      if (have.has(child)) { used.add(child); children.push({ key: child, label: labelOf(child) }); }
    } else if (child instanceof RegExp) {
      for (const key of have) if (child.test(key)) { used.add(key); children.push({ key, label: labelOf(key) }); }
    } else {
      const sub = resolve(child, have, labelOf, used);
      if (sub) children.push(sub);
    }
  }
  const context = (node.context || []).filter((k) => have.has(k));
  context.forEach((k) => used.add(k));
  const hasSubtotal = typeof node.subtotal === "function" || have.has(node.subtotal);
  if (!hasSubtotal && !children.length) return null;
  return { id: node.id, label: node.label, value: valueOf(node.subtotal), stock: !!node.stock, rule: !!node.rule,
    children, context: context.map((key) => ({ key, label: labelOf(key) })) };
}

const memberKeys = (node) => [
  ...(typeof node.subtotal === "string" ? [node.subtotal] : []),
  ...node.children.flatMap((c) => (c.key ? [c.key] : memberKeys(c))),
  ...node.context.map((c) => c.key),
];

export function buildTree(table, which) {
  const columns = table.columns || [];
  const have = new Set(columns.map((c) => c.key));
  const byKey = new Map(columns.map((c) => [c.key, c]));
  const labelOf = (key) => (byKey.get(key) || {}).label || key;
  const used = new Set(DROPPED[which] || []);
  const nodes = (GROUPS[which] || []).map((n) => resolve(n, have, labelOf, used)).filter(Boolean);

  // A key the config doesn't know goes under the group holding most of its workbook banner's
  // columns (not one that borrows a single key, as Investable borrows Cash from OTHER ASSETS), so a
  // new column is still reachable (a test flags it for a deliberate home).
  const unmapped = columns.map((c) => c.key).filter((k) => !used.has(k));
  const counts = new Map();   // banner -> Map(node -> member count)
  for (const node of nodes) for (const key of memberKeys(node)) {
    const banner = (byKey.get(key) || {}).banner;
    if (!banner) continue;
    if (!counts.has(banner)) counts.set(banner, new Map());
    const per = counts.get(banner);
    per.set(node, (per.get(node) || 0) + 1);
  }
  const groupOf = new Map([...counts].map(([banner, per]) => [banner, [...per].sort((a, b) => b[1] - a[1])[0][0]]));
  const fallback = [...nodes].reverse().find((n) => n.children.length) || nodes[0];
  for (const key of unmapped) {
    const target = groupOf.get((byKey.get(key) || {}).banner) || fallback;
    if (target) target.children.push({ key, label: labelOf(key) });
  }

  const rows = (table.rows || []).map((r, i, all) => ({ ...r, prev: i ? all[i - 1].values : null }));
  return { which, nodes, unmapped, rows };
}

// edge.left / edge.right: 2 = an open top-level group's outer rule, 1 = an open nested group's lighter
// rule, 0 = none. A nested group's edge that is also its parent's keeps the heavier rule.
function columnsOf(node, open, depth, out) {
  const expandable = node.children.length > 0 || node.context.length > 0;
  const start = out.length;
  out.push({ id: node.id, label: node.label, depth, kind: "subtotal", value: node.value, groupId: node.id,
    expandable, open: expandable && open.has(node.id), stock: node.stock, totalRule: node.rule, edge: { left: 0, right: 0 } });
  if (!expandable || !open.has(node.id)) return;
  const leaf = (c, kind, stock) => ({ id: c.key, label: c.label, depth: depth + 1, kind, value: valueOf(c.key),
    groupId: node.id, expandable: false, open: false, stock, totalRule: false, edge: { left: 0, right: 0 } });
  for (const child of node.children) {
    if (child.key) out.push(leaf(child, "detail", false));
    else columnsOf(child, open, depth + 1, out);
  }
  for (const c of node.context) out.push(leaf(c, "context", true));
  const level = depth === 0 ? 2 : 1;
  out[start].edge.left = Math.max(out[start].edge.left, level);
  out[out.length - 1].edge.right = Math.max(out[out.length - 1].edge.right, level);
}

export function visibleColumns(tree, open) {
  const out = [];
  for (const node of tree.nodes) columnsOf(node, open, 0, out);
  return out;
}

// Every group id of a tree (Expand all).
export function allGroupIds(tree) {
  const ids = [];
  const walk = (n) => { if (n.children.length || n.context.length) ids.push(n.id); n.children.forEach((c) => c.key || walk(c)); };
  tree.nodes.forEach(walk);
  return ids;
}

export function clampYears(v) {
  const n = typeof v === "number" ? v : (String(v ?? "").trim() === "" ? NaN : Number(v));
  if (!Number.isFinite(n)) return 5;
  return Math.min(30, Math.max(1, Math.round(n)));
}

// The rows from startYear for count years, clamped to the plan's own years; never empty when the
// plan has rows. endsAt is the plan's last year when the window runs past it, else null.
export function windowRows(rows, startYear, count) {
  if (!rows.length) return { rows: [], endsAt: null };
  const last = rows[rows.length - 1].year;
  let from = rows.findIndex((r) => r.year >= startYear);
  if (from < 0) from = Math.max(0, rows.length - count);
  const picked = rows.slice(from, from + count);
  return { rows: picked, endsAt: startYear + count - 1 > last ? last : null };
}

// Cash Flow's window total: flows add across years; balances and context columns don't (null).
export function windowTotal(rows, cols) {
  const out = {};
  for (const c of cols) out[c.id] = c.stock ? null : sum(rows.map((r) => c.value(r)));
  return out;
}

// How far reconcileNW may drift before the page says so: a cent in dollars. A percent-only viewer's data
// is already divided by today's net worth on the server, where a cent would hide a mismatch of 1% of it.
export function reconcileTolerance(allowed) {
  return allowed === "percent" ? 1e-7 : 0.01;
}

// (Investable + Annuities & Pension + Home & Other) - Total NW; ~0 when the regrouping is complete.
export function reconcileNW(row) {
  return (investable(row) || 0) + (row.values["Σ Ann"] || 0) + (homeOther(row) || 0) - (row.values["TOTAL NW"] || 0);
}
