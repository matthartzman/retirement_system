// ── Home screen panels (Welcome page) ────────────────────────────────────
// Plan KPI metrics summary and the plan closeout checklist, both rendered
// only on the Welcome/home screen. Extracted from dashboard.js verbatim
// (first modularization increment); shares the classic-script global scope
// with dashboard.js, so these remain plain global functions/vars just as
// they were inline.

/* ── 5.1 Plan KPI metrics panel (home screen) ── */
function planKpiMetricsHtml() {
  if (!planLoaded || !kpiHasValues(lastBuildSummary)) return "";
  const k = currentKpi(lastBuildSummary);
  const heRate =
    lastBuildSummary && lastBuildSummary.success_rate_with_home_equity;
  const heEnabled =
    lastBuildSummary && lastBuildSummary.home_equity_contingency_enabled;
  let successVal = Number.isFinite(k.mc_success)
    ? fmtPct(k.mc_success * 100)
    : "—";
  if (heEnabled && Number.isFinite(Number(heRate))) {
    successVal = `${Number.isFinite(k.mc_success) ? fmtPct(k.mc_success * 100) : "—"} <span class="small" title="With home equity contingency">(+HE: ${fmtPct(Number(heRate) * 100)})</span>`;
  }
  const metrics = [
    {
      label: "Projected final portfolio",
      val: Number.isFinite(k.terminal_nw) ? fmtMoney(k.terminal_nw) : "—",
      html: false,
    },
    {
      label: "After-tax net worth",
      val: Number.isFinite(k.after_tax_terminal_nw)
        ? fmtMoney(k.after_tax_terminal_nw)
        : "—",
      html: false,
    },
    {
      label: "Probability of Success",
      val: successVal,
      html: heEnabled && Number.isFinite(Number(heRate)),
    },
    {
      label: "Lifetime taxes",
      val: Number.isFinite(k.lifetime_tax) ? fmtMoney(k.lifetime_tax) : "—",
      html: false,
    },
  ];
  const cards = metrics
    .map(
      (m) =>
        `<div class="plan-kpi-card"><div class="plan-kpi-value">${m.html ? m.val : esc(m.val)}</div><div class="plan-kpi-label">${esc(m.label)}</div></div>`,
    )
    .join("");
  return `<div class="plan-kpi-section"><div class="plan-kpi-head"><span>Last build results</span><button class="btn tiny" type="button" data-step-id="reports_and_review">View Reports &rarr;</button></div><div class="plan-kpi-grid">${cards}</div></div>`;
}

/* ── 5.8 Closeout checklist ── */
const CLOSEOUT_ITEMS = [
  {
    key: "sections_complete",
    label: "All required sections complete",
    auto: () => !!(planLoaded && !overallStats().missing.length),
  },
  {
    key: "results_reviewed",
    label: "Results reviewed (visited Results tab)",
    auto: null,
  },
  { key: "workbook_downloaded", label: "Workbook downloaded", auto: null },
  {
    key: "assumptions_confirmed",
    label: "Key assumptions confirmed (horizon, return rate, spending)",
    auto: null,
  },
];
function getCloseoutState() {
  try {
    return JSON.parse(localStorage.getItem("rpCloseoutChecks") || "{}");
  } catch (_e) {
    return {};
  }
}
function closeoutChecklistHtml() {
  if (!planLoaded) return "";
  const state = getCloseoutState();
  const finalized = !!state.plan_finalized;
  let allDone = true;
  const itemsHtml = CLOSEOUT_ITEMS.map((item) => {
    const autoDone = !!(item.auto && item.auto());
    const done = autoDone || !!state[item.key];
    if (!done) allDone = false;
    const autoNote = autoDone ? ' <span class="small">(auto)</span>' : "";
    const onChange = autoDone
      ? ""
      : ` onchange="toggleCloseoutItem('${esc(item.key)}',this.checked)"`;
    return `<label class="closeout-item${done ? " done" : ""}"><input type="checkbox"${done ? " checked" : ""}${autoDone ? " disabled" : ""}${onChange}> ${esc(item.label)}${autoNote}</label>`;
  }).join("");
  const finalBadge = finalized
    ? `<div class="plan-final-badge">Plan marked as final &#10003; &nbsp;<button class="btn tiny" type="button" onclick="clearPlanFinal()">Clear</button></div>`
    : "";
  const finalBtn =
    allDone && !finalized
      ? `<div style="margin-top:10px"><button class="btn primary" type="button" onclick="markPlanFinal()">Mark plan as final</button></div>`
      : "";
  return `<div class="closeout-checklist"><div class="closeout-head"><h3>Plan closeout checklist</h3><p class="small">Check each item when done. Advisory only — does not lock editing.</p></div>${finalBadge}<div class="closeout-items">${itemsHtml}</div>${finalBtn}</div>`;
}
function toggleCloseoutItem(key, checked) {
  try {
    const s = getCloseoutState();
    s[key] = checked;
    localStorage.setItem("rpCloseoutChecks", JSON.stringify(s));
  } catch (_e) {}
  renderMain();
}
function markPlanFinal() {
  try {
    const s = getCloseoutState();
    s.plan_finalized = true;
    localStorage.setItem("rpCloseoutChecks", JSON.stringify(s));
  } catch (_e) {}
  renderMain();
}
async function clearPlanFinal() {
  if (
    !(await showInAppConfirm("The plan can be re-finalized at any time.", {
      title: "Clear Final Marker",
      confirmLabel: "Clear",
      variant: "warn",
    }))
  )
    return;
  try {
    const s = getCloseoutState();
    delete s.plan_finalized;
    localStorage.setItem("rpCloseoutChecks", JSON.stringify(s));
  } catch (_e) {}
  renderMain();
}
