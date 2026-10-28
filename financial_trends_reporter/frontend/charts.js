// Pure, side-effect-free chart-rendering helpers for the Financial trends
// reporter's dashboard (financial_trends_reporter/frontend/index.html).
//
// Finding QUA-302 (system review 2026-09-07, Wave 6 item W6-11): this logic
// used to live inline in index.html's <script> block with no module
// boundary -- untestable except by regex-extracting the whole block (see
// tests/frontend/trends_reporter_chart_escaping_and_accessibility.test.mjs,
// added in Wave 5 for the SVG-escaping/accessibility fix). Extracted here so
// it can be imported and tested directly; index.html's own <script
// type="module"> now imports from this file and keeps only the DOM-wiring/
// fetch/render orchestration inline.

export function fmtMoney(v) {
  if (v === null || v === undefined) return "-";
  return "$" + Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 });
}

// Finding UX-102 (Wave 5 item W5-6): category names and date labels were
// interpolated directly into these SVG strings (then assigned via
// innerHTML) with no escaping -- a imported category containing "&" or "<"
// broke the SVG markup, and a category name chosen to contain markup could
// inject arbitrary SVG/HTML. Escape every interpolated string, not just the
// ones a realistic category name might hit today.
export function escSvg(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// ---- Time scope -------------------------------------------------------------
// All date math below works on the "YYYY-MM-DD" string's own numbers (or UTC), never
// through a local-timezone getter -- see the isoWeekKey comment further down.
const MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export const SCOPE_NAMES = ["week", "month", "3m", "6m", "ytd", "1y", "all", "custom"];
const SCOPE_TITLE = { week: "1 Week", month: "1 Month", "3m": "3 Months", "6m": "6 Months", ytd: "YTD", "1y": "1 Year", all: "All Time", custom: "Custom" };
const SCOPE_NOMINAL_GRANULARITY = { week: "day", month: "day", "3m": "week", "6m": "week", ytd: "month", "1y": "month", all: "month" };

function parseYmd(s) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(s == null ? "" : s));
  return m ? [Number(m[1]), Number(m[2]), Number(m[3])] : null;
}
function ymdStr(y, m, d) {
  return `${String(y).padStart(4, "0")}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
}
function addDaysStr(s, n) {
  const [y, m, d] = parseYmd(s);
  const t = new Date(Date.UTC(y, m - 1, d + n));
  return ymdStr(t.getUTCFullYear(), t.getUTCMonth() + 1, t.getUTCDate());
}
// Calendar-month arithmetic with month-end clamping (Mar 31 - 1 month = Feb 28/29).
function addMonthsStr(s, n) {
  const [y, m, d] = parseYmd(s);
  const total = y * 12 + (m - 1) + n;
  const ny = Math.floor(total / 12), nm = total - ny * 12 + 1;
  return ymdStr(ny, nm, Math.min(d, new Date(Date.UTC(ny, nm, 0)).getUTCDate()));
}
function spanDaysStr(from, to) {
  const [a, b, c] = parseYmd(from), [x, y, z] = parseYmd(to);
  return (Date.UTC(x, y - 1, z) - Date.UTC(a, b - 1, c)) / 86400000;
}
function todayStr() {
  const t = new Date();
  return ymdStr(t.getFullYear(), t.getMonth() + 1, t.getDate());
}
function fmtMonthDay(s, withYear) {
  const [y, m, d] = parseYmd(s);
  return `${MONTH_ABBR[m - 1]} ${d}${withYear ? `, ${y}` : ""}`;
}

// Old saved preferences used "quarter" and "12m".
export function normalizeScope(key) {
  const k = ({ quarter: "3m", "12m": "1y" })[key] || key;
  return SCOPE_NAMES.includes(k) ? k : "month";
}

// The saved choice (localStorage "trendsScope_v1") -> {scope, from, to}; anything unusable -> Month.
export function parseSavedScope(raw) {
  let v = null;
  try { v = raw ? JSON.parse(raw) : null; } catch (_e) { v = null; }
  if (!v || typeof v !== "object") return { scope: "month", from: "", to: "" };
  const okDate = (d) => (typeof d === "string" && parseYmd(d) && d.length === 10 ? d : "");
  return { scope: normalizeScope(v.scope), from: okDate(v.from), to: okDate(v.to) };
}

// The one range every chart reads. anchorDate = the latest data date ("YYYY-MM-DD"; today when
// none). A Custom range's empty bound is left open ("").
export function scopeRange(scope, anchorDate, custom) {
  const sc = normalizeScope(scope);
  const anchor = parseYmd(anchorDate) ? String(anchorDate).slice(0, 10) : todayStr();
  const title = SCOPE_TITLE[sc];
  const rangeText = (from, to) => {
    const [fy] = parseYmd(from), [ty] = parseYmd(to);
    return `${fmtMonthDay(from, fy !== ty)} – ${fmtMonthDay(to, true)}`;
  };
  if (sc === "custom") {
    const from = custom && parseYmd(custom.from) ? custom.from : "";
    const to = custom && parseYmd(custom.to) ? custom.to : "";
    const span = spanDaysStr(from || ALL_TIME_START, to || anchor);
    const granularity = span < 28 ? "day" : span < 120 ? "week" : "month";
    const text = from && to ? rangeText(from, to) : from ? `from ${fmtMonthDay(from, true)}` : to ? `through ${fmtMonthDay(to, true)}` : "all dates";
    return { from, to, label: `${title} · ${text}`, granularity };
  }
  let from;
  if (sc === "week") from = addDaysStr(anchor, -7);
  else if (sc === "month") from = addMonthsStr(anchor, -1);
  else if (sc === "3m") from = addMonthsStr(anchor, -3);
  else if (sc === "6m") from = addMonthsStr(anchor, -6);
  else if (sc === "1y") from = addMonthsStr(anchor, -12);
  else if (sc === "ytd") from = ymdStr(parseYmd(anchor)[0], 1, 1);
  else from = ALL_TIME_START;
  return { from, to: anchor, label: `${title} · ${rangeText(from, anchor)}`, granularity: SCOPE_NOMINAL_GRANULARITY[sc] };
}

// Rows inside the scope. "all" returns every row (the page truncates to ALL_TIME_START itself, so
// it can say so). `custom` ({from, to}) defaults to the page's two date inputs.
export function filterByTimeframe(rows, tf, custom) {
  if (!rows.length) return rows;
  const sc = normalizeScope(tf);
  if (sc === "all") return rows;
  if (sc === "custom" && !custom && typeof document !== "undefined") {
    const f = document.getElementById("customFrom"), t = document.getElementById("customTo");
    custom = { from: f ? f.value : "", to: t ? t.value : "" };
  }
  const { from, to } = scopeRange(sc, rows[rows.length - 1].as_of_date, custom);
  return rows.filter((r) => {
    const d = String(r.as_of_date).slice(0, 10);
    return (!from || d >= from) && (!to || d <= to);
  });
}

// Nominal granularity comes from scopeRange (day for week/month, weekly for 3m/6m, monthly for
// ytd/1y/all) -- but never finer than the data supports: monthly points revert to weekly when
// the rows span under 4 months, and weekly to daily when they span under 4 weeks. A custom range
// has no nominal answer, so it's inferred from how many days the rows span.
export function granularityForTimeframe(tf, rows) {
  const spanDays = rows && rows.length >= 2
    ? (new Date(rows[rows.length - 1].as_of_date) - new Date(rows[0].as_of_date)) / 86400000
    : null;
  const sc = normalizeScope(tf);
  const nominal = SCOPE_NOMINAL_GRANULARITY[sc];
  if (nominal) {
    if (spanDays === null) return nominal;
    if (nominal === "month" && spanDays < 120) return spanDays < 28 ? "day" : "week";
    if (nominal === "week" && spanDays < 28) return "day";
    return nominal;
  }
  if (spanDays === null) return "day";
  if (spanDays < 28) return "day";
  if (spanDays < 120) return "week";
  return "month";
}

// Works entirely off the "YYYY-MM-DD" string's own numbers (never through
// a parsed Date's local-timezone getters, which can roll the calendar day
// backwards in negative-UTC-offset zones and silently misbucket rows).
function isoWeekKey(dateStr) {
  const [y, m, d] = dateStr.split("-").map(Number);
  const date = new Date(Date.UTC(y, m - 1, d));
  date.setUTCDate(date.getUTCDate() + 4 - (date.getUTCDay() || 7)); // nearest Thursday
  const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1));
  const week = Math.ceil(((date - yearStart) / 86400000 + 1) / 7);
  return `${date.getUTCFullYear()}-W${String(week).padStart(2, "0")}`;
}

// Buckets rows down to one point per day/week/month, keeping the last
// (most recent) row seen in each bucket -- rows are chronologically
// ascending, per trends_log.py's append-only ordering.
export function aggregateByGranularity(rows, granularity) {
  if (granularity === "day" || !rows.length) return rows;
  const keyFn = granularity === "week"
    ? (r) => isoWeekKey(r.as_of_date)
    : (r) => r.as_of_date.slice(0, 7);
  const buckets = new Map();
  for (const r of rows) buckets.set(keyFn(r), r);
  return Array.from(buckets.values());
}

const WEEKDAY_ABBR = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
function weekdayOfStr(s) {
  const [y, m, d] = parseYmd(s);
  return new Date(Date.UTC(y, m - 1, d)).getUTCDay();
}
// The Monday on or before the date.
function weekStartStr(s) { return addDaysStr(s, -((weekdayOfStr(s) + 6) % 7)); }

// Full, unambiguous text for a point -- used by tooltips and the screen-reader table (the axis
// shows shorter text, see xAxisLabels): a day, the week starting on a Monday, or a month.
export function labelForDate(dateStr, granularity) {
  if (!parseYmd(dateStr)) return String(dateStr);
  const [y, m, d] = parseYmd(dateStr);
  if (granularity === "month") return `${MONTH_ABBR[m - 1]} ${y}`;
  if (granularity === "week") return `Week of ${fmtMonthDay(weekStartStr(dateStr), true)}`;
  return `${WEEKDAY_ABBR[weekdayOfStr(dateStr)]}, ${MONTH_ABBR[m - 1]} ${d}, ${y}`;
}

export function dataTableFallbackHtml(caption, columnHeaders, rows) {
  // UX-102: an accessible, screen-reader-visible fallback for the SVG
  // chart above it -- visually hidden (not display:none, which most
  // screen readers also skip), so a sighted keyboard user tabbing past it
  // isn't confused by a chart with no visible label either.
  const head = columnHeaders.map(h => `<th>${escSvg(h)}</th>`).join("");
  const body = rows.map(cells =>
    `<tr>${cells.map(c => `<td>${escSvg(c)}</td>`).join("")}</tr>`).join("");
  return `<table class="visually-hidden"><caption>${escSvg(caption)}</caption>` +
    `<thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

// "Nice" axis bounds a little beyond the data (not anchored at zero): pads
// the data range by ~8% each side, then snaps to a round tick step so the
// gridline labels read as clean numbers.
export function niceRange(min, max, tickTarget) {
  tickTarget = tickTarget || 4;
  if (!(max > min)) {
    const pad = Math.abs(max) * 0.05 || 1;
    min -= pad; max += pad;
  } else {
    const pad = (max - min) * 0.08;
    min -= pad; max += pad;
  }
  const rough = (max - min) / tickTarget;
  const mag = Math.pow(10, Math.floor(Math.log10(rough)));
  const norm = rough / mag;
  const step = (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 5 ? 5 : 10) * mag;
  const lo = Math.floor(min / step) * step;
  const hi = Math.ceil(max / step) * step;
  const ticks = [];
  for (let v = lo; v <= hi + step / 1e6; v += step) ticks.push(Math.round(v / step) * step);
  return { min: ticks[0], max: ticks[ticks.length - 1], ticks };
}

// ---- x-axis labels for a fitted line chart (design 2.6) ---------------------------------
// Which points get a label, and how it reads, depends on the granularity rather than on "every
// Nth point". Points carry `date` ("YYYY-MM-DD"); a point without one is labelled by its `label`
// text and thinned by measurement alone. Returns [{i, x, width, text, sub, year, lines}] oldest
// first, x = offset from the left edge of the plot. Label width is estimated at ~6 px per
// character (10 px type) plus 10 px padding; labels are kept greedily from the newest point
// backward, so the newest is always labelled and none overlap.
const AXIS_CHAR_PX = 6, AXIS_LABEL_PAD = 10;
export function xAxisLabels(points, opts) {
  opts = opts || {};
  const n = points.length;
  if (!n) return [];
  const plotWidth = opts.plotWidth > 0 ? opts.plotWidth : 470;
  const narrow = opts.narrow !== undefined ? !!opts.narrow : plotWidth < 420;
  const gran = opts.granularity;
  const last = n - 1;
  const xOf = (i) => (n > 1 ? (i * plotWidth) / (n - 1) : 0);
  const dated = points.every((p) => p && parseYmd(p.date));
  const cands = [];
  const add = (i, text, sub, year, month) => cands.push({ i, text, sub: sub || "", year: year || "", month: month || 0 });
  if (!dated) {
    points.forEach((p, i) => add(i, String(p.label)));
  } else if (gran === "week") {
    // week-start text; the first week of each month, plus the newest
    let prevKey = "";
    points.forEach((p, i) => {
      const ws = weekStartStr(p.date), [y, m, d] = parseYmd(ws), key = ws.slice(0, 7);
      if (key !== prevKey || i === last) add(i, narrow ? MONTH_ABBR[m - 1] : `${MONTH_ABBR[m - 1]} ${d}`, "", String(y), m);
      prevKey = key;
    });
  } else if (gran === "month") {
    points.forEach((p, i) => {
      const [y, m] = parseYmd(p.date);
      add(i, narrow ? MONTH_ABBR[m - 1][0] : MONTH_ABBR[m - 1], "", String(y), m);
    });
  } else {
    // day: Mondays plus the newest; with 14 points or fewer every day is a candidate, with a
    // weekday initial underneath
    const few = n <= 14;
    points.forEach((p, i) => {
      const [y, m, d] = parseYmd(p.date), dow = weekdayOfStr(p.date);
      if (few || dow === 1 || i === last) add(i, narrow ? String(d) : `${MONTH_ABBR[m - 1]} ${d}`, few && !narrow ? "SMTWTFS"[dow] : "", String(y), m);
    });
  }
  const widthOf = (c) => Math.max(c.text.length, c.sub.length, c.year ? 4 : 0) * AXIS_CHAR_PX + AXIS_LABEL_PAD;
  const greedy = (list) => {
    const kept = [];
    for (let k = list.length - 1; k >= 0; k--) {
      const x = xOf(list[k].i), width = widthOf(list[k]);
      if (kept.every((o) => Math.abs(o.x - x) >= (o.width + width) / 2)) kept.push({ ...list[k], x, width });
    }
    return kept.reverse();
  };
  let kept = greedy(cands);
  // Months: every month if they fit, otherwise quarter starts (Jan/Apr/Jul/Oct) plus the newest.
  if (dated && gran === "month" && kept.length < cands.length) {
    kept = greedy(cands.filter((c) => c.month % 3 === 1 || c.i === last));
  }
  // Narrow cards aim for about three labels.
  if (narrow && kept.length > 3) {
    const every = Math.ceil(kept.length / 3);
    kept = kept.filter((_, idx) => (kept.length - 1 - idx) % every === 0);
  }
  // Year line under the first label and wherever the year changes.
  let prevYear = "";
  return kept.map((c) => {
    const year = c.year && c.year !== prevYear ? c.year : "";
    if (c.year) prevYear = c.year;
    return { i: c.i, x: c.x, width: c.width, text: c.text, sub: c.sub, year, lines: [c.text, c.sub, year].filter(Boolean) };
  });
}

// Line chart drawn at the card's measured width (opts.width; 560 when unknown) so it never
// scrolls: points are spaced evenly across the plot and the x-axis labels do the work of keeping
// it readable (see xAxisLabels). opts.granularity ("day"|"week"|"month") picks the label style;
// points are {label, value, date}: `label` is the full text for the tooltip and the
// screen-reader table, `date` ("YYYY-MM-DD") drives the axis labels.
export function lineChartSvg(points, opts) {
  opts = opts || {};
  const h = 216, padL = 56, padR = 34, padT = 16, padB = 44;
  const label = (opts.title || "Chart") + ", line chart";
  if (!points.length) return '<div class="empty">No data yet for this range.</div>';
  const values = points.map(p => p.value).filter(v => v !== null && v !== undefined);
  if (!values.length) return '<div class="empty">No data yet for this range.</div>';
  const range = niceRange(Math.min(...values), Math.max(...values));
  const min = range.min, max = range.max;
  const w = opts.width > 0 ? Math.max(160, Math.round(opts.width)) : 560;
  const plotW = w - padL - padR, plotH = h - padT - padB;
  const xStep = points.length > 1 ? plotW / (points.length - 1) : 0;
  const x = i => padL + i * xStep;
  const y = v => padT + plotH - ((v - min) / (max - min || 1)) * plotH;
  const color = opts.color || '#2563eb';
  // A missing value breaks the line (a new "M") rather than dropping to $0.
  let pen = false;
  const path = points.map((p, i) => {
    if (p.value === null || p.value === undefined) { pen = false; return ""; }
    const cmd = pen ? "L" : "M";
    pen = true;
    return `${cmd}${x(i)},${y(p.value)}`;
  }).filter(Boolean).join(" ");

  // Y-axis: gridlines and value labels (plain SVG text).
  let grid = "";
  for (const v of range.ticks) {
    const yy = y(v);
    grid += `<line x1="${padL}" y1="${yy}" x2="${w - padR}" y2="${yy}" stroke="#e5e5e5" stroke-width="1"/>` +
      `<text x="${padL - 6}" y="${yy + 3}" text-anchor="end" style="font-size:10px">${escSvg(fmtMoney(v))}</text>`;
  }

  // X-axis: scope-aware labels, each with a faint vertical tick at its point.
  let xAxis = "";
  for (const lab of xAxisLabels(points, { granularity: opts.granularity, plotWidth: plotW })) {
    const lx = padL + lab.x;
    xAxis += `<line class="x-tick" x1="${lx}" y1="${padT}" x2="${lx}" y2="${h - padB + 4}" stroke="currentColor" stroke-opacity=".12" stroke-width="1"/>`;
    lab.lines.forEach((line, k) => {
      xAxis += `<text x="${lx}" y="${h - padB + 16 + k * 12}" text-anchor="middle" style="font-size:10px">${escSvg(line)}</text>`;
    });
  }

  // One hover/keyboard target per point, with a tooltip giving the full date and value. Dots
  // shrink above 40 points and are invisible (but still targets) above 90.
  const n = points.length, hidden = n > 90, r = n > 40 ? 2 : 3;
  let dots = "";
  // Roving tabindex: only the newest point is a tab stop; arrow keys move between points.
  let lastShown = -1;
  points.forEach((p, i) => { if (p.value !== null && p.value !== undefined) lastShown = i; });
  points.forEach((p, i) => {
    if (p.value === null || p.value === undefined) return;
    // opts.interactive: dots are keyboard-focusable and carry their index so the
    // page can show a rollover (see rolloverModel) on hover or focus.
    const focus = opts.interactive
      ? ` tabindex="${i === lastShown ? 0 : -1}" data-i="${i}" role="img" aria-label="${escSvg(p.label)}: ${escSvg(fmtMoney(p.value))}"` : "";
    const look = hidden ? `r="4" fill="${color}" fill-opacity="0" class="chart-dot chart-dot-hit"` : `r="${r}" fill="${color}" class="chart-dot"`;
    dots += `<circle cx="${x(i)}" cy="${y(p.value)}" ${look}${focus}>` +
      `<title>${escSvg(p.label)}: ${escSvg(fmtMoney(p.value))}</title></circle>`;
  });

  const svg = `<svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" style="display:block;max-width:100%;height:auto" role="img" aria-label="${escSvg(label)}">
    ${grid}
    <line x1="${padL}" y1="${padT}" x2="${padL}" y2="${h - padB}" stroke="#999" stroke-width="1"/>
    <line x1="${padL}" y1="${h - padB}" x2="${w - padR}" y2="${h - padB}" stroke="#999" stroke-width="1"/>
    ${xAxis}
    <path d="${path}" fill="none" stroke="${color}" stroke-width="2"/>
    ${dots}
  </svg>`;
  return svg + dataTableFallbackHtml(label, ["Date", "Value"], points.map(p => [p.label, fmtMoney(p.value)]));
}

// Rows for the YTD-expenses chart. Level 1 (Tracking Type) is what the bars
// show. Rolling over a bar lists its categories (`categories`); rolling over a
// category lists its merchants. `hierarchy` is
// {trackingType: {group: {category: {merchant: amount}}}}.
function sumLeaves(node) {
  return typeof node === "number" ? node : Object.values(node).reduce((t, v) => t + sumLeaves(v), 0);
}

// The three spending markers (design §2.5): same dates one year earlier, the annual budget
// prorated to the window, and the end year's whole annual budget. Each has its own shape, so
// colour never carries the meaning alone. The page sets the colours as CSS custom properties
// (index.html :root, with dark overrides); light/dark here are those values, used as var()
// fallbacks and by the contrast test. The period and full-year colours were moved from the
// design's #ea580c/#c026d3 (light) and #fb923c/#e879f9 (dark), keeping hue and saturation, just
// far enough in lightness to reach 3:1 against both the bar blue and the card background.
export const BAR_BLUE = "#2563eb";
export const SPEND_MARKERS = [
  { key: "prior", cls: "mk-prior", cssVar: "--mk-prior", light: "#111827", dark: "#f3f4f6", width: 2.5, dash: null, label: "Same period last year" },
  { key: "budget", cls: "mk-period", cssVar: "--mk-period", light: "#ea580c", dark: "#fcb77d", width: 3.5, dash: null, label: "Budget for this period" },
  { key: "fullYear", cls: "mk-full", cssVar: "--mk-full", light: "#c026d3", dark: "#f1affb", width: 2.5, dash: "3 2", label: "Full-year budget" },
];
// The full-year budget marker is optional (the Spending card's checkbox). Defaults to shown so the pure
// helpers behave as before when a page never calls the setter.
let showFullYear = true;
export function setShowFullYear(on) { showFullYear = !!on; }
export const fullYearDefault = scope => scope === "ytd";
const activeMarkers = () => SPEND_MARKERS.filter(m => m.key !== "fullYear" || showFullYear);
const markerColor = m => `var(${m.cssVar}, ${m.light})`;
const markerStyle = m => `stroke:${markerColor(m)};stroke-width:${m.width}px${m.dash ? `;stroke-dasharray:${m.dash}` : ""}`;
// Each tick sits on a thin card-coloured outline (OUTLINE_PX each side) so it stands out against the blue bar
// whatever its own colour; the outline is drawn first, with the same dash pattern.
export const OUTLINE_PX = 1;
const outlineStyle = m => `stroke:var(--card-bg, #fff);stroke-width:${m.width + 2 * OUTLINE_PX}px${m.dash ? `;stroke-dasharray:${m.dash}` : ""}`;
// When the prorated and full-year budgets are within 1% the full-year tick shifts 1px so both show.
export function fullYearNudge(meta) {
  const b = meta && meta.budget, f = meta && meta.fullYear;
  return b != null && f != null && Math.abs(f - b) <= 0.01 * Math.max(Math.abs(f), Math.abs(b), 1e-9) ? 1 : 0;
}

// Arguments after `hierarchy` are optional maps for the three markers (older log rows have none):
// priorByType {type: amount}, budgetByType {type: amount} (prorated to the window), priorDetail
// {type: {group: {category: {prior, merchants: {name: amount}}}}}, budgetByCategory
// {type: {category: amount}}, and fullYearByType / fullYearByCategory (the end year's whole
// annual budget, same shapes). Each row and category carries {prior, budget, fullYear}.
export function buildHierarchyRows(hierarchy, priorByType, budgetByType, priorDetail, budgetByCategory, fullYearByType, fullYearByCategory) {
  const pick = (map, ...keys) => {
    let node = map;
    for (const k of keys) { if (node == null) return null; node = node[k]; }
    return node != null ? node : null;
  };
  const rows = [];
  for (const [name, groups] of Object.entries(hierarchy || {})) {
    const categories = [];
    for (const [group, cats] of Object.entries(groups)) {
      for (const [cat, merchants] of Object.entries(cats)) {
        const value = sumLeaves(merchants);
        if (Math.abs(value) < 0.005) continue;
        const priorCat = pick(priorDetail, name, group, cat);
        const priorMerchants = (priorCat && priorCat.merchants) || {};
        categories.push({
          name: cat, group, value,
          prior: priorCat && priorCat.prior != null ? priorCat.prior : null,
          budget: pick(budgetByCategory, name, cat),
          fullYear: pick(fullYearByCategory, name, cat),
          // Merchants have no budget; prior-year shows only for a merchant that also appears last year.
          merchants: Object.entries(merchants).filter(e => Math.abs(e[1]) > 0.005).sort((a, b) => b[1] - a[1])
            .map(([m, v]) => priorCat ? [m, v, { prior: priorMerchants[m] != null ? priorMerchants[m] : null }] : [m, v]),
        });
      }
    }
    categories.sort((a, b) => b.value - a.value);
    const amount = categories.reduce((t, c) => t + c.value, 0);
    if (amount > 0.005) rows.push({ name, amount, kind: "category", detailTitle: name, categories,
      prior: pick(priorByType, name), budget: pick(budgetByType, name), fullYear: pick(fullYearByType, name) });
  }
  rows.sort((a, b) => b.amount - a.amount);
  const total = rows.reduce((t, r) => t + r.amount, 0);
  // Totals come from the full maps, not just the visible rows: a type budgeted but not yet spent still counts.
  const sumMarker = map => (map && Object.keys(map).length ? Object.values(map).reduce((t, v) => t + v, 0) : null);
  return {
    total, rows,
    totalMarkers: { prior: sumMarker(priorByType), budget: sumMarker(budgetByType), fullYear: sumMarker(fullYearByType) },
    totalDetail: { detailTitle: "Total - By Tracking Type", detail: rows.map(r => [r.name, r.amount, { prior: r.prior, budget: r.budget, fullYear: r.fullYear }]) },
  };
}

const markerValues = meta => activeMarkers().map(m => (meta && meta[m.key]) || 0);

// The three marker ticks on a popup bar, same colours and shapes as the Spending bars. `max`
// is the bar scale shared by the popup so ticks never overflow.
function popMarkers(meta, max) {
  if (!meta) return "";
  const nudge = showFullYear ? fullYearNudge(meta) : 0;
  return activeMarkers().map(m => {
    const v = meta[m.key];
    if (v == null) return "";
    const pct = Math.min(100, Math.max(0, (v / max) * 100)).toFixed(1);
    const left = m.key === "fullYear" && nudge ? `calc(${pct}% + 1px)` : `${pct}%`;
    return `<b class="pm ${m.cls}" style="left:${left}" title="${escSvg(m.label)}: ${escSvg(fmtMoney(v))}"></b>`;
  }).join("");
}

// Step-1 popup: a tracking type's categories (each tagged data-cat for the
// step-2 merchant popup), with the type's total.
export function categoryListHtml(title, categories) {
  if (!categories.length) return `<div class="pop-title">${escSvg(title)}</div><div class="empty">No further detail logged.</div>`;
  const total = categories.reduce((t, c) => t + c.value, 0);
  const max = Math.max(...categories.flatMap(c => [c.value, ...markerValues(c)]), 1);
  const body = categories.map((c, i) =>
    `<div class="pop-row pop-cat${c.value < 0 ? " pop-neg" : ""}" data-cat="${i}"><span class="pop-name" title="${escSvg(c.group)}">${escSvg(c.name)}</span>` +
    `<span class="pop-bar"><i style="width:${c.value > 0 ? Math.max(1, (c.value / max) * 100).toFixed(1) : 0}%"></i>${popMarkers(c, max)}</span>` +
    `<span class="pop-val">${escSvg(fmtMoney(c.value))}</span></div>`).join("");
  return `<div class="pop-title">${escSvg(title)} <span class="pop-hint">- hover a category for merchants, click to pin</span></div>${body}` +
    `<div class="pop-total"><span>Total</span><span>${escSvg(fmtMoney(total))}</span></div>`;
}

// Popup body: title, a mini bar chart of up to `maxLines` entries (the
// remainder collapsed into one line), and the level's total.
// opts.indexAttr (e.g. "merchant") gives each real row a data-<name>="<index into detail>" and makes it
// focusable, so the dock can hover/pin it; the collapsed "N more" line gets none.
export function detailPopupHtml(title, detail, maxLines, opts) {
  maxLines = maxLines || Infinity;
  const indexAttr = opts && opts.indexAttr;
  if (!detail.length) return `<div class="pop-title">${escSvg(title)}</div><div class="empty">No further detail logged.</div>`;
  const total = detail.reduce((t, e) => t + e[1], 0);
  let lines = detail.slice(0, maxLines);
  if (detail.length > maxLines) {
    const more = detail.slice(maxLines);
    lines = lines.concat([[`${more.length} more`, more.reduce((t, e) => t + e[1], 0)]]);
  }
  const max = Math.max(...lines.flatMap(e => [e[1], ...markerValues(e[2])]), 1);
  const body = lines.map(([n, v, meta], i) =>
    `<div class="pop-row${v < 0 ? " pop-neg" : ""}"${indexAttr && i < detail.length && i < maxLines ?
      ` data-${indexAttr}="${i}" tabindex="0" role="button" aria-label="${escSvg(n)}: show transactions"` : ""}><span class="pop-name">${escSvg(n)}</span>` +
    `<span class="pop-bar"><i style="width:${v > 0 ? Math.max(1, (v / max) * 100).toFixed(1) : 0}%"></i>${popMarkers(meta, max)}</span>` +
    `<span class="pop-val">${escSvg(fmtMoney(v))}</span></div>`).join("");
  return `<div class="pop-title">${escSvg(title)}</div>${body}` +
    `<div class="pop-total"><span>Total</span><span>${escSvg(fmtMoney(total))}</span></div>`;
}

// entries: [name, amount, meta?] -- meta.kind is "total" (text-only summary
// row, not scaled), "other" (muted bar) or anything else (normal bar). Rows
// with meta carry data-row so the page can attach the detail popup; rows
// without it keep a native <title> tooltip. meta.prior / budget / fullYear draw the markers.
// opts.width: the card's real pixel width, so the chart draws at 1:1 like the line charts (a fixed
// viewBox stretched to the card would scale its text up); without it the chart uses 560 units.
export function barChartSvg(entries, opts) {
  if (!entries.length) return '<div class="empty">No expenses recorded yet.</div>';
  const w = opts && opts.width >= 320 ? Math.floor(opts.width) : 560, barH = 18, gap = 6, padL = 120, padR = 60, padB = 20;
  // Axis fits the longest of spend and the three markers so no marker runs off the plot.
  const max = Math.max(...entries.filter(e => !(e[2] && e[2].kind === "total")).flatMap(e => [e[1], ...markerValues(e[2])]), 1);
  const plotW = w - padL - padR;
  const h = entries.length * (barH + gap) + padB;

  // X-axis (amount scale): a few gridlines/ticks so bar lengths read
  // against a labeled scale, not just their own end-of-bar text.
  const xTickCount = 3;
  let xAxis = "";
  for (let i = 0; i <= xTickCount; i++) {
    const v = (max * i) / xTickCount;
    const xx = padL + (v / max) * plotW;
    xAxis += `<line x1="${xx}" y1="0" x2="${xx}" y2="${h - padB}" stroke="#e5e5e5" stroke-width="1"/>` +
      `<text x="${xx}" y="${h - padB + 14}" text-anchor="middle" style="font-size:10px">${escSvg(fmtMoney(v))}</text>`;
  }

  const markersFor = (meta, y) => {
    if (!meta) return "";
    const nudge = showFullYear ? fullYearNudge(meta) : 0;
    return activeMarkers().map(m => {
      const v = meta[m.key];
      if (v == null) return "";
      const xx = padL + (v / max) * plotW + (m.key === "fullYear" ? nudge : 0);
      return `<line class="mk-outline" x1="${xx}" y1="${y - 2}" x2="${xx}" y2="${y + barH + 2}" style="${outlineStyle(m)}"/>` +
        `<line class="mk ${m.cls}" x1="${xx}" y1="${y - 2}" x2="${xx}" y2="${y + barH + 2}" style="${markerStyle(m)}">` +
        `<title>${escSvg(m.label)}: ${escSvg(fmtMoney(v))}</title></line>`;
    }).join("");
  };
  // The row label is the only thing that opens the breakdown panels: a focusable button (Enter/Space pins),
  // with its own hit area so the ticks and the bar never trigger anything.
  const labelFor = (name, y, bold, meta) => {
    const text = `<text x="0" y="${y + barH - 5}" style="font-size:11px${bold ? ";font-weight:600" : ""}">${escSvg(name)}</text>`;
    if (!meta) return text;
    return `<g class="row-label" tabindex="0" role="button" aria-label="${escSvg(name)}: show breakdown">` +
      `<rect x="0" y="${y - 2}" width="${padL - 6}" height="${barH + 4}" fill="transparent"/>${text}</g>`;
  };
  const bars = entries.map((e, i) => {
    const y = i * (barH + gap);
    const meta = e[2];
    const row = meta ? ` data-row="${i}"` : "";
    const hit = `<rect x="0" y="${y - 2}" width="${w}" height="${barH + 4}" fill="transparent"/>`;
    if (meta && meta.kind === "total") {
      return `<g${row} class="bar-row">${hit}` +
        `${labelFor(e[0], y, true, meta)}` +
        `<text x="${padL + 6}" y="${y + barH - 5}" style="font-size:11px;font-weight:600">${escSvg(fmtMoney(e[1]))}</text></g>`;
    }
    const bw = (e[1] / max) * plotW;
    const fill = meta && meta.kind === "other" ? "#94a3b8" : BAR_BLUE;
    const tip = meta ? "" : `<title>${escSvg(e[0])}: ${escSvg(fmtMoney(e[1]))}</title>`;
    return `<g${row} class="bar-row">${hit}` +
      `${labelFor(e[0], y, false, meta)}` +
      `<rect x="${padL}" y="${y}" width="${bw}" height="${barH}" fill="${fill}" rx="3">${tip}</rect>` + markersFor(meta, y) +
      `<text x="${padL + bw + 6}" y="${y + barH - 5}" style="font-size:11px">${escSvg(fmtMoney(e[1]))}</text></g>`;
  }).join("");
  // Legend: one entry per marker present, each with a swatch in the marker's own shape.
  const shown = activeMarkers().filter(m => entries.some(e => e[2] && e[2][m.key] != null));
  const legend = shown.length ? `<div class="bar-legend" style="font-size:12px">` +
    shown.map(m => `<span class="mk-key"><svg class="mk-swatch" width="10" height="14" viewBox="0 0 10 14" aria-hidden="true">` +
      `<line class="${m.cls}" x1="5" y1="0" x2="5" y2="14" style="${markerStyle(m)}"/></svg> ${escSvg(m.label)}</span>`).join(" ") + `</div>` : "";
  const svg = legend + `<svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}" style="width:100%;max-width:100%;height:auto" role="img" aria-label="Spending, bar chart">
    ${xAxis}
    <line x1="${padL}" y1="0" x2="${padL}" y2="${h - padB}" stroke="#999" stroke-width="1"/>
    ${bars}
  </svg>`;
  const money = v => (v == null ? "-" : fmtMoney(v));
  return svg + dataTableFallbackHtml("Spending", ["Tracking type", "Amount", ...shown.map(m => m.label)],
    entries.map(e => [e[0], fmtMoney(e[1]), ...shown.map(m => money(e[2] && e[2][m.key]))]));
}

// --- Spending card (Trends Phase 5): window data from /api/spending, YTD snapshot fallback ---

export function spendingUrl(range) {
  return `/api/spending?from=${encodeURIComponent(range.from)}&to=${encodeURIComponent(range.to)}`;
}

// The card's model from an /api/spending response. A null `prior` (window before the data
// starts) leaves the same-period marker off rather than drawing it at $0.
export function spendingModelFromWindow(resp) {
  if (!resp || !resp.hierarchy) return null;
  const prior = resp.prior, budget = resp.budget || {}, full = resp.full_year_budget || {};
  return buildHierarchyRows(resp.hierarchy, prior ? prior.by_type : null, budget.by_type, prior ? prior.detail : null,
    budget.by_category, full.by_type, full.by_category);
}

// Fallback when the window can't be loaded: the latest logged YTD snapshot. Its budget is the
// whole year's, so it draws as the full-year marker; the snapshot has no prorated budget.
export function spendingModelFromSnapshot(latest) {
  if (!latest || !latest.ytd_expense_hierarchy) return null;
  return buildHierarchyRows(latest.ytd_expense_hierarchy, latest.ytd_expense_prior_year, null, latest.ytd_expense_prior_detail,
    null, latest.annual_budget_by_tracking_type, latest.annual_budget_by_category);
}

// The transactions behind one merchant line (GET /api/spending/transactions).
export function transactionsUrl(range, { type, group, category, merchant }) {
  const q = (v) => encodeURIComponent(v);
  return `/api/spending/transactions?from=${q(range.from)}&to=${q(range.to)}&type=${q(type)}&group=${q(group)}` +
    `&category=${q(category)}&merchant=${q(merchant)}`;
}

// Date | Account | Merchant | Amount, newest first as served; notes on a second muted line (full text in title).
// Every interpolated value is user-imported data and goes through escSvg.
export function transactionsPanelHtml(title, payload) {
  const txns = (payload && payload.transactions) || [];
  if (!txns.length) return `<div class="pop-title">${escSvg(title)}</div><div class="empty">No transactions found.</div>`;
  const rows = txns.map(t =>
    `<tr class="${t.amount < 0 ? "pop-neg" : ""}"><td>${escSvg(t.date)}</td><td>${escSvg(t.account)}</td><td>${escSvg(t.merchant)}` +
    `${t.notes ? `<div class="txn-notes" title="${escSvg(t.notes)}">${escSvg(t.notes)}</div>` : ""}</td>` +
    `<td class="pop-val">${escSvg(fmtMoney(t.amount))}</td></tr>`).join("");
  return `<div class="pop-title">${escSvg(title)}</div>` +
    `<table class="txn-table"><thead><tr><th scope="col">Date</th><th scope="col">Account</th><th scope="col">Merchant</th>` +
    `<th scope="col" class="pop-val">Amount</th></tr></thead><tbody>${rows}</tbody></table>` +
    `<div class="pop-total"><span>Total</span><span>${escSvg(fmtMoney(payload.total))}</span></div>`;
}

// Drops out-of-order responses: only the most recently started request may draw.
export function latestOnly() {
  let n = 0;
  return { start: () => ++n, isCurrent: id => id === n };
}

// The note under the Spending card, describing the markers for the period shown.
export function spendingNoteText(resp, label) {
  const lead = "Totals follow the Spending Analysis mapping and include taxes.";
  const tail = "Hover a row label to see its categories (click to pin), then hover a category to see its merchants.";
  if (!resp) {
    return `${lead} Markers: same dates last year, and the full-year budget. ${tail}`;
  }
  const days = resp.window && resp.window.days;
  const prior = resp.prior && resp.prior.window
    ? `same period last year (${fmtMonthDay(resp.prior.window.from, true)} – ${fmtMonthDay(resp.prior.window.to, true)})`
    : "same period last year (not shown: it falls before the first imported transactions)";
  const year = resp.full_year_budget && resp.full_year_budget.year;
  return `${lead} Markers for ${label || "this period"}: ${prior}; budget for this period (the annual budget prorated to these ${days} day${days === 1 ? "" : "s"}); ` +
    `full-year budget (the whole ${year} annual budget). ${tail}`;
}

// Hover/focus rollover for the Net worth and Investments line charts: the
// account subtotals at one log entry. `kind` is "networth" or "investments".
// Accounts come from holdings.by_account (investments) and, for net worth,
// net_worth.other_accounts (cash, cards, loans; logged since 347b) grouped by
// role with a subtotal each. Net worth adds the plan-level lines from
// net_worth. Entries lacking account detail return an aggregate-only model
// (groups empty) so the page still shows the total.
// Accounts whose value is zero are omitted (a closed account or one not yet opened adds only noise).
const ZERO_EPS = 0.005;
export function isNonZero(v) { return Math.abs(Number(v) || 0) >= ZERO_EPS; }

function groupByRole(accounts) {
  const byRole = new Map();
  for (const a of accounts) {
    if (!isNonZero(a.value)) continue;
    if (!byRole.has(a.role)) byRole.set(a.role, []);
    byRole.get(a.role).push({ name: a.name, value: a.value });
  }
  return Array.from(byRole, ([role, items]) => ({
    role, items: items.sort((p, q) => Math.abs(q.value) - Math.abs(p.value)),
    subtotal: items.reduce((t, i) => t + i.value, 0),
  }));
}

export function rolloverModel(row, kind) {
  if (!row) return null;
  const h = row.holdings || {}, nw = row.net_worth || {};
  const invAccounts = (h.by_account || []).map(a => ({
    name: a.account, role: a.role || "Investment", value: a.current_value || 0,
  }));
  if (kind === "investments") {
    return { title: "Investments", date: row.as_of_date, total: h.current_value ?? null, groups: groupByRole(invAccounts), lines: [] };
  }
  const other = Array.isArray(nw.other_accounts) ? nw.other_accounts : [];
  // Liability roles are shown negative so the groups add toward the total.
  const otherAccounts = other.map(a => ({ name: a.account, role: a.role, value: a.liability ? -a.value : a.value }));
  const accountLiabilities = other.reduce((t, a) => t + (a.liability ? a.value : 0), 0);
  const lines = [];
  if (nw.home != null) lines.push(["Home", nw.home]);
  if (nw.other_assets != null) lines.push(["Other assets (plan)", nw.other_assets]);
  // mortgage is 0 when a Monarch mortgage account replaced the plan's (it is listed with the accounts above).
  if (isNonZero(nw.mortgage)) lines.push(["Mortgage", -nw.mortgage]);
  // nw.liabilities = account liabilities + liabilities file + mortgage. Cards/loans are already listed
  // under their role above and the mortgage has its own line, so show only the remainder.
  if (nw.liabilities != null) {
    const rest = nw.liabilities - (nw.mortgage || 0) - accountLiabilities;
    if (Math.abs(rest) >= 0.5) lines.push(["Other liabilities", -rest]);
  }
  return {
    title: "Net Worth", date: row.as_of_date, total: nw.total ?? null,
    groups: groupByRole(invAccounts.concat(otherAccounts)), lines,
  };
}

export function rolloverHtml(model) {
  if (!model) return "";
  const head = `<div class="pop-title">${escSvg(model.title)} - ${escSvg(model.date)}</div>`;
  const total = `<div class="pop-total"><span>${escSvg(model.title)}</span><span>${escSvg(fmtMoney(model.total))}</span></div>`;
  if (!model.groups.length) {
    return head + total + `<div class="pop-hint">${escSvg(model.emptyNote || "No per-account detail was logged for this date.")}</div>`;
  }
  const groups = model.groups.map(g =>
    `<div class="pop-group"><strong>${escSvg(g.role)}</strong>` +
    g.items.map(i => `<div class="pop-row${i.value < 0 ? " pop-neg" : ""}"><span class="pop-name">${escSvg(i.name)}</span><span></span><span class="pop-val">${escSvg(fmtMoney(i.value))}</span></div>`).join("") +
    `<div class="pop-row pop-sub"><span class="pop-name">Subtotal</span><span></span><span class="pop-val">${escSvg(fmtMoney(g.subtotal))}</span></div></div>`).join("");
  const lines = model.lines.map(([n, v]) =>
    `<div class="pop-row${v < 0 ? " pop-neg" : ""}"><span class="pop-name">${escSvg(n)}</span><span></span><span class="pop-val">${escSvg(fmtMoney(v))}</span></div>`).join("");
  return head + groups + lines + total;
}

// Rows for the investment-flows chart, from a log entry's
// investment_net_flows_by_account ({account: {to_checking, from_checking, net}}).
// Returns null when the entry predates the field (no backfill, decision D3) so
// the page can show an empty state. net > 0 is a net withdrawal to checking,
// net < 0 a net contribution from checking. Largest magnitude first.
export function investmentFlowRows(flows) {
  if (!flows || typeof flows !== "object") return null;
  const rows = Object.entries(flows).map(([name, f]) => ({
    name, net: f.net || 0, toChecking: f.to_checking || 0, fromChecking: f.from_checking || 0,
  }));
  rows.sort((a, b) => Math.abs(b.net) - Math.abs(a.net));
  const total = rows.reduce((t, r) => t + r.net, 0);
  return { rows, total };
}

// Warning block for near-match investment-to-investment pairs (amounts within $100,
// not equal) awaiting the user's decision. `items` is the log entry's
// passthrough_review; each button carries the pair key for the decision POST.
export function passthroughReviewHtml(items) {
  if (!Array.isArray(items) || !items.length) return "";
  const rows = items.map(it => {
    const w = it.withdrawal || {}, d = it.deposit || {};
    return `<div class="review-item" data-key="${escSvg(it.key)}">` +
      `<span>${escSvg(w.date)} ${escSvg(fmtMoney(w.amount))} out of ${escSvg(w.account)} and ${escSvg(d.date)} ${escSvg(fmtMoney(d.amount))} into ${escSvg(d.account)} ` +
      `(differ by ${escSvg(fmtMoney(it.difference))}). Same money moving between investment accounts?</span> ` +
      `<button type="button" data-decision="approve">Yes, exclude</button> ` +
      `<button type="button" data-decision="deny">No, count both</button></div>`;
  }).join("");
  return `<div class="review-warning" role="alert"><strong>Possible investment-to-investment transfers.</strong> ` +
    `Until you decide, both legs still count as a withdrawal and a contribution.${rows}</div>`;
}

// Signed horizontal bars around a zero line: withdrawals extend right, contributions
// left. Each bar's tooltip gives the to/from-checking split; the last row is the total.
export function flowBarChartSvg(model) {
  if (!model || !model.rows.length) return '<div class="empty">No investment transfers recorded yet this year.</div>';
  const w = 560, barH = 18, gap = 6, padL = 150, padR = 70, padB = 20;
  const entries = model.rows.concat([{ name: "Total", net: model.total, total: true }]);
  const maxAbs = Math.max(...entries.map(e => Math.abs(e.net)), 1);
  const neg = entries.some(e => e.net < 0), pos = entries.some(e => e.net > 0);
  const plotW = w - padL - padR;
  // Zero line sits where the negative and positive extents meet.
  const negW = neg ? (pos ? plotW / 2 : plotW) : 0;
  const zeroX = padL + negW;
  const scale = (neg && pos ? plotW / 2 : plotW) / maxAbs;
  const h = entries.length * (barH + gap) + padB;
  const bars = entries.map((e, i) => {
    const y = i * (barH + gap);
    const bw = Math.abs(e.net) * scale;
    const x = e.net < 0 ? zeroX - bw : zeroX;
    const fill = e.total ? "#475569" : e.net < 0 ? "#0d9488" : "#d97706";
    const tipText = e.total ? `Total: ${fmtMoney(e.net)}`
      : `${e.name}: net ${fmtMoney(e.net)} (withdrawn ${fmtMoney(e.toChecking)}, contributed ${fmtMoney(e.fromChecking)})`;
    // Negative bars label on the far side of the zero line so the text never lands on the account names.
    const labelX = e.net < 0 ? zeroX + 6 : x + bw + 6;
    const anchor = "start";
    return `<g class="bar-row" tabindex="0" role="img" aria-label="${escSvg(tipText)}">` +
      `<rect x="0" y="${y - 2}" width="${w}" height="${barH + 4}" fill="transparent"/>` +
      `<text x="0" y="${y + barH - 5}"${e.total ? ' style="font-weight:600"' : ""}>${escSvg(e.name)}</text>` +
      `<rect x="${x}" y="${y}" width="${bw}" height="${barH}" fill="${fill}" rx="3"><title>${escSvg(tipText)}</title></rect>` +
      `<text x="${labelX}" y="${y + barH - 5}" text-anchor="${anchor}">${escSvg(fmtMoney(e.net))}</text></g>`;
  }).join("");
  const svg = `<svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}" style="width:100%;max-width:100%;height:auto" role="group" aria-label="YTD net investment flows by account, bar chart">` +
    `<line x1="${zeroX}" y1="0" x2="${zeroX}" y2="${h - padB}" stroke="#999" stroke-width="1"/>` +
    `<text x="${zeroX}" y="${h - padB + 14}" text-anchor="middle" style="font-size:10px">$0</text>${bars}</svg>`;
  return svg + dataTableFallbackHtml("YTD net investment flows by account",
    ["Account", "Net (withdrawal +)", "Withdrawn", "Contributed"],
    model.rows.map(r => [r.name, fmtMoney(r.net)]).map((row, i) => row.concat([fmtMoney(model.rows[i].toChecking), fmtMoney(model.rows[i].fromChecking)]))
      .concat([["Total", fmtMoney(model.total), "", ""]]));
}

// ---------------------------------------------------------------------------
// imported daily balances (balances payload from /api/balances) -- Net worth, Holdings.
// `balances` = {dates, series: {account_key: [value per date]}, accounts: [{account_key,
// display_name, type, active, enabled: {networth, holdings, flows}, ...}]}. Totals are
// summed here from the toggles so switching an account on/off needs no server round trip.
// ---------------------------------------------------------------------------

function round2(v) { return Math.round(v * 100) / 100; }

export function hasMonarchBalances(balances) {
  return !!balances && Array.isArray(balances.dates) && balances.dates.length > 0
    && !!balances.series && Array.isArray(balances.accounts);
}

function enabledKeys(balances, chart) {
  return balances.accounts.filter(a => a.enabled && a.enabled[chart]).map(a => a.account_key);
}

// Log-entry-shaped rows, so the existing timeframe filter / granularity / line chart code
// works unchanged. Import dates use imported totals; dates imported doesn't cover keep the
// plan-derived log entry (source "plan", `plan` holds it for the rollover).
export function buildMonarchRows(balances, history) {
  if (!hasMonarchBalances(balances)) return null;
  const nwKeys = enabledKeys(balances, "networth"), hKeys = enabledKeys(balances, "holdings");
  const total = (keys, i) => keys.reduce((t, k) => t + ((balances.series[k] || [])[i] || 0), 0);
  const rows = balances.dates.map((d, i) => ({
    as_of_date: d, source: "monarch", idx: i,
    net_worth: { total: round2(total(nwKeys, i)) }, holdings: { current_value: round2(total(hKeys, i)) },
  }));
  const covered = new Set(balances.dates);
  for (const e of history || []) {
    if (covered.has(e.as_of_date)) continue;
    rows.push({
      as_of_date: e.as_of_date, source: "plan", idx: -1, plan: e,
      net_worth: { total: e.net_worth ? e.net_worth.total : null },
      holdings: { current_value: e.holdings ? e.holdings.current_value : null },
    });
  }
  rows.sort((a, b) => (a.as_of_date < b.as_of_date ? -1 : a.as_of_date > b.as_of_date ? 1 : 0));
  return rows;
}

// All time starts here. imported history before this date has only a loan or two linked, so it
// is not a comparable total and it stretches the Y axis; it is cut, not just hidden.
export const ALL_TIME_START = "2025-02-01";

export function truncateAllTime(rows, start = ALL_TIME_START) {
  const kept = rows.filter(r => r.as_of_date >= start);
  return { rows: kept, truncated: kept.length < rows.length };
}

// Rollover for a imported-sourced row: enabled accounts with a non-zero value on that date,
// grouped by account type with subtotals. Plan-sourced rows use the legacy model.
export function monarchRolloverModel(row, balances, kind) {
  if (!row) return null;
  if (row.source !== "monarch") return rolloverModel(row.plan || row, kind);
  const chart = kind === "investments" ? "holdings" : "networth";
  const byType = new Map();
  for (const a of balances.accounts) {
    if (!(a.enabled && a.enabled[chart])) continue;
    const v = (balances.series[a.account_key] || [])[row.idx] || 0;
    if (!isNonZero(v)) continue;
    const type = a.type || "Other";
    if (!byType.has(type)) byType.set(type, []);
    byType.get(type).push({ name: a.display_name, value: v });
  }
  const groups = Array.from(byType, ([role, items]) => ({
    role, items: items.sort((p, q) => Math.abs(q.value) - Math.abs(p.value)),
    subtotal: items.reduce((t, i) => t + i.value, 0),
  })).sort((p, q) => Math.abs(q.subtotal) - Math.abs(p.subtotal));
  return {
    title: chart === "holdings" ? "Liquid Investments and Cash" : "Net Worth", date: row.as_of_date,
    total: chart === "holdings" ? row.holdings.current_value : row.net_worth.total,
    groups, lines: [], emptyNote: "No accounts with a balance are switched on for this date.",
  };
}

// Banner text when the daily imported import is failing or stale; "" when healthy.
export function balancesFreshnessNote(freshness, today) {
  const last = freshness && freshness.last_run, ok = freshness && freshness.last_ok;
  if (!last) return "";
  const now = today ? new Date(today + "T00:00:00") : new Date();
  const ageDays = ok && ok.latest_date ? Math.floor((now - new Date(ok.latest_date + "T00:00:00")) / 86400000) : null;
  if (last.status !== "ok") {
    return `The latest Imported balances import was rejected (${last.detail || "unknown reason"}); showing balances through ${ok && ok.latest_date ? ok.latest_date : "no date"}.`;
  }
  if (ageDays !== null && ageDays > 2) return `Imported balances were last updated ${ok.latest_date}.`;
  return "";
}

// ---- per-chart account toggle popover ----

const TYPE_ORDER = ["Cash", "Investment", "Retirement", "HSA", "Annuity/Pension", "Real estate", "Vehicle", "Loan", "Credit card", "Other"];

function groupAccountsByType(accounts) {
  const groups = new Map();
  for (const a of accounts) {
    const t = a.type || "Other";
    if (!groups.has(t)) groups.set(t, []);
    groups.get(t).push(a);
  }
  const rank = t => { const i = TYPE_ORDER.indexOf(t); return i < 0 ? TYPE_ORDER.length : i; };
  return Array.from(groups).sort((p, q) => rank(p[0]) - rank(q[0]));
}

// showClosed: closed (inactive) accounts are hidden unless the popup's toggle is on. Hidden accounts keep
// their saved selection and are still covered by the All / None / Reset buttons.
export function accountToggleHtml(accounts, chart, title, showClosed = false) {
  const hasClosed = accounts.some(a => !a.active);
  const shown = showClosed ? accounts : accounts.filter(a => a.active);
  const body = groupAccountsByType(shown).map(([type, list]) =>
    `<fieldset class="acct-group"><legend>${escSvg(type)}</legend>` +
    list.map(a => `<label class="acct-item"><input type="checkbox" data-chart="${escSvg(chart)}" data-key="${escSvg(a.account_key)}"${a.enabled && a.enabled[chart] ? " checked" : ""}> ` +
      `<span>${escSvg(a.display_name)}${a.active ? "" : ' <em class="pop-hint">(closed)</em>'}</span></label>`).join("") +
    `</fieldset>`).join("");
  return `<div class="pop-title">${escSvg(title)} - accounts</div>` +
    `<div class="note">Type, match to the plan and Ignore come from the Retirement app's Account Reconciliation page.</div>` +
    `<div class="acct-actions"><button type="button" data-bulk="all" data-chart="${escSvg(chart)}">All</button> ` +
    `<button type="button" data-bulk="none" data-chart="${escSvg(chart)}">None</button> ` +
    `<button type="button" data-bulk="default" data-chart="${escSvg(chart)}">Reset to defaults</button></div>` +
    (hasClosed ? `<label class="acct-closed-toggle"><input type="checkbox" data-show-closed${showClosed ? " checked" : ""}> Show closed accounts</label>` : "") +
    body;
}

// ---- monthly investment flows (payload from /api/flows) ----

export function monthLabel(month) {
  return new Date(`${month}-01T00:00:00`).toLocaleDateString(undefined, { month: "short", year: "numeric" });
}

function monthsBetween(first, last) {
  const out = [];
  let y = Number(first.slice(0, 4)), m = Number(first.slice(5, 7));
  const ly = Number(last.slice(0, 4)), lm = Number(last.slice(5, 7));
  while (y < ly || (y === ly && m <= lm)) {
    out.push(`${String(y).padStart(4, "0")}-${String(m).padStart(2, "0")}`);
    if (++m === 13) { y++; m = 1; }
  }
  return out;
}

// Flow accounts that the Flows toggles include: a flow account tied to registry accounts is
// included when any of them has Flows on; one with no registry match stays included.
export function flowIncludedAccounts(flowAccounts, balances) {
  const byKey = new Map(((balances && balances.accounts) || []).map(a => [a.account_key, a]));
  return (flowAccounts || []).filter(fa => {
    const keys = (fa.account_keys || []).filter(k => byKey.has(k));
    return keys.length ? keys.some(k => byKey.get(k).enabled && byKey.get(k).enabled.flows) : (fa.account_keys && fa.account_keys.length ? !!fa.enabled : true);
  }).map(fa => fa.flow_account);
}

// credits = contributions into investments, debits = withdrawals out of them, net = credits - debits.
export function flowMonthlySeries(monthly, included) {
  const chosen = new Set(included);
  const all = Object.entries(monthly || {}).filter(([a]) => chosen.has(a));
  const months = [...new Set(all.flatMap(([, ms]) => Object.keys(ms)))].sort();
  if (!months.length) return [];
  return monthsBetween(months[0], months[months.length - 1]).map(month => {
    let credits = 0, debits = 0;
    for (const [, ms] of all) { const c = ms[month]; if (c) { credits += c.from_checking || 0; debits += c.to_checking || 0; } }
    return { month, credits: round2(credits), debits: round2(debits), net: round2(credits - debits) };
  });
}

export function flowYtdSummary(series, year) {
  const rows = series.filter(p => p.month.startsWith(`${year}-`));
  const credits = round2(rows.reduce((t, p) => t + p.credits, 0)), debits = round2(rows.reduce((t, p) => t + p.debits, 0));
  return { year, credits, debits, total: round2(credits - debits) };
}

export function fmtMoneySigned(v) {
  if (v === null || v === undefined) return "-";
  return (v < 0 ? "-" : "") + "$" + Math.abs(Number(v)).toLocaleString(undefined, { maximumFractionDigits: 0 });
}

// ---- Investment Net Flows on any time scope (Trends Phase 4) ----
// A point per bucket of the selected scope: {key, date, label, credits, debits, net}. `label` is
// the full text (tooltips, screen-reader table) from labelForDate, so the flows chart reads like
// the other charts; `date` drives the fitted x-axis.
function flowPoint(key, date, granularity, credits, debits) {
  return { key, date, label: labelForDate(date, granularity), credits: round2(credits), debits: round2(debits), net: round2(credits - debits) };
}

// Sums the daily ledger ({account: {"YYYY-MM-DD": {to_checking, from_checking}}}) for the
// included accounts into the scope's buckets: day = every calendar day in [from, to]; week = ISO
// weeks (the same keys and "Week of <Monday>" labels as the other charts); month = calendar
// months. Empty buckets are zero so the line keeps its spacing. An open bound ("" in a Custom
// range) falls back to the first/last day with a flow. No included account with data -> [].
export function flowSeries(daily, included, range, granularity) {
  const chosen = new Set(included || []);
  const all = Object.entries(daily || {}).filter(([a]) => chosen.has(a));
  const days = [...new Set(all.flatMap(([, ds]) => Object.keys(ds)))].sort();
  if (!days.length) return [];
  const from = (range && parseYmd(range.from) && String(range.from).slice(0, 10)) || days[0];
  const to = (range && parseYmd(range.to) && String(range.to).slice(0, 10)) || days[days.length - 1];
  if (from > to) return [];
  const gran = granularity === "week" || granularity === "month" ? granularity : "day";
  const keyOf = gran === "week" ? isoWeekKey : gran === "month" ? (d) => d.slice(0, 7) : (d) => d;
  // Buckets in order, each dated by its first day inside the range (month: the 1st).
  const buckets = new Map();
  for (let d = from; d <= to; d = addDaysStr(d, 1)) {
    const k = keyOf(d);
    if (!buckets.has(k)) buckets.set(k, { date: gran === "month" ? `${k}-01` : d, credits: 0, debits: 0 });
  }
  for (const [, ds] of all) {
    for (const [d, c] of Object.entries(ds)) {
      if (d < from || d > to || !c) continue;
      const b = buckets.get(keyOf(d));
      b.credits += c.from_checking || 0;
      b.debits += c.to_checking || 0;
    }
  }
  return Array.from(buckets, ([k, b]) => flowPoint(k, b.date, gran, b.credits, b.debits));
}

// Fallback for log entries without the daily ledger: the monthly ledger, keeping every whole
// month that overlaps [from, to] (zero-filled), as month points.
export function flowMonthlyRangeSeries(monthly, included, range) {
  const series = flowMonthlySeries(monthly, included);
  if (!series.length) return [];
  const from = range && parseYmd(range.from) ? String(range.from).slice(0, 7) : series[0].month;
  const to = range && parseYmd(range.to) ? String(range.to).slice(0, 7) : series[series.length - 1].month;
  if (from > to) return [];
  const byMonth = new Map(series.map(p => [p.month, p]));
  return monthsBetween(from, to).map(m => {
    const p = byMonth.get(m);
    return flowPoint(m, `${m}-01`, "month", p ? p.credits : 0, p ? p.debits : 0);
  });
}

// Totals for the selected period, labelled with the scope's period text.
export function flowPeriodSummary(points, label) {
  const credits = round2((points || []).reduce((t, p) => t + p.credits, 0));
  const debits = round2((points || []).reduce((t, p) => t + p.debits, 0));
  return { label, credits, debits, total: round2(credits - debits) };
}

// summary = {label, credits, debits, total} (flowPeriodSummary); a legacy {year, ...} reads "YYYY YTD".
export function flowSummaryHtml(summary) {
  if (!summary) return "";
  const heading = summary.label || `${summary.year} YTD`;
  const tile = (label, value, cls) => `<div class="flow-stat ${cls}"><span class="flow-stat-label">${escSvg(label)}</span><span class="flow-stat-value">${escSvg(fmtMoneySigned(value))}</span></div>`;
  return `<div class="flow-summary" role="group" aria-label="Investment flows, ${escSvg(String(heading))}">` +
    `<div class="flow-year">${escSvg(String(heading))}</div>` +
    tile("Credits (into investments)", summary.credits, "flow-credit") +
    tile("Debits (out of investments)", summary.debits, "flow-debit") +
    tile("Total (net contributions)", summary.total, "flow-total") + `</div>`;
}

// Points from flowSeries / flowMonthlyRangeSeries (opts.granularity picks the axis style), or a
// legacy flowMonthlySeries ({month, ...}), which draws as months.
export function flowLineChartSvg(series, opts) {
  opts = opts || {};
  if (!series.length) return '<div class="empty">No investment transfers recorded for the accounts switched on.</div>';
  const legacy = series[0].month !== undefined && series[0].date === undefined;
  const points = legacy
    ? series.map(p => ({ label: monthLabel(p.month), date: `${p.month}-01`, value: p.net }))
    : series.map(p => ({ label: p.label, date: p.date, value: p.net }));
  return lineChartSvg(points, { color: "#0d9488", title: "Net Investment Contributions", granularity: legacy ? "month" : (opts.granularity || "month"), width: opts.width });
}

// What the page does on open (and after a passthrough decision), given GET /api/run-status:
// "poll" a run already in flight, "run" a fresh update, or "skip" when the last run is recent.
// force ignores the freshness window but never starts a second run beside one in flight.
export function updateDecision(status, nowMs, force = false) {
  if (!status) return "run";
  if (status.running) return "poll";
  if (force) return "run";
  const last = status.last_run_at ? Date.parse(status.last_run_at) : NaN;
  if (!Number.isFinite(last)) return "run";
  return (nowMs - last) / 1000 < Number(status.fresh_seconds ?? 900) ? "skip" : "run";
}
