// Transactions panel (dashboard_decomp_transactions.js): read-only list of buys, reinvestments and sales.
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
