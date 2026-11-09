// Sales Ledger v3: "Found in broker history" with Got it, hide / show hidden (n) / Unhide.
import { test, describe, before } from "node:test";
import assert from "node:assert/strict";

let q;
const calls = [];
before(async () => {
  globalThis.esc = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  globalThis.window = globalThis;
  globalThis.accountDisplayLabel = (a) => String(a);
  globalThis.document = { getElementById: () => null };
  globalThis.api = async (url, opts) => {
    calls.push([url, opts && opts.method, opts && opts.body ? JSON.parse(opts.body) : null]);
    if (url.startsWith("/api/sales/history?")) return { success: true, items: ITEMS };
    return { success: true };
  };
  q = await import("../../frontend/js/dashboard_decomp_sales_queue.js");
});
const sale = (o) => ({ key: "k1", account: "Matt_Trust", symbol: "ITOT", sale_date: "2026-09-22", shares: 600, proceeds: 102000, kind: "sale", complete: true, pieces: [1, 2], gain: 5000, hidden: false, hidden_on: null, ...o });
const bill = (o) => ({ key: "k2", account: "Matt_Trust", symbol: "912797VN4", sale_date: "2026-10-27", shares: 120000, proceeds: 120000, kind: "interest", complete: false, pieces: [], hidden: false, hidden_on: null, ...o });
let ITEMS = [sale({}), bill({})];

describe("history finds", () => {
  test("the button reads Got it, hide and Treasury rows say counted as interest income", () => {
    const h = q.sqHistoryHtml(ITEMS, false);
    assert.equal((h.match(/Got it, hide/g) || []).length, 2);
    assert.doesNotMatch(h, />Dismiss</);
    assert.match(h, /counted as interest income/);
    assert.match(h, /Sales found in history imports \(2\)/);
    assert.doesNotMatch(h, /show hidden/);
  });
  test("show hidden (n) lists hidden rows greyed with the date hidden and an Unhide button", () => {
    const items = [sale({}), bill({ hidden: true, hidden_on: "2026-11-09" })];
    const off = q.sqHistoryHtml(items, false);
    assert.match(off, /Sales found in history imports \(1\)/);
    assert.match(off, /show hidden \(1\)/);
    assert.doesNotMatch(off, /Unhide|912797VN4/);
    const on = q.sqHistoryHtml(items, true);
    assert.match(on, /<tr class="sq-hidden muted">/);
    assert.match(on, /hidden 2026-11-09/);
    assert.match(on, /onclick="sqHistoryUnhide\(\d+\)">Unhide</);
  });
  test("with nothing visible but some hidden the card collapses to its title and keeps the control", () => {
    const items = [sale({ hidden: true }), bill({ hidden: true })];
    const h = q.sqHistoryHtml(items, false);
    assert.match(h, /Sales found in history imports \(0\)/);
    assert.match(h, /show hidden \(2\)/);
    assert.doesNotMatch(h, /<table/);
    assert.equal(q.sqHistoryHtml([], false), "");                      // nothing at all: no card
  });
  test("hide and Unhide post the row's key; the list is read with include_hidden and the Year", async () => {
    globalThis.slCurrentYear = () => "2026";
    ITEMS = [sale({}), bill({})];
    try {
      await q.sqLoadHistory();
      assert.ok(calls.some((c) => c[0] === "/api/sales/history?include_hidden=1&year=2026"));
      calls.length = 0;
      await q.sqHistoryDismiss(1);
      assert.deepEqual(calls.find((c) => c[1] === "POST"), ["/api/sales/history/dismiss", "POST", { key: "k2" }]);
      calls.length = 0;
      await q.sqHistoryUnhide(1);
      assert.deepEqual(calls.find((c) => c[1] === "POST"), ["/api/sales/history/undismiss", "POST", { key: "k2" }]);
    } finally { delete globalThis.slCurrentYear; }
  });
});

describe("review fixes", () => {
  test("the queue list follows the Year", () => {
    globalThis.slCurrentYear = () => "2025";
    try {
      const html = q.sqQueueHtml([{ candidate_id: 1, sale_date: "2025-03-01", account: "A", symbol: "X", amount: 1, source: "monarch" }].concat([]), null);
      assert.match(html, /2025-03-01/);
    } finally { delete globalThis.slCurrentYear; }
  });
});
