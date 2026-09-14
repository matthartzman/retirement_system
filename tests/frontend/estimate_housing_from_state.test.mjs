// Slice 1 (housing-estimate-realism-and-dollar-convention-design.md, §3.2/
// §3.4/H3): estimateHousingFromState() must thread start_year/home_appr/
// inflation_general into the POST body (so the backend can translate
// today's-dollars estimates to start_year dollars) and must surface the
// returned note instead of discarding it. It must also require Area Type
// and Population for rent steps now, not just purchase.

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();

function purchaseStepRows() {
  return [
    { row_index: 1, section: "Housing", subsection: "next_step_1", label: "state", value: "IL" },
    { row_index: 2, section: "Housing", subsection: "next_step_1", label: "type", value: "purchase" },
    { row_index: 3, section: "Housing", subsection: "next_step_1", label: "city_type", value: "suburban" },
    { row_index: 4, section: "Housing", subsection: "next_step_1", label: "population_size", value: "20000" },
    { row_index: 5, section: "Housing", subsection: "next_step_1", label: "start_year", value: "2035" },
    { row_index: 6, section: "Housing", subsection: "next_step_1", label: "purchase_price", value: "" },
    { row_index: 7, section: "Other Assets", subsection: "Home", label: "appreciation_rate", value: "3.00%" },
    { row_index: 8, section: "Economic Assumptions", subsection: "", label: "inflation_general", value: "2.50%" },
  ];
}

function withStubs(rows, fn) {
  sandbox.window.rows = rows;
  window_housingLastEstimateReset(sandbox);
  const messages = [];
  sandbox.showMessage = (msg) => messages.push(msg);
  sandbox.renderMain = () => {};
  sandbox.window.applyHousingEstimateField = () => true;
  return fn(rows, messages);
}

function window_housingLastEstimateReset(sandbox) {
  sandbox.window.housingLastEstimate = {};
}

describe("estimateHousingFromState (Slice 1 dollar-convention threading)", () => {
  test("POST body includes start_year/home_appr/inflation_general from the plan's rows", async () => {
    await withStubs(purchaseStepRows(), async (rows, messages) => {
      let capturedBody = null;
      sandbox.api = async (path, opts) => {
        capturedBody = JSON.parse(opts.body);
        return {
          estimate: {
            purchase_price: 500000,
            note: "Estimated costs for a 3BR/2BA home ... Reflects 2035 dollars: today's $400,000 projected to $500,000 (9 years out). All values are editable.",
          },
        };
      };
      await sandbox.estimateHousingFromState(1);
      assert.equal(capturedBody.state, "IL");
      assert.equal(capturedBody.start_year, 2035);
      assert.equal(capturedBody.home_appr, 0.03);
      assert.equal(capturedBody.inflation_general, 0.025);
      assert.ok(
        messages.some((m) => m.includes("Reflects 2035 dollars")),
        "note text should be surfaced via showMessage",
      );
    });
  });

  test("blank start_year is sent as an empty string, not NaN", async () => {
    const rows = purchaseStepRows();
    const startRow = rows.find((r) => r.label === "start_year");
    startRow.value = "";
    await withStubs(rows, async (_rows, _messages) => {
      let capturedBody = null;
      sandbox.api = async (path, opts) => {
        capturedBody = JSON.parse(opts.body);
        return { estimate: { purchase_price: 400000, note: "note" } };
      };
      await sandbox.estimateHousingFromState(1);
      assert.equal(capturedBody.start_year, "");
    });
  });

  test("rent steps now require Area Type and Population before estimating", async () => {
    const rows = [
      { row_index: 1, section: "Housing", subsection: "next_step_2", label: "state", value: "TX" },
      { row_index: 2, section: "Housing", subsection: "next_step_2", label: "type", value: "rent" },
      { row_index: 3, section: "Housing", subsection: "next_step_2", label: "city_type", value: "" },
      { row_index: 4, section: "Housing", subsection: "next_step_2", label: "population_size", value: "" },
    ];
    await withStubs(rows, async (_rows, messages) => {
      let called = false;
      sandbox.api = async () => {
        called = true;
        return { estimate: {} };
      };
      await sandbox.estimateHousingFromState(2);
      assert.equal(called, false, "should not call the API before Area Type/Population are set");
      assert.ok(messages.some((m) => /Area Type/i.test(m)));
    });
  });
});
