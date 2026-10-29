// Recent Projections (financial_trends_reporter/frontend/projection_groups.js): the column group tree,
// what a collapsed or opened table shows, the year window and the Cash Flow window total. No DOM.
import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  buildTree, visibleColumns, windowRows, clampYears, windowTotal, reconcileNW,
} from "../../financial_trends_reporter/frontend/projection_groups.js";
import { renderProjections, buildLine, mountProjections, EMPTY_TEXT } from "../../financial_trends_reporter/frontend/projections.js";
import { setMoneyView } from "../../financial_trends_reporter/frontend/money_view.js";

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
  test("liabilities and a credit shelter trust the sheet doesn't show join their groups and keep NW footing", () => {
    const values = { ...NW_2026, Other_Liab: -14286.78, CST: 1000, "TOTAL NW": NW_2026["TOTAL NW"] - 14286.78 + 1000 };
    const nw = { columns: [...NW_COLS, col("Other_Liab", "Loans & Other Liabilities", "OTHER ASSETS"), col("CST", "Credit Shelter Trust", "OTHER ASSETS")],
      rows: [{ year: 2026, ages: [64, 65], values }] };
    const tree = buildTree(nw, "nw");
    assert.deepEqual(tree.unmapped, []);
    assert.ok(Math.abs(reconcileNW(tree.rows[0])) < 0.005, String(reconcileNW(tree.rows[0])));
    const open = visibleColumns(tree, new Set(["investable", "homeother"]));
    assert.ok(labels(open).includes("Loans & Other Liabilities"));
    assert.ok(labels(open).includes("Credit Shelter Trust"));
  });
  test("every column the builder emits (fixture from the Python emit test) has a group", () => {
    const fx = JSON.parse(readFileSync(new URL("../fixtures/projection_table_columns.json", import.meta.url), "utf8"));
    for (const [name, tables] of Object.entries(fx)) {
      for (const [which, key] of [["nw", "net_worth"], ["cf", "cash_flow"]]) {
        const table = { columns: tables[key].map((c) => col(c.key, c.key, c.banner)), rows: [] };
        assert.deepEqual(buildTree(table, which).unmapped, [], `${name} ${key}`);
      }
    }
  });
  test("a new column goes to the group holding most of its banner, not one that borrows a key", () => {
    const nw = { columns: [...NW_COLS, col("Boat", "Boat", "OTHER ASSETS")], rows: NW.rows };
    assert.ok(labels(visibleColumns(buildTree(nw, "nw"), new Set(["homeother"]))).includes("Boat"));
    const cf = { columns: [...CF.columns, col("New_Draw", "New Draw", "ACCOUNT OUTFLOWS"), col("New_Bridge", "New Bridge", "CASH BRIDGE")], rows: CF.rows };
    const tree = buildTree(cf, "cf");
    assert.ok(labels(visibleColumns(tree, new Set(["draws"]))).includes("New Draw"));
    assert.ok(labels(visibleColumns(tree, new Set(["need"]))).includes("New Bridge"));
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

// ---- the view (financial_trends_reporter/frontend/projections.js) ----
const DOC = (extra = {}) => ({
  schema: "projection_tables/1", build_id: "b1", built_at: "2026-10-03T21:56:40Z", owners: ["Matt", "Pat"],
  plan_changed: false, plan_first_year: 2026, plan_last_year: 2027, tables: { net_worth: NW, cash_flow: CF }, ...extra,
});
const NOW = new Date("2026-10-29T12:00:00Z");
const UI = (o = {}) => ({ table: "nw", years: 5, open: new Set(), now: NOW, narrow: false, ...o });
const leafHeaders = (html) => (html.match(/<thead>[\s\S]*?<\/thead>/)[0].match(/<th scope="col"/g) || []).length;
const norm = (s) => s.replace(/\s/g, " ");

describe("render", () => {
  test("collapsed NW has six column headers and ages in the year cell", () => {
    setMoneyView({ allowed: "both", shown: "dollars", scale: 1 });
    const html = renderProjections(DOC(), UI());
    assert.equal(leafHeaders(html), 6);
    assert.match(html, /<th scope="row" class="proj-year"[^>]*>2026<span class="proj-ages">64 \/ 65<\/span>/);
    assert.match(html, /\$5,687,743/);
  });
  test("collapsed CF has eight column headers and an N-yr total row", () => {
    const html = renderProjections(DOC(), UI({ table: "cf", years: 2 }));
    assert.equal(leafHeaders(html), 8);
    assert.match(html, /2-yr total/);
  });
  test("group headers are buttons that say whether they're open", () => {
    const closed = renderProjections(DOC(), UI());
    assert.match(closed, /<button type="button" class="proj-toggle" data-proj-group="investable" aria-expanded="false">/);
    const open = renderProjections(DOC(), UI({ open: new Set(["investable"]) }));
    assert.match(open, /data-proj-group="investable" aria-expanded="true"/);
    assert.equal(leafHeaders(open), 11);
  });
  test("missing data renders the rebuild prompt", () => {
    const html = renderProjections({ missing: true }, UI());
    assert.ok(html.includes(EMPTY_TEXT));
    assert.doesNotMatch(html, /data-proj-all|projYears/);   // nothing to expand or count yet
    assert.equal(EMPTY_TEXT, "Recent Projections appear after the plan is rebuilt. Rebuild in the Retirement Planner, then refresh.");
  });
  test("a window past the plan's end says where the plan ends", () => {
    assert.match(renderProjections(DOC(), UI({ years: 5 })), /The plan ends in 2027\./);
    assert.doesNotMatch(renderProjections(DOC(), UI({ years: 2 })), /The plan ends/);
  });
  test("a negative change is written with a minus sign before the dollar", () => {
    assert.match(renderProjections(DOC(), UI()), /class="num neg">−\$105,495</);
  });
  test("narrow screens use compact amounts", () => {
    assert.match(renderProjections(DOC(), UI({ narrow: true })), />\$5\.69M</);
  });
  test("percent mode writes every cell as a percent of today's net worth", () => {
    setMoneyView({ allowed: "both", shown: "percent", scale: 5687742.910374286 });
    const html = renderProjections(DOC(), UI());
    assert.match(html, />100\.0%</);
    assert.doesNotMatch(html.replace(/<span class="proj-build[\s\S]*?<\/span>/, ""), /\$\d/);
    setMoneyView({ allowed: "both", shown: "dollars", scale: 1 });
  });
  test("a regrouping that doesn't add up is shown, not hidden", () => {
    const bad = { ...NW, rows: [{ ...NW.rows[0], values: { ...NW_2026, "TOTAL NW": 1 } }] };
    const html = renderProjections(DOC({ tables: { net_worth: bad, cash_flow: CF } }), UI());
    assert.match(html, /don't add up to Total NW/);
  });
});

describe("build line", () => {
  test("date and age, not stale", () => {
    const b = buildLine("2026-10-03T21:56:40Z", false, NOW);
    assert.match(norm(b.text), /^Workbook built Oct [34], 2026 \d{1,2}:\d{2} [AP]M · 2[56] days ago$/);
    assert.equal(b.stale, false);
  });
  test("over 30 days old is stale", () => {
    assert.equal(buildLine("2026-09-20T12:00:00Z", false, NOW).stale, true);
  });
  test("a plan changed since the build is stale", () => {
    assert.equal(buildLine("2026-10-28T12:00:00Z", true, NOW).stale, true);
  });
  test("today and one day", () => {
    assert.match(buildLine("2026-10-29T11:00:00Z", false, NOW).text, /· today$/);
    assert.match(buildLine("2026-10-28T11:00:00Z", false, NOW).text, /· 1 day ago$/);
  });
});

describe("mount", () => {
  function harness({ store = {}, blocked = false, data = DOC() } = {}) {
    const listeners = {}, docListeners = {}, kv = new Map(Object.entries(store));
    const el = () => ({ innerHTML: "", hidden: true, addEventListener() {}, setAttribute() {} });
    const body = { dataset: {}, classList: { on: new Set(), toggle(c, v) { if (v) this.on.add(c); else this.on.delete(c); } } };
    const projBody = { ...el(), addEventListener: (t, fn) => { (listeners[t] ||= []).push(fn); } };
    const els = { projView: el(), projBody };
    const doc = { body, getElementById: (id) => els[id], querySelectorAll: () => [],
      addEventListener: (t, fn) => { (docListeners[t] ||= []).push(fn); } };
    const storage = { getItem: (k) => { if (blocked) throw new Error("blocked"); return kv.get(k) ?? null; },
      setItem: (k, v) => { if (blocked) throw new Error("blocked"); kv.set(k, v); } };
    const win = { localStorage: storage, fetch: async () => ({ ok: true, json: async () => data }),
      matchMedia: () => ({ matches: false, addEventListener() {} }) };
    const fire = (t, e) => (listeners[t] || []).forEach((fn) => fn(e));
    return { doc, win, kv, body, projBody, els, fire, docListeners };
  }
  const settle = () => new Promise((r) => setTimeout(r, 20));
  const click = (map) => ({ target: { closest: (sel) => map[sel] ?? null } });

  test("a saved Recent Projections view opens it and loads the table", async () => {
    const h = harness({ store: { trendsView_v1: "projections" } });
    mountProjections(h.doc, h.win, () => NOW); await settle();
    assert.equal(h.els.projView.hidden, false);
    assert.ok(h.body.classList.on.has("proj-mode"));
    assert.equal(leafHeaders(h.projBody.innerHTML), 6);
  });
  test("storage failure renders collapsed", async () => {
    const h = harness({ blocked: true });
    mountProjections(h.doc, h.win, () => NOW);
    h.docListeners.click.forEach((fn) => fn(click({ "[data-view]": { dataset: { view: "projections" } } }))); await settle();
    assert.equal(leafHeaders(h.projBody.innerHTML), 6);
    h.fire("click", click({ "[data-proj-group]": { dataset: { projGroup: "investable" } } }));
    assert.equal(leafHeaders(h.projBody.innerHTML), 11);
  });
  test("a stale remembered group is ignored and open groups are remembered", async () => {
    const h = harness({ store: { trendsView_v1: "projections", "trends.proj.open.nw": JSON.stringify(["gone", "annuities"]) } });
    mountProjections(h.doc, h.win, () => NOW); await settle();
    assert.equal(leafHeaders(h.projBody.innerHTML), 11);
    h.fire("click", click({ "[data-proj-group]": { dataset: { projGroup: "investable" } } }));
    assert.deepEqual(JSON.parse(h.kv.get("trends.proj.open.nw")).sort(), ["annuities", "investable"]);
  });
  test("Collapse all forgets every open group; Expand all opens them all", async () => {
    const h = harness({ store: { trendsView_v1: "projections", "trends.proj.open.nw": JSON.stringify(["annuities"]) } });
    mountProjections(h.doc, h.win, () => NOW); await settle();
    h.fire("click", click({ "[data-proj-all]": { dataset: { projAll: "collapse" } } }));
    assert.equal(h.kv.get("trends.proj.open.nw"), "[]");
    assert.equal(leafHeaders(h.projBody.innerHTML), 6);
    h.fire("click", click({ "[data-proj-all]": { dataset: { projAll: "expand" } } }));
    assert.ok(leafHeaders(h.projBody.innerHTML) > 20);
  });
  test("the NW / CF toggle and the year count are remembered; a bad count is clamped", async () => {
    const h = harness({ store: { trendsView_v1: "projections" } });
    mountProjections(h.doc, h.win, () => NOW); await settle();
    h.fire("click", click({ "[data-proj-table]": { dataset: { projTable: "cf" } } }));
    assert.equal(h.kv.get("trends.proj.table"), "cf");
    assert.equal(leafHeaders(h.projBody.innerHTML), 8);
    h.fire("change", { target: { id: "projYears", value: "99" } });
    assert.equal(h.kv.get("trends.proj.years"), "30");
  });
});
