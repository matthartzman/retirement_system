// ── Plan Features (Settings → Plan Features) ────────────────────────────────
// The switch surface for every optional workbook module: #330's "three
// surfaces, one registry" (spec §5.1), of which this page is surface 1.
//
// Extracted from dashboard.js because dashboard.js sits on a size ratchet
// (tests/test_frontend_size_ratchet.py) that may only move DOWN, and this page
// grows substantially here. The ratchet's own docstring names this as the
// supported way through: "a change that adds lines to dashboard.js must take
// lines out of it somewhere else, or move the new code into its own module --
// which is the point."
//
// Loaded AFTER dashboard.js (see frontend/index.html), the same position
// dashboard_decomp_workbook_formatting.js occupies for the other extracted
// Settings page: this module reads `searchText`, `boolishValue`, `rows` and
// `moduleStatus` off dashboard.js's own window bridge, and dashboard.js calls
// `renderOptionalFunctions()` back as a bare global from renderMain()'s
// dispatch. Both directions resolve at call time, not at module-evaluation
// time, so neither file needs the other to have finished evaluating.
//
// SHAPE: everything that decides *what* the page says is a pure function
// taking its data as parameters; only `renderOptionalFunctions()` itself
// reads shared mutable state. That is not stylistic — a module-scoped `let`
// is a lexical binding the frontend tests' vm sandbox cannot reach, so a
// helper that closes over page state is a helper that cannot be tested
// (see tests/frontend/plan_features.test.mjs).

// Which kind chip is active ("" = all), and which domain groups are expanded.
// Per-render UI state only; nothing here is persisted or sent to the server.
let planFeatureKind = "";
let planFeatureCollapsed = new Set();

export function setPlanFeatureKind(kind) {
  planFeatureKind = planFeatureKind === kind ? "" : kind;
  renderMain();
}

export function togglePlanFeatureGroup(domain) {
  if (planFeatureCollapsed.has(domain)) planFeatureCollapsed.delete(domain);
  else planFeatureCollapsed.add(domain);
  renderMain();
}

// Demand is a five-band catalog field; the page shows it as a plain-language
// hint rather than the raw enum, which means nothing to a reader.
const DEMAND_HINT = {
  high: "Most plans use this",
  medium_high: "Common",
  medium: "Sometimes relevant",
  low: "Situational",
  niche: "Rarely needed",
};

export function demandHint(demand) {
  return DEMAND_HINT[String(demand || "").toLowerCase()] || "";
}

// #330 Q7. Read-only disclosure: when a RETIREMENT_SYSTEM_FORCE_* variable is
// what decided a module's state, the page says so rather than showing a switch
// that silently disagrees with what the build did. Never a writable tier --
// the whole point is that there is no second precedence rule.
//
// Returns "" when nothing is overridden, which is every ordinary run.
export function envOverrideNotice(status) {
  const forced = Object.keys(status || {})
    .filter((k) => (status[k] || {}).forced)
    .sort();
  if (!forced.length) return "";
  const vars = [...new Set(forced.map((k) => status[k].forced_by))].sort();
  const n = forced.length;
  return (
    `${n} feature${n === 1 ? " is" : "s are"} currently forced by ` +
    `${vars.join(" and ")}. Those switches are read-only here and the build ` +
    `is using the forced state, not the saved one.`
  );
}

// "Off · 4 policies entered" (#330 §5.4). Turning a module off never deletes
// plan data, so a module that is off but holds data needs to say so -- that is
// the discoverability half of the guarantee.
//
// `rows` are the plan rows already narrowed to this module; a row counts as
// entered when it holds a non-blank value that is not a bare boolean toggle.
export function enteredRowCount(rows) {
  return (rows || []).filter((r) => {
    const v = String((r && r.value) != null ? r.value : "").trim();
    if (!v) return false;
    const u = v.toUpperCase();
    return u !== "NO" && u !== "FALSE" && u !== "0";
  }).length;
}

// WP1.5: the one wording for "off, but your data is still here", shared by
// Plan Features and every page-level off note.
export function offRowsLabel(n) {
  return "Off · " + n + (n === 1 ? " row" : " rows") + " entered";
}

// WP1.5: when a feature the projection itself reads is off, say what the
// switch does to the numbers (design 2026-10-04 section 3, off semantics).
export function engineIgnoredWarning(meta) {
  return meta && meta.engine_participation
    ? "While " + (meta.name || "this feature") + " is off, the projection ignores it. Your entries are kept."
    : "";
}

// #330 §5.3 (W9): where each plan flag's row actually renders for editing.
// Not mechanically derivable from the catalog the way a module toggle's
// dashboard_step is: HELOC has one (moduleGates.flag_gates), but Hybrid
// LTC/DAF/QCD don't, and the generic row->step resolver
// (sourceStepForRow(), which BUILD_IMPACT_SOURCE_STEP_IDS drives) would send
// Hybrid LTC to "ltc_stress" -- its readiness-stats step, not the page
// (Other Assets and Liabilities) that actually renders its enable toggle.
// Same three-line shape as the "Open HELOC strategy page" button already
// hardcodes on Other Assets and Liabilities (dashboard_decomp_assets_other.js).
const PLAN_FLAG_DESTINATION_STEP = {
  heloc: "heloc_strategy",
  hybrid_ltc_policy: "assets_special",
  daf_giving: "entity_charitable",
  qcd_giving: "entity_charitable",
};

// Group the toggle rows by the catalog's `domain` axis, in DOMAINS order, then
// by demand within a domain so the common features surface first.
//
// `taxonomy` is the server's module_taxonomy payload; a row whose module has
// no catalog entry still renders, under "Other", rather than disappearing --
// a switch that exists in the CSV but not the catalog is exactly the drift
// this page should make visible, not hide.
export function planFeatureGroups(toggleRows, taxonomy, kindFilter) {
  const modules = (taxonomy || {}).modules || {};
  const order = (taxonomy || {}).domains || [];
  const rank = { high: 0, medium_high: 1, medium: 2, low: 3, niche: 4 };
  const byDomain = new Map();
  const seenKeys = new Set();
  (toggleRows || []).forEach((r) => {
    const meta = modules[r.label] || {};
    if (kindFilter && meta.answer_type !== kindFilter) return;
    seenKeys.add(r.label);
    const domain = meta.domain || "Other";
    if (!byDomain.has(domain)) byDomain.set(domain, []);
    byDomain.get(domain).push({ row: r, key: r.label, meta });
  });
  // #330 §5.3 (W9): a plan flag has no client_optional_functions.csv row, so
  // it is invisible to the loop above -- list it from the taxonomy directly.
  // Plan Features must still show it, as a link to the page that owns it,
  // not a toggle (§5.1: "for a plan flag it renders a link... not a toggle").
  Object.keys(modules).forEach((key) => {
    if (seenKeys.has(key)) return;
    const meta = modules[key];
    // WP1.3: a switchable feature with no CSV row is listed the same way.
    if (meta.gate_kind !== "plan_flag" && meta.csv_row !== false) return;
    if (meta.csv_row === false && !meta.optional) return;
    if (kindFilter && meta.answer_type !== kindFilter) return;
    const domain = meta.domain || "Other";
    if (!byDomain.has(domain)) byDomain.set(domain, []);
    byDomain.get(domain).push({ row: null, key, meta });
  });
  const sortedDomains = [...byDomain.keys()].sort((a, b) => {
    const ia = order.indexOf(a),
      ib = order.indexOf(b);
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib) || a.localeCompare(b);
  });
  return sortedDomains.map((domain) => ({
    domain,
    entries: byDomain.get(domain).sort((x, y) => {
      const d = (rank[x.meta.demand] ?? 9) - (rank[y.meta.demand] ?? 9);
      return d || String(x.meta.name || x.key).localeCompare(String(y.meta.name || y.key));
    }),
  }));
}

// The filter chips, labeled with the catalog's user-facing answer-type
// vocabulary (#332 §1.2: Reports/Optimizers/Comparisons/Risks/Reference)
// rather than the raw internal `kind` id -- "stress_test" means nothing to a
// reader, "Risks" does. Only answer types actually present among the toggle
// rows (or a plan flag) get a chip, so the row never offers a filter that
// would empty the page, and chips are ordered by taxonomy.answer_types
// (KIND_LETTER_PREFIX's own order) rather than alphabetically.
export function planFeatureKinds(toggleRows, taxonomy) {
  const modules = (taxonomy || {}).modules || {};
  const order = (taxonomy || {}).answer_types || [];
  const seen = new Set();
  (toggleRows || []).forEach((r) => {
    const answerType = (modules[r.label] || {}).answer_type;
    if (answerType) seen.add(answerType);
  });
  // Plan flags carry an answer type too and now render on this page (see
  // planFeatureGroups) -- a filter chip must include them or a plan flag
  // whose answer type no toggle module shares would become unreachable.
  Object.values(modules).forEach((meta) => {
    if (meta.gate_kind === "plan_flag" && meta.answer_type) seen.add(meta.answer_type);
  });
  return order.filter((at) => seen.has(at));
}

function kindChipsHtml(kinds, active) {
  if (kinds.length < 2) return "";
  // esc(escJs(x)), both layers and in that order: escJs makes x a safe JS
  // string literal, esc then makes that safe as an HTML attribute value. The
  // HTML parser undoes esc first, leaving JS exactly the literal escJs built.
  // One layer alone is not enough here -- domain names carry "&"
  // ("Estate & Legacy", "Family & Business"), which is attribute-level, not
  // JS-level.
  const chip = (kind, label) =>
    `<button class="pf-chip${active === kind ? " active" : ""}" type="button" ` +
    `onclick="setPlanFeatureKind('${esc(escJs(kind))}')">${esc(label)}</button>`;
  return (
    '<div class="pf-chips" role="group" aria-label="Filter by answer type">' +
    chip("", "All") +
    kinds.map((k) => chip(k, k)).join("") +
    "</div>"
  );
}

// Plan rows behind a module, for the entered-data count. Only modules that
// actually gate dashboard input have a declared data location (`csv_sections`
// / `dashboard_step`); most Optimization and Stress modules gate a workbook
// *sheet* and have neither, so they get no count rather than a guessed one.
function moduleOwnedRows(key) {
  const gates = moduleGates || {};
  const sections = Object.keys(gates.section_gates || {}).filter(
    (s) => (gates.section_gates[s] || {}).key === key,
  );
  if (sections.length)
    return (rows || []).filter((r) => sections.includes(String(r.section || "")));
  const step = Object.keys(gates.step_gates || {}).find((s) => gates.step_gates[s] === key);
  if (step) return rowsForStep(step) || [];
  return null;
}

// Shared by featureRowHtml/planFlagRowHtml and the domain "N of M on" count
// below -- a plan-flag entry carries no row (moduleGates has no CSV row to
// read), so its on/off state comes from the live plan data via its gate_ref
// instead of boolishValue(row).
function entryIsOn(entry) {
  if (entry.meta.gate_kind === "plan_flag") {
    const ref = entry.meta.gate_ref || [];
    return ref.length === 3 ? sectionFlagEnabled(ref[0], ref[1], ref[2]) : false;
  }
  if (!entry.row) return entry.meta.default_on !== false;
  return boolishValue(entry.row);
}

// #330 §5.3 (W9): a plan flag's row, on Plan Features. Normally no toggle --
// the switch lives where its data is, and rendering a second writer for the
// same value here is the exact double-gate #330 Q2 removed from DAF. `on`
// reads the live plan row directly (gate_ref is [section, subsection, label],
// exactly sectionFlagEnabled()'s argument tuple), the same way
// strategySectionGatedNote() and rowsForStep()'s generalized HELOC check do.
//
// Ticket 340 makes HELOC the one exception: its switch moved OFF the Home
// Equity Line page onto this one (rowsForStep()'s "heloc_strategy" case now
// excludes the heloc_enabled row, so there is no second writer to double-gate
// against). DAF/QCD/Hybrid LTC keep the link-only rendering below.
function planFlagRowHtml(entry) {
  const meta = entry.meta;
  const ref = meta.gate_ref || [];
  const on = ref.length === 3 ? sectionFlagEnabled(ref[0], ref[1], ref[2]) : false;
  const lbl = meta.name || entry.key;
  const desc = formatAcronyms(meta.description || "");
  const hint = demandHint(meta.demand);

  let html = '<div class="opt-module-row">';
  html += '<div class="opt-module-info"><span class="opt-module-name">' + esc(lbl) + "</span>";
  if (meta.kind) html += '<span class="badge pf-kind">' + esc(meta.answer_type || meta.kind) + "</span>";
  if (hint) html += '<span class="pf-demand">' + esc(hint) + "</span>";
  if (desc) html += '<span class="opt-module-desc">' + esc(desc) + "</span>";
  html += planTierDiffBadgeHtml(entry.key);

  // Every plan flag (HELOC, DAF, QCD, LTC/Life Policy) is switched here and
  // only here; the page that owns its data carries no second switch.
  const row = ref.length === 3
    ? rows.find(
        (r) =>
          isEditable(r) &&
          r.section === ref[0] &&
          norm(r.subsection || "") === norm(ref[1]) &&
          norm(r.label) === norm(ref[2]),
      )
    : null;
  html += "</div>";
  html += row
    ? '<button class="opt-module-toggle ' +
      (on ? "on" : "off") +
      '" type="button" data-requires-app="1" ' +
      'onclick="editValue(' +
      row.row_index +
      ",'" +
      (on ? "NO" : "YES") +
      "',null);saveAll(false);renderMain()\">" +
      (on ? "ON" : "OFF") +
      "</button>"
    : rowlessSwitchHtml(entry.key, on);
  html += "</div>";
  return html;
}

// WP5.1: a switch the plan holds no row for yet is still a switch -- the click
// writes its row through POST /api/plan/feature (module_catalog.set_feature).
function rowlessSwitchHtml(key, on) {
  return (
    `<button class="opt-module-toggle ${on ? "on" : "off"}" type="button" data-requires-app="1" ` +
    `onclick="setPlanFeatureSwitch('${esc(escJs(key))}',${on ? "false" : "true"})">${on ? "ON" : "OFF"}</button>`
  );
}

// WP1.3: a switchable feature with no CSV row (default-on page switch). WP5.1:
// its first flip writes the row (rowlessSwitchHtml); from then on it is an
// ordinary toggle row.
function rowlessFeatureRowHtml(entry) {
  const meta = entry.meta;
  const on = meta.default_on !== false;
  let html = '<div class="opt-module-row">';
  html += '<div class="opt-module-info"><span class="opt-module-name">' + esc(meta.name || entry.key) + "</span>";
  if (meta.kind) html += '<span class="badge pf-kind">' + esc(meta.answer_type || meta.kind) + "</span>";
  const desc = formatAcronyms(meta.description || "");
  if (desc) html += '<span class="opt-module-desc">' + esc(desc) + "</span>";
  html += planTierDiffBadgeHtml(entry.key);
  html += "</div>";
  html += rowlessSwitchHtml(entry.key, on) + "</div>";
  return html;
}

function featureRowHtml(entry) {
  if (entry.meta.gate_kind === "plan_flag") return planFlagRowHtml(entry);
  if (!entry.row) return rowlessFeatureRowHtml(entry);
  const r = entry.row;
  const meta = entry.meta;
  const on = boolishValue(r);
  const status = moduleStatus[entry.key] || {};
  const lbl = meta.name || humanLabel(r.label, r);
  const desc = formatAcronyms(meta.description || r.schema?.description || r.notes || "");
  const hint = demandHint(meta.demand);

  let html = '<div class="opt-module-row">';
  html += '<div class="opt-module-info"><span class="opt-module-name">' + esc(lbl) + "</span>";
  if (meta.kind) html += '<span class="badge pf-kind">' + esc(meta.answer_type || meta.kind) + "</span>";
  if (hint) html += '<span class="pf-demand">' + esc(hint) + "</span>";
  if (desc) html += '<span class="opt-module-desc">' + esc(desc) + "</span>";
  if (status.auto_enabled) {
    html +=
      '<span class="badge auto">Auto-enabled — required by ' +
      esc((status.required_by || []).join(", ")) +
      "</span>";
  }
  // #330 §3.4: what switching this OFF costs elsewhere, from the catalog's
  // reverse degrades_without map. Shown while the module is on, because that
  // is when it is a warning rather than a fact.
  const offImpact = on ? moduleOffImpactWarning(entry.key) : "";
  if (offImpact) html += '<span class="opt-module-off-impact">' + esc(offImpact) + "</span>";
  // #330 §5.4: off, but the household's data is still there.
  if (!on) {
    const owned = moduleOwnedRows(entry.key);
    const n = owned === null ? 0 : enteredRowCount(owned);
    if (n)
      html += '<span class="pf-retained">' + offRowsLabel(n) + "</span>";
    const ignored = engineIgnoredWarning(meta);
    if (ignored) html += '<span class="pf-engine-ignored">' + esc(ignored) + "</span>";
  }
  html += planTierDiffBadgeHtml(entry.key);
  if (status.forced) {
    html +=
      '<span class="badge warn pf-forced">Forced ' +
      esc(status.forced) +
      " by " +
      esc(status.forced_by) +
      "</span>";
  }
  html += "</div>";

  // A forced module renders its state, not a switch: writing the toggle would
  // save a value the build then ignores, which is the disagreement Q7 exists
  // to end.
  if (status.forced) {
    html += '<span class="opt-module-toggle forced" aria-disabled="true">' + (on ? "ON" : "OFF") + "</span>";
  } else {
    html +=
      '<button class="opt-module-toggle ' +
      (on ? "on" : "off") +
      '" type="button" data-requires-app="1" ' +
      'onclick="editValue(' +
      r.row_index +
      ",'" +
      (on ? "NO" : "YES") +
      "',null);saveAll(false);renderMain()\">" +
      (on ? "ON" : "OFF") +
      "</button>";
  }
  html += "</div>";
  return html;
}

// Modules with no dashboard_step of their own whose rows still live on a
// given page, plus hub pages that front several legacy steps.
const PAGE_EXTRA_MODULES = {
  assets_special: ["education_funding_529", "equity_compensation"],
  family_business: ["education_funding_529", "equity_compensation"],
};
const PAGE_STEP_ALIASES = {
  strategy_stress: ["monte_carlo_options", "survivor_stress", "ltc_stress", "divorce_options"],
  strategy_scenarios: ["scenarios"],
};

// Optional features that would add content to `stepId` if they were on.
// Returns [{key, name}] for every owned module that is currently off.
export function offFeaturesForPage(stepId, taxonomy) {
  const modules = (taxonomy || {}).modules || {};
  const steps = new Set([stepId, ...(PAGE_STEP_ALIASES[stepId] || [])]);
  const extra = new Set(PAGE_EXTRA_MODULES[stepId] || []);
  const out = [];
  Object.keys(modules).forEach((key) => {
    const meta = modules[key];
    const isFlag = meta.gate_kind === "plan_flag";
    if (!isFlag && !meta.optional) return;
    const owner = PLAN_FLAG_DESTINATION_STEP[key] || meta.dashboard_step;
    if (!extra.has(key) && !steps.has(owner)) return;
    const on = isFlag
      ? entryIsOn({ meta })
      : optionalFunctionEnabled(key);
    if (!on) out.push({ key, name: meta.name || key });
  });
  return out;
}

// One compact line on a nav page: the optional features that are off and
// would appear here if enabled, with the single link to Plan Features.
export function offFeaturesLineHtml(stepId) {
  if (stepId === "optional_functions") return "";
  const off = offFeaturesForPage(stepId, planModuleTaxonomy());
  if (!off.length) return "";
  return (
    '<div class="section-note pf-off-features">Optional features not enabled that would appear here: ' +
    off.map((f) => esc(f.name)).join(", ") +
    '. <a href="#" onclick="setStep(\'optional_functions\');return false">Turn on in Plan Features</a></div>'
  );
}

export function renderOptionalFunctions() {
  if (searchText.trim()) return renderFields("optional_functions");
  const rs = rowsForStep("optional_functions");
  if (!rs.length)
    return '<div class="section-note">No plan feature rows found. Save Changes to initialize defaults, then reload.</div>';

  const taxonomy = planModuleTaxonomy();
  let html = "";

  const notice = envOverrideNotice(moduleStatus);
  if (notice) html += '<div class="section-note pf-override">' + esc(notice) + "</div>";

  // WP5.1: the tier picker (dashboard_decomp_plan_tiers.js) heads the page.
  html += planTierPickerHtml();

  html += kindChipsHtml(planFeatureKinds(rs, taxonomy), planFeatureKind);

  const groups = planFeatureGroups(rs, taxonomy, planFeatureKind);
  if (!groups.length)
    return html + '<div class="section-note">No features match this filter.</div>';

  groups.forEach(function (g) {
    const open = !planFeatureCollapsed.has(g.domain);
    const onCount = g.entries.filter(entryIsOn).length;
    html +=
      '<div class="pf-group"><button class="pf-group-head" type="button" ' +
      `aria-expanded="${open}" onclick="togglePlanFeatureGroup('${esc(escJs(g.domain))}')">` +
      '<span class="pf-group-name">' +
      esc(g.domain) +
      '</span><span class="pf-group-count">' +
      onCount +
      " of " +
      g.entries.length +
      " on</span></button>";
    if (open) {
      html += '<div class="opt-module-list">';
      g.entries.forEach(function (entry) {
        html += featureRowHtml(entry);
      });
      html += "</div>";
    }
    html += "</div>";
  });
  return html;
}

Object.assign(window, {
  demandHint,
  offFeaturesForPage,
  offFeaturesLineHtml,
  enteredRowCount,
  offRowsLabel,
  engineIgnoredWarning,
  envOverrideNotice,
  moduleOwnedRows,
  planFeatureGroups,
  planFeatureKinds,
  renderOptionalFunctions,
  setPlanFeatureKind,
  togglePlanFeatureGroup,
});
