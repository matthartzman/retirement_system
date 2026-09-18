// Results rendering (design 2026-09-16 §9.4, Task 13).
//
// The design plan's own version of this test imports
// renderHousingOptimizeResultsHtml directly from
// dashboard_decomp_housing_optimizer.js. That file is not a standalone ES
// module (see housing_optimize_request.test.mjs's header for the full
// explanation) so it cannot be imported that way. This file follows Task
// 12's corrected pattern instead: load the real production source via
// loadDashboardSandbox() and call the exported function directly off the
// sandbox object. The assertions are the plan's; only how the function is
// obtained differs.

import { test } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

function render(payload) {
  const { renderHousingOptimizeResultsHtml } = loadDashboardSandbox();
  return renderHousingOptimizeResultsHtml(payload);
}

const MOVE1 = {
  index: 1,
  acquisition_year: 2033,
  action: "buy",
  mode: "sequential",
  location: {
    zip_code: "80024",
    city: "Derby",
    state: "CO",
    area_type: "suburban",
    population: 12480,
    nss: 89.1,
    band: "Very Favorable",
    distance_miles: 11.83,
    family_distance_miles: 18.4,
    est_price: 539400,
  },
  financing: {
    purchase_price: 539400,
    monthly_pi_payment: 2848.12,
  },
  sec121_exclusion_lost: false,
};

function payload(over = {}) {
  return {
    success: true,
    schema: "housing_optimize_v2",
    objective: "net_worth",
    candidates: [
      {
        rank: 1,
        original_home: { disposition: "sell", sale_year: 2032 },
        moves: [MOVE1],
        net_worth: 4210000,
        lifetime_cost: 1180000,
        mc_success_rate: 0.912,
        objective_value: 4210000,
        notes: [],
      },
    ],
    recommendation: null,
    candidates_evaluated: 12,
    rejections: {},
    ...over,
  };
}

test("a recommendation row carries year, action, ZIP, price and distance", () => {
  const html = render(payload());
  for (const part of ["2032", "2033", "Buy", "80024", "Derby", "CO", "$539,400", "11.8 mi"]) {
    assert.ok(html.includes(part), `missing ${part}`);
  }
});

test("a kept home reads as Keep rather than a blank sale year", () => {
  const p = payload();
  p.candidates[0].original_home = { disposition: "keep", sale_year: null };
  assert.ok(render(p).includes("Keep"));
});

test("a missing second move renders an em dash, not an empty cell", () => {
  assert.ok(render(payload()).includes("—"));
});

test("rank 1 is badged and labelled Recommended", () => {
  const html = render(payload());
  assert.ok(html.includes("housing-opt-rank"));
  assert.ok(html.includes("Recommended"));
});

test("the objective column reads as impact vs. the do-nothing baseline, not vs. rank 1", () => {
  const p = payload({ baseline_objective_value: 3800000 });
  p.candidates.push({ ...p.candidates[0], rank: 2, objective_value: 3900000 });
  const html = render(p);
  // Rank 1 ($4,210,000) vs. baseline ($3,800,000): +$410,000.
  assert.ok(html.includes("+$410,000"), html);
  // Rank 2 ($3,900,000) vs. the SAME baseline (not vs. rank 1): +$100,000.
  assert.ok(html.includes("+$100,000"), html);
});

test("a negative impact vs. baseline is colored as negative even for rank 1", () => {
  const p = payload({ baseline_objective_value: 5000000 });
  const html = render(p);
  assert.ok(html.includes("negative-money"));
  assert.ok(html.includes("-$790,000"));
});

test("no baseline in the payload falls back to the raw objective value", () => {
  const html = render(payload());
  assert.ok(html.includes("$4,210,000"));
});

test("adjacent results alternate shading so a wrapped row stays one block", () => {
  const p = payload();
  p.candidates.push({ ...p.candidates[0], rank: 2 });
  const html = render(p);
  assert.ok(html.includes("housing-opt-result-odd"));
  assert.ok(html.includes("housing-opt-result-even"));
});

test("an empty run reports the rejection tally instead of a generic sentence", () => {
  const html = render(
    payload({ candidates: [], rejections: { family_presence: 12, dual_ownership: 40 } }),
  );
  assert.ok(html.includes("12"));
  assert.ok(html.includes("40"));
  assert.ok(!html.includes("No candidates satisfied the search windows"));
});

test("a zero rejection count is omitted, not rendered as zero", () => {
  // Known gap (Task 9/10, 2026-09-16): rejections['move_order'] reads 0 in
  // narrowed mode even though the rule was never actually measured there.
  // Rendering "0 rejected for move order" would assert something the
  // optimizer did not check.
  const html = render(
    payload({
      candidates: [],
      rejections: { family_presence: 12, dual_ownership: 0, move_order: 0 },
    }),
  );
  assert.ok(html.includes("12"));
  assert.ok(!html.includes("0 rejected"));
  assert.ok(!/\bmove order\b/.test(html));
  assert.ok(!/\bdual ownership\b/.test(html));
});

test("family distance is never shown in a move cell (duplicates the search criteria, was the widest part of the row)", () => {
  assert.ok(!render(payload()).includes("18.4"));
  assert.ok(!render(payload()).includes("from family"));
});

test("a genuinely empty run with no rejections and no funnel data keeps the generic sentence", () => {
  const html = render(payload({ candidates: [], rejections: {} }));
  assert.ok(html.includes("No candidates satisfied the search windows"));
});

test("an empty run also surfaces the zip screen's emptying funnel stage", () => {
  const html = render(
    payload({
      candidates: [],
      rejections: {},
      zip_screens: {
        move1: {
          funnel: {
            in_radius: 40,
            with_data: 40,
            above_score: 40,
            matching_area_type: 40,
            under_population_cap: 0,
            affordable: 0,
            distinct: 0,
            near_family: 0,
            promoted: 0,
          },
          relaxation: {
            stage: "under_population_cap",
            field: "max_population",
            current: 20000,
            suggested: 65000,
            would_return: 9,
          },
        },
      },
    }),
  );
  assert.ok(html.includes("population"));
  assert.ok(!html.includes("No candidates satisfied the search windows"));
});
