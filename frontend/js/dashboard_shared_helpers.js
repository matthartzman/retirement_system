// dashboard_shared_helpers.js: the single copy of esc/escJs/fmtMoney/fmtPct and
// the display-formatting helpers other frontend modules build on. Loaded first
// (index.html) so it is available as plain globals to every script that
// follows, and via window.RPDashboardUtils for callers that prefer that form.
//
// A13: these were previously reimplemented per-file (dashboard.js, reports_ui.js,
// planning_workbench_ui.js, dashboard_batch_assumption_edit.js) with divergent
// escJs behavior (only this version strips \n/\r, which the others didn't) —
// a security-relevant drift for HTML-escaping code. One implementation now.
function esc(s) {
  return String(s ?? "").replace(
    /[&<>"']/g,
    (m) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        m
      ],
  );
}
function escJs(s) {
  return String(s ?? "")
    .replace(/\\/g, "\\\\")
    .replace(/'/g, "\\'")
    .replace(/\n/g, "\\n")
    .replace(/\r/g, "");
}
function fmtMoney(v) {
  if (v === undefined || v === null || v === "") return "Not available";
  const n = Number(String(v).replace(/[^0-9.-]/g, ""));
  if (!Number.isFinite(n)) return "Not available";
  return n.toLocaleString(undefined, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  });
}
function fmtPct(v) {
  if (v === undefined || v === null || v === "") return "Not available";
  const n = Number(String(v).replace(/[^0-9.-]/g, ""));
  if (!Number.isFinite(n)) return "Not available";
  return n.toLocaleString(undefined, { maximumFractionDigits: 1 }) + "%";
}
function decimalTrim(text) {
  return String(text)
    .replace(/\.0+$/, "")
    .replace(/(\.\d*?)0+$/, "$1");
}
function numberFromDisplay(value) {
  const raw = String(value ?? "").trim();
  if (!raw) return null;
  const neg = /^\(.*\)$/.test(raw) || /^\s*-/.test(raw);
  const cleaned = raw.replace(/[,$%\s]/g, "").replace(/[()]/g, "");
  const n = Number(cleaned);
  if (!Number.isFinite(n)) return null;
  return neg ? -Math.abs(n) : n;
}
function formatNumberValue(value, maxDecimals = 2, minDecimals = 0) {
  const n = numberFromDisplay(value);
  if (n === null) return String(value ?? "");
  const opts = {
    useGrouping: false,
    minimumFractionDigits: minDecimals,
    maximumFractionDigits: maxDecimals,
  };
  return n.toLocaleString(undefined, opts);
}
function currencyDisplay(value, maxDecimals = 2) {
  const n = numberFromDisplay(value);
  if (n === null) return String(value ?? "");
  const max = Math.max(2, Math.min(6, Number(maxDecimals) || 2));
  const opts = {
    minimumFractionDigits: Number.isInteger(n) ? 0 : 2,
    maximumFractionDigits: max,
  };
  return (n < 0 ? "-" : "") + "$" + Math.abs(n).toLocaleString(undefined, opts);
}
function percentDisplay(value, decimals = 0) {
  const n = numberFromDisplay(value);
  if (n === null) return String(value ?? "");
  const d = Math.max(0, Math.min(6, Number(decimals) || 0));
  return (
    n.toLocaleString(undefined, {
      minimumFractionDigits: d,
      maximumFractionDigits: d,
    }) + "%"
  );
}
if (typeof window !== "undefined") {
  window.RPDashboardUtils = {
    decimalTrim,
    numberFromDisplay,
    formatNumberValue,
    currencyDisplay,
    percentDisplay,
  };
}
