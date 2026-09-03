// ── Local backups (Settings → System Configuration → Local backups card) ────
// Opt-in .rpx database backup status, policy controls, and manual/automatic
// trigger points. Extracted from dashboard.js verbatim (first modularization
// increment).
//
// system_review 2026-08-31 item 3.11: converted to type="module". Wave 6.4
// had deliberately kept this classic because dashboard.js's own synchronous
// top-level boot chain (checkAppStatus(true).then(...)) calls
// refreshLocalBackupStatus() -- a deferred module would have executed it
// AFTER dashboard.js's classic-script code instead of before, reversing the
// load-order guarantee test_dashboard_startup_race_and_script_order.py
// exists to protect (a real 2026-07-22 outage where this exact function was
// undefined when the boot chain called it).
//
// That boot chain now reaches this file through a dynamic import
// (`await import('./dashboard_decomp_local_backups.js')`) instead of a bare
// global reference -- see dashboard.js, right before the
// refreshLocalBackupStatus(true) call. Dynamic import resolves the module's
// module-record from the cache (already fetched via the <script
// type="module"> tag below; re-importing the same specifier does not
// re-run this file's top-level code) and only then proceeds, which is
// correct regardless of script-tag order, unlike relying on "classic always
// beats module" or "document order among modules" positioning. Every other
// caller (the onclick handlers in this file's own HTML, and
// localBackupControlsHtml()/maybeRunLocalBackup() called from
// dashboard_decomp_checklist_closeout.js / dashboard_decomp_row_model.js)
// still reaches these functions as bare globals via the window bridge below
// -- those call sites all run from later event handlers/rendering, well
// after every module has finished evaluating, so they don't need the
// dynamic-import treatment the boot chain does.
let localBackupStatus = null;
function localBackupStatusLine() {
  const s = localBackupStatus || {};
  const p = s.policy || {};
  if (!p.enabled) return "Off — backups run only when enabled here.";
  const latest =
    s.latest_backup && s.latest_backup.created_at
      ? String(s.latest_backup.created_at)
          .replace("T", " ")
          .replace("Z", " UTC")
      : "none yet";
  return `${p.cadence === "per_build" ? "Per build" : "Daily"}; keep ${Number(p.retention_count || 7)} backup${Number(p.retention_count || 7) === 1 ? "" : "s"}; latest: ${latest}.`;
}
function localBackupControlsHtml() {
  const s = localBackupStatus || {};
  const p = Object.assign(
    { enabled: false, cadence: "daily", retention_count: 7 },
    s.policy || {},
  );
  return `<div class="feature-card local-backup-card" tabindex="0" onclick="showConfigCardHelp('local_backups')" onfocus="showConfigCardHelp('local_backups')"><h3>Local backups</h3><p class="small">Opt-in .rpx database backups with automatic retention. Runs opportunistically after Save Changes or successful builds; no background service is started.</p><label class="small"><input type="checkbox" id="localBackupEnabled" ${p.enabled ? "checked" : ""}> Enable automatic backups</label><div class="table-actions"><label class="small">Cadence <select id="localBackupCadence"><option value="daily" ${p.cadence === "daily" ? "selected" : ""}>Daily</option><option value="per_build" ${p.cadence === "per_build" ? "selected" : ""}>Every build</option></select></label><label class="small">Keep <input id="localBackupRetention" type="number" min="1" max="60" value="${Number(p.retention_count || 7)}" style="width:72px"> backups</label></div><p class="small"><b>Status:</b> ${esc(localBackupStatusLine())}</p><div class="table-actions"><button class="btn" type="button" onclick="event.stopPropagation();saveLocalBackupPolicy()" onfocus="event.stopPropagation();showConfigCardHelp('local_backups')">Save backup setting</button><button class="btn" type="button" onclick="event.stopPropagation();runLocalBackupNow()" onfocus="event.stopPropagation();showConfigCardHelp('local_backups')">Back up now</button><button class="btn" type="button" onclick="event.stopPropagation();refreshLocalBackupStatus()" onfocus="event.stopPropagation();showConfigCardHelp('local_backups')">Refresh</button></div></div>`;
}
async function refreshLocalBackupStatus(silent = false) {
  try {
    localBackupStatus = await api("/api/plan/backups");
    if (!silent) showMessage("Backup status refreshed.", "success");
    if (activeStep === "system_configuration") renderMain();
    return localBackupStatus;
  } catch (e) {
    if (!silent)
      showMessage(
        "Backup status unavailable: " + (e && e.message ? e.message : e),
        "error",
      );
    return null;
  }
}
async function saveLocalBackupPolicy() {
  try {
    const enabled = !!(document.getElementById("localBackupEnabled") || {})
      .checked;
    const cadence =
      (document.getElementById("localBackupCadence") || {}).value || "daily";
    const retention =
      Number((document.getElementById("localBackupRetention") || {}).value) ||
      7;
    localBackupStatus = await api("/api/plan/backups/config", {
      method: "POST",
      body: JSON.stringify({ enabled, cadence, retention_count: retention }),
    });
    showMessage(
      enabled
        ? "Automatic local backups enabled."
        : "Automatic local backups disabled.",
      "success",
    );
    renderMain();
  } catch (e) {
    showMessage(
      "Could not save backup setting: " + (e && e.message ? e.message : e),
      "error",
    );
  }
}
async function runLocalBackupNow() {
  try {
    const out = await api("/api/plan/backups/run", {
      method: "POST",
      body: JSON.stringify({ trigger: "manual", force: true }),
    });
    localBackupStatus = out;
    if (out.created) {
      const name = (out.backup && out.backup.filename) || "backup";
      showMessage("Local backup created: " + name, "success");
    } else {
      showMessage(
        "Backup skipped: " + (out.skip_reason || out.due_reason || "not due"),
        "warn",
      );
    }
    if (activeStep === "system_configuration") renderMain();
  } catch (e) {
    showMessage(
      "Local backup failed: " + (e && e.message ? e.message : e),
      "error",
    );
  }
}
async function maybeRunLocalBackup(trigger) {
  try {
    const s = await api("/api/plan/backups");
    localBackupStatus = s;
    if (!(s && s.policy && s.policy.enabled && s.due)) return false;
    const out = await api("/api/plan/backups/run", {
      method: "POST",
      body: JSON.stringify({ trigger: trigger || "save", force: false }),
    });
    localBackupStatus = out;
    if (out && out.created) {
      showMessage("Automatic local backup created.", "success");
      if (activeStep === "system_configuration") renderMain();
      return true;
    }
  } catch (_e) {}
  return false;
}
// Bare-global bridge (see this file's header comment): onclick handlers in
// this file's own generated HTML and cross-module callers
// (dashboard_decomp_checklist_closeout.js's localBackupControlsHtml(),
// dashboard_decomp_row_model.js's maybeRunLocalBackup()) all reach these as
// plain identifiers, not window.-prefixed.
Object.assign(window, {
  localBackupStatusLine,
  localBackupControlsHtml,
  refreshLocalBackupStatus,
  saveLocalBackupPolicy,
  runLocalBackupNow,
  maybeRunLocalBackup,
});
