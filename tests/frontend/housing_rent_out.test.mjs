// WP12.8: Keep and rent out in the housing optimizer panel (dashboard_decomp_housing_optimizer.js),
// the Phase 1 "no rental income" disclosure kept while Rental Properties is off and replaced while
// it is on, and the Convert my home links into Rental Properties' convert dialog.
import { test, describe, afterEach } from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();
const realOptional = sandbox.optionalFunctionEnabled;
const realSetStep = sandbox.setStep;
const run = (code) => vm.runInContext(code, sandbox);
const featureOn = (on) => {
  sandbox.optionalFunctionEnabled = (k) => on && k === "rental_property_income";
};
const helpText = (key) => run(`JSON.stringify(HOUSING_OPT_FIELD_HELP[${JSON.stringify(key)}])`);

afterEach(() => {
  sandbox.optionalFunctionEnabled = realOptional;
  sandbox.setStep = realSetStep;
});

describe("feature off: unchanged", () => {
  test("no rent-out option, no rent field, the Phase 1 disclosure stays", () => {
    featureOn(false);
    const html = sandbox.renderHousingOptimizePanelHtml();
    assert.ok(!html.includes('value="rent_out"'));
    assert.ok(!html.includes("housingOptRentOutRent"));
    assert.match(html, /Auto \(search both\)/);
    assert.match(html, /Rental income from a kept home is not modelled/);
    assert.match(helpText("_panel"), /no rental income is modelled/);
    assert.match(helpText("_panel"), /Phase 1 limitation/);
    assert.match(helpText("housingOptDisposition"), /No rental income is modelled for a kept home/);
    assert.match(helpText("housingOptNoDualOwnership"), /no rental income exists/);
  });
});

describe("feature on: keep and rent out", () => {
  test("the option and the rent field appear; the disclosure text is gone", () => {
    featureOn(true);
    const html = sandbox.renderHousingOptimizePanelHtml();
    assert.match(html, /<option value="rent_out">Keep and rent out<\/option>/);
    assert.match(html, /id="housingOptRentOutRent"/);
    assert.match(html, /Auto \(search all\)/);
    assert.ok(!/not modelled/i.test(html));
    for (const key of ["_panel", "housingOptDisposition", "housingOptNoDualOwnership"]) {
      const text = helpText(key);
      assert.ok(!/no rental income|phase 1|phase 2/i.test(text), `${key}: ${text}`);
    }
    assert.match(helpText("housingOptDisposition"), /Keep and rent out/);
    assert.match(helpText("housingOptRentOutRent"), /No rent is ever suggested/);
  });

  test("a rent-out result row says so and links to Convert my home with its year", () => {
    featureOn(true);
    const html = sandbox.renderHousingOptimizeResultsHtml({
      objective: "net_worth", baseline_objective_value: null,
      candidates: [{
        rank: 1, original_home: { disposition: "rent_out", sale_year: null, conversion_year: 2028 },
        moves: [], net_worth: 1, lifetime_cost: 1, objective_value: 1,
        notes: ["rented out from 2028", "§121 two-of-five: exclusion only if sold by 2031"],
      }],
    });
    assert.match(html, /Keep and rent out/);
    assert.match(html, /rpConvertFromHousing\(2028, housingOptDomNum\('housingOptRentOutRent'\)\)/);
    assert.match(html, /exclusion only if sold by 2031/);
  });
});

describe("Convert my home from Next Housing Move", () => {
  test("opens Rental Properties with the dialog pre-filled from the move year and rent", () => {
    let step = "";
    sandbox.setStep = (s) => { step = s; };
    run(`rpData = { success: true, enabled: true, count: 0, properties: [], table: [], warnings: [],
      summary: {}, estimate: {}, home: { available: true, label: "Home", adjusted_basis: 500000,
      appreciation: 0.03, conversion_year: 2028, value_at_conversion: 1000000 } };`);
    sandbox.rpConvertFromHousing(2030, 4200);
    assert.equal(step, "rental_properties");
    const html = sandbox.renderRentalProperties();
    assert.match(html, /id="rpConvYear"[^>]*value="2030"/);
    assert.match(html, /id="rpConvRent"[^>]*value="4200"/);
    assert.match(html, /id="rpConvValue"[^>]*value="1060900"/);
    run("rpConvert = null; rpData = null;");
  });

  test("no prefill once the home is already converted", () => {
    sandbox.setStep = () => {};
    run(`rpData = { success: true, enabled: true, count: 1, properties: [{ name: "Our house", kind: "converted_home" }],
      table: [], warnings: [], summary: {}, estimate: {}, home: { available: true, conversion_year: 2028, value_at_conversion: 1 } };`);
    sandbox.rpConvertFromHousing(2030, 4200);
    assert.ok(!sandbox.renderRentalProperties().includes("rpConvRent"));
    run("rpConvert = null; rpData = null;");
  });

  test("Next Housing Move shows the link only while the feature is on", () => {
    featureOn(false);
    assert.ok(!sandbox.nextHousingMoveInputsHtml([]).includes("rpConvertFromHousing"));
    featureOn(true);
    assert.match(sandbox.nextHousingMoveInputsHtml([]), /onclick="rpConvertFromHousing\(\)">Convert my home to a rental/);
  });
});
