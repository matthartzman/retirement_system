// Transactions panel on the Sales Ledger page: every purchase, reinvestment, sale and redemption for the brokerage
// accounts, with a "Held" filter showing the lots still open. Read-only (phase 1 of the transaction log plan); the
// view model lives on the server (src/transactions_view.py, GET /api/transactions). Helpers are bare globals.

const TR_TYPES = [["", "All types"], ["buy", "Buy"], ["reinvest", "Reinvest"], ["sell", "Sale / redemption"]];
const TR_LABEL = { buy: "Buy", reinvest: "Reinvest", sell: "Sale / redemption" };
let trFilter = { account: "", symbol: "", year: "", type: "", held: false };
let trView = null;
let trError = "";

const trMoney = (v) => (v == null ? "" : window.slMoney ? window.slMoney(v) : String(v));
const trNum = (v) => esc(String(Math.round(Number(v) * 1e6) / 1e6));

export function trHtml(view, filter = trFilter) {
  const rows = (view && view.rows) || [];
  const accounts = [...new Set([...rows.map((r) => r.account), ...((view && view.held) || []).map((h) => h.account)])].sort();
  const sel = (id, opts, cur, fn) => `<select id="${id}" onchange="${fn}(this.value)">${opts.map(([v, t]) => `<option value="${esc(v)}"${v === cur ? " selected" : ""}>${esc(t)}</option>`).join("")}</select>`;
  const bar = `<div class="sl-filters">` +
    sel("trAccount", [["", "All accounts"], ...accounts.map((a) => [a, accountDisplayLabel(a)])], filter.account, "trSet('account',") +
    `<input id="trSymbol" placeholder="Symbol" value="${esc(filter.symbol)}" onchange="trSet('symbol',this.value)" size="7">` +
    `<input id="trYear" placeholder="Year" value="${esc(filter.year)}" onchange="trSet('year',this.value)" size="5">` +
    sel("trType", TR_TYPES, filter.type, "trSet('type',") +
    `<label><input type="checkbox" id="trHeld"${filter.held ? " checked" : ""} onchange="trSet('held',this.checked)"> Held only</label></div>`;
  const table = !rows.length ? `<p class="muted">No transactions match.</p>` :
    `<table class="rc-table"><thead><tr><th>Date</th><th>Account</th><th>Type</th><th>Symbol</th><th class="rc-num">Shares</th><th class="rc-num">Price</th><th class="rc-num">Amount</th><th class="rc-num">Remaining</th><th>Sale</th><th>Source</th></tr></thead><tbody>` +
    rows.map((r) => `<tr><td>${esc(r.date)}</td><td>${esc(accountDisplayLabel(r.account))}</td><td>${esc(TR_LABEL[r.type] || r.type)}</td><td>${esc(r.symbol)}</td>` +
      `<td class="rc-num">${trNum(r.shares)}</td><td class="rc-num">${trMoney(r.price)}</td><td class="rc-num">${trMoney(r.amount)}</td>` +
      `<td class="rc-num">${r.remaining == null ? "" : trNum(r.remaining)}</td><td>${esc(r.linked || "")}</td><td>${esc(r.source)}</td></tr>`).join("") + `</tbody></table>`;
  const held = ((view && view.held) || []);
  const heldHtml = filter.held ? `<h4>Lots held</h4>` + (held.length ? `<table class="rc-table"><thead><tr><th>Account</th><th>Symbol</th><th>Purchased</th><th class="rc-num">Shares</th><th class="rc-num">Price</th></tr></thead><tbody>` +
    held.map((h) => `<tr><td>${esc(accountDisplayLabel(h.account))}</td><td>${esc(h.symbol)}</td><td>${esc(h.purchase_date)}</td><td class="rc-num">${trNum(h.shares)}</td><td class="rc-num">${trMoney(h.price)}</td></tr>`).join("") + `</tbody></table>` : `<p class="muted">No open lots.</p>`) : "";
  return `<h3>Transactions</h3>${trError ? `<p role="alert" class="error">${esc(trError)}</p>` : ""}${bar}${table}${heldHtml}`;
}

export function renderTransactions() {
  if (trView === null) setTimeout(trLoad, 0);
  return `<div class="sl-import" id="trRoot">${trHtml(trView)}</div>`;
}

export async function trLoad() {
  const q = new URLSearchParams();
  for (const k of ["account", "symbol", "year", "type"]) if (trFilter[k]) q.set(k, trFilter[k]);
  if (trFilter.held) q.set("held", "1");
  try { trView = await api(`/api/transactions?${q}`); trError = ""; } catch (e) { trView = { rows: [], held: [] }; trError = e.message; }
  const root = document.getElementById("trRoot");
  if (root) root.innerHTML = trHtml(trView);
}

export function trSet(key, value) { trFilter = { ...trFilter, [key]: value }; return trLoad(); }

Object.assign(window, { renderTransactions, trHtml, trLoad, trSet });
