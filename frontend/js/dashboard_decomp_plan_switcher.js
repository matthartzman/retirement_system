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

// ---- Manage plans (multi-user server): one menu prompt; names only, the server assigns ids.
const PLAN_ROUTES = { create: "/api/plans/create", duplicate: "/api/plans/duplicate", rename: "/api/plans/rename", delete: "/api/plans/delete" };

export function planManageRequest(action, plan, input) {
  const url = PLAN_ROUTES[action];
  if (!url) return null;
  const name = (input && input.name) || "";
  if (action === "create") return { url, body: { name, from: (input && input.from) || "blank" } };
  return { url, body: action === "delete" ? { plan_id: plan.plan_id, confirm_name: name } : { plan_id: plan.plan_id, name } };
}

export function planUsageText(l) {
  l = l || {};
  const used = Math.round((l.disk_used_mb || 0) * 10) / 10;
  const plans = l.max_plans ? `${l.plan_count} of ${l.max_plans} plans` : `${l.plan_count || 0} plans`;
  return `${plans} \u00b7 ${l.disk_quota_mb ? `${used} of ${l.disk_quota_mb} MB used` : `${used} MB used`}`;
}

// The menu entries the server would accept: nothing new at the plan cap, no delete without a second plan.
export function planManageChoices(state) {
  const s = state || {};
  const mine = (s.plans || []).filter((p) => p.kind !== "demo");
  const room = !(s.limits && s.limits.max_plans && s.limits.plan_count >= s.limits.max_plans);
  const demo = !!(s.active && s.active.kind === "demo");
  const all = [["new-blank", "New blank plan", room], ["new-sample", "New plan from sample", room], ["duplicate", "Duplicate this plan", room],
    ["rename", "Rename this plan", !demo], ["delete", "Delete a plan", mine.filter((p) => !p.active).length > 0 && mine.length > 1]];
  return all.filter((c) => c[2]).map((c) => ({ value: c[0], label: c[1] }));
}

async function sendPlanManage(action, plan, input) {
  const req = planManageRequest(action, plan, input);
  try {
    const resp = await api(req.url, { method: "POST", body: JSON.stringify(req.body) });
    if (resp && resp.success) return (planSwitcherState = resp);
    showMessage((resp && resp.error) || "That did not work.", "error");
  } catch (e) {
    showMessage("Error: " + e.message, "error");
  }
  return null;
}

export async function openManagePlans() {
  await refreshPlanSwitcher();
  const st = planSwitcherState;
  if (!st) return;
  const act = await showInAppPrompt(planUsageText(st.limits), "", { title: "Manage plans", choices: planManageChoices(st) });
  const ask = (msg, def, title) => showInAppPrompt(msg, def, { title });
  let resp = null;
  if (act === "new-blank" || act === "new-sample") {
    const name = await ask("Name for the new plan", "", "New plan");
    if (name && (await leaveUnsavedChangesOk("New Plan"))) resp = await sendPlanManage("create", null, { name, from: act === "new-sample" ? "demo" : "blank" });
  } else if (act === "duplicate" || act === "rename") {
    const copy = act === "duplicate";
    const name = await ask(copy ? "Name for the copy" : "New name", st.active.name + (copy ? " (copy)" : ""), copy ? "Duplicate plan" : "Rename plan");
    if (name) resp = await sendPlanManage(act, st.active, { name });
  } else if (act === "delete") {
    const others = st.plans.filter((p) => p.kind !== "demo" && !p.active);
    const id = await showInAppPrompt("Plan to delete", others[0].plan_id, { title: "Delete plan", choices: others.map((p) => ({ value: p.plan_id, label: p.name })) });
    const target = others.find((p) => p.plan_id === id);
    const typed = target && (await ask(`Type "${target.name}" to delete it for good. This cannot be undone.`, "", "Delete plan"));
    if (typed) resp = await sendPlanManage("delete", target, { name: typed });
  }
  if (!resp) return;
  renderPlanSwitcher();
  showMessage(act === "delete" ? "Plan deleted." : "Done.", "success");
  if (act.startsWith("new-")) {
    await loadAll({ source: "Switched plan", preferLocal: false });
    renderMain();
  }
}

Object.assign(window, {
  planSwitcherHtml,
  renderPlanSwitcher,
  refreshPlanSwitcher,
  switchPlanFromSelect,
  openManagePlans,
  planManageRequest,
  planManageChoices,
  planUsageText,
});
