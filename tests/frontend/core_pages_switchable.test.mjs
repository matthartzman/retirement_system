// WP1.3: Estate, Insurance, Reserve Requirements, Family & Business,
// Scenarios and Workbench pages are switchable and default on.
import { test, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();
const GATES = {
  step_gates: {
    estate: "estate_legacy_plan",
    annuity_death_benefits: "insurance_inputs",
    assets_home_cash: "reserve_requirements",
    strategy_scenarios: "what_if_analysis",
    strategy_workbench: "planning_workbench",
  },
  section_gates: {},
  flag_gates: {},
  rowless_defaults: { insurance_inputs: true, reserve_requirements: true, planning_workbench: true },
};

beforeEach(() => {
  sandbox.window.rows = [];
  sandbox.window.dirty = new Map();
  sandbox.window.moduleGates = GATES;
});

test("rowless features read their registry default (on)", () => {
  for (const id of ["annuity_death_benefits", "assets_home_cash", "strategy_workbench"]) {
    assert.equal(sandbox.stepGatedByOptionalModule(id), false, id);
  }
});

test("a module with a CSV row but no row loaded stays off (unchanged behavior)", () => {
  assert.equal(sandbox.stepGatedByOptionalModule("estate"), true);
});

test("Family & Business hides only when both of its modules are off", () => {
  assert.equal(sandbox.stepGatedByOptionalModule("family_business"), true);
});

test("WP1.4: Optimize sections follow their sheet toggles; Harvesting is any-of", () => {
  sandbox.window.moduleGates = {
    ...GATES,
    step_gates: { ...GATES.step_gates, hsa_drawdown: "hsa_drawdown", social_security: "social_security_timing", withdrawal_sequencing: "retirement_strategy" },
  };
  for (const id of ["hsa_drawdown", "social_security", "withdrawal_sequencing", "harvesting"]) {
    assert.equal(sandbox.stepGatedByOptionalModule(id), true, id); // no rows loaded = off
  }
});
