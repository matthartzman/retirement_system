// UX-001 (system review 2026-09-25, Wave 5 item WI-501): dashboard.js's
// document-level capture-phase keydown handler, moveToNextEntry(), used to
// act on every input/select/button/textarea on the page. It called
// preventDefault() on Enter (so a focused button could only be activated
// with Space) and on Tab, and for any element NOT in focusableEntries() it
// sent focus to the second header button -- including out of an open
// confirm dialog, whose own bubble-phase Tab trap never got a chance.
//
// It is now scoped to the curated data-entry controls only. These tests run
// the real handler from the production source (load_dashboard.mjs vm
// sandbox) against stub elements and a stub focusableEntries() list.

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();
// Run the deferred focus move synchronously so assertions can see it.
sandbox.setTimeout = (fn) => {
  fn();
  return 0;
};

function el(tag, opts = {}) {
  const e = {
    tagName: tag.toUpperCase(),
    type: opts.type || "",
    focused: 0,
    classList: { contains: (c) => (opts.classes || []).includes(c) },
    matches(sel) {
      return sel.split(",").map((s) => s.trim()).includes(tag);
    },
    closest(sel) {
      if (opts.inDialog && /role="dialog"|aria-modal/.test(sel)) return {};
      return null;
    },
    focus() {
      this.focused += 1;
    },
    select() {},
  };
  return e;
}

function keydown(target, key, extra = {}) {
  const ev = {
    key,
    target,
    shiftKey: !!extra.shiftKey,
    defaultPrevented: !!extra.defaultPrevented,
    prevented: false,
    preventDefault() {
      this.prevented = true;
    },
  };
  sandbox.moveToNextEntry(ev);
  return ev;
}

function withEntries(list) {
  sandbox.window.RetirementNavigation = { focusableEntries: () => list };
}

describe("moveToNextEntry only advances between curated data-entry fields", () => {
  test("Tab on a field input moves focus to the next listed entry", () => {
    const a = el("input");
    const b = el("input");
    withEntries([a, b]);
    const ev = keydown(a, "Tab");
    assert.equal(ev.prevented, true);
    assert.equal(b.focused, 1);
  });

  test("Enter on a field select advances too", () => {
    const a = el("select");
    const b = el("input");
    withEntries([a, b]);
    const ev = keydown(a, "Enter");
    assert.equal(ev.prevented, true);
    assert.equal(b.focused, 1);
  });

  test("Enter on a button is left alone so the button activates natively", () => {
    const btn = el("button");
    const next = el("input");
    // Even a button that IS in the curated list (header/pane-actions) must
    // not have Enter swallowed.
    withEntries([btn, next]);
    const ev = keydown(btn, "Enter");
    assert.equal(ev.prevented, false);
    assert.equal(next.focused, 0);
  });

  test("Tab on a left-nav step button keeps native Tab order", () => {
    const stepBtn = el("button");
    const header = el("button");
    withEntries([header, el("input")]);
    const ev = keydown(stepBtn, "Tab");
    assert.equal(ev.prevented, false);
    assert.equal(header.focused, 0, "focus must not jump to a header button");
  });

  test("an input outside the curated list (e.g. the nav search box) keeps native Tab", () => {
    const search = el("input");
    const header1 = el("button");
    const header2 = el("button");
    withEntries([header1, header2]);
    const ev = keydown(search, "Tab");
    assert.equal(ev.prevented, false);
    assert.equal(header2.focused, 0, "the old fallback sent focus to f[1]");
  });

  test("Tab inside a dialog is left to the dialog's own focus trap", () => {
    const inDialog = el("input", { inDialog: true });
    const other = el("input");
    withEntries([inDialog, other]);
    const ev = keydown(inDialog, "Tab");
    assert.equal(ev.prevented, false);
    assert.equal(other.focused, 0);
  });

  test("textareas keep native Enter and Tab", () => {
    const ta = el("textarea");
    withEntries([ta, el("input")]);
    assert.equal(keydown(ta, "Enter").prevented, false);
    assert.equal(keydown(ta, "Tab").prevented, false);
  });

  test("Shift+Tab and already-handled events are never touched", () => {
    const a = el("input");
    const b = el("input");
    withEntries([a, b]);
    assert.equal(keydown(a, "Tab", { shiftKey: true }).prevented, false);
    assert.equal(keydown(a, "Tab", { defaultPrevented: true }).prevented, false);
    assert.equal(b.focused, 0);
  });

  test("Tab on the last listed entry falls through to native Tab", () => {
    const a = el("input");
    const last = el("input");
    withEntries([a, last]);
    const ev = keydown(last, "Tab");
    assert.equal(ev.prevented, false);
    assert.equal(last.focused, 0);
  });
});
