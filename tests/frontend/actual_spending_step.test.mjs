// #338 W-C task C5: "Actual Spending (This Year)" (ytd_transactions) and
// "Spending Analysis" (spending_dashboard) merge into one visible step,
// actual_spending, under Reports & Review -- two tabs, "This year" and
// "Analysis". The reports_and_review hub is retitled "Build & Results", and
// the residual "Reports" group string is gone.

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const JS = path.join(HERE, "..", "..", "frontend", "js");

function loadNavigation() {
  const noop = () => {};
  const sandbox = {
    console,
    setTimeout: (fn) => {
      try {
        fn();
      } catch (_e) {}
      return 0;
    },
    clearTimeout: noop,
    localStorage: { getItem: () => null, setItem: noop, removeItem: noop },
    document: { getElementById: () => null, querySelector: () => null, querySelectorAll: () => [], addEventListener: noop },
  };
  sandbox.window = sandbox;
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(path.join(JS, "navigation.js"), "utf8"), sandbox);
  return sandbox;
}

function go(id) {
  const sandbox = loadNavigation();
  const tabs = [];
  const landed = [];
  sandbox.window.setStrategyTab = (step, tab) => tabs.push([step, tab]);
  sandbox.window.RetirementNavigation.setStep(
    {
      getPlanLoaded: () => true,
      setActiveStep: (x) => landed.push(x),
      renderMain: () => {},
      setSearchText: () => {},
      setNavSearchText: () => {},
      focusableEntries: () => [],
    },
    id,
  );
  return { landed: landed[landed.length - 1], tabs };
}

const dash = loadDashboardSandbox();
const run = (code) => vm.runInContext(code, dash);

describe("Actual Spending step (#338 C5)", () => {
  test("visible Reports & Review group is exactly Actual Spending, Build & Results", () => {
    run("planLoaded = true; activeStep = 'spending_core';");
    const titles = run(
      "visibleSteps().filter((s) => s.group === 'Reports & Review').map((s) => s.title).join('|')",
    );
    assert.equal(titles, "Actual Spending|Build & Results");
  });

  test("actual_spending has the two tabs, This year first", () => {
    assert.equal(run("STRATEGY_TABS.actual_spending.join('|')"), "This year|Analysis");
  });

  test("Spending Model is no longer a tabbed workspace", () => {
    assert.equal(run("STRATEGY_TABS.spending_core"), undefined);
  });

  test("ytd_transactions lands on actual_spending / This year", () => {
    const r = go("ytd_transactions");
    assert.equal(r.landed, "actual_spending");
    assert.deepEqual(r.tabs, [["actual_spending", "This year"]]);
  });

  test("spending_dashboard lands on actual_spending / Analysis", () => {
    const r = go("spending_dashboard");
    assert.equal(r.landed, "actual_spending");
    assert.deepEqual(r.tabs, [["actual_spending", "Analysis"]]);
  });

  test("actual_spending autosaves on navigate, like ytd_transactions did", () => {
    assert.ok(loadNavigation().window.RetirementNavigation.AUTOSAVE_STEPS.includes("actual_spending"));
  });
});

describe("one reports group (#338 C5)", () => {
  test("no STEPS entry is in a 'Reports' group; hub sub-pages are Reports & Review", () => {
    const groups = JSON.parse(run("JSON.stringify(Object.fromEntries(STEPS.map((s) => [s.id, s.group])))"));
    assert.ok(!Object.values(groups).includes("Reports"));
    for (const id of ["review", "build_impact", "detailed_results", "plan_data_report", "spending_dashboard"]) {
      assert.equal(groups[id], "Reports & Review", id);
    }
  });

  test("reports_and_review is titled Build & Results; build_impact keeps its title", () => {
    const titles = JSON.parse(run("JSON.stringify(Object.fromEntries(STEPS.map((s) => [s.id, s.title])))"));
    assert.equal(titles.reports_and_review, "Build & Results");
    assert.equal(titles.build_impact, "Impact & Build History");
  });

  test("fieldFinderCategoryName has no 'Reports' special case", () => {
    assert.equal(dash.fieldFinderCategoryName("Reports & Review"), "Reports & Review");
    assert.equal(dash.fieldFinderCategoryName("Reports"), "Reports");
  });

  test("the pane eyebrow list is just Reports & Review and Settings", () => {
    const src = fs.readFileSync(path.join(JS, "dashboard.js"), "utf8");
    assert.match(src, /\["Reports & Review", "Settings"\]\.includes\(/);
    assert.doesNotMatch(src, /\["Reports", "Reports & Review", "Settings"\]/);
  });

  // Buttons that mean "go to the hub" name it; action buttons that happen to
  // land there ("Download", "Rebuild now") keep naming the action.
  test("hub navigation buttons name Build & Results", () => {
    const OLD = /^(Review Reports|View Reports|Review and Build|Go to Build(?! &))/;
    let named = 0;
    for (const f of fs.readdirSync(JS).filter((x) => x.endsWith(".js"))) {
      const src = fs.readFileSync(path.join(JS, f), "utf8");
      for (const m of src.matchAll(/data-step-id="reports_and_review"[^>]*>([^<]*)</g)) {
        assert.doesNotMatch(m[1], OLD, `${f}: "${m[1]}"`);
        if (/Build &(amp;)? Results/.test(m[1])) named++;
      }
    }
    assert.ok(named >= 4, `only ${named} hub buttons name Build & Results`);
  });
});
