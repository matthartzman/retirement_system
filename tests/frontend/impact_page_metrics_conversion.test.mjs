// Ticket 293: the Impact page's headline metrics were converted --
// Terminal Net Worth -> LCV, Lifetime Taxes -> NPV of Future Taxes,
// Probability of Success -> Worst-Case Ending Wealth (5th percentile), plus
// a new Effective Future Tax Rate (EFTR) stat.

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();

describe("buildImpactCardsHtml (ticket 293)", () => {
  test("renders LCV, NPV of Future Taxes, Worst-Case Ending Wealth, and EFTR cards", () => {
    const before = {
      lcv: 10_000_000,
      npv_future_taxes: 400_000,
      terminal_nw_mc_p5: 3_000_000,
      eftr: 0.12,
    };
    const after = {
      lcv: 11_000_000,
      npv_future_taxes: 350_000,
      terminal_nw_mc_p5: 3_500_000,
      eftr: 0.10,
    };
    const html = sandbox.buildImpactCardsHtml(before, after);
    assert.match(html, /Expected After-Tax LCV/);
    assert.match(html, /NPV of Future Taxes/);
    // #309: the card title itself dropped the "(5th %ile)" suffix (it kept
    // wrapping to 2 lines at card width) -- the tooltip still states
    // "5th-percentile" in full, so the info isn't lost, only relocated.
    assert.match(html, /Worst-Case Ending Wealth/);
    assert.match(html, /5th-percentile ending net worth/);
    assert.match(html, /Effective Future Tax Rate \(EFTR\)/);
    // Old metric labels must not leak back in.
    assert.doesNotMatch(html, /Terminal net worth/);
    assert.doesNotMatch(html, /Lifetime taxes/);
    assert.doesNotMatch(html, /Probability of Success/);
  });

  test("handles missing Monte Carlo data without throwing", () => {
    const before = { lcv: 1000, npv_future_taxes: 100 };
    const after = { lcv: 1100, npv_future_taxes: 90 };
    const html = sandbox.buildImpactCardsHtml(before, after);
    assert.match(html, /Monte Carlo results were not available/);
  });
});

describe("currentKpi (ticket 293)", () => {
  test("resolves lcv, npv_future_taxes, terminal_nw_mc_p5, and eftr from a summary payload", () => {
    const summary = {
      lcv: 5_000_000,
      npv_future_taxes: 250_000,
      terminal_nw_mc_p5: 1_500_000,
      eftr: 0.15,
    };
    const k = sandbox.currentKpi(summary);
    assert.equal(k.lcv, 5_000_000);
    assert.equal(k.npv_future_taxes, 250_000);
    assert.equal(k.terminal_nw_mc_p5, 1_500_000);
    assert.equal(k.eftr, 0.15);
  });
});

// Ticket 309: the "Suggestions to improve the plan" panel and the Build
// History dials were missed when ticket 293 converted the 4 headline cards
// -- they kept generating text/labels from the retired Terminal Net Worth /
// Lifetime Taxes / Probability of Success fields even though the before/
// after KPI objects passed in already carried the new fields.
describe("buildImpactSuggestionsHtml (ticket 309)", () => {
  test("suggestion text and footer reference the new KPIs, not the retired ones", () => {
    const before = {
      lcv: 16_145_753,
      npv_future_taxes: 796_412,
      terminal_nw_mc_p5: 4_066_647,
      eftr: 0.124,
    };
    const after = {
      lcv: 16_203_602,
      npv_future_taxes: 805_641,
      terminal_nw_mc_p5: 4_066_781,
      eftr: 0.125,
    };
    const html = sandbox.buildImpactSuggestionsHtml(before, after, {});
    assert.match(html, /Worst-Case Ending Wealth/);
    assert.match(html, /NPV of Future Taxes/);
    assert.match(html, /Expected After-Tax LCV|LCV/);
    assert.doesNotMatch(html, /Monte Carlo success/);
    assert.doesNotMatch(html, /Lifetime taxes/);
    assert.doesNotMatch(html, /Terminal net worth/);
    assert.doesNotMatch(html, /terminal net worth/);
  });

  test("still counts and labels the suggestions as dynamic tests", () => {
    const html = sandbox.buildImpactSuggestionsHtml({}, {}, {});
    assert.match(html, /\d+ dynamic tests/);
  });
});

describe("buildHistoryEntryHtml (ticket 309)", () => {
  test("renders 4 dials for the new KPIs, not the retired PTI/Lifetime Tax/Success % trio", () => {
    const entry = {
      id: "1",
      label: "Build",
      timestamp: Date.now(),
      kpi: {
        lcv: 16_203_602,
        npv_future_taxes: 805_641,
        terminal_nw_mc_p5: 4_066_781,
        eftr: 0.125,
      },
      changes: [],
    };
    const heat = {
      nwHeat: () => 0.5,
      taxHeat: () => 0.5,
      mcHeat: () => 0.5,
      eftrHeat: () => 0.5,
    };
    const html = sandbox.buildHistoryEntryHtml(entry, true, heat);
    assert.match(html, /Expected After-Tax LCV/);
    assert.match(html, /NPV of Future Taxes/);
    assert.match(html, /Worst-Case Ending Wealth/);
    assert.match(html, /Effective Future Tax Rate/);
    assert.doesNotMatch(html, /Post-Tax Inheritance/);
    assert.doesNotMatch(html, />Lifetime Tax</);
    assert.doesNotMatch(html, />Success %</);
  });
});

describe("loadBuildHistory (ticket 309)", () => {
  test("drops pre-#293 entries that have no kpi.lcv instead of rendering them with missing KPIs", () => {
    const fresh = loadDashboardSandbox();
    const stored = JSON.stringify([
      { id: "old", kpi: { inheritable_nw: 100, lifetime_tax: 10, mc_success: 0.9 } },
      { id: "new", kpi: { lcv: 5000, npv_future_taxes: 100, terminal_nw_mc_p5: 2000, eftr: 0.1 } },
    ]);
    fresh.localStorage.getItem = () => stored;
    let saved = null;
    fresh.localStorage.setItem = (_k, v) => {
      saved = v;
    };
    fresh.loadBuildHistory();
    // Cross-realm arrays (vm sandbox vs. this test's own realm) compare
    // unequal under assert.deepEqual despite identical content -- stringify
    // to sidestep the realm mismatch rather than the values under test.
    const ids = Array.prototype.map.call(fresh.window.buildHistory || [], (e) => e.id);
    assert.equal(JSON.stringify(ids), JSON.stringify(["new"]));
    assert.ok(saved, "should persist the filtered list back to localStorage");
    const savedIds = Array.prototype.map.call(JSON.parse(saved), (e) => e.id);
    assert.equal(JSON.stringify(savedIds), JSON.stringify(["new"]));
  });
});
