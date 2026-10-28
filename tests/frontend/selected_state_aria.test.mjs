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

describe("trends reporter time scope pulldown", () => {
  const INDEX = path.join(ROOT, "financial_trends_reporter", "frontend", "index.html");
  const html = fs.readFileSync(INDEX, "utf8");

  test("markup: one labelled select with every scope, Month is the default, no timeframe buttons", () => {
    assert.match(html, /<label[^>]*>\s*Time scope\s*<select id="scopeSelect"/);
    const sel = html.match(/<select id="scopeSelect"[^>]*>([\s\S]*?)<\/select>/)[1];
    const values = [...sel.matchAll(/<option value="([^"]+)"( selected)?>/g)];
    assert.deepEqual(values.map((m) => m[1]), ["week", "month", "3m", "6m", "ytd", "1y", "all", "custom"]);
    assert.deepEqual(values.filter((m) => m[2]).map((m) => m[1]), ["month"]);
    assert.ok(!html.includes("data-tf="), "old timeframe buttons must be gone");
    assert.match(html, /id="scopeLabel"/);
  });

  // Runs the page's inline module script against stub elements; returns the elements, handlers and storage.
  async function loadPage({ saved = null, throwStorage = false } = {}) {
    let src = html.match(/<script type="module">([\s\S]*?)<\/script>/)[1];
    src = src.replace(/^import\s*{[^}]*}\s*from\s*["'][^"']*["'];?\s*$/mg, "");
    const charts = await import("../../financial_trends_reporter/frontend/charts.js");
    const { initSpendingDock } = await import("../../financial_trends_reporter/frontend/spending_dock.js");
    const moneyViewApi = await import("../../financial_trends_reporter/frontend/money_view.js");
    const els = {}, handlers = {}, store = {};
    if (saved !== null) store.trendsScope_v1 = saved;
    const el = (id) => (els[id] ||= {
      id, innerHTML: "", textContent: "", value: "", style: {}, disabled: false,
      classList: { add: noop, remove: noop, toggle: noop, contains: () => false },
      setAttribute: noop, querySelectorAll: () => [], querySelector: () => null,
      addEventListener: (type, fn) => { handlers[id + ":" + type] = fn; },
    });
    const box = {
      ...charts, ...moneyViewApi, initSpendingDock, console, setTimeout: (fn) => { fn(); return 0; }, clearTimeout: noop, setInterval: () => 0, clearInterval: noop,
      fetch: async () => ({ ok: true, json: async () => [] }),
      localStorage: throwStorage
        ? { getItem() { throw new Error("blocked"); }, setItem() { throw new Error("blocked"); } }
        : { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); } },
      document: { getElementById: el, querySelectorAll: () => [], addEventListener: noop },
      navigator: { sendBeacon: noop }, window: null,
    };
    box.window = box; box.globalThis = box;
    vm.createContext(box);
    try { new vm.Script(src, { filename: "trends_inline.js" }).runInContext(box); } catch (_e) {}
    return { els, handlers, store, el };
  }

  test("first visit defaults to Month and shows the period label", async () => {
    const { els } = await loadPage();
    assert.equal(els.scopeSelect.value, "month");
    assert.match(els.scopeLabel.textContent, /^1 Month · /);
  });

  test("changing the select re-renders (label + chart) and saves the choice", async () => {
    const { els, handlers, store } = await loadPage();
    els.chartNetWorth.innerHTML = "stale";
    els.scopeSelect.value = "6m";
    handlers["scopeSelect:change"]({ target: els.scopeSelect });
    assert.match(els.scopeLabel.textContent, /^6 Months · /);
    assert.notEqual(els.chartNetWorth.innerHTML, "stale", "chart was not re-rendered");
    assert.deepEqual(JSON.parse(store.trendsScope_v1), { scope: "6m", from: "", to: "" });
  });

  test("custom shows the date inputs and saves their values; other scopes hide them", async () => {
    const { els, handlers, store } = await loadPage();
    els.scopeSelect.value = "custom";
    handlers["scopeSelect:change"]({ target: els.scopeSelect });
    assert.notEqual(els.customFrom.style.display, "none");
    els.customFrom.value = "2026-02-01";
    handlers["customFrom:change"]({ target: els.customFrom });
    assert.deepEqual(JSON.parse(store.trendsScope_v1), { scope: "custom", from: "2026-02-01", to: "" });
    assert.match(els.scopeLabel.textContent, /^Custom/);
    els.scopeSelect.value = "ytd";
    handlers["scopeSelect:change"]({ target: els.scopeSelect });
    assert.equal(els.customFrom.style.display, "none");
    assert.equal(els.customTo.style.display, "none");
  });

  test("a saved choice is restored on load, mapping the old keys", async () => {
    const a = await loadPage({ saved: JSON.stringify({ scope: "12m", from: "", to: "" }) });
    assert.equal(a.els.scopeSelect.value, "1y");
    const b = await loadPage({ saved: JSON.stringify({ scope: "custom", from: "2026-02-01", to: "2026-03-01" }) });
    assert.equal(b.els.scopeSelect.value, "custom");
    assert.equal(b.els.customFrom.value, "2026-02-01");
    assert.equal(b.els.customTo.value, "2026-03-01");
  });

  test("blocked localStorage never breaks the page: Month default, change still re-renders", async () => {
    const { els, handlers } = await loadPage({ throwStorage: true });
    assert.equal(els.scopeSelect.value, "month");
    els.scopeSelect.value = "3m";
    handlers["scopeSelect:change"]({ target: els.scopeSelect });
    assert.match(els.scopeLabel.textContent, /^3 Months/);
  });
});
