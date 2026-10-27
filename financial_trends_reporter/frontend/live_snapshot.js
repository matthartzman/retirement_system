// Live Snapshot view (design: documentation/future/superpowers/plans/2026-10-27-live-snapshot-design.md).
// Pure render/poll helpers are exported for tests; initLiveView() wires the toggle, the 60 s poll
// and the Refresh button in the browser. It runs as its own module so the Trends script is untouched:
// the toggle only switches body.live-mode, and CSS hides the trend cards and the time scope.

export const VIEW_KEY = "trendsView_v1";
export const POLL_MS = 60000;
const POLLING_STATES = new Set(["pre", "open", "post"]);
const DASH = "–";

export function parseSavedView(raw) {
  return raw === "live" ? "live" : "trends";
}

export function shouldPoll({ shown, visible, market }) {
  return Boolean(shown && visible && POLLING_STATES.has(market));
}

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

export function fmtUsd(v) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return DASH;
  const n = Number(v);
  return (n < 0 ? "-" : "") + "$" + Math.abs(n).toLocaleString("en-US", { maximumFractionDigits: 0 });
}

export function fmtPct(v, digits = 2) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return DASH;
  return (Number(v) * 100).toFixed(digits) + "%";
}

// A change with an arrow as well as a colour, so it reads without colour too.
export function changeHtml(v, isPct = false) {
  if (v === null || v === undefined) return `<span class="na">${DASH}</span>`;
  const text = isPct ? fmtPct(Math.abs(v)) : fmtUsd(v);
  if (v > 0) return `<span class="up">▲ ${text}</span>`;
  if (v < 0) return `<span class="down">▼ ${isPct ? "-" : ""}${text}</span>`;
  return `<span class="flat">${isPct ? fmtPct(0) : fmtUsd(0)}</span>`;
}

function clock(iso) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

export function statusText(data) {
  const state = data?.market?.state;
  const at = clock(data?.as_of);
  const parts = [];
  if (state === "closed") parts.push(`Market closed · last prices${at ? " at " + at : ""}`);
  else {
    const phase = state === "pre" ? "Pre-market" : state === "post" ? "After hours" : "Market open";
    parts.push(`${phase} · Delayed ~${data?.delayed_minutes ?? 15} min${at ? " · as of " + at : ""}`);
  }
  const stale = data?.liquid?.stale_symbols || [];
  if (stale.length) parts.push(`Old prices for ${stale.join(", ")}`);
  return parts.join(" · ");
}

const COLUMNS = [
  ["Start (12/31)", "col-start"], ["Bought since", "col-new"], ["Current", "col-cur"], ["Share", "col-share"],
  ["Day $", "col-day"], ["Day %", "col-daypct"], ["Market gain", "col-gain"], ["Return %", "col-ret"],
  ["Share of gain", "col-sog"], ["Annualized", "col-ann"],
];

function cells(r) {
  return [
    `<td class="num col-start">${fmtUsd(r.start)}</td>`,
    `<td class="num col-new">${r.new_money ? fmtUsd(r.new_money) : DASH}</td>`,
    `<td class="num col-cur">${fmtUsd(r.current)}</td>`,
    `<td class="num col-share">${fmtPct(r.share, 0)}</td>`,
    `<td class="num col-day">${changeHtml(r.day)}</td>`,
    `<td class="num col-daypct">${changeHtml(r.day_pct, true)}</td>`,
    `<td class="num col-gain">${changeHtml(r.market_gain)}</td>`,
    `<td class="num col-ret">${changeHtml(r.return_pct, true)}</td>`,
    `<td class="num col-sog">${fmtPct(r.share_of_gain, 1)}</td>`,
    `<td class="num col-ann">${fmtPct(r.annualized_pct)}</td>`,
  ].join("");
}

function liquidTable(caption, rows, total) {
  const head = `<tr><th scope="col">${esc(caption)}</th>${COLUMNS.map(([h, c]) => `<th scope="col" class="num ${c}">${h}</th>`).join("")}</tr>`;
  const body = rows.map((r) => {
    const tickers = r.tickers || [];
    const name = tickers.length
      ? `<button type="button" class="expand" aria-expanded="false" data-group="${esc(r.name)}">▸ ${esc(r.name)}</button>`
      : esc(r.name);
    const kids = tickers.map((t) => `<tr class="ticker-row" data-parent="${esc(r.name)}" hidden><th scope="row" class="ticker">${esc(t.symbol)}</th>${cells(t)}</tr>`).join("");
    return `<tr class="class-row"><th scope="row">${name}</th>${cells(r)}</tr>${kids}`;
  }).join("");
  const foot = total ? `<tfoot><tr class="total-row"><th scope="row">Total liquid</th>${cells({ ...total, share: 1, share_of_gain: 1 })}</tr></tfoot>` : "";
  return `<div class="table-wrap"><table class="live-table"><thead>${head}</thead><tbody>${body}</tbody>${foot}</table></div>`;
}

function simpleTable(rows, columns) {
  return `<div class="table-wrap"><table class="live-table simple"><tbody>${rows.map((r) =>
    `<tr>${columns.map((c, i) => (i === 0 ? `<th scope="row">${c(r)}</th>` : `<td class="num">${c(r)}</td>`)).join("")}</tr>`).join("")}</tbody></table></div>`;
}

// Hint wording lives here: the backend sends only kinds and numbers. Each line shows the numbers
// that prompted it and says "may" where it is a guess.
export function hintText(hint) {
  switch (hint?.kind) {
    case "after_balance_date":
      return `${hint.count} lot(s) bought after the imported balance date (${fmtUsd(hint.value)}). The imported balance can't include them yet.`;
    case "stale_prices":
      return `Old prices for ${(hint.symbols || []).join(", ")}.`;
    case "matches_position":
      return `The gap is close to ${hint.shares} sh ${hint.symbol}${hint.purchase_date ? " bought " + hint.purchase_date : ""} (${fmtUsd(hint.value)}).`;
    case "direction":
      return hint.higher === "holdings"
        ? "Holdings are higher: a sale or transfer out may not be entered yet."
        : "Holdings are lower: a purchase or transfer in may not be entered yet.";
    default:
      return "";
  }
}

function accountRowHtml(a) {
  const hasPct = a.delta_pct !== null && a.delta_pct !== undefined;
  const flag = a.flag ? `<span class="flag" title="${hasPct ? "Differs from the imported balance by more than 1% and $100" : "Differs from the imported balance by more than $100"}">⚠ <span class="flag-text">Check</span></span> ` : "";
  const monarch = (a.monarch_accounts || []).length ? ` <span class="muted">(${(a.monarch_accounts || []).map(esc).join(", ")})</span>` : "";
  const row = `<tr class="${a.flag ? "flagged" : ""}"><th scope="row">${flag}${esc(a.holdings_account)}${monarch}</th>`
    + `<td class="num">${fmtUsd(a.holdings_value)}</td><td class="num">${fmtUsd(a.monarch_value)}</td>`
    + `<td class="num">${changeHtml(a.delta)}</td><td class="num">${a.delta_pct === null || a.delta_pct === undefined ? DASH : changeHtml(a.delta_pct, true)}</td></tr>`;
  const hints = (a.hints || []).map(hintText).filter(Boolean);
  const hintRow = hints.length
    ? `<tr class="hint-row"><td colspan="5"><ul class="hints">${hints.map((h) => `<li>${esc(h)}</li>`).join("")}</ul></td></tr>` : "";
  return row + hintRow;
}

function accountsSectionHtml(rec) {
  const accounts = rec.accounts;
  if (!Array.isArray(accounts)) return "";
  const flagged = accounts.some((a) => a.flag);
  const unmappedMonarch = rec.unmapped_monarch || [], unmappedHoldings = rec.unmapped_holdings || [];
  const head = `<tr><th scope="col">Account</th><th scope="col" class="num">Holdings</th><th scope="col" class="num">Imported</th>`
    + `<th scope="col" class="num">Difference</th><th scope="col" class="num">%</th></tr>`;
  const foot = `<tfoot><tr class="total-row"><th scope="row">Holdings total</th><td class="num">${fmtUsd(rec.footing)}</td><td></td><td></td><td></td></tr></tfoot>`;
  const table = `<div class="table-wrap"><table class="live-table recon-table"><thead>${head}</thead><tbody>${accounts.map(accountRowHtml).join("")}</tbody>${foot}</table></div>`;
  const stale = rec.monarch_stale
    ? `<p class="note warn-text">Imported balances are from ${esc(rec.monarch_as_of || "an earlier day")}; moves since then aren't backed out.</p>` : "";
  const unmapped = unmappedMonarch.length || unmappedHoldings.length
    ? `<p class="note">Not linked to a holdings account, so not compared. Link them in the Retirement Planner.</p>`
      + (unmappedMonarch.length ? `<p class="note"><b>Imported accounts:</b> ${unmappedMonarch.map((u) => `${esc(u.name)} ${fmtUsd(u.value)}`).join("; ")}</p>` : "")
      + (unmappedHoldings.length ? `<p class="note"><b>Holdings accounts:</b> ${unmappedHoldings.map((u) => `${esc(u.account)} ${fmtUsd(u.value)}`).join("; ")}</p>` : "")
    : "";
  const count = accounts.filter((a) => a.flag).length;
  const summary = `Reconciliation by account${count ? ` <b>⚠ ${count} to check</b>` : ""}`;
  return `<details class="live-section recon-accounts"${flagged ? " open" : ""}><summary>${summary}</summary>${stale}${table}${unmapped}</details>`;
}

function reconciliationHtml(rec) {
  if (!rec) return "";
  const pct = rec.delta_pct === null || rec.delta_pct === undefined ? DASH : fmtPct(Math.abs(rec.delta_pct));
  const warn = rec.flag ? " Check the Investment Holdings page in the Retirement Planner for trades or transfers not yet entered." : "";
  return `<div class="recon${rec.flag ? " warn" : ""}" role="${rec.flag ? "alert" : "status"}">Holdings file ${fmtUsd(rec.holdings_value)} vs. imported balances ${fmtUsd(rec.monarch_value)} (${esc(rec.monarch_as_of || "")}): ${pct} apart.${warn}</div>`
    + accountsSectionHtml(rec);
}

const TREATMENT = { pre_tax: "Taxed in full", after_tax: "Taxed above premium", none: "Not taxed" };

function taxHtml(tax) {
  const lines = [
    ["Pre-tax holdings (IRA, 401k)", tax.pre_tax_balance],
    ["Joint annuities and pension", tax.pre_tax_non_liquid],
    ["Single-life annuity growth above premium", tax.annuity_taxable_gain],
  ];
  const missing = (tax.basis_missing || []).length
    ? `<p class="note warn-text">After-tax premium not set for ${tax.basis_missing.map(esc).join(", ")}: not taxed until it is (annuity_basis in live_snapshot_settings.json).</p>`
    : "";
  return simpleTable(lines.map(([label, v]) => ({ label, v })), [(r) => esc(r.label), (r) => fmtUsd(r.v)])
    + `<p class="note">Ordinary income above × ${fmtPct(tax.pre_tax_rate, 0)}, plus taxable-account unrealized gains of ${fmtUsd(tax.unrealized_gain)} × ${fmtPct(tax.ltcg_rate, 0)}. An estimate, not a tax calculation.</p>`
    + missing;
}

function totalsHtml(t, checking, debt, tax, nonLiquid, liquid) {
  const steps = [
    ["Liquid investments", liquid.current], ["Checking", checking.total], ["Non-liquid assets", nonLiquid.total],
    ["Debt", -debt.total], ["Net assets", t.net_assets], ["Estimated tax", -tax.total], ["After-tax net worth", t.after_tax_net_worth],
  ];
  const kinds = Object.entries(t.by_kind || {}).map(([k, v]) =>
    `<span class="kind-chip">${esc(k)} <b>${fmtUsd(v)}</b> <span class="muted">${fmtPct(t.gross_assets ? v / t.gross_assets : null, 0)}</span></span>`).join("");
  return `<div class="totals-band">${steps.map(([label, v], i) =>
    `<div class="total-step${i === 4 || i === 6 ? " strong" : ""}"><span>${label}</span><b>${fmtUsd(v)}</b></div>`).join("")}</div>`
    + `<div class="kinds" aria-label="Assets by kind (share of gross assets)">${kinds}</div>`;
}

export function liveViewHtml(data) {
  if (!data) return `<p class="empty">Loading live prices…</p>`;
  if (data.error) return `<p class="live-error">Live Snapshot is unavailable: ${esc(data.error)}</p>`;
  const L = data.liquid, t = data.totals;
  const indices = (data.indices || []).map((i) =>
    `<span class="index-chip">${esc(i.label)} ${i.day_pct === null || i.day_pct === undefined ? `<span class="na">${DASH}</span>` : changeHtml(i.day_pct, true)}</span>`).join("");
  const head = `<div class="live-head"><div><div class="live-label">After-tax net worth</div><div class="live-big">${fmtUsd(t.after_tax_net_worth)}</div>`
    + `<div class="live-sub">Liquid today ${changeHtml(L.day)} (${changeHtml(L.day_pct, true)}) · Year to date ${changeHtml(L.market_gain)} (${changeHtml(L.return_pct, true)})</div></div>`
    + `<div class="live-right"><div class="indices">${indices}</div><div class="live-status" role="status">${esc(statusText(data))}</div></div></div>`;
  const flows = L.checking_net_flows === null || L.checking_net_flows === undefined ? ""
    : ` Net transfers from checking this year: ${fmtUsd(L.checking_net_flows)} (for information).`;
  const liquid = `<div class="card live-card"><h2>Liquid investments</h2>${liquidTable("Asset class", L.by_class, L)}`
    + `<h3>Equity by sub-class</h3>${liquidTable("Sub-class", L.by_equity_subclass, null)}${reconciliationHtml(data.reconciliation)}`
    + `<p class="note">Start = 12/31 value of lots held then. Bought since = lots bought after 12/31, at purchase price; reinvested dividends count as gain. Return % weights new money by how long it was invested (Modified Dietz). Gains on positions sold this year are not included.${flows}</p></div>`;
  const nl = data.non_liquid;
  const nonLiquid = `<details class="live-section"><summary>Non-liquid assets <b>${fmtUsd(nl.total)}</b> <span class="muted">imported balances, ${esc(nl.as_of || "")}</span></summary>`
    + simpleTable(nl.rows, [(r) => esc(r.name), (r) => esc(r.kind), (r) => fmtUsd(r.value), (r) => fmtPct(r.share, 0), (r) => esc(TREATMENT[r.tax_treatment] || "")]) + `</details>`;
  const tax = `<details class="live-section"><summary>Estimated tax <b>${fmtUsd(-data.tax.total)}</b></summary>${taxHtml(data.tax)}</details>`;
  const debt = `<details class="live-section"><summary>Debt <b>${fmtUsd(-data.debt.total)}</b></summary>`
    + simpleTable(data.debt.rows, [(r) => esc(r.name), (r) => fmtUsd(r.value)])
    + `<p class="note">Checking: ${fmtUsd(data.checking.total)} across ${data.checking.rows.length} account(s).</p></details>`;
  return head + liquid + `<div class="card live-card">${totalsHtml(t, data.checking, data.debt, data.tax, nl, L)}${nonLiquid}${tax}${debt}</div>`;
}

// ---- browser wiring ----
export function initLiveView(doc = document, win = window) {
  const body = doc.body;
  const section = doc.getElementById("liveView");
  const out = doc.getElementById("liveBody");
  const errorBox = doc.getElementById("liveError");
  const buttons = [...doc.querySelectorAll("[data-view]")];
  let view = "trends", data = null, lastLoad = 0, busy = false;
  const expanded = new Set(), openSections = new Map();

  try { view = parseSavedView(win.localStorage.getItem(VIEW_KEY)); } catch (err) { view = "trends"; }

  // Only a section the user opened or closed themselves is remembered (recorded on the summary click),
  // so the server's default -- the reconciliation section opening when an account flags -- applies
  // until then. Keyed by name for the reconciliation section and by position among the others, so a
  // section that appears or disappears between refreshes doesn't shift the rest.
  function sectionKeys() {
    let n = 0;
    return (d) => (d.classList.contains("recon-accounts") ? "recon-accounts" : n++);
  }

  function render() {
    out.innerHTML = liveViewHtml(data);
    const key = sectionKeys();
    out.querySelectorAll("details.live-section").forEach((d) => { const k = key(d); if (openSections.has(k)) d.open = openSections.get(k); });
    out.querySelectorAll("button.expand").forEach((b) => { if (expanded.has(b.dataset.group)) toggleGroup(b, true); });
  }

  function toggleGroup(button, open) {
    button.setAttribute("aria-expanded", open ? "true" : "false");
    button.textContent = (open ? "▾ " : "▸ ") + button.dataset.group;
    out.querySelectorAll("tr.ticker-row").forEach((tr) => { if (tr.dataset.parent === button.dataset.group) tr.hidden = !open; });
  }

  async function load(force = false) {
    if (busy) return;
    busy = true;
    try {
      const resp = await win.fetch("/api/live-snapshot" + (force ? "?refresh=1" : ""));
      const json = await resp.json();
      if (!resp.ok || json.success === false) throw new Error(json.error || `HTTP ${resp.status}`);
      data = json;
      lastLoad = Date.now();
      errorBox.textContent = "";
      render();
    } catch (err) {
      const msg = err && err.message ? err.message : String(err);
      errorBox.textContent = data
        ? `Couldn't update prices (${msg}). Showing the values from ${clock(data.as_of)}.`
        : `Couldn't load the Live Snapshot (${msg}).`;
      if (!data) out.innerHTML = "";
    } finally {
      busy = false;
    }
  }

  function setView(next) {
    view = next;
    body.classList.toggle("live-mode", view === "live");
    section.hidden = view !== "live";
    buttons.forEach((b) => b.setAttribute("aria-pressed", b.dataset.view === view ? "true" : "false"));
    try { win.localStorage.setItem(VIEW_KEY, view); } catch (err) { /* storage blocked: the choice just won't persist */ }
    if (view === "live" && Date.now() - lastLoad >= POLL_MS) { if (!data) render(); load(); }
  }

  buttons.forEach((b) => b.addEventListener("click", () => setView(b.dataset.view)));
  doc.getElementById("liveRefresh").addEventListener("click", () => load(true));
  out.addEventListener("click", (e) => {
    const summary = e.target.closest("summary");
    if (summary && summary.parentElement && summary.parentElement.matches("details.live-section")) {
      const d = summary.parentElement, key = sectionKeys();
      let k;
      out.querySelectorAll("details.live-section").forEach((x) => { const kx = key(x); if (x === d) k = kx; });
      openSections.set(k, !d.open);   // the click's default action flips it after this handler
      return;
    }
    const b = e.target.closest("button.expand");
    if (!b) return;
    const open = b.getAttribute("aria-expanded") !== "true";
    if (open) expanded.add(b.dataset.group); else expanded.delete(b.dataset.group);
    toggleGroup(b, open);
  });
  const tick = () => {
    const due = Date.now() - lastLoad >= POLL_MS - 5000;
    if (due && shouldPoll({ shown: view === "live", visible: doc.visibilityState === "visible", market: data?.market?.state })) load();
  };
  win.setInterval(tick, POLL_MS);
  doc.addEventListener("visibilitychange", tick);
  setView(view);
}

if (typeof document !== "undefined" && document.getElementById("liveView")) initLiveView();
