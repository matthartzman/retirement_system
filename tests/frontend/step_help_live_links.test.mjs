// T1f (system review 2026-07-21, U4): the three cross-page help strings that
// used to just name the (now-hidden) "Roth Conversion" / "Asset allocation &
// location" pages in plain text must become clickable links to the
// consolidated "Distribution Strategy" step that now hosts those tabs.
import { test, describe } from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();

function stepById(id) {
  // STEPS is a top-level `const`, so it isn't a property of the sandbox
  // object the way `function`-declared helpers are -- but the sandbox is
  // already a vm-contextified object, so it can be queried directly.
  return vm.runInContext(
    `STEPS.find((s) => s.id === ${JSON.stringify(id)})`,
    sandbox,
  );
}

describe("stepHelpLinkHtml (pure render helper)", () => {
  test("renders a clickable setStep() link when helpLink is present", () => {
    const html = sandbox.stepHelpLinkHtml({
      helpLink: { id: "distribution_strategy", label: "Open Distribution Strategy" },
    });
    assert.match(html, /<a href="#" onclick="setStep\('distribution_strategy'\);return false">/);
    assert.match(html, />Open Distribution Strategy<\/a>/);
  });
  test("escapes the label text", () => {
    const html = sandbox.stepHelpLinkHtml({
      helpLink: { id: "x", label: "<b>evil</b>" },
    });
    assert.doesNotMatch(html, /<b>evil<\/b>/);
    assert.match(html, /&lt;b&gt;evil&lt;\/b&gt;/);
  });
  test("returns empty string when no helpLink is set", () => {
    assert.equal(sandbox.stepHelpLinkHtml({}), "");
    assert.equal(sandbox.stepHelpLinkHtml(null), "");
  });
});

describe("STEPS entries carry a helpLink to distribution_strategy", () => {
  for (const id of ["income_work", "income_retirement", "withdrawal_strategy"]) {
    test(`${id}.helpLink points at distribution_strategy`, () => {
      const step = stepById(id);
      assert.ok(step, `expected a STEPS entry with id ${id}`);
      assert.equal(step.helpLink?.id, "distribution_strategy");
      assert.ok(String(step.helpLink?.label || "").length > 0);
    });
  }
});
