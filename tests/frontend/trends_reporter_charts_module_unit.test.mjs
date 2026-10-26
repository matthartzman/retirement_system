// Finding QUA-302 (system review 2026-09-07, Wave 6 item W6-11):
// financial_trends_reporter/frontend/charts.js's pure functions -- newly
// extracted from an inline <script> with no module boundary -- exercised
// directly via a real ESM import, without the HTML-regex indirection the
// prior test needed. Covers filterByTimeframe's edge cases (empty input,
// single data point) that the escaping/accessibility test doesn't touch.
import { test, describe } from "node:test";
import assert from "node:assert/strict";
import {
  filterByTimeframe, granularityForTimeframe, aggregateByGranularity, labelForDate,
  lineChartSvg, barChartSvg, escSvg, fmtMoney, niceRange, buildHierarchyRows, detailPopupHtml, categoryListHtml,
  scopeRange, normalizeScope, parseSavedScope, ALL_TIME_START, xAxisLabels, flowBarChartSvg, flowLineChartSvg,
} from "../../financial_trends_reporter/frontend/charts.js";

describe("filterByTimeframe", () => {
  test("an empty row list is returned unchanged for any timeframe", () => {
    assert.deepEqual(filterByTimeframe([], "ytd"), []);
  });

  test("a single data point survives every non-custom timeframe filter", () => {
    const rows = [{ as_of_date: "2026-06-15" }];
    for (const tf of ["week", "month", "quarter", "ytd", "12m", "all"]) {
      assert.equal(filterByTimeframe(rows, tf).length, 1, `timeframe=${tf}`);
    }
  });

  test("ytd keeps only rows from January 1st of the last row's year onward", () => {
    const rows = [
      { as_of_date: "2025-12-20" },
      { as_of_date: "2026-01-15" },
      { as_of_date: "2026-06-01" },
    ];
    const kept = filterByTimeframe(rows, "ytd").map((r) => r.as_of_date);
    assert.deepEqual(kept, ["2026-01-15", "2026-06-01"]);
  });

  test("'all' returns every row (truncation to ALL_TIME_START is the page's job)", () => {
    const rows = [{ as_of_date: "2020-01-01" }, { as_of_date: "2026-06-01" }];
    assert.equal(filterByTimeframe(rows, "all").length, 2);
  });
});

describe("lineChartSvg edge cases", () => {
  test("no points renders the empty-state message, not a broken SVG", () => {
    assert.match(lineChartSvg([], {}), /No data yet/);
  });

  test("every point value null/undefined also renders the empty-state message", () => {
    const svg = lineChartSvg([{ label: "Jan", value: null }, { label: "Feb", value: undefined }], {});
    assert.match(svg, /No data yet/);
  });
});

describe("lineChartSvg axes and hover", () => {
  const points = [
    { label: "01-01", value: 100 },
    { label: "01-02", value: 150 },
    { label: "01-03", value: 90 },
  ];

  test("renders y-axis gridlines with formatted value labels", () => {
    const svg = lineChartSvg(points, {});
    assert.match(svg, /\$150/);
    assert.match(svg, /<line x1="56"/); // gridline anchored at the y-axis
  });

  test("renders x-axis date labels for each point", () => {
    const svg = lineChartSvg(points, {});
    for (const p of points) assert.match(svg, new RegExp(escSvg(p.label)));
  });

  test("renders a hover target with a title tooltip per point", () => {
    const svg = lineChartSvg(points, {});
    assert.match(svg, /<circle[^>]*class="chart-dot"/);
    assert.match(svg, /<title>01-02: \$150<\/title>/);
  });

  test("a point with a null value gets no hover dot", () => {
    const svg = lineChartSvg([{ label: "Jan", value: null }, ...points], {});
    const dotCount = (svg.match(/<circle/g) || []).length;
    assert.equal(dotCount, points.length);
  });
});

describe("barChartSvg edge cases", () => {
  test("no entries renders the empty-state message, not a broken SVG", () => {
    assert.match(barChartSvg([]), /No expenses recorded yet/);
  });
});

describe("barChartSvg axes and hover", () => {
  test("renders an x-axis scale and a hover tooltip per bar", () => {
    const svg = barChartSvg([["Groceries", 500], ["Rent", 2000]]);
    assert.match(svg, /<title>Groceries: \$500<\/title>/);
    assert.match(svg, /<title>Rent: \$2,000<\/title>/);
    assert.match(svg, /\$1,333/); // a tick on the amount scale (0, 667, 1333, 2000)
  });
});

describe("granularityForTimeframe", () => {
  const span = (days) => [{ as_of_date: "2026-01-01" }, { as_of_date: new Date(Date.UTC(2026, 0, 1 + days)).toISOString().slice(0, 10) }];

  test("with unknown/short row history, nominal granularity applies", () => {
    for (const tf of ["week", "month"]) assert.equal(granularityForTimeframe(tf, []), "day");
    assert.equal(granularityForTimeframe("quarter", []), "week");
    for (const tf of ["ytd", "12m", "all"]) assert.equal(granularityForTimeframe(tf, []), "month");
  });

  test("monthly ranges with 4+ months of data stay monthly", () => {
    for (const tf of ["ytd", "12m", "all"]) assert.equal(granularityForTimeframe(tf, span(150)), "month");
  });

  test("monthly ranges with under 4 months of data revert to weekly", () => {
    for (const tf of ["ytd", "12m", "all"]) assert.equal(granularityForTimeframe(tf, span(60)), "week");
  });

  test("and to daily with under 4 weeks of data", () => {
    for (const tf of ["ytd", "12m", "all", "quarter"]) assert.equal(granularityForTimeframe(tf, span(20)), "day");
  });

  test("quarter stays weekly with 4+ weeks of data; week/month stay daily", () => {
    assert.equal(granularityForTimeframe("quarter", span(60)), "week");
    for (const tf of ["week", "month"]) assert.equal(granularityForTimeframe(tf, span(90)), "day");
  });

  test("custom infers granularity from the span of the filtered rows", () => {
    assert.equal(granularityForTimeframe("custom", span(9)), "day");
    assert.equal(granularityForTimeframe("custom", span(59)), "week");
    assert.equal(granularityForTimeframe("custom", span(2000)), "month");
  });
});

describe("aggregateByGranularity", () => {
  test("daily granularity returns rows unchanged", () => {
    const rows = [{ as_of_date: "2026-01-01" }, { as_of_date: "2026-01-02" }];
    assert.equal(aggregateByGranularity(rows, "day"), rows);
  });

  test("weekly granularity keeps the last row of each ISO week", () => {
    const rows = [
      { as_of_date: "2026-01-05", v: 1 }, // Mon, ISO week 2026-W02
      { as_of_date: "2026-01-07", v: 2 }, // Wed, ISO week 2026-W02
      { as_of_date: "2026-01-12", v: 3 }, // Mon, ISO week 2026-W03
    ];
    const kept = aggregateByGranularity(rows, "week");
    assert.deepEqual(kept.map(r => r.v), [2, 3]);
  });

  test("monthly granularity keeps the last row of each calendar month", () => {
    const rows = [
      { as_of_date: "2026-01-05", v: 1 },
      { as_of_date: "2026-01-25", v: 2 },
      { as_of_date: "2026-02-10", v: 3 },
    ];
    const kept = aggregateByGranularity(rows, "month");
    assert.deepEqual(kept.map(r => r.v), [2, 3]);
  });
});

describe("labelForDate (full text for tooltips and the data table)", () => {
  test("day: weekday, month, day, year; week: the Monday it starts; month: month and year", () => {
    assert.equal(labelForDate("2026-03-05", "day"), "Thu, Mar 5, 2026");
    assert.equal(labelForDate("2026-10-26", "day"), "Mon, Oct 26, 2026");
    assert.equal(labelForDate("2026-03-05", "week"), "Week of Mar 2, 2026");
    assert.equal(labelForDate("2026-03-01", "week"), "Week of Feb 23, 2026");
    assert.equal(labelForDate("2026-03-05", "month"), "Mar 2026");
  });
});

describe("escSvg / fmtMoney", () => {
  test("escSvg handles null/undefined without throwing", () => {
    assert.equal(escSvg(null), "");
    assert.equal(escSvg(undefined), "");
  });

  test("fmtMoney handles null/undefined without throwing", () => {
    assert.equal(fmtMoney(null), "-");
    assert.equal(fmtMoney(undefined), "-");
  });
});

describe("niceRange", () => {
  test("does not anchor at zero and brackets the data with round ticks", () => {
    const r = niceRange(4200000, 4260000);
    assert.ok(r.min > 4000000 && r.min <= 4200000, `min=${r.min}`);
    assert.ok(r.max >= 4260000 && r.max < 4500000, `max=${r.max}`);
    assert.ok(r.ticks.length >= 3);
  });

  test("a flat series still yields a non-degenerate range", () => {
    const r = niceRange(100, 100);
    assert.ok(r.min < 100 && r.max > 100);
  });

  test("line chart y-axis labels start near the data, not at $0", () => {
    const svg = lineChartSvg([{ label: "a", value: 4200000 }, { label: "b", value: 4260000 }], {});
    assert.ok(!svg.includes(">$0<"));
  });
});

// ---- fitted line chart (design 2.6): no horizontal scroll, scope-aware x-axis ----
const pad2 = (n) => String(n).padStart(2, "0");
function addDays(start, n) {
  const [y, m, d] = start.split("-").map(Number);
  const t = new Date(Date.UTC(y, m - 1, d + n));
  return t.getUTCFullYear() + "-" + pad2(t.getUTCMonth() + 1) + "-" + pad2(t.getUTCDate());
}
// n consecutive daily points ending on 'end'
function dayPoints(n, end = "2026-10-26") {
  return Array.from({ length: n }, (_, i) => {
    const date = addDays(end, i - (n - 1));
    return { date, label: labelForDate(date, "day"), value: 100 + i };
  });
}
// n weekly points (Fridays) ending on 'end'
function weekPoints(n, end = "2026-10-23") {
  return Array.from({ length: n }, (_, i) => {
    const date = addDays(end, 7 * (i - (n - 1)));
    return { date, label: labelForDate(date, "week"), value: 100 + i };
  });
}
// n monthly points ending on the month of 'endMonth' ("YYYY-MM")
function monthPoints(n, endMonth = "2026-10") {
  const [ey, em] = endMonth.split("-").map(Number);
  return Array.from({ length: n }, (_, i) => {
    const t = ey * 12 + (em - 1) - (n - 1 - i);
    const date = Math.floor(t / 12) + "-" + pad2((t % 12) + 1) + "-28";
    return { date, label: labelForDate(date, "month"), value: 100 + i };
  });
}
const WIDTHS = [320, 480, 560]; // card widths; the plot is the card minus the 56 px / 34 px margins
const plotOf = (w) => w - 56 - 34;

describe("fitted line chart", () => {
  test("no scroll wrappers or pinned y-axis, and the SVG width equals the width passed, for 3..400 points", () => {
    for (const n of [3, 4, 7, 14, 15, 30, 40, 41, 90, 91, 150, 400]) {
      for (const width of [320, 480, 777]) {
        const svg = lineChartSvg(dayPoints(n), { width, granularity: "day" });
        assert.ok(!/chart-scroll|chart-inner|chart-yaxis/.test(svg), "n=" + n);
        assert.equal(Number(svg.match(/<svg viewBox="0 0 ([0-9]+) /)[1]), width, "n=" + n);
        assert.match(svg, new RegExp('<svg viewBox="0 0 ' + width + ' [0-9]+" width="' + width + '"'));
        assert.ok(!/NaN/.test(svg), "n=" + n);
      }
    }
  });

  test("falls back to 560 px when the width is unknown", () => {
    assert.match(lineChartSvg(dayPoints(10), { granularity: "day" }), /<svg viewBox="0 0 560 /);
  });

  test("the y-axis labels are plain SVG text inside the one chart svg", () => {
    const svg = lineChartSvg(dayPoints(5), { width: 480, granularity: "day" });
    assert.equal((svg.match(/<svg /g) || []).length, 1);
    assert.match(svg, /<text x="50" [^>]*text-anchor="end"[^>]*>\$/);
  });

  test("points are spaced evenly across the plot", () => {
    const svg = lineChartSvg(dayPoints(5), { width: 480, granularity: "day" });
    const xs = [...svg.matchAll(/<circle cx="([0-9.]+)"/g)].map((m) => Number(m[1]));
    assert.equal(xs.length, 5);
    assert.equal(xs[0], 56);
    assert.equal(xs[4], 480 - 34);
    const gaps = xs.slice(1).map((x, i) => Math.round((x - xs[i]) * 100) / 100);
    assert.equal(new Set(gaps).size, 1);
  });

  test("dots: r=3 normally, r=2 above 40 points, hidden above 90 with one target per point", () => {
    const dotR = (n) => [...lineChartSvg(dayPoints(n), { width: 480, granularity: "day", interactive: true }).matchAll(/<circle [^>]*>/g)];
    assert.ok(dotR(40).every((m) => m[0].includes('r="3"')));
    assert.ok(dotR(41).every((m) => m[0].includes('r="2"')));
    assert.ok(dotR(90).every((m) => m[0].includes('r="2"') && !m[0].includes("fill-opacity")));
    const hidden = dotR(91);
    assert.equal(hidden.length, 91);
    assert.ok(hidden.every((m) => m[0].includes('fill-opacity="0"') && m[0].includes("chart-dot")));
  });

  test("keyboard/hover markup survives at every density: roving tabindex, data-i, tooltips", () => {
    for (const n of [5, 60, 200]) {
      const svg = lineChartSvg(dayPoints(n), { width: 480, granularity: "day", interactive: true });
      assert.equal((svg.match(/<circle /g) || []).length, n);
      assert.equal((svg.match(/tabindex="0"/g) || []).length, 1);
      assert.match(svg, new RegExp('tabindex="0" data-i="' + (n - 1) + '"'));
      assert.equal((svg.match(/data-i="/g) || []).length, n);
      assert.equal((svg.match(/<title>/g) || []).length, n);
    }
  });

  test("tooltips, aria-labels and the data table keep the FULL date; the axis does not", () => {
    const pts = dayPoints(20);
    const svg = lineChartSvg(pts, { width: 560, granularity: "day", interactive: true });
    const newest = pts[19];
    assert.equal(newest.label, "Mon, Oct 26, 2026");
    assert.ok(svg.includes("<title>Mon, Oct 26, 2026: $119</title>"));
    assert.ok(svg.includes('aria-label="Mon, Oct 26, 2026: $119"'));
    assert.ok(svg.includes("<td>Mon, Oct 26, 2026</td>"));
    const table = svg.indexOf("<table");
    const axisTexts = [...svg.slice(0, table).matchAll(/text-anchor="middle"[^>]*>([^<]*)</g)].map((m) => m[1]);
    assert.ok(axisTexts.includes("Oct 26"));
    assert.ok(!axisTexts.some((t) => t.includes("Mon,")));
  });

  test("a faint vertical tick marks every labelled point", () => {
    const pts = dayPoints(30);
    const svg = lineChartSvg(pts, { width: 560, granularity: "day" });
    const labels = xAxisLabels(pts, { granularity: "day", plotWidth: plotOf(560) });
    assert.equal((svg.match(/class="x-tick"/g) || []).length, labels.length);
  });

  test("points without dates fall back to their label text, still thinned by measurement", () => {
    const pts = Array.from({ length: 40 }, (_, i) => ({ label: "L" + i, value: i }));
    const svg = lineChartSvg(pts, { width: 560 });
    const axis = svg.slice(0, svg.indexOf("<table"));
    assert.ok(axis.includes(">L39<"), "newest label missing");
    assert.ok(!axis.includes(">L38<"), "neighbour of the newest should be dropped as overlapping");
  });
});

describe("xAxisLabels", () => {
  const dow = (date) => {
    const [y, m, d] = date.split("-").map(Number);
    return new Date(Date.UTC(y, m - 1, d)).getUTCDay();
  };
  const noOverlap = (labels) => {
    for (let k = 1; k < labels.length; k++) {
      const gap = labels[k].x - labels[k - 1].x;
      assert.ok(gap >= (labels[k].width + labels[k - 1].width) / 2, "labels " + labels[k - 1].text + " and " + labels[k].text + " overlap");
    }
  };

  test("day: Mondays plus the newest, text like 'Oct 26', no year on the label itself", () => {
    const pts = dayPoints(30);
    const labels = xAxisLabels(pts, { granularity: "day", plotWidth: 470 });
    assert.ok(labels.length >= 3);
    for (const l of labels.slice(0, -1)) assert.equal(dow(pts[l.i].date), 1, "non-Monday labelled: " + pts[l.i].date);
    assert.equal(labels[labels.length - 1].i, 29);
    for (const l of labels) assert.match(l.text, /^[A-Z][a-z][a-z] [0-9]+$/);
  });

  test("day with 14 points or fewer: every day is a candidate and carries a weekday initial", () => {
    const pts = dayPoints(7);
    const labels = xAxisLabels(pts, { granularity: "day", plotWidth: 470 });
    assert.ok(labels.length >= 3);
    for (const l of labels) assert.equal(l.sub, "SMTWTFS"[dow(pts[l.i].date)]);
    const many = xAxisLabels(dayPoints(15), { granularity: "day", plotWidth: 470 });
    assert.ok(many.every((l) => l.sub === ""));
  });

  test("week: week-start dates, first week of each month plus the newest", () => {
    const pts = weekPoints(26);
    const labels = xAxisLabels(pts, { granularity: "week", plotWidth: 470 });
    const monthOfWeekStart = (date) => {
      const [y, m, d] = date.split("-").map(Number);
      const t = new Date(Date.UTC(y, m - 1, d - ((dow(date) + 6) % 7)));
      return t.getUTCFullYear() + "-" + pad2(t.getUTCMonth() + 1);
    };
    const firstOfMonth = new Set();
    const seen = new Set();
    pts.forEach((p, i) => { const k = monthOfWeekStart(p.date); if (!seen.has(k)) { seen.add(k); firstOfMonth.add(i); } });
    assert.ok(labels.length >= 3);
    for (const l of labels.slice(0, -1)) assert.ok(firstOfMonth.has(l.i), "label on a week that is not the first of its month: " + pts[l.i].date);
    assert.equal(labels[labels.length - 1].i, 25);
    // text is the week START (a Monday), not the Friday row date
    assert.equal(labels[labels.length - 1].text, "Oct 19");
  });

  test("month: every month when they fit, quarter starts when they do not", () => {
    const fits = xAxisLabels(monthPoints(12), { granularity: "month", plotWidth: 470 });
    assert.equal(fits.length, 12);
    assert.deepEqual(fits.slice(-3).map((l) => l.text), ["Aug", "Sep", "Oct"]);
    const tight = xAxisLabels(monthPoints(36), { granularity: "month", plotWidth: 470 });
    assert.ok(tight.length < 36);
    for (const l of tight.slice(0, -1)) assert.ok(["Jan", "Apr", "Jul", "Oct"].includes(l.text), l.text);
    assert.equal(tight[tight.length - 1].i, 35);
  });

  test("the newest point is always labelled, for every granularity and width", () => {
    const sets = { day: [3, 7, 20, 31, 90, 400], week: [3, 13, 26, 52], month: [3, 12, 24, 60] };
    const make = { day: dayPoints, week: weekPoints, month: monthPoints };
    for (const gran of Object.keys(sets)) {
      for (const n of sets[gran]) {
        for (const w of WIDTHS) {
          const labels = xAxisLabels(make[gran](n), { granularity: gran, plotWidth: plotOf(w) });
          assert.ok(labels.length >= 1, gran + n);
          assert.equal(labels[labels.length - 1].i, n - 1, gran + " n=" + n + " w=" + w);
        }
      }
    }
  });

  test("no two kept labels overlap at plot widths for 320, 480 and 560 px cards", () => {
    const sets = { day: [7, 14, 21, 31, 90], week: [13, 26, 52], month: [6, 12, 24, 60] };
    const make = { day: dayPoints, week: weekPoints, month: monthPoints };
    for (const gran of Object.keys(sets)) {
      for (const n of sets[gran]) {
        for (const w of WIDTHS) noOverlap(xAxisLabels(make[gran](n), { granularity: gran, plotWidth: plotOf(w) }));
      }
    }
  });

  test("year line: under the first label and wherever the year changes, nowhere else", () => {
    const pts = monthPoints(8, "2026-02"); // Jul 2025 .. Feb 2026
    const labels = xAxisLabels(pts, { granularity: "month", plotWidth: 470 });
    assert.equal(labels.length, 8);
    const withYear = labels.filter((l) => l.year).map((l) => [l.text, l.year]);
    assert.deepEqual(withYear, [["Jul", "2025"], ["Jan", "2026"]]);
    assert.deepEqual(labels.find((l) => l.text === "Jan").lines, ["Jan", "2026"]);
    // a single calendar year: only the first label carries it
    const one = xAxisLabels(monthPoints(6, "2026-10"), { granularity: "month", plotWidth: 470 });
    assert.deepEqual(one.filter((l) => l.year).map((l) => l.year), ["2026"]);
    assert.ok(one[0].year);
    // day labels across New Year
    const days = xAxisLabels(dayPoints(40, "2026-01-15"), { granularity: "day", plotWidth: 470 });
    assert.deepEqual(days.filter((l) => l.year).map((l) => l.year), ["2025", "2026"]);
  });

  test("narrow card (< 420 px plot): day-of-month only, single-letter months, about three labels", () => {
    const days = xAxisLabels(dayPoints(31), { granularity: "day", plotWidth: 300 });
    assert.ok(days.length <= 4 && days.length >= 1);
    for (const l of days) assert.match(l.text, /^[0-9]+$/);
    assert.equal(days[days.length - 1].i, 30);
    const months = xAxisLabels(monthPoints(24), { granularity: "month", plotWidth: 300 });
    assert.ok(months.length <= 4 && months.length >= 1);
    for (const l of months) assert.match(l.text, /^[A-Z]$/);
    assert.ok(months[0].year, "the year line stays on narrow cards");
    assert.equal(months[months.length - 1].i, 23);
    // the page can force it too
    const forced = xAxisLabels(dayPoints(31), { granularity: "day", plotWidth: 470, narrow: true });
    for (const l of forced) assert.match(l.text, /^[0-9]+$/);
  });

  test("an empty list gives no labels", () => {
    assert.deepEqual(xAxisLabels([], { granularity: "day", plotWidth: 400 }), []);
  });
});

describe("responsive bar charts and the flows line", () => {
  test("barChartSvg carries a viewBox and width:100%", () => {
    const svg = barChartSvg([["Groceries", 500], ["Rent", 2000]]);
    assert.match(svg, /<svg viewBox="0 0 [0-9]+ [0-9]+" width="100%"[^>]*style="width:100%/);
  });
  test("flowBarChartSvg carries a viewBox and width:100%", () => {
    const svg = flowBarChartSvg({ rows: [{ name: "IRA", net: -500, toChecking: 0, fromChecking: 500 }], total: -500 });
    assert.match(svg, /<svg viewBox="0 0 [0-9]+ [0-9]+" width="100%"[^>]*style="width:100%/);
  });
  test("flows line uses the fitted chart: month labels with a year line, full month in the table", () => {
    const series = Array.from({ length: 10 }, (_, i) => ({ month: "2026-" + pad2(i + 1), net: i * 10 }));
    const svg = flowLineChartSvg(series, { width: 560 });
    assert.ok(!/chart-scroll|chart-yaxis/.test(svg));
    assert.match(svg, /<svg viewBox="0 0 560 /);
    assert.match(svg, /text-anchor="middle"[^>]*>Jan</);
    assert.match(svg, /text-anchor="middle"[^>]*>2026</);
    assert.match(svg, /<td>Oct 2026<\/td>/);
  });
});

describe("category rows and detail popup", () => {
  const hier = {
    Housing: { Utilities: { "Gas & Electric": { ComEd: 30, Nicor: 20 } }, Mortgage: { Mortgage: { Bank: 100 } } },
    Travel: { Travel: { Trips: { Airline: 40 } } },
  };
  test("level 1 rows are tracking types sorted by amount, with a grand total", () => {
    const m = buildHierarchyRows(hier);
    assert.deepEqual(m.rows.map(r => [r.name, r.amount]), [["Housing", 150], ["Travel", 40]]);
    assert.equal(m.total, 190);
  });

  test("each row lists its categories (across groups) with their merchants", () => {
    const m = buildHierarchyRows(hier);
    const housing = m.rows[0];
    assert.deepEqual(housing.categories.map(c => [c.name, c.value]), [["Mortgage", 100], ["Gas & Electric", 50]]);
    assert.deepEqual(housing.categories[1].merchants, [["ComEd", 30], ["Nicor", 20]]);
  });

  test("category popup tags each row for the merchant step, escapes names, shows the total", () => {
    const m = buildHierarchyRows({ T: { G: { "C<b>": { M: 5 } } } });
    const html = categoryListHtml("T", m.rows[0].categories);
    assert.ok(html.includes("C&lt;b&gt;") && html.includes('data-cat="0"'));
    assert.match(html, /pop-total[^>]*><span>Total<\/span><span>\$5<\/span>/);
  });

  test("lists every category and merchant, with no 'n more' truncation", () => {
    const big = { T: { G: {} } };
    for (let c = 0; c < 30; c++) big.T.G["c" + c] = { m: c + 1 };
    const html = categoryListHtml("T", buildHierarchyRows(big).rows[0].categories);
    assert.equal((html.match(/data-cat=/g) || []).length, 30);
    assert.ok(!html.includes(" more"));
  });

  test("a negative line (refunds & credits) has no bar and the total stays net", () => {
    const m = buildHierarchyRows({ T: { G: { C: { A: 100, "Refunds & credits": -20 } } } });
    assert.equal(m.total, 80);
    assert.ok(detailPopupHtml("C", m.rows[0].categories[0].merchants).includes("pop-neg"));
  });

  test("popup shows the detail bars and a total", () => {
    const html = detailPopupHtml("T", [["x", 30], ["y", 20]]);
    assert.match(html, /pop-total[^>]*><span>Total<\/span><span>\$50<\/span>/);
  });

  test("total and other rows render with data-row hooks", () => {
    const svg = barChartSvg([["Total", 100, { kind: "total" }], ["A", 60, { kind: "category" }], ["Other", 40, { kind: "other" }]]);
    assert.equal((svg.match(/data-row=/g) || []).length, 3);
  });
});

describe("347a: prior-year and budget markers on the Spending bars", () => {
  const tree = { Core: { Food: { Groceries: { Kroger: 100 } } }, Travel: { Trips: { Air: { Delta: 40 } } } };

  test("buildHierarchyRows attaches prior/budget per tracking type and totals them", () => {
    const m = buildHierarchyRows(tree, { Core: 80 }, { Core: 500, Travel: 200 });
    const core = m.rows.find(r => r.name === "Core");
    assert.equal(core.prior, 80);
    assert.equal(core.budget, 500);
    assert.equal(m.rows.find(r => r.name === "Travel").prior, null);
    assert.deepEqual(m.totalMarkers, { prior: 80, budget: 700, fullYear: null });
    // a budgeted type with no spend yet still counts toward the Total budget
    assert.equal(buildHierarchyRows(tree, {}, { Core: 500, Housing: 900 }).totalMarkers.budget, 1400);
  });

  test("entries from older log rows (no marker data) draw no markers or legend", () => {
    const m = buildHierarchyRows(tree);
    assert.deepEqual(m.totalMarkers, { prior: null, budget: null, fullYear: null });
    const svg = barChartSvg(m.rows.map(r => [r.name, r.amount, r]));
    assert.doesNotMatch(svg, /Same period last year|Budget for this period|Full-year budget/);
  });

  test("markers, legend, tooltips and fallback columns appear, and the axis fits the budget", () => {
    const m = buildHierarchyRows(tree, { Core: 80 }, { Core: 500 });
    const svg = barChartSvg(m.rows.map(r => [r.name, r.amount, r]));
    assert.match(svg, /<title>Same period last year: \$80<\/title>/);
    assert.match(svg, /<title>Budget for this period: \$500<\/title>/);
    assert.match(svg, /class="mk-key">.*Same period last year/);
    assert.match(svg, /<th[^>]*>Same period last year<\/th>/);
    assert.match(svg, />\$500</, "axis max reaches the $500 budget");
  });
});

describe("351: budget and prior-year markers match at every level", () => {
  const tree = { Core: { Food: { Groceries: { Kroger: 100, Aldi: 20 } } } };
  const priorDetail = { Core: { Food: { Groceries: { prior: 80, merchants: { Kroger: 70 } } } } };
  const budgetByCat = { Core: { Groceries: 400 } };

  test("the budget marker has the same height as the prior-year marker (351a)", () => {
    const m = buildHierarchyRows(tree, { Core: 80 }, { Core: 500 });
    const svg = barChartSvg(m.rows.map(r => [r.name, r.amount, r]));
    const lines = [...svg.matchAll(/<line class="mk (mk-prior|mk-period)" x1="[\d.]+" y1="([\d.-]+)" x2="[\d.]+" y2="([\d.-]+)"/g)];
    const h = c => Number(lines.find(l => l[1] === c)[3]) - Number(lines.find(l => l[1] === c)[2]);
    assert.equal(h("mk-period"), h("mk-prior"));
  });

  test("category popup rows carry prior and budget markers (351b)", () => {
    const m = buildHierarchyRows(tree, { Core: 80 }, { Core: 500 }, priorDetail, budgetByCat);
    const cat = m.rows[0].categories[0];
    assert.equal(cat.prior, 80);
    assert.equal(cat.budget, 400);
    const html = categoryListHtml("Core", m.rows[0].categories);
    assert.match(html, /pm mk-prior/);
    assert.match(html, /pm mk-period/);
  });

  test("merchant rows show prior-year only where last year had that merchant", () => {
    const m = buildHierarchyRows(tree, { Core: 80 }, { Core: 500 }, priorDetail, budgetByCat);
    const [kroger, aldi] = m.rows[0].categories[0].merchants;
    assert.deepEqual(kroger[2], { prior: 70 });
    assert.deepEqual(aldi[2], { prior: null });
    const html = detailPopupHtml("merchants", m.rows[0].categories[0].merchants);
    assert.equal((html.match(/pm mk-prior/g) || []).length, 1);
    assert.doesNotMatch(html, /mk-period|mk-full/);
  });

  test("the Total popup lists tracking types with their markers", () => {
    const m = buildHierarchyRows(tree, { Core: 80 }, { Core: 500 });
    const html = detailPopupHtml(m.totalDetail.detailTitle, m.totalDetail.detail);
    assert.match(html, /pm mk-prior/);
    assert.match(html, /pm mk-period/);
  });

  test("without detail data (older log rows) popups draw no markers", () => {
    const m = buildHierarchyRows(tree);
    assert.doesNotMatch(categoryListHtml("Core", m.rows[0].categories), /class="pm /);
  });
});

describe("352: All time starts 2025-02-01", () => {
  const mk = (d, nw) => ({ as_of_date: d, source: "monarch", net_worth: { total: nw }, holdings: { current_value: nw } });

  test("truncateAllTime keeps 2025-02-01 onward and nothing earlier", async () => {
    const { truncateAllTime } = await import("../../financial_trends_reporter/frontend/charts.js");
    const rows = [mk("2024-01-10", -360000), mk("2025-01-31", 2008000), mk("2025-02-01", 4174000), mk("2026-10-15", 6570000)];
    const t = truncateAllTime(rows);
    assert.deepEqual(t.rows.map(r => r.as_of_date), ["2025-02-01", "2026-10-15"]);
    assert.equal(t.truncated, true);
  });

  test("nothing is flagged when all rows are on or after the start", async () => {
    const { truncateAllTime } = await import("../../financial_trends_reporter/frontend/charts.js");
    assert.equal(truncateAllTime([mk("2025-03-01", 1)]).truncated, false);
  });

  test("a missing value breaks the line instead of dropping to zero", () => {
    const svg = lineChartSvg([{ label: "a", value: 100 }, { label: "b", value: null }, { label: "c", value: 120 }, { label: "d", value: 130 }]);
    const d = svg.match(/<path d="([^"]+)"/)[1];
    assert.equal((d.match(/M/g) || []).length, 2);
    assert.doesNotMatch(d, /NaN/);
  });
});

describe("scopeRange", () => {
  const R = (scope, anchor, custom) => scopeRange(scope, anchor, custom);
  test("week goes back 7 days, month 1 calendar month, 3m/6m/1y 3/6/12 months", () => {
    assert.equal(R("week", "2026-10-26").from, "2026-10-19");
    assert.equal(R("month", "2026-10-26").from, "2026-09-26");
    assert.equal(R("3m", "2026-10-26").from, "2026-07-26");
    assert.equal(R("6m", "2026-10-26").from, "2026-04-26");
    assert.equal(R("1y", "2026-10-26").from, "2025-10-26");
    for (const s of ["week", "month", "3m", "6m", "1y", "ytd", "all"]) assert.equal(R(s, "2026-10-26").to, "2026-10-26");
  });
  test("month-end anchors clamp to the shorter month", () => {
    assert.equal(R("month", "2026-03-31").from, "2026-02-28");
    assert.equal(R("month", "2028-03-31").from, "2028-02-29");
    assert.equal(R("3m", "2026-05-31").from, "2026-02-28");
    assert.equal(R("6m", "2026-08-31").from, "2026-02-28");
    assert.equal(R("1y", "2028-02-29").from, "2027-02-28");
    assert.equal(R("month", "2026-01-31").from, "2025-12-31");
  });
  test("week crosses month and year boundaries without local-timezone drift", () => {
    assert.equal(R("week", "2026-01-03").from, "2025-12-27");
    assert.equal(R("week", "2026-03-02").from, "2026-02-23");
  });
  test("ytd starts on Jan 1 of the anchor year, including when the anchor is Jan 1", () => {
    assert.equal(R("ytd", "2026-10-26").from, "2026-01-01");
    assert.equal(R("ytd", "2026-01-01").from, "2026-01-01");
  });
  test("all time starts at ALL_TIME_START", () => {
    assert.equal(R("all", "2026-10-26").from, ALL_TIME_START);
  });
  test("custom uses the inputs; either bound may be empty (open-ended)", () => {
    const both = R("custom", "2026-10-26", { from: "2026-02-01", to: "2026-03-15" });
    assert.deepEqual([both.from, both.to], ["2026-02-01", "2026-03-15"]);
    const onlyFrom = R("custom", "2026-10-26", { from: "2026-02-01", to: "" });
    assert.deepEqual([onlyFrom.from, onlyFrom.to], ["2026-02-01", ""]);
    const onlyTo = R("custom", "2026-10-26", { from: "", to: "2026-03-15" });
    assert.deepEqual([onlyTo.from, onlyTo.to], ["", "2026-03-15"]);
    const none = R("custom", "2026-10-26");
    assert.deepEqual([none.from, none.to], ["", ""]);
    assert.match(onlyFrom.label, /^Custom/);
  });
  test("label names the scope and the window", () => {
    assert.equal(R("month", "2026-10-26").label, "1 Month · Sep 26 – Oct 26, 2026");
    assert.equal(R("1y", "2026-10-26").label, "1 Year · Oct 26, 2025 – Oct 26, 2026");
    assert.match(R("week", "2026-10-26").label, /^1 Week · Oct 19 – Oct 26, 2026$/);
    assert.match(R("ytd", "2026-10-26").label, /^YTD · Jan 1 – Oct 26, 2026$/);
    assert.match(R("3m", "2026-10-26").label, /^3 Months/);
    assert.match(R("6m", "2026-10-26").label, /^6 Months/);
    assert.match(R("all", "2026-10-26").label, /^All Time/);
  });
  test("granularity table: day / week / month, custom inferred from its span", () => {
    const g = (s, c) => R(s, "2026-10-26", c).granularity;
    assert.deepEqual(["week", "month"].map((s) => g(s)), ["day", "day"]);
    assert.deepEqual(["3m", "6m"].map((s) => g(s)), ["week", "week"]);
    assert.deepEqual(["ytd", "1y", "all"].map((s) => g(s)), ["month", "month", "month"]);
    assert.equal(g("custom", { from: "2026-10-01", to: "2026-10-10" }), "day");
    assert.equal(g("custom", { from: "2026-09-01", to: "2026-10-20" }), "week");
    assert.equal(g("custom", { from: "2025-01-01", to: "2026-10-20" }), "month");
  });
  test("an invalid anchor falls back to today instead of throwing", () => {
    assert.match(R("month", "").to, /^\d{4}-\d{2}-\d{2}$/);
  });
  test("filterByTimeframe is driven by scopeRange (custom bounds passed in)", () => {
    const rows = ["2026-01-01", "2026-02-01", "2026-03-01"].map((d) => ({ as_of_date: d }));
    assert.equal(filterByTimeframe(rows, "custom", { from: "2026-02-01", to: "" }).length, 2);
    assert.equal(filterByTimeframe(rows, "custom", { from: "", to: "2026-02-01" }).length, 2);
    assert.equal(filterByTimeframe(rows, "month").length, 2);
  });
});

describe("saved scope", () => {
  test("old keys map to the new ones", () => {
    assert.equal(normalizeScope("quarter"), "3m");
    assert.equal(normalizeScope("12m"), "1y");
    assert.equal(normalizeScope("6m"), "6m");
  });
  test("a missing, corrupt or unknown preference falls back to month", () => {
    for (const raw of [null, undefined, "", "not json", "{}", '{"scope":"bogus"}', "42"]) {
      assert.deepEqual(parseSavedScope(raw), { scope: "month", from: "", to: "" }, String(raw));
    }
  });
  test("a saved preference round-trips, mapping old keys and dropping bad dates", () => {
    assert.deepEqual(parseSavedScope('{"scope":"quarter","from":"","to":""}'), { scope: "3m", from: "", to: "" });
    assert.deepEqual(parseSavedScope('{"scope":"custom","from":"2026-02-01","to":"zzz"}'), { scope: "custom", from: "2026-02-01", to: "" });
  });
});
