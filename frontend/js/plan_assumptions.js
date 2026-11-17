// Plan assumptions: the plan's engine settings, edited with the shared settings renderer (settings_renderer.js).
SETTINGS_ENDPOINT = "/api/plan/engine-assumptions";
const PLAN_PAGES = [
  { id: "assumptions", title: "Capital market assumptions", desc: "Expected returns, volatility, custom assumption files, and long-term optimizer inputs.", filterSections: ["Asset Class Assumptions"] },
  { id: "correlations", title: "Asset correlations", desc: "Pairwise correlation settings used by optimizer diversification calculations.", filterSections: ["Asset Correlations"] },
  { id: "plan", title: "Tax modeling", desc: "Switches for the Net Investment Income Tax (NIIT) and residence-state estate tax.", filterSections: ["Plan Settings"] },
  { id: "rebalancing", title: "Global rebalancing controls", desc: "Household-level tax-aware optimizer mode, risk limits, tax-aware trade controls, and objective weights.", filterSections: ["Rebalancing"] },
  { id: "annuity_calibration", title: "Annuity calibration", desc: "Annuity purchase-rate curve and reserve-decay factors used to value annuity income.", filterSections: ["Annuity Calibration"] },
];
function navHelpKey(id) { return id; }
function renderAdminNav() {
  const box = document.getElementById("adminSteps");
  if (!box) return;
  const q = String(adminNavSearchText || "").trim().toLowerCase();
  lastAdminNavItems = PLAN_PAGES.map((p) => ({ id: "plan_" + p.id, group: "Plan assumptions", title: p.title, desc: p.desc, action: `showPlanAssumptions('${p.id}')` }));
  const items = [...lastAdminNavItems, ...editorHeadingNavPages].filter((it) => !q || [it.title, it.desc].join(" ").toLowerCase().includes(q) || it.id === activeAdminStep);
  box.classList.add("grouped");
  box.innerHTML = items.map((it) => `<button class="stepbtn ${it.id === activeAdminStep ? "active" : ""}" data-admin-step="${esc(it.id)}" onclick="${it.action}"><span class="step-title">${esc(it.title)}</span><br><span class="step-desc">${esc(it.desc || "")}</span></button>`).join("") || '<div class="no-results">No navigation matches.</div>';
}
function setAdminStep(id) { activeAdminStep = id || activeAdminStep; renderAdminNav(); }
function setAdminNavSearch(q) { adminNavSearchText = q; renderAdminNav(); }
function setAdminSearchScope(scope) {
  adminSearchScope = scope === "page" ? "page" : "nav";
  document.querySelectorAll("[data-admin-search-scope]").forEach((b) => b.classList.toggle("primary", b.dataset.adminSearchScope === adminSearchScope));
  if (adminSearchScope === "page") filterActiveTable(); else renderAdminNav();
}
function setAdminCombinedSearch(q) {
  if (adminSearchScope === "nav") { adminNavSearchText = q; renderAdminNav(); return; }
  adminPageSearchText = q;
  const cfg = document.getElementById("cfgSearch");
  if (cfg) cfg.value = q;
  filterActiveTable();
}
async function showPlanAssumptions(id = PLAN_PAGES[0].id) {
  const page = PLAN_PAGES.find((p) => p.id === id) || PLAN_PAGES[0];
  setAdminStep("plan_" + page.id);
  const def = { kind: "plan", file: "engine_assumptions", title: page.title, profile: "section_settings", filterSections: page.filterSections, filterSubsections: [], filterKeys: [], defaultOpen: false, collapseBySubsection: true, note: page.desc + " Saved with this plan.", navStep: "plan_" + page.id };
  await loadCsvEditor(def, `showPlanAssumptions('${page.id}')`);
}
const showAppSettings = () => showPlanAssumptions();
window.addEventListener("beforeunload", (e) => {
  if (activeEditor && activeEditor.changed) { e.preventDefault(); e.returnValue = "Unsaved changes"; }
});
// Start after DOMContentLoaded so pywebview_bridge.js (a module) has patched fetch first.
async function _bootPlanAssumptions() {
  try {
    const sj = await (await fetch("/api/auth/session", { cache: "no-store" })).json();
    if (sj && sj.csrf_token) csrfToken = sj.csrf_token;
  } catch (_e) {}
  showPlanAssumptions().catch((e) => msg("Error: " + e.message, true));
}
window.addEventListener("DOMContentLoaded", _bootPlanAssumptions, { once: true });
