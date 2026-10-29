/* Run-time history helpers (ES module, pure apart from localStorage). Shared by the planner's
   progress overlay (dashboard_decomp_build_lifecycle.js) and served to the Financial Insight
   reporter at /shared/runtime_history.js. Each app keeps its own history: different origins
   have separate localStorage. */
export const POPUP_RUNTIME_HISTORY_LS_KEY = "popupRuntimeHistory_v1";
export const POPUP_RUNTIME_HISTORY_MAX = 20;

export function formatElapsed(ms) {
  const total = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(total / 60),
    sec = String(total % 60).padStart(2, "0");
  return `${m}:${sec}`;
}

// Per-popup average run-time (#326): each progress popup (build, plan load,
// YTD load, spending model load, housing optimizer screen/run, load-all-
// assumptions) shares one overlay, so run-time history is bucketed by
// the caller-supplied popupId rather than by title (titles change mid-run,
// e.g. the build sequence cycles through several). Persisted client-side
// only -- this is a display nicety, not data the app needs to survive a
// reinstall or sync across machines.
export function loadPopupRuntimeHistory(key = POPUP_RUNTIME_HISTORY_LS_KEY) {
  try {
    const raw = localStorage.getItem(key);
    const parsed = raw ? JSON.parse(raw) : {};
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch (_e) {
    return {};
  }
}
export function recordPopupRuntime(popupId, durationMs, key = POPUP_RUNTIME_HISTORY_LS_KEY, max = POPUP_RUNTIME_HISTORY_MAX) {
  if (!popupId || !Number.isFinite(durationMs) || durationMs <= 0) return;
  const history = loadPopupRuntimeHistory(key);
  const runs = Array.isArray(history[popupId]) ? history[popupId] : [];
  runs.unshift(durationMs);
  history[popupId] = runs.slice(0, max);
  try {
    localStorage.setItem(key, JSON.stringify(history));
  } catch (_e) {}
}
export function averageRuntimeText(popupId, key = POPUP_RUNTIME_HISTORY_LS_KEY) {
  if (!popupId) return null;
  const runs = loadPopupRuntimeHistory(key)[popupId];
  if (!Array.isArray(runs) || runs.length < 2) return null;
  const avgMs = runs.reduce((sum, v) => sum + v, 0) / runs.length;
  return `The average run-time over the last ${runs.length} runs has been ${formatElapsed(avgMs)}`;
}
