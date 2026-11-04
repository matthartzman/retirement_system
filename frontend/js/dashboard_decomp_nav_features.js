// Left-nav redesign (2026-11-04): the Set up / Maintain switch and the per-heading "Features" popover.
// Spec: documentation/future/superpowers/specs/2026-11-04-left-nav-redesign-design.md
//
// Everything here is derived, never stored: a feature's on/off state is read through the same accessors the
// Plan Features page uses (optionalFunctionEnabled / sectionFlagEnabled) and written through the same setter
// (setPlanFeatureSwitch -> POST /api/plan/feature -> module_catalog.set_feature), so the two pages cannot
// disagree. Turning a feature off only hides it; the saved entries are kept.
// The pure functions take their inputs as arguments so node tests can drive them without a browser.

// ── Set up / Maintain flow switch ───────────────────────────────────────────
const MODE_KEY = "rp_nav_mode";
export const MAINTAIN_FIRST_GROUP = "Track & Reconcile";
export const PINNED_GROUP = "Plan Status";
// Maintain mode's "Suggested next" chain (Set up keeps SUGGESTED_NEXT in dashboard_decomp_row_model.js).
export const MAINTAIN_CHAIN = {
  actual_spending: "monarch_reconciliation",
  monarch_reconciliation: "sales_ledger",
  sales_ledger: "reports_and_review",
};

let storedMode = null;
try {
  const v = typeof localStorage !== "undefined" ? localStorage.getItem(MODE_KEY) : null;
  if (v === "setup" || v === "maintain") storedMode = v;
} catch (_e) {
  storedMode = null; // storage blocked: the automatic default still works
}

// Automatic default: Set up while any required item is missing (or no plan is open), otherwise Maintain.
export function autoMode(missingCount, planIsLoaded) {
  return planIsLoaded && Number(missingCount) === 0 ? "maintain" : "setup";
}
export function currentMode(missingCount, planIsLoaded) {
  return storedMode || autoMode(missingCount, planIsLoaded);
}
export function setNavMode(mode) {
  if (mode !== "setup" && mode !== "maintain") return;
  storedMode = mode;
  try {
    localStorage.setItem(MODE_KEY, mode);
  } catch (_e) {
    /* per-viewer convenience only */
  }
  if (typeof window !== "undefined" && typeof window.renderSteps === "function") window.renderSteps();
}
export function resetNavModeForTests() {
  storedMode = null;
  seededFor = null;
}

// Only Track & Reconcile is lifted in Maintain; Plan Status stays pinned first. Group homes never change.
export function orderGroups(groups, mode) {
  if (mode !== "maintain") return groups;
  const lift = groups.find((g) => g.name === MAINTAIN_FIRST_GROUP);
  if (!lift) return groups;
  const rest = groups.filter((g) => g !== lift);
  const pinned = rest.filter((g) => g.name === PINNED_GROUP);
  return [...pinned, lift, ...rest.filter((g) => g.name !== PINNED_GROUP)];
}

export function maintainNext(stepId) {
  return MAINTAIN_CHAIN[stepId] || "";
}

// Which group opens by default: the first with required items missing (Set up) or Track & Reconcile (Maintain).
// Applied once per mode (when a plan is loaded) by adding it to the user-opened set, so the user can still close it.
let seededFor = null;
export function defaultOpenGroup(groups, mode, missingOf) {
  if (mode === "maintain") return groups.some((g) => g.name === MAINTAIN_FIRST_GROUP) ? MAINTAIN_FIRST_GROUP : "";
  const g = groups.find((x) => x.name !== PINNED_GROUP && missingOf(x) > 0);
  return g ? g.name : "";
}
export function seedOpenGroup(openSet, groups, mode, missingOf, planIsLoaded) {
  if (!planIsLoaded || seededFor === mode) return;
  seededFor = mode;
  const name = defaultOpenGroup(groups, mode, missingOf);
  if (name) openSet.add(name);
}

export function progressTexts(mode, pct, missingCount, planIsLoaded) {
  if (!planIsLoaded) return { progress: "Open local plan", required: "" };
  if (mode === "maintain")
    return {
      progress: missingCount ? `${missingCount} need${missingCount === 1 ? "s" : ""} attention` : "All caught up",
      required: "",
    };
  return { progress: `${pct}% complete`, required: `${missingCount} required missing` };
}

// ── Features: host-page map ─────────────────────────────────────────────────
// Where each optional feature's inputs appear: [host step id | null, kind, group override]. kind is
// page | section | sheet | option. A null host (workbook-only output) lists under the override group. Every
// catalog module that is optional or a plan flag must be here: tests/test_nav_feature_host_map_regression.py
// fails when one is missing, so a new feature cannot silently drop out of the popovers.
export const FEATURE_HOST = {
  scorp_vs_llc: ["income_work", "section"],
  qlac: ["income_retirement", "option"],
  rental_property_income: ["rental_properties", "page"],
  heloc: ["heloc_strategy", "page"],
  reserve_requirements: ["assets_home_cash", "page"],
  education_funding_529: ["family_business", "page"],
  equity_compensation: ["family_business", "page"],
  hybrid_ltc_policy: ["assets_special", "option"],
  insurance_inputs: ["annuity_death_benefits", "page"],
  life_insurance_need: ["annuity_death_benefits", "section"],
  existing_life_insurance: ["annuity_death_benefits", "section"],
  disability_income_insurance: ["annuity_death_benefits", "section"],
  property_casualty_umbrella: ["annuity_death_benefits", "section"],
  estate_legacy_plan: ["estate", "page"],
  special_needs_planning: ["estate", "section"],
  roth_conversion_plan: ["roth_conversion", "page"],
  charitable_giving: ["entity_charitable", "page"],
  daf_giving: ["entity_charitable", "option"],
  qcd_giving: ["entity_charitable", "option"],
  lifetime_tax_projection: [null, "sheet", "Taxes"],
  tax_capacity: [null, "sheet", "Taxes"],
  rmd_audit: [null, "sheet", "Taxes"],
  social_security_timing: ["strategy_optimize", "section"],
  retirement_strategy: ["strategy_optimize", "section"],
  hsa_drawdown: ["strategy_optimize", "section"],
  tax_loss_harvesting: ["strategy_optimize", "section"],
  gain_harvesting: ["strategy_optimize", "section"],
  asset_location: ["strategy_optimize", "section"],
  housing_location_search: ["strategy_optimize", "section"],
  housing_trajectory_comparison: ["strategy_optimize", "section"],
  state_residency: ["strategy_optimize", "section"],
  market_luck_stress_test: ["strategy_stress", "section"],
  survivor_stress_test: ["strategy_stress", "section"],
  long_term_care_stress: ["strategy_stress", "section"],
  divorce_qdro: ["strategy_stress", "section"],
  what_if_analysis: ["strategy_scenarios", "page"],
  planning_workbench: ["strategy_workbench", "page"],
  charts_dashboard: ["reports_and_review", "sheet"],
  current_vs_proposed: ["reports_and_review", "sheet"],
  methodology_rerun: ["reports_and_review", "sheet"],
  glossary: ["reports_and_review", "sheet"],
  // No inputs found anywhere in the UI (phase 0 recon), so it is a workbook-only row under Build & Results.
  business_succession: ["reports_and_review", "sheet"],
  spending_summary: ["actual_spending", "sheet"],
  spending_tracker_ytd: ["actual_spending", "section"],
  account_import: ["monarch_reconciliation", "page"],
  account_reconciliation: ["monarch_reconciliation", "sheet"],
};

// Plain-language names for features whose catalog name is internal.
const DISPLAY_NAME = {
  market_luck_stress_test: "Market-luck stress test (Monte Carlo)",
  account_import: "Transaction and balance auto-import",
  retirement_strategy: "Withdrawal Sequencing",
};

// Ungated sections that always exist on a page (listed under "Always on").
export const ALWAYS_ON_SECTIONS = {
  strategy_optimize: ["Asset Allocation"],
  strategy_workbench: ["Strategy Levers", "Unified Comparison Matrix", "Decision", "Saved Planning Cases"],
};
// Pages whose gate is hand-written in stepGatedByOptionalModule rather than in moduleGates.
const HAND_GATED_STEPS = ["strategy_stress", "entity_charitable", "family_business", "rental_properties"];

const DEMAND_RANK = { high: 0, medium_high: 1, medium: 2, low: 3, niche: 4 };

function esc(v) {
  return String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

function addsPhrase(kind, hostTitle) {
  if (kind === "page") return "Adds a page";
  if (kind === "sheet") return "Adds a workbook sheet";
  if (kind === "option") return hostTitle ? `Adds an option to ${hostTitle}` : "Adds an option";
  return hostTitle ? `Adds a section to ${hostTitle}` : "Adds a section";
}

function oneLine(text, max = 150) {
  const t = String(text || "").replace(/\s+/g, " ").trim();
  if (t.length <= max) return t;
  const cut = t.slice(0, max);
  const stop = cut.lastIndexOf(". ");
  return stop > 60 ? cut.slice(0, stop + 1) : cut.replace(/\s+\S*$/, "") + "…";
}

// Catalog modules that are switchable features (the ones the popovers list).
export function featureKeys(taxonomy) {
  const modules = (taxonomy || {}).modules || {};
  return Object.keys(modules).filter((k) => modules[k].optional || modules[k].gate_kind === "plan_flag");
}

// The feature's switch exists only when the catalog gives it one of its own and nothing forces it.
export function hasOwnSwitch(meta, status) {
  return !meta.gated_by && !(meta.gated_by_any_flag || []).length && !(status && status.forced);
}

// {group, hostStepId, hostTitle, kind} for a catalog key, from FEATURE_HOST and STEPS; null when unmapped.
export function featureHome(key, steps) {
  const h = FEATURE_HOST[key];
  if (!h) return null;
  const [stepId, kind, override] = h;
  const st = stepId ? steps.find((s) => s.id === stepId) : null;
  const group = override || (st && st.group);
  if (!group) return null;
  return { group, hostStepId: st ? st.id : "", hostTitle: st ? st.title : "", kind };
}

// Dependencies that are currently off: needsOff (strong, "Needs X") and softOff ("Works best with X").
export function dependencyNotes(meta, deps) {
  const off = (list) => (list || []).filter((d) => !deps.isOn(d.key)).map((d) => d.name || d.key);
  return { needsOff: off(meta.needs), softOff: off(meta.degrades_without) };
}

// Everything a group's popover shows. deps: { taxonomy, steps, isOn(key), status(key), keptLabel(key), gatedStepIds }.
export function groupFeatures(group, deps) {
  const modules = (deps.taxonomy || {}).modules || {};
  const features = [];
  featureKeys(deps.taxonomy).forEach((key) => {
    const home = featureHome(key, deps.steps);
    if (!home || home.group !== group) return;
    const meta = modules[key];
    const status = deps.status ? deps.status(key) : null;
    const on = deps.isOn(key);
    const follows = meta.gated_by
      ? [(modules[meta.gated_by] || {}).name || meta.gated_by]
      : (meta.gated_by_any_flag || []).map((k) => (modules[k] || {}).name || k);
    features.push({
      key,
      name: DISPLAY_NAME[key] || meta.name || key,
      desc: oneLine(meta.description),
      adds: addsPhrase(home.kind, home.hostTitle),
      kind: home.kind,
      hostStepId: home.hostStepId,
      hostTitle: home.hostTitle || (home.kind === "sheet" ? "Workbook sheets" : ""),
      tag: meta.domain || "",
      demand: meta.demand,
      rank: DEMAND_RANK[meta.demand] ?? 9,
      on,
      hasSwitch: hasOwnSwitch(meta, status),
      forced: !!(status && status.forced),
      follows,
      kept: !on && deps.keptLabel ? deps.keptLabel(key) : "",
      ...dependencyNotes(meta, deps),
    });
  });
  const byDemand = (a, b) => a.rank - b.rank || a.name.localeCompare(b.name);
  features.sort(byDemand);
  const gated = new Set(deps.gatedStepIds || []);
  const always = [];
  deps.steps
    .filter((s) => s.group === group && !s.hidden && !gated.has(s.id))
    .forEach((s) => {
      always.push({ name: s.title, stepId: s.id, hostTitle: s.title });
      (ALWAYS_ON_SECTIONS[s.id] || []).forEach((sec) => always.push({ name: sec, stepId: s.id, hostTitle: s.title, section: true }));
    });
  // A gated page whose gate is hand-written still lists through its feature rows, never as "always on".
  return {
    off: features.filter((f) => !f.on),
    on: features.filter((f) => f.on),
    always: always.filter((a) => !HAND_GATED_STEPS.includes(a.stepId)),
    offCount: features.filter((f) => !f.on).length,
    total: features.length,
  };
}

// ── Features: markup ────────────────────────────────────────────────────────
const SLIDERS_SVG =
  '<svg viewBox="0 0 14 14" width="12" height="12" aria-hidden="true" focusable="false"><path d="M1 3.5h7M11 3.5h2M1 10.5h2M6 10.5h7" stroke="currentColor" stroke-width="1.4" fill="none" stroke-linecap="round"/><circle cx="9.5" cy="3.5" r="1.7" fill="none" stroke="currentColor" stroke-width="1.4"/><circle cx="4.5" cy="10.5" r="1.7" fill="none" stroke="currentColor" stroke-width="1.4"/></svg>';

export function iconHtml(group, data, expanded) {
  if (!data || !data.total) return "";
  const n = data.offCount;
  const label = `Manage features in ${group}${n ? `, ${n} off` : ""}`;
  return (
    `<button type="button" class="nf-icon" data-nf-group="${esc(group)}" aria-haspopup="dialog" aria-expanded="${expanded ? "true" : "false"}" aria-label="${esc(label)}" title="${esc(label)}">` +
    SLIDERS_SVG +
    (n ? `<span class="nf-count" aria-hidden="true">${n}</span>` : "") +
    "</button>"
  );
}

function rowHtml(f, planOpen) {
  const switchHtml = f.hasSwitch
    ? `<button type="button" role="switch" class="nf-switch${f.on ? " on" : ""}" aria-checked="${f.on ? "true" : "false"}" aria-label="${esc(f.name)}" data-nf-key="${esc(f.key)}" data-nf-to="${f.on ? "off" : "on"}"${planOpen ? "" : " disabled"}><span class="nf-knob"></span></button>`
    : f.forced
      ? '<span class="nf-note">Set by environment</span>'
      : "";
  const open = f.hostStepId
    ? `<button type="button" class="nf-link" data-nf-open="${esc(f.hostStepId)}">${esc(f.name)}</button>`
    : `<span class="nf-name">${esc(f.name)}</span>`;
  const follows = !f.hasSwitch && f.follows.length ? `<span class="nf-note">Follows ${esc(f.follows.join(" or "))}</span>` : "";
  const needs = (f.needsOff || []).length ? `<span class="nf-note nf-needs">Needs ${esc(f.needsOff.join(" and "))}</span>` : "";
  const soft = (f.softOff || []).length ? `<span class="nf-note nf-soft">Works best with ${esc(f.softOff.join(" and "))}</span>` : "";
  return (
    `<li class="nf-row" data-nf-row="${esc(f.key)}"><div class="nf-main">${open}${f.tag ? `<span class="nf-tag">${esc(f.tag)}</span>` : ""}` +
    `<div class="nf-desc">${esc(f.adds)}.${f.desc ? " " + esc(f.desc) : ""}</div>` +
    (f.kept ? `<span class="nf-note">${esc(f.kept)}</span>` : "") +
    follows +
    needs +
    soft +
    `</div>${switchHtml}</li>`
  );
}

// Rows under host-page sub-headers; sheet-only rows collapse under "Workbook sheets", niche rows under "More".
function sectionRowsHtml(features, planOpen) {
  const common = features.filter((f) => f.kind !== "sheet" && f.demand !== "niche");
  const sheets = features.filter((f) => f.kind === "sheet");
  const niche = features.filter((f) => f.kind !== "sheet" && f.demand === "niche");
  const hosts = [];
  common.forEach((f) => {
    let h = hosts.find((x) => x.title === f.hostTitle);
    if (!h) hosts.push((h = { title: f.hostTitle, items: [] }));
    h.items.push(f);
  });
  const list = (items) => `<ul class="nf-list">${items.map((f) => rowHtml(f, planOpen)).join("")}</ul>`;
  let html = "";
  hosts.forEach((h) => {
    html += `${hosts.length > 1 || h.title ? `<div class="nf-host">${esc(h.title)}</div>` : ""}${list(h.items)}`;
  });
  if (niche.length) html += `<details class="nf-more"><summary>More (${niche.length})</summary>${list(niche)}</details>`;
  if (sheets.length) html += `<details class="nf-more"><summary>Workbook sheets (${sheets.length})</summary>${list(sheets)}</details>`;
  return html;
}

export function popoverHtml(group, data, opts = {}) {
  const planOpen = opts.planOpen !== false;
  let html = `<div class="nf-head"><b id="nfTitle">Features in ${esc(group)}</b><button type="button" class="nf-close" data-nf-close aria-label="Close features">&times;</button></div>`;
  html += `<div class="nf-status" role="status">${opts.statusHtml || ""}</div>`;
  if (!planOpen) html += '<p class="nf-note">Open a plan to switch features on or off.</p>';
  if (data.off.length)
    html += `<section class="nf-section" aria-label="Not enabled"><h3>Not enabled</h3>${sectionRowsHtml(data.off, planOpen)}</section>`;
  if (data.on.length)
    html += `<section class="nf-section" aria-label="Enabled"><h3>Enabled</h3>${sectionRowsHtml(data.on, planOpen)}</section>`;
  if (data.always.length)
    html +=
      '<section class="nf-section" aria-label="Always on"><h3>Always on</h3><ul class="nf-list">' +
      data.always
        .map(
          (a) =>
            `<li class="nf-row"><div class="nf-main"><button type="button" class="nf-link" data-nf-open="${esc(a.stepId)}"><span aria-hidden="true">&#128274; </span>${esc(a.name)}</button>${a.section ? `<span class="nf-tag">${esc(a.hostTitle)}</span>` : ""}</div></li>`,
        )
        .join("") +
      "</ul></section>";
  html +=
    '<div class="nf-foot"><button type="button" class="nf-link" data-nf-open="optional_functions">Open Plan Features</button>' +
    '<span class="nf-foot-note">Plan Features also lists every feature by topic.</span></div>';
  return html;
}

// ── Features: browser wiring ────────────────────────────────────────────────
const nfState = { group: "", status: "", statusKey: "" };

function liveDeps() {
  const g = typeof window !== "undefined" ? window : {};
  const taxonomy = typeof g.planModuleTaxonomy === "function" ? g.planModuleTaxonomy() : { modules: {} };
  const modules = taxonomy.modules || {};
  const gates = typeof moduleGates !== "undefined" && moduleGates ? moduleGates : {};
  const isOn = (key) => {
    const meta = modules[key] || {};
    if (meta.gate_kind === "plan_flag") {
      const r = meta.gate_ref || [];
      return r.length === 3 && typeof sectionFlagEnabled === "function" ? !!sectionFlagEnabled(r[0], r[1], r[2]) : false;
    }
    if ((meta.gated_by_any_flag || []).length) return meta.gated_by_any_flag.some((k) => isOn(k));
    return !!g.optionalFunctionEnabled(key);
  };
  return {
    taxonomy,
    steps: typeof STEPS !== "undefined" ? STEPS : [],
    isOn,
    status: (key) => (typeof moduleStatus !== "undefined" && moduleStatus ? moduleStatus[key] : null),
    keptLabel: (key) => (typeof g.featureKeptLabel === "function" ? g.featureKeptLabel(key) : ""),
    gatedStepIds: [...Object.keys(gates.step_gates || {}), ...Object.keys(gates.flag_gates || {}), ...HAND_GATED_STEPS],
  };
}

export function groupFeaturesLive(group) {
  try {
    return groupFeatures(group, liveDeps());
  } catch (_e) {
    return null;
  }
}
export function iconHtmlLive(group) {
  return iconHtml(group, groupFeaturesLive(group), nfState.group === group);
}

function popEl() {
  let el = document.getElementById("navFeaturesPopover");
  if (!el) {
    el = document.createElement("div");
    el.id = "navFeaturesPopover";
    el.className = "nf-pop hidden";
    el.setAttribute("role", "dialog");
    el.setAttribute("aria-modal", "false");
    el.setAttribute("aria-labelledby", "nfTitle");
    document.body.appendChild(el);
  }
  return el;
}
function iconFor(group) {
  return [...document.querySelectorAll("[data-nf-group]")].find((b) => b.getAttribute("data-nf-group") === group) || null;
}
function paint() {
  if (!nfState.group) return;
  const data = groupFeaturesLive(nfState.group);
  if (!data) return;
  const planOpen = typeof planLoaded !== "undefined" ? !!planLoaded : true;
  const el = popEl();
  const scroll = el.scrollTop;
  el.innerHTML = popoverHtml(nfState.group, data, { planOpen, statusHtml: nfState.status });
  el.scrollTop = scroll;
}
function position(icon) {
  const el = popEl();
  if (window.matchMedia && window.matchMedia("(max-width: 900px)").matches) {
    el.style.left = el.style.top = "";
    return;
  }
  const side = document.getElementById("sideNav");
  const r = icon.getBoundingClientRect();
  const left = (side ? side.getBoundingClientRect().right : r.right) + 8;
  el.style.left = left + "px";
  const h = Math.min(el.offsetHeight || 440, window.innerHeight - 16);
  el.style.top = Math.max(8, Math.min(r.top - 8, window.innerHeight - h - 8)) + "px";
}
export function openFeatures(group) {
  const icon = iconFor(group);
  nfState.group = group;
  nfState.status = "";
  const el = popEl();
  paint();
  el.classList.remove("hidden");
  if (icon) {
    icon.setAttribute("aria-expanded", "true");
    position(icon);
  }
  const first = el.querySelector(".nf-switch:not([disabled]), .nf-link");
  if (first) first.focus({ preventScroll: true });
}
export function closeFeatures(returnFocus = true) {
  if (!nfState.group) return;
  const group = nfState.group;
  nfState.group = "";
  nfState.status = "";
  const el = document.getElementById("navFeaturesPopover");
  if (el) el.classList.add("hidden");
  const icon = iconFor(group);
  if (icon) {
    icon.setAttribute("aria-expanded", "false");
    if (returnFocus) icon.focus({ preventScroll: true });
  }
}

function announce(text) {
  const a = document.getElementById("navAnnouncer");
  if (a) a.textContent = text;
}

async function toggleFeature(key, turnOn) {
  const deps = liveDeps();
  const meta = (deps.taxonomy.modules || {})[key] || {};
  const home = featureHome(key, deps.steps) || {};
  if (typeof window.setPlanFeatureSwitch !== "function") return;
  await window.setPlanFeatureSwitch(key, turnOn); // the same writer Plan Features' rowless switches use
  const name = DISPLAY_NAME[key] || meta.name || key;
  const nowOn = liveDeps().isOn(key);
  if (nowOn === turnOn) {
    const where = home.hostTitle ? `${home.group} › ${home.hostTitle}` : home.group;
    nfState.status = turnOn
      ? `Added to ${esc(where)}. ${home.hostStepId ? `<button type="button" class="nf-link" data-nf-open="${esc(home.hostStepId)}">Open</button>` : ""}`
      : `${esc(name)} hidden. Anything you entered is kept.`;
    announce(turnOn ? `${name} added to ${where}` : `${name} hidden`);
  } else {
    nfState.status = `Could not change ${esc(name)}.`;
    announce(`Could not change ${name}`);
  }
  paint();
}

let wired = false;
function wire() {
  if (wired || typeof document === "undefined") return;
  wired = true;
  document.addEventListener("click", (e) => {
    const t = e.target && e.target.closest ? e.target : null;
    if (!t) return;
    const icon = t.closest("[data-nf-group]");
    if (icon) {
      e.preventDefault();
      e.stopPropagation();
      const g = icon.getAttribute("data-nf-group");
      if (nfState.group === g) closeFeatures();
      else {
        closeFeatures(false);
        openFeatures(g);
      }
      return;
    }
    const mode = t.closest("[data-nav-mode]");
    if (mode) {
      setNavMode(mode.getAttribute("data-nav-mode"));
      return;
    }
    const pop = t.closest("#navFeaturesPopover");
    if (!pop) {
      if (nfState.group) closeFeatures(false);
      return;
    }
    if (t.closest("[data-nf-close]")) return closeFeatures();
    const sw = t.closest("[data-nf-key]");
    if (sw) {
      if (!sw.disabled) toggleFeature(sw.getAttribute("data-nf-key"), sw.getAttribute("data-nf-to") === "on");
      return;
    }
    const open = t.closest("[data-nf-open]");
    if (open) {
      const id = open.getAttribute("data-nf-open");
      closeFeatures(false);
      if (typeof window.setStep === "function") window.setStep(id);
    }
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && nfState.group) {
      e.preventDefault();
      closeFeatures();
    }
  });
}

// Called at the end of every renderSteps(): keep the mode switch and any open popover in step with the plan.
export function afterRender(mode) {
  wire();
  document.querySelectorAll("[data-nav-mode]").forEach((b) => {
    const on = b.getAttribute("data-nav-mode") === mode;
    b.setAttribute("aria-pressed", on ? "true" : "false");
    b.classList.toggle("primary", on);
  });
  const steps = document.getElementById("steps");
  if (steps) steps.classList.toggle("nav-maintain", mode === "maintain");
  if (nfState.group) {
    const icon = iconFor(nfState.group);
    if (icon) icon.setAttribute("aria-expanded", "true");
    paint();
  }
}

if (typeof window !== "undefined") {
  window.RPNav = {
    currentMode,
    setNavMode,
    orderGroups,
    seedOpenGroup,
    maintainNext,
    progressTexts,
    iconHtml: iconHtmlLive,
    afterRender,
    openFeatures,
    closeFeatures,
  };
}
