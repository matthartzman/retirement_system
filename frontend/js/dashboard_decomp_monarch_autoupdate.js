// ── Monarch auto-update (Settings → System Configuration → Monarch auto-update card) ──
// Ticket 305: opt-in daily transaction import from the Monarch Extractor's
// output folder, upserted by Monarch id. The actual 4am trigger is an
// OS-level Windows Task Scheduler entry (this toggle keeps that entry in
// sync via the server, which shells out to a PowerShell helper) -- this
// card only shows status and lets the user enable/disable or run it now.
// Mirrors dashboard_decomp_local_backups.js's structure, including its
// conversion to type="module" (system_review 2026-08-31 item 3.11) -- see
// that file's header comment for the full reasoning (dashboard.js's boot
// chain now reaches refreshMonarchAutoUpdateStatus() via a dynamic import
// instead of a bare global reference, for the same load-order reason).
let monarchAutoUpdateStatus = null;
// Finding UX-103 (system review 2026-09-07, Wave 5 item W5-8): this card
// used a manual "Save setting" button in an otherwise-autosaving app, with
// no dirty/busy indicator, and "Import now" gave no feedback while running.
let monarchAutoUpdateSaving = false;
let monarchAutoUpdateRunning = false;
// The value the in-flight save actually sent, captured from the DOM before
// the busy-state render below fires -- without this, that render rebuilds
// the checkbox/input from the still-stale pre-save monarchAutoUpdateStatus,
// visibly snapping the control back to its old value (while disabled) the
// instant a user toggles it, even though the save proceeds correctly.
let monarchAutoUpdatePendingPolicy = null;
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
// 2026-09 outage: the import job above reports success every day even when
// the extractor (the thing that actually fetches new transactions from
// Monarch) has been silently dead for weeks -- "nothing new to import"
// and "nothing is producing anything to import" render identically in
// monarchAutoUpdateStatusLine() alone. This surfaces the extractor's own
// last-run freshness (src/monarch_autoupdate.py's get_extractor_freshness)
// so that gap is visible without checking file timestamps by hand.
function monarchAutoUpdateFreshnessWarningHtml() {
  const s = monarchAutoUpdateStatus || {};
  const p = s.policy || {};
  const freshness = s.extractor_freshness;
  if (!p.enabled || !freshness || !freshness.stale) return "";
  const detail = freshness.last_extract_at
    ? `last successful extraction was ${String(freshness.last_extract_at).replace("T", " ").replace("Z", " UTC")} (${freshness.age_hours}h ago)`
    : "no extraction has ever run";
  return `<p class="small" style="color:var(--warn)"><b>Warning:</b> the Monarch Extractor itself looks stalled — ${esc(detail)}, past the ${Number(freshness.stale_after_hours)}h freshness threshold. The import above can keep reporting success with nothing new to consume. Check that the "RetirementSystem_MonarchExtract" scheduled task is registered and running.</p>`;
}
function monarchAutoUpdateControlsHtml() {
  const s = monarchAutoUpdateStatus || {};
  const p = Object.assign(
    { enabled: false, source_dir: "Monarch Extractor/output" },
    s.policy || {},
    monarchAutoUpdateSaving ? monarchAutoUpdatePendingPolicy || {} : {},
  );
  const busy = monarchAutoUpdateSaving || monarchAutoUpdateRunning;
  const disabledAttr = busy ? " disabled" : "";
  const statusSuffix = monarchAutoUpdateSaving
    ? ' <span class="small" style="color:var(--muted)">Saving…</span>'
    : "";
  const runLabel = monarchAutoUpdateRunning ? "Importing…" : "Import now";
  return `<div class="feature-card monarch-autoupdate-card" tabindex="0" onclick="showConfigCardHelp('monarch_autoupdate')" onfocus="showConfigCardHelp('monarch_autoupdate')"><h3>Monarch auto-update</h3><p class="small">Import new and changed transactions from the Monarch Extractor's output folder automatically every day at 4am, matched and merged by Monarch id. Requires Windows Task Scheduler entries (registered automatically when enabled).</p><label class="small"><input type="checkbox" id="monarchAutoUpdateEnabled" ${p.enabled ? "checked" : ""}${disabledAttr} onchange="event.stopPropagation();saveMonarchAutoUpdatePolicy()"> Enable daily auto-update (4am)</label><div class="table-actions"><label class="small">Source folder <input id="monarchAutoUpdateSourceDir" type="text" value="${esc(p.source_dir || "")}"${disabledAttr} onblur="event.stopPropagation();saveMonarchAutoUpdatePolicy()" style="width:260px"></label></div><p class="small"><b>Status:</b> ${esc(monarchAutoUpdateStatusLine())}${statusSuffix}</p>${monarchAutoUpdateFreshnessWarningHtml()}<div class="table-actions"><button class="btn" type="button"${monarchAutoUpdateRunning ? " disabled" : ""} onclick="event.stopPropagation();runMonarchAutoUpdateNow()" onfocus="event.stopPropagation();showConfigCardHelp('monarch_autoupdate')">${runLabel}</button><button class="btn" type="button" onclick="event.stopPropagation();refreshMonarchAutoUpdateStatus()" onfocus="event.stopPropagation();showConfigCardHelp('monarch_autoupdate')">Refresh</button></div></div>`;
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
  const enabled = !!(document.getElementById("monarchAutoUpdateEnabled") || {}).checked;
  const sourceDir = (document.getElementById("monarchAutoUpdateSourceDir") || {}).value || "";
  monarchAutoUpdatePendingPolicy = { enabled, source_dir: sourceDir };
  monarchAutoUpdateSaving = true;
  renderMain();
  try {
    const out = await api("/api/plan/monarch-autoupdate/config", {
      method: "POST",
      body: JSON.stringify({ enabled, source_dir: sourceDir }),
    });
    monarchAutoUpdateStatus = out;
    const reg = out.task_registration;
    if (enabled && reg && reg.attempted && !reg.success) {
      showMessage(
        "Auto-update enabled, but one or more scheduled tasks could not be registered: " +
          (reg.error || "unknown error") +
          ". Run tools/launchers/register_monarch_autoimport_task.ps1 and Monarch Extractor/register_monarch_extract_task.ps1 manually.",
        "warn",
      );
    } else {
      showMessage(enabled ? "Monarch auto-update enabled." : "Monarch auto-update disabled.", "success");
    }
  } catch (e) {
    showMessage(
      "Could not save Monarch auto-update setting: " + (e && e.message ? e.message : e),
      "error",
    );
  } finally {
    monarchAutoUpdateSaving = false;
    monarchAutoUpdatePendingPolicy = null;
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
    monarchAutoUpdateStatus = {
      policy: (monarchAutoUpdateStatus || {}).policy,
      status: out.status,
      extractor_freshness: (monarchAutoUpdateStatus || {}).extractor_freshness,
    };
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
  } catch (e) {
    showMessage(
      "Monarch import failed: " + (e && e.message ? e.message : e),
      "error",
    );
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
  monarchAutoUpdateFreshnessWarningHtml,
  monarchAutoUpdateControlsHtml,
  refreshMonarchAutoUpdateStatus,
  saveMonarchAutoUpdatePolicy,
  runMonarchAutoUpdateNow,
});
