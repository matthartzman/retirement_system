// Plan step 2.2: the sale-queue panel (dashboard_decomp_sales_queue.js) in the plain Node sandbox.
import { test, describe, before, beforeEach } from "node:test";
import assert from "node:assert/strict";

let m;
const calls = [];
const PANEL = {
  candidate: { candidate_id: 3, account: "Trust", symbol: "VTI", shares: 12, amount: 3000, sale_date: "2026-07-06", source: "monarch" },
  symbol: "VTI", shares: 12, confirmable: true, allocation: {}, only_exact_fit: null, year_end_case: false, settle_date: "2026-07-06",
  suggested_trade_date: "2026-07-03", tax_class: "taxable",
  lots: [{ lot_id: "0", purchase_date: "2023-01-10", remaining: 10, basis_per_share: 100, holding_period: "long", implied_gain: 1500 },
         { lot_id: "1", purchase_date: "2025-12-02", remaining: 5.5, basis_per_share: 200, holding_period: "short", implied_gain: 275 }],
  aids: { fifo: { allocation: { 0: 10, 1: 2 }, gain: 1600, complete: true }, hifo: { allocation: { 1: 5.5, 0: 6.5 }, gain: 1100, complete: true } },
};
before(async () => {
  globalThis.esc = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  globalThis.window = globalThis;
  globalThis.accountDisplayLabel = (a) => String(a).replace(/^Member_1_/, "Matt's ");
  const els = { sqRoot: { innerHTML: "" } };
  globalThis.document = { getElementById: (id) => els[id] || null };
  globalThis.api = async (url, opts) => {
    calls.push([url, opts && opts.method, opts && opts.body ? JSON.parse(opts.body) : null]);
    if (url.includes("/panel")) return { success: true, ...PANEL };
    if (url.startsWith("/api/sales/candidates?")) return { success: true, candidates: [PANEL.candidate], counts: { unmatched: 1 } };
    return { success: true, sale_ids: [1, 2] };
  };
  m = await import("../../frontend/js/dashboard_decomp_sales_queue.js");
});
beforeEach(() => { calls.length = 0; });

describe("allocation state", () => {
  test("Confirm only when the total equals the shares sold and no lot is over-allocated", () => {
    assert.equal(m.sqAllocationState(PANEL, {}).ok, false);
    assert.equal(m.sqAllocationState(PANEL, { 0: 10, 1: 2 }).ok, true);
    assert.equal(m.sqAllocationState(PANEL, { 0: 9, 1: 2 }).ok, false);
    const over = m.sqAllocationState(PANEL, { 0: 11, 1: 1 });
    assert.deepEqual(over.over, ["0"]);
    assert.equal(over.ok, false);
  });
  test("a holdings-import candidate is never confirmable", () => {
    assert.equal(m.sqAllocationState({ ...PANEL, confirmable: false }, { 0: 10, 1: 2 }).ok, false);
  });
});

describe("panel html", () => {
  test("no lot is pre-filled and Confirm starts disabled", () => {
    const html = m.sqPanelHtml(PANEL, { allocation: {}, tradeDate: "2026-07-03", taxClass: "taxable" });
    assert.match(html, /id="sqConfirm"[^>]*disabled/);
    assert.doesNotMatch(html, /data-lot="d" value="[^"]/);
    assert.match(html, /FIFO \(gain \$1,600\.00\)/);
  });
  test("the year-end case is highlighted", () => {
    assert.match(m.sqPanelHtml({ ...PANEL, year_end_case: true }, { allocation: {}, tradeDate: "", taxClass: "taxable" }), /Year-end/);
  });
  test("user text is escaped", () => {
    const html = m.sqQueueHtml([{ ...PANEL.candidate, account: "<img onerror=x>" }], null);
    assert.doesNotMatch(html, /<img/);
  });
});

describe("flow", () => {
  test("open, fill from an aid (saves nothing), confirm posts the allocation, undo posts undo", async () => {
    await m.sqOpen(3);
    m.sqFill("fifo");
    assert.deepEqual(calls.map((c) => c[1]), [undefined], "only the panel read so far");
    await m.sqConfirm();
    const post = calls.find((c) => c[1] === "POST");
    assert.equal(post[0], "/api/sales/candidates/3/confirm");
    assert.deepEqual(post[2].allocation, { 0: 10, 1: 2 });
    assert.equal(post[2].trade_date, "2026-07-03");
    calls.length = 0;
    await m.sqUndo(3);
    assert.equal(calls[0][0], "/api/sales/candidates/3/undo");
  });
});
