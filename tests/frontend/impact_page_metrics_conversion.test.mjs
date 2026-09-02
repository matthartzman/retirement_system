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
    assert.match(html, /Worst-Case Ending Wealth \(5th %ile\)/);
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
