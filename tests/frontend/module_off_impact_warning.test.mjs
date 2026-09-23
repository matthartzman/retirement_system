// #330 §3.4 (master plan W5): the reverse-direction warning on an optional
// module's switch.
//
// `degrades_without` is declared on the module that shows less, but the
// question a user actually has is at the switch they are about to flip --
// "what do I lose if I turn this off?" -- so the catalog's relation is served
// reversed (config_service._module_taxonomy's `degraded_by`) and rendered
// here. The spec's own worked example is the sentence pinned below.
//
// The helper lives in dashboard_decomp_row_model.js rather than dashboard.js
// because dashboard.js is 6 lines under its size ratchet; that placement is
// deliberate, so this test reaches it through the same whole-page sandbox the
// browser would.

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();

// Shaped exactly as _module_taxonomy() serves it. `name` rides along on each
// entry so the sentence needs no second lookup.
//
// The taxonomy is passed in explicitly rather than assigned onto the sandbox:
// the helper takes it as a parameter precisely so it can be exercised without
// standing up the payload fetch (and because a module-scoped `let` is a
// lexical binding the vm sandbox cannot reach from outside).
function warn(key, modules) {
  return sandbox.moduleOffImpactWarning(key, { domains: [], kind_questions: {}, modules });
}

const MONTE_CARLO = {
  name: "Monte Carlo",
  degraded_by: [
    { key: "executive_summary", name: "Executive Summary", loses: "the success-probability headline" },
    { key: "charts_dashboard", name: "Charts", loses: "the fan chart" },
  ],
};

describe("moduleOffImpactWarning", () => {
  test("names every output the switch's module takes with it", () => {
    // The spec's worked example, verbatim: this exact sentence is what #330
    // §3.4 calls "the single highest-value thing this field buys".
    assert.equal(
      warn("market_luck_stress_test", { market_luck_stress_test: MONTE_CARLO }),
      "Turning Monte Carlo off also removes the success-probability headline " +
        "from Executive Summary and the fan chart from Charts.",
    );
  });

  test("a single dependent reads as a sentence, not a one-item list", () => {
    assert.equal(
      warn("social_security_timing", {
        social_security_timing: {
          name: "Social Security",
          degraded_by: [
            { key: "executive_summary", name: "Executive Summary", loses: "the optimal claim-age line" },
          ],
        },
      }),
      "Turning Social Security off also removes the optimal claim-age line from Executive Summary.",
    );
  });

  test("three or more dependents get separating commas plus a trailing 'and'", () => {
    assert.equal(
      warn("mc", {
        mc: {
          name: "Monte Carlo",
          degraded_by: [
            ...MONTE_CARLO.degraded_by,
            { key: "planning_levers_echo", name: "Planning Levers", loses: "the model anchor" },
          ],
        },
      }),
      "Turning Monte Carlo off also removes the success-probability headline from " +
        "Executive Summary, the fan chart from Charts and the model anchor from Planning Levers.",
    );
  });

  test("says nothing when nothing degrades without the module", () => {
    // Most modules. The caller concatenates the result unconditionally, so an
    // empty string -- not a placeholder sentence -- is the contract.
    assert.equal(warn("glossary", { glossary: { name: "Glossary", degraded_by: [] } }), "");
  });

  test("is silent rather than broken before the payload has loaded", () => {
    // renderOptionalFunctions() can run on a page whose /api/config/rows call
    // has not resolved yet, so an unknown key, an empty taxonomy and a missing
    // one must all fall through to "" instead of throwing on a property of
    // undefined.
    assert.equal(warn("anything", {}), "");
    assert.equal(sandbox.moduleOffImpactWarning("market_luck_stress_test", {}), "");
    // No second argument at all: falls back to the module's own state, which
    // is still the pre-fetch default.
    assert.equal(sandbox.moduleOffImpactWarning("market_luck_stress_test"), "");
  });
});
