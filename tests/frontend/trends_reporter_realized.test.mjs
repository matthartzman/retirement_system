// Realized gains and losses view (sales ledger 4.3): render, percent handling and the tab wiring.
import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { realizedViewHtml, realizedQuery, initRealized, DEFAULT_STATE } from "../../financial_trends_reporter/frontend/realized.js";
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

describe("realizedQuery", () => {
  test("uses the scope's first day unless a tax year is picked", () => {
    assert.equal(realizedQuery(DEFAULT_STATE, "2026-01-01"), "from=2026-01-01&group=symbol");
    assert.equal(realizedQuery({ ...DEFAULT_STATE, taxYear: "2025" }, "2026-01-01"), "tax_year=2025&group=symbol");
    assert.equal(realizedQuery({ ...DEFAULT_STATE, group: "account", taxable: true, wash: true, unconfirmed: true }, ""),
      "group=account&taxable=1&wash=1&unconfirmed=1");
    assert.equal(realizedQuery({ ...DEFAULT_STATE, group: "bogus" }, ""), "group=symbol");
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
