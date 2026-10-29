// Plan step 3a.3: the pure HTML helpers and fetch calls of dashboard_decomp_sales_tax.js (tax-year panel on the Sales Ledger page).
import { test, describe, before, beforeEach } from "node:test";
import assert from "node:assert/strict";

let m;
const calls = [];
const fields = {};
const SUMMARY = (o = {}) => ({
  success: true, year: 2026, filing: "MFJ", limit: 3000,
  netting: { net_st: 1500, net_lt: -600, ordinary_offset: 0, carryforward_st: 0, carryforward_lt: 0, gain_to_tax_ordinary: 900, gain_to_tax_ltcg: 0 },
  carryforward_in: { short: 0, long: 5000, entered: false }, carryforward_out: { short: 0, long: 0 },
  totals: { count: 2, st_gain: 1500, lt_gain: -600 },
  wash: { count: 0, flagged_loss: 0, rows: [] }, ...o,
});
before(async () => {
  globalThis.esc = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  globalThis.window = globalThis;
  globalThis.document = { getElementById: (id) => (id in fields ? { value: fields[id], innerHTML: "" } : null) };
  globalThis.api = async (url, opts) => {
    calls.push([url, opts && opts.method, opts && opts.body ? JSON.parse(opts.body) : null]);
    if (url.startsWith("/api/sales/tax-year")) return SUMMARY();
    if (url === "/api/sales/wash/refresh") return { success: true, flagged: 1, updated: 1 };
    return { success: true };
  };
  m = await import("../../frontend/js/dashboard_decomp_sales_tax.js");
});
beforeEach(() => { calls.length = 0; for (const k of Object.keys(fields)) delete fields[k]; });

describe("netting table", () => {
  test("shows the two buckets, what is taxed each way, the ordinary offset and the carry out", () => {
    const html = m.stNettingHtml(SUMMARY());
    assert.match(html, /Short-term net[\s\S]*\$1,500\.00/);
    assert.match(html, /Long-term net[\s\S]*-\$600\.00/);
    assert.match(html, /Taxed as ordinary income[\s\S]*\$900\.00/);
    assert.match(html, /Taxed at long-term rates[\s\S]*\$0\.00/);
    assert.match(html, /Loss deducted against other income[\s\S]*\$0\.00/);
    assert.match(html, /Carried to next year/);
  });
  test("the limit is named (MFS shows its own)", () => {
    assert.match(m.stNettingHtml(SUMMARY({ limit: 1500, filing: "MFS" })), /\$1,500\.00 limit/);
  });
  test("an empty year says so", () => {
    assert.match(m.stNettingHtml(SUMMARY({ totals: { count: 0, st_gain: 0, lt_gain: 0 } })), /No taxable sales recorded for 2026/);
  });
});

describe("carryforward form", () => {
  test("prefills the figures going in and says whether they were entered or estimated from the ledger", () => {
    const html = m.stCarryforwardHtml(SUMMARY());
    assert.match(html, /id="stCfShort"[^>]*value="0"/);
    assert.match(html, /id="stCfLong"[^>]*value="5000"/);
    assert.match(html, /estimated from your earlier sales/i);
    assert.match(m.stCarryforwardHtml(SUMMARY({ carryforward_in: { short: 1, long: 2, entered: true } })), /entered from your Schedule D/i);
  });
  test("save posts both figures for the year", async () => {
    await m.loadSalesTaxYear(2026);
    calls.length = 0;
    fields.stCfShort = "250";
    fields.stCfLong = "1000";
    await m.stSaveCarryforward();
    const post = calls.find((c) => c[0] === "/api/sales/carryforward");
    assert.deepEqual(post[2], { year: 2026, carryforward_short: "250", carryforward_long: "1000" });
    assert.ok(calls.some((c) => c[0].startsWith("/api/sales/tax-year?year=2026")));
  });
});

describe("wash warnings", () => {
  test("no flags: a quiet line and the re-check button", () => {
    const html = m.stWashHtml({ count: 0, flagged_loss: 0, rows: [] });
    assert.match(html, /No losses are flagged/);
    assert.match(html, /stRefreshWash\(\)/);
  });
  test("flags: the overstated-deduction warning, each note escaped", () => {
    const html = m.stWashHtml({ count: 1, flagged_loss: 405, rows: [{ sale_id: 3, symbol: "VTI", sale_date: "2026-06-10", gain: -405, note: "Loss on VTI; <b>bought</b>" }] });
    assert.match(html, /\$405\.00 of losses flagged as possible wash sales — this may overstate the deduction/);
    assert.doesNotMatch(html, /<b>bought/);
    assert.match(html, /VTI/);
  });
  test("refresh posts, then reloads the summary", async () => {
    await m.loadSalesTaxYear(2026);
    calls.length = 0;
    await m.stRefreshWash();
    assert.deepEqual(calls.map((c) => c[0]).slice(0, 2), ["/api/sales/wash/refresh", "/api/sales/tax-year?year=2026"]);
  });
});

describe("load", () => {
  test("loadSalesTaxYear fetches the chosen year", async () => {
    await m.loadSalesTaxYear(2025);
    assert.equal(calls[0][0], "/api/sales/tax-year?year=2025");
  });
});
