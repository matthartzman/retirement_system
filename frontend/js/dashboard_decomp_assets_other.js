/* Assets & Protection: liabilities, note receivables, 529 education accounts,
   and the "other assets" item table -- extracted from dashboard.js by
   tools/js_codemod/extract_module.mjs.

   First domain cluster of the Wave 6.4 domain-module split (see
   docs/superpowers/specs/2026-08-10-dashboard-js-split-codemod-design.md),
   following the shared-core extraction that produced
   dashboard_decomp_row_model.js. Selected as a connected component of
   dashboard.js's internal call graph (tools/js_codemod/find_clusters.mjs),
   stable across fan-in cutoffs 3 through 8.

   Loaded BEFORE dashboard.js, in the same position as
   dashboard_decomp_row_model.js -- not after it with the other leaves.
   dashboard.js ends its module body with a queueMicrotask() that schedules the
   real boot work, and a microtask checkpoint runs after that script's
   evaluation, so it can fire before a LATER module script has evaluated. This
   module's own top level is nothing but declarations and one Object.assign, so
   it has no evaluation-time dependency on dashboard.js and is safe to run
   first.

   The four constant tables (LIABILITY_LABELS, LIABILITY_TYPES,
   LIABILITY_TYPE_FIELDS, OTHER_ASSET_TYPES) moved with the code: they are read
   by this cluster and by nothing else anywhere in the repo, so leaving them in
   dashboard.js would have stranded them behind four generated window accessors
   that exist to serve exactly one other file.

   What this module still reaches back into dashboard.js for, all through the
   generated window bridge and all verified present before this pass landed:
   the function renderMain (a reassigned monkey-patch chain, exposed via a get
   accessor, so a bare call here gets the live decorated implementation), the
   read-only state rows/searchText/planSource/dirty, and the writable state
   activeStep/lastBuildOk (both `let`, both with set accessors). */

export const OTHER_ASSET_TYPES = [
  "Auto",
  "Boat",
  "Start-up Equity",
  "Art",
  "Collectible",
  "Other",
];

export function otherAssetRows() {
  return rows
    .filter(isEditable)
    .filter(
      (r) =>
        r.section === "Other Assets" &&
        norm(r.subsection).startsWith("other_asset"),
    );
}

export function otherAssetSubsections() {
  return [
    ...new Set(
      otherAssetRows()
        .map((r) => String(r.subsection || ""))
        .filter(Boolean),
    ),
  ].sort((a, b) => {
    const na = Number((a.match(/(\d+)/) || [])[1] || 0),
      nb = Number((b.match(/(\d+)/) || [])[1] || 0);
    return na - nb || a.localeCompare(b);
  });
}

export function otherAssetRow(sub, label) {
  return otherAssetRows().find(
    (r) => r.subsection === sub && norm(r.label) === norm(label),
  );
}

export function otherAssetTypeCell(r) {
  if (!r) return '<span class="small">—</span>';
  const cur = String(valOf(r) || "").trim();
  return `<select data-row="${r.row_index}" onchange="editValue(${r.row_index},this.value,this)" onfocus="showFieldHelp(${r.row_index})">${OTHER_ASSET_TYPES.map((t) => `<option value="${esc(t)}" ${norm(t) === norm(cur) ? "selected" : ""}>${esc(t)}</option>`).join("")}</select>`;
}

export function otherAssetInputCell(sub, label, placeholder = "") {
  const r = otherAssetRow(sub, label);
  if (!r) return '<span class="small">—</span>';
  return `<input class="year-cell" type="${isDateField(r) ? "date" : "text"}" value="${esc(displayValueForInput(r, valOf(r)))}" placeholder="${esc(placeholder || r.schema?.default || "")}" oninput="editValue(${r.row_index},this.value,this)" onfocus="beginEdit(${r.row_index},this)" onblur="finishEdit(${r.row_index},this)">`;
}

export function renderOtherAssetItemsTable() {
  const subs = otherAssetSubsections();
  let html = `<details><summary>Other Asset Items</summary><div class="field-list"><div class="section-note">One row per non-portfolio asset — auto, boat, start-up equity, art, or collectible. Enter today's estimated value and as-of date. Use a positive annual rate for appreciating assets (e.g., collectibles, equity) and a negative rate for depreciating ones (e.g., vehicles).</div>`;
  html += `<div class="table-actions"><select id="newOtherAssetType">${OTHER_ASSET_TYPES.map((t) => `<option value="${esc(t)}">${esc(t)}</option>`).join("")}</select><button class="btn" type="button" data-requires-app="1" onclick="addOtherAssetItem()">Add asset</button></div>`;
  if (!subs.length) {
    return (
      html +
      "<p>No typed other assets yet. Add an asset to track an auto, boat, start-up equity, art, or other non-portfolio item.</p></div></details>"
    );
  }
  html += `<div class="matrix-wrap" role="region" aria-label="Other assets" tabindex="0"><table class="matrix-table"><thead><tr><th>Type</th><th>Name</th><th>Value</th><th>As-of date</th><th>Annual +/- %</th><th>Basis</th><th>Sell date</th><th></th></tr></thead><tbody>`;
  subs.forEach((sub) => {
    html += `<tr><td>${otherAssetTypeCell(otherAssetRow(sub, "type"))}</td><td>${otherAssetInputCell(sub, "name")}</td><td>${otherAssetInputCell(sub, "value")}</td><td>${otherAssetInputCell(sub, "as_of_date")}</td><td>${otherAssetInputCell(sub, "annual_appreciation_pct")}</td><td>${otherAssetInputCell(sub, "basis")}</td><td>${otherAssetInputCell(sub, "sell_date")}</td><td><button class="danger-link" type="button" onclick="deleteOtherAssetItem('${escJs(sub)}')">Delete</button></td></tr>`;
  });
  html +=
    '</tbody></table></div><p class="small">For appreciating assets such as start-up equity, art, or collectibles, enter a basis when you know the purchase price or tax basis. For depreciating assets, basis can be left blank unless it matters for a later sale scenario.</p></div></details>';
  return html;
}

export async function addOtherAssetItem() {
  try {
    const typ =
      (document.getElementById("newOtherAssetType") || {}).value || "Auto";
    const out = await api("/api/other-asset/add", {
      method: "POST",
      body: JSON.stringify({ asset_type: typ }),
    });
    await loadAll({ source: planSource, preferLocal: false, silent: true });
    activeStep = "assets_special";
    showMessage(out.message || "Other asset added.");
  } catch (e) {
    showMessage("Error adding other asset: " + e.message, "error");
  }
}

export async function deleteOtherAssetItem(subsection) {
  if (!subsection) return;
  if (
    !(await showInAppConfirm("This cannot be undone.", {
      title: "Delete Asset",
      confirmLabel: "Delete",
      variant: "danger",
    }))
  )
    return;
  try {
    const out = await api("/api/other-asset/delete", {
      method: "POST",
      body: JSON.stringify({ subsection }),
    });
    dirty.clear();
    lastBuildOk = false;
    await loadAll({ source: planSource, preferLocal: false, silent: true });
    activeStep = "assets_special";
    renderMain();
    showMessage(out.message || "Other asset deleted.");
  } catch (e) {
    showMessage("Error deleting other asset: " + e.message, "error");
  }
}

export function noteReceivableSubsections() {
  return [
    ...new Set(
      noteReceivableRows()
        .map((r) => String(r.subsection || ""))
        .filter((sub) => /^Note\s+\d+$/i.test(sub) || sub === "Summary"),
    ),
  ].sort((a, b) => {
    const na = Number((a.match(/(\d+)/) || [])[1] || 0),
      nb = Number((b.match(/(\d+)/) || [])[1] || 0);
    return na - nb || a.localeCompare(b);
  });
}

export function noteReceivableRow(sub, label) {
  return noteReceivableRows().find(
    (r) => r.subsection === sub && norm(r.label) === norm(label),
  );
}

export function renderNoteInterestTable(sub) {
  const interestSub =
    sub === "Summary" ? "Interest by Year" : `${sub} Interest`;
  const rs = rows
    .filter(isEditable)
    .filter(
      (r) => r.section === "Note Receivable" && r.subsection === interestSub,
    );
  if (!rs.length) return "";
  const years = [
    ...new Set(rs.map((r) => String(r.label || "")).filter(Boolean)),
  ].sort(
    (a, b) =>
      (Number(a) || 0) - (Number(b) || 0) || String(a).localeCompare(String(b)),
  );
  let html = `<div class="section-note"><b>Interest by year:</b> Enter the expected taxable interest income from this note for each calendar year. This affects cash flow, taxable income, NIIT exposure, and projected note income.</div><div class="matrix-wrap" role="region" aria-label="Note receivable interest schedule" tabindex="0"><table class="matrix-table"><thead><tr><th>Schedule</th>${years.map((y) => `<th>${esc(y)}</th>`).join("")}</tr></thead><tbody><tr><td>Interest income</td>`;
  years.forEach((y) => {
    const r = rs.find((x) => String(x.label) === String(y));
    html += `<td>${r ? `<input class="year-cell" type="text" value="${esc(displayValueForInput(r, valOf(r)))}" aria-label="Note interest ${esc(y)}" oninput="editValue(${r.row_index},this.value,this)" onfocus="beginEdit(${r.row_index},this)" onblur="finishEdit(${r.row_index},this)">` : '<span class="small">—</span>'}</td>`;
  });
  html += `</tr></tbody></table></div><p class="small">Years run across the top. Enter dollars for each year the note is expected to pay interest.</p>`;
  return html;
}

export function renderNoteReceivableTable() {
  const subs = noteReceivableSubsections();
  let html = `<div class="section-note">One or more promissory notes receivable. Each note has a descriptive name plus its own face value, payment schedule, and interest-by-year detail. The current note is named "RedMane Note".</div>`;
  html += `<div class="table-actions"><button class="btn" type="button" data-requires-app="1" onclick="addNoteReceivable()">Add note</button></div>`;
  if (!subs.length)
    return (
      html +
      "<p>No notes receivable yet. Add a note to track a promissory note.</p>"
    );
  subs.forEach((sub) => {
    const nameRow = noteReceivableRow(sub, "name");
    const label = nameRow ? String(valOf(nameRow) || sub) : sub;
    const body =
      noteReceivableRows()
        .filter((r) => r.subsection === sub && norm(r.label) !== "name")
        .map(fieldHtml)
        .join("") + renderNoteInterestTable(sub);
    html += `<details><summary><span>${esc(label)}</span> <button class="danger-link" type="button" onclick="deleteNoteReceivable('${escJs(sub)}')">Delete</button></summary><div class="field-list">${nameRow ? fieldHtml(nameRow) : ""}${body}</div></details>`;
  });
  return html;
}

export async function addNoteReceivable() {
  try {
    const out = await api("/api/note-receivable/add", {
      method: "POST",
      body: JSON.stringify({}),
    });
    await loadAll({ source: planSource, preferLocal: false, silent: true });
    activeStep = "assets_special";
    showMessage(out.message || "Note added.");
  } catch (e) {
    showMessage("Error adding note: " + e.message, "error");
  }
}

export async function deleteNoteReceivable(subsection) {
  if (!subsection) return;
  if (
    !(await showInAppConfirm("This cannot be undone.", {
      title: "Delete Note",
      confirmLabel: "Delete",
      variant: "danger",
    }))
  )
    return;
  try {
    const out = await api("/api/note-receivable/delete", {
      method: "POST",
      body: JSON.stringify({ subsection }),
    });
    dirty.clear();
    lastBuildOk = false;
    await loadAll({ source: planSource, preferLocal: false, silent: true });
    activeStep = "assets_special";
    renderMain();
    showMessage(out.message || "Note deleted.");
  } catch (e) {
    showMessage("Error deleting note: " + e.message, "error");
  }
}

export function renderHsaPolicyOnOtherAssets(rs) {
  const gr = (rs || []).filter((r) => r.section === "HSA Policy");
  if (!gr.length) return "";
  const modeRow = gr.find(
    (r) =>
      norm(r.subsection) === "withdrawals" &&
      norm(r.label) === "hsa_withdrawal_mode",
  );
  // #213: hsa_withdrawal_end_year sorted before hsa_withdrawal_start_year
  // under the generic dependency sort's alphabetical tie-break ("end" < "start"
  // lexicographically) -- force chronological order for this one pair.
  const withdrawalRows = sortRowsByDependency(
    gr.filter((r) => norm(r.subsection) === "withdrawals"),
  ).sort((a, b) => {
    const rank = (r) =>
      norm(r.label) === "hsa_withdrawal_start_year"
        ? 0
        : norm(r.label) === "hsa_withdrawal_end_year"
          ? 1
          : -1;
    return rank(a) - rank(b);
  });
  const contribRows = sortRowsByDependency(
    gr.filter((r) => norm(r.subsection) === "contributions"),
  );
  const rolloverRows = sortRowsByDependency(
    gr.filter((r) => norm(r.subsection) === "spousal_rollover"),
  );
  const otherRows = sortRowsByDependency(
    gr.filter(
      (r) =>
        !["withdrawals", "contributions", "spousal_rollover"].includes(
          norm(r.subsection),
        ),
    ),
  );
  // #213: one collapsible HSA section instead of up to 4 -- compact
  // sub-headings inside, not separate nested <details>.
  let body = `<div class="section-note"><b>Withdrawal timing:</b> choose how the HSA is used in Cash Flow. <b>Spend as needed</b> uses HSA for qualified Wellness costs/gaps. <b>Annual percentage</b> and <b>Smooth window</b> use the start/end years below to schedule HSA withdrawals across the cash-flow projection.</div>${withdrawalRows.map(fieldHtml).join("")}`;
  if (contribRows.length)
    body += `<h4 class="group-title">Contributions</h4><div class="section-note">Contribution limits and eligibility feed annual HSA additions before Medicare eligibility.</div>${contribRows.map(fieldHtml).join("")}`;
  if (rolloverRows.length)
    body += `<h4 class="group-title">Spousal Rollover</h4>${rolloverRows.map(fieldHtml).join("")}`;
  if (otherRows.length)
    body += `<h4 class="group-title">Other HSA controls</h4>${otherRows.map(fieldHtml).join("")}`;
  return `<details><summary>HSA</summary><div class="field-list">${body}</div></details>`;
}

export function renderAssetsSpecial() {
  if (searchText.trim()) return renderFields("assets_special");
  const rs = rowsForStep("assets_special");
  const groups = [
    "Other Asset Items",
    "Note Receivable",
    "HSA",
    "529 Plans",
    "Equity Compensation",
    "LTC/Life Policy",
  ];
  let html = "";
  groups.forEach((g, idx) => {
    const gr = rs.filter((r) => friendlyGroup(r) === g);
    if (g === "Other Asset Items") {
      html += renderOtherAssetItemsTable();
      return;
    }
    if (g === "Note Receivable") {
      html += `<details><summary>Note Receivable</summary><div class="field-list">${renderNoteReceivableTable()}</div></details>`;
      return;
    }
    if (g === "HSA") {
      html += renderHsaPolicyOnOtherAssets(rs);
      html += renderHsaSchedule();
      return;
    }
    if (g === "529 Plans") {
      if (optionalFunctionEnabled(rowModuleGate("Education Funding").key)) {
        html += `<details><summary>529 Plans</summary><div class="field-list"><div class="section-note"><b>Purpose:</b> 529 plans are education savings accounts. Enter one section per beneficiary or goal, then add another 529 when a different beneficiary or goal should be tracked separately.</div>${gr.map(fieldHtml).join("")}<div class="table-actions"><button class="btn" type="button" data-requires-app="1" onclick="addEducation529Section()">Add 529 section</button></div></div></details>`;
      }
      return;
    }
    if (g === "LTC/Life Policy" && !ltcLifePolicyModuleEnabled()) return;
    if (
      g === "Equity Compensation" &&
      !optionalFunctionEnabled(rowModuleGate("Equity Compensation").key)
    )
      return;
    if (gr.length)
      html += `<details><summary>${esc(g)}</summary><div class="field-list">${gr.map(fieldHtml).join("")}</div></details>`;
  });
  html += renderHELOCInputsOnOtherPage();
  html += renderLiabilitiesTable();
  return html || '<div class="field-list"><p>No fields in this step.</p></div>';
}

export async function addEducation529Section() {
  try {
    const out = await api("/api/education-529/add", {
      method: "POST",
      body: JSON.stringify({}),
    });
    await loadAll({ source: planSource, preferLocal: false, silent: true });
    activeStep = "assets_special";
    showMessage(out.message || "529 section added.");
  } catch (e) {
    showMessage("Error adding 529 section: " + e.message, "error");
  }
}

export function renderHELOCInputsOnOtherPage() {
  const rs = rows.filter(
    (r) => isEditable(r) && r.section === "HELOC" && r.subsection === "Setup",
  );
  if (!rs.length) return "";
  const enabledRow = rs.find((x) => norm(x.label) === "heloc_enabled");
  if (!helocModuleEnabled())
    return enabledRow
      ? `<details><summary>HELOC modeling inputs</summary><div class="field-list"><div class="section-note">HELOC strategy is turned off. Turn it on below to reveal the borrowing assumptions.</div>${fieldHtml(enabledRow)}</div></details>`
      : "";
  const ordered = [
    "heloc_enabled",
    "heloc_credit_limit",
    "heloc_draw_end_year",
    "heloc_initial_rate_pct",
    "heloc_rate_drift_bps_yr",
    "heloc_repayment_years",
  ];
  const list = [];
  ordered.forEach((l) => {
    const r = rs.find((x) => norm(x.label) === l);
    if (r) list.push(r);
  });
  rs.forEach((r) => {
    if (!list.includes(r)) list.push(r);
  });
  // #214: this used to fully duplicate the HELOC Strategy page's editable
  // fields here too (same rows, so edits never went out of sync, but two
  // full edit forms for one set of terms reads as redundant). Read-only
  // summary + a link to the one place to actually change it.
  const summaryRows = list
    .map(
      (r) =>
        `<div class="impact-row"><span>${esc(humanLabel(r.label, r))}</span><strong>${esc(displayValueForInput(r, valOf(r)) || "—")}</strong></div>`,
    )
    .join("");
  return `<details><summary>HELOC modeling inputs</summary><div class="field-list"><div class="section-note"><b>Read-only summary</b> — shown here with other liabilities so the borrowing assumption is not stranded on the Strategy page; edit on the HELOC Strategy page.</div>${summaryRows}<div class="table-actions"><button class="btn" type="button" data-step-id="heloc_strategy">Open HELOC strategy page</button></div></div></details>`;
}

export const LIABILITY_TYPES = [
  { v: "auto", t: "Auto loan" },
  { v: "heloc", t: "HELOC" },
  { v: "student_loan", t: "Student loan" },
  { v: "other", t: "Other" },
];

export const LIABILITY_LABELS = {
  liability_id: "ID",
  type: "Type",
  label: "Name",
  balance: "Balance",
  interest_rate: "Interest rate %",
  monthly_payment: "Monthly payment",
  start_year: "Start year",
  payoff_year: "Payoff year",
  notes: "Notes",
};

export const LIABILITY_TYPE_FIELDS = {
  auto: ["balance", "interest_rate", "monthly_payment", "payoff_year"],
  heloc: [
    "balance",
    "interest_rate",
    "monthly_payment",
    "start_year",
    "payoff_year",
  ],
  student_loan: ["balance", "interest_rate", "monthly_payment", "payoff_year"],
  other: [
    "balance",
    "interest_rate",
    "monthly_payment",
    "start_year",
    "payoff_year",
  ],
};

export function liabilityFieldsForType(type) {
  return (
    LIABILITY_TYPE_FIELDS[String(type || "other").toLowerCase()] ||
    LIABILITY_TYPE_FIELDS.other
  );
}

export function updateLiability(i, col, val) {
  const d = ensureLiabilityRows().data;
  if (d[i]) {
    d[i][col] = val;
    markLiabilitiesDirty();
  }
}

export function setLiabilityType(i, val) {
  const d = ensureLiabilityRows().data;
  if (d[i]) {
    d[i].type = val;
    markLiabilitiesDirty();
    renderMain();
  }
}

export function addLiability() {
  const h = ensureLiabilityRows();
  const row = {};
  h.header.forEach((c) => (row[c] = ""));
  row.liability_id = "liab_" + Date.now().toString(36);
  row.type = "auto";
  row.label = "";
  h.data.push(row);
  markLiabilitiesDirty();
  renderMain();
  setTimeout(() => {
    const f = document.querySelector('.lot-table input[data-lcol="label"]');
    if (f) f.focus();
  }, 0);
}

export async function deleteLiability(i) {
  if (
    !(await showInAppConfirm("This cannot be undone.", {
      title: "Delete Liability",
      confirmLabel: "Delete",
      variant: "danger",
    }))
  )
    return;
  ensureLiabilityRows().data.splice(i, 1);
  markLiabilitiesDirty();
  renderMain();
}

export function renderLiabilitiesTable() {
  const h = ensureLiabilityRows();
  const cols = [
    "label",
    "balance",
    "interest_rate",
    "monthly_payment",
    "start_year",
    "payoff_year",
    "notes",
  ];
  let html = `<details><summary>Liabilities</summary><div class="field-list"><div class="section-note"><b>Purpose:</b> Track loans the plan must pay down over time. Choose a type, then enter the fields needed to forecast its cash flow. Each liability is amortized into the yearly cash-flow forecast and its outstanding balance reduces net worth. Auto and student loans use standard fixed amortization; HELOC line items amortize over the years to payoff. Leave a field blank to use sensible defaults (no monthly payment = interest-only unless a payoff year is set).</div><div class="table-actions"><button class="btn" type="button" data-requires-app="1" onclick="addLiability()">Add liability</button></div><div class="lot-table-wrap"><table class="lot-table"><thead><tr><th>Type</th>${cols.map((c) => `<th>${esc(LIABILITY_LABELS[c] || humanLabel(c))}</th>`).join("")}<th>Actions</th></tr></thead><tbody>`;
  if (!h.data.length) {
    html += `<tr><td colspan="${cols.length + 2}"><span class="small">No liabilities yet. Click "Add liability" to add one.</span></td></tr>`;
  }
  h.data.forEach((r, i) => {
    const type = String(r.type || "other").toLowerCase();
    const allowed = liabilityFieldsForType(type);
    html += "<tr>";
    html += `<td data-label="Type"><select onchange="setLiabilityType(${i},this.value)">${LIABILITY_TYPES.map((o) => `<option value="${o.v}" ${type === o.v ? "selected" : ""}>${esc(o.t)}</option>`).join("")}</select></td>`;
    cols.forEach((c) => {
      const lbl = esc(LIABILITY_LABELS[c] || humanLabel(c));
      if (c === "label" || c === "notes") {
        html += `<td data-label="${lbl}"><input data-lcol="${esc(c)}" type="text" value="${esc(r[c] || "")}" oninput="updateLiability(${i},'${esc(c)}',this.value)"></td>`;
        return;
      }
      const shown = allowed.includes(c);
      if (!shown) {
        html += `<td data-label="${lbl}"><span class="small">—</span></td>`;
        return;
      }
      const isMoney = c === "balance" || c === "monthly_payment";
      const isYear = c === "start_year" || c === "payoff_year";
      if (isMoney) {
        html += `<td data-label="${lbl}"><input class="tiny" data-lcol="${esc(c)}" type="text" value="${esc(currencyDisplay(r[c] || ""))}" oninput="updateLiability(${i},'${esc(c)}',currencyRaw(this.value))" onfocus="this.value=currencyRaw(this.value);this.select&&this.select()" onblur="this.value=currencyDisplay(this.value)"></td>`;
      } else if (isYear) {
        html += `<td data-label="${lbl}"><input class="tiny" data-lcol="${esc(c)}" type="number" step="1" value="${esc(r[c] || "")}" oninput="updateLiability(${i},'${esc(c)}',this.value)"></td>`;
      } else {
        html += `<td data-label="${lbl}"><input class="tiny" data-lcol="${esc(c)}" type="number" step="0.01" value="${esc(r[c] || "")}" oninput="updateLiability(${i},'${esc(c)}',this.value)"></td>`;
      }
    });
    html += `<td data-label="Actions"><button class="danger-link" onclick="deleteLiability(${i})">Delete</button></td></tr>`;
  });
  html += `</tbody></table></div></div></details>`;
  return html;
}

// Every export above is also re-attached to window: dashboard.js calls these
// as bare globals, and this file's own rendered HTML uses inline
// onclick="..." handlers, which always resolve through window regardless of
// module scoping. New code should prefer `import` from this module; this
// bridge exists only for callers that cannot move to import in the same pass.
Object.assign(window, {
  OTHER_ASSET_TYPES,
  otherAssetRows,
  otherAssetSubsections,
  otherAssetRow,
  otherAssetTypeCell,
  otherAssetInputCell,
  renderOtherAssetItemsTable,
  addOtherAssetItem,
  deleteOtherAssetItem,
  noteReceivableSubsections,
  noteReceivableRow,
  renderNoteInterestTable,
  renderNoteReceivableTable,
  addNoteReceivable,
  deleteNoteReceivable,
  renderHsaPolicyOnOtherAssets,
  renderAssetsSpecial,
  addEducation529Section,
  renderHELOCInputsOnOtherPage,
  LIABILITY_TYPES,
  LIABILITY_LABELS,
  LIABILITY_TYPE_FIELDS,
  liabilityFieldsForType,
  updateLiability,
  setLiabilityType,
  addLiability,
  deleteLiability,
  renderLiabilitiesTable,
});
