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

test("panel_shows_pace_without_difference_while_open_and_past_years_and_straddles", () => {
  const v = { ...VIEW,
    comparison: { year: 2026, closed: false, snapshot: { built_at: "2026-11-01T10:00:00Z" }, note: "may be stale",
      accounts: [{ account: "Member_1_HSA", reported_ytd: 300, plan: 1000, difference: null }], plan_unmapped: { Zed_IRA: 5 } },
    past_years: [{ account: "Member_1_HSA", year: 2025, external_withdrawal: 40, internal: 0, unmatched: 0 }],
    straddles: [{ out_account: "Member_1_HSA", out_date: "2026-12-30", in_account: "Member_1_IRA", in_date: "2027-01-02", amount: 100 }] };
  const h = m.ciHtml(v, null);
  assert.match(h, /Plan vs reported 2026/);
  assert.match(h, /year to date/i);
  assert.match(h, /2026-11-01T10:00:00Z/);
  assert.match(h, /may be stale/);
  assert.doesNotMatch(h, /Difference<\/th><th[^>]*>Plan/);       // no difference column while the year is open
  assert.match(h, /straddle year-end/i);
  assert.match(h, /2025/);
});

test("panel_shows_difference_only_for_a_closed_year", () => {
  const v = { ...VIEW, comparison: { year: 2026, closed: true, snapshot: null, note: "No saved plan run yet",
    accounts: [{ account: "Member_1_HSA", reported_ytd: 300, plan: 1000, difference: 700 }], plan_unmapped: {} } };
  assert.match(m.ciHtml(v, null), /Plan − reported/);
});

// ---- cash-year close (year-end transition Phase 1) ----
test("panel_offers_close_for_an_ended_year_with_blockers_listed", () => {
  const v = { ...VIEW, closes: [
    { year: 2025, closed: false, allowed: false, blockers: ["2 unmatched cash row(s) dated 2025 must be resolved first."], straddles: [], snapshot: null },
    { year: 2026, closed: false, allowed: true, blockers: [], straddles: [{ amount: 100 }], snapshot: { built_at: "2026-12-20T09:00:00Z" } }] };
  const h = m.ciHtml(v, null);
  assert.match(h, /unmatched cash row/);
  assert.doesNotMatch(h, /ciCloseYear\(2025/);                       // blocked: no button
  assert.match(h, /ciCloseYear\(2026, 1\)/);                         // allowed: button carries the straddle count
  assert.match(h, /2026-12-20T09:00:00Z/);                           // which plan run would be used
  assert.match(h, /feeds no tax number/i);
});

test("panel_shows_closed_year_difference_reopen_and_change_since_close", () => {
  const v = { ...VIEW, closes: [{ year: 2026, closed: true, closed_at: "2027-01-08T10:00:00Z", note: "final", plan_source: "snapshot", built_at: "2026-12-20T09:00:00Z",
    changed: true, closed_total: 300, current_total: 340,
    difference: [{ account: "Member_1_HSA", reported: 300, plan: 1000, difference: 700 }] }] };
  const h = m.ciHtml(v, null);
  assert.match(h, /2026 closed 2027-01-08/);
  assert.match(h, /Changed since close/);
  assert.match(h, /ciReopenYear\(2026\)/);
  assert.match(h, /700/);
  const none = m.ciHtml({ ...VIEW, closes: [{ ...v.closes[0], changed: false, plan_source: "none", difference: [{ account: "Member_1_HSA", reported: 300, plan: null, difference: null }] }] }, null);
  assert.match(none, /no plan figure/i);
  assert.doesNotMatch(none, /Changed since close/);
});

// ---- floor gate (year-end Phase 4) ----
test("panel_shows_floor_gate_state_with_verify_and_unverify_controls", () => {
  const gate = (g) => ({ ...VIEW, accounts: [{ ...VIEW.accounts[0], floor_gate: g }] });
  const no = m.ciHtml(gate({ verified: false, eligible: false, reason: "not verified against a closed year" }), null);
  assert.match(no, /Floor feed/);
  assert.match(no, /not verified against a closed year/);
  assert.match(no, /ciVerify\(&quot;Member_1_HSA&quot;, true\)/);
  const ok = m.ciHtml(gate({ verified: true, eligible: true, reason: "" }), null);
  assert.match(ok, /eligible/);
  assert.match(ok, /ciVerify\(&quot;Member_1_HSA&quot;, false\)/);
  const blocked = m.ciHtml(gate({ verified: true, eligible: false, reason: "2 unmatched row(s) dated 2026" }), null);
  assert.match(blocked, /2 unmatched row/);
  assert.match(blocked, /ciVerify\(&quot;Member_1_HSA&quot;, false\)/);
});

test("summary: unmatched cash rows across accounts are a warn, worded like the column; paint without slPublish is safe", async () => {
  const pub = [];
  globalThis.slPublish = (k, s) => pub.push([k, s]);
  globalThis.document = { getElementById: () => null };
  const orig = globalThis.api;
  globalThis.api = async () => VIEW;
  await m.ciLoad();
  assert.deepEqual(pub.at(-1), ["cash", { count: 2, tone: "warn", text: "2 unmatched cash rows" }]);
  globalThis.api = async () => ({ ...VIEW, accounts: [{ ...VIEW.accounts[1], unmatched: 1 }] });
  await m.ciLoad();
  assert.deepEqual(pub.at(-1), ["cash", { count: 1, tone: "warn", text: "1 unmatched cash row" }]);
  delete globalThis.slPublish;
  await assert.doesNotReject(m.ciLoad());
  globalThis.api = orig;
});

test("the panel is a body only: the page's cash section shell supplies the summary, open memory and badge", () => {
  const html = m.ciHtml(VIEW, null);
  assert.doesNotMatch(html, /<details|<summary/); // 2026-11-04: shell moved to slSection("cash")
  assert.match(html, /<table/);
  assert.match(m.ciStateText(), /^(\d+ accounts?)?$/);
  assert.equal(globalThis.ciReveal, undefined);
});

test("ledger_offers_mark_as_rollover_on_a_plain_outflow_and_unmark_on_a_marked_one", () => {
  const rows = [
    { date: "2026-04-07", class: "transfer_out", amount: -355000, cash_balance: 0, pair_status: "external_withdrawal", source: "broker", in_kind: false },
    { date: "2026-04-08", class: "transfer_out", amount: -5, cash_balance: 0, pair_status: "internal", source: "broker", in_kind: false },
    { date: "2026-04-09", class: "transfer_in", amount: 9, cash_balance: 0, pair_status: "external_inflow", source: "broker", in_kind: false },
    { date: "2026-04-10", class: "distribution", amount: -40, cash_balance: 0, pair_status: "external_rollover", source: "broker", in_kind: false }];
  const h = m.ciHtml(VIEW, { account: "Member_1_IRA", rows });
  assert.equal((h.match(/Mark as rollover/g) || []).length, 1);
  assert.equal((h.match(/Unmark rollover/g) || []).length, 1);
  assert.match(h, /ciMarkRollover\(&quot;Member_1_IRA&quot;, &quot;2026-04-07&quot;, -355000, true\)/);
});
