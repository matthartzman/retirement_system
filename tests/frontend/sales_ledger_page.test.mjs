// Plan step 1.4: the pure HTML helpers and the fetch calls of dashboard_decomp_sales_ledger.js.
import { test, describe, before, beforeEach } from "node:test";
import assert from "node:assert/strict";

let m;
const calls = [];
before(async () => {
  globalThis.esc = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  globalThis.window = globalThis;
  const fields = {};
  globalThis.__fields = fields;
  globalThis.document = { getElementById: (id) => (id in fields ? { value: fields[id] } : null) };
  globalThis.api = async (url, opts) => {
    calls.push([url, opts && opts.method, opts && opts.body ? JSON.parse(opts.body) : null]);
    if (url.startsWith("/api/sales?")) return { success: true, sales: [], totals: { count: 0, short_gain: 0, long_gain: 0 } };
    if (url === "/api/sales/import/preview") return { success: true, received: 1, will_write: [{ symbol: "VXUS" }], duplicates: [], errors: [] };
    return { success: true };
  };
  m = await import("../../frontend/js/dashboard_decomp_sales_ledger.js");
});
beforeEach(() => { calls.length = 0; });

const SALE = (o) => ({ sale_id: 7, sale_date: "2026-06-10", account: "Trust", symbol: "VTI", shares: 10, proceeds: 2000, fees: 5, basis: 1500,
  gain: 495, holding_period: "long", tax_class: "taxable", status: "confirmed", source: "manual", ...o });

describe("formatting", () => {
  test("money", () => {
    assert.equal(m.slMoney(1234.5), "$1,234.50");
    assert.equal(m.slMoney(-5), "-$5.00");
    assert.equal(m.slMoney(null), "—");
  });
  test("a loss is marked down and a gain up; non-taxable has no gain", () => {
    assert.match(m.slGainHtml(495), /sl-up.*\+\$495\.00/);
    assert.match(m.slGainHtml(-505), /sl-down.*-\$505\.00/);
    assert.equal(m.slGainHtml(null), "—");
  });
});

describe("table", () => {
  test("a row shows the lot, term and a Void button; a voided row offers Restore", () => {
    const html = m.slRowHtml(SALE());
    assert.match(html, /VTI/);
    assert.match(html, /Long/);
    assert.match(html, /slVoid\(7\)/);
    assert.match(m.slRowHtml(SALE({ status: "voided" })), /slUnvoid\(7\)/);
    assert.match(m.slRowHtml(SALE({ status: "voided" })), /sl-voided/);
  });
  test("user text is escaped", () => {
    assert.doesNotMatch(m.slRowHtml(SALE({ account: "<img onerror=x>" })), /<img/);
  });
  test("empty ledger says so", () => {
    assert.match(m.slTableHtml([]), /No sales recorded/);
  });
  test("totals line shows short and long net", () => {
    const html = m.slTotalsHtml({ count: 2, short_gain: -505, long_gain: 495 });
    assert.match(html, /-\$505\.00/);
    assert.match(html, /\$495\.00/);
  });
});

describe("csv preview", () => {
  test("counts, duplicates and line errors", () => {
    const html = m.slPreviewHtml({ received: 4, will_write: [{}], duplicates: [{}, {}], errors: [{ line: 5, error: "shares must be > 0" }] });
    assert.match(html, /1 to add/);
    assert.match(html, /2 already in the ledger/);
    assert.match(html, /Line 5: shares must be &gt; 0|Line 5: shares must be > 0/);
    assert.doesNotMatch(html, /slImportCommit/);  // errors refuse the whole file
  });
  test("a clean preview offers the commit", () => {
    assert.match(m.slPreviewHtml({ received: 1, will_write: [{}], duplicates: [], errors: [] }), /slImportCommit/);
  });
});

describe("actions", () => {
  test("slSubmit posts the form fields and reloads the list", async () => {
    Object.assign(globalThis.__fields, { slDate: "2026-06-10", slAccount: "Trust", slClass: "taxable", slSymbol: "vti", slShares: "10",
      slProceeds: "2000", slFees: "5", slBasis: "1500", slPurchase: "2025-01-02" });
    await m.slSubmit();
    const post = calls.find((c) => c[0] === "/api/sales" && c[1] === "POST");
    assert.deepEqual(post[2], { sale_date: "2026-06-10", account: "Trust", tax_class: "taxable", symbol: "vti", shares: "10",
      proceeds: "2000", fees: "5", basis: "1500", purchase_date: "2025-01-02" });
    assert.ok(calls.some((c) => c[0].startsWith("/api/sales?")));
  });
  test("void and restore post to the sale", async () => {
    await m.slVoid(7);
    await m.slUnvoid(7);
    assert.deepEqual(calls.filter((c) => c[1] === "POST").map((c) => c[0]), ["/api/sales/7/void", "/api/sales/7/unvoid"]);
  });
  test("csv preview posts the pasted text", async () => {
    globalThis.__fields.slCsv = "a,b\n";
    await m.slImportPreview();
    assert.deepEqual(calls.find((c) => c[0] === "/api/sales/import/preview")[2], { content: "a,b\n" });
  });
});
