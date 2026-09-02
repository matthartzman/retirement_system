/* Build History & "What the Model Heard": the saved build-history list (view,
   revert, delete an entry, provenance badges) and the latest-build impact
   summary (before/after KPI dials, the plain-language narrative, the
   per-field "what changed" breakdown, and the follow-up suggestions) --
   extracted from dashboard.js by tools/js_codemod/extract_module.mjs.

   Fourth domain cluster of the Wave 6.4 domain-module split (see
   docs/superpowers/specs/2026-08-10-dashboard-js-split-codemod-design.md),
   after dashboard_decomp_assets_other.js,
   dashboard_decomp_spending_taxonomy.js and
   dashboard_decomp_housing_scenarios.js. Selected as a connected component of
   dashboard.js's internal call graph (tools/js_codemod/find_clusters.mjs),
   re-run against the current file rather than trusting the previous report --
   every extraction changes the graph for the next one.

   The build-history list and the impact summary arrive as ONE component
   rather than two because reverting is defined in terms of the comparison:
   the history entry stores the before/after snapshot the impact cards render,
   and both sides share the source-step jump links and the money/percent
   formatters (mhBool, mhPct, mhMoney, mhText, mhOnOff, mhRow). Splitting them
   would have put a cross-module edge through the middle of that.

   Loaded BEFORE dashboard.js, in the same position as the other extracted
   modules -- not after them with the leaves. dashboard.js ends its module body
   with a queueMicrotask() that schedules the real boot work, and a microtask
   checkpoint runs after that script's evaluation, so it can fire before a
   LATER module script has evaluated. This module's own top level is nothing
   but declarations and one Object.assign, so it has no evaluation-time
   dependency on dashboard.js and is safe to run first. (Confirmed this matters
   here specifically: dashboard_decomp_row_model.js calls
   buildHistoryEntryHtml/latestBuildImpactHtml from inside its own render
   functions -- not at its own module top level -- so by the time those calls
   actually happen the window bridge below has already been installed.)

   No constant tables moved with this cluster. BUILD_HISTORY_LS_KEY, which
   this cluster reads, stays in dashboard.js behind its generated accessor:
   dashboard_decomp_row_model.js reads it too, so it is shared state and the
   codemod's variable safety rule refused it by name rather than letting the
   split quietly break it.

   What this module still reaches back into dashboard.js for, enumerated with
   tools/js_codemod/cluster_deps.mjs against the moved declarations' own text,
   so this list is exhaustive as of this pass rather than illustrative:

     - the function renderMain (a reassigned monkey-patch chain, exposed via a
       get accessor, so a bare call here gets the live decorated
       implementation);

     - four WRITTEN state variables -- activeStep, buildHistory, lastBuildOk,
       lastBuildCompare. All are `let` in dashboard.js and all get set
       accessors from convert_dashboard.mjs. The bare assignments from inside
       this module are legal despite module strict mode precisely because the
       bridge has already defined those properties on window: strict mode only
       throws for an identifier that resolves to nothing at all. Remove one of
       those setters and that assignment starts throwing at call time, which
       no static check in this pipeline catches;

     - six read-only bindings -- BUILD_HISTORY_LS_KEY, dirty, planSource,
       rows, sessionChanges, sessionSpecialChanges. The last three are read
       through their existing get accessor and mutated in place with .clear()
       or .add(), never reassigned, so they need no setter.

     - loadBuildHistory(), which the row-model extraction already moved to
       dashboard_decomp_row_model.js and bridged onto window -- a cross-module
       reference resolved the same way, not a new dependency this pass
       introduces. */

export function saveBuildHistory() {
  try {
    localStorage.setItem(BUILD_HISTORY_LS_KEY, JSON.stringify(buildHistory));
  } catch (_e) {}
}

export function shortHash(v) {
  v = String(v || "").trim();
  return v ? v.slice(0, 12) : "";
}

export function buildHistoryProvenanceHtml(entry) {
  const p = (entry && entry.provenance) || {};
  const chips = [];
  const pricing = [p.pricing_mode, p.pricing_status]
    .filter(Boolean)
    .join(" / ");
  if (pricing) chips.push(["Pricing", pricing]);
  if (p.input_fingerprint)
    chips.push(["Input", shortHash(p.input_fingerprint)]);
  if (p.workbook_fingerprint)
    chips.push(["Workbook", shortHash(p.workbook_fingerprint)]);
  if (p.results_model_fingerprint)
    chips.push(["Results", shortHash(p.results_model_fingerprint)]);
  if (p.code_version) chips.push(["Version", p.code_version]);
  if (!chips.length) return "";
  return (
    '<div class="build-history-provenance" aria-label="Build provenance">' +
    chips
      .map(
        ([k, v]) =>
          '<span title="' +
          esc(k + ": " + v) +
          '"><b>' +
          esc(k) +
          "</b> " +
          esc(v) +
          "</span>",
      )
      .join("") +
    "</div>"
  );
}

// A change's row_index is only a positional offset into the current CSV
// files -- it is recomputed fresh on every read, not a stable id (see
// _client_csv_rows in app_core.py). Any row added or removed anywhere in
// the plan data between when a snapshot was taken and now shifts every
// row_index downstream of it, so blindly replaying a snapshot's stored
// row_index values can write a stale value into a completely different
// field (wrong type/section), which is what made revert fail with
// "Plan Data validation failed" (#297). Re-resolve each change's current
// row_index by its stable (section, subsection, label) identity instead.
export function resolveCurrentRowIndex(rowsList, c) {
  const row = (rowsList || []).find(
    (r) =>
      (r.section || "") === (c.section || "") &&
      (r.subsection || "") === (c.subsection || "") &&
      (r.label || "") === (c.rawLabel || ""),
  );
  return row ? row.row_index : null;
}

export async function revertToBuildHistoryEntry(id) {
  loadBuildHistory();
  const entry = buildHistory.find((e) => e.id === id);
  if (!entry) {
    showMessage("Snapshot not found.", "error");
    return;
  }
  if (
    !(await showInAppConfirm(
      "Tracked field changes will be restored to their before-values from this snapshot.",
      { title: "Revert to Snapshot", confirmLabel: "Revert", variant: "warn" },
    ))
  )
    return;
  const trackedChanges = (entry.changes || []).filter(
    (c) => !c.special && c.row_index !== undefined,
  );
  if (!trackedChanges.length) {
    showMessage("No tracked field changes to revert in this snapshot.", "warn");
    return;
  }
  const resolved = trackedChanges.map((c) => ({
    change: c,
    row_index: resolveCurrentRowIndex(rows, c),
  }));
  const stale = resolved.filter((r) => r.row_index == null);
  const changes = resolved.filter((r) => r.row_index != null);
  if (!changes.length) {
    showMessage(
      "None of this snapshot's tracked fields could be located in the current plan data (they may have been removed since).",
      "error",
    );
    return;
  }
  try {
    const updates = changes.map(({ change: c, row_index }) => ({
      row_index,
      value: String(
        c.beforeStorage != null
          ? c.beforeStorage
          : c.before != null
            ? c.before
            : "",
      ),
    }));
    await api("/api/config/rows", {
      method: "POST",
      body: JSON.stringify({ updates, sync: false }),
    });
    await syncBackends();
    dirty.clear();
    sessionChanges.clear();
    sessionSpecialChanges.clear();
    lastBuildCompare = null;
    lastBuildOk = false;
    await loadAll({ source: planSource, preferLocal: false, silent: true });
    activeStep = "build_impact";
    renderMain();
    if (stale.length) {
      showMessage(
        `Reverted ${changes.length} field(s); ${stale.length} field(s) from this snapshot no longer exist and were skipped. Save Changes to persist.`,
        "warn",
      );
    } else {
      showMessage("Reverted to snapshot state. Save Changes to persist.");
    }
  } catch (e) {
    const detail =
      e && Array.isArray(e.errors) && e.errors.length
        ? " (" + e.errors.slice(0, 3).join("; ") + ")"
        : "";
    showMessage("Error reverting to snapshot: " + e.message + detail, "error");
  }
}

export function buildKpiDial(label, value, heatFn, fmtFn) {
  const hasVal =
    value !== null && value !== undefined && Number.isFinite(Number(value));
  const heat = hasVal ? Math.max(0, Math.min(1, heatFn(Number(value)))) : null;
  const color =
    heat !== null ? "hsl(" + Math.round(heat * 120) + ",70%,40%)" + "" : "#999";
  const r = 28,
    circ = Math.round(2 * Math.PI * r);
  const dash = heat !== null ? Math.round((1 - heat) * circ) : circ;
  const svg =
    '<svg width="72" height="72" viewBox="0 0 72 72"><circle cx="36" cy="36" r="' +
    r +
    '" fill="none" stroke="#e0e0e0" stroke-width="8"/><circle cx="36" cy="36" r="' +
    r +
    '" fill="none" stroke="' +
    color +
    '" stroke-width="8" stroke-dasharray="' +
    circ +
    '" stroke-dashoffset="' +
    dash +
    '" transform="rotate(-90 36 36)" stroke-linecap="round"/><text x="36" y="40" text-anchor="middle" font-size="9" fill="' +
    color +
    '" font-weight="bold">' +
    esc(hasVal ? fmtFn(Number(value)).slice(0, 8) : "N/A") +
    "</text></svg>";
  return (
    '<div class="kpi-dial">' +
    svg +
    '<div class="kpi-dial-label">' +
    esc(label) +
    "</div></div>"
  );
}

// #293/#309: the four dials mirror the four Build Impact cards -- LCV, NPV
// of Future Taxes, Worst-Case Ending Wealth (5th %ile), and EFTR -- instead
// of the retired Post-Tax Inheritance / Lifetime Tax / Success % trio. The
// heat functions (nwHeat/taxHeat/mcHeat/eftrHeat) were already re-keyed to
// these fields in dashboard_decomp_row_model.js; this is the matching fix
// for the dial VALUES and LABELS themselves, which had been left reading
// the old fields even though their color mapping was already on the new
// ones.
export function buildHistoryEntryHtml(entry, isCurrent, heat) {
  const kpi = entry.kpi || {};
  const nwDial = buildKpiDial(
    "Expected After-Tax LCV",
    kpi.lcv,
    heat.nwHeat,
    fmtMoney,
  );
  const taxDial = buildKpiDial(
    "NPV of Future Taxes",
    kpi.npv_future_taxes,
    heat.taxHeat,
    fmtMoney,
  );
  const mcDial = buildKpiDial(
    "Worst-Case Ending Wealth",
    kpi.terminal_nw_mc_p5,
    heat.mcHeat,
    fmtMoney,
  );
  const eftrDial = buildKpiDial(
    "Effective Future Tax Rate",
    kpi.eftr,
    heat.eftrHeat,
    function (v) {
      return fmtPct(v * 100);
    },
  );
  const badge = entry.isSnapshot
    ? '<span class="badge">Snapshot</span>'
    : '<span class="badge good">Build</span>';
  const currentBadge = isCurrent
    ? '<span class="badge primary">Latest</span>'
    : "";
  const elapsed = entry.elapsed ? " · " + esc(entry.elapsed) : "";
  const changesHtml =
    entry.changes && entry.changes.length
      ? buildChangeSummaryHtml(entry.changes)
      : '<p class="small">No user field changes recorded in this entry.</p>';
  const revertBtn = !isCurrent
    ? '<button class="btn" type="button" data-requires-app="1" onclick="revertToBuildHistoryEntry(\'' +
      escJs(entry.id || "") +
      "')\" >Revert to this snapshot</button>"
    : "";
  const deleteBtn =
    '<button class="btn danger-link" type="button" onclick="deleteBuildHistoryEntry(\'' +
    escJs(entry.id || "") +
    "')\" >Delete</button>";
  const actionsHtml =
    revertBtn || deleteBtn
      ? '<div class="build-history-actions">' + revertBtn + deleteBtn + "</div>"
      : "";
  return (
    '<div class="build-history-entry' +
    (isCurrent ? " current" : "") +
    '"><div class="build-history-header"><span class="build-history-label">' +
    esc(entry.label || "") +
    " " +
    badge +
    " " +
    currentBadge +
    '</span><span class="build-history-ts small">' +
    esc(new Date(entry.timestamp).toLocaleString()) +
    elapsed +
    '</span></div><div class="build-history-dials">' +
    nwDial +
    taxDial +
    mcDial +
    eftrDial +
    "</div>" +
    buildHistoryProvenanceHtml(entry) +
    "<details><summary>Changes in this entry</summary>" +
    changesHtml +
    "</details>" +
    actionsHtml +
    "</div>"
  );
}

export async function deleteBuildHistoryEntry(id) {
  if (
    !(await showInAppConfirm("This cannot be undone.", {
      title: "Delete Build History Entry",
      confirmLabel: "Delete",
      variant: "danger",
    }))
  )
    return;
  loadBuildHistory();
  buildHistory = buildHistory.filter(function (e) {
    return e.id !== id;
  });
  saveBuildHistory();
  if (lastBuildCompare && lastBuildCompare.id === id)
    lastBuildCompare = buildHistory[0] || null;
  renderMain();
}

export function sourceStepForSpecialLabel(label) {
  const l = norm(label);
  if (l.includes("holding")) return "holdings";
  if (l.includes("liabil")) return "assets_home_cash";
  if (l.includes("large_discretionary") || l.includes("travel_extras"))
    return "spending_travel_extras";
  if (l.includes("liquidity")) return "assets_home_cash";
  if (l.includes("forced_conversion")) return "roth_conversion";
  if (l.includes("transaction") || l.includes("account"))
    return "ytd_transactions";
  if (l.includes("budget") || l.includes("category") || l.includes("spending"))
    return "spending_core";
  return "all_assumptions";
}

export function buildSourceJumpHtml(stepId, label) {
  if (!stepId) return "";
  const title = stepTitleById(stepId);
  return `<button class="btn tiny build-source-jump" type="button" data-step-id="${esc(stepId)}" title="Open source page: ${esc(title)}">${esc(label || title)}</button>`;
}

export function buildChangeSummaryHtml(changes) {
  const all = Array.isArray(changes) ? changes : capturedSessionChanges();
  if (!all.length)
    return '<p class="small">No user UI edits were captured before this build.</p>';
  const scenarioOnly = all.filter((c) =>
    String(c.scope || "")
      .toLowerCase()
      .includes("scenario analysis"),
  );
  let html = scenarioOnly.length
    ? `<div class="section-note warning"><b>${scenarioOnly.length} scenario-only change${scenarioOnly.length === 1 ? "" : "s"} captured.</b> These values are used in the workbook Scenario Analysis sheet but do not move the headline Build Impact cards unless the matching base-plan input is also changed.</div>`
    : "";
  html +=
    '<table class="change-table"><thead><tr><th>Factor</th><th>Source page</th><th>Before</th><th>After</th></tr></thead><tbody>';
  all.slice(0, 25).forEach((c) => {
    const source = c.sourceStep
      ? buildSourceJumpHtml(
          c.sourceStep,
          c.sourceTitle || stepTitleById(c.sourceStep),
        )
      : "";
    html += `<tr><td><div class="change-factor">${esc(c.label)}</div>${c.group ? `<div class="change-context">${esc(c.group)}${c.scope ? ` · ${esc(c.scope)}` : ""}</div>` : ""}</td><td>${source || esc(c.group || "—")}</td><td>${esc(c.before || "blank")}</td><td>${esc(c.after || "blank")}</td></tr>`;
  });
  if (all.length > 25)
    html += `<tr><td colspan="4" class="small">${all.length - 25} more user change${all.length - 25 === 1 ? "" : "s"} captured.</td></tr>`;
  html += "</tbody></table>";
  return html;
}

export function impactCardHtml(
  title,
  delta,
  beforeVal,
  afterVal,
  valueFormatter,
  help,
  deltaFormatter = fmtDelta,
  invert = false,
) {
  const headline = Number.isFinite(Number(delta))
    ? deltaFormatter(delta)
    : Number.isFinite(Number(afterVal))
      ? valueFormatter(afterVal)
      : "Not available";
  const headlineLabel = Number.isFinite(Number(delta))
    ? "Change"
    : "Current build";
  const hNeg = Number.isFinite(Number(delta))
    ? Number(delta) < 0
    : Number(afterVal) < 0;
  const bNeg = Number(beforeVal) < 0,
    aNeg = Number(afterVal) < 0;
  // #233: headline goes green when it moved the good direction, red when it
  // moved the bad direction, and stays neutral (black) at zero/unavailable.
  // `invert` flips which direction is "good" (e.g. Lifetime Taxes: down is good).
  const dNum = Number(delta);
  let headlineColorClass = "";
  if (Number.isFinite(dNum) && dNum !== 0) {
    const isGood = invert ? dNum < 0 : dNum > 0;
    headlineColorClass = isGood ? "positive-money" : "negative-money";
  }
  const infoIcon = help
    ? ` <sup class="field-info-i" tabindex="0" title="${esc(help)}" aria-label="More info: ${esc(help)}">i</sup>`
    : "";
  return `<div class="impact-card"><span>${esc(title)}${infoIcon}</span><b class="${headlineColorClass}">${headline}</b><div class="impact-headline-label">${headlineLabel}</div><div class="impact-row"><span>Before</span><strong class="${bNeg ? "negative-money" : ""}">${valueFormatter(beforeVal)}</strong></div><div class="impact-row"><span>After</span><strong class="${aNeg ? "negative-money" : ""}">${valueFormatter(afterVal)}</strong></div></div>`;
}

// #293: the three headline cards report Expected After-Tax Lifetime
// Consumption-and-Transfer Value (LCV), NPV of Future Taxes, and Worst-Case
// Ending Wealth (5th percentile Monte Carlo outcome) -- replacing raw
// Terminal Net Worth, nominal Lifetime Taxes, and Probability of Success.
export function buildImpactCardsHtml(before, after) {
  const dLcv =
    Number.isFinite(after.lcv) && Number.isFinite(before.lcv)
      ? after.lcv - before.lcv
      : null;
  const dNpvTax =
    Number.isFinite(after.npv_future_taxes) && Number.isFinite(before.npv_future_taxes)
      ? after.npv_future_taxes - before.npv_future_taxes
      : null;
  const dP5 =
    Number.isFinite(after.terminal_nw_mc_p5) && Number.isFinite(before.terminal_nw_mc_p5)
      ? after.terminal_nw_mc_p5 - before.terminal_nw_mc_p5
      : null;
  const worstCaseCard =
    Number.isFinite(after.terminal_nw_mc_p5) || Number.isFinite(before.terminal_nw_mc_p5)
      ? impactCardHtml(
          // #309: dropped the "(5th %ile)" suffix from the visible card
          // title -- at card width, "Worst-Case Ending Wealth (5th %ile)"
          // was the one label of the four that still wrapped to 2 lines
          // even after the general font/padding shrink below. The tooltip
          // (help text below) already states "5th-percentile" in full.
          "Worst-Case Ending Wealth",
          dP5,
          before.terminal_nw_mc_p5,
          after.terminal_nw_mc_p5,
          fmtMoney,
          "The 5th-percentile ending net worth across Monte Carlo simulation paths -- what the plan leaves even in a bad-market scenario, without collapsing risk into a single pass/fail probability.",
          fmtDelta,
        )
      : `<div class="impact-card"><span>Worst-Case Ending Wealth</span><b>Not available</b><div class="small">Monte Carlo results were not available for this comparison.</div></div>`;
  // #225: Post-Tax Inheritance was shown as its own headline card here AND
  // separately on Estate & Legacy Plan, computed at a different point in the
  // timeline (terminal plan year here vs. second-death year there) -- the two
  // numbers legitimately differ and showing both as equivalent headline
  // figures reads as a bug. Keep PTI as the Estate & Legacy Plan's own
  // number; here, only note the estate-tax bite baked into LCV's terminal
  // component, and only when it's actually nonzero.
  const afterEstateTax = Number.isFinite(after.after_tax_terminal_nw) && Number.isFinite(after.post_tax_inheritance)
    ? after.after_tax_terminal_nw - after.post_tax_inheritance
    : null;
  const estateTaxNote =
    afterEstateTax !== null && Math.abs(afterEstateTax) > 0.5
      ? `<div class="small">LCV's terminal-transfer component is already net of estate tax (${fmtMoney(afterEstateTax)} reduced to ${fmtMoney(after.post_tax_inheritance)} for heirs). See Estate &amp; Legacy Plan for the figure at second death.</div>`
      : "";
  const lcvCard = impactCardHtml("Expected After-Tax LCV", dLcv, before.lcv, after.lcv, fmtMoney, "Lifetime Consumption-and-Transfer Value: total spending across the plan plus the after-tax, after-estate-tax terminal transfer to heirs (Post-Tax Inheritance) -- the household's total expected financial welfare, not just what's left at the end.");
  // #293: Effective Future Tax Rate (EFTR) -- an added 4th stat, not a
  // dial-replacement like the three above. Already computed by
  // compute_future_lcv_and_eftr (total future tax / total future gross cash
  // flow, current year through plan end); this card just surfaces it here.
  const dEftr =
    Number.isFinite(after.eftr) && Number.isFinite(before.eftr)
      ? (after.eftr - before.eftr) * 100
      : null;
  const eftrBefore = Number.isFinite(before.eftr) ? before.eftr * 100 : before.eftr;
  const eftrAfter = Number.isFinite(after.eftr) ? after.eftr * 100 : after.eftr;
  const eftrCard =
    Number.isFinite(eftrAfter) || Number.isFinite(eftrBefore)
      ? impactCardHtml(
          "Effective Future Tax Rate (EFTR)",
          dEftr,
          eftrBefore,
          eftrAfter,
          fmtPct,
          "Total future taxes divided by total future gross cash flow, from the current year through the end of the plan -- the household's blended tax burden on every dollar that flows through the plan from here on.",
          fmtPctDelta,
          true,
        )
      : "";
  const notes = [estateTaxNote].filter(Boolean).join("");
  const notesHtml = notes ? `<div class="impact-notes">${notes}</div>` : "";
  return `<div class="impact-grid">${lcvCard} ${impactCardHtml("NPV of Future Taxes", dNpvTax, before.npv_future_taxes, after.npv_future_taxes, fmtMoney, "Total taxes paid, discounted to today's dollars at the plan's assumed portfolio return rate -- an apples-to-apples way to compare an early Roth conversion against a late RMD.", fmtDelta, true)} ${worstCaseCard} ${eftrCard}</div>${notesHtml}`;
}

export function impactDirectionWord(delta, kind) {
  if (!Number.isFinite(Number(delta))) return "stayed hard to quantify";
  const d = Number(delta);
  if (Math.abs(d) < 0.000001) return "held flat";
  if (kind === "tax") return d > 0 ? "increased" : "decreased";
  return d > 0 ? "improved" : "declined";
}

export function buildImpactSourceLinksHtml(changes) {
  const byStep = new Map();
  (changes || []).forEach((c) => {
    const step = c.sourceStep || sourceStepForSpecialLabel(c.label || "");
    if (!step) return;
    const rec = byStep.get(step) || {
      title: c.sourceTitle || stepTitleById(step),
      count: 0,
      labels: [],
    };
    rec.count += 1;
    if (c.label && rec.labels.length < 3) rec.labels.push(c.label);
    byStep.set(step, rec);
  });
  if (!byStep.size)
    return '<p class="small">No source-page links were captured for this build.</p>';
  const items = [...byStep.entries()]
    .slice(0, 8)
    .map(
      ([step, rec]) =>
        `<li>${buildSourceJumpHtml(step, rec.title)}<span>${rec.count} captured change${rec.count === 1 ? "" : "s"}${rec.labels.length ? `: ${rec.labels.map(esc).join(", ")}` : ""}</span></li>`,
    )
    .join("");
  return `<ul class="build-impact-source-list">${items}</ul>`;
}

// #293: narrative points reference LCV / NPV of Future Taxes / Worst-Case
// (5th %ile) Ending Wealth instead of raw terminal net worth, nominal
// lifetime tax, and Monte Carlo pass/fail probability.
export function buildImpactNarrativeHtml(entry) {
  entry = entry || {};
  const before = currentKpi(entry.before || {}),
    after = currentKpi(entry.after || {});
  const dLcv =
    Number.isFinite(after.lcv) && Number.isFinite(before.lcv)
      ? after.lcv - before.lcv
      : null;
  const dNpvTax =
    Number.isFinite(after.npv_future_taxes) && Number.isFinite(before.npv_future_taxes)
      ? after.npv_future_taxes - before.npv_future_taxes
      : null;
  const dAfterTax =
    Number.isFinite(after.after_tax_terminal_nw) &&
    Number.isFinite(before.after_tax_terminal_nw)
      ? after.after_tax_terminal_nw - before.after_tax_terminal_nw
      : null;
  const dP5 =
    Number.isFinite(after.terminal_nw_mc_p5) && Number.isFinite(before.terminal_nw_mc_p5)
      ? after.terminal_nw_mc_p5 - before.terminal_nw_mc_p5
      : null;
  const changed = (entry.changes || []).length,
    adminChanged = (entry.admin_changes || []).length;
  let lead =
    "This build compared the saved plan before the last edit batch with the latest successful output package.";
  if (changed || adminChanged)
    lead = `This build compared ${changed} user input change${changed === 1 ? "" : "s"}${adminChanged ? ` plus ${adminChanged} admin/config event${adminChanged === 1 ? "" : "s"}` : ""} against the session baseline.`;
  const points = [];
  if (Number.isFinite(dLcv))
    points.push(
      `Expected After-Tax LCV ${impactDirectionWord(dLcv)} by ${fmtDelta(dLcv)}.`,
    );
  if (Number.isFinite(dAfterTax))
    points.push(
      `Post-Tax Inheritance ${impactDirectionWord(dAfterTax)} by ${fmtDelta(dAfterTax)}.`,
    );
  if (Number.isFinite(dNpvTax))
    points.push(
      `NPV of future taxes ${impactDirectionWord(dNpvTax, "tax")} by ${fmtDelta(dNpvTax)}.`,
    );
  if (Number.isFinite(dP5))
    points.push(
      `Worst-case (5th percentile) ending wealth ${impactDirectionWord(dP5)} by ${fmtDelta(dP5)}.`,
    );
  if (!points.length)
    points.push(
      "The latest summary did not contain enough before/after KPIs to calculate a numeric impact. Use the source links below to review what changed, then rebuild from a saved snapshot.",
    );
  let riskNote =
    "Use the source links below to inspect the inputs behind the measured changes before accepting the build as the new baseline.";
  if (Number.isFinite(dP5) && dP5 < 0)
    riskNote =
      "Worst-case ending wealth moved down, so treat a higher LCV or lower tax result as tentative until you recover bear-market durability or explicitly accept more downside risk.";
  else if (
    Number.isFinite(dNpvTax) &&
    dNpvTax > 0 &&
    Number.isFinite(dAfterTax) &&
    dAfterTax > 0
  )
    riskNote =
      "The NPV of future taxes rose, but after-tax inheritance also improved; review allocation or income timing sources to confirm the tradeoff was intentional.";
  else if (Number.isFinite(dAfterTax) && dAfterTax < 0)
    riskNote =
      "After-tax inheritance fell; start with the largest source-page change and test one rollback or lever at a time.";
  return `<div class="impact-narrative"><h4>Plain-English Build Impact summary</h4><p>${esc(lead)}</p><ul>${points.map((p) => `<li>${esc(p)}</li>`).join("")}</ul><p class="small"><b>Next check:</b> ${esc(riskNote)}</p><h4>Source-page links</h4>${buildImpactSourceLinksHtml(entry.changes || [])}</div>`;
}

export function latestBuildImpactHtml(entry) {
  if (!entry || entry.isSnapshot) return "";
  const before = currentKpi(entry.before || {}),
    after = currentKpi(entry.after || {});
  return `<div class="latest-build-impact"><h3>Latest Build Impact</h3>${buildImpactNarrativeHtml(entry)}${buildImpactCardsHtml(before, after)}${buildImpactSuggestionsHtml(before, after, entry.after || {})}${modelHeardHtml(entry.after || {})}<details><summary>Input and configuration changes</summary>${window.unifiedBuildChangeSummaryHtml(entry.changes || [], entry.admin_changes || [])}</details></div>`;
}

export function mhBool(v) {
  return (
    v === true ||
    String(v).toLowerCase() === "true" ||
    String(v).toLowerCase() === "yes" ||
    String(v) === "1"
  );
}

export function mhPct(v) {
  const n = Number(v);
  if (!Number.isFinite(n)) return "not set";
  const pct = Math.abs(n) <= 1 ? n * 100 : n;
  return pct.toLocaleString(undefined, { maximumFractionDigits: 2 }) + "%";
}

export function mhMoney(v) {
  const n = Number(v);
  if (!Number.isFinite(n)) return "not set";
  return n.toLocaleString(undefined, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  });
}

export function mhText(v, fallback = "not set") {
  if (v === undefined || v === null || v === "") return fallback;
  return String(v);
}

export function mhOnOff(v) {
  return mhBool(v) ? "On" : "Off";
}

export function mhRow(title, impact, action, detail) {
  return `<li><b>${esc(title)}</b><span>${esc(impact)}<br><em>Action:</em> ${esc(action)}${detail ? `<br><span class="small">${esc(detail)}</span>` : ""}</span></li>`;
}

export function modelHeardHtml(summary) {
  const h = (summary && summary.model_heard_assumptions) || {};
  if (!Object.keys(h).length) return "";
  const ss = h.social_security || {},
    home = h.home_and_property_tax || {},
    hc = h.healthcare || {},
    taxable = h.taxable_income || {},
    roth = h.roth_and_irmaa || {},
    estate = h.tax_and_estate || {},
    mc = h.monte_carlo || {},
    alloc = h.allocation || {},
    rep = h.reporting || {};
  const rows = [];
  if (h.plan_years) {
    rows.push(
      mhRow(
        "Time horizon",
        "The model projected the plan over " +
          mhText(h.plan_years) +
          ". A wrong start or end year shifts every income, tax, spending, and estate calculation.",
        "Verify the plan years match the horizon you intend to compare before interpreting terminal net worth.",
      ),
    );
  }
  rows.push(
    mhRow(
      "Social Security income",
      "The build used " +
        personDisplayName(1) +
        " claim age " +
        mhText(ss.husband_claim_age) +
        " and " +
        personDisplayName(2) +
        " claim age " +
        mhText(ss.wife_claim_age) +
        ". Benefits are reduced by " +
        mhPct(ss.funding_discount_pct) +
        " starting in " +
        mhText(ss.funding_discount_year) +
        " for the funding-shortfall stress.",
      "To isolate this drag, set Social Security funding discount percent to 0%, rebuild, and compare terminal net worth and withdrawal needs.",
      `PIA inputs: ${mhOnOff(ss.uses_pia)}; spousal benefits: ${mhOnOff(ss.spousal_benefits_enabled)}; survivor uses deceased claim age: ${mhOnOff(ss.survivor_uses_deceased_claim_age)}.`,
    ),
  );
  rows.push(
    mhRow(
      "Home sale and real-estate tax",
      "The base projection heard annual real estate taxes of " +
        mhMoney(home.annual_real_estate_taxes_today) +
        " growing at " +
        mhPct(home.real_estate_tax_growth_rate) +
        ". Current Home Value is " +
        mhMoney(home.current_home_value) +
        ". Base Plan Home Sale Year is " +
        mhText(home.base_home_sale_year, "0") +
        " with canonical Home Basis " +
        mhMoney(home.canonical_home_basis) +
        ".",
      "If property tax or base home sale year changed but headline impact did not move, confirm these heard values changed. Scenario-only Sell Home year affects the Scenario Analysis sheet, not the headline Build Impact cards.",
      `Sell Home stress-test year: ${mhText(home.sell_home_stress_year, "0")}; stress basis source: ${mhText(home.sell_home_stress_basis_source)}.`,
    ),
  );
  rows.push(
    mhRow(
      "healthcare cash flow",
      "The model is spending healthcare and healthcare costs instead of treating those fields as notes: ACA bridge premiums " +
        mhMoney(
          hc.bridge_premium_monthly_today ||
            (Number(hc.bridge_premium_today) || 0) / 12,
        ) +
        " per covered person per month today, Medicare B/D/G " +
        mhMoney(
          (Number(hc.part_b_monthly_today) || 0) +
            (Number(hc.part_d_monthly_today) || 0) +
            (Number(hc.part_g_monthly_today) || 0),
        ) +
        " per person per month today, and medical OOP cap/reference " +
        mhMoney(hc.oop_estimate_today) +
        ".",
      "If recent terminal net worth fell, test healthcare premium and medical-spending impact by temporarily setting bridge, Medicare, and non-premium medical assumptions to zero, then restore realistic values.",
      `ACA premium tax credit: ${mhOnOff(hc.aca_ptc_enabled)}; benchmark premium today: ${mhMoney(hc.aca_benchmark_premium_today)}; OOP cap utilization: ${mhPct(hc.oop_utilization_pct)}.`,
    ),
  );
  rows.push(
    mhRow(
      "Taxable portfolio income",
      "Taxable holdings now create annual dividends/interest using " +
        mhText(taxable.portfolio_distributions_mode) +
        ". This can raise AGI, Social Security taxation, IRMAA, NIIT, and reduce Roth-conversion room.",
      "If taxes jumped, review taxable account asset location and the admin capital-market distribution-yield assumptions before changing spending assumptions.",
      `Tax-exempt interest included in MAGI/provisional income: ${mhOnOff(taxable.tax_exempt_interest_in_magi)}. Gain mode: ${mhText(taxable.trust_gain_mode)}.`,
    ),
  );
  rows.push(
    mhRow(
      "Estate and survivor treatment",
      "The build used survivor filing status (Qualifying Surviving Spouse, QSS), basis step-up, federal portability, and credit-shelter trust (CST) settings when calculating survivor cash flow and terminal estate values. Credit-shelter trust funded/excluded amount shown by the last projection year is " +
        mhMoney(estate.cst_funded_total) +
        ".",
      "If terminal net worth or after-tax estate changed sharply, compare one rebuild with the credit-shelter trust disabled or estate objective off, then restore the estate plan settings.",
      `Basis step-up: ${mhOnOff(estate.basis_step_up_at_death)} (${mhText(estate.basis_step_up_property_regime)}); credit-shelter trust (CST): ${mhOnOff(estate.credit_shelter_trust_enabled)}; federal portability: ${mhOnOff(estate.federal_portability_enabled)}.`,
    ),
  );
  if (mc.engine_mode || mc.simulation_count) {
    rows.push(
      mhRow(
        "Monte Carlo risk mode",
        "The risk comparison used " +
          mhText(mc.engine_mode) +
          " Monte Carlo with " +
          mhText(mc.simulation_count) +
          " main paths and " +
          mhText(mc.sensitivity_simulation_count) +
          " sensitivity paths. Exact scalar is slower but more tax-faithful.",
        "For interactive work use moderate path counts; for final advisor review raise simulations and max_build_seconds, then rebuild once.",
        "If the build appears slow, lower path counts or increase System Configuration → Build timeout.",
      ),
    );
  }
  rows.push(
    mhRow(
      "Allocation and real-dollar reporting",
      "The allocation source is " +
        mhText(alloc.selection_mode) +
        ". Today-dollar output rows are " +
        mhOnOff(rep.real_dollar_rows_available) +
        " using " +
        mhText(rep.real_dollar_base_year) +
        " as the base year.",
      "Use real-dollar outputs when judging purchasing power; use nominal terminal net worth only when comparing like-for-like workbook runs.",
    ),
  );
  const acronyms = acronymDefinitionsHtml(rows);
  return `<details class="impact-suggestions model-used-panel collapsible-impact-section"><summary class="collapsible-summary"><span class="collapse-caret" aria-hidden="true"></span><span class="collapsible-title">What the model used in this build</span><span class="small collapsible-meta">${rows.length} impact checks</span></summary><div class="collapsible-content"><p class="small">Plain-English checks for assumptions that materially change cash flow, taxes, risk, and terminal net worth. These are not extra recommendations; they explain which model switches were actually consumed so you can run targeted what-if tests.</p><ol>${rows.join("")}</ol>${acronyms}</div></details>`;
}

// #293/#309: keyed to the plan's headline KPIs (LCV, NPV of Future Taxes,
// Worst-Case Ending Wealth 5th %ile) instead of the retired Terminal Net
// Worth / Lifetime Taxes / Probability of Success trio -- this section was
// missed when those cards were converted, so it kept generating suggestions
// in the old language even though before/after already carry the new
// fields (dashboard.js/dashboard_decomp_row_model.js's kpi:{...} builders).
export function buildImpactSuggestionsHtml(before, after, summary = {}) {
  const dLcv =
    Number.isFinite(after.lcv) && Number.isFinite(before.lcv)
      ? after.lcv - before.lcv
      : null;
  const dTax =
    Number.isFinite(after.npv_future_taxes) && Number.isFinite(before.npv_future_taxes)
      ? after.npv_future_taxes - before.npv_future_taxes
      : null;
  const dWorstCase =
    Number.isFinite(after.terminal_nw_mc_p5) && Number.isFinite(before.terminal_nw_mc_p5)
      ? after.terminal_nw_mc_p5 - before.terminal_nw_mc_p5
      : null;
  const heard = (summary && summary.model_heard_assumptions) || {};
  const hc = heard.healthcare || {};
  const roth = heard.roth_and_irmaa || {};
  const mc = heard.monte_carlo || {};
  const alloc = heard.allocation || {};
  const suggestions = [];
  const add = (title, text, context) =>
    suggestions.push([title, text, context]);
  const riskAvailable =
    Number.isFinite(after.terminal_nw_mc_p5) || Number.isFinite(before.terminal_nw_mc_p5);
  const riskWorse = Number.isFinite(dWorstCase) && dWorstCase < 0;
  const riskFloor = Number.isFinite(after.terminal_nw_mc_p5)
    ? fmtMoney(after.terminal_nw_mc_p5)
    : "the current worst-case Monte Carlo result";
  if (riskWorse) {
    add(
      "Recover worst-case ending wealth before optimizing LCV",
      `This build lowered Worst-Case Ending Wealth (5th %ile) by ${fmtDelta(dWorstCase)}. Undo or offset the change before accepting any higher LCV or lower tax result.`,
      `Current risk floor: ${riskFloor}.`,
    );
  } else if (riskAvailable) {
    add(
      "Protect the current worst-case result",
      `Use ${riskFloor} as a floor when testing tax or LCV improvements; reject changes that lower it unless you intentionally accept more risk.`,
      `Before/after worst-case move: ${Number.isFinite(dWorstCase) ? fmtDelta(dWorstCase) : "not available"}.`,
    );
  } else {
    add(
      "Turn on a risk comparison",
      "Run Monte Carlo or refresh the forecast package so Build Impact can judge whether a change improves taxes or LCV without lowering the worst-case (5th percentile) outcome.",
      "No worst-case Monte Carlo result was available for this build.",
    );
  }
  if (Number.isFinite(dTax) && dTax > 0) {
    add(
      "Look for tax-neutral or tax-lowering alternatives",
      `NPV of Future Taxes increased by ${fmtDelta(dTax)}. Test Roth conversion caps, LTCG harvesting limits, and taxable-gain budgets while keeping Worst-Case Ending Wealth flat or better.`,
      `NPV of Future Taxes: ${fmtMoney(after.npv_future_taxes)}.`,
    );
  } else if (Number.isFinite(after.npv_future_taxes)) {
    add(
      "Preserve the tax result while improving the plan",
      `NPV of Future Taxes is ${fmtMoney(after.npv_future_taxes)}${Number.isFinite(dTax) ? ` (${fmtDelta(dTax)} vs. prior build)` : ""}. Keep this tax result as a constraint while testing allocation, spending, or timing changes.`,
      "Prefer tests that do not increase NPV of Future Taxes unless they also improve risk-adjusted outcomes.",
    );
  }
  if (Number.isFinite(dLcv) && dLcv < 0) {
    add(
      "Recover LCV without adding volatility",
      `Expected After-Tax LCV fell by ${fmtDelta(dLcv)}. Test lower cash drag, planned-spending timing, lower-cost ETF substitutions, or tax-aware turnover limits before increasing portfolio risk.`,
      `After-build LCV: ${fmtMoney(after.lcv)}.`,
    );
  } else if (Number.isFinite(after.lcv)) {
    add(
      "Stress-test the LCV result",
      `Expected After-Tax LCV is ${fmtMoney(after.lcv)}${Number.isFinite(dLcv) ? ` (${fmtDelta(dLcv)} vs. prior build)` : ""}. Rerun with conservative return and inflation assumptions to confirm the value did not come from added downside risk.`,
      "Keep Worst-Case Ending Wealth flat or better during this stress test.",
    );
  }
  const bridgePremium = Number(hc.bridge_premium_today || 0);
  const medMonthly =
    Number(hc.part_b_monthly_today || 0) +
    Number(hc.part_d_monthly_today || 0) +
    Number(hc.part_g_monthly_today || 0);
  if (bridgePremium > 50000 || medMonthly > 800) {
    add(
      "Audit healthcare assumptions before changing investment risk",
      `The model heard ACA bridge premiums of ${mhMoney(bridgePremium)} per year and Medicare B/D/G of ${mhMoney(medMonthly)} per person per month. Normalize these if they are placeholders before taking more allocation risk.`,
      "healthcare cash flow can dominate withdrawals and Monte Carlo success.",
    );
  }

  if (
    String(alloc.selection_mode || "")
      .toLowerCase()
      .includes("user")
  ) {
    add(
      "Run the optimizer as a controlled allocation test",
      "Allocation is currently using the user target. Try the optimizer recommendation or optimizer override with the current Monte Carlo success as the floor, then reject changes that reduce probability of success.",
      "This tests risk-adjusted return without manually increasing risk first.",
    );
  } else if (alloc.selection_mode) {
    add(
      "Compare allocation modes one at a time",
      `Allocation mode is ${mhText(alloc.selection_mode)}. Compare it to the user target with the same spending and tax settings so Build Impact isolates the allocation effect.`,
      "Do not change Roth, spending, and allocation in the same run.",
    );
  }
  add(
    "Change one practical lever at a time",
    "Change only one lever—spending, retirement date, Roth conversions, allocation target, or rebalancing limits—then rebuild so the impact cards identify the tradeoff clearly.",
    "This keeps suggestions tied to measured risk, tax, and LCV moves.",
  );
  const shown = suggestions.slice(0, 6);
  return `<details class="impact-suggestions collapsible-impact-section dynamic-suggestions-panel"><summary class="collapsible-summary"><span class="collapse-caret" aria-hidden="true"></span><span class="collapsible-title">Suggestions to improve the plan without lowering risk</span><span class="small collapsible-meta">${shown.length} dynamic tests</span></summary><div class="collapsible-content"><p class="small">These are generated from this build's LCV, NPV of Future Taxes, Worst-Case Ending Wealth (5th %ile), and model-heard assumptions. Keep Worst-Case Ending Wealth flat or better when improving LCV or lowering NPV of Future Taxes.</p><ol>${shown.map((s) => `<li><b>${esc(s[0])}</b><span>${esc(s[1])}</span>${s[2] ? `<span class="change-context">${esc(s[2])}</span>` : ""}</li>`).join("")}</ol></div></details>`;
}

// Every export above is also re-attached to window: dashboard.js calls these
// as bare globals, and this file's own rendered HTML uses inline
// onclick="..." handlers, which always resolve through window regardless of
// module scoping. New code should prefer `import` from this module; this
// bridge exists only for callers that cannot move to import in the same pass.
Object.assign(window, {
  saveBuildHistory,
  shortHash,
  buildHistoryProvenanceHtml,
  revertToBuildHistoryEntry,
  buildKpiDial,
  buildHistoryEntryHtml,
  deleteBuildHistoryEntry,
  sourceStepForSpecialLabel,
  buildSourceJumpHtml,
  buildChangeSummaryHtml,
  impactCardHtml,
  buildImpactCardsHtml,
  impactDirectionWord,
  buildImpactSourceLinksHtml,
  buildImpactNarrativeHtml,
  latestBuildImpactHtml,
  mhBool,
  mhPct,
  mhMoney,
  mhText,
  mhOnOff,
  mhRow,
  modelHeardHtml,
  buildImpactSuggestionsHtml,
});
