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
  if (tf === "day") { from = new Date(last); from.setDate(from.getDate() - 1); }
  else if (tf === "week") { from = new Date(last); from.setDate(from.getDate() - 7); }
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

// Granularity requirement: daily points for day/week/month ranges, weekly
// for quarter, monthly for ytd/12-month/all-time. A custom range has no
// fixed answer, so it's inferred from how many days the range spans.
export function granularityForTimeframe(tf, rows) {
  const fixed = { day: "day", week: "day", month: "day", quarter: "week", ytd: "month", "12m": "month", all: "month" };
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

export function lineChartSvg(points, opts) {
  opts = opts || {};
  const w = 560, h = 200, padL = 56, padR = 16, padT = 16, padB = 28;
  const label = (opts.title || "Chart") + ", line chart";
  if (!points.length) return '<div class="empty">No data yet for this range.</div>';
  const values = points.map(p => p.value).filter(v => v !== null && v !== undefined);
  if (!values.length) return '<div class="empty">No data yet for this range.</div>';
  const min = Math.min(0, ...values), max = Math.max(...values, 1);
  const plotW = w - padL - padR, plotH = h - padT - padB;
  const xStep = points.length > 1 ? plotW / (points.length - 1) : 0;
  const x = i => padL + i * xStep;
  const y = v => padT + plotH - ((v - min) / (max - min || 1)) * plotH;
  const path = points.map((p, i) => `${i === 0 ? "M" : "L"}${x(i)},${y(p.value ?? 0)}`).join(" ");

  // Y-axis: gridlines + value labels at 4 evenly-spaced ticks.
  const yTickCount = 4;
  let yAxis = "";
  for (let i = 0; i <= yTickCount; i++) {
    const v = min + ((max - min) * i) / yTickCount;
    const yy = y(v);
    yAxis += `<line x1="${padL}" y1="${yy}" x2="${w - padR}" y2="${yy}" stroke="#e5e5e5" stroke-width="1"/>` +
      `<text x="${padL - 6}" y="${yy + 3}" text-anchor="end" style="font-size:10px">${escSvg(fmtMoney(v))}</text>`;
  }

  // X-axis: date labels, thinned out so they don't overlap on long ranges.
  const maxXLabels = 6;
  const xLabelStep = points.length > 1 ? Math.max(1, Math.ceil((points.length - 1) / (maxXLabels - 1))) : 1;
  let xAxis = "";
  points.forEach((p, i) => {
    if (i % xLabelStep !== 0 && i !== points.length - 1) return;
    xAxis += `<text x="${x(i)}" y="${h - padB + 16}" text-anchor="middle" style="font-size:10px">${escSvg(p.label)}</text>`;
  });

  // Hover targets: one dot per point, with a native tooltip giving the
  // x label and y value (no charting library in play, so this is the
  // simplest reliable way to surface hover data across browsers).
  let dots = "";
  points.forEach((p, i) => {
    if (p.value === null || p.value === undefined) return;
    dots += `<circle cx="${x(i)}" cy="${y(p.value)}" r="3" fill="${opts.color || '#2563eb'}" class="chart-dot">` +
      `<title>${escSvg(p.label)}: ${escSvg(fmtMoney(p.value))}</title></circle>`;
  });

  const svg = `<svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}" role="img" aria-label="${escSvg(label)}">
    ${yAxis}
    <line x1="${padL}" y1="${padT}" x2="${padL}" y2="${h - padB}" stroke="#999" stroke-width="1"/>
    <line x1="${padL}" y1="${h - padB}" x2="${w - padR}" y2="${h - padB}" stroke="#999" stroke-width="1"/>
    <path d="${path}" fill="none" stroke="${opts.color || '#2563eb'}" stroke-width="2"/>
    ${dots}
    ${xAxis}
  </svg>`;
  return svg + dataTableFallbackHtml(label, ["Date", "Value"], points.map(p => [p.label, fmtMoney(p.value)]));
}

export function barChartSvg(entries) {
  if (!entries.length) return '<div class="empty">No expenses recorded yet.</div>';
  const w = 560, barH = 18, gap = 6, padL = 120, padR = 60, padB = 20;
  const max = Math.max(...entries.map(e => e[1]), 1);
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
    const bw = (e[1] / max) * plotW;
    return `<text x="0" y="${y + barH - 5}">${escSvg(e[0])}</text>
      <rect x="${padL}" y="${y}" width="${bw}" height="${barH}" fill="#2563eb" rx="3">
        <title>${escSvg(e[0])}: ${escSvg(fmtMoney(e[1]))}</title>
      </rect>
      <text x="${padL + bw + 6}" y="${y + barH - 5}">${escSvg(fmtMoney(e[1]))}</text>`;
  }).join("");
  const svg = `<svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}" role="img" aria-label="YTD expenses by category, bar chart">
    ${xAxis}
    <line x1="${padL}" y1="0" x2="${padL}" y2="${h - padB}" stroke="#999" stroke-width="1"/>
    ${bars}
  </svg>`;
  return svg + dataTableFallbackHtml("YTD expenses by category", ["Category", "Amount"], entries.map(e => [e[0], fmtMoney(e[1])]));
}
