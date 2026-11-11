// ── Person, liability, scenario and matrix row helpers (W4-06): extracted verbatim from row_model; bridge below ──
export function renderFields(step) {
  let rs = rowsForStep(step);
  if (searchText.trim()) {
    const q = searchText.toLowerCase();
    rs = rowsForStep(step).filter((r) =>
      [
        r.section,
        r.subsection,
        r.label,
        r.notes,
        r.value,
        r.schema?.description,
      ]
        .join(" ")
        .toLowerCase()
        .includes(q),
    );
  }
  const tierView = fieldTierView(step, rs, !!searchText.trim());
  rs = tierView.rows;
  const missing = rs.filter(isMissing);
  let html = tierView.controlHtml;
  html += missing.length
    ? `<div class="missing-list"><h3>${missing.length} required field${missing.length === 1 ? "" : "s"} missing in this view</h3><ul>${missing
        .slice(0, 8)
        .map((r) => `<li>${esc(humanLabel(r.label, r))}</li>`)
        .join("")}</ul></div>`
    : "";
  if (["assets_special"].includes(step))
    html += `<div class="section-note" data-kind="state" data-help-section="assets_special.reporting_fields">Some fields here are reporting-only. ${window.RPHelp?.sectionButtonHtml("assets_special.reporting_fields") || ""}</div>`;
  // Phase 3b: the prose for these pages lives in HELP_SECTIONS (help_registry.js); the key wraps the page body.
  const helpKey = { scenarios: "strategy_scenarios.stress_rows", roth_conversion: "roth_conversion.bracket_targets", all_assumptions: "all_assumptions.field_list", monte_carlo_options: "strategy_stress.monte_carlo_mode" }[step];
  const wrapHelp = (inner) => (helpKey ? `<div data-help-section="${helpKey}">${inner}</div>` : inner);
  // #330 §5.2 (W12): a step-owning module that is off gets a note, not a
  // blackout -- the earlier hand-written versions of these branches each
  // `return`ed a static "hidden" paragraph in place of the step's rows,
  // which is exactly the no-hidden-data invariant violation §5.2 exists to
  // close (a search hit or a direct step visit must not make already-entered
  // data disappear just because its module is off). featureGatedNote() now
  // supplies the note -- registry-driven, so a plan-flag step (via
  // flag_gates) and a module-toggle step (divorce_qdro/long_term_care_stress/
  // charitable_giving) resolve through the same call -- and rs still renders
  // below it rather than being replaced by it.
  const _flagGate = (moduleGates.flag_gates || {})[step];
  const gateKey = _flagGate
    ? _flagGate.key
    : step === "divorce_options"
      ? "divorce_qdro"
      : step === "ltc_stress"
        ? "long_term_care_stress"
        : null;
  const gateOff = _flagGate
    ? !sectionFlagEnabled(..._flagGate.ref)
    : gateKey
      ? !optionalFunctionEnabled(gateKey)
      : false;
  if (gateKey && gateOff) html += featureGatedNote(gateKey, { rows: rs });
  if (step === "all_assumptions") return wrapHelp(html + renderFieldFinderGroups(rs));
  // #358: the ACA section sits directly above the Tax Assumptions table, which
  // the tax-assumptions module appends after this page's fields.
  if (step === "economic_tax_assumptions") {
    const isAca = (r) => norm(r.subsection).startsWith("aca");
    const aca = rs.filter(isAca);
    if (aca.length)
      return (
        html +
        renderFieldGroups(rs.filter((r) => !isAca(r))) +
        `<div class="field-list"><h3 class="group-title">${esc(friendlyGroup(aca[0]))}</h3>${sortRowsByDependency(aca).map(fieldHtml).join("")}</div>`
      );
  }
  return wrapHelp(html + renderFieldGroups(rs));
}

export function personDisplayName(n) {
  const nick = householdPersonRow(n, "nickname");
  const name = householdPersonRow(n, "name");
  const v =
    String(nick ? valOf(nick) : "").trim() ||
    String(name ? valOf(name) : "")
      .trim()
      .split(/\s+/)[0];
  return v || `Member ${n}`;
}

export function householdPersonRow(n, suffix) {
  return (
    rows.find(
      (r) =>
        isEditable(r) &&
        r.section === "Household" &&
        norm(r.label) === `member_${n}_${suffix}`,
    ) || null
  );
}

export function noteReceivableRows() {
  return rows.filter(isEditable).filter((r) => r.section === "Note Receivable");
}

export function accountDisplayLabel(account) {
  const s = String(account || "");
  const m = /^member[ _]([12])[ _](.+)$/i.exec(s);
  if (!m) return s;
  return (
    personDisplayName(Number(m[1])) + "'s " + m[2].replace(/_/g, " ").trim()
  );
}

export function ensureLiabilityRows() {
  if (liabilityRowsCache) return liabilityRowsCache;
  const lines = String(liabilitiesText || "")
    .split(/\r?\n/)
    .filter((x) => x.trim());
  const parsed = lines.map(parseCsvLine);
  const header = (parsed[0] || LIABILITY_HEADER.slice()).map((x) =>
    String(x || "").trim(),
  );
  // Older files predate the payoff-month / carry-zero columns; add them so edits serialize.
  ["payoff_month", "carry_zero"].forEach((h) => {
    if (!header.includes(h)) header.splice(Math.max(0, header.indexOf("notes")), 0, h);
  });
  const data = (parsed.length > 1 ? parsed.slice(1) : []).map((r) => {
    const o = {};
    header.forEach((h, i) => {
      o[h] = String(r[i] ?? "").trim();
    });
    return o;
  });
  liabilityRowsCache = { header, data };
  return liabilityRowsCache;
}

export function markLiabilitiesDirty() {
  serializeLiabilities();
  liabilitiesChanged = true;
  markBuildStale();
  scheduleStatusUpdate();
}

export function matrixRows(section) {
  const target = norm(section);
  return rows.filter(isEditable).filter((r) => norm(r.section) === target);
}

export function rowByNormLabel(label) {
  const key = norm(label);
  return (
    rawRowsForStep("roth_conversion").find((r) => norm(r.label) === key) ||
    rows.find((r) => isEditable(r) && norm(r.label) === key)
  );
}

export function scenarioRowsForManagement(rs) {
  const input = Array.isArray(rs) ? rs : rawRowsForStep("scenarios");
  return input.filter(
    (r) =>
      String(r.section || "").trim() === "Scenarios" &&
      !rowIsDivorceScenario(r) &&
      norm(r.subsection) !== "base",
  );
}

export function scenarioRowKey(row) {
  return scenarioRowKeyFromParts(
    row && row.section,
    row && row.subsection,
    row && row.label,
  );
}

export function scenarioFieldName(row) {
  return `${friendlyGroup(row)} · ${humanLabel(row.label, row)}`;
}

export function scenarioFindRow(subsection, label) {
  const wanted = scenarioRowKeyFromParts("Scenarios", subsection, label);
  return (
    scenarioRowsForManagement(rawRowsForStep("scenarios")).find(
      (r) => scenarioRowKey(r) === wanted,
    ) || null
  );
}

export function scenarioStoredSets() {
  try {
    const raw = localStorage.getItem(SCENARIO_SET_STORAGE_KEY);
    const arr = JSON.parse(raw || "[]");
    return Array.isArray(arr)
      ? arr.filter((x) => x && Array.isArray(x.items))
      : [];
  } catch (_e) {
    return [];
  }
}

export function mcEngineModeValue() {
  const r =
    rows.find(
      (x) =>
        isEditable(x) &&
        rowIsMonteCarlo(x) &&
        norm(x.label) === "mc_engine_mode",
    ) || rows.find((x) => isEditable(x) && norm(x.label) === "mc_engine_mode");
  const v = String(r ? valOf(r) : "advanced_exact_scalar")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_");
  return v === "quick_vectorized" || v === "vectorized"
    ? "quick_vectorized"
    : "advanced_exact_scalar";
}
Object.assign(window, {
  accountDisplayLabel, ensureLiabilityRows, householdPersonRow, markLiabilitiesDirty, matrixRows,
  mcEngineModeValue, noteReceivableRows, personDisplayName, renderFields, rowByNormLabel,
  scenarioFieldName, scenarioFindRow, scenarioRowKey, scenarioRowsForManagement, scenarioStoredSets,
});
