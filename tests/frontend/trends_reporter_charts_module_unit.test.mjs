// Finding QUA-302 (system review 2026-09-07, Wave 6 item W6-11):
// financial_trends_reporter/frontend/charts.js's pure functions -- newly
// extracted from an inline <script> with no module boundary -- exercised
// directly via a real ESM import, without the HTML-regex indirection the
// prior test needed. Covers filterByTimeframe's edge cases (empty input,
// single data point) that the escaping/accessibility test doesn't touch.
import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { filterByTimeframe, lineChartSvg, barChartSvg, escSvg, fmtMoney } from "../../financial_trends_reporter/frontend/charts.js";

describe("filterByTimeframe", () => {
  test("an empty row list is returned unchanged for any timeframe", () => {
    assert.deepEqual(filterByTimeframe([], "ytd"), []);
  });

  test("a single data point survives every non-custom timeframe filter", () => {
    const rows = [{ as_of_date: "2026-06-15" }];
    for (const tf of ["day", "week", "month", "quarter", "ytd", "12m", "all"]) {
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

describe("barChartSvg edge cases", () => {
  test("no entries renders the empty-state message, not a broken SVG", () => {
    assert.match(barChartSvg([]), /No expenses recorded yet/);
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
