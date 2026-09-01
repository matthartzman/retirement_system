// Ticket 298: utilities/maintenance/insurance estimates on a Next Housing
// Step must be re-estimated when the home value (purchase_price) or rent
// (monthly_rent) changes -- they used to stay stale forever once entered.
//
// reestimateHousingCostsOnValueChange() scales the sibling utilities/
// maintenance/insurance rows by the same ratio the value/rent itself moved,
// rather than re-fetching state defaults (that endpoint would overwrite the
// price/rent the user just typed with a state lookup value).

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();

function rowsForStep1Purchase() {
  return [
    { row_index: 10, section: "Housing", subsection: "next_step_1", label: "purchase_price", value: "400000" },
    { row_index: 11, section: "Housing", subsection: "next_step_1", label: "insurance_annual", value: "2000" },
    { row_index: 12, section: "Housing", subsection: "next_step_1", label: "utilities_annual", value: "3000" },
    { row_index: 13, section: "Housing", subsection: "next_step_1", label: "maintenance_annual", value: "4000" },
  ];
}

function withStubs(rows, fn) {
  // dashboard.js declares `let rows` and bridges it onto window with a real
  // get/set accessor (Object.defineProperty(window, "rows", {...})) for
  // cross-module access -- but the sandbox's `window` is a separate stub
  // object from the vm context itself, so only sandbox.window.rows = ...
  // actually reaches the internal binding every top-level function shares;
  // sandbox.rows = ... would silently no-op (rows is `let`, not `var`, so it
  // never became a vm-context-global property in the first place).
  sandbox.window.rows = rows;
  sandbox.dirty = new Map();
  const calls = [];
  sandbox.editValue = (idx, val) => {
    calls.push([idx, val]);
    const r = rows.find((x) => x.row_index === idx);
    if (r) r.value = String(val);
  };
  fn(rows, calls);
}

describe("reestimateHousingCostsOnValueChange (ticket 298)", () => {
  test("scales insurance/utilities/maintenance when purchase_price doubles", () => {
    withStubs(rowsForStep1Purchase(), (rows, calls) => {
      const priceRow = rows[0];
      const adjusted = sandbox.reestimateHousingCostsOnValueChange(priceRow, "400000", "800000");
      assert.equal(adjusted, 3);
      const byIdx = Object.fromEntries(calls);
      assert.equal(byIdx[11], "4000"); // insurance 2000 -> 4000
      assert.equal(byIdx[12], "6000"); // utilities 3000 -> 6000
      assert.equal(byIdx[13], "8000"); // maintenance 4000 -> 8000
    });
  });

  test("rent step only rescales insurance/utilities, not maintenance", () => {
    const rentRows = [
      { row_index: 20, section: "Housing", subsection: "next_step_2", label: "monthly_rent", value: "2000" },
      { row_index: 21, section: "Housing", subsection: "next_step_2", label: "insurance_annual", value: "300" },
      { row_index: 22, section: "Housing", subsection: "next_step_2", label: "utilities_annual", value: "2400" },
    ];
    withStubs(rentRows, (rows, calls) => {
      const rentRow = rows[0];
      const adjusted = sandbox.reestimateHousingCostsOnValueChange(rentRow, "2000", "3000");
      assert.equal(adjusted, 2);
      const byIdx = Object.fromEntries(calls);
      assert.equal(byIdx[21], "450"); // insurance scales 1.5x
      assert.equal(byIdx[22], "3600"); // utilities scales 1.5x
    });
  });

  test("does nothing for fields other than purchase_price/monthly_rent", () => {
    withStubs(rowsForStep1Purchase(), (rows, calls) => {
      const insuranceRow = rows[1];
      const adjusted = sandbox.reestimateHousingCostsOnValueChange(insuranceRow, "2000", "2500");
      assert.equal(adjusted, 0);
      assert.equal(calls.length, 0);
    });
  });

  test("does nothing outside the Housing/next_step_N shape", () => {
    withStubs(rowsForStep1Purchase(), (rows, calls) => {
      const otherRow = { row_index: 99, section: "Other Assets", subsection: "Home", label: "purchase_price", value: "400000" };
      const adjusted = sandbox.reestimateHousingCostsOnValueChange(otherRow, "400000", "800000");
      assert.equal(adjusted, 0);
      assert.equal(calls.length, 0);
    });
  });

  test("does nothing when the old value is zero or unparsable", () => {
    withStubs(rowsForStep1Purchase(), (rows, calls) => {
      const priceRow = rows[0];
      assert.equal(sandbox.reestimateHousingCostsOnValueChange(priceRow, "0", "800000"), 0);
      assert.equal(sandbox.reestimateHousingCostsOnValueChange(priceRow, "400000", "400000"), 0);
      assert.equal(calls.length, 0);
    });
  });
});
