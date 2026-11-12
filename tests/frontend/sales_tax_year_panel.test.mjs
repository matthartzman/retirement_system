// Plan step 3a.3: the pure HTML helpers and fetch calls of dashboard_decomp_sales_tax.js (tax-year panel on the Sales Ledger page).
import { test, describe, before, beforeEach } from "node:test";
import { installInAppConfirm } from "./inapp_confirm_stub.mjs";
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
  await installInAppConfirm();
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

describe("load", () => {
  test("loadSalesTaxYear fetches the chosen year", async () => {
    await m.loadSalesTaxYear(2025);
    assert.equal(calls[0][0], "/api/sales/tax-year?year=2025");
  });
});

describe("summary publish", () => {
  test("an unsaved carryforward warns; an entered one is neutral; no slPublish is safe", async () => {
    const pub = {};
    globalThis.slPublish = (k, s) => { pub[k] = s; };
    await m.loadSalesTaxYear(2026);
    assert.deepEqual(pub.cf, { count: 0, tone: "warn", text: "carryforward not saved" });
    assert.equal(pub.wash, undefined);                      // the wash cards publish their own summary
    const orig = globalThis.api;
    globalThis.api = async () => SUMMARY({ carryforward_in: { short: 0, long: 0, entered: true } });
    await m.loadSalesTaxYear(2026);
    assert.deepEqual(pub.cf, { count: 0, tone: "", text: "" });
    delete globalThis.slPublish;
    await assert.doesNotReject(m.loadSalesTaxYear(2026));
    globalThis.api = orig;
  });
  test("the netting table names the disallowed wash-sale losses with the split and a link to the cards", async () => {
    const wash = { count: 1, flagged_loss: 50, rows: [], disallowed: 12.5, deferred: 10, lost_permanently: 2.5, sales: 1 };
    const html = m.stNettingHtml(SUMMARY({ wash }));
    assert.match(html, /Wash-sale losses disallowed/);
    assert.match(html, /deferred \$10\.00 · lost in IRA \$2\.50/);
    assert.match(html, /slGo\('fix','wash'\)/);
    assert.doesNotMatch(m.stNettingHtml(SUMMARY({ wash: { ...wash, disallowed: 0 } })), /Wash-sale losses disallowed/);
  });
});

describe("tax tab layout (task 13)", () => {
  const TAXED = { available: true, ordinary_tax: 1, ltcg_tax: 2, niit: 0, state_tax: 0, total: 742, note: "n" };
  test("tiles: ST net, LT net, estimated tax, carryforward out with signs", () => {
    const html = m.stTilesHtml(SUMMARY({ realized_tax: TAXED, netting: { net_st: -505, net_lt: 4950, carryforward_st: 10, carryforward_lt: 5 } }));
    assert.match(html, /sl-tiles/);
    assert.equal((html.match(/class="tile sl-tile"/g) || []).length, 4);
    assert.match(html, /Short-term net[\s\S]*-\$505\.00/);
    assert.match(html, /Long-term net[\s\S]*\$4,950\.00/);
    assert.match(html, /Estimated tax[\s\S]*\$742\.00/);
    assert.match(html, /Carryforward out[\s\S]*\$15\.00/);
  });
  test("tiles never show NaN with zero or missing data", () => {
    for (const s of [{ year: 2026 }, SUMMARY({ totals: { count: 0 }, netting: undefined }), SUMMARY({ realized_tax: { available: false } })]) {
      const html = m.stTilesHtml(s);
      assert.doesNotMatch(html, /NaN|undefined/);
      assert.equal((html.match(/class="tile sl-tile"/g) || []).length, 4);
    }
    assert.match(m.stTilesHtml({ year: 2026 }), /Estimated tax[\s\S]*—/);
  });
  test("body: scope title, two-column wrapper, carryforward ids once", async () => {
    await m.loadSalesTaxYear(2026);
    const html = m.renderSalesTaxYear();
    assert.match(html, /Tax year 2026 · sales dated 1\/1–12\/31/);
    assert.match(html, /class="sl-tax-cols"/);
    assert.equal((html.match(/id="stCfShort"/g) || []).length, 1);
    assert.equal((html.match(/id="stCfLong"/g) || []).length, 1);
  });
  test("1099-B row: neutral and warn", () => {
    assert.match(m.st1099bStatusRowHtml(undefined), /1099-B: No 1099-B differences recorded/);
    assert.match(m.st1099bStatusRowHtml({ count: 2, tone: "warn", text: "x" }), /1099-B: 2 accounts not tied/);
    assert.match(m.st1099bStatusRowHtml({ count: 1, tone: "bad" }), /slGo\('tax','b1099'\)/);
    assert.match(m.st1099bStatusRowHtml({ count: 0, tone: "" }), /No 1099-B differences/);
  });
  test("year-end link text and fetch handling", async () => {
    assert.match(m.stYearEndLinkHtml(2, 9, 2026), /Year-end steps \(2026\): 2 of 9 open → Year-End Transition/);
    assert.match(m.stYearEndLinkHtml(2, 9, 2026), /setStep\('year_end'\)/);
    assert.equal(m.stYearEndLinkHtml(0, 0, 2026), "");
    const orig = globalThis.api;
    globalThis.api = async (url) => (url === "/api/year-end" ? { year: 2026, steps: [{ state: "open" }, { state: "done" }, { state: "open" }] } : SUMMARY());
    await m.loadSalesTaxYear(2026);
    assert.match(m.renderSalesTaxYear(), /Year-end steps \(2026\): 2 of 3 open/);
    globalThis.api = async (url) => { if (url === "/api/year-end") throw new Error("down"); return SUMMARY(); };
    await m.loadSalesTaxYear(2026);
    assert.doesNotMatch(m.renderSalesTaxYear(), /Year-end steps/);
    globalThis.api = orig;
  });
});
