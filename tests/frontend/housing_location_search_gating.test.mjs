// #330 §3.2, Housing "Where to live": "The UI panel is hidden;
// `src/housing/` is not invoked". Until `housing_location_search` was
// catalogued there was no switch to gate on, so the Optimize screen's "Next
// Housing Move" section carried `gate: null` and the panel was
// unconditionally live. This suite covers the UI half of the off-semantics;
// the catalog record and the endpoint half are pinned in
// tests/test_housing_location_search_catalog.py.

import { test, describe, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();
const KEY = "housing_location_search";

beforeEach(() => {
  sandbox.window.rows = [];
  sandbox.window.dirty = new Map();
  sandbox.window.searchText = "";
  sandbox.window.moduleGates = {
    step_gates: { [KEY]: KEY },
    section_gates: {},
    flag_gates: {},
  };
  sandbox.window.moduleTaxonomy = {
    modules: { [KEY]: { name: "Housing Location Search", gate_kind: "module_toggle" } },
  };
});

describe("the location search's gate resolves through the server-declared map", () => {
  test("off when the toggle row says NO", () => {
    sandbox.window.rows = [
      { row_index: 1, section: "Optional Functions", label: KEY, value: "NO" },
    ];
    assert.equal(sandbox.stepGatedByOptionalModule(KEY), true);
  });

  test("on when the toggle row says YES", () => {
    sandbox.window.rows = [
      { row_index: 1, section: "Optional Functions", label: KEY, value: "YES" },
    ];
    assert.equal(sandbox.stepGatedByOptionalModule(KEY), false);
  });

  test("off when no row is loaded yet -- optionalFunctionEnabled()'s own default", () => {
    // Unlike the server-side module_enabled() (which defaults an absent key
    // to ENABLED so a build never silently drops an always-on sheet),
    // optionalFunctionEnabled() defaults to false when the toggle row is not
    // yet loaded into `rows` -- the same as every other module_toggle gate on
    // this map, not a housing-specific rule. The row is always present once
    // the plan is loaded (client_optional_functions.csv seeds it TRUE), so
    // this is a transient pre-load state, not the steady-state default.
    assert.equal(sandbox.stepGatedByOptionalModule(KEY), true);
  });
});

describe("the off-state is Collapsed-with-a-note, and the body is not built", () => {
  beforeEach(() => {
    sandbox.window.rows = [
      { row_index: 1, section: "Optional Functions", label: KEY, value: "NO" },
    ];
  });

  test("the section still renders, with the note in place of the panel", () => {
    let built = 0;
    const html = sandbox.strategySection(
      "housing",
      "Next Housing Move",
      () => {
        built += 1;
        return "<div id='housingOptPanel'>the panel</div>";
      },
      KEY,
      true,
    );
    assert.equal(built, 0, "the panel body must not be built while the module is off");
    assert.ok(!html.includes("housingOptPanel"));
    assert.ok(html.includes("Next Housing Move</summary>"), "the section header stays");
    assert.ok(html.includes("is off"));
  });

  test("the note offers the switch inline when the toggle row is loaded", () => {
    const html = sandbox.featureGatedNote(KEY, { title: "Next Housing Move" });
    assert.ok(html.includes("editValue(1,'YES',null)"));
  });

  test("on, the panel body IS built", () => {
    sandbox.window.rows = [
      { row_index: 1, section: "Optional Functions", label: KEY, value: "YES" },
    ];
    let built = 0;
    const html = sandbox.strategySection(
      "housing",
      "Next Housing Move",
      () => {
        built += 1;
        return "<div id='housingOptPanel'>the panel</div>";
      },
      KEY,
      true,
    );
    assert.equal(built, 1);
    assert.ok(html.includes("housingOptPanel"));
  });
});

describe("no-hidden-data: the switch owns no plan rows to hide", () => {
  test("the household's housing plan rows are not gated by this module", () => {
    // The search's own inputs are browser-local (HOUSING_OPT_STORAGE_KEY);
    // the plan's housing data lives on the always-on Home & Housing page and
    // is reached through a step this module does not gate.
    sandbox.window.rows = [
      { row_index: 50, section: "Housing", subsection: "Next Step 1", label: "purchase_price", value: "650000" },
      { row_index: 51, section: "Housing", subsection: "Home", label: "home_sale_yr", value: "2031" },
    ];
    sandbox.window.moduleGates.section_gates = {};
    assert.equal(sandbox.stepGatedByOptionalModule("assets_home_cash"), false);
    assert.equal(sandbox.stepGatedByOptionalModule("spending_housing"), false);
    // ...and the note, asked about this module, reports no retained rows --
    // because there are none behind it, not because it failed to look.
    const html = sandbox.featureGatedNote(KEY, { title: "Next Housing Move" });
    assert.ok(!html.includes("already-entered"));
  });
});
