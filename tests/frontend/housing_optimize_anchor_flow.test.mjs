// The two-step anchor-flow panel (design 2026-09-19 §5.2/§5.3, #331 A1-A4).
//
// Follows the same corrected pattern as every other housing_optimize_*.test.mjs
// file (see housing_optimize_request.test.mjs's header for the full
// explanation of why): dashboard_decomp_housing_optimizer.js is not a
// standalone ES module, so this loads the real production source via
// loadDashboardSandbox() and drives the exported functions off a plain
// id->element stub map, the same as buildHousingOptRequest's own tests.
//
// Covers the five things the master plan's A4 line item names: quota
// rendering (the "covers {anchor}" badge and per-anchor coverage line),
// the selection round-trip (tick/untick reaching selected_zips), the
// client-side handling of a stale-selection rejection from the server,
// step gating (Continue disabled until every enabled move has a selection,
// re-enabled once it does), and that the coverage warning never blocks.

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

// A minimal, valid single-anchor "where" element set for one move, in the
// same shape housing_optimize_request.test.mjs's defaultElements() uses --
// just enough for housingOptMoveSearchBody()/validateHousingOptForm() to
// read a move's fields without throwing.
function moveElements(n, overrides = {}) {
  const p = `housingOptMove${n}`;
  const base = {
    [`${p}Earliest`]: { value: "2031" },
    [`${p}Latest`]: { value: "2046" },
    [`${p}Action`]: { value: "auto" },
    [`${p}Radius`]: { value: "25" },
    [`${p}MinScore`]: { value: "0" },
    [`${p}AreaType`]: { value: "any" },
    [`${p}MaxPopulation`]: { value: "" },
    [`${p}Bedrooms`]: { value: "3" },
    [`${p}Bathrooms`]: { value: "2" },
    [`${p}PropertyType`]: { value: "single_family" },
    [`${p}SqftBand`]: { value: "1800_2500" },
    [`${p}LotSize`]: { value: "quarter_half" },
    [`${p}BuiltWithin`]: { value: "" },
    [`${p}PriceMax`]: { value: "" },
    [`${p}Anchor0`]: { value: "city" },
    [`${p}AnchorCity0`]: { value: "80014" },
    [`${p}AnchorZip0`]: { value: "" },
  };
  return { ...base, ...overrides };
}

// A generic stand-in for any DOM element this file's stubbed
// getElementById is asked for but does not care about the contents of --
// mirrors load_dashboard.mjs's own stubElement() so setBuildOverlay's
// classList.toggle/setAttribute calls (showHousingOptOverlay's overlay,
// document.body) do not throw.
function domStub(overrides = {}) {
  return {
    style: {},
    classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
    setAttribute() {},
    addEventListener() {},
    appendChild() {},
    textContent: "",
    value: "",
    disabled: false,
    innerHTML: "",
    ...overrides,
  };
}

function baseElements() {
  return {
    housingOptObjective: { value: "net_worth" },
    housingOptSearchMode: { value: "full" },
    housingOptMove2Strategy: { value: "anchored" },
    housingOptNoDualOwnership: { checked: true },
    housingOptDownPaymentPct: { value: "20" },
    housingOptMortgageRatePct: { value: "6.85" },
    housingOptPresenceEnabled: { checked: false },
    housingOptDisposition: { value: "auto" },
    housingOptEarliestSale: { value: "2030" },
    housingOptLatestSale: { value: "2045" },
    housingOptMove2Enabled: { checked: false },
    ...moveElements(1),
    ...moveElements(2),
    housingOptRun: { disabled: false },
    housingOptContinue: { disabled: true },
    housingOptFind: {},
    housingOptStep1: { hidden: false },
    housingOptStep2: { hidden: true },
    housingOptStepIndicator: { textContent: "" },
    housingOptStep1Validation: { hidden: true, textContent: "" },
    housingOptValidation: { hidden: true, textContent: "" },
    housingOptSelectedSummary: { innerHTML: "" },
    housingOptimizeResults: { innerHTML: "" },
    actionMessage: domStub(),
    buildOverlay: domStub(),
  };
}

// Mounts a fresh sandbox with `elements` stubbed behind document.getElementById
// and `apiResponses` behind the module's `api()` global (a plain export, so
// direct assignment reaches every call site -- see
// housing_step_zip_lookup.test.mjs's header for why that differs from the
// window-bridged `rows`/`dirty` globals). `apiResponses` maps a URL substring
// to the payload (or a function of the request body) that call should
// resolve with.
function mount(overrides = {}, apiResponses = {}) {
  const elements = { ...baseElements(), ...overrides };
  const sandbox = loadDashboardSandbox();
  sandbox.document.getElementById = (id) => elements[id] || domStub();
  sandbox.document.body = sandbox.document.body || domStub();
  const calls = [];
  sandbox.api = async (url, opts = {}) => {
    const body = opts.body ? JSON.parse(opts.body) : {};
    calls.push({ url, body });
    for (const [key, resp] of Object.entries(apiResponses)) {
      if (url.includes(key)) return typeof resp === "function" ? resp(body) : resp;
    }
    throw new Error(`no stubbed api() response for ${url}`);
  };
  return { sandbox, elements, calls };
}

// A screen response with three passing ZIPs: two near anchor 80014 (one of
// which the quota reserves) and one near a second anchor, 60521 -- the
// shape needed to exercise the quota badge and the anchor coverage line.
function screenPayload() {
  const row = (zip, nss, anchor, quota) => ({
    zip, city: `City${zip}`, state: "CO", distance_miles: 3.1, nss, band: "Mixed",
    coverage_pct: 78.8, est_price: 400000, est_price_move_year: 420000,
    est_price_basis_year: 2026, est_price_reference_year: 2038,
    components: {}, upi_adjusted: false, cross_state: null, promoted: quota,
    collapsed: [], area_type: "suburban", population: 12000,
    nearest_anchor_zip: anchor, family_distance_miles: null, quota_reserved: quota,
  });
  return {
    success: true,
    zip_screen: {
      schema: "zip_screen_v2", score_model: "v1", disclosure: "Measures housing stability.",
      anchor: { zip: "80014", city: "Aurora", state: "CO" },
      anchors: [
        { zip: "80014", city: "Aurora", state: "CO" },
        { zip: "60521", city: "Hinsdale", state: "IL" },
      ],
      radius_miles: 25,
      funnel: {
        in_radius: 10, with_data: 9, above_score: 8, matching_area_type: 8,
        under_population_cap: 8, affordable: 5, distinct: 3, near_family: 3,
        per_anchor_quota: 2, promoted: 3,
      },
      relaxation: null,
      unrepresented_anchors: [],
      // Only the two quota-promoted rows are ever in `shortlist` -- a
      // non-promoted row belongs only in `all_passing`, the same contract
      // api.py's screen_payload() keeps (§5.5's `promoted` flag is what
      // distinguishes them). Getting this wrong here would let the
      // "seeds from the quota's promotions" test below pass for the wrong
      // reason: the un-promoted row leaking into the initial selection.
      shortlist: [row("80020", 92.0, "80014", true), row("60521", 71.0, "60521", true)],
      all_passing: [row("80020", 92.0, "80014", true), row("60521", 71.0, "60521", true),
                    row("80021", 85.0, "80014", false)],
    },
  };
}

describe("quota rendering", () => {
  test("a reserved-pass row carries the covers-{anchor} badge", async () => {
    const { sandbox } = mount({}, { "zip-screen": screenPayload() });
    await sandbox.findHousingOptCandidates();
    const html = sandbox.renderHousingZipShortlistHtml(
      { zip_screen: screenPayload().zip_screen }, { moveIndex: 1 });
    assert.match(html, /covers 60521/);
  });

  test("the per-anchor coverage line reports both anchors", async () => {
    const { sandbox } = mount({}, { "zip-screen": screenPayload() });
    await sandbox.findHousingOptCandidates();
    const html = sandbox.renderHousingZipShortlistHtml(
      { zip_screen: screenPayload().zip_screen }, { moveIndex: 1 });
    assert.match(html, /Aurora, CO/);
    assert.match(html, /Hinsdale, IL/);
  });

  test("the funnel readout names the quota's reservation count, not as a survivor drop", async () => {
    const { sandbox } = mount({}, { "zip-screen": screenPayload() });
    const html = sandbox.renderHousingZipShortlistHtml(
      { zip_screen: screenPayload().zip_screen }, { moveIndex: 1 });
    assert.match(html, /2 reserved to cover your anchors/);
  });

  test("the price column names the reference year, not just today's price", async () => {
    const { sandbox } = mount({}, { "zip-screen": screenPayload() });
    const html = sandbox.renderHousingZipShortlistHtml(
      { zip_screen: screenPayload().zip_screen }, { moveIndex: 1 });
    assert.match(html, /as of 2038/);
    assert.match(html, /\$420,000/);
    assert.match(html, /\$400,000 today/);
  });
});

describe("selection round-trip", () => {
  test("Find candidate locations seeds the selection from the quota's promotions", async () => {
    const { sandbox } = mount({}, { "zip-screen": screenPayload() });
    await sandbox.findHousingOptCandidates();
    const search = sandbox.housingOptMoveSearchBody(1);
    assert.deepEqual(Array.from(search.selected_zips).sort(), ["60521", "80020"]);
  });

  test("ticking an unpromoted row adds it to the selection", async () => {
    const { sandbox } = mount({}, { "zip-screen": screenPayload() });
    await sandbox.findHousingOptCandidates();
    sandbox.toggleHousingOptZipSelection(1, "80021");
    const search = sandbox.housingOptMoveSearchBody(1);
    assert.ok(Array.from(search.selected_zips).includes("80021"));
  });

  test("unticking a promoted row removes it from the selection", async () => {
    const { sandbox } = mount({}, { "zip-screen": screenPayload() });
    await sandbox.findHousingOptCandidates();
    sandbox.toggleHousingOptZipSelection(1, "80020");
    const search = sandbox.housingOptMoveSearchBody(1);
    assert.ok(!Array.from(search.selected_zips).includes("80020"));
  });

  test("a second, unchanged Find is a no-op -- the client-side screen memo", async () => {
    const { sandbox, calls } = mount({}, { "zip-screen": screenPayload() });
    await sandbox.findHousingOptCandidates();
    const callsAfterFirst = calls.length;
    await sandbox.findHousingOptCandidates();
    assert.equal(calls.length, callsAfterFirst, "an identical re-screen must not re-request");
  });

  test("a changed filter re-screens rather than reusing the memo", async () => {
    let requested = 0;
    const { sandbox, elements } = mount(
      {},
      { "zip-screen": (body) => { requested++; return screenPayload(); } },
    );
    await sandbox.findHousingOptCandidates();
    assert.equal(requested, 1);
    elements.housingOptMove1MinScore.value = "40";
    await sandbox.findHousingOptCandidates();
    assert.equal(requested, 2, "a changed min score must invalidate the memo");
  });

  test("re-screening replaces the previous selection outright, not merges it", async () => {
    const { sandbox, elements } = mount({}, { "zip-screen": screenPayload() });
    await sandbox.findHousingOptCandidates();
    sandbox.toggleHousingOptZipSelection(1, "80021"); // hand-pick a non-promoted row
    let search = sandbox.housingOptMoveSearchBody(1);
    assert.ok(Array.from(search.selected_zips).includes("80021"));
    // A changed filter invalidates the memo and triggers a genuine re-screen
    // (the "no-op when unchanged" case is covered separately above).
    elements.housingOptMove1MinScore.value = "10";
    await sandbox.findHousingOptCandidates();
    search = sandbox.housingOptMoveSearchBody(1);
    assert.deepEqual(
      Array.from(search.selected_zips).sort(), ["60521", "80020"],
      "the hand-picked 80021 must not survive a fresh screen under different filters",
    );
  });
});

describe("step gating", () => {
  test("Continue is blocked before any screen has run", () => {
    const { sandbox } = mount();
    assert.equal(sandbox.housingOptStep1SelectionComplete(), false);
  });

  test("Continue re-enables once every enabled move has a selection", async () => {
    const { sandbox } = mount({}, { "zip-screen": screenPayload() });
    await sandbox.findHousingOptCandidates();
    assert.equal(sandbox.housingOptStep1SelectionComplete(), true);
  });

  test("enabling move 2 re-blocks Continue until move 2 also has a selection", async () => {
    const { sandbox, elements } = mount({}, { "zip-screen": screenPayload() });
    await sandbox.findHousingOptCandidates();
    assert.equal(sandbox.housingOptStep1SelectionComplete(), true);
    elements.housingOptMove2Enabled.checked = true;
    assert.equal(
      sandbox.housingOptStep1SelectionComplete(), false,
      "move 2 has no selection of its own yet",
    );
  });

  test("goToHousingOptStep(2) refuses to advance while the selection is incomplete", () => {
    const { sandbox, elements } = mount();
    const advanced = sandbox.goToHousingOptStep(2);
    assert.equal(advanced, false);
    assert.equal(elements.housingOptStep1.hidden, false, "step 1 must still be showing");
  });

  test("goToHousingOptStep(2) advances once the selection is complete", async () => {
    const { sandbox, elements } = mount({}, { "zip-screen": screenPayload() });
    await sandbox.findHousingOptCandidates();
    const advanced = sandbox.goToHousingOptStep(2);
    assert.equal(advanced, true);
    assert.equal(elements.housingOptStep1.hidden, true);
    assert.equal(elements.housingOptStep2.hidden, false);
  });

  test("the step-2 selected-locations summary reflects the ticked ZIPs", async () => {
    const { sandbox } = mount({}, { "zip-screen": screenPayload() });
    await sandbox.findHousingOptCandidates();
    sandbox.goToHousingOptStep(2);
    const html = sandbox.housingOptSelectedLocationsSummaryHtml();
    assert.match(html, /80020/);
    assert.match(html, /60521/);
  });

  test("disabling move 2 clears its selection so a stale one cannot resurface", async () => {
    const { sandbox, elements } = mount({}, { "zip-screen": screenPayload() });
    elements.housingOptMove2Enabled.checked = true;
    await sandbox.findHousingOptCandidates(); // screens both enabled moves
    let search = sandbox.housingOptMoveSearchBody(2);
    assert.ok(search.selected_zips.length > 0);
    elements.housingOptMove2Enabled.checked = false;
    sandbox.toggleHousingOptMove2Fields();
    search = sandbox.housingOptMoveSearchBody(2);
    assert.equal(search.selected_zips.length, 0);
  });
});

describe("coverage warning never blocks", () => {
  test("unticking an anchor's last ZIP warns but leaves Continue enabled", async () => {
    const { sandbox } = mount({}, { "zip-screen": screenPayload() });
    await sandbox.findHousingOptCandidates();
    // 60521 is the only row anchored on Hinsdale -- untick it.
    sandbox.toggleHousingOptZipSelection(1, "60521");
    assert.equal(
      sandbox.housingOptStep1SelectionComplete(), true,
      "move 1 still has a selection (80020); coverage is a separate, non-blocking concern",
    );
    const html = sandbox.renderHousingZipShortlistHtml(
      { zip_screen: screenPayload().zip_screen }, { moveIndex: 1 });
    assert.match(html, /no longer covers 60521/);
  });

  test("an unrepresented anchor from the screen itself is reported, not raised", async () => {
    const payload = screenPayload();
    payload.zip_screen.unrepresented_anchors = ["99999"];
    const { sandbox } = mount({}, { "zip-screen": payload });
    await sandbox.findHousingOptCandidates();
    assert.equal(sandbox.housingOptStep1SelectionComplete(), true);
    const html = sandbox.renderHousingZipShortlistHtml(
      { zip_screen: payload.zip_screen }, { moveIndex: 1 });
    assert.match(html, /No ZIP near 99999 survived the screen/);
  });
});

describe("stale-selection rejection", () => {
  // runHousingOptimization() calls refreshHousingOptValidation() first and
  // returns before ever reaching api() if the selection is empty (§5.3's
  // real gate), so these tests seed a selection directly -- the server
  // rejection under test is a DIFFERENT failure than an empty one: a ZIP
  // that WAS selected but no longer screens.
  function mountWithSelection(apiResponses) {
    const mounted = mount({}, apiResponses);
    mounted.sandbox.toggleHousingOptZipSelection(1, "80014");
    return mounted;
  }

  test("a server-side {success:false} for a stale ZIP renders as an error, not a crash", async () => {
    const { sandbox, elements } = mountWithSelection({
      "housing/optimize": {
        success: false,
        error: "ZIP 99999 is not among the screened candidates for move 1. " +
          'The screen filters have changed since it was selected -- press "Find candidate locations" again and re-pick.',
      },
    });
    await sandbox.runHousingOptimization();
    assert.match(elements.housingOptimizeResults.innerHTML, /not among the screened candidates/);
    assert.match(elements.housingOptimizeResults.innerHTML, /99999/);
  });

  test("a stale rejection does not throw and leaves the panel usable afterward", async () => {
    const { sandbox } = mountWithSelection({
      "housing/optimize": { success: false, error: "ZIP 99999 is not among the screened candidates for move 1." },
    });
    await assert.doesNotThrow(async () => sandbox.runHousingOptimization());
  });

  test("a successful run after a prior stale rejection renders results normally", async () => {
    let first = true;
    const { sandbox, elements } = mountWithSelection({
      "housing/optimize": () => {
        if (first) {
          first = false;
          return { success: false, error: "ZIP 99999 is not among the screened candidates for move 1." };
        }
        return { success: true, schema: "housing_optimize_v2", recommendation: null, candidates: [] };
      },
    });
    await sandbox.runHousingOptimization();
    assert.match(elements.housingOptimizeResults.innerHTML, /not among the screened candidates/);
    await sandbox.runHousingOptimization();
    assert.ok(!elements.housingOptimizeResults.innerHTML.includes("not among the screened candidates"));
  });
});
