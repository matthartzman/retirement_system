// W3-07 / UX-005: one tab-strip implementation; every strip emits aria-controls and a role=tabpanel panel.
import { test, describe, before } from "node:test";
import assert from "node:assert/strict";

let h, sl;
before(async () => {
  globalThis.window = globalThis;
  globalThis.renderMain = () => {};
  h = await import("../../frontend/js/dashboard_shared_helpers.js");
  sl = await import("../../frontend/js/dashboard_decomp_sales_ledger_ui.js");
});

describe("shared tab strip", () => {
  test("bar: one tabindex=0, aria-controls per tab, ids match the panel", () => {
    const bar = globalThis.tabBarHtml("zz", [["a", "A"], ["b", "B"]], "b", "pick", "Demo sections");
    assert.match(bar, /role="tablist"/);
    assert.equal((bar.match(/tabindex="0"/g) || []).length, 1);
    assert.ok(bar.includes('aria-controls="zz-p-a"') && bar.includes('aria-controls="zz-p-b"'));
    const panel = globalThis.tabPanelHtml("zz", "b", "<p>x</p>");
    assert.ok(panel.includes('role="tabpanel"') && panel.includes('id="zz-p-b"') && panel.includes('aria-labelledby="zz-t-b"'));
  });
  test("a tab id with spaces is slugged to one IDREF token", () => {
    assert.equal(globalThis.tabSlug("This year"), "this-year");
  });
  test("the Sales Ledger strip is built by the shared helper", () => {
    const bar = sl.slTabBarHtml("fix", {});
    assert.match(bar, /onclick="tabSelect\('sl','slSetTab','fix'\)"/);
    assert.match(bar, /onkeydown="tabKeydown\(event,'sl','slSetTab'\)"/);
  });
});
