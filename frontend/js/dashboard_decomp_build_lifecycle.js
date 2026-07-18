/* Build lifecycle UI: duration estimate, progress overlay, smooth-progress
   ticker, cancel, and post-build snapshot/baseline handling. Extracted verbatim
   from dashboard.js as part of the dashboard decomposition.

   Plain classic script sharing dashboard.js's global scope, loaded BEFORE
   dashboard.js in index.html so these globals are defined before dashboard.js's
   end-of-file boot runs. No logic changed; function names, module-level state
   (buildCancelled) and behavior are byte-for-byte identical to the original
   inline block. */
function estimateBuildDurationLabel() {
  const mode = String(
    rowConfigValue("mc_engine_mode", "advanced_exact_scalar"),
  ).toLowerCase();
  const sims =
    Number(
      String(rowConfigValue("mc_simulations", "300")).replace(/[^0-9.]/g, ""),
    ) || 300;
  const sens =
    Number(
      String(rowConfigValue("mc_sensitivity_simulations", "25")).replace(
        /[^0-9.]/g,
        "",
      ),
    ) || 25;
  if (mode.includes("quick") || mode.includes("vector"))
    return `quick Monte Carlo: ${sims.toLocaleString()} paths`;
  return `advanced Monte Carlo: ${sims.toLocaleString()} paths + sensitivity ${sens.toLocaleString()}/cell`;
}
function formatElapsed(ms) {
  const total = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(total / 60),
    sec = String(total % 60).padStart(2, "0");
  return `${m}:${sec}`;
}
function friendlyBuildDetail(detail) {
  let text = String(detail || "Working through the build steps...").trim();
  if (!text) return "Working through the build steps...";
  const low = text.toLowerCase();
  if (/sheet\s+\d+/.test(low)) return "Writing workbook pages.";
  if (/saving to/.test(low)) return "Saving the finished workbook.";
  if (/output directory|using config backend/.test(low))
    return "Preparing the build environment.";
  if (/\.csv|\.xlsx|\.pdf|[a-z]:\|\/[^\s]+\//i.test(text))
    return "Working through the next build step.";
  return text;
}
function overlayTimerSuffix() {
  const elapsed = buildOverlayStartedAt
    ? formatElapsed(Date.now() - buildOverlayStartedAt)
    : "0:00";
  return buildOverlayExpectedLabel
    ? `Elapsed ${elapsed} • ${buildOverlayExpectedLabel}`
    : `Elapsed ${elapsed}`;
}
function refreshBuildOverlayTimer() {
  const d = document.getElementById("buildOverlayDetail");
  if (!d || !buildOverlayStartedAt) return;
  d.textContent = `${friendlyBuildDetail(buildOverlayLastDetail)}  (${overlayTimerSuffix()})`;
}
function setBuildOverlay(active, title, detail, pct, expectedLabel) {
  const overlay = document.getElementById("buildOverlay");
  if (!overlay) return;
  if (active) {
    buildOverlayStartedAt = Date.now();
    buildOverlayExpectedLabel =
      expectedLabel !== undefined
        ? expectedLabel
        : estimateBuildDurationLabel();
    if (buildOverlayTimer) clearInterval(buildOverlayTimer);
    buildOverlayTimer = setInterval(refreshBuildOverlayTimer, 1000);
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
function updateBuildOverlay(title, detail, pct, state) {
  const overlay = document.getElementById("buildOverlay");
  if (!overlay) return;
  overlay.classList.remove("waiting");
  if (state) {
    overlay.classList.remove("done", "error");
    overlay.classList.add(state);
  }
  const t = document.getElementById("buildOverlayTitle");
  const d = document.getElementById("buildOverlayDetail");
  const b = document.getElementById("buildOverlayBar");
  const p = document.getElementById("buildOverlayPct");
  if (t && title) {
    buildOverlayLastTitle = title;
    t.textContent = title;
  }
  if (detail) {
    buildOverlayLastDetail = friendlyBuildDetail(detail);
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
async function cancelBuild() {
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
function hideBuildOverlay() {
  stopSmoothProgress();
  const overlay = document.getElementById("buildOverlay");
  if (!overlay) return;
  if (buildOverlayTimer) {
    clearInterval(buildOverlayTimer);
    buildOverlayTimer = null;
  }
  buildOverlayStartedAt = 0;
  buildOverlayExpectedLabel = "";
  buildOverlayLastTitle = "";
  buildOverlayLastDetail = "";
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
function startBuildProgressTicker(startPct = 0) {
  stopBuildProgressTicker();
  updateBuildOverlay(
    "Building workbook",
    "Preparing build output...",
    startPct || 0,
  );
  startSmoothProgress(startPct || 0, 82, 22, 5000);
}
function stopBuildProgressTicker() {
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
function startSmoothProgress(fromPct, cap, speed, delayMs) {
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
        updateBuildOverlay(
          buildOverlayLastTitle || "Building workbook",
          buildOverlayLastDetail || "",
          target,
        );
    }, 350);
  };
  if (delay > 0) _smoothDelayTimer = setTimeout(go, delay);
  else go();
}
function stopSmoothProgress() {
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
function updateBuildProgress(job) {
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
async function buildWithProgress(buildBody) {
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

async function fetchCurrentSummaryKpi() {
  try {
    const out = await api("/api/summary");
    if (out && out.success !== false) {
      const k = summaryFromApiPayload(out);
      return kpiHasValues(k) ? cloneSummary(k) : {};
    }
  } catch (_e) {}
  return {};
}
async function captureBuildBaseline() {
  sessionBaselineSummary = await fetchCurrentSummaryKpi();
  sessionBaselineCaptured = true;
  return cloneSummary(sessionBaselineSummary || {});
}

function snapshotPendingEdits() {
  const fieldUpdates = [];
  try {
    dirty.forEach((value, idx) => {
      const row = rows.find((r) => r.row_index === idx);
      if (row)
        fieldUpdates.push({
          section: row.section || "",
          subsection: row.subsection || "",
          label: row.label || "",
          value: String(value ?? ""),
        });
    });
  } catch (_e) {}
  return {
    fieldUpdates,
    holdingsChanged: !!holdingsChanged,
    holdingsText: String(holdingsText || ""),
    liabilitiesChanged: !!liabilitiesChanged,
    liabilitiesText: String(liabilitiesText || ""),
    travelExtrasChanged: !!travelExtrasChanged,
    travelExtras: JSON.parse(JSON.stringify(travelExtras || [])),
    liquidityChanged: !!liquidityChanged,
    liquidityBuffers: JSON.parse(JSON.stringify(liquidityBuffers || [])),
    forcedConversionsChanged: !!forcedConversionsChanged,
    forcedConversions: JSON.parse(JSON.stringify(forcedConversions || [])),
  };
}
function hasSnapshotEdits(s) {
  return !!(
    s &&
    (s.fieldUpdates?.length ||
      s.holdingsChanged ||
      s.liabilitiesChanged ||
      s.travelExtrasChanged ||
      s.liquidityChanged)
  );
}
function restorePendingEdits(s) {
  if (!s) return;
  (s.fieldUpdates || []).forEach((u) => {
    const row = rows.find(
      (r) =>
        r.section === u.section &&
        r.subsection === u.subsection &&
        r.label === u.label,
    );
    if (row) {
      const original = storageValueForInput(row, row.value || "");
      if (String(u.value) === String(original)) dirty.delete(row.row_index);
      else {
        dirty.set(row.row_index, String(u.value));
        noteSessionFieldChange(
          row,
          displayValueForInput(row, row.value || ""),
          displayValueForInput(row, u.value),
          original,
          u.value,
        );
      }
    }
  });
  if (s.holdingsChanged) {
    holdingsText = String(s.holdingsText || "");
    holdingRowsCache = null;
    holdingsChanged = true;
    noteSpecialSessionChange("Investment holdings updated");
  }
  if (s.liabilitiesChanged) {
    liabilitiesText = String(s.liabilitiesText || "");
    liabilityRowsCache = null;
    liabilitiesChanged = true;
    noteSpecialSessionChange("Liabilities updated");
  }
  if (s.travelExtrasChanged) {
    travelExtras = JSON.parse(JSON.stringify(s.travelExtras || []));
    travelExtrasChanged = true;
    noteSpecialSessionChange("Large Discretionary Expenses updated");
  }
  if (s.liquidityChanged) {
    liquidityBuffers = JSON.parse(JSON.stringify(s.liquidityBuffers || []));
    liquidityChanged = true;
    noteSpecialSessionChange("Liquidity buffers updated");
  }
  if (s.forcedConversionsChanged) {
    forcedConversions = JSON.parse(JSON.stringify(s.forcedConversions || []));
    forcedConversionsChanged = true;
    noteSpecialSessionChange("Forced conversions updated");
  }
  updateUnsaved();
}
function renderBuildImpactAfterBuild(message) {
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
