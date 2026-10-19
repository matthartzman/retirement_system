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

// Nominal granularity: daily points for week/month ranges, weekly for
// quarter, monthly for ytd/12-month/all-time -- but never finer than the data
// supports: monthly points revert to weekly when the rows span under 4 months,
// and weekly to daily when they span under 4 weeks. A custom range has no
// nominal answer, so it's inferred from how many days the range spans.
export function granularityForTimeframe(tf, rows) {
  const spanDays = rows && rows.length >= 2
    ? (new Date(rows[rows.length - 1].as_of_date) - new Date(rows[0].as_of_date)) / 86400000
    : null;
  const nominal = { week: "day", month: "day", quarter: "week", ytd: "month", "12m": "month", all: "month" }[tf];
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

// Line chart wide enough to give each point `pxPerPoint` of room; when that
// exceeds the card, the chart scrolls horizontally (.chart-scroll) with the
// y-axis labels pinned in a sticky overlay so they stay visible.
export function lineChartSvg(points, opts) {
  opts = opts || {};
  const minW = 560, h = 200, padL = 56, padR = 34, padT = 16, padB = 28;
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
  // A missing value breaks the line (a new "M") rather than dropping to $0.
  let pen = false;
  const path = points.map((p, i) => {
    if (p.value === null || p.value === undefined) { pen = false; return ""; }
    const cmd = pen ? "L" : "M";
    pen = true;
    return `${cmd}${x(i)},${y(p.value)}`;
  }).filter(Boolean).join(" ");

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
  // Counted back from the newest point so the last label is always drawn and
  // never crowds its neighbour; padR leaves room for it to render untruncated.
  points.forEach((p, i) => {
    if ((points.length - 1 - i) % xLabelStep !== 0) return;
    xAxis += `<text x="${x(i)}" y="${h - padB + 16}" text-anchor="middle" style="font-size:10px">${escSvg(p.label)}</text>`;
  });

  // Hover targets: one dot per point, with a native tooltip giving the
  // x label and y value.
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
    dots += `<circle cx="${x(i)}" cy="${y(p.value)}" r="3" fill="${opts.color || '#2563eb'}" class="chart-dot"${focus}>` +
      `<title>${escSvg(p.label)}: ${escSvg(fmtMoney(p.value))}</title></circle>`;
  });

  // The pinned y-axis stops above the x-axis labels so it can't clip the first one.
  const axisH = h - padB + 8;
  const axisSvg = `<svg class="chart-yaxis" width="${padL}" height="${axisH}" style="margin-bottom:-${axisH}px" aria-hidden="true">${yLabels}</svg>`;
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
// show. Rolling over a bar lists its categories (`categories`); rolling over a
// category lists its merchants. `hierarchy` is
// {trackingType: {group: {category: {merchant: amount}}}}.
function sumLeaves(node) {
  return typeof node === "number" ? node : Object.values(node).reduce((t, v) => t + sumLeaves(v), 0);
}

// priorByType / budgetByType (347a): optional {trackingType: amount} for the bar markers.
// priorDetail {type: {group: {category: {prior, merchants: {name: amount}}}}} and budgetByCategory
// {type: {category: amount}} (both optional) carry the same markers into the popups.
export function buildHierarchyRows(hierarchy, priorByType, budgetByType, priorDetail, budgetByCategory) {
  const rows = [];
  for (const [name, groups] of Object.entries(hierarchy || {})) {
    const categories = [];
    for (const [group, cats] of Object.entries(groups)) {
      for (const [cat, merchants] of Object.entries(cats)) {
        const value = sumLeaves(merchants);
        if (Math.abs(value) < 0.005) continue;
        const priorCat = priorDetail && priorDetail[name] && priorDetail[name][group] && priorDetail[name][group][cat];
        const priorMerchants = (priorCat && priorCat.merchants) || {};
        const budgetCat = budgetByCategory && budgetByCategory[name] && budgetByCategory[name][cat];
        categories.push({
          name: cat, group, value,
          prior: priorCat && priorCat.prior != null ? priorCat.prior : null,
          budget: budgetCat != null ? budgetCat : null,
          // Merchants have no budget; prior-year shows only for a merchant that also appears last year.
          merchants: Object.entries(merchants).filter(e => Math.abs(e[1]) > 0.005).sort((a, b) => b[1] - a[1])
            .map(([m, v]) => priorCat ? [m, v, { prior: priorMerchants[m] != null ? priorMerchants[m] : null }] : [m, v]),
        });
      }
    }
    categories.sort((a, b) => b.value - a.value);
    const amount = categories.reduce((t, c) => t + c.value, 0);
    if (amount > 0.005) rows.push({ name, amount, kind: "category", detailTitle: name, categories,
      prior: priorByType && priorByType[name] != null ? priorByType[name] : null,
      budget: budgetByType && budgetByType[name] != null ? budgetByType[name] : null });
  }
  rows.sort((a, b) => b.amount - a.amount);
  const total = rows.reduce((t, r) => t + r.amount, 0);
  // Totals come from the full maps, not just the visible rows: a type budgeted but not yet spent still counts.
  const sumMarker = map => (map && Object.keys(map).length ? Object.values(map).reduce((t, v) => t + v, 0) : null);
  return {
    total, rows,
    totalMarkers: { prior: sumMarker(priorByType), budget: sumMarker(budgetByType) },
    totalDetail: { detailTitle: "Total - by tracking type", detail: rows.map(r => [r.name, r.amount, { prior: r.prior, budget: r.budget }]) },
  };
}

// Prior-year (black) and full-year budget (orange) ticks on a popup bar, same colours
// as the YTD bars. `max` is the bar scale shared by the popup so ticks never overflow.
function popMarkers(prior, budget, max) {
  const tick = (v, cls, label) => v == null ? "" :
    `<b class="pm ${cls}" style="left:${Math.min(100, Math.max(0, (v / max) * 100)).toFixed(1)}%" title="${escSvg(label)}: ${escSvg(fmtMoney(v))}"></b>`;
  return tick(prior, "pm-prior", "Prior-year YTD") + tick(budget, "pm-budget", "Full-year budget");
}

// Step-1 popup: a tracking type's categories (each tagged data-cat for the
// step-2 merchant popup), with the type's total.
export function categoryListHtml(title, categories) {
  if (!categories.length) return `<div class="pop-title">${escSvg(title)}</div><div class="empty">No further detail logged.</div>`;
  const total = categories.reduce((t, c) => t + c.value, 0);
  const max = Math.max(...categories.flatMap(c => [c.value, c.prior || 0, c.budget || 0]), 1);
  const body = categories.map((c, i) =>
    `<div class="pop-row pop-cat${c.value < 0 ? " pop-neg" : ""}" data-cat="${i}"><span class="pop-name" title="${escSvg(c.group)}">${escSvg(c.name)}</span>` +
    `<span class="pop-bar"><i style="width:${c.value > 0 ? Math.max(1, (c.value / max) * 100).toFixed(1) : 0}%"></i>${popMarkers(c.prior, c.budget, max)}</span>` +
    `<span class="pop-val">${escSvg(fmtMoney(c.value))}</span></div>`).join("");
  return `<div class="pop-title">${escSvg(title)} <span class="pop-hint">- roll over a category for merchants</span></div>${body}` +
    `<div class="pop-total"><span>Total</span><span>${escSvg(fmtMoney(total))}</span></div>`;
}

// Popup body: title, a mini bar chart of up to `maxLines` entries (the
// remainder collapsed into one line), and the level's total.
export function detailPopupHtml(title, detail, maxLines) {
  maxLines = maxLines || Infinity;
  if (!detail.length) return `<div class="pop-title">${escSvg(title)}</div><div class="empty">No further detail logged.</div>`;
  const total = detail.reduce((t, e) => t + e[1], 0);
  let lines = detail.slice(0, maxLines);
  if (detail.length > maxLines) {
    const more = detail.slice(maxLines);
    lines = lines.concat([[`${more.length} more`, more.reduce((t, e) => t + e[1], 0)]]);
  }
  const max = Math.max(...lines.flatMap(e => [e[1], (e[2] && e[2].prior) || 0, (e[2] && e[2].budget) || 0]), 1);
  const body = lines.map(([n, v, meta]) =>
    `<div class="pop-row${v < 0 ? " pop-neg" : ""}"><span class="pop-name">${escSvg(n)}</span>` +
    `<span class="pop-bar"><i style="width:${v > 0 ? Math.max(1, (v / max) * 100).toFixed(1) : 0}%"></i>${popMarkers(meta && meta.prior, meta && meta.budget, max)}</span>` +
    `<span class="pop-val">${escSvg(fmtMoney(v))}</span></div>`).join("");
  return `<div class="pop-title">${escSvg(title)}</div>${body}` +
    `<div class="pop-total"><span>Total</span><span>${escSvg(fmtMoney(total))}</span></div>`;
}

// entries: [name, amount, meta?] -- meta.kind is "total" (text-only summary
// row, not scaled), "other" (muted bar) or anything else (normal bar). Rows
// with meta carry data-row so the page can attach the detail popup; rows
// without it keep a native <title> tooltip.
const PRIOR_COLOR = "#475569", BUDGET_COLOR = "#d97706";
export function barChartSvg(entries) {
  if (!entries.length) return '<div class="empty">No expenses recorded yet.</div>';
  const w = 560, barH = 18, gap = 6, padL = 120, padR = 60, padB = 20;
  // Axis fits the longest of spend / prior-year / budget so no marker runs off the plot.
  const max = Math.max(...entries.filter(e => !(e[2] && e[2].kind === "total")).flatMap(e => [e[1], e[2] && e[2].prior || 0, e[2] && e[2].budget || 0]), 1);
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

  const marker = (v, y, len, color, label, sw) => {
    if (v == null) return "";
    const xx = padL + (v / max) * plotW;
    return `<line x1="${xx}" y1="${y}" x2="${xx}" y2="${y + len}" stroke="${color}" stroke-width="${sw}"><title>${escSvg(label)}: ${escSvg(fmtMoney(v))}</title></line>`;
  };
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
    const markers = marker(meta && meta.prior, y - 2, barH + 4, PRIOR_COLOR, "Prior-year YTD", 2.5) +
      marker(meta && meta.budget, y - 2, barH + 4, BUDGET_COLOR, "Full-year budget", 2.5);
    const bw = (e[1] / max) * plotW;
    const fill = meta && meta.kind === "other" ? "#94a3b8" : "#2563eb";
    const tip = meta ? "" : `<title>${escSvg(e[0])}: ${escSvg(fmtMoney(e[1]))}</title>`;
    return `<g${row} class="bar-row">${hit}` +
      `<text x="0" y="${y + barH - 5}">${escSvg(e[0])}</text>` +
      `<rect x="${padL}" y="${y}" width="${bw}" height="${barH}" fill="${fill}" rx="3">${tip}</rect>` + markers +
      `<text x="${padL + bw + 6}" y="${y + barH - 5}">${escSvg(fmtMoney(e[1]))}</text></g>`;
  }).join("");
  const anyPrior = entries.some(e => e[2] && e[2].prior != null), anyBudget = entries.some(e => e[2] && e[2].budget != null);
  const legend = (anyPrior || anyBudget) ? `<div class="bar-legend" style="font-size:12px">` +
    (anyPrior ? `<span style="color:${PRIOR_COLOR}">&#9646; Prior-year YTD (same dates)</span> ` : "") +
    (anyBudget ? `<span style="color:${BUDGET_COLOR}">&#9646; Full-year budget</span>` : "") + `</div>` : "";
  const svg = legend + `<svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}" role="img" aria-label="YTD expenses by tracking type, bar chart">
    ${xAxis}
    <line x1="${padL}" y1="0" x2="${padL}" y2="${h - padB}" stroke="#999" stroke-width="1"/>
    ${bars}
  </svg>`;
  const money = v => (v == null ? "-" : fmtMoney(v));
  return svg + dataTableFallbackHtml("YTD expenses by tracking type", ["Tracking type", "Amount", ...(anyPrior ? ["Prior-year YTD"] : []), ...(anyBudget ? ["Full-year budget"] : [])],
    entries.map(e => [e[0], fmtMoney(e[1]), ...(anyPrior ? [money(e[2] && e[2].prior)] : []), ...(anyBudget ? [money(e[2] && e[2].budget)] : [])]));
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
  if (nw.mortgage != null) lines.push(["Mortgage", -nw.mortgage]);
  // nw.liabilities = account liabilities + liabilities file + mortgage. Cards/loans are already listed
  // under their role above and the mortgage has its own line, so show only the remainder.
  if (nw.liabilities != null) {
    const rest = nw.liabilities - (nw.mortgage || 0) - accountLiabilities;
    if (Math.abs(rest) >= 0.5) lines.push(["Other liabilities", -rest]);
  }
  return {
    title: "Net worth", date: row.as_of_date, total: nw.total ?? null,
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
  const svg = `<svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}" role="group" aria-label="YTD net investment flows by account, bar chart">` +
    `<line x1="${zeroX}" y1="0" x2="${zeroX}" y2="${h - padB}" stroke="#999" stroke-width="1"/>` +
    `<text x="${zeroX}" y="${h - padB + 14}" text-anchor="middle" style="font-size:10px">$0</text>${bars}</svg>`;
  return svg + dataTableFallbackHtml("YTD net investment flows by account",
    ["Account", "Net (withdrawal +)", "Withdrawn", "Contributed"],
    model.rows.map(r => [r.name, fmtMoney(r.net)]).map((row, i) => row.concat([fmtMoney(model.rows[i].toChecking), fmtMoney(model.rows[i].fromChecking)]))
      .concat([["Total", fmtMoney(model.total), "", ""]]));
}

// ---------------------------------------------------------------------------
// Monarch daily balances (balances payload from /api/balances) -- Net worth, Holdings.
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
// works unchanged. Monarch dates use Monarch totals; dates Monarch doesn't cover keep the
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

// All time starts here. Monarch history before this date has only a loan or two linked, so it
// is not a comparable total and it stretches the Y axis; it is cut, not just hidden.
export const ALL_TIME_START = "2025-02-01";

export function truncateAllTime(rows, start = ALL_TIME_START) {
  const kept = rows.filter(r => r.as_of_date >= start);
  return { rows: kept, truncated: kept.length < rows.length };
}

// Rollover for a Monarch-sourced row: enabled accounts with a non-zero value on that date,
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
    title: chart === "holdings" ? "Liquid Investments and Cash" : "Net worth", date: row.as_of_date,
    total: chart === "holdings" ? row.holdings.current_value : row.net_worth.total,
    groups, lines: [], emptyNote: "No accounts with a balance are switched on for this date.",
  };
}

// Banner text when the daily Monarch import is failing or stale; "" when healthy.
export function balancesFreshnessNote(freshness, today) {
  const last = freshness && freshness.last_run, ok = freshness && freshness.last_ok;
  if (!last) return "";
  const now = today ? new Date(today + "T00:00:00") : new Date();
  const ageDays = ok && ok.latest_date ? Math.floor((now - new Date(ok.latest_date + "T00:00:00")) / 86400000) : null;
  if (last.status !== "ok") {
    return `The latest Monarch balances import was rejected (${last.detail || "unknown reason"}); showing balances through ${ok && ok.latest_date ? ok.latest_date : "no date"}.`;
  }
  if (ageDays !== null && ageDays > 2) return `Monarch balances were last updated ${ok.latest_date}.`;
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
    `<div class="note">Type, match to the plan and Ignore come from the Retirement app's Monarch Reconciliation page.</div>` +
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

export function flowSummaryHtml(ytd) {
  if (!ytd) return "";
  const tile = (label, value, cls) => `<div class="flow-stat ${cls}"><span class="flow-stat-label">${escSvg(label)}</span><span class="flow-stat-value">${escSvg(fmtMoneySigned(value))}</span></div>`;
  return `<div class="flow-summary" role="group" aria-label="${escSvg(String(ytd.year))} year to date investment flows">` +
    `<div class="flow-year">${escSvg(String(ytd.year))} YTD</div>` +
    tile("Credits (into investments)", ytd.credits, "flow-credit") +
    tile("Debits (out of investments)", ytd.debits, "flow-debit") +
    tile("Total (net contributions)", ytd.total, "flow-total") + `</div>`;
}

export function flowLineChartSvg(series) {
  if (!series.length) return '<div class="empty">No investment transfers recorded for the accounts switched on.</div>';
  return lineChartSvg(series.map(p => ({ label: monthLabel(p.month), value: p.net })),
    { color: "#0d9488", title: "Net investment contributions by month", pxPerPoint: 56 });
}
