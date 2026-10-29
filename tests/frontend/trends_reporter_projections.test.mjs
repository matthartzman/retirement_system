// Recent Projections (financial_trends_reporter/frontend/projection_groups.js): the column group tree,
// what a collapsed or opened table shows, the year window and the Cash Flow window total. No DOM.
import { test, describe } from "node:test";
import assert from "node:assert/strict";
import {
  buildTree, visibleColumns, windowRows, clampYears, windowTotal, reconcileNW,
} from "../../financial_trends_reporter/frontend/projection_groups.js";

const col = (key, label, banner, subtotal = false) => ({ key, label, banner, subtotal });
const NW_COLS = [
  col("Pension PV", "Pension PV", "ANNUITIES & PENSION"), col("W Single PV", "Pat Single PV", "ANNUITIES & PENSION"),
  col("W Joint PV", "Pat Joint PV", "ANNUITIES & PENSION"), col("H Single PV", "Matt Single PV", "ANNUITIES & PENSION"),
  col("H Joint PV", "Matt Joint PV", "ANNUITIES & PENSION"), col("Σ Ann", "Σ Ann", "ANNUITIES & PENSION", true),
  col("PreTax_1", "Matt IRA", "PRE-TAX"), col("PreTax_2", "Matt 401k", "PRE-TAX"), col("PreTax_3", "Pat IRA", "PRE-TAX"),
  col("Σ PreTax", "Σ PreTax", "PRE-TAX", true), col("Roth_1", "Matt Roth", "ROTH"), col("Roth_2", "Pat Roth", "ROTH"),
  col("Σ Roth", "Σ Roth", "ROTH", true), col("Trust_1", "Matt Trust", "TRUSTS"), col("Trust_2", "Pat Trust", "TRUSTS"),
  col("Σ Trust", "Σ Trust", "TRUSTS", true), col("HSA_1", "Matt HSA", "HSA"), col("Home Equity", "Home Equity", "OTHER ASSETS"),
  col("Next Housing Equity", "Next Housing Equity", "OTHER ASSETS"), col("Startup", "Startup", "OTHER ASSETS"),
  col("Autos", "Autos", "OTHER ASSETS"), col("Note", "Note", "OTHER ASSETS"), col("Cash", "Cash", "OTHER ASSETS"),
  col("Σ Other", "Σ Other", "OTHER ASSETS", true), col("TOTAL NW", "TOTAL NW", "TOTAL", true),
];
const NW_2026 = {
  "Pension PV": 64738.91815552025, "W Single PV": 51035.49799864552, "W Joint PV": 313532.7613828605,
  "H Single PV": 84379.73264388696, "H Joint PV": 743389.72411315, "Σ Ann": 1257076.634294063,
  PreTax_1: 1364781.93124, PreTax_2: 20824.32, PreTax_3: 473735.7735249999, "Σ PreTax": 1859342.024765,
  Roth_1: 136506.35365, Roth_2: 202139.467361, "Σ Roth": 338645.821011, Trust_1: 221825.00973, Trust_2: 336083.951712,
  "Σ Trust": 557908.961442, HSA_1: 73174.74664, "Home Equity": 1052241, "Next Housing Equity": 0, Startup: 66000,
  Autos: 48382.38222222222, Note: 414971.34, Cash: 20000, "Σ Other": 1601594.722222222, "TOTAL NW": 5687742.910374286,
};
const NW = {
  columns: NW_COLS,
  rows: [
    { year: 2026, ages: [64, 65], values: NW_2026 },
    { year: 2027, ages: [65, 66], values: { ...NW_2026, "TOTAL NW": 5582247.974889976 } },
  ],
};

const CF_KEYS = [
  ["Earned", "INCOME"], ["H_SS", "INCOME"], ["W_SS", "INCOME"], ["Pension", "INCOME"], ["Note", "INCOME"], ["RMD", "INCOME"],
  ["Σ_Inc", "INCOME", true], ["Roth_Conv", "INCOME"], ["AGI", "TAXES"], ["Taxable", "TAXES"], ["Fed", "TAXES"],
  ["State", "TAXES"], ["Spend_Base", "SPENDING"], ["Housing", "SPENDING"], ["Mort_PI", "SPENDING"],
  ["Prop_Tax", "SPENDING"], ["Wellness", "SPENDING"], ["Wellness_Medical", "SPENDING"], ["Travel", "SPENDING"],
  ["Σ_Spend", "SPENDING", true], ["Other_Cash_Need", "SPENDING"], ["Total_Tax", "CASH BRIDGE", true],
  ["Total_Cash_Need", "CASH BRIDGE", true], ["Income_Funding", "CASH BRIDGE"], ["Req_Portfolio_Draws", "CASH BRIDGE"],
  ["Cash_Bridge_Gap", "CASH BRIDGE"], ["H_Trust_WD", "ACCOUNT OUTFLOWS"], ["W_Trust_WD", "ACCOUNT OUTFLOWS"],
  ["Σ_Trust", "ACCOUNT OUTFLOWS", true], ["HSA_WD", "ACCOUNT OUTFLOWS"], ["H_IRA_RMD", "ACCOUNT OUTFLOWS"],
  ["H_IRA_Elec", "ACCOUNT OUTFLOWS"], ["H_IRA_Conv", "ACCOUNT OUTFLOWS"], ["H_IRA_Tot", "ACCOUNT OUTFLOWS"],
  ["HELOC_Draw", "ACCOUNT OUTFLOWS"], ["HELOC_Bal", "ACCOUNT OUTFLOWS"], ["Σ_WD", "ACCOUNT OUTFLOWS", true],
  ["NW_Check", "NET WORTH", true],
];
const CF_ROW = (year, k) => ({ year, ages: [year - 1962, year - 1961], values: Object.fromEntries(CF_KEYS.map(([key], i) => [key, (i + 1) * k])) });
const CF = { columns: CF_KEYS.map(([key, banner, sub]) => col(key, key.replace("_", " "), banner, !!sub)), rows: [CF_ROW(2026, 1), CF_ROW(2027, 2)] };
const labels = (cols) => cols.map((c) => c.label);

describe("collapsed tables", () => {
  test("collapsed NW is the six spec columns (Year is rendered separately, frozen)", () => {
    const cols = visibleColumns(buildTree(NW, "nw"), new Set());
    assert.deepEqual(labels(cols), ["Investable", "Annuities & Pension", "Home & Other", "Total NW", "Δ vs prior"]);
    assert.deepEqual(cols.map((c) => c.expandable), [true, true, true, false, false]);
  });
  test("collapsed CF is the eight spec columns", () => {
    const cols = visibleColumns(buildTree(CF, "cf"), new Set());
    assert.deepEqual(labels(cols), ["Income", "Taxes", "Spending", "Cash Need", "Portfolio Draws", "Roth Conv", "Net Worth"]);
  });
});

describe("opening groups", () => {
  test("opening Investable keeps its subtotal first, then its children", () => {
    const cols = visibleColumns(buildTree(NW, "nw"), new Set(["investable"]));
    assert.equal(cols[0].id, "investable");
    assert.equal(cols[0].kind, "subtotal");
    assert.deepEqual(labels(cols.slice(1, 6)), ["Pre-Tax", "Roth", "Trusts", "Matt HSA", "Cash"]);
    assert.ok(cols.slice(1, 6).every((c) => c.depth === 1));
    assert.equal(cols[6].label, "Annuities & Pension");
  });
  test("a nested group opens to its accounts under its own subtotal", () => {
    const cols = visibleColumns(buildTree(NW, "nw"), new Set(["investable", "pretax"]));
    assert.deepEqual(labels(cols.slice(1, 5)), ["Pre-Tax", "Matt IRA", "Matt 401k", "Pat IRA"]);
    assert.equal(cols[2].depth, 2);
  });
  test("an open nested group under a closed parent stays hidden", () => {
    const cols = visibleColumns(buildTree(NW, "nw"), new Set(["pretax"]));
    assert.equal(cols.length, 5);
  });
  test("context columns show muted after the group's detail and IRA totals are dropped", () => {
    const tree = buildTree(CF, "cf");
    const taxes = visibleColumns(tree, new Set(["taxes"]));
    const ctx = taxes.filter((c) => c.kind === "context").map((c) => c.label);
    assert.deepEqual(ctx, ["AGI", "Taxable"]);
    const all = visibleColumns(tree, new Set(["income", "taxes", "spending", "need", "draws", "ira", "conv", "housing", "wellness", "trust"]));
    assert.ok(!all.some((c) => c.id === "H_IRA_Tot"));
    assert.deepEqual(tree.unmapped, []);
  });
});

describe("values", () => {
  test("NW reconciles to the cent on the real 2026 row, and a mismatch shows", () => {
    const [r2026, r2027] = buildTree(NW, "nw").rows;
    assert.ok(Math.abs(reconcileNW(r2026)) < 0.005, String(reconcileNW(r2026)));
    // the 2027 fixture keeps 2026's components under a new total, so it is off by the change
    assert.ok(Math.abs(reconcileNW(r2027) - (5687742.910374286 - 5582247.974889976)) < 1e-6);
  });
  test("Investable and Home & Other on the 2026 row", () => {
    const tree = buildTree(NW, "nw");
    const cols = visibleColumns(tree, new Set());
    const [inv, , ho] = cols.map((c) => c.value(tree.rows[0]));
    assert.equal(Math.round(inv), 2849072);
    assert.equal(Math.round(ho), 1581595);
  });
  test("Δ is null for the plan's first year, else the difference", () => {
    const tree = buildTree(NW, "nw");
    const delta = visibleColumns(tree, new Set()).at(-1);
    assert.equal(delta.value(tree.rows[0]), null);
    assert.ok(Math.abs(delta.value(tree.rows[1]) - (5582247.974889976 - 5687742.910374286)) < 1e-6);
  });
  test("CF window total sums flows and skips context and Net Worth", () => {
    const tree = buildTree(CF, "cf");
    const cols = visibleColumns(tree, new Set(["taxes"]));
    const total = windowTotal(tree.rows, cols);
    const inc = cols.find((c) => c.id === "income");
    assert.equal(total.income, inc.value(tree.rows[0]) + inc.value(tree.rows[1]));
    assert.equal(total.AGI, null);
    assert.equal(total.networth, null);
  });
});

describe("unmapped and conditional keys", () => {
  test("rental keys mapped", () => {
    const nw = { columns: [...NW_COLS, col("Rental Equity", "Rental Equity", "OTHER ASSETS")], rows: NW.rows };
    const cf = { columns: [...CF.columns, col("Rental", "Rental Cash (net)", "INCOME"), col("Rental_Tax", "Rental Tax", "TAXES"),
      col("Rent_Det", "Rent", "SPENDING"), col("HC_LTC", "LTC", "SPENDING")], rows: CF.rows };
    assert.deepEqual(buildTree(nw, "nw").unmapped, []);
    assert.deepEqual(buildTree(cf, "cf").unmapped, []);
    const ho = visibleColumns(buildTree(nw, "nw"), new Set(["homeother"]));
    assert.ok(labels(ho).includes("Rental Equity"));
  });
  test("unknown key falls back to its banner's group", () => {
    const cf = { columns: [...CF.columns, col("New_Tax", "New Tax", "TAXES")], rows: CF.rows };
    const tree = buildTree(cf, "cf");
    assert.deepEqual(tree.unmapped, ["New_Tax"]);
    const taxes = visibleColumns(tree, new Set(["taxes"]));
    assert.ok(labels(taxes).includes("New Tax"));
  });
  test("keys missing from the table are pruned", () => {
    const cols = visibleColumns(buildTree(CF, "cf"), new Set(["income"]));
    assert.ok(!labels(cols).includes("W Sgl"));
  });
});

describe("year window", () => {
  const rows = Array.from({ length: 36 }, (_, i) => ({ year: 2026 + i }));
  test("starts at the given year", () => {
    const w = windowRows(rows, 2026, 5);
    assert.deepEqual(w.rows.map((r) => r.year), [2026, 2027, 2028, 2029, 2030]);
    assert.equal(w.endsAt, null);
  });
  test("windowRows clamps to plan years", () => {
    const w = windowRows(rows, 2059, 5);
    assert.deepEqual(w.rows.map((r) => r.year), [2059, 2060, 2061]);
    assert.equal(w.endsAt, 2061);
  });
  test("a start before the plan begins at the plan's first year", () => {
    assert.equal(windowRows(rows, 2020, 3).rows[0].year, 2026);
  });
  test("a start after the plan shows its last years, never an empty table", () => {
    const w = windowRows(rows, 2070, 2);
    assert.deepEqual(w.rows.map((r) => r.year), [2060, 2061]);
    assert.equal(w.endsAt, 2061);
  });
  test("clampYears", () => {
    assert.deepEqual(["", 0, 99, "abc", 7, "12", null, 3.6].map(clampYears), [5, 1, 30, 5, 7, 12, 5, 4]);
  });
});
