/* Build lifecycle UI: duration estimate, progress overlay, smooth-progress
   ticker, cancel, and post-build snapshot/baseline handling. Extracted verbatim
   from dashboard.js as part of the dashboard decomposition.

   Wave 6.4 ("leaves inward" ES-module migration, 'plan_state_build' leaf):
   converted to a real ES module. Unlike dashboard_decomp_local_backups.js
   (which stayed classic), none of this file's functions are called from
   dashboard.js's own synchronous top-level boot chain -- every call site
   (buildWithProgress, cancelBuild, setBuildOverlay, etc.) lives inside a
   user-triggered action (Build Reports / Download / Cancel), which can only
   fire after the page has finished loading. All the module-level state these
   functions read/write (buildOverlayStartedAt, buildOverlayDepth,
   buildProgressTicker, sessionBaselineSummary, ...) is owned by dashboard.js
   itself (`let` declarations, not this file's), which modules can read and
   write as bare identifiers the same as any other classic-script global (see
   dashboard_decomp_holdings.js's header for why). buildCancelled is the one
   piece of state this file owns; nothing outside reads or writes it. */
export function formatElapsed(ms) {
  const total = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(total / 60),
    sec = String(total % 60).padStart(2, "0");
  return `${m}:${sec}`;
}
export function refreshBuildOverlayTimer() {
  const d = document.getElementById("buildOverlayDetail");
  if (!d || !buildOverlayStartedAt) return;
  d.textContent = `Elapsed ${formatElapsed(Date.now() - buildOverlayStartedAt)}`;
}
export function setBuildOverlay(active, title, detail, pct) {
  const overlay = document.getElementById("buildOverlay");
  if (!overlay) return;
  if (active) {
    buildOverlayDepth++;
    if (buildOverlayDepth === 1) {
      buildOverlayStartedAt = Date.now();
      if (buildOverlayTimer) clearInterval(buildOverlayTimer);
      buildOverlayTimer = setInterval(refreshBuildOverlayTimer, 1000);
    }
  } else if (buildOverlayTimer) {
    clearInterval(buildOverlayTimer);
    buildOverlayTimer = null;
  }
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
    p.textContent = value === null ? "Working…" : Math.round(value) + "%";
  }
  refreshBuildOverlayTimer();
}
let buildCancelled = false;
export async function cancelBuild() {
  if (
    !(await showInAppConfirm("The workbook will be left incomplete.", {
      title: "Cancel Build",
      confirmLabel: "Cancel Build",
      cancelLabel: "Keep Building",
      variant: "warn",
    }))
  )
    return;
  buildCancelled = true;
  hideBuildOverlay();
  setAppControls(true);
  showMessage("Build cancelled.", "warn");
}
export function hideBuildOverlay() {
  if (buildOverlayDepth > 0) buildOverlayDepth--;
  if (buildOverlayDepth > 0) return;
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
  } else if (job.status === "failed") {
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
  try {
    const started = await api("/api/build/start", {
      method: "POST",
      body: JSON.stringify(buildBody),
    });
    if (!started || !started.job_id)
      throw new Error("Build progress endpoint did not return a job id.");
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
      }
    } finally {
      stopSmoothProgress();
    }
    throw new Error("Build progress polling timed out after about 40 minutes.");
  } catch (e) {
    stopSmoothProgress();
    if (
      String((e && e.message) || e).includes("404") ||
      String((e && e.message) || e)
        .toLowerCase()
        .includes("not found")
    ) {
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

export function renderBuildImpactAfterBuild(message) {
  activeStep = "build_impact";
  planLoaded = true;
  renderMain();
  setAppControls(appReady);
  showStepHelp("build_impact");
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
  cancelBuild,
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
