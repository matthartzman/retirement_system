// Finding UX-105 (system review 2026-09-07, Wave 5 item W5-7): the
// dynamically-built in-app confirm dialogs (showInAppConfirm,
// showSaveDiscardStayModal in dashboard_decomp_row_model.js, and the
// YTD-choice modal in dashboard_decomp_checklist_closeout.js) lacked
// role="dialog"/aria-modal, had no focus trap or focus restore, and leaked
// a `keydown` listener on every non-Escape close (removeEventListener was
// only ever called from inside the Escape branch of the handler).
//
// This test runs the real module source (not a hand-copied fixture)
// against a purpose-built minimal DOM stub -- there is no jsdom/happy-dom
// dependency in this repo, and the existing tests/frontend/load_dashboard.mjs
// sandbox's document stub returns null from every querySelector call by
// design, which these dialog functions cannot run against. The stub here
// is intentionally narrow: just enough class-based querySelector/
// addEventListener bookkeeping to drive showInAppConfirm/
// showSaveDiscardStayModal to completion and count listener churn.
import { test, describe } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const JS_DIR = path.join(__dirname, "..", "..", "frontend", "js");

function loadModuleExports(filename) {
  const src = fs
    .readFileSync(path.join(JS_DIR, filename), "utf8")
    .replace(/^export\s+/gm, "");

  const addedListenerTypes = [];
  const removedListenerTypes = [];
  let lastOverlay = null;

  function makeStubElement() {
    const childCache = new Map();
    const el = {
      className: "",
      _innerHTML: "",
      removed: false,
      focusCalls: 0,
      get innerHTML() {
        return this._innerHTML;
      },
      set innerHTML(html) {
        this._innerHTML = html;
        childCache.clear();
      },
      appendChild() {},
      remove() {
        el.removed = true;
      },
      focus() {
        el.focusCalls++;
      },
      onclick: null,
      querySelector(sel) {
        const cls = sel.replace(/^\./, "");
        if (!el._innerHTML.includes(cls)) return null;
        if (!childCache.has(cls)) {
          childCache.set(cls, { onclick: null, focus() {}, tagName: "BUTTON" });
        }
        return childCache.get(cls);
      },
      querySelectorAll() {
        return [];
      },
    };
    return el;
  }

  const previouslyFocusedStub = { focusCalls: 0, focus() { this.focusCalls++; } };
  const documentStub = {
    activeElement: previouslyFocusedStub,
    body: { appendChild() {} },
    createElement() {
      lastOverlay = makeStubElement();
      return lastOverlay;
    },
    addEventListener(type) {
      addedListenerTypes.push(type);
    },
    removeEventListener(type) {
      removedListenerTypes.push(type);
    },
  };

  const sandbox = {
    document: documentStub,
    esc: (s) => String(s),
    setTimeout: (fn) => fn(),
    console,
  };
  sandbox.globalThis = sandbox;
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  try {
    new vm.Script(src, { filename }).runInContext(sandbox);
  } catch (e) {
    // Mirrors load_dashboard.mjs's own tolerance: this file's top-level
    // code may reach past what this narrow stub provides once execution
    // gets beyond the dialog function(s) under test (function declarations
    // are already hoisted onto the sandbox by the time any later top-level
    // statement could throw).
  }

  return {
    sandbox,
    getLastOverlay: () => lastOverlay,
    getPreviouslyFocusedStub: () => previouslyFocusedStub,
    getListenerBalance: () => ({
      added: addedListenerTypes.filter((t) => t === "keydown").length,
      removed: removedListenerTypes.filter((t) => t === "keydown").length,
    }),
  };
}

describe("showInAppConfirm has dialog semantics and does not leak keydown listeners", () => {
  test("dialog markup declares role=dialog and aria-modal=true", async () => {
    const { sandbox, getLastOverlay } = loadModuleExports("dashboard_decomp_row_model.js");
    const { showInAppConfirm } = sandbox;
    const p = showInAppConfirm("Are you sure?");
    const overlay = getLastOverlay();
    assert.ok(overlay.innerHTML.includes('role="dialog"'), "missing role=dialog");
    assert.ok(overlay.innerHTML.includes('aria-modal="true"'), "missing aria-modal=true");
    overlay.querySelector(".inapp-cancel").onclick();
    await p;
  });

  test("repeated open+close via Confirm/Cancel/backdrop never leaves a dangling keydown listener", async () => {
    const { sandbox, getLastOverlay, getListenerBalance } = loadModuleExports("dashboard_decomp_row_model.js");
    const { showInAppConfirm } = sandbox;
    for (let i = 0; i < 5; i++) {
      const p = showInAppConfirm("Are you sure?");
      const overlay = getLastOverlay();
      // Close via the Confirm button (not Escape) -- the exact path that
      // used to leak, since removeEventListener only ever ran inside the
      // Escape branch.
      overlay.querySelector(".inapp-confirm").onclick();
      await p;
    }
    const balance = getListenerBalance();
    assert.equal(
      balance.added,
      balance.removed,
      `keydown listeners leaked: ${balance.added} added vs ${balance.removed} removed`,
    );
  });

  test("closing restores focus to whatever was focused before the dialog opened", async () => {
    const { sandbox, getLastOverlay, getPreviouslyFocusedStub } = loadModuleExports("dashboard_decomp_row_model.js");
    const { showInAppConfirm } = sandbox;
    const before = getPreviouslyFocusedStub();
    assert.equal(before.focusCalls, 0);
    const p = showInAppConfirm("Are you sure?");
    const overlay = getLastOverlay();
    overlay.querySelector(".inapp-cancel").onclick();
    await p;
    assert.equal(
      before.focusCalls, 1,
      "closing the dialog must call .focus() on the element that had focus before it opened",
    );
  });
});

describe("showSaveDiscardStayModal has dialog semantics and does not leak keydown listeners", () => {
  test("dialog markup declares role=dialog and aria-modal=true", async () => {
    const { sandbox, getLastOverlay } = loadModuleExports("dashboard_decomp_row_model.js");
    const { showSaveDiscardStayModal } = sandbox;
    const p = showSaveDiscardStayModal("Unsaved changes");
    const overlay = getLastOverlay();
    assert.ok(overlay.innerHTML.includes('role="dialog"'), "missing role=dialog");
    assert.ok(overlay.innerHTML.includes('aria-modal="true"'), "missing aria-modal=true");
    overlay.querySelector(".sds-stay").onclick();
    await p;
  });

  test("repeated open+close via Save/Discard/Stay never leaves a dangling keydown listener", async () => {
    const { sandbox, getLastOverlay, getListenerBalance } = loadModuleExports("dashboard_decomp_row_model.js");
      const { showSaveDiscardStayModal } = sandbox;
    for (let i = 0; i < 5; i++) {
      const p = showSaveDiscardStayModal("Unsaved changes");
      const overlay = getLastOverlay();
      overlay.querySelector(".sds-discard").onclick();
      await p;
    }
    const balance = getListenerBalance();
    assert.equal(
      balance.added,
      balance.removed,
      `keydown listeners leaked: ${balance.added} added vs ${balance.removed} removed`,
    );
  });

  test("closing restores focus to whatever was focused before the dialog opened", async () => {
    const { sandbox, getLastOverlay, getPreviouslyFocusedStub } = loadModuleExports("dashboard_decomp_row_model.js");
    const { showSaveDiscardStayModal } = sandbox;
    const before = getPreviouslyFocusedStub();
    const p = showSaveDiscardStayModal("Unsaved changes");
    const overlay = getLastOverlay();
    overlay.querySelector(".sds-stay").onclick();
    await p;
    assert.equal(
      before.focusCalls, 1,
      "closing the dialog must call .focus() on the element that had focus before it opened",
    );
  });
});

describe("showYtdBlendChoiceModal has dialog semantics and does not leak keydown listeners", () => {
  test("dialog markup declares role=dialog and aria-modal=true", async () => {
    const { sandbox, getLastOverlay } = loadModuleExports("dashboard_decomp_checklist_closeout.js");
    const { showYtdBlendChoiceModal } = sandbox;
    const p = showYtdBlendChoiceModal({ actual: {}, ytd_end: "2026-06-30" });
    const overlay = getLastOverlay();
    assert.ok(overlay.innerHTML.includes('role="dialog"'), "missing role=dialog");
    assert.ok(overlay.innerHTML.includes('aria-modal="true"'), "missing aria-modal=true");
    overlay.querySelector(".ytd-choice-cancel").onclick();
    await p;
  });

  test("repeated open+close via Blend/Hypothetical/Cancel never leaves a dangling keydown listener", async () => {
    const { sandbox, getLastOverlay, getListenerBalance } = loadModuleExports("dashboard_decomp_checklist_closeout.js");
    const { showYtdBlendChoiceModal } = sandbox;
    for (let i = 0; i < 5; i++) {
      const p = showYtdBlendChoiceModal({ actual: {}, ytd_end: "2026-06-30" });
      const overlay = getLastOverlay();
      overlay.querySelector(".ytd-choice-blend").onclick();
      await p;
    }
    const balance = getListenerBalance();
    assert.equal(
      balance.added,
      balance.removed,
      `keydown listeners leaked: ${balance.added} added vs ${balance.removed} removed`,
    );
  });

  test("closing restores focus to whatever was focused before the dialog opened", async () => {
    const { sandbox, getLastOverlay, getPreviouslyFocusedStub } = loadModuleExports("dashboard_decomp_checklist_closeout.js");
    const { showYtdBlendChoiceModal } = sandbox;
    const before = getPreviouslyFocusedStub();
    const p = showYtdBlendChoiceModal({ actual: {}, ytd_end: "2026-06-30" });
    const overlay = getLastOverlay();
    overlay.querySelector(".ytd-choice-cancel").onclick();
    await p;
    assert.equal(
      before.focusCalls, 1,
      "closing the dialog must call .focus() on the element that had focus before it opened",
    );
  });
});
