// Ticket 374: the pure tree builder behind the Investment Holdings grouped view.
import { test } from "node:test";
import assert from "node:assert/strict";

globalThis.window = globalThis;
globalThis.renderMain = () => {};
const m = await import("../../frontend/js/dashboard_decomp_holdings_tree.js");

const lot = (account, symbol, date, shares, basis, value, asset_class = "Equity", subclass = "US Total Equity") =>
  ({ account, symbol, purchase_date: date, shares, basis, value, asset_class, subclass });
const lots = [
  lot("A", "VTI", "2024-01-02", 10, 1000, 1500), lot("A", "VTI", "2025-03-04", 5, 700, 750),
  lot("B", "VTI", "2024-05-06", 2, 200, 300), lot("A", "BND", "2024-01-02", 20, 1000, 900, "Fixed Income", null),
];

test("order always ends in lot and ignores unknown or repeated levels", () => {
  assert.deepEqual(m.htNormalizeOrder(["symbol", "bogus", "symbol", "lot", "account"]), ["symbol", "account", "lot"]);
  assert.deepEqual(m.htNormalizeOrder(null), m.HT_DEFAULT_ORDER);
  assert.deepEqual(m.htToggleDimension(["class", "lot"], "symbol"), ["class", "symbol", "lot"]);
  assert.deepEqual(m.htToggleDimension(["class", "symbol", "lot"], "class"), ["symbol", "lot"]);
  assert.deepEqual(m.htStepDimension(["class", "symbol", "lot"], "symbol", -1), ["symbol", "class", "lot"]);
});

test("groups by class then symbol, totals roll up, lots newest first", () => {
  const t = m.htBuildTree(lots, ["class", "symbol", "lot"]);
  assert.deepEqual(t.nodes.map((n) => n.label), ["Equity", "Fixed Income"]);
  const eq = t.nodes[0];
  assert.equal(eq.row.value, 2550);
  assert.equal(eq.row.gain, 2550 - 1900);
  const vti = eq.children[0];
  assert.equal(vti.label, "VTI");
  assert.deepEqual(vti.children.map((n) => n.name), ["2025-03-04", "2024-05-06", "2024-01-02"]);
  assert.equal(t.total.value, 3450);
});

test("changing the hierarchy regroups the same lots", () => {
  const t = m.htBuildTree(lots, ["account", "lot"], (a) => `Acct ${a}`);
  assert.deepEqual(t.nodes.map((n) => n.label), ["Acct A", "Acct B"]);
  assert.equal(t.nodes[0].children.length, 3);
});

test("a level that only repeats its parent is skipped", () => {
  const t = m.htBuildTree([lot("A", "BND", "2024-01-02", 20, 1000, 900, "Fixed Income", null)], ["class", "subclass", "lot"]);
  assert.equal(t.nodes[0].children[0].dim, "lot");
});
