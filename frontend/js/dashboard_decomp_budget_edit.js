// ── Spending taxonomy and budget-line data/edit helpers ──
// Extracted verbatim from dashboard_decomp_row_model.js (W4-06, ARC-005): taxonomy/budget loading and saving,
// category detail sums and the domain budget page. Bare-global bridge below.
export async function loadTaxonomy(force) {
  if (taxonomyData && !force) return;
  taxonomyLoading = true;
  renderMain();
  try {
    const out = await api("/api/spending/taxonomy");
    if (out && out.success) {
      taxonomyData = out.taxonomy || [];
      taxonomyFlat = out.flat || {};
      taxonomyError = "";
    } else {
      taxonomyError = (out && out.error) || "Failed to load taxonomy.";
    }
  } catch (e) {
    taxonomyError = e.message || "Error loading taxonomy.";
  }
  taxonomyLoading = false;
  renderMain();
}

export async function loadSpendingModel(force) {
  if (spendingModelData && !force) return;
  const cold = !spendingModelData;
  spendingModelLoading = true;
  if (cold) showSpendingModelLoadOverlay();
  try {
    const out = await api("/api/spending/model");
    if (out && out.success) {
      spendingModelData = out;
      spendingModelError = "";
    } else {
      spendingModelData = null;
      spendingModelError =
        (out && out.error) || "Failed to load spending model.";
      if (force) showMessage(spendingModelError, "error");
    }
  } catch (e) {
    spendingModelData = null;
    spendingModelError = e.message || "Error loading spending model.";
    if (force) showMessage(spendingModelError, "error");
  }
  spendingModelLoading = false;
  if (cold) hideSpendingModelLoadOverlay();
  renderMain();
}

export function clearSpendingCaches() {
  spendingModelData = null;
  spendingModelError = "";
  taxonomyData = null;
  taxonomyFlat = {};
  taxonomyError = "";
  taxBudgetLoaded = false;
  budgetLinesLoaded = false;
}

export async function saveMappingRulesData() {
  try {
    await api("/api/spending/rules/save", {
      method: "POST",
      body: JSON.stringify({ rules: mappingRules || [] }),
    });
    rulesChanged = false;
    renderMain();
    showMessage("Advanced auto-mapping rules saved.");
  } catch (e) {
    showMessage("Error saving rules: " + e.message, "error");
  }
}

export async function loadBudgetLines(force) {
  if (budgetLinesLoaded && !force) return;
  try {
    const out = await api("/api/spending/budget-lines");
    budgetLines = out && out.success ? out.lines || [] : [];
    if (!taxonomyData) await loadTaxonomy(false);
  } catch (e) {
    budgetLines = [];
  }
  budgetLines.forEach((l) => {
    if (l.mode === "summary") budgetSectionMode[l.section] = "summary";
    if (l.section === "category_budget" && l.category_id)
      categoryBudgetMode[l.category_id] = "detail";
  });
  budgetLinesLoaded = true;
  budgetLinesChanged = false;
  renderMain();
}

export async function loadTaxonomyBudget(force) {
  if (taxBudgetLoaded && !force) return;
  try {
    const out = await api("/api/spending/budget/taxonomy");
    if (out && out.success) {
      taxBudget = out.budget || {};
    } else {
      taxBudget = {};
      if (force)
        showMessage(
          (out && out.error) || "Unable to load category budgets.",
          "error",
        );
    }
  } catch (e) {
    taxBudget = {};
    if (force)
      showMessage("Error loading category budgets: " + e.message, "error");
  }
  taxBudgetLoaded = true;
  taxBudgetChanged = false;
  restoreGroupBudgetModes();
  renderMain();
}

export async function saveBudgetLines() {
  try {
    await api("/api/spending/budget-lines", {
      method: "POST",
      body: JSON.stringify({ lines: budgetLines }),
    });
    budgetLinesChanged = false;
    renderMain();
    showMessage("Spending category changes saved.");
  } catch (e) {
    showMessage("Error saving spending budget: " + e.message, "error");
  }
}

export function markBudgetLinesDirty() {
  budgetLinesChanged = true;
  taxBudgetChanged = true;
  markBuildStale();
  scheduleStatusUpdate();
}

export function catDetailLines(catId) {
  return (budgetLines || []).filter((l) => l.category_id === catId);
}

export function budgetAmount(value) {
  return budgetMoneyNumber(value);
}

// #344: mirrors spending_tracker._line_amount_for_year. `y` = selected spending year (display); saved budgets pass the real year.
export function catDetailSum(catId, y = selectedSpendingYear()) {
  const n = (v) => parseInt(v, 10) || 0, ok = (l) => n(l.one_time_year) ? n(l.one_time_year) === y : !((n(l.start_year) && y < n(l.start_year)) || (n(l.end_year) && y > n(l.end_year)));
  return catDetailLines(catId).reduce((s, l) => s + (ok(l) ? budgetAmount(l.amount_per_year) || 0 : 0), 0);
}

export function hasExplicitBudget(key) {
  const b = taxBudget[key];
  return !!(
    b &&
    b.annual_budget !== undefined &&
    b.annual_budget !== null &&
    b.annual_budget !== ""
  );
}

export function groupCatSum(tt, grp, y) {
  const ids = groupCatIds(tt, grp);
  if (!ids.length) {
    const mg = groupModelData(tt, grp);
    return budgetAmount(mg && mg.budget);
  }
  return ids.reduce((s, id) => s + (catEffectiveBudget(id, y) || 0), 0);
}

export function groupKeyFor(tt, grp) {
  return "grp::" + tt + "::" + grp;
}

export function groupIsSummary(tt, grp) {
  return groupBudgetMode[tt + "::" + grp] === "summary";
}

export function syncCategoryTotal(catId) {
  if (!taxBudget[catId]) taxBudget[catId] = { annual_budget: 0, notes: "" };
  taxBudget[catId].annual_budget = Math.round(catDetailSum(catId, new Date().getFullYear()));
  taxBudgetChanged = true;
  syncTaxonomyBudgetToBudgetLines();
}

export function updateCategoryDetail(lineId, field, val, catId) {
  const l = budgetLines.find((x) => x.line_id === lineId);
  if (l) l[field] = val;
  syncCategoryTotal(catId);
  markBudgetLinesDirty();
}

export function syncTaxonomyBudgetToBudgetLines() {
  try {
    if (!budgetLines || !taxBudget) return;
    const domainCategories = {
      travel: [
        "travel_plane",
        "travel_housing",
        "travel_meals",
        "travel_vacation",
      ],
      healthcare: [
        "medical",
        "dental",
        "vision",
        "healthcare_premium",
        "drugs_rx",
      ],
      housing: [
        "mortgage",
        "rent",
        "property_tax",
        "homeowners_insurance",
        "utilities",
        "maintenance",
      ],
    };
    Object.entries(domainCategories).forEach(([domain, catIds]) => {
      const domainTotal = catIds.reduce((sum, catId) => {
        const budget = taxBudget[catId];
        return (
          sum +
          (budget && budget.annual_budget
            ? parseFloat(budget.annual_budget)
            : 0)
        );
      }, 0);
      if (domainTotal > 0) {
        const existingLine = budgetLines.find(
          (l) => l.section === domain && l.category_id === domain + "_total",
        );
        if (existingLine) {
          existingLine.amount_per_year = String(domainTotal);
        } else {
          const newLine = {
            section: domain,
            line_id: domain + "_total_" + Date.now(),
            label:
              domain.charAt(0).toUpperCase() +
              domain.slice(1) +
              " Budget Total",
            category_id: domain + "_total",
            start_year: "",
            end_year: "",
            one_time_year: "",
            amount_per_year: String(domainTotal),
            mode: "summary",
            notes: "Auto-synced from taxonomy budget",
          };
          budgetLines.push(newLine);
        }
      }
    });
    budgetLinesChanged = true;
  } catch (e) {
    console.warn("Sync error between taxonomy budget and budget lines:", e);
  }
}

export async function saveTaxonomyBudgetData() {
  try {
    await api("/api/spending/budget/taxonomy/save", {
      method: "POST",
      body: JSON.stringify({ budget: taxBudget }),
    });
    syncTaxonomyBudgetToBudgetLines();
    taxBudgetChanged = false;
    renderMain();
    showMessage("Spending category changes saved.");
  } catch (e) {
    showMessage("Error saving budget: " + e.message, "error");
  }
}

export function updateTaxBudget(catId, field, val) {
  if (!taxBudget[catId]) taxBudget[catId] = { annual_budget: 0, notes: "" };
  taxBudget[catId][field] = val;
  taxBudgetChanged = true;
  syncTaxonomyBudgetToBudgetLines();
}

// Flips the two-state Annualize icon (green=annualize, red=don't annualize)
// for a category or group budget key. Re-renders so the icon's color/tooltip
// picks up the new state immediately.
export function toggleAnnualizeFlag(key, currentlyNoAnnualize) {
  updateTaxBudget(key, "no_annualize", currentlyNoAnnualize ? "FALSE" : "TRUE");
  renderMain();
}

export function domainBudgetTitle(domain) {
  return (
    {
      core: "Spending Categories",
      housing: "Housing Budget Detail",
      healthcare: "Wellness Budget Detail",
      travel: "Travel Budget Detail",
      large_discretionary: "Large Discretionary Budget Detail",
    }[domain] || "Budget Detail"
  );
}

export function renderDomainBudgetPage(domain, opts) {
  opts = opts || {};
  if (
    !taxonomyData ||
    !spendingModelData ||
    !budgetLinesLoaded ||
    !taxBudgetLoaded
  ) {
    setTimeout(() => {
      loadTaxonomy(false);
      loadSpendingModel(false);
      loadBudgetLines(false);
      loadTaxonomyBudget(false);
    }, 0);
  }
  // The explanation of each budget domain lives in the help panel (HELP_SECTIONS spending_core.*).
  const domainKey = { core: "spending_core.spending_categories", housing: "spending_core.housing_costs", healthcare: "spending_core.wellness", travel: "spending_core.travel_budget" }[domain] || "spending_core.large_discretionary";
  const domainBtn = window.RPHelp?.sectionButtonHtml(domainKey) || "";
  let html = '<div class="holdings" data-help-section="' + domainKey + '">';
  if (!opts.embedded)
    html +=
      '<h3 class="group-title">' + esc(domainBudgetTitle(domain)) + " " + domainBtn + "</h3>";
  else html += "<div>" + domainBtn + "</div>";
  html +=
    '<div class="table-actions"><button class="btn primary" ' +
    (budgetLinesChanged || taxBudgetChanged ? "" : "disabled") +
    ' onclick="saveAll(true)">Save Changes</button><button class="btn" onclick="reloadDomainBudget(\'' +
    esc(domain) +
    "')\">Reload</button>" +
    (domain === "core"
      ? '<button class="btn" onclick="recoverPriorSpendingBudget()">Recover prior budget values</button><button class="btn" onclick="hideUnusedTemplateCategories()">Hide unused template categories</button>'
      : "") +
    "</div>";
  if (!taxonomyData) {
    html += '<div class="question"><b>Loading…</b></div></div>';
    return html;
  }
  html += renderDomainBudgetTable(domain);
  html += "</div>";
  return html;
}
Object.assign(window, {
  budgetAmount, catDetailLines, catDetailSum, clearSpendingCaches, domainBudgetTitle, groupCatSum,
  groupIsSummary, groupKeyFor, hasExplicitBudget, loadBudgetLines, loadSpendingModel, loadTaxonomy,
  loadTaxonomyBudget, markBudgetLinesDirty, renderDomainBudgetPage, saveBudgetLines,
  saveMappingRulesData, saveTaxonomyBudgetData, syncCategoryTotal, syncTaxonomyBudgetToBudgetLines,
  toggleAnnualizeFlag, updateCategoryDetail, updateTaxBudget,
});
