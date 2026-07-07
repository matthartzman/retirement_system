// Unit tests for allocation.mjs pure functions.
//
// These tests verify allocation calculation and formatting behavior independently
// from dashboard.js, following Phase B test modernization (conversion from
// source-text matching to behavior-based testing).
//
// Run with: node --test tests/frontend/allocation.test.mjs
//           or npm test (runs all frontend tests)

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import {
  computeAllocationDeviation,
  isDeviationAcceptable,
  formatAllocationPercent,
  computeTotalAllocation,
  validateAllocationPercentages,
  sortAllocationsBySize,
  generateAllocationLabels,
  compareAllocations,
} from "../../frontend/js/modules/allocation.mjs";

describe("computeAllocationDeviation", () => {
  test("computes actual minus target when target is non-zero", () => {
    assert.equal(computeAllocationDeviation(55, 50), 5);
    assert.equal(computeAllocationDeviation(45, 50), -5);
    assert.equal(computeAllocationDeviation(50, 50), 0);
  });

  test("returns actual as-is when target is zero", () => {
    assert.equal(computeAllocationDeviation(25, 0), 25);
    assert.equal(computeAllocationDeviation(0, 0), 0);
  });
});

describe("isDeviationAcceptable", () => {
  test("accepts deviations within tolerance (default 5%)", () => {
    assert.equal(isDeviationAcceptable(0), true);
    assert.equal(isDeviationAcceptable(3), true);
    assert.equal(isDeviationAcceptable(-3), true);
    assert.equal(isDeviationAcceptable(5), true);
    assert.equal(isDeviationAcceptable(-5), true);
  });

  test("rejects deviations outside tolerance", () => {
    assert.equal(isDeviationAcceptable(5.1), false);
    assert.equal(isDeviationAcceptable(-5.1), false);
    assert.equal(isDeviationAcceptable(10), false);
  });

  test("respects custom tolerance parameter", () => {
    assert.equal(isDeviationAcceptable(7, 10), true);
    assert.equal(isDeviationAcceptable(7, 5), false);
  });
});

describe("formatAllocationPercent", () => {
  test("formats number with default 1 decimal place", () => {
    assert.equal(formatAllocationPercent(50), "50.0%");
    assert.equal(formatAllocationPercent(33.456), "33.5%");
    assert.equal(formatAllocationPercent(0), "0.0%");
  });

  test("respects custom decimal places parameter", () => {
    assert.equal(formatAllocationPercent(33.456, 0), "33%");
    assert.equal(formatAllocationPercent(33.456, 2), "33.46%");
  });

  test("returns '—' for non-numbers", () => {
    assert.equal(formatAllocationPercent(null), "—");
    assert.equal(formatAllocationPercent(undefined), "—");
    assert.equal(formatAllocationPercent(NaN), "—");
  });
});

describe("computeTotalAllocation", () => {
  test("sums allocation percentages", () => {
    const allocs = { stocks: 60, bonds: 40 };
    assert.equal(computeTotalAllocation(allocs), 100);
  });

  test("returns 0 for invalid input", () => {
    assert.equal(computeTotalAllocation(null), 0);
    assert.equal(computeTotalAllocation(undefined), 0);
    assert.equal(computeTotalAllocation("not an object"), 0);
  });

  test("handles string values by parsing to float", () => {
    const allocs = { stocks: "60", bonds: "40" };
    assert.equal(computeTotalAllocation(allocs), 100);
  });

  test("treats NaN/non-numeric as 0", () => {
    const allocs = { stocks: 50, bonds: "invalid", cash: 50 };
    assert.equal(computeTotalAllocation(allocs), 100);
  });

  test("handles empty object", () => {
    assert.equal(computeTotalAllocation({}), 0);
  });
});

describe("validateAllocationPercentages", () => {
  test("accepts valid allocation totaling 100%", () => {
    const result = validateAllocationPercentages({ stocks: 60, bonds: 40 });
    assert.equal(result.valid, true);
    assert.equal(result.errors.length, 0);
  });

  test("accepts allocations with small rounding tolerance (≤0.1%)", () => {
    const result = validateAllocationPercentages({ stocks: 60.05, bonds: 39.95 });
    assert.equal(result.valid, true);
  });

  test("rejects allocations not totaling 100%", () => {
    const result = validateAllocationPercentages({ stocks: 60, bonds: 30 });
    assert.equal(result.valid, false);
    assert.ok(result.errors.some((e) => e.includes("Total allocation")));
  });

  test("rejects negative allocations", () => {
    const result = validateAllocationPercentages({ stocks: 110, bonds: -10 });
    assert.equal(result.valid, false);
    assert.ok(result.errors.some((e) => e.includes("negative")));
  });

  test("rejects allocations exceeding 100%", () => {
    const result = validateAllocationPercentages({ stocks: 110, bonds: 40 });
    assert.equal(result.valid, false);
    assert.ok(result.errors.some((e) => e.includes("exceeds 100%")));
  });

  test("rejects invalid allocations object", () => {
    const result = validateAllocationPercentages(null);
    assert.equal(result.valid, false);
    assert.ok(result.errors.some((e) => e.includes("Invalid allocations object")));
  });
});

describe("sortAllocationsBySize", () => {
  test("sorts allocations descending by percentage", () => {
    const allocs = { bonds: 30, stocks: 60, cash: 10 };
    const sorted = sortAllocationsBySize(allocs);
    assert.deepEqual(sorted, [
      ["stocks", 60],
      ["bonds", 30],
      ["cash", 10],
    ]);
  });

  test("handles string values by parsing to float", () => {
    const allocs = { bonds: "30", stocks: "60", cash: "10" };
    const sorted = sortAllocationsBySize(allocs);
    assert.deepEqual(sorted, [
      ["stocks", 60],
      ["bonds", 30],
      ["cash", 10],
    ]);
  });

  test("treats NaN/non-numeric as 0", () => {
    const allocs = { stocks: 100, bonds: "invalid" };
    const sorted = sortAllocationsBySize(allocs);
    assert.equal(sorted[0][0], "stocks");
    assert.equal(sorted[1][0], "bonds");
    assert.equal(sorted[1][1], 0);
  });

  test("returns empty array for invalid input", () => {
    assert.deepEqual(sortAllocationsBySize(null), []);
    assert.deepEqual(sortAllocationsBySize(undefined), []);
  });
});

describe("generateAllocationLabels", () => {
  test("generates labels with percentages for allocations >= minLabelPercent", () => {
    const allocs = { stocks: 60, bonds: 30, cash: 10 };
    const labels = generateAllocationLabels(allocs);
    assert.equal(labels.stocks, "stocks: 60.0%");
    assert.equal(labels.bonds, "bonds: 30.0%");
    assert.equal(labels.cash, "cash: 10.0%");
  });

  test("omits labels below minLabelPercent (default 5%)", () => {
    const allocs = { stocks: 96, bonds: 3, cash: 1 };
    const labels = generateAllocationLabels(allocs);
    assert.equal(labels.stocks, "stocks: 96.0%");
    assert.equal(labels.bonds, undefined);
    assert.equal(labels.cash, undefined);
  });

  test("respects custom minLabelPercent option", () => {
    const allocs = { stocks: 60, bonds: 30, cash: 10 };
    const labels = generateAllocationLabels(allocs, { minLabelPercent: 20 });
    assert.equal(labels.stocks, "stocks: 60.0%");
    assert.equal(labels.bonds, "bonds: 30.0%");
    assert.equal(labels.cash, undefined);
  });

  test("omits percentages when showPercent is false", () => {
    const allocs = { stocks: 60, bonds: 40 };
    const labels = generateAllocationLabels(allocs, { showPercent: false });
    assert.equal(labels.stocks, "stocks");
    assert.equal(labels.bonds, "bonds");
  });

  test("respects both showPercent and minLabelPercent together", () => {
    const allocs = { stocks: 60, bonds: 30, cash: 10 };
    const labels = generateAllocationLabels(allocs, {
      showPercent: false,
      minLabelPercent: 15,
    });
    assert.equal(labels.stocks, "stocks");
    assert.equal(labels.bonds, "bonds");
    assert.equal(labels.cash, undefined);
  });
});

describe("compareAllocations", () => {
  test("computes deviations for common asset classes", () => {
    const alloc1 = { stocks: 60, bonds: 40 };
    const alloc2 = { stocks: 65, bonds: 35 };
    const result = compareAllocations(alloc1, alloc2);

    assert.equal(result.deviations.stocks, 5);
    assert.equal(result.deviations.bonds, -5);
    assert.equal(result.largestDeviation, 5);
  });

  test("handles asset classes present only in one allocation", () => {
    const alloc1 = { stocks: 60, bonds: 40 };
    const alloc2 = { stocks: 50, bonds: 30, cash: 20 };
    const result = compareAllocations(alloc1, alloc2);

    assert.equal(result.deviations.stocks, -10);
    assert.equal(result.deviations.bonds, -10);
    assert.equal(result.deviations.cash, 20);
    assert.equal(result.largestDeviation, 20);
  });

  test("reports largest deviation by absolute value", () => {
    const alloc1 = { a: 20, b: 50, c: 30 };
    const alloc2 = { a: 10, b: 60, c: 30 };
    const result = compareAllocations(alloc1, alloc2);

    assert.equal(Math.abs(result.largestDeviation), 10);
    assert.equal(result.deviations.a, -10);
    assert.equal(result.deviations.b, 10);
  });

  test("validates both allocations", () => {
    const valid = { stocks: 60, bonds: 40 };
    const invalid = { stocks: 110, bonds: 30 };
    const result = compareAllocations(valid, invalid);

    assert.equal(result.allocationValid, false);
  });

  test("handles null/undefined allocations", () => {
    const result = compareAllocations(null, { stocks: 100 });
    assert.equal(result.deviations.stocks, 100);
  });
});
