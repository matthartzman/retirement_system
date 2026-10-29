// Recent Projections view (design: documentation/future/superpowers/plans/2026-10-29-trends-recent-projections-design.md).
// The next N years of the workbook's Net Worth and Cash Flow tables from /api/projections, with column
// groups that start collapsed (projection_groups.js) and a frozen Year column. Runs as its own module,
// like live_snapshot.js: the shared [data-view] toggle switches body.proj-mode and CSS hides the rest.
// renderProjections() and buildLine() are pure (exported for tests); mountProjections() wires the page.

import { moneyView, fmtAmount, onMoneyViewChange } from "./money_view.js";
import { buildTree, visibleColumns, windowRows, clampYears, windowTotal, reconcileNW, allGroupIds } from "./projection_groups.js";

export const VIEW_KEY = "trendsView_v1";   // shared with live_snapshot.js
export const KEYS = { table: "trends.proj.table", years: "trends.proj.years", open: (t) => `trends.proj.open.${t}` };
export const EMPTY_TEXT = "Recent Projections appear after the plan is rebuilt. Rebuild in the Retirement Planner, then refresh.";
const STALE_DAYS = 30;
const DASH = "–";
const TABLE_KEY = { nw: "net_worth", cf: "cash_flow" };

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]);
}

// One amount: percent view through money_view (a percent of today's net worth); dollars as $1,234
// with a true minus sign, or compact ($5.69M, $428k) on a narrow screen.
function amount(v, narrow) {
  if (typeof v !== "number" || !Number.isFinite(v)) return { text: DASH, neg: false };
  if (moneyView().shown !== "dollars") return { text: fmtAmount(v), neg: v < 0 };
  const a = Math.abs(v);
  let body;
  if (narrow && a >= 1e6) body = `${(a / 1e6).toFixed(2)}M`;
  else if (narrow && a >= 1e3) body = `${Math.round(a / 1e3)}k`;
  else body = Math.round(a).toLocaleString("en-US");
  return { text: `${Math.round(a) && v < 0 ? "−" : ""}$${body}`, neg: v < 0 && Math.round(a) !== 0 };
}

export function buildLine(builtAtIso, planChanged, now) {
  const built = new Date(builtAtIso);
  if (Number.isNaN(built.getTime())) return { text: "Workbook build date unknown", stale: true };
  const days = Math.max(0, Math.floor((now - built) / 86400000));
  const date = built.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  const time = built.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
  const age = days === 0 ? "today" : days === 1 ? "1 day ago" : `${days} days ago`;
  return { text: `Workbook built ${date} ${time} · ${age}`.replace(/\s/g, " "), stale: days > STALE_DAYS || !!planChanged };
}

function headerCell(c) {
  const cls = `proj-h d${c.depth} ${c.kind}${c.open ? " open" : ""}`;
  if (!c.expandable) return `<th scope="col" class="${cls}">${esc(c.label)}</th>`;
  return `<th scope="col" class="${cls}"><button type="button" class="proj-toggle" data-proj-group="${esc(c.id)}" aria-expanded="${c.open}">`
    + `<span aria-hidden="true">${c.open ? "▾" : "▸"}</span>&nbsp;${esc(c.label)}</button></th>`;
}

function cell(c, v, narrow) {
  const { text, neg } = amount(v, narrow);
  const cls = ["num", neg ? "neg" : "", c.kind === "detail" ? "d" : "", c.kind === "context" ? "ctx" : "", text === DASH ? "na" : ""]
    .filter(Boolean).join(" ");
  const title = c.kind === "context" ? ' title="Not part of the total"' : "";
  return `<td class="${cls}"${title}>${text}</td>`;
}

function actionsHtml(data, ui) {
  const tab = (t, label) => `<button type="button" data-proj-table="${t}" aria-pressed="${ui.table === t}">${label}</button>`;
  const line = data && !data.missing ? buildLine(data.built_at, data.plan_changed, ui.now) : null;
  return `<div class="live-actions proj-actions">`
    + `<div class="live-tabs" role="group" aria-label="Table">${tab("nw", "Net Worth")}${tab("cf", "Cash Flow")}</div>`
    + `<label class="proj-years">Years <input id="projYears" type="number" min="1" max="30" step="1" inputmode="numeric" value="${ui.years}"></label>`
    + `<button type="button" data-proj-all="expand">Expand all</button><button type="button" data-proj-all="collapse">Collapse all</button>`
    + (line ? `<span class="proj-build${line.stale ? " stale" : ""}">${esc(line.text)}</span>` : "")
    + (data && data.plan_changed ? `<span class="proj-flag">⚠ Plan changed since this build</span>` : "")
    + `</div>`;
}

export function renderProjections(data, ui) {
  if (!data || data.missing) return `<p class="live-error proj-empty">${esc(EMPTY_TEXT)}</p>`;
  const table = ((data.tables || {})[TABLE_KEY[ui.table]]) || { columns: [], rows: [] };
  const tree = buildTree(table, ui.table);
  const cols = visibleColumns(tree, ui.open);
  const { rows, endsAt } = windowRows(tree.rows, ui.now.getFullYear(), ui.years);
  const owners = data.owners || [];
  const yearCell = (r) => {
    const ages = (r.ages || []).filter((a) => a !== null && a !== undefined);
    const title = ages.length ? ` title="${esc(ages.map((a, i) => `${owners[i] || ""} ${a}`.trim()).join(" · "))}"` : "";
    return `<th scope="row" class="proj-year"${title}>${r.year}${ages.length ? `<span class="proj-ages">${ages.join(" / ")}</span>` : ""}</th>`;
  };
  const body = rows.map((r) => `<tr>${yearCell(r)}${cols.map((c) => cell(c, c.value(r), ui.narrow)).join("")}</tr>`).join("");
  let foot = "";
  if (ui.table === "cf" && rows.length) {
    const total = windowTotal(rows, cols);
    foot = `<tfoot><tr class="total-row"><th scope="row" class="proj-year">${rows.length}-yr total</th>`
      + cols.map((c) => cell(c, total[c.id], ui.narrow)).join("") + `</tr></tfoot>`;
  }
  const notes = [];
  if (ui.table === "nw") {
    const off = rows.filter((r) => Math.abs(reconcileNW(r)) >= 0.01);
    if (off.length) notes.push(`<p class="live-error">Net worth groups don't add up to Total NW in ${off.map((r) => r.year).join(", ")}`
      + ` (off by ${amount(reconcileNW(off[0]), false).text}). The workbook's figures are shown unchanged.</p>`);
  }
  if (endsAt !== null) notes.push(`<p class="note">The plan ends in ${endsAt}.</p>`);
  return actionsHtml(data, ui)
    + `<div class="live-card proj-card"><div class="table-wrap proj-wrap"><table class="live-table proj-table">`
    + `<thead><tr><th scope="col" class="proj-year">Year</th>${cols.map(headerCell).join("")}</tr></thead>`
    + `<tbody>${body}</tbody>${foot}</table></div>${notes.join("")}</div>`;
}

export function mountProjections(doc = document, win = window, clock = () => new Date()) {
  const body = doc.body;
  const section = doc.getElementById("projView");
  const out = doc.getElementById("projBody");
  if (!section || !out) return;
  const get = (k) => { try { return win.localStorage.getItem(k); } catch (err) { return null; } };
  const set = (k, v) => { try { win.localStorage.setItem(k, v); } catch (err) { /* storage blocked: the choice just won't persist */ } };
  const parseOpen = (raw) => { try { const a = JSON.parse(raw); return new Set(Array.isArray(a) ? a.map(String) : []); } catch (err) { return new Set(); } };

  let table = get(KEYS.table) === "cf" ? "cf" : "nw";
  let years = clampYears(get(KEYS.years));
  const open = { nw: parseOpen(get(KEYS.open("nw"))), cf: parseOpen(get(KEYS.open("cf"))) };
  let data = null, shown = false, busy = false;
  const mq = typeof win.matchMedia === "function" ? win.matchMedia("(max-width: 700px)") : null;

  const treeOf = (t) => buildTree(((data && data.tables) || {})[TABLE_KEY[t]] || { columns: [], rows: [] }, t);
  const saveOpen = (t) => set(KEYS.open(t), JSON.stringify([...open[t]]));
  function render() {
    out.innerHTML = renderProjections(data, { table, years, open: open[table], now: clock(), narrow: !!(mq && mq.matches) });
  }
  // A remembered group that no longer exists (a column renamed or a feature turned off) is forgotten.
  function pruneOpen() {
    if (!data || data.missing) return;
    for (const t of ["nw", "cf"]) {
      const ids = new Set(allGroupIds(treeOf(t)));
      for (const id of [...open[t]]) if (!ids.has(id)) open[t].delete(id);
    }
  }

  async function load() {
    if (busy) return;
    busy = true;
    try {
      const resp = await win.fetch("/api/projections");
      const json = await resp.json();
      if (!resp.ok || json.success === false) throw new Error(json.error || `HTTP ${resp.status}`);
      data = json;
      pruneOpen();
      render();
    } catch (err) {
      const msg = err && err.message ? err.message : String(err);
      out.innerHTML = `<p class="live-error">Couldn't load Recent Projections (${esc(msg)}).</p>`;
    } finally {
      busy = false;
    }
  }

  function show(next) {
    shown = next;
    body.classList.toggle("proj-mode", shown);
    section.hidden = !shown;
    if (shown) load();   // a rebuild since the last visit shows up on the next switch here
  }

  doc.addEventListener("click", (e) => {
    const btn = e.target && e.target.closest && e.target.closest("[data-view]");
    if (btn && btn.dataset.view) show(btn.dataset.view === "projections");
  });
  out.addEventListener("click", (e) => {
    const t = e.target && e.target.closest ? e.target : null;
    if (!t) return;
    const tab = t.closest("[data-proj-table]");
    if (tab) { table = tab.dataset.projTable === "cf" ? "cf" : "nw"; set(KEYS.table, table); render(); return; }
    const group = t.closest("[data-proj-group]");
    if (group) {
      const id = group.dataset.projGroup;
      if (open[table].has(id)) open[table].delete(id); else open[table].add(id);
      saveOpen(table); render(); return;
    }
    const all = t.closest("[data-proj-all]");
    if (all) {
      open[table] = all.dataset.projAll === "expand" ? new Set(allGroupIds(treeOf(table))) : new Set();
      saveOpen(table); render();
    }
  });
  out.addEventListener("change", (e) => {
    if (!e.target || e.target.id !== "projYears") return;
    years = clampYears(e.target.value);
    set(KEYS.years, String(years));
    render();
  });
  if (mq && typeof mq.addEventListener === "function") mq.addEventListener("change", () => { if (data) render(); });
  onMoneyViewChange(() => { if (data) render(); });

  show(get(VIEW_KEY) === "projections");
}

if (typeof document !== "undefined" && document.getElementById && document.getElementById("projView")) mountProjections();
