// Plan step 1.4: the pure HTML helpers and the fetch calls of dashboard_decomp_sales_ledger.js.
import { test, describe, before, after, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { installInAppConfirm, resetInAppConfirm, confirmState } from "./inapp_confirm_stub.mjs";

let m;
const calls = [];
before(async () => {
  globalThis.esc = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  globalThis.window = globalThis;
  globalThis.accountDisplayLabel = (a) => String(a).replace(/^Member_1_/, "Matt's ");
  const fields = {};
  globalThis.__fields = fields;
  const roots = {};
  globalThis.__roots = roots;
  globalThis.document = { getElementById: (id) => (id in fields ? { value: fields[id] } : roots[id] || null) };
  globalThis.api = async (url, opts) => {
    calls.push([url, opts && opts.method, opts && opts.body ? JSON.parse(opts.body) : null]);
    if (url.startsWith("/api/sales?")) return { success: true, sales: [], totals: { count: 0, short_gain: 0, long_gain: 0 } };
    if (url === "/api/sales/import/preview") return { success: true, received: 1, will_write: [{ symbol: "VXUS" }], duplicates: [], errors: [] };
    return { success: true };
  };
  await installInAppConfirm();
  await import("../../frontend/js/dashboard_decomp_sales_ledger_ui.js");
  await import("../../frontend/js/dashboard_decomp_sales_group.js");
  await import("../../frontend/js/dashboard_decomp_sales_entry.js");
  m = await import("../../frontend/js/dashboard_decomp_sales_ledger.js");
});
beforeEach(() => { calls.length = 0; resetInAppConfirm(); });

const SALE = (o) => ({ sale_id: 7, sale_date: "2026-06-10", account: "Trust", symbol: "VTI", shares: 10, proceeds: 2000, fees: 5, basis: 1500,
  gain: 495, holding_period: "long", tax_class: "taxable", status: "confirmed", source: "manual", ...o });

describe("formatting", () => {
  test("money", () => {
    assert.equal(m.slMoney(1234.5), "$1,234.50");
    assert.equal(m.slMoney(-5), "-$5.00");
    assert.equal(m.slMoney(null), "—");
  });
  test("a loss is marked down and a gain up; non-taxable has no gain", () => {
    assert.match(m.slGainHtml(495), /sl-up.*\+\$495\.00/);
    assert.match(m.slGainHtml(-505), /sl-down.*-\$505\.00/);
    assert.equal(m.slGainHtml(null), "—");
  });
});

describe("table", () => {
  const TWO = [SALE({ sale_id: 7, shares: 5, proceeds: 500, basis: 400, gain: 100 }), SALE({ sale_id: 8, shares: 3, proceeds: 330, basis: 300, gain: 30, holding_period: "short" })];
  const first = () => m.slTableHtml(TWO);
  test("one row per sale with lots hidden until expanded", () => {
    const h = first();
    assert.equal((h.match(/class="sl-sale/g) || []).length, 1);
    assert.equal((h.match(/class="sl-lot/g) || []).length, 0);
    assert.match(h, /8<\/td><td class="rc-num">\$830\.00/);                       // shares and proceeds summed
    assert.match(h, /<td>Mixed<\/td>/);                                          // lots of two terms
    m.slToggleSale(0);
    const open = first();
    assert.equal((open.match(/class="sl-lot/g) || []).length, 2);
    assert.match(open, /aria-expanded="true"/);
    m.slToggleSale(0);
  });
  test("sale row menu offers only Send back to queue", () => {
    const row = m.slSaleRowHtml(window.slGroupSales([SALE({ source: "broker" })])[0], 0);
    const menu = row.slice(row.indexOf('class="sl-menu"'));
    assert.match(menu, /slRequeue\(7\)/);
    assert.doesNotMatch(menu, /slEdit|slVoid/);
  });
  test("Back to queue is disabled with a reason for a manual sale", () => {
    const row = m.slSaleRowHtml(window.slGroupSales([SALE({ source: "manual" })])[0], 0);
    assert.match(row, /<button class="btn" type="button" disabled title="a hand-recorded sale has no queue entry">Send back to queue/);
    assert.doesNotMatch(row, /slRequeue/);
  });
  test("lot row menu offers Edit and Void; Edit is disabled with a reason for a queue or log-linked lot", () => {
    const manual = m.slLotRowHtml(SALE({ source: "manual" }));
    assert.match(manual, /slEdit\(7\)[^]*slVoid\(7\)/);
    const queued = m.slLotRowHtml(SALE({ source: "broker" }));
    assert.match(queued, /disabled title="came from the queue[^"]*">Edit/);
    assert.match(queued, /slVoid\(7\)/);
    assert.match(m.slLotRowHtml(SALE({ source: "manual", lot_key: '{"log_sell":3,"txn_lot":2}' })), /disabled title="linked to the transaction log/);
    assert.match(m.slLotRowHtml(SALE({ status: "voided" })), /slUnvoid\(7\)/);
    assert.match(m.slLotRowHtml(SALE({ status: "voided" })), /sl-voided/);
  });
  test("a non-taxable gain shows a dash with a not-taxable tooltip; user text is escaped", () => {
    assert.match(m.slLotRowHtml(SALE({ gain: null })), /<span title="not taxable">—<\/span>/);
    assert.doesNotMatch(m.slSaleRowHtml(window.slGroupSales([SALE({ account: "<img onerror=x>" })])[0], 0), /<img/);
  });
  test("empty ledger says so", () => {
    assert.match(m.slTableHtml([]), /No sales recorded/);
  });
  test("KPI strip uses the summary endpoint values", () => {
    const h = m.slKpiHtml({ sales: 12, count: 20, st_gain: -505, lt_gain: 495, fees: 12.5 });
    assert.match(h, /<strong>12<\/strong> sales/);
    assert.match(h, /short-term realized .*-\$505\.00/);
    assert.match(h, /long-term realized .*\+\$495\.00/);
    assert.match(h, /fees \$12\.50/);
    assert.equal(m.slKpiHtml(null), "");
  });
});

describe("actions", () => {
  test("void and restore post to the sale", async () => {
    await m.slVoid(7);
    await m.slUnvoid(7);
    assert.deepEqual(calls.filter((c) => c[1] === "POST").map((c) => c[0]), ["/api/sales/7/void", "/api/sales/7/unvoid"]);
  });
});

describe("tax-year panel hook", () => {
  test("the page mounts the panel when it is loaded and reloads it with the ledger", async () => {
    let loaded = null;
    globalThis.renderSalesTaxYear = () => '<div id="stRoot">panel</div>';
    globalThis.loadSalesTaxYear = (y) => { loaded = y; };
    try {
      assert.match(m.renderSalesLedger(), /id="stRoot"/);
      await m.loadSalesLedger();
      assert.equal(loaded, String(new Date().getFullYear()));
    } finally {
      delete globalThis.renderSalesTaxYear;
      delete globalThis.loadSalesTaxYear;
    }
  });
});

describe("scoped repaint keeps the entry card", () => {
  beforeEach(() => {
    for (const id of ["slHeadRoot", "slListRoot", "seCard"]) globalThis.__roots[id] = { writes: 0, _h: "", get innerHTML() { return this._h; }, set innerHTML(v) { this.writes++; this._h = v; } };
  });
  test("a ledger load repaints the list and head, never the entry card", async () => {
    await m.loadSalesLedger();
    const r = globalThis.__roots;
    assert.ok(r.slListRoot.writes >= 1);
    assert.equal(r.seCard.writes, 0);
  });
  test("changing the year does not rewrite the entry card", async () => {
    await m.slSetYear("2025");
    assert.equal(globalThis.__roots.seCard.writes, 0);
    await m.slSetYear(String(new Date().getFullYear()));
  });
  test("Edit hands the lot row to the entry grid; a save reloads with a message", async () => {
    await m.loadSalesLedger();
    let got = null;
    globalThis.seEdit = (sale) => { got = sale; };
    try {
      m.slEdit(7);
      assert.equal(got, null);                                   // not in the (empty) ledger
    } finally { delete globalThis.seEdit; }
    calls.length = 0;
    await m.slAfterEntry("Recorded 2 sales.");
    assert.ok(calls.some((c) => c[0].startsWith("/api/sales?")));
  });
  test("header says Year with an All years option, the Taxable switch and a Voided rows link; ids appear once", () => {
    const html = m.renderSalesLedger();
    assert.match(html, /<label>Year <select id="slYear"/);
    assert.doesNotMatch(html, /Sale year|Density|Show voided/);
    assert.match(html, /<select id="slYear"[^>]*>\s*<option value="" ?[^>]*>All years/);
    assert.match(html, /id="slTaxableBox"\s+checked\s/);
    assert.match(html, /id="slVoidedLink"[^>]*>Voided rows \(\d+\)</);
    for (const id of ["slYear", "slTaxableBox", "seCard"]) assert.equal(html.split(`id="${id}"`).length - 1, 1, id);
  });
  test("year options list only years returned by the server plus All years", () => {
    const h = m.slYearOptionsHtml([2024, 2026], "2026");
    assert.deepEqual([...h.matchAll(/<option value="(\d*)"/g)].map((x) => x[1]), ["", "2026", "2024"]);
    assert.match(h, /<option value="2026" selected>/);
    assert.doesNotMatch(h, /2027|2025/);
    assert.match(m.slYearOptionsHtml([], ""), /^<option value="" selected>All years<\/option>$/);
  });
  test("Taxable accounts only defaults on and persists through slSetTaxableOnly", async () => {
    const mem = {}; const prev = globalThis.localStorage;
    globalThis.localStorage = { getItem: (k) => mem[k] ?? null, setItem: (k, v) => { mem[k] = v; } };
    try {
      assert.equal(m.slTaxableOnly(), true);
      await m.slSetTaxableOnly(false);
      assert.equal(m.slTaxableOnly(), false);
      assert.doesNotMatch(m.renderSalesLedger(), /id="slTaxableBox"\s+checked\s/);
      await m.slSetTaxableOnly(true);
      assert.equal(m.slTaxableOnly(), true);
    } finally { if (prev === undefined) delete globalThis.localStorage; else globalThis.localStorage = prev; }
  });
  test("All years does not load a tax year; the Tax tab is repainted to say Pick a year", async () => {
    const loaded = []; let repainted = 0;
    globalThis.loadSalesTaxYear = (y) => { loaded.push(y); };
    globalThis.stRepaint = () => { repainted++; };
    try {
      await m.slSetYear("");
      assert.deepEqual(loaded, []);
      assert.equal(repainted, 1);
      assert.equal(m.slCurrentYear(), "");
      await m.slSetYear("2025");
      assert.deepEqual(loaded, ["2025"]);
    } finally { delete globalThis.loadSalesTaxYear; delete globalThis.stRepaint; await m.slSetYear(String(new Date().getFullYear())); }
  });
});

describe("three tabs", () => {
  const stubs = { renderSalesQueue: "sq", renderTransactionLog: "tl", renderCashInvestment: "ci", renderTransactions: "tx",
    renderSalesTaxYear: "stRoot", renderBrokerImport: "bi", renderSalesBroker1099b: "b1" };
  const ids = (html) => [...html.matchAll(/\sid="([^"]*)"/g)].map((x) => x[1]);
  const memStore = () => { const d = {}; return { getItem: (k) => (k in d ? d[k] : null), setItem: (k, v) => { d[k] = String(v); } }; };
  const withStubs = (fn) => () => {
    for (const [k, id] of Object.entries(stubs)) globalThis[k] = () => `<div id="${id}">${k}</div>`;
    globalThis.localStorage = memStore();
    try { fn(); } finally { for (const k of Object.keys(stubs)) delete globalThis[k]; delete globalThis.location; delete globalThis.localStorage; }
  };
  const ORDER = ["fix", "ledger", "tax"];

  test("three tabpanels are direct children of the .field-list root, with stRoot inside", withStubs(() => {
    const html = m.renderSalesLedger();
    assert.match(html, /^<div class="field-list sl-page" id="slRoot">/);
    assert.equal((html.match(/role="tabpanel"/g) || []).length, 3);
    for (const id of ORDER) {
      const before = html.slice(0, html.indexOf(`<div class="sl-tab" role="tabpanel" id="sl-p-${id}"`));
      const depth = (before.match(/<div\b/g) || []).length - (before.match(/<\/div>/g) || []).length;
      assert.equal(depth, 1, id); // only the page root is open
    }
    assert.match(html, /id="stRoot"/);
    assert.ok(html.indexOf('id="slHeadRoot"') < html.indexOf('role="tablist"'));
    assert.ok(html.indexOf('role="tablist"') < html.indexOf('id="sl-p-fix"'));
  }));

  test("panels land in their tabs", withStubs(() => {
    const html = m.renderSalesLedger();
    const inPanel = (panel, text) => {
      const a = html.indexOf(`id="sl-p-${panel}"`);
      const n = ORDER[ORDER.indexOf(panel) + 1];
      const b = n ? html.indexOf(`id="sl-p-${n}"`) : html.length;
      const i = html.indexOf(text);
      return i > a && i < b;
    };
    assert.ok(inPanel("fix", "renderSalesQueue"));
    for (const n of ["renderTransactionLog", "renderCashInvestment", "renderBrokerImport"]) assert.ok(!html.includes(n), n + " no longer mounts on the ledger");
    for (const t of ['id="seCard"', 'id="slListRoot"']) assert.ok(inPanel("ledger", t), t);
    assert.ok(!html.includes("slCsvRoot") && !html.includes("More views"));
    for (const n of ["renderSalesTaxYear", "renderSalesBroker1099b"]) assert.ok(inPanel("tax", n), n);
  }));

  test("fix tab holds the queue and the log-health slot only", withStubs(() => {
    const html = m.renderSalesLedger();
    const fix = html.slice(html.indexOf('id="sl-p-fix"'), html.indexOf('id="sl-p-ledger"'));
    assert.match(fix, /id="sl-sec-queue"/);
    assert.doesNotMatch(fix, /id="sl-sec-log"|id="sl-sec-cash"/);
  }));

  test("no id occurs twice", withStubs(() => {
    const all = ids(m.renderSalesLedger());
    assert.ok(all.length > 10);
    assert.deepEqual(all.filter((x, i) => all.indexOf(x) !== i), []);
  }));

  test("fix is the default active tab", withStubs(() => {
    const html = m.renderSalesLedger();
    assert.match(html, /id="sl-t-fix"[^>]*aria-selected="true"/);
    assert.doesNotMatch(html, /id="sl-p-fix"[^>]*hidden/);
    for (const id of ["ledger", "tax"]) assert.match(html, new RegExp(`id="sl-p-${id}"[^>]*hidden`));
  }));

  test("#sales_ledger?tab=tax opens Tax year; the retired import tab is ignored", withStubs(() => {
    globalThis.location = { hash: "#sales_ledger?tab=tax" };
    const html = m.renderSalesLedger();
    assert.match(html, /id="sl-t-tax"[^>]*aria-selected="true"/);
    assert.doesNotMatch(html, /id="sl-p-tax"[^>]*hidden/);
    assert.match(html, /id="sl-p-fix"[^>]*hidden/);
    globalThis.location = { hash: "#sales_ledger?tab=import" };
    assert.match(m.renderSalesLedger(), /id="sl-t-tax"[^>]*aria-selected="true"/); // unchanged: the link does not apply
  }));

  test("an unknown tab or another page's hash is ignored", withStubs(() => {
    globalThis.location = { hash: "#sales_ledger?tab=bogus" };
    assert.match(m.renderSalesLedger(), /id="sl-t-fix"[^>]*aria-selected="true"/);
    globalThis.location = { hash: "#other?tab=import" };
    assert.match(m.renderSalesLedger(), /id="sl-t-fix"[^>]*aria-selected="true"/);
  }));

  test("a deep link applies once: a later tab click survives a full re-render", withStubs(() => {
    globalThis.location = { hash: "#sales_ledger?tab=ledger" };
    assert.match(m.renderSalesLedger(), /id="sl-t-ledger"[^>]*aria-selected="true"/);
    const els = {};
    globalThis.document = { getElementById: (id) => els[id] || null };
    window.slSetTab("tax");
    delete globalThis.document;
    assert.match(m.renderSalesLedger(), /id="sl-t-tax"[^>]*aria-selected="true"/); // hash still says ledger
  }));

  test("sec is validated against the known section keys", withStubs(() => {
    globalThis.location = { hash: "#sales_ledger?tab=fix&sec=wash" };
    assert.deepEqual(m.slHashTarget(), { tab: "fix", sec: "wash" });
    globalThis.location = { hash: "#sales_ledger?tab=fix&sec=nonsense" };
    assert.deepEqual(m.slHashTarget(), { tab: "fix", sec: null });
    delete globalThis.location;
    assert.deepEqual(m.slHashTarget(), { tab: null, sec: null });
  }));
});

describe("real-DOM fixes (Task 16a)", () => {
  const stubs = { renderSalesQueue: "sq", renderTransactionLog: "tl", renderLogHealth: "lh", renderSalesTaxYear: "stRoot", renderBrokerImport: "bi", renderSalesBroker1099b: "b1" };
  const memStore = () => { const d = {}; return { getItem: (k) => (k in d ? d[k] : null), setItem: (k, v) => { d[k] = String(v); } }; };
  const withStubs = (fn) => async () => {
    for (const [k, id] of Object.entries(stubs)) globalThis[k] = () => `<div id="${id}">${k}</div>`;
    globalThis.localStorage = memStore();
    try { await fn(); } finally {
      for (const k of Object.keys(stubs)) delete globalThis[k];
      delete globalThis.location; delete globalThis.history; delete globalThis.localStorage; delete globalThis.tlStarted;
    }
  };
  const idsOf = (html) => [...html.matchAll(/\sid="([^"]*)"/g)].map((x) => x[1]);

  test("the page has no Sales Ledger h2 heading", withStubs(() => {
    assert.doesNotMatch(m.renderSalesLedger(), /<h2>Sales Ledger<\/h2>/);
  }));

  test("the wrapper carries the slot id once and its content never does", withStubs(() => {
    for (const started of [true, false]) {
      globalThis.tlStarted = () => started;
      assert.doesNotMatch(window.slHealthSlotInnerHtml(), /id="tlHealthSlot"/);
      assert.equal(window.slHealthSlotHtml(), `<div id="tlHealthSlot">${window.slHealthSlotInnerHtml()}</div>`);
    }
  }));

  test("slGo leaves no hash: a later render keeps the clicked tab and schedules no slGo", withStubs(async () => {
    const went = [];
    const realGo = window.slGo;
    globalThis.location = { hash: "", pathname: "/p", search: "?q=1" };
    globalThis.history = { replaceState: (_a, _b, url) => { globalThis.location.hash = url.startsWith("#") ? url : ""; } };
    const els = {};
    for (const t of ["fix", "ledger", "tax"]) { els[`sl-t-${t}`] = { setAttribute() {}, classList: { toggle() {} } }; els[`sl-p-${t}`] = {}; }
    globalThis.document = { getElementById: (id) => els[id] || null };
    try {
      realGo("tax", "wash"); // a strip click
      assert.equal(globalThis.location.hash, "");
      window.slSetTab("fix");
      window.slGo = (t, s2) => went.push([t, s2]);
      assert.match(m.renderSalesLedger(), /id="sl-t-fix"[^>]*aria-selected="true"/);
      await new Promise((r) => setTimeout(r, 5));
      assert.deepEqual(went, []);
      globalThis.location.hash = "#sales_ledger?tab=tax&sec=wash"; // a Year-End style entry still applies once
      assert.match(m.renderSalesLedger(), /id="sl-t-tax"[^>]*aria-selected="true"/);
      await new Promise((r) => setTimeout(r, 5));
      assert.deepEqual(went, [["tax", "wash"]]);
    } finally { window.slGo = realGo; delete globalThis.document; globalThis.document = { getElementById: (id) => (id in globalThis.__fields ? { value: globalThis.__fields[id] } : globalThis.__roots[id] || null) }; }
  }));

  test("storage off: a summary publish repaints the tab bar with the clicked tab; Expand/Collapse act on it", withStubs(() => {
    globalThis.localStorage = { getItem() { throw new Error("denied"); }, setItem() { throw new Error("denied"); } };
    const prev = globalThis.document;
    const els = { slTabsRoot: { innerHTML: "" }, slStripRoot: { innerHTML: "" } };
    for (const t of ["fix", "ledger", "tax"]) { els[`sl-t-${t}`] = { setAttribute() {}, classList: { toggle() {} } }; els[`sl-p-${t}`] = {}; }
    globalThis.document = { getElementById: (id) => els[id] || null, activeElement: null };
    try {
      assert.match(m.renderSalesLedger(), /id="sl-t-fix"[^>]*aria-selected="true"/); // subscribes the tab bar repaint
      window.slSetTab("ledger");
      window.slPublish("queue", { count: 2, tone: "warn", text: "2 waiting" });
      assert.match(els.slTabsRoot.innerHTML, /id="sl-t-ledger"[^>]*aria-selected="true"/);
      assert.match(els.slTabsRoot.innerHTML, /id="sl-t-fix"[^>]*aria-selected="false"/);
      assert.match(els.slTabsRoot.innerHTML, /onclick="slSecAll\(null,true\)"/);
      assert.match(els.slTabsRoot.innerHTML, /onclick="slSecAll\(null,false\)"/);
      assert.match(m.renderSalesLedger(), /id="sl-t-ledger"[^>]*aria-selected="true"/); // a full re-render keeps it too
    } finally { window.slPublish("queue", { count: 0, tone: "", text: "" }); window.slSetTab("fix"); globalThis.document = prev; }
  }));

  test("queue and health shells are closed with state text when there is nothing to show; open when alerting", withStubs(() => {
    window.slPublish("queue", { count: 0, tone: "", text: "" });
    window.slPublish("health", { count: 0, tone: "", text: "" });
    globalThis.tlStarted = () => true;
    let html = m.renderSalesLedger();
    assert.match(html, /<details class="sl-sec" id="sl-sec-queue" data-key="queue" data-alert="0">/);
    assert.match(html, /<details class="sl-sec" id="sl-sec-health" data-key="health" data-alert="0">/);
    assert.match(html, /id="sl-sec-state-queue">Nothing waiting</);
    assert.match(html, /id="sl-sec-state-health">Log agrees with holdings</);
    assert.equal(m.slQueueStateText(), "Nothing waiting");
    window.slPublish("queue", { count: 3, tone: "warn", text: "3 waiting" });
    window.slPublish("health", { count: 2, tone: "bad", text: "drift: 2 accounts" });
    html = m.renderSalesLedger();
    assert.match(html, /<details class="sl-sec" id="sl-sec-queue" data-key="queue" open data-alert="3">/);
    assert.match(html, /<details class="sl-sec" id="sl-sec-health" data-key="health" open data-alert="2">/);
    assert.match(html, /id="sl-sec-state-queue">oldest first — pick the lots sold</);
    assert.match(html, /id="sl-sec-state-health">drift: 2 accounts</);
    window.slPublish("queue", { count: 0, tone: "", text: "" });
    window.slPublish("health", { count: 0, tone: "", text: "" });
  }));

  test("a deep link is consumed after it applies, so the same link applies again", withStubs(() => {
    const replaced = [];
    globalThis.location = { hash: "#sales_ledger?tab=tax", pathname: "/frontend/index.html", search: "?x=1" };
    globalThis.history = { replaceState: (a, b, url) => { replaced.push(url); globalThis.location.hash = ""; } };
    window.slSetTab && window.slUiSave(window.slUiSetTab(window.slUiLoad(), "fix"));
    assert.match(m.renderSalesLedger(), /id="sl-t-tax"[^>]*aria-selected="true"/);
    assert.deepEqual(replaced, ["/frontend/index.html?x=1"]);
    window.slUiSave(window.slUiSetTab(window.slUiLoad(), "fix")); // the user moved on
    globalThis.location.hash = "#sales_ledger?tab=tax"; // the same link again
    assert.match(m.renderSalesLedger(), /id="sl-t-tax"[^>]*aria-selected="true"/);
    delete globalThis.history; // no history API: must not throw
    globalThis.location.hash = "#sales_ledger?tab=ledger";
    assert.doesNotThrow(() => m.renderSalesLedger());
  }));

  test("the hash's sec opens that section after mount (known keys only)", withStubs(async () => {
    const went = [];
    const realGo = window.slGo;
    window.slGo = (t, s) => went.push([t, s]);
    try {
      globalThis.location = { hash: "#sales_ledger?tab=fix&sec=queue", pathname: "/p", search: "" };
      globalThis.history = { replaceState: () => { globalThis.location.hash = ""; } };
      m.renderSalesLedger();
      await new Promise((r) => setTimeout(r, 5));
      assert.deepEqual(went, [["fix", "queue"]]);
      went.length = 0;
      globalThis.location.hash = "#sales_ledger?tab=fix&sec=nonsense";
      m.renderSalesLedger();
      await new Promise((r) => setTimeout(r, 5));
      assert.deepEqual(went, []);
    } finally { window.slGo = realGo; }
  }));
});

describe("summary change repaints only strip and tab bar roots (Task 6)", () => {
  test("panel roots untouched", () => {
    const mk = (id) => (globalThis.__roots[id] = { writes: 0, _h: "", get innerHTML() { return this._h; }, set innerHTML(v) { this.writes++; this._h = v; } });
    for (const id of ["slStripRoot", "slTabsRoot", "slHeadRoot", "slFormRoot", "slCsvRoot", "slListRoot"]) mk(id);
    globalThis.document = { getElementById: (id) => globalThis.__roots[id] || null };
    const html = m.renderSalesLedger();
    assert.ok(!html.includes('id="slLive"') && html.indexOf('id="slStripRoot"') < html.indexOf('role="tablist"')); // live regions are persistent now
    window.slPublish("queue", { count: 2, tone: "bad", text: "2 waiting" });
    const r = globalThis.__roots;
    assert.ok(r.slStripRoot.writes >= 1 && r.slStripRoot.innerHTML.includes("2 waiting"));
    assert.ok(r.slTabsRoot.writes >= 1 && /sl-tab-badge/.test(r.slTabsRoot.innerHTML));
    for (const id of ["slHeadRoot", "slFormRoot", "slCsvRoot", "slListRoot"]) assert.equal(r[id].writes, 0, id);
    for (const id of ["slStripRoot", "slTabsRoot", "slHeadRoot", "slFormRoot", "slCsvRoot", "slListRoot"]) delete globalThis.__roots[id];
  });
});

describe("ledger tab (Task 12)", () => {
  before(() => { globalThis.localStorage = { getItem: () => JSON.stringify({ taxableOnly: false }), setItem() {} }; }); // these rows include a Roth sale
  after(() => { delete globalThis.localStorage; });
  const rows =[SALE(), SALE({ sale_id: 8, gain: null, tax_class: "roth" }), SALE({ sale_id: 9, status: "voided", gain: 100 })];
  const withApi = (handler, fn) => async () => {
    const realApi = globalThis.api;
    globalThis.api = async (url, opts) => { const r = await handler(url, opts); return r === undefined ? realApi(url, opts) : r; };
    try { await fn(); } finally { globalThis.api = realApi; }
  };
  const mkRoot = (id) => (globalThis.__roots[id] = { writes: 0, log: null, _h: "", get innerHTML() { return this._h; }, set innerHTML(v) { this.writes++; this._h = v; if (this.log) this.log.push(id); } });
  const loadWith = (extra) => async (url, opts) => {
    if (url.startsWith("/api/sales?")) {
      calls.push([url, opts && opts.method, null]);
      const hidden = url.includes("include_voided");
      const sales = hidden ? rows : rows.slice(0, 2);
      return { success: true, sales, totals: { count: sales.length, short_gain: 0, long_gain: 495 } };
    }
    return extra ? extra(url) : undefined;
  };

  test("the list shows one sale row per sale and the KPI strip from /api/sales/summary", withApi(async (url) => {
    if (url.startsWith("/api/sales/summary")) { calls.push([url]); return { success: true, summary: { sales: 2, count: 2, st_gain: 0, lt_gain: 495, fees: 10 } }; }
    return loadWith()(url);
  }, async () => {
    mkRoot("slListRoot");
    calls.length = 0;
    await m.loadSalesLedger();
    const h = globalThis.__roots.slListRoot.innerHTML;
    assert.match(h, /<strong>2<\/strong> sales · short-term realized .*\$0\.00.* · long-term realized .*\+\$495\.00<\/span> · fees \$10\.00/);
    assert.equal((h.match(/class="sl-sale/g) || []).length, 1);                    // both lots are one sale (same account, symbol, day)
    assert.ok(calls.some((c) => /\/api\/sales\/summary\?year=\d{4}&taxable_only=0/.test(c[0])));   // the switch is off in this describe
    delete globalThis.__roots.slListRoot;
  }));

  test("table sits in a focusable labelled scroll region", () => {
    assert.match(m.slTableHtml([SALE()]), /<div class="rc-scroll sl-scroll" role="region" aria-label="Sales" tabindex="0">/);
  });

  test("void asks first: cancel posts nothing, confirm posts once and names the gain and year", withApi(loadWith(), async () => {
    await m.loadSalesLedger();
    confirmState.answer = false;
    calls.length = 0;
    await m.slVoid(7);
    assert.equal(calls.filter((c) => c[1] === "POST").length, 0);
    confirmState.answer = true;
    await m.slVoid(7);
    assert.equal(calls.filter((c) => c[1] === "POST").length, 1);
    const [first, second] = confirmState.asked;
    assert.match(first.message, /\+\$495\.00/);
    assert.match(first.message, /2026 totals/);
    assert.equal(first.opts.confirmLabel, "Void sale");
    assert.equal(first.opts.variant, "warn");
    await m.slVoid(8);
    assert.match(confirmState.asked[2].message, /this sale/);
    assert.ok(second);
  }));

  test("a log-linked sale void says Restore will not be available; no dialog means no void", withApi(async (url) => {
    if (url.startsWith("/api/sales?")) {
      const linked = SALE({ sale_id: 21, lot_key: JSON.stringify({ log_sell: 12 }) });
      return { success: true, sales: [linked], totals: { count: 1, short_gain: 0, long_gain: 495 } };
    }
  }, async () => {
    await m.loadSalesLedger();
    calls.length = 0;
    await m.slVoid(21);
    assert.match(confirmState.asked.at(-1).message, /Restore will not be available/);
    assert.equal(calls.filter((c) => c[1] === "POST").length, 1);
    delete globalThis.showInAppConfirm;
    calls.length = 0;
    try {
      await m.slVoid(21);
      assert.equal(calls.filter((c) => c[1] === "POST").length, 0, "fails closed when no dialog exists");
    } finally { await installInAppConfirm(); }
  }));

  test("hidden voided count comes from one extra fetch; absent on failure", withApi(loadWith(), async () => {
    calls.length = 0;
    await m.loadSalesLedger();
    assert.equal(calls.filter((c) => c[0].includes("include_voided=1")).length, 1);
    assert.equal(m.slHiddenVoidCount(), 1);
    assert.match(m.renderSalesLedger(), /id="slVoidedLink"[^>]*>Voided rows \(1\)</);
    globalThis.api = async (url) => { if (url.includes("include_voided=1")) throw new Error("x"); return { success: true, sales: [], totals: { count: 0, short_gain: 0, long_gain: 0 } }; };
    await m.loadSalesLedger();
    assert.equal(m.slHiddenVoidCount(), 0);
    assert.match(m.renderSalesLedger(), /Voided rows \(0\)/);
  }));

  test("the hidden-void count uses the year the load started with, even if the year changes mid-load", withApi(async (url) => {
    if (url.startsWith("/api/sales?")) {
      calls.push([url]);
      if (!url.includes("include_voided") && !globalThis.__kicked) { globalThis.__kicked = true; m.slSetYear("2019"); }
      return { success: true, sales: rows.slice(0, 2), totals: { count: 2, short_gain: 0, long_gain: 0 } };
    }
    return undefined;
  }, async () => {
    const orig = String(new Date().getFullYear());
    globalThis.__kicked = true;
    await m.slSetYear(orig);
    calls.length = 0;
    globalThis.__kicked = false;
    await m.loadSalesLedger();
    await new Promise((r) => setTimeout(r, 20));
    const years = calls.filter((c) => c[0].includes("include_voided=1")).map((c) => new URLSearchParams(c[0].split("?")[1]).get("year")).sort();
    assert.deepEqual(years, [orig, "2019"].sort());
    delete globalThis.__kicked;
    await m.slSetYear(orig);
  }));

  test("with Show voided on there is no extra include_voided fetch and nothing is hidden", withApi(loadWith(), async () => {
    await m.slSetShowVoided(true);
    calls.length = 0;
    await m.loadSalesLedger();
    assert.equal(calls.filter((c) => c[0].includes("/api/sales?")).length, 1);
    assert.equal(m.slHiddenVoidCount(), 0);
    await m.slSetShowVoided(false);
  }));
});

describe("next-step links", () => {
  test("slNextStepHtml offers the wash re-run after a 1099-B apply, and the queue link only when sales are waiting", () => {
    window.slPublish("queue", { count: 0, tone: "", text: "" });
    let h = window.slNextStepHtml({ wash: true });
    assert.match(h, /slGo\('tax','wash'\)/);
    assert.match(h, /Review changed lots \/ re-run wash check/);
    assert.doesNotMatch(h, /slGo\('fix','queue'\)/);
    window.slPublish("queue", { count: 3, tone: "warn", text: "3 waiting" });
    h = window.slNextStepHtml({ wash: true });
    assert.match(h, /3 sales waiting → Fix lots/);
    assert.match(h, /slGo\('fix','queue'\)/);
    assert.doesNotMatch(window.slNextStepHtml({}), /slGo\('tax','wash'\)/);
    assert.equal(window.slNextStepHtml(null), "");
    window.slPublish("queue", { count: 0, tone: "", text: "" });
    assert.equal(window.slNextStepHtml({}), "");
  });
});

describe("section shell state", () => {
  test("every section summary carries a state span; slSecSetState patches it and is a no-op without the element or document", () => {
    assert.match(window.slSecHtml({ key: "x", title: "T" }), /<span class="sl-sec-state" id="sl-sec-state-x"><\/span>/);
    const el = { textContent: "" };
    const prev = globalThis.document;
    globalThis.document = { getElementById: (id) => (id === "sl-sec-state-x" ? el : null) };
    window.slSecSetState("x", "hello"); window.slSecSetState("nope", "z");
    assert.equal(el.textContent, "hello");
    delete globalThis.document;
    assert.doesNotThrow(() => window.slSecSetState("x", "y"));
    globalThis.document = prev;
  });
});
