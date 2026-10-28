// Task 5 of the Trends percent-view plan: one money formatter that every card goes through.
import { test, describe, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { setMoneyView, moneyView, fmtAmount, fmtSharePct, onMoneyViewChange, netWorthScale } from "../../financial_trends_reporter/frontend/money_view.js";
import { fmtMoney, fmtMoneySigned } from "../../financial_trends_reporter/frontend/charts.js";
import { fmtUsd, fmtUsd2 } from "../../financial_trends_reporter/frontend/live_snapshot.js";

beforeEach(() => setMoneyView({ allowed: "both", shown: "dollars", scale: 1 }));

describe("fmtAmount", () => {
  test("percent of today's net worth when shown is percent", () => {
    setMoneyView({ allowed: "both", shown: "percent", scale: 1e6 });
    assert.equal(fmtAmount(250000), "25.0% of net worth");
  });
  test("dollars when shown is dollars", () => {
    setMoneyView({ allowed: "both", shown: "dollars", scale: 1e6 });
    assert.equal(fmtAmount(250000), "$250,000");
  });
  test("a percent person is forced to percent even if dollars are asked for", () => {
    setMoneyView({ allowed: "percent", shown: "dollars", scale: 1 });
    assert.equal(moneyView().shown, "percent");
    assert.equal(fmtAmount(0.25), "25.0% of net worth");
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
    assert.equal(fmtMoney(250), "25.0% of net worth");
    assert.equal(fmtMoneySigned(-250), "-25.0% of net worth");
    assert.equal(fmtUsd(250), "25.0% of net worth");
    assert.equal(fmtUsd2(250), "25.0% of net worth");
  });
});
