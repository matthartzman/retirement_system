// Sales Ledger v3: the Record sales grid and lot chooser (pure helpers plus the rendered chooser and grid).
import { test, describe, before } from "node:test";
import assert from "node:assert/strict";

let m;
before(async () => {
  globalThis.esc = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  globalThis.window = globalThis;
  globalThis.accountDisplayLabel = (a) => String(a).replace(/^Matt_/, "Matt's ");
  globalThis.api = async (url) => {
    if (url.startsWith("/api/sales/open-lots")) return { success: true, lots: [], log_started: true, nearby_buys: [] };
    return { success: true };
  };
  m = await import("../../frontend/js/dashboard_decomp_sales_entry.js");
});

const LOTS = [
  { txn_id: 1, purchase_date: "2024-01-10", open_shares: 100, unit_cost: 90, term: "long" },
  { txn_id: 2, purchase_date: "2025-06-01", open_shares: 50, unit_cost: 130, term: "long" },
  { txn_id: 3, purchase_date: "2026-03-04", open_shares: 50, unit_cost: 110, term: "short" },
];

describe("seFill", () => {
  test("fifo fills oldest first", () => assert.deepEqual(m.seFill(LOTS, 120, "fifo"), { 1: 100, 2: 20 }));
  test("hifo fills highest cost first", () => assert.deepEqual(m.seFill(LOTS, 60, "hifo"), { 2: 50, 3: 10 }));
  test("losses fills lowest gain first at the sale price", () => {
    assert.deepEqual(m.seFill(LOTS, 60, "losses", 120), { 2: 50, 3: 10 });   // cost 130 loses most, then 110, then 90
    assert.deepEqual(m.seFill(LOTS, 100, "losses", 200), { 3: 50, 2: 50 }); // all gain: smallest gain (highest cost) first
  });
  test("selling more than is open fills what there is", () => assert.equal(Object.values(m.seFill(LOTS, 500, "fifo")).reduce((a, b) => a + b, 0), 200));
});

describe("seRowState and saving", () => {
  const row = (picks, over = {}) => ({ shares: 200, proceeds: 24000, fees: 0, taxable: true, picks, ...over });
  test('label reads "2 lots ✓" when matched and "0 / 200 · pick" when not', () => {
    assert.equal(m.seRowState(row([{ shares: 100, unit_cost: 90, term: "long" }, { shares: 100, unit_cost: 130, term: "long" }])).label, "2 lots ✓");
    assert.equal(m.seRowState(row([])).label, "0 / 200 · pick");
    assert.equal(m.seRowState(row([{ shares: 50, unit_cost: 90 }])).label, "50 / 200 · pick");
  });
  test("gain is proceeds minus fees minus basis; term is Mixed when lots differ", () => {
    const s = m.seRowState(row([{ shares: 100, unit_cost: 90, term: "long" }, { shares: 100, unit_cost: 110, term: "short" }], { fees: 10 }));
    assert.equal(s.gain, 24000 - 10 - 20000);
    assert.equal(s.term, "Mixed");
  });
  test("save is disabled until every row is matched", () => {
    const ok = row([{ shares: 200, unit_cost: 90 }]);
    assert.equal(m.seCanSave([ok]), true);
    assert.equal(m.seCanSave([ok, row([])]), false);
    assert.equal(m.seCanSave([]), false);
  });
  test('non-taxable account row reads "not taxable"', () => {
    const s = m.seRowState(row([{ shares: 200, unit_cost: 90 }], { taxable: false }));
    assert.equal(s.gain, null);
    assert.equal(s.gainText, "not taxable");
  });
  test("Enter in the last field of the last row adds a row; elsewhere it moves on", () => {
    const rows = [{}, {}];
    assert.equal(m.seKeyAction(rows, 1, 5, "Enter"), "add-row");
    assert.equal(m.seKeyAction(rows, 0, 5, "Enter"), "next");
    assert.equal(m.seKeyAction(rows, 1, 2, "Enter"), "next");
    assert.equal(m.seKeyAction(rows, 1, 5, "a"), "none");
  });
  test("batch rows split proceeds and fees across lots, last takes the remainder, and link the log lot", () => {
    const out = m.seBatchRows([{ account: "Matt_Trust", symbol: "ITOT", date: "2026-09-01", shares: 3, proceeds: 100, fees: 1,
      picks: [{ txn_id: 7, purchase_date: "2024-01-10", shares: 1, unit_cost: 10 }, { txn_id: 8, purchase_date: "2025-01-10", shares: 2, unit_cost: 20 }] }]);
    assert.equal(out.length, 2);
    assert.equal(+(out[0].proceeds + out[1].proceeds).toFixed(2), 100);
    assert.equal(+(out[0].fees + out[1].fees).toFixed(2), 1);
    assert.deepEqual(out.map((r) => r.txn_lot), [7, 8]);
    assert.deepEqual(out.map((r) => r.basis), [10, 40]);
    assert.equal("tax_class" in out[0], false);                           // the account sets the class
  });
});

describe("chooser", () => {
  const r = { id: 1, account: "Matt_Trust", symbol: "ITOT", date: "2026-09-01", shares: 60, proceeds: 7200, fees: 0, picks: [] };
  test("an account with no log shows blank lot rows (Bought, Shares, Basis)", () => {
    const h = m.seChooserHtml({ ...r, picks: [{ purchase_date: "", shares: "", basis: "" }] }, { lots: [], log_started: false });
    assert.match(h, /Bought <input type="date"/);
    assert.match(h, /Basis \$ <input/);
    assert.match(h, /add lot/);
  });
  test("an empty chooser renders a link to Holdings Activity for that account and symbol", () => {
    const h = m.seChooserHtml(r, { lots: [], log_started: true });
    assert.match(h, /No open lots of ITOT in Matt&#39;?s Trust|No open lots of ITOT in Matt's Trust/);
    assert.match(h, /href="#holdings\/activity\?account=Matt_Trust&amp;symbol=ITOT&amp;type=buy&amp;back=sales"/);
  });
  test("lots render with a Fill row, a checkbox and a Selected total", () => {
    const h = m.seChooserHtml({ ...r, picks: [{ txn_id: 3, purchase_date: "2026-03-04", shares: 50, unit_cost: 110, term: "short" }] }, { lots: LOTS, log_started: true });
    for (const t of ["FIFO", "Highest cost", "Losses first", "Clear", "Open shares", "Cost / share", "Sell shares", "Selected"]) assert.ok(h.includes(t), t);
    assert.equal((h.match(/type="checkbox"/g) || []).length, 3);
    assert.equal((h.match(/ checked /g) || []).length, 1);
  });
});

describe("grid", () => {
  test("renders column headings, one blank row and a disabled Save", () => {
    m.seSetAccounts({ Matt_Trust: "taxable", Matt_IRA: "pre_tax" });
    m.seOpen();
    const h = m.renderSalesEntry();
    for (const t of ["Account", "Symbol", "Sale date", "Shares", "Proceeds", "Fees", "Lots", "Gain", "Add row", "Save 1 sale"]) assert.ok(h.includes(t), t);
    assert.match(h, /id="seSave" type="button" disabled/);
    assert.match(h, /Matt&#39;?s Trust \(taxable\)|Matt's Trust \(taxable\)/);
    assert.match(h, /Matt's IRA \(pre-tax\)|Matt&#39;s IRA \(pre-tax\)/);
    m.seClose();
  });
});

describe("review fixes", () => {
  test("an edited sale offers no add-lot button (it is exactly one lot)", () => {
    m.seSetAccounts({ Matt_Trust: "taxable" });
    m.seEdit({ sale_id: 7, account: "Matt_Trust", symbol: "ITOT", sale_date: "2026-09-01", shares: 5, proceeds: 500, fees: 0, basis: 400, purchase_date: "2025-01-01", holding_period: "long", tax_class: "taxable" });
    const h = m.renderSalesEntry();
    assert.match(h, /Bought <input type="date"/);
    assert.doesNotMatch(h, /add lot/);
    m.seClose();
  });
});
