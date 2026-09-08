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
// This extracts and runs the page's own inline <script> block (not a
// hand-copied fixture) in a Node vm with a minimal DOM stub, so it exercises
// the real shipped source.
import { test, describe } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const INDEX_HTML_PATH = path.join(
  __dirname, "..", "..", "financial_trends_reporter", "frontend", "index.html",
);

function extractInlineScript(html) {
  const match = html.match(/<script>([\s\S]*?)<\/script>/);
  if (!match) throw new Error("could not find the page's inline <script> block");
  return match[1];
}

function loadPageSandbox() {
  const html = fs.readFileSync(INDEX_HTML_PATH, "utf8");
  const src = extractInlineScript(html);

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
    const { sandbox } = loadPageSandbox();
    const svg = sandbox.barChartSvg([["R&D <script>", 1234.5]]);
    assert.ok(!svg.includes("<script>"), "raw <script> tag leaked into chart markup");
    assert.ok(svg.includes("R&amp;D &lt;script&gt;"), "escaped category name not found");
  });

  test("bar chart declares role=img with a label, and includes a data-table fallback", () => {
    const { sandbox } = loadPageSandbox();
    const svg = sandbox.barChartSvg([["Groceries", 500]]);
    assert.ok(svg.includes('role="img"'), "missing role=img");
    assert.ok(svg.includes("aria-label="), "missing aria-label");
    assert.ok(svg.includes("<table"), "missing data-table fallback");
    assert.ok(svg.includes("Groceries"), "fallback table missing the category name");
  });
});

describe("lineChartSvg escapes labels", () => {
  test("a label containing HTML/SVG-special characters is escaped, not injected", () => {
    const { sandbox } = loadPageSandbox();
    const svg = sandbox.lineChartSvg(
      [{ label: '"><img src=x onerror=alert(1)>', value: 100 }],
      { title: "Test" },
    );
    assert.ok(!svg.includes("<img src=x"), "raw markup leaked into chart via a label");
  });

  test("line chart declares role=img with a label, and includes a data-table fallback", () => {
    const { sandbox } = loadPageSandbox();
    const svg = sandbox.lineChartSvg([{ label: "Jan", value: 100 }], { title: "Net worth" });
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
