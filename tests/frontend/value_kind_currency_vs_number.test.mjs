// valueKind() has to satisfy two rules that pull in opposite directions, and
// each one was landed as a fix for a real display bug:
//
//   1. A money-like label coming from older Plan Data with no schema type and
//      no units must still render as dollars, not as a raw integer
//      (test_scenario_home_value_display_fix.py -- home value/basis/proceeds).
//   2. A field whose schema explicitly declares a numeric type must render as
//      a plain number even when its label contains a currency-ish keyword, or
//      roth_optimize_lifetime_tax_weight shows as "$0.25" instead of "0.25".
//
// Rule 2 was implemented by moving the schema-type branch above the label
// heuristic. The Python test had pinned rule 1 by asserting the *source order*
// of those two branches, so it broke on a change that kept both behaviors
// intact. These tests pin the behavior instead, so neither rule can regress
// without a failure that names the actual symptom.
import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();
const { valueKind } = sandbox;

describe("valueKind: money-like label with no schema type and no units", () => {
  // Scenario/home rows that predate the schema carrying reliable type info.
  const moneyLabels = [
    "home_sale_price",
    "home_basis",
    "value_as_of_plan_start",
    "home_sale_proceeds",
    "annual_real_estate_taxes",
    "section_121_exclusion_mfj",
  ];

  for (const label of moneyLabels) {
    test(`${label} falls through to currency`, () => {
      assert.equal(valueKind({ label, units: "", schema: {} }), "currency");
    });
  }
});

describe("valueKind: schema-declared numeric type beats a currency-ish label", () => {
  // Roth optimizer weights are 0-1 decimals whose labels contain "tax".
  const weightLabels = [
    "roth_optimize_lifetime_tax_weight",
    "future_tax_risk_weight",
    "inheritance_tax_burden_weight",
    "survivor_tax_risk_weight",
  ];

  for (const label of weightLabels) {
    test(`${label} stays a plain number`, () => {
      assert.equal(
        valueKind({ label, units: "", schema: { type: "number" } }),
        "number",
      );
    });
  }
});

describe("valueKind: an explicit currency type is still honored", () => {
  test("dollars-typed rows render as currency", () => {
    assert.equal(
      valueKind({
        label: "annual_spending_base_year",
        units: "dollars",
        schema: { type: "dollars" },
      }),
      "currency",
    );
  });
});
