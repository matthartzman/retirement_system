// #346: the Year-to-date / Last year toggle is a year pull-down listing the years
// present in the imported data; the saved period maps to one selected year.

import { test, describe, beforeEach } from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const dash = loadDashboardSandbox();
const run = (code) => vm.runInContext(code, dash);
const now = new Date().getFullYear();

beforeEach(() => {
  run(`
    ytdActualsPeriod = "ytd";
    ytdData = { summary: { enabled: true, available_years: [${now}, ${now - 1}, ${now - 3}] }, transactions: [] };
    loadYtdStatus = async () => {};
    renderMain = () => {};
  `);
});

const sandbox_set = (load, render) => { dash.__load = load; dash.__render = render; run("loadSpendingDashboard = globalThis.__load; renderMain = globalThis.__render"); };

describe("#346 spending year pull-down", () => {
  test("selectedSpendingYear maps the saved period to a year", () => {
    assert.equal(run("selectedSpendingYear()"), now);
    run(`ytdActualsPeriod = normalizeYtdActualsPeriod("last_year")`);
    assert.equal(run("selectedSpendingYear()"), now - 1);
    run(`ytdActualsPeriod = "${now - 3}"`);
    assert.equal(run("selectedSpendingYear()"), now - 3);
  });

  test("normalize keeps past years, collapses current/future/junk to ytd", () => {
    assert.equal(run(`normalizeYtdActualsPeriod("${now - 2}")`), String(now - 2));
    assert.equal(run(`normalizeYtdActualsPeriod("${now}")`), "ytd");
    assert.equal(run(`normalizeYtdActualsPeriod("${now + 1}")`), "ytd");
    assert.equal(run(`normalizeYtdActualsPeriod("last_year")`), String(now - 1));
    assert.equal(run(`normalizeYtdActualsPeriod("zzz")`), "ytd");
  });

  test("pull-down lists each data year, newest first, current year as year-to-date", () => {
    const html = run(`ytdActualsPeriodToggleHtml("t")`);
    const years = [...html.matchAll(/<option value="(\d{4})"/g)].map((m) => Number(m[1]));
    assert.deepEqual(years, [now, now - 1, now - 3]);
    assert.match(html, new RegExp(`${now} \\(year-to-date\\)`));
    assert.match(html, new RegExp(`${now - 1} \\(full year\\)`));
    assert.doesNotMatch(html, /Last year/);
  });

  test("years come from the loaded transactions even if the server omits available_years", () => {
    run(`ytdData = { summary: { enabled: true }, transactions: [{ Date: "${now - 1}-03-02" }, { Date: "${now - 2}-01-09" }] }`);
    const years = [...run(`ytdActualsPeriodToggleHtml("t")`).matchAll(/<option value="(\d{4})"/g)].map((m) => Number(m[1]));
    assert.deepEqual(years, [now, now - 1, now - 2]);
  });

  test("a legacy saved last_year shows the prior year selected", () => {
    run(`ytdActualsPeriod = normalizeYtdActualsPeriod("last_year")`);
    const html = run(`ytdActualsPeriodToggleHtml("t")`);
    assert.match(html, new RegExp(`value="${now - 1}" selected`));
  });

  test("the server's calendar year wins over the browser clock (new-year boundary)", () => {
    // Server already in the next year: "ytd" means that year and the previous year is a full year.
    run(`ytdData.summary.calendar_year = ${now + 1}; ytdData.summary.available_years = [${now + 1}, ${now}]`);
    assert.equal(run("selectedSpendingYear()"), now + 1);
    const html = run(`ytdActualsPeriodToggleHtml("t")`);
    assert.ok(html.includes(`${now + 1} (year-to-date)`));
    assert.ok(html.includes(`${now} (full year)`));
  });

  test("choosing a year sets the period; choosing the current year returns to ytd", () => {
    run(`setYtdActualsPeriod("${now - 3}")`);
    assert.equal(run("ytdActualsPeriod"), String(now - 3));
    run(`setYtdActualsPeriod("${now}")`);
    assert.equal(run("ytdActualsPeriod"), "ytd");
  });

  test("a year change reloads the loaded spending dashboard once, with no extra render", async () => {
    let loads = 0, renders = 0;
    sandbox_set(() => loads++, () => renders++);
    run(`window.spendingData = { year: ${now} }`);
    run(`setYtdActualsPeriod("${now - 1}")`);
    await new Promise((r) => setTimeout(r, 0));
    assert.deepEqual([loads, renders], [1, 0]);
  });
});
