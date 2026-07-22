// T1g (system review 2026-07-21, U1): 1280x800/1366x768/1440x900 render the
// 3-column grid but can't satisfy its width floor, causing horizontal
// overflow instead of the clean single-column fallback. A resize listener
// should auto-collapse the help pane in that gap (1180 < width < 1500),
// auto-restore it above 1500, and never override an explicit user choice.
import { test, describe, beforeEach } from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();

function makeClassList(initial = []) {
  const set = new Set(initial);
  return {
    add: (c) => set.add(c),
    remove: (c) => set.delete(c),
    toggle: (c) => (set.has(c) ? (set.delete(c), false) : (set.add(c), true)),
    contains: (c) => set.has(c),
  };
}
function makeLocalStorage(initial = {}) {
  const store = { ...initial };
  return {
    getItem: (k) => (Object.prototype.hasOwnProperty.call(store, k) ? store[k] : null),
    setItem: (k, v) => {
      store[k] = String(v);
    },
    removeItem: (k) => {
      delete store[k];
    },
  };
}

let messageCalls;

beforeEach(() => {
  sandbox.document.body.classList = makeClassList();
  sandbox.window.localStorage = makeLocalStorage();
  messageCalls = [];
  sandbox.showMessage = (...args) => messageCalls.push(args);
  // _autoHelpCollapsedActive is a private top-level `let`, not a sandbox
  // property (same as any other non-function top-level declaration) -- but
  // the sandbox is already a vm-contextified object, so it can be reset
  // directly, keeping each test's starting state independent of prior tests.
  vm.runInContext("_autoHelpCollapsedActive = false;", sandbox);
});

describe("autoCollapseHelpForNarrowLaptop", () => {
  test("collapses help and shows a one-time notice in the 1180-1500px gap", () => {
    sandbox.window.innerWidth = 1366;
    sandbox.autoCollapseHelpForNarrowLaptop();
    assert.ok(sandbox.document.body.classList.contains("help-collapsed"));
    assert.equal(messageCalls.length, 1);
  });

  test("does not re-show the notice after cycling wide then narrow again", () => {
    sandbox.window.innerWidth = 1366;
    sandbox.autoCollapseHelpForNarrowLaptop(); // collapse + notice #1
    sandbox.window.innerWidth = 1760;
    sandbox.autoCollapseHelpForNarrowLaptop(); // auto-restore
    sandbox.window.innerWidth = 1366;
    sandbox.autoCollapseHelpForNarrowLaptop(); // collapse again
    assert.ok(sandbox.document.body.classList.contains("help-collapsed"));
    assert.equal(messageCalls.length, 1, "notice should only ever fire once (persisted in localStorage)");
  });

  test("restores help above 1500px if it was auto-collapsed", () => {
    sandbox.window.innerWidth = 1366;
    sandbox.autoCollapseHelpForNarrowLaptop();
    assert.ok(sandbox.document.body.classList.contains("help-collapsed"));
    sandbox.window.innerWidth = 1760;
    sandbox.autoCollapseHelpForNarrowLaptop();
    assert.ok(!sandbox.document.body.classList.contains("help-collapsed"));
  });

  test("does nothing at or below 1180px (single-column fallback already applies)", () => {
    sandbox.window.innerWidth = 1024;
    sandbox.autoCollapseHelpForNarrowLaptop();
    assert.ok(!sandbox.document.body.classList.contains("help-collapsed"));
    assert.equal(messageCalls.length, 0);
  });

  test("never overrides an explicit user preference (localStorage set)", () => {
    sandbox.window.localStorage = makeLocalStorage({ retirementHelpCollapsed: "0" });
    sandbox.window.innerWidth = 1366;
    sandbox.autoCollapseHelpForNarrowLaptop();
    assert.ok(!sandbox.document.body.classList.contains("help-collapsed"));
    assert.equal(messageCalls.length, 0);
  });

  test("does not fight a user who manually collapsed even above 1500px", () => {
    sandbox.window.localStorage = makeLocalStorage({ retirementHelpCollapsed: "1" });
    sandbox.document.body.classList.add("help-collapsed");
    sandbox.window.innerWidth = 1760;
    sandbox.autoCollapseHelpForNarrowLaptop();
    assert.ok(sandbox.document.body.classList.contains("help-collapsed"));
  });
});
