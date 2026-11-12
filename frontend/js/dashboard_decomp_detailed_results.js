// ── Detailed Results sheet loading (loadDetailedResultSheet, preflight refresh) ──
// Extracted verbatim from dashboard_decomp_row_model.js (W4-06, ARC-005). Bridge below.
export function _isViewingDetailedResults() {
  return activeStep === "detailed_results";
}

export async function loadDetailedResultSheet(name, force = false) {
  name = String(name || "");
  if (!name) return Promise.resolve(null);
  if (detailedResultSheets[name] && !force)
    return Promise.resolve(detailedResultSheets[name]);
  if (detailedResultSheetInFlight[name] && !force)
    return detailedResultSheetInFlight[name];
  const seq = ++detailedResultSheetSeq;
  const isChartDashboardSheet = /chart/i.test(name) && /dashboard/i.test(name);
  const isAssetAllocationSheet = /asset\s+allocation/i.test(name);
  detailedResultSheetLoading = true;
  detailedResultSheetLoadingName = name;
  detailedResultSheetError = "";
  startDetailedResultsProgress("sheet");
  if (isChartDashboardSheet || isAssetAllocationSheet) {
    detailedResultsProgress = {
      active: true,
      pct: 22,
      phase: isChartDashboardSheet
        ? "Loading Chart Dashboard"
        : "Loading Asset Allocation",
      detail: isChartDashboardSheet
        ? "Building browser-friendly charts from workbook chart data. Data tables are not rendered here."
        : "Loading a UI-bounded allocation result view so the browser does not freeze on dense workbook ranges.",
      startedAt: detailedResultsProgress.startedAt,
      mode: "sheet",
    };
    renderDetailedResultsProgressTick();
  }
  detailedResultSheetInFlight[name] = (async () => {
    try {
      const out = await api(
        "/api/detailed-results?sheet=" + encodeURIComponent(name),
        {
          timeoutMs: isChartDashboardSheet
            ? 20000
            : isAssetAllocationSheet
              ? 30000
              : 60000,
        },
      );
      if (seq !== detailedResultSheetSeq) return null;
      detailedResultsProgress = {
        active: true,
        pct: 96,
        phase: isChartDashboardSheet
          ? "Rendering charts"
          : "Rendering selected result",
        detail: isChartDashboardSheet
          ? "Preparing the chart-only dashboard view."
          : "Preparing result sections for display.",
        startedAt: detailedResultsProgress.startedAt,
        mode: "sheet",
      }; // Support both the Excel-parser format {success,sheet:{...}} and the
      // semantic-model format where the page IS the response object.
      const sheetData =
        out && out.success
          ? out.sheet || (out.kind || out.sections || out.charts ? out : null)
          : null;
      if (sheetData) {
        detailedResultSheets[name] = sheetData;
        mergeDetailedSheetMeta(sheetData);
        return sheetData;
      } else {
        detailedResultSheetError =
          (out && out.error) || "Selected result page is not available.";
        return null;
      }
    } catch (e) {
      if (seq !== detailedResultSheetSeq) return null;
      const msg = e && e.message ? e.message : String(e);
      const timed =
        msg.toLowerCase().includes("timed out") || msg.includes("aborted");
      detailedResultSheetError = timed
        ? isChartDashboardSheet
          ? "Chart Dashboard loading timed out while preparing browser-native charts. Try Refresh results, rebuild reports, or choose another result page."
          : isAssetAllocationSheet
            ? "Asset Allocation loading timed out while preparing a browser-friendly view. Use Download Workbook for the full Excel sheet, or retry this page."
            : "Selected result page loading timed out. This page may be very large. Try Refresh results or choose another page."
        : msg;
      return null;
    } finally {
      delete detailedResultSheetInFlight[name];
      if (seq !== detailedResultSheetSeq) return;
      detailedResultSheetLoading = false;
      detailedResultSheetLoadingName = "";
      stopDetailedResultsProgress(detailedResultSheetError ? 0 : 100);
      if (_isViewingDetailedResults()) renderMain();
      else renderSteps();
    }
  })();
  return detailedResultSheetInFlight[name];
}

export function _updateDetailGroupStatus(el) {
  const wrap = el.closest(".detail-single-table-wrap");
  if (!wrap) return;
  const table = wrap.querySelector("table");
  const status = wrap.querySelector(".detail-col-group-status");
  if (!table || !status) return;
  const groups = Array.from(table.querySelectorAll(".detail-col-group-th"));
  const expanded = groups.filter(function (g) {
    return !g.classList.contains("collapsed");
  }).length;
  const total = groups.length;
  status.textContent =
    total +
    " group" +
    (total !== 1 ? "s" : "") +
    " · " +
    (expanded === 0 ? "all collapsed" : expanded + " expanded");
}

export async function refreshPreflightForReview() {
  try {
    buildPreflight = await api("/api/build/preflight");
    updatePlanStateBanner();
    renderMain();
    showMessage("Build preflight refreshed.");
  } catch (e) {
    showMessage("Preflight failed: " + e.message, "error");
  }
}
Object.assign(window, { _isViewingDetailedResults, _updateDetailGroupStatus, loadDetailedResultSheet, refreshPreflightForReview });
