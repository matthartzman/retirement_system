// UX-010 (system review 2026-09-25, Wave 5 item WI-509): the current step,
// the nav search scope and the trends-reporter timeframe were shown only by
// a CSS class (colour). The active step button now carries
// aria-current="step" and the scope/timeframe toggles carry aria-pressed
// that follows the selection. Each check drives the real production code.

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(HERE, "..", "..");
const noop = () => {};

function stubEl(id) {
  return {
    id,
    innerHTML: "",
    textContent: "",
    style: {},
    classList: { add: noop, remove: noop, toggle: noop, contains: () => false },
    setAttribute: noop,
    querySelectorAll: () => [],
    querySelector: () => null,
    addEventListener: noop,
  };
}

describe("left nav: the active step button has aria-current=step", () => {
  const sandbox = loadDashboardSandbox();
  const run = (code) => vm.runInContext(code, sandbox);

  function renderStepsFor(step) {
    const els = {};
    sandbox.document.getElementById = (id) => (els[id] ||= stubEl(id));
    run(`planLoaded = true; activeStep = ${JSON.stringify(step)};`);
    try {
      run("renderSteps()");
    } catch (_e) {}
    return els.steps ? els.steps.innerHTML : "";
  }

  test("exactly one step button is aria-current, and it is the active one", () => {
    const html = renderStepsFor("household_people");
    const current = [...html.matchAll(/<button class="stepbtn[^>]*aria-current="step"[^>]*>/g)];
    assert.equal(current.length, 1, html.slice(0, 400));
    assert.match(current[0][0], /data-step-id="household_people"/);
    assert.match(current[0][0], /class="stepbtn active"/);
  });

  test("aria-current follows navigation", () => {
    const html = renderStepsFor("income_work");
    const current = html.match(/<button class="stepbtn[^>]*aria-current="step"[^>]*>/);
    assert.match(current[0], /data-step-id="income_work"/);
  });
});

describe("nav search scope toggles expose aria-pressed", () => {
  function loadNav(buttons) {
    const box = {
      console,
      setTimeout: () => 0,
      clearTimeout: noop,
      localStorage: { getItem: () => null, setItem: noop, removeItem: noop },
      document: {
        getElementById: () => null,
        querySelector: () => null,
        querySelectorAll: (sel) => (sel === "[data-search-scope]" ? buttons : []),
        addEventListener: noop,
      },
    };
    box.window = box;
    box.globalThis = box;
    vm.createContext(box);
    vm.runInContext(fs.readFileSync(path.join(ROOT, "frontend", "js", "navigation.js"), "utf8"), box);
    return box.window.RetirementNavigation;
  }

  function scopeButton(scope) {
    const classes = new Set();
    return {
      dataset: { searchScope: scope },
      attrs: {},
      setAttribute(k, v) {
        this.attrs[k] = v;
      },
      classList: { toggle: (c, on) => (on ? classes.add(c) : classes.delete(c)) },
    };
  }

  for (const scope of ["nav", "page"]) {
    test(`selecting ${scope} marks only that button pressed`, () => {
      const btns = [scopeButton("nav"), scopeButton("page")];
      loadNav(btns).updateSearchToggle({ getSearchScope: () => scope });
      for (const b of btns) {
        assert.equal(b.attrs["aria-pressed"], b.dataset.searchScope === scope ? "true" : "false");
      }
    });
  }

  test("the static markup starts in the same state (Navigation pressed)", () => {
    const html = fs.readFileSync(path.join(ROOT, "frontend", "index.html"), "utf8");
    assert.match(html, /data-search-scope="nav" aria-pressed="true"/);
    assert.match(html, /data-search-scope="page" aria-pressed="false"/);
  });
});

describe("trends reporter timeframe buttons expose aria-pressed", () => {
  const INDEX = path.join(ROOT, "financial_trends_reporter", "frontend", "index.html");
  const html = fs.readFileSync(INDEX, "utf8");

  test("initial markup: only the default YTD button is pressed", () => {
    const tf = [...html.matchAll(/<button data-tf="([^"]+)"[^>]*aria-pressed="(true|false)"/g)];
    assert.ok(tf.length >= 7, "every timeframe button must declare aria-pressed");
    assert.deepEqual(tf.filter((m) => m[2] === "true").map((m) => m[1]), ["ytd"]);
  });

  test("clicking a timeframe moves aria-pressed to it", () => {
    let src = html.match(/<script type="module">([\s\S]*?)<\/script>/)[1];
    src = src.replace(/^import\s*\{[^}]*\}\s*from\s*["'][^"']*["'];?\s*$/m, "");
    const handlers = {};
    const tfButtons = ["week", "ytd", "12m"].map((tf) => ({
      dataset: { tf },
      attrs: {},
      setAttribute(k, v) {
        this.attrs[k] = v;
      },
      classList: { toggle: noop },
      closest() {
        return this;
      },
    }));
    const box = {
      console,
      fetch: async () => ({ ok: true, json: async () => [] }),
      document: {
        getElementById: (id) => {
          const e = stubEl(id);
          e.addEventListener = (type, fn) => {
            handlers[id + ":" + type] = fn;
          };
          return e;
        },
        querySelectorAll: (sel) => (sel.includes("button[data-tf]") ? tfButtons : []),
        addEventListener: noop,
      },
    };
    box.window = box;
    box.globalThis = box;
    vm.createContext(box);
    try {
      new vm.Script(src, { filename: "trends_inline.js" }).runInContext(box);
    } catch (_e) {}
    // render() needs chart helpers the page imports; stub it out.
    box.render = noop;
    const click = handlers["timeframeBar:click"];
    assert.ok(click, "timeframe bar click handler not wired");
    try {
      click({ target: tfButtons[0] });
    } catch (_e) {}
    assert.deepEqual(tfButtons.map((b) => b.attrs["aria-pressed"]), ["true", "false", "false"]);
  });
});
