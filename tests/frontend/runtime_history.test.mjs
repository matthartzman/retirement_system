// Shared run-time helpers (frontend/js/runtime_history.js): used by the planner's progress overlay
// and served to the Financial Insight app. Pure functions over localStorage, stubbed here.
import { test, describe, beforeEach } from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { pathToFileURL, fileURLToPath } from "node:url";

const MODULE = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "frontend", "js", "runtime_history.js");
const { formatElapsed, loadPopupRuntimeHistory, recordPopupRuntime, averageRuntimeText } = await import(
  pathToFileURL(MODULE).href
);

function installStorage(overrides = {}) {
  const data = new Map();
  globalThis.localStorage = {
    getItem: (k) => (data.has(k) ? data.get(k) : null),
    setItem: (k, v) => void data.set(k, String(v)),
    ...overrides,
  };
  return data;
}

describe("runtime_history", () => {
  beforeEach(() => installStorage());

  test("formatElapsed renders m:ss", () => {
    assert.equal(formatElapsed(0), "0:00");
    assert.equal(formatElapsed(5000), "0:05");
    assert.equal(formatElapsed(65000), "1:05");
    assert.equal(formatElapsed(-10), "0:00");
  });

  test("averageRuntimeText is null with fewer than 2 runs", () => {
    assert.equal(averageRuntimeText("build"), null);
    recordPopupRuntime("build", 10000);
    assert.equal(averageRuntimeText("build"), null);
    assert.equal(averageRuntimeText(""), null);
  });

  test("averageRuntimeText reports the average with 2+ runs", () => {
    recordPopupRuntime("build", 60000);
    recordPopupRuntime("build", 120000);
    assert.equal(averageRuntimeText("build"), "The average run-time over the last 2 runs has been 1:30");
  });

  test("history is capped at 20 runs, newest first", () => {
    for (let i = 1; i <= 25; i++) recordPopupRuntime("build", i * 1000);
    const runs = loadPopupRuntimeHistory().build;
    assert.equal(runs.length, 20);
    assert.equal(runs[0], 25000);
    assert.equal(runs[19], 6000);
  });

  test("non-positive and non-finite durations are ignored", () => {
    for (const bad of [0, -5, NaN, Infinity, undefined, "x"]) recordPopupRuntime("build", bad);
    recordPopupRuntime("", 5000);
    assert.deepEqual(loadPopupRuntimeHistory(), {});
  });

  test("storage that throws is safe", () => {
    installStorage({
      getItem: () => {
        throw new Error("denied");
      },
      setItem: () => {
        throw new Error("quota");
      },
    });
    assert.deepEqual(loadPopupRuntimeHistory(), {});
    assert.doesNotThrow(() => recordPopupRuntime("build", 5000));
    assert.equal(averageRuntimeText("build"), null);
  });

  test("separate popup ids keep separate histories", () => {
    recordPopupRuntime("a", 1000);
    recordPopupRuntime("a", 3000);
    recordPopupRuntime("b", 9000);
    assert.equal(averageRuntimeText("a"), "The average run-time over the last 2 runs has been 0:02");
    assert.equal(averageRuntimeText("b"), null);
  });

  test("default storage key is the planner's popupRuntimeHistory_v1", () => {
    const data = installStorage();
    recordPopupRuntime("a", 1000);
    assert.ok(data.has("popupRuntimeHistory_v1"));
  });

  test("custom storage key and max work", () => {
    const data = installStorage();
    for (let i = 1; i <= 5; i++) recordPopupRuntime("t", i * 1000, "trendsRuntime_v1", 3);
    assert.ok(data.has("trendsRuntime_v1"));
    assert.ok(!data.has("popupRuntimeHistory_v1"));
    assert.equal(loadPopupRuntimeHistory("trendsRuntime_v1").t.length, 3);
    assert.equal(averageRuntimeText("t", "trendsRuntime_v1"), "The average run-time over the last 3 runs has been 0:04");
    assert.equal(averageRuntimeText("t"), null);
  });
});
