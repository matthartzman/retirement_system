// Projection Controls section (after Spending Categories) and Category Manager
// tracking-type order.

import { test, describe, beforeEach } from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();
const run = (code) => vm.runInContext(code, sandbox);

const row = (i, section, subsection, label, value) => ({
  row_index: i, section, subsection, label, value, type: "text", editable: "TRUE", is_header: false, is_comment: false,
});

function seed({ withRows }) {
  sandbox.__rows = withRows
    ? [
        row(1, "Cashflow", "Spending", "core_spending_growth_mode", "cpi"),
        row(2, "Cashflow", "Spending", "annual_spending_base_year", "185000"),
        row(3, "Model Constants", "Retirement", "spending_freeze_year", "2040"),
        row(4, "Economic Assumptions", "", "inflation_general", "2.50%"),
      ]
    : [];
  run(`rows = globalThis.__rows; searchText = ""; spendingModelData = { tracking_types: [] };
       taxonomyData = [{tracking_type:"Business",groups:[]},{tracking_type:"Taxes",groups:[]},{tracking_type:"Core Expenses",groups:[]},{tracking_type:"Income",groups:[]},{tracking_type:"Travel",groups:[]}];
       taxBudgetLoaded = true; budgetLinesLoaded = true; spendingModelLoading = false; spendingModelError = "";`);
  sandbox.resetSpendingAdjustments();
  run("spendingAdjustmentsLoaded = true;");
}

beforeEach(() => {
  for (const fn of ["noteSpecialSessionChange", "updateUnsaved", "setAppControls", "scheduleStatusUpdate", "renderMain"])
    sandbox[fn] = () => {};
});

describe("Projection Controls section", () => {
  test("page order is Spending Categories, Projection Controls, Category Manager", () => {
    seed({ withRows: true });
    const page = sandbox.renderCoreSpendingUnified();
    const total = page.indexOf("Spending Categories total");
    const pc = page.indexOf('data-dkey="budget:core:projection_controls"');
    const mgr = page.indexOf("Category Manager");
    assert.ok(total >= 0 && pc > total && mgr > pc, `${total} < ${pc} < ${mgr}`);
    assert.doesNotMatch(page.slice(0, total), /Projection controls:/);
  });

  test("collapsed by default, with a compact readout of the current inputs", () => {
    seed({ withRows: true });
    const page = sandbox.renderCoreSpendingUnified();
    const tag = page.match(/<details class="taxonomy-type-section projection-controls"[^>]*>/)[0];
    assert.doesNotMatch(tag, /\bopen\b/);
    const summary = page.match(/<details class="taxonomy-type-section projection-controls"[^>]*><summary>(.*?)<\/summary>/s)[1];
    assert.match(summary, /Projection Controls/);
    assert.match(summary, /Increase method<\/b> General CPI/);
    assert.match(summary, /Rate<\/b> 2\.50%/);
    assert.match(summary, /Increases stop<\/b> 2040/);
    assert.match(summary, /Adjustments<\/b> 0 step changes/);
  });

  test("Adjustments sits inside the section and is not itself collapsible", () => {
    seed({ withRows: true });
    const page = sandbox.renderCoreSpendingUnified();
    const pc = page.indexOf('data-dkey="budget:core:projection_controls"');
    const body = page.slice(pc, page.indexOf("Category Manager"));
    assert.match(body, /<h4 class="group-title">Adjustments/);
    assert.doesNotMatch(body, /<details[^>]*spending-adjustments/);
  });

  test("opens by itself when a control is missing", () => {
    seed({ withRows: false });
    const page = sandbox.renderCoreSpendingUnified();
    assert.match(page, /<details class="taxonomy-type-section projection-controls"[^>]*\bopen\b/);
    assert.match(page, /Core spending controls are being created/);
  });

  test("an edited input shows the Unsaved tag", () => {
    seed({ withRows: true });
    assert.doesNotMatch(sandbox.renderCoreSpendingUnified(), /pc-unsaved/);
    run(`dirty.set(3, "2045")`);
    assert.match(sandbox.renderCoreSpendingUnified(), /pc-unsaved/);
    run(`dirty.clear()`);
  });
});

describe("Category Manager tracking-type order", () => {
  test("matches Spending Categories order, unknown types last", () => {
    seed({ withRows: true });
    const mgr = sandbox.renderTaxonomyManager();
    const order = [...mgr.matchAll(/<details class="taxonomy-type-section"><summary><b>([^<]+)<\/b>/g)].map((m) => m[1]);
    assert.deepEqual(order, ["Core Expenses", "Travel", "Taxes", "Business", "Income"]);
  });
});
