// #338 W-C task C4: the Spending workspace's "Withdrawal Order" tab may be
// removed only once every row it renders also renders on Optimize (HSA
// Drawdown, Withdrawal Sequencing, Harvesting) AND belongs to Optimize's own
// row set -- the one sourceStepForRow()/stepStats() read. A row that fails
// parity moves to Optimize; it is never dropped.
//
// Fixture: the demo plan's own Withdrawal Policy / HSA Policy rows.

import { test, describe, before } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const DEMO = path.join(HERE, "..", "..", "input", "demo");

function splitCsv(line) {
  const out = [];
  let cur = "";
  let q = false;
  for (const ch of line) {
    if (ch === '"') q = !q;
    else if (ch === "," && !q) {
      out.push(cur);
      cur = "";
    } else cur += ch;
  }
  out.push(cur);
  return out;
}

function demoWithdrawalRows() {
  const rows = [];
  for (const f of fs.readdirSync(DEMO).filter((x) => x.endsWith(".csv"))) {
    for (const line of fs.readFileSync(path.join(DEMO, f), "utf8").split(/\r?\n/)) {
      const [section, subsection, label, value] = splitCsv(line);
      if (section !== "Withdrawal Policy" && section !== "HSA Policy") continue;
      rows.push({ row_index: rows.length + 1, section, subsection, label, value: value || "", original_value: value || "" });
    }
  }
  return rows;
}

const rowIdsIn = (html) => new Set([...String(html).matchAll(/data-row="(\d+)"/g)].map((m) => Number(m[1])));

describe("Withdrawal Order parity with Optimize (#338 C4)", () => {
  let sandbox;
  let demo;
  before(() => {
    sandbox = loadDashboardSandbox();
    demo = demoWithdrawalRows();
    sandbox.__rows = demo;
    vm.runInContext('rows = globalThis.__rows; searchText = ""; planLoaded = true;', sandbox);
    sandbox.withdrawalAccountOrderEditorHtml = () => "";
    sandbox.window.withdrawalAccountOrderEditorHtml = () => "";
  });

  function withdrawalOrderRows() {
    // Exactly what the tab rendered: the four row blocks
    // renderWithdrawalStrategy() stacked under the order table.
    const other = sandbox.withdrawalOtherRows();
    return rowIdsIn(
      sandbox.hsaWithdrawalPolicyBlock(other) +
        sandbox.taxLossHarvestingBlock(other) +
        sandbox.gainHarvestBlock(other) +
        sandbox.withdrawalMiscBlock(other),
    );
  }

  function optimizeRenderedRows() {
    let sections = [];
    const real = sandbox.renderStrategyScreen;
    sandbox.renderStrategyScreen = (s) => {
      sections = s;
      return "";
    };
    try {
      sandbox.renderStrategyOptimize();
    } finally {
      sandbox.renderStrategyScreen = real;
    }
    const keys = ["hsa_drawdown", "withdrawal_sequencing", "harvesting"];
    return rowIdsIn(sections.filter((s) => keys.includes(s.key)).map((s) => s.body()).join(""));
  }

  test("the fixture actually exercises the tab", () => {
    assert.ok(withdrawalOrderRows().size >= 5, "demo withdrawal rows did not render");
  });

  test("every row the tab renders also renders on Optimize", () => {
    const opt = optimizeRenderedRows();
    const missing = [...withdrawalOrderRows()].filter((id) => !opt.has(id));
    assert.deepEqual(missing.map((id) => demo[id - 1].label), []);
  });

  test("every row the tab renders is in rawRowsForStep('strategy_optimize')", () => {
    const own = new Set(sandbox.rawRowsForStep("strategy_optimize").map((r) => r.row_index));
    const missing = [...withdrawalOrderRows()].filter((id) => !own.has(id));
    assert.deepEqual(missing.map((id) => demo[id - 1].label), []);
  });

  test("the Withdrawal Order tab is gone from the Spending workspace", () => {
    const tabs = vm.runInContext("STRATEGY_TABS.spending_core || []", sandbox);
    assert.ok(!tabs.includes("Withdrawal Order"));
  });
});
