// Plan 7.2 / 3a.3 gap (a): stTaxHtml, the "Tax on gains realized" table of the Sales Ledger tax-year panel (dashboard_decomp_sales_tax.js).
import { test, describe, before } from "node:test";
import assert from "node:assert/strict";

let m;
const TAX = {
  available: true, method: "planner", ordinary_income: 90600, magi: 90600, ordinary_tax: 1200, ltcg_tax: 3000, niit: 0, state_tax: 0, total: 4200,
  note: "Estimate: gains are stacked on the plan's pension, taxable Social Security. Retirement withdrawals and required minimum distributions are not included.",
};
const SUMMARY = (tax) => ({ year: 2026, ...(tax === undefined ? {} : { realized_tax: tax }) });
before(async () => {
  globalThis.esc = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  globalThis.window = globalThis;
  globalThis.document = { getElementById: () => null };
  globalThis.api = async () => ({ success: true });
  m = await import("../../frontend/js/dashboard_decomp_sales_tax.js");
});

describe("stTaxHtml", () => {
  test("an empty ledger sends no realized_tax and draws nothing", () => {
    assert.equal(m.stTaxHtml(SUMMARY()), "");
  });
  test("shows each tax part, the total, and the estimate note naming what is included", () => {
    const html = m.stTaxHtml(SUMMARY(TAX));
    assert.match(html, /Tax on gains realized in 2026/);
    assert.match(html, /Federal tax on ordinary gain[\s\S]*\$1,200\.00/);
    assert.match(html, /Federal tax on long-term gain[\s\S]*\$3,000\.00/);
    assert.match(html, /Net investment income tax[\s\S]*\$0\.00/);
    assert.match(html, /State tax[\s\S]*\$0\.00/);
    assert.match(html, /Estimated tax on gains realized this year[\s\S]*\$4,200\.00/);
    assert.match(html, /Estimate: gains are stacked on the plan&#39;s pension, taxable Social Security/);
    assert.match(html, /Separate from the estimated tax on unrealized gains/);
  });
  test("an unavailable estimate shows only its reason, with no figures", () => {
    const html = m.stTaxHtml(SUMMARY({ available: false, reason: "The plan is not complete enough to price tax." }));
    assert.match(html, /not complete enough to price tax/);
    assert.doesNotMatch(html, /\$|<table/);
  });
  test("an unavailable estimate with no reason falls back to a plain sentence", () => {
    assert.match(m.stTaxHtml(SUMMARY({ available: false })), /not available/);
  });
  test("the note is escaped", () => {
    assert.doesNotMatch(m.stTaxHtml(SUMMARY({ ...TAX, note: "<b>x</b>" })), /<b>x/);
  });
});
