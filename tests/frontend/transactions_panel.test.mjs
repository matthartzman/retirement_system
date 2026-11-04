// Transactions history (dashboard_decomp_transactions.js): read-only list of buys, reinvestments and sales, shown as the
// "History & held lots" mode of the Transaction log section.
import { test, before } from "node:test";
import assert from "node:assert/strict";

let m;
before(async () => {
  globalThis.esc = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  globalThis.window = globalThis;
  globalThis.accountDisplayLabel = (a) => String(a).replace(/^Member_1_/, "Matt's ");
  globalThis.document = { getElementById: () => null };
  globalThis.api = async () => ({ rows: [], held: [] });
  m = await import("../../frontend/js/dashboard_decomp_transactions.js");
});

const VIEW = {
  rows: [{ date: "2026-05-12", account: "Member_1_IRA", type: "buy", symbol: "TOTL", shares: 10, price: 100, amount: -1000, remaining: 4, linked: null, source: "broker" },
    { date: "2026-08-20", account: "Member_1_IRA", type: "sell", symbol: "<b>X</b>", shares: 1000, price: 0.01, amount: 10, remaining: null, linked: "confirmed", source: "broker" }],
  held: [{ account: "Member_1_IRA", symbol: "TOTL", purchase_date: "2026-05-12", shares: 4, price: 100 }],
};

test("renders friendly account names and remaining shares", () => {
  const h = m.trHtml(VIEW);
  assert.match(h, /Matt's IRA/);
  assert.match(h, /Sale \/ redemption/);
  assert.match(h, /<td class="rc-num">4<\/td>/);
});

test("Held filter lists only open lots", () => {
  assert.doesNotMatch(m.trHtml(VIEW, { account: "", symbol: "", year: "", type: "", held: false }), /Lots held/);
  const h = m.trHtml(VIEW, { account: "", symbol: "", year: "", type: "", held: true });
  assert.match(h, /Lots held/);
  assert.match(h, /2026-05-12/);
});

test("escapes user text", () => {
  assert.doesNotMatch(m.trHtml(VIEW), /<b>X<\/b>/);
  assert.match(m.trHtml(VIEW), /&lt;b&gt;X&lt;\/b&gt;/);
});

// Task 11 (deliberate update): the standalone <details ontoggle="trToggle…"> wrapper and its own filter bar are gone;
// trHtml is the pure History & held lots body of the merged Transaction log section, which owns the filters.
test("trHtml is the history body only: no details wrapper, no filter bar, no own count", () => {
  const h = m.trHtml(VIEW);
  assert.match(h, /^<table class="rc-table">/);
  assert.doesNotMatch(h, /<details|ontoggle|trToggle/);
  assert.doesNotMatch(h, /id="trAccount"|id="trHeld"|Held only/);
  assert.doesNotMatch(h, /\(2\)/);
  assert.equal(m.trToggle, undefined);
  assert.equal(m.renderTransactions, undefined);
});

test("trLoad sends the given filters to the server exactly as the old panel did", async () => {
  const urls = [];
  const orig = globalThis.api;
  globalThis.api = async (url) => { urls.push(url); return VIEW; };
  try {
    await m.trLoad({ account: "Member_1_IRA", symbol: "TOTL", year: "2026", type: "buy", held: true });
    await m.trLoad({ account: "", symbol: "", year: "", type: "", held: false });
    assert.deepEqual(urls, ["/api/transactions?account=Member_1_IRA&symbol=TOTL&year=2026&type=buy&held=1", "/api/transactions?"]);
    assert.match(m.trHtml(m.trState().view), /Matt's IRA/);
  } finally { globalThis.api = orig; }
});
