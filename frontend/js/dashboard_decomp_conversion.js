// First-launch conversion (WP10.4, design F P8.4): a notice under the header while an old install
// needs the one-time conversion, a check (dry run), progress, the verified result and, when a
// check blocked it, the differing key NAMES with the choices the 10.3 safeguard allows. Nothing
// converts by itself. Helpers are bare globals; loadAll() calls refreshConversionNotice().
let conversionState = null;
let conversionBusy = false;
let conversionDismissed = false;
let conversionPoll = null;

const REASONS = {
  verification_differences: "The converted plan does not match the old one in the checks listed below.",
  tier_mapping_changes_results: "Fitting your features to a tier would change your results.",
  verification_error: "The numbers could not be compared because the engine reported an error.",
  step_failed: "A conversion step failed.",
  backup_failed: "The backup could not be made or verified, so nothing was changed.",
  sources_modified: "An original file changed while converting, so nothing was changed.",
  sources_unreadable: "An original file could not be read.",
  plan_changed_during_conversion: "Your plan changed while converting. Try again.",
  plan_backup_failed: "The copy of your current plan could not be made.",
  swap_failed: "The converted plan could not be put in place.",
  busy: "A conversion is already running.",
  internal_error: "The conversion stopped unexpectedly.",
};
const ACCEPTABLE = ["verification_differences", "tier_mapping_changes_results", "verification_error"];

function listHtml(names, cap) {
  const shown = (names || []).slice(0, cap || 8).map((n) => `<code>${esc(n)}</code>`).join(", ");
  const more = (names || []).length > (cap || 8) ? ` and ${(names || []).length - (cap || 8)} more` : "";
  return shown + more;
}

function checksHtml(res) {
  const bad = (res.checks || []).filter((c) => c.status === "diff" || c.status === "error");
  if (!bad.length) return "";
  const items = bad
    .map((c) => `<li><strong>${esc(c.name)}</strong>: ${c.differing || 0} differing${c.names && c.names.length ? " (" + listHtml(c.names) + ")" : ""}</li>`)
    .join("");
  return `<ul class="small">${items}</ul>`;
}

export function conversionNoticeHtml(state, busy) {
  const s = state || {};
  const res = s.last_result;
  const running = busy || s.running;
  const btn = (label, cls, onclick) => `<button class="btn tiny ${cls || ""}" type="button" onclick="${onclick}">${esc(label)}</button>`;
  const opts =
    '<div class="small"><label><input type="checkbox" id="convBackupSecrets"> Also back up the old keys file (<code>secrets.local.json</code>)</label><br>' +
    '<label><input type="checkbox" id="convDeleteSecrets"> Delete the old keys file once the keys are safely in the credential store</label></div>';
  if (running) {
    return '<div class="conversion-notice" role="status"><strong>Converting your plan…</strong> Backing up, converting and checking the numbers. This takes about ten seconds. Your original files are not changed.</div>';
  }
  if (conversionDismissed && (!res || res.status === "done")) return "";
  if (res && res.status === "done") {
    const removable = res.removable && Object.keys(res.removable).length
      ? `<div class="small">Safe to remove after 30 days: ${listHtml(Object.keys(res.removable))}. The app never deletes them.</div>` : "";
    const warn = (res.warnings || []).length ? `<div class="small">Notes: ${listHtml(res.warnings)}</div>` : "";
    return `<div class="conversion-notice" role="status"><strong>Your plan was converted and checked.</strong> The numbers match the old version. Your original files were backed up${res.backup && res.backup.name ? " (<code>" + esc(res.backup.name) + "</code>)" : ""} and left in place.${removable}${warn} ${btn("Dismiss", "", "dismissConversionNotice()")}</div>`;
  }
  if (res && res.status === "dry_run" && !res.blocked_reason) {
    return `<div class="conversion-notice" role="status"><strong>Check passed.</strong> Converting would not change your numbers. Nothing was written. ${btn("Convert now", "primary", "runConversion()")}${opts}</div>`;
  }
  if (res && (res.status === "blocked" || res.status === "dry_run" || res.status === "failed")) {
    const why = REASONS[res.blocked_reason] || "The conversion did not finish.";
    const acceptable = ACCEPTABLE.includes(res.blocked_reason);
    const keep = res.blocked_reason === "tier_mapping_changes_results"
      ? btn("Keep my switches and convert", "primary", "runConversion({tier_mapping:'keep'})") : "";
    const any = acceptable ? btn("Convert anyway", "", "runConversion({accept_differences:true})") : "";
    return `<div class="conversion-notice conversion-blocked" role="alert"><strong>Nothing was changed.</strong> ${esc(why)}${checksHtml(res)}<div class="small">Your plan and original files are exactly as they were.</div>${keep}${any}${btn("Check again", "", "checkConversion()")}</div>`;
  }
  if (s.needed && !conversionDismissed) {
    const what = s.mode === "mid_demo"
      ? "Your own plan was set aside while the demo was open. It will be restored."
      : "Your plan is stored in the old file format.";
    return `<div class="conversion-notice" role="status"><strong>One-time update.</strong> ${esc(what)} The app backs up your original files first, converts into a new plan file, and checks that the numbers match before switching over. Originals are never changed or deleted. ${btn("Check first", "", "checkConversion()")}${btn("Convert now", "primary", "runConversion()")}${opts}</div>`;
  }
  return "";
}

export function renderConversionNotice() {
  const host = document.getElementById("conversionNotice");
  if (host) host.innerHTML = conversionNoticeHtml(conversionState, conversionBusy);
}

export async function refreshConversionNotice() {
  try {
    const out = await api("/api/conversion/status");
    conversionState = out && out.success ? out : null;
  } catch (_e) {
    conversionState = null;
  }
  renderConversionNotice();
  return conversionState;
}

function optionsFromBoxes(extra) {
  const on = (id) => !!(document.getElementById(id) || {}).checked;
  const o = Object.assign({}, extra || {});
  if (on("convBackupSecrets")) o.backup_legacy_secrets = true;
  if (on("convDeleteSecrets")) o.delete_legacy_secrets = true;
  return o;
}

async function startConversion(path, extra) {
  if (conversionBusy) return;
  conversionBusy = true;
  renderConversionNotice();
  try {
    const resp = await api(path, { method: "POST", body: JSON.stringify(optionsFromBoxes(extra)) });
    if (!resp || !resp.success) throw new Error((resp && resp.error) || "could not start");
    await waitForConversion();
  } catch (e) {
    showMessage("Conversion: " + e.message, "error");
    conversionBusy = false;
    await refreshConversionNotice();
  }
}

async function waitForConversion() {
  for (;;) {
    await new Promise((r) => (conversionPoll = setTimeout(r, 1000)));
    const st = await refreshConversionNotice();
    if (!st || !st.running) break;
  }
  conversionBusy = false;
  const res = conversionState && conversionState.last_result;
  renderConversionNotice();
  if (res && res.status === "done") {
    await loadAll({ source: "Plan converted", preferLocal: false });
    renderMain();
    if (typeof refreshPlanSwitcher === "function") refreshPlanSwitcher();
  }
}

export function checkConversion() {
  return startConversion("/api/conversion/check", {});
}

export function runConversion(extra) {
  return startConversion("/api/conversion/run", extra || {});
}

export function dismissConversionNotice() {
  conversionDismissed = true;
  if (conversionState) conversionState = Object.assign({}, conversionState, { last_result: null, needed: false });
  renderConversionNotice();
}

Object.assign(window, {
  conversionNoticeHtml,
  renderConversionNotice,
  refreshConversionNotice,
  checkConversion,
  runConversion,
  dismissConversionNotice,
});
