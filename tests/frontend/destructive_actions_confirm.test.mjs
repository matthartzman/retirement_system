// W2-04 / UX-002: every destructive record action asks in the in-app dialog with an action-named primary
// button and a consequence line, does nothing when the dialog is dismissed, and does nothing when no dialog
// exists (fail closed). Native confirm() is never consulted.
import { test, before, beforeEach } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { installInAppConfirm, resetInAppConfirm, confirmState } from "./inapp_confirm_stub.mjs";

const calls = [];
const mods = {};
before(async () => {
  globalThis.window = globalThis;
  globalThis.esc = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  globalThis.accountDisplayLabel = (a) => String(a).replace(/_/g, " ");
  globalThis.document = { getElementById: () => null };
  globalThis.setTimeout = () => 0;
  globalThis.confirm = () => { throw new Error("native confirm() must not be used"); };
  globalThis.api = async (url, opts) => { calls.push([url, opts && opts.method]); return { accounts: [], import_accounts: [], success: true }; };
  await installInAppConfirm();
  await import("../../frontend/js/dashboard_decomp_sales_ledger_ui.js");
  mods.ca = await import("../../frontend/js/dashboard_decomp_cash_accounts.js");
  mods.ci = await import("../../frontend/js/dashboard_decomp_cash_investment.js");
  mods.tl = await import("../../frontend/js/dashboard_decomp_transactions_log.js");
  mods.sl = await import("../../frontend/js/dashboard_decomp_sales_ledger.js");
});
beforeEach(() => { calls.length = 0; resetInAppConfirm(); });

const posts = () => calls.filter((c) => c[1] === "POST");
// [label, handler, expected button label]
const HANDLERS = [
  ["caDelete", () => mods.ca.caDelete("Family_Checking"), "Delete account"],
  ["ciCloseYear", () => mods.ci.ciCloseYear(2026, 0), "Close year"],
  ["ciCloseYear (straddles)", () => mods.ci.ciCloseYear(2026, 2), "Close year"],
  ["ciReopenYear", () => mods.ci.ciReopenYear(2026), "Reopen year"],
  ["ciMarkRollover", () => mods.ci.ciMarkRollover("Member_1_IRA", "2026-03-01", -500, true), "Mark as rollover"],
  ["tlStart", () => mods.tl.tlStart(), "Start the log"],
  ["tlVoid", () => mods.tl.tlVoid(7), "Void transaction"],
  ["slVoid", () => mods.sl.slVoid(7), "Void sale"],
];

for (const [label, run, button] of HANDLERS) {
  test(`${label}: asks with an action-named button and a consequence line`, async () => {
    await run();
    const ask = confirmState.asked[0];
    assert.ok(ask, "no in-app dialog was shown");
    assert.equal(ask.opts.confirmLabel, button);
    assert.ok(ask.opts.title && ask.message.length > 10, "title and consequence line are required");
    assert.equal(ask.opts.variant, "warn");
  });
  test(`${label}: dismissed does nothing`, async () => {
    confirmState.answer = false;
    await run();
    assert.equal(posts().length, 0);
  });
  test(`${label}: no dialog available fails closed`, async () => {
    const saved = globalThis.showInAppConfirm;
    delete globalThis.showInAppConfirm;
    try { await run(); } finally { globalThis.showInAppConfirm = saved; }
    assert.equal(posts().length, 0);
  });
}

test("tlCleanBank asks and fails closed", async () => {
  globalThis.api = async (url, opts) => { calls.push([url, opts && opts.method]); return url.includes("bank-cleanup") && !opts ? { success: true, accounts: [{ account: "Biz", managed: false, opening_rows: [1] }] } : { success: true }; };
  await mods.tl.tlLoad();
  calls.length = 0;
  confirmState.answer = false;
  await mods.tl.tlCleanBank();
  assert.equal(confirmState.asked[0].opts.confirmLabel, "Void bank rows");
  assert.equal(posts().length, 0);
});

test("no record-action source calls native confirm()", () => {
  for (const f of ["cash_accounts", "cash_investment", "sales_1099b", "sales_ledger", "transactions_log"]) {
    const src = fs.readFileSync(new URL(`../../frontend/js/dashboard_decomp_${f}.js`, import.meta.url), "utf8");
    assert.ok(!/(^|[^.\w])(window\.)?confirm\(/m.test(src), `${f} still calls confirm()`);
  }
});
