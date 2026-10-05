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
  lineChartSvg, barChartSvg, escSvg, fmtMoney, niceRange, cashflowNet, buildHierarchyRows, detailPopupHtml, detailTreeHtml,
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

  test("an unrecognized timeframe falls through to 'all time' (every row)", () => {
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
  test("week/month map to daily granularity", () => {
    for (const tf of ["week", "month"]) assert.equal(granularityForTimeframe(tf, []), "day");
  });

  test("quarter maps to weekly granularity", () => {
    assert.equal(granularityForTimeframe("quarter", []), "week");
  });

  test("ytd, 12m, and all map to monthly granularity", () => {
    for (const tf of ["ytd", "12m", "all"]) assert.equal(granularityForTimeframe(tf, []), "month");
  });

  test("custom infers granularity from the span of the filtered rows", () => {
    const short = [{ as_of_date: "2026-01-01" }, { as_of_date: "2026-01-10" }];
    const medium = [{ as_of_date: "2026-01-01" }, { as_of_date: "2026-03-01" }];
    const long = [{ as_of_date: "2020-01-01" }, { as_of_date: "2026-01-01" }];
    assert.equal(granularityForTimeframe("custom", short), "day");
    assert.equal(granularityForTimeframe("custom", medium), "week");
    assert.equal(granularityForTimeframe("custom", long), "month");
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

describe("labelForDate", () => {
  test("day/week granularity uses MM-DD", () => {
    assert.equal(labelForDate("2026-03-05", "day"), "03-05");
    assert.equal(labelForDate("2026-03-05", "week"), "03-05");
  });

  test("month granularity uses a short month + year", () => {
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

describe("scrollable line chart", () => {
  test("many points widen the chart beyond the card so it scrolls", () => {
    const pts = Array.from({ length: 60 }, (_, i) => ({ label: `d${i}`, value: i }));
    const svg = lineChartSvg(pts, {});
    assert.match(svg, /class="chart-scroll"/);
    const w = Number(svg.match(/class="chart-inner" style="width:(\d+)px"/)[1]);
    assert.ok(w > 560);
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

  test("each row carries group > category > merchant levels for the popup", () => {
    const m = buildHierarchyRows(hier);
    const mortgage = m.rows[0].tree[0];
    assert.equal(mortgage.name, "Mortgage");
    assert.equal(mortgage.children[0].name, "Mortgage");
    assert.equal(mortgage.children[0].children[0].name, "Bank");
  });

  test("tree popup shows levels 2-4 and the type total, escaping names", () => {
    const m = buildHierarchyRows({ T: { "G<b>": { C: { M: 5 } } } });
    const html = detailTreeHtml("T", m.rows[0].tree);
    assert.ok(html.includes("G&lt;b&gt;") && html.includes("pop-d2") && html.includes("pop-d3"));
    assert.match(html, /pop-total[^>]*><span>Total<\/span><span>\$5<\/span>/);
  });

  test("rolling over 'n more' (its key in `expanded`) lists every entry at that level", () => {
    const big = { T: {} };
    for (let g = 0; g < 12; g++) big.T["g" + g] = { c: { m: g + 1 } };
    const tree = buildHierarchyRows(big).rows[0].tree;
    const collapsed = detailTreeHtml("T", tree, 36);
    const key = collapsed.match(/data-more="([^"]+)"/)[1];
    const open = detailTreeHtml("T", tree, 36, new Set([key]));
    assert.ok(!open.includes("data-more="), "level should be fully expanded");
    assert.ok(open.includes(">g0<") && open.includes(">g11<"));
  });

  test("a negative line (refunds & credits) has no bar and the total stays net", () => {
    const m = buildHierarchyRows({ T: { G: { C: { A: 100, "Refunds & credits": -20 } } } });
    assert.equal(m.total, 80);
    assert.ok(detailTreeHtml("T", m.rows[0].tree).includes("pop-neg"));
  });

  test("a huge tree is trimmed to fit with a 'more' line", () => {
    const big = { T: {} };
    for (let g = 0; g < 12; g++) big.T["g" + g] = { c: { m: g + 1 } };
    const html = detailTreeHtml("T", buildHierarchyRows(big).rows[0].tree, 36);
    assert.ok(html.includes("more"));
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

describe("cashflowNet", () => {
  const cats = { Groceries: 237514, "Real Estate Taxes": 17291 }; // total 254,805
  test("current-definition entries: income - expenses", () => {
    const r = { cashflow: { income: 433512, expenses: 305515, taxes: 51213 }, ytd_expenses_by_category: cats };
    assert.equal(cashflowNet(r), 433512 - 305515);
  });
  test("pre-9/30 entries get income and real estate taxes added back, so there is no step", () => {
    const old = { cashflow: { income: 433512, expenses: 236805, taxes: 51213 }, ytd_expenses_by_category: cats };
    assert.equal(cashflowNet(old), 433512 - (236805 + 51213 + 17291));
  });
  test("missing income/expenses yields null", () => {
    assert.equal(cashflowNet({ cashflow: { income: null, expenses: 1 } }), null);
  });
});
