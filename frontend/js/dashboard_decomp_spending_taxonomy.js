/* Spending setup and taxonomy: the category/group taxonomy manager, category
   mapping rules, domain budget tables, and the unified core-spending view --
   extracted from dashboard.js by tools/js_codemod/extract_module.mjs.

   Second domain cluster of the Wave 6.4 domain-module split (see
   docs/superpowers/specs/2026-08-10-dashboard-js-split-codemod-design.md),
   following dashboard_decomp_assets_other.js. Selected as a connected component
   of dashboard.js's internal call graph (tools/js_codemod/find_clusters.mjs):
   39 declarations, the largest coherent single-domain component remaining.

   Loaded BEFORE dashboard.js, in the same position as
   dashboard_decomp_row_model.js and dashboard_decomp_assets_other.js -- not
   after them with the other leaves. dashboard.js ends its module body with a
   queueMicrotask() that schedules the real boot work, and a microtask
   checkpoint runs after that script's evaluation, so it can fire before a LATER
   module script has evaluated. This module's own top level is nothing but
   declarations and one Object.assign, so it has no evaluation-time dependency
   on dashboard.js and is safe to run first.

   What this module still reaches back into dashboard.js for, all through the
   generated window bridge. Enumerated by walking the moved declarations' text
   against dashboard.js's top-level bindings, so this list is exhaustive as of
   this pass rather than illustrative:

     - the function renderMain (a reassigned monkey-patch chain, exposed via a
       get accessor, so a bare call here gets the live decorated implementation);

     - four WRITTEN state variables -- budgetLines, mappingRules, rulesChanged,
       taxBudgetChanged. All four are `let` in dashboard.js and all four get a
       set accessor from convert_dashboard.mjs. A bare assignment from inside
       this module is legal despite module strict mode precisely because the
       bridge has already defined the property on window: strict mode only
       throws for an identifier that resolves to nothing at all, and these
       resolve to the global accessor pair. Remove a setter and the assignment
       starts throwing, so the bridge is load-bearing here, not cosmetic;

     - thirteen read-only state variables -- categoryBudgetMode, groupBudgetMode,
       rows, searchText, spendingModelData, spendingModelError,
       spendingModelLoading, taxBudget, taxBudgetLoaded, taxonomyData,
       taxonomyError, taxonomyFlat, taxonomyLoading.

   No constants moved with this cluster: unlike the assets cluster, every
   constant table it reads is shared with other parts of dashboard.js and so
   had to stay behind. */

export function updateTaxBudgetMoney(catId, field, el) {
  updateTaxBudget(catId, field, budgetMoneyNumber(el && el.value));
}

export function updateCategoryDetailMoney(lineId, field, el, catId) {
  updateCategoryDetail(
    lineId,
    field,
    String(budgetMoneyNumber(el && el.value)),
    catId,
  );
}

export function coreSpendingGrowthMode() {
  const r =
    findEditableRow("Cashflow", "Spending", "core_spending_growth_mode") ||
    rows.find(
      (x) => isEditable(x) && norm(x.label) === "core_spending_growth_mode",
    );
  const v = String(r ? valOf(r) : "cpi")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_");
  return v === "manual" || v === "manual_override" ? "manual_override" : "cpi";
}

export function renderSpendingCore() {
  if (searchText.trim()) return renderFields("spending_core");
  /* DAF contributions are intentionally routed to Charitable Giving, not Core Spending. */ const rs =
    rowsForStep("spending_core").filter(
      (r) => norm(r.label) !== "daf_annual_contribution",
    );
  const mode = coreSpendingGrowthMode();
  const hidden = new Set([
    "core_spending_manual_growth_rate",
    "inflation_general",
    "daf_annual_contribution",
    "annual_charitable_giving_low",
    "annual_charitable_giving_high",
  ]);
  const labels =
    mode === "manual_override"
      ? [
          "core_spending_growth_mode",
          "annual_spending_base_year",
          "spending_freeze_year",
          "core_spending_manual_growth_rate",
        ]
      : [
          "core_spending_growth_mode",
          "annual_spending_base_year",
          "spending_freeze_year",
          "inflation_general",
        ];
  const ordered = [];
  labels.forEach((l) => {
    const r = rs.find((x) => norm(x.label) === norm(l));
    if (r) ordered.push(r);
  });
  rs.forEach((r) => {
    if (!ordered.includes(r) && !hidden.has(norm(r.label))) ordered.push(r);
  });
  const have = Object.fromEntries(
    [
      "annual_spending_base_year",
      "core_spending_growth_mode",
      "core_spending_manual_growth_rate",
      "inflation_general",
      "spending_freeze_year",
    ].map((l) => [l, !!rs.find((x) => norm(x.label) === norm(l))]),
  );
  let missingMsg = "";
  if (
    !have.core_spending_growth_mode ||
    !have.spending_freeze_year ||
    (!have.inflation_general && mode === "cpi") ||
    (!have.core_spending_manual_growth_rate && mode === "manual_override")
  )
    missingMsg = `<div class="section-note warning" id="coreSpendingRowsMissing"><b>Core spending controls are being created:</b> save or reload Plan Data if any control is missing. Expected rows are Core Spending Base, Core Spending Increase Stops, Core Spending Increase Method, and the relevant increase-rate field.</div>`;
  let html = `<div class="section-note"><b>Projection controls:</b> Core spending base/growth controls feed recurring lifestyle spending. The category hierarchy below is the comprehensive income/expense model except taxes/transfers. Category assignment happens here; Accounts & Sources lives on Income & Expense Transactions.</div>${missingMsg}`;
  html += `<div class="field-list core-spending-flat">${ordered.map(fieldHtml).join("")}</div>`;
  return html;
}

export function renderTaxonomyManager() {
  if (!taxonomyData && !taxonomyLoading && !taxonomyError) {
    setTimeout(() => loadTaxonomy(false), 0);
  }
  let html =
    '<div class="holdings taxonomy-manager"><h3 class="group-title">Category Manager</h3>';
  html +=
    '<div class="section-note">Manage the canonical <b>Tracking Type → Group → Category</b> tree. Transaction assignment uses these canonical categories, so there is no separate group-mapping table to maintain.</div>';
  if (taxonomyLoading) {
    html += '<div class="question"><b>Loading taxonomy…</b></div>';
  } else if (taxonomyError && !taxonomyData) {
    html += `<div class="missing-list"><p>${esc(taxonomyError)}</p></div><button class="btn" onclick="loadTaxonomy(true)">Retry</button>`;
  } else if (taxonomyData) {
    html +=
      '<div class="table-actions"><button class="btn" onclick="showTaxonomyAddForm()">+ Add Category</button><button class="btn" onclick="loadTaxonomy(true)">Reload</button></div>';
    html += '<div id="taxonomyAddForm" style="display:none"></div>';
    html += '<div class="taxonomy-tree">';
    (taxonomyData || []).forEach(function (typeData) {
      const totalCats = (typeData.groups || []).reduce(
        (s, g) => s + (g.categories || []).length,
        0,
      );
      html += `<details class="taxonomy-type-section"><summary><b>${esc(typeData.tracking_type)}</b> <span class="small">(${totalCats} categories)</span></summary>`;
      (typeData.groups || []).forEach(function (grp) {
        html += `<div class="taxonomy-group"><h4 class="taxonomy-group-title">${esc(grp.group)} <span class="small">(${(grp.categories || []).length})</span></h4>`;
        html +=
          '<table class="lot-table taxonomy-cat-table"><thead><tr><th>ID</th><th>Label</th><th>Notes</th><th></th></tr></thead><tbody>';
        (grp.categories || []).forEach(function (cat) {
          html += `<tr><td><code class="small">${esc(cat.id)}</code></td><td>${esc(cat.label)}</td><td class="small">${esc(cat.notes || "")}</td><td><button class="danger-link" onclick="deleteTaxonomyCat('${esc(cat.id)}','${esc(cat.label)}')">Delete</button></td></tr>`;
        });
        html += "</tbody></table></div>";
      });
      html += "</details>";
    });
    html += "</div>";
  } else {
    html +=
      '<div class="question"><b>No taxonomy loaded.</b> <button class="btn" onclick="loadTaxonomy(true)">Load Taxonomy</button></div>';
  }
  html +=
    '<details class="advanced-mapping-rules" style="margin-top:32px"><summary><b>Advanced Auto-Mapping Rules</b><span class="small" style="margin-left:8px;font-weight:400;color:var(--muted)">merchant/category text rules</span></summary>' +
    renderCategoryMappingRules() +
    "</details>";
  html += "</div>";
  return html;
}

export function showTaxonomyAddForm() {
  const form = document.getElementById("taxonomyAddForm");
  if (!form) return;
  const types = taxonomyData || [];
  let typeOpts = types
    .map(
      (t) =>
        `<option value="${esc(t.tracking_type)}">${esc(t.tracking_type)}</option>`,
    )
    .join("");
  form.style.display = "block";
  form.innerHTML = `<div class="taxonomy-add-inner" style="padding:12px;border:1px solid var(--line);border-radius:6px;margin:12px 0"><h4>Add Custom Category</h4><div class="field-row" style="display:flex;gap:12px;align-items:center;margin:6px 0"><label style="width:120px">Tracking Type</label><select id="taxAddType" onchange="updateTaxAddGroups()">${typeOpts}</select></div><div class="field-row" style="display:flex;gap:12px;align-items:center;margin:6px 0"><label style="width:120px">Group</label><select id="taxAddGroup"></select><span class="small" style="margin-left:8px">or new: <input id="taxAddNewGroup" placeholder="New group name" style="width:160px"></span></div><div class="field-row" style="display:flex;gap:12px;align-items:center;margin:6px 0"><label style="width:120px">Category key</label><input id="taxAddId" placeholder="e.g. my_category (lowercase_underscores)" style="width:220px" oninput="this.value=this.value.replace(/[^a-z0-9_]/g,'')"></div><div class="field-row" style="display:flex;gap:12px;align-items:center;margin:6px 0"><label style="width:120px">Label</label><input id="taxAddLabel" placeholder="Display name" style="width:220px"></div><div class="field-row" style="display:flex;gap:12px;align-items:center;margin:6px 0"><label style="width:120px">Notes</label><input id="taxAddNotes" placeholder="Optional description" style="width:220px"></div><div class="table-actions"><button class="btn primary" onclick="submitAddTaxonomy()">Add Category</button><button class="btn" onclick="document.getElementById('taxonomyAddForm').style.display='none'">Cancel</button></div></div>`;
  updateTaxAddGroups();
}

export function updateTaxAddGroups() {
  const typeEl = document.getElementById("taxAddType");
  const groupEl = document.getElementById("taxAddGroup");
  if (!typeEl || !groupEl) return;
  const sel = typeEl.value;
  const typeData = (taxonomyData || []).find((t) => t.tracking_type === sel);
  const groups = typeData ? (typeData.groups || []).map((g) => g.group) : [];
  groupEl.innerHTML = groups
    .map((g) => `<option value="${esc(g)}">${esc(g)}</option>`)
    .join("");
}

export async function reloadDomainBudget(domain) {
  clearSpendingCaches();
  await Promise.all([
    loadTaxonomy(true),
    loadSpendingModel(true),
    loadBudgetLines(true),
    loadTaxonomyBudget(true),
  ]);
  renderMain();
}

export function currentSpendingTreeForDomain(domain) {
  const wanted = new Set(trackingBudgetTypesForDomain(domain));
  const modelTypes =
    spendingModelData && Array.isArray(spendingModelData.tracking_types)
      ? spendingModelData.tracking_types
      : [];
  if (modelTypes.length) {
    return modelTypes.filter((t) => wanted.has(t.tracking_type));
  }
  return (taxonomyData || []).filter((t) => wanted.has(t.tracking_type));
}

export function dollars0(v) {
  return "$" + Math.round(budgetMoneyNumber(v) || 0).toLocaleString();
}

export async function submitAddTaxonomy() {
  const tt = ((document.getElementById("taxAddType") || {}).value || "").trim();
  const newGrp = (
    (document.getElementById("taxAddNewGroup") || {}).value || ""
  ).trim();
  const grp =
    newGrp ||
    ((document.getElementById("taxAddGroup") || {}).value || "").trim();
  const catId = (
    (document.getElementById("taxAddId") || {}).value || ""
  ).trim();
  const label = (
    (document.getElementById("taxAddLabel") || {}).value || ""
  ).trim();
  const notes = (
    (document.getElementById("taxAddNotes") || {}).value || ""
  ).trim();
  if (!tt || !grp || !catId || !label) {
    showMessage(
      "Tracking Type, Group, Category key, and Label are all required.",
      "error",
    );
    return;
  }
  try {
    const out = await api("/api/spending/taxonomy/category", {
      method: "POST",
      body: JSON.stringify({
        tracking_type: tt,
        group: grp,
        id: catId,
        label: label,
        notes: notes,
      }),
    });
    if (out && out.success) {
      showMessage('Category "' + label + '" added.');
      await Promise.all([loadTaxonomy(true), loadSpendingModel(true)]);
    } else
      showMessage((out && out.error) || "Failed to add category.", "error");
  } catch (e) {
    showMessage("Error: " + e.message, "error");
  }
}

export async function deleteTaxonomyCat(catId, label) {
  if (
    !(await showInAppConfirm(
      '"' + label + '" (' + catId + ") will be permanently deleted.",
      { title: "Delete Category", confirmLabel: "Delete", variant: "danger" },
    ))
  )
    return;
  try {
    const out = await api(
      "/api/spending/taxonomy/category/" + encodeURIComponent(catId),
      { method: "DELETE" },
    );
    if (out && out.success) {
      showMessage("Category deleted.");
      await Promise.all([loadTaxonomy(true), loadSpendingModel(true)]);
    } else showMessage((out && out.error) || "Failed to delete.", "error");
  } catch (e) {
    showMessage("Error: " + e.message, "error");
  }
}

export async function deleteTaxonomyGroup(tt, grp) {
  if (
    !(await showInAppConfirm('"' + grp + '" will be removed from ' + tt + ".", {
      title: "Delete Group",
      confirmLabel: "Delete",
      variant: "danger",
    }))
  )
    return;
  try {
    const out = await api("/api/spending/taxonomy/group", {
      method: "DELETE",
      body: JSON.stringify({ tracking_type: tt, group: grp }),
    });
    if (out && out.success) {
      showMessage("Group deleted.");
      await Promise.all([loadTaxonomy(true), loadSpendingModel(true)]);
    } else
      showMessage((out && out.error) || "Failed to delete group.", "error");
  } catch (e) {
    showMessage("Error: " + e.message, "error");
  }
}

export async function loadMappingRules(force) {
  if (mappingRules && !force) return;
  try {
    const out = await api("/api/spending/rules");
    mappingRules = out && out.success ? out.rules || [] : [];
    if (!taxonomyFlat || !Object.keys(taxonomyFlat).length)
      await loadTaxonomy(false);
  } catch (e) {
    mappingRules = [];
  }
  renderMain();
}

export function addMappingRule() {
  if (!mappingRules) mappingRules = [];
  mappingRules.unshift({
    keyword: "",
    category_id: "",
    match_field: "category",
    exact: false,
    priority: 50,
  });
  rulesChanged = true;
  renderMain();
}

export function updateMappingRule(i, field, val) {
  if (!mappingRules || !mappingRules[i]) return;
  mappingRules[i][field] = val;
  rulesChanged = true;
}

export function deleteMappingRule(i) {
  if (!mappingRules) return;
  mappingRules.splice(i, 1);
  rulesChanged = true;
  renderMain();
}

export function renderCategoryMappingRules() {
  if (!mappingRules && !rulesChanged) {
    setTimeout(() => loadMappingRules(false), 0);
  }
  let html =
    '<div class="holdings"><h3 class="group-title">Advanced Auto-Mapping Rules</h3>';
  html +=
    '<div class="section-note">Optional rules auto-assign imported merchant or category text to a canonical Spending Category. Most users should use the category picker in Spending Categories; use these rules only when the same text should be classified automatically every time.</div>';
  const rules = mappingRules || [];
  html +=
    '<div class="table-actions"><button class="btn" onclick="addMappingRule()">+ Add rule</button>';
  html += `<button class="btn primary" ${rulesChanged ? "" : "disabled"} onclick="saveMappingRulesData()">Save Changes</button>`;
  html +=
    '<button class="btn" onclick="loadMappingRules(true)">Reload</button></div>';
  html +=
    '<div class="lot-table-wrap pinned-col-right"><table class="lot-table"><thead><tr><th>Match text</th><th>Match source</th><th style="width:64px">Exact?</th><th>Target category</th><th>Priority</th><th style="width:64px"></th></tr></thead><tbody>';
  if (!rules.length) {
    html +=
      '<tr><td colspan="6" class="small" style="padding:12px">No auto-mapping rules defined. Add a rule only for merchant/category text that should be classified the same way every time.</td></tr>';
  } else {
    const catIds = Object.keys(taxonomyFlat || {}).sort((a, b) =>
      a.localeCompare(b),
    );
    rules.forEach(function (rule, i) {
      const current = String(rule.category_id || "");
      let opts = catIds
        .map(
          (id) =>
            `<option value="${esc(id)}" ${id === current ? "selected" : ""}>${esc(id)}${taxonomyFlat[id] && taxonomyFlat[id].label ? " — " + esc(taxonomyFlat[id].label) : ""}</option>`,
        )
        .join("");
      if (current && !catIds.includes(current))
        opts =
          `<option value="${esc(current)}" selected>${esc(current)}</option>` +
          opts;
      html += `<tr><td><input value="${esc(rule.keyword)}" oninput="updateMappingRule(${i},'keyword',this.value)" style="width:160px"></td><td><select onchange="updateMappingRule(${i},'match_field',this.value)"><option value="category"${rule.match_field === "category" ? " selected" : ""}>Category text</option><option value="merchant"${rule.match_field === "merchant" ? " selected" : ""}>Merchant text</option></select></td><td style="width:64px;text-align:center"><input type="checkbox" ${rule.exact ? "checked" : ""} onchange="updateMappingRule(${i},'exact',this.checked)"></td><td><select onchange="updateMappingRule(${i},'category_id',this.value)" style="min-width:260px"><option value="" ${current ? "" : "selected"}>Select category…</option>${opts}</select></td><td><input type="number" value="${rule.priority || 50}" oninput="updateMappingRule(${i},'priority',parseInt(this.value)||50)" style="width:70px"></td><td style="width:64px;white-space:nowrap"><button class="danger-link" onclick="deleteMappingRule(${i})">Delete</button></td></tr>`;
    });
  }
  html += "</tbody></table></div></div>";
  return html;
}

export function groupCatIds(tt, grp) {
  const ids = [];
  (taxonomyData || []).forEach((t) => {
    if (t.tracking_type === tt)
      (t.groups || []).forEach((g) => {
        if (g.group === grp)
          (g.categories || []).forEach((c) => ids.push(c.id));
      });
  });
  return ids;
}

export function groupEffectiveBudget(tt, grp) {
  if (groupIsSummary(tt, grp)) {
    const gk = groupKeyFor(tt, grp);
    if (hasExplicitBudget(gk)) return budgetAmount(taxBudget[gk].annual_budget);
    return groupCatSum(tt, grp);
  }
  return groupCatSum(tt, grp);
}

export function spendingRowYtd(row) {
  return budgetAmount(
    row && (row.ytd_actual !== undefined ? row.ytd_actual : row.actual),
  );
}

export function spendingRowAnnualized(row) {
  return budgetAmount(
    row &&
      (row.annualized_actual !== undefined
        ? row.annualized_actual
        : row.annualized),
  );
}

export function spendingRowBudget(row) {
  return budgetAmount(
    row && (row.annual_budget !== undefined ? row.annual_budget : row.budget),
  );
}

export function spendingRowProjectionSeed(row) {
  return budgetAmount(
    row &&
      (row.projection_seed !== undefined
        ? row.projection_seed
        : row.annual_budget !== undefined
          ? row.annual_budget
          : row.budget),
  );
}

export function setGroupBudgetMode(tt, grp, mode) {
  groupBudgetMode[tt + "::" + grp] = mode;
  const gk = groupKeyFor(tt, grp);
  if (mode === "summary") {
    const sum = groupCatSum(tt, grp);
    if (!taxBudget[gk]) taxBudget[gk] = { annual_budget: 0, notes: "" };
    if (!(Number(taxBudget[gk].annual_budget) > 0))
      taxBudget[gk].annual_budget = Math.round(sum);
    taxBudget[gk]._mode = "summary";
  } else {
    if (taxBudget[gk]) taxBudget[gk]._mode = "detail";
  }
  taxBudgetChanged = true;
  syncTaxonomyBudgetToBudgetLines();
  markBudgetLinesDirty();
  renderMain();
}

export function addGroupDetailRow(tt, grp) {
  const cats = groupCatIds(tt, grp);
  const catId = cats[0] || "";
  budgetLines.push({
    section: "category_budget",
    line_id: "cb_" + (Date.now() % 1000000),
    label: "",
    category_id: catId,
    start_year: "",
    end_year: "",
    one_time_year: "",
    amount_per_year: "",
    mode: "detail",
    notes: "",
  });
  if (catId) {
    categoryBudgetMode[catId] = "detail";
    syncCategoryTotal(catId);
  }
  markBudgetLinesDirty();
  renderMain();
}

export function updateGroupDetailCategory(lineId, newCatId, oldCatId) {
  const l = budgetLines.find((x) => x.line_id === lineId);
  if (!l) return;
  l.category_id = newCatId;
  if (newCatId) {
    categoryBudgetMode[newCatId] = "detail";
    syncCategoryTotal(newCatId);
  }
  if (oldCatId && oldCatId !== newCatId) syncCategoryTotal(oldCatId);
  markBudgetLinesDirty();
  renderMain();
}

export function deleteCategoryDetailRow(lineId, catId) {
  budgetLines = budgetLines.filter((l) => l.line_id !== lineId);
  syncCategoryTotal(catId);
  markBudgetLinesDirty();
  renderMain();
}

export async function loadAnnualizedActuals() {
  if (
    !(await showInAppConfirm(
      "Load annualized current spend into EVERY category budget? This overwrites all category totals and adds any new transaction categories to the taxonomy.",
      {
        title: "Load Annualized Actuals",
        confirmLabel: "Load",
        variant: "warn",
      },
    ))
  )
    return;
  try {
    const out = await api("/api/spending/budget/load-actuals", {
      method: "POST",
      body: JSON.stringify({}),
    });
    if (!out || out.success === false)
      throw new Error((out && out.error) || "Failed to load actuals.");
    const a = out.actuals || {};
    Object.keys(a).forEach((id) => {
      const v = Math.round(Number(a[id]) || 0);
      if (!taxBudget[id]) taxBudget[id] = { annual_budget: 0, notes: "" };
      taxBudget[id].annual_budget = v;
      if (!taxBudget[id].notes) taxBudget[id].notes = "Annualized actual";
    });
    taxBudgetChanged = true;
    await loadTaxonomy(true);
    await saveTaxonomyBudgetData();
    showMessage(
      (out.merged_count
        ? out.merged_count +
          " new transaction categor" +
          (out.merged_count > 1 ? "ies" : "y") +
          " merged. "
        : "") + "Annualized actuals loaded into category budgets.",
    );
    renderMain();
  } catch (e) {
    showMessage("Error loading actuals: " + e.message, "error");
  }
}

export function trackingBudgetTypesForDomain(domain) {
  if (domain === "core")
    return [
      "Core Expenses",
      "Wellness",
      "Housing",
      "Travel",
      "Large Discretionary",
      "Business",
    ];
  if (domain === "housing") return ["Housing"];
  if (domain === "healthcare") return ["Wellness"];
  if (domain === "travel") return ["Travel"];
  if (domain === "large_discretionary") return ["Large Discretionary"];
  return [];
}

export function loadTemplateGroup(tt, grp) {
  api("/api/spending/restore-template", {
    method: "POST",
    body: JSON.stringify({ tracking_type: tt, group: grp }),
  })
    .then(function (out) {
      if (out && out.success) {
        showMessage(
          (out.count || 0) + " template categories loaded for " + grp + ".",
        );
        clearSpendingCaches();
        loadTaxonomy(true);
        loadSpendingModel(true);
        loadTaxonomyBudget(true);
        loadBudgetLines(true);
      } else
        showMessage(
          (out && out.error) || "Unable to load template categories.",
          "error",
        );
    })
    .catch(function (e) {
      showMessage("Error loading template categories: " + e.message, "error");
    });
}

export function renderDomainBudgetTable(domain) {
  if (!taxBudgetLoaded) {
    setTimeout(() => loadTaxonomyBudget(false), 0);
  }
  if (!spendingModelData && !spendingModelLoading) {
    setTimeout(() => loadSpendingModel(false), 0);
  }
  const data = currentSpendingTreeForDomain(domain);
  if (spendingModelError && !data.length)
    return (
      '<div class="missing-list"><p>' +
      esc(spendingModelError) +
      '</p><button class="btn" onclick="reloadDomainBudget(\'' +
      esc(domain) +
      "')\">Reload</button></div>"
    );
  if (!data.length)
    return (
      '<div class="question"><b>No ' +
      esc(domainBudgetTitle(domain)) +
      ' transaction categories loaded.</b><p class="small">Spending Categories shows Tracking Types, Groups, and Categories with non-zero YTD Actual, Annualized Actual, Annual Budget, or Projection Seed. Use Income &amp; Expense Transactions to import transactions, or add budget/projection values on the source page, then Reload.</p></div>'
    );
  let grandTotal = 0;
  data.forEach(function (t) {
    (t.groups || []).forEach(function (g) {
      grandTotal += groupEffectiveBudget(t.tracking_type, g.group);
    });
  });
  let html = "";
  if (domain === "core") {
    html += `<details class="section-note help-detail"><summary style="cursor:pointer;font-weight:500;list-style:none;display:flex;align-items:center;gap:6px"><span style="font-size:13px">▸</span> Annual Budget vs. Projection Seed — when do they differ?</summary><div style="margin-top:8px"><p class="small"><b>Annual Budget</b> is what you entered. <b>Projection Seed</b> is what the engine uses as the year-one spending base for that category. In most cases they are equal. They diverge in four scenarios:</p><ul class="small" style="margin:6px 0 0 18px;line-height:1.8"><li><b>Cap/reference categories</b> (e.g., Medical OOP Cap in Wellness): Annual Budget holds the cap value so you can see it; Projection Seed is forced to <b>$0</b> because a cap is a ceiling on out-of-pocket costs, not a recurring spending input.</li><li><b>Group in Summary mode</b>: The single group-level override number becomes the Projection Seed for the whole group. Any per-category Annual Budget values that were entered before switching to Summary are stale — the engine ignores them and uses the group total.</li><li><b>Detail-line total disagrees with the Annual Budget override</b>: In Detail mode, Projection Seed equals the sum of the detail lines. If you also typed a manual value in the Annual field, it is stored but overridden by the line sum in the projection.</li><li><b>$0 budget categories with transaction history</b>: The category appears in the table because transactions were imported, but Projection Seed = $0, so it contributes nothing to the projected spend base.</li></ul><p class="small" style="margin-top:8px">The <b>Projection Seed</b> column in each group header shows the value that feeds the projection. If it looks wrong compared to Annual Budget, check whether Summary mode is active or whether a cap/reference flag is set on that category.</p></div></details>`;
  }
  // #1000: bulk "overwrite every category budget with its annualized current
  // spend". Shown only on the core domain because it rewrites EVERY category
  // in the taxonomy, not just the domain being viewed -- repeating it on each
  // domain tab would imply a per-domain scope it does not have.
  //
  // Deliberately NOT guarded by readOnlyRef: that const is declared per
  // tracking type inside the data.forEach below (it means "this tracking type
  // is budgeted on its source page"), so it is both out of scope here and the
  // wrong question to ask -- there is no workspace-wide read-only mode. The
  // showInAppConfirm() inside loadAnnualizedActuals is the guard.
  if (domain === "core") {
    html += `<div class="table-actions"><button class="btn" type="button" onclick="loadAnnualizedActuals()" title="Overwrite every category budget with its annualized current-year spend; new transaction categories are merged into the taxonomy">Load annualized current spend</button> <span class="small" style="color:var(--muted)">Overwrites all category budgets across every tracking type.</span></div>`;
  }
  html += '<div class="taxonomy-tree">';
  data.forEach(function (typeData) {
    const tt = typeData.tracking_type;
    let ttTotal = 0,
      ttActual = 0,
      ttAnnualized = 0,
      ttProjection = 0;
    (typeData.groups || []).forEach((g) => {
      const eff = groupEffectiveBudget(tt, g.group);
      ttTotal += eff;
      ttProjection += spendingRowProjectionSeed(g) || eff;
      ttActual += spendingRowYtd(g);
      ttAnnualized += spendingRowAnnualized(g);
    });
    const readOnlyRef =
      domain === "core" && ["Housing", "Wellness", "Travel"].includes(tt);
    html += `<details class="taxonomy-type-section" data-dkey="budget:${esc(domain)}:${esc(tt)}"><summary><b>${esc(tt)}</b> <span class="small">YTD ${dollars0(ttActual)} · Annualized ${dollars0(ttAnnualized)} · Budget ${dollars0(ttTotal)} · Projection Seed ${dollars0(ttProjection || ttTotal)}</span>${tt === "Business" ? ` <span class="small" style="font-weight:400;color:var(--muted)">modeled; excluded from core spend base</span>` : ""}${readOnlyRef ? ` <span class="small" style="font-weight:400;color:var(--muted)">read-only reference</span>` : ""}</summary>`;
    if (readOnlyRef)
      html +=
        '<div class="section-note">This Tracking Type is budgeted on its source page. Values appear here as read-only reference so Spending Categories remains comprehensive without creating duplicate inputs.</div>';
    (typeData.groups || []).forEach(function (grp) {
      const gname = grp.group;
      const gj = esc(gname).replace(/'/g, "\\'");
      const gmode = groupIsSummary(tt, gname) ? "summary" : "detail";
      const gk = groupKeyFor(tt, gname);
      const catSum = groupCatSum(tt, gname);
      const eff = groupEffectiveBudget(tt, gname);
      const catCount = (grp.categories || []).length;
      html += `<div class="taxonomy-group"><h4 class="taxonomy-group-title" style="display:flex;align-items:center;gap:8px;flex-wrap:wrap"><span>${esc(gname)}</span><span class="small" style="font-weight:400">YTD ${dollars0(spendingRowYtd(grp))} · Annualized ${dollars0(spendingRowAnnualized(grp))} · Budget ${dollars0(eff)} · Projection Seed ${dollars0(spendingRowProjectionSeed(grp) || eff)}</span><span style="margin-left:auto"><button class="btn" style="padding:0 8px" ${readOnlyRef ? "disabled " : ""}onclick="loadTemplateGroup('${esc(tt)}','${gj}')">Load template categories for group</button> ${catCount === 0 ? `<button class="danger-link" style="font-size:11px" onclick="deleteTaxonomyGroup('${esc(tt)}','${gj}')">Delete group</button>` : ""} <button class="btn ${gmode === "summary" ? "primary" : ""}" style="padding:0 8px" ${readOnlyRef ? "disabled " : ""}onclick="setGroupBudgetMode('${esc(tt)}','${gj}','summary')">Summary</button> <button class="btn ${gmode === "detail" ? "primary" : ""}" style="padding:0 8px" ${readOnlyRef ? "disabled " : ""}onclick="setGroupBudgetMode('${esc(tt)}','${gj}','detail')">Detail</button></span></h4>`;
      if (gmode === "summary") {
        // #231: Travel/Large Discretionary group budgets are time-bounded in
        // the projection (spending_budget_resolver.py TIME_BOUNDED_LINE_TRACKING_TYPES)
        // -- only these two tracking types honor start/end year on the group
        // row, so only show the fields where they actually take effect.
        const gYearFields = ["Travel", "Large Discretionary"].includes(tt)
          ? `<label class="small">Start year&nbsp;</label><input ${readOnlyRef ? "disabled " : ""}type="number" value="${esc((taxBudget[gk] || {}).start_year || "")}" placeholder="plan start" oninput="updateTaxBudget('${esc(gk)}','start_year',this.value)" style="width:90px"> <label class="small">End year&nbsp;</label><input ${readOnlyRef ? "disabled " : ""}type="number" value="${esc((taxBudget[gk] || {}).end_year || "")}" placeholder="plan end" oninput="updateTaxBudget('${esc(gk)}','end_year',this.value)" style="width:90px"> `
          : "";
        html += `<div class="table-actions"><label class="small">Group budget / yr&nbsp;</label><input ${readOnlyRef ? "disabled " : ""}type="text" class="budget-money-input" value="${esc(budgetMoneyInputValue((taxBudget[gk] || {}).annual_budget))}" placeholder="${catSum > 0 ? dollars0(catSum) : "$0"}" onfocus="focusBudgetMoney(this)" oninput="updateTaxBudgetMoney('${esc(gk)}','annual_budget',this)" onblur="blurBudgetMoney(this)" style="width:140px"> ${gYearFields}<span class="small">category and line detail disabled — group number wins</span></div>`;
      } else {
        html += '<div class="budget-cat-detail-list">';
        (grp.categories || []).forEach(function (cat) {
          const catId = cat.id;
          const cidEsc = esc(catId);
          const b = taxBudget[catId] || {};
          const catHasExplicitBudget = hasExplicitBudget(catId);
          const lineTotal = catDetailSum(catId);
          const displayTotal =
            lineTotal ||
            (catHasExplicitBudget
              ? budgetAmount(b.annual_budget)
              : spendingRowBudget(cat));
          const hasData =
            catDetailLines(catId).length > 0 ||
            catHasExplicitBudget ||
            spendingRowBudget(cat) > 0 ||
            spendingRowProjectionSeed(cat) > 0;
          html += `<div class="budget-cat-entry"><div class="budget-cat-header" style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--line)"><span class="budget-cat-name" style="font-weight:500">${esc(cat.label)}</span><span class="small" style="color:var(--muted)">${cat.actual || cat.annualized || hasData ? `YTD Actual ${dollars0(spendingRowYtd(cat))} · Annualized Actual ${dollars0(spendingRowAnnualized(cat))}${hasData ? ` · Annual Budget ${dollars0(displayTotal)}/yr · Projection Seed ${dollars0(spendingRowProjectionSeed(cat) || displayTotal)}` : ""}` : ""}</span><span style="margin-left:auto"><button class="danger-link" style="font-size:11px" ${readOnlyRef ? "disabled" : ""} onclick="deleteTaxonomyCat('${cidEsc}','${esc(cat.label)}')">Delete</button></span><label class="small">Annual <input ${readOnlyRef ? "disabled " : ""}type="text" class="budget-money-input" value="${esc(budgetMoneyInputValue(b.annual_budget))}" placeholder="$0" onfocus="focusBudgetMoney(this)" oninput="updateTaxBudgetMoney('${cidEsc}','annual_budget',this)" onblur="blurBudgetMoney(this)" style="width:100px"></label></div></div>`;
        });
        html += "</div>";
        const allGroupLines = [];
        (grp.categories || []).forEach(function (cat) {
          catDetailLines(cat.id).forEach(function (l) {
            allGroupLines.push(l);
          });
        });
        if (allGroupLines.length > 0) {
          html += `<table class="lot-table budget-cat-lines-table" style="margin:4px 0;width:100%"><thead><tr><th>Category</th><th>Label</th><th>Start year</th><th>End year</th><th>One-time year</th><th>Amount / yr</th><th></th></tr></thead><tbody>`;
          allGroupLines.forEach(function (l) {
            const lid = esc(l.line_id);
            const cidEsc = esc(l.category_id || "");
            html += `<tr><td><select ${readOnlyRef ? "disabled " : ""} onchange="updateGroupDetailCategory('${lid}',this.value,'${cidEsc}')">${(grp.categories || []).map((c) => `<option value="${esc(c.id)}"${c.id === l.category_id ? " selected" : ""}>${esc(c.label)}</option>`).join("")}</select></td><td><input value="${esc(l.label || "")}" placeholder="description" oninput="updateCategoryDetail('${lid}','label',this.value,'${cidEsc}')" style="width:120px"></td><td><input type="number" value="${esc(l.start_year || "")}" placeholder="—" oninput="updateCategoryDetail('${lid}','start_year',this.value,'${cidEsc}')" style="width:72px"></td><td><input type="number" value="${esc(l.end_year || "")}" placeholder="forever" oninput="updateCategoryDetail('${lid}','end_year',this.value,'${cidEsc}')" style="width:72px"></td><td><input type="number" value="${esc(l.one_time_year || "")}" placeholder="—" oninput="updateCategoryDetail('${lid}','one_time_year',this.value,'${cidEsc}')" style="width:72px"></td><td><input type="text" class="budget-money-input" value="${esc(budgetMoneyInputValue(l.amount_per_year))}" placeholder="$0" onfocus="focusBudgetMoney(this)" oninput="updateCategoryDetailMoney('${lid}','amount_per_year',this,'${cidEsc}')" onblur="blurBudgetMoney(this)" style="width:100px"></td><td><button class="danger-link" onclick="deleteCategoryDetailRow('${lid}','${cidEsc}')">×</button></td></tr>`;
          });
          html += "</tbody></table>";
        }
        html += `<div class="table-actions" style="margin-top:4px"><button class="btn" style="font-size:12px" ${readOnlyRef ? "disabled " : ""} onclick="addGroupDetailRow('${esc(tt)}','${gj}')">+ Add row</button></div>`;
      }
      html += "</div>";
    });
    html += "</details>";
  });
  html += `<div class="section-note" style="margin-top:12px"><b>${esc(domainBudgetTitle(domain))} total: $${Math.round(grandTotal).toLocaleString()}/yr</b></div>`;
  html += "</div>";
  return html;
}

export function renderCoreSpendingUnified() {
  let html = renderSpendingCore();
  html +=
    '<div style="margin-top:32px">' + renderDomainBudgetPage("core") + "</div>";
  html += '<div style="margin-top:32px">' + renderTaxonomyManager() + "</div>";
  return html;
}

export function renderSpendingSetup() {
  return renderCoreSpendingUnified();
}

// Every export above is also re-attached to window: dashboard.js calls these
// as bare globals, and this file's own rendered HTML uses inline
// onclick="..." handlers, which always resolve through window regardless of
// module scoping. New code should prefer `import` from this module; this
// bridge exists only for callers that cannot move to import in the same pass.
Object.assign(window, {
  updateTaxBudgetMoney,
  updateCategoryDetailMoney,
  coreSpendingGrowthMode,
  renderSpendingCore,
  renderTaxonomyManager,
  showTaxonomyAddForm,
  updateTaxAddGroups,
  reloadDomainBudget,
  currentSpendingTreeForDomain,
  dollars0,
  submitAddTaxonomy,
  deleteTaxonomyCat,
  deleteTaxonomyGroup,
  loadMappingRules,
  addMappingRule,
  updateMappingRule,
  deleteMappingRule,
  renderCategoryMappingRules,
  groupCatIds,
  groupEffectiveBudget,
  spendingRowYtd,
  spendingRowAnnualized,
  spendingRowBudget,
  spendingRowProjectionSeed,
  
  setGroupBudgetMode,
  
  addGroupDetailRow,
  updateGroupDetailCategory,
  deleteCategoryDetailRow,
  
  loadAnnualizedActuals,
  
  trackingBudgetTypesForDomain,
  loadTemplateGroup,
  renderDomainBudgetTable,
  renderCoreSpendingUnified,
  renderSpendingSetup,
  
});
