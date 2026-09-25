// #336 (spec §4): Large Discretionary is one section -- the Large
// Discretionary accordion -- with five categories, one-time rows only, and no
// Annualized figure anywhere.

import { test, describe, beforeEach } from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();
const run = (code) => vm.runInContext(code, sandbox);
const THIS_YEAR = new Date().getFullYear();

function ldModel() {
  return {
    tracking_types: [
      { tracking_type: "Core Expenses", groups: [{ group: "Food", categories: [{ id: "groceries", label: "Groceries" }] }] },
      { tracking_type: "Large Discretionary", groups: [{ group: "Weddings", categories: [{ id: "weddings", label: "Weddings" }] }] },
    ],
  };
}

function ldBody(html) {
  const start = html.indexOf('data-dkey="budget:core:Large Discretionary"');
  assert.ok(start >= 0, "Large Discretionary accordion missing");
  const next = html.indexOf('class="taxonomy-type-section"', start + 1);
  return html.slice(start, next < 0 ? undefined : next);
}

function setOptional529(on) {
  sandbox.optionalFunctionEnabled = (label) => on && label === "education_funding_529";
}

beforeEach(() => {
  sandbox.__lines = [
    { section: "large_discretionary", line_id: "w1", label: "Wedding", category_id: "weddings", one_time_year: "2031", amount_per_year: "60000", notes: "first child" },
    { section: "large_discretionary", line_id: "c1", label: "Auto", category_id: "ld_auto", one_time_year: String(THIS_YEAR), amount_per_year: "45000", notes: "" },
  ];
  sandbox.__model = ldModel();
  run(`spendingModelData = globalThis.__model; taxonomyData = globalThis.__model.tracking_types;
       taxBudgetLoaded = true; budgetLinesLoaded = true; spendingModelLoading = false; spendingModelError = "";
       searchText = ""; rows = []; budgetLines = globalThis.__lines;`);
  sandbox.rowsForStep = () => [];
  setOptional529(false);
});

describe("Large Discretionary section (#336)", () => {
  test("category pulldown equals LD_CATEGORIES, Education labelled not-529", () => {
    assert.deepEqual([...run("LARGE_DISC_TYPES")], ["Weddings", "Large Gifts", "Education", "Auto", "Other"]);
    const html = sandbox.renderLargeDiscretionaryBudgetPage();
    const select = html.match(/<select[^>]*updateLargeDiscLine[^>]*>(.*?)<\/select>/)[1];
    const labels = [...select.matchAll(/<option[^>]*>([^<]*)<\/option>/g)].map((m) => m[1]);
    assert.deepEqual(labels, ["Weddings", "Large Gifts", "Education (not 529-funded)", "Auto", "Other"]);
  });

  test("rows have Amount, Year, Note, In budget and no start/end-year inputs", () => {
    const html = sandbox.renderLargeDiscretionaryBudgetPage();
    const headers = [...html.matchAll(/<th>([^<]*)<\/th>/g)].map((m) => m[1]);
    for (const h of ["Category", "Amount", "Year", "Note", "In budget"]) assert.ok(headers.includes(h), h);
    assert.doesNotMatch(html, /start_year|end_year|Repeat Start|Repeat End/);
  });

  test("In budget marks only rows dated this year", () => {
    const cells = [...sandbox.renderLargeDiscretionaryBudgetPage().matchAll(/class="large-disc-in-budget"[^>]*>([^<]*)</g)].map((m) => m[1]);
    assert.deepEqual(cells, ["—", "✓"]);
  });

  test("the accordion shows no Annualized figure; other types still do", () => {
    const html = sandbox.renderDomainBudgetTable("core");
    const body = ldBody(html);
    assert.doesNotMatch(body, /Annualized/);
    assert.match(body, /class="lot-table large-disc-table"/);
    assert.match(html.slice(0, html.indexOf('data-dkey="budget:core:Large Discretionary"')), /Annualized/);
  });

  test("double-count caution only when education_funding_529 is on", () => {
    assert.doesNotMatch(sandbox.renderLargeDiscretionaryBudgetPage(), /large-disc-529-caution/);
    setOptional529(true);
    assert.match(sandbox.renderLargeDiscretionaryBudgetPage(), /large-disc-529-caution/);
  });

  test("legacy repeatable rows expand to one row per year with a notice", () => {
    const lines = [{ section: "large_discretionary", line_id: "v", label: "Vehicle", category_id: "ld_auto", start_year: "2026", end_year: "2037", amount_per_year: "10000" }];
    const notices = sandbox.migrateLargeDiscLines(lines, 2056);
    assert.deepEqual(lines.map((l) => Number(l.one_time_year)), Array.from({ length: 12 }, (_, i) => 2026 + i));
    assert.ok(lines.every((l) => !l.start_year && !l.end_year));
    assert.equal(notices.length, 1);
    assert.match(notices[0], /Core category/);
  });

  test("changing the category re-points the line to its taxonomy id", () => {
    run("markBudgetLinesDirty = function () {};");
    sandbox.updateLargeDiscLine("w1", "type", "Education");
    assert.equal(sandbox.__lines[0].category_id, "ld_education");
  });
});
