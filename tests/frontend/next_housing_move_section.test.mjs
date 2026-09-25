// #338 W-E (Task E2), design 2026-09-24 §6: every housing PLAN input -- home
// sale, next housing steps 1 & 2, state residency over time, and the "where
// to live" ZIP search -- lives in Strategy -> Optimize -> Next Housing Move.
// Off, the section lists what is kept but not applied, links to Plan
// Features, and offers no inline switch (the only one is on Plan Features).

import { test, describe, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();
const KEY = "housing_location_search";

const HOUSING_ROWS = [
  { row_index: 20, section: "Other Assets", subsection: "Home", label: "home_sale_year", value: "2040" },
  { row_index: 21, section: "Other Assets", subsection: "Home", label: "home_sale_price", value: "900000" },
  { row_index: 22, section: "Housing", subsection: "next_step_1", label: "start_year", value: "2040" },
  { row_index: 23, section: "Housing", subsection: "next_step_1", label: "type", value: "rent" },
  { row_index: 24, section: "Housing", subsection: "next_step_2", label: "start_year", value: "" },
  { row_index: 25, section: "Other Assets", subsection: "Home", label: "value_as_of_plan_start", value: "800000" },
  { row_index: 26, section: "Cashflow", subsection: "mortgage", label: "balance_as_of_plan_start", value: "200000" },
];

function toggle(value) {
  return { row_index: 1, section: "Optional Functions", subsection: "", label: KEY, value };
}

// renderStrategyScreen() is stubbed to hand back the descriptors, so the
// test reads the real Optimize section list without building every section.
function housingDescriptor() {
  const real = sandbox.renderStrategyScreen;
  sandbox.renderStrategyScreen = (sections) => sections;
  try {
    return sandbox.renderStrategyOptimize().find((s) => s.key === "housing");
  } finally {
    sandbox.renderStrategyScreen = real;
  }
}

beforeEach(() => {
  sandbox.window.rows = [toggle("YES"), ...HOUSING_ROWS];
  sandbox.window.dirty = new Map();
  sandbox.window.searchText = "";
  sandbox.window.residencySchedule = [{ state: "Florida", start_year: "2040", end_year: "" }];
  sandbox.window.homeSaleSplits = [];
  sandbox.window.moduleGates = { step_gates: { [KEY]: KEY }, section_gates: {}, flag_gates: {} };
  sandbox.window.moduleTaxonomy = {
    modules: { [KEY]: { name: "Next Housing Move", gate_kind: "module_toggle" } },
  };
  sandbox.rowsForStep = (id) => (id === "spending_mortgage_events" ? HOUSING_ROWS : []);
  sandbox.renderHousingOptimizePanelHtml = () => "<div id='housingOptPanel'>zip search</div>";
});

describe("the Next Housing Move section holds the housing plan inputs", () => {
  test("home sale, next steps 1-2, residency and the ZIP search render in the section", () => {
    const s = housingDescriptor();
    assert.equal(s.title, "Next Housing Move");
    assert.equal(s.gate, KEY);
    const html = s.body();
    assert.ok(html.includes("Home Sale"), "home sale block");
    assert.ok(html.includes('data-row="20"'), "home_sale_year field");
    assert.ok(html.includes("Next Housing Step 1"), "next step 1");
    assert.ok(html.includes("Next Housing Step 2"), "next step 2");
    assert.ok(html.includes('data-dkey="housing:residency"'), "state over time");
    assert.ok(html.includes("Florida"));
    assert.ok(html.includes("housingOptPanel"), "the where-to-live ZIP search");
    // Home value and the mortgage balance are NOT here (Other Assets owns them).
    assert.ok(!html.includes('data-row="25"'));
    assert.ok(!html.includes('data-row="26"'));
  });

  test("sourceStepForRow sends these rows to strategy_optimize", () => {
    for (const r of HOUSING_ROWS.slice(0, 5))
      assert.equal(sandbox.sourceStepForRow(r), "strategy_optimize", r.label);
  });

  test("Spending Model's Housing accordion no longer renders them", () => {
    const tail = sandbox.spendingSourceTailHtml("Housing");
    assert.ok(!tail.includes('data-row="20"'));
    assert.ok(!tail.includes("housing:residency"));
    assert.ok(tail.includes("Next Housing Move"));
  });
});

describe("off-state", () => {
  beforeEach(() => {
    sandbox.window.rows = [toggle("NO"), ...HOUSING_ROWS];
  });

  test("the note counts the saved fields, lists them muted, and links to Plan Features", () => {
    const s = housingDescriptor();
    let built = 0;
    const html = sandbox.strategySection(
      s.key, s.title, () => { built += 1; return s.body(); }, s.gate, true, s.offBody,
    );
    assert.equal(built, 0, "the body must not be built while off");
    // home_sale_year, home_sale_price, step 1 start_year, step 1 type, one residency period.
    assert.ok(
      html.includes(
        "Off — 5 saved fields not applied: the plan assumes you stay in your current home and state.",
      ),
      html,
    );
    assert.ok(html.includes("Open Plan Features"));
    assert.ok(html.includes("setStep('optional_functions')"));
    assert.ok(html.includes('class="small next-housing-saved"'), "values listed muted");
    assert.ok(html.includes("Florida from 2040"));
    assert.ok(html.includes("900000"));
    // No inline switch: the only switch lives on Plan Features.
    assert.ok(!html.includes("editValue("), "no inline switch");
    assert.ok(!html.includes("Turn on"));
    assert.ok(!html.includes("housingOptPanel"));
  });
});
