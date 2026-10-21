// WI-031 / QA-008: behavioural tests for the withdrawal account-order editor
// handlers (drag/drop reorder, reset, save) in dashboard_decomp_misc.js.
// Module state is private, so everything is driven through the handlers and
// observed through window.api calls and the rendered HTML.

import { test, describe, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();
const w = sandbox.window;

const ACCOUNTS = [
  { account_id: "A", priority: "1" },
  { account_id: "B", priority: "2" },
  { account_id: "C", priority: "3" },
];

let calls, messages, renders;
const ev = () => ({ preventDefault() {}, dataTransfer: { setData() {} } });

async function load(accounts = ACCOUNTS) {
  w.api = async (url, opts) => {
    calls.push({ url, opts });
    return opts && opts.method === "POST" ? { success: true } : { accounts: accounts.map((a) => ({ ...a })) };
  };
  await sandbox.loadWithdrawalAccountOrder(true);
}
const order = () => [...sandbox.withdrawalAccountOrderEditorHtml().matchAll(/<td>([^<]*)<\/td>/g)].map((m) => m[1]);

describe("withdrawal account order handlers", () => {
  beforeEach(() => {
    calls = [];
    messages = [];
    renders = 0;
    w.renderMain = () => renders++;
    w.showMessage = (m, k) => messages.push([m, k]);
    w.esc = (s) => String(s);
  });

  test("load sorts by priority and starts clean", async () => {
    await load([{ account_id: "B", priority: "2" }, { account_id: "A", priority: "1" }]);
    assert.deepEqual(order(), ["A", "B"]);
    assert.equal(sandbox.withdrawalAccountOrderIsDirty(), false);
  });

  test("drop moves the dragged row, renumbers, marks dirty and re-renders", async () => {
    await load();
    sandbox.withdrawalOrderDragStart(ev(), 0);
    sandbox.withdrawalOrderDrop(ev(), 2);
    assert.deepEqual(order(), ["B", "C", "A"]);
    assert.equal(sandbox.withdrawalAccountOrderIsDirty(), true);
    assert.ok(renders > 0);
  });

  test("drop without a drag, or onto the same row, changes nothing", async () => {
    await load();
    sandbox.withdrawalOrderDrop(ev(), 1);
    sandbox.withdrawalOrderDragStart(ev(), 1);
    sandbox.withdrawalOrderDrop(ev(), 1);
    assert.deepEqual(order(), ["A", "B", "C"]);
    assert.equal(sandbox.withdrawalAccountOrderIsDirty(), false);
  });

  test("dragend cancels a pending drag", async () => {
    await load();
    sandbox.withdrawalOrderDragStart(ev(), 0);
    sandbox.withdrawalOrderDragEnd();
    sandbox.withdrawalOrderDrop(ev(), 2);
    assert.deepEqual(order(), ["A", "B", "C"]);
  });

  test("save posts the reordered priorities and clears dirty", async () => {
    await load();
    sandbox.withdrawalOrderDragStart(ev(), 2);
    sandbox.withdrawalOrderDrop(ev(), 0);
    await sandbox.saveWithdrawalAccountOrder();
    const post = calls.find((c) => c.opts && c.opts.method === "POST");
    assert.equal(post.url, "/api/withdrawal-account-order");
    const sent = JSON.parse(post.opts.body).accounts;
    assert.deepEqual(sent.map((a) => [a.account_id, a.priority]), [["C", "1"], ["A", "2"], ["B", "3"]]);
    assert.equal(sandbox.withdrawalAccountOrderIsDirty(), false);
    assert.equal(messages.at(-1)[1], "good");
  });

  test("save failure keeps dirty and reports the error", async () => {
    await load();
    sandbox.withdrawalOrderDragStart(ev(), 0);
    sandbox.withdrawalOrderDrop(ev(), 1);
    w.api = async () => ({ success: false, error: "nope" });
    await sandbox.saveWithdrawalAccountOrder();
    assert.equal(sandbox.withdrawalAccountOrderIsDirty(), true);
    assert.deepEqual(messages.at(-1), ["nope", "error"]);
  });

  test("reset restores registry order and marks dirty", async () => {
    await load();
    sandbox.withdrawalOrderDragStart(ev(), 0);
    sandbox.withdrawalOrderDrop(ev(), 2);
    sandbox.resetWithdrawalAccountOrderToDefault();
    assert.deepEqual(order(), ["A", "B", "C"]);
    assert.equal(sandbox.withdrawalAccountOrderIsDirty(), true);
  });
});
