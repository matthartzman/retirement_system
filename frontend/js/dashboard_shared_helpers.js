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
// Shared row-action icons (A13-style single copy): a trash can for delete
// buttons and a calendar for the spending-screen Annualize control, both with
// title/aria-label so a rollover still shows the word they replace.
const TRASH_SVG_ICON =
  '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" focusable="false"><path fill="currentColor" d="M6 1.5h4a.5.5 0 0 1 .5.5v1h3a.5.5 0 0 1 0 1h-.6l-.7 9.4a1.5 1.5 0 0 1-1.5 1.4H5.3a1.5 1.5 0 0 1-1.5-1.4L3.1 4H2.5a.5.5 0 0 1 0-1h3V2a.5.5 0 0 1 .5-.5Zm-1.9 2.5.68 9.32a.5.5 0 0 0 .5.46h5.44a.5.5 0 0 0 .5-.46L11.9 4H4.1Zm2.15 1.75a.5.5 0 0 1 .5.5v5.5a.5.5 0 0 1-1 0v-5.5a.5.5 0 0 1 .5-.5Zm3.5 0a.5.5 0 0 1 .5.5v5.5a.5.5 0 0 1-1 0v-5.5a.5.5 0 0 1 .5-.5ZM7 2.5v.5h2v-.5H7Z"/></svg>';
const CALENDAR_SVG_ICON =
  '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" focusable="false"><path fill="currentColor" d="M5 1a.5.5 0 0 1 .5.5V2h5v-.5a.5.5 0 0 1 1 0V2h1A1.5 1.5 0 0 1 14 3.5v9A1.5 1.5 0 0 1 12.5 14h-9A1.5 1.5 0 0 1 2 12.5v-9A1.5 1.5 0 0 1 3.5 2h1v-.5A.5.5 0 0 1 5 1ZM3 6v6.5a.5.5 0 0 0 .5.5h9a.5.5 0 0 0 .5-.5V6H3Zm0-1h10V3.5a.5.5 0 0 0-.5-.5h-9a.5.5 0 0 0-.5.5V5Zm2 3h2v2H5V8Z"/></svg>';
function deleteIconBtn(onclickExpr, opts) {
  opts = opts || {};
  const disabledAttr = opts.disabled ? " disabled" : "";
  const extraCls = opts.cls ? " " + opts.cls : "";
  const extraStyle = opts.style ? ' style="' + opts.style + '"' : "";
  return (
    '<button type="button" class="danger-link icon-btn' +
    extraCls +
    '"' +
    extraStyle +
    disabledAttr +
    ' onclick="' +
    onclickExpr +
    '" title="Delete" aria-label="Delete">' +
    TRASH_SVG_ICON +
    "</button>"
  );
}
// Calendar toggle for the spending-screen Annualize flag: green = annualize
// (default), red = don't annualize (lumpy, e.g. real estate tax). Clicking
// flips the two-state flag directly -- no third "Default" option, since the
// caller resolves the starting color from the known no_annualize value before
// rendering.
function annualizeToggleBtn(onclickExpr, isNoAnnualize, opts) {
  opts = opts || {};
  const disabledAttr = opts.disabled ? " disabled" : "";
  const stateCls = isNoAnnualize ? "state-no-annualize" : "state-annualize";
  const tip = isNoAnnualize ? "Do Not Annualize" : "Annualize";
  return (
    '<button type="button" class="icon-annualize-toggle ' +
    stateCls +
    '" data-tip="' +
    esc(tip) +
    '"' +
    disabledAttr +
    ' onclick="' +
    onclickExpr +
    '" aria-label="' +
    esc(tip) +
    '">' +
    CALENDAR_SVG_ICON +
    "</button>"
  );
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
