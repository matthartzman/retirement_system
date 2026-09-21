// Ticket 323 / Phase 1: the Strategy workspace's collapsible-section primitive.
//
// The whole point of strategySection() is that the body function is NOT called
// while the section is collapsed: renderMain() re-renders the entire tree on
// every field edit, and one of these bodies
// (renderAllocationRecommendation()) emits seven sub-panels. A regression
// that eagerly evaluates every body would be invisible on screen and very
// expensive per keystroke, so it is asserted directly here.
//
// The second invariant under test is open-state bookkeeping: the persisted
// state must be written BEFORE renderMain() re-renders, because renderMain()
// captures/restores <details> open-state across its innerHTML write (keyed by
// data-dkey). If persistence lagged the DOM, a section could be restored open
// while still holding the collapsed stub body.

import { test, describe, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();
// Captured before the top-level beforeEach below stubs it out for the
// strategySection tests; the "strategy_stress screen-level gate" describe
// restores this real binding to exercise the actual gating logic.
const realStepGatedByOptionalModule = sandbox.stepGatedByOptionalModule;

let store;

beforeEach(() => {
  store = {};
  sandbox.localStorage = {
    getItem: (k) => (k in store ? store[k] : null),
    setItem: (k, v) => {
      store[k] = String(v);
    },
    removeItem: (k) => {
      delete store[k];
    },
  };
  // dashboard.js declares renderMain as a reassignable `let` with a get+set
  // window accessor (the generated module bridge); assigning through the
  // accessor is what actually replaces the binding every module calls.
  sandbox.window.renderMain = () => {};
  sandbox.stepGatedByOptionalModule = () => false;
  // Open state is mirrored in module memory (see the storage comment in
  // dashboard_decomp_strategy_workspace.js); drop it so each case starts from
  // its own localStorage stub rather than the previous case's state.
  sandbox.strategySectionResetOpenCache();
});

describe("strategySection lazy body (ticket 323)", () => {
  test("a collapsed section never calls its body function", () => {
    let calls = 0;
    const html = sandbox.strategySection(
      "roth_conversion",
      "Roth Conversion",
      () => {
        calls += 1;
        return "<p>body</p>";
      },
      null,
    );
    assert.equal(calls, 0);
    assert.ok(!html.includes("<p>body</p>"));
    assert.ok(html.includes('data-dkey="strategy:roth_conversion"'));
    assert.ok(html.includes("Roth Conversion"));
  });

  test("an open section calls its body function exactly once and renders it", () => {
    store.strategySectionsOpen = JSON.stringify({ roth_conversion: true });
    let calls = 0;
    const html = sandbox.strategySection(
      "roth_conversion",
      "Roth Conversion",
      () => {
        calls += 1;
        return "<p>body</p>";
      },
      null,
    );
    assert.equal(calls, 1);
    assert.ok(html.includes("<p>body</p>"));
    assert.ok(/<details[^>]*\sopen/.test(html));
  });

  test("a gated-off section shows the enable note instead of calling the body", () => {
    store.strategySectionsOpen = JSON.stringify({ charitable_giving: true });
    sandbox.stepGatedByOptionalModule = (id) => id === "entity_charitable";
    let calls = 0;
    const html = sandbox.strategySection(
      "charitable_giving",
      "Charitable Giving",
      () => {
        calls += 1;
        return "<p>body</p>";
      },
      "entity_charitable",
    );
    assert.equal(calls, 0);
    assert.ok(!html.includes("<p>body</p>"));
    assert.ok(html.includes("Plan Features"));
  });

  test("the HELOC gate keeps its own enable-it link", () => {
    sandbox.stepGatedByOptionalModule = (id) => id === "heloc_strategy";
    const html = sandbox.strategySection(
      "heloc",
      "Home Equity Line",
      () => "<p>body</p>",
      "heloc_strategy",
    );
    assert.ok(html.includes("Enable HELOC Strategy"));
  });

  test("toggling persists the new state before re-rendering", () => {
    const order = [];
    sandbox.window.renderMain = () =>
      order.push("render:" + store.strategySectionsOpen);
    sandbox.strategySectionToggle("heloc", true);
    assert.deepEqual(JSON.parse(store.strategySectionsOpen), { heloc: true });
    assert.equal(order.length, 1);
    assert.ok(order[0].includes('"heloc":true'));
    sandbox.strategySectionToggle("heloc", false);
    assert.deepEqual(JSON.parse(store.strategySectionsOpen), { heloc: false });
  });

  test("a throwing localStorage does not break rendering", () => {
    sandbox.localStorage = {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("blocked");
      },
      removeItem: () => {},
    };
    const html = sandbox.strategySection("heloc", "HELOC", () => "x", null);
    assert.ok(html.includes("HELOC"));
    sandbox.strategySectionToggle("heloc", true);
  });
});

// Note: the file-level beforeEach leaves localStorage empty and
// stepGatedByOptionalModule stubbed to "nothing is gated" -- exactly the
// first-visit state renderStrategyScreen()'s default-open logic is built
// for. That means each screen's FIRST section listed below genuinely renders
// open with its real body on these calls; the other three/two stay collapsed
// stubs. (An earlier version of this block asserted only that every
// data-dkey was present and claimed in its title that nothing was open --
// that claim was true before the first-visit default-open behavior was
// added later in the same ticket, and was never updated to match. The
// deeper default-open semantics -- explicit stored state beating the
// default, gated sections being skipped when picking it -- are covered in
// their own "first-visit default open state" block below; this block only
// needs to correctly describe what these three specific calls produce.)
describe("the four Strategy screens (ticket 323 + Workbench)", () => {
  test("Optimize renders its five sections; the first (Roth Conversion) opens with its real body, the rest stay collapsed", () => {
    const html = sandbox.renderStrategyOptimize();
    for (const key of [
      "roth_conversion",
      "asset_allocation",
      "housing",
      "charitable_giving",
      "heloc",
    ]) {
      assert.ok(
        html.includes(`data-dkey="strategy:${key}"`),
        `missing section ${key}`,
      );
    }
    assert.match(html, /data-dkey="strategy:roth_conversion"[^>]*\sopen/);
    for (const key of ["asset_allocation", "housing", "charitable_giving", "heloc"]) {
      assert.doesNotMatch(
        html,
        new RegExp(`data-dkey="strategy:${key}"[^>]*\\sopen`),
      );
    }
  });

  test("Stress Test renders its four sections; the first (Monte Carlo) opens, the rest stay collapsed", () => {
    const html = sandbox.renderStrategyStress();
    for (const key of ["monte_carlo", "survivor", "ltc", "divorce"]) {
      assert.ok(
        html.includes(`data-dkey="strategy:${key}"`),
        `missing section ${key}`,
      );
    }
    assert.match(html, /data-dkey="strategy:monte_carlo"[^>]*\sopen/);
    for (const key of ["survivor", "ltc", "divorce"]) {
      assert.doesNotMatch(
        html,
        new RegExp(`data-dkey="strategy:${key}"[^>]*\\sopen`),
      );
    }
  });

  test("Scenarios renders only Scenario Change Sets, which opens by default", () => {
    const html = sandbox.renderStrategyScenarios();
    assert.ok(html.includes('data-dkey="strategy:change_sets"'));
    assert.ok(!html.includes('data-dkey="strategy:levers"'), "levers must no longer live under Scenarios");
    assert.ok(!html.includes('data-dkey="strategy:workbench"'), "workbench must no longer live under Scenarios");
    assert.match(html, /data-dkey="strategy:change_sets"[^>]*\sopen/);
  });

  test("Workbench renders its five sections; the first (Strategy Levers) opens, the rest stay collapsed", () => {
    // load_dashboard.mjs only loads dashboard.js/dashboard_shared_helpers.js/
    // dashboard_decomp_*.js into the sandbox (see its `wanted` filter), so
    // planning_workbench_ui.js -- and therefore the real
    // window.RetirementPlanningWorkbench -- is never present here. Only
    // readAll/activeId run unconditionally inside renderStrategyWorkbench()
    // (the other W.* methods live inside lazy bodies that stay collapsed and
    // uncalled in this test), so a minimal stub is enough, matching the same
    // stubbing pattern reports_and_review_restructure.test.mjs already uses.
    sandbox.window.RetirementPlanningWorkbench = {
      readAll: () => [],
      activeId: () => "",
    };
    const html = sandbox.renderStrategyWorkbench();
    for (const key of ["levers", "change_sets", "comparison", "decision", "saved_cases"]) {
      assert.ok(
        html.includes(`data-dkey="strategy:${key}"`),
        `missing section ${key}`,
      );
    }
    assert.match(html, /data-dkey="strategy:levers"[^>]*\sopen/);
    for (const key of ["change_sets", "comparison", "decision", "saved_cases"]) {
      assert.doesNotMatch(
        html,
        new RegExp(`data-dkey="strategy:${key}"[^>]*\\sopen`),
      );
    }
  });

  test("Workbench keeps its top model-note intro above the sections", () => {
    sandbox.window.RetirementPlanningWorkbench = {
      readAll: () => [],
      activeId: () => "",
    };
    const html = sandbox.renderStrategyWorkbench();
    assert.match(html, /Planning Workbench model/);
    assert.ok(
      html.indexOf("Planning Workbench model") < html.indexOf('data-dkey="strategy:levers"'),
      "the model note must render before the first section",
    );
  });
});

// The tests below were moved here from tests/test_strategy_workspace_screens.py
// (originally a Python source-text-grep file) per the preference order in
// tests/test_freeze_frontend_source_grep.py: STEPS is a real array and
// stepGatedByOptionalModule/renderDistributionStrategy/renderStateResidency/
// renderSpecialStrategies are real hoisted bindings on the sandbox, so
// inspecting/calling them directly catches a broken refactor that a string
// match on dashboard.js's source text would not (e.g. STEPS moving to a
// lookup table, or a rename that keeps the string but drops the wiring).
// window.STEPS/window.moduleGates are get(+set) accessors generated by
// tools/js_codemod/convert_dashboard.mjs for dashboard.js's reassignable
// `let`/`const` top-level bindings -- see load_dashboard.mjs's header comment
// and the `window.renderMain` accessor used above.
describe("STEPS wiring for the four Strategy screens (ticket 323 + Workbench)", () => {
  const NEW_STEPS = ["strategy_optimize", "strategy_stress", "strategy_scenarios", "strategy_workbench"];
  const stepById = (id) => sandbox.window.STEPS.find((s) => s.id === id);

  test("each new step is a Strategy-group nav entry with desc/intro/help", () => {
    const titles = { strategy_optimize: "Optimize", strategy_stress: "Stress Test", strategy_scenarios: "Scenarios", strategy_workbench: "Workbench" };
    for (const id of NEW_STEPS) {
      const step = stepById(id);
      assert.ok(step, `missing STEPS entry for ${id}`);
      assert.equal(step.group, "Strategy", id);
      assert.equal(step.title, titles[id], id);
      assert.ok(step.desc, `${id} missing desc`);
      assert.ok(step.intro, `${id} missing intro`);
      assert.ok(step.help, `${id} missing help`);
    }
  });

  test("the three new steps are adjacent so the nav groups them together", () => {
    const ids = sandbox.window.STEPS.map((s) => s.id);
    const positions = NEW_STEPS.map((id) => ids.indexOf(id));
    assert.deepEqual(positions, [...positions].sort((a, b) => a - b));
    const between = sandbox.window.STEPS.slice(positions[0], positions[positions.length - 1] + 1);
    assert.equal(between.filter((s) => s.group === "Strategy").length, positions.length);
  });

  test("the superseded steps survive as hidden, ungrouped shells (row routing still keys off them)", () => {
    for (const id of ["distribution_strategy", "state_residency", "special_strategies"]) {
      const step = stepById(id);
      assert.ok(step, `missing STEPS shell for ${id}`);
      assert.equal(step.group, null, id);
      assert.equal(step.hidden, true, id);
    }
  });

  test('the "Stress Tests" nav group label no longer exists', () => {
    assert.ok(sandbox.window.STEPS.every((s) => s.group !== "Stress Tests"));
  });

  test("strategy_workbench is a Strategy-group nav entry with desc/intro/help", () => {
    const step = stepById("strategy_workbench");
    assert.ok(step, "missing STEPS entry for strategy_workbench");
    assert.equal(step.group, "Strategy");
    assert.equal(step.title, "Workbench");
    assert.ok(step.desc, "strategy_workbench missing desc");
    assert.ok(step.intro, "strategy_workbench missing intro");
    assert.ok(step.help, "strategy_workbench missing help");
  });

  test("planning_workbench and planning_levers are now hidden shells", () => {
    for (const id of ["planning_workbench", "planning_levers"]) {
      const step = stepById(id);
      assert.ok(step, `missing STEPS shell for ${id}`);
      assert.equal(step.hidden, true, id);
    }
  });
});

// SECTION_REDIRECTS lives in navigation.js, which this file's dashboard
// sandbox (load_dashboard.mjs) deliberately does not load -- see that file's
// header comment. Behavioral coverage of planning_workbench/planning_levers
// redirecting to strategy_workbench lives in
// tests/frontend/strategy_section_redirects.test.mjs (the "Compare & Decide"
// and legacy-step-id describe blocks), which loads navigation.js directly.

describe("deletions stay deleted (ticket 323)", () => {
  test("renderStateResidency, renderSpecialStrategies and renderDistributionStrategy are gone -- no stale window bridge to throw at load", () => {
    assert.equal(typeof sandbox.renderStateResidency, "undefined");
    assert.equal(typeof sandbox.renderSpecialStrategies, "undefined");
    // renderDistributionStrategy was a one-line wrapper around
    // renderPlanningLevers(); its inbound links were redirected to
    // strategy_optimize before this deletion landed (SECTION_REDIRECTS,
    // tests/frontend/strategy_section_redirects.test.mjs), so nothing can
    // reach the dead renderMain branch this function backed.
    assert.equal(typeof sandbox.renderDistributionStrategy, "undefined");
  });

  test("ssClaimAgeCoordinationSummaryHtml is gone -- Optimize has no Social Security section", () => {
    assert.equal(typeof sandbox.ssClaimAgeCoordinationSummaryHtml, "undefined");
  });
});

describe("deletions stay deleted (Workbench integration)", () => {
  test("renderWorkbenchStressHtml and renderWorkbenchLeverEditorHtml are gone -- no stale duplicate renderers", () => {
    assert.equal(typeof sandbox.renderWorkbenchStressHtml, "undefined");
    assert.equal(typeof sandbox.renderWorkbenchLeverEditorHtml, "undefined");
  });

  test("the old planning_workbench_ui.js renderWorkbench() is gone -- superseded by renderStrategyWorkbench()", () => {
    assert.equal(typeof sandbox.window.RetirementPlanningWorkbench.renderWorkbench, "undefined");
  });

  test("renderPlanningLevers() no longer links back to itself", () => {
    // planningLeversBaselineReady() gates the real body vs. a "build first"
    // placeholder; force it true (both planLoaded and lastBuildOk have
    // get/set window accessors -- dashboard.js:7188/7202 -- generated by
    // this repo's module-bridge codemod) so this test exercises the actual
    // markup the deletion touches, not the unrelated placeholder.
    sandbox.window.planLoaded = true;
    sandbox.window.lastBuildOk = true;
    const html = sandbox.renderPlanningLevers();
    assert.ok(!html.includes("Back to Planning Workbench"));
    sandbox.window.planLoaded = false;
    sandbox.window.lastBuildOk = false;
  });
});

describe("strategy_stress screen-level gate (ticket 323)", () => {
  const STRESS_LEGACY_IDS = ["monte_carlo_options", "survivor_stress", "ltc_stress", "divorce_options"];
  let originalOptionalFunctionEnabled;
  let originalModuleGates;

  beforeEach(() => {
    // Undo the file-level beforeEach's `sandbox.stepGatedByOptionalModule =
    // () => false` stub so this describe block exercises the real function.
    sandbox.stepGatedByOptionalModule = realStepGatedByOptionalModule;
    originalOptionalFunctionEnabled = sandbox.optionalFunctionEnabled;
    originalModuleGates = sandbox.window.moduleGates;
    sandbox.window.moduleGates = {
      step_gates: {
        monte_carlo_options: "Monte Carlo",
        survivor_stress: "Survivor Stress",
        ltc_stress: "LTC Stress",
        divorce_options: "Divorce Options",
      },
    };
  });

  afterEach(() => {
    sandbox.optionalFunctionEnabled = originalOptionalFunctionEnabled;
    sandbox.window.moduleGates = originalModuleGates;
  });

  test("hidden when all four Stress Test modules are off", () => {
    sandbox.optionalFunctionEnabled = () => false;
    assert.equal(sandbox.stepGatedByOptionalModule("strategy_stress"), true);
  });

  test("visible when even one Stress Test module is on", () => {
    sandbox.optionalFunctionEnabled = (label) => label === "Survivor Stress";
    assert.equal(sandbox.stepGatedByOptionalModule("strategy_stress"), false);
  });

  test("derives its module keys from step_gates for the four legacy ids, not a hand-written list", () => {
    let queried = [];
    sandbox.optionalFunctionEnabled = (label) => {
      queried.push(label);
      return false;
    };
    sandbox.stepGatedByOptionalModule("strategy_stress");
    for (const legacyId of STRESS_LEGACY_IDS) {
      assert.ok(
        queried.includes(sandbox.window.moduleGates.step_gates[legacyId]),
        `did not query the module for ${legacyId}`,
      );
    }
  });

  test("Divorce Planning is entirely absent (not just gated-off) when its module is off; its siblings still render with an enable note", () => {
    sandbox.optionalFunctionEnabled = (label) => label === "Monte Carlo";
    const html = sandbox.renderStrategyStress();
    assert.ok(!html.includes('data-dkey="strategy:divorce"'), "Divorce Planning section must not render at all when divorce_qdro is off");
    assert.ok(!html.includes("Divorce Planning"), "Divorce Planning's title must not appear when its module is off");
    for (const key of ["monte_carlo", "survivor", "ltc"]) {
      assert.ok(
        html.includes(`data-dkey="strategy:${key}"`),
        `${key} should still render (gated-off sections keep their enable-note stub, unlike divorce)`,
      );
    }
  });

  test("Divorce Planning reappears once divorce_qdro is enabled", () => {
    sandbox.optionalFunctionEnabled = (label) => label === "Divorce Options";
    const html = sandbox.renderStrategyStress();
    assert.ok(html.includes('data-dkey="strategy:divorce"'));
    assert.ok(html.includes("Divorce Planning"));
  });
});

// Ticket 323 follow-up: open state must survive a localStorage write that
// throws (private mode, blocked site data, quota). The module already guards
// every storage ACCESS with try/catch so a throw cannot break rendering -- but
// swallowing a failed write is not enough on its own. If the persisted map
// stays stale while the DOM has already toggled, the two disagree, and
// renderMain()'s restore pass (which assigns d.open from the state it captured
// before its innerHTML write) flips the element back. That assignment fires
// another toggle event, which calls strategySectionToggle again, which fails to
// persist again -- an unbounded render loop in exactly the environment the
// try/catch was added to tolerate.
describe("strategySection open state when persistence fails", () => {
  test("a section the user opened still renders open after a failed write", () => {
    sandbox.localStorage.setItem = () => {
      throw new Error("QuotaExceededError");
    };
    sandbox.strategySectionToggle("heloc", true);
    const html = sandbox.strategySection(
      "heloc",
      "HELOC",
      () => "<p>body</p>",
      null,
    );
    assert.ok(
      /<details[^>]*\sopen/.test(html),
      "section rendered collapsed after the user opened it -- persisted state and DOM now disagree",
    );
    assert.ok(html.includes("<p>body</p>"), "open section must render its body");
  });

  test("a failed write does not strand the section in the opposite state on close", () => {
    sandbox.strategySectionToggle("heloc", true);
    sandbox.localStorage.setItem = () => {
      throw new Error("QuotaExceededError");
    };
    sandbox.strategySectionToggle("heloc", false);
    const html = sandbox.strategySection(
      "heloc",
      "HELOC",
      () => "<p>body</p>",
      null,
    );
    assert.ok(
      !/<details[^>]*\sopen/.test(html),
      "section rendered open after the user closed it",
    );
  });
});

// Ticket 323 follow-up: landing on a screen for the first time should show
// content, not a stack of collapsed bars. The first section a reader can
// actually use opens by default; once they open or close anything themselves,
// their own state wins from then on.
describe("first-visit default open state", () => {
  const optimize = () => [
    { key: "roth_conversion", title: "Roth Conversion", gate: "roth_conversion", body: () => "<p>roth</p>" },
    { key: "asset_allocation", title: "Asset Allocation", gate: null, body: () => "<p>alloc</p>" },
    { key: "heloc", title: "HELOC", gate: "heloc_strategy", body: () => "<p>heloc</p>" },
  ];

  function openKeys(html) {
    return [...html.matchAll(/data-dkey="strategy:([^"]+)"([^>]*)>/g)]
      .filter((m) => / open/.test(m[2]))
      .map((m) => m[1]);
  }

  test("the first section opens on a first visit, and only that one", () => {
    const html = sandbox.renderStrategyScreen(optimize());
    assert.deepEqual(openKeys(html), ["roth_conversion"]);
    assert.ok(html.includes("<p>roth</p>"), "the defaulted-open section renders its body");
    assert.ok(!html.includes("<p>alloc</p>"), "the others stay lazy");
  });

  test("a gated-off first section does not take the default; the first usable one does", () => {
    sandbox.stepGatedByOptionalModule = (id) => id === "roth_conversion";
    const html = sandbox.renderStrategyScreen(optimize());
    assert.deepEqual(
      openKeys(html),
      ["asset_allocation"],
      "defaulting an unavailable section open shows an enable-note instead of content",
    );
    assert.ok(html.includes("<p>alloc</p>"));
  });

  test("a section the reader closed stays closed on the next render", () => {
    store.strategySectionsOpen = JSON.stringify({ roth_conversion: false });
    sandbox.strategySectionResetOpenCache();
    const html = sandbox.renderStrategyScreen(optimize());
    assert.deepEqual(openKeys(html), [], "an explicit false must beat the first-visit default");
    assert.ok(!html.includes("<p>roth</p>"));
  });

  test("a section the reader opened stays open even when it is not the first", () => {
    store.strategySectionsOpen = JSON.stringify({ heloc: true });
    sandbox.strategySectionResetOpenCache();
    const html = sandbox.renderStrategyScreen(optimize());
    assert.ok(openKeys(html).includes("heloc"));
    assert.ok(html.includes("<p>heloc</p>"));
  });
});
