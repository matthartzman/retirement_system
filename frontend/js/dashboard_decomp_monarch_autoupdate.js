// ── Monarch auto-update (Settings → System Configuration → Monarch auto-update card) ──
// Ticket 305: opt-in daily transaction import from the Monarch Extractor's
// output folder, upserted by Monarch id. The actual 4am trigger is an
// OS-level Windows Task Scheduler entry (this toggle keeps that entry in
// sync via the server, which shells out to a PowerShell helper) -- this
// card only shows status and lets the user enable/disable or run it now.
// Mirrors dashboard_decomp_local_backups.js's structure; stays a classic
// script for the same reason that module does (see its own header comment).
let monarchAutoUpdateStatus = null;
function monarchAutoUpdateStatusLine() {
  const s = monarchAutoUpdateStatus || {};
  const p = s.policy || {};
  const last = s.status || {};
  if (!p.enabled) return "Off — the daily 4am import only runs when enabled here.";
  if (!last.last_run_at) return "Enabled; no run yet.";
  const when = String(last.last_run_at).replace("T", " ").replace("Z", " UTC");
  const outcome = last.success
    ? `${Number(last.rows_added || 0)} added, ${Number(last.rows_updated || 0)} updated, ${Number(last.rows_skipped || 0)} skipped`
    : "failed — " + (Array.isArray(last.errors) && last.errors.length ? last.errors[0] : "see status");
  return `Last run ${when}: ${outcome}.`;
}
function monarchAutoUpdateControlsHtml() {
  const s = monarchAutoUpdateStatus || {};
  const p = Object.assign({ enabled: false, source_dir: "../Monarch Extractor/output" }, s.policy || {});
  return `<div class="feature-card monarch-autoupdate-card" tabindex="0" onclick="showConfigCardHelp('monarch_autoupdate')" onfocus="showConfigCardHelp('monarch_autoupdate')"><h3>Monarch auto-update</h3><p class="small">Import new and changed transactions from the Monarch Extractor's output folder automatically every day at 4am, matched and merged by Monarch id. Requires a Windows Task Scheduler entry (registered automatically when enabled).</p><label class="small"><input type="checkbox" id="monarchAutoUpdateEnabled" ${p.enabled ? "checked" : ""}> Enable daily auto-update (4am)</label><div class="table-actions"><label class="small">Source folder <input id="monarchAutoUpdateSourceDir" type="text" value="${esc(p.source_dir || "")}" style="width:260px"></label></div><p class="small"><b>Status:</b> ${esc(monarchAutoUpdateStatusLine())}</p><div class="table-actions"><button class="btn" type="button" onclick="event.stopPropagation();saveMonarchAutoUpdatePolicy()" onfocus="event.stopPropagation();showConfigCardHelp('monarch_autoupdate')">Save setting</button><button class="btn" type="button" onclick="event.stopPropagation();runMonarchAutoUpdateNow()" onfocus="event.stopPropagation();showConfigCardHelp('monarch_autoupdate')">Import now</button><button class="btn" type="button" onclick="event.stopPropagation();refreshMonarchAutoUpdateStatus()" onfocus="event.stopPropagation();showConfigCardHelp('monarch_autoupdate')">Refresh</button></div></div>`;
}
async function refreshMonarchAutoUpdateStatus(silent = false) {
  try {
    monarchAutoUpdateStatus = await api("/api/plan/monarch-autoupdate");
    if (!silent) showMessage("Monarch auto-update status refreshed.", "success");
    if (activeStep === "system_configuration") renderMain();
    return monarchAutoUpdateStatus;
  } catch (e) {
    if (!silent)
      showMessage(
        "Monarch auto-update status unavailable: " + (e && e.message ? e.message : e),
        "error",
      );
    return null;
  }
}
async function saveMonarchAutoUpdatePolicy() {
  try {
    const enabled = !!(document.getElementById("monarchAutoUpdateEnabled") || {}).checked;
    const sourceDir = (document.getElementById("monarchAutoUpdateSourceDir") || {}).value || "";
    const out = await api("/api/plan/monarch-autoupdate/config", {
      method: "POST",
      body: JSON.stringify({ enabled, source_dir: sourceDir }),
    });
    monarchAutoUpdateStatus = out;
    const reg = out.task_registration;
    if (enabled && reg && reg.attempted && !reg.success) {
      showMessage(
        "Auto-update enabled, but the scheduled task could not be registered: " +
          (reg.error || "unknown error") +
          ". Run tools/launchers/register_monarch_autoimport_task.ps1 manually.",
        "warn",
      );
    } else {
      showMessage(enabled ? "Monarch auto-update enabled." : "Monarch auto-update disabled.", "success");
    }
    renderMain();
  } catch (e) {
    showMessage(
      "Could not save Monarch auto-update setting: " + (e && e.message ? e.message : e),
      "error",
    );
  }
}
async function runMonarchAutoUpdateNow() {
  try {
    const out = await api("/api/plan/monarch-autoupdate/run", {
      method: "POST",
      body: JSON.stringify({ force: true }),
    });
    monarchAutoUpdateStatus = { policy: (monarchAutoUpdateStatus || {}).policy, status: out.status };
    if (out.skipped) {
      showMessage("Monarch import: " + (out.skip_reason || "nothing to do") + ".", "warn");
    } else if (out.success) {
      const u = out.upsert || {};
      showMessage(
        `Monarch import complete: ${Number(u.added || 0)} added, ${Number(u.updated || 0)} updated.`,
        "success",
      );
    } else {
      showMessage("Monarch import failed — see status for details.", "error");
    }
    if (activeStep === "system_configuration") renderMain();
  } catch (e) {
    showMessage(
      "Monarch import failed: " + (e && e.message ? e.message : e),
      "error",
    );
  }
}
