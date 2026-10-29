// Realized gains and losses (sales ledger plan 9.2): confirmed ledger sales in the Time scope (or a tax year),
// grouped by symbol or account with their lots. A "Realized" tab inside the Live Snapshot area; the data comes from
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

export const DEFAULT_STATE = Object.freeze({ group: "symbol", taxYear: "", taxable: false, wash: false, unconfirmed: false });

const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const ratio = (n, d) => (n === null || n === undefined || !d ? null : n / d);
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

// The request: the shared Time scope's first day, unless a tax year is picked.
export function realizedQuery(state, scopeFrom) {
  const p = new URLSearchParams();
  if (state.taxYear) p.set("tax_year", String(state.taxYear)); else if (scopeFrom) p.set("from", scopeFrom);
  p.set("group", state.group === "account" ? "account" : "symbol");
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
    + `<label>Group by <select id="realizedGroup"><option value="symbol"${state.group !== "account" ? " selected" : ""}>Symbol</option><option value="account"${state.group === "account" ? " selected" : ""}>Account</option></select></label>`
    + check("realizedTaxable", "taxable", "Taxable accounts only") + check("realizedWash", "wash", "Wash-flagged only")
    + check("realizedUnconfirmed", "unconfirmed", "Include unconfirmed (estimate)") + `</div>`;
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

function lotRow(l) {
  const when = `${esc(l.sale_date)}${l.purchase_date ? ` · bought ${esc(l.purchase_date)}` : ""}`;
  const flags = [l.wash_flag && l.wash_flag !== "none" ? "wash" : "", l.estimate ? "estimate" : ""].filter(Boolean).join(", ");
  const dollars = isPct() ? "" : `<td class="num">${esc(l.shares)}</td><td class="num">${money(l.proceeds)}</td><td class="num">${money(l.basis)}</td><td class="num">${gainText(l.gain)}</td>`;
  return `<tr class="sale-lot"><th scope="row">${when}</th>${dollars}<td class="num">${returnText(l.gain, l.basis)}</td>`
    + `<td>${esc(TERMS[l.term] || DASH)}</td><td>${esc(SOURCES[l.source] || l.source || DASH)}</td><td>${esc(flags) || DASH}</td><td>${esc(STATUS_1099[l.status_1099] || DASH)}</td></tr>`;
}

function tableHtml(groups, by) {
  if (!groups.length) return "";
  const dollarHeads = isPct() ? "" : `<th scope="col" class="num">Shares</th><th scope="col" class="num">Proceeds</th><th scope="col" class="num">Basis</th><th scope="col" class="num">Gain</th>`;
  const head = `<thead><tr><th scope="col">${by === "account" ? "Account" : "Symbol"} / lot</th>${dollarHeads}<th scope="col" class="num">Return</th><th scope="col">Term</th><th scope="col">Source</th><th scope="col">Flags</th><th scope="col">1099-B</th></tr></thead>`;
  const body = groups.map((g) => {
    const dollars = isPct() ? "" : `<td></td><td class="num">${money(g.proceeds)}</td><td class="num">${money(g.basis)}</td><td class="num">${gainText(g.net)}</td>`;
    return `<tbody><tr class="top-row"><th scope="row">${esc(g.name)} <span class="muted">${plural(g.count, "lot", "lots")}</span></th>${dollars}<td class="num">${returnText(g.net, g.basis)}</td><td></td><td></td><td></td><td></td></tr>`
      + `${(g.lots || []).map(lotRow).join("")}</tbody>`;
  }).join("");
  return `<div class="table-scroll"><table class="live-table realized-table">${head}${body}</table></div>`;
}

function estimateHtml(est, by) {
  if (!est) return "";
  const inner = est.count
    ? `${summaryHtml(est)}${tableHtml(est.groups, by)}`
    : `<p class="empty">No waiting sale could be valued.</p>`;
  return `<details class="live-section estimate" open><summary>Estimate for sales not yet confirmed</summary>`
    + `<p class="note">Estimate only: each is valued at its imported amount with first-in-first-out lots from today's holdings. Not in the totals above, and never used for tax, the projection or the daily log.</p>${inner}</details>`;
}

export function realizedViewHtml(data, state = DEFAULT_STATE) {
  if (!data) return `<p class="empty">Loading realized sales…</p>`;
  if (data.error) return `<p class="live-error">Realized sales are unavailable: ${esc(data.error)}</p>`;
  const w = data.window || {};
  const period = w.tax_year ? `Tax year ${w.tax_year}` : `Since ${esc(w.from)}`;
  const waiting = data.unconfirmed?.count ?? 0;
  const chip = waiting
    ? `<p class="note"><span class="chip warn">${plural(waiting, "sale", "sales")} waiting for lots</span> Confirm the lots in the Retirement Planner's Sales ledger page; until then they are not in these totals.${data.estimate && data.unconfirmed.not_estimated ? ` ${plural(data.unconfirmed.not_estimated, "sale", "sales")} could not be estimated.` : ""}</p>`
    : "";
  const body = data.summary.count || data.estimate
    ? `${summaryHtml(data.summary)}${tableHtml(data.groups, data.group_by)}`
    : `<p class="empty">No confirmed sales in this period.</p>`;
  return `<div class="card live-card"><div class="live-card-head"><h2>Realized gains and losses <span class="muted">${period}</span></h2></div>`
    + `${controlsHtml(data, state)}${chip}${body}${estimateHtml(data.estimate, data.group_by)}`
    + `<p class="note">Confirmed ledger sales only; proceeds are net of fees. Short and long term follow the calendar rule.</p></div>`;
}

// ---- browser wiring ----
export function initRealized(doc = document, win = window) {
  const tabs = [...doc.querySelectorAll("[data-live-tab]")];
  const out = doc.getElementById("realizedBody"), live = doc.getElementById("liveBody");
  if (!tabs.length || !out || !live) return;
  let state = { ...DEFAULT_STATE }, data = null, shown = false, busy = false, again = false, stale = true, focusId = "";

  // The body is redrawn after every change; keep keyboard focus on the control just used.
  const render = () => {
    out.innerHTML = realizedViewHtml(data, state);
    const el = focusId && doc.getElementById(focusId);
    if (el && el.focus) el.focus();
    focusId = "";
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
    if (id === "realizedYear") state.taxYear = e.target.value;
    else if (id === "realizedGroup") state.group = e.target.value;
    else if (id === "realizedTaxable") state.taxable = e.target.checked;
    else if (id === "realizedWash") state.wash = e.target.checked;
    else if (id === "realizedUnconfirmed") state.unconfirmed = e.target.checked;
    else return;
    focusId = id;
    load();
  });
  tabs.forEach((b) => b.addEventListener("click", () => showTab(b.dataset.liveTab)));
  doc.addEventListener("trends-scope-change", () => { stale = true; if (shown) load(); });
  onMoneyViewChange(() => { if (shown && data) render(); });
  showTab("holdings");
}

if (typeof document !== "undefined" && document.getElementById("realizedBody")) initRealized();
