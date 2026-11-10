// Sales Ledger v3: grouping ledger lot rows into one row per sale.
import { test, describe, before } from "node:test";
import assert from "node:assert/strict";

let m;
before(async () => {
  globalThis.window = globalThis;
  m = await import("../../frontend/js/dashboard_decomp_sales_group.js");
});

const lot = (over) => ({ sale_id: 1, account: "Trust_A", symbol: "VTI", sale_date: "2026-06-10", shares: 5, proceeds: 500, basis: 400, gain: 100, holding_period: "long", wash_flag: "none", ...over });

describe("slGroupSales", () => {
  test("groups two same-day same-symbol orders into one sale", () => {
    const g = m.slGroupSales([lot({ sale_id: 1 }), lot({ sale_id: 2, shares: 3, proceeds: 330, basis: 300, gain: 30 })]);
    assert.equal(g.length, 1);
    assert.equal(g[0].key, "Trust_A|VTI|2026-06-10");
    assert.equal(g[0].shares, 8);
    assert.equal(g[0].proceeds, 830);
    assert.equal(g[0].gain, 130);
    assert.equal(g[0].lots.length, 2);
  });
  test('groups lots of mixed term as "Mixed"', () => {
    const g = m.slGroupSales([lot({}), lot({ sale_id: 2, holding_period: "short" })]);
    assert.equal(g[0].term, "Mixed");
  });
  test("a single lot is a single-row sale", () => {
    const g = m.slGroupSales([lot({ wash_flag: "possible" })]);
    assert.equal(g.length, 1);
    assert.equal(g[0].term, "long");
    assert.equal(g[0].wash, true);
  });
  test("different accounts or days stay apart, newest first", () => {
    const g = m.slGroupSales([lot({}), lot({ account: "Trust_B" }), lot({ sale_date: "2026-07-01" })]);
    assert.equal(g.length, 3);
    assert.equal(g[0].sale_date, "2026-07-01");
  });
});
