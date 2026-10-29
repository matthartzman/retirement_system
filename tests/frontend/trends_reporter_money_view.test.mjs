// Task 5 of the Trends percent-view plan: one money formatter that every card goes through.
import { test, describe, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { setMoneyView, moneyView, fmtAmount, fmtSharePct, onMoneyViewChange, netWorthScale } from "../../financial_trends_reporter/frontend/money_view.js";
import {
  fmtMoney, fmtMoneySigned, toPercentChange, toShareOfTotal, flowsAsShareOfLiquid,
  lineChartSvg, barChartSvg, flowSummaryHtml, flowLineChartSvg, flowRolloverHtml, rolloverHtml, setSpendShareBase,
} from "../../financial_trends_reporter/frontend/charts.js";
import { fmtUsd, fmtUsd2, initLiveView } from "../../financial_trends_reporter/frontend/live_snapshot.js";

beforeEach(() => setMoneyView({ allowed: "both", shown: "dollars", scale: 1 }));

describe("fmtAmount", () => {
  test("percent of today's net worth when shown is percent", () => {
    setMoneyView({ allowed: "both", shown: "percent", scale: 1e6 });
    assert.equal(fmtAmount(250000), "25.0%");
  });
  test("dollars when shown is dollars", () => {
    setMoneyView({ allowed: "both", shown: "dollars", scale: 1e6 });
    assert.equal(fmtAmount(250000), "$250,000");
  });
  test("a percent person is forced to percent even if dollars are asked for", () => {
    setMoneyView({ allowed: "percent", shown: "dollars", scale: 1 });
    assert.equal(moneyView().shown, "percent");
    assert.equal(fmtAmount(0.25), "25.0%");
  });
  test("a dollars person is forced to dollars", () => {
    setMoneyView({ allowed: "dollars", shown: "percent", scale: 1e6 });
    assert.equal(moneyView().shown, "dollars");
  });
  test("null and non-finite show a dash", () => {
    assert.equal(fmtAmount(null), "-");
    assert.equal(fmtAmount(NaN), "-");
    setMoneyView({ allowed: "both", shown: "percent", scale: 1e6 });
    assert.equal(fmtAmount(undefined), "-");
  });
  test("a bad scale in percent mode shows n/a, never Infinity", () => {
    setMoneyView({ allowed: "both", shown: "percent", scale: 0 });
    assert.equal(fmtAmount(5), "n/a");
  });
});

describe("fmtSharePct", () => {
  test("signed one-decimal percent", () => {
    assert.equal(fmtSharePct(0.032), "+3.2%");
    assert.equal(fmtSharePct(-0.01), "-1.0%");
    assert.equal(fmtSharePct(null), "n/a");
  });
});

describe("onMoneyViewChange", () => {
  test("listeners fire when the view is set", () => {
    let n = 0;
    onMoneyViewChange(() => { n += 1; });
    setMoneyView({ allowed: "both", shown: "percent", scale: 10 });
    assert.ok(n >= 1);
  });
});

describe("netWorthScale", () => {
  test("last finite networth point", () => {
    const pt = v => ({ date: "2026-10-28", source: "monarch", value: v });
    assert.equal(netWorthScale({ points: { networth: [pt(1), pt(900), pt(null)] } }), 900);
    assert.equal(netWorthScale(null), 0);
  });
});

describe("existing formatters follow the view", () => {
  test("dollars mode output is unchanged", () => {
    assert.equal(fmtMoney(1234.6), "$1,235");
    assert.equal(fmtMoneySigned(-1234), "-$1,234");
    assert.equal(fmtUsd(-5), "-$5");
    assert.equal(fmtUsd2(5), "$5.00");
  });
  test("percent mode routes them all through fmtAmount", () => {
    setMoneyView({ allowed: "both", shown: "percent", scale: 1000 });
    assert.equal(fmtMoney(250), "25.0%");
    assert.equal(fmtMoneySigned(-250), "-25.0%");
    assert.equal(fmtUsd(250), "25.0%");
    assert.equal(fmtUsd2(250), "25.0%");
  });
});

const near = (a, b) => assert.ok(Math.abs(a - b) < 1e-9, `${a} != ${b}`);

describe("toPercentChange", () => {
  test("values become change since the first point", () => {
    const r = toPercentChange([{ label: "a", value: 200 }, { label: "b", value: 250 }]);
    assert.deepEqual(r.points.map(p => p.value), [0, 0.25]);
    assert.deepEqual(r.base, { label: "a", value: 200 });
  });
  test("a zero or negative base gives null values and no base", () => {
    for (const first of [-10, 0]) {
      const r = toPercentChange([{ label: "a", value: first }, { label: "b", value: 50 }]);
      assert.deepEqual(r.points.map(p => p.value), [null, null]);
      assert.equal(r.base, null);
    }
  });
  test("a missing first value: the first finite point is the base", () => {
    const r = toPercentChange([{ label: "a", value: null }, { label: "b", value: 100 }, { label: "c", value: 110 }]);
    assert.equal(r.base.label, "b");
    assert.equal(r.points[0].value, null);
    near(r.points[2].value, 0.1);
  });
  test("keeps the other fields and handles an empty list", () => {
    assert.equal(toPercentChange([{ label: "a", date: "2026-01-02", value: 5 }]).points[0].date, "2026-01-02");
    assert.deepEqual(toPercentChange([]), { points: [], base: null });
  });
});

describe("toShareOfTotal", () => {
  test("share of the positive total; a refund stays negative", () => {
    const r = toShareOfTotal([["Home", 300], ["Food", 100], ["Refund", -20]]);
    assert.deepEqual(r.map(e => e[0]), ["Home", "Food", "Refund"]);
    near(r[0][1], 0.75); near(r[1][1], 0.25); near(r[2][1], -0.05);
  });
  test("no positive total: every share is null, never a division", () => {
    assert.deepEqual(toShareOfTotal([["A", -5], ["B", 0]]).map(e => e[1]), [null, null]);
  });
  test("extra tuple fields are kept", () => {
    assert.deepEqual(toShareOfTotal([["A", 50, { k: 1 }]])[0][2], { k: 1 });
  });
});

describe("flowsAsShareOfLiquid", () => {
  const series = [{ key: "a", net: 500, credits: 600, debits: 100, byAccount: { X: { credits: 600, debits: 100 } } }];
  test("each flow divided by the liquid balance at the start", () => {
    const r = flowsAsShareOfLiquid(series, 10000);
    near(r[0].net, 0.05); near(r[0].credits, 0.06); near(r[0].debits, 0.01); near(r[0].byAccount.X.credits, 0.06);
    assert.equal(series[0].net, 500);
  });
  test("a zero, negative or missing balance gives null values", () => {
    for (const base of [0, -5, null, undefined]) {
      const r = flowsAsShareOfLiquid(series, base);
      assert.equal(r[0].net, null); assert.equal(r[0].credits, null);
    }
  });
});

describe("percent forms in the chart output", () => {
  const pts = [{ label: "1 Jan", date: "2026-01-01", value: 200 }, { label: "2 Jan", date: "2026-01-02", value: 250 }];
  test("dollars mode: line chart axis and tooltips are dollars", () => {
    assert.match(lineChartSvg(pts, { title: "T" }), /\$250/);
  });
  test("a line chart can take its own value formatter", () => {
    const out = lineChartSvg(toPercentChange(pts).points, { title: "T", fmt: fmtSharePct });
    assert.match(out, /\+25\.0%/);
    assert.doesNotMatch(out, /\$/);
  });
  test("spending bars show shares, with the header, in percent mode", () => {
    setMoneyView({ allowed: "both", shown: "percent", scale: 1000 });
    setSpendShareBase([300, 100, -20]);
    const out = barChartSvg([["Home", 300], ["Food", 100], ["Refund", -20]], {});
    assert.match(out, /Share of spending/);
    assert.match(out, /75\.0%/);
    assert.match(out, /-5\.0%/);
    assert.doesNotMatch(out, /\$|of net worth/);
  });
  test("spending with a non-positive total says n/a, not Infinity or NaN", () => {
    setMoneyView({ allowed: "both", shown: "percent", scale: 1000 });
    setSpendShareBase([-5]);
    const out = barChartSvg([["Refund", -5]], {});
    assert.match(out, /n\/a/);
    assert.doesNotMatch(out, /NaN|Infinity/);
  });
  test("dollars mode: spending bars unchanged", () => {
    setSpendShareBase([300]);
    const out = barChartSvg([["Home", 300]], {});
    assert.match(out, /\$300/);
    assert.doesNotMatch(out, /Share of spending/);
  });
  test("flow summary, chart and popup use percent forms of liquid in percent mode", () => {
    setMoneyView({ allowed: "both", shown: "percent", scale: 1000 });
    const series = flowsAsShareOfLiquid([{ key: "k", date: "2026-01-01", label: "1 Jan", credits: 600, debits: 100, net: 500, byAccount: { X: { credits: 600, debits: 100 } } }], 10000);
    const summary = flowsAsShareOfLiquid([{ credits: 600, debits: 100, total: 500, label: "Jan" }], 10000)[0];
    for (const out of [flowSummaryHtml(summary), flowLineChartSvg(series, {}), flowRolloverHtml(series[0])]) {
      assert.match(out, /%/);
      assert.doesNotMatch(out, /\$|of net worth|NaN/);
    }
  });
  test("change line in a popup is a percent change, not an amount", () => {
    setMoneyView({ allowed: "both", shown: "percent", scale: 1000 });
    const out = rolloverHtml({ title: "Net worth", date: "2026-01-02", total: 250, prior: { date: "2026-01-01", total: 200 }, groups: [], rows: [] });
    assert.match(out, /Change since 2026-01-01<\/span><span class="pop-val">\+25\.0%<\/span>/);
  });
});

describe("a percent person and a toggled owner see the same percentages", () => {
  test("proportional data gives identical percent changes, shares and flows", () => {
    const K = 4_000_000;
    const dollars = [{ label: "a", value: 2_000_000 }, { label: "b", value: 2_500_000 }];
    const ratios = dollars.map(p => ({ ...p, value: p.value / K }));
    const a = toPercentChange(dollars), b = toPercentChange(ratios);
    a.points.forEach((p, i) => near(p.value, b.points[i].value));
    const sd = toShareOfTotal([["H", 300], ["F", 100]]), sr = toShareOfTotal([["H", 300 / K], ["F", 100 / K]]);
    sd.forEach((e, i) => near(e[1], sr[i][1]));
    const f = n => [{ net: n, credits: n, debits: 0, byAccount: {} }];
    near(flowsAsShareOfLiquid(f(500), 10000)[0].net, flowsAsShareOfLiquid(f(500 / K), 10000 / K)[0].net);
  });
  test("a percent person's tiny ratios are not rounded away or hidden as zero in the flow popup", () => {
    setMoneyView({ allowed: "percent", shown: "percent", scale: 1 });
    const out = flowRolloverHtml({ label: "x", net: 0.001, byAccount: { X: { credits: 0.001, debits: 0 } } });
    assert.match(out, /X/);
  });
});

describe("current snapshot follows the toggle", () => {
  test("changing the view re-renders the body without waiting for a poll", async () => {
    const el = () => ({ innerHTML: "", textContent: "", hidden: false, classList: { toggle() {}, contains: () => false }, addEventListener() {}, querySelectorAll: () => [], setAttribute() {} });
    const els = { liveView: el(), liveBody: el(), liveError: el(), liveRefresh: el() };
    const doc = { body: el(), getElementById: id => els[id], querySelectorAll: () => [], addEventListener() {}, visibilityState: "visible" };
    const payload = { as_of: "2026-10-27T15:18:04Z", market: { state: "closed" }, indices: [], liquid: { name: "Total", start: 1000, new_money: 0, current: 1100, share: 1, day: 10, day_pct: 0.01, market_gain: 100, return_pct: 0.1, share_of_gain: 1, annualized_pct: 0.1, positions: [], stale_symbols: [], unclassified_symbols: [] }, non_liquid: { rows: [], total: 0, as_of: "2026-10-26" }, checking: { rows: [], total: 0 }, debt: { rows: [], total: 0 }, tax: { pre_tax_balance: 0, pre_tax_non_liquid: 0, annuity_taxable_gain: 0, basis_missing: [], pre_tax_rate: 0.25, unrealized_gain: 0, ltcg_rate: 0.15, total: 0 }, totals: { gross_assets: 5000, net_assets: 4000, after_tax_net_worth: 3000, by_kind: {} } };
    const win = { localStorage: { getItem: () => "live", setItem() {} }, setInterval() {}, fetch: async () => ({ ok: true, json: async () => payload }) };
    setMoneyView({ allowed: "both", shown: "dollars", scale: 1 });
    initLiveView(doc, win);
    await new Promise(r => setTimeout(r, 20));
    const before = els.liveBody.innerHTML;

    assert.match(before, /\$/);
    setMoneyView({ allowed: "both", shown: "percent", scale: 5000 });
    assert.notEqual(els.liveBody.innerHTML, before);
  });
});

// --- Task 7: no dollar wording anywhere for a percent-only person ---------------------------
import { passthroughReviewHtml, flowBarChartSvg, nearMatchClause, spendingNoteText, balancesFreshnessNote, detailPopupHtml, categoryListHtml } from "../../financial_trends_reporter/frontend/charts.js";

describe("percent-only person: dollar-free text", () => {
  const DOLLAR = /\$\s?\d/;
  const items = [{ key: "k", withdrawal: { date: "2026-01-01", amount: 1000, account: "A" }, deposit: { date: "2026-01-02", amount: 1050, account: "B" }, difference: 50 }];
  test("passthroughReviewHtml is empty for percent-only, unchanged for both", () => {
    setMoneyView({ allowed: "percent", scale: 1 });
    assert.equal(passthroughReviewHtml(items), "");
    setMoneyView({ allowed: "both", shown: "dollars", scale: 1 });
    assert.match(passthroughReviewHtml(items), /review-item/);
    setMoneyView({ allowed: "both", shown: "percent", scale: 1 });
    assert.match(passthroughReviewHtml(items), /review-item/);
  });
  test("the flows note clause names $100 only when dollars may be shown", () => {
    setMoneyView({ allowed: "percent", scale: 1 });
    assert.ok(!DOLLAR.test(nearMatchClause()));
    setMoneyView({ allowed: "both", shown: "percent", scale: 1 });
    assert.match(nearMatchClause(), /\$100/);
  });
  test("YTD flow bars, spending popups and notes are dollar-free", () => {
    setMoneyView({ allowed: "percent", scale: 1e6 });
    const model = { rows: [{ name: "A", net: 0.01, toChecking: 0.02, fromChecking: 0.01 }], total: 0.01 };
    const out = [
      flowBarChartSvg(model),
      detailPopupHtml("t", [["All merchants", 0.5]]),
      categoryListHtml("t", [{ name: "c", group: "g", value: 0.5, merchants: [["All merchants", 0.5]] }]),
      barChartSvg([["Core", 0.5, { kind: "total" }]]),
      spendingNoteText(null, "x"),
      balancesFreshnessNote({ last_run: { status: "error", detail: "balance moved $5,000" }, last_ok: { latest_date: "2026-01-01" } }, "2026-01-02"),
    ].join("\n");
    assert.ok(!DOLLAR.test(out), out.match(/.{20}\$\s?\d.{20}/)?.[0]);
  });
});

describe("percent popups give a share of the popup's own total, with one heading", () => {
  const model = { title: "Net Worth", date: "2026-01-02", total: 1000, prior: { date: "2026-01-01", total: 800 },
    groups: [{ role: "Investments", items: [{ name: "IRA", value: 600 }, { name: "Cash", value: 150 }], subtotal: 750 }], lines: [["Home", 250]] };

  test("rows are bare shares, the 100% total row is gone, the change line stays", () => {
    setMoneyView({ allowed: "both", shown: "percent", scale: 5000 });
    const out = rolloverHtml(model);
    assert.match(out, /% of total/);
    assert.match(out, />60\.0%</);
    assert.match(out, />25\.0%</);
    assert.doesNotMatch(out, /pop-total/);
    assert.match(out, /Change since 2026-01-01/);
    assert.doesNotMatch(out, /of net worth|\$/);
  });

  test("a non-positive total reads n/a, not a made-up number", () => {
    setMoneyView({ allowed: "both", shown: "percent", scale: 5000 });
    assert.match(rolloverHtml({ ...model, total: -10, prior: null }), />n\/a</);
  });

  test("dollars mode keeps the total row and dollar rows", () => {
    const out = rolloverHtml(model);
    assert.match(out, /pop-total/);
    assert.match(out, /\$600/);
  });
});
