// Trends Phase 5 (design §2.5): the Spending card follows the time scope and draws three
// markers -- same period last year, budget for this period, full-year budget.
import { test, describe } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  buildHierarchyRows, barChartSvg, categoryListHtml, detailPopupHtml, SPEND_MARKERS, BAR_BLUE, OUTLINE_PX,
  spendingModelFromWindow, spendingModelFromSnapshot, spendingUrl, latestOnly, spendingNoteText, fullYearNudge,
} from "../../financial_trends_reporter/frontend/charts.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const html = fs.readFileSync(path.join(HERE, "..", "..", "financial_trends_reporter", "frontend", "index.html"), "utf8");

const tree = { Core: { Food: { Groceries: { Kroger: 100, Aldi: 20 } } }, Travel: { Trips: { Air: { Delta: 40 } } } };
const priorDetail = { Core: { Food: { Groceries: { prior: 80, merchants: { Kroger: 70 } } } } };
const args = [tree, { Core: 80 }, { Core: 50, Travel: 10 }, priorDetail, { Core: { Groceries: 45 } },
  { Core: 600, Travel: 120 }, { Core: { Groceries: 540 } }];

describe("buildHierarchyRows: three markers", () => {
  test("each row and category carries prior, budget and fullYear", () => {
    const m = buildHierarchyRows(...args);
    const core = m.rows.find(r => r.name === "Core");
    assert.deepEqual([core.prior, core.budget, core.fullYear], [80, 50, 600]);
    const cat = core.categories[0];
    assert.deepEqual([cat.prior, cat.budget, cat.fullYear], [80, 45, 540]);
    const travel = m.rows.find(r => r.name === "Travel");
    assert.deepEqual([travel.prior, travel.budget, travel.fullYear], [null, 10, 120]);
  });
  test("the Total row sums all three", () => {
    const m = buildHierarchyRows(...args);
    assert.deepEqual(m.totalMarkers, { prior: 80, budget: 60, fullYear: 720 });
    const core = m.totalDetail.detail.find(d => d[0] === "Core");
    assert.deepEqual(core[2], { prior: 80, budget: 50, fullYear: 600 });
  });
  test("the five-argument form still works (fullYear null)", () => {
    const m = buildHierarchyRows(tree, { Core: 80 }, { Core: 500 });
    assert.equal(m.rows[0].fullYear, null);
    assert.equal(m.totalMarkers.fullYear, null);
  });
});

describe("markers render on the bars and in both popups with distinct classes", () => {
  const m = buildHierarchyRows(...args);
  const svg = barChartSvg(m.rows.map(r => [r.name, r.amount, r]));
  test("bars draw all three, each with its own class, colour variable, width and dash", () => {
    for (const mk of SPEND_MARKERS) {
      const re = new RegExp(`<line class="mk ${mk.cls}"[^>]*style="stroke:var\\(${mk.cssVar}, ${mk.light}\\);stroke-width:${mk.width}px${mk.dash ? `;stroke-dasharray:${mk.dash}` : ""}"`);
      assert.match(svg, re, mk.key);
    }
    assert.match(svg, /<title>Same period last year: \$80<\/title>/);
    assert.match(svg, /<title>Budget for this period: \$50<\/title>/);
    assert.match(svg, /<title>Full-year budget: \$600<\/title>/);
    assert.match(svg, /fill="#2563eb"/);
  });
  test("legend lists all three with a swatch in each marker's shape", () => {
    const legend = svg.slice(0, svg.indexOf("<svg viewBox=\"0 0 560"));
    const keys = [...legend.matchAll(/class="mk-key"><svg[^>]*><line class="(mk-[a-z]+)"[^>]*style="([^"]+)"\/><\/svg> ([^<]+)<\/span>/g)];
    assert.deepEqual(keys.map(k => k[3]), ["Same period last year", "Budget for this period", "Full-year budget"]);
    assert.match(keys[2][2], /stroke-dasharray:3 2/);
    assert.match(keys[1][2], /stroke-width:3.5px/);
  });
  test("the no-JS table has a column per marker with the new headings", () => {
    for (const h of ["Same period last year", "Budget for this period", "Full-year budget"]) assert.match(svg, new RegExp(`<th[^>]*>${h}</th>`));
    assert.doesNotMatch(svg, /Prior-year YTD/);
  });
  test("the axis fits the full-year budget", () => {
    assert.match(svg, />\$600</);
  });
  test("category popup draws all three; merchant popup only the prior; Total popup all three", () => {
    const cats = categoryListHtml("Core", m.rows.find(r => r.name === "Core").categories);
    for (const cls of ["mk-prior", "mk-period", "mk-full"]) assert.match(cats, new RegExp(`class="pm ${cls}"`));
    const merchants = detailPopupHtml("m", m.rows.find(r => r.name === "Core").categories[0].merchants);
    assert.match(merchants, /pm mk-prior/);
    assert.doesNotMatch(merchants, /mk-period|mk-full/);
    const total = detailPopupHtml(m.totalDetail.detailTitle, m.totalDetail.detail);
    for (const cls of ["mk-prior", "mk-period", "mk-full"]) assert.match(total, new RegExp(`class="pm ${cls}"`));
  });
  test("prorated and full-year within 1% draw separately, 1px apart", () => {
    assert.equal(fullYearNudge({ budget: 1000, fullYear: 1005 }), 1);
    assert.equal(fullYearNudge({ budget: 1000, fullYear: 1100 }), 0);
    assert.equal(fullYearNudge({ budget: null, fullYear: 1000 }), 0);
    const one = buildHierarchyRows(tree, null, { Core: 1000 }, null, null, { Core: 1000 });
    const s = barChartSvg(one.rows.map(r => [r.name, r.amount, r]));
    const x = cls => Number(s.match(new RegExp(`class="mk ${cls}" x1="([\\d.]+)"`))[1]);
    assert.equal(x("mk-full") - x("mk-period"), 1);
    const pop = detailPopupHtml("t", [["Core", 120, { budget: 1000, fullYear: 1000 }]]);
    assert.match(pop, /class="pm mk-full" style="left:calc\(100\.0% \+ 1px\)"/);
  });
});

// WCAG 2.x relative luminance and contrast ratio.
function luminance(hex) {
  const [r, g, b] = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map(c => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
function contrast(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}
const CARD_BG = { light: "#ffffff", dark: "#1e2126" };

describe("marker palette", () => {
  test("the contrast helper matches known WCAG values", () => {
    assert.equal(contrast("#000000", "#ffffff").toFixed(1), "21.0");
    assert.equal(contrast("#777777", "#ffffff").toFixed(2), "4.48");
  });
  test("all six colour values are distinct", () => {
    const all = SPEND_MARKERS.flatMap(m => [m.light.toLowerCase(), m.dark.toLowerCase()]);
    assert.equal(new Set(all).size, 6);
  });
  // A tick is drawn on a card-coloured outline, so what the eye measures is the tick against that outline
  // (the card colour) and the outline against the bar blue -- not the tick directly against the blue.
  for (const theme of ["light", "dark"]) {
    test(`every ${theme} marker is at least 3:1 against its card-coloured outline, and the outline against the bar blue`, () => {
      assert.ok(contrast(CARD_BG[theme], BAR_BLUE) >= 3, `${theme} outline vs blue: ${contrast(CARD_BG[theme], BAR_BLUE).toFixed(2)}`);
      for (const m of SPEND_MARKERS) {
        assert.ok(contrast(m[theme], CARD_BG[theme]) >= 3, `${m.key} ${m[theme]} vs outline/card: ${contrast(m[theme], CARD_BG[theme]).toFixed(2)}`);
      }
    });
  }
  test("dark-mode markers also clear 3:1 against the bar blue directly", () => {
    for (const m of SPEND_MARKERS) assert.ok(contrast(m.dark, BAR_BLUE) >= 3, `${m.key} ${m.dark}`);
  });
  test("light-mode orange and magenta are the visible design colours", () => {
    const by = Object.fromEntries(SPEND_MARKERS.map(m => [m.key, m.light.toLowerCase()]));
    assert.equal(by.budget, "#ea580c");
    assert.equal(by.fullYear, "#c026d3");
  });
  test("every bar tick is drawn on an outline of the card colour, one px wider each side, with the same dash", () => {
    const meta = { kind: "category", prior: 100, budget: 200, fullYear: 300 };
    const svg = barChartSvg([["Housing", 150, meta]]);
    const outlines = [...svg.matchAll(/<line class="mk-outline"[^>]*style="([^"]*)"/g)].map(m => m[1]);
    assert.equal(outlines.length, 3);
    for (const [i, m] of SPEND_MARKERS.entries()) {
      assert.match(outlines[i], /stroke:var\(--card-bg, #fff\)/);
      assert.match(outlines[i], new RegExp(`stroke-width:${m.width + 2 * OUTLINE_PX}px`));
      assert.equal(/stroke-dasharray/.test(outlines[i]), !!m.dash);
    }
    assert.ok(svg.indexOf('class="mk-outline"') < svg.indexOf('class="mk mk-prior"'), "outline is drawn before the tick");
  });
  test("popup ticks carry a card-coloured outline in the page CSS", () => {
    assert.match(html, /\.pop-bar \.pm \{[^}]*box-shadow: 0 0 0 1px var\(--card-bg\)/);
  });
  test("the bars stay blue #2563eb", () => assert.equal(BAR_BLUE, "#2563eb"));
  test("index.html defines the three CSS variables with these values, dark overrides included", () => {
    for (const m of SPEND_MARKERS) {
      assert.match(html, new RegExp(`${m.cssVar}:\\s*${m.light}`), `${m.cssVar} light`);
      assert.match(html, new RegExp(`prefers-color-scheme: dark\\)[^\\n]*${m.cssVar}:\\s*${m.dark}`), `${m.cssVar} dark`);
    }
    assert.doesNotMatch(html, /\.pm-prior|\.pm-budget|#475569/);
  });
});

describe("page wiring", () => {
  const resp = {
    window: { from: "2026-09-26", to: "2026-10-26", days: 31 },
    hierarchy: tree,
    prior: { window: { from: "2025-09-26", to: "2025-10-26" }, by_type: { Core: 80 }, detail: priorDetail },
    budget: { by_type: { Core: 50 }, by_category: { Core: { Groceries: 45 } } },
    full_year_budget: { year: 2026, by_type: { Core: 600 }, by_category: { Core: { Groceries: 540 } } },
  };
  test("spendingUrl encodes the range", () => {
    assert.equal(spendingUrl({ from: "2026-01-01", to: "2026-10-26" }), "/api/spending?from=2026-01-01&to=2026-10-26");
  });
  test("an /api/spending response maps onto buildHierarchyRows", () => {
    const m = spendingModelFromWindow(resp);
    assert.deepEqual(m.totalMarkers, { prior: 80, budget: 50, fullYear: 600 });
    const noPrior = spendingModelFromWindow({ ...resp, prior: null });
    assert.equal(noPrior.totalMarkers.prior, null);
    assert.equal(noPrior.rows[0].categories[0].prior, null);
  });
  test("the snapshot fallback shows prior-year YTD and the full-year budget", () => {
    const latest = { ytd_expense_hierarchy: tree, ytd_expense_prior_year: { Core: 80 }, ytd_expense_prior_detail: priorDetail,
      annual_budget_by_tracking_type: { Core: 600 }, annual_budget_by_category: { Core: { Groceries: 540 } } };
    const m = spendingModelFromSnapshot(latest);
    assert.deepEqual(m.totalMarkers, { prior: 80, budget: null, fullYear: 600 });
    assert.equal(spendingModelFromSnapshot({}), null);
  });
  test("latestOnly drops out-of-order responses", () => {
    const seq = latestOnly();
    const a = seq.start(), b = seq.start();
    assert.equal(seq.isCurrent(a), false);
    assert.equal(seq.isCurrent(b), true);
  });
  test("the note describes the period's markers", () => {
    const note = spendingNoteText(resp, "1 Month · Sep 26 – Oct 26, 2026");
    assert.match(note, /^Totals follow the Spending Analysis mapping and include taxes\. Markers/);
    assert.match(note, /Sep 26, 2025 – Oct 26, 2025/);
    assert.match(note, /prorated to these 31 days/);
    assert.match(note, /whole 2026 annual budget/);
    assert.match(spendingNoteText({ ...resp, prior: null }, "x"), /falls before the first imported transactions/);
  });
  test("the page fetches the window, shows Loading in-card, guards order and falls back with a note", () => {
    assert.match(html, /spendingUrl\(/);
    assert.match(html, /Loading…/);
    assert.match(html, /spendingSeq\.isCurrent\(/);
    assert.match(html, /Showing year-to-date figures; couldn't load this period\./);
    assert.match(html, /spendingModelFromSnapshot\(latest\)/);
    assert.match(html, /id="spendingPeriod"/);
    assert.match(html, /<h2>Spending<\/h2>/);
  });
});
