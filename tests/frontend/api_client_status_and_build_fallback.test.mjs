// W1-06 (QA-004): RetirementApiClient.request puts the real HTTP status on the error it throws, so
// buildWithProgress's "404 from /api/build/start -> POST /api/build" fallback actually runs.
// Before this, only the (removed) inline fetch branch in api() set err.status, and that branch was
// unreachable in a browser because api_client.js is always loaded.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const JS_DIR = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "frontend", "js");

function response(status, body) {
  const text = typeof body === "string" ? body : JSON.stringify(body);
  return { ok: status >= 200 && status < 300, status, statusText: `HTTP ${status}`, text: async () => text };
}

function sandboxWithRealClient(fetchImpl) {
  const sb = loadDashboardSandbox();
  vm.runInContext(fs.readFileSync(path.join(JS_DIR, "api_client.js"), "utf8"), sb, { filename: "api_client.js" });
  sb.fetch = fetchImpl;
  vm.runInContext('appReady = true; apiBase = "";', sb);
  sb.updateBuildOverlay = () => {};
  sb.setActiveBuildJob = () => {};
  return sb;
}

test("a non-2xx response carries one error shape: message, status, errors, fieldErrors", async () => {
  const sb = sandboxWithRealClient(async () =>
    response(422, { error: "Plan data is invalid.", errors: ["a", "b"], field_errors: [{ label: "x" }] }),
  );
  await assert.rejects(
    () => sb.api("/api/anything", { method: "POST", body: "{}" }),
    (err) => {
      assert.equal(err.message, "Plan data is invalid.");
      assert.equal(err.status, 422);
      assert.deepEqual([...err.errors], ["a", "b"]);
      assert.equal(err.fieldErrors.length, 1);
      return true;
    },
  );
});

test("a 404 from /api/build/start falls back to POST /api/build", async () => {
  const calls = [];
  const sb = sandboxWithRealClient(async (url, opts) => {
    calls.push(`${(opts && opts.method) || "GET"} ${url}`);
    if (url.endsWith("/api/build/start")) return response(404, { error: "Not found" });
    if (url.endsWith("/api/build")) return response(200, { success: true, via: "legacy" });
    throw new Error(`unexpected request ${url}`);
  });
  const out = await sb.buildWithProgress({ any: "body" });
  assert.equal(out.via, "legacy");
  assert.deepEqual(calls, ["POST /api/build/start", "POST /api/build"]);
});

test("any other status from /api/build/start is rethrown, not retried", async () => {
  const calls = [];
  const sb = sandboxWithRealClient(async (url, opts) => {
    calls.push(`${(opts && opts.method) || "GET"} ${url}`);
    return response(409, { error: "Build not started: 1 required Plan Data value(s) are blank." });
  });
  await assert.rejects(
    () => sb.buildWithProgress({}),
    (err) => err.status === 409 && /Build not started/.test(err.message),
  );
  assert.deepEqual(calls, ["POST /api/build/start"]);
});
