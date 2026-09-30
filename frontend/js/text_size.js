// In-app text-size preference (100/115/130%). Independent of WebView zoom
// settings so low-vision users can enlarge the UI in desktop mode.
// Persisted server-side via /api/prefs (key rpTextSize) and mirrored in
// localStorage for a flash-free first paint.
export const TEXT_SIZE_OPTIONS = [100, 115, 130];

export function normalizeTextSize(v) {
  const n = parseInt(v, 10);
  return TEXT_SIZE_OPTIONS.indexOf(n) >= 0 ? n : 100;
}

export function applyTextSize(v) {
  const n = normalizeTextSize(v);
  document.documentElement.style.zoom = n === 100 ? "" : String(n / 100);
  const sel = document.getElementById("textSizeSelect");
  if (sel) sel.value = String(n);
  return n;
}

export function setTextSize(v) {
  const n = applyTextSize(v);
  try {
    localStorage.setItem("rpTextSize", String(n));
  } catch (_e) {}
  fetch("/api/prefs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rpTextSize: n }),
  }).catch(function () {});
  return n;
}

function init() {
  let local = null;
  try {
    local = localStorage.getItem("rpTextSize");
  } catch (_e) {}
  if (local !== null) applyTextSize(local);
  const sel = document.getElementById("textSizeSelect");
  if (sel) sel.addEventListener("change", () => setTextSize(sel.value));
  fetch("/api/prefs")
    .then((r) => r.json())
    .then((p) => {
      const v = p && p.prefs ? p.prefs.rpTextSize : undefined;
      if (typeof v !== "undefined") applyTextSize(v);
    })
    .catch(function () {});
}

if (typeof document !== "undefined") {
  if (document.readyState === "loading")
    document.addEventListener("DOMContentLoaded", init);
  else init();
}
