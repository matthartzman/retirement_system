// "Other Spending" no longer has its own workspace tab -- its content
// (Travel/Large Items, renderLifestyleSpending()) is folded directly into
// the Spending Model tab's own output instead of living beside it.

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

describe("STRATEGY_TABS.spending_core no longer lists Other Spending", () => {
  test("has exactly the four remaining tabs, in order", () => {
    const sandbox = loadDashboardSandbox();
    // Spread into a plain array first: STRATEGY_TABS.spending_core is a
    // native array of the vm sandbox's own realm, and assert/strict's
    // deepEqual treats cross-realm arrays as "same structure but not
    // reference-equal" even when every element matches -- not a real
    // difference, just a vm-context gotcha this loader's other tests avoid
    // by comparing primitives/strings rather than whole arrays.
    assert.deepEqual([...sandbox.window.STRATEGY_TABS.spending_core], [
      "Spending Model",
      "Actual Spending (YTD)",
      "Spending Analysis",
      "Withdrawal Order",
    ]);
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
