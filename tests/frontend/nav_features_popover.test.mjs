// Left-nav redesign: the Set up / Maintain switch and the per-heading Features popover (pure logic).
import { test, describe } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import * as nf from "../../frontend/js/dashboard_decomp_nav_features.js";

const STEPS = [
  { id: "start", group: "Plan Status", title: "Plan Status" },
  { id: "income_work", group: "Household & Cash Flow", title: "Work Income" },
  { id: "roth_conversion", group: "Taxes", title: "Roth Conversion" },
  { id: "entity_charitable", group: "Taxes", title: "Charitable Giving" },
  { id: "account_tax_basis", group: "Taxes", title: "Account Tax Basis" },
  { id: "strategy_optimize", group: "Analyze", title: "Optimize" },
  { id: "strategy_stress", group: "Analyze", title: "Stress Test" },
  { id: "actual_spending", group: "Track & Reconcile", title: "Actual Spending" },
  { id: "monarch_reconciliation", group: "Track & Reconcile", title: "Account Reconciliation" },
];
const M = (name, extra = {}) => ({
  name,
  optional: true,
  description: `${name} does a thing. It has more detail after.`,
  domain: "Taxes",
  demand: "medium",
  gate_kind: "module_toggle",
  gated_by: null,
  gated_by_any_flag: [],
  ...extra,
});
const TAXONOMY = {
  modules: {
    roth_conversion_plan: M("Roth Conversion", { demand: "high" }),
    charitable_giving: M("Charitable Giving", { gated_by_any_flag: ["daf_giving", "qcd_giving"] }),
    daf_giving: M("DAF Giving", { optional: false, gate_kind: "plan_flag", demand: "low" }),
    qcd_giving: M("QCD Giving", { optional: false, gate_kind: "plan_flag", demand: "low" }),
    lifetime_tax_projection: M("Lifetime Taxes", { demand: "high" }),
    hsa_drawdown: M("HSA Drawdown"),
    divorce_qdro: M("Divorce / QDRO", { demand: "niche", domain: "Family & Business" }),
    spending_summary: M("Spending Summary", { gated_by: "spending_tracker_ytd" }),
    spending_tracker_ytd: M("Spending Tracker / YTD"),
    net_worth: { name: "Net Worth", optional: false, gate_kind: "module_toggle" },
  },
};
const deps = (on) => ({
  taxonomy: TAXONOMY,
  steps: STEPS,
  isOn: (k) => on.has(k),
  gatedStepIds: ["roth_conversion", "strategy_stress", "entity_charitable"],
});

describe("flow switch", () => {
  test("auto mode: Set up while anything is missing or no plan, Maintain otherwise", () => {
    assert.equal(nf.autoMode(3, true), "setup");
    assert.equal(nf.autoMode(0, false), "setup");
    assert.equal(nf.autoMode(0, true), "maintain");
  });
  test("Maintain lifts only Track & Reconcile, after the pinned Plan Status", () => {
    const names = ["Plan Status", "Household & Cash Flow", "Taxes", "Track & Reconcile", "Settings"].map((name) => ({ name }));
    assert.deepEqual(nf.orderGroups(names, "maintain").map((g) => g.name), ["Plan Status", "Track & Reconcile", "Household & Cash Flow", "Taxes", "Settings"]);
    assert.deepEqual(nf.orderGroups(names, "setup").map((g) => g.name), names.map((g) => g.name));
  });
  test("default open group: first group with missing items, or Track & Reconcile; seeded once per mode", () => {
    nf.resetNavModeForTests();
    const groups = [{ name: "Plan Status" }, { name: "Taxes" }, { name: "Track & Reconcile" }];
    const missing = (g) => (g.name === "Taxes" ? 2 : 0);
    assert.equal(nf.defaultOpenGroup(groups, "setup", missing), "Taxes");
    assert.equal(nf.defaultOpenGroup(groups, "maintain", missing), "Track & Reconcile");
    const open = new Set();
    nf.seedOpenGroup(open, groups, "setup", missing, false);
    assert.equal(open.size, 0, "nothing is seeded before a plan is loaded");
    nf.seedOpenGroup(open, groups, "setup", missing, true);
    assert.ok(open.has("Taxes"));
    open.delete("Taxes");
    nf.seedOpenGroup(open, groups, "setup", missing, true);
    assert.equal(open.size, 0, "a group the user closed stays closed");
  });
  test("progress text and the Maintain chain", () => {
    assert.deepEqual(nf.progressTexts("setup", 40, 3, true), { progress: "40% complete", required: "3 required missing" });
    assert.equal(nf.progressTexts("maintain", 90, 2, true).progress, "2 need attention");
    assert.equal(nf.progressTexts("maintain", 100, 0, true).progress, "All caught up");
    assert.equal(nf.maintainNext("actual_spending"), "monarch_reconciliation");
    assert.equal(nf.maintainNext("sales_ledger"), "reports_and_review");
  });
});

describe("Features popover data", () => {
  test("rows land under the host page's group and split into Not enabled / Enabled", () => {
    const d = nf.groupFeatures("Taxes", deps(new Set(["roth_conversion_plan"])));
    assert.deepEqual(d.on.map((f) => f.key), ["roth_conversion_plan"]);
    assert.deepEqual(d.off.map((f) => f.key).sort(), ["charitable_giving", "daf_giving", "lifetime_tax_projection", "qcd_giving"]);
    assert.equal(d.offCount, 4);
  });
  test("a topic tag comes from the catalog domain; a feature with no inputs is a workbook sheet", () => {
    const d = nf.groupFeatures("Taxes", deps(new Set()));
    const lt = d.off.find((f) => f.key === "lifetime_tax_projection");
    assert.equal(lt.kind, "sheet");
    assert.equal(lt.adds, "Adds a workbook sheet");
    assert.equal(lt.tag, "Taxes");
    const hsa = nf.groupFeatures("Analyze", deps(new Set())).off.find((f) => f.key === "hsa_drawdown");
    assert.equal(hsa.adds, "Adds a section to Optimize");
  });
  test("a bundle child and an any-of page have no switch and say what they follow", () => {
    const tax = nf.groupFeatures("Taxes", deps(new Set())).off.find((f) => f.key === "charitable_giving");
    assert.equal(tax.hasSwitch, false);
    assert.deepEqual(tax.follows, ["DAF Giving", "QCD Giving"]);
    const child = nf.groupFeatures("Track & Reconcile", deps(new Set())).off.find((f) => f.key === "spending_summary");
    assert.equal(child.hasSwitch, false);
    assert.deepEqual(child.follows, ["Spending Tracker / YTD"]);
  });
  test("always-on lists ungated pages and sections, never a gated page or an always-on workbook sheet", () => {
    const d = nf.groupFeatures("Analyze", deps(new Set()));
    const names = d.always.map((a) => a.name);
    assert.ok(names.includes("Optimize") && names.includes("Asset Allocation"));
    assert.ok(!names.includes("Stress Test"), "Stress Test is gated by its sections");
    assert.ok(![...d.on, ...d.off].map((f) => f.key).includes("net_worth"));
    assert.deepEqual(nf.groupFeatures("Taxes", deps(new Set())).always.map((a) => a.name), ["Account Tax Basis"]);
  });
  test("a group with nothing toggleable gets no icon", () => {
    assert.equal(nf.iconHtml("Settings", nf.groupFeatures("Settings", deps(new Set())), false), "");
  });
});

describe("Features popover markup", () => {
  const data = nf.groupFeatures("Taxes", deps(new Set(["roth_conversion_plan"])));
  test("icon is a labelled button with the off count in its label", () => {
    const html = nf.iconHtml("Taxes", data, false);
    assert.match(html, /aria-haspopup="dialog"/);
    assert.match(html, /aria-expanded="false"/);
    assert.match(html, /aria-label="Manage features in Taxes, 4 off"/);
  });
  test("three sections in order; switches are role=switch; sheets collapse; any-of page has no switch", () => {
    const html = nf.popoverHtml("Taxes", data, { planOpen: true });
    const order = ["Not enabled", "Enabled", "Always on"].map((t) => html.indexOf(`<h3>${t}</h3>`));
    assert.ok(order.every((i) => i >= 0));
    assert.deepEqual([...order].sort((a, b) => a - b), order);
    assert.match(html, /role="switch" class="nf-switch on" aria-checked="true" aria-label="Roth Conversion"/);
    assert.match(html, /<summary>Workbook sheets \(1\)<\/summary>/);
    assert.match(html, /Follows DAF Giving or QCD Giving/);
    assert.match(html, /data-nf-open="optional_functions"/);
  });
  test("switches are disabled until a plan is open", () => {
    assert.match(nf.popoverHtml("Taxes", data, { planOpen: false }), /class="nf-switch[^"]*"[^>]* disabled/);
  });
  test("niche rows sit under a collapsed More", () => {
    const d = nf.groupFeatures("Analyze", { ...deps(new Set()), taxonomy: { modules: { divorce_qdro: TAXONOMY.modules.divorce_qdro } } });
    // divorce_qdro is hosted by Stress Test, which is an Analyze page.
    assert.match(nf.popoverHtml("Analyze", d, {}), /<summary>More \(1\)<\/summary>/);
  });
});

describe("shared setter", () => {
  test("the popover writes through setPlanFeatureSwitch, the writer Plan Features uses", () => {
    const src = fs.readFileSync("frontend/js/dashboard_decomp_nav_features.js", "utf8");
    assert.match(src, /window\.setPlanFeatureSwitch\(key, turnOn\)/);
    assert.doesNotMatch(src, /api\(["']\/api\/plan\/feature/, "no second writer");
  });
});
