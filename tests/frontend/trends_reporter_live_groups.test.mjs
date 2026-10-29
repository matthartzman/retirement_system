// Current Snapshot Group By: the pure grouping, ordering and aggregation behind the table
// (financial_trends_reporter/frontend/live_groups.js). No DOM.
import { test, describe } from "node:test";
import assert from "node:assert/strict";
import {
  DIMENSIONS, DEFAULT_ORDER, normalizeOrder, parseSavedOrder, moveDimension, stepDimension, toggleDimension, dropOrder,
  aggregate, buildTree, groupLabel, normalizeSort, parseSavedSort,
} from "../../financial_trends_reporter/frontend/live_groups.js";

const LOT = (o) => ({
  account: "A", symbol: "ITOT", title: "", asset_class: "Equity", subclass: "US Total Equity", purchase_date: "2025-06-01",
  shares: 10, purchase_price: 100, reinvested: false, start: 1000, new_money: 0, weighted: 0, current: 1100, day: 10, ...o,
});
const near = (a, b, msg) => assert.ok(Math.abs(a - b) < 1e-9, `${msg}: ${a} vs ${b}`);

describe("order", () => {
  test("the default is sub-class, symbol, account, lot", () => {
    assert.deepEqual(DEFAULT_ORDER, ["subclass", "symbol", "account", "lot"]);
    assert.deepEqual(Object.keys(DIMENSIONS).sort(), ["account", "class", "lot", "subclass", "symbol"]);
  });
  test("normalize keeps known, unique levels and always ends with lot", () => {
    assert.deepEqual(normalizeOrder(["symbol", "lot", "class", "symbol", "bogus"]), ["symbol", "class", "lot"]);
    assert.deepEqual(normalizeOrder(["lot"]), ["lot"]);
    assert.deepEqual(normalizeOrder([]), ["lot"]);
    for (const bad of [null, undefined, "x", 3, {}]) assert.deepEqual(normalizeOrder(bad), DEFAULT_ORDER);
  });
  test("a saved order that is unreadable falls back to the default", () => {
    assert.deepEqual(parseSavedOrder(null), DEFAULT_ORDER);
    assert.deepEqual(parseSavedOrder("not json"), DEFAULT_ORDER);
    assert.deepEqual(parseSavedOrder(JSON.stringify(["account", "symbol"])), ["account", "symbol", "lot"]);
  });
  test("move and step never move lot and never leave the list", () => {
    assert.deepEqual(moveDimension(DEFAULT_ORDER, "account", 0), ["account", "subclass", "symbol", "lot"]);
    assert.deepEqual(moveDimension(DEFAULT_ORDER, "subclass", 99), ["symbol", "account", "subclass", "lot"]);
    assert.deepEqual(moveDimension(DEFAULT_ORDER, "lot", 0), DEFAULT_ORDER);
    assert.deepEqual(stepDimension(DEFAULT_ORDER, "symbol", -1), ["symbol", "subclass", "account", "lot"]);
    assert.deepEqual(stepDimension(DEFAULT_ORDER, "symbol", 1), ["subclass", "account", "symbol", "lot"]);
    assert.deepEqual(stepDimension(DEFAULT_ORDER, "subclass", -1), DEFAULT_ORDER);
    assert.deepEqual(stepDimension(DEFAULT_ORDER, "account", 1), DEFAULT_ORDER);   // lot stays last
  });
  test("toggle adds a level before lot, or removes one; lot cannot be removed", () => {
    assert.deepEqual(toggleDimension(DEFAULT_ORDER, "class"), ["subclass", "symbol", "account", "class", "lot"]);
    assert.deepEqual(toggleDimension(DEFAULT_ORDER, "symbol"), ["subclass", "account", "lot"]);
    assert.deepEqual(toggleDimension(DEFAULT_ORDER, "lot"), DEFAULT_ORDER);
  });
  test("dropping a chip before or after another", () => {
    assert.deepEqual(dropOrder(DEFAULT_ORDER, "account", "subclass", false), ["account", "subclass", "symbol", "lot"]);
    assert.deepEqual(dropOrder(DEFAULT_ORDER, "subclass", "account", true), ["symbol", "account", "subclass", "lot"]);
    assert.deepEqual(dropOrder(DEFAULT_ORDER, "symbol", "symbol", true), DEFAULT_ORDER);
    assert.deepEqual(dropOrder(DEFAULT_ORDER, "account", "lot", false), ["subclass", "symbol", "account", "lot"]);
    assert.deepEqual(dropOrder(DEFAULT_ORDER, "account", "lot", true), ["subclass", "symbol", "account", "lot"]);
  });
});

describe("aggregate (the server's formulas)", () => {
  const totals = { current: 2200, gain: 200 };
  test("one lot", () => {
    const r = aggregate([LOT()], totals, 300);
    assert.deepEqual([r.start, r.new_money, r.current, r.market_gain, r.day], [1000, 0, 1100, 100, 10]);
    near(r.return_pct, 100 / 1000, "return");
    near(r.share, 0.5, "share");
    near(r.share_of_gain, 0.5, "share of gain");
    near(r.day_pct, 10 / 1090, "day pct");
    near(r.annualized_pct, 1.1 ** (365 / 300) - 1, "annualized");
  });
  test("new money counts as cost, and its time weighting widens the return's base", () => {
    const r = aggregate([LOT({ start: 0, new_money: 500, weighted: 250, current: 600 })], { current: 600, gain: 100 }, 300);
    assert.equal(r.market_gain, 100);
    near(r.return_pct, 100 / 250, "return over weighted new money");
  });
  test("day is null when no lot has a previous close, and sums only the lots that do", () => {
    assert.equal(aggregate([LOT({ day: null })], totals, 300).day, null);
    assert.equal(aggregate([LOT({ day: null })], totals, 300).day_pct, null);
    assert.equal(aggregate([LOT({ day: null }), LOT({ day: 5 })], totals, 300).day, 5);
  });
  test("no base, no total gain, or too few days gives null rather than a made-up number", () => {
    const zero = aggregate([LOT({ start: 0, new_money: 0, weighted: 0, current: 0, day: null })], totals, 300);
    assert.equal(zero.return_pct, null);
    assert.equal(aggregate([LOT()], { current: 2200, gain: 0 }, 300).share_of_gain, null);
    assert.equal(aggregate([LOT()], totals, 89).annualized_pct, null);
    assert.equal(aggregate([LOT({ current: 0, start: 1000 })], totals, 300).annualized_pct, null);   // lost everything: <= -100%
  });
});

describe("buildTree", () => {
  const P = [
    LOT({ account: "A", symbol: "ITOT", current: 3000, start: 2500 }),
    LOT({ account: "B", symbol: "ITOT", current: 1000, start: 900, purchase_date: "2026-02-01" }),
    LOT({ account: "A", symbol: "IXUS", subclass: "International Equity", current: 2000, start: 1800 }),
    LOT({ account: "A", symbol: "PDBC", asset_class: "Commodities", subclass: null, current: 500, start: 450 }),
    LOT({ account: "Z_cash", symbol: "CASH", asset_class: "Cash", subclass: null, current: 100, start: 100, new_money: 0, weighted: 0, day: 0, purchase_date: "2026-06-01" }),
    LOT({ account: "a_cash", symbol: "CASH", asset_class: "Cash", subclass: null, current: 50, start: 50, new_money: 0, weighted: 0, day: 0, purchase_date: "2026-07-01" }),
  ];
  const opts = { days: 300, labelOf: (id) => id };
  const big = { ...opts, sort: { field: "current", dir: "desc" } };
  const names = (nodes) => nodes.map((n) => n.name);

  test("sub-class first falls back to the asset class for holdings without one; largest first", () => {
    const t = buildTree(P, DEFAULT_ORDER, big);
    assert.deepEqual(names(t.nodes), ["US Total Equity", "International Equity", "Commodities", "Cash"]);
    assert.equal(groupLabel(P[3], "subclass"), "Commodities");
  });
  test("asset class level follows the fixed class order, not size", () => {
    const t = buildTree(P, ["class", "symbol", "lot"], opts);
    assert.deepEqual(names(t.nodes), ["Equity", "Commodities", "Cash"]);
  });
  test("every level's rows sum to its parent and to the total", () => {
    const t = buildTree(P, DEFAULT_ORDER, opts);
    const sum = (nodes, k) => nodes.reduce((s, n) => s + n.row[k], 0);
    assert.equal(sum(t.nodes, "current"), 6650);
    for (const n of t.nodes) for (const k of ["current", "start", "market_gain"]) near(sum(n.children, k), n.row[k], `${n.name} ${k}`);
    near(sum(t.nodes, "share"), 1, "shares");
    near(t.total.current, 6650, "total");
  });
  test("paths are unique and each child names its parent", () => {
    const t = buildTree(P, DEFAULT_ORDER, opts);
    const all = [];
    const walk = (nodes, parent) => nodes.forEach((n) => { assert.equal(n.parent, parent); all.push(n.path); walk(n.children, n.path); });
    walk(t.nodes, null);
    assert.equal(new Set(all).size, all.length);
  });
  test("lots are the leaves, newest first, undated last", () => {
    const lots = [LOT({ purchase_date: "2024-01-01" }), LOT({ purchase_date: null }), LOT({ purchase_date: "2026-01-01" })];
    const t = buildTree(lots, ["lot"], opts);
    assert.deepEqual(names(t.nodes), ["2026-01-01", "2024-01-01", "Undated"]);
    assert.ok(t.nodes.every((n) => n.lot && n.children.length === 0));
  });
  test("a single cash lot is folded into its account row: date inline, no lot child", () => {
    const t = buildTree(P, DEFAULT_ORDER, opts);
    const cash = t.nodes.find((n) => n.name === "Cash");
    assert.ok(cash.children.every((a) => a.children.length === 0 && a.inline));
    assert.deepEqual(cash.children.map((a) => a.inline), ["2026-07-01", "2026-06-01"]);
  });
  test("accounts always read A to Z by the name shown, not by id or size", () => {
    const labelOf = (id) => ({ Z_cash: "Zed cash", a_cash: "alpha cash", A: "Pat IRA", B: "Matt IRA" })[id] || id;
    const t = buildTree(P, DEFAULT_ORDER, { ...opts, labelOf });
    const cash = t.nodes.find((n) => n.name === "Cash");
    assert.deepEqual(cash.children.map((a) => a.label), ["alpha cash", "Zed cash"]);
    const itot = t.nodes.find((n) => n.name === "US Total Equity").children[0];   // A is larger, but B's name comes first
    assert.deepEqual(itot.children.map((a) => a.label), ["Matt IRA", "Pat IRA"]);
    const top = buildTree(P, ["account", "lot"], { ...opts, labelOf });
    assert.deepEqual(top.nodes.map((a) => a.label), ["alpha cash", "Matt IRA", "Pat IRA", "Zed cash"]);
  });
  test("a non-cash lot keeps its lot row, and non-cash lots are never folded", () => {
    const t = buildTree(P, DEFAULT_ORDER, big);
    const acct = t.nodes[0].children[0].children[0];
    assert.equal(acct.children.length, 1);
    assert.ok(acct.children[0].lot);
    assert.equal(acct.inline, undefined);
  });
  test("any order works, and the same lots total the same either way", () => {
    const a = buildTree(P, ["account", "class", "symbol", "lot"], opts);
    const b = buildTree(P, ["symbol", "account", "lot"], opts);
    near(a.total.current, b.total.current, "total");
    near(a.nodes.reduce((s, n) => s + n.row.market_gain, 0), b.nodes.reduce((s, n) => s + n.row.market_gain, 0), "gain");
  });
  test("a level that only repeats its parent's name is skipped: no extra click, no duplicate row", () => {
    const t = buildTree(P, ["class", "subclass", "symbol", "account", "lot"], big);
    const commodities = t.nodes.find((n) => n.name === "Commodities");
    assert.deepEqual(commodities.skipped, ["subclass"]);
    assert.deepEqual(names(commodities.children), ["PDBC"]);
    assert.equal(commodities.children[0].parent, commodities.path);
    const cash = t.nodes.find((n) => n.name === "Cash");   // sub-class Cash and symbol CASH both repeat it
    assert.deepEqual(cash.skipped, ["subclass", "symbol"]);
    assert.deepEqual(names(cash.children).sort(), ["Z_cash", "a_cash"]);
    const equity = t.nodes.find((n) => n.name === "Equity");   // two sub-classes: kept
    assert.equal(equity.skipped, undefined);
    assert.deepEqual(names(equity.children), ["US Total Equity", "International Equity"]);
  });
  test("a single child with a different name is kept", () => {
    const t = buildTree(P, ["symbol", "account", "lot"], opts);
    const ixus = t.nodes.find((n) => n.name === "IXUS");
    assert.equal(ixus.skipped, undefined);
    assert.deepEqual(names(ixus.children), ["A"]);
  });
  test("the default sort is by name A to Z at every level (asset classes keep their fixed order)", () => {
    const t = buildTree(P, DEFAULT_ORDER, opts);
    assert.deepEqual(names(t.nodes), ["Cash", "Commodities", "International Equity", "US Total Equity"]);
    assert.deepEqual(names(buildTree(P, ["class", "lot"], opts).nodes), ["Equity", "Commodities", "Cash"]);
    assert.deepEqual(names(buildTree(P, ["class", "lot"], { ...opts, sort: { field: "name", dir: "desc" } }).nodes), ["Cash", "Commodities", "Equity"]);
  });
  test("a figure column sorts either way at every level; ties fall back to the name", () => {
    const asc = buildTree(P, DEFAULT_ORDER, { ...opts, sort: { field: "current", dir: "asc" } });
    assert.deepEqual(names(asc.nodes), ["Cash", "Commodities", "International Equity", "US Total Equity"]);
    const itot = buildTree(P, ["symbol", "account", "lot"], { ...opts, sort: { field: "current", dir: "desc" } }).nodes.find((n) => n.name === "ITOT");
    assert.deepEqual(names(itot.children), ["A", "B"]);
    const flipped = buildTree(P, ["symbol", "account", "lot"], { ...opts, sort: { field: "current", dir: "asc" } }).nodes.find((n) => n.name === "ITOT");
    assert.deepEqual(names(flipped.children), ["B", "A"]);
  });
  test("a missing figure sorts last in either direction; lots stay newest first", () => {
    const lots = [LOT({ symbol: "X", day: null, purchase_date: "2024-01-01" }), LOT({ symbol: "Y", day: 5, purchase_date: "2026-01-01" })];
    for (const dir of ["asc", "desc"]) {
      assert.deepEqual(names(buildTree(lots, ["symbol", "lot"], { ...opts, sort: { field: "day", dir } }).nodes), ["Y", "X"], dir);
    }
    assert.deepEqual(names(buildTree(lots, ["lot"], { ...opts, sort: { field: "current", dir: "asc" } }).nodes), ["2026-01-01", "2024-01-01"]);
  });
  test("an unknown saved sort falls back to name A to Z", () => {
    assert.deepEqual(normalizeSort({ field: "bogus", dir: "sideways" }), { field: "name", dir: "asc" });
    assert.deepEqual(parseSavedSort("{nope"), { field: "name", dir: "asc" });
    assert.deepEqual(parseSavedSort(JSON.stringify({ field: "return_pct", dir: "desc" })), { field: "return_pct", dir: "desc" });
  });
  test("an empty list is an empty table, not an error", () => {
    const t = buildTree([], DEFAULT_ORDER, opts);
    assert.deepEqual(t.nodes, []);
    assert.equal(t.total.current, 0);
  });
});

describe("sold lots (sales ledger 4.2)", () => {
  // A sold AVUV lot (start 4500, proceeds 5500 out) and the Cash row that takes the 5500 in, beside held rows.
  const SOLD = LOT({ symbol: "AVUV", subclass: "Small-Cap Value", sold: true, shares: 0, start: 4500, new_money: -5500, weighted: -550, current: 0, day: null });
  const SWAP = LOT({ symbol: "CASH", asset_class: "Cash", subclass: null, sold: true, shares: 0, start: -5500, new_money: 5500, weighted: 550, current: 0, day: null });
  const HELD = [LOT({ symbol: "ITOT", start: 12000, current: 13000 }), LOT({ symbol: "CASH", asset_class: "Cash", subclass: null, start: 6500, current: 6500, day: 0 })];
  const ALL = [...HELD, SOLD, SWAP];

  test("sold rows are in every group total and the groups add up to the total", () => {
    for (const order of [["class", "symbol", "lot"], ["account", "lot"], ["subclass", "symbol", "account", "lot"]]) {
      const { nodes, total } = buildTree(ALL, order, { days: 300 });
      near(nodes.reduce((s, n) => s + n.row.market_gain, 0), total.market_gain, "gain");
      near(nodes.reduce((s, n) => s + n.row.start, 0), total.start, "start");
      near(nodes.reduce((s, n) => s + n.row.new_money, 0), total.new_money, "new money");
      near(total.market_gain, 2000, "total gain = ITOT 1000 + AVUV 1000");
    }
  });
  test("per-group returns come from the signed money out and in", () => {
    const { nodes } = buildTree(ALL, ["class", "lot"], { days: 300 });
    const equity = nodes.find((n) => n.name === "Equity"), cash = nodes.find((n) => n.name === "Cash");
    near(equity.row.market_gain, 2000, "equity gain");
    near(equity.row.return_pct, 2000 / (16500 - 550), "equity return");
    near(cash.row.market_gain, 0, "cash gain");
  });
  test("a sold ticker is its own (sold) row, apart from the same ticker still held", () => {
    const held = LOT({ symbol: "AVUV", subclass: "Small-Cap Value", start: 900, current: 1000 });
    const { nodes } = buildTree([held, SOLD], ["symbol", "lot"], { days: 300 });
    assert.deepEqual(nodes.map((n) => n.name).sort(), ["AVUV", "AVUV (sold)"]);
    near(nodes.find((n) => n.name === "AVUV (sold)").row.market_gain, 1000, "sold gain");
    assert.equal(groupLabel(SWAP, "symbol"), "CASH");    // the Cash row stays in Cash
  });
});

