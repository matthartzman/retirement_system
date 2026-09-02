// Ticket 302: the state residency schedule editor must keep its "last row is
// always open-ended" invariant through add/delete, not just at initial render.

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();

function withStubs(schedule, fn) {
  sandbox.window.residencySchedule = schedule;
  sandbox.dirty = new Map();
  sandbox.renderMain = () => {};
  // The real showInAppConfirm() builds a DOM modal and waits for a click,
  // which never resolves against these stub DOM elements -- auto-confirm.
  sandbox.showInAppConfirm = async () => true;
  fn(schedule);
}

describe("residency schedule add/delete-row open-ended invariant (ticket 302)", () => {
  test("adding a row gives the previously-last row a real end year and leaves the new row open", () => {
    withStubs(
      [{ state: "Illinois", start_year: "2026", end_year: "" }],
      () => {
        sandbox.addResidencyPeriod();
        const schedule = sandbox.window.residencySchedule;
        assert.equal(schedule.length, 2);
        assert.notEqual(schedule[0].end_year, "");
        assert.equal(schedule[1].end_year, "");
      },
    );
  });

  test("deleting the last row reopens whatever row is now last", async () => {
    const schedule = [
      { state: "Illinois", start_year: "2026", end_year: "2031" },
      { state: "Florida", start_year: "2032", end_year: "" },
    ];
    sandbox.window.residencySchedule = schedule;
    sandbox.dirty = new Map();
    sandbox.renderMain = () => {};
    sandbox.showInAppConfirm = async () => true;
    await sandbox.deleteResidencyPeriod(1);
    const remaining = sandbox.window.residencySchedule;
    assert.equal(remaining.length, 1);
    assert.equal(remaining[0].end_year, "");
  });

  test("editing the last row's end year is cleared back to open-ended by updateResidencyPeriod", () => {
    withStubs(
      [{ state: "Illinois", start_year: "2026", end_year: "" }],
      () => {
        // Simulates a stale DOM value briefly setting an end year on what is
        // (and must remain) the last, open-ended row.
        sandbox.updateResidencyPeriod(0, "end_year", "2031");
        assert.equal(sandbox.window.residencySchedule[0].end_year, "");
      },
    );
  });
});
