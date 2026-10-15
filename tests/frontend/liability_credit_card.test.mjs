// Credit card liability type: offered in the type picker, and limited to
// balance / APR / monthly payment (no start or payoff year).

import { test } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();

test("credit card shows only balance, rate and payment inputs", () => {
  assert.deepEqual(
    Array.from(sandbox.liabilityFieldsForType("credit_card")),
    ["balance", "interest_rate", "monthly_payment"],
  );
});
