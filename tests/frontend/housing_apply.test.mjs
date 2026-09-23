// W10c (#329 P6 / §4.3 "structural adoption"): Housing's optimizer patch.
//
// The second and harder patch shape, taken only after the scalar one
// (Social Security) was proven, per the master plan's own scoping note.
// Housing is the only optimizer whose answer does not map onto one obvious
// row: a candidate spans the sale year, then per move a step type, start
// year, state and price or rent, across two sections -- and the part of the
// answer that matters most to a reader, the actual town, has no field at all.
//
// So the claims worth testing are about what the patch writes and, just as
// much, what it refuses to write:
//
//   1. the optimizer's action vocabulary ("buy"/"rent") is translated to the
//      plan row's ("purchase"/"rent") -- the two are not the same words;
//   2. afterRaw is the STORED form, so a $400,000 row compared against a
//      bare 400000 does not read "not applied" for a plan that is applied;
//   3. the ZIP/city and the financing terms become advisory items, because
//      no row holds them -- silently dropping them would hide the part the
//      user most needs to act on;
//   4. the estimated utilities/maintenance/insurance rows are NOT in the
//      patch, because editValue()'s own housing hook re-scales them.

import { test, describe, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();
const {
  housingOptimizerPatch,
  housingOptRecommendedCandidate,
  housingOptimizerResult,
  housingOptResultReset,
} = sandbox;
const OA = sandbox.window.OptimizerApply;

// The Housing rows the frozen sample plan actually carries
// (tests/fixtures/sample_plan_frozen/client_spending.csv), plus the home
// sale year row from client_assets.csv.
function planRows() {
  const housing = (subsection, label, value, format) => ({
    row_index: 0,
    section: "Housing",
    subsection,
    label,
    value,
    format,
    editable: true,
  });
  const out = [
    {
      row_index: 10,
      section: "Other Assets",
      subsection: "Home",
      label: "home_sale_year",
      value: "0",
      format: "int",
      editable: true,
    },
    housing("next_step_1", "type", "purchase", "choice"),
    housing("next_step_1", "start_year", "2036", "int"),
    housing("next_step_1", "state", "TX", "text"),
    housing("next_step_1", "purchase_price", "$400,000", "money"),
    housing("next_step_1", "monthly_rent", "", "money"),
    housing("next_step_1", "insurance_annual", "$2,200", "money"),
    housing("next_step_1", "utilities_annual", "$2,400", "money"),
    housing("next_step_1", "maintenance_annual", "$2,500", "money"),
    housing("next_step_1", "down_payment", "27%", "pct"),
    housing("next_step_1", "mortgage_rate_pct", "6.00%", "pct"),
    housing("next_step_2", "type", "", "choice"),
    housing("next_step_2", "start_year", "", "int"),
    housing("next_step_2", "state", "", "text"),
    housing("next_step_2", "monthly_rent", "", "money"),
    housing("next_step_2", "purchase_price", "", "money"),
  ];
  out.forEach((r, i) => {
    if (!r.row_index) r.row_index = 100 + i;
  });
  return out;
}

// One /api/housing/optimize response candidate, in src/housing/results.py's
// real shape -- note `action: "buy"`, which is NOT the plan row's word.
function payload(over) {
  return Object.assign(
    {
      success: true,
      objective: "net_worth",
      candidates: [
        {
          rank: 1,
          original_home: { disposition: "sell", sale_year: 2034 },
          moves: [
            {
              index: 1,
              acquisition_year: 2034,
              action: "buy",
              location: {
                zip_code: "80024",
                city: "Derby",
                state: "CO",
                distance_miles: 11.8,
              },
              financing: {
                purchase_price: 539400,
                monthly_pi_payment: 2848.12,
              },
            },
          ],
          notes: [],
        },
        {
          rank: 2,
          original_home: { disposition: "keep", sale_year: null },
          moves: [],
          notes: [],
        },
      ],
    },
    over || {},
  );
}

beforeEach(() => {
  sandbox.window.rows = planRows();
  sandbox.window.dirty = new Map();
  housingOptResultReset();
});

describe("which candidate a bare apply means", () => {
  test("the starred rank-1 candidate", () => {
    assert.equal(housingOptRecommendedCandidate(payload()).rank, 1);
  });

  test("a payload with no candidates has nothing to recommend", () => {
    assert.equal(housingOptRecommendedCandidate({ candidates: [] }), null);
    assert.equal(housingOptRecommendedCandidate(null), null);
  });

  test("no retained result means an empty patch, not a throw", () => {
    assert.equal(housingOptimizerResult(), null);
    assert.deepEqual(Array.from(housingOptimizerPatch(null) || []), []);
  });
});

describe("the structural patch", () => {
  const byField = (patch, field) => patch.find((x) => x.field === field);

  test('"buy" becomes the plan row\'s "purchase"', () => {
    // The optimizer's vocabulary and the row's are different words for the
    // same thing; writing "buy" into a purchase|rent choice row would be
    // rejected or silently wrong.
    const item = byField(housingOptimizerPatch(payload()), "type");
    assert.equal(item.afterRaw, "purchase");
  });

  test('"rent" stays "rent"', () => {
    const p = payload();
    p.candidates[0].moves[0].action = "rent";
    p.candidates[0].moves[0].financing = { monthly_rent: 2400 };
    const item = byField(housingOptimizerPatch(p), "type");
    assert.equal(item.afterRaw, "rent");
  });

  test("the sale year of the current home is written", () => {
    const item = byField(housingOptimizerPatch(payload()), "home_sale_year");
    assert.equal(item.afterRaw, "2034");
    assert.equal(item.section, "Other Assets");
  });

  test('"keep" is written as year 0, which is how the row spells no sale', () => {
    const p = payload();
    p.candidates[0].original_home = { disposition: "keep", sale_year: null };
    const item = byField(housingOptimizerPatch(p), "home_sale_year");
    assert.equal(item.afterRaw, "0");
  });

  test("the move's start year and state land on next_step_1", () => {
    const patch = housingOptimizerPatch(payload());
    assert.equal(byField(patch, "start_year").afterRaw, "2034");
    assert.equal(byField(patch, "start_year").subsection, "next_step_1");
    assert.equal(byField(patch, "state").afterRaw, "CO");
  });

  test("a second move lands on next_step_2, not on top of the first", () => {
    const p = payload();
    p.candidates[0].moves.push({
      index: 2,
      acquisition_year: 2041,
      action: "rent",
      location: { zip_code: "85001", city: "Phoenix", state: "AZ" },
      financing: { monthly_rent: 2600 },
    });
    const patch = housingOptimizerPatch(p);
    const steps = patch
      .filter((x) => x.section === "Housing" && x.row_index != null)
      .map((x) => x.subsection);
    assert.ok(steps.includes("next_step_1"));
    assert.ok(steps.includes("next_step_2"));
    const rent = patch.find(
      (x) => x.field === "monthly_rent" && x.subsection === "next_step_2",
    );
    assert.equal(rent.afterRaw, "2600");
  });

  test("a purchase writes the price and not the rent", () => {
    const patch = housingOptimizerPatch(payload());
    assert.ok(byField(patch, "purchase_price"));
    assert.ok(!patch.some((x) => x.field === "monthly_rent"));
  });

  test("a rental writes the rent and not the price", () => {
    const p = payload();
    p.candidates[0].moves[0].action = "rent";
    p.candidates[0].moves[0].financing = { monthly_rent: 2400 };
    const patch = housingOptimizerPatch(p);
    assert.ok(byField(patch, "monthly_rent"));
    assert.ok(!patch.some((x) => x.field === "purchase_price"));
  });

  test("afterRaw is the STORED form, so the comparison can match", () => {
    // storageValueForInput turns 539400 into the currency row's own stored
    // spelling; comparing a bare 539400 against "$539,400" would read as
    // not-applied for a plan that is applied.
    const item = byField(housingOptimizerPatch(payload()), "purchase_price");
    const live = (idx) =>
      item.row_index === idx ? item.afterRaw : undefined;
    assert.equal(
      OA.optimizerAppliedState([item], live),
      OA.APPLIED,
      `afterRaw ${JSON.stringify(item.afterRaw)} did not compare equal to itself`,
    );
    assert.match(item.after, /539,400/);
  });

  test("before reports what the row holds today, in display form", () => {
    const item = byField(housingOptimizerPatch(payload()), "purchase_price");
    assert.equal(item.beforeRaw, "$400,000");
    assert.match(item.before, /400,000/);
  });

  test("every written item routes back to the Home & Housing page", () => {
    for (const x of housingOptimizerPatch(payload()))
      assert.equal(x.sourceStep, "assets_home_cash");
  });
});

describe("what the patch deliberately does not write", () => {
  test("the estimated cost rows are left to editValue's own housing hook", () => {
    // reestimateHousingCostsOnValueChange already re-scales these when the
    // price changes; writing them here too would double-apply the ratio.
    const fields = housingOptimizerPatch(payload()).map((x) => x.field);
    for (const f of [
      "insurance_annual",
      "utilities_annual",
      "maintenance_annual",
    ])
      assert.ok(!fields.includes(f), `${f} must not be in the patch`);
  });

  test("the down payment and mortgage rate rows are not written", () => {
    // src/housing/results.py never reports them back, so there is no value
    // to write -- and writing a guess into a row that drives P&I is worse
    // than leaving it and saying so.
    const fields = housingOptimizerPatch(payload())
      .filter((x) => x.row_index != null)
      .map((x) => x.field);
    assert.ok(!fields.includes("down_payment"));
    assert.ok(!fields.includes("mortgage_rate_pct"));
  });

  test("the financing gap is surfaced as advisory, not dropped", () => {
    const advisory = OA.advisoryItems(housingOptimizerPatch(payload()));
    const fin = advisory.find((x) => /financing/i.test(x.label));
    assert.ok(fin, "the P&I assumption must be stated somewhere");
    assert.match(fin.after, /2,848/);
    assert.match(fin.rationale, /Down Payment and Mortgage Rate/);
  });

  test("the chosen town is advisory, because no row holds a ZIP", () => {
    const advisory = OA.advisoryItems(housingOptimizerPatch(payload()));
    const loc = advisory.find((x) => /location/i.test(x.label));
    assert.ok(loc);
    assert.match(loc.after, /80024/);
    assert.match(loc.after, /Derby/);
    assert.equal(loc.row_index, undefined);
  });

  test("a row the plan does not have is skipped, not faked", () => {
    sandbox.window.rows = planRows().filter(
      (r) => !(r.section === "Other Assets" && r.label === "home_sale_year"),
    );
    const patch = housingOptimizerPatch(payload());
    assert.ok(!patch.some((x) => x.field === "home_sale_year"));
    // The rest of the patch still lands.
    assert.ok(patch.some((x) => x.field === "purchase_price"));
  });
});

describe("§4.6 applied state and un-apply on the structural shape", () => {
  const liveFrom = (world) => (idx) => world[idx];

  test("advisory items never keep a fully-written patch from reading applied", () => {
    const patch = housingOptimizerPatch(payload());
    const world = {};
    OA.promotableItems(patch).forEach((x) => {
      world[x.row_index] = x.afterRaw;
    });
    assert.ok(OA.advisoryItems(patch).length > 0, "this case needs advisories");
    assert.equal(
      OA.optimizerAppliedState(patch, liveFrom(world)),
      OA.APPLIED,
    );
  });

  test("a partially written plan reads diverged", () => {
    const patch = housingOptimizerPatch(payload());
    const items = OA.promotableItems(patch);
    const world = {};
    items.forEach((x, i) => {
      world[x.row_index] = i === 0 ? x.afterRaw : x.beforeRaw;
    });
    assert.equal(OA.optimizerAppliedState(patch, liveFrom(world)), OA.DIVERGED);
  });

  test("the reverse patch restores every written row's original text", () => {
    const patch = housingOptimizerPatch(payload());
    const rev = OA.reverseOptimizerPatch(patch);
    OA.promotableItems(rev).forEach((x) => {
      const original = patch.find((y) => y.row_index === x.row_index);
      assert.equal(x.afterRaw, original.beforeRaw);
    });
  });

  test("reversing carries the advisory items along unwritten", () => {
    const rev = OA.reverseOptimizerPatch(housingOptimizerPatch(payload()));
    assert.ok(OA.advisoryItems(rev).length > 0);
    for (const x of OA.advisoryItems(rev))
      assert.equal(x.row_index, undefined);
  });
});

describe("the results table carries the strip", () => {
  test("a rendered result offers apply", () => {
    const html = sandbox.renderHousingOptimizeResultsHtml(payload());
    assert.match(html, /housing-optimize-table/);
    assert.match(html, /optimizer-apply-strip/);
    assert.match(html, /Apply the recommended option/);
  });

  test("it says which row it applies", () => {
    const html = sandbox.renderHousingOptimizeResultsHtml(payload());
    assert.match(html, /starred \(rank 1\) option/);
  });

  test("it states the re-scaling caveat rather than leaving it a surprise", () => {
    const html = sandbox.renderHousingOptimizeResultsHtml(payload());
    assert.match(html, /re-scale automatically/);
    assert.match(html, /to within rounding/);
  });

  test("§4.6: it does not imply the provenance is durable", () => {
    const html = sandbox.renderHousingOptimizeResultsHtml(payload());
    assert.match(html, /this browser only/i);
  });

  test("an empty result renders the table's own empty state, not a strip", () => {
    const html = sandbox.renderHousingOptimizeResultsHtml(
      payload({ candidates: [] }),
    );
    assert.ok(!/optimizer-apply-strip/.test(html));
  });
});
