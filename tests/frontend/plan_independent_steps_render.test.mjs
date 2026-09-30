// UX-008 (system review 2026-09-25, Wave 5 item WI-508): navigation.js's
// PLAN_INDEPENDENT_STEPS lists workbook_formatting, so setStep() lets it
// open before a plan is loaded -- but renderMain() kept its own inline copy
// of that list, without workbook_formatting, and rendered the Plan Status
// welcome screen instead. The nav's step-button disable check kept a third
// copy. All three now read the one list.
//
// Runs the real renderMain()/renderSteps() (load_dashboard.mjs sandbox) with
// window.RetirementNavigation taken from the real navigation.js.

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const JS = path.join(HERE, "..", "..", "frontend", "js");

function realNavigation() {
  const noop = () => {};
  const box = {
    console,
    setTimeout: () => 0,
    clearTimeout: noop,
    localStorage: { getItem: () => null, setItem: noop, removeItem: noop },
    document: { getElementById: () => null, querySelector: () => null, querySelectorAll: () => [], addEventListener: noop },
  };
  box.window = box;
  box.globalThis = box;
  vm.createContext(box);
  vm.runInContext(fs.readFileSync(path.join(JS, "navigation.js"), "utf8"), box);
  return box.window.RetirementNavigation;
}

const NAV = realNavigation();
const sandbox = loadDashboardSandbox();
const run = (code) => vm.runInContext(code, sandbox);
sandbox.window.RetirementNavigation = NAV;

function renderWith(step) {
  const noop = () => {};
  const els = {};
  const el = (id) =>
    (els[id] ||= {
      id,
      innerHTML: "",
      textContent: "",
      style: {},
      classList: { add: noop, remove: noop, toggle: noop, contains: () => false },
      setAttribute: noop,
      querySelectorAll: () => [],
      querySelector: () => null,
      addEventListener: noop,
    });
  sandbox.document.getElementById = el;
  run(`planLoaded = false; activeStep = ${JSON.stringify(step)};`);
  try {
    run("renderMain()");
  } catch (_e) {
    // Post-render chrome (help pane, focus restore) may reach past these
    // stubs; #mainPane is written before any of that runs.
  }
  return { main: el("mainPane").innerHTML, steps: el("steps").innerHTML };
}

describe("plan-independent steps render the same set the router allows", () => {
  test("renderMain reads navigation.js's list (no drifting inline copy)", () => {
    assert.deepEqual([...sandbox.planIndependentSteps()], [...NAV.PLAN_INDEPENDENT_STEPS]);
    assert.ok(NAV.PLAN_INDEPENDENT_STEPS.includes("workbook_formatting"));
  });

  test("with no plan loaded, workbook_formatting renders Workbook Formatting, not the welcome screen", () => {
    const welcome = sandbox.renderWelcome();
    const { main } = renderWith("workbook_formatting");
    assert.match(main, /workbook-format-panel/);
    assert.ok(!main.includes(welcome), "renderMain fell back to renderWelcome()");
  });

  test("with no plan loaded, a plan-dependent step still shows the welcome screen", () => {
    const { main } = renderWith("household_people");
    assert.ok(main.includes(sandbox.renderWelcome()));
  });

  test("the Workbook Formatting nav button is enabled before a plan is open", () => {
    const { steps } = renderWith("workbook_formatting");
    const btn = steps.match(/<button class="stepbtn[^"]*" type="button" data-step-id="workbook_formatting"[^>]*>/);
    assert.ok(btn, "workbook_formatting step button not rendered");
    assert.doesNotMatch(btn[0], /\sdisabled/);
  });
});
