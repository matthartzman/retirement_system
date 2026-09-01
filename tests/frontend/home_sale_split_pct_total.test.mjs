// Ticket 299: home sale split percentage rows must sum to 100% before save
// (enforced both client-side, in saveWorkingCopy(), and server-side, in
// save_home_sale_splits_payload). homeSaleSplitPctTotal() is the shared
// running total both the inline warning and the pre-save guard read from.

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();

describe("homeSaleSplitPctTotal (ticket 299)", () => {
  test("sums percentage strings, ignoring a trailing % sign", () => {
    sandbox.window.homeSaleSplits = [
      { account: "Joint_Trust", percentage: "60%" },
      { account: "Family_Checking", percentage: "40%" },
    ];
    assert.equal(sandbox.homeSaleSplitPctTotal(), 100);
  });

  test("reports a short total when rows don't yet sum to 100", () => {
    sandbox.window.homeSaleSplits = [
      { account: "Joint_Trust", percentage: "60" },
      { account: "Family_Checking", percentage: "30" },
    ];
    assert.equal(sandbox.homeSaleSplitPctTotal(), 90);
  });

  test("treats a blank/unparsable percentage as zero rather than throwing", () => {
    sandbox.window.homeSaleSplits = [
      { account: "Joint_Trust", percentage: "" },
      { account: "Family_Checking", percentage: "40" },
    ];
    assert.equal(sandbox.homeSaleSplitPctTotal(), 40);
  });

  test("empty split list totals zero", () => {
    sandbox.window.homeSaleSplits = [];
    assert.equal(sandbox.homeSaleSplitPctTotal(), 0);
  });
});
