// Sales Ledger: group ledger rows (one per lot) into sales (pure, no DOM). Key = account|symbol|sale_date, shared with wash reviews.
export const slSaleKey = (r) => `${r.account}|${r.symbol}|${r.sale_date}`;

export function slGroupSales(rows) {
  const out = new Map();
  for (const r of rows || []) {
    const key = slSaleKey(r);
    let g = out.get(key);
    if (!g) { g = { key, account: r.account, symbol: r.symbol, sale_date: r.sale_date, shares: 0, proceeds: 0, basis: 0, gain: null, term: "", lots: [], wash: false }; out.set(key, g); }
    g.lots.push(r);
    g.shares += Number(r.shares) || 0;
    g.proceeds += Number(r.proceeds) || 0;
    g.basis += Number(r.basis) || 0;
    if (r.gain != null) g.gain = (g.gain || 0) + Number(r.gain);
    g.term = g.term === "" || g.term === r.holding_period ? r.holding_period : "Mixed";
    if (r.wash_flag && r.wash_flag !== "none") g.wash = true;
  }
  return [...out.values()].sort((a, b) => (a.sale_date < b.sale_date ? 1 : a.sale_date > b.sale_date ? -1 : a.key < b.key ? -1 : 1));
}

Object.assign(window, { slSaleKey, slGroupSales });
