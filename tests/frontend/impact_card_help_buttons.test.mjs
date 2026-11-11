// W3-06 / UX-004: Build Impact card "i" buttons open the help panel, and Worst-Case shows its percentile.

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();
const before = { lcv: 1e7, npv_future_taxes: 4e5, terminal_nw_mc_p5: 3e6, eftr: 0.12 };
const after = { lcv: 1.1e7, npv_future_taxes: 3.5e5, terminal_nw_mc_p5: 3.5e6, eftr: 0.1 };

describe("impact card help buttons", () => {
  test("every card info button controls the help panel", () => {
    const html = sandbox.buildImpactCardsHtml(before, after);
    const buttons = html.match(/<button[^>]*field-info-i[^>]*>/g) || [];
    assert.equal(buttons.length, 4);
    for (const b of buttons) {
      assert.match(b, /aria-controls="helpPanel"/);
      assert.match(b, /onclick="openImpactHelp\(this\)"/);
    }
  });

  test("Worst-Case card states its percentile without a hover", () => {
    const html = sandbox.buildImpactCardsHtml(before, after);
    assert.match(html, /Worst-Case Ending Wealth[\s\S]*5th percentile of simulated outcomes/);
  });
});
