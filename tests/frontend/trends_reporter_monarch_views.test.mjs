// Phase 6 of the Monarch balances feed: Monarch-driven Net worth / Holdings rows, zero-hiding
// rollover, account toggles, and the monthly investment flows line + YTD summary.
import { test, describe } from "node:test";
import assert from "node:assert/strict";
import {
  buildMonarchRows, monarchRolloverModel, rolloverHtml, rolloverModel, balancesFreshnessNote,
  accountToggleHtml, flowIncludedAccounts, flowMonthlySeries, flowYtdSummary,
  flowSummaryHtml, flowLineChartSvg, fmtMoneySigned, hasMonarchBalances,
} from "../../financial_trends_reporter/frontend/charts.js";

const acct = (key, name, type, enabled, active = true) => ({ account_key: key, display_name: name, type, active, last_seen: "2026-01-10", enabled });
const ON = { networth: true, holdings: true, flows: false };

const BAL = {
  dates: ["2026-01-08", "2026-01-09", "2026-01-10"],
  series: { ira: [100, 110, 120], cash: [10, 10, 0], loan: [-50, -50, -50], annuity: [500, 500, 500], closed: [5, 0, 0] },
  accounts: [
    acct("ira", "IRA - A", "Retirement", ON),
    acct("cash", "Checking", "Cash", ON),
    acct("loan", "Mortgage", "Loan", { networth: true, holdings: false, flows: false }),
    acct("annuity", "Annuity - A", "Annuity/Pension", { networth: true, holdings: false, flows: false }),
    acct("closed", "Old Brokerage", "Investment", ON, false),
  ],
};

describe("buildMonarchRows", () => {
  test("sums enabled accounts per date: net worth takes debts, holdings excludes annuity and loans", () => {
    const rows = buildMonarchRows(BAL, []);
    assert.deepEqual(rows.map(r => r.net_worth.total), [100 + 10 - 50 + 500 + 5, 110 + 10 - 50 + 500, 120 + 0 - 50 + 500]);
    assert.deepEqual(rows.map(r => r.holdings.current_value), [115, 120, 120]);
    assert.ok(rows.every(r => r.source === "monarch"));
  });

  test("turning an account off removes it from the sums", () => {
    const b = structuredClone(BAL);
    b.accounts.find(a => a.account_key === "annuity").enabled.networth = false;
    assert.equal(buildMonarchRows(b, [])[2].net_worth.total, 120 - 50);
  });

  test("dates Monarch doesn't cover keep the plan-derived log value, tagged plan", () => {
    const history = [
      { as_of_date: "2025-12-31", net_worth: { total: 900 }, holdings: { current_value: 400 } },
      { as_of_date: "2026-01-09", net_worth: { total: 1 }, holdings: { current_value: 1 } },   // covered by Monarch
      { as_of_date: "2026-01-12", net_worth: { total: 950 }, holdings: { current_value: 420 } },
    ];
    const rows = buildMonarchRows(BAL, history);
    assert.deepEqual(rows.map(r => [r.as_of_date, r.source]), [
      ["2025-12-31", "plan"], ["2026-01-08", "monarch"], ["2026-01-09", "monarch"], ["2026-01-10", "monarch"], ["2026-01-12", "plan"],
    ]);
    assert.equal(rows[0].net_worth.total, 900);
    assert.equal(rows[2].net_worth.total, 110 + 10 - 50 + 500);
  });

  test("returns null without usable balances", () => {
    assert.equal(buildMonarchRows(null, []), null);
    assert.equal(buildMonarchRows({ dates: [], series: {}, accounts: [] }, []), null);
    assert.equal(hasMonarchBalances([]), false);
  });
});

describe("monarchRolloverModel", () => {
  const rows = buildMonarchRows(BAL, []);

  test("omits accounts whose value is zero on that date", () => {
    const m = monarchRolloverModel(rows[2], BAL, "networth");
    const names = m.groups.flatMap(g => g.items.map(i => i.name));
    assert.ok(!names.includes("Checking"), "zero-balance Checking must not be listed");
    assert.ok(!names.includes("Old Brokerage"), "closed account must not be listed");
    assert.ok(names.includes("IRA - A") && names.includes("Mortgage"));
    assert.equal(m.total, 570);
    assert.ok(!rolloverHtml(m).includes("Checking"));
  });

  test("an account is listed on dates where it has a value", () => {
    const names = monarchRolloverModel(rows[0], BAL, "networth").groups.flatMap(g => g.items.map(i => i.name));
    assert.ok(names.includes("Checking") && names.includes("Old Brokerage"));
  });

  test("groups by type with subtotals; holdings uses only holdings accounts", () => {
    const m = monarchRolloverModel(rows[1], BAL, "investments");
    assert.equal(m.title, "Liquid Investments and Cash");
    assert.deepEqual(m.groups.map(g => [g.role, g.subtotal]).sort(), [["Cash", 10], ["Retirement", 110]]);
    assert.equal(m.total, 120);
  });

  test("debts show negative and get a subtotal", () => {
    const loan = monarchRolloverModel(rows[2], BAL, "networth").groups.find(g => g.role === "Loan");
    assert.equal(loan.subtotal, -50);
  });

  test("plan-sourced rows fall back to the legacy model", () => {
    const planRow = { as_of_date: "2025-12-31", source: "plan", idx: -1, plan: { as_of_date: "2025-12-31", net_worth: { total: 900 }, holdings: { current_value: 400 } } };
    assert.deepEqual(monarchRolloverModel(planRow, BAL, "networth"), rolloverModel(planRow.plan, "networth"));
  });

  test("account names are escaped", () => {
    const b = structuredClone(BAL);
    b.accounts[0].display_name = '<img src=x onerror=alert(1)>';
    assert.ok(!rolloverHtml(monarchRolloverModel(buildMonarchRows(b, [])[2], b, "networth")).includes("<img"));
  });
});

describe("legacy rollover hides zero-value accounts too", () => {
  test("a zero-balance logged account is not listed", () => {
    const row = {
      as_of_date: "2026-06-12", holdings: { current_value: 100, by_account: [{ account: "Real", role: "Investment", current_value: 100 }, { account: "Empty", role: "Investment", current_value: 0 }] },
      net_worth: { total: 100, other_accounts: [{ account: "Zero Card", role: "Credit card", value: 0, liability: true }] },
    };
    const html = rolloverHtml(rolloverModel(row, "networth"));
    assert.ok(html.includes("Real") && !html.includes("Empty") && !html.includes("Zero Card"));
  });
});

describe("balancesFreshnessNote", () => {
  const ok = { latest_date: "2026-10-14" };
  test("healthy and recent is silent", () => {
    assert.equal(balancesFreshnessNote({ last_run: { status: "ok" }, last_ok: ok }, "2026-10-15"), "");
  });
  test("stale good import is reported with its date", () => {
    assert.match(balancesFreshnessNote({ last_run: { status: "ok" }, last_ok: ok }, "2026-10-20"), /last updated 2026-10-14/);
  });
  test("a rejected import is reported with the reason", () => {
    const n = balancesFreshnessNote({ last_run: { status: "rejected", detail: "stale export" }, last_ok: ok }, "2026-10-15");
    assert.match(n, /rejected \(stale export\)/);
    assert.match(n, /2026-10-14/);
  });
  test("no import history is silent", () => {
    assert.equal(balancesFreshnessNote({ last_run: null, last_ok: null }), "");
  });
});

describe("account toggle popover and accounts table", () => {
  test("groups by type, checks enabled accounts, marks closed, offers bulk actions", () => {
    const html = accountToggleHtml(BAL.accounts, "holdings", "Holdings", true);
    assert.match(html, /<legend>Retirement<\/legend>/);
    assert.match(html, /data-chart="holdings" data-key="ira" checked/);
    assert.ok(!/data-key="annuity" checked/.test(html));
    assert.match(html, /\(closed\)/);
    for (const mode of ["all", "none", "default"]) assert.ok(html.includes(`data-bulk="${mode}"`));
  });

  test("closed accounts are hidden by default and shown by the toggle", () => {
    const hidden = accountToggleHtml(BAL.accounts, "holdings", "Holdings");
    assert.ok(!/\(closed\)/.test(hidden));
    assert.match(hidden, /data-show-closed>/);
    const shown = accountToggleHtml(BAL.accounts, "holdings", "Holdings", true);
    assert.match(shown, /data-show-closed checked>/);
    assert.match(shown, /\(closed\)/);
  });

  test("account names are escaped in the popover", () => {
    const html = accountToggleHtml([acct("x", "<b>&", "Cash", ON)], "networth", "Net worth");
    assert.ok(!html.includes("<b>&<"));
    assert.ok(html.includes("&lt;b&gt;&amp;"));
  });

  test("the popover says type, match and ignore come from the app", () => {
    assert.match(accountToggleHtml([acct("x", "X", "Cash", ON)], "networth", "Net worth"), /Retirement app's Monarch Reconciliation/);
  });
});

describe("monthly investment flows", () => {
  const MONTHLY = {
    "Brokerage A": { "2025-12": { to_checking: 400, from_checking: 0 }, "2026-02": { to_checking: 0, from_checking: 100 } },
    "IRA B": { "2026-02": { to_checking: 50, from_checking: 10 } },
  };

  test("fills gap months and sums credits, debits and net", () => {
    const s = flowMonthlySeries(MONTHLY, ["Brokerage A", "IRA B"]);
    assert.deepEqual(s.map(p => p.month), ["2025-12", "2026-01", "2026-02"]);
    assert.deepEqual(s[1], { month: "2026-01", credits: 0, debits: 0, net: 0 });
    assert.deepEqual(s[2], { month: "2026-02", credits: 110, debits: 50, net: 60 });
    assert.equal(s[0].net, -400);
  });

  test("only included accounts count; none included gives an empty series", () => {
    assert.deepEqual(flowMonthlySeries(MONTHLY, ["IRA B"]).map(p => p.month), ["2026-02"]);
    assert.deepEqual(flowMonthlySeries(MONTHLY, []), []);
    assert.deepEqual(flowMonthlySeries({}, ["x"]), []);
  });

  test("YTD summary totals one calendar year", () => {
    const s = flowMonthlySeries(MONTHLY, ["Brokerage A", "IRA B"]);
    assert.deepEqual(flowYtdSummary(s, 2026), { year: 2026, credits: 110, debits: 50, total: 60 });
    assert.deepEqual(flowYtdSummary(s, 2025), { year: 2025, credits: 0, debits: 400, total: -400 });
  });

  test("account inclusion follows the Flows toggles through the mapping; unmatched stay included", () => {
    const flowAccounts = [
      { flow_account: "Brokerage A", account_keys: ["brk"], enabled: true },
      { flow_account: "IRA B", account_keys: ["ira"], enabled: true },
      { flow_account: "Mystery", account_keys: [], enabled: true },
    ];
    const bal = { accounts: [acct("brk", "Brokerage A", "Investment", { flows: false }), acct("ira", "IRA - A", "Retirement", { flows: true })] };
    assert.deepEqual(flowIncludedAccounts(flowAccounts, bal), ["IRA B", "Mystery"]);
    assert.deepEqual(flowIncludedAccounts(flowAccounts, null), ["Brokerage A", "IRA B", "Mystery"]);
  });

  test("summary shows credits, debits and total with signs", () => {
    const html = flowSummaryHtml({ year: 2026, credits: 20000, debits: 56000, total: -36000 });
    assert.match(html, /2026 YTD/);
    assert.match(html, /\$20,000/);
    assert.match(html, /\$56,000/);
    assert.match(html, /-\$36,000/);
    assert.equal(flowSummaryHtml(null), "");
    assert.equal(fmtMoneySigned(-5), "-$5");
  });

  test("line chart is a labelled line chart with a data-table fallback; empty gives a message", () => {
    const html = flowLineChartSvg(flowMonthlySeries(MONTHLY, ["Brokerage A", "IRA B"]));
    assert.match(html, /role="img"/);
    assert.match(html, /Net investment contributions by month, line chart/);
    assert.match(html, /<table class="visually-hidden">/);
    assert.match(flowLineChartSvg([]), /class="empty"/);
  });
});
