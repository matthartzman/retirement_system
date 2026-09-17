// Ticket 323 gap (carried from Phase 4's ledger entry to Phase 6): of the
// seven State Comparison rows on the old State Residency Analysis page, only
// one has a live backend consumer -- src/data_io.py:1056 reads
// State Comparison/auto_insurance/current_state_baseline_annual as the
// fallback auto-premium baseline for the workbook's "Auto Ins. Delta" column
// when no Auto insurance policy exists. Task 1 retargeted that one row's UI
// routing (sourceStepForRow) to the Insurance page (annuity_death_benefits)
// -- everything else in State Comparison, having no reader, stayed routed to
// the (now nav-less) state_residency shell.
//
// This got a code-quality review (SPEC PASS / QUALITY APPROVED) in Task 1
// but never a routing-level regression test of its own -- prior coverage
// (strategy_screen_rows_aggregate.test.mjs) proves State Comparison rows in
// general don't leak into the three new Strategy screens, not that this
// SPECIFIC row lands on Insurance rather than its old home.

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();

const AUTO_BASELINE_ROW = {
  row_index: 1,
  section: "State Comparison",
  subsection: "auto_insurance",
  label: "current_state_baseline_annual",
};

// The row_index its own subsection would suggest, but which the fix must NOT
// route to -- confirms the retargeting is a genuine override, not the
// State Comparison default that every other row in that section still gets.
const OTHER_STATE_COMP_ROW = {
  row_index: 2,
  section: "State Comparison",
  subsection: "auto_insurance",
  label: "target_state_annual",
};

function rawRows(id) {
  sandbox.window.rows = [AUTO_BASELINE_ROW, OTHER_STATE_COMP_ROW];
  return Array.from(sandbox.rawRowsForStep(id));
}

describe("the live State Comparison auto-insurance row routes to Insurance, not State Residency (ticket 323)", () => {
  test("current_state_baseline_annual routes to annuity_death_benefits", () => {
    const rows = rawRows("annuity_death_benefits");
    assert.ok(
      rows.some((r) => r.row_index === 1),
      "the auto-insurance baseline row did not route to the Insurance page",
    );
  });

  test("current_state_baseline_annual no longer routes to state_residency", () => {
    const rows = rawRows("state_residency");
    assert.ok(
      !rows.some((r) => r.row_index === 1),
      "the auto-insurance baseline row is still claimed by state_residency -- it is now claimed by two steps at once",
    );
  });

  test("every OTHER State Comparison row still routes to state_residency, unaffected", () => {
    const rows = rawRows("state_residency");
    assert.ok(
      rows.some((r) => r.row_index === 2),
      "an unrelated State Comparison row was swept up by the retargeting fix",
    );
  });

  test("sourceStepForRow agrees: the live row's source page is Insurance", () => {
    sandbox.window.rows = [AUTO_BASELINE_ROW];
    const step = sandbox.sourceStepForRow(AUTO_BASELINE_ROW);
    assert.equal(
      step,
      "annuity_death_benefits",
      "sourceStepForRow disagrees with rawRowsForStep about where this row's source page is -- every source-jump button in the app reads sourceStepForRow, so a mismatch here breaks the Source button on the lever/change-summary UI even if row-listing itself is correct",
    );
  });
});
