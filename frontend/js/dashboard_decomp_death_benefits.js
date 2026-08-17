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

export function renderYearMatrix(section, title, intro, opts = {}) {
  const rs = matrixRows(section);
  if (!rs.length)
    return `<div class="holdings"><h3 class="group-title">${esc(title)}</h3><div class="section-note">No year-by-year rows were found for ${esc(section)}.</div></div>`;
  const years = matrixYears(rs);
  const policies = matrixPolicies(rs);
  const frozen = opts.frozenLabel || "Policy";
  let html = `<div class="holdings"><h3 class="group-title">${esc(title)}</h3><div class="section-note">${esc(intro)}</div>`;
  html += `<div class="table-actions"><button class="btn" type="button" onclick="showStepHelp(activeStep)">How to use this table</button></div>`;
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
  html += `<p class="small">Tip: use <span class="kbd">Tab</span> or <span class="kbd">Return</span> to move across the editable year cells. Scroll horizontally to reach later years; the ${esc(frozen.toLowerCase())} column remains visible.</p>`;
  html += "</div>";
  return html;
}

export function renderDeathBenefitsTable() {
  return renderYearMatrix(
    "Annuity Death Benefits",
    "Annuity death benefits",
    "Each row is a separate annuity policy. Each column is a calendar year. Enter the benefit payable to heirs if death occurs in that year.",
    { frozenLabel: "Policy" },
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
  return `<details><summary>Life Insurance Illustrations</summary><div class="section-note">Enter values from each Life policy's carrier illustration for the years shown. Each policy below matches a policy added under Insurance Policies.</div>${renderYearMatrix("Life Illustration Cash Value", "Cash value", "Cash surrender value in each year, per the illustration.", { frozenLabel: "Policy" })}${renderYearMatrix("Life Illustration Death Benefit", "Death benefit", "Death benefit payable to beneficiaries in each year, per the illustration.", { frozenLabel: "Policy" })}${renderYearMatrix("Life Illustration Premium", "Premium", "Premium due in each year, per the illustration.", { frozenLabel: "Policy" })}</details>`;
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
