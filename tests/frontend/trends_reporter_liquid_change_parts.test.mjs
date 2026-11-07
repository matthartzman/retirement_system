// Liquid Investments and Cash pop-up: the Change line's three parts (deposits & withdrawals, income less fees,
// market gain/loss) from /api/liquid-change, summed over the switched-on accounts and (prior date, date].
import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { changeParts, rolloverHtml, accountMatchKey } from "../../financial_trends_reporter/frontend/charts.js";

const BALANCES = {
  dates: ["2026-10-01", "2026-10-31"], series: {},
  accounts: [
    { account_key: "c", display_name: "Family Checking", type: "Cash", enabled: { holdings: true } },
    { account_key: "i", display_name: "IRA - Matt", type: "Retirement", enabled: { holdings: true } },
    { account_key: "t", display_name: "Trust  Under Agreement", type: "Investment", enabled: { holdings: true } },
    { account_key: "a", display_name: "Annuity", type: "Annuity/Pension", enabled: { holdings: false } },
  ],
};
const LIQUID = {
  broker_covered: ["IRA - Matt"],
  daily: {
    "Family Checking": { "2026-10-01": { flows: 999, income: 0 }, "2026-10-05": { flows: 5000, income: 2 }, "2026-10-20": { flows: -3000, income: 0 } },
    "IRA - Matt": { "2026-10-15": { flows: 0, income: 150 }, "2026-11-02": { flows: 0, income: 77 } },
    "Trust Under Agreement": { "2026-10-10": { flows: 1000, income: -10 } },
    "Annuity": { "2026-10-10": { flows: -50000, income: 0 } },
  },
};

describe("Liquid change parts", () => {
  const prior = { date: "2026-10-01", total: 100000 };
  test("sums switched-on accounts over (prior, date] and leaves the rest to market", () => {
    const p = changeParts(110000, prior, "2026-10-31", LIQUID, BALANCES);
    assert.equal(p.flows, 5000 - 3000 + 1000);   // the prior day itself and the excluded annuity are out
    assert.equal(p.income, 2 + 150 - 10);
    assert.equal(p.market, 10000 - 3000 - 142);
    assert.equal(p.flows + p.income + p.market, 10000);
    assert.equal(p.uncovered, 1);                 // the trust has no broker file
  });
  test("no ledger or no prior point: no parts", () => {
    assert.equal(changeParts(110000, prior, "2026-10-31", null, BALANCES), null);
    assert.equal(changeParts(110000, null, "2026-10-31", LIQUID, BALANCES), null);
  });
  test("the pop-up shows the three lines under Change, signed", () => {
    const parts = changeParts(110000, prior, "2026-10-31", LIQUID, BALANCES);
    const html = rolloverHtml({ title: "Liquid Investments and Cash", date: "2026-10-31", total: 110000, prior, parts, groups: [], lines: [] });
    for (const label of ["Deposits &amp; withdrawals", "Income less fees", "Market gain/loss"]) assert.ok(html.includes(label), label);
    assert.ok(html.indexOf("Change since") < html.indexOf("Deposits &amp; withdrawals"));
    assert.match(html, /no broker file for 1 account:/);
  });
  test("account names match ignoring case, spacing and symbols", () => {
    assert.equal(accountMatchKey("Trust  Under Agreement"), accountMatchKey("trust under agreement"));
  });
});
