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
