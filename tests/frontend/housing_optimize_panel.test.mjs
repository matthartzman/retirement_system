// Housing move optimizer panel markup
// (docs/superpowers/specs/2026-09-16-housing-optimizer-refinement-design.md
// §9.1-§9.3). The panel now lives in its own module,
// frontend/js/dashboard_decomp_housing_optimizer.js.
//
// The design plan's own version of this file imports
// renderHousingOptimizePanelHtml directly from that module. That is not how
// this repo's frontend modules can be exercised: none of them are standalone
// ES modules -- they resolve `esc`, `api`, `showMessage`,
// `ensureHelpPanelVisible` and friends as bare globals supplied by
// dashboard.js and its siblings, in the load order index.html declares. The
// assertions below are the plan's; only the way the HTML is obtained differs,
// via loadDashboardSandbox() like every other frontend test here.

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();
const panelHtml = () => sandbox.renderHousingOptimizePanelHtml();

describe("renderHousingOptimizePanelHtml", () => {
  test("the manual-location mode is gone", () => {
    const html = panelHtml();
    assert.ok(!html.includes("Choose locations manually"));
    assert.ok(!html.includes("housingOptGeoMode"));
    assert.ok(!html.includes("housingOptLocCount"));
  });

  test("global constraints and objective come before the move sections", () => {
    const html = panelHtml();
    assert.ok(html.indexOf("housingOptObjective") < html.indexOf("housingOptMove1Earliest"));
    assert.ok(html.indexOf("housingOptPresenceZip") < html.indexOf("housingOptMove1Earliest"));
  });

  test("the current home is its own section with a disposition control", () => {
    const html = panelHtml();
    assert.ok(html.includes("housingOptDisposition"));
    assert.ok(html.includes("housingOptEarliestSale"));
    assert.ok(html.includes("housingOptLatestSale"));
  });

  test("each move has an acquisition window, not a purchase window", () => {
    const html = panelHtml();
    assert.ok(html.includes("housingOptMove1Earliest"));
    assert.ok(html.includes("housingOptMove2Earliest"));
    assert.ok(!html.includes("housingOptEarliestPurchase"));
  });

  test("family presence is a ZIP plus a proximity radius", () => {
    const html = panelHtml();
    assert.ok(html.includes("housingOptPresenceZip"));
    assert.ok(html.includes("housingOptPresenceRadius"));
    for (const r of ["10", "25", "50", "100"]) {
      assert.ok(html.includes(`value="${r}"`), `radius ${r} missing`);
    }
    assert.ok(!html.includes("housingOptPresenceRegion"));
  });

  test("both moves expose the new candidate and dwelling constraints", () => {
    const html = panelHtml();
    for (const n of [1, 2]) {
      for (const f of ["AreaType", "MaxPopulation", "LotSize", "Bedrooms", "Bathrooms"]) {
        assert.ok(html.includes(`housingOptMove${n}${f}`), `move ${n} ${f} missing`);
      }
    }
  });

  test("labels are stacked above their control, never inline before it", () => {
    const html = panelHtml();
    assert.ok(html.includes("housing-opt-field"));
    assert.ok(
      !/<label>[^<]*<input/.test(html),
      "found an inline label immediately followed by its input",
    );
  });

  test("every field carries a help affordance instead of inline helper text", () => {
    const html = panelHtml();
    const fields = (html.match(/class="housing-opt-field"/g) || []).length;
    const helps = (html.match(/showHousingOptFieldHelp\(/g) || []).length;
    assert.ok(fields > 0);
    assert.ok(helps >= fields, `${helps} help hooks for ${fields} fields`);
  });

  test("sizing is CSS classes, never an inline style width", () => {
    assert.ok(!panelHtml().includes('style="width:'));
  });

  test("the run button, validation area and results area are present", () => {
    const html = panelHtml();
    assert.match(html, /id="housingOptRun"/);
    assert.match(html, /id="housingOptValidation"/);
    assert.match(html, /id="housingOptimizeResults"/);
  });

  test("a Purchase assumptions section sits between Current home and Move 1", () => {
    const html = panelHtml();
    assert.match(html, /id="housingOptDownPaymentPct"/);
    assert.match(html, /id="housingOptMortgageRatePct"/);
    const currentHomeIdx = html.indexOf("housingOptDisposition");
    const purchaseAssumptionsIdx = html.indexOf("housingOptDownPaymentPct");
    const move1Idx = html.indexOf("housingOptMove1Earliest");
    assert.ok(currentHomeIdx < purchaseAssumptionsIdx, "assumptions come after Current home");
    assert.ok(purchaseAssumptionsIdx < move1Idx, "assumptions come before Move 1");
  });

  test("down payment and mortgage rate show real editable defaults, not placeholders", () => {
    const html = panelHtml();
    assert.match(html, /id="housingOptDownPaymentPct"[^>]*value="20"/);
    assert.match(html, /id="housingOptMortgageRatePct"[^>]*value="6\.85"/);
  });
});

describe("anchors control (§9.3)", () => {
  test("one compact anchor entry per move is shown by default, with a City/ZIP mode toggle", () => {
    const html = panelHtml();
    for (const n of [1, 2]) {
      assert.match(html, new RegExp(`id="housingOptMove${n}Anchor0"`));
      assert.ok(
        !html.includes(`id="housingOptMove${n}Anchor1"`),
        `move ${n} shows more than one anchor by default`,
      );
      assert.match(html, new RegExp(`id="housingOptMove${n}AnchorCity0"`));
      assert.match(html, new RegExp(`id="housingOptMove${n}AnchorZip0"`));
    }
    assert.match(html, /\+ Add anchor/);
  });

  test("addHousingOptAnchor grows the list to five and stops, with a remove control past the second", () => {
    const local = loadDashboardSandbox();
    let rendered = "";
    local.document.getElementById = (id) =>
      id === "housingOptMove1Anchors"
        ? {
            set innerHTML(v) {
              rendered = v;
            },
            get innerHTML() {
              return rendered;
            },
          }
        : null;
    for (let i = 0; i < 10; i++) local.addHousingOptAnchor(1);
    assert.match(rendered, /id="housingOptMove1Anchor4"/);
    assert.ok(!rendered.includes('id="housingOptMove1Anchor5"'));
    assert.ok(!/removeHousingOptAnchor\(1, 0\)/.test(rendered));
    assert.match(rendered, /removeHousingOptAnchor\(1, 1\)/);
    local.removeHousingOptAnchor(1, 4);
    assert.ok(!rendered.includes('id="housingOptMove1Anchor4"'));
  });
});

describe("Move N -- where row field order", () => {
  test("Area type renders immediately after the anchors block", () => {
    const html = panelHtml();
    const anchorsIdx = html.indexOf('id="housingOptMove1Anchors"');
    const areaTypeIdx = html.indexOf('id="housingOptMove1AreaType"');
    const radiusIdx = html.indexOf('id="housingOptMove1Radius"');
    assert.ok(anchorsIdx < areaTypeIdx, "area type comes after anchors");
    assert.ok(areaTypeIdx < radiusIdx, "area type comes before radius");
  });
});

describe("toggleHousingOptMove2Fields", () => {
  test("reveals the move-2 fields only when the checkbox is checked", () => {
    const local = loadDashboardSandbox();
    const elements = {
      housingOptMove2Enabled: { checked: true },
      housingOptMove2Fields: { hidden: true },
    };
    local.document.getElementById = (id) => elements[id] || null;
    local.toggleHousingOptMove2Fields();
    assert.equal(elements.housingOptMove2Fields.hidden, false);
    elements.housingOptMove2Enabled.checked = false;
    local.toggleHousingOptMove2Fields();
    assert.equal(elements.housingOptMove2Fields.hidden, true);
  });
});

describe("toggleHousingOptNoDualOwnershipAvailability", () => {
  test("disables no-dual-ownership and shows the note when concurrent is checked", () => {
    const local = loadDashboardSandbox();
    const elements = {
      housingOptMove2Concurrent: { checked: true },
      housingOptNoDualOwnership: { disabled: false, checked: true },
      housingOptNoDualOwnershipConcurrentNote: { hidden: true },
    };
    local.document.getElementById = (id) => elements[id] || null;
    local.toggleHousingOptNoDualOwnershipAvailability();
    assert.equal(elements.housingOptNoDualOwnership.disabled, true);
    assert.equal(elements.housingOptNoDualOwnership.checked, true);
    assert.equal(elements.housingOptNoDualOwnershipConcurrentNote.hidden, false);

    elements.housingOptMove2Concurrent.checked = false;
    local.toggleHousingOptNoDualOwnershipAvailability();
    assert.equal(elements.housingOptNoDualOwnership.disabled, false);
    assert.equal(elements.housingOptNoDualOwnershipConcurrentNote.hidden, true);
  });
});

describe("toggleHousingOptDispositionFields", () => {
  test("disables the sale window and shows the kept-home note under Keep", () => {
    const local = loadDashboardSandbox();
    const elements = {
      housingOptDisposition: { value: "keep" },
      housingOptEarliestSale: { disabled: false },
      housingOptLatestSale: { disabled: false },
      housingOptKeepNote: { hidden: true },
    };
    local.document.getElementById = (id) => elements[id] || null;
    local.toggleHousingOptDispositionFields();
    assert.equal(elements.housingOptEarliestSale.disabled, true);
    assert.equal(elements.housingOptLatestSale.disabled, true);
    assert.equal(elements.housingOptKeepNote.hidden, false);

    elements.housingOptDisposition.value = "auto";
    local.toggleHousingOptDispositionFields();
    assert.equal(elements.housingOptEarliestSale.disabled, false);
    assert.equal(elements.housingOptKeepNote.hidden, true);
  });
});

describe("housingOptMoveCellHtml", () => {
  function moveFixture(overrides = {}) {
    return {
      acquisition_year: 2033,
      action: "buy",
      location: { zip_code: "80014", city: "Aurora", state: "Colorado", distance_miles: 3.2 },
      financing: { purchase_price: 450000, monthly_pi_payment: 1918.56 },
      ...overrides,
    };
  }

  test("a rent move shows monthly rent and no price", () => {
    const html = sandbox.housingOptMoveCellHtml(moveFixture({
      action: "rent",
      financing: { monthly_rent: 1850 },
    }));
    assert.match(html, /\$1,850\/mo rent/);
    assert.ok(!/purchase/i.test(html));
    assert.ok(!/P&I/i.test(html));
  });

  test("a buy move shows purchase price and monthly P&I", () => {
    const html = sandbox.housingOptMoveCellHtml(moveFixture());
    assert.match(html, /\$450,000 purchase/);
    assert.match(html, /\$1,919\/mo P&amp;I/);
    assert.ok(!/rent/i.test(html));
  });
});

// 2026-09-17: relocated from Strategy -> Scenarios -> Scenario Change Sets to
// its own Strategy -> Optimize tab, alongside the plan's other major
// planning-lever decisions (Roth Conversion, Asset Allocation).
describe("panel location (2026-09-17 relocation)", () => {
  test("the panel renders inside Strategy -> Optimize's housing section", () => {
    const html = sandbox.renderStrategyOptimize();
    assert.match(html, /data-dkey="strategy:housing"/);
  });

  test("Scenario Change Sets no longer embeds the panel", () => {
    const html = sandbox.renderScenarioManagementPanel([]);
    assert.ok(
      !html.includes(`id="${sandbox.HOUSING_OPT_PANEL_ID}"`),
      "renderScenarioManagementPanel still embeds the housing optimizer panel",
    );
  });
});
