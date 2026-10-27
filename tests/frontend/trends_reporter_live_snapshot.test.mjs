// Live Snapshot view (design 2026-10-27, step 5): the pure render/poll helpers in live_snapshot.js
// and the toggle markup in index.html.
import { test, describe } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  parseSavedView, shouldPoll, changeHtml, statusText, liveViewHtml, fmtPct, hintText,
} from "../../financial_trends_reporter/frontend/live_snapshot.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const html = fs.readFileSync(path.join(HERE, "..", "..", "financial_trends_reporter", "frontend", "index.html"), "utf8");

const ROW = (name, extra = {}) => ({
  name, start: 1000, new_money: 0, current: 1100, share: 0.5, day: 10, day_pct: 0.0092, market_gain: 100,
  return_pct: 0.1, share_of_gain: 0.5, annualized_pct: 0.12, ...extra,
});
const DATA = {
  as_of: "2026-10-27T15:18:04Z", market: { state: "open", early_close: false }, delayed_minutes: 15,
  indices: [{ symbol: "^GSPC", label: "S&P 500", price: 6800, day_pct: 0.0072, stale: false },
            { symbol: "^IXIC", label: "Nasdaq", price: null, day_pct: null, stale: true }],
  baseline_date: "2025-12-31",
  liquid: {
    ...ROW("Total"), checking_net_flows: -36000, stale_symbols: [], unclassified_symbols: [],
    by_class: [ROW("Equity", { tickers: [{ ...ROW("ITOT"), symbol: "ITOT" }] }), ROW("Cash", { tickers: [], day: 0, annualized_pct: null })],
    by_equity_subclass: [ROW("US Total Equity")],
  },
  reconciliation: { holdings_value: 2844220, monarch_value: 2816837, monarch_as_of: "2026-10-26", delta_pct: 0.0097, flag: false },
  non_liquid: { rows: [{ name: "Joint <Annuity>", kind: "Fixed Income", value: 1269216, share: 0.3, tax_treatment: "pre_tax" }], total: 1269216, as_of: "2026-10-26" },
  checking: { rows: [{ name: "Family Checking", value: 20795 }], total: 20795 },
  debt: { rows: [{ name: "Mortgage 1.99% 7/34", value: 278138 }], total: 278138 },
  tax: { pre_tax_balance: 1868961, pre_tax_non_liquid: 1851791, annuity_taxable_gain: 0, basis_missing: ["Annuity - Matt"],
         pre_tax_rate: 0.25, unrealized_gain: 40509, ltcg_rate: 0.15, total: 936255 },
  totals: { gross_assets: 6866606, net_assets: 6575106, after_tax_net_worth: 5638210, by_kind: { Equity: 2484616, Cash: 200825 } },
};

describe("view toggle", () => {
  test("saved view: live only when saved as live", () => {
    assert.equal(parseSavedView(null), "trends");
    assert.equal(parseSavedView("live"), "live");
    assert.equal(parseSavedView("nonsense"), "trends");
  });
  test("markup: a labelled two-button group, Trends pressed, and the Live section", () => {
    assert.match(html, /role="group" aria-label="View"/);
    assert.match(html, /data-view="trends" aria-pressed="true"/);
    assert.match(html, /data-view="live" aria-pressed="false"/);
    assert.match(html, /<section id="liveView"/);
    assert.match(html, /<script type="module" src="\.\/live_snapshot\.js"><\/script>/);
  });
  test("live mode hides the time scope and the trend cards", () => {
    assert.match(html, /body\.live-mode \.grid/);
    assert.match(html, /body\.live-mode \.scope-pick/);
  });
});

describe("polling", () => {
  test("polls in pre, open and post market while shown and visible", () => {
    for (const state of ["pre", "open", "post"]) assert.equal(shouldPoll({ shown: true, visible: true, market: state }), true);
  });
  test("never when closed, hidden, or another view is shown", () => {
    assert.equal(shouldPoll({ shown: true, visible: true, market: "closed" }), false);
    assert.equal(shouldPoll({ shown: true, visible: false, market: "open" }), false);
    assert.equal(shouldPoll({ shown: false, visible: true, market: "open" }), false);
  });
});

describe("formatting", () => {
  test("changes carry an arrow as well as a colour class", () => {
    assert.match(changeHtml(1234.4), /class="up"[^>]*>▲ \$1,234/);
    assert.match(changeHtml(-50), /class="down"[^>]*>▼ -\$50/);
    assert.match(changeHtml(0.0058, true), /▲ 0\.58%/);
    assert.equal(changeHtml(null), '<span class="na">–</span>');
  });
  test("percentages", () => {
    assert.equal(fmtPct(0.1178), "11.78%");
    assert.equal(fmtPct(null), "–");
  });
  test("status line says delayed, closed, or names stale prices", () => {
    assert.match(statusText(DATA), /Delayed ~15 min/);
    assert.match(statusText({ ...DATA, market: { state: "closed" } }), /Market closed/);
    const stale = { ...DATA, liquid: { ...DATA.liquid, stale_symbols: ["IXUS", "AVUV"] } };
    assert.match(statusText(stale), /Old prices for AVUV, IXUS|Old prices for IXUS, AVUV/);
  });
});

describe("liveViewHtml", () => {
  const out = liveViewHtml(DATA);
  test("headline is after-tax net worth with the liquid day change", () => {
    assert.match(out, /After-tax net worth/);
    assert.match(out, /\$5,638,210/);
  });
  test("index chips, with a dash when a quote is missing", () => {
    assert.match(out, /S&amp;P 500/);
    assert.match(out, /Nasdaq[\s\S]*?–/);
  });
  test("liquid table: column headers and expandable class rows", () => {
    for (const h of ["Start (12/31)", "Bought since", "Current", "Day %", "Market gain", "Return %", "Share of gain", "Annualized"]) {
      assert.ok(out.includes(h), h);
    }
    assert.match(out, /<button[^>]*aria-expanded="false"[^>]*data-group="Equity"/);
    assert.match(out, /<tr class="ticker-row" data-parent="Equity" hidden>/);
  });
  test("the total row is 100% of value and of gain", () => {
    const foot = out.match(/<tfoot>([\s\S]*?)<\/tfoot>/)[1];
    assert.match(foot, /<td class="num col-share">100%<\/td>/);
    assert.match(foot, /<td class="num col-sog">100\.0%<\/td>/);
  });
  test("names are escaped", () => {
    assert.ok(out.includes("Joint &lt;Annuity&gt;"));
    assert.ok(!out.includes("<Annuity>"));
  });
  test("non-liquid, tax and debt are collapsed sections", () => {
    assert.match(out, /<details class="live-section"><summary>Non-liquid assets/);
    assert.match(out, /<details class="live-section"><summary>Estimated tax/);
    assert.match(out, /<details class="live-section"><summary>Debt/);
  });
  test("tax section says which annuities have no basis yet", () => {
    assert.match(out, /Annuity - Matt/);
    assert.match(out, /after-tax premium not set/i);
  });
  test("reconciliation: a quiet line when close, a warning when flagged", () => {
    assert.match(out, /vs\. imported balances/);
    assert.ok(!out.includes('class="recon warn"'));
    const flagged = liveViewHtml({ ...DATA, reconciliation: { ...DATA.reconciliation, delta_pct: 0.05, flag: true } });
    assert.match(flagged, /class="recon warn"/);
  });
  test("missing annualized shows a dash, not 0%", () => {
    assert.match(liveViewHtml(DATA), /<td class="num col-ann">–<\/td>/);
  });
  test("an error body renders a message", () => {
    assert.match(liveViewHtml({ error: "plan store locked" }), /plan store locked/);
  });
});

const REC = {
  ...DATA.reconciliation,
  accounts: [{ holdings_account: "Member_1_IRA", monarch_accounts: ["Matt IRA"], holdings_value: 500000, monarch_value: 499800,
               delta: 200, delta_pct: 0.0004, flag: false, hints: [] }],
  unmapped_monarch: [], unmapped_holdings: [], footing: 2844220, monarch_stale: false,
};
const REC_FLAGGED = {
  ...REC, delta_pct: 0.0102, flag: true,
  accounts: [{ holdings_account: "Member_1_IRA", monarch_accounts: ["Matt IRA"], holdings_value: 513250, monarch_value: 500000,
               delta: 13250, delta_pct: 0.0265, flag: true,
               hints: [{ kind: "after_balance_date", count: 2, value: 5000 }, { kind: "stale_prices", symbols: ["IXUS"] },
                       { kind: "matches_position", symbol: "IXUS", shares: 200, purchase_date: "2025-06-01", value: 13250 },
                       { kind: "direction", higher: "holdings" }] }],
  unmapped_monarch: [{ name: "Old 401k", value: 12000 }], unmapped_holdings: [{ account: "Joint_Brokerage", value: 90000 }],
};

describe("reconciliation by account", () => {
  test("warning names the Investment Holdings page", () => {
    const out = liveViewHtml({ ...DATA, reconciliation: { ...REC, delta_pct: 0.0102, flag: true } });
    assert.match(out, /Check the Investment Holdings page in the Retirement Planner for trades or transfers not yet entered\./);
    assert.ok(!out.includes("client_holdings"));
  });
  test("lists rows, opens when flagged, and shows hints", () => {
    const out = liveViewHtml({ ...DATA, reconciliation: REC_FLAGGED });
    assert.match(out, /<details class="live-section recon-accounts" open>/);
    assert.match(out, /Member_1_IRA/);
    assert.match(out, /⚠/);
    assert.match(out, /The gap is close to 200 sh IXUS bought 2025-06-01 \(\$13,250\)\./);
    assert.match(out.replaceAll("&#39;", "'"), /2 lot\(s\) bought after the imported balance date \(\$5,000\)\. The imported balance can't include them yet\./);
    assert.match(out, /Old prices for IXUS\./);
    assert.match(out, /Holdings are higher: a sale or transfer out may not be entered yet\./);
    assert.match(out, /Old 401k/);
    assert.match(out, /Joint_Brokerage/);
    assert.match(out, /Not linked to a holdings account, so not compared\. Link them in the Retirement Planner\./);
    assert.match(out, /Holdings total/);
  });
  test("summary counts the accounts to check", () => {
    const out = liveViewHtml({ ...DATA, reconciliation: REC_FLAGGED });
    assert.match(out, /<summary>Reconciliation by account <b>⚠ 1 to check<\/b><\/summary>/);
    assert.ok(!liveViewHtml({ ...DATA, reconciliation: REC }).includes("to check"));
  });
  test("account names are escaped", () => {
    const evil = "<img src=x onerror=alert(1)>";
    const rec = { ...REC_FLAGGED, accounts: [{ ...REC_FLAGGED.accounts[0], holdings_account: evil, monarch_accounts: [evil] }],
                  unmapped_monarch: [{ name: evil, value: 1 }], unmapped_holdings: [{ account: evil, value: 1 }] };
    const out = liveViewHtml({ ...DATA, reconciliation: rec });
    assert.ok(!out.includes(evil));
    assert.ok(out.includes("&lt;img src=x onerror=alert(1)&gt;"));
  });
  test("flag title drops the percent when there is no Monarch balance to divide by", () => {
    const acct = { ...REC_FLAGGED.accounts[0], delta_pct: null, monarch_value: 0 };
    const out = liveViewHtml({ ...DATA, reconciliation: { ...REC_FLAGGED, accounts: [acct] } });
    assert.match(out, /title="Differs from the imported balance by more than \$100"/);
    assert.match(liveViewHtml({ ...DATA, reconciliation: REC_FLAGGED }), /title="Differs from the imported balance by more than 1% and \$100"/);
  });
  test("stays closed when nothing flags", () => {
    const out = liveViewHtml({ ...DATA, reconciliation: REC });
    assert.match(out, /<details class="live-section recon-accounts">/);
    assert.ok(!out.includes("⚠"));
  });
  test("no section when the response has no account breakdown", () => {
    assert.ok(!liveViewHtml(DATA).includes("recon-accounts"));
  });
  test("Monarch older than the previous session shows a note", () => {
    assert.match(liveViewHtml({ ...DATA, reconciliation: { ...REC, monarch_stale: true } }).replaceAll("&#39;", "'"), /moves since then aren't backed out/);
  });
  test("lower-holdings hint and a position with no purchase date", () => {
    assert.equal(hintText({ kind: "direction", higher: "monarch" }), "Holdings are lower: a purchase or transfer in may not be entered yet.");
    assert.equal(hintText({ kind: "matches_position", symbol: "VTI", shares: 15, purchase_date: null, value: 4112 }),
      "The gap is close to 15 sh VTI (\$4,112).");
  });
});
