// Ticket 301: Reports & Review is primarily the Impact page now -- Build and
// Download live as buttons on that page (not separate tabs), and Plan Data
// Review / Build History are collapsible <details> sections on it instead
// of their own tabs.
//
// Executable test against the real render output rather than a source-text
// assertion, per this repo's existing convention (a string search would
// keep passing if the markup moved without the actual structure changing).

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

function freshSandbox() {
  const sandbox = loadDashboardSandbox();
  // loadBuildHistory() unconditionally reloads from localStorage (stubbed to
  // always return null), clobbering whatever buildHistory this test sets --
  // no-op it so the pre-set value sticks.
  sandbox.loadBuildHistory = () => {};
  sandbox.dirty = new Map();
  return sandbox;
}

describe("Reports & Review restructure (ticket 301)", () => {
  test("no build history yet: Build/Download buttons and Plan Data Review are present, no leftover 'Back to Download Reports'", () => {
    const sandbox = freshSandbox();
    sandbox.window.buildHistory = [];
    const out = sandbox.renderBuildImpactPage();
    assert.match(out, /Build Reports/);
    assert.match(out, /Download Workbook/);
    assert.match(out, /class="plan-data-review-collapsible"/);
    assert.doesNotMatch(out, /Back to Download Reports/);
  });

  test("with build history: Build History is a collapsible <details>, not a plain always-open list", () => {
    const sandbox = freshSandbox();
    sandbox.window.RetirementPlanningWorkbench = { renderBuildImpactContext: () => "" };
    sandbox.window.buildHistory = [
      { id: "1", kpi: { inheritable_nw: 100, lifetime_tax: 10, mc_success: 0.9 }, changes: [] },
    ];
    const out = sandbox.renderBuildImpactPage();
    assert.match(out, /<details class="build-history-collapsible">/);
    assert.match(out, /<summary class="section-header">Build History/);
    assert.match(out, /Build Reports/);
    assert.match(out, /Download Workbook/);
    assert.match(out, /class="plan-data-review-collapsible"/);
  });
});

describe("REPORTS_TABS / reportsActiveTab source (ticket 301)", () => {
  test("dashboard.js no longer defines Build/Downloads/Plan Data Review as separate report tabs", async () => {
    const fs = await import("node:fs");
    const path = await import("node:path");
    const { fileURLToPath } = await import("node:url");
    const __dirname = path.dirname(fileURLToPath(import.meta.url));
    const src = fs.readFileSync(
      path.join(__dirname, "..", "..", "frontend", "js", "dashboard.js"),
      "utf8",
    );
    const m = src.match(/const REPORTS_TABS = \[([\s\S]*?)\];/);
    assert.ok(m, "REPORTS_TABS declaration not found");
    const tabs = m[1].split(",").map((s) => s.trim().replace(/"/g, "")).filter(Boolean);
    assert.deepEqual(tabs, ["Preflight", "Impact", "Results"]);
  });
});
