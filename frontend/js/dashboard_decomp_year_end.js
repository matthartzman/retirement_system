// "Year-End Transition" page (year-end transition Phase 2): an ordered checklist for moving from one calendar year to the next.
// Step state is derived server-side (src/year_end.py, GET /api/year-end); "Update personal numbers" and "tie the 1099-B" are stored
// confirmations. Each step links to the screen that does it. Helpers are bare globals.
const YE_STATE = { done: "Done", open: "Open", na: "Not applicable" };
const YE_CONFIRM = { personal_numbers: "I have reviewed these", tie_1099b: "I have tied each 1099-B" };
let yeData = null, yeError = "";
export function yeHtml(data) {
  if (!data) return `<h2>Year-End Transition</h2><p class="muted">${yeError ? "" : "Loading…"}</p>${panelMsgHtml("ye", yeError && { text: yeError, error: true }, "error")}`;
  const items = data.steps.map((s, i) => `<li data-step="${esc(s.id)}" data-state="${esc(s.state)}"><b>${i + 1}. ${esc(s.title)}</b> <span class="muted">${esc(YE_STATE[s.state] || s.state)}</span><br>` +
    `${esc(s.detail)} <a href="#" onclick="${s.hash ? `yeGo(${esc(JSON.stringify(s.link))}, ${esc(JSON.stringify(s.hash))})` : `setStep(${esc(JSON.stringify(s.link))})`};return false">Go to this step</a>` +
    (YE_CONFIRM[s.id] && s.state !== "na" && !(s.id === "tie_1099b" && s.state === "done" && s.count_known === true) ? ` <button class="btn" type="button" onclick="yeConfirm(${data.year}, ${s.state === "done" ? "false" : "true"}${s.id === "personal_numbers" ? "" : `, ${esc(JSON.stringify(s.id))}`})">${s.state === "done" ? "Undo confirmation" : YE_CONFIRM[s.id]}</button>` : "") + `</li>`).join("");
  return `<h2>Year-End Transition</h2><p>Closing ${esc(String(data.year))}${data.closed ? " (cash year closed)" : ""}. Each step's state comes from your data; nothing here changes the plan's tax numbers.</p>` +
    `${panelMsgHtml("ye", yeError && { text: yeError, error: true }, "error")}<ol class="ye-steps">${items}</ol>` +
    (window.renderCashInvestment ? `<h3>Investment cash, ${esc(String(data.year))}</h3>${window.renderCashInvestment(data.year)}` : "");
}
// A step with a deep link sets the hash first (the Sales Ledger reads tab/section from it); location may not exist (node tests).
export function yeGo(link, hash) {
  try { // replace, never push: following a step must not add a history entry
    if (hash && typeof location !== "undefined" && location) {
      if (typeof history !== "undefined" && history.replaceState) history.replaceState(null, "", hash); else location.hash = hash;
    }
  } catch (e) { /* navigate anyway */ }
  setStep(link);
}
export function renderYearEnd() {
  if (yeData === null) setTimeout(yeLoad, 0);
  return `<div class="sl-import" id="yeRoot">${yeHtml(yeData)}</div>`;
}
const yePaint = () => { const el = document.getElementById("yeRoot"); if (el) el.innerHTML = yeHtml(yeData); };
export async function yeLoad() {
  try { yeData = await api("/api/year-end"); yeError = ""; } catch (e) { yeError = e.message; }
  yePaint();
}
export async function yeConfirm(year, confirmed, step = "personal_numbers") {
  try { yeData = await api("/api/year-end/confirm", { method: "POST", body: JSON.stringify({ year, step, confirmed }) }); yeError = ""; } catch (e) { yeError = e.message; }
  yePaint();
}
// Plan Status nudge, mid-December through January (the page stays reachable all year from the nav).
export function renderYearEndBanner(now = new Date()) {
  const m = now.getMonth() + 1, d = now.getDate();
  return (m === 12 && d >= 15) || m === 1
    ? `<div class="section-note" data-kind="state"><b>Year-end:</b> a checklist is ready. <a href="#" onclick="setStep('year_end');return false">Open Year-End Transition</a></div>` : "";
}
Object.assign(window, { renderYearEnd, yeHtml, yeGo, yeLoad, yeConfirm, renderYearEndBanner });