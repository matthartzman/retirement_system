// T1f (system review 2026-07-21, U4): the three cross-page help strings that
// used to just name the (now-hidden) "Roth Conversion" / "Asset allocation &
// location" pages in plain text must become clickable links to the
// consolidated "Distribution Strategy" step that now hosts those tabs.
import { test, describe } from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
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
      helpLink: { id: "roth_conversion", label: "Open Roth Conversion" },
    });
    assert.match(html, /<a href="#" onclick="setStep\('roth_conversion'\);return false">/);
    assert.match(html, />Open Roth Conversion<\/a>/);
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

// #323: these three steps point the reader at wherever Roth conversion is
// actually configured. That used to be the Distribution Strategy page; it is
// now the Roth Conversion section of Strategy -> Optimize. The guard is the
// same one it always was -- the link must name a destination that still
// resolves -- so it asserts the id is one navigation.js knows how to route,
// rather than hard-coding whichever screen currently owns the section.
describe("STEPS entries link to a live Roth conversion destination", () => {
  for (const id of ["income_work", "income_retirement", "withdrawal_strategy"]) {
    test(`${id}.helpLink points at the Roth conversion destination`, () => {
      const step = stepById(id);
      assert.ok(step, `expected a STEPS entry with id ${id}`);
      assert.equal(step.helpLink?.id, "roth_conversion");
      assert.ok(String(step.helpLink?.label || "").length > 0);
    });
  }

  test("that destination is routable rather than a dead id", () => {
    const navSrc = fs.readFileSync(
      path.join(HERE, "..", "..", "frontend", "js", "navigation.js"),
      "utf8",
    );
    // Cheap reachability check: navigation.js must carry a redirect entry for
    // the id, since roth_conversion is a hidden shell step with no nav button
    // of its own. tests/frontend/strategy_section_redirects.test.mjs asserts
    // where it actually lands.
    assert.match(navSrc, /roth_conversion:\s*\{\s*step:\s*'strategy_optimize'/);
  });
});
