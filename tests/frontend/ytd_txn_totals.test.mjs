// Income & Expense Transactions: Debits/Credits/Total over ALL filtered rows.
import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sb = loadDashboardSandbox();
const rows = (...amts) => amts.map((a, i) => ({ r: { Amount: a }, i }));

describe("ytdTxnTotals", () => {
  test("mixed signs: debits magnitude, credits sum, total = credits - debits", () => {
    const t = sb.ytdTxnTotals(rows(-100.25, 50, "-$1,000.00", "$2,500.50", -0.5));
    assert.equal(t.debits, 1100.75);
    assert.equal(t.credits, 2550.5);
    assert.equal(t.total, 1449.75);
  });
  test("no float drift (0.1 + 0.2)", () => {
    const t = sb.ytdTxnTotals(rows(0.1, 0.2, -0.1, -0.2));
    assert.equal(t.credits, 0.3);
    assert.equal(t.debits, 0.3);
    assert.equal(t.total, 0);
  });
  test("zero matches and junk amounts give zeros", () => {
    assert.deepEqual({ ...sb.ytdTxnTotals([]) }, { debits: 0, credits: 0, total: 0 });
    const t = sb.ytdTxnTotals(rows("", "abc", undefined));
    assert.equal(t.total, 0);
  });
  test("net-negative total", () => {
    assert.equal(sb.ytdTxnTotals(rows(-30, 10)).total, -20);
  });
});

describe("ytdTxnTotalsHtml / pager", () => {
  test("currency formatting, 2 decimals, negative total", () => {
    const h = sb.ytdTxnTotalsHtml({ debits: 1234.5, credits: 0, total: -1234.5 });
    assert.match(h, /Debits = \$1,234\.50/);
    assert.match(h, /Credits = \$0\.00/);
    assert.match(h, /Total = -\$1,234\.50/);
  });
  test("top pager has totals on same line; bottom copy has no Showing text", () => {
    const t = { debits: 5, credits: 7, total: 2 };
    const top = sb.ytdTxnPager(3, 0, 3, 1, "", "", t);
    assert.match(top, /Showing 3 of 3 matching transactions\..*Debits = \$5\.00/);
    assert.equal(sb.ytdTxnPager(3, 0, 3, 1, "", "", t, true), "");
    const multi = sb.ytdTxnPager(900, 0, 100, 9, "", "", t, true);
    assert.ok(!/Showing/.test(multi));
    assert.match(multi, /Next/);
  });
});
