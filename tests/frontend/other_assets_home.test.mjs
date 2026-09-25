// #338 W-E (Task E3), design 2026-09-24 §6: home value and the mortgage
// balance are always in effect, so they live on Other Assets and Liabilities
// as a "Primary home" group -- regardless of the Next Housing Move switch.
// HELOC keeps its own plan-flag gating and moves to Investments & Property.

import { test, describe, beforeEach } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();

const HOME_VALUE = { row_index: 25, section: "Other Assets", subsection: "Home", label: "value_as_of_plan_start", value: "800000" };
const HOME_BASIS = { row_index: 27, section: "Other Assets", subsection: "Home", label: "home_basis", value: "300000" };
const MORTGAGE = { row_index: 26, section: "Cashflow", subsection: "mortgage", label: "balance_as_of_plan_start", value: "200000" };
const HOUSING_ROWS = [
  HOME_VALUE, HOME_BASIS, MORTGAGE,
  { row_index: 20, section: "Other Assets", subsection: "Home", label: "home_sale_year", value: "2040" },
];

function renderWithToggle(value) {
  sandbox.window.rows = [
    { row_index: 1, section: "Optional Functions", subsection: "", label: "housing_location_search", value },
    ...HOUSING_ROWS,
  ];
  return sandbox.renderAssetsSpecial();
}

beforeEach(() => {
  sandbox.window.dirty = new Map();
  sandbox.window.searchText = "";
  sandbox.rowsForStep = (id) => (id === "spending_mortgage_events" ? HOUSING_ROWS : []);
});

describe("Other Assets and Liabilities: Primary home", () => {
  test("renders a Primary home group with home value and mortgage balance", () => {
    const html = renderWithToggle("YES");
    const start = html.indexOf("<summary>Primary home</summary>");
    assert.ok(start >= 0, "Primary home group missing");
    const group = html.slice(start, html.indexOf("</details>", start));
    assert.ok(group.includes('data-row="25"'), "home value input");
    assert.ok(group.includes('data-row="26"'), "mortgage balance input");
    assert.ok(!group.includes('data-row="20"'), "home sale belongs to Next Housing Move");
  });

  test("stays in effect with Next Housing Move off", () => {
    const html = renderWithToggle("NO");
    assert.ok(html.includes("<summary>Primary home</summary>"));
    assert.ok(html.includes('data-row="25"'));
    assert.ok(html.includes('data-row="26"'));
  });

  test("sourceStepForRow sends home value and mortgage balance to Other Assets", () => {
    for (const r of [HOME_VALUE, HOME_BASIS, MORTGAGE])
      assert.equal(sandbox.sourceStepForRow(r), "assets_special", r.label);
  });
});

describe("HELOC nav group", () => {
  test('heloc_strategy.group === "Investments & Property"', () => {
    const src = fs.readFileSync("frontend/js/dashboard.js", "utf8");
    const entry = /id: "heloc_strategy",\s*group: "([^"]+)"/.exec(src);
    assert.ok(entry, "heloc_strategy STEPS entry not found");
    assert.equal(entry[1], "Investments & Property");
  });
});
