// 1099-B import panel, mounted on the Sales Ledger page (plan 5.4, step 5.2 UI). All logic is on the server
// (src/sales_1099b.py, /api/sales/1099b/preview and /apply): this chooses the Planner account and broker, takes the
// statement as pasted text, a text file or a PDF (base64), shows the difference report (matched / unmatched / unreported
// lines, totals, the wash-sale loss disallowed from column 1g), applies it, and exports the report as CSV.
// The Planner account is always the user's choice, never read from the statement. Helpers are bare globals.

const BB_BROKERS = [["etrade", "E*Trade"], ["vanguard", "Vanguard"]];
const BB_STATUS = { changed: "Changed", unchanged: "Matches the ledger", not_previously_entered: "Not previously entered", no_1099b_line: "No 1099-B line" };
const BB_FIELD = { proceeds: "Proceeds", basis: "Basis", gain: "Gain", holding_period: "Holding period", purchase_date: "Acquired", sale_date: "Sold" };

let bbBroker = "etrade";
let bbAccount = "";
let bbText = "";
let bbPdf = ""; // base64 of an uploaded PDF; wins over pasted text
let bbFile = "";
let bbAccounts = null; // null = not loaded yet
let bbPreview = null;
let bbPreviewKey = ""; // the request body the current preview was built from; Apply refuses any other
let bbMessage = null; // { text, error }
let bbBusy = false;
let bbViewed = false; // the user ticked "I have reviewed this difference report" for the current preview
let bbDone = null; // set after a successful apply: drives the next-step links

const bbMoney = (v) => (Number(v) < 0 ? "-$" : "$") + Math.abs(Number(v) || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const bbQty = (v) => esc(String(Math.round(Number(v) * 1e3) / 1e3));
const bbLabel = (a) => (window.accountDisplayLabel ? window.accountDisplayLabel(a) : String(a));
function bbMoneyCell(f) {
  if (!f || f.official === null || f.official === undefined) return `<td class="rc-num">${f ? bbMoney(f.ledger) : ""}</td>`;
  const d = Number(f.delta) || 0;
  return `<td class="rc-num">${bbMoney(f.ledger)} &rarr; ${bbMoney(f.official)}${Math.abs(d) > 0.005 ? ` <span class="muted">(${d > 0 ? "+" : ""}${bbMoney(d)})</span>` : ""}</td>`;
}

export const bbSuggestionsHtml = (r) => ((r.suggestions || []).length ? `<br><span class="muted">Possible ledger rows (advice only, nothing is applied):</span><ul class="bb-suggest">${r.suggestions.map((c) => `<li>Ledger row ${Number(c.sale_id)}, score ${Number(c.score)}: ${esc(c.reason)}</li>`).join("")}</ul>` : "");
export function bbReportRowHtml(r) {
  const f = r.fields || {};
  const hp = f.holding_period || {};
  const hold = hp.official ? (hp.ledger && hp.ledger !== hp.official ? `${esc(hp.ledger)} &rarr; ${esc(hp.official)}` : esc(hp.official)) : esc(hp.ledger || "");
  const note = r.note || Object.values(f).map((x) => x.note).filter(Boolean).join("; ");
  const changed = (r.changed || []).map((k) => BB_FIELD[k] || k).join(", ");
  return `<tr class="bb-${esc(r.status)}"><td>${esc(BB_STATUS[r.status] || r.status)}${changed ? `<br><span class="muted">${esc(changed)}</span>` : ""}</td>` +
    `<td>${esc(r.symbol || "(no symbol)")}</td><td>${esc(r.date_sold)}</td><td class="rc-num">${bbQty(r.quantity)}</td>` +
    `${bbMoneyCell(f.proceeds)}${bbMoneyCell(f.basis)}${bbMoneyCell(f.gain)}<td>${hold}</td>` +
    `<td class="rc-num">${Number(r.wash_disallowed) ? bbMoney(r.wash_disallowed) : ""}</td><td class="muted">${esc(note)}${r.possible_return_of_capital ? ` <strong>Possible return of capital (${bbMoney(r.possible_return_of_capital.amount)})</strong>` : ""}${bbSuggestionsHtml(r)}</td></tr>`;
}

export function bbTotalsHtml(t) {
  const n = (k, label) => `<li>${Number(t[k] || 0)} ${label}</li>`;
  return `<ul class="bb-totals">${n("changed", "changed")}${n("unchanged", "matching the ledger")}${n("not_previously_entered", "not previously entered (will be added)")}` +
    `${n("no_1099b_line", "ledger rows with no 1099-B line")}</ul>` +
    `<p>Net change if applied: proceeds ${bbMoney(t.proceeds_delta)}, basis ${bbMoney(t.basis_delta)}, gain ${bbMoney(t.gain_delta)}. ` +
    `Wash-sale loss disallowed (column 1g): ${bbMoney(t.wash_disallowed)}.</p>`;
}

export function bbReportHtml(report) {
  if (!report || !report.rows.length) return `<p class="muted">Nothing to compare.</p>`;
  return `<h4>Difference report for ${esc(String(report.tax_year))}</h4>${bbTotalsHtml(report.totals)}` +
    `<div class="rc-scroll"><table class="rc-table"><thead><tr><th>Status</th><th>Symbol</th><th>Sold</th><th class="rc-num">Shares</th>` +
    `<th class="rc-num">Proceeds</th><th class="rc-num">Basis</th><th class="rc-num">Gain</th><th>Term</th><th class="rc-num">Wash-sale loss disallowed (1g)</th><th>Note</th></tr></thead><tbody>` +
    report.rows.map(bbReportRowHtml).join("") + `</tbody></table></div>`;
}

export function bbControlHtml(c) {
  if (!c) return "";
  if (c.status === "ok") return `<p class="muted" role="status">Control totals tie to the statement's 1099-B summary.</p>`;
  if (c.status === "missing") return `<p class="field-error">No 1099-B summary totals were found, so the lines cannot be verified.</p>`;
  return `<div class="field-error"><p>Control totals do not match the statement summary:</p><ul>` +
    (c.gaps || []).map((g) => `<li>${esc(g.term)} ${g.covered ? "covered" : "noncovered"} ${esc(g.column)}: statement ${bbMoney(g.statement)}, lines ${bbMoney(g.detail)} (difference ${bbMoney(g.difference)})</li>`).join("") + `</ul></div>`;
}

export function bbChangesHtml(p) {
  if (!p.supersedes) return "";
  const s = p.supersedes;
  const rows = (p.changes_since_previous || []).map((c) => `<li>${esc(c.change)}: ${esc(c.symbol || "(no symbol)")} sold ${esc(c.date_sold)}` +
    Object.entries(c.fields || {}).map(([k, v]) => ` — ${esc(k)} ${v.delta !== undefined ? `${bbMoney(v.old)} &rarr; ${bbMoney(v.new)}` : `${esc(v.old)} &rarr; ${esc(v.new)}`}`).join("") + `</li>`).join("");
  return `<div class="field-warning"><p>An earlier ${esc(p.broker)} statement for this account and year was imported (${esc(String(s.applied_at || ""))}, ${Number(s.line_count)} lines${s.corrected ? ", corrected" : ""}). ` +
    `Applying this one replaces it: the earlier corrections are undone first.</p>${rows ? `<p>Changes since that import:</p><ul>${rows}</ul>` : `<p>No line changed since that import.</p>`}</div>`;
}

// Apply needs what the server already requires (can_apply: clean statement, control totals tie) plus the user's review.
export const bbCanApply = (preview, viewed) => !!(preview && preview.can_apply) && !!viewed;
const bbReason = (p, v) => (bbCanApply(p, v) ? "" : "Review the differences and tick the box; totals must tie.");
export function bbMarkViewed(on) { // in place: repainting the root would drop keyboard focus from the checkbox
  bbViewed = !!on;
  const btn = document.getElementById("bbApplyBtn");
  const why = document.getElementById("bbApplyReason");
  if (btn) btn.disabled = !bbCanApply(bbPreview, bbViewed) || bbBusy;
  if (why) why.textContent = bbReason(bbPreview, bbViewed);
}

export function bbPreviewHtml(p) {
  const errs = (p.errors || []).map((e) => `<li>${e.line ? `Line ${Number(e.line)}: ` : ""}${esc(e.error)}</li>`).join("");
  const warns = (p.warnings || []).map((w) => `<li>${esc(w)}</li>`).join("");
  const meta = p.meta || {};
  const head = `<p>${Number(p.received)} lines read for ${esc(bbLabel(p.account))}, tax year ${esc(String(p.tax_year))}` +
    `${meta.corrected ? ` <strong>(CORRECTED statement${meta.statement_date ? ` dated ${esc(meta.statement_date)}` : ""})</strong>` : ""}.</p>`;
  return `<div class="sl-preview bb-preview">${head}${errs ? `<ul class="field-error">${errs}</ul>` : ""}${warns ? `<ul class="field-warning">${warns}</ul>` : ""}` +
    `${bbControlHtml(p.control_totals)}${bbChangesHtml(p)}${bbReportHtml(p.report)}` +
    `<label class="bb-viewed"><input type="checkbox" ${bbViewed ? "checked" : ""} onchange="bbMarkViewed(this.checked)"> I have reviewed this difference report</label>` +
    `<div class="bb-actions"><button class="btn" type="button" onclick="bbExportCsv()">Export report CSV</button> ` +
    `<button class="btn primary" type="button" id="bbApplyBtn" aria-describedby="bbApplyReason" onclick="bbApply()" ${bbCanApply(p, bbViewed) && !bbBusy ? "" : "disabled"}>${p.supersedes ? "Replace earlier import and apply" : "Apply official numbers"}</button>` +
    ` <span class="muted" id="bbApplyReason">${bbReason(p, bbViewed)}</span></div></div>`;
}

function bbBodyHtml() {
  const accounts = bbAccounts || [];
  const msg = bbMessage ? `<p class="${bbMessage.error ? "field-error" : "muted"}" role="status">${esc(bbMessage.text)}</p>` : "";
  const steps = window.slStepsHtml ? window.slStepsHtml(bbPreview ? 2 : 1) : "";
  return `${steps}<h3>Import a broker 1099-B</h3><p class="muted">Paste the statement text or choose the file (text or PDF with a text layer). Preview never changes the ledger; ` +
    `applying writes the broker's official numbers and keeps the earlier values in an audit trail.</p>` +
    `<div class="field-grid"><label>Broker<select aria-label="1099-B broker" onchange="bbSetBroker(this.value)">${BB_BROKERS.map(([v, l]) => `<option value="${v}" ${v === bbBroker ? "selected" : ""}>${l}</option>`).join("")}</select></label>` +
    `<label>Planner account<select aria-label="1099-B Planner account" onchange="bbSetAccount(this.value)"><option value="">Choose…</option>` +
    accounts.map((a) => `<option value="${esc(a)}" ${a === bbAccount ? "selected" : ""}>${esc(bbLabel(a))}</option>`).join("") + `</select></label>` +
    `<label>Statement file<input type="file" accept=".txt,.csv,.pdf,text/plain,application/pdf" aria-label="1099-B statement file" onchange="bbFileChosen(this)"></label></div>` +
    `<label>Or paste the statement text<textarea id="bbText" rows="4" aria-label="1099-B statement text" oninput="bbSetText(this.value)">${esc(bbPdf ? "" : bbText)}</textarea></label>` +
    `${bbFile ? `<p class="muted">File: ${esc(bbFile)}</p>` : ""}` +
    `<button class="btn" type="button" onclick="bbPreviewStatement()" ${bbBusy ? "disabled" : ""}>Preview</button>${msg}${bbPreview ? bbPreviewHtml(bbPreview) : ""}${bbDone && window.slNextStepHtml ? window.slNextStepHtml(bbDone) : ""}`;
}

export function renderSalesBroker1099b() {
  if (bbAccounts === null) setTimeout(bbLoadAccounts, 0);
  return `<div class="sl-import bb-panel" id="bbRoot">${bbBodyHtml()}</div>`;
}

// The panel holds no per-account "tied" data yet, so nothing is reported as untied.
export const bbStateText = () => (bbPreview ? `Preview ready · tax year ${bbPreview.tax_year}` : "");
export const bbSummary = () => ({ count: 0, tone: "", text: "" });

function bbPaint() {
  if (window.slPublish) window.slPublish("b1099", bbSummary());
  if (window.slSecSetState) window.slSecSetState("b1099", bbStateText());
  const root = document.getElementById("bbRoot");
  if (!root) return;
  const old = root.querySelector('input[type="file"]');
  const ta = root.querySelector("textarea");
  const typed = ta ? ta.value : null;
  root.innerHTML = bbBodyHtml();
  const fresh = old && old.files && old.files.length && root.querySelector('input[type="file"]');
  if (fresh) fresh.replaceWith(old);
  const ta2 = root.querySelector("textarea");
  if (ta2 && typed !== null && !bbPdf) ta2.value = typed;
}

export async function bbLoadAccounts() {
  try { bbAccounts = (await api("/api/sales/broker/imports")).accounts || []; } catch (e) { bbAccounts = []; }
  bbPaint();
}

export function bbSetBroker(v) { bbBroker = v; bbPreview = null; bbDone = null; bbPaint(); }
export function bbSetAccount(v) { bbAccount = v; bbPreview = null; bbDone = null; bbPaint(); }
export function bbSetText(v) {
  const hadDone = !!bbDone;
  bbText = v; bbPdf = ""; bbFile = ""; bbPreview = null; bbDone = null;
  const next = hadDone && typeof document !== "undefined" && document.getElementById("bbRoot");
  const el = next && next.querySelector && next.querySelector(".sl-next");
  if (el && el.remove) el.remove(); // drop the stale next-step links without repainting (a repaint would move the caret)
}

export function bbFileChosen(input) {
  const file = input.files && input.files[0];
  if (!file) return;
  const reader = new FileReader();
  const pdf = /\.pdf$/i.test(file.name) || file.type === "application/pdf";
  reader.onload = () => {
    const out = String(reader.result || "");
    bbFile = file.name; bbPreview = null; bbDone = null;
    if (pdf) { bbPdf = out.slice(out.indexOf(",") + 1); bbText = ""; } else { bbText = out; bbPdf = ""; }
    bbPaint();
  };
  if (pdf) reader.readAsDataURL(file); else reader.readAsText(file);
}

const bbBody = () => ({ broker: bbBroker, account: bbAccount, ...(bbPdf ? { pdf_base64: bbPdf } : { content: bbText }) });

export async function bbPreviewStatement() {
  if (!bbAccount) { bbMessage = { text: "Choose the Planner account this statement belongs to.", error: true }; return bbPaint(); }
  if (!bbText && !bbPdf) { bbMessage = { text: "Paste the statement text or choose a file first.", error: true }; return bbPaint(); }
  bbBusy = true; bbViewed = false; bbDone = null; bbMessage = { text: "Previewing…", error: false }; bbPaint();
  const key = JSON.stringify(bbBody()); // the account, broker or statement may change while the request is in flight
  try {
    const out = await api("/api/sales/1099b/preview", { method: "POST", body: key });
    if (JSON.stringify(bbBody()) !== key) bbMessage = null; // a preview of other inputs: drop it
    else { bbPreview = out; bbPreviewKey = key; bbMessage = null; bbViewed = false; }
  } catch (e) { bbPreview = null; bbMessage = { text: e.message, error: true }; }
  bbBusy = false; bbPaint();
}

export async function bbApply() {
  if (!bbCanApply(bbPreview, bbViewed)) return;
  if (JSON.stringify(bbBody()) !== bbPreviewKey) { bbMessage = { text: "The inputs changed after this preview — preview again.", error: true }; return bbPaint(); }
  const replace = !!bbPreview.supersedes;
  if (replace && !(window.confirm && window.confirm("An earlier statement for this account and year was imported. Replace it with this one?"))) return;
  bbBusy = true; bbPaint();
  try {
    const out = await api("/api/sales/1099b/apply", { method: "POST", body: JSON.stringify({ ...bbBody(), replace }) });
    bbMessage = { text: `Applied: ${out.corrected} ledger row(s) corrected, ${out.added} added${out.superseded ? `, earlier statement ${out.superseded} replaced` : ""}.`, error: false };
    bbPreview = null; bbViewed = false;
    bbDone = { wash: true };
  } catch (e) { bbMessage = { text: e.message, error: true }; }
  bbBusy = false; bbPaint();
  if (window.loadSalesLedger) window.loadSalesLedger();
  if (window.sqReload) window.sqReload();
}

export function bbExportCsv() {
  if (!bbPreview || !bbPreview.report_csv) return;
  const name = `1099b_difference_${bbBroker}_${bbPreview.tax_year}.csv`;
  if (window.downloadBlob) { window.downloadBlob(name, bbPreview.report_csv); return; }
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([bbPreview.report_csv], { type: "text/csv;charset=utf-8" }));
  a.download = name;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500);
}

Object.assign(window, {
  bbSummary, bbCanApply, bbMarkViewed, bbStateText,
  bbSuggestionsHtml, bbReportRowHtml, bbTotalsHtml, bbReportHtml, bbControlHtml, bbChangesHtml, bbPreviewHtml, renderSalesBroker1099b, bbLoadAccounts,
  bbSetBroker, bbSetAccount, bbSetText, bbFileChosen, bbPreviewStatement, bbApply, bbExportCsv,
});
