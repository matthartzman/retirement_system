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
  const DEFAULTS = { tab: "fix", sections: {}, density: "" };
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
    const st = { tab: "tax", sections: { queue: { open: false, lastAlertCount: 3 } }, density: "compact" };
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
});

describe("tabs and hash", () => {
  test("SL_TABS", () => {
    assert.deepEqual(m.SL_TABS.map((t) => t[0]), ["fix", "ledger", "tax", "import"]);
  });
  test("slUiSetTab", () => {
    assert.equal(m.slUiSetTab({ tab: "fix", sections: {}, density: "" }, "import").tab, "import");
    assert.equal(m.slUiSetTab({ tab: "fix", sections: {}, density: "" }, "bogus").tab, "fix");
  });
  test("slParseHash", () => {
    assert.deepEqual(m.slParseHash("#sales_ledger?tab=import&sec=queue"), { tab: "import", sec: "queue" });
    assert.deepEqual(m.slParseHash("#sales_ledger?tab=zzz&sec=queue"), { tab: null, sec: "queue" });
    assert.deepEqual(m.slParseHash("#other"), { tab: null, sec: null });
    assert.deepEqual(m.slParseHash(""), { tab: null, sec: null });
  });
});

describe("slSecOpen / slUiRecordToggle", () => {
  const st = (e) => ({ tab: "fix", sections: e ? { q: e } : {}, density: "" });
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
    assert.equal((h.match(/tabindex="-1"/g) || []).length, 3);
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
    assert.ok(press("ArrowRight", "import")); assert.equal(active(), "fix");
    press("ArrowLeft", "fix"); assert.equal(active(), "import");
    press("Home", "tax"); assert.equal(active(), "fix");
    press("End", "tax"); assert.equal(active(), "import");
    assert.equal(doc.els["sl-t-import"].focused, true);
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
    queue: S(3, "bad", "3 waiting"), health: S(2, "warn", "drift: 2 accounts"), log: S(0, "", "never run"),
    cash: S(1, "warn", "1 to review"), wash: S(0, "", ""), cf: S(0, "", ""), b1099: S(0, "", ""), imports: S(0, "", "")
  });
  test("strip lists queue, drift, log-not-started and cash items as text-only badges", () => {
    const h = m.slStripHtml(fixture());
    assert.match(h, /<nav aria-label="Needs attention"/);
    for (const t of ["3 waiting", "drift: 2 accounts", "never run", "1 to review"]) assert.ok(h.includes(t), t);
    assert.ok(h.includes('href="#sales_ledger?tab=fix&amp;sec=queue"') || h.includes('href="#sales_ledger?tab=fix&sec=queue"'));
    assert.ok(h.includes('data-go="fix:queue"') && h.includes("slGo('fix','queue');return false"));
    assert.ok(!h.includes("data-go=\"tax:wash\""));
  });
  test("key to tab mapping", () => {
    const all = Object.fromEntries(["queue", "health", "log", "wash", "cf", "b1099", "cash", "imports"].map((k) => [k, S(1, "warn", "x " + k)]));
    const h = m.slStripHtml(all);
    for (const [k, t] of [["queue", "fix"], ["health", "fix"], ["log", "fix"], ["cash", "fix"], ["wash", "tax"], ["cf", "tax"], ["b1099", "import"], ["imports", "import"]]) {
      assert.ok(h.includes(`data-go="${t}:${k}"`), k);
    }
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
  test("slMarkers sums per tab, tone bad wins, empty tabs omitted", () => {
    const mk = m.slMarkers(fixture());
    assert.deepEqual(mk.fix, { count: 6, tone: "bad" });
    assert.equal(mk.tax, undefined);
    assert.equal(mk.import, undefined);
    const mk2 = m.slMarkers({ wash: S(2, "warn", "w"), cf: S(1, "warn", "c"), b1099: S(4, "bad", "b") });
    assert.deepEqual(mk2.tax, { count: 3, tone: "warn" });
    assert.deepEqual(mk2.import, { count: 4, tone: "bad" });
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
    assert.equal(globalThis.history.url, "#sales_ledger?tab=tax&sec=wash");
    const sum = { focus() { this.focused = true; } };
    d.els["sl-sec-wash"] = { open: false, querySelector: () => sum };
    m.slGo("tax", "wash");
    assert.equal(d.els["sl-sec-wash"].open, true);
    assert.equal(sum.focused, true);
    globalThis.history.url = null;
    m.slGo("tax", "bogus");
    assert.equal(globalThis.history.url, "#sales_ledger?tab=tax");
    delete globalThis.document; delete globalThis.history;
  });
});
