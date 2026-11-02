// Cash in investment accounts panel: rows, unanchored label, sortable headings, income by tax class, ledger.
import { test, before } from "node:test";
import assert from "node:assert/strict";

let m;
before(async () => {
  globalThis.window = globalThis;
  globalThis.esc = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
  globalThis.accountDisplayLabel = (a) => a.replace(/_/g, " ");
  globalThis.setTimeout = () => 0;
  globalThis.api = async () => ({});
  m = await import("../../frontend/js/dashboard_decomp_cash_investment.js");
});

const VIEW = { year: 2026, income_by_tax_class: { hsa: 12.5 }, accounts: [
  { account: "Member_1_HSA", balance: 50, as_of: "2026-09-30", anchor: "broker balance", cash_lot: 10, difference: 40, last_flow: "2026-09-18", unmatched: 0 },
  { account: "Member_1_IRA", balance: null, as_of: null, anchor: "unanchored", cash_lot: null, difference: null, last_flow: null, unmatched: 2 }] };

test("panel_lists_accounts_unanchored_and_income", () => {
  const h = m.ciHtml(VIEW, null);
  assert.match(h, /Member 1 HSA/);
  assert.match(h, /unanchored/);
  assert.match(h, /HSA 12.5/);
});

test("panel_sorts_by_heading_and_shows_ledger", () => {
  const h = m.ciHtml(VIEW, { account: "Member_1_HSA", rows: [{ date: "2026-09-18", class: "income", amount: 5, cash_balance: 50, pair_status: "unpaired", source: "broker" }] }, { key: "balance", dir: -1 });
  assert.ok(h.indexOf("Member 1 HSA") < h.indexOf("Member 1 IRA"));
  assert.match(h, /ledger/);
  assert.match(h, /unpaired/);
});

test("panel_reports_withdrawals_by_pair_status_and_flags_excess_return", () => {
  const v = { ...VIEW, accounts: [{ ...VIEW.accounts[0], tax_class: "hsa", withdrawals: { external_withdrawal: 300, internal: 200, unmatched: 50 }, excess_return: { count: 1, amount: 100 } }] };
  const h = m.ciHtml(v, null);
  assert.match(h, /Withdrawals 2026 by pairing/);
  assert.match(h, /report only/i);
  assert.match(h, /enter the earnings/);
});
