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

test("rendered rows of a managed account are readonly with a link; others stay editable", () => {
  window.managedHoldingAccounts = ["Member_1_IRA"];
  window.currentHoldingAccount = "ALL";
  window.holdingsText = "account,symbol,purchase_date,shares,purchase_price,lot_type,note\nMember_1_IRA,VTI,2023-01-10,10,100,buy,\nMember_1_HSA,BND,2024-01-02,7,50,buy,";
  window.holdingRowsCache = null;
  const html = m.renderHoldings();
  const parts = html.split("<tr data-hidx").slice(1);
  const ira = parts.find((x) => x.includes("Member_1_IRA"));
  const hsa = parts.find((x) => x.includes("Member_1_HSA"));
  assert.match(ira, /data-managed="1"/);
  assert.match(ira, /readonly/);
  assert.doesNotMatch(ira, /oninput/);
  assert.match(ira, /Managed in Transactions/);
  assert.doesNotMatch(hsa, /readonly/);
  assert.match(hsa, /oninput/);
});

test("a cash-only account (one CASH lot) is read-only and points to Checking & Savings", () => {
  window.managedHoldingAccounts = [];
  window.currentHoldingAccount = "ALL";
  window.holdingsText = "account,symbol,purchase_date,shares,purchase_price,lot_type,note\nFamily_Checking,CASH,2026-06-01,25000,1,buy,\nMember_1_HSA,BND,2024-01-02,7,50,buy,\nMember_1_HSA,CASH,2024-01-02,3,1,buy,";
  window.holdingRowsCache = null;
  assert.deepEqual([...m.cashOnlyAccounts([{ account: "A", symbol: "cash" }, { account: "B", symbol: "VTI" }, { account: "B", symbol: "CASH" }])], ["a"]);
  const parts = m.renderHoldings().split("<tr data-hidx").slice(1);
  const chk = parts.find((x) => x.includes("Family_Checking"));
  assert.match(chk, /readonly/);
  assert.match(chk, /Managed in Checking &amp; Savings/);
  assert.doesNotMatch(parts.find((x) => x.includes("BND")), /readonly/);
  assert.doesNotMatch(parts.find((x) => x.includes(",CASH") || x.includes('value="CASH"') && x.includes("Member_1_HSA")), /readonly/);
});
