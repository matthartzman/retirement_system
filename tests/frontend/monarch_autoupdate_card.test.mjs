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
  test("reads as off when no status has been fetched yet", () => {
    assert.match(sandbox.monarchAutoUpdateStatusLine(), /Off/);
  });
});

describe("monarchAutoUpdateControlsHtml (default/unfetched state)", () => {
  const html = sandbox.monarchAutoUpdateControlsHtml();

  test("renders the card heading and enable label", () => {
    assert.match(html, /Monarch auto-update/);
    assert.match(html, /Enable daily auto-update/);
  });

  test("renders an unchecked toggle", () => {
    assert.doesNotMatch(html, /id="monarchAutoUpdateEnabled"[^>]*checked/);
  });

  test("renders the default Monarch Extractor source folder", () => {
    assert.match(html, /value="\.\.\/Monarch Extractor\/output"/);
  });

  test("wires up save/run-now/refresh actions", () => {
    assert.match(html, /saveMonarchAutoUpdatePolicy\(\)/);
    assert.match(html, /runMonarchAutoUpdateNow\(\)/);
    assert.match(html, /refreshMonarchAutoUpdateStatus\(\)/);
  });
});
