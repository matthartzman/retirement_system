// Plan step 2.2 follow-up: the bulk review list (dashboard_decomp_sales_bulk.js) in the plain Node sandbox.
import { test, describe, before, beforeEach } from "node:test";
import assert from "node:assert/strict";

let m;
const calls = [];
let reply = {};
const LOTS = [{ lot_id: "0", purchase_date: "2023-01-10", remaining: 10, basis_per_share: 100, holding_period: "long", implied_gain: 1500 },
              { lot_id: "1", purchase_date: "2025-12-02", remaining: 5.5, basis_per_share: 200, holding_period: "short", implied_gain: 275 }];
const item = (id, shares, alloc) => ({
  ok: true, candidate_id: id, candidate: { candidate_id: id, account: "Trust", symbol: "VTI", shares, amount: shares * 250, sale_date: "2026-07-06", source: "monarch" },
  symbol: "VTI", shares, confirmable: true, refusal: null, year_end_case: false, suggested_trade_date: "2026-07-03", tax_class: "taxable",
  lots: LOTS, allocation: alloc, method: "fifo",
  aids: { fifo: { allocation: alloc, gain: 100, complete: true }, hifo: { allocation: { 1: 4 }, gain: 40, complete: true } },
});
const els = {};
before(async () => {
  globalThis.esc = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  globalThis.window = globalThis;
  globalThis.accountDisplayLabel = (a) => String(a);
  globalThis.document = { getElementById: (id) => els[id] || (els[id] = { innerHTML: "", textContent: "", disabled: false }) };
  globalThis.api = async (url, opts) => {
    calls.push([url, opts && opts.method, opts && opts.body ? JSON.parse(opts.body) : null]);
    const key = Object.keys(reply).find((k) => url.includes(k));
    return key ? reply[key] : { success: true, candidates: [], counts: { unmatched: 0 } };
  };
  m = await import("../../frontend/js/dashboard_decomp_sales_bulk.js");
});
beforeEach(() => { calls.length = 0; reply = {}; });

describe("item state", () => {
  test("ready only when allocated shares equal the sale and no lot is over its remaining shares", () => {
    const i = item(1, 12, { 0: 10, 1: 2 });
    assert.equal(m.sbItemState(i, { 0: 10, 1: 2 }).ok, true);
    assert.equal(m.sbItemState(i, { 0: 10 }).ok, false);
    assert.deepEqual(m.sbItemState(i, { 0: 11, 1: 1 }).over, ["0"]);
    assert.equal(m.sbItemState({ ...i, confirmable: false }, { 0: 10, 1: 2 }).ok, false);
    assert.equal(m.sbItemState({ ok: false }, {}).ok, false);
  });
  test("only ready drafts are sent", () => {
    const a = item(1, 12, { 0: 10, 1: 2 }), b = item(2, 4, {}), bad = { ok: false, candidate_id: 3, error: "x" };
    const drafts = { 1: { allocation: { 0: 10, 1: 2 } }, 2: { allocation: {} } };
    assert.deepEqual(m.sbReadyItems([a, b, bad], drafts).map((i) => i.candidate_id), [1]);
  });
});

describe("html", () => {
  test("queue rows carry checkboxes and select-all reflects the selection", () => {
    const cs = [{ candidate_id: 1, sale_date: "2026-07-06", account: "Trust", symbol: "VTI", shares: 4, amount: 1000 }, { candidate_id: 2, sale_date: "2026-07-07", account: "Trust", symbol: "", shares: null, amount: null }];
    const html = m.sbQueueHtml(cs, new Set([1]));
    assert.match(html, /sbToggle\(1, this\.checked\)/);
    assert.match(html, /needs detail/);
    assert.equal((html.match(/ checked /g) || []).length, 1);
    assert.match(m.sbQueueHtml([], new Set()), /No sales are waiting/);
  });
  test("an item shows FIFO as a filled draft with aid chips, and a failed item shows its reason", () => {
    const i = item(1, 12, { 0: 10, 1: 2 });
    const html = m.sbItemHtml(i, { allocation: { 0: 10, 1: 2 }, tradeDate: "2026-07-03", taxClass: "taxable" }, undefined);
    assert.match(html, /value="10"/);
    assert.match(html, /sbFill\(1, 'hifo'\)/);
    assert.match(html, /ready/);
    const failed = m.sbItemHtml(i, { allocation: { 0: 10, 1: 2 }, tradeDate: "d", taxClass: "taxable" }, { ok: false, error: "lot 0 is over-allocated" });
    assert.match(failed, /field-error">lot 0 is over-allocated/);
    assert.match(m.sbItemHtml({ ok: false, candidate_id: 9, error: "no sale candidate 9" }, {}, undefined), /no sale candidate 9/);
  });
});

describe("flows", () => {
  const list = { success: true, candidates: [{ candidate_id: 1, sale_date: "d", account: "Trust", symbol: "VTI", shares: 12, amount: 3000 }, { candidate_id: 2, sale_date: "d", account: "Trust", symbol: "VTI", shares: 4, amount: 1000 }], counts: { unmatched: 2 } };
  test("review -> confirm sends ready items, keeps a failed one, and offers one batch Undo", async () => {
    reply = { "/candidates?": list, "bulk/review": { success: true, items: [item(1, 12, { 0: 10, 1: 2 }), item(2, 4, { 0: 4 })] },
      "bulk/confirm": { success: true, results: [{ candidate_id: 1, ok: true }, { candidate_id: 2, ok: false, error: "boom" }], succeeded: 1, failed: 1, confirmed: [1] } };
    await m.loadSalesBulk();
    m.sbToggleAll(true);
    await m.sbReview();
    assert.deepEqual(calls.find((c) => c[0].endsWith("bulk/review"))[2], { candidate_ids: [1, 2] });
    m.sbSetAlloc(2, "0", "3");   // 2 now short: left out of the send
    await m.sbConfirmAll();
    const sent = calls.find((c) => c[0].endsWith("bulk/confirm"))[2].items;
    assert.deepEqual(sent.map((i) => i.candidate_id), [1]);
    assert.deepEqual(sent[0].allocation, { 0: 10, 1: 2 });
    assert.equal(sent[0].trade_date, "2026-07-03");
    const html = els.sbRoot.innerHTML;
    assert.match(html, /Confirmed 1 sale; 1 failed/);
    assert.match(html, /Undo batch/);
    assert.match(html, /id="sbItem2"/);
    assert.doesNotMatch(html, /id="sbItem1"/);
  });
  test("Undo batch sends the confirmed ids to bulk/undo", async () => {
    reply = { "bulk/undo": { success: true, results: [{ candidate_id: 1, ok: true }], succeeded: 1, failed: 0 }, "/candidates?": list };
    await m.sbUndoBatch();
    assert.deepEqual(calls.find((c) => c[0].endsWith("bulk/undo"))[2], { candidate_ids: [1] });
    assert.match(els.sbRoot.innerHTML, /Returned 1 sale to the queue and restored their lots/);
  });
  test("bulk dismiss sends the selection with a reason and offers a restoring Undo", async () => {
    reply = { "/candidates?": list, "bulk/dismiss": { success: true, results: [{ candidate_id: 1, ok: true }, { candidate_id: 2, ok: true }], succeeded: 2, failed: 0, dismissed: [1, 2] },
      "bulk/restore": { success: true, results: [], succeeded: 2, failed: 0 } };
    await m.loadSalesBulk();
    m.sbToggleAll(true);
    await m.sbDismiss("not_a_sale");
    assert.deepEqual(calls.find((c) => c[0].endsWith("bulk/dismiss"))[2], { candidate_ids: [1, 2], reason: "not_a_sale" });
    await m.sbUndoBatch();
    assert.deepEqual(calls.find((c) => c[0].endsWith("bulk/restore"))[2], { candidate_ids: [1, 2] });
  });
  test("Check all posts to validate and shows per-item results without saving", async () => {
    reply = { "bulk/review": { success: true, items: [item(1, 12, { 0: 10, 1: 2 })] }, "bulk/validate": { success: true, results: [{ candidate_id: 1, ok: false, error: "over" }], succeeded: 0, failed: 1 } };
    m.sbToggleAll(true);
    await m.sbReview();
    await m.sbValidate();
    assert.ok(calls.some((c) => c[0].endsWith("bulk/validate")));
    assert.ok(!calls.some((c) => c[0].endsWith("bulk/confirm")));
    assert.match(els.sbRoot.innerHTML, /Nothing was saved/);
    assert.match(els.sbRoot.innerHTML, /field-error">over/);
  });
});
