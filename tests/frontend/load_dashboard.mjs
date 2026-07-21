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
const JS_DIR = path.join(__dirname, "..", "..", "frontend", "js");
const DASHBOARD_JS_PATH = path.join(JS_DIR, "dashboard.js");
// esc/escJs/fmtMoney/fmtPct and the RPDashboardUtils formatters live here now
// (A13) — must load before dashboard.js, matching frontend/index.html's order.
const SHARED_HELPERS_PATH = path.join(JS_DIR, "dashboard_shared_helpers.js");

// dashboard.js's top-level checkAppStatus(true).then(...) chain calls
// refreshLocalBackupStatus() and other functions that now live in sibling
// dashboard_decomp_*.js modules (see frontend/index.html, which loads them
// as plain <script> tags alongside dashboard.js). In a real page load this
// is safe because fetch() is genuinely async, so every sibling script has
// already run by the time it resolves. The fetch stub below resolves as a
// microtask right after this file finishes evaluating, so every sibling
// module must be loaded into the same context first too, matching the
// convention already used by tests/_decomp_dashboard.py on the Python side.
function decompModulePaths() {
  return fs
    .readdirSync(JS_DIR)
    .filter((f) => f.startsWith("dashboard_decomp_") && f.endsWith(".js"))
    .sort()
    .map((f) => path.join(JS_DIR, f));
}

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
  const src = [SHARED_HELPERS_PATH, DASHBOARD_JS_PATH, ...decompModulePaths()]
    .map((p) => fs.readFileSync(p, "utf8"))
    .join("\n");
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
