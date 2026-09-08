// Finding UX-101 (system review 2026-09-07, Wave 5 item W4-7): the
// Annualize toggle (dashboard_shared_helpers.js's annualizeToggleBtn)
// conveyed its two states -- annualize vs. don't annualize, a real
// budget-overwrite-triggering choice -- by icon color alone (green/red on
// an identical calendar glyph), with no aria-pressed and no
// keyboard-focus-visible tooltip (only :hover).
import { test, describe } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const HELPERS_PATH = path.join(__dirname, "..", "..", "frontend", "js", "dashboard_shared_helpers.js");
const CSS_PATH = path.join(__dirname, "..", "..", "frontend", "css", "dashboard.css");

function loadHelpers() {
  const src = fs.readFileSync(HELPERS_PATH, "utf8").replace(/^export\s+/gm, "");
  const sandbox = { console };
  sandbox.globalThis = sandbox;
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  new vm.Script(src, { filename: "dashboard_shared_helpers.js" }).runInContext(sandbox);
  return sandbox;
}

describe("annualizeToggleBtn declares aria-pressed reflecting its state", () => {
  test("annualize (default) state is aria-pressed=true", () => {
    const { annualizeToggleBtn } = loadHelpers();
    const html = annualizeToggleBtn("toggle()", false);
    assert.ok(html.includes('aria-pressed="true"'), html);
  });

  test("do-not-annualize state is aria-pressed=false", () => {
    const { annualizeToggleBtn } = loadHelpers();
    const html = annualizeToggleBtn("toggle()", true);
    assert.ok(html.includes('aria-pressed="false"'), html);
  });

  test("both states keep an aria-label so the button has an accessible name", () => {
    const { annualizeToggleBtn } = loadHelpers();
    assert.ok(annualizeToggleBtn("toggle()", false).includes("aria-label="));
    assert.ok(annualizeToggleBtn("toggle()", true).includes("aria-label="));
  });
});

describe("annualize toggle states are distinguishable without color", () => {
  test("the two states carry different CSS state classes (color is not the only signal)", () => {
    const { annualizeToggleBtn } = loadHelpers();
    const on = annualizeToggleBtn("toggle()", false);
    const off = annualizeToggleBtn("toggle()", true);
    assert.ok(on.includes("state-annualize") && !on.includes("state-no-annualize"));
    assert.ok(off.includes("state-no-annualize"));
  });

  test("dashboard.css gives each state class a distinct non-color ::before badge glyph", () => {
    const css = fs.readFileSync(CSS_PATH, "utf8");
    const onMatch = css.match(/\.icon-annualize-toggle\.state-annualize::before\{content:"([^"]+)"/);
    const offMatch = css.match(/\.icon-annualize-toggle\.state-no-annualize::before\{content:"([^"]+)"/);
    assert.ok(onMatch, "no ::before badge rule found for .state-annualize");
    assert.ok(offMatch, "no ::before badge rule found for .state-no-annualize");
    assert.notEqual(
      onMatch[1], offMatch[1],
      "the two states' ::before badges must render different glyphs, not just different colors",
    );
  });

  test("dashboard.css shows the tooltip on :focus-visible, not only :hover", () => {
    const css = fs.readFileSync(CSS_PATH, "utf8");
    assert.match(
      css,
      /\.icon-annualize-toggle:focus-visible::after/,
      "keyboard-focused users get no tooltip -- :focus-visible must also trigger the data-tip ::after rule",
    );
  });
});
