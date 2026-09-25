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
import { loadDashboardSandbox } from "./load_dashboard.mjs";

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
let revealed;

beforeEach(() => {
  sandbox = loadNavigation();
  nav = sandbox.window.RetirementNavigation;
  landedOn = [];
  openedSections = [];
  openedTabs = [];
  sandbox.window.strategySectionSetOpen = (key, open) =>
    openedSections.push([key, open]);
  sandbox.window.setStrategyTab = (step, tab) => openedTabs.push([step, tab]);
  revealed = [];
  sandbox.document.querySelector = (sel) => {
    revealed.push(sel);
    return null;
  };
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
  // #330 P8 / Q6 (W13): roth_conversion and entity_charitable left this table
  // when they became real Taxes nav steps (see "destinations that left
  // Strategy entirely" below) -- the same move W9 made for heloc_strategy.
  const OPTIMIZE = {
    allocation_assets: "asset_allocation",
    allocation_policy: "asset_allocation",
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
  // #338 W-C: the Housing page left the nav; its residency table sits
  // under Spending Model's Housing accordion.
  test("state_residency lands on Spending Model's residency section", () => {
    assert.equal(go("state_residency"), "spending_core");
    assert.deepEqual(openedTabs, [["spending_core", "Spending Model"]]);
    assert.deepEqual(revealed, ['[data-dkey="housing:residency"]']);
  });

  test("timing_tax lands on Spending Model's residency section", () => {
    assert.equal(go("timing_tax"), "spending_core");
    assert.deepEqual(revealed, ['[data-dkey="housing:residency"]']);
  });

  // #329/#330 W9: heloc_strategy is a direct nav step now (W13 moved it into
  // the Housing & Property group), not an embedded strategySection -- setStep
  // resolves it like any other real id, with no SECTION_REDIRECTS entry and
  // no section forced open. special_strategies (dead per W6's notes) now
  // points at the same real page instead of a strategySection key that no
  // longer exists.
  test("heloc_strategy lands directly on its own Housing & Property page", () => {
    assert.equal(go("heloc_strategy"), "heloc_strategy");
    assert.deepEqual(openedSections, []);
  });

  // #330 P8 / Q6 (W13): the two tax levers followed HELOC out of Optimize,
  // into the new Taxes nav group. Both keep their own renderMain() dispatch
  // case, so nothing forces a section open on the way.
  test("roth_conversion lands directly on its own Taxes page", () => {
    assert.equal(go("roth_conversion"), "roth_conversion");
    assert.deepEqual(openedSections, []);
  });

  test("entity_charitable lands directly on its own Taxes page", () => {
    assert.equal(go("entity_charitable"), "entity_charitable");
    assert.deepEqual(openedSections, []);
  });

  test("special_strategies lands on the same HELOC page", () => {
    assert.equal(go("special_strategies"), "heloc_strategy");
    assert.deepEqual(openedSections, []);
  });

  // #338 W-C (C4): the Spending workspace's Withdrawal Order tab is gone;
  // every row it rendered renders on these three Optimize sections.
  test("withdrawal_strategy lands on Optimize with its three withdrawal sections open", () => {
    const landed = go("withdrawal_strategy");
    assert.equal(landed, "strategy_optimize");
    assert.deepEqual(openedTabs, []);
    assert.deepEqual(openedSections, [
      ["withdrawal_sequencing", true],
      ["hsa_drawdown", true],
      ["harvesting", true],
    ]);
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
    assert.equal(go("strategy_optimize", false), "start");
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

  test("state_residency's autosave moved with its table to Spending Model", () => {
    assert.ok(nav.AUTOSAVE_STEPS.includes("spending_core"));
  });

  test("the retired Housing and Wellness step ids are not autosave destinations (#338)", () => {
    for (const id of ["spending_mortgage_events", "retirement_wellness"]) {
      assert.ok(!nav.AUTOSAVE_STEPS.includes(id), id);
    }
  });

  // #330 P8 / Q6 (W13): both left strategy_optimize's aggregate autosave
  // umbrella when they became their own Taxes steps, exactly as
  // heloc_strategy did in W9 -- they are input pages and must keep
  // autosaving on navigate.
  test("the two promoted Taxes steps autosave on their own", () => {
    for (const id of ["roth_conversion", "entity_charitable"]) {
      assert.ok(nav.AUTOSAVE_STEPS.includes(id), `${id} must autosave`);
    }
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
    // allocation_assets resolves through SECTION_REDIRECTS to
    // strategy_optimize, which is NOT in PLAN_INDEPENDENT_STEPS -- the
    // early-return path fires. (This drove roth_conversion until W13 promoted
    // it to a real step with no SECTION_REDIRECTS entry of its own.)
    go("allocation_assets", false);
    assert.equal(landedOn[landedOn.length - 1], "start");

    // Now load a plan and navigate somewhere else entirely. If the bug is
    // present, revealPendingSection() still holds "strategy:asset_allocation"
    // from the aborted navigation above and will act on it here even though
    // this navigation has nothing to do with Asset Allocation.
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

// #338 W-C task C3: Housing and Wellness are edited inside Spending Model;
// their old step ids land there with the matching accordion open.
describe("Housing and Wellness steps redirect into Spending Model (#338)", () => {
  const OPEN = { spending_mortgage_events: "Housing", retirement_wellness: "Wellness" };
  for (const [legacy, accordion] of Object.entries(OPEN)) {
    test(`${legacy} -> Spending Model / ${accordion} accordion`, () => {
      assert.equal(go(legacy), "spending_core");
      assert.deepEqual(openedTabs, [["spending_core", "Spending Model"]]);
      assert.deepEqual(revealed, [`[data-dkey="budget:core:${accordion}"]`]);
    });
  }

  test("the reveal opens every collapsed ancestor, not just the target", () => {
    const outer = { tagName: "DETAILS", open: false, parentElement: null };
    const inner = { tagName: "DETAILS", open: false, parentElement: outer };
    const target = { tagName: "DETAILS", open: false, parentElement: inner, scrollIntoView() {} };
    sandbox.document.querySelector = () => target;
    go("state_residency");
    assert.equal(target.open, true);
    assert.equal(inner.open, true);
    assert.equal(outer.open, true);
  });

  test("neither id is a visible nav step", () => {
    const dash = loadDashboardSandbox();
    vm.runInContext("planLoaded = true; activeStep = 'spending_core';", dash);
    const ids = vm.runInContext("visibleSteps().map((s) => s.id)", dash);
    assert.ok(ids.includes("spending_core"));
    for (const id of Object.keys(OPEN)) assert.ok(!ids.includes(id), id);
  });
});
