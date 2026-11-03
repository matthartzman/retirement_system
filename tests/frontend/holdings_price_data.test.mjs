// Plan Holdings: current value must come from the last build's prices, not silently fall back to cost.
// /api/admin/diagnostics names the file "pricing_diagnostics" (it was "pricing_diagnostics.json").
import { test, before } from "node:test";
import assert from "node:assert/strict";

let m;
before(async () => {
  globalThis.window = globalThis;
  globalThis.esc = (s) => String(s ?? "");
  globalThis.setTimeout = () => 0;
  globalThis.api = async () => ({});
  m = await import("../../frontend/js/dashboard_decomp_holdings.js");
});

const diag = (name) => ({ files: [{ name, json: { prices: { AVUV: 125.39 } } }, { name: "plan_summary", json: {} }] });

test("prices are read under both the current and the legacy diagnostics file name", () => {
  assert.deepEqual(m.pricesFromDiagnostics(diag("pricing_diagnostics")), { AVUV: 125.39 });
  assert.deepEqual(m.pricesFromDiagnostics(diag("pricing_diagnostics.json")), { AVUV: 125.39 });
});

test("no diagnostics, or none for pricing, gives an empty price map", () => {
  assert.deepEqual(m.pricesFromDiagnostics(null), {});
  assert.deepEqual(m.pricesFromDiagnostics({ files: [{ name: "plan_summary", json: {} }] }), {});
});

test("a priced lot's value is shares x market price and differs from its cost", () => {
  window.holdingsPriceData = m.pricesFromDiagnostics(diag("pricing_diagnostics"));
  const v = m.holdingLotCurrentValue({ symbol: "avuv", shares: "88", purchase_price: "117.25" });
  assert.equal(v.isEstimate, false);
  assert.equal(v.price, 125.39);
  assert.ok(Math.abs(v.value - 88 * 125.39) < 1e-9);
});

test("an unpriced lot still falls back to cost and is flagged as an estimate", () => {
  window.holdingsPriceData = {};
  const v = m.holdingLotCurrentValue({ symbol: "ZZZZ", shares: "10", purchase_price: "5" });
  assert.equal(v.isEstimate, true);
  assert.equal(v.value, 50);
});
