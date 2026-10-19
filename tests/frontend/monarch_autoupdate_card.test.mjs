// Behavioral coverage for the Monarch auto-update settings card (ticket 305),
// via the Node vm sandbox rather than a raw-text grep of the frontend
// source -- see tests/test_freeze_frontend_source_grep.py: new frontend
// string-literal-in-source-text assertions are frozen; executing the real
// render function is the preferred alternative for new coverage.
//
// Scope note: dashboard_decomp_monarch_autoupdate.js keeps its fetched
// status in a module-top-level `let monarchAutoUpdateStatus`, not a
// sandbox-global property. A vm script's top-level `let`/`const` bindings
// are NOT reified onto the context object (only `var`/function
// declarations are) -- verified empirically while writing this file:
// assigning `sandbox.monarchAutoUpdateStatus = {...}` from here has no
// effect on what monarchAutoUpdateControlsHtml()/monarchAutoUpdateStatusLine()
// actually read, since they close over the real internal binding instead.
// So only the deterministic, untouched-initial-state behavior (the module's
// `let monarchAutoUpdateStatus = null;` default) is something this sandbox
// can actually exercise; testing the "loaded/enabled" rendered state would
// need the source itself to expose a setter, which local_backups' equivalent
// module doesn't do either -- not introduced here to stay consistent with it.
//
// Run with: node --test tests/frontend/

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();

describe("monarchAutoUpdateStatusLine (default/unfetched state)", () => {
  test("reads as enabled with no run yet when nothing has been fetched (default on)", () => {
    assert.match(sandbox.monarchAutoUpdateStatusLine(), /no run yet/);
  });
});

describe("monarchAutoUpdateControlsHtml (default/unfetched state)", () => {
  const html = sandbox.monarchAutoUpdateControlsHtml();

  test("renders the card heading and enable label", () => {
    assert.match(html, /Third-party import auto-update/);
    assert.match(html, /Enable daily auto-update/);
  });

  test("renders a checked toggle (default on)", () => {
    assert.match(html, /id="monarchAutoUpdateEnabled" checked/);
  });

  test("renders run time 04:00, both step checkboxes and a source folder input", () => {
    assert.match(html, /type="time" id="monarchAutoUpdateRunTime" value="04:00"/);
    assert.match(html, /id="monarchAutoUpdateTransactions" checked/);
    assert.match(html, /id="monarchAutoUpdateBalances" checked/);
    assert.match(html, /id="monarchAutoUpdateSourceDir"/);
    assert.match(html, /<b>Transactions:<\/b>/);
    assert.match(html, /<b>Account balances:<\/b>/);
  });

  test("wires up save/run-now/refresh actions", () => {
    assert.match(html, /saveMonarchAutoUpdatePolicy\(\)/);
    assert.match(html, /runMonarchAutoUpdateNow\(\)/);
    assert.match(html, /refreshMonarchAutoUpdateStatus\(\)/);
  });
});

describe("monarchAutoUpdateFreshnessWarningHtml (default/unfetched state)", () => {
  // 2026-09 outage follow-up: a stalled extractor (Monarch Extractor/
  // run_monarch.ps1 never actually scheduled) used to be invisible because
  // the downstream import job reports success with nothing new to import.
  // This banner surfaces src/monarch_autoupdate.py's get_extractor_freshness
  // in the same card. Auto-update is off/unfetched by default, so no
  // warning should render regardless of freshness.
  test("renders nothing when no status has been fetched yet", () => {
    assert.equal(sandbox.monarchAutoUpdateFreshnessWarningHtml(), "");
  });
});
