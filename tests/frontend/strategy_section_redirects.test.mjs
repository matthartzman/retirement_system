// Ticket 323 / Phase 2: the Strategy redesign collapsed eleven destinations
// into three screens of collapsible sections. Roughly thirty buttons, helpLink
// entries and SUGGESTED_NEXT values still navigate to the OLD step ids, so
// those ids have to keep working -- and land on the right section, not just at
// the top of a four-section screen.
//
// navigation.js is a classic IIFE that publishes window.RetirementNavigation;
// the dashboard sandbox in load_dashboard.mjs deliberately loads only
// dashboard*.js, so this file evaluates navigation.js on its own with a
// minimal window/document and drives setStep() through a ctx stub. That keeps
// this a behavioral test of the redirect table rather than a grep over source
// text.

import { test, describe, beforeEach } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const NAV_JS = path.join(HERE, "..", "..", "frontend", "js", "navigation.js");

function noop() {}

function loadNavigation() {
  const sandbox = {
    console,
    setTimeout: (fn) => {
      // Run scroll/focus callbacks synchronously so assertions see their
      // effects without the test having to await a real timer.
      try {
        fn();
      } catch (_e) {}
      return 0;
    },
    clearTimeout: noop,
    localStorage: {
      getItem: () => null,
      setItem: noop,
      removeItem: noop,
    },
    document: {
      getElementById: () => null,
      querySelector: () => null,
      querySelectorAll: () => [],
      addEventListener: noop,
      alias: null,
    },
  };
  sandbox.window = sandbox;
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(NAV_JS, "utf8"), sandbox, {
    filename: "navigation.js",
  });
  return sandbox;
}

let sandbox;
let nav;
let landedOn;
let openedSections;
let openedTabs;

beforeEach(() => {
  sandbox = loadNavigation();
  nav = sandbox.window.RetirementNavigation;
  landedOn = [];
  openedSections = [];
  openedTabs = [];
  sandbox.window.strategySectionSetOpen = (key, open) =>
    openedSections.push([key, open]);
  sandbox.window.setStrategyTab = (step, tab) => openedTabs.push([step, tab]);
});

function go(id, planLoaded = true) {
  nav.setStep(
    {
      getPlanLoaded: () => planLoaded,
      setActiveStep: (x) => landedOn.push(x),
      renderMain: noop,
      setSearchText: noop,
      setNavSearchText: noop,
      focusableEntries: () => [],
    },
    id,
  );
  return landedOn[landedOn.length - 1];
}

describe("legacy Strategy step ids land on the right screen and section", () => {
  const OPTIMIZE = {
    roth_conversion: "roth_conversion",
    allocation_assets: "asset_allocation",
    allocation_policy: "asset_allocation",
    entity_charitable: "charitable_giving",
  };
  for (const [legacy, section] of Object.entries(OPTIMIZE)) {
    test(`${legacy} -> Optimize / ${section}`, () => {
      assert.equal(go(legacy), "strategy_optimize");
      assert.deepEqual(openedSections, [[section, true]]);
    });
  }

  const STRESS = {
    monte_carlo_options: "monte_carlo",
    survivor_stress: "survivor",
    ltc_stress: "ltc",
    divorce_options: "divorce",
  };
  for (const [legacy, section] of Object.entries(STRESS)) {
    test(`${legacy} -> Stress Test / ${section}`, () => {
      assert.equal(go(legacy), "strategy_stress");
      assert.deepEqual(openedSections, [[section, true]]);
    });
  }

  const SCENARIOS = {
    scenarios: "change_sets",
  };
  for (const [legacy, section] of Object.entries(SCENARIOS)) {
    test(`${legacy} -> Scenarios / ${section}`, () => {
      assert.equal(go(legacy), "strategy_scenarios");
      assert.deepEqual(openedSections, [[section, true]]);
    });
  }

  // planning_levers and planning_workbench were folded into strategy_scenarios
  // as the "levers"/"workbench" sections; they now redirect to the standalone
  // Workbench screen instead (ticket 323 + Workbench), both opening its
  // default "levers" section.
  const WORKBENCH = {
    planning_levers: "levers",
    planning_workbench: "levers",
  };
  for (const [legacy, section] of Object.entries(WORKBENCH)) {
    test(`${legacy} -> Workbench / ${section}`, () => {
      assert.equal(go(legacy), "strategy_workbench");
      assert.deepEqual(openedSections, [[section, true]]);
    });
  }

  test("distribution_strategy lands on Optimize with no section forced open", () => {
    assert.equal(go("distribution_strategy"), "strategy_optimize");
    assert.deepEqual(openedSections, []);
  });

  test("investment_strategy lands on Optimize with no section forced open", () => {
    assert.equal(go("investment_strategy"), "strategy_optimize");
    assert.deepEqual(openedSections, []);
  });
});

describe("destinations that left Strategy entirely", () => {
  test("state_residency lands on the Housing page", () => {
    assert.equal(go("state_residency"), "spending_mortgage_events");
  });

  test("timing_tax lands on the Housing page", () => {
    assert.equal(go("timing_tax"), "spending_mortgage_events");
  });

  // #329/#330 W9: heloc_strategy is a direct Assets & Protection step now,
  // not an embedded strategySection -- setStep resolves it like any other
  // real id, with no SECTION_REDIRECTS entry and no section forced open.
  // special_strategies (dead per W6's notes) now points at the same real
  // page instead of a strategySection key that no longer exists.
  test("heloc_strategy lands directly on its own Assets & Protection page", () => {
    assert.equal(go("heloc_strategy"), "heloc_strategy");
    assert.deepEqual(openedSections, []);
  });

  test("special_strategies lands on the same HELOC page", () => {
    assert.equal(go("special_strategies"), "heloc_strategy");
    assert.deepEqual(openedSections, []);
  });

  test("withdrawal_strategy lands on the Spending workspace's own tab, not on Strategy", () => {
    const landed = go("withdrawal_strategy");
    assert.equal(landed, "spending_core");
    assert.deepEqual(openedTabs, [["spending_core", "Withdrawal Order"]]);
  });
});

describe("Compare & Decide stays reachable before a plan is open", () => {
  // planning_workbench was plan-independent and is reached from a button in
  // every page header. Redirecting it to strategy_workbench must not make
  // that button bounce to the start page when no plan is loaded.
  test("planning_workbench still resolves rather than bouncing to start", () => {
    assert.equal(go("planning_workbench", false), "strategy_workbench");
  });

  test("a genuinely plan-dependent Strategy screen still bounces to start", () => {
    assert.equal(go("roth_conversion", false), "start");
  });
});

describe("autosave coverage follows the steps that replaced the old ones", () => {
  // Only Optimize autosaves. It replaced distribution_strategy and
  // special_strategies, which both did. Stress Test and Scenarios replaced
  // monte_carlo_options / scenarios / planning_levers and friends, none of
  // which were listed -- they are previews that do not touch the saved plan,
  // and the exclusion is deliberate, not an oversight to be tidied up.
  test("Optimize autosaves on navigate, like the input pages it replaced", () => {
    assert.ok(nav.AUTOSAVE_STEPS.includes("strategy_optimize"));
  });

  test("the two preview screens stay on explicit save", () => {
    for (const id of ["strategy_stress", "strategy_scenarios"]) {
      assert.ok(
        !nav.AUTOSAVE_STEPS.includes(id),
        `${id} replaced steps that were deliberately excluded from autosave`,
      );
    }
  });

  test("the retired step ids are no longer listed as autosave destinations", () => {
    for (const id of [
      "distribution_strategy",
      "state_residency",
      "special_strategies",
    ]) {
      assert.ok(
        !nav.AUTOSAVE_STEPS.includes(id),
        `${id} is no longer a reachable destination and should not be listed`,
      );
    }
  });

  test("state_residency's autosave moved with its table to the Housing page", () => {
    assert.ok(nav.AUTOSAVE_STEPS.includes("spending_mortgage_events"));
  });
});

describe("pendingSectionDkey does not leak across an aborted redirect (final review finding)", () => {
  // setStep() resolves SECTION_REDIRECTS (which sets the module-level
  // pendingSectionDkey) BEFORE it checks planLoaded. If the plan-not-loaded
  // early-return branch below that fires instead -- bouncing to "start" --
  // it must not leave pendingSectionDkey set. Otherwise the reveal-and-scroll
  // meant for THIS aborted navigation fires later, on an unrelated
  // navigation, forcing open and scrolling to whatever page happens to still
  // have that data-dkey in the DOM -- a surprise side effect disconnected
  // from the user's actual action.
  test("a SECTION_REDIRECTS id clicked before a plan is loaded does not leave a stale pending reveal", () => {
    // roth_conversion resolves through SECTION_REDIRECTS to strategy_optimize,
    // which is NOT in PLAN_INDEPENDENT_STEPS -- the early-return path fires.
    go("roth_conversion", false);
    assert.equal(landedOn[landedOn.length - 1], "start");

    // Now load a plan and navigate somewhere else entirely. If the bug is
    // present, revealPendingSection() still holds "strategy:roth_conversion"
    // from the aborted navigation above and will act on it here even though
    // this navigation has nothing to do with Roth Conversion.
    let queried = null;
    sandbox.document.querySelector = (sel) => {
      queried = sel;
      return null;
    };
    go("holdings", true);
    assert.equal(
      queried,
      null,
      `a stale pending section reveal from the aborted navigation leaked into an unrelated one (queried ${queried})`,
    );
  });
});
