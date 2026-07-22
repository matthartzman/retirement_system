// T1d (system review 2026-07-21, D2): the max-Sharpe/tangency allocation
// labels must lead with a plain-language outcome (not raw "Sharpe"/"tangency"
// jargon) in both places they're defined, and the terms must be registered
// in the glossary so acronymDefinitionsHtml() picks them up.
import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();

const EXPECTED_MAX_SHARPE =
  "Best risk-adjusted mix within your risk limits (max-Sharpe, risk-budgeted)";
const EXPECTED_TANGENCY =
  "Best risk-adjusted mix with no risk limits applied (max-Sharpe, pure tangency)";

describe("allocation_selection_mode choice options (Roth/Allocation step dropdown)", () => {
  test("max_sharpe and tangency lead with plain-language outcome text", () => {
    const opts = sandbox.choiceOptions({ label: "allocation_selection_mode" });
    const byValue = Object.fromEntries(opts.map((o) => [o.value, o.label]));
    assert.equal(byValue.max_sharpe, EXPECTED_MAX_SHARPE);
    assert.equal(byValue.tangency, EXPECTED_TANGENCY);
  });
});

describe("allocationModeHtml (Allocation Mode button row)", () => {
  test("max_sharpe and tangency buttons match the same plain-language wording", () => {
    const html = sandbox.allocationModeHtml();
    assert.match(html, new RegExp(EXPECTED_MAX_SHARPE.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
    assert.match(html, new RegExp(EXPECTED_TANGENCY.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  });
});

describe("ACRONYM_DEFINITIONS glossary", () => {
  test("Sharpe and tangency resolve to plain-language definitions", () => {
    const html = sandbox.acronymDefinitionsHtml([EXPECTED_MAX_SHARPE, EXPECTED_TANGENCY]);
    assert.match(html, /<b>Sharpe<\/b>: Sharpe ratio/);
    assert.match(html, /<b>tangency<\/b>: Tangency portfolio/);
  });
});
