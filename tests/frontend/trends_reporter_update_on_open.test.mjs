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
  });
  test("the overlay has a progress bar, Cancel update and Hide buttons, and the keeps-running note", () => {
    assert.match(html, /role="progressbar"[^>]*aria-valuenow="0"/);
    assert.match(html, /id="updateCancel"[^>]*>Cancel update</);
    assert.match(html, /id="updateHide"[^>]*>Hide</);
    assert.match(html, /The update keeps running if you hide this window\./);
    assert.match(html, /id="updateChip"[^>]*hidden/);
    assert.match(html, /\/api\/run-cancel/);
  });
  test("the page imports the shared run-time helpers", () => {
    assert.match(html, /from "\/shared\/runtime_history\.js"/);
  });
});

describe("full-year budget marker toggle", async () => {
  const charts = await import("../../financial_trends_reporter/frontend/charts.js");
  const entries = [["Total", 300, { kind: "total", prior: 250, budget: 280, fullYear: 900 }], ["Fixed", 300, { kind: "category", prior: 250, budget: 280, fullYear: 900 }]];
  test("on only for YTD by default", () => {
    assert.equal(charts.fullYearDefault("ytd"), true);
    for (const s of ["week", "month", "year", "all", "custom"]) assert.equal(charts.fullYearDefault(s), false);
  });
  test("unchecked: no full-year tick, legend entry or axis stretch; checked: all three return", () => {
    charts.setShowFullYear(false);
    const off = charts.barChartSvg(entries);
    assert.ok(!/mk-full/.test(off));
    assert.ok(!/Full-year budget/.test(off));
    charts.setShowFullYear(true);
    const on = charts.barChartSvg(entries);
    assert.match(on, /mk-full/);
    assert.match(on, /Full-year budget/);
  });
  test("the page has the checkbox in the Spending card head", () => {
    assert.match(html, /<div class="card-head"><h2>Spending<\/h2><label class="fy-toggle"><input type="checkbox" id="fullYearToggle">/);
  });
});

describe("breakdown panels (label-only trigger, fixed dock)", async () => {
  const charts = await import("../../financial_trends_reporter/frontend/charts.js");
  const entries = [["Total", 300, { kind: "total", detail: [], detailTitle: "T" }], ["Fixed", 300, { kind: "category", prior: 250, budget: 280, fullYear: 900 }]];
  test("each row with detail has a focusable label button; ticks are not inside it", () => {
    const svg = charts.barChartSvg(entries);
    assert.equal((svg.match(/class="row-label" tabindex="0" role="button"/g) || []).length, 2);
    const label = svg.match(/<g class="row-label"[\s\S]*?<\/g>/)[0];
    assert.ok(!/class="mk/.test(label));
  });
  test("the panels live in one fixed dock, closed by Escape/Close/outside click", () => {
    assert.match(html, /<div id="spendDock"[^>]*>\s*<div id="detailPopup"[^>]*><\/div><div id="detailPopup2"/);
    const dockJs = fs.readFileSync(path.join(HERE, "..", "..", "financial_trends_reporter", "frontend", "spending_dock.js"), "utf8");
    assert.match(dockJs, /e\.key === "Escape"\) hideAll\(\)/);
    assert.match(dockJs, /data-dock="close"/);
    assert.ok(!/scheduleHide|keepOpen/.test(html + dockJs));
  });
});

describe("Spending bars draw at card scale", async () => {
  const charts = await import("../../financial_trends_reporter/frontend/charts.js");
  const entries = [["Total", 300, { kind: "total", detail: [], detailTitle: "T" }], ["Fixed", 300, { kind: "category" }]];
  test("a passed width becomes the viewBox width and text is at most 11px", () => {
    const svg = charts.barChartSvg(entries, { width: 720 });
    assert.match(svg, /viewBox="0 0 720 /);
    const sizes = [...svg.matchAll(/font-size:(\d+)px/g)].map(m => Number(m[1]));
    assert.ok(sizes.length > 0 && Math.max(...sizes) <= 11);
    assert.match(charts.barChartSvg(entries), /viewBox="0 0 560 /);
  });
});
