// Roth Conversion page: grouped compact fields, no "Roth" prefix on field names,
// Objectives before Tax assumptions.
import { test } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

test("Objectives group comes before Tax assumptions", () => {
  const { rothGroupFor, rothCompactFieldsHtml } = loadDashboardSandbox();
  assert.equal(rothGroupFor("roth_objective_mode"), "Objectives");
  assert.equal(rothGroupFor("roth_tax_discount_rate"), "Tax assumptions");
  assert.equal(rothGroupFor("future_tax_risk_weight"), "Scoring weights");
  assert.equal(rothGroupFor("something_else"), "Other");
  const row = (label, i) => ({ row_index: i, label, value: "", units: "", schema: { type: "text" } });
  const html = rothCompactFieldsHtml(
    [row("roth_tax_discount_rate", 1), row("roth_objective_mode", 2)],
    true,
  );
  assert.ok(html.indexOf("Objectives") < html.indexOf("Tax assumptions"));
});

test("field labels drop the Roth prefix on this page only", () => {
  const { rothCompactFieldsHtml, fieldHtml } = loadDashboardSandbox();
  const row = { row_index: 3, label: "roth_objective_mode", value: "", units: "", schema: { type: "text" } };
  const compact = rothCompactFieldsHtml([row], false);
  assert.doesNotMatch(compact, />Roth Objective Mode</);
  assert.match(compact, />Objective Mode</);
  assert.match(fieldHtml(row, {}), />Roth Objective Mode</);
});
