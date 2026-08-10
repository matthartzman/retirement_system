// Minimal loader for exercising the pure/stateless helper functions defined
// in frontend/js/dashboard.js from Node's built-in test runner.
//
// dashboard.js and the dashboard_decomp_*.js leaf modules are loaded by
// index.html as real ES modules (<script type="module">), each exporting its
// top-level functions with `export function`/`export const` and also
// bridging them onto `window` for the inline onclick/onchange HTML attributes
// that still call them as bare globals. This loader concatenates all of them
// and runs the result through Node's `vm` as one classic (non-module) script
// so every function's declaration hoists onto a single sandbox object,
// regardless of which file it lives in -- `vm` doesn't parse ES module syntax
// in script mode, so the literal `export ` keyword is stripped from each
// declaration first (leaving the plain `function`/`const` declaration, which
// is exactly what a classic script needs and is a no-op change to the code
// actually under test). No `import`/`export {...}` grouped-export syntax
// exists in any of these files today; if that changes, this stripping will
// need to grow with it. Most of the remaining ~810 functions are tightly
// coupled to a large set of shared mutable state (the `rows`/`dirty`/
// `activeStep`/... globals — see
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
const INDEX_HTML_PATH = path.join(__dirname, "..", "..", "frontend", "index.html");

// dashboard.js's top-level code isn't just function declarations -- e.g.
// `const STEP_HELP = {start: pageHelp(...), ...}` calls into
// dashboard_decomp_row_model.js's exports (acronymDefinitionsHtml,
// formatAcronyms) as bare identifiers, immediately, at module-evaluation
// time. Real ES modules don't share scope, so that only resolves at all
// because it falls through to the global object -- and only resolves
// *correctly* because frontend/index.html loads row_model.js's <script
// type="module"> tag BEFORE dashboard.js's, so row_model.js's own
// window-bridge has already run by the time dashboard.js's top-level code
// executes. Concatenating these files in any order other than index.html's
// real one (e.g. alphabetically, or dashboard.js first) reproduces exactly
// this ReferenceError against real production code for a reason that has
// nothing to do with the code being tested -- an "environment-only"
// failure. Deriving the load order from index.html itself, rather than
// hand-maintaining an order that has to be kept in sync with it by hand,
// is what makes this loader keep matching reality as the page's own script
// tags are reordered.
//
// dashboard.js's top-level checkAppStatus(true).then(...) chain also calls
// refreshLocalBackupStatus() and other functions that live in sibling
// dashboard_decomp_*.js modules. In a real page load this is safe because
// fetch() is genuinely async, so every sibling script has already run by
// the time it resolves. The fetch stub below resolves as a microtask right
// after this file finishes evaluating, so every sibling module must be
// loaded into the same context first too, matching the convention already
// used by tests/_decomp_dashboard.py on the Python side.
function orderedDashboardScriptPaths() {
  const html = fs.readFileSync(INDEX_HTML_PATH, "utf8");
  const names = [...html.matchAll(/<script[^>]*\ssrc="js\/([^"?]+\.js)(?:\?[^"]*)?"/g)].map(
    (m) => m[1],
  );
  const wanted = new Set(
    fs
      .readdirSync(JS_DIR)
      .filter((f) => f === "dashboard_shared_helpers.js" || f === "dashboard.js" || (f.startsWith("dashboard_decomp_") && f.endsWith(".js"))),
  );
  const ordered = names.filter((n) => wanted.has(n));
  const missing = [...wanted].filter((n) => !ordered.includes(n));
  if (missing.length) {
    throw new Error(
      `load_dashboard.mjs: index.html is missing a <script> tag for ${missing.join(", ")} -- ` +
        "this loader's file set must exactly match what real production loads, " +
        "or the sandbox no longer represents the real page.",
    );
  }
  return ordered.map((n) => path.join(JS_DIR, n));
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

// Strips the leading `export ` off a top-level `export function`/
// `export const`/`export async function` declaration, turning it into the
// plain declaration a classic (non-module) vm script can parse. Only matches
// at the start of a line so it can't touch an unrelated identifier that
// merely contains the word "export" elsewhere in a string or comment.
function stripEsmExports(src) {
  return src.replace(/^export (function|const|async function)/gm, "$1");
}

export function loadDashboardSandbox() {
  const src = stripEsmExports(
    orderedDashboardScriptPaths()
      .map((p) => fs.readFileSync(p, "utf8"))
      .join("\n"),
  );
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
    // dashboard.js's own top-level bootstrap is wrapped in queueMicrotask()
    // (deliberately, so it runs after every sibling module's window-bridge --
    // see orderedDashboardScriptPaths() above). A vm sandbox is not a real
    // JS host environment and does not provide this as a global on its own;
    // omitting it entirely throws "queueMicrotask is not defined" as an
    // *uncaught* ReferenceError during the top-level script run, which halts
    // execution immediately and silently drops every file ordered after
    // dashboard.js in real production (workbook_formatting, state_inputs,
    // home_panels, holdings) -- none of their declarations ever hoist onto
    // the sandbox. A no-op (never invoking the callback) is correct here for
    // the same reason the timer stubs above are: the pure functions under
    // test need no real deferred/async bootstrap behavior.
    queueMicrotask: noop,
    fetch: async () => ({ json: async () => ({}) }),
    URLSearchParams,
    Set,
    Map,
    Promise,
    Intl,
  };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  // Compiling and running are separate steps deliberately: a SyntaxError here
  // means nothing in `src` executed at all (no function declarations hoisted
  // onto `sandbox`), which is never expected and must fail loudly -- unlike
  // dashboard.js's own bootstrap render call at the bottom of the *running*
  // script, which throws against these minimal DOM stubs on every load and
  // is the one error this loader is meant to swallow.
  const script = new vm.Script(src, { filename: "dashboard.js" });
  try {
    script.runInContext(sandbox);
  } catch (e) {
    // Expected: see above. All function declarations earlier in the file
    // are already hoisted onto `sandbox` by this point regardless.
  }
  return sandbox;
}
