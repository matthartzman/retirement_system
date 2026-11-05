// Holdings editor: rows of an account the transaction log manages are read-only and link to Transactions.
import { test, before } from "node:test";
import assert from "node:assert/strict";

let m;
before(async () => {
  globalThis.window = globalThis;
  globalThis.esc = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
  globalThis.rows = [];
  globalThis.parseCsvLine = (l) => l.split(",");
  globalThis.isEditable = () => false;
  globalThis.humanLabel = (c) => c;
  globalThis.currencyDisplay = (v) => v;
  globalThis.accountDisplayLabel = (a) => a;
  globalThis.deleteIconBtn = () => "<x>";
  globalThis.setTimeout = () => 0;
  globalThis.norm = (s) => String(s).toLowerCase();
  globalThis.api = async () => ({ managed: ["Member_1_IRA"] });
  m = await import("../../frontend/js/dashboard_decomp_holdings.js");
});

test("holdings_editor_marks_managed_rows_read_only", async () => {
  window.managedHoldingAccounts = ["Member_1_IRA"];
  assert.equal(m.isManagedHoldingAccount("member_1_ira"), true);
  assert.equal(m.isManagedHoldingAccount("Member_1_HSA"), false);
  await m.loadManagedHoldingAccounts();
  assert.deepEqual(window.managedHoldingAccounts, ["Member_1_IRA"]);
});

const CSV = "account,symbol,purchase_date,shares,purchase_price,lot_type,note\n";
const render = (body, managed = ["Member_1_IRA"]) => {
  window.managedHoldingAccounts = managed;
  window.currentHoldingAccount = "ALL";
  window.holdingsText = CSV + body;
  window.holdingRowsCache = null;
  return m.renderHoldings();
};

test("the editor is for cash only: securities lots are never listed or editable", () => {
  const html = render("Member_1_IRA,VTI,2023-01-10,10,100,buy,\nMember_1_IRA,CASH,2026-10-30,2200.56,1,buy,\nMember_1_HSA,BND,2024-01-02,7,50,buy,");
  assert.match(html, /Edit cash in investment accounts/);
  assert.doesNotMatch(html, /Edit lots|pricing tester|Add Lot|Add Account|Delete Account|replace CSV/);
  const parts = html.split("<tr data-hidx").slice(1);
  assert.equal(parts.length, 1);
  assert.match(parts[0], /Member_1_IRA/);
  assert.match(parts[0], /data-hcol="shares"/);
  assert.match(parts[0], /data-hcol="purchase_date"/);
  assert.doesNotMatch(html, /data-hcol="symbol"/);
});

test("an investment account with no cash balance offers to add one; a cash-only account is not listed", () => {
  const html = render("Family_Checking,CASH,2026-06-01,25000,1,buy,\nMember_1_HSA,BND,2024-01-02,7,50,buy,\nMember_1_HSA,CASH,2024-01-02,3,1,buy,\nMember_1_IRA,VTI,2023-01-10,10,100,buy,");
  assert.deepEqual([...m.cashOnlyAccounts([{ account: "A", symbol: "cash" }, { account: "B", symbol: "VTI" }, { account: "B", symbol: "CASH" }])], ["a"]);
  assert.doesNotMatch(html, /Family.Checking/);
  assert.match(html, /addHoldingCash\('Member_1_IRA'\)/);
  assert.doesNotMatch(html, /addHoldingCash\('Member_1_HSA'\)/);
});

test("adding a cash balance creates one CASH lot at $1 for that account", () => {
  render("Member_1_IRA,VTI,2023-01-10,10,100,buy,");
  globalThis.csvEscape = (v) => String(v);
  globalThis.lastBuildOk = true;
  globalThis.appReady = true;
  globalThis.updateUnsaved = () => {};
  globalThis.setAppControls = () => {};
  globalThis.scheduleStatusUpdate = () => {};
  globalThis.renderMain = () => {};
  m.addHoldingCash("Member_1_IRA");
  const added = m.ensureHoldingRows().data.at(-1);
  assert.deepEqual([added.account, added.symbol, added.purchase_price], ["Member_1_IRA", "CASH", "1"]);
});
