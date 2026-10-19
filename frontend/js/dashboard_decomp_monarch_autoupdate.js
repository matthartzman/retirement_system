// ── Third-party import auto-update (Settings → System Configuration card) ──
// Ticket 305 / item 359: opt-in daily import of transactions and account balances that another
// process drops in a source folder. The daily trigger is a Windows Task Scheduler entry kept in sync
// by the server; this card shows status and lets the user configure it or run it now. A type="module"
// script like dashboard_decomp_local_backups.js (see its header; dashboard.js reaches
// refreshMonarchAutoUpdateStatus() through a dynamic import for the same load-order reason).
let monarchAutoUpdateStatus = null;
// UX-103: autosave with a busy indicator instead of a manual Save button.
let monarchAutoUpdateSaving = false;
let monarchAutoUpdateRunning = false;
// What the in-flight save sent, so the busy-state render does not snap controls back to stale values.
let monarchAutoUpdatePendingPolicy = null;
const aucTime = (iso) => String(iso).replace("T", " ").replace("Z", " UTC");
const aucDefaults = { enabled: true, transactions: true, balances: true };
// Item 359: two independent steps under one daily schedule, one status line each.
function monarchAutoUpdateStatusLine() {
  const s = monarchAutoUpdateStatus || {};
  const p = Object.assign({}, aucDefaults, s.policy || {});
  const last = s.status || {};
  if (!p.enabled) return "Off — the daily import only runs when enabled here.";
  if (!p.transactions) return "Skipped — Transactions is not checked.";
  if (!last.last_run_at) return "Enabled; no run yet.";
  const outcome = last.success
    ? `${Number(last.rows_added || 0)} added, ${Number(last.rows_updated || 0)} updated, ${Number(last.rows_skipped || 0)} skipped`
    : "failed — " + (Array.isArray(last.errors) && last.errors.length ? last.errors[0] : "see status");
  return `Last run ${aucTime(last.last_run_at)}: ${outcome}.`;
}
function monarchAutoUpdateBalancesStatusLine() {
  const s = monarchAutoUpdateStatus || {};
  const p = Object.assign({}, aucDefaults, s.policy || {});
  const last = s.balances_status || null;
  if (!p.enabled) return "Off — the daily import only runs when enabled here.";
  if (!p.balances) return "Skipped — Account balances is not checked.";
  if (!last) return "Enabled; no run yet.";
  return `Last run ${aucTime(last.last_run_at)}: ${last.success ? last.status : "failed"}${last.detail ? " — " + last.detail : ""}.`;
}
// "Nothing new" looks the same as "nothing is being produced": surface the source's freshness.
function monarchAutoUpdateFreshnessWarningHtml() {
  const s = monarchAutoUpdateStatus || {};
  const p = s.policy || {};
  const freshness = s.extractor_freshness;
  if (!p.enabled || !freshness || !freshness.stale) return "";
  const detail = freshness.last_extract_at
    ? `the last delivery was ${aucTime(freshness.last_extract_at)} (${freshness.age_hours}h ago)`
    : "nothing has ever been delivered";
  return `<p class="small" style="color:var(--warn)"><b>Warning:</b> the process that supplies the data looks stalled — ${esc(detail)}, past the ${Number(freshness.stale_after_hours)}h freshness threshold. The import can keep reporting success with nothing new to consume.</p>`;
}
function monarchAutoUpdateControlsHtml() {
  const s = monarchAutoUpdateStatus || {};
  const p = Object.assign(
    { enabled: true, source_dir: "", run_time: "04:00", transactions: true, balances: true },
    s.policy || {},
    monarchAutoUpdateSaving ? monarchAutoUpdatePendingPolicy || {} : {},
  );
  const busy = monarchAutoUpdateSaving || monarchAutoUpdateRunning;
  const disabledAttr = busy ? " disabled" : "";
  const statusSuffix = monarchAutoUpdateSaving ? ' <span class="small" style="color:var(--muted)">Saving…</span>' : "";
  const runLabel = monarchAutoUpdateRunning ? "Importing…" : "Import now";
  const chk = (id, on, label) =>
    `<label class="small"><input type="checkbox" id="${id}" ${on ? "checked" : ""}${disabledAttr} onchange="event.stopPropagation();saveMonarchAutoUpdatePolicy()"> ${label}</label>`;
  const detail = p.enabled
    ? `<div class="table-actions"><label class="small">Run time <input type="time" id="monarchAutoUpdateRunTime" value="${esc(p.run_time || "04:00")}"${disabledAttr} onchange="event.stopPropagation();saveMonarchAutoUpdatePolicy()"></label> ${chk("monarchAutoUpdateTransactions", p.transactions, "Transactions")} ${chk("monarchAutoUpdateBalances", p.balances, "Account balances")}</div><div class="table-actions"><label class="small">Source folder (full path) <input id="monarchAutoUpdateSourceDir" type="text" value="${esc(p.source_dir || "")}"${disabledAttr} onblur="event.stopPropagation();saveMonarchAutoUpdatePolicy()" style="width:360px"></label></div><p class="small"><b>Transactions:</b> ${esc(monarchAutoUpdateStatusLine())}${statusSuffix}</p><p class="small"><b>Account balances:</b> ${esc(monarchAutoUpdateBalancesStatusLine())}</p>${monarchAutoUpdateFreshnessWarningHtml()}`
    : `<p class="small"><b>Status:</b> ${esc(monarchAutoUpdateStatusLine())}${statusSuffix}</p>`;
  return `<div class="feature-card monarch-autoupdate-card" tabindex="0" onclick="showConfigCardHelp('monarch_autoupdate')" onfocus="showConfigCardHelp('monarch_autoupdate')"><h3>Third-party import auto-update</h3><p class="small">Import new and changed transactions and daily account balances that another process places in the source folder. Both steps run under one daily Windows Task Scheduler entry (registered automatically).</p>${chk("monarchAutoUpdateEnabled", p.enabled, "Enable daily auto-update")}${detail}<div class="table-actions"><button class="btn" type="button"${monarchAutoUpdateRunning ? " disabled" : ""} onclick="event.stopPropagation();runMonarchAutoUpdateNow()" onfocus="event.stopPropagation();showConfigCardHelp('monarch_autoupdate')">${runLabel}</button><button class="btn" type="button" onclick="event.stopPropagation();refreshMonarchAutoUpdateStatus()" onfocus="event.stopPropagation();showConfigCardHelp('monarch_autoupdate')">Refresh</button></div></div>`;
}
async function refreshMonarchAutoUpdateStatus(silent = false) {
  try {
    monarchAutoUpdateStatus = await api("/api/plan/monarch-autoupdate");
    if (!silent) showMessage("Auto-update status refreshed.", "success");
    if (activeStep === "system_configuration") renderMain();
    return monarchAutoUpdateStatus;
  } catch (e) {
    if (!silent) showMessage("Auto-update status unavailable: " + (e && e.message ? e.message : e), "error");
    return null;
  }
}
const aucIsAbsolute = (p) => /^([A-Za-z]:[\\/]|\\\\|\/)/.test(String(p || "").trim());
async function saveMonarchAutoUpdatePolicy() {
  const el = (id) => document.getElementById(id);
  const cur = (monarchAutoUpdateStatus || {}).policy || {};
  const enabled = !!(el("monarchAutoUpdateEnabled") || {}).checked;
  // The detail controls only exist while enabled; fall back to the saved values.
  const pick = (id, key, prop, dflt) => (el(id) ? el(id)[prop] : key in cur ? cur[key] : dflt);
  const policy = {
    enabled,
    run_time: pick("monarchAutoUpdateRunTime", "run_time", "value", "04:00") || "04:00",
    transactions: !!pick("monarchAutoUpdateTransactions", "transactions", "checked", true),
    balances: !!pick("monarchAutoUpdateBalances", "balances", "checked", true),
    source_dir: String(pick("monarchAutoUpdateSourceDir", "source_dir", "value", "")).trim(),
  };
  if (policy.source_dir && !aucIsAbsolute(policy.source_dir)) {
    showMessage("Source folder must be a full absolute path, e.g. C:\\Data\\import.", "error");
    return;
  }
  monarchAutoUpdatePendingPolicy = policy; monarchAutoUpdateSaving = true;
  renderMain();
  try {
    const out = await api("/api/plan/monarch-autoupdate/config", {
      method: "POST",
      body: JSON.stringify(policy),
    });
    monarchAutoUpdateStatus = Object.assign({}, monarchAutoUpdateStatus || {}, out);
    const reg = out.task_registration;
    if (enabled && reg && reg.attempted && !reg.success) {
      showMessage(
        "Auto-update saved, but the scheduled task could not be registered: " +
          (reg.error || "unknown error") +
          ". Run tools/launchers/register_monarch_autoimport_task.ps1 manually.",
        "warn",
      );
    } else {
      showMessage(enabled ? `Auto-update enabled, daily at ${policy.run_time}.` : "Auto-update disabled.", "success");
    }
  } catch (e) {
    showMessage("Could not save auto-update setting: " + (e && e.message ? e.message : e), "error");
  } finally {
    monarchAutoUpdateSaving = false; monarchAutoUpdatePendingPolicy = null;
    renderMain();
  }
}
async function runMonarchAutoUpdateNow() {
  monarchAutoUpdateRunning = true;
  renderMain();
  try {
    const out = await api("/api/plan/monarch-autoupdate/run", {
      method: "POST",
      body: JSON.stringify({ force: true }),
    });
    const prev = monarchAutoUpdateStatus || {};
    monarchAutoUpdateStatus = Object.assign({}, prev, { status: out.status || prev.status, balances_status: out.balances_status || prev.balances_status });
    const bal = out.balances;
    const balText = bal ? ` Balances: ${bal.status === "ok" ? Number(bal.rows || 0) + " rows" : bal.status || "no result"}.` : "";
    if (out.skipped) {
      showMessage("Import: " + (out.skip_reason || "nothing to do") + "." + balText, bal && !bal.success ? "error" : "warn");
    } else if (out.success) {
      const u = out.upsert || {};
      showMessage(`Import complete: ${Number(u.added || 0)} transactions added, ${Number(u.updated || 0)} updated.` + balText, "success");
    } else {
      showMessage("Import failed — see status for details.", "error");
    }
  } catch (e) {
    showMessage("Import failed: " + (e && e.message ? e.message : e), "error");
  } finally {
    monarchAutoUpdateRunning = false;
    if (activeStep === "system_configuration") renderMain();
  }
}
// Bare-global bridge (see this file's header comment): onclick handlers in
// this file's own generated HTML and dashboard_decomp_checklist_closeout.js's
// monarchAutoUpdateControlsHtml() call site reach these as plain
// identifiers, not window.-prefixed.
Object.assign(window, {
  monarchAutoUpdateStatusLine,
  monarchAutoUpdateBalancesStatusLine,
  monarchAutoUpdateFreshnessWarningHtml,
  monarchAutoUpdateControlsHtml,
  refreshMonarchAutoUpdateStatus,
  saveMonarchAutoUpdatePolicy,
  runMonarchAutoUpdateNow,
});
