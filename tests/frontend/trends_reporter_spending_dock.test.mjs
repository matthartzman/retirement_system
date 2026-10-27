// Spending dock: Pin/Unpin must not close the panels, and the wiring lives in spending_dock.js.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { isOutsideClick } from "../../financial_trends_reporter/frontend/spending_dock.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const html = fs.readFileSync(path.join(HERE, "..", "..", "financial_trends_reporter", "frontend", "index.html"), "utf8");
const el = (connected, inside) => ({ isConnected: connected, closest: () => (inside ? {} : null) });

test("a click on a button removed by re-render is not an outside click", () => {
  assert.equal(isOutsideClick(el(false, false)), false);
});
test("a click inside the chart or dock is not outside", () => { assert.equal(isOutsideClick(el(true, true)), false); });
test("a click elsewhere is outside", () => { assert.equal(isOutsideClick(el(true, false)), true); });
test("index.html wires the dock from the module", () => {
  assert.match(html, /import \{[^}]*initSpendingDock[^}]*\} from "\.\/spending_dock\.js"/);
  assert.match(html, /initSpendingDock\(\{ doc: document, win: window, getModel: \(\) => categoryModel \}\)/);
  assert.ok(!html.includes("function pinRow("));   // moved, not duplicated
});
