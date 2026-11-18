// Financial Insight served at "/" (desktop) and "/insights/" (gateway worker): one prefix-agnostic fetch wrapper.
import { test, describe } from "node:test";
import assert from "node:assert/strict";
import {
  baseFromPath, prefixUrl, isBackgroundPoll, loginUrl, installInsightsClient,
  lastMarketSessionEnd, autoUpdateReason, claimDailyAutoUpdate,
} from "../../financial_trends_reporter/frontend/insights_client.js";

function fakeWin(responder) {
  const calls = [];
  const win = {
    Headers,
    fetch: async (url, init) => { calls.push({ url, init }); return responder(url, init); },
  };
  return { win, calls };
}
const ok = (body = {}) => ({ ok: true, status: 200, json: async () => body });

describe("baseFromPath / prefixUrl / loginUrl", () => {
  test("empty at the root, /insights under the gateway prefix", () => {
    assert.equal(baseFromPath("/"), "");
    assert.equal(baseFromPath("/index.html"), "");
    assert.equal(baseFromPath("/insights"), "/insights");
    assert.equal(baseFromPath("/insights/"), "/insights");
    assert.equal(baseFromPath("/insightsfoo"), "");
  });
  test("only /api/ and /shared/ are prefixed; the gateway's own /api/auth/ never is", () => {
    assert.equal(prefixUrl("/api/history", "/insights"), "/insights/api/history");
    assert.equal(prefixUrl("/shared/runtime_history.js", "/insights"), "/insights/shared/runtime_history.js");
    assert.equal(prefixUrl("/api/auth/logout", "/insights"), "/api/auth/logout");
    assert.equal(prefixUrl("./charts.js", "/insights"), "./charts.js");
    assert.equal(prefixUrl("/api/history", ""), "/api/history");
  });
  test("401 goes to the gateway login in worker mode and /signin on the desktop", () => {
    assert.equal(loginUrl("/insights"), "/login?next=/insights/");
    assert.equal(loginUrl(""), "/signin");
  });
});

describe("isBackgroundPoll", () => {
  test("ping, run-status and the plain live snapshot poll; a forced refresh and data loads do not", () => {
    assert.equal(isBackgroundPoll("/api/ping"), true);
    assert.equal(isBackgroundPoll("/api/run-status"), true);
    assert.equal(isBackgroundPoll("/api/live-snapshot?from=2026-01-01"), true);
    assert.equal(isBackgroundPoll("/api/live-snapshot?refresh=1"), false);
    assert.equal(isBackgroundPoll("/api/history"), false);
    assert.equal(isBackgroundPoll("/api/run-now"), false);
  });
});

describe("installInsightsClient", () => {
  test("desktop: URLs and headers are passed through untouched", async () => {
    const { win, calls } = fakeWin(() => ok());
    installInsightsClient({ win, base: "", onUnauthorized: () => {} });
    await win.fetch("/api/ping", { method: "POST", body: "{}" });
    assert.equal(calls.length, 1);
    assert.equal(calls[0].url, "/api/ping");
    assert.equal(calls[0].init.headers, undefined);
  });

  test("under /insights: prefix, CSRF on unsafe methods (read once), X-Background-Poll on polls only", async () => {
    const { win, calls } = fakeWin((url) => ok(url === "/api/auth/session" ? { csrf_token: "tok123" } : {}));
    installInsightsClient({ win, base: "/insights", onUnauthorized: () => {} });
    await win.fetch("/api/run-now", { method: "POST" });
    await win.fetch("/api/ping", { method: "POST" });
    await win.fetch("/api/run-status");
    await win.fetch("/api/history");
    const sessionReads = calls.filter((c) => c.url === "/api/auth/session");
    assert.equal(sessionReads.length, 1);
    const byUrl = (u) => calls.find((c) => c.url === u);
    assert.equal(byUrl("/insights/api/run-now").init.headers.get("X-CSRF-Token"), "tok123");
    assert.equal(byUrl("/insights/api/run-now").init.headers.get("X-Background-Poll"), null);
    assert.equal(byUrl("/insights/api/ping").init.headers.get("X-Background-Poll"), "1");
    assert.equal(byUrl("/insights/api/run-status").init.headers.get("X-Background-Poll"), "1");
    assert.equal(byUrl("/insights/api/run-status").init.headers.get("X-CSRF-Token"), null);
    assert.equal(byUrl("/insights/api/history").init.headers.get("X-Background-Poll"), null);
  });

  test("the gateway logout goes to the gateway, not the worker", async () => {
    const { win, calls } = fakeWin((url) => ok(url === "/api/auth/session" ? { csrf_token: "t" } : {}));
    installInsightsClient({ win, base: "/insights", onUnauthorized: () => {} });
    await win.fetch("/api/auth/logout", { method: "POST" });
    assert.ok(calls.some((c) => c.url === "/api/auth/logout" && c.init.headers.get("X-CSRF-Token") === "t"));
  });

  test("a 401 calls onUnauthorized once per response", async () => {
    let n = 0;
    const { win } = fakeWin(() => ({ ok: false, status: 401, json: async () => ({}) }));
    installInsightsClient({ win, base: "", onUnauthorized: () => { n += 1; } });
    await win.fetch("/api/history");
    assert.equal(n, 1);
  });
});

describe("automatic updates in worker mode", () => {
  const at = (iso) => Date.parse(iso);
  test("the last market session end skips weekends", () => {
    // Sunday 2026-11-15 12:00Z -> Friday 2026-11-13 21:00Z
    assert.equal(lastMarketSessionEnd(at("2026-11-15T12:00:00Z")), at("2026-11-13T21:00:00Z"));
    // Tuesday 22:00Z -> same day 21:00Z; Tuesday 10:00Z -> Monday 21:00Z
    assert.equal(lastMarketSessionEnd(at("2026-11-17T22:00:00Z")), at("2026-11-17T21:00:00Z"));
    assert.equal(lastMarketSessionEnd(at("2026-11-17T10:00:00Z")), at("2026-11-16T21:00:00Z"));
  });
  test("empty history means first run; a stale newest entry means daily; a fresh one means none", () => {
    const now = at("2026-11-17T10:00:00Z");
    assert.equal(autoUpdateReason([], now), "first");
    assert.equal(autoUpdateReason([{ run_at: "2026-11-16T15:00:00Z" }], now), "daily");
    assert.equal(autoUpdateReason([{ run_at: "2026-11-16T22:00:00Z" }], now), "");
  });
  test("at most one automatic update per day", () => {
    let saved = null;
    const store = { get: () => saved, set: (v) => { saved = v; } };
    const now = at("2026-11-17T10:00:00Z");
    assert.equal(claimDailyAutoUpdate(store, now), true);
    assert.equal(claimDailyAutoUpdate(store, now + 3600_000), false);
    assert.equal(claimDailyAutoUpdate(store, now + 86_400_000), true);
  });
});
