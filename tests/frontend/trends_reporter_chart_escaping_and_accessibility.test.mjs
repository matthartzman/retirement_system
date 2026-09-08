// Finding UX-102 / UX-106 (system review 2026-09-07, Wave 5 item W5-6):
// financial_trends_reporter/frontend/index.html interpolated category names
// and date labels directly into SVG strings (then set via innerHTML) with
// no escaping -- a real injection bug wearing an accessibility finding's
// ID, not merely cosmetic: a Monarch category containing "&" or "<" broke
// the chart, and a chosen category name could inject arbitrary markup.
// Charts also had no role="img"/label/data-table fallback, and a failed
// history fetch or run showed the same "no data yet" empty state as a
// household with genuinely no history.
//
// Finding QUA-302 (Wave 6 item W6-11): the chart-rendering functions this
// file tests (barChartSvg/lineChartSvg/...) used to live inline in
// index.html's <script> block with no module boundary, so this file used to
// regex-extract that whole block and vm-execute it. They now live in
// ./charts.js as a real ES module -- imported directly below, a strictly
// stronger test than the extraction it replaces. The remaining inline
// <script type="module"> (render/loadHistory/error-handling/event wiring)
// still can't be imported directly (it self-invokes loadHistory() and wires
// DOM event listeners at module-evaluation time), so that half continues to
// use the vm-sandbox extraction, with charts.js's real exports pre-populated
// into the sandbox in place of the page's own `import` statement (which a
// classic, non-module vm.Script can't parse).
import { test, describe } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import * as charts from "../../financial_trends_reporter/frontend/charts.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const INDEX_HTML_PATH = path.join(
  __dirname, "..", "..", "financial_trends_reporter", "frontend", "index.html",
);

function extractInlineScript(html) {
  const match = html.match(/<script type="module">([\s\S]*?)<\/script>/);
  if (!match) throw new Error("could not find the page's inline <script type=\"module\"> block");
  return match[1];
}

function loadPageSandbox() {
  const html = fs.readFileSync(INDEX_HTML_PATH, "utf8");
  let src = extractInlineScript(html);
  // The real import is exercised directly via the top-level `charts` import
  // above; strip the statement itself so a classic (non-module) vm.Script
  // can parse the rest, and pre-populate the sandbox with the same real
  // functions in its place.
  src = src.replace(/^import\s*\{[^}]*\}\s*from\s*["'][^"']*["'];?\s*$/m, "");

  const elements = new Map();
  function makeStubElement(id) {
    return {
      id,
      _innerHTML: "",
      style: {},
      disabled: false,
      textContent: "",
      get innerHTML() {
        return this._innerHTML;
      },
      set innerHTML(v) {
        this._innerHTML = v;
      },
      value: "",
      addEventListener() {},
      classList: { toggle() {} },
    };
  }
  const CHART_IDS = ["chartNetWorth", "chartHoldings", "chartCashflow", "chartCategories"];
  const OTHER_IDS = ["timeframeBar", "customFrom", "customTo", "runNow"];
  for (const id of [...CHART_IDS, ...OTHER_IDS]) elements.set(id, makeStubElement(id));

  const documentStub = {
    getElementById: (id) => elements.get(id) || makeStubElement(id),
    querySelectorAll: () => [],
    addEventListener() {},
  };

  let fetchImpl = async () => ({ ok: true, json: async () => [] });

  const sandbox = {
    ...charts,
    document: documentStub,
    fetch: (...args) => fetchImpl(...args),
    console,
  };
  sandbox.globalThis = sandbox;
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  try {
    new vm.Script(src, { filename: "trends_reporter_inline.js" }).runInContext(sandbox);
  } catch (e) {
    // loadHistory() self-invokes at the bottom of the script and will throw
    // against this stub's synchronous-only fetch/Promise plumbing in some
    // Node versions -- every function declaration above it is already
    // hoisted onto the sandbox by that point regardless.
  }

  return {
    sandbox,
    elements,
    setFetchImpl: (fn) => { fetchImpl = fn; },
  };
}

describe("barChartSvg escapes category names", () => {
  test("a category name containing HTML/SVG-special characters is escaped, not injected", () => {
    const svg = charts.barChartSvg([["R&D <script>", 1234.5]]);
    assert.ok(!svg.includes("<script>"), "raw <script> tag leaked into chart markup");
    assert.ok(svg.includes("R&amp;D &lt;script&gt;"), "escaped category name not found");
  });

  test("bar chart declares role=img with a label, and includes a data-table fallback", () => {
    const svg = charts.barChartSvg([["Groceries", 500]]);
    assert.ok(svg.includes('role="img"'), "missing role=img");
    assert.ok(svg.includes("aria-label="), "missing aria-label");
    assert.ok(svg.includes("<table"), "missing data-table fallback");
    assert.ok(svg.includes("Groceries"), "fallback table missing the category name");
  });
});

describe("lineChartSvg escapes labels", () => {
  test("a label containing HTML/SVG-special characters is escaped, not injected", () => {
    const svg = charts.lineChartSvg(
      [{ label: '"><img src=x onerror=alert(1)>', value: 100 }],
      { title: "Test" },
    );
    assert.ok(!svg.includes("<img src=x"), "raw markup leaked into chart via a label");
  });

  test("line chart declares role=img with a label, and includes a data-table fallback", () => {
    const svg = charts.lineChartSvg([{ label: "Jan", value: 100 }], { title: "Net worth" });
    assert.ok(svg.includes('role="img"'), "missing role=img");
    assert.ok(svg.includes("aria-label="), "missing aria-label");
    assert.ok(svg.includes("<table"), "missing data-table fallback");
  });
});

describe("failed history fetch/run surfaces a distinct error state", () => {
  test("loadHistory() renders an error, not the empty-history message, on a failed fetch", async () => {
    const { sandbox, elements, setFetchImpl } = loadPageSandbox();
    setFetchImpl(async () => { throw new Error("network down"); });
    await sandbox.loadHistory();
    const shown = elements.get("chartNetWorth").innerHTML;
    assert.ok(shown.includes("error"), `expected an error state, got: ${shown}`);
    assert.ok(!shown.includes("No data yet"), "a fetch failure must not read as an empty history");
  });

  test("loadHistory() renders an error on a non-ok HTTP response", async () => {
    const { sandbox, elements, setFetchImpl } = loadPageSandbox();
    setFetchImpl(async () => ({ ok: false, status: 500, json: async () => [] }));
    await sandbox.loadHistory();
    const shown = elements.get("chartHoldings").innerHTML;
    assert.ok(shown.includes("error"), `expected an error state, got: ${shown}`);
  });
});
