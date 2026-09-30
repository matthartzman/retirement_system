// UX-004 (system review 2026-09-25, Wave 5 item WI-502): the static dialogs
// declared in index.html -- #exitModal (the unsaved-changes exit decision)
// and #chartModal (enlarged chart) -- carried role=dialog/aria-modal but were
// opened and closed by toggling style.display alone: focus stayed behind the
// backdrop, Tab walked out into the page, Escape did nothing (exit) and focus
// was never restored. They now go through openStaticDialog()/
// closeStaticDialog(). These tests drive the real production functions
// (load_dashboard.mjs vm sandbox) against a small DOM stub.

import { test, describe, beforeEach } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const INDEX_HTML = fs.readFileSync(path.join(HERE, "..", "..", "frontend", "index.html"), "utf8");

const sandbox = loadDashboardSandbox();

function focusable(name, doc) {
  return {
    name,
    focus() {
      doc.activeElement = this;
    },
  };
}

let doc;
let listeners;

function makeModal(id, buttons, initialSelector) {
  const modal = {
    id,
    style: { display: "none" },
    buttons,
    querySelector(sel) {
      if (sel === initialSelector) return buttons[0];
      return buttons[0] || null;
    },
    querySelectorAll() {
      return buttons;
    },
  };
  return modal;
}

beforeEach(() => {
  listeners = [];
  doc = {
    activeElement: null,
    body: { classList: { add() {}, remove() {} } },
    addEventListener(type, fn) {
      listeners.push([type, fn]);
    },
    removeEventListener(type, fn) {
      listeners = listeners.filter(([t, f]) => !(t === type && f === fn));
    },
  };
  const keep = focusable("Keep Editing", doc);
  const discard = focusable("Discard & Exit", doc);
  const save = focusable("Save & Exit", doc);
  const close = focusable("Close", doc);
  const exitModal = makeModal("exitModal", [keep, discard, save], ".exit-keep-editing");
  const chartModal = makeModal("chartModal", [close], ".chart-modal-close");
  const byId = {
    exitModal,
    chartModal,
    chartModalTitle: { textContent: "" },
    chartModalBody: { innerHTML: "" },
  };
  doc.getElementById = (id) => byId[id] || null;
  sandbox.document = doc;
});

function press(key, shiftKey = false) {
  const ev = {
    key,
    shiftKey,
    prevented: false,
    preventDefault() {
      this.prevented = true;
    },
  };
  for (const [t, fn] of listeners.slice()) if (t === "keydown") fn(ev);
  return ev;
}

describe("exit modal (WF-11 exit with unsaved changes)", () => {
  test("opening moves focus inside the dialog, onto Keep Editing", () => {
    const opener = focusable("Exit", doc);
    opener.focus();
    sandbox.openExitModal();
    const modal = doc.getElementById("exitModal");
    assert.equal(modal.style.display, "flex");
    assert.equal(doc.activeElement.name, "Keep Editing");
  });

  test("Escape closes it and returns focus to the Exit button", () => {
    const opener = focusable("Exit", doc);
    opener.focus();
    sandbox.openExitModal();
    press("Escape");
    assert.equal(doc.getElementById("exitModal").style.display, "none");
    assert.equal(doc.activeElement, opener);
    assert.equal(listeners.length, 0, "keydown listener must be removed on close");
  });

  test("Tab from the last button wraps to the first instead of leaving the dialog", () => {
    focusable("Exit", doc).focus();
    sandbox.openExitModal();
    const modal = doc.getElementById("exitModal");
    modal.buttons[2].focus(); // Save & Exit
    const ev = press("Tab");
    assert.equal(ev.prevented, true);
    assert.equal(doc.activeElement.name, "Keep Editing");
    const back = press("Tab", true);
    assert.equal(back.prevented, true);
    assert.equal(doc.activeElement.name, "Save & Exit");
  });

  test("closing via Keep Editing (closeExitModal) also restores focus and unhooks", () => {
    const opener = focusable("Exit", doc);
    opener.focus();
    sandbox.openExitModal();
    sandbox.closeExitModal();
    assert.equal(doc.activeElement, opener);
    assert.equal(listeners.length, 0);
  });
});

describe("chart modal", () => {
  test("open focuses Close; Escape closes and restores focus to the chart button", () => {
    const opener = focusable("Enlarge chart", doc);
    opener.focus();
    const id = sandbox.cacheChart("<svg></svg>", "Net worth");
    sandbox.openCachedChart(id);
    const modal = doc.getElementById("chartModal");
    assert.equal(modal.style.display, "flex");
    assert.equal(doc.activeElement.name, "Close");
    press("Escape");
    assert.equal(modal.style.display, "none");
    assert.equal(doc.activeElement, opener);
    assert.equal(listeners.length, 0);
  });
});

describe("index.html static dialog markup", () => {
  test("the unused #pathModal markup is gone", () => {
    assert.ok(!INDEX_HTML.includes('id="pathModal"'));
  });

  test("Keep Editing is the exit dialog's identifiable safe default", () => {
    assert.match(INDEX_HTML, /class="btn exit-keep-editing"[^>]*>Keep Editing</);
  });
});
