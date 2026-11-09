// Sales Ledger > To fix > Wash sales: one card per flagged sale (both sides, where each replacement's share of the loss goes), a Review
// control with three outcomes, and the list of reviews already made (with Undo). Rules and amounts come from the server
// (src/wash_sales.py, GET /api/sales/wash?year, POST /api/sales/wash/review[/clear]); this only displays and posts the choice.
const SW_OUTCOMES = [["wash", "Wash sale"], ["broker_reported", "Broker already reported it"], ["not_wash", "Not a wash sale…"]];
let swData = null, swMessage = null, swWindows = [];
const swMoney = (v) => (window.slMoney ? window.slMoney(v) : String(v));

// "Not a wash sale" needs a reason; the other two do not.
export const swValidate = (outcome, reason) => (outcome === "not_wash" && !String(reason || "").trim() ? "Say why it is not a wash sale (for example: not substantially identical)." : "");

export function swCardHtml(c, i) {
  const rep = c.matches.map((m) => `<li>${esc(m.label)} bought ${esc(String(+m.shares.toFixed(4)))} on ${esc(m.date)}${m.value == null ? "" : ` (${swMoney(m.value)})`}${m.is_reinvest ? " (dividend reinvest)" : ""}: ` +
    (m.taxable ? esc(m.where) : `<span class="field-error">${esc(m.where)}</span>`) + (window.hsActivityLink && m.taxable ? ` <a href="${esc(window.hsActivityLink({ account: m.account, symbol: c.symbol, back: "sales" }))}">See the lot</a>` : "") + `</li>`).join("");
  return `<div class="sw-card" id="swCard${i}"><h4>${esc(c.symbol)} · ${esc(c.account)} · ${esc(c.sale_date)}</h4>` +
    `<p>Sold at a loss: ${esc(String(+c.shares.toFixed(4)))} shares for ${swMoney(c.proceeds)}, loss ${swMoney(c.loss)} (${Number(c.lots)} lot${c.lots === 1 ? "" : "s"}).</p><p>Replacement purchases:</p><ul>${rep}</ul>` +
    `<p><b>Disallowed ${swMoney(c.disallowed)} of ${swMoney(c.loss)} · ${swMoney(c.deductible)} still deductible</b></p>` +
    `<div class="sl-filters"><label>Review <select id="swOutcome${i}" onchange="swOutcomeChanged(${i})">${SW_OUTCOMES.map(([v, t]) => `<option value="${v}">${t}</option>`).join("")}</select></label> ` +
    `<label id="swReasonLabel${i}" hidden>Reason <input id="swReason${i}" size="30" placeholder="why it is not a wash sale"></label> <button class="btn" type="button" onclick="swSave(${i})">Save review</button></div></div>`;
}

// Prevention: one line per loss sale still inside its 30 days; it goes away on its own when the window closes.
export function swWindowsHtml(list = swWindows) {
  if (!list.length) return "";
  const md = (iso) => String(iso).slice(5);
  return `<div class="sw-windows" role="status">` + list.map((w) => `<p><b>${esc(w.symbol)} loss: the window is open until ${esc(md(w.closes_on))}.</b>` +
    (w.reinvesting.length ? ` Turn off reinvest for ${esc(w.symbol)} in ${w.reinvesting.map(esc).join(", ")} (has reinvested in the last 12 months).` : "") +
    (w.also_holds.length ? ` Also holds ${esc(w.symbol)}: ${w.also_holds.map(esc).join(", ")} (no recent reinvest; check contributions).` : "") + `</p>`).join("") + `</div>`;
}

export function swHtml(d = swData) {
  if (!d) return `<p class="muted">Loading…</p>`;
  const msg = swMessage ? `<p class="${swMessage.error ? "field-error" : "muted"}" role="status">${esc(swMessage.text)}</p>` : "";
  const done = d.reviewed.length ? `<details><summary>Reviewed (${d.reviewed.length})</summary><ul>` + d.reviewed.map((r, i) =>
    `<li>${esc(r.label)}: ${esc((SW_OUTCOMES.find((o) => o[0] === r.outcome) || [0, r.outcome])[1])}${r.reason ? ` (${esc(r.reason)})` : ""} <button class="btn" type="button" onclick="swUndo(${i})">Undo</button></li>`).join("") + `</ul></details>` : "";
  return `${msg}${swWindowsHtml()}${d.cards.length ? d.cards.map(swCardHtml).join("") : `<p class="muted">No wash sales to review.</p>`}${done}` +
    `<button class="btn" type="button" onclick="swRefresh()">Check for wash sales</button>`;
}

export const renderSalesWash = () => { if (swData === null) setTimeout(loadSalesWash, 0); return `<div id="swRoot">${swHtml()}</div>`; };
// Flagged sales are bad; otherwise the last-run marker warns "never run" or "stale" (a scan clears it).
export function swSummary() {
  const n = swData ? swData.cards.length : 0, run = (swData && swData.run) || {};
  return n ? { count: n, tone: "bad", text: `${n} to review` } : run.never_run ? { count: 0, tone: "warn", text: "never run" } : run.stale ? { count: 0, tone: "warn", text: "stale" } : { count: 0, tone: "", text: "" };
}
export const swStateText = () => (swData ? (swData.cards.length ? "" : "No wash sales to review") : "");
function swPaint() {
  const el = typeof document !== "undefined" && document.getElementById("swRoot");
  if (el) el.innerHTML = swHtml();
  if (window.slPublish) { window.slPublish("wash", swSummary()); window.slPublish("windows", swWindows.length ? { count: swWindows.length, tone: "warn", text: `${swWindows.length} open wash window${swWindows.length === 1 ? "" : "s"}` } : { count: 0, tone: "", text: "" }); }
  if (window.slSecSetState) window.slSecSetState("wash", swStateText());
}
export async function loadSalesWash() {
  const year = window.slCurrentYear ? window.slCurrentYear() : "";
  try { swWindows = ((await api("/api/sales/wash/open-windows")) || {}).windows || []; } catch (e) { swWindows = []; }
  try { swData = year ? await api(`/api/sales/wash?year=${encodeURIComponent(year)}`) : { cards: [], reviewed: [] }; } catch (e) { swData = { cards: [], reviewed: [] }; swMessage = { text: e.message, error: true }; }
  swPaint();
}
export function swOutcomeChanged(i) {
  const sel = document.getElementById(`swOutcome${i}`), lab = document.getElementById(`swReasonLabel${i}`);
  if (sel && lab) lab.hidden = sel.value !== "not_wash";
}
async function swPost(url, body, okText) {
  try { await api(url, { method: "POST", body: JSON.stringify(body) }); swMessage = { text: okText, error: false }; } catch (e) { swMessage = { text: e.message, error: true }; swPaint(); return false; }
  await loadSalesWash();
  if (window.loadSalesLedger) window.loadSalesLedger();
  return true;
}
export function swSave(i) {
  const c = swData && swData.cards[i];
  const val = (id) => { const el = document.getElementById(id); return el ? el.value : ""; };
  const outcome = val(`swOutcome${i}`) || "wash", reason = val(`swReason${i}`);
  const bad = swValidate(outcome, reason);
  if (bad) { swMessage = { text: bad, error: true }; swPaint(); return Promise.resolve(false); }
  return c ? swPost("/api/sales/wash/review", { sale_key: c.sale_key, outcome, reason }, "Review saved.") : Promise.resolve(false);
}
export const swUndo = (i) => swPost("/api/sales/wash/review/clear", { sale_key: swData.reviewed[i].sale_key }, "Review undone; the sale is back in the list.");
export const swRefresh = () => swPost("/api/sales/wash/refresh", {}, "Wash-sale check done.");

Object.assign(window, { swWindowsHtml, swValidate, swCardHtml, swHtml, renderSalesWash, swSummary, swStateText, loadSalesWash, swOutcomeChanged, swSave, swUndo, swRefresh });
