// Sales Ledger redesign Task 1: UI state store, tab model, hash parsing and the section alert rule (pure functions).
import { test, describe, before } from "node:test";
import assert from "node:assert/strict";

let m;
before(async () => {
  globalThis.window = globalThis;
  m = await import("../../frontend/js/dashboard_decomp_sales_ledger_ui.js");
});

const mem = (initial) => {
  let v = initial ?? null;
  return { getItem: () => v, setItem: (_k, x) => { v = x; }, get raw() { return v; } };
};

describe("slUiLoad / slUiSave", () => {
  const DEFAULTS = { tab: "fix", sections: {}, taxableOnly: true };
  test("defaults when getItem throws", () => {
    assert.deepEqual(m.slUiLoad({ getItem() { throw new Error("denied"); } }), DEFAULTS);
  });
  test("defaults on corrupt JSON", () => {
    assert.deepEqual(m.slUiLoad(mem("{bad")), DEFAULTS);
  });
  test("defaults on null", () => {
    assert.deepEqual(m.slUiLoad(mem(null)), DEFAULTS);
  });
  test("round-trips a saved state", () => {
    const st = { tab: "tax", sections: { queue: { open: false, lastAlertCount: 3 } }, taxableOnly: false };
    const s = mem();
    m.slUiSave(st, s);
    assert.deepEqual(m.slUiLoad(s), st);
  });
  test("save swallows storage errors", () => {
    assert.doesNotThrow(() => m.slUiSave(DEFAULTS, { setItem() { throw new Error("full"); } }));
  });
  test("unknown tab in storage falls back to fix", () => {
    assert.equal(m.slUiLoad(mem(JSON.stringify({ tab: "nope" }))).tab, "fix");
  });
  test('old stored tab "import" falls back to "fix"', () => {
    assert.equal(m.slUiLoad(mem(JSON.stringify({ tab: "import" }))).tab, "fix");
  });
  test("Taxable accounts only defaults on and persists; an old density value is ignored", () => {
    assert.equal(m.slUiLoad(mem(null)).taxableOnly, true);
    const s = mem();
    m.slUiSave({ ...m.slUiLoad(s), taxableOnly: false }, s);
    assert.equal(m.slUiLoad(s).taxableOnly, false);
    const old = m.slUiLoad(mem(JSON.stringify({ tab: "tax", density: "compact" })));
    assert.deepEqual(old, { tab: "tax", sections: {}, taxableOnly: true });
  });
});

describe("tabs and hash", () => {
  test("SL_TABS has three tabs in order", () => {
    assert.deepEqual(m.SL_TABS.map((t) => t[0]), ["fix", "ledger", "tax"]);
    assert.deepEqual(m.SL_TABS.map((t) => t[1]), ["To fix", "Sales", "Tax year"]);
  });
  test("slUiSetTab", () => {
    assert.equal(m.slUiSetTab({ tab: "fix", sections: {}, taxableOnly: true }, "tax").tab, "tax");
    assert.equal(m.slUiSetTab({ tab: "fix", sections: {}, taxableOnly: true }, "import").tab, "fix");
    assert.equal(m.slUiSetTab({ tab: "fix", sections: {}, taxableOnly: true }, "bogus").tab, "fix");
  });
  test("slParseHash", () => {
    assert.deepEqual(m.slParseHash("#sales_ledger?tab=tax&sec=queue"), { tab: "tax", sec: "queue" });
    assert.deepEqual(m.slParseHash("#sales_ledger?tab=import&sec=queue"), { tab: null, sec: "queue" });
    assert.deepEqual(m.slParseHash("#sales_ledger?tab=zzz&sec=queue"), { tab: null, sec: "queue" });
    assert.deepEqual(m.slParseHash("#other"), { tab: null, sec: null });
    assert.deepEqual(m.slParseHash(""), { tab: null, sec: null });
  });
});

describe("slSecOpen / slUiRecordToggle", () => {
  const st = (e) => ({ tab: "fix", sections: e ? { q: e } : {}, taxableOnly: true });
  test("nothing stored returns defaultOpen", () => {
    assert.equal(m.slSecOpen(st(), "q", true, 0), true);
    assert.equal(m.slSecOpen(st(), "q", false, 0), false);
  });
  test("alert count changed and >0 forces open", () => {
    assert.equal(m.slSecOpen(st({ open: false, lastAlertCount: 0 }), "q", false, 1), true);
  });
  test("user collapsed at current count stays closed", () => {
    assert.equal(m.slSecOpen(st({ open: false, lastAlertCount: 2 }), "q", true, 2), false);
  });
  test("stored open honoured when count unchanged", () => {
    assert.equal(m.slSecOpen(st({ open: true, lastAlertCount: 0 }), "q", false, 0), true);
  });
  test("recordToggle stores open and count without mutating input", () => {
    const a = st();
    const b = m.slUiRecordToggle(a, "q", false, 4);
    assert.deepEqual(b.sections.q, { open: false, lastAlertCount: 4 });
    assert.deepEqual(a.sections, {});
  });
});

describe("ARIA tab bar and panels", () => {
  test("slTabBarHtml structure", () => {
    const h = m.slTabBarHtml("fix", {});
    assert.match(h, /role="tablist"/);
    assert.match(h, /aria-label="/);
    assert.equal((h.match(/tabindex="0"/g) || []).length, 1);
    assert.equal((h.match(/tabindex="-1"/g) || []).length, 2);
    for (const [id] of m.SL_TABS) {
      assert.ok(h.includes(`aria-controls="sl-p-${id}"`));
      assert.ok(h.includes(`id="sl-t-${id}"`));
    }
    assert.equal((h.match(/aria-selected="true"/g) || []).length, 1);
  });
  test("marker renders count inside tab", () => {
    const h = m.slTabBarHtml("fix", { ledger: { count: 3, tone: "bad" } });
    assert.match(h, /id="sl-t-ledger"[^>]*>[^]*?<span[^>]*>3<\/span>[^]*?<\/button>/);
  });
  test("slTabPanelHtml hidden unless active", () => {
    const a = m.slTabPanelHtml("fix", "<p>x</p>", "fix");
    const b = m.slTabPanelHtml("tax", "<p>x</p>", "fix");
    for (const h of [a, b]) {
      assert.match(h, /role="tabpanel"/);
    }
    assert.ok(a.includes('aria-labelledby="sl-t-fix"') && a.includes('id="sl-p-fix"') && !/\shidden/.test(a));
    assert.ok(b.includes('aria-labelledby="sl-t-tax"') && /\shidden/.test(b));
  });
  const stubDoc = () => {
    const els = {};
    for (const [id] of m.SL_TABS) {
      els[`sl-t-${id}`] = { attrs: {}, tabIndex: 0, setAttribute(k, v) { this.attrs[k] = v; }, focus() { this.focused = true; } };
      els[`sl-p-${id}`] = { hidden: false };
    }
    return { els, getElementById: (i) => els[i] || null };
  };
  test("slSetTab toggles hidden/aria/tabIndex without re-render", () => {
    const doc = stubDoc();
    globalThis.document = doc;
    let rerenders = 0;
    globalThis.renderMain = () => { rerenders++; };
    m.slSetTab("tax", { focus: true });
    assert.equal(doc.els["sl-p-tax"].hidden, false);
    assert.equal(doc.els["sl-p-fix"].hidden, true);
    assert.equal(doc.els["sl-t-tax"].attrs["aria-selected"], "true");
    assert.equal(doc.els["sl-t-fix"].attrs["aria-selected"], "false");
    assert.equal(doc.els["sl-t-tax"].tabIndex, 0);
    assert.equal(doc.els["sl-t-fix"].tabIndex, -1);
    assert.equal(doc.els["sl-t-tax"].focused, true);
    assert.equal(rerenders, 0);
    delete globalThis.document; delete globalThis.renderMain;
  });
  test("slTabKeydown arrows wrap, Home/End", () => {
    const doc = stubDoc();
    globalThis.document = doc;
    const press = (key, from) => {
      let prevented = false;
      m.slTabKeydown({ key, target: { id: `sl-t-${from}` }, preventDefault() { prevented = true; } });
      return prevented;
    };
    const active = () => m.SL_TABS.map((t) => t[0]).find((id) => doc.els[`sl-t-${id}`].tabIndex === 0);
    assert.ok(press("ArrowRight", "tax")); assert.equal(active(), "fix");
    press("ArrowLeft", "fix"); assert.equal(active(), "tax");
    press("Home", "tax"); assert.equal(active(), "fix");
    press("End", "fix"); assert.equal(active(), "tax");
    assert.equal(doc.els["sl-t-tax"].focused, true);
    assert.equal(press("a", "fix"), false);
    delete globalThis.document;
  });
});

describe("panel summary publish hook", () => {
  test("slPublish stores, slSummaries returns copies, slOnSummary notifies and unsubscribes", () => {
    const seen = [];
    const off = m.slOnSummary((k, s) => seen.push([k, s]));
    m.slPublish("queue", { count: 3, tone: "bad", text: "3 waiting" });
    assert.deepEqual(seen, [["queue", { count: 3, tone: "bad", text: "3 waiting" }]]);
    const snap = m.slSummaries();
    assert.deepEqual(snap.queue, { count: 3, tone: "bad", text: "3 waiting" });
    snap.queue.count = 99;
    assert.equal(m.slSummaries().queue.count, 3);
    off();
    m.slPublish("cash", { count: 0, tone: "", text: "" });
    assert.equal(seen.length, 1);
    assert.deepEqual(m.slSummaries().cash, { count: 0, tone: "", text: "" });
    assert.equal(globalThis.slPublish, m.slPublish);
  });
  test("a throwing subscriber does not break publishing", () => {
    const off = m.slOnSummary(() => { throw new Error("boom"); });
    assert.doesNotThrow(() => m.slPublish("log", { count: 1, tone: "", text: "" }));
    off();
  });
});

describe("alert strip, markers, live region, slGo (Task 6)", () => {
  const S = (count, tone, text) => ({ count, tone, text });
  const fixture = () => ({
    queue: S(3, "bad", "3 waiting"), health: S(2, "warn", "drift: 2 accounts"), wash: S(0, "", "never run"),
    cf: S(1, "warn", "1 to review"), b1099: S(0, "", "")
  });
  test("strip lists queue, drift, wash-never-run and carryforward items as text-only badges", () => {
    const h = m.slStripHtml(fixture());
    assert.match(h, /<nav aria-label="Needs attention"/);
    for (const t of ["3 waiting", "drift: 2 accounts", "never run", "1 to review"]) assert.ok(h.includes(t), t);
    assert.ok(h.includes('href="#sales_ledger?tab=fix&amp;sec=queue"') || h.includes('href="#sales_ledger?tab=fix&sec=queue"'));
    assert.ok(h.includes('data-go="fix:queue"') && h.includes("slGo('fix','queue');return false"));
  });
  test("key to tab mapping", () => {
    const all = Object.fromEntries(["queue", "health", "wash", "cf", "b1099"].map((k) => [k, S(1, "warn", "x " + k)]));
    const h = m.slStripHtml(all);
    for (const [k, t] of [["queue", "fix"], ["health", "fix"], ["wash", "tax"], ["cf", "tax"], ["b1099", "tax"]]) {
      assert.ok(h.includes(`data-go="${t}:${k}"`), k);
    }
    for (const k of ["log", "cash", "imports", "csv"]) assert.ok(!m.slStripHtml({ [k]: S(1, "warn", "x") }).includes("data-go"), k);
  });
  test("a prior-year item still appears (no year filter)", () => {
    const h = m.slStripHtml({ wash: S(2, "warn", "2 wash flags (2023)") });
    assert.ok(h.includes("2 wash flags (2023)"));
  });
  test("count>0 with neutral tone is not an alert; stale text is", () => {
    assert.ok(m.slStripHtml({ queue: S(5, "", "5 rows") }).includes("No open items"));
    assert.ok(m.slStripHtml({ wash: S(0, "", "stale") }).includes('data-go="tax:wash"'));
  });
  test("clear state says No open items and never mentions reconcile", () => {
    for (const s of [{}, { log: S(0, "", "never run"), queue: S(0, "", "") }, { queue: S(0, "", "") }]) {
      const h = m.slStripHtml(s);
      assert.doesNotMatch(h, /reconcile/i);
    }
    assert.match(m.slStripHtml({ queue: S(0, "", "") }), /<span>No open items<\/span>/);
  });
  // Final review I3: raw counts are in different units (sales, accounts, cash rows), so a tab counts its counted alert ITEMS.
  test("slMarkers counts alert items per tab (not summed raw counts), tone bad wins, empty tabs omitted", () => {
    const mk = m.slMarkers(fixture());
    assert.deepEqual(mk.fix, { count: 2, tone: "bad" }); // queue and drift
    assert.deepEqual(mk.tax, { count: 1, tone: "warn" }); // carryforward; the uncounted "never run" wash item adds no number
    const mk2 = m.slMarkers({ wash: S(2, "warn", "w"), cf: S(1, "warn", "c"), b1099: S(4, "bad", "b") });
    assert.deepEqual(mk2.tax, { count: 3, tone: "bad" });
    assert.equal(mk2.import, undefined);
  });
  test("a tab whose alert item has count 0 still gets a text marker (!, needs attention)", () => {
    const mk = m.slMarkers({ wash: S(0, "", "stale") });
    assert.equal(mk.tax.count, 0);
    assert.equal(mk.tax.attn, true);
    const h = m.slTabBarHtml("fix", mk);
    assert.match(h, /id="sl-t-tax"[^>]*>[^]*?<span class="sl-tab-badge warn"[^>]*>[^]*?!<[^]*?needs attention[^]*?<\/button>/);
    assert.doesNotMatch(m.slTabBarHtml("fix", { tax: { count: 0, tone: "warn" } }), /sl-tab-badge/); // no alert flag, nothing to show
    assert.equal(m.slMarkers(fixture()).fix.attn, undefined);
  });
  test("queue and health default closed; ledger and wash default open", () => {
    const st = { sections: {} };
    for (const k of ["queue", "health"]) { assert.equal(m.slSecWantOpen(st, k, 0), false, k); assert.equal(m.slSecWantOpen(st, k, 2), true, k); }
    for (const k of ["ledger", "wash"]) assert.equal(m.slSecWantOpen(st, k, 0), true, k);
  });
  const liveDoc = (withLive = true) => {
    const els = {};
    if (withLive) {
      els.slLive = { textContent: "" };
      els.slAlert = { textContent: "" };
    }
    for (const [id] of m.SL_TABS) {
      els[`sl-t-${id}`] = { attrs: {}, tabIndex: 0, setAttribute(k, v) { this.attrs[k] = v; } };
      els[`sl-p-${id}`] = { hidden: false };
    }
    return { els, getElementById: (i) => els[i] || null };
  };
  test("slAnnounce writes polite or assertive and is a no-op when absent", () => {
    const d = liveDoc(); globalThis.document = d;
    m.slAnnounce("hello"); assert.equal(d.els.slLive.textContent, "hello"); assert.equal(d.els.slAlert.textContent, "");
    m.slAnnounce("bad", true); assert.equal(d.els.slAlert.textContent, "bad");
    globalThis.document = liveDoc(false);
    assert.doesNotThrow(() => m.slAnnounce("x"));
    assert.match(m.slLiveHtml(), /id="slLive"[^>]*aria-live="polite"/);
    assert.match(m.slLiveHtml(), /id="slAlert"[^>]*role="alert"/);
    delete globalThis.document;
  });
  test("slGo switches tab, tolerates missing sections, opens and focuses a present one", () => {
    const d = liveDoc(); globalThis.document = d;
    globalThis.history = { replaceState(_s, _t, u) { this.url = u; } };
    assert.doesNotThrow(() => m.slGo("tax", "wash"));
    assert.equal(d.els["sl-p-tax"].hidden, false);
    assert.equal(d.els["sl-p-fix"].hidden, true);
    assert.equal(globalThis.history.url, undefined); // no location in node: the clean-URL write is skipped; it never writes a hash
    const sum = { focus() { this.focused = true; } };
    d.els["sl-sec-wash"] = { open: false, querySelector: () => sum };
    m.slGo("tax", "wash");
    assert.equal(d.els["sl-sec-wash"].open, true);
    assert.equal(sum.focused, true);
    m.slGo("tax", "bogus");
    assert.equal(globalThis.history.url, undefined); // still no hash written
    delete globalThis.document; delete globalThis.history;
  });
});

describe("collapsible section shell (Task 7)", () => {
  const store = () => { let v = null; return { writes: 0, getItem: () => v, setItem(_k, x) { v = x; this.writes++; } }; };
  const setStore = (s) => Object.defineProperty(globalThis, "localStorage", { value: s, configurable: true, writable: true });
  const secDoc = (keys) => {
    const els = { slLive: { textContent: "" }, slAlert: { textContent: "" } };
    for (const k of keys) {
      els[`sl-sec-${k}`] = { open: false };
      els[`sl-sec-badge-${k}`] = { textContent: "", className: "" };
    }
    els.focusCalls = 0;
    for (const id of ["sl-p-fix", "sl-p-tax", "sl-t-fix", "sl-t-tax"]) els[id] = { hidden: false, focus() { els.focusCalls++; }, setAttribute() {} };
    return { els, getElementById: (i) => els[i] || null };
  };
  const tick = () => new Promise((r) => setTimeout(r, 5));

  test("slSecHtml: details shell, text badge, aria-hidden chevron, no ontoggle", () => {
    const h = m.slSecHtml({ key: "queue", title: "Sales waiting for lots", badges: [{ text: "3 waiting", tone: "warn" }], state: "Needs review", alertCount: 3, open: false, body: "<p>x</p>" });
    assert.match(h, /<details class="sl-sec" id="sl-sec-queue" data-key="queue"(?![^>]*\sopen)/);
    assert.match(h, /<summary id="sl-sec-sum-queue" onclick="slOnSummaryClick\('queue'\)"/);
    assert.match(h, /aria-hidden="true"/);
    assert.match(h, /<h3 class="sl-sec-title">Sales waiting for lots<\/h3>/);
    assert.match(h, /<span class="sl-sec-badge sl-tone-warn" id="sl-sec-badge-queue">3 waiting<\/span>/);
    assert.match(h, /<div class="sl-sec-body"><p>x<\/p><\/div>/);
    assert.ok(!/ontoggle/.test(h));
    assert.match(m.slSecHtml({ key: "log", title: "T", open: true, body: "" }), /data-key="log" open/);
  });
  test("a programmatic open change does not write the store", () => {
    const s = store(); setStore(s); globalThis.document = secDoc(["queue"]);
    m.slPublish("queue", { count: 2, tone: "warn", text: "2 waiting" });
    assert.equal(s.writes, 0);
    assert.equal(globalThis.document.els["sl-sec-queue"].open, true);
    assert.equal(s.writes, 0);
    delete globalThis.document;
  });
  test("click-recorded collapse at count 2 persists; count 3 reopens, announces, never focuses", async () => {
    const s = store(); setStore(s); const d = secDoc(["queue"]); globalThis.document = d;
    m.slSecUpdate("queue", { count: 2, tone: "warn", text: "2 waiting" });
    m.slPublish("queue", { count: 2, tone: "warn", text: "2 waiting" });
    d.els["sl-sec-queue"].open = false; // browser toggled it closed after the click
    m.slOnSummaryClick("queue");
    await tick();
    assert.deepEqual(m.slUiLoad(s).sections.queue, { open: false, lastAlertCount: 2 });
    m.slPublish("queue", { count: 2, tone: "warn", text: "2 waiting" });
    assert.equal(d.els["sl-sec-queue"].open, false);
    m.slPublish("queue", { count: 3, tone: "warn", text: "3 waiting" });
    assert.equal(d.els["sl-sec-queue"].open, true);
    assert.match(d.els.slLive.textContent, /3 waiting/);
    assert.equal(d.els["sl-sec-badge-queue"].textContent, "3 waiting");
    assert.match(d.els["sl-sec-badge-queue"].className, /sl-tone-warn/);
    assert.equal(d.els.focusCalls, 0);
    delete globalThis.document;
  });
  test("alert badge text is in the closed summary html", () => {
    const h = m.slSecHtml({ key: "wash", title: "Realized gains & wash sales", badges: [{ text: "warning: drift 2", tone: "warn" }], open: false, body: "" });
    assert.match(h, /<summary[\s\S]*warning: drift 2[\s\S]*<\/summary>/);
  });
  test("storage throwing never throws", async () => {
    setStore({ getItem() { throw new Error("no"); }, setItem() { throw new Error("no"); } });
    globalThis.document = secDoc(["queue"]);
    assert.doesNotThrow(() => m.slSecUpdate("queue", { count: 1, tone: "warn", text: "1" }));
    assert.doesNotThrow(() => m.slOnSummaryClick("queue"));
    await tick();
    assert.doesNotThrow(() => m.slSecAll("fix", false));
    delete globalThis.document;
  });
  test("storage off: the active tab is kept in memory; slSecAll with no tab acts on it", () => {
    setStore({ getItem() { throw new Error("no"); }, setItem() { throw new Error("no"); } });
    const d = secDoc(["log", "ledger"]); globalThis.document = d;
    m.slSetTab("ledger");
    assert.equal(m.slCurrentTab(), "ledger");
    assert.equal(window.slCurrentTab, m.slCurrentTab);
    m.slSecAll(null, true);
    assert.equal(d.els["sl-sec-ledger"].open, true);
    assert.equal(d.els["sl-sec-log"].open, false); // the Fix tab is not touched
    m.slSetTab("fix");
    assert.equal(m.slCurrentTab(), "fix");
    delete globalThis.document;
  });
  test("a fresh store starts from the stored tab, not a tab chosen under another store", () => {
    setStore(store()); globalThis.document = secDoc([]);
    m.slSetTab("tax");
    assert.equal(m.slCurrentTab(), "tax");
    const s = store(); setStore(s);
    assert.equal(m.slCurrentTab(), "fix");
    m.slUiSave({ tab: "ledger", sections: {}, taxableOnly: true }, s);
    assert.equal(m.slCurrentTab(), "ledger");
    delete globalThis.document;
  });
  test("slSecAll collapse leaves alerting sections open; expand opens all", () => {
    setStore(store()); const d = secDoc(["queue", "health"]); globalThis.document = d;
    for (const k of ["queue", "health"]) d.els[`sl-sec-${k}`].open = true;
    m.slPublish("queue", { count: 2, tone: "warn", text: "2 waiting" });
    m.slPublish("health", { count: 0, tone: "", text: "" });
    m.slSecAll("fix", false);
    assert.equal(d.els["sl-sec-queue"].open, true);
    assert.equal(d.els["sl-sec-health"].open, false);
    m.slSecAll("fix", true);
    assert.equal(d.els["sl-sec-health"].open, true);
    delete globalThis.document;
  });
  test("slGo('tax','b1099') opens the 1099-B section shell like any other section", () => {
    setStore(store()); const d = secDoc(["b1099"]); globalThis.document = d;
    globalThis.history = { replaceState() {} };
    try {
      m.slGo("tax", "b1099");
      assert.equal(d.els["sl-sec-b1099"].open, true);
    } finally { delete globalThis.document; }
  });
  test("slGo rejects an unknown tab, tolerates no document, records the opened section", () => {
    const s = store(); setStore(s); const d = secDoc(["wash"]); globalThis.document = d;
    globalThis.history = { replaceState(_a, _b, u) { this.url = u; } };
    m.slPublish("wash", { count: 0, tone: "", text: "" });
    m.slGo("bogus", "wash");
    assert.equal(globalThis.history.url, undefined);
    d.els["sl-sec-wash"].querySelector = () => null;
    m.slGo("tax", "wash");
    assert.deepEqual(m.slUiLoad(s).sections.wash, { open: true, lastAlertCount: 0 });
    delete globalThis.document;
    assert.doesNotThrow(() => m.slGo("tax", "wash"));
    delete globalThis.history;
  });
  test("informational counts (row totals) are not alerts: collapse-all closes, user collapse sticks, no announcement", async () => {
    const s = store(); setStore(s); const d = secDoc(["health"]); globalThis.document = d;
    d.els["sl-sec-health"].open = true;
    m.slPublish("health", { count: 12, tone: "", text: "12 rows" });
    m.slSecAll("fix", false);
    assert.equal(d.els["sl-sec-health"].open, false);
    assert.equal(m.slUiLoad(s).sections.health.lastAlertCount, 0);
    d.els.slLive.textContent = "";
    m.slPublish("health", { count: 13, tone: "", text: "13 rows" });
    assert.equal(d.els["sl-sec-health"].open, false);
    assert.equal(d.els.slLive.textContent, "");
    delete globalThis.document;
  });
  test("a summary update never closes an open section (2 -> 3 -> 2 -> 0)", async () => {
    const s = store(); setStore(s); const d = secDoc(["queue"]); globalThis.document = d;
    m.slUiSave(m.slUiRecordToggle(m.slUiLoad(s), "queue", false, 2), s);
    m.slPublish("queue", { count: 3, tone: "warn", text: "3 waiting" });
    assert.equal(d.els["sl-sec-queue"].open, true);
    m.slPublish("queue", { count: 2, tone: "warn", text: "2 waiting" });
    assert.equal(d.els["sl-sec-queue"].open, true);
    m.slPublish("queue", { count: 0, tone: "", text: "" });
    assert.equal(d.els["sl-sec-queue"].open, true);
    delete globalThis.document;
  });
});

