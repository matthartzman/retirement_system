// ZIP-first location entry for a Spending -> Housing "next step" (design
// 2026-09-16-housing-financing-and-zip-ux). Stubs the row-model globals
// (rows/dirty/editValue/renderMain/api) the same way
// housing_optimize_request.test.mjs stubs document.getElementById --
// dashboard_decomp_housing_scenarios.js is not a standalone ES module either.

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

function rowFixtures() {
  return [
    { row_index: 1, section: "Housing", subsection: "next_step_1", label: "state", value: "" },
    { row_index: 2, section: "Housing", subsection: "next_step_1", label: "city_type", value: "" },
    { row_index: 3, section: "Housing", subsection: "next_step_1", label: "population_size", value: "" },
    { row_index: 4, section: "Housing", subsection: "next_step_1", label: "zip_code", value: "" },
  ];
}

function mountWithZipApi(apiResponse) {
  // dashboard.js declares `let rows`/`let dirty`/`let renderMain` at its top
  // level, bridged onto `window` via explicit get/set accessors
  // (Object.defineProperty) for cross-module access -- see
  // housing_cost_reestimate.test.mjs's header comment for the full
  // explanation. Only `sandbox.window.rows = ...` (etc.) actually reaches the
  // internal binding every top-level function shares; `sandbox.rows = ...`
  // would silently create an unrelated plain property and never be seen by
  // resolveHousingStepZip's own bare `rows`/`dirty`/`renderMain` references.
  // `api` is a real `export async function`, so it DOES become a plain
  // global property and `sandbox.api = ...` works directly.
  const sandbox = loadDashboardSandbox();
  const rowsArr = rowFixtures();
  sandbox.window.rows = rowsArr;
  const dirtyMap = new Map();
  sandbox.window.dirty = dirtyMap;
  let renderCount = 0;
  sandbox.window.renderMain = () => {
    renderCount++;
  };
  let calledUrl = null;
  sandbox.api =
    typeof apiResponse === "function"
      ? async (url) => {
          calledUrl = url;
          return apiResponse(url);
        }
      : async (url) => {
          calledUrl = url;
          return apiResponse;
        };
  return {
    sandbox,
    rows: rowsArr,
    dirty: dirtyMap,
    getRenderCount: () => renderCount,
    getCalledUrl: () => calledUrl,
  };
}

describe("resolveHousingStepZip", () => {
  test("a valid ZIP fills state, city_type, and population_size", async () => {
    const { sandbox, rows, dirty, getCalledUrl } = mountWithZipApi({
      success: true, city: "Hinsdale", state: "Illinois", area_type: "suburban", population: 17349,
    });
    await sandbox.resolveHousingStepZip(1, "60521");
    assert.match(getCalledUrl(), /zip-lookup\?zip=60521/);
    const stateRow = rows.find((r) => r.row_index === 1);
    const cityTypeRow = rows.find((r) => r.row_index === 2);
    const popRow = rows.find((r) => r.row_index === 3);
    assert.equal(dirty.get(stateRow.row_index), "Illinois");
    assert.equal(dirty.get(cityTypeRow.row_index), "suburban");
    assert.equal(dirty.get(popRow.row_index), "17349");
  });

  test("a valid ZIP is cached for the read-only City/State display", async () => {
    const { sandbox } = mountWithZipApi({
      success: true, city: "Hinsdale", state: "Illinois", area_type: "suburban", population: 17349,
    });
    await sandbox.resolveHousingStepZip(1, "60521");
    assert.equal(sandbox.window.housingStepZipLookup[1].city, "Hinsdale");
    assert.equal(sandbox.window.housingStepZipLookup[1].state, "Illinois");
    assert.ok(!sandbox.window.housingStepZipLookup[1].error);
  });

  test("an invalid ZIP records an error and leaves existing state alone", async () => {
    // In production, api()'s RetirementApiClient.request() throws on any
    // non-2xx response, and the real /api/housing/zip-lookup endpoint always
    // signals failure via HTTP status -- never via a 200 body with
    // `success: false`. So the realistic mock here is a rejection, which
    // drives resolveHousingStepZip's `catch` branch, not its
    // `!payload.success` branch.
    const { sandbox, rows, dirty } = mountWithZipApi(async () => {
      throw new Error("ZIP 00000 not recognized.");
    });
    dirty.clear();
    const stateRow = rows.find((r) => r.row_index === 1);
    stateRow.value = "Colorado";
    await sandbox.resolveHousingStepZip(1, "00000");
    assert.equal(dirty.has(stateRow.row_index), false, "state must not be touched");
    assert.equal(
      sandbox.window.housingStepZipLookup[1].error,
      "Error looking up ZIP: ZIP 00000 not recognized."
    );
  });

  test("a defensive 200-with-success:false body also records its error and leaves state alone (not the primary production path -- the real endpoint always fails via HTTP status -- but resolveHousingStepZip guards against it anyway)", async () => {
    const { sandbox, rows, dirty } = mountWithZipApi({
      success: false, error: "ZIP 00000 not recognized.",
    });
    dirty.clear();
    const stateRow = rows.find((r) => r.row_index === 1);
    stateRow.value = "Colorado";
    await sandbox.resolveHousingStepZip(1, "00000");
    assert.equal(dirty.has(stateRow.row_index), false, "state must not be touched");
    assert.equal(sandbox.window.housingStepZipLookup[1].error, "ZIP 00000 not recognized.");
  });

  test("re-renders after a lookup so the read-only display and auto-filled selects update", async () => {
    const { sandbox, getRenderCount } = mountWithZipApi({
      success: true, city: "Hinsdale", state: "Illinois", area_type: "suburban", population: 17349,
    });
    await sandbox.resolveHousingStepZip(1, "60521");
    assert.equal(getRenderCount(), 1);
  });
});

describe("renderNextHousingStepSection -- ZIP-first field order", () => {
  test("ZIP is the first field, State renders read-only", () => {
    const sandbox = loadDashboardSandbox();
    const stepRows = [
      { row_index: 10, section: "Housing", subsection: "next_step_1", label: "type", value: "purchase" },
      { row_index: 11, section: "Housing", subsection: "next_step_1", label: "state", value: "Colorado" },
      { row_index: 12, section: "Housing", subsection: "next_step_1", label: "city_type", value: "suburban" },
      { row_index: 13, section: "Housing", subsection: "next_step_1", label: "population_size", value: "20000" },
      { row_index: 14, section: "Housing", subsection: "next_step_1", label: "zip_code", value: "" },
    ];
    const html = sandbox.renderNextHousingStepSection(stepRows, "Next Housing Step 1", 1);
    const zipIdx = html.indexOf("resolveHousingStepZip(1");
    const stateIdx = html.indexOf('data-row="11"');
    assert.ok(zipIdx >= 0, "ZIP input with a resolve handler must be present");
    assert.ok(zipIdx < stateIdx, "ZIP renders before State");
    // State is read-only display, not an editable <select>/<input data-row>:
    assert.ok(!/<select[^>]*data-row="11"/.test(html), "State must not be an editable select");
  });
});
