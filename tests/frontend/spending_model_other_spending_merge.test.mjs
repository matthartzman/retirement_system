// "Other Spending" no longer has its own workspace tab -- its content
// (Travel/Large Items, renderLifestyleSpending()) is folded directly into
// the Spending Model tab's own output instead of living beside it.

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

describe("STRATEGY_TABS.spending_core no longer lists Other Spending", () => {
  // #338 W-C: Withdrawal Order moved to Optimize (C4) and Actual Spending /
  // Spending Analysis to the Actual Spending step (C5), so Spending Model is
  // no longer a tabbed workspace at all.
  test("Spending Model has no tab strip left", () => {
    const sandbox = loadDashboardSandbox();
    assert.equal(sandbox.window.STRATEGY_TABS.spending_core, undefined);
  });
});

describe("renderCoreSpendingUnified includes the former Other Spending content", () => {
  test("output contains the Large Items accordion", () => {
    const sandbox = loadDashboardSandbox();
    sandbox.window.rows = [];
    sandbox.window.spendingModelData = null;
    const out = sandbox.renderCoreSpendingUnified();
    assert.match(out, /class="lifestyle-workspace"/);
    assert.match(out, /<summary>Large Items<\/summary>/);
  });

  // #338 W-C: Travel is edited in its own Spending Model tracking-type
  // accordion now; a second Travel editor here would be a duplicate.
  test("does not repeat Travel -- it has its own tracking-type accordion", () => {
    const sandbox = loadDashboardSandbox();
    sandbox.window.rows = [];
    sandbox.window.spendingModelData = null;
    assert.doesNotMatch(sandbox.renderCoreSpendingUnified(), /<summary>Travel<\/summary>/);
  });
});
