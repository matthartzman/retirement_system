// #330 P3 (master plan W4): the Plan Features page's decision logic.
//
// Everything that decides *what* the page says is a pure function taking its
// data as a parameter, so it can be exercised here; `renderOptionalFunctions()`
// itself reads shared mutable state (`rows`, `searchText`, `moduleStatus`) that
// the vm sandbox cannot reach, and is deliberately kept to assembling the
// strings these functions return.

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();

// Shaped as config_service._module_taxonomy() serves it.
const TAXONOMY = {
  domains: ["Income & Benefits", "Taxes", "Risk & Resilience", "Reports & Documentation"],
  kind_questions: {},
  modules: {
    social_security_timing: { name: "Social Security", kind: "optimization", domain: "Income & Benefits", demand: "high" },
    roth_conversion_plan: { name: "Roth Conversion", kind: "optimization", domain: "Taxes", demand: "high" },
    tax_loss_harvesting: { name: "Tax-Loss Harvesting", kind: "optimization", domain: "Taxes", demand: "low" },
    market_luck_stress_test: { name: "Monte Carlo", kind: "stress_test", domain: "Risk & Resilience", demand: "medium" },
  },
};

const row = (label, value = "YES") => ({ label, value, row_index: 1 });

// The helpers run inside the vm context, so every array they return comes from
// that realm's own Array constructor. Node's strict deepEqual compares
// prototypes, so a cross-realm array of identical primitives still fails as
// "same structure but not reference-equal" -- Array.from() rebuilds it with
// this realm's Array, which is all deepEqual needs once the elements are
// primitives. Same workaround, and same reason, as
// strategy_screen_rows_aggregate.test.mjs.
const here = (a) => Array.from(a);
const groups = (rows, taxonomy, kind) =>
  here(sandbox.planFeatureGroups(rows, taxonomy, kind)).map((g) => ({
    domain: g.domain,
    keys: here(g.entries).map((e) => e.key),
  }));

const TOGGLE_ROWS = [
  row("market_luck_stress_test"),
  row("tax_loss_harvesting"),
  row("social_security_timing"),
  row("roth_conversion_plan"),
];

describe("planFeatureGroups", () => {
  test("groups by domain in the catalog's own domain order", () => {
    assert.deepEqual(
      groups(TOGGLE_ROWS, TAXONOMY, "").map((g) => g.domain),
      ["Income & Benefits", "Taxes", "Risk & Resilience"],
    );
  });

  test("orders by demand within a domain, so common features surface first", () => {
    const taxes = groups(TOGGLE_ROWS, TAXONOMY, "").find((g) => g.domain === "Taxes");
    assert.deepEqual(taxes.keys, ["roth_conversion_plan", "tax_loss_harvesting"]);
  });

  test("a toggle with no catalog entry still renders, under Other", () => {
    // A switch that exists in the CSV but not the catalog is exactly the drift
    // this page should make visible. Dropping it would hide the bug.
    const gs = groups([...TOGGLE_ROWS, row("mystery_module")], TAXONOMY, "");
    assert.deepEqual(gs.find((g) => g.domain === "Other").keys, ["mystery_module"]);
    // ...and it sorts last, after every known domain.
    assert.equal(gs[gs.length - 1].domain, "Other");
  });

  test("the kind filter narrows to one kind and drops now-empty domains", () => {
    const gs = groups(TOGGLE_ROWS, TAXONOMY, "stress_test");
    assert.deepEqual(gs.map((g) => g.domain), ["Risk & Resilience"]);
    assert.deepEqual(gs[0].keys, ["market_luck_stress_test"]);
  });

  test("survives a taxonomy that has not loaded yet", () => {
    // Everything lands in "Other" with no demand to rank by, so the name
    // tiebreaker decides -- alphabetical, and deterministic, rather than
    // whatever order the CSV happened to be in.
    assert.deepEqual(groups(TOGGLE_ROWS, undefined, ""), [
      {
        domain: "Other",
        keys: [
          "market_luck_stress_test",
          "roth_conversion_plan",
          "social_security_timing",
          "tax_loss_harvesting",
        ],
      },
    ]);
    assert.deepEqual(groups(undefined, TAXONOMY, ""), []);
  });
});

describe("planFeatureKinds", () => {
  test("offers only kinds actually present among the toggle rows", () => {
    // Never a filter that would empty the page.
    assert.deepEqual(here(sandbox.planFeatureKinds(TOGGLE_ROWS, TAXONOMY)), [
      "optimization",
      "stress_test",
    ]);
  });

  test("is empty when nothing is classified", () => {
    assert.deepEqual(here(sandbox.planFeatureKinds([row("mystery_module")], TAXONOMY)), []);
  });
});

describe("envOverrideNotice", () => {
  test("says nothing on an ordinary run", () => {
    assert.equal(
      sandbox.envOverrideNotice({ a: { enabled: true, forced: null, forced_by: null } }),
      "",
    );
    assert.equal(sandbox.envOverrideNotice({}), "");
    assert.equal(sandbox.envOverrideNotice(undefined), "");
  });

  test("names the variables doing the forcing, and says the build is using them", () => {
    // #330 Q7: disclosure exists so the switch page cannot silently disagree
    // with what the build actually did.
    const notice = sandbox.envOverrideNotice({
      a: { forced: "enabled", forced_by: "RETIREMENT_SYSTEM_FORCE_ALL_MODULES" },
      b: { forced: "disabled", forced_by: "RETIREMENT_SYSTEM_FORCE_DISABLE_MODULES" },
      c: { forced: null, forced_by: null },
    });
    assert.match(notice, /^2 features are currently forced by /);
    assert.match(notice, /RETIREMENT_SYSTEM_FORCE_ALL_MODULES and RETIREMENT_SYSTEM_FORCE_DISABLE_MODULES/);
    assert.match(notice, /read-only here and the build is using the forced state/);
  });

  test("agrees with itself about one forced module", () => {
    const notice = sandbox.envOverrideNotice({
      a: { forced: "enabled", forced_by: "RETIREMENT_SYSTEM_FORCE_ENABLE_MODULES" },
    });
    assert.match(notice, /^1 feature is currently forced by RETIREMENT_SYSTEM_FORCE_ENABLE_MODULES\./);
  });
});

describe("enteredRowCount", () => {
  test("counts rows holding real values", () => {
    assert.equal(
      sandbox.enteredRowCount([
        { value: "250000" },
        { value: "Term life" },
        { value: "" },
        { value: "   " },
      ]),
      2,
    );
  });

  test("an off toggle is not entered data", () => {
    // Otherwise every module would report itself as holding one item -- its
    // own switch -- and the indicator would be noise on every row.
    assert.equal(
      sandbox.enteredRowCount([{ value: "NO" }, { value: "FALSE" }, { value: "0" }]),
      0,
    );
    assert.equal(sandbox.enteredRowCount([{ value: "YES" }]), 1);
  });

  test("survives missing and malformed input", () => {
    assert.equal(sandbox.enteredRowCount(undefined), 0);
    assert.equal(sandbox.enteredRowCount([null, {}, { value: null }]), 0);
  });
});

describe("demandHint", () => {
  test("translates the raw band into something a reader can act on", () => {
    assert.equal(sandbox.demandHint("high"), "Most plans use this");
    assert.equal(sandbox.demandHint("niche"), "Rarely needed");
  });

  test("says nothing for an unknown or absent band", () => {
    assert.equal(sandbox.demandHint(undefined), "");
    assert.equal(sandbox.demandHint("not_a_band"), "");
  });
});
