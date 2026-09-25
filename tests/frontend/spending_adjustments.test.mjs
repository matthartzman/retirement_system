// #335 (spec §5): the Spending Model Adjustments table.

import { test, describe, beforeEach } from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();
const run = (code) => vm.runInContext(code, sandbox);

const FLAT = {
  dining: { id: "dining", label: "Dining", tracking_type: "Core Expenses", status: "active" },
  utilities: { id: "utilities", label: "Utilities", tracking_type: "Housing", status: "active" },
  home_aide: { id: "home_aide", label: "Home Aide", tracking_type: "Wellness", status: "active" },
  hotels: { id: "hotels", label: "Hotels", tracking_type: "Travel", status: "active" },
  weddings: { id: "weddings", label: "Weddings", tracking_type: "Large Discretionary", status: "active" },
  fed_tax: { id: "fed_tax", label: "Federal Tax", tracking_type: "Taxes", status: "active" },
  biz: { id: "biz", label: "Biz Services", tracking_type: "Business", status: "active" },
};

let posted = null;

beforeEach(() => {
  posted = null;
  sandbox.__flat = FLAT;
  run(`taxonomyFlat = globalThis.__flat; taxonomyData = [];
       spendingModelData = { tracking_types: [] }; taxBudgetLoaded = true; budgetLinesLoaded = true;
       spendingModelLoading = false; spendingModelError = ""; searchText = ""; rows = [];`);
  sandbox.resetSpendingAdjustments();
  run("spendingAdjustmentsLoaded = true;");
  for (const fn of ["noteSpecialSessionChange", "updateUnsaved", "setAppControls", "scheduleStatusUpdate", "renderMain"])
    sandbox[fn] = () => {};
  sandbox.showInAppConfirm = async () => true;
  sandbox.api = async (url, opts) => {
    if (opts && opts.method === "POST") posted = { url, body: JSON.parse(opts.body) };
    return { success: true };
  };
});

function selectOptions(html) {
  const select = html.match(/<select[^>]*updateSpendingAdjustment[^>]*>(.*?)<\/select>/)[1];
  return [...select.matchAll(/<option value="([^"]*)"[^>]*>([^<]*)<\/option>/g)].map((m) => [m[1], m[2]]);
}

describe("Spending Adjustments table (#335)", () => {
  test("pulldown = active Core/Housing/Wellness/Travel categories + four All options", () => {
    sandbox.addSpendingAdjustment();
    const opts = selectOptions(sandbox.renderSpendingAdjustmentsTable());
    assert.deepEqual(opts, [
      ["ALL:Core Expenses", "All Core Expenses"], ["dining", "Dining"],
      ["ALL:Housing", "All Housing"], ["utilities", "Utilities"],
      ["ALL:Wellness", "All Wellness"], ["home_aide", "Home Aide"],
      ["ALL:Travel", "All Travel"], ["hotels", "Hotels"],
    ]);
    for (const excluded of ["weddings", "fed_tax", "biz", "ALL:Large Discretionary", "ALL:Taxes", "ALL:Business"])
      assert.ok(!opts.some(([v]) => v === excluded), excluded);
  });

  test("add / edit / delete post the adj rows list on save", async () => {
    sandbox.addSpendingAdjustment();
    sandbox.addSpendingAdjustment();
    sandbox.updateSpendingAdjustment(0, "category", "dining");
    sandbox.updateSpendingAdjustment(0, "start_year", "2035");
    sandbox.updateSpendingAdjustment(0, "change_pct", "-20");
    sandbox.updateSpendingAdjustment(1, "category", "hotels");
    assert.equal(sandbox.spendingAdjustmentsDirty(), true);
    assert.equal(sandbox.hasUnsavedPlanChanges(), true);
    await sandbox.deleteSpendingAdjustment(1);
    await sandbox.saveSpendingAdjustments(false);
    assert.equal(posted.url, "/api/spending-adjustments");
    assert.deepEqual(JSON.parse(JSON.stringify(posted.body.adjustments)), [
      { category: "dining", start_year: "2035", end_year: "", change_pct: "-20" },
    ]);
    assert.equal(sandbox.spendingAdjustmentsDirty(), false);
  });

  test("helper text shows the compounded result", () => {
    const adjs = [
      { category: "dining", start_year: "2035", end_year: "", change_pct: "-20" },
      { category: "dining", start_year: "2042", end_year: "", change_pct: "-10" },
      { category: "ALL:Travel", start_year: "2038", end_year: "2040", change_pct: "-50" },
    ];
    assert.equal(sandbox.spendingAdjustmentResultText(adjs, 1, FLAT), "72% of today's level from 2042");
    assert.equal(sandbox.spendingAdjustmentResultText(adjs, 2, FLAT), "50% of today's level from 2038; back to 100% after 2040");
    assert.equal(Math.round(sandbox.adjustmentFactor(adjs, "hotels", "Travel", 2039) * 100), 50);
  });

  test("the Adjustments accordion follows the tracking-type accordions", () => {
    sandbox.__model = { tracking_types: [{ tracking_type: "Core Expenses", groups: [] }, { tracking_type: "Travel", groups: [] }] };
    run("spendingModelData = globalThis.__model; taxonomyData = globalThis.__model.tracking_types;");
    const html = sandbox.renderDomainBudgetTable("core");
    const adj = html.indexOf('data-dkey="budget:core:adjustments"');
    assert.ok(adj > html.indexOf('data-dkey="budget:core:Travel"'));
    assert.match(html.slice(adj), /<summary><b>Adjustments<\/b>/);
  });
});
