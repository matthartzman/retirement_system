// ── Build runner (runBuild, build warnings, workbook download) ──
// Extracted verbatim from dashboard_decomp_row_model.js (W4-06, ARC-005); build-in-flight state stays private here.
// WI-019: a build the user hid (hideBuildInBackground) is still running; a second one must not
// start on top of it, and the hide flag/chip are cleared whenever a build ends.
let buildInFlight = false;
// WI-019 / ARC-003: swallowed derived-result steps reported by the last build (the
// config_contract_warnings WI-007 collects), shown on the build result banner and Build Impact.
let lastBuildWarnings = [];
export function buildWarningsBannerHtml() {
  if (!lastBuildWarnings.length) return "";
  return (
    '<div class="section-note warn build-warnings" role="group" aria-label="Build warnings"><b>The last build finished with ' +
    lastBuildWarnings.length +
    " warning" +
    (lastBuildWarnings.length === 1 ? "" : "s") +
    ".</b> Some report content may be missing:<ul class=\"inapp-modal-list\">" +
    lastBuildWarnings.map((w) => "<li>" + esc(w) + "</li>").join("") +
    "</ul></div>"
  );
}

export async function runBuild(queue = false, opts = {}) {
  const fromDownload = !!(opts && opts.fromDownload);
  const stepBeforeBuild = activeStep;
  if (buildInFlight) {
    showMessage(
      "A build is already running in the background. Wait for it to finish before starting another.",
      "warn",
    );
    return false;
  }
  buildInFlight = true;
  resetBuildHidden();
  try {
    if (!validateAllocationTargetsOrMessage()) return false;
    setBuildOverlay(
      true,
      "Preparing build",
      "Capturing the current workbook baseline...",
      0,
      "build",
    );
    const before = await captureBuildBaseline();
    const hadUnsaved = hasUnsavedPlanChanges();
    const buildChanges = capturedSessionChanges().map((c) =>
      Object.assign({}, c),
    );
    updateBuildOverlay(
      "Saving current plan",
      "Saving the on-screen inputs to the local database before building outputs.",
      6,
    );
    const saved = await saveWorkingCopy();
    if (!saved) {
      showMessage(
        "Could not save the plan before building. Check disk space and try again.",
        "error",
      );
      hideBuildOverlay();
      return false;
    }
    updateBuildOverlay(
      "Checking build preflight",
      "Reviewing saved Plan Data, report freshness, pricing diagnostics, and validation warnings.",
      10,
    );
    buildPreflight = await api("/api/build/preflight");
    updatePlanStateBanner();
    const blockers = (buildPreflight && buildPreflight.blockers) || [];
    const warnings = (buildPreflight && buildPreflight.warnings) || [];
    if (blockers.length) {
      hideBuildOverlay();
      showMessage("Build preflight blocked: " + blockers[0], "error", {
        persistent: true,
      });
      if (activeStep !== "review") {
        activeStep = "review";
        renderMain();
      }
      return false;
    }
    if (warnings.length && !fromDownload && !opts.skipPreflightConfirm) {
      hideBuildOverlay();
      const warnHtml =
        "<p>Build preflight found <b>" +
        warnings.length +
        " warning" +
        (warnings.length === 1 ? "" : "s") +
        '</b>:</p><ul class="inapp-modal-list">' +
        warnings
          .slice(0, 5)
          .map((w) => "<li>" + esc(w) + "</li>")
          .join("") +
        "</ul><p>Continue building anyway?</p>";
      const proceed = await showInAppConfirm(warnHtml, {
        title: "Preflight Warnings",
        confirmLabel: "Continue Build",
        cancelLabel: "Review Preflight",
        variant: "warn",
        bodyIsHtml: true,
      });
      if (!proceed) {
        if (activeStep !== "review") {
          activeStep = "review";
          renderMain();
        }
        return false;
      }
      setBuildOverlay(
        true,
        "Starting build",
        "Continuing after preflight warning review.",
        12,
        "build",
      );
    }
    let buildBody = {
      queue,
      ui_saved_working_copy: true,
      build_input_source: "sqlite_snapshot",
    };
    lastBuildOk = false;
    setAppControls(appReady);
    showMessage("Building outputs...");
    updateBuildOverlay(
      "Starting build",
      "Launching generated workbook and report outputs from the saved database snapshot.",
      0,
    );
    const out = await buildWithProgress(buildBody);
    if (out && out.success !== false) {
      detailedResultsData = null;
      detailedResultSheets = {};
      detailedResultsError = "";
      detailedResultSheetError = "";
      activeDetailedSheet = "";
      if (window.invalidateWorkbookFormatCache) window.invalidateWorkbookFormatCache();
      updateBuildOverlay(
        "Preparing Build Impact",
        "Comparing changes, terminal net worth, after-tax net worth, lifetime taxes, Monte Carlo success probability, and Roth conversions.",
        96,
      );
      lastBuildOk = true;
      lastBuildWarnings = Array.isArray(out.warnings)
        ? out.warnings.map((w) => String(w))
        : [];
      lastBuildSummary = summaryFromApiPayload(out);
      if (!kpiHasValues(lastBuildSummary)) lastBuildSummary = out.kpi || {};
      const postBuildStatus = await refreshBuildStatus();
      rememberBuildCompare({
        before: kpiHasValues(before) ? before : {},
        after: lastBuildSummary,
        changes: buildChanges,
        admin_changes: out.admin_changes || [],
        qc: out.qc_result || lastBuildSummary.qc_result || "Complete",
        elapsed: out.elapsed_seconds ? `Built in ${out.elapsed_seconds}s` : "",
        provenance: buildHistoryProvenance(postBuildStatus || buildPreflight),
      });
      sessionBaselineSummary = cloneSummary(lastBuildSummary);
      sessionBaselineCaptured = true;
      sessionChanges.clear();
      sessionSpecialChanges.clear();
      updateBuildOverlay(
        "Build complete",
        fromDownload ? "Build complete." : "Opening Impact & Build History.",
        100,
        "done",
      );
      const nWarn = lastBuildWarnings.length;
      const warnText =
        "Build finished with " +
        nWarn +
        " warning" +
        (nWarn === 1 ? "" : "s") +
        ": " +
        lastBuildWarnings[0] +
        (nWarn > 1 ? " (and " + (nWarn - 1) + " more on Impact & Build History)" : "");
      if (fromDownload) {
        setTimeout(hideBuildOverlay, 400);
        if (nWarn) showMessage(warnText, "warn", { persistent: true });
        else showMessage("Build successful.");
        renderMain();
      } else if (buildWasHiddenByUser()) {
        // The user hid the progress window and moved on: do not pull them to another page.
        setBuildRunningChip(false);
        showMessage(
          (nWarn ? warnText : "Build finished in the background.") + " Open Impact & Build History to see the results.",
          nWarn ? "warn" : "info",
          {
            persistent: true,
            action: {
              label: "View Impact & Build History",
              fn: "renderBuildImpactAfterBuild(null,null)",
            },
          },
        );
      } else {
        renderBuildImpactAfterBuild(
          nWarn ? null : "Build successful. Build impact is ready.",
          stepBeforeBuild,
        );
        if (nWarn) showMessage(warnText, "warn", { persistent: true });
      }
      maybeRunLocalBackup("build");
    } else throw new Error(JSON.stringify(out));
  } catch (e) {
    stopBuildProgressTicker();
    lastBuildOk = false;
    setAppControls(appReady);
    updateBuildOverlay(
      "Build failed",
      "The build stopped before Impact & Build History could be displayed.",
      100,
      "error",
    );
    // A hidden overlay is already closed; a delayed hide would close someone else's.
    if (!buildWasHiddenByUser()) setTimeout(hideBuildOverlay, 700);
    setBuildRunningChip(false);
    showMessage("Error building: " + e.message, "error");
  } finally {
    buildInFlight = false;
  }
  return lastBuildOk;
}

export async function downloadWithBuild(url, label) {
  try {
    if (lastBuildOk && !unsavedChangeCount()) {
      downloadFile(url);
      return;
    }
    const ok = await runBuild(false, { fromDownload: true });
    if (ok) downloadFile(url);
  } catch (e) {
    showMessage("Error building for download: " + e.message, "error");
  }
}

// #<reports-redesign>: Build/Download for Reports & Review's persistent
// header (primaryActionForStep(), dashboard.js) -- distinct from
// downloadWithBuild() above, which silently rebuilds before downloading.
// This page instead asks: an explicit warning lets the user choose to
// download the last successful build's workbook as-is rather than being
// rebuilt out from under them.
export function reportsAndReviewCanBuild() {
  // Active whenever there's something a build would actually change: pending
  // edits, or no successful build has ever completed (so a freshly loaded,
  // never-built plan isn't permanently stuck with a disabled button).
  return hasUnsavedPlanChanges() || !lastBuildOk;
}

export async function reportsAndReviewDownloadWorkbook() {
  // Gated on planStateArtifactsReady() (do report output files actually
  // exist), not lastBuildOk: updateUnsaved() forces lastBuildOk false as
  // soon as ANY input is dirty, regardless of whether a build has ever
  // succeeded -- exactly the case this button needs to allow (downloading
  // the last real build despite newer unsaved edits). Calling
  // performFileDownload() directly, rather than downloadFile(), for the same
  // reason: downloadFile()'s own lastBuildOk gate would otherwise refuse
  // right after the user has just confirmed "download anyway" below.
  if (!planStateArtifactsReady()) {
    showMessage("Build reports before downloading the workbook.", "error");
    return;
  }
  // planStateFresh(), not unsavedChangeCount() alone: this is the same
  // "is it stale" signal the left-nav Stale badge (stepButton(), reportStale)
  // and every other freshness indicator in the app already use. A first fix
  // here checked unsavedChangeCount() only, so right after a plain page
  // reload -- lastBuildOk resets to false every session regardless of
  // whether the on-disk build is actually current, but there are zero
  // unsaved edits -- the badge said "Stale" while this downloaded silently
  // with no warning at all. Reproduced live, not hypothetical.
  if (planStateFresh()) {
    performFileDownload("/api/xlsx");
    return;
  }
  const proceed = await showInAppConfirm(
    "The last build doesn't reflect changes made since then. Download that build's workbook anyway?",
    {
      title: "Build may be out of date",
      confirmLabel: "Download anyway",
      cancelLabel: "Cancel",
      variant: "warn",
    },
  );
  if (proceed) performFileDownload("/api/xlsx");
}
Object.assign(window, {
  buildWarningsBannerHtml, downloadWithBuild, reportsAndReviewCanBuild,
  reportsAndReviewDownloadWorkbook, runBuild,
});
