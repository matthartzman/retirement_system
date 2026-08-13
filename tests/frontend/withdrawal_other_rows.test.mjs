// Ticket 285: "Other funding and rollover settings" must not re-list the
// per-account withdrawal sequence.
//
// The Withdrawal sequencing page renders a purpose-built drag-to-reorder editor
// ("Withdrawal order", withdrawalAccountOrderEditorHtml) at the top. The same
// underlying data also lives in the plan as
// `Withdrawal Policy / Account Order / <account_id>` rows, and those rows fell
// through withdrawalOtherRows() into the `misc` bucket -- so every account's
// draw priority was ALSO rendered as a raw numeric field further down the same
// page, under a heading about funding tolerance and spousal rollover.
//
// Two editors for one value on one page, and the raw fields are the worse of
// the two: the editor sorts and drags, the fields are a flat list of integers
// whose meaning is only explained in the section above them. The old
// Priority-1..6 subsections were already excluded here for the same reason.
//
// Executable test rather than a source-text assertion, per the Wave 2.2 guard
// (tests/test_freeze_frontend_source_grep.py): a substring test would keep
// passing if the filter were reintroduced somewhere else in the pipeline.

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();

const ROWS = [
  { section: "Withdrawal Policy", subsection: "Identity", label: "annual_funding_tolerance" },
  { section: "Withdrawal Policy", subsection: "Spousal Rollover", label: "decedent_balances_pass_to_survivor" },
  { section: "Withdrawal Policy", subsection: "Account Order", label: "Family_Checking" },
  { section: "Withdrawal Policy", subsection: "Account Order", label: "Member_1_Roth" },
  { section: "Withdrawal Policy", subsection: "Priority 1", label: "priority_1" },
  { section: "Withdrawal Policy", subsection: "Tax-Loss Harvesting", label: "tlh_enabled" },
  { section: "HSA Policy", subsection: "Withdrawals", label: "hsa_withdrawal_mode" },
];

function otherRowsFrom(rows) {
  sandbox.rows = rows;
  sandbox.rowsForStep = () => rows;
  return sandbox.withdrawalOtherRows();
}

describe("withdrawalOtherRows (ticket 285)", () => {
  test("drops Account Order rows -- the Withdrawal order editor owns them", () => {
    const labels = otherRowsFrom(ROWS).map((r) => r.label);
    assert.ok(!labels.includes("Family_Checking"), "Family_Checking still leaks into the field list");
    assert.ok(!labels.includes("Member_1_Roth"), "Member_1_Roth still leaks into the field list");
  });

  test("still drops the legacy Priority N subsections", () => {
    assert.ok(!otherRowsFrom(ROWS).map((r) => r.label).includes("priority_1"));
  });

  test("keeps the settings the section is actually about", () => {
    const labels = otherRowsFrom(ROWS).map((r) => r.label);
    assert.ok(labels.includes("annual_funding_tolerance"));
    assert.ok(labels.includes("decedent_balances_pass_to_survivor"));
  });

  test("leaves the HSA and harvesting buckets alone -- they have their own sections", () => {
    const labels = otherRowsFrom(ROWS).map((r) => r.label);
    assert.ok(labels.includes("hsa_withdrawal_mode"));
    assert.ok(labels.includes("tlh_enabled"));
  });

  test("a plan with only account-order rows yields an empty list, so the section collapses", () => {
    const only = ROWS.filter((r) => r.subsection === "Account Order");
    assert.equal(otherRowsFrom(only).length, 0);
  });
});
