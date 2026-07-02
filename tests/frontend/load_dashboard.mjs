// Minimal loader for exercising the pure/stateless helper functions defined
// in frontend/js/dashboard.js from Node's built-in test runner.
//
// dashboard.js is a single-page app script with no module system (loaded via
// a plain <script> tag) and no build step, so its ~810 functions are plain
// top-level declarations attached to whatever global object runs the script.
// Most of them are tightly coupled to a large set of shared mutable state
// (the `rows`/`dirty`/`activeStep`/... globals — see
// documentation/SYSTEM_REVIEW_AND_REFACTOR_PLAN.md Phase 2d) and cannot be
// safely unit-tested in isolation without a much larger DOM/fetch simulation
// effort. This loader deliberately targets only the small set of functions
// that take explicit parameters and return a value with no dependency on
// that shared state, so they can be tested directly against the real
// production source.
//
// Approach: run the actual dashboard.js source in a Node `vm` context with
// minimal window/document/localStorage stubs (just enough that the file's
// own top-level statements don't throw), then read the target functions off
// the sandbox object (function declarations are hoisted, so they exist on
// the sandbox regardless of what happens later in the file). The file's own
// bootstrap code calls renderMain() at the very end, which will throw
// against these minimal DOM stubs — that's expected and harmless; by the
// time it runs, every function declaration earlier in the file is already
// available on the sandbox.

import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DASHBOARD_JS_PATH = path.join(__dirname, "..", "..", "frontend", "js", "dashboard.js");

function noop() {}

function stubElement() {
  return {
    style: {},
    classList: { add: noop, remove: noop, toggle: noop, contains: () => false },
    addEventListener: noop,
    appendChild: noop,
    setAttribute: noop,
    textContent: "",
    value: "",
    disabled: false,
  };
}

export function loadDashboardSandbox() {
  const src = fs.readFileSync(DASHBOARD_JS_PATH, "utf8");
  const sandbox = {
    window: {
      addEventListener: noop,
      removeEventListener: noop,
      location: { href: "", search: "" },
      RPDashboardUtils: {},
      history: { pushState: noop, replaceState: noop },
    },
    document: {
      addEventListener: noop,
      getElementById: stubElement,
      querySelectorAll: () => [],
      querySelector: () => null,
      createElement: stubElement,
      body: stubElement(),
      documentElement: stubElement(),
    },
    localStorage: { getItem: () => null, setItem: noop, removeItem: noop },
    navigator: { clipboard: { writeText: async () => {} } },
    console,
    // Stubbed as no-ops rather than the real Node timer functions: dashboard.js
    // schedules a top-level `setInterval(checkAppStatus, 15000)` on load, which
    // would otherwise keep the real Node event loop (and `node --test`) alive
    // forever. None of the pure functions under test need real timer behavior.
    setTimeout: () => 0,
    clearTimeout: noop,
    setInterval: () => 0,
    clearInterval: noop,
    fetch: async () => ({ json: async () => ({}) }),
    URLSearchParams,
    Set,
    Map,
    Promise,
    Intl,
  };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  try {
    vm.runInContext(src, sandbox, { filename: "dashboard.js" });
  } catch (e) {
    // Expected: the file's own bootstrap render call at the bottom throws
    // against these minimal DOM stubs. All function declarations above it
    // are already hoisted onto `sandbox` by this point regardless.
  }
  return sandbox;
}
