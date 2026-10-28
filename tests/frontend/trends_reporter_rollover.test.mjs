// Item 347c: account-subtotal rollover on the Net worth and Investments line charts.
import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { rolloverModel, rolloverHtml, rolloverChange, flowRolloverHtml, flowSeries, lineChartSvg } from "../../financial_trends_reporter/frontend/charts.js";

const ROW = {
  as_of_date: "2026-06-12",
  holdings: {
    current_value: 156000,
    by_account: [
      { account: "Brokerage A", role: "Investment", current_value: 110000 },
      { account: "IRA B", role: "Investment", current_value: 46000 },
    ],
  },
  net_worth: {
    total: 900000, home: 800000, other_assets: 50000, mortgage: 100000, liabilities: 102000, assets: 1002000,
    other_accounts: [
      { account: "Checking", role: "Cash / spending", value: 900, liability: false },
      { account: "Visa", role: "Credit card", value: 2000, liability: true },
    ],
  },
};

describe("rolloverModel", () => {
  test("investments: groups by role with a subtotal", () => {
    const m = rolloverModel(ROW, "investments");
    assert.equal(m.total, 156000);
    assert.equal(m.groups.length, 1);
    assert.equal(m.groups[0].role, "Investment");
    assert.equal(m.groups[0].subtotal, 156000);
    assert.deepEqual(m.groups[0].items.map(i => i.name), ["Brokerage A", "IRA B"]);
  });

  test("net worth: adds non-investment accounts (liabilities negative) and the plan-level lines", () => {
    const m = rolloverModel(ROW, "networth");
    const roles = Object.fromEntries(m.groups.map(g => [g.role, g.subtotal]));
    assert.equal(roles["Credit card"], -2000);
    assert.equal(roles["Cash / spending"], 900);
    assert.deepEqual(m.lines.map(l => l[0]).slice(0, 3), ["Home", "Other assets (plan)", "Mortgage"]);
    assert.equal(m.lines.find(l => l[0] === "Mortgage")[1], -100000);
    // liabilities 102,000 = mortgage 100,000 + Visa 2,000: nothing left over, so no second liabilities line.
    assert.ok(!m.lines.some(l => /liabilities/i.test(l[0])));
  });

  test("liabilities not itemized elsewhere show as one 'Other liabilities' remainder", () => {
    const row = { as_of_date: "d", net_worth: { total: 1, mortgage: 100, liabilities: 350, other_accounts: [] } };
    const m = rolloverModel(row, "networth");
    assert.deepEqual(m.lines.filter(l => l[0] === "Other liabilities"), [["Other liabilities", -250]]);
  });

  test("entries lacking detail show the aggregate only", () => {
    const old = { as_of_date: "2026-01-02", holdings: { current_value: 5 }, net_worth: { total: 9 } };
    assert.match(rolloverHtml(rolloverModel(old, "investments")), /No per-account detail/);
    const nw = rolloverModel(old, "networth");
    assert.equal(nw.groups.length, 0);
    assert.match(rolloverHtml(nw), /\$9/);
  });

  test("null row yields no popup", () => {
    assert.equal(rolloverModel(undefined, "networth"), null);
    assert.equal(rolloverHtml(null), "");
  });
});

describe("rolloverHtml", () => {
  test("escapes account names", () => {
    const row = { as_of_date: "d", holdings: { current_value: 1, by_account: [{ account: "<img onerror=x>", role: "Investment", current_value: 1 }] } };
    assert.ok(!rolloverHtml(rolloverModel(row, "investments")).includes("<img"));
  });
});

describe("lineChartSvg interactive points", () => {
  const pts = [{ label: "a", value: 1 }, { label: "b", value: 2 }];
  test("interactive dots are keyboard-focusable and carry their index", () => {
    const svg = lineChartSvg(pts, { interactive: true });
    // Roving tabindex: only the newest point is a tab stop; the rest are reached with arrow keys.
    assert.equal((svg.match(/class="chart-dot" tabindex="0" data-i="/g) || []).length, 1);
    assert.equal((svg.match(/class="chart-dot" tabindex="-1" data-i="/g) || []).length, 1);
    assert.match(svg, /tabindex="0" data-i="1"/);
    assert.match(svg, /aria-label="b: \$2"/);
  });
  test("non-interactive charts are unchanged", () => {
    assert.ok(!lineChartSvg(pts, {}).includes("tabindex"));
  });
});

describe("rollover total and change (items 367, 368)", () => {
  const rows = [
    { as_of_date: "2026-10-01", net_worth: { total: 1000 }, holdings: { current_value: 400 } },
    { as_of_date: "2026-10-02", net_worth: { total: null }, holdings: { current_value: null } },
    { as_of_date: "2026-10-03", net_worth: { total: 900 }, holdings: { current_value: 500 } },
  ];
  test("change compares with the nearest prior data point that has a value", () => {
    assert.deepEqual(rolloverChange(rows, 2, "networth"), { date: "2026-10-01", total: 1000 });
    assert.equal(rolloverChange(rows, 0, "networth"), null);
  });
  test("total (and change) come before the account groups", () => {
    const model = { title: "Net Worth", date: "2026-10-03", total: 900, prior: { date: "2026-10-01", total: 1000 },
      groups: [{ role: "Cash", items: [{ name: "Chk", value: 900 }], subtotal: 900 }], lines: [] };
    const html = rolloverHtml(model);
    assert.ok(html.indexOf("pop-total") < html.indexOf("pop-group"));
    assert.match(html, /Change since 2026-10-01[\s\S]*-\$100 \(-10\.0%\)/);
  });
  test("flow rollover lists only accounts that moved money, net total on top", () => {
    const daily = { A: { "2026-10-01": { from_checking: 100, to_checking: 30 } }, B: { "2026-10-02": { from_checking: 5, to_checking: 0 } }, C: {} };
    const s = flowSeries(daily, ["A", "B", "C"], { from: "2026-10-01", to: "2026-10-02" }, "day");
    const html = flowRolloverHtml(s[0]);
    assert.match(html, /Net<\/span><span>\$70/);
    assert.match(html, />A \(in \$100, out \$30\)</);
    assert.ok(!html.includes(">B") && !html.includes(">C"));
    assert.ok(html.indexOf("pop-total") < html.indexOf("pop-row"));
  });
});
