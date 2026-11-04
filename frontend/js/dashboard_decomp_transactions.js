// Transactions history: every purchase, reinvestment, sale and redemption for the brokerage accounts, with the lots still
// held. It is the "History & held lots" mode of the Transaction log section (dashboard_decomp_transactions_log.js), which
// owns the filter bar and calls trLoad with its filters. Read-only; the view model lives on the server
// (src/transactions_view.py, GET /api/transactions). Helpers are bare globals.

const TR_LABEL = { buy: "Buy", reinvest: "Reinvest", sell: "Sale / redemption" };
let trFilter = { account: "", symbol: "", year: "", type: "", held: false }; // the filters of the last load
let trView = null;
let trError = "";

const trMoney = (v) => (v == null ? "" : window.slMoney ? window.slMoney(v) : String(v));
const trNum = (v) => esc(String(Math.round(Number(v) * 1e6) / 1e6));

// The history body: error, transactions table and, with filter.held, the Lots held table.
export function trHtml(view, filter = trFilter) {
  const rows = (view && view.rows) || [];
  const table = !rows.length ? `<p class="muted">No transactions match.</p>` :
    `<table class="rc-table"><thead><tr><th>Date</th><th>Account</th><th>Type</th><th>Symbol</th><th class="rc-num">Shares</th><th class="rc-num">Price</th><th class="rc-num">Amount</th><th class="rc-num">Remaining</th><th>Sale</th><th>Source</th></tr></thead><tbody>` +
    rows.map((r) => `<tr><td>${esc(r.date)}</td><td>${esc(accountDisplayLabel(r.account))}</td><td>${esc(TR_LABEL[r.type] || r.type)}</td><td>${esc(r.symbol)}</td>` +
      `<td class="rc-num">${trNum(r.shares)}</td><td class="rc-num">${trMoney(r.price)}</td><td class="rc-num">${trMoney(r.amount)}</td>` +
      `<td class="rc-num">${r.remaining == null ? "" : trNum(r.remaining)}</td><td>${esc(r.linked || "")}</td><td>${esc(r.source)}</td></tr>`).join("") + `</tbody></table>`;
  const held = ((view && view.held) || []);
  const heldHtml = filter.held ? `<h4>Lots held</h4>` + (held.length ? `<table class="rc-table"><thead><tr><th>Account</th><th>Symbol</th><th>Purchased</th><th class="rc-num">Shares</th><th class="rc-num">Price</th></tr></thead><tbody>` +
    held.map((h) => `<tr><td>${esc(accountDisplayLabel(h.account))}</td><td>${esc(h.symbol)}</td><td>${esc(h.purchase_date)}</td><td class="rc-num">${trNum(h.shares)}</td><td class="rc-num">${trMoney(h.price)}</td></tr>`).join("") + `</tbody></table>` : `<p class="muted">No open lots.</p>`) : "";
  return `${trError ? `<p role="alert" class="error">${esc(trError)}</p>` : ""}${table}${heldHtml}`;
}

// Fetch the history for these filters (account, symbol, year, type, held); the caller paints.
export async function trLoad(filter = trFilter) {
  trFilter = { ...trFilter, ...filter };
  const q = new URLSearchParams();
  for (const k of ["account", "symbol", "year", "type"]) if (trFilter[k]) q.set(k, trFilter[k]);
  if (trFilter.held) q.set("held", "1");
  try { trView = await api(`/api/transactions?${q}`); trError = ""; } catch (e) { trView = { rows: [], held: [] }; trError = e.message; }
  return trView;
}
export const trState = () => ({ view: trView, error: trError });

Object.assign(window, { trHtml, trLoad, trState });
