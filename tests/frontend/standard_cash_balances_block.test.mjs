// The Cash Reserves page shows the four standard checking / credit-card balance fields
// (design: documentation/future/superpowers/plans/2026-11-07-cash-balances-and-art-split-design-and-plan.md 3.1).
import { describe, test } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();
const row = (label, i) => ({ section: "Other Assets", subsection: "Cash", label, row_index: i });

describe("standard cash balances block", () => {
  test("lists only the four standard-balance rows, in the order given", () => {
    sandbox.rowsForStep = () => [
      row("value", 0),
      row("checking_standard_balance", 1),
      row("checking_annual_change_pct", 2),
      row("credit_card_standard_balance", 3),
      row("credit_card_annual_change_pct", 4),
    ];
    sandbox.fieldHtml = (r) => `<f>${r.label}</f>`;
    const html = sandbox.renderStandardCashBalances();
    assert.match(html, /Checking &amp; credit-card balances in forecast years|Checking & credit-card balances in forecast years/);
    assert.deepEqual(
      [...html.matchAll(/<f>(\w+)<\/f>/g)].map((m) => m[1]),
      ["checking_standard_balance", "checking_annual_change_pct", "credit_card_standard_balance", "credit_card_annual_change_pct"],
    );
  });

  test("shows nothing when the plan has none of the rows", () => {
    sandbox.rowsForStep = () => [row("value", 0)];
    assert.equal(sandbox.renderStandardCashBalances(), "");
  });
});
