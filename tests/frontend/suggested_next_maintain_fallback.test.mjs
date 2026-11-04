// Left-nav follow-ups (A): in Maintain mode, suggestedNext() uses the Maintain chain and falls back to the
// Set up chain on pages outside it; the module-gate guard still drops a target whose module is off.
import { test, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();
const realGate = sandbox.stepGatedByOptionalModule;
let mode;

beforeEach(() => {
  mode = "maintain";
  sandbox.window.RPNav = { currentMode: () => mode, maintainNext: sandbox.maintainNext };
  sandbox.stepGatedByOptionalModule = () => false;
});

test("Maintain chain page uses the Maintain chain", () => {
  assert.match(sandbox.suggestedNext("actual_spending"), /data-step-id="monarch_reconciliation"/);
});

test("Maintain page outside the chain falls back to the Set up chain", () => {
  assert.equal(sandbox.maintainNext("income_work"), "");
  assert.match(sandbox.suggestedNext("income_work"), /data-step-id="income_retirement"/);
});

test("Set up mode ignores the Maintain chain", () => {
  mode = "setup";
  assert.doesNotMatch(sandbox.suggestedNext("actual_spending"), /monarch_reconciliation/);
  assert.match(sandbox.suggestedNext("income_work"), /data-step-id="income_retirement"/);
});

test("a gated-off target yields no footer in Maintain, chain or fallback", () => {
  sandbox.stepGatedByOptionalModule = () => true;
  assert.equal(sandbox.suggestedNext("actual_spending"), "");
  assert.equal(sandbox.suggestedNext("income_work"), "");
  sandbox.stepGatedByOptionalModule = realGate;
});
