// Live Snapshot view (design 2026-10-27, step 5): the pure render/poll helpers in live_snapshot.js
// and the toggle markup in index.html.
import { test, describe } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  parseSavedView, shouldPoll, changeHtml, statusText, liveViewHtml, fmtPct, hintText, lotLabel, startDayText, isYearToDate, initLiveView,
} from "../../financial_trends_reporter/frontend/live_snapshot.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const html = fs.readFileSync(path.join(HERE, "..", "..", "financial_trends_reporter", "frontend", "index.html"), "utf8");

const ROW = (name, extra = {}) => ({
  name, start: 1000, new_money: 0, current: 1100, share: 0.5, day: 10, day_pct: 0.0092, market_gain: 100,
  return_pct: 0.1, share_of_gain: 0.5, annualized_pct: 0.12, ...extra,
});
// One lot of the flat list the page groups (liquid.positions).
const POS = (o = {}) => ({
  account: "Member_1_IRA", symbol: "ITOT", title: "", asset_class: "Equity", subclass: "US Total Equity", purchase_date: "2024-03-15",
  shares: 120, purchase_price: 412.1, reinvested: false, start: 1000, new_money: 0, weighted: 0, current: 1100, day: 10, ...o,
});
const CASH_LOT = (o = {}) => POS({ account: "Family_Trust", symbol: "CASH", title: "Cash and sweep balances", asset_class: "Cash", subclass: null,
  purchase_date: "2026-06-01", shares: 100, purchase_price: 1, start: 100, current: 100, day: 0, ...o });
const DATA = {
  as_of: "2026-10-27T15:18:04Z", market: { state: "open", early_close: false }, delayed_minutes: 15,
  indices: [{ symbol: "^GSPC", label: "S&P 500", price: 6800, day_pct: 0.0072, stale: false },
            { symbol: "^IXIC", label: "Nasdaq", price: null, day_pct: null, stale: true }],
  baseline_date: "2025-12-31",
  liquid: {
    ...ROW("Total"), checking_net_flows: -36000, stale_symbols: [], unclassified_symbols: [],
    positions: [POS(), CASH_LOT()],
  },
  days: 300,
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
  test("live mode hides the trend cards and the custom end date, but keeps the time scope", () => {
    assert.match(html, /body\.live-mode \.grid, body\.live-mode #customTo,/);
    assert.doesNotMatch(html, /body\.live-mode \.scope-pick/);
    assert.doesNotMatch(html, /body\.live-mode #scopeLabel/);
  });
  test("the time scope toolbar follows the title, with no description paragraph", () => {
    assert.ok(html.indexOf('<div class="title-row">') < html.indexOf('id="scopeBar"'));
    assert.doesNotMatch(html, /<div class="sub">Four charts/);
  });
  test("the $ | % toggle fills only the active side", () => {
    assert.match(html, /<span class="seg seg-dollars" aria-hidden="true">\$<\/span><span class="seg seg-percent" aria-hidden="true">%<\/span>/);
    assert.match(html, /#moneyToggle\[aria-pressed="false"\] \.seg-dollars, #moneyToggle\[aria-pressed="true"\] \.seg-percent \{ background: #2563eb/);
    assert.doesNotMatch(html, /#moneyToggle\[aria-pressed="true"\] \{ background/);
  });
  test("the Trends page publishes its scope for Live Snapshot", () => {
    assert.match(html, /ds\.scopeFrom = from \|\| ""/);
    assert.match(html, /new CustomEvent\("trends-scope-change"/);
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
  test("year to date headline for a 12/31 start; 'Since' and the date for any other", () => {
    assert.match(out, /Year to date/);
    const since = liveViewHtml({ ...DATA, baseline_date: "2026-09-25" });
    assert.match(since, /Since 9\/25/);
    assert.match(since, /Start \(9\/25\)/);
    assert.doesNotMatch(since, /12\/31/);
  });
  test("start date text", () => {
    assert.equal(startDayText("2026-09-25", "2026-10-27T15:00:00Z"), "9/25");
    assert.equal(startDayText("2025-12-31", "2026-10-27T15:00:00Z"), "12/31");
    assert.equal(startDayText("2025-10-24", "2026-10-27T15:00:00Z"), "10/24/25");
    assert.equal(isYearToDate("2025-12-31", "2026-10-27"), true);
    assert.equal(isYearToDate("2024-12-31", "2026-10-27"), false);
    assert.equal(isYearToDate("2026-09-25", "2026-10-27"), false);
  });
  test("index chips, with a dash when a quote is missing", () => {
    assert.match(out, /S&amp;P 500/);
    assert.match(out, /Nasdaq[\s\S]*?–/);
  });
  test("liquid table: column headers, and the first level's rows are expandable", () => {
    for (const h of ["Start (12/31)", "Bought since", "Current", "Day %", "Market gain", "Return %", "Share of gain", "Annualized"]) {
      assert.ok(out.includes(h), h);
    }
    assert.match(out, /<th scope="col">Sub-class<\/th>/);
    assert.match(out, /<tr class="top-row" data-depth="0" data-path="\/US%20Total%20Equity"><th scope="row" class="dim-subclass"><button[^>]*aria-expanded="false"/);
    assert.match(out, /<tr data-depth="1" data-path="\/US%20Total%20Equity\/ITOT" data-parent="\/US%20Total%20Equity" hidden>/);
  });
  test("one liquid table: no separate equity sub-class table", () => {
    assert.doesNotMatch(out, /Equity by sub-class/);
    assert.equal((out.match(/<table class="live-table">/g) || []).length, 1);
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
  test("annualized is a dash until 90 days have passed, never 0%", () => {
    const rows = (data) => liveViewHtml(data).match(/<tbody>[\s\S]*?<\/tbody>/)[0];   // the total row comes from the server
    assert.match(rows({ ...DATA, days: 60 }), /<td class="num col-ann">–<\/td>/);
    assert.doesNotMatch(rows({ ...DATA, days: 60 }), /<td class="num col-ann">(?!–)/);
    assert.match(rows(DATA), /<td class="num col-ann">\d/);
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
  test("lists rows, starts closed even when flagged, and shows hints", () => {
    const out = liveViewHtml({ ...DATA, reconciliation: REC_FLAGGED });
    assert.match(out, /<details class="live-section recon-accounts"><summary>Reconciliation by account <b>⚠ 1 to check<\/b>/);
    assert.doesNotMatch(out, /recon-accounts" open/);
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

const ITOT_LOTS = [POS(), POS({ purchase_date: null, reinvested: true }), POS({ account: "Joint <Brokerage>", purchase_date: "2025-01-02", current: 500, start: 450 })];
const DATA_WITH_LOTS = { ...DATA, liquid: { ...DATA.liquid, positions: ITOT_LOTS } };

describe("holdings drill-down", () => {
  test("symbol → account → lot rows, hidden until expanded", () => {
    const out = liveViewHtml(DATA_WITH_LOTS);
    assert.match(out, /<button[^>]*aria-expanded="false"[^>]*data-path="\/US%20Total%20Equity\/ITOT"/);
    assert.match(out, /<button[^>]*aria-expanded="false"[^>]*data-path="\/US%20Total%20Equity\/ITOT\/Member_1_IRA"/);
    assert.match(out, /<tr data-depth="2" data-path="\/US%20Total%20Equity\/ITOT\/Member_1_IRA" data-parent="\/US%20Total%20Equity\/ITOT" hidden>/);
    assert.match(out, /<tr data-depth="3" data-parent="\/US%20Total%20Equity\/ITOT\/Member_1_IRA" hidden><th scope="row" class="dim-lot">/);
    assert.ok(out.includes("2024-03-15 · 120 @ $412.10"));
    assert.ok(!out.includes(" 120 sh"));
  });
  test("lot label", () => {
    assert.equal(lotLabel({ purchase_date: "2024-03-15", shares: 120, purchase_price: 412.1, reinvested: false }), "2024-03-15 · 120 @ $412.10");
    assert.match(lotLabel({ purchase_date: "2026-04-01", shares: 0.5, purchase_price: 50, reinvested: true }), / · reinvested$/);
  });
  test("undated and unpriced lots still read sensibly", () => {
    assert.equal(lotLabel({ purchase_date: null, shares: 10, purchase_price: 0, reinvested: false }), "Undated · 10 @ $0.00");
    assert.equal(lotLabel({ purchase_date: null, shares: 10, purchase_price: null, reinvested: true }), "Undated · 10 · reinvested");
  });
  test("every row's path is unique", () => {
    const out = liveViewHtml(DATA_WITH_LOTS);
    const paths = [...out.matchAll(/<tr[^>]* data-path="([^"]*)"/g)].map((m) => m[1]);
    assert.ok(paths.length >= 4);
    assert.equal(new Set(paths).size, paths.length);
  });
  test("account names are escaped in paths and labels", () => {
    const out = liveViewHtml(DATA_WITH_LOTS);
    assert.ok(out.includes("Joint &lt;Brokerage&gt;"));
    assert.ok(!out.includes("Joint <Brokerage>"));
  });
  test("a row with nothing below it renders plain, with no expand button", () => {
    const out = liveViewHtml({ ...DATA, liquid: { ...DATA.liquid, positions: [POS()] } }, ["lot"]);
    assert.match(out, /<th scope="row" class="dim-lot">2024-03-15 · 120 @ \$412\.10<\/th>/);
    assert.doesNotMatch(out, /<button[^>]*class="expand"/);
  });
});

describe("cash holdings", () => {
  const CASH = [
    CASH_LOT({ account: "Zed_Trust", purchase_date: "2026-06-01" }),
    CASH_LOT({ account: "Member_1_Trust", purchase_date: "2026-05-01" }),
    CASH_LOT({ account: "alpha_Checking", purchase_date: "2026-07-01" }),
  ];
  const data = (extra = {}) => ({ ...DATA, ...extra, liquid: { ...DATA.liquid, positions: CASH } });
  const labels = { Zed_Trust: "Zed Trust", Member_1_Trust: "Matt Trust", alpha_Checking: "alpha Checking" };
  test("the account row carries the lot date; no expand button and no lot row", () => {
    const out = liveViewHtml(data({ account_labels: labels }));
    assert.match(out, /<th scope="row" class="dim-account">Matt Trust <span class="muted">· 2026-05-01<\/span><\/th>/);
    assert.doesNotMatch(out, /dim-lot/);
    assert.doesNotMatch(out, /data-path="[^"]*Member_1_Trust"/);
  });
  test("cash accounts sort A to Z by the name shown, ignoring case", () => {
    const out = liveViewHtml(data({ account_labels: labels }));
    const order = [...out.matchAll(/<th scope="row" class="dim-account">([^<]*?) <span/g)].map((m) => m[1]);
    assert.deepEqual(order, ["alpha Checking", "Matt Trust", "Zed Trust"]);
  });
  test("other symbols keep their lot rows, accounts A to Z by the name shown", () => {
    const out = liveViewHtml(DATA_WITH_LOTS);
    assert.match(out, /dim-lot/);
    const order = [...out.matchAll(/class="dim-account"><button[^>]*>▸ ([^<]*)<\/button>/g)].map((m) => m[1]);
    assert.deepEqual(order, ["Joint &lt;Brokerage&gt;", "Member_1_IRA"]);
  });
});

describe("holding titles", () => {
  test("the fund name follows the symbol, muted and escaped", () => {
    const out = liveViewHtml({ ...DATA, liquid: { ...DATA.liquid, positions: [POS({ title: "iShares Core <S&P> ETF" })] } });
    assert.match(out, /ITOT<\/button> <span class="muted ticker-title">iShares Core &lt;S&amp;P&gt; ETF<\/span>/);
  });
  test("no title, no empty span", () => {
    assert.doesNotMatch(liveViewHtml(DATA_WITH_LOTS), /ticker-title/);
  });
});

describe("Group By", () => {
  test("the row sits beside the title: default levels in order, Lot fixed last, unused levels offered", () => {
    const out = liveViewHtml(DATA);
    assert.match(out, /<div class="live-card-head"><h2>Liquid investments<\/h2><div class="group-by" role="group" aria-label="Group by">/);
    const chips = [...out.matchAll(/<span class="chip-name">([^<]*)<\/span>/g)].map((m) => m[1]);
    assert.deepEqual(chips, ["Sub-class", "Symbol", "Account"]);
    assert.match(out, /<span class="chip fixed" data-dim="lot" title="Lots are always the last level">Lot<\/span>/);
    assert.match(out, /<button type="button" class="chip off" draggable="true" data-dim="class"[^>]*>\+ Asset class<\/button>/);
  });
  test("each chip can be dragged, and moved with arrows; the ends' arrows are disabled", () => {
    const out = liveViewHtml(DATA);
    assert.equal((out.match(/<span class="chip" draggable="true"/g) || []).length, 3);
    assert.match(out, /data-dim="subclass" data-step="-1" aria-label="Move Sub-class earlier" disabled>/);
    assert.match(out, /data-dim="account" data-step="1" aria-label="Move Account later" disabled>/);
    assert.doesNotMatch(out, /data-dim="symbol" data-step="-1"[^>]*disabled/);
    assert.match(out, /aria-label="Stop grouping by Symbol"/);
  });
  test("the order reshapes the table: first level names the column, rows regroup", () => {
    const out = liveViewHtml({ ...DATA_WITH_LOTS, account_labels: { Member_1_IRA: "Matt IRA" } }, ["account", "symbol"]);
    assert.match(out, /<th scope="col">Account<\/th>/);
    assert.match(out, /<tr class="top-row" data-depth="0" data-path="\/Member_1_IRA"><th scope="row" class="dim-account"><button[^>]*>▸ Matt IRA<\/button>/);
    assert.match(out, /<tr data-depth="1" data-path="\/Member_1_IRA\/ITOT" data-parent="\/Member_1_IRA" hidden>/);
    const chips = [...out.matchAll(/<span class="chip-name">([^<]*)<\/span>/g)].map((m) => m[1]);
    assert.deepEqual(chips, ["Account", "Symbol"]);
  });
  test("an unreadable order falls back to the default", () => {
    assert.match(liveViewHtml(DATA, "garbage"), /<th scope="col">Sub-class<\/th>/);
  });
});

describe("friendly account labels", () => {
  const labels = { Member_1_IRA: "Matt IRA" };
  test("account rows show the label; paths keep the account id", () => {
    const out = liveViewHtml({ ...DATA_WITH_LOTS, account_labels: labels });
    assert.match(out, /data-path="\/US%20Total%20Equity\/ITOT\/Member_1_IRA" data-label="Matt IRA">▸ Matt IRA<\/button>/);
    assert.ok(!/>▸ Member_1_IRA</.test(out));
  });
  test("reconciliation accounts sort A to Z by the name shown", () => {
    const a = (id, extra = {}) => ({ ...REC.accounts[0], holdings_account: id, ...extra });
    const rec = { ...REC, accounts: [a("c_id", { flag: true, delta: 99999 }), a("a_id"), a("b_id")] };
    const out = liveViewHtml({ ...DATA, account_labels: { c_id: "Apple", a_id: "cherry", b_id: "Banana" }, reconciliation: rec });
    const order = [...out.matchAll(/<tr class="[^"]*"><th scope="row">(?:<span class="flag"[^>]*>.*?<\/span> )?(Apple|Banana|cherry)/g)].map((m) => m[1]);
    assert.deepEqual(order, ["Apple", "Banana", "cherry"]);
  });
  test("reconciliation rows and unmapped holdings show the label", () => {
    const rec = { ...REC_FLAGGED, unmapped_holdings: [{ account: "Member_1_IRA", value: 1 }] };
    const out = liveViewHtml({ ...DATA, account_labels: labels, reconciliation: rec });
    const recon = out.match(/<details class="live-section recon-accounts">[\s\S]*?<\/details>/)[0];   // paths elsewhere keep the id
    assert.ok(!recon.includes("Member_1_IRA"));
    assert.match(recon, /Matt IRA/);
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

describe("Group By wiring", () => {
  const SAVED = "trendsLiveGroups_v1";
  function harness({ saved, blocked } = {}) {
    const listeners = {}, store = new Map([["trendsView_v1", "live"], ...(saved ? [[SAVED, saved]] : [])]);
    const el = () => ({ innerHTML: "", textContent: "", hidden: false, classList: { toggle() {}, contains: () => false, add() {}, remove() {} },
                        addEventListener() {}, querySelectorAll: () => [], querySelector: () => null, setAttribute() {} });
    const out = { ...el(), addEventListener: (type, fn) => { (listeners[type] ||= []).push(fn); } };
    const els = { liveView: el(), liveBody: out, liveError: el(), liveRefresh: el() };
    const doc = { body: el(), getElementById: (id) => els[id], querySelectorAll: () => [], addEventListener() {}, visibilityState: "visible" };
    const win = {
      localStorage: { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => { if (blocked) throw new Error("blocked"); store.set(k, v); } },
      setInterval() {}, fetch: async () => ({ ok: true, json: async () => DATA_WITH_LOTS }),
    };
    return { listeners, store, out, doc, win, fire: (type, e) => (listeners[type] || []).forEach((fn) => fn(e)) };
  }
  const started = async (h) => { initLiveView(h.doc, h.win); await new Promise((r) => setTimeout(r, 20)); return h; };
  const target = (map) => ({ closest: (sel) => map[sel] ?? null });
  const saved = (h) => JSON.parse(h.store.get(SAVED));
  const firstColumn = (h) => h.out.innerHTML.match(/<thead><tr><th scope="col">([^<]*)<\/th>/)[1];

  test("a saved order is restored; an unreadable one means the default", async () => {
    assert.equal(firstColumn(await started(harness({ saved: JSON.stringify(["account", "symbol"]) }))), "Account");
    assert.equal(firstColumn(await started(harness({ saved: "not json" }))), "Sub-class");
    assert.equal(firstColumn(await started(harness())), "Sub-class");
  });
  test("an arrow moves a chip, redraws the table and remembers the order", async () => {
    const h = await started(harness());
    h.fire("click", { target: target({ "button.chip-step": { dataset: { dim: "subclass", step: "1" } } }) });
    assert.deepEqual(saved(h), ["symbol", "subclass", "account"]);
    assert.equal(firstColumn(h), "Symbol");
  });
  test("x drops a level, and an unused chip adds one before Lot", async () => {
    const h = await started(harness());
    h.fire("click", { target: target({ "button.chip-remove": { dataset: { dim: "symbol" } } }) });
    assert.deepEqual(saved(h), ["subclass", "account"]);
    h.fire("click", { target: target({ "button.chip.off": { dataset: { dim: "class" } } }) });
    assert.deepEqual(saved(h), ["subclass", "account", "class"]);
  });
  test("dragging a chip onto the left half of another puts it before; the right half, after", async () => {
    const h = await started(harness());
    const chip = (dim) => ({ dataset: { dim }, classList: { contains: () => false, add() {}, remove() {} }, getBoundingClientRect: () => ({ left: 0, width: 100 }) });
    const drag = (from, onto, clientX) => {
      h.fire("dragstart", { target: target({ ".group-by .chip[data-dim]": chip(from) }), dataTransfer: { setData() {} } });
      h.fire("drop", { target: target({ ".group-by .chip[data-dim]": chip(onto) }), clientX, preventDefault() {} });
    };
    drag("account", "subclass", 10);
    assert.deepEqual(saved(h), ["account", "subclass", "symbol"]);
    drag("account", "symbol", 90);
    assert.deepEqual(saved(h), ["subclass", "symbol", "account"]);
  });
  test("the Lot chip cannot be dragged, and a drop with nothing being dragged does nothing", async () => {
    const h = await started(harness());
    const lot = { dataset: { dim: "lot" }, classList: { contains: (c) => c === "fixed", add() {} } };
    h.fire("dragstart", { target: target({ ".group-by .chip[data-dim]": lot }), dataTransfer: { setData() {} } });
    h.fire("drop", { target: target({ ".group-by .chip[data-dim]": { dataset: { dim: "symbol" }, getBoundingClientRect: () => ({ left: 0, width: 10 }) } }), clientX: 1, preventDefault() {} });
    assert.equal(h.store.has(SAVED), false);
  });
  test("blocked storage never breaks regrouping", async () => {
    const h = await started(harness({ blocked: true }));
    h.fire("click", { target: target({ "button.chip-step": { dataset: { dim: "subclass", step: "1" } } }) });
    assert.equal(firstColumn(h), "Symbol");
  });
  test("a sort pick redraws the table, remembers the choice", async () => {
    const SORT = "trendsLiveSort_v1";
    const h = await started(harness());
    assert.match(h.out.innerHTML, /<option value="name" selected>Name<\/option>/);
    assert.match(h.out.innerHTML, /<option value="asc" selected>Ascending<\/option>/);
    h.fire("change", { target: { closest: (sel) => (sel === "#liveSortField" ? { value: "current" } : null) } });
    h.fire("change", { target: { closest: (sel) => (sel === "#liveSortDir" ? { value: "desc" } : null) } });
    assert.deepEqual(JSON.parse(h.store.get(SORT)), { field: "current", dir: "desc" });
    assert.match(h.out.innerHTML, /<option value="current" selected>Current<\/option>/);
    assert.match(h.out.innerHTML, /<option value="desc" selected>Descending<\/option>/);
    h.fire("change", { target: { closest: () => null } });   // some other control: nothing happens
    assert.deepEqual(JSON.parse(h.store.get(SORT)), { field: "current", dir: "desc" });
  });
  test("a new grouping drops the old expanded rows", async () => {
    const h = await started(harness());
    const rows = [{ dataset: { path: "/US%20Total%20Equity" } }];
    h.out.querySelectorAll = (sel) => (sel === "button.expand" ? rows.map((r) => ({ ...r, getAttribute: () => "false", setAttribute() {}, textContent: "" })) : []);
    h.fire("click", { target: target({ "button.expand": { dataset: { path: "/US%20Total%20Equity" }, getAttribute: () => "false" } }) });
    h.fire("click", { target: target({ "button.chip-step": { dataset: { dim: "subclass", step: "1" } } }) });
    assert.match(h.out.innerHTML, /data-path="\/ITOT"/);   // symbol is now the top level
  });
});

describe("Sort by", () => {
  test("sits after the Group By row as two picklists, field then direction", () => {
    const out = liveViewHtml(DATA_WITH_LOTS);
    assert.match(out, /class="group-by"[\s\S]*<div class="sort-by" role="group" aria-label="Sort by">/);
    assert.match(out, /<select id="liveSortField"[^>]*>(<option[^>]*>[^<]*<\/option>)+<\/select><select id="liveSortDir"/);
  });
  test("the picked sort orders the rows", () => {
    const names = (out) => [...out.matchAll(/class="dim-subclass"><button[^>]*>▸ ([^<]*)<\/button>/g)].map((m) => m[1]);
    const asc = names(liveViewHtml(DATA_WITH_LOTS, undefined, { field: "name", dir: "asc" }));
    const desc = names(liveViewHtml(DATA_WITH_LOTS, undefined, { field: "name", dir: "desc" }));
    assert.ok(asc.length > 0);
    assert.deepEqual(desc, [...asc].reverse());
  });
  test("is set apart from Group By", () => {
    assert.match(html, /\.sort-by \{[^}]*margin-left: 20px/);
  });
});

describe("Group By styles", () => {
  test("rows indent by depth and the chips have drag cues", () => {
    for (const d of [1, 2, 3, 4]) assert.match(html, new RegExp(String.raw`\.live-table tr\[data-depth="${d}"\] th \{`));
    assert.match(html, /\.group-by \.chip\.drop-before \{ box-shadow/);
    assert.match(html, /\.group-by \.chip\.drop-after \{ box-shadow/);
    assert.doesNotMatch(html, /\.ticker-row th|\.acct-row th|\.lot-row th/);
  });
});

describe("sold positions note (sales ledger 4.1)", () => {
  const live = (liquid) => liveViewHtml({ ...DATA, liquid: { ...DATA.liquid, ...liquid } });
  test("the old not-included caveat is gone", () => {
    const out = live({});
    assert.ok(!out.includes("are not included"));
    assert.ok(!out.includes("Gains on positions sold"));
  });
  test("says how many positions were sold since the start, with no dollars", () => {
    const out = live({ sold: { count: 2 }, unconfirmed_sales: { count: 0 } });
    assert.match(out, /Includes 2 positions sold since /);
    assert.ok(!out.includes("not yet confirmed"));
  });
  test("unconfirmed sales are a count only", () => {
    const out = live({ sold: { count: 1 }, unconfirmed_sales: { count: 3 } });
    assert.match(out, /Includes 1 position sold since /);
    assert.match(out, /3 sales not yet confirmed are not included\./);
  });
});

describe("sold lot labels (sales ledger 4.2)", () => {
  test("no shares or price on a sold lot or its Cash counterpart", () => {
    assert.equal(lotLabel(POS({ sold: true, shares: 0, purchase_date: "2025-06-01" })), "2025-06-01 · sold");
    assert.equal(lotLabel(POS({ sold: true, symbol: "CASH", shares: 0 })), "Sale proceeds");
    assert.match(lotLabel(POS()), /120 @ /);
  });
  test("a sold position shows as a (sold) group in the page", () => {
    const out = liveViewHtml({ ...DATA, liquid: { ...DATA.liquid, positions: [POS(), POS({ symbol: "AVUV", sold: true, shares: 0, start: 4500, new_money: -5500, weighted: -550, current: 0, day: null })] } }, ["symbol", "lot"]);
    assert.ok(out.includes("AVUV (sold)"));
  });
});

