// Account Reconciliation page (Reports & Review): the app's account numbers beside the imported daily
// balances, with a way to copy the imported number into the app where they differ.
// Logic and every write live on the server (src/reconcile.py, /api/reconcile/*): the page only shows
// rows, collects a selection, asks for a preview, then applies it. Each applied change is logged and can
// be undone from the change log. Investment accounts (valued from holdings x prices) and annuities that
// take their value from an income stream are report only.
// Two tabs: "Needs a decision" (a difference needs one of Update app / Ignore this time / Always update / App is
// source) and "All mappings" (every match with its policy). Policy: ask, auto (copied at import, guarded),
// app (report only), ignore. Closed accounts with no balance are quiet; closed with money is flagged.
// Helpers are bare globals; renderMain() calls renderMonarchReconciliation().

const RC_GROUPS = ["Cash, cards and loans", "Manual accounts", "Plan inputs", "Investments (report only)"];
const RC_STATUS_LABEL = {
  differs: "Differs", match: "Matches", report_only: "Report only",
  not_in_monarch: "Not in import", not_in_app: "Not in app",
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
let rcTab = "inbox";
let rcDismissed = new Set(rcLoadDismissed());
let rcSeq = 0;
let rcLoadedAt = 0;
const RC_STALE_MS = 5000; // coming back to the page re-reads: Accounts & Sources may have changed meanwhile

const RC_POLICIES = [["ask", "Ask me"], ["auto", "Always update"], ["app", "App is source"], ["ignore", "Ignore"]];
function rcLoadDismissed() {
  try { return JSON.parse(localStorage.getItem("rcDismissed") || "[]"); } catch (e) { return []; }
}
function rcSaveDismissed() {
  try { localStorage.setItem("rcDismissed", JSON.stringify([...rcDismissed])); } catch (e) { /* storage unavailable: dismissal lasts this visit */ }
}

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
  // Each match can be removed: a saved match is cleared, a by-name match is switched off by ignoring that Imported account.
  const chip = (a) => esc(a.account) + (a.closed ? " (closed)" : "") +
    (a.balance_date && a.balance_date !== asOf ? ` (balance from ${esc(a.balance_date)})` : "") +
    ` <button class="rc-unmatch" type="button" data-key="${esc(a.account_key)}" data-auto="${a.auto ? "1" : ""}" title="Remove this match" aria-label="Remove match for ${esc(a.account)}" onclick="rcUnmatch(this.dataset.key, this.dataset.auto)">✕</button>`;
  return `<div class="rc-sub">${accts.map(chip).join(" + ")} · ${note}</div>`;
}

export function rcRowHtml(row, selected, asOf) {
  const box = row.updatable
    ? `<input type="checkbox" data-id="${esc(row.id)}" aria-label="Update ${esc(row.label)}" onchange="rcToggle(this.dataset.id, this.checked)"${selected ? " checked" : ""}>`
    : "";
  const status = row.report_reason
    ? `<span class="rc-status rc-report" title="${esc(row.report_reason)}">Report only</span><div class="rc-sub">${esc(row.report_reason)}</div>`
    : `<span class="rc-status rc-${esc(row.status)}">${esc(RC_STATUS_LABEL[row.status] || row.status)}</span>`;
  return `<tr class="rc-row rc-${esc(row.status)}" data-row="${esc(row.id)}"><td class="rc-box">${box}</td>` +
    `<td>${esc(row.label)}${rcMatchedNames(row, asOf)}</td>` + `<td>${rcPolicyHtml(row)}</td>` +
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
      ? `<div class="rc-scroll"><table class="rc-table"><thead><tr><th></th><th>Account</th><th>Policy</th><th class="rc-num">App</th><th class="rc-num">Imported</th><th class="rc-num">Difference</th><th>Status</th></tr></thead><tbody>` +
        shown.map((r) => rcRowHtml(r, selected.has(r.id), data.as_of)).join("") + "</tbody></table></div>"
      : '<div class="section-note">Everything here matches.</div>');
  }
  return html || '<div class="section-note">No accounts to compare yet.</div>';
}

// Policy control for a row: one select that sets the policy on every Imported account feeding it.
export function rcPolicyHtml(row) {
  const accts = row.monarch_accounts || [];
  if (!accts.length) return '<span class="rc-sub">—</span>';
  const keys = accts.map((a) => a.account_key).join("\u001f");
  const opts = RC_POLICIES.map(([v, l]) => `<option value="${v}"${v === (row.policy || "ask") ? " selected" : ""}>${esc(l)}</option>`).join("");
  return `<select class="rc-policy" data-keys="${esc(keys)}" aria-label="What to do when ${esc(row.label)} differs" onchange="rcSetPolicy(this.dataset.keys, this.value)">${opts}</select>`;
}

const rcDismissKey = (r) => r.id + "@" + r.monarch_value;

// What needs a decision: differences on rows set to ask (or held auto changes), minus ones dismissed for
// this imported number, plus Imported accounts with no match and closed accounts that still hold money.
export function rcInboxItems(data, dismissed) {
  const gone = dismissed || new Set();
  const open = (data.rows || []).filter((r) => r.status === "differs" && r.updatable && (r.policy !== "auto" || r.auto_hold));
  const diffs = open.filter((r) => !gone.has(rcDismissKey(r)));
  const unmatched = (data.unmatched || []).filter((u) => !gone.has("monarch:" + u.account_key + "@" + u.monarch_value));
  return { diffs, unmatched, hidden: open.length - diffs.length };
}

const rcHiddenHtml = (n) => n ? `<div class="section-note">${n} hidden by "Ignore this time". <button class="btn" type="button" onclick="rcRestoreDismissed()">Show hidden</button></div>` : "";

export function rcInboxRowHtml(row) {
  const btn = (act, label, cls) => `<button class="btn ${cls || ""}" type="button" data-id="${esc(row.id)}" onclick="rcDecide('${act}', this.dataset.id)">${label}</button>`;
  const hold = row.auto_hold ? `<div class="rc-sub rc-warn">${esc(row.auto_hold)}</div>` : "";
  return `<tr class="rc-row" data-row="${esc(row.id)}"><td>${esc(row.label)}${rcMatchedNames(row, "")}${hold}</td>` +
    `<td class="rc-num">${esc(rcMoney(row.app_value))}</td><td class="rc-num">${esc(rcMoney(row.monarch_value))}</td><td class="rc-num">${rcDiffHtml(row.difference)}</td>` +
    `<td class="rc-actions">${btn("update", "Update app", "good")} ${btn("ignore", "Ignore this time")} ${btn("always", "Always update")} ${btn("app", "App is source")}</td></tr>`;
}

export function rcInboxHtml(data, dismissed) {
  const { diffs, unmatched, hidden } = rcInboxItems(data, dismissed);
  if (!diffs.length && !unmatched.length) return '<div class="section-note">Nothing needs a decision. Every matched account agrees with the app, is handled automatically, or is set to ignore.</div>' + rcHiddenHtml(hidden);
  const table = diffs.length
    ? `<h3>Numbers that differ (${diffs.length})</h3><div class="rc-scroll"><table class="rc-table"><thead><tr><th>Account</th><th class="rc-num">App</th><th class="rc-num">Imported</th><th class="rc-num">Difference</th><th>Choose</th></tr></thead><tbody>${diffs.map(rcInboxRowHtml).join("")}</tbody></table></div>` +
      '<div class="section-note"><b>Update app</b> copies imported\'s number once (after a preview). <b>Always update</b> does that now and copies it automatically at each import. <b>App is source</b> keeps the app\'s number and only reports. <b>Ignore this time</b> hides it until imported\'s number changes.</div>'
    : "";
  const closedMoney = unmatched.filter((u) => u.status === "closed_with_balance");
  const flagged = closedMoney.length
    ? `<h3>Closed accounts that still show a balance (${closedMoney.length})</h3><div class="rc-scroll"><table class="rc-table"><tbody>${closedMoney.map((u) => `<tr><td>${esc(u.label)} <span class="rc-sub">stopped syncing ${esc(u.closed_since || "")}</span></td><td class="rc-num">${esc(rcMoney(u.monarch_value))}</td><td><button class="btn" type="button" data-key="${esc(u.account_key)}" onclick="rcMap(this.dataset.key, 'ignore')">Money moved: mark done</button></td></tr>`).join("")}</tbody></table></div>`
    : "";
  const rest = unmatched.filter((u) => u.status !== "closed_with_balance");
  return table + flagged + rcUnmatchedHtml({ ...data, unmatched: rest }) + rcHiddenHtml(hidden);
}

export function rcParkedHtml(data) {
  const items = data.parked_accounts || [];
  if (!items.length) return "";
  return `<details class="rc-ignored"><summary>Matched to something the page cannot update (${items.length}): report only</summary><ul>` +
    items.map((u) => `<li>${esc(u.label)} <span class="rc-sub">${esc(String(u.ref || "").split("|").pop())}</span></li>`).join("") + "</ul></details>";
}

export function rcClosedHtml(data) {
  const items = data.closed_accounts || [];
  if (!items.length) return "";
  return `<details class="rc-ignored"><summary>Closed accounts with no balance (${items.length}): nothing to decide</summary><ul>` +
    items.map((u) => `<li>${esc(u.label)} <span class="rc-sub">last balance ${esc(u.last_date || "")}</span></li>`).join("") + "</ul></details>";
}

// Automatic updates in the last 7 days, with a way to undo them all.
export function rcAutoBannerHtml(log, now) {
  const cutoff = (now || Date.now()) - 7 * 86400000;
  const auto = (log || []).filter((e) => e.source === "auto" && !e.undone_at && Date.parse(e.applied_at) >= cutoff);
  if (!auto.length) return "";
  return `<div class="section-note" role="status">${auto.length} number${auto.length === 1 ? " was" : "s were"} updated automatically from the import in the last 7 days (see the change log). ` +
    '<button class="btn" type="button" onclick="rcUndoAuto()">Undo all automatic updates</button></div>';
}

export function rcPreviewHtml(preview) {
  if (!preview) return "";
  const changes = preview.changes || [];
  const rejected = preview.rejected || [];
  const planInput = changes.some((c) => String(c.kind || "").startsWith("plan:"));
  const rows = changes.map((c) => `<tr><td>${esc(c.label)}</td><td class="rc-num">${esc(c.old === "" ? "blank" : c.old)}</td><td class="rc-num">${esc(c.new)}</td>` +
    `<td class="rc-num">${esc(rcMoney(c.app_value))} → ${esc(rcMoney(c.monarch_value))}</td></tr>`).join("");
  return `<div class="rc-preview" role="dialog" aria-label="Preview update from import"><h3>Update ${changes.length} number${changes.length === 1 ? "" : "s"} from the import</h3>` +
    (changes.length ? `<div class="rc-scroll"><table class="rc-table"><thead><tr><th>Account</th><th class="rc-num">Stored now</th><th class="rc-num">Will store</th><th class="rc-num">App → Imported</th></tr></thead><tbody>${rows}</tbody></table></div>` : '<div class="section-note">Nothing to update.</div>') +
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
    `<option value="ignore">Ignore this imported account</option>` +
    targets.map((t) => `<option value="${esc(t.id)}"${t.id === sel ? " selected" : ""}>${esc(t.label)}${t.role ? " (" + esc(t.role) + ")" : ""}</option>`).join("");
  return `<h3>Imported accounts with no match in the app</h3><div class="rc-scroll"><table class="rc-table"><thead><tr><th>Imported account</th><th class="rc-num">Balance</th><th>Match it to</th></tr></thead><tbody>` +
    items.map((u) => `<tr><td>${esc(u.label)}${u.closed ? ' <span class="rc-sub">(closed)</span>' : ""}</td><td class="rc-num">${esc(rcMoney(u.monarch_value))}</td>` +
      `<td><select data-key="${esc(u.account_key)}" aria-label="Match ${esc(u.label)} to" onchange="rcMap(this.dataset.key, this.value)">${opts("")}</select></td></tr>`).join("") +
    "</tbody></table></div>";
}

export function rcIgnoredHtml(data) {
  const items = data.ignored_accounts || [];
  if (!items.length) return "";
  return `<details class="rc-ignored"><summary>Ignored imported accounts (${items.length})</summary><ul>` +
    items.map((u) => `<li>${esc(u.label)} <button class="btn" type="button" data-key="${esc(u.account_key)}" onclick="rcMap(this.dataset.key, '')">Stop ignoring</button></li>`).join("") +
    "</ul></details>";
}

export function rcLogHtml(log) {
  if (!log || !log.length) return '<div class="section-note">No updates from the import yet.</div>';
  return '<div class="rc-scroll"><table class="rc-table"><thead><tr><th>When</th><th>Account</th><th>By</th><th class="rc-num">Old</th><th class="rc-num">New</th><th>Import date</th><th></th></tr></thead><tbody>' +
    log.map((e) => `<tr><td>${esc(String(e.applied_at || "").replace("T", " ").replace("+00:00", " UTC"))}</td><td>${esc(e.label)}</td><td>${e.source === "auto" ? "automatic" : "you"}</td>` +
      `<td class="rc-num">${esc(e.old_value === "" ? "blank" : e.old_value)}</td><td class="rc-num">${esc(e.new_value)}</td><td>${esc(e.monarch_date)}</td>` +
      `<td>${e.undone_at ? '<span class="rc-sub">undone</span>' : `<button class="btn" type="button" data-id="${esc(String(e.id))}" onclick="rcUndo(this.dataset.id)">Undo</button>`}</td></tr>`).join("") +
    "</tbody></table></div>";
}

export function rcImportNote(data) {
  const last = data.import, ok = data.last_ok_import;
  if (last && last.status !== "ok") {
    return `The latest Imported balances import was rejected (${esc(last.detail || "unknown reason")}); these figures are from ${esc(ok && ok.latest_date ? ok.latest_date : "an earlier import")}.`;
  }
  return "";
}

export function rcBodyHtml(state) {
  const { data, loading, error, message, selected, preview, showMatched, tolerance, log, tab, dismissed } = state;
  if (error) return `<div class="section-note rc-warn">${esc(error)} <button class="btn" type="button" onclick="loadMonarchReconciliation()">Retry</button></div>`;
  if (!data) return `<div class="section-note">${loading ? "Loading the comparison…" : "Nothing loaded yet."}</div>`;
  if (!data.has_balances) {
    return '<div class="section-note">No account balances have been imported into this plan yet. They arrive with the daily account balance import (another process writes balances.csv to the source folder, then the scheduled job loads it).</div>';
  }
  const s = rcSummary(data.rows, data.unmatched);
  const inbox = rcInboxItems(data, dismissed);
  const need = inbox.diffs.length + inbox.unmatched.length;
  const dates = (data.dates || []).map((d) => `<option value="${esc(d)}"${d === data.as_of ? " selected" : ""}>${esc(d)}${d === data.latest ? " (latest)" : ""}</option>`).join("");
  const note = rcImportNote(data);
  const nSel = [...selected].filter((id) => data.rows.some((r) => r.id === id && r.updatable)).length;
  const tabBtn = (id, label) => `<button class="btn${tab === id ? " good" : ""}" type="button" role="tab" aria-selected="${tab === id}" onclick="rcSetTab('${id}')">${label}</button>`;
  const controls = `<div class="rc-controls"><label>Compare as of <select id="rcAsOf" onchange="rcSetAsOf(this.value)">${dates}</select></label> ` +
    `<label>Count as matching within <select onchange="rcSetTolerance(this.value)">${[1, 10, 100].map((t) => `<option value="${t}"${t === tolerance ? " selected" : ""}>$${t}</option>`).join("")}</select></label></div>`;
  const head = (message ? `<div class="section-note${message.error ? " rc-warn" : ""}" role="status">${esc(message.text)}</div>` : "") +
    (note ? `<div class="section-note rc-warn" role="alert">${note}</div>` : "") + rcAutoBannerHtml(log) +
    `<div class="rc-tabs" role="tablist">${tabBtn("inbox", `Needs a decision (${need})`)} ${tabBtn("all", "All mappings")}</div>` + controls +
    rcPreviewHtml(preview);
  if (tab === "inbox") return head + rcInboxHtml(data, dismissed);
  return head +
    `<label><input type="checkbox" onchange="rcSetShowMatched(this.checked)"${showMatched ? " checked" : ""}> Show matching accounts (${s.match})</label>` +
    `<div class="rc-summary"><strong>${s.differs}</strong> differ · <strong>${s.match}</strong> match · <strong>${s.reportOnly}</strong> report only · ` +
    `<strong>${s.notInMonarch}</strong> not in the import · <strong>${s.notInApp}</strong> Imported accounts not in the app</div>` +
    `<div class="pane-actions"><button class="btn good" type="button" onclick="rcPreview()"${nSel ? "" : " disabled"}>Preview update from import (${nSel} selected)</button> ` +
    `<label class="btn">Import mapping CSV<input type="file" accept=".csv,text/csv" hidden onchange="rcImportCsv(this.files[0])"></label></div>` +
    rcGroupsHtml(data, selected, showMatched) + rcUnmatchedHtml(data) + rcParkedHtml(data) + rcClosedHtml(data) + rcIgnoredHtml(data) +
    `<h3>Change log</h3>${rcLogHtml(log)}`;
}

// ── page ─────────────────────────────────────────────────────────────────────────────────────
function rcState() {
  return { data: rcData, loading: rcLoading, error: rcError, message: rcMessage, selected: rcSelected,
    preview: rcPreviewData, showMatched: rcShowMatched, tolerance: rcTolerance, log: rcLog, tab: rcTab, dismissed: rcDismissed };
}

export function renderMonarchReconciliation() {
  const stale = rcData === null || Date.now() - rcLoadedAt > RC_STALE_MS;
  if (stale && !rcLoading && !rcError) setTimeout(loadMonarchReconciliation, 0);
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
  rcLoadedAt = Date.now();
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
    rcMessage = { text: n ? `Updated ${n} number${n === 1 ? "" : "s"} from the import. Rebuild to see them in results.` : "Nothing was changed.", error: !n };
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

export function rcSetTab(t) { rcTab = t === "all" ? "all" : "inbox"; rcPaint(); }

export async function rcSetPolicy(keys, policy) {
  try {
    for (const k of String(keys).split("\u001f")) {
      await api("/api/reconcile/policy", { method: "POST", body: JSON.stringify({ account_key: k, policy }) });
    }
    rcMessage = { text: "Saved: " + (RC_POLICIES.find((p) => p[0] === policy) || [0, policy])[1] + ".", error: false };
  } catch (e) {
    rcMessage = { text: "Could not save the policy: " + e.message, error: true };
  }
  await loadMonarchReconciliation();
}

// Inbox buttons. Update app and Always update both preview first: nothing is written without the confirm.
export async function rcDecide(action, id) {
  const row = rcData && rcData.rows.find((r) => r.id === id);
  if (!row) return;
  if (action === "ignore") { rcDismissed.add(rcDismissKey(row)); rcSaveDismissed(); rcPaint(); return; }
  const keys = (row.monarch_accounts || []).map((a) => a.account_key).join("\u001f");
  if (action === "app") { await rcSetPolicy(keys, "app"); return; }
  if (action === "always") {
    try {
      for (const k of keys.split("\u001f")) await api("/api/reconcile/policy", { method: "POST", body: JSON.stringify({ account_key: k, policy: "auto" }) });
    } catch (e) {
      rcMessage = { text: "Could not save the policy: " + e.message, error: true };
      rcPaint();
      return;
    }
  }
  rcSelected = new Set([id]);
  await rcPreview();
}

export function rcRestoreDismissed() { rcDismissed.clear(); rcSaveDismissed(); rcPaint(); }

export async function rcUndoAuto() {
  try {
    const out = await api("/api/reconcile/undo-auto", { method: "POST", body: "{}" });
    rcMessage = { text: `Undid ${(out.undone || []).length} automatic update(s).` + ((out.skipped || []).length ? " Left alone (edited since): " + out.skipped.map((x) => x.label).join(", ") : ""), error: false };
    if ((out.undone || []).length && typeof markBuildStale === "function") markBuildStale();
  } catch (e) {
    rcMessage = { text: e.message, error: true };
  }
  await loadMonarchReconciliation();
}

export async function rcImportCsv(file) {
  if (!file) return;
  try {
    const out = await api("/api/reconcile/seed", { method: "POST", body: JSON.stringify({ csv_text: await file.text() }) });
    const r = out.seed;
    rcMessage = { text: `Mapping imported: ${r.saved.length} matched, ${r.pending.length} resolved by name or waiting, ${r.ignored.length} ignored, ${r.not_in_monarch.length} not found in the import, ${r.kept.length} already matched (left as they are).`, error: false };
  } catch (e) {
    rcMessage = { text: "Could not import the mapping: " + e.message, error: true };
  }
  await loadMonarchReconciliation();
}

export function rcUnmatch(accountKey, auto) {
  return rcMap(accountKey, auto ? "ignore" : "");
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
  rcRestoreDismissed, rcMoney, rcDiffHtml, rcSummary, rcRowHtml, rcGroupsHtml, rcPreviewHtml, rcUnmatchedHtml, rcLogHtml, rcImportNote, rcBodyHtml,
  renderMonarchReconciliation, loadMonarchReconciliation, rcToggle, rcSelectGroup, rcSetAsOf, rcSetTolerance, rcSetShowMatched,
  rcPreviewCancel, rcPreview, rcApply, rcUndo, rcMap, rcUnmatch, rcIgnoredHtml,
  rcPolicyHtml, rcParkedHtml, rcInboxItems, rcInboxRowHtml, rcInboxHtml, rcClosedHtml, rcAutoBannerHtml,
  rcSetTab, rcSetPolicy, rcDecide, rcUndoAuto, rcImportCsv,
});
