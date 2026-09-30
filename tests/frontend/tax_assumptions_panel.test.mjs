// Tax Assumptions card: pure formatting/parsing helpers.
import { test } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const s = loadDashboardSandbox();

const lever = (o = {}) => ({
  key: "state_income_tax_rate", label: "State income-tax rate", value: 0.05, source: "model",
  model_value: 0.05, basis: "state_tax.csv <b>", warning: "", drifted: false, ...o,
});

test("taxPct formats fractions as percents", () => {
  assert.equal(s.taxPct(0.02), "2%");
  assert.equal(s.taxPct(0.0525), "5.25%");
  assert.equal(s.taxPct(0.85), "85%");
  assert.equal(s.taxPct(null), "n/a");
});

test("taxOverrideText only prefills for overrides", () => {
  assert.equal(s.taxOverrideText(lever()), "");
  assert.equal(s.taxOverrideText(lever({ source: "override", value: 0.03 })), "3%");
});

test("taxEffectiveText parses percent and decimal, blank is Auto", () => {
  const lv = lever();
  assert.equal(s.taxEffectiveText(lv, undefined), "5%");
  assert.equal(s.taxEffectiveText(lv, "3%"), "3%");
  assert.equal(s.taxEffectiveText(lv, "0.03"), "3%");
  assert.equal(s.taxEffectiveText(lv, ""), "5% (Auto)");
  assert.equal(s.taxEffectiveText(lv, "abc"), "invalid");
});

test("taxChangedOverrides returns only changed rows; blank resets", () => {
  const a = lever();
  const b = lever({ key: "fed_tax_bracket_inflator", source: "override", value: 0.03 });
  const out = s.taxChangedOverrides([a, b], { [a.key]: "4%", [b.key]: "" });
  assert.deepEqual({ ...out }, { [a.key]: "4%", [b.key]: "" });
  assert.deepEqual({ ...s.taxChangedOverrides([a, b], { [a.key]: "", [b.key]: "3%" }) }, {});
});

test("card html escapes text and shows warning, drift, badge", () => {
  const p = {
    levers: [lever({ warning: "<script>x</script>", drifted: true, baseline_model_value: 0.04, source: "override", value: 0.03 })],
    residency_periods: [{ state: "CA", start_year: 2026, end_year: 2030, model_rate: 0.09 }, { state: "TX", start_year: 2031, end_year: 2060, model_rate: 0 }],
    law_table: { year: 2026, dataset_version: "v10", source: "src", standard_deduction: { MFJ: 32200 }, niit_threshold: { MFJ: 250000 },
      ltcg_brackets: { MFJ: { zero_top: 98900, fifteen_top: 613700 } }, salt_cap: 40400,
      ordinary_brackets: { MFJ: [{ lower: 0, upper: 24800, rate: 0.1 }, { lower: 24800, upper: null, rate: 0.12 }] } },
  };
  const h = s.taxAssumptionsCardHtml(p, {}, "bad <b>input</b>", false);
  assert.ok(!h.includes("<script>x"));
  assert.ok(h.includes("&lt;script&gt;"));
  assert.ok(h.includes("&lt;b&gt;input"));
  assert.ok(h.includes("Model value changed from 4% to 5% since you overrode."));
  assert.ok(h.includes("Override</span>"));
  assert.ok(h.includes("$32,200") && h.includes("$40,400") && h.includes("Tax law in use (read-only)"));
  assert.ok(h.includes("CA 2026 to 2030: 9%"));
  assert.ok(h.includes("and up"));
});

test("card html without payload shows loading / error", () => {
  assert.ok(s.taxAssumptionsCardHtml(null, {}, "", true).includes("Loading tax assumptions"));
  assert.ok(s.taxAssumptionsCardHtml(null, {}, "nope", false).includes("nope"));
});
