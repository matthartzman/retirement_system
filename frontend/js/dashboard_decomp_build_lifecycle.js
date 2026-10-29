/* Build lifecycle UI: duration estimate, progress overlay, smooth-progress ticker, cancel, and
   post-build snapshot/baseline handling (ES module; extracted from dashboard.js). The shared state
   (buildOverlayStartedAt, buildOverlayDepth, ...) is owned by dashboard.js and read here as
   globals. buildHiddenByUser and activeBuildJobId are the state this file owns. */
import { formatElapsed, recordPopupRuntime, averageRuntimeText } from "./runtime_history.js";

// Run-time history helpers live in runtime_history.js (shared with the Financial Insight app).
let buildOverlayPopupId = "";

export function refreshBuildOverlayTimer() {
  const d = document.getElementById("buildOverlayDetail");
  if (!d || !buildOverlayStartedAt) return;
  d.textContent = `Elapsed ${formatElapsed(Date.now() - buildOverlayStartedAt)}`;
}
export function setBuildOverlay(active, title, detail, pct, popupId) {
  const overlay = document.getElementById("buildOverlay");
  if (!overlay) return;
  if (active) {
    buildOverlayDepth++;
    if (buildOverlayDepth === 1) {
      buildOverlayStartedAt = Date.now();
      buildOverlayPopupId = popupId || title || "";
      if (buildOverlayTimer) clearInterval(buildOverlayTimer);
      buildOverlayTimer = setInterval(refreshBuildOverlayTimer, 1000);
    }
  } else if (buildOverlayTimer) {
    clearInterval(buildOverlayTimer);
    buildOverlayTimer = null;
  }
  // Only a real build can be hidden-and-continued; "Saving changes"/"Loading plan" and the
  // other shared popups have nothing to hide, so they get no button at all.
  if (active && buildOverlayDepth === 1)
    overlay.classList.toggle("no-cancel", String(popupId || "") !== "build");
  overlay.classList.toggle("active", !!active);
  overlay.classList.toggle("done", false);
  overlay.classList.toggle("error", false);
  overlay.setAttribute("aria-hidden", active ? "false" : "true");
  document.body.classList.toggle("is-busy", !!active);
  updateBuildOverlay(title, detail, pct);
}
export function updateBuildOverlay(title, detail, pct, state) {
  const overlay = document.getElementById("buildOverlay");
  if (!overlay) return;
  overlay.classList.remove("waiting");
  if (state) {
    overlay.classList.remove("done", "error");
    overlay.classList.add(state);
  }
  const t = document.getElementById("buildOverlayTitle");
  const b = document.getElementById("buildOverlayBar");
  const p = document.getElementById("buildOverlayPct");
  if (t && title) {
    buildOverlayLastTitle = title;
    t.textContent = title;
  }
  let value = null;
  if (pct === "waiting" || pct === "indeterminate" || pct === null) {
    value = null;
    overlay.classList.add("waiting");
  } else if (Number.isFinite(Number(pct))) {
    value = Math.max(0, Math.min(100, Number(pct)));
  }
  if (value !== null) buildOverlayLastPct = value;
  if (value !== null && _smoothIntervalTimer && value >= _smoothCap)
    stopSmoothProgress();
  if (b && value !== null) {
    b.style.width = value + "%";
    b.style.animation = "none";
  }
  if (p) {
    p.textContent = averageRuntimeText(buildOverlayPopupId) || "Working…";
  }
  refreshBuildOverlayTimer();
}
// UX-002 / WI-019: Hide keeps the build running; it shows a "still running" chip and tells runBuild() not to navigate.
let buildHiddenByUser = false;
let activeBuildJobId = "";
export const setActiveBuildJob = (jobId) => (activeBuildJobId = String(jobId || ""));
export async function cancelActiveBuild() {
  if (!activeBuildJobId) return;
  try {
    const out = await api("/api/build/cancel/" + encodeURIComponent(activeBuildJobId), { method: "POST" });
    if (out && out.outcome === "cancelling") updateBuildOverlay("Cancelling build", "Stopping the build…", "indeterminate");
  } catch (e) {
    showMessage("Could not cancel the build: " + ((e && e.message) || e), "error");
  }
}
export function buildWasHiddenByUser() {
  return buildHiddenByUser;
}
export function resetBuildHidden() {
  buildHiddenByUser = false;
  setBuildRunningChip(false);
}
export function setBuildRunningChip(show) {
  let chip = document.getElementById("buildRunningChip");
  if (!chip && show) {
    chip = document.createElement("div");
    chip.id = "buildRunningChip";
    chip.className = "build-running-chip";
    chip.setAttribute("role", "status");
    chip.innerHTML =
      '<span>Build still running in the background.</span> <button class="btn" type="button" onclick="showBuildProgress()">Show progress</button>';
    document.body.appendChild(chip);
  }
  if (chip) chip.hidden = !show;
}
export function hideBuildInBackground() {
  buildHiddenByUser = true;
  // Close the window outright (whatever the overlay nesting depth) without recording a
  // partial run-time sample; the build itself is untouched.
  buildOverlayStartedAt = 0;
  buildOverlayDepth = 1;
  hideBuildOverlay();
  setAppControls(true);
  setBuildRunningChip(true);
  showMessage(
    "Build is still running in the background. You will be told when it finishes.",
    "info",
    { persistent: true },
  );
}
export function showBuildProgress() {
  buildHiddenByUser = false;
  setBuildRunningChip(false);
  setBuildOverlay(
    true,
    buildOverlayLastTitle || "Building workbook",
    "",
    buildOverlayLastPct || "waiting",
    "build",
  );
}
export function hideBuildOverlay() {
  if (buildOverlayDepth > 0) buildOverlayDepth--;
  if (buildOverlayDepth > 0) return;
  if (buildOverlayStartedAt) {
    recordPopupRuntime(buildOverlayPopupId, Date.now() - buildOverlayStartedAt);
  }
  stopSmoothProgress();
  const overlay = document.getElementById("buildOverlay");
  if (!overlay) return;
  if (buildOverlayTimer) {
    clearInterval(buildOverlayTimer);
    buildOverlayTimer = null;
  }
  buildOverlayStartedAt = 0;
  buildOverlayLastTitle = "";
  buildOverlayLastPct = 0;
  buildOverlayPopupId = "";
  overlay.classList.remove("active", "done", "error", "waiting");
  overlay.setAttribute("aria-hidden", "true");
  document.body.classList.remove("is-busy");
  const b = document.getElementById("buildOverlayBar");
  if (b) {
    b.style.width = "0%";
    b.style.animation = "none";
  }
  const p = document.getElementById("buildOverlayPct");
  if (p) p.textContent = "0%";
}
export function startBuildProgressTicker(startPct = 0) {
  stopBuildProgressTicker();
  updateBuildOverlay(
    "Building workbook",
    "Preparing build output...",
    startPct || 0,
  );
  startSmoothProgress(startPct || 0, 82, 22, 5000);
}
export function stopBuildProgressTicker() {
  if (buildProgressTicker) {
    clearInterval(buildProgressTicker);
    buildProgressTicker = null;
  }
  if (buildOverlayTimer) {
    clearInterval(buildOverlayTimer);
    buildOverlayTimer = null;
  }
  stopSmoothProgress();
}
export function startSmoothProgress(fromPct, cap, speed, delayMs) {
  stopSmoothProgress();
  _smoothFromPct = Number(fromPct) || 0;
  _smoothCap = cap != null ? cap : 82;
  _smoothSpeed = speed || 22;
  const delay = delayMs != null ? delayMs : 5000;
  const go = () => {
    _smoothStart = Date.now();
    _smoothIntervalTimer = setInterval(() => {
      const elapsed = (Date.now() - _smoothStart) / 1000;
      const target = Math.min(
        _smoothCap,
        _smoothFromPct +
          (_smoothCap - _smoothFromPct) *
            (1 - Math.exp(-elapsed / _smoothSpeed)),
      );
      if (buildOverlayLastPct < target - 0.4)
        updateBuildOverlay(buildOverlayLastTitle || "Building workbook", "", target);
    }, 350);
  };
  if (delay > 0) _smoothDelayTimer = setTimeout(go, delay);
  else go();
}
export function stopSmoothProgress() {
  if (_smoothDelayTimer) {
    clearTimeout(_smoothDelayTimer);
    _smoothDelayTimer = null;
  }
  if (_smoothIntervalTimer) {
    clearInterval(_smoothIntervalTimer);
    _smoothIntervalTimer = null;
  }
  _smoothStart = 0;
}
export function updateBuildProgress(job) {
  var pct = Number.isFinite(Number(job.progress))
    ? Number(job.progress)
    : "indeterminate";
  updateBuildOverlay(
    job.phase || "Building workbook",
    job.detail || "Working...",
    pct,
    job.status === "failed" ? "error" : undefined,
  );
  if (job.status === "done") {
    if (window.__desktopBuildTimeout)
      clearTimeout(window.__desktopBuildTimeout);
    var res = window.__desktopBuildResolve;
    window.__desktopBuildResolve = null;
    window.__desktopBuildReject = null;
    if (res) res(job.result || { success: true });
  } else if (job.status === "failed" || job.status === "cancelled") {
    if (window.__desktopBuildTimeout)
      clearTimeout(window.__desktopBuildTimeout);
    var rej = window.__desktopBuildReject;
    window.__desktopBuildResolve = null;
    window.__desktopBuildReject = null;
    if (rej)
      rej(
        new Error(
          (job.result && job.result.error) || job.detail || "Build failed.",
        ),
      );
  }
}
export async function buildWithProgress(buildBody) {
  // ARC-004/UX-009: fallback to /api/build is now scoped to only this
  // initial call (real HTTP status, not free-text "not found" matching);
  // nothing after a job_id issues ever falls back.
  let started;
  try {
    started = await api("/api/build/start", {
      method: "POST",
      body: JSON.stringify(buildBody),
    });
  } catch (e) {
    if (e && e.status === 404) {
      updateBuildOverlay(
        "Building workbook",
        "Progress telemetry unavailable; using the standard build endpoint.",
        5,
      );
      return await api("/api/build", {
        method: "POST",
        body: JSON.stringify(buildBody),
      });
    }
    throw e;
  }
  if (!started || !started.job_id)
    throw new Error("Build progress endpoint did not return a job id.");
  setActiveBuildJob(started.job_id);
  let lastProgress = Math.max(0, Number(started.progress) || 0);
  updateBuildOverlay(
    started.phase || "Preparing build",
    "Build accepted. Waiting for live build telemetry.",
    lastProgress,
  );
  startSmoothProgress(lastProgress, 82, 22, 5000);
  let lastKnownProgress = lastProgress;
  let lastChange = Date.now();
  try {
    for (let i = 0; i < 1600; i++) {
      await sleep(i < 40 ? 750 : 1500);
      const out = await api(
        "/api/build/progress/" + encodeURIComponent(started.job_id),
      );
      const job = out.job || {};
      let pct = Number.isFinite(Number(job.progress))
        ? Number(job.progress)
        : lastKnownProgress;
      if (pct > lastKnownProgress) {
        lastKnownProgress = pct;
        lastChange = Date.now();
      } else if (job.status === "running" && Date.now() - lastChange > 9000) {
        pct = "indeterminate";
      }
      lastProgress =
        pct === "indeterminate" ? lastProgress : Math.max(lastProgress, pct);
      updateBuildOverlay(
        job.phase || "Building workbook",
        job.detail || "Working through the current Monte Carlo/build step...",
        pct === "indeterminate" ? "indeterminate" : lastProgress,
        job.status === "failed" ? "error" : undefined,
      );
      if (job.status === "done") {
        const result = job.result || { success: true };
        if (result.success === false)
          throw new Error(result.error || job.detail || "Build failed.");
        return result;
      }
      if (job.status === "failed") {
        const result = job.result || {};
        throw new Error(result.error || job.detail || "Build failed.");
      }
      if (job.status === "cancelled") throw new Error("Build cancelled.");
    }
  } finally {
    stopSmoothProgress();
  }
  throw new Error("Build progress polling timed out after about 40 minutes.");
}

export async function fetchCurrentSummaryKpi() {
  try {
    const out = await api("/api/summary");
    if (out && out.success !== false) {
      const k = summaryFromApiPayload(out);
      return kpiHasValues(k) ? cloneSummary(k) : {};
    }
  } catch (_e) {}
  return {};
}
export async function captureBuildBaseline() {
  sessionBaselineSummary = await fetchCurrentSummaryKpi();
  sessionBaselineCaptured = true;
  return cloneSummary(sessionBaselineSummary || {});
}

// #<reports-redesign follow-up>: this used to force-navigate to the old
// standalone build_impact step after EVERY build, regardless of where the
// build was started -- including from Reports & Review's own header, which
// already shows Impact inline (renderReportsAndReview()/
// renderImpactSectionContent()). A user building from Reports & Review got
// yanked to a different page instead of seeing the fresh results in place.
// originStep (runBuild()'s stepBeforeBuild, previously captured and never
// used) lets this stay put when the build already started somewhere that
// shows Impact itself; every other origin (Planning Workbench, the welcome
// banner, the standalone build_impact page) keeps the original "jump to
// Impact" behavior.
export function renderBuildImpactAfterBuild(message, originStep) {
  if (originStep !== "reports_and_review") {
    activeStep = "build_impact";
  }
  planLoaded = true;
  renderMain();
  setAppControls(appReady);
  showStepHelp(activeStep);
  setTimeout(() => {
    window.scrollTo({ top: 0, behavior: "smooth" });
    const panel = document.querySelector(".build-impact");
    if (panel) {
      panel.setAttribute("tabindex", "-1");
      panel.focus({ preventScroll: true });
    }
    hideBuildOverlay();
  }, 80);
  if (message) showMessage(message);
}

Object.assign(window, {
  formatElapsed,
  refreshBuildOverlayTimer,
  setBuildOverlay,
  updateBuildOverlay,
  hideBuildInBackground,
  cancelActiveBuild,
  setActiveBuildJob,
  showBuildProgress,
  buildWasHiddenByUser,
  resetBuildHidden,
  setBuildRunningChip,
  hideBuildOverlay,
  startBuildProgressTicker,
  stopBuildProgressTicker,
  startSmoothProgress,
  stopSmoothProgress,
  updateBuildProgress,
  buildWithProgress,
  fetchCurrentSummaryKpi,
  captureBuildBaseline,
  
  
  
  renderBuildImpactAfterBuild,
});
