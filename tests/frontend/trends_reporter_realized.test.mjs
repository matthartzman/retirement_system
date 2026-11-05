// Realized gains and losses view (sales ledger 4.3): render, percent handling and the tab wiring.
import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { realizedViewHtml, realizedQuery, initRealized, DEFAULT_STATE, sortNodes, normalizeLevels, stepLevel, toggleLevel } from "../../financial_trends_reporter/frontend/realized.js";
import { setMoneyView } from "../../financial_trends_reporter/frontend/money_view.js";

const LOT = (o = {}) => ({ sale_id: 1, symbol: "ITOT", account: "Member_1_Trust", sale_date: "2026-03-10", purchase_date: "2025-01-01", shares: 10,
  proceeds: 5500, basis: 4000, gain: 1500, term: "long", source: "manual", wash_flag: "none", status_1099: "none", estimate: false, ...o });
const GROUP = (name, lots) => ({ name, count: lots.length, proceeds: lots.reduce((s, l) => s + l.proceeds, 0), basis: lots.reduce((s, l) => s + l.basis, 0),
  net: lots.reduce((s, l) => s + l.gain, 0), lots });
const SUMMARY = { count: 2, proceeds: 7500, basis: 6600, st_gain: -600, lt_gain: 1500, unknown_gain: 0, net: 900, wash_flagged: -600, basis_missing: 0 };
const DATA = {
  window: { from: "2026-01-01", to: "2026-10-27", tax_year: null }, group_by: "symbol", years: [2026, 2025],
  filters: {}, summary: SUMMARY, unconfirmed: { count: 0, not_estimated: null }, estimate: null,
  groups: [GROUP("ITOT", [LOT()]), GROUP("AVUV", [LOT({ sale_id: 2, symbol: "AVUV", proceeds: 2000, basis: 2600, gain: -600, term: "short", wash_flag: "possible", status_1099: "differs" })])],
};
const back = () => setMoneyView({ allowed: "both", shown: "dollars", scale: 1 });

describe("realizedViewHtml in dollars", () => {
  test("shows the summary, groups and lots", () => {
    const out = realizedViewHtml(DATA);
    assert.match(out, /Since 2026-01-01/);
    for (const text of ["Short-term", "Long-term", "Net", "Proceeds", "Basis", "Wash-flagged", "ITOT", "AVUV", "2026-03-10 · bought 2025-01-01", "Long", "Short", "Differs", "wash"]) {
      assert.ok(out.includes(text), text);
    }
    assert.match(out, /\$1,500/);
    assert.match(out, /37\.5%/);                           // 1500 / 4000 return on basis
  });
  test("a tax year, an empty period, an error and loading", () => {
    assert.match(realizedViewHtml({ ...DATA, window: { ...DATA.window, tax_year: 2025 } }), /Tax year 2025/);
    assert.match(realizedViewHtml({ ...DATA, summary: { ...SUMMARY, count: 0 }, groups: [] }), /No confirmed sales in this period/);
    assert.match(realizedViewHtml({ error: "boom <b>" }), /unavailable: boom &lt;b&gt;/);
    assert.match(realizedViewHtml(null), /Loading/);
  });
  test("text from the data is escaped", () => {
    const out = realizedViewHtml({ ...DATA, groups: [GROUP("<img src=x>", [LOT({ symbol: "<img src=x>" })])] });
    assert.ok(!out.includes("<img src=x>"));
  });
  test("waiting sales are a chip and a count, with no dollars of their own", () => {
    const out = realizedViewHtml({ ...DATA, unconfirmed: { count: 3, not_estimated: null } });
    assert.match(out, /3 sales waiting for lots/);
    assert.match(realizedViewHtml({ ...DATA, unconfirmed: { count: 1, not_estimated: null } }), /1 sale waiting for lots/);
    assert.doesNotMatch(realizedViewHtml(DATA), /waiting for lots/);
  });
  test("the estimate is its own labelled section, apart from the confirmed totals", () => {
    const est = { ...SUMMARY, count: 1, net: 220, groups: [GROUP("ITOT", [LOT({ estimate: true, gain: 220, source: "monarch" })])] };
    const out = realizedViewHtml({ ...DATA, unconfirmed: { count: 3, not_estimated: 2 }, estimate: est });
    assert.match(out, /Estimate for sales not yet confirmed/);
    assert.match(out, /never used for tax, the projection or the daily log/);
    assert.match(out, /2 sales could not be estimated/);
    assert.match(out, /estimate<\/td>/);
    assert.doesNotMatch(realizedViewHtml(DATA), /Estimate for sales/);
  });
});

describe("realizedViewHtml for a percent-only person", () => {
  test("groups arrive without lots and still render, with returns only", () => {
    setMoneyView({ allowed: "percent", shown: "percent", scale: 100000 });
    try {
      const groups = DATA.groups.map(({ lots, ...g }) => g);
      const out = realizedViewHtml({ ...DATA, groups, estimate: null });
      assert.match(out, /ITOT/);
      assert.match(out, /37\.5%/);
      assert.doesNotMatch(out, /\$\s?\d|sale-lot/);
    } finally { back(); }
  });
});

describe("realizedViewHtml in the percent view", () => {
  test("only ratios: no dollars, proceeds, basis, gain or share counts", () => {
    setMoneyView({ allowed: "both", shown: "percent", scale: 1000 });
    try {
      const out = realizedViewHtml({ ...DATA, unconfirmed: { count: 2, not_estimated: null } });
      assert.doesNotMatch(out, /\$\s?\d/);
      for (const word of ["Proceeds", "Basis", "Shares", "Short-term"]) assert.ok(!out.includes(word), word);
      assert.match(out, /return on basis 13\.6%/);        // 900 / 6600
      assert.match(out, /37\.5%/);
      assert.ok(!out.includes(">10<"), "no share count cell");
      assert.match(out, /2 sales waiting for lots/);
    } finally { back(); }
  });
});

describe("grouping, sorting and collapsible headings", () => {
  const NODE = (dim, name, label, rest) => ({ dim, name, label, count: 1, proceeds: 100, basis: 80, net: 20, ...rest });
  const NESTED = {
    ...DATA, levels: ["account", "symbol"], group_by: "account",
    groups: [
      NODE("account", "Member_1_Trust", "Matt Trust", { count: 2, proceeds: 7500, basis: 6600, net: 900, children: [
        NODE("symbol", "ITOT", "ITOT", { proceeds: 5500, basis: 4000, net: 1500, lots: [LOT({ account_label: "Matt Trust" })] }),
        NODE("symbol", "AVUV", "AVUV", { proceeds: 2000, basis: 2600, net: -600, lots: [LOT({ sale_id: 2, symbol: "AVUV", gain: -600, account_label: "Matt Trust" })] })] }),
      NODE("account", "Member_1_IRA", "Matt IRA", { proceeds: 1000, basis: 800, net: 200, children: [
        NODE("symbol", "IXUS", "IXUS", { proceeds: 1000, basis: 800, net: 200, lots: [LOT({ sale_id: 3, symbol: "IXUS", account_label: "Matt IRA" })] })] }),
    ],
  };
  const st = (o) => ({ ...DEFAULT_STATE, levels: ["account", "symbol"], ...o });

  test("the Group by and Sort by rows sit in the card head, like Holdings", () => {
    const out = realizedViewHtml(NESTED, st());
    assert.match(out, /<div class="live-card-head"><h2>[\s\S]*class="group-by"[\s\S]*class="sort-by"/);
    assert.match(out, /data-dim="lot"[^>]*>Sale</);
    assert.match(out, /class="chip off" data-dim="term"/);
    assert.match(out, /id="realizedSortField"/);
  });
  test("headings are collapse buttons; only the top rows start visible", () => {
    const out = realizedViewHtml(NESTED, st());
    assert.match(out, /<button type="button" class="expand" aria-expanded="false" data-path="\/Member_1_Trust" data-label="Matt Trust">▸ Matt Trust<\/button>/);
    const rows = out.match(/<tr [^>]*>/g);
    assert.ok(rows.filter((r) => r.includes("top-row")).every((r) => !r.includes("hidden")));
    assert.ok(rows.filter((r) => !r.includes("top-row")).every((r) => r.includes("hidden") && r.includes("data-parent")));
  });
  test("an internal account id is never shown: groups use the label, sale rows add it when Account is not a level", () => {
    const out = realizedViewHtml(NESTED, st());
    assert.match(out, /Matt Trust/);
    assert.doesNotMatch(out.replace(/data-(path|parent)="[^"]*"/g, ""), /Member_1_/);
    const bySymbol = realizedViewHtml({ ...DATA, groups: [NODE("symbol", "ITOT", "ITOT", { lots: [LOT({ account: "Member_1_Trust", account_label: "Matt Trust" })] })] });
    assert.match(bySymbol, /bought 2025-01-01 · Matt Trust/);
    assert.doesNotMatch(bySymbol, /Member_1_/);
  });
  test("sorting orders every level; missing figures go last either way", () => {
    const names = (nodes) => nodes.map((n) => n.name);
    assert.deepEqual(names(sortNodes(NESTED.groups, { field: "name", dir: "asc" })), ["Member_1_IRA", "Member_1_Trust"]);   // Matt IRA, Matt Trust
    assert.deepEqual(names(sortNodes(NESTED.groups, { field: "net", dir: "desc" })), ["Member_1_Trust", "Member_1_IRA"]);
    const kids = NESTED.groups[0].children;
    assert.deepEqual(names(sortNodes(kids, { field: "ret", dir: "desc" })), ["ITOT", "AVUV"]);
    const gap = [{ name: "a", label: "a", net: null, basis: 0 }, { name: "b", label: "b", net: 5, basis: 50 }];
    assert.deepEqual(names(sortNodes(gap, { field: "ret", dir: "asc" })), ["b", "a"]);
    assert.deepEqual(names(sortNodes(gap, { field: "ret", dir: "desc" })), ["b", "a"]);
    const out = realizedViewHtml(NESTED, st({ sort: { field: "net", dir: "desc" } }));
    assert.ok(out.indexOf("Matt Trust") < out.indexOf("Matt IRA"));
  });
  test("terms sort short, long, unknown and read as words", () => {
    const terms = ["unknown", "long", "short"].map((t) => ({ dim: "term", name: t, label: t }));
    assert.deepEqual(sortNodes(terms, { field: "name", dir: "asc" }).map((n) => n.name), ["short", "long", "unknown"]);
  });
  test("level helpers keep the order unique and never empty", () => {
    assert.deepEqual(normalizeLevels(["account", "account", "x"]), ["account"]);
    assert.deepEqual(normalizeLevels([]), ["symbol"]);
    assert.deepEqual(stepLevel(["symbol", "account"], "account", -1), ["account", "symbol"]);
    assert.deepEqual(toggleLevel(["symbol"], "term"), ["symbol", "term"]);
    assert.deepEqual(toggleLevel(["symbol"], "symbol"), ["symbol"]);
  });
  test("a percent-only person still gets collapsible group rows without sale rows", () => {
    setMoneyView({ allowed: "percent", shown: "percent", scale: 100000 });
    try {
      const strip = (n) => { const { lots, ...r } = n; return { ...r, children: n.children && n.children.map(strip) }; };
      const out = realizedViewHtml({ ...NESTED, groups: NESTED.groups.map(strip), estimate: null }, st());
      assert.match(out, /class="expand"[^>]*>▸ Matt Trust/);
      assert.doesNotMatch(out, /sale-lot|\$\s?\d/);
      assert.doesNotMatch(out, /value="proceeds"/);
    } finally { back(); }
  });
});

describe("realizedQuery", () => {
  test("uses the scope's first day unless a tax year is picked", () => {
    assert.equal(realizedQuery(DEFAULT_STATE, "2026-01-01"), "from=2026-01-01&group=symbol");
    assert.equal(realizedQuery({ ...DEFAULT_STATE, taxYear: "2025" }, "2026-01-01"), "tax_year=2025&group=symbol");
    assert.equal(realizedQuery({ ...DEFAULT_STATE, levels: ["account", "term"], taxable: true, wash: true, unconfirmed: true }, ""),
      "group=account%2Cterm&taxable=1&wash=1&unconfirmed=1");
    assert.equal(realizedQuery({ ...DEFAULT_STATE, levels: ["bogus"] }, ""), "group=symbol");
  });
});

describe("initRealized", () => {
  function harness(reply = DATA) {
    const listeners = {}, docListeners = {};
    const el = (extra = {}) => ({ innerHTML: "", hidden: false, attrs: {}, setAttribute(k, v) { this.attrs[k] = v; }, focus() {}, addEventListener() {}, ...extra });
    const out = el({ hidden: true, addEventListener: (type, fn) => { (listeners[type] ||= []).push(fn); } });
    const live = el();
    const tab = (name) => el({ dataset: { liveTab: name }, addEventListener(type, fn) { this.click = fn; } });
    const tabs = [tab("holdings"), tab("realized")];
    const fetched = [];
    const doc = { body: { dataset: { scopeFrom: "2026-01-01" } }, getElementById: (id) => ({ realizedBody: out, liveBody: live }[id] || el({ id })),
                  querySelectorAll: () => tabs, addEventListener: (type, fn) => { (docListeners[type] ||= []).push(fn); } };
    const win = { fetch: async (url) => { fetched.push(url); return { ok: true, json: async () => reply }; }, setTimeout: (fn) => fn() };
    return { out, live, tabs, fetched, doc, win, change: (e) => listeners.change.forEach((fn) => fn(e)), scope: () => docListeners["trends-scope-change"].forEach((fn) => fn()) };
  }
  const settle = () => new Promise((r) => setTimeout(r, 10));

  test("starts on Holdings; the Realized tab loads once with the scope and swaps the bodies", async () => {
    const h = harness();
    initRealized(h.doc, h.win);
    assert.equal(h.live.hidden, false); assert.equal(h.out.hidden, true); assert.deepEqual(h.fetched, []);
    h.tabs[1].click(); await settle();
    assert.deepEqual(h.fetched, ["/api/realized?from=2026-01-01&group=symbol"]);
    assert.equal(h.live.hidden, true); assert.equal(h.out.hidden, false);
    assert.equal(h.tabs[1].attrs["aria-pressed"], "true");
    assert.match(h.out.innerHTML, /ITOT/);
    h.tabs[0].click(); h.tabs[1].click(); await settle();
    assert.equal(h.fetched.length, 1, "no refetch when nothing changed");
  });
  test("a control change refetches with it; a scope change refetches only while shown", async () => {
    const h = harness();
    initRealized(h.doc, h.win);
    h.scope(); await settle();
    assert.equal(h.fetched.length, 0);
    h.tabs[1].click(); await settle();
    h.change({ target: { id: "realizedUnconfirmed", checked: true } }); await settle();
    h.change({ target: { id: "realizedYear", value: "2025" } }); await settle();
    assert.equal(h.fetched.at(-1), "/api/realized?tax_year=2025&group=symbol&unconfirmed=1");
    h.change({ target: { id: "somethingElse" } }); await settle();
    const n = h.fetched.length;
    h.scope(); await settle();
    assert.equal(h.fetched.length, n + 1);
  });
  test("a refused or failed request shows the message", async () => {
    const h = harness({ success: false, error: "Not available in the percent view." });
    h.win.fetch = async () => ({ ok: false, status: 403, json: async () => ({ success: false, error: "Not available in the percent view." }) });
    initRealized(h.doc, h.win);
    h.tabs[1].click(); await settle();
    assert.match(h.out.innerHTML, /Not available in the percent view/);
  });
});
