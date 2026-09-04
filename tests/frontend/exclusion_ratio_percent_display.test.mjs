// exclusion_ratio (annuity income streams) was misclassified as a dollar
// field -- valueKind()'s generic "exclusion" keyword (meant for genuine
// dollar exclusions like section_121_exclusion_mfj) caught it too, so the
// UI rendered a 0-1 tax-basis fraction like 0.738 as "$0.738" instead of a
// percentage.
//
// Fixing the label match alone is not enough: unlike every other percent
// field in this app (stored already scaled, e.g. "5.00%", displayed by just
// appending "%"), exclusion_ratio is stored as a raw 0-1 fraction in
// client_income.csv and multiplied directly against payment amounts in
// deterministic_engine.py. So the UI-side fix scales by 100 for display and
// divides by 100 on save, while the CSV value and the calculation engine
// are left untouched -- see the conversation this test was written from for
// the two options considered and why this (UI-only) one was chosen.
import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();
const { valueKind, displayValueForInput, storageValueForInput } = sandbox;

const row = { label: "exclusion_ratio", units: "", schema: {}, value: "0.738" };

describe("exclusion_ratio renders as a percent, not a dollar amount", () => {
  test("valueKind is percent_fraction, not currency", () => {
    assert.equal(valueKind(row), "percent_fraction");
  });

  test("a genuine dollar exclusion field is unaffected", () => {
    assert.equal(
      valueKind({ label: "section_121_exclusion_mfj", units: "", schema: {} }),
      "currency",
    );
  });

  test("0.738 displays as 73.8%, not $0.738", () => {
    assert.equal(displayValueForInput(row, "0.738"), "73.8%");
  });

  test("0.789 (Matt's annuity) displays as 78.9%", () => {
    const r = { ...row, value: "0.789" };
    assert.equal(displayValueForInput(r, "0.789"), "78.9%");
  });

  test("typing 73.8 (with a % in the input) stores back as 0.738", () => {
    assert.equal(storageValueForInput(row, "73.8%"), "0.738");
  });

  test("round-trip: display then store recovers the original fraction", () => {
    const displayed = displayValueForInput(row, "0.738");
    assert.equal(storageValueForInput(row, displayed), "0.738");
  });
});
