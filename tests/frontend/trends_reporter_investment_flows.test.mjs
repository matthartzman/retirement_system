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
