// Live Snapshot view (design 2026-10-27, step 5): the pure render/poll helpers in live_snapshot.js
// and the toggle markup in index.html.
import { test, describe } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  parseSavedView, shouldPoll, changeHtml, statusText, liveViewHtml, fmtPct, hintText, lotLabel,
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
    assert.match(out, /<button[^>]*aria-expanded="false"[^>]*data-path="Asset class\/Equity"/);
    assert.match(out, /<tr class="ticker-row" data-path="Asset class\/Equity\/ITOT" data-parent="Asset class\/Equity" hidden>/);
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
  test("tax table shows the Planner method, its rates and the flat-rate comparison", () => {
    const data = { ...DATA, tax: { ...DATA.tax, method: "planner", pre_tax_rate: 0.22, ltcg_rate: null, unrealized_gain: 200000, ltcg_tax: 47000,
      ltcg_detail: { federal: 30000, niit: 7600, state: 9400 }, hsa_balance: 20000, hsa_tax: 4400, flat_total: 90000, total: 100000, rate_source: "planner" } };
    const html = liveViewHtml(data);
    assert.match(html, /Same method as the Retirement Planner/);
    assert.match(html, /HSA balance/);
    assert.match(html, /federal \$30,000, NIIT \$7,600, state \$9,400/);
    assert.match(html, /Flat 25% \/ 15% rates would give \$90,000/);
  });
  test("a note receivable's future interest gets its own tax line and treatment label", () => {
    const data = { ...DATA, non_liquid: { ...DATA.non_liquid, rows: [{ name: "RedMane Note Jan 2026", kind: "Fixed Income", value: 512848, share: 1, tax_treatment: "note_interest" }] },
      tax: { ...DATA.tax, note_interest: 120349, note_rows: [{ name: "RedMane Note Jan 2026", note: "RedMane Note", interest: 120349 }] } };
    const html = liveViewHtml(data);
    assert.match(html, /Note interest still to be paid \(RedMane Note Jan 2026\)<\/th><td class="num">\$120,349/);
    assert.match(html, /Interest taxed/);
  });
  test("no note line when there is no note interest", () => {
    assert.doesNotMatch(out, /Note interest/);
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

const LOT = (date, extra = {}) => ({ ...ROW(date || ""), purchase_date: date, shares: 120, purchase_price: 412.1, reinvested: false, ...extra });
const ITOT = () => ({
  ...ROW("ITOT"), symbol: "ITOT",
  accounts: [
    { ...ROW("Member_1_IRA"), lots: [LOT("2024-03-15"), LOT(null, { reinvested: true })] },
    { ...ROW("Joint <Brokerage>"), lots: [LOT("2025-01-02")] },
  ],
});
const DATA_WITH_LOTS = {
  ...DATA,
  liquid: {
    ...DATA.liquid,
    by_class: [ROW("Equity", { tickers: [ITOT()] })],
    by_equity_subclass: [ROW("US Total Equity", { tickers: [ITOT()] })],
  },
};

describe("holdings drill-down", () => {
  test("ticker → account → lot rows, hidden until expanded", () => {
    const out = liveViewHtml(DATA_WITH_LOTS);
    assert.match(out, /<button[^>]*aria-expanded="false"[^>]*data-path="Asset class\/Equity\/ITOT"/);
    assert.match(out, /<button[^>]*aria-expanded="false"[^>]*data-path="Asset class\/Equity\/ITOT\/Member_1_IRA"/);
    assert.match(out, /<tr class="acct-row" data-path="Asset class\/Equity\/ITOT\/Member_1_IRA" data-parent="Asset class\/Equity\/ITOT" hidden>/);
    assert.match(out, /<tr class="lot-row" data-parent="Asset class\/Equity\/ITOT\/Member_1_IRA" hidden>/);
    assert.ok(out.includes("2024-03-15 · 120 sh @ $412.10"));
  });
  test("lot label", () => {
    assert.equal(lotLabel({ purchase_date: "2024-03-15", shares: 120, purchase_price: 412.1, reinvested: false }), "2024-03-15 · 120 sh @ $412.10");
    assert.match(lotLabel({ purchase_date: "2026-04-01", shares: 0.5, purchase_price: 50, reinvested: true }), / · reinvested$/);
  });
  test("undated and unpriced lots still read sensibly", () => {
    assert.equal(lotLabel({ purchase_date: null, shares: 10, purchase_price: 0, reinvested: false }), "Undated · 10 sh @ $0.00");
    assert.equal(lotLabel({ purchase_date: null, shares: 10, purchase_price: null, reinvested: true }), "Undated · 10 sh · reinvested");
  });
  test("same ticker in both tables gets distinct paths", () => {
    const out = liveViewHtml(DATA_WITH_LOTS);
    assert.match(out, /data-path="Asset class\/Equity\/ITOT"/);
    assert.match(out, /data-path="Sub-class\/US Total Equity\/ITOT"/);
    const paths = [...out.matchAll(/<tr class="(?:class|ticker|acct)-row" data-path="([^"]*)"/g)].map((m) => m[1]);
    assert.equal(new Set(paths).size, paths.length);
  });
  test("account names are escaped in paths and labels", () => {
    const out = liveViewHtml(DATA_WITH_LOTS);
    assert.ok(out.includes("Joint &lt;Brokerage&gt;"));
    assert.ok(!out.includes("Joint <Brokerage>"));
  });
  test("rows without accounts render plain, with no expand button", () => {
    const out = liveViewHtml(DATA);
    assert.match(out, /<th scope="row" class="ticker">ITOT<\/th>/);
    assert.ok(!/<button[^>]*data-path="Asset class\/Equity\/ITOT"/.test(out));
  });
});

describe("friendly account labels", () => {
  const labels = { Member_1_IRA: "Matt IRA" };
  test("account rows show the label; paths keep the account id", () => {
    const out = liveViewHtml({ ...DATA_WITH_LOTS, account_labels: labels });
    assert.match(out, /data-path="Asset class\/Equity\/ITOT\/Member_1_IRA" data-label="Matt IRA">▸ Matt IRA<\/button>/);
    assert.ok(!/>▸ Member_1_IRA</.test(out));
  });
  test("reconciliation rows and unmapped holdings show the label", () => {
    const rec = { ...REC_FLAGGED, unmapped_holdings: [{ account: "Member_1_IRA", value: 1 }] };
    const out = liveViewHtml({ ...DATA, account_labels: labels, reconciliation: rec });
    assert.ok(!out.includes("Member_1_IRA"));
    assert.match(out, /Matt IRA/);
  });
  test("an account without a label falls back to its id, and labels don't carry over between renders", () => {
    liveViewHtml({ ...DATA_WITH_LOTS, account_labels: labels });
    assert.match(liveViewHtml(DATA_WITH_LOTS), />▸ Member_1_IRA<\/button>/);
  });
});

describe("imported balance sync date", () => {
  const acct = REC_FLAGGED.accounts[0];
  test("a balance more than a session old says when it last synced", () => {
    const rec = { ...REC_FLAGGED, accounts: [{ ...acct, balance_as_of: "2026-10-22", balance_stale: true }] };
    assert.match(liveViewHtml({ ...DATA, reconciliation: rec }), /last synced 2026-10-22/);
  });
  test("a fresh balance shows no date", () => {
    const rec = { ...REC_FLAGGED, accounts: [{ ...acct, balance_as_of: "2026-10-26", balance_stale: false }] };
    assert.ok(!liveViewHtml({ ...DATA, reconciliation: rec }).includes("last synced"));
  });
});

// --- Percent-only people: no reconciliation, no dollar figures ------------------------------
import { setMoneyView } from "../../financial_trends_reporter/frontend/money_view.js";

describe("percent-only live snapshot", () => {
  const WITH_RECON = {
    ...DATA,
    reconciliation: { ...DATA.reconciliation, accounts: [{ holdings_account: "A", holdings_value: 5, monarch_value: 4, delta: 1, delta_pct: 0.2, flag: true, hints: [{ kind: "stale_prices", symbols: ["X"] }] }],
      unmapped_monarch: [{ name: "Foo", value: 1234 }], unmapped_holdings: [{ account: "B", value: 4321 }], footing: 5 },
    tax: { ...DATA.tax, method: "planner", pre_tax_rate: 0.25, ltcg_rate: 0.15, ltcg_tax: 6000, flat_total: 900000, ltcg_detail: { federal: 1, niit: 2, state: 3 }, hsa_balance: 100, hsa_tax: 25 },
  };
  test("no Reconciliation section and no tax amounts sentence", () => {
    setMoneyView({ allowed: "percent", scale: 1e6 });
    try {
      const out = liveViewHtml(WITH_RECON);
      assert.ok(!/Reconciliation/i.test(out));
      assert.ok(!out.includes("recon"));
      assert.ok(!/Flat 25%/.test(out) || !/different/.test(out));
    } finally { setMoneyView({ allowed: "both", shown: "dollars", scale: 1 }); }
  });
  test("no HTML matches a dollar amount in percent mode", () => {
    setMoneyView({ allowed: "percent", scale: 1e6 });
    try {
      const out = liveViewHtml(WITH_RECON);
      assert.ok(!/\$\s?\d/.test(out), out.match(/.{30}\$\s?\d.{20}/)?.[0]);
    } finally { setMoneyView({ allowed: "both", shown: "dollars", scale: 1 }); }
  });
  test("both keeps the Reconciliation section in either toggle position", () => {
    for (const shown of ["dollars", "percent"]) {
      setMoneyView({ allowed: "both", shown, scale: 1e6 });
      assert.match(liveViewHtml(WITH_RECON), /Reconciliation by account/);
    }
    setMoneyView({ allowed: "both", shown: "dollars", scale: 1 });
  });
});

import { setMoneyView as __setMoneyView } from "../../financial_trends_reporter/frontend/money_view.js";

describe("liveViewHtml in the percent view states each base once", () => {
  const percentHtml = () => { __setMoneyView({ allowed: "both", shown: "percent", scale: 1000 }); return liveViewHtml(DATA); };
  const after = () => __setMoneyView({ allowed: "both", shown: "dollars", scale: 1 });

  test("no cell repeats the base phrase; each heading carries it", () => {
    const out = percentHtml(); after();
    assert.doesNotMatch(out.replace(/<span class="unit">[^<]*<\/span>/g, ""), /of net worth/);
    assert.match(out, /<h2>Liquid investments <span class="unit">% of net worth<\/span><\/h2>/);
    assert.doesNotMatch(out, /\$\s?\d/);
  });

  test("the dollar day column is hidden and the liquid card is marked", () => {
    const out = percentHtml(); after();
    assert.match(out, /class="card live-card pm"/);
  });

  test("dollars mode output is unchanged", () => {
    after();
    const out = liveViewHtml(DATA);
    assert.doesNotMatch(out, /class="unit"|live-card pm/);
    assert.match(out, /<h2>Liquid investments<\/h2>/);
  });
});
