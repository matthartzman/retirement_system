// WP10.4: the first-launch conversion notice (dashboard_decomp_conversion.js).
// Run with: node --test tests/frontend/

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();

describe("conversionNoticeHtml", () => {
  test("nothing when no conversion is needed", () => {
    assert.equal(sandbox.conversionNoticeHtml({ needed: false }, false), "");
    assert.equal(sandbox.conversionNoticeHtml(null, false), "");
  });

  test("offers Check first and Convert now, and says originals stay", () => {
    const html = sandbox.conversionNoticeHtml({ needed: true, mode: "normal" }, false);
    assert.match(html, /checkConversion\(\)/);
    assert.match(html, /runConversion\(\)/);
    assert.match(html, /never changed or deleted/);
  });

  test("shows progress while running", () => {
    assert.match(sandbox.conversionNoticeHtml({ needed: true, running: true }, false), /Converting your plan/);
    assert.match(sandbox.conversionNoticeHtml({ needed: true }, true), /Converting your plan/);
  });

  test("a tier-safeguard block offers keep-my-switches first, names keys, no values", () => {
    const html = sandbox.conversionNoticeHtml({
      needed: true,
      last_result: { status: "blocked", blocked_reason: "tier_mapping_changes_results",
        checks: [{ name: "tier_mapping", status: "diff", differing: 2, names: ["a/b", "c/d"] }] },
    }, false);
    assert.match(html, /Nothing was changed/);
    assert.match(html, /runConversion\(\{tier_mapping:'keep'\}\)/);
    assert.match(html, /Convert anyway/);
    assert.match(html, /<code>a\/b<\/code>/);
  });

  test("a hard block (backup failed) has no Convert anyway", () => {
    const html = sandbox.conversionNoticeHtml({ needed: true, last_result: { status: "blocked", blocked_reason: "backup_failed" } }, false);
    assert.doesNotMatch(html, /Convert anyway/);
    assert.match(html, /Check again/);
  });

  test("done shows the backup name and the 30-day removal list", () => {
    const html = sandbox.conversionNoticeHtml({ needed: false, last_result: { status: "done", backup: { name: "pre_conversion_1" }, removable: { "system_config.csv": "x" } } }, false);
    assert.match(html, /converted and checked/);
    assert.match(html, /pre_conversion_1/);
    assert.match(html, /system_config\.csv/);
  });
});
