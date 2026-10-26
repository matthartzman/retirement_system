// Phase 2 of the trends time-scope design: titles, no Run now button, and the
// update-on-open overlay. updateDecision() is the pure load-flow decision.
import { test, describe } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { updateDecision } from "../../financial_trends_reporter/frontend/charts.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const html = fs.readFileSync(path.join(HERE, "..", "..", "financial_trends_reporter", "frontend", "index.html"), "utf8");
const NOW = Date.parse("2026-10-26T15:00:00Z");

describe("updateDecision", () => {
  test("a stale last run starts an update", () => {
    const status = { running: false, last_run_at: "2026-10-26T14:00:00Z", fresh_seconds: 900 };
    assert.equal(updateDecision(status, NOW), "run");
  });
  test("a never-run log starts an update", () => {
    assert.equal(updateDecision({ running: false, last_run_at: null, fresh_seconds: 900 }, NOW), "run");
  });
  test("a fresh last run is skipped", () => {
    const status = { running: false, last_run_at: "2026-10-26T14:50:00Z", fresh_seconds: 900 };
    assert.equal(updateDecision(status, NOW), "skip");
  });
  test("force runs even when fresh", () => {
    const status = { running: false, last_run_at: "2026-10-26T14:59:00Z", fresh_seconds: 900 };
    assert.equal(updateDecision(status, NOW, true), "run");
  });
  test("a run in flight is polled, even when forced", () => {
    assert.equal(updateDecision({ running: true, last_run_at: null, fresh_seconds: 900 }, NOW), "poll");
    assert.equal(updateDecision({ running: true, last_run_at: null, fresh_seconds: 900 }, NOW, true), "poll");
  });
  test("an unreadable status falls back to running an update", () => {
    assert.equal(updateDecision(null, NOW), "run");
  });
  test("an unparseable timestamp counts as stale", () => {
    assert.equal(updateDecision({ running: false, last_run_at: "garbage", fresh_seconds: 900 }, NOW), "run");
  });
});

describe("page markup", () => {
  test("there is no Run now button or copy", () => {
    assert.ok(!/runNow/.test(html));
    assert.ok(!/Run now/.test(html));
  });
  test("titles use the Financial Trends names", () => {
    assert.match(html, /<title>Financial Trends<\/title>/);
    assert.match(html, /<h1>Financial Trends<\/h1>/);
    assert.match(html, /<h2>Net Worth<\/h2>/);
    assert.match(html, /<h2>Spending<\/h2>/);
    assert.match(html, /"Investment Net Flows"/);
    assert.ok(!/YTD expenses/.test(html));
  });
  test("the Updating Data overlay is an accessible status region with the average line", () => {
    assert.match(html, /id="updateOverlay"[^>]*role="status"[^>]*aria-live="polite"[^>]*aria-hidden="true"/);
    assert.match(html, /Updating Data/);
    assert.match(html, /id="updateOverlayAvg"/);
    assert.ok(!/Cancel/.test(html.match(/id="updateOverlay"[\s\S]*?<\/div>\s*<\/div>\s*<\/div>/)[0]));
  });
  test("the page imports the shared run-time helpers", () => {
    assert.match(html, /from "\/shared\/runtime_history\.js"/);
  });
});
