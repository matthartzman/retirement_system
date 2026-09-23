// Ticket 323 / Phase 3: rowsForStep() must union the constituent legacy ids
// for the three new Strategy screens.
//
// The three new STEPS entries (strategy_optimize, strategy_stress,
// strategy_scenarios) own no plan rows of their own -- every row still routes
// to a legacy shell id (roth_conversion, monte_carlo_options, ...) via the
// rawRowsForStep() switch, which the redesign deliberately left untouched
// (see spec S1, "old step ids survive as shells"). Without this aggregation,
// rowsForStep("strategy_optimize") falls through the switch's default case
// and returns [] forever -- which means stepStats("strategy_optimize") always
// reports zero required and zero missing, and the Strategy nav group's
// readiness badge (which sums stepStats(id).missing over every step in the
// group) silently and permanently reads zero. That is a real regression: it
// removes a signal every other nav group still provides.
//
// This is deliberately a rawRowsForStep()-level test, not a rowsForStep()
// one: rowsForStep() layers rowBuildUsageState()/inactiveEditReveals on top,
// which needs a running build-context this file does not stand up. The
// aggregation itself lives in rawRowsForStep(); rowsForStep() and
// stepStats() call through it unchanged, so proving the union at that layer
// proves the fix for both.

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();

// One synthetic row per legacy id this aggregation must cover, distinguished
// by a label unique enough to identify which case matched it. Real section/
// subsection/label combinations, lifted from the switch itself, not
// approximations -- a row that doesn't actually satisfy its case's predicate
// would prove nothing.
const ROWS = [
  { row_index: 1, section: "Withdrawal Policy", subsection: "roth_conversion", label: "roth_conversion_policy" },
  { row_index: 2, section: "Asset Allocation Policy", subsection: "global", label: "allocation_mode" },
  { row_index: 3, section: "Model Constants", subsection: "allocation", label: "risk_tolerance" },
  { row_index: 4, section: "DAF", subsection: "Setup", label: "daf_enabled" },
  { row_index: 5, section: "HELOC", subsection: "Setup", label: "heloc_enabled" },
  { row_index: 6, section: "Model Constants", subsection: "monte_carlo", label: "mc_trials" },
  { row_index: 7, section: "Household", subsection: "", label: "survivor_income_pct" },
  { row_index: 8, section: "Hybrid LTC", subsection: "Policy", label: "ltc_daily_benefit" },
  { row_index: 9, section: "Scenarios", subsection: "Divorce_transfer_pct", label: "amount" },
  { row_index: 10, section: "Scenarios", subsection: "Economy", label: "returns_shock_pct" },
  // A row that belongs to none of the three new screens -- must never appear
  // in any of their aggregates.
  { row_index: 11, section: "Household", subsection: "", label: "name" },
];

function rawRows(id, rowsOverride) {
  // `rows` is module-scoped `let` state in dashboard.js, not a plain sandbox
  // property -- top-level `let`/`const` bindings don't land on the vm
  // context's global object the way `function` declarations do. dashboard.js
  // bridges it as an accessor on window (Object.defineProperty(window,
  // "rows", {get, set})), and `window` here is sandbox.window specifically
  // (a distinct object from the sandbox/global itself in load_dashboard.mjs),
  // so that accessor -- not a bare `sandbox.rows =` -- is what actually
  // reaches the internal state rawRowsForStep() reads.
  sandbox.window.rows = rowsOverride || ROWS;
  // rawRowsForStep() runs inside the vm context, so the array it returns is
  // an Array from that context's OWN realm -- a different Array constructor
  // than this file's. Node's strict assert.deepEqual compares prototypes as
  // part of its structural check, so a cross-realm array full of identical
  // primitives still fails as "same structure but not reference-equal".
  // Array.from() here rebuilds it with THIS realm's Array, which is all
  // deepEqual needs since the elements themselves are primitives (numbers),
  // and primitives carry no realm identity of their own.
  return Array.from(sandbox.rawRowsForStep(id));
}

describe("rawRowsForStep aggregates the constituent legacy ids (ticket 323)", () => {
  // #329/#330 W9: heloc_strategy left this union when it became its own
  // Assets & Protection step -- row 5 (HELOC) is still reachable directly
  // via rawRowsForStep("heloc_strategy") below, just no longer through
  // strategy_optimize's aggregate.
  // #330 P8 / Q6 (W13): roth_conversion (row 1) and entity_charitable (row 4)
  // left this union when they became their own Taxes nav steps -- same move,
  // same reason as heloc_strategy above. Both are still reachable directly,
  // asserted in "the legacy shell ids still return their own rows" below.
  test("strategy_optimize unions allocation_assets and allocation_policy", () => {
    const indices = rawRows("strategy_optimize").map((r) => r.row_index).sort();
    assert.deepEqual(indices, [2, 3]);
  });

  test("the two promoted Taxes steps still return their own rows directly", () => {
    assert.deepEqual(rawRows("roth_conversion").map((r) => r.row_index), [1]);
    assert.deepEqual(rawRows("entity_charitable").map((r) => r.row_index), [4]);
  });

  test("heloc_strategy still returns its own row directly, unaggregated", () => {
    const indices = rawRows("heloc_strategy").map((r) => r.row_index).sort();
    assert.deepEqual(indices, [5]);
  });

  test("strategy_stress unions monte_carlo_options, survivor_stress, ltc_stress, divorce_options", () => {
    const indices = rawRows("strategy_stress").map((r) => r.row_index).sort();
    assert.deepEqual(indices, [6, 7, 8, 9]);
  });

  test("strategy_scenarios unions scenarios (planning_levers/planning_workbench own no rows)", () => {
    const indices = rawRows("strategy_scenarios").map((r) => r.row_index).sort();
    assert.deepEqual(indices, [10]);
  });

  test("a row belonging to none of the three never leaks into any aggregate", () => {
    for (const id of ["strategy_optimize", "strategy_stress", "strategy_scenarios"]) {
      assert.ok(
        !rawRows(id).some((r) => r.row_index === 11),
        `row 11 (Household/name) leaked into ${id}`,
      );
    }
  });

  test("the legacy shell ids still return their own rows directly, unaggregated", () => {
    // Row routing for every OTHER surface in the app (Field Finder, the build
    // change summary, source-jump buttons) keys off the legacy ids directly,
    // not the new screen ids. The aggregation must be additive, not a
    // replacement -- the shells must keep working exactly as before.
    assert.deepEqual(rawRows("roth_conversion").map((r) => r.row_index), [1]);
    assert.deepEqual(rawRows("monte_carlo_options").map((r) => r.row_index), [6]);
    assert.deepEqual(rawRows("scenarios").map((r) => r.row_index), [10]);
  });

  test("no row is double-counted even if the union set overlapped (defensive)", () => {
    // allocation_assets and allocation_policy are disjoint by section today,
    // so this can't currently happen -- but the aggregation dedupes by
    // row_index regardless, so a future member-id addition that overlaps
    // another can't silently inflate stepStats totals.
    const indices = rawRows("strategy_optimize", ROWS).map((r) => r.row_index);
    const seen = new Set();
    for (const i of indices) {
      assert.ok(!seen.has(i), `row_index ${i} appeared twice in the aggregate`);
      seen.add(i);
    }
  });
});

// Ticket 323 / Phase 5: renderScenarios() used to carry a "State comparison —
// insurance costs" block gated on rowsForStep("scenarios") containing
// section === "State Comparison" rows. That precondition is never true --
// State Comparison rows route to state_residency (now the Housing page's
// residency section), never to scenarios -- so the block has never rendered.
// This proves the precondition false at the routing layer, which is what
// justifies deleting the dead consumer in
// dashboard_decomp_housing_scenarios.js rather than merely asserting the
// string is gone from source.
describe("State Comparison rows never route to the scenarios step (ticket 323)", () => {
  test("a State Comparison row is absent from rawRowsForStep(\"scenarios\")", () => {
    const stateCompRow = {
      row_index: 100,
      section: "State Comparison",
      subsection: "homeowners_insurance",
      label: "target_state_annual",
    };
    sandbox.window.rows = [stateCompRow];
    const scenarios = sandbox.rawRowsForStep("scenarios");
    assert.ok(
      !scenarios.some((r) => r.row_index === 100),
      "a State Comparison row leaked into the scenarios step",
    );
  });
});
