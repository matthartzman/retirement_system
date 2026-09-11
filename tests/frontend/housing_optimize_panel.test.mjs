// Housing move optimizer panel
// (docs/superpowers/specs/2026-09-09-housing-optimization-design.md):
// renderHousingOptimizeResultsHtml() renders the §5 headline recommendation
// and ranked alternatives table (reusing this page's scenario-diff table
// styling); toggleHousingOptLocationRows()/toggleHousingOptMove2Fields()
// show/hide inputs; runHousingOptimization() gathers form values and posts
// to /api/housing/optimize.

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

function freshSandbox() {
  return loadDashboardSandbox();
}

function samplePayload() {
  return {
    success: true,
    schema: "housing_optimize_v1",
    objective: "net_worth",
    recommendation: {
      moves: [
        {
          sale_year: 2027,
          purchase_year: 2028,
          rent_indefinitely: false,
          location: { state: "Texas", city_type: "suburban", population_size: 150000 },
          sec121_exclusion_lost: false,
        },
      ],
      net_worth: 11447476.74,
      lifetime_cost: 607683.2,
      mc_success_rate: 1.0,
      objective_value: 11447476.74,
      family_presence_via_rental: false,
    },
    alternatives: [
      {
        moves: [
          {
            sale_year: 2028,
            purchase_year: null,
            rent_indefinitely: true,
            location: { state: "Florida", city_type: "urban", population_size: 300000 },
            sec121_exclusion_lost: false,
          },
        ],
        net_worth: 11375199.93,
        lifetime_cost: 576773.85,
        mc_success_rate: null,
        objective_value: 11375199.93,
        family_presence_via_rental: true,
      },
    ],
    candidates_evaluated: 12,
  };
}

describe("renderHousingOptimizePanelHtml", () => {
  test("renders location rows, search-window inputs, and the objective dropdown", () => {
    const sandbox = freshSandbox();
    const html = sandbox.renderHousingOptimizePanelHtml();
    assert.match(html, /id="housingOptLocState0"/);
    assert.match(html, /id="housingOptLocState1"/);
    assert.match(html, /id="housingOptEarliestSale"/);
    assert.match(html, /id="housingOptLatestPurchase"/);
    assert.match(html, /id="housingOptObjective"/);
    assert.match(html, /id="housingOptSearchMode"/);
    assert.match(html, /id="housingOptNoDualOwnership"[^>]*checked/);
    assert.match(html, /id="housingOptimizeResults"/);
  });

  test("hides candidate locations 3 and 4 by default", () => {
    const sandbox = freshSandbox();
    const html = sandbox.renderHousingOptimizePanelHtml();
    assert.match(html, /id="housingOptLocRow2" hidden/);
    assert.match(html, /id="housingOptLocRow3" hidden/);
  });
});

describe("toggleHousingOptLocationRows", () => {
  test("shows exactly as many location rows as selected", () => {
    const sandbox = freshSandbox();
    const elements = {
      housingOptLocCount: { value: "3" },
      housingOptLocRow0: { hidden: false },
      housingOptLocRow1: { hidden: false },
      housingOptLocRow2: { hidden: true },
      housingOptLocRow3: { hidden: true },
    };
    sandbox.document.getElementById = (id) => elements[id] || null;
    sandbox.toggleHousingOptLocationRows();
    assert.equal(elements.housingOptLocRow0.hidden, false);
    assert.equal(elements.housingOptLocRow1.hidden, false);
    assert.equal(elements.housingOptLocRow2.hidden, false);
    assert.equal(elements.housingOptLocRow3.hidden, true);
  });
});

describe("toggleHousingOptMove2Fields", () => {
  test("reveals the move-2 fields only when the checkbox is checked", () => {
    const sandbox = freshSandbox();
    const elements = {
      housingOptMove2Enabled: { checked: true },
      housingOptMove2Fields: { hidden: true },
    };
    sandbox.document.getElementById = (id) => elements[id] || null;
    sandbox.toggleHousingOptMove2Fields();
    assert.equal(elements.housingOptMove2Fields.hidden, false);
    elements.housingOptMove2Enabled.checked = false;
    sandbox.toggleHousingOptMove2Fields();
    assert.equal(elements.housingOptMove2Fields.hidden, true);
  });
});

describe("renderHousingOptimizeResultsHtml", () => {
  test("renders the headline recommendation and the ranked alternatives table", () => {
    const sandbox = freshSandbox();
    const html = sandbox.renderHousingOptimizeResultsHtml(samplePayload());
    assert.match(html, /Recommended/);
    assert.match(html, /Sell 2027/);
    assert.match(html, /Buy 2028/);
    assert.match(html, /Texas/);
    assert.match(html, /Florida/);
    assert.match(html, /Rent indefinitely/);
    assert.match(html, /family presence via rental/);
    assert.match(html, /scenario-diff-table/);
  });

  test("flags a lost §121 exclusion on the move it applies to", () => {
    const sandbox = freshSandbox();
    const payload = samplePayload();
    payload.recommendation.moves[0].sec121_exclusion_lost = true;
    const html = sandbox.renderHousingOptimizeResultsHtml(payload);
    assert.match(html, /likely loses.*121 exclusion/);
  });

  test("shows a no-candidates message when nothing satisfied the constraints", () => {
    const sandbox = freshSandbox();
    const html = sandbox.renderHousingOptimizeResultsHtml({ recommendation: null, alternatives: [] });
    assert.match(html, /No candidates satisfied/);
  });
});

describe("runHousingOptimization", () => {
  test("rejects when a candidate location has no state, without calling the API", async () => {
    const sandbox = freshSandbox();
    const elements = {
      housingOptLocCount: { value: "2" },
      housingOptLocState0: { value: "" },
      housingOptimizeResults: { innerHTML: "" },
    };
    sandbox.document.getElementById = (id) => elements[id] || { value: "" };
    let apiCalled = false;
    sandbox.api = async () => {
      apiCalled = true;
      return { success: true };
    };
    const messages = [];
    sandbox.showMessage = (msg, kind) => messages.push([msg, kind]);
    await sandbox.runHousingOptimization();
    assert.equal(apiCalled, false);
    assert.ok(messages.length >= 1);
    assert.match(messages[0][0], /state/i);
  });

  test("posts the gathered form values to /api/housing/optimize and renders the response", async () => {
    const sandbox = freshSandbox();
    const values = {
      housingOptLocCount: "2",
      housingOptLocState0: "Texas",
      housingOptLocCity0: "suburban",
      housingOptLocPop0: "150000",
      housingOptLocState1: "Florida",
      housingOptLocCity1: "urban",
      housingOptLocPop1: "300000",
      housingOptEarliestSale: "2027",
      housingOptLatestSale: "2028",
      housingOptEarliestPurchase: "2027",
      housingOptLatestPurchase: "2028",
      housingOptAnchorCount: "5",
      housingOptObjective: "net_worth",
      housingOptSearchMode: "narrowed",
    };
    const resultsEl = { innerHTML: "" };
    const noDualOwnership = { checked: true };
    const move2Enabled = { checked: false };
    sandbox.document.getElementById = (id) => {
      if (id === "housingOptimizeResults") return resultsEl;
      if (id === "housingOptNoDualOwnership") return noDualOwnership;
      if (id === "housingOptMove2Enabled") return move2Enabled;
      if (id in values) return { value: values[id] };
      return { value: "" };
    };
    let capturedUrl = null;
    let capturedBody = null;
    sandbox.api = async (url, opts) => {
      capturedUrl = url;
      capturedBody = JSON.parse(opts.body);
      return { success: true, recommendation: null, alternatives: [] };
    };
    await sandbox.runHousingOptimization();
    assert.equal(capturedUrl, "/api/housing/optimize");
    assert.equal(capturedBody.locations.length, 2);
    assert.equal(capturedBody.locations[0].state, "Texas");
    assert.equal(capturedBody.no_dual_ownership, true);
    assert.equal(capturedBody.search_mode, "narrowed");
    assert.equal(capturedBody.move2_window, undefined);
    assert.equal(capturedBody.move1_window.earliest_sale_year, 2027);
    assert.match(resultsEl.innerHTML, /No candidates satisfied/);
  });
});
