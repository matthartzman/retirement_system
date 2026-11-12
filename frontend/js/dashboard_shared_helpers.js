// dashboard_shared_helpers.js: the single copy of esc/escJs/fmtMoney/fmtPct and
// the display-formatting helpers other frontend modules build on. Loaded first
// (index.html) so it is available as plain globals to every script that
// follows, and via window.RPDashboardUtils for callers that prefer that form.
//
// A13: these were previously reimplemented per-file (dashboard.js, reports_ui.js,
// planning_workbench_ui.js, dashboard_batch_assumption_edit.js) with divergent
// escJs behavior (only this version strips \n/\r, which the others didn't) —
// a security-relevant drift for HTML-escaping code. One implementation now.
//
// system_review 2026-08-31 item 3.11: converted to type="module" (see
// tests/test_dashboard_shared_helpers_load_order_regression.py for why that
// was safe here specifically -- unlike pywebview_bridge.js, see
// tests/test_pywebview_bridge_load_order_regression.py, which is not). Every
// top-level function/const below stops being an implicit global the moment
// this runs as a module, so the explicit window bridge below (mirroring the
// convert_dashboard.mjs-generated bridges every other leaf module already
// has) is what keeps esc(...), fmtMoney(...), etc. callable as bare
// identifiers from every classic-or-module script that follows this one.
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
// Housing dwelling-spec option sets (Task 16, design doc §10/§14): the
// optimizer panel (dashboard_decomp_housing_optimizer.js) and the spending
// screen's next-housing-step fields (dashboard_decomp_housing_scenarios.js)
// describe the same dwelling, so both render their bedroom/bathroom/property
// type/sqft/lot-size/area-type selects from these arrays instead of each
// screen maintaining its own list and agreeing (or, per the design doc's
// decision log, disagreeing) by coincidence. `areaTypes` holds only the four
// concrete values; the optimizer alone prepends its own "any" search
// wildcard, since the spending screen records a specific dwelling and must
// not offer it.
const HOUSING_DWELLING_OPTIONS = {
  areaTypes: [
    { value: "urban", label: "Urban" },
    { value: "suburban", label: "Suburban" },
    { value: "exurban", label: "Exurban" },
    { value: "rural", label: "Rural" },
  ],
  bedrooms: [
    { value: "2", label: "2 BR" },
    { value: "3", label: "3 BR" },
    { value: "4", label: "4 BR" },
    { value: "5", label: "5+ BR" },
  ],
  bathrooms: [
    { value: "1", label: "1 BA" },
    { value: "1.5", label: "1.5 BA" },
    { value: "2", label: "2 BA" },
    { value: "2.5", label: "2.5 BA" },
    { value: "3", label: "3 BA" },
    { value: "3.5", label: "3.5+ BA" },
  ],
  propertyTypes: [
    { value: "single_family", label: "Single family" },
    { value: "townhome", label: "Townhome" },
    { value: "condo", label: "Condo" },
    { value: "duplex", label: "Duplex" },
    { value: "apartment", label: "Apartment (rent only)" },
  ],
  sqftBands: [
    { value: "under_1200", label: "Under 1,200 sqft" },
    { value: "1200_1800", label: "1,200-1,800 sqft" },
    { value: "1800_2500", label: "1,800-2,500 sqft" },
    { value: "2500_3500", label: "2,500-3,500 sqft" },
    { value: "over_3500", label: "Over 3,500 sqft" },
  ],
  lotSizeBands: [
    { value: "under_quarter", label: "Under 1/4 acre" },
    { value: "quarter_half", label: "1/4 to 1/2 acre" },
    { value: "half_one", label: "1/2 to 1 acre" },
    { value: "one_three", label: "1 to 3 acres" },
    { value: "over_three", label: "Over 3 acres" },
  ],
};
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
    '" aria-pressed="' +
    (isNoAnnualize ? "false" : "true") +
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
// UX-003/UX-002: announce() -> persistent live regions (index.html); panelMsgHtml() -> panel message, announced once per change; confirmDestructive() -> in-app dialog, fails closed. UX-005: tabBarHtml/tabPanelHtml/tabSelect/tabKeydown are the one tab strip (tabs are [id, labelHtml]; `select` names a window function called as select(id, prefix)).
const announce = (text, { error = false } = {}) => { const el = typeof document !== "undefined" && document.getElementById ? document.getElementById(error ? "rpAlert" : "rpLive") : null; if (el) { el.textContent = ""; el.textContent = String(text ?? ""); } };
const _panelMsgSeen = {};
function panelAnnounce(key, m) {
  if (!m || !m.text) { delete _panelMsgSeen[key]; return false; }
  if (_panelMsgSeen[key] !== m.text) { _panelMsgSeen[key] = m.text; announce(m.text, { error: !!m.error }); }
  return true;
}
const tabBarHtml = (prefix, tabs, active, select, label, cls = "workspace-tabs", btn = "workspace-tab", on = "active") =>
  `<div class="${cls}" id="${prefix}-bar" role="tablist" aria-label="${esc(label)}" data-tabs="${tabs.map((t) => t[0]).join(",")}">` + tabs.map(([id, html]) =>
    `<button type="button" role="tab" id="${prefix}-t-${id}" class="${btn}${id === active ? " " + on : ""}" aria-selected="${id === active}" aria-controls="${prefix}-p-${id}" tabindex="${id === active ? 0 : -1}" onclick="tabSelect('${prefix}','${select}','${id}')" onkeydown="tabKeydown(event,'${prefix}','${select}')">${html}</button>`).join("") + "</div>";
const tabSlug = (t) => String(t).toLowerCase().replace(/[^a-z0-9]+/g, "-"); // a tab id must be one IDREF token
const tabPanelHtml = (prefix, id, html, cls = "", hidden = false) => `<div class="${cls}" role="tabpanel" id="${prefix}-p-${id}" aria-labelledby="${prefix}-t-${id}"${hidden ? " hidden" : ""}>${html}</div>`;
function tabSelect(prefix, select, id) { window[select](id, prefix); const b = document.getElementById(`${prefix}-t-${id}`); if (b) b.focus(); } // focus survives a re-render
function tabKeydown(event, prefix, select) {
  const bar = document.getElementById(`${prefix}-bar`), ids = bar ? bar.dataset.tabs.split(",") : [], cur = ids.indexOf(String(event.target && event.target.id).replace(`${prefix}-t-`, ""));
  const next = cur < 0 ? undefined : { ArrowRight: (cur + 1) % ids.length, ArrowLeft: (cur + ids.length - 1) % ids.length, Home: 0, End: ids.length - 1 }[event.key];
  if (next !== undefined) { event.preventDefault(); tabSelect(prefix, select, ids[next]); }
}
const panelMsgHtml = (key, m, errCls = "field-error", okCls = "muted", tag = "p") => panelAnnounce(key, m) ? `<${tag} class="${m.error ? errCls : okCls}">${esc(m.text)}</${tag}>` : "";
async function confirmDestructive(consequence, { title, action }) {
  const ask = typeof showInAppConfirm === "function" ? showInAppConfirm : typeof window !== "undefined" ? window.showInAppConfirm : null;
  return typeof ask === "function" && (await ask(consequence, { title: title || action, confirmLabel: action, variant: "warn" })) === true;
}
if (typeof window !== "undefined") {
  window.RPDashboardUtils = {
    decimalTrim,
    numberFromDisplay,
    formatNumberValue,
    currencyDisplay,
    percentDisplay,
  };
  // Bare-global bridge: every one of this module's top-level bindings, so
  // callers elsewhere keep writing esc(x), fmtMoney(x), etc. rather than
  // window.esc(x). One-time value copies are correct here -- nothing in this
  // file reassigns any of these after module evaluation, unlike dashboard.js's
  // renderMain/showStepHelp, which need the get/set accessor treatment
  // because other leaf modules monkey-patch them.
  Object.assign(window, {
    esc,
    escJs,
    TRASH_SVG_ICON,
    CALENDAR_SVG_ICON,
    deleteIconBtn,
    annualizeToggleBtn,
    fmtMoney,
    fmtPct,
    decimalTrim,
    numberFromDisplay,
    formatNumberValue,
    currencyDisplay,
    percentDisplay,
    HOUSING_DWELLING_OPTIONS,
    confirmDestructive,
    announce,
    panelAnnounce,
    panelMsgHtml,
    tabBarHtml,
    tabSlug,
    tabPanelHtml,
    tabSelect,
    tabKeydown,
  });
}
