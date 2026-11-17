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
  const manage = s.manageable
    ? '<button class="btn tiny" type="button" aria-haspopup="dialog" onclick="openManagePlans()">Manage plans</button>'
    : "";
  return `<label class="plan-switcher small" title="${esc(active.path || "")}">Plan <select id="planSwitcherSelect" class="btn tiny" aria-label="Active plan" onchange="switchPlanFromSelect(this.value)">${options}</select></label>${manage}${demo}`;
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

// False when the user chose to stay (or saving failed): nothing else should happen.
async function leaveUnsavedChangesOk(title) {
  if (typeof hasUnsavedPlanChanges !== "function" || !hasUnsavedPlanChanges()) return true;
  const choice = await showSaveDiscardStayModal(
    "You have unsaved changes. Save them before switching plans, discard them, or stay here?",
    { title },
  );
  if (choice === "stay") return false;
  return choice !== "save" || (await saveAll(true));
}

export async function switchPlanFromSelect(planId) {
  const current = planSwitcherState && planSwitcherState.active;
  if (!planId || (current && current.plan_id === planId)) return;
  if (!(await leaveUnsavedChangesOk("Switch Plan"))) {
    renderPlanSwitcher();
    return;
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

// ---- Manage plans (multi-user server): new, duplicate, rename, delete. Names only: the server assigns ids.
const PLAN_MANAGE_ROUTES = {
  create: "/api/plans/create",
  duplicate: "/api/plans/duplicate",
  rename: "/api/plans/rename",
  delete: "/api/plans/delete",
};

export function planManageRequest(action, plan, input) {
  const url = PLAN_MANAGE_ROUTES[action];
  if (!url) return null;
  const id = plan && plan.plan_id;
  const name = (input && input.name) || "";
  if (action === "create") return { url, body: { name, from: (input && input.from) || "blank" } };
  if (action === "delete") return { url, body: { plan_id: id, confirm_name: name } };
  return { url, body: { plan_id: id, name } };
}

export function planUsageText(limits) {
  const l = limits || {};
  const plans = l.max_plans ? `${l.plan_count} of ${l.max_plans} plans` : `${l.plan_count || 0} plans`;
  const used = Math.round((l.disk_used_mb || 0) * 10) / 10;
  const disk = l.disk_quota_mb ? `${used} of ${l.disk_quota_mb} MB used` : `${used} MB used`;
  return `${plans} \u00b7 ${disk}`;
}

export function managePlansHtml(state) {
  const s = state || {};
  const plans = Array.isArray(s.plans) ? s.plans : [];
  const l = s.limits || {};
  const atCap = !!l.max_plans && l.plan_count >= l.max_plans;
  const own = plans.filter((p) => p.kind !== "demo").length;
  const cap = atCap ? " disabled" : "";
  const rows = plans
    .map((p) => {
      const demo = p.kind === "demo";
      const gone = p.exists === false;
      const lock = demo || p.active || own <= 1 ? " disabled" : "";
      const tag = p.active ? " (active)" : demo ? " (demo)" : gone ? " (file missing)" : "";
      const btn = (act, label, off) =>
        `<button class="btn tiny" type="button" data-plan-act="${act}" data-plan-id="${esc(p.plan_id)}"${off ? " disabled" : ""}>${label}</button>`;
      return `<li class="manage-plan-row"><span class="manage-plan-name">${esc(p.name)}${tag}</span> ${demo ? "" : btn("rename", "Rename", false) + btn("duplicate", "Duplicate", atCap || gone) + btn("delete", "Delete", !!lock)}</li>`;
    })
    .join("");
  const note = atCap ? '<p class="small">You have reached the plan limit. Delete a plan to add another.</p>' : "";
  return `<b class="inapp-modal-title" id="managePlansTitle">Manage plans</b><div class="inapp-modal-body"><p class="small">${esc(planUsageText(l))}</p>${note}<ul class="manage-plan-list">${rows}</ul><div><button class="btn" type="button" data-plan-act="new-blank"${cap}>New blank plan</button> <button class="btn" type="button" data-plan-act="new-sample"${cap}>New plan from sample</button></div></div><div class="inapp-modal-actions"><button class="btn primary" type="button" data-plan-act="close">Close</button></div>`;
}

async function sendPlanManage(action, plan, input) {
  const req = planManageRequest(action, plan, input);
  try {
    const resp = await api(req.url, { method: "POST", body: JSON.stringify(req.body) });
    if (!resp || !resp.success) {
      showMessage((resp && resp.error) || "That did not work.", "error");
      return null;
    }
    planSwitcherState = resp;
    return resp;
  } catch (e) {
    showMessage("Error: " + e.message, "error");
    return null;
  }
}

function closeManagePlans(overlay) {
  closeStaticDialog(overlay);
  overlay.remove();
}

async function runPlanManageAction(act, planId, overlay) {
  const plans = (planSwitcherState && planSwitcherState.plans) || [];
  const plan = plans.find((p) => p.plan_id === planId) || null;
  if (act === "close") return closeManagePlans(overlay);
  let resp = null;
  if (act === "new-blank" || act === "new-sample") {
    const name = await showInAppPrompt("Name for the new plan", "", { title: "New plan" });
    if (!name || !(await leaveUnsavedChangesOk("New Plan"))) return;
    resp = await sendPlanManage("create", null, { name, from: act === "new-sample" ? "demo" : "blank" });
    if (resp) {
      closeManagePlans(overlay);
      showMessage("Created " + ((resp.plan && resp.plan.name) || "plan") + ".", "success");
      await loadAll({ source: "Switched plan", preferLocal: false });
      renderMain();
      renderPlanSwitcher();
    }
    return;
  }
  if (plan && act === "duplicate") {
    const name = await showInAppPrompt("Name for the copy", plan.name + " (copy)", { title: "Duplicate plan" });
    if (name) resp = await sendPlanManage("duplicate", plan, { name });
  } else if (plan && act === "rename") {
    const name = await showInAppPrompt("New name", plan.name, { title: "Rename plan" });
    if (name && name !== plan.name) resp = await sendPlanManage("rename", plan, { name });
  } else if (plan && act === "delete") {
    const name = await showInAppPrompt(
      'Type "' + plan.name + '" to delete this plan for good. This cannot be undone.',
      "",
      { title: "Delete plan" },
    );
    if (name) resp = await sendPlanManage("delete", plan, { name });
  }
  if (resp) {
    renderPlanSwitcher();
    overlay.innerHTML =
      '<div class="inapp-modal" role="dialog" aria-modal="true" aria-labelledby="managePlansTitle">' + managePlansHtml(planSwitcherState) + "</div>";
  }
}

export async function openManagePlans() {
  await refreshPlanSwitcher();
  if (!planSwitcherState) return;
  const overlay = document.createElement("div");
  overlay.className = "inapp-modal-overlay";
  overlay.innerHTML =
    '<div class="inapp-modal" role="dialog" aria-modal="true" aria-labelledby="managePlansTitle">' + managePlansHtml(planSwitcherState) + "</div>";
  overlay.onclick = (e) => {
    const btn = e.target && e.target.closest ? e.target.closest("[data-plan-act]") : null;
    if (btn) runPlanManageAction(btn.getAttribute("data-plan-act"), btn.getAttribute("data-plan-id"), overlay);
    else if (e.target === overlay) closeManagePlans(overlay);
  };
  document.body.appendChild(overlay);
  openStaticDialog(overlay, { onEscape: () => closeManagePlans(overlay) });
}

Object.assign(window, {
  planSwitcherHtml,
  renderPlanSwitcher,
  refreshPlanSwitcher,
  switchPlanFromSelect,
  openManagePlans,
  managePlansHtml,
  planManageRequest,
  planUsageText,
});
