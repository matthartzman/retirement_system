// Sales Ledger v3: Tax year headings follow the Year control, and fund types are a table with one select per symbol.
import { test, describe, before } from "node:test";
import assert from "node:assert/strict";

let tax;
before(async () => {
  globalThis.esc = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  globalThis.window = globalThis;
  globalThis.accountDisplayLabel = (a) => String(a);
  globalThis.document = { getElementById: () => null };
  globalThis.api = async (url) => {
    if (url.startsWith("/api/sales/tax-year")) return SUMMARY(Number(new URL("http://x" + url).searchParams.get("year")));
    if (url.startsWith("/api/investment-income")) return INCOME(Number(new URL("http://x" + url).searchParams.get("year")));
    return { success: true, steps: [] };
  };
  tax = await import("../../frontend/js/dashboard_decomp_sales_tax.js");
});

const SUMMARY = (year) => ({ success: true, year, filing: "MFJ", limit: 3000, netting: { net_st: 1, net_lt: 2, ordinary_offset: 0, carryforward_st: 0, carryforward_lt: 0, gain_to_tax_ordinary: 1, gain_to_tax_ltcg: 2 },
  carryforward_in: { short: 0, long: 5, entered: false }, carryforward_out: { short: 0, long: 0 }, totals: { count: 2, st_gain: 1, lt_gain: 2 },
  wash: { count: 0, all_years_count: 0, flagged_loss: 0, rows: [] }, realized_tax: { available: true, ordinary_tax: 1, ltcg_tax: 1, niit: 0, state_tax: 0, total: 2, note: "n" } });
const INCOME = (year) => ({ success: true, year, rows: [1], totals: { interest: 10 }, by_account: { Trust_A: { interest: 10 } }, labels: { interest: "Interest", qualified: "Qualified" },
  symbols: [{ symbol: "VTI", type: "qualified" }, { symbol: "BND", type: "interest" }, { symbol: "VXUS", type: "qualified" }], notes: ["note"] });
const headings = (html) => [...html.matchAll(/<h[34][^>]*>([\s\S]*?)<\/h[34]>/g)].map((x) => x[1]);

describe("Tax year headings come from the Year control", () => {
  test("no heading contains a hardcoded year", async () => {
    for (const year of [2031, 2019]) {
      await tax.loadSalesTaxYear(year);
      const hs = headings(tax.renderSalesTaxYear());
      assert.ok(hs.length >= 3);
      const years = hs.join(" ").match(/\b(19|20)\d\d\b/g) || [];
      assert.ok(years.length > 0 && years.every((y) => [String(year), String(year - 1)].includes(y)), `${year}: ${years}`);
    }
  });
  test('carryforward label reads "Loss carried in from {Year-1}"', async () => {
    await tax.loadSalesTaxYear(2031);
    assert.match(tax.renderSalesTaxYear(), /<h4>Loss carried in from 2030<\/h4>/);
    assert.doesNotMatch(tax.renderSalesTaxYear(), /Capital-loss carryforward into/);
  });
  test("fund types render one select per symbol in a two-column table", async () => {
    await tax.loadSalesTaxYear(2031);
    const html = tax.renderSalesTaxYear();
    const table = html.slice(html.indexOf('class="rc-table st-types"'));
    assert.equal((table.slice(0, table.indexOf("</table>")).match(/<select/g) || []).length, 3);
    assert.match(table, /<th>Symbol<\/th><th>Counted as<\/th>/);
    assert.doesNotMatch(html, /type="radio"/);
  });
});
