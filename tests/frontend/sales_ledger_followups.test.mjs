// Sales Ledger follow-ups (2026-11-04): carryforward draft, All years, countless-alert signature, strip items, landing fallbacks.
import { test, describe, before, beforeEach } from "node:test";
import assert from "node:assert/strict";

let ui, tax, tr, ye, tl;
const calls = [];
const els = {};
const mkEl = (id) => ({ id, value: "", disabled: false, attrs: {}, setAttribute(k, v) { this.attrs[k] = v; }, parentNode: { classList: { toggle() {} } } });
const store = () => { let v = null; return { getItem: () => v, setItem: (_k, x) => { v = x; } }; };
const WASH = (o = {}) => ({ count: 0, all_years_count: 0, flagged_loss: 0, rows: [], ...o });
const SUMMARY = (o = {}) => ({ success: true, year: 2026, filing: "MFJ", limit: 3000,
  netting: { net_st: 0, net_lt: 0, ordinary_offset: 0, carryforward_st: 0, carryforward_lt: 0, gain_to_tax_ordinary: 0, gain_to_tax_ltcg: 0 },
  carryforward_in: { short: 0, long: 5000, entered: false }, carryforward_out: { short: 0, long: 0 }, totals: { count: 1, st_gain: 0, lt_gain: 0 }, wash: WASH(), ...o });
const defaultApi = async (url) => {
  calls.push(url);
  if (url.startsWith("/api/sales/tax-year")) return SUMMARY();
  if (url === "/api/year-end") return { year: 2026, steps: [{ state: "open" }] };
  return { success: true };
};

before(async () => {
  globalThis.esc = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  globalThis.window = globalThis;
  globalThis.localStorage = store();
  globalThis.document = { getElementById: (id) => els[id] || null };
  globalThis.api = defaultApi;
  ui = await import("../../frontend/js/dashboard_decomp_sales_ledger_ui.js");
  tax = await import("../../frontend/js/dashboard_decomp_sales_tax.js");
  tr = await import("../../frontend/js/dashboard_decomp_transactions.js");
  ye = await import("../../frontend/js/dashboard_decomp_year_end.js");
  tl = await import("../../frontend/js/dashboard_decomp_transactions_log.js");
});
beforeEach(() => {
  calls.length = 0;
  for (const k of Object.keys(els)) delete els[k];
  globalThis.localStorage = store();
  globalThis.api = defaultApi;
});

describe("1 carryforward draft", () => {
  test("typed values survive a reload/repaint and clear after a save", async () => {
    await tax.loadSalesTaxYear(2026);
    tax.stCfDraftSet("stCfShort", "123");
    const html = tax.stCarryforwardHtml(SUMMARY());
    assert.match(html, /id="stCfShort"[^>]*value="123"/);
    assert.match(html, /id="stCfLong"[^>]*value="5000"/);
    await tax.loadSalesTaxYear(2026);
    assert.match(tax.stCarryforwardHtml(SUMMARY()), /value="123"/);
    await tax.stSaveCarryforward();
    assert.match(tax.stCarryforwardHtml(SUMMARY()), /id="stCfShort"[^>]*value="0"/);
  });
  test("a draft for another year is ignored", async () => {
    await tax.loadSalesTaxYear(2026);
    tax.stCfDraftSet("stCfShort", "9");
    assert.doesNotMatch(tax.stCarryforwardHtml(SUMMARY({ year: 2025 })), /value="9"/);
  });
});

describe("2 header controls and All years", () => {
  test("Taxable accounts only is locked on in Tax year, with a reason; Year stays live", () => {
    for (const [tab, off] of [["fix", false], ["ledger", false], ["tax", true]]) {
      const st = ui.slHeadControlState(tab);
      assert.equal(st.disabled, off, tab);
      assert.equal(!!st.title, off, tab);
    }
    els.slYear = mkEl("slYear"); els.slTaxableBox = mkEl("slTaxableBox");
    ui.slSetTab("tax");
    assert.equal(els.slTaxableBox.disabled, true);
    assert.match(els.slTaxableBox.attrs.title, /taxable accounts only/i);
    assert.equal(els.slYear.disabled, false);
    ui.slSetTab("ledger");
    assert.equal(els.slTaxableBox.disabled, false);
  });
  test("All years on the Tax tab says to pick a year and shows no totals", async () => {
    globalThis.slCurrentYear = () => "";
    try {
      assert.match(tax.renderSalesTaxYear(), /Pick a year/);
      assert.doesNotMatch(tax.renderSalesTaxYear(), /Tax year 2026/);
    } finally { delete globalThis.slCurrentYear; }
    await tax.loadSalesTaxYear(2026);
    assert.match(tax.renderSalesTaxYear(), /Tax year 2026/);
  });
});

describe("3 countless alerts get a signature", () => {
  const stale = { count: 0, tone: "warn", text: "stale" };
  test("signature is nonzero, stable and differs by alert", () => {
    const a = ui.slAlertCountOf(stale);
    assert.ok(a < 0);
    assert.equal(a, ui.slAlertCountOf({ ...stale }));
    assert.notEqual(a, ui.slAlertCountOf({ count: 0, tone: "warn", text: "never run" }));
    assert.equal(ui.slAlertCountOf({ count: 0, tone: "", text: "" }), 0);
    assert.equal(ui.slAlertCountOf({ count: 3, tone: "bad", text: "x" }), 3);
  });
  test("a collapsed section re-opens when a countless alert first appears or changes, not when unchanged", () => {
    const a = ui.slAlertCountOf(stale), b = ui.slAlertCountOf({ count: 0, tone: "warn", text: "never run" });
    const collapsed = ui.slUiRecordToggle({ tab: "tax", sections: {}, density: "" }, "wash", false, 0);
    assert.equal(ui.slSecWantOpen(collapsed, "wash", a), true);
    const seen = ui.slUiRecordToggle(collapsed, "wash", false, a);
    assert.equal(ui.slSecWantOpen(seen, "wash", a), false);
    assert.equal(ui.slSecWantOpen(seen, "wash", b), true);
  });
  test("a cleared alert is forgotten so its return re-opens a collapsed section", () => {
    const sec = { open: true, querySelector: () => null };
    els["sl-sec-wash"] = sec;
    ui.slPublish("cf", { count: 0, tone: "", text: "" }); // earlier tests may have published a carryforward alert
    ui.slPublish("wash", { count: 0, tone: "warn", text: "stale" });
    sec.open = false;
    ui.slUiSave(ui.slUiRecordToggle(ui.slUiLoad(), "wash", false, ui.slAlertCountOf({ count: 0, tone: "warn", text: "stale" })));
    ui.slPublish("wash", { count: 0, tone: "", text: "" });
    assert.equal(ui.slUiLoad().sections.wash.lastAlertCount, 0);
    ui.slPublish("wash", { count: 0, tone: "warn", text: "stale" });
    assert.equal(sec.open, true);
    ui.slPublish("wash", { count: 0, tone: "", text: "" });
  });
});

describe("4/5 strip counts and items", () => {
  test("wash count in the strip is the all-years count", async () => {
    globalThis.api = async (url) => (url.startsWith("/api/sales/tax-year") ? SUMMARY({ wash: WASH({ count: 0, all_years_count: 2 }) }) : { steps: [] });
    await tax.loadSalesTaxYear(2026);
    assert.deepEqual(tax.stSummary().wash, { count: 2, tone: "bad", text: "2 flagged" });
    globalThis.api = async (url) => (url.startsWith("/api/sales/tax-year") ? SUMMARY({ wash: { count: 1, flagged_loss: 1, rows: [] } }) : { steps: [] });
    await tax.loadSalesTaxYear(2026);
    assert.equal(tax.stSummary().wash.count, 1);
  });
  test("carryforward warns only when a figure is carried in and never entered", async () => {
    const run = async (cf) => {
      globalThis.api = async (url) => (url.startsWith("/api/sales/tax-year") ? SUMMARY({ carryforward_in: cf }) : { steps: [] });
      await tax.loadSalesTaxYear(2026);
      return tax.stSummary().cf;
    };
    assert.equal((await run({ short: 0, long: 0, entered: false })).tone, "");
    assert.equal((await run({ short: 0, long: 100, entered: true })).tone, "");
    assert.deepEqual(await run({ short: 5, long: 0, entered: false }), { count: 0, tone: "warn", text: "carryforward not saved" });
  });
});

describe("6 strip links land somewhere", () => {
  test("cf lands in (and opens) the wash section", () => {
    const sec = { open: false, querySelector: () => null };
    els["sl-sec-wash"] = sec;
    globalThis.history = { replaceState() {} };
    ui.slGo("tax", "cf");
    assert.equal(sec.open, true);
  });
  test("log not started focuses the bare Start prompt", () => {
    let focused = 0;
    els.tlStartBtn = { focus() { focused++; }, scrollIntoView() {} };
    globalThis.history = { replaceState() {} };
    ui.slGo("fix", "health");
    assert.equal(focused, 1);
  });
});

describe("7 year-end is fetched lazily", () => {
  test("not fetched while another tab shows; fetched once when the Tax tab is shown", async () => {
    ui.slSetCurrentTab("fix");
    calls.length = 0;
    await tax.loadSalesTaxYear(2026);
    assert.ok(!calls.includes("/api/year-end"));
    ui.slSetTab("tax");
    await tax.stOnShown();
    assert.equal(calls.filter((c) => c === "/api/year-end").length, 1);
    await tax.stOnShown();
    assert.equal(calls.filter((c) => c === "/api/year-end").length, 1);
    await tax.loadSalesTaxYear(2026);
    assert.equal(calls.filter((c) => c === "/api/year-end").length, 2);
  });
});

describe("9 smaller items", () => {
  test("tab badge has screen-reader text", () => {
    const h = ui.slTabBarHtml("fix", { fix: { count: 2, tone: "warn" }, tax: { count: 1, tone: "warn" } });
    assert.match(h, /<span aria-hidden="true">2<\/span><span class="sr-only">2 items need attention<\/span>/);
    assert.match(h, /1 item needs attention/);
  });
  test("next-step paragraph is not a live region", () => {
    ui.slPublish("queue", { count: 0, tone: "", text: "" });
    assert.doesNotMatch(ui.slNextStepHtml({ wash: true }), /role="status"/);
  });
  test("trLoad returns the error with its view", async () => {
    globalThis.api = async () => { throw new Error("boom"); };
    const v = await tr.trLoad({});
    assert.equal(v.error, "boom");
    assert.match(tr.trHtml(v), /boom/);
    globalThis.api = async () => ({ rows: [], held: [] });
    const ok = await tr.trLoad({});
    assert.equal(ok.error, "");
    assert.doesNotMatch(tr.trHtml(ok), /boom/);
    assert.match(tr.trHtml(v), /boom/);
  });
  test("a failed log load publishes neutral, not 'log not started'", async () => {
    globalThis.api = async () => { throw new Error("net"); };
    await tl.tlLoad();
    assert.equal(tl.tlSummary().health.text, "");
    globalThis.api = async () => ({ started: false, rows: [], open: [], drift: [] });
    await tl.tlLoad();
    assert.equal(tl.tlSummary().health.text, "log not started");
  });
  test("yeGo replaces the history entry instead of adding one", () => {
    let pushed = 0, replaced = null, step = null;
    globalThis.location = { get hash() { return ""; }, set hash(v) { pushed++; } };
    globalThis.history = { replaceState(_a, _b, u) { replaced = u; } };
    globalThis.setStep = (s) => { step = s; };
    ye.yeGo("sales_ledger", "#sales_ledger?tab=tax");
    assert.equal(pushed, 0);
    assert.equal(replaced, "#sales_ledger?tab=tax");
    assert.equal(step, "sales_ledger");
    delete globalThis.location; delete globalThis.history;
  });
  test("Undo confirmation for tie_1099b shows only while the tie count is unknown", () => {
    const step = (o) => ({ steps: [{ id: "tie_1099b", title: "t", link: "sales_ledger", hash: "#x", detail: "d", ...o }], year: 2026 });
    assert.match(ye.yeHtml(step({ state: "done", count_known: false })), /Undo confirmation/);
    assert.doesNotMatch(ye.yeHtml(step({ state: "done", count_known: true })), /Undo confirmation/);
    assert.match(ye.yeHtml(step({ state: "open", count_known: false })), /I have tied each 1099-B/);
  });
});
