// Investment Holdings tab host: tabs, deep links, remembered tab, back link.
import { test, describe, before } from "node:test";
import assert from "node:assert/strict";

let m;
before(async () => {
  globalThis.window = globalThis;
  m = await import("../../frontend/js/dashboard_decomp_holdings_tabs.js");
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
