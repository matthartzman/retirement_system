// Item 347b: per-account YTD investment net-flow chart (replaces the cashflow line chart).
import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { investmentFlowRows, flowBarChartSvg, dataTableFallbackHtml } from "../../financial_trends_reporter/frontend/charts.js";

const FLOWS = {
  "Brokerage A": { to_checking: 1000, from_checking: 5000, net: -4000 },
  "IRA B": { to_checking: 7000, from_checking: 2500, net: 4500 },
};

describe("investmentFlowRows", () => {
  test("entries without the field (old log entries, no backfill) yield null", () => {
    assert.equal(investmentFlowRows(undefined), null);
    assert.equal(investmentFlowRows(null), null);
  });

  test("sorts by magnitude and totals the signed nets", () => {
    const m = investmentFlowRows(FLOWS);
    assert.deepEqual(m.rows.map(r => r.name), ["IRA B", "Brokerage A"]);
    assert.equal(m.total, 500);
  });
});

describe("flowBarChartSvg", () => {
  test("empty model shows an empty-state message", () => {
    assert.match(flowBarChartSvg(investmentFlowRows({})), /class="empty"/);
  });

  test("draws a zero line, signed bars, a total row and a keyboard-focusable accessible row each", () => {
    const html = flowBarChartSvg(investmentFlowRows(FLOWS));
    assert.match(html, /\$0/);
    assert.equal((html.match(/tabindex="0"/g) || []).length, 3); // 2 accounts + total
    assert.match(html, /IRA B: net \$4,500 \(withdrawn \$7,000, contributed \$2,500\)/);
    assert.match(html, /Total: \$500/);
    assert.match(html, /<table class="visually-hidden">/);
  });

  test("negative-bar labels sit on the far side of the zero line, not on the account names", () => {
    const html = flowBarChartSvg(investmentFlowRows(FLOWS));
    const zeroX = Number(html.match(/<line x1="([\d.]+)" y1="0"/)[1]);
    const label = html.match(/<text x="([\d.]+)" y="[\d.]+" text-anchor="start">\$-4,000/);
    assert.ok(label && Number(label[1]) > zeroX, "negative label must start right of the zero line");
  });

  test("escapes account names", () => {
    const html = flowBarChartSvg(investmentFlowRows({ "A<b>&": { to_checking: 1, from_checking: 0, net: 1 } }));
    assert.ok(!html.includes("<b>"));
  });
});

test("dataTableFallbackHtml still renders two-column rows", () => {
  const html = dataTableFallbackHtml("c", ["a", "b"], [["x", "y"]]);
  assert.match(html, /<tr><td>x<\/td><td>y<\/td><\/tr>/);
});

import { passthroughReviewHtml } from "../../financial_trends_reporter/frontend/charts.js";

describe("passthroughReviewHtml", () => {
  const item = {
    key: "k<1>", difference: 50,
    withdrawal: { date: "2026-03-10", account: "Brokerage A", amount: 5000 },
    deposit: { date: "2026-03-14", account: "IRA B", amount: 4950 },
  };
  test("renders nothing when there is nothing to review (including old entries)", () => {
    assert.equal(passthroughReviewHtml(undefined), "");
    assert.equal(passthroughReviewHtml([]), "");
  });
  test("renders an alert with approve/deny buttons and an escaped key", () => {
    const html = passthroughReviewHtml([item]);
    assert.match(html, /role="alert"/);
    assert.match(html, /data-decision="approve"/);
    assert.match(html, /data-decision="deny"/);
    assert.match(html, /differ by \$50/);
    assert.ok(!html.includes("k<1>"));
  });
});

// ---- Trends Phase 4: Investment Net Flows on any time scope (daily ledger) ----
import {
  flowSeries, flowMonthlyRangeSeries, flowPeriodSummary, flowSummaryHtml, flowLineChartSvg, scopeRange,
} from "../../financial_trends_reporter/frontend/charts.js";

const DAILY = {
  "Brokerage A": {
    "2026-09-28": { to_checking: 0, from_checking: 100 },   // Mon
    "2026-10-01": { to_checking: 40, from_checking: 0 },    // Thu
    "2026-10-26": { to_checking: 0, from_checking: 5 },     // Mon
  },
  "IRA B": {
    "2026-10-01": { to_checking: 0, from_checking: 10 },
    "2026-08-15": { to_checking: 300, from_checking: 0 },
  },
};
const BOTH = ["Brokerage A", "IRA B"];

describe("flowSeries (daily ledger bucketed by the scope)", () => {
  test("day buckets: one per calendar day in [from, to], empty days are zero", () => {
    const s = flowSeries(DAILY, BOTH, { from: "2026-09-27", to: "2026-10-02" }, "day");
    assert.deepEqual(s.map(p => p.key), ["2026-09-27", "2026-09-28", "2026-09-29", "2026-09-30", "2026-10-01", "2026-10-02"]);
    assert.deepEqual(s[0], { key: "2026-09-27", date: "2026-09-27", label: "Sun, Sep 27, 2026", credits: 0, debits: 0, net: 0 });
    assert.deepEqual(s[4], { key: "2026-10-01", date: "2026-10-01", label: "Thu, Oct 1, 2026", credits: 10, debits: 40, net: -30 });
    assert.equal(s[1].net, 100);
  });

  test("week buckets use ISO weeks and the shared 'Week of' label", () => {
    const s = flowSeries(DAILY, BOTH, { from: "2026-09-26", to: "2026-10-26" }, "week");
    assert.deepEqual(s.map(p => p.key), ["2026-W39", "2026-W40", "2026-W41", "2026-W42", "2026-W43", "2026-W44"]);
    assert.equal(s[0].label, "Week of Sep 21, 2026");
    assert.equal(s[1].label, "Week of Sep 28, 2026");
    assert.deepEqual([s[1].credits, s[1].debits, s[1].net], [110, 40, 70]);
    assert.equal(s[5].net, 5);
    assert.equal(s[2].net, 0);
  });

  test("month buckets are calendar months, zero-filled", () => {
    const s = flowSeries(DAILY, BOTH, { from: "2026-07-26", to: "2026-10-26" }, "month");
    assert.deepEqual(s.map(p => p.key), ["2026-07", "2026-08", "2026-09", "2026-10"]);
    assert.deepEqual(s.map(p => p.net), [0, -300, 100, -25]);
    assert.equal(s[3].label, "Oct 2026");
    assert.equal(s[3].date, "2026-10-01");
  });

  test("only included accounts count; none included gives an empty series", () => {
    const s = flowSeries(DAILY, ["IRA B"], { from: "2026-10-01", to: "2026-10-01" }, "day");
    assert.deepEqual([s[0].credits, s[0].debits], [10, 0]);
    assert.deepEqual(flowSeries(DAILY, [], { from: "2026-10-01", to: "2026-10-26" }, "day"), []);
    assert.deepEqual(flowSeries({}, BOTH, { from: "", to: "" }, "day"), []);
  });

  test("days outside the range are ignored; open bounds fall back to the data's own span", () => {
    const s = flowSeries(DAILY, BOTH, { from: "2026-10-02", to: "2026-10-26" }, "month");
    assert.deepEqual(s.map(p => [p.key, p.net]), [["2026-10", 5]]);
    const open = flowSeries(DAILY, BOTH, { from: "", to: "" }, "month");
    assert.deepEqual(open.map(p => p.key), ["2026-08", "2026-09", "2026-10"]);
  });

  test("works with a scopeRange result directly", () => {
    const r = scopeRange("week", "2026-10-26");
    const s = flowSeries(DAILY, BOTH, r, r.granularity);
    assert.equal(s.length, 8);
    assert.equal(s[s.length - 1].key, "2026-10-26");
  });
});

describe("flowMonthlyRangeSeries (fallback when the log has no daily ledger)", () => {
  const MONTHLY = {
    "Brokerage A": { "2026-08": { to_checking: 0, from_checking: 50 }, "2026-10": { to_checking: 40, from_checking: 105 } },
    "IRA B": { "2026-10": { to_checking: 0, from_checking: 10 } },
  };
  test("keeps whole months that overlap the range, zero-filled, month labels", () => {
    const s = flowMonthlyRangeSeries(MONTHLY, BOTH, { from: "2026-09-26", to: "2026-10-26" });
    assert.deepEqual(s.map(p => [p.key, p.net]), [["2026-09", 0], ["2026-10", 75]]);
    assert.equal(s[1].label, "Oct 2026");
    const wk = flowMonthlyRangeSeries(MONTHLY, BOTH, { from: "2026-10-19", to: "2026-10-26" });
    assert.deepEqual(wk.map(p => p.key), ["2026-10"]);
  });
  test("toggle filter and empty", () => {
    assert.deepEqual(flowMonthlyRangeSeries(MONTHLY, ["IRA B"], { from: "2026-10-01", to: "2026-10-26" }).map(p => p.credits), [10]);
    assert.deepEqual(flowMonthlyRangeSeries(MONTHLY, [], { from: "2026-10-01", to: "2026-10-26" }), []);
  });
});

describe("period summary tiles", () => {
  test("totals the selected period", () => {
    const s = flowSeries(DAILY, BOTH, { from: "2026-09-26", to: "2026-10-26" }, "day");
    assert.deepEqual(flowPeriodSummary(s, "1 Month · Sep 26 – Oct 26, 2026"),
      { label: "1 Month · Sep 26 – Oct 26, 2026", credits: 115, debits: 40, total: 75 });
  });
  test("tiles carry the period label, colour classes and an aria-label (no 'YTD')", () => {
    const html = flowSummaryHtml({ label: "1 Month · Sep 26 – Oct 26, 2026", credits: 115, debits: 40, total: -75 });
    assert.match(html, /1 Month · Sep 26 – Oct 26, 2026/);
    assert.ok(!/YTD/.test(html));
    assert.match(html, /aria-label="Investment flows, 1 Month · Sep 26 – Oct 26, 2026"/);
    assert.match(html, /flow-credit[\s\S]*\$115/);
    assert.match(html, /flow-debit[\s\S]*\$40/);
    assert.match(html, /flow-total[\s\S]*-\$75/);
  });
});

describe("flowLineChartSvg with scope points", () => {
  test("day points get the fitted axis and full dates in the table", () => {
    const s = flowSeries(DAILY, BOTH, { from: "2026-09-26", to: "2026-10-26" }, "day");
    const svg = flowLineChartSvg(s, { width: 560, granularity: "day" });
    assert.match(svg, /<svg viewBox="0 0 560 /);
    assert.ok(!/chart-scroll/.test(svg));
    assert.match(svg, /Net Investment Contributions, line chart/);
    assert.match(svg, /<td>Mon, Oct 26, 2026<\/td>/);
    assert.match(svg, /text-anchor="middle"[^>]*>Oct 26</);
  });
  test("week points use week labels", () => {
    const s = flowSeries(DAILY, BOTH, { from: "2026-07-26", to: "2026-10-26" }, "week");
    assert.match(flowLineChartSvg(s, { width: 560, granularity: "week" }), /<td>Week of Oct 26, 2026<\/td>/);
  });
});
