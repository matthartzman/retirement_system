// Credit card liability type: offered in the type picker, and limited to
// balance / APR / monthly payment plus a payoff date (year + month) and carry-zero.

import { test } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();

test("credit card shows balance, rate, payment and payoff-date inputs", () => {
  assert.deepEqual(
    Array.from(sandbox.liabilityFieldsForType("credit_card")),
    ["balance", "interest_rate", "monthly_payment", "payoff_year", "payoff_month", "carry_zero"],
  );
});
