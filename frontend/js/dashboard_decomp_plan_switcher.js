// Header plan switcher (WP8.4, design F 5A): the active plan's name, the registered plans to
// switch to (POST /api/plans/switch; no plan file is copied) and, while the demo plan is active,
// a Demo badge with "Exit demo". Helpers are bare globals; loadAll() calls refreshPlanSwitcher().
let planSwitcherState = null;

export function planSwitcherHtml(state) {
  const s = state || {};
  const plans = Array.isArray(s.plans) ? s.plans : [];
  const active = s.active || plans.find((p) => p.active) || null;
  if (!active) return "";
  const options = plans
    .map((p) => {
      const label = p.kind === "demo" ? p.name + " (demo)" : p.name;
      const missing = p.exists === false ? " (file missing)" : "";
      return `<option value="${esc(p.plan_id)}"${p.plan_id === active.plan_id ? " selected" : ""}${p.exists === false ? " disabled" : ""}>${esc(label + missing)}</option>`;
    })
    .join("");
  const demo = s.demo_active
    ? '<span class="status plan-demo-badge" title="You are viewing the demo plan. Your own plan is unchanged.">Demo</span><button class="btn tiny" type="button" onclick="openCurrentPlan()">Exit demo</button>'
    : "";
  return `<label class="plan-switcher small" title="${esc(active.path || "")}">Plan <select id="planSwitcherSelect" class="btn tiny" aria-label="Active plan" onchange="switchPlanFromSelect(this.value)">${options}</select></label>${demo}`;
}

export function renderPlanSwitcher() {
  const host = document.getElementById("planSwitcher");
  if (host) host.innerHTML = planSwitcherHtml(planSwitcherState);
}

export async function refreshPlanSwitcher() {
  try {
    const out = await api("/api/plans");
    planSwitcherState = out && out.success ? out : null;
  } catch (_e) {
    planSwitcherState = null;
  }
  renderPlanSwitcher();
  return planSwitcherState;
}

export async function switchPlanFromSelect(planId) {
  const current = planSwitcherState && planSwitcherState.active;
  if (!planId || (current && current.plan_id === planId)) return;
  if (typeof hasUnsavedPlanChanges === "function" && hasUnsavedPlanChanges()) {
    const choice = await showSaveDiscardStayModal(
      "You have unsaved changes. Save them before switching plans, discard them, or stay here?",
      { title: "Switch Plan" },
    );
    if (choice === "stay") {
      renderPlanSwitcher();
      return;
    }
    if (choice === "save" && !(await saveAll(true))) {
      renderPlanSwitcher();
      return;
    }
  }
  try {
    const resp = await api("/api/plans/switch", {
      method: "POST",
      body: JSON.stringify({ plan_id: planId }),
    });
    if (!resp || !resp.success) {
      showMessage("Could not switch plans: " + ((resp && resp.error) || "unknown error"), "error");
      renderPlanSwitcher();
      return;
    }
    showMessage("Switched to " + ((resp.active && resp.active.name) || "plan") + ".", "success");
    await loadAll({ source: "Switched plan", preferLocal: false });
    renderMain();
  } catch (e) {
    showMessage("Error switching plans: " + e.message, "error");
    renderPlanSwitcher();
  }
}

Object.assign(window, {
  planSwitcherHtml,
  renderPlanSwitcher,
  refreshPlanSwitcher,
  switchPlanFromSelect,
});
