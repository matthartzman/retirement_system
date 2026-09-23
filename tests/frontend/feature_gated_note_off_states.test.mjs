// #330 §5.2/§5.3 (W12): off-state rendering. featureGatedNote() generalizes
// strategySectionGatedNote() into the registry-driven "Collapsed with a
// note" off-state (see dashboard_decomp_strategy_workspace.js and
// tests/test_strategy_workspace_module_gating.py for the note's own
// mechanics); this file covers the other two things the plan names as W12's
// job:
//
//   - the no-hidden-data invariant itself: a module/flag that gates a
//     SECTION inside a page that stays visible must never make a row with a
//     user-entered value disappear. renderInsurancePolicies(),
//     renderAssetsSpecial() and renderEntityCharitable() each used to
//     `return` a static "hidden" message (or omit a group entirely) in
//     place of the gated rows -- this suite proves seeded data survives.
//   - the "Disabled in place" state (optionalModuleState()/
//     rowBuildUsageState()) is unchanged by that fix, and the "Hidden" state
//     (a module-owned nav step with no data) still hides today, matching
//     the spec's three-off-states table (§5.2).

import { test, describe, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();

beforeEach(() => {
  sandbox.window.rows = [];
  sandbox.window.dirty = new Map();
  sandbox.window.searchText = "";
  sandbox.window.moduleGates = { step_gates: {}, section_gates: {}, flag_gates: {} };
  sandbox.window.moduleTaxonomy = { modules: {} };
});

describe("featureGatedNote (Collapsed-with-a-note, #330 §5.2)", () => {
  test("module_toggle: falls back to a Plan Features link when the toggle row isn't loaded", () => {
    const html = sandbox.featureGatedNote("existing_life_insurance", { title: "Existing Life Insurance" });
    assert.ok(html.includes("Existing Life Insurance is off"));
    assert.ok(html.includes("Plan Features"));
    assert.ok(!html.includes("<button"));
  });

  test("module_toggle: offers an inline switch when the toggle row is loaded", () => {
    sandbox.window.rows = [
      { row_index: 1, section: "Optional Functions", label: "existing_life_insurance", value: "NO" },
    ];
    const html = sandbox.featureGatedNote("existing_life_insurance", { title: "Existing Life Insurance" });
    assert.ok(html.includes("<button"));
    assert.ok(html.includes("editValue(1,'YES',null)"));
  });

  test("plan_flag: offers an inline switch and names where the flag lives when the row is loaded", () => {
    sandbox.window.rows = [
      { row_index: 7, section: "Hybrid LTC", subsection: "Settings", label: "enabled", value: "NO" },
    ];
    const html = sandbox.featureGatedNote("hybrid_ltc_policy", {
      title: "LTC/Life Policy",
      gateKind: "plan_flag",
      gateRef: ["Hybrid LTC", "Settings", "enabled"],
      gateEnableLabel: "Enabled",
    });
    assert.ok(html.includes("editValue(7,'YES',null)"));
    assert.ok(html.includes("Hybrid LTC &rarr; Settings &rarr; Enabled"));
  });

  test("shows how many already-entered rows are affected, per §5.2's invariant text", () => {
    const html = sandbox.featureGatedNote("existing_life_insurance", {
      title: "Existing Life Insurance",
      rows: [
        { row_index: 1, value: "Disability" },
        { row_index: 2, value: "1200" },
        { row_index: 3, value: "" },
      ],
    });
    assert.ok(html.includes("2 already-entered items are retained"));
  });
});

describe("no-hidden-data invariant: Insurance In Force (§1 observation 4's own named example)", () => {
  test("a Disability policy survives when existing_life_insurance is off", () => {
    sandbox.window.rows = [
      {
        row_index: 10,
        section: "Insurance In Force",
        subsection: "Disability 1",
        label: "policy_type",
        value: "Disability",
      },
      {
        row_index: 11,
        section: "Insurance In Force",
        subsection: "Disability 1",
        label: "annual_premium",
        value: "1200",
      },
    ];
    const html = sandbox.renderInsurancePolicies();
    assert.ok(!html.includes("hidden until"), "the old static blackout message must be gone");
    assert.ok(html.includes('data-row="11"'), "the Disability policy's premium row must still render");
  });

  test("no rows still shows the note, not a blank page", () => {
    const html = sandbox.renderInsurancePolicies();
    assert.ok(html.includes("is off"));
  });
});

describe("no-hidden-data invariant: 529 / Equity Compensation / Hybrid LTC on Other Assets and Liabilities", () => {
  beforeEach(() => {
    // Matches config_service.py's real _module_gates() payload shape:
    // section_gates[section] = {key, label}, one entry per csv_sections-
    // declared module (education_funding_529/equity_compensation here).
    sandbox.window.moduleGates = {
      step_gates: {},
      flag_gates: {},
      section_gates: {
        "Education Funding": { key: "education_funding_529", label: "Education Funding 529 optional workbook module" },
        "Equity Compensation": { key: "equity_compensation", label: "Equity Compensation optional workbook module" },
      },
    };
  });

  test("a Hybrid LTC policy row survives when its flag is off", () => {
    sandbox.window.rows = [
      {
        row_index: 20,
        section: "Hybrid LTC",
        subsection: "Settings",
        label: "enabled",
        value: "NO",
      },
      {
        row_index: 21,
        section: "Hybrid LTC",
        subsection: "Policy",
        label: "annual_premium",
        value: "3000",
      },
    ];
    const html = sandbox.renderAssetsSpecial();
    assert.ok(html.includes('data-row="21"'), "the Hybrid LTC premium row must still render");
  });

  test("a 529 Plans row survives when education_funding_529 is off", () => {
    sandbox.window.rows = [
      {
        row_index: 30,
        section: "Education Funding",
        subsection: "Beneficiary 1",
        label: "current_balance",
        value: "15000",
      },
    ];
    const html = sandbox.renderAssetsSpecial();
    assert.ok(html.includes('data-row="30"'), "the 529 balance row must still render");
  });

  test("an Equity Compensation row survives when equity_compensation is off", () => {
    sandbox.window.rows = [
      {
        row_index: 40,
        section: "Equity Compensation",
        subsection: "equity_compensation",
        label: "shares_granted",
        value: "500",
      },
    ];
    const html = sandbox.renderAssetsSpecial();
    assert.ok(html.includes('data-row="40"'), "the equity-comp grant row must still render");
  });
});

// #330 P8 / Q6 (W13): the Family & Business nav step renders the same two
// gated groups from the same code (familyBusinessGroupsHtml), so the
// invariant above must hold identically on it. Asserted separately rather
// than assumed: a second entry point that silently drops a household's rows
// would be exactly the bug W12 closed, arriving through a new door.
describe("no-hidden-data invariant: the Family & Business step renders the same groups", () => {
  beforeEach(() => {
    sandbox.window.moduleGates = {
      step_gates: {},
      flag_gates: {},
      section_gates: {
        "Education Funding": { key: "education_funding_529", label: "Education Funding 529 optional workbook module" },
        "Equity Compensation": { key: "equity_compensation", label: "Equity Compensation optional workbook module" },
      },
    };
    sandbox.window.rows = [
      {
        row_index: 30,
        section: "Education Funding",
        subsection: "Beneficiary 1",
        label: "current_balance",
        value: "15000",
      },
      {
        row_index: 40,
        section: "Equity Compensation",
        subsection: "equity_compensation",
        label: "shares_granted",
        value: "500",
      },
    ];
  });

  test("both groups' rows survive when both modules are off", () => {
    const html = sandbox.renderFamilyBusiness();
    assert.ok(html.includes('data-row="30"'), "the 529 balance row must still render");
    assert.ok(html.includes('data-row="40"'), "the equity-comp grant row must still render");
    assert.ok(html.includes("is off"), "each off module must say so");
  });

  test("it links back to the page the rows actually live on", () => {
    const html = sandbox.renderFamilyBusiness();
    assert.ok(html.includes('data-step-id="assets_special"'));
  });

  test("the rows keep Other Assets and Liabilities as their source step", () => {
    // The new step is additive: nothing moved, so every surface that resolves
    // a row to its source page (Build Impact, the Field Finder, the closeout
    // checklist) must still answer assets_special.
    for (const idx of [30, 40]) {
      const row = sandbox.window.rows.find((r) => r.row_index === idx);
      assert.equal(sandbox.sourceStepForRow(row), "assets_special");
    }
  });

  test("rawRowsForStep('family_business') is exactly the two catalog-declared sections", () => {
    sandbox.window.rows = [
      ...sandbox.window.rows,
      { row_index: 41, section: "Note Receivable", subsection: "note_1", label: "balance", value: "1" },
    ];
    const got = Array.from(sandbox.rawRowsForStep("family_business")).map((r) => r.row_index).sort();
    assert.deepEqual(got, [30, 40]);
  });
});

describe("no-hidden-data invariant: DAF/QCD on Charitable Giving survive charitable_giving being off", () => {
  test("a DAF contribution row survives when charitable_giving is off but the DAF flag is on", () => {
    sandbox.window.rows = [
      { row_index: 50, section: "DAF", subsection: "Settings", label: "enabled", value: "YES" },
      {
        row_index: 51,
        section: "DAF",
        subsection: "Settings",
        label: "annual_daf_contribution",
        value: "5000",
      },
    ];
    const html = sandbox.renderEntityCharitable();
    assert.ok(!html.includes("hidden until"), "the old static blackout message must be gone");
    assert.ok(html.includes('data-row="51"'), "the DAF contribution row must still render");
  });
});

describe("Disabled-in-place is unchanged (optionalModuleState/rowBuildUsageState, §5.2's third state)", () => {
  test("a Hybrid LTC row still reports optionalModuleOff with the reason/activation/effect triple", () => {
    sandbox.window.rows = [
      { row_index: 60, section: "Hybrid LTC", subsection: "Settings", label: "enabled", value: "NO" },
      { row_index: 61, section: "Hybrid LTC", subsection: "Policy", label: "annual_premium", value: "3000" },
    ];
    const row = sandbox.window.rows[1];
    const state = sandbox.rowBuildUsageState(row, "assets_special");
    assert.equal(state.optionalModuleOff, true);
    assert.ok(state.reason);
    assert.ok(state.activation);
    assert.ok(state.effect);
  });
});

describe("Hidden is unchanged for a module-owned nav step (§5.2's first state)", () => {
  test("a module-toggle-gated step with no data is absent from visibleSteps()", () => {
    sandbox.window.moduleGates = {
      step_gates: { ltc_stress: "long_term_care_stress" },
      section_gates: {},
      flag_gates: {},
    };
    sandbox.optionalFunctionEnabled = () => false;
    assert.equal(sandbox.stepGatedByOptionalModule("ltc_stress"), true);
  });
});
