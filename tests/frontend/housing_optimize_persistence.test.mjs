// Input persistence (design 2026-09-16 §9.6, Task 15).
//
// The design plan's own version of this file imports HOUSING_OPT_STORAGE_KEY,
// loadHousingOptInputs, saveHousingOptInputs and renderHousingOptimizePanelHtml
// directly from dashboard_decomp_housing_optimizer.js, and mounts the panel
// via a mountHousingOptPanel() helper. Neither import style works: that file
// is not a standalone ES module (see housing_optimize_results.test.mjs's
// header), and there is no real DOM in this repo's test setup for a
// mountHousingOptPanel() helper to mount into (no jsdom dependency exists --
// see load_dashboard.mjs). This file follows the same corrected pattern as
// Tasks 12-14: load the real production source via loadDashboardSandbox()
// and exercise the exported functions directly off the sandbox object.
//
// renderHousingOptimizePanelHtml() returns an HTML *string* -- it has no live
// DOM to restore values into even in the real app, since the caller has not
// yet assigned that string into innerHTML by the time the function returns.
// Persistence therefore has two independently-testable halves:
//   - saveHousingOptInputs() reads real DOM (via document.getElementById /
//     el.querySelectorAll), which these tests stub the same way
//     reports_and_review_restructure.test.mjs stubs querySelectorAll for
//     setAppControls().
//   - renderHousingOptimizePanelHtml() restores by patching the *markup it
//     is about to return* against what saveHousingOptInputs() persisted, so
//     these tests read the returned string the same way
//     housing_optimize_panel.test.mjs does, rather than a live element.
//
// The assertions below are the plan's own (a round trip survives a
// save-then-render, results are never part of what is saved or restored, a
// corrupt or unavailable payload degrades to defaults without throwing, and
// an unknown stored key is silently ignored) -- only how the panel's state is
// produced and inspected differs from the plan's non-working sketch.

import { test } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

function fakeLocalStorage(initial = {}) {
  const store = new Map(Object.entries(initial));
  return {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, String(v)),
    removeItem: (k) => store.delete(k),
  };
}

// Locates the single element carrying id="id" in a rendered panel string --
// its whole <select>...</select> block if it is a select, otherwise just its
// opening tag -- mirroring how the production hydration code itself finds it.
function tagFor(html, id) {
  const idx = html.indexOf(`id="${id}"`);
  assert.ok(idx !== -1, `id="${id}" not found in rendered panel html`);
  const start = html.lastIndexOf("<", idx);
  const isSelect = /^<select/i.test(html.slice(start, start + 8));
  const end = isSelect
    ? html.indexOf("</select>", idx) + "</select>".length
    : html.indexOf(">", idx) + 1;
  return html.slice(start, end);
}

function attrValue(html, id, attr) {
  const openTag = tagFor(html, id).match(/^<[^>]*>/)[0];
  const m = new RegExp(`${attr}="([^"]*)"`).exec(openTag);
  return m ? m[1] : null;
}

function hasBooleanAttr(html, id, attr) {
  const openTag = tagFor(html, id).match(/^<[^>]*>/)[0];
  return new RegExp(`[ "]${attr}(=|>| |$)`).test(openTag);
}

function selectedOptionValue(html, id) {
  const m = /<option\s+value="([^"]*)"[^>]*\sselected/.exec(tagFor(html, id));
  return m ? m[1] : null;
}

// A minimal stand-in for the real <details id="housingOptPanel"> element
// saveHousingOptInputs() scopes its querySelectorAll("[id]") to. `fields` is
// the list of form controls "currently on screen" for the test to save.
function fakePanelRoot(fields, open = false) {
  return {
    open,
    querySelectorAll: (sel) => (sel === "[id]" ? fields : []),
  };
}

function wireDom(sandbox, root, resultsStub) {
  const PANEL_ID = sandbox.window.HOUSING_OPT_PANEL_ID;
  sandbox.document.getElementById = (id) => {
    if (id === PANEL_ID) return root;
    if (id === "housingOptimizeResults") return resultsStub || { id: "housingOptimizeResults" };
    return null;
  };
}

test("inputs survive a save-then-render round trip", () => {
  const sandbox = loadDashboardSandbox();
  sandbox.localStorage = fakeLocalStorage();
  const root = fakePanelRoot([
    { id: "housingOptMove1Earliest", tagName: "INPUT", type: "number", value: "2037" },
    { id: "housingOptPresenceZip", tagName: "INPUT", type: "text", value: "60521" },
  ]);
  wireDom(sandbox, root);

  sandbox.saveHousingOptInputs();
  const html = sandbox.renderHousingOptimizePanelHtml();
  assert.equal(attrValue(html, "housingOptMove1Earliest", "value"), "2037");
  assert.equal(attrValue(html, "housingOptPresenceZip", "value"), "60521");
});

test("a checkbox and a select round-trip too", () => {
  const sandbox = loadDashboardSandbox();
  sandbox.localStorage = fakeLocalStorage();
  const root = fakePanelRoot([
    { id: "housingOptMove2Enabled", tagName: "INPUT", type: "checkbox", checked: true },
    { id: "housingOptObjective", tagName: "SELECT", value: "lifetime_cost" },
  ]);
  wireDom(sandbox, root);

  sandbox.saveHousingOptInputs();
  const html = sandbox.renderHousingOptimizePanelHtml();
  assert.ok(hasBooleanAttr(html, "housingOptMove2Enabled", "checked"));
  assert.equal(selectedOptionValue(html, "housingOptObjective"), "lifetime_cost");
});

test("a restored Move 2 enabled checkbox also un-hides the Move 2 fields block", () => {
  // Regression: restoring `checked` on housingOptMove2Enabled via markup
  // patching does not fire its onchange handler, so
  // toggleHousingOptMove2Fields() never runs on its own -- without this,
  // reopening the panel after a save with Move 2 enabled left the checkbox
  // showing checked while #housingOptMove2Fields stayed hidden, even though
  // the fields underneath still held real values and were submitted with
  // the next run.
  const sandbox = loadDashboardSandbox();
  sandbox.localStorage = fakeLocalStorage();
  const root = fakePanelRoot([
    { id: "housingOptMove2Enabled", tagName: "INPUT", type: "checkbox", checked: true },
  ]);
  wireDom(sandbox, root);

  sandbox.saveHousingOptInputs();
  const html = sandbox.renderHousingOptimizePanelHtml();
  assert.ok(hasBooleanAttr(html, "housingOptMove2Enabled", "checked"));
  assert.ok(!hasBooleanAttr(html, "housingOptMove2Fields", "hidden"));
});

test("the <details> open state round-trips", () => {
  const sandbox = loadDashboardSandbox();
  sandbox.localStorage = fakeLocalStorage();
  const root = fakePanelRoot([], /* open */ true);
  wireDom(sandbox, root);

  sandbox.saveHousingOptInputs();
  const html = sandbox.renderHousingOptimizePanelHtml();
  assert.ok(hasBooleanAttr(html, sandbox.window.HOUSING_OPT_PANEL_ID, "open"));
});

test("results are never part of what is saved or what is restored", () => {
  const sandbox = loadDashboardSandbox();
  sandbox.localStorage = fakeLocalStorage();
  const root = fakePanelRoot([
    { id: "housingOptMove1Earliest", tagName: "INPUT", type: "number", value: "2037" },
  ]);
  wireDom(sandbox, root);

  sandbox.saveHousingOptInputs();
  const stored = JSON.parse(sandbox.localStorage.getItem(sandbox.window.HOUSING_OPT_STORAGE_KEY));
  assert.ok(!("results" in stored));
  assert.ok(!("candidates" in stored));

  const html = sandbox.renderHousingOptimizePanelHtml();
  assert.match(html, /id="housingOptimizeResults"><\/div>/);
});

test("a form control living inside the results container is never saved, even if it looks like one", () => {
  const sandbox = loadDashboardSandbox();
  sandbox.localStorage = fakeLocalStorage();
  const staleInput = {
    id: "housingOptStaleResultInput",
    tagName: "INPUT",
    type: "text",
    value: "stale-recommendation",
  };
  const resultsStub = { id: "housingOptimizeResults", contains: (el) => el === staleInput };
  const root = fakePanelRoot([staleInput]);
  wireDom(sandbox, root, resultsStub);

  sandbox.saveHousingOptInputs();
  const stored = JSON.parse(sandbox.localStorage.getItem(sandbox.window.HOUSING_OPT_STORAGE_KEY));
  assert.ok(!("housingOptStaleResultInput" in stored));
});

test("an unparseable payload falls back to defaults rather than throwing", () => {
  const sandbox = loadDashboardSandbox();
  sandbox.localStorage = fakeLocalStorage({
    [sandbox.window.HOUSING_OPT_STORAGE_KEY]: "{not json",
  });
  assert.doesNotThrow(() => sandbox.loadHousingOptInputs());
  // A cross-realm {} (this object was created inside the vm sandbox, not in
  // this file's own realm) is not === deepStrictEqual to a same-realm {} --
  // its prototype chain differs -- so the fallback shape is checked directly
  // rather than via assert.deepEqual.
  assert.equal(Object.keys(sandbox.loadHousingOptInputs()).length, 0);
  assert.doesNotThrow(() => sandbox.renderHousingOptimizePanelHtml());
});

test("an unknown key is ignored so the shape can grow without a migration", () => {
  const sandbox = loadDashboardSandbox();
  sandbox.localStorage = fakeLocalStorage({
    [sandbox.window.HOUSING_OPT_STORAGE_KEY]: JSON.stringify({
      housingOptMove1Earliest: 2037,
      somethingRemoved: "x",
    }),
  });
  let html;
  assert.doesNotThrow(() => {
    html = sandbox.renderHousingOptimizePanelHtml();
  });
  assert.equal(attrValue(html, "housingOptMove1Earliest", "value"), "2037");
});

test("unavailable storage degrades silently on both save and load", () => {
  const sandbox = loadDashboardSandbox();
  const root = fakePanelRoot([
    { id: "housingOptMove1Earliest", tagName: "INPUT", type: "number", value: "2037" },
  ]);
  wireDom(sandbox, root);
  Object.defineProperty(sandbox, "localStorage", {
    configurable: true,
    get() {
      throw new Error("blocked");
    },
  });

  assert.doesNotThrow(() => sandbox.saveHousingOptInputs());
  assert.equal(Object.keys(sandbox.loadHousingOptInputs()).length, 0);
  assert.doesNotThrow(() => sandbox.renderHousingOptimizePanelHtml());
});
