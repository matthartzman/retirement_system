// Bug: typing the first character into a Next Housing Step's purchase_price
// or monthly_rent field right after "Estimate fields" filled the siblings
// (insurance/utilities/maintenance/HOA) loses focus and scroll position,
// forcing the user to reselect the field to finish typing.
//
// Root cause, traced end to end:
//   1. Every text input rendered by fieldHtml() fires editValue() on
//      `oninput` -- i.e. on every keystroke, not on blur/change.
//   2. editValue() on a Housing row calls
//      reestimateHousingCostsOnValueChange() (ticket 298), which -- as soon
//      as the sibling insurance/utilities/maintenance fields are nonzero,
//      which is exactly the state right after an estimate -- returns a
//      nonzero adjustment on the very first keystroke and triggers a
//      synchronous renderMain() mid-edit.
//   3. renderMain() replaces #mainPane's entire innerHTML. The general
//      focus-preservation fix (ticket 285, captureMainPaneFocus /
//      restoreMainPaneFocus) only revives an element that carries a stable
//      `data-focus-key` attribute -- fieldHtml()'s generic text/money input
//      never set one, so capture is a no-op and the freshly-typed-into
//      input is destroyed with nothing to restore focus to.
//
// Fix: fieldHtml()'s generic input branches now stamp `data-focus-key`
// from the row's own stable row_index, so ticket 285's existing mechanism
// can find and refocus the field after any mid-edit renderMain() -- for
// Housing price/rent and for every other field sharing this same template.

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();

function baseSetup() {
  sandbox.window.rows = [];
  sandbox.dirty = new Map();
}

describe("fieldHtml() data-focus-key (ticket 285 coverage for housing price/rent)", () => {
  test("a plain money field (e.g. Housing purchase_price) carries a stable data-focus-key", () => {
    baseSetup();
    const row = {
      row_index: 42,
      section: "Housing",
      subsection: "next_step_1",
      label: "purchase_price",
      value: "400000",
      units: "",
      schema: { type: "money" },
    };
    const html = sandbox.fieldHtml(row);
    assert.match(html, /data-focus-key="field:42"/);
  });

  test("a plain money field (e.g. Housing monthly_rent) carries a stable data-focus-key", () => {
    baseSetup();
    const row = {
      row_index: 77,
      section: "Housing",
      subsection: "next_step_2",
      label: "monthly_rent",
      value: "2000",
      units: "",
      schema: { type: "money" },
    };
    const html = sandbox.fieldHtml(row);
    assert.match(html, /data-focus-key="field:77"/);
  });

  test("the data-focus-key round-trips through captureMainPaneFocus/restoreMainPaneFocus", () => {
    baseSetup();
    const row = {
      row_index: 42,
      section: "Housing",
      subsection: "next_step_1",
      label: "purchase_price",
      value: "400000",
      units: "",
      schema: { type: "money" },
    };
    const html = sandbox.fieldHtml(row);
    const m = html.match(/data-focus-key="([^"]+)"/);
    assert.ok(m, "fieldHtml() output must carry a data-focus-key for capture/restore to work");

    // Simulate the element captureMainPaneFocus/restoreMainPaneFocus would
    // see: a focused <input> inside #mainPane carrying this data-focus-key.
    const fakeInput = {
      getAttribute: (name) => (name === "data-focus-key" ? m[1] : null),
      value: "4000001",
      selectionStart: 7,
      selectionEnd: 7,
    };
    const mainPane = { contains: () => true };
    const priorActiveElement = sandbox.document.activeElement;
    sandbox.document.activeElement = fakeInput;
    let queried = null;
    sandbox.document.querySelector = (sel) => {
      queried = sel;
      return sel === `[data-focus-key="${m[1]}"]` ? fakeInput : null;
    };
    sandbox.CSS = { escape: (s) => s };
    try {
      const state = sandbox.captureMainPaneFocus(mainPane);
      assert.ok(state, "capture should not be a no-op once a data-focus-key exists");
      assert.equal(state.focusKey, m[1]);

      let focused = false;
      fakeInput.focus = () => {
        focused = true;
      };
      fakeInput.setSelectionRange = () => {};
      sandbox.restoreMainPaneFocus(state);
      assert.equal(focused, true, "restoreMainPaneFocus should refocus the revived element");
      assert.equal(queried, `[data-focus-key="${m[1]}"]`);
    } finally {
      sandbox.document.activeElement = priorActiveElement;
    }
  });
});
