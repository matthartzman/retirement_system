// T1c (system review 2026-07-21, D1): the "What the model used in this build"
// survivor/estate narrative must spell out QSS/CST instead of using bare
// acronyms, and both terms must be registered in the app's own glossary so
// acronymDefinitionsHtml() picks them up as defense in depth.
import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();

function summaryWithEstateAssumptions() {
  return {
    model_heard_assumptions: {
      tax_and_estate: {
        cst_funded_total: 250000,
        basis_step_up_at_death: true,
        basis_step_up_property_regime: "community property",
        credit_shelter_trust_enabled: true,
        federal_portability_enabled: false,
      },
    },
  };
}

describe("modelHeardHtml estate/survivor narrative", () => {
  test("spells out Qualifying Surviving Spouse and Credit-Shelter Trust inline", () => {
    const html = sandbox.modelHeardHtml(summaryWithEstateAssumptions());
    assert.match(html, /Qualifying Surviving Spouse/);
    assert.match(html, /credit-shelter trust/i);
  });

  test("appends an Acronym definitions block naming QSS and CST", () => {
    const html = sandbox.modelHeardHtml(summaryWithEstateAssumptions());
    assert.match(html, /Acronym definitions/);
    assert.match(html, /<b>QSS<\/b>/);
    assert.match(html, /<b>CST<\/b>/);
  });
});

describe("ACRONYM_DEFINITIONS glossary", () => {
  test("QSS and CST resolve to their definitions via the glossary lookup", () => {
    const html = sandbox.acronymDefinitionsHtml(["QSS CST"]);
    assert.match(html, /<b>QSS<\/b>: Qualifying Surviving Spouse/);
    assert.match(html, /<b>CST<\/b>: Credit-Shelter Trust/);
  });
});
