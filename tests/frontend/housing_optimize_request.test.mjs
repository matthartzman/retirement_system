// Request building (§7.1) and inline validation (§8) for the housing
// optimizer panel (Task 12).
//
// The design plan's own version of this test imports buildHousingOptRequest
// directly from dashboard_decomp_housing_optimizer.js and mounts the panel
// via an invented `./helpers/mount_housing_opt.mjs`. Neither exists for real:
// this repo's frontend modules are not standalone ES modules (see
// housing_optimize_panel.test.mjs's header comment for the full explanation),
// and there is no shared mount helper -- each test file that needs specific
// DOM values stubs document.getElementById itself, the same pattern
// dashboard_decomp_housing_optimizer.js's own panel test already uses for
// toggleHousingOptMove2Fields et al. This file follows that pattern: it loads
// the real production source via loadDashboardSandbox() and drives the
// exported functions off a plain id->element map. The assertions are the
// plan's; only how the panel state is supplied differs.

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

// A fully valid, minimal form: every rule in validateHousingOptForm() passes
// against these defaults, so a test can override just the one or two fields
// it cares about.
function defaultElements() {
  return {
    housingOptObjective: { value: "net_worth" },
    housingOptSearchMode: { value: "full" },
    housingOptMove2Strategy: { value: "anchored" },
    housingOptNoDualOwnership: { checked: true },
    housingOptDownPaymentPct: { value: "20" },
    housingOptMortgageRatePct: { value: "6.85" },

    housingOptPresenceEnabled: { checked: false },
    housingOptPresenceZip: { value: "" },
    housingOptPresenceRadius: { value: "25" },
    housingOptPresenceFrom: { value: "" },
    housingOptPresenceThrough: { value: "" },

    housingOptDisposition: { value: "auto" },
    housingOptEarliestSale: { value: "2030" },
    housingOptLatestSale: { value: "2045" },

    housingOptMove1Earliest: { value: "2031" },
    housingOptMove1Latest: { value: "2046" },
    housingOptMove1Action: { value: "auto" },
    housingOptMove1Radius: { value: "25" },
    housingOptMove1MinScore: { value: "60" },
    housingOptMove1AreaType: { value: "any" },
    housingOptMove1MaxPopulation: { value: "" },
    housingOptMove1ShortlistSize: { value: "4" },
    housingOptMove1Bedrooms: { value: "3" },
    housingOptMove1Bathrooms: { value: "2" },
    housingOptMove1PropertyType: { value: "single_family" },
    housingOptMove1SqftBand: { value: "1800_2500" },
    housingOptMove1LotSize: { value: "quarter_half" },
    housingOptMove1BuiltWithin: { value: "" },
    housingOptMove1PriceMin: { value: "" },
    housingOptMove1PriceMax: { value: "" },
    housingOptMove1Anchor0: { value: "city" },
    housingOptMove1AnchorCity0: { value: "80014" },
    housingOptMove1AnchorZip0: { value: "" },
    housingOptMove1Anchor1: { value: "city" },
    housingOptMove1AnchorCity1: { value: "60521" },
    housingOptMove1AnchorZip1: { value: "" },

    housingOptMove2Enabled: { checked: false },
    housingOptMove2Earliest: { value: "2040" },
    housingOptMove2Latest: { value: "2050" },
    housingOptMove2Action: { value: "auto" },
    housingOptMove2Concurrent: { checked: false },
    housingOptMove2AnchorCount: { value: "5" },
    housingOptMove2Radius: { value: "25" },
    housingOptMove2MinScore: { value: "60" },
    housingOptMove2AreaType: { value: "any" },
    housingOptMove2MaxPopulation: { value: "" },
    housingOptMove2ShortlistSize: { value: "4" },
    housingOptMove2Bedrooms: { value: "3" },
    housingOptMove2Bathrooms: { value: "2" },
    housingOptMove2PropertyType: { value: "single_family" },
    housingOptMove2SqftBand: { value: "1800_2500" },
    housingOptMove2LotSize: { value: "quarter_half" },
    housingOptMove2BuiltWithin: { value: "" },
    housingOptMove2PriceMin: { value: "" },
    housingOptMove2PriceMax: { value: "" },
    housingOptMove2Anchor0: { value: "city" },
    housingOptMove2AnchorCity0: { value: "80014" },
    housingOptMove2AnchorZip0: { value: "" },
    housingOptMove2Anchor1: { value: "city" },
    housingOptMove2AnchorCity1: { value: "60521" },
    housingOptMove2AnchorZip1: { value: "" },

    housingOptRun: { disabled: false },
    housingOptValidation: { hidden: true, textContent: "" },
    housingOptimizeResults: { innerHTML: "" },
  };
}

// Loads a fresh sandbox and stubs document.getElementById off `elements`
// (default form plus the given overrides, one level deep per id).
function mountHousingOptPanel(overrides = {}) {
  const elements = defaultElements();
  for (const [id, patch] of Object.entries(overrides)) {
    elements[id] = { ...(elements[id] || {}), ...patch };
  }
  const sandbox = loadDashboardSandbox();
  sandbox.document.getElementById = (id) => elements[id] || { value: "", checked: false };
  return { sandbox, elements };
}

describe("buildHousingOptRequest", () => {
  test("the request carries no locations key", () => {
    const { sandbox } = mountHousingOptPanel();
    assert.ok(!("locations" in sandbox.buildHousingOptRequest()));
  });

  test("anchors are collected per move", () => {
    const { sandbox } = mountHousingOptPanel({
      housingOptMove1Anchor0: { value: "zip" },
      housingOptMove1AnchorZip0: { value: "80014" },
      housingOptMove1Anchor1: { value: "zip" },
      housingOptMove1AnchorZip1: { value: "60521" },
    });
    // The anchor count now defaults to 1 (§ 1-5 anchors, was 2-5) -- this
    // test wants both anchor slots read, so grow move 1 to 2 first (the
    // stubbed getElementById tolerates addHousingOptAnchor's container
    // lookup the same way it tolerates every other id it doesn't know).
    sandbox.addHousingOptAnchor(1);
    const body = sandbox.buildHousingOptRequest();
    // Array.from() re-materializes the sandbox (vm-realm) array/objects as
    // host-realm values -- assert/strict's deepEqual otherwise fails a
    // cross-realm array on constructor identity even when every element is
    // equal.
    assert.deepEqual(
      Array.from(body.move1.search.anchors, (a) => a.anchor_zip),
      ["80014", "60521"],
    );
  });

  test("a kept home sends no sale window", () => {
    const { sandbox } = mountHousingOptPanel({ housingOptDisposition: { value: "keep" } });
    const body = sandbox.buildHousingOptRequest();
    assert.equal(body.original_home.disposition, "keep");
    assert.ok(!body.original_home.earliest_sale_year);
    assert.ok(!("earliest_sale_year" in body.original_home));
  });

  test("family presence sends a zip and a radius, never a region", () => {
    const { sandbox } = mountHousingOptPanel({
      housingOptPresenceEnabled: { checked: true },
      housingOptPresenceZip: { value: "60521" },
      housingOptPresenceRadius: { value: "25" },
      housingOptPresenceFrom: { value: "2026" },
      housingOptPresenceThrough: { value: "2050" },
    });
    const fp = sandbox.buildHousingOptRequest().family_presence;
    assert.equal(fp.zip, "60521");
    assert.equal(fp.radius_miles, 25);
    assert.ok(!("region" in fp));
  });

  test("move2 is present only when enabled, with its own window and search", () => {
    const { sandbox: withoutMove2 } = mountHousingOptPanel();
    assert.ok(!("move2" in withoutMove2.buildHousingOptRequest()));

    const { sandbox: withMove2 } = mountHousingOptPanel({
      housingOptMove2Enabled: { checked: true },
    });
    const body = withMove2.buildHousingOptRequest();
    assert.ok(body.move2);
    assert.equal(body.move2.earliest_acquisition_year, 2040);
    assert.equal(body.move2.latest_acquisition_year, 2050);
  });

  test("down payment % is sent as a fraction", () => {
    const { sandbox } = mountHousingOptPanel({ housingOptDownPaymentPct: { value: "15" } });
    assert.equal(sandbox.buildHousingOptRequest().down_payment_pct, 0.15);
  });

  test("an empty down payment field defaults to 20%", () => {
    const { sandbox } = mountHousingOptPanel({ housingOptDownPaymentPct: { value: "" } });
    assert.equal(sandbox.buildHousingOptRequest().down_payment_pct, 0.2);
  });

  test("mortgage rate % is sent as a fraction", () => {
    const { sandbox } = mountHousingOptPanel({ housingOptMortgageRatePct: { value: "5" } });
    assert.equal(sandbox.buildHousingOptRequest().mortgage_rate_pct, 0.05);
  });

  test("clearing the mortgage rate field sends null, not zero", () => {
    const { sandbox } = mountHousingOptPanel({ housingOptMortgageRatePct: { value: "" } });
    assert.equal(sandbox.buildHousingOptRequest().mortgage_rate_pct, null);
  });
});

describe("validateHousingOptForm", () => {
  test("a valid form validates clean", () => {
    const { sandbox } = mountHousingOptPanel();
    assert.equal(sandbox.validateHousingOptForm(), null);
  });

  test("the screenshot case is blocked before any request is built", () => {
    const { sandbox } = mountHousingOptPanel({
      housingOptMove1Earliest: { value: "2031" },
      housingOptMove1Latest: { value: "2046" },
      housingOptMove2Enabled: { checked: true },
      housingOptMove2Earliest: { value: "2029" },
      housingOptMove2Latest: { value: "2030" },
    });
    const msg = sandbox.validateHousingOptForm();
    assert.ok(msg && msg.includes("2031"));
    assert.equal(
      msg,
      "Move 2 must be able to happen after move 1. Raise the move-2 latest year above 2031.",
    );
  });

  test("an inverted sale window is rejected", () => {
    const { sandbox } = mountHousingOptPanel({
      housingOptEarliestSale: { value: "2045" },
      housingOptLatestSale: { value: "2030" },
    });
    assert.equal(
      sandbox.validateHousingOptForm(),
      "Earliest sale year must not be after the latest sale year.",
    );
  });

  test("keep + buy under no-dual-ownership is rejected", () => {
    const { sandbox } = mountHousingOptPanel({
      housingOptDisposition: { value: "keep" },
      housingOptMove1Action: { value: "buy" },
    });
    assert.equal(
      sandbox.validateHousingOptForm(),
      "Keeping the current home and buying another means owning two homes. Choose Rent, " +
        "sell the current home, or turn off 'Never own two homes at once'.",
    );
  });

  test("rules 4 and 5 do not fire under auto disposition", () => {
    const { sandbox } = mountHousingOptPanel({
      housingOptDisposition: { value: "auto" },
      housingOptMove1Action: { value: "buy" },
    });
    assert.equal(sandbox.validateHousingOptForm(), null);
  });

  test("zero anchors for move 1 is rejected", () => {
    const { sandbox } = mountHousingOptPanel({
      housingOptMove1AnchorCity0: { value: "" },
      housingOptMove1AnchorCity1: { value: "" },
    });
    assert.equal(sandbox.validateHousingOptForm(), "Choose between 1 and 5 anchors for move 1.");
  });

  test("a single anchor for move 1 is now allowed", () => {
    const { sandbox } = mountHousingOptPanel({
      housingOptMove1AnchorCity1: { value: "" },
    });
    assert.equal(sandbox.validateHousingOptForm(), null);
  });

  test("an inverted price range is rejected", () => {
    const { sandbox } = mountHousingOptPanel({
      housingOptMove1PriceMin: { value: "700000" },
      housingOptMove1PriceMax: { value: "400000" },
    });
    assert.equal(
      sandbox.validateHousingOptForm(),
      "Minimum target price must not exceed the maximum.",
    );
  });

  test("apartment forced to buy is rejected", () => {
    const { sandbox } = mountHousingOptPanel({
      housingOptMove1Action: { value: "buy" },
      housingOptMove1PropertyType: { value: "apartment" },
    });
    const msg = sandbox.validateHousingOptForm();
    assert.match(msg, /apartment/i);
    assert.match(msg, /move 1/i);
  });

  test("apartment is fine under rent or auto", () => {
    for (const action of ["rent", "auto"]) {
      const { sandbox } = mountHousingOptPanel({
        housingOptMove1Action: { value: action },
        housingOptMove1PropertyType: { value: "apartment" },
      });
      assert.equal(sandbox.validateHousingOptForm(), null, action);
    }
  });

  test("family presence needs a 5-digit zip and an ordered window", () => {
    const { sandbox } = mountHousingOptPanel({
      housingOptPresenceEnabled: { checked: true },
      housingOptPresenceZip: { value: "605" },
      housingOptPresenceFrom: { value: "2026" },
      housingOptPresenceThrough: { value: "2050" },
    });
    assert.equal(
      sandbox.validateHousingOptForm(),
      "Family presence needs a 5-digit ZIP and a from-year no later than the through-year.",
    );
  });
});

describe("validateHousingOptForm -- purchase assumptions bounds", () => {
  test("down payment over 100 is rejected", () => {
    const { sandbox } = mountHousingOptPanel({ housingOptDownPaymentPct: { value: "150" } });
    assert.match(sandbox.validateHousingOptForm(), /down payment/i);
  });

  test("a negative mortgage rate is rejected", () => {
    const { sandbox } = mountHousingOptPanel({ housingOptMortgageRatePct: { value: "-1" } });
    assert.match(sandbox.validateHousingOptForm(), /mortgage rate/i);
  });

  test("the pre-filled defaults are valid", () => {
    const { sandbox } = mountHousingOptPanel();
    assert.equal(sandbox.validateHousingOptForm(), null);
  });
});

describe("refreshHousingOptValidation", () => {
  test("the run button is disabled while the form is invalid", () => {
    const { sandbox, elements } = mountHousingOptPanel({
      housingOptMove1Earliest: { value: "2046" },
      housingOptMove1Latest: { value: "2031" },
    });
    sandbox.refreshHousingOptValidation();
    assert.equal(elements.housingOptRun.disabled, true);
    assert.equal(elements.housingOptValidation.hidden, false);
    assert.equal(
      elements.housingOptValidation.textContent,
      "Earliest move-1 year must not be after the latest.",
    );
  });

  test("the run button re-enables once the form is valid again", () => {
    const { sandbox, elements } = mountHousingOptPanel();
    sandbox.refreshHousingOptValidation();
    assert.equal(elements.housingOptRun.disabled, false);
    assert.equal(elements.housingOptValidation.hidden, true);
  });
});
