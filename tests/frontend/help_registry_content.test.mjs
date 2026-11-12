// W2-08 / DOC-001: the help registry names no retired page, defines the headline measures, and the
// success-rate guidance is a convention, not a recommendation. Length and abbreviation limits are
// checked in tests/test_help_registry_length_and_abbreviations_regression.py.
import { test } from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const reg = await import("../../frontend/js/help_registry.js");
const everything = JSON.stringify([reg.HELP_PAGES, reg.HELP_SECTIONS, reg.GLOSSARY]);

test("help_registry names no retired page, and no path to a file that does not exist", () => {
  for (const name of ["Spending Analysis", "Income & Expense Transactions", "Reports & Review", "Reports and Review", "Preflight tab", "Welcome page", "reference_data/"]) {
    assert.ok(!everything.includes(name), `help text still says ${name}`);
  }
});

test("the glossary defines the headline measures a page uses", () => {
  for (const term of ["Terminal net worth", "Probability of success", "Lifetime consumption-and-transfer value (LCV)", "Allocation sleeve", "Key performance indicator (KPI)"]) {
    assert.ok(reg.GLOSSARY[term] && reg.GLOSSARY[term].length > 30, term);
  }
  for (const [pid, rec] of Object.entries(reg.HELP_PAGES)) {
    for (const t of rec.terms || []) assert.ok(reg.GLOSSARY[t], `${pid} lists the undefined term ${t}`);
  }
});

test("the 80-90% success-rate guidance is presented as a planning convention", () => {
  const dash = loadDashboardSandbox();
  const text = vm.runInContext("FIELD_GUIDANCE_OVERRIDES.market_luck_stress_test.consider", dash);
  assert.match(text, /common planning convention, not a recommendation for your household/);
  assert.doesNotMatch(text, /^Aim for/);
});
