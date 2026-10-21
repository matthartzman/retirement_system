// Contextual help panel, Phase 1: the right panel follows the user (page help on arrival,
// section help when a section gets focus or opens, field help on field focus) without
// stealing focus, opens by default only on the pre-build pages, and remembers a close.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

// Minimal DOM: just what help_registry.js touches. Must exist before the module is imported.
const classes = new Set();
const panel = { innerHTML: "" };
const store = {};
let narrow = false;
let activeElement = null;
const listeners = {};
const doc = {
  body: {
    classList: {
      add: (c) => classes.add(c),
      remove: (c) => classes.delete(c),
      contains: (c) => classes.has(c),
      toggle: (c, on) => (on ? classes.add(c) : classes.delete(c)),
    },
  },
  getElementById: (id) => (id === "helpPanel" ? panel : null),
  querySelector: () => null,
  addEventListener: (type, fn) => (listeners[type] = fn),
  get activeElement() {
    return activeElement;
  },
};
const fieldHelpCalls = [];
globalThis.window = {
  document: doc,
  localStorage: { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => (store[k] = String(v)) },
  matchMedia: () => ({ matches: narrow }),
  showFieldHelp: (idx) => fieldHelpCalls.push(idx),
};

const reg = await import("../../frontend/js/help_registry.js");

// A fake element: `closest(sel)` answers from a map of selector -> ancestor element.
function el(tagName, ancestors = {}, attrs = {}) {
  const node = {
    tagName,
    focusCalls: 0,
    focus() {
      this.focusCalls++;
    },
    getAttribute: (k) => (k in attrs ? attrs[k] : null),
    classList: { contains: (c) => (attrs.class || "").split(" ").includes(c) },
    closest: (sel) => (sel in ancestors ? ancestors[sel] : null),
  };
  return node;
}
const mainPane = { id: "mainPane" };

test("open policy: remembered choice wins, pre-build pages open by default, never on narrow screens", () => {
  assert.equal(reg.PRE_BUILD_PAGES.length, 11);
  assert.equal(reg.helpOpenOnArrival("household_people", null, false), true);
  assert.equal(reg.helpOpenOnArrival("strategy_optimize", null, false), false);
  assert.equal(reg.helpOpenOnArrival("household_people", "0", false), false);
  assert.equal(reg.helpOpenOnArrival("strategy_optimize", "1", false), true);
  assert.equal(reg.helpOpenOnArrival("household_people", "1", true), false);
});

test("arrival opens the panel on a pre-build page, re-renders keep pinned field help, force overrides", () => {
  assert.equal(reg.arriveAtPage("household_people"), true);
  assert.ok(classes.has("help-open"));
  reg.pinHelp("field", 7);
  assert.equal(reg.arriveAtPage("household_people"), false, "a re-render must not replace pinned field help");
  assert.deepEqual(reg.helpPanelState(), { step: "household_people", kind: "field", ref: 7 });
  assert.equal(reg.arriveAtPage("household_people", true), true, "an explicit ? / Step Help request rewrites it");
  assert.equal(reg.helpPanelState().kind, "page");
});

test("arrival closes the panel on other pages and after the user closed it", () => {
  assert.equal(reg.arriveAtPage("strategy_optimize"), true);
  assert.equal(classes.has("help-open"), false);
  store.retirementHelpOpen = "0";
  reg.arriveAtPage("income_work");
  assert.equal(classes.has("help-open"), false, "remembered close beats the pre-build default");
  delete store.retirementHelpOpen;
  narrow = true;
  reg.arriveAtPage("holdings");
  assert.equal(classes.has("help-open"), false, "below 1180px the sheet waits for ? or i");
  narrow = false;
});

test("field focus shows field help without opening the panel or moving focus", () => {
  reg.arriveAtPage("household_people", true);
  classes.delete("help-open");
  fieldHelpCalls.length = 0;
  const input = el("INPUT", { "#mainPane": mainPane, '.field[id^="field-"]': { id: "field-12" } });
  reg.onHelpFocusIn({ target: input });
  assert.deepEqual(fieldHelpCalls, [12]);
  assert.equal(classes.has("help-open"), false);
  assert.equal(input.focusCalls, 0);
  reg.pinHelp("field", 12);
  reg.onHelpFocusIn({ target: input });
  assert.deepEqual(fieldHelpCalls, [12], "re-focusing the same field does not rewrite the panel");
  reg.onHelpFocusIn({ target: el("INPUT", { '.field[id^="field-"]': { id: "field-3" } }) });
  assert.deepEqual(fieldHelpCalls, [12], "focus outside the center panel is ignored");
});

test("section focus shows section help; a form control inside a section is left to field help", () => {
  const sec = { getAttribute: () => "household_people.people" };
  panel.innerHTML = "";
  reg.pinHelp("page");
  reg.onHelpFocusIn({ target: el("INPUT", { "#mainPane": mainPane, "[data-help-section]": sec }) });
  assert.equal(panel.innerHTML, "");
  const btn = el("BUTTON", { "#mainPane": mainPane, "[data-help-section]": sec });
  reg.onHelpFocusIn({ target: btn });
  assert.match(panel.innerHTML, /help-title">People</);
  assert.deepEqual(reg.helpPanelState().kind, "section");
  assert.equal(btn.focusCalls, 0);
  assert.equal(classes.has("help-open"), false, "focus never opens the panel");
});

test("a section opening by user toggle shows its help; renderMain's restore does not", () => {
  reg.pinHelp("page");
  panel.innerHTML = "";
  const details = {
    tagName: "DETAILS",
    open: true,
    matches: () => true,
    getAttribute: () => "household_people.tax_survivor",
    contains: (n) => n === "summary",
  };
  activeElement = null;
  reg.onHelpToggle({ target: details });
  assert.equal(panel.innerHTML, "");
  activeElement = "summary";
  reg.onHelpToggle({ target: details });
  assert.match(panel.innerHTML, /State, filing status and survivor/);
  activeElement = null;
});

test("explicit openers (i, ?, section ?) open the panel; the sheet toggle is left to toggleHelpSheet", () => {
  classes.delete("help-open");
  const toggle = el("BUTTON", {}, { class: "help-toggle" });
  reg.onHelpClick({ target: el("SPAN", { '[aria-controls="helpPanel"]': toggle }) });
  assert.equal(classes.has("help-open"), false);
  const info = el("BUTTON", {}, { class: "field-info-i" });
  reg.onHelpClick({ target: el("BUTTON", { '[aria-controls="helpPanel"]': info }) });
  assert.ok(classes.has("help-open"));
  classes.delete("help-open");
  reg.pinHelp("page");
  const secBtn = el("BUTTON", {}, { "data-help-section-btn": "household_people.people" });
  reg.onHelpClick({ target: el("BUTTON", { '[aria-controls="helpPanel"]': secBtn }) });
  assert.ok(classes.has("help-open"));
  assert.equal(reg.helpPanelState().ref, "household_people.people");
});

test("the registry wires follow-focus listeners and field lookups drop the person number", () => {
  for (const t of ["focusin", "toggle", "click", "keydown"]) assert.equal(typeof listeners[t], "function", t);
  assert.ok(window.RPHelp && typeof window.RPHelp.arrive === "function");
  assert.equal(reg.fieldHelpEntry("member_2_mortality_age"), reg.HELP_FIELDS.member_mortality_age);
  assert.equal(reg.fieldHelpEntry("residence_state"), null);
});

test("dashboard wiring: showStepHelp delegates to the registry, ? button, pilot sections, field hook", () => {
  const dash = fs.readFileSync("frontend/js/dashboard.js", "utf8");
  assert.match(dash, /window\.RPHelp\.arrive\(id, force\)/);
  assert.match(dash, /window\.pageHelpButtonHtml\(st\.id\)/);
  for (const key of Object.keys(reg.HELP_SECTIONS)) assert.ok(dash.includes(`data-help-section="${key}"`), key);
  const rowModel = fs.readFileSync("frontend/js/dashboard_decomp_row_model.js", "utf8");
  assert.match(rowModel, /RPHelp\?\.fieldEntry\(row\.label\)/);
  assert.match(rowModel, /window\.RPHelp\.pinned\("field", idx\)/);
});

test("accessibility: labelled panel region, no aria-live chatter, openers use aria-controls", () => {
  const html = fs.readFileSync("frontend/index.html", "utf8");
  const tag = /<div id="helpPanel"[^>]*>/.exec(html)[0];
  assert.match(tag, /role="region"/);
  assert.match(tag, /aria-label="/);
  assert.doesNotMatch(tag, /aria-live/);
  assert.match(reg.pageHelpButtonHtml("household_people"), /aria-controls="helpPanel"/);
  assert.match(reg.sectionHelpButtonHtml("household_people.people"), /aria-controls="helpPanel"/);
  assert.equal(reg.sectionHelpButtonHtml("nope.nope"), "");
  const css = fs.readFileSync("frontend/css/dashboard.css", "utf8");
  assert.match(css, /body\.help-open aside\.card\.help\{transform:translateX\(0\);visibility:visible/);
});
