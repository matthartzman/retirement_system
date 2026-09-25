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

describe("renderCoreSpendingUnified no longer appends Other Spending", () => {
  // #336: Large Discretionary (the former "Large Items") has its own Spending
  // Model accordion; #338 W-C gave Travel one too. Neither is repeated below.
  test("no Large Items or Travel block after the accordions", () => {
    const sandbox = loadDashboardSandbox();
    sandbox.window.rows = [];
    sandbox.window.spendingModelData = null;
    const out = sandbox.renderCoreSpendingUnified();
    assert.doesNotMatch(out, /class="lifestyle-workspace"/);
    assert.doesNotMatch(out, /<summary>Large Items<\/summary>/);
    assert.doesNotMatch(out, /<summary>Travel<\/summary>/);
  });
});
