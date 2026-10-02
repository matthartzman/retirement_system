// Every *_weight setting is stored as a raw multiplier but shown as a percent.
import { test } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const LABELS = [
  "future_tax_risk_weight",
  "survivor_tax_risk_weight",
  "inheritance_tax_burden_weight",
  "roth_optimize_terminal_weight",
  "roth_optimize_lifetime_tax_weight",
  "real_loss_aware_weight",
];

test("weights display as percent, never dollars", () => {
  const { displayValueForInput, valueKind } = loadDashboardSandbox();
  for (const label of LABELS) {
    const row = { label, units: "number", schema: { type: "number" } };
    assert.equal(valueKind(row), "percent_fraction", label);
    assert.doesNotMatch(displayValueForInput(row, "0.35"), /\$/, label);
  }
  assert.equal(displayValueForInput({ label: "future_tax_risk_weight", units: "number" }, "0.35"), "35%");
  assert.equal(displayValueForInput({ label: "roth_optimize_terminal_weight", units: "number" }, "1.00"), "100%");
});

test("typing a percent stores the raw multiplier the engine reads", () => {
  const { storageValueForInput } = loadDashboardSandbox();
  const row = { label: "survivor_tax_risk_weight", units: "number" };
  assert.equal(storageValueForInput(row, "25%"), "0.25");
  assert.equal(storageValueForInput(row, "25"), "0.25");
});
