// #338 W-C task C2: Spending Model is the single read/write surface for every
// spending Tracking Type -- one accordion per type, in planning order, with
// Housing / Wellness / Travel editable in place instead of the old
// "read-only reference -- budgeted on its source page" mirror.

import { test, describe, beforeEach } from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();
const run = (code) => vm.runInContext(code, sandbox);

const ORDER = ["Core Expenses", "Housing", "Wellness", "Travel", "Large Discretionary", "Taxes", "Business"];

// The rows the old Housing page rendered as Current-home cost fields, plus
// the ones that stay housing PLAN inputs (balance, home value).
const HOUSING_ROWS = [
  { row_index: 11, section: "Cashflow", subsection: "Mortgage", label: "monthly_payment", value: "$2,750" },
  { row_index: 12, section: "Cashflow", subsection: "Mortgage", label: "interest_rate", value: "3.25%" },
  { row_index: 13, section: "Cashflow", subsection: "Mortgage", label: "last_payment_year", value: "2038" },
  { row_index: 14, section: "Cashflow", subsection: "Mortgage", label: "balance_as_of_plan_start", value: "$412,500" },
  { row_index: 15, section: "Cashflow", subsection: "Mortgage", label: "annual_real_estate_taxes", value: "$14,500" },
  { row_index: 16, section: "Housing", subsection: "current_home", label: "utilities_annual", value: "$6,600" },
  { row_index: 17, section: "Other Assets", subsection: "Home", label: "home_value", value: "$900,000" },
];
const HOUSING_COST_ROW_INDEXES = [11, 12, 13];

function trackingType(tt) {
  return { tracking_type: tt, groups: [{ group: tt + " Group", categories: [{ id: tt.toLowerCase().replace(/ /g, "_") + "_cat", label: tt + " Cat" }] }] };
}

beforeEach(() => {
  // Backend order (src/spending_tracker.py TRACKING_TYPE_ORDER) puts
  // Wellness and Housing last -- the accordion must not follow it.
  const backendOrder = ["Core Expenses", "Taxes", "Travel", "Large Discretionary", "Business", "Wellness", "Housing"];
  sandbox.__model = { tracking_types: backendOrder.map(trackingType) };
  run(`spendingModelData = globalThis.__model; taxonomyData = globalThis.__model.tracking_types;
       taxBudgetLoaded = true; budgetLinesLoaded = true; spendingModelLoading = false; spendingModelError = "";
       searchText = ""; rows = globalThis.__rows || [];`);
  sandbox.rowsForStep = (id) => (id === "spending_mortgage_events" ? HOUSING_ROWS : []);
  sandbox.housingPlanSectionsHtml = () => "";
});

function accordionTitles(html) {
  return [...html.matchAll(/class="taxonomy-type-section" data-dkey="budget:core:([^"]+)"/g)].map((m) => m[1]);
}

function accordionBody(html, tt) {
  const start = html.indexOf(`data-dkey="budget:core:${tt}"`);
  assert.ok(start >= 0, `${tt} accordion missing`);
  const next = html.indexOf('class="taxonomy-type-section"', start + 1);
  return html.slice(start, next < 0 ? undefined : next);
}

describe("Spending Model accordions (#338 C2)", () => {
  test("TRACKING_TYPE_ORDER is the planning order", () => {
    assert.deepEqual([...run("TRACKING_TYPE_ORDER")], ORDER);
  });

  test("accordion headers render in TRACKING_TYPE_ORDER, not backend order", () => {
    assert.deepEqual(accordionTitles(sandbox.renderDomainBudgetTable("core")), ORDER);
  });

  test("Housing body holds editable inputs for exactly the old page's cost rows", () => {
    const body = accordionBody(sandbox.renderDomainBudgetTable("core"), "Housing");
    const fieldRows = [...body.matchAll(/data-row="(\d+)"/g)].map((m) => Number(m[1]));
    assert.deepEqual([...new Set(fieldRows)].sort((a, b) => a - b), HOUSING_COST_ROW_INDEXES);
    assert.match(body, /<input/);
  });

  test("Housing, Wellness and Travel budget inputs are not disabled", () => {
    const html = sandbox.renderDomainBudgetTable("core");
    for (const tt of ["Housing", "Wellness", "Travel"]) {
      const body = accordionBody(html, tt);
      assert.match(body, /class="budget-money-input"/, `${tt} has no budget input`);
      assert.doesNotMatch(body, /disabled type="text" class="budget-money-input"/, `${tt} budget input is disabled`);
    }
  });

  test("no read-only reference copy remains", () => {
    const html = sandbox.renderDomainBudgetTable("core");
    assert.doesNotMatch(html, /read-only reference/);
    assert.doesNotMatch(html, /budgeted on its source page/);
  });

  test("Travel keeps its group-number-wins note", () => {
    assert.match(accordionBody(sandbox.renderDomainBudgetTable("core"), "Travel"), /group number wins/);
  });
});

describe("housing cost rows are owned by Spending Model (#338 C2)", () => {
  test("rowIsHousingCost keeps costs, drops balance / taxes / budgeted costs / home value", () => {
    const cost = HOUSING_ROWS.filter((r) => sandbox.rowIsHousingCost(r)).map((r) => r.row_index);
    assert.deepEqual(cost, HOUSING_COST_ROW_INDEXES);
  });

  test("sourceStepForRow() for a housing-cost row returns spending_core", () => {
    sandbox.__rows = HOUSING_ROWS;
    run("rows = globalThis.__rows;");
    // Use the real rawRowsForStep (rowsForStep is stubbed only for renders).
    const row = HOUSING_ROWS[0];
    assert.equal(sandbox.sourceStepForRow(row), "spending_core");
    sandbox.__rows = [];
  });
});
