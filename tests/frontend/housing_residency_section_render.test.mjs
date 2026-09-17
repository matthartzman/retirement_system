// Ticket 323 gap (carried from Phase 4's ledger entry to Phase 6): the
// State residency over time table moved from its own retired step onto the
// Housing page as a collapsible. Prior coverage
// (tests/frontend/housing_residency_dirty_badge.test.mjs,
// tests/frontend/strategy_section_redirects.test.mjs) proves the dirty badge
// and the redirect landing target, but nothing actually calls
// renderSpendingHousing() and checks the collapsible -- and its body --
// really renders. This closes that gap.

import { test, describe, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();

beforeEach(() => {
  // renderSpendingHousing() filters rowsForStep("spending_mortgage_events")
  // for mortgage/home/housing rows -- that filtering is exercised by its own
  // existing coverage; stubbed to [] here so this test isolates the one
  // thing it actually checks, the residency collapsible.
  sandbox.rowsForStep = () => [];
  sandbox.window.residencySchedule = [];
});

describe("Housing page renders the residency collapsible (ticket 323)", () => {
  test("the collapsible exists with its data-dkey, even with no residency rows yet", () => {
    const html = sandbox.renderSpendingHousing();
    assert.ok(
      html.includes('data-dkey="housing:residency"'),
      "State residency collapsible is missing from the Housing page",
    );
    assert.ok(
      html.includes("State residency over time"),
      "residency section heading is missing",
    );
  });

  test("a configured residency period actually renders inside the collapsible", () => {
    sandbox.window.residencySchedule = [
      { state: "Florida", start_year: "2030", end_year: "" },
    ];
    const html = sandbox.renderSpendingHousing();
    const start = html.indexOf('data-dkey="housing:residency"');
    assert.ok(start >= 0, "collapsible not found");
    // The residency row must render INSIDE that collapsible, not merely
    // appear somewhere else on the page.
    const section = html.slice(start, start + 4000);
    assert.ok(
      section.includes("Florida"),
      "configured residency state did not render inside the Housing collapsible",
    );
  });

  test("the collapsible sits after the Current home section, not before it", () => {
    const html = sandbox.renderSpendingHousing();
    const currentHomeIdx = html.indexOf("Current home");
    const residencyIdx = html.indexOf('data-dkey="housing:residency"');
    assert.ok(currentHomeIdx >= 0, "Current home section not found");
    assert.ok(residencyIdx >= 0, "residency collapsible not found");
    assert.ok(
      currentHomeIdx < residencyIdx,
      "residency collapsible must come after Current home, per spec S3",
    );
  });
});
