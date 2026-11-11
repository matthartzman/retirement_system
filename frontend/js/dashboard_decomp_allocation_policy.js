// ── Allocation policy rows and preview (allocationModeRow .. renderAllocationPolicy) ──
// Extracted verbatim from dashboard_decomp_row_model.js (W4-06, ARC-005). Bridge below.
export function allocationModeRow() {
  return (
    findEditableRow(
      "Asset Allocation Policy",
      "Global",
      "allocation_selection_mode",
    ) ||
    findEditableRow("Asset Allocation Policy", "Global", "allocation_mode") ||
    findEditableRow(
      "Asset Allocation Policy",
      "Global",
      "use_allocation_optimizer",
    )
  );
}

export function allocationSelectionMode() {
  const r = allocationModeRow();
  const v = String(r ? valOf(r) : "user_target")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_");
  if (v.includes("tangency") || v === "pure_tangency" || v === "unconstrained_sharpe")
    return "tangency";
  if (v.includes("real_loss") || v.includes("loss_aware") || v === "holding_period_aware")
    return "real_loss_aware";
  if (v.includes("max_sharpe") || v === "sharpe" || v === "sharpe_optimal")
    return "max_sharpe";
  if (v.includes("optimizer") || v === "yes" || v === "true" || v === "auto")
    return "optimizer_recommendation";
  return "user_target";
}

export function allocationTargetRows() {
  return rows
    .filter(isEditable)
    .filter(
      (r) =>
        r.section === "Asset Allocation Policy" &&
        norm(r.subsection) !== "global" &&
        norm(r.label) === "target_pct",
    );
}

export function optimizerOverrideRows() {
  return rows
    .filter(isEditable)
    .filter(
      (r) =>
        r.section === "Asset Class Optimizer Controls" &&
        norm(r.subsection) !== "global" &&
        norm(r.label) === "optimizer_override_pct",
    );
}

export function selectionActionRows() {
  return rows
    .filter(isEditable)
    .filter(
      (r) =>
        r.section === "Asset Class Optimizer Controls" &&
        norm(r.subsection) !== "global" &&
        norm(r.label) === "selection_action",
    );
}

export function assetCategory(asset) {
  const a = norm(asset);
  if (
    [
      "us_large_cap",
      "us_mid_cap",
      "us_small_cap",
      "international",
      "emerging_markets",
    ].includes(a)
  )
    return "Equity";
  if (
    [
      "bonds",
      "short_term_bonds",
      "tips",
      "municipal_bonds",
      "private_credit",
      "cash",
    ].includes(a)
  )
    return "Fixed income";
  return "Other";
}

export function findTargetRow(assetClass) {
  const key = norm(assetClass);
  return allocationTargetRows().find((r) => norm(r.subsection) === key);
}

export function rowActionValue(row) {
  const v = String(row ? valOf(row) : "include")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_");
  if (["exclude", "excluded", "no", "false", "disabled", "disable"].includes(v))
    return "exclude";
  if (
    [
      "consider_alternate",
      "consider_alternate_first",
      "alternate",
      "alternate_first",
      "alternative",
      "alternative_first",
    ].includes(v)
  )
    return "consider_alternate_first";
  return "include";
}

export function requestAllocationPreview() {
  // #323: allocation_assets and distribution_strategy were both legacy step
  // ids for pages that hosted the Allocation & Location panel; both now
  // redirect to strategy_optimize (SECTION_REDIRECTS in navigation.js), and
  // activeStep can never actually equal either of them once the redesign's
  // nav is in place. strategy_optimize is the only id the panel is shown
  // under now -- this is a replacement, not an additional accepted value.
  if (!planLoaded || activeStep !== "strategy_optimize") return;
  const key = allocationPreviewFingerprint();
  if (allocationPreviewLoading && allocationPreviewKey === key) return;
  if (
    allocationPreview &&
    allocationPreviewKey === key &&
    !allocationPreviewError
  )
    return;
  allocationPreviewKey = key;
  allocationPreviewLoading = true;
  allocationPreviewError = "";
  const seq = ++allocationPreviewSeq;
  api("/api/allocation-preview", {
    method: "POST",
    body: JSON.stringify({
      rows: allocationPreviewRowsForPost(),
      mode: allocationSelectionMode(),
    }),
  })
    .then((out) => {
      if (seq !== allocationPreviewSeq) return;
      allocationPreviewLoading = false;
      if (out && out.success !== false) {
        allocationPreview = out;
        allocationPreviewError = "";
      } else {
        allocationPreview = null;
        allocationPreviewError =
          (out && out.error) || "Allocation preview failed";
      }
    })
    .catch((e) => {
      if (seq !== allocationPreviewSeq) return;
      allocationPreviewLoading = false;
      allocationPreview = null;
      allocationPreviewError = e.message || String(e);
    })
    .finally(() => {
      if (seq === allocationPreviewSeq && activeStep === "strategy_optimize")
        renderMain();
    });
}

export function allocationTargetTotalPct() {
  return allocationTargetRows().reduce((s, r) => {
    const a = selectionActionRows().find(
      (x) => norm(x.subsection) === norm(r.subsection),
    );
    return (
      s + (rowActionValue(a) === "exclude" ? 0 : parsePercentInput(valOf(r)))
    );
  }, 0);
}

export function optimizerOverrideTotalPct() {
  return optimizerOverrideRows().reduce(
    (s, r) => s + parsePercentInput(valOf(r)),
    0,
  );
}

export function optimizerOverrideHasEntries() {
  return optimizerOverrideRows().some(
    (r) => String(valOf(r) || "").trim() !== "",
  );
}

export function optimizerOverrideValid() {
  if (!optimizerOverrideHasEntries()) return true;
  return Math.abs(optimizerOverrideTotalPct() - 100) <= 0.01;
}

export function allocationTotalHtml() {
  const total = allocationTargetTotalPct();
  const ok = Math.abs(total - 100) <= 0.01;
  return `<div class="section-note" id="allocationTargetTotal"><b>User-specified allocation total:</b> ${total.toFixed(2)}% ${ok ? "✓" : "— must equal 100.00% before saving or building in user-specified mode."}</div>`;
}

export function renderAllocationPolicy() {
  const rs = allocationPolicyRows();
  if (!rs.length)
    return '<div class="holdings"><div class="field-list"><p>No optimizer input rows were found. Reload the current plan so optimizer inputs can be backfilled.</p></div></div>';
  return `<div class="holdings"><details><summary>Optimizer inputs</summary><div class="field-list">${rs.map(fieldHtml).join("")}</div></details></div>`;
}
Object.assign(window, {
  allocationModeRow, allocationSelectionMode, allocationTargetRows, allocationTargetTotalPct,
  allocationTotalHtml, assetCategory, findTargetRow, optimizerOverrideHasEntries,
  optimizerOverrideRows, optimizerOverrideTotalPct, optimizerOverrideValid, renderAllocationPolicy,
  requestAllocationPreview, rowActionValue, selectionActionRows,
});
