// Plan step 1.4: the pure HTML helpers and the fetch calls of dashboard_decomp_sales_ledger.js.
import { test, describe, before, beforeEach } from "node:test";
import assert from "node:assert/strict";

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
  await import("../../frontend/js/dashboard_decomp_sales_ledger_ui.js");
  m = await import("../../frontend/js/dashboard_decomp_sales_ledger.js");
});
beforeEach(() => { calls.length = 0; });

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
  test("a row shows the lot, term and a Void button; a voided row offers Restore", () => {
    const html = m.slRowHtml(SALE());
    assert.match(html, /VTI/);
    assert.match(html, /Long/);
    assert.match(html, /slVoid\(7\)/);
    assert.match(m.slRowHtml(SALE({ status: "voided" })), /slUnvoid\(7\)/);
    assert.match(m.slRowHtml(SALE({ status: "voided" })), /sl-voided/);
  });
  test("user text is escaped", () => {
    assert.doesNotMatch(m.slRowHtml(SALE({ account: "<img onerror=x>" })), /<img/);
  });
  test("empty ledger says so", () => {
    assert.match(m.slTableHtml([]), /No sales recorded/);
  });
  test("totals line shows short and long net", () => {
    const html = m.slTotalsHtml({ count: 2, short_gain: -505, long_gain: 495 });
    assert.match(html, /-\$505\.00/);
    assert.match(html, /\$495\.00/);
  });
});

describe("csv preview", () => {
  test("counts, duplicates and line errors", () => {
    const html = m.slPreviewHtml({ received: 4, will_write: [{}], duplicates: [{}, {}], errors: [{ line: 5, error: "shares must be > 0" }] });
    assert.match(html, /1 to add/);
    assert.match(html, /2 already in the ledger/);
    assert.match(html, /Line 5: shares must be &gt; 0|Line 5: shares must be > 0/);
    assert.doesNotMatch(html, /slImportCommit/);  // errors refuse the whole file
  });
  test("a clean preview offers the commit", () => {
    assert.match(m.slPreviewHtml({ received: 1, will_write: [{}], duplicates: [], errors: [] }), /slImportCommit/);
  });
});

describe("actions", () => {
  test("slSubmit posts the form fields and reloads the list", async () => {
    Object.assign(globalThis.__fields, { slDate: "2026-06-10", slAccount: "Trust", slClass: "taxable", slSymbol: "vti", slShares: "10",
      slProceeds: "2000", slFees: "5", slBasis: "1500", slPurchase: "2025-01-02" });
    await m.slSubmit();
    const post = calls.find((c) => c[0] === "/api/sales" && c[1] === "POST");
    assert.deepEqual(post[2], { sale_date: "2026-06-10", account: "Trust", tax_class: "taxable", symbol: "vti", shares: "10",
      proceeds: "2000", fees: "5", basis: "1500", purchase_date: "2025-01-02" });
    assert.ok(calls.some((c) => c[0].startsWith("/api/sales?")));
  });
  test("void and restore post to the sale", async () => {
    await m.slVoid(7);
    await m.slUnvoid(7);
    assert.deepEqual(calls.filter((c) => c[1] === "POST").map((c) => c[0]), ["/api/sales/7/void", "/api/sales/7/unvoid"]);
  });
  test("csv preview posts the pasted text", async () => {
    globalThis.__fields.slCsv = "a,b\n";
    await m.slImportPreview();
    assert.deepEqual(calls.find((c) => c[0] === "/api/sales/import/preview")[2], { content: "a,b\n" });
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

describe("scoped repaint keeps drafts (F10)", () => {
  const clearFields = () => { for (const k of Object.keys(globalThis.__fields)) delete globalThis.__fields[k]; };
  const unesc = (t) => t.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, "&");
  // Root stubs behave like the DOM: writing innerHTML re-creates the inputs, so their live value comes from the new markup.
  const mountRoots = () => {
    for (const id of ["slHeadRoot", "slFormRoot", "slCsvRoot", "slListRoot"]) {
      globalThis.__roots[id] = { writes: 0, _h: "", get innerHTML() { return this._h; }, set innerHTML(v) {
        this.writes++; this._h = v;
        if (id === "slCsvRoot") {
          const t = /<textarea id="slCsv"[^>]*>([\s\S]*?)<\/textarea>/.exec(v);
          if (t) globalThis.__fields.slCsv = unesc(t[1]); else delete globalThis.__fields.slCsv;
        }
        if (id === "slFormRoot") {
          for (const mt of v.matchAll(/<input id="(sl\w+)"[^>]*value="([^"]*)"/g)) globalThis.__fields[mt[1]] = unesc(mt[2]);
        }
      } };
    }
  };
  const type = (id, v) => { globalThis.__fields[id] = v; m.slDraftSet(id, v); }; // what a keystroke does
  beforeEach(() => { clearFields(); mountRoots(); });

  test("a ledger load repaints only the list and keeps the form and CSV drafts", async () => {
    type("slSymbol", "VXUS");
    type("slCsv", "a,b\n1,2\n");
    await m.loadSalesLedger();
    const r = globalThis.__roots;
    assert.ok(r.slListRoot.writes >= 1);
    assert.equal(r.slFormRoot.writes, 0);
    assert.equal(r.slCsvRoot.writes, 0);
    assert.equal(r.slHeadRoot.writes, 0);
    calls.length = 0;
    await m.slSubmit();
    assert.equal(calls.find((c) => c[0] === "/api/sales" && c[1] === "POST")[2].symbol, "VXUS");
    type("slCsv", "a,b\n1,2\n");
    await m.slImportPreview();
    assert.deepEqual(calls.find((c) => c[0] === "/api/sales/import/preview")[2], { content: "a,b\n1,2\n" });
  });

  test("changing the year does not rewrite the form or CSV roots", async () => {
    await m.slSetYear("2025");
    assert.equal(globalThis.__roots.slFormRoot.writes, 0);
    assert.equal(globalThis.__roots.slCsvRoot.writes, 0);
    await m.slSetYear(String(new Date().getFullYear()));
  });

  test("a successful action clears a stale preview and its Add button", async () => {
    type("slCsv", "sale_date,symbol\n2026-01-02,VTI\n");
    await m.slImportPreview();
    assert.match(globalThis.__roots.slCsvRoot.innerHTML, /slImportCommit/);
    await m.slVoid(7);
    assert.doesNotMatch(globalThis.__roots.slCsvRoot.innerHTML, /slImportCommit/);
  });

  test("typing during an in-flight save is kept; a failed save restores the sent draft", async () => {
    const realApi = globalThis.api;
    let release;
    globalThis.api = async (url, opts) => {
      if (url === "/api/sales" && opts && opts.method === "POST") { await new Promise((r) => { release = r; }); return { success: true }; }
      return realApi(url, opts);
    };
    try {
      type("slSymbol", "VTI");
      const p = m.slSubmit();
      await new Promise((r) => setTimeout(r, 0));
      type("slShares", "5"); // typed while the save is in flight
      release();
      await p;
      const html = m.renderSalesLedger();
      assert.match(html, /id="slShares"[^>]*value="5"/);
      assert.match(html, /id="slSymbol"[^>]*value=""/);
      globalThis.api = async (url, opts) => {
        if (url === "/api/sales" && opts && opts.method === "POST") throw new Error("nope");
        return realApi(url, opts);
      };
      type("slSymbol", "BND");
      await m.slSubmit();
      assert.match(m.renderSalesLedger(), /id="slSymbol"[^>]*value="BND"/);
    } finally {
      globalThis.api = realApi;
      m.slCancelEdit();
    }
  });

  test("preview then commit posts the pasted CSV text even though the preview repaints the CSV box", async () => {
    type("slCsv", "sale_date,symbol\n2026-01-02,VTI\n");
    await m.slImportPreview();
    assert.ok(globalThis.__roots.slCsvRoot.writes >= 1);
    assert.equal(globalThis.__fields.slCsv, "sale_date,symbol\n2026-01-02,VTI\n"); // the repainted textarea still holds the text
    await m.slImportCommit();
    const bodies = calls.filter((c) => c[0] === "/api/sales/import/preview" || c[0] === "/api/sales/import/commit").map((c) => c[2].content);
    assert.deepEqual(bodies, ["sale_date,symbol\n2026-01-02,VTI\n", "sale_date,symbol\n2026-01-02,VTI\n"]);
  });

  test("the form is drawn from the draft", () => {
    m.slDraftSet("slShares", "42");
    assert.match(m.renderSalesLedger(), /id="slShares"[^>]*value="42"/);
  });

  test("header says Sale year with an All years option; ledger ids appear once", () => {
    const html = m.renderSalesLedger();
    assert.match(html, /Sale year/);
    assert.match(html, /<select id="slYear"[^>]*>\s*<option value="" ?[^>]*>All years/);
    assert.match(html, /Show voided/);
    for (const id of ["slAccount", "slDate", "slClass", "slSymbol", "slShares", "slProceeds", "slFees", "slBasis", "slPurchase", "slCsv", "slYear"]) {
      assert.equal(html.split(`id="${id}"`).length - 1, 1, id);
    }
  });
});

describe("four tabs (Task 4)", () => {
  const stubs = { renderSalesQueue: "sq", renderTransactionLog: "tl", renderCashInvestment: "ci", renderTransactions: "tx",
    renderSalesTaxYear: "stRoot", renderBrokerImport: "bi", renderSalesBroker1099b: "b1" };
  const ids = (html) => [...html.matchAll(/\sid="([^"]*)"/g)].map((x) => x[1]);
  const memStore = () => { const d = {}; return { getItem: (k) => (k in d ? d[k] : null), setItem: (k, v) => { d[k] = String(v); } }; };
  const withStubs = (fn) => () => {
    for (const [k, id] of Object.entries(stubs)) globalThis[k] = () => `<div id="${id}">${k}</div>`;
    globalThis.localStorage = memStore();
    try { fn(); } finally { for (const k of Object.keys(stubs)) delete globalThis[k]; delete globalThis.location; delete globalThis.localStorage; }
  };
  const ORDER = ["fix", "ledger", "tax", "import"];

  test("four tabpanels are direct children of the .field-list root, with stRoot inside", withStubs(() => {
    const html = m.renderSalesLedger();
    assert.match(html, /^<div class="field-list sl-page" id="slRoot">/);
    assert.equal((html.match(/role="tabpanel"/g) || []).length, 4);
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
    for (const n of ["renderSalesQueue", "renderTransactionLog", "renderCashInvestment", "renderTransactions"]) assert.ok(inPanel("fix", n), n);
    for (const t of ['id="slFormRoot"', 'id="slCsvRoot"', 'id="slListRoot"']) assert.ok(inPanel("ledger", t), t);
    assert.ok(inPanel("tax", "renderSalesTaxYear"));
    for (const n of ["renderBrokerImport", "renderSalesBroker1099b"]) assert.ok(inPanel("import", n), n);
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
    for (const id of ["ledger", "tax", "import"]) assert.match(html, new RegExp(`id="sl-p-${id}"[^>]*hidden`));
  }));

  test("#sales_ledger?tab=import opens Import; an unknown tab or other hash is ignored", withStubs(() => {
    globalThis.location = { hash: "#sales_ledger?tab=import" };
    const html = m.renderSalesLedger();
    assert.match(html, /id="sl-t-import"[^>]*aria-selected="true"/);
    assert.doesNotMatch(html, /id="sl-p-import"[^>]*hidden/);
    assert.match(html, /id="sl-p-fix"[^>]*hidden/);
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

describe("summary change repaints only strip and tab bar roots (Task 6)", () => {
  test("panel roots untouched", () => {
    const mk = (id) => (globalThis.__roots[id] = { writes: 0, _h: "", get innerHTML() { return this._h; }, set innerHTML(v) { this.writes++; this._h = v; } });
    for (const id of ["slStripRoot", "slTabsRoot", "slHeadRoot", "slFormRoot", "slCsvRoot", "slListRoot"]) mk(id);
    globalThis.document = { getElementById: (id) => globalThis.__roots[id] || null };
    const html = m.renderSalesLedger();
    assert.ok(html.indexOf('id="slLive"') > -1 && html.indexOf('id="slStripRoot"') < html.indexOf('role="tablist"'));
    window.slPublish("queue", { count: 2, tone: "bad", text: "2 waiting" });
    const r = globalThis.__roots;
    assert.ok(r.slStripRoot.writes >= 1 && r.slStripRoot.innerHTML.includes("2 waiting"));
    assert.ok(r.slTabsRoot.writes >= 1 && /sl-tab-badge/.test(r.slTabsRoot.innerHTML));
    for (const id of ["slHeadRoot", "slFormRoot", "slCsvRoot", "slListRoot"]) assert.equal(r[id].writes, 0, id);
    for (const id of ["slStripRoot", "slTabsRoot", "slHeadRoot", "slFormRoot", "slCsvRoot", "slListRoot"]) delete globalThis.__roots[id];
  });
});
