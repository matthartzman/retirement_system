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
  const w = 560, h = 160, pad = 28;
  const label = (opts.title || "Chart") + ", line chart";
  if (!points.length) return '<div class="empty">No data yet for this range.</div>';
  const values = points.map(p => p.value).filter(v => v !== null && v !== undefined);
  if (!values.length) return '<div class="empty">No data yet for this range.</div>';
  const min = Math.min(0, ...values), max = Math.max(...values, 1);
  const xStep = points.length > 1 ? (w - 2 * pad) / (points.length - 1) : 0;
  const y = v => h - pad - ((v - min) / (max - min || 1)) * (h - 2 * pad);
  const path = points.map((p, i) => `${i === 0 ? "M" : "L"}${pad + i * xStep},${y(p.value ?? 0)}`).join(" ");
  const last = points[points.length - 1];
  const svg = `<svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}" role="img" aria-label="${escSvg(label)}">
    <line x1="${pad}" y1="${y(0)}" x2="${w - pad}" y2="${y(0)}" stroke="#ccc" stroke-width="1"/>
    <path d="${path}" fill="none" stroke="${opts.color || '#2563eb'}" stroke-width="2"/>
    <text x="${pad}" y="12">${escSvg(points[0].label)}</text>
    <text x="${w - pad}" y="12" text-anchor="end">${escSvg(last.label)}</text>
    <text x="${w - pad}" y="${y(last.value ?? 0) - 6}" text-anchor="end" font-weight="600">${escSvg(fmtMoney(last.value))}</text>
  </svg>`;
  return svg + dataTableFallbackHtml(label, ["Date", "Value"], points.map(p => [p.label, fmtMoney(p.value)]));
}

export function barChartSvg(entries) {
  if (!entries.length) return '<div class="empty">No expenses recorded yet.</div>';
  const w = 560, barH = 18, gap = 6, pad = 120;
  const max = Math.max(...entries.map(e => e[1]), 1);
  const h = entries.length * (barH + gap);
  const bars = entries.map((e, i) => {
    const y = i * (barH + gap);
    const bw = (e[1] / max) * (w - pad - 60);
    return `<text x="0" y="${y + barH - 5}">${escSvg(e[0])}</text>
      <rect x="${pad}" y="${y}" width="${bw}" height="${barH}" fill="#2563eb" rx="3"/>
      <text x="${pad + bw + 6}" y="${y + barH - 5}">${escSvg(fmtMoney(e[1]))}</text>`;
  }).join("");
  const svg = `<svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}" role="img" aria-label="YTD expenses by category, bar chart">${bars}</svg>`;
  return svg + dataTableFallbackHtml("YTD expenses by category", ["Category", "Amount"], entries.map(e => [e[0], fmtMoney(e[1])]));
}
