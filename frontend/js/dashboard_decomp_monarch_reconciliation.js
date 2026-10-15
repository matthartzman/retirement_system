// Monarch Reconciliation page (Reports & Review): the app's account numbers beside Monarch's daily
// balances, with a way to copy Monarch's number into the app where they differ.
// Logic and every write live on the server (src/reconcile.py, /api/reconcile/*): the page only shows
// rows, collects a selection, asks for a preview, then applies it. Each applied change is logged and can
// be undone from the change log. Investment accounts (valued from holdings x prices) and annuities that
// take their value from an income stream are report only.
// Helpers are bare globals; renderMain() calls renderMonarchReconciliation().

const RC_GROUPS = ["Cash, cards and loans", "Manual accounts", "Plan inputs", "Investments (report only)"];
const RC_STATUS_LABEL = {
  differs: "Differs", match: "Matches", report_only: "Report only",
  not_in_monarch: "Not in Monarch", not_in_app: "Not in app",
};

let rcData = null;
let rcLog = [];
let rcLoading = false;
let rcError = "";
let rcAsOf = "";
let rcTolerance = 1;
let rcSelected = new Set();
let rcPreviewData = null;
let rcShowMatched = false;
let rcMessage = null; // { text, error }
let rcSeq = 0;

// ── pure html helpers (exported for tests) ───────────────────────────────────────────────────
export function rcMoney(v) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "—";
  const n = Number(v);
  return (n < 0 ? "-$" : "$") + Math.abs(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function rcDiffHtml(v) {
  if (v === null || v === undefined) return "—";
  const cls = Math.abs(v) < 0.005 ? "" : v > 0 ? " rc-up" : " rc-down";
  return `<span class="rc-num${cls}">${esc((v > 0 ? "+" : "") + rcMoney(v))}</span>`;
}

export function rcSummary(rows, unmatched) {
  const count = (s) => rows.filter((r) => r.status === s).length;
  return { differs: count("differs"), match: count("match"), reportOnly: count("report_only"),
    notInMonarch: count("not_in_monarch"), notInApp: (unmatched || []).length };
}

function rcMatchedNames(row, asOf) {
  const accts = row.monarch_accounts || [];
  if (!accts.length) return "";
  const note = row.auto_matched ? "matched by name" : "matched by you";
  return `<div class="rc-sub">${accts.map((a) => esc(a.account) + (a.closed ? " (closed)" : "") +
    (a.balance_date && a.balance_date !== asOf ? ` (balance from ${esc(a.balance_date)})` : "")).join(" + ")} · ${note}</div>`;
}

export function rcRowHtml(row, selected, asOf) {
  const box = row.updatable
    ? `<input type="checkbox" data-id="${esc(row.id)}" aria-label="Update ${esc(row.label)}" onchange="rcToggle(this.dataset.id, this.checked)"${selected ? " checked" : ""}>`
    : "";
  const status = row.report_reason
    ? `<span class="rc-status rc-report" title="${esc(row.report_reason)}">Report only</span><div class="rc-sub">${esc(row.report_reason)}</div>`
    : `<span class="rc-status rc-${esc(row.status)}">${esc(RC_STATUS_LABEL[row.status] || row.status)}</span>`;
  return `<tr class="rc-row rc-${esc(row.status)}" data-row="${esc(row.id)}"><td class="rc-box">${box}</td>` +
    `<td>${esc(row.label)}${rcMatchedNames(row, asOf)}</td>` +
    `<td class="rc-num">${esc(rcMoney(row.app_value))}</td><td class="rc-num">${esc(rcMoney(row.monarch_value))}</td>` +
    `<td class="rc-num">${rcDiffHtml(row.difference)}</td><td>${status}</td></tr>`;
}

export function rcGroupsHtml(data, selected, showMatched) {
  const rows = data.rows || [];
  let html = "";
  for (const g of RC_GROUPS) {
    const inGroup = rows.filter((r) => r.group === g);
    if (!inGroup.length) continue;
    const shown = inGroup.filter((r) => showMatched || r.status !== "match");
    const hidden = inGroup.length - shown.length;
    const selectable = shown.filter((r) => r.updatable);
    const all = selectable.length && selectable.every((r) => selected.has(r.id));
    const head = `<div class="rc-group-head"><h3>${esc(g)}</h3>` +
      (selectable.length ? `<button class="btn" type="button" onclick="rcSelectGroup(${esc(JSON.stringify(g))}, ${all ? "false" : "true"})">${all ? "Clear" : "Select all differences"}</button>` : "") +
      (hidden ? `<span class="rc-sub">${hidden} matching hidden</span>` : "") + "</div>";
    html += head + (shown.length
      ? `<div class="rc-scroll"><table class="rc-table"><thead><tr><th></th><th>Account</th><th class="rc-num">App</th><th class="rc-num">Monarch</th><th class="rc-num">Difference</th><th>Status</th></tr></thead><tbody>` +
        shown.map((r) => rcRowHtml(r, selected.has(r.id), data.as_of)).join("") + "</tbody></table></div>"
      : '<div class="section-note">Everything here matches.</div>');
  }
  return html || '<div class="section-note">No accounts to compare yet.</div>';
}

export function rcPreviewHtml(preview) {
  if (!preview) return "";
  const changes = preview.changes || [];
  const rejected = preview.rejected || [];
  const planInput = changes.some((c) => String(c.kind || "").startsWith("plan:"));
  const rows = changes.map((c) => `<tr><td>${esc(c.label)}</td><td class="rc-num">${esc(c.old === "" ? "blank" : c.old)}</td><td class="rc-num">${esc(c.new)}</td>` +
    `<td class="rc-num">${esc(rcMoney(c.app_value))} → ${esc(rcMoney(c.monarch_value))}</td></tr>`).join("");
  return `<div class="rc-preview" role="dialog" aria-label="Preview update from Monarch"><h3>Update ${changes.length} number${changes.length === 1 ? "" : "s"} from Monarch</h3>` +
    (changes.length ? `<div class="rc-scroll"><table class="rc-table"><thead><tr><th>Account</th><th class="rc-num">Stored now</th><th class="rc-num">Will store</th><th class="rc-num">App → Monarch</th></tr></thead><tbody>${rows}</tbody></table></div>` : '<div class="section-note">Nothing to update.</div>') +
    (planInput ? '<div class="section-note rc-warn">Plan inputs change what the next build calculates. Rebuild after applying.</div>' : "") +
    (rejected.length ? `<div class="section-note">${rejected.map((r) => esc(r.id) + ": " + esc(r.reason)).join("<br>")}</div>` : "") +
    `<div class="pane-actions"><button class="btn good" type="button" onclick="rcApply()"${changes.length ? "" : " disabled"}>Apply ${changes.length} change${changes.length === 1 ? "" : "s"}</button> ` +
    `<button class="btn" type="button" onclick="rcPreviewCancel()">Cancel</button></div></div>`;
}

export function rcUnmatchedHtml(data) {
  const items = data.unmatched || [];
  if (!items.length) return "";
  const targets = data.app_targets || [];
  const opts = (sel) => '<option value="">Match to…</option>' +
    `<option value="ignore">Ignore this Monarch account</option>` +
    targets.map((t) => `<option value="${esc(t.id)}"${t.id === sel ? " selected" : ""}>${esc(t.label)}${t.role ? " (" + esc(t.role) + ")" : ""}</option>`).join("");
  return `<h3>Monarch accounts with no match in the app</h3><div class="rc-scroll"><table class="rc-table"><thead><tr><th>Monarch account</th><th class="rc-num">Balance</th><th>Match it to</th></tr></thead><tbody>` +
    items.map((u) => `<tr><td>${esc(u.label)}${u.closed ? ' <span class="rc-sub">(closed)</span>' : ""}</td><td class="rc-num">${esc(rcMoney(u.monarch_value))}</td>` +
      `<td><select data-key="${esc(u.account_key)}" aria-label="Match ${esc(u.label)} to" onchange="rcMap(this.dataset.key, this.value)">${opts("")}</select></td></tr>`).join("") +
    "</tbody></table></div>";
}

export function rcLogHtml(log) {
  if (!log || !log.length) return '<div class="section-note">No updates from Monarch yet.</div>';
  return '<div class="rc-scroll"><table class="rc-table"><thead><tr><th>When</th><th>Account</th><th class="rc-num">Old</th><th class="rc-num">New</th><th>Monarch date</th><th></th></tr></thead><tbody>' +
    log.map((e) => `<tr><td>${esc(String(e.applied_at || "").replace("T", " ").replace("+00:00", " UTC"))}</td><td>${esc(e.label)}</td>` +
      `<td class="rc-num">${esc(e.old_value === "" ? "blank" : e.old_value)}</td><td class="rc-num">${esc(e.new_value)}</td><td>${esc(e.monarch_date)}</td>` +
      `<td>${e.undone_at ? '<span class="rc-sub">undone</span>' : `<button class="btn" type="button" data-id="${esc(String(e.id))}" onclick="rcUndo(this.dataset.id)">Undo</button>`}</td></tr>`).join("") +
    "</tbody></table></div>";
}

export function rcImportNote(data) {
  const last = data.import, ok = data.last_ok_import;
  if (last && last.status !== "ok") {
    return `The latest Monarch balances import was rejected (${esc(last.detail || "unknown reason")}); these figures are from ${esc(ok && ok.latest_date ? ok.latest_date : "an earlier import")}.`;
  }
  return "";
}

export function rcBodyHtml(state) {
  const { data, loading, error, message, selected, preview, showMatched, tolerance, log } = state;
  if (error) return `<div class="section-note rc-warn">${esc(error)} <button class="btn" type="button" onclick="loadMonarchReconciliation()">Retry</button></div>`;
  if (!data) return `<div class="section-note">${loading ? "Loading the comparison…" : "Nothing loaded yet."}</div>`;
  if (!data.has_balances) {
    return '<div class="section-note">No Monarch balances have been imported into this plan yet. They arrive with the daily Monarch import (the Monarch Extractor writes balances.csv, then the 04:00 job loads it).</div>';
  }
  const s = rcSummary(data.rows, data.unmatched);
  const dates = (data.dates || []).map((d) => `<option value="${esc(d)}"${d === data.as_of ? " selected" : ""}>${esc(d)}${d === data.latest ? " (latest)" : ""}</option>`).join("");
  const note = rcImportNote(data);
  const nSel = [...selected].filter((id) => data.rows.some((r) => r.id === id && r.updatable)).length;
  return (message ? `<div class="section-note${message.error ? " rc-warn" : ""}" role="status">${esc(message.text)}</div>` : "") +
    (note ? `<div class="section-note rc-warn" role="alert">${note}</div>` : "") +
    `<div class="rc-controls"><label>Compare as of <select id="rcAsOf" onchange="rcSetAsOf(this.value)">${dates}</select></label> ` +
    `<label>Count as matching within <select onchange="rcSetTolerance(this.value)">${[1, 10, 100].map((t) => `<option value="${t}"${t === tolerance ? " selected" : ""}>$${t}</option>`).join("")}</select></label> ` +
    `<label><input type="checkbox" onchange="rcSetShowMatched(this.checked)"${showMatched ? " checked" : ""}> Show matching accounts (${s.match})</label></div>` +
    `<div class="rc-summary"><strong>${s.differs}</strong> differ · <strong>${s.match}</strong> match · <strong>${s.reportOnly}</strong> report only · ` +
    `<strong>${s.notInMonarch}</strong> not in Monarch · <strong>${s.notInApp}</strong> Monarch accounts not in the app</div>` +
    `<div class="pane-actions"><button class="btn good" type="button" onclick="rcPreview()"${nSel ? "" : " disabled"}>Preview update from Monarch (${nSel} selected)</button></div>` +
    rcPreviewHtml(preview) + rcGroupsHtml(data, selected, showMatched) + rcUnmatchedHtml(data) +
    `<h3>Change log</h3>${rcLogHtml(log)}`;
}

// ── page ─────────────────────────────────────────────────────────────────────────────────────
function rcState() {
  return { data: rcData, loading: rcLoading, error: rcError, message: rcMessage, selected: rcSelected,
    preview: rcPreviewData, showMatched: rcShowMatched, tolerance: rcTolerance, log: rcLog };
}

export function renderMonarchReconciliation() {
  if (rcData === null && !rcLoading && !rcError) setTimeout(loadMonarchReconciliation, 0);
  return `<div class="field-list rc-page" id="rcRoot">${rcBodyHtml(rcState())}</div>`;
}

function rcPaint() {
  const root = document.getElementById("rcRoot");
  if (root) root.innerHTML = rcBodyHtml(rcState());
}

export async function loadMonarchReconciliation() {
  const seq = ++rcSeq;
  rcLoading = true;
  rcError = "";
  try {
    const q = new URLSearchParams();
    if (rcAsOf) q.set("as_of", rcAsOf);
    q.set("tolerance", String(rcTolerance));
    const [out, log] = await Promise.all([api("/api/reconcile?" + q), api("/api/reconcile/log")]);
    if (seq !== rcSeq) return;
    rcData = out && out.success ? out : null;
    rcLog = log && log.success ? log.log : [];
    if (!rcData) rcError = "The comparison could not be loaded.";
    else rcSelected = new Set([...rcSelected].filter((id) => rcData.rows.some((r) => r.id === id && r.updatable)));
  } catch (e) {
    if (seq !== rcSeq) return;
    rcData = null;
    rcError = "The comparison could not be loaded: " + e.message;
  }
  rcLoading = false;
  rcPaint();
}

export function rcToggle(id, on) {
  if (on) rcSelected.add(id); else rcSelected.delete(id);
  rcPreviewData = null;
  rcPaint();
}

export function rcSelectGroup(group, on) {
  for (const r of rcData.rows) {
    if (r.group !== group || !r.updatable || (!rcShowMatched && r.status === "match")) continue;
    if (on) rcSelected.add(r.id); else rcSelected.delete(r.id);
  }
  rcPreviewData = null;
  rcPaint();
}

export function rcSetAsOf(v) { rcAsOf = v; rcSelected = new Set(); rcPreviewData = null; rcMessage = null; loadMonarchReconciliation(); }
export function rcSetTolerance(v) { rcTolerance = Number(v) || 1; rcSelected = new Set(); rcPreviewData = null; loadMonarchReconciliation(); }
export function rcSetShowMatched(on) { rcShowMatched = !!on; rcPaint(); }
export function rcPreviewCancel() { rcPreviewData = null; rcPaint(); }

function rcItems() {
  return [...rcSelected].map((id) => ({ id }));
}

export async function rcPreview() {
  try {
    const out = await api("/api/reconcile/preview", { method: "POST", body: JSON.stringify({ items: rcItems(), as_of: rcData.as_of }) });
    rcPreviewData = out;
    rcMessage = null;
  } catch (e) {
    rcMessage = { text: "Could not preview: " + e.message, error: true };
  }
  rcPaint();
}

export async function rcApply() {
  if (!rcPreviewData) return;
  const items = rcPreviewData.changes.map((c) => ({ id: c.id, expected_new: c.new }));
  try {
    const out = await api("/api/reconcile/apply", { method: "POST", body: JSON.stringify({ items, as_of: rcData.as_of }) });
    const n = (out.applied || []).length;
    rcMessage = { text: n ? `Updated ${n} number${n === 1 ? "" : "s"} from Monarch. Rebuild to see them in results.` : "Nothing was changed.", error: !n };
    if (out.rejected && out.rejected.length) rcMessage.text += " Skipped: " + out.rejected.map((r) => r.reason).join("; ");
    if (n && typeof markBuildStale === "function") markBuildStale();
    rcSelected = new Set();
    rcPreviewData = null;
  } catch (e) {
    rcMessage = { text: "Could not apply: " + e.message, error: true };
  }
  await loadMonarchReconciliation();
}

export async function rcUndo(id) {
  try {
    const out = await api("/api/reconcile/undo", { method: "POST", body: JSON.stringify({ change_id: Number(id) }) });
    rcMessage = { text: `Restored ${out.label} to ${out.restored === "" ? "blank" : out.restored}.`, error: false };
    if (typeof markBuildStale === "function") markBuildStale();
  } catch (e) {
    rcMessage = { text: e.message, error: true };
  }
  await loadMonarchReconciliation();
}

export async function rcMap(accountKey, target) {
  try {
    await api("/api/reconcile/map", { method: "POST", body: JSON.stringify({ account_key: accountKey, target: target || null }) });
    rcMessage = { text: target ? "Saved the match." : "Cleared the match.", error: false };
  } catch (e) {
    rcMessage = { text: "Could not save the match: " + e.message, error: true };
  }
  await loadMonarchReconciliation();
}

Object.assign(window, {
  rcMoney, rcDiffHtml, rcSummary, rcRowHtml, rcGroupsHtml, rcPreviewHtml, rcUnmatchedHtml, rcLogHtml, rcImportNote, rcBodyHtml,
  renderMonarchReconciliation, loadMonarchReconciliation, rcToggle, rcSelectGroup, rcSetAsOf, rcSetTolerance, rcSetShowMatched,
  rcPreviewCancel, rcPreview, rcApply, rcUndo, rcMap,
});
