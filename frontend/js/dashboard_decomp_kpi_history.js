// ── KPI deltas, current KPI and build history (W4-06): extracted verbatim from row_model; bridge below ──
export function fmtDelta(v) {
  if (v === undefined || v === null || v === "") return "Not available";
  const n = Number(v);
  if (!Number.isFinite(n)) return "Not available";
  const sign = n > 0 ? "+" : "";
  return (
    sign +
    n.toLocaleString(undefined, {
      style: "currency",
      currency: "USD",
      maximumFractionDigits: 0,
    })
  );
}

export function fmtPctDelta(v) {
  if (v === undefined || v === null || v === "") return "Not available";
  const n = Number(v);
  if (!Number.isFinite(n)) return "Not available";
  const sign = n > 0 ? "+" : "";
  return (
    sign + n.toLocaleString(undefined, { maximumFractionDigits: 1 }) + " pts"
  );
}

export function firstFinite(...vals) {
  for (const v of vals) {
    const n = finiteOrNull(v);
    if (Number.isFinite(n)) return n;
  }
  return NaN;
}

export function deriveAfterTaxTerminalNw(summary) {
  summary = summary || {};
  const direct = firstFinite(
    summary.after_tax_terminal_nw,
    summary.after_tax_terminal_net_worth,
    summary.after_tax_nw,
    summary.after_tax_net_worth,
  );
  if (Number.isFinite(direct)) return direct;
  const terminal = firstFinite(summary.terminal_nw, summary.terminal_net_worth);
  const deferred = firstFinite(
    summary.terminal_deferred_tax_total,
    summary.terminal_deferred_pretax_tax,
    summary.terminal_deferred_taxable_cap_gain_tax,
    summary.deferred_pretax_tax,
    summary.embedded_deferred_tax,
  );
  if (Number.isFinite(terminal) && Number.isFinite(deferred))
    return terminal - deferred;
  const pretax = firstFinite(
    summary.terminal_pretax_nw,
    summary.terminal_pretax_net_worth,
    summary.pretax_terminal_nw,
  );
  const rate = firstFinite(
    summary.terminal_after_tax_rate_used,
    summary.roth_optimize_terminal_tax_rate,
    summary.roth_target_rate,
  );
  if (
    Number.isFinite(terminal) &&
    Number.isFinite(pretax) &&
    Number.isFinite(rate)
  )
    return (
      terminal -
      Math.max(0, pretax) * Math.max(0, Math.abs(rate) > 1 ? rate / 100 : rate)
    );
  return NaN;
}

export function currentKpi(summary) {
  summary = summary || {};
  const afterTax = deriveAfterTaxTerminalNw(summary);
  return {
    terminal_nw: firstFinite(
      summary.terminal_nw,
      summary.terminal_net_worth,
      // inheritable_nw is the key name pushBuildHistoryEntry/rememberBuildCompare
      // actually store terminal net worth under (see dashboard.js ~1852, ~1898) —
      // metricSummary() in planning_workbench_ui.js already checks this alias;
      // currentKpi() needs it too so build-history-sourced summaries resolve.
      summary.inheritable_nw,
    ),
    lifetime_tax: firstFinite(
      summary.lifetime_tax,
      summary.total_taxes,
      summary.total_tax,
    ),
    after_tax_terminal_nw: afterTax,
    post_tax_inheritance: firstFinite(summary.post_tax_inheritance, afterTax),
    terminal_estate_tax: firstFinite(summary.terminal_estate_tax),
    mc_success: firstFinite(
      summary.mc_success,
      summary.monte_carlo_success,
      summary.success_rate,
    ),
    // #202: success_rate requires BOTH not running out of money AND keeping
    // the configured reserve floor -- success_rate_no_ruin drops the reserve
    // requirement so a change to the reserve setting doesn't get misread as
    // a change in the plan's actual resilience.
    mc_success_no_ruin: firstFinite(
      summary.mc_success_no_ruin,
      summary.success_rate_no_ruin,
    ),
    total_roth_conversions: deriveTotalRothConversions(summary),
    blended_return_info: firstFinite(summary.blended_return_info),
    // #293: the 3 Impact-page dial metrics, plus EFTR (Effective Future Tax
    // Rate) as a 4th supplemental stat -- already computed by
    // compute_future_lcv_and_eftr (its "from today, no upper bound" row set
    // already covers the current year through plan end).
    lcv: firstFinite(summary.lcv),
    lcv_all_in_including_taxes: firstFinite(summary.lcv_all_in_including_taxes),
    npv_future_taxes: firstFinite(summary.npv_future_taxes),
    terminal_nw_mc_p5: firstFinite(summary.terminal_nw_mc_p5),
    eftr: firstFinite(summary.eftr),
  };
}

export function loadBuildHistory() {
  try {
    const raw = localStorage.getItem(BUILD_HISTORY_LS_KEY);
    buildHistory = raw ? JSON.parse(raw) : [];
  } catch (_e) {
    buildHistory = [];
  }
  // #309/#331: an entry saved before some `kpi` field the dials/suggestions
  // panel now require was added has nothing to migrate to (LCV/NPV of Future
  // Taxes/Worst-Case Ending Wealth/EFTR/All-In LCV require re-running the
  // build, which this load path must not do), so drop it rather than render
  // dials with missing/undefined values. schemaVersion generalizes this:
  // bumping BUILD_HISTORY_SCHEMA_VERSION when a required field is added (or
  // removed) is now the whole fix, instead of writing a new bespoke filter
  // predicate here every time. An entry with no schemaVersion at all predates
  // this mechanism and is always dropped.
  const before = buildHistory.length;
  buildHistory = buildHistory.filter(
    (e) =>
      e &&
      e.kpi &&
      Number.isFinite(Number(e.kpi.lcv)) &&
      e.schemaVersion === BUILD_HISTORY_SCHEMA_VERSION,
  );
  if (buildHistory.length !== before) saveBuildHistory();
}

export function pushBuildHistoryEntry(entry) {
  loadBuildHistory();
  buildHistory.unshift(entry);
  if (buildHistory.length > BUILD_HISTORY_MAX)
    buildHistory = buildHistory.slice(0, BUILD_HISTORY_MAX);
  saveBuildHistory();
  lastBuildCompare = buildHistory[0];
}

export function buildHistoryProvenance(preflight) {
  preflight = preflight || buildPreflight || {};
  const snapshot = preflight.snapshot || {};
  const input = snapshot.input_fingerprint || {};
  return {
    schema: snapshot.schema || preflight.snapshot_schema || "",
    build_id: snapshot.build_id || "",
    code_version: snapshot.version || "",
    pricing_mode: preflight.pricing_mode || "",
    pricing_status: preflight.pricing_status || "",
    input_fingerprint: input.sha256 || "",
    workbook_fingerprint: artifactHashFromPreflight(
      preflight,
      "retirement_plan.xlsx",
    ),
    results_model_fingerprint: artifactHashFromPreflight(
      preflight,
      "results_explorer_model.json",
    ),
  };
}
Object.assign(window, {
  buildHistoryProvenance, currentKpi, deriveAfterTaxTerminalNw, firstFinite, fmtDelta, fmtPctDelta,
  loadBuildHistory, pushBuildHistoryEntry,
});
