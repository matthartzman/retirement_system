// Sales Ledger v3: the wash-sale cards in To fix.
import { test, describe, before } from "node:test";
import assert from "node:assert/strict";

let w;
const calls = [];
const CARD = { sale_key: "Matt_Trust|MUB|2026-04-01", account: "Matt Trust", symbol: "MUB", sale_date: "2026-04-01", lots: 3, shares: 160.848, proceeds: 17000, loss: 123.61, disallowed: 0.98, deductible: 122.63,
  matches: [{ txn_id: 5, label: "Pat Trust", account: "Pat_Trust", date: "2026-04-10", shares: 0.86, value: 92.5, is_reinvest: true, taxable: true, amount: 0.66, where: "adds $0.66 to the cost of this lot" },
    { txn_id: 6, label: "Pat Roth", account: "Pat_Roth", date: "2026-04-20", shares: 0.412, value: 44, is_reinvest: false, taxable: false, amount: 0.32, where: "lost permanently" }] };
before(async () => {
  globalThis.esc = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  globalThis.window = globalThis;
  globalThis.slMoney = (v) => (v < 0 ? "-$" : "$") + Math.abs(v).toFixed(2);
  globalThis.setTimeout = () => 0;
  globalThis.slCurrentYear = () => "2026";
  globalThis.document = { getElementById: () => null };
  globalThis.api = async (url, opts) => { calls.push([url, opts && opts.method, opts && opts.body ? JSON.parse(opts.body) : null]); return url.startsWith("/api/sales/wash?") ? { success: true, cards: [CARD], reviewed: [{ sale_key: "Matt_Trust|VTI|2026-03-01", outcome: "not_wash", reason: "other: x" }] } : { success: true }; };
  w = await import("../../frontend/js/dashboard_decomp_sales_wash.js");
});

describe("wash cards", () => {
  test("card shows both sides with friendly names", () => {
    const h = w.swCardHtml(CARD, 0);
    for (const t of ["MUB · Matt Trust · 2026-04-01", "Sold at a loss", "Pat Trust bought 0.86 on 2026-04-10", "(dividend reinvest)", "Pat Roth bought 0.412"]) assert.ok(h.includes(t), t);
    assert.match(h, /adds \$0\.66 to the cost of this lot/);
    assert.match(h, /Disallowed \$0\.98 of \$123\.61 · \$122\.63 still deductible/);
    assert.doesNotMatch(h, /Pat_Trust"?>|Matt_Trust<|Member_1/);
  });
  test('IRA replacement renders "lost permanently" in red', () => {
    assert.match(w.swCardHtml(CARD, 0), /<span class="field-error">lost permanently<\/span>/);
  });
  test("the review control offers the three outcomes", () => {
    const h = w.swCardHtml(CARD, 0);
    for (const t of ["Wash sale", "Broker already reported it", "Not a wash sale…"]) assert.ok(h.includes(t), t);
  });
  test("Not a wash sale without a reason is rejected; the other outcomes need none", () => {
    assert.match(w.swValidate("not_wash", "  "), /Say why/);
    assert.equal(w.swValidate("not_wash", "not substantially identical"), "");
    assert.equal(w.swValidate("wash", ""), "");
    assert.equal(w.swValidate("broker_reported", ""), "");
  });
  test("Reviewed list shows Undo and undo posts the clear route", async () => {
    await w.loadSalesWash();
    const h = w.swHtml();
    assert.match(h, /<summary>Reviewed \(1\)<\/summary>/);
    assert.match(h, /onclick="swUndo\(0\)">Undo</);
    calls.length = 0;
    await w.swUndo(0);
    assert.deepEqual(calls.find((c) => c[1] === "POST"), ["/api/sales/wash/review/clear", "POST", { sale_key: "Matt_Trust|VTI|2026-03-01" }]);
  });
  test("the summary counts cards and an empty list says so", async () => {
    await w.loadSalesWash();
    assert.deepEqual(w.swSummary(), { count: 1, tone: "bad", text: "1 to review" });
    assert.equal(w.swHtml({ cards: [], reviewed: [] }).includes("No wash sales to review"), true);
  });
});

describe("wash summary", () => {
  test("never run and stale warn when nothing is flagged; flagged cards are bad", async () => {
    const run = async (extra) => { globalThis.api = async () => ({ success: true, cards: [], reviewed: [], ...extra }); await w.loadSalesWash(); return w.swSummary(); };
    assert.deepEqual(await run({ run: { never_run: true, stale: false } }), { count: 0, tone: "warn", text: "never run" });
    assert.deepEqual(await run({ run: { never_run: false, stale: true } }), { count: 0, tone: "warn", text: "stale" });
    assert.deepEqual(await run({ run: { never_run: false, stale: false } }), { count: 0, tone: "", text: "" });
    assert.deepEqual(await run({ cards: [CARD], run: { never_run: true } }), { count: 1, tone: "bad", text: "1 to review" });
  });
});

describe("open windows", () => {
  const W = [{ sale_key: "A|VTI|2026-11-06", symbol: "VTI", closes_on: "2026-12-06", reinvesting: ["Pat's IRA", "Pat's Roth"], also_holds: ["Pat's 401k"] }];
  test("names the accounts that have reinvested, the date the window closes, and never says reinvest is on", () => {
    const h = w.swWindowsHtml(W);
    assert.match(h, /the window is open until 12-06/);
    assert.match(h, /Turn off reinvest for VTI in Pat&#39;?s IRA, Pat&#39;?s Roth|Turn off reinvest for VTI in Pat's IRA, Pat's Roth/);
    assert.match(h, /has reinvested in the last 12 months/);
    assert.match(h, /Also holds VTI: Pat(&#39;|')s 401k \(no recent reinvest; check contributions\)/);
    assert.doesNotMatch(h, /reinvest on/i);
    assert.equal(w.swWindowsHtml([]), "");
  });
});
