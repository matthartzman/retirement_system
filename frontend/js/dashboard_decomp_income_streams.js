// Extracted from dashboard.js by tools/js_codemod/extract_module.mjs.

export function findRows(sectionName, subsectionName, labels) {
  return labels
    .map((l) => findEditableRow(sectionName, subsectionName, l))
    .filter(Boolean);
}

export function ssPersonRows(person) {
  return findRows("Social Security", person, [
    "claim_age",
    "monthly_pia_at_fra_today_dollars",
    "fra_age",
  ]);
}

export function ssActiveCell(row) {
  if (!row) return '<span class="small">Missing</span>';
  return fieldControlOnly(row);
}

export function ssClaimFactor(claimAge, fra) {
  const months = Math.round((Number(claimAge || fra) - fra) * 12);
  if (months >= 0) return 1.0 + months * (0.08 / 12.0);
  const early = Math.abs(months);
  const first36 = Math.min(36, early) * (5.0 / 900.0);
  const extra = Math.max(0, early - 36) * (5.0 / 1200.0);
  return Math.max(0.0, 1.0 - first36 - extra);
}

export function ssMonthlyAtClaimAgeCell(person, claimAgeRow) {
  if (!claimAgeRow) return '<span class="small">Missing</span>';
  const age = Math.max(
    62,
    Math.min(70, Math.round(fieldNumericValue(claimAgeRow) || 70)),
  );
  const benefitRow = findEditableRow(
    "Social Security",
    person,
    `ss_benefit_age_${age}`,
  );
  const amount = benefitRow ? fieldNumericValue(benefitRow) : 0;
  if (benefitRow && amount)
    return `<span class="computed-value">${esc(fmtMoney(amount))}</span>`;
  // No SSA-quoted figure for this exact age — derive it from FRA/PIA using
  // the SSA reduction/delayed-credit factor instead of just asking the user
  // to fill in the table, so a claim-age change always shows a value.
  const fraRow = findEditableRow("Social Security", person, "fra_age");
  const fra = (fraRow ? fieldNumericValue(fraRow) : 0) || 67;
  const piaRow = findEditableRow(
    "Social Security",
    person,
    "monthly_pia_at_fra_today_dollars",
  );
  const age67Row = findEditableRow("Social Security", person, "ss_benefit_age_67");
  const pia =
    (piaRow ? fieldNumericValue(piaRow) : 0) ||
    (age67Row ? fieldNumericValue(age67Row) : 0);
  if (!pia)
    return `<span class="small">Enter Monthly at FRA</span>`;
  const derived = pia * ssClaimFactor(age, fra);
  return `<span class="computed-value">~${esc(fmtMoney(derived))} <span class="small">(derived from FRA)</span></span>`;
}

export function renderSsCompactTable() {
  const people = [
    { key: "Member 1", n: 1 },
    { key: "Member 2", n: 2 },
  ];
  let html = `<div class="holdings retirement-income-section"><h3 class="group-title">Social Security</h3><div class="section-note">Enter each person’s FRA Age, Monthly at FRA, and claiming age. Monthly at Claim Age is calculated: it’s looked up from a saved SSA benefit-table entry for that exact age when available, otherwise it’s derived from FRA Age and Monthly at FRA using the SSA reduction/delayed-credit factor. FRA Age defaults to 67 (SSA birth-year rule) if left blank.</div><div class="lot-table-wrap"><table class="lot-table compact-table ss-compact-table"><thead><tr><th>Person</th><th>FRA Age</th><th>Monthly at FRA</th><th>Claim Age</th><th>Monthly at Claim Age</th></tr></thead><tbody>`;
  people.forEach((p) => {
    const r = ssPersonRows(p.key);
    const by = {};
    r.forEach((x) => (by[norm(x.label)] = x));
    html += `<tr><td><b>${esc(personDisplayName(p.n))}</b></td><td>${ssActiveCell(by.fra_age)}</td><td>${ssActiveCell(by.monthly_pia_at_fra_today_dollars)}</td><td>${ssActiveCell(by.claim_age)}</td><td>${ssMonthlyAtClaimAgeCell(p.key, by.claim_age)}</td></tr>`;
  });
  return html + "</tbody></table></div></div>";
}

export function fieldControlOnly(r) {
  const html = fieldHtml(r);
  const m = html.match(
    /<div>(<input[\s\S]*?<\/input>|<select[\s\S]*?<\/select>|<input[\s\S]*?>)(?:<div class="unit">[\s\S]*?<\/div>)?<\/div><\/div>$/,
  );
  if (m) return m[1];
  const wrap = document.createElement("div");
  wrap.innerHTML = html;
  const ctrl = wrap.querySelector("input,select,textarea");
  return ctrl ? ctrl.outerHTML : html;
}

export function incomeStreamSubsections() {
  return [
    ...new Set(
      rows
        .filter(isEditable)
        .filter(
          (r) =>
            r.section === "Income Streams" &&
            ![
              "joint_and_survivor_percentage",
              "recovery_age",
            ].includes(norm(r.subsection)),
        )
        .map((r) => String(r.subsection || ""))
        .filter(Boolean),
    ),
  ];
}

export function renderIncomeStreamsSection() {
  const globalRows = findRows(
    "Income Streams",
    "Joint-and-Survivor Percentage",
    ["js_pct"],
  )
    .concat(
      findRows("Income Streams", "Recovery Age", ["principal_recovery_age"]),
    )
    // #236: moved from Economic and Tax Assumptions -- these are annuity-wide
    // defaults, not per-stream Income Streams rows, so they're looked up by
    // their actual Economic Assumptions section/subsection.
    .concat(
      findRows("Economic Assumptions", "", [
        "annuity_default_dividend_rate",
        "annuity_default_additional_income_pct",
      ]),
    );
  let html = `<div class="holdings retirement-income-section"><h3 class="group-title">Pensions and annuities</h3><div class="section-note">Each card starts with Type, then the payment and valuation fields for that income stream. Recovery Age is the age at which each stream's cash dividend payout stops (the guaranteed payment continues for life).</div>`;
  incomeStreamSubsections().forEach((sub) => {
    let rs = rows
      .filter(isEditable)
      .filter((r) => r.section === "Income Streams" && r.subsection === sub);
    const typeRow = rs.find((r) => norm(r.label) === "type");
    rs = rs.filter((r) => norm(r.label) !== "type");
    const ordered = [...(typeRow ? [typeRow] : []), ...rs];
    html += `<details><summary>${esc(translatePersonPlaceholders(sub))}</summary><div class="field-list">${ordered.map(fieldHtml).join("")}</div></details>`;
  });
  if (globalRows.length)
    html += `<details><summary>Plan-wide income stream settings</summary><div class="field-list">${globalRows.map(fieldHtml).join("")}</div></details>`;
  return html + "</div>";
}

export function renderSsPolicySection() {
  const compactLabels = new Set([
    "claim_age",
    "monthly_pia_at_fra_today_dollars",
    "fra_age",
  ]);
  // Per-age SSA benefit-table entries (62-70) still drive the Monthly at
  // Claim Age lookup in the compact table above and the engine's benefit
  // calculation, but are not shown as an editable table on this page.
  const hiddenLabels = new Set(
    Array.from({ length: 9 }, (_, i) => `ss_benefit_age_${62 + i}`),
  );
  const excludedSubs = new Set(["funding discount"]);
  const rs = rows
    .filter(isEditable)
    .filter(
      (r) =>
        r.section === "Social Security" &&
        !compactLabels.has(norm(r.label)) &&
        !hiddenLabels.has(norm(r.label)) &&
        !excludedSubs.has(String(r.subsection || "").toLowerCase()),
    );
  const fundingRows = [
    findEditableRow("Social Security", "Funding Discount", "ss_funding_discount_year"),
    findEditableRow("Social Security", "Funding Discount", "ss_funding_discount_pct"),
  ].filter(Boolean);
  if (!rs.length && !fundingRows.length) return "";
  const bySub = {};
  rs.forEach((r) => {
    const k = String(r.subsection || "");
    (bySub[k] = bySub[k] || []).push(r);
  });
  if (fundingRows.length) {
    const policyKey =
      Object.keys(bySub).find((k) => k.toLowerCase() === "policy") || "Policy";
    bySub[policyKey] = (bySub[policyKey] || []).concat(fundingRows);
  }
  let html = `<div class="holdings retirement-income-section"><h3 class="group-title">Social Security policy &amp; benefit details</h3><div class="section-note">Household-wide spousal, survivor, and funding-discount policy settings.</div>`;
  Object.keys(bySub).forEach((sub) => {
    if (sub && sub.toLowerCase() !== "policy")
      html += `<div class="subsection-label">${esc(friendlyGroup({ section: "Social Security", subsection: sub }) || sub)}</div>`;
    html += `<div class="field-list inline-row">${bySub[sub].map(fieldHtml).join("")}</div>`;
  });
  return html + "</div>";
}

export function renderRetirementIncome() {
  const ssInner = renderSsCompactTable() + renderSsPolicySection();
  const ssSummary =
    "Claim ages, FRA, per-age benefit tables, spousal/survivor policy, and funding discount";
  const ssSection =
    `<details class="allocation-policy-collapsed"><summary><b>Social Security</b><span class="small" style="margin-left:8px;font-weight:normal;color:var(--muted)">${esc(ssSummary)}</span></summary>` +
    ssInner +
    "</details>";
  return ssSection + renderIncomeStreamsSection();
}

// Every export above is also re-attached to window: dashboard.js calls these
// as bare globals, and this file's own rendered HTML uses inline
// onclick="..." handlers, which always resolve through window regardless of
// module scoping. New code should prefer `import` from this module; this
// bridge exists only for callers that cannot move to import in the same pass.
Object.assign(window, {
  findRows,
  ssPersonRows,
  ssActiveCell,
  ssClaimFactor,
  ssMonthlyAtClaimAgeCell,
  renderSsCompactTable,
  fieldControlOnly,
  incomeStreamSubsections,
  renderIncomeStreamsSection,
  renderSsPolicySection,
  renderRetirementIncome,
});
