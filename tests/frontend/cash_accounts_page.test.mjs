// Checking & Savings page (dashboard_decomp_cash_accounts.js): name, balance, last updated; add and delete only.
import { test, before } from "node:test";
import assert from "node:assert/strict";
import { installInAppConfirm, resetInAppConfirm, confirmState } from "./inapp_confirm_stub.mjs";
import fs from "node:fs";

let m;
before(async () => {
  globalThis.window = globalThis;
  globalThis.esc = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  globalThis.accountDisplayLabel = (a) => String(a).replace(/_/g, " ");
  globalThis.document = { getElementById: () => null };
  globalThis.setTimeout = () => 0;
  globalThis.api = async () => ({ accounts: [], import_accounts: [] });
  await installInAppConfirm();
  m = await import("../../frontend/js/dashboard_decomp_cash_accounts.js");
});

const DATA = {
  accounts: [{ account: "Family_Checking", name: "Family Checking", balance: "13894.27", as_of: "2026-10-14", import_account: "Family Checking" },
    { account: "Petty_Cash", name: "<b>Petty</b>", balance: "40.00", as_of: "2026-09-01", import_account: null }],
  import_accounts: [{ account_key: "hys", account: "High Yield Savings" }],
};
const EMPTY = { name: "", balance: "", as_of: "", import_account_key: "" };

test("shows name, balance, last updated and the source, with no lot fields", () => {
  const h = m.caHtml(DATA, EMPTY, null);
  assert.match(h, /Family Checking<\/td><td class="rc-num">\$13,894\.27<\/td><td>2026-10-14<\/td><td>Account import: Family Checking/);
  assert.match(h, /Entered by hand/);
  assert.doesNotMatch(h, /Symbol|Shares|Purchase|Lot type/i);
});

test("escapes account names and offers imported accounts to link", () => {
  const h = m.caHtml(DATA, EMPTY, null);
  assert.doesNotMatch(h, /<b>Petty<\/b>/);
  assert.match(h, /<option value="hys">High Yield Savings<\/option>/);
  assert.doesNotMatch(m.caHtml({ accounts: [], import_accounts: [] }, EMPTY, null), /Account import<select/);
});

test("empty and error states", () => {
  assert.match(m.caHtml({ accounts: [], import_accounts: [] }, EMPTY, null), /No checking or savings accounts yet/);
  assert.match(m.caHtml(DATA, EMPTY, { text: "bad", error: true }), /<p class="field-error">bad/);
});

test("wired into the nav first under Accounts & Property, and into index.html", () => {
  const dash = fs.readFileSync("frontend/js/dashboard.js", "utf8");
  assert.match(dash, /id: "cash_accounts",\s+group: "Accounts & Property",\s+title: "Checking & Savings",\s+\},\s+\{\s+id: "holdings"/);
  assert.match(dash, /activeStep === "cash_accounts"\) content \+= renderCashAccounts\(\)/);
  assert.match(fs.readFileSync("frontend/index.html", "utf8"), /js\/dashboard_decomp_cash_accounts\.js\?v=1/);
});
