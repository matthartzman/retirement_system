// Realized gains and losses (sales ledger plan 9.2): confirmed ledger sales in the Time scope (or a tax year),
// grouped by symbol or account with their lots. A "Realized" tab inside the Current Snapshot area; the data comes from
// /api/realized. Pure helpers are exported for tests; initRealized() wires the tab in the browser.
//
// In the percent view of the $ | % toggle only ratios are shown (return on basis): no proceeds, basis, gain or share
// counts. A percent-only person is sent group-level totals only (the server drops the per-sale lots), so a group
// can arrive without ``lots``.

import { moneyView, onMoneyViewChange } from "./money_view.js";
import { fmtUsd, fmtPct } from "./live_snapshot.js";

const isPct = () => moneyView().shown === "percent";
const DASH = "–";
const TERMS = { short: "Short", long: "Long", unknown: "Unknown" };
const SOURCES = { holdings_diff: "Holdings import", monarch: "Imported transactions", manual: "Manual", "1099b": "1099-B" };
const STATUS_1099 = { none: DASH, matches: "Matches", differs: "Differs" };

// Grouping levels, outermost first (the Holdings Group by row, with this view's own dimensions). The sale rows are always
// the last level and cannot move or be removed. The grouping is built by the server; the sort is applied here.
export const LEVELS = { symbol: "Symbol", account: "Account", term: "Term" };
export const LEVELS_KEY = "trendsRealizedLevels_v1", SORT_KEY = "trendsRealizedSort_v1";
const SORT_FIELDS = { name: "Name", proceeds: "Proceeds", basis: "Basis", net: "Gain", ret: "Return" };
const PERCENT_SORT = ["name", "ret"];
export const DEFAULT_SORT = Object.freeze({ field: "name", dir: "asc" });
export const DEFAULT_STATE = Object.freeze({ levels: ["symbol"], sort: DEFAULT_SORT, taxYear: "", taxable: false, wash: false, unconfirmed: false });

export function normalizeLevels(raw) {
  const out = [];
  for (const d of Array.isArray(raw) ? raw : []) if (Object.hasOwn(LEVELS, d) && !out.includes(d)) out.push(d);
  return out.length ? out : [...DEFAULT_STATE.levels];
}
export function normalizeSort(raw) {
  return { field: raw && Object.hasOwn(SORT_FIELDS, raw.field) ? raw.field : "name", dir: raw && raw.dir === "desc" ? "desc" : "asc" };
}
export const stepLevel = (levels, dim, delta) => {
  const at = levels.indexOf(dim), to = at + delta;
  if (at < 0 || to < 0 || to >= levels.length) return normalizeLevels(levels);
  const next = [...levels]; next.splice(at, 1); next.splice(to, 0, dim);
  return next;
};
export const toggleLevel = (levels, dim) => normalizeLevels(levels.includes(dim) ? levels.filter((d) => d !== dim) : [...levels, dim]);

const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const ratio = (n, d) => (n === null || n === undefined || !d ? null : n / d);
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

// The request: the shared Time scope's first day, unless a tax year is picked.
export function realizedQuery(state, scopeFrom) {
  const p = new URLSearchParams();
  if (state.taxYear) p.set("tax_year", String(state.taxYear)); else if (scopeFrom) p.set("from", scopeFrom);
  p.set("group", normalizeLevels(state.levels).join(","));
  if (state.taxable) p.set("taxable", "1");
  if (state.wash) p.set("wash", "1");
  if (state.unconfirmed) p.set("unconfirmed", "1");
  return p.toString();
}

const money = (v) => (v === null || v === undefined ? DASH : fmtUsd(v));
const gainText = (v) => (v === null || v === undefined ? DASH : `<span class="${v < 0 ? "neg" : "pos"}">${fmtUsd(v)}</span>`);
const returnText = (gain, basis) => { const r = ratio(gain, basis); return r === null ? DASH : fmtPct(r, 1); };

function controlsHtml(data, state) {
  const years = (data.years || []).map((y) => `<option value="${y}"${String(state.taxYear) === String(y) ? " selected" : ""}>Tax year ${y}</option>`).join("");
  const check = (id, key, label) => `<label><input type="checkbox" id="${id}"${state[key] ? " checked" : ""}> ${label}</label>`;
  return `<div class="realized-controls">`
    + `<label>Period <select id="realizedYear"><option value="">Time scope</option>${years}</select></label>`
    + check("realizedTaxable", "taxable", "Taxable accounts only") + check("realizedWash", "wash", "Wash-flagged only")
    + check("realizedUnconfirmed", "unconfirmed", "Include unconfirmed (estimate)")
    + `<button type="button" data-realized-all="expand">Expand all</button><button type="button" data-realized-all="collapse">Collapse all</button></div>`;
}

// The Group by row, as on Holdings: the levels in use (arrows reorder, x drops one), Sale always last, then the unused levels.
export function groupByHtml(levels) {
  const cur = normalizeLevels(levels), unused = Object.keys(LEVELS).filter((d) => !cur.includes(d));
  const chip = (dim, i) => `<span class="chip" data-dim="${dim}">`
    + `<button type="button" class="chip-step" data-dim="${dim}" data-step="-1" aria-label="Move ${LEVELS[dim]} earlier"${i === 0 ? " disabled" : ""}>◂</button>`
    + `<span class="chip-name">${LEVELS[dim]}</span>`
    + `<button type="button" class="chip-step" data-dim="${dim}" data-step="1" aria-label="Move ${LEVELS[dim]} later"${i === cur.length - 1 ? " disabled" : ""}>▸</button>`
    + `<button type="button" class="chip-remove" data-dim="${dim}" aria-label="Stop grouping by ${LEVELS[dim]}">×</button></span>`;
  return `<div class="group-by" role="group" aria-label="Group by"><span class="group-by-label">Group by</span>${cur.map(chip).join("")}`
    + `<span class="chip fixed" data-dim="lot" title="Sales are always the last level">Sale</span>`
    + unused.map((dim) => `<button type="button" class="chip off" data-dim="${dim}" aria-label="Also group by ${LEVELS[dim]}">+ ${LEVELS[dim]}</button>`).join("") + `</div>`;
}

export function sortByHtml(sort) {
  const cur = normalizeSort(sort);
  const fields = Object.entries(SORT_FIELDS).filter(([f]) => !isPct() || PERCENT_SORT.includes(f));
  const opt = (value, label, on) => `<option value="${value}"${on ? " selected" : ""}>${esc(label)}</option>`;
  return `<div class="sort-by" role="group" aria-label="Sort by"><label class="group-by-label" for="realizedSortField">Sort by</label>`
    + `<select id="realizedSortField" aria-label="Sort by field">${fields.map(([f, label]) => opt(f, label, f === cur.field)).join("")}</select>`
    + `<select id="realizedSortDir" aria-label="Sort direction">${opt("asc", "Ascending", cur.dir === "asc")}${opt("desc", "Descending", cur.dir === "desc")}</select></div>`;
}

function summaryHtml(s) {
  if (isPct()) {
    return `<p class="live-sub">${plural(s.count, "sale", "sales")} · return on basis ${returnText(s.net, s.basis)}</p>`;
  }
  const cell = (label, value) => `<div><div class="live-label">${label}</div><div class="live-big small">${value}</div></div>`;
  return `<div class="realized-summary">${cell("Short-term", gainText(s.st_gain))}${cell("Long-term", gainText(s.lt_gain))}${cell("Net", gainText(s.net))}`
    + `${cell("Proceeds", money(s.proceeds))}${cell("Basis", money(s.basis))}${cell("Wash-flagged", gainText(s.wash_flagged))}</div>`
    + (s.unknown_gain ? `<p class="note">${fmtUsd(s.unknown_gain)} of the net has no holding period yet.</p>` : "");
}

function lotRow(l, parent, depth, showAccount) {
  const acct = showAccount && l.account_label ? ` · ${esc(l.account_label)}` : "";
  const when = `${esc(l.sale_date)}${l.purchase_date ? ` · bought ${esc(l.purchase_date)}` : ""}${acct}`;
  const flags = [l.wash_flag && l.wash_flag !== "none" ? "wash" : "", l.estimate ? "estimate" : ""].filter(Boolean).join(", ");
  const dollars = isPct() ? "" : `<td class="num">${esc(l.shares)}</td><td class="num">${money(l.proceeds)}</td><td class="num">${money(l.basis)}</td><td class="num">${gainText(l.gain)}</td>`;
  return `<tr class="sale-lot" data-depth="${depth}" data-parent="${esc(parent)}" hidden><th scope="row">${when}</th>${dollars}<td class="num">${returnText(l.gain, l.basis)}</td>`
    + `<td>${esc(TERMS[l.term] || DASH)}</td><td>${esc(SOURCES[l.source] || l.source || DASH)}</td><td>${esc(flags) || DASH}</td><td>${esc(STATUS_1099[l.status_1099] || DASH)}</td></tr>`;
}

// ---- sort: one field and a direction at every level; a figure a row doesn't have goes last either way ----
const TERM_RANK = { short: 0, long: 1, unknown: 2 };
const labelOf = (n) => (n.dim === "term" ? TERMS[n.name] || n.name : n.label ?? n.name);
const figure = (n, field) => (field === "proceeds" ? n.proceeds : field === "basis" ? n.basis : field === "net" ? (n.net ?? n.gain) : ratio(n.net ?? n.gain, n.basis));
function byName(a, b) {
  if (a.dim === "term" && b.dim === "term") return (TERM_RANK[a.name] ?? 9) - (TERM_RANK[b.name] ?? 9);
  return String(labelOf(a)).localeCompare(String(labelOf(b)), undefined, { sensitivity: "base" });
}
export function sortNodes(nodes, sort) {
  const { field, dir } = normalizeSort(sort), sign = dir === "desc" ? -1 : 1;
  return [...nodes].sort((a, b) => {
    if (field === "name") return sign * byName(a, b);
    const x = figure(a, field), y = figure(b, field), hasX = x !== null && x !== undefined, hasY = y !== null && y !== undefined;
    if (hasX !== hasY) return hasX ? -1 : 1;
    return (hasX ? sign * (x - y) : 0) || byName(a, b);
  });
}
// Sale rows have no name of their own: by date, newest first, when the sort is by name.
const sortLots = (lots, sort) => (normalizeSort(sort).field === "name"
  ? [...lots].sort((a, b) => String(b.sale_date).localeCompare(String(a.sale_date)) || (b.sale_id ?? 0) - (a.sale_id ?? 0))
  : sortNodes(lots, sort));

// Nested group rows. A row's path (its names, URL-encoded) keys its expanded state; rows below the top carry
// data-parent and start hidden until their parent is expanded (applyExpanded in initRealized).
function rowsHtml(nodes, ctx, parent, depth) {
  return sortNodes(nodes, ctx.sort).map((n) => {
    const path = `${parent}/${encodeURIComponent(n.name)}`, kids = (n.children || []).length + (n.lots || []).length > 0;
    const label = esc(labelOf(n)), count = ` <span class="muted">${plural(n.count, "lot", "lots")}</span>`;
    const head = kids ? `<button type="button" class="expand" aria-expanded="false" data-path="${esc(path)}" data-label="${label}">▸ ${label}</button>` : label;
    const dollars = isPct() ? "" : `<td></td><td class="num">${money(n.proceeds)}</td><td class="num">${money(n.basis)}</td><td class="num">${gainText(n.net)}</td>`;
    const attrs = `data-depth="${depth}"${kids ? ` data-path="${esc(path)}"` : ""}${depth ? ` data-parent="${esc(parent)}" hidden` : ""}`;
    return `<tr class="${depth ? "group-row" : "top-row"}" ${attrs}><th scope="row">${head}${count}</th>${dollars}<td class="num">${returnText(n.net, n.basis)}</td><td></td><td></td><td></td><td></td></tr>`
      + (n.children ? rowsHtml(n.children, ctx, path, depth + 1) : sortLots(n.lots || [], ctx.sort).map((l) => lotRow(l, path, depth + 1, !ctx.levels.includes("account"))).join(""));
  }).join("");
}

function tableHtml(groups, state, key) {
  if (!groups.length) return "";
  const levels = normalizeLevels(state.levels);
  const dollarHeads = isPct() ? "" : `<th scope="col" class="num">Shares</th><th scope="col" class="num">Proceeds</th><th scope="col" class="num">Basis</th><th scope="col" class="num">Gain</th>`;
  const head = `<thead><tr><th scope="col">${esc(levels.map((d) => LEVELS[d]).join(" / "))} / sale</th>${dollarHeads}<th scope="col" class="num">Return</th><th scope="col">Term</th><th scope="col">Source</th><th scope="col">Flags</th><th scope="col">1099-B</th></tr></thead>`;
  return `<div class="table-scroll"><table class="live-table realized-table">${head}<tbody>${rowsHtml(groups, { sort: state.sort, levels }, key, 0)}</tbody></table></div>`;
}

function estimateHtml(est, state) {
  if (!est) return "";
  const inner = est.count
    ? `${summaryHtml(est)}${tableHtml(est.groups, state, "~est")}`
    : `<p class="empty">No waiting sale could be valued.</p>`;
  return `<details class="live-section estimate" open><summary>Estimate for sales not yet confirmed</summary>`
    + `<p class="note">Estimate only: each is valued at its imported amount with first-in-first-out lots from today's holdings. Not in the totals above, and never used for tax, the projection or the daily log.</p>${inner}</details>`;
}

export function realizedViewHtml(data, state = DEFAULT_STATE) {
  if (!data) return `<p class="empty">Loading realized sales…</p>`;
  if (data.error) return `<p class="live-error">Realized sales are unavailable: ${esc(data.error)}</p>`;
  state = { ...DEFAULT_STATE, ...state };
  const w = data.window || {};
  const period = w.tax_year ? `Tax year ${w.tax_year}` : `Since ${esc(w.from)}`;
  const waiting = data.unconfirmed?.count ?? 0;
  const chip = waiting
    ? `<p class="note"><span class="chip warn">${plural(waiting, "sale", "sales")} waiting for lots</span> Confirm the lots in the Retirement Planner's Sales ledger page; until then they are not in these totals.${data.estimate && data.unconfirmed.not_estimated ? ` ${plural(data.unconfirmed.not_estimated, "sale", "sales")} could not be estimated.` : ""}</p>`
    : "";
  const body = data.summary.count || data.estimate
    ? `${summaryHtml(data.summary)}${tableHtml(data.groups, state, "")}`
    : `<p class="empty">No confirmed sales in this period.</p>`;
  return `<div class="card live-card"><div class="live-card-head"><h2>Realized gains and losses <span class="muted">${period}</span></h2>${groupByHtml(state.levels)}${sortByHtml(state.sort)}</div>`
    + `${controlsHtml(data, state)}${chip}${body}${estimateHtml(data.estimate, state)}`
    + `<p class="note">Confirmed ledger sales only; proceeds are net of fees. Short and long term follow the calendar rule.</p></div>`;
}

// ---- browser wiring ----
export function initRealized(doc = document, win = window) {
  const tabs = [...doc.querySelectorAll("[data-live-tab]")];
  const out = doc.getElementById("realizedBody"), live = doc.getElementById("liveBody");
  if (!tabs.length || !out || !live) return;
  let state = { ...DEFAULT_STATE }, data = null, shown = false, busy = false, again = false, stale = true, focusId = "", focusSel = "";
  const expanded = new Set();
  const remember = (key, value) => { try { win.localStorage.setItem(key, JSON.stringify(value)); } catch (err) { /* storage blocked: the choice just won't persist */ } };
  try { state.levels = normalizeLevels(JSON.parse(win.localStorage.getItem(LEVELS_KEY))); } catch (err) { /* nothing saved: the default */ }
  try { state.sort = normalizeSort(JSON.parse(win.localStorage.getItem(SORT_KEY))); } catch (err) { /* nothing saved: the default */ }

  // Rows are in document order (parents before children). A row shows only when its parent is expanded and itself shown.
  function applyExpanded() {
    if (!out.querySelectorAll) return;
    const shownPaths = new Set();
    out.querySelectorAll("tr[data-parent], tr.top-row").forEach((tr) => {
      const parent = tr.dataset.parent;
      const visible = parent === undefined || (shownPaths.has(parent) && expanded.has(parent));
      tr.hidden = !visible;
      if (visible && tr.dataset.path !== undefined) shownPaths.add(tr.dataset.path);
    });
    out.querySelectorAll("button.expand").forEach((b) => {
      const open = expanded.has(b.dataset.path);
      b.setAttribute("aria-expanded", open ? "true" : "false");
      b.textContent = (open ? "▾ " : "▸ ") + b.dataset.label;
    });
  }

  // Collapsing a row also forgets every expanded row below it (paths nest: a child's path starts with its parent's).
  const collapse = (path) => { for (const p of [...expanded]) if (p === path || p.startsWith(path + "/")) expanded.delete(p); };

  // The body is redrawn after every change; keep keyboard focus on the control just used.
  const render = () => {
    out.innerHTML = realizedViewHtml(data, state);
    applyExpanded();
    const el = focusSel ? out.querySelector(focusSel) : focusId && doc.getElementById(focusId);
    if (el && el.focus && !el.disabled) el.focus();
    focusId = focusSel = "";
  };

  async function load() {
    if (busy) { again = true; return; }
    busy = true;
    try {
      const resp = await win.fetch("/api/realized?" + realizedQuery(state, doc.body?.dataset?.scopeFrom));
      const json = await resp.json();
      data = !resp.ok || json.success === false ? { error: json.error || `HTTP ${resp.status}` } : json;
      stale = false;
    } catch (err) {
      data = { error: err && err.message ? err.message : String(err) };
    } finally {
      busy = false;
      render();
      if (again) { again = false; load(); }
    }
  }

  function showTab(name) {
    shown = name === "realized";
    tabs.forEach((b) => b.setAttribute("aria-pressed", b.dataset.liveTab === name ? "true" : "false"));
    live.hidden = shown;
    out.hidden = !shown;
    if (shown) { render(); if (stale) load(); }
  }

  out.addEventListener("change", (e) => {
    const id = e.target.id;
    if (id === "realizedSortField" || id === "realizedSortDir") {
      // The sort is applied here: no refetch, and the expanded rows stay open (their paths don't depend on it).
      state.sort = normalizeSort({ field: id === "realizedSortField" ? e.target.value : state.sort.field, dir: id === "realizedSortDir" ? e.target.value : state.sort.dir });
      remember(SORT_KEY, state.sort);
      focusId = id;
      if (data) render();
      return;
    }
    if (id === "realizedYear") state.taxYear = e.target.value;
    else if (id === "realizedTaxable") state.taxable = e.target.checked;
    else if (id === "realizedWash") state.wash = e.target.checked;
    else if (id === "realizedUnconfirmed") state.unconfirmed = e.target.checked;
    else return;
    focusId = id;
    load();
  });

  // A new grouping is built by the server, so it refetches; the old expanded rows no longer exist.
  function setLevels(next, sel) {
    state.levels = normalizeLevels(next);
    remember(LEVELS_KEY, state.levels);
    expanded.clear();
    focusSel = sel || "";
    load();
  }
  out.addEventListener("click", (e) => {
    const closest = (sel) => (e.target.closest ? e.target.closest(sel) : null);
    const step = closest("button.chip-step"), remove = closest("button.chip-remove"), add = closest("button.chip.off");
    const all = closest("button[data-realized-all]"), toggle = closest("button.expand");
    if (step) setLevels(stepLevel(state.levels, step.dataset.dim, Number(step.dataset.step)), `button.chip-step[data-dim="${step.dataset.dim}"][data-step="${step.dataset.step}"]`);
    else if (remove) setLevels(toggleLevel(state.levels, remove.dataset.dim), ".group-by button");
    else if (add) setLevels(toggleLevel(state.levels, add.dataset.dim), `button.chip-remove[data-dim="${add.dataset.dim}"]`);
    else if (all) {
      expanded.clear();
      if (all.dataset.realizedAll === "expand") out.querySelectorAll("tr[data-path]").forEach((tr) => expanded.add(tr.dataset.path));
      applyExpanded();
    } else if (toggle) {
      if (toggle.getAttribute("aria-expanded") !== "true") expanded.add(toggle.dataset.path); else collapse(toggle.dataset.path);
      applyExpanded();
    }
  });

  tabs.forEach((b) => b.addEventListener("click", () => showTab(b.dataset.liveTab)));
  doc.addEventListener("trends-scope-change", () => { stale = true; if (shown) load(); });
  onMoneyViewChange(() => { if (shown && data) render(); });
  showTab("holdings");
}

if (typeof document !== "undefined" && document.getElementById("realizedBody")) initRealized();
