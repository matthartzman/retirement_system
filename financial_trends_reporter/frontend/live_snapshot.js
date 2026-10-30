// Current Snapshot view (design: documentation/future/superpowers/plans/2026-10-27-live-snapshot-design.md).
// Pure render/poll helpers are exported for tests; initLiveView() wires the toggle, the 60 s poll
// and the Refresh button in the browser. It runs as its own module so the Trends script is untouched:
// the toggle only switches body.live-mode, and CSS hides the trend cards. The Time scope is shared: its
// first day (body[data-scope-from]) sets the Start date.

import { moneyView, fmtAmount, onMoneyViewChange, unitChip } from "./money_view.js";
import { DIMENSIONS, DEFAULT_ORDER, GROUPS_KEY, SORT_KEY, SORT_FIELDS, normalizeSort, parseSavedSort, normalizeOrder, parseSavedOrder, stepDimension, toggleDimension, dropOrder, buildTree } from "./live_groups.js";

const isPct = () => moneyView().shown === "percent";

export const VIEW_KEY = "trendsView_v1";
export const POLL_MS = 60000;
const POLLING_STATES = new Set(["pre", "open", "post"]);
const DASH = "–";

export function parseSavedView(raw) {
  return raw === "live" || raw === "projections" ? raw : "trends";   // projections: Recent Projections (projections.js)
}

export function shouldPoll({ shown, visible, market }) {
  return Boolean(shown && visible && POLLING_STATES.has(market));
}

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

export function fmtUsd(v) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return DASH;
  if (moneyView().shown !== "dollars") return fmtAmount(v);
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

// The Start date follows the page's Time scope (the close before its first day); liveViewHtml sets it.
let startDay = "12/31";

// "9/25", or "9/25/25" when the start is in an earlier year than ``asOf`` and isn't the year-end close.
export function startDayText(baselineDate, asOf) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(baselineDate || ""));
  if (!m) return "12/31";
  const md = `${Number(m[2])}/${Number(m[3])}`;
  const asOfYear = Number(String(asOf || "").slice(0, 4)) || Number(m[1]);
  return Number(m[1]) < asOfYear && !isYearToDate(baselineDate, asOf) ? `${md}/${m[1].slice(2)}` : md;
}

// The start is the prior year's last close (12/24 at the earliest): the period is year to date.
export function isYearToDate(baselineDate, asOf) {
  const m = /^(\d{4})-12-(\d{2})/.exec(String(baselineDate || ""));
  const asOfYear = Number(String(asOf || "").slice(0, 4));
  return Boolean(m) && Number(m[2]) >= 24 && (!asOfYear || Number(m[1]) === asOfYear - 1);
}

const columns = () => [
  [`Start (${startDay})`, "col-start"], ["Bought since", "col-new"], ["Current", "col-cur"], ["Share", "col-share"],
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

export function fmtUsd2(v) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return DASH;
  if (moneyView().shown !== "dollars") return fmtAmount(v);
  const n = Number(v);
  return (n < 0 ? "-" : "") + "$" + Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// "2024-03-15 · 120 @ $412.10", plus " · reinvested". An undated lot reads "Undated"; a lot with
// no purchase price leaves the "@ price" off rather than showing a made-up one.
// A sold lot (a confirmed ledger sale) reads "2025-06-01 · sold"; the Cash row that takes its proceeds in reads
// "Sale proceeds". Neither shows shares or a price.
export function lotLabel(lot) {
  if (lot.sold) return String(lot.symbol || "").toUpperCase().startsWith("CASH") ? "Sale proceeds" : `${lot.purchase_date || "Undated"} · sold`;
  const parts = [lot.purchase_date || "Undated"];
  const hasShares = lot.shares !== null && lot.shares !== undefined && !Number.isNaN(Number(lot.shares));
  const hasPrice = lot.purchase_price !== null && lot.purchase_price !== undefined && !Number.isNaN(Number(lot.purchase_price));
  if (hasShares) parts.push(`${Number(lot.shares)}${hasPrice ? " @ " + fmtUsd2(lot.purchase_price) : ""}`);
  if (lot.reinvested) parts.push("reinvested");
  return parts.join(" · ");
}

// Rows are a tree built by live_groups.js from the flat lot list, in the order chosen in the Group By row.
// A node's path (its levels, URL-encoded) keys its expanded state; rows below the top carry data-parent.
// {holdings account id: display label} from the payload, e.g. Member_1_401k -> "Matt 401k". Ids stay the keys.
let accountLabels = {};
const acctLabel = (id) => accountLabels[id] || id;

function expandButton(path, label) {
  return `<button type="button" class="expand" aria-expanded="false" data-path="${esc(path)}" data-label="${esc(label)}">▸ ${esc(label)}</button>`;
}

// The Group By row: the levels in use (drag a chip, or use its arrows, to reorder; x drops it), Lot always
// last, then the unused levels (click or drag one in to add it).
export function groupByHtml(order) {
  const levels = normalizeOrder(order).filter((d) => d !== "lot");
  const unused = Object.keys(DIMENSIONS).filter((d) => d !== "lot" && !levels.includes(d));
  const name = (d) => esc(DIMENSIONS[d]);
  const chip = (dim, i) => `<span class="chip" draggable="true" data-dim="${dim}">`
    + `<button type="button" class="chip-step" data-dim="${dim}" data-step="-1" aria-label="Move ${name(dim)} earlier"${i === 0 ? " disabled" : ""}>◂</button>`
    + `<span class="chip-name">${name(dim)}</span>`
    + `<button type="button" class="chip-step" data-dim="${dim}" data-step="1" aria-label="Move ${name(dim)} later"${i === levels.length - 1 ? " disabled" : ""}>▸</button>`
    + `<button type="button" class="chip-remove" data-dim="${dim}" aria-label="Stop grouping by ${name(dim)}">×</button></span>`;
  return `<div class="group-by" role="group" aria-label="Group by"><span class="group-by-label">Group by</span>${levels.map(chip).join("")}`
    + `<span class="chip fixed" data-dim="lot" title="Lots are always the last level">Lot</span>`
    + unused.map((dim) => `<button type="button" class="chip off" draggable="true" data-dim="${dim}" aria-label="Also group by ${name(dim)}">+ ${name(dim)}</button>`).join("") + `</div>`;
}

// The Sort by row, after Group By: a field picklist and an ascending/descending picklist.
export function sortByHtml(sort) {
  const cur = normalizeSort(sort);
  const opt = (value, label, on) => `<option value="${value}"${on ? " selected" : ""}>${esc(label)}</option>`;
  return `<div class="sort-by" role="group" aria-label="Sort by"><label class="group-by-label" for="liveSortField">Sort by</label>`
    + `<select id="liveSortField" aria-label="Sort by field">${Object.entries(SORT_FIELDS).map(([f, [label]]) => opt(f, label, f === cur.field)).join("")}</select>`
    + `<select id="liveSortDir" aria-label="Sort direction">${opt("asc", "Ascending", cur.dir === "asc")}${opt("desc", "Descending", cur.dir === "desc")}</select></div>`;
}

function groupedTable(tree, firstLabel, total) {
  const head = `<tr><th scope="col">${esc(firstLabel)}</th>${columns().map(([h, c]) => `<th scope="col" class="num ${c}">${h}</th>`).join("")}</tr>`;
  const rows = (nodes, depth) => nodes.map((n) => {
    const kids = n.children.length > 0;
    const title = n.title ? ` <span class="muted ticker-title">${esc(n.title)}</span>` : "";
    const date = n.inline ? ` <span class="muted">· ${esc(n.inline)}</span>` : "";
    const label = n.lot ? esc(lotLabel(n.lot)) : (kids ? expandButton(n.path, n.label) : esc(n.label)) + title + date;
    const attrs = `data-depth="${depth}"${kids ? ` data-path="${esc(n.path)}"` : ""}${depth ? ` data-parent="${esc(n.parent)}" hidden` : ""}`;
    return `<tr${depth ? "" : ' class="top-row"'} ${attrs}><th scope="row" class="dim-${n.dim}">${label}</th>${cells(n.row)}</tr>${rows(n.children, depth + 1)}`;
  }).join("");
  const foot = total ? `<tfoot><tr class="total-row"><th scope="row">Total liquid</th>${cells({ ...total, share: 1, share_of_gain: 1 })}</tr></tfoot>` : "";
  return `<div class="table-wrap"><table class="live-table"><thead>${head}</thead><tbody>${rows(tree.nodes, 0)}</tbody>${foot}</table></div>`;
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
    case "unmatched_sale": {
      // The percent form names the sale without its size.
      const what = isPct() || hint.shares === null || hint.shares === undefined ? `A sale of ${hint.symbol}` : `Sale of ~${hint.shares} ${hint.symbol} on ${hint.sale_date}`;
      return what + (hint.confirmed ? " is in the ledger; holdings or the imported balance may not reflect it yet." : " is waiting to be confirmed.");
    }
    case "sale_not_in_holdings":
      return "Holdings still list the lot you sold.";
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
  // Only a balance more than a session old says when it synced; holdings are valued at that day's close.
  const synced = a.balance_stale && a.balance_as_of ? ` <span class="muted synced">· last synced ${esc(a.balance_as_of)}</span>` : "";
  const row = `<tr class="${a.flag ? "flagged" : ""}"><th scope="row">${flag}${esc(acctLabel(a.holdings_account))}${monarch}${synced}</th>`
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
  const unmappedMonarch = rec.unmapped_monarch || [], unmappedHoldings = rec.unmapped_holdings || [];
  const head = `<tr><th scope="col">Account</th><th scope="col" class="num">Holdings</th><th scope="col" class="num">Imported</th>`
    + `<th scope="col" class="num">Difference</th><th scope="col" class="num">%</th></tr>`;
  const foot = `<tfoot><tr class="total-row"><th scope="row">Holdings total</th><td class="num">${fmtUsd(rec.footing)}</td><td></td><td></td><td></td></tr></tfoot>`;
  const table = `<div class="table-wrap"><table class="live-table recon-table"><thead>${head}</thead><tbody>${[...accounts].sort((x, y) => acctLabel(x.holdings_account).localeCompare(acctLabel(y.holdings_account), undefined, { sensitivity: "base" })).map(accountRowHtml).join("")}</tbody>${foot}</table></div>`;
  const stale = rec.monarch_stale
    ? `<p class="note warn-text">Imported balances are from ${esc(rec.monarch_as_of || "an earlier day")}; moves since then aren't backed out.</p>` : "";
  const unmapped = unmappedMonarch.length || unmappedHoldings.length
    ? `<p class="note">Not linked to a holdings account, so not compared. Link them in the Retirement Planner.</p>`
      + (unmappedMonarch.length ? `<p class="note"><b>Imported accounts:</b> ${unmappedMonarch.map((u) => `${esc(u.name)} ${fmtUsd(u.value)}`).join("; ")}</p>` : "")
      + (unmappedHoldings.length ? `<p class="note"><b>Holdings accounts:</b> ${unmappedHoldings.map((u) => `${esc(acctLabel(u.account))} ${fmtUsd(u.value)}`).join("; ")}</p>` : "")
    : "";
  const count = accounts.filter((a) => a.flag).length;
  const summary = `Reconciliation by account${count ? ` <b>⚠ ${count} to check</b>` : ""}`;
  return `<details class="live-section recon-accounts"><summary>${summary}</summary>${stale}${table}${unmapped}</details>`;
}

function reconciliationHtml(rec) {
  if (!rec) return "";
  const pct = rec.delta_pct === null || rec.delta_pct === undefined ? DASH : fmtPct(Math.abs(rec.delta_pct));
  const warn = rec.flag ? " Check the Investment Holdings page in the Retirement Planner for trades or transfers not yet entered." : "";
  return `<div class="recon${rec.flag ? " warn" : ""}" role="${rec.flag ? "alert" : "status"}">Holdings file ${fmtUsd(rec.holdings_value)} vs. imported balances ${fmtUsd(rec.monarch_value)} (${esc(rec.monarch_as_of || "")}): ${pct} apart.${warn}</div>`
    + accountsSectionHtml(rec);
}

const TREATMENT = { pre_tax: "Taxed in full", after_tax: "Taxed above premium", note_interest: "Interest taxed", none: "Not taxed" };

function taxHtml(tax) {
  const planner = tax.method === "planner";
  const ord = (v) => v * tax.pre_tax_rate;
  const ltcgRate = tax.ltcg_rate ?? (tax.unrealized_gain ? tax.ltcg_tax / tax.unrealized_gain : null);
  const lines = [
    ["Pre-tax holdings (IRA, 401k)", tax.pre_tax_balance, ord(tax.pre_tax_balance), tax.pre_tax_rate],
    ["Joint annuities and pension", tax.pre_tax_non_liquid, ord(tax.pre_tax_non_liquid), tax.pre_tax_rate],
    ["Single-life annuity growth above premium", tax.annuity_taxable_gain, ord(tax.annuity_taxable_gain), tax.pre_tax_rate],
    ["Taxable and trust accounts: unrealized gains", tax.unrealized_gain, tax.ltcg_tax ?? tax.unrealized_gain * tax.ltcg_rate, ltcgRate],
  ];
  // Notes receivable: only the interest in the remaining payments is income (the Planner's interest schedule).
  for (const n of tax.note_rows || []) lines.splice(3, 0, [`Note interest still to be paid (${n.name})`, n.interest, ord(n.interest), tax.pre_tax_rate]);
  if (planner && tax.hsa_balance) lines.push(["HSA balance (taxed if not left to a spouse)", tax.hsa_balance, tax.hsa_tax, tax.hsa_balance ? tax.hsa_tax / tax.hsa_balance : null]);
  const missing = (tax.basis_missing || []).length
    ? `<p class="note warn-text">After-tax premium not set for ${tax.basis_missing.map(esc).join(", ")}: not taxed until it is (Tax Treatment and After-Tax Premium on the Retirement Planner's Accounts &amp; Sources page).</p>`
    : "";
  const head = `<thead><tr><th scope="col">Source</th>${isPct() ? "" : `<th scope="col" class="num">Taxable amount</th>`}<th scope="col" class="num">Rate</th><th scope="col" class="num">Est. tax</th></tr></thead>`;
  const body = lines.map(([label, base, t, rate]) =>
    `<tr><th scope="row">${esc(label)}</th>${isPct() ? "" : `<td class="num">${fmtUsd(base)}</td>`}<td class="num">${rate === null || rate === undefined ? DASH : fmtPct(rate, 1)}</td><td class="num">${fmtUsd(t)}</td></tr>`).join("");
  const d = tax.ltcg_detail;
  const how = moneyView().allowed === "percent"
    ? `<p class="note">Estimated with the Retirement Planner's tax method applied to today's balances: pre-tax money taxed as ordinary income, taxable-account gains from the lots' cost basis. Est. tax is a percent of net worth.</p>`
    : planner
    ? `<p class="note">Same method as the Retirement Planner's after-tax figures, applied to today's balances: pre-tax money at the heirs' 10-year bracket rate${tax.rate_source === "settings" ? " (overridden in live_snapshot_settings.json)" : ""}; taxable-account gains${d ? ` (federal ${fmtUsd(d.federal)}, NIIT ${fmtUsd(d.niit)}, state ${fmtUsd(d.state)})` : ""} from the lots' cost basis with no step-up, since nobody has died yet. Assumes no other income. Flat 25% / 15% rates would give ${fmtUsd(tax.flat_total)} (${fmtUsd(tax.total - tax.flat_total)} different). The Planner's report figure is for the end of the plan, so it will differ.</p>`
    : `<p class="note">Flat rates (the Planner's plan could not be read): ordinary income at ${fmtPct(tax.pre_tax_rate, 0)}, taxable-account gains at ${fmtPct(tax.ltcg_rate, 0)}. An estimate, not a tax calculation.</p>`;
  return `<div class="table-wrap"><table class="live-table simple">${head}<tbody>${body}</tbody></table></div>` + how + missing + realizedTaxHtml(tax);
}

// Tax on gains realized this year is a line of its own beside the unrealized estimate: a sold lot has left holdings,
// so the two never overlap (sales ledger plan 9.4).
function realizedTaxHtml(tax) {
  const r = tax.realized_tax;
  if (!r) return "";
  const rows = [["On unrealized gains if liquidated", tax.total], [`On gains realized in ${r.tax_year}`, r.total], ["Total", tax.total_with_realized]];
  const body = rows.map(([label, v], i) => `<tr${i === 2 ? ' class="total-row"' : ""}><th scope="row">${esc(label)}</th><td class="num">${fmtUsd(v)}</td></tr>`).join("");
  const unknown = r.unknown_term?.count
    ? ` ${r.unknown_term.count} ${r.unknown_term.count === 1 ? "sale has" : "sales have"} no holding period yet and ${r.unknown_term.count === 1 ? "is" : "are"} left out.` : "";
  const how = r.method === "planner"
    ? "Netted short and long term with any carryforward you entered, then taxed with the Retirement Planner's federal, NIIT and state rules."
    : "Netted short and long term with any carryforward you entered, at flat rates.";
  return `<h3>Tax on realized gains</h3><div class="table-wrap"><table class="live-table simple"><tbody>${body}</tbody></table></div>`
    + `<p class="note">${how} Uses the income recorded so far this year, so it is an estimate.${unknown}</p>`;
}

function totalsHtml(t, checking, debt, tax, nonLiquid, liquid) {
  const steps = [
    ["Liquid investments", liquid.current], ["Checking", checking.total], ["Non-liquid assets", nonLiquid.total],
    ["Debt", -debt.total], ["Net assets", t.net_assets], ["Estimated tax", -tax.total], ["After-tax net worth", t.after_tax_net_worth],
  ];
  const kinds = Object.entries(t.by_kind || {}).map(([k, v]) =>
    isPct()
      ? `<span class="kind-chip">${esc(k)} <b>${fmtPct(t.gross_assets ? v / t.gross_assets : null, 0)}</b></span>`
      : `<span class="kind-chip">${esc(k)} <b>${fmtUsd(v)}</b> <span class="muted">${fmtPct(t.gross_assets ? v / t.gross_assets : null, 0)}</span></span>`).join("");
  return `<div class="totals-band">${steps.map(([label, v], i) =>
    `<div class="total-step${i === 4 || i === 6 ? " strong" : ""}"><span>${label}</span><b>${fmtUsd(v)}</b></div>`).join("")}</div>`
    + (isPct() ? `<div class="unit-line">${unitChip("share of gross assets")}</div>` : "")
    + `<div class="kinds" aria-label="Assets by kind (share of gross assets)">${kinds}</div>`;
}

// Sold lots feed the returns (confirmed ledger sales only); unconfirmed ones are a count, never an estimate.
export function soldNote(L, startDay) {
  const sold = L.sold?.count ?? 0, waiting = L.unconfirmed_sales?.count ?? 0;
  const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
  const included = sold ? `Includes ${plural(sold, "position", "positions")} sold since ${startDay}.` : "";
  const unconfirmed = waiting ? ` ${plural(waiting, "sale", "sales")} not yet confirmed ${waiting === 1 ? "is" : "are"} not included.` : "";
  return (included + unconfirmed).trim();
}

export function liveViewHtml(data, groupOrder, groupSort) {
  if (!data) return `<p class="empty">Loading live prices…</p>`;
  if (data.error) return `<p class="live-error">Current Snapshot is unavailable: ${esc(data.error)}</p>`;
  accountLabels = data.account_labels || {};
  startDay = startDayText(data.baseline_date, data.as_of);
  const period = isYearToDate(data.baseline_date, data.as_of) ? "Year to date" : `Since ${startDay}`;
  const L = data.liquid, t = data.totals;
  const order = normalizeOrder(groupOrder);
  const tree = buildTree(L.positions || [], order, { days: data.days ?? 0, labelOf: acctLabel, sort: groupSort });
  const indices = (data.indices || []).map((i) =>
    `<span class="index-chip">${esc(i.label)} ${i.day_pct === null || i.day_pct === undefined ? `<span class="na">${DASH}</span>` : changeHtml(i.day_pct, true)}</span>`).join("");
  const sub = isPct()
    ? `Liquid today ${changeHtml(L.day_pct, true)} · ${period} ${changeHtml(L.return_pct, true)}`
    : `Liquid today ${changeHtml(L.day)} (${changeHtml(L.day_pct, true)}) · ${period} ${changeHtml(L.market_gain)} (${changeHtml(L.return_pct, true)})`;
  const head = `<div class="live-head"><div><div class="live-label">After-tax net worth${unitChip("% of net worth")}</div><div class="live-big">${fmtUsd(t.after_tax_net_worth)}</div>`
    + `<div class="live-sub">${sub}</div></div>`
    + `<div class="live-right"><div class="indices">${indices}</div><div class="live-status" role="status">${esc(statusText(data))}</div></div></div>`;
  const flows = L.checking_net_flows === null || L.checking_net_flows === undefined ? ""
    : ` Net transfers from checking since ${startDay}: ${fmtUsd(L.checking_net_flows)} (for information).`;
  const liquid = `<div class="card live-card${isPct() ? " pm" : ""}"><div class="live-card-head"><h2>Liquid investments${unitChip("% of net worth")}</h2>${groupByHtml(order)}${sortByHtml(groupSort)}</div>${groupedTable(tree, DIMENSIONS[order[0]], L)}${moneyView().allowed === "percent" ? "" : reconciliationHtml(data.reconciliation)}`
    + `<p class="note">Start = ${startDay} closing value of lots held then (the Time scope sets the date). Bought since = lots bought after ${startDay}, at purchase price; reinvested dividends count as gain. Return % weights new money by how long it was invested (Modified Dietz). ${soldNote(L, startDay)}${flows}</p></div>`;
  const nl = data.non_liquid;
  const nonLiquid = `<details class="live-section"><summary>Non-liquid assets <b>${fmtUsd(nl.total)}</b>${unitChip("% of net worth")} <span class="muted">imported balances, ${esc(nl.as_of || "")}</span></summary>`
    + simpleTable(nl.rows, [(r) => esc(r.name) + (r.source === "plan" ? ` <span class="muted" title="Present value from the plan's latest build (Recent Projections), not the imported balance">plan value</span>` : ""), (r) => esc(r.kind), (r) => fmtUsd(r.value), ...(isPct() ? [] : [(r) => fmtPct(r.share, 0)]), (r) => esc(TREATMENT[r.tax_treatment] || "")]) + `</details>`;
  const tax = `<details class="live-section"><summary>Estimated tax <b>${fmtUsd(-data.tax.total)}</b>${unitChip("% of net worth")}</summary>${taxHtml(data.tax)}</details>`;
  const debt = `<details class="live-section"><summary>Debt <b>${fmtUsd(-data.debt.total)}</b>${unitChip("% of net worth")}</summary>`
    + simpleTable(data.debt.rows, [(r) => esc(r.name), (r) => fmtUsd(r.value)])
    + `<p class="note">Checking: ${fmtUsd(data.checking.total)} across ${data.checking.rows.length} account(s).</p></details>`;
  return head + liquid + `<div class="card live-card">${isPct() ? `<div class="unit-line">${unitChip("% of net worth")}</div>` : ""}${totalsHtml(t, data.checking, data.debt, data.tax, nl, L)}${nonLiquid}${tax}${debt}</div>`;
}

// ---- browser wiring ----
export function initLiveView(doc = document, win = window) {
  const body = doc.body;
  const section = doc.getElementById("liveView");
  const out = doc.getElementById("liveBody");
  const errorBox = doc.getElementById("liveError");
  const buttons = [...doc.querySelectorAll("[data-view]")];
  let view = "trends", data = null, lastLoad = 0, busy = false, reloadAfter = false;
  const expanded = new Set(), openSections = new Map();
  let groupOrder = [...DEFAULT_ORDER], groupSort = normalizeSort(null), dragging = null;

  try { view = parseSavedView(win.localStorage.getItem(VIEW_KEY)); } catch (err) { view = "trends"; }
  try { groupOrder = parseSavedOrder(win.localStorage.getItem(GROUPS_KEY)); } catch (err) { groupOrder = [...DEFAULT_ORDER]; }
  try { groupSort = parseSavedSort(win.localStorage.getItem(SORT_KEY)); } catch (err) { groupSort = normalizeSort(null); }

  // Only a section the user opened or closed themselves is remembered (recorded on the summary click),
  // so the server's default (every section closed) applies until then. Keyed by name for the reconciliation section and by position among the others, so a
  // section that appears or disappears between refreshes doesn't shift the rest.
  function sectionKeys() {
    let n = 0;
    return (d) => (d.classList.contains("recon-accounts") ? "recon-accounts" : n++);
  }

  function render() {
    out.innerHTML = liveViewHtml(data, groupOrder, groupSort);
    const key = sectionKeys();
    out.querySelectorAll("details.live-section").forEach((d) => { const k = key(d); if (openSections.has(k)) d.open = openSections.get(k); });
    applyExpanded();
  }

  // Rows are in document order (parents before children). A row shows only when its parent is
  // expanded and itself shown, so a collapsed level hides everything below it.
  function applyExpanded() {
    const shown = new Set();
    out.querySelectorAll("tr[data-parent], tr.top-row").forEach((tr) => {
      const parent = tr.dataset.parent;
      const visible = parent === undefined || (shown.has(parent) && expanded.has(parent));
      tr.hidden = !visible;
      if (visible && tr.dataset.path !== undefined) shown.add(tr.dataset.path);
    });
    out.querySelectorAll("button.expand").forEach((b) => {
      const open = expanded.has(b.dataset.path);
      b.setAttribute("aria-expanded", open ? "true" : "false");
      b.textContent = (open ? "▾ " : "▸ ") + b.dataset.label;
    });
  }

  // Collapsing a path also forgets every expanded path below it (found by following data-parent).
  function collapse(path) {
    const parentOf = new Map();
    out.querySelectorAll("tr[data-path][data-parent]").forEach((tr) => parentOf.set(tr.dataset.path, tr.dataset.parent));
    expanded.delete(path);
    for (const p of [...expanded]) {
      for (let q = parentOf.get(p), n = 0; q !== undefined && n < 10; q = parentOf.get(q), n++) {
        if (q === path) { expanded.delete(p); break; }
      }
    }
  }

  async function load(force = false) {
    if (busy) return;
    busy = true;
    try {
      const params = new URLSearchParams();
      if (force) params.set("refresh", "1");
      const scopeFrom = body?.dataset?.scopeFrom;
      if (scopeFrom) params.set("from", scopeFrom);
      const query = params.toString();
      const resp = await win.fetch("/api/live-snapshot" + (query ? "?" + query : ""));
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
        : `Couldn't load the Current Snapshot (${msg}).`;
      if (!data) out.innerHTML = "";
    } finally {
      busy = false;
      if (reloadAfter) { reloadAfter = false; load(); }   // the scope changed mid-request
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

  // A new grouping: remembered per browser; the old expanded rows no longer exist, so they are dropped.
  // ``focusSel`` puts keyboard focus back on the control just used (the row is redrawn).
  function setGroupOrder(next, focusSel) {
    groupOrder = normalizeOrder(next);
    try { win.localStorage.setItem(GROUPS_KEY, JSON.stringify(groupOrder.filter((d) => d !== "lot"))); } catch (err) { /* storage blocked: the choice just won't persist */ }
    expanded.clear();
    if (data) render();
    const target = focusSel && out.querySelector(focusSel);
    if (target && !target.disabled) target.focus();
  }

  // A new sort: remembered per browser. Row paths don't depend on it, so expanded rows stay open.
  out.addEventListener("change", (e) => {
    const field = e.target.closest ? e.target.closest("#liveSortField") : null, dir = e.target.closest ? e.target.closest("#liveSortDir") : null;
    if (!field && !dir) return;
    groupSort = normalizeSort({ field: field ? field.value : groupSort.field, dir: dir ? dir.value : groupSort.dir });
    try { win.localStorage.setItem(SORT_KEY, JSON.stringify(groupSort)); } catch (err) { /* storage blocked: the choice just won't persist */ }
    if (data) render();
    const again = out.querySelector(field ? "#liveSortField" : "#liveSortDir");
    if (again) again.focus();
  });

  out.addEventListener("click", (e) => {
    const step = e.target.closest("button.chip-step"), remove = e.target.closest("button.chip-remove"), add = e.target.closest("button.chip.off");
    if (step) setGroupOrder(stepDimension(groupOrder, step.dataset.dim, Number(step.dataset.step)), `button.chip-step[data-dim="${step.dataset.dim}"][data-step="${step.dataset.step}"]`);
    else if (remove) setGroupOrder(toggleDimension(groupOrder, remove.dataset.dim), ".group-by button");
    else if (add) setGroupOrder(toggleDimension(groupOrder, add.dataset.dim), `button.chip-remove[data-dim="${add.dataset.dim}"]`);
  });

  // Mouse: drag a chip onto another to put it before (left half) or after (right half) it. Touch and keyboard
  // use the arrows. A chip dragged in from the unused ones is added at the drop point.
  const chipAt = (e) => (e.target.closest ? e.target.closest(".group-by .chip[data-dim]") : null);
  const clearMarks = () => out.querySelectorAll(".chip.drop-before, .chip.drop-after, .chip.dragging").forEach((c) => c.classList.remove("drop-before", "drop-after", "dragging"));
  const afterHalf = (e, chip) => { const r = chip.getBoundingClientRect(); return e.clientX > r.left + r.width / 2; };
  out.addEventListener("dragstart", (e) => {
    const chip = chipAt(e);
    if (!chip || chip.classList.contains("fixed")) return;
    dragging = chip.dataset.dim;
    if (e.dataTransfer) { e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", dragging); }
    chip.classList.add("dragging");
  });
  out.addEventListener("dragover", (e) => {
    const chip = dragging && chipAt(e);
    if (!chip) return;
    e.preventDefault();
    clearMarks();
    chip.classList.add(afterHalf(e, chip) ? "drop-after" : "drop-before");
  });
  out.addEventListener("drop", (e) => {
    const chip = dragging && chipAt(e);
    if (!chip) return;
    e.preventDefault();
    const dim = dragging;
    dragging = null;
    clearMarks();
    setGroupOrder(dropOrder(groupOrder, dim, chip.dataset.dim, afterHalf(e, chip)), `.group-by .chip[data-dim="${dim}"] .chip-name, .group-by .chip.off[data-dim="${dim}"]`);
  });
  out.addEventListener("dragend", () => { dragging = null; clearMarks(); });

  // A new Time scope moves the start date: reload now if shown, else on the next switch to Live.
  doc.addEventListener("trends-scope-change", () => {
    lastLoad = 0;
    if (view === "live") { if (busy) reloadAfter = true; else load(); }
  });

  // The $ | % toggle repaints the figures now; the next poll would otherwise leave the old form up.
  onMoneyViewChange(() => { if (data) render(); });
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
    if (open) expanded.add(b.dataset.path); else collapse(b.dataset.path);
    applyExpanded();
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
