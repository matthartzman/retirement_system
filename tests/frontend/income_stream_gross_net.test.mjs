// Gross vs net income streams (FUNCTIONAL_SPEC §6): the payment field is the
// gross monthly amount the engine taxes; net_monthly_payment is the optional
// deposit after withholding. The Pensions and annuities panel labels both and
// shows Gross · Withholding · Net, warning when net is above gross.
import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();
const { grossNetSummary, humanLabel, fieldGuidance } = sandbox;

describe("grossNetSummary", () => {
  test("the pension: $397.73 gross, $282.58 net -> $115.15 withheld", () => {
    const s = grossNetSummary("$397.73", "$282.58");
    assert.equal(s.gross, 397.73);
    assert.equal(s.net, 282.58);
    assert.equal(Math.round(s.withholding * 100) / 100, 115.15);
    assert.equal(s.netEntered, true);
    assert.equal(s.netAboveGross, false);
  });

  test("blank net means no withholding", () => {
    const s = grossNetSummary("1,071.33", "");
    assert.equal(s.net, 1071.33);
    assert.equal(s.withholding, 0);
    assert.equal(s.netEntered, false);
  });

  test("net above gross is flagged", () => {
    assert.equal(grossNetSummary("100", "150").netAboveGross, true);
  });
});

describe("labels and help", () => {
  const row = (label) => ({ section: "Income Streams", subsection: "Member 2 Pension", label });

  test("the payment field says Gross, the new field says Net", () => {
    assert.equal(humanLabel("initial_guaranteed_income_payment", row("initial_guaranteed_income_payment")), "Monthly Payment (Gross)");
    assert.equal(humanLabel("net_monthly_payment", row("net_monthly_payment")), "Monthly Payment (Net, After Withholding)");
  });

  test("help explains gross drives the plan and net is reference only", () => {
    assert.match(fieldGuidance(row("initial_guaranteed_income_payment")).purpose, /GROSS/);
    assert.match(fieldGuidance(row("net_monthly_payment")).impact, /None on the projection/);
  });
});
