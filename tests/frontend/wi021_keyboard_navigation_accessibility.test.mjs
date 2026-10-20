// WI-021 (UX-003, UX-008, UX-009, UX-012): keyboard and navigation accessibility.
//  - the field help badge is a real <button> (Tab reaches it, Enter/Space activate it natively)
//    and the document-level handler never swallows Tab/Space/Enter on it
//  - Back/Forward/navigateTo go through the same unsaved guard as the left nav (UX-009, confirmed
//    in a browser first: Back and window.setStep left an edited autosave page without saving it)
//  - a page change updates document.title, the polite live region and moves focus to the heading
//  - each report chart carries a plain-language summary tied to the SVG, and a keyboard Expand button
import { test, describe } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const JS = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "frontend", "js");
const noop = () => {};

describe("field help badge (UX-003)", () => {
  test("renders a native button with an accessible name, no tabindex and no key handler needed", () => {
    const sb = loadDashboardSandbox();
    const html = sb.fieldTooltipHtml("", { label: "birth_year", schema: { description: "Four-digit birth year." }, notes: "" });
    assert.match(html, /^<button type="button" class="field-info-i"/);
    assert.match(html, /aria-label="More info: /);
    assert.match(html, /aria-controls="helpPanel"/);
    assert.doesNotMatch(html, /<sup|tabindex/);
  });

  test("the Enter-advance handler leaves the badge (a button) alone for Enter, Space and Tab", () => {
    const sb = loadDashboardSandbox();
    sb.window.RetirementNavigation = { focusableEntries: () => [] };
    const badge = {
      matches: (sel) => sel.split(",").map((x) => x.trim()).includes("button"),
      classList: { contains: () => false },
      closest: () => null,
    };
    for (const key of ["Enter", " ", "Tab"]) {
      let prevented = false;
      sb.moveToNextEntry({ key, target: badge, shiftKey: false, defaultPrevented: false, preventDefault: () => (prevented = true) });
      assert.equal(prevented, false, `${JSON.stringify(key)} on the badge must stay native`);
    }
  });
});

function loadNavigation({ activeStep = "household_people", unsaved = false, saveResult = true, choice = "stay" } = {}) {
  const log = [];
  const live = { textContent: "" };
  const heading = { attrs: {}, focused: 0, setAttribute(k, v) { this.attrs[k] = v; }, focus() { this.focused++; } };
  const sandbox = {
    console,
    setTimeout: (fn) => (fn(), 0),
    clearTimeout: noop,
    localStorage: { getItem: () => null, setItem: noop, removeItem: noop },
    document: {
      title: "Retirement Planner",
      getElementById: (id) => (id === "navAnnouncer" ? live : null),
      querySelector: (sel) => (sel === "#mainPane h2, #mainPane h1" ? heading : null),
      querySelectorAll: () => [],
      addEventListener: noop,
    },
    scrollTo: noop,
  };
  sandbox.window = sandbox;
  sandbox.globalThis = sandbox;
  sandbox.stepTitleById = (id) => ({ household_people: "Household & People", estate: "Estate", holdings: "Holdings" })[id] || id;
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(path.join(JS, "navigation.js"), "utf8"), sandbox, { filename: "navigation.js" });
  const nav = sandbox.window.RetirementNavigation;
  const state = { active: activeStep, unsaved };
  const ctx = {
    getPlanLoaded: () => true,
    getActiveStep: () => state.active,
    setActiveStep: (id) => { state.active = id; log.push("set:" + id); },
    renderMain: noop,
    setSearchText: noop,
    setNavSearchText: noop,
    focusableEntries: () => [],
    hasUnsavedPlanChanges: () => state.unsaved,
    saveWorkingCopy: async () => { log.push("save"); return saveResult; },
    saveAll: async () => { log.push("saveAll"); return true; },
    confirmSaveDiscardStay: async () => { log.push("confirm"); return choice; },
    showMessage: (m) => log.push("msg:" + m),
  };
  ctx.setStep = (id) => nav.setStep(ctx, id);
  return { sandbox, nav, ctx, state, log, live, heading };
}

describe("one navigation guard for Back/Forward and jump links (UX-009)", () => {
  test("Back from an edited autosave page saves first, then navigates", async () => {
    const t = loadNavigation({ unsaved: true });
    t.nav.wireStepNavigation(t.ctx);
    t.ctx.setStep("estate");
    t.state.active = "household_people"; // user is on a data-entry page with an edit
    t.log.length = 0;
    await t.sandbox.navigateHistoryBack();
    assert.deepEqual(t.log.slice(0, 3), ["save", "msg:Auto-saved.", "set:household_people"].slice(0, 3));
    assert.equal(t.state.active, "household_people");
  });

  test("a failed autosave keeps the user on the page and does not move the history index", async () => {
    const t = loadNavigation({ unsaved: true, saveResult: false });
    t.nav.wireStepNavigation(t.ctx);
    t.ctx.setStep("estate");
    t.state.active = "estate";
    t.log.length = 0;
    const ok = await t.sandbox.navigateHistoryBack();
    assert.equal(ok, false);
    assert.ok(!t.log.some((e) => e.startsWith("set:")), "must not navigate when the save failed");
    // Back is still available (index unchanged), and works once the save succeeds
    t.state.unsaved = false;
    await t.sandbox.navigateHistoryBack();
    assert.ok(t.log.includes("set:household_people"));
  });

  test("navigateTo from an explicit-save page with unsaved edits asks Save/Discard/Stay; Stay stays", async () => {
    const t = loadNavigation({ activeStep: "strategy_scenarios", unsaved: true, choice: "stay" });
    t.nav.wireStepNavigation(t.ctx);
    const ok = await t.sandbox.navigateTo("household_people");
    assert.equal(ok, false);
    assert.ok(t.log.includes("confirm"));
    assert.ok(!t.log.some((e) => e.startsWith("set:")));
  });

  test("navigateTo with Discard navigates; with Save it saves then navigates", async () => {
    let t = loadNavigation({ activeStep: "strategy_scenarios", unsaved: true, choice: "discard" });
    t.nav.wireStepNavigation(t.ctx);
    assert.equal(await t.sandbox.navigateTo("household_people"), true);
    assert.ok(t.log.includes("set:household_people"));
    t = loadNavigation({ activeStep: "strategy_scenarios", unsaved: true, choice: "save" });
    t.nav.wireStepNavigation(t.ctx);
    assert.equal(await t.sandbox.navigateTo("household_people"), true);
    assert.ok(t.log.indexOf("saveAll") < t.log.indexOf("set:household_people"));
  });

  test("nothing unsaved: navigateTo and Back navigate at once with no save and no toast", async () => {
    const t = loadNavigation({ unsaved: false });
    t.nav.wireStepNavigation(t.ctx);
    t.log.length = 0;
    assert.equal(await t.sandbox.navigateTo("estate"), true);
    assert.deepEqual(t.log, ["set:estate"]);
  });

  test("window.setStep stays the raw, unguarded router (internal callers such as save validation use it)", async () => {
    const t = loadNavigation({ unsaved: true });
    t.nav.wireStepNavigation(t.ctx);
    t.log.length = 0;
    t.sandbox.setStep("estate");
    assert.deepEqual(t.log, ["set:estate"]);
  });
});

describe("page changes are announced and focus lands on the heading (UX-008)", () => {
  test("title, live region and heading focus after navigation", () => {
    const t = loadNavigation({ unsaved: false });
    t.nav.wireStepNavigation(t.ctx);
    t.ctx.setStep("holdings");
    assert.equal(t.sandbox.document.title, "Holdings - Retirement Planner");
    assert.equal(t.live.textContent, "Now on Holdings");
    assert.equal(t.heading.attrs.tabindex, "-1");
    assert.equal(t.heading.focused, 1);
  });
});

describe("report chart summaries (UX-012)", () => {
  function loadReports() {
    const sandbox = { console, esc: (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;") };
    sandbox.window = sandbox;
    vm.createContext(sandbox);
    vm.runInContext(fs.readFileSync(path.join(JS, "reports_ui.js"), "utf8"), sandbox, { filename: "reports_ui.js" });
    return sandbox.window.RetirementReportsUI;
  }
  const line = { type: "line", title: "Net worth over time", x: [2030, 2031, 2032], series: [{ label: "Net worth", values: [100000, 120000, 150000] }] };
  const pie = { type: "pie", title: "Asset mix", slices: [{ label: "Stocks", value: 60 }, { label: "Bonds", value: 40 }] };

  test("summaries describe the data, not just the title", () => {
    const ui = loadReports();
    const s = ui.detailChartSummary(line);
    assert.match(s, /Line chart of 3 periods from 2030 to 2032/);
    assert.match(s, /Net worth: \$100K to \$150K \(low \$100K, high \$150K\)/);
    assert.match(ui.detailChartSummary(pie), /Pie chart with 2 slices: Stocks 60%, Bonds 40%/);
    assert.match(ui.detailChartSummary({ type: "stacked_bar", x: [1, 2], series: [{ label: "A", values: [1000, 2000] }, { label: "B", values: [3000, 4000] }] }), /Bar chart of 2 periods.*2 series \(A, B\)/);
    assert.match(ui.detailChartSummary({ type: "line", x: [], series: [] }), /no data/);
  });

  test("the card ties the summary to the SVG and offers a keyboard Expand button", () => {
    const ui = loadReports();
    const html = ui.renderDetailChartCard({ cacheChart: () => "c9" }, line);
    const m = /<svg aria-describedby="(chart-sum-\d+)"/.exec(html);
    assert.ok(m, "svg must carry aria-describedby");
    assert.match(html, new RegExp(`<p class="sr-only" id="${m[1]}">Line chart of 3 periods`));
    assert.match(html, /<button class="chart-expand-hint" type="button" aria-label="Expand chart: Net worth over time"/);
    assert.match(html, /event\.stopPropagation\(\);openCachedChart\('c9'\)/);
  });
});
