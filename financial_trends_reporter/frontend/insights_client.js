// Financial Insight's fetch wrapper, prefix-agnostic. The same page is served at "/" (desktop listeners) and at
// "/insights/" (a signed-in user's own worker, behind the gateway). Pure functions plus one installer; no DOM.

export const INSIGHTS_PREFIX = "/insights";
const POLL_PATHS = new Set(["/api/ping", "/api/run-status"]);
const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"]);

// "" at the root, "/insights" when the page itself is under that prefix.
export function baseFromPath(pathname) {
  const p = String(pathname || "");
  return p === INSIGHTS_PREFIX || p.startsWith(INSIGHTS_PREFIX + "/") ? INSIGHTS_PREFIX : "";
}

// Feature URLs ("/api/..", "/shared/..") gain the prefix; the gateway's own "/api/auth/.." never does.
export function prefixUrl(url, base) {
  if (typeof url !== "string" || !base) return url;
  if (url.startsWith("/api/auth/")) return url;
  return url.startsWith("/api/") || url.startsWith("/shared/") ? base + url : url;
}

// Background polling must not keep a gateway session alive. The live snapshot counts only when it is not a forced refresh.
export function isBackgroundPoll(url) {
  if (typeof url !== "string") return false;
  const [path, query = ""] = url.split("?");
  if (POLL_PATHS.has(path)) return true;
  return path === "/api/live-snapshot" && !/(^|&)refresh=1(&|$)/.test(query);
}

export function loginUrl(base) {
  return base ? `/login?next=${base}/` : "/signin";
}

// install({win, fetchImpl, base, onUnauthorized}) replaces win.fetch and returns a small control object.
export function installInsightsClient({ win, base, onUnauthorized }) {
  const nativeFetch = win.fetch.bind(win);
  let worker = base !== "";
  let csrf = null;
  const needCsrf = () => {
    if (!csrf) {
      csrf = nativeFetch("/api/auth/session", { credentials: "same-origin" })
        .then((r) => (r.ok ? r.json() : {}))
        .then((j) => j.csrf_token || "")
        .catch(() => "");
    }
    return csrf;
  };
  win.fetch = async (input, init) => {
    const isString = typeof input === "string";
    const url = isString ? input : "";
    const next = { ...(init || {}) };
    if (worker && isString) {
      const method = String(next.method || "GET").toUpperCase();
      const headers = new win.Headers(next.headers || {});
      if (UNSAFE.has(method)) {
        const token = await needCsrf();
        if (token) headers.set("X-CSRF-Token", token);
      }
      if (isBackgroundPoll(url)) headers.set("X-Background-Poll", "1");
      next.headers = headers;
    }
    const resp = await nativeFetch(isString ? prefixUrl(url, base) : input, isString ? next : init);
    if (resp.status === 401) onUnauthorized();
    return resp;
  };
  return { setWorker: (on) => { worker = !!on || base !== ""; }, isWorker: () => worker };
}

// Newest log entry older than the previous weekday's market close (21:00 UTC) -> an automatic update is due.
export function lastMarketSessionEnd(now) {
  const d = new Date(now);
  d.setUTCHours(21, 0, 0, 0);
  if (d.getTime() > now) d.setUTCDate(d.getUTCDate() - 1);
  while (d.getUTCDay() === 0 || d.getUTCDay() === 6) d.setUTCDate(d.getUTCDate() - 1);
  return d.getTime();
}

// "first" when there is no history yet; "daily" when the latest entry predates the last session; otherwise "".
export function autoUpdateReason(history, now) {
  if (!Array.isArray(history) || history.length === 0) return "first";
  const last = Date.parse(history[history.length - 1].run_at || "");
  if (!Number.isFinite(last)) return "first";
  return last < lastMarketSessionEnd(now) ? "daily" : "";
}

// At most one automatic update per calendar day per browser (the caller passes a get/set over storage).
export function claimDailyAutoUpdate(store, now) {
  const day = new Date(now).toISOString().slice(0, 10);
  try {
    if (store.get() === day) return false;
    store.set(day);
  } catch (err) { /* storage blocked: allow this one */ }
  return true;
}
