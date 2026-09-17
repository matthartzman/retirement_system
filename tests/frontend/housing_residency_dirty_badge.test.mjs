// Ticket 323 gap S7.6: the State residency over time table moved from its
// own retired step to a collapsible on the Housing page
// (spending_mortgage_events). Its edit-tracking flag, residencyScheduleChanged,
// was already checked by the global unsaved-changes guard
// (unsavedChangeCount()) but was never wired into stepStats() for ANY step --
// so editing the residency table has never raised an "Edited" nav badge on
// its own page. That gap moved with the table; it does not fix itself.
//
// Executable rather than a source grep, per the Wave 2.2 guard
// (test_freeze_frontend_source_grep.py): this exercises stepStats() directly.

import { test, describe, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();

beforeEach(() => {
  sandbox.window.rows = [];
  sandbox.window.residencyScheduleChanged = false;
});

describe("stepStats() surfaces residencyScheduleChanged on the Housing page (ticket 323)", () => {
  test("a dirty residency schedule raises a dirty entry on spending_mortgage_events", () => {
    sandbox.window.residencyScheduleChanged = true;
    const stats = sandbox.stepStats("spending_mortgage_events");
    assert.ok(
      stats.dirty.length >= 1,
      "residencyScheduleChanged=true produced no dirty entry for the Housing step",
    );
  });

  test("a clean residency schedule raises nothing on its own", () => {
    sandbox.window.residencyScheduleChanged = false;
    const stats = sandbox.stepStats("spending_mortgage_events");
    assert.equal(stats.dirty.length, 0);
  });

  test("the flag does not leak a dirty entry onto an unrelated step", () => {
    sandbox.window.residencyScheduleChanged = true;
    const stats = sandbox.stepStats("holdings");
    assert.equal(
      stats.dirty.length,
      0,
      "residencyScheduleChanged leaked into a step it has nothing to do with",
    );
  });
});
