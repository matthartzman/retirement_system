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
