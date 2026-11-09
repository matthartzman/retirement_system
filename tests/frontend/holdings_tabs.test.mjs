// Investment Holdings tab host: tabs, deep links, remembered tab, back link.
import { test, describe, before } from "node:test";
import assert from "node:assert/strict";

let m, tree;
before(async () => {
  globalThis.window = globalThis;
  globalThis.esc = (t) => String(t ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  globalThis.renderMain = () => {};
  globalThis.setTimeout = () => 0;
  Object.assign(globalThis, { holdingLotCurrentValue: (r) => ({ value: Number(r.shares) * 100, isEstimate: false }), isCash: (s) => s === "CASH", isTBill: () => false });
  m = await import("../../frontend/js/dashboard_decomp_holdings_tabs.js");
  tree = await import("../../frontend/js/dashboard_decomp_holdings_tree.js");
});
const mem = (v) => ({ getItem: () => v ?? null, setItem(_k, x) { v = x; }, get raw() { return v; } });

describe("holdings tabs", () => {
  test("HOLDINGS_TABS lists Positions, Activity and Import in order", () => {
    assert.deepEqual(m.HOLDINGS_TABS, [["positions", "Positions"], ["activity", "Activity"], ["import", "Import"]]);
  });
  test("parses an activity deep link into filters", () => {
    assert.deepEqual(m.hsParseHash("#holdings/activity?account=Matt_Trust&symbol=ITOT&type=opening&source=backfill&year=2026&back=sales"),
      { tab: "activity", account: "Matt_Trust", symbol: "ITOT", type: "opening", source: "backfill", year: "2026", back: "sales" });
    assert.equal(m.hsParseHash("#sales_ledger?tab=fix"), null);
    assert.equal(m.hsParseHash(""), null);
  });
  test("round-trips hsActivityLink and hsParseHash", () => {
    const f = { account: "Matt's Trust", symbol: "ITOT", type: "buy", year: "2026", back: "sales" };
    const link = m.hsActivityLink(f);
    assert.equal(link, "#holdings/activity?account=Matt's%20Trust&symbol=ITOT&type=buy&year=2026&back=sales");
    assert.deepEqual(m.hsParseHash(link), { tab: "activity", source: "", ...f });
    assert.equal(m.hsActivityLink({}), "#holdings/activity");
  });
  test("unknown tab falls back to positions", () => {
    assert.equal(m.hsParseHash("#holdings/nonsense?account=A").tab, "positions");
    assert.equal(m.hsParseHash("#holdings").tab, "positions");
    assert.equal(m.hsInitial("", mem(JSON.stringify("bogus"))).tab, "positions");
  });
  test("a deep link survives a page reload: the hash wins over the remembered tab", () => {
    const st = m.hsInitial("#holdings/activity?account=Matt_Trust&back=sales", mem(JSON.stringify("import")));
    assert.equal(st.tab, "activity");
    assert.equal(st.filters.account, "Matt_Trust");
    assert.equal(m.hsInitial("", mem(JSON.stringify("import"))).tab, "import");        // no link: the remembered tab
    assert.equal(m.hsInitial("", { getItem() { throw new Error("off"); } }).tab, "positions");
  });
  test('back=sales shows "← Back to Sales Ledger"', () => {
    assert.match(m.hsBackHtml({ back: "sales" }), /← Back to Sales Ledger/);
    assert.equal(m.hsBackHtml({ back: "" }), "");
  });
  test("the tab bar marks the active tab", () => {
    const h = m.hsTabBarHtml("activity");
    assert.equal((h.match(/aria-selected="true"/g) || []).length, 1);
    assert.match(h, /id="hs-t-activity"[^>]*aria-selected="true"/);
  });
  test("renderHoldingsTabs shows only the active tab's panel", () => {
    globalThis.localStorage = mem();
    m.hsSetTab("positions");
    const h = m.renderHoldingsTabs(() => "<p>POS</p>");
    assert.match(h, /<p>POS<\/p>/);
    assert.doesNotMatch(h, /hs-back/);
    delete globalThis.localStorage;
  });
});

describe("Positions markers and cross-links", () => {
  const LOTS = [
    { account: "Matt_Trust", symbol: "ITOT", purchase_date: "", shares: 10, basis: 900, value: 1000, asset_class: "Equity", subclass: "US" },
    { account: "Matt_Trust", symbol: "ITOT", purchase_date: "2025-03-04", shares: 5, basis: 500, value: 520, asset_class: "Equity", subclass: "US" },
    { account: "Hand_Brokerage", symbol: "QQQ", purchase_date: "", shares: 2, basis: 100, value: 120, asset_class: "Equity", subclass: "US" }];
  const render = () => {
    window.holdingsTreeOrder = ["lot"];
    window.managedHoldingAccounts = ["Matt_Trust"];
    window.isManagedHoldingAccount = (a) => window.managedHoldingAccounts.includes(a);
    return tree.renderHoldingsTree(LOTS.map((l) => ({ ...l, purchase_price: l.basis / l.shares })), (a) => a);
  };
  const lotRow = (h, i) => h.split('<tr class="ht-row ht-lot"')[i + 1].split("</tr>")[0];
  test("backfilled lot row shows the date-not-on-file chip and Fix date", () => {
    const h = render();
    const undated = lotRow(h, 1);                                         // newest first: 2025-03-04 is row 0, the undated lot row 1
    assert.match(undated, /date not on file/);
    assert.match(undated, /href="#holdings\/activity\?account=Matt_Trust&amp;symbol=ITOT&amp;type=opening&amp;source=backfill">Fix date</);
    assert.doesNotMatch(lotRow(h, 0), /date not on file/);
  });
  test("managed row shows an Edit in Activity link; an unmanaged row does not", () => {
    const h = render();
    assert.match(lotRow(h, 0), />Edit in Activity</);
    assert.doesNotMatch(h.slice(h.indexOf("Hand_Brokerage")), /Edit in Activity|date not on file/);
  });
  test("History link opens Activity filtered to the account and symbol", () => {
    assert.match(lotRow(render(), 0), /href="#holdings\/activity\?account=Matt_Trust&amp;symbol=ITOT">History</);
  });
  test("a holding-period check Review link carries source=backfill and the year", async () => {
    const led = await import("../../frontend/js/dashboard_decomp_sales_ledger.js");
    const h = led.slHpHtml({ lots: 2, sales: 3 }, "2026");
    assert.match(h, /3 sale rows use 2 lots with no purchase date on file/);
    assert.match(h, /href="#holdings\/activity\?type=opening&amp;source=backfill&amp;year=2026&amp;back=sales">Review in Activity</);
    assert.equal(led.slHpHtml({ lots: 0, sales: 0 }, "2026"), "");
  });
  test("the toolbar says whether the log agrees with the holdings", async () => {
    const log = await import("../../frontend/js/dashboard_decomp_transactions_log.js");
    assert.match(log.tlStatusHtml(), /id="tlStatusRoot"/);
  });
});

describe("wash markers on Positions", () => {
  test("adjusted lot shows incl. wash marker and adjusted unit cost", async () => {
    const log = await import("../../frontend/js/dashboard_decomp_transactions_log.js");
    globalThis.api = async (url) => (url === "/api/transactions/log" ? { started: true, rows: [], drift: [], open: [
      { account: "Spouse_Trust", symbol: "VTI", purchase_date: "2026-06-15", tacked_date: "2024-01-10", adjusted_unit_cost: 105, wash_adjustment: 400, shares: 20 }] } : { success: true });
    globalThis.document = { getElementById: () => null };
    await log.tlLoad();
    globalThis.renderMain = () => {};
    window.holdingsTreeOrder = ["lot"];
    window.managedHoldingAccounts = [];
    const html = tree.renderHoldingsTree([{ account: "Spouse_Trust", symbol: "VTI", purchase_date: "2024-01-10", shares: 20, purchase_price: 105 }], (a) => a);
    assert.match(html, /incl\. \$400\.00 wash/);
    assert.match(html, /title="Includes \$400\.00 of a disallowed wash-sale loss; the holding period counts from 2024-01-10"/);
    assert.match(html, /slGo\('fix','wash'\)/);
    assert.match(html, /\$105/);                                  // the unit cost shown is the adjusted one
  });
  test("lot with no adjustment shows no marker", () => {
    window.holdingsTreeOrder = ["lot"];
    const html = tree.renderHoldingsTree([{ account: "Spouse_Trust", symbol: "VTI", purchase_date: "2025-01-10", shares: 20, purchase_price: 100 }], (a) => a);
    assert.doesNotMatch(html, /wash<\/a>|incl\./);
  });
});
