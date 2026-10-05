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
// innerHTML) with no escaping -- a Monarch category containing "&" or "<"
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

export function filterByTimeframe(rows, tf) {
  if (!rows.length) return rows;
  const last = new Date(rows[rows.length - 1].as_of_date);
  let from = null;
  if (tf === "week") { from = new Date(last); from.setDate(from.getDate() - 7); }
  else if (tf === "month") { from = new Date(last); from.setMonth(from.getMonth() - 1); }
  else if (tf === "quarter") { from = new Date(last); from.setMonth(from.getMonth() - 3); }
  else if (tf === "ytd") { from = new Date(last.getFullYear(), 0, 1); }
  else if (tf === "12m") { from = new Date(last); from.setFullYear(from.getFullYear() - 1); }
  else if (tf === "custom") {
    const fromEl = document.getElementById("customFrom");
    const toEl = document.getElementById("customTo");
    const fromVal = fromEl.value ? new Date(fromEl.value) : null;
    const toVal = toEl.value ? new Date(toEl.value) : null;
    return rows.filter(r => {
      const d = new Date(r.as_of_date);
      return (!fromVal || d >= fromVal) && (!toVal || d <= toVal);
    });
  } else {
    return rows; // all time
  }
  return rows.filter(r => new Date(r.as_of_date) >= from);
}

// Granularity requirement: daily points for week/month ranges, weekly
// for quarter, monthly for ytd/12-month/all-time. A custom range has no
// fixed answer, so it's inferred from how many days the range spans.
export function granularityForTimeframe(tf, rows) {
  const fixed = { week: "day", month: "day", quarter: "week", ytd: "month", "12m": "month", all: "month" };
  if (fixed[tf]) return fixed[tf];
  if (!rows || rows.length < 2) return "day";
  const first = new Date(rows[0].as_of_date);
  const last = new Date(rows[rows.length - 1].as_of_date);
  const spanDays = (last - first) / 86400000;
  if (spanDays <= 31) return "day";
  if (spanDays <= 120) return "week";
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

export function labelForDate(dateStr, granularity) {
  if (granularity === "month") {
    return new Date(`${dateStr}T00:00:00`).toLocaleDateString(undefined, { month: "short", year: "numeric" });
  }
  return dateStr.slice(5); // MM-DD
}

export function dataTableFallbackHtml(caption, columnHeaders, rows) {
  // UX-102: an accessible, screen-reader-visible fallback for the SVG
  // chart above it -- visually hidden (not display:none, which most
  // screen readers also skip), so a sighted keyboard user tabbing past it
  // isn't confused by a chart with no visible label either.
  const head = columnHeaders.map(h => `<th>${escSvg(h)}</th>`).join("");
  const body = rows.map(([label, value]) =>
    `<tr><td>${escSvg(label)}</td><td>${escSvg(value)}</td></tr>`).join("");
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

// Line chart wide enough to give each point `pxPerPoint` of room; when that
// exceeds the card, the chart scrolls horizontally (.chart-scroll) with the
// y-axis labels pinned in a sticky overlay so they stay visible.
export function lineChartSvg(points, opts) {
  opts = opts || {};
  const minW = 560, h = 200, padL = 56, padR = 16, padT = 16, padB = 28;
  const pxPerPoint = opts.pxPerPoint || 36;
  const label = (opts.title || "Chart") + ", line chart";
  if (!points.length) return '<div class="empty">No data yet for this range.</div>';
  const values = points.map(p => p.value).filter(v => v !== null && v !== undefined);
  if (!values.length) return '<div class="empty">No data yet for this range.</div>';
  const range = niceRange(Math.min(...values), Math.max(...values));
  const min = range.min, max = range.max;
  const w = Math.max(minW, padL + padR + (points.length - 1) * pxPerPoint);
  const plotW = w - padL - padR, plotH = h - padT - padB;
  const xStep = points.length > 1 ? plotW / (points.length - 1) : 0;
  const x = i => padL + i * xStep;
  const y = v => padT + plotH - ((v - min) / (max - min || 1)) * plotH;
  const path = points.map((p, i) => `${i === 0 ? "M" : "L"}${x(i)},${y(p.value ?? 0)}`).join(" ");

  // Y-axis: gridlines in the scrolling plot, value labels in the sticky overlay.
  let grid = "", yLabels = "";
  for (const v of range.ticks) {
    const yy = y(v);
    grid += `<line x1="${padL}" y1="${yy}" x2="${w - padR}" y2="${yy}" stroke="#e5e5e5" stroke-width="1"/>`;
    yLabels += `<text x="${padL - 6}" y="${yy + 3}" text-anchor="end" style="font-size:10px">${escSvg(fmtMoney(v))}</text>`;
  }

  // X-axis: date labels, thinned out so they don't overlap.
  const xLabelStep = xStep > 0 ? Math.max(1, Math.ceil(60 / xStep)) : 1;
  let xAxis = "";
  points.forEach((p, i) => {
    if (i % xLabelStep !== 0 && i !== points.length - 1) return;
    xAxis += `<text x="${x(i)}" y="${h - padB + 16}" text-anchor="middle" style="font-size:10px">${escSvg(p.label)}</text>`;
  });

  // Hover targets: one dot per point, with a native tooltip giving the
  // x label and y value.
  let dots = "";
  points.forEach((p, i) => {
    if (p.value === null || p.value === undefined) return;
    dots += `<circle cx="${x(i)}" cy="${y(p.value)}" r="3" fill="${opts.color || '#2563eb'}" class="chart-dot">` +
      `<title>${escSvg(p.label)}: ${escSvg(fmtMoney(p.value))}</title></circle>`;
  });

  const axisSvg = `<svg class="chart-yaxis" width="${padL}" height="${h}" aria-hidden="true">${yLabels}</svg>`;
  const svg = `<div class="chart-scroll"><div class="chart-inner" style="width:${w}px">${axisSvg}` +
    `<svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" aria-label="${escSvg(label)}">
    ${grid}
    <line x1="${padL}" y1="${padT}" x2="${padL}" y2="${h - padB}" stroke="#999" stroke-width="1"/>
    <line x1="${padL}" y1="${h - padB}" x2="${w - padR}" y2="${h - padB}" stroke="#999" stroke-width="1"/>
    <path d="${path}" fill="none" stroke="${opts.color || '#2563eb'}" stroke-width="2"/>
    ${dots}
    ${xAxis}
  </svg></div></div>`;
  return svg + dataTableFallbackHtml(label, ["Date", "Value"], points.map(p => [p.label, fmtMoney(p.value)]));
}

// Rows for the YTD-expenses chart. Level 1 (Tracking Type) is what the bars
// show; levels 2-4 (Group -> Category -> Merchant) ride along in each row's
// `tree` for the hover popup. `hierarchy` is
// {trackingType: {group: {category: {merchant: amount}}}}.
function sumLeaves(node) {
  return typeof node === "number" ? node : Object.values(node).reduce((t, v) => t + sumLeaves(v), 0);
}

export function hierarchyToTree(node) {
  if (typeof node === "number") return [];
  return Object.entries(node)
    .map(([name, child]) => ({ name, value: sumLeaves(child), children: hierarchyToTree(child) }))
    .filter(n => Math.abs(n.value) > 0.005)
    .sort((a, b) => b.value - a.value);
}

export function buildHierarchyRows(hierarchy) {
  const rows = hierarchyToTree(hierarchy || {}).map(n => ({
    name: n.name, amount: n.value, kind: "category", detailTitle: n.name, tree: n.children,
  }));
  const total = rows.reduce((t, r) => t + r.amount, 0);
  return {
    total, rows,
    totalDetail: { detailTitle: "Total - by tracking type", detail: rows.map(r => [r.name, r.amount]) },
  };
}

// Popup body: title, a mini bar chart of up to `maxLines` entries (the
// remainder collapsed into one line), and the level's total.
export function detailPopupHtml(title, detail, maxLines) {
  maxLines = maxLines || 12;
  if (!detail.length) return `<div class="pop-title">${escSvg(title)}</div><div class="empty">No further detail logged.</div>`;
  const total = detail.reduce((t, e) => t + e[1], 0);
  let lines = detail.slice(0, maxLines);
  if (detail.length > maxLines) {
    const more = detail.slice(maxLines);
    lines = lines.concat([[`${more.length} more`, more.reduce((t, e) => t + e[1], 0)]]);
  }
  const max = Math.max(...lines.map(e => e[1]), 1);
  const body = lines.map(([n, v]) =>
    `<div class="pop-row"><span class="pop-name">${escSvg(n)}</span>` +
    `<span class="pop-bar"><i style="width:${Math.max(1, (v / max) * 100).toFixed(1)}%"></i></span>` +
    `<span class="pop-val">${escSvg(fmtMoney(v))}</span></div>`).join("");
  return `<div class="pop-title">${escSvg(title)}</div>${body}` +
    `<div class="pop-total"><span>Total</span><span>${escSvg(fmtMoney(total))}</span></div>`;
}

// Popup body for a Tracking Type: its Group -> Category -> Merchant tree as
// indented mini bars, plus the type's total. Per-level caps shrink until the
// popup fits `maxLines`, with the remainder at each level rolled into one
// "n more" line, so a large tree stays readable.
const TREE_LIMITS = [[6, 4, 3], [6, 3, 2], [6, 3, 1], [6, 2, 1], [6, 2, 0], [6, 0, 0]];

// `expanded` holds the keys of "n more" rows the viewer has rolled over; those
// levels list every entry instead of being capped.
function treeLines(nodes, depth, limits, parentMax, out, path, expanded) {
  const moreKey = `${path}|more`;
  const open = expanded.has(moreKey);
  const cap = open ? nodes.length : limits[depth - 1];
  const shown = nodes.slice(0, cap);
  const hidden = nodes.slice(cap);
  for (const n of shown) {
    out.push({ depth, name: n.name, value: n.value, max: parentMax });
    if (depth < 3 && n.children.length && limits[depth] > 0) {
      treeLines(n.children, depth + 1, limits, n.value, out, `${path}/${n.name}`, expanded);
    }
  }
  if (hidden.length) {
    out.push({ depth, name: `${hidden.length} more`, value: hidden.reduce((t, n) => t + n.value, 0), max: parentMax, muted: true, moreKey });
  }
}

export function detailTreeHtml(title, tree, maxLines, expanded) {
  maxLines = maxLines || 36;
  expanded = expanded || new Set();
  const total = tree.reduce((t, n) => t + n.value, 0);
  if (!tree.length) return `<div class="pop-title">${escSvg(title)}</div><div class="empty">No further detail logged.</div>`;
  let lines = [];
  // Once something is expanded, stop shrinking caps to fit: the popup scrolls instead.
  const presets = expanded.size ? [TREE_LIMITS[0]] : TREE_LIMITS;
  for (const limits of presets) {
    lines = [];
    treeLines(tree, 1, limits, total, lines, "", expanded);
    if (lines.length <= maxLines) break;
  }
  const body = lines.map(l =>
    `<div class="pop-row pop-d${l.depth}${l.muted ? " pop-muted" : ""}${l.value < 0 ? " pop-neg" : ""}"` +
    `${l.moreKey ? ` data-more="${escSvg(l.moreKey)}"` : ""}><span class="pop-name">${escSvg(l.name)}</span>` +
    `<span class="pop-bar"><i style="width:${l.value > 0 ? Math.max(1, (l.value / (l.max || 1)) * 100).toFixed(1) : 0}%"></i></span>` +
    `<span class="pop-val">${escSvg(fmtMoney(l.value))}</span></div>`).join("");
  return `<div class="pop-title">${escSvg(title)}</div>${body}` +
    `<div class="pop-total"><span>Total</span><span>${escSvg(fmtMoney(total))}</span></div>`;
}

// entries: [name, amount, meta?] -- meta.kind is "total" (text-only summary
// row, not scaled), "other" (muted bar) or anything else (normal bar). Rows
// with meta carry data-row so the page can attach the detail popup; rows
// without it keep a native <title> tooltip.
export function barChartSvg(entries) {
  if (!entries.length) return '<div class="empty">No expenses recorded yet.</div>';
  const w = 560, barH = 18, gap = 6, padL = 120, padR = 60, padB = 20;
  const max = Math.max(...entries.filter(e => !(e[2] && e[2].kind === "total")).map(e => e[1]), 1);
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

  const bars = entries.map((e, i) => {
    const y = i * (barH + gap);
    const meta = e[2];
    const row = meta ? ` data-row="${i}"` : "";
    const hit = `<rect x="0" y="${y - 2}" width="${w}" height="${barH + 4}" fill="transparent"/>`;
    if (meta && meta.kind === "total") {
      return `<g${row} class="bar-row">${hit}` +
        `<text x="0" y="${y + barH - 5}" style="font-weight:600">${escSvg(e[0])}</text>` +
        `<text x="${padL + 6}" y="${y + barH - 5}" style="font-weight:600">${escSvg(fmtMoney(e[1]))}</text></g>`;
    }
    const bw = (e[1] / max) * plotW;
    const fill = meta && meta.kind === "other" ? "#94a3b8" : "#2563eb";
    const tip = meta ? "" : `<title>${escSvg(e[0])}: ${escSvg(fmtMoney(e[1]))}</title>`;
    return `<g${row} class="bar-row">${hit}` +
      `<text x="0" y="${y + barH - 5}">${escSvg(e[0])}</text>` +
      `<rect x="${padL}" y="${y}" width="${bw}" height="${barH}" fill="${fill}" rx="3">${tip}</rect>` +
      `<text x="${padL + bw + 6}" y="${y + barH - 5}">${escSvg(fmtMoney(e[1]))}</text></g>`;
  }).join("");
  const svg = `<svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}" role="img" aria-label="YTD expenses by tracking type, bar chart">
    ${xAxis}
    <line x1="${padL}" y1="0" x2="${padL}" y2="${h - padB}" stroke="#999" stroke-width="1"/>
    ${bars}
  </svg>`;
  return svg + dataTableFallbackHtml("YTD expenses by tracking type", ["Tracking type", "Amount"], entries.map(e => [e[0], fmtMoney(e[1])]));
}

// Cashflow = YTD income - YTD expenses, on one consistent definition of
// "expenses" (spending including income taxes and real estate taxes).
// Log entries written before 2026-09-30's tracker change (#158) excluded both
// taxes from expenses; they're recognizable because expenses came in below the
// category total (which includes real estate tax), whereas current expenses are
// category total + income taxes. Those older entries get the two taxes added
// back so the series has no artificial step. The stored "net" is never used:
// older entries also subtracted taxes a second time.
export function cashflowNet(r) {
  const cf = r && r.cashflow;
  if (!cf || cf.income == null || cf.expenses == null) return null;
  let expenses = cf.expenses;
  const cats = r.ytd_expenses_by_category;
  if (cats) {
    const categoryTotal = Object.values(cats).reduce((t, v) => t + v, 0);
    if (expenses < categoryTotal) expenses += (cf.taxes || 0) + (cats["Real Estate Taxes"] || 0);
  }
  return cf.income - expenses;
}
