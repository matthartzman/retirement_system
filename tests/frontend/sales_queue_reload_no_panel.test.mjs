// Regression: the 1099-B apply, broker import and sale record paths call window.sqReload() to refresh the queue even
// when no single-sale panel is open; that used to throw "Cannot read properties of null (reading 'candidate')".
import { test } from "node:test";
import assert from "node:assert/strict";

test("sqReload with no panel open reloads the list instead of throwing", async () => {
  const calls = [];
  globalThis.esc = (s) => String(s ?? "");
  globalThis.window = globalThis;
  globalThis.accountDisplayLabel = (a) => String(a);
  globalThis.document = { getElementById: () => null };
  globalThis.api = async (url) => { calls.push(url); return { success: true, candidates: [], counts: { unmatched: 0 } }; };
  const m = await import("../../frontend/js/dashboard_decomp_sales_queue.js");
  await assert.doesNotReject(async () => m.sqReload());
  assert.ok(calls.some((u) => u.startsWith("/api/sales/candidates?state=unmatched")));
});
