// "Cash in investment accounts" panel on the Sales Ledger page (cash tracking Phase 5): per account the computed balance, its
// anchor, the CASH lot and the difference; cash income of the year by tax class; click an account for its ledger. Read-only;
// the view model is server-side (src/cash_view.py, GET /api/cash). Helpers are bare globals.

const CI_COLS = [["account", "Account"], ["balance", "Balance"], ["as_of", "As of"], ["cash_lot", "CASH lot"], ["difference", "Difference"], ["anchor", "Anchor"], ["last_flow", "Last flow"], ["unmatched", "Unmatched"]];
const CI_CLASS = { taxable: "Taxable", pre_tax: "Traditional", roth: "Roth", hsa: "HSA" };
let ciView = null, ciLedger = null, ciError = "", ciOpen = false, ciSort = { key: "account", dir: 1 };

const ciMoney = (v) => (v == null ? "" : window.slMoney ? window.slMoney(v) : String(v));

// Year close (src/cash_year_close.py): the owner closes an ended year by hand; it feeds no tax number.
function ciCloses(closes, lbl) {
  return closes.map((c) => {
    if (c.closed) {
      const rows = c.difference.map((d) => `<tr><td>${lbl(d.account)}</td><td class="rc-num">${ciMoney(d.reported)}</td><td class="rc-num">${ciMoney(d.plan)}</td><td class="rc-num">${ciMoney(d.difference)}</td></tr>`).join("");
      return `<p><b>${esc(String(c.year))} closed ${esc(String(c.closed_at).slice(0, 10))}</b>${c.note ? ` (${esc(c.note)})` : ""}. ${c.plan_source === "snapshot" ? `Plan run built ${esc(c.built_at)}.` : "No plan figure was saved for this year."} ` +
        `<button class="btn" type="button" onclick="ciReopenYear(${c.year})">Reopen ${esc(String(c.year))}</button></p>` +
        (c.changed ? `<p role="alert" class="error">Changed since close: withdrawals were ${ciMoney(c.closed_total)} when closed, now ${ciMoney(c.current_total)}. Reopen and close again to accept.</p>` : "") +
        (rows ? `<div class="rc-scroll"><table class="rc-table"><thead><tr><th>Account</th><th class="rc-num">Reported</th><th class="rc-num">Plan</th><th class="rc-num">Plan − reported</th></tr></thead><tbody>${rows}</tbody></table></div>` : "");
    }
    const why = (c.blockers || []).map((b) => `<li>${esc(b)}</li>`).join("");
    return `<p><b>${esc(String(c.year))} is not closed.</b> ` + (c.allowed
      ? `${c.snapshot ? `Plan figure from the run built ${esc(c.snapshot.built_at)}.` : "No saved plan run projects this year, so it would close with no plan figure."} Closing feeds no tax number. ` +
        `<button class="btn" type="button" onclick="ciCloseYear(${c.year}, ${(c.straddles || []).length})">Close ${esc(String(c.year))}</button>` : "Resolve before closing:") + `</p>` + (why ? `<ul>${why}</ul>` : "");
  }).join("");
}

export function ciHtml(view, ledger = ciLedger, sort = ciSort) {
  const rows = [...((view && view.accounts) || [])].sort((a, b) => {
    const x = a[sort.key], y = b[sort.key];
    return (x == null) - (y == null) || (x > y ? 1 : x < y ? -1 : 0) * sort.dir; // blanks always last
  });
  const head = CI_COLS.map(([k, t]) => `<th><a href="#" onclick="ciSortBy('${k}');return false">${esc(t)}${sort.key === k ? (sort.dir > 0 ? " ▲" : " ▼") : ""}</a></th>`).join("");
  const body = rows.map((r) => `<tr><td><a href="#" onclick="ciShowLedger(${esc(JSON.stringify(r.account))});return false">${esc(accountDisplayLabel(r.account))}</a></td>` +
    `<td class="rc-num">${r.balance == null ? "unanchored" : ciMoney(r.balance)}</td><td>${esc(r.as_of || "")}</td><td class="rc-num">${ciMoney(r.cash_lot)}</td>` +
    `<td class="rc-num">${ciMoney(r.difference)}</td><td>${esc(r.anchor)}</td><td>${esc(r.last_flow || "")}</td><td class="rc-num">${r.unmatched || ""}</td></tr>`).join("");
  const inc = Object.entries((view && view.income_by_tax_class) || {}).map(([k, v]) => `${esc(CI_CLASS[k] || k)} ${ciMoney(v)}`).join(" · ");
  const wd = rows.filter((r) => r.withdrawals && Object.values(r.withdrawals).some((x) => x)).map((r) => `<li>${esc(accountDisplayLabel(r.account))} (${esc(CI_CLASS[r.tax_class] || r.tax_class)}): withdrawn ${ciMoney(r.withdrawals.external_withdrawal)}, internal transfers ${ciMoney(r.withdrawals.internal)}, unmatched ${ciMoney(r.withdrawals.unmatched)}</li>`).join("");
  const ex = rows.filter((r) => r.excess_return && r.excess_return.count).map((r) => `<li>${esc(accountDisplayLabel(r.account))}: ${ciMoney(r.excess_return.amount)} returned, untaxed; enter the earnings on it, they are taxable.</li>`).join("");
  const rep = (wd ? `<p>Withdrawals ${esc(String(view.year))} by pairing (report only, the plan's tax numbers are unchanged):</p><ul>${wd}</ul>` : "") + (ex ? `<p>Excess contributions returned:</p><ul>${ex}</ul>` : "");
  const cmp = view && view.comparison, lbl = (a) => esc(accountDisplayLabel(a));
  const cmpHtml = cmp && cmp.accounts.length ? `<p>Plan vs reported ${esc(String(cmp.year))} (report only). ${cmp.closed ? "Year closed." : "Year to date reported against the plan's full-year figure; no difference until the year is closed."}` +
    ` ${cmp.snapshot ? `Plan run built ${esc(cmp.snapshot.built_at)}. ` : ""}${esc(cmp.note)}</p><div class="rc-scroll"><table class="rc-table"><thead><tr><th>Account</th><th class="rc-num">Reported, year to date</th><th class="rc-num">Plan, full year</th>${cmp.closed ? '<th class="rc-num">Plan − reported</th>' : ""}</tr></thead><tbody>` +
    cmp.accounts.map((a) => `<tr><td>${lbl(a.account)}</td><td class="rc-num">${ciMoney(a.reported_ytd)}</td><td class="rc-num">${ciMoney(a.plan)}</td>${cmp.closed ? `<td class="rc-num">${ciMoney(a.difference)}</td>` : ""}</tr>`).join("") + `</tbody></table></div>` +
    (Object.keys(cmp.plan_unmapped || {}).length ? `<p class="muted">Plan withdrawals from accounts with no broker import: ${Object.entries(cmp.plan_unmapped).map(([k, v]) => `${lbl(k)} ${ciMoney(v)}`).join(", ")}.</p>` : "") : "";
  const past = ((view && view.past_years) || []).filter((p) => p.external_withdrawal || p.internal || p.unmatched);
  const pastHtml = past.length ? `<p>Earlier years, reported only (the plan has no past-year figures):</p><ul>` + past.map((p) => `<li>${lbl(p.account)} ${esc(String(p.year))}: withdrawn ${ciMoney(p.external_withdrawal)}, internal ${ciMoney(p.internal)}, unmatched ${ciMoney(p.unmatched)}</li>`).join("") + `</ul>` : "";
  const st = (view && view.straddles) || [];
  const stHtml = st.length ? `<p>Transfers that straddle year-end (each row stays in the year of its own date):</p><ul>` + st.map((t) => `<li>${ciMoney(t.amount)} out of ${lbl(t.out_account)} ${esc(t.out_date)}, into ${lbl(t.in_account)} ${esc(t.in_date)}</li>`).join("") + `</ul>` : "";
  const fg = rows.filter((r) => r.floor_gate).map((r) => `<li>${esc(accountDisplayLabel(r.account))}: ${r.floor_gate.eligible ? "eligible" : `not fed (${esc(r.floor_gate.reason)})`} ` +
    `<button class="btn" type="button" onclick="ciVerify(${esc(JSON.stringify(r.account))}, ${!r.floor_gate.verified})">${r.floor_gate.verified ? "Remove verification" : "Mark verified"}</button></li>`).join("");
  const floorHtml = fg ? `<p>Floor feed (applies only when the plan's pair-status tax setting is on; an account is fed only once verified against a closed year and with no unmatched rows this year):</p><ul>${fg}</ul>` : "";
  const closesHtml = ciCloses((view && view.closes) || [], lbl);
  const led = ledger && ledger.rows ? `<h4>${esc(accountDisplayLabel(ledger.account))}: ledger</h4>` + (ledger.rows.length ? `<div class="rc-scroll"><table class="rc-table"><thead><tr><th>Date</th><th>Class</th><th class="rc-num">Amount</th><th class="rc-num">Balance</th><th>Pairing</th><th>Source</th></tr></thead><tbody>` +
    ledger.rows.map((l) => `<tr><td>${esc(l.date)}</td><td>${esc(l.class)}${l.needs_review ? " (review)" : ""}</td><td class="rc-num">${l.in_kind ? "in kind" : ciMoney(l.amount)}</td><td class="rc-num">${ciMoney(l.cash_balance)}</td>` +
      `<td>${esc(l.pair_status)}${l.partner_account ? " " + esc(accountDisplayLabel(l.partner_account)) : ""}</td><td>${esc(l.source)}</td></tr>`).join("") + `</tbody></table></div>` : `<p class="muted">No cash rows.</p>`) : "";
  const table = rows.length ? `<div class="rc-scroll"><table class="rc-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>` : `<p class="muted">No broker imports yet.</p>`;
  return `<details${ciOpen ? " open" : ""} ontoggle="ciToggle(this.open)"><summary><h3 style="display:inline">Cash in investment accounts</h3>${view ? ` (${rows.length})` : ""}</summary>` +
    `${ciError ? `<p role="alert" class="error">${esc(ciError)}</p>` : ""}${table}${inc ? `<p>Cash income ${esc(String(view.year))}: ${inc}</p>` : ""}${rep}${cmpHtml}${pastHtml}${stHtml}${closesHtml}${floorHtml}${led}</details>`;
}

export function renderCashInvestment() {
  if (ciView === null) setTimeout(ciLoad, 0);
  return `<div class="sl-import" id="ciRoot">${ciHtml(ciView)}</div>`;
}

export function ciSummary() {
  const n = ((ciView && ciView.accounts) || []).reduce((t, a) => t + (Number(a.unmatched) || 0), 0);
  return { count: n, tone: n > 0 ? "warn" : "", text: n > 0 ? `${n} unpaired` : "" };
}
const ciPaint = () => {
  const el = document.getElementById("ciRoot");
  if (el) el.innerHTML = ciHtml(ciView);
  if (window.slPublish) window.slPublish("cash", ciSummary());
};
export async function ciLoad() {
  try { ciView = await api("/api/cash"); ciError = ""; } catch (e) { ciView = { accounts: [] }; ciError = e.message; }
  ciPaint();
}
export async function ciShowLedger(account) {
  try { ciLedger = await api(`/api/cash?account=${encodeURIComponent(account)}`); ciError = ""; } catch (e) { ciError = e.message; }
  ciPaint();
}
export async function ciCloseYear(year, straddles) {
  const seen = straddles ? confirm(`${straddles} transfer(s) straddle the ${year} year-end and stay in the year of their own date. Close ${year}?`) : confirm(`Close ${year}? This freezes its reported withdrawals and plan figure.`);
  if (!seen) return;
  await ciYearAction({ year, action: "close", straddles_seen: !!straddles });
}
export async function ciReopenYear(year) {
  if (confirm(`Reopen ${year}? Its frozen figures are discarded.`)) await ciYearAction({ year, action: "reopen" });
}
async function ciYearAction(body) {
  try { await api("/api/cash/year-close", { method: "POST", body: JSON.stringify(body) }); await ciLoad(); } catch (e) { ciError = e.message; ciPaint(); }
}
export async function ciVerify(account, verified) {
  try { await api("/api/cash/verify-account", { method: "POST", body: JSON.stringify({ account, verified }) }); await ciLoad(); } catch (e) { ciError = e.message; ciPaint(); }
}
export function ciSortBy(key) { ciSort = { key, dir: ciSort.key === key ? -ciSort.dir : 1 }; ciPaint(); }
export function ciToggle(open) { ciOpen = !!open; }

Object.assign(window, { ciSummary, renderCashInvestment, ciHtml, ciLoad, ciShowLedger, ciSortBy, ciToggle, ciCloseYear, ciReopenYear, ciVerify });
