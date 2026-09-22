// W10a: the Roth optimizer's result panel (#329 P5, §4.5 path 1).
//
// §1.3 records what this section was before: "Input form. Policy/guardrail/
// calibration rows. No result shown; the candidate table exists only on
// workbook 11. Roth Conversion." These assertions are about what is now on
// screen instead.
//
// rothOptimizerResultPanelHtml() is deliberately pure -- it prints only what
// is in the payload handed to it -- so it can be exercised against a payload
// without a build, a DOM, or any of dashboard_decomp_allocation_optimizer.js's
// shared mutable state. Obtained via loadDashboardSandbox() rather than a
// direct import, the same way housing_optimize_results.test.mjs does it (that
// file's header explains why these are not importable ES modules here).

import { test } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

function render(payload) {
  const { rothOptimizerResultPanelHtml } = loadDashboardSandbox();
  return rothOptimizerResultPanelHtml(payload);
}

function candidate(over = {}) {
  return {
    rank: 1,
    label: "Fill to 24% bracket",
    policy: "fill_to_bracket",
    relative_score: 100,
    objective_value: 4210000,
    total_conversions: 480000,
    lifetime_tax: 812000,
    after_tax_terminal_net_worth: 5310000,
    why_selected_or_rejected:
      "Selected because it produced the highest total objective score.",
    ...over,
  };
}

function payload(over = {}) {
  return {
    selected_strategy_name: "Fill to 24% bracket",
    selected_policy: "fill_to_bracket",
    objective_mode: "BALANCED_RETIREMENT",
    target_bracket: 0.24,
    auto_optimized: true,
    forced_conversions: 30000,
    voluntary_conversions: 450000,
    total_conversions: 480000,
    lifetime_tax: 812000,
    after_tax_terminal_net_worth: 5310000,
    why_selected: "The selected strategy is Fill to 24% bracket.",
    explanation: "Forced conversions total $30,000.",
    candidates: [
      candidate(),
      candidate({
        rank: 2,
        label: "No voluntary conversions",
        policy: "none",
        relative_score: 0,
        total_conversions: 30000,
        lifetime_tax: 905000,
        after_tax_terminal_net_worth: 5090000,
        why_selected_or_rejected: "Not selected: lower total objective score.",
      }),
    ],
    candidate_count: 2,
    ...over,
  };
}

test("no result renders nothing rather than an empty frame", () => {
  assert.equal(render(null), "");
  assert.equal(render(undefined), "");
});

test("the candidate comparison reaches the screen", () => {
  const html = render(payload());
  assert.match(html, /Fill to 24% bracket/);
  assert.match(html, /No voluntary conversions/);
  assert.match(html, /Not selected: lower total objective score\./);
  assert.match(html, /Score \(0-100\)/);
});

test("the candidate the plan is actually running is marked", () => {
  const html = render(payload());
  const rows = html.split("<tr").slice(2); // drop everything before the body
  assert.match(rows[0], /is-selected/);
  assert.match(rows[0], /In the plan/);
  assert.doesNotMatch(rows[1], /is-selected/);
});

test("the mark follows the selected strategy, not rank 1", () => {
  // §4.6 and the contract's own why_selected text both distinguish "the
  // optimizer picked this" from "you picked this". When the user picked a
  // strategy the optimizer did not rank first, the row in the plan is not
  // row 1, and marking row 1 would name the wrong one.
  const html = render(
    payload({ selected_strategy_name: "No voluntary conversions" }),
  );
  const rows = html.split("<tr").slice(2);
  assert.doesNotMatch(rows[0], /is-selected/);
  assert.match(rows[1], /is-selected/);
});

test("the score column is disclosed as a relative ranking", () => {
  // Sheet 11's own wording for the same column. Without it, "100" next to a
  // strategy reads as a projected outcome.
  const html = render(payload());
  assert.match(html, /ranks these candidates relative to each other/);
  assert.match(html, /not a projected dollar outcome/);
});

test("a trimmed candidate list says how many were scored", () => {
  const html = render(payload({ candidate_count: 17 }));
  assert.match(html, /Showing the top 2 of 17 scored candidates/);
});

test("an untrimmed list makes no claim about hidden candidates", () => {
  assert.doesNotMatch(render(payload()), /Showing the top/);
});

test("a result with no scored alternatives says so instead of drawing an empty table", () => {
  const html = render(payload({ candidates: [], candidate_count: 0 }));
  assert.match(html, /scored no alternative strategies/);
  assert.doesNotMatch(html, /<table/);
});

test("the target bracket is printed as a percentage of its fraction", () => {
  const html = render(payload({ target_bracket: 0.24 }));
  assert.match(html, /24%/);
});

test("missing figures read as unavailable rather than as zero", () => {
  // summary_figures returns None rather than a placeholder when a figure is
  // unavailable; a null must not surface as "$0".
  const html = render(
    payload({
      lifetime_tax: null,
      candidates: [candidate({ after_tax_terminal_net_worth: null })],
      candidate_count: 1,
    }),
  );
  assert.match(html, /Not available/);
  assert.doesNotMatch(html, /\$0\b/);
});

test("the explanation and the why-selected sentence are both shown", () => {
  const html = render(payload());
  assert.match(html, /The selected strategy is Fill to 24% bracket\./);
  assert.match(html, /Forced conversions total \$30,000\./);
});

test("candidate text is escaped, not injected", () => {
  const html = render(
    payload({
      selected_strategy_name: "<script>x</script>",
      candidates: [candidate({ label: "<script>x</script>" })],
      candidate_count: 1,
    }),
  );
  assert.doesNotMatch(html, /<script>x<\/script>/);
  assert.match(html, /&lt;script&gt;/);
});
