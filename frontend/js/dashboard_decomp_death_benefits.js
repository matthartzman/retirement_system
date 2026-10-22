// Extracted from dashboard.js by tools/js_codemod/extract_module.mjs.

export function matrixYears(rs) {
  return [
    ...new Set(rs.map((r) => String(r.subsection || "")).filter(Boolean)),
  ].sort(
    (a, b) =>
      (Number(a) || 0) - (Number(b) || 0) || String(a).localeCompare(String(b)),
  );
}

export function matrixPolicies(rs) {
  return [
    ...new Set(rs.map((r) => String(r.label || "")).filter(Boolean)),
  ].sort((a, b) => humanLabel(a).localeCompare(humanLabel(b)));
}

export function findMatrixCell(rs, policy, year) {
  return rs.find(
    (r) => String(r.label) === policy && String(r.subsection) === year,
  );
}

export function renderYearMatrix(section, title, opts = {}) {
  const rs = matrixRows(section);
  if (!rs.length)
    return `<div class="holdings"><h3 class="group-title">${esc(title)}</h3><div class="section-note" data-kind="state">No year-by-year rows were found for ${esc(section)}.</div></div>`;
  const years = matrixYears(rs);
  const policies = matrixPolicies(rs);
  const frozen = opts.frozenLabel || "Policy";
  let html = `<div class="holdings"${opts.helpKey ? ` data-help-section="${opts.helpKey}"` : ""}><h3 class="group-title">${esc(title)}</h3>`;
  html += `<div class="table-actions"><button class="btn" type="button" onclick="openStepHelp(activeStep)">How to use this table</button></div>`;
  html += `<div class="matrix-wrap" role="region" aria-label="${esc(title)} matrix" tabindex="0"><table class="matrix-table"><thead><tr><th>${esc(frozen)}</th>${years.map((y) => `<th>${esc(y)}</th>`).join("")}</tr></thead><tbody>`;
  policies.forEach((pol) => {
    html += `<tr><td><span>${esc(humanLabel(pol))}</span></td>`;
    years.forEach((y) => {
      const r = findMatrixCell(rs, pol, y);
      html += `<td>${r ? `<input type="text" value="${esc(displayValueForInput(r, valOf(r)))}" aria-label="${esc(humanLabel(pol))} ${esc(y)}" oninput="editValue(${r.row_index},this.value,this)" onfocus="beginEdit(${r.row_index},this)" onblur="finishEdit(${r.row_index},this)">` : '<span class="small">—</span>'}</td>`;
    });
    html += "</tr>";
  });
  html += "</tbody></table></div>";
  html += "</div>";
  return html;
}

export function renderDeathBenefitsTable() {
  return renderYearMatrix(
    "Annuity Death Benefits",
    "Annuity death benefits",
    { frozenLabel: "Policy", helpKey: "annuity_death_benefits.annuity_death_benefits" },
  );
}

export function illustrationPlanYears() {
  return matrixYears(matrixRows("Annuity Death Benefits"));
}

export function renderLifeIllustrations() {
  const years = illustrationPlanYears();
  if (!years.length) return "";
  const cashValue = matrixRows("Life Illustration Cash Value");
  const deathBenefit = matrixRows("Life Illustration Death Benefit");
  const premium = matrixRows("Life Illustration Premium");
  if (!cashValue.length && !deathBenefit.length && !premium.length) return "";
  return `<details data-help-section="annuity_death_benefits.life_illustrations"><summary>Life Insurance Illustrations</summary>${renderYearMatrix("Life Illustration Cash Value", "Cash value", { frozenLabel: "Policy", helpKey: "annuity_death_benefits.life_cash_value" })}${renderYearMatrix("Life Illustration Death Benefit", "Death benefit", { frozenLabel: "Policy", helpKey: "annuity_death_benefits.life_death_benefit" })}${renderYearMatrix("Life Illustration Premium", "Premium", { frozenLabel: "Policy", helpKey: "annuity_death_benefits.life_premium" })}</details>`;
}

export function renderSpecialIncomeAnnuitiesInsurance() {
  if (searchText.trim()) return renderFields("annuity_death_benefits");
  return (
    renderDeathBenefitsTable() +
    renderLifeIllustrations() +
    renderInsurancePolicies()
  );
}

// Every export above is also re-attached to window: dashboard.js calls these
// as bare globals, and this file's own rendered HTML uses inline
// onclick="..." handlers, which always resolve through window regardless of
// module scoping. New code should prefer `import` from this module; this
// bridge exists only for callers that cannot move to import in the same pass.
Object.assign(window, {
  matrixYears,
  matrixPolicies,
  findMatrixCell,
  renderYearMatrix,
  renderDeathBenefitsTable,
  illustrationPlanYears,
  renderLifeIllustrations,
  renderSpecialIncomeAnnuitiesInsurance,
});
